---
paths:
  - "src/dagobert/ui/{tables,gridstate,gridcolumns,assets,snapshot,cashflows,fields,forms,formguard,widgets}.py"
  - "tests/test_ui_grids.py"
---

# Editable grids

The save guard of the grids is in the rule `save-guard`.

- A column comes from the JSON schema of its field (`gridcolumns.columns`): type, `Unit`
  (`model.base.units`), bounds, default and description as help, the options of an enum (in words
  through `format_func` where it is a `model.base.Titled`: the `kind` of a stream, a `Land` by its
  name, in the order of the names of the session where the English lists them so,
  `gridcolumns.in_order`, also in a form). A number takes the format of its unit
  (`gridcolumns.FORMATS`: euros `EUR_COLUMN`, a share or a rate `%g%%`, a plain number
  `NUMBER_COLUMN` (units, m², Rentenpunkte; rule `money`), else none: months, ages, factors), the
  bounds of the field (exclusive ones too: the model refuses the bound itself) and `Unit.step` (1
  for an `int`, none for a float without one: `units` of a trade need many decimals). A number
  column is a float column (`gridstate.frame`): of whole numbers only it became an integer column,
  whose editor dropped the decimal mark, `100,5` m² read 1005. A share or a rate is typed in
  percent, `2.5` for 2.5%, also in a grid (`Column.shown` and `stored`: the file keeps the fraction,
  rounded, so 1.1 becomes 0.011); its help says so. A minimum of 0 keeps the minus off the cell
  editor (`allowNegative`), so a phone keypad without one does no harm. The grid sets a number above
  the maximum to it without a word, so a share or a rate takes no maximum (the guard warns above
  100%, the model refuses on save), nor does a field of `Table.negative` (a maximum below zero would
  turn a 9 typed without the minus into the bound); one of `Table.unsigned` shows without its minus
  and takes a minimum of 0 (`Column.unsigned`: the loan of a purchase, rule `money`). `float |
  "all"` shows `all` as an empty cell, and an empty cell removes the key. A checkbox without a key
  shows its default (`Column.checked`, also in a new row: an empty box reads as false, `cumulative`
  is true), and a box at its default removes the key. `Column.header` heads it in the language of
  the session (rule `i18n`): the label of a phase as written, `Column.label` (English,
  `Table.titles`: the event grids, `month` for `at`) in words, else the keys of its name
  (`gridcolumns.keyword`); `Column.help` the same from English parts (`about`, `named`, `more`); a
  checkbox too.
- A nested model takes a column per field (`when age` of a sale), one level deep. `Table.fields` and
  `more` name a field by its key or a field of a nested model by its column (`property growth`),
  `Table.options` a column by its name (`bav policy`). `Table.inner` lifts the fields of one (the
  `stream` of an `add_stream`) under their own names (`Column.inner`), and an edit of either merges
  into its mapping (`store.Merge`, so the comment lines inside it stay; the guard lists a `Merge`
  entry by entry, `guard._merged`). A gated mapping (`factor`) goes whole with its gate list. A list
  of mappings (`trades`, `then`, also of a union) takes no column. `MapRows` turns a mapping of
  mappings or of numbers (`returns`, `scale.categories`) into rows with a key column and back (a
  form takes its changes by entry, `forms._map_edits`). `Table.num_rows` `add` removes no row (the
  grids of an override).
- `Table.options` makes a column a select of the names that exist (`Ref`: a `references.Kind`, the
  asset or stream kinds `sorts`, `new` takes a new name: tags), from `references.of` once per
  `ui.data_stamp` (`tables._references`), in the scenario of a scenario file: `index` (with `null`,
  a nominal amount: `Column.null`), `of` (salary streams without `of` in the file of the grid,
  `Ref.unless`: a bonus is no base; the options are per column, so a base salary lists itself;
  `Ref.without` leaves out names of other files, the bonuses of an `add_stream` grid), `repays`
  (loans), `after_sale_of`, `property` of a stream and `finances` of a loan (properties), `into`
  (the equity, fixed-income, gold and crypto assets of a savings plan,
  `model.streams.SAVINGS_TARGETS`), `growth` (return classes), `salary` (the salary streams of a bAV
  conversion that the model takes: `assets.unconverted` leaves out by `Ref.without` a name without a
  monthly row free of `of`, such as a bonus), `tags`. `cat` stays text: a row defines its category,
  and a select takes no new option. `Table.locked` keeps a column of a saved row (by its name,
  `gridcolumns.key_paths`, as `negative`), the `id` of an asset, the `name` of a stream, `property
  id` and `loan id` of a purchase: other inputs and the history name the row by it. `Table.rename`
  (the kind of the locked columns: the Assets and stream tables, the purchases) adds `Rename` beside
  `All columns`, which rewrites the name with its uses (`ui.rename`, rule `references`), and its
  help to those columns (`RENAME_HELP`). Streamlit disables a column for new rows too, so
  `Table.held` drops such an edit, and the guard names it (`notes`) until it is typed back;
  `Table.derived` fills the cells that a new row lacks from its others before the guard
  (`Table.filled`, as `forms.Form.derived`: the ids of a purchase, `events.purchase_ids`).
  `Table.check` adds warnings of no single cell about the edited and added rows to the same `notes`
  (the price of a trade of gold or Bitcoin against its series).
- An editable table is a `tables.Table` spec (row filter, fields, sort, grouping, hooks). A mapping
  of numbers by name (`factor` per phase; `Column.of` gives one `object` column with the unit and
  bounds of its numbers) becomes one number column per name of `Table.entries` (the phases of the
  plan with their labels, `cashflows.with_phases`, `events.table`), headed by the label, never a
  YAML cell; without entries it shows no column. `Table.gates` folds a list field into those cells:
  for streams the `factor` cells also carry `phases` (a cell shows 1 when the stream applies, 0
  switches the phase off, 1 is never written), so the `phases` column is gone. `Table.more` names
  rare fields behind the `All columns` toggle. A turn of it keeps the edits: a dynamic editor keys
  its state by its data and columns, so the grid with other columns is a new widget. The toggle's
  `on_change` (`gridstate.carry`, before the run; also the phases grid of a form, rule `forms`, and
  a switch of the language, the grids of `gridstate.drawn`) moves the editor state of each grid
  (each block) into `carried-<grid key>` and deletes it; the new grid shows its rows with them
  (`frame`, `applied`), and `grid_state` folds its own edits on top (`fold`: by the rows of the
  first grid), so the guard, `_held` and Save see both. Edits are read with every column
  (`Table.columns( everything=True)`), so a cell keeps its edit while its column hides. A save or
  `Discard my edits` starts a new nonce, which leaves the carried edits behind. `st.data_editor`
  cannot shade editable rows (it styles disabled columns only). `group_by` therefore draws one grid
  per group in a collapsed `st.expander` whose header is colored by CSS on its key class
  (`tables.key_class`) and holds the group, its number of rows and its total row
  (`tables.block_label`), with fixed column widths so the grids line up, and one Save button for
  all. A keyed expander keeps its open state when its label changes. Collapsed grids still draw: a
  filter that leaves grids out would drop their widget state and with it the unsaved edits. With the
  side padding of 16 px (`ui.PAGE_STYLE`, instead of 80) and the widths in `gridcolumns.WIDTHS`, the
  expense grids fit into a window of 1,500 px with the sidebar open. The income grid has more
  columns and needs 1,760 px with the phases of a new plan (`Career break` the widest label). The
  widths are the smallest that show the headers, an ISO date and the bold totals below the phase
  columns. `Table.totals` adds a bold row under each grid (`tables.total_row`): HTML cells with the
  same widths, shifted by `ROW_MARKER`, the checkbox column of a dynamic editor. A row inside the
  editor cannot be bold and stays editable and deletable. Grouped grids use `width="content"`: a
  stretched grid widens its columns and the total row drifts off. For streams the row holds the
  monthly sum per phase column at the `As of` date (`cashplan.phase_totals`), unsaved edits
  included: `_grouped` reads the edits of every grid from its widget state before any grid draws (a
  derived stream follows another group) and takes the rows from `RowEdits.result`. Known limitation:
  the row knows only the configured layout. It does not follow a horizontal scroll of the grid, and
  columns that the user reorders, resizes, hides or pins in the browser leave the totals under the
  wrong column until a reload. Streamlit does not report that layout to Python. A phone gets no row
  (its grid takes `Table.phone_order` and `PHONE_PINNED`), and `ui/page.css` hides it in a window up
  to 640 px wide or, on touch, 500 px high: the grid scrolls sideways, and the header holds the same
  totals, each on one line (no-break spaces). On the dark theme a block header is dim with a stripe
  in its color on the left, the color of its bars (`light-dark()`). A tap leaves a header hovered on
  touch, so under `hover: none` it keeps its color when hovered.
- Simple mode and the features (rule `mode`): `edit_table(file, table, view)` with `Table.grid`
  (`assets`, `streams`: the asset kind and stream grids) moves a column that `mode.View` hides
  behind `All columns` (`Table.columns(hidden=)`, as `more`, also of a table without `fields`: the
  asset grids, the AfA of a property is `EXPERT`; `more` stays the choice of the table whatever the
  rows hold: every row holds the `cat` of a stream and the ids of a purchase) and drops an option of
  a select that it hides (`tables.limited`: the `kind` of a stream by its stream kind, `deduct:
  childcare` by `children`; a value that a row of the grid or an edit holds stays). What the other
  inputs give (`tables._hidden`, both modes) is fixed in `save.Base.hidden`: a change of it
  elsewhere renews the base only without edits, like a write elsewhere in the file
  (`save.base(hidden=)`), so a grid with edits keeps its columns; the mode stays live, its switch
  carries the edits (`ui.chose`). `Table.grid` None hides nothing.
- On a phone a grid of `edit_table` keeps the columns of `Table.pinned` in view (`tables.pin`: the
  `id` of an asset, the `name` of a stream, the `date` of a trade). There `Table.lead` comes right
  after them (`Table.phone_order`: the value, balance, `per_sqm` and rate of an asset), and the
  pinned name of a block grid narrows to `tables.PHONE_PINNED` (120 px), so a few columns show
  beside it. An asset id keeps its width: ids differ at their end. On a desktop a pinned column
  turns gray and shrinks to its content, so the desktop pins none and keeps its order. Every other
  grid that pins goes through `tables.pin` too (the `asset` of the Snapshot page, the `security` of
  the securities tables). `pin` changes the configs it gets: pass new ones, never a module constant,
  or one phone session pins the column for every later desktop session. On a phone a grid grows with
  its rows (`height="content"`, a desktop scrolls a grid of 25 rows or more inside 800 px, a
  securities table after ten rows): an inner scroll would hold the swipe that should scroll the
  page. A tap on a header sorts and shows no help, so on a phone `tables.column_help` puts the help
  of the columns into a popover `Columns` (`Table.help_label`, `What the columns mean` on the Assets
  page) beside the `All columns` toggle. `Table.titles` gives a column a readable header
  (`Column.label`, whose help then names the key of the file); the cells, the edits and the key of a
  guard line keep the field name, its words the keys (`Table.names`). `Table.helps` replaces the
  help of a column where the schema says another default: the `index` of a savings plan is nominal
  without one, the field default is `cpi` (`cashflows.SAVINGS`). `Column.width` takes the label only
  for an entry of a mapping (a phase): `ENTRY_PAD` plus `ENTRY_CHAR` per character, at least
  `entry`, so `unemployed` takes 110 px. `Column.stored` keeps an emptied list as `[]` where the
  field is required (the `phases` of a bAV policy, a select of `Ref(Kind.PHASE)`) or has a default.
- A row that a link opened (`tables.focus`, `Focus`: its `Table.identity`, the `fields` to check,
  the digest of the row) lives in `<key>-focus` of the session, not only in the run of the link: a
  rerun with the rows in another order drops the edits of a dynamic grid. `edit_table` takes it as
  `Table.focus` before `save.base`: the row first (`Table.indices`), the headers of the fields with
  `FOCUS_MARK`, on a phone the fields after the pinned columns (`phone_order`), an `st.info` after
  the style of Save that names the row and the fields (`_focus_line`). A base whose row differs from
  the digest (a save of the row: the base follows the file only without edits) or lacks it ends the
  focus (`_lead`). Streamlit 1.65 styles no editable cell (a `Styler` reaches the disabled columns
  only, `data_editor` docstring), and the canvas takes no CSS per cell.
- The Save button of `edit_table` and `Record` of the Snapshot page are pinned into the page header
  by CSS on their key class (`tables.save_in_header`, `SAVE_IN_HEADER`). The style is the first
  element of `edit_table` and of the Snapshot page: an element before it that comes or goes (the
  list of the guard) would move it, and in a rerun the button then dropped into the page for a
  moment. A hidden tab hides its button, so only one shows at a time. Up to 768 px the open sidebar
  overlays the page and its close button lies under Save, so Save hides while the sidebar is open.
  In portrait Save sits beside the button that opens the sidebar (`left: 4.5rem`): beside the menu
  it covered the status widget of a run with its Stop.
- Date cells in the tables are ISO text columns. A `DateColumn` edits with the native date input of
  the browser, which follows its locale (mm/dd/yyyy). A month (`Unit.MONTH`, `Column.month`: `start`
  of a stream, `at`, `fixed_until`) shows `2027-05` as a form does, and reads it or a day
  (`ISO_MONTH`), any day as the first; the guard lists it so too (`guard._cell` by the unit, the
  month of an event in `guard.label`, the rows of a form in `formguard`).
- Save conflicts (one instance serves phone and desktop). A dynamic editor keys its state by its
  data and its column config, a fixed one by its schema and row count, so another device's write
  dropped the edits of a grid or let `Record` write over its value. So each grid of `edit_table` and
  the Snapshot grid keep a `save.Base` per nonce (`<key>-nonce`, `<key>-base`): the rows of the file
  when the grid first drew, the `Seen` of its part (`Table.part`, the shown rows; the revision taken
  before the read) and, with `Table.options`, the references of its selects. While the nonce lives
  the grid shows the base: the positions of its edits hold. Each run (`save.base`) compares the part
  now with the `Seen` (`revisions.unchanged`). Without edits in the widget state (`_held`: also a
  blank new row, also of a block; on the Snapshot page also the taken estimates) a changed part
  starts a new nonce on the rows now, and a write elsewhere in the file refreshes the base under the
  same nonce. With edits the base stays, and `save.warn` shows above the grid `` `assets.yaml`
  changed at 14:03 on Snapshot since this table was drawn `` with what Save does, `Changed there:`
  (`RowEdits.between` of the part, rows by `Table.identity`, a required field: a table without it
  would fall back to the place of a row; in the format of the guard: `guard.listing`; the trades of
  a depot as their count, `2 rows → 3 rows`), `Discard my edits` (a new nonce, the rows now) and
  once per new revision a toast. Save and `Record` pass `Base.read` to `RowFile.apply`: an edit of a
  row changed since is refused (`Not saved: … in a row that you edited`, also as a toast), the edits
  stay; the other edits go onto the newest file by name (rule `store`). `Take estimates` keeps the
  base under its new nonce (`save.renew`). A save of another grid on the same file is no change of
  this one. The API of `AppTest` sends no editor state (rule `ui`): check it with two browser
  contexts.
