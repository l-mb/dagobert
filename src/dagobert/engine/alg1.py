"""The claim to ALG1 as a balance of days, the same on every path (§§147, 148, 159, 161 SGB III):
the months of ALG1 use it, a Sperrzeit rests and shortens it, a course uses half, a later
stretch within four years pays the rest. The month of the claim comes before the streams, so
every step after them reads it (`Alg1State`)."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np

from dagobert import sv
from dagobert.engine.profit import Profit
from dagobert.engine.state import StreamState
from dagobert.model.streams import StreamKind
from dagobert.result import SOURCE


class Alg1(Profit):
    def _claim_alg1(self) -> None:
        """The claim in this month, before the streams. It arises in the first month in which an
        ALG1 row pays by its dates and phases (`_open_alg1`). A stretch, the months in a row with
        such a row, pays while days are left; a later stretch only when it begins within
        `alg1_claim_months` of that month (§161 Abs. 2: the claim cannot be claimed again; a
        stretch runs on past it, BA FW 161.2). The month books its ALG1 once, under the first row
        without `training` (`Alg1State.row`)."""
        c = self.alg1
        rows = [s for s in self.streams if s.spec.kind == StreamKind.ALG1 and self._pays(s)]
        training = any(s.spec.training for s in rows)
        if not training:
            self._extend_alg1()
        continued = c.row is not None
        c.row = min(rows, key=lambda s: s.spec.training, default=None)
        c.share, c.status = 0.0, False
        if c.row is None:
            return
        if c.start is None:
            self._open_alg1()
        elif not continued:
            c.fresh = self.m.i - c.start < self.ty.alg1_claim_months
            if not c.fresh:
                self._end_alg1("alg1 expired" if c.days > 0 else "alg1 used")
        if c.fresh:
            self._use_alg1(rows, training=training)

    def _open_alg1(self) -> None:
        """The claim arises: its days by the age in this month (§147 Abs. 1 Nr. 2, Abs. 2), its
        monthly amount on the last salary (`sv.alg1_month`), at 67% with a child that counts now.
        A member of the PKV before `gkv_return_age` stays in it only by the exemption of §8 Abs. 1
        S. 1 Nr. 1a SGB V, which the run assumes and marks: else ALG1, also while a Sperrzeit
        rests it, makes a compulsory member (§5 Abs. 1 Nr. 2), which `tax.gkv_from` models."""
        c, ty, i = self.alg1, self.ty, self.m.i
        age = self._age(i)
        c.start, c.fresh = i, True
        c.days = float(ty.alg1_month_days * sv.alg1_months(int(age), ty))
        child = bool(self.a.person.counting(self.m.month))
        c.monthly = sv.alg1_month(self.last_salary / self.deflator, ty, child=child) * self.deflator
        if self.first_profit is not None:  # no Anwartschaft of its own without §28a SGB III
            self._mark("alg1")
        if self.pkv and age < ty.gkv_return_age:
            self._mark("exemption")

    def _use_alg1(self, rows: list[StreamState], *, training: bool) -> None:
        """The days of the month. A row with `sperrzeit` that pays for the first time rests the
        claim for `alg1_sperrzeit_days` and takes as many of its days, at least
        `alg1_sperrzeit_share` of those left, rounded down (§148 Abs. 1 Nr. 4; BA FW 148.1.4).
        The rest of the month pays while days are left; a month of a course (`training`) pays in
        full with any days left and takes `alg1_training_rate` of its days, down to
        `alg1_training_floor_days` at the lowest (§148 Abs. 1 Nr. 7, Abs. 2 S. 3; BA FW 148.2)."""
        c, ty = self.alg1, self.ty
        for s in rows:
            if s.spec.sperrzeit and s not in c.rested and c.days > 0:
                c.rested.add(s)
                c.resting += ty.alg1_sperrzeit_days
                cut = max(ty.alg1_sperrzeit_days, math.floor(c.days * ty.alg1_sperrzeit_share))
                c.days = max(c.days - cut, 0.0)
        rest = min(c.resting, ty.alg1_month_days)
        c.resting -= rest
        free = ty.alg1_month_days - rest
        if training and c.days > 0:
            paid = free
            floor = ty.alg1_training_floor_days
            c.days -= min(free * ty.alg1_training_rate, max(c.days - floor, 0.0))
            c.course += paid > 0
        else:
            paid = min(free, c.days)
            c.days -= paid
        c.share = paid / ty.alg1_month_days
        c.status = rest > 0 or paid > 0
        if not c.status:
            self._end_alg1("alg1 used")

    def _extend_alg1(self) -> None:
        """In a month without a course, after one of `alg1_course_months` in a row: a rest below
        `alg1_training_floor_days` rises to it, once for the claim (§148 Abs. 3; BA FW 148.3, also
        when no ALG1 follows at once)."""
        c, ty = self.alg1, self.ty
        floor = ty.alg1_training_floor_days
        if c.course >= ty.alg1_course_months and not c.extended and c.days < floor:
            c.days, c.extended = float(floor), True
        c.course = 0

    def _end_alg1(self, kind: Literal["alg1 used", "alg1 expired"]) -> None:
        """The marker of the first month in which an ALG1 row pays nothing: the claim is used up,
        or four years have passed since it arose."""
        if not self.alg1.ended:
            self.alg1.ended = True
            self._mark(kind)

    def _on_alg1(self) -> bool:
        """A month of ALG1: it pays or a Sperrzeit rests it (the KVdA, §5 Abs. 1 Nr. 2 SGB V)."""
        return self.alg1.status

    def _alg1_holds(self, i: int) -> bool:
        """An ALG1 row in the month `i`, the next one, would pay or rest: before the claim arose,
        else with days or a Sperrzeit left, in a stretch that runs on from this month or begins
        within the four years of §161 Abs. 2 SGB III."""
        c = self.alg1
        if c.start is None:
            return True
        fresh = c.fresh if c.row is not None else i - c.start < self.ty.alg1_claim_months
        return fresh and (c.days > 0 or c.resting > 0)

    def _pay_alg1(self, s: StreamState) -> None:
        """The ALG1 of the month into the cash, once, under the row that books it, at the share of
        the month that it pays, none after the onset of a disability (`working`): tax-free under
        the Progressionsvorbehalt, a month of compulsory GRV with points on `alg1_rv_share` of the
        last salary (§166 Abs. 1 Nr. 2 SGB VI). No points in a Sperrzeit."""
        c = self.alg1
        if s is not c.row or c.monthly is None:
            return
        d, working = self.deflator, s.mask * self.working * c.share
        paid = c.monthly * working
        self._note(SOURCE, "", s.spec.name, paid)
        self._receive(paid)
        if not c.share:
            return
        self.acc.lohnersatz += paid / d
        self.acc.compulsory = np.maximum(self.acc.compulsory, paid > 0)
        points = sv.pension_points(self.last_salary / d, self.ty) * working
        self.pension.points += self.ty.alg1_rv_share * points
        self.pension.counts_now = self.pension.compulsory_now = True
