"""The Overview: the roll forward, the plan, the records against the plan, the items
that need attention and their links."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

import pytest
from apps import MAIN, labels, record
from builders import ASSETS, spent
from german import ACTIVATE, words
from streamlit.testing.v1 import AppTest

from dagobert import datadir, goalseek, i18n, revisions, rollforward, schema
from dagobert.loader import APP, load_assumptions, load_plan
from dagobert.model.assets import Assets
from dagobert.model.months import add_months, months_between
from dagobert.money import format_eur
from dagobert.result import RunResult
from dagobert.runner import DATA_ENV
from dagobert.ui import PAGES, SCENARIO, TAB, day_said, mode, outlook, overview, runs

PHASES = "phases: [{from: 2026-01-01, phase: work}]\nnote: then\n"
POLICY = {
    "id": "bav",
    "kind": "bav",
    "value": 5000,
    "phases": [],
    "matures": "2040-01-01",
    "growth": "equity",
}
OVERVIEW = """
from pathlib import Path
from typing import Literal
from dagobert.store import streams_file
from dagobert.ui import overview
overview.page(streams_file(Path({data!r})))
"""


VPW = {"base": "no_pay", "categories": ["wohnen"], "vpw": {}}  # the rent of `data` flexible


def test_overview_rolls_the_start_forward(data: Path) -> None:
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    month = date.today().replace(day=1)  # the fixture starts in 2026-01
    at.selectbox(key="overview-roll-to").select(add_months(month, -1)).run()
    amounts = next(d.value for d in at.dataframe if "old" in d.value.columns)
    assert len(amounts)  # whole and broken amounts alike show with cents
    assert all(cell.endswith(" €") and "," in cell for cell in amounts["old"])
    at.button(key="overview-roll").click().run()
    assert not at.exception
    assert load_assumptions(data).start == add_months(month, -1)
    assert at.selectbox(key="overview-roll-to").options == [f"{month:%Y-%m}"]  # one month left
    at.button(key="overview-roll").click().run()
    assert not at.exception
    assert load_assumptions(data).start == month
    assert f"to {month:%Y-%m}." in at.success[0].value
    assert [e.source for e in revisions.entries(data)[1:]] == ["app: roll forward"] * 2
    assert "overview-roll" not in [b.key for b in at.button]  # nothing left to roll


def test_the_roll_forward_lists_and_keeps_the_founding_of_a_business(data: Path) -> None:
    """A business that runs before the new start keeps its founding: the half Regelbeitrag."""
    (data / "cashflows.yaml").write_text(
        "streams: [{name: Praxis, kind: self_employed, amount: 5000, index: null, "
        "start: 2026-02-01}]\n"
    )
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("tax: {self_employed: {rv: regular}}\n")
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    founded = next(d.value for d in at.dataframe if "founded" in d.value.columns)
    assert founded.values.tolist() == [["2026-02", "all", "assumptions.yaml"]]
    at.button(key="overview-roll").click().run()
    assert not at.exception
    assert "assumptions.yaml keeps the founding of a business, 2026-02" in at.success[0].value
    assert load_assumptions(data).tax.self_employed.founded == date(2026, 2, 1)


def test_the_roll_forward_lists_and_keeps_the_losses_carried(data: Path) -> None:
    """A loss of a business in the months before the new start carries forward (§10d EStG)."""
    (data / "cashflows.yaml").write_text(
        "streams: [{name: Laden, kind: self_employed, amount: -1000, index: null, "
        "end: 2027-01-01}]\n"
    )
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    months = min(months_between(date(2026, 1, 1), date.today()), 12)
    pot = format_eur(1000 * months, cents=True)
    carried = next(d.value for d in at.dataframe if "loss_carryforward" in d.value.columns)
    assert carried.values.tolist() == [[pot, "all", "assumptions.yaml"]]
    at.button(key="overview-roll").click().run()
    assert not at.exception
    assert f"assumptions.yaml keeps the losses carried, {pot}" in at.success[0].value
    assert load_assumptions(data).tax.loss_carryforward == 1000 * months


def test_the_roll_forward_lists_and_keeps_the_capital_losses_carried(data: Path) -> None:
    """Losses of capital income carried to the start (§20 Abs. 6 EStG) carry on to the new one."""
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("tax: {capital_losses: 5000}\n")
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    carried = next(d.value for d in at.dataframe if "capital_losses" in d.value.columns)
    [[pot, *where]] = carried.values.tolist()
    assert where == ["all", "assumptions.yaml"]
    at.button(key="overview-roll").click().run()
    assert not at.exception
    kept = f"assumptions.yaml keeps the losses of capital income carried, {pot}"
    assert kept in at.success[0].value
    assert format_eur(load_assumptions(data).tax.capital_losses, cents=True) == pot


def test_overview_shows_the_plan(data: Path) -> None:
    """The outlook of the main scenario, the first of `app.yaml`, by its name and note; the target
    names the age that the run takes the chance to run out at."""
    (data / "scenarios" / "early.yaml").write_text(f"name: Early\n{PHASES}")
    (data / APP).write_text("scenarios: [early, base]\n")
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    assert "Main scenario: Early" in [s.value for s in at.subheader]
    assert "then" in [c.value for c in at.caption]  # its note
    assert any("main scenario, Early," in e.value for e in at.markdown)  # the folds name it
    tiles = [labels(data)[term] for term in outlook.TILES]
    assert [m.label for m in at.metric if m.label in tiles] == tiles
    target = at.number_input(key="overview-seek-target")
    assert target.label == "Target, chance to run out by 51 (%)"
    assert "needs a saved version of the plan" in at.info[-1].value  # no revision, no comparison
    stop = next(m for m in at.metric if m.label == goalseek.STOP)
    assert (stop.value, stop.delta) == ("–", "not searched yet")
    at.button(key="overview-stop").click().run()  # the plan pays no salary: a sentence, no runs
    assert not at.exception
    assert any(m.value.startswith("No phase of the scenario pays") for m in at.markdown)
    stop = next(m for m in at.metric if m.label == goalseek.STOP)
    assert (stop.value, stop.delta) == ("–", "see the answer below")


def test_the_recorded_net_worth_stands_beside_the_assets_once_it_has_a_chart(data: Path) -> None:
    """One recorded month: the rings, then the info of the history below them, no empty column
    beside them, and on to the Explorer: the plan needs no record; a second month of records: the
    chart beside the rings."""
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60)
    for rows, beside in (
        ("2026-01-15,giro,1100\n", []),  # in the start month: one month
        ("2026-03-15,giro,1100\n", ["Assets", "Recorded net worth"]),
    ):
        (data / "history.csv").write_text(f"date,asset,value\n{rows}")
        at.run()
        assert not at.exception
        assert [s.value for column in at.columns for s in column.subheader] == beside
        assert (overview.explore(mode.EVERYTHING) in [m.value for m in at.markdown]) == (not beside)


@pytest.mark.parametrize(
    ("used", "named"),
    [
        (set(), []),
        ({"records"}, ["Snapshot"]),
        ({"actuals"}, ["Spend"]),
        ({"records", "actuals"}, ["Snapshot", "Spend"]),
    ],
)
def test_the_line_to_the_explorer_names_the_pages_of_the_records_that_show(
    used: set[str], named: list[str]
) -> None:
    """Simple mode shows the Snapshot and Spend pages only while records are kept on them."""
    found = {mode.Item(mode.Sort.PAGE, (mode.RECORDED[data],)) for data in used}
    line = overview.explore(mode.View(mode.Uses(frozenset(found)), frozenset(), advanced=False))
    assert [page for page in ("Snapshot", "Spend") if page in line] == named
    assert line.startswith(overview.EXPLORE)


def test_simple_mode_shows_the_records_once_they_are_kept(data: Path) -> None:
    """Without a record no stale value, no recorded net worth and no comparison with the plan;
    with one they come back, as in advanced mode."""
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60)
    at.query_params["mode"] = "simple"
    at.run()
    assert not at.exception
    headings, cells = [s.value for s in at.subheader], [m.value for m in at.markdown]
    assert not {"Recorded net worth", "Records against the plan"} & set(headings)
    assert "the value has no date yet" not in cells
    assert [t for t in words(at) if "Snapshot" in t or "Spend page" in t] == []  # not shown
    (data / "history.csv").write_text("date,asset,value\n2026-01-15,giro,1100\n")
    at.run()
    headings, cells = [s.value for s in at.subheader], [m.value for m in at.markdown]
    assert {"Recorded net worth", "Records against the plan"} <= set(headings)
    assert "the value has no date yet" in cells


@pytest.mark.parametrize(
    ("asset", "carried"),
    [
        (POLICY, False),  # its value holds at the start
        (POLICY | {"asof": "2025-12-31"}, True),
        ({"id": "av", "kind": "av_depot", "start": "2027-01-01", "asof": "2026-06-30"}, True),
        ({"id": "giro", "kind": "cash", "value": 1000, "asof": "2025-12-31"}, False),
    ],
    ids=["undated policy", "dated policy", "dated depot", "dated account"],
)
def test_the_plan_carries_a_policy_from_the_date_of_its_value(
    asset: dict[str, object], *, carried: bool
) -> None:
    assert outlook.carried(Assets.model_validate({"assets": [asset]}).assets) == carried


def test_the_records_against_the_plan_say_how_the_plan_carries_a_policy(data: Path) -> None:
    """Records keep a policy as typed, the plan carries it on: a line below the chart says so and
    names `Take estimates`, only while the policy has the date of its value."""
    (data / "history.csv").write_text("date,asset,value\n2026-03-15,giro,1100\n")
    record(
        data,
        "20260110T120000.000000+0000",
        "test",
        {"scenarios/base.yaml": "name: base\n" + PHASES},
    )
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60)
    for policy, said in ((POLICY, False), (POLICY | {"asof": "2025-12-31"}, True)):
        (data / "assets.yaml").write_text(f"{ASSETS}  - {json.dumps(policy)}\n")
        at.run()
        assert not at.exception
        assert any(m.value.startswith("The last record") for m in at.markdown)  # the comparison
        assert any("Take estimates" in c.value for c in at.caption) == said


def test_the_last_tile_shows_the_month_to_stop_working_that_meets_the_target() -> None:
    dial = goalseek.Dial(
        goalseek.STOP,
        ((("shift", "retired"), 1.0),),
        0.0,
        -24.0,
        12.0,
        1.0,
        whole=True,
        origin=date(2040, 1, 1),
        born=date(1985, 6, 1),
    )
    found = goalseek.Found(-6.0, 0.04, 9, rising=False)
    assert outlook.stopped((found, dial), 0.05) == (date(2039, 7, 1), 54)
    assert outlook.stopped((replace(found, p_broke=0.06), dial), 0.05) is None  # misses it
    assert outlook.stopped((replace(found, rising=None), dial), 0.05) is None  # no effect
    assert outlook.stopped(None, 0.05) is None  # a plan without the change


@pytest.mark.parametrize(
    ("spending", "found", "said"),
    [
        ({}, goalseek.Found(0.5, 0.05, 9, rising=None), "Spending does not change"),
        (VPW, goalseek.Found(1450, 0.05, 9, rising=True), "A floor of up to **1.450 € per month**"),
        (VPW, goalseek.Found(0, 0.2, 2, rising=True), "even at a floor of 0 € per month"),
        (VPW, goalseek.Found(0, 0.0, 2, rising=None), "from 0 € to 5.000 € per month"),
    ],
    ids=["no expense", "floor", "floor missed", "floor without effect"],
)
def test_the_spending_seek_answers_in_the_units_of_its_dial(
    data: Path, spending: dict[str, object], found: goalseek.Found, said: str
) -> None:
    """A factor on the spending, also of a plan without an expense stream (no category to move),
    and under VPW the floor in euros."""
    if spending:
        with (data / "assumptions.yaml").open("a") as fh:
            fh.write(f"spending: {json.dumps(spending)}\n")
    else:
        (data / "cashflows.yaml").write_text("streams: []\n")
    _label, dial_of, say = outlook.SEEKS["overview-seek"]
    dial = dial_of(load_plan(data, data / "scenarios" / "base.yaml"))
    assert said in say(found, dial, 0.05)


@pytest.mark.parametrize(
    ("found", "said"),
    [
        (goalseek.Found(0.86, 0.049, 34, rising=True), ["Spend at most **", "14% less than now"]),
        (goalseek.Found(1.25, 0.049, 34, rising=True), ["25% more than now"]),
        (goalseek.Found(0.5, 0.2, 34, rising=True), ["Even ", "50% less than now", "above"]),
    ],
    ids=["less", "more", "missed"],
)
def test_the_spending_seek_answers_in_plain_words(
    data: Path, found: goalseek.Found, said: list[str]
) -> None:
    """No factor and no count of runs in the sentence: the amount and the change against now."""
    _label, dial_of, say = outlook.SEEKS["overview-seek"]
    sentence = say(found, dial_of(load_plan(data, data / "scenarios" / "base.yaml")), 0.05)
    assert all(part in sentence for part in said)
    assert "×" not in sentence
    assert "runs" not in sentence.replace("run out", "")


def test_a_work_seek_that_misses_names_the_age_of_its_latest_month() -> None:
    dial = goalseek.Dial(
        goalseek.STOP,
        ((("shift", "retired"), 1.0),),
        0.0,
        -24.0,
        12.0,
        1.0,
        whole=True,
        origin=date(2040, 1, 1),
        born=date(1985, 6, 1),
    )
    missed = goalseek.Found(12.0, 0.2, 9, rising=False)
    assert outlook.latest((missed, dial), 0.05) == 55  # 2041-01 at 55
    assert outlook.latest((replace(missed, p_broke=0.04), dial), 0.05) is None  # it meets it
    assert outlook.latest((replace(missed, rising=True), dial), 0.05) is None
    assert outlook.latest(None, 0.05) is None


def test_the_plan_says_when_it_stops_working(tmp_path: Path) -> None:
    """The change out of the last phase with a salary: the Regelaltersgrenze of a quick start;
    a plan without a salary says nothing."""
    for gross, said in ((4200.0, "The plan stops working in 2057-"), (None, None)):
        data = tmp_path / str(gross)
        data.mkdir()
        for name, text in datadir.texts(datadir.Quick(date(1990, 5, 20), gross=gross)).items():
            (data / name).parent.mkdir(exist_ok=True)
            (data / name).write_text(text)
        sentence = outlook.assumed(load_plan(data, data / "scenarios" / "plan.yaml"))
        assert (sentence is None) if said is None else (sentence or "").startswith(said)


def test_the_overview_says_why_a_plan_has_no_work_seek_in_german(data: Path) -> None:
    at = AppTest.from_string(ACTIVATE + OVERVIEW.format(data=str(data)), default_timeout=60)
    at.query_params["lang"] = "de"
    at.run().button(key="overview-stop").click().run()
    assert not at.exception
    assert any(m.value.startswith("In keiner Phase des Szenarios fließt") for m in at.markdown)


@pytest.mark.parametrize(
    ("first", "chosen"),
    [
        (date(2026, 10, 1), "2026-10-31"),  # the plan when the record began
        (date(2026, 11, 1), "2026-11-02"),
        (date(2026, 8, 1), "2026-09-29"),  # the record began before the first day
    ],
)
def test_on_track_opens_on_the_plan_when_the_record_began(first: date, chosen: str) -> None:
    days = [
        revisions.Day(date.fromisoformat(day), str(i), ())
        for i, day in enumerate(["2026-12-05", "2026-11-02", "2026-10-31", "2026-09-29"])
    ]
    assert outlook.default_day(days, first).day == date.fromisoformat(chosen)


def test_on_track_lists_the_days_whose_inputs_hold_the_scenario(data: Path) -> None:
    scenario = "scenarios/base.yaml"
    streams = (data / "cashflows.yaml").read_text()
    (data / scenario).unlink()  # the baseline holds no scenario
    for day, change in (
        (9, {}),
        (10, {scenario: "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"}),
        (11, {scenario: None}),  # removed
        (12, {scenario: "name: base\nphases: [{from: 2026-02-01, phase: work}]\n"}),
        (13, {"cashflows.yaml": streams + "\n"}),
    ):
        record(data, f"202601{day:02}T120000.000000+0000", "test", change)
    assert [d.day.day for d in outlook.plan_days(data, "base")] == [13, 12, 10]


def test_on_track_keeps_the_days_before_a_rename(data: Path) -> None:
    old, new = "scenarios/base.yaml", "scenarios/plan.yaml"
    text = (data / old).read_text() + "note: x\n"
    record(data, "20260110T120000.000000+0000", "test", {old: text})
    renaming = f"Scenarios: {revisions.renaming(old, new)}"
    record(data, "20260112T120000.000000+0000", renaming, {old: None, new: text})
    found = outlook.plan_days(data, "plan")
    assert {d.day.day: file for d, file in found.items()} == {12: new, 10: old}


def test_a_day_names_an_edit_outside_the_app_in_german() -> None:
    day = revisions.Day(date(2026, 1, 10), "x", ((revisions.OUTSIDE, 2),))
    with i18n.use("de"):
        assert day_said(day) == "2026-01-10 · außerhalb der App ×2"


REFUSAL = "no tax constants for 2019"


def _refuses(_data: Path, _file: Path) -> RunResult:
    """A run that the engine refuses, as with a tax year that the code no longer ships."""
    raise ValueError(REFUSAL)


def test_a_past_plan_that_the_engine_refuses_gives_its_reason(data: Path) -> None:
    scenario = "scenarios/base.yaml"
    record(data, "20260110T120000.000000+0000", "test", {scenario: "name: base\n" + PHASES})
    at = revisions.entries(data)[-1].id
    assert runs.at_revision(data, at, scenario, _refuses) == runs.Refused(REFUSAL)
    assert runs.at_revision(data, at, "scenarios/gone.yaml", _refuses) is None


AT_REVISION = runs.Refused("the run in a directory of its own")


@pytest.mark.parametrize(
    ("later", "model", "files"),
    [
        ({APP: "scenarios: [base]\n"}, "explorer", True),
        ({APP: "scenarios: [base]\n"}, "fixed", True),
        ({"history.csv": "date,asset,value\n2026-03-15,giro,1100\n"}, "fixed", True),
        ({schema.MANIFEST: schema.manifest_text()}, "fixed", True),
        ({"scenarios/base.yaml": "name: base\n" + PHASES.replace("then", "later")}, "fixed", False),
        ({"scenarios/base.yaml": None}, "explorer", False),
    ],
)
def test_the_baseline_is_the_run_of_the_files_while_they_hold_its_plan(
    data: Path,
    monkeypatch: pytest.MonkeyPatch,
    later: revisions.Texts,
    model: Literal["fixed", "explorer"],
    files: bool,
) -> None:
    """`Records against the plan` and the Flows comparison run nothing more while no later
    revision changed what a run reads: a save of `app.yaml`, the records or the manifest keeps
    the run of the files, a change or a removal of the plan runs its inputs of that day."""
    monkeypatch.setattr(runs, "at_revision", lambda *_: AT_REVISION)
    scenario = "scenarios/base.yaml"
    record(data, "20260110T120000.000000+0000", "test", {scenario: "name: base\n" + PHASES})
    at = revisions.entries(data)[-1].id
    record(data, "20260111T120000.000000+0000", "test", later)
    found = runs.baseline(data, scenario, at, model)
    assert isinstance(found, RunResult) if files else found is AT_REVISION


def test_records_against_a_plan_that_no_longer_runs_say_why(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A past plan that loads but that the engine of today refuses: the comparison names the
    reason instead of a traceback."""
    at_revision = runs.at_revision
    monkeypatch.setattr(runs, "at_revision", lambda d, at, f, _run: at_revision(d, at, f, _refuses))
    (data / "history.csv").write_text("date,asset,value\n2026-03-15,giro,1100\n")
    scenario = "scenarios/base.yaml"
    record(data, "20260110T120000.000000+0000", "test", {scenario: "name: base\n" + PHASES})
    # a later plan, so the one of the record runs on its own inputs, not those of the files
    later = "name: base\n" + PHASES.replace("then", "later")
    record(data, "20260501T120000.000000+0000", "test", {scenario: later})
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    assert any(f"this version of the app ({REFUSAL})" in w.value for w in at.warning)


ATTENTION_ASSETS = """\
assets:
  - {id: giro, kind: cash, value: 1000, asof: 2025-09-01}
  - {id: depot, kind: equity, value: 5000, cost_basis: 4000, asof: 2026-06-01}
  - {id: soon, kind: term_deposit, value: 1000, rate: 0.03, start: 2025-09-01,
     matures: 2027-03-01}
  - {id: later, kind: term_deposit, value: 1000, rate: 0.03, start: 2025-09-01,
     matures: 2028-01-01, asof: 2025-09-01}
  - {id: done, kind: term_deposit, value: 1000, rate: 0.03, start: 2024-09-01,
     matures: 2026-09-01}
  - {id: fixed, kind: loan, balance: -1000, rate: 0.02, annuity: 100, fixed_until: 2027-09-01,
     asof: 2026-09-01}
  - {id: long, kind: loan, balance: -1000, rate: 0.02, annuity: 100, fixed_until: 2027-10-01,
     asof: 2026-09-01}
  - {id: ended, kind: loan, balance: -1000, rate: 0.02, annuity: 100, fixed_until: 2026-08-01,
     asof: 2026-09-01}
  - {id: undated, kind: loan, balance: -1000, rate: 0.02, annuity: 100}
  - {id: empty, kind: cash, value: 0, asof: 2025-09-01}
"""


ATTENTION_STREAMS = """\
streams:
  - {name: Miete, cat: wohnen, amount: -500}
  - {name: Strom, cat: wohnen, amount: -80, end: 2026-12-01}
  - {name: Strom, cat: wohnen, amount: -95, start: 2026-12-01}
  - {name: Kita, cat: kinder, amount: -300, start: 2027-01-01}
"""


ATTENTION_SCENARIO = """\
name: base
phases: [{from: 2026-01-01, phase: work}, {from: 2026-12-01, phase: retired}]
events:
  - {at: 2026-11-01, type: end_streams, names: [Miete]}
  - {at: 2027-02-01, type: set_stream, name: Strom, amount: -75}
  - {at: 2026-12-01, type: buy_property, price: 200000, land: BY, property: {id: home},
     loan: {id: home-loan, balance: -150000, rate: 0.03, annuity: 700}}
  - {at: 2027-01-01, type: buy_property, price: 1, transfer_tax: 0, property: {id: cabin}}
"""


def test_attention_lists_what_falls_due(data: Path) -> None:
    (data / "assets.yaml").write_text(ATTENTION_ASSETS)
    (data / "cashflows.yaml").write_text(ATTENTION_STREAMS)
    (data / "scenarios" / "base.yaml").write_text(ATTENTION_SCENARIO)
    notices = overview.attention(data, "base", date(2026, 9, 28))
    # each with the page where the inputs change: an asset on its row with the fields to check
    assert [
        (n.when, n.item, n.late, n.fix and (n.fix.page, dict(n.fix.query))) for n in notices
    ] == [
        # a deposit and an empty account need no date
        (None, "undated", True, ("Assets", {"asset": "undated", "fields": "balance,asof"})),
        # a zero goes stale too, a deposit never
        (date(2025, 9, 1), "empty", True, ("Assets", {"asset": "empty", "fields": "value,asof"})),
        # older than twelve months
        (date(2025, 9, 1), "giro", True, ("Assets", {"asset": "giro", "fields": "value,asof"})),
        (date(2026, 1, 1), "simulation start", True, None),  # the Roll forward below the table
        (
            date(2026, 8, 1),
            "ended",
            True,
            ("Assets", {"asset": "ended", "fields": "fixed_until,rate"}),
        ),
        (date(2026, 9, 1), "done", True, ("Assets", {"asset": "done", "fields": "matures,value"})),
        # an event of the scenario: its type in the file that writes it
        (
            date(2026, 11, 1),
            "Miete",
            False,
            ("Scenarios", {"scenario": "base", "event": "end_streams"}),
        ),
        (date(2026, 12, 1), "Strom", False, ("Cashflows", {})),  # a new price of a stream
        # a purchase within three months
        (
            date(2026, 12, 1),
            "home",
            False,
            ("Scenarios", {"scenario": "base", "event": "buy_property"}),
        ),
        (date(2027, 3, 1), "soon", False, ("Assets", {"asset": "soon", "fields": "matures"})),
        (
            date(2027, 9, 1),
            "fixed",
            False,
            ("Assets", {"asset": "fixed", "fields": "fixed_until,rate"}),
        ),
    ]
    assert notices[3].what == "8 months ago, see Roll forward"
    assert notices[6].what == "ends, +500 € per month in Work"
    assert notices[7].what == "amount: -80 € → -95 €, -15 € per month in Retired"  # one row
    assert notices[8].what == (
        "bought for 200.000 €, 207.000 € with the transfer tax and the costs: 57.000 € from cash "
        "and liquid assets"
    )
    assert notices[9].what == "matures, pays 1.045 €"  # 18 months at 3 %
    spent(data, date(2026, 7, 1), {"wohnen": -500.0})
    spent(data, date(2026, 8, 1), {"bargeld": -20.0})  # an unplanned category only
    what = "2026-08: 0 of 1 planned categories"
    month = overview.Link("Spend", query={"month": "2026-08"})  # the grid of that month
    missing = overview.Notice(date(2026, 8, 1), "actual spending", what, True, month)
    assert missing in overview.attention(data, "base", date(2026, 9, 28))
    # an event of a parent links to the file of the parent
    (data / "scenarios" / "kid.yaml").write_text("name: kid\nextends: base\n")
    kid = {n.item: n.fix for n in overview.attention(data, "kid", date(2026, 9, 28))}
    assert kid["Miete"] == notices[6].fix


def test_attention_names_a_disability_without_a_pension_from_points(data: Path) -> None:
    """The EM-Rente rides on the statutory pension from points: without one a drawn disability
    pays none, and the table says so while the plan draws one."""
    day = date(2026, 1, 1)
    assert not any(n.item == "disability" for n in overview.attention(data, "base", day))
    with (data / "assumptions.yaml").open("a") as f:
        f.write("disability: {}\n")
    found = [n for n in overview.attention(data, "base", day) if n.item == "disability"]
    assert [(n.what, n.fix) for n in found] == [
        ("no pension from points, so a disability pays no EM-Rente", overview.CASHFLOWS)
    ]
    with (data / "cashflows.yaml").open("a") as f:
        f.write("  - {name: Rente, kind: pension, points: 10, point_value: 40}\n")
    assert not any(n.item == "disability" for n in overview.attention(data, "base", day))
    # a forced onset with no contributions behind it pays none either, and links to its place
    scenario = data / "scenarios" / "base.yaml"
    scenario.write_text(scenario.read_text() + "overrides: {disability: {at: 2027-06-01}}\n")
    (onset,) = [n for n in overview.attention(data, "base", day) if n.item == "disability"]
    assert onset.when == date(2027, 6, 1)
    assert onset.fix == overview.Link(
        "Scenarios", "base.yaml", {SCENARIO: "base", TAB: "Overrides"}
    )


@pytest.mark.parametrize(("plan", "paused"), [(1000, True), (300, False)])
def test_attention_names_a_savings_plan_that_pauses(
    tmp_path: Path, plan: float, paused: bool
) -> None:
    """The example of issue #20: a savings plan that the salary cannot pay pauses in the run of
    the files, in the month of the engine's marker, linked to the Cashflows page."""
    quick = datadir.Quick(date(1986, 5, 20), gross=5500, spending=3000, plan=plan)
    datadir.start_quick(tmp_path, quick)
    found = [
        n
        for n in overview.attention(tmp_path, datadir.SCENARIO, date.today())
        if n.item == datadir.NAMES["en"].savings
    ]
    assert [(n.what, n.fix) for n in found] == (
        [("pauses: the cash does not cover its rate", overview.CASHFLOWS)] if paused else []
    )
    assert all(n.when and n.when >= datadir.first_month() for n in found)


@pytest.mark.parametrize(
    ("kind", "query"),
    [
        ("sell", {"scenario": "early-exit", "event": "sell"}),  # the Events tab at the type
        (None, {"scenario": "early-exit", "tab": "Phases"}),  # a phase
    ],
)
def test_an_item_before_the_new_start_links_to_the_file_that_holds_it(
    kind: str | None, query: dict[str, str]
) -> None:
    item = rollforward.Passed("scenarios/early-exit.yaml", date(2026, 3, 1), "x", kind, ("a",))
    assert overview.fix(item) == overview.Link("Scenarios", "early-exit.yaml", query)


def test_the_overview_links_each_item_to_the_page_that_fixes_it(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The attention table and the roll forward, each row of its own (`st.table` takes no
    widget): a stale value to its row on the Assets page, an event before the new start to its
    type and a phase to the phases of its file on the Scenarios page, a loan without a date to its
    row."""
    with (data / "assets.yaml").open("a") as file:
        file.write("  - {id: bank, kind: loan, balance: -1000, rate: 0.02, annuity: 100}\n")
    (data / "scenarios" / "base.yaml").write_text(
        "name: base\n"
        "phases: [{from: 2026-01-01, phase: work}, {from: 2026-03-01, phase: alt}]\n"
        "events: [{at: 2026-02-01, type: lump_sum, amount: 100}]\n"
    )
    monkeypatch.setenv(DATA_ENV, str(data))
    pages = AppTest.from_file(MAIN, default_timeout=60).run().session_state[PAGES]
    at = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60)
    at.session_state[PAGES] = pages
    at.run()
    assert not at.exception
    assert {(link.proto.label, link.proto.query_string) for link in at.get("page_link")} == {
        ("Open Assets", "asset=giro&fields=value%2Casof"),
        ("Open Assets", "asset=depot&fields=value%2Casof"),
        ("Open Assets", "asset=bank&fields=balance%2Casof"),
        ("bank", "asset=bank&fields=balance%2Casof"),  # the roll takes its balance at the start
        ("base.yaml", "scenario=base&event=lump_sum"),
        ("base.yaml", "scenario=base&tab=Phases"),
        ("Data: fetch newer consumer prices", ""),  # the roll estimates the consumer prices
        ("Change the main scenario", "main=open"),  # the scenario of the outlook
        ("Explore scenarios", ""),  # no record yet: the plan needs none
        ("Cashflows: where the money goes", ""),  # the end of the page
    }
