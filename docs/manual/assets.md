# Assets

On the Assets page you edit your assets: one tab for each kind, and the tab `securities` for the
trades of a depot. The [configuration reference](configuration.md#dataassetsyaml) describes every
field.

In simple mode the page shows the tabs of cash, fixed income, equity and pension policies, and the
tab of each other kind that your plan holds. The tab `securities` shows when an asset has trades or
a price file exists. A feature that is off hides its kinds in both modes, for example gold and
crypto. A note below the tabs names the hidden kinds. In simple mode each table also moves the
columns for experts that no row fills behind `All columns`, for example `tags`. A feature that is
off moves its columns there in both modes, for example `Basisrente`. See
[Simple and advanced mode, and features](index.md#simple-and-advanced-mode-and-features).

## The kinds of assets

- `cash`: a current account or cash. It earns the return of cash.
- `term deposit`: money fixed for a term at a rate (Festgeld). The simulation pays the interest
  when the deposit matures. It cannot use the money before that.
- `fixed income`: an overnight account (Tagesgeld), or a bond or money-market fund.
- `equity`: a depot of shares and funds. One depot is one asset, unless it holds funds with
  another Teilfreistellung (the share of the gains that is free of tax) or shares. Then keep one
  asset for each class. The column `Fund gains tax-free %` takes the share of the class: 30 for an
  equity fund, 15 for a mixed fund, 60 for a real-estate fund, 80 for a fund of foreign real
  estate, and 0 for shares, bonds, certificates and funds of gold or crypto. Empty, the asset
  takes the share on the [Assumptions](assumptions.md) page.
- `gold`: gold coins and bars, or a gold note.
- `crypto`: a wallet of Bitcoin or another coin.
- `property`: a flat or a house, by its size and its price per square meter. `bought for` is
  what the purchase cost, with the Grunderwerbsteuer, the notary and the broker. A let property
  also needs three fields: `bought in`, the month of the purchase, `building share`, the share of
  the building in the cost, and `AfA rate`, the yearly depreciation of the building. In simple
  mode they are behind `All columns` until a property holds them. The help of `AfA rate` names the
  rate of the law by the year in which the building was completed. A property is let when a rent
  on the Cashflows page names it.
- `loan`: a loan with its balance, rate, monthly payment and the end of its fixed rate. The
  simulation pays it off by itself. Do not add the loan payments as an expense. `financed
  property` names the property that the loan paid for: while that property is let, the interest
  lowers the tax of its rent.
- `pension policy`: a company pension (bAV) or a Basisrente. Mark a Basisrente in the column
  `Basisrente` and set its payout to `annuity`: a Basisrente pays no lump sum. In the statutory
  health insurance, a company pension pays health and care contributions, a Basisrente pays them
  only for a voluntary member. If you pay into a company pension from your salary
  (Entgeltumwandlung), enter the monthly amount in `salary conversion` and keep the full gross
  salary on the Cashflows page. `converted salary` names the salary stream, a monthly salary
  without `of` (no bonus). Empty, the conversion takes the first monthly salary that pays in the
  month. `employer subsidy` is the share that your employer adds by contract. Empty, the employer
  adds the 15% of the law, as far as the conversion saves it social insurance. The conversion
  pays in the phases of the policy (`phases`) until it matures. A Basisrente takes your own
  payments in `own premium per month`, from the cash in the phases of the policy until it matures.
  The premium lowers your income tax. A Basisrente takes no contribution of an employer and no
  salary conversion. Its pension is taxed at the share of the year in which it starts, as the
  statutory pension: 84% for 2026, half a point more for each later year.
- `pension depot`: the Altersvorsorgedepot, the state-subsidized pension depot from 2027. You get
  one state grant for all your depots. From 2027 each child whose Kindergeld you get adds a grant
  of up to 300 € a year: enter your children on the [Assumptions](assumptions.md) page.

## Edit an asset

1. Open the tab of its kind.
2. Change a cell, or add a row at the end of the table.
3. Read the list of changes below the table.
4. Press `Save` at the top of the page.

To take a save back, press `Undo` at the top of the page ([Undo a save](index.md#undo-a-save)).

The column headers are plain words, for example `as of` for the date of the value and
`check every (months)` for its update interval. On a computer, hold the pointer over a header to
see its help. The help also names the key in the file, for example `asof`. On a phone, the button
`What the columns mean` above the table shows the help of all columns.

Other files and the history name an asset by its `ID`, so you cannot change the ID of a saved
asset in the table. To change it, press `Rename` above the table. Select the asset and type the new
ID. The dialog lists each line that changes in each file, also the rows of the history. Press
`Rename` in the dialog to write all of them as one change. The new ID must be new: an ID that an
asset, a scenario or the history uses already is refused. If the table holds edits that are not
saved, `Rename` stays off until you save or discard them. A rename does not change a `fixed` run.
A Monte Carlo run draws the random price of a sale by the ID of the asset, so after a rename it
draws other prices.

A share or a rate takes percent: type `2.5` for 2.5%. A loan balance is saved negative, also if
you type it without a minus. A new value of an asset also sets its date and adds a row to the
history, as the [Snapshot](snapshot.md) page does.

## Open an asset from a link

The [Overview](overview.md) and the [Snapshot](snapshot.md) page link to an asset that needs your
attention. The link opens the tab of the asset on this page:

- The row of the asset comes first in its table.
- A blue box above the table names the asset and the columns to check.
- The headers of these columns start with `⚠`, for example `⚠ value` and `⚠ as of`. The app cannot
  color the cells themselves.
- On a phone, these columns come right after the ID, so you see them without a swipe.

The mark stays while you edit. It goes when you save a change of the row, or when you open the page
again without a link.

## Securities

The tab `securities` lists the assets that can hold securities: depots, fixed income, gold and
crypto. The asset with the most trades comes first. Select one. For each security the page shows:

- its value, its gain, and its yearly return over all its trades (`yearly return %`), nominal
  and after inflation (`real yearly return %`)
- the units that you still hold and what they cost
- the open lots (the units of each purchase that you still hold) and the sales.

The units show with a decimal point and a small space between the thousands, for example
`1 234.5678`. The table of trades shows them the same way. A table always writes a decimal point,
also on a German page. A text, such as the preview of an import, writes the units in the way of the
language: `1 234,5678` on a German page.

The yearly return weighs each amount by how long it was invested. The value uses the last stored
price (see [Snapshot](snapshot.md#prices)).

Below them, under `Trades`, is the table of trades. Enter each trade as your bank shows it, also
of securities that you sold:

- `date` and `kind`: `buy`, `sell` or `vorabpauschale`. The Vorabpauschale is a part of the
  expected gain of a fund that is taxed each year before a sale. Your bank reports it. Gold and
  crypto have no Vorabpauschale.
- `ISIN or symbol`: the ISIN, or a symbol such as `XAU` for gold in troy ounces or `BTC` for
  Bitcoin.
- `units`: the number of units. Do not group the thousands.
- `amount`: the market value of the trade without fees (Kurswert), or the Vorabpauschale of the
  fund.
- `fees`: the fees of the trade.
- `name`: the name of the security. The last name that you give names it everywhere.

A sale takes the oldest units first. The tax law says so for funds and shares, and the tax office
allows it for crypto. For gold, the app assumes it. Date a Vorabpauschale with its booking in
January. It counts for the year before. The open lots give the cost of the depot for the tax on a
sale. The trades do not change the value of the depot: record that on the Snapshot page.

On a phone, the form `Add a trade` above the table saves one trade at once. A message names the
units, the price per unit and the euros, so that you see a typing error at once. For gold, the form
offers `XAU`, and for crypto `BTC`. If the app cannot add the trade, it says why right below the
button `Add`, for example `enter the amount in euros`, and it frames the field to correct in red.
Type a fraction with a comma, for example `1,2` units. While the table of trades holds edits that
you did not save, `Add` is off: save or discard them first.

An account without securities, such as an overnight account, needs no trades. Record its value on
the Snapshot page.

## Import trades

A savings plan buys every month, so its trades add up fast. You can import them from the export of
your broker, a CSV file. The app reads the exports of these brokers by the names of their columns.
`Where to get the file` below the text of `Import trades` tells where each broker keeps it:

- Trade Republic: in the app, Profile > Account statements > Transaction export. Then choose the
  period and press Create. The app has this export since April 2026.
- Scalable Capital: in the transactions of the broker, select all and export them as CSV (with
  PRIME and PRIME+).
- comdirect: the Depotumsätze of the depot as CSV.

ING and Consorsbank offer no export of the trades of a depot. For any other file, you choose the
columns yourself. The file needs a date, an ISIN, the units and the amount in euros of each trade.

1. Open the tab `securities` and select the asset.
2. Open `Import trades` above the table of trades and choose the file.
3. If the app did not find a column that a trade needs, `Check the columns read from the file`
   opens: choose the column. Else it stays closed. Open it to see the columns that the app
   chose.
4. Read the preview.
5. Press `Import N trades`.

If the file is not a table, for example a PDF or the statement of the cash account, the app says
so and reads nothing.

The app takes only buys, sales and savings plans in euros. It leaves out the other rows, such as
dividends, deposits, taxes, transfers and cancelled orders, and counts them in the preview. The
amounts and the fees lose their minus. If a row has no kind, a minus before the units makes it a
sale.

The preview shows:

- how many new trades the import adds, with the dates of the first and the last, and how many
  trades the asset holds already
- per security, the new trades and the units that they add, so that a wrong security shows
- the first and the last three new trades with their price per unit, so that a wrong decimal
  mark shows. The units and the euros show as in the table of trades: `1 234.5678` units and
  whole euros.
- in a second line, how many rows the app leaves out. `Other rows left out` lists them with their
  line in the file and their cells.
- the lines that the app refuses, with the reason.

A row with the same date, ISIN, units and amount as a trade of the asset is a trade that the asset
holds already. The import leaves it out, so you can import the same months twice. If the file holds
the same trade twice on one day, the second one counts as a new trade. The app refuses a row that
the asset cannot take, for example a sale of more units than the asset holds on that day, or a
symbol such as `XAU` in a depot. A Vorabpauschale is not in the exports: add it by hand. If a price
per unit is far from a stored price of the security, the app shows a warning.

If you edited the table of trades and did not save, the import button is off: save or discard the
edits first. If
another device changed the trades of the asset after the preview, the import saves nothing. The
preview then shows the trades as they are now. Look at it again and press the button again.

On the command line, `uv run dagobert trades import depot export.csv` imports the file into the
asset `depot`. It shows the columns and the preview. Add `--dry-run` to see the preview without a
save. `--column units=Menge` chooses a column by its name, and `--decimal` and `--dates` set the
decimal mark and the order of the date. The command stops at a price far from a stored price, or
for `XAU` and `BTC` far from its series. Add `--force` to save it anyway. If it refuses lines and
finds no new trade and no trade that the asset holds already, it stops with an error.

## Gold and crypto

A sale of gold or crypto is free of tax when you held the units for more than a year. If you sell
earlier, the gain is a private sale (§23 EStG). You declare it in the Anlage SO. The tab
`securities` shows this for a gold or crypto asset:

- `tax-free units`: the units that you can sell today without tax.
- In the open lots, `tax`: `free`, `private sale` or `capital`. `free from` is the first day on
  which a sale of the lot is free. It is the day after the first anniversary of the purchase.
- In the sales, one row for each kind of tax in a sale. Each row has its part of the proceeds, its
  cost and the dates of the purchases. The rows with `private sale` are the lines of the Anlage SO.

The units with `capital` pay the flat tax on capital income (§20 EStG) when you sell them, also
after a year. These are the units of an asset with `tax: capital`, for example a gold note without
physical backing. If `tax.crypto_capital_from` in `assumptions.yaml` has a month, the crypto that
you buy from that month on is `capital` too.

Enter gold and crypto like this:

- `XAU` counts troy ounces. One troy ounce is exactly 31.1034768 g, so a bar of 100 g is
  100 / 31.1034768 troy ounces.
- An asset without trades counts as held for more than a year, so a sale is free of tax.
- Keep one security in each asset. The simulation does not read prices. It splits the value of an
  asset with more than one security over its lots by their cost.

The app shows a warning when the price per unit of an `XAU` trade is less than half or more than
double the gold series of that month. This catches grams that you typed as troy ounces. For `BTC`,
the limits are one fifth and five times the Bitcoin series, because the price of Bitcoin can
double in a few months. The simulation counts whole months, so it can free a unit up to one month
later than the law.
