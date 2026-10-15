# Flows

The Flows page shows where the money of one scenario goes in each phase of your life. It uses a
single run of the scenario with the mean returns and the mean inflation (the `fixed` model, see
[the models](models.md#the-three-models)). The amounts are in euros of the simulation start.

## Controls

- `Scenario` and `Amounts`: the scenario, and the amounts per month or per year. The page opens
  with your main scenario, which the list marks with `(main)`.
- `Options`:
  - The fold collects small items into one, below 50 € by default.
  - `One-offs` adds the payments that come once, with the tax on them. Examples are a sale, a
    severance payment and the loan repayments from them.
  - `Run rate` spreads a payment that comes every few months, such as a bonus or a yearly bill,
    over the months that earn it.
- `Compare with the inputs before`: select a day. The table then shows the change against the plan
  as it was before that day. The list holds the days on which you changed the plan. The newest day
  comes first. A new data directory has no earlier plan, so the select shows only after your first
  change of the plan. The change in brackets compares with the inputs of that earlier day. The
  Explorer compares with `(as saved)`, the run of the files now. If this version of the app cannot
  load or run the plan of a day, a message says so, with the reason when it has one, and the table
  shows no changes.

The controls are in one row. On a narrow screen the row wraps.

## The table

The table has one column for each stretch of a phase, for example `Work` and `Retired`, named as the
Assumptions page shows the phase. A phase that the scenario does not reach has no column. Each cell
is the mean per month over all months of the stretch. A salary can differ a little from the figure
you typed, because it rises with its own growth rate and prices change during the year. A
salary of 4.200 € can show as 4.207 €. Money that goes out is below zero, as on the
[Cashflows](cashflows.md) page:

- `income`: everything that comes in, gross.
- `taxes`: income tax, the solidarity surcharge, the church tax, the trade tax of a business and
  social insurance, below zero.
- `spending`: everything else that goes out, also the repayment of a loan, below zero.
- `surplus`: the sum of income, taxes and spending. It is what you save, or below zero what you
  take from your savings.
- `into savings plans`: what your savings plans paid into their assets. It is a part of the
  surplus. The line shows only when a plan paid.
- `into assets`: what the flows put into your assets other than the cash, and into your loans,
  less what they take out. The repayment of a loan goes in, and so does a salary conversion into a
  company pension. A pension that a policy pays as income comes out of the policy.
- `non-cash income`: the growth of your assets, and what goes into a pension policy without passing
  your cash. An example is a contribution of your employer. It stays invested.
- `wealth built`: the surplus, plus `into assets`, plus the non-cash income. It is the change of
  your net worth before the tax on unrealized gains. It can be above zero while the surplus is
  below zero, because your assets grow. The match is exact for whole calendar years. A stretch
  that ends before December can differ a little: it counts its share of the tax settlement of
  December, but your net worth pays that tax only in December.

The box `What the lines and terms mean` under the table explains each line and the German terms,
for example SV (social insurance). The Cashflows page shows other numbers for the same scenario.
It shows the plan on one date and the first twelve months of the run. The Flows page shows the
mean over all months of a phase. A link under the table opens the Cashflows page.

## The tabs

Each stretch of a phase has a tab. A phase that comes twice shows its years. The tab opens on the
whole stretch. The `Period` slider and its arrows select one calendar year instead. The tiles show
the income, the net income after taxes, the surplus and the wealth built per month. The line
above the tiles names the parts of the social insurance that the diagram shows by their short
names: RV pension, AV unemployment, KV health and PV care insurance.

The diagram shows the flow of the money from left to right. It starts with the sources of income.
Then come the taxes and social insurance beside the budget, the spending groups and their items. The
colors name the roles: income, taxes, spending, loans and savings. A surplus flows into savings. A
deficit flows from savings. A business that makes a loss in the period has no band in the diagram.
The table above it takes the loss off the income.

On a narrow screen, such as a phone in portrait, bars of the outflows replace the diagram. Turn the
phone, or close the sidebar, to see the diagram. You can also turn on `Show the diagram anyway`.
The diagram then keeps its full width, and you swipe it sideways.

## What to know

- The December tax settlement is spread over the months of its year by their taxable income.
- Moves between your own accounts, such as investing, withdrawals and a maturing deposit, are not
  flows.
- The upkeep of a property is a provision of its yearly share of the value.
- Without `One-offs`, `wealth built` leaves out a sale, a severance payment and the moves that come
  with them. With `One-offs`, a move between your cash and another asset counts on both sides, so
  only its cost changes `wealth built`. For example, the proceeds of a sale count as income, and
  the value of the sold asset counts below zero in `into assets`. The costs of the sale and a
  prepayment penalty lower `wealth built`. The top-up of a bAV policy to its guarantee raises it.
