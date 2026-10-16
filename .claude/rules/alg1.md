---
paths:
  - "src/dagobert/engine/{alg1,income,health}.py"
  - "src/dagobert/sv.py"
  - "src/dagobert/data/tax/*.yaml"
  - "src/dagobert/model/streams.py"
  - "tests/test_{alg1,golden}.py"
---

# ALG1

The unemployment benefit (Arbeitslosengeld, SGB III) and its claim, a balance of days, with the
law checked at gesetze-im-internet.de on 2026-10-16 (SGB III §§144, 147, 148, 154, 159, 161, 174,
339; SGB V §5 Abs. 1 Nr. 2; SGB VI §§58, 166) and the Fachliche Weisungen of the Bundesagentur
(§148 of 07/2023, §161 of 03/2022). The design: issue #16, the owner's decisions of 2026-10-16. The
Gründungszuschuss: issue #30, its law read at gesetze-im-internet.de on 2026-10-17 (SGB III §§93,
94, 148 Abs. 1 Nr. 8; EStG §3 Nr. 2 a, §32b; SGB V §240 Abs. 2 S. 3), the Fachliche Weisungen GZ of
2023-09-13 and the Katalog of the GKV-Spitzenverband of 2026-05-26. The
rest of the tax and SV law: rule `tax`; the KVdA and the exemption of a PKV member: rule `gkv`; a
child: rule `children`; ALG1 after a business: rule `self-employment`. The inputs:
`docs/manual/configuration.md`, in plain English `docs/manual/models.md`.

## The amount

- `sv.alg1_month` pays 60% (67% with a child) of the Leistungsentgelt of 30 days (§§149, 151, 153,
  154 SGB III): the BBG-capped last salary per day (times 12, over 365), less 20% for the SV, less
  the Lohnsteuer and Soli of a day, 1/360 of the year's (§39b Abs. 2 S. 9 EStG) in Steuerklasse
  I: Arbeitnehmer- and Sonderausgaben-Pauschbetrag, the Vorsorgepauschale of a GKV member at the
  reduced KV rate plus the average Zusatzbeitrag, PV at the base rate, the ALV part within 1,900 €
  with KV and PV (§153 Abs. 1 S. 4; §39b Abs. 2 S. 5 Nr. 3 e). It is the same for a PKV member.
  `test_alg1_month_matches_the_bundesagentur` pins the Selbstberechnungsprogramm of the
  Bundesagentur (pub.arbeitsagentur.de) for 2026 to 1 € a month; the former stand-in (the tariff
  on 80% of the salary) paid 3% too much at the BBG. The salary (`Core.last_salary`) stays nominal;
  the rules apply at the price level of the year in which the claim arises, and the amount stays
  fixed in nominal euros (`Alg1State.monthly`, a Bewilligungsbescheid), also for a later stretch.

## Inputs

- A stream of `kind: alg1` has no amount. `Stream.sperrzeit` and `Stream.training` (booleans,
  `TAKES` of `alg1` only; `Stream._together` refuses both on one row): a Sperrzeit after a
  resignation or an Aufhebungsvertrag (§159), once per row, from the first month in which the row
  pays; a course with a Bildungsgutschein (Arbeitslosengeld bei Weiterbildung, §§81, 144: the same
  amount, subsidy and points), a row beside the ALG1 row with the dates of the course. No new kind,
  no event (owner).

## The claim (`engine/alg1.py`)

- `Alg1` (on `Profit`, under `Health`) keeps `Core.alg1`, an `Alg1State`, the same on every path
  (owner: per path only where a per-path effect can change it; none can: a disability onset stops
  the pay for good, `working`, and the days of a path that never pays again are never read). Days of
  30 a month (§339 S. 1, 2; `alg1_month_days`). `Income._apply_streams` calls `_claim_alg1` first:
  every step after the streams reads the month.
- It arises (`_open_alg1`) in the first month in which an ALG1 row pays by its dates and phases
  (`_pays`), a Sperrzeit too: days `alg1_month_days` × `sv.alg1_months` of the age completed in that
  month (§147 Abs. 1 Nr. 2, Abs. 2; `_age`, whole months), with the full insurance record; the
  monthly amount; the markers `alg1` (a business before, rule `self-employment`) and `exemption`
  (rule `gkv`).
- A stretch is the months in a row with an ALG1 row. One that begins `alg1_claim_months` (48) or
  more after the claim arose pays nothing (`fresh`, §161 Abs. 2: "kann nicht mehr geltend gemacht
  werden"); one begun before runs on past the mark (BA FW 161.2: "nicht wieder geltend gemacht").
- A month (`_use_alg1`): a `sperrzeit` row that pays for the first time adds `alg1_sperrzeit_days`
  (84, §159 Abs. 3 S. 1) to `resting` and takes `max(84, floor(days × alg1_sperrzeit_share))` from
  the days (§148 Abs. 1 Nr. 4: the days of the Sperrzeit, at least a quarter of the claim due when
  it is first fulfilled after the event, rounded in favour, BA FW 148.1.4; of a first claim the
  whole, of a later stretch the days left, a decision: a quarter of 360 to 720 days is 90 to 180,
  more than 84). The rest of the month after `resting` pays while days are left; a month with a
  `training` row pays in full with any days left and takes `alg1_training_rate` (half) of its days,
  but none below `alg1_training_floor_days` (90; §148 Abs. 1 Nr. 7, Abs. 2 S. 3: a rest below 90
  stays whole, BA FW 148.2). `share` is the part of the month that pays: 0, 0, 0.2 for a Sperrzeit
  from the first of a month.
- `_extend_alg1`, in a month without a course: after `alg1_course_months` (6) course months in a
  row, a rest below 90 days rises to 90, once per claim (§148 Abs. 3; BA FW 148.3: one measure,
  months in a row, also when no ALG1 follows at once).
- `_pay_alg1`: the month books its ALG1 once, under the first row without `training` (`row`), else
  the course row: `monthly × share × mask × working` into the cash, `lohnersatz`
  (Progressionsvorbehalt), `acc.compulsory`; points `alg1_rv_share` of the last salary times
  `share` (§166 Abs. 1 Nr. 2 SGB VI), a month of Pflichtbeiträge and Versicherungszeit only with a
  `share` above 0: a Sperrzeit pays no contribution, and §58 Abs. 1 S. 1 Nr. 3 needs a benefit for
  an Anrechnungszeit.
- `status` (`_on_alg1`): ALG1 pays or a Sperrzeit rests it: the KVdA of §5 Abs. 1 Nr. 2 SGB V,
  since 2017-08-01 from the first day of a Sperrzeit (the HHVG struck `ab Beginn des zweiten
  Monats`). It makes a GKV month compulsory (`_pay_gkv`), keeps a business from being the main
  work (`_pay_profit`). The Agentur's PKV subsidy (§174 SGB III) takes `share`
  (`Income._health_support`): none in a Sperrzeit. `_alg1_holds` gives the status of next January
  for `Health._voluntary_next` (the harvest cap, rule `harvest`).
- Markers (`_end_alg1`, once): `alg1 used` in the first month in which an ALG1 row is active and the
  claim has no days left, `alg1 expired` at a stretch that begins after the four years with days
  left. Words: `charts.SAYS`, `LAWS` (rule `charts`).

## The Gründungszuschuss (`Alg1._found`)

- Input (owner 2026-10-17): `Stream.gruendungszuschuss` and `gz_extension` (the Ermessen of §94
  Abs. 2, default off), booleans of `self_employed` only (`TAKES`); `_together` refuses the
  extension without the flag (type `extension`). No phase kind, no event.
- `_claim_alg1` calls `_found` before the ALG1 rows: a month in which it pays books no row
  (`row` None, so the next stretch is a new one, `fresh`), takes no days of a row, `share` and
  `status` stay 0: no KVdA, the business is the main work (`_pay_profit`, its GRV and the voluntary
  GKV, rule `self-employment`), no PKV subsidy of the Agentur (§174 needs ALG1).
- Once per run: the first month in which a flagged business runs (`_running`, by dates, phases and
  factor; `Alg1State.founded`) decides it (`funded`), else a marker: `refusal(c, i, ty)`, a pure
  function of the state before the month that `whatifs.founding` takes too: `gz gap` without a
  month that paid ALG1 (`Alg1State.paid`, set by `_use_alg1`) within `gz_gap_months` (1) before it
  (§93 Abs. 1, Abs. 2 Nr. 1: the business ends the unemployment of a claim that pays; FW 93.36,
  93.44; a Sperrzeit that rests a claim never paid gives none, FW 93.39), `gz days` below
  `gz_min_days` (150, Nr. 1, the days after the Sperrzeit's); then `gz salary` when a salary pays by
  dates, phases, `every` and `core.pays` (`_salaried`: §93 Abs. 1, hauptberuflich), a bonus (`of`)
  too: one without `phases` pays with its last base after that ends (`Income._salary_gross`), so it
  refuses or skips the months that it pays in (`every`), as the books show it.
- It pays `gz_months` (6) from that month of `Alg1State.monthly` plus `gz_amount` (300, nominal:
  the law kept it since 2006, never indexed, a decision as the Erbschaftsteuer of rule `estates`),
  each taking `alg1_month_days` of the claim, not below 0 (§94 Abs. 1: six months whatever is left;
  §148 Abs. 1 Nr. 8), then with `gz_extension` `gz_extension_months` (9) of `gz_amount`, no days;
  in each such month in which a flagged business runs without a salary, on the paths of its `mask`,
  none after a disability onset (`working`). A month without pays nothing; its count goes on.
  Tax-free (§3 Nr. 2 a EStG), outside `lohnersatz` (not in §32b), no points, no
  Pflichtbeitrag. `Alg1State.grant`, its ALG1 part of the month, joins the base of a voluntary GKV
  member (`Health._pay_gkv`), the 300 € not (§240 Abs. 2 S. 3 SGB V; Katalog: `ja`, the share of
  300 € `nein`). Ledger: `source` `GRUENDUNGSZUSCHUSS` (`Gründungszuschuss`, German as is, rule
  `ledger`). Words of the markers: `charts.SAYS`, `LAWS`.
- The Cashflows sheet shows the profit of the row only; the rows of the run show the grant (no
  stream is named so, `budget.beyond_streams`, rule `cashflows`). The what-if `Start a business`:
  rule `whatifs`. Simple mode hides both columns behind `All columns` (`mode.EXPERT`, the feature
  `self_employment`).

## Elsewhere

- The constants of the year file: `alg1_months`, `alg1_month_days`, `alg1_sperrzeit_days`,
  `alg1_sperrzeit_share`, `alg1_training_rate`, `alg1_training_floor_days`, `alg1_course_months`,
  `alg1_claim_months`, `gz_min_days`, `gz_gap_months`, `gz_months`, `gz_extension_months`,
  `gz_amount`, and those of the amount.
- The Cashflows estimate (rule `cashflows`): `cashplan.with_alg1` gives a course row no amount (the
  claim pays once, on the ALG1 row beside it), `ui.cashflows._alg1` finds the claim by the rows
  without `training`. The sheet shows the monthly ALG1 of the phase, not the Sperrzeit or the end
  of the days: the rows of the run show what it pays (rule `ledger`).
- Simple mode hides the columns `sperrzeit` and `training` behind `All columns`, the feature
  `job_loss` with ALG1 (rule `mode`).

## Gaps

A new claim by a new Anwartschaftszeit (§§142, 143, 147 Abs. 4) and with it a Sperrzeit before a new
claim; the insurance record of §147 Abs. 1 Nr. 1 (always the full one); the shorter claim of §147
Abs. 3; the Sperrzeiten of 3 and 6 weeks (§159 Abs. 3 S. 2) and the others of §159 (Nr. 3 of §148:
their days only); the Erlöschen after 21 weeks of Sperrzeit (§161 Abs. 1 Nr. 2); §148 Abs. 2 S. 2
(an event more than a year back: never, the Sperrzeit starts with its row); Ruhen (§§157, 158); of
the Gründungszuschuss the Tragfähigkeit (assumed), a second one (§93 Abs. 4: one per run), the end
at the Regelaltersgrenze (Abs. 5), a start in a Ruhen after ALG1 paid (FW 93.40: later, here none),
a start per path (`after_sale_of`), a business that runs at the start (no claim seen: `gz gap`; a
roll forward past its start loses the rest), the Ermessen of phase 1 (always paid); Teil-ALG; a
profit beside ALG1 (§155); an onset of a disability during ALG1 (rule `disability`); a per-path
claim (a `mask` of a sale that ends an ALG1 row counts the days on every path); the reference salary
is the sum of the monthly (`every: 1`) salary streams in the last month that paid one, however long
ago (§150: the last year); partial months but the Sperrzeit; the roll forward starts the claim anew
at the new start; the next January of `Health._voluntary_next` (`_alg1_holds`) takes the four years
of a stretch that pays now, also for a stretch that ends before it and one that begins then.

## Tests

`tests/test_alg1.py` (relations: a Sperrzeit later and a quarter less, no subsidy and no points in
it, compulsory in the GKV, on a rest its 84 days; a course at half the days, its floor and its
extension; a later stretch within and after four years; the age at the first month, also of a
Sperrzeit), `test_sv.py` (`alg1_month`, `alg1_months`), the markers in `test_report.py`, the
refusals in `test_model.py`, the estimate in `test_ui_cashflows.py`, `rich_plan` of `test_golden.py`
(a Sperrzeit at 52 after the severance, a course of six months, 62 days left; the business of 2032
with the flag: the marker `gz gap`, 21 months after the ALG1; `gkv_plan`: three months of ALG1, then
the business with the grant and its extension, so its ledger adds up with them). The
Gründungszuschuss in `test_alg1.py` (relations: six months of ALG1 and 300 € more, its ledger row
the difference, the taxes the same; the days less in a later stretch; 150 and 120 days, a month and
two between; a salary or a bonus beside it; the extension; no points; the GKV as a higher profit,
the 300 € none), the what-if in `test_whatifs.py`.
