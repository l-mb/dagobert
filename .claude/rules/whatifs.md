---
paths:
  - "src/dagobert/whatifs.py"
  - "src/dagobert/ui/whatifs.py"
  - "tests/test_whatifs.py"
---

# What-ifs

The steps after the quick start (owner 2026-10-16, issue #14; rule `first-run`): a first-time user
checks a what-if without model knowledge. The block on the Overview: rule `overview`; the menu on
the Scenarios page: rule `scenarios`; `away`, `lost_job` and `compared`: rule `store`. The manual:
`docs/manual/scenarios.md` (`Check a what-if`, `Lose the job`), `overview.md` (`What-ifs`).

## The steps (`src/dagobert/whatifs.py`)

- Each a frozen dataclass (`Step`: `main`, `name`, `stem`, `misfits(dir)`, `edits(dir)`): a
  scenario of its own that extends the main one, last in the comparison of `app.yaml` with the
  features that it needs on (`scenariofiles.compared`), one revision through `scenariofiles.act`.
  `misfits` by the key of the field, in the language of the session (N_ messages; the months of
  `datadir.LOSS_EARLY`, `LOSS_LATE`); `edits` raises ValueError with them first. The stop of the
  main scenario is the origin of `goalseek.work` (`stops`; None without that change: no check).
- `Earlier` (`Stop earlier`): the `shift` of the id of the change out of work (`goalseek.work`),
  as the work slider of the Explorer moves it. A child's shift replaces its parent's
  (`loader.merged_overrides`), so its months count from the month of the file, the main one's own
  shift added. Refused: an age at or after the stop (`NOT_EARLIER`), one whose month lies before
  `Dial.low` (`TOO_EARLY`, with the youngest age, `_youngest`), a plan without the change (its
  `NoChange.said`). `ages`: the youngest age and the age at the stop; `months`: the month of the
  stop before and after, which the save guard says (the dialogs, below).
- `Loss` (`Lose the job`, a `scenariofiles.JobLoss`): `lost_job`. Refused: a loss before the
  start or at or after the stop, a plan without a salary in `cashflows.yaml` (`UNPAID`), a new job
  not after the loss (`NEW_JOB_EARLY`).
- `Course` (`Take a course`): `months` from `start`. After a job loss (`loss`): `jobless` with the
  new job in the month after the course, and an `add_stream` of an ALG1 row with `training: true`
  in the phase of unemployment up to that month (ALG1 bei Weiterbildung, rule `alg1`: the month
  books under the ALG1 row and uses half of the days). Else a career break (`BREAK`, `alt`, the
  phase of a new plan; ids `course`, `after-course`) that pays nothing. Costs (euros of the start)
  an expense over its months with `deduct: work` (rule `deductions`), `Feature.DEDUCTIONS` on:
  `costs`, whole cents a month that add up to the cost, the cents that do not divide one more in
  the last month, an `add_stream` of its own there.
  Refused: a start before the start, an end after the stop (`COURSE_LATE`), a loss without a
  salary.
- `Business` (`Start a business`): from `start` the phase `BUSINESS` (`self-employed`), no return
  (`away`: the salary limited as for a job loss), and an `add_stream` of a `self_employed` stream
  (`profit`) in that phase, so the next change of the main scenario ends it, the stop of work or a
  job loss (the caption: the salary and the savings plan stop in it, as those of a quick start pay
  in `work` only); `tax.self_employed` at its defaults (`rv: none`, no Krankengeld; rule
  `self-employment`); `Feature.SELF_EMPLOYMENT` on. Refused: a start before the start or at or
  after the last change of phase of the main scenario (`_last_change`, `BUSINESS_LATE`), whose
  phase it would replace to the end of the plan. So it starts after a job loss without a new job
  too (owner 2026-10-17), which is the stop of work (`goalseek.work`), and runs to the next
  change, the pension. `founded` writes `gruendungszuschuss: true` on the stream (rule `alg1`).
  `founding(dir, main, month)`: the claim of the main scenario before the month
  (`simulation.before`, `engine.alg1.refusal`), a `Founding` (`days`, `why`), None without a
  claim (no job loss before).
- `Purchase` (`Buy a property`): a `buy_property` (rule `engine`) with the Grunderwerbsteuer of
  `land` (a quick start writes no `tax.land`), `COSTS` 5% of the price (notary, land register,
  broker: those of `buy-home`), `UPKEEP` 1% a year (a rule of thumb), a loan of the cost less the
  own funds at `datadir.LOAN_RATE` with `datadir.payment` (the loan of the property of a quick
  start), none where the own funds pay it all; the ids those of the scenario
  (`scenariofiles.unique`); `Feature.PROPERTY` on. `rent` (the rent and the costs of the current
  home, euros of the start a month; a quick start holds it in its one spending) comes off the
  spending `stream` from the month of the purchase: a `set_stream` of its amount less the rent,
  with the id of the purchase (a shift moves both); 0 writes none. `spending`: the monthly
  expenses of the main scenario that run then (no health premium, cost of a let property or
  deduction), at the amount of the last `set_stream` up to then; `living` the default, the living
  costs of a quick start by `datadir.NAMES` in either language, else the largest. Refused: a
  month before the start, own funds beyond the cost (`OWN_MORE`; without a Land beyond that at
  the highest Grunderwerbsteuer, `OWN_MOST`, so a typo shows at once), no Land (`NO_LAND`), a
  rent without spending (`NO_SPENDING`) or above its amount (`RENT_MORE`).
- The names of what a step adds (streams, the property, its loan) through `pgettext("data", …)`,
  the label of a phase through `pgettext("phase", …)`: user data in the language of the session,
  which the leak check of user data does not count.

## The dialogs (`src/dagobert/ui/whatifs.py`)

- `STEPS`: per key the label of the button, also the title of its dialog, and the dialog.
  `menu(dir, Plan, holder, where, inline=)`: a button per step in `holder` (`inline`, the
  invitation of the Overview), else in the popover `Check a what-if` (on a phone its buttons in a
  row that wraps), which a tap on one closes (`fileactions.shut`); nothing without a main
  scenario. Keys by the page (`where`: the pages render in one test script); the popover's also
  by the count of the scenario files: after a step it is a new one, closed (Streamlit 1.65 opened
  the old one again after the page switch of the step).
- A dialog takes the language of the session first (rule `i18n`), says what the step writes in a
  caption, then its fields: `_Form.typed`, a text field (`decimal-`: the keypad of a phone) read by
  `fields.parse` (`MONTH`, `AGE`, `MONTHS` 1 to 60, `EUROS`, `PRICE` above 0), its default as the
  field shows it, why it does not read below it, then a slot for its misfit; the name (placeholder
  `<step> at <age>` of the month, numbered `(2)` where taken, the file name its slug, numbered
  `-2`). `_finish`: the misfits in their slots, then `fileactions.confirm` (button `Add and
  compare`; source `<page>: what-if <stem>`; `why`: `Fill in the fields above first.` or `Change
  the fields marked above.`; the toast `Added <name>: …`; `page="Overview"`, which
  `st.switch_page` opens, also from the Overview). A field that does not read or an empty one
  that the step needs (`Price €`) gives no step and so no misfit; an empty Land is a misfit of
  the step. `lines` (`confirm`, `fileactions.listing`): a line of the guard that a step words
  itself, the `shift` of `Stop earlier` as `Stop working 2053-06 (age 67) → 2046-06 (age 60)`
  (`ui.at_age`, as the work slider of the Explorer), never `shift retired -84`.
- `Start a business` (`_founded`): after the start field, where `founding` finds a claim, the
  checkbox `With the Gründungszuschuss` (help: what it pays), on where `why` is None, else off with
  the reason below it (`FOUNDING`: the days left or no ALG1 up to a month before); keyed by that,
  so a start that changes it shows the new default.
- Defaults: a month the next January, `EARLIER` (5) years before the stop, `COURSE_MONTHS` (6: so
  many months of a course in a row extend a short claim), costs 0, the profit the gross of the
  first salary, the Land the `tax.land` of `assumptions.yaml`, the rent 0. The purchase names its
  cost and the payment of its loan below the fields once a Land is chosen; a select `Spending that
  holds the rent` only where the plan has two or more (`_spending`).

## Tests

`tests/test_whatifs.py` on the fixture `quick` (`conftest.py`, `builders.QUICK`): the comparison
entry, each step as runs (fewer months of work, ALG1 in the course months and the salary after
them, less tax with costs, the profit in the new phase, the property from its month, the loan,
the rent equal to a `set_stream` by hand), the costs to the cent, the spending of a rent, the
misfits, the guard line of `Stop earlier`, each dialog one revision as a desktop and a phone, the
Land and the own funds marked at once, the Gründungszuschuss after a job loss with and without a
new job (`founding` at 270 and 120 days, its six months in the run and on the sheet, without a new
job the business to the stop, the box on and off with its reason).
`test_ui_overview`: the invitation
and the row of a what-if. `test_scenarios`: `lost_job`.
