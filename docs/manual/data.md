# Data

The Data page shows the external series that the simulation uses, such as the consumer prices.
A line at the top counts the series that are ready. It also names the optional series that you did
not fetch yet, and what each one is for. Six series ship with the app and are always ready. Two
are optional: MSCI World and Bitcoin. If your assets hold Bitcoin without a price of your own, the
Bitcoin series is needed: the line and its box show a warning. Fetch the series, or type in a price
on the Snapshot page. Each series has a box with:

- its title, and whether it ships with the app or is optional
- the months that the app holds: shipped with the app, or fetched or imported by you. A month
  that the source can still change shows as `an estimate`.
- what uses the series
- the source note, as the terms of the source require it
- `License and source`: the license, a link to the terms and to the source, and the name of the
  series for the command `dagobert series`.

Nothing is fetched by itself. The app sends a request to a source only when you press a fetch
button. Fetched and imported months stay in the folder `series/` of your data directory.

In simple mode, the navigation shows this page only when your plan holds a fetched or imported
series.

## The series

- `vpi-west`: the consumer prices of the former West Germany, up to 1990. Final, nothing to fetch.
- `vpi`: the consumer price index (VPI) of Germany, from 1991. The app joins it with `vpi-west`
  into one series of consumer prices. The `historical` model, the roll forward and the correction
  of your records for inflation use it.
- `umlaufsrendite`: the yield of German bonds. The `historical` model uses it for fixed income.
- `msci-world`: the MSCI World index in euros, with the dividends reinvested. The `historical`
  model uses it for equity. It does not ship, because its terms allow only informational,
  non-commercial use. Without it, the `historical` model is off.
- `gold`: the gold price in US dollars. It values gold (`XAU`) without a price of its own, and the
  `historical` model uses it for a gold asset. A new release of the app brings the next months.
- `bitcoin`: the Bitcoin price in US dollars at the end of each month. It values Bitcoin (`BTC`)
  without a price of its own. It does not ship, because its license allows only non-commercial use.
- `usd-dem` and `usd-eur`: the exchange rates that convert gold and Bitcoin into euros.
- The life table (Sterbetafel) of Germany: the survival probabilities for the chance to run out
  over a lifetime (`P(broke) alive`), the chance of care (`P(care)`), the chance of a disability
  (`P(disability)`) and how deep the money falls when it runs out (the typical
  shortfall). A new release of the app brings the next table.

[SOURCES.md](../../src/dagobert/data/SOURCES.md) gives the source and the terms of each shipped
file.

## Fetch new months

Only a series whose source publishes new months has a fetch button. A final series, whose source
adds no months, has none. The gold series and the life table have none either: a new release of
the app brings their next months.

1. Press `Fetch missing months` in the box of the series.
2. Wait for the result below the button, for example `Added 1 month, up to 2026-09` or `Already
   current, up to 2026-09`, or the error. If the source changed months that the app holds, the
   app replaces the stored months, and the result says how many differed. When the new months
   change the price of your gold or Bitcoin, the app records their market values, and the result
   names them too (see [Snapshot](snapshot.md)).

`Undo` at the top of the page takes back the market values that a fetch recorded. The fetched
months stay, because they are no input ([Undo a save](index.md#undo-a-save)).

If the Bundesbank refuses the request, you sent several requests in a short time. Wait at least
half an hour, then try again. The command `uv run dagobert series fetch` fetches every series at
once.

## Import the MSCI World series

Instead of a fetch, you can import a history of the MSCI World index, or the prices of an ETF that
follows it:

1. Download the history as a CSV file. The values must be in euros.
2. Open `Import a CSV` in the box of `msci-world` and upload the file.
3. Make sure that the app found the correct columns: the date, the order of day, month and year,
   the value and the decimal mark. A date with the name of the month, such as `Dec 31, 2025` or
   `31. Dez. 2025`, needs no order.
4. Read the preview: the months, the new, changed and dropped months, and the lines that the app
   cannot read.
5. Press `Import N months`.

The import replaces all stored months, because an ETF and the index have different scales. The
app keeps the last value of each month. A gap of missing months between two months stops the
import. The command `uv run dagobert series import msci-world FILE` does the same.

The page [Export and import](transfer.md) makes a zip of your data directory and imports one.
