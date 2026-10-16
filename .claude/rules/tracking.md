---
paths:
  - "src/dagobert/{history,lots,tradeimport}.py"
  - "src/dagobert/ui/{summary,snapshot,assets,tradeform,overview,tradeimport}.py"
  - "tests/test_{history,lots,tradeimport,ui_assets}.py"
---

# Observed values and lots

The price files, their import and the `Prices` expander: rule `prices`.

## Snapshot page

- Record observed asset values: updates `value`/`balance`/`per_sqm` and `asof`, appends to
  `data/history.csv`; under the tiles one line of what to do, a line that names a held security
  without a price, `Observed on` and the grid, the rest of the help (`snapshot.HOW`) folded below it
  on every device (`ui.fold`); rows by kind and name, the columns `asset`, `current`, `estimate`,
  `new`, `unchanged` first on every device (`snapshot.COLUMNS`; headers `as of`, `measure`: value,
  balance or price per m², `cost basis`), the asset pinned on a phone at 140 px, the kind 160 px
  wide (`KIND_WIDTH`: the grid cut `Rentenvertrag`, and `Altersvorsorgedepot` is longer). A tick of
  `unchanged` observes the current value: a new `asof` and a history row, unless `new` holds one
  (`snapshot_edits`); a `cost_basis` alone keeps the `asof` of the value (the Assets grid dates a
  new value only, `save.stamp`). A term deposit takes no `new` or `unchanged` (its contract gives
  the value, the history counts its interest), a `cost_basis` only equity without trades: such an
  entry is dropped with a warning (`snapshot.stray`, `takes`), so it does not block the save. An
  asset whose value needs an update (`summary.needs_update`) with `⚠` before its name, its `asof` in
  red, `never` without one, its name in red on a desktop only: no red reaches 4.5:1 on both themes,
  and the pinned column of a phone mutes it to 2.4:1, so there the name stays gray; on a phone a
  name longer than the pinned column keeps its start and its end (`snapshot.asset_cell`: the names
  of two loans may differ only at the end); below the grid a link per such row to its row on the
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
  lot explains itself in its help), then the open units and their cost, then the open lots and the
  sales, value and gain first there too, empty cells blank, units like those of the trades, `1
  234.5678` (`assets.formats`, rule `money`). Gold and crypto (`assets.Holding`: the holding period
  `private_sale_months` of the tax year, `tax: capital` or for crypto `tax.crypto_capital_from` of
  `assumptions.yaml`; `assets.LOT_TAX` folded below the tables, beside `assets.HOLDINGS`, how to
  read them) add `tax-free units` (sold today without tax), per open lot `tax` (`free`, `private
  sale`, `capital`) and `free from` (the day after the purchase a year on, §188 BGB: the law counts
  days, the engine months) instead of the Vorabpauschale, and split a sale by the `tax` of the lots
  it took (`lots.Sale.taken`), each part with its share of the proceeds and the dates of the
  purchases: the lines of the Anlage SO. Then the heading `Trades`, on a phone the form `Add a
  trade` (`ui/tradeform.py`: security, the one of the latest trade first or a new ISIN or symbol,
  for gold or crypto also `XAU` or `BTC`, `tradeform.choices`; date, kind, without the
  Vorabpauschale there; units, euros, fees with the placeholders `10`, `104,20`, `0`; name), whose
  refusal (`Not added:`) shows right below `Add`, in plain words (`enter the number of units`,
  `enter the amount in euros`), with the fields to correct framed in red
  (`tradeform.TypedError.fields`); every hint takes the decimal comma, `1200, or 1,2 for a
  fraction`, also `tradeform.COUNTS`. The form saves one trade at once, its `Add` off while the grid
  holds unsaved edits (`tables.unsaved`, help `tradeform.WAIT`), which shows the trades as it read
  them until a save (the grid adds a row at the end of its list, out of view on a phone). The trades
  of an asset are found by its id inside each write (`RowFile.child`): a removed asset refuses a
  trade, an asset added before it on another device takes none. Units take no thousands groups:
  `1.200` is refused (`tradeform.plain`, also for a typed price), a mark before three digits may
  group them like the euros. The toast names units, price per unit and euros (`tradeform.receipt`),
  so a slip of a mark shows. A trade of `XAU` or `BTC` far from its series (`prices.off_series`,
  rule `prices`) adds a toast after the save, and in the grid a warning of the guard (`Table.check`,
  `tradeform.series_notes`): grams typed as troy ounces. Then on every device the expander `Import
  trades` (`ui.tradeimport`, see the code below): one sentence, folded `Where to get the file`
  (`WHERE`: the menu of each broker, as far as public sources name it), an upload (a file that is no
  table: `Not read:` with `NOT_READ`), its columns in the expander `COLUMNS` (`ui.csvcolumns`, each
  preselected with the guess; open only while the guess lacks a field of `REQUIRED`, which then
  waits for a choice, named by its label), a preview (`tradeimport.summary`, two lines: the new
  trades by kind with their dates and those held already; then the other rows by kind or status and
  the refused lines; per security the new trades and the units net of sales, so a stray security
  shows; the first and last three with their price per unit, so a slip of a mark shows, units and
  euros as in the trades grid, `format_number` and whole euros; folded `Other rows left out` with
  their line and cells; the first three refused lines), the save guard with the prices far off
  (`tradeimport.slips`, `hint`: the decimal mark) and `Import N trades`, off like `Add` while the
  grid holds unsaved edits. It adds only onto the trades that the preview of the last run was
  checked against: its `Seen` goes to `RowFile.apply(seen=…)`, so a trade added or changed elsewhere
  since refuses it (`Not imported: … since the preview`), and the run shows the preview of the
  trades now. The toast after the rerun (`ui.tell`) names the count and the dates; the upload field
  starts empty. Then the editable trades, the name last (`assets.TRADE_FIELDS`), the security as
  `ISIN or symbol`; the asset with the most trades comes first, the others are marked `(no trades)`
  and explain that an account without securities needs none, gold or crypto that it counts as held
  over a year.

## Code

- `uv run dagobert trades import ASSET FILE` adds the buys and sales of a broker export (CSV) to the
  trades of the asset `ASSET` (equity, fixed income, gold, crypto) as one revision `trades import`,
  after `datadir.open`. `--column FIELD=HEADER` (once per field, `''` for none), `--decimal` and
  `--dates` default to the guess; it prints the mapping, the refused lines, `tradeimport.summary`
  and the slips, which stop it unless `--force`. `--dry-run` saves nothing. It exits with 1 for an
  asset that is gone or holds no securities, a missing column, a refused line without a trade added
  or held already (`no trade to add`) and a conflict.
- `src/dagobert/tradeimport.py`: `guess` maps the columns by header (`ALIASES`, without case, whole
  before start, each column for one field), after the exports described in public: the transaction
  export of Trade Republic (`date`, `type`, `symbol` with the ISIN, `shares`, `amount`, `fee`,
  `name`, `currency`; a decimal point, amount and fee signed), the transactions of Scalable Capital
  (`date`, `type`, `isin`, `shares`, `amount`, `fee`, `description`, `currency`, `status`; a decimal
  comma, the newest first) and the Depotumsätze of comdirect (`Datum`, `Art`, `ISIN`, `Menge`,
  `Kurswert`, `Bezeichnung`, `Kurswertwährung`: the currency of the amount, not of the price; no
  fees). ING and consorsbank describe no export of the depot: the user picks the columns. Without a
  header the security is the first column of ISINs; the date column and the decimal mark come from
  `csvimport.guess`. `read` takes a kind by the start of its cell (`KINDS`: `Kauf`, `Buy`,
  `Sparplan`, `Savings plan`; `Verkauf`, `Sell`; `Vorabpauschale`) and leaves out, with its line
  (`Parsed.others`), any other kind (`Distribution`, `Umbuchung`, `DIVIDEND`; the `Taxes` of
  Scalable are the tax, not the Vorabpauschale, which stays typed by hand) and a status that is no
  execution (`DONE`: `Executed`, not `Cancelled`), `NoTrade`. Without a kind column a minus before
  the units sells. Units, amount and fees lose their sign, amount and fees round to cents. Refused
  with its line: a missing cell, a date or number that does not read, a date after today, a currency
  other than EUR (an empty cell is EUR), a buy or sale without units, a row without amount or ISIN.
  A file whose first date is newer than its last reads backwards, so a sale follows the buy of its
  day. `merge`, oldest first, against the trades of the asset (`holding`: the asset of one read and
  the `Seen` of its trades): a row with the date, security, units and amount of a trade is held
  already, each trade once (a file that repeats an execution of a day adds the second); refused are
  a row that the model refuses (a Vorabpauschale out of January), a security that the asset does not
  take (`HoldingsAsset.securities`) and one that the trades so far cannot replay (`lots.book`: a
  sale of more units than held). A security without a name takes that of its first row. `slips`:
  `prices.off_series` and `prices.off_trades` against the price file of each security. `save`:
  `RowFile.apply` with `seen`, and a depot drops its `cost_basis` like at its first buy.
  `replaced_basis` warns of that drop (the lots of recent months only would leave out the cost
  of what the depot held before): a `Check:` line of the command, a note of the guard of the
  import, the trades grid (`tradeform.basis_check`, `Table.check`) and a toast of the form.
- `src/dagobert/history.py`: `history.csv` (`date,asset,value`: a property its full value, a loan
  its negative balance; `appended`: its text with new rows for the write of the caller,
  `RowFile.apply(observed=…)` and `prices.record`; nothing without rows), `observations` and
  `values_at` (the last observed value per asset by a date), `actual_values` and `actual_totals`,
  the observed values and net worth at the end of each month with an observation (a snapshot; a
  month between two holds none: people record rarely, owner 2026-10-13). They start in the first
  month in which every asset has an observation (the value in `assets.yaml` counts at `asof`, else
  at `start`), so entries never look like growth. Without an asset, nothing.
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
