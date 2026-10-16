"""The December settlement: the income tax of the year, the Vorabpauschale, the Günstigerprüfung
and the sales that pay the bill."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np

from dagobert import tax
from dagobert.engine.income import Income
from dagobert.engine.portfolio import Portfolio
from dagobert.model.months import add_months
from dagobert.model.streams import Deduction
from dagobert.model.taxes import Allowance
from dagobert.result import (
    INCOME_TAX,
    ONEOFF_OUT,
    ONEOFF_TAX,
    SETTLEMENT,
    TAX,
    TRADE_TAX,
    FloatArray,
)

# A sale for the December bill raises the bill. Cover and settle again until no path owes a cent
# (nominal) more: each round sells about the marginal rate of the one before, a gain at the top
# rate needs about 20 rounds
LATE_ROUNDS, CENT = 30, 0.01


class Settlement(Income, Portfolio):
    def _settle_year(self) -> tuple[tax.YearIncome, tax.YearSettlement]:
        acc = self.acc
        d = self.deflator
        growth = self.eq_index[:, self.m.i] / acc.index_jan - 1
        vp = tax.vorabpauschale(self._vorab_base(growth), growth, self.ty)
        # taxed after the Teilfreistellung of each depot, at the share of December, the year's
        # purchases in it; a later sale gains less by all of it, so less after the Teilfreistellung
        # by the taxed part (§19 Abs. 1 S. 3 and 4 InvStG)
        taxed = vp * self.taxable_share
        self.taxable_basis += taxed
        flat_tax = self._flat_tax(taxed, vorab=True) + self._flat_tax(acc.interest * d)
        private, _ = tax.private_sales(acc.private_sales, self.private_losses, self.ty)
        zero = np.zeros(self.paths)
        trades = [
            (t.profit, *tax.trade_tax(t.profit, t.hebesatz, self.ty)) for t in acc.trade.values()
        ]
        year_income = tax.YearIncome(
            salary_gross=acc.salary_gross,
            severance=acc.severance,
            alg1=acc.lohnersatz,
            pension_taxable=self._pension_taxable(acc.pension_gross) + acc.basisrente,
            other_taxable=acc.other_taxable + private,
            rent=acc.rent,
            # the yearly work expenses count for the months with a salary (§9a S. 1 Nr. 1 a)
            werbungskosten=self.a.tax.werbungskosten * acc.sv_months / 12,
            rv_paid=acc.rv_paid,
            rv_employer=acc.rv_employer,
            health_deductible=acc.health_deductible,
            capital_income=acc.capital_income,
            capital_tax_paid=acc.capital_tax_paid,
            av_deduction=acc.av_deduction,
            av_zulage=acc.av_zulage,
            church_paid=acc.church_withheld + self.church_due / d,
            trade_income=sum((np.maximum(profit, 0.0) for profit, _, _ in trades), zero),
            trade_tax=sum((gewst for _, gewst, _ in trades), zero),
            trade_credit=sum((credit for _, _, credit in trades), zero),
            loss_carried=self.income_losses / d,
            donations=acc.deduct.get(Deduction.DONATION, zero),
            childcare=acc.deduct.get(Deduction.CHILDCARE, zero),
            children=self.a.person.children_in(self.ty.childcare_age, self.m.month.year),
            child_years=self._child_years(),
            entlastung=self._entlastung(),
            household=acc.deduct.get(Deduction.HOUSEHOLD, zero),
            craftsman=acc.deduct.get(Deduction.CRAFTSMAN, zero),
        )
        if self.a.tax.harvest and self.m.month.month == 12:
            flat_tax += self._harvest(year_income)
            year_income = replace(
                year_income,
                capital_income=acc.capital_income,
                capital_tax_paid=acc.capital_tax_paid,
            )
        settlement = tax.year_settlement(year_income, self.ty, church=self.church)
        income_due = (settlement.total - acc.withheld) * d
        capital_due = flat_tax - settlement.refund * d
        january = self._january
        self.cash -= income_due + capital_due
        self.flows.taxes -= income_due
        self._report_capital_tax(capital_due, since=january)
        # what the year would owe without its severance is the regular part of the bill
        plain = tax.year_settlement(
            replace(year_income, severance=0.0), self.ty, church=self.church
        ).total
        regular = plain - (acc.withheld - acc.severance_withheld)
        self.oneoff_tax = income_due - regular * d
        if self.ledger is not None:
            # the months that earn carry the tax: a half year without income shows none
            earned = np.maximum(np.diff(self.earned[january : self.m.i + 1], prepend=0.0), 0.0)
            trade = settlement.trade_tax
            self._note(TAX, "", INCOME_TAX, (regular - trade) * d, since=january, weights=earned)
            if trade.any():
                self._note(TAX, "", TRADE_TAX, trade * d, since=january, weights=earned)
            self._note(ONEOFF_OUT, ONEOFF_TAX, SETTLEMENT, self.oneoff_tax)
        return year_income, settlement

    @property
    def _months_of_year(self) -> list[date]:
        """The months of this year in the run, up to this one."""
        return [add_months(self.start, i) for i in range(self._january, self.m.i + 1)]

    def _child_years(self) -> tuple[tax.ChildYear, ...]:
        """The children that count in the months of the year in the run, oldest first, with
        those months (§32 Abs. 6 S. 5 EStG: a twelfth of the allowances each)."""
        months = self._months_of_year
        return tuple(
            tax.ChildYear(n, child.freibetrag is Allowance.FULL)
            for child in sorted(self.a.person.children_born, key=lambda c: c.born)
            if (n := sum(map(child.counts, months)))
        )

    def _entlastung(self) -> FloatArray:
        """The Entlastungsbetrag of a single parent over the months of the year in the run."""
        if not self.a.tax.alleinerziehend:
            return np.zeros(self.paths)
        counting = [len(self.a.person.counting(month)) for month in self._months_of_year]
        return np.full(self.paths, tax.entlastungsbetrag(counting, self.ty))

    def _harvest(self, year: tax.YearIncome) -> FloatArray:
        """Sell the equity whose taxable gain fits the tax-free room of the year
        (`tax.harvest_room`) and buy it back at once: the units stay, the taxable basis rises by
        that gain. A GKV member who is voluntary in the next January takes no more than keeps the
        base of the next year at its minimum (`_kv_room`). Returns the flat tax, which the
        Günstigerprüfung of the settlement refunds. A marker gives the gain before the
        Teilfreistellung in the first December in which half of the paths harvest."""
        room = tax.harvest_room(year, self.acc.pauschbetrag_left, self.losses, self.ty)
        if self._voluntary_next():
            room = np.minimum(room, np.maximum(self._kv_room(), 0.0))
        gain = np.minimum(room * self.deflator, np.maximum(self.taxable_gain, 0.0))
        if not self.harvested and (gain > 0).mean() >= 0.5:
            self.harvested = True
            # exact for depots of one rate, as the share and the gain share then agree
            plain = gain / np.where(self.taxable_share > 0, self.taxable_share, 1.0)
            self._mark("harvest", amount=float(np.median(plain[gain > 0])), form="once")
        self.taxable_basis += gain
        return self._flat_tax(gain)

    def _vorab_base(self, growth: FloatArray) -> FloatArray:
        """The units of the year end in January euros that owe the Vorabpauschale, those
        bought in the year by their twelfths. A sale takes the units held since January first
        (FIFO, §20 Abs. 4 S. 7 EStG); beyond them it shrinks the purchases pro rata."""
        acc = self.acc
        units = self.equity / (1 + growth)
        jan_units = np.clip(units - acc.bought, 0.0, acc.equity_jan)
        rest = np.divide(
            acc.weighted * (units - jan_units),
            acc.bought,
            out=np.zeros(self.paths),
            where=acc.bought > 0,
        )
        return np.asarray(jan_units + rest)

    def _settle_december(self) -> None:
        """The settlement of the year, then a deficit cover for its bill. What that cover sells
        joins the settlement: pay the change and cover again, until no path owes a cent more
        (each round sells less, at most `LATE_ROUNDS`). Then the §23 losses left and the
        Verlustvortrag (§10d EStG, nominal) carry into the next year, the church tax that the
        withholding left, which the next year pays, and the Rentenfreibetrag after the first full
        pension year. `settled` keeps the regular bill of all rounds for VPW, which spreads it over
        the next year; the Fünftelregelung part (a refund of the withholding) is a one-off."""
        before = self.cash.copy()
        year = self._settle_year()
        self.settled = before - self.cash - self.oneoff_tax
        for _ in range(LATE_ROUNDS):
            self._cover_deficit()
            before = self.cash.copy()
            year = self._settle_late_sales(*year)
            self.settled += before - self.cash
            if not (self.cash < before - CENT).any():
                break
        _, self.private_losses = tax.private_sales(
            self.acc.private_sales, self.private_losses, self.ty
        )
        self.income_losses = year[1].loss_left * self.deflator
        self.church_due = (year[1].church - self.acc.church_withheld) * self.deflator
        self._freeze_rentenfreibetrag()

    def _settle_late_sales(
        self, year_income: tax.YearIncome, settled: tax.YearSettlement
    ) -> tuple[tax.YearIncome, tax.YearSettlement]:
        """A deficit after the December bill sells equity at the flat rate, and gold or crypto.
        Their gains join the settlement of the year, the Günstigerprüfung and the private
        sales: pay the change. Returns the year as settled now."""
        acc = self.acc
        private, _ = tax.private_sales(acc.private_sales, self.private_losses, self.ty)
        income = replace(
            year_income,
            other_taxable=acc.other_taxable + private,
            capital_income=acc.capital_income,
            capital_tax_paid=acc.capital_tax_paid,
        )
        late = tax.year_settlement(income, self.ty, church=self.church)
        refund = (late.refund - settled.refund) * self.deflator
        owed = (late.total - settled.total) * self.deflator
        self.cash += refund - owed
        if refund.any():
            self._report_capital_tax(-refund, since=self._january)
        if owed.any():
            self.flows.taxes -= owed
            self._note(TAX, "", INCOME_TAX, owed)
        return income, late
