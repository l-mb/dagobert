---
paths:
  - "src/dagobert/tax.py"
  - "src/dagobert/engine/{core,income,health,events,settlement,simulation,state}.py"
  - "src/dagobert/model/{assets,streams,taxes}.py"
  - "tests/test_rental.py"
---

# Letting and the losses of the income tax

A let property (§21 EStG), its AfA, the Verlustrücktrag and the Verlustvortrag of the income tax
(§10d EStG), with their sources (gesetze-im-internet.de, BFH and BSG, the BVSzGs and Katalog of the
GKV-Spitzenverband, read on 2026-10-13). The rest of the tax law: rule `tax`; the GKV: rule `gkv`;
the run: rule `engine`. The inputs: `docs/manual/configuration.md`, in plain English
`docs/manual/models.md` (`Letting a property`, `A loss of a year`). Individuals only.

- Inputs. `Stream.property` (an asset id) on `other_income` makes the amount a rent of that
  property, on an `expense` without `health` a Werbungskosten of it (§9 Abs. 1 S. 3 Nr. 2: Hausgeld,
  Grundsteuer); `taxable: false` or `health` with it is refused (`Stream._together`), any other
  kind too (`TAKES`). Such a cost is no spending: `Stream.managed` is false, so `scale.categories`,
  the age curve and the
  spending dial and sliders leave it. No kind `rent` and no tag: a tag means "a sale
  ends it". `Loan.finances` (a property id): its interest is a Werbungskosten while that property
  is let (Nr. 1); the `NewLoan` of a `buy_property` finances its property (`LoanState.finances`,
  set by `Events._buy_property`). `PropertyAsset.bought` (a month),
  `building_share` and `afa` (shares), also on `BoughtProperty` without `bought` (the event gives
  it). `afa` is the rate of §7 Abs. 4 S. 1 Nr. 2 by the year of completion (3% after 2022, 2% 1925
  to 2022, 2.5% before 1925; S. 2 a proven shorter life; 0 none), an input: no `built` year, no rate
  table in the tax year files (owner R6). `bought_for` is the cost with GrESt, notary and broker,
  of a purchase `BuyPropertyEvent.cost` (Abs. 3 S. 1: Anschaffungsnebenkosten). The AfA base is
  it times `building_share` (`PropertyState.afa_base`; the land is not depreciated, BMF Arbeitshilfe
  Kaufpreisaufteilung, which BFH IX R 26/19 does not bind).
- The check (`Plan._let_known`): a property that a rent names needs `bought_for`, `bought`,
  `building_share` and `afa` (`0` passes), one of a purchase `building_share` and `afa`: one
  problem of the type `missing` per field, so its key path names it in `assets.yaml` or the event
  (`test_loader`). `Plan._held_at_start`: a `bought` after `start` is refused at the field (the
  AfA and `held` would run before the purchase; a later one is a `buy_property`). A
  cost or a loan alone makes no property let. `property` and `finances` name known properties
  (`_event_checks`), and a stream that names a bought property in or before the month of the
  purchase is the `early` error (`_named_assets`, with `repays`). `references` counts both as uses
  of the asset (`STREAM_USE`, `ASSET_USE`, also in `overrides.events` and `overrides.assets`).
- Let (`Core._let`, per path): a rent of the property is `active` in the month (dates, phases, the
  mask of `after_sale_of` and of a sale; not `_pays`: a rent `every: 12` lets each month, a `factor`
  of 0 is a vacant month) and the property is not sold. Own use is `end_streams` of the rent (owner
  R5). A sale ends the streams whose `property` names it, tag or no tag (`_sell_property`; the
  scheduled changes too, `cashplan._Events._sale`).
- The month (`Core._rent_net`, nominal, per path, pure): of each let property the run rate of the
  streams that name it (rents above zero, costs below) less the AfA of the month
  (`PropertyState.afa_month`: a twelfth of `afa` times the base, at most the base left), the
  interest of its loans (`LoanState.interest`, which `_service_loans` writes before the streams)
  and its `upkeep` of the month. `_stream_flow` books a rent as a source but adds nothing to
  `other_taxable`; `Income._apply_streams` adds `_rent_net() / d` once, and `Health._pay_gkv` takes
  it too, so `_take_afa` advances `PropertyState.afa_taken` once, after `_apply_streams`. A
  property of the file starts with the AfA of the months from `bought` to `start` (`Core._property`,
  capped at the base: let since the purchase, an assumption; an heir enters the testator's
  `bought`, `bought_for` and `afa`, §11d EStDV). The AfA is nominal by law: deflated like every
  flow of its month. The tax takes the run rate (a rent `every: 12` counts 1/12 each month), not
  the month that pays (§11, a gap of timing).
- A sale (`Events._sell_property`): a `taxable` one within `property_sale_months` of `bought` (of a
  file property too: `taxable` means "not own use", owner R3; without `bought` `taxable` alone
  decides) books the proceeds less the penalty of a repayment from its `then` (`_then` returns it:
  BFH IX R 42/13, a Veräußerungskosten) less `bought_for - afa_taken` (§23 Abs. 3 S. 4). After a
  conditional sale the loan runs on, its interest no Werbungskosten (nachträgliche Schuldzinsen:
  a gap), and a repayment without a sale deducts no penalty.
- §10d (`tax.carried`, `year_settlement`): `YearIncome.loss_carried`, `YearSettlement.loss_left`.
  The Gesamtbetrag der Einkünfte (§2 Abs. 3) is salary, taxable pension and other income less the
  Pauschbeträge, plus the severance; the pot offsets it before the Sonderausgaben (Abs. 2 S. 1, no
  limit: the 1 Mio. € and 70% of the Mindestgewinnbesteuerung, 60% from 2028, are a gap), a
  negative one joins the pot, a negative zvE from the Sonderausgaben alone carries nothing. Used
  beyond the regular income (a severance), the zvE below zero joins the fifth (§34 Abs. 1 S. 3).
  The Günstigerprüfung settles the pot again on the Gesamtbetrag with the capital income (§32d
  Abs. 6 S. 1): where it refunds, its `loss_left` holds, so a loss first shelters the flat-taxed
  gains of its year. A business loss falls out of the same sum (rule `self-employment`), so do
  dated work expenses (rule `deductions`).
- Verlustrücktrag (owner 2026-10-16, which reversed R4; Abs. 1 read at gesetze-im-internet.de that
  day): `tax.loss_carryback` (`TaxOptions`, default true). `YearSettlement.loss`, the negative
  Gesamtbetrag der Einkünfte of the year (with the capital income where the Günstigerprüfung
  refunds), goes back into the year before, the rest into the second before (S. 1, 2), each up to
  its `YearSettlement.room` (the Gesamtbetrag der Einkünfte less the Vortrag used and the losses
  carried back so far: the Vortrag first where both meet, Haufe `Verluste/Verlustabzug` 4.5; with
  the capital income where its Günstigerprüfung refunds, §32d Abs. 6 S. 1, `Zve.room_capital`), at
  most `loss_carryback_max` in all (1 Mio. € of a single person since 2024, year file;
  `tax.carryback`). `YearIncome.loss_back` comes off as the pot does, before the Sonderausgaben,
  the regular income first, so beyond it the zvE below zero joins the fifth of a severance (R 34.1
  Abs. 1 S. 3 EStR, §34 Abs. 1 S. 3), and beyond the regular room the capital income of the
  Günstigerprüfung. The rest joins the pot. S. 6 since 2022 (Viertes Corona-Steuerhilfegesetz,
  BGBl. 2022 I S. 911; read again 2026-10-16: "insgesamt abzusehen"): the waiver on application is
  whole, no part of it (a partial waiver down to the Grundfreibetrag is the law before 2022, not
  modelled): the default carries back in full; `false` is the waiver, forward only, the engine
  before the option.
- The engine (`Settlement._carry_back`, in `_settle_december` after the rounds, the church tax due
  set): `Core.assessed`, a `deque` of two `state.Assessed`, the last year first (its final
  `YearIncome` with `loss_back`, its settlement, its price level), a loss of no path skips. The
  rooms (`YearSettlement.room`) at their levels in the euros of the loss year; each year settles
  again and is amended in place
  (a year takes from two later ones). `refund_back` (the old `total` less the new: income tax, Soli,
  church and trade tax) and `flat_back` (the new Günstigerprüfung refund less the old), nominal at
  the level of the year amended, `_refund_back` pays first in the next `_settle_december` (the
  assessment of the loss year comes the next year; the last settlement of a run too): `income tax`
  and `capital gains tax` below zero in that month (rule `ledger`), before `settled` (rule
  `spending`). The church tax refunded lowers `church_due`, the church tax paid in the year of the
  refund (§10 Abs. 4b S. 3).
- The pot is nominal, as the law carries it: `Core.income_losses`, seeded from
  `tax.loss_carryforward` (the Feststellungsbescheid, Abs. 4, nominal at `start`), `/ d` into
  `_settle_year`, kept by `_settle_late_sales` and the `plain` recompute of the ledger split through
  `replace`, written `* d` by `_settle_december` after the rounds. `losses` (§20) and
  `private_losses` (§23) stay in start-year euros (a gap: they grow with the prices). The roll
  forward writes the pot at the new start (rule `rollforward`).
- GKV (rule `gkv`): a voluntary member pays on `max(_rent_net(), 0)` beside the other taxable
  income at its run rate (`_run_rate(taxable=True)` leaves the rents out), each kind at least 0
  (BVSzGs §3 Abs. 1b: after the Werbungskosten; BSG B 12 KR 12/98 R, B 12 KR 11/20 R).
- Ledger (rule `ledger`): no new flow. The rent is a `source`, the interest, the upkeep and the
  Hausgeld book as before; the AfA is no cash and has no row: it shows as a lower `income tax`.
- Gaps: degressive AfA (§7 Abs. 5a, a construction from 2023-10 to 2029-09 or a purchase in the year
  of completion) and §7b; a use that changes within a holding (BMF 2000-10-05); verbilligte
  Vermietung (§21 Abs. 2); anschaffungsnahe Herstellungskosten (§6 Abs. 1 Nr. 1a); §82b EStDV;
  Liebhaberei; the AfA of the month of a sale (R 7.4 Abs. 8 EStR counts it; the events run before
  the streams, so `_let` is false then: a twelfth of a year); the Erhaltungsrücklage when the WEG
  spends it (BFH IX R 119/83: the example leaves it without `property`); Vorauszahlungen on the
  rent; the Gewerbesteuer carryforward (§10a GewStG). Of the Verlustrücktrag: none into the years
  before `start` (after a roll forward the loss of its first year carries forward only); a refund
  due after the end of the run is lost, so is one across a roll forward (`rollforward.built`
  writes the pot of `simulation.before` only, not `refund_back`, `flat_back` or `assessed`). A
  roll of one year settles one December with `assessed` empty: the whole loss is in the pot. A
  roll of two or more loses the carryback of a loss of its last year, refund and loss; models.md
  names the waiver for the roll as the remedy (an issue for the owner, review 2026-10-16); the
  Günstigerprüfung of the loss year takes the loss against its capital income also where a
  carryback saves more (the application of §32d Abs. 6 is per year); §23 losses forward only (rule
  `tax`). The §35 share leaves a rental loss out of the positive income
  (`YearIncome.rent`), a church tax refund comes after the pot (BFH IX R 34/17), and `deduct`
  refuses `property` (§35a Abs. 5 S. 1): rule `deductions`.
- Tests: `tests/test_rental.py` (relations: a cost lowers the tax as much as a rent lower by it;
  the AfA rate, share and end; the end of the rent and a sale; the §23 basis, once for a GKV
  member too, and the penalty; the costs that the age curve and `scale` leave; the pot over years,
  nominal with inflation, the seed, a business loss, a purchase, the GKV; the carryback a December
  later, switched off, into the second year, into the capital income of a Günstigerprüfung, the
  Grundfreibetrag it takes), the law in amounts in `test_tax.py` (`carryback`, `loss_back` as the
  pot, the room, with the capital income), `rich_plan` (a let flat at a loss,
  its taxable sale; a course of 2030, whose loss beyond the capital income goes back into the
  severance year 2029, refunded in December 2031) and `gkv_plan`
  (a let flat with a loan repaid in 2033, its loss against the capital gains of the gap years, a
  seed of 20,000 €) of `test_golden.py`.
