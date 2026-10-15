# Model and loader: small cleanups

Low findings of the reviewer read of 2026-10-13 (model, loader, schema, datadir). None changes a
result today. Each is a small change of its own.

- `model/assumptions.py`: `interpolate` writes `np.interp` (linear between the points, flat outside)
  by hand. `share_at` builds new `AgePoint` models on every call, once per month in the engine, and
  `engine.core._age_factors` loops in Python over the months. Use `np.interp` on the ages and
  values, sorted once, and pass all ages at once. A `care.hazard` point keeps a yearly probability
  under the key `factor`: a rename to `chance` needs a migration.
- `loader.py`: `_plan_error` is a router of about 60 lines with six cases, and it reads the
  `extends` chain again. Move the error sourcing (`_plan_error`, `_phase_changes`,
  `_override_sources`, `_source`) into a module of its own, one function per case, and pass the
  layers that `load_plan` has. The chain and its `drop` are walked in four places (`loader._layers`
  and `kept`, `overrides._read`, `references._reaches`, `schema._changes`) with slightly different
  rules for a missing parent or a cycle: one pure function for the chain and one for the drops.
  The migration steps keep their own copies.
- `model/events.py` `Shift` is `dict[str, Months]`, a float, and `loader.adjust` and
  `schema._changes` apply `round()`, which rounds a half to even (2.5 moves 2 months, 3.5 moves 4).
  Type it as whole months, so a fraction is refused, and drop the `round()` calls.
- `datadir.open` runs the whole migration outside the lock only to decide the read-only case, then
  again inside `revisions.write`, and reads the version for the source outside the lock too.
  Migrate outside only when the directory is read-only, and read the version inside `edit`.
- `loader.written` calls `adjust` without the gold and crypto ids, so every sale takes the fields
  of a property sale: an override of `share` or `price` can differ from the run (documented in
  its docstring only). Pass the ids from `assets.yaml`.

Needs: nothing.
