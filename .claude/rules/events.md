---
paths:
  - "src/dagobert/ui/{events,lineage}.py"
  - "tests/test_ui_events.py"
---

# Events tab of the Scenarios page

The grids, their bases and Save: rule `grids`; the save guard: rule `save-guard`; the form
`Add an event`: rule `forms`. The scenario files and `drop`: `docs/manual/configuration.md`; the
user guide of the tab: `docs/manual/events.md`.

- `src/dagobert/ui/events.py`: `tab(path)` draws the events of the scenario file `path`
  (`<data>/scenarios/<stem>.yaml`), the `Events` tab of the Scenarios page, on a `Tab` (the file,
  its events, `tables.known`, the streams with `of`). One `st.tabs` tab per event type (`TYPES`, in
  the order of the `Event` union), named in words (`TITLES`, also in the timeline and the inherited
  events: the engine names `lump_sum` and `fund_policy` meant nothing to a user) with the events of
  the file and those it inherits and does not drop, and `EDITED` while its grid or the repayments of
  the sale chosen hold edits not saved yet (`_edited`, from the widget state before they draw):
  `Sell an asset (1, 2 inherited) ●`, `Repay a loan (1)`, `Write off shares`. Every tab draws, so a
  grid keeps its edits while another one shows (pills would draw one grid and drop the state of
  the others). A label that a save or an edit changes makes a new tab strip,
  which opens on its default: so the strip is stateful (`key`, `on_change`; `_open` finds the type
  of a label by the map of the run) and keeps the open type in `events-<stem>-open`, set on the
  first draw to the type of the file's first event, else of an inherited one (an empty grid of
  inherited sales hid the purchase of the file at the far end of the strip), scrolled into view
  like a link. `open_type(stem, kind)` sets it for a link to an event type (the query
  `event` of the Scenarios page) and once a script that scrolls the tab into view, watching for
  10 s at most (`_REVEAL`: a
  strip scrolls only to a tapped tab, and on a phone a later type lay beyond its end). A tab switch
  reruns the page.
- Simple mode and the features (rule `mode`): the strip holds the types that `mode.View` shows
  (`tab` takes `mode.view` once: the core types, those of any scenario file, `sell` with a
  property, gold or crypto), those with events of the file or its parents and those whose grid or
  repayments hold edits (`_edited`); it opens on the first of them without an event, not on
  `SELL`. Below the strip `View.note` names the hidden types (`lineage.INLINE`). The event
  grids hide no column (no `Table.grid`).
- Each type is an `edit_table` on `RowFile(…, ("events",))` (`table(stem, kind)`): `fixed={"type":
  kind}`, `at` first and pinned on a phone, the fields of the type, `id` and `note` last, the rare
  ones behind `All columns` (`MORE`: the price spread, costs, `taxable` and `end_tagged` of a sale,
  the bAV part of a severance, the factor and the `premium` of `set_stream`, the `building_share`
  and `afa` of a purchase, `building share` and `AfA rate` in `HEADERS`), the headers in words
  (`HEADERS` through `Table.titles`: `month`, `or at age`, `or when liquid below`; a header only:
  the pin, the edits and the guard keep the name, `at`); `identity` `("type", "at", "id")`, no field
  is unique and `store.keyed` counts equals. `FIELDS` names the columns of a type with nested models
  by column name: a `buy_property` shows the property name, the price, `land` and the loan amount
  (12 columns ran past a desktop and a phone), the ids and the rest behind `All columns`;
  `TYPE_HEADERS` and `TYPE_LABELS` call its `costs` `purchase costs`, `LABELS` its ids `Property id`
  and `Loan id`. A saved purchase keeps both (`LOCKED`: sales and repayments name them; a new row of
  the grid makes them as the form does, `Table.derived` with `purchase_ids` of `Tab.taken`; `Rename`
  of `Kind.ASSET` beside `All columns` lists both, rule `references`), and its loan is saved
  negative whatever sign is typed (`NEGATIVE`), as on the Assets page, and shows without its minus,
  the amount borrowed (`Table.unsigned`, rule `money`: the header names the direction). `REFS` gives
  the selects by key path, also of the form (the grid by the column name, the path joined by
  spaces): the asset of a sale (property, gold, crypto, as `Plan` checks it), of a `buy` (gold,
  crypto) and of a `write_off` (equity), `property growth` and `property tags` of a `buy_property`,
  `loan`, `policy` and `bav policy` (`bav`), `names` and `tags` of `end_streams` (no new tag: an
  unknown one is a model error), `name` of `set_stream`, the stream fields of an `add_stream`, whose
  `of` leaves out the streams with `of` in `cashflows.yaml` and the `add_stream` events of the chain
  (`bonus_streams`, `Ref.without`: a bonus is no base), whose `into` (behind `All columns`) takes
  the assets that a savings plan buys (`model.streams.SAVINGS_TARGETS`) and whose `property` the
  properties (a rent or a cost of letting, rule `rental`), `from` of an inheritance and a gift
  (`Kind.RELATIVE`, a multiselect of the relatives by their short names). That row lifts its
  `stream` (`inner`, `gates` of `factor` and `phases`, a `factor` column per phase of `Tab.phases`,
  `references.phases`), with the columns of the stream grids of the Cashflows page after `at`, `id`
  and `note`, the rare ones behind `All columns`, and no sign rule (one table holds income and
  spending). `id` stays text: a select column takes no new name. Each grid saves with its own Save
  in the header (a hidden tab hides it).
- The form `Add an event` above the grid, on every device (a phone adds no grid row, rule `ui`:
  `forms.Form`, `new={"type": kind}` on `("events",)`, the labels of `LABELS`): the fields of the
  type without `then`, of an `add_stream` a `factor` per phase (`fields.entries`, `FACTORS`) and its
  `phases` a select of them (`STREAM_PHASES`), `at` first, `id` (`Event id (optional)`) and `note`
  last, the id of a nested model after its other fields (`ordered`); its `Add` (the notices above it
  name `Add`, and an empty form shows none: what a new row lacks is no news before its first edit,
  rule `forms`) (`forms.save`) is off while the grid holds unsaved edits (`ready`,
  `tables.unsaved`), its help (`why`) says to save or discard them. The actions of a new sale follow
  under the grid once it is saved. A purchase (`Form.derived`, `purchase_ids`) makes an empty
  property id of its name (`ui.slug`, numbered where the inputs hold it: `own-flat-2`, `made`) and
  an empty loan id of the loan's name, else of the property (`own-flat-loan`); it takes the loan
  amount without a minus (`Form.negative`, `LOAN_BALANCE`), has helps in words (`HELPS`: no file
  words), the model's either-or of `land` and `transfer_tax` in plain words (`PLAIN`) and that rule
  as a caption above it (`EITHER`, of `CAPTIONS`, which also says that an inheritance without a
  month falls at the death and that a gift joins such an estate). An inheritance and a gift: `from`,
  `cash`, the section `equity` (`Securities`: `value`, `cost_basis`), headed `relatives`, `cash`,
  `securities`, `their cost basis` (rule `estates`). `table` names a column by the key of the file
  (`from`, the alias of the field `givers`), and one relative of the file shows as a list of one
  (`Column.shown`, also the multiselect of the form, `widgets`).
- Under each grid the ids of its events that an override (`shift`, `events`) or a `drop` uses, in
  the scenarios whose chain holds the file (`_ids`, from `references`): a changed id must change
  there too, or the save does not load.
- Under the sales `Repayments`: a select of the sales of the file (by their `store.keyed` name),
  a grid of the `repay` rows of the one chosen (the loan a select, an empty `amount` repays all,
  the file keeps no key) and the toggle `Invest the rest`, on `RowFile(…, ("events", i, "then"))`
  with `save.base`, `save.warn` and `save.button` (`Save repayments`, rows by `("repay",
  "invest")`). `actions` gives its edits: new repayments before `invest`, which moves last behind
  them and goes when the toggle is off. A conditional sale repays nothing (the model refuses it):
  only the toggle. The guard lists `repay flat-loan amount all → 50.000,00 €`.
- `src/dagobert/ui/lineage.py`: what a file inherits through its `extends` chain,
  which the Scenarios page shares, and an event in words (`TITLES`, `INLINE`, `describe`, `when`,
  `either`, `at_death`: an inheritance without a month `at the death of mother`, of two `at the
  later death of mother and father`, by their short names; `describe` the givers and the sum of
  cash and securities). `inherited(chain, key)` is
  the one list of the phases (`key`) or events of the parents, on the
  raw `loader.chain` (a parent that the model refuses still lists; a missing one gives a warning),
  each an `Inherited`: the stem of its file, the row, and the stem of the nearest file below that
  drops its id (`dropped`); the Scenarios page takes it too (its `Timeline` and `Phases`). `reach`
  keeps those that a toggle can take back: not dropped, or by the file itself, not by a file
  between (an id that no file above keeps does not load).
- `Inherited events` below the type tabs (`events._inherited`): first `leave_out` for the ids of
  `reach` (below a long table the toggles lay far from the rows), which the `Phases` tab of the
  Scenarios page calls for the phases (one id can name both, each tab has its toggle); then all of
  them, read only, by date, then an inheritance without a month (`AT_DEATH`, `at death`, as its
  month: `at_death` did not fit the column), a conditional sale last (`_order`; `on condition`,
  `ON_CONDITION`, its condition after `describe`, what it names or pays, a purchase by its property)
  in a column as wide as the detail of the timeline on a desktop (`DETAIL`), the type in words, the
  file (`set in`) and `left out by` (before the wide column); on a phone it grows with its rows
  (`height="content"`).
- `leave_out`: a toggle `Leave out <id> (2 events)` per id (`_named`: `1 phase and 1 event`), its
  help lists the phases and events of the parents with it (`_items`, `_said`); an event without an
  id has none. In the Events tab (`stale`) also an id that the file drops and no item of the parents
  has: it keeps the file from loading. `Save what to leave out` (`forms.save` with a `Grid`,
  `primary` off: a primary button beside the Save of the header read as a second save model) writes
  `drop`: the order kept, new ids last, the key removed when empty. The guard lists `leave out car
  (2 events) no → yes`. Save conflicts: `save.base` on `RowFile(…, ("drop",))`; a change of the
  drops elsewhere while a toggle differs warns, keeps Save off and offers `Discard my edits`, and
  `_drop_check` refuses inside the write. A drop also ends the `shift` and `events` overrides of the
  files above for its id; one of this file that names it does not load, and the save says so.
- One Save per part, not per tab or page: each grid is an `edit_table` with its own base and Save,
  the repayments name rows of another list, and the drops merge into a list of names.
- Words (rule `i18n`): the constants hold English marked `N_` (`TITLES`, `HEADERS`, `LABELS`,
  `HELPS`, `PLAIN`, `EITHER`), said where they show; `INLINE` names a type inside a sentence (the
  help of a `leave_out` toggle; lowercase in English). `read_only` heads the read-only tables of
  phases and events (the inherited events, the timeline, the inherited rows of the Overrides tab),
  `either` says the condition of a sale, `LABELS` also the headings of nested models that no field
  names (`Property`, `Stream factor`). The factor of a phase is labeled in the language of the
  session with the label as written. `Add` is `forms.Form.button`. The grid of the repayments notes
  its editor (`gridstate.drawn`): a switch of the language keeps its edits.
