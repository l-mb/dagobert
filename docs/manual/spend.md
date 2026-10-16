# Spend

On the Spend page you record what you spent each month, by category, and you compare it with your
plan. The records go into `actuals.csv` in the data directory.

In simple mode, the navigation shows this page only when your plan holds a record of what you
spent. The feature `Records` of the [Features](features.md) page hides it in both modes.

## Add an amount

The form `Add` adds one amount to a month at once, for example a receipt.

1. Select a category, or type a new one.
2. Type the euros that you spent, without a minus.
3. Select the month in `Add to month`. The current month comes first.
4. Press `Add`.

A line under the form names the amount, the category, the month and what you spent there now,
for example `Added 45,50 € to cash, 2026-10: now 65,50 € spent.` The line stays until your next
amount. If the grid below shows another month, the button `Show 2026-10` opens that month in the
grid. If the form misses a category or an amount, the same line says so in red. The category and
the month stay for the next amount. To take an amount back, press `Undo` at the top of the page
([Undo a save](index.md#undo-a-save)). It also takes back a save of the grid.

## Edit a month

The section `A whole month` holds the grid. The grid shows one month: the plan and the recorded
actual for each category. It opens on the last complete month, or on the month of a link of the
[Overview](overview.md). The buttons beside the month go to the previous and the next month. A
line above the grid counts the planned categories that have an actual. A category without an
actual is not recorded. A 0 counts as recorded.

1. Type the actual amounts. Spending is negative. A refund can be positive.
2. If you want to take over the plan, press `Take plan`. It fills the empty actual cells.
3. If you spent money in a category that the plan does not have, add a row.
4. Press `Save` at the top of the page.

`Save` saves only the month that the grid shows. Your unsaved edits stay with their month while
you look at another month. `Discard`, beside `Save`, drops the edits of the month. `Save` and
`Discard` are at the top of the page, as on the other pages with tables. The quick add keeps its
own `Add` button. On a phone, the total and `Take plan` stay at the bottom of the screen.

A category can change elsewhere while you edit it, for example on your phone. Then the page shows
both amounts and asks which one to keep: `Take the file` or `Keep yours`.
`Save` stays off until you decided.

The plan of a month comes from your current streams as they are written. It is in euros of the
simulation start, without inflation and without the events of a scenario. The phase is the phase of
the main scenario in that month. A month before its first phase change takes its first
phase.

## Actual against plan

Beside the grid on a wide screen, or below it on a phone, the page compares the last twelve
recorded months, without the current month until it ends:

- a table with the plan, the actual and the difference for each category, summed over the months in
  which the category has an actual
- a chart of the spending per month against the plan
- a chart of the difference per category. A bar to the left means that you spent more than
  planned.

A stream that you pay every few months, such as a yearly insurance, counts a part in each month.
So compare over several months.

The [Overview](overview.md#needs-attention) reminds you of the first month in which a planned
category has no actual, while you keep your actual spending: one of the last three months must have
a record.
