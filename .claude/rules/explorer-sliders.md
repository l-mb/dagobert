---
paths:
  - "src/dagobert/ui/{knobs,sliders}.py"
  - "tests/test_ui_explorer.py"
---

# Explorer sliders

The sliders and switches of the Explorer sidebar: the catalog `knobs.py`, the units and groups
`sliders.py`. The page, its table, status line, goal seek and phone layout: rule `explorer`.
The `scale` overrides that the sliders write: `docs/manual/configuration.md`.

- Sliders in sidebar groups, each with a hover help from the `knobs.knobs` catalog (that of a field
  of the Assumptions page starts with its model description, `_about`; a key of the inputs reads
  through `model.base.named`: `bAV return`), become assumption overrides (the world, and through
  `scale` the plan: salary and profit per phase with a salary or a profit in the run, group `Income`
  (`sliders.SALARY`, German `Einnahmen`, the key stays `scale.salary`), in the order of `phases`,
  named by its label, spending as a whole (group `Total spending`, `sliders.ALL_SPENDING`,
  `scale.spending`, core in simple mode; the one group a desktop opens) and per category (`Spending
  by category`, closed everywhere); through `shift` and `events` the dated items with an `id` of the
  first chosen scenario: a month slider per group (its position shows the month with the age then,
  `Knob.reached`, `2050-03 (age 72)`, so a user who thinks in ages finds `stop at 50`; also in the
  dial text), and one per `gross` or `price`; the price of a purchase with a loan starts at the
  lowest price that the loan allows, `_least` and `LEAST`, as the model refuses a loan above the
  price with tax and costs and the goal seek would run into it; through `assets` the contribution of
  an `av_depot`; in `Savings plans` one slider per savings plan of `cashflows.yaml` and of the
  `add_stream` events of the first chosen scenario, `scale.savings.<name>`, in euros per month like
  the salary: `scale` the rate of its first row, `-amount / every`, in steps that divide the rate,
  at most 50 € (a quarterly plan of 100 € steps by 33 €, so the slider returns to its file value),
  up to twice the rate or 1,000 €; `loader._plans_of` drops such a factor for a chosen scenario
  without the plan, the explorer's overrides only), start at the values of the first chosen
  scenario, run the chosen scenarios, can save the overrides as a scenario file (and then links to
  it on the Scenarios page), seek on request the value of one slider, or the factor `scale.spending`
  of all spending, at which P(broke by 90) meets a target, in the chosen scenarios with the sliders
  applied (`goalseek`), and start each scenario tab with the note of the scenario
  (`ui.scenario_note`, also in its `(as saved)` tab) and end it with the failure anatomy (`anatomy`)
  and two sensitivity charts, the plan (`scale`, `shift`, `events`) and the assumptions: every
  slider one step down and up around its position. The groups start closed (a desktop opens `Total
  spending`), keyed by their id (`Knob.group`, its words `sliders.GROUPS`), the plan first (`knobs`:
  all spending, spending by category, income (salary and profit, then the income indices and
  `Pension growth`), savings plans, events, assets, then markets (`Inflation`, the indices that
  costs follow, the returns), gold and crypto, the spending rule, care, allocation, spreads; the
  spending rule its cut and, with `base: no_pay` only, as the model refuses an increase without it,
  `Increase in good months` and `Increase when wealth rises above`, `knobs.CEILING` from 100%, the
  trigger below it, `TRIGGER`, while the file turns the increase on, as the model refuses a ceiling
  at or below the trigger then; a file value widens a range, also an unset ceiling of 0 or a trigger
  above 95%, and an increase that its slider turns on keeps the trigger range, so a position or a
  step of the sensitivity can reach the trigger: `Status` and rule `analyses`; with VPW, rule
  `spending`, `VPW growth` (`sliders.TREND`, 0 to 8%), `Spend down to age` (`AGE`, 80 to 110) and
  `Spending floor` (`EUR`, `goalseek.FLOOR`) instead, each a lever and a dial, and the help of a
  flexible category adds `knobs.VPW_SHARE`; `loader._plans_of` drops `spending.vpw` for a chosen
  scenario without VPW and the band, `loader.BAND`, for one with it). `Gold and crypto` follows
  `Markets` as a closed group: Streamlit nests no expander in an expander, so no fold can hold
  groups. The class of a gold or crypto asset of the first chosen scenario has its mean, spread and
  `equity_correlation` side by side in `Gold and crypto` (`knobs._holding_knobs`,
  `sliders.GOLD_CRYPTO`; a crypto class on wider ranges, `sliders.CRYPTO_RATE` and `CRYPTO_SPREAD`),
  and their help gives the growth of the median path at the values of the scenario
  (`returns.median_growth`: a spread pulls it below the mean, `fixed` compounds the mean, a
  decision) and asks for conservative crypto values; without such an asset a class shows as any
  other. An index slider (`{index} growth`, `knobs._index_knobs`) sits in `Income` when an income
  stream (salary, ALG1, pension, other income, profit) follows it and no cost does (an expense or
  `care.index`); an index that only costs follow, both or none follow stands in `Markets` after
  `Inflation` (a price level, not a pay lever; decision). Its help names the streams that follow it
  by their `index` field (`knobs._followers`, `LISTED` names, then `and n more`): a salary row of
  another phase may follow `cpi`, so `salary growth` moves only the rows with `index: salary`. A
  slider is off in a model that does not read it (`Knob.models`): a spread and a correlation act in
  `montecarlo`, and in `historical` for a class that it draws (`returns.historical_draws`, such as
  `bitcoin`, not the replayed `gold`); the inflation and the mean of a class whose series
  `historical` replays (`returns.historical_replays`: equity, fixed income, a held `gold`) act in
  `fixed` and `montecarlo` only, and their help ends with `NOT_HISTORICAL`; care cost and duration
  not in `fixed`, which draws no episodes. An off slider keeps its position for the next model but
  joins neither the overrides, the `moved` list and the save nor the levers and the dials. A yes or
  no is a `Switch` (`knobs.switches`): `Invest the rest` (`invest_rest`) in the group `Allocation`,
  which shows it without an allocation too, a toggle that joins the overrides, the `moved` list
  (`Invest the rest on → off`) and the save, no lever and no dial; `Realize gains` (`tax.harvest`,
  rule `harvest`) alone in the group `Taxes`, which follows the groups of the sliders; on a phone a
  caption below gives its help, as for `Nominal euros`. The help of a savings slider says that the
  rate moves the chance to run out little while the rest is invested (by the age of the plan,
  `goalseek.broke_age`), and that the goal seek assumes one crossing. `explorer._Picked` collects
  what the sidebar sets. A slider's widget key holds its scale, range and file value (`Knob.key`): a
  crypto class without its asset (no scenario chosen) takes the narrower `sliders.RATE`, and a
  stored 60% would exceed it. The select `Model` offers `historical` only with the equity series
  (`runs.models`), else a caption below it names the Data page, and a session that held it falls
  back to `montecarlo`; it shows `MODEL_NAMES` (`Monte Carlo`) with `MODEL_HELP`. The table and the
  charts show euros of the simulation start. The switch `Nominal euros` below `Paths` shows nominal
  euros without new runs, with a help icon (`explorer.NOMINAL_HELP`). On a phone a caption below it
  gives the help instead: the icon of a `help` sits in the label of a toggle, and a tap on it flips
  the switch. `Reset sliders` (all keys of `Sidebar.keys`, `sliders.forget` in `on_click`) ends the
  controls of the page in a row `explorer-actions` that stays at the bottom of the sidebar while the
  sliders scroll (`ui/page.css`). The controls sit in the box `explorer-sidebar`, which the sticky
  row and strip end with: below it the language switch of `main.py` scrolls clear of them (rule
  `i18n`).
- The widgets keyed `sliders.KEY` keep their values across pages (`main.py`): `keep` at the end of
  every run stores them and the keys of those that the run drew (`Carried`: the write that keeps
  the others as plain state raises for a widget of the run), `carry` at the start writes back those
  that the run before did not draw, all of them on a run that opens a page (`ui.arrived`).
  Streamlit drops a widget that a run does not draw (a page switch those of the page before; a
  closed tab, simple mode, another first scenario), and a toggle or a select that comes back shows
  its kept value only after a write: present but not drawn, one hidden for two reruns showed its
  default (checked in Chrome). A widget of the run before gets no write: a write tells the browser
  to take that value, and with `runner.fastReruns = false` a key press that landed while the next
  run began went back a step (five ArrowRight presses 300 ms apart ended one step short in three of
  four tries, checked in Chrome 2026-10-16, when `main.py` wrote every key in every run; none
  after). `forget` drops keys from `Carried` too
  (`test_a_slider_keeps_its_position_while_no_run_draws_it`).
