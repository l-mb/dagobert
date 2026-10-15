---
paths:
  - "src/dagobert/ui/{explorer,seek,main}.py"
  - "tests/test_ui_explorer.py"
---

# Explorer page

The `scale` overrides that the sliders write: `docs/manual/configuration.md`. The rest of the
Overview page: rule `overview`. The seek of `goalseek.py`, its dials and `edge`: rule `goalseek`.
The sensitivity run, the failure anatomy and the difference of two runs: rule `analyses`. The runs,
their caches and process pool, and the plan of the Overview: rule `explorer-runs`. Simple mode and
the features: rule `mode`.

## Explorer page

- Plain words: a label names what a figure means, its help the term of the report (`P(broke)@90`,
  rule `charts`); the help of a slider and the goal seek say `chance to run out of money` instead; a
  scenario shows by its name, not its file.
- The sliders, their groups and switches in the sidebar: rule `explorer-sliders`.
- The scenarios show their names (`scenariofiles.scenario_labels`: the stem added where two share a
  name), the main one marked `(main)` in the options only (`ui.main_marked`, as Cashflows and Flows;
  a run keeps the name), the help of the control the file and the first sentence of each note.
  Without a chosen scenario the page asks for one and `Set as default, the first as main` is off;
  its help says why, else it names the first chosen one, which becomes the main scenario (rule
  `scenarios`). Above the table one line never goes (`Status`): `Simulating 2 scenarios, Monte
  Carlo, 500 paths … A faded result below is the last one.` while the runs compute (Streamlit fades
  the elements of the last run until the new ones replace them) and the progress of the sensitivity,
  then `Up to date: …`, or `Not simulated: …` for positions that the model refuses (`InputError` of
  the runs with the sliders: the runs of the files run first, so inputs that do not load still raise
  to `main.py`): a warning below the moved sliders, on a phone also in the strip, names the problem
  and ends the page, the sliders stay (Streamlit drops the faded results when a run ends;
  `Status.refused`). Below it a line that never goes either, so the table and the charts do not jump
  at the first move: `Sliders moved: label from → to · …` or `The sliders stand at the values of the
  files.`, with `Reset sliders` (off without a move). More than `MOVED_SHOWN` (3) moved sliders show
  as a popover `N sliders moved` (key `sliders-moved`) with a line each (`Apply to sliders` of all
  spending once moved every category into one long line; it sets the one slider now). The table
  holds the runs of the sliders only (`compared`), the change against the run of the files in
  brackets in every column of `report.COLUMNS` with a `change` (`changes`; `strip` takes
  P(broke)@90 and Total@67): chances in points, money signed, `1 in 20 runs out at` in years, cuts
  and raises in months; where one side is none (never, no shortfall) the files' value in words, `(as
  saved: never)`; the runs of the files (`RunResult.twin`, named `(as saved)`) show in the charts
  (lighter, no legend entry: the lines of a scenario would double it, rule `charts`), the tabs and
  the difference. Its headers are `Shown.label` of `report.summary_columns`, the help `Shown.tip`
  (the term first), the numbers right; the grid keeps the widths of its first data, so with brackets
  money columns take 190 px, the others 150 (`CHANGED_WIDTHS`, desktop and phone), more where the
  header in the language of the session is longer (`summary_widths(columns)`: `HEADER_PAD` and
  `HEADER_CHAR` per character, for the German `Geld aus bei 1 von 20 (Alter)`; not checked in a
  browser with a moved slider). On a desktop `Scenario` takes 24 px and 6.5 px per character of its
  longest name, up to 400 px (`SCENARIO_WIDTH`, `CHAR_WIDTH`, `summary_widths`): 16 characters fit a
  window of 1,500 px with the sidebar open, where a fixed 400 px scrolled sideways, and a longer
  name scrolls rather than lose the end that tells variants apart. The caption names the unit and
  says that a header explains its column on hover.
- The goal seek (`seek.goal_seek`: `Goal seek: the limit of one lever`, `Find the limit`, the target
  in the words of the Overview, `seek.Target` of the runs of the chosen scenarios, rule `goalseek`)
  answers in one sentence per scenario (`seek_answer`: the limit of `goalseek.Found.limit`, where
  the lever stands, the chance there by the age of its runs) and, when the target is met, `Apply to
  sliders` (`slider_positions`: the position of each slider of `Dial.weights` at the value found,
  `Knob.position`, none beyond its range, which Streamlit refuses; `All spending` sets its one
  slider; `_apply` in `on_click`, before the sliders draw). A slider takes a position between its
  steps. The lever `Stop working` (`WORK`, `goalseek.work` per scenario with the sliders, `_dial`)
  answers with `goalseek.stop`; a scenario without the change says why as soon as the lever is
  chosen. The month slider of its id reaches the range of the seek in every chosen scenario
  (`knobs(work=)`, `seek.work_dials`: `_dial` of each without the sliders), so `Apply to sliders`
  sets it; the range is part of its key, so a new choice may reset it. `_dial` is `st.cache_data` by
  the overrides and `data_stamp`: the sidebar asks on every rerun. It holds no words: the English
  label of `LEVERS` (`_named` says it) or a `goalseek.NoChange`. A chosen scenario that does not
  load has no dial there, so the sidebar draws and its run raises after it, as before the lever
  (`InputError`, shown by `main.py`). `_find` runs the seeks under one progress bar, which counts
  the scenarios with a dial and goes when they end or one raises.
- On a phone (`ui.is_mobile`) the scenarios are pills (the input of a multiselect can open the
  keyboard) with `Set as default, the first as main` below them and, while the choice differs from
  the default, a caption that names the first one chosen as the new main scenario (pills show no
  order, a touch screen no help), the goal seek folds its explanation (`ui.note`), the top of the
  sidebar holds P(broke)@90 and Total@67 of each scenario with the change against its `(as saved)`
  run, a line per scenario (`explorer.strip`, from `report.summary_row`: the open sidebar covers the
  page), in a box that shows while a scenario is chosen, keeps its last lines while a rerun computes
  (created first, not an `st.empty`) and in portrait stays at the top in small type while the
  sliders scroll (`explorer-strip`, on the sidebar color `--dg-side`). On a phone the sidebar shows
  its content before the navigation (`order` in `ui/page.css` under
  `:has(.st-key-explorer-actions)`: the navigation took the first screen). `Show results` beside
  `Reset sliders` closes the sidebar and `Move the sliders` under the title opens it (the sliders
  sit in the closed sidebar, which nothing else points to): Streamlit has no call for either, so
  `SIDEBAR_BUTTONS` clicks `stSidebarCollapseButton` or `stExpandSidebarButton` (the DOM of
  Streamlit 1.65: check it after an upgrade). The table shows `PHONE_COLUMNS` (those of the strip)
  unless `All columns`, its `Scenario` pinned at `tables.PHONE_PINNED`, the column help in the
  popover `What the columns mean` (`tables.COLUMNS_MEAN`), the difference table names the runs A and
  B in its rows (`report.difference_table(compact=True)`), the charts are compact (`compact`), the
  sensitivity charts show the measure of a selector (the index of `explorer.measures`,
  `persist_state`: a closed fold drops it), and only the open scenario tab draws and runs its
  sensitivity (`st.tabs(on_change="rerun")`, `tab.open`). In a tab the charts sit in folds (`_fold`:
  `st.expander(on_change="rerun")`, drawn only while `open`): `Net worth` (open at first), `Will the
  money last?`, `Income, spending and taxes`, `Why paths run out` (the reading of the anatomy as a
  caption: no expander inside an expander) and `What moves the result`, so the sensitivity runs only
  when its fold opens. A desktop draws them all (in simple mode in folds, below), the chart `Will
  the money last?` (rule `balance`) with its reading (`report.lasting_reading`) as a caption below
  it on both.
- With one result the page hides the chart of the median net worth: the fan chart of the tab shows
  the same lines. With two or more results, a section compares two of them path by path (rule
  `analyses`; A and B: a chosen scenario as B and the nearest chosen one that it extends as A,
  `pair` and `extended`, so buy or rent shows the purchase; else the first two; a run that leaves
  the selection gives way to the first run that the other side does not show; a select holds the id
  of a run, its scenario and `twin`, and shows its label). `?compare=<stem>` (`ui.COMPARE`, the link
  of the Scenarios page) chooses the scenario after the nearest scenario of its chain that runs
  (`compared_with`) and drops A and B.
- Simple mode (rule `mode`; `mode.advanced()` once per run): `_run_options` draws `Model`, `Paths`
  and `Nominal euros` only while they differ from `montecarlo`, `runs.PATHS` and off (the caption
  `NO_HISTORICAL` with the `Model`). `View` and `drawn` (pure) pick the sliders and switches: one
  shows while `mode.shown` holds its key path (`EXPERT`, the feature of the path, a path that a file
  sets away from its default, rule `mode`) or it is moved (`Knob.moved`, `Switch.moved`: its carried
  state left the file value, also while its model leaves it off). In simple mode a slider of a
  return class shows only for a class that the first chosen scenario holds (`knobs.classes`: the
  `growth` of an asset or of a purchase, `cash` with a cash asset, always `STANDING`, equity and
  fixed income). A group shows with a control in it. A hidden control stands at its file value, so
  it joins neither the overrides nor the levers, the dials and `Sidebar.sliders` (`_Picked`): the
  sensitivity and the goal seek follow the drawn sliders. Below the last group `mode.hidden_note`
  names what simple mode hides (the run options, a group without a control by its name, else its
  sliders) and the features off that hide one, in both modes; `mode.Held.VALUES` words it `at the
  values as saved` (a class slider that stands at its file value is no default), a long note
  folds on a phone under `Hidden in simple mode`. A control dragged back to its file value is no
  longer `moved`: it hides on the next run. On a desktop simple mode takes the folds of a phone
  (`_fold(folded=)`) with the wide figures: `Net worth` open, the rest closed, so the sensitivity
  runs when its fold opens. Rejected (design): a fold `Advanced` around expert groups (no expander
  in an expander), a reset of hidden sliders on the switch.

## Code

- `src/dagobert/ui/explorer.py` is the page, `sliders.py` a slider and a switch (`Unit`, `Knob`,
  `Switch`, `GROUPS`), `knobs.py` their catalog (`knobs`, `switches`, `classes`), `seek.py` its goal
  seek, `runs.py` its cached runs and process pool, which the Overview shares (rule
  `explorer-runs`).
