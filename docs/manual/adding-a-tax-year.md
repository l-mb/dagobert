# Adding a tax year

This page is for contributors. It tells you how to add the legal values of a new tax year.

## How the tax year works

The legal values of one year are in one YAML file: `src/dagobert/data/tax/<year>.yaml`. Today
only `2026.yaml` exists. The comments in the file name the law or the source of each value.

The field `tax.year` in `assumptions.yaml` selects the file. It takes only a year that has a file.
The simulation applies the values of that one year to the whole plan. The amounts of the plan are
in euros of its `start` month, and the simulation reads the values of the file in the same euros.
It raises them with the consumer prices of each path, as if the law adjusted them every January.
It does not change to the file of a later year when the simulated years pass. The values of the
Erbschaftsteuer are the one exception: they stay nominal, because the law kept them unchanged
since 2009.

Without the field, the plan takes the newest file whose year is at most the year of `start`. If no
file is that old, it takes the oldest file. So a new file serves the plans that start in its year
or later, and a plan that starts earlier keeps its file. A roll forward into a new year takes the
file of that year, if it exists.

A new year is a new file. It needs no change of the code, as long as the law changes only amounts
and rates. Each function in `src/dagobert/tax.py` and `src/dagobert/sv.py` (the social insurance)
gets the values of the year from its caller, and each caller passes the year of the plan
(`Assumptions.tax_year`). If the law changes a rule, for example a new zone of the tariff, the code
in these files must change too, with its tests.

## Steps

1. Copy `src/dagobert/data/tax/2026.yaml` to a file with the new year as its name, for example
   `2027.yaml`.
2. Set `year` in the new file to the new year. The app refuses a file whose `year` differs from its
   name.
3. Update each value from its source. The list below names the sources.
4. Update the comments: name the law, and the date of each letter of the Federal Ministry of
   Finance (BMF-Schreiben) that you used.
5. Make sure that the values that follow from others still agree. The caps of the health insurance
   subsidy of the employment agency follow from the contribution ceiling and the rates. The
   subsidy of the employer has no caps in the file: the simulation computes it from the rates and
   the salary.
6. Copy the example data to `tmp/rt`, set `tax.year` in its `assumptions.yaml`, and run a
   scenario of it with the model `fixed`:

   ```sh
   uv run dagobert run --data tmp/rt --model fixed tmp/rt/scenarios/plan.yaml
   ```
7. Run the tests and the code checks (see below).

The Grunderwerbsteuer is not in the year file. Its rate changes per Bundesland on any day, and
the simulation takes the rate of the day of a purchase. The rates are in the table
`src/dagobert/data/grunderwerbsteuer.yaml`, a list of rates with the day from which each holds
for each Land. If a Land changes its rate, add a row with the new day and rate, and name the law or
the source in a comment. Source: §11 GrEStG and the Grunderwerbsteuer law of the Land.

## The values and their sources

- The income tax tariff: `grundfreibetrag`, the ends of the zones and their factors. Source: §32a
  EStG in the version of the year.
- The solidarity surcharge: its rate, its exemption limit and the rate of the transition zone.
  Source: §§3 and 4 SolZG.
- Capital income: the rate of the flat tax before the Soli and the church tax
  (`abgeltungsteuer_rate`), and the base rate (`basiszins`) for the Vorabpauschale. Source:
  §32d EStG, and the BMF-Schreiben on the base rate that comes out each January (§18 InvStG).
- Church tax: the rate of each Land as a share of the income tax (`kirchensteuer`, all 16
  Länder). Source: the Kirchensteuergesetze of the Länder and the overview of the rates of the
  EKD (kirchenfinanzen.de).
- Private sales: the holding period of gold and crypto (`private_sale_months`), the holding
  period of land and buildings (`property_sale_months`, 120 months) and the exemption limit.
  Source: §23 EStG.
- Social insurance: the employee rates of pension, unemployment, health and care insurance. Also
  the half of the reduced health insurance rate (`kv_rate_reduced`), the half of the average
  additional contribution (Zusatzbeitrag), and the monthly contribution ceilings. Source: the
  Sozialversicherungs-Rechengrößenverordnung of the year, §243 SGB V, and the average Zusatzbeitrag
  that the Federal Ministry of Health announces in the Bundesanzeiger.
- Care insurance: the surcharge for the childless, and the discount for each child under 25 with
  its limits. Source: §55 Abs. 3 SGB XI.
- Deductions: the flat work expenses, the flat amount against a pension, the flat amount for
  special expenses (`sonderausgaben_pauschbetrag`), the limit of the carryback of a loss
  (`loss_carryback_max`, §10d Abs. 1 EStG) and the ceiling of the pension contributions.
  Also the limit of the unemployment insurance part in the Vorsorgepauschale of the wage tax
  (`vorsorge_alv_cap`), and the default share of a private health premium that is deductible.
  Source: §9a, §10 Abs. 3, §10c and §39b Abs. 2 EStG. The share and the limit per child of the
  childcare costs (`childcare_share`, `childcare_max`) and the age of the child
  (`childcare_age`), the share of the income up to which donations count (`donation_share`), and
  the credit of household services and of a craftsman (`haushalt_credit`: the rate and the two
  limits). Source: §10 Abs. 1 Nr. 5, §10b Abs. 1 and §35a EStG.
- Private health insurance subsidies: the largest share of the premium that the employer and the
  pension insurance pay, and the share and the caps of the employment agency. Source: §257 SGB V,
  §61 SGB XI, §174 SGB III, §106 SGB VI.
- Unemployment benefit (ALG1): the shares, the number of months by age, and the days of a year,
  of a month and of the wage tax year. Source: §§147, 149, 151, 153 and 154 SGB III, and §39b
  Abs. 2 EStG. The rules of the claim: the days of a Sperrzeit and the share that it takes, the
  rate, the floor and the months of a course, and the years in which a rest pays. Source: §§148,
  159, 161 and 339 SGB III. To make sure that the values are correct, compare `sv.alg1_month` with the
  Selbstberechnungsprogramm of the Bundesagentur für Arbeit (pub.arbeitsagentur.de). Select the
  new year there. The two results must agree to about 1 euro per month.
- Statutory pension: the average salary (`durchschnittsentgelt`), the pension ages, and the
  reduction and the increase per month. Also the taxable share of a pension that starts in the new
  year (`pension_share` and `pension_share_start_year`). Source: SGB VI, the
  Sozialversicherungs-Rechengrößenverordnung and §22 Nr. 1 EStG. The file also holds the value of
  a pension point from July of the year (`rentenwert`). The quick start of the app writes it into a
  new plan. Source: §1 of the Rentenwertbestimmungsverordnung of the year, which comes out in June.
- The loss of the ability to work: the months of salary after the onset (`efzg_months`), the share
  and the cap of the sick pay (`krankengeld_rate`, `krankengeld_net_cap`), the month of the start
  of the disability pension (`em_start_months`), the months of insurance and of compulsory
  contributions that it needs (`em_wartezeit_months`, `em_pflicht_months`, `em_window_months`), the
  ages of its reduction (`em_reference_age`, `em_floor_age`), and the table of the end of the
  Zurechnungszeit by the year of its start (`zurechnung_end`, in months of age; the last row holds
  for every later year). Source: §3 EFZG, §47 SGB V, §§43, 50, 77, 101 and 253a SGB VI. The
  taxable share of a disability insurance by the years of its contract (`ertragsanteil_by_years`,
  keyed by the last year of each row). Source: §55 Abs. 2 EStDV. `tests/test_tax.py` and
  `tests/test_sv.py` test them with the values of 2026.
- Altersvorsorgedepot: the subsidy and its limits, and the limit of the grant per child
  (`av_kinderzulage`). Source: §§10a, 84, 85 and 86 EStG.
- Children: the Kindergeld of a month (`kindergeld_month`), the two child allowances of one parent
  (`kinderfreibetrag`, `betreuungsfreibetrag`), the Entlastungsbetrag of a single parent and its
  increase for each further child (`entlastungsbetrag`, `entlastungsbetrag_more`). Source: §66
  Abs. 1, §32 Abs. 6 and §24b Abs. 2 EStG. The manual states the amounts of 2026 (259 €, 4,260 €
  and 240 € in `models.md` and `configuration.md`): change them too. The child-raising years: the
  months after the birth (`kez_months`), the pension points of a month (`kez_points_month`) and
  the age up to which the months count as insured (`beruecksichtigung_age`). Source: §§56, 57 and
  70 Abs. 2 SGB VI. The ages 18 and 25 of §32 EStG are part of the code.
- Company pension: the shares of the contribution ceiling of the pension insurance up to which a
  salary conversion is free of income tax (`bav_tax_free_share`, 8%) and of social insurance
  (`bav_sv_free_share`, 4%), and the subsidy of the employer (`bav_subsidy`, 15%). Source: §3
  Nr. 63 EStG, §1 Abs. 1 Nr. 9 SvEV and §1a Abs. 1a BetrAVG.
- Self-employment: the monthly Bezugsgröße (`bezugsgroesse_month`), the Geringfügigkeitsgrenze
  (`geringfuegigkeit_month`), and the years and the share of the half pension contribution after
  the founding (`rv_founding_years`, `rv_founding_share`). Source: the
  Sozialversicherungs-Bezugsgrößenverordnung of the year (SvBezGrV), §8 Abs. 1a SGB IV with the
  minimum wage of the year, §165 SGB VI. The page `Beiträge` of the Federal Ministry of Health
  (BMG) gives the minimum and the maximum health contribution of a self-employed member.
  `tests/test_sv.py` and `tests/test_health.py` compare the rules with the values of 2026.
- Statutory health insurance beyond a salary: the months over which a lump sum of a company
  pension counts (`versorgung_months`, 120) and the yearly work expenses that a voluntary member
  takes off the capital income (`kv_capital_werbungskosten`, 51 €). The exemption limit of a
  company pension is a twentieth of `bezugsgroesse_month`, which the code computes. The age from
  which a change from the private to the statutory health insurance is usually not possible
  (`gkv_return_age`, 55). Source: §§6, 226 and 229 SGB V, and the Beitragsverfahrensgrundsätze
  Selbstzahler of the GKV-Spitzenverband.
- Trade tax: the exemption amount (`gewst_freibetrag`), the rate of the base amount
  (`gewst_messzahl`) and the multiple of the base amount that comes off the income tax
  (`gewst_credit_factor`). Source: §11 GewStG and §35 EStG.
- Erbschaft- und Schenkungsteuer, in nominal euros: the tax-free amount (`erbst_freibetrag`) and
  the tax class (`erbst_klasse`) of each relation, the limits of the brackets (`erbst_brackets`),
  the rates of each class (`erbst_rates`, one more than the limits), the relief over a limit
  (`erbst_haerte`: the share of the excess at a rate up to `rate` and above it), the costs of an
  inheritance without proof (`erbst_erbfallkosten`) and the rounding of the taxable amount
  (`erbst_rounding`). Source: §§10, 15, 16, 19 ErbStG. `tests/test_tax.py` tests the rules with
  the values of 2026.

## Tests

The tests of the legal rules use the values of 2026: each test file reads them with
`TY = for_year(2026)`. Keep them as they are: they test the rules, and the rules did not change.
The small plans of the engine tests (`tests/builders.py`) and the plan of the golden test
(`rich_plan` in `tests/test_golden.py`) start in 2026, so they keep the file of 2026 and a new file
changes none of them.

Six tests make sure that the year of the plan reaches every calculation. They copy every year file
into a temporary folder and add the year after the newest: the values of 2026 with one change
(the fixture `later_tax_year` in `tests/conftest.py`):

- `test_the_tax_year_of_the_plan_sets_the_sv_bases_and_the_flat_tax` in `tests/test_engine.py`
- `test_a_plan_without_a_tax_year_takes_the_newest_file_up_to_its_start` in
  `tests/test_engine.py`
- `test_the_alg1_estimate_takes_the_tax_year_of_the_scenario` in `tests/test_ui_cashflows.py`
- `test_the_tax_year_sets_the_least_bases` in `tests/test_profit.py`
- `test_the_tax_year_sets_the_months_of_a_lump_sum` in `tests/test_health.py`
- `test_the_tax_year_sets_the_limits_of_a_conversion` in `tests/test_bav.py`

`test_pkv_caps_follow_the_rates` compares the caps of the health insurance subsidy of the
employment agency with the rates of every year file. If the BMF publishes example values for the
tariff of the new year, add a test with them.

Then run the tests and the code checks of the repository:

```sh
uv run ruff check src tests scripts
uv run ruff format src tests scripts
uv run mypy
uv run basedpyright
uv run pytest
```

The app reads the list of tax years from the names of the files, so `tax.year` accepts the new
year at once.
