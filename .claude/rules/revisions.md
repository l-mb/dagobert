---
paths:
  - "src/dagobert/{revisions,files,store}.py"
  - "tests/test_{revisions,store}.py"
---

# Revisions and file writes

The input model, the loader and its problems: rule `persistence`; the YAML edits of the store:
rule `store`.

- `src/dagobert/revisions.py`: the revision store, the one writer of the inputs: `store`, `actuals`,
  `prices.save`, `prices.fetch_series`, `rollforward.apply`, `rename.apply`, `datadir.open`, the
  starts of `datadir` and `transfer.apply` call `write` with a `source`, the page title
  (`ui.source`, `Overview: roll forward`) or the command (`prices import`, `series fetch`, `migrate
  1 → 2 (Dagobert 0.1.0)`, `import x.zip`, `example`, `empty plan` and `quick start` of a first run,
  rule `first-run`). A writer that skips it leaves its change to `_adopt` as `outside the app`
  (`test_revisions.test_every_writer_records_one_revision`; only an import into an empty directory
  moves the revisions of its zip in by a rename, rule `transfer`). The inputs of an earlier day come
  from it (`Records against the plan` of the Overview, `Changes since` of the Cashflows page, the
  comparison of the Flows page; `ui.since`). `revisions/log.csv` (`time,files,removed,source`, paths
  joined by `;`, oldest first, its header written before the first revision) is the commit point: a
  revision directory without its line does not exist for a reader. A line that is no entry raises
  `InputError` with its line. `revisions/<id>/` holds the new content of each changed file at its
  path, `revisions/.lock` the lock. The id is the UTC time, `20261012T140312.123456Z` (`time_of`
  reads it), at least one microsecond after the head; a page shows a time, never the id.
  `is_tracked` takes the patterns of `schema.INPUTS` without dotfiles and `;`, `is_plan` the
  manifest, the plan files and the scenarios.
- `revisions.write(dir, source, edit, *, validate)` runs under `lock` (a `filelock.FileLock` on
  `.lock` per call, so threads and processes take turns; `BusyError`, a `TimeoutError`, after
  `LOCK_WAIT`, 10 s; `ReadOnlyError`, a `PermissionError`, in a read-only directory (`os.access`, on
  Windows always writable: a plain one, `docs/install/windows.md`); a page shows either as `Not
  saved: …`; a write inside a write raises `RuntimeError`), then `_recover`, `_adopt` and `edit()`:
  the new text per path, None removes. `edit` reads what it changes, so it sees the newest content,
  and may raise `ConflictError`. Texts equal to the files drop out, and nothing to write gives None.
  A `source` may be a function (`Writer`), called after `edit` while the files are still the ones
  it read: `datadir.open` names the schema that it migrated from (rule `migrations`).
  `write_returning` takes an `edit` that returns its texts and what it found with them, and returns
  that: the amounts of a Spend month before and after, the `Saved` of a price, the `Roll`.
  Then the revision directory (`.entry` first, the copies, `fsync`), the live files by
  `atomic_write` (a directory that the write makes, such as `prices/`, synced in its parent too),
  when a YAML file changed `loader.problems` before and after (a write is refused
  only for a problem that it adds, by file, key path and message without the line, a renamed file
  under its new path: a file that was broken does not block the fix or the removal of another, nor
  its own; a page shows it as a warning), the log line in one `O_APPEND | O_BINARY` write with
  `fsync` (without `O_BINARY` Windows writes `\r\n`), and `.entry` goes. Any failure up to the log
  line, its own included (a full disk), runs `_recover`. A write of several files (a roll forward, a
  migration with its manifest, a price with the values it records) is one revision. `datadir.open`
  runs a `write` in every run of a page, so `_recover` lists `revisions/` without a `stat` per entry
  and `state` builds paths for its result only: about 2 ms at 2,000 revisions.
- `_recover` cuts a torn last log line and undoes an orphan, a revision directory without a log
  line. The lock allows one, newer than the head: several, an older one or a missing log (a lost log
  or one restored from a backup) raise `InputError` and change no input. With `.entry` the orphan is
  an interrupted `write`: each live file that equals its copy there goes back to the head, a file
  that differs (not written yet, or edited by hand since) stays for `_adopt`. Without it the orphan
  changed nothing: `_adopt` records the live files as they are, and a committed write whose line a
  restored log lacks keeps its files, which `_adopt` then records. `_adopt` records the files that
  differ from the head as `outside the app` (without a log every tracked file as `baseline`; a
  missing copy differs), at the newest modification time of those files, kept between the head and
  now.
- Readers take no lock: `entries` (cached by size and modification time of the log, a torn last line
  ignored), `head`, `last_change`, `changed_after` (whether a revision after one writes or removes
  a path of some patterns: `runs.baseline`), `state(at)` (the copy of each path at or before `at`),
  `materialize` (the plan at `at`, copied into a directory and migrated: the Flows page and `Records
  against the plan` run a scenario there; `cashplan.plan_at` migrates the texts of `state` in memory
  and reads raw rows), `days` (one `Day` per local day of a time zone with a revision of the
  `selected` files, newest first: its last id and its sources, `label` `2026-10-12 · Cashflows ×2,
  Snapshot`), `before` (the last revision before a time with its zone), `named` (the path that a
  file of the head had at a revision, or None when the inputs then do not hold it, as `state` gives
  them: the scenario of `Records against the plan` and of the Flows comparison, also on the days
  before it was removed and added again). A rename is a revision that removes the old path and
  writes the new one, whose source ends with `renaming` (`rename scenarios/a.yaml →
  scenarios/b.yaml`, `Entry.renamed`): `named` follows it back, so the history of a renamed scenario
  stays; a later rename away from a path ends the history of the file that took it. For save
  conflicts a `Seen` keeps the revision and the `digest` of the part that a page shows (`seen`; a
  page that takes `last_change` before it reads builds one itself, so a write between counts as a
  change), and `unchanged` inside `edit` raises `ConflictError` with the revisions since when that
  part changed. The grids (rule `grids`), `Record` of the Snapshot page and the roll forward
  (`rollforward.seen`, every YAML input) use them; the Spend save merges its draft per category
  inside `edit` instead (`actuals.merge`, rule `spend`). A page names a conflict with
  `save.changed_at`: `` `assets.yaml` changed at 14:03 on Snapshot ``, each source at the local time
  of its last revision.
- `files.atomic_write` syncs the temp file before `os.replace`, `files.fsync_dir` a directory, but
  not on Windows (`files.WINDOWS`), which opens no directory. Windows refuses a replace while
  another process holds the file (a reader, a virus scanner): it tries again after `REPLACE_WAITS`.
  The temp file takes the mode of the file it replaces, a new file that of the umask
  (`NEW_MODE`): `mkstemp` makes 0600, and a backup job or a host user beside the container lost
  the inputs after a save. So privacy on a shared machine is a private folder (`chmod 700`, the
  guides of rule `container`), not the mode of a file.
  A text read names `encoding="utf-8"` (rule `tooling`). `files.yaml()` quotes a string that the
  loader (PyYAML, YAML 1.1) would read as something else (`text_only`: `on`, `no`, `null`, `1_000`,
  a date): ruamel.yaml writes YAML 1.2, where they are text, so a stream named `on` came back as
  true. The lock (`flock` on Unix, `LockFileEx` on Windows, which removes `.lock` after it) needs a
  local file system for the data directory.
- `files.read_csv` reads the CSV inputs (`history.read_history`, `actuals.read`,
  `prices.read_prices`): `utf-8-sig` (Excel's `CSV UTF-8` starts with a BOM), the header must name
  the fields, each line holds as many cells as the header, a number reads through `files.finite`
  (`nan` and `inf`, which `float` reads, raise), and a line that does not read raises
  `InputError` with its file and line (`1.234,56` in `history.csv` read silently as 1.234). So a
  page shows it like a YAML problem, and a save that reads the file says it. `loader.problems`
  does not check them: a CSV file fails only what reads it.
