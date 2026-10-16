---
paths:
  - "src/dagobert/series.py"
  - "src/dagobert/ui/data.py"
  - "src/dagobert/data/*.{csv,md}"
  - "scripts/refresh_shipped.py"
  - "tests/test_{series,ui_data}.py"
---

# External series

The sources and terms of each shipped file: `src/dagobert/data/SOURCES.md`.

- `uv run dagobert series list` prints per series and for the life table the months, the provisional
  ones, the origin (shipped, fetched with the date of the file) and the source note. `series fetch
  [NAME...]` runs `series.update` for the named series, without names for every one with a fetch
  (two requests to the Bundesbank, one each to Curvo, Coin Metrics and the ECB), through
  `prices.fetch_series`: a new price of gold or Bitcoin records the market values, a revision of
  `series fetch` per series, and prints them like `prices import` (rule `prices`); after a
  `FetchError` it asks that host no more (`urlsplit(Series.source)`), goes on with the others and
  exits with 1, so does a record that the inputs refuse (`ValueError`, `OSError`: `<name>: not
  saved: <reason>`). `series import msci-world FILE` reads a download with the column options of
  `prices import` (`cli.Columns`), or a file of `month,value[,provisional]` rows as it is
  (`series.month_values`: the `msci_world.csv` of an older data directory), and writes it through
  `series.month_ends` and `series.save`, which refuses a gap (exit 1); only a series with `imports`
  takes one. Nothing else fetches: the app on the button of the Data page only.
- `uv run python scripts/refresh_shipped.py` (maintainers, before a release) downloads the
  shipped series again (`series`): every series with `delivered` byte for byte, whole (three
  Bundesbank files and the ECB file, 5 s apart: the Bundesbank refuses a burst), the newest
  Destatis life table, the West German CPI extract and the gold extract (`gold_csv`: the link to
  `CMO-Historical-Data-Monthly.xlsx` on `series.WORLD_BANK`, refused when its `Updated on` is
  more than `STALE` days old), both read with openpyxl (dev group only, no run-time dependency).
  It prints the changed files, and the sources of the gold prices (sheet `Description`) when the
  source note of `gold` lacks them: the dataset terms of the World Bank (`WORLD_BANK_TERMS`) ask
  for `The World Bank: Dataset name: Data source`. Then update the dates in `SOURCES.md`.
- `src/dagobert/series.py`: the registry of the external series (`SERIES`: name, title, use, source
  URI, attribution, licence, terms URL, shipped file, `delivered` (the `Sdmx` service whose whole
  answer the shipped file is; it gives `Series.parse`, else `parse_month_value`), fetch, `imports`,
  `final` (the source adds no months), `usd`), their reads, the fetch and the import.
  `MonthlySeries` lives here (`returns` imports `series`). `read` gives the shipped rows overlaid by
  the months fetched into `<data>/series/<name>.csv` (`month,value,provisional`,
  `parse_month_value`), a fetched month wins. Only a fetch or an import writes there, no user
  records; `msci-world.csv` (MSCI World net EUR, index terms: non-commercial use) and `bitcoin.csv`
  (CC BY-NC) are never redistributed. `load` gives a `MonthlySeries` as the model reads it, a `usd`
  series in euros (`in_euros`), None without rows (`msci-world`, `bitcoin` before their first
  fetch). `usd_per_eur` chains the Deutsche Mark per US dollar of the Bundesbank (`usd-dem`, to
  1998-12) at `DEM_PER_EUR` (1.95583, Regulation (EC) No 2866/98) to the ECB rate (`usd-eur`, from
  1999-01): the terms of both forbid a change of the shipped files, so the app converts in memory.
  `in_euros` divides each month by its rate; a month after the last rate takes the last one and is
  provisional. `gold` (World Bank, monthly average) and `bitcoin` (Coin Metrics, the close of the
  last day of a month) are in US dollars, the rates monthly averages. `prices.series_price` reads
  them in euros for `XAU` and `BTC` without a price file (rule `prices`). The `historical` model
  replays `gold` for a gold asset (`returns.REPLAYED`, rule `returns`), never `bitcoin`: it draws
  that class. `cpi` chains the West German CPI (`vpi-west`, to 1990-12) to the VPI at run time, the
  older series rescaled to the VPI of 1991-01: the Bundesbank terms forbid a change of the shipped
  file. The `historical` model and the roll forward read `cpi`; `consumer_prices` gives it by day, a
  day after its end at its last month, for the real returns of the `securities` tab and the observed
  values of `balance_figure` (`report.Observed`). `update` fetches from the first provisional month,
  else the last one (one month of overlap), or, for a series that ships a file, from the first
  fetched month when that is earlier: a newer shipped file can revise the fetched months, and one
  fetch then heals them. A final month that differs is a revision, or a month of an import: then the
  whole series replaces the fetched file (`Update.replaced`). An empty answer or one without news
  writes nothing. `Update.text` says the result to the user, in the CLI and on the Data page (`added
  3 months, up to 2026-09`, `already current, up to 2026-09`). A fetch takes a `Getter` (url to
  `Response`, `http_get` by default, tests pass a fake), runs only on a user action, sends
  `USER_AGENT` and raises `FetchError`. An answer that `Sdmx` cannot read, and a
  `http.client.HTTPException`, are a `FetchError` too. A `FetchError` puts URL and key in backticks
  (the page renders markdown, which took a `_` for italics) and names the `reason` of a `URLError`.
  An HTML page of the Bundesbank is its rate limit (`RATE_LIMIT`, an Enodia challenge after about
  seven requests in half an hour, which lasted over 20 minutes). `Sdmx` is a monthly series of an
  SDMX service without an account, `startPeriod` for the months from: `bundesbank` parses `bbk_csv`
  (`parse_bbk`: the `YYYY-MM;value;flags` rows, a flag marks a provisional month), `ecb` the
  `csvdata` of the ECB data portal (`parse_ecb`: the columns `TIME_PERIOD`, `OBS_VALUE`,
  `OBS_STATUS` E, F or P provisional; an empty body for no months; it publishes complete months
  only). Curvo sends the whole file, so a changed month replaces it without a second request.
  `coin_metrics` asks the community API (`COIN_METRICS`, no key; the host `api.coinmetrics.io` of
  its documentation wants one) from the first day of the month, follows `next_page_url` (only on
  `COIN_METRICS_ORIGIN`, at most `COIN_METRICS_PAGES`, else `FetchError`) and keeps the close of the
  last day of each month: a month without its last day is provisional. Its data is CC BY-NC: fetched
  into `<data>/series/` only, never shipped. An import of a series with `imports` (`EQUITY`,
  `msci-world`): `month_ends` turns the dated values of a download (an index history, the prices of
  an ETF) into the last value of each month, the month of today provisional (a fetch then sees no
  revision there); `save` replaces the fetched file with them and refuses a `gap` (missing months
  between two: `returns._align` raises on one). `life_table()` finds the one
  `sterbetafel-<period>.csv`, with its report and source note (`LIFE_TABLE_SOURCE`,
  `LIFE_TABLE_ATTRIBUTION`: the refresh script names new ones).
- Without the equity series the `historical` model is off: `returns.make_provider` raises
  `MissingSeriesError` (the CLI exits with 1 and the message), `runs.models` leaves it out.
  No fallback: Shiller has no licence.
- `src/dagobert/data/`: shipped series, read only, see `SOURCES.md` there (source, terms and
  source note of each file): `destatis_vpi_west.csv` (1962-01 to 1999-12, an extract),
  `worldbank_gold.csv` (from 1960-01, an extract, whole dollars as stored),
  `bundesbank_vpi.csv`, `bundesbank_umlaufsrendite.csv` and `bundesbank_usd_dem.csv` (1948-07 to
  1998-12) as delivered (`bbk_csv`), `ecb_usd_eur.csv` as delivered (`csvdata`, from 1999-01),
  `sterbetafel-<period>.csv`.

## Data page

- `src/dagobert/ui/data.py`, the page `Data` in the navigation section `Setup`: a one-line intro,
  the rest folded (`READING`), then a summary (`data.summary`: `6 of 8 series are ready.` and the
  optional ones without months, each with its use: a first user saw two warnings and could not tell
  whether to act; a warning, first, the series that the assets need: `data.needed`, a symbol of
  `prices.BY_SYMBOL` held without any price, Bitcoin before its fetch and its price file), then one
  bordered container per `series.SERIES` entry in registry order, then the life table. Each shows
  the title, whether it ships or is optional (fetched on request), the months (`data.held`: first to
  last, a provisional month as `an estimate`, shipped up to, fetched (or imported, for a series with
  `imports`) up to, on the date of the file), what uses it (`used_by`, in words: `the value of gold
  (XAU) without a price file of your own`) and the source note, verbatim (`Quelle: …` too) and
  visible: the terms make it a condition of redistribution, so it shows in the product. The license
  (US spelling in the UI) with the terms link, the source link and the name of the CLI and the file
  sit in the expander `License and source`. A series with a fetch has `Fetch missing months`:
  `prices.fetch_series` in a spinner, then a rerun so the months take it, and the outcome below the
  button for the session (`Update.text` and the values it recorded, `pricing.recorded`; the text of
  `FetchError`, among them `RATE_LIMIT`). The page passes `series.http_get` at the click, so a test
  replaces it. A series without a fetch says that its source is final (`final`) or that a release
  brings the next months. A series without rows shows an info (it is optional): fetch it, or import
  a CSV for one with `imports`; a needed one a warning: fetch it or type in a price on the Snapshot
  page. A failed record after a fetch (`ValueError`, inputs that refuse it) shows `Not saved:` like
  an `OSError`. A series with `imports` has `Import a CSV`: `csvimport` with `pricing.mapper`,
  `series.month_ends`, a preview (months, new, changed and dropped against the stored ones, the
  first and last three, refused lines) and `Import N months`, which replaces all stored months: an
  ETF and the index differ in scale, so no merge. A `series.gap` shows an error and turns the button
  off. Stored months that go (`data.ranges`) or change show a warning, and the button carries
  `guard.MARK`. No guard list: `series/` holds no user records. A caption below a series
  (`data.NOTES`) names the join of `series.cpi` under `vpi` and the conversion of `series.in_euros`
  under `usd-eur`. Nothing fetches on start or on a timer. In portrait the fetch and import buttons
  take the full width (`ui/page.css`).
- Last a bordered box `Kept results` (`data._cache`, owner 2026-10-16, issue #28): the folder
  `.cache` of the results kept over a restart (`KEPT`, its bound `cache.BYTES`, rule
  `explorer-runs`) and `Clear cache (<size>)` (`money.format_size`), off while empty. A tap asks
  `Clear the … of kept results?` with `Clear` and `Cancel` (session state `CLEARING`); `Clear`
  empties the cache on disk and in the process (`runs.forget`), with a toast of what it freed and
  no revision: the results are no input. Without a cache on disk (`cache.folder` None: a data
  directory that takes no write, an export zip as `--data`) a caption says that the app keeps them
  in memory (`IN_MEMORY`), no button. Simple mode shows the page only with a series (rule `mode`).
- Words of the page (rule `i18n`): `Series.title`, `used_by` and `licence` hold English marked
  `N_` (a German term, `Datenlizenz Deutschland`, unmarked), said where the page shows them; the
  source note stays as written (the terms). `data.updated` says an `Update` in a sentence (the CLI
  prints `Update.text`), `series.gap` speaks the language of the session, English in the CLI.
