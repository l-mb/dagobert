"""Simple and advanced mode and the features: what the inputs use, the one predicate, the pages of
the navigation, the mode of a session, the Features page and every page drawn in simple mode
and with every feature off."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
import yaml
from apps import EXPLORER, MAIN, PAGE, render
from german import edited, leaks, words
from streamlit.runtime.context import ContextProxy
from streamlit.testing.v1 import AppTest

from dagobert import datadir, references, revisions, store
from dagobert.loader import APP, flatten, load_app_settings
from dagobert.model.assumptions import Assumptions
from dagobert.model.base import KeyPath
from dagobert.model.plan import Feature
from dagobert.model.streams import Deduction, Stream, StreamKind
from dagobert.problems import InputError
from dagobert.runner import DATA_ENV
from dagobert.ui import PAGES, mode, sliders
from dagobert.ui.events import TYPES
from dagobert.ui.fields import ABSENT, Kind, of
from dagobert.ui.gridcolumns import ASSET_MODELS
from dagobert.ui.mode import FEATURES, Item, Sort, Uses, shown

NOTHING: frozenset[Feature] = frozenset()
SHIPPED = mode.DEFAULT  # read at collection, before the fixture `advanced_by_default`
SIMPLE_PAGES = {
    "Overview",
    "Assets",
    "Cashflows",
    "Explorer",
    "Flows",
    "Features",
    "Assumptions",
    "Scenarios",
    "Export and import",
}


def _item(sort: Sort, name: str) -> Item:
    return Item(sort, tuple(name.split(".")))


def _example(name: datadir.ExampleName) -> Uses:
    return mode.uses(datadir.EXAMPLES / name)


def test_the_simple_example_uses_less_than_the_full_one() -> None:
    """`starter` is a newcomer's plan: no gold, no property, no event, no rule beyond the
    defaults. It holds an index, Werbungskosten, a cost basis and a bonus share of the salary."""
    starter, engineer = _example("starter"), _example("engineer")
    for sort in (Sort.KIND, Sort.STREAM, Sort.EVENT, Sort.DATA, Sort.PAGE):
        assert {i for i in starter.items if i.sort is sort} <= engineer.items
    lacks = [
        *(_item(Sort.KIND, k) for k in ("gold", "crypto", "property", "loan", "term_deposit")),
        *(_item(Sort.STREAM, k) for k in ("alg1", "self_employed")),
        *(_item(Sort.EVENT, k) for k in TYPES),
        *(_item(Sort.PATH, p) for p in ("care", "allocation", "spending")),
    ]
    assert [i for i in lacks if i in starter] == []
    assert all(i in engineer for i in lacks)
    holds = [
        _item(Sort.PATH, "indices"),
        _item(Sort.PATH, "tax.werbungskosten"),
        _item(Sort.PATH, "returns.*.stdev"),
        *(_item(Sort.COLUMN, c) for c in ("assets.cost_basis", "streams.of", "streams.share")),
    ]
    assert [i for i in holds if i not in starter] == []
    assert _item(Sort.PATH, "returns.*.equity_correlation") not in starter


def test_the_full_example_locks_every_feature_that_has_items() -> None:
    """`engineer` uses every part of life that the app models, and names where."""
    engineer = _example("engineer")
    free = {f for f in Feature if not engineer.used(f)}
    assert free == {f for f, spec in FEATURES.items() if not spec.hides}
    assert all(1 <= len(engineer.where[f]) <= mode.PLACES_SHOWN for f in Feature if f not in free)


def test_inputs_that_do_not_parse_use_everything(data: Path) -> None:
    """The error screen of `main.py` comes with the whole navigation: the Scenarios page fixes
    the file."""
    (data / "scenarios" / "broken.yaml").write_text("[\n")
    found = mode.uses(data)
    assert found.everything
    assert found.where == {}
    assert mode.pages(found, frozenset(Feature), advanced=False) == set(mode.PAGES)


def test_records_that_do_not_decode_count(data: Path) -> None:
    """A history of another encoding counts its rows: the Snapshot page names the problem."""
    (data / "history.csv").write_bytes(b"date,asset,value\n2026-01-31,giro,1000\xff\n")
    assert _item(Sort.PAGE, "Snapshot") in mode.uses(data)


def test_only_what_acts_counts_as_used(data: Path) -> None:
    """A key at the default of its field holds nothing (`children: 0`, `alleinerziehend: false`),
    and the share of a PKV premium that the tax takes is no deduction: neither locks its feature.
    A child does, and so does an `update_every` without a record: its column always shows."""
    assumptions = data / "assumptions.yaml"
    text = assumptions.read_text().replace("horizon_age: 51}", "horizon_age: 51, children: 0}")
    assumptions.write_text(f"{text}tax: {{alleinerziehend: false}}\n")
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - {id: tg, kind: fixed_income, value: 1, update_every: 6}\n")
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: PKV, cat: health, amount: -500, health: kv, deductible: 0.8}\n")
    found = mode.uses(data)
    locks = (Feature.CHILDREN, Feature.TRACKING, Feature.DEDUCTIONS)
    assert [f for f in locks if found.used(f)] == [Feature.TRACKING]
    assert _item(Sort.COLUMN, "streams.deductible") in found  # its column shows
    every = _item(Sort.COLUMN, "assets.update_every")
    assert shown(every, found, frozenset({Feature.TRACKING}), advanced=False)
    assumptions.write_text(assumptions.read_text().replace("children: 0", "children: 1"))
    assert [f for f in locks if mode.uses(data).used(f)] == [Feature.CHILDREN, Feature.TRACKING]


def _listed() -> list[Item]:
    """Every item that a table of `mode` names."""
    return sorted(
        {*mode.CORE, *mode.EXPERT, *(i for spec in FEATURES.values() for i in spec.hides)}
    )


def test_advanced_with_every_feature_on_shows_everything() -> None:
    assert all(shown(i, Uses(), NOTHING, advanced=True) for i in _listed())


def test_simple_mode_shows_the_core_and_what_the_inputs_use() -> None:
    starter = _example("starter")
    assert all(shown(i, Uses(), NOTHING, advanced=False) for i in mode.CORE)
    assert not any(shown(i, Uses(), NOTHING, advanced=False) for i in mode.EXPERT)
    shows = [
        _item(Sort.PATH, "indices"),  # an expert path that the file sets
        _item(Sort.PATH, "returns.*.stdev"),
        _item(Sort.KIND, "av_depot"),  # a kind of no core that the plan holds
        _item(Sort.COLUMN, "assets.update_every"),
        _item(Sort.PAGE, "Snapshot"),  # its records
        _item(Sort.PAGE, "Spend"),
    ]
    hides = [
        _item(Sort.PATH, "seed"),
        _item(Sort.PATH, "returns.*.equity_correlation"),
        _item(Sort.KIND, "term_deposit"),
        _item(Sort.EVENT, "sell"),  # nothing to sell
        _item(Sort.PAGE, "Data"),
    ]
    assert [shown(i, starter, NOTHING, advanced=False) for i in [*shows, *hides]] == [
        *(True for _ in shows),
        *(False for _ in hides),
    ]


def test_a_feature_off_hides_its_items_in_both_modes_unless_the_inputs_use_them() -> None:
    off = frozenset({Feature.GOLD_CRYPTO})
    gold = _item(Sort.KIND, "gold")
    assert not shown(gold, Uses(), off, advanced=True)
    assert not shown(_item(Sort.GROUP, sliders.GOLD_CRYPTO), Uses(), off, advanced=True)
    assert shown(gold, Uses(frozenset({gold})), off, advanced=False)
    assert shown(_item(Sort.KIND, "property"), Uses(), off, advanced=True)  # another feature
    # below the path of a feature: its fields
    care = frozenset({Feature.CARE})
    assert not shown(_item(Sort.PATH, "care.duration.mean"), Uses(), care, advanced=True)


def test_a_field_of_a_form_shows_by_the_deepest_listed_path_above_it() -> None:
    """A section that the inputs use shows whole (`care` with its spread at the default), a
    feature below it by its own path (VPW in the spending rule)."""
    paths = [
        ("care", "duration", "stdev"),
        ("spending", "vpw", "growth"),
        ("spending", "cut"),
        ("person", "born"),
        ("returns", "*", "equity_correlation"),
    ]
    assert [mode.head(p).key for p in paths] == [
        ("care",),
        ("spending", "vpw"),
        ("spending",),
        ("person", "born"),
        ("returns", "*", "equity_correlation"),
    ]


def _known_path(path: tuple[str, ...]) -> bool:
    """A field of the assumptions, a model above fields, or a column of a mapping by name
    (`returns.*.stdev`)."""
    fields = {f.path: f for f in of(Assumptions)}
    if "*" not in path:
        return any(p[: len(path)] == path for p in fields)
    at = path.index("*")
    held = fields.get(path[:at])
    return held is not None and len(path) == at + 2 and path[-1] in {c.name for c in held.columns}


COLUMNS = {
    "assets": {name for model in ASSET_MODELS.values() for name in model.model_fields},
    "streams": set(Stream.model_fields),
}
KNOWN: dict[Sort, Callable[[tuple[str, ...]], bool]] = {
    Sort.PAGE: lambda key: key[0] in mode.PAGES,
    Sort.KIND: lambda key: key[0] in ASSET_MODELS,
    Sort.STREAM: lambda key: key[0] in set(StreamKind),
    Sort.EVENT: lambda key: key[0] in TYPES,
    Sort.PATH: _known_path,
    Sort.COLUMN: lambda key: key[1] in COLUMNS[key[0]],
    Sort.OPTION: lambda key: key[:2] == ("streams", "deduct") and key[2] in set(Deduction),
    Sort.GROUP: lambda key: key[0] in sliders.GROUPS,
    Sort.DATA: lambda key: key[0] in mode.RECORDED,
}


def test_every_listed_item_exists() -> None:
    """Every page, kind, type, path, column and group of the tables of `mode` is one of the app:
    a renamed field would leave a line that hides nothing."""
    assert [i for i in _listed() if not KNOWN[i.sort](i.key)] == []


def test_a_required_field_of_an_optional_section_shares_its_tier() -> None:
    """A section switched on must not demand a field that the mode or a feature hides."""
    differ = [
        f.path
        for f in of(Assumptions)
        if f.section is not None and f.default is ABSENT and f.kind is not Kind.SECTION
        for field, section in [(Item(Sort.PATH, f.path), Item(Sort.PATH, f.section))]
        if (mode.core(field), mode.feature(field)) != (mode.core(section), mode.feature(section))
    ]
    assert differ == []


def test_the_pages_of_an_empty_plan(tmp_path: Path) -> None:
    """Simple mode shows nine pages, advanced every one, a feature off its pages in both."""
    datadir.start_empty(tmp_path, date(1985, 3, 14))
    found = mode.uses(tmp_path)
    assert mode.pages(found, NOTHING, advanced=False) == SIMPLE_PAGES
    assert mode.pages(found, NOTHING, advanced=True) == set(mode.PAGES)
    tracking = frozenset({Feature.TRACKING})
    assert mode.pages(found, tracking, advanced=True) == set(mode.PAGES) - {"Snapshot", "Spend"}


def test_the_navigation_registers_the_pages_of_the_mode(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A page that the navigation leaves out is None in `ui.PAGES`: no link goes there. The
    switch shows them, and a scenario that does not parse shows every page with the error."""
    monkeypatch.setenv(DATA_ENV, str(data))
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.query_params["mode"] = "simple"
    at.run()
    assert not at.exception
    pages = at.session_state[PAGES]
    assert {title for title, page in pages.items() if page is not None} == SIMPLE_PAGES
    assert set(pages) == set(mode.PAGES)
    at.sidebar.segmented_control(key=mode.MODE).set_value("advanced").run()
    assert None not in at.session_state[PAGES].values()
    at.sidebar.segmented_control(key=mode.MODE).set_value("simple").run()
    (data / "scenarios" / "broken.yaml").write_text("[\n")
    at.run()
    assert [e.value for e in at.error] == ["The inputs do not load:"]
    assert None not in at.session_state[PAGES].values()


SWITCH = """
import streamlit as st
from dagobert.ui import mode
st.markdown(str(mode.advanced()))
mode.mode_switch()
"""


def _advanced(at: AppTest) -> bool:
    return at.markdown[0].value == "True"


def test_the_mode_comes_from_the_query_the_switch_the_cookie_else_simple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simple without a choice: a new browser (owner, 2026-10-16). `?mode` is taken once, the
    switch keeps its choice and writes it into a cookie for the next visit."""
    assert SHIPPED == "simple"
    monkeypatch.setattr(mode, "DEFAULT", SHIPPED)
    assert not _advanced(AppTest.from_string(SWITCH).run())
    at = AppTest.from_string(SWITCH)
    at.query_params["mode"] = "advanced"
    at.run()
    assert _advanced(at)
    assert "mode" not in at.query_params
    assert _advanced(at.run())
    at.sidebar.segmented_control(key=mode.MODE).set_value("simple").run()
    assert not _advanced(at)
    scripts = [h.proto.body for h in at.get("html")]
    assert any(f"{mode.MODE_COOKIE}=simple;" in s for s in scripts)
    cookies = {mode.MODE_COOKIE: "advanced"}
    monkeypatch.setattr(ContextProxy, "cookies", property(lambda _: cookies))
    assert _advanced(AppTest.from_string(SWITCH).run())


def test_features_off_is_a_list_of_known_features(tmp_path: Path) -> None:
    (tmp_path / APP).write_text("features_off: [care, gold]\n")
    with pytest.raises(InputError, match=r"app\.yaml:1: features_off\[1\]"):
        load_app_settings(tmp_path)
    assert mode.features_off(tmp_path) == {Feature.CARE}  # the pages draw, the check names it


def test_the_note_names_what_a_page_hides() -> None:
    assert mode.hidden_text([], NOTHING, phone=False) == ""
    text = mode.hidden_text(["Random seed", "Plan up to age"], {Feature.CARE}, phone=True)
    assert text == (
        "Hidden in simple mode (at their defaults): Random seed and Plan up to age. Switch to "
        "Advanced in the menu to change them. Off in Features: long-term care. Turn them on there "
        "to use them."
    )
    for held, said in (
        (mode.Held.INHERITED, "(inherited from the files it extends)"),
        (mode.Held.VALUES, "(at the values as saved)"),
    ):
        assert mode.hidden_text(["Cut"], NOTHING, phone=False, held=held).startswith(
            f"Hidden in simple mode {said}: Cut."
        )
    features = {Feature.CHILDREN, Feature.ESTATES}
    assert mode.said(features) == "children; inheritance and gifts"  # a name holds an `and`
    kinds = mode.hidden_text(["term deposit"], NOTHING, phone=False, held=mode.Held.KINDS)
    assert kinds == (
        "Hidden in simple mode: term deposit. Switch to Advanced in the sidebar to use them."
    )


FEATURES_PAGE = """
from pathlib import Path
from dagobert.ui import features, told
told()
features.page(Path({data!r}))
"""


def _features_page(data: Path) -> AppTest:
    at = AppTest.from_string(FEATURES_PAGE.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    return at


def _started(tmp_path: Path, example: datadir.ExampleName) -> Path:
    datadir.start_example(data := tmp_path / "data", datadir.EXAMPLES / example)
    return data


def _all_on(data: Path) -> None:
    """`starter` without its preset: every feature on."""
    (data / APP).write_text("scenarios: [ausstieg, plan]\n")


def _off(data: Path) -> object:
    return references.read(data, APP).get(mode.FEATURES_OFF)


def test_the_features_page_locks_what_the_plan_uses(tmp_path: Path) -> None:
    """Every switch of `engineer` that has items is on and locked, and names where it is used."""
    at = _features_page(_started(tmp_path, "engineer"))
    locked = {f for f in Feature if at.toggle(key=f"features-{f}").disabled}
    assert locked == {f for f, spec in FEATURES.items() if spec.hides}
    assert all(at.toggle(key=f"features-{f}").value for f in Feature)
    uses = [c.value for c in at.caption if c.value.startswith("In use: ")]
    assert len(uses) == len(locked)
    assert "In use: `assets.yaml`: gold-coins (gold)" in uses[1]


def test_a_feature_switched_off_saves_app_yaml_alone_and_hides_its_items(tmp_path: Path) -> None:
    """The save guard lists the switch, Save writes one revision of `app.yaml`; switched on again
    the key goes."""
    _all_on(data := _started(tmp_path, "starter"))
    at = _features_page(data)
    assert at.button(key="features-save").disabled
    gold = at.toggle(key="features-gold_crypto")
    assert not gold.disabled
    gold.set_value(False).run()
    assert "**gold and crypto** on → off" in at.caption[-1].value
    at.button(key="features-save").click().run()
    assert not at.exception
    assert _off(data) == ["gold_crypto"]
    assert references.read(data, APP)["scenarios"] == ["ausstieg", "plan"]
    last = revisions.entries(data)[-1]
    assert (last.source, last.paths) == ("app", (APP,))
    off = mode.features_off(data)
    assert not shown(_item(Sort.KIND, "gold"), mode.uses(data), off, advanced=True)
    at.toggle(key="features-gold_crypto").set_value(True).run()
    at.button(key="features-save").click().run()
    assert mode.FEATURES_OFF not in references.read(data, APP)


def test_a_feature_off_that_the_plan_uses_shows_and_goes_with_the_next_save(
    tmp_path: Path,
) -> None:
    """A zip or a hand edit can switch off what the plan holds: its items show anyway, its switch
    is locked and says so, and the next Save drops it."""
    data = _started(tmp_path, "starter")
    (data / APP).write_text("scenarios: [ausstieg, plan]\nfeatures_off: [gold_crypto, care]\n")
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - {id: coins, kind: gold, value: 1000}\n")
    off, found = mode.features_off(data), mode.uses(data)
    assert shown(_item(Sort.KIND, "gold"), found, off, advanced=True)
    at = _features_page(data)
    gold = at.toggle(key="features-gold_crypto")
    assert gold.disabled and gold.value
    switched = "Switched off in `app.yaml`, but in use: it shows anyway."
    assert switched in [c.value for c in at.caption]
    assert not at.button(key="features-save").disabled
    at.button(key="features-save").click().run()
    assert _off(data) == ["care"]


def test_a_change_elsewhere_keeps_the_edits_and_save_off(tmp_path: Path) -> None:
    """A switch flipped while `app.yaml` changes elsewhere: a warning, Save off, `Discard my
    edits` reads the file again. Without a flip the page starts anew."""
    _all_on(data := _started(tmp_path, "starter"))
    at = _features_page(data)
    at.toggle(key="features-care").set_value(False).run()
    elsewhere = store.Edit(APP, {(mode.FEATURES_OFF,): ["children"]})
    store.write(data, [elsewhere], source="Features")
    at.run()
    assert at.warning and at.button(key="features-save").disabled
    at.button(key="features-discard").click().run()
    assert not at.toggle(key="features-children").value
    assert at.toggle(key="features-care").value
    store.write(data, [store.Edit(APP, {(mode.FEATURES_OFF,): None})], source="Features")
    at.run()
    assert not at.warning
    assert at.toggle(key="features-children").value


def _all_off(data: Path) -> None:
    with (data / APP).open("a") as fh:
        fh.write(f"features_off: [{', '.join(Feature)}]\n")


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("pages", [PAGE, EXPLORER], ids=["editors", "explorer"])
def test_the_pages_render_in_simple_mode(data: Path, pages: str, phone: bool) -> None:
    render(data, pages, phone=phone, mode="simple")


TABS = """
from pathlib import Path
from dagobert.store import streams_file
from dagobert.ui import cashflows
cashflows.page(streams_file(Path({data!r})))
"""


def _tabs(data: Path, *, simple: bool = True) -> AppTest:
    at = AppTest.from_string(TABS.format(data=str(data)), default_timeout=60)
    if simple:
        at.query_params["mode"] = "simple"
    at.run()
    assert not at.exception
    return at


def test_simple_mode_shows_the_tab_of_a_kind_once_a_row_holds_it(data: Path) -> None:
    """The BU policy, a stream kind outside the core: its tab shows with the first policy, until
    then the note below the tabs names it."""
    at, tab = _tabs(data), "disability insurance"
    assert tab not in [t.label for t in at.tabs]
    assert any("Disability insurance (BU)" in c.value for c in at.caption)
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: BU, cat: insurance, kind: bu, amount: 2000, premium: -80}\n")
    assert tab in [t.label for t in _tabs(data).tabs]


def test_disability_off_hides_the_bu_tab_in_advanced_mode_too(data: Path) -> None:
    """The note names the feature off; a policy brings the tab back."""
    tab = "disability insurance"
    assert tab in [t.label for t in _tabs(data, simple=False).tabs]
    (data / APP).write_text(f"features_off: [{Feature.DISABILITY}]\n")
    at = _tabs(data, simple=False)
    assert tab not in [t.label for t in at.tabs]
    assert any("Off in Features: disability" in c.value for c in at.caption)
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: BU, cat: insurance, kind: bu, amount: 2000, premium: -80}\n")
    assert tab in [t.label for t in _tabs(data, simple=False).tabs]


def test_simple_mode_speaks_german(data: Path) -> None:
    assert leaks(words(render(data, PAGE, lang="de", mode="simple"))) == []


@pytest.mark.parametrize("simple", [False, True])
def test_the_pages_render_with_every_feature_off(data: Path, simple: bool) -> None:
    """The Overview counts the features off that the plan does not use (it holds gold and crypto
    with trades, records, and VPW, a spending rule), with a link to the Features page."""
    _all_off(data)
    at = render(data, PAGE, mode="simple" if simple else None)
    n = len(Feature) - 3
    assert f"{n} parts of the app are switched off: the Features page turns them on." in [
        c.value for c in at.caption
    ]


SAVE_GRID = """
from pathlib import Path
from dagobert.loader import load_assumptions
from dagobert.store import assets_file, streams_file
from dagobert.ui import assets, cashflows, mode, tables
data = Path({data!r})
streams = {{"expenses": cashflows.EXPENSES, "income": cashflows.INCOME}}
streams["savings"] = cashflows.SAVINGS
if {grid!r} == "bu":
    tables.edit_table(streams_file(data), cashflows.BU, mode.view(data))
elif {grid!r} in streams:
    table = cashflows.with_phases(streams[{grid!r}], load_assumptions(data).phase_labels)
    tables.edit_table(streams_file(data), table, mode.view(data))
else:
    tables.edit_table(assets_file(data), assets.TABLES[{grid!r}], mode.view(data))
"""
# a visible cell per grid that no row holds with that value: a stream keeps its name, an asset
# takes another
EDITS: dict[str, dict[str, object]] = {
    "expenses": {"amount": 123},
    "income": {"end": "2090-01"},
    "savings": {"amount": 77},
    "bu": {"amount": 2100},
}
FILES = ("assets.yaml", "cashflows.yaml")


def _grids(example: datadir.ExampleName) -> list[str]:
    """The grids of the Assets and the Cashflows page that `example` fills."""
    assets, streams = (yaml.safe_load((datadir.EXAMPLES / example / f).read_text()) for f in FILES)
    kinds = {row.get("kind") for row in (*assets["assets"], *streams["streams"])}
    return [
        *(kind for kind in ASSET_MODELS if kind in kinds),
        *(grid for grid in EDITS if grid != "bu" or grid in kinds),
    ]


def _rows(data: Path) -> list[dict[KeyPath, object]]:
    """Every row of the assets and the streams by its key paths."""
    docs = [yaml.safe_load((data / file).read_text()) for file in FILES]
    return [flatten(row) for doc in docs for rows in doc.values() for row in rows]


@pytest.mark.parametrize(
    ("example", "grid"),
    [(example, grid) for example in ("starter", "engineer") for grid in _grids(example)],
)
def test_a_save_in_simple_mode_changes_only_the_cell_edited(
    tmp_path: Path, example: datadir.ExampleName, grid: str
) -> None:
    """The columns that simple mode hides keep their cells: a save of one visible cell changes
    that key of that row alone."""
    data = _started(tmp_path, example)
    at = AppTest.from_string(SAVE_GRID.format(data=str(data), grid=grid), default_timeout=60)
    at.query_params["mode"] = "simple"
    at.run()
    cell: dict[str, object] = EDITS.get(grid, {"name": "Changed"})
    before, key, edit = _rows(data), str(at.dataframe[0].key), {"edited_rows": {"0": cell}}
    edited(at, key, edit)
    next(b for b in at.button if str(b.key).endswith("-save")).click()
    edited(at, key, edit)  # a browser sends the edits with the press
    assert not at.exception
    changed = [
        path
        for old, new in zip(before, _rows(data), strict=True)
        for path in old.keys() | new.keys()
        if old.get(path) != new.get(path)
    ]
    assert changed == [tuple(cell)]
