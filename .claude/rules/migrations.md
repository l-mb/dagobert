---
paths:
  - "src/dagobert/datadir.py"
  - "src/dagobert/schema.py"
  - "tests/test_schema.py"
  - "tests/schemas/**"
---

# Schema and migrations

The input model: rule `persistence`; the writes and the revision store: rule `revisions`.

- `src/dagobert/schema.py`: the schema version of the data directory (`manifest.yaml`) and the
  migrations. `STEPS[n - 1]` migrates schema n to n + 1 on the raw files (`Inputs`: ruamel.yaml
  round-trip documents, which `texts` dumps in the layout of the store, or a text that `set_text`
  replaces, kept as it is; `text` of a file that a step parsed is its dump, with the changes, so a
  later `set_text` keeps them but not the other characters), is named after its target (`to_2`), may
  move a field between files and returns the paths that it changed. `datadir.open` writes them with
  the manifest as one revision under the lock. `current()` is `len(STEPS) + 1`. `migrate` gives the
  changed texts, the manifest last: nothing when the files are current. Files without a manifest
  count as schema 1 (a revision or a zip from before the first manifest, a directory that lost it),
  so every step runs on them: a step changes nothing on the files of a later schema (`to_2` and
  `to_3` find nothing to do, `to_4` stops at its mark), so the manifest alone comes back.
  (`datadir.open` takes a directory with no manifest and no log at all as written by hand in the
  current format; see there. A folder with a log that lost its manifest keeps `revisions/`; its
  inputs without the mark get it from `to_4`, which converts its scenarios that set the growth or
  the inflation.) The other files keep every character. A file that a step cannot parse raises
  `InputError`. A newer schema raises `SchemaError`, which names both versions. `manifest_text`
  writes a new manifest (`Manifest`: `schema`, `app`, `base`) for a migration, the first open and an
  export. A migration keeps the `base` of the old one, which an export and a directory unpacked from
  it carry (rule `transfer`); the manifest of an instance has none. `Tree` reads the files of
  `INPUTS` on access. `migrate_dir` migrates a temporary copy in place, unchecked
  (`revisions.materialize`); `cashplan.plan_at` migrates the texts of a revision in memory.
  `dagobert.__version__` comes from the package metadata.
- The steps: `to_2` renames the `isin` of a trade to `security`, in `assets.yaml` and in the
  `overrides.assets` of every scenario (`_trades`; `_rename` keeps the position of the key and its
  comments). `to_3` makes the phases inputs: `PHASES` (today's four with the labels of a new plan,
  `Work`, `Unemployed`, `Career break`, `Retired`) as text after the `start:` line of
  `assumptions.yaml` (`_START`), so no other character changes (a decision: a round trip reformats a
  flow mapping); `phases: [work]` in a bAV policy of `assets.yaml` without them (the default of
  schema 2, after `contribution`; not in `overrides.assets`: an asset override merges into the whole
  asset, so it holds the phases of `assets.yaml`); and `{from: <month>, phase: work}` once, first in
  the root of the raw chain of each concrete scenario without a phase change in or before the start
  month as its run sees them (`_changes`: less what a file below drops, `loader.drops_below`, moved
  by the merged `shift`, whole months, as `loader.adjust`; the steps keep their own walk of the
  chain, `_chain`, which stops at a missing parent or a cycle). The month is the start or the
  earliest such change of a scenario of that root, so the item sorts before every change, and one in
  the same month wins (the later item): `work` before the first change, as schema 2 ran it, also for
  a sibling with a change of its own before the start (`_work_at`). `to_4` turns the nominal
  `pension_growth` into the growth on top of the index of the pension (rule `engine`): less
  `inflation.mean`, with the comment `REAL`, so the mean path pays as in schema 3 and a path of
  other inflation moves the pension. Always in `assumptions.yaml`, as text (`_PENSION_GROWTH`, the
  line of its value; without one the default of 2% appended, also where it stays 0): its comment
  (`_CONVERTED`) marks a directory of schema 4, so `to_4` returns nothing on one whose
  `assumptions.yaml` holds it, and a scenario written since keeps its real growth. In a scenario
  whose `overrides` set either, with the values of its chain (`_growth`), where the real growth
  differs from what it inherits (an inflation override alone that equals its parent's writes
  nothing). It reads every chain before it writes one: a child read after its parent took the
  parent's real growth as the nominal (fixture: `boost` sorts before its child `burn`). `to_5` drops
  `deductible` of a `fund_policy`, in the events of every scenario and in its `overrides.events` (an
  override left empty goes): a payment into a Basisrente deducts by law, `Plan` refuses one into a
  company pension (rule `deductions`). A policy of `assets.yaml` without `basisrente` that only
  `deductible: true` payments fund becomes one (owner 2026-10-14), with the comment `BASISRENTE`
  before `payout`, other comments kept: `_funded` reads the payments of every scenario file, also a
  template, as its chain merges them (less a `drop`, with the `overrides.events`), so a child's
  override counts. Only where it can be one: an annuity without `contribution` or `conversion` that
  no `severance.bav` funds. A policy that a payment without the flag funds too, and any other,
  stays: the migrated inputs do not load, nothing is written, and the problem names the event and
  the way out (`FUNDING`; `test_to_5_leaves_a_policy_of_mixed_payments_to_the_loader`). Schema 5
  holds no such key: the step changes nothing on it. `to_6`: the engine pays the Kindergeld of a
  child (rule `children`), so every row of `person.children_born` without `kindergeld` gets
  `kindergeld: false`, in `assumptions.yaml` and in the `overrides.person` of every scenario: a plan
  pays as before, by its stream. The mappings down to the list turn block for the comment
  `KINDERGELD` above it, a flow row keeps its style. A file that holds the comment is migrated (a
  directory that lost its manifest changes no more); one written by hand without it gets the flag,
  as `to_4` converts one. The ALG1 rate and the base of the Soli change no file:
  `docs/manual/models.md` says so. A step reads a shape it does not expect as nothing (`_items`,
  `_child`): the loader names that problem after the migration.
- `src/dagobert/datadir.py`: `open` brings a data directory to the current schema. One with no
  manifest and no revisions log at all (`revisions.head` is None, looked at before the lock) is
  written by hand in the current format: it gets the manifest as its first revision after the
  `baseline`, source `manifest <current> (Dagobert <version>)`, and no step. A manifest that another
  write stamps between the look and the lock is kept: the edit under the lock migrates then. Any
  history means Dagobert touched the folder, so the texts of a folder with a log and no manifest, of
  an old revision or of a zip count as schema 1 (a hand-made folder killed in the millisecond
  between the baseline and the manifest of one locked write migrates on its retry). Otherwise one
  `revisions.write` of the migrated inputs and the manifest, source `migrate 1 → 4 (Dagobert
  <version>)` (every scenario must load, else nothing changes; `MIGRATED`, `MANIFESTED` start the
  sources, `opened` tells them: no undo on the Overview). The write records the edits outside
  the app first (`_adopt`; the first open writes the `baseline` of the files as they are, so an old
  revision migrates again). The steps run once, inside the write, and its source (a function,
  `revisions.Writer`) reads the schema there too: a schema that another write stamps between the
  look and the lock counts. Before the lock `open` reads the manifest only (`schema.version`): a
  newer schema (`SchemaError`) or a broken manifest raises before any write, so an older app records
  nothing in the folder. A step that fails on broken inputs (`InputError`) runs under the lock, so
  the edits outside the app are recorded first (`_adopt`); nothing else is written. A directory
  without `assumptions.yaml` raises `InputError` (not a data directory; an empty or missing one
  names `dagobert init`, rule `first-run`, which also holds the starts of `datadir`) and gets
  nothing. A read-only directory (`os.access`) migrates outside the lock to decide and returns
  before `write`, so neither `_recover` nor `_adopt` runs there: it runs as it is while at most the
  manifest would be new (no manifest, no revision, a save refused with `ReadOnlyError`), and one
  that needs a migration raises `InputError`. Every run of the app and the commands `run`, `prices
  import` and `series fetch|import` call it first (`cli._opened`), about 2 ms, so do
  `transfer.export` and `transfer.preview` (a target with inputs). It is the one write-back of a
  migration. `transfer.unpacked` migrates a zip with neither a manifest nor a history as `read`
  does; one with either unpacks as it is, and the open migrates it (rule `transfer`).
- Model changes need a matching update in the YAML inputs, the examples (rule `examples`), tests
  and `docs/manual/configuration.md`.
  A change that existing inputs do not pass needs a migration step (`schema.STEPS`) and a fixture
  `tests/schemas/<n>/` of the old version, which the test migrates and loads
  (`test_schema.py`). The model stays strict: an unknown key is an error after a migration too.
