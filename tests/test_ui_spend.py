"""The Spend page: the comparison with the plan, the quick add, the grid and its drafts,
a category changed elsewhere."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from builders import spent
from streamlit.testing.v1 import AppTest

from dagobert import actuals, revisions
from dagobert.model.months import add_months
from dagobert.ui import guard, spend

SPEND = """
from pathlib import Path
from dagobert.store import streams_file
from dagobert.ui import spend
spend.page(streams_file(Path({data!r})))
"""


def _shown_month(at: AppTest) -> date | None:
    """The month of the grid."""
    return next(s for s in at.selectbox if s.label == "Month").value


def test_a_link_opens_its_month(data: Path) -> None:
    """`?month=YYYY-MM` of the Overview opens that month; a month without the choices, none."""
    linked = add_months(date.today().replace(day=1), -3)
    at = AppTest.from_string(SPEND.format(data=str(data)), default_timeout=30)
    at.query_params[spend.SHOW] = f"{linked:%Y-%m}"
    at.run()
    assert not at.exception
    assert _shown_month(at) == linked
    assert spend.linked("2026-13") is None


def test_spend_page_compares_the_recorded_months(data: Path) -> None:
    # conftest: Miete -500 in wohnen
    spent(data, date(2026, 7, 1), {"wohnen": -520.0, "bargeld": -60.0})
    spent(data, date(2026, 8, 1), {"wohnen": -500.0})
    at = AppTest.from_string(SPEND.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    # the grid and the quick add start on the current month
    this = date.today().replace(day=1)
    assert _shown_month(at) == this == _quick(at)[2]
    next(b for b in at.button if b.help == "Previous month").click().run()
    assert not at.exception
    assert _shown_month(at) == add_months(this, -1)
    table = at.table[0].value
    assert list(table.columns)[1] == "months"  # `ui/page.css` hides it in portrait by position
    assert table["category"].tolist() == ["bargeld", "wohnen", "total"]
    assert table["plan"].tolist() == [0.0, -1000.0, -1000.0]
    assert table["difference"].tolist() == [-60.0, -20.0, -80.0]


def test_spend_grid_records_the_cells_it_holds() -> None:
    shown: list[tuple[str, float | None]] = [("reisen", None), ("sport", -40.0), ("wohnen", -900.0)]
    state = {
        "edited_rows": {"0": {"actual": -120.0}, "1": {"actual": None}, "2": {"category": "miete"}},
        "added_rows": [
            {"category": "bargeld", "actual": -50.0},
            {"category": " reisen "},
            {"category": "Reisen ", "actual": -5.5},  # a phone keyboard starts with a capital
            {"actual": -1.0},
            {"category": "Kino", "actual": -8.0},  # new twice: the first spelling counts
            {"category": "kino", "actual": -4.0},
        ],
        "deleted_rows": [],
    }
    assert spend.entered(shown, state) == {
        "reisen": -125.5,
        "miete": -900.0,
        "bargeld": -50.0,
        "Kino": -12.0,
    }
    assert spend.entered(shown, {"deleted_rows": [2]}) == {"sport": -40.0}
    plan = {"reisen": -100.0, "grundsteuer": -10.0833}
    assert spend.take_plan(plan, {"reisen": 0.0}) == {"reisen": 0.0, "grundsteuer": -10.08}


def test_spend_save_lists_the_categories_and_flags_an_amount_above_zero() -> None:
    found = spend.changes(
        {"wohnen": -900.0, "sport": -40.0, "reisen": -10.0},
        {"wohnen": -900.0, "sport": 40.0, "bargeld": -20.5, "kino": 12.0},
    )
    assert [(c.label, c.old, c.new) for c in found] == [
        ("bargeld", None, -20.5),
        ("kino", None, 12.0),
        ("reisen", -10.0, None),
        ("sport", -40.0, 40.0),
    ]
    assert [bool(c.warning) for c in found] == [False, True, False, True]


def _quick(at: AppTest) -> list[object]:
    """What the quick add form holds: category, amount, month."""
    return [
        next(w for w in widgets if w.label == label).value
        for widgets, label in (
            (at.selectbox, "Category"),
            (at.text_input, "Spent"),
            (at.selectbox, "Add to month"),
        )
    ]


def _add(at: AppTest, cat: str | None, spent: str, month: date | None = None) -> None:
    """A quick add on the Spend page, in the month of the form unless `month` is given."""
    next(s for s in at.selectbox if s.label == "Category").set_value(cat)
    next(t for t in at.text_input if t.label == "Spent").set_value(spent)
    if month:
        next(s for s in at.selectbox if s.label == "Add to month").set_value(month)
    next(b for b in at.button if b.label == "Add").click().run()
    assert not at.exception


def test_spend_quick_add_saves_at_once_and_adds_to_the_month(data: Path) -> None:
    month = date.today().replace(day=1)
    spent(data, month, {"wohnen": -500.0})
    at = AppTest.from_string(SPEND.format(data=str(data)), default_timeout=30).run()
    _add(at, "wohnen", "20,5")  # positive, saved negative
    _add(at, "wohnen", "1.500")
    assert actuals.read(data)[month] == {"wohnen": -2020.5}
    # a line under the form in the sign of the form, no toast, and a button to the month
    assert _said(at) == (
        f":material/check_circle: Added 1.500,00 € to **wohnen**, {month:%Y-%m}: now 2.020,50 € "
        "spent."
    )
    assert not at.toast
    assert not [b for b in at.button if b.label.startswith("Show ")]  # the grid starts on it
    next(b for b in at.button if b.help == "Previous month").click().run()
    next(b for b in at.button if b.label == f"Show {month:%Y-%m}").click().run()
    assert _shown_month(at) == month
    assert not [b for b in at.button if b.label.startswith("Show ")]  # the grid shows it
    assert _quick(at) == ["wohnen", "", month]  # the amount empties
    next(b for b in at.button if b.label == "Add").click().run()  # a second tap adds nothing
    assert _said(at).startswith(":red[")
    earlier = add_months(month, -1)
    _add(at, "wohnen", "-20", earlier)  # rejected: the form keeps it
    assert _said(at).startswith(":red[") and _quick(at) == ["wohnen", "-20", earlier]
    _add(at, "wohnen", "20")  # the month stays for the next receipt
    assert _quick(at) == ["wohnen", "", earlier]
    assert actuals.read(data) == {earlier: {"wohnen": -20.0}, month: {"wohnen": -2020.5}}
    # one revision per add, named by the page (`app` without the navigation of `main.py`)
    assert [(e.source, e.files) for e in revisions.entries(data)[-3:]] == [
        ("app", ("actuals.csv",))
    ] * 3


@pytest.mark.parametrize(
    ("cat", "found"),
    [(" Wohnen", ("wohnen", 5.0)), ("   ", None), (None, None)],  # spaces: no new category
)
def test_a_quick_add_takes_a_known_category_in_any_case(
    cat: str | None, found: tuple[str, float] | None
) -> None:
    assert spend.quick(cat, "5", ["wohnen"]) == found


def test_a_quick_add_saves_cents_spent_and_warns_of_more_refunds_than_spending() -> None:
    assert actuals.add_spent({}, "bargeld", 20.504) == {"bargeld": -20.5}
    month = date(2026, 10, 1)
    assert "⚠" in spend.Added("bargeld", month, 5.0, 10.0).text
    assert "⚠" not in spend.Added("bargeld", month, 5.0, -5.0).text


def _said(at: AppTest) -> str:
    """The line under the quick add: an error, or the last add."""
    return next(m.value for m in at.markdown if m.value.startswith((":red[", ":material/check")))


def test_spend_drafts_keep_the_edited_categories_and_what_they_held() -> None:
    saved = {"bargeld": -113.36, "finanzen": -10.0, "sport": -40.0}
    draft = spend.edits(saved, {"bargeld": -113.36, "finanzen": -30.0, "kino": -5.0})
    assert draft == {"finanzen": (-10.0, -30.0), "kino": (None, -5.0), "sport": (-40.0, None)}
    later = saved | {"bargeld": -123.36, "sport": -45.0}  # saved on another device
    shown = actuals.applied(later, draft)
    assert shown == {"bargeld": -123.36, "finanzen": -30.0, "kino": -5.0}
    # the grid starts again on the file: each edit keeps what the file held when it began
    assert spend.edits(later, shown, draft) == draft
    assert [c.category for c in actuals.merge(later, draft)[1]] == ["sport"]
    # a quick add on this device moves an edit at both ends, so it clashes with nothing
    added = spend.moved(draft, "finanzen", 5)
    assert added == draft | {"finanzen": (-15.0, -35.0)}
    assert not actuals.merge(actuals.add_spent(saved, "finanzen", 5), added)[1]
    assert spend.moved(draft, "bargeld", 5) == draft
    clash = actuals.Clash("sport", -40.0, None, -45.0)
    assert spend.chosen(draft, [clash], yours=True) == draft | {"sport": (-45.0, None)}
    assert spend.chosen(draft, [clash], yours=False) == {
        cat: edit for cat, edit in draft.items() if cat != "sport"
    }


def _click(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception


def _saveable(at: AppTest) -> bool:
    return not next(b for b in at.button if b.label.startswith("Save")).disabled


def test_spend_grid_follows_the_file_and_keeps_its_edits(data: Path) -> None:
    month = date.today().replace(day=1)  # the grid opens on it
    spent(data, month, {"bargeld": -50.0})
    at = AppTest.from_string(SPEND.format(data=str(data)), default_timeout=30).run()

    def to_save() -> list[str]:
        return [c.value.split("\n")[1] for c in at.caption if c.value.startswith("To save")]

    def recorded() -> list[str]:
        return [c.value for c in at.caption if c.value.startswith("Recorded")]

    assert recorded() == ["Recorded: 0 of 1 planned categories."]  # bargeld is unplanned
    _click(at, "Take plan")
    assert to_save() == ["**wohnen** empty → -500 €"]
    _click(at, "Discard")
    assert not to_save() and not _saveable(at)
    _click(at, "Take plan")
    actuals.save_draft(data, month, {"bargeld": (-50.0, -70.0)}, source="test")  # another device
    _add(at, "wohnen", "20", month)  # the edited category takes it too
    assert to_save() == ["**wohnen** -20 € → -520 €"]
    # a jump: once a toast, and Save carries the mark while it lasts, still enabled
    assert any(t.value.startswith("Check before you save") for t in at.toast)
    at.run()
    assert not any(t.value.startswith("Check before you save") for t in at.toast)
    _click(at, "Save" + guard.MARK)
    assert actuals.read(data)[month] == {"bargeld": -70.0, "wohnen": -520.0}
    assert not to_save() and not _saveable(at)
    assert recorded() == ["Recorded: 1 of 1 planned categories."]


def test_spend_save_lists_a_category_changed_elsewhere_and_takes_the_choice(data: Path) -> None:
    month = date.today().replace(day=1)  # the grid opens on it
    spent(data, month, {"bargeld": -50.0})
    at = AppTest.from_string(SPEND.format(data=str(data)), default_timeout=30).run()

    def clashes() -> list[str]:
        return [m.value for m in at.markdown if "at the start" in m.value]

    _click(at, "Take plan")  # wohnen: empty → -500
    actuals.add(data, month, "wohnen", 480, source="phone")  # an add on another device
    at.run()
    assert clashes() == ["**wohnen**: file -480,00 €, yours -500,00 €, at the start empty"]
    assert any(t.value.startswith("wohnen changed elsewhere") for t in at.toast)
    assert not _saveable(at)
    _click(at, "Keep yours")
    assert not clashes() and _saveable(at)
    actuals.add(data, month, "bargeld", 20, source="phone")  # no edit here: no clash
    at.run()
    assert not clashes()
    _click(at, "Save")
    assert actuals.read(data)[month] == {"bargeld": -70.0, "wohnen": -500.0}
    next(b for b in at.button if b.help == "Previous month").click().run()
    earlier = add_months(month, -1)  # two edits there, both changed elsewhere since
    at.session_state[spend.DRAFTS] = {earlier: {"wohnen": (None, -500.0), "kino": (None, -8.0)}}
    spent(data, earlier, {"wohnen": -470.0, "kino": -9.0}, "phone")
    at.run()
    assert len(clashes()) == 2
    _click(at, "Take the file for all")
    assert not clashes() and not _saveable(at)
    assert actuals.read(data)[earlier] == {"wohnen": -470.0, "kino": -9.0}


def test_spend_months_reach_back_and_cover_the_records() -> None:
    today = date(2026, 9, 30)
    assert spend.months({}, today)[-2:] == [date(2026, 8, 1), date(2026, 9, 1)]
    assert len(spend.months({}, today)) == spend.MONTHS_BACK + 1
    older = spend.months({date(2023, 1, 1): {}}, today)
    assert (older[0], older[-1]) == (date(2023, 1, 1), date(2026, 9, 1))
