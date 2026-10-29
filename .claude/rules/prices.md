---
paths:
  - "src/dagobert/{prices,csvimport}.py"
  - "src/dagobert/ui/{pricing,csvcolumns}.py"
  - "tests/test_{prices,csvimport}.py"
---

# Prices

The Snapshot page around the `Prices` expander: rule `tracking`.

- `uv run dagobert prices import SECURITY FILE` merges a downloaded price history (CSV, euros per
  unit) into `data/prices/<SECURITY>.csv` (`date,close`, one row per date, sorted; an imported date
  replaces the stored price). A security is an ISIN, or the symbol of gold or a coin
  (`model.assets.SECURITY`: 2 to 10 capitals and digits, such as `XAU` or `BTC`). Options `--date`,
  `--value` (columns by header), `--decimal , | .`, `--dates ymd|dmy|mdy`, `--currency` (a column,
  `''` for none) default to the guess of `csvimport`; the command prints the mapping it used and the
  refused lines (a date after today too). A price outside half to double the stored price of its
  date or the price of a trade within five days (`prices.far_off`) stops it before it saves, unless
  `--force`; it exits with 1 then and when no price reads. Then it records the market value of every
  asset whose open lots all have a price (`prices.record`): `value` and `asof` (the oldest of those
  prices) in `assets.yaml`, and a row in `history.csv`. The row counts the lots held on its date
  (the trades up to it), each at its last price: a lot bought later (a price typed for a past day, a
  provisional month) does not count, a lot sold since does; a lot held then without a price records
  nothing. The date comes from the lots held today, in one pass: the oldest price of a security sold
  since may be older. An asset with a value of that date or later keeps it, so a past price records
  nothing, unless the save replaced the last price of one of its securities: a corrected price of
  the day of `asof` records again (the last row of a day in `history.csv` counts). The Snapshot page
  imports and takes typed prices too (`Prices`). The Snapshot estimate, the asset sunburst and the
  `securities` tab read these files. No price is fetched: the justETF terms forbid automated
  queries. Gold (`XAU`, troy ounces) and Bitcoin (`BTC`) also take the last month of their series in
  euros (`prices.BY_SYMBOL`, a `Symbol` each: `gold` ships, `bitcoin` after a fetch; rule `series`),
  dated on its last day (the month-end close, or the monthly average of gold), a provisional month
  on its first: no later day of it is certain, so a value recorded since keeps its place. The newer
  of the last stored price and the series wins, the stored one on the same day: gold has no fetch
  and nothing deletes a price file, so one typed price must not fix the value for good. A save of
  any price records these assets too, and so does a fetch that changes the last price of a symbol: a
  month of `bitcoin` or of the dollar rate `usd-eur` (`prices.fetch_series`, on the Data page and by
  `series fetch`, a revision of its own; a new price of the same day, such as a provisional month
  fetched again, is corrected). Both series are monthly: no price by day.
- `src/dagobert/prices.py`: the price files: `read_prices` (a line that does not read, edited by
  hand, raises `InputError` with `prices/<security>.csv` and its line, `files.read_csv`, as
  `revisions` does for its log: a command ends with it, exit 1, the app shows `The inputs do not
  load`), `save` (the one writer: merges by date and records the market values, one revision of its
  `source`; returns `Saved`, the `Replaced` prices and the recorded values; `price_file` refuses a
  text that is no security, it names the file), `merge`, `Securities` (names by security, held
  first, then traded, then price files only; units held; trades), `off_trades`, `far_off` (the check
  of the CLI), `off_series` (a trade of `XAU` or `BTC` whose price per unit lies outside
  `Symbol.off` times its series in euros, of its month or up to `Symbol.lag` months before: gold
  `OFF` and 3 months, grams typed as troy ounces; Bitcoin, which doubled within months, 0.2 to 5 and
  1 month, a slip of the unit only; the trade form and the trades grid of the Assets page warn with
  it, rule `tracking`), `GRAMS_PER_TROY_OUNCE` (31.1034768, exact: the unit of `XAU`), `last_price`
  (the newer of the last stored price, of the given rows or the price file, and `series_price`),
  `series_prices` (the months of the series of a symbol, dated as `series_price` takes the last),
  `price_history` (the stored prices over those months, the stored one on the same day: the chart
  of the securities tab, rule `tracking`), `market_value` of lots, `record` (the texts of
  `assets.yaml` and `history.csv` inside the write of `save`, by `last_price` on its new price
  file; `corrected`: the replaced prices by security and day), `fetch_series` (`series.update`,
  then `record` when the last price of a symbol of `BY_SYMBOL` differs from the one before the
  fetch, as a revision of its `source`: `series/` is no input; it records after every fetch, also
  one without news, so a record that failed after an earlier fetch is made up; returns `Fetched`,
  the `Update` and the recorded values).
- `src/dagobert/csvimport.py`: a downloaded table of dated values. `sniff` decodes UTF-8 (BOM or
  not) or cp1252 (a file in neither, a spreadsheet or a PDF, is `RefusedError`: `Not imported`, `Not
  read`, no traceback), takes the delimiter (`;`, tab, `,`) under which a header row is followed by
  a row with a date and a number, and drops the lines before it; a file whose first row is data has
  an empty header (`column N`). `guess` gives the `Mapping`: the first date column, the price column
  by header (`Schluss`, `Close` before `Adj Close`, `Kurs`, `NAV`, `Rücknahmepreis`), else the last
  numeric one without volume, the decimal mark (the last of two marks, a mark before other than
  three digits, else `;` means a comma), the date order (year first `ymd`, dots `dmy`, a first part
  above 12 `dmy`, else `mdy`), a currency column. A month by its English or German name or
  abbreviation (`csvimport.MONTHS`: `Dec 31, 2025`, `31-Dec-25`, `31. Dez. 2025`) fixes the order
  itself: `read_date` ignores the mapping there, and `guess` gives the order it is written in (`mdy`
  or `dmy`). `parse` refuses a line with its reason (a missing cell, a date or a number that does
  not read, thousands groups that are not groups of three, a value not above zero, a date after
  `today` or a repeated one, another currency than EUR). The two import commands share their column
  options and the read (`cli.Columns`): `prices import` and `series import` (rule `series`). The
  equity import of the `Data` page uses it too, with `pricing.mapper`. `mostly`, `order` (the date
  order of some cells), `day` and `number` (a cell that does not read raises with it) serve the
  trade import too (rule `tradeimport`).
- `src/dagobert/ui/pricing.py`: the `Prices` expander of the Snapshot page and `mapper`, the mapping
  of a CSV of dated values by `ui.csvcolumns.select`: a select box per field (`ColumnPick`: a field
  that may lack a column offers none, one without a guess waits for a choice), then the date order
  and the decimal mark, each keyed by the header, so a new file starts from its guess; the trade
  import takes it too (rule `tradeimport`). `stored` names the series (`gold series`) in the count
  of a security that its series prices, and lists a price file without trades after the held
  securities, marked `(no trades)`: a history imported before its trades, which values no asset
  (`Securities.of` lists any CSV named like a security; one sold in full is left out).
