"""Cashflow plan sheet: monthly amounts, scheduled changes, revision diff."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from builders import plan

from dagobert import cashplan, revisions
from dagobert.cashplan import Change
from dagobert.loader import load_plan, read_yaml
from dagobert.model.assets import GoldAsset, PropertyAsset
from dagobert.model.assumptions import Index
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream
from dagobert.model.taxes import TaxOptions

ROWS: list[cashplan.Row] = [
    {"name": "Gehalt", "cat": "gehalt", "kind": "salary", "gross": 10_000, "part": 0.9},
    {"name": "Bonus", "cat": "gehalt", "kind": "salary", "of": "Gehalt", "share": 0.1, "every": 12},
    {"name": "ALG", "cat": "gehalt", "kind": "alg1", "phases": ["unemployed"]},
    {"name": "Miete", "cat": "wohnen", "amount": -900, "factor": {"retired": 0.5}},
    {"name": "Steuer", "cat": "wohnen", "amount": -300, "every": 3},
    {"name": "Abo", "cat": "medien", "amount": -10, "end": "2027-03-01"},
    {"name": "Abo", "cat": "medien", "amount": -12, "start": date(2027, 3, 1)},
]
TODAY = date(2026, 9, 18)
BUSINESS: list[cashplan.Row] = [
    *ROWS[:1],
    {"name": "Laden", "cat": "laden", "kind": "self_employed", "amount": 4000},
    {"name": "Anlauf", "cat": "laden", "kind": "self_employed", "amount": -500},
    {"name": "Projekt", "cat": "laden", "kind": "self_employed", "amount": 12_000}
    | {"every": 12, "start": date(2026, 12, 1)},
]
JOB = [r | {"phases": ["job"]} if r.get("kind") == "salary" else r for r in ROWS]


def test_monthly_equivalents() -> None:
    amounts = [cashplan.monthly(r, ROWS, "work") for r in ROWS]
    assert amounts == [9000.0, 900.0, None, -900.0, -100.0, -10.0, -12.0]
    assert cashplan.monthly(ROWS[3], ROWS, "retired") == -450.0
    # a row of a grid half typed, whose totals the header of its block shows
    half: list[cashplan.Row] = [{"name": "B", "kind": "salary", "of": "Gehalt"}, {"points": 10.0}]
    assert [cashplan.monthly(r, ROWS, "work") for r in half] == [0.0, 0.0]


def test_derived_stream_follows_the_row_active_on_the_day() -> None:
    rows: list[cashplan.Row] = [
        {"name": "Gehalt", "kind": "salary", "gross": 5000, "end": "2027-01-01"},
        {"name": "Gehalt", "kind": "salary", "gross": 6000, "start": "2027-01-01"},
        {"name": "Bonus", "kind": "salary", "of": "Gehalt", "share": 0.1, "every": 12},
    ]
    assert cashplan.monthly(rows[2], rows, "work", date(2026, 6, 1)) == 500.0
    assert cashplan.monthly(rows[2], rows, "work", date(2027, 6, 1)) == 600.0


def test_a_non_cumulative_index_counts_at_its_clipped_mean() -> None:
    """As the `fixed` run pays it: a bonus at its mean payout ratio. A cumulative index grows
    from 1, so its streams stay at 100 %."""
    indices = {
        "bonus": Index(mean=0.8, stdev=0.2, cap=1.0, cumulative=False),
        "high": Index(mean=1.2, cap=1.0, cumulative=False),
        "salary": Index(mean=0.03),
    }
    rows = cashplan.with_levels(
        [
            ROWS[0],
            *(ROWS[1] | {"name": name, "index": name} for name in indices),
            ROWS[3] | {"index": "bonus"},
        ],
        indices,
    )
    amounts = [cashplan.monthly(r, rows, "work") for r in rows]
    assert amounts == pytest.approx([9000, 0.8 * 900, 900, 900, 0.8 * -900])
    assert cashplan.LEVEL not in ROWS[1]


def test_sheet_splits_income_and_expenses_per_phase() -> None:
    assert cashplan.sheet(ROWS, TODAY, ["work", "retired"]) == {
        "income": {"gehalt": {"work": 9900.0, "retired": 9900.0}},
        "expenses": {
            "medien": {"work": -10.0, "retired": -10.0},
            "wohnen": {"work": -1000.0, "retired": -550.0},
        },
    }
    late = cashplan.sheet(ROWS, date(2027, 3, 1), ["work"])
    assert late["expenses"]["medien"] == {"work": -12.0}
    assert cashplan.sheet(ROWS[2:3], TODAY, ["unemployed"]) == {"income": {}, "expenses": {}}


def test_the_sheet_counts_a_profit_as_income() -> None:
    """A loss is negative income."""
    assert cashplan.sheet(BUSINESS, TODAY, ["work"])["income"]["laden"] == {"work": 4500.0}


def test_phase_totals_follow_the_date_and_resolve_derived_streams() -> None:
    assert cashplan.phase_totals(ROWS[3:], ROWS, TODAY, ["work", "retired"]) == {
        "work": -1010.0,
        "retired": -560.0,
    }
    assert cashplan.phase_totals(ROWS[1:3], ROWS, TODAY, ["unemployed"]) == {"unemployed": 900.0}
    unnamed: list[cashplan.Row] = [{"amount": -5}]  # a row the editor just added
    assert cashplan.phase_totals(unnamed, ROWS + unnamed, TODAY, ["work"]) == {"work": -5.0}


@pytest.mark.parametrize(
    ("rows", "phases", "salary"),
    [
        (ROWS, ["work"], ("work", 9000.0)),
        (BUSINESS, ["work"], ("work", 9000.0)),
        (JOB, ["unemployed", "job", "work"], ("job", 9000.0)),
        (JOB, ["unemployed", "retired"], None),
    ],
    ids=["no yearly bonus", "no business", "the newest phase with a salary", "none"],
)
def test_alg1_takes_the_last_monthly_salary(
    rows: list[cashplan.Row], phases: list[str], salary: tuple[str, float] | None
) -> None:
    """The engine bases ALG1 on the last salary paid: of the phase of the day, else of the newest
    phase before it that pays one, whatever its name."""
    assert cashplan.alg1_reference(rows, TODAY, phases) == salary


def test_the_pkv_premiums_end_with_a_switch_to_the_gkv() -> None:
    """`tax.gkv_from` ends the `health` rows as the engine does: an end before it stays, the
    other rows run on; a plan without it keeps them all."""
    switch = date(2027, 1, 1)
    rows: list[cashplan.Row] = [
        {"name": "PKV", "cat": "pkv", "amount": -600, "health": "kv"},
        {"name": "Tarif", "cat": "pkv", "amount": -40, "health": "kv", "end": "2026-10-01"},
        {"name": "Pflege", "cat": "pkv", "amount": -80, "health": "pv"},
        *ROWS[3:4],
    ]
    switched = cashplan.with_gkv(rows, switch)
    assert [r.get("end") for r in switched] == [switch, date(2026, 10, 1), switch, None]
    assert [c.name for c in cashplan.scheduled(switched, TODAY, ["work"])] == [
        "Tarif",
        "PKV",
        "Pflege",
    ]
    assert cashplan.with_gkv(rows, None) == rows
    premium = {"type": "add_stream", "stream": {"name": "Zusatz", "amount": -30, "health": "kv"}}
    scenario = Scenario.model_validate(
        {"name": "s", "events": [premium | {"at": "2026-11-01"}, premium | {"at": "2027-02-01"}]}
    )
    p = plan([], [], scenario, tax=TaxOptions(gkv_from=switch))
    assert [c.when for c in cashplan.scenario_changes([], p, TODAY, ["work"])] == [
        date(2026, 11, 1)
    ]


def test_alg1_estimate_fills_the_stream_without_amount() -> None:
    filled = cashplan.with_alg1(ROWS, 2500.0)
    assert cashplan.phase_totals(filled[2:3], filled, TODAY, ["work", "unemployed"]) == {
        "work": 0.0,
        "unemployed": 2500.0,
    }
    assert "amount" not in ROWS[2]


def test_periodic_stream_accrues_before_its_first_payment() -> None:
    bonus: cashplan.Row = {"name": "Bonus", "amount": 1200, "every": 12, "start": "2027-01-01"}
    assert cashplan.accrues_from(bonus) == date(2026, 2, 1)
    assert cashplan.active(bonus, TODAY, "work")
    assert not cashplan.active(bonus, date(2026, 1, 31), "work")
    assert cashplan.scheduled([bonus], TODAY, ["work"]) == []
    assert cashplan.accrues_from({"name": "Abo", "start": "2027-03-01"}) == date(2027, 3, 1)


def test_scheduled_changes() -> None:
    assert cashplan.scheduled(ROWS, TODAY, ["work"]) == [
        Change(date(2027, 3, 1), "Abo", "ends", {"work": 10.0}),
        Change(date(2027, 3, 1), "Abo", "starts", {"work": -12.0}),
    ]
    # a successor row of the same name on the same date is one change: a new price
    assert cashplan.scheduled(ROWS, TODAY, ["work"], paired=True) == [
        Change(date(2027, 3, 1), "Abo", "amount: -10 € → -12 €", {"work": -2.0}),
    ]
    gated: list[cashplan.Row] = [
        {"name": "Ticket", "amount": -50, "phases": ["work"], "end": "2027-01-01"}
    ]
    assert cashplan.scheduled(gated, TODAY, ["work", "retired"]) == [
        Change(date(2027, 1, 1), "Ticket", "ends", {"work": 50.0, "retired": 0.0})
    ]


def test_diff_between_versions() -> None:
    new = [dict(r) for r in ROWS if r["name"] != "Steuer"]
    new[3]["amount"] = -950
    new.append({"name": "Strom", "cat": "wohnen", "amount": -75})
    assert cashplan.diff(ROWS, new, ["work", "retired"], date(2026, 1, 1)) == [
        Change(None, "Miete", "amount: -900 € → -950 €", {"work": -50.0, "retired": -25.0}),
        Change(None, "Steuer", "removed", {"work": 100.0, "retired": 100.0}),
        Change(None, "Strom", "added", {"work": -75.0, "retired": -75.0}),
    ]


def test_diff_lists_the_bonus_of_a_raised_salary() -> None:
    """The bonus follows the salary: the changes add up to the change of the sheet."""
    new = [r | {"gross": 11_000} if r["name"] == "Gehalt" else r for r in ROWS]
    changes = cashplan.diff(ROWS, new, ["work"], date(2026, 1, 1))
    assert [(c.name, c.what, c.monthly) for c in changes] == [
        ("Gehalt", "gross: 10.000 € → 11.000 €", {"work": 900.0}),
        ("Bonus", "follows Gehalt", {"work": 90.0}),
    ]
    was, now = (cashplan.sheet(rows, TODAY, ["work"])["income"]["gehalt"] for rows in (ROWS, new))
    assert sum(c.monthly["work"] for c in changes) == now["work"] - was["work"]


def test_diff_pairs_a_stream_that_a_roll_forward_gave_the_old_start() -> None:
    """Kfz took the old start in a roll. Abo keeps a row without `start`: a price change."""
    start = date(2026, 1, 1)
    old: list[cashplan.Row] = [
        {"name": "Kfz", "amount": -600, "every": 12},
        {"name": "Abo", "amount": -120, "every": 12},
    ]
    new: list[cashplan.Row] = [
        {"name": "Kfz", "amount": -612, "every": 12, "start": start},
        {"name": "Abo", "amount": -120, "every": 12, "end": start},
        {"name": "Abo", "amount": -132, "every": 12, "start": start},
    ]
    assert [(c.name, c.what, c.monthly) for c in cashplan.diff(old, new, ["work"], start)] == [
        ("Kfz", "amount: -600 € → -612 €", {"work": -1.0}),
        ("Abo", "end: – → 2026-01-01", {"work": 0.0}),
        ("Abo", "added", {"work": -11.0}),
    ]
    unpaired = cashplan.diff(old, new, ["work"], date(2026, 2, 1))  # another start: no roll
    assert [(c.name, c.what) for c in unpaired] == [
        ("Kfz", "removed"),
        ("Abo", "end: – → 2026-01-01"),
        ("Kfz", "added"),
        ("Abo", "added"),
    ]


def test_diff_between_two_revisions(tmp_path: Path) -> None:
    def save(texts: dict[str, str]) -> str:
        entry = revisions.write(tmp_path, "test", lambda: texts)
        assert entry
        return entry.id

    first = save(
        {
            "cashflows.yaml": "streams:\n  - {name: Miete, amount: -900}\n",
            "assumptions.yaml": "start: 2026-10-01\n",
        }
    )
    second = save({"cashflows.yaml": "streams:\n  - {name: Miete, amount: -950}\n"})
    (old, start), (new, _start) = (cashplan.plan_at(tmp_path, at) for at in (first, second))
    assert start == date(2026, 10, 1)
    changes = cashplan.diff(old, new, ["work"], start)
    assert [(c.name, c.what, c.monthly) for c in changes] == [
        ("Miete", "amount: -900 € → -950 €", {"work": -50.0})
    ]
    broken = save({"cashflows.yaml": "streams: [\n"})  # a hand edit, recorded as it was
    with pytest.raises(ValueError, match=r"cashflows\.yaml of the revision"):
        cashplan.plan_at(tmp_path, broken)


def test_a_savings_plan_is_neither_income_nor_expense() -> None:
    """It takes its rate out of the surplus into an asset: the sheet and the bars leave it out,
    and a change of it has no effect on their monthly totals."""
    savings: cashplan.Row = {
        "name": "ETF",
        "kind": "savings",
        "amount": -500,
        "start": "2027-01-01",
    }
    rows = [*ROWS, savings]
    roles = [cashplan.role(r) for r in (ROWS[0], ROWS[3], savings)]
    assert roles == [cashplan.INCOME, cashplan.EXPENSE, cashplan.SAVINGS]
    later = date(2027, 6, 1)
    assert cashplan.sheet(rows, later, ["work"]) == cashplan.sheet(ROWS, later, ["work"])
    for income in (True, False):
        assert cashplan.by_stream(rows, later, "work", income=income) == cashplan.by_stream(
            ROWS, later, "work", income=income
        )
    starts = Change(date(2027, 1, 1), "ETF", "starts", {"work": 0.0})
    assert starts in cashplan.scheduled(rows, TODAY, ["work"])
    added = Change(None, "ETF", "added", {"work": 0.0})
    assert cashplan.diff(ROWS, rows, ["work"], date(2026, 1, 1)) == [added]


def test_a_bu_policy_shows_its_premium_and_its_change() -> None:
    """The sheet counts the premium as an expense in every phase, the benefit nowhere: only the
    run draws a disability. A `set_stream` of the premium is a scheduled change."""
    bu: cashplan.Row = {"name": "BU", "cat": "insurance", "kind": "bu", "amount": 2000}
    rows = [bu | {"premium": -95}]
    assert cashplan.role(bu) == cashplan.EXPENSE
    assert cashplan.sheet(rows, TODAY, ["work", "retired"])["expenses"] == {
        "insurance": {"work": -95.0, "retired": -95.0}
    }
    change = {"at": "2027-01-01", "type": "set_stream", "name": "BU", "premium": -95}
    scenario = Scenario.model_validate({"name": "s", "events": [change]})
    p = plan([Stream.model_validate(bu)], [], scenario)
    changes = cashplan.scenario_changes([bu], p, TODAY, ["work"])
    assert [(c.what, c.monthly) for c in changes] == [("premium: – → -95 €", {"work": -95.0})]


def test_by_stream_splits_the_sheet() -> None:
    assert cashplan.by_stream(ROWS, TODAY, "work", income=False) == {
        ("wohnen", "Miete"): -900.0,
        ("wohnen", "Steuer"): -100.0,
        ("medien", "Abo"): -10.0,
    }
    sheet = cashplan.sheet(ROWS, TODAY, ["retired"])
    for section, income in (("income", True), ("expenses", False)):
        per_cat: dict[str, float] = {}
        for (cat, _), value in cashplan.by_stream(ROWS, TODAY, "retired", income=income).items():
            per_cat[cat] = per_cat.get(cat, 0.0) + value
        assert per_cat == {cat: sums["retired"] for cat, sums in sheet[section].items()}


def test_scenario_changes_list_what_the_events_change() -> None:
    rows: list[cashplan.Row] = [
        {"name": "Hausgeld", "amount": -400, "tags": ["flat"]},
        {"name": "Miete danach", "amount": -1000, "after_sale_of": "flat"},
        {"name": "Strom", "amount": -75},
        {"name": "Gas", "amount": -30},
        {"name": "Job", "kind": "salary", "gross": 0, "phases": ["alt"]},
        {"name": "Grundsteuer", "amount": -40, "tags": ["home"]},
        {"name": "Verwaltung", "amount": -50, "property": "flat"},  # a sale ends it, no tag
    ]
    scenario = Scenario.model_validate(
        {
            "name": "s",
            "events": [
                {"at": "2020-01-01", "type": "end_streams", "names": ["Gas"]},  # before
                {"at": "2029-03-01", "type": "set_stream", "name": "Gas", "amount": -40},  # ended
                {"at": "2028-07-01", "type": "sell", "asset": "flat", "note": "sale"},
                {"at": "2028-01-01", "type": "set_stream", "name": "Strom", "amount": -120},
                {
                    "at": "2031-05-01",
                    "type": "add_stream",
                    "stream": {"name": "Job", "kind": "salary", "gross": 4000, "phases": ["alt"]},
                },
                {
                    "at": "2031-05-01",
                    "type": "add_stream",
                    "stream": {"name": "Bonus", "kind": "salary", "of": "Job", "share": 0.1}
                    | {"phases": ["alt"], "index": "bonus"},
                },
                {"type": "sell", "asset": "other", "when": {"age": 80}},
                {"at": "2029-01-01", "type": "sell", "asset": "gold"},  # ends no stream
                {"at": "2027-01-01", "type": "buy_property", "price": 1, "land": "BY"}
                | {"property": {"id": "home", "tags": ["home"]}},
                {"at": "2030-01-01", "type": "sell", "asset": "home"},
            ],
        }
    )
    assets: list[object] = [
        PropertyAsset(id="flat", kind="property", sqm=1, per_sqm=1, tags=["flat"]),
        PropertyAsset(id="other", kind="property", sqm=1, per_sqm=1),
        GoldAsset(id="gold", kind="gold", value=1, tags=["flat"]),
    ]
    bonus = {"bonus": {"mean": 0.8, "cumulative": False}}
    changes = cashplan.scenario_changes(
        rows,
        plan([Stream.model_validate(r) for r in rows], assets, scenario, indices=bonus),
        date(2026, 9, 1),
        ["work", "alt"],
    )
    assert [(c.when, c.name, c.what) for c in changes] == [
        (date(2028, 1, 1), "Strom", "amount: -75 € → -120 €"),
        (date(2028, 7, 1), "Hausgeld", "ends: sale of flat"),
        (date(2028, 7, 1), "Miete danach", "starts: after the sale of flat"),
        (date(2028, 7, 1), "Verwaltung", "ends: sale of flat"),
        (date(2030, 1, 1), "Grundsteuer", "ends: sale of home"),
        (date(2031, 5, 1), "Bonus", "starts"),
        (date(2031, 5, 1), "Job", "starts"),
    ]
    assert changes[1].monthly == {"work": 400, "alt": 400}
    assert changes[0].monthly == {"work": -45, "alt": -45}
    assert changes[5].monthly == {"work": 0, "alt": 320}  # the added Job at its payout ratio


def test_scenario_changes_follow_a_stream_added_again_under_its_name() -> None:
    """As in the engine: `end_streams` ends every row of the name so far, also one that starts
    later, and a `set_stream` after an `add_stream` of that name changes the added row."""
    rows: list[cashplan.Row] = [
        {"name": "Miete", "amount": -1000, "end": "2027-01-01"},
        {"name": "Miete", "amount": -1100, "start": "2027-01-01"},
    ]
    scenario = Scenario.model_validate(
        {
            "name": "s",
            "events": [
                {"at": "2026-12-01", "type": "end_streams", "names": ["Miete"]},
                {"at": "2030-01-01", "type": "add_stream"}
                | {"stream": {"name": "Miete", "amount": -800}},
                {"at": "2032-01-01", "type": "set_stream", "name": "Miete", "amount": -900},
            ],
        }
    )
    p = plan([Stream.model_validate(r) for r in rows], [], scenario)
    changes = cashplan.scenario_changes(rows, p, date(2026, 9, 1), ["work"])
    assert [(c.when, c.what, c.monthly) for c in changes] == [
        (date(2026, 12, 1), "ends", {"work": 1000}),
        (date(2030, 1, 1), "starts", {"work": -800}),
        (date(2032, 1, 1), "amount: -800 € → -900 €", {"work": -100}),
    ]


def test_scenario_changes_set_the_row_that_runs_as_the_engine_does() -> None:
    """A later row of the name keeps its amount, a change after the event; before the first row
    of a name the event changes the next one (`SetStreamEvent.targets`)."""
    rows: list[cashplan.Row] = [
        {"name": "Miete", "amount": -1000, "end": "2027-01-01"},
        {"name": "Miete", "amount": -1100, "start": "2027-01-01"},
        {"name": "Pflege", "amount": -200, "start": "2040-01-01"},
    ]
    scenario = Scenario.model_validate(
        {
            "name": "s",
            "events": [
                {"at": "2026-10-01", "type": "set_stream", "name": "Miete", "amount": -900},
                {"at": "2030-01-01", "type": "set_stream", "name": "Pflege", "amount": -250},
            ],
        }
    )
    p = plan([Stream.model_validate(r) for r in rows], [], scenario)
    changes = cashplan.scenario_changes(rows, p, date(2026, 9, 1), ["work"])
    assert [(c.when, c.name, c.what) for c in changes] == [
        (date(2026, 10, 1), "Miete", "amount: -1.000 € → -900 €"),
        (date(2030, 1, 1), "Pflege", "amount: -200 € → -250 €"),
    ]


def test_scenario_changes_leave_out_what_a_child_drops(data: Path) -> None:
    scen = data / "scenarios"
    (scen / "base.yaml").write_text(
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
        "events: [{at: 2027-01-01, id: rent, type: set_stream, name: Miete, amount: -600}]\n"
    )
    (scen / "child.yaml").write_text("name: child\nextends: base\ndrop: [rent]\n")
    rows = read_yaml(data / "cashflows.yaml")["streams"]
    changes = {
        name: [
            c.what
            for c in cashplan.scenario_changes(
                rows, load_plan(data, scen / f"{name}.yaml"), date(2026, 1, 1), ["work"]
            )
        ]
        for name in ("base", "child")
    }
    assert changes == {"base": ["amount: -500 € → -600 €"], "child": []}
