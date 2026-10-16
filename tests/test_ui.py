"""Every page drawn as a desktop and a phone, in English and in German: no exception, the
note of a scenario, the keys of the widgets, the charts and grids of a phone, no English in
German. The entry script, the first run, a widget over a language switch, the helpers of
every page."""

from __future__ import annotations

import ast
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from apps import ASSUMPTIONS, EXPLORER, MAIN, PAGE, labels, note, record, render
from german import leaks, words
from streamlit.testing.v1 import AppTest

from dagobert import (
    __version__,
    budget,
    datadir,
    goalseek,
    i18n,
    references,
    rename,
    report,
    revisions,
    schema,
    transfer,
)
from dagobert.runner import DATA_ENV
from dagobert.ui import (
    LANGUAGE,
    LANGUAGE_LABEL,
    PAGE_STYLE,
    PAGES,
    PER,
    Stamp,
    data_stamp,
    explorer,
    literal,
    main,
    mode,
    overview,
    run_stamp,
    runs,
    tables,
    welcome,
)
from dagobert.ui import rename as rename_ui


def _configs(at: AppTest) -> list[dict[str, Any]]:
    """The column configs of every grid."""
    return [c for g in at.dataframe for c in json.loads(g.proto.columns).values()]


RENDERED = pytest.mark.parametrize("pages", [PAGE, EXPLORER], ids=["editors", "explorer"])


@pytest.mark.parametrize("lang", ["en", "de"])
@pytest.mark.parametrize("phone", [False, True])
@RENDERED
def test_pages_render(data: Path, pages: str, phone: bool, lang: i18n.Language) -> None:
    """Every page renders as a desktop and a phone, in English and in German. The note of the
    scenario shows as written, as in the report, on the Overview, the Cashflows and the Flows page,
    as the main scenario on the Scenarios page and on each scenario tab of the explorer: a long one
    folds on a phone, but in the expander of the main scenario."""
    at = render(data, pages, phone=phone, lang=lang)
    shown, written = 4 if pages == PAGE else 1, literal(note(pages))
    notes = [[e.value for e in elements].count(written) for elements in (at.caption, at.markdown)]
    assert notes == ([1, shown - 1] if phone and pages == PAGE else [shown, 0])


@pytest.mark.parametrize("phone", [False, True])
@RENDERED
def test_the_pages_show_no_english_in_german(data: Path, pages: str, phone: bool) -> None:
    """German shows none of the English that the catalogue translates, also inside a text."""
    assert leaks(words(render(data, pages, phone=phone, lang="de"))) == []


def test_the_shared_helpers_speak_german(data: Path) -> None:
    at = render(data, PAGE, lang="de")
    assert at.button(key="assumptions-person-save").label == "Speichern"
    assert at.toggle(key="streams-expenses-more").label == "Alle Spalten"
    assert at.segmented_control(key="cashflows-per").label == "Beträge"
    assert "Geschlecht" in [c.label for c in at.segmented_control]  # a label of the model
    for key in ("cashflows-scenario", "flows-scenario"):  # the scenario of the Overview marked
        assert at.selectbox(key=key).options == ["base (Hauptszenario)"]
    assert {"Betrag", "Ist"} <= {c.get("label") for c in _configs(at)}  # Ist: the Spend grid
    # the sheet of the Cashflows page and the table of the Flows page say the ledger in words
    sheets = [str(t.value) for t in at.table]
    assert any("Überschuss" in t and "aus der Simulation" in t for t in sheets)
    assert any("Vermögenszuwachs" in t for t in sheets)


@pytest.mark.parametrize("lang", ["en", "de"])
def test_the_flows_table_names_the_savings_plans(data: Path, lang: i18n.Language) -> None:
    at = render(data, PAGE, lang=lang)
    with i18n.use(lang):
        saved = i18n._(budget.SAVED)
    assert any(saved in str(t.value) for t in at.table)


@pytest.mark.parametrize("lang", ["en", "de"])
@pytest.mark.parametrize("phone", [False, True])
def test_the_explorer_names_its_levers_in_the_language_of_the_session(
    data: Path, phone: bool, lang: i18n.Language
) -> None:
    at = render(data, EXPLORER, phone=phone, lang=lang)
    with i18n.use(lang):
        coins, rest = i18n._("{plan} per month").format(plan="Coins"), i18n._("Invest the rest")
        stop_help = goalseek.stop_help()
        main = i18n._(
            "Set as default makes {scenario}, the first one chosen, your main scenario."
        ).format(scenario="base")
        marked = i18n._("{scenario} (main)").format(scenario="base")
    header = labels(data, lang)[report.BROKE_AT]
    # the options mark the main scenario, as pills on a phone; its run keeps the name
    assert marked in {o for w in [*at.multiselect, *at.button_group] for o in w.options}
    assert [tab.label for tab in at.tabs] == ["base"]
    assert coins in [s.label for s in at.slider]
    assert rest in [t.label for t in at.toggle]
    # the help of the goal seek: a caption on a desktop, folded on a phone (`ui.note`)
    assert any(stop_help in e.value for e in (at.markdown if phone else at.caption))
    assert header in {c.get("label") for c in _configs(at)}  # the summary
    # pills show no order and a touch screen no help: a phone names the new main scenario
    assert (main in [c.value for c in at.caption]) == phone


def test_the_explorer_speaks_german(data: Path) -> None:
    at = render(data, EXPLORER, lang="de")
    assert "Coins pro Monat" in [s.label for s in at.slider]
    figures = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
    assert "Aktien" in [t.get("name") for f in figures for t in f["data"]]  # of the balance sheet


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize(
    ("pages", "names"),
    [
        (
            PAGE,
            {
                "asset",
                "id",
                "date",
                "name",
                "from",
                "month",
                "security",
                "at",
                "born",
                "label",
                "age",
            },
        ),
        (EXPLORER, {"Scenario"}),
    ],
    ids=["editors", "explorer"],
)
def test_a_phone_scrolls_over_a_chart_and_keeps_the_name_of_a_row_in_view(
    data: Path, pages: str, names: set[str], phone: bool
) -> None:
    """A swipe over a chart scrolls, and a tap that counts twice keeps the axes. The column that
    names a row stays in view, with the help of the columns in a popover."""
    at = render(data, pages, phone=phone)
    charts = at.get("plotly_chart")
    assert {json.loads(c.proto.spec)["layout"].get("dragmode") for c in charts} == {
        False if phone else None
    }
    resets = {json.loads(c.proto.config or "{}").get("doubleClick") for c in charts}
    assert resets == {False if phone else None}
    pinned = {
        name
        for grid in at.dataframe
        for name, column in json.loads(grid.proto.columns).items()
        if column.get("pinned")
    }
    assert pinned == (names if phone else set())
    popovers = {p.proto.popover.label for p in at.get("popover")}
    assert bool(popovers & {tables.COLUMNS_HELP, tables.COLUMNS_MEAN}) == phone


@pytest.mark.parametrize("phone", [False, True])
@RENDERED
def test_every_widget_and_editable_grid_has_a_key(data: Path, pages: str, phone: bool) -> None:
    """Without a key a widget takes its label as its identity: other words drop what it holds."""
    at = render(data, pages, phone=phone)
    widgets = [
        *at.button,
        *at.button_group,  # pills and segmented controls
        *at.checkbox,
        *at.color_picker,
        *at.date_input,
        *at.file_uploader,
        *at.multiselect,
        *at.number_input,
        *at.radio,
        *at.select_slider,
        *at.selectbox,
        *at.slider,
        *at.text_area,
        *at.text_input,
        *at.toggle,
    ]
    assert [w.label for w in widgets if w.key is None] == []
    assert [g.proto.columns for g in at.dataframe if g.proto.editing_mode and g.key is None] == []


def test_every_expander_has_a_key_but_the_help_fold() -> None:
    """Without a key an expander takes its label as its identity: other words, such as another
    language, or a value in its label close it. `AppTest` shows no key of an expander, so this
    reads the code. A help fold (`ui.fold`) starts closed and may close again."""
    keyless = {
        f"{path.stem}.{func.name}"
        for path in Path(main.__file__).parent.glob("*.py")
        for func in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(func, ast.FunctionDef)
        for call in ast.walk(func)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "expander"
        and all(k.arg != "key" for k in call.keywords)
    }
    assert keyless == {"__init__.fold"}


QUICK = datadir.Quick(date(1985, 3, 14), gross=4000, spending=2500, savings=10000, plan=300)


@pytest.mark.parametrize("phone", [False, True])
@pytest.mark.parametrize("mode", ["simple", "advanced"])
@pytest.mark.parametrize("pages", [PAGE, EXPLORER], ids=["editors", "explorer"])
@pytest.mark.parametrize("quick", [datadir.Quick(QUICK.born), QUICK], ids=["empty", "quick"])
def test_pages_render_an_empty_plan(
    tmp_path: Path,
    pages: str,
    mode: str,
    phone: bool,
    quick: datadir.Quick,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A first run's empty plan (no asset, no stream, no record) and a quick start, every feature
    off, in simple mode, which a start opens in, and in advanced mode. The desktop Explorer of
    advanced mode runs the whole sensitivity: at the fewest paths, with the time of a CI runner."""
    for module in (runs, explorer):
        monkeypatch.setattr(module, "PATHS", explorer.PATH_CHOICES[0])
    datadir.start_quick(tmp_path, quick)
    at = AppTest.from_string(pages.format(data=str(tmp_path)), default_timeout=120)
    at.query_params["mobile"] = str(int(phone))
    at.query_params["mode"] = mode
    at.run()
    assert not at.exception


AMOUNTS = """
import streamlit as st
from dagobert.ui import per_control
words, factor = per_control(st.container(), "amounts")
st.markdown(f"{words}, {factor}")
"""


def test_a_widget_keeps_its_choice_in_other_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """A widget has a key and its options are ids that its words show, so other words, as of
    another language, keep what it holds."""
    at = AppTest.from_string(AMOUNTS).run()
    at.segmented_control(key="amounts").set_value("year").run()
    monkeypatch.setitem(PER, "month", ("pro Monat", 1))
    monkeypatch.setitem(PER, "year", ("pro Jahr", 12))
    at.run()
    assert at.segmented_control(key="amounts").value == "year"
    assert [m.value for m in at.markdown] == ["pro Jahr, 12"]


QUICKLY = ("Start my plan", datadir.QUICK_START)


@pytest.mark.parametrize(
    ("button", "source", "typed", "landing", "notes"),
    [
        *((e.button, datadir.FROM_EXAMPLE, {}, "Overview", ()) for e in welcome.EXAMPLES),
        (*QUICKLY, {}, "Assumptions", ()),
        (*QUICKLY, {"gross": "4.000"}, "Overview", (welcome.NO_POINTS,)),
        (
            *QUICKLY,
            {"born": "05.05.1950", "gross": "4.000", "points": "8,5"},
            "Assumptions",
            (welcome.RETIRED,),
        ),
    ],
)
def test_a_first_run_starts_a_plan_and_opens_its_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    button: str,
    source: str,
    typed: dict[str, str],
    landing: str,
    notes: tuple[str, ...],
) -> None:
    """A missing data directory shows the start instead of the pages, with the language switch
    alone. An example opens the Overview; the quick start needs the date of birth, and a number
    that does not read keeps it off. It opens the Overview with a salary, else the Assumptions
    page, also at 67, where the salary does not pay: a line says so, as one says what the
    pension counts without points. The Overview of a new plan seeks when to stop working once."""
    data = tmp_path / "data"
    monkeypatch.setenv(DATA_ENV, str(data))
    sought: list[goalseek.Dial] = []

    def seek(job: object, dial: goalseek.Dial, progress: object) -> goalseek.Found:
        sought.append(dial)
        return goalseek.Found(dial.value, 0.01, 1, rising=False)

    monkeypatch.setattr(runs, "seek", seek)
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Start a plan"]
    assert [c.key for c in at.sidebar.segmented_control] == [LANGUAGE]
    assert not any(at.button(key=f"welcome-{e.name}").disabled for e in welcome.EXAMPLES)
    assert at.button(key="welcome-quick").disabled  # the quick start needs a birth date
    assert [u.label for u in at.file_uploader] == ["Choose a Dagobert export (.zip)"]
    at.text_input(key="decimal-welcome-born").set_value("14.03.1985").run()
    assert welcome.said(date(1985, 3, 14), date.today()) in [c.value for c in at.caption]
    at.text_input(key="decimal-welcome-cash").set_value("-5").run()
    assert at.button(key="welcome-quick").disabled
    at.text_input(key="decimal-welcome-cash").set_value("").run()
    for key, text in typed.items():
        at.text_input(key=f"decimal-welcome-{key}").set_value(text).run()
    captions = [c.value for c in at.caption]
    assert [n for n in (welcome.NO_POINTS, welcome.RETIRED) if n in captions] == list(notes)
    next(b for b in at.button if b.label == button).click().run()
    assert not at.exception
    assert [t.value for t in at.title] == [landing]
    assert [e.source for e in revisions.entries(data)] == [source]
    assert mode.MODE in [c.key for c in at.sidebar.segmented_control]
    assert len(sought) == (landing == "Overview")
    if sought:
        stop = next(m for m in at.metric if m.label == goalseek.STOP)
        assert stop.value == f"{sought[0].month(sought[0].value)[0]:%Y-%m}"  # type: ignore[index]
        at.run()
        assert len(sought) == 1  # once


@pytest.mark.parametrize(
    ("typed", "problems", "warned"),
    [
        ({"gross": "5.500", "spending": "3.000", "plan": "1.000"}, {}, True),
        ({"gross": "5.500", "spending": "3.000", "plan": "300"}, {}, False),
        ({"plan": "300"}, {}, True),  # no salary pays it
        ({"gross": "5.500", "lost": "2020-01"}, {"lost": "type a month from"}, False),
        ({"lost": "2030-01"}, {"lost": "a job loss needs a salary"}, False),
        ({"gross": "5.500", "stop": "50", "lost": "2040-01"}, {"lost": "before you stop"}, False),
        ({"gross": "5.500", "stop": "71"}, {"stop": "at most 70"}, False),
        ({"owed": "100.000"}, {"owed": "the value of the property"}, False),
    ],
)
def test_the_quick_start_checks_its_goals_and_the_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    typed: dict[str, str],
    problems: dict[str, str],
    warned: bool,
) -> None:
    """A goal that does not fit the other answers says why below its field and keeps the start
    off; a salary that leaves less than the spending and the savings plan warns, and the start
    stays on."""
    monkeypatch.setenv(DATA_ENV, str(tmp_path / "data"))
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    at.text_input(key="decimal-welcome-born").set_value("14.03.1985").run()
    if "owed" in typed:
        at.toggle(key="welcome-owner").set_value(True).run()
    for key, text in typed.items():
        at.text_input(key=f"decimal-welcome-{key}").set_value(text).run()
    assert not at.exception
    errors = [e.value for e in at.error]
    assert len(errors) == len(problems)
    assert all(any(p in e for e in errors) for p in problems.values())
    assert bool(at.warning) == warned
    assert at.button(key="welcome-quick").disabled == bool(problems)


@pytest.mark.parametrize(("phone", "history"), [(False, False), (True, True)])
def test_a_first_run_imports_an_export_and_opens_the_overview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phone: bool, history: bool
) -> None:
    """Every file of the zip is new: one revision `import <zip>`, or with the revisions of the
    zip its history."""
    datadir.start_empty(source := tmp_path / "source", date(1985, 3, 14))
    taken = transfer.export(source)
    data = tmp_path / "data"
    monkeypatch.setenv(DATA_ENV, str(data))
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    at.file_uploader[0].upload(taken.name, taken.zip(history=history), "application/zip").run()
    assert not at.exception and not at.error
    assert set(at.table[0].value["action"]) == {"add"}
    next(b for b in at.button if b.label.startswith("Import ")).click().run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Overview"]
    imported = datadir.EMPTY_PLAN if history else f"import {taken.name}"
    assert [e.source for e in revisions.entries(data)] == [imported]
    assert dict(schema.Tree(data)).keys() == dict(schema.Tree(source)).keys()


def test_a_rename_lists_the_first_lines_of_each_file() -> None:
    """The history of an asset can hold many rows: past `SHOWN` a file names their number."""
    rows = rename_ui.SHOWN + 2
    shown = rename.Preview(
        rename.Rename(references.Kind.ASSET, "a", "b"),
        {"assets.yaml": "  - id: a\n", "history.csv": "date,asset,value\n" + "d,a,1\n" * rows},
        {"assets.yaml": "  - id: b\n", "history.csv": "date,asset,value\n" + "d,b,1\n" * rows},
        (),
    )
    found, more = rename_ui.listing(shown)
    assert [c.text for c in found[:2]] == [
        "**assets.yaml:1** \\- id: a → \\- id: b",
        "**history.csv:2** d,a,1 → d,b,1",
    ]
    assert (len(found), more) == (1 + rename_ui.SHOWN, ["2 more lines of `history.csv`"])


@pytest.mark.parametrize(
    ("file", "text", "shown"),
    [
        ("assets.yaml", "assets:\n  - {id: giro, kind: cash, valu: 1}\n", "assets.yaml:2: assets"),
        ("manifest.yaml", "schema: 9\napp: 9.0.0\n", "manifest.yaml: schema 9, written by"),
    ],
)
def test_the_app_shows_inputs_that_do_not_load(
    data: Path, monkeypatch: pytest.MonkeyPatch, file: str, text: str, shown: str
) -> None:
    """The entry script opens the data directory before the page, and an input that does not
    load names its file, line and key path instead of a traceback. The language switch stays."""
    monkeypatch.setenv(DATA_ENV, str(data))
    (data / file).write_text(text)
    at = AppTest.from_file(MAIN, default_timeout=30).run()
    assert not at.exception
    assert [e.value for e in at.error] == ["The inputs do not load:"]
    assert at.code[0].value.startswith(shown)
    switch = next(s for s in at.sidebar.segmented_control if s.label == LANGUAGE_LABEL)
    assert switch.value == "en"


def test_a_link_to_the_roll_forward_opens_the_overview_of_the_navigation(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The link takes the very page that the navigation registers: one built again would need
    the same `url_path`, and Streamlit drops a link to an unknown page without an error."""
    monkeypatch.setenv(DATA_ENV, str(data))
    app = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not app.exception
    pages = app.session_state[PAGES]
    assert pages["Overview"].url_path == ""  # the default page, served at `/`
    at = AppTest.from_string(ASSUMPTIONS.format(data=str(data)), default_timeout=60)
    at.session_state[PAGES] = pages
    at.run()
    [link] = at.get("page_link")
    assert (link.proto.label, link.proto.page) == ("Roll forward on the Overview", "")
    assert link.proto.query_string == f"{overview.ROLL}={overview.OPEN}"  # opens the expander
    assert not AppTest.from_string(ASSUMPTIONS.format(data=str(data))).run().get("page_link")
    # while the start is current there is nothing to roll
    path = data / "assumptions.yaml"
    path.write_text(path.read_text().replace("2026-01-01", f"{date.today():%Y-%m}-01"))
    at.run()
    assert not at.get("page_link")


def test_the_runs_follow_what_they_read_only(data: Path) -> None:
    """The cache key of the runs: the plan and a fetched series count. `app.yaml` and the
    manifest, which the other caches of the inputs follow, do not, nor does a file elsewhere."""

    def touched(path: str, offset: float) -> Stamp:
        (data / path).parent.mkdir(parents=True, exist_ok=True)
        (data / path).touch()  # keeps an existing file
        os.utime(data / path, (base + offset, base + offset))
        return run_stamp(data)

    before = run_stamp(data)
    base = before[0]
    assert touched("revisions/1/assets.yaml", 10) == before
    assert touched("prices/IE00B4L5Y983.csv", 20) == before
    for offset, path in enumerate(("app.yaml", "manifest.yaml"), 30):
        assert touched(path, offset) == before
        assert data_stamp(data)[0] == base + offset
    assert touched("series/vpi.csv", 40) == (base + 40, before[1] + 1)
    last = touched("scenarios/base.yaml", 50)
    assert last[0] == base + 50
    (data / "series/vpi.csv").unlink()  # removing a file that is not the newest counts
    assert run_stamp(data) == (base + 50, last[1] - 1)


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        ("*the* flat_1 at $5 [a](b) `c`", r"\*the\* flat\_1 at \$5 \[a\](b) \`c\`"),
        ("- one\n+ two\n12. three\n1) four", "\\- one\n\\+ two\n12\\. three\n1\\) four"),
        ("Then\n===\n# end", "Then\n\\===\n\\# end"),
    ],
)
def test_literal_keeps_text_as_written(text: str, shown: str) -> None:
    """No emphasis, LaTeX, link, code, list, heading or rule: the app shows a note as the report."""
    assert literal(text) == shown


NOTE = """
from dagobert.ui import note
note("How to read the page.")
"""


def test_a_phone_folds_a_note_for_the_session() -> None:
    def shown(query: dict[str, str]) -> tuple[list[str], list[str]]:
        at.query_params.clear()
        at.query_params.update(query)
        at.run()
        return [c.value for c in at.caption], [m.value for m in at.markdown]

    at = AppTest.from_string(NOTE)
    text = ["How to read the page."]
    assert shown({}) == (text, [])  # no user agent: a desktop
    assert shown({"mobile": "1"}) == ([], text)  # folded
    assert shown({}) == ([], text)  # a page switch drops the query
    assert shown({"mobile": "0"}) == (text, [])


def test_the_page_style_survives_the_sanitizer() -> None:
    """`st.html` drops a whole style whose text holds an opening angle bracket before a letter,
    `/` or `!` (DOMPurify), without a word: every rule of the app would go."""
    style = PAGE_STYLE.removeprefix("<style>").removesuffix("</style>")
    assert not re.search(r"<[A-Za-z/!]", style)


DAYS = ("20260120T120000.000000+0000", "20260305T120000.000000+0000")


def test_pages_compare_with_the_revisions_of_earlier_days(data: Path) -> None:
    """A baseline on one day, a change of the streams on a later one: On track lists both days,
    Changes since and the Flows comparison the later one, against the inputs before it."""
    (data / "history.csv").write_text("date,asset,value\n2026-03-15,giro,1100.00\n")
    record(data, DAYS[0], "baseline", {})
    streams = (data / "cashflows.yaml").read_text().replace("-500", "-450")
    record(data, DAYS[1], "Cashflows", {"cashflows.yaml": streams})
    at = AppTest.from_string(PAGE.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    days = ["2026-03-05 · Cashflows", "2026-01-20 · baseline"]
    assert at.selectbox(key="overview-track-day").options == days
    assert any(m.value.startswith("The last record, 2026-03") for m in at.markdown)
    assert at.selectbox(key="cashflows-since").options == days[:1]
    assert any("amount: -500 € → -450 €" in t.value.to_string() for t in at.table)
    assert at.selectbox(key="flows-since").options == days[:1]
    assert any("the inputs before 2026-03-05" in c.value for c in at.caption)
    at.segmented_control(key="overview-track-what").set_value("liquid").run()
    assert not at.exception
    assert any(m.value.startswith("The last record, 2026-03") for m in at.markdown)


def test_app_opens_on_the_overview(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The first run records the inputs as they are, then the manifest of a folder by hand."""
    monkeypatch.setenv(DATA_ENV, str(data))
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    assert not at.exception
    assert at.title[0].value == "Overview"
    assert [e.source for e in revisions.entries(data)] == [
        "baseline",
        f"manifest {schema.current()} (Dagobert {__version__})",
    ]
    at.run()
    assert len(revisions.entries(data)) == 2
