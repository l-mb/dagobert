---
paths:
  - "src/dagobert/ui/{guard,save,tables,assets,snapshot,cashflows,spend,pricing,forms,formguard}.py"
  - "src/dagobert/ui/{tradeimport,tradeform,rename}.py"
  - "tests/test_ui_guard.py"
---

# Save guard

- Every save of the inputs passes the save guard (`ui/guard.py`). A number cell reads `,` and `.` by
  the browser language (`-20,50` becomes -2.050 in English, `131.500` becomes 131,5 in German), and
  a grid shows whole euros, so the guard lists what a save writes: each changed cell old to new,
  money with cents, the numbers of a new row and the cells that its table makes (`Table.made`, of
  `Table.derived`: the ids of a purchase, which the grid does not show before the save), the removed
  rows (`asof` only in a row without a changed amount: `save.stamp` sets it with every new value),
  in the order of the grid (`guard.changes` takes the file indices as shown), each row by its name,
  id or security after the date of a trade or the month of an event, an event without them by the
  asset, loan, policy, stream or property that it names, else by its type (`guard.label`). A number
  shows in the unit of its field (`Change.unit`, default euros): `guard.changes` takes the units of
  the table by the name of each cell (`Table.units`; `gridcolumns.asset_units` on the Snapshot
  page), not by the field name alone, since the `cost` of care is euros and the `cost` of an asset a
  share. A share or a rate shows in percent like its grid, `2.5% → 250%`. A number set to zero, that
  changes its sign or lands outside 0.5 to 2 times the old one gets an `st.warning` (`1000 times`,
  `1/1004 of the old value`: no exponent), so does a share or a rate above 100% (`2,50` reads 250 in
  an English browser; a percent column takes no maximum, so the guard sees it), not a factor shown
  in percent (`Change.capped` off: the categories of `scale` in the Overrides tab) nor a field of
  `guard.ABOVE_ONE` (`Change.capped`, which `guard.changes` and `formguard.changes` set by the key
  of the cell: a label may be words): the `hebesatz` of a business, at least 200% by law, the
  `increase` and `ceiling` of the spending rule (factors, 150% a usual ceiling). An edit of a
  `Table.locked` field of a saved row is no change but a warning (`notes`, `Table.held`). The list
  sits below its grid, often out of view on a phone while Save in the header is not: so a warning
  that is new to its list also shows once as an `st.toast` (`guard.review` keeps the warnings of the
  last run per list in `guard-<key>`, so a rerun repeats none and a value typed again warns again),
  and while a warning lasts the button carries `guard.MARK` (`Record ⚠`, `Save ⚠`, also on the
  Spend page, all in the page header). Each of these buttons has a key: without one Streamlit puts
  the label into the widget ID, and a tap that comes with the cell edit that sets or clears the mark
  is lost. Saving stays possible and takes no second tap: a big change is sometimes real, and a row
  that the model refuses (a stream, `ui.refusals`, rule `cashflows`) gets its `Not saved:`. The
  caller of `save.button` shows the list (`guard.check`, which returns whether it warns) with the
  rows it holds, since a second read of `assets.yaml` costs about 26 ms per grid, and the Assets
  page draws one per asset kind and per depot: `edit_table` under its grid or under each grid of a
  block, the Snapshot page above `Take estimates`. A page that saves something else (the Spend page,
  the price import, the trade import with its slips only, a form: `formguard.changes`, a rename:
  `rename.listing`) builds `guard.Change`s and calls `guard.review` before it writes. `notes` add
  warnings of no single cell (a price against a trade), `hint` replaces the sentence on the language
  of the browser (the import has its own decimal mark). Its quick add saves at once and warns only
  of a sum above zero (`Change.ratio` off): one more receipt is no jump. The keypad of a phone may
  have no minus: a column of `Table.negative` (the `amount` of an expense, the `balance` of a loan,
  `loan balance` of a purchase, in the `Merge` of its mapping) is saved negative whatever sign is
  typed while the row stays in its table (`Table.signed`), and so is a loan balance on the Snapshot
  page, both by `save.signed`; the guard lists the value saved, also of a column of
  `Table.unsigned`. The Spend grid keeps the sign typed, since a month can hold a refund, and the
  guard warns of an amount above zero (`Change.outflow`). Its quick add takes the euros spent and
  needs no minus.
- A `Change.added` (a field of the form of a new row, rule `forms`) lists its value alone, without
  `empty →`.
- `guard.listing` writes the list under a title: `To save:` (`review`), `Changed there:` (the
  difference of a grid whose rows changed elsewhere, `save.warn`, rule `grids`). `save.py` also
  holds the base of a grid (`Base`, `base`, `kept`, `renew`), `warn`, `changed_at`, the refusal
  of a save whose rows changed since (`save.button` with `read`), `Grid` (what a part of a tab
  adds to its Save: edit, check, nonce; `forms.save`), `Part` (grids, guard lines and `ready` of a
  part that saves with the Save of another: the drops of a scenario, `save.button(part=)`) and
  `listed`, the list that the button of a dialog writes (a file action, a rename): the one of the
  run before, none while the list now refuses.
- The guard speaks the language of the session (rule `i18n`): its sentences, the warnings, a cell
  of a grid by `names` beside `units` (`Table.names`, `gridcolumns.names`: its keys as the headers
  name them), a field of a form by its keys (`formguard.changes`); `Change.key` (`named`) keeps the
  English for a caller that tells a field by it (`assumptions.hint`, `scenario_overrides._hint`
  and `changes`). `save.changed_at` names the
  page of a change in words (`ui.page_said`), `save.reason` why a save failed: a lock, a read-only
  directory and a conflict by their type, any other error as written.
