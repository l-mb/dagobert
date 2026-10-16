---
paths:
  - "src/dagobert/engine/*.py"
  - "src/dagobert/{result,budget}.py"
  - "src/dagobert/ui/{flows,cashflows,bars}.py"
  - "tests/test_{budget,engine,portfolio,golden}.py"
---

# Ledger and budget

After a change, run the check of the rule `engine`.

- A single-path run keeps a `result.Ledger`: every cash flow by month as `(side, group, item)` in
  start-year euros, written by `Core._note`. A salary is a `source` row with the group `salary`, a
  self-employed profit one with `profit` (`budget.regular_salary` reads both: a usual month of
  earned income, which `scale.salary` scales), every other source has no group (the Kindergeld,
  `result.KINDERGELD`, rule `children`; `GRUENDUNGSZUSCHUSS`, rule `alg1`; `KRANKENGELD` with
  its `RV`, `AV` and `PV`, `EM_RENTE` outside the phases of its stream, a BU policy `<name>:
  benefit`, `BENEFIT`, and its premium a
  `spending` row of its `cat`: rule `disability`). A business books `RV` and its reserve as `income
  tax` monthly, the Gewerbesteuer `trade tax` with the settlement; the KV and PV of a GKV member
  beyond the salary and the pension book monthly as `KV` and `PV` (`Health._pay_gkv`, rule `gkv`).
  `income tax` holds the Soli and the church tax too; the refund of a loss carried back books it
  below zero in the December after the year of the loss, alone (rule `rental`). A let property adds no flow: the AfA is no
  cash, it shows as a lower `income tax` (rule `rental`). The sides `one-off in` and `one-off out`
  are part of the engine totals (severance, lump sum, policy payout, the tax on them; the cash of an
  inheritance or a gift, group `inheritance` or `gift` by the label of the giver, and its
  Erbschaftsteuer, `tax on one-offs` `<label>: inheritance tax` or `gift tax`, rule `estates`; of a
  `buy_property` the Grunderwerbsteuer, `result.ONEOFF_TAX` `<label>: transfer tax`, in `taxes`, and
  its costs, `PURCHASE_COSTS`, in `expenses` through `MonthFlows.expenses`). The sides `move in` and
  `move out` are not (the proceeds of a sale event, group `sale`, before the flat tax of a §20 part;
  a `buy` and the price of a `buy_property`, group `purchase`; the loan of a purchase, `move in`
  group `loan` by its label, its `moved` the new debt below zero; repayments, group `repayment`; a
  `fund_policy`, group `policy premium`; what a savings plan paid, group `savings plan`
  (`result.SAVINGS_PLAN`), `move out` and `moved` by the name of the plan, its run rate from what it
  paid, so a skipped payment spreads nothing, and the own premium of a Basisrente and the December
  contribution of an Altersvorsorgedepot (with a run rate of 12 months), item `<label>: premium`
  (`OWN_PREMIUM`, rule `deductions`); a deficit cover is no flow), nor is the side `non-cash`: what
  the assets gain in the month without a cash flow. The growth of every asset has the kind of the
  asset as the group, the item `equity`, `fixed income` or `cash` for the pools (cash also on a
  negative balance), else the label: each term deposit by what `_deposits` counts more than the
  month before (none in the first month), so its months add up to what it pays beyond its value at
  the start, each property while held, each bAV policy until it is done, each Altersvorsorgedepot
  and each gold or crypto asset, all net of their `cost`. What goes into a policy without passing
  the cash has the group `contribution` (the employer's bAV contribution, `<label>: employer`, and
  its subsidy of a salary conversion, `<label>: subsidy`; the Zulage of an Altersvorsorgedepot,
  `<label>: Zulage`, not its contribution: that is a `move out` of `savings plan`) or `one-off
  contribution` (the securities of an inheritance or a gift, `<label>: equity`; the tax-free part of
  a severance, `<label>: severance`, at the event, not in `Events._fund`, which also serves
  `_fund_from_cash`, a premium already booked as `move out`; the top-up of a bAV policy to its
  guarantee at maturity, `<label>: guarantee`). It is nominal in start-year euros like every entry,
  so the inflation part of the growth does not raise the real net worth. `Portfolio._note_growth`
  runs only with a ledger. Runs with more paths keep none, so Monte Carlo pays nothing for it.
  Outside the totals too, the sides `draw` and `moved` hold the other side of a flow: how it changes
  an asset other than the cash, or a loan, beyond the loan principal, item the label. `draw`, group
  the kind: what a payout that a source books (a bAV annuity, an Auszahlplan) takes out of its
  policy, the actual drop, so an annuity beyond the capital is new wealth. `moved`, a one-off, group
  that of its move or `write-off`: a sale at the value of the asset (so its costs and a price off
  the value count), a purchase, a repayment without its penalty, a premium, a policy paid out at
  once, a write-off. So the held assets change each month by the engine totals, the non-cash income,
  `draw`, `moved` and `move in` less `move out`, the loans by the loan principal (`test_engine.py`,
  nominal: each entry at the price level of its year). Per year the ledger adds up exactly to
  `income` (`source`, `one-off in`), `expenses` (`spending`, the purchase costs; VPW books no flow
  of its own, its flexible streams their rows, rule `spending`), `taxes` (`tax`, `tax on one-offs`)
  and `capital_taxes`, at the price level of each year (`test_golden.py`): keep that true when you
  add a flow to the engine. The regular part of the December settlement is spread over the months of
  its year by their taxable income (salary, pension, other income, ALG1; evenly without any; what a
  sale for the December bill adds stays in December), and the part of it that a severance causes is
  a one-off (the settlement computed again without the severance gives the regular part).
  `Ledger.run_rate` holds, for a stream paid every n months, each payment spread over the n months
  that end with it, less the payment: added to the entries on request (`from_ledger(run_rate=True)`,
  the Flows default) it shows the rate of a bonus or a yearly bill instead of its lump. Moves
  between own accounts are no flows, nor is a harvest (rule `harvest`). The Flows page and the rows
  of the run on the Cashflows page must read the ledger and never re-derive engine rules: a static
  copy of them missed repaid loans, sales and phase timing.
- `src/dagobert/budget.py`: `from_ledger` turns a stretch of months of the engine ledger into a
  `Budget` (sources, taxes, spending by group), a monthly average in start-year euros, behind the
  `Flows` page. A tax that pays back becomes a source, the capital gains tax is a spending group (a
  withdrawal triggers and pays it), one-offs count only on request, the tax on them (`one-off out`
  of the group `tax on one-offs`) under the taxes, so `net` is after all taxes, the other `one-off
  out` (the purchase costs) and the moves under the spending `one-offs`. `stretches` splits a run
  into contiguous months of one phase (its `label` that of the phase, `RunResult.phase_labels`, with
  the years of a phase that occurs twice, its `key` the phase and how often it occurred before),
  `Budget.totals` gives the lines of the comparison table, taxes and spending below zero (rule
  `money`). `from_ledger(without=...)` leaves out the flows of the named streams (a stream books
  under its name). `ahead` gives the first 12 months of each phase from a date, `beyond_streams` the
  budget of what no stream pays over them (the streams of the plan and of `add_stream` events), for
  the Cashflows sheet and its bars. `Budget.outflows` holds the taxes as one group `taxes & SV`
  beside the spending groups. `Budget.noncash` holds the non-cash income by item, the ledger side
  `non-cash`, whatever `without` says: no cash flow, outside `net`, `surplus` and `lines`, but in
  `wealth_built` and in the line `non-cash income` of `totals`. Its group `one-off contribution`
  (the tax-free part of a severance paid into a policy, the top-up to the guarantee) counts only
  with `oneoffs`, like the severance, so the Overview and the Cashflows page never show it.
  `Budget.assets` holds the sides `draw` and `moved` by `group: item`, `moved` only with `oneoffs`
  (`_oneoff`: a one-off counts on both its sides or not at all), but always that of a salary
  conversion (rule `bav`: a `spending` group `salary conversion`, in `expenses`, the converted part
  of the gross, which a `source` books in full); `into_assets` adds the loan principal, the line
  `into assets` of `totals`. `Budget.saved` holds the `move out` of the group `savings plan` by
  plan, positive, with or without `oneoffs` (a plan is no one-off), its `moved` side nowhere: the
  surplus holds what the plan moves, so `wealth_built` stays; the line `into savings plans`
  (`budget.SAVED`) of `totals` after `surplus`, which the Flows table shows only with a plan, and
  the row of the Cashflows sheet below `surplus`. `wealth_built` is the surplus, `into_assets` and
  the non-cash income: with `oneoffs` the change of the net worth before the latent tax, without
  them too in a stretch without one-offs (`test_golden.py`, per calendar year of `rich_plan`, as the
  settlement is spread over its year, without the run rate, which reaches into the year before).
  Every note that names the non-cash income says what is in it, that it is nominal, in euros of the
  start, and the growth of equity before the capital gains tax of a sale (`bars.NONCASH_NOTE`).
- The sides stay in the code; the groups and items of the ledger and the lines of a `Budget` are
  English data in every language. The words of the engine are constants of `result.py`, marked
  `N_` (`result.WORDS`: `INCOME_TAX`, `LOAN_PRINCIPAL`, `SALE`, the suffixes `EMPLOYER`,
  `GUARANTEE`, `BENEFIT`, …; the SV parts, `ZULAGE`, `KINDERGELD`, `GRUENDUNGSZUSCHUSS`,
  `KRANKENGELD` and `EM_RENTE` are German already), those of a
  budget beside them
  (`budget.WORDS`: `TAXES`, `SAVED`, the lines of `totals`, `REFUND`). A new word of the engine is a
  constant there, never a literal. The pages say a name through `budget.said` (rule `i18n`): a
  word translated, a label, a name or a category as written, a name of parts (`<label>: employer`,
  `sale: <asset>`) part by part, `{tax} refund` by its message. Keys, `GROUP_ROLES`, a pick of
  `outflow_bars` and the tests keep the English (`test_golden` snapshots it).
