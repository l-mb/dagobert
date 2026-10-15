---
paths:
  - "src/dagobert/references.py"
  - "src/dagobert/rename.py"
  - "src/dagobert/ui/rename.py"
  - "tests/test_references.py"
  - "tests/test_rename.py"
---

# References

The inputs that it reads and their model: rule `persistence`; their writes: rule `revisions`.

- `src/dagobert/references.py`: who refers to what across the inputs, for the options of the editors
  and the users that they name when they refuse a delete or a rename. `of` reads the raw YAML into
  `References`: per `Kind` where each name is defined and every use of it, as a `Site` (file, key
  path, label of what holds it; `sort`: the kind of a defined asset or stream; `key`: the name is
  the last key of the path, a step `KEY`, not the value there). Kinds: asset id (also `into` of a
  savings plan, `property` of a stream and `finances` of a loan: a let property), stream name (also
  `scale.savings`), tag (of a stream: `end_streams` and the tags of a property use it, a sale ends
  the streams that share one), category (of an expense stream without `health` and `property`, as
  `scale` and the age curve take it, `Stream.managed`), phase (defined by the keys of `phases` in
  `assumptions.yaml` only, `PHASE_DEFINE`, so it counts in every scenario; used by the `phases` and
  `factor` keys of a stream, also of an `add_stream`, the `phases` of a bAV policy, also in
  `overrides.assets`, the `phase` of a phase change, `CHANGE_USE`, and the keys of `scale.salary`),
  relative (defined by the keys of `person.relatives`, `SETTINGS_DEFINE`, also in the overrides of a
  scenario; used by `from` of an inheritance or a gift, one name or a list), index, return class,
  item id (of a phase change or an event, `CHANGE_DEFINE`, for `overrides.shift`), event id (for
  `overrides.events`, which needs an event), scenario stem. A file that does not load counts as
  written, an empty one or one without a mapping as empty, one that does not parse raises
  `InputError` (`read`, one input: the store and the Scenarios page use it too). A name defined
  outside the scenario files, and a scenario stem, counts everywhere; one that a scenario file
  defines (an item id, an `add_stream`, an index or a return class of its overrides) counts there
  and in the files that extend it (`chain`), until one drops its item (`Site.item`). `names` gives
  the options sorted without regard to case, by `sorts` too, `orphans` the uses that no definition
  reaches once a file or the part below a key path goes (the Assumptions page keeps a used phase by
  it). A `drop` uses an item of the parents (`names(Kind.ITEM, <parent>)`). A `buy_property` defines
  its property and its loan (`_Walk.bought`, sorts `property` and `loan`) like an `add_stream` its
  stream. An asset without `growth` uses the default class of its kind. A field of
  `overrides.events` names what that field of an event names.
- `phases(dir)`: the phases of `assumptions.yaml` in the order of the file, each with how the pages
  name it (its `label`, else its name), from the raw file: the columns and selects of the grids and
  forms that a file which does not load still draws. `relatives(dir)` the same of
  `person.relatives`.

## Rename

- `src/dagobert/rename.py`: a rename of an asset id, a stream name, a phase or a relative name
  (`KINDS`, the names that the grids keep) in every input that names it. `texts` rewrites each site
  of `defined` and `used` of the old name (all rows of a stream, a `buy_property` id, an
  `add_stream` name, a key such as `factor: {work: 1}` or `overrides.assets.<id>`) through
  `textedit.scalars` with `textedit.Key` for a key, so every other character stays (no dump: the
  flow mappings of the scenarios), and for an asset its rows of `history.csv` (`history.renamed`,
  cell exact, quoted as CSV needs: an id may hold `,` or `"`). `actuals.csv` keys by category,
  trades and `prices/` by security, `tax.self_employed` names nothing: none changes. Refused
  (`_check`, ValueError): another kind (a tag), a name that is gone, the old name, spaces at its
  ends or more lines, no phase name (`model.assumptions. phase_name`, of a relative
  `relative_name`), a name in use in any case (defined, only used: it would bind the dangling uses,
  or in `history.csv`: a removed asset's values would join). Asset ids and stream names take what
  the model takes: no slug rule. `preview` gives the texts before and after, the changed `lines` (a
  rename keeps the line count) and a `Seen` per file; `apply` writes them as one revision inside
  which a file changed since raises `ConflictError` and other texts now (a new use elsewhere) refuse
  it (`the inputs changed since the list`). The source ends `<kind> <old> → <new>` (`Assets: asset
  flat → home`), never `rename a → b`, which names a renamed file (`revisions.renaming`). The run
  stays the same (`test_rename`), but Monte Carlo draws the price of a sale with `price_stdev` by
  the asset id (`sale.<asset>`, rule `engine`): another id draws other prices, and the month of
  death of a relative by its name (`inheritance.<relative>`). The revisions before keep the old
  name: `Changes since` and the Flows comparison show it as removed and added.
- `src/dagobert/ui/rename.py`: `button` (`Rename`, off while its table holds edits, `HELD`) opens a
  dialog: a select of the names of the table, `New name` (`nocaps-` but for a stream; both keyed by
  the table: the state of another table held a name not among these), the lines of `preview` through
  the save guard (`listing`: `file:line` old → new, `SHOWN` per file, then their number) or
  `Refused: …`, and `Rename`, which writes what the run before listed for the same names (`LISTED`,
  `save.listed`; `Not saved: … since this list`), off while the preview now refuses. It tells
  `Renamed the asset a to b` (`ui.tell`) and the selection of the securities tab follows (`FOLLOW`).
  The grids of `tables.edit_table` with `Table.rename` (the Assets tables, the stream tables, the
  purchases of the Events tab) draw it in the row of `All columns`, its kind the names of the
  `locked` columns (both ids of a purchase); the Assumptions page below the phases (rule
  `assumptions`). Its words per kind (`ABOUT`, `KINDS`, `HELPS`, `RENAMED`: one sentence each, rule
  `i18n`); the dialog takes its title per call and the language of the session first, as it reruns
  alone.
