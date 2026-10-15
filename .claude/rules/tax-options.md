---
paths:
  - "src/dagobert/{tax,sv}.py"
  - "src/dagobert/model/taxes.py"
  - "src/dagobert/engine/{core,health,income,profit,portfolio,settlement}.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{tax,sv,income,golden,health}.py"
---

# Church tax and the own Zusatzbeitrag

Two options of the person in `tax` (`model.taxes.TaxOptions`, beside `pkv`), the law checked at
gesetze-im-internet.de on 2026-10-13. The rest of the tax and SV law: rule `tax`; a business: rule
`self-employment`. The inputs: `docs/manual/configuration.md`, in plain English
`docs/manual/models.md`.

- Church tax (`tax.church`, `tax.land`, a `model.taxes.Land`: the file keeps its ISO code, the
  selects show its English name; the model refuses a church without a Land):
  `tax.church_rate`, the rate of the Land in the year file (`kirchensteuer`: 8% in BW and BY, 9%
  elsewhere; EKD, `Übersicht der Kirchensteuersätze`), 0 outside a church, `Core.church`. A share
  of the income tax (§51a EStG): `year_tax`, the withholding of a salary and of a sonstiger Bezug,
  the reserve of a profit (Vorauszahlungen, §51a Abs. 4) and `year_settlement` take `church`, a
  keyword without default, so each call decides. ALG1 takes none: the Leistungsentgelt deducts the
  Lohnsteuer and the Soli only (§153 Abs. 1 S. 2 SGB III). The settlement takes `church` of the
  tariff tax before the credit of the Gewerbesteuer (§51a Abs. 2 S. 3: §35 does not apply), the
  Soli of the tax after it (§3 Abs. 2 SolZG): `YearSettlement.church`, part of `total`.
- Capital income: `tax.flat_rate`, the Abgeltungsteuer (`abgeltungsteuer_rate`, 25%) less a
  quarter of its church tax, e / (4 + k) (§32d Abs. 1 S. 3, 4), with Soli and church tax on top:
  24.45% and 27.99% in all at 9%, 24.51% and 27.82% at 8%, 26.375% without. `Core.flat_rate` is
  every flat rate of the engine: `capital_gains_tax` (from the options), the gross-up of a sale,
  the latent tax and the capital income that `_flat_tax` keeps for the Günstigerprüfung, which
  counts the Zuschlagsteuern on both sides (§32d Abs. 6: the tariff delta times 1 + k, plus its
  Soli, against the flat tax paid).
- Sonderausgabe (§10 Abs. 1 Nr. 4): the church tax paid in the year, not that on the
  Abgeltungsteuer. `Core._withhold` books every withholding (salary, severance, the reserve of a
  profit) and with a church its church part into `YearAcc.church_withheld` (the withholding again
  at 0). The settlement deducts it and `Core.church_due`, the church tax of the last settlement
  less its withholding (nominal): the engine settles in December what the assessment of the next
  year settles, so that balance counts in the year after, as it is paid in reality. It replaces the
  Sonderausgaben-Pauschbetrag of 36 € (§10c) with the other Sonderausgaben (`tax.sonderausgaben`,
  rule `deductions`). Below 0 a refund, which raises the zvE after the §10d pot (§10 Abs. 4b S. 3,
  BFH IX R 34/17). The first year deducts no balance of the year before the start.
- The base takes every child allowance, whichever wins (§51a Abs. 2 S. 1; the settlement, rule
  `children`); the withholding does not (the Kinderfreibetragszähler of Abs. 2a, a gap of timing).
- Left out: the Kappung (2.75 to 4% of the zvE, on application in some Länder), the Kirchgeld of
  a mixed marriage, the church tax on capital income that the Günstigerprüfung taxes at the tariff
  as a Sonderausgabe. Leaving the church is the override `tax.church: false` of a scenario, from
  the start of its run.
- Zusatzbeitrag (`tax.kv_zusatz`, the whole rate of the own Kasse, GKV only; `sv.kv_zusatz` gives
  it, else the average of the year, twice `kv_zusatz_half`, §242a SGB V): half of it on a salary
  (§249 Abs. 1) and on the pension (§247, §249a; a voluntary member pays all and the DRV half of it
  back, §106 Abs. 2 SGB VI), `sv.kv_member_half`; all of it on the rest of the GKV (§242 Abs. 1,
  rule `gkv`): the company pension and the profit of a Pflichtmitglied (`kv_compulsory`), all that
  a freiwilliges Mitglied pays (`kv_voluntary`). The Lohnsteuer takes the member's own share (§39b
  Abs. 2 S. 5 Nr. 3 b EStG: the Zusatzbeitragssatz of the Kasse). The average stays where the law
  names it: the PKV subsidy of the employer (§257 Abs. 2 SGB V, `TaxYear.kv_half`) and of the DRV
  (§106 Abs. 3 SGB VI), the caps of the Agentur, the Vorsorgepauschale of ALG1 (§153 Abs. 1 S. 4
  SGB III).
