---
paths:
  - "src/dagobert/ui/position.py"
---

# Value over time

The chart of a security below the tables of the `securities` tab of the Assets page (rule
`tracking`; owner 2026-10-29: the value against the invested money, real or nominal).

- `ui/position.py`: the heading `Value over time`, a select of the securities that the table lists
  (`assets.securities`, keyed by the asset id: each asset keeps its choice), the switch `Nominal
  euros`, then `tracker.position_figure` of `position.position`, with a caption that a few stored
  prices draw a few points. A security without a price shows a caption that names the Snapshot
  page instead (an info would come before the messages of the trade import).
- `position.position`: from the first buy or sale on, the value of the units held at each price of
  `prices.price_history` (the stored prices and, for `XAU` and `BTC`, the months of their series,
  rule `prices`), the units after the trades of that day (`lots.held`); their cost with fees (not
  the basis: the Vorabpauschale is tax) on each day with a price or a trade; each buy and sale
  (`tracker.Traded`) at the cost after its day. After a sale of all units without a later buy it
  ends. Real by default: in euros of the last price date, as the real returns of the table, each lot
  at the consumer prices of its purchase, a value at those of its day (not euros of the simulation
  start, the unit of the plan charts in rule `money`); the axis says the unit (`result.unit`).
- `report/tracker.py`: `position_figure` (`Position`) draws the value as a line in `BLUE`, with a
  marker per price up to `SPARSE` prices (a few typed prices read as points), the cost as dotted
  steps in `GRAY` (`hv`), each buy a triangle up and each sale a triangle down on them, the hover
  `{units} units for {amount}` as traded; a unified hover with ISO days, the month ticks of the
  other tracker figures (`_month_axis`), the legend above.
