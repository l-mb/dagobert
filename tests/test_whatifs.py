"""The what-ifs on a quick start: what each writes in one revision, why its answers do not fit
the plan, the run that it gives, and the dialogs of the Scenarios page."""

from __future__ import annotations

from datetime import date
from functools import partial
from typing import TYPE_CHECKING

import numpy as np
import pytest
from builders import QUICK, booked, fixed_run
from streamlit.testing.v1 import AppTest

from dagobert import datadir, references, revisions, scenariofiles, whatifs
from dagobert.budget import regular_salary
from dagobert.loader import APP, load_plan, read_yaml
from dagobert.model.events import BuyPropertyEvent, SetStreamEvent
from dagobert.model.months import add_months, aged, months_between
from dagobert.model.plan import Feature
from dagobert.model.taxes import Land
from dagobert.result import SOURCE
from dagobert.scenariofiles import act, created
from dagobert.ui import SAVED, Saved, at_age, guard
from dagobert.ui.fileactions import listing

if TYPE_CHECKING:
    from pathlib import Path

BORN = QUICK.born
START = datadir.first_month()
LATER = add_months(START, 12)  # a month of work, a year after the start
STOP = aged(BORN, 67)  # the quick start stops working at 67
LIVING = datadir.NAMES["en"].living[0]  # the spending of the quick start, 2500 a month


def written(data: Path, step: whatifs.Step) -> None:
    act(data, step.edits, source=f"test {step.stem}")


def months_in(run_phases: list[str], phase: str) -> int:
    return sum(p == phase for p in run_phases)


@pytest.mark.parametrize(
    ("listed", "off", "app"),
    [
        ([], ["job_loss", "care"], {"scenarios": ["plan", "new"], "features_off": ["care"]}),
        (["plan", "x"], ["job_loss"], {"scenarios": ["plan", "x", "new"]}),
        # a list that lacks the main one: the new one must not become the main one
        (["x"], [], {"scenarios": ["plan", "x", "new"], "features_off": []}),
    ],
)
def test_a_what_if_joins_the_comparison_after_the_main_one(
    quick: Path, listed: list[str], off: list[str], app: dict[str, object]
) -> None:
    (quick / APP).write_text(f"scenarios: {listed}\nfeatures_off: {off}\n")
    edit = scenariofiles.compared(quick, "plan", "new", (Feature.JOB_LOSS,))
    (quick / APP).write_text(edit.onto((quick / APP).read_text()) or "")
    assert read_yaml(quick / APP) == app


@pytest.mark.parametrize("own", [0, -12])
def test_stopping_earlier_moves_the_change_out_of_work(quick: Path, own: int) -> None:
    """The child's shift replaces the main one's: it counts from the month of the file."""
    if own:
        main = quick / "scenarios" / "plan.yaml"
        main.write_text(f"{main.read_text()}overrides: {{shift: {{retired: {own}}}}}\n")
    written(quick, whatifs.Earlier("plan", 60, "Stop at 60", "stop-at-60"))
    early = load_plan(quick, quick / "scenarios" / "stop-at-60.yaml").scenario
    assert early.phase_at(add_months(aged(BORN, 60), -1)) == "work"
    assert early.phase_at(aged(BORN, 60)) == "retired"
    worked = months_in(fixed_run(quick, "plan").phases, "work")
    assert worked - months_in(fixed_run(quick, "stop-at-60").phases, "work") == months_between(
        aged(BORN, 60), add_months(STOP, own)
    )


@pytest.mark.parametrize(
    ("age", "misfit"),
    [
        (66, None),
        (67, "type an age below 67"),
        (datadir.youngest(BORN) - 1, f"type an age from {datadir.youngest(BORN)} on"),
    ],
)
def test_stop_earlier_takes_an_age_between_the_start_and_the_stop(
    quick: Path, age: int, misfit: str | None
) -> None:
    found = whatifs.Earlier("plan", age, "Early", "early").misfits(quick)
    assert (misfit is None) == (not found)
    assert misfit is None or found["age"].startswith(misfit)


def test_stop_earlier_lists_the_months_of_the_stop_in_words(quick: Path) -> None:
    """The save guard says the shift by the month and the age before and after it, as the work
    slider of the Explorer: never as `shift retired -60`."""
    step = whatifs.Earlier("plan", 60, "Stop at 60", "stop-at-60")
    assert step.months(quick) == (STOP, aged(BORN, 60))
    stop, early = at_age(STOP, BORN), at_age(aged(BORN, 60), BORN)
    line = guard.Change("stop working", stop, early, unit=None)
    found, _gone = listing(
        step.edits(quick),
        partial(references.read, quick),
        lines={("scenarios/stop-at-60.yaml", ("overrides",)): line},
    )
    assert line in found
    assert not any("shift" in str(c.new) for c in found)
    assert stop.endswith("(age 67)")
    assert early.endswith("(age 60)")


def test_stop_earlier_says_why_a_plan_has_no_change_out_of_work(quick: Path) -> None:
    (quick / "scenarios" / "plan.yaml").write_text(
        f"name: Plan\nphases: [{{from: {START}, phase: work}}]\n"
    )
    assert whatifs.ages(quick, "plan") is None
    assert "no change out of it" in whatifs.Earlier("plan", 60, "x", "x").misfits(quick)["age"]


@pytest.mark.parametrize(
    ("lost", "back", "salaried", "misfits"),
    [
        (LATER, None, True, {}),
        (add_months(START, -1), None, True, {"lost": f"type a month from {START:%Y-%m} on"}),
        (STOP, None, True, {"lost": f"type a month before you stop working in {STOP:%Y-%m}"}),
        (LATER, None, False, {"lost": whatifs.UNPAID}),
        (LATER, LATER, True, {"back": whatifs.NEW_JOB_EARLY}),
    ],
)
def test_a_job_loss_fits_a_month_of_work_with_a_salary(
    quick: Path, lost: date, back: date | None, salaried: bool, misfits: dict[str, str]
) -> None:
    if not salaried:
        (quick / "cashflows.yaml").write_text("streams: []\n")
    loss = whatifs.Loss("plan", lost, back, "Lost", "lost", "Unemployed")
    assert loss.misfits(quick) == misfits


def test_a_course_after_a_job_loss_pays_alg1_and_returns_to_work(quick: Path) -> None:
    """Unemployed in its months, ALG1 under its row with `training` beside the ALG1 row, back to
    work after it; its costs an expense that deducts as work expenses."""
    written(quick, whatifs.Course("plan", LATER, 6, 0, True, "Course", "course"))
    written(quick, whatifs.Course("plan", LATER, 6, 3000, True, "Paid course", "paid"))
    free, paid = fixed_run(quick, "course"), fixed_run(quick, "paid")
    i = months_between(free.months[0], LATER)
    assert free.phases[i - 1 : i + 7] == ["work", *["unemployed"] * 6, "work"]
    assert (booked(free, "ALG1", SOURCE)[i : i + 6] > 0).all()
    assert "work" in regular_salary(free)
    course = next(e for e in load_plan(quick, quick / "scenarios" / "paid.yaml").scenario.events)
    assert course.type == "add_stream"
    year = slice(i - LATER.month + 1, i - LATER.month + 13)  # the calendar year of the course
    assert paid.expenses[0, year].sum() < free.expenses[0, year].sum()
    assert paid.taxes[0, year].sum() > free.taxes[0, year].sum()  # less tax: the costs deduct
    assert Feature.DEDUCTIONS not in read_yaml(quick / APP)["features_off"]


@pytest.mark.parametrize(("cost", "months"), [(1000, 3), (3000, 6), (0.05, 2), (99.99, 7)])
def test_the_costs_of_a_course_add_up_to_the_cent(cost: float, months: int) -> None:
    """Whole cents a month, the cents that do not divide in the last month."""
    course = whatifs.Course("plan", LATER, months, cost, False, "Course", "course")
    rows = [(e["at"], e["stream"]) for e in course.costs()]
    paid = [round(-row["amount"] * 100) * months_between(at, row["end"]) for at, row in rows]
    assert sum(paid) == round(cost * 100)
    assert rows[-1][1]["end"] == course.end
    assert len(rows) == (1 if round(cost * 100) % months == 0 else 2)


def test_a_course_in_a_break_pays_nothing_and_returns_to_work(quick: Path) -> None:
    """Costs that do not divide into whole cents run as two rows of one name: each month of the
    course pays them."""
    written(quick, whatifs.Course("plan", LATER, 6, 0, False, "Break", "break"))
    written(quick, whatifs.Course("plan", LATER, 3, 1000, False, "Paid break", "paid"))
    run, paid = fixed_run(quick, "break"), fixed_run(quick, "paid")
    i = months_between(run.months[0], LATER)
    assert run.phases[i - 1 : i + 7] == ["work", *["alt"] * 6, "work"]
    assert not booked(run, "ALG1", SOURCE).any()
    assert len(load_plan(quick, quick / "scenarios" / "paid.yaml").scenario.events) == 2
    course = run.expenses[0, i : i + 4] - paid.expenses[0, i : i + 4]  # money out below zero
    assert (course[:3] > 1000 / 3).all()
    assert course[3] == pytest.approx(0)


def test_a_business_replaces_the_salary_until_the_plan_stops_working(quick: Path) -> None:
    written(quick, whatifs.Business("plan", LATER, 6000, "Business", "business"))
    run = fixed_run(quick, "business")
    assert regular_salary(run).keys() == {"work", whatifs.BUSINESS}
    assert months_in(run.phases, whatifs.BUSINESS) == months_between(LATER, STOP)
    assert Feature.SELF_EMPLOYMENT not in read_yaml(quick / APP)["features_off"]
    assert whatifs.Business("plan", STOP, 1, "x", "x").misfits(quick) == {
        "start": f"type a month before you stop working in {STOP:%Y-%m}"
    }


@pytest.mark.parametrize("own", [100000, None])  # None: all of the cost
def test_a_purchase_borrows_what_the_own_funds_leave(quick: Path, own: float | None) -> None:
    cost = whatifs.Purchase("plan", LATER, 400000, 0, Land.NI, "Home", "home").cost
    step = whatifs.Purchase("plan", LATER, 400000, own or cost, Land.NI, "Home", "home")
    written(quick, step)
    plan = load_plan(quick, quick / "scenarios" / "home.yaml")
    bought = next(e for e in plan.scenario.events if isinstance(e, BuyPropertyEvent))
    assert bought.cost == pytest.approx(step.cost)
    assert (bought.loan is not None) == bool(own)
    if bought.loan is not None:
        assert -bought.loan.balance == pytest.approx(cost - step.own)
        assert bought.loan.annuity == pytest.approx(datadir.payment(cost - step.own), abs=0.01)
    run = fixed_run(quick, "home")
    i = months_between(run.months[0], LATER)
    assert run.balance["property"][i] > 0 == run.balance["property"][i - 1]
    assert Feature.PROPERTY not in read_yaml(quick / APP)["features_off"]


def test_a_purchase_ends_the_rent_as_a_set_stream_does(quick: Path) -> None:
    """The rent comes off the living costs from the month of the purchase: the run equals that of
    the purchase without it and a `set_stream` written by hand."""
    assert whatifs.spending(quick, "plan", LATER) == {LIVING: 2500}
    assert whatifs.living(whatifs.spending(quick, "plan", LATER)) == LIVING
    step = whatifs.Purchase("plan", LATER, 400000, 100000, Land.NI, "Rent", "rent", 1000, LIVING)
    written(quick, step)
    ended = next(
        e
        for e in load_plan(quick, quick / "scenarios" / "rent.yaml").scenario.events
        if isinstance(e, SetStreamEvent)
    )
    assert (ended.at, ended.name, ended.amount) == (LATER, LIVING, -1500)
    event = read_yaml(quick / "scenarios" / "rent.yaml")["events"][0]
    by_hand = {"at": LATER, "type": "set_stream", "name": LIVING, "amount": -1500}
    act(quick, lambda d: created(d, "hand", "Hand", "plan", events=[event, by_hand]), source="t")
    rent, hand = fixed_run(quick, "rent"), fixed_run(quick, "hand")
    for got, want in [(rent.expenses, hand.expenses), (rent.taxes, hand.taxes)]:
        np.testing.assert_array_equal(got, want)
    np.testing.assert_array_equal(rent.balance["cash"], hand.balance["cash"])
    i = months_between(rent.months[0], LATER)
    assert rent.expenses[0, i] < rent.expenses[0, i - 1]
    kept = whatifs.Purchase("plan", LATER, 400000, 0, Land.NI, "Kept", "kept").edits(quick)
    assert [e["type"] for e in kept[0].values["events",]] == ["buy_property"]


def test_a_rent_comes_off_the_spending_that_runs_then(quick: Path) -> None:
    """A monthly expense that runs in the month, at the amount of the last `set_stream` of the
    main scenario up to then; no health premium, no deduction, none that ended. The living costs
    by default, else the largest."""
    flows = quick / "cashflows.yaml"
    flows.write_text(
        f"{flows.read_text()}"
        "  - {name: Rent, amount: -1200}\n"
        f"  - {{name: Old rent, amount: -900, end: {LATER}}}\n"
        "  - {name: Donation, amount: -50, deduct: donation}\n"
        "  - {name: Insurance, amount: -300, every: 12}\n"
    )
    main = quick / "scenarios" / "plan.yaml"
    main.write_text(
        f"{main.read_text()}events:\n"
        f"  - {{at: {START}, type: set_stream, name: Rent, amount: -1300}}\n"
        f"  - {{at: {add_months(LATER, 1)}, type: set_stream, name: Rent, amount: -1400}}\n"
    )
    held = whatifs.spending(quick, "plan", LATER)
    assert held == {LIVING: 2500, "Rent": 1300}
    assert whatifs.living(held) == LIVING
    assert whatifs.living({"Rent": 1300, "Food": 400}) == "Rent"
    assert not whatifs.living({})


@pytest.mark.parametrize(
    ("rent", "stream", "misfit"),
    [
        (2500, LIVING, None),  # all of it
        (2600, LIVING, f"type at most the amount of {LIVING}, 2.500 € a month"),
        (100, "", whatifs.NO_SPENDING),
        (0, "", None),
    ],
)
def test_the_rent_of_a_purchase_fits_the_spending(
    quick: Path, rent: float, stream: str, misfit: str | None
) -> None:
    step = whatifs.Purchase("plan", LATER, 400000, 0, Land.NI, "x", "x", rent, stream)
    assert step.misfits(quick).get("rent") == misfit


@pytest.mark.parametrize(
    ("land", "misfits"),
    [
        (Land.BE, {"own": "type at most the price with tax and costs, 111.000 €"}),
        # without a Land the own funds show at once, against the highest Grunderwerbsteuer
        (
            None,
            {
                "own": "type at most the price with the highest Grunderwerbsteuer and costs, "
                "111.500 €",
                "land": whatifs.NO_LAND,
            },
        ),
    ],
)
def test_a_purchase_takes_no_more_own_funds_than_its_cost(
    quick: Path, land: Land | None, misfits: dict[str, str]
) -> None:
    over = whatifs.Purchase("plan", LATER, 100000, 200000, land, "x", "x")
    assert over.misfits(quick) == misfits


PAGE = """
from pathlib import Path
from dagobert.ui import scenarios
scenarios.page(Path({data!r}))
"""


def typed_in(data: Path, step: str, typed: dict[str, object], *, phone: bool = False) -> AppTest:
    """The dialog of `step` with the fields `typed` by their keys. `AppTest` draws a dialog only
    in the run of the click of its button: the fields come through the session state."""
    at = AppTest.from_string(PAGE.format(data=str(data)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    next(b for b in at.button if b.key == f"whatif-scenarios-{step}").click().run()
    assert not at.exception
    for key, value in typed.items():
        at.session_state[key if key.startswith("whatif-") else f"decimal-whatif-{key}"] = value
    next(b for b in at.button if b.key == f"whatif-scenarios-{step}").click().run()
    assert not at.exception
    return at


@pytest.mark.parametrize(
    ("step", "typed"),
    [
        ("stop", {"age": "60"}),
        ("job-loss", {"lost": f"{LATER:%Y-%m}", "back": f"{add_months(LATER, 6):%Y-%m}"}),
        ("course", {}),  # its defaults
        ("business", {}),
        (
            "property",
            {"price": "400000", "own": "100000", "rent": "1000", "whatif-property-land": Land.NI},
        ),
    ],
)
@pytest.mark.parametrize("phone", [False, True])
def test_a_what_if_dialog_writes_one_revision(
    quick: Path, step: str, typed: dict[str, object], phone: bool
) -> None:
    """The confirm comes with the click of the button of the dialog. The guard lists no key of
    the files where a step words a value (`Stop earlier`). The new scenario comes last in the
    comparison."""
    at = typed_in(quick, step, typed, phone=phone)
    assert not at.error, [e.value for e in at.error]
    listed = next(c.value for c in at.caption if "→" in c.value)
    assert "shift" not in listed
    assert step != "stop" or "(age 60)" in listed
    next(b for b in at.button if b.key == f"whatif-scenarios-{step}").click()
    next(b for b in at.button if b.key == "scenarios-confirm").click().run()
    assert not at.exception
    last = revisions.entries(quick)[-1]
    stem = read_yaml(quick / APP)["scenarios"][-1]
    assert last.source == f"app: what-if {stem}"
    assert {APP, f"scenarios/{stem}.yaml"} <= set(last.files)
    assert at.session_state[SAVED] == Saved(last.id)  # its undo: a dialog runs without `main.py`
    assert load_plan(quick, quick / "scenarios" / f"{stem}.yaml").scenario.name


def test_the_purchase_dialog_marks_the_land_and_the_own_funds_at_once(quick: Path) -> None:
    """Without a Land the own funds show against the highest cost; with two expenses a select
    names the one that the rent comes off, the living costs first."""
    flows = quick / "cashflows.yaml"
    flows.write_text(f"{flows.read_text()}  - {{name: Rent, amount: -1200}}\n")
    at = typed_in(quick, "property", {"price": "100000", "own": "200000", "rent": "3000"})
    assert at.selectbox(key="whatif-property-stream").value == LIVING
    errors = [e.value for e in at.error]
    assert whatifs.NO_LAND in errors
    assert any(e.startswith("type at most the price with the highest") for e in errors)
    assert any(e.startswith(f"type at most the amount of {LIVING}") for e in errors)
