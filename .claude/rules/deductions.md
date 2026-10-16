---
paths:
  - "src/dagobert/tax.py"
  - "src/dagobert/engine/{income,settlement,events,state}.py"
  - "src/dagobert/model/{assets,events,plan,streams,taxes}.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{deductions,tax}.py"
---

# Deductions, the Basisrente and the Zulage

What lowers the income tax beyond the Vorsorge: the Werbungskosten above the Pauschbetrag, the
Sonderausgaben, the credit of §35a; the own premium of a Basisrente and its payout at the share of
its start; the Zulage of the Altersvorsorgedepots once per person, with the Kinderzulage of 2027.
The law checked at gesetze-im-internet.de and in BGBl. 2026 I Nr. 156 (Altersvorsorgereformgesetz)
on 2026-10-13. The rest of the tax law: rule `tax`; a company pension: rule `bav`; the church tax:
rule `tax-options`; §10d and a let property: rule `rental`. The inputs:
`docs/manual/configuration.md`, in plain English `docs/manual/models.md`. Individuals only: no
spouse rule anywhere.

- Werbungskosten (owner 2026-10-16, which ended their one source): `tax.werbungskosten`
  (`TaxOptions`), the yearly costs of the job of the Steuerbescheid, start-year euros, and the
  expenses with `deduct: work`, costs at a date (§9 EStG: a course, applications, also before a job,
  vorweggenommene Werbungskosten), in the year that pays them. `tax.werbungskosten(salary, pension,
  ty, actual, dated)`: `max(min(pauschale, salary⁺), min(actual, salary⁺) + dated)` plus the 102 of
  the pension (§9a S. 1 Nr. 1 a, Nr. 3, S. 2); the settlement passes `actual` times
  `YearAcc.sv_months / 12` (a job that ends in March deducts a quarter, the month the work-end seek
  moves) and `dated` = `YearIncome.work` (`YearAcc.deduct[work]`). The yearly costs stop at the
  Arbeitslohn, the dated ones do not: a loss of §19 (§2 Abs. 3) joins §10d, back first (rule
  `rental`). The withholding (`_zve_year`, §39b Abs. 2 S. 5 Nr. 1, 2: the Arbeitnehmer- and the
  Sonderausgaben-Pauschbetrag) and `sv.alg1_month` (§153 SGB III) pass 0: a Freibetrag of §39a is
  on application, the settlement refunds. ALG1 under the Progressionsvorbehalt counts less the part
  of the Pauschbetrag that the deducted work expenses leave, `max(0, pauschale - deducted)` (§32b
  Abs. 2 S. 1 Nr. 1): none where higher costs came off (BFH III R 61/12 of 2014-09-25, also dated
  ones in a year without a salary), the rest of it where dated costs below it came off without a
  salary. The judgment decides costs above the Pauschbetrag: the wording of §32b is neutral, the
  actual costs and the Pauschbetrag never come off both. Dated costs below it without a salary it
  does not decide (review 2026-10-16): a modelling choice keeps the relief, §19 and ALG1 together,
  at `max(deducted, pauschale)` at every point. The literal reading, `pauschale - min(pauschale,
  salary⁺)` unless the costs are higher, relieves costs of 1,229 € without a salary by 2,459 € in
  all and costs of 1,231 € by 1,231 €; the choice errs by a few euros of rate towards more tax. The
  negative Progressionsvorbehalt it could give is left out.
  `rollforward.rebase` scales `tax.werbungskosten` (rule `rollforward`), a scenario overrides it.
- Expenses with `deduct` (`model.streams.Deduction`: `work`, `donation`, `childcare`, `household`,
  `craftsman`; `TAKES` of an expense only, `Stream._together` refuses it with `health` or with
  `property`: a cost of letting is a Werbungskosten of the rent, §35a Abs. 5 S. 1). The cash flow
  stays an expense of its category. `deductible` is the share that counts (default 1; of a `health`
  premium its Basis share, rule `tax`): the labour of a bill (§35a Abs. 5 S. 2), the donations among
  gifts. `Income._deduct` adds what the month paid (after `scale.categories`, the age curve and the
  spending cut, real) times that share into `YearAcc.deduct[kind]`; `childcare` only in a month
  with a child under `childcare_age` (`Person.children_under`).
- The settlement (`tax.year_settlement`, its zvE `tax.zve`, which the harvest room of rule `harvest`
  takes too; `YearIncome` `donations`, `childcare`, `children`, `household`, `craftsman`):
  `sonderausgaben` = `max(36, max(church_paid, 0) + gifts + care) + min(church_paid, 0)`: the
  Sonderausgaben-Pauschbetrag (§10c, also in the withholding), the church tax (rule `tax-options`),
  care `childcare_share` (80%) of the costs up to `childcare_max` (4,800) per child under 14 in any
  month of the year (`Person.children_in`, of `children_born` only: a child without a date counts
  none; no twelfths, §10 Abs. 1 Nr. 5 S. 1), donations up to `donation_share` (20%) of the
  Gesamtbetrag der Einkünfte `gde`, the rest lost (§10b Abs. 1 S. 1 Nr. 1; the carry of S. 9 is a
  gap). A church refund beyond the year's payments comes after the §10d pot (§10 Abs. 4b S. 3: it
  raises no Gesamtbetrag der Einkünfte, BFH IX R 34/17, BStBl II 2019, 658; the negative GdE of FG
  München 12 K 1937/19 is a gap). `haushalt_credit`: `rate` (20%) of each kind up to `household`
  (4,000) and `craftsman` (1,200), no carry (§35a Abs. 2 S. 1, Abs. 3 S. 1). Order (`_credited`, §2
  Abs. 6 S. 2, R 2 Abs. 2 EStR, BFH X R 11/21): the credits of §35 (at most its share, rule
  `self-employment`) and §35a come off the tariff tax, which floors at 0 before the Zulage of §10a
  comes back; each side of the check of §10a Abs. 2 floors on its own, the capital income of the
  Günstigerprüfung too. The Soli takes the tax after them (§3 Abs. 2 SolZG), the church tax the tax
  before §35 only (§51a Abs. 2 S. 3). `YearSettlement.credit` holds the credits taken. The §35 share
  counts a negative rent as none: `YearIncome.rent` (`YearAcc.rent`, `Income._let_income`) leaves
  the positive income of the other kinds whole.
- Constants of the year file: `childcare_share`, `childcare_max`, `childcare_age`,
  `donation_share`, `haushalt_credit` (`tax.HaushaltCredit`), `av_kinderzulage`;
  in start-year euros at the price level of the year like every constant (rule `tax`), though the
  law keeps them nominal.
- Basisrente (`PensionPolicy.basisrente`, rule `bav`): `premium` (nominal a month) from the cash in
  the `phases` until `matures` (`Income._policy_flows`, beside the employer's contribution), into
  `value` and `paid`, into `YearAcc.rv_paid` (§10 Abs. 1 Nr. 2 b; `rv_deductible` caps at the
  Höchstbetrag less the employer share, 100% since 2023); the reserve of a profit takes it off
  (`own` of `_apply_streams`). Deficit cover pays it (a contract is due). A `fund_policy` into a
  Basisrente deducts the same (no flag). Refused: `contribution` or `conversion` on a Basisrente,
  `premium` without it (`PensionPolicy._payout`), `severance.bav` into one and a `fund_policy` into
  a company pension (`Plan._fundings_fit`, `FUNDING`: money free under §3 Nr. 63 comes out taxed in
  full, §22 Nr. 5 S. 1; a private top-up of a bAV is not modelled).
- Payout at the Besteuerungsanteil (§22 Nr. 1 S. 3 a aa): the annuity is nominal and fixed, so
  `PolicyState.taxable` = `pension_share` of `matures.year` (at least `pension_share_step_since`:
  a start before 2023 takes the share of 2023, a gap) times it is the same euros each year, the
  Freibetrag frozen (S. 4, 5). It joins `YearAcc.basisrente`, the settlement's `pension_taxable`
  with the one 102 € of §9a S. 1 Nr. 3; a company annuity stays `other_taxable` in full. The KV of
  a voluntary member takes it whole (rule `gkv`).
- Ledger (rule `ledger`): the premium books `move out` and `moved` of `result.SAVINGS_PLAN`, item
  `<label>: premium` (`OWN_PREMIUM`), so `Budget.saved` shows it as `into savings plans`; so does
  the December contribution of an Altersvorsorgedepot, with a 12-month run rate (`_spread`). A
  `fund_policy` stays `policy premium`, a one-off.
- Altersvorsorgedepot (`Income._contribute_av`): one Zulage and one room of §10a per person
  (§84 S. 1): `tax.av_zulage` and `av_deduction` on the sum of the contributions of all depots, the
  Zulage split by them. The Kinderzulage of 2027 (§85 Abs. 1 S. 1 as of 2027-01-01): the
  contributions up to 1,800, at most `av_kinderzulage` (300) per child whose Kindergeld the
  person receives in a month of the year (`Person.kindergeld_in`: `kindergeld` and `until`, rule
  `children`; `carry.depot` too); none below the 120 € minimum. Old Riester contracts:
  issue #10.
- Migration `to_5` (rule `migrations`; owner 2026-10-14): `fund_policy` loses `deductible`; a
  policy that only `deductible: true` payments fund, and that can be one, becomes a Basisrente
  with a comment. A payment into any other policy without `basisrente`, also one that a payment
  without the flag funds too, stops it, and `FUNDING` names the event: the user marks the
  Basisrente or removes the event.
- Gaps: Werbungskosten of a rent beyond rule `rental`; `deduct: work` is of the Arbeitslohn only (a
  business holds its costs in its profit); the commute's 4,500 € cap, Verpflegung, doppelte
  Haushaltsführung (typed into the yearly euros); the donation carry (§10b Abs. 1 S. 9),
  §34g (parties), a Stiftungsstock (§10b Abs. 1a); §35a Abs. 1 (a Minijob at home) and Abs. 2 S. 2
  (care), two single people sharing the caps (Abs. 5 S. 4); the Berufseinsteiger-Bonus (§84 S. 2);
  the Zulage for at most two contracts (§10a Abs. 5); capital above the subsidized cap (§22 Nr. 5
  S. 2); an own after-tax contribution to a company pension; a Basisrente with BU cover (§10 Abs. 1
  Nr. 2 b bb); the Vorauszahlungen of §37 on the deductions.
- Tests: `tests/test_deductions.py` (relations: the costs above the Pauschbetrag and by the salary
  months, dated costs on top and beyond the salary, also without one, a loss that carries, ALG1
  unchanged, a donation up to its cap without carry, `deductible`, `scale` and the cut,
  §35a, childcare by the months and its cap, the premium against a `fund_policy`, the share of a
  Basisrente and its KV, the refusals, two depots, the Kinderzulage), the law in amounts in
  `test_tax.py` (dated costs, the ALG1 of §32b without a jump), the trade credit beside a rental
  loss and the refund after the pot in `test_rental.py`, `rich_plan` (the costs, a donation,
  household services, a course of 30,000 € in 2030 without a salary: rule `rental`) and `gkv_plan`
  (a premium in `work`) of `test_golden.py`, `to_5` in `test_schema.py`.
