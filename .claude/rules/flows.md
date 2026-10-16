---
paths:
  - "src/dagobert/ui/flows.py"
  - "src/dagobert/ui/page.css"
  - "tests/test_ui_flows.py"
---

# Flows page

Its budget comes from the ledger: rule `ledger`.

## The page

- One scenario (`stem · name`, `ui.scenario_titles`, at first the main one, marked `(main)`) from a
  single `fixed` run: beside the scenario and the amounts an `Options` popover with the fold of
  small items and two switches, its label names the switches that are on and a fold other than 50 €
  (on a phone only their number, so the button keeps its place): `One-offs` adds the one-offs such
  as a sale, a severance and the repayments from them, the tax on them under taxes and SV, `Run
  rate` spreads a payment every n months over the months that earn it; in the same row, which wraps
  (all four fit a phone in landscape), the select `Compare with the inputs before` (the local days
  with a revision of the plan that have a revision before them, `ui.since`, whose inputs then hold
  the scenario, `revisions.named`: before a rename its old file, which the run takes; newest first,
  as `ui.day_said`; it opens on the newest, so its own changes show; gone without such a day, and
  the caption says so; inputs that do not load with the model of today give a warning and no
  brackets, so do inputs that the engine refuses, with its reason, `runs.Refused`); the note of the
  scenario (`ui.scenario_note`); a table of the means over each phase stretch (income, taxes,
  spending, surplus, into savings plans: what the plans paid, part of the surplus, only with a plan
  (`flows._comparison`), into assets: the loan principal less what a policy pays as income, with
  `One-offs` also the other side of the moves, non-cash income: the growth of the assets and what
  goes into a policy without passing the cash, the severance part and the top-up to the guarantee
  only with `One-offs`, and wealth built: their sum, the change of the net worth before the latent
  tax, see `Budget.wealth_built`) with the change against the inputs of the last revision before
  that day (`runs.baseline`, `runs.at_revision`, as `Records against the plan`:
  `revisions.materialize`, the same `fixed` run, the cached one of the files while they hold those
  inputs; an error of the run other than a ValueError raises: a bug), signed like the Cashflows
  sheet (rule `money`). Its caption says so and that a phase the scenario does not reach has no
  column; below it the lines (`LINES`) and the terms (`cashflows.terms`) in `What the lines and
  terms mean`, and why the Cashflows page differs, with a link there. Then one tab per stretch
  (named by the label of its phase, which gets its years when it occurs twice; on a phone only the
  open tab draws, a closed one keeps its period and picked group), opening on the whole stretch,
  with a slider for its calendar years between two step buttons (above them the months, and where
  the taxes hold a part of the SV the short names in words, `SV_TERMS`: the boxes name `RV` and
  `AV`), the tiles and a Sankey diagram titled `<stretch>, per month`: income sources, then taxes
  and SV beside the budget, then the spending groups, then their items. In a main area up to 860 px
  (portrait, landscape with the sidebar open, a narrow window) the outflow bars with their picker
  (`bars.outflow_bars`) stand in for the diagram, below a hint to turn the phone or close the
  sidebar and the switch `Show the diagram anyway` (`flows-diagram-<stretch>`, kept per page): it
  draws the diagram 1000 px wide in a box that scrolls sideways instead. The rest folds into `How to
  read this`.

## Code

- `flows.flow_figure` draws the Sankey diagram itself: `flows.Layout` computes node spans and
  bands in pixels, the figure holds one filled scatter trace per band and node (hover on the
  fill) and two text traces for the labels. Do not go back to `go.Sankey`: its placement
  interleaves the items of different groups, and with fixed positions it still orders the bands
  at a node by its internal layout (50 iterations, not configurable), so a thin band crosses a
  wide one. Items stack in the order of their groups, a node to their left sits in the middle
  of what it pays for, `from savings` shares the column of `income`, a surplus runs through a
  `surplus` node in the group column, bands at a node follow the order of their other ends. A
  source below zero (the loss of a business) has no band (`_Links.add` keeps values above zero), so
  more flows into the `income` node than out of it; the table and the tiles hold the loss. Nodes are
  `(level, label, group)`: two groups can hold the same item name. Color names the role (income,
  taxes, spending, loans, savings), the label names the node: twenty categories have no distinct
  hues. The labels are 14 px (`LABEL_SIZE`) in the color of the page text: Plotly writes a color
  into each label, and the theme of the app makes it a light gray on the light theme, so CSS on the
  key class of the charts (`LABEL_INK`, `fill: currentColor`) overrides it in both themes, and the
  hover label takes 14 px too. The report has no Sankey diagram. A node starts at least `PITCH` (18
  px) below the one above it, so a sliver keeps a line for its label, also when a severance scales
  the items down. The labels of a group and of a long item beside it need the width: 14 px fit
  from 1,000 px, 12 px from 860 px (a phone in landscape: 882 px, measured on a full plan).
  The container `flows-view-` of each tab is a container query (`ui.PAGE_STYLE`): up to 1,000 px
  the labels take 12 px (`!important`, plotly writes the size into each label), up to 860 px the
  rules hide the layout wrapper of the container of the diagram (key prefix `CHART`) and show
  the outflow bars (`flows-bars-`) instead, a wider one the reverse. A query on the width of the
  main area, not of the viewport, so an open sidebar counts. A hidden container in a shown
  wrapper would keep the gap of the tab. A diagram hidden at load takes the full width after a
  turn to landscape. With the switch the container is `flows-scroll-`, which no query reaches,
  and the element of the chart takes a `min-width` (Streamlit draws plotly at the width of that
  element, not of the chart inside it). Its Fullscreen is hidden: it would squash the diagram to the
  height of the screen. The Fullscreen of the bars fills the screen despite the container query.
