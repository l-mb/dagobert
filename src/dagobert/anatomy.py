"""Failure anatomy: what sets the paths broke by `BROKE_AGE` apart from the others. Numbers only:
`report.anatomy` writes the words, so a run in the cache of the app serves every language."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from dagobert.result import BROKE_AGE, BoolArray, FloatArray, RunResult

if TYPE_CHECKING:
    from collections.abc import Mapping

EARLY_YEARS = 10  # the window of the sequence-of-returns risk
GROUPS = 5  # groups of equal size per driver
# the kinds of driver: the equity return over the first years, the return of a class (equity and
# the class of each gold or crypto asset), the inflation, the growth of a named index, the age at
# the start of the first care episode, at the onset of a disability and at an inheritance without
# a month
EARLY, RETURN, INFLATION, INDEX, CARE = "early", "return", "inflation", "index", "care"
INHERITANCE, DISABLED = "inheritance", "disabled"
AGES = (CARE, DISABLED, INHERITANCE)  # drivers that are an age, infinite without the event
Key = tuple[str, str]  # a driver: its kind and the name of its class or index
EQUITY: Key = (RETURN, "equity")
CARE_AGES = (80, 85, BROKE_AGE)  # bin edges of the age at the start of the first care episode
DISABLED_AGES = (50, 60, BROKE_AGE)  # of the age at the onset, which comes before 67


def holding_return(key: Key) -> bool:
    """Whether the driver `key` is the return of the class of a gold or crypto asset."""
    return key[0] == RETURN and key != EQUITY


def _per_year(growth: NDArray[np.floating], months: int) -> NDArray[np.floating]:
    return growth ** (12 / max(months, 1)) - 1


def drivers(
    r: RunResult,
    returns: Mapping[str, FloatArray],
    indices: Mapping[str, FloatArray],
    inherited: Mapping[str, NDArray[np.intp]],
) -> dict[Key, NDArray[np.float32]]:
    """One number per path and random driver: the nominal growth per year of the return classes
    up to `BROKE_AGE` (`returns`, the levels after the return of each month: `equity`, then the
    classes of the gold and crypto assets), of equity also over the first years, of the
    consumer prices and of the named growth `indices` up to `BROKE_AGE`, the age at the start of
    the first care episode, at the onset of a disability and at each inheritance without a month
    (`inherited`: its month index per path by the labels of its givers), infinite without one."""
    end, early = r.age_index(BROKE_AGE), min(12 * EARLY_YEARS, len(r.months))
    n = len(r.months)
    values = {
        (EARLY, "equity"): _per_year(returns["equity"][:, early - 1], early),
        **{(RETURN, name): _per_year(level[:, end], end + 1) for name, level in returns.items()},
        (INFLATION, ""): _per_year(r.cpi[:, end], end),
        **{(INDEX, name): _per_year(level[:, end], end) for name, level in indices.items()},
        (CARE, ""): np.where(r.care.any(axis=1), r.ages[r.care.argmax(axis=1)], np.inf),
        (DISABLED, ""): np.where(r.onset >= 0, r.ages[np.maximum(r.onset, 0)], np.inf),
        **{
            (INHERITANCE, name): np.where(month < n, r.ages[np.minimum(month, n - 1)], np.inf)
            for name, month in inherited.items()
        },
    }
    return {key: v.astype(np.float32) for key, v in values.items()}


@dataclass(frozen=True)
class Bin:
    low: float | None  # the range of the driver, open below or above at None
    high: float | None
    paths: int
    broke: float  # share of its paths broke by `BROKE_AGE`


@dataclass(frozen=True)
class Driver:
    key: Key
    # the broke paths against the others: the median of the driver, of an age driver (care,
    # disability, inheritance) the share with the event by `BROKE_AGE`
    broke: float
    others: float
    bins: tuple[Bin, ...]  # lowest values first


@dataclass(frozen=True)
class Anatomy:
    scenario: str
    paths: int
    broke: int  # paths broke by `BROKE_AGE`
    drivers: tuple[Driver, ...]
    age: int  # the whole age that `BROKE_AGE` takes in the run (`RunResult.age_at`)

    @property
    def p_broke(self) -> float:
        return self.broke / self.paths


def _driver(key: Key, values: FloatArray, broke: BoolArray) -> Driver:
    """Care by the ages of `CARE_AGES`, a disability by `DISABLED_AGES`, an inheritance by the
    whole ages that split the paths that receive it by `BROKE_AGE` into equal groups, any other
    driver in `GROUPS` groups of equal size."""
    if key[0] in AGES:
        fixed = {CARE: CARE_AGES, DISABLED: DISABLED_AGES}
        edges = np.array(fixed.get(key[0]) or _ages(values), dtype=float)
        by_then = values < BROKE_AGE
        sides = (float(by_then[broke].mean()), float(by_then[~broke].mean()))
    else:
        edges = np.quantile(values, np.arange(1, GROUPS) / GROUPS)
        sides = (float(np.median(values[broke])), float(np.median(values[~broke])))
    group = np.searchsorted(edges, values, side="right")
    paths: list[int] = np.bincount(group, minlength=len(edges) + 1).tolist()
    hits: list[float] = np.bincount(group, weights=broke, minlength=len(edges) + 1).tolist()
    bounds = [None, *map(float, edges), None]
    return Driver(
        key,
        *sides,
        tuple(
            Bin(low, high, n, h / n)
            for (low, high), n, h in zip(pairwise(bounds), paths, hits, strict=True)
            if n
        ),
    )


def _ages(values: FloatArray) -> list[float]:
    """Whole ages that split the values below `BROKE_AGE` into `GROUPS` - 1 groups, then
    `BROKE_AGE`: the paths without the event by then form the last group."""
    early = values[values < BROKE_AGE]
    shares = np.arange(1, GROUPS - 1) / (GROUPS - 1)
    inner = np.round(np.quantile(early, shares)).tolist() if early.size else []
    return [*sorted({float(a) for a in inner if a < BROKE_AGE}), float(BROKE_AGE)]


def of(r: RunResult) -> Anatomy | None:
    """A driver without spread is left out. None when no driver is left, or when no path or
    every path is broke by `BROKE_AGE`, so always for a single path."""
    broke = r.broke[:, : r.age_index(BROKE_AGE) + 1].any(axis=1)
    if broke.all() or not broke.any():
        return None
    drivers = tuple(
        _driver(key, values.astype(float), broke)
        for key, values in r.drivers.items()
        if values.min() < values.max()
    )
    return (
        Anatomy(r.label, r.paths, int(broke.sum()), drivers, r.age_at(BROKE_AGE))
        if drivers
        else None
    )
