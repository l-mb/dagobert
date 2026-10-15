---
paths:
  - "src/dagobert/returns.py"
  - "tests/test_returns.py"
---

# Return models

The providers of the returns and the consumer prices of a run. The generator of each random
purpose and the rest of the engine: rule `engine`. The series that `historical` replays: rule
`series`.

- Return modes: `fixed` uses the means only, also for gold and bitcoin (far above the median path of
  a large spread, a decision). `montecarlo` draws lognormal monthly returns (`returns._lognormal`):
  the standard normal shocks z of `returns.equity`, and per class its own e of `returns.<class>`,
  mixed as ρ·z + √(1 − ρ²)·e for ρ = `equity_correlation` (one factor, no matrix). Equity takes z,
  and a class without a correlation takes e alone: numpy's `normal(loc, scale)` is loc + scale ×
  `standard_normal`, so these draws are the ones from before the correlation, bit for bit, and runs
  pair up whatever the other classes draw. `historical` replays rolling cycles, one path per start
  month of the aligned series, with wrap-around at the end, all from `series` (rule `series`):
  equity is `msci-world` of the data directory (fetched from Curvo, net EUR from 1969-12, before
  1999 USD rescaled by a constant, or imported), without it the model is off (`MissingSeriesError`).
  The CPI is the chain of the West German index and the VPI (`series.cpi`), fixed income the
  Bundesbank Umlaufsrendite. The class of a gold or crypto asset replays its series of
  `returns.REPLAYED` (`gold`: World Bank in euros from 1960), which then joins the window, so a plan
  without such an asset keeps its window. One without a series (`bitcoin`: its data from 2010 hold a
  growth by about 10,000 up to 2013) draws as in `montecarlo` with the seed of the run, z the log
  return of the replayed equity month standardized over the whole window (a window without spread
  gives no z: the class draws e alone). Its moments are approximate there: the equity months are
  skewed and fat-tailed, so on the MSCI window ρ = 0.4 lifts a mean of 30% (85% spread) to 31% and ρ
  = 0.9 to 34%. Cash and every other class use the assumption mean.
