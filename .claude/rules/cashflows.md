---
paths:
  - "src/dagobert/cashplan.py"
  - "src/dagobert/ui/{cashflows,bars,overview,flows}.py"
  - "tests/test_{cashplan,ui_cashflows}.py"
---

# Cashflow plan and outflow bars

The rows of the run on the Cashflows sheet come from the ledger: rule `ledger`.

## Cashflows page

- Under the title links to the sections (`SECTIONS`, the anchors of their headings: `Sheet`, `Bars
  of one phase`, `Scheduled changes`, `Streams`; Streamlit keeps a heading 60 px below the top,
  clear of the header). The date `As of`, which reaches the end of the plan, the scenario (`stem ·
  name`, `ui.scenario_titles`, at first the main one, marked `(main)`) and the amounts, each with a
  help, the note of the scenario below its select (`ui.scenario_note`). Each section keeps one
  sentence visible and folds the rest (`ui.fold`), the terms of the law under the sheet in `What the
  terms mean` (`TERMS`, which the Flows table shares; a tooltip of this length ran off a phone); a
  static sheet by category for the date with one column per phase that the scenario reaches
  (`reached`: its phase changes, in the order of `assumptions.yaml`, headed by the label, as the
  Flows page; also the bars, the scheduled changes and `Changes since`: `Labels`, `_phase_table`)
  and the rows `income` and `expenses` of the plan (a stream of a non-cumulative index, such as a
  bonus, at the clipped mean of the index in the scenario), then the rows `from the run`: what no
  stream pays in the `fixed` run of the scenario (PKV subsidy, taxes and SV, a salary conversion,
  loan interest and principal, property upkeep, capital gains tax), the mean over the first 12
  months of each phase from the date on (`budget.beyond_streams`, run rate on, `–` for a phase that
  the run does not reach), the `surplus` of all rows, and below it, with a savings plan that paid,
  `into savings plans` (`Budget.saved` of the same months: a skipped rate shows, part of the
  surplus, not taken off it) and `non-cash income` in the same months of the run (the growth of the
  assets and what goes into a policy without passing the cash, not part of the surplus), per month
  or per year. On a phone the header of the sheet stays below the page header while its rows scroll
  (`table-cashflows-sheet`: its box drops the sideways scroll, which held the header, and in
  portrait its first column wraps, so four phases fit also per year, a few pixels more spill into
  the side padding; landscape holds eight, per year too). In portrait a fifth phase (the sixth
  header cell, `:has`) scrolls its box sideways again, the first column sticky, and the header stays
  at the top of the sheet: a scroller holds a sticky header, and an inner scroll of the rows would
  hold the swipe that scrolls the page. Below it where the columns come from (`PHASES`: the
  Assumptions page) and why the Flows page differs, with a link there (the plan on one date and 12
  months of the run against the means over whole phases); bars of the outflows by category (the
  groups of the run in the colors of their roles; a click on a bar shows its streams or items beside
  it; on a phone a pill above the bars shows them right below the pills) and of the income streams
  (the non-cash income purple, below them and outside the total) for a chosen phase
  (`phase_control`: the phases that the scenario reaches by label, at first the one of the scenario
  on the date, `Scenario.phase_of`; its key holds the names, so a removed phase leaves no value),
  side by side (on a touch screen they stack in a main area under 760 px, as in landscape with the
  sidebar open); scheduled starts and ends, per row the stream, the date, the change and the monthly
  effect per phase (green more money, red less), a row that ends on the date on which a row of its
  name starts as one change (`scheduled(paired=True)`: the fields that differ, `amount: -1.450 € →
  -1.300 €`), with what the events of the scenario change (streams that a property sale ends, those
  that name it in `property` or share a tag, or starts, also of a property that a `buy_property`
  brings, `end_streams`, `add_stream`, `set_stream`, by date; a sale on a condition shows `on
  condition`; a row that a dated event ended changes no more, `_Events.ended`, so a `set_stream`
  after its `end_streams` shows nothing, as the engine pays it; a `set_stream` changes the rows that
  `SetStreamEvent.targets` names, rule `plan`; the event ends every row of its name or tag so far,
  also one that starts later, by identity, and a stream that an `add_stream` adds again under the
  name runs, so a later event changes it) and `Changes since`: the changes of the streams since the
  start of a day with the monthly effect per phase (a derived stream whose base changed shows
  `follows <base>`, so the total is the change of the sheet). Its select `Day` lists the local days
  with a revision of `cashflows.yaml` that have a revision before them (`ui.since`), newest first,
  as `day_said` (`Day.label` with its pages in words), and compares with the last revision before
  the chosen day began, so the newest day shows its own changes. Without such a day the section is
  gone; a revision whose streams do not read gives a warning. Then the editable streams in an
  `expenses` and an `income` tab, one collapsed block per category with its monthly sums per phase
  in the header and a `factor` column per phase of the plan, every one: the file serves every
  scenario (`with_phases`, `Table.entries`); an expense is saved negative whatever sign is typed,
  the name of a saved stream stays (`Rename` beside `All columns` in each tab, rule `references`),
  `index`, `of`, `repays`, `after_sale_of` and `tags` are selects (rule `grids`); behind `All
  columns` of the expenses `deduct` (`deductible as`, rule `deductions`) and `deductible` with one
  help for a premium and a deduction. `TERMS` name Werbungskosten, Sonderausgaben and §35a too,
  their Pauschbeträge by the tax year of the scenario (`cashflows.terms`, also under the Flows
  table). A third tab `savings` (`cashflows.SAVINGS`, `fixed` kind `savings`, no blocks, no total
  row, `SAVINGS_NOTE` above it): `name`, `amount` (saved negative), `into` (a select of the equity,
  fixed-income, gold and crypto assets, `model.streams.SAVINGS_TARGETS`), the `_WHEN` fields and
  `index`. A savings plan has no effect in the scheduled changes, `Changes since` and the attention
  table of the Overview (`cashplan._effects`): it lies outside the monthly totals. A fourth tab
  `disability insurance` (`cashflows.BU`, `fixed` kind `bu`, rule `disability`; `BU_NOTE` folded
  above it): `name`, `amount` as `Monthly benefit €`, `premium` as `Monthly premium €` (saved
  negative), `until_age` as `Pays until age`, `start`, `end`; the expenses tab leaves it out
  (`EXPENSES.match`). `cashplan.monthly` counts its premium, an expense of its `cat`, never the
  benefit, which the run draws: the rows of the run show it (`<name>: benefit`).
- Simple mode and the features (rule `mode`): the four stream grids take `grid` `streams` and the
  `mode.View` of the page (rule `grids`): a column of `mode.EXPERT` or of a feature off that no row
  holds goes behind `All columns` (`tags` of the expenses, `of` and `share` of the income, `index`
  of the savings), and `kind` offers the stream kinds that `View` shows and those that a row or an
  edit holds (a kind outside `CORE` hides until used: `alg1`, `self_employed`, `rv_voluntary`, a
  new kind too, no line here). The tab `disability insurance` shows while `View` shows the kind
  `bu` (outside `CORE`; the feature `disability` off hides it in both modes) or its grid holds
  unsaved edits. Below the tabs `View.note` names the hidden kinds in words
  (`StreamKind.titles`).

## Code

- `src/dagobert/cashplan.py`: the cashflow plan on raw YAML rows (monthly equivalents, scheduled
  changes, `scenario_changes` from the events of a scenario, each with its event (`Change.event`,
  outside the comparison: the Overview links to it), `diff` against the rows of a revision,
  `by_stream` for the bars). `plan_at` reads the streams and the start of a revision of the store
  once (`revisions.state`), migrated in memory (`schema.migrate`), as raw rows, so revisions from
  before a model change still load; `ValueError` when they do not read. A stream is keyed by name
  and `start`. A change names what differs as the grids show it (`shown`, by the unit of the field:
  `amount: -900 € → -950 €`, `share: 10% → 12%`, `end: – → 2027-01-01`), in the attention table of
  the Overview too, in the words of the session (`Change.what` is made per call, never cached:
  `starts`, `sale of …`, a key by `pgettext("key", …)`, German `Betrag: -900 € → -950 €`). `role`
  gives `INCOME` (`INCOME_KINDS`: also `self_employed`, the profit of a business, its `hebesatz`
  behind `All columns` of the income grid), `EXPENSE` or `SAVINGS` (kind `savings`): `sheet`,
  `by_stream` and so `actuals.planned` and the bars take income and expense rows only. `diff` also
  lists an unchanged derived stream (`of`) whose amount follows a changed base row. It takes the
  `start` of the revision (`plan_at`, from its `assumptions.yaml`): a row without `start` there and
  the row of the same name that starts then are one stream, the roll forward wrote that start,
  unless the plan still has a row of that name without `start`. A stream paid every n months is
  active from `accrues_from`, n months before the month after its first payment: a yearly bonus that
  starts next January counts today. An ALG1 stream has no amount: the page fills in `sv.alg1_month`
  on `cashplan.alg1_reference` through `cashplan.with_alg1` (`estimated` takes the plan). As the
  engine it takes the last monthly salary before the claim (`_alg1`): in the month before the first
  change to a phase in which an ALG1 stream pays, of the newest phase before it that pays one, so a
  change of jobs counts; without one, on the `As of` date in the phase of the scenario then, else
  the newest before it that pays; less the part free of SV of the conversions of the bAV policies
  that pay in that phase and month, before `matures` (`_converted`, `sv.conversions` on that
  salary), each from its salary as the engine takes it (`_salary_of`: the one that `salary` names,
  else the first without `of`; none that pays then, no conversion). A stream of a non-cumulative
  index counts at the level that a `fixed` run pays, the clipped mean (`Index.at_mean`):
  `with_levels` adds it to the row as `level`, and `monthly` multiplies by it, so a bonus with a
  payout ratio of 0.9 counts 90 %. A cumulative index starts at 1 in the euros of the start, so its
  streams count in full. `ui.cashflows.estimated` applies both to the rows of the Cashflows page and
  of the Overview, with the assumptions of the chosen scenario on the Cashflows page;
  `scenario_changes` takes the plan and levels the streams of `add_stream` events the same way. The
  Spend page levels its rows with the assumptions of `assumptions.yaml`. Both end the PKV premiums
  (`health`) in the month of `tax.gkv_from` as the engine does (`cashplan.with_gkv`, rule `gkv`):
  the sheet of a later date leaves them out, the scheduled changes show their end, and an
  `add_stream` of one that starts after the switch shows no start.
- `src/dagobert/ui/bars.py`: the bars of one phase, which the Cashflows page and the Flows page
  share; their labels take a fixed room, so the bars of stacked charts start at one x (rule
  `charts`, `bars_figure`). The outflow and income bars color a category like its block in the
  stream tables (`tables.row_colors`), the groups of the run in `bars.GROUP_ROLES` by their role
  (`bars.ROLES`, the colors of the Flows page): `taxes & SV` and `capital gains tax` orange, `loan
  principal` amber, a salary conversion and the non-cash income purple, the rest gray, the loan
  interest too (a cost, so the principal stands apart). The Flows page colors every group by its
  role, spending blue. The income bars show the non-cash income (`bars.noncash_of`, an item named
  like a stream gets ` (non-cash)`: a bar is named by the last part of its path) below the cash
  income and outside its total (an asset that shrinks to the left of a zero line), with the line
  `plus N non-cash income: growth of the assets and payments into policies, stays invested`.
  `bars.outflow_bars` is the outflow picker of every page: under its headline the line `of which N
  repays loans: stays in net worth`, with a salary conversion its own words or both (`KEPT`: its
  total keeps both; a part counts where it rounds to a euro, both where only their sum does), bars
  per group (the first part of each `Slice` path), the largest on top, and the items of one group.
  The paths are the English of the ledger: the bars say them (`budget.said`), the pills take them as
  options in words (`format_func`), and a click maps the words of its bar back, so the pick and its
  keys stay English. On a phone pills above the chart pick the group, its items show right below
  them, and the chart takes no tap, so a swipe over it scrolls. On a desktop a click on a bar picks
  it, and its items show in `detail`, by default a container above the chart (the Cashflows page
  passes the income column). A new pick scrolls its items into view once, as little as needed, when
  their chart is drawn, the run has ended and they kept their place for ten frames (`bars._SCROLL`:
  what fills in above them late, such as a slow run, would move them). A hand on the page meanwhile
  (wheel, touch, pointer, key) ends the wait, and so does a minute, so the page never jumps late. It
  is a one-shot `st.html` script that names the pick, so the next pick runs it again. Their
  container `outflow-detail-<key>` keeps the heading clear of the header (`scroll-margin`).
