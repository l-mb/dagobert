---
paths:
  - "src/dagobert/{result,sensitivity,goalseek,difference,cli,runner,money}.py"
  - "src/dagobert/report/**"
  - "src/dagobert/ui/*.py"
  - "tests/test_{report,cli,money}.py"
---

# Money and units

- Money shows in one format everywhere, the one of the tiles: `1.234.567 €` (the console summary
  drops the ` €` of its cells, see `report/summary.py`). Text and `st.table` use `format_eur`. It
  rounds a half away from zero like the sprintf of a grid cell, so a total row and its cells agree,
  and what rounds to zero shows no minus. A number column of `st.dataframe` or `st.data_editor`
  stays numeric and takes `money.EUR_COLUMN` (a field of the unit `eur`, `gridcolumns.FORMATS`). Its
  printf format groups with a dot in any browser locale, but only whole numbers. So a grid shows
  whole euros, and the cell editor shows the exact value. Where cents matter, as in the amounts of a
  roll forward, the cells are text from `format_eur(cents=True)`: `1.234,56 €`. The `localized` and
  `euro` formats follow the browser locale, so do not use them. A figure takes `charts.LAYOUT`
  (`separators`: a decimal point and a thousands dot, the app keeps them in its own theme) and a
  euro axis `charts.EUR_TICKS`. Money in a figure is whole euros, so no number there shows both.
  Other numbers, such as rates and percentages, keep the decimal point: `14.1%` in text and `+1.0%`
  on an axis, also a share or a rate in an editable grid (the unit `percent`: a loan rate, upkeep,
  cost, guarantee, part): the cell holds the percent, `%g%%` shows `2.5%`, and its editor takes
  `2.5` (rule `grids`). The `percent` format follows the browser language and multiplies a fraction
  by 100: do not use it. A plain number (the unit `number`: the units of a security, also in the
  `securities` tab, m², Rentenpunkte) keeps its decimals and groups by a narrow no-break space, `1
  234.5678` (`money.NUMBER_COLUMN`: `%'`, a narrow no-break space (U+202F), `,.10g`; the sprintf
  takes the character after `'` as the separator of the `,` flag; ten significant digits drop the
  noise of a sum of lots, and below 0.000001 it shows an exponent; `money.format_number` writes the
  same text in Python, the units of the trade import preview). A euro slider (the explorer, the fold
  of the Flows page) takes the format of a grid column: `st.slider` formats with the same sprintf,
  `1.234.567 €`. So a `Unit` format is written for that sprintf (`money.GROUPED`), and
  `money.printf` shows the same text in Python: the tooltip of a slider, the levers of the
  sensitivity charts, the goal seek.
- Charts and tables show euros of the simulation start by default. `RunResult.cpi` holds the
  consumer price level of each path per month (`float32`, 1 in the first month), and
  `RunResult.euros` divides a `(paths, months)` array by it. Deflate first, then take
  medians and percentiles. Every money figure and the summary take `nominal` (default
  `False`), and `RunResult.unit` names the unit of axes and of the summary title (the
  headers stay short, the column help names the unit too). The unit is no field of
  `runner.Options`: the options are the cache key of the explorer's runs, and the switch must
  not start new runs. So `sensitivity.Outcome` holds the medians in both units. The ledger
  and the tax rules use the yearly level (`year_levels`), so start-year euros and the euros
  of the first month differ by a few tenths of a percent. Do not store real copies of the
  arrays: they would add 27 MB per array at 5000 paths.
- One sign rule for money on every page. A table whose rows add up signs every amount, money in
  above zero and money out below, so each sum is the sum of the rows above it: the Cashflows sheet,
  the Flows table (`Budget.totals`: `surplus` is income, taxes and spending, `wealth built` the
  surplus, `into assets` and the non-cash income), the change tables (green more money per month,
  red less: `ui.GAIN` and `ui.LOSS`, `light-dark()`, 4.5:1 on both themes), the stream grids,
  the Spend grid and comparison. A heading, tile, bar chart, diagram
  or form field that names its direction (`All outflows`, `income`, `Spent`, the Sankey,
  `bars.outflow_bars`, the `loan amount` of a purchase in its grid and form) shows amounts
  without sign. A line holds one sign only: the Spend quick
  add takes and names the euros spent, the grid shows the month below zero.
