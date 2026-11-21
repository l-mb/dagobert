"""The page `Where is what`: its links name pages and tabs that exist."""

from german import ACTIVATE, leaks, words
from streamlit.testing.v1 import AppTest

from dagobert.ui import assumptions, mode, scenarios, whereis

PAGE = "from dagobert.ui import whereis\nwhereis.page()\n"
STREAM_TABS = {"expenses", "income", "savings", "health insurance", "disability insurance"}


def test_every_place_names_a_page_and_a_tab_that_exist() -> None:
    """A link opens a tab by `?tab=`: the key of a tab of the Assumptions page, the name of one of
    the Cashflows or the Scenarios page, each with the words that the tab shows."""
    tabs = {
        "Assumptions": {(t.key, t.title) for t in assumptions.TABS},
        "Cashflows": {(t, t) for t in STREAM_TABS},
        "Scenarios": {(t, t) for t in scenarios.TABS},
    }
    places = [place for found in whereis.SUBJECTS.values() for place in found]
    assert {place.page for place in places} <= set(mode.PAGES)
    assert [p.what for p in places if p.tab is not None and p.tab not in tabs[p.page]] == []
    assert [p.what for p in places if p.tab is None and p.page in tabs] == []


def test_the_page_draws_its_subjects_in_both_languages() -> None:
    at = AppTest.from_string(PAGE, default_timeout=30).run()
    assert not at.exception
    assert [s.value for s in at.subheader] == list(whereis.SUBJECTS)
    german = AppTest.from_string(ACTIVATE + PAGE, default_timeout=30)
    german.query_params["lang"] = "de"
    german.run()
    assert not german.exception
    assert leaks(words(german)) == []
