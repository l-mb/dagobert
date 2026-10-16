---
paths:
  - "src/dagobert/{problems,origins}.py"
---

# Problems of the inputs

The loader, which raises them, and the checks of a plan across the inputs: rules `persistence`
and `plan`.

- `src/dagobert/problems.py`: `RefusedError` (a `ValueError`: what an import or a write refuses in
  words, a missing column, a row that is gone; the commands catch it and let an error of the code
  raise), `InputError`, one `Problem` per error, sorted: `file:line: key.path: message`. The file
  is relative to the data directory (`scenarios/a.yaml`). The key path follows the location
  through the raw document and leaves out the tag of a discriminated union (a part that is no key
  there, except the field of a `missing` error): `assets[1].trades[0].unit` (`dotted`), not
  `assets.1.equity.trades.0.unit`. The line comes from a second parse with `ruamel.yaml`, only on
  an error. `message`: `extra_forbidden` reads `unknown key`, other errors keep the pydantic
  message, a check of the model without its `Value error, `. A check of one field is a
  `field_validator`, so the problem names it (`returns: needs the class equity`, not the line of
  the file and the whole mapping), and it shows a share in percent (`floor 200% is above cap
  150%`). `InputError` pickles, so it crosses the explorer's process pool. Every reader of a YAML
  input (`loader`, `references.read`, `schema`: `Tree`, `_plain`, `Inputs.yaml`) reads it with
  `read_text` (`decoded` for bytes, also the import preview), a file that is not UTF-8 at the line
  of its first bad byte (`NOT_UTF8`), and parses it with `parsed` (PyYAML) or hands a ruamel.yaml
  error to `syntax`: every `YAMLError`, a control character (`ReaderError`) at its line too.
- `src/dagobert/origins.py`: where an error of `loader.load_plan` lies, one function per case
  (`label`: the name of an input; `source`: its keys with their lines). An override error names the
  source that `deep_merge` takes the value from (`override_sources`, of the `loader.Layer`s of the
  chain), in the order of precedence: the overrides of the explorer (`explorer sliders`, `SLIDERS`,
  no line), then the files of the `extends` chain from the last (`overrides.<path>`). At each depth
  the first source that holds the key path wins, until one holds no mapping there (a list replaces
  the lists below it). An error of the whole assumptions belongs to the first source that overrides
  them (`model.plan.split`). This covers the merged assumptions, the `events` and `assets` overrides
  and their unknown ids and fields, and the shapes of `events`, `shift` and `assets`
  (`loader._shaped`). A check across the inputs (`plan_error`, on the plan as `load_plan` composed
  it, `Composed`: its layers, which keep the index of an event in its file, the overrides of the
  explorer, the `events`, `shift` and `assets` overrides that it applies, its assets, in the order
  of `assets.yaml`: `set_assets` keeps it, so an index of the plan names the row of the file) names
  its file and line: a stream `cashflows.yaml`, an asset `assets.yaml` or the `assets` override that
  sets the field, a name of the assumptions the override that sets it, else `assumptions.yaml`, so
  `loader.problems` lists it once. One at an event (also `Plan._streams_exist`: the names and tags
  of `set_stream` and `end_streams` exist) names the `events` override that sets the field, else the
  file that writes the event, with line and key path; in another file it adds `(for <scenario>,
  whose chain drops <ids>)`. An unknown phase names its use: of a stream `cashflows.yaml`, of a bAV
  policy the `assets` override that sets `phases`, else `assets.yaml`, of a phase change every file
  of the chain that writes it, less its drops (`_phase_changes`: the merged changes are sorted and
  shifted, so their place names no file; `Error.input` holds the name); a missing phase at the start
  the `phases` of the scenario. Tests: `tests/test_loader.py` (rule `persistence`).
