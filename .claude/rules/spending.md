---
paths:
  - "src/dagobert/engine/{core,income,settlement,simulation}.py"
  - "src/dagobert/model/assumptions.py"
  - "tests/test_model.py"
  - "tests/test_spending.py"
---

# Spending rule

`spending` of `assumptions.yaml` (`model.assumptions.Spending`): the band (the cut and the
increase) or VPW on the flexible `categories`, and the age curve. The rest of the engine: rule
`engine`; the inputs: `docs/manual/configuration.md`, in plain English `docs/manual/models.md`
(`Spending rules`). No law: planning methods. Individuals only.

## The band

- `Core._update_spending_rule`, first in a month: per path the liquid wealth of the month before
  against `Core.reference` (start-year euros, at the deflator of the year): `reduced` below
  `trigger` times it, else `raised` above `ceiling` times it (0 switches each off), and `_index`
  takes 1 − `cut` or 1 + `increase` on the `categories`. `base: start` acts in every month and arms
  in the first (`spending.reference` when set). `base: no_pay` acts in a month after a month that
  paid no salary and no profit (`Core.earns`, set at the end of `Income._apply_streams`:
  `salary_real` not 0 or a running business, `Profit._business`, so ALG1, a pension and
  `other_income` are no pay; the first month by `core.pays` on the phase of the start, the
  predicate of the goal seek), so a month lags its pay by one. It arms in the first such month (the
  first month of the run with `spending.reference` when set) and again after `REARM` (12) months
  of pay in a row (`Core.paying`): a late bonus suspends the month after it and keeps the
  reference. A purchase keeps the reference too (a decision): it can switch the cut on, also across
  the price slider of the explorer.

## VPW (variable percentage withdrawal)

The design of 2026-10-14, whose nine answers the owner took that day (owner 1 to 9). Sources: the
Bogleheads wiki and forum (`Variable percentage withdrawal`, threads t=120430, t=284519; the wiki
behind a Cloudflare check on 2026-10-14, read through the search index), finiki.org, the Credit
Suisse Yearbook 2019 press release (equities just over 5% real since 1900; the 1.8% of bonds is the
forum's).

- Inputs: `Spending.vpw`, `model.assumptions.Vpw`: `growth` (real, default 3%, at most 10%),
  `horizon_age` (100), `floor` (start-year euros a month, 0). `Vpw.rate_at(age)` is
  `min(pmt(growth, max(horizon_age − age, 1)), VPW_CAP)`, `pmt` the annuity due (the payment at the
  start of a year): 60/40 (3.72%) gives 4.97%, 5.39%, 6.92% at 65, 70, 80, the table of the forum
  (5.0, 5.4, 6.9; the ordinary annuity would give 5.2, 5.6, 7.2); `VPW_CAP` 10%, the Bogleheads
  cap. No growth from the allocation, no rate table, not `person.horizon_age` (owner 1, 2). The
  model refuses at `vpw` a `base` other than `no_pay`, a `trigger` or `increase` above 0 and empty
  `categories` (`Spending._rules_fit`).
- State (`Core._init_spending_rule`, `(paths,)`): `budget` nominal (NaN before), `budget_year`,
  `settled` (the regular bill of the last December, `Settlement._settle_december`: `_settle_year`
  and every late round, less `oneoff_tax`, the Fünftelregelung part of the settlement: a refund of
  the withholding on a lump sum goes to the wealth, not to the flexible spending, and so does the
  refund of a loss carried back, paid before it, rule `rental`; 0 in the first year), `cash_mark` (`Engine.run` copies `cash` after `_apply_returns`, before `_service_loans`),
  `liquid_prev` (`_update_spending_rule` keeps it and returns: the band's state is unused).
  `reduced` and `raised` stay False, so `_index` and the buffer need no guard.
- `Income._pay_flexible`, after `earns` of this month and before `_record_earned` (owner 4: the
  month itself, no lag): `Core._flexible` is a `managed` expense of a flexible category, which
  `_pay_streams` skips with its `_accrue`. In a month without pay (`free`): a new budget, `rate_at`
  of the age of January (`_january`: the first month of the run in its first year; one scalar, the
  rate is set once a year, also in a budget that a later month takes) × `liquid_prev`, in the first
  free month of a calendar year (`budget_year`) and after `REARM` months of pay (`paying` counts
  here under VPW); then `wanted = (budget − settled) / 12 + cash − cash_mark − MonthFlows.oneoff`
  (owner 3: the loans, the other streams, the GKV, the withholding, the premium of a Basisrente,
  `_policy_flows`, which moves the cash without a flow), `F = max(wanted, floor × deflator)`, no cap
  above. Each active flexible stream pays monthly its run rate (`_nominal / every`: phase factor,
  `scale`, age curve, index) times `F / P`, `P` their sum (owner 9: twelfths, no January lump); `P`
  0 spends nothing, also not the floor. A month with pay pays the plan (`_pays`, `_accrue`).
  `_deduct` takes what it paid.
- `MonthFlows.oneoff`: what a lump sum of a policy (`_pay_out`, also through `_severance`, which
  returns its net) and the `lump_sum` of an Altersvorsorgedepot (`_av_paid(at_once=True)`) paid
  into the cash; they go to the wealth and the next budget. The events (a purchase, a severance, an
  inheritance) come before the mark.
- `months_cut` counts the months without pay (with `P` above 0) at the floor (`wanted` below it),
  `months_raised` the others with `F > P` (owner 6), never both: `Cuts` and `Raises`.
- Ledger (rule `ledger`): no flow, the flexible streams book their rows with what they paid. No
  marker. The cash buffer counts them at their plan. No draw: a seed pairs the paths.
- Elsewhere: the floor dial of the goal seek (rule `goalseek`), the sliders and what the loader
  drops of them (rule `explorer`, `loader._plans_of`), the floor in the roll forward (rule
  `rollforward`), the form (rule `assumptions`), `engineer` `vpw.yaml` (rule `examples`).
- Gaps: the budget takes the liquid wealth after the latent tax (Bogleheads before tax; the
  harvest raises it a little); the first year pays its own bill on top, a year whose tax jumps
  overspends the difference; no pension bridge (the spending jumps at the pension), ALG1 raises `F`
  while it pays; the loan service comes out of the budget while the loan sits outside `liquid`; a
  yearly bill of an essential category lands in its month (the floor holds it); no `Required
  Flexibility`, no annuitization at 80, no legacy, no couples.

## Tests

`tests/test_spending.py` (relations; VPW: a twelfth of the rate of the wealth, monthly whatever
`every`; the fixed draws; twice the wealth; an older start; the PMT invariant, cash at the 3% of
`growth` spends each January as the one before to 0.1%, faster rises, slower falls; the floor; a
month with pay, a late bonus, a January with pay; a lump sum, an Altersvorsorgedepot, a purchase,
a Basisrente premium; the counts; the bill of a year in the next), the model in `test_model.py`,
`gkv_plan` of `test_golden.py`: VPW (3%, a floor of 1,000 €) on `Leben` from 2029, at its floor
until the pension of 2044, above its plan after; the lump sum of 2035 leaves its month at the floor.
