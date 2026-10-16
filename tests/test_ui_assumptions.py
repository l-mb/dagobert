"""The Assumptions page: its tabs and their saves, the phases, the tax year, the
fields of self-employment; the sick pay of the Overrides tab; the fields of simple mode and of a
feature off."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml
from apps import ASSUMPTIONS
from german import ACTIVATE, edited
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button

from dagobert import datadir, i18n, references, revisions, store
from dagobert.loader import flatten, load_assumptions
from dagobert.model.assumptions import Assumptions
from dagobert.model.taxes import default_tax_year
from dagobert.overrides import Leaf
from dagobert.store import NULL
from dagobert.tax import for_year
from dagobert.ui import PAGES, fields, forms
from dagobert.ui import assumptions as assumptions_page
from dagobert.ui.assumptions import LABELS

ENGINEER = datadir.EXAMPLE


def test_the_tabs_edit_every_assumption_but_start_and_scale() -> None:
    shown = [f.path for tab in assumptions_page.TABS for f in tab.fields]
    assert len(shown) == len(set(shown))  # each in one tab
    every = {f.path for f in fields.of(Assumptions) if f.path[0] != "scale"}
    assert set(shown) == every - {("start",)}


def test_a_scenario_overrides_no_phase() -> None:
    """`assumptions.yaml` defines the phases for every scenario: the Overrides tab lacks them."""
    person = assumptions_page.PERSON
    assert ("phases",) in {f.path for f in person.form().fields}
    override = person.form(file="scenarios/base.yaml", keys=("overrides",), override=True)
    assert all(f.path[0] != "phases" for f in override.fields)


def test_a_phase_that_an_input_names_keeps_its_name(data: Path) -> None:
    """A delete or a rename leaves the uses behind: Save stays off, the label may change."""
    refs = references.of(data)  # `work` names the phase of the base scenario
    before: dict[str, object] = {"phases": {"work": {}, "alt": {}}}
    assert assumptions_page.refused(refs, before, {"phases": {"job": {}, "alt": {}}}) == [
        "the phase work keeps its name while inputs name it: scenarios/base.yaml: "
        "phases[0].phase (phase work 2026-01)"
    ]
    assert assumptions_page.refused(refs, before, {"phases": {"work": {"label": "Job"}}}) == []


def test_a_relative_that_an_event_names_keeps_its_name(data: Path) -> None:
    """A delete of a relative that an inheritance names leaves its use behind: Save stays off;
    its label may change."""
    (data / "scenarios" / "base.yaml").write_text(
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
        "events: [{type: inheritance, from: mutter, cash: 1000}]\n"
    )
    refs = references.of(data)
    mutter = {"born": date(1950, 5, 1), "sex": "f", "relation": "parent"}
    before: dict[str, object] = {"person": {"relatives": {"mutter": mutter}}}
    assert assumptions_page.refused(refs, before, {"person": {"relatives": {}}}) == [
        "the relative mutter keeps its name while inputs name it: scenarios/base.yaml: "
        "events[0].from (inheritance)"
    ]
    renamed = {"person": {"relatives": {"mutter": mutter | {"label": "Mama"}}}}
    assert assumptions_page.refused(refs, before, renamed) == []


def test_the_gifts_before_the_start_save_alone(tmp_path: Path) -> None:
    """A gift of a relative before the start saves from its own grid, beside the Save of the tab:
    one revision of the page, the rest of the file as it was."""
    data = tmp_path / "engineer"
    shutil.copytree(ENGINEER, data)
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    grid, edit = (
        "assumptions-given-mother-0",
        {"added_rows": [{"at": "2024-03-01", "value": 50000}]},
    )
    edited(at, grid, edit)
    assert "To save:  \n**2024-03 value** empty → 50.000,00 €" in [c.value for c in at.caption]
    at.button(key="assumptions-given-mother-save").click()
    edited(at, grid, edit)  # a browser sends the edits with the press
    assert not at.exception
    given = load_assumptions(data).person.relatives["mother"].given
    assert [(g.at, g.value, g.tax) for g in given] == [(date(2024, 3, 1), 50000, 0)]
    assert revisions.entries(data)[-1].source == "app"


def test_a_form_names_a_change_elsewhere_in_the_language_of_the_session(data: Path) -> None:
    """The page of a change elsewhere in words, its action as written; the revision log keeps the
    English source."""
    pages = f"import streamlit as st\nst.session_state[{PAGES!r}] = {{'Assumptions': None}}\n"
    at = AppTest.from_string(ACTIVATE + pages + ASSUMPTIONS.format(data=str(data)))
    at.query_params["lang"] = "de"
    at.run()
    with i18n.use("de"):  # the German of the label: a German render drives no English label
        label = i18n._(assumptions_page.LABELS[("cash_buffer_months",)])
    next(w for w in at.text_input if w.label == label).input("4,5").run()
    edit = store.Edit("assumptions.yaml", {("cash_buffer_months",): 6})
    store.write(data, [edit], source="Assumptions: Rules")
    at.run()
    [warning] = [w.value for w in at.warning if "seit dieses Formular angezeigt wurde" in w.value]
    assert "auf der Seite Annahmen: Rules" in warning
    assert "Meine Änderungen verwerfen" in [b.label for b in at.button]
    assert revisions.entries(data)[-1].source == "Assumptions: Rules"


def _save(at: AppTest, tab: str) -> Button:
    """The Save of a tab of the Assumptions page."""
    return at.button(key=f"{assumptions_page.KEY}-{tab}-save")


def test_a_tab_of_the_assumptions_saves_alone_as_one_revision(tmp_path: Path) -> None:
    data = tmp_path / "engineer"
    shutil.copytree(ENGINEER, data)
    before, example = (data / "assumptions.yaml").read_text(), load_assumptions(ENGINEER)
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    start = next(w for w in at.text_input if w.label == "Start month (read only)")
    # the roll forward moves it
    assert (start.value, start.proto.disabled) == (f"{example.start:%Y-%m}", True)
    next(
        w for w in at.text_input if w.label == assumptions_page.LABELS[("cash_buffer_months",)]
    ).input("4,5").run()
    next(
        w for w in at.text_input if w.label == assumptions_page.LABELS[("inflation", "mean")]
    ).input("2,5").run()  # of `Markets`
    _save(at, "rules").click().run()
    assert not at.exception
    assert revisions.entries(data)[-1].source == "app: Rules"
    # one line changed, the comments and the flow mappings stay
    buffer = f"cash_buffer_months: {example.cash_buffer_months:g}\n"
    assert buffer in before
    after = before.replace(buffer, "cash_buffer_months: 4.5\n")
    assert (data / "assumptions.yaml").read_text() == after
    # the edit of another tab of the file stays, and its Save is not refused
    assert (_save(at, "rules").disabled, _save(at, "markets").disabled) == (True, False)


def test_an_empty_tax_year_shows_the_year_of_the_start(data: Path) -> None:
    """The model leaves `tax.year` to the plan: the newest file up to the year of `start`, and
    `tax.kv_zusatz` the average of that year."""
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60).run()
    year = next(g.proto for g in at.get("button_group") if g.proto.label == "Tax year")
    marked = [o.content for o in year.options if o.content.endswith(" from start")]
    taken = default_tax_year(load_assumptions(data).start)
    assert (marked, list(year.default)) == ([f"{taken} from start"], [])
    label = assumptions_page.LABELS[("tax", "kv_zusatz")]
    zusatz = next(w for w in at.text_input if w.label == label)
    average = f"{200 * for_year(taken).kv_zusatz_half:g}"
    assert zusatz.placeholder == f"{average} from tax year {taken}"


def test_a_start_leaf_without_a_value_falls_back_to_the_start_of_the_file(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A merged `start` that holds None gives no year: the file's own start does."""
    monkeypatch.setattr(forms.Form, "leaves", lambda *_: {("start",): Leaf(None, "child")})
    tax = next(t for t in assumptions_page.TABS if "tax" in t.tops)
    found = tax.form().leaves(data, {})
    assert found[assumptions_page.TAX_YEAR].value == default_tax_year(load_assumptions(data).start)


@pytest.mark.parametrize(
    ("tax", "off", "private"),
    [
        ("", True, True),
        ("tax: {pkv: false, self_employed: {rv: regular}}\n", False, False),
        ("tax: {gkv_from: 2030-01-01, self_employed: {rv: regular}}\n", False, True),
    ],
)
def test_self_employment_reads_in_words_and_offs_what_has_no_effect(
    data: Path, tax: str, *, off: bool, private: bool
) -> None:
    """Sick pay counts with statutory insurance only, also after a switch to it, which a member
    of the PKV takes, the founding with a fixed contribution."""
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write(tax)
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    rv = next(g.proto for g in at.get("button_group") if g.proto.label.startswith("Pension ins"))
    assert [o.content for o in rv.options] == [
        "None (default)",
        "Fixed contribution (Regelbeitrag)",
        "By profit",
    ]
    assert "contribution ceiling" in rv.help and "`" not in rv.help  # words, no keys
    sick = next(t for t in at.toggle if t.label.startswith("Sick pay"))
    founded = next(t for t in at.text_input if t.label == "Business founded")
    assert (sick.label, sick.proto.disabled, founded.proto.disabled) == (
        "Sick pay in the GKV (statutory insurance only)" if off else "Sick pay in the GKV",
        off,
        off,
    )
    assert (founded.placeholder == "fixed contribution only") is off  # a label would wrap
    switch = next(t for t in at.text_input if t.label == "Statutory health insurance from")
    assert (switch.proto.disabled, switch.placeholder == "private insurance only") == (
        not private,
        not private,
    )


@pytest.mark.parametrize(
    ("overrides", "off"),
    [
        ("", True),
        ("overrides: {tax: {pkv: false}}\n", False),
        ("overrides: {tax: {gkv_from: 2030-01-01}}\n", False),
    ],
)
def test_a_scenario_offs_sick_pay_by_the_insurance_it_inherits(
    data: Path, overrides: str, off: bool
) -> None:
    """The Overrides tab takes the insurance of its chain, the default PKV without one, and its
    switch to the GKV."""
    path = data / "scenarios" / "base.yaml"
    path.write_text(path.read_text() + overrides)
    script = "from pathlib import Path\nfrom dagobert.ui import scenario_overrides\n"
    at = AppTest.from_string(
        f"{script}scenario_overrides.tab(Path({str(path)!r}))\n", default_timeout=60
    ).run()
    assert not at.exception
    sick = next(g.proto for g in at.get("button_group") if g.proto.label.startswith("Sick pay"))
    assert (sick.label.endswith("(statutory insurance only)"), sick.disabled) == (off, off)


def test_the_phases_show_their_name_on_the_pages_first() -> None:
    """A phase without a label shows its short name, a label like it is not written, and a new
    phase takes a short name from its label that no other phase has."""
    rows = assumptions_page.LabeledRows()
    phases = {"work": {}, "alt": {"label": "Career break"}}
    shown = rows.rows(phases)
    assert shown == [{"name": "work", "label": "work"}, {"name": "alt", "label": "Career break"}]
    assert rows.mapping(shown) == phases
    added = [*shown, {"label": "Career break 2"}, {"label": "work"}, {}]
    assert list(rows.mapping(added).items())[2:] == [
        ("career-break-2", {"label": "Career break 2"}),
        ("work-2", {"label": "work"}),
    ]


def test_a_tab_of_a_broken_file_saves_what_does_not_break_it(data: Path) -> None:
    """A problem that the file holds already shows, by the field that needs it, and keeps Save
    on: the edit does not add it, and the write refuses only what it adds, so a fix elsewhere in
    a broken file saves."""
    path = data / "assumptions.yaml"
    path.write_text(path.read_text().replace("  equity: {mean: 0.05}\n", ""))
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60).run()
    next(w for w in at.text_input if w.label == assumptions_page.LABELS[("refinance_rate",)]).input(
        "5"
    ).run()
    assert any("returns: needs the class equity" in w.value for w in at.warning)
    _save(at, "markets").click().run()
    assert not at.exception
    assert "refinance_rate: 0.05" in path.read_text()


def test_a_whole_number_and_a_choice_empty_again_take_their_default(data: Path) -> None:
    """A number input or a select box that starts with a value has no empty state: both start
    empty and hold the value of the file in their state."""
    path = data / "assumptions.yaml"
    path.write_text(path.read_text() + "care:\n  hazard: [{age: 80, factor: 0.1}]\n  cost: 500\n")
    path.write_text(path.read_text() + "  duration: {mean: 24}\n  index: null\n")
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60).run()
    horizon = next(
        w for w in at.number_input if w.label == assumptions_page.LABELS[("person", "horizon_age")]
    )
    index = next(w for w in at.selectbox if w.label == assumptions_page.LABELS[("care", "index")])
    assert (horizon.value, index.value) == (51, NULL)
    assert not horizon.proto.HasField("default")  # the browser lets it go empty
    assert "none: nominal euros" in index.options
    horizon.set_value(None).run()
    next(
        w for w in at.selectbox if w.label == assumptions_page.LABELS[("care", "index")]
    ).set_value(None).run()
    for tab in ("person", "rules"):
        _save(at, tab).click().run()
    assert not at.exception
    a = load_assumptions(data)
    assert (a.person.horizon_age, a.care and a.care.index) == (105, "cpi")


STARTER = datadir.EXAMPLES / "starter"


def _starter(tmp_path: Path) -> Path:
    """`starter` with keys at the default of their field: they act like absent ones, so simple mode
    hides their fields, and a save must keep them."""
    data = tmp_path / "starter"
    shutil.copytree(STARTER, data)
    path = data / "assumptions.yaml"
    text = path.read_text().replace(
        "  rv_since: 2019-10-01\n", "  rv_since: 2019-10-01\n  children: 0\n  relatives: {}\n"
    )
    path.write_text(f"{text}  teilfreistellung: 0.3\n  alleinerziehend: false\nseed: 7\n")
    return data


def _page(data: Path, mode: str | None = "simple") -> AppTest:
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60)
    if mode:
        at.query_params["mode"] = mode
    at.run()
    assert not at.exception
    return at


def _labels(at: AppTest) -> set[str]:
    """The labels of the fields and the headings of the grids and sections on the page."""
    widgets = (*at.text_input, *at.number_input, *at.toggle, *at.selectbox)
    return {w.label for w in widgets} | {m.value.strip("*") for m in at.markdown}


def _notes(at: AppTest) -> list[str]:
    return [c.value for c in at.caption if c.value.startswith("Hidden in simple mode")]


def test_simple_mode_shows_the_fields_that_the_plan_uses(tmp_path: Path) -> None:
    """`starter` in simple mode: the core, the expert fields that it sets (an index, the volatility
    of inflation and of its classes), no tab without a field (`Rules`), and a note per tab and
    below the tabs of what is hidden. Advanced mode shows every field."""
    data = _starter(tmp_path)
    at = _page(data)
    assert [t.label for t in at.tabs] == ["Person", "Markets", "Tax"]
    shown = _labels(at)
    held = [LABELS[p] for p in [("person", "rv_since"), ("inflation", "stdev"), ("indices",)]]
    hidden = [LABELS[p] for p in [("person", "horizon_age"), ("seed",), ("tax", "year")]]
    assert [label for label in held if label not in shown] == []
    assert [label for label in hidden if label in shown] == []
    person, markets, tax, rules = _notes(at)
    assert person == (
        "Hidden in simple mode (at their defaults): Plan up to age and Health insurance of "
        "pensioners (KVdR). Switch to Advanced in the sidebar to change them. Off in Features: "
        "children; inheritance and gifts. Turn them on there to use them."
    )
    assert "Off in Features: property, rental and loans." in markets
    assert "Off in Features: gold and crypto; self-employment; children." in tax
    assert rules.startswith("Hidden in simple mode (at their defaults): Cash buffer (months),")
    advanced = _page(data, None)
    assert [t.label for t in advanced.tabs] == ["Person", "Markets", "Rules", "Tax"]
    assert _notes(advanced) == []


def test_a_section_in_use_shows_whole_and_a_feature_off_hides_in_both_modes(
    tmp_path: Path,
) -> None:
    """The fields of `care` follow the section: its spread shows at its default while the file
    sets the care. Care switched off in `app.yaml` hides the section of a plan without it, also in
    advanced mode, and the note names the feature."""
    data = _starter(tmp_path)
    path = data / "assumptions.yaml"
    held = path.read_text()
    care = "care: {hazard: [{age: 80, factor: 0.1}], cost: 500, duration: {mean: 24}}\n"
    path.write_text(held + care)
    assert LABELS[("care", "duration", "stdev")] in _labels(_page(data))
    path.write_text(held)
    (data / "app.yaml").write_text("scenarios: [ausstieg, plan]\nfeatures_off: [care]\n")
    at = _page(data, None)
    assert LABELS[("care",)] not in _labels(at)
    assert any("Off in Features: long-term care." in c.value for c in at.caption)


# a field of each tab that simple mode shows on `starter` (`engineer` for the rules), the text
# typed into it and the example
VISIBLE = {
    "person": (("person", "rv_since"), "2019-11-01", "starter"),
    "markets": (("inflation", "mean"), "2,5", "starter"),
    "rules": (("care", "cost"), "1900", "engineer"),
    "tax": (("tax", "werbungskosten"), "1600", "starter"),
}


@pytest.mark.parametrize("tab", list(VISIBLE))
def test_a_save_in_simple_mode_changes_only_the_field_edited(tmp_path: Path, tab: str) -> None:
    """The fields that simple mode hides keep their keys, also those at their default (`seed: 7`,
    `children: 0`), and the sections that the plan sets (the care, the allocation, the spending
    rule of `engineer`)."""
    path, typed, example = VISIBLE[tab]
    data = _starter(tmp_path) if example == "starter" else tmp_path / example
    if example != "starter":
        shutil.copytree(ENGINEER, data)
    before = flatten(yaml.safe_load((data / "assumptions.yaml").read_text()))
    at = _page(data)
    next(w for w in at.text_input if w.label == LABELS[path]).input(typed).run()
    _save(at, tab).click().run()
    assert not at.exception
    after = flatten(yaml.safe_load((data / "assumptions.yaml").read_text()))
    assert [p for p in before.keys() | after.keys() if before.get(p) != after.get(p)] == [path]


@pytest.mark.parametrize("ran", [True, False])
def test_a_field_edited_in_advanced_mode_stays_in_simple_mode(tmp_path: Path, ran: bool) -> None:
    """A value typed in advanced mode stays with its tab when simple mode would hide it, also
    when the switch comes with the value (`ran` off: no run saw the edit first), and saves."""
    data = _starter(tmp_path)
    at = _page(data, None)
    next(w for w in at.number_input if w.label == LABELS[("seed",)]).set_value(8)
    if ran:
        at.run()
    at.query_params["mode"] = "simple"
    at.run()
    assert [t.label for t in at.tabs] == ["Person", "Markets", "Rules", "Tax"]
    assert LABELS[("seed",)] in _labels(at)
    assert LABELS[("cash_buffer_months",)] not in _labels(at)
    _save(at, "rules").click().run()
    assert load_assumptions(data).seed == 8


def test_a_section_switched_on_in_advanced_mode_stays_whole_in_simple_mode(
    tmp_path: Path,
) -> None:
    """`Use` of the care turned on shows its required fields after the switch, which name what
    keeps Save off. The care is on in Features: `starter` switches it off."""
    data = _starter(tmp_path)
    (data / "app.yaml").write_text("scenarios: [ausstieg, plan]\n")
    at = _page(data, None)
    care = f"{assumptions_page.KEY}-rules-0-care"
    at.toggle(key=care).set_value(True).run()
    at.query_params["mode"] = "simple"
    at.run()
    assert at.toggle(key=care).value
    assert LABELS[("care", "cost")] in _labels(at)
    assert _save(at, "rules").disabled


@pytest.mark.parametrize(
    ("example", "mode", "shown"),
    [("starter", "simple", False), ("starter", None, True), ("engineer", "simple", True)],
)
def test_simple_mode_moves_a_column_that_no_class_holds_behind_all_columns(
    tmp_path: Path, example: str, mode: str | None, shown: bool
) -> None:
    """The correlation of a class with equity: `engineer` sets one for Bitcoin."""
    shutil.copytree(datadir.EXAMPLES / example, data := tmp_path / example)
    at = _page(data, mode)
    returns = next(d for d in at.dataframe if str(d.key).endswith("-returns"))
    assert ("equity_correlation" in returns.value.columns) == shown
    assert "stdev" in returns.value.columns  # every class of both holds one
