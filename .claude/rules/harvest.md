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
  and widens the room. A `cap` bounds the Pauschbetrag and the tariff part together.
- The loss pots (issue #6, 2026-10-16). A gain uses up a pot first: the §20 pot (`Core.losses`, also
  of `tax.capital_losses`) before the Pauschbetrag (§20 Abs. 6 S. 2, `capital_gains_tax`), the
  Verlustvortrag left with the capital income of the year (`Zve.left_capital`, §10d Abs. 2; the
  Günstigerprüfung adds the gain to the Gesamtbetrag der Einkünfte, §32d Abs. 6 S. 1) before the
  tariff room, which beyond it is `grundfreibetrag − Zve.capital − Zve.loss_capital − Zve.alg1` (a
  loss of the year joins the pot). `tax._along`: a pot goes along with the room beyond it only where
  that room is at least the pot, so the basis steps up at least twice each pot used (with both at
  once the §20 gate counts the Verlustvortrag as room: 4/3 of both at worst, the Pauschbetrag used,
  the tariff room the §10d pot, the §20 pot twice it; an approximation); else that room closes, for
  the §20 pot all of it, for the §10d pot the tariff part. Why: a §20 pot offsets the next capital
  income at once (often the next Vorabpauschale), a Verlustvortrag the tariff of the next year with
  income, at most the top rate with Soli and church tax (47.5%, 51.5% at 9%), below twice the flat
  rate (52.75%, 55.98%); a stepped-up pooled basis reaches each later sale by its share and the end.
  Approximations: no discounting, no look at the later years (a pot that offsets income below the
  Grundfreibetrag saves nothing).
- The tariff part is 0 in a year with a severance (the Fünftelregelung, §34; also a bAV lump sum
  with `fuenftel`) and, with `tax.loss_carryback`, in a year whose own Gesamtbetrag with the
  capital income is negative (`Zve.loss_capital`): a gain would shrink the loss that goes back,
  which may refund more than the top rate (into a year of the Fünftelregelung); not in the first
  year of a run (`assessed` empty), whose loss goes forward only, but in a year whose earlier
  years have no room (an approximation). A loss that goes forward only joins the pot.
- Measured on a copy of `engineer` (2,000 paths, seed 42; the median real end net worth against
  the rule before, no room while a pot held losses): every §20 pot along −555 to −3,865 € over the
  ten scenarios (`plan` −2,817 €, seed 7 alike, as the −3,001 € of the first design C8, C11); the
  rule here +7 to +531 € (`plan` +263 €, paired +172 €; the 5th percentile +14 to +572 €). The §20
  gate alone at half the pot gave +33 to +762 €, at twice the pot +0 to +531 €: the pot itself
  keeps one rule for both pots.
- The step (`Settlement._harvest`, December only): after the Vorabpauschale and the interest took
  their part of the Pauschbetrag, before `year_settlement`, whose `YearIncome` it rebuilds with the
  new capital income. The `cap` beyond the §20 pot is the taxable gain held (so a gate sees what
  the equity holds) and the KV room below. `gain = min(room × deflator, taxable_gain⁺)`,
  `taxable_basis += gain`, its `_flat_tax` joins the bill, and the Günstigerprüfung of the same
  settlement refunds it: the cash never falls. `liquid` rises by gain × `flat_rate`
  (`_latent_tax`) with no cash moved, so the spending rule, `broke`, the difference of two runs
  and the end wealth see the tax saved. A sale for the December bill after it
  (`_settle_late_sales`) pays the tax on what exceeds the room.
  Equity only: gold and crypto keep their lots (a rebuy restarts the §23 period, BMF 2025-03-06 Rn.
  55), deposits and the bucket hold no gain to step up. No tax-loss harvesting.
- GKV cap (always, owner W3; the formulas of rule `gkv`): when the next January is voluntary by the
  inputs (`Health._voluntary_next`, the same on every path: in the GKV then, `tax.pkv: false` or a
  `tax.gkv_from` by then, whose PKV December keeps `kv_rest`, a switch later in the year no cap; no
  salary stream active then by its dates and phases and `core.pays`, no ALG1 stream that pays or
  rests (`_alg1_holds`, rule `alg1`), no pension with `person.kvdr` that can be claimed by then;
  masks and later events left out), the gain beyond the §20 pot (which `kv_capital` leaves out) is
  at most `Health._kv_room`, the `cap` before the gates of the pots, so the base of the next year
  (`_kv_last`) stays at the minimum and the harvest costs no KV. KV and PV of about 20.5% on
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
  without pay and without a pot larger than its room, or a year whose falling market leaves the
  Pauschbetrag. No harvest outside December (a sale that a deficit forces, the month of a lump
  sum): the settlement alone knows the income of the year. The waiver of a carryback (rule
  `rental`) decides without the harvest, which may then take the kept loss along. A harvest raises
  the room of its year (`Zve.room_capital`), so a loss of the next two years goes back into it by
  up to the gain, where the tax was 0 already: the waiver keeps it only where the next year saves
  more.
- Tests: `tests/test_harvest.py` (relations: a §20 pot below the room along, less tax in all, one
  beyond it waits; a Verlustvortrag along, less tax in all, beyond the room the Pauschbetrag),
  `test_tax.py` (the room in amounts, the pots, the gates, the `cap`), `test_health.py` (the cap,
  a §20 pot beside it), `rich_plan` of `test_golden.py` (one harvest, 2031, a career break; its
  §20 pot goes before the December of 2026, the course loss of 2030 goes back); `gkv_plan`
  harvests once, 2043: the gift of that year pays its spending (VPW at its floor, rule `spending`)
  without a sale, and the KVdR of 2044 lifts the cap. Else its Vorabpauschale takes the
  Pauschbetrag, its sales stay within the Grundfreibetrag and the minimum base, its bAV lump sum
  of 2035 takes the Fünftelregelung.
