# How the simulation works

Dagobert computes your plan one month at a time, from the simulation start to the end age of the
plan (105 by default). This page explains what it computes, the three models of the markets, and
the meaning of the results.

## The values at the start

The simulation starts from the values on the [Assets](assets.md) page. A value without a date
(`as of`) counts at the simulation start. A value with a date before the month of the start moves
forward to the start:

- A loan pays its scheduled payments.
- A company pension (bAV) and an Altersvorsorgedepot grow by the mean return of their class, less
  their cost. They also take the contributions of the months between, in the phases of your
  scenario: the payments of the employer, a salary conversion with the subsidy of the employer,
  and the yearly contribution of the depot with its Zulage.
- A term deposit counts with its interest so far.

All other values count as they are. A value with a date in the month of the start or later also
counts at the start, as it is. The simulation then adds the months from the start up to that date
once more: their returns, payments and contributions. A `Roll forward` on the
[Overview](overview.md) to a start after that date ends this overlap. The [Snapshot](snapshot.md)
page estimates the same values for today.

## Each month

In each month, the simulation does these steps in this order:

1. It applies the events of the month: first the inheritances and gifts, then the others, such
   as a sale or a severance payment.
2. It adds the returns of the month to your assets.
3. It pays the loans: interest and repayment.
4. It pays the streams: salary, profit and pension in, expenses out, with the withholding tax and
   the social insurance of a salary or a business. A salary conversion goes from the gross salary
   into its company pension. With VPW, the flexible categories pay last, from what the budget and
   the other streams leave (see `Spending rules`).
5. It pays the savings plans of the month from the cash into their assets.
6. If the cash is not enough, it covers the gap from your assets.
7. If your assumptions set an allocation, it rebalances your investments towards the target share
   of fixed income for your age. It does this every `rebalance_every` months, 12 by default.
8. In December, it settles the taxes of the year, like the yearly tax assessment. A refund goes back
   to your cash.
9. It invests what is left above your cash buffer, unless `invest_rest` is off.

To cover a gap, the simulation takes money in this order: cash, fixed income, equity, then gold
and crypto. When it sells equity, it sells enough to pay the tax on the gain too. A term deposit is
locked until it matures. A property is sold only by an event of your scenario.

The taxes follow the German rules of 2026. They include the income tax, the solidarity surcharge
(Soli) and social insurance. They also include the flat tax on capital income (Abgeltungsteuer)
with its allowances, the Vorabpauschale of funds, and the tax on private sales of property, gold
and crypto. The Vorabpauschale is a part of the expected gain of a fund that is taxed each year
before a sale. A fund share that you buy during the year owes it only for the months that you hold
it: one twelfth for each month from the month of the purchase. A sale takes the oldest shares
first. A part of the gains of a fund is free of tax (Teilfreistellung): 30% of an equity fund by
default, and the rate of its class for each depot that sets `teilfreistellung`. Shares get none,
but they pay the Vorabpauschale like a fund. The depot grows by the total return and pays out no
dividends, so the Vorabpauschale stands in for the tax on them. A later sale credits it. The
simulation applies the 2026 rules in every year. It raises their amounts, such as
the tax-free allowance, with the consumer prices of each path, as if the law adjusted them every
January.

If you are a member of a church (`tax.church`), the church tax adds 8% or 9% of the income tax.
The rate depends on the Land where you live (`tax.land`). On capital income, the flat tax then
falls a little and the church tax comes on top. The church tax that you pay in a year lowers your
taxable income. The employer withholds it with the salary in the year itself. The rest comes with
the December settlement and lowers the taxable income of the next year.

A salary conversion (Entgeltumwandlung, `conversion` of a company pension) takes a part of the
gross salary into the policy. Up to the limits of the law, that part pays no income tax and no
social insurance, and the employer adds a subsidy. The lower gross also gives fewer pension points,
a lower unemployment benefit and a lower subsidy of the employer to a private health insurance.
The simulation applies the rules of a Direktversicherung, a Pensionskasse and a Pensionsfonds to
every company pension. A Direktzusage or an Unterstützungskasse has no limit for the income tax
and no subsidy by law.

The statutory pension follows the consumer prices of each path, like every amount in euros of
the start. `pension_growth` adds a real growth on top of that. So a path with high inflation keeps
the buying power of the pension.

With a private health insurance, others pay a part of your premium. The payments of the month
decide who pays, not the name of the phase. In a month with a salary, your employer pays 8.75% of
the salary for the health part and 1.8% for the care part. The salary counts up to the
contribution ceiling of the health insurance, and the employer pays at most half of each part. In
a month with unemployment benefit (ALG1), the employment agency pays the premium up to a limit,
for the days that ALG1 pays. In a Sperrzeit it pays nothing.
The pension insurance pays 8.75% of your pension, at most half of the health part.

## What lowers the income tax

The December settlement takes these costs off your income before the tax:

- Work expenses (Werbungskosten). The tax takes 1,230 € a year from a salary in any case (the
  Arbeitnehmer-Pauschbetrag), or `tax.werbungskosten` when that is higher. A year with fewer months
  of salary takes the share of its months. The monthly withholding does not know your own costs,
  so the settlement refunds the difference.
- Special expenses (Sonderausgaben): the church tax paid in the year, donations up to 20% of the
  income, and 80% of the costs of childcare, at most 4,800 € a year for each child under 14. The
  tax takes at least 36 € a year. A refund of church tax beyond what the year paid raises the
  taxable income after the carried losses: they do not offset it.
- The pension insurance and the premiums of a Basisrente, together up to a maximum (30,826 € in
  2026, less the half that an employer pays).

These costs come off the tax itself: 20% of household services, such as a cleaner, at most 4,000 €
a year, and 20% of the labour of a craftsman, at most 1,200 € a year (§35a EStG). The tax does not
fall below zero, and a rest does not carry over. The state grant of an Altersvorsorgedepot comes
after these credits, so they never take it.

An expense stream with `deduct` holds such a cost: its cash flow stays an expense, and the tax
falls. A Basisrente takes a monthly `premium` from the cash. Its pension is taxed like the
statutory pension: at the share of the year in which it starts, 84% for 2026. Unemployment benefit
(ALG1) is free of tax, but it raises the rate on your other income. In a year without a salary,
the 1,230 € of work expenses come off the benefit first.

You get one state grant of the Altersvorsorgedepot, however many depots you have. From 2027 each
child whose Kindergeld you get adds up to 300 € a year to it.

## Children

Each row of `person.children_born` is a child. A child counts from the month of its birth up to
its 18th birthday. For a child in education, `until` ends it later, at most at its 25th birthday.
While a child counts, these rules apply:

- Kindergeld. The simulation pays 259 € a month (2026) for each child whose Kindergeld goes to you
  (`kindergeld`), in euros of the start. It is free of tax and of the health insurance. The
  Cashflows sheet shows it among the rows from the run.
- Child allowances. Each December the tax compares, for each child, the Kindergeld with the child
  allowances (Kinderfreibetrag and Betreuungsfreibetrag, 4,878 € a year for each parent in 2026).
  When the allowances save more, they come off the taxable income, and the tax adds half of the
  Kindergeld of the year. For one child, this starts at a taxable income of about 43,050 €. With
  `freibetrag: full`, you take the allowances of both parents against the whole Kindergeld. The
  tax checks the oldest child first, then each next one.
- Soli and church tax. Both always take the allowances, also when the Kindergeld saves more.
- Single parent. With `tax.alleinerziehend`, the Entlastungsbetrag of 4,260 € a year (2026), and
  240 € for each further child, comes off the income, a twelfth for each month with a child.
- Unemployment benefit. ALG1 pays 67% instead of 60% when a child counts in its first month.
- Altersvorsorgedepot. From 2027 each child whose Kindergeld you get adds up to 300 € a year to the
  state grant.

The child-raising years count for your pension when you raised the child (`erziehung`, on by
default). Each of the 36 months after the month of birth adds 0.0833 pension points to the points
of your salary. The sum stays at most at the points of a salary at the contribution ceiling. The
months up to the 10th birthday count as insured months for the 35 and 45 years of an early
pension. The simulation adds these months from the start on. The months before the start count
through `points` and `rv_since` of your Renteninformation. A pension stream with `gross` ignores
the points of the run, so the child-raising years change nothing there.

In the statutory health insurance, the care insurance adds the surcharge for the childless up to
the month of the first birth. A scenario with one more child sets `person.children` and
`person.children_born` in its overrides, with all rows. Enter the Elterngeld of your notice as an
`other_income` stream with `taxable: false` for its months.

## Unemployment benefit

An `alg1` stream pays unemployment benefit (Arbeitslosengeld, ALG1). The simulation computes the
amount from your last monthly salary, as the calculator of the Bundesagentur für Arbeit does: 60%
of a net salary, or 67% with a child. The amount stays the same in euros for the whole claim.

The claim is a number of days, and a month counts as 30 days. The claim starts in the first month
in which an `alg1` stream pays. Your age in that month sets its length: 12 months, 15 months from
50, 18 months from 55 and 24 months from 58. Each month of ALG1 uses 30 days. When no days are
left, the stream pays nothing, and a marker names that month.

A later time with an `alg1` stream pays the days that are left. It must start within four years
after the first month of the claim. If it starts later, it pays nothing, and a marker says so. A
time that starts within the four years runs on after them.

A Sperrzeit (`sperrzeit: true`) follows when you quit or sign an Aufhebungsvertrag. For 12 weeks
after the job ends, the stream pays nothing. In these weeks the employment agency pays no private
health premium and no pension contributions, so you get no pension points. You stay a compulsory
member of the statutory health insurance. The claim also loses at least a quarter of its days. So
a claim of 12 months pays for 9 months, and the first payment comes in the third month.

A course with a Bildungsgutschein (`training: true`) pays the same ALG1. Two days of the course use
one day of the claim, but a course never takes the claim below three months. After a course of six
months or longer, a rest below three months grows to three months, once.

The Cashflows sheet shows the monthly ALG1 of a phase. It does not show the Sperrzeit or the end of
the days: the rows from the run show what the simulation pays.

## The statutory health insurance

In the statutory health insurance (GKV: `tax.pkv` off, or from `tax.gkv_from`), the payments of the
month decide how you pay the health insurance (KV) and the care insurance (PV):

- In a month with a salary or with unemployment benefit (ALG1), you are a compulsory member, also
  in a Sperrzeit. The salary pays its share, and the employment agency pays for the ALG1. Your other income pays
  nothing, except a company pension (see below). A profit pays too if you also get a pension or a
  company pension.
- In a month with a pension, you are a compulsory member as a pensioner (KVdR) if `person.kvdr`
  is on, which is the default. You pay half of the health rate and the whole care rate on the
  pension. A company pension and a business beside the pension pay too. Rent and capital income
  pay nothing.
- Every other month makes you a voluntary member. This is the case in the years between your last
  salary and your pension, and after the start of the pension if `person.kvdr` is off. The KVdR
  needs nine tenths of the second half of your working life in the statutory insurance. The
  simulation does not test this, so set `kvdr` off if you do not reach it.
- A voluntary member pays on all income: a profit, rent and other taxable income, a Basisrente,
  the Altersvorsorgedepot, a company pension, and the capital income of the year before. The rent
  of a let property counts after its costs, as for the income tax (see Letting a property). The
  capital income counts after the Teilfreistellung and without the Sparer-Pauschbetrag, less 51 €
  a year. Kindergeld and other tax-free income do not count. A loss of one kind of income does not
  lower another kind. You pay on at least 1,318.33 € a month in 2026, so a month without income
  costs about 278 € with the care insurance of the childless. You pay on at most 5,812.50 € a
  month, the contribution ceiling.
- A company pension (bAV) is a Versorgungsbezug. A compulsory member pays the whole health and
  care rates on it, but only if it is above 197.75 € a month in 2026. The health part then takes
  197.75 € off. A voluntary member pays on all of it. A lump sum counts as 1/120 of it per month
  for ten years, from the month after the payout. A Basisrente (`basisrente` on the policy) is no
  company pension: only a voluntary member pays on it. A Basisrente pays a monthly pension. The
  law does not allow a lump sum, so the policy needs `payout: annuity`.

The health insurance fund sets the contribution of a voluntary member from the last tax
assessment. So the simulation takes the capital income of a year into the next year. In the first
year of a run, the capital income counts nothing. The simulation divides interest and the gains of
sales by the months of that year in the run. It divides the Vorabpauschale, which is the amount of
a whole year, and a one-off, such as the gain of a private sale, by 12. So the month in which a
run starts does not change what the Vorabpauschale adds in the next year.

Each Krankenkasse sets an extra rate on top of the general rate: the Zusatzbeitrag. You pay half
of it on a salary and on a pension. On all other income that pays, such as a company pension or a
profit, you pay all of it. Without `tax.kv_zusatz`, the simulation takes the average of the year.

### A change from the PKV to the GKV

`tax.gkv_from` is the month in which you leave the private health insurance (PKV) for the GKV.
Before this month the simulation uses the rules of the PKV: the `health` streams, the subsidy of
the employer, the employment agency or the pension insurance, and the deduction of the premium.
From this month it uses the rules of the GKV above. The `health` streams end in this month without
an edit. The tax withheld from a salary follows the insurance of each month. The tax settlement of
the year of the change deducts the PKV premiums before the change and the GKV contributions after
it.

The capital income of the last year in the PKV counts in the first year as a voluntary member. In
the December before a change to a voluntary member, the harvest of gains keeps the contribution of
the next year at its minimum (see Realizing gains). This limit applies only to a change in January.
Before a change in another month, the harvest does not look at the contribution.

The law decides whether you can change. Before 55, ALG1 or a salary below the
Jahresarbeitsentgeltgrenze makes a PKV member a compulsory member of the GKV (§5 SGB V). With ALG1
you stay in the PKV only if you apply for an exemption within three months, and you cannot revoke
it (§8 Abs. 1 S. 1 Nr. 1a SGB V). A plan in the PKV with ALG1 before 55 assumes this exemption, and
a marker says so. From 55, §6 Abs. 3a SGB V usually blocks the change for a person who was outside
the GKV in the last five years. The simulation does not refuse such a change, but a marker says
so. The KVdR needs nine tenths of the second half of your working life in the statutory insurance.
A late change seldom reaches it, so set `person.kvdr` off then.

To compare the two insurances, set `tax.gkv_from` in the `overrides` of one scenario, and keep a
scenario without it. The Explorer has no switch for it.

## A business of your own

A stream of the kind `self_employed` is the profit of a business: what is left of the revenue after
the business expenses, before the income tax and your own social insurance.

- The income tax treats the profit as other income. A loss lowers the tax on your other income of
  the same year. The rest of a loss carries forward to the next years (see Letting a property).
- Each month the simulation keeps back the tax on the profit, as if you earned the same profit all
  year. This stands in for the advance payments (Vorauszahlungen) that the tax office sets. The
  December settlement pays or refunds the difference.
- A trade business (Gewerbe) has a `hebesatz`. It pays the trade tax (Gewerbesteuer) in December
  on its profit above 24,500 €. Four times the base amount of that tax comes off your income tax.
  Up to a Hebesatz of 400%, this pays back the whole trade tax. A Freiberufler, such as a doctor, a
  lawyer or an architect, has no `hebesatz` and pays no trade tax. Whether your work is a trade is
  a question for you and your tax advisor.
- In a month with a business and without a salary or unemployment benefit, the business is your
  main work. In the statutory health insurance, you are then a voluntary member and pay the whole
  health and care rates yourself, on the profit and your other income (see above). The minimum
  applies also in a month of a loss. With a pension in the KVdR, the profit pays at the rates of
  the pension. In a private health insurance, you pay the whole premium: no employer pays a part.
- Your assumptions decide the pension insurance of a business (`tax.self_employed.rv`). Most
  self-employed people pay none today. Some trades must pay, and every self-employed person can
  apply. The regular contribution is fixed and half of it applies for the first years. These years
  count from the first month of the first business, or from the month that you set as `founded`.
  The other choice is a contribution on the profit, which is never half. Both earn pension points.
- From 2027 a business makes you eligible for the state grant of the Altersvorsorgedepot.

## Buying a property

An event of the type `buy_property` buys a property in its month. The simulation pays the price,
the Grunderwerbsteuer and the other costs from the cash. The Grunderwerbsteuer is the tax on the
purchase of land. Its rate depends on the Bundesland and on the date of the purchase. A loan of the
event adds its amount to the cash. Step 6 then covers the rest of the gap, as for any other gap.

- The property is worth the price on every path. It grows with its return class from the month of
  the purchase, and its upkeep starts in that month.
- The loan pays its first annuity in the month after the purchase, with a month of interest.
- The Grunderwerbsteuer counts in the taxes of the year, the other costs in the spending. Both are
  one-offs. So the net worth falls by the tax and the costs. The price moves from the cash into the
  property, and the loan adds a debt of the same size as the cash it brings.
- A sale of the property is a private sale only when you mark it as `taxable`. A home that you live
  in is free of this tax, so leave `taxable` off for it. The simulation taxes a `taxable` sale only
  up to ten years after the month of the purchase. The gain is the price of the sale less its costs,
  less what the purchase cost with the tax and the costs, less the depreciation of a let property.
- A sale on a condition, for example at an age, waits for the purchase. It cannot repay the loan
  of the purchase, so that loan runs on after such a sale.
- The spending rule compares your liquid wealth with its reference wealth (see below). A purchase
  takes liquid wealth, so it can switch on the cut of your flexible spending. The simulation does
  not reset the reference for a purchase. If the cut is not what you want, change
  `spending.trigger`.

The guide [Buy or rent](buy-or-rent.md) shows how to compare a purchase with renting.

## Letting a property

A property is let in a month in which a rent names it: an `other_income` stream with the
`property` of the property. The rent pays into the cash like any income. For the income tax the
simulation takes the rent less its costs (Werbungskosten, §21 EStG):

- The depreciation of the building (AfA): `afa` of `bought_for` times `building_share` a year, a
  twelfth in each let month. The land is not depreciated. The AfA ends when it reaches the cost of
  the building. A property of `assets.yaml` took the AfA of the months from `bought` to the start,
  as if it was let since then.
- The interest of each loan that `finances` the property. The loan of a purchase finances its
  property.
- The `upkeep` of the property and the expenses that name it, such as the Hausgeld. These costs
  are not spending: `scale` and the age curve do not change them.

The tax law counts the depreciation in euros of its year, so its value falls with the prices. When
the rent stops, by its dates, by `end_streams` or by a sale of the property, the costs stop
counting too. A sale ends the streams that name the property. The month of the sale takes no AfA,
though the tax law counts it: a twelfth of the AfA of a year. A `taxable` sale within ten years of
`bought` subtracts the AfA taken from the cost of the purchase, so the gain grows by it. A
prepayment penalty of a loan that the sale repays lowers the gain.

A loss, the costs above the rent, lowers your other income of the same year, for example the
salary. What is left of a loss carries forward to the next years (Verlustvortrag, §10d EStG). It
lowers your income of the next year before the Sonderausgaben, such as the health insurance, also
in a year whose income stays below the tax-free amount. The carried losses stay in euros of their
year. In a year in which the flat tax on capital income is refunded at your personal rate
(Günstigerprüfung), a loss first offsets that capital income. A business loss carries forward the
same way. `tax.loss_carryforward` holds the losses of your last tax notice, and the roll forward
writes there what the plan carries to the new start.

In the statutory health insurance, a voluntary member pays on the rent after its costs, at least
0: a loss of the rent lowers no other kind of income.

## Realizing gains

With `tax.harvest` on, the simulation realizes gains of your equity each December. It sells the
fund shares whose gains fit into the tax-free room of the year and buys them back at once. The
number of shares stays the same, but their cost rises, so a later sale pays less tax. The law
allows a sale and a purchase of the same fund on the same day (BFH VIII R 32/16). Buy back at the
next market price, not in one order at the same price: no court decided that case.

The tax-free room of a year has two parts:

- The Sparer-Pauschbetrag that your other capital income leaves. The Vorabpauschale of a depot
  above about 64,000 € uses it up in each year in which the market grows.
- The part of the Grundfreibetrag (12,348 € in 2026) that your other income leaves. This part
  exists in a calendar year without pay or with a small income. The bank withholds the flat tax on
  it, and the December settlement pays it back (Günstigerprüfung).

The room counts the gains after the Teilfreistellung. In a year without other income, a fund with
a Teilfreistellung of 30% can realize 19,120 € of gains free of tax in 2026.

The harvest never uses up carried losses. So it realizes nothing while you carry losses of capital
income from earlier years: they come off the next sale first. It uses no part of the Grundfreibetrag
while you carry a loss of the income tax (Verlustvortrag), for example of a let flat. That loss
lowers the tax of a later year at your full rate. A year with a severance payment taxed by the
Fünftelregelung realizes the Sparer-Pauschbetrag only.

In the statutory health insurance, the health fund counts the capital income of a year in the
contribution of the next year. If you are a voluntary member in the next January, the simulation
realizes only so much that this contribution stays at its minimum. With a salary, ALG1 or the KVdR
in January, the full room applies. A year in which you live from sales of your depot usually
leaves no room.

The simulation decides your status in January in a simple way:

- Only your phases and the dates of your streams decide it. A sale that switches a stream off or
  on, and other events, do not change it.
- If your ALG1 continues into January and ends later in that year, the full room applies. The
  months of voluntary membership after the ALG1 then pay contributions on the realized gains.

No cash moves. The tax on your unrealized gains falls, so your liquid wealth rises by the tax that
you save: about 18.5% of the realized gain at a Teilfreistellung of 30%. A marker in the charts
shows the first December in which half of the paths realize gains, with their median gain. Gold,
crypto, deposits and fixed income realize nothing. Trading costs are left out.

## An inheritance or a gift

An event of the type `inheritance` or `gift` brings cash and securities from a relative. The
relatives are on the Assumptions page, each with the date of birth, the sex and the relation.

An inheritance without a month comes at the death of the relative. For each path, the simulation
draws that month from the life table of the relative, who is alive at the start. So the paths
receive the inheritance at different ages, and some receive it after the end of the plan, which
means never. The model `fixed` uses one path: it takes the median month, the first month in which
less than half of the relatives of that age are alive. An inheritance from two relatives, for
example from both parents with a joint will (Berliner Testament), comes at the later death. The
draw of one relative is the same for all events that name the relative. If the relative of a gift
dies before the month of the gift on a path, the gift joins the inheritance of that path.

The Erbschaftsteuer is the tax on an inheritance or a gift. The relation sets the tax class and
the tax-free amount (Freibetrag): 400,000 € from a parent, 200,000 € from a grandparent, and
20,000 € from a sibling, an aunt or uncle, a parent-in-law or another person. An inheritance also
deducts 15,000 € for its costs without proof. The rates rise with the amount, from 7% in class I
and from 15% in class II, up to 30% or 43%. Class III pays 30% or 50%. The tax adds all
acquisitions from one relative within ten years, also the gifts before the start. It subtracts
the tax on the earlier ones.

The amounts of this tax do not follow the consumer prices. The law has kept the tax-free amounts
since 2009, so the simulation applies them in nominal euros. Every other tax of the simulation
follows the consumer prices. So a far inheritance pays more tax than an inheritance of the same
buying power today. For example, an inheritance from a parent of 600,000 € in euros of the start,
received after 15 years at 2.2% inflation, pays 45,100 €. With amounts that follow the prices, it
would pay 20,350 €.

An inheritance is no income. It pays no income tax and no health insurance. The tax is paid from
the cash in the month of the inheritance. The securities join your depot. They keep the cost that
the relative paid for them, so a later sale taxes their whole gain.

## When you cannot work

The section `Disability` of the Assumptions page (tab `Rules`) adds the risk that you lose the
ability to work before the statutory pension age. The law calls this a full Erwerbsminderung: you
can work less than three hours a day. Each path draws whether and in which month this happens.
The model `fixed` draws nothing, but the field `Disabled from (what-if)` forces the month in every
path. That month must come before you are 67. Without the section, no path loses the ability to
work.

The yearly chance rises with age. The default curve starts at 0.044% at 20 and reaches 1.614% at
64. It comes from the pension insurance (DRV): 171,732 new disability pensions in 2024, on 38.6
million insured people of 15 to 64. That is 4.45 in 1,000 a year. The curve spreads this over the
ages so that the mean age at the start matches the mean age of the new pensions, 53.8 years, less
seven months. From age 40, about one person in five loses the ability to work before 67 with this
curve. The DRV publishes no rate for each age, so the curve is an assumption. Change it in the
table.

After the month in which you lose the ability to work, the plan does this:

1. Your employer pays the salary for six weeks: the month itself and the next one. A business
   pays its profit in these two months too.
2. From the third month, the salary, the profit, ALG1 and the payments of the employer into a
   company pension stop. The statutory health insurance pays sick pay (Krankengeld) for five
   months: 70% of the gross salary, counted up to 5,812.50 € a month, so at most 4,068.75 €, and
   at most 90% of the net salary. Your share of the pension, unemployment and care insurance comes
   off it, about 12.4% (13.0% without children). The sick pay is free of income tax, but it raises
   the tax rate on your other income of the year (Progressionsvorbehalt). A business pays sick pay
   only with the option `Sick pay in the GKV`, 70% of the profit. Private health insurance pays no
   Krankengeld. The plan leaves out a daily sick pay of a private tariff (Krankentagegeld): these
   five months come out of your savings.
3. From the seventh month, the pension insurance pays the disability pension (EM-Rente). It needs
   five years of insurance and three years of compulsory contributions in the last five years. It
   uses the pension stream from points on the Cashflows page, whatever its phases say. Its amount
   takes your points so far and adds the Zurechnungszeit: the months up to about 67 (66 years and
   3 months in 2026, 67 from 2031) count with the average points of your months since the start of
   your insurance. A month without contributions lowers that average. A pension that starts before
   62 is 10.8% lower, one between 62 and 65 loses 0.3% a month before 65. At the statutory pension
   age the old-age pension follows with the same amount. The tax and the health insurance treat it
   like a pension that starts in its year.

Without a pension stream from points, or without the three years of contributions, no EM-Rente
pays. The table `Needs attention` of the Overview names a plan with the section but no pension
from points. The Cashflows sheet shows the sick pay and the EM-Rente among the rows from the run,
in the phases in which the pension stream does not pay.

### A disability insurance (BU)

A private disability insurance (Berufsunfähigkeitsversicherung, BU) is a stream of the kind
`Disability insurance (BU)`, in its own tab on the Cashflows page. It holds the monthly benefit,
the monthly premium and the age at which the contract ends. You pay the premium up to the month in
which you lose the ability to work. From the next month, the premium stops and the benefit pays
until that age. It goes on when the policy ends later, for example when you leave the employer:
the insurer pays a running claim to its end. A policy that ends before you lose the ability to
work pays nothing, and so does one that starts after it. The benefit stays the same in euros,
unless the stream follows an index. The tax takes only a part of it, the Ertragsanteil, by the
years from its start to the end of the contract: 12% for 10 years, 21% for 20 years, 30% for 30
years. A voluntary member of the statutory health insurance pays on it. A member who pays the
rates of pensioners (KVdR) does not.

Many employers pay a BU for their staff. When you leave the employer, you can usually continue
the policy at your own premium, or let it lapse. The page
[Scenarios](scenarios.md#an-employer-bu-carried-forward-or-not) shows how to compare the two.

If the employer pays the BU through a company pension (a Direktversicherung under §3 Nr. 63 EStG),
the law taxes the benefit in full and the health insurance takes it as a company pension. The plan
taxes only its Ertragsanteil, so the tax comes out too low in that case.

## Investing the surplus

By default the simulation invests the rest. At the end of each month, after the December tax bill,
it keeps your cash buffer: `cash_buffer_months` times the expenses that you expect in a month. It
invests the cash above it. With an allocation, the glide path splits the money: the fixed-income
share for your age goes into fixed income, the rest into equity. Without an allocation, all of it
goes into equity. The buffer is a ceiling only. A month with a gap does not refill it, so your cash
is near zero once the gaps start. Every `rebalance_every` months the rebalancing moves your
investments back towards the target share. After a loss of equity in the last `skip_after_loss`
months, it sells no equity for this. The surplus and the rebalancing buy equity at the default
Teilfreistellung of the Assumptions page (30%), not at the rate of an asset.

If you switch `invest_rest` off, the cash above the buffer stays in cash. It earns the `cash`
return, and the interest is taxed each December. Then only your savings plans invest, and the
`invest` of a sale.

## Spending rules

The spending rule (`spending` in `assumptions.yaml`) changes your flexible spending by your liquid
wealth. Liquid wealth is your cash, deposits, fixed income, equity, gold and crypto, less the tax
on their gains. At the start of each month the rule compares it with a reference wealth, in real
terms.

- The cut: while the liquid wealth is below `trigger` times the reference, the expense streams of
  the `categories` pay the share `cut` less. A `trigger` of 0 switches the cut off. Then a path
  does not cut either when its money runs out.
- The increase: while it is above `ceiling` times the reference, they pay the share `increase`
  more. A month never cuts and raises at once.
- The reference with `base: start`, the default, is the liquid wealth at the start of the plan.
  The rule then acts in every month.
- The reference with `base: no_pay` is the liquid wealth when your pay stops. Pay is a salary or
  the profit of a business, of any amount. ALG1, a pension and other income are no pay, so put a
  side job in retirement into `other_income`. The rule acts only in a month after a month without
  pay. A month with pay, for example a bonus after the job, stops the rule for the month after it.
- After twelve months of pay in a row, the next month without pay takes a new reference. So a
  retirement after a career break and a new job compares with its own wealth, not with the wealth
  of the break.
- The increase needs `base: no_pay`. While you work, your wealth soon passes the wealth of the
  start, and the increase would raise your spending while you save.
- `reference` sets the reference of the start, in euros of the start. It counts with `base: start`,
  and with `base: no_pay` when the plan starts without pay. Without it, the reference is the
  liquid wealth of the start. Then a roll forward after a crash stops the cut, and a roll forward
  after a boom stops the increase. The roll forward changes a `reference` by the consumer prices.
- A path near a threshold can switch the cut or the increase on and off from month to month.

The rule is no Guyton-Klinger rule. It does not look at your withdrawal rate, and it never freezes
your spending for a year after a loss: your expenses follow the prices in every year.

### Variable percentage withdrawal (VPW)

VPW (`spending.vpw`) replaces the cut and the increase. It sets a budget for each year as a share
of your liquid wealth, and the share rises with your age. So you spend less after a bad year and
more after a good one, and you never need a cut slider. The method comes from the Bogleheads
forum.

- The rate of a year is the payment of an annuity (a fixed yearly payment that uses up a sum) at
  the start of each year, at a real growth of `growth` per year, over the years to `horizon_age`.
  At 3% and an age of 100, the rate is 4.95% for 30 years left. The rate is at most 10%, which it
  reaches 11 years before `horizon_age`.
- Choose `growth` by your allocation. Bogleheads takes a real growth of 5.0% for stocks and 1.8%
  for bonds. That gives 3.7% for 60% stocks and 40% bonds, and 3.4% for 50/50. A higher growth
  spends more now and less later.
- The budget is the rate of your age in January times your liquid wealth at the start of the first
  month without pay of a calendar year. Each month without pay spends a twelfth of it.
- The fixed flows of a month come out of the budget first: your pension, a rent and ALG1 go in,
  the other expenses, the loan payments, the premium of a Basisrente and the KV go out. The
  flexible categories spend the rest. So a pension above your fixed costs raises your flexible
  spending above the twelfth.
- The tax of a year comes in December. So each month of the next year spends a twelfth of that
  bill less. Over a year your spending then comes to about the budget.
- A lump sum of a policy or of an Altersvorsorgedepot, an inheritance, a sale and a purchase do
  not change the spending of their month. They change your wealth, and the budget of the next year
  follows.
- `floor` is the least that the flexible categories spend in a month without pay, in euros of
  the start. If the budget leaves less, the month pays the floor and sells for it. The floor only
  holds while a flexible stream runs: a phase in which no flexible stream pays spends nothing
  flexible.
- Each flexible stream pays every month by its share of the plan of the flexible streams, also a
  stream that pays every twelve months. The factor of a phase, the age curve and the slider of the
  category set this share.
- A month with pay spends the plan. The first month without pay of a year takes a new budget, and
  again after twelve months of pay in a row. A bonus after the job spends the plan in its month,
  and the next January counts it in the budget.
- VPW needs `base: no_pay`. It spends what the rate gives and has no upper limit.

The budget takes the liquid wealth after the tax on its gains, while Bogleheads takes it before
tax. The realized gains of `tax.harvest` lower that tax, so they raise the budget a little. A loan
counts outside the liquid wealth, but its payments come out of the budget: a mortgage in
retirement lowers your flexible spending. VPW has no bridge to the pension: your flexible
spending is lower before the pension and rises when it starts. ALG1 raises the flexible spending
while it pays, and it falls when ALG1 ends. The first year of VPW pays the tax bill of that year
on top of the budget. With VPW the chance to run out is the chance that your fixed spending and
the floor use up your wealth. It is small with a floor of 0 €.

## Savings plans

A savings plan is a stream of the kind `savings`. It pays a fixed rate from your cash into an asset
each month, or every `every` months, in its phases and between its `start` and `end`. `into` names
the asset: equity, fixed income, gold or crypto. Without `into`, the plan buys the equity of your
depot.

- The plan pays from the cash before the gaps are covered, and it does not care about the cash
  buffer. When the cash of the month cannot pay the whole rate, the plan skips the rate, as a broker
  does. It does not pay the rate later, and it does not sell other assets for it. A marker in the
  charts names the first month that skips the rate.
- The rate is nominal by default, as your broker runs it. With `index: cpi` it follows the consumer
  prices. For a yearly increase (Dynamisierung), give it an index with a spread of 0. That index
  steps each January.
- The plan buys equity outside the glide path. The next rebalancing moves your investments towards
  the target share again.
- The rate counts in the surplus. The Cashflows sheet and the Flows page show it below the surplus
  as `into savings plans`.
- While `invest_rest` is on, a plan changes little: the cash above the buffer goes into the
  portfolio anyway. A plan matters when you keep the rest in cash, and for gold and crypto.

A December plan buys before the December tax bill, so its fund shares owe one twelfth of the
Vorabpauschale of the year (see the taxes above). The surplus invested in December comes after the
bill and owes nothing for that year. When the tax bill of December needs more cash than a plan
left, the simulation sells equity for it.

## The three models

A model decides how the returns of the markets and the inflation move:

- `fixed`: one path with the mean returns and the mean inflation of your assumptions. It draws
  nothing at random, and it has no care episodes. The Cashflows sheet and the Flows page use it,
  because their numbers must add up month by month.
- `montecarlo`: many random paths (500 in the Explorer, 5000 on the command line). Each month draws
  random returns around your means with your spreads. Each year draws an inflation rate. The model
  also draws care episodes, the loss of the ability to work, the growth of your indices and the
  prices of sales. A sale price
  varies around the price of the event by its spread, and it never falls below zero. This is the
  default model.
- `historical`: it replays real history, with one path for each start month of the history. It takes
  the MSCI World index for equity, the yield of German bonds for fixed income, and the German
  consumer prices for inflation. A gold asset replays the gold price. When a path reaches the end of
  the history, it continues at its beginning. Like `montecarlo`, it draws the care episodes and the
  prices of sales at random, and the returns of a crypto asset too. This model needs the MSCI World
  series from the [Data](data.md) page.

Two runs with the same seed draw the same random numbers for each purpose: the returns, the
inflation, the care episodes, the loss of the ability to work and the sale prices. So two
scenarios meet the same markets on each path, and their difference shows the effect of the plan,
not of luck.

## The results

The table of the Explorer, the tiles of the Overview and the report use these figures. A header
names each figure in plain words. Its help starts with the short term in brackets below, which the
help texts and the command line also use.

- `Chance to run out by 90` (`P(broke)@90`): the share of the paths in which the liquid net worth
  fell below zero at or before age 90. Run out, or broke, means that the money that you can spend
  ran out. Property and pension policies do not count as liquid, so you can run out and still own
  a flat.
- `Chance to run out, lifetime` (`P(broke) alive`): the probability that you run out of money in
  some month while you are still alive. The simulation does not let anybody die. Instead, each path
  counts with the probability that you are still alive in its first month without money, from the
  German life table.
- `Typical shortfall` (`Shortfall`): for the lives that run out, how far the liquid net worth falls
  below zero before death. It is the median of the lowest value, weighted by the probability to die
  at each age. A dash means that no life runs out.
- `Net worth at 67` (`Total@67`): the median net worth at age 67: liquid assets plus property and
  pension policies, less loans.
- `Liquid at 67` (`Liquid@67`): the median liquid net worth at age 67, after the tax on
  unrealized gains.
- `Taxes`: the median sum of all taxes and social insurance from the start to the end, less
  refunds.
- `1 in 20 runs out at` (`Liquid p5<0`): the first age at which one path in twenty has run out of
  money.
- `Months of cuts` (`Cuts`): the median number of months in which the spending rule cut your
  flexible spending. The rule applies while your liquid wealth is below a share of its reference
  wealth that you set. With VPW, the months at the floor: the rate alone would spend less.
- `Months of raises` (`Raises`): the median number of months in which the spending rule raised
  your flexible spending, while your liquid wealth was above a share of its reference wealth. With
  VPW, the months that spend more than the plan of the flexible categories.
- `Chance of care` (`P(care)`): the probability of a long-term care episode while you are alive.
- `Chance of disability` (`P(disability)`): the probability that you lose the ability to work
  before the statutory pension age while you are alive. The summary of the command line leaves it
  out: its table has no room.

A median is the middle value: half of the paths are above it, half below. The 5th percentile is
the value that only one path in twenty falls below.

## Euros of the start

A euro buys less every year. So the app shows money in euros of the simulation start by default.
Each path divides its amounts by its own consumer prices since the start. An amount in euros of
the start buys what the same amount bought at the start. The switch `Nominal euros` on the
Explorer, and `--nominal` on the command line, show the amounts as paid instead. The chart
`Records against the plan` of the Overview uses nominal euros, because your records are nominal.

## What the model leaves out

Dagobert is approximate by design. These are the main simplifications:

- It computes one person, assessed alone. No joint assessment of a married couple.
- The church tax has no cap (Kappung).
- The rules of one tax year apply to the whole plan. Later changes of the law are unknown.
- Your work expenses are one number a year. The limit of 4,500 € for the commute without a car,
  meals away from home and a second home are not computed: enter them in the number. Costs above
  the salary make no loss.
- A donation above 20% of the income is lost. The law carries it to later years. Donations to
  parties and to the capital of a foundation have rules of their own that are left out.
- The tax credit of §35a leaves out a mini-job in your home and the costs of care. Two single
  people in one home share its limits by law. The simulation gives each plan the full limits.
- The state grant of the Altersvorsorgedepot leaves out the bonus for a young saver and the limit
  of two contracts.
- A Basisrente with a disability cover, or one that started before 2023, is left out.
- A loss carries forward only. Carrying it back into the year before (Verlustrücktrag) is left
  out, so the tax comes out a little too high in the year before a loss. The limit on a carried
  loss above 1 Mio. € a year (Mindestgewinnbesteuerung) is left out. The losses of private sales
  and of capital income stay in euros of the start, while the losses of the income tax stay in
  euros of their year.
- The unemployment benefit assumes a full record of insured work, so your age alone sets its
  length. A new claim after a new job of a year is not modeled: a later time pays the rest of the
  first claim. The short Sperrzeiten of 3 and 6 weeks, the other Sperrzeiten and the
  Gründungszuschuss are left out. The claim is the same on every path.
- The rules for children cover one parent. Nothing splits between two parents. The monthly
  withholding of a salary leaves out the child allowances of the Soli and the church tax, and the
  Entlastungsbetrag. The December settlement refunds the difference.
- Elterngeld is a stream of your notice. Its Progressionsvorbehalt is left out, so the tax of its
  year comes out too low. A disabled child without an age limit, a child abroad and the
  Kinderzuschlag are left out.
- The child-raising years leave out the longer time for a second child in the same years and
  the bonus for low earners (§70 Abs. 3a SGB VI).
- The loss of the ability to work is full and lasts to the end. A partial one (three to six
  hours a day), a recovery and a second onset are left out. One curve draws it, so a BU that pays
  for your own profession while you could still do other work pays too rarely in the plan. A
  business pays its profit in the first two months, where the law waits six weeks for its sick
  pay. A plan that is unemployed at the onset gets no sick pay. The months of school and studies
  that the law leaves out of the average of the Zurechnungszeit stay in it, so the EM-Rente comes
  out a little low. Points after the onset do not raise the later old-age pension. The higher
  mortality after a disability, the premium of a BU as a tax deduction and the waiting time of a
  BU tariff are left out. A Versorgungswerk pays no disability pension in the plan.
- Gold and crypto income from staking or lending is not modeled. A fund that holds gold or
  Bitcoin is an `equity` asset without Teilfreistellung, so its value grows with the return of
  equity.
- A payment counts in the tax year of the month that pays it.
- Your depot is one pool with one cost basis. A sale counts the oldest shares first for the
  Vorabpauschale, but its gain uses the average cost of the pool. When the sales of a year take
  more than the shares of January, the purchases of the year shrink in proportion.
- All `equity` assets share this pool and its return. The pool keeps the taxable part of the
  value and of the cost of each asset, so each gain pays at its own Teilfreistellung. A sale takes
  a slice of every asset. So a plan cannot sell the real-estate fund first.
- The invested surplus, the `invest` of a sale, the purchases of the rebalancing and the
  securities of an inheritance or a gift buy at the default rate of the Assumptions page, 30%
  (`tax.teilfreistellung`), not at the rate of an asset. Only a savings plan `into` an `equity`
  asset buys at the rate of that asset.
- The Vorabpauschale of a year counts in the next year by law: its tax-free allowance, its check
  against the personal tax rate and the health insurance of a voluntary member. The simulation
  takes it in December of the year itself. The Basiszins of the tax year applies in every year.
  A higher Basiszins moves tax earlier, because a sale credits the Vorabpauschale.
- A loss on shares offsets only gains on shares by law. The simulation lets it offset all capital
  income. A bond fund is `fixed_income`, so its return pays tax every year. The law taxes a
  Vorabpauschale each year and the rest at the sale. Funds of funds and a fund that changes its
  class are not modeled.
- A savings plan has no fees, and the simulation does not delete it after it skipped rates.
- A salary conversion uses the limits of each month, a twelfth of the year. A conversion of a
  bonus, which the law lets use the rest of the yearly limit at once, is not modeled. The
  contribution that the employer pays on top stays free of tax and social insurance whatever its
  size.
- The employer pays at most half of the health premium of each month. In practice, if your salary
  is below the contribution ceiling, a bonus month can also use what the earlier months of the
  year left of that half. So the simulation pays a little less.
- Every salary gets the subsidy of the employer, also a mini-job, which gets none by law.
- The health insurance of a voluntary member takes the profit of the month and the capital
  income of the year before. The health insurance fund takes the profit of the last tax
  assessment and corrects it later with the assessment of the year. Beside a profit or a rent, it
  takes the capital income of the same year.
- A business beside a pension stays in the health insurance of pensioners (KVdR). The law ends
  the KVdR for a business that is your main work.
- The contribution ceiling and the Bezugsgröße of the health insurance follow the consumer prices
  in the run. The law raises them with the wages, so over decades the simulation falls behind.
  This matters more for a voluntary member.
- A change from the PKV to the GKV comes from `tax.gkv_from` only. The simulation does not find
  the month itself, for example the first month of ALG1 or of a salary below the
  Jahresarbeitsentgeltgrenze.
- The unemployment insurance of a business (on application, §28a SGB III) is not modeled. Add an
  expense stream for its premium. Unemployment benefit after a business is paid on the last
  salary. By law it needs that insurance, and then it is paid on a fixed wage by your
  qualification. A profit beside unemployment benefit does not reduce it.
- A business ends without a sale and without a tax on its sale. The Umsatzsteuer, the
  Künstlersozialkasse and the pension funds of the professions (Versorgungswerke) are not modeled.
  A pension fund can be an `rv_voluntary` stream for the contribution and a `pension` stream with a
  `gross` for its pension.
- An inheritance or a gift holds cash and securities only. Enter the expected net proceeds of a
  property, after its sale, as cash. Gold, crypto, policies, loans and a business of a relative
  are not modeled. The household goods, the family home and the reductions for rented housing are
  not tax-free in the simulation. Debts of the estate count only as the 15,000 € for the costs.
  Enter your own share when other heirs share the estate. The tax is due in the month of the
  inheritance, not months later with the notice of the tax office. The life table is the same for
  every relative of one age and sex, whatever the health of the relative. Under a joint will of two
  parents, the simulation uses the tax-free amount of the parent who died last only. A gift comes
  from one relative: enter a gift of two relatives as one gift of each.
- A property is let while its rent runs, else lived in. A change of the use within the ten years of
  a private sale is not split. The depreciation is linear: the declining AfA for new homes (§7 Abs.
  5a EStG) and the special AfA of §7b are left out. A rent below half of the local rent (§21 Abs. 2
  EStG), large repairs in the first three years after the purchase (§6 Abs. 1 Nr. 1a EStG) and the
  spread of a large repair over several years (§82b EStDV) are left out. Interest after a sale and
  the penalty of a repayment without a sale lower no tax. The reserve of the owners
  (Erhaltungsrücklage) lowers the tax only when the owners spend it: enter it without `property`. A
  vacant month with the rent stream at a factor of 0 keeps the costs. The Gewerbesteuer has a loss
  carryforward of its own, which the simulation leaves out. The furniture of a purchase, such as a
  kitchen, counts in the price that the Grunderwerbsteuer taxes. A purchase takes one loan. The
  Grunderwerbsteuer is due in the month of the purchase, not a month after the notice of the tax
  office.
