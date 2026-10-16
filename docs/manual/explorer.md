# Explorer

On the Explorer page you run scenarios, change the assumptions with sliders, and compare the
results. Nothing that you do with the sliders changes your files, until you save the sliders as a
new scenario.

## Select scenarios

Select one or more scenarios at the top. The list shows the name of each scenario and marks your
main scenario with `(main)`. If two scenarios have the same name, the list adds the file of each in
brackets, for example `Buy (buy)`. The results use the same names without `(main)`: the table, the
charts, the tabs and the difference of two runs. The help icon beside `Scenarios` shows the file of
each scenario and the start of its note.

`Set as default, the first as main` saves the selected scenarios. `Undo` at the top of the page
takes this save back ([Undo a save](index.md#undo-a-save)). The Explorer opens with them. The
first of them becomes your main scenario: the Overview, the Cashflows page, the Flows page and the
Spend page show it. The top of the [Scenarios](scenarios.md#main-scenario) page sets the same
choice. The help of the button names the new main scenario, or says why the button is off: no
scenario is selected, or the selection is the default already. On a phone, the first scenario that
you tap is the first one. A line below the button names it.

## The results table

Above the table, one line tells you what the app does. While it computes, the line says so, for
example `Simulating 2 scenarios, Monte Carlo, 500 paths`. The old table stays grey until the new
results arrive. If you move a slider again during this time, the app stops the wait at once and
starts the runs for the new position. When the work is done, the line starts with `Up to date`.
The app keeps the results that it computed. When you come back to them, also from another page,
they show at once without that line. A new default choice of scenarios or a change on the
Features page keeps them too. Your inputs do not allow some positions of the sliders, for example
a spending rule whose increase starts at or below the wealth where its cut starts. Then the line
starts with `Not simulated`, a message below it names the problem, and the page shows no results.
Move a slider back to see them again.

The next line names the sliders that you moved, each as `from → to`. When you moved more than three
sliders, the line shows how many, for example `16 sliders moved`. Click or tap it to see the list.
`Reset sliders` beside it moves all sliders back to the values of your files.

The table shows one row for each scenario. Each column header names its figure in plain words. Hold
the mouse over a header to read what it means. The help starts with the short term of the figure,
such as `P(broke)@90`. [How the simulation works](models.md#the-results) explains each column. When
you moved a slider, every column with a value also shows the change against the run as saved in
brackets: chances in points, money with a sign, ages in years, months of cuts and raises in months.
When one side has no value, the brackets name the value as saved, for example `(as saved: never)`.
The scenario column has room for long names. If the window is too narrow for all columns, scroll the
table sideways.

## The sidebar

- `Model`: `Monte Carlo` (the default), `Fixed` or `Historical`. See [the
  models](models.md#the-three-models). `Historical` shows only after you fetched or imported the
  MSCI World series on the [Data](data.md) page.
- `Paths`: the number of paths of a Monte Carlo run: 200, 500 (the default), 1000 or 5000. More
  paths give steadier results and take longer. `Fixed` runs one path, and `Historical` one path for
  each start month of the history, so the select is off for them.
- `Nominal euros`: shows the results in nominal euros instead of euros of the start. It does not
  start a new run.
- The slider groups, the parts of your plan first. On a computer the first group, `Total spending`,
  is open, the others are closed. `Total spending` holds `All spending`, one factor on every expense
  stream (the categories, the spending cut and the age curve apply on top). Then `Spending by
  category`, `Income` (the salary and the profit per phase, then the growth of the indices that your
  income streams follow, and `Pension growth`), `Savings plans` (the rate of each plan), `Events and
  phases` (their dates and amounts), `Assets` (the contribution of an Altersvorsorgedepot), then the
  world: `Markets` (the inflation, then the growth of an index that only costs follow, such as
  `insurance`, then the returns), `Gold and crypto` (the return, spread and correlation of the gold
  and crypto that you hold), `Spending rule`, `Care`, `Allocation`, and `Spread per year (Monte
  Carlo)`. Each slider has a help text. The help of a growth slider names the streams that follow
  that index: a stream follows it only with `index:` of that name, so a row of another phase may
  follow the consumer prices instead. An index that both income and costs follow, or that no stream
  follows, is in `Markets`. `Spending rule` holds the cut, and the increase when the reference
  wealth comes from the first month without pay (see [How the simulation
  works](models.md#spending-rules)). With VPW it holds `VPW growth`, `Spend down to age` and
  `Spending floor` instead. Then the slider of a flexible category sets its share of the VPW
  spending in a month without pay, and its level in a month with pay. A slider of VPW reaches only
  the selected scenarios with VPW, and a slider of the cut or the increase only those without it.
  `Allocation` also holds the switch `Invest the rest`: off, the cash above your buffer stays in
  cash, and only your savings plans invest. The last group, `Taxes`, holds the switch `Realize
  gains`: on, the simulation realizes the gains that fit into the tax-free room of each year (see
  [How the simulation works](models.md#realizing-gains)). The switches have no step in the
  sensitivity charts and no goal seek.
- A month slider of a phase change or of `Stop working` shows the month and your age then, for
  example `2050-03 (age 72)`.
- On a phone the sliders are in the menu, which starts closed. The button `Move the sliders` under
  the title opens it, and `Show results` in the menu closes it.
- `Reset sliders` stays at the bottom of the sidebar while you scroll the sliders.

The sliders start at the values of the first selected scenario. A moved slider applies to every
selected scenario. A salary slider of `Income` shows the gross salary and the profit of a business
per month in euros, and it changes both in each scenario by the same share. A savings plan slider
shows the rate per month in euros, for the plans of your streams and those that an event of the
first selected scenario adds. A scenario without that plan ignores its slider. While `Invest the
rest` is on, the rate changes the risk little, because the cash above the buffer goes into the
portfolio anyway. A slider that the selected model does not use is off. For example, a spread has no
effect in a `Fixed` run. The price slider of a purchase with a loan starts at the lowest price that
the loan allows, because the loan can be at most the price with the tax and the costs.

## Save the sliders as a scenario

`Save the sliders as a scenario` writes a new scenario file with the values of the moved sliders.
Select the scenario that the new file extends in `Extends`, type a `File name`, and press `Write
scenario`. The file name is also the name of the new scenario. The app refuses a file name that
exists or that another scenario has as its name. After the save, a link below the message opens the
new scenario on the [Scenarios](scenarios.md) page, where you edit it.

## Goal seek

The goal seek looks for the value of one slider at which the chance to run out of money by 90 meets
a target that you set. Type the target as on the [Overview](overview.md), with a decimal comma or a
decimal point. Instead of one slider, it can look for the factor `All spending`. Press `Find
the limit`. It runs the selected scenarios with the other sliders as they are. A bar shows how far
the search is. It first runs both ends of the range, then a few rounds of simulations that narrow
it: at 500 paths a scenario takes about 10 seconds.

In a scenario with VPW, `All spending` moves the floor of the flexible spending instead: VPW spends
a share of your wealth, so a factor on the plan hardly changes the chance to run out, but the
spending that VPW guarantees does. The answer then names `Spending floor`. Without VPW `Apply to
sliders` sets the slider `All spending`.

The answer is one sentence for each scenario, for example: `Work to 65 · All spending — up to 5.373
€ per month, now 5.201 € per month. A 5.0% chance to run out by 90 there.` When the target is met,
`Apply to sliders` beside the sentence sets the sliders to that value, for all selected scenarios.
If the value lies outside the range of a slider, the button does not show.

The lever `Stop working` finds the earliest month in which you can stop working. It moves the change
out of the last phase that pays a salary or a profit, in each scenario. The month can be from the
start of that phase, or of the plan, up to the next phase change, or up to age 70 without one. The
answer is, for example: `Mit 55 aufhören · Stop working in 2050-10 (age 55) for at most 5% chance to
run out by 90: 4.8% there, against 2050-03 (age 55) in the plan.` If even the latest month misses
the target, the answer says so and gives the chance in that month. The change needs an id, which you
set in the `Phases` tab of the [Scenarios](scenarios.md) page. A phase change that you add or change
there gets an id if it has none. Its month slider in `Events and phases` then reaches the range of
every selected scenario, so `Apply to sliders` can set it. If a scenario has no such change, its
line says why as soon as you select the lever.

`Stop working` moves only the items that have the id of the change. Events with the same id, for
example a severance or a lump sum, move with the month. Later phase changes, such as the start of
the pension, stay where they are. The dates of the streams also stay: the `start` and `end` of a
stream, and the `add_stream` and `end_streams` events with another id. So a phase counts only while
a stream pays a salary or a profit in it on those dates. A stream pays nothing in a phase where its
`factor` is 0. A stream without `phases` pays in every phase, so no phase change stops it. If each
stream that the change stops has an end date of its own, the month goes no later than that date. If
the pay ends on its own date before the change, the lever cannot move it, and the line of the
scenario says so.

A Monte Carlo run has random noise, so the last step of the answer is not exact. The goal seek
expects that the risk crosses the target once between the ends of the slider. For the rate of a
savings plan that is not sure: more equity can raise the risk as well as lower it. `Stop working`
starts at the latest month and stops at the first month that misses the target. An earlier month can
meet the target again. If the chance is the same at the earliest and at the latest month, the answer
says that the month makes no difference, also when the chance changes between them.

The target is for the chance to run out by 90, the column `Chance to run out by 90` of the table.
That figure counts every path up to age 90, so the goal seek does not use the German life table. The
column `Chance to run out, lifetime` uses it and shows another figure.

If a plan ends before age 90, the goal seek uses its last age, as the table does. When every
selected scenario ends at 80, the target reads `Target, chance to run out by 80 (%)`. When the
scenarios end at different ages, the target says 90, and its help names the scenarios at another
age. Each answer names the age of its own scenario: `A 5.0% chance to run out by 80 there.`

## Charts

The age axis of the charts also shows the calendar year below each age.

- `Comparison: median net worth and liquid by age`: the median net worth and the median liquid net
  worth of each scenario. When you moved a slider, the runs of your files show as lighter, dashed
  lines in the color of their scenario. They have no entry in the legend.
- `Comparison: chance to have run out by age`: the share of the paths that ran out of money by each
  age.
- `Difference of two runs`: with two or more runs, select A and B. At first, B is a scenario that
  extends another selected scenario, and A is that other scenario: `Buy a home` less `Work to 65`
  shows what the purchase changes. The link `Compare with … in the Explorer` on the tab `Timeline`
  of the [Scenarios](scenarios.md) page selects such a pair for you. The chart and the table show B
  less A, path by path. They show the median of the difference, and its range from the 5th to the
  95th percentile. Both runs meet the same markets on each path, so the difference shows the effect
  of the plan and not of luck. The table also shows the taxes and the share of the paths that run
  out of money in one run but not in the other.

## The tab of a scenario

Each scenario has a tab. When you moved a slider, the run as saved has a tab too, named with
`(as saved)`. A tab starts with the note of the scenario and holds:

- a fan chart of the liquid net worth by age. It shows the median and the ranges between the
  percentiles, and the median net worth as a line. Numbered markers show the events, and a list
  below the chart names them in words, for example `One-off payment: Replace the car`. The buttons
  show all values or a log scale.
- a stack of the balance sheet of the median path, split into the kinds of assets. The loans and the
  tax on unrealized gains are below zero. A kind that the plan never holds, such as gold, is not in
  the legend. A dot shows your recorded net worth of each month with records, a line only between
  months that follow each other.
- `Will the money last?`: a stack of shares by age that always adds up to 100%. The chart starts in
  the first month after your last salary or profit, when you stop work for good. A gap between two
  jobs does not count. A plan that has no pay, or whose pay runs to the end, starts at the start.
  Each path counts against its own liquid net worth in that first month (1×). Red at the bottom is
  the share of the paths that ran out of money. The greens above it, from light to deep, are the
  paths with less than 1×, 1× to 2×, 2× to 5×, and 5× or more of that value. A path with no liquid
  net worth in that first month counts as less than 1×. Gray at the top is the chance that you died
  by that age, from the German life table, and the red and the greens share the rest. The chart
  compares euros of the start, or nominal euros with the switch `Nominal euros`. A click on an entry
  of the legend hides its band. When you point to the chart (on a phone, tap it), a label shows
  every share at that age, rounded to 0.1%. So the shares in the label can add up to 99.9% or
  100.1%. The report of `dagobert run` shows the same chart in the tab of each scenario, without the
  gray with `--no-mortality`.
- the income, the spending and the taxes of each year.
- the failure anatomy: what sets the paths that run out of money by 90 apart from the others. Each
  panel sorts the paths by one random cause, such as the return of equity in the first ten years,
  into five groups. A steep panel shows a cause that decides. The panel of a gold or crypto class
  that moves with equity (`equity_correlation`) also shows a part of the slope of equity. In that
  case, a steep panel does not mean that the class itself decides. An inheritance without a month
  has a panel by your age when it comes, like the start of care: it shows whether a late inheritance
  leaves paths without money.
- two sensitivity charts, one for the parts of the plan and one for the assumptions. Each moves one
  slider one step down and up and shows the change of the chance to run out by 90 and of the median
  net worth. The color of a bar shows the effect on the value of its chart: green is better (a lower
  chance to run out, more net worth), red is worse. The fill shows the direction of the step: a
  striped bar is one step down, a solid bar is one step up. For example, more spending gives a solid
  red bar and less spending a striped green bar. The legend below the chart names the colors and the
  fills. When you point to a bar (on a phone, tap it), a label shows the value of the slider, the
  change and whether it is better or worse. A step that the inputs do not allow, such as a ceiling
  moved to the trigger, shows no change.

The sensitivity charts are in the group `What moves the result`, which starts closed, also on a
computer. They need many runs, about half a minute for each scenario at 500 paths. So the app
computes them only while the group is open, and only when you did not move a slider for 2 seconds.
While the app waits or computes, the group shows a bar. Below the bar, the charts of your last
position show in grey, with the line `For the sliders before your last move`. When the new charts
are ready, they replace the grey ones. If you move a slider during this time, the app stops and
waits for the sliders again.

## On a phone

- The scenarios are buttons. A selected one has a colored border.
- The sidebar covers the page. Its top shows the chance to run out by 90 and the net worth at 67 of
  each scenario while you move the sliders. The sliders come before the list of pages, which is at
  the bottom of the sidebar. `Show results` beside `Reset sliders` closes the sidebar.
- The table shows the scenario, the chance to run out by 90 and the net worth at 67. `All columns`
  shows the rest, and `What the columns mean` explains each column.
- In the tab of a scenario, the charts sit in groups that open with a tap: `Net worth` (open at
  first), `Will the money last?`, `Income, spending and taxes`, `Why paths run out` and `What moves
  the result`. Only an open group computes and draws its charts. A selector picks the measure of
  the sensitivity charts. Their axis marks zero and the
  end of the longest bar; tap a bar for its value. Only the open tab computes.

## In simple mode

In [simple mode](index.md#simple-and-advanced-mode-and-features), the sidebar shows fewer controls.
The simulation does not change.

- `Model`, `Paths` and `Nominal euros` show only when they are not at their defaults: `Monte Carlo`,
  500 paths and off.
- A slider shows when your files set its value, also when they set the default value. For example,
  `Equity spread` shows when `assumptions.yaml` sets it. Simple mode hides the other sliders, and
  they keep their defaults.
- The sliders of a return class show only when an asset of the first selected scenario grows with
  that class, for example `Property return` with a property. The sliders of equity and fixed income
  always show.
- A slider or a switch that you moved always shows. So simple mode never hides a change that acts on
  the results. Drag it back to its value as saved, and it hides again with the next run.

Below the last group, a note names the sliders and the groups that simple mode hides, at the values
of your files. On a phone a long note sits in a fold, `Hidden in simple mode`. A feature that is off
on the [Features](features.md) page hides its sliders in both modes, and the note names the feature.
For example, when property is off, the sidebar does not show `Loan rate after the fixed period`.

The sensitivity charts and the goal seek use only the sliders that show. On a computer, the charts
of a scenario tab sit in groups that open with a click, as on a phone. `Net worth` is open at first.
