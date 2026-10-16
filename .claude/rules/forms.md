---
paths:
  - "src/dagobert/ui/{fields,forms,formguard,widgets}.py"
  - "tests/test_forms.py"
---

# Forms from the model

The editors build their forms here; each page that uses them has its own rule. The save guard: rule
`save-guard`. The grids beside a form and the columns of its small grids: rule `grids`.

## Fields

- `src/dagobert/ui/fields.py`: `of(model, prefix)` gives one `Field` per leaf of a model, from its
  JSON schema: the key path, the `Kind` (which sets the widget), the `Unit`, the options of an enum
  (`titles` in words where it is a `model.base.Titled`: `Self-employed profit`; the file keeps the
  value), the bounds as the file holds them (`low`, `high`, `open_low` for `gt`), `default` (of the
  field itself, `ABSENT` for a required one), `nullable`, `empty` (`all` of a repayment), `help`
  (the description, the default as the help of a grid column names it, `(default: 30%)`, of the
  holding mapping for a nested field, `inflation mean` 2%, and how the unit reads; kept as English
  parts, `about`, `named`, `more`, `term`, and said like `label` in the language of the session,
  rule `i18n`), `section` (the optional model above it) and `columns` (`gridcolumns.Column`): of the
  rows of a list (also of a union, `anyOf` or the `oneOf` of the events), of the entries of a
  mapping by name (`MAP`: `returns`, a `value` column for a mapping of numbers such as
  `scale.categories`; a list of mappings inside a row takes no column, `_columns`: the `given` of a
  relative). An optional model is a `SECTION` before its fields. A mapping by name is a `MAP`;
  `entries` turns one of numbers into a number per name (per phase: `scale.salary` of the Overrides
  tab, `factor` of an `add_stream` form; `entry`: empty counts as 1, never required). A tag (`type`
  of an event) is no field.
- `shown` and `parse` give the one text of a value: euros `1.234,56` with a decimal comma or point
  (`euros`, a minus only with `signed`; the Spend quick add and the trade form read it unsigned), a
  share or a rate in percent (`2.5` for 0.025, rounded like the grid cells, so a shown value parses
  back to the same), a month `2027-05` (also `05.2027` or a day; any day reads as the first, the
  file keeps the 1st), a date in ISO (`day` also reads it day first with dots, `14.03.1965`, as a
  German user types it; bare digits stay unread, either order fits them; the start page takes it
  too), `null` where a null differs from the default (`care.index`: nominal). `parse` checks the
  bounds in the unit (`at most 100%`, `above 0 €`) and raises ValueError with what to type. An empty
  text is None: the fallback. A whole number goes as an int (`4`, not `4.0`), as the other writers
  keep it. `read` keeps the old value while its text is unchanged, so cents beyond two are not
  rewritten.
- The fallback of an empty field depends on what the mapping holds after the edits (the candidate):
  `fallback` takes it from `overrides.filled`, the defaults of each field in the mapping that holds
  it, of that mapping's own default where it goes too. So `inflation` without a file value takes 2%
  and 1%, with only `mean` its `stdev` takes 0, and with only `stdev` the `mean` is required. Of a
  field that the candidate holds, the fallback is what it takes once cleared, so a field never
  changes its own. `filled` fills no nested model that the candidate lacks (the `stream` of a new
  `add_stream`): until it holds one, its fields fall back to their own defaults (`Form.leaves`),
  else an untouched toggle (`taxable`) read as `false` once the defaults came. In a scenario the
  chain gives it (`overrides.fallback` of the candidate). `placeholder` names it with its source (`2
  (default)`, `3 from base`, `1.000 from assumptions.yaml`).

## Widgets

- `src/dagobert/ui/widgets.py`: one widget per kind, at a `Spot` (key, label, fallback, names,
  override, the label of the null toggle). A widget returns `ABSENT` when empty and the old value
  while it shows it, so an untouched form has no edits.
- A number is a text field. Its key starts with `decimal-` (`prefix`, the decimal keypad of
  `ui.keyboard`) when the bounds allow no minus, which the keypad of a phone may lack; a rate that
  may fall keeps the text keyboard. A whole number is `st.number_input`, step 1, with the model
  bounds (`gt=0` is 1); a value of the file that it cannot show takes a text field until it reads. A
  date is text, shown in ISO, its placeholder `YYYY-MM-DD or DD.MM.YYYY` (`SHAPE`): no
  `st.date_input`, whose calendar takes many taps back to a birth year and shows a day for a month.
  A bool is a toggle, in an override a segmented control, which can be empty: inherit. A choice of
  up to four options is a segmented control, more and the names of the inputs (`Names`, from
  `references`) a select box, which can be cleared. A number input and a select box start empty
  (`value=None`, `index=None`) with the value of the file in their state (`_seed`): one that starts
  with a value has no empty state, so it could not be cleared to take the fallback again. That state
  is a deep copy, so `store.NULL` survives a copy. A cleared choice is `ABSENT`, also over a null of
  the file (`_kept`). The fallback is marked in an option (`m (default)`), an option shows its words
  (`Form.choices`, `Spot.words`), a null option what null stands for (`Form.nulls`: `care.index`
  nominal), else `null`; an empty select box whose null is the default shows it as its placeholder
  (`extends`: `none: a scenario of its own`). A field of names without one to choose (not
  `Names.new`; the `extends` of a scenario that every other one extends) is a disabled select box
  with that placeholder: a text field took a name that the check refused only on save. Text is a
  text field (`note` a text area), `nocaps-` on ids, choices and names (`name` and `note` are for
  people and keep the capital).
- A list of names is a multiselect (`Names.new` takes a new one), empty is `ABSENT`; it takes the
  rest of its row (at 220 px the second name was cut). A list that the model also takes as null
  (`age_categories`) has a toggle for null (`Form.nulls` labels it): off, an empty list is a value
  of its own, `[]`; on, it is the default, in an override an explicit null over an inherited list.
- A list of rows is a small grid in the units of its columns, the first one pinned on a phone, the
  help of its columns there in the popover `Columns` (`tables.small_grid`, which the repayments of a
  sale and the grids by id of the Overrides tab take too, `tables.column_help`). A list of the file
  gives `RowEdits` from the grid state (`gridstate.edits_from_state`), so the store keeps the
  comments, the flow rows and the untouched cells; without one the rows go as a list. A mapping by
  name is a small grid with a key column (`tables.MapRows`, the key a select of `Names`), headed by
  `Form.labels` of the path and `name` (`Spot.key_label`: `asset class` of `returns`), else `name`;
  its changes go per entry and field. `Form.rows` gives the `MapRows` of a path (`Spot.rows`): with
  a `lead` column it comes first and the key column last, behind the toggle `All columns`
  (`gridstate.carry` keeps the edits over a turn, as in `edit_table`); an entry whose row shows as
  before keeps what the file holds. In an override the toggle `Override` starts the list or the
  mapping from what it inherits (a mapping adds entries and removes none: an override cannot remove
  a key), off shows that read only. An optional section has the toggle `Use` and its help, like a
  grid, in `ui.fold` (`About <label>`), collapsed on every device (the forms serve the pages of
  `Setup`). A section that a `When` turns off says why after `Use` and does not turn on, but one on
  turns off, as the model refuses it (`spending.vpw`). On a desktop the fields of one model share a
  row, 220 px each; a phone takes one column.

## Forms

- `src/dagobert/ui/forms.py`: a `Form` is the part of an input file that a tab edits: its fields,
  the file, `model` (the model of the edited mapping: its defaults, the live check), the key path of
  the mapping (`keys`: `("overrides",)` of a scenario, an item of a list `("events", 0)`),
  `override` (an empty field inherits through the chain), `new` (the form adds a row to the list at
  `keys` with these fields fixed, `{"type": "sell"}`), `labels` (of a field, of the heading of a
  model and of a grid column by the path of its field and its name, `Form.shown`), `terms` (the
  technical term before the help: `Sparer-Pauschbetrag`), `helps` (a help in words that replaces the
  description), `choices` (the words of the options), `when` (`When`: a field that takes effect only
  while a field drawn before it holds one of some values or its `unless` holds a value, else it
  shows disabled with why after the label of a bool, else as its placeholder: a label of 220 px
  wraps; `Spot.off`), `rows` (see above), `nulls` (what null stands for: the toggle of a list, the
  option of a choice), `negative` (numbers typed without a sign, no minus on the keypad, kept below
  zero: the loan of a purchase), `derived` (what an empty field takes from the candidate: its
  placeholder `own-flat from the name`, and `Form.filled` writes it into the edits before the
  checks) and `plain` (a message of the model in plain words, by the end of its text). `show` draws
  it and returns `Shown` (the edits, the candidate, the guard list, the `Edit` and the check of the
  write). A form that shows a value in another unit than the file keeps it overrides `mapping` (file
  to shown) and `stored` (shown to file, in `Shown.edit`): the salary of
  `scenario_overrides.ScaleForm` in euros, the file keeps the factor.
- `show` draws with the fallback of the candidate of the run before (`<key>-leaves`); when the edits
  change it (`Shown.refresh`), `save` reruns the page once per interaction, so a placeholder follows
  its siblings, but not when Save was pressed with the edit: a rerun drops the press.
- `edits` gives the changes by key path in the convention of the store (None removes, `NULL` writes
  null), `Typed.rows` those of the lists of the file. A section that is off goes (a null stays), in
  an override it writes null where the fallback has it on. One that is on but holds nothing writes
  `{}` (none while it holds a mapping), in an override it inherits again.
- The check runs in three steps: a text that does not read and an empty field that the schema
  requires and nothing falls back to (`Typed.unread`, `REQUIRED`) keep Save off; then the model
  checks the candidate over the rest of the mapping (`Form.problems`; an override merged into the
  assumptions through `overrides.effective`; a new row as the last of its list), `problems.located`
  on a plain mapping, without lines, `explain` (the trade form uses both), and what it refuses that
  the file does not hold already keeps Save off too (`Shown.refused`: the write would fail, such as
  a required class of `returns` deleted in its grid); what the file holds already shows as a warning
  and keeps Save on, as the write refuses only what it adds (rule `revisions`), so a fix elsewhere
  in a broken file saves; `store.write` loads every input. The messages go into a container above
  the form and name its button (`Form.button`: `Add` for a new row, else `Save`). A new row
  (`Form.new`) without an edit shows neither its empty required fields nor the model's problems: it
  lacks what its type needs, and `Add` is off anyway. Of a new row, which is no line of the file
  yet, `Form.explain` names a problem by the term of its field (none for the row itself, the type
  and id that a check of a row puts first dropped, `plain` applied) under `Add stays off:`.
- `src/dagobert/ui/formguard.py`: `changes` gives one `guard.Change` per changed field, labeled by
  its key path (`returns equity mean`, each key by `gridcolumns.keyword`: German `Renditen equity
  Mittelwert`; `Change.key` keeps the English path for a caller that matches it), of a new row by
  `Form.term` (its label without the unit, after the heading of its model unless the label is its
  own: `Loan · Rate`, `Month`) as `Change.added`, the value alone, a month as `2029-03`, in its
  unit: a section `on` or `off` (empty while an override inherits it) without its fields, a list of
  rows per cell (`care hazard 1 factor`; by its `RowEdits`, a new row numbered after the last), a
  mapping by name per entry and field. A tab calls `guard.review` once with the lists of its forms
  and grids.
- `Shown.fill(path, more)` returns the form with the rows of a list that a save writes (added,
  edited, or a new list) completed by the cells of `more` that they do not set, before the guard:
  the id of a phase change (rule `scenarios`). A `Shown` is not changed after `show`: a caller keeps
  Save off with `save(ready=False)`.
- Save conflicts: a form keeps a `Base` per nonce in the session: the part that it showed first
  (`Form.part`: the top keys of its fields, so two tabs of one file do not refuse each other; of an
  item of a list, so an insert before it is a change) and its `revisions.seen`, none for a new row.
  Each run checks it (`conflict`): a change on disk without edits starts a new generation; with
  edits a warning above the form names the time in the browser's time zone and the page of the
  change (`save.changed_at`, as the grids; also a refused Save), `What changed there` lists it,
  `Discard my edits` starts anew, and Save stays off. The write checks again (`Shown.check`).
- `save` is the one Save of a tab: its forms and its `Grid`s (edit, check, nonce) as one
  `store.write` of the page and its `action`, the tab (`ui.source`: `Assumptions: Markets`), one
  `Edit` per file (`merged`, which keeps `create` and `remove`). It is off while nothing changed, a
  field does not read, the model refuses what the edit adds, a part changed on disk or the caller is
  not `ready` (a grid of its own whose cell does not read, the live check of the Overrides tab);
  while nothing changed its help says `No changes to save`. `Not saved: …` (`save.reason`) keeps the edits; a save
  raises every nonce and reruns, and the next run toasts `Saved <files>` (`ui.tell`: a toast before
  `st.rerun` is lost in Streamlit 1.65). The tab pins the button into the header: the style of
  `tables.SAVE_IN_HEADER` is its first element.

## Simple mode and the features

- They hide, never by `When` (it disables): the page leaves a field out of `Form.fields`
  (`assumptions.Tab.shown`, rule `mode`), so its file value stays in the part and the candidate, and
  a save neither removes it nor turns its section off. `Form.parts` adds the top keys of the whole
  tab to `tops`: the part keeps its shape, and so its conflict check, whatever shows.
- `edited(key)`: the fields of the form `key` with an edit not saved yet, before it draws. `show`
  keeps its run in `<key>-drawn` (`Drawn`: the edits, the lists with edits, a text that does not
  read, and the state of each widget with its field, `Typed.widgets`); `edited` takes those, and
  each field whose widget changed since that run (a value typed and the mode switched before a run
  saw it) or whose grid holds carried edits (`carried-<key>`, the switch carries them). A page keeps
  such a field, so no edit goes with its widget state.
- `Form.hides`: the columns of a mapping by name that the mode hides by a path of their own
  (`returns.*.equity_correlation`). `widgets.mapping` puts those that no entry of the part holds
  behind `All columns` (`Spot.hidden`, as the key column of a `lead`): fixed per generation, the
  edits read with every column. A list of rows (`widgets.rows`) leaves them out (the ids of the
  phase changes), its edits read with every column too. `Form.computed`: read-only columns of a
  list of rows that each row gives (`tables.Computed`: the age of a phase change).
