---
paths:
  - "src/dagobert/transfer.py"
  - "src/dagobert/ui/transfer.py"
  - "tests/test_transfer.py"
---

# Export and import

The revision store: rule `revisions`. The manifest and the migrations: rule `migrations`.

- `src/dagobert/transfer.py`: the export zip of a data directory and its import. Local
  work runs on an export unpacked outside the checkout (`dagobert app --data x.zip`), whose own
  export goes back into the instance by `import`.
- `uv run dagobert export [--data DIR] [--revisions] [--out FILE|DIR]` writes
  `dagobert-<revision>.zip` (`--out` a directory, default the current one) through
  `atomic_write`. `transfer.export` opens the directory (`datadir.open`) and takes `state(head)`:
  the copies never change, so the files belong together; a read-only directory gives its live
  files. The entries sit at the root, so `unzip -d x` gives a data directory: the inputs
  (`is_tracked`, `prices/` included), a new manifest (`schema.manifest_text`) whose `base` is the
  head, or the `base` of the directory's own manifest (an unpacked export keeps the revision it
  started from), and with `--revisions` `revisions/log.csv` up to the head and the copies that it
  names. Never `series/`, `out/`, `.cache/` (the results kept on disk, rule `explorer-runs`),
  `.lock`, `.entry`, an orphan or an untracked file.
  `Export.zip` refuses more than `LIMIT` (64 MB) unpacked (`Export.check`, of `Export.size`): the
  import would refuse it. A message rounds a size up (`megabytes`): never `64 MB, more than 64 MB`.
- `transfer.read` takes a path or an upload (`IO[bytes]`) and refuses before a byte unpacks
  (`ArchiveError`, one line per entry): a path outside the data directory (absolute, `..`, `.`,
  `//`, a backslash, a drive letter), a symbolic link (`external_attr`), a name twice, a file that
  no data directory holds (an input, `revisions/log.csv`, `revisions/<id>/<input>`; so a `.cache/`
  entry: a pickle runs code, an import brings no results), more than
  `LIMIT` unpacked. `zipfile` stops at the declared size, so the sizes bound what it reads (no ratio
  check: it refused a uniform CSV). `LIMIT` is low because the import holds the zip, its files and
  their text in memory, an upload and the page too, beside the runs of the Explorer (`mem_limit`,
  rule `container`); real data takes well under 1 MB. Then: a damaged entry (`zlib.error`,
  `BadZipFile`), no UTF-8, no `assumptions.yaml`, a newer schema (`SchemaError`); it migrates in
  memory and loads every scenario in a temporary directory (`loader.check`, `InputError`), and the
  revisions must hold a log whose ids rise and name inputs, with each copy that it names and no
  other. `Archive.written` keeps the manifest of the zip as it is, `Archive.migration` says an older
  schema in words (the versions, the Dagobert of the zip, the files that the migration changes), a
  note of the preview.
- `transfer.preview(dir, zip)` opens a target with inputs (`datadir.open`) and compares per file,
  the manifest aside (a target keeps its own; a new one gets `manifest_text()` without `base`),
  each side as text without a newline translation. With the `base` in the log of the target, each
  `Change` holds the file at the base (`state(base)`, migrated like the zip, so a migration since
  on either side is no change), here and in the zip: changed on one side takes that side
  (`default`). The import asks keep or take (`default` None, `Preview.undecided`) for a file
  changed on both sides (`conflict`), for a file that it would remove (a file goes only on an
  explicit take) and, without the base in the log (another instance or history, also an instance
  made by a plain import, whose log holds only the import), for every file that differs: the files
  here stand for the base then, and `notes` warns (`STRANGER`). An empty target takes every file of
  the zip. `Change.sides` gives the differences of an asked file (`Side`: from, to, old, new,
  `unified`): at a conflict of each side against the base and then of the zip against the file
  here, which names what a take drops here; else the last one only. `Preview.unchanged` counts the
  inputs that both hold alike.
  `here`, `there`: `added`, `removed`, `changed` or empty; `action`: `add`, `remove`, `replace` or
  `keep`. The revisions of a zip are ignored in a target with inputs (a note says so): two
  histories cannot interleave.
- `transfer.apply(dir, preview, choices)` writes one revision `import <zip name>` with the files
  that their `Choice` (`KEEP`, `TAKE`) or default takes; an undecided file without a choice or a
  choice of a file without a change raises ValueError (`Preview.texts`). Its `edit` refuses with
  `StaleError` when the head moved since the preview (an edit outside the app too, which `_adopt`
  records first): preview again. Kept and taken files that do not load together raise `InputError`
  and change nothing (`revisions.write`). An empty target (`datadir.empty`: no input, no revision,
  or missing) takes the revisions of the zip (`_take_history`): staged in a dot directory inside the
  target (its parent may be read-only or another file system, a volume), the live files of their
  head first, then `revisions/` by one rename, so an interruption leaves inputs without a history,
  which the next open records as the baseline; a `revisions/` there without a log refuses. Then
  `datadir.open` (a migration) and the revision of the import, usually none.
- `uv run dagobert import ZIP [--data DIR] [--keep PATH ...] [--take PATH ...] [--keep-all |
  --take-all] [--yes]` prints the notes, the table (file, here, in the zip, action) and per asked
  file a unified diff (`Change.sides`, none for a removal), stops with exit code 1 while a file
  has no choice, asks unless `--yes`. `--keep-all` or `--take-all` decides every asked file that
  `--keep` and `--take` leave. A row-level merge is later work.
- `dagobert run --data x.zip` reads the inputs, migrated, from a temporary directory
  (`transfer.temporary`), writes nothing back and names a scenario by its file name (`plan.yaml`).
  `dagobert app --data x.zip` unpacks into `x/` beside the zip (`transfer.unpacked`, through a
  temporary directory and a rename) and serves it (`datadir.open`): a zip with a manifest or a
  history unpacks as it is, and the open migrates it as a `migrate` revision; one with neither
  unpacks migrated (only the baseline, no `migrate` revision). An existing `x/` serves only when its
  manifest holds the `base` of the zip, else `ArchiveError`. The app then keeps its results in
  memory only (`DAGOBERT_CACHE=memory`, rule `explorer-runs`): the copy gets no `.cache/`. An
  import keeps the `.cache/` of its target. `cli.PROBLEMS` end a command with their lines, exit 1.
- Upload: `transfer.UPLOAD_MB` (`LIMIT` in MB) is `server.maxUploadSize` of the app (rule
  `container`), which the server enforces whatever the uploader says; every export fits.
- `src/dagobert/ui/transfer.py`: the page `Export and import` (`Setup`, `/transfer`; at the end of
  the Data page it sat 3,200 px down in portrait), its guide `docs/manual/transfer.md`. Its intro
  names no command; `Export` and `Import` are bold labels as on the other pages of `Setup`. Export:
  the toggle `Include change history` (the revisions) with the size of `Export.copies`, and
  `st.download_button` with a callable that builds `Export.zip` on the click (`on_click="ignore"`),
  a caption with the time of the last save in the browser's time zone (`stamp`, `12 Oct 2026,
  21:33`, `12. Okt. 2026, 21:33`: `babel.dates.format_datetime` with a translated pattern, from
  `revisions.time_of`: the id read as a raw timestamp) and the file name. `Export.check`
  runs first: Streamlit drops the exception of a callable, the browser shows only `Failed to
  generate file`. Import (`import_zip`, also on the start page of an empty data directory, rule
  `first-run`): `st.file_uploader(_(UPLOADER), type="zip", max_upload_size=UPLOAD_MB)`, `Choose a
  Dagobert export (.zip)`, under a nonce (`UPLOAD`: a done
  import empties it), a caption with the limit below it (Streamlit names a refused upload in a
  tooltip only, none on a phone). The preview sits in session state with the id of the upload
  (`HELD`): one archive per session, replaced by another upload, dropped without one and after the
  import, made again when the head moved since (a save here or on another device), and then
  without choices (their keys hold the head). A zip that holds the files here gives an info with
  their count (`Nothing to import: the 16 files of the zip are the same as here.`). The notes
  (`STRANGER` a warning), the caption `Since the export of <stamp>:`, the table (`rows`:
  file, here, zip, action, `keep or take?` without a choice; without the base `here` holds the
  file here against the zip: `not here`, `only here`, `differs`) in `table-transfer`, whose file
  names wrap after a slash in portrait (`WRAP`, a zero-width space, and a rule of `page.css`), so
  the action fits; the count of the unchanged files, `ui.note(READING)`, a segmented control
  `Every file in the zip` with more than one asked file that the zip holds (it shows the choice
  that they share, its `on_change` sets them; a removal takes a choice of its own, so one tap
  removes no file) and per asked file a bordered box: why it asks (`why`), its segmented control,
  an expander `Difference` per `Change.sides`. `difference` gives a row file (`ROW_FILES`:
  `assets.yaml` by the asset `id`, `cashflows.yaml` by `name` and `start`, the identities of the
  grids; the `trades` of an asset row by row too, `NESTED` by `assets.TRADE_IDENTITY`: the guard
  shows a list of rows as their count, so an edited trade showed nothing) through
  `RowEdits.between` and `guard.changes`, a CSV input by every column but the last (`(month,
  category)`, `(date, asset)`, the date of a price; `value` and `amount` in euros), both through
  `guard.listing`; else, and where no row differs or a file does not parse, the unified diff
  (`st.code(language="diff")`). The first `LINES` (40) show. Above `Import` a warning names the
  files that it removes (`removals`), and the count (`effect`: `1 added, 2 replaced, 9
  unchanged`); `Import N files` (primary; N the files that it adds, replaces or removes) is off
  while a file lacks a choice or nothing changes.
  `StaleError` previews again with a warning, `InputError` shows its lines, `OSError` and
  `ValueError` `Not imported:`; a done import shows its time (`stamp`) and the count, or with
  `then` goes to that page of the navigation (`PAGES`; the start page: the Overview), which says
  them in a toast (`ui.tell`).
- The page speaks the language of the session (rule `i18n`): `rows` heads its table and says the
  words of a `Change` (`SAID`: `changed`, `replace`) in it, so do `effect` and `why`; the
  `Import` button takes `pgettext("button", …)`, as German tells the verb from the label.
  `Preview.notes` and `Archive.migration` say their sentences with `_()` in `transfer.py`: the
  CLI runs in English.
