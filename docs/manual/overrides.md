# Overrides of a scenario

The tab `Overrides` of the Scenarios page shows what the chosen scenario file changes. An override
is a value that applies in this scenario only. It changes an assumption, such as the inflation, or
an item that the scenario takes from the scenarios that it extends, such as the month of a sale.
The scenarios that extend this one take its overrides too. The
[configuration reference](configuration.md#datascenariosyaml) describes the key `overrides`.

If the scenario changes `start`, the month of the simulation start, a line above the sections
shows it. The tab does not edit it.

The tab has one section for each part. A number after the name of a section shows how many values
the file sets there: `Markets (2)`. A section that holds values opens when the tab opens.

In [simple mode](index.md#simple-and-advanced-mode-and-features) the sections hide the same
fields as the [Assumptions](assumptions.md#simple-mode) page, and the Scenarios page shows this
tab only for a scenario that has overrides or leaves out an item of a parent. A value that a
scenario sets always shows, also when it is equal to the default.

## Inherited values

An empty field takes the value that the scenario inherits. The field shows that value in gray,
with its source: `2 (default)`, `3 from assumptions.yaml` or `5 from base`. The source `base` is a
scenario that this one extends.

A value that you type stays in the file, also when it is equal to the inherited value. If the
parent changes later, this scenario keeps your value. To take the inherited value again, empty the
field and save.

## The sections

- `Person`, `Markets`, `Rules` and `Tax`: the fields of the [Assumptions](assumptions.md) page.
  Type shares and rates in percent: `2.5` for 2.5%. A table, such as the returns, has a switch
  `Override`. If the switch is off, the table of the parent shows below it. If it is on, the rows
  that you add apply in this scenario. A row of the parent stays.
- `Scale`: factors on the plan. `Spending by category` multiplies the expense streams of a
  category, in percent as on the slider of the Explorer: `90` spends 10% less. `Savings plans`
  multiplies the rate of a savings plan in the same way: `150` saves half as much again.
  `Salary and profit in Work €` shows the salary and the profit of a business of a usual month in
  euros of the start, as the slider of the [Explorer](explorer.md) shows it. The file keeps a
  factor on every salary payment and profit of the phase, so a bonus changes by the same share. A
  phase that pays neither in the plan shows the factor, `Salary and profit in Work`.
- `Dates`: moves the phases and events with an id by months. Below the table, each moved group
  shows its month before and after: `job-loss 2039-06 → 2039-09`. When you type a month into a
  phase change of a parent in the tab `Phases`, the app writes the same move here.
- `Event fields`: sets a field of the events with an id, for example the `price` of a sale.
- `Assets`: sets a field of an asset of `assets.yaml`, for example the `contribution` of an
  Altersvorsorgedepot.

In the last three tables, select the id first and then the field. Type the value in the unit of
the field: euros as `1.234,56`, a share or a rate in percent, a month as `2027-05`, a date as
`2027-05-14`, and `true` or `false`. If you empty a value or delete a row, the item takes its own
value again. The [Events](events.md) tab explains the id of an event.

## Save

1. Change the fields and the tables of one or more sections.
2. Read the list of changes below the sections.
3. Press `Save` at the top of the page.

One `Save` writes all sections as one revision. Before you save, the app loads the scenario and
the scenarios that extend it with your changes. If one of them does not load, a message above the
sections names the problem, and `Save` stays off. This happens, for example, for a field that no
event of the id has. A section that keeps `Save` off is named above the sections too.

If the file changed after the tab opened, for example on another device, `Save` stays off. Press
`Discard my edits` to see the file as it is now. To take a save back, press `Undo` at the top of the
page ([Undo a save](index.md#undo-a-save)).
