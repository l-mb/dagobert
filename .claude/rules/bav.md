---
paths:
  - "src/dagobert/{tax,sv}.py"
  - "src/dagobert/engine/{income,events,state}.py"
  - "src/dagobert/model/assets.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{bav,tax,sv,engine,income,golden}.py"
---

# Company pension (bAV)

A `PensionPolicy` (`kind: bav`) and its salary conversion, with their sources (checked at
gesetze-im-internet.de on 2026-10-13). The rest of the tax and SV law: rule `tax`; the KV and PV
of its payout: rule `gkv`; its ledger rows: rule `ledger`. The inputs:
`docs/manual/configuration.md`, in plain English `docs/manual/models.md`.

- The policy grows with its return class less `cost` and takes the employer's `contribution` in its
  `phases`, free of tax and SV whatever its size and outside the cash; `severance.bav` (into a
  company pension) and `fund_policy` (into a Basisrente, with its own `premium`, its payout at the
  share of its start and the fundings it refuses: rule `deductions`) add lump sums to value and paid
  (`PolicyState.paid`, per path: a conversion follows the salary). At `matures` the engine pays
  max(value, guarantee × paid), nothing when that is zero. A value of an earlier `asof` starts with
  the months up to the start and their contributions, the `premium` of a Basisrente and the subsidy
  (`carry.policy`, rule `engine`). The lump sum goes through the severance path (Fünftelregelung in
  the settlement, not in the withholding). BFH X R 25/23 (2025) denies the Fünftelregelung for a
  freely chosen Kapitalwahlrecht. A Unterstützungskasse lump sum still counts as Vergütung für
  mehrjährige Tätigkeit, so the default is `fuenftel: true`. The engine ignores the
  Versorgungsfreibetrag (a few percent for a payout that starts in the 2040s, capped at a few
  hundred euros) and the guaranteed Rentensteigerung. A bAV annuity gets no PKV subsidy, its payout
  pays the KV and PV of a GKV member (rule `gkv`). An early draw (possible from 62) is not modelled.
- Salary conversion (Entgeltumwandlung, §1 Abs. 2 Nr. 3 BetrAVG): `conversion`, nominal a month in
  the policy's `phases` until `matures`, from the monthly salary `salary` (a stream of kind `salary`
  without `of` and with `every: 1`, `Plan._plan_checks`; `references` counts it as a use of the
  stream, so a rename follows), else from the first such salary that pays in the month, at most what
  the conversions before it leave of its gross (`Income._convert`). `sv.conversion` per policy in
  file order: the rooms are a twelfth of 8% (§3 Nr. 63 S. 1 EStG, 676 € in 2026) and of 4% (§1 Abs.
  1 S. 1 Nr. 9 SvEV, "insgesamt", 338 €) of the yearly BBG of the RV (`sv_bbg_month`; BMF,
  Steuerliche Förderung der betrieblichen Altersversorgung, LStH 2024 Anhang 2 III, Rn. 30: monthly
  parts of the yearly room), less what the employer pays in the month already: the contributions of
  every policy that pays (Rn. 31: they fill the room first), then the conversions before it with
  their subsidies. The subsidy is part of the conversion (Rn. 31): `subsidy`, the share of a
  contract, paid in full, else `bav_subsidy` (15%) of the conversion as far as the employer saves SV
  (§1a Abs. 1a BetrAVG): `sv.employer_sv` on the regular salary less the part within the SV room: RV
  and ALV (10.6%), in a month of the GKV (`month`, rule `gkv`) KV and PV below the KV-BBG too
  (21.15%; `rich_plan` from its switch to the GKV); above the RV-BBG
  nothing, for a PKV member never the §257 subsidy (no SV contribution). Conversion and subsidy
  beyond a room stay in that gross (`tax_free`, `sv_free` below the conversion, below zero when the
  subsidy alone exceeds the room).
- What follows the lower SV gross (`Income._pay_salaries`): the bases, so the SV, the
  Entgeltpunkte (§70 SGB VI on the beitragspflichtige Einnahmen), the PKV subsidy of the employer
  (§257 Abs. 2 S. 2 SGB V: the beitragspflichtige Einnahmen), the room of the GKV beyond the
  salary (§230), and `last_salary`, the ALG1 reference (§151 Abs. 1 SGB III: the beitragspflichtige
  Arbeitsentgelt, FW 151.1 of the Bundesagentur, 2026), so the ALG1 points too. The lower tax
  gross: the withholding of the regular salary and `YearAcc.salary_gross` (the settlement, the
  Werbungskosten). The cash gets the net of the full gross less the conversion. The page's ALG1
  estimate (`ui.cashflows._alg1`) takes the SV-free part of the conversions that pay in the month
  before the claim, each from its salary (rule `cashflows`).
- Ledger (rule `ledger`): the salary source stays the full gross; the conversion is a `spending`
  row of the group `salary conversion` (`result.CONVERSION`, item the policy label, in `expenses`
  like the loan principal) with its `moved` side, the subsidy `non-cash` `contribution`,
  `<label>: subsidy`. The budget counts the `moved` side always (`budget._oneoff`), so it is in
  `into assets`, and the Cashflows sheet shows the row `salary conversion` from the run between
  the gross and the surplus.
- Gaps: a Direktzusage or an Unterstützungskasse has no tax room (no Zufluss: the payout is
  taxed), its SV room covers the conversion alone (§14 Abs. 1 S. 2 SGB IV) and §1a Abs. 1a binds
  no subsidy; the engine applies the rules of the external ways to every policy. The employer's
  own contribution beyond 8% or 4% stays free. A conversion of a bonus, which may use the rest of
  the yearly room at once, is not modelled. A conversion under §10a and Abschnitt XI (Riester, §3
  Nr. 63 S. 2) and the §100 BAV-Förderbetrag are left out. Tests: `tests/test_bav.py` (the law in
  amounts, the engine as relations), the policy `bav` of `rich_plan` (a PKV member above the
  KV-BBG: a subsidy of 10.6%).
