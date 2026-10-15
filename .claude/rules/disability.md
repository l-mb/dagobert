---
paths:
  - "src/dagobert/{tax,sv,anatomy,cashplan}.py"
  - "src/dagobert/engine/{core,income,health,profit,state}.py"
  - "src/dagobert/model/{assumptions,streams,events}.py"
  - "src/dagobert/data/tax/*.yaml"
  - "src/dagobert/report/summary.py"
  - "tests/test_disability.py"
  - "tests/test_golden.py"
---

# Disability

The loss of the ability to work (a full Erwerbsminderung, §43 Abs. 2 SGB VI) per path, the months
after it and a BU policy. Law checked at gesetze-im-internet.de on 2026-10-13 (SGB VI §§3, 34, 43,
50, 59, 72, 75, 77, 88, 101, 253a; SGB V §§44, 47, 48, 192, 224; EStDV §55), the DRV values of
2026. Individuals only. The rest of the tax and SV law: rules `tax`, `gkv`; the run: rule `engine`;
the ledger: rule `ledger`. The inputs: `docs/manual/configuration.md`, in plain English
`docs/manual/models.md` (`When you cannot work`).

## Inputs

- `assumptions.disability` (`model.assumptions.DisabilityOptions`, optional, beside `care`):
  `hazard` (`DisabilityPoint` rows, the yearly chance by age, linear, zero before the first age;
  default `DEFAULT_HAZARD`, so `overrides.disability.at` on a plan without the block takes it) and
  `at` (a forced onset in every path, also of a `fixed` run: a what-if; before `start` or at an
  age of `REGELALTERSGRENZE` (67, a literal: the model reads no tax year) refused,
  `Assumptions._disabled_in_the_run`). Without the block no path is disabled.
- `DEFAULT_HAZARD`: 171,732 new EM-Renten in 2024 on 38,573,053 aktiv Versicherte of 15 to 64
  (DRV, Aktuelle Daten; RV in Zahlen 2026, p. 30), 4.45‰, spread by an exponential in age, fitted
  so that the rate weighted by the aktiv Versicherte by age (DRV, Versicherte 2024, table 3.00 V)
  hits 4.45‰ and its mean age the mean Zugangsalter of 53.8 less the seven months of §101 Abs. 1:
  0.044% at 20 to 1.614% at 64, about 20% with an onset before 67 from 40.
  `test_the_default_hazard_hits_its_anchors` pins both and the cumulative.
- A stream of kind `bu` (`StreamKind.BU`, `Disability insurance (BU)`): `amount` the monthly benefit
  (0 or more), `premium` (0 or less, `Euros`, a field of the kind alone) and `until_age` (default
  67, the contractual end), `index` default null (`streams.NOMINAL`, a guaranteed benefit; `cpi` a
  dynamic one), `cat` its spending group, `start`, `end`, `tags`, `after_sale_of`. `phases`,
  `factor` and `every` refused (`Stream._together`: a contract runs by age). A `set_stream` sets
  its `premium` (`SetStreamEvent.premium`, only on a `bu`, `plan._update_problems`): the owner's
  employer BU at premium 0, its own premium from the leave. Two rows of one name do the same; `end`
  or `end_streams` let it lapse: no premium and no claim of a later onset, a claim stands.

## Engine

- `Core._draw_disability` at setup: `onset` `(paths,)`, the month index or -1. `at` in every path;
  else the first month whose draw of `generator(seed, "disability")` falls below the monthly chance
  `1 − (1 − yearly)^(1/12)`, before the Regelaltersgrenze; a single path without `at` draws none.
  `Income._claim_pension` drops every onset in or after the month of the old-age claim (§34 Abs. 2
  SGB VI); `RunResult.onset` holds the onsets that stand, `RunResult.em` the paths that claim an
  EM-Rente.
- From the onset m0 (`Core.working`, 0 from m0 + `efzg_months`): the salary (`_salary_nominal`), a
  profit (`Profit._profit_nominal`, `_business`), ALG1 and its points, the employer's bAV
  `contribution` stop after two months of Entgeltfortzahlung (§3 EFZG); a conversion stops with the
  salary, a Basisrente premium goes on. `last_salary` keeps the salary per path.
- `Income._disable` in m0, before the streams: `em_ok` per path, scalar from the run:
  `insured_months` ≥ `em_wartezeit_months` (§50 Abs. 1), at least `em_pflicht_months` of the last
  `em_window_months` with Pflichtbeiträge (`PensionState.compulsory`, a ring of the months: a
  salary, ALG1, a business with `rv` not `none` (§55 Abs. 1: `Profit._pay_profit`), child-raising
  years, Krankengeld with RV; seeded with the months since `rv_since` when the first month pays, as
  the run cannot see the years before), and a pension stream from points (`_grv`, the first; a
  `gross` pension, a Versorgungswerk, carries none). The points freeze (§75 Abs. 2 S. 1):
  `PensionState.em_points` = the points reached × (1 + Zurechnungszeit / months since `rv_since`, at
  the earliest the 17th birthday, `INSURED_FROM`), the Zurechnungszeit to
  `TaxYear.zurechnung_months` of the year of the Rentenbeginn (§253a Abs. 3).
- Krankengeld (`_fix_sick_pay` in the last month of pay, `_pay_sick` from m0+2 to m0+6 until the
  old-age claim (§50 Abs. 1 S. 1 Nr. 1 SGB V), a GKV member only: `SickPay`): on the salary of that
  month (`sv.krankengeld_month`: 70% up to the KV-BBG, at most 90% of its net after the Lohnsteuer
  and the church tax), else on the profit of a business with `tax.self_employed.krankengeld` (no net
  cap, §47 Abs. 4); less the member's half of RV, ALV, PV (of a business its RV only, with `rv` not
  `none`) on the Krankengeld paid, not on the 80% of the gross that the Kasse pays on (§166 Abs. 1
  Nr. 2 SGB VI): the member's half falls only "soweit sie auf die Leistung entfallen" (§170 Abs. 1
  Nr. 2 a; Haufe 2026-07-08: "vom Zahlbetrag"). Booked `KRANKENGELD` with `RV`, `AV`, `PV`; the
  gross into `YearAcc.lohnersatz` (§32b Abs. 1 S. 1 Nr. 1 b: the gross, hkk), RV into `rv_paid`, PV
  into `health_deductible`. No points (the EM points stand). An employee's month is compulsory and
  free of KV (`_pay_gkv(sick=)`, §192 Abs. 1 Nr. 2, §224); a business's stays voluntary, the
  Krankengeld outside its base. PKV: none (the Krankentagegeld of a tariff is left out).
- EM-Rente (`_claim_em` in m0 + `em_start_months`, before an old-age claim): `PensionState.em` on
  the path, `em_factor` (`sv.em_factor`, §77 Abs. 2: 0.3% a month before 65, counted from 62), its
  year in `start_year`. `_pension_paid` pays the carrier on such a path whatever its phases, at the
  frozen points and factor, also after 67 (§88 Abs. 1 S. 2), the old-age claim on the other paths;
  the ledger books it by the stream's name in its phases, else `EM_RENTE`. It opens the
  Altersvorsorgedepot (`acc.compulsory`); its payout waits for the old-age claim (`claimed`).
  Per path: `start_year` (`_shares`: one `pension_share` per year), the Rentenfreibetrag; the KVdR
  and the DRV subsidy as for any pension.
- `Income._mark_onset`, after `_pay_streams`: the marker `disability` of a forced onset that the
  old-age claim of its month left standing.
- `Income._pay_bu` (`_pay_streams`, each month), under `until_age`: the premium while in force
  (`_pays`, the mask) through m0 (a `spending` row of its `cat`, outside the cut of `_index`); an
  onset while in force sets `StreamState.claim` (a row that starts later has none), whose benefit
  (`<name>: benefit`, `BENEFIT`) pays from m0+1 whatever ends the row later (`end`, `end_streams`,
  a sale: a contract pays a running claim to its end), taxed at `tax.ertragsanteil` of the years
  from its start to `until_age` (R 22.4 Abs. 4 EStR: rounded down) as other income, in the base of
  a voluntary member (`bu_paid`).
- The old-age claim stays scalar (`claimed`, `regular`, the Versicherungszeit of the paths that
  pay): a disabled path takes its payout start of the Altersvorsorgedepot from the others.

## Results

`summary` `P(disability)` (`Chance of disability`, weighted by the survival at the onset, not in
the console summary: twelve columns leave the scenario no room in 120); `anatomy.DISABLED`, the
age at the onset, bins at 50 and 60 (`DISABLED_AGES`); the difference and the sensitivity pair up
by the purpose. `cashplan.monthly` takes the premium of a `bu` row, the benefit nowhere; the
Cashflows page has the tab `disability insurance` (`cashflows.BU`, the benefit `Monthly benefit €`).
The Assumptions page: section `Disability` of `Rules`. The roll forward: `at` before the new start
blocks it (`rollforward.DISABILITY`), `rebase` scales `premium` of a `cpi` row.

## Gaps

Partial EM and §96a, recovery and the Befristung (§102), the Arbeitsmarktrente, §77 Abs. 4 (40
years), the Anrechnungszeiten of §§71, 72 (out of the months of the Zurechnungszeit), the
Grundrentenzuschlag, points after the onset for the Altersrente alone, the PV on Krankengeld of a
business (§57 Abs. 2 SGB XI), an onset during ALG1 (§146 SGB III, §47b SGB V: nothing paid), the
waiting time of a business's Krankengeld (§46 S. 3: its profit pays the two months), the
Krankentagegeld of the PKV, the BU premium as a Sonderausgabe, the 102 € of §9a S. 1 Nr. 3 on a BU
benefit without a GRV pension, a BU without an EM (Berufsunfähigkeit only: the one hazard
understates the benefit), a BU of a bAV (§3 Nr. 63: taxed in full, §22 Nr. 5, and a
Versorgungsbezug), the Karenzzeit and the Nachversicherung of a tariff, the higher mortality of
EM-Rentner, the Rehabilitation, a Hinterbliebenenrente, a savings plan that buys on while the cash
lasts, the BU of a Versorgungswerk, the Versicherungszeit of the old-age claim per path.

## Tests

`tests/test_disability.py` (relations: the months of pay, premium and benefit; Krankengeld of an
employee and of a business; the EM-Rente and no step at 67; the points and the factor of the law; a
voluntary contribution after the onset; a gap; no EM-Rente without three years, with a business in
the GRV; the Ertragsanteil; the KV of a voluntary member; `set_stream` against two rows; a lapse
before and after the onset, a row after it; outside the cut; drawn paths against forced ones; the
pairing; the refusals; an onset in the month of the old-age claim; the default anchors), amounts in
`test_tax.py` and `test_sv.py`, `gkv_plan(DISABLED)` of `test_golden.py` (2028-03 in the business
with Krankengeld: the voluntary KV on the benefit, the EM-Rente in the KVdR), the premium in
`rich_plan`.
