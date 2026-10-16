---
paths:
  - "src/dagobert/tax.py"
  - "src/dagobert/engine/{core,health,settlement}.py"
  - "src/dagobert/model/taxes.py"
  - "tests/test_harvest.py"
---

# Harvest of gains

`tax.harvest` (`model.taxes.TaxOptions`, default off; owner W2): each December the settlement sells
the equity whose gain fits the tax-free room of the year and buys it back at once. Sources read on
2026-10-13 (gesetze-im-internet.de, BFH, BVSzGs). The rest of the capital tax: rule `tax`; the GKV:
rule `gkv`; the run: rule `engine`. The inputs: `docs/manual/configuration.md`, in plain English
`docs/manual/models.md` (`Realizing gains`). Individuals only.

- Law. A sale and a rebuy of the same securities on the same day at another price is no
  Gestaltungsmissbrauch (§42 AO; BFH 25.08.2009 IX R 60/07 and IX R 55/07; BFH 12.06.2018 VIII R
  32/16, BStBl II 2019, 221, Rz. 23: the taxpayer decides "ob, wann und mit welchem Ertrag"): no
  wash-sale rule. A rebuy at the same price in one order is untested, so the manual says the next
  market price. The units stay, so the pooled basis (rule `tax`) steps up exactly; a real December
  rebuy owes 1/12 of a Vorabpauschale on the new units (§18 Abs. 2 InvStG), moot here: the engine
  charged it on the whole holding.
- The room (`tax.harvest_room`): a taxable amount in start-year euros, after the Teilfreistellung,
  as the pool's `taxable_basis` takes it (no divisor). The Sparer-Pauschbetrag left (§20 Abs. 9
  EStG) and the tariff room, `grundfreibetrag − Zve.capital − Zve.alg1` at least 0, where the
  Günstigerprüfung refunds the flat tax in full (§32d Abs. 6 S. 1, 2; ALG1 by §32b, less the
  Arbeitnehmer-Pauschbetrag that no Arbeitslohn takes; zone 1 of §32a: no Soli, the 27.99% of a
  church member come back too). `tax.zve` (out of `year_settlement`, `Zve`) gives the zvE after
  the Werbungskosten and the Sonderausgaben of rule `deductions` and the Verlustvortrag left,
  without and with the capital income of the year; a negative zvE from the Sonderausgaben (PKV
  premiums, the Pauschbetrag of §10c: 13,384 € of room in a year without income) carries nothing
  and widens the room.
- A harvest never uses up carried losses. The tariff part is 0 in a year with a severance (the
  Fünftelregelung, §34; also a bAV lump sum with `fuenftel`) and while a Verlustvortrag (§10d) is
  left with the capital income of the year (`Zve.left_capital`, also of a negative Gesamtbetrag of
  the year): it would use up losses that offset the tariff of a later year. No room at all while
  the §20 loss pot holds losses (`Core.losses`): `capital_gains_tax` takes the pot first (§20 Abs. 6
  S. 2), which would shelter the next sale at once, while a stepped-up pooled basis reaches each
  later sale by its share: tax earlier. The design (C8, C11) took the pot as the cheapest step-up;
  `engineer`, 2,000 paths: median end net worth −3,001 € with it, +170 € without (5th percentile 0).
- The step (`Settlement._harvest`, December only): after the Vorabpauschale and the interest took
  their part of the Pauschbetrag, before `year_settlement`, whose `YearIncome` it rebuilds with the
  new capital income. `gain = min(room × deflator, taxable_gain⁺)`, `taxable_basis += gain`, its
  `_flat_tax` joins the bill, and the Günstigerprüfung of the same settlement refunds it: the cash
  never falls. `liquid` rises by gain × `flat_rate` (`_latent_tax`) with no cash moved, so the
  spending rule, `broke`, the difference of two runs and the end wealth see the tax saved. A sale
  for the December bill after it (`_settle_late_sales`) pays the tax on what exceeds the room.
  Equity only: gold and crypto keep their lots (a rebuy restarts the §23 period, BMF 2025-03-06 Rn.
  55), deposits and the bucket hold no gain to step up. No tax-loss harvesting.
- GKV cap (always, owner W3; the formulas of rule `gkv`): when the next January is voluntary by the
  inputs (`Health._voluntary_next`, the same on every path: in the GKV then, `tax.pkv: false` or a
  `tax.gkv_from` by then, whose PKV December keeps `kv_rest`, a switch later in the year no cap; no
  salary stream active then by its dates and phases and `core.pays`, no ALG1 stream that pays or
  rests (`_alg1_holds`, rule `alg1`), no pension with `person.kvdr` that can be claimed by then;
  masks and later events left out), the gain is at most `Health._kv_room`, so the base of the next
  year (`_kv_last`) stays at the minimum and the harvest costs no KV. KV and PV of about 20.5% on
  the base after the Teilfreistellung are 14.4% of the gain against 18.5% of tax later: the cap pays
  only through discounting and a later sale free of KV. A compulsory January (a job, ALG1, the KVdR)
  takes the tax room: after a December of ALG1 whose days end next year, the voluntary months after
  it pay on the harvest (a decision of the design).
- Ledger (rule `ledger`): no flow and no group; its tax books as `capital gains tax` of the year
  with the refund (`since` January), so `test_golden` adds up. A marker `harvest` (`once`) in the
  first December in which half of the paths harvest: the median gain of those paths before the
  Teilfreistellung (gain over `taxable_share`, exact for depots of one rate), `charts.said`
  `19.120 €`, `MARKER_KINDS` `Gains realized`.
- Inputs: the Tax tab (`Realize gains each December within the tax-free room`, `TERMS`
  `Günstigerprüfung`), the overrides of a scenario, and the Explorer switch `Realize gains` in the
  group `Taxes` (`knobs.switches`, `sliders.TAXES`; no lever, no dial).
- Gaps: no trade cost or spread; no harvest into zone 2 while the marginal rate stays below the
  flat rate (a GKV member pays about 20.5% on the base); the Kasse sets the base from the last tax
  notice, the engine counts the harvest in the next year in full (rule `gkv`); a severance year
  harvests the Pauschbetrag only. The Vorabpauschale of a depot above about 64 k€ (the Basiszins of
  2026) takes the Pauschbetrag in each year of growth, so the room comes from a calendar year
  without pay and without carried losses, or a year whose falling market leaves the Pauschbetrag.
- Tests: `tests/test_harvest.py` (relations), `test_tax.py` (the room in amounts), `test_health.py`
  (the cap), `rich_plan` of `test_golden.py` (one harvest, 2031, a career break); `gkv_plan`
  harvests once, 2043: the gift of that year pays its spending (VPW at its floor, rule `spending`)
  without a sale, and the KVdR of 2044 lifts the cap. Else its Vorabpauschale takes the
  Pauschbetrag, its sales stay within the Grundfreibetrag and the minimum base, its bAV lump sum
  of 2035 takes the Fünftelregelung.
