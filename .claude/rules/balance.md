---
paths:
  - "src/dagobert/report/balance.py"
---

# The balance sheet and whether the money lasts

The figures of `src/dagobert/report/balance.py`, which the report and the explorer show. What every
figure shares (`compact`, `legend_below`, `age_axis`, the palette, the check): rule `charts`.

- `balance_figure` stacks the classes, with loans and the latent tax downwards, and overlays the
  observed net worth (`Observed`: the nominal totals and the consumer prices, which the caller
  reads, `series.consumer_prices`). In euros of the start the observed values deflate by the
  consumer prices of their month (`returns.deflate`). A month after the end of the CPI series
  takes its last value. The colors of the classes are categorical steps, fixed per class and
  validated on the dark surface of the report and on the light theme of the app (the dataviz
  validator, adjacent pairs). Every class has an opaque fill in its color: the translucent default
  of plotly blends with the surface, and in it fixed income and equity, gold and property fell to
  ΔE 6 to 9 (a translucent red loan looked like the orange of fixed income). `GOLD` and `PLUM`
  (gold, crypto) lie beyond the eight hues of the palette: ΔE at least 12 under a color-vision
  deficiency and 16 without to their neighbors in the stack, also with one of the two absent;
  labels tell them from the classes further off. A class that is zero in every month takes no
  trace and no legend entry. Outside `compact` the legend has a `maxheight` for all its entries:
  drawn in a hidden tab of the report, it kept the height of a smaller plot and cut the last
  entries.
- `lasting_figure` (`Will the money last?`, the chart of engaging-data.com that the owner asked for
  on 2026-10-14): a stack to 100% by age from `RunResult.pay_ends`, the first month after the last
  salary or profit (rule `engine`; a gap between two jobs does not count: the owner's decision is
  the wealth at retirement), or the start for a plan without pay or whose pay runs to the end.
  `lasting_shares` gives its bands from the bottom by their English names: `RUN_OUT`, the share of
  the paths broke by then (`RunResult.broke_by`, the broke of P(broke)), then by `HELD` the others
  by their liquid net worth against their own in that month, below 1×, 1× to 2×, 2× to 5×, 5× or
  more (`MULTIPLES`, compared, not divided; a reference of 0 counts below 1×: no multiple of
  nothing, the comparison alone made it 5× or more), both in euros of the start or both nominal (the
  switch of the page: like with like). With the survival `DEAD` is 1 less the survival in that month
  (so a little gray at the first month, a decision), and every other band takes the survival: they
  add up to 1 in each month. Without the survival (`--no-mortality`) no `DEAD`. The hover is `x
  unified` in both variants and lists every band at its age, each rounded to 0.1% (`PCT_HOVER`), so
  the listed values may add up to 99.9% or 100.1% (a decision: the stack is exact); a legend click
  hides a band (plotly, no `groupnorm`: a hidden band leaves a gap at the top). The legend runs top
  down as the stack (`reversed`), compact two entries a row where every name fits `charts.shared`:
  three cut `5× or more` in the fold of an Explorer tab on a phone. The title is the question with
  `1×` at its age; `lasting_reading` is the line below the figure (a `p.note` in the report, a
  caption in the explorer): the month of the reference and, with the survival, the gray.
- Colors of `lasting_figure`, opaque fills: `RED` run out, `GRAY` dead, between them `GREENS`,
  an ordinal ramp of one hue (OKLCH 152°, L 0.75, 0.64, 0.535, 0.43), lighter to deeper with the
  multiple. The dataviz validator `--ordinal` passes on white (the lightest 2.09:1), on `#111111`
  (the report, the deepest 2.46:1) and on `#0e1117` (the app, 2.47:1). Neighbors under a
  color-vision deficiency (target 8): red and the lightest green ΔE 22.0 (deutan; 37.3 without),
  the steps of the ramp 10.5 to 11.2 (10.6 to 11.2 without: its lightness tells them), the
  deepest green and gray 17.4 (protan; 21.7 without). Red and the deepest green fall to 2.9 under
  protanopia: they never touch, red stays at the bottom, and the legend names both.
- Tests in `tests/test_report.py`: the bands add up to 1 with and without the survival, real and
  nominal, a path not run out holds 1× to 2× in the first month, one with a reference of 0 below
  1×; less spending runs out less and holds 5× more often (an engine run). `pay_ends`, also after
  a gap between two jobs: `tests/test_engine.py`.
