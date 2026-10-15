---
paths:
  - "src/dagobert/problems.py"
---

# Problems of the inputs

The loader, which raises them, and where a check across the inputs names its file: rule
`persistence`.

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
