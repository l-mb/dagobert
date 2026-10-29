---
paths:
  - "src/dagobert/{history,lots,tradeimport}.py"
  - "src/dagobert/ui/{summary,snapshot,assets,tradeform,overview,tradeimport,corrections}.py"
  - "tests/test_{history,lots,tradeimport,ui_assets}.py"
---

# Observed values and lots

The price files, their import and the `Prices` expander: rule `prices`.

## Snapshot page

- Record observed asset values: updates `value`/`balance`/`per_sqm` and `asof`, appends to
  `data/history.csv`; under the tiles one line of what to do, a line that names a held security
  without a price, `Observed on` and the grid, the rest of the help (`snapshot.HOW`) folded below it
  on every device (`ui.fold`); rows by kind and name, the columns `asset`, `current`, `estimate`,
  `new`, `unchanged` first (`snapshot.COLUMNS`; headers `as of`, `measure`: value or balance,
  `price per m²`, `cost basis`), on a phone `asset`, `current`, `new`, `unchanged`, then
  `estimate` (`PHONE_COLUMNS`: `unchanged` in view at 412 px), the asset pinned at
  `tables.PHONE_PINNED` in rows of `PHONE_ROW` (65 px: Streamlit 1.65 wraps a text cell only in a
  row above 4rem), so a long name takes two or three lines, never cut (owner 2026-10-16; a single
  word longer than the column breaks inside), the kind 160 px wide (`KIND_WIDTH`: the grid cut
  `Rentenvertrag`, and `Altersvorsorgedepot` is longer). A property shows its value, `per_sqm`
  times `sqm`, in `current` and takes it in `new` (`snapshot.current`, `stored`: saved as its
  price per m² to four decimals, so the typed value returns to the cent; the history row the value
  of that price), its `per_sqm` in the read-only column `price per m²` (owner 2026-10-16: a bare
  price per m² read as the value). The save guard names a field as the Assets grids head it
  (`gridcolumns.asset_names(assets.TITLES)`: `as of`, `price per m²`, `paid in`). A tick of
  `unchanged` observes the current value: a new `asof` and a history row, unless `new` holds one
  (`snapshot_edits`); a `cost_basis` alone keeps the `asof` of the value (the Assets grid dates a
  new value only, `save.stamp`). A term deposit takes no `new` or `unchanged` (its contract gives
  the value, the history counts its interest), a `cost_basis` only equity without trades: such an
  entry is dropped with a warning (`snapshot.stray`, `takes`), so it does not block the save. An
  asset whose value needs an update (`summary.needs_update`) with `⚠` before its name, its `asof` in
  red, `never` without one, its name in red on a desktop only: no red reaches 4.5:1 on both themes,
  and the pinned column of a phone mutes it to 2.4:1, so there the name stays gray; below the
  grid a link per such row to its row on the
  Assets page (`assets.opened` with its value field and `asof`: this page dates a value with
  `Observed on` only), then the expander `Prices` (`ui.pricing`, open at first while a held security
  has no price, `pricing.unpriced`): a table of the held securities, then the price files without
  trades marked `(no trades)`, with the date and the euros of their last price (`prices.last_price`;
  `(gold series)` after the date when the series of `XAU` or `BTC` gave it, rule `prices`) and the
  number of stored prices; the form `Add a price` (security, held ones first, or a typed ISIN or
  symbol such as `XAU`, kept for the next price; date up to today, also a past one; euros per unit
  with the decimal keypad, without thousands groups like the units of a trade: `5.432` is refused),
  which saves at once, and its toast names the value of the units held at that price, so a slip of a
  mark shows, with a warning for a stored price of that date that it changes beyond half or double,
  or a trade within five days whose price per unit lies that far off (`prices.off_trades`); the
  import of a downloaded price history of one security (`csvimport`): its security select, empty at
  first and after each import (a preselected one took the history of another without a word; nothing
  reads until one is chosen), an upload, the mapper (`pricing.mapper`: date column, price column,
  currency column, date order, decimal mark, each preselected with the guess), a preview (count,
  dates, new and replaced prices, the first and last three, the refused lines), the save guard with
  only the replaced prices beyond half or double, a count of the others and the trades far off
  (`hint`: the decimal mark), and `Import N prices`; after either save `prices.record` runs and the
  toast names what it recorded; above `Prices` a button `Take estimates` that fills the empty `new`
  cells from `estimate`, except for term deposits, estimates equal to the current value and rows
  ticked `unchanged`, and says in a toast how many it took and which it skipped and why
  (`snapshot.took`; off only when it would neither take nor skip), the list of the save guard, and
  in the page header `Record`, `Record 3 changes` once there are entries, whose toast names the
  assets; a loan balance is saved negative whatever sign is typed. The grid shows the assets as it
  read them while it holds entries (`save.base`, rule `grids`): a value recorded elsewhere since,
  also by a price saved on this page, shows above it, and `Record` refuses an entry of an asset
  changed since and records the others. A price save stays possible while the grid holds entries: it
  changes only the assets that it records. The `⚠` of a row comes from the rows of the grid
  (`Assets.model_validate`), also of an asset removed elsewhere since. `estimate` of an asset with
  trades: its open lots at `prices.last_price`, so `XAU` and `BTC` at their series when it is newer;
  `HOW` says so. Of a dated loan, pension policy or depot: its value carried to the day (rule
  `engine`) in the plan of the main scenario, which the page loads once; of a policy also `paid`
  (`snapshot.Estimate`), which `Record` writes with each new `asof` (typed, estimated or
  `unchanged`): the contributions by `asof`, the base of the next carry and of the guarantee.
- `Correct a recorded month` (`ui/corrections.py`, owner 2026-10-16), a keyed expander between
  `Take estimates` and `Prices` while `history.csv` holds a row: `ABOUT` (the value of `assets.yaml`
  stays: record it again or change it on the Assets page), `Month` (`history.months`, newest
  first), a fixed grid of its rows (`date`, `asset` by name, `value` as recorded, `remove`; on a
  phone `PHONE_COLUMNS`, the name last, so value and `remove` fit), the save guard (`listed`: each
  value old to new, each removed row by date and asset; a removal always warns, a `notes` line with
  the count, so `Save the correction ⚠`) and `Save the correction` in the expander (the header
  holds `Record`): `corrections` (a tick removes, a loan stays below zero whatever sign is typed,
  the value as recorded or an emptied cell is none), one revision `Snapshot: correct 2026-09`
  (`history.corrected` inside the write), refused (`Not saved: … since this table was drawn`)
  while the rows of the month changed since the grid drew: `Base` per nonce and month, kept while
  the grid holds edits (`save.stays`, the `Seen` of the rows of the month, as rule `grids`), with
  a warning and `Discard my edits`. A mistake just recorded is the job of `Undo` (rule
  `save-guard`), which also takes a correction back.

## Assets page

- A link opens an asset (`?asset=<id>&fields=<keys>`, `assets.opened`, `ASSET`, `FIELDS`; the
  Overview and the Snapshot page): `_arrival` pops the query into `tables.focus` of the grid of its
  kind (rule `grids`) and opens its tab (`st.tabs(default=)`, while the focus lives); a run that
  opens the page without a link ends it (`ui.arrived`). `SHOW_TAB` scrolls the strip to that tab
  once per drawing: on a phone it lay out of view.
- Editable tables (`grid` `assets`: rule `grids`), a tab per asset kind that `mode.View` shows, a
  link opens or whose grid holds edits (`View.note` names the rest), in words (`summary.KINDS`:
  `pension policy`, `pension depot`; the id of a saved asset stays, `Rename` beside it, `growth`,
  `tags` and the `salary` of a bAV conversion and the `finances` of a loan are selects; readable
  headers, `assets.titles`: `TITLES` such as `ID`, `as of`, `check every (months)`, a key with an
  underscore with spaces, else the key; `bought`, `building_share` and `afa` of a property (rule
  `rental`) are `mode.EXPERT`; the column help `What the columns mean` on a phone; above the grid of
  gold and crypto, folded `About gold and crypto`, `assets.LOT_KINDS`: what a unit of `XAU` or `BTC`
  is, an asset without trades counts as held for more than a year, one security per asset keeps the
  engine's split of `value` exact, `tax: capital` needs trades), and a `securities` tab (while
  `View` shows `assets.TRADES` or a trades grid holds edits) for an asset with trades
  (`gridcolumns.HOLDING_KINDS`): per security (`security` the name, `tradeform.CODE` the ISIN or
  symbol) the value, the gain and the yearly return of all its trades, nominal and real (`yearly
  return %`, `real yearly return %`, help in `assets.RETURNS`; the `Vorabpauschale per unit` of a
  lot explains itself in its help), then the open units and their cost, then the open lots (with
  the yearly returns of the purchase, at its cost with fees, not the basis) and the sales, value and
  gain first there too. A yearly return over less than a year (`assets.YEAR`, from the first flow
  to the price date) stays empty, a security, its total and a lot alike (owner 2026-10-29, the
  GIPS rule: a few months would inflate it). A security without units leaves the table
  `assets.SOLD_SHOWN` (3 months) after its last sale (owner 2026-10-29); the total keeps all
  trades. Empty cells blank, units like those of the trades, `1 234.5678` (`assets.formats`, rule
  `money`). Below the sales the chart `Value over time` (rule `position`). Gold and crypto
  (`assets.Holding`: the holding period `private_sale_months` of the tax year, `tax: capital` or
  for crypto `tax.crypto_capital_from` of `assumptions.yaml`; `assets.LOT_TAX` folded below the
  tables, beside `assets.HOLDINGS`, how to read them) add `tax-free units` (sold today without
  tax), per open lot `tax` (`free`, `private
  sale`, `capital`) and `free from` (the day after the purchase a year on, §188 BGB: the law counts
  days, the engine months) instead of the Vorabpauschale, and split a sale by the `tax` of the lots
  it took (`lots.Sale.taken`), each part with its share of the proceeds and the dates of the
  purchases: the lines of the Anlage SO. Then the heading `Trades`, on a phone the form `Add a
  trade` (`ui/tradeform.py`: security, the one of the latest trade first or a new ISIN or symbol,
  for gold or crypto also `XAU` or `BTC`, `tradeform.choices`; date, kind, without the
  Vorabpauschale there; units, euros, fees with the placeholders `10`, `104.20`, `0`; name), whose
  refusal (`Not added:`) shows right below `Add`, in plain words (`enter the number of units`,
  `enter the amount in euros`), with the fields to correct framed in red
  (`tradeform.TypedError.fields`); every hint takes the mark of the language, `1200, or 1.2 for a
  fraction` (German `1,2`), also `tradeform.COUNTS`. The form saves one trade at once, its `Add` off
  while the grid holds unsaved edits (`tables.unsaved`, help `tradeform.WAIT`), which shows the
  trades as it read them until a save (the grid adds a row at the end of its list, out of view on a
  phone). The trades of an asset are found by its id inside each write (`RowFile.child`): a removed
  asset refuses a trade, an asset added before it on another device takes none. Units take no
  thousands groups: `1.200` is refused (`tradeform.plain`, also for a typed price), a mark before
  three digits may group them like the euros. The toast names units, price per unit and euros
  (`tradeform.receipt`), so a slip of a mark shows. A trade of `XAU` or `BTC` far from its series
  (`prices.off_series`, rule `prices`) adds a toast after the save, and in the grid a warning of the
  guard (`Table.check`, `tradeform.series_notes`): grams typed as troy ounces. Then on every device
  the expander `Import trades` (`ui.tradeimport`, its code: rule `tradeimport`): one sentence,
  folded `Where to get the file` (`WHERE`: the menu of each broker, as far as public sources name
  it), an upload (a file that is no table: `Not read:` with `NOT_READ`), its columns in the expander
  `COLUMNS` (`ui.csvcolumns`, each preselected with the guess; open only while the guess lacks a
  field of `REQUIRED`, which then waits for a choice, named by its label), a preview
  (`tradeimport.summary`, two lines: the new trades by kind with their dates and those held already;
  then the other rows by kind or status and the refused lines; per security the new trades and the
  units net of sales, so a stray security shows; the first and last three with their price per unit,
  so a slip of a mark shows, units and euros as in the trades grid, `format_number` and whole euros;
  folded `Other rows left out` with their line and cells; the first three refused lines), the save
  guard with the prices far off (`tradeimport.slips`, `hint`: the decimal mark) and `Import N
  trades`, off like `Add` while the grid holds unsaved edits. It adds only onto the trades that the
  preview of the last run was checked against: its `Seen` goes to `RowFile.apply(seen=…)`, so a
  trade added or changed elsewhere since refuses it (`Not imported: … since the preview`), and the
  run shows the preview of the trades now. The toast after the rerun (`ui.tell`) names the count and
  the dates; the upload field starts empty. Then the editable trades, the name last
  (`assets.TRADE_FIELDS`), the security as `ISIN or symbol`; the asset with the most trades comes
  first, the others are marked `(no trades)` and explain that an account without securities needs
  none, gold or crypto that it counts as held over a year.

## Code

- `src/dagobert/history.py`: `history.csv` (`date,asset,value`: a property its full value, a loan
  its negative balance; `appended`: its text with new rows for the write of the caller,
  `RowFile.apply(observed=…)` and `prices.record`; nothing without rows), `observations` and
  `values_at` (the last observed value per asset by a date), `actual_values` and `actual_totals`,
  the observed values and net worth at the end of each month with an observation (a snapshot; a
  month between two holds none: people record rarely, owner 2026-10-13). They start in the first
  month in which every asset has an observation (the value in `assets.yaml` counts at `asof`, else
  at `start`), so entries never look like growth. Without an asset, nothing.
  `corrected`: the text with rows of a month changed or removed (None), each by its place among
  the rows of the month in the file (`of_month`, in file order; `months` the months with a row),
  every other character kept but the line ends, for the write of the caller; nothing without a
  change.
- `src/dagobert/lots.py`: replays the `trades` of an asset into a `Book`: open lots by `security`,
  oldest first, and the sales with the part of each lot they took (`Sale.taken`): the oldest units
  first (FIFO, §20 Abs. 4 S. 7 EStG; gold and crypto: rule `tax`). A Vorabpauschale raises the basis
  of the lots held at its date, with one twelfth less per month before the purchase in the purchase
  year. `irr` is the money-weighted return of the cash flows (`flows`: buys negative, sales
  positive, a Vorabpauschale is no flow), `returns.deflate` turns them into euros of the last date
  for the real return (`series.consumer_prices`).
- `summary.py` holds the asset totals, the tiles (in `tiles-<page>`; a tile without a change says
  `no change since …` in gray, no arrow, so each keeps the line; none while no value predates the
  month, `change` None: a new plan), the asset sunburst (`breakdown`: of the height that the page
  gives, `PHONE_RINGS` on a phone; no asset: an info naming the Assets page), `KINDS` (the asset
  kinds in tabs, tables and charts, the YAML keeps its keys), `COLORS` of the sectors (those of
  `balance._BALANCE_STYLE`) and the fixed-income share (fixed income over fixed income and equity,
  as the engine rebalances it; term deposits join at maturity).
- `summary.needs_update` is the rule of the Snapshot page and the attention table of the Overview: a
  value needs an update when it is stale (`summary.stale`: older than `summary.update_months`) or
  has no `asof`, except for an empty asset and a term deposit. `update_months` is the `update_every`
  of the asset, else `summary.UPDATE_EVERY` of its kind: never for a term deposit (its contract) and
  a property, whose `per_sqm` is a rare estimate by hand and must not be flagged or rolled forward,
  else `summary.UPDATE_MONTHS`, 12: people record rarely (owner, 2026-10-13). A property that the
  main scenario sells on a date (`summary.selling`) takes `SALE_MONTHS`, six, while the
  sale runs. An empty asset goes stale too.
