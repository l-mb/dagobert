---
paths:
  - "src/dagobert/engine/{core,income,profit,simulation,state}.py"
  - "src/dagobert/model/assumptions.py"
  - "src/dagobert/ui/{knobs,scenario_overrides}.py"
  - "tests/test_{income,scenario_overrides}.py"
---

# Growth of the pay of a phase

`scale.growth` (issue #11, owner 2026-10-16): a real growth per year of the salary and the profit of
a phase on top of the index of their streams and of `scale.salary`, so two jobs grow apart without
a second index. No migration: a plan that gives a phase an index of its own keeps working. The rest
of a run: rule `engine`; the sliders: rule `explorer-sliders`; the Overrides tab: rule
`scenario-overrides`. The inputs: `docs/manual/configuration.md` (`scale`), in plain English
`docs/manual/models.md`, `explorer.md` and `overrides.md`.

## Input

- `model.assumptions.Scale.growth`: `{<phase>: rate}`, a `Percent` above -100% (`gt=-1`), 0 where
  absent. `Assumptions._phases_named` refuses an unknown phase at `scale.growth.<phase>`
  (`unknown_phase`), `references.SETTINGS_USE` counts its keys as uses of the phase, so a rename
  follows. `mode.EXPERT` lists it: simple mode shows its slider only when moved or set in a file.

## Engine

- `Core._earned(s)`: the factor of the stream, `scale.salary` and `(1 + growth) ** (year −
  since.year)` of the phase of the month; `Income._salary_nominal` and `Profit._profit_nominal`
  take it. `MonthState.since`: the first month of the phase in a row (`Engine.run` keeps the one of
  the month before while the phase holds, also over a change into the phase that holds), at the
  earliest `start` (`Core.__init__`): the amounts of the file are those of the start, so a growth
  before it is in them. So the first January after the phase starts is the first step (a start in
  January steps the next one), as `pension_growth` steps from the start year.
- A phase that comes back starts again at the amounts of its streams, its steps from its new start
  (owner 2026-10-16: each start; a decision of the design: a return is a new job at the amount of
  its row, the index carries the wages across the gap).
- What follows it: a share `of` another (a bonus) takes it once, through its own `_earned`
  (`_salary_gross` takes the factor and the index of its base, not its scale); `last_salary`, so
  ALG1 and Krankengeld after the phase; the SV, the points, a conversion, the PKV subsidy. Not:
  ALG1, a pension, other income; `core.pays` and `Profit._running` (a factor or `scale.salary` of 0
  switches the pay off, a rate cannot); `carry._gross` (the months before the start); the roll
  forward, whose `rebase` keeps the amounts while `since` moves to the new start: the steps start
  again (a gap, as of `pension_growth`, rule `rollforward`).

## Pages

- Explorer: `knobs._growth_knob`, `Raises in <label>` right after `Salary and profit in
  <label>` (`_salary_knobs`: a phase with pay in the run), group `Income`, `sliders.RAISES` (-5% to
  8% in steps of 0.1%, a step of the sensitivity 0.5%). Its lever and its dial come with
  `explorer._Picked.slide`, the lever in the chart of the plan (`explorer.PLAN_KEYS`: `scale`), the
  dial `Income: Raises in <label>`. The help says from when it steps and what it leaves.
- `budget.regular_salary`, the median month of a phase, lies above the start with a growth, so the
  gross of the salary slider and of the Overrides tab does too (their helps say so, as of an index).
- Overrides tab: `scale_form` gives a growth per phase after the salaries, under `Raises per year`
  (side by side with its salary, each pair took a heading of its own, checked in Chrome):
  `Raises in <label> %` (`fields.entries(..., EMPTY_ZERO)`: empty counts as 0,
  `ScaleForm.leaves` shows `0 (default)`), shown in percent and kept in the file as a fraction
  (the `PERCENT` unit of `fields.parse`; `ScaleForm.stored` converts the salary only); of a phase
  without pay in the run only while the chain holds it (`held`, by key path). The Scale part shows
  its fields in both modes, as before.
- Cashflows (rule `cashflows`): the plan rows of the sheet (`cashplan`) stay at the amounts of the
  file, the level of the start; the rows of the run (the taxes and SV of the first 12 months of a
  phase, from the ledger) and the Flows page take the growth.

## Tests

`test_income.py` (relations: a growth of 0 is the run without it, the steps each January from each
start of the phase, of a salary and a profit, other income stays; on top of the index and the
scale, the bonus once, ALG1 on the grown salary), `test_loader.py` (an unknown phase),
`test_references.py`, `test_ui_explorer.py` (the slider after the salary, its lever and dial),
`test_scenario_overrides.py` (the field, its save), `rich_plan` of `test_golden.py` (2% in the part
time from 2036: the salary, the tax of the bAV lump sum of 2040, the pension points after it).
