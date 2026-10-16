---
paths:
  - "src/dagobert/ui/{scenario_overrides,overridegrids}.py"
  - "tests/test_scenario_overrides.py"
---

# Overrides tab of the Scenarios page

The forms, their fallbacks and Save: rule `forms`; the override algebra (`overrides.effective`,
`fallback`, `own`, `rows`, `from_rows`): rule `persistence`; the save guard: rule `save-guard`. The
`overrides` of a scenario file: `docs/manual/configuration.md`; the user guide of the tab:
`docs/manual/overrides.md`.

- `src/dagobert/ui/scenario_overrides.py`: `tab(path)` draws the overrides of the scenario file
  `path`, the `Overrides` tab of the Scenarios page, on an `overridegrids.Here` (the file, its raw
  `loader.chain`, `tables.known`). A chain that does not read (a missing parent, a cycle) gives a
  warning instead: nothing inherits then. Each part is an `st.expander` keyed by `Tab.key`, labeled
  with the leaves that the file sets there (`Markets (2)`) and open at first while it sets one;
  every part draws in every run, so a closed one keeps its edits. `Save stays off: see Markets`
  names a closed form that keeps Save off. A `start` that the chain overrides shows read only above
  them (`_start`: `Start overridden: 2026-11, in this file`, else `from <stem>`): the roll forward
  moves only the start of `assumptions.yaml`.
- The tabs of the Assumptions page in override mode (`assumptions.TABS`, `Tab.form(file, keys=
  ("overrides",), override=True, key, view)`, `assumptions.options(refs, stem)`): an empty field
  inherits, its placeholder names the value and its source (`2 from base`, `(default)`). Simple
  mode and the features take the fields of the Assumptions page (rule `assumptions`: an override
  counts as used also at a default), each part ends with the note of what it hides, a part
  without a field to show is left out and named in the note below the parts. `unsaved(stem)`:
  whether a form (`forms.edited`; `Scale` by the start of its key) or a grid by id
  (`overridegrids.unsaved`) holds an edit, before they draw: the Scenarios page keeps the tab
  then (rule `scenarios`). Then
  `Scale` (decision: only here): `ScaleForm`, the `scale` fields of the model. `categories` is a
  mapping grid with a select of the expense categories of the scenario, its factor in percent as on
  the explorer's slider (`90` for 0.9; `changes` turns off the guard's warning above 100%,
  `Change.capped`: a factor is no share); `savings` the same with a select of the savings plans of
  the scenario (`Kind.STREAM`, `sorts=("savings",)`), `FACTORS` and `FACTOR_HELP` name both, and
  `NAMES` heads their key columns `category` and `savings plan`. A salary per phase
  (`fields.entries` of `scale.salary` with the phases of `references.phases`, by label; `Salary and
  profit in <label> €`: it scales the profit of a business too) shows
  in euros as on the explorer's slider: `gross` takes the gross of a usual month at the factor 1
  from the cached `fixed` run of the files (`budget.regular_salary` over the factor that the run
  took, from `overrides.effective`), `mapping` shows factor times gross (cents), `stored` keeps
  the factor (`round(euros / gross, 6)`, as the slider), `leaves` gives the inherited one in euros
  and without one the gross itself, `from cashflows.yaml`. A phase without a salary in the run
  keeps its factor field while the chain holds a factor; without a run (a template, a plan that
  does not load) every phase takes its factor. The form key holds a digest of the gross: a value
  shown in euros means another factor once the run changes, so a new run starts a new form. The
  growth of each phase follows the salaries, in percent (rule `pay-growth`).
- `src/dagobert/ui/overridegrids.py`: the overrides by id as grids (`ById`, the rows of
  `overrides.rows`): `Dates` (`shift`: `id`, `months`), `Event fields` (`events`: `id`, `field`,
  `value`) and `Assets` (`assets`: `asset`, `field`, `value`); the first column a select of
  `references` (`ITEM`, `EVENT`, `ASSET` names of the scenario, plus an id that the file holds),
  `field` a select of what an override sets whole (`settable`: a value of one line of the model of
  each event type with an id in the chain or of each asset kind, less what names or describes the
  item, `NOT_SET`). `value` is text in the unit of the field of its row (`text`: `170.000 €`, `7%`,
  `2027-05`; `value` reads it with `fields.parse`, a field that the id lacks as YAML). `edited`
  gives the changes by override path from the grid edits: a value that the row keeps stays as the
  file holds it (also under another id or field), an emptied value or a deleted row inherits again,
  a value that does not read or a new row without all its cells keeps Save off (`needs field`). Each
  grid pins its first column on a phone, its column help in the popover `Columns`. Below it the
  entries that the file inherits, with their file; below the dates each group that moves,
  `job-end 2027-05 → 2027-08 (from base)` (`moved`, from the first month that the chain writes,
  after the edits). The Phases tab writes the same `shift` when a month of an inherited phase
  change is moved (rule `scenarios`): each checks the other by its `Seen` of the part.
- Save conflicts: the forms keep their own bases; the grids one `overridegrids.Base` per nonce of
  their part (`part`: `shift`, `events`, `assets` of the file), the revision taken before the read.
  A change of it on disk without edits starts a new generation, with edits it warns above the parts
  with `Discard my edits` and keeps Save off; their `save.Grid` checks again inside the write.
- The live check (`trial`): once every form and grid reads, the merged edit of the tab is written
  to a copy of the plan files (`revisions.PLAN`) in a temporary directory, and `load_plan` runs for
  the scenario and those that extend it (`Here.below`). A problem that the files now do not
  have (by file, key path, message; `_held`, cached per `ui.data_stamp`: about 25 ms per plan, a
  parent of nine takes 0.25 s) keeps Save off with its line in the edited text; one that they have
  shows above the tabs already (rule `scenarios`).
- One Save for the tab (`forms.save` with `ready`): the forms and the grids as one revision
  `Scenarios: <stem>`, one `guard.review` of all their changes (the euros of a salary, a grid row
  `events flat-sale price`, the sentence on the browser language only for a number cell of a
  grid). The style of `tables.SAVE_IN_HEADER` is its first element.
- Words (rule `i18n`): `overridegrids.GRIDS` are keys (`shift`, which no model names, marked in the
  context `key` for the guard: `Verschiebung`), `_title` their words (`Assets` in the context
  `overrides`: asset fields, not the page), `HEADS` the headers of the columns of a grid by id that
  no model names, `SALARY` its heading in `scale_form`. A salary per phase takes its label and the
  sentence of its help in the language of the session, the label of the phase as written (its braces
  doubled in `about`, which `gridcolumns.said` formats). The grids by id note their editors
  (`gridstate.drawn`): a switch of the language keeps their edits.
