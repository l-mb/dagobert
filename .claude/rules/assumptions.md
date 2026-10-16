---
paths:
  - "src/dagobert/ui/assumptions.py"
  - "tests/test_ui_assumptions.py"
---

# Assumptions page

The forms, widgets and their Save: rule `forms`. The input file: `docs/manual/configuration.md`.
The user guide: `docs/manual/assumptions.md`.

- `src/dagobert/ui/assumptions.py`: the `Assumptions` page in the navigation section `Setup`
  (`/assumptions`) edits `assumptions.yaml` in four tabs (`TABS`), each one `forms.Form` of the top
  keys it shows (`Tab.tops`; `Tab.key` names its widgets, `Tab.title` is words): `Person` (`person`
  with the grid `Relatives you may inherit from` of `person.relatives`, then the `phases` grid, both
  `LabeledRows`: `name on the pages`, the label, first, an empty one shown as the name and a label
  equal to the name not written; `short name in the files`, the name, behind `All columns`, which a
  new row without it takes from its label, `model.assumptions.phase_name_for`; the relatives with
  `date of birth`, `sex`, `relation` and a help in words, `HELPS`, that names the Freibeträge; their
  `given` takes no column: `fields._columns` leaves a list of mappings out of a grid; the grid
  `Children by date of birth` of `children_born` (rule `children`) with `date of birth`, `counts as
  a child until`, `Kindergeld paid to you`, `child allowance` (`half`, `full`) and `child-raising
  years credited to your pension`, all five shown: a list grid of a form has no `All columns`; its
  help in `HELPS`), `Markets` (`inflation`, the `returns` and `indices` grids by name,
  `refinance_rate`, `pension_growth`), `Rules` (`cash_buffer_months`, `invest_rest`, labeled `Invest
  the rest`, `seed`, `allocation`, `spending`, `care`, `disability` (`Disability`, its grid `Yearly
  chance of a disability by age`, `Disabled from (what-if)`, rule `disability`): optional sections
  with `Use`, the age lists as grids) and `Tax` (`tax`, its nested `self_employed` last under the
  heading `Self-employment`: a top key after it would show under that heading, so `seed` moved to
  `Rules`; `werbungskosten` (`Work expenses per year €`, the term `Werbungskosten` in `TERMS`, so
  the label fits one line beside its neighbours; rule `deductions`) and `harvest` after
  `teilfreistellung`, `harvest` labeled `Realize gains each December within the tax-free room`;
  `kv_zusatz`, `church`, `land`, `loss_carryforward` and `capital_losses` come before it, labeled
  `Health fund extra rate %`, `Church tax`, `Bundesland`, `Losses carried forward €`, `Capital
  losses carried forward €` (rule `tax-options`); `alleinerziehend` after it,
  `Single parent (Entlastungsbetrag)`, always on: `WHEN` gates by a value, not by a row of the
  grid). Every field of `Assumptions` lies in one tab but `start` and `scale` (decision: scenario
  overrides only, which the explorer writes): a new field of the model joins a tab
  (`test_the_tabs_edit_every_assumption_but_start_and_scale`). Plain `st.tabs`: a closed tab keeps
  its unsaved edits. The parts of the tabs do not overlap, so a save of one tab neither refuses nor
  drops the edits of another.
- Each tab: the style of `tables.SAVE_IN_HEADER` first, `forms.show`, then `guard.review` with the
  sentence on the language of the browser only for a warning of a grid cell (`hint`: a text field
  reads a comma and a point alike), then `forms.save` with the tab as its `action`: one revision
  `Assumptions: Markets`. `LABELS` in plain words, for a field, a heading (`("care", "duration")`)
  and a grid column (`("returns", "stdev")`: `volatility`): `Pension insurance since`, `Tax-free
  capital income €`, `Private health insurance (PKV)`, the months of an integer or a duration; the
  keys of `returns` and `indices` stay as written (`fixed_income`), names that this file defines.
  The key column of the `returns` grid is headed `asset class`, of `indices` `index` (`LABELS` by
  the path and `name`). `TERMS` put the German term before the help (`Sparer-Pauschbetrag`,
  `Teilfreistellung`, `Werbungskosten`, `Rentenversicherung (RV)`, `Kirchensteuer`, `Zusatzbeitrag`,
  `Verlustvortrag`, `Verlustvortrag aus Kapitalvermögen`, the `Günstigerprüfung` of the harvest),
  and every help names the default.
  `HELPS` put a help in words where the description of the model names keys of the files (the
  phases, `rv`, `founded`, `loss_carryforward`, `spending.base` and `reference`), `CHOICES` the
  options in words (`rv`: `None`, `Fixed contribution (Regelbeitrag)`, `By profit`; `spending.base`:
  `The start, always`, `The first month without pay`), `WHEN` turns a field off while it has no
  effect (`forms.When`): `Sick pay in the GKV (statutory insurance only)` while `pkv` is on and
  `gkv_from` empty (`When.unless`), `Statutory health insurance from` (placeholder `private
  insurance only`, rule `tax-options`) while `pkv` is off, `Business founded` (placeholder `fixed
  contribution only`) without `rv: regular`, the `increase` and `ceiling` of the spending rule
  (`without pay only`) without `base: no_pay`, so does the section `vpw` (`Use (without pay only)`,
  rule `forms`: off it cannot turn on, on it can turn off). The spending rule names the reference
  wealth in its labels (`Cut below this share of the reference wealth %`), `base` and `reference`
  first, `categories` `Flexible categories`, the section `vpw` last (rule `spending`): `Variable
  percentage withdrawal (VPW)`, `Growth trend, real % per year`, `Spend down to age`, `Floor of the
  flexible spending € per month`. The intro is one line, the rest folds (`READING`, `ui.fold`).
  `NULLS` (`Every category except the health premium` for `age_categories: null`; off, an empty list
  is `[]`). `options` gives the names of the selects from `references`: the expense categories of
  `spending.categories` and `age_categories`, the indices with `cpi` of `care.index` (`null`:
  nominal). The keys of `returns` and `indices` are free text: a new class or index is a new name.
- `start` is read only (decision): a disabled field `Start month (read only)` with the description
  of the model and `START` as its help, a caption that the roll forward moves it, and, while
  it lags the current month (`months_between`), a link to the Overview (`ui.page_link`, the page
  that the navigation registers) with `?roll=open`, which opens its `Roll forward`: that moves it
  with the amounts. While it is current the Overview has no roll forward, so no link shows.
- `NULLS` also names the null option of `care.index`: `none: nominal euros`.
- Below the tables `Gifts received before the start` (`_given`, `GIVEN` folded): a select of the
  relatives of the file (`references.relatives`, by label; none: `Add a relative above first`),
  a grid of its `given` rows (`month`, `value`, `tax paid`, `GIVEN_HEADERS`) on `RowFile(…,
  ("person", "relatives", <name>, "given"))` with `save.base`, `save.warn`, `guard.check` and
  `save.button` (`Save gifts`, one revision of the page), as the repayments of a sale (rule
  `events`): a relative of one list, not a column of the tab's form. Its save makes the form of the
  tab start anew, as a change of its part elsewhere does (rule `forms`).
- A phase or a relative keeps its name in the grid while an input names it (`KEPT`): a delete or a
  rename in the grid that `references.orphans` leaves with uses gives a warning above the Save
  with the first three (`refused`, `SHOWN`) and `RENAME`, and keeps Save off
  (`forms.save(ready=False)`), as the General tab of the Scenarios page refuses a name; its label
  changes freely.
  `Rename` and `Rename a relative` below the tables (`ui.rename`, rule `references`, off while the
  tab holds edits or an unread field) rename it with every use as one revision `Assumptions:
  phase work → job`. The write refuses it too (rule `revisions`). The order of the grid is
  the order of the columns and colors; a new phase comes last.
- `tax.year` defaults to none, the year that the plan takes from `start`: an empty field shows that
  year from `start` (`AssumptionsForm.leaves`, `model.taxes.default_tax_year`; the segmented control
  marks it, `2026 from start`), in a scenario too when no file of its chain sets it. An empty
  `tax.kv_zusatz` shows the average of that year (`2.9 from tax year 2026`, `KV_ZUSATZ`), also while
  simple mode hides `tax.year`.
- The Overrides tab of a scenario (rule `scenario-overrides`) takes the same tabs: `Tab.form(file=
  ..., keys=("overrides",), override=True, key=..., view=...)` and `options(refs, scenario)`,
  without the phases (`Tab.shown`: a scenario defines none, the loader refuses `overrides.phases`).
- Simple mode and the features (rule `mode`; `mode.view` once per page, the `Here` of the tabs):
  `Tab.form(view=)` takes the fields of `Tab.shown`, those whose head (`mode.head`: the deepest
  path of `EXPERT` or of a feature above, so a section in use shows whole) `View` shows, and those
  whose head holds an edit not saved yet (`forms.edited`); `parts` the top keys of the tab (rule
  `forms`); `hides` the columns of a grid by a head of their own (`_columns`: `equity_correlation`
  of `returns`, behind `All columns` while no class holds it). On `starter` simple mode shows
  `Person`, `Markets` and `Tax`; a tab without a field is left out of `st.tabs`. The relatives
  grid takes `Rename a relative` and the gifts before the start with it. Each tab ends with
  `View.note` of what it hides (`Tab.hidden`: each head once in words, `Tab.named`, after the
  heading of its model unless the tab is named by it, `Inflation · Volatility`; one below another
  hidden head only for a feature off), and below the tabs the note of the tabs left out.
- The help of a field and of the explorer's slider of the same number is one text: the field
  description of the model (`model.base.description`), which the slider follows with what it adds
  (`knobs._about`). The slider help of the glide path and of the care duration names this page
  for the lists (`knobs._rule_knobs`).
- `Tab.title` is English (the revision source of its Save); the strip shows its words. The
  sources of the placeholders of `tax.year` and `tax.kv_zusatz` (`start`, `tax year 2026`) are said
  in the language of the session (rule `i18n`).
