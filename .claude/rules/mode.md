---
paths:
  - "src/dagobert/ui/{mode,features}.py"
  - "tests/test_mode.py"
---

# Simple and advanced mode, features

The owner (2026-10-14): a simple and an advanced mode, and switches that turn off unused parts, to
make the setup more accessible. The mode is a habit of the viewer, per browser; a feature a fact of
the plan, in `app.yaml`. What the inputs use always shows. The manual: `docs/manual/index.md` (the
section on the mode and the features) and `features.md`.

## The predicate

- `mode.shown(item, uses, off, advanced)`: `item in uses or (feature(item) not in off and
  (advanced or core(item)))`, a pure function. An `Item` is a `Sort` (page by its English title,
  asset kind, stream kind, event type, key path of the assumptions with `*` for any entry of a
  mapping, grid column by table `assets` or `streams`, option of a select column, Explorer group
  by id, `DATA`: `records`, `actuals`, `trades`, `series`) and a key. `pages(uses, off,
  advanced)` gives the titles of `PAGES` that the navigation registers.
- Core: `CORE` lists the pages (all but Snapshot, Spend and Data), kinds (cash, fixed income,
  equity, bAV), stream kinds (expense, salary, pension, other income, savings), event types
  (`lump_sum`, `end_streams`, `set_stream`, `add_stream`; `sell` shows while a property, gold or
  crypto asset exists: `Uses` counts it used then, `SELLABLE`) and Explorer groups (all spending, by
  category, salary, savings, events, markets). A key path or a column is core unless `EXPERT` lists
  it or a path above it: a new field shows until a line hides it. A `DATA` item is never core.
  `EXPERT` holds the whole `Rules` tab of the Assumptions page, `disability` too: `starter` shows no
  `Rules` tab in simple mode.
- `head(path)`: the item by which a field of a form shows, its key path up to the deepest path of
  `EXPERT` or of a feature above it (`care` of `care.duration.stdev`, `spending.vpw` of its
  fields): a section or a nested model that the inputs use shows whole, and a field below it that
  a feature hides by its own path follows that path (rules `assumptions`, `forms`).
- `FEATURES`: per `model.plan.Feature` a `Spec` (the toggle `label`, its `help` of what it hides,
  the `inline` name in the context `inline`, one msgid per use, rule `i18n`; `hides`, the items).
  `feature(item)` is the feature whose `hides` hold the item, a key path also below one (`care`
  hides `care.cost`); none counts as on. `deductions` hides `deduct`, not `deductible`: the share
  of a PKV premium that the tax takes is no deduction of the feature (a PKV member needs it).
  `option(grid, column, value)`: the item of an option of a select, the `kind` of a stream its
  stream kind. `disability` hides the section `disability` and the stream kind `bu` (no slider:
  the Explorer has none); `spending_rules` holds `spending.vpw` (rule `spending`). A line for
  an item of another unit comes with that unit: `test_every_listed_item_exists` holds every item
  to the app (a key path to a field of `Assumptions` or the column of a mapping, a column to a
  field of the asset or stream models, a type to `events.TYPES`, a group to `sliders.GROUPS`).
- `Uses` (`mode.uses`): what the raw inputs use (`references.read`, `raw_scenarios`: a file that
  does not load still counts), `st.cache_data` by `stamp` (`ui.data_stamp` and the mtimes of
  `history.csv`, `actuals.csv` and the folders `prices/`, `scenarios/`, `series/`: a Spend quick add
  changes no YAML). The items: every key path of `assumptions.yaml` and of the `overrides` of any
  scenario but `shift`, `events` and `assets`, with every path above it (an override counts also at
  a default; a key of `assumptions.yaml` at the default of its field, `fields.of`, holds nothing
  that acts: `children: 0`, `relatives: {}`), the asset kinds and every key of an asset row, the
  stream kinds and keys of `cashflows.yaml` and of each `add_stream`, the option of a select column
  that a feature names (`OPTIONS`: `deduct: childcare`), the event types of every scenario file
  (templates too), `property` and `loan` for a `buy_property`, `DATA` with its page (`RECORDED`: a
  row of `history.csv` or `actuals.csv`, counted in bytes, so a file that does not decode counts
  too, an asset with `trades`, a file under `prices/` or `series/`). `where`: per feature the first
  `SHOWN` (3) places as ids (`Source`: the file and the row with why, `coins (gold)`, `buy 2027-03`,
  a key path, or the rows of a CSV; `said` words them at draw time: a cached value holds no words),
  a key below a listed one left out. `overrides(stem)`: the scenario holds `overrides` or `drop`
  (the Overrides tab, rule `scenarios`). `used(feature)`: a place exists. A file that does not parse
  (`InputError`) gives `ALL` (`everything`: every item used, `where` empty): the error screen of
  `main.py` comes with every page.
- `features_off(data_dir)`: the known ids of `features_off` of the raw `app.yaml` (`listed`); a
  file that does not load switches nothing off, an unknown id is an `InputError` of the model
  (`AppSettings`, `Strict`) on the pages that load it.
- `View` (`view(data_dir)`: `uses`, `features_off`, `advanced()`, once per page or tab) holds the
  predicate of a page (`shows`) and its note (`note`). The session facts join at the call: a
  kind or a type whose grid holds unsaved rows (`tables.unsaved`, `events._edited`) or that a link
  opened, `shows(...) or edited`; a field of a form with an edit (`forms.edited`), a tab of the
  Scenarios page with one (`scenario_overrides.unsaved`). The grids, the kinds, the types and the
  Overview: rules `grids`, `tracking`, `cashflows`, `events`, `overview`. The forms: the
  Assumptions page and the Overrides tab (rules `assumptions`, `scenario-overrides`, `forms`),
  `General` and the Overrides tab of the Scenarios page (rule `scenarios`). The Explorer (rule
  `explorer`): `explorer.View` and `drawn`, a moved slider by `Knob.moved` and `Switch.moved`. A
  quick start switches off every feature, `starter` the ten that it does not use (rule `examples`).

- `main.py` computes `mode.uses` from the raw inputs before `datadir.open` migrates them, so the
  pages of an old schema show by its old keys on the first run. A grid with unsaved edits keeps its
  `Base.hidden` until the save: a feature switched elsewhere changes its columns after it.

## The mode

- `mode.advanced()`: `?mode=simple|advanced` (tests and links; popped, so the switch can change
  it), the state of the switch (`MODE`, `ui-mode`), the cookie `dagobert-mode` (`MODE_COOKIE`, of
  the first request), else advanced: every viewer and every `AppTest` keeps what the app showed
  before the mode. A plan started on the start page sets simple (`welcome._start`, rule
  `examples`). `main.py` and a page call it once per run.
- `mode.mode_switch`: a segmented control `Simple · Advanced` (ids, words by `format_func`,
  label `Mode` with `:material/tune:`, its help `MODE_HELP`) at the end of the sidebar above the
  language switch, drawn by `main.py` in its `finally`, so also on the start page and beside `The
  inputs do not load`. `ui.chose` (its `on_change`, shared with the language switch) carries the
  grid edits (`gridstate.carry`) and notes the choice; `ui.remember` writes the cookie in every run
  after it (`SET_COOKIE`, 400 days).
- The note of a page that hides something: `hidden_text(expert, off, phone, held)` (pure) and
  `hidden_note` draw `Hidden in simple mode (at their defaults): … Switch to Advanced in the sidebar
  to change them.` (on a phone `in the menu`; `held` is a `Held`: `DEFAULTS`; `INHERITED`
  `(inherited from the files it extends)` of an override, an unset one takes its parent's value;
  `VALUES` `(at the values as saved)` of the Explorer; `KINDS`, kinds and types, `Hidden in simple
  mode: … to use them.`, `HIDDEN`) and `Off in Features: … Turn them on there to use them.`, each
  only while it names something, the names by `babel.lists.format_list`, those of features by
  `said`, set apart by semicolons (`children; inheritance and gifts`: a name holds an `and`), a long
  one folded on a phone (`ui.note`, labelled `HIDDEN_LABEL`, `Hidden in simple mode`), and
  `ui.page_link` to the Features page after the second. `View.note` splits the hidden items of a
  page by what hides them; the Assets page (the kinds, `securities`), the Cashflows page (the stream
  kinds) and the Events tab (the types) end with it.
- `off_note(data_dir)`: the caption of the Overview (rule `overview`) while `app.yaml` switches off
  features that the plan does not use, `Some parts of the app are switched off: …` and the link.

## The Features page

- `ui/features.py`, url `/features`, first in `Setup`, always registered. Title, one sentence
  (`INTRO`), the rest folded (`ui.fold`, `How the switches work`). A toggle per feature in the
  order of `FEATURES`, keyed `features-<id>`, its help what it hides (on a phone a caption below
  instead: the help icon sits in the label of a toggle, and a tap on it flips the switch).
- Locked: a feature that the inputs use (`Uses.used`) draws on and disabled (its widget state
  popped first: one from before the data came would show it off), below it `In use: <places>`;
  where `app.yaml` lists it off nevertheless (a zip, a hand edit) also `Switched off in
  app.yaml, but in use: it shows anyway.`, and its toggle counts as a change on, so the next Save
  drops the id.
- Save: pinned into the header (`tables.save_in_header`), off without a change (`No changes to
  save`), the guard (`guard.review`) lists each change `gold and crypto on → off`
  (`gridcolumns.on_off`, `Change.ratio` off). It writes `store.Edit(APP, {("features_off",):
  [ids] or None})` (the key goes when the list is empty), one revision of `app.yaml` alone
  (`store.write` validates `AppSettings` and loads no scenario), source `Features`, toast
  `Saved app.yaml` (`ui.tell`), then reruns with the switches read anew.
- Conflicts as a form (rule `forms`): `Base` keeps the features off and the `revisions.Seen` of
  the raw `features_off` (the revision taken before the read) in `features-base`. A change on disk
  without a flipped free switch starts anew (`_fresh` pops the base and the toggle states); with
  one a warning (`save.changed_at`), Save off, `Discard my edits`. The write checks again.
- Data safety: a switch never touches the inputs, the page writes `app.yaml` only, a feature in
  use cannot be switched off, and what the inputs use shows whatever the file lists. The engine
  ignores the features: a default acts as before (`teilfreistellung`, the PV surcharge of the
  childless with `children` 0).

## Tests

- `tests/test_mode.py`: `Uses` of `starter` against `engineer` (what the newcomer lacks and holds),
  every feature with items locked on `engineer`, only what acts in use (a default, a PKV
  `deductible`; a lone `update_every` locks `tracking`), `ALL` for a scenario that does not parse,
  the predicate in both modes and with a feature off, `head`, every listed item exists, a required
  field of a section shares its tier, `pages` of an empty plan, the navigation of `main.py`
  (`ui.PAGES`: None for a page left out), the mode by query, switch, cookie and default (a script of
  a few lines), `features_off` against the model, the note, the Features page (the lock, a save of
  `app.yaml` alone, a feature off in use, a change elsewhere), every page (`apps.PAGE`, which holds
  the Features page, and `apps.EXPLORER` through `apps.render`) in simple mode as a desktop and a
  phone, in German without a leak, and with every feature off in both modes; the BU tab with the
  first policy, named in the note until then; data safety: a save in simple mode of one visible cell
  of each grid of Assets and Cashflows on `starter` and `engineer` changes that key of that row
  alone (`loader.flatten`).
- The forms: `tests/test_ui_assumptions.py` (the tabs and the notes of `starter` in simple mode, a
  section in use whole, a feature off in advanced, a save of one visible field of each tab
  changes that key alone while keys at their default stay, a value typed in advanced mode stays
  after the switch, also when the switch comes with it, a `Use` switched on stays whole, the
  column `equity_correlation`), `tests/test_scenario_overrides.py` (the parts) and
  `tests/test_scenarios.py` (the Overrides tab, an override typed in advanced, `Template`).
