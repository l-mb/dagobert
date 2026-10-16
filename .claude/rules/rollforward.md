---
paths:
  - "src/dagobert/rollforward.py"
  - "src/dagobert/ui/overview.py"
  - "tests/test_rollforward.py"
---

# Roll forward

The `Roll forward` on the Overview: rule `overview`. It writes through `revisions.write` with the
texts of `textedit.scalars`: rule `revisions`.

- `src/dagobert/rollforward.py`: moves `start` to a later month. `passed` finds the events before
  the new start that a run refuses (all but `end_streams`, `set_stream` and `add_stream`, which
  apply in the first month, `model.events.STATE_EVENTS`, and a `gift`, which the roll moves into
  `given` of its relative, rule `estates`: `KEPT`) and the phases that end before it, in every
  concrete scenario, each once per file where it is written, less what the scenario drops
  (`loader.written`: a child that drops a passed event no longer refuses the roll for it). A
  `Passed` names the type of an event (`kind`, None for a phase): the Overview links it to its place
  on the Scenarios page. A forced onset of a disability before the new start (`disability.at`, kind
  `DISABILITY`, of `assumptions.yaml` or the nearest `overrides` of a chain that set it) refuses it
  too: the Overview links its file, the Assumptions page or the `Overrides` tab. `apply` refuses
  while such an event remains: only the user knows what became of it, so the roll removes no event
  but a gift (`Roll.gifts`), no phase and no asset; `check` refuses a gift that a scenario moves
  across the new start or that an override or a `drop` names by its id (rule `estates`).
  `cpi_change` is the factor of the consumer prices between the two months, `check` takes those of
  the data directory (`series.cpi`: shipped, then fetched). Past its last month the last value grows
  at `inflation.mean`, `CpiChange.source` says so, and the Overview links the Data page, which
  fetches newer months. `rebase` multiplies by it and rounds to cents: `amount`, `gross`,
  `point_value` and the `premium` of a BU of the streams whose `index` is `cpi` (absent or `cpi`;
  absent on a savings plan or a BU is null, `model.streams.stream_index`; a pension too) in
  `cashflows.yaml` and in `add_stream` events, of `set_stream` events on such a stream (streams of
  one name with the consumer prices and another index raise), `liquid_below` of a conditional sale,
  the `cash` of an inheritance without a month, `spending.reference`, `spending.vpw.floor` and
  `tax.werbungskosten` (`_reference`, `START_EUROS`, by key paths of any depth), `care.cost` when
  its index is `cpi` and the `contribution` of an `av_depot`, also as scenario overrides. That
  includes `overrides.events.<id>` (`_overridden`), which `loader.adjust` sets on each event of the
  id that has the field, in the chain of every scenario file whose chain holds the file (`_reached`:
  also an event that only a child of a template writes, less an id that a file below drops):
  `amount` and `gross` where those are `set_stream`s on such streams (with a nominal event amount or
  another index under the id it raises), `when.liquid_below` of a sale, and a `stream` (`_added`, so
  `periodic` finds it too). The real `pension_growth` of the months between is left out. Nominal
  amounts, the other indices and the event amounts that are nominal at their date stay too. A stream
  paid every n months without `start` counts its payment months from the simulation start:
  `periodic` finds them in `cashflows.yaml` and in `add_stream` events, and the roll writes the old
  start as their `start` (`textedit.After`, behind `every`), so they pay in the same months. A
  business that runs before the new start would take that as its founding and start the half
  Regelbeitrag again (rule `self-employment`), and the loss pots that the run built would be lost
  (rules `rental`, `tax-options`). `built` runs each concrete scenario up to the new start
  (`engine.simulation.before`, `fixed`) once and reads them. `Founded`: the first month of a
  business (`Core.first_profit`) in a scenario without `tax.self_employed.founded`, written as
  `founded` into the options `tax.self_employed` that the scenario takes, the nearest `overrides` of
  its chain that hold them as a mapping (also one of mappings only, `tax: {self_employed: …}`), else
  `assumptions.yaml` (`_options`: `textedit.After` behind their last key whose value takes a line,
  `textedit.FIRST` when none does, so no second `tax` goes in; in place of the key or a null).
  Scenarios that share them take the earliest month. Without them `rv` is `none`, which reads no
  founding. `Carried`: each pot (`key`) of every concrete scenario, rounded to cents, by the options
  `tax` that it takes, written as its key there the same way: the Verlustvortrag
  (`Core.income_losses`) as `loss_carryforward`, the losses of capital income (`Core.losses`) as
  `capital_losses`, both as the run holds them, without the factor of `cpi_change`: the law keeps
  them nominal, so a seed that the run leaves alone is no change (the run keeps `Core.losses` in
  start-year euros, a gap of rule `rental`); without any options, one new `tax: {…}` behind `start`
  in `assumptions.yaml` for both (`textedit.After` takes a flow mapping of scalars; two keys added
  into `{}`: rule `store`). Scenarios that share them take the smallest pot of all of them, also one
  equal to the value now (errs towards more tax: none starts with losses it never built), written
  where it differs from the value that they take. `apply` writes the amounts, these starts, the
  foundings, the pots and `start` in one write, and runs `check` inside it, on the newest inputs.
  With `read` (`seen`: a `revisions.Seen` of the text of every YAML input, `inputs`, taken when the
  page draws the list) an input changed since, also a new one, raises `ConflictError` and changes
  nothing. The Overview keeps the `seen` of the run that drew the list (`overview.SHOWN`, by month):
  the tap reruns the page, which lists again from the inputs then. Fetched consumer prices are no
  input: a fetch between list and tap goes into the roll unseen. Asset values are not touched: a
  dated loan, policy or depot carries to the new start (rule `engine`), and one without `asof` then
  counts its value at the new start. The `Changes since` table of the Cashflows page pairs such a
  stream with its row of the revision (`cashplan.diff`), so it shows only the changed amount.
