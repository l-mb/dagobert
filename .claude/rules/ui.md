---
paths:
  - "src/dagobert/ui/*.py"
  - "src/dagobert/ui/page.css"
  - "tests/{test_ui,apps}.py"
  - ".streamlit/config.toml"
---

# Streamlit app

After a change, run the skill `app-check` as a desktop and as a phone. The rule of a page
describes it: read it before you change the page, and change it with the page, together with its
page of the user guide (`docs/manual/<page>.md`, plain English). The table names the rules to
read for a module; one whose `paths:` miss the module does not load with it, so open it. The tests
of a page, `tests/test_ui_<page>.py`, load its rule; `tests/test_ui.py` draws every page (this
rule and `page-style`), `tests/apps.py` holds what they share. The
style of the pages (`ui/page.css`): rule `page-style`.

| Module | Rules besides `ui`, `money` and `i18n` |
|---|---|
| `overview.py` | `overview` (the page), `cashflows` (the plan changes of the attention table), `rollforward`, `tracking`, `i18n-track` |
| `outlook.py` | `overview`, `explorer-runs`, `i18n-track` |
| `explorer.py`, `knobs.py`, `sliders.py`, `seek.py`, `main.py` | `explorer` (the page), `explorer-sliders` (`knobs.py`, `sliders.py`: sliders, groups, switches), `explorer-runs` (its runs, caches and pool), `mode` (simple mode) |
| `runs.py` | `explorer-runs` |
| `snapshot.py`, `assets.py` | `tracking` (both pages), `grids`, `save-guard`, `i18n-track` |
| `pricing.py` | `prices`, `save-guard`, `i18n-track` |
| `csvcolumns.py` | `prices` (the column selects of a CSV import), `i18n-track` |
| `tradeform.py`, `tradeimport.py` | `tracking` (the trade form and import of the Assets page), `save-guard`, `i18n-track` |
| `cashflows.py` | `cashflows` (the page), `ledger`, `grids`, `save-guard` |
| `bars.py` | `cashflows` (the bars of a phase, which the Cashflows page and the Flows page share), `ledger` |
| `spend.py` | `spend` (the page), `save-guard` |
| `data.py` | `series` (the page), `prices` |
| `assumptions.py` | `assumptions` (the page), `forms`, `save-guard` |
| `scenarios.py`, `fileactions.py`, `phases.py` | `scenarios` (the page), `events`, `scenario-overrides`, `forms`, `store` |
| `transfer.py` | `transfer` (the page) |
| `welcome.py` | `examples` (the first-run page) |
| `mode.py`, `features.py` | `mode` (the mode, the features and their page), `save-guard` |
| `flows.py` | `flows` (the page), `ledger`, `cashflows` |
| `__init__.py` | `charts` |
| `summary.py` | `tracking`, `i18n-track` |
| `tables.py` | `grids`, `save-guard` |
| `gridstate.py`, `gridcolumns.py` | `grids` |
| `guard.py`, `save.py` | `save-guard` |
| `rename.py` | `references` (the rename of a name with its uses), `save-guard` |
| `fields.py`, `forms.py`, `formguard.py`, `widgets.py` | `forms`, `grids`; `forms.py`, `formguard.py` also `save-guard` |
| `events.py`, `lineage.py` | `events` (the Events tab of the Scenarios page), `grids`, `forms`, `save-guard` |
| `scenario_overrides.py`, `overridegrids.py` | `scenario-overrides` (the Overrides tab), `forms`, `grids`, `save-guard` |
| `fixed.py` | |
| `page.css` | `page-style` (the style of every page), `flows`, not `money` |

## The app

- `uv run dagobert app` opens the Streamlit app in the browser (options: rule `container`). The
  navigation has three sections. `Track`: `Overview`, `Snapshot`, `Assets`, `Cashflows`, `Spend`.
  `Plan`: `Explorer`, `Flows`. `Setup`: `Features`, `Data`, `Assumptions`, `Scenarios`, `Export and
  import`. It registers the pages of `mode.pages` (rule `mode`), computed before the `try` from the
  raw inputs: simple mode leaves out Snapshot and Spend without records, Data without a series, a
  feature off its pages; inputs that do not parse register every page beside their error. A reload
  or a bookmark of a page left out (`/snapshot`) shows the dialog `Page not found` of Streamlit and
  runs the Overview (checked in Chrome, Streamlit 1.65: no error, so no `position="hidden"`).
- `Overview`, `Snapshot` and `Assets` open with the tiles: net worth, liquid, illiquid, debt, each
  with the change since the end of the previous month over the assets observed by then
  (`summary.change`). The explorer opens with the scenarios in `data/app.yaml` (`Set as default`,
  the box of the main scenario on the Scenarios page). The Cashflows, Flows and Spend pages, the
  attention table and the plan of the Overview open with the first of them, the main scenario
  (`scenariofiles.first_scenario`), which the selects of Cashflows and Flows and the scenarios of
  the Explorer mark `(main)` (`ui.main_marked`). The Flows page, the Cashflows sheet and its bars
  and the salary sliders of the explorer share one cached `fixed` run per scenario
  (`ui.fixed.result`). The toolbar mode `viewer` hides the `Deploy` button of Streamlit, and with it
  `Rerun` and `Clear cache` in the menu. It opens a browser tab only when no open tab reconnects
  within 6 s of the start. A tab that reconnects after a restart reloads itself once (`ui.BOOT` in
  `sessionStorage`). The same script adds the `theme-color` metas: the address bar of Chrome on a
  phone takes the page background of the OS theme; it also gives the page the color scheme of
  `.stApp` (rule `page-style`). A session lives one hour after its tab disconnects
  (`server.disconnectedSessionTTL`, default 2 minutes), so a phone that leaves the tab keeps its
  unsaved edits. On a phone the sidebar starts collapsed. Every run first takes the language of the
  session (`ui.language`, rule `i18n`), whose switch ends the sidebar, below the switch of the mode
  (`mode.mode_switch`, rule `mode`). Every run keeps the English title of its page in `ui.PAGE`
  (rule `i18n`) and opens the data directory first (`datadir.open`: a migration and the edits
  outside the app become revisions), and inputs that do not load (`InputError`, `SchemaError`) show
  their lines instead of the page. An empty or missing data directory shows the page `Start a plan`
  (`welcome.py`, rule `examples`) instead, with no navigation but the two switches.
- Every save of a page is one revision whose source is the page title (`ui.source`, `app` for a page
  drawn alone, as in `AppTest`): the Save buttons of the grids and `Record` with the history rows
  they add, a price with the values it records, the values that a fetch of the Data page records
  (the fetched months stay outside), the Spend quick add (`actuals.add`, which reads the month under
  the lock) and Save (`actuals.save_draft`, which merges the draft there), the trade form and the
  trade import, the explorer's scenario file and `Set as default`, the roll forward
  (`Overview: roll forward`), a tab of a form (`Assumptions: Markets`), a file action of the
  Scenarios page (`Scenarios: rename scenarios/a.yaml → scenarios/b.yaml`), a rename of a name
  (`Assets: asset flat → home`, rule `references`); an import is `import <zip name>` (rule
  `transfer`). A failed save shows `Not saved:` (or `Not added:`, `Nothing changed:`) with the
  reason, also `BusyError` and `ReadOnlyError`. A save of rows changed since the page read them is
  refused with when and where they changed (`ConflictError`, `save.changed_at`): the grids and
  `Record` (rule `grids`), the roll forward (rule `rollforward`); the Spend Save asks per category
  (rule `spend`).

## Modules

- `__init__.py` holds the helpers of every page: `is_mobile` (a phone: `Mobile` in the user agent,
  or `?mobile=1` for the session), `arrived` (a run that opens its page, by `CAME`, the page of the
  run before, set by `main.py`), `language` and `language_switch` (the language of the session and
  its switch, rule `i18n`), `chose` and `remember` (a choice on a switch of the viewer: the grid
  edits carried, the cookie written in every later run, `SET_COOKIE`; the language and the mode),
  `keyboard` (the keyboard of a phone for the text fields by the start of their key: `decimal-` the
  decimal keypad, such as the numbers of `Add a trade` and the euros of the Spend quick add,
  `nocaps-` no capital first letter, the category of the quick add), `step_button` (a chevron that
  moves a select control to the previous or the next option, off at the end: the Spend month and the
  Flows year, `after` runs after the step; its help names the unit, `STEPS`), `page_link` (a link to
  a page of the navigation, an arrow by default: the `st.Page` that `main.py` registers and keeps in
  `PAGES` by its English title, None for a page that the navigation leaves out, which then shows no
  link; Streamlit finds a page by the hash of its `url_path`, so a link never builds a page again; a
  page drawn alone shows none; `SCENARIO`, `EVENT`, `TAB` and `MAIN` name the query of the Scenarios
  page, rule `scenarios`: the Overview and the explorer link there, and the page imports the
  explorer), `chart` (every chart of the app, see the rules below), `slug` (a file name or an id
  made of a name, the scenarios and the ids of a purchase), `titled` and `scenario_titles` (a
  scenario in a select, `stem · name`, the main one by `main_marked`), `note` (a long caption: as is
  on a desktop, on a phone `fold`, a collapsed expander `How to read this`, which the tracker pages,
  `Setup`, Cashflows, Flows and Spend take on every device behind a caption of one sentence), `tell`
  and `told` (a toast for the next run, `warn` with the warning icon and longer: one before
  `st.rerun` or `st.switch_page` is lost, checked in Chrome; a save that reruns tells, `main.py`
  calls `told` first in each run, as must a test of a page drawn alone), `literal` (text as written
  in Markdown: no emphasis, LaTeX, link, code, list, heading or rule; the names and values of the
  save guard, the scenario note), `scenario_note` (the `note` of a scenario as a caption, `literal`
  as in the report; on a phone one longer than `SHORT_NOTE`, about three lines in portrait, folds
  through `note` into `About the scenario`), `month_labels` (the month labels that fit across a
  chart in one of n columns: `DESKTOP_MONTHS` at 1,500 px with the sidebar open, `PHONE_MONTHS` on a
  phone) and `per_control` (`Amounts` with its help, its options the ids `month` and `year`, `PER`
  their words, English, and multiplier, wrap in a narrow column), `data_stamp` (a cache key of the
  inputs: the latest mtime and count of `STAMPED`, the YAML files of `schema.INPUTS`, `series/*.csv`;
  `run_stamp` that of the runs, `RUN_INPUTS`: rule `explorer-runs`), `timezone` (of the browser,
  `st.context.timezone`, UTC without one: a day of the revisions is a local day) and `since` (the
  days with a revision of some files that have a revision before them, each with the last revision
  before the day began: `Changes since` and the Flows comparison; a data directory with only the
  baseline has none, so both are off).
- `fixed.py` holds the single-path `fixed` run of a scenario: `result` cached by `run_stamp`,
  `run` uncached for the inputs of a revision.

## Rules

- The phone (412 x 915 CSS px, touch only) uses every page. The desktop keeps its look, its
  interactions (a click on a bar, drag to zoom) and the widths of these rules. What CSS can do sits
  in `ui/page.css` behind a media query: `max-width: 640px` for portrait,
  `(max-width: 640px), (max-height: 500px) and (pointer: coarse)` for both orientations (a short
  desktop window keeps its look), `pointer: coarse` and `hover: none` for touch. What CSS cannot do
  branches on `ui.is_mobile()`. A fix that helps both applies everywhere.
- Every widget has a key that no words make (`test_every_widget_and_editable_grid_has_a_key` checks
  the pages, uploads and editable grids too): without one Streamlit takes its label as its identity,
  and other words, such as another language, drop what it holds. An option is an id that
  `format_func` shows in words (`ui.per_control`, the measures of the explorer and the Overview, A
  and B of the difference; `test_a_widget_keeps_its_choice_in_other_words`), a key no label
  (`assumptions.Tab.key`, the file actions of the Scenarios page). Streamlit 1.65 keeps a keyed
  widget whose label, help or options change, not `st.tabs`, a stateful `st.expander` (`on_change`)
  or a popover: their label is part of their identity. An expander without `on_change` keeps its
  open state by its key, so every one has a key (`test_every_expander_has_a_key_but_the_help_fold`
  reads the code: `AppTest` shows no key of an expander), the Explorer groups by id
  (`sliders.GROUPS`), but `ui.fold`: a help that starts closed and may close in other words.
- `ui/` never calls `st.plotly_chart`: `ui.chart` draws every chart. On a phone it sets
  `dragmode=False`, so a swipe over a chart scrolls the page and a tap still shows the hover
  label, and the modebar keeps only Fullscreen (`PHONE_MODEBAR`: Streamlit adds Fullscreen
  through `modeBarButtonsToAdd`, a `modeBarButtons` list would drop it). It turns off
  `doubleClick`: without the drag mode a tap counts twice, as touch and as mouse, and the
  double click reset the axes, for example the cut of the fan chart. `charts.LAYOUT` keeps
  the drag mode, so the HTML report keeps drag to zoom. Streamlit gives a chart with
  `on_select` the drag mode `pan` whatever the figure says: on a phone such a chart holds the
  finger, and a tap only shows the hover label. So on a phone no chart selects:
  `bars.outflow_bars` picks with pills there.
- `st.tabs(on_change="rerun")` with `tab.open` draws only the open tab, and Streamlit then drops
  the state of the widgets of a closed tab. A widget there that must keep its value takes
  `persist_state="page"` (the period of the Flows page, the pills of `bars.outflow_bars`).
  `AppTest` builds a new `PagesManager` per run, so every run counts as a page switch and drops
  that value: check it in a browser.
- `st.html` sanitizes with DOMPurify, also with `unsafe_allow_javascript`. It drops a whole
  `<script>` or `<style>` whose text holds `<` before a letter, `/` or `!`, without a warning:
  build elements in a script with `document.createElement`, never from markup strings; `page.css`
  has no `@property` (its syntax `<length>`; `test_the_page_style_survives_the_sanitizer`). A
  script runs again when its text changes (the boot script of `main.py` with the language), so it
  declares in a block `{…}`: a second `const` at the top level of the page throws before line 1.
- A read-only table with total rows is `st.table` on a pandas `Styler` (`cashflows._phase_table`):
  it honors bold, borders, colors and alignment per cell.
- The API of `AppTest` drives no `st.data_editor` (`german.edited` sends the edits of a grid as a
  browser, through `AppTest._run`). Keep the page logic in pure functions
  (`gridstate.edits_from_state`, `snapshot.snapshot_edits`, `snapshot.take_estimates`,
  `snapshot.took`, `snapshot.stray`, `tradeform.Typed`, `spend.entered`, `spend.take_plan`,
  `spend.quick`, `fields.euros`, `spend.edits`, `spend.moved`, `spend.chosen`, `actuals.applied`,
  `actuals.merge`, `guard.changes`, `pricing.TypedPrice`, `fields.parse`, `forms.edits`,
  `formguard.changes`, `transfer.rows`, `transfer.difference`, `transfer.effect`,
  `transfer.removals`, `transfer.why`) and test those. An `st.file_uploader` can be driven
  (`at.file_uploader[0].upload(name, bytes, mime)`), so the price import has an AppTest. Code cannot
  set the edits of an editor. `Take estimates` writes the filled cells into the table under a new
  widget key and merges them with the edits of that key.

## What Streamlit 1.65 cannot do

A request that Streamlit cannot meet is named here, or in the rule of its page (the Spend grid:
rule `spend`), and dropped.

- A button of the page cannot add a row to an `st.data_editor`: a new row comes through the empty
  last row or the `+` of the grid toolbar, which a touch screen always shows (rule `page-style`).
- An editable cell takes no color: a link marks the row of an asset and its headers (rule `grids`).
