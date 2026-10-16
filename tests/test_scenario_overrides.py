"""The overrides of a scenario file: the parts of its tab as one mapping, the rows by id read in
the unit of their field, the salary in euros, the live check, and the tab as a desktop and as a
phone with its save."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from builders import PHASE_LABELS
from streamlit.testing.v1 import AppTest

from dagobert import references, revisions, store
from dagobert.loader import chain, load_plan, read_yaml
from dagobert.store import Edit, RowEdits
from dagobert.ui import fields, forms
from dagobert.ui.assumptions import LABELS, TABS, TAX_YEAR
from dagobert.ui.overridegrids import OWN, ById, Here, edited, moved, text
from dagobert.ui.scenario_overrides import GROWTH, SALARY, changes, scale_form, trial

if TYPE_CHECKING:
    from pathlib import Path

STREAMS = """\
streams:
  - name: Salary
    kind: salary
    gross: 5000
    phases: [work]
  - name: Rent
    cat: housing
    amount: -1200
"""
ASSETS = """\
assets:
  - id: giro
    kind: cash
    value: 1000
  - id: flat
    kind: property
    sqm: 50
    per_sqm: 4000
  - id: avd
    kind: av_depot
    value: 0
    contribution: 600
    start: 2027-01-01
"""
BASE = """\
name: Base
phases:
  - {from: 2026-01-01, phase: work}
  - {from: 2040-01-01, phase: retired, id: retirement}
events:
  - {at: 2030-01-01, type: lump_sum, amount: -20000, id: car}
  - {at: 2032-01-01, type: sell, asset: flat, costs: 0.05, id: flat-sale}
overrides:
  refinance_rate: 0.05
  shift: {car: 12}
"""
CHILD = """\
name: Child
extends: base
overrides:
  # the same rate as the parent: it holds when the parent changes
  refinance_rate: 0.05
  events:
    flat-sale: {price: 180000}
"""


@pytest.fixture
def plans(data: Path) -> Path:
    (data / "cashflows.yaml").write_text(STREAMS)
    (data / "assets.yaml").write_text(ASSETS)
    (data / "scenarios" / "base.yaml").write_text(BASE)
    (data / "scenarios" / "child.yaml").write_text(CHILD)
    return data


CATEGORY = ("scale", "categories", "housing")


def _here(data: Path, stem: str = "child") -> Here:
    path = data / "scenarios" / f"{stem}.yaml"
    return Here(path, chain(path), references.of(data))


def _specs(data: Path) -> dict[str, ById]:
    return {spec.key: spec for spec in _here(data).specs()}


def _shown(data: Path, form: forms.Form, found: dict[tuple[str, ...], Any]) -> forms.Shown:
    """A form whose widgets typed `found`, as `forms.show` returns it."""
    part = form.part(read_yaml(data / form.file))
    return forms.Shown(data, form, forms.Base(part, None), forms.Typed({}, {}, {}), found, False)


def test_the_parts_write_one_mapping_of_overrides(plans: Path) -> None:
    """A field of the assumptions, the scale (the salary typed in euros, kept as the factor), a
    moved date, a field of an event and a field of an asset: one edit of the file."""
    file, specs = "scenarios/child.yaml", _specs(plans)
    markets = TABS[1].form(file=file, keys=OWN, override=True, key="test")
    scale = scale_form(file, "child", {"work": 5000.0}, [], PHASE_LABELS)
    rows = {
        "shift": RowEdits(added=[{"id": "retirement", "months": 6}]),
        "events": RowEdits(edited={0: {"value": "175.000,50 €"}}),
        "assets": RowEdits(added=[{"asset": "avd", "field": "contribution", "value": "1.200"}]),
    }
    held = read_yaml(plans / file)["overrides"]
    grids: dict[tuple[str, ...], Any] = {}
    for key, typed in rows.items():
        found, unread = edited(specs[key], held.get(key, {}), typed)
        assert not unread
        grids |= found
    written = [
        _shown(plans, markets, {("inflation", "mean"): 0.025}).edit(),
        _shown(
            plans, scale, {(*SALARY, "work"): 5500, (*GROWTH, "work"): 0.02, CATEGORY: 0.9}
        ).edit(),
        Edit(file, {(*OWN, *path): v for path, v in grids.items()}),
    ]
    store.write(plans, forms.merged(written), source="test")
    assert read_yaml(plans / file)["overrides"] == {
        "refinance_rate": 0.05,  # set equal to the inherited one, it stays
        "events": {"flat-sale": {"price": 175000.5}},
        "inflation": {"mean": 0.025},
        "scale": {
            "salary": {"work": 1.1},
            "growth": {"work": 0.02},
            "categories": {"housing": 0.9},
        },
        "shift": {"retirement": 6},
        "assets": {"avd": {"contribution": 1200}},
    }
    assert (
        "  # the same rate as the parent: it holds when the parent changes\n"
        in (plans / file).read_text()
    )
    plan = load_plan(plans, plans / file)
    assert plan.assumptions.scale.salary == {"work": 1.1}
    assert plan.scenario.phases[-1].at.year == 2040 and plan.scenario.phases[-1].at.month == 7


HELD: dict[str, dict[str, Any]] = {"events": {"flat-sale": {"price": 180000}}, "shift": {"car": 12}}


@pytest.mark.parametrize(
    ("key", "edits", "changes"),
    [
        # a value in the unit of its field: a share in percent, a month
        (
            "events",
            RowEdits(added=[{"id": "flat-sale", "field": "costs", "value": "7"}]),
            {("events", "flat-sale", "costs"): 0.07},
        ),
        (
            "events",
            RowEdits(added=[{"id": "car", "field": "at", "value": "2031-05"}]),
            {("events", "car", "at"): date(2031, 5, 1)},
        ),
        # an emptied value or a deleted row inherits again
        ("events", RowEdits(edited={0: {"value": None}}), {("events", "flat-sale", "price"): None}),
        ("events", RowEdits(deleted=[0]), {("events", "flat-sale", "price"): None}),
        # a row that the edits keep is no change, also when its text shows fewer cents
        ("events", RowEdits(edited={0: {"value": "180.000 €"}}), {}),
        # another id takes the value along
        (
            "events",
            RowEdits(edited={0: {"id": "car"}}),
            {("events", "flat-sale", "price"): None, ("events", "car", "price"): 180000},
        ),
        ("shift", RowEdits(edited={0: {"months": -3}}), {("shift", "car"): -3}),
    ],
)
def test_a_row_reads_in_the_unit_of_its_field(
    plans: Path, key: str, edits: RowEdits, changes: dict[tuple[str, ...], Any]
) -> None:
    assert edited(_specs(plans)[key], HELD[key], edits) == (changes, {})


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ({"id": "flat-sale", "field": "price", "value": "a lot"}, "type euros, such as 1.234,56"),
        ({"id": "flat-sale", "value": "5"}, "needs field"),  # a row in the making saves nothing
        ({"id": "flat-sale", "field": "price"}, "needs value"),
    ],
)
def test_a_row_that_does_not_read_keeps_save_off(
    plans: Path, row: dict[str, Any], problem: str
) -> None:
    found, unread = edited(_specs(plans)["events"], {}, RowEdits(added=[row]))
    assert found == {}
    assert [p.startswith(problem) for p in unread.values()] == [True]


def test_a_row_shows_its_value_in_the_unit_of_its_field(plans: Path) -> None:
    spec = _specs(plans)["events"]
    held = {"flat-sale": {"price": 180000, "costs": 0.07, "at": "2033-01-01"}}
    assert [row["value"] for row in spec.shown(held)] == ["180.000 €", "7%", "2033-01-01"]
    assert text(None, {"age": 70}) == "{age: 70}"  # a field that no event of the id takes


def test_a_category_factor_reads_in_percent_without_the_cap_of_a_share(plans: Path) -> None:
    """As on the explorer's slider: 120 spends a fifth more, no share above 100%."""
    form = scale_form("scenarios/child.yaml", "child", {}, [], PHASE_LABELS)
    column = next(f for f in form.fields if f.path == CATEGORY[:2]).columns[0]
    assert column.stored(120) == 1.2
    found = changes(_shown(plans, form, {CATEGORY: 1.2}))
    assert [(c.text, c.warning) for c in found] == [
        ("**scale categories housing** empty → 120%", None)
    ]


def test_all_spending_reads_in_percent_and_keeps_its_factor(plans: Path) -> None:
    form = scale_form("scenarios/child.yaml", "child", {}, [], PHASE_LABELS)
    field = next(f for f in form.fields if f.path == ("scale", "spending"))
    assert form.label(field) == "All spending"
    assert fields.parse(field, "75") == 0.75  # 90 would be a factor of 90 otherwise
    found = changes(_shown(plans, form, {("scale", "spending"): 0.75}))
    assert [(c.text, c.warning) for c in found] == [("**scale spending** empty → 75%", None)]


def test_the_salary_shows_in_euros_and_keeps_its_factor(plans: Path) -> None:
    form = scale_form("scenarios/child.yaml", "child", {"work": 4000.0}, [], PHASE_LABELS)
    doc = {"overrides": {"scale": {"salary": {"work": 1.05, "alt": 0.5}}}}
    assert form.mapping(doc)["scale"]["salary"] == {"work": 4200.0, "alt": 0.5}
    assert form.stored(("scale", "salary", "work"), 4400) == 1.1
    assert form.stored(("scale", "salary", "alt"), 0.4) == 0.4  # no gross: the factor
    labels = {f.path: form.label(f) for f in form.fields}
    assert labels[(*SALARY, "work")] == "Salary and profit in Work €"
    assert (*SALARY, "retired") not in labels  # no salary, no factor held
    # the growth of a phase with pay in percent, empty at 0; of a phase without pay as the chain
    # holds it
    assert labels[(*GROWTH, "work")] == "Raises in Work %"
    assert form.leaves(plans, {})[(*GROWTH, "work")].value == 0
    assert form.stored((*GROWTH, "work"), 0.02) == 0.02
    assert (*GROWTH, "retired") not in labels
    held = scale_form(
        "scenarios/child.yaml", "child", {"work": 4000.0}, [(*GROWTH, "retired")], PHASE_LABELS
    )
    assert {f.path for f in held.fields} - {f.path for f in form.fields} == {(*GROWTH, "retired")}


def test_a_phase_label_with_braces_shows_as_written() -> None:
    """The help of a field is a message that `said` formats: a label of the user stays as is."""
    phases = PHASE_LABELS | {"work": "Teil{x}"}
    form = scale_form("scenarios/child.yaml", "child", {"work": 4000.0}, [], phases)
    work = next(f for f in form.fields if f.path == ("scale", "salary", "work"))
    assert form.shown(work).help.startswith("A usual month in `Teil{x}` pays 4.000 €")
    assert form.label(work) == "Salary and profit in Teil{x} €"


def test_the_live_check_names_what_an_edit_breaks(plans: Path) -> None:
    file = "scenarios/base.yaml"
    wrong = Edit(file, {("overrides", "events", "car", "price"): 5})
    found = trial(plans, wrong, ["base", "child"])
    assert {(p.file, p.path, p.message) for p in found} == {
        (file, "overrides.events.car.price", "no event of this id has this field")
    }
    assert trial(plans, Edit(file, {("overrides", "shift", "car"): 3}), ["base", "child"]) == []


def test_a_moved_group_shows_its_months(plans: Path) -> None:
    shift = {"car": (12, "base"), "retirement": (-6, ""), "gone": (3, "")}
    assert moved(_here(plans).chain, shift) == [
        "car 2030-01 → 2031-01 (from base)",
        "retirement 2040-01 → 2039-07",
    ]


def test_the_givers_of_a_gift_are_no_month_of_its_group(plans: Path) -> None:
    """`from` is the month of a phase but the givers of a gift: the group starts at the phase."""
    raw = {
        "phases": [{"from": date(2031, 6, 1), "phase": "x", "id": "trip"}],
        "events": [{"at": date(2028, 2, 1), "type": "gift", "from": "mother", "id": "trip"}],
    }
    assert moved([(plans / "x.yaml", raw)], {"trip": (3, "")}) == ["trip 2028-02 → 2028-05"]


def test_the_default_tax_year_follows_the_start_that_the_scenario_runs(plans: Path) -> None:
    """The placeholder of `tax.year` names the merged `start` and the file that sets it."""
    form = next(t for t in TABS if t.key == "tax").form(file="scenarios/child.yaml", override=True)
    assert form.leaves(plans, {})[TAX_YEAR].source != "base"
    base = plans / "scenarios" / "base.yaml"
    base.write_text(base.read_text() + "  start: 2027-03-01\n")
    assert form.leaves(plans, {})[TAX_YEAR].source == "base"


HARNESS = """
from pathlib import Path
from dagobert.ui import scenario_overrides
scenario_overrides.tab(Path({path!r}))
"""


def _tab(data: Path, stem: str, *, phone: bool = False, mode: str | None = None) -> AppTest:
    path = data / "scenarios" / f"{stem}.yaml"
    at = AppTest.from_string(HARNESS.format(path=str(path)), default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    if mode:
        at.query_params["mode"] = mode
    return at.run()


def test_simple_mode_shows_the_fields_that_a_scenario_or_the_plan_sets(plans: Path) -> None:
    """The same predicate as the Assumptions page: the loan rate that the scenarios set shows, a
    part without a field to show does not (`Rules`), and a note names what is hidden."""
    at = _tab(plans, "child", mode="simple")
    assert not at.exception
    parts = [e.label for e in at.expander if not e.icon]
    assert parts[:4] == ["Person", "Markets (1)", "Tax", "Scale"]
    labels = {w.label for w in at.text_input}
    assert LABELS[("refinance_rate",)] in labels
    assert LABELS[("pension_growth",)] not in labels
    assert any(
        c.value.startswith(
            "Hidden in simple mode (inherited from the files it extends): Cash buffer (months),"
        )
        for c in at.caption
    )


@pytest.mark.parametrize("phone", [False, True])
def test_the_tab_renders_the_parts_and_pins_the_ids_on_a_phone(plans: Path, phone: bool) -> None:
    at = _tab(plans, "child", phone=phone)
    assert not at.exception
    assert [e.label for e in at.expander if not e.icon] == [  # the parts, not the help folds
        "Person",
        "Markets (1)",
        "Rules",
        "Tax",
        "Scale",
        "Dates",
        "Event fields (1)",
        "Assets",
    ]
    pinned = {
        name
        for grid in at.dataframe
        for name, column in json.loads(grid.proto.columns).items()
        if column.get("pinned")
    }
    # the grids by id, the classes of `returns` that it inherits
    assert pinned == ({"id", "asset", "name"} if phone else set())
    rate = next(w for w in at.text_input if w.label == LABELS[("refinance_rate",)])
    assert (rate.value, rate.placeholder) == ("5", "5 from base")
    salary = next(w for w in at.text_input if w.label == "Salary and profit in Work €")
    assert salary.placeholder.endswith(" from cashflows.yaml")
    assert any("car 2030-01 → 2031-01 (from base)" in c.value for c in at.caption)


@pytest.mark.parametrize(("stem", "where"), [("base", "in this file"), ("child", "from base")])
def test_an_overridden_start_shows_read_only(plans: Path, stem: str, where: str) -> None:
    base = plans / "scenarios" / "base.yaml"
    base.write_text(base.read_text() + "  start: 2026-11-01\n")
    at = _tab(plans, stem)
    assert not at.exception
    assert any(f"Start overridden: 2026-11, {where}." in c.value for c in at.caption)


def test_a_save_writes_the_overrides_as_one_revision(plans: Path) -> None:
    """The rate equal to the inherited one stays; the salary typed in euros goes as its factor."""
    at = _tab(plans, "child")
    assert all(b.disabled for b in at.button if b.label.startswith("Save"))  # nothing typed
    next(w for w in at.text_input if w.label == LABELS[("pension_growth",)]).input("1,5").run()
    next(w for w in at.text_input if w.label == "Salary and profit in Work €").input("6.000").run()
    assert any("**scale salary work** " in c.value for c in at.caption)  # in euros
    next(b for b in at.button if b.label.startswith("Save")).click().run()
    assert not at.exception
    path = plans / "scenarios" / "child.yaml"
    held = read_yaml(path)["overrides"]
    assert held["refinance_rate"] == 0.05
    assert held["pension_growth"] == 0.015
    gross = held["scale"]["salary"]["work"]
    usual = next(w for w in at.text_input if w.label == "Salary and profit in Work €")
    assert usual.value == "6.000"  # the factor times the gross of the run
    assert 1.1 < gross < 1.3
    assert revisions.entries(plans)[-1].source == "app: child"
