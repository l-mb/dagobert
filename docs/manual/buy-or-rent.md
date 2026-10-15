# Buy or rent

This guide shows how to compare the purchase of a home with renting. You write two scenarios of one
plan: one rents, the other buys. Then you compare them path by path. A path is one possible future
of the markets and of inflation.

## What you own today and what you plan

The file `assets.yaml` holds what you own today. If you own your home, its property and its loan
are there, and every scenario keeps them. A scenario cannot take them away: an override cannot set
the living space or the balance of a loan to zero.

A purchase that you consider is an event of a scenario. Your plan rents, and a child scenario buys.
This also works for a purchase now: give the event the month of the simulation start.

## The example pair

The example data directory holds such a pair. The scenario `plan` keeps renting. The scenario
`buy-home` extends `plan` and adds four events in 2028-04, all with the id `buy-home`:

```yaml
events:
  - at: 2028-04-01
    type: buy_property
    property: {id: home, name: Own flat, upkeep: 0.005, tags: [home]}
    price: 330000
    land: NI
    costs: 0.05
    loan:
      id: home-loan
      name: Home loan
      balance: -300000
      rate: 0.035
      annuity: 1500
      fixed_for: 180
    note: Buy a flat to live in
    id: buy-home
  - {at: 2028-04-01, type: end_streams, names: [Rent], note: The rent ends, id: buy-home}
  - at: 2028-04-01
    type: add_stream
    stream: {name: Hausgeld, cat: housing, amount: -400, tags: [home]}
    id: buy-home
  - at: 2028-04-01
    type: add_stream
    stream: {name: Property tax, cat: housing, amount: -40, tags: [home]}
    id: buy-home
```

The purchase costs 330,000 € plus 5% Grunderwerbsteuer in Niedersachsen (`NI`) and 5% other costs:
363,000 €. The loan pays 300,000 € of it. So 63,000 € come from your cash and your liquid assets. If
the cash is not enough, the simulation sells fixed income, then equity, then gold and crypto, as
for any gap.

## Set up your own pair

1. On the [Scenarios](scenarios.md) page, press `New`. Type a name, for example `Buy a home`, and
   select your plan as the scenario that the new one extends. Then the new scenario takes the
   phases and the events of the plan.
2. Select the new scenario. On the `Events` tab, open `Buy a property` and add the purchase with
   `Add an event`.
3. Open `End streams` and end your rent in the same month.
4. Open `Add a stream` and add the Hausgeld and the property tax from the same month. Give them the
   tag of the property. Then a later sale of the property ends them.
5. Give the four events the same id. Then one slider of the Explorer moves all of them.

A flat that you buy to let takes no `End streams` of your rent. Instead, add its rent with `Add a
stream`, of the kind other income, from the month after the purchase, and select the flat in
`property` (under `All columns`). Its Hausgeld takes `property` too. The purchase then needs
`property building_share` and `property afa` (under `All columns`). Give the rent the id of the
purchase as well: a slider that moves the purchase past the rent would make the rent name a flat
that is not bought yet, and the scenario would not load.

## The fields of a purchase

- `price`: the price in euros on the date of the purchase.
- `land`: the code of the Bundesland of the property, for example `NI` or `BY`. The pages show
  its name, for example `Lower Saxony` or `Bavaria`. The simulation takes
  the Grunderwerbsteuer of that Land on the date of the purchase: 3.5% in Bavaria, up to 6.5%
  elsewhere. The Grunderwerbsteuer is the tax on the purchase of land.
- `transfer_tax`: a rate of your own instead of `land`. A purchase from your spouse, your parents
  or your children pays no Grunderwerbsteuer: set `transfer_tax` to 0.
- `costs`: the other costs as a share of the price. The notary and the land register cost about
  1.5%. A broker costs the buyer up to 3.57% with VAT, half of the fee.
- `property`: the id and the name of the property, its return class (`growth`), its yearly upkeep
  as a share of the value, and its tags. The Hausgeld of a flat pays for the building, so `upkeep`
  is for the inside of the flat only. A flat to let also takes `building_share`, the share of the
  building in the cost, and `afa`, the yearly depreciation of the building.
- `loan`: the id and the name of the loan, the amount with a minus (`balance`), the rate, the
  monthly annuity and `fixed_for`, the months of the fixed rate from the purchase. The first annuity
  is due a month after the purchase. The loan can be at most the price with the tax and the costs.

## Compare the two scenarios

1. On the [Scenarios](scenarios.md) page, choose the purchase and press `Compare with … in the
   Explorer` on the tab `Timeline`. Or select both scenarios on the [Explorer](explorer.md).
2. Read the table: the chance to run out of money, the net worth and the liquid assets at 67.
3. Below the charts, `Difference of two runs` compares them path by path: the plan as A and the
   purchase as B, which extends it. The chart and the table show B less A on each path, at 67, at
   90 and at the end.

Both runs meet the same markets on each path, so the difference shows the effect of the purchase.
On the command line, the report does the same:

```sh
uv run dagobert run data/scenarios/plan.yaml data/scenarios/buy-home.yaml
```

The report then has a tab `Difference from Work to 65`, the name of the first scenario.

In the example, the purchase gives a higher net worth at 67 and lower liquid assets, because the
money is in the flat. The flat is not liquid: you can run out of money and still own it. With the
average returns (the model `fixed`), the down payment does not start the cut of the spending rule
(see below).

## Move the purchase with the sliders

The Explorer shows two sliders for the id `buy-home` in the group of the events. One moves the
month of the four events. The other sets the price. The down payment takes the change of the price,
because the loan stays the same. The price slider starts at the lowest price that the loan allows.

The goal seek finds the price at which the chance to run out of money by 90 meets your target. Open
`Goal seek: the limit of one lever` and select the price.

## What to know

- After the purchase, the spending rule can cut your flexible spending. The rule compares your
  liquid wealth with your liquid wealth at the start, and the down payment lowers it. The
  simulation does not reset the start for a purchase. If you do not want the cut, change
  `spending.trigger` on the [Assumptions](assumptions.md) page.
- An event of the plan that changes the rent later, for example at the retirement, changes nothing
  after the rent ended.
- A later sale of a home that you live in pays no tax on its gain: leave `taxable` of the sale off.
  If you rent the property out, a sale within ten years of the purchase is a private sale: switch
  `taxable` on. The simulation then taxes the gain over what the purchase cost with the tax and
  the costs.
- A sale on a condition cannot repay the loan. The loan then runs on after the sale.
- The page [How the simulation works](models.md#buying-a-property) lists what the model leaves out.

## After the real purchase

The purchase is no longer a plan. Record it as a fact:

1. On the [Assets](assets.md) page, add the property and the loan with their values today. Give the
   loan its `fixed_until` and the date of its balance.
2. On the [Scenarios](scenarios.md) page, remove the purchase from the scenario, with the events
   that end the rent and start the Hausgeld. Change your plan so that it no longer pays the rent.

The roll forward of the [Overview](overview.md) refuses a purchase that lies before the new start.
It does not know what became of it.
