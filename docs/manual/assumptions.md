# Assumptions

On the Assumptions page you edit `assumptions.yaml`: the facts about you and the assumptions that
every scenario starts from. A scenario can change them in its own overrides. The
[Explorer](explorer.md) moves many of the numbers with sliders, but it does not save them here.

The page has four tabs:

- `Person`: your date of birth, your sex for the life table, the age at which the simulation ends
  (`Plan up to age`), your number of children, the first month of your contributions to the
  statutory pension insurance, the Rentenversicherung (`Pension insurance since`), the health
  insurance of pensioners (`Health insurance of pensioners (KVdR)`), and a row for each child
  (`Children by date of birth`). The KVdR applies only in the statutory health insurance. Switch it
  off if your pension will not make you a compulsory member: you then pay on all income, as a
  voluntary member. A row of a child holds its date of birth and four columns: `counts as a child
  until` (empty: up to the 18th birthday, else the month after the end of an education, at most the
  25th birthday), `Kindergeld paid to you`, `child allowance` (`half`, or `full` when the other
  parent pays no support) and `child-raising years credited to your pension`. While a child counts,
  the simulation pays its Kindergeld, the tax takes the child allowances where they save more, and
  ALG1 pays 67%. In the statutory health insurance (GKV), the care insurance (Pflegeversicherung)
  costs less for the second to the fifth child under 25. [How the simulation
  works](models.md#children) explains the rules. Then the relatives from whom you may inherit
  (`Relatives you may inherit from`) and the phases of your life (`Phases of life`), see below.
- `Markets`: the inflation, the return of each asset class (`Returns by asset class`), the growth
  indices that streams can follow, the interest rate of a loan after its fixed period, and the
  yearly growth of the pension on top of the consumer prices (`Pension growth per year`). The
  pension follows the consumer prices of each path, so 0 keeps its buying power. `average` is the
  mean per year, `volatility` the standard deviation of the yearly draw.
- `Rules`: the cash buffer, `Invest the rest` (off: the cash above the buffer stays in cash, and
  only your savings plans invest), the random seed, the allocation between equity and fixed income,
  the spending rule, the long-term care and the disability (the loss of the ability to work). The
  seed sets the random draws of the care episodes, of the disability and of the sale prices.
- `Tax`: the tax year, the capital income free of tax (the Sparer-Pauschbetrag), the share of the
  gains of an equity fund that is free of tax (the Teilfreistellung, `Fund gains tax-free`, the
  default of each depot without its own on the [Assets](assets.md) page), your work expenses of a
  year (the Werbungskosten, `Work expenses per year €`, as your tax notice lists them: they count
  when they are higher than the 1,230 € that the tax takes anyway), the switch `Realize gains each
  December within the tax-free room` (see [How the simulation works](models.md#realizing-gains)),
  private health insurance (PKV), the Zusatzbeitrag of your Krankenkasse in the statutory health
  insurance (empty: the average of the year), the church tax (`Church tax`) with the Land where you
  live (`Bundesland`), and the first month in which a purchase of crypto counts as capital income
  (`Crypto taxed like shares from`), and the losses of earlier years that your last tax notice
  carries forward (`Losses carried forward €`, the Verlustvortrag). Switch on `Single parent
  (Entlastungsbetrag)` when you raise your children with no other adult in the household. The select
  `Bundesland` shows the name of the Land, and the file keeps its code, such as `BY`. If no tax year
  is selected, the plan takes the newest tax year up to the year of the simulation start. The page
  marks that year, for example `2026 from start`. Below them, `Self-employment` holds the social
  insurance in a month with a business of your own and without a salary:
  - `Pension insurance of a business`: `None` (no compulsory contribution), `Fixed contribution
    (Regelbeitrag)` (the same amount each month, half of it in the first years after the founding)
    or `By profit` (a share of the profit).
  - `Sick pay in the GKV`: sick pay of the statutory health insurance, for a higher rate. It is off
    while `Private health insurance (PKV)` is on: then the field shows `statutory insurance only`.
  - `Business founded`: the month of the founding. It counts only with a fixed contribution: else
    the field shows `fixed contribution only`.

  The [configuration reference](configuration.md) explains the choices.

The help icon of each field explains it, names its default, and names the German term where one
exists. The [configuration reference](configuration.md) explains each value.

## Simple mode

In [simple mode](index.md#simple-and-advanced-mode-and-features) the page hides the fields for
experts that your plan does not use, for example the random seed or the tax year. A field shows when
your file sets it to a value other than its default, or when a scenario sets it. A section that your
plan uses shows with all of its fields, for example all fields of `Long-term care`. A tab without a
field to show is not there: a new plan has no tab `Rules`. A note at the end of each tab names the
fields that it hides, and a note below the tabs names the fields of a hidden tab.

A feature that is off on the [Features](features.md) page hides its fields in both modes, for
example `Single parent (Entlastungsbetrag)` when `Children` is off.

The table of returns shows the column `correlation with equity` only when a class has a value there.
To see it, turn on `All columns` below the table.

A hidden field keeps its value: a save of a tab changes only the fields that you edited. If you type
a value and then switch to simple mode, the field stays on the page until you save or discard it.

## Edit and save

1. Open the tab of the value.
2. Type the new value. Type shares and rates in percent: type `2.5` for 2.5%. Type amounts in euros
   with a decimal comma or a decimal point. Type a month as `2027-05` or `05.2027`, and a date as
   `1986-05-20` or `20.05.1986`.
3. Read the list of changes below the tab.
4. Press `Save` at the top of the page. A short message `Saved assumptions.yaml` shows at the bottom
   of the page. While nothing changed, `Save` is off.

Each tab has its own `Save`. A save writes the changes of its tab only. The other tabs keep the
values that you typed, until you save them too. Each save is one revision, for example `Assumptions:
Markets`.

An empty field takes the value that it shows in gray: the default of the app. To go back to the
default, empty the field. If a value does not read, or the values do not fit together, for example a
table of returns without `equity`, a warning above the fields names the problem. Then `Save` stays
off until you correct it.

## Lists and tables

Returns and indices are tables with a row per name: the column `asset class` or `index` holds the
name. To add a return class for an asset, type its name and its average into the empty row at the
end. The classes `equity`, `fixed_income`, `cash` and `property` must stay.

The glide path of the allocation, the age curve of the spending and the yearly chances of care and
of a disability are tables with a row per age. Each age can be in a table one time only.

## Phases of life

A phase is a period of your life, such as work, part time, a sabbatical or retirement. A scenario
switches between your phases on dates. A stream pays in the phases that its row names, and the
company pension (bAV) gets the contributions of the employer in its own phases. The simulation reads
no name. A phase means what its streams pay.

The table `Phases of life` has a row per phase:

- `name on the pages` is the name on the pages that show the plan: Cashflows, Overview, Flows,
  Spend, the charts and the timeline of a scenario. It can have capitals and umlauts, for example
  `Teilzeit`. If you empty it, the pages show the short name.
- `short name in the files` shows when you turn on `All columns`. The data files use it. It has
  small letters, digits, `-` and `_`, and it starts with a letter, for example `part-time`. The
  tables that edit a stream, a policy or a scenario select a phase by its short name.

To add a phase, type its name on the pages into the empty row at the end. On a phone, `+` above the
table adds that row too. The app makes the short name from it: `Elternzeit für Kind` becomes
`elternzeit-fuer-kind`. To choose the short name yourself, turn on `All columns` and type it.

The order of the rows is the order of the columns on the Cashflows page and of the colors of the
phases in the charts. A new phase comes last. A new plan has four phases: `Work`, `Unemployed`,
`Career break` and `Retired`. Their short names are `work`, `unemployed`, `alt` and `retired`.

To compare a job change or part time, add a phase, for example `part-time`. Then give your salary a
factor of 0.5 in that phase on the Cashflows page, and switch to it in a scenario on the Scenarios
page. The example does this for a new job after a job loss: the scenario `Job loss at 53` switches
to the phase `new-job`. The new salary pays only in that phase. The company pension of the old
employer gets its contributions in `work` only, so it gets nothing in `new-job`.

If a stream, a policy or a scenario uses a phase, you cannot change its short name in the table. A
warning names the first uses, and `Save` stays off until the name is back. To change the short name,
press `Rename` below the table. The dialog lists each line that changes in each file, and writes
them as one change. You can change the name on the pages at any time. A scenario cannot add or
rename phases. It only switches between the phases of this table.

On a phone, `Columns` above a table explains its columns.

## Relatives

The table `Relatives you may inherit from` has a row per relative: a parent, a grandparent, a
sibling, an aunt or uncle, a parent-in-law or another person, never your spouse. The inheritances
and gifts of a scenario name a relative by its short name. The table works like the table of the
phases:

- `name on the pages` is the name on the pages, for example `Mutter`.
- `short name in the files` shows with `All columns`. The app makes it from the name on the pages.
- `date of birth` and `sex` draw the month of death from the life table for an inheritance without a
  month.
- `relation` sets the tax class and the tax-free amount of the Erbschaftsteuer. A step-parent counts
  as a parent.

If an event uses a relative, you cannot remove the row or change its short name. A warning names the
first uses, and `Save` stays off. To change the short name, press `Rename a relative` below the
tables.

Below the tables, `Gifts received before the start` lists the gifts of one relative before the
simulation start. Select the relative, then type the month (`2022-05`), the value and the tax that
you paid, all in nominal euros. Press `Save gifts`. The tax on a later inheritance or gift of the
same relative adds the gifts of ten years. The roll forward moves a gift of a scenario into this
table once its month passed. To add a gift for a new relative, save the relative first.

## Optional parts

The allocation, the spending rule, the care and the disability are optional. The switch `Use` turns
each one on or off. When the switch is off, the simulation does not use that part. For the
allocation, all surplus then goes into equity.

`Disability` adds the risk that you can no longer work, a full Erwerbsminderung. `Yearly chance of a
disability by age` starts with the default curve of the pension insurance: about 4.5 in 1,000 a year
on average, rising with age. `Disabled from (what-if)` forces the month in every simulated future,
also in the run with the mean values. A scenario can set it in its overrides to show the months
after it on the Cashflows page. The [simulation guide](models.md#when-you-cannot-work) explains the
sick pay, the disability pension and a disability insurance.

The spending rule compares your liquid wealth with a reference wealth: below the cut threshold it
cuts your flexible categories, above the increase threshold it raises them. `Reference wealth from`
sets that wealth. `The start, always` takes the liquid wealth at the start, and the rule acts in
every month. `The first month without pay` takes the liquid wealth when your salary and your profit
stop, and the rule acts only while you have no pay. The two increase fields are off until you choose
`The first month without pay`. While you work, your wealth soon passes the wealth of the start, and
the increase would raise your spending while you save. `Reference wealth at the start €` fixes the
reference of the start. Leave it empty to take the liquid wealth of the start. [How the simulation
works](models.md#spending-rules) explains the rule.

`Variable percentage withdrawal (VPW)` is a spending rule of its own. Its switch `Use` is off until
you choose `The first month without pay`. Set `Cut below this share of the reference wealth %` and
`Increase in a good time %` to 0 first: VPW replaces both. Each year VPW takes a share of your
liquid wealth as the budget, and the share rises with your age. `Growth trend, real % per year` sets
that share: 3.7% suits 60% stocks and 40% bonds, 3.4% suits 50/50. `Spend down to age` is the age by
which the rates would use up the wealth. `Floor of the flexible spending € per month` is the least
that your `Flexible categories` spend in a month without pay. [How the simulation
works](models.md#variable-percentage-withdrawal-vpw) explains VPW.

The age curve of the spending applies to every category except the health premium, while `Every
category except the health premium` is on. It never applies to a cost of a let property, such as its
Hausgeld. If you turn it off, select the categories. If you select no category, the age curve
applies to none.

## The simulation start

The simulation start (`Start month (read only)`) is read only. Every amount of your plan is in euros
of this month. The `Roll forward` on the [Overview](overview.md) moves the start after the month
passed. It also changes your amounts by the consumer prices between the two months, so that they
keep their meaning. While the start lies before the current month, the link `Roll forward on the
Overview` opens that page with the roll forward open.

## What is not on this page

The scale factors on the salary and the spending (`scale`) belong to a scenario. The Explorer saves
them as overrides of a new scenario.
