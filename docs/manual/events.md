# Events of a scenario

The tab `Events` of the Scenarios page shows the events of the chosen scenario file. An event is a
dated change of the plan, for example a sale, a severance or a new income stream. The
[configuration reference](configuration.md#datascenariosyaml) describes each type and its fields.

There is one tab for each type of event. Each tab names its type in words:

| Tab | Type in the file |
|---|---|
| Sell an asset | `sell` |
| Repay a loan | `repay` |
| Severance pay | `severance` |
| Pay into a policy | `fund_policy` |
| One-off payment | `lump_sum` |
| Write off shares | `write_off` |
| End streams | `end_streams` |
| Change a stream | `set_stream` |
| Add a stream | `add_stream` |
| Buy gold or crypto | `buy` |
| Buy a property | `buy_property` |
| Inheritance | `inheritance` |
| Gift | `gift` |

The label shows how many events of that type the file holds, and how many it takes from the
scenarios that it extends: `Sell an asset (1, 2 inherited)`. A dot after the label, `Sell an asset
(1, 2 inherited) ●`, shows that the tab holds edits that you did not save. The page opens on the
type of the first event of this file, else on the first type with inherited events.

In simple mode the strip shows `One-off payment`, `End streams`, `Change a stream`, `Add a
stream` and each type that a scenario file holds. `Sell an asset` shows when your plan holds a
property, gold or crypto. A feature that is off hides its types in both modes, for example `Buy a
property`. A tab with edits that you did not save stays. A note below the strip names the hidden
types. See [Simple and advanced mode, and features](index.md#simple-and-advanced-mode-and-features).

## Add an event

1. Open the tab of the type.
2. Open `Add an event` above the table. The form shows only the fields of the type.
3. Fill in the fields. Type the month as `2027-05` or `05.2027`.
4. Press `Add`.

If the table holds edits that you did not save, `Add` is off: save or discard them first.

## Edit the events of the file

1. Open the tab of the type.
2. Change a cell, add a row at the end of the table, or delete a row.
3. Read the list of changes below the table.
4. Press `Save` at the top of the page.

The month in the column `month` counts, the day does not. A share or a rate takes percent: type
`5` for 5%. A select lists the names that exist in your files, for example the loans for `Repay a
loan`. A sale on a condition has no month: it sells at the age in `or at age`, or earlier when the
liquid assets fall below `or when liquid below`. The rare columns, such as the price spread or the
sale costs of a sale, show when you switch on `All columns`. The row of `Add a stream` has the
columns of a stream, as on the [Cashflows](cashflows.md) page. For a savings plan, set `kind` to
`savings`, and set the asset that it buys in `into`, behind `All columns`.

The table of `Buy a property` shows the month, the name of the property, the price, the
`Bundesland` and the `loan amount`. The other columns of the property and of its loan, such as the
ids and the rate, show when you switch on `All columns`. The loan amount shows without a minus: it
is the amount that you borrow. The file keeps it below zero. Fill in either `Bundesland` or,
behind `All columns`, `or transfer tax`. `Bundesland` shows the name of the Land, such as `Lower
Saxony`, and the file keeps its code, `NI`. A new
row makes the `property id` and the `loan id` from the names, as the form does. After the save, the
ids stay: sales and repayments name them. To change one, press `Rename` beside `All columns`: it
changes the id in every file that names it. The guide [Buy or rent](buy-or-rent.md) explains the
fields.

In the form `Add an event` of a purchase, you can leave the ids empty. The form then makes them
from the names: `Own flat` gives `own-flat`, and the loan takes the name of its own, else
`own-flat-loan`. An id that your files hold already gets a number, such as `own-flat-2`. Type the
loan amount without a minus. Fill in one of `Bundesland` and `Transfer tax`, not both.

## Inheritances and gifts

An inheritance or a gift comes from a relative. Add the relative on the
[Assumptions](assumptions.md) page first: the column `from` lists the relatives by their short
names. Type the cash in nominal euros, as in a one-off payment. The net proceeds of a property that
you expect to inherit go into the cash too. The securities take their value in euros of the start
(`securities`) and the amount that the relative paid for them (`their cost basis`, nominal).

If you leave the month of an inheritance empty, the inheritance comes at the death of the
relative. The simulation draws that month for each future from the life table. If the
inheritance names two relatives, for example both parents with a joint will (Berliner Testament),
it comes at the later death. A gift always has a month and one relative. The
[models](models.md#an-inheritance-or-a-gift) page explains the tax.

## The id of an event

An `id` names one or more events and phases. The overrides of a scenario use it to move them
(`shift`) or to change a field (`events`). Events with the same id move together. Below the table,
the page names the ids that another scenario uses. If you change such an id, change it there too.
Otherwise the app does not save.

## Repayments of a sale

Below the table of sales, select a sale. Its table lists the loans that the sale repays. If the
amount is empty, the sale repays all of the loan. The toggle `Invest the rest` puts the rest of the
money into your portfolio. Press `Save repayments`. A sale on a condition, for example at an age,
happens only in some paths of the simulation. It cannot repay a loan.

## Inherited events

Below the tabs, `Inherited events` lists the events that the scenario takes from the scenarios
that it extends. The column `set in` names the scenario of each event. An event that this scenario
or one between leaves out shows with `left out by`. An inheritance without a month shows `at death`
as its month. You cannot edit them here. To edit one, open its scenario.

You can leave out inherited events by their id. Each switch names the id and how many phases and
events it leaves out, for example `Leave out car (2 events)`:

1. Switch on `Leave out` with the id.
2. Read the list of changes below the table of the open tab, for example `leave out car (2
   events) no → yes`.
3. Press `Save` at the top of the page. It saves the switches together with the edits of the
   events of the open tab.

This leaves out every phase and event of those files with that id, also in the scenarios that
extend this one. The tab `Phases` has the same switches for the phases. An event without an id
cannot be left out. Give it an id in its file first.

If another device changed the file since the page showed it, the page says so. Your edits stay.
Press `Discard my edits` to see the file as it is now.
