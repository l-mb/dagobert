---
paths:
  - "src/dagobert/ui/*.py"
  - "src/dagobert/ui/page.css"
  - "tests/test_ui.py"
  - ".streamlit/config.toml"
---

# Page style

`ui/page.css` is `ui.PAGE_STYLE`, the style of every page, which `main.py` injects through
`st.html` (rule `ui`: no `<` before a letter in it). The media queries: rule `ui`. A rule of one
page sits under the heading of that page in `page.css`, and its rule says what it does.

## Keyed containers and touch

- `ui.PAGE_STYLE` serves keyed containers. Tiles go into an `st.container` whose key starts with
  `tiles`: two per row in a main area up to 720 px, a value of 1.6rem in a column up to 220 px
  (container queries, so an open sidebar counts); the five tiles of the plan of the Overview
  (`tiles-plan`) three per row from 720 to 1,000 px, where one row cut a label in landscape. An
  `st.table` goes into an `st.container` whose key starts with `table-`: in portrait its cells keep
  one line and its first column sticks on `--dg-bg` while the table scrolls sideways, with an opaque
  divider of 1 px (at the fractional pixel ratio of the phone the scrolled glyphs showed through the
  last device column of the cell, a translucent divider lets them through). A column that must wrap
  needs a rule of its page, such as `stream` and `change` of the Cashflows change tables (on a
  phone, also in landscape, its tables take 13 px and keep dates and amounts on one line, so the
  sheet fits four phases in portrait and the change tables fit in landscape). An `st.table` keeps no
  class of a column (a class that its `Styler` sets does not reach the cells), so such a rule counts
  columns: `change` is the third of the scheduled changes and the second of `Changes since`, from
  the start (the phases follow it, any number), the months of the Spend comparison the second, and
  tests pin both. The wrapper of an `st.table` scrolls sideways, so a sticky header there holds only
  where the page drops that scroll: the Cashflows sheet on a phone up to four phases in portrait
  (rule `cashflows`). The attention table of the Overview and the items before the new start of a
  roll are no `st.table` but grids with a link per row (`overview._linked`, rule `overview`). In
  portrait the help tooltips stay inside the screen. On touch tap targets grow to at least 40 px
  (help icons, segmented controls, expander headers, the sidebar navigation, the header buttons and
  the one that closes the sidebar, tabs and their scroll arrows, the labels of checkboxes and
  toggles, the steps of a number input, a `page_link`; a tapped tab scrolls into view clear of the
  arrows, `scroll-padding-inline`, but Streamlit keeps the scroll offset when the strip narrows, so
  the selected tab can leave the strip when the sidebar opens in landscape), and so do the buttons
  of the grid toolbar and the Fullscreen of the modebar (`hover: none`: Streamlit and plotly show
  both always, and the close button of the sidebar, which Streamlit shows on hover in landscape).
  The Fullscreen icon stays in its corner, its tap area grows into the chart. Pull-to-refresh is off
  (`overscroll-behavior-y: contain` on `stMain` and `stSidebarContent`, the scrollers of the page),
  and a slider moves only by its thumb (24 px): a swipe over its track scrolls, a tap on the track
  does not jump. The slider rule follows the DOM of Streamlit 1.65, not test ids (the thumb is the
  `div` that holds the hidden range input): check it after an upgrade. On a phone the title starts
  4.5rem from the top (the header is 60 px, the `top` of a sticky bar below it, 3.75rem), `h1` at
  2rem.
- On touch the grid toolbar of a grid that adds rows (its `Add row`, by the label of Streamlit
  1.65; a grid takes no `alt`, which 1.65 appends to the labels of its toolbar) gets a band of
  3rem above the grid, the height of the toolbar (it covered the tabs and
  buttons above; its Delete row(s) is the only way to delete a row there, and in fullscreen the
  band fits above the grid). A grid without it (read only, or of fixed rows: the timeline, the
  inherited events, the explorer's summary, the Snapshot grid) has neither band nor toolbar: its
  search, download and column menu serve a desktop, and the band left a gap above it. A grid that
  scrolls sideways fades out at its right edge until it reaches its end: a scroll-driven animation
  (`scroll-timeline` on the scroller `.dvn-scroller` of the canvas grid, `timeline-scope` on
  `stDataFrameResizable`), inactive while nothing scrolls; it flips off at the end, as an animated
  length needs `@property`. The DOM of Streamlit 1.65: check it after an upgrade.
- A segmented control is as high as a text field (2.5rem, its buttons by `data-variant`), so its
  label lines up in a row of fields (`Sex`, `Tax year`, `Amounts` beside a select).
- A result that a new one is about to replace fades: a container whose key starts with
  `explorer-stale-` takes `opacity: 0.4` in both themes (the old sensitivity charts, rule
  `explorer`).

## Theme

- CSS colors follow the theme of the Streamlit menu: `light-dark()` or the tokens `--dg-bg`,
  `--dg-fg` and `--dg-side` (the sidebar) of `.stApp` and of a dialog, never
  `prefers-color-scheme`, which follows the OS. Only `.stApp` knows the theme of the menu (its
  `color-scheme`, from a class of Streamlit): the boot script in `main.py` copies it to the page,
  `<html>`, and again when that class changes (a `MutationObserver`), so a dialog (`st.dialog`,
  the file actions of the Scenarios page), which draws outside `.stApp`, follows the theme too.
  Only the two `theme-color` metas of the boot script (the address
  bar of Chrome on a phone) take it: a meta cannot read the theme. The accent (`primaryColor`) is
  blue in `[theme.light]` and `[theme.dark]` (`.streamlit/config.toml`, `cli.STREAMLIT_ENV`): the
  red of Streamlit marked a selected pill like an error, and a bare `[theme]` makes one light
  theme without the choice of Light and Dark in the menu.
- A primary button labels in white on the light accent (`#1c64d1`) and in the page color
  (`#0e1117`) on the dark one (`#4a8ff0`): white there reached 3.24:1, the page color 5.8:1, and
  no blue reaches 4.5:1 both under a white label and as text on the dark page (the page color
  `--dg-bg` on `[data-testid^="stBaseButton-primary"]` inside `.stApp` or a dialog, not when
  disabled). Streamlit has no theme option for it.
