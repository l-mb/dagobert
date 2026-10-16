---
paths:
  - "src/dagobert/{tax,sv}.py"
  - "src/dagobert/engine/{income,settlement}.py"
  - "src/dagobert/model/assumptions.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_children.py"
  - "tests/test_golden.py"
---

# Children

The children of the person: the Kindergeld that the engine pays, the check of §31 EStG against
the allowances, the base of the Soli and the church tax, the Entlastungsbetrag, ALG1 at 67%, the
PV surcharge up to the first birth, the child-raising years of the pension. One person, the
parent (owner): nothing splits between two parents. Law checked at gesetze-im-internet.de on
2026-10-13. The rest of the tax law: rule `tax`; the GKV and the PV: rule `gkv`; childcare and the
Kinderzulage: rule `deductions`; the migration: rule `migrations`. The inputs:
`docs/manual/configuration.md`, in plain English `docs/manual/models.md` (`Children`).

## Inputs

- `person.children_born`, `model.assumptions.Child`, all optional but `born`: `until` (a `Month`,
  the first month without the child, exclusive as `Stream.end`; default `Child.end`: the month
  after the last one at whose start the child is under 18, §32 Abs. 3 EStG, so a birth on the 1st
  ends a month earlier, the arithmetic of `months_of_age`; at most the same at 25, Abs. 4 S. 1 Nr.
  2: `Child._until_while_a_child` refuses one in or before the month of birth or later, at
  `until`), `kindergeld` (default true: the engine pays it), `freibetrag` (`model.taxes.Allowance`,
  `half` or `full`: both halves on transfer, §32 Abs. 6 S. 6), `erziehung` (default true: the
  parent in the plan raised the child, owner Q1). `CHILD_AGE` and `EDUCATION_AGE` are literals of
  the model, which reads no tax year. `Person.counting(month)` (`Child.counts`: born by the month,
  `until` not reached, oldest first), `kindergeld_in(year)` (the Kinderzulage), `parent(month)`
  (the PV). `children` stays the count of all children, grown ones too, for the PV surcharge.
- `tax.alleinerziehend` (`TaxOptions`, default false): the Entlastungsbetrag (owner Q2).
- A scenario that adds a child overrides `person.children_born` (a list replaces the list,
  `loader.deep_merge`: it repeats the rows) and `children`: no `birth` event, so a `shift` moves no
  birth. The explorer has no slider. Example: `sabbatical` of `engineer` (rule `examples`), with
  the Elterngeld of the notice as a `taxable: false` stream (Elterngeld by rule: issue
  #3).

## Engine

- Kindergeld (§66 EStG: 259 € in 2026, from the month of birth): `Income._pay_kindergeld`, after
  `_pay_streams`, `kindergeld_month` per child that counts with `kindergeld`, at the deflator like
  every constant (the law raises it in steps). Ledger `source`, group none, item `KINDERGELD`
  (`result.py`, German already): the Cashflows sheet shows it among the rows of the run, the Flows
  page as a source. No tax, no GKV (BVSzGs Katalog), outside `_record_earned`.
- The settlement (`Settlement._child_years`, `tax.ChildYear`): per child the months of the year in
  the run in which it counts (§32 Abs. 6 S. 5: a twelfth each), with `full`. `ChildYear.allowances`
  is a twelfth of `kinderfreibetrag` and `betreuungsfreibetrag` per month (3,414 and 1,464 per
  parent, twice with `full`), `kindergeld` the claim of those months, half of it with `half` (§31 S.
  4: in the extent of the Kinderfreibetrag), whatever `kindergeld` says.
- §31 (`tax._with_children`, per child, oldest first, R 31 Abs. 1 S. 3 EStR): the allowances come
  off the zvE where the tariff with them plus the Kindergeld of the child costs less than without,
  each tariff the cheaper route of the Altersvorsorgedepot (§10a Abs. 2), compared before the
  credits (§31 S. 4 compares the tarifliche Einkommensteuer plus the Kindergeld; §2 Abs. 6 S. 1
  takes the credits off and S. 3 adds the Kindergeld only afterwards); the winning zvE then takes
  the credits of §35 (at most its share of that tariff) and §35a in `_credited`, and the tax adds
  the Kindergeld of the children whose allowances came off (§2 Abs. 6 S. 3). Per child, not one
  joint min: two half children at a zvE of 45,500 pay 8,961, the joint min 9,001. The half
  allowances (4,878) against the half Kindergeld (1,554) win from a zvE of 43,050 in 2026 (a
  marginal rate of 31.9%).
- The Soli and the church tax take the tax of the zvE less every allowance, whichever wins (§3
  Abs. 2 SolZG, §51a Abs. 2 S. 1 EStG): `year_settlement` calls `_credited` once more for that
  base. The Günstigerprüfung of the capital income runs the same check on its zvE and its
  `guenstigerpruefung(bases=)` counts the Zuschlagsteuern on those bases.
- Entlastungsbetrag (§24b): with `alleinerziehend`, `tax.entlastungsbetrag` over the months of the
  year in the run: a twelfth of `entlastungsbetrag` (4,260) and of `entlastungsbetrag_more` (240)
  for each further child per month with a child that counts (Abs. 2, 4), `YearIncome.entlastung`.
  `tax.zve` takes it off the Summe der Einkünfte, at most down to 0 (§2 Abs. 3: it makes no loss
  for §10d), before the Sonderausgaben and the harvest room of rule `harvest`.
- ALG1 (§149 SGB III): 67% when a child counts in the first month of the claim (`Alg1._open_alg1`,
  `sv.alg1_month(child=)`; the Cashflows estimate takes the month after its salary), else 60%. A
  child without a date counts for nothing (owner Q4).
- PV (§55 Abs. 3 SGB XI): the surcharge for the childless until the first birth (`Person.parent`:
  a child without a date, a grown one, or one born by the month). The discount: rule `gkv`.
- Child-raising years (`Income._raise_children`, after `_pay_profit`): for a child with
  `erziehung`, in each of the `kez_months` (36) after the month of birth (§56 Abs. 5 SGB VI)
  `kez_points_month` (0.0833, §70 Abs. 2 S. 1) on top of the points of the month (salary, ALG1,
  voluntary and business contributions: `points` before `_apply_streams`) up to the Höchstwert of
  Anlage 2b, `sv_bbg_month / durchschnittsentgelt` (no constant), per child: two children in the
  same months both credit, up to the cap (§56 Abs. 5 S. 2 extends the time instead, a gap). Such a
  month sets `YearAcc.compulsory` (§3 S. 1 Nr. 1 SGB VI: pflichtversichert, as §10a EStG asks). Each
  month with such a child under `beruecksichtigung_age` (10) counts as insured (§57; §51 Abs. 3,
  3a: for the 35 and the 45 years). Months before `start` count only through `points` and
  `rv_since` of the Renteninformation: a child born before the start gets the rest of its 36. A
  pension stream with `gross` ignores the points of the run.

## Constants of the year file

`kindergeld_month`, `kinderfreibetrag`, `betreuungsfreibetrag` (per parent), `entlastungsbetrag`,
`entlastungsbetrag_more`, `kez_months`, `kez_points_month`, `beruecksichtigung_age`; in start-year
euros at the price level of the year like every constant (rule `tax`). The ages 18 and 25 are in
the model.

## Gaps

Elterngeld by rule (a `taxable: false` stream of the notice; its Progressionsvorbehalt, §32b Abs. 1
S. 1 Nr. 1 j EStG, is left out; issue #3). The Kinderzuschlag, a child abroad, a disabled
child (§32 Abs. 4 S. 1 Nr. 3, no age limit), a child registered unemployed to 21 (Nr. 1): set
`until`. The withholding: the monthly Soli and church tax of the Lohnsteuer take the
Kinderfreibetragszähler (§51a Abs. 2a, §3 Abs. 2a SolZG), Steuerklasse II the Entlastungsbetrag;
the December settlement refunds both, a gap of timing. The ALG1 Leistungsentgelt without the
allowances. The Zuschlag of §70 Abs. 3a SGB VI, the extension of §56 Abs. 5 S. 2 for a second child,
the Mütterrente of births before 1992 and the months before `start` (all in `points` and
`rv_since`). A `shift` of a scenario moves no birth. Couples: nothing splits between two parents.

## Tests

`tests/test_children.py` (relations: the Kindergeld by the months, the allowances above and below
the threshold, `full`, the church tax with the Kindergeld winning, the Entlastungsbetrag, ALG1, the
PV surcharge, the points up to the Höchstwert, the 35 years, `until`), the law in amounts in
`test_tax.py` (the threshold of 43,050, two children, the route of §10a, the credits, the bases of
the Soli and the church tax, the Entlastungsbetrag), `rich_plan` of `test_golden.py` (a child born
2015 to 2040, `half`: the allowances, the bases, the Kindergeld, ALG1 at 67%, the Kinderzulage), the
Kinderzulage in `test_deductions.py`, `to_6` in `test_schema.py`.
