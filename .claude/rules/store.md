---
paths:
  - "src/dagobert/{store,yamlcomments,scenariofiles,textedit}.py"
  - "tests/test_{store,textedit}.py"
---

# The store

- `src/dagobert/store.py`: writes to the YAML inputs with `ruamel.yaml` (comments survive), scenario
  files from the explorer, `app.yaml`. `scenariofiles.concrete_scenarios` leaves out the templates,
  `default_scenarios` holds the concrete ones of `app.yaml`, `scenario_labels` names each by stem,
  the stem added where two share a name (the explorer, the report). `Edit` changes one file in its
  document, `text` gives the new text (`RowFile.text` is one): first `rows` (`RowEdits` by key path
  of the list; a missing list, and a missing mapping on the way, comes with the first row), then
  `values` by key path. `None` clears and removes each mapping or nested list above that holds
  nothing else, up to a list item or the top: a leftover `{}` over a parent's null would switch a
  section on. `NULL` writes null, `Merge` changes some keys of a mapping (the `stream` of an
  `add_stream` row), a missing key or a null on the way becomes a block mapping, another value there
  raises (`NULL` is one object, also through a copy: a widget state is a deep copy). A value equal
  to the old one (a bool is no number) keeps the old node: `0.10` stays, and so do the comments
  inside a list. A new value keeps the flow style of the one it replaces, a new row takes that of
  the row before it, and so does a new mapping of scalars in a mapping (a class of `returns`:
  `_neighbour`; a section stays a block). A missing file starts empty, or from the text of `origin`
  (a copy, a rename), `create` refuses one that exists, `remove` removes it; an edit without values
  or rows keeps the text, also that of `origin`, unless it creates an empty file. `Edit.onto(text)`
  applies it onto a text instead of the file: the roll forward moves a gift onto the texts of its
  scalars (rule `estates`). `write` refuses two edits of one file. The first edit of a file dumps
  it, so its layout changes once (a decision; comments stay); after that an edit changes its own
  lines only. `yamlcomments.settle` moves the comment lines that ruamel.yaml keeps at the end of a
  block list (after flow rows) behind its last item, where the edits look for them. `ruamel.yaml`
  hangs the comment lines below a row on its last scalar or flow list, also inside its trades or a
  block list: an edit moves them to the entry that is last after it (`yamlcomments.move_comment`; a
  new list or mapping becomes a node that can carry them), so a new `asof` goes in above the comment
  of the next row, and an added row goes in above the comment at the end of the list, also the first
  row of a new list. After a flow list it keeps them on the next entry instead. A deleted row, key
  or list leaves the comment lines around it where the lines above it hang (`yamlcomments.drop`):
  behind the entry before it, or above the first item of a list. So the comment of the next row
  stays above that row, and the one above the deleted entry stays too. A nested list that loses all
  its rows goes (a missing list reads as empty): `ruamel.yaml` would write the comment lines inside
  an empty list in front of its `[]`, which does not parse. A top-level list (`assets` and `streams`
  are required) stays as `[]`, with every comment line that it held behind it
  (`yamlcomments.emptied`).
- `src/dagobert/yamlcomments.py`: the comment lines of a round trip (the slots of ruamel.yaml's
  `ca`, its module docstring), which `store` calls.
- `src/dagobert/textedit.py`: `scalars` replaces numbers, dates and texts by key path in several
  files at once, as text at the position that `ruamel.yaml` gives, and leaves the rest of each file
  as it is but its line ends: a CRLF file comes back with LF, as every write of the app (owner,
  2026-10-13; lines split at `\n` only, `_LINES`): a plain text as written (a name holds spaces; one
  over several lines raises), a quoted one or a number or date by `_TOKEN`, which must read back as
  the old value or raises (`ruamel.yaml` places an alias at its anchor); a null without text
  (`founded:`) takes the value behind the colon of its key (`_null`: `ruamel.yaml` places it at what
  follows, and the write replaced the next key); a new text plain where it reads as itself in a
  block and a flow list (`_PLAIN`, `files.text_only`), else in single quotes, also where the old one
  was quoted. `Key` renames the last key of a path (`rename`). `After` adds a key that a mapping
  lacks behind an entry whose value takes one line: on a line of its own in a block mapping, after a
  comma in a flow mapping; its value a scalar or a flow mapping of scalars (the new `tax` of a roll
  forward, rule `rollforward`); `FIRST` puts it in front of the first entry, in its column, or into
  `{}` (which `ruamel.yaml` gives no flow style): a mapping of mappings only. Keys added at one
  place (the two loss pots of a roll) go in in the order of their text, into `{}` with a comma.
- `assets.yaml` and `cashflows.yaml` keep one block mapping per row. `ruamel.yaml` drops
  comments inside flow mappings (`- { ... }`), so do not reintroduce that layout. The store
  writes no anchors: one `asof` date on several rows would otherwise become `&id001`.
- Every writer of the store is one `revisions.write` with a `source` (a required keyword), whose
  load of every scenario refuses inputs that the write breaks and changes nothing: `write` (the
  `Edit`s of several files; `check` runs first inside it, for `revisions.unchanged`; no load when
  only `app.yaml` changes, which `_MODELS` checks with `AppSettings`),
  `RowFile.apply` (`RowFile.text` gives the file after the edits, read inside the write;
  `observed` appends the asset values that the edits set to `history.csv` in the same revision,
  `history.appended`), `act` (a file action) and
  `save_default_scenarios`, an `Edit`.
- `src/dagobert/scenariofiles.py`: the file actions of the scenario files (the Scenarios page, rule
  `scenarios`): `created` (also the explorer's scenario: `{name, extends, overrides}`; one of its
  own in the first phase of `assumptions.yaml` from `start`, as a run needs a phase there), `copied`
  (the text with its comments and parent, a new `name`), `renamed` (`origin` and `remove`: the text
  as it is; each `extends` and entry of `app.yaml` that names it, `references.orphans`, item by
  item, so the comments of the list stay) and `removed` (with its entries of `app.yaml`, from the
  last) give the `Edit`s from the files now, or raise ValueError with the reason: a new stem that is
  no file name (`_SCENARIO_NAME`; also a device name of Windows, `ntpath.isreserved`: `con`,
  `aux.x`, on every system, as an export moves between them), that YAML reads as a value
  (`files.text_only`: `extends: on` is true) or that exists in any case (`casefold`: a file system
  may not tell `Plan` from `plan`), a `name` that another scenario has (the results carry it), a
  scenario that is gone (`_held`: copied, renamed or deleted elsewhere), a delete while a scenario
  extends it (named) or of the last scenario that runs (raw `abstract`, so a file that does not load
  counts). The page names a rename in the source (`revisions.renaming`), so the history follows it.
  `lost_job(dir, JobLoss)` (`Add a job loss`, rule `scenarios`): a new file that extends the main
  one with the change to the phase of unemployment (`_idle`: the first phase of an ALG1 stream,
  else `unemployed`, else that phase added to `assumptions.yaml` with the label of the page) and,
  with a new job, back to the phase that the main one has then (`_phase_at`, `loader.written`), ids
  `job-loss`, `new-job` numbered where the chain holds them; an ALG1 stream in that phase where
  none exists (no amount: the engine takes the salary before); each salary without phases limited
  to the others while no scenario file runs that phase (a limit then changes no scenario), so it
  stops; `job_loss` out of `features_off`. A loss before `start`, a new job not after it or in a
  month where the main one is unemployed or has no phase raises.
  `listed` gives the edits that a page shows and the `Seen` of each file that they change (the
  revision before the text); `act` writes them as one revision and, inside the write, refuses a file
  changed since (`ConflictError`) and edits other than those now (`the inputs changed since the
  list`: a new child). `raw_scenarios` (raw mappings by stem, `references.read`), `parents` (the
  stems a scenario may extend: not itself, not a descendant) and `children` serve the page.
- Rows by name, not by index: `keyed` names a row by the values of some fields and its place
  among the rows with those values (`Table.identity`: the asset `id`, `(name, start)` of a stream,
  `(date, kind, security)` of a trade; no fields: its place). `RowEdits.between(a, b, key)` gives
  the edits from `a` to `b` (a changed field, `NULL` for a null, None for a field that `b` lacks;
  a new order is no edit; `result(a)` holds the rows of `b`), the difference that a grid shows.
  `RowEdits.onto(a, b, key)` moves edits of `a` onto `b` by name. `RowFile.apply(read=Read(rows,
  holder, revision, key))` takes edits of the rows that a page read (`RowFile.contents`: the rows
  and the other fields of the mapping that holds them): inside the write `RowFile.moved` calls
  `revisions.unchanged` on the rows that they change or remove and on the fields of the holder
  that `RowEdits.parent` sets (a `Seen` of the `revision` before the read and the digest of
  those), so a row or such a field changed since raises `ConflictError` (the `cost_basis` that a
  first buy clears; a value that a price records on the depot is no conflict), and moves the rest
  onto the rows now: what changed in other rows stays, also a new row before.
  `RowFile.apply(seen=…)` instead refuses any change of the rows since a `Seen` of all of them
  (`revisions.unchanged` on `rows()` inside the write): new rows that were checked against every
  row, the trade import (rule `tracking`).
  A key path step `Where(key, value)` names an item by a value, found at each read and write
  (`_found`; `RowFile.child(row_id, key)`: the trades of an asset by its id); none raises
  `problems.RefusedError`, `assets holds no row with id … any more`. A hand edit that holds another
  value where an edit needs a mapping or a list (`trades: 5`, also where rows go) raises it too,
  with the file and the line of the value (`_MisfitError`, from `RowFile.contents` and
  `Edit.onto`), so does a top level that is no mapping (`_document`): `Not imported:`, no
  traceback.
- A dump of `ruamel.yaml` rewrites the flow mappings of `assumptions.yaml` and the scenario
  files: `{ a: b }` becomes `{a: b}`, and a flow mapping over several lines becomes one line.
  So a write that changes only numbers or dates there (the roll forward, a rename) takes the
  texts of `textedit.scalars` inside its own `revisions.write`, which keep every other character.
