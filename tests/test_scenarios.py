"""The Scenarios page: its pure parts and a render with a file action that it refuses."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from operator import itemgetter
from typing import TYPE_CHECKING, Any

import pytest
from builders import fixed_run
from german import edited
from streamlit.testing.v1 import AppTest

from dagobert import loader, references, revisions, scenariofiles, store
from dagobert.budget import ledger, regular_salary
from dagobert.loader import APP, chain, load_scenario, read_yaml
from dagobert.model.base import KeyPath
from dagobert.model.plan import Scenario
from dagobert.problems import InputError
from dagobert.scenariofiles import act, copied, removed, renamed
from dagobert.store import RowEdits
from dagobert.ui import assumptions, forms, slug
from dagobert.ui.fileactions import Plan, followed, listing
from dagobert.ui.lineage import AT_DEATH, LEFT_OUT, ON_CONDITION, SET_IN, THIS, Inherited
from dagobert.ui.phases import Moving, moving, phase_ids, shifted, typed_moves
from dagobert.ui.scenarios import (
    FIELDS,
    LABELS,
    TABS,
    compare_label,
    label,
    opening,
    option,
    promoted,
    refusals,
    timeline,
    tree,
)

if TYPE_CHECKING:
    from pathlib import Path

PARENT = """\
name: Work to 65
phases:
  - {from: 2026-01-01, phase: work}
  - {from: 2050-01-01, phase: retired, id: retirement}
events:
  - {at: 2036-06-01, type: lump_sum, amount: 5000, id: bonus, note: A bonus}
  - {type: sell, asset: flat, when: {age: 78}, note: The flat at 78}
"""
CHILD = """\
name: Keep going
extends: base
drop: [bonus]
overrides:
  shift: {retirement: 24}
"""


@pytest.fixture
def family(data: Path) -> Path:
    (data / "assets.yaml").write_text(
        "assets:\n  - {id: flat, kind: property, sqm: 50, per_sqm: 3000}\n"
    )
    (data / "scenarios" / "base.yaml").write_text(PARENT)
    (data / "scenarios" / "child.yaml").write_text(CHILD)
    (data / APP).write_text("scenarios: [base, child]\n")
    return data


def test_the_tree_puts_each_scenario_below_its_parent() -> None:
    parents = {"stress": "plan", "plan": None, "Base": None, "keep": "plan", "lost": "gone"}
    parents |= {"a": "b", "b": "a"}  # a cycle still shows
    assert tree(parents) == [
        ("Base", 0),
        ("lost", 0),  # its parent is missing
        ("plan", 0),
        ("keep", 1),
        ("stress", 1),
        ("a", 0),
        ("b", 1),
    ]


@pytest.mark.parametrize(
    ("stem", "depth", "doc", "shown"),
    [
        ("plan", 0, {"name": "Work to 65"}, "plan · Work to 65"),
        ("keep", 1, {"name": "keep"}, "↳ keep"),
        ("deep", 2, {"name": "Deep", "abstract": True}, " ↳ deep · Deep (template)"),
    ],
)
def test_a_scenario_shows_its_stem_its_name_and_its_place(
    stem: str, depth: int, doc: dict[str, object], shown: str
) -> None:
    assert label(stem, depth, doc) == shown


@pytest.mark.parametrize(
    ("held", "new", "after"),
    [
        ("plan", "work", "work"),
        (["base", "plan"], "work", ["base", "work"]),
        (["base", "plan"], None, ["base"]),  # a delete
        ("plan", None, None),
        ("base", "work", "base"),
    ],
)
def test_the_selections_of_other_pages_follow_the_stem(
    held: object, new: str | None, after: object
) -> None:
    assert followed(held, "plan", new) == after


def test_a_file_action_lists_what_it_writes(family: Path) -> None:
    def read(name: str) -> dict[str, object]:
        return references.read(family, name)

    found, gone = listing(renamed(family, "base", "plan"), read)
    assert [c.text for c in found] == [
        "**file** scenarios/base.yaml → scenarios/plan.yaml",
        "**scenarios/child.yaml extends** base → plan",
        "**app.yaml scenarios\\[0\\]** base → plan",
    ]
    assert gone == []
    found, gone = listing(removed(family, "child"), read)
    assert [c.text for c in found] == ["**app.yaml scenarios\\[1\\]** child → empty"]
    assert gone == ["scenarios/child.yaml"]
    found, _ = listing(copied(family, "child", "again", "Again"), read)
    assert [c.text for c in found] == [
        "**scenarios/again.yaml** empty → copy of scenarios/child.yaml",
        "**scenarios/again.yaml name** Keep going → Again",
    ]


@pytest.mark.parametrize(
    ("candidate", "refused"),
    [
        ({"name": "Work to 65"}, ["base has the name Work to 65"]),
        ({"name": "Keep going", "abstract": True}, ["the last scenario that runs cannot be a"]),
        ({"name": "Keep going"}, []),
    ],
)
def test_the_general_fields_refuse_a_taken_name_and_the_last_template(
    candidate: dict[str, object], refused: list[str]
) -> None:
    docs: dict[str, dict[str, object]] = {
        "base": {"name": "Work to 65", "abstract": True},
        "child": {"name": "Keep going"},
    }
    found = refusals("child", candidate, docs)
    assert [text[: len(start)] for text, start in zip(found, refused, strict=True)] == refused


def test_the_timeline_shows_what_a_run_sees_and_marks_what_the_child_drops(
    family: Path,
) -> None:
    """A phase by its label, as the other pages show it; an inheritance without a month at death
    after the dated rows, the givers and the sum of a gift after its note."""
    child = family / "scenarios" / "child.yaml"
    child.write_text(
        f"{CHILD}events:\n  - {{at: 2030-01-01, type: lump_sum, amount: 900}}\n"
        "  - {type: inheritance, from: [mother, father], cash: 1000}\n"
        "  - {at: 2031-01-01, type: gift, from: mother, cash: 500, note: For the car}\n"
    )
    shown = itemgetter("month", "item", "detail", "id", SET_IN, LEFT_OUT)
    assert list(map(shown, timeline(family, child, references.phases(family)))) == [
        ("2026-01", "Phase", "Work", "", "base", ""),
        ("2030-01", "One-off payment", "", "", THIS, ""),  # the child's own event
        ("2031-01", "Gift", "For the car (mother: 500 €)", "", THIS, ""),
        ("2036-06", "One-off payment", "A bonus", "bonus", "base", "child"),  # dropped: not run
        ("2052-01", "Phase", "Retired", "retirement", "base", ""),  # moved by the child's shift
        (AT_DEATH, "Inheritance", "mother, father: 1.000 €", "", THIS, ""),
        (ON_CONDITION, "Sell an asset", "The flat at 78 (age 78)", "", "base", ""),  # last
    ]
    child.write_text(CHILD.replace("[bonus]", "[retirement]"))
    rows = timeline(family, child, references.phases(family))
    assert [(r["detail"], r["id"]) for r in rows if r[LEFT_OUT]] == [("Retired", "retirement")]


def test_the_timeline_words_a_dropped_gift_and_sale_as_the_rows_it_runs(family: Path) -> None:
    (family / "scenarios" / "base.yaml").write_text(
        PARENT
        + "  - {type: inheritance, from: mother, cash: 1000, id: estate}\n"
        + "  - {at: 2031-01-01, type: gift, from: mother, cash: 500, id: trip, note: Trip}\n"
        + "  - {type: sell, asset: flat, when: {liquid_below: 0}, id: flat-sale}\n"
    )
    child = family / "scenarios" / "child.yaml"
    child.write_text(CHILD.replace("[bonus]", "[estate, trip, flat-sale]"))
    shown = itemgetter("month", "item", "detail", "id")
    dropped = [shown(r) for r in timeline(family, child, {}) if r[LEFT_OUT]]
    assert dropped == [
        ("2031-01", "Gift", "Trip (mother: 500 €)", "trip"),
        (AT_DEATH, "Inheritance", "mother: 1.000 €", "estate"),
        (ON_CONDITION, "Sell an asset", "flat (liquid below 0 €)", "flat-sale"),
    ]


def test_the_phases_of_the_parents_name_their_file_and_who_drops_them(family: Path) -> None:
    """The month as the run sees it, moved by the shift of the child; a dropped one as written."""
    found = moving(chain(family / "scenarios" / "child.yaml"))
    assert [(r.phase, r.month, r.item.file, r.item.dropped) for r in found] == [
        ("work", date(2026, 1, 1), "base", None),
        ("retired", date(2052, 1, 1), "base", None),  # `shift: {retirement: 24}`
    ]
    (family / "scenarios" / "child.yaml").write_text(CHILD.replace("[bonus]", "[retirement]"))
    dropped = moving(chain(family / "scenarios" / "child.yaml"))[1]
    assert (dropped.month, dropped.item.dropped, dropped.movable) == (
        date(2050, 1, 1),
        "child",
        False,
    )
    # a timeline by month, whatever file holds a change
    (family / "scenarios" / "child.yaml").write_text(
        CHILD + "phases:\n  - {from: 2040-01-01, phase: alt, id: break}\n"
    )
    (family / "scenarios" / "grand.yaml").write_text("name: Grand\nextends: child\n")
    found = moving(chain(family / "scenarios" / "grand.yaml"))
    assert [(r.month, r.item.file) for r in found] == [
        (date(2026, 1, 1), "base"),
        (date(2040, 1, 1), "child"),
        (date(2052, 1, 1), "base"),
    ]


@pytest.mark.parametrize(
    ("name", "stem"),
    [("Früh in Rente!", "frueh-in-rente"), ("Work to 65", "work-to-65"), ("  ", "")],
)
def test_a_new_scenario_takes_its_file_name_from_its_name(name: str, stem: str) -> None:
    assert slug(name) == stem


PAGE = """
from pathlib import Path
from dagobert.ui import scenarios
scenarios.page(Path({data!r}))
"""


@pytest.mark.parametrize("phone", [False, True])
def test_the_page_opens_a_scenario_and_keeps_save_off_for_a_taken_name(
    family: Path, phone: bool
) -> None:
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.query_params["scenario"] = "child"  # the hand-off of another page
    at.run()
    assert not at.exception
    name = next(t for t in at.text_input if t.label == "Name")
    assert name.value == "Keep going"  # the child opened
    # a phone names the choice on a popover of pills: ten scenarios would fill the screen
    popovers = {p.proto.popover.label for p in at.get("popover")}
    assert ("child · Keep going" in popovers) == phone
    name.input("Work to 65").run()
    assert any("base has the name Work to 65" in w.value for w in at.warning)
    assert all(b.disabled for b in at.button if b.label.startswith("Save"))
    next(t for t in at.text_input if t.label == "Name").input("Fresh").run()
    assert not all(b.disabled for b in at.button if b.label.startswith("Save"))


def test_extends_is_off_where_no_scenario_can_be_the_parent(family: Path) -> None:
    """Every other scenario extends `base`: no field to type a parent that the check refuses."""
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params["scenario"] = "base"
    at.run()
    assert not at.exception
    extends = next(s for s in at.selectbox if s.label == "Extends")
    assert extends.disabled
    assert extends.proto.placeholder == "none: a scenario of its own"
    assert not any(t.label == "Extends" for t in at.text_input)


def _plan(at: AppTest) -> tuple[str, list[str]]:
    """The main scenario and the comparison that the page shows."""
    main = next(s for s in at.selectbox if s.label == "Main scenario")
    compare = next(m for m in at.multiselect if m.label == "Also compare in the Explorer")
    return str(main.value), list(compare.value)


def test_the_main_scenario_follows_a_rename(family: Path) -> None:
    """The choice starts anew: holding the old stem, one tap would drop the main scenario."""
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30).run()
    renaming = revisions.renaming("scenarios/base.yaml", "scenarios/plan.yaml")
    act(family, lambda d: renamed(d, "base", "plan"), source=f"Scenarios: {renaming}")
    at.run()
    assert not at.exception
    assert _plan(at) == ("plan", ["child"])
    assert not any("**scenarios**" in c.value for c in at.caption)  # nothing to save


@pytest.mark.parametrize("phone", [False, True])
def test_a_new_main_scenario_keeps_the_old_one_in_the_comparison(family: Path, phone: bool) -> None:
    """Above the scenario to edit, on a phone in an expander that names the main scenario. A new
    main scenario takes the old one into the comparison, which does not offer the main one; Save
    writes both as the one list of `app.yaml`, the main one first."""
    (family / "scenarios" / "solo.yaml").write_text(PARENT.replace("Work to 65", "Solo"))
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    assert not at.exception
    assert ("Main scenario: base · Work to 65" in [e.label for e in at.expander]) == phone
    assert _plan(at) == ("base", ["child"])
    next(s for s in at.selectbox if s.label == "Main scenario").select("solo").run()
    assert _plan(at) == ("solo", ["base", "child"])
    compare = next(m for m in at.multiselect if m.label == "Also compare in the Explorer")
    assert not [o for o in compare.options if o.startswith("solo")]
    at.button(key="scenarios-plan-save").click().run()
    assert not at.exception
    assert read_yaml(family / APP)["scenarios"] == ["solo", "base", "child"]
    assert revisions.entries(family)[-1].source == "app: main scenario"
    assert _plan(at) == ("solo", ["base", "child"])
    assert at.button(key="scenarios-plan-save").disabled  # saved: nothing to save


def test_a_choice_of_the_main_scenario_shows_the_start_of_each_note() -> None:
    note = "Sell the flat at 60 and move to the coast, then live on the rent of the garage."
    assert option("plan", {"name": "Work to 65", "note": note}) == (
        "plan · Work to 65 — Sell the flat at 60 and move to the coast, then live on …"
    )
    assert option("plan", {"name": "Work to 65", "note": " "}) == "plan · Work to 65"


@pytest.mark.parametrize(
    ("new", "others", "after"),
    [("child", ["child", "solo"], ["base", "solo"]), ("solo", [], ["base"])],
)
def test_a_new_main_scenario_takes_the_old_one_into_the_comparison(
    new: str, others: list[str], after: list[str]
) -> None:
    assert promoted("base", new, others) == after


@pytest.mark.parametrize(
    ("query", "tab"),
    [
        ({}, "Timeline"),
        ({"tab": "Phases"}, "Phases"),  # a phase before the start of a roll forward
        ({"event": "lump_sum"}, "Events"),
        ({"tab": "Phases", "event": "lump_sum"}, "Events"),
        ({"tab": "nothing"}, "Timeline"),
    ],
)
def test_a_link_opens_the_tab_of_its_query(family: Path, query: dict[str, str], tab: str) -> None:
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params.update({"scenario": "child"} | query)
    at.run()
    assert not at.exception
    tabs, *_ = at.get("tab_container")  # the first holds the tabs of the scenario
    assert TABS[tabs.proto.tab_container.default_tab_index] == tab


def test_a_phase_change_takes_a_phase_of_the_assumptions(family: Path) -> None:
    """In the order of `assumptions.yaml`, by its label, no new name: a scenario defines no
    phase."""
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params.update({"scenario": "child", "tab": "Phases"})
    at.run()
    assert not at.exception
    columns = (json.loads(g.proto.columns) for g in at.dataframe)
    phase = next(c["phase"]["type_config"] for c in columns if "phase" in c)
    labels = ("Work", "Unemployed", "Career break", "Retired")
    names = ("work", "unemployed", "alt", "retired")
    options = [{"value": n, "label": t} for n, t in zip(names, labels, strict=True)]
    assert phase == {"type": "selectbox", "options": options}


def test_the_items_of_the_parents_are_left_out_in_their_tabs(family: Path) -> None:
    """A toggle per id, of the phases of the parents in `Phases`, of their events in `Events`:
    both write the one `drop` list of the file."""
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params["scenario"] = "child"
    at.query_params["event"] = "lump_sum"  # a link to an event type opens its tab
    at.run()
    assert not at.exception
    assert at.session_state["events-child-open"] == "lump_sum"
    toggles = {str(t.key).rsplit("-", 1)[-1]: t for t in at.toggle if t.label.startswith("Leave")}
    assert (toggles["retirement"].value, toggles["bonus"].value) == (False, True)
    toggles["retirement"].set_value(True).run()
    next(b for b in at.button if b.key == "scenarios-phases-child-save").click().run()
    assert any("no event or phase with this id" in e.value for e in at.error)  # its own shift
    bonus = next(t for t in at.toggle if str(t.key).endswith("events-child-drop-0-bonus"))
    bonus.set_value(False).run()
    at.button(key="events-child-lump_sum-save").click().run()  # the Save of the type open
    assert not at.exception
    assert "drop" not in read_yaml(family / "scenarios" / "child.yaml")
    assert "bonus" in {e.id for e in load_scenario(family / "scenarios" / "child.yaml").events}


@pytest.mark.parametrize(
    ("app", "template", "first"),
    [
        ("scenarios: []\n", False, "base"),  # the last default deleted
        ("scenarios: [gone, child]\n", False, "child"),
        ("", True, "child"),  # a template does not run
    ],
)
def test_the_first_scenario_is_the_one_of_the_other_pages(
    family: Path, app: str, template: bool, first: str
) -> None:
    (family / APP).write_text(app)
    if template:
        (family / "scenarios" / "base.yaml").write_text(PARENT + "abstract: true\n")
    saved = references.read(family, APP).get("scenarios")
    assert (
        opening(scenariofiles.raw_scenarios(family), saved)[1]
        == first
        == scenariofiles.first_scenario(family)
    )


def test_without_a_concrete_scenario_the_main_one_is_an_input_problem(family: Path) -> None:
    for file in (family / "scenarios").glob("*.yaml"):
        file.write_text(file.read_text() + "abstract: true\n")
    with pytest.raises(InputError, match="no scenario runs"):
        scenariofiles.first_scenario(family)


def test_a_phase_saved_from_the_grid_runs(family: Path) -> None:
    file = "scenarios/base.yaml"  # a file with phases: the grid edits them row by row
    form = forms.Form("phases", file, (FIELDS[("phases",)],), Scenario)
    added = {"from": date(2040, 1, 1), "phase": "retired", "id": "early"}
    rows: dict[KeyPath, RowEdits] = {("phases",): RowEdits(added=[added])}
    shown = forms.Shown(
        family,
        form,
        forms.Base(form.part(read_yaml(family / file)), None),
        forms.Typed({}, {}, {}, rows),
        {},
        stale=False,
    )
    assert [c.text for c in shown.changes()] == [
        "**phases 3 from** empty → 2040-01",
        "**phases 3 phase** empty → retired",
        "**phases 3 id** empty → early",
    ]
    store.write(family, [shown.edit()], source="test")
    phases = load_scenario(family / file).phases
    assert (date(2040, 1, 1), "retired", "early") in [(p.at, p.phase, p.id) for p in phases]


def test_a_phase_change_saved_without_an_id_takes_one(family: Path) -> None:
    """Its phase, else with its year, none that the chain holds; a cleared id stays cleared."""
    file = "scenarios/base.yaml"
    form = forms.Form("phases", file, (FIELDS[("phases",)],), Scenario)
    early = {"from": date(2040, 1, 1), "phase": "retired"}
    rows: dict[KeyPath, RowEdits] = {
        ("phases",): RowEdits(edited={0: {"from": date(2026, 2, 1)}}, added=[early, dict(early)])
    }
    shown = forms.Shown(
        family,
        form,
        forms.Base(form.part(read_yaml(family / file)), None),
        forms.Typed({}, {}, {}, rows),
        {},
        stale=False,
    )
    filled = shown.fill(("phases",), phase_ids({"retirement", "work-2026"}))
    phases = filled.candidate["phases"]
    assert [p.get("id") for p in phases] == ["work", "retirement", "retired", "retired-2040"]
    # the form that it filled stays as drawn
    assert rows[("phases",)].added == [{"from": date(2040, 1, 1), "phase": "retired"}] * 2
    typed = forms.Typed({}, {}, {}, {("phases",): RowEdits(edited={1: {"id": None}})})
    cleared = replace(shown, typed=typed)
    assert "id" not in cleared.fill(("phases",), phase_ids(set())).candidate["phases"][1]


def test_the_link_to_the_explorer_names_the_parent_that_runs(tmp_path: Path) -> None:
    chain: list[tuple[Path, dict[str, Any]]] = [
        (tmp_path / "plan.yaml", {"name": "Work to 65"}),
        (tmp_path / "tpl.yaml", {"name": "Base", "abstract": True}),
        (tmp_path / "buy.yaml", {"name": "Buy"}),
    ]
    assert compare_label(chain) == "Compare with Work to 65 in the Explorer"
    assert compare_label(chain[-1:]) == "Run it in the Explorer"


def _page(data: Path, stem: str, mode: str | None = "simple") -> AppTest:
    at = AppTest.from_string(PAGE.format(data=str(data)), default_timeout=30)
    at.query_params["scenario"] = stem
    if mode:
        at.query_params["mode"] = mode
    at.run()
    assert not at.exception
    return at


def _tabs(at: AppTest) -> list[str]:
    return [t.label for t in at.tabs if t.label in TABS]


@pytest.mark.parametrize(
    ("stem", "mode", "shown"),
    [("base", "simple", False), ("child", "simple", True), ("base", None, True)],
)
def test_simple_mode_shows_the_overrides_of_a_scenario_that_holds_some(
    family: Path, stem: str, mode: str | None, shown: bool
) -> None:
    """`child` holds overrides and drops, `base` none: its tab goes, and a note names it."""
    at = _page(family, stem, mode)
    assert ("Overrides" in _tabs(at)) == shown
    note = "Hidden in simple mode: Overrides. Switch to Advanced in the sidebar to use them."
    assert (note in [c.value for c in at.caption]) != shown


def test_an_override_typed_in_advanced_mode_keeps_its_tab_in_simple_mode(family: Path) -> None:
    at = _page(family, "base", None)
    label = assumptions.LABELS[("cash_buffer_months",)]
    next(w for w in at.text_input if w.label == label).input("4").run()
    at.query_params["mode"] = "simple"
    at.run()
    assert "Overrides" in _tabs(at)
    assert label in [w.label for w in at.text_input]
    next(b for b in at.button if b.key == "overrides-base-save").click().run()
    assert not at.exception
    assert read_yaml(family / "scenarios" / "base.yaml")["overrides"] == {"cash_buffer_months": 4}


@pytest.mark.parametrize(("abstract", "shown"), [("", False), ("abstract: true\n", True)])
def test_simple_mode_shows_the_template_switch_of_a_template_only(
    family: Path, abstract: str, shown: bool
) -> None:
    (family / "scenarios" / "tpl.yaml").write_text(f"name: Tpl\n{abstract}")
    at = _page(family, "tpl")
    assert (LABELS[("abstract",)] in [t.label for t in at.toggle]) == shown
    notes = [c.value for c in at.caption if c.value.startswith("Hidden in simple mode")]
    assert any("Template." in note for note in notes) != shown


def test_a_new_scenario_extends_the_main_one_and_lists_its_phases_in_words(family: Path) -> None:
    plan = Plan(scenariofiles.raw_scenarios(family), "child")
    assert plan.parents == ["child", "base", None]
    assert plan.said("child") == "child · Keep going (main)"
    labels = references.phases(family)

    def listed(parent: str | None) -> list[str]:
        edits = scenariofiles.created(family, "new", "New", parent)
        return [c.text for c in listing(edits, lambda n: references.read(family, n), labels)[0]]

    assert listed("child") == [
        "**scenarios/new.yaml name** empty → New",
        "**scenarios/new.yaml extends** empty → child",
    ]
    assert listed(None)[1] == "**scenarios/new.yaml phases** empty → Work from 2026-01"


def test_a_moved_month_shifts_the_inherited_change_as_the_parents_give_it() -> None:
    """The months from the parent's month; the parents' own shift or an emptied cell sets none;
    a change without an id or one left out does not move."""
    row = Moving(Inherited("base", {"phase": "retired", "id": "r"}, None), date(2050, 1, 1), None)
    rows = [replace(row, month=date(2052, 1, 1)), replace(row, raw=None)]
    rows += [Moving(Inherited("base", {"phase": "work"}, None), date(2026, 1, 1), None)]
    typed = {0: date(2049, 6, 1), 1: date(2049, 1, 1), 2: date(2027, 1, 1)}
    assert {i: m for i, (_r, _d, m) in shifted(rows, typed, {}).items()} == {"r": -7}
    assert shifted(rows, {0: date(2051, 1, 1)}, {"r": 12})["r"][2] is None  # what base gives
    assert shifted(rows, {0: None}, {})["r"][1:] == (date(2050, 1, 1), None)  # emptied
    assert shifted(rows, {0: date(2052, 1, 1)}, {"r": 24}) == {}  # as shown


def test_the_rows_of_one_id_move_as_one_and_a_text_that_is_no_month_moves_nothing() -> None:
    """The guard notes the other rows of an id that moves, also one typed in vain, and a month
    that does not read: it keeps its month, not the parents' one."""

    def row(phase: str, month: date) -> Moving:
        return Moving(Inherited("base", {"phase": phase, "id": "alg1"}, None), month, month)

    rows = [row("unemployed", date(2028, 7, 1)), row("work", date(2029, 10, 1))]
    labels = {"unemployed": "Unemployed", "work": "Work"}
    found, notes = typed_moves(rows, {0: "2028-09"}, {}, labels)
    assert {i: m for i, (_r, _d, m) in found.items()} == {"alg1": 2}
    assert notes == ["alg1 moves as one: Work from 2029-10 moves to 2029-12 too"]
    found, notes = typed_moves(rows, {0: "2028-09", 1: "2030-06"}, {}, labels)
    assert found["alg1"][1] == date(2028, 9, 1)  # the first row typed
    assert notes == [
        "alg1 moves as one: Work from 2029-10 moves to 2029-12, not to the month typed"
    ]
    assert typed_moves(rows, {0: "2028-13"}, {"alg1": 3}, labels) == (
        {},
        ["Unemployed from 2028-07: 2028-13 is no month, so it does not move"],
    )


def test_an_inherited_change_moves_in_place_and_a_repeat_offers_to_move_it(family: Path) -> None:
    """The child moves `retirement` (24 months later now) by a month typed into the grid of the
    parents' changes; a new row of the same phase warns and moves it instead of adding a row.
    `AppTest` keeps no edit of a grid: each run that needs one sends it (`german.edited`)."""
    at = _page(family, "child", "advanced")
    grid, save = "scenarios-phases-child-move-0", "scenarios-phases-child-save"
    move = {"edited_rows": {"1": {"from": "2049-06"}}, "added_rows": [], "deleted_rows": []}
    at = edited(at, grid, move)
    lines = [c.value for c in at.caption if c.value.startswith("To save")]
    moved = "move retirement (1 phase)** 2052-01 (age 75) → 2049-06 (age 72)"
    assert any(moved in line for line in lines)
    at.button(key=save).click()
    at = edited(at, grid, move)
    assert not at.exception
    child = family / "scenarios" / "child.yaml"
    assert read_yaml(child)["overrides"]["shift"] == {"retirement": -7}
    assert "phases" not in read_yaml(child)
    new = {"edited_rows": {}, "added_rows": [{"from": "2048-01", "phase": "retired"}]}
    own, added = "scenarios-phases-child-1-phases", new | {"deleted_rows": []}
    at = edited(at, own, added)
    assert any("repeats the change to Retired of base in 2049-06" in w.value for w in at.warning)
    next(t for t in at.toggle if "instead" in t.label).set_value(True)
    at.button(key=save).click()
    at = edited(at, own, added)
    assert not at.exception
    assert read_yaml(child)["overrides"]["shift"] == {"retirement": -24}
    assert "phases" not in read_yaml(child)
    retired = [p.at for p in loader.load_plan(family, child).scenario.phases if p.id]
    assert retired == [date(2048, 1, 1)]


def test_a_move_instead_stays_with_its_row_when_a_row_above_goes(family: Path) -> None:
    at = _page(family, "child", "advanced")
    own, rows = (
        "scenarios-phases-child-0-phases",
        [
            {"from": "2047-01", "phase": "retired"},
            {"from": "2048-01", "phase": "retired"},
        ],
    )
    both = {"edited_rows": {}, "added_rows": rows, "deleted_rows": []}
    at = edited(at, own, both)
    next(t for t in at.toggle if "instead" in t.label and "2048-01" in t.label).set_value(True)
    at = edited(at, own, both)
    at = edited(at, own, both | {"added_rows": rows[1:]})  # the first new row deleted
    [toggle] = [t for t in at.toggle if "instead" in t.label]
    assert "2048-01" in toggle.label
    assert toggle.value


@pytest.mark.parametrize("phone", [False, True])
def test_the_phases_grid_shows_labels_and_ages_and_the_ids_in_advanced_mode(
    family: Path, phone: bool
) -> None:
    for mode, ids in (("simple", False), ("advanced", True)):
        at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
        at.query_params.update({"scenario": "base", "tab": "Phases", "mode": mode})
        at.query_params["mobile"] = str(int(phone))
        at.run()
        assert not at.exception
        grid = next(g for g in at.dataframe if g.key == "scenarios-phases-base-0-phases")
        assert ("id" in grid.value.columns) == ids
        assert grid.value["age"].tolist() == ["49", "73"]  # born 1977-01-01


def test_a_job_loss_adds_what_the_plan_lacks_and_stops_the_salary(data: Path) -> None:
    """A salary without phases, no ALG1, no phase `unemployed`, the feature off: the action adds
    the phase, the stream and the feature, limits the salary, and the run pays ALG1 then."""
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(assumptions.read_text().replace("unemployed: {label: Unemployed}, ", ""))
    (data / "cashflows.yaml").write_text(
        "streams:\n  - {name: Gehalt, kind: salary, gross: 5000}\n  - {name: Miete, amount: -500}\n"
    )
    (data / APP).write_text("scenarios: [base]\nfeatures_off: [job_loss, care]\n")
    loss = scenariofiles.JobLoss(
        "base", date(2026, 6, 1), date(2027, 6, 1), "Job loss at 49", "job-loss", "Arbeitslos"
    )
    edits = scenariofiles.lost_job(data, loss)
    found, _gone = listing(edits, lambda n: references.read(data, n), references.phases(data))
    assert [c.text for c in found][2:] == [
        "**scenarios/job-loss.yaml phases** empty → Arbeitslos from 2026-06, Work from 2027-06",
        "**assumptions.yaml phases.unemployed** empty → Arbeitslos",
        "**cashflows.yaml streams Gehalt phases** empty → Work, Career break, Retired",
        "**cashflows.yaml streams** name ALG1, cat ALG1, kind Unemployment benefit (ALG1), "
        "phases Arbeitslos",
        "**job loss** off → on",
    ]
    act(data, lambda d: scenariofiles.lost_job(d, loss), source="test")
    assert read_yaml(data / APP)["features_off"] == ["care"]
    with pytest.raises(ValueError, match="exists"):
        scenariofiles.lost_job(data, loss)  # once
    base, lost = fixed_run(data), fixed_run(data, "job-loss")
    assert regular_salary(base).keys() == {"work"}
    assert "unemployed" in lost.phases
    assert "unemployed" not in regular_salary(lost)
    alg1 = [row for (_s, _g, item), row in ledger(lost).entries.items() if item == "ALG1"]
    assert sum(row.sum() for row in alg1) > 0


@pytest.mark.parametrize(("runs", "limited"), [(False, True), (True, False)])
def test_a_job_loss_limits_a_salary_only_where_no_scenario_runs_the_phase(
    family: Path, runs: bool, limited: bool
) -> None:
    """A limit of a salary without phases would change a scenario that runs `unemployed`."""
    (family / "cashflows.yaml").write_text("streams:\n  - {name: Gehalt, kind: salary, gross: 1}\n")
    if runs:
        change = "\n  - {from: 2040-01-01, phase: unemployed}"
        (family / "scenarios" / "base.yaml").write_text(
            PARENT.replace("\nevents:", change + "\nevents:")
        )
    loss = scenariofiles.JobLoss("base", date(2027, 1, 1), None, "Lost", "lost", "Unemployed")
    rows = next(e for e in scenariofiles.lost_job(family, loss) if e.name == "cashflows.yaml")
    assert bool(rows.rows[("streams",)].edited) == limited


@pytest.mark.parametrize(
    ("lost", "back", "refused"),
    [
        (date(2025, 6, 1), None, "before the start 2026-01"),
        (date(2026, 6, 1), date(2026, 6, 1), "the new job starts before the job loss"),
        # the main scenario is unemployed then: the new job would change no phase
        (date(2039, 6, 1), date(2041, 1, 1), "is unemployed or has no phase in 2041-01"),
    ],
)
def test_a_job_loss_refuses_a_month_out_of_order(
    family: Path, lost: date, back: date | None, refused: str
) -> None:
    change = "\n  - {from: 2040-01-01, phase: unemployed}"
    (family / "scenarios" / "base.yaml").write_text(
        PARENT.replace("\nevents:", change + "\nevents:")
    )
    loss = scenariofiles.JobLoss("base", lost, back, "Lost", "lost", "Unemployed")
    with pytest.raises(ValueError, match=refused):
        scenariofiles.lost_job(family, loss)


@pytest.mark.parametrize("phone", [False, True])
def test_the_job_loss_dialog_writes_one_revision(family: Path, phone: bool) -> None:
    """`AppTest` draws a dialog only in the run of the click of its button: the months come
    through the session state, the confirm with that click."""
    at = AppTest.from_string(PAGE.format(data=str(family)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    action = next(b for b in at.button if b.key == "scenarios-job-loss")
    action.click().run()
    assert not at.exception
    assert next(b for b in at.button if b.key == "scenarios-confirm").disabled
    at.session_state["scenarios-loss-lost"] = "2027-03"
    at.session_state["scenarios-loss-back"] = "2028-01"
    next(b for b in at.button if b.key == "scenarios-job-loss").click().run()
    assert at.text_input(key="scenarios-loss-name").placeholder == "Job loss at 50"
    listed = next(c.value for c in at.caption if c.value.startswith("To save"))
    assert "Unemployed from 2027-03, Work from 2028-01" in listed
    next(b for b in at.button if b.key == "scenarios-job-loss").click()
    next(b for b in at.button if b.key == "scenarios-confirm").click().run()
    assert not at.exception
    last = revisions.entries(family)[-1]
    assert (last.source, last.files) == (
        "app: job loss job-loss-at-50",
        ("cashflows.yaml", "scenarios/job-loss-at-50.yaml"),
    )
    lost = load_scenario(family / "scenarios" / "job-loss-at-50.yaml")
    assert [(p.at, p.phase) for p in lost.phases][1:3] == [
        (date(2027, 3, 1), "unemployed"),
        (date(2028, 1, 1), "work"),
    ]
