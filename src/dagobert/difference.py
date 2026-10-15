"""Two runs compared path by path: B less A."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np

from dagobert.i18n import _
from dagobert.result import FloatArray, RunResult, age_index

SPREAD = (5, 50, 95)  # percentiles over the paths


@dataclass(frozen=True)
class Difference:
    """B less A on each path, reduced over the paths per month. Runs with the same model, paths
    and seeds draw the same numbers on a path (`returns.generator`), so the difference on a
    path is the effect of the plan and not of luck."""

    a: str
    b: str
    unit: str
    months: list[date]
    ages: FloatArray  # (months,)
    total: FloatArray  # (len(SPREAD), months)
    liquid: FloatArray  # (len(SPREAD), months)
    taxes: FloatArray  # (months,) median of the taxes paid from the start up to the month
    # (months,) share of the paths broke by the month in A only, and in B only
    broke_only: tuple[FloatArray, FloatArray]

    @classmethod
    def of(cls, a: RunResult, b: RunResult, *, nominal: bool = False) -> Difference:
        if a.months != b.months or a.paths != b.paths:
            msg = _("{a} and {b} differ in their months or paths").format(a=a.label, b=b.label)
            raise ValueError(msg)

        def diff(get: Callable[[RunResult], FloatArray]) -> FloatArray:
            return get(b) - get(a)

        def spread(get: Callable[[RunResult], FloatArray]) -> FloatArray:
            return np.asarray(np.percentile(diff(get), SPREAD, axis=0))

        broke_a, broke_b = a.broke_by, b.broke_by
        return cls(
            a.label,
            b.label,
            a.unit(nominal=nominal),
            a.months,
            a.ages,
            spread(lambda r: r.euros(r.total, nominal=nominal)),
            spread(lambda r: r.euros(r.liquid, nominal=nominal)),
            np.median(diff(lambda r: r.taxes_paid(nominal=nominal).cumsum(axis=1)), axis=0),
            ((broke_a & ~broke_b).mean(axis=0), (broke_b & ~broke_a).mean(axis=0)),
        )

    def index(self, age: float) -> int:
        """The month of `age`, the last month beyond the run."""
        return age_index(self.ages, age)
