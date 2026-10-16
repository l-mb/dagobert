"""The statutory health and care insurance (GKV) of a month beyond the salary and the pension: the
Versorgungsbezüge of a Pflichtmitglied, and a freiwilliges Mitglied on all its income."""

from __future__ import annotations

from datetime import date

import numpy as np

from dagobert import sv
from dagobert.engine.alg1 import Alg1
from dagobert.engine.core import pays
from dagobert.model.streams import StreamKind
from dagobert.result import KV, PV, TAX, BoolArray, FloatArray


class Health(Alg1):
    def _versorgung(self) -> tuple[FloatArray, FloatArray]:
        """Nominal payments of the policies this month: the Versorgungsbezüge of the company
        pensions (an annuity, or a lump sum's tail), and the annuities of a Basisrente."""
        company, basis = np.zeros(self.paths), np.zeros(self.paths)
        for pol in self.policies:
            if pol.annuity is not None:
                if pol.spec.basisrente:
                    basis += pol.annuity
                else:
                    company += pol.annuity
            if pol.tail is not None and 0 <= self.m.i - pol.tail_from < self.ty.versorgung_months:
                company += pol.tail
        return company, basis

    def _pay_gkv(
        self,
        salary_real: FloatArray,
        kv_base_real: FloatArray,
        rente: FloatArray,
        av_paid: FloatArray,
        *,
        on_alg1: bool,
        sick: BoolArray,
    ) -> FloatArray:
        """The KV and PV of a GKV member beyond the salary and the pension (`_pay_pension`) out
        of the cash, returned nominal. A salary, ALG1 that pays or a Sperrzeit that rests it
        (`on_alg1`), the Krankengeld of an employee on the paths `sick` (free of KV itself, §224
        Abs. 1 S. 1 SGB V) or a pension with
        `person.kvdr` make the month compulsory: KV and PV on the Versorgungsbezüge, and on the
        profit beside a pension or a Versorgungsbezug (`sv.kv_compulsory`), in the room below the
        KV-BBG that the salary base `kv_base_real` or the pension leave. Any other month is
        voluntary (`sv.kv_voluntary`): the pension, the Versorgungsbezüge and the rest, which is
        the profit at its run rate, the taxable other income, the rent net of its costs, a
        Basisrente, the Auszahlplan `av_paid`, the benefit of a BU policy (`bu_paid`; Katalog: a
        private Risikoversicherung) and `kv_last`; the Krankengeld of a business stays free (§224
        Abs. 1 S. 2). Nothing in a month of the PKV (`Core.pkv`); its December before a switch to
        a voluntary January keeps the base beside `kv_last` for the cap of a harvest (`kv_rest`)."""
        if self.pkv and not (self.m.month.month == 12 and self._voluntary_next()):
            return np.zeros(self.paths)
        d, ty, opts, person, month = self.deflator, self.ty, self.a.tax, self.a.person, self.m.month
        company, basis = (x / d for x in self._versorgung())
        pension = rente / d
        on, profit = self._business()
        # the taxable other income at its run rate and the rent net of its Werbungskosten (BVSzGs
        # §3 Abs. 1b): a loss offsets another stream of its kind, no other kind
        other = np.maximum(self._run_rate(StreamKind.OTHER_INCOME, taxable=True), 0.0)
        other += np.maximum(self._rent_net(), 0.0)
        rest = np.maximum(profit, 0.0) + (other + basis + av_paid + self.bu_paid) / d
        self.kv_rest = pension + company + rest
        if self.pkv:
            return np.zeros(self.paths)
        employed = salary_real > 0
        kvdr = (pension > 0) & person.kvdr & ~employed & (not on_alg1) & ~sick
        room = np.maximum(ty.kv_pv_bbg_month - np.where(employed, kv_base_real, pension), 0.0)
        beside = (pension > 0) | (company > 0)  # §226 Abs. 1 Nr. 4, §232a Abs. 3, §237 Nr. 3
        compulsory = sv.kv_compulsory(
            (company, np.where(beside, profit, 0.0)), opts, person, month, ty, room=room
        )
        voluntary = sv.kv_voluntary(
            (pension, company, rest + self.kv_last),
            opts,
            person,
            month,
            ty,
            krankengeld=on & opts.self_employed.krankengeld,
        )
        free = ~employed & (not on_alg1) & ~kvdr & ~sick
        kv, pv = (np.where(free, v, c) for v, c in zip(voluntary, compulsory, strict=True))
        self.acc.health_deductible += kv + pv
        self._note(TAX, "", KV, kv * d)
        self._note(TAX, "", PV, pv * d)
        self._receive(0.0, (kv + pv) * d)
        return (kv + pv) * d

    def _mark_switch(self) -> None:
        """The marker of a switch from the PKV to the GKV (`tax.gkv_from`) at an age from which
        §6 Abs. 3a SGB V usually keeps a person who was outside the GKV for five years free of
        it: the run switches, the law seldom lets one."""
        if self.m.month == self.a.tax.gkv_from and self._age(self.m.i) >= self.ty.gkv_return_age:
            self._mark("gkv")

    def _kv_last(self) -> FloatArray:
        """In January, the monthly base that the year that ends gives a freiwilliges Mitglied in
        the next. The Kasse takes the capital income of the last proven year over the months in
        which it was earned (BVSzGs §5 Abs. 2 S. 4): the sales and the interest over the months
        of the year in the run, the Vorabpauschale over twelve, less the Werbungskosten of a
        year. A one-off, the net private sales among them, counts a twelfth (§5 Abs. 3)."""
        acc = self.acc
        capital = np.maximum(
            acc.kv_capital / min(self.m.i, 12)
            + (acc.kv_vorab - self.ty.kv_capital_werbungskosten) / 12,
            0.0,
        )
        return capital + (np.maximum(acc.private_sales, 0.0) + acc.kv_oneoff) / 12

    def _kv_room(self) -> FloatArray:
        """In December, the capital income after the Teilfreistellung that the year can still add
        while the base of a voluntary member in the next year, `_kv_last` beside
        the rest of the base of this month (`kv_rest`), stays at the minimum: below 0 none."""
        acc = self.acc
        once = acc.kv_vorab - self.ty.kv_capital_werbungskosten
        once += np.maximum(acc.private_sales, 0.0) + acc.kv_oneoff
        room = self.ty.kv_min_base - self.kv_rest - once / 12
        return min(self.m.i + 1, 12) * np.maximum(room, 0.0) - acc.kv_capital

    def _voluntary_next(self) -> bool:
        """A voluntary member of the GKV in the next January by the inputs, the same on every
        path: in the GKV then (`TaxOptions.pkv_in`), no salary pays by its dates and phases (§5
        Abs. 1 Nr. 1 SGB V), no ALG1 pays or rests (Nr. 2, `_alg1_holds`), no pension that can
        be claimed by then with `person.kvdr` (Nr. 11)."""
        month = date(self.m.month.year + 1, 1, 1)
        if self.a.tax.pkv_in(month):
            return False
        i, phase = self.m.i + 13 - self.m.month.month, self.plan.phase_at(month)
        active = [s for s in self.streams if s.active(month, phase)]
        kinds = {s.spec.kind for s in active}
        salary = any(
            s.spec.kind == StreamKind.SALARY and pays(s.spec, self.a, phase, s.factor_override)
            for s in active
        )
        alg1 = StreamKind.ALG1 in kinds and self._alg1_holds(i)
        p = self.pension
        claim = p.claimed is not None or (
            sv.pension_claim(self._age(i), p.insured_months / 12, self.ty) is not None
        )
        kvdr = StreamKind.PENSION in kinds and self.a.person.kvdr and claim
        return not (salary or alg1 or kvdr)
