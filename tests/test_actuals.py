"""Actual spending: the file, the plan of a month, the comparison."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pytest
from builders import spent

from dagobert import actuals, cashplan, revisions
from dagobert.actuals import Clash, ClashError, Comparison, Coverage, Draft, Line
from dagobert.model.plan import Scenario

AUG, SEP, OCT = date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)
ROWS: list[cashplan.Row] = [
    {"name": "Gehalt", "cat": "gehalt", "kind": "salary", "gross": 5000},
    {"name": "Miete", "cat": "wohnen", "amount": -900, "end": "2026-10-01"},
    {"name": "Miete", "cat": "wohnen", "amount": -1000, "start": "2026-10-01"},
    {"name": "Grundsteuer", "cat": "wohnen", "amount": -120, "every": 12},
    {"name": "Kino", "cat": "freizeit", "amount": -100, "factor": {"retired": 0.5}},
    {"name": "Kita", "cat": "kinder", "amount": -300, "phases": ["work"]},
    {"name": "ETF", "kind": "savings", "amount": -500},  # plans no spending
]
SCENARIO = Scenario.model_validate(
    {"name": "s", "phases": [{"from": AUG, "phase": "work"}, {"from": OCT, "phase": "retired"}]}
)


def test_a_save_keeps_the_file_sorted_and_a_month_without_amounts_goes(data: Path) -> None:
    assert actuals.read(data) == {}
    spent(data, SEP, {"wohnen": -1000.5, "bargeld": -80})
    spent(data, date(2026, 8, 15), {"wohnen": -990})
    assert (data / actuals.FILE).read_text().splitlines() == [
        "month,category,amount",
        "2026-08,wohnen,-990.00",
        "2026-09,bargeld,-80.00",
        "2026-09,wohnen,-1000.50",
    ]
    actuals.save_draft(data, AUG, {"wohnen": (-990.0, None)}, source="test")
    assert actuals.read(data) == {SEP: {"wohnen": -1000.5, "bargeld": -80.0}}


def test_adds_of_two_devices_both_count(data: Path) -> None:
    """Each add reads the month under the lock of its write: none overwrites the other."""
    spent(data, SEP, {"wohnen": -1000})
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: actuals.add(data, SEP, "bargeld", 20.5, source="test"), range(10)))
    before, after = actuals.add(data, date(2026, 9, 30), "wohnen", 10, source="test")
    assert (before, after) == (
        {"bargeld": -205.0, "wohnen": -1000.0},
        {"bargeld": -205.0, "wohnen": -1010.0},
    )
    assert actuals.read(data) == {SEP: after}


@pytest.mark.parametrize(
    ("saved", "draft", "merged", "clashes"),
    [
        (  # the file changed only a category without an edit
            {"wohnen": -500.0, "bargeld": -70.0},
            {"wohnen": (-500.0, -520.0), "kino": (None, -8.0)},
            {"wohnen": -520.0, "bargeld": -70.0, "kino": -8.0},
            [],
        ),
        (  # both changed one category, to other amounts: the file stays
            {"wohnen": -510.0, "bargeld": -70.0},
            {"wohnen": (-500.0, -520.0), "bargeld": (-50.0, -55.0)},
            {"wohnen": -510.0, "bargeld": -70.0},
            [Clash("bargeld", -50.0, -55.0, -70.0), Clash("wohnen", -500.0, -520.0, -510.0)],
        ),
        ({"wohnen": -520.0}, {"wohnen": (-500.0, -520.0)}, {"wohnen": -520.0}, []),  # the same
        (
            {"kino": -8.0},
            {"kino": (None, -12.0)},
            {"kino": -8.0},
            [Clash("kino", None, -12.0, -8.0)],
        ),
        (  # a cleared cell, once unchanged and once changed elsewhere
            {"sport": -40.0, "kino": -9.0},
            {"sport": (-40.0, None), "kino": (-8.0, None)},
            {"kino": -9.0},
            [Clash("kino", -8.0, None, -9.0)],
        ),
        ({}, {"sport": (-40.0, -45.0)}, {}, [Clash("sport", -40.0, -45.0, None)]),  # removed
    ],
)
def test_merge_takes_the_newer_side_and_clashes_where_both_changed(
    saved: actuals.Amounts, draft: Draft, merged: actuals.Amounts, clashes: list[Clash]
) -> None:
    assert actuals.merge(saved, draft) == (merged, clashes)


def test_a_save_merges_its_edits_into_the_file_and_refuses_a_clash(data: Path) -> None:
    spent(data, SEP, {"wohnen": -500.0, "bargeld": -50.0})
    actuals.add(data, SEP, "bargeld", 20, source="phone")  # an add elsewhere
    saved = actuals.save_draft(
        data, SEP, {"wohnen": (-500.0, -520.0), "kino": (None, -8.0)}, source="test"
    )
    assert actuals.read(data)[SEP] == saved == {"bargeld": -70.0, "kino": -8.0, "wohnen": -520.0}
    actuals.add(data, SEP, "kino", 4, source="phone")
    log = revisions.entries(data)
    with pytest.raises(ClashError) as refused:
        actuals.save_draft(
            data, SEP, {"kino": (-8.0, -10.0), "wohnen": (-520.0, -530.0)}, source="test"
        )
    assert refused.value.clashes == [Clash("kino", -8.0, -10.0, -12.0)]
    assert actuals.read(data)[SEP] == saved | {"kino": -12.0}  # nothing saved
    assert revisions.entries(data) == log


def test_rows_of_a_month_and_category_add_up(data: Path) -> None:
    (data / "actuals.csv").write_text(
        "month,category,amount\n2026-09,wohnen,-10.1\n2026-09,wohnen,-20.2\n2026-08,sport,0\n"
    )
    # in cents: a float sum would be -30.299999999999997, an edit and a clash of nothing
    assert actuals.read(data) == {AUG: {"sport": 0.0}, SEP: {"wohnen": -30.3}}


def test_plan_of_a_month_follows_dates_and_phase() -> None:
    # expenses only, a yearly bill counts a twelfth, a successor row from its start
    assert actuals.planned(ROWS, SCENARIO, SEP) == {
        "freizeit": -100.0,
        "kinder": -300.0,
        "wohnen": -910.0,
    }
    # retired: half the Kino, no Kita
    assert actuals.planned(ROWS, SCENARIO, OCT) == {"freizeit": -50.0, "wohnen": -1010.0}


def test_comparison_counts_the_recorded_categories_only() -> None:
    recorded = {
        AUG: {"wohnen": -900.0},
        SEP: {"wohnen": -950.0, "freizeit": -70.0, "Kaffee": -40.0},
        OCT: {"wohnen": -1010.0},
    }
    comparison = Comparison.of(recorded, ROWS, SCENARIO, count=2)
    assert list(comparison.cells) == [SEP, OCT]
    assert comparison.by_month() == {
        SEP: Line(-1010.0, -1060.0),  # Kita has no actual, so no plan either
        OCT: Line(-1010.0, -1010.0),
    }
    assert list(comparison.by_category().items()) == [  # a capital sorts by the letter
        ("freizeit", (Line(-100.0, -70.0), 1)),
        ("Kaffee", (Line(0.0, -40.0), 1)),
        ("wohnen", (Line(-1920.0, -1960.0), 2)),
    ]
    wohnen = comparison.by_category()["wohnen"][0]
    assert wohnen.difference == -40.0
    assert wohnen.share == pytest.approx(-40 / 1920)
    assert Line(0.0, -40.0).share is None


FULL = {"wohnen": -1.0, "freizeit": 0.0, "kinder": -1.0}  # the plan of a month in work, 0 counts
JUN, JUL = date(2026, 6, 1), date(2026, 7, 1)


@pytest.mark.parametrize(
    ("recorded", "expected"),
    [
        ({}, None),
        ({SEP: FULL}, None),
        ({AUG: FULL}, Coverage(SEP, 0, 3)),
        ({JUN: FULL}, None),  # no record in the last three months: no longer kept
        ({JUL: FULL}, Coverage(AUG, 0, 3)),
        ({JUN: FULL, AUG: FULL, SEP: FULL}, Coverage(JUL, 0, 3)),  # a gap
        ({AUG: FULL, OCT: {"wohnen": -1.0}}, Coverage(SEP, 0, 3)),  # the current one on the go
        ({AUG: FULL, SEP: {"wohnen": -1.0, "bargeld": -5.0}}, Coverage(SEP, 1, 3)),  # unplanned
        ({AUG: FULL | {"Kino": -9.0}, SEP: FULL | {"kinder": 0.0}}, None),
    ],
)
def test_missing_is_the_first_complete_month_without_an_actual_per_planned_category(
    recorded: dict[date, dict[str, float]], expected: Coverage | None
) -> None:
    assert actuals.missing(recorded, ROWS, SCENARIO, date(2026, 10, 5)) == expected
