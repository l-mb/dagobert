# Snapshot

On the Snapshot page you record the values of your assets as you see them, for example once a month
from your bank statements. The app then compares these records with your plan on the
[Overview](overview.md).

In simple mode, the navigation shows this page only when your plan holds a record of a value or a
trade of a security. The feature `Records` of the [Features](features.md) page hides it in both
modes.

## Record values

The table comes right below the tiles. It has a row for each asset. `current` is the value in your
inputs, `estimate` is what the app expects today, and `new` takes the value that you observed.
`measure` tells what the numbers are: the value, or the balance of a loan. For a property,
`current` is its whole value: the price per square meter times the square meters. The column
`price per m²` shows the price per square meter. A `⚠` before an asset marks a value that needs an
update. Its date (`as of`)
is older than the update interval of the asset, twelve months unless you set another, or it has
no date (`never`). The section `How the columns work` below the table explains each column.

On a phone, the table shows `asset`, `current`, `new` and `unchanged` first. To see the other
columns, swipe the table to the left. A long name takes two or three lines.

This page dates each value with the day of `Observed on`. To type a value together with another
date, use the links below the table. Each link opens an asset with a `⚠` on the
[Assets](assets.md) page, where `as of` takes any date.

1. Set `Observed on` to the day of your values.
2. Type each value into `new`. For an account, type its balance. For a loan, type the balance that
   you still owe, with or without a minus. For a property, type its whole value. The app saves the
   price per square meter that gives this value.
3. If a value did not change, tick `unchanged` in its row. The app then keeps the value and gives
   it the new date. This also clears the `⚠` of a value that is still correct.
4. If you want to take over the estimates, press `Take estimates`. It fills the empty `new` cells
   from `estimate`. It skips term deposits, because their value is the amount invested, without
   interest. It also skips an estimate that is equal to the current value. A message tells how many
   estimates it took, and which rows it skipped and why.
5. Read the list of changes. It names each field as the [Assets](assets.md) page does, for
   example `as of` for the date. It shows cents only for a value that has cents.
6. Press `Record` at the top of the page. The button shows the number of changes, for example
   `Record 3 changes`.

The app saves each new value with its date in `assets.yaml` and adds a row to `history.csv`. For a
company pension, the app also saves `paid`, the contributions up to the new date, in the same way as
the estimate. It does this for a typed value and for a tick of `unchanged` too. The estimate of a
loan is its balance after the scheduled payments. The estimate of a term deposit includes the
interest so far. The estimate of a company pension or an Altersvorsorgedepot adds the mean return of
its class and the contributions since its date, as the simulation does at its start (see [How the
simulation works](models.md#the-values-at-the-start)). The estimate of an asset with trades uses the
last prices of its securities. For gold (`XAU`) and Bitcoin (`BTC`), the app takes the last month of
their series when it is newer than your last price.

A term deposit takes no new value: its contract gives the value. If you type one, the app does not
save it and shows a warning.

`cost basis` is only for a depot without trades: what you paid for the shares, which the tax on a
sale needs. A depot with trades gets its cost from the trades on the [Assets](assets.md) page. A
cost basis alone does not change the date of the value: the value still needs its update.

If the values that you just recorded are wrong, press `Undo` at the top of the page. See
[Undo a save](index.md#undo-a-save).

## Correct a recorded month

Each record adds a row to `history.csv`: the date, the asset and the value. The charts of your
records on the [Overview](overview.md) use these rows. To change or remove a row that you
recorded by mistake, use the section `Correct a recorded month` below the table.

1. Open `Correct a recorded month`.
2. Select the month in `Month`. The table shows the rows of that month: the date, the asset and the
   value as recorded. The value of a property is its full value, and the value of a loan is its
   balance below zero.
3. To change a value, type the correct value into `value`. For a loan, type the balance with or
   without the minus.
4. To remove a row, tick `remove`.
5. Read the list of changes. A removal always shows a warning, and the button shows a `⚠`.
6. Press `Save the correction`.

The correction changes only `history.csv`. The value in your inputs, `current` in the table above,
stays. To change it too, record the value again above, or change it on the [Assets](assets.md)
page. If another device recorded into the same month after the table showed, the app refuses the
correction and tells you when and where the month changed.

## Prices

Dagobert does not download the prices of your securities. You add them in the section `Prices`
below the table. It opens by itself while a security that you hold has no price, and a note above
the table names that security. Its table shows each security that
you hold, with the date and the euros of its last price. Then it shows the securities that have
prices but no trades yet, marked `(no trades)`. This happens when you import a price history before
you enter the trades.

To add one price:

1. Under `Add a price`, select the security, or type its ISIN or a symbol such as `XAU`.
2. Set the date of the price. It can be a past date.
3. Type the price in euros for one unit. Do not group the thousands: type `5432.10` or `5432,10`.
4. Press `Add`. A message shows the value of your units at this price, so that you see a typing
   error at once.

To import a price history of one security:

1. Download the price history as a CSV file, for example from your broker or from the website of
   an exchange. The prices must be in euros.
2. Under `Import a price history`, select the security of the file in `Security`, or type its ISIN.
   The select starts empty, and the app reads no file until you chose the security.
3. Upload the file.
4. Make sure that the app found the correct columns: the date and its order of day, month and
   year, the price, the decimal mark and the currency, if there is one. A date with the name of
   the month in English or German, such as `Dec 31, 2025` or `31. Dez. 2025`, needs no order.
5. Read the preview: the number of prices, the new and the replaced prices, and the lines that the
   app cannot read.
6. Press `Import N prices`. After the import, the select of the security is empty again.

The app shows a warning for a price that is less than half or more than double another price. It
compares with the stored price of that day and with the price of a trade within five days. After
each saved price, the app records the market value of each asset whose securities all have a price.
The date of that value is the date of the oldest of those prices. The value counts the units that
you held on that date: a purchase after that date does not count yet, and a sale after that date
does not reduce it.

Gold coins and bars (`XAU`, in troy ounces) need no price of their own. Without a newer price, the
app takes the last month of the gold series, which ships with the app. Bitcoin (`BTC`) takes the
last month of the Bitcoin series in the same way, but only after you fetched that series on the
[Data](data.md) page. Until then, Bitcoin needs a price of its own. When a fetch of the Bitcoin
series or of the dollar rate changes the price of gold or Bitcoin, the app records the market
values again.
