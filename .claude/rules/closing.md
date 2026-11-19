---
paths:
  - "src/dagobert/closing.py"
  - "src/dagobert/ui/closing.py"
  - "tests/test_closing.py"
---

# Closed and opened assets

Owner 2026-11-18: an asset that ended (a term deposit paid out, an account closed) is closed, not
deleted, and money moved into a new account is no loss in the tiles. The records and the tiles:
rule `tracking`; the store: rule `store`; the German: rule `i18n-glossary`.

- Model (`model/assets.py`): `Assets.closed`, a list of `ClosedAsset` (`ended`, a day; `payout`,
  euros; `asset`, the whole row as it was, trades too), optional, so no migration. The key is
  `ended`, not `on`: YAML 1.1 reads `on` as true. `Assets._unique_ids` counts both lists.
  `AssetBase.opened` (a day, optional, every kind): the account held nothing before it.
  `loader.load_assets` gives the open assets only, so the engine, `Plan`, the grids, the Snapshot
  page, `prices` and `references` never see a closed one; `loader.load_closed` gives the others.
  A later migration of asset fields must walk `closed[].asset` too (`schema._trades` reads
  `assets` only): none exists yet.
- `closing.py`: `Close` (asset, `ended`, `payout`; `str`: `close <id>`, the action of its
  source), `check` (ValueError: the asset is gone, `ended` before its `asof`, or another input
  names it, `References.orphans`: a savings plan, a sale, the `finances` of a loan), `apply` (one
  revision, `check` inside the write) and `reopen` (the row back at the end of `assets`, the
  emptied `closed` key gone). Both move the row inside one ruamel document (`store.moved`): the
  comment lines inside the row go with it, those around it stay (`yamlcomments.drop`).
- The payout is a record only: the app moves no money. The user records it where it went, as the
  value of a tracked account or as a new asset with `opened` (`ui.closing.ABOUT`, the manual).
- Records (`history.observations(closed=)`): a closed asset counts with the value of its row at
  `asof` (when before `ended`) and its rows of `history.csv` up to `ended`, then with 0 from that
  day, the last observation of the day; a row after `ended` counts no more.
  `history.actual_values` takes them, and an asset with `opened` does not delay the first month
  (it is known as 0 before its first value). `rename._check` refuses the id of a closed asset.
- Tiles (`summary.change`): an asset first observed after `since` counts from 0 when its `opened`
  lies after `since`, else it stays out (a late entry is no growth, owner 2026-10-13); an asset
  closed by the day counts down from its value at `since` to 0. The Overview groups the recorded
  months with the kinds of the closed assets too (`overview.page`).
- `ui/closing.py`: `button` (`Close`, `Table.beside` of every asset grid, beside `Rename`, off
  while the table holds edits) opens a dialog (it takes the language first, rule `i18n`): the
  asset, `Ended on` (`ended`: the maturity of a deposit that matured, else today, never after
  today), `Paid out €` (a `decimal-` text field read by `fields.euros`, preset with the value on
  that day), the sentence of what the close does or `Refused: …` (English, as an input error),
  and `Close`, which tells `Closed <name>`. `closed` draws the fold `Closed assets (n)` below the
  tabs of the Assets page, none without one: a table (`rows`: asset, kind, ended, last value,
  paid out) and `Reopen` with a select. Widget keys hold no words; the fields of the dialog are
  keyed by table and asset, so another asset starts from its own day and value.
- An asset whose trades sold every unit is worth 0 (rule `prices`: `prices.record`,
  `snapshot.estimate`), so its value no longer stays at the last recorded price.
- Tests: `tests/test_closing.py` (close and reopen with the comments, the refusals, the id that
  stays taken, the records and the tile around an end, `opened`, the day that the dialog offers),
  `test_prices.py` (an asset sold in full). The dialog is checked in a browser (skill
  `app-check`): `AppTest` opens no dialog of a grid toolbar with its state.
