---
paths:
  - "src/dagobert/ui/{overview,outlook,summary,snapshot,corrections,assets,position,tradeform,pricing,tradeimport,csvcolumns}.py"
  - "src/dagobert/report/tracker.py"
  - "src/dagobert/{tradeimport,prices,rollforward}.py"
---

# Translation of the Track pages

The Overview, Snapshot and Assets pages speak German (rule `i18n`): `ui/overview.py`,
`outlook`, `summary`, `snapshot`, `corrections`, `assets`, `position`, `tradeform`, `pricing`,
`tradeimport`, `csvcolumns` and `report/tracker.py` are in `i18n_check.TRANSLATED`.

- Ids and words: a table keeps English ids as its columns and keys (tests read them), and its column
  config heads them in words (`assets.HEADERS` in `formats`, `pricing.HEADERS` and
  `tradeimport.HEADERS` by `said`, the configs of the Snapshot grid, `overview.ROLL_HEADERS`). A
  constant of words is marked `N_` and said where it shows: the kinds and groups (`summary.KINDS`,
  `LIQUIDITY`; `summary.said` for the paths of the sunburst and `COLORS`, the asset and its
  securities as written), the tax of a lot (`assets.FREE`, `PRIVATE_SALE`, `CAPITAL`, compared as
  ids), the reasons of `Take estimates` (`snapshot.DEPOSIT`, `EQUAL`). `assets.titles` gives the
  headers of `TITLES` only: any other column takes its key, in German its word
  (`gridcolumns.keyword`). The Snapshot guard names a cell by `gridcolumns.asset_names` with
  `assets.TITLES`, as the Assets grids head it (uncached, twin of `asset_units`).
- The Snapshot grid is a fixed editor with a key: Streamlit 1.65 knows it by its key and the
  schema of its data, so a language switch keeps its entries, though its labels and some cells
  change. The editors of the Assets page are `tables.edit_table` grids (rule `i18n`).
- `overview.Link.said`: `Open <page>` in words, a file of the roll forward as written.
  `ui.day_said` names the pages of the sources of a day in words (`ui.page_said`).
- `runs.answers(PLAN_SEEK)` keeps what a seek found, `(Found, Dial)`, or None for a plan without the
  dial, never its words: each run says it (`SEEKS`: the dial of a plan and the answer), and a plan
  without the dial gives its reason again.
- The roll forward keeps the keys of the files in its sentences (`start`, `founded`,
  `inflation.mean`), the items of its grids (`Passed.what`, `Change.item`), the headers `every`
  and `founded`, and the refusals of `rollforward.check`, as input errors. `CpiChange.source`
  speaks German, after `from` in a sentence (German `nach`, dative).
- English, as input errors: the refused lines of an import (`csvimport.parse`, `tradeimport.read`
  and `merge`) and `Not read:` reasons. German: the summary of a trade import
  (`tradeimport.summary`, `counted`) and the prices far off (`prices.OFF_TRADE`, `OFF_SERIES`); the
  CLI says them in English.
- A count takes `ngettext` where the English had a plural (`Record 3 changes`, `Took 1
  estimate`); else its one form stays, so the English does not change (`Import 1 prices`).
- Words of other units that the Overview shows in their German: `goalseek` (`STOP`, `stop`, the
  reasons of `work`, `stop_help`, `Dial.text`), `report.summary_columns` (the headers of the tiles
  and their help), `result.unit`, `seek.Target` (`TARGET_LABEL`, `TARGET_HELP`: the target, shared
  with the goal seek of the Explorer) and the changes of `cashplan`. The fold of the roll names
  `Changes since` in the words of the Cashflows page.
