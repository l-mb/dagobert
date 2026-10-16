# Scenarios

On the Scenarios page you create, copy, rename and delete scenarios, and you edit their general
fields, phases, events and overrides. A scenario is one file in the folder `scenarios/` of your
data directory. Each save on this page is one revision.

## Main scenario

The box at the top of the page sets which scenarios the other pages show:

- `Main scenario`: the scenario of your plan. The Overview, the Cashflows page, the Flows page and
  the Spend page show it, and the Explorer shows it first.
- `Also compare in the Explorer`: the other scenarios that the Explorer opens with, in this order.
  The list does not offer the main scenario. A template does not run, so neither list offers it.

Each scenario in the two lists shows its file name, its name and the start of its note. The full
note of the main scenario shows below its list. When you select a new main scenario, the old main
scenario moves into `Also compare in the Explorer`. Remove it there if you do not want to compare
it. Then press `Save`. The box lists the change before you save it.

On a phone the box is a section that you open with a tap. Its title names the main scenario. The
link `Change the main scenario` on the [Overview](overview.md) opens it.

`Set as default` on the [Explorer](explorer.md) saves the same choice: its first scenario becomes
the main scenario. The last save wins.

## Edit a scenario

The list `Edit scenario` below the box shows every scenario file. The tabs below it edit the
selected scenario. Each entry shows the file name and the name of the scenario. A scenario that
extends another one shows below it, with `↳`. A template shows `(template)`. A template is a
scenario that does not run. Other scenarios extend it.

On a phone the button with the pencil shows the selected scenario. Tap it to see every scenario as
a button, then tap one. A list opens the keyboard, a button does not.

The page opens with the main scenario. A link from another page opens the scenario that it names,
and often a tab. For example, an event that stops the `Roll forward` of the
[Overview](overview.md) opens the `Events` tab at the type of the event, and a phase opens the
`Phases` tab.

If the selected scenario contains an error, the page shows the file, the line and the problem above
the tabs as a warning. You can still edit, fix or delete the scenario. A save is refused only for
a problem that the save adds. A problem that a file had before does not block a save.

## An employer BU, carried forward or not

Many employers pay a disability insurance (BU) for their staff while they work for them. When you
leave the employer, you can usually continue the policy at a premium of your own, or let it lapse.
Two scenarios show what the policy is worth to you:

1. On the [Cashflows](cashflows.md) page, add the policy in the tab `disability insurance`: its
   monthly benefit, the premium 0 while the employer pays it, and the age at which the contract
   ends.
2. On the [Assumptions](assumptions.md) page, turn on `Disability` in the tab `Rules`. Each
   simulated future then draws whether and when you lose the ability to work.
3. Open the scenario in which you leave the employer. In its tab `Events`, add an event `Change a
   stream` in the month of the leave. Give it the name of the policy and your own `premium`, below
   zero (switch on `All columns` to see the column). From that month, you pay the premium.
4. Create a scenario that extends this one. In its tab `Events`, add an event `End streams` in
   the same month with the name of the policy. From that month, the policy costs nothing and pays
   nothing when you lose the ability to work later.
5. On the [Explorer](explorer.md), select both scenarios.

Both scenarios draw the same months of disability in each simulated future, so they differ only
by the policy. Read the comparison like this:

- `Chance to run out by 90` and `Chance to run out, lifetime`: the policy lowers them when its
  benefit carries you through the years without salary. The `Difference` tab shows the change on
  each path.
- `Net worth at 67`: the scenario without the policy keeps its premiums. In the futures without a
  disability it ends richer.
- `Chance of disability` is the same in both: the policy changes the money, not the risk.
- `Why paths run out` of each scenario has the panel `Disability starts at age`. Without the
  policy, the paths with an early onset run out more often.

Two rows of one name in `cashflows.yaml` do the same as the event of step 3: a row with the
premium 0 that ends in the month of the leave, and a row with your premium that starts then. The
example plan holds the pair: `Self-employed at 42` keeps the policy, `Self-employed at 42 without
the BU` lets it lapse. Its scenario `Unable to work at 51` forces the onset in every future
(`Disabled from (what-if)` in the overrides), so the Cashflows page shows the months after it.

## Create, copy, rename and delete

The buttons `New`, `Copy`, `Rename file` and `Delete` are next to the list `Edit scenario`. On a
phone they are in the menu `File`. The menu `Check a what-if` is next to them (see [Check a
what-if](#check-a-what-if)). Each button opens a window. The window lists each change before
you save it. If the app refuses the change, the window shows the reason. If the button of the
window is off, a line above it says what is missing. After the change, a short message at the
bottom of the page says what the app did. To take the change back, press `Undo` at the top of
the page ([Undo a save](index.md#undo-a-save)). An undo of a rename gives the file its old name
again.

- `New`: type a name. The new scenario extends the main scenario, so it starts with its phases,
  events and overrides. `Extends` shows each scenario with its file name and its name. Select
  another scenario there, or `none: a scenario of its own`. A scenario of its own starts in the
  first phase of the [Assumptions](assumptions.md) page. The app makes the file name from the
  name, for example `frueh-in-rente` from `Früh in Rente!`. Type a file name if you want another
  one. The list `To save` shows the phases in words, for example `Work from 2026-10`.
- `Copy`: makes a copy of the selected scenario under a new name and a new file name. The copy
  keeps the comments of the file and extends the same scenario.
- `Rename file`: gives the file a new name. Every scenario that extends it, the main scenario and
  the list `Also compare in the Explorer` change to the new file name. The name of the scenario in
  the results stays. Change it in the tab `General`. The revisions record the rename, so `Records
  against the plan` on the Overview and the comparison on the Flows page still show the days before
  it.
- `Delete`: removes the file, also from the list `Also compare in the Explorer`. If you delete the
  main scenario, the first scenario of that list becomes the main scenario. If the list is empty,
  the first scenario file that runs becomes the main scenario. The revisions keep a copy.

## Check a what-if

The menu `Check a what-if` asks five questions about your life. Each question makes a new scenario
that extends the main scenario and adds it last to the list `Also compare in the Explorer`. The
[Overview](overview.md#what-ifs) then opens and compares it with your plan. The same questions show
on the Overview as buttons while your plan has no what-if. Each window has a few fields, most with
a value already. A field that does not fit your plan shows why in red below it. The name of the
scenario comes from the question and your age, for example `Stop at 62`. Type a name if you want
another one. The list `To save` shows every change, and the window saves all of them as one
revision.

- `Stop earlier`: type the age at which you stop working. The field shows your age at the stop of
  the plan less five years. The scenario moves the change out of work of the main scenario (for
  example the change to `Retired`) to the month in which you reach that age, as the slider of the
  [Explorer](explorer.md) does. Your salary and your savings plan stop then, the statutory pension
  starts as before. The age must lie before the stop of the main scenario and after the start of
  the plan. The list `To save` shows the month and your age at the stop before and after, for
  example `Stop working 2053-06 (age 67) → 2046-06 (age 60)`.
- `Lose the job`: see [Lose the job](#lose-the-job) below.
- `Take a course`: a course of some months, six by default, then back to work. Select what the
  course follows. After `a job loss` you lose your job in the first month of the course, and ALG1
  pays during the course: a course with a Bildungsgutschein (Arbeitslosengeld bei Weiterbildung)
  uses half of the days of your claim. In `a career break` nothing pays. In the month after the
  course the scenario changes back to the phase of the main scenario, so the salary pays again.
  Type the costs of the course if you pay them yourself. They are spread over its months in whole
  cents, and the last month takes the cents that are left, so the months add up to the costs that
  you type. They count as work expenses (Werbungskosten) for the income tax. The course must end
  before you stop working.
- `Start a business`: type the month in which you start and the profit per month, before income
  tax and social insurance. The field shows your gross salary first. From that month the scenario
  changes to the phase `self-employed`: the salary and the savings plan stop, and the profit pays
  until you stop working. You pay the income tax and your health insurance yourself and no statutory pension
  insurance. The tab `Rules` of the [Assumptions](assumptions.md) page changes this
  (`tax.self_employed`). The month must lie before you stop working.
- `Buy a property`: type the month, the price, your own funds and the Land (Bundesland) where the
  property lies. The Land sets the Grunderwerbsteuer, and 5% of the price go to the notary and a
  broker. A loan pays what your own funds leave, at the refinance rate of the plan with a repayment
  of 2% a year. When you select the Land, a line shows the cost and the payment of the loan. Until
  you select it, the Land shows in red. Own funds above the price with the highest
  Grunderwerbsteuer and the costs show in red at once. The property costs 1% of its value a year
  for its upkeep. In `Rent that ends (€ a month)`, type the rent and the costs of your current home
  that the purchase ends. From the month of the purchase they come off your spending: the scenario
  lowers your living costs (`Living costs` of a quick start) by that amount with a change of a
  payment (`set_stream`). If your plan has more than one spending row, select the row that holds
  the rent in `Spending that holds the rent`. The rent cannot be more than that row. Leave the
  field empty if you do not pay a rent now.

If your plan does not have the parts that a question needs, the question adds them too: a phase on
the [Assumptions](assumptions.md) page (`unemployed`, `alt` for a career break, `self-employed`),
the payment ALG1 on the [Cashflows](cashflows.md) page, and the feature on the
[Features](features.md) page (`Job loss`, `Self-employment`, `Property`, `Deductions` for the costs
of a course).

## Lose the job

`Lose the job` makes a new scenario that extends the main scenario. In this scenario you lose your
job and get unemployment benefit (ALG1). Type the month of the job loss. If you find a new job,
type its month too. The name and the file name come from your age, for example `Job loss at 48`.
Type a name if you want another one. The month must lie from the start of the plan to before you
stop working, and the plan needs a salary.

The scenario changes to the phase of unemployment in the month of the job loss. A salary that
pays only in the phases of work stops then. In the month of the new job, the scenario changes back
to the phase that the main scenario has in that month. If the main scenario is unemployed in
that month too, the action refuses it: type a later month. If you type no new job, the phase of
unemployment lasts until the next phase change of the main scenario, for example your retirement.

If your plan does not have these parts yet, the action adds them too:

- A phase `unemployed` on the [Assumptions](assumptions.md) page.
- A payment ALG1 on the [Cashflows](cashflows.md) page, which pays in that phase. It has no
  amount: the app calculates ALG1 from the salary before the job loss.
- The feature `Job loss` on the [Features](features.md) page.

If a salary has no phases, it pays in every phase, also while you are unemployed. If no scenario
uses the phase of unemployment yet, the action limits such a salary to the other phases. The same
holds for a course and a business.

A file name can contain letters, digits, spaces, dots, underscores and dashes. It must start with a
letter or a digit. The app refuses a file name that YAML reads as a value, such as `on`, `no`,
`null` or a number, and a file name that exists with other capital letters. It also refuses a name
that Windows keeps for a device, such as `con`, `aux`, `nul` or `com1`, so that your plan works on
every system. Two scenarios cannot have the same name, because the results show a scenario by its
name.

The app refuses to delete a scenario while other scenarios extend it. The window names them. Give
them another parent first, or delete them first. The app also refuses to delete the last scenario
that runs, because every page shows one.

If a file in the list changed after the window opened, for example on another device, the app
refuses the change. Close the window and open it again to see the new list.

## The tabs

On a phone the row of tabs stays at the top of the screen while you scroll. A table that is wider
than the screen fades out at its right edge: swipe it to see the other columns.

- `Timeline`: every phase change and event that a run of the scenario sees, by month. It includes
  the items of the scenarios that it extends. The column `set in` names the scenario that holds
  each item, `this scenario` for its own items. A phase shows with its `name on the pages` of the
  [Assumptions](assumptions.md) page. The months include the moves of `shift` in the overrides. An
  inheritance without a month follows the dated items with `at death` as its month. Its detail
  names the relatives and the sum, as does the detail of a gift. A sale on a condition, such as an
  age, comes last with `on condition` as its month. If the
  scenario or a scenario between leaves out an item of a parent, the item shows with `left out
  by`. The ids of the items show when you switch on `All columns`. A button `Open the parent`
  opens each parent. The link `Compare with … in the Explorer` opens the
  [Explorer](explorer.md) with this scenario and the scenario that it extends, and their
  difference. A scenario without a parent has the link `Run it in the Explorer`.
- `General`: the name, the note, the scenario that it extends, and `Template`. A template is only
  a base for other scenarios and does not run. `Extends` offers every scenario except this one and
  the scenarios that extend it. If it is empty, it shows `none: a scenario of its own`. The tab
  names the scenarios that extend this one, because a change here changes them too.
- `Phases`: the phase changes of this file as a table, with the month, the age in that month and
  the phase. The phase shows with its `name on the pages` of the [Assumptions](assumptions.md)
  page, and you select one of those phases. The age shows the saved month: for a new or a changed
  month, the list `To save` shows the age. A row that you add or change without an id gets one
  when you save: its phase, for example `retired`. If another phase change or event of the
  scenario has that id, the year follows, for example `retired-2051`. The Explorer and the
  Overview move a phase change by its id, for example to find when you can stop working. The
  column `id` shows only in advanced mode. A scenario that runs needs a phase change in the month
  of the simulation start or before it, in its own file or in a parent. A new scenario without a
  parent starts in the first phase.

  Below the table, `Inherited phases` shows the phase changes of the parents by month. To move
  one of them, type another month in its row. The scenario then saves a move of the id of that
  change (`shift` in its overrides), and the events with the same id move with it. The parent
  does not change. To take the month of the parent again, empty the month. If two phase changes
  have the same id, they move together by the same number of months: the list `To save` names the
  new month of the other one. A change without an id does not move: change it in its own
  scenario. To leave out the phase changes and events of an id, switch
  on `Leave out` with that id. A phase change that this scenario leaves out shows with `left out
  by`.

  If you add a row with the phase of a change of a parent, for example `Retired` at 60 while the
  parent retires at 65, the app warns you: the change of the parent stays, with its events. Switch
  on `Move … instead` to move the change of the parent to your month. Then the save does not add
  your row.

  One `Save` saves the table, the moves and the switches `Leave out` together.
- `Events`: the sales, payments and other events of the file, one tab for each type, and the
  events of the parents. See [Events of a scenario](events.md).
- `Overrides`: the assumptions and the items of the parents that the scenario changes, such as
  the inflation, a salary or the month of a sale. An empty field shows the value that the scenario
  inherits. See [Overrides of a scenario](overrides.md).

In [simple mode](index.md#simple-and-advanced-mode-and-features) the tab `Overrides` shows only
for a scenario that has overrides or leaves out an item of a parent. A note below the tabs says
that it is hidden. When you save sliders as a scenario in the Explorer, the scenario has
overrides. Simple mode also hides `Template` in the tab `General`, except for a template. The tab
`Overrides` hides the same fields as the [Assumptions](assumptions.md#simple-mode) page. A field or
a tab with a value that you did not save stays when you switch to simple mode.

Each tab with fields has its own `Save` button at the top of the page. In the tab `Phases`, it
saves the table, the moves and the switches `Leave out` together. In the tab `Events`, the `Save`
of the open event type also saves the switches `Leave out` below the types. The box of the main
scenario has a `Save` of its own, because it saves another file, `app.yaml`. A list below the
fields shows each change before you save it. While nothing changed, `Save` is off, and its tooltip says
`No changes to save`. After a save, a short message `Saved` with the file name shows at the bottom
of the page.

[Configuration reference](configuration.md#datascenariosyaml) explains each field of a scenario
file.
