"""The save guard: what a save writes, its warnings, its words in the language of the
session, the date of a new value, why a save failed."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
from apps import STREAMS
from streamlit.testing.v1 import AppTest

from dagobert import i18n, revisions
from dagobert.loader import load_assets
from dagobert.model.assets import CashAsset, Trade
from dagobert.model.assumptions import CareOptions
from dagobert.model.base import Unit
from dagobert.model.streams import Stream, StreamKind
from dagobert.store import RowEdits
from dagobert.ui import assumptions as assumptions_page
from dagobert.ui import cashflows, formguard, gridcolumns, guard, save

if TYPE_CHECKING:
    from pathlib import Path


def test_stamp_dates_new_values() -> None:
    rows = [
        {"id": "giro", "kind": "cash", "value": 1.0, "asof": "2026-01-01"},
        {"id": "loan", "kind": "loan", "balance": -5.0},
        {"id": "depot", "kind": "equity", "value": 1.0},
    ]
    today, earlier = date(2026, 9, 18), date(2026, 8, 31)
    edits = RowEdits(
        edited={0: {"value": 2.0}, 1: {"balance": -4.0, "asof": earlier}, 2: {"name": "Depot"}},
        added=[{"kind": "cash", "id": "neu", "value": 7.0}],
    )
    stamped, observed = save.stamp(rows, edits, today)
    assert observed == [(today, "giro", 2.0), (earlier, "loan", -4.0), (today, "neu", 7.0)]
    assert stamped.edited[0] == {"value": 2.0, "asof": today}
    assert stamped.edited[2] == {"name": "Depot"}
    assert stamped.added[0]["asof"] == today
    assert "asof" not in edits.edited[0]  # the edits of the grid stay as typed


def test_guard_counts_the_rows_of_a_list_that_changed_elsewhere() -> None:
    buy = {"date": date(2026, 1, 5), "kind": "buy", "security": "XAU", "units": 1}
    before = [{"id": "depot", "kind": "equity", "value": 9.0, "trades": [buy]}]
    after = [before[0] | {"trades": [buy, buy | {"units": 2}]}]
    difference = RowEdits.between(before, after, ("id",))
    assert [c.text for c in guard.changes(before, difference, units=gridcolumns.asset_units())] == [
        "**depot trades** 1 row → 2 rows"
    ]


def test_guard_lists_the_date_of_a_value_typed_again() -> None:
    rows = [{"id": "giro", "kind": "cash", "value": 1.0}]
    edits = RowEdits(edited={0: {"value": 1.0}})
    stamped, _observed = save.stamp(rows, edits, date(2026, 9, 18))
    assert guard.changes(rows, stamped, units=gridcolumns.asset_units()) == [
        guard.Change("giro asof", None, "2026-09-18", Unit.DATE)
    ]


@pytest.mark.parametrize(
    ("change", "warning"),
    [
        (guard.Change("x", 100.0, 150.0), None),  # within half and twice the old value
        (guard.Change("x", 100.0, 49.0), "0.49 times the old value"),
        (guard.Change("x", 100.0, 201.0), "2.01 times the old value"),
        (guard.Change("x", 12.34, 12340.0), "1000 times the old value"),
        (guard.Change("x", 1234.56, 1.23), "1/1004 of the old value"),
        (guard.Change("x", 100.0, 271.0), "2.71 times the old value"),
        (guard.Change("x", -50.0, 0.0), "set to zero"),
        (guard.Change("x", -500.0, 500.0), "the sign changed"),
        (guard.Change("x", None, 0.0), None),  # a month without spending
        (guard.Change("x", 0.0, 5.0), None),
        (guard.Change("x", 100.0, None), None),
        # `2,50` in a grid of an English browser reads 250
        (guard.Change("x", 0.025, 2.5, Unit.PERCENT), "above 100%"),
        # one more receipt of the quick add is no jump, a sum above zero is a refund
        (guard.Change("x", -5.0, -25.0, outflow=True, ratio=False), None),
        (
            guard.Change("x", 10.0, 5.0, outflow=True, ratio=False),
            "above zero, which records a refund",
        ),
    ],
)
def test_guard_warns_of_a_jump_or_a_sign_change(change: guard.Change, warning: str | None) -> None:
    assert change.warning == warning


def test_guard_shows_each_number_in_the_unit_of_its_field() -> None:
    """The unit comes from the model of the grid, not from the name: the `cost` of care is
    euros, the `cost` of an asset a share. A share or a rate above 100% gets a warning."""
    care = guard.changes(
        [{"cost": 3000.0}],
        RowEdits(edited={0: {"cost": 3500.5}}),
        units=gridcolumns.units(gridcolumns.columns(CareOptions)),
    )
    assert [c.text for c in care] == ["**cost** 3.000 € → 3.500,50 €"]
    rows: list[gridcolumns.Row] = [{"id": "kredit", "rate": 0.011, "cost": 0.002}]
    edits = RowEdits(
        edited={0: {"rate": 0.0298, "cost": 0.003}}, added=[{"name": "Bonus", "share": 15.0}]
    )
    rate, cost, share = guard.changes(
        rows, edits, units=gridcolumns.asset_units() | cashflows.INCOME.units()
    )
    assert (rate.text, cost.text) == ("**kredit rate** 1.1% → 2.98%", "**kredit cost** 0.2% → 0.3%")
    assert rate.warning == "2.71 times the old value"
    assert (share.text, share.warning) == ("**Bonus share** empty → 1500%", "above 100%")
    with pytest.raises(ValueError, match="less than or equal to 1"):
        Stream(name="Bonus", kind=StreamKind.SALARY, of="Gehalt", share=15)


def test_a_hebesatz_above_100_percent_is_no_slip() -> None:
    """The Gewerbesteuer-Hebesatz is 200% or more by law. The guard knows it by the field of the
    cell, so a label in words keeps it."""
    rows: list[gridcolumns.Row] = [{"name": "Consulting", "hebesatz": 4.1, "share": 0.1}]
    edits = RowEdits(edited={0: {"hebesatz": 4.3, "share": 1.5}})
    hebesatz, share = guard.changes(rows, edits, units=cashflows.INCOME.units())
    assert (hebesatz.text, hebesatz.warning) == ("**Consulting hebesatz** 410% → 430%", None)
    assert share.warning == "above 100%"


def test_guard_lists_the_rows_in_the_order_of_the_grid() -> None:
    rows: list[gridcolumns.Row] = [
        {"id": "a", "value": 1.0},
        {"id": "b", "value": 1.0},
        {"id": "c"},
    ]
    edits = RowEdits(edited={0: {"value": 1.5}, 1: {"value": 1.5}}, deleted=[2])
    units = gridcolumns.asset_units()
    assert [c.label for c in guard.changes(rows, edits, [1, 2, 0], units=units)] == [
        "b value",
        "a value",
    ]
    assert [c.label for c in guard.changes(rows, edits, units=units)] == ["a value", "b value"]


def test_guard_lists_the_numbers_to_save() -> None:
    rows: list[gridcolumns.Row] = [
        {"id": "giro", "kind": "cash", "value": 1000},
        {"name": "Miete_alt", "amount": -500.5, "factor": {"alt": 0.8}},
        {"id": "depot", "kind": "equity", "value": 1000, "asof": "2026-01-01"},
    ]
    edits = RowEdits(
        edited={
            1: {"amount": -520.0, "name": "Miete", "factor": {"alt": 0.8, "work": 0.9}},
            0: {"value": 1000.0, "asof": date(2026, 9, 1)},
            2: {"value": 2000.0, "asof": date(2026, 9, 1)},
        },
        added=[{"date": date(2026, 9, 2), "name": "World", "units": 1.5}, {"value": 7.0}],
    )
    units = (
        gridcolumns.asset_units() | STREAMS.units() | gridcolumns.units(gridcolumns.columns(Trade))
    )
    found = guard.changes(rows, edits, units=units)
    assert found == [
        # the value is the same, so the date is all that changes
        guard.Change("giro asof", None, "2026-09-01", Unit.DATE),
        guard.Change("Miete_alt amount", -500.5, -520.0),
        guard.Change("Miete_alt name", "Miete_alt", "Miete", None),
        guard.Change("Miete_alt factor work", None, 0.9, Unit.FACTOR),
        guard.Change("depot value", 1000.0, 2000.0),  # its date comes with the new value
        guard.Change("2026-09-02 World units", None, 1.5, Unit.NUMBER),
        guard.Change("value", None, 7.0),
    ]
    assert found[1].text == r"**Miete\_alt amount** -500,50 € → -520 €"


@pytest.mark.parametrize(
    ("label", "hint"), [("returns equity mean", guard.LOCALE), ("refinance_rate", "")]
)
def test_the_sentence_on_the_browser_language_comes_with_a_grid_cell_only(
    label: str, hint: str
) -> None:
    """A text field reads a comma and a point alike, a number cell of a grid by the language."""
    jump = guard.Change(label, 0.05, 0.5, unit=Unit.PERCENT)
    assert jump.warning
    assert assumptions_page.hint(assumptions_page.TABS[1].form(), [jump]) == hint


def test_a_line_of_the_guard_names_its_field_in_the_language_of_the_session() -> None:
    """A German line names each key of a form or a grid in German, an entry, a row and a name as
    written; the sentence on the browser language and the factors of a scenario find the field by
    its English key (`Change.named`)."""
    form = assumptions_page.TABS[1].form()
    returns = next(f for f in form.fields if f.path == ("returns",))
    part = {"returns": {"equity": {"mean": 0.05}}}
    rows = [{"name": "Rent", "amount": -900.0}]
    edits = RowEdits(edited={0: {"amount": -950.0}})
    with i18n.use("de"):
        [change] = formguard.changes(part, {"returns": {"equity": {"mean": 0.5}}}, [returns])
        names = cashflows.EXPENSES.names()
        [line] = guard.changes(rows, edits, units={"amount": Unit.EUR}, names=names)
        assert change.text == "**Renditen equity Mittelwert** 5\u00a0% → 50\u00a0%"
    assert change.named == "returns equity mean"
    assert assumptions_page.hint(form, [change]) == guard.LOCALE
    assert (line.label, line.named) == ("Rent Betrag", "Rent amount")


@pytest.mark.parametrize(
    ("err", "said"),
    [
        (revisions.BusyError("busy"), "Gerade läuft ein anderes Speichern. Speichere noch einmal."),
        (revisions.ReadOnlyError("read-only"), "das Datenverzeichnis ist schreibgeschützt"),
        (ValueError("assets[0].value: Input should be a valid number"), None),
    ],
)
def test_a_failed_save_says_why_in_the_language_of_the_session(
    err: Exception, said: str | None
) -> None:
    """A lock held by another save and a read-only data directory in German by their type; a
    refusal of the model or the inputs as they write it, in English."""
    with i18n.use("de"):
        assert save.reason(err) == (said or str(err))


# a save of a page inside `recording`, under the line of the session and the last save of the
# Overview, as `main.py` and the Overview draw them
SAVES = """
from pathlib import Path
import streamlit as st
from dagobert.store import RowEdits, assets_file
from dagobert.ui import recording, told, undo
data = Path({data!r})
told()
with st.container(key=undo.LINE):
    undo.line(data)
with recording():
    undo.last(data)
    if st.button("Save", key="save"):
        assets_file(data).apply(RowEdits({{0: {{"value": 1500}}}}), source="Snapshot")
        st.rerun()
"""


def _giro(data: Path) -> float:
    giro = next(a for a in load_assets(data) if a.id == "giro")
    assert isinstance(giro, CashAsset)
    return giro.value


def _undo_line(at: AppTest) -> str:
    return next(c.value for c in at.caption if c.value.startswith(":material/history:"))


def _phone(data: Path) -> None:
    """A save of the same file on another device."""
    text = (data / "assets.yaml").read_text().replace("1500", "1600")
    revisions.write(data, "Phone", lambda: {"assets.yaml": text})


def test_the_last_save_of_the_session_offers_its_undo(data: Path) -> None:
    """Until the next save: an undo writes the files as before the save, and its own undo
    restores it; a later save of the same files elsewhere keeps it off, and then the Overview
    offers that one."""
    at = AppTest.from_string(SAVES.format(data=str(data)), default_timeout=30).run()
    assert not [b for b in at.button if b.key in ("undo", "overview-undo")]  # nothing saved yet
    at.button(key="save").click().run()
    assert _undo_line(at).startswith(":material/history: Saved at ")
    assert _undo_line(at).endswith(" on Snapshot.")
    assert "overview-undo" not in [b.key for b in at.button]  # the line of the session has it
    at.button(key="undo").click().run()
    assert not at.exception
    assert _giro(data) == 1000
    assert revisions.entries(data)[-1].source == "app: undo"
    assert _undo_line(at).startswith(":material/history: Took back the save at ")
    assert at.toast[0].value.startswith("Took back the save at ")
    at.button(key="undo").click().run()  # the undo of the undo
    assert _giro(data) == 1500
    _phone(data)
    at.run()
    assert "Undo is off: `assets.yaml` changed at " in _undo_line(at)
    assert "undo" not in [b.key for b in at.button]
    at.button(key="overview-undo").click().run()
    assert not at.exception
    assert _giro(data) == 1500
    assert _undo_line(at).endswith(" on Phone.")  # what it took back, though the page records
    assert _undo_line(at).startswith(":material/history: Took back the save at ")
