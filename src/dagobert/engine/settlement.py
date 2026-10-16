"""The December settlement: the income tax of the year, the Vorabpauschale, the Günstigerprüfung
and the sales that pay the bill."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np

from dagobert import tax
from dagobert.engine.income import Income
from dagobert.engine.portfolio import Portfolio
from dagobert.engine.state import Assessed
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
    BoolArray,
    FloatArray,
)

# A sale for the December bill raises the bill. Cover and settle again until no path owes a cent
# (nominal) more: each round sells about the marginal rate of the one before, a gain at the top
# rate needs about 20 rounds
LATE_ROUNDS, CENT = 30, 0.01


class Settlement(Income, Portfolio):
    def _year_income(self) -> tuple[tax.YearIncome, FloatArray]:
        """The income of the year to settle, after the Vorabpauschale and the interest, and their
        flat tax, nominal."""
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
        return tax.YearIncome(
            salary_gross=acc.salary_gross,
            severance=acc.severance,
            alg1=acc.lohnersatz,
            pension_taxable=self._pension_taxable(acc.pension_gross) + acc.basisrente,
            other_taxable=acc.other_taxable + private,
            rent=acc.rent,
            # the yearly work expenses count for the months with a salary (§9a S. 1 Nr. 1 a)
            werbungskosten=self.a.tax.werbungskosten * acc.sv_months / 12,
            work=acc.deduct.get(Deduction.WORK, zero),
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
        ), flat_tax

    def _settle_year(
        self, year_income: tax.YearIncome, flat_tax: FloatArray
    ) -> tuple[tax.YearIncome, tax.YearSettlement]:
        """Settle the year (`_year_income`) after a harvest, pay the bill and book its tax.
        Returns the year as settled."""
        acc = self.acc
        d = self.deflator
        if self.a.tax.harvest and self.m.month.month == 12:
            flat_tax = flat_tax + self._harvest(year_income)
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
        that gain. Beyond the loss pot the gain is at most what the equity holds and, of a GKV
        member who is voluntary in the next January, what keeps the base of the next year at its
        minimum (`_kv_room`), so a pot goes along only where the room still pays for it. Returns
        the flat tax, which the Günstigerprüfung of the settlement refunds. A marker gives the gain
        before the Teilfreistellung in the first December in which half of the paths harvest."""
        held = np.maximum(self.taxable_gain / self.deflator - self.losses, 0.0)
        room = tax.harvest_room(
            year,
            self.acc.pauschbetrag_left,
            self.losses,
            self.ty,
            carryback=self.a.tax.loss_carryback and bool(self.assessed),  # a year to go back to
            cap=np.clip(self._kv_room(), 0.0, held) if self._voluntary_next() else held,
        )
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
        """The income of the year, with the decision on the carryback of the loss of the year
        before (`_waive_back`) and its refund (`_refund_back`), then the settlement of the year
        and a deficit cover for its bill. What that cover sells joins the settlement: pay the
        change and cover again, until no path owes a cent more (each round sells less, at most
        `LATE_ROUNDS`). Then the §23 losses left carry into the next year, the church tax that the
        withholding left, which the next year pays, the loss of the year, back into the years
        before (`_carry_back`) unless `tax.loss_carryback` is off, the rest with the Verlustvortrag
        (§10d EStG, nominal), and the Rentenfreibetrag after the first full pension year.
        `settled` keeps the regular bill of all rounds for VPW, which spreads it over the next
        year; the Fünftelregelung part (a refund of the withholding) is a one-off, and so is the
        refund of a carryback."""
        year_income, flat_tax = self._year_income()
        year_income = self._waive_back(year_income)
        self._refund_back()
        before = self.cash.copy()
        year = self._settle_year(year_income, flat_tax)
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
        self.church_due = (year[1].church - self.acc.church_withheld) * self.deflator
        left = year[1].loss_left
        if self.a.tax.loss_carryback:
            left = left - self._carry_back(year[1].loss)
            self.assessed.appendleft(Assessed(*year, self.deflator.copy()))
        self.income_losses = left * self.deflator
        self._freeze_rentenfreibetrag()

    def _waive_back(self, income: tax.YearIncome) -> tax.YearIncome:
        """§10d Abs. 1 S. 6 EStG: the return of the year before, settled now when the income of
        this year is known, waives the carryback of its loss as a whole or not at all. Per path
        this year settles with the Verlustvortrag as it is and with the loss taken back on top
        (`loss_back`; the church tax that its refund takes off this year, `church_back`, stays
        paid): the waiver where what the loss then saves here (income tax, Soli, church and trade
        tax, the refund of the Günstigerprüfung) exceeds the refund, `refund_back` and
        `flat_back`, both nominal now, by more than a cent. What the pot keeps after this year
        counts nothing. A waiver pays no refund, and the years amended settle again without the
        loss (`Assessed.pending`), so a later loss sees their room. Returns this year's income as
        decided."""
        if not self.loss_back.any():
            return income
        d = self.deflator
        back, church = self.loss_back / d, self.church_back / d
        self.loss_back, self.church_back = np.zeros(self.paths), np.zeros(self.paths)

        def waived(paths: BoolArray) -> tax.YearIncome:
            return replace(
                income,
                loss_carried=income.loss_carried + np.where(paths, back, 0.0),
                church_paid=income.church_paid + np.where(paths, church, 0.0),
            )

        kept, waiver = (
            tax.year_settlement(year, self.ty, church=self.church)
            for year in (income, waived(np.full(self.paths, True)))
        )
        saved = (kept.total - waiver.total + waiver.refund - kept.refund) * d
        waive = saved > self.refund_back + self.flat_back + CENT
        self.refund_back = np.where(waive, 0.0, self.refund_back)
        self.flat_back = np.where(waive, 0.0, self.flat_back)
        for year in self.assessed:
            if waive.any() and np.any(year.pending):
                year.income = replace(
                    year.income,
                    loss_back=year.income.loss_back - np.where(waive, year.pending, 0.0),
                )
                year.settlement = tax.year_settlement(year.income, self.ty, church=self.church)
            year.pending = 0.0
        return waived(waive)

    def _carry_back(self, loss: FloatArray) -> FloatArray:
        """§10d Abs. 1 EStG: the negative Gesamtbetrag der Einkünfte `loss` of this year (real)
        goes back into the years that the run settled before it (`assessed`, `tax.carryback`), up
        to their rooms at their price levels: each settles again with it. What that saves of the
        income tax, Soli and church tax, and what its Günstigerprüfung refunds more of the flat
        tax, come back with the next settlement, nominal (the assessment of this year comes next
        year, `_refund_back`), unless that settlement waives the carryback (`_waive_back`, which
        `loss_back` and `church_back` serve). The church tax refunded lowers the church tax paid
        in the year of the refund, a Sonderausgabe (`church_due`). Returns the loss taken back,
        real."""
        taken = np.zeros(self.paths)
        if not loss.any():
            return taken
        d = self.deflator
        rooms = [year.settlement.room * year.level / d for year in self.assessed]
        for year, back in zip(self.assessed, tax.carryback(loss, rooms, self.ty), strict=True):
            year.pending = back * d / year.level
            income = replace(year.income, loss_back=year.income.loss_back + year.pending)
            again = tax.year_settlement(income, self.ty, church=self.church)
            settled = year.settlement
            church = (settled.church - again.church) * year.level
            self.refund_back += (settled.total - again.total) * year.level
            self.flat_back += (again.refund - settled.refund) * year.level
            self.church_due -= church
            self.church_back += church
            year.income, year.settlement = income, again
            taken += back
        self.loss_back = taken * d
        return taken

    def _refund_back(self) -> None:
        """Pay what a loss carried back the year before refunds: the income tax with its Soli and
        church tax as `income tax`, the flat tax of a Günstigerprüfung as capital gains tax, both
        in this month."""
        refund, flat = self.refund_back, self.flat_back
        self.cash += refund + flat
        if refund.any():
            self.flows.taxes += refund
            self._note(TAX, "", INCOME_TAX, -refund)
        if flat.any():
            self._report_capital_tax(-flat)
        self.refund_back, self.flat_back = np.zeros(self.paths), np.zeros(self.paths)

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
