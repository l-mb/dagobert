---
paths:
  - "src/dagobert/engine/*.py"
  - "src/dagobert/{result,returns,tax,sv,mortality,holdings,carry}.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{engine,income,portfolio,golden,tax,sv,returns,mortality,profit,health,rental,spending,deductions,harvest,children,alg1}.py"
  - "tests/{builders,conftest}.py"
  - "tests/__snapshots__/**"
---

# Engine

The tax and SV law that the engine applies is in the rule `tax`, the bookkeeping of a run in the
rule `ledger`, the units of money in the rule `money`. The user guide explains a run in plain
English (`docs/manual/models.md`: the month, the withdrawal order, the models, the results, the
simplifications): change it with the behaviour.

## Code

- `src/dagobert/engine/`: `simulation.py` holds `Engine` (`run`: the months in their order),
  `simulate`, `horizon_months` and `before` (a run up to a month, rule `rollforward`). `Engine`
  takes the steps of a month from a class per module, each on `core.Core` (the setup of a run and
  the helpers that every step reads, `year_levels`): `portfolio.Portfolio` (the returns, the savings
  plans, invest and sell, the rebalancing, the flat tax), `income.Income` (the streams, a severance)
  on `health.Health` (the GKV beyond the salary and the pension, rule `gkv`) on `alg1.Alg1` (the
  claim to ALG1, rule `alg1`) on `profit.Profit` (a business, rule `self-employment`),
  `events.Events` and `settlement.Settlement` (December), the last two on `Income` and `Portfolio`.
  A method calls into its own class, `Core` and the bases of its class only. `state.py`: the
  dataclasses of the state (`YearAcc`, `MonthState`, `MonthPay`, one per asset kind).
- Each step pays into `Core.cash` itself and reports in `MonthFlows`, nominal: `Core._receive`
  (gross income less the taxes and SV taken off it), `_spend` (expenses below zero), `run` reads
  only `self.flows`. `Income._apply_streams` runs the stream steps in their order: `_claim_alg1`
  (the steps after the streams read the claim), `_pay_streams` (the plain streams, the
  salaries and pensions into a `MonthPay`), `_pay_kindergeld`, `_pay_salaries`, the depots, the bAV
  policies (a lump sum withholds on the salary of the year so far), `_pay_gkv`, `_pay_profit`,
  `_raise_children` (rule `children`), `_costs`, `_pay_flexible` (VPW, rule `spending`),
  `_record_earned` (the settlement's weights).
- Units: a value in start-year euros, as the law of `tax` and `sv` takes it, carries `_real` in its
  name (a variable, a parameter, a field); other money is nominal. A step converts at its boundary:
  `/ self.deflator` before the law, `* self.deflator` after, and returns nominal euros unless its
  docstring says real (`_pay_salary`, `_convert`, `_sv_bases`, `Profit._business`). `Core._balance`:
  the nominal `BALANCE_CLASSES` of a month, `simulation.liquid_of` sums those of `result.LIQUID`.
- `Engine.m` is the `MonthState` (index, month, phase, `since`: rule `pay-growth`) of the step.
  Helpers read it, so they take no `month`, `phase` or `i` parameters. The phase is a name of `assumptions.yaml` (`Plan.phase_at`),
  and no rule reads a name: a stream pays in the `phases` of its row at its `factor`, a bAV policy
  takes its contribution in its `phases`, `scale.salary` scales by name, the PKV subsidies follow
  what the month pays (rule `tax`). The marker of a change shows the label, not the name, as every
  page does (`phase: Career break`), `RunResult.phase_labels` the labels in the order of the file,
  which sets the colors of the bands (`charts.PHASE_COLORS`). `test_golden` renames every phase of
  `rich_plan` (its own phase `part-time`, labeled) and gets the same run. `Portfolio._flat_tax` is
  the one place that charges Abgeltungsteuer (Pauschbetrag, memory for the Günstigerprüfung), and
  `_report_capital_tax` the one that reports it.
- A marker is data (`result.Marker`, `Core._mark`): its kind (`result.MarkerKind`: the event type,
  `phase`, `pension`, `bav`, `av`, `alg1 …` and `gz …` (rule `alg1`), `savings plan`, `harvest`,
  `disability`, `exemption` and `gkv` (rule `gkv`); a new kind there, the type
  checker refuses an event type that it lacks), the name as the inputs write it, the median euros
  or the claim factor, the years, the deferred month, the form (`monthly`, `once`, `half`); the
  run, which the app caches for every session, holds no words. `report.charts.said` writes them (rule `charts`), `tests/builders.marked` in the words of
  the engine (`sell: flat`), which the snapshots of `test_golden` keep.
- Engine state is one numpy array of shape `(paths,)` per quantity. Loans are scalar because events
  are deterministic. `RunResult` arrays are `(paths, months)`, the counts of months `reduced` and
  `raised` of the spending rule `(paths,)`. The Monte Carlo run must stay in the seconds range: 5000
  paths × about 650 months × 3 scenarios takes about 6 s. Keep new per-month work vectorized.
- Every random draw has a generator of its own purpose (`returns.generator`): `returns.<class>`,
  `inflation`, `indices.<name>`, `care`, `disability` (rule `disability`), `sale.<asset>` (a renamed
  asset draws other prices) and `inheritance.<relative>`, the month of death of a relative (rule
  `estates`). Two runs with the same seeds then draw the same numbers for a purpose, whatever else
  they draw. Their paths pair up, and the explorer's difference and the sensitivity run rely on
  that. A sale draws one number per path and asset, so a moved or conditional sale keeps its price:
  lognormal with the mean `price` and the relative spread `price_stdev` (`Events._sell_property`),
  so no price falls below zero. Never draw two purposes from one generator.
- `RunResult.drivers` holds the random drivers of `anatomy.drivers`, one `float32` array of shape
  `(paths,)` per kind and name (`anatomy.Key`, no words: the app caches the run for every language),
  about 20 KB each at 5000 paths. The engine computes them once after the last month from arrays it
  already has (the equity index, the CPI, the index levels, the care episodes, the rates of the
  class of each gold or crypto asset, which `Engine._class_levels` compounds), so it draws nothing
  and the run takes about 1 ms longer, 10 ms more per such class at 5000 paths.
- `RunResult.balance` holds one value per balance sheet class (`BALANCE_CLASSES`, shape
  `(months,)`), not per-path arrays: those would add 160 MB at 5000 paths. The value is the mean
  over the paths whose `total` lies inside `MEDIAN_BAND` (45th to 55th percentile) in that month, in
  euros of the start. Real class values cannot come from the nominal means, so the engine reduces
  twice: `balance` over the band of the deflated `total`, `nominal_balance` over the band of the
  nominal one. Per path the classes add up to `total`, so the stack adds up to about the median net
  worth. Do not use class medians: with a per-path sale the property median stays at the full value
  until half of the paths sold, and the stack then falls at the sale.
- `src/dagobert/holdings.py`: one `Pool` per gold or crypto asset, as a holder keeps a depot or a
  wallet. A unit is worth one euro at the start, `price` follows the return class less the
  custody `cost`. `aged` holds the free units, `young` one row per purchase month of the holding
  period, a ring by month index (`young_cost` nominal), `capital` the units under §20 with their
  basis. `Pool.opening` spreads `value` over the open lots: by units within a security, by cost
  across securities (no price files). `take` sells oldest first: `aged`, the rows from the oldest,
  then `capital`, only on the paths that sell.
- Tests by the steps of a month: `test_engine.py` (flows, loans, events and sales, a purchase, the
  ledger, care, the tax year, the price levels), `test_spending.py` (rule `spending`),
  `test_income.py` (the streams), `test_portfolio.py` (the holdings and their taxes),
  `test_rental.py` (letting, the Verlustvortrag), `test_deductions.py` (rule `deductions`),
  `test_harvest.py` (the harvest, its cap of a GKV member in `test_health.py`), `test_children.py`
  (rule `children`), `test_alg1.py` (rule `alg1`); the law in amounts in `test_tax.py` and
  `test_sv.py`.

## Behaviour

- Start values: a value of `assets.yaml` holds at `start` (people record rarely, owner
  2026-10-13). One of an earlier `asof` carries to the month before `start`: a loan by
  its schedule (`Loan.opening`), a term deposit by its interest from its own `start`
  (`TermDeposit.value_at`), a pension policy (`carry.policy`: `value` and `paid`) and an
  Altersvorsorgedepot (`carry.depot`) by the mean return of its class less `cost` (`returns.grown`,
  `monthly_rate`) and the contributions: per month in its `phases` (`Scenario.phase_of`) before
  `matures` the employer's `contribution`, the `premium` of a Basisrente and the conversion with its
  subsidy (`sv.conversions` on the monthly salaries of the phase in euros of the start, without
  `scale`, a share `of` another too, `carry._gross`; the source as `Income._source`), each December
  from `start` of a year with a salary of a gross above zero, ALG1 or a business the contribution
  and the Zulage. A known approximation: the streams of `cashflows.yaml` only, without the events
  that add, end or set one. One value for every path. One of an `asof` in or after the month of
  `start` stays: the run adds the months up to it once more until a roll forward passes it (rule
  `rollforward`), as `Loan.opening` does. The Snapshot estimate carries to the day (rule
  `tracking`), the tiles and the history keep the recorded values.
- Amounts follow their `index`, in euros of the start. Event amounts are nominal at the event date;
  the securities of an inheritance or a gift are in euros of the start at the equity index. A
  pension too (`Income._pension_gross`: its `gross` or `points` times `point_value`, the claim
  factor), with `pension_growth` on top, a real growth over the default `cpi`, stepped each January
  (§68 SGB VI: the Rentenwert follows the wages of its time, so a path of high inflation does not
  erode it). A salary and a profit take `scale.growth` of their phase on top: rule `pay-growth`.
- Order within a month: the pools age, the sales on a condition (`_check_triggers`), events
  (`Events._apply_events`: the inheritances and gifts first, rule `estates`), returns, the term
  deposits that mature (`Portfolio._pay_matured_deposits`: flat tax, then the net into the bucket or
  the cash), loans
  (`LoanState.interest`), streams (the rent net of its costs, then the AfA of the let properties,
  rule `rental`), the savings plans (`Portfolio._save_plans`, in file order), deficit cover,
  rebalancing, in December the Altersvorsorgedepot contribution, the settlement, then rounds of
  deficit cover and the settlement again with what the cover sold, until no path owes a cent more
  (`Settlement._settle_december`), then the surplus is invested. The December bill therefore comes
  out of cash before anything is invested. The loss pots carry from one settlement to the next: §20
  (`Core.losses`, from `tax.capital_losses`) and §23 (`private_losses`) in start-year euros, §10d
  (`income_losses`, from `tax.loss_carryforward`) nominal, with the last two years settled
  (`assessed`), which a loss goes back into, and their refund due (`refund_back`), which the next
  settlement pays or waives per path (`_waive_back`, rule `rental`).
- Withdrawal order for deficits: cash, fixed income, equity (grossed up for capital gains tax), then
  gold and crypto in file order: first the free units of every pool, then the rest of each, the
  young units at face value (their tax comes with the settlement), the §20 part grossed up. Term
  deposits are locked until maturity: when the rest is used up, cash goes negative while the deposit
  still counts in `liquid`. Surplus above the cash buffer is invested by the allocation share,
  unless `invest_rest` is false (`_invest_surplus` returns: the cash grows and earns `returns.cash`;
  a sale's `invest` still invests). The cash buffer is a ceiling only, a deficit does not refill it,
  so cash is near zero once deficits start and `returns.cash` hardly matters. Rebalancing skips
  selling equity after a loss over `skip_after_loss` months.
- A savings plan (stream kind `savings`) pays `-amount` times its factor, index and
  `scale.savings` from the cash into `into` (`Portfolio._put`: a gold or crypto pool, a row per
  purchase month; a fixed-income asset into the bucket; else, also without `into`, the equity
  pool through `_buy_equity`, outside the glide path: the next rebalancing moves towards the
  share), ignoring the buffer. A path whose cash does not cover the whole rate skips it (a
  broker skips an execution): no deficit cover, no catch-up, no deletion after misses. A marker
  `savings plan: <name> paused` falls in the first month in which half of the paths skip, once
  per plan. In December the plan buys before the settlement, whose bill may then sell equity on
  a path that the plan left short (accepted). `_pay_streams` skips the kind, the cash buffer
  counts the expenses only (`Core._run_rate`), `_index` applies no spending cut (no `cat`).
- `broke` means liquid net worth below zero; gold and crypto count in `liquid`. Property is only
  sold through events, gold and crypto bought only through `buy` events. A conditional sale fires
  per path, once, on the first condition met, with `liquid_below` in start-year euros. Its marker
  falls in the month in which half of the paths have sold, labelled `(half of the paths)` unless all
  have (a `fixed` run). Conditional sales cannot repay loans, because loans are scalar. A sale of
  a property sells on every path that it reaches and that holds it, whatever the price: one at
  `price: 0` (a gift) or with `costs: 1` takes the property out and ends and starts its streams
  too. A sale of gold or crypto ends no streams.
- A `buy_property` (`Events._buy_property`) takes `BuyPropertyEvent.cost` (the price, the
  Grunderwerbsteuer `transfer_rate`, the `costs`) from the cash, its loan (`NewLoan.taken`) adds
  its balance, and the deficit cover of the month takes the rest. The property joins `properties`
  as a `PropertyAsset` of one m² at the price, `bought_for` the cost, `PropertyState.bought` the
  month index: it grows and costs upkeep from that month. The loan (`LoanState.since`) pays its
  first annuity a month later. A conditional sale of a property not bought yet waits
  (`_check_triggers`).
- The spending rule (`Core._update_spending_rule`, first in a month; VPW in
  `Income._pay_flexible` after the streams): rule `spending`.
- `RunResult.pay_ends`: the month after the last one with pay (`Core.earns`, after a month's events;
  0: no pay, pay to the end or to the month before it: one point is no chart), where
  `lasting_figure` starts (rule `balance`).
- A repayment (`Core._repay`) pays `prepayment_penalty` while `Loan.fixed_at`: up to
  `fixed_until`, without it for the whole term. §489 Abs. 1 Nr. 2 BGB ends the penalty ten years
  and six months after the full payout (a new agreement on the rate or the term starts again). A
  loan has no payout date, so the engine sets no cap (a decision): the help of the field and
  `configuration.md` ask for 0 at a repayment that late.
- Care episodes are drawn per path from the yearly hazard, so are the onsets of a disability (rule
  `disability`). Single-path runs (`fixed`) draw none. Paths do not die, so the summary weights
  P(care) by the survival at the episode start, and P(broke) alive by the survival to the first
  broke month (`RunResult.p_broke_alive`). `RunResult.shortfall` is the median of the lowest liquid
  value by each month of death, over the paths broke by then, weighted by the probability to die in
  that month. Without the life table (`--no-mortality`) every path lives to the end.
- Return modes (`fixed`, `montecarlo`, `historical`): rule `returns`.

## Check

- For engine changes, run `uv run pytest -n0 tests/test_golden.py --snapshot-update` and read the
  diff of `tests/__snapshots__/`: the yearly totals, ledger groups and markers of a rich synthetic
  plan (PKV, the GKV from 2035) and of `gkv_plan`, a GKV member (rule `gkv`). Check them by hand
  before you trust charts. For the effect on a real scenario, run it with `--model fixed` and print
  the yearly figures of the `RunResult` (income, expenses, taxes, capital_taxes, liquid, total,
  phase). Income is gross including PKV subsidies, `expenses` the loan principal and a salary
  conversion too, `taxes` holds income tax, Soli and SV, `capital_taxes` the Abgeltungsteuer net of
  the Günstigerprüfung. Sanity anchors: taxes and SV take about 37% of a full salary year, refund in
  the first partial year, pension starts with the phases of its stream, repaid loans stop paying.
