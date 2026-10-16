# Configuration reference

The pydantic models in `src/dagobert/model/` are the authority. Unknown keys are rejected. Money is
in EUR, expenses are negative, one step is one month. Dates are `YYYY-MM-DD`. A field that holds
a month (such as the simulation `start`, the `start` and `end` of a stream, or the `at` of an
event) takes any day and reads it as the first of its month. A field that holds a day (such as
`born`, `asof`, the dates of a term deposit or the `date` of a trade) keeps the day. Shares,
rates and probabilities are fractions (0.025 is 2.5%), and a factor multiplies (1 leaves an
amount as it is). Every `stdev` is at least 0. The app shows shares and rates in percent and
takes them so: type 2.5 for 2.5%, and the file gets 0.025.

`src/dagobert/examples/engineer/` is a complete data directory of a made-up person that uses most
features below. The first start of the app offers it, and `dagobert init --example` copies it.
`src/dagobert/examples/starter/` is a small one in German of an employee who wants to stop working
early (`dagobert init --example starter`).

## `data/manifest.yaml`

Written by the app, never by hand, with one exception below: `schema` (the version of the data
format, one more per migration step) and `app` (the version of Dagobert that set it). An export, and
a directory unpacked from one, also holds `base`: the revision of the data directory that the export
came from. A folder that you write by hand needs no manifest: with no manifest and no `revisions/`
log at all, Dagobert takes it as the current format and writes the manifest at its first open. Any
history means that Dagobert touched the folder, so its files count as schema 1 and migrate. For a
folder of an older Dagobert without a manifest, add a `manifest.yaml` with the line `schema: 1`:
this is the one manifest you write by hand. Only that first open and a migration write the manifest
of a data directory. An export writes a copy into its zip.

## `data/revisions/`

Written by the app, never by hand. Each save of the app, each command that writes and each
migration is one revision: a folder named after the UTC time of the save, with a copy of each
input file that it changed, and a line in `log.csv` (`time,files,removed,source`). The source is
the page, such as `Snapshot`, or the command. An `Undo` of the app is a revision too, with the
source `<page>: undo`: it writes the files of a save as they were before it, so the log keeps both
([Undo a save](index.md#undo-a-save)). The first open records every input as `baseline`.
A file that you edit by hand is recorded as `outside the app` at the next open or save. The data
directory must be on a local file system, because the lock of a save does not work on every
network file system. In a read-only data directory the app runs, but it refuses every save, and a
directory that needs a migration does not open. Windows does not tell the app in advance that a
folder is read-only: there each command stops with `[Errno 13] Permission denied` and each page
with a `PermissionError` ([Install Dagobert on Windows](../install/windows.md)).

The app compares with the inputs of an earlier day from these copies: `Records against the plan`
on the Overview, `Changes since` on the Cashflows page and the comparison on the Flows page. A day
is a day in the time zone of the browser. The last two need a revision before the chosen day, so
they show nothing while the folder holds only the baseline.

## `data/assumptions.yaml`

The [Assumptions](assumptions.md) page edits every key but `start` (the roll forward of the
Overview moves it) and `scale` (the overrides of a scenario).

- `person`: `born` (required, a date: a birthday after the first of the month counts in the month
  after), `sex` (`m` or `f`, the only two of the life table, default `m`), `horizon_age` (default
  105, at least 1: the run ends at this age; a plan that ends before 90 shows the chance to run out
  by its last age, and one that starts after 67 the net worth at its first age, with that age in
  the words, also in the goal seek; when scenarios differ in it, the summary and the target of the
  goal seek say 90 and 67, and the help names the scenarios at another age), `children` (default 0,
  at least 0: every child, also a grown one), `children_born` (default none: a row for each child,
  at most `children` of them, see below), `rv_since` (optional: the first month of uninterrupted
  Rentenversicherung contributions), `kvdr` (default true, with `pkv: false` or from
  `tax.gkv_from` only).
  With `kvdr`, the pension makes you a compulsory member of the health insurance of pensioners
  (KVdR, §5 Abs. 1 Nr. 11 SGB V), which pays on the pension, a company pension and a profit beside
  them. False: you stay a voluntary member and pay on all income ([How the simulation
  works](models.md#the-statutory-health-insurance)).
  A row of `children_born` has these fields:
  - `born` (required): the date of birth.
  - `until` (a month, default empty): the first month in which the child no longer counts. Empty
    means the month after the 18th birthday, or the month of the birthday when it is on the first
    (§32 Abs. 3 EStG). For a child in education, enter the month after the end of the education.
    It must come after the month of birth and at most at the 25th birthday (§32 Abs. 4).
  - `kindergeld` (default true): the Kindergeld of the child is paid to you. The simulation pays
    it in each month in which the child counts, 259 € in 2026, in euros of the start. Use `false`
    when another person receives it.
  - `freibetrag` (`half` or `full`, default `half`): your share of the Kinderfreibetrag and the
    Betreuungsfreibetrag. `full` applies when the other parent pays no support and the allowances
    move to you on application (§32 Abs. 6 S. 6).
  - `erziehung` (default true): you raised the child, so the child-raising years count for your
    pension. Use `false` when the other parent gets them.

  While a child counts, the tax takes its allowances instead of the Kindergeld where that saves
  more (§31 EStG), and ALG1 pays 67% instead of 60%. A child without a row counts for nothing, also
  for ALG1: enter each child that still counts. Without a child the Pflegeversicherung adds the
  surcharge for the childless, up to the month of the first birth. In the statutory health
  insurance (`pkv: false`, or from `tax.gkv_from`) it takes 0.25 points less for each child of
  `children_born` under 25 from the second, up to the fifth, through the month in which the child
  turns 25 (§55 Abs. 3 SGB XI): the month of the birthday, for a birthday on the first the month
  before (§187 Abs. 2 S. 2, §188 Abs. 2 BGB). A child that `children_born` leaves out gives no
  discount. [How the simulation works](models.md#children) explains the rules.

  Schema 6 pays the Kindergeld itself. The migration to schema 6 writes `kindergeld: false` into
  every row of `children_born`, in `assumptions.yaml` and in the overrides of a scenario, with a
  comment above the list. So a plan pays as before, by its stream. Set `kindergeld: true` and
  delete the Kindergeld stream. The comment marks the file as migrated: keep it, or delete it
  after the change. Two other changes of schema 6 change no file: ALG1 pays 67% only for a child
  that counts, and the Soli and the church tax take the child allowances.
  `relatives` (default none): the relatives from whom you may inherit or receive gifts, never a
  spouse, as `{<name>: {label, born, sex, relation, given}}`. The name is what the events write
  in `from`, with the rules of a phase name. `label` (default: the name) names the relative on the
  pages. `born` (required, a date, before yours) and `sex` (required, `m` or `f`) draw the month of
  death from the life table. `relation` (required) sets the tax class and the Freibetrag of the
  Erbschaftsteuer (§§15, 16 ErbStG): `parent` (also a step-parent, 400,000 €), `grandparent`
  (200,000 €), `sibling`, `aunt_uncle` (you are the child of a sibling), `parent_in_law` (class
  II, 20,000 €) or `other` (class III, 20,000 €). `given` (default none): the gifts of the relative
  before the start, `[{at: 2024-03-01, value: 50000, tax: 0}]`: the month (before `start`), the
  nominal value and the nominal Schenkungsteuer paid. The tax adds the gifts of ten years from one
  relative (§14 ErbStG). The roll forward moves a `gift` event that passes the new start here, with
  the tax that it computes. The Assumptions page keeps the name of a relative that an event uses,
  and its `Rename a relative` changes it in every input.
- `start` (required): the first simulated month. Every amount in `cashflows.yaml` is in the
  euros of this month. The `Roll forward` of the Overview moves it and re-bases those amounts
  (`rollforward`). A stream paid every n months without `start` pays in the start month, so the
  roll writes the old start into it and its payment months stay.
- `phases` (required, at least one): the phases of life that the scenarios switch between, as
  `{<name>: {label: <text>}}`, in the order of the columns of the Cashflows sheet and of the colors
  of the phase bands. The name is what the files write: small letters, digits, `-` and `_`, a letter
  first, at most 24 characters, and no word that YAML reads as yes, no or null (`on`, `off`,
  `null`). `label` (default: the name) names the phase on the pages, also with capitals and umlauts
  (`Teilzeit`). Two phases cannot show alike. A new plan starts with `work: {label: Work}`,
  `unemployed: {label: Unemployed}`, `alt: {label: Career break}` and `retired: {label: Retired}`.
  The full example adds `new-job: {label: New job}` and `freelance: {label: Freelance}`. Schema 2
  named the four phases in the code, and the migration to schema 3 writes them after `start`. A
  stream, a factor, a bAV policy, `scale.salary` and a phase change of a scenario name a phase of
  this list: another name is an error at its file, line and key path. The simulation reads no
  name: what a phase means comes from the streams that pay in it (a salary, ALG1, the pension).
  So `part-time` is a phase in which the salary pays at a `factor`, and a sabbatical is one in
  which it does not pay. A scenario cannot override `phases`. The Assumptions page keeps the name
  of a phase that an input uses. Its `Rename` changes the name in every input that names it. The
  label can change at any time.
- `inflation`: `{mean, stdev}` per year, default `{mean: 0.02, stdev: 0.01}`. Monte Carlo
  draws one rate per calendar year, clipped at -2%.
- `indices`: named growth indices, `{mean, stdev, floor, cap, cumulative}` (`stdev` default 0,
  `floor` and `cap` optional, `cumulative` default true). The draw is yearly and steps each
  January. A cumulative index compounds the draw as growth. With `cumulative: false` the clipped
  draw is the level itself, for example a bonus payout ratio. The `fixed` and `historical` models
  use the clipped mean (`Index.at_mean`). `floor` is at most `cap`. The name `cpi` is reserved.
- `returns` (required): `{mean, stdev, equity_correlation}` per class, `stdev` default 0.
  `equity`, `fixed_income`, `cash` and `property` are required. Extra names serve as `growth` of a
  property, a policy, an
  Altersvorsorgedepot, gold (default `gold`) or crypto (default `bitcoin`). No values ship for
  them, and an asset whose class `returns` lacks is an error. `equity_correlation` (-1 to 1,
  default 0, not on `equity` itself) ties the Monte Carlo draw of a class to the one of equity.
  The `historical` model replays equity, fixed income and the class `gold` when a gold or crypto
  asset grows with it (the World Bank prices in euros from 1960). It draws every other class of a
  gold or crypto asset as Monte Carlo does (`bitcoin`: its prices from 2010 are no sample of the
  future), tied to the replayed equity month by `equity_correlation` (at 0.4 a mean of 30% with a
  spread of 85% then comes out near 31%). It takes the mean of every other class. A large
  `stdev` lowers the growth of the median path to
  (1 + mean) / √(1 + stdev² / (1 + mean)²) - 1: a mean of 15% with a spread of 80% loses money
  there. Set crypto conservatively: Bitcoin fell by 75% or more four times since 2011 (a spread
  of 60% to 90% gives that), and its monthly correlation with the MSCI World was 0.3 to 0.5.
  `src/dagobert/examples/engineer/` takes a mean of 10%, a spread of 60% and a correlation of 0.4:
  its median path loses about 3% a year. `fixed` compounds the mean, so there Bitcoin grows by 10%
  a year.
- `refinance_rate` (default 0.04): the rate of every loan after its `fixed_until`. The annuity
  stays, so a higher rate repays more slowly.
- `cash_buffer_months` (default 3, at least 0): months of the expected expenses kept as cash
  before the surplus is invested. It is a ceiling only: a deficit does not refill it, and a
  savings plan draws below it.
- `invest_rest` (default true): invest the cash above the buffer each month, by the allocation.
  `false` keeps it in cash, where it earns the `cash` return and pays its tax each December.
  Then only the savings plans and the `invest` of a sale invest.
- `pension_growth` (default 0): yearly growth of the pension on top of the `index` of its
  stream, before and after the claim, stepped each January. The default index is `cpi`, so this
  is the real growth: the pension follows the consumer prices of each path. Schema 3 took a
  nominal growth (default 0.02). The migration to schema 4 writes that growth less
  `inflation.mean`, with a comment, into `assumptions.yaml` (always, also a growth of 0) and into
  each scenario whose overrides set the growth or the inflation. So the mean path pays the same
  pension as before. The comment in `assumptions.yaml` marks the directory as migrated: keep it.
- `allocation` (optional, without it all surplus goes into equity): `fixed_income`, the glide
  path as `[{age, share}]` (required, at least one point: the share of the liquid investments
  held as fixed income, linear between the ages), `rebalance_every` (months, default 12, at
  least 1) and `skip_after_loss` (months, default 12, at least 0: a rebalancing sells no equity
  when equity fell over this many months, 0 always rebalances).
- `spending` (optional): the band of the flexible spending and the age curve. `cut` (default 0, 0
  to 1) is the share taken off the flexible `categories` (default none) while the liquid wealth at
  the start of a month is below `trigger` (default 0, which switches the cut off) times the
  reference wealth, in real terms. `increase` (default 0, at least 0, also above 1) is the share
  added to them while it is above `ceiling` (default 0, which switches the increase off) times the
  reference wealth. A month that cuts does not raise. `base` sets the reference wealth. `start`
  (default): the liquid wealth at the start, and the rules act in every month. `no_pay`: the liquid
  wealth at the first month without a salary or a profit (of any amount: ALG1, a pension and
  `other_income` are no pay), and the rules act only in a month after a month without pay, again
  with a new reference after twelve months of pay in a row. An `increase` above 0 needs `base:
  no_pay`, and with a `ceiling` above 0 that is above `trigger`. `reference` (euros, default none)
  is the reference wealth of the start in start-year euros, with `start` or with `no_pay` when the
  plan starts without pay. The roll forward changes it by the consumer prices. `age_curve` as
  `[{age, factor}]` (default none) is a factor on spending by age, in real terms. `age_categories`
  names the categories that it reaches (default: all expense streams except the health premium
  and the costs of a let property). A category of either list without such a stream is rejected.
  `vpw` (optional) spends the flexible `categories` by variable percentage withdrawal instead of
  the cut and the increase: `growth` (a real rate per year, default 3%, 0 to 10%), `horizon_age`
  (default 100, 60 to 120) and `floor` (euros per month in start-year euros, default 0). The budget
  of a year is the liquid wealth at the start of its first month without pay times the rate of the
  age: the payment at the start of each year of an annuity at `growth` over the years to
  `horizon_age`, at most 10%. Each month without pay the flexible categories spend a twelfth of it
  plus what the other flows of the month net in the cash (income less the other expenses, the loan
  payments, the premium of a Basisrente, the KV), less a twelfth of the tax bill of the December
  before, at least `floor`. Each flexible stream pays monthly by its share of their plan amounts of
  the month, whatever its `every`. A month with pay pays the plan. `vpw` needs `base: no_pay`,
  `categories`, and `trigger` and `increase` at 0. The roll forward changes `floor` by the consumer
  prices.
- `care` (optional): `hazard` as `[{age, factor}]` (required, at least one point: the yearly
  probability of entering care, linear between the points, zero before the first age and flat
  after the last, `CareOptions.hazard_at`. The age curve and the glide path hold their first point
  flat before it). `cost` (required, above 0) is the cost per month above the benefit of the
  Pflegeversicherung, in start-year euros. `duration` is `{mean, stdev}` in months (`stdev`
  default 0). `index` (default `cpi`, an index of `indices`, or `null` for nominal euros) is what
  the cost follows. The factor of the hazard is a probability, at most 1. Each of the three age
  lists holds an age once, and ages are at least 0.
- `disability` (optional): the loss of the ability to work, a full Erwerbsminderung (see [the
  models](models.md#when-you-cannot-work)). `hazard` as `[{age, factor}]` (default: the curve of
  `DEFAULT_HAZARD`, from 0.044% at 20 to 1.614% at 64): the yearly probability, linear between the
  points, zero before the first age, flat after the last and zero from the statutory pension age,
  each age once. `at` (a month, default none): a what-if, the onset in that month in every path,
  also in a `fixed` run, at or after `start` and before the age of 67. So `overrides: {disability:
  {at: 2038-01}}` in a scenario is enough: without a block in `assumptions.yaml` it takes the
  default curve. Without the block no path loses the ability to work. The roll forward refuses a new
  start after `at`.
- `scale` (optional): what-if factors on the plan, 1 when absent, each at least 0. `spending` (a
  number) acts on every expense stream that `categories` reaches, also those without a category
  factor, and multiplies with it. `categories` as `{<cat>: factor}` acts on the expense streams of a
  category, except the health premium and the costs of a let property (`Stream.managed`). The
  spending cut and the age curve apply on top, and a category without such a stream is rejected.
  `savings` as `{<name>: factor}` acts on the rate of the savings plan of that name, every row of
  it. A name without such a stream is rejected, and the sliders of the Explorer leave out a plan
  that a chosen scenario lacks. `salary` as `{<phase>: factor}` acts on every salary payment and
  every profit of a business in a phase of `phases`, also of streams that a scenario adds. A derived
  stream (`of`) scales once. `growth` as `{<phase>: rate}` (a rate per year, default 0, also below
  0) acts on the same payments, on top of their `index` and of `salary`. Over the default index,
  the consumer prices, it is the real growth. It adds one step each January: the first January
  after the phase starts is the first step, and a phase that starts before `start` counts from
  `start`. If the phase comes back later, it starts again at the amounts of its streams. A derived
  stream takes it once, and ALG1 after the phase takes the last salary with its growth. A pension,
  ALG1 and other income do not take it. A plan that gives a phase an index of its own keeps
  working. The Explorer writes them: one slider for all spending, one per category, per phase with
  a salary or a profit (with its growth beside it) and per savings plan. A savings plan slider shows
  euros per month: the rate of its first row times the factor. A slider of the group `Salary and
  profit` shows euros too, in steps of 500: the gross salary and profit of a usual month in the
  phase, from a `fixed` run of the first chosen scenario (the median month, so without a bonus). The
  file gets the factor on that gross, and the other chosen scenarios change by the same share. The
  `Overrides` tab of the Scenarios page edits them too, the salary in the same euros.
- `tax`: all fields are optional.
  - `year`: a file in `src/dagobert/data/tax/`, and only 2026 exists. The default is the newest
    file up to the year of `start`, the oldest when none is. The amounts are in euros of the
    start, so a roll forward into a new year takes the file of that year.
  - `sparer_pauschbetrag` (default 1000, at least 0): the capital income free of tax per year.
  - `teilfreistellung` (default 0.30, 0 to 1): the share of the gains of an equity fund free of
    tax. An `equity` asset without its own `teilfreistellung` takes it.
  - `werbungskosten` (default 0, at least 0): your work expenses of a year with a salary in every
    month, as the Steuerbescheid lists them: the commute, a home office, work equipment, union
    dues. Enter the euros of the start. A year with fewer months of salary counts its share: a job
    that ends in March counts a quarter. They count at most up to the salary of the year. Costs at
    a date, for example a course, are an expense with `deduct: work`. The income tax takes them
    when they are higher than the Arbeitnehmer-Pauschbetrag (1,230 € in 2026), which applies
    anyway. The monthly withholding does not know them, so the December settlement refunds. ALG1
    does not change with them. The `Roll forward` of the Overview changes the amount by the
    consumer prices. A scenario can override it, for example with 0 for a remote job.
  - `harvest` (default false): each December, sell the equity whose gains fit into the tax-free
    room of the year, and buy it back at the next price. The room is the Sparer-Pauschbetrag that
    is left, and the part of the Grundfreibetrag that your other income leaves. A later sale then
    pays less tax. Carried losses come off a gain first, so the harvest uses them only if the
    tax-free room beyond them is at least as large. If you are a voluntary member of the
    statutory health insurance in the next January, the harvest keeps the contribution of the next
    year at its minimum. In other cases this limit does not apply. See
    [How the simulation works](models.md#realizing-gains).
  - `pkv` (default true): privately insured. Then there is no statutory KV and PV, and the
    `health` streams take the subsidies and the deduction. With `gkv_from`, this is true only
    before that month.
  - `gkv_from` (a month, default empty, only with `pkv: true`): the first month in the statutory
    health insurance (GKV). Before this month the rules of the PKV apply. From this month the
    rules of the GKV apply, and the `health` streams end by themselves. A salary, ALG1 or a
    pension with `person.kvdr` makes you a compulsory member, else you are a voluntary member
    ([How the simulation works](models.md#the-statutory-health-insurance)). The law decides
    whether you can change. Before 55, a salary below the Jahresarbeitsentgeltgrenze or ALG1
    makes you a compulsory member (§5 SGB V). From 55, §6 Abs. 3a SGB V usually blocks the
    change. The simulation does not refuse a change at 55 or later, but it marks it. Set it in
    the `overrides` of a scenario to compare it with a scenario that stays in the PKV. After a
    late change you usually stay a voluntary member as a pensioner too: set `person.kvdr` to
    false then. Empty: the PKV for the whole run.
  - `kv_zusatz` (default empty: the average Zusatzbeitrag of the tax year, 0.029 in 2026): the
    whole rate of your own Krankenkasse, at least 0, for the statutory health insurance only. You
    pay half of it on a salary and on the pension, and all of it on the other income that pays,
    such as a company pension or a profit.
  - `church` (default false): a member of a church that levies the church tax.
  - `land` (a Land code such as `NW`, needed with `church`): `BW` and `BY` take 8% of the income
    tax, the other Länder 9%.
  - `loss_carryforward` (default 0, at least 0): the Verlustvortrag of your last
    Feststellungsbescheid (§10d Abs. 4 EStG), in euros of `start`. These are losses of earlier
    years, for example of a let flat or a business. They offset the income of the first years
    before the Sonderausgaben. The `Roll forward` of the Overview writes the losses that the plan
    carries to the new start, into the `tax` that the scenario takes: that of its `overrides` or
    of a scenario that it extends, else that of `assumptions.yaml`, where it adds `tax` when the
    file has none. Scenarios that share one `tax` take the smallest amount. The losses of
    capital income are another pot: see `capital_losses`.
  - `loss_carryback` (default true): a loss of a year can go back (Verlustrücktrag, §10d Abs. 1
    EStG). It goes into the year before, and the rest into the year before that. Each year takes it
    up to its income, at most 1,000,000 € in all, and the losses that a year carried forward come
    first. The refund comes in the December after the year of the loss. What is left carries
    forward. The carryback comes off before the Sonderausgaben, so in a year of low income it can
    use up the tax-free amount (Grundfreibetrag). Since 2022 the law lets you waive only the whole
    carryback. With true, the simulation chooses in that December, separately for each path. It
    waives the carryback when the loss saves more tax in the year after the loss than the refund.
    It does not count what the loss saves in later years. A loss of the last year of the plan
    always goes back. With false, the simulation always waives: the whole loss carries forward. The
    years before `start` take no carryback. See [How the simulation
    works](models.md#a-loss-of-a-year).
  - `capital_losses` (default 0, at least 0): the losses of capital income that you carry forward
    at the start (§20 Abs. 6 EStG), in euros of `start`. Enter the sum of two amounts: the losses
    that your bank still holds in its loss pot (its yearly tax statement lists them), and the
    losses of capital income in your last Feststellungsbescheid. A loss certificate of the bank
    (Verlustbescheinigung) moves the first amount into the second. They offset the capital
    income of later years, gains and interest, before the Sparer-Pauschbetrag. While they are
    larger than the tax-free room of a year, `harvest` realizes no gains. By law, a loss from the
    sale of single shares (Aktienverlusttopf) offsets only gains from single shares (§20 Abs. 6
    S. 4 EStG). The BVerfG checks this rule
    (2 BvL 3/21) and did not decide yet. If it strikes the rule, such a loss offsets all capital
    income. So add a loss of single shares only in the `overrides` of a scenario, and compare that
    scenario with one without it. The simulation holds no single shares, so it has no pot for
    shares alone. The `Roll forward` writes the losses that the plan carries to the new start
    into the same `tax` as `loss_carryforward`. It does not change them by the consumer prices,
    because the law keeps them in nominal euros.
  - `alleinerziehend` (default false): you raise your children alone, with no other adult in the
    household. The Entlastungsbetrag (§24b EStG) of 4,260 € a year in 2026, and 240 € more for each
    further child, comes off the income in each month in which a child of `children_born` counts.
  - `self_employed`: the social insurance of a business, see below.
  - `crypto_capital_from` (a month, default none: the law of today). A crypto unit bought in or
    after that month is capital income (§20 EStG) without a holding period, as the BMF draft of
    2026-09-30 plans for coins bought from 2027 (`2027-01`). It is not law yet. Such a unit pays
    the flat tax at the sale (see `tax: capital` of the gold and crypto assets), also a unit of
    the trades bought before the start. Gold stays a private sale.
- `tax.church` with `tax.land`: the church tax is 8% or 9% of the income tax, also of the tax
  that the employer withholds. On capital income the flat tax falls to 24.51% or 24.45%, and the
  church tax comes on top: 27.82% or 27.99% with the Soli. The church tax that you pay in a year
  lowers the taxable income of that year. A scenario leaves the church with the override `tax:
  {church: false}`. Some Länder cap the church tax on application (Kappung). Dagobert does not
  apply that cap.
- `tax.self_employed`: the social insurance in a month with a business (`kind: self_employed`) and
  without a salary or ALG1. `rv` (default `none`): the statutory pension insurance. `none` pays
  nothing, as most self-employed people do today. `regular` pays the Regelbeitrag, 18.6% of the
  monthly Bezugsgröße (735.63 € in 2026), and half of it up to the end of the third calendar year
  after the year of the founding. `income` pays 18.6% of the profit, at least of the
  Geringfügigkeitsgrenze (603 €) and at most of the contribution ceiling, also in the first years.
  Only `regular` has the half years. Some trades must pay (§2 SGB VI), and every self-employed
  person can apply within five years (§4 Abs. 2 SGB VI). The contributions earn pension points.
  `krankengeld` (default false, for the statutory health insurance only): the general rate of 14.6%
  with sick pay instead of 14.0%. `founded` (a month, default empty: the first month in which a
  business runs) starts the years of the half Regelbeitrag. Set it for a business that started
  before the simulation start. The `Roll forward` of the Overview writes it when a business runs
  before the new start. It writes it into the `tax.self_employed` that the scenario takes: that of
  its `overrides` or of a scenario that it extends, else that of `assumptions.yaml`. Without them
  `rv` is `none`, and the roll writes nothing. A second business after a break takes the half
  years of the first one: `founded` sets another start.
- `seed` (default 7): the seed of the engine draws for care episodes, the onset of a disability
  and sale prices. The
  `--seed` option of `dagobert run` seeds the return provider instead.

## `data/assets.yaml`

A list under `assets`, each with a `kind`. Every asset has an `id` (unique), and optional `name`,
`tags`, `asof` (the date of the value) and `update_every`. `update_every` (at least 1) is the
number of months after which the value needs an update on the Overview and the Snapshot page, for
example 3 for an account with a quarterly statement. Without it, a term deposit and a property
never need an update, and every other asset takes 12 months. A property that the main scenario
sells on a date takes 6 months. The simulation counts every value at its start. It
carries a value with an `asof` before the month of the start to its start: a loan by its schedule,
a `bav` policy (also `paid`) and an `av_depot` by the mean return of their class less `cost` and
the contributions of the months between, in the phases of the scenario. A term deposit counts
with its interest from its own `start`. A value with an `asof` in the month of the start or later
counts as it is. The simulation then adds the months from the start up to that date once more:
their returns, payments and contributions. A `Roll forward` of the Overview to a start after that
date ends this overlap. The Snapshot page estimates these values for today in the same way. The
records of the Overview count a value at its `asof`, and a value without one at the simulation
start. The tables of the Assets page show readable headers for some keys
(`assets.TITLES`), for example `ID` for `id`, `as of` for `asof`, `check every (months)` for
`update_every` and `price per m²` for `per_sqm`. `Rename` on the Assets page changes an `id` in
every input that names it and in the rows of `history.csv`. The text of every other line stays,
comments too. Trades and price files name a security, not the asset, so they do not change.

- `cash`: `value`. Earns the `cash` return.
- `fixed_income`: `value`, optional `trades`. Tagesgeld, Festgeld without maturity, bond and
  money-market funds. Earns the `fixed_income` return and belongs to the allocation bucket.
  The bucket is liquid. It can also stand for a rolling Festgeld ladder in which one rung
  matures each year and covers more than the yearly gap: the engine does not model the rungs.
  `trades` work as for `equity`, for the price import, the valuation and the return only: the
  engine uses no basis here. A money-market ETF in a depot is its own `fixed_income` asset beside
  the `equity` asset of the depot (`money-market` in the full example), because the depot is one
  pool of equity for the engine.
- `term_deposit`: `value` (the amount invested at `start`, without interest), `rate`, `start` and
  `matures` (both full dates, `start` before `matures`), all required. Interest compounds yearly
  (actual/365) and is paid once at maturity. A deficit cannot draw on the deposit before that.
  The payout rolls into the fixed-income bucket (into cash without an allocation).
- `equity`: `value`, and either `trades` or `cost_basis`, not both. A depot is one asset.
  `trades` lists the bookings as the bank shows them, also of securities that are sold:
  `date`, `kind` (`buy`, `sell`, `vorabpauschale`), `security` (the ISIN: schema 1 named it
  `isin`, and the migration renames it), `name` (the last one given names the security), `units`
  (above 0, none for a Vorabpauschale), `amount` (at least 0: the Kurswert without fees, or the
  Vorabpauschale of the fund), `fees` (default 0). A Vorabpauschale is dated with its booking in
  January and counts for the year before: another month is an error. The open lots give the
  basis: their cost with fees plus the Vorabpauschale charged on them. The `securities` tab and
  `dagobert trades import` remove `cost_basis` when they save trades, and say so: import the
  trades from the first purchase on, or the basis misses the cost of the older shares. The engine
  uses only `value`, the basis and `teilfreistellung`. The trades do not change `value`. Without
  the tax certificates, a Vorabpauschale row can be estimated from the price files and the
  Basiszins.
  `teilfreistellung` (0 to 1, default empty: `tax.teilfreistellung`) is the share of the gains
  that is free of tax (§20 InvStG). The law gives 0.30 to an equity fund, 0.15 to a mixed fund,
  0.60 to a real-estate fund and 0.80 to a fund of foreign real estate. Shares, bonds,
  certificates and funds of gold or crypto get 0. Keep one asset for each class, for example the
  ETFs of a depot in one asset and the shares of your employer in another (`share-plan` in the
  full example). The engine adds all `equity` assets to one pool with one return. It keeps the
  part of the value and of the basis that is taxable, so the gain of each asset pays at its own
  rate. A sale takes a slice of every asset. The invested surplus, the `invest` of a sale, the
  rebalancing and the securities of an inheritance or a gift buy at the default
  `tax.teilfreistellung` (0.30); only
  a savings plan `into` an asset buys at its rate. Shares at 0 also pay the Vorabpauschale. The
  pool grows by the total return and pays out no dividends, so the Vorabpauschale stands in for
  the tax on them.
- `gold` and `crypto`: `value` (the market value at the start), `trades` as for `equity`, but only
  `buy` and `sell`. `security` is an ISIN or a symbol of 2 to 10 capitals and digits that starts
  with a capital: `XAU` counts troy ounces of exactly 31.1034768 g, `BTC` bitcoins. The Snapshot
  values them at the last month of the gold series and of the Bitcoin series (once fetched on the
  Data page), unless a price in `prices/XAU.csv` or `prices/BTC.csv` is as new or newer. One asset
  is one depot or wallet, as the BMF counts per wallet. The engine spreads `value` over the open
  lots, by units within a security and by cost across securities, because it reads no prices. So
  keep one security per asset. An asset without trades counts as held for more than a year.
  `growth` is the return class (default `gold` or `bitcoin`, another coin takes a class of its
  own). `cost` is the yearly custody as a share of the value (default 0, 0 to 1). A spread of a
  dealer goes into the `fees` of a trade. `tax` is `private_sale` (default: bars, coins, Bitcoin,
  and a note fully backed by gold or coins such as Xetra-Gold, §23 EStG) or `capital` (a note
  without backing, §20 Abs. 2 S. 1 Nr. 7 EStG). `capital` needs trades for its basis.
  - A private sale: a unit sold up to 12 months after its purchase month is taxable (bought in
    2025-03, sold by 2026-03), at worst a month longer than the law says. The engine sells the
    oldest units first. The private sales of a year add up (gold, crypto and a taxable property
    sale), so a loss offsets a gain. A net gain below 1,000 € is free. From 1,000 € the whole gain
    pays the personal tariff: a Freigrenze in euros of the start, so it grows with the prices. A
    net loss carries forward to the private sales of later years. It offsets a net gain of
    1,000 € or more, and one below the limit stays free and keeps the loss.
  - `capital` and `tax.crypto_capital_from`: the gain pays the flat tax at the sale, without
    Teilfreistellung and without Vorabpauschale. A loss goes into the general loss pot of the
    capital income.
  - Gold and crypto count as liquid. A deficit sells them after equity: first the free units of
    every asset, then the rest, the oldest first.
  - Shares of gold miners, and funds of them, are `equity`. A fund that holds gold or Bitcoin is
    `equity` with `teilfreistellung: 0`: it pays the Vorabpauschale and the flat tax without
    Teilfreistellung (InvStG). Its value then grows with the `equity` return.
  - Not modelled: income from staking and lending (§22 Nr. 3 EStG), gold lent against interest
    (a holding period of ten years), a swap of one coin for another (write a sale and a `buy`),
    the carryback of a loss of private sales into the gains of private sales of the year before
    (§23 Abs. 3 S. 8 EStG), and the limit of §10d Abs. 2 EStG on a carried loss against the part
    of a year's gain above 1 Mio. €.
- `property`: `sqm` (the living space, above 0), `per_sqm` (the market value per m², at least 0),
  optional `bought_for` (what the purchase cost: the price with the Grunderwerbsteuer, the notary
  and the broker), `growth` (return class, default `property`), `upkeep` (yearly share of the
  value, default 0). The value is `sqm` times `per_sqm`. Three optional fields serve a let
  property and a taxable sale:
  - `bought`: the month of the purchase, at the latest the month of `start` (a later purchase is
    a `buy_property` event). A `taxable` sale within ten years of it is a private sale (§23
    EStG). Without it, `taxable` alone decides.
  - `building_share` (0 to 1): the share of the building in `bought_for`. The land is the rest,
    and the land is not depreciated. The Arbeitshilfe Kaufpreisaufteilung of the BMF gives a
    first estimate.
  - `afa` (0 to 1): the yearly depreciation (AfA) of the building, by the year in which the
    building was completed (§7 Abs. 4 S. 1 Nr. 2 EStG): 0.03 after 2022, 0.02 from 1925 to 2022,
    0.025 before 1925. A shorter useful life that you can prove takes its own rate. 0 takes
    none, for example for a building that is depreciated already.

  A property is let in a month in which an `other_income` stream that names it is active (see
  `property` in `cashflows.yaml`). A let property needs `bought_for`, `bought`, `building_share`
  and `afa`, else the plan does not load: no default sets a tax base. Its AfA is `afa` times
  `bought_for` times `building_share` a year, a twelfth in each let month, until the AfA reaches
  the cost of the building. The engine counts the AfA of the months from `bought` to the start
  as taken, as if the property was let since the purchase. The month of a sale takes no AfA: the
  sale runs before the streams of its month (the tax law counts that month, a twelfth of a year's
  AfA). An heir continues the AfA of the
  testator (§11d EStDV): enter the `bought`, `bought_for` and `afa` of the testator. An app before
  these fields, `finances` and `property` does not load a plan with them.
- `av_depot`: the Altersvorsorgedepot from 2027. `value` (default 0, at `asof`), `contribution`
  (default 1800, at least 0, 0 means no depot): paid each December of a year in which you are
  eligible (a month with a salary, ALG1 or a business), in start-year euros, and the Zulage counts
  up to 1,800. You get one Zulage, however many depots you have: it counts on the sum of their
  contributions and goes into each by its share. From 2027 each child whose Kindergeld you get in
  some month of the year adds a Kinderzulage of its contributions, at most 300 € a child. Only the
  rows of `person.children_born` with `kindergeld` count, up to their `until`. `start` (required) is
  the first year with a contribution, 2027 or later. `growth` is the return class (default
  `equity`), `cost` the yearly share of the value (default 0), `lump_sum` the share paid at the
  start of the payout (default 0.3, at most 0.3), `until_age` the end of the Auszahlplan (default
  85, at least 85).
- `loan`: `balance` (below 0: the balance at `asof`, else at the start), `rate`, `annuity` (the
  monthly payment of interest and principal, above 0), optional `fixed_until` (the last month of
  the fixed rate: after it the loan takes `refinance_rate`, without it the rate holds for the
  whole term), `prepayment_penalty` (default 0: the share of the repaid balance that a repayment
  pays up to `fixed_until`, without `fixed_until` for the whole term). The law limits the
  penalty: ten years after you received the whole loan, you can end it with six months' notice,
  and no penalty is due (§489 Abs. 1 Nr. 2 BGB). A new agreement on the rate or the term starts
  the ten years again. The engine does not know these dates. So for a repayment ten years and six
  months or more after the payout, set `prepayment_penalty` to 0. A `fixed_until` at that month
  would change the rate too. `finances` (optional, the `id` of the property that the loan paid
  for): while that property is let, the interest of the loan lowers the taxable rent. The engine
  amortizes loans. Do not add loan rates as expense streams.
- `bav`: betriebliche Altersversorgung, a company pension. `value` (required, at least 0) is the
  policy value at `asof`, `paid` (default 0) the contributions by then, the base of the guarantee.
  `contribution` (default 0) is what the employer pays on top of the salary, a nominal monthly
  amount, free of tax and social insurance. `conversion` (default 0) is the part of the salary
  that goes into the policy (Entgeltumwandlung), a nominal monthly amount. It comes off the gross
  of `salary`, a monthly salary stream (`every: 1`, no `of`).
  Without `salary`, it comes off the first monthly salary that pays in the month. Several
  conversions from one salary take at most its gross together, in the order of the file.
  Together with the contribution and the subsidy of the employer, the conversion is free of
  income tax up to 8%
  and free of social insurance up to 4% of the contribution ceiling of the pension insurance:
  676 € and 338 € a month in 2026 (§3 Nr. 63 EStG, §1 Abs. 1 Nr. 9 SvEV). The part above a limit
  pays the tax or the social insurance. The lower gross also lowers the pension points, the ALG1
  and the subsidy of the employer to a private health insurance. `subsidy` is the share of the
  conversion that the employer adds by contract. Without it, the employer adds 15% as far as the
  conversion saves it social insurance (§1a Abs. 1a BetrAVG): 10.6% above the contribution
  ceiling of the health insurance or for a private health insurance, nothing above the ceiling of
  the pension insurance. The simulation applies these rules to every policy, as the law does for
  a Direktversicherung, a Pensionskasse or a Pensionsfonds. A Direktzusage or an
  Unterstützungskasse has no limit for the tax and no subsidy by law. `examples/starter/` uses a
  conversion. The contribution and the conversion are paid in `phases` until `matures` (a month,
  required). `phases` is required: the phases of the job of the policy, `[]` for none. Schema 2
  took `[work]` without them, and the migration writes it. A later job in a phase of its own takes
  no contribution from the old employer.
  `guarantee` (default 0, 0 to 1) is the share of all contributions paid at least at maturity.
  `growth` is the return class (default `bav`), `cost` a yearly fee as a share of the value
  (default 0). `growth: equity` with a `cost` models an ETF-based Nettotarif that moves with the
  depot. `payout: lump_sum` (default) pays into cash as Arbeitslohn with the Fünftelregelung,
  unless `fuenftel: false`. `payout: annuity` pays `annuity_per_10k` (required then) per month per
  10,000 EUR capital, nominal and fully taxable. The policy is illiquid: it counts in `total`, not
  in `liquid`. Once it pays an annuity, the capital less the payments received stays in `total`
  (floored at zero, no present value, no mortality). A policy with `value: 0`, `contribution: 0`
  and `phases: []` is an empty vehicle that scenario events can fund (`severance.bav`,
  `fund_policy`). It pays nothing and leaves no marker elsewhere.
  `basisrente: true` (default false) marks a Basisrente (Rürup). In the statutory health insurance
  (`pkv: false`, or from `tax.gkv_from`) the payout of a company pension is a Versorgungsbezug (§229
  SGB V). A compulsory member pays the health and care rates on it above 197.75 € a month, a
  voluntary member on all of it, and a lump sum counts as 1/120 for 120 months. A Basisrente pays
  them only for a voluntary member. A Basisrente needs `payout: annuity`: the law allows no lump
  sum. Set `basisrente: true` on every Basisrente. Without it, the simulation takes the policy for a
  company pension: the payout pays the health and care rates also in the KVdR, the income tax takes
  all of it, and you cannot pay into it.
  - `premium` (default 0, at least 0, only with `basisrente: true`): your own premium per month,
    nominal, from the cash in the `phases` of the policy until `matures`. When the cash is short,
    the simulation sells assets to pay it, as for any bill. The premium lowers the income tax
    like the statutory pension insurance, together with it up to the Höchstbetrag (30,826 € in
    2026, less the employer's half of the pension insurance).
  - The income tax takes the annuity of a Basisrente at the share of the year in which it starts,
    as for the statutory pension: 84% for 2026, half a point more for each later year, 100% from
    2058. The share of `matures` counts, the share of 2023 for an earlier year. The annuity is
    fixed, so the taxed part is the same each year. The annuity of a company pension is taxed in
    full.
  - A Basisrente takes no `contribution` and no `conversion`, and no severance pays into it: this
    money is free of tax on the way in, and the law taxes its payout in full. Your own payments go
    in by `premium` and `fund_policy`.

## `data/cashflows.yaml`

A list under `streams`. Fields:

- `name` (required), `cat` (the category for the spending rules, default empty), `tags` (a
  property sale ends tagged streams). Rows with one `name` are one stream, for example a salary
  and its raise. Name and `start` together must be unique. `Rename` on the Cashflows page changes
  the name on all of them and in every input that names the stream.
- `kind`: `expense` (default), `salary`, `alg1`, `pension`, `other_income`,
  `rv_voluntary`, `savings`, `self_employed`, `bu`.
- `amount`, a monthly amount in euros, for every kind but `salary`, `pension` and `alg1`:
  - `expense` and `savings`: at most 0, and 0 is off.
  - `rv_voluntary`: below 0.
  - `other_income`: any sign, income above 0.
  - `self_employed`: the profit, below zero for a loss. 0 is no profit, not off.
  - `bu`: the monthly benefit, at least 0.
- `gross` for `salary` (required, except with `of`) and `pension`. `alg1` takes neither: the
  simulation computes it from the last salary ([How the simulation
  works](models.md#unemployment-benefit)). Its claim is a number of days: 12 months, 15 from age
  50, 18 from 55 and 24 from 58 in the first month in which an `alg1` stream pays. A later time
  with an `alg1` stream pays the rest if it starts within four years after that month. `part` (default 1, 0 to 1) scales a salary gross
  for part time. A field that the kind does not take is rejected, also `amount` beside the `gross`
  of a salary: each field here names its kinds, `cat` every kind but `savings`, `alg1` only
  `sperrzeit` and `training`.
- `sperrzeit` (only `alg1`, default false): you quit or signed an Aufhebungsvertrag, so a
  Sperrzeit applies (§159 SGB III). It starts in the first month in which the row pays, once for
  the row. For 12 weeks the row pays no ALG1, and the employment agency pays no private health
  premium and no pension contributions. The claim loses those days, at least a quarter of its
  days (§148 Abs. 1 Nr. 4 SGB III). An app before this field does not load a plan with it.
- `training` (only `alg1`, default false, not with `sperrzeit`): the months of a course with a
  Bildungsgutschein (§§81, 144 SGB III). Add this row beside the `alg1` row of the phase, with the
  `start` and the `end` of the course. ALG1 pays once a month, the same amount, and the sheet shows
  it on the other row. Two days of the course use one day of the claim, but never below three
  months. After a course of six months or longer, a rest below three months rises to three months,
  once. An app before this field does not load a plan with it.
- `of` and `share` (0 to 1) go together: a salary stream without `gross` that pays `share` of the
  gross of another salary stream for `every` months, for example a bonus. `of` names a salary
  stream without `of`. The own `index` of the stream then acts as a payout ratio. When several
  rows carry the name (a raise is a successor row), it follows the row that is active in the
  month; when none is, the row that started last, and before the first row it pays nothing.
- `points` and `point_value` instead of `gross` for a pension (Renteninformation): a pension
  takes either `gross` or both of them. Both `gross` and `point_value` are in euros of `start`.
  The pension follows its `index` like any stream, plus `pension_growth`.
- `every` (default 1, at least 1): period in months, counted from `start` or the simulation start.
- `phases`: the list of phases (of `assumptions.yaml`) in which the stream applies, default all.
  `factor`: a multiplier per phase, at least 0, for example `{retired: 0.5}`.
- `start` (optional): the first month in which the stream pays. `end` (optional): the first month
  in which it no longer pays, so `end: 2031-01-01` pays through December 2030.
- `index`: `cpi` (the default, for a savings plan `null`), a name from `assumptions.indices`, or
  `null` for a nominal amount.
- `health: kv` or `health: pv` marks an expense as a part of the PKV premium (subsidies,
  deduction). Every tariff is its own stream, so a new Nachtrag is an edit of amounts: for example
  Krankentagegeld with `phases: [work]`, the gesetzlicher Zuschlag with `end` at age 60, the
  Pflegepflicht part as `pv`. The engine holds no premium parts. `deductible` (0 to 1) with
  `health` is the share of a part that is Basisabsicherung and a Sonderausgabe, from the
  certificate of the insurer. The default is all of `pv`, and `pkv_basis_share` of the tax year
  for `kv`. A `health` stream ends in the month of `tax.gkv_from`.
- `deduct` (an `expense` without `health` and without `property`, default none): what the expense
  is for the income tax. The cash flow stays an expense of its category.
  - `work`: work expenses (Werbungskosten, §9 EStG) at a date, for example a course that you pay
    yourself or the costs of applications. They count in the year that pays them, on top of
    `tax.werbungskosten`, also in a year without a salary. Above the salary of the year they make a
    loss, which goes back and forward (`tax.loss_carryback`).
  - `donation`: up to 20% of the income (the Gesamtbetrag der Einkünfte) lowers the taxable
    income. The simulation loses the rest. The law carries it to later years.
  - `childcare`: 80% of the costs lowers the taxable income, at most 4,800 € a year for each child
    under 14 in some month of the year. Only the months with a child under 14 count, and only
    children with a date of birth in `person.children_born`.
  - `household`: household services, such as a cleaner. 20% of the costs come off the income tax,
    at most 4,000 € a year (§35a EStG).
  - `craftsman`: the labour of a craftsman. 20% of the costs come off the income tax, at most
    1,200 € a year.
  `deductible` (0 to 1, default 1) with `deduct` is the share that counts: the labour part of a
  craftsman's bill, the donations among the gifts. A deduction counts what the stream paid, after
  `scale` and the spending cut. Pay the services of §35a by bank transfer: the law refuses cash.
- `repays: <loan id>`: `other_income` with `index: null` paid straight into the loan, for
  example employer VL. The ledger books the payment as principal of that loan (under its `name`,
  else its `id`). The loan is the same on every path: a sale with `liquid_below` must not end or
  start the stream (its `property`, tags, `after_sale_of`), else the scenario does not load.
- `after_sale_of: <property id>`: the stream starts in the paths that sold that property.
- `property: <property id>`: the stream belongs to a let property. On an `other_income` stream the
  amount is the rent of that property, and the property is let in each month in which the stream is
  active (its dates, phases and the paths of a sale; a stream paid every n months in each month). On
  an `expense` stream without `health` the amount is a cost of letting it, for example the Hausgeld.
  Such a cost is no spending: `scale.categories` and the age curve leave it as it is.
  The income tax takes the rent less its costs (§21 EStG): the AfA, the interest of the loans that
  name it in `finances`, its `upkeep` and the expenses that name it. The cash flows stay the same. A
  net loss lowers the other income of its year, then goes back and forward (`tax.loss_carryback`).
  Enter the rent and the Hausgeld both with or both without the costs that the tenant pays back
  (Nebenkosten). Leave the reserve of the owners (Erhaltungsrücklage) out of the Hausgeld with
  `property`: it is a cost only when the owners spend it. When you move into the flat, end the rent
  with `end_streams`. A `set_stream` with `factor: 0` keeps the rent active and reads as a vacant
  month, so the costs still count. A sale of the property ends the streams that name it. A rent
  cannot take `taxable: false`.
- `taxable` (default true): `false` marks `other_income` that is tax-free and outside the
  Progressionsvorbehalt, for example the Gründungszuschuss (§3 Nr. 2 EStG, not in §32b). The
  Kindergeld needs no stream: `person.children_born`. Enter the Elterngeld of your notice as such
  a stream for now: the simulation leaves its Progressionsvorbehalt out.
- A business (`kind: self_employed`) pays `amount`, the profit of a month before the income tax
  and before your own social insurance, net of the Umsatzsteuer. It is other income in the income
  tax, without a flat amount for work expenses. A loss offsets the other income of its year, and
  the rest carries forward. Each month the simulation keeps back the tax of the profit as if it were
  earned all year, for the advance payments (Vorauszahlungen). The December settlement pays the
  difference. `hebesatz` (only on this kind, at least 2, that is 200%) is the
  Gewerbesteuer-Hebesatz of the municipality of a trade business, `4.1` for 410%. The trade tax
  (Gewerbesteuer) is charged in December, and four times its base amount comes off the income tax
  (§35 EStG). Up to 400%, that pays it back. Leave `hebesatz` empty for a Freiberufler, who owes
  no trade tax. In a month with a business and without a salary or ALG1, the business pays the
  social insurance of `tax.self_employed` (see `assumptions.yaml`). Then a member of the statutory
  health insurance (`pkv: false`, or from `tax.gkv_from`) pays the whole health and care rates as a
  voluntary member, on the profit and the other income ([How the simulation
  works](models.md#the-statutory-health-insurance)). The base is at least a third of the monthly
  Bezugsgröße (1,318.33 € in 2026), even in a month of no profit or a loss. So a phase with a
  business needs no `expense` stream for this insurance. A private member pays the `health` streams
  in full: no one pays a subsidy. A business is off in a phase with a `factor` of 0 or a
  `scale.salary` of 0. Beside a salary or ALG1, a business pays no social insurance of its own. A
  business paid every n months pays the social insurance on a part of 1/n in every month in which it
  runs. Use `rv_voluntary` only in phases without a compulsory pension insurance (§7 Abs. 1 SGB VI).
  An app before this kind does not load a plan with it.
- A payment that makes up for the deduction of an early pension (§187a SGB VI, from the age of 50)
  is an `rv_voluntary` stream of one month: `start` its month, `end` the month after, `amount` the
  payment from the pension insurance below 0, also in a month with a salary. It counts that month
  as insurance time, which the payment does not ([How the simulation works](models.md#each-month)).
- A savings plan (`kind: savings`) pays `-amount` from the cash into an asset in the months that
  `every`, `start`, `end` and `phases` give, times `factor`, its index and `scale.savings`. `into`
  (only on this kind) names an `equity`, `fixed_income`, `gold` or `crypto` asset. Without it, the
  plan buys the equity of the depot. Into an `equity` asset it buys at its `teilfreistellung`,
  without `into` at `tax.teilfreistellung`. It ignores the cash buffer. When the cash of the month
  does not cover the whole rate, the plan skips it, as a broker skips an execution: no catch-up, and
  the plan is not deleted after misses. A marker names the first month that skips it (half of
  the paths in Monte Carlo). Its default `index` is `null`, nominal as a broker runs it, so the
  roll forward leaves its amount alone. `index: cpi` follows the prices. A yearly increase
  (Dynamisierung) is an index with a spread of 0, for example `dynamik: {mean: 0.03, stdev: 0}`
  and `index: dynamik`. It steps each January, not on the anniversary of the plan, and a roll
  forward starts it at 1 again. A plan takes no `cat`, `health`, `of`, `share`, `repays` or
  `taxable: false`. `after_sale_of` and `tags` work as for every stream, and so do `set_stream`,
  `end_streams` and `add_stream`. An app before this kind does not load a plan with it.
  Purchases of the year owe the Vorabpauschale by twelfths (§18 Abs. 2 InvStG). Gold and crypto
  start a holding period per purchase month.
- A disability insurance (`kind: bu`, a Berufsunfähigkeitsversicherung) pays `amount`, its
  monthly benefit, from the month after the onset of a disability (`assumptions.disability`), as
  long as you are under `until_age` (default 67, the end of the contract). `premium` (default 0,
  at most 0, only on this kind) is the monthly premium: you pay it up to the month of the onset
  and under `until_age`. 0 while an employer pays it. Its default `index` is `null`, a benefit and
  a premium that the contract fixes in euros; `index: cpi` or an index of `indices` makes them
  grow, and the roll forward then changes both. `start`, `end`, `cat`, `tags` and `after_sale_of`
  work as for every stream; `phases`, `factor` and `every` are rejected (a contract runs by your
  age). A `set_stream` with `premium` changes the premium from its month (your own premium after
  you leave the employer), `end` or `end_streams` lets the policy lapse: no premium from then and
  no benefit of a later onset. A benefit that pays already runs on to `until_age`, and a row that
  starts after the onset pays none. The benefit is taxed at its Ertragsanteil and counts for a
  voluntary member of the statutory health insurance. The spending rule does not cut it. An app
  before this kind does not load a plan with it.

## `data/actuals.csv`

The CSV files below start with a header row. Each line has one cell per column, and a number has
a decimal point and no thousands mark. A file that Excel saves as `CSV UTF-8` reads too. If you
edit a file by hand and a line does not read, the page that reads the file shows the file and
the line instead.

`month,category,amount`: the spending of one month in one expense category (`cat` of the
streams, or a category of its own such as cash), negative like the streams. `month` is
`YYYY-MM`. One row per month and category, sorted. The `Spend` page writes it from what you type
(the grid or the quick add), and creates the file with the first saved month. A bank import can
write the same rows later. Rows of one month and category add up when read. A category without a
row in a month is not recorded, but a 0 is.

## `data/history.csv`

`date,asset,value`: the observed values of the assets, one row per asset and day (long format),
the date as `YYYY-MM-DD` and the value in euros with cents. A property row holds the full value, a
loan row the negative balance. The `Snapshot` page appends rows with `Record`, and so does a new
value in a table of the Assets page. A saved price, and a fetch that changes the price of gold or
Bitcoin, append the market value of the assets whose securities all have a price. Each of them
also sets `value` and `asof` in `assets.yaml`. `Rename` on the Assets page renames the asset in
its rows and keeps every other character. `Correct a recorded month` on the Snapshot page changes
the value of a row or removes the row, and keeps every other row as it is. Every write leaves the
line ends LF (`\n`), also in the rows that an earlier version appended with CRLF. The pages read
the value in `assets.yaml` at its `asof` (the simulation start without one) as one more row.

## `data/prices/<security>.csv`

`date,close`: the prices in euros of one unit of a security, one row per date, sorted, for
example `prices/IE000WORLD05.csv` or `prices/XAU.csv`. The file name is the ISIN or the symbol.
The section `Prices` of the Snapshot page writes it, from a price that you type (also a past
one) or from an imported price history, and so does `dagobert prices import`. An import of a day
that the file holds replaces that price. The market value of the open lots of an asset uses the
last price of each security. Gold (`XAU`) and Bitcoin (`BTC`) without a newer price take the last
month of their series. If you edit the file by hand, write the date as `2026-09-18` and the price
with a decimal point. A line that does not read gives an error with the file name and the line
number, for example `prices/XAU.csv:3: no price: ...`.

## `data/series/`

The months of the external series that a fetch or an import added: `<name>.csv` as
`month,value,provisional`, for example `series/vpi.csv`. A provisional month (`1`) is one that the
source can still change. Only the [Data](data.md) page (a fetch or an import) and the command
`dagobert series` write the folder. It holds no records of yours, and an export leaves it out.
`msci-world.csv` and `bitcoin.csv` must not be passed on: their terms allow no redistribution.

## `data/scenarios/*.yaml`

- `name` (required: the name in the results, the tabs and the summary table; two scenarios of one
  name show their file names too), optional `note`, `extends` (the file name of the parent scenario
  without `.yaml`), `abstract: true` for a template that only serves `extends` (`run` skips it
  with a note, and stops with an error when you name only templates). `run` also stops when two
  of the files that you name have the same file name in different folders, such as `a/plan.yaml`
  and `b/plan.yaml`: the report tells the runs apart by the file name. The `note` says what the
  scenario stands for. It shows on the tab of the scenario in the report and with the scenario on
  the Explorer, Cashflows and Flows pages, not in the console summary. A child does not take the
  note of its parent.
- `phases`: `[{from, phase, id}]`, each `phase` one of `phases` of `assumptions.yaml`. Parent and
  child phases merge and sort by date. A scenario that runs needs a change in or before the month
  of `start`, its own or of a parent: no phase holds before the first change. A template can leave
  it to its children. The migration to schema 3 wrote `{from: <start>, phase: work}` first into
  the first file of the chain of a scenario without one, after `overrides.shift`, as schema 2 ran
  `work` before the first change. When another scenario of that file has an earlier change, the
  item starts in that month, and the other change wins in it. A new scenario without a parent
  starts in the first phase from `start`.
- `events`: parent events plus child events. Each event has `at` and an optional `note`.
  Events and phases take an optional `id`: the address for `overrides.shift` and
  `overrides.events`. Items that belong together share one, for example the phase that
  ends a job and its severance.
  An `end_streams`, `set_stream` or `add_stream` event dated before `assumptions.start`
  applies in the first month. Any other event before the start is an error at its line: remove
  it together with the asset or the payment that it stands for. So is a `fund_policy`, or the
  `bav` part of a `severance`, after the `matures` month of its policy.
  - `sell`: `asset` (a property, gold or crypto), `costs` (a share of the price, default 0),
    `then` with `{repay: <loan id>, amount}` (`amount` default `all`) or `{invest: portfolio}`
    (what is left of the proceeds after the repayments, the cash buffer stays).
    `when: {age, liquid_below}` instead of `at` makes the sale conditional per path: it sells at
    the first condition met. `liquid_below` is in start-year euros and follows the consumer prices
    of the path. A conditional sale cannot repay a loan. A property takes `price` (default: its
    current value; 0 gives it away: a gift is no sale, so `taxable` is an error), `price_stdev`
    (relative spread per path, default 0, lognormal around the price, so no price falls below zero),
    `taxable` (default false: a private sale within ten years, §23 EStG) and `end_tagged` (default
    true). A `taxable` sale adds the proceeds less its basis to the private sales of the year:
    `bought_for` less the AfA that a let property took (§23 Abs. 3 S. 4 EStG). The prepayment
    penalty of a loan that `then` repays lowers the gain too. Without `bought_for` it adds nothing.
    A home that the owner lives in is free (§23 Abs. 1 S. 1 Nr. 1 S. 3), so leave `taxable` off for
    it. With `bought`, or for a property of a `buy_property`, a `taxable` sale counts only up to 120
    months after the purchase (`property_sale_months` of the tax year). A sale ends the streams that
    name the property in `property`, and with `end_tagged` those that share a tag with it. A gold or
    crypto asset takes `share` instead (above 0 and at most 1, of the
    holding in each path, default 1). The sale takes the oldest units first and ends no streams.
    The gain or loss of the units within the holding period joins the private sales of the year.
    The §20 part pays the flat tax at once (see `gold` and `crypto` in `assets.yaml`).
  - `buy`: `asset` (gold or crypto), `amount` (above 0) in euros from cash, nominal at the event
    date, at the price of the month. It is the only way the engine buys gold or crypto: a surplus
    and the allocation never go there.
  - `buy_property`: a property bought from cash and liquid assets, the down payment taken like a
    deficit (fixed income, then equity, then gold and crypto). Fields:
    - `property`: `id` (required), `name`, `growth` (return class, default `property`), `upkeep`
      (yearly share of the value, default 0: for a flat the inside of the flat, as the Hausgeld
      pays for the building), `tags` (a sale ends the streams that share one), `building_share`
      and `afa` as for a property of `assets.yaml`, needed when a rent names it. Its loan
      finances it.
    - `price` (above 0): euros, nominal at the event date. The property is worth it on every path
      and grows from the month of the event. Its `bought_for` is the price with the tax and the
      costs.
    - Exactly one of `land` and `transfer_tax`. `land` is the code of the Bundesland, `BW` to `TH`
      (ISO 3166-2:DE without `DE-`): the Grunderwerbsteuer of that Land on the event date, from
      the dated table `src/dagobert/data/grunderwerbsteuer.yaml`. `transfer_tax` is a share
      instead, for example 0 for a purchase from a spouse, parents or children (§3 Nr. 4, 6
      GrEStG).
    - `costs` (share of the price, default 0): notary and land register about 1.5%, the
      buyer's share of a broker up to 3.57% (§656c, §656d BGB).
    - `loan` (optional): `id` (required), `name`, `balance` (below 0), `rate`, `annuity`,
      `fixed_for` and `prepayment_penalty` (default 0), as for a `loan` asset. `fixed_for` is the
      number of months of the fixed rate from the event, so a `shift` moves its end too. Empty,
      the rate and the penalty hold for the whole term. The ten years of §489 Abs. 1 Nr. 2 BGB (see
      `loan`) start at the event. The first annuity is due a month after the event. The
      loan must not exceed the price with the tax and the costs.

    The ids of the property and of the loan are new: no asset and no other purchase has them. A
    dated sale, a `repay`, a `then: repay` or a stream with `repays` names them only after the
    month of the event, and a conditional sale waits for it. Such a stream names them from the
    first month in which it pays: from its `start` (of an `add_stream` not before the event) in a
    phase of its `phases`. So `phases: [retired]` without `start` names them from the first
    change to `retired`. One that never pays names nothing. The Grunderwerbsteuer counts in the
    taxes of the run, the costs in its spending, both as one-offs. A purchase that lies before a
    new start refuses the roll forward. After the real purchase, add the property and the loan to
    `assets.yaml` (the loan with `fixed_until` and `asof`) and remove the event.
  - `repay`: `loan`, `amount` (default `all`).
  - `severance`: `gross`, nominal at the event date. Optional `bav: {policy, amount}` pays
    that part (above 0, at most `gross`) tax-free into a `bav` asset (Vervielfältigung, §3 Nr. 63
    S. 3 EStG) and taxes only the rest. The engine does not check that amount against the limits
    of §3 Nr. 63.
  - `fund_policy`: `policy`, `amount` (above 0) from cash into a `bav` asset with `basisrente:
    true`. The payment lowers the income tax of its year like a `premium`. A company pension takes
    no payment of your own. Schema 4 had `deductible: true` for this. The migration to schema 5
    removes the key. If only payments with `deductible: true` fund a policy, the migration sets
    `basisrente: true` on it and adds a comment. It does this only for a policy that pays an
    annuity, has no `contribution` and no `conversion`, and gets no severance. Your own comments
    stay. If a payment without `deductible: true` also funds the policy, or the policy cannot be a
    Basisrente, the migration stops, and the error names the event. If the policy is a
    Basisrente, set `basisrente: true` on it, else remove the event. Then open the data directory
    again.
  - `lump_sum`: `amount`, signed: above 0 it pays into the cash, below 0 out of it. `taxable`
    (default false) adds the amount to the other taxable income of the year.
  - `inheritance`: `from` (required: the name of a relative of `person.relatives`, or a list of
    names), `cash` (nominal at the event, like a `lump_sum`, default 0: also the net proceeds of
    a property of the estate), `equity` (optional: `{value, cost_basis}`, the securities, `value`
    in euros of the start, `cost_basis` what the relative paid for them, nominal), at least one of
    the two. `at` is optional: empty, the inheritance comes at the death of the relative, drawn
    for each path from the life table (`fixed` takes the median month, the first in which less
    than half of the relatives of that age are alive), with a list at the later death of them.
    Beyond the end of the run, a path gets nothing. The engine pays the Erbschaftsteuer by the
    relation of the relative who died last, nominal (the constants are not indexed), with the
    acquisitions from that relative of the ten years before (§14 ErbStG). No income tax and no
    health insurance. The securities join the depot with the cost basis of the relative (§20 Abs.
    4 S. 6 EStG). The roll forward changes the `cash` of an inheritance without `at` by the
    consumer prices. Update the `value` of the securities after a roll forward.
  - `gift`: as `inheritance`, with `at` (required) and one relative in `from`, without the
    Erbfallkosten-Pauschbetrag of 15,000 €. Where an inheritance without `at` from the same
    relative draws the death before the gift, the gift joins that inheritance on that path. A gift
    before a new start does not refuse the roll forward: the roll moves it into `given` of its
    relative.
  - `write_off`: `asset`, an equity asset that leaves the depot without proceeds and without
    tax, for example a share plan forfeited without payment. The depot is one pool, so the engine
    takes out the start value of the asset at the equity index of the date, and its basis, each
    at the `teilfreistellung` of the asset.
  - `end_streams`: `tags`, `names` (both default empty), at least one of them.
  - `set_stream`: `name` with a new `amount`, `gross`, `premium` or `factor` (at least 0, in every
    phase), at least one of them. `gross` sets a salary or a pension, `amount` any other stream,
    neither ALG1 nor a salary with `of`, `premium` (at most 0) only a `bu`; a `bu` row refuses
    `factor`. The row must stay valid: an expense at or below zero. It changes the row of the name
    that runs in its month, else the next row that starts; a later row, such as a raise, keeps its
    own values. In a concrete scenario a `set_stream` after the `end` of every row of its name
    changes nothing, so it is an error at its `at`.
  - In a concrete scenario every name and tag of `end_streams` and `set_stream` belongs to a
    stream of `cashflows.yaml` or of an `add_stream` event of the scenario or its parents. An
    unknown one is an error at the line of the event, or of the `events` override that sets it.
    So a removed stream or tag refuses the save until the event changes too. `Rename` on the
    Cashflows page changes the name of a stream in the events too. A template leaves the check
    to the scenarios that extend it.
  - `add_stream`: `stream` with the fields of a stream above.
- `drop`: ids of phases and events of the parents that the scenario leaves out, for example
  `drop: [flat-sale]`. It takes every phase and event of the id in the files above, and with
  them their `shift` and `events` overrides of the id: an override follows its item. The file
  can then write items of its own with that id, which those overrides do not move. An id that
  no file above keeps is an error at its line: a `drop` without `extends`, or an id that a
  parent dropped already. The drops apply before the overrides, so an override of the id in the
  dropping file or below it needs an item of the id that is left (`no event or phase with this
  id`). An event of a parent that names a stream of a dropped `add_stream` is an error at the
  line of the event that names the scenario and its drops: `(for scenarios/child.yaml, whose
  chain drops side)`.
- `overrides`: deep-merged into `assumptions`, for example `{inflation: {mean: 0.04}}`. Dicts
  merge key by key, and lists (glide paths, hazards) are replaced whole. A scenario with one more
  child sets `person.children` and `person.children_born` with every row, also the rows of
  `assumptions.yaml`. A `shift` moves no birth. `phases` cannot be
  overridden. Three keys change the scenario instead (`loader.adjust`):
  - `events: {<id>: {<field>: value}}` sets a field on every event of the group that has it. A
    nested mapping such as `loan` or `property` of a `buy_property` is replaced whole, so it needs
    all its fields.
  - `shift: {<id>: months}` moves `at` and `from` of every item of the group by whole months,
    below zero earlier.
  - `assets: {<asset id>: {<field>: value}}` sets a field of an asset.

  The `Overrides` tab of the Scenarios page edits every key, the last three as tables of rows. In
  a file an unknown id or field is an error. The Explorer skips them, because its sliders reach
  every chosen scenario. A value of the wrong shape is an error with its file and line:
  `shift: {retirement: x}` or `shift: {retirement: 2.5}` (months must be a whole number; earlier
  versions rounded a fraction),
  `events: {car: 5}` (needs fields). The ids
  of the full example include `flat-sale` (a sale and the repayment from it), `job-loss` (the
  change to `unemployed`, the severance and the end of the old salary), `retirement` (the change
  to `retired` and the rent of a smaller flat) and `car` (two new cars).

## `data/app.yaml`

Written by `Set as default` of the Explorer and by `Save` of the main scenario on the Scenarios
page, and changed by a rename or a delete there: `scenarios`, the file stems of the scenarios that
the Explorer opens with. The first one is the main scenario, which the pages that show one scenario
show. A stem of no concrete
scenario is ignored, an empty file counts as none, and an unknown key is an error at its line.

`features_off` (optional, default none) lists the parts of life that the plan does not model. The
app hides their pages, kinds, event types, fields, columns and sliders, as long as the inputs hold
no data of them. The ids: `tracking` (the Snapshot and Spend pages, trades and prices),
`gold_crypto`, `property` (property, rental and loans), `self_employment`, `children`, `estates`
(inheritance and gifts), `job_loss` (ALG1 and severance), `disability`, `deductions` (deductions
and the Basisrente), `spending_rules` (the spending rule beyond the cut, and VPW), `care` and
`allocation` (the allocation and its glide path). An unknown id is an error at its line. The
[Features](features.md) page writes the key and removes it when the list is empty. The key changes
no simulation: the defaults of a hidden field still act. A new plan of the quick start lists every
id that it does not use, and the simple example lists the ten that it does not use.
