"""The German catalogue against the code, the language of a session, its switch over the edits of a
grid, the German start page and the German pages of `Setup`. The rest of the suite runs in
English."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from babel.messages import Catalog
from babel.messages.catalog import Message
from german import ACTIVATE, edited, leaks, words
from streamlit.testing.v1 import AppTest

from dagobert import budget, i18n, i18n_check, revisions, transfer
from dagobert.model.assumptions import Assumptions
from dagobert.model.streams import Stream
from dagobert.runner import DATA_ENV
from dagobert.ui import COOKIE, LANGUAGE_LABEL, bars, fields, main
from dagobert.ui.gridcolumns import in_order
from dagobert.ui.save import changed_at

MAIN = main.__file__


def test_the_catalogue_serves_the_code() -> None:
    """Every message that the code marks is in the catalogue, translated, confirmed and with the
    placeholders of its English, and the catalogue holds no other."""
    assert i18n_check.problems(i18n.read("de"), i18n_check.extract()) == []


def test_translated_modules_show_no_words_outside_the_catalogue() -> None:
    assert i18n_check.lint() == []


def test_the_catalogue_names_no_address(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The header holds none of Babel's templates of an address (`EMAIL@ADDRESS`), also after a
    write of a catalogue that holds them."""
    shipped = i18n.catalogue_path("de")
    monkeypatch.setattr(i18n, "PACKAGE", tmp_path)
    i18n.catalogue_path("de").parent.mkdir(parents=True)
    i18n_check.write(Catalog(locale="de", header_comment="# Dagobert"), "de")
    for path in (shipped, i18n.catalogue_path("de")):
        header = path.read_text(encoding="utf-8").split("\n\n")[0]
        assert "ADDRESS" not in header
        assert "FULL NAME" not in header


def _catalogue(
    english: str | tuple[str, str], german: str | tuple[str, str] = "", context: str | None = None
) -> Catalog:
    catalogue = Catalog(locale="de")
    catalogue.add(english, german, context=context)
    return catalogue


@pytest.mark.parametrize(
    ("english", "german", "context", "found"),
    [
        ("Born {day}.", "Geboren am {tag}.", None, "its str.format fields differ"),
        ("Born {day}.", "Geboren am {day:%d}.", None, "its str.format fields differ"),
        ("Born {day}.", "Geboren am {day.", None, "its braces do not parse"),
        ("Born {day}.", "", None, "not translated"),
        (
            ("{n} file", "{n} files"),
            ("eine Datei", "{n} Dateien"),
            None,
            "its str.format fields differ",
        ),
        (("{n} file", "{n} files"), ("{n} Datei", ""), None, "not translated"),
        ("Set `scale`.", "Setze `Faktor`.", None, "its `code` differs"),
        ("%.0f months", "%d Monate", "sprintf", "its % conversions differ"),
        # a `%` outside a sprintf format is a word (Babel flags it as python-format), `{{` a brace
        ("5% chance", "5% Risiko", None, None),
        ("{{x}} is {x}", "{{x}} ist {x}", None, None),
    ],
)
def test_a_translation_keeps_the_placeholders_of_its_english(
    english: str | tuple[str, str],
    german: str | tuple[str, str],
    context: str | None,
    found: str | None,
) -> None:
    code = _catalogue(english, context=context)
    problems = i18n_check.problems(_catalogue(english, german, context=context), code)
    if found is None:
        assert problems == []
    else:
        [problem] = problems
        assert found in problem


def test_a_code_span_names_a_button_as_the_catalogue_says_it() -> None:
    """A YAML key in backticks stays; the name of a button may take its German."""
    english = "`Rename` above the table changes `id` too."
    catalogue, code = (
        _catalogue(english, "`Umbenennen` über der Tabelle ändert auch `id`."),
        _catalogue(english),
    )
    for found in (catalogue, code):
        found.add("Rename", "Umbenennen" if found is catalogue else "")
    assert i18n_check.problems(catalogue, code) == []
    catalogue[english].string = "`Umbenennen` über der Tabelle ändert auch `ID`."
    assert i18n_check.problems(catalogue, code) == [f"{english!r}: its `code` differs"]


def test_the_catalogue_holds_what_the_code_marks_and_nothing_else() -> None:
    catalogue = _catalogue("Plan", "Planen", context="navigation")
    catalogue.add("Start", "Starten", flags=["fuzzy"])
    catalogue.obsolete["Gone"] = Message("Gone", "Weg")
    code = _catalogue("Plan", context="navigation")
    code.add("Start")
    code.add("New")
    assert i18n_check.problems(catalogue, code) == [
        "'Gone': obsolete",
        "'New': not in the catalogue: run update",
        "'Start': fuzzy, confirm the translation",
    ]
    assert i18n_check.problems(catalogue, _catalogue("Start")) == [
        "'Gone': obsolete",
        "'Plan' (navigation): not in the code",
        "'Start': fuzzy, confirm the translation",
    ]


SHOWN = """
st.title("Start a plan")
st.title(_("Start a plan"))
column.button(f"Import {n}")
st.caption(f"**{_(title)}:** {_(text)}")
st.button(":material/chevron_left:", key="back")
st.text_input(_(BORN), placeholder="DD.MM.YYYY", help=_("{x}").format(x=1))
ui.page_link("Overview", "Open the Overview")
st.page_link(page, label=_("Open"))
st.tabs(["One", _("Two")])
st.code(str(err), language=None)
TITLE = N_("Start a plan")
st.caption(TITLE)
st.caption(_(TITLE))
st.markdown(f"**{TITLE}**")
st.markdown("Born {day}.".format(day=day))
st.markdown(_(TITLE).format(x=1))
FIRST, SECOND = N_("One"), N_("Two")
st.caption(SECOND)
"""


def test_a_streamlit_call_shows_no_english() -> None:
    """A literal with words outside `_()`, also in an f-string, a list or before `.format`, and a
    constant that the module marks `N_`; not an icon, an id or code."""
    found = i18n_check.untranslated(SHOWN, "m.py")
    assert [line.split(": ")[0] for line in found] == [
        "m.py:2",
        "m.py:4",
        "m.py:7",
        "m.py:8",
        "m.py:10",
        "m.py:13",
        "m.py:15",
        "m.py:16",
        "m.py:19",
    ]


@pytest.mark.parametrize(
    ("tags", "lang"),
    [
        (["de-CH"], "de"),
        (["fr", "de_AT"], "de"),
        (["EN-us", "de"], "en"),
        (["fr"], None),
        ([""], None),
    ],
)
def test_a_language_tag_names_a_language_of_the_app(tags: list[str], lang: str | None) -> None:
    assert i18n.negotiate(tags) == lang


def test_an_accept_language_header_goes_by_weight() -> None:
    assert i18n.preferred("fr;q=0.5, de-CH, en;q=0.8, it;q=0, *;q=0.1") == [
        "de-CH",
        "en",
        "fr",
        "*",
    ]
    assert i18n.negotiate(i18n.preferred("fr;q=2.5.1, de;q=0.9")) == "de"  # bad weight: no crash


def test_a_block_speaks_its_language() -> None:
    with i18n.use("de"):
        assert i18n._("Start a plan") == "Einen Plan starten"
        assert i18n.pgettext("navigation", "Plan") == "Planen"
        assert i18n._("Words of no message") == "Words of no message"
    assert i18n._("Start a plan") == "Start a plan"
    assert i18n.ngettext("{n} file", "{n} files", 2) == "{n} files"


@pytest.mark.parametrize("phone", [False, True])
def test_the_start_page_speaks_german(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phone: bool
) -> None:
    """`?lang=de` shows the start page in German, with the help and the date of birth in German
    words. The switch goes back to English, also in `<html lang>`, and keeps the choice in a
    cookie. The names and notes of the examples are data as written, German or English."""
    monkeypatch.setenv(DATA_ENV, str(tmp_path / "data"))
    at = AppTest.from_file(MAIN, default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    at.query_params["lang"] = "de"
    at.run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Einen Plan starten"]
    born = next(t for t in at.text_input if t.label == "Geburtsdatum")
    examples = next(e for e in at.expander if e.label == "Szenarien der Beispiele").markdown
    data = {m.value for m in examples}
    texts = [*(t for t in words(at) if t not in data), *(u.label for u in at.file_uploader)]
    assert leaks(texts) == []
    assert born.placeholder == "TT.MM.JJJJ"
    assert born.help.startswith("Geburtsdatum. Ein Geburtstag nach dem Monatsersten")
    born.set_value("20.05.1986").run()
    assert any(c.value.startswith("Geboren am 20. Mai 1986, Alter ") for c in at.caption)
    for key, text, line in [
        ("gross", "4.000", "Ohne die Punkte oder das Jahr "),
        ("since", "2016", "Geschätzt: "),
        ("born", "05.05.1950", "Ab 67 "),
    ]:  # the lines below the pension points and, at 67, below the savings plan
        at.text_input(key=f"decimal-welcome-{key}").set_value(text).run()
        assert any(c.value.startswith(line) for c in at.caption)
        assert leaks([t for t in words(at) if t not in data]) == []
        if key == "since":  # the estimate with a decimal comma
            assert any(re.match(r"Geschätzt: \d+,\d\d Rentenpunkte", c.value) for c in at.caption)
    assert "lang" not in at.query_params  # taken once: the switch can change it
    switch = next(s for s in at.sidebar.segmented_control if s.label == LANGUAGE_LABEL)
    switch.set_value("en").run()
    assert [t.value for t in at.title] == ["Start a plan"]
    scripts = [h.proto.body for h in at.get("html")]
    assert any(f"{COOKIE}=en;" in s for s in scripts)
    assert any('document.documentElement.lang = "en"' in s for s in scripts)


GRID = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import assets, tables
tables.edit_table(assets_file(Path({data!r})), assets.TABLES["cash"])
ui.language_switch()
"""


def test_a_language_switch_keeps_the_edits_of_a_grid(data: Path) -> None:
    """Streamlit draws a new editor for the German headers, without the edits of the old one:
    the switch carries them over, so the new grid shows them, and the guard and Save still have
    them in the runs after it."""
    at = AppTest.from_string(ACTIVATE + GRID.format(data=str(data)), default_timeout=30).run()
    edit = {"edited_rows": {"0": {"value": 2000}}}
    edited(at, "assets-cash-0", edit)
    assert [c.value for c in at.caption] == ["To save:  \n**giro value** 1.000 € → 2.000 €"]
    old = at.dataframe[0].proto.id
    next(s for s in at.sidebar.segmented_control if s.label == LANGUAGE_LABEL).set_value("de")
    edited(at, "assets-cash-0", edit)  # the old grid sends its edits with the switch
    assert not at.exception
    assert at.dataframe[0].proto.id != old  # a new editor
    assert at.dataframe[0].value["value"].tolist() == [2000]
    at.run()  # the new grid sends no edits
    assert [c.value for c in at.caption] == ["Zu speichern:  \n**giro Wert** 1.000 € → 2.000 €"]
    save = at.button(key="assets-cash-save")
    assert (save.label, save.disabled) == ("Speichern", False)


def _listed(at: AppTest) -> list[str]:
    """The list of the save guard."""
    return [c.value for c in at.caption if "→" in c.value]


SNAPSHOT = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import snapshot
snapshot.page(assets_file(Path({data!r})))
ui.language_switch()
"""


def test_a_language_switch_keeps_the_entries_of_the_snapshot(data: Path) -> None:
    """The Snapshot grid is a fixed editor with a key: Streamlit keeps it, with its entries, when
    its headers and some cells take other words, and the guard names a cell in German."""
    at = AppTest.from_string(ACTIVATE + SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    edit = {"edited_rows": {"0": {"new": 2000}}}
    edited(at, "snapshot-0", edit)
    assert _listed(at) == ["To save:  \n**giro value** 1.000 € → 2.000 €"]
    old = at.dataframe[0].proto.id
    next(s for s in at.sidebar.segmented_control if s.label == LANGUAGE_LABEL).set_value("de")
    edited(at, "snapshot-0", edit)
    assert not at.exception
    assert at.dataframe[0].proto.id == old  # the same editor
    assert _listed(at) == ["Zu speichern:  \n**giro Wert** 1.000 € → 2.000 €"]
    assert at.button(key="snapshot-save").label == "1 Änderung erfassen"


@pytest.mark.parametrize(
    ("lang", "said"), [("en", "`assets.yaml` changed"), ("de", "`assets.yaml` wurde geändert")]
)
def test_a_change_without_a_revision_since_names_the_file(lang: i18n.Language, said: str) -> None:
    with i18n.use(lang):
        assert changed_at(revisions.ConflictError("assets.yaml", [])) == said


@pytest.mark.parametrize(
    ("name", "german"),
    [
        ("income tax", "Einkommensteuer"),
        ("flat: transfer tax", "flat: Grunderwerbsteuer"),  # a label as written
        ("tax on one-offs: flat: transfer tax", "Steuer auf Einmalposten: flat: Grunderwerbsteuer"),
        ("income tax refund", "Erstattung Einkommensteuer"),
        ("KV refund", "Erstattung KV"),
        ("Miete: Nebenkosten", "Miete: Nebenkosten"),  # a stream with a colon
        ("tax refund", "tax refund"),  # a stream that ends like a refund
    ],
)
def test_a_name_of_the_ledger_says_its_words(name: str, german: str) -> None:
    """The ledger and the budget keep English names: the pages say their words, and a label, a
    name or a category as written."""
    with i18n.use("de"):
        assert budget.said(name) == german
    assert budget.said(name) == name


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_select_keeps_the_order_of_names_in_the_language_of_the_session(
    lang: i18n.Language,
) -> None:
    """A `Land` lists by its name in the language of the session (`Mecklenburg-Vorpommern` before
    `Niedersachsen`, English `Lower Saxony` first), whatever order the schema gives its names in;
    the stream kinds keep the order of the model."""
    land = next(f for f in fields.of(Assumptions) if f.path == ("tax", "land"))
    kind = next(f for f in fields.of(Stream) if f.path == ("kind",))
    with i18n.use(lang):
        names = [i18n._(dict(land.titles)[o]) for o in in_order(land.options, land.titles)]
        assert names == sorted(names)
        assert in_order(kind.options, kind.titles) == list(kind.options)


def test_items_that_read_alike_in_german_keep_their_bars() -> None:
    """The growth of the fixed income and an asset labeled `Anleihen` read alike in German."""
    run = budget.Budget(noncash={"fixed income": 10.0, "Anleihen": 5.0})
    with i18n.use("de"):
        assert [s.value for s in bars.noncash_of(run, set())] == [10.0, 5.0]


CASH = """
from pathlib import Path
from dagobert.store import streams_file
from dagobert.ui import cashflows, flows, spend
data = Path({data!r})
cashflows.page(streams_file(data))
spend.page(streams_file(data))
flows.page(data)
"""


@pytest.mark.parametrize("phone", [False, True])
def test_the_cash_pages_speak_german(data: Path, phone: bool) -> None:
    """The Cashflows, Spend and Flows pages show no English that the catalogue translates, also
    inside a sentence."""
    at = AppTest.from_string(ACTIVATE + CASH.format(data=str(data)), default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    at.query_params["lang"] = "de"
    at.run()
    assert not at.exception
    assert leaks(words(at)) == []
    assert [t.value for t in at.title] == ["Cashflows", "Ausgaben", "Flows"]


SPEND = """
from pathlib import Path
from dagobert.store import streams_file
from dagobert.ui import spend
spend.page(streams_file(Path({data!r})))
ui.language_switch()
"""


def test_a_language_switch_keeps_the_edits_of_the_spend_grid(data: Path) -> None:
    """The German headers make a new editor: it starts from the draft of the month, so it shows
    the edit, and Save still has it."""
    at = AppTest.from_string(ACTIVATE + SPEND.format(data=str(data)), default_timeout=30).run()
    old = next(g.key for g in at.dataframe if g.key)
    edit = {"edited_rows": {"0": {"actual": -40}}}
    edited(at, old, edit)
    next(s for s in at.sidebar.segmented_control if s.label == LANGUAGE_LABEL).set_value("de")
    edited(at, old, edit)  # the old grid sends its edits with the switch
    assert not at.exception
    [grid] = at.dataframe
    assert grid.key != old
    assert grid.value["actual"].tolist()[0] == -40
    at.run()  # the new grid sends no edits
    save = at.button(key="spend-save")
    assert (save.label, save.disabled) == ("Speichern", False)


DATES = """
from pathlib import Path
from dagobert.ui import scenario_overrides
scenario_overrides.tab(Path({path!r}))
ui.language_switch()
"""


def test_a_language_switch_keeps_the_edits_of_a_grid_by_id(data: Path) -> None:
    """The grids by id of the Overrides tab draw editors of their own: the switch carries them."""
    path = data / "scenarios" / "base.yaml"
    path.write_text(f"{path.read_text()}events: [{{type: lump_sum, at: 2030-01-01, id: car}}]\n")
    at = AppTest.from_string(ACTIVATE + DATES.format(path=str(path)), default_timeout=30).run()
    key, edit = "overrides-base-grids-0-shift", {"added_rows": [{"id": "car", "months": 12}]}
    edited(at, key, edit)
    next(s for s in at.sidebar.segmented_control if s.label == LANGUAGE_LABEL).set_value("de")
    edited(at, key, edit)  # the old grid sends its edits with the switch
    at.run()  # the new grid sends no edits
    assert not at.exception
    assert next(g for g in at.dataframe if g.key == key).value["id"].tolist() == ["car"]
    save = at.button(key="overrides-base-save")
    assert (save.label, save.disabled) == ("Speichern", False)


SETUP = """
from pathlib import Path
from dagobert.ui import assumptions, scenarios, transfer
from dagobert.ui import data as data_page
data = Path({data!r})
data_page.page(data)
assumptions.page(data)
scenarios.page(data)
transfer.page(data)
"""
# a parent with a sale on a condition and a one-off payment, a child with a purchase and a move
EVENTS = """\
events:
  - {type: sell, asset: flat, when: {age: 60}, id: flat-sale}
  - {type: lump_sum, at: 2030-01-01, amount: -5000, id: car}
"""
CHILD = """\
name: Child
extends: base
events:
  - {type: buy_property, at: 2031-01-01, property: {id: home, name: Home}, price: 300000, land: BY}
overrides: {shift: {car: 12}}
"""


def _changed(data: Path, value: int) -> None:
    text = (data / "assets.yaml").read_text().replace("value: 5000", f"value: {value}")
    assert revisions.write(data, "test", lambda: {"assets.yaml": text})


def _export(data: Path, dest: Path) -> Path:
    taken = transfer.export(data)
    (path := dest / taken.name).write_bytes(taken.zip(history=False))
    return path


@pytest.mark.parametrize("phone", [False, True])
def test_the_setup_pages_speak_german(
    data: Path, tmp_path_factory: pytest.TempPathFactory, phone: bool
) -> None:
    """The pages of `Setup` show no English message, also inside a text: the forms, the grids and
    the read-only tables with their headers, the events of a child and those that it inherits, its
    overrides, and the preview of an import that asks keep or take. A Land shows its German
    name."""
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - {id: flat, kind: property, sqm: 50, per_sqm: 3000}\n")
    base = data / "scenarios" / "base.yaml"
    base.write_text(base.read_text() + EVENTS)
    (data / "scenarios" / "child.yaml").write_text(CHILD)
    there = transfer.unpacked(_export(data, tmp_path_factory.mktemp("first")))
    _changed(there, 7000)
    back = _export(there, tmp_path_factory.mktemp("back"))
    _changed(data, 6000)  # changed on both sides: the import asks
    at = AppTest.from_string(ACTIVATE + SETUP.format(data=str(data)), default_timeout=60)
    at.query_params.update({"mobile": str(int(phone)), "lang": "de", "scenario": "child"})
    at.run()
    at.file_uploader(key="transfer-upload-0").upload(
        back.name, back.read_bytes(), "application/zip"
    )
    at.run()
    assert not at.exception
    assert [c.value for c in at.segmented_control if str(c.key).endswith("assets.yaml")] == [None]
    headers = [
        c.get("label") or n for g in at.dataframe for n, c in json.loads(g.proto.columns).items()
    ]
    headers += [str(c) for t in at.table for c in t.value.columns]
    assert leaks([*words(at), *headers]) == []
    assert any("Bayern" in s.options for s in at.selectbox)
