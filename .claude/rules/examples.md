---
paths:
  - "src/dagobert/examples/**"
  - "src/dagobert/datadir.py"
  - "src/dagobert/ui/welcome.py"
  - "tests/test_examples.py"
---

# Examples and the first run

- `src/dagobert/examples/<name>/` (package data, `datadir.EXAMPLES`, so the image holds it; the
  names in `datadir.ExampleName`, which the CLI argument and `welcome.EXAMPLES` take) is a complete
  data directory of a made-up person: `manifest.yaml` at the current schema, the YAML inputs,
  `app.yaml`, `history.csv`, `actuals.csv` and `prices/` for its trades, no `revisions/`. The
  README screenshots come from `engineer`, which `dagobert init --example` starts
  (`datadir.EXAMPLE`); `starter` is the simple one (the owner's choice: less intimidating to
  try than the full example).
- The README screenshots, `docs/screenshots/*.webp` (Pillow, quality 80, about 500 KB in all;
  `cashflows.webp` comes from `starter`, the others from `engineer`, `assumptions.webp` is new):
  clips of the main column (the Overview and the Explorer with the sidebar) of a render 1280 CSS
  px wide and as tall as the page, light theme, and the Overview on a phone in portrait (412 x 915
  at device scale 2), by the skill `app-check` on `dagobert init --example`. A clip ends at the
  end of a section (the Overview after `Needs attention`, the Cashflows page after the sheet), never
  at a bare heading. Take them again when a page that they show changes visibly; keep the total
  well under 2 MB.
- `engineer/`: born 1986, one child (`children_born`: 2016-04-01, `until` 2039-10, the end of its
  studies, `kindergeld: true`: the engine pays it, rule `children`), the mother as a relative
  (`mother`, `Mother`, born 1956-05-02, a parent), PKV, a rented home and a rented-out flat with a
  loan, start 2026-10. Its phases are those of a new plan (`datadir.NEW_PHASES`: `work`,
  `unemployed`, `alt`, `retired`, labeled `Work`, `Unemployed`, `Career break`, `Retired`), then
  `new-job` (`New job`, the job after the job loss of `severance`: the bAV of the old employer gets
  nothing there) and `freelance` (`Freelance`). It holds every kind of asset, stream, event and
  phase: salary with a raise row and a bonus (`of`, a payout-ratio index), VL into the loan, the let
  flat (rule `rental`: `bought` 2018-03, `building_share` 0.7, `afa` 0.02, completed in 1972;
  `flat-loan` `finances` it; `Rent from the flat`, the cold rent, and the Hausgeld that the tenant
  does not pay back, 60 €, name it in `property`; the `Erhaltungsrücklage`, 40 €, does not: a cost
  only when spent; the 150 € that the tenant pays back are on neither side; a loss against the
  salary), ALG1, voluntary contributions, the pension from points, a company pension under §3 Nr. 63
  EStG (`bav`, `fuenftel: false`, in `work`) and a Basisrente with a `premium` of 200 € in `work`
  and `new-job`, an Altersvorsorgedepot (its Kinderzulage up to 2039), the deductions of rule
  `deductions` (`tax.werbungskosten: 1900`; `Gifts and donations` half donations, `Household help`
  100 € `household`, `After-school care` 200 € `childcare` to 2030-08, whose deduction ends with the
  14th birthday in April), a term deposit, a building savings contract (`update_every: 12`), a depot
  with trades and Vorabpauschale rows, a money-market ETF, an employee share plan (`cost_basis`,
  `teilfreistellung: 0`: shares), gold coins (`XAU`, priced by the shipped gold series), a gold note
  (by ISIN, its prices stop in 2026-03 so the Overview flags it), Bitcoin with one young lot
  (`prices/BTC.csv` typed in), a savings plan of 300 € into the depot in `work` and `new-job`
  (nominal, `invest_rest` at its default; the car of 2030-04 pauses it), care, the spending rule
  (`base: no_pay`, a cut of 25% below 25% and an increase of 10% above 150% of the wealth at the
  first month without pay: a trigger of 50% cut `stress` from 96 on its mean path) and the age
  curve, an allocation glide path, the `disability` block with the default chances written out and a
  BU of the employer (`BU policy`, kind `bu`, 2,000 € to 67, `premium: 0`; rule `disability`).
  Scenarios: `plan` (work to 65, the BU ends with the job by `end_streams` of the id `retirement`,
  the flat sold at 50 repays the loan, a Basisrente premium at 55, an inheritance from the mother at
  her drawn death, 20,000 € cash and securities of 10,000 € with her cost basis, below the
  Freibetrag (more raises the spending of `buy-home` on its mean path, `test_examples`), conditional
  sales of Bitcoin and of the coins, `tax.harvest` in its `overrides` for every scenario: the mean
  paths harvest 32 € of `stress` in 2026 only, as the Vorabpauschale takes the Pauschbetrag, the
  sabbatical takes salary in both of its years and the let flat carries a loss; Monte Carlo paths
  harvest after a falling year, P(broke)@90 stays), `severance` (a severance with a bAV part at 53,
  `end_streams`, ALG1, a new job by `add_stream` in `new-job`), `sabbatical` (`alt` at 45 with
  voluntary contributions, a gift of 25,000 € from the mother in 2028-02; a second child born
  2031-06-12 by `overrides.person`, which repeats the first row: its child-raising years, rule
  `children`; by `add_stream` its cost, 400 € to 2049-07, and the Elterngeld of the notice,
  `Parental allowance (Elterngeld)`, 1,800 € nominal for twelve months, `taxable: false`: a stream
  named in English with the German term in brackets), `freelance` (`freelance` from 42: a
  `self_employed` stream by `add_stream` with a made-up `hebesatz`, `tax.self_employed.rv: income`
  in its `overrides`; the PKV goes on without a subsidy; she keeps the BU at 95 € of her own, a
  `set_stream` of `premium`), `freelance-no-bu` (extends `freelance`: the BU lapses by `end_streams`
  in 2029-01; the pair of the BU in `docs/manual/scenarios.md`), `disabled` (extends `plan`:
  `overrides.disability.at: 2038-01`, unable to work at 51, so the Cashflows page shows the months
  after; at 47 its mean path ran out at 98 and cut), `keep-flat` (`drop`, `repay`, a conditional
  sale of the flat), `buy-home` (extends `plan`: a `buy_property` of a flat in 2028-04 for 330,000 €
  with a loan of 300,000 €, `end_streams` of the rent, Hausgeld (400 €: at 350 its mean path raised
  its spending once the BU of `plan` cost nothing) and property tax by `add_stream`; the pair of
  `docs/manual/buy-or-rent.md`), `stress` (`overrides` of returns and tax, `shift`, `events`,
  `assets`, a write-off), `vpw` (extends `plan`: VPW instead of the band, `growth` 3.7% for 60/40, a
  floor of 600 €, rule `spending`; P(broke)@90 3%, alive 4%, so the Difference tab shows band
  against VPW). `app.yaml` opens `plan` and `stress`. With 2,000 Monte Carlo paths and the default
  chances of a disability (P(disability) 17%, weighted by survival) P(broke)@90 is about 3% for
  `plan`, `buy-home` and `freelance`, 2% for `keep-flat`, 6% for `freelance-no-bu` and `severance`,
  4% for `sabbatical`, 14% for `stress`, 22% for `disabled`: keep the default scenarios clear of 0
  and 100%, or the tiles, the sensitivity and the goal seek show nothing. `actuals.csv` follows the
  plan of its months, with a summer holiday and one category missing in 2026-09 for the Overview
  reminder, which shows while a month of the last three holds a record (`actuals.KEEPING`): up to
  2026-12. The bAV statements of 2025-12-31 carry to the start (rule `engine`).
- `starter/`: a FIRE aspirant, born 1995-02-09, single, no child, GKV (`kvdr` default, average
  Zusatzbeitrag), no church (`land: NW`, not a city-state), a rented flat, start 2026-10. Its data
  is German whatever the language of the pages (owner, 2026-10-13; the start page says so): names,
  notes, phase labels, categories and comments in plain German, ids, keys and stems ASCII slugs.
  Phases `arbeit` (`Arbeit`), `teilzeit` (`Teilzeit`), `ruhestand` (`Früher Ruhestand`), `rente`
  (`Rente`). A salary `Gehalt` of 5,900 € a month (70,800 € a year, `index: gehalt` at 2.5%; 60% in
  `teilzeit`), a `Bonus` of 10% each March (`of`, `index: null`: no payout ratio), the pension
  from 8.5 points; the bAV by a salary `conversion` of 200 € (rule `bav`: the subsidy of the law,
  15% until the salary less the conversion passes the KV-BBG in 2028, then 10.6%, 15% in
  `teilzeit`; within the SV-free 4% of `sv_bbg_month`, 338 €; `contribution` 0, `fuenftel: false`,
  phases `arbeit` and `teilzeit`), an Altersvorsorgedepot (`av-depot`) of 1,800 € from 2027,
  `tax.werbungskosten: 1500`,
  `girokonto`, `tagesgeld` as the buffer, a `depot` of an MSCI World ETF with `cost_basis` (no
  trades, no `prices/`), a savings plan of 500 € into it in `arbeit`. Spending of 2,115 € a month
  in seven categories (`Wohnen`, `Essen`, `Freizeit`, `Haushalt`, `Verkehr`, `Versicherungen`,
  `Sonstiges`), about the Destatis LWR 2024 average of a woman living alone (2,033 €, insurance
  premiums apart), the rent of 55 m² in a mid-size city. No allocation, care or spending rule.
  Scenarios: `plan` (`Arbeiten bis 67`, `rente` in 2062-03), `ausstieg` (`Mit 55 aufhören`,
  extends `plan`: `ruhestand` from 2050-03 with the id `ausstieg`), `teilzeit` (`Teilzeit ab 40`,
  extends `plan`). `app.yaml` opens `ausstieg` and `plan`, so the tiles and `Find when to stop
  working` of the Overview read `ausstieg`: P(broke)@90 about 6% at 500 paths (5% at 2,000, 6% at
  50), `plan` and `teilzeit` 0%, the contrast. No event: the full example shows them. `features_off`
  holds the ten features that `mode.uses` finds unused: a newcomer's plan (`engineer`: none).
- A German `engineer` and a German empty plan: issue #5. Spread the features
  over the scenarios: no one scenario may stack a real life story.
- Nothing may resemble a real person's situation: no real city, bank, insurer or employer,
  made-up ISINs (`IE000WORLD05`), round amounts. The personal-data hook checks the amounts too:
  change a flagged number, never the list. No licensed series: the Data page fetches them;
  `prices/` holds user records only (typed or imported).
- Never open an example in place: `datadir.open` (every command and the app) writes `revisions/`
  into it. Start a copy (`uv run dagobert init --example --data tmp/rt`) for a run or the skill
  `app-check`.
- `tests/test_examples.py` reads every directory of the examples without writing: the names of
  `ExampleName` and of the start page are the directories, the schema is current (a migration
  step must migrate the examples too: run `schema.migrate_dir` on them and commit), every
  scenario loads, `app.yaml` names concrete scenarios, the history and the actuals read, every
  defined phase is used, one phase has a label, and no concrete scenario goes broke in a `fixed`
  run, and none cuts its spending there but by VPW, which sets it in every month without pay (the
  difference of the pair of `buy-or-rent.md` is the purchase alone). `engineer` alone uses every
  kind of the model's asset, stream kind and event type (a new kind needs a use there), and so
  every feature, with `features_off` the unused ones. The `fixed` run of the main scenario of
  `starter` goes broke when she stops at the start (`goalseek.work`, `dial.low`) and lasts at the
  month of the file: the work seek finds a month.
- The dates are fixed: a first run months after the start shows the roll forward and stale
  values (the start page and the README say so). Moving the example forward is a roll forward on
  a copy plus new `asof` dates.

## First run

- `datadir.empty`: no tracked input and no revision, or no directory (`lost+found`, `series/` and
  other files do not count; a file is not empty); `transfer` takes it for an import into an empty
  target. A start writes only there (`check_empty`, before and again under the lock of the write:
  two tabs; else `InputError` `holds a plan already`, for a file `not a directory`), creates a
  missing directory and writes one `revisions.write` with every scenario checked:
  `start_example(dir, example)` the inputs of an example as they are (`schema.Tree`, `EXAMPLE` by
  default), source `example` (`FROM_EXAMPLE`); `start_quick(dir, Quick)` the quick start, source
  `quick start` (`QUICK_START`); `start_empty(dir, born)` (the CLI) its date alone, source `empty
  plan` (`EMPTY_PLAN`), the same files. `datadir.texts`: `person.born` (`sex`, `rv_since` the
  January of `since`), `start` the current month (`first_month`), the `phases` of `NEW_PHASES` (four
  fit the sheet on an upright phone), the four `REQUIRED_CLASSES` of `returns` of the example,
  `tax.pkv` (off: an empty plan is GKV, the model's default PKV); per answer a row, none for an
  empty or zero one, named in German as `starter`: `girokonto` (cash), `depot` (equity, `cost_basis`
  its value; at 0 for a savings plan alone), `Gehalt` (salary, `work`), `Rente` (pension, `retired`,
  with a salary or points: typed, else `estimate`, a year of `sv.pension_points` of the salary per
  year since `since`; `point_value` the `rentenwert` of the tax year of `start`), `Lebenshaltung`
  (cat `Leben`), `Sparplan` (into `depot`, `work`); `app.yaml` every feature off (the plan uses
  none); `scenarios/plan.yaml` (`Plan`, `SCENARIO`) in `work` from `start`, in `retired` from the
  month of 67 (`model.months.aged`) with the id `retired`, the change that `goalseek.work` moves
  (past 67, `starts_retired`, `retired` from `start`); the manifest, so the next `datadir.open`
  writes nothing. `born` has no default: a placeholder would drive every age rule. `check_born`
  refuses one after today or before `OLDEST` (1900-01-01), ValueError: the CLI parser, the page and
  `texts` take it. The example is not rolled forward (a decision).
- `datadir.open` of an empty or missing directory raises `InputError` that names `dagobert init`
  (`START`); one with other inputs but no `assumptions.yaml` stays `not a data directory`.
- `uv run dagobert init [--data DIR] [--example [NAME] | --born YYYY-MM-DD]`: an example (`NAME` of
  `ExampleName`, `engineer` without it), or an empty plan whose date of birth it asks for without
  `--born` (`typer.prompt`, again until a date reads; `cli._born`). Typer 0.27 takes no option with
  an optional value (`flag_value`), so `NAME` is a positional argument that needs `--example`. It
  refuses a directory with a plan or a file before it asks.
- `ui/welcome.py`, the page `Start a plan`: `main.py` draws it instead of the page while
  `datadir.empty(DATA)`, with the navigation registered but hidden (`position="hidden"`), so a start
  goes on by `st.switch_page` to the `Overview` (an example, a quick start with a salary before 67)
  or the `Assumptions` page, in simple mode (`_start` sets `mode.MODE` and `MODE_CHOSEN`, the cookie
  follows; not an import). Two columns, stacked on a phone, buttons of equal weight: `An example`, a
  line and a button per example of `welcome.EXAMPLES` (`Start simple: …`, `Full example: …`), then
  `Their scenarios` (name and note of each, the app's defaults first, read without an open) and
  `Their dates` (their start months and the roll forward), expanders on every device; and `Quick
  start` (`QUICK`, `overview.explore` of the plan it writes: no page that records; owner,
  2026-10-13: people configure once and explore): `Date of birth` (a text field with the decimal
  keypad of a phone, day first with dots or ISO, `welcome.birth` through `fields.day` and
  `check_born`: bare digits stay unread, `20051986` could be either order; below it the date in
  words with the age, `welcome.said`, `Born 20 May 1986, age 40.`, so a slip of the order shows, or
  why it does not read; without a date why the start is off: a calendar took many taps back), `Sex`
  (none: the model's `m`), the numbers of `ANSWERS` two to a row (`fields.parse` of `field`: at
  least 0, the year from the birth to now; the error below; below the points `pension_note`, their
  estimate or `NO_POINTS`; past 67 `RETIRED`: the salary and the savings plan pay in `work`), the
  toggle of the PKV, `Start my plan` (off while the date or a number does not read) and the caption
  `OFF` that names every feature (`mode.said`). The path of the data directory is the last caption.
  A failed start shows `Not started: <dir>: <reason>` (`ValueError`, which `InputError` is, and
  `OSError`: read-only, locked, a plan there by now). The container's empty `/data` volume reaches
  it; a bind mount that Docker created is root's, so the README makes the directory first. Below the
  columns `An export`: the import of `Export and import` (`ui.transfer.import_zip`, rule
  `transfer`): every file `add`, one revision `import <zip>`, or with the revisions of the zip its
  history (`_take_history`); then the Overview. The page speaks the language of the session (rule
  `i18n`: the date in words, `20. Mai 1986`; the points of `pension_note` as `9.24` in both
  languages), the names and notes of the examples as written (each line names its language); the
  sidebar: two switches.
- An empty plan and a quick start render all pages in both modes
  (`test_pages_render_an_empty_plan`): no asset gives no recorded net worth
  (`history.actual_values`), an info for the sunburst, no category a text column in the Spend grid.
  `test_examples`: the date alone is `start_empty` file by file, the month of 67, a salary pays a
  pension and the work seek finds a month, the estimate.
