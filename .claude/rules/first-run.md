---
paths:
  - "src/dagobert/datadir.py"
  - "src/dagobert/ui/welcome.py"
  - "tests/test_examples.py"
---

# The first run

The examples that a start copies: rule `examples`. The manual: `docs/manual/start-a-plan.md`.

## Starts

- `datadir.empty`: no tracked input and no revision, or no directory (`lost+found`, `series/` and
  other files do not count; a file is not empty); `transfer` takes it for an import into an empty
  target. A start writes only there (`check_empty`, before and again under the lock of the write:
  two tabs; else `InputError` `holds a plan already`, for a file `not a directory`), creates a
  missing directory and writes one `revisions.write` with every scenario checked:
  `start_example(dir, example)` the inputs of an example as they are (`schema.Tree`, `EXAMPLE` by
  default), source `example` (`FROM_EXAMPLE`); `start_quick(dir, Quick)` the quick start, source
  `quick start` (`QUICK_START`); `start_empty(dir, born, lang)` (the CLI) its date alone, source
  `empty plan` (`EMPTY_PLAN`), the same files. The example is not rolled forward (a decision).
- `datadir.texts`: `person.born` (`sex`, `rv_since` the January of `since`), `start` the current
  month (`first_month`), the `phases` of `NEW_PHASES` (four fit the sheet on an upright phone), the
  four `REQUIRED_CLASSES` of `returns` of the example, `tax.pkv` (off: an empty plan is GKV, the
  model's default PKV); per answer a row, none for an empty or zero one; `scenarios/plan.yaml`
  (`Plan`, `SCENARIO`) in `work` from `start`, in `retired` from `Quick.stops` (the age to stop,
  else 67, `model.months.aged`) with the id `retired`, the change that `goalseek.work` moves (past
  67, `starts_retired`, `retired` from `start`); `app.yaml` the features off that the plan does not
  use (`unused`: all but `property` with a property, `job_loss` with a job loss); the manifest, so
  the next `datadir.open` writes nothing. `born` has no default: a placeholder would drive every
  age rule. `check_born` refuses one after today or before `OLDEST` (1900-01-01), ValueError: the
  CLI parser, the page and `texts` take it; `texts` raises a misfit too (`misfits`).
- The names (`NAMES`, `Names`, by `Quick.lang`: the language of the session, owner 2026-10-16,
  issue #20 with the second part of #5): data of the user, never through `_()`, ids and stems ASCII.
  English: phases `Work`, `Unemployed`, `Career break`, `Retired` (those of `engineer`), `cash`
  (`Current account`), `depot` (`Depot`), `home` (`Home`), `home-loan` (`Home loan`), `Salary`
  (cat `salary`), `Pension` (`pension`), `Living costs` (`living`), `Savings plan`, the scenario
  `job-loss` (`Job loss at <age>`). German: `Arbeit`, `Arbeitslos`, `Auszeit`, `Ruhestand`,
  `girokonto` (`Girokonto`), `depot`, `wohnung` (`Wohnung`), `darlehen` (`Darlehen`), `Gehalt`
  (`Gehalt`), `Rente` (`Rente`), `Lebenshaltung` (`Leben`), `Sparplan`, `jobverlust` (`Jobverlust
  mit <age>`). The rows: the cash, the depot (equity, `cost_basis` its value; at 0 for a savings
  plan alone), the salary (`work`), the pension (`retired`, with a salary or points: typed, else
  `estimate`, a year of `sv.pension_points` of the salary per year since `since`; `point_value` the
  `rentenwert` of the tax year of `start`), the spending, the savings plan (into the depot, `work`).
- The goals (owner 2026-10-16: a single person with a job, a possible job loss, early retirement,
  ETF investing): `stop`, the age to stop working (the change to `retired`); `lost`, the month of a
  job loss (`_lost`: `scenariofiles.lost_job` on a copy of the files in a temporary directory, its
  edits applied with `Edit.onto`, so one revision: a scenario `job-loss` that extends `plan`, no new
  job, the ALG1 stream, `job_loss` on, second in `app.yaml`, which the Explorer and the what-ifs
  of the Overview compare: `lost_job` writes it, `scenariofiles.compared`); `home`
  and `owed`, an own property at its value as 1 m² (as a `buy_property`, `sqm` 1, `per_sqm` the
  value) and its loan (`balance`, `rate` `LOAN_RATE`, the refinance rate of the model, `annuity`
  `payment`: `LOAN_RATE` and `REPAYMENT`, 2%, of the balance a year, `asof` today, `finances` the
  property). `misfits` (by the key of the field, in the language of the session: N_ messages here,
  the CLI says them in English): a stop at or before the start (`youngest`), a loss before the
  start, at or after the stop or without a salary, a loan without its property.
- The budget check (`Quick.net`, `out`, `short`): the net of the salary of the start month through
  `sv.sv_employee` and `tax.withholding_with_bonus` (Steuerklasse I, no church, a PKV premium apart:
  no new tax code), against the spending, the savings plan and the loan payment; 0 without a salary
  and a savings plan, and for a plan that starts retired.
- `datadir.open` of an empty or missing directory raises `InputError` that names `dagobert init`
  (`START`); one with other inputs but no `assumptions.yaml` stays `not a data directory`.
- `uv run dagobert init [--data DIR] [--example [NAME] | --born YYYY-MM-DD] [--lang en|de]`: an
  example (`NAME` of `ExampleName`, `engineer` without it), or an empty plan whose date of birth it
  asks for without `--born` (`typer.prompt`, again until a date reads; `cli._born`), its names in
  `--lang` (`DAGOBERT_LANG`, default `en`). Typer 0.27 takes no option with an optional value
  (`flag_value`), so `NAME` is a positional argument that needs `--example`. It refuses a directory
  with a plan or a file before it asks.

## The start page

- `ui/welcome.py`, the page `Start a plan`: `main.py` draws it instead of the page while
  `datadir.empty(DATA)`, with the navigation registered but hidden (`position="hidden"`), so a start
  goes on by `st.switch_page` to the `Overview` (an example, a quick start with a salary before 67),
  whose plan seeks when to stop working once (`outlook.SEEK_FIRST`, rule `overview`) and whose
  block `What-ifs` invites to the steps after the quick start (rule `whatifs`), or the
  `Assumptions` page; not an import. The sidebar holds the language switch alone: no mode switch
  (owner 2026-10-16), and a start keeps the mode of the browser (a new one starts simple, rule
  `mode`). Two columns, stacked on a phone: `An example`, a line and a button per example of
  `welcome.EXAMPLES` (`Start simple: …`, `Full example: …`), then `Their scenarios` (name and note
  of each, the app's defaults first, read without an open) and `Their dates` (their start months and
  the roll forward), expanders on every device; and `Quick start` (`QUICK` and `overview.explore` of
  the plan it writes in one paragraph: no page that records; owner, 2026-10-13: people configure
  once and explore): `Date of birth` (a text field with the decimal keypad of a phone, day first
  with dots or ISO, `welcome.birth` through `fields.day` and `check_born`: bare digits stay unread,
  `20051986` could be either order; below it the date in words with the age, `welcome.said`, `Born
  20 May 1986, age 40.`, so a slip of the order shows, or why it does not read; without a date why
  the start is off: a calendar took many taps back), `Sex` (none: the model's `m`), the numbers of
  `ANSWERS` two to a row (`_row`; `fields.parse` of `field`: at least 0, the year from the birth to
  now, an age up to `goalseek.WORK_AGE`, a month; the error below; below the points `pension_note`,
  their estimate or `NO_POINTS`; past 67 `RETIRED`: the salary and the savings plan pay in `work`),
  `Your goals` (`GOALS`: `Stop working at age`, placeholder 67, and `Check a job loss in (month)`,
  both off past 67; the toggle `I own a property` with `HOME`, `Value of the property €` and `Loan
  still owed €`, below them the payment that the plan takes, `PAYMENT`), the toggle of the PKV, the
  misfits below their fields (slots), the warning `budget` while `Quick.short` (`BUDGET`, without a
  salary `UNPAID`, with a PKV `PREMIUM`), `Start my plan` (primary; off while the date or a field
  does not read or a goal misfits) and a caption with the count of the features off. The path of
  the data directory is the last caption. A failed start shows `Not started: <dir>: <reason>`
  (`ValueError`, which `InputError` is, and `OSError`: read-only, locked, a plan there by now). The
  container's empty `/data` volume reaches it; a bind mount that Docker created is root's, so the
  README makes the directory first. Below the columns `An export`: the import of `Export and
  import` (`ui.transfer.import_zip`, rule `transfer`): every file `add`, one revision `import
  <zip>`, or with the revisions of the zip its history (`_take_history`); then the Overview. The
  page speaks the language of the session (rule `i18n`: the date in words, `20. Mai 1986`; the
  points of `pension_note` as `9.24` in both languages), the names and notes of the examples as
  written (each line names its language).

## Tests

- An empty plan and a quick start render all pages in both modes
  (`test_pages_render_an_empty_plan`): no asset gives no recorded net worth
  (`history.actual_values`), an info for the sunburst, no category a text column in the Spend grid.
  `test_examples`: the date alone is `start_empty` file by file, the month of 67, a salary pays a
  pension and the work seek finds a month, the estimate, the names per language, the goals in one
  revision (the job loss lasts less than the plan), the misfits, the budget check (the example of
  issue #20). `test_ui`: the start page per start (the seek once on the Overview, the mode switch
  after the start only), the misfits and the warning of the form.
