"""German period life tables, survival probability curves and the months of death they draw."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

import numpy as np
from numpy.typing import ArrayLike, NDArray

from dagobert import series
from dagobert.model.assumptions import Person, Relative
from dagobert.model.months import months_of_age
from dagobert.result import FloatArray


@dataclass(frozen=True)
class LifeTable:
    qx: dict[str, FloatArray]  # sex -> annual death probability, indexed by whole-year age


def load_life_table(path: Path) -> LifeTable:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ages = [int(row["age"]) for row in rows]
    if ages != list(range(len(ages))):
        msg = f"{path}: ages must be contiguous starting at 0"
        raise ValueError(msg)
    qx_m = np.array([float(row["qx_m"]) for row in rows], dtype=np.float64)
    qx_f = np.array([float(row["qx_f"]) for row in rows], dtype=np.float64)
    return LifeTable(qx={"m": qx_m, "f": qx_f})


@cache
def table() -> LifeTable:
    """The shipped life table (`series.life_table`), read once per process."""
    return load_life_table(series.life_table().path)


def survival_curve(
    table: LifeTable, person: Person | Relative, start: date, months: int
) -> FloatArray:
    """P(alive at month i | alive at start), i = 0..months-1, of the person or a relative by
    its date of birth and sex. curve[0] == 1."""
    qx = table.qx[person.sex]
    max_age = qx.shape[0] - 1
    ages = (months_of_age(person.born, start) + np.arange(months)) // 12
    q = np.where(ages <= max_age, qx[np.clip(ages, 0, max_age)], 1.0)
    monthly_survival = (1 - q) ** (1 / 12)
    curve = np.ones(months, dtype=np.float64)
    if months > 1:
        curve[1:] = np.cumprod(monthly_survival[:-1])
    return curve


def death_months(curve: FloatArray, u: ArrayLike) -> NDArray[np.intp]:
    """The month of death at each uniform draw `u`: the first month in which the share of the dead,
    1 - `curve`, exceeds it, so a higher draw dies later; `len(curve)` when none does (alive to
    the end). A draw of 0.5 gives the median month, the first with a survival below 0.5."""
    return np.searchsorted(1 - curve, u, side="right")
