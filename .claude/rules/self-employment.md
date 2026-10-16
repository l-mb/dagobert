---
paths:
  - "src/dagobert/engine/profit.py"
  - "src/dagobert/{tax,sv}.py"
  - "src/dagobert/model/taxes.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{profit,tax,sv}.py"
---

# Self-employment

The law of a business that the engine applies, with its sources (checked at gesetze-im-internet.de
and the official values of 2026 on 2026-10-13); the rest of the tax and SV law: rule `tax`. The
inputs: `docs/manual/configuration.md` (`kind: self_employed`, `hebesatz`, `tax.self_employed`), in
plain English `docs/manual/models.md`. No phase kind: the engine reads what the month pays.

- A stream of `kind: self_employed` pays its `amount`, the profit of a month before tax and own SV,
  times its factor, the `scale.salary` of the phase (the salary slider of the explorer scales it
  too) and its index (`Profit._profit_nominal`). It may be below zero, a loss. It runs while it is
  active by dates and phases (per path by `after_sale_of`) at a factor other than 0
  (`Profit._running`): a factor of 0, also of `scale.salary`, switches the business off; a profit
  of 0 or below keeps it running and pays the minimum KV. A stream paid every n months pays in its
  months; its SV takes the run rate, `amount / n`, in every month in which it runs.
- Income tax (§2 Abs. 1 Nr. 2, 3, §§15, 18 EStG): a paid profit joins `YearAcc.other_taxable`, no
  Werbungskosten-Pauschbetrag (the business expenses are inside the profit); a loss offsets the
  other income of its year, the rest carries forward (§10d, rule `rental`). The Vorauszahlungen (§37
  EStG: quarterly, at the tax of the last assessment) are a monthly reserve into `withheld`,
  `tax.profit_reserve`: the tax of the regular monthly profit as if earned all year, less the RV of
  the month and its KV and PV or the deductible PKV premium and a Basisrente premium (none when a
  salary takes them), a payment every n months on top as a one-off (`withholding_oneoff`). The
  December settlement pays the difference; a profit beside a salary reserves as if alone. No
  Vorsorgepauschale (it belongs to the Lohnsteuerabzug, §39b Abs. 2 S. 5 Nr. 3): the settlement
  takes the premiums paid. The own GRV contribution counts in full against the Höchstbetrag (no
  employer share, §10 Abs. 3 S. 5).
- Gewerbesteuer: a stream with `hebesatz` (at least 200%, §16 Abs. 4 S. 2 GewStG) is a trade
  business, one per stream name (`YearAcc.trade`: a raise row keeps the one Freibetrag), one
  without it a Freiberufler (§18 Abs. 1 Nr. 1 EStG; which one applies is the user's question).
  `tax.trade_tax`: the Messbetrag, `gewst_messzahl` (3.5%) of the profit of the year beyond
  `gewst_freibetrag` (24,500, §11 Abs. 1 S. 3 Nr. 1, Abs. 2), times the Hebesatz; its credit
  `gewst_credit_factor` (4) times the Messbetrag, at most the Gewerbesteuer (§35 Abs. 1 S. 1 Nr. 1,
  S. 5 EStG) and the share of the tariff tax on the trade income (S. 2: the positive trade profits
  over salary, severance, taxable pension and the other income, at least the trade profits).
  `tax.year_settlement` takes it off before the Soli (§3 Abs. 2 SolZG): up to 400% the Gewerbesteuer
  comes back in full and the Soli falls. `YearSettlement.trade_tax` is part of `total`, so the late
  sales and the split of a severance see it; the ledger item `trade tax` is spread like the income
  tax. Left out: Hinzurechnungen and Kürzungen (§§8, 9 GewStG), the rounding to 100 € (§11 Abs. 1
  S. 3), the Vorauszahlungen of §19 GewStG (the reserve takes the income tax before the credit, so
  the December bill nets the two), a business in several municipalities (Zerlegung).
- Social insurance (the options `tax.self_employed` of the person: two businesses pay once, on
  the sum of their run rates, `Profit._business`) in a month in which a business is the main
  work: no salary and no month of ALG1 (`_on_alg1`, rule `alg1`; §5 Abs. 5 SGB V; a salary keeps
  its Pflichtversicherung, ALG1 the KVdA of §5 Abs. 1 Nr. 2, and the profit pays only beside a
  pension or a Versorgungsbezug, rule `gkv`). GKV (`tax.pkv: false`): freiwillig (§9 Abs. 1 S. 1 Nr. 1,
  the Vorversicherungszeit assumed) on all income, the profit at its run rate with the rent, the
  other income and the capital income (rule `gkv`, `sv.kv_voluntary`), between
  `TaxYear.kv_min_base` (the 90th part of `bezugsgroesse_month` per day, 30 days: §240 Abs. 4 S. 1
  SGB V, §57 Abs. 4 SGB XI, 1,318.33 in 2026) and the KV-BBG, the member alone: 14.0% (§243, no
  Krankengeld), 14.6% with `krankengeld` (the Wahlerklärung, §44 Abs. 2 Nr. 2), plus the
  Zusatzbeitrag of the Kasse (rule `tax-options`); PV the whole rate. A business beside a KVdR
  pension pays in the KVdR (rule `gkv`). PKV: the `health` streams in full, no subsidy (§257 Abs. 2
  SGB V names Beschäftigte), the Basis share deductible.
- GRV (`sv.rv_self_employed`, `rv`): `none` (the law of today for most; voluntary contributions are
  `rv_voluntary` streams, which §7 Abs. 1 SGB VI allows only without compulsory insurance: the
  manual says so), `regular` (the groups of §2 SGB VI, or the Antragspflicht of §4 Abs. 2 within
  five years of the start: the Regelbeitrag, `rv_rate_total` of `bezugsgroesse_month`, 735.63;
  `rv_founding_share` of it up to the end of the `rv_founding_years`-th calendar year after the year
  of the founding, §165 Abs. 1 S. 2: 367.82; the whole Bezugsgröße on application in those years is
  left out), `income` (the proven profit, at least `geringfuegigkeit_month`, §8 Abs. 1a SGB IV: 603,
  up to the BBG; never half: the half base of S. 2 serves `regular` only, the proof of the profit is
  the choice of `income` in the founding years too). The founding: `tax.self_employed.founded`, else
  the first month in which a business runs (`Core.first_profit`), so a later phase moves it; a roll
  forward past that month writes it (rule `rollforward`). Points: the contribution as a voluntary
  one (`sv.voluntary_points`), the month counts as Versicherungszeit and as one of Pflichtbeiträge
  (§55 Abs. 1 SGB VI: the EM-Rente, rule `disability`), `rv_paid` takes it all, no `rv_employer`.
  The Alterssicherungskommission (report of 2026-06-23, Empfehlung 22) wants every new self-employed
  person in the GRV; no draft is law. When it is, a tax year gets a constant to compare with the
  founding month: no switch now.
- Altersvorsorgedepot: from 2027 income under §15 or §18 Abs. 1 Nr. 1 to 3 EStG makes its owner
  eligible without a compulsory insurance (Altersvorsorgereformgesetz, BGBl. 2026 I Nr. 156): a
  running business sets `YearAcc.compulsory` whatever `rv` says. Its bound of age 67 never bites:
  the payout starts by then, and with it the contributions end.
- Gaps: the Kassen and the DRV take the profit of the last Einkommensteuerbescheid, set
  provisionally (§240 Abs. 4a SGB V, §165 Abs. 1 SGB VI): the engine takes that of the month, the
  capital income of the year before (rule `gkv`). A salary beside a business makes the salary the
  main work whatever their sizes, and a KVdR pension keeps the KVdR (§5 Abs. 5 would end it for a
  hauptberuflich business). No ALV: the Antragspflichtversicherung (§28a SGB III, 2.6% of the
  Bezugsgröße, 102.83 € in 2026, §345b) is an expense stream. ALG1 after a business: without §28a it
  earns no Anwartschaft (§142), with it the fictitious wage of §152 Abs. 2 by Qualifikationsgruppe
  (1/300 of the yearly Bezugsgröße a day for a degree, 158.20 € in 2026); the engine pays on the
  last salary, however long ago (right for a Restanspruch, which lasts four years, §161 Abs. 2), and
  marks `alg1: on the last salary, not on the self-employment`; a later stretch pays the days left
  (rule `alg1`); a business out of unemployment may take the Gründungszuschuss
  (`gruendungszuschuss`, rule `alg1`: its months are those of the main work); a profit beside ALG1
  does not reduce it (§155: 30% flat expenses, a Freibetrag of 165 €); the 4% cut of the deductible
  KV with Krankengeld: rule `gkv`. `Core.first_profit` is the first month of any business of the
  run: a second business after a stretch without one gets no new half years (whether a new Aufnahme
  starts them again, §165 Abs. 1 S. 2 SGB VI, is open; `founded` sets the start). Left out:
  Umsatzsteuer (the profit is net of it), the sale or the end of the business (§§16, 34 EStG), the
  Künstlersozialkasse, Versorgungswerke (an `rv_voluntary` stream approximates the contribution, a
  `pension` stream with `gross` the pension).
