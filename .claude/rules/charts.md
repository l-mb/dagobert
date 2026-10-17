---
paths:
  - "src/dagobert/report/**"
  - "src/dagobert/ui/__init__.py"
  - "tests/test_report.py"
---

# Figures and the report

After a change of a figure, run the check at the end of this rule, and for a figure of the
app the skill `app-check`. `ui.chart` draws every chart of the app: rule `ui`.

- `src/dagobert/report/`: plotly HTML, rich table. `money.py` (a leaf) holds the euro formatting.
  `charts.py` holds what every figure shares: the color palette and `layout()` (the template and
  the separators of the language), titles, legends, hover labels (a percent as text, `percents`),
  percent ticks (`tick_format`, rule `money`) and the age axis with its phase bands and
  markers. The `go.Figure` builders (public, the app reuses them) are a module per theme: `fan.py`
  (the liquid fan, the difference), `comparison.py` (the scenarios by age), `balance.py` (the
  balance sheet, whether the money lasts: rule `balance`), `flows.py`, `sensitivity.py`,
  `anatomy.py`, `tracker.py`. Those of the explorer build traces and layout as mappings, one figure
  at the end (`figure`, `merged`, `Grid`, `hline`: a setter validates again, 0.33 s for 13 against
  0.24 s), whose JSON gives it back byte for byte (`ui.figures`). The builders of the explorer take
  `compact` (`ui.is_mobile()`, the report never): the title breaks after the scenario and wraps a
  long one at 38 characters
  (`split_title(name, subject)`: a name with a colon stays whole; `title_room` grows the top margin
  by 42 px per line beyond two: plotly centers the first line of a title in the margin and lets the
  others flow below), the legend sits below the plot and the height grows by it (`legend_below`:
  plotly takes the room of a legend from the plot; it stays in the lower half, so a long marker
  legend grows the plot: plotly reserves the top margin down to a legend at `y` 0.5 or more, and the
  plot had no room, `Something went wrong with axis scaling`, which stopped the figures after it in
  the tab of the report; the entries of short names take an equal share of the plot width,
  `_row_share`, so a legend keeps the rows it reserves in landscape too, and names of any length
  keep their width: plotly clips a name longer than its share), a tap anywhere lists every line at
  its age (`hovermode` `x unified`), the age axis ticks every tenth age with 32 px on the right
  (`TICK_ROOM`: the phone has no side margins, and plotly hid the label of age 100 past the figure),
  and the range buttons of the fan get a row of their own just above the plot, at 14 px with `Up to
  p75` on two lines: plotly makes a button 33 px high up to a font of 23 px, two lines make it 40
  px. `anatomy_figure` then draws one column and leaves `anatomy.READING` to the page (`ui.note`),
  `sensitivity_figure` one panel (rule `analyses`). `difference_figure` stacks total and liquid on
  one scale (`legend_below(plots=2)`, the age axis titled once below both) under the title `B less
  A, path by path`: the selectors above name A and B. `tracker.py` holds the figures of the tracker
  pages, with text at 14 px: `sunburst_figure` (rings from `Slice` paths, the total in the hole,
  values in whole cents so that `branchvalues="total"` adds up exactly, a sector inherits the color
  of its parent, a label that does not fit at 14 px is hidden; `maxdepth` and `height` for a phone),
  `bars_figure` (horizontal bars of `Slice`s, the largest on top, colored like the sectors; `signed`
  keeps the negative ones left of a zero line and puts a value inside a bar long enough for it, so
  it keeps clear of the labels; `below` puts the bars of some groups below the others; 30 px above
  the top bar for the modebar; the labels in a fixed room, `LABEL_ROOM`, less with `compact` on a
  phone, so stacked charts such as the outflow and the income bars start their bars at one x, where
  automargin fitted each to its longest label: a longer label takes a second line in `ticktext`
  (`_fit`, at a space; the bar pitch holds it), only a longer one is cut with `…`, and its bar keeps
  the full name in `y` for the hover and the pick), `history_figure` (debt in the red of the loans
  in `balance_figure`; `height` for a row of two charts; bars of `MONTH_BAR`, 24 days: plotly made a
  bar as wide as the gap to the next record), `spend_figure` (actual spending per month as bars, the
  plan as a line, both upwards) and `track_figure` (records in `GRAY` over a `Band`: p5, median and
  p95 of a `(paths, months)` array of a run per month up to a date, as given, so nominal for `total`
  or `liquid`; the full trace names in the hover). The records of both and the observed net worth of
  `balance_figure` come per month with a snapshot: `charts.gapped` breaks their line (None) after a
  month that the next record does not follow, a marker each, so two snapshots far apart draw no
  growth between them. These three have the legend above the plot and month ticks that end at the
  last month, one per month or every n-th so that at most `labels` show (`ui.month_labels`).
  Plotly's own step leaves 80 px to a label, so it would label every second month where each fits,
  and days on a short span. `track_figure` widens its range by half a step at both ends: plotly
  hides a label that runs past the figure, and its lines, unlike bars, leave no room. `anatomy.py`
  holds the failure anatomy figure and its text: `reading` is `READING`, with `TIED` when a panel
  shows the return of a gold or crypto class (`anatomy.holding_return`), whose `equity_correlation`
  gives it part of the slope of equity; a third subtitle line grows the top margin by `LINE`, 32 px
  (plotly centers the title in the margin), compact 150 px above the first panel title. `summary.py`
  holds the summary: `SummaryRow` (the numbers of a run), `COLUMNS` (per column a `Column`: its
  term, plain header, help and cell, so a header never parts from its figures), `summary_columns` (a
  `Shown` per column for some runs: `label`, the plain header, and `tip`, the help with the term
  first), the difference table and the console summary. A measure names the age of the month that it
  takes (`RunResult.age_at`: a run that ends before 90 or starts after 67 takes its last or first
  month), in the summary the age that every run takes it at, else the age of its term with the runs
  at another age in its help (`taken_at`, also the target of the goal seek, rule `goalseek`) and the
  ends as a list (`to age 80 or 95`), in the difference table one column per month and whole age (an
  end a few months past 90 reads `at 90` too: the column keeps the month of the measure, keyed by
  its header), in the sensitivity panels by `Outcome.ages`, in the anatomy by `Anatomy.age`; the key
  of a column stays its term (`P(broke)@90`). `page.py` assembles the HTML (`write_html`, see below)
  with its style `report.css`, `phone.css` and its tab script `tabs.js`, files of the package. A
  scenario tab opens with the `note` of its scenario (`RunResult.note`, from `Scenario.note`) as a
  `p.note`; the console summary leaves it out, and `P(disability)` (`Column.console`). The console
  table fits a terminal of 120 columns: its title names the unit once, so the money cells leave out
  ` €`, a plain header wraps at `HEADER_LINE` (9) characters, the width of `1.234.567` (at 11 the
  eleven columns left the scenario 7), a long scenario name folds, and a figure never wraps. A
  narrower terminal gets lines of 120 columns that run over, because rich would cut the figures.
  `__init__.py` re-exports the package API.
- A figure builder never reads `st.context`: a phone variant is a parameter.
- Words (rule `i18n`): a builder writes them through `_()` in the language of the page that draws
  it, the run holds data (markers, `anatomy.drivers`). `RUN_OUT` takes `{age}` (`run_out()`),
  `MARKER_KINDS` and `PAID` (one message per `Marker.form`) are messages, `class_name` names a
  return class (context `class`, another class by its key), `Shown.label` a summary header
  (`Column.header`; the console summary prints it in English). The page of the report speaks the
  language of `i18n.use` (`run --lang`): the headings, the tabs and the summary title; the headings
  `Liquid` and `Flows` in the context `heading` (`Liquides Vermögen`, `Einnahmen, Ausgaben und
  Steuern`: not the row of a table, not the page name); the model by its value of `--model`
  (`montecarlo`). The axis of the flows names the unit per year (`RunResult.unit(yearly=True)`, `€
  pro Jahr, Kaufkraft 2026-10`). A msgid holds a line break as `\n` where a figure wants `<br>` (`Up
  to\np75`, the groups of the anatomy). German runs longer: compact, `split_title` wraps the subject
  at 38 characters too (`title_room`, also in `comparison`), and a legend of `shared` names takes a
  row each when one is longer than its share of `ROW_CHARS` (30: `liquide (Median)`); wide, a
  sensitivity panel title over `_PANEL_LINE` (44 characters) breaks before its value. English keeps
  its layout, but the compact marker legend: plotly cuts a line longer than an entry
  (`legend._maxWidth`, by the plot width), so it wraps at 34 characters in both languages, which fit
  the narrowest compact figure, the fold of an Explorer tab on a phone (346 px; about 36 fit there,
  41 in the report at 412 px; at 44 an `Ausbuchung: …` or a `Zahlung ändert sich: …` ran past it).
- Plain words: a title, an axis and a legend name what they show (`net worth`, `run out`, not
  `total`, `broke`), the terms of the report (`P(broke)@90`) stay in the help. Every age axis is one
  axis (`age_axis`): a tick at every fifth age, compact every tenth, each with its calendar year
  below, the title `Age and year`. A marker reads in words, written from its data (rule `engine`):
  `charts.said` what it says (`Policy pays 5 € per month`, `85.9% with 40 years`, German `85,9 %`, a
  full claim `100%` without its `.0`, the gain of a harvest `19.120 €`; `SAYS` of a kind that always
  says the same: `alg1`, the end of the claim `alg1 used` and `alg1 expired` (§161, rule `alg1`),
  why no Gründungszuschuss pays (`gz gap`, `gz days`, `gz salary`, rule `alg1`), the law behind
  `exemption` and `gkv`, rule `gkv`, its paragraph `{law}` of `LAWS` with no-break spaces, so a
  legend never parts `SGB` from `V`), `readable` its kind in words before it (`MARKER_KINDS`, one
  entry per `result.MarkerKind`, a test holds them equal: a `lump_sum` of `Car` is
  `One-off payment: Car`, `alg1` `ALG1: …`, an estate drawn per path
  `Inheritance: Mutter (half of the paths)`, a policy payout keeps only `<policy> pays …`). The
  bands of the phases take `PHASE_COLORS` by the order of the phases of the plan (`_phase_colors`,
  `RunResult.phase_labels`; a phase of the run that the plan lacks after them), no name: the markers
  name each change by its label. The legend of the markers wraps at 110 characters, compact at 34. A
  run of the files (`RunResult.twin`, its label the scenario and `(as saved)`, `result.TWIN`) takes
  the color of its scenario, dashed and at `TWIN_OPACITY` (`comparison._styles`), in the legend too
  (owner 2026-10-17). The phase marker `Phase: Work` is translated (`Phase` is the same word in
  German; the label is data).
- The report (`write_html`) follows the color scheme of the browser (`prefers-color-scheme`: the CSS
  tokens `--bg`, `--fg`, `--muted`, `--line`, `--head`; the app follows its menu instead, rule `ui`)
  and fits a phone below `PHONE` (700) px: the media of the style element `phone`, which holds
  `phone.css` and which the tab script reads. Each figure is an empty `div.figure` and a JSON script
  with both variants, `wide` and `compact` (`_figure_html`: a builder by `compact`; a field of a
  compact trace equal to the wide one is `SAME`, about 3 MB less), without its template: the tab
  script draws the figures of a tab when it shows (`Plotly.react`), with `plotly_dark` or
  `plotly_white` (`TEMPLATES`, once in the page with `SAME` in the JSON `config`) and below `PHONE`
  the compact variant as `ui.chart` draws it on a phone: no drag mode, no toolbar, no double click,
  no side margins (the theme of the app has none); again when the width or the scheme changes. A
  plot takes the height of its element, which the script sets from the layout (450 without one).
  plotly.js comes once inline. A table scrolls in its own box (`.scroll`) with a shadow at the edge
  that hides more, on a phone its first column sticks, and a name of more than `LONG` (16)
  characters wraps at 8rem or more (`td.long`; a long scenario name pushed every figure off the
  screen). The summary shows the plain headers (`Shown.label`, the tiles of the Overview take the
  same words) with the help on hover (`Shown.tip`), and below it a `details` `What the columns mean`
  for touch. The tab `Difference from <first scenario>` names the reference, and a hash that names
  no tab or does not decode (`#%E0`) opens the first. A compact anatomy leaves its reading to a
  `p.note.phone`. `runner.Options.run_all` runs each file once and names two scenarios of one name
  by their files too (`scenariofiles.scenario_labels`), so the tabs, the colors and the difference
  tell them apart; `run` leaves out the templates with a note and ends with exit code 1 when it
  names only templates, and refuses two files of one stem from two folders (exit 2): one run would
  be lost.
- Colors: the categorical steps of `charts.py` are validated on the dark surface of the report
  and on the light theme of the app (the dataviz validator), those of the balance sheet and of
  whether the money lasts in rule `balance`. `GREEN` and `RED` also color the effect of a
  sensitivity step (rule `analyses`): ΔE 10.6 under deuteranopia (target 8) and 30.2 without, on
  both surfaces. A lighter fill of one step down (opacity 0.4 to 0.6) fell to ΔE 2.6 to 7.5 to the
  other color, so it takes white stripes over the full color, 12% of its area: averaged, the worst
  pair (green, striped red) keeps 6.5, and the stripes and the side of zero tell it too. The net
  worth lines of `balance_figure` and `history_figure`, and the net of `flow_figure`, are
  `charts.GRAY`. A light gray does not show on the light theme.
- `liquid_fan_figure` and `balance_figure` draw a dashed line per month with markers
  (`RunResult.markers`) and a numbered badge on it. A legend below the plot (`legend2`) lists each
  number with its month and labels, and a click on an entry hides line and badge. A badge closer
  than 1/40 of the age axis to an earlier one moves a row down. The figure grows by 12 px per line
  of the legend. Compact the gap is 1/12, each label takes a line of its own, wrapped at 34
  characters, the legend starts at the left edge of the figure with an entry per row in both
  orientations (the legend clips a longer line), and the badges show no hover label: a tap lists the
  lines at its age, and the nearest badge, even a far one, would join them.
- `liquid_fan_figure` opens with the axis cut above p75 and the median total. With p90 the median of
  a plan with a large lump sum still looked flat in nominal euros. The buttons show all values or a
  log axis. A button passes the range as two scalars (`yaxis.range[0]`): plotly.js converts a range
  array to log in place, and the button then sets a wrong range.
- `flow_figure` draws the net as the median of the net of each path (not the sum of the medians
  of the bars) and ends its axis 10% beyond the tallest usual stack of a year (`_usual_top`, inside
  the Tukey fence; when over a tenth of the years lie outside it, the fence applies to those
  again: a short working life before a long retirement keeps its years), up and down. A severance
  year does not set the axis then. A stack beyond the edge shows its value there.
- The summary table shows the median taxes: income tax, Soli, SV and capital gains tax of the whole
  run, less refunds. Each path adds up its own deflated months, then the median follows. Of the
  shares of broke paths by age it keeps only `P(broke)@90`, the figure of the goal seek and the
  sensitivity. The chart of the chance to have run out by age (`BROKE_BY_AGE`) shows every age (its
  axis reaches at least 5%: at 1% the ticks of `.0%` repeated), and `P(broke) alive` the risk over
  the lifetime. `Cuts` and `Raises` take the median of the months per path that the spending rule
  cut or raised (`RunResult.reduced`, `raised`; VPW at the floor, above the plan: their help says
  so, rule `spending`). A panel of the sensitivity names its measure in words (`RUN_OUT`, `Net worth
  at 67, € of …`).
- Report tests introspect figures with `fig.to_dict()`: plotly attributes trip basedpyright.

## Check

- Inspect the report visually: `google-chrome --headless=new --password-store=basic --disable-gpu
  --no-sandbox --hide-scrollbars --window-size=1400,3600 --screenshot=tmp/report.png
  "file://$PWD/out/index.html"`, then read the PNG. The figures sit in tabs below the summary table:
  `Comparison`, `Difference from <first>` with two or more scenarios, and one per scenario. Append
  the URL-encoded tab label as the hash (`index.html#Early%20retirement`) to show a scenario tab,
  and add `--virtual-time-budget=5000` so the tab script runs before the capture. Check both schemes
  and the phone with Playwright (`color_scheme="dark"` and `"light"`: headless Chrome takes the
  scheme of the system; a context of 412 x 915 with `is_mobile`; `full_page=True` takes the whole
  report; a new page per tab, as a hash on the same page draws no other tab). A headless
  `--screenshot` of 412 px drew the figures past the edge, which the Playwright context did not:
  only it counts. Check a report of `--lang de` too (`#Vergleich`, `#Unterschied%20zu%20…`).
