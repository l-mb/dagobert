---
paths:
  - "src/dagobert/ui/whereis.py"
  - "tests/test_ui_whereis.py"
---

# Where is what

The page `Where is what` (`/where`, first in the section `Your plan`, issue #51, owner
2026-11-21): the inputs of the plan by subject, since a subject is spread over pages and a user
comes a few times a year. The other pages: rule `ui`.

- `whereis.SUBJECTS`: per subject (a heading) its `Place`s: what a user looks for, the page by its
  English title and the tab there as the value of `?tab=` with its words. `Place.link` draws
  what it is and beside it `ui.page_link` with `ui.TAB`, labelled `page › tab`, in a row that
  wraps (one label of both was cut on a phone, checked in Chrome); a page that the navigation
  leaves out (simple mode, a feature off) gives no row, so the page never names a page that does
  not show. A page drawn alone (a test) has no navigation: it shows the headings only.
  No input, no save, no run: the page reads nothing.
- `?tab=` (popped at the draw): the Assumptions page takes the key of a tab (`assumptions.Tab.key`:
  `person`, `markets`, `investing`, `risks`, `insurance`, `tax`), the stream tabs of the Cashflows
  page their English name (`expenses`, `income`, `savings`, `health insurance`, `disability
  insurance`), the Scenarios page its tab names as before (rule `scenarios`); each as
  `st.tabs(default=)`. A tab that does not show (hidden, another plan) leaves the first tab open.
  The Cashflows link opens the page at its top: `page_link` takes no anchor, the streams are below
  the sheet.
- A new tab, a renamed one or a moved field changes `SUBJECTS` with it:
  `test_every_place_names_a_page_and_a_tab_that_exist` holds every place to the tabs of the pages.
- Words: marked `N_`, said per draw (rule `i18n`); the tab words are the messages of their pages.
