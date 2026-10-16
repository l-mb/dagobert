---
paths:
  - "src/dagobert/{tax,sv}.py"
  - "src/dagobert/engine/*.py"
  - "src/dagobert/holdings.py"
  - "src/dagobert/data/tax/*.yaml"
  - "src/dagobert/data/grunderwerbsteuer.yaml"
  - "tests/test_{tax,sv}.py"
  - "tests/test_{engine,income,portfolio,harvest}.py"
  - "tests/test_golden.py"
---

# Tax and social insurance

The tax and SV law of the engine, with its sources. A business: rule `self-employment`; a company
pension, the salary conversion: rule `bav`; the KV and PV beyond a salary, the PV rate, the KVdR:
rule `gkv`; the church tax, the own Zusatzbeitrag: rule `tax-options`; a let property, its AfA and
§10d: rule `rental`; the Werbungskosten above the Pauschbetrag, the Sonderausgaben, §35a, the
Basisrente and the Zulage per person: rule `deductions`; the children (Kindergeld, §31, §24b, the
child-raising years): rule `children`; Krankengeld, the EM-Rente, a BU policy: rule `disability`;
the Erbschaftsteuer: rule `estates`; the harvest: rule `harvest`; the engine: rule `engine`. Inputs:
`docs/manual/configuration.md`; in plain English, change with the law: `docs/manual/models.md`
(the taxes and the simplifications) and `docs/manual/adding-a-tax-year.md` (the year file, its
sources, the tests).

- `src/dagobert/tax.py`: the income and capital tax, `sv.py` the social insurance (the SV of a
  salary and of a business, the KV and PV, the PKV subsidies, the salary conversion, the pension
  and ALG1), on top of `tax`. `TaxYear` holds the legal constants of a year, loaded by `for_year` from `src/dagobert/data/tax/<year>.yaml` (comments there name the
  sources). A new year is a new file, no code change. `Assumptions.tax_year` is the year:
  `tax.year`, else the newest file (`model.taxes.TAX_YEARS`) up to the year of `start`, the oldest when
  none is (`model.taxes.default_tax_year`, also the fallback that the Assumptions page shows). The
  constants apply in euros of the start (below), so a later file must not serve a plan that starts
  earlier. Every function takes its `TaxYear`, no default and no year in the code: the
  engine passes `Core.ty`, the Cashflows sheet `tax.for_year(a.tax_year)`. The test plans start
  in 2026 and the tests pin `TY = for_year(2026)`, so a new year file changes no test; the fixture
  `later_tax_year` copies every year file and writes 2026 with a change as the year after the
  newest, so a relation test sees that a year reaches a call.
- The functions of `tax.py` and `sv.py` take floats or arrays and always return arrays
  (`test_tax.test_a_float_gives_an_array_and_an_array_one_value_per_path`). Never loop over paths.
- Tax and SV rules are applied in start-year euros. The engine deflates by the path's price level
  of the calendar year (`engine.core.year_levels`: the mean CPI of its months, 1 in the start year)
  before calling `tax.py` or `sv.py` and inflates the result. This stands in for constants that are indexed
  each January. Every flow of a year and its December settlement convert at the same level, so the
  nominal tax of a year is the start-year tariff at that level.
- Salary: SV on the month's total gross: the regular salary up to the monthly BBG, a one-off payment
  on top up to what the BBG of the salary months of the year leaves (§23a SGB IV, without the
  Märzklausel). Pension points follow the RV base. Withholding on the regular monthly salary as if
  paid all year, including the PKV Vorsorgepauschale, and on a bonus as a sonstiger Bezug (the tax
  of the year with it less without it, §39b Abs. 3 EStG). A severance is withheld in full as a
  sonstiger Bezug on the salary of the year so far: since 2025 only the assessment applies the
  Fünftelregelung (§39b Abs. 3 S. 9 EStG repealed by the Wachstumschancengesetz). The December
  settlement then refunds the difference, in reality it comes with the assessment of the next year.
  The December settlement applies the income tax tariff, Soli and the PKV deduction
  (`tax.health_deductible`: the `deductible` share of each premium part, less the whole tax-free
  subsidy of employer, Agentur or DRV, §10 Abs. 2 S. 1 Nr. 1 EStG, BFH IX R 43/13). ALG1 in the
  severance year raises the rate in both steps of the Fünftelregelung and, with a negative zvE,
  joins the fifth in full (R 34.2 EStR, BFH IX R 23/11). It also covers the Fünftelregelung on
  severance (with a negative zvE per §34 Abs. 1 S. 3), ALG1 with Progressionsvorbehalt and the
  pension. The pension taxable share follows the start year for the first two years; the tax-free
  part of the first full year is then frozen as a nominal Rentenfreibetrag, so later increases are
  fully taxable. Werbungskosten: 1,230 against salary (or more, rule `deductions`), 102 against the
  pension. Altersvorsorgeaufwand (own GRV share, voluntary contributions, Basisrente premiums) is
  deductible up to the Höchstbetrag of 30,826 less the employer GRV share (§10 Abs. 3 EStG).
- Capital: Abgeltungsteuer with Pauschbetrag on realized gains and the Vorabpauschale, of a fund
  after its Teilfreistellung (§20 InvStG; `capital_gains_tax` takes the taxable amount):
  `EquityAsset.teilfreistellung`, else `tax.teilfreistellung`; 0 for shares, which still owe the
  Vorabpauschale: the pool is total return, it stands in for their dividends and is credited at the
  sale (§19 Abs. 1 S. 3). The depots are one pool, `Core.equity`, with `taxable_share` (of its value
  after the Teilfreistellung of each depot) and `taxable_basis`: `taxable_gain`, equity × share −
  basis, is the sum of each depot's gain after its rate, exact as all earn the one return (a blended
  rate on the plain basis taxes the wrong gain once their gain shares differ). `_buy_equity` buys at
  the rate of the depot that a savings plan names (`into`), else the default, `_sell_equity` a slice
  of every depot (no sale names one), `_write_off` takes the asset's part out of both (the start
  value at the index ignores the sales since: the share is clipped). The Vorabpauschale is taxed at
  December's share, the taxable basis grows by that part (§19 Abs. 1 S. 3, 4). A loss (a year of
  interest below zero, a sale of equity below its pooled basis) goes into the general loss pot,
  which offsets later capital income before the Pauschbetrag and carries over the years (§20 Abs. 6
  EStG, `Core.losses`). Term deposit interest is taxed in the maturity month, without
  Teilfreistellung, after what is left of the Pauschbetrag. Until then the deposit counts with its
  accrued interest, and the tax on that interest is part of the latent tax. The return on cash and
  the fixed-income bucket is summed over the year, losing months offset it, and the December
  settlement taxes a positive sum the same way. The Vorabpauschale takes the January price and the
  growth of the equity index over the year as cap (§18 Abs. 1 InvStG) on the units held at the end
  of the year (BMF 2019-05-21 Rz. 18.4), in January euros; a unit bought in the year counts (13 −
  month)/12 of it (§18 Abs. 2, Rz. 18.11: bought in July, 6/12). `Portfolio._buy_equity` is the one
  purchase (the surplus, the rebalancing, `invest`, a savings plan), at the price of now
  (`eq_price`: before the month's return for an event, after it for the rest): `YearAcc.bought` and
  `weighted`. `_vorab_base` splits the units of December FIFO (§20 Abs. 4 S. 7 EStG): `jan_units =
  clip(units − bought, 0, equity_jan)` since January, the rest the purchases by their weighted
  share. Sales beyond the January units shrink the purchases pro rata, not oldest first. The surplus
  invested in December comes after the settlement: it carries no twelfth; a savings plan buys before
  it and does. Gains keep the pooled basis: FIFO lots per path would cost a loop per sale. Gaps of
  the funds: the Vorabpauschale of X counts in X+1 (§18 Abs. 3: Pauschbetrag, Günstigerprüfung,
  GKV), the engine books it in December of X; a loss on shares offsets only gains on shares (§20
  Abs. 6 S. 4 EStG), the engine pools it (issue #12); Ausschüttungen; a
  bond ETF stays `fixed_income`, taxed yearly; a Dachfonds (§2 Abs. 5, Abs. 6 S. 2–3 InvStG), a
  change of class (§22, §20 Abs. 4), §20 Abs. 5. The Basiszins stays the constant of the tax year:
  its effect is timing (§19 Abs. 1 S. 3). Günstigerprüfung in December refunds the difference to
  the tariff of the year, with the Progressionsvorbehalt, the Fünftelregelung and the route of an
  Altersvorsorgedepot on both sides (§32d Abs. 6 EStG; `tariff_of` in `tax.year_settlement`). A sale
  that pays the December bill joins it: the engine repeats the settlement, pays the change and
  covers again until no path owes a cent more, so a §23 gain of that sale is paid in its year.
- Private Veräußerungsgeschäfte (§23 EStG): a gain is taxable when the sale comes at most
  `private_sale_months` (12) after the purchase. `tax.private_sales` takes the net of a year (its
  losses offset, Abs. 3 S. 7) and the losses carried from earlier years. A net gain below
  `private_sale_freigrenze` (1,000 since 2024, strictly below, Abs. 3 S. 5) is free and leaves the
  carried losses unused. A larger one is taxable less them, also where they push it below 1,000: the
  Freigrenze is checked before the loss carryforward or carryback (BMF 2004-10-25, BStBl I S. 1034,
  Tz. 52; BFH IX R 27/04; FG München 1 K 2045/06). A net loss joins the carried losses (Abs. 3 S. 8,
  `Core.private_losses`). The engine sums the year in `YearAcc.private_sales`, in start-year euros,
  so the Freigrenze grows with the prices, and the settlement adds the taxable part to the other
  income (tariff, Soli, no withholding). It holds the signed gain of a taxable property sale and of
  gold and crypto sold within the holding period: a unit bought in month P is free from month P +
  13, so a sale counts up to a month longer than the law says. The fees of a trade and the `costs`
  of a sale count. The engine sells the oldest units first, for the period and the gain: the BMF
  allows it for crypto (2025-03-06 Rn. 61), for gold it is an assumption. A gold note without
  backing (`tax: capital`, §20 Abs. 2 S. 1 Nr. 7, BMF 2025-05-14 Rn. 57) and crypto bought in or
  after `tax.crypto_capital_from` (the BMF draft of 2026-09-30) pay the flat tax at the sale,
  without Teilfreistellung and without Vorabpauschale, a loss into `Core.losses`; their gain counts
  in the latent tax, that of the young §23 units does not.
- A property of a `buy_property`: a `taxable` sale counts up to `property_sale_months` (120) after
  the purchase month (§23 Abs. 1 S. 1 Nr. 1 S. 1; the month rule of gold), its basis `bought_for`
  the price with tax and costs (Abs. 3 S. 1). One of `assets.yaml` counts from its `bought`, without
  it `taxable` alone decides; `taxable` means "not own use" (S. 3: a home of its owner leaves it
  off). The basis less the AfA taken (Abs. 3 S. 4) and the penalty of a repayment: rule `rental`.
  Left out: a use that changes (BMF 2000-10-05, BStBl I S. 1383; BFH IX R 37/16). The
  Grunderwerbsteuer (`model.taxes.transfer_tax_rate`, `BuyPropertyEvent.transfer_rate`): the rate of
  `land` on the day of the purchase from `src/dagobert/data/grunderwerbsteuer.yaml` (per Land rows
  `since`, `rate`: 3.5% of §11 Abs. 1 GrEStG from 1997, then the Länder, Art. 105 Abs. 2a S. 2 GG;
  sources in its comments), not from the tax year: a Land changes it on any day. In `model/taxes.py`
  beside `TAX_YEARS`: the check of the loan needs it. `transfer_tax` replaces it (§3 Nr. 4, 6: 0
  between spouses and relatives in a direct line). Base: the whole `price` (§8 Abs. 1, §9 Abs. 1
  Nr. 1). Left out: movables such as a kitchen, rounding (§11 Abs. 2), the due date (§15).
- Pension points: salary months add the RV base (a conversion lowers it, rule `bav`) over the
  Durchschnittsentgelt, ALG1 months 80% of that, `rv_voluntary` streams buy points. All of them
  count as Versicherungszeit on top of `person.rv_since`. `rentenwert` (§1 RWBestV): rule `examples`.
- An Altersvorsorgedepot takes its `contribution` from cash each December of a year with a salary
  or ALG1 month (compulsory GRV insurance, §10a EStG; the ALG1 months assume the insurance on
  application) or a running business (rule `self-employment`), plus the Zulage into the depot, once
  per person (rule `deductions`). The settlement deducts contributions up to 1,800 plus the
  Zulage where that saves more than the Zulage, and the tax then rises by the Zulage (§10a Abs. 2).
  No tax inside. From the start of the pension (at the Regelaltersgrenze without one) it pays
  `lump_sum` of the value at once and the rest as an Auszahlplan until `until_age`, both taxed as
  other income (§22 Nr. 5 EStG, no Fünftelregelung). It counts in `total`, not in `liquid`. Death
  and a harmful use are not modelled.
- bAV policies and the salary conversion (Entgeltumwandlung): rule `bav`.
- Pension claim: a claim needs age 67, or 63 with 35 years (0.3% Abschlag per month), or
  65 with 45 years. Ages count in whole months. A birthday after the first of the month
  reaches an age in the following month, so the pension starts there. When a claim is possible, the pension starts with the phases
  of its stream. Otherwise the engine defers to 67 and adds a marker. An EM-Rente: rule `disability`.
- ALG1 (`sv.alg1_month`) pays 60% (67% with a child) of the Leistungsentgelt of 30 days
  (§§149, 151, 153, 154 SGB III): the BBG-capped last salary per day (times 12, over 365), less 20%
  for the SV, less the Lohnsteuer and Soli of a day, 1/360 of the year's (§39b Abs. 2 S. 9 EStG)
  in Steuerklasse I: Arbeitnehmer- and Sonderausgaben-Pauschbetrag, the Vorsorgepauschale of a GKV
  member at the reduced KV rate plus the average Zusatzbeitrag, PV at the base rate, the ALV part
  within 1,900 € with KV and PV (§153 Abs. 1 S. 4; §39b Abs. 2 S. 5 Nr. 3 e). It is the same for a
  PKV member. `test_alg1_month_matches_the_bundesagentur` pins the Selbstberechnungsprogramm of
  the Bundesagentur (pub.arbeitsagentur.de) for 2026 to 1 € a month; the former stand-in (the
  tariff on 80% of the salary) paid 3% too much at the BBG. The engine keeps that salary nominal
  and applies the rules at the price level of the year of entry. The amount is fixed in nominal
  euros in the first ALG1 month and does not follow the CPI. The duration follows the age at entry
  and payments stop by themselves. The phase of the ALG1 stream can be longer than the ALG1
  duration. The Agentur pays the PKV premium up to a cap. A child that counts: rule `children`.
- PKV subsidies follow what the month pays and its insurance (`Core.pkv`, rule `gkv`), never the
  phase (`Income._health_support`). The employer (`sv.employer_pkv_subsidy`): 8.75% (`kv_half`) and
  1.8% (`pv_rate`, its half, §58 Abs. 1 SGB XI) of the KV base of the salary (`sv.sv_bases`: up to
  the KV-BBG, a one-off within what the BBG of the year leaves), at most half of the KV and PV
  premium (§257 Abs. 2 S. 2 SGB V, §61 Abs. 2 S. 2 SGB XI): 508.59 and 104.63 at the BBG in 2026,
  none without a salary. Instead the Agentur, while an ALG1 stream pays within the entitlement
  (`Income._on_alg1`): the whole premium (caps 813.75 KV, 167.40 PV: the rates on 80% of the
  KV-BBG). The DRV: 8.75% of the sum of the pensions, at most half of the KV premium: half of 14.6%
  plus the average Zusatzbeitrag of the year, 2.9% in 2026 (§106 Abs. 3 SGB VI; DRV brochure
  `Rentner und ihre Krankenversicherung`, 2/2026; a DRV notice of 2026-03-23 still named the 8.55%
  of 2025). A salary beside a pension gets both, up to the whole premium: §257 Abs. 2 and §106 Abs.
  3 hold no joint cap, §106 Abs. 1 S. 2 excludes only GKV-Pflichtversicherte. The PV part is the sum
  of the `health: pv` streams. Caps are in start-year euros, the engine deflates the premium first.
- Known gaps: Sperrzeit and Ruhen (§§ 158, 159 SGB III) are not modelled, a scenario avoids them
  through the phase dates (for example a year without salary before the phase of ALG1). The ALG1
  reference salary is the sum of the monthly (`every: 1`) salary streams in the last month that paid
  one, however long ago. The gaps of the deductions: rule `deductions`; of the children: rule
  `children`. A payment counts in the tax year of the month that pays it: a bonus
  that the employer books into an earlier tax year (Märzklausel) needs a one-off salary in the month
  of the booking. The employer's cap of half the premium holds per month; for a one-off the practice
  spreads it over the §23a period (Haufe, Beitragszuschuss 5.1), so a bonus on a salary below the
  BBG gets less. Every salary counts as an employment with the subsidy: a Minijob gets none (§7 SGB
  V), and the reduced rate without Krankengeld (§257 Abs. 2 S. 3), Kurzarbeit and partial months are
  left out. A month with a salary and ALG1 gets the Agentur's share only. The Agentur's caps hold
  for a reference salary at or above the KV-BBG (§232a Abs. 1 S. 1 Nr. 1 SGB V: 80% of it, else
  less). The PV split of Saxony is left out: there the employee bears 1 point alone (§58 Abs. 3 SGB
  XI), so the employer's share and its PKV subsidy (§61 Abs. 2 S. 2) are 1.3% in 2026, not 1.8%.
  Negative income of a year (rule `rental`) and §23 losses carry forward only: the carryback into
  the year before (§10d Abs. 1) is optional, so leaving it out errs towards more tax. The carried
  §23 losses offset a year's §23 gain in full. The Mindestgewinnbesteuerung of §10d Abs. 2 (BMF
  2004-11-29, BStBl I S. 1097) lets them offset only 70% of the part of a year's §23 gain above 1
  Mio. € (60% from 2028). Gold and crypto leave out: income from staking and lending (§22 Nr. 3
  EStG, Freigrenze 256 €, BMF 2025-03-06 Rn. 65 ff.; its coins are new purchases, Rn. 54), gold lent
  against interest (ten years, §23 Abs. 1 S. 1 Nr. 2 S. 4), a swap of coins, which starts a new
  period (Rn. 55; a scenario writes a sale and a `buy`). A fund that holds gold or Bitcoin (§20
  through the InvStG, BFH VIII R 15/18) is `equity` with `teilfreistellung: 0`: its growth follows
  the equity class. One person: spouses have a Freigrenze each.
