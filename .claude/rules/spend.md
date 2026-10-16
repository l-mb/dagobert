---
paths:
  - "src/dagobert/ui/spend.py"
  - "src/dagobert/actuals.py"
  - "tests/test_{actuals,ui_spend}.py"
---

# Spend page and actuals

The file `actuals.csv`: `docs/manual/configuration.md`.

## Spend page

- The actual spending per expense category, entered by hand: first the form `Add` (a category, also
  a new one typed in; the euros spent, above zero; `Add to month`, the current one first), which
  adds one amount to the month in `data/actuals.csv` at once. The line under the form (`_said`,
  always there and at least as high as its button, in portrait as two lines of text beside it, a row
  that does not wrap, so nothing moves: the button wrapped below the text) holds how to enter, a
  rejected entry in red, or the last add (`spend.Added`, `LAST`), with cents and one sign, the one
  of the form: `Added 45,50 € to cash, 2026-10: now 45,50 € spent.`, with a warning when the month
  holds more refunds, and `Show 2026-10` while the grid shows another month. No toast: it covered
  the title, and one before `st.rerun` is lost. A rejected entry stays in the form, an added one
  empties the amount, and category and month stay for the next one, also after another page
  (`CATEGORY`, `ADD_MONTH`). Then, in a row that wraps (`spend-columns`: the month 25rem, the
  comparison at least 36rem, side by side on a desktop, where the grid of 370 px left most of the
  page empty), the heading `A whole month`, a month control, at first on the last complete month or
  on that of a link (`?month=YYYY-MM`, `SHOW`, `linked`; the attention table of the Overview), with
  buttons for the previous and the next month, and a caption with the planned categories of the
  month that have an actual (`actuals.Coverage`); a grid with the plan of the month
  (`actuals.planned`) and the recorded actual, the list of the save guard, a total row; `Take plan`
  fills the empty `actual` cells with the plan, a new row adds a category that the plan does not
  have, and `Save` writes the edits into the month as the file holds it then: a category edited here
  and changed elsewhere since (a quick add or a save on another device) is a clash, every other
  category takes the newer side. The clashes show above the grid, under a warning, one line each,
  `<category>: file …, yours …, at the start …`, with `Take the file` (drops the edit, a fresh grid)
  and `Keep yours` (the file amount becomes the start of the edit), and for several one more pair `…
  for all` (`spend.chosen`). Not in the sticky bar: eight clashes there covered the grid. A new
  clash also shows once as a toast, since the list can be out of view (`spend.CLASHES`). `Save` is
  off while one shows. A clash that comes between the run and the save saves nothing, a toast says
  `Not saved: …`, and the rerun lists it. Unsaved edits of the grid stay with their month while
  another one shows, and the caption names those months; `Discard` drops those of the month. In
  portrait the total row and the buttons stay at the bottom of the screen while the grid shows (the
  container `spend-grid` bounds them; they cover its last rows until the page reaches its end, but a
  field that the browser scrolls into view stops above them, `scroll-padding-bottom`, not a row that
  the canvas grid scrolls itself; padding under the grid would only add a gap at its end). Its empty
  last row, where a new row goes, has no label (`placeholder` fills empty cells only). Streamlit
  1.65 cannot do better for either (rule `ui`). On touch its toolbar keeps add row and fullscreen.
  The rest of the help folds into `How to enter a month`, which says why Save sits under the grid:
  it saves the month that the grid shows. A save says `Saved <month>` after its rerun (`ui.tell`)
  and drops the line of a quick add into that month, whose sum it names from before. Categories sort
  without regard to case. Beside it, or below on a narrow screen, `Actual against plan`: the last
  twelve recorded months without the current one until it ends: per category plan, actual,
  difference and its share (in portrait without the number of months, at 13 px), summed over the
  months in which the category has an actual, the spending per month against the plan, and the
  difference per category as bars below both, side by side above 960 px.

## Code

- `src/dagobert/actuals.py`: `actuals.csv`. `read`, and two writers of one month, each one revision
  of the whole file, sorted, that reads the month inside its write and so counts a change on another
  device (`_write`): `add` (the quick add: two devices both count, it never conflicts; returns the
  amounts of the month before and after; `add_spent`) and `save_draft` (the Save of the grid:
  `merge`s a `Draft` and raises `ClashError` with the `Clash`es, writing nothing). `read` adds the
  rows of a month and category up in cents: a float sum such as -30.299999999999997 made edits and
  clashes of nothing. A `Draft` holds per edited category an `Edit`, `(was, now)`: the amount of the
  file when the edit began and after it, None for none. `applied` lays it over the file. `merge` is
  three-way: an edit applies where the file holds `was` or `now`, else the category clashes and
  keeps the file; a category without an edit keeps the file. `planned`: the plan per expense
  category of a month, the `cashplan.sheet` of that date in the phase of the main scenario
  (`Scenario.phase_of`: a month before its first change takes the first; the help names it by its
  label). It uses the current `cashflows.yaml` as written: euros of the simulation start, no
  inflation, no events of the scenario, the PKV premiums up to `tax.gkv_from` of
  `assumptions.yaml` (`cashplan.with_gkv`). `Comparison` pairs plan and actual per month and category,
  only where the category has an actual. `Coverage` counts the planned categories of a month that
  have an actual, 0 included (other categories, such as cash, do not count). `missing` gives the
  reminder of the Overview: the first complete month since the first record whose `Coverage` falls
  short, only while a month from `KEEPING` (3) months before the current one holds a record: none
  for a user who never or no longer records (owner, 2026-10-13). `categories` gives the categories
  with a record.
- `src/dagobert/ui/spend.py`: the `Spend` page. `entered` reads the grid (rows of one category
  add up, also in another case, in the first spelling (`canonical`: a phone keyboard starts with
  a capital), an empty
  cell records nothing), `take_plan` fills the empty cells, `changes` lists a save for the guard
  (`guard.Change.outflow`: an amount above zero gets a warning). `quick` reads the quick add (a
  category of spaces is none), `fields.euros` its amount with a decimal comma or point, and
  `actuals.add` adds it. That amount is a text field
  with a decimal keypad (`inputmode` by `ui.keyboard`): a number field reads `,` and `.` by the
  language of the browser, and `20,50` became 2050 in an English Chrome. The same script turns
  off the capital at the start of a category (`autocapitalize`). The difference of the
  comparison takes `light-dark()` colors in its `Styler`, at least 4.5:1 on both themes.
- The Spend page keeps the unsaved edits of each month in `spend.DRAFTS`, written by the `on_change`
  of the grid before the run: a tap that leaves the month can come with the last edit. A draft holds
  only the edited categories (`spend.edits`) and lies over the amounts that the file holds now
  (`actuals.applied`): a quick add on the phone while the desktop holds edits of the same month is
  not saved back over. `edits` keeps the `was` of a category that the draft edits already, so a
  change elsewhere since stays a clash through every rerun and fresh grid; a new edit takes the
  amount of the file that the grid started from, what the cell held. Each run lists the clashes of
  the draft against the file it read (`actuals.merge`), and `Save` merges again under the lock. A
  quick add into an edited category on this device moves its edit at both ends (`spend.moved`), so
  the cell counts the add and it makes no clash, while a change elsewhere before it still does. The
  key of the grid holds the month, a nonce that a change of month, `Take plan` and `Discard` raise,
  a checksum of what its rows come from besides the draft (the saved amounts of the month, the plan
  and the recorded categories) and the language: its headers (`spend.HEADERS`, the labels of its
  `column_config`; the frame keeps the English names) in other words are another editor without the
  edits, so the grid starts again from the draft (`test_i18n`). A dynamic editor keys its state by
  its data too, so a new row (a quick add of a new category into another month) dropped its edits. A
  save, a quick add or a write on another device therefore starts a fresh grid. A fresh grid starts
  from the draft over the saved amounts and keeps that start while it lives (`spend.BASE`), so the
  row positions of its state stay valid. `Take plan` writes the filled cells into the draft. A grid
  back from another page starts fresh too: Streamlit dropped its state. AppTest sends no state of an
  editor back, so it draws a fresh grid in every run and cannot show the checksum at work.
