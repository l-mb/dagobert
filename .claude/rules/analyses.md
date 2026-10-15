---
paths:
  - "src/dagobert/{sensitivity,anatomy,difference}.py"
  - "src/dagobert/report/{anatomy,sensitivity}.py"
  - "tests/test_{sensitivity,anatomy,difference}.py"
---

# Analyses of a run

The sensitivity run, the failure anatomy and the difference of two runs, which the explorer
(rule `explorer`) and the report (rule `charts`) show. The goal seek: rule `goalseek`.

- `src/dagobert/sensitivity.py`: one-at-a-time sensitivity run. `run` takes `Lever`s and an
  executor, two engine runs per lever, ranked by the change in P(broke by 90) in whole points,
  then in the median net worth at 90. A side at its bound is not run, one that the model refuses
  (`InputError`: a ceiling stepped to the trigger) is the base run too; the base run raises. A
  `Lever` compares without its words (`label`, `format`, `step`): the explorer keys its caches by
  it, and no cache key holds words (rule `i18n`).
- `src/dagobert/report/sensitivity.py`: `sensitivity_figure`, the tornado chart of the explorer
  (the report has none): per lever a bar of one step down and one of one step up in a row, the
  upper one thin where both point the same way. A bar takes the color of its effect on the
  measure of its panel (owner): `GREEN` where it improves it (less risk, more net worth), `RED`
  where it worsens it, `GRAY` without a change (`_EFFECTS`, by `_Measure.better`), never the
  direction of the lever (more spending is worse). The direction is the fill: one step up solid,
  one step down with white stripes over its color (`_STRIPES`; a lighter fill lost the hue under a
  color-vision deficiency, rule `charts`). The legend names both cues: the sides in gray, whose
  click hides a side in every panel, and `better` and `worse` in a `legend2` that a click does
  not change (entries of their own, `_key`: a trace of bars shows the color of its first bar);
  the hover names the lever, its value and side, the measure, the change and its effect. Wide
  both legends share a row below the panels, the colors right. Compact one panel, of the measure
  `measure`, its title (with the base value) as the subtitle: centered over the panel, the title
  of a total ran past the edge; its ticks at zero and at the end of the bars farther from it, to
  one digit, never turned (`_end_ticks`, `tickangle` 0: the ticks of plotly turned on a plot of
  200 px and ran into the legend, the nearer end ran into the label of zero at 360 px; a right
  margin keeps the label at the end, plotly hides one past the figure); below the tick labels the
  sides and the colors in the one `legend` (a click on a color greys its entry, a double click is
  off: it hid every bar): two legends lined up only when as wide, since plotly moves a legend too
  wide for the figure from the plot to its edge (`constrain`) and leaves a narrower one. Two
  entries a row where every name fits `charts.shared` (English, a 2×2 grid), else a row each
  (German, 4 rows), each `_ROW` of the legend width per row (plotly wraps a row that its entries
  fill exactly), at a `y` below 0 in pixels of the plot (`_LEVER` per lever, `_TICKS`, `ENTRY` per
  row) and an `x` just below 0: plotly gives a legend below and left of the plot the width of the
  plot and its left margin (`_maxWidth`), one at a `y` of the container kept the width of the
  plot, one at an `x` of the container reserved its width in the left margin.
- `src/dagobert/anatomy.py`: what sets the paths broke by 90 apart from the others, in numbers
  (`report.anatomy` writes the words: `label`, `groups`, `bin_label`; the last group of an age by
  `NONE_BY`, a context per event: `ohne Pflege`, `erwerbsfähig`, `keine`). `drivers` gives the
  engine one number per path and random driver, by its kind and name (`Key`): the nominal equity
  return per year over the first ten years and up to 90, the nominal return per year up to 90 of the
  class of each gold or crypto asset (`RETURN`, before the custody cost), the inflation per year up
  to 90, the growth per year up to 90 of each cumulative index that a stream or the care cost
  follows, the age at the start of the first care episode, at the onset of a disability (`DISABLED`,
  rule `disability`) and at each inheritance without a month (`INHERITANCE`, by the labels of its
  givers, user data: rule `estates`), infinite without one. `of` sorts the paths by each driver into
  five groups of equal size, an age (`AGES`) by ages: the care start by 80, 85 and 90, the onset by
  50, 60 and 90, an inheritance by the whole ages that split the paths that receive it by 90 into
  four groups (`_ages`), then 90; it gives P(broke by 90) per group and the medians of the broke
  paths and the others (of an age the share with it by 90, `groups`). A driver without spread is
  left out. It returns None when no driver is left or when no path or every path is broke, so always
  for a `fixed` run. `holding_return` tells the panel of such a class: the text
  `report.anatomy.reading` then says that a class tied to equity shows part of its pattern.
  `report.anatomy_figure` shows one panel per driver on one probability axis (report, explorer).
- `src/dagobert/difference.py`: two runs path by path. `Difference.of` takes B less A on each path
  and keeps per month the median and p5 to p95 of total and liquid, the median taxes paid so far and
  the shares of paths broke by then in one run only. `report.difference_table` (at 67, 90 and the
  end, each month once, headed by its age in the run; its first header names the unit only, the page
  names B and A: a long header leaves no room on a phone) and `report.difference_figure` show it, in
  the explorer and in the `Difference` tab of the report: each scenario less the first one of the
  command line, which sets the reference. The command runs every scenario with the same `--seed`,
  model and paths, so the paths pair up. It raises `ValueError` for runs of other months or paths,
  and the tab then shows the error for that pair. `report.DIFFERENCE_NOTE` explains the figures on
  both (in the explorer `ui.note`).
