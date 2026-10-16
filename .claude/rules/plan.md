---
paths:
  - "src/dagobert/model/{plan,events}.py"
  - "tests/test_model.py"
  - "tests/test_loader.py"
---

# Checks of a plan

The checks of `model.plan.Plan` across the inputs: what a run takes, refused at load and not in
the run, where a bare `ValueError` ended `dagobert run` in a traceback. Each error lies at the key
path of its use, so `origins.plan_error` names the file and the line (rule `problems`). The
messages are English, as every input error. The inputs: `docs/manual/configuration.md`.

- Purchases: `Plan._ids` adds the ids of a `buy_property` to the properties and loans;
  `_purchases_fit` refuses at the event an id that an asset or another purchase has, and a dated
  sale, repayment or a stream with `repays` or `property` (`_named_assets`, from its first month
  by `start`, `end` and `phases`, `_first_pay`) that names one in or before the month of the
  purchase. `_let_known` refuses a let property without the fields of its AfA (rule `rental`).
- `_stream_updates_fit`: a `set_stream` sets the field of the amount that each row of its name
  reads (`Stream.amount_key`: `gross` of a salary or a pension, none of ALG1 or a derived salary,
  else `amount`; `premium` of a BU policy only, which takes no `factor`, rule `disability`), and
  each row stays valid with it (`SetStreamEvent.applied`, which the engine takes too: `model_copy`
  skipped the validators, and an expense set above zero invested money that did not exist). The
  error is at `events[i].amount`, `.gross` or `.premium`.
- `SetStreamEvent.targets`: the rows of its name that run in its month by `start` and `end`, else
  the next one that starts. A later row keeps its values: a change after the event. The engine
  (`Events._set_stream`, with the `end` that an `end_streams` set) and the scheduled changes of
  the Cashflows page (`cashplan._Events`, rule `cashflows`) take it. `_stream_updates_fit` refuses
  at `events[i].at` one of a concrete scenario without a target (`STREAM_ENDED`: every row of its
  name ended before it; a template leaves it to a child, which may add a row).
- `_sales_fit` (`_sale_problems`, `SALE`): a field of the other kind of asset at the first such
  field (`SellEvent.misfits`), a property sale at `price: 0` (a gift) with `taxable` at
  `events[i].taxable`: it booked the whole basis as a §23 loss.
- `_events_in_time`, of a concrete scenario only (its children may drop the event of a template):
  an event dated before `start`, unless it is one of `model.events.STATE_EVENTS` (`set_stream`,
  `add_stream`, `end_streams`: they apply in the first month), and a `fund_policy` or the `bav`
  part of a `severance` dated after the `matures` of its policy (in that month it still funds:
  the events come before the payout). The error is at `events[i].at`. The engine keeps its own
  raises (`Core._init_streams`, `Events._policy`) for a plan that is built around the checks.
- `_fundings_fit`: a `severance.bav` pays into a company pension, a `fund_policy` into a Basisrente
  (`FUNDING`, `_fundings`, rule `deductions`). The error is at `events[i].bav.policy` or `.policy`.
- `_repayments_on_every_path`: a stream that `repays` a loan pays alike on every path, as the loan
  is one: no sale at `liquid_below` ends it (its `property`, or `end_tagged` and a shared tag) or
  starts it (`after_sale_of`). An age is the same month on every path. The error is at
  `events[i].when`. The engine repays the least that a path of the stream pays
  (`Income._stream_flow`), so the spending cut of its `cat` on some paths lowers the repayment on
  all.
- Tests: `tests/test_model.py` (each check, a template), `tests/test_loader.py` (the file and the
  line), the engine side as relations in `tests/test_engine.py`.
