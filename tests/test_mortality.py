"""Survival curves from the life table, its loader and the committed table."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from dagobert.model.assumptions import Person, Relative
from dagobert.model.taxes import Relation
from dagobert.mortality import LifeTable, death_months, load_life_table, survival_curve, table
from dagobert.series import life_table


def _life_table(n: int = 101) -> LifeTable:
    qx = np.linspace(0.001, 1.0, n)
    return LifeTable(qx={"m": qx, "f": qx * 0.9})


def test_survival_curve_starts_at_one_and_monotone() -> None:
    life = _life_table()
    person = Person(born=date(1960, 6, 15), sex="m")
    curve = survival_curve(life, person, date(2026, 1, 1), 240)
    assert curve[0] == 1.0
    assert np.all(np.diff(curve) <= 0)


def test_survival_curve_beyond_table_is_zero() -> None:
    life = _life_table()
    person = Person(born=date(1900, 1, 1), sex="f")
    curve = survival_curve(life, person, date(2026, 1, 1), 12)
    assert curve[-1] == 0.0


def test_load_life_table(tmp_path: Path) -> None:
    path = tmp_path / "sterbetafel.csv"
    path.write_text("age,qx_m,qx_f\n0,0.001,0.0009\n1,0.002,0.0018\n")
    loaded = load_life_table(path)
    assert loaded.qx["m"].tolist() == [0.001, 0.002]
    assert loaded.qx["f"].tolist() == [0.0009, 0.0018]


def test_load_life_table_rejects_gaps(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("age,qx_m,qx_f\n0,0.001,0.0009\n2,0.002,0.0018\n")
    with pytest.raises(ValueError, match="contiguous"):
        load_life_table(path)


def test_committed_sterbetafel_is_sane() -> None:
    """The committed table is data, not code: check the shape the engine relies on.
    `load_life_table` itself raises unless the ages run contiguously from 0."""
    shipped = load_life_table(life_table().path)

    assert shipped.qx["m"].shape == shipped.qx["f"].shape
    assert shipped.qx["m"].shape[0] > 90
    adult = slice(20, 80)
    assert np.all(shipped.qx["m"][adult] > shipped.qx["f"][adult])
    for sex in ("m", "f"):
        tail = shipped.qx[sex][40:]  # childhood/young-adult dips are past by 40
        assert np.all(np.diff(tail) >= 0)


def test_death_months_follow_the_draw() -> None:
    """A higher draw dies later; a draw near 1 lives past a short run (its length); a draw of 0.5
    dies in the median month, the first with a survival below 0.5."""
    mother = Relative(born=date(1950, 5, 1), sex="f", relation=Relation.PARENT)
    curve = survival_curve(table(), mother, date(2026, 1, 1), 600)
    months = death_months(curve, np.array([0.1, 0.5, 0.9]))
    assert list(months) == sorted(months)
    assert months[1] == np.argmax(curve < 0.5)
    short = curve[:120]
    assert death_months(short, np.array([1 - 1e-9]))[0] == len(short)
    # the share of the draws dead by a month is one less its survival
    draws = np.random.default_rng(1).random(20000)
    assert (death_months(curve, draws) <= 240).mean() == pytest.approx(1 - curve[240], abs=0.01)
