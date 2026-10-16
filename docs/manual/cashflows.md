# Cashflows

On the Cashflows page you edit your income and your spending, and you see them for each phase of
your life. The amounts are in euros of the simulation start. Money that comes in is above zero.
Money that goes out is below zero.

The links under the title go to the sections of the page: `Sheet`, `Bars`, `Changes` and
`Streams`. On a phone the page is long, so use them.

At the top, select the date (`As of`), the scenario, and the amounts per month or per year. The
page opens with your main scenario, which the list marks with `(main)`. The note of the scenario
shows below the scenario. Each section shows one sentence. The rest of its
help is in a collapsed box, for example `How to read the sheet`.

## The sheet

The sheet has one row for each category and one column for each phase that the scenario
reaches. A phase is a part of your life with its own income, for example a salary in `Work` and
the pension in `Retired`. You define the phases on the [Assumptions](assumptions.md) page. The
columns come in that order, each with the name that the page shows, for example `Career break` for
`alt`. A phase that the scenario never changes to has no column, as on the [Flows](flows.md) page.
The bars and the tables of changes show the same phases. The tables of the streams keep a column
for every phase: all scenarios share the streams.

On a phone the row with the names of the phases stays at the top of the screen while you scroll
through the sheet. With more than four phases, a phone held upright cannot show all columns. Then
you swipe the sheet sideways, and the column of the categories stays in view. The row with the
names of the phases then stays at the top of the sheet.

The box `What the terms mean` under the sheet explains the German terms, for example SV (social
insurance) and PKV (private health insurance). The sheet shows the plan on the selected date:

- `income` and `expenses`: the streams of your plan. A salary or a pension shows gross, the profit
  of a business before the income tax and its social insurance. A bonus with a payout ratio
  counts at the mean ratio. The unemployment benefit (ALG1) is an estimate from the last monthly
  salary before the scenario first changes to a phase with ALG1. If you change jobs before that,
  it is the salary of the new job. Without such a change, the estimate takes the salary of the
  `As of` date. A salary conversion lowers it by its part that is free of social insurance, while
  the policy runs. The estimate is net, and it pays only for the 12 to 24 months of the claim. A
  Sperrzeit (`sperrzeit`, after you quit) pays nothing for 12 weeks, which the sheet does not
  show. A course row (`training`) shows no amount: the ALG1 row beside it shows the payment.
- The rows `from the run`: what no stream pays. These rows come from a single run of the scenario
  with the mean returns. They are the health insurance subsidy, the taxes and social insurance, the
  salary conversion (the part of the gross salary that goes into a company pension), the loan
  interest and repayment, the upkeep of property and the tax on capital gains. After the loss of
  the ability to work (a scenario that forces it), they also hold the sick pay (`Krankengeld`), the
  disability pension (`EM-Rente`) where the pension stream does not pay, and the benefit of a
  disability insurance. Each is the mean over the first twelve months of the phase from the
  selected date on. A `–` means that the run does not reach that phase after this date.
- `surplus`: the sum of all rows above. It is what is left to save.
- `into savings plans`: what your savings plans paid in the same months of the run. It is a part of
  the surplus, so it is not taken off it. A month in which a plan skipped its rate shows here. The
  row shows only when a plan paid.
- `non-cash income`: the growth of your assets and what goes into a pension policy without passing
  your cash. It is not part of the surplus, because it stays invested.

The [Flows](flows.md) page shows other numbers for the same scenario. The sheet shows the plan on
one date and the first twelve months of the run in each phase. The Flows page shows the mean over
all months of a phase of the run. A link under the sheet opens the Flows page.

## Bars of one phase

The bars show the outflows by category and the income by stream for one phase. A bar has no sign,
because the title says whether money comes in or goes out. On a desktop, click a bar of the
outflows to see its streams. On a phone, tap the category above the chart. The bars of all
charts start at the same place. A long name is cut short: point at its bar, or tap it, to see
the full name.

The outflows also show what no stream pays, from a single run of the plan. These are the taxes
and social insurance, the loan interest and repayment, a salary conversion, the upkeep of
property and the tax on capital gains. The repayment of a loan leaves your cash, but it reduces
your debt. A salary conversion goes into your company pension. So both stay in your net worth,
and the line below the total says how much of it they are.

The purple income bars at the bottom are the non-cash income: the growth of your assets and the
payments of your employer into a pension policy. This money stays invested, so it is not part of
the income total.

## Scheduled changes

This table lists the dates on which a stream starts or ends, with its effect per month in each
phase. A green effect gives you more money per month, a red effect less. A stream that ends on the
date on which a new row of the same name starts is one row, for example a raise: `gross: 7.000 € →
7.300 €`. The table also lists what the events of the scenario change: the streams that a sale
ends, and the streams that an event adds or changes. A sale on a condition has no date and comes
last. A stream that an event ended changes no more, so a later change of it does not show. A
savings plan shows no effect, because its rate stays a part of the surplus.

## Changes since

This table shows how your streams changed since the start of a day, with the effect per month in
each phase. Select the day in `Day`. The list holds the days on which you saved changes to the
streams. The section shows only when such a day exists. A roll forward shows here too.

## Edit the streams

The streams are in four tabs, `expenses`, `income`, `savings` and `disability insurance`. In the
first two, each category is a block that you open with a click. The header of a block shows its
sum per month in each phase. The `savings` tab holds your savings plans in one table: the name, the
rate as `amount`, the asset that the plan buys in `into` (empty: the equity of your depot), the
months and phases, and the `index` (empty: nominal, as your broker runs the plan). The
[simulation guide](models.md#savings-plans) explains how a plan runs.

The `disability insurance` tab holds your disability insurance (BU): the monthly benefit, the
monthly premium (0 while an employer pays it, saved negative) and the age at which the contract
ends. The sheet counts the premium as an expense. The benefit pays only when a simulated future
loses the ability to work, so the sheet does not show it. An employer BU that you carry forward
or let lapse when you leave is a pair of scenarios: the
[simulation guide](models.md#a-disability-insurance-bu) shows the steps. In simple mode the tab
shows only while a row holds a BU policy. If the feature Disability is off, the tab shows in both
modes only while a row holds a BU policy.

1. Open the block of the category.
2. Change a cell, or add a row. A new row takes the category of its block.
3. Read the list of changes, and the notes under the table.
4. Press `Save` at the top of the page.

A new row starts like most rows of its block. In the income tab it takes their kind, for example
`Salary` in a block of salaries. Its phase columns take the value that most rows of that kind in
the block have. So a new salary does not pay in retirement when the other salaries do not. If a
tab has no rows yet, it shows one table without blocks, with the column `cat` for the category.
There a new income is a `Salary` and a new savings plan pays only in the phase that your scenario
starts in. A new expense pays in every phase. You can change each of these cells.

If a row cannot be saved, a note under its table says why before you press `Save`. The note names
the row and the column as the table heads it, and says what to enter. For example: "**Bonus**:
the kind Expense is money out: enter `amount` with a minus, or choose another kind". A row without
a name shows as "new row". If you press `Save` anyway, the page saves
nothing. It shows `Not saved:` with the file, the line and the problem, in English.

Some rules help you:

- A phase column holds a multiplier. 1 applies the stream in full, 0 means that the stream does
  not apply in that phase.
- An expense is saved negative, also if you type it without a minus.
- If you know that a price changes on a date, set `end` on the old row. Then add a row with the
  same name, the new amount and a `start`.
- A bonus is a salary stream with `of` and `share`. One payment is `share` of the base salary of
  `every` months. With `share` 10 and `every` 12, it pays 10% of the yearly base salary. The help
  of the columns `of` and `share` says the same. In simple mode the two columns show as soon as
  your plan has a salary.
- The column `kind` names the kind of income in words, for example `Salary` or `Self-employed
  profit`. In simple mode it offers the kinds of an employee (salary, pension, other income, an
  expense and a savings plan) and each kind that a row holds. A feature that is off hides its
  kind, for example ALG1 for the job loss. A note below the tabs names the hidden kinds. In simple
  mode the columns for experts that no row fills, for example `tags`, are behind `All columns`.
- `All columns` shows the rare fields, for example `cat` to move a stream to another category, or
  `trade tax rate (Hebesatz)` of a business. Type `410` for 410%, and leave it empty for a
  Freiberufler, who pays no trade tax. `property` names a let property: on other income the rent
  of that property, on an expense a cost of letting it, such as the Hausgeld. The income tax then
  takes the rent less its costs, the depreciation and the interest of its loan. A loss lowers the
  tax of your salary, then goes back into the two years before and forward to the next years
  ([How the simulation works](models.md#a-loss-of-a-year)).
  `deductible as` marks an expense that lowers the income tax: work expenses at a date (for example
  a course that you pay yourself), a donation, childcare, household services or a craftsman's
  labour. `deductible` is the share of it that counts, for example the labour part of a
  craftsman's bill. The expense stays in its category ([How the simulation
  works](models.md#what-lowers-the-income-tax)).
  Your edits that are not saved yet stay when you turn it on or off.
- The scenarios and a bonus name a stream by its name, so you cannot change the name of a
  saved stream in the table. To change it, press `Rename` above the table. The dialog lists each
  line that changes, on every row of the stream and in every scenario. The new name must be new.

The [configuration reference](configuration.md#datacashflowsyaml) describes every field of a
stream.
