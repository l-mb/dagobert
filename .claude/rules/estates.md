---
paths:
  - "src/dagobert/engine/{core,events,state}.py"
  - "src/dagobert/{tax,mortality,rollforward}.py"
  - "src/dagobert/data/tax/*.yaml"
  - "tests/test_{estates,tax,mortality}.py"
---

# Inheritances and gifts received

The events `inheritance` and `gift` from relatives of `person.relatives` (individuals only: never a
spouse), with the law checked at gesetze-im-internet.de on 2026-10-13 (ErbStG §§9, 10, 14, 15, 16,
19; EStG §20 Abs. 4 S. 6) and the Katalog of the GKV-Spitzenverband of 2026-05-26. The rest of
the tax law: rule `tax`; the engine: rule `engine`; the ledger: rule `ledger`; the tabs and the
grids: rules `events` and `assumptions`. The inputs: `docs/manual/configuration.md`, in plain
English `docs/manual/models.md` (`An inheritance or a gift`).

## Law

- `tax.erbschaftsteuer(acquired, prior_values, prior_tax, relation, ty, *, inheritance)`, nominal:
  the first tax of the engine whose constants are not indexed (the Freibeträge stand since 2009, a
  decision of the owner: the convention of the start-year euros would halve the tax of a far
  estate, 600,000 € of the start after 15 years at 2.2% pays 45,100, not 20,350). An inheritance
  deducts the Erbfallkosten-Pauschbetrag (`erbst_erbfallkosten`, 15,000 since the JStG 2024, §10
  Abs. 5 Nr. 3). §14 Abs. 1: the earlier acquisitions from the giver within ten years
  (`state.TEN_YEARS`, 120 months, both ends in), one row each of `prior_values` and `prior_tax`,
  add at their value, a value of 0 or below stays out (S. 5); the tax of the sum less the larger
  of the tax on them alone by the law of today and the tax paid (S. 2, 3), at least the tax on
  this acquisition alone (S. 4), at most half of it (Abs. 3).
- `_erbst_tariff`: less the Freibetrag of the relation (§16 Abs. 1 Nr. 2, 3, 5, 7:
  `erbst_freibetrag`), rounded down to 100 (§10 Abs. 1 S. 6, `erbst_rounding`), the rate of the
  bracket (`erbst_brackets`, up to and including each limit) of the class of the relation (§15
  Abs. 1, `erbst_klasse`, `erbst_rates`), the Härteausgleich of §19 Abs. 3 over the limit below
  (`erbst_haerte`: half the excess up to a rate of 30%, three quarters above).
- `model.taxes.Relation`: `parent` (also a step-parent, §15 Abs. 1 I Nr. 2: class I, 400,000),
  `grandparent` (I Nr. 3, 200,000), `sibling` (II Nr. 2), `aunt_uncle` (II Nr. 3: the person is the
  child of a sibling), `parent_in_law` (II Nr. 5), `other` (III); class II and III 20,000.
- No income tax (an inheritance is no income of §2 EStG) and no GKV: the Katalog lists
  `Erbschaften: nein` (BVSzGs §3 Abs. 1). The income of the inherited assets counts as any.
- Securities keep the cost basis of the giver (§20 Abs. 4 S. 6 EStG): `Securities.cost_basis`,
  nominal; `Portfolio._buy_equity(basis=)` puts it into the one pool, so the latent tax and a sale
  tax their gain. Their units count for the Vorabpauschale of the year in twelfths from the month.

## Engine

- `Core._init_acquisitions`: one `state.Acquisition` per event in file order, with its month per
  path. A dated one at its month on every path; one without a month at the death of its givers:
  `Core._death` draws a uniform number per path of the generator `inheritance.<key>` (rule
  `engine`: one purpose per relative, shared by its events, so runs with one seed pair up; a
  renamed relative draws other months) and takes `mortality.death_months` on the survival curve
  of the relative from the start (`mortality.survival_curve` on its `born` and `sex`, the shipped
  table `mortality.table`, alive at the start); a single-path run takes the draw 0.5, the median
  month, the first with a survival below 0.5. Beyond the run: none. With several givers the later
  death, the giver who died last per path (`Acquisition.giver`). A dated gift whose giver an
  inheritance without a month names and who died by its month (`death <= at`) waits on that path
  and joins the first such estate of the giver (`Acquisition.joined`): paid in its month, under
  its giver, one acquisition with it; on a path whose estate falls beyond the run, never.
- `Events._apply_events` (from `Engine.run`, after the conditional sales): `_check_acquisitions`
  first, then the dated events of the month; dated acquisitions never enter `Core.events` (their
  month before the start still raises). `_acquire`: the cash and the securities (`value` in euros
  of the start times the equity index of the month before its return, `eq_price`), the tax per
  giver with what `Core.received` (`state.Received`: per relative a row per gift of `given` and
  per event that names it, filled on the paths that receive) holds within ten years; cash in,
  tax out (`MonthFlows.taxes`), the securities into the pool. Nothing reaches `YearAcc`.
- The marker (`kind` the event type, the note or the labels of the givers, the median received):
  in the month in which half of the paths have received, `half` unless all have (a dated gift with
  paths that wait, an estate drawn per path), as a conditional sale. Ledger (rule `ledger`):
  `one-off in` `inheritance` or `gift` by the label of the giver, `tax on one-offs` `<label>:
  inheritance tax` or `gift tax`, `non-cash` `one-off contribution` `<label>: equity`.
- `anatomy.drivers` (rule `analyses`): `(inheritance, <labels>)`, the age of the person at an
  inheritance without a month, infinite without one, binned like care (whole ages of equal groups
  below `BROKE_AGE`, the rest one group).

## Roll forward

- `rollforward.rebase` takes the `cash` of an inheritance without a month (`inheritance <givers>
  cash`): it falls in the drawn month, so its euros are those of the start. A dated gift and `given`
  stay nominal. `passed` lists no gift (`KEPT`): `gifts` finds each gift of a scenario file before
  the new start by the month of its file (`Moved`: its row, its value of cash and securities as
  written, its tax by `tax.erbschaftsteuer` with the earlier gifts of `given` and of the roll within
  ten years), and `apply` moves it (`_moving`): the row out of its file, a row of `given` into
  `assumptions.yaml`, `store.Edit.onto` the texts of the scalars, so those two files are dumped once
  (rule `store`). The value takes `equity.value` as written, euros of the old start, without the
  equity index of the month that `_acquire` applies: an approximation, the manual (Overview, step 5)
  has the user correct the `given` row. The comment lines above a moved row stay where they hang
  (`yamlcomments.drop`); the manual says to remove them. `check` refuses with ValueError naming the
  file (`_movable`): a gift that a concrete scenario sees across the new start (`_crossing`:
  `loader.lineage` against `loader.written`, its `shift` and `events` overrides), and a `shift`,
  `events` override or `drop` in the chain of a moved gift that names its id (`references.of`,
  `Kind.ITEM`, `Kind.EVENT`; also an id that other items share): either would fail in the write or
  no longer load. A gift of a relative that only the overrides of a scenario define raises
  ValueError (no `given` of `assumptions.yaml` takes it).

## Gaps

Hausrat and movables (§13 Abs. 1 Nr. 1), the family home (Nr. 4c), §13d (rented housing at 90%),
Gelegenheitsgeschenke (Nr. 14), the Versorgungsfreibetrag (§17), Nachlassverbindlichkeiten beyond
the Pauschbetrag, a Pflichtteil and the shares of co-heirs (the user enters the share), a
grandparent whose child is dead (400,000: set `parent`), the Bewertung of the BewG, Stundung
(§28), the Bescheid months after the death (paid in its month), units bought before 2009, a
property in an estate (its expected net proceeds as `cash`: a drawn property would exist on some
paths only), gold, crypto, policies, loans and a business in an estate, a giver healthier or
sicker than the period table, a giver dead before the start (remove the row), under a Berliner
Testament the Freibetrag of the parent who died first, Vermögen from abroad, a gift of several
givers (one gift each: the model refuses two).
