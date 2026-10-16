---
paths:
  - "src/dagobert/__init__.py"
  - "src/dagobert/loader.py"
  - "src/dagobert/model/*.py"
  - "src/dagobert/overrides.py"
  - "src/dagobert/store.py"
  - "tests/test_loader.py"
  - "tests/test_model.py"
  - "tests/test_overrides.py"
  - "tests/test_store.py"
---

# Input model and loading

`docs/manual/configuration.md` describes the input files, and `model/` must match it.

- `src/dagobert/model/`: pydantic input model, a module per input (`assumptions.py` with `taxes.py`,
  `assets.py`, `streams.py`, `events.py`, and `plan.py`: the scenarios, `app.yaml` (`AppSettings`:
  `scenarios`, `features_off`, a list of `Feature`, optional, no migration: rule `mode`), `Plan`) on
  `base.py` (`Strict`, the units, `description`, `named`, `Titled`: an enum whose options read in
  words in the selects, `StreamKind`). A `Month` field normalizes to the first of the month. A list
  or dict default is `Field(default=[])`: ruff (RUF012) sees no `BaseModel` behind `Strict`.
  `months.py`: `months_between` and `add_months` are the month arithmetic for every module. `named`
  gives a key of the inputs as a label (`bav_return` reads `bAV return`, `ACRONYMS`): the sliders of
  the explorer, the anatomy, a field that no page names (`fields.Field.label`). `Loan.step` is the
  one amortization rule: the engine uses it each month, `Loan.balance_at` gives the Snapshot
  estimate from `asof`, `Loan.opening` the engine's balance at the start (an earlier `asof` rolls
  forward) and switches to `refinance_rate` after `fixed_until` as well; `Loan.fixed_at` is the one
  test of the fixed rate, for `step` and the `prepayment_penalty` (no `fixed_until`: the whole term;
  §489 Abs. 1 Nr. 2 BGB: rule `engine`). `HoldingsAsset.securities` is what its trades may name: an
  ISIN, for `LotAsset` (gold, crypto) also a symbol (`SECURITY`). A check across the inputs reads
  values, never `model_fields_set`: `loader.adjust` and `set_assets` revalidate an item from a full
  dump, which sets every field (`SellEvent.misfits`: the `foreign` fields, those of a property sale
  on a sale of gold or crypto and `share` on a property, stay at their defaults). `adjust` sets no
  `foreign` field (`loader._takes`, with the ids of the gold and crypto assets), so one `events`
  override reaches a property sale and a gold sale that share an id. A savings plan and a BU policy
  (`Stream` of kind `savings`, `bu`: `streams.NOMINAL`) take null as their default `index`
  (`Stream._nominal_plan`, before validation, so a full dump keeps it); a reader of raw rows takes
  `model.streams.stream_index` (the roll forward). A stream keeps the fields that its kind does not
  take (`streams.TAKES`) at their defaults, by value (`Stream._fits_its_kind`): `amount` beside the
  `gross` of a salary, `health` of an income. Each check of a `Stream` raises a
  `PydanticCustomError` (`streams._refusal`): a type (`kind`, `bonus`, `needs`, `outflow`, …) and
  its context, which the grids say in words (`ui.refusals`, rule `cashflows`), and the English text
  of the problem as before. Every number and date field carries a `Unit` in its
  JSON schema through an alias (`Euros`, `Percent`, `Factor`, `Months`, `Years`, `Number`, `Day`,
  `Month`, `Annotated[int, unit(...)]`; `Shift` for `overrides.shift`): `units` gives them by key
  path (`EACH` for a key or an item, the tag of a discriminated union) and raises for one without, a
  choice (`enum`) aside. `Unit.step`: the finest step shown (cents, 0.001%). Bounds go on the field:
  an alias bound replaces its own (`Factor` carries `ge=0`, which none narrows). The description of
  a field is the one text of its help: the forms show it (with how its unit reads),
  `description(model, path)` gives it to the sliders of the explorer (rule `assumptions`). Every
  event but a sale and an inheritance is a `DatedEvent`, whose `at` is required, a gift too
  (`SellEvent._at_or_when`: `at` or `when`; an inheritance without `at` falls at a death, rule
  `estates`). `BuyPropertyEvent` nests `property` (`BoughtProperty`; the field shadows the builtin
  in the class body, so its methods take `builtins.property`; so does `Stream` with its field
  `property`) and `loan` (`NewLoan`, the fields of a `Loan` with `fixed_for` months, `taken(at)`).
  The checks of a `Plan` across the inputs: rule `plan`. `Assumptions.phases` (required) are the
  phases by name, in the order of the columns and colors: a `PhaseName` (`PHASE_NAME`, a word that
  YAML 1.1 reads as itself, `files.text_only`: `[on]` read as true) to a `PhaseSpec` with its
  `label` (`phase_labels`: the label, else the name; no two show alike). The engine reads no name. A
  use names a defined phase (`Plan._phases_known`, one `unknown_phase` per use at its key path: the
  `phases` and `factor` of a stream and of an `add_stream`, the `phases` of a bAV policy, required,
  `[]` for none, a phase change; `Assumptions._phases_named`: `scale.salary`), and a concrete
  scenario has a phase change at or before `start` (`NO_PHASE`, of the type `missing`, so it names
  `phases`): no fallback, as the order of the definitions is the order of the columns.
  `Plan.phase_at` raises before it, `Scenario.phase_of` takes the first change for a month before it
  (a past month of Spend). `Person.relatives` (rule `estates`): a `RelativeName` (the rules of a
  phase name) to a `Relative` (`label`, `born` before the person's, `sex`, `relation`, a
  `model.taxes.Relation`, `given`: `Given` rows before `start`, `Assumptions._given_before_start`;
  `relative_labels`). The events `InheritanceEvent` and `GiftEvent` (`Acquired`) on
  `AcquisitionEvent`: `givers`, written `from` (an alias, so a dump takes `by_alias` and
  `loader._takes` matches an override by the alias), one name read as a list of one
  (`BeforeValidator`), a gift one giver; `cash`, `equity` (`Securities`); an inheritance without
  `at` (its `_dated` takes none). `Plan` refuses a giver that `person.relatives` lacks
  (`_event_checks`).
- `src/dagobert/loader.py`: YAML loading, `extends` composition, `overrides` merge. `lineage` gives
  each file of an `extends` chain with its own content less what a file below drops (`_without`: the
  items of a `drop` id and, `kept`, its `shift` and `events` overrides above), `written` the same
  with the `shift` and `events` overrides of the chain applied, so an item keeps the file it is
  written in. Drops first, root first (an id that no file above keeps raises at `drop[i]`), then the
  merge of the overrides and `adjust`. `_plan_error` takes `_layers`, which keep the index of an
  event in its file. Every input that does not load raises `problems.InputError` (rule
  `problems`): a file that does not read or parse or is empty, a model error, a missing or
  circular `extends` parent or one with a path (`NO_PATH`; at the line of `extends`), an override.
  An override error names the source that `deep_merge` takes the
  value from, in the order of precedence: the overrides of the explorer (`explorer sliders`, no
  line), then the files of the `extends` chain from the last (`overrides.<path>`). At each depth the
  first source that holds the key path wins, until one holds no mapping there (a list replaces the
  lists below it). An error of the whole assumptions belongs to the first source that overrides
  them. This covers the merged assumptions, the `events` and `assets` overrides and their unknown
  ids and fields, and the shapes of `events`, `shift` and `assets` (`_shaped`). A check across the
  inputs (`Plan`) is an error at the key path of each use (`Plan._references_known`: one `Check` of
  a message and its `known` names per kind, over the streams of the plan and of `add_stream`,
  the assets, the events, `care.index`, `scale` and the `spending` categories; `TWICE`: two streams
  of `cashflows.yaml` of one name and start, an `add_stream` may add a name again). The loader
  names its file and line (`_plan_error`): a stream `cashflows.yaml`, an asset `assets.yaml` or
  the `assets` override that sets the field, a name of the assumptions the override that sets it,
  else `assumptions.yaml`, so `problems` lists it once. One at an event (also `_streams_exist`: the
  names and tags of `set_stream` and `end_streams` exist) names the `events` override that sets
  the field, else the file that writes the event, with line and key path; in another
  file it adds `(for <scenario>, whose chain drops <ids>)`. An unknown phase names its use: of a
  stream `cashflows.yaml`, of a bAV policy the `assets` override that sets `phases`, else
  `assets.yaml`, of a phase change every file of the chain that writes it, less its drops
  (`_phase_changes`: the merged changes are sorted and shifted, so their place names no file;
  `Error.input` holds the name); a missing phase at the start the `phases` of the scenario.
  `overrides.phases` is refused (`_assumptions`, `OWN_PHASES`). `problems` loads `app.yaml`
  (`load_app_settings`, `AppSettings`) and every scenario and gives what does not load, each problem
  once: the validation of `revisions.write`; `check` raises them (an import, rule `transfer`). The
  explorer's overrides lose the `scale.savings` of a plan that the scenario lacks (`_plans_of`); in
  a file such a name is a model error. They lose `spending.vpw` where the `spending` of
  `assumptions.yaml` with the scenario's own overrides has no VPW, and the band (`BAND`: `cut`,
  `trigger`, `increase`, `ceiling`) where it has (rule `spending`), an emptied `spending` whole.
  `chain` gives the raw mappings of an `extends` chain.
  `merged_overrides` merges the overrides of a chain with each other before they merge over the
  assumptions, so a child's mapping over its parent's null merges with `assumptions.yaml` again.
  `flatten` and `nested` turn a mapping into its leaves by key path and back: a list, a null and an
  empty mapping are leaves.
- `src/dagobert/overrides.py`: the overrides of a scenario file for the editor, on raw YAML, so a
  file that does not load still gives its values. `effective` gives each override path (`leaves`:
  down to the field of an item in `events` and `assets`, which a value replaces whole) with its
  value and source (`DEFAULT`, `ASSUMPTIONS`, a scenario stem), merged as `load_plan` merges (less a
  dropped id, `loader.kept`). Defaults come from the model classes (`filled`, also the fallback of a
  form, `ui.fields.fallback`), also in a section that an override switches on, and a scalar of the
  assumptions reads as the model reads it (a month on its first day). `fallback` gives the
  placeholders: per path `effective` after `own` clears that path, the rest of the own overrides
  kept (a null between two mappings of the chain lets the assumptions through again); a path without
  one has nothing to inherit. `own` sets and clears paths in the convention of the store (`None`
  clears, `NULL` writes null): a cleared last key removes its mapping, a value equal to the
  inherited one stays. Its plain dicts are the candidate for the checks only: a dump of them loses
  the comments and the flow style inside `overrides`. The save writes the same changes by key path
  through `store.Edit`, which removes an emptied mapping too. `rows` and `from_rows` give the
  `shift`, `events` and `assets` overrides as rows (`ROWS`) and back; a row with an empty cell goes.
- Elsewhere: the problems of the inputs and the readers of a YAML input (`problems.py`): rule
  `problems`; who refers to what (`references.py`): rule `references`; the schema, its migrations
  and the fixture of a model change: rule `migrations`; `store.py` and its YAML edits: rule `store`;
  the revision store, the one writer of the inputs, and `files.py`: rule `revisions`.
