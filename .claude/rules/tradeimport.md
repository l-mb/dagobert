---
paths:
  - "src/dagobert/tradeimport.py"
  - "src/dagobert/ui/tradeimport.py"
  - "tests/test_tradeimport.py"
---

# Trade import

The expander `Import trades` of the Assets page: rule `tracking`. The lots that the trades give:
`lots.py`, rule `tracking`.

- `uv run dagobert trades import ASSET FILE` adds the buys and sales of a broker export (CSV) to the
  trades of the asset `ASSET` (equity, fixed income, gold, crypto) as one revision `trades import`,
  after `datadir.open`. `--column FIELD=HEADER` (once per field, `''` for none), `--decimal` and
  `--dates` default to the guess; it prints the mapping, the refused lines, `tradeimport.summary`
  and the slips, which stop it unless `--force`. `--dry-run` saves nothing. It exits with 1 for an
  asset that is gone or holds no securities, a missing column, a refused line without a trade added
  or held already (`no trade to add`) and a conflict.
- `src/dagobert/tradeimport.py`: `guess` maps the columns by header (`ALIASES`, without case, whole
  before start, each column for one field), after the exports described in public: the transaction
  export of Trade Republic (`date`, `type`, `symbol` with the ISIN, `shares`, `amount`, `fee`,
  `name`, `currency`; a decimal point, amount and fee signed), the transactions of Scalable Capital
  (`date`, `type`, `isin`, `shares`, `amount`, `fee`, `description`, `currency`, `status`; a decimal
  comma, the newest first) and the Depotumsätze of comdirect (`Datum`, `Art`, `ISIN`, `Menge`,
  `Kurswert`, `Bezeichnung`, `Kurswertwährung`: the currency of the amount, not of the price; no
  fees). ING and consorsbank describe no export of the depot: the user picks the columns. Without a
  header the security is the first column of ISINs; the date column and the decimal mark come from
  `csvimport.guess`. `read` takes a kind by the start of its cell (`KINDS`: `Kauf`, `Buy`,
  `Sparplan`, `Savings plan`; `Verkauf`, `Sell`; `Vorabpauschale`) and leaves out, with its line
  (`Parsed.others`), any other kind (`Distribution`, `Umbuchung`, `DIVIDEND`; the `Taxes` of
  Scalable are the tax, not the Vorabpauschale, which stays typed by hand) and a status that is no
  execution (`DONE`: `Executed`, not `Cancelled`), `NoTrade`. Without a kind column a minus before
  the units sells. Units, amount and fees lose their sign, amount and fees round to cents. Refused
  with its line: a missing cell, a date or number that does not read, a date after today, a currency
  other than EUR (an empty cell is EUR), a buy or sale without units, a row without amount or ISIN.
  A file whose first date is newer than its last reads backwards, so a sale follows the buy of its
  day. `merge`, oldest first, against the trades of the asset (`holding`: the asset of one read and
  the `Seen` of its trades): a row with the date, security, units and amount of a trade is held
  already, each trade once (a file that repeats an execution of a day adds the second); refused are
  a row that the model refuses (a Vorabpauschale out of January), a security that the asset does not
  take (`HoldingsAsset.securities`) and one that the trades so far cannot replay (`lots.book`: a
  sale of more units than held). A security without a name takes that of its first row. `slips`:
  `prices.off_series` and `prices.off_trades` against the price file of each security. `save`:
  `RowFile.apply` with `seen`, and a depot drops its `cost_basis` like at its first buy.
  `replaced_basis` warns of that drop (the lots of recent months only would leave out the cost
  of what the depot held before): a `Check:` line of the command, a note of the guard of the
  import, the trades grid (`tradeform.basis_check`, `Table.check`) and a toast of the form.
