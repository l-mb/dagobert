---
paths:
  - "src/dagobert/{tax,sv}.py"
  - "src/dagobert/engine/{health,income,profit}.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{health,income,tax,sv,golden,profit}.py"
---

# Statutory health insurance (GKV)

The KV and PV of a member of the GKV (`tax.pkv: false`, or from `tax.gkv_from`) beside the SV of a
salary (rule `tax`), with its sources (checked at gesetze-im-internet.de, the
Beitragsverfahrensgrundsätze Selbstzahler of the GKV-Spitzenverband (BVSzGs, as of 2025-01-01) and
its Katalog of 2026-05-26 on 2026-10-13). The GRV and the tax of a business: rule `self-employment`.
In plain English: `docs/manual/models.md`.

- The month (`engine.health.Health._pay_gkv`, per path). A salary (§5 Abs. 1 Nr. 1 SGB V), ALG1 that
  pays or a Sperrzeit (`Alg1._on_alg1`, KVdA, Nr. 2, rule `alg1`) or a pension with `person.kvdr`
  (KVdR, Nr. 11; it needs nine tenths of the second half of the working life insured, the engine
  does not derive it) make it compulsory, any other month voluntary (§9, §188 Abs. 4): a gap year,
  ALG1 beyond its days, a pension before its claim (`_claim_pension` defers it), a business
  (`Profit._business`) without a salary or ALG1, a pension with `kvdr: false`. The Krankengeld of an
  employee keeps the month compulsory and free of KV (`sick`, §192 Abs. 1 Nr. 2, §224 Abs. 1 S. 1);
  a voluntary member pays on the benefit of a BU policy (`bu_paid`), not on the Krankengeld of a
  business (§224 Abs. 1 S. 2; rule `disability`). A business beside a KVdR pension stays in the
  KVdR: its profit is Arbeitseinkommen (§237 Nr. 3); the engine does not judge whether it is
  hauptberuflich (§5 Abs. 5). One person: no Familienversicherung (§10).
- The pension pays in every month (`sv.pension_net_month`, `Income._pay_pension`): half of the
  general rate and of the Zusatzbeitrag (§249a, 8.75% in 2026 at the average) and the whole PV
  rate. A voluntary member pays both rates on it (§247 by §240 Abs. 2 S. 5) and the DRV pays half
  of them back (§106 Abs. 2 SGB VI: the Zusatzbeitrag of the Kasse), the same net: `kv_voluntary`
  counts the pension first and charges only the room above it.
- The Zusatzbeitrag of every contribution here is that of the Kasse, `tax.kv_zusatz` (§242 Abs. 1;
  rule `tax-options`), else the average of the year (§242a).
- Compulsory (`sv.kv_compulsory`): the Versorgungsbezüge (§229 Abs. 1 S. 1 Nr. 5: a company
  pension, `PensionPolicy` without `basisrente`) and the profit at its run rate beside a pension or
  a Versorgungsbezug (`Health._pay_gkv`: §226 Abs. 1 Nr. 4, by §232a Abs. 3 also beside ALG1, in the
  KVdR §237 Nr. 3), each at least 0, the member alone (§250 Abs. 1) at the general rate plus the
  Zusatzbeitrag (§248 S. 1, also for the profit) and the whole PV rate. Nothing while both
  stay within a twentieth of the monthly Bezugsgröße (`TaxYear.versorgung_freibetrag`, 197.75 in
  2026), a Freigrenze (§226 Abs. 2 S. 1; §232a Abs. 3 for ALG1, §237 S. 4 for the KVdR, §57 Abs. 1
  SGB XI for the PV); above it the KV takes a Freibetrag of the same size off the company pension
  (S. 2), the PV not (§57 Abs. 1 names S. 1 and 3). The room below the KV-BBG: after the salary base
  of the month (§230 S. 1; S. 2 counts the pension apart, not before the Versorgungsbezüge:
  `test_a_pension_beside_a_salary_leaves_the_company_pension_its_room`) or after the pension (§238).
  A profit beside a salary or ALG1 alone pays nothing. Not counted: the base of ALG1 (§232a) in the
  room.
- Voluntary (`sv.kv_voluntary`, §240, §57 Abs. 4 SGB XI): the pension, the Versorgungsbezüge
  and the rest in this order up to the KV-BBG (§238a; BVSzGs §7 Abs. 3), all together at least
  `kv_min_base` (§240 Abs. 4 S. 1), the member alone (§250 Abs. 2). No Freibetrag or Freigrenze
  (BVSzGs §3 Abs. 4). Rates: the general one on the Versorgungsbezüge (§248 by §240 Abs. 2 S. 5),
  the reduced 14.0% on the rest (§243), the general 14.6% with `tax.self_employed.krankengeld`
  while a business runs (§44 Abs. 2 Nr. 2, BVSzGs §7 Abs. 3 S. 2), each plus the Zusatzbeitrag; PV
  the whole rate through `sv.pv_rate`. Pinned to the BMG `Beiträge` 2026 (the average
  Zusatzbeitrag): 222.80 and 230.71 at the minimum, 982.31 and 1,017.19 at the BBG, KV only. The
  rest, each kind
  at least 0 (a loss offsets no other kind of income, BSG B 12 KR 8/06 R): the profit at its run
  rate (`Profit._business`, as BVSzGs §5 Abs. 2 S. 2 divides the year by its months), the taxable
  `other_income` at its run rate (`Core._run_rate`: a `taxable: false` stream such as Elterngeld is
  free, Katalog, as the Kindergeld of rule `children`; one kind: a stream below zero offsets
  another, not the other kinds), the rent of a
  let property after its Werbungskosten (`Core._rent_net`, BVSzGs §3 Abs. 1b S. 1, rule `rental`),
  the annuity of a Basisrente (a private pension counts for a voluntary member, Katalog), the
  Auszahlplan of an Altersvorsorgedepot, the Gründungszuschuss but its 300 € (`Alg1State.grant`,
  §240 Abs. 2 S. 3, read 2026-10-17; Katalog; rule `alg1`), and `kv_last`.
- `kv_last` (`Health._kv_last`, each January): the capital income of the year that ended
  (`YearAcc.kv_capital`, booked by `Portfolio._flat_tax`: after the Teilfreistellung and the loss
  pot, §20 InvStG and §20 Abs. 6 EStG by Katalog and BVSzGs §3 Abs. 1b S. 4, before the
  Sparer-Pauschbetrag, which the GKV does not know: sales, interest, the §20 part of gold and
  crypto) over the months of that year in the run, `YearAcc.kv_vorab` (the Vorabpauschale, a whole
  year's, `_flat_tax(vorab=True)`) over twelve (BVSzGs §5 Abs. 2 S. 4: the last proven year, over
  the months in which it was earned), less a twelfth of `kv_capital_werbungskosten` (51, BVSzGs §3
  Abs. 1b S. 3); then a twelfth of the net gain of its private sales (§23 EStG, Katalog: §5 Abs. 3
  S. 3, one-offs) and of `YearAcc.kv_oneoff` (a taxable `lump_sum`, what an Altersvorsorgedepot pays
  at once). So the start month does not change what a Vorabpauschale adds. The first year of a run
  counts none, and a one-off counts a year late (the law: 1/12 for twelve months from the inflow, §5
  Abs. 3).
- The harvest (rule `harvest`) of a member who is voluntary in the next January
  (`Health._voluntary_next`) stops beyond the §20 pot at `Health._kv_room`: k × max(`kv_min_base`
  − `Core.kv_rest` − (kv_vorab − 51 + private sales⁺ + kv_oneoff) / 12, 0) − kv_capital, k = min(i
  + 1, 12) the months of the year in the run (as `_kv_last` divides), `kv_rest` the base of
  December beside `kv_last` (`_pay_gkv`: the pension, the Versorgungsbezüge and the rest). So
  `_kv_last` of the next year stays at the minimum.
- Versorgungsbezüge (`Health._versorgung`): the annuity of a company pension, and of a lump sum a
  `versorgung_months`-th (120) for that many months from the month after the payout (§229 Abs. 1 S.
  3 SGB V; BVSzGs §5 Abs. 4), `PolicyState.tail` from `tail_from`, nominal, deflated each month. A
  Basisrente (`basisrente: true`) is none: free for a compulsory member, the rest for a voluntary
  one. It pays an annuity, `PensionPolicy` refuses `payout: lump_sum`: §10 Abs. 1 Nr. 2 S. 2 EStG
  makes it nicht kapitalisierbar (S. 3: twelve monthly payments at once or the settlement of a
  Kleinbetragsrente, left out). The payout of an Altersvorsorgedepot is no Versorgungsbezug (§229
  Abs. 1 S. 1 Nr. 5: Altersvorsorgevermögen of §92 EStG): free for a compulsory member.
- PV of a GKV member (`sv.pv_rate`, on the employee share of a salary and on the whole rate of
  a pension): the surcharge for the childless up to the first birth (`Person.parent`: a child
  without a date, a grown one, or one of `children_born` born by the month), then 0.25 points less
  for each child under 25 from the second, at most 1 point, through the month in which the child
  completes its 25th year (§55 Abs. 3 SGB XI): one born on the first of a month on the last day of
  the month before (§187 Abs. 2 S. 2, §188 Abs. 2 BGB; `model.months.months_of_age`, as
  `Person.age`). A child of 25 does not count at all, so a grown first child leaves the second
  without a discount. Only the dates of `person.children_born` give ages
  (`Person.children_under`), so a child that it leaves out gives none. The member bears the
  surcharge (§58 Abs. 1 S. 3, §59 Abs. 5) and the discount: no law assigns that, the Kassen take it
  off the employee share, and the employer pays half of the base rate (TK Beratungsblatt `Beiträge
  in der Pflegeversicherung`, 2026). The Lohnsteuer takes the same PV in its Vorsorgepauschale
  (§39b Abs. 2 S. 5 Nr. 3 c EStG).
- The switch (`tax.gkv_from`, `TaxOptions.pkv_in`; owner 2026-10-16): a PKV member (the model
  refuses it with `pkv: false`) is in the GKV from that month. `Core.pkv` is the status of the
  month, which every reader takes: `sv.sv_on` (the SV of a salary, its Vorsorgepauschale),
  `employer_sv` and `conversion` (`month`, rule `bav`), `pension_net_month` (the KVdR or the DRV
  subsidy), `Income._health_support` (§257 SGB V, §174 SGB III, §106 SGB VI), `_fix_sick_pay`,
  `Health._pay_gkv` and `_voluntary_next` (the GKV next January: the harvest cap of the December
  before a switch, whose `_pay_gkv` keeps `kv_rest`). `Core._stream_state` ends a `health` stream
  in that month (also one of `add_stream`), `cashplan.with_gkv` the rows of the estimates of the
  Cashflows, Overview and Spend pages. `health_deductible` sums by month, so the settlement of the
  switch year deducts the PKV Basis share before and the GKV contributions after; `kv_last` of the
  first GKV year takes the capital income of the last PKV year. `person.kvdr` stays an input: a
  late switch seldom reaches the nine tenths. No Explorer switch: a scenario per choice.
- Markers (checked at gesetze-im-internet.de on 2026-10-16), never refusals: `exemption` when the
  claim to ALG1 arises (`Alg1._open_alg1`, a Sperrzeit too) in a PKV month before `gkv_return_age`
  (55): ALG1 makes a compulsory member (§5 Abs. 1 Nr. 2) unless exempt on application within three
  months, irrevocable (§8 Abs. 1 S. 1 Nr. 1a, Abs. 2), which the run assumes; `gkv` in the month of
  a switch at 55 or later (`Health._mark_switch`): §6 Abs. 3a keeps one who was outside the GKV for
  five years free of it. The words: `charts.SAYS` (rule `charts`). The user sets the month: the run
  does not find the first ALG1 month or a salary below the Jahresarbeitsentgeltgrenze (§6 Abs. 1
  Nr. 1, Abs. 6, 7).
- The ledger: `Health._pay_gkv` books `KV` and `PV` of the month (rule `ledger`), all of it is
  deductible in the settlement (`YearAcc.health_deductible`), and the reserve of a business takes
  it off (`Profit._pay_profit`). PKV: nothing here.
- Gaps: the Kasse sets the voluntary contribution provisionally from the last tax notice and finally
  after the notice of the year (§240 Abs. 4a): the engine takes the profit of the month and the
  capital income of the year before, both final at once. The capital income beside a profit or a
  rent counts by law in its own year (BVSzGs §5 Abs. 2 S. 3). A rent without `property` counts in
  full, as its tax does. A severance of a voluntary member (BVSzGs §5 Abs. 5: the last salary for
  the days of the Ruhen) is free. A lump sum paid before the start leaves no tail. The 4% cut of the
  deductible KV with Krankengeld (§10 Abs. 1 Nr. 3 S. 4 EStG) is left out. The refund on application
  of the own share of the pension's KV and PV above the BBG with the salary and the
  Versorgungsbezüge (§231 Abs. 2) is left out: a working pensioner pays too much. The KV-BBG and the
  Bezugsgröße (`kv_min_base`, the Freigrenze) follow the CPI in the run (rule `tax`), the law the
  wages (§6 Abs. 6 SGB V, §18 SGB IV): over decades they fall behind, more for a voluntary one. The
  loss pot of capital income from earlier years, also `tax.capital_losses`, lowers `kv_capital`, but
  the Beitragsrecht knows no Verlustvortrag (SG München, BeckRS 2021, 15075, on §10d; for §20 Abs. 6
  unverified): errs towards less contribution.
- Tests: `tests/test_health.py` (the law in amounts, the engine as relations; the church tax changes
  no KV), `gkv_plan` of `test_golden.py` (salary, ALG1, business with the Gründungszuschuss, gap
  years from a depot and a rent, a lump sum, the KVdR, a company annuity and a Basisrente; VPW
  spends from the gap years; disabled in 2028, rule `disability`), the Krankengeld and a BU in
  `test_disability.py`. The switch: `test_health.py` (with and without it, the settlement, the
  harvest cap, the markers), `rich_plan` (`gkv_from` 2035-01 at 58, `kvdr: false`: compulsory in the
  part time with a bAV tail, voluntary at the KV-BBG as a pensioner; the marker of ALG1 at 52).
