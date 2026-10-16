"""Self-employment: the profit of the `self_employed` streams, the GRV of a month in which it is
the main work, the reserve for the Vorauszahlungen and the trade businesses of the year."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from dagobert import sv, tax
from dagobert.engine.core import Core
from dagobert.engine.state import StreamState, Trade
from dagobert.model.streams import StreamKind
from dagobert.result import INCOME_TAX, PROFIT, RV, SOURCE, TAX, FloatArray


class Profit(Core):
    def _profit_nominal(self, s: StreamState) -> FloatArray:
        """Nominal profit of one payment this month: its factor, the `scale.salary` and the
        growth of the phase (`_earned`) and its index, none after the onset of a disability
        (`working`)."""
        return s.amount * self._earned(s) * self._index(s) * self.working

    def _running(self) -> list[StreamState]:
        """The self-employed streams of the month: active by dates and phases at a factor other
        than 0. A profit of 0 or below runs: the business goes on."""
        return [
            s
            for s in self.streams
            if s.spec.kind == StreamKind.SELF_EMPLOYED
            and s.active(self.m.month, self.m.phase)
            and s.earned_scale(self.m.phase, self.a)
        ]

    def _business(self) -> tuple[NDArray[np.bool_], FloatArray]:
        """Per path whether a business runs this month, and the real profit of the running
        streams at their run rate (a stream paid every n months counts 1/n in each month). None
        runs after the onset of a disability (`working`)."""
        running, zero = self._running(), np.zeros(self.paths)
        on = (sum((s.mask for s in running), zero) > 0) & (self.working > 0)
        rate = sum((self._profit_nominal(s) / s.spec.every for s in running), zero)
        return on, rate / self.deflator

    def _pay_profit(
        self, salary_real: FloatArray, deductions_real: FloatArray, *, on_alg1: bool
    ) -> None:
        """The self-employed streams of this month into the cash, net. The profit that pays is
        other income of the year, a trade business's also its Gewerbeertrag. As the main work the
        business pays the GRV of `tax.self_employed.rv` on its run rate. The reserve for the
        Vorauszahlungen takes off the `deductions_real` of the month: the KV and PV of a GKV
        member or the deductible PKV premium, when no salary takes them."""
        running = self._running()
        if not running:
            return
        if self.first_profit is None:
            self.first_profit = self.m.month
        d, zero = self.deflator, np.zeros(self.paths)
        regular, lump = zero.copy(), zero.copy()
        for s in (s for s in running if self._pays(s)):
            real = self._profit_nominal(s) / d
            if s.spec.every == 1:
                regular += real
            else:
                lump += real
            self._note(SOURCE, PROFIT, s.spec.name, real * d)
            if s.spec.hebesatz is not None:
                trade = self.acc.trade.get(s.spec.name)
                so_far = zero if trade is None else trade.profit
                self.acc.trade[s.spec.name] = Trade(s.spec.hebesatz, so_far + real)
        on, rate = self._business()
        main = on & (salary_real == 0) & (not on_alg1)
        founded = self.a.tax.self_employed.founded or self.first_profit
        rv = sv.rv_self_employed(rate, self.a.tax, self.m.month, self.ty, founded=founded) * main
        reserve = self._withhold(
            lambda church: tax.profit_reserve(
                regular, lump, rv + deductions_real, self.ty, church=church
            )
        )
        acc = self.acc
        acc.other_taxable += regular + lump
        acc.compulsory = np.maximum(acc.compulsory, on)  # Altersvorsorgedepot from 2027 (§10a)
        acc.rv_paid += rv
        self.pension.points += sv.voluntary_points(rv, self.ty)
        if rv.any():  # Pflichtbeiträge (§2, §4 Abs. 2, §55 Abs. 1 SGB VI)
            self.pension.counts_now = self.pension.compulsory_now = True
            self._note(TAX, "", RV, rv * d)
        self._note(TAX, "", INCOME_TAX, reserve * d)
        self._receive((regular + lump) * d, (rv + reserve) * d)
