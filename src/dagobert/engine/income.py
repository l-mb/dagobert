"""The streams of a month: salary with SV and withholding, pension and its claim, ALG1, the PKV
premiums and subsidies, the bAV policies, the Altersvorsorgedepots, a severance, and after the
onset of a disability the Krankengeld, the EM-Rente and the benefit of a BU policy."""

from __future__ import annotations

from datetime import date

import numpy as np

from dagobert import sv, tax
from dagobert.engine.core import REARM
from dagobert.engine.health import Health
from dagobert.engine.state import AvState, MonthPay, PolicyState, StreamState
from dagobert.model.assets import PensionPolicy
from dagobert.model.months import add_months, months_between, months_of_age
from dagobert.model.streams import Deduction, Stream, StreamKind
from dagobert.result import (
    AV,
    BENEFIT,
    CARE,
    CONTRIBUTION,
    CONVERSION,
    DRAW,
    EM_RENTE,
    EMPLOYER,
    GUARANTEE,
    INCOME_TAX,
    KINDERGELD,
    KRANKENGELD,
    KV,
    LOAN_PRINCIPAL,
    MOVE_OUT,
    MOVED,
    NONCASH,
    ONEOFF_CONTRIBUTION,
    ONEOFF_IN,
    ONEOFF_OUT,
    ONEOFF_TAX,
    OWN_PREMIUM,
    PAYOUT,
    PKV_SUBSIDY,
    PROFIT,
    PV,
    RV,
    SALARY,
    SAVINGS_PLAN,
    SEVERANCE,
    SOURCE,
    SPENDING,
    SUBSIDY,
    TAX,
    UPKEEP,
    ZULAGE,
    BoolArray,
    FloatArray,
)

# the age from which the months count in the Gesamtleistungsbewertung of an EM-Rente: the
# belegungsfähige Gesamtzeitraum starts at the 17th birthday (§72 Abs. 2 SGB VI)
INSURED_FROM = 17


class Income(Health):
    def _accrue(self, s: StreamState) -> None:
        """The run rate of a stream paid every n months that pays this month (`_spread`)."""
        spec = s.spec
        if self.ledger is None or spec.every == 1 or not self._pays(s):
            return
        match spec.kind:
            case StreamKind.SALARY:
                self._spread((SOURCE, SALARY, spec.name), self._salary_nominal(s), spec.every)
            case StreamKind.SELF_EMPLOYED:
                self._spread((SOURCE, PROFIT, spec.name), self._profit_nominal(s), spec.every)
            case StreamKind.OTHER_INCOME:
                self._spread((SOURCE, "", spec.name), self._nominal(s), spec.every)
            case StreamKind.EXPENSE | StreamKind.RV_VOLUNTARY:
                self._spread((SPENDING, spec.cat, spec.name), -self._nominal(s), spec.every)
            case _:  # a savings plan spreads what it paid, in `_save_plans`
                return

    def _premium(self, *parts: str) -> FloatArray:
        """Nominal PKV premium due this month for the `health` parts."""
        return sum(
            (-self._nominal(s) for s in self.streams if s.spec.health in parts and self._pays(s)),
            np.zeros(self.paths),
        )

    def _basis(self) -> FloatArray:
        """Nominal Basisabsicherung part of the PKV premium due this month."""
        return sum(
            (
                -self._nominal(s) * self._deductible_share(s.spec)
                for s in self.streams
                if s.spec.health and self._pays(s)
            ),
            np.zeros(self.paths),
        )

    def _deductible_share(self, spec: Stream) -> float:
        """The share of a PKV premium or of an expense with `deduct` that counts for the tax."""
        if spec.deductible is not None:
            return spec.deductible
        return 1.0 if spec.deduct or spec.health == "pv" else self.ty.pkv_basis_share

    def _severance(self, gross: float | FloatArray, label: str = SEVERANCE) -> FloatArray:
        """Income under the Fünftelregelung, nominal at the event date. The withholding taxes
        it in full on top of the salary of the year so far, the settlement refunds the rest.
        Returns what reached the cash."""
        real = gross / self.deflator
        withheld = self._withhold(
            lambda church: tax.withholding_oneoff(
                self.acc.salary_gross, real, self.ty, church=church
            )
        )
        self.acc.severance += real
        self.acc.severance_withheld += withheld
        self._note(ONEOFF_IN, SEVERANCE, label, gross)
        self._note(ONEOFF_OUT, ONEOFF_TAX, label, withheld * self.deflator)
        self._receive(np.broadcast_to(gross, self.paths), withheld * self.deflator)
        return gross - withheld * self.deflator

    def _apply_streams(self) -> None:
        """The streams of the month, each step into the cash: the claim to ALG1 takes the days of
        the month (`_claim_alg1`), the plain streams pay and the salaries and pensions add up
        (`_pay_streams`), the Kindergeld, then what follows from them: the salaries and pensions
        with their SV, tax and PKV subsidies
        (`_pay_salaries`), the Altersvorsorgedepots and the bAV policies, the GKV beyond the
        salary, a business, the child-raising years on the points of the month, the costs of
        the month and, under VPW, the flexible streams (`_pay_flexible`)."""
        p = self.pension
        p.counts_now = p.compulsory_now = False
        self.bu_paid = np.zeros(self.paths)
        points = p.points.copy()
        self._disable()
        self._mark_switch()
        self._claim_alg1()
        pay = self._pay_streams()
        self._mark_onset()
        self._pay_kindergeld()
        sick = self._pay_sick()
        kv_base_real, deductible = self._pay_salaries(pay)
        monthly = self._av_flows()
        premium = self._policy_flows()
        on_alg1 = self._on_alg1()
        gkv = self._pay_gkv(
            pay.salary_real, kv_base_real, pay.rente, monthly, on_alg1=on_alg1, sick=sick
        )
        own = deductible + gkv + premium  # what the reserve of a profit takes off
        own_real = np.where(pay.salary_real > 0, 0.0, own / self.deflator)
        self._pay_profit(pay.salary_real, own_real, on_alg1=on_alg1)
        self._raise_children(p.points - points)
        self._fix_sick_pay(pay)
        self._costs()
        p.insured_months += p.counts_now
        p.compulsory.append(p.compulsory_now)
        self.earns = (pay.salary_real != 0) | self._business()[0]  # for the next spending rule
        self._pay_flexible()
        self._record_earned()

    def _disable(self) -> None:
        """The onsets of this month (`Core.onset`): whether an EM-Rente follows (§43 Abs. 1 S. 1
        Nr. 2, 3, §50 Abs. 1 SGB VI: the allgemeine Wartezeit and three years of Pflichtbeiträge
        in the last five, and a pension stream from points), and its points, frozen now (§75 Abs.
        2 S. 1): those reached and the Zurechnungszeit (§59 Abs. 2) to its end in the year of the
        Rentenbeginn (§253a Abs. 3), valued by the points over the months from the start of the
        insurance, at the earliest the 17th birthday (§§71, 72: a gap lowers it)."""
        new = self.onset == self.m.i
        if not new.any():
            return
        grv, p, ty = self._grv(), self.pension, self.ty
        person, month = self.a.person, self.m.month
        self.em_ok[new] = (
            grv is not None
            and p.insured_months >= ty.em_wartezeit_months
            and sum(p.compulsory) >= ty.em_pflicht_months
        )
        if grv is None:
            return
        reached = (grv.spec.points or 0.0) + p.points[new]
        adult = add_months(person.born, 12 * INSURED_FROM)
        months = months_between(max(person.rv_since or adult, adult), month)
        begins = add_months(month, ty.em_start_months)
        added = max(ty.zurechnung_months(begins.year) - months_of_age(person.born, month), 0)
        p.em_points[new] = reached * (1 + added / months if months > 0 else 1)

    def _mark_onset(self) -> None:
        """The marker of a forced onset, after the streams: an old-age claim of its month drops
        it (`_claim_pension`)."""
        spec = self.a.disability
        if spec is not None and spec.at == self.m.month and (self.onset == self.m.i).any():
            self._mark("disability")

    def _pay_sick(self) -> BoolArray:
        """The Krankengeld of the paths after the Entgeltfortzahlung up to the EM-Rente
        (`SickPay`, fixed by `_fix_sick_pay`) into the cash, less the member's shares of RV, ALV
        and PV: tax-free under the Progressionsvorbehalt at its gross (§3 Nr. 1 a, §32b Abs. 1 S. 1
        Nr. 1 b EStG), the RV share an Altersvorsorgeaufwand, the PV share deductible. Such a month
        with RV is one of Pflichtbeiträge (§3 S. 1 Nr. 3 SGB VI), which earns no point for the
        EM-Rente (§75 Abs. 2). It ends with the old-age claim (§50 Abs. 1 S. 1 Nr. 1 SGB V).
        Returns the paths on which it keeps a compulsory member of the GKV free of KV (§192 Abs. 1
        Nr. 2, §224 Abs. 1 S. 1 SGB V)."""
        i, ty, sick = self.m.i, self.ty, self.sick
        now = (
            (self.pension.claimed is None)
            & (self.onset >= 0)
            & (i >= self.onset + ty.efzg_months)
            & (i < self.onset + ty.em_start_months)
            & (sick.gross > 0)
        )
        if not now.any():
            return now
        d, p = self.deflator, self.pension
        gross, rv, alv, pv = (x * now for x in (sick.gross, sick.rv, sick.alv, sick.pv))
        self._receive(gross, rv + alv + pv)
        self._note(SOURCE, "", KRANKENGELD, gross)
        for item, part in ((RV, rv), (AV, alv), (PV, pv)):
            self._note(TAX, "", item, part)
        self.acc.lohnersatz += gross / d
        self.acc.rv_paid += rv / d
        self.acc.health_deductible += pv / d
        if rv.any():
            p.counts_now = p.compulsory_now = True
        return np.asarray(now & sick.employed)

    def _fix_sick_pay(self, pay: MonthPay) -> None:
        """In the last month of the Entgeltfortzahlung, the Krankengeld of a member of the GKV
        (`sv.krankengeld_month`) on the regular salary of the month (`last_salary`), else on the
        profit of a business with `tax.self_employed.krankengeld`, nominal in this month."""
        last = (self.onset >= 0) & (self.onset + self.ty.efzg_months - 1 == self.m.i)
        if self.pkv or not last.any():
            return
        d, opts, sick = self.deflator, self.a.tax, self.sick
        on, profit = self._business()
        employed = last & (pay.recurring_real > 0)
        business = last & ~employed & on & opts.self_employed.krankengeld
        when = (self.a.person, self.m.month, self.ty)
        salary = sv.krankengeld_month(
            self.last_salary / d, opts, *when, church=self.church, employed=True
        )
        own = sv.krankengeld_month(profit, opts, *when, church=self.church, employed=False)
        for name in ("gross", "rv", "alv", "pv"):
            paid = np.where(employed, getattr(salary, name), getattr(own, name)) * d
            setattr(sick, name, np.where(employed | business, paid, getattr(sick, name)))
        sick.employed = np.where(last, employed, sick.employed)

    def _pay_kindergeld(self) -> None:
        """The Kindergeld of the children that count this month and whose Kindergeld the person
        receives (§66 EStG): `kindergeld_month` each in euros of the start, free of tax and of the
        GKV."""
        paid = sum(c.kindergeld for c in self.a.person.counting(self.m.month))
        if paid:
            amount = paid * self.ty.kindergeld_month * self.deflator
            self._note(SOURCE, "", KINDERGELD, amount)
            self._receive(amount)

    def _raise_children(self, earned: FloatArray) -> None:
        """The child-raising years of the children with `erziehung` (§56 SGB VI). In each of the
        `kez_months` after the month of birth `kez_points_month` on top of the points `earned` in
        the month, up to the Höchstwert, the BBG over the Durchschnittsentgelt (§70 Abs. 2): a
        month of compulsory insurance (§3 S. 1 Nr. 1), as the Altersvorsorgedepot asks. A month
        with such a child under `beruecksichtigung_age` counts as insured (§57, §51 Abs. 3, 3a)."""
        ty, month = self.ty, self.m.month
        raised = [c for c in self.a.person.children_born if c.erziehung]
        cap = ty.sv_bbg_month / ty.durchschnittsentgelt
        for child in raised:
            if 0 < months_between(child.born, month) <= ty.kez_months:
                added = np.minimum(ty.kez_points_month, np.maximum(cap - earned, 0.0))
                self.pension.points += added
                earned = earned + added
                self.acc.compulsory = np.maximum(self.acc.compulsory, 1.0)
                self.pension.compulsory_now = True  # Pflichtbeiträge (§55 Abs. 1 S. 2 SGB VI)
        if any(
            months_between(c.born, month) >= 0
            and months_of_age(c.born, month) < 12 * ty.beruecksichtigung_age
            for c in raised
        ):
            self.pension.counts_now = True

    def _pay_streams(self) -> MonthPay:
        """The streams that pay this month: the plain ones into the cash, the gross of the
        salaries and of the pensions added up for `_pay_salaries`. The pension stream of an
        EM-Rente (`_grv`) pays whatever its phases say, a BU policy its claims after its end."""
        d = self.deflator
        pay = MonthPay.new(self.paths)
        self._claim_em()
        grv = self._grv()
        for s in self.streams:
            if self._flexible(s):  # `_pay_flexible`, after what the month pays
                continue
            self._accrue(s)
            if s.spec.kind == StreamKind.BU:
                self._pay_bu(s)
                continue
            if s.spec.kind in (StreamKind.SAVINGS, StreamKind.SELF_EMPLOYED) or not (
                self._pays(s) or (s is grv and self.pension.em.any())
            ):
                continue
            match s.spec.kind:
                case StreamKind.SALARY:
                    gross_real = self._salary_nominal(s) / d
                    pay.salary_real += gross_real
                    self._note(SOURCE, SALARY, s.spec.name, gross_real * d)
                    if s.spec.every == 1:
                        pay.recurring_real += gross_real
                        pay.salaries_real[s] = gross_real
                case StreamKind.PENSION:
                    pay.rente += self._pension_paid(s, grv)
                case _:
                    self._stream_flow(s)
        self._let_income()
        return pay

    def _pay_salaries(self, pay: MonthPay) -> tuple[FloatArray, FloatArray]:
        """The salaries and the pensions of the month into the cash, net: the salary conversions,
        the KV and PV of the pensions, the PKV subsidies, the SV and the withholding. Returns the
        real KV base of the salaries and the nominal deductible PKV premium."""
        d = self.deflator
        converted_real, tax_free, sv_free = self._convert(pay.salaries_real, pay.recurring_real)
        # the ALG1 reference and the base of the Krankengeld: the contributory salary (§151 SGB III,
        # §47 Abs. 2 SGB V) of the last month that paid one on the path
        self.last_salary = np.where(
            pay.recurring_real > 0, (pay.recurring_real - sv_free) * d, self.last_salary
        )
        premium, pflege = self._premium("kv", "pv"), self._premium("pv")
        pension = self._pay_pension(pay.rente, premium - pflege)
        bases = self._sv_bases(pay.salary_real - sv_free, pay.recurring_real - sv_free)
        subsidy, deductible = self._health_support(premium, pflege, pension.pkv_subsidy, bases[1])
        net_real = self._pay_salary(
            pay.salary_real, pay.recurring_real, (tax_free, sv_free), bases, deductible / d
        )
        self._receive(subsidy + pay.salary_real * d, (pay.salary_real - net_real) * d)
        self._spend(-converted_real * d)
        self._note(SOURCE, "", PKV_SUBSIDY, subsidy)
        self.acc.health_deductible += deductible / d
        return bases[1], deductible

    def _record_earned(self) -> None:
        """The taxable income of the year so far, by which the ledger spreads the settlement."""
        if self.ledger is not None:
            acc = self.acc
            taxable = acc.salary_gross + acc.pension_gross + acc.basisrente + acc.other_taxable
            self.earned[self.m.i] = float((taxable + acc.lohnersatz)[0])

    def _let_income(self) -> None:
        """The net rent of the month, real, joins the other income (§21 EStG, `_rent_net`)."""
        rent = self._rent_net() / self.deflator
        self.acc.other_taxable += rent
        self.acc.rent += rent

    def _costs(self) -> None:
        """Care and property upkeep of the month out of the cash."""
        costs = self._care_cost()
        self._note(SPENDING, CARE, CARE, -costs)
        for prop in self.properties.values():
            upkeep = prop.held * prop.spec.upkeep / 12
            costs = costs - upkeep
            self._note(SPENDING, UPKEEP, prop.spec.label, upkeep)
        self._spend(costs)

    def _health_support(
        self,
        premium: FloatArray,
        pflege: FloatArray,
        pension_subsidy: FloatArray,
        kv_base_real: FloatArray,
    ) -> tuple[FloatArray, FloatArray]:
        """Nominal PKV subsidy and deductible premium in a month of the PKV. The Agentur pays
        for the share of the month that ALG1 pays (§174 SGB III: none in a Sperrzeit), else the
        employer on the contributory salary `kv_base_real`: in start-year euros, as the constants
        of `sv`."""
        if not self.pkv:
            return np.zeros(self.paths), np.zeros(self.paths)
        d, share = self.deflator, self.alg1.share
        subsidy = d * (
            share * sv.agentur_pkv_subsidy(premium / d, pflege / d, self.ty)
            if share
            else sv.employer_pkv_subsidy(premium / d, pflege / d, kv_base_real, self.ty)
        )
        return subsidy, tax.health_deductible(self._basis(), subsidy + pension_subsidy)

    def _pay_pension(self, rente: FloatArray, kv_premium: FloatArray) -> sv.PensionMonth:
        """The pensions into the cash with the KVdR, or the §106 SGB VI subsidy to the KV premium,
        once on the sum of the pensions: its cap of half the premium holds per person."""
        d = self.deflator
        net = sv.pension_net_month(
            rente, self.a.tax, self.a.person, self.m.month, self.ty, premium_month=kv_premium
        )
        self.acc.pension_gross += rente / d
        self.acc.health_deductible += (net.kvdr + net.pv) / d
        self._note(SOURCE, "", PKV_SUBSIDY, net.pkv_subsidy)
        self._note(TAX, "", KV, net.kvdr)
        self._note(TAX, "", PV, net.pv)
        self._receive(net.gross + net.pkv_subsidy, net.kvdr + net.pv)
        return net

    def _stream_flow(self, s: StreamState) -> None:
        """One stream other than a salary, a pension or a BU policy into the cash this month, with
        its tax bookkeeping."""
        d = self.deflator
        match s.spec.kind:
            case StreamKind.RV_VOLUNTARY:
                amount = self._nominal(s)
                self.acc.rv_paid += -amount / d
                self.pension.points += sv.voluntary_points(-amount / d, self.ty)
                self.pension.counts_now = True
                self._note(SPENDING, s.spec.cat, s.spec.name, -amount)
                self._spend(amount)
            case StreamKind.OTHER_INCOME:
                amount = self._nominal(s)
                if s.spec.taxable and s.spec.property is None:  # a rent: `_rent_net`
                    self.acc.other_taxable += amount / d
                self._note(SOURCE, "", s.spec.name, amount)
                self._receive(amount)
                if s.spec.repays is not None:  # a loan is one: the least that a path pays
                    loan = self._loan_by_id(s.spec.repays)
                    paid = min(float(amount.min()), -loan.balance)
                    loan.balance += paid
                    self._note(SPENDING, LOAN_PRINCIPAL, loan.spec.label, paid)
                    self._spend(-paid)
            case StreamKind.ALG1:
                self._pay_alg1(s)
            case _:
                expense = self._nominal(s)
                self._note(SPENDING, s.spec.cat, s.spec.name, -expense)
                self._spend(expense)
                self._deduct(s.spec, -expense / d)

    def _pay_bu(self, s: StreamState) -> None:
        """A BU policy while under its `until_age`: the premium while it is in force (its dates,
        the mask of a sale) and the person can work, waived from the month after the onset
        (`Core.onset`), which starts the benefit (the GDV Musterbedingungen: from the end of the
        month of the onset; the Karenzzeit of a tariff is left out). An onset while in force is a
        claim (`StreamState.claim`): its benefit runs to `until_age`, whatever ends the policy
        later. The benefit is taxed at its Ertragsanteil by the Laufzeit from its start to the
        end of the contract (`tax.ertragsanteil`), and a voluntary member of the GKV pays on it
        (`bu_paid`)."""
        spec, i = s.spec, self.m.i
        if self._age(i) >= spec.until_age:
            return
        d, level = self.deflator, self._level(spec.index)
        disabled = (self.onset >= 0) & (i > self.onset)
        if self._pays(s):
            s.claim |= (self.onset == i) & (s.mask > 0)
            premium = spec.premium * self._index(s) * ~disabled
            self._note(SPENDING, spec.cat, spec.name, -premium)
            self._spend(premium)
        paid = s.claim & disabled  # an onset that the old-age claim drops pays nothing
        if not paid.any():
            return
        benefit = s.amount * level * paid
        started = self._age(0) + (self.onset + 1) / 12
        self.acc.other_taxable += benefit / d * tax.ertragsanteil(spec.until_age - started, self.ty)
        self.bu_paid += benefit
        self._note(SOURCE, "", f"{spec.name}: {BENEFIT}", benefit)
        self._receive(benefit)

    def _pay_flexible(self) -> None:
        """VPW (`spending.vpw`): the flexible streams of a month without pay (`earns`, set for
        this month) spend `F`, a twelfth of the budget of the year plus what the month netted in
        the cash since the returns (`cash_mark`; without the lump sums of `MonthFlows.oneoff`,
        which go to the wealth) less a twelfth of the bill of the last December, at least the
        floor. Each active one pays monthly its run rate (its phase factor, `scale`, age curve
        and index) times `F` over their sum, whatever its `every`; none active spends nothing. The
        budget is the rate of the age times the liquid wealth at the start of the month, taken in
        the first month without pay of each calendar year and after `REARM` months of pay in a
        row. A month with pay pays the plan. Counts the months at the floor and above the plan."""
        rule = self.a.spending
        if rule is None or (vpw := rule.vpw) is None:
            return
        free, year = ~self.earns, self.m.month.year
        new = free & (np.isnan(self.budget) | (self.budget_year < year) | (self.paying >= REARM))
        self.paying = np.where(free, 0, self.paying + 1)
        rate = vpw.rate_at(self._age(self._january))
        self.budget = np.where(new, rate * self.liquid_prev, self.budget)
        self.budget_year = np.where(new, year, self.budget_year)
        flexible = [
            s for s in self.streams if self._flexible(s) and s.active(self.m.month, self.m.phase)
        ]
        planned = sum((-self._nominal(s) / s.spec.every for s in flexible), np.zeros(self.paths))
        net = self.cash - self.cash_mark - self.flows.oneoff  # below zero in a usual month
        wanted = (self.budget - self.settled) / 12 + net
        floor = vpw.floor * self.deflator
        spent = np.maximum(wanted, floor)
        share = np.divide(spent, planned, out=np.zeros(self.paths), where=free & (planned > 0))
        for s in flexible:
            if not free.any():  # a ledger has one path: a month with pay spreads its plan
                self._accrue(s)
            plan = -self._nominal(s) if self._pays(s) else np.zeros(self.paths)
            paid = np.where(free, -self._nominal(s) / s.spec.every * share, plan)
            self._note(SPENDING, s.spec.cat, s.spec.name, paid)
            self._spend(-paid)
            self._deduct(s.spec, paid / self.deflator)
        spending = free & (planned > 0)
        self.months_cut += spending & (wanted < floor)
        self.months_raised += spending & (wanted >= floor) & (spent > planned)

    def _deduct(self, spec: Stream, paid: FloatArray) -> None:
        """What an expense with `deduct` paid, real, its share that counts: childcare only in a
        month with a child under `childcare_age` (§10 Abs. 1 Nr. 5 EStG)."""
        kind = spec.deduct
        if kind is None or (
            kind == Deduction.CHILDCARE
            and not self.a.person.children_under(self.ty.childcare_age, self.m.month)
        ):
            return
        acc = self.acc.deduct
        acc[kind] = acc.get(kind, 0.0) + paid * self._deductible_share(spec)

    def _policy_flows(self) -> FloatArray:
        """The annuities of the pension policies into the cash; in their phases the employer's
        contributions accrue, no cash, and the premium of a Basisrente leaves the cash, an
        Altersvorsorgeaufwand (§10 Abs. 1 Nr. 2 b EStG). A company annuity is taxable in full, a
        Basisrente's at its share (`PolicyState.taxable`). Returns the nominal premiums."""
        premium = np.zeros(self.paths)
        d = self.deflator
        for pol in self.policies:
            spec = pol.spec
            if not pol.done and self.m.month >= spec.matures:
                self._pay_out(pol)
            if pol.annuity is not None:
                self._receive(pol.annuity)
                self._note(SOURCE, "", spec.label, pol.annuity)
                if spec.basisrente:
                    self.acc.basisrente += pol.annuity * pol.taxable / d
                else:
                    self.acc.other_taxable += pol.annuity / d
                drawn = np.minimum(pol.annuity, pol.value)  # beyond the capital it is new wealth
                pol.value = pol.value - drawn
                self._note(DRAW, spec.kind, spec.label, -drawn)
            elif not pol.done and self.m.phase in spec.phases:
                employer = spec.contribution * self.working  # it ends with the salary
                pol.value += employer + spec.premium
                pol.paid += employer + spec.premium
                self._note(NONCASH, CONTRIBUTION, f"{spec.label}: {EMPLOYER}", employer)
                self._note_move(SAVINGS_PLAN, f"{spec.label}: {OWN_PREMIUM}", spec.premium)
                premium += spec.premium
        self.cash -= premium
        self.acc.rv_paid += premium / d
        return premium

    def _pay_out(self, pol: PolicyState) -> None:
        """Convert the policy at maturity: guarantee floor, then lump sum or annuity."""
        spec = pol.spec
        capital = np.maximum(pol.value, spec.guarantee * pol.paid)
        self._note(NONCASH, ONEOFF_CONTRIBUTION, f"{spec.label}: {GUARANTEE}", capital - pol.value)
        pol.value = capital if spec.payout == "annuity" else np.zeros(self.paths)
        pol.done = True
        if not capital.any():
            return
        name = spec.label
        if spec.payout == "annuity":
            pol.annuity = capital * spec.annuity_per_10k / 10_000
            if spec.basisrente:  # before 2023 the share of 2023, a gap
                start = max(spec.matures.year, self.ty.pension_share_step_since)
                pol.taxable = tax.pension_share(start, self.ty)
            self._mark("bav", name, amount=float(np.median(pol.annuity)), form="monthly")
        else:
            self._mark("bav", name, amount=float(np.median(capital)))
            self._note(MOVED, PAYOUT, name, -capital)
            # a Versorgungsbezug for `versorgung_months` from the next (§229 Abs. 1 S. 3 SGB V)
            pol.tail, pol.tail_from = capital / self.ty.versorgung_months, self.m.i + 1
            if spec.fuenftel:
                self.flows.oneoff += self._severance(capital, name)
            else:
                self._receive(capital)
                self.flows.oneoff += capital
                self._note(ONEOFF_IN, PAYOUT, name, capital)
                self.acc.other_taxable += capital / self.deflator

    def _av_flows(self) -> FloatArray:
        """The payout of the Altersvorsorgedepots into the cash, at once and by the Auszahlplan.
        It starts with the pension, or at the Regelaltersgrenze without one: `lump_sum` of the
        value, then an Auszahlplan. Returns the nominal Auszahlplan of the month."""
        monthly = np.zeros(self.paths)
        for av in self.av:
            if av.months_left is None:
                if self.pension.claimed is None and self._age(self.m.i) < self.ty.regelaltersgrenze:
                    continue
                av.months_left = max(round(12 * (av.spec.until_age - self._age(self.m.i))), 1)
                lump = av.value * av.spec.lump_sum
                self._av_paid(av, lump, at_once=True)
                self._mark("av", av.spec.label, amount=float(np.median(lump)), form="once")
            if av.months_left:
                rate = av.value / av.months_left
                self._av_paid(av, rate, at_once=False)
                monthly += rate
                av.months_left -= 1
        return monthly

    def _av_paid(self, av: AvState, nominal: FloatArray, *, at_once: bool) -> None:
        """A payment out of the depot into the cash, fully taxable as other income (§22 Nr. 5
        EStG), without the Fünftelregelung."""
        av.value = av.value - nominal
        self.acc.other_taxable += nominal / self.deflator
        name = av.spec.label
        if at_once:
            self._note(ONEOFF_IN, PAYOUT, name, nominal)
            self._note(MOVED, PAYOUT, name, -nominal)
            self.acc.kv_oneoff += nominal / self.deflator
            self.flows.oneoff += nominal
        else:
            self._note(SOURCE, "", name, nominal)
            self._note(DRAW, av.spec.kind, name, -nominal)
        self._receive(nominal)

    def _contribute_av(self) -> None:
        """December: the contributions of a year with compulsory insurance, the Zulage on top.
        The person earns one Zulage and one room of §10a whatever the number of depots (§84 S. 1
        EStG): both on the sum of the contributions, the Zulage split by them. A child whose
        Kindergeld the person receives in a month of the year earns the Kinderzulage (§85)."""
        paying = [av for av in self.av if av.months_left is None and self.m.month >= av.spec.start]
        if not paying:
            return
        d, acc = self.deflator, self.acc
        paid = [av.spec.contribution * acc.compulsory for av in paying]
        total = sum(paid, np.zeros(self.paths))
        zulage = tax.av_zulage(total, self.a.person.kindergeld_in(self.m.month.year), self.ty)
        acc.av_deduction += tax.av_deduction(total, zulage, self.ty)
        acc.av_zulage += zulage
        for av, own in zip(paying, paid, strict=True):
            part = zulage * np.divide(own, total, out=np.zeros(self.paths), where=total > 0)
            self.cash -= own * d
            av.value = av.value + (own + part) * d
            item = f"{av.spec.label}: {OWN_PREMIUM}"
            self._note_move(SAVINGS_PLAN, item, own * d)
            self._spread((MOVE_OUT, SAVINGS_PLAN, item), own * d, 12)
            self._note(NONCASH, CONTRIBUTION, f"{av.spec.label}: {ZULAGE}", part * d)

    def _claim_pension(self) -> bool:
        """Fix the old-age claim on the first eligible month, the same on every path without an
        EM-Rente. Defers when the years fall short. An onset in this month or later is dropped:
        after an old-age pension no EM-Rente (§34 Abs. 2 SGB VI)."""
        p = self.pension
        month = self.m.month
        if p.claimed is not None:
            return True
        if p.wanted is None:
            p.wanted = month
        years = p.insured_months / 12
        factor = sv.pension_claim(self._age(self.m.i), years, self.ty)
        if factor is None:
            return False
        p.claimed, p.regular = month, factor
        p.start_year = np.where(p.em, p.start_year, month.year)
        self.onset = np.where(self.onset >= self.m.i, -1, self.onset)
        if not p.em.all():
            since = None if month == p.wanted else p.wanted
            self._mark("pension", amount=factor, years=years, since=since)
        return True

    def _claim_em(self) -> None:
        """The EM-Rente from the `em_start_months`-th month after the onset (§101 Abs. 1 SGB VI) of
        a path that `_disable` let claim one, before an old-age claim: its Zugangsfaktor by the
        age now (`sv.em_factor`), its year for the tax. A month with it opens the
        Altersvorsorgedepot (§10a Abs. 1 S. 4 EStG); its payout waits for the old-age claim."""
        p = self.pension
        due = (self.onset >= 0) & (self.onset + self.ty.em_start_months == self.m.i) & self.em_ok
        if p.claimed is not None or not due.any():
            return
        p.em |= due
        p.em_factor = np.where(due, sv.em_factor(self._age(self.m.i), self.ty), p.em_factor)
        p.start_year = np.where(due, self.m.month.year, p.start_year)

    def _grv(self) -> StreamState | None:
        """The stream of the statutory pension, which an EM-Rente pays on: the first pension
        from points (one with a `gross`, a Versorgungswerk, pays none)."""
        return next(
            (
                s
                for s in self.streams
                if s.spec.kind == StreamKind.PENSION
                and s.spec.points is not None
                and s.spec.point_value is not None
            ),
            None,
        )

    def _pension_paid(self, s: StreamState, grv: StreamState | None) -> FloatArray:
        """The nominal pension of `s` this month: after the old-age claim in its phases, and on
        `grv` the EM-Rente of a path whatever the phases say, also after the Regelaltersgrenze,
        when the Altersrente follows with its points and factor (§88 Abs. 1 S. 2, §77 Abs. 3 S. 1
        SGB VI). The ledger books it under the name of the stream in the phases of the stream, as
        `EM_RENTE` in the others: the Cashflows sheet shows the stream in its phases, what no
        stream pays from the run."""
        p = self.pension
        phased = self._pays(s)
        regular = phased and self._claim_pension()  # before the gross: the claim sets its factor
        em = p.em if s is grv else np.zeros(self.paths, dtype=bool)
        paid = self._pension_gross(s, em) * s.mask * (em | regular)
        self.acc.compulsory = np.maximum(self.acc.compulsory, em)
        self._note(SOURCE, "", s.spec.name if phased else EM_RENTE, paid)
        return paid

    def _salary_nominal(self, s: StreamState) -> FloatArray:
        """Nominal gross of one salary payment this month: its factor, the `scale` and growth of
        the phase (`_earned`, once on a share `of` another) and its index, none after the onset
        of a disability (`working`)."""
        return self._salary_gross(s) * self._earned(s) * self._index(s) * self.working

    def _salary_gross(self, s: StreamState) -> FloatArray:
        """Nominal gross for one payment before the stream's own factor and index.

        A derived stream (`of`) pays `share` of the base stream's gross for `every` months,
        so its own index acts as a payout ratio."""
        spec = s.spec
        if spec.of is None or spec.share is None:
            return np.full(self.paths, s.gross * spec.part)
        named = [b for b in self.streams if b.spec.name == spec.of]
        # a raise is a successor row with the same name: follow the row that pays now, else the
        # one that started last, none before the first
        started = [b for b in named if b.spec.start is None or b.spec.start <= self.m.month]
        base = next((b for b in named if b.active(self.m.month, self.m.phase)), None) or max(
            started, key=lambda b: b.spec.start or date.min, default=None
        )
        if base is None:
            return np.zeros(self.paths)
        gross = base.gross * base.spec.part * base.factor(self.m.phase) * self._index(base)
        return spec.share * spec.every * gross

    def _sv_bases(
        self, gross_real: FloatArray, regular_real: FloatArray
    ) -> tuple[FloatArray, FloatArray]:
        """Real contributory bases of RV and of KV of the month's salary, counted into the year."""
        acc = self.acc
        acc.sv_months += gross_real > 0
        bases = sv.sv_bases(
            regular_real,
            gross_real - regular_real,
            acc.sv_months,
            (acc.rv_used, acc.kv_used),
            self.ty,
        )
        acc.rv_used += bases[0]
        acc.kv_used += bases[1]
        return bases

    def _convert(
        self, salaries: dict[StreamState, FloatArray], regular_real: FloatArray
    ) -> tuple[FloatArray, FloatArray, FloatArray]:
        """The salary conversions of the bAV policies in their phases (`sv.conversions`, in file
        order after the employer's contributions of the month), into each policy with its
        subsidy, each at most what its salary leaves after the conversions before it. Returns,
        real: what they take from the monthly `salaries` and off their regular gross of the
        income tax and of the SV."""
        d = self.deflator
        paying = [
            p
            for p in self.policies
            if not p.done and self.m.month < p.spec.matures and self.m.phase in p.spec.phases
        ]
        left = dict(salaries)  # of each salary what the conversions before leave
        taken: list[tuple[PolicyState, FloatArray]] = []
        for pol in paying:
            if pol.spec.conversion and (s := self._source(pol.spec, salaries)) is not None:
                taken.append((pol, np.minimum(pol.spec.conversion / d, left[s])))
                left[s] = left[s] - taken[-1][1]
        convs = sv.conversions(
            [(amount, pol.spec.subsidy) for pol, amount in taken],
            regular_real,
            sum(p.spec.contribution for p in paying) / d,
            self.a.tax,
            self.ty,
            month=self.m.month,
        )
        zero = np.zeros(self.paths)
        for (pol, amount), conv in zip(taken, convs, strict=True):
            label = pol.spec.label
            pol.value = pol.value + (amount + conv.subsidy) * d
            pol.paid = pol.paid + (amount + conv.subsidy) * d
            self._note(SPENDING, CONVERSION, label, amount * d)
            self._note(MOVED, CONVERSION, label, amount * d)
            self._note(NONCASH, CONTRIBUTION, f"{label}: {SUBSIDY}", conv.subsidy * d)
        return (
            sum((amount for _, amount in taken), zero),
            sum((c.tax_free for c in convs), zero),
            sum((c.sv_free for c in convs), zero),
        )

    @staticmethod
    def _source(spec: PensionPolicy, salaries: dict[StreamState, FloatArray]) -> StreamState | None:
        """The salary of a conversion among the monthly `salaries` that pay: the one that
        `salary` names, else the first without `of`."""
        return next(
            (
                s
                for s in salaries
                if (s.spec.name == spec.salary if spec.salary else s.spec.of is None)
            ),
            None,
        )

    def _pay_salary(
        self,
        gross_real: FloatArray,
        regular_real: FloatArray,
        free: tuple[FloatArray, FloatArray],
        bases: tuple[FloatArray, FloatArray],
        health_real: FloatArray,
    ) -> FloatArray:
        """SV on the contributory `bases` of the month's total salary, withholding with the part
        beyond the regular monthly salary as a sonstiger Bezug, both less what a conversion takes
        off the regular salary (`free`: of the income tax, of the SV); returns the net before
        the conversion in real euros."""
        if not gross_real.any():
            return np.zeros(self.paths)
        tax_free, sv_free = free
        paid = sv.sv_on(bases, self.a.tax, self.a.person, self.m.month, self.ty)
        regular = sv.sv_employee(
            regular_real - sv_free, self.a.tax, self.a.person, self.m.month, self.ty
        )
        withheld = self._withhold(
            lambda church: tax.withholding_with_bonus(
                regular_real - tax_free,
                gross_real - regular_real,
                (paid, regular),
                health_real,
                self.ty,
                church=church,
            )
        )
        self.acc.salary_gross += gross_real - tax_free
        self.acc.compulsory = np.maximum(self.acc.compulsory, gross_real > 0)
        self.acc.rv_paid += paid.rv
        self.acc.rv_employer += paid.rv
        self.acc.health_deductible += paid.kv + paid.pv
        for item, part in ((RV, paid.rv), (AV, paid.alv), (KV, paid.kv), (PV, paid.pv)):
            self._note(TAX, "", item, part * self.deflator)
        self._note(TAX, "", INCOME_TAX, withheld * self.deflator)
        self.pension.points += bases[0] / self.ty.durchschnittsentgelt
        self.pension.counts_now = self.pension.compulsory_now = True
        return gross_real - paid.total - withheld

    def _pension_gross(self, s: StreamState, em: BoolArray) -> FloatArray:
        """Nominal monthly pension: the fixed gross, or the points reached and those earned in the
        run at the point value, in start-year euros, times the factor of the old-age claim; on the
        paths `em` the points and the factor of the EM-Rente in every phase. It follows its index
        like any stream and grows by `pension_growth` on top, stepped each January."""
        spec, p = s.spec, self.pension
        if spec.points is not None and spec.point_value is not None:
            points = np.where(em, p.em_points, spec.points + p.points)
            base = points * spec.point_value
        else:
            base = np.full(self.paths, s.gross)
        claim = np.where(em, p.em_factor, p.regular * s.factor(self.m.phase))
        growth = (1 + self.a.pension_growth) ** (self.m.month.year - self.start.year)
        return base * claim * growth * self._level(spec.index)

    def _shares(self) -> FloatArray:
        """Per path the taxable share of the first pension year (`tax.pension_share`; before 2023
        that of 2023, a gap), 0 before the claim: one call per year in which paths start."""
        years = self.pension.start_year
        share = np.zeros(self.paths)
        for year in np.unique(years[years > 0]).tolist():
            share[years == year] = tax.pension_share(
                max(year, self.ty.pension_share_step_since), self.ty
            )
        return share

    def _pension_taxable(self, gross_real: FloatArray) -> FloatArray:
        """The taxable part of the pensions of a year (§22 Nr. 1 S. 3 EStG): the share of the
        first pension year of each path, after the Rentenfreibetrag (`_freeze_rentenfreibetrag`)
        all but it."""
        frozen = self.pension.freibetrag
        return np.where(
            np.isnan(frozen),
            gross_real * self._shares(),
            np.maximum(gross_real - np.nan_to_num(frozen) / self.deflator, 0.0),
        )

    def _freeze_rentenfreibetrag(self) -> None:
        """The tax-free part is fixed in euros at the end of the first full pension year of each
        path, so every later increase is taxed in full."""
        p, month = self.pension, self.m.month
        due = (p.start_year > 0) & np.isnan(p.freibetrag) & (month.year == p.start_year + 1)
        if month.month == 12 and due.any():
            free = self.acc.pension_gross * (1 - self._shares()) * self.deflator
            p.freibetrag = np.where(due, free, p.freibetrag)
