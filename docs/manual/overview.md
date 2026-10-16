# Overview

The Overview is the first page of the app. It shows where you stand today, how your plan looks, and
what needs your attention. It shows no details: the [Cashflows](cashflows.md) page shows where the
money goes, and the [Assets](assets.md) page shows each asset. The sections come in this order.

## Tiles

Four tiles show your net worth, the liquid and the illiquid part, and your debt. They use the values
that you recorded on the [Snapshot](snapshot.md) page and the values in `assets.yaml`. Each tile
shows the change since the end of the previous month. If the value did not change, the tile says `no
change since` that day in gray. A new plan has no value from before the current month, so the
tiles show no change yet.

## Outlook

The heading `Main scenario:` names your main scenario, and its note follows below it. The link
`Change the main scenario` opens the [Scenarios](scenarios.md#main-scenario) page, where you select
another one. The tiles show the outlook of the main scenario. They come from 500 simulated futures
of the markets and the prices (a Monte Carlo run) on your files, without the sliders of the
Explorer. The amounts are in euros of the start. A line above the tiles says what the plan assumes:
the month and your age when the main scenario stops working. The help icon of each tile gives the
short name of the figure in the report and the Explorer. [How the simulation
works](models.md#the-results) explains each figure:

- `Chance to run out, lifetime` (`P(broke) alive`): the probability that your money runs out while
  you are alive. It can be lower than the figure by 90: it counts a path only with the chance that
  you are alive in the month the money runs out.
- `Chance to run out by 90` (`P(broke)@90`): the share of the futures in which the money ran out by
  age 90.
- `Net worth at 67` (`Total@67`): the median net worth at age 67.
- `Typical shortfall` (`Shortfall`): how far the money falls below zero in the lives that run out.
- `Stop working`: the month that `Find when to stop working` found, with your age in that month.
  Until you press the button, the tile shows a dash and `not searched yet`. A plan that you start
  on the page [Start a plan](start-a-plan.md) searches once by itself when the Overview opens. If
  even the latest month
  misses the target, the tile shows `not even at` and your age in that month. In other cases without
  a month, the tile shows a dash, and the answer below the buttons says why. The tile keeps the
  month until you change an input or the target.

`Find the spending limit` answers the question: by how much can all spending change, so that the
chance to run out by 90 stays at the target? Set the target in the field `Target, chance to run out
by 90 (%)` beside the button (5% by default). Type a number from 0.5 to 50, with a decimal comma
or a decimal point, for example `4.5` or `4,5`. If the field holds something else, a message says
what to type, and the buttons stay off. The answer shows below the button. The answer is in
words, for example: `Spend at most 2.054 € a month, 14% less than now`. It is one change for all
spending categories. The health insurance premium does not change with it. If the target is not met,
a link opens the [Explorer](explorer.md), where you can try less spending or more savings. The
answer can be a little off, because a Monte Carlo run has random noise.

`Find when to stop working` answers the question: how early can you stop working, so that the chance
to run out by 90 stays at the same target? It moves one phase change: the change out of the last
phase that pays a salary or a profit, for example the change to `Retired`. It finds the earliest
month that meets the target. The answer is one sentence, for example: `Stop working in 2050-10 (age
55) for at most 5% chance to run out by 90: 4.8% there, against 2050-03 (age 55) in the plan.` The
month can be from the start of that phase, or of the plan, up to the next phase change. Without a
next change, it can be up to age 70. If even the latest month misses the target, the answer says so
and gives the chance in that month. The change needs an id, which you set in the `Phases` tab of the
[Scenarios](scenarios.md) page. A phase change that you add or change there gets an id if it has
none, for example `retired`. If the scenario has no such change, the answer tells you why.

If the main scenario spends by VPW (see [How the simulation
works](models.md#variable-percentage-withdrawal-vpw)), the spending follows the wealth. The two
tiles of the chance to run out then give the chance that your fixed spending and the floor of the
flexible spending use up your wealth, and their help says so. `Find the spending limit` then looks
for the highest floor of the flexible spending that meets the target, in euros per month: the
spending that VPW guarantees in each month without pay. With a floor of 0 €, VPW rarely runs out, so
`Find when to stop working` needs a floor to answer a question: when your wealth carries the fixed
spending and that floor.

Each search shows a bar that moves after each round. The search first runs both ends of the range,
then a few rounds of simulations that narrow it: at 500 paths it takes about 10 seconds.

The search moves only the items that have the id of the change. Events with the same id, for example
a severance, move with the month. Later phase changes, such as the start of the pension, stay where
they are, and so do the start and end dates of the streams. So a phase counts only while a stream
pays a salary or a profit in it on those dates. If the pay ends on such a date, the month goes no
later than that date. The search starts at the latest month and stops at the first month that misses
the target. An earlier month can meet the target again. The goal seek of the [Explorer](explorer.md)
explains the details.

Both searches aim at the chance to run out by 90, the figure of the tile `Chance to run out by 90`.
That figure counts every future up to age 90, so the searches do not use the German life table. The
tile `Chance to run out, lifetime` uses it and shows another figure. If your plan ends before age
90, the tile, the target and the answers use the last age of the plan instead, for example `Target,
chance to run out by 80 (%)`.

## What-ifs

A what-if is a question about your life: what if I stop working earlier, lose my job, take a
course, start a business or buy a property? Each question makes a scenario that extends your main
scenario. The section `What-ifs` below the outlook compares these scenarios with your plan.

If your plan has no what-if yet, the section shows the five questions as buttons. A plan from the
[quick start](start-a-plan.md) shows them first. A button opens a small window with a few fields.
Most fields have a value already, so you can often press `Add and compare` at once. The window lists
what it saves before you save it, and a field that does not fit your plan shows why in red below
it. [Check a what-if](scenarios.md#check-a-what-if) on the Scenarios page explains each question.

After the save the Overview opens again. The section shows one row for each scenario of the list
`Also compare in the Explorer` (see [Main scenario](scenarios.md#main-scenario)): its name, its
`Chance to run out by 90` and its `Net worth at 67`, the same figures as the tiles above. In
brackets is the change against your main scenario: `67% (+41.2 pt)` means 41.2 percentage points
more than the plan. The link `Compare` opens the [Explorer](explorer.md) with the scenario and the
main scenario, with the difference path by path. Below the rows, the menu `Check a what-if` holds
the five questions again.

The rows come from the same simulation as the Explorer, so `Compare` shows at once. After you change
an input, the section simulates every row again: a bar shows the progress. A scenario that does not
load or run shows `does not run`, and the link `Open` shows it on the Scenarios page. On a phone a
row shows the name above the two figures.

## Needs attention

The table lists what you must update or know about:

- An asset value that is older than its update interval, or a value without a date. The interval is
  twelve months. You can set another interval for an asset in its column `check every (months)` on
  the [Assets](assets.md) page. A term deposit and a property never become old. Its contract gives
  the value of a term deposit, and the price of a property is an estimate that you change rarely.
  But a property that the main scenario sells on a date becomes old after six months, so that you
  follow its price while the sale comes closer.
- A change of the plan in the next three months, such as a salary raise, with its effect per month.
  A purchase of a property shows its price, its cost with the tax and the costs, and what your cash
  and your liquid assets pay.
- A term deposit or a fixed loan rate that ends within twelve months, or that ended already.
- A month in which you recorded no actual spending for a planned category, while you keep your
  actual spending on the Spend page: the table names it only when one of the last three months has a
  record. If you do not record your spending, or you stopped, the table does not remind you.
- A simulation start before the current month, with how far it lags.
- A plan that draws a disability without a pension stream from points: the disability pension needs
  one, so the plan pays none. The link opens the [Cashflows](cashflows.md) page.
- A disability on a fixed date that pays no disability pension, because the insurance time or the
  contributions before it are too short. The row has the date of the disability. The link opens the
  place where the date is written: the [Assumptions](assumptions.md) page or the `Overrides` tab of
  the scenario on the [Scenarios](scenarios.md) page.
- A savings plan that pauses in the main scenario, because the cash in a month does not cover its
  rate. The row has the first such month, also years ahead. The simulation of your files with the
  mean returns finds it. Lower the savings plan or the spending on the [Cashflows](cashflows.md)
  page, which the link opens.

A red date needs an update of your inputs. The link on the right of a row opens the place where you
change it:

- An asset value without a date, or an old one: the [Assets](assets.md) page. It opens the tab of
  the asset with its row first, and marks the columns to check, the value and `as of`, with `⚠`.
- A term deposit or a fixed loan rate: the same, with the maturity date, or the rate and the end of
  the fixed rate, marked.
- A change of a stream: the [Cashflows](cashflows.md) page.
- A change that an event makes, and a purchase of a property: the [Scenarios](scenarios.md) page. It
  opens the file that holds the event, in the `Events` tab at the type of the event.
- A month without actual spending: the [Spend](spend.md) page, on that month.

For a simulation start that lags, use the `Roll forward` below the table. On a phone, each row is a
small card: the item in bold, the date and what to do below it, and the link on the right.

In simple mode, and when the feature Records is off, the table lists no old values and no values
without a date until your plan holds a record of a value or a trade. The fold `What the table lists`
then leaves them out too.

## Roll forward

The section `Roll forward` shows when the simulation start lies before the current month. A roll
forward moves the start to a later month, so that the plan starts today again. To roll forward:

1. Open `Roll forward` and select the new start month.
2. Read the list of events before the new month. The roll does not run while such an event remains,
   because only you know what happened to it. A gift is not in this list: see step 5. Remove the
   event in its scenario file, or move it to a later date. The file name is a link: it opens the
   file on the [Scenarios](scenarios.md) page, in the `Events` tab at the type of the event.
3. Read the warnings. A phase that ends before the new month, and a loan without a date for its
   balance, need your attention. The file of a phase links to its `Phases` tab. Each loan links to
   its row on the Assets page, where you type its balance and the date of the balance.
4. Read the price factor and the list of amounts that it changes. The amounts of your plan are in
   euros of the start. So the roll multiplies each amount that follows the consumer prices by the
   rise of the prices between the two months. The pension and its point value are such amounts too,
   and so is an amount that a scenario sets for an event of the scenario that it extends, the
   reference wealth of the spending rule when you set it, the floor of VPW and the cash of an
   inheritance without a month.
5. Read the lists of dates that the roll writes. A stream that pays every few months and has no
   `start` gets the old start as its `start`, so it pays in the same months as before. A business
   that runs before the new month gets its first month as `founded`. This month starts the years in
   which the regular pension contribution of a business is half (see
   [configuration](configuration.md), `tax.self_employed`). Losses that the plan carries to the new
   month for the income tax, for example of a let flat, go into `loss_carryforward`, so the years
   after the new start still get them. Scenarios that share one `loss_carryforward` get the smallest
   of their losses, so no scenario starts with losses that it did not have. The losses of capital
   income go into `capital_losses` the same way. The roll does not change them by the consumer
   prices, because the law keeps them in nominal euros. A gift before the new
   month moves from its scenario into the gifts before the start of its relative, with the tax that
   the roll computes for it. So the tax of a later gift or inheritance still adds it (see
   [Assumptions](assumptions.md#relatives)). The roll takes the month of the gift as its scenario
   file writes it. It stops with a message when a scenario moves the gift to the other side of the
   new month (`shift` or `events` in its overrides), or when an override or `drop` names the gift by
   its id. Change that scenario first. The roll takes the securities of the gift at the value that
   you typed, in euros of the old start. It does not add the change of the share prices up to the
   month of the gift. If the securities were worth more or less in that month, correct the value and
   the tax of the gift on the [Assumptions](assumptions.md#relatives) page. The comment lines above
   the gift stay in the scenario file. Remove them if they no longer fit.
6. Press the button to roll forward.

The roll is one revision. The `Changes since` section of the [Cashflows](cashflows.md) page shows
what it changed. It does not change the values of your assets: record them on the
[Snapshot](snapshot.md) page, or on the [Assets](assets.md) page while the navigation leaves out the
Snapshot page. If the consumer prices of the new month are not known yet, the roll uses the
inflation of your assumptions. The link `Data: fetch newer consumer prices` opens the
[Data](data.md) page, which can fetch newer months. In simple mode the link shows only when your
plan holds a fetched or imported series.

## Last save

Below the roll forward, a line names the last save of your data directory, for example `Last save
at 14:03 on Cashflows.`. This save can come from another device, from a command or from an edit of
a file by hand. The button `Undo` takes it back, as described in [Undo a save](index.md#undo-a-save).
The line does not show when the last save is your own: the line at the top of the page offers its
undo. It does not show either for the first revision of the folder or for a migration to a new
version of the app, because they have nothing to take back.

## Assets

On a desktop, this section and `Recorded net worth` stand side by side, and the two charts have the
same height. On a phone, they stand one below the other. Until a second month has records, `Recorded
net worth` has no chart, so it stands below this section on every device.

The ring chart shows your assets before debt: the middle shows their sum. A line below the chart
takes off the loans and gives your net worth. The inner ring splits them into liquid and illiquid.
The next rings split them into kinds and into single assets. The outer ring shows the securities of
a depot at their last prices. Loans show only in the debt tile. On a phone, the chart shows two
rings, and a tap on a ring opens it. If you have no asset yet, for example in an empty plan, a note
names the Assets page instead.

A line below the chart compares your fixed-income share with the target of your allocation for your
age. The share is fixed income divided by fixed income plus equity. The value of each kind of asset
shows in the second ring, and the [Assets](assets.md) page has a tab for each kind.

## Recorded net worth

Once a second month has records, a chart shows your recorded net worth at the end of each month with
a record. You do not need to record every month: a month without a record has no bar. An asset
without a record in a month counts with its last value. The bars show the liquid and the illiquid
assets above zero and the debt below zero. A dot shows the net worth: the assets less the debt. A
line joins only the dots of months that follow each other, so two records a year apart show no line
between them.

Until a second month has records, a line says that the plan needs no records: you can explore your
plan on the [Explorer](explorer.md) page, and the Snapshot and Spend pages keep records only when
you want them. The line names only the pages that the navigation shows. The link `Explore scenarios`
opens the Explorer.

In simple mode, and when the feature Records is off, this section and `Records against the plan`
show only when your plan holds a record. Before that, only the line to the Explorer shows.

If the [Features](features.md) page switched off parts of life that your plan does not use, a line
below gives their number, with a link to the Features page. That page names them. Turn a part on
there when you need it.

## Records against the plan

This chart compares your records with the plan as you made it on an earlier day. The band shows the
median and the range from the 5th to the 95th percentile of the paths of that plan. A dot shows each
month with records, and a line joins the dots of months that follow each other. Above the chart, a
sentence says how many paths lie below your last record. The chart needs a second month with
records.

- `Compare with plan saved on`: the plan as it was at the end of that day. The list holds each day
  on which the plan changed, from the first start of the app on. At first it shows the plan from the
  start of your records. If this version of the app cannot load or run the plan of a day, a message
  says so, and the reason when it has one. Then choose a newer day.
- `Measure`: the net worth or the liquid part.

The chart uses nominal euros, because your records are nominal too.

If a pension policy or an Altersvorsorgedepot has a date for its value, a line below the chart
explains a difference. The plan carries the value forward from that date with the returns and the
payments. Your records keep the value that you typed. `Take estimates` on the
[Snapshot](snapshot.md) page fills in the carried value, and `Record` saves it.

## Where the money goes

The link `Cashflows: where the money goes` at the end of the page opens the
[Cashflows](cashflows.md) page. Its bars show the outflows and the income of one phase.
