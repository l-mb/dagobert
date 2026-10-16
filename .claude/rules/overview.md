---
paths:
  - "src/dagobert/ui/{overview,outlook}.py"
  - "tests/test_ui_overview.py"
---

# Overview page

The plan below the tiles (`outlook.py`): rule `explorer`. The `Roll forward`: rule
`rollforward`. The tiles, the sunburst and the attention table: rule `tracking`.

- Plain words: a label names what a figure means, its help the term of the report (`P(broke)@90`);
  no file or key name outside the `Roll forward`, which edits them; every long caption folds into
  `ui.fold` on every device, also inside the `Roll forward`, labeled `How to read the <section>`
  (the outlook, the assets, the recorded net worth, the comparison), but `What the table lists`
  of the attention table, which lists.
- The landing page, about four screens on a phone: the tiles; the plan of the main scenario
  (`scenariofiles.first_scenario`) below them (`outlook.plan`): `Main scenario: <scenario>` (the
  words of the Scenarios page), its note (`ui.scenario_note`), the link `Change the main scenario`
  to the box of the Scenarios page (`?main=open`, `ui.MAIN`, rule `scenarios`), a caption that names
  the simulated futures, one line of what the plan assumes (`outlook.assumed`: the month and age at
  which the scenario stops working, `goalseek.work` at its own value; none without that change), the
  tiles (`tiles-plan`, `outlook.TILES`, labeled by `report.summary_columns`) `Chance to run out,
  lifetime`, `Chance to run out by 90`, `Net worth at 67` and `Typical shortfall`, the columns
  `P(broke) alive`, `P(broke)@90`, `Total@67` and `Shortfall` of the summary of the explorer's run
  as it opens (Monte Carlo, `runs.PATHS` paths, the files without sliders, euros of the start),
  whose help starts with the column (the two of the chance to run out add why the lifetime figure
  can be the lower: `LIFETIME_HELP`), a fifth tile `Stop working` (`goalseek.STOP`): the month that
  `Find when to stop working` found for the target, its age below it in gray (`outlook.stopped`,
  `Dial.month`), from `outlook._seeks`, so it stays until an input or the target changes; before the
  seek a dash and `not searched yet`, without a month a dash and `see the answer below` (no effect,
  no such change), when even the latest month misses the target `not even at <age of that month>`
  (`outlook.latest`) (a seek takes about 10 s: it runs by itself once only, on the Overview of a
  plan that the start page started, `outlook.SEEK_FIRST`, owner 2026-10-16); on request (`Find
  the spending limit`, beside the target `Target, chance to run out by 90 (%)`, its sentence in the
  help, both shared with the goal seek of the Explorer, `seek.Target` (the age of the run, rule
  `goalseek`), in a row that wraps, the answer below) the one factor on all spending at which
  P(broke by 90) meets the target (default `seek.TARGET`), in euros per month and as the change
  against now, in plain words with no factor and no count of runs: `Spend at most 2.054 € a month,
  14% less than now` (`outlook._allowed`; a miss adds the link `Explorer: try less spending or more
  saving`, `ui.page_link`, to a seek that misses the target; under VPW, rule `spending`, the floor
  in euros, `_floor`, and the two tiles of the chance to run out and the fold add `VPW_RISK` and
  `VPW_SEEKS`), and beside it `Find when to stop working` with the same target (`goalseek.work` and
  `goalseek.stop`, rule `goalseek`: the earliest month of the change out of the last phase with a
  salary or a profit, or why there is none), each answer kept per button (`outlook.SEEKS`), its
  progress bar gone when the seek ends or raises; a table of what needs attention (a simulation
  start before the current month, with how far it lags; the values that need an update,
  `summary.needs_update`; the changes of the plan in the next three months with the events of the
  main scenario, which its fold names, each with its effect in the phase of its date, named by its
  label (`overview.attention`, `Scenario.phase_of`, `Assumptions.phase_labels`), a raise as one
  change (`scheduled(paired=True)`, as on the Cashflows page), a purchase of a property too
  (`overview._purchase`: the price, the cost with tax and costs, what the cash and the liquid assets
  pay); a plan with `disability` and no pension from points, which then pays no EM-Rente
  (`overview._no_em_rente`, undated, linked to the Cashflows page; rule `disability`), or a forced
  onset (`at`) whose run of the files pays none (`RunResult.em`), dated, linked to where `at` is
  written; a savings plan that pauses in the `fixed` run of the files (`overview._paused`: the
  marker `savings plan` of the engine, in its month whenever it lies, never derived again, rule
  `ledger`; issue #20), linked to the Cashflows page; the term deposits and fixed loan rates that
  end within twelve months or ended already;
  while `actuals.csv` holds one of the last three months (`actuals.KEEPING`), the first complete
  month since the first record in which a planned category has no actual (0 counts), also a gap
  before a later record, with the count: `2026-01: 1 of 12 planned categories`, `actuals.missing`;
  each row with the place where the user changes it, `Notice.fix`, `Open <page>` (the owner,
  2026-10-13: the Snapshot page cannot edit `as of`): a value its row on the Assets page with the
  value field and `asof` to check (`dated`, `edit`: `assets.opened`, rule `tracking`), a deposit
  `matures` (ended: and `value`), a loan rate `fixed_until` and `rate`; a change of a stream the
  Cashflows page, of an event (`cashplan.Change.event`) and a purchase its type in the file of the
  chain that writes it (`placed`, `loader.written`, nearest first); the month `?month=YYYY-MM` of
  the Spend page (rule `spend`); the lagging start none, the `Roll forward` below fixes it), while
  the start lags a collapsed `Roll forward` (open with `?roll=open`, `ROLL` and `OPEN`, the link of
  the Assumptions page; a month between the old start and the current month, the current one first;
  the events that refuse the roll, with the scenarios they reach, per file where they are written
  (date, item, scenarios, file) and what to do (for a purchase: the property and its loan into the
  assets first), which names the Scenarios page; the phases that end before the new month and the
  loans without `asof` (`Roll.undated`, each a link to its row on the Assets page) as warnings; the
  file of an event or a phase links to it (`overview.fix`, `Passed.kind`:
  `?scenario=<stem>&event=<type>` or `&tab=Phases`, the file that holds it, a template too); the
  consumer price factor with its source, the amounts it changes (item, old, new, file; on a phone
  the item at 140 px, so old and new fit), the periodic streams that take the old start, the
  businesses that keep their founding (founded, scenarios, file), the losses carried to the new
  start, a grid per pot (`loss_carryforward` or `capital_losses`, scenarios, file; `CARRIED`,
  `KEPT`), the gifts that move into `given` (item, month,
  value, tax, file; rule `estates`), and the button; these grids (`_roll_grid`) at most 250 px high,
  on a phone 160 px, so a swipe beside them still scrolls the page in landscape, a shorter list as
  high as its rows; after the roll a summary above it; an input changed since the list drew refuses
  the roll, `Nothing changed: the inputs changed since the list above (… changed at 14:03 on …). It
  shows them now.`, see `rollforward`); then one row (`st.columns`, stacked in portrait): a sunburst
  of the assets (liquidity, kind, asset, and the securities of a depot with their open lots at the
  last stored prices; `assets before debt` in the hole, the loans in the line `less loans … = net
  worth …` below it and in their tile; on a phone the first two rings at 340 px, which fits
  landscape, and a hint that a tap opens a ring) and a line of the fixed-income share against the
  glide path of `allocation`; beside it the recorded net worth of each month with a record once
  there are two (`history.actual_values`; a line under it: the bars of the assets and the debt, a
  dot the net worth, a line between consecutive months only); on a desktop both charts
  `overview.CHART_HEIGHT` (460 px) high, so the columns end together, and the circle of the sunburst
  in the middle of its column; on a phone 340 px, as the rings (`PHONE_CHART_HEIGHT`). Before a
  second month of records no row but one column: the rings, then the info of the recorded net worth
  with the line to the Explorer (`overview.explore`: the plan needs no record, the Snapshot and
  Spend pages keep records, each named while `View` shows it, `KEEP`) and the link `Explore
  scenarios` to the Explorer (owner, 2026-10-14: people configure once and explore), no empty column
  beside them. Below the row, while `app.yaml` switches off features that the plan does not use, one
  caption counts them with a link to the Features page (`mode.off_note`, rule `mode`). The outflow
  and income bars stay on the Cashflows page, the totals per kind on the Assets page (a tab per
  kind): the Overview shows no detail. Then `Records against the plan`: the recorded net worth or
  liquid assets of each month with a record (a dot, a line between consecutive months only) over the
  median and p5 to p95 of the same run of the scenario on the inputs at the end of a day, in nominal
  euros (`outlook.on_track`). The day is the select box `Compare with plan saved on`: the local days
  of the browser with a revision of the plan (`revisions.is_plan`) whose inputs hold the scenario
  (`outlook.plan_days`, `revisions.named`: before a rename under its old file, which the run then
  takes), each as `Day.label` (date and saves), with `Measure` beside it (`outlook.MEASURES`: an
  option is the array of the run that it shows, `total` or `liquid`), below it in portrait
  (`overview-track-day` keeps 20rem). The value of an option is its date, so a save elsewhere that
  changes the sources of a day keeps the choice. It opens on the plan as it stood when the record
  began: the newest day before the first recorded month ended, else the oldest
  (`outlook.default_day`). Without a revision, an info. The run takes the inputs of the last
  revision of the day (`revisions.materialize`), or is the run of the tiles while the files still
  hold them (`runs.baseline`, rule `explorer-runs`). The band runs from the `start` of that day to
  `outlook.AHEAD` months after the last record, and a line gives the share of the paths below the
  last record. Below the chart, while an asset is a pension policy or depot with an `asof`
  (`outlook.carried`), one line: the plan carries it from that date (rule `engine`), the records
  keep the values typed, and `Take estimates` of the Snapshot page updates them (owner, 2026-10-14:
  records stay as typed). A day whose inputs do not load with the model of today gives a warning,
  one that its engine refuses (a ValueError, `runs.Refused`) a warning with the reason, never a
  traceback. The roll help says that the roll is one revision, which `Changes since` of the
  Cashflows page shows. Last the link `Cashflows: where the money goes` (`ui.page_link`).
- Simple mode and the features (rule `mode`; `page` takes `mode.view` once): the notices `last
  updated …` and `the value has no date yet` (`attention(stale=)`) while `View` shows the data
  `records` or `trades` (in simple mode: once kept); the recorded net worth and `Records against
  the plan` while it shows `records`, else only the line to the Explorer. No text names a page that
  `View` hides: the fold `What the table lists` takes its parts (`LISTS`: the stale values with
  them, the month of the Spend page while it shows), the roll help and its refusal send the asset
  values to the Snapshot page while it shows, else to the Assets page (`VALUES`, `OUTCOME`), and
  an estimated consumer price links `Data: fetch newer consumer prices` (`ui.page_link`: none for
  a page left out).
- The attention table and the items before the new start are `_linked` tables: `st.table` takes no
  widget, and a Markdown link opens a new tab, a new session. The container `overview-attention` or
  `overview-passed-<kind>` is a CSS grid of four columns (`ui/page.css`), its header and each row a
  container on those columns (`subgrid`), the last column the `ui.page_link` to the page that fixes
  the row (`Link`), empty without one. Cells are Markdown (`ui.literal`), a late date `:red[**…**]`
  (the theme's red, also on the dark theme). In portrait a row is a card without the header: the
  item in bold, below it the date and the third cell (what, scenarios), the link on the right of
  both (`grid-area`). A link is 28 px high, on touch 40 px.
