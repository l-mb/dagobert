---
paths:
  - "src/dagobert/{result,sensitivity,goalseek,difference,cli,runner,money}.py"
  - "src/dagobert/report/**"
  - "src/dagobert/ui/*.py"
  - "tests/test_{report,cli,money}.py"
---

# Money and units

- Money shows in one format everywhere and in both languages, the one of the tiles: `1.234.567 €`
  (the console summary drops the ` €` of its cells, see `report/summary.py`). Text and `st.table`
  use `format_eur`. It rounds a half away from zero like the sprintf of a grid cell, so a total row
  and its cells agree, and what rounds to zero shows no minus. A number column of `st.dataframe` or
  `st.data_editor` stays numeric and takes `money.EUR_COLUMN` (a field of the unit `eur`,
  `gridcolumns.FORMATS`). Its printf format groups with a dot in any browser locale, but only whole
  numbers. So a grid shows whole euros, and the cell editor shows the exact value. Where cents
  matter, as in the amounts of a roll forward, the cells are text from `format_eur(cents=True)`:
  `1.234,56 €`, in English too (owner, issue #23). A line of the save guard shows a value with
  cents only where it has cents (owner 2026-10-16, `guard.Change`: `6.240,10 € → 6.100 €`, not
  `6.100,00 €`). A figure takes `charts.layout()` (`separators` of the language, `money.separators`:
  a thousands dot, the decimal mark of the language; the app keeps them in its own theme) and a
  euro axis `charts.EUR_TICKS`. Money in a figure is whole euros, so no number there shows both. A
  euro slider (the explorer, the fold of the Flows page) takes the format of a grid column:
  `st.slider` formats with the same sprintf, `1.234.567 €`. So a `Unit` format is written for that
  sprintf (`money.GROUPED`).
- Percentages and plain numbers take the decimal mark of the language of the session (owner
  2026-10-16, `i18n.language()`): English `36.6%` and `5.00`, German `36,6 %` (a no-break space
  before `%`, `money.PERCENT`) and `5,00`; dates stay ISO (`2026-10`) in both. One helper per kind
  in `money.py`: `format_percent` (a share or a rate; `decimals` None keeps those of the value, a
  loan rate `2.25%`, a full claim `100%`; never grouped), `format_number` (a plain number, fixed
  decimals or ten significant digits, the thousands grouped by a narrow no-break space, U+202F:
  `1 234,5678`), `decimal_mark` (a number that Python wrote with a point: an age `67,5`, a line of
  the guard, a hint). Every text, metric, caption, cell of an `st.table`, hover and title of the
  app and the report takes them; the console summary prints outside `i18n.use`, so in English. A
  form shows a share or a rate in percent in its mark (`fields.shown`: `2,5` for 0.025) and reads
  either mark (`5,5`, `5.5`); a switch of the language rewrites the text of an untouched field in
  the other mark (`widgets._respoken`, with no edit). The target of the goal seek is a text field
  for that reason (`seek.target_field`). A hint with an example takes the mark of the language
  (`for example 20.50`, German `20,50`; `type a number, such as 2.5`, German `etwa 2,5`).
- What Streamlit 1.65 and plotly 4.1 cannot write in German: Streamlit's sprintf (`sprintfjs`)
  writes `toFixed`, a decimal point in any language (its `'c` only sets the thousands separator of
  the `,` flag). So a slider, a number column of a grid and a number input show a decimal point on
  a German page too, with the sign of the language (`pgettext("sprintf", …)` of the formats of
  `sliders.Unit` and of `gridcolumns.FORMATS`: German `%.2f %%`, a slider `2.25 %`, a cell of the
  unit `percent` `2.5 %`): the units `1 234.5678` (`money.NUMBER_COLUMN`: `%'`, a narrow no-break
  space, `,.10g`; ten significant digits drop the noise of a sum of lots, below 0.000001 an
  exponent), the returns and prices of the securities tables (`%.1f`, `%.4f`). The `localized`,
  `percent` and `euro` formats follow the browser locale, not the page (a German page in an
  English browser would show English; `percent` also multiplies a fraction by 100): do not use
  them. `money.printf` writes the text of a slider in the mark of the language (`2,25 %`): its
  tooltip, the levers of the sensitivity charts, the goal seek. A cell of the unit `percent` holds
  the percent, its editor takes `2.5` and reads its mark by the browser (rule `grids`). Plotly takes
  the decimal mark of `separators`, but its locale writes no space before `%` (it takes the decimal
  and thousands marks of a locale, not the `percent` of d3): a percent in a hover is text
  (`charts.percents` in `customdata`, `PCT_HOVER`; the sunburst its share of the total), and a
  percent axis (`.0%`, `+.1%`) takes `charts.tick_format`, in German the labels by `labelalias`,
  keyed as plotly writes them (a decimal comma, the minus U+2212), over the range of its values.
  The file list of an uploader (`12.3KB`) stays Streamlit's.
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
