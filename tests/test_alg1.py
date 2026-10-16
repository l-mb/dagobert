"""The claim to ALG1 as a balance of days (§§147, 148, 159, 161 SGB III): relations between runs
of one person with a salary of 5,000 € and then ALG1, by the months of ALG1 that they pay."""

from datetime import date

import numpy as np
import pytest
from builders import booked, cash, phases, plan, zero_run

from dagobert import sv
from dagobert.model.assumptions import Person
from dagobert.model.months import add_months
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import TaxOptions
from dagobert.result import SOURCE, FloatArray, RunResult
from dagobert.tax import for_year

TY = for_year(2026)
MONTHLY = float(sv.alg1_month(5000, TY, child=False))
START = date(2026, 1, 1)
LOST = date(2026, 3, 1)  # the first month without the job, index 2
UNEMPLOYED = ((LOST, "unemployed"),)


def _alg1(**kw: object) -> Stream:
    return Stream.model_validate({"name": "alg", "kind": "alg1", "phases": ["unemployed"]} | kw)


def _course(start: date, months: int) -> Stream:
    return Stream.model_validate(
        {"name": "course", "kind": "alg1", "training": True}
        | {"start": start, "end": add_months(start, months)}
    )


def _run(
    *rows: Stream,
    changes: tuple[tuple[date, str], ...] = UNEMPLOYED,
    others: tuple[Stream, ...] = (Stream(name="kv", amount=-700, health="kv", index=None),),
    months: int = 60,
    **kw: object,
) -> RunResult:
    """A salary of 5,000 € in `work` from the start, then the phase `changes`, the ALG1 `rows`
    and the `others`, by default a PKV premium of 700 €."""
    streams = [
        Stream(name="pay", kind=StreamKind.SALARY, gross=5000, index=None, phases=["work"]),
        *rows,
        *others,
    ]
    scenario = Scenario(name="s", phases=phases((START, "work"), *changes))
    return zero_run(plan(streams, [cash(500_000)], scenario, **kw), months)


def _paid(r: RunResult) -> FloatArray:
    """The months of ALG1 that each month pays, by the rows of the ledger."""
    return (booked(r, "alg", SOURCE) + booked(r, "course", SOURCE)) / MONTHLY


def _ends(r: RunResult) -> list[tuple[date, str]]:
    return [(m.month, m.kind) for m in r.markers if m.kind in ("alg1 used", "alg1 expired")]


def test_a_sperrzeit_pays_later_and_a_quarter_less() -> None:
    """§159 Abs. 3: twelve weeks without ALG1, 84 days of 30 a month (§339): two months and 24
    days of the third. §148 Abs. 1 Nr. 4: the claim of 360 days loses 90, a quarter, more than
    the 84 days of the Sperrzeit."""
    plain, rested = _run(_alg1()), _run(_alg1(sperrzeit=True))
    assert _paid(plain)[2:15].tolist() == pytest.approx([1.0] * 12 + [0.0])
    assert _paid(rested)[2:6].tolist() == pytest.approx([0.0, 0.0, 0.2, 1.0])
    assert _paid(rested).sum() == pytest.approx(0.75 * _paid(plain).sum())
    assert _ends(plain) == [(date(2027, 3, 1), "alg1 used")]


def test_a_sperrzeit_pays_no_premium_and_earns_no_points() -> None:
    """§174 SGB III: the Agentur pays the PKV premium for the days of ALG1, none in a Sperrzeit.
    The pension points of ALG1, 80% of the last salary (§166 Abs. 1 Nr. 2 SGB VI), only for its
    days. Born 1960: ten months to the pension at 67, of a claim of 24 months, less 180 days."""
    pension = Stream(name="rente", kind=StreamKind.PENSION, points=30, point_value=40)
    changes = (*UNEMPLOYED, (date(2027, 1, 1), "retired"))
    plain, rested = (
        _run(
            _alg1(sperrzeit=sperrzeit),
            changes=changes,
            others=(Stream(name="kv", amount=-700, health="kv", index=None), pension),
            months=13,
            person=Person(born=date(1960, 1, 1)),
        )
        for sperrzeit in (False, True)
    )
    subsidy = rested.income[0, 2:5] - _paid(rested)[2:5] * MONTHLY
    assert subsidy.tolist() == pytest.approx([0.0, 0.0, 0.2 * 700])
    assert _paid(plain).sum() == pytest.approx(10.0)
    assert _paid(rested).sum() == pytest.approx(7.2)
    points = 2.8 * TY.alg1_rv_share * 5000 / TY.durchschnittsentgelt
    lost = booked(plain, "rente", SOURCE)[12] - booked(rested, "rente", SOURCE)[12]
    assert lost == pytest.approx(points * 40)


def test_a_sperrzeit_keeps_a_member_of_the_gkv_compulsory() -> None:
    """§5 Abs. 1 Nr. 2 SGB V: compulsory also while a Sperrzeit rests the claim, since 2017-08
    from its first day: no voluntary KV, which a month without ALG1 pays."""
    gkv = TaxOptions(pkv=False)
    rested, without = (_run(*rows, others=(), tax=gkv) for rows in ((_alg1(sperrzeit=True),), ()))
    assert booked(rested, "KV")[2:4].tolist() == [0.0, 0.0]
    assert booked(without, "KV")[2] > 0


def test_a_sperrzeit_on_a_rest_takes_at_least_its_days() -> None:
    """§148 Abs. 1 Nr. 4: the days of the Sperrzeit, at least a quarter. A rest of 120 days
    loses 84, more than its quarter."""
    again = date(2027, 6, 1)
    changes = (*UNEMPLOYED, (date(2026, 11, 1), "work"), (again, "unemployed"))
    r = _run(_alg1(end=again), _alg1(start=again, sperrzeit=True), changes=changes)
    assert _paid(r)[2:10].sum() == pytest.approx(8.0)
    assert _paid(r)[17:22].tolist() == pytest.approx([0.0, 0.0, 0.2, 1.0, 0.0])


def test_a_course_uses_half_a_day_of_the_claim() -> None:
    """§148 Abs. 1 Nr. 7: six months of a course use three months of the claim, with the ALG1
    of the claim booked once, under the row of ALG1."""
    plain, course = _run(_alg1()), _run(_alg1(), _course(date(2026, 6, 1), 6))
    assert _paid(course)[2:17].tolist() == pytest.approx([1.0] * 15)
    assert _paid(course).sum() == pytest.approx(_paid(plain).sum() + 3)
    assert not booked(course, "course", SOURCE).any()


@pytest.mark.parametrize(
    ("before", "months", "after"),
    [(8, 6, 3), (10, 6, 3), (10, 5, 2)],
    ids=["down to three months", "raised to three months", "too short to raise"],
)
def test_a_course_leaves_three_months(before: int, months: int, after: int) -> None:
    """§148 Abs. 2 S. 3: a course takes no day below three months, a rest below them stays
    whole; Abs. 3: after a course of six months a rest below three months rises to them."""
    r = _run(_alg1(), _course(add_months(LOST, before), months))
    paid = _paid(r)[2:]
    assert paid[: before + months].tolist() == pytest.approx([1.0] * (before + months))
    assert paid[before + months :].sum() == pytest.approx(after)


@pytest.mark.parametrize(
    ("again", "paid", "ends"),
    [
        (date(2029, 6, 1), 6.0, [(date(2029, 12, 1), "alg1 used")]),
        (date(2029, 12, 1), 6.0, [(date(2030, 6, 1), "alg1 used")]),  # past 2030-03
        (date(2030, 3, 1), 0.0, [(date(2030, 3, 1), "alg1 expired")]),
    ],
    ids=["within four years", "begun within them", "after four years"],
)
def test_a_later_stretch_pays_the_rest(
    again: date, paid: float, ends: list[tuple[date, str]]
) -> None:
    """§161 Abs. 2 SGB III: the rest of a claim, six months here, pays in a later stretch that
    begins within four years after the claim arose; a stretch begun runs on (BA FW 161.2). The
    marker names the month in which it pays no more."""
    changes = (*UNEMPLOYED, (date(2026, 9, 1), "work"), (again, "unemployed"))
    r = _run(_alg1(), changes=changes, months=72)
    assert _paid(r)[2:8].sum() == pytest.approx(6.0)
    assert _paid(r)[8:].sum() == pytest.approx(paid)
    assert _ends(r) == ends


@pytest.mark.parametrize(
    ("age", "months"),
    [(49, 12), (50, 15), (54, 15), (55, 18), (57, 18), (58, 24)],
)
def test_the_duration_follows_the_age_in_the_first_month(age: int, months: int) -> None:
    """§147 Abs. 2: the age completed when the claim arises, the first month of ALG1: 50 in that
    month gives 15 months, a month later born gives 12."""
    born = add_months(LOST, -12 * age - 11 * (age in (49, 54, 57)))
    r = _run(_alg1(), person=Person(born=born))
    assert _paid(r).sum() == pytest.approx(months)


def test_the_age_counts_in_the_first_month_of_a_sperrzeit() -> None:
    """The claim arises with the Sperrzeit: 49 then, 50 when it first pays, still 12 months,
    less a quarter."""
    r = _run(_alg1(sperrzeit=True), person=Person(born=add_months(LOST, -12 * 50 + 1)))
    assert np.flatnonzero(_paid(r))[0] == 4
    assert _paid(r).sum() == pytest.approx(9.0)
