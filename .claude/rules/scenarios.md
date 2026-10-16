---
paths:
  - "src/dagobert/ui/{scenarios,fileactions,phases}.py"
  - "tests/test_scenarios.py"
---

# Scenarios page

The forms and small grids of its tabs: rule `forms`. The file actions and `Edit.origin`: rule
`store`. The rename in the revisions (`revisions.renaming`, `named`): rule `revisions`. The page of
the user guide: `docs/manual/scenarios.md`. The `Events` tab: rule `events`, the `Overrides` tab:
rule `scenario-overrides`.

## Main scenario, chooser and file actions

- `src/dagobert/ui/scenarios.py`, in the section `Setup` (`/scenarios`). It reads raw YAML
  (`scenariofiles.raw_scenarios`, `references.of`), so a scenario that does not load still opens;
  its problems (`loader.load_plan`) show above the tabs as a warning: a save is refused only for a
  problem that it adds, so the file can be fixed or deleted.
- At the top, apart from the chooser below it (owner, 2026-10-14: the order of the old multiselect
  `Explorer starts with` was invisible, its first one the main scenario), the box `PLAN` (`_plan`;
  bordered, on a phone a keyed expander `Main scenario: <stem · name>`, open with `?main=open`,
  `ui.MAIN`, the link of the Overview): the select `Main scenario` (the first of `app.yaml` that
  runs, else the first file that runs: `opening`, `scenariofiles.first_scenario`, which raises
  `InputError` when none runs; the scenario of
  the Overview, Cashflows, Flows and Spend, the first of the Explorer), the full note of the main
  one as a caption (no fold: an expander nests none) and the multiselect `Also compare in the
  Explorer` (the rest of the list, the main one not offered), templates in neither, one below the
  other, each option `stem · name — the start of its note` (`option`, `NOTE_CHARS`; side by side,
  the select cut the note), a tag at most 20rem (`ui/page.css`: Streamlit 1.65 scrolls the tags
  sideways in one row, two tags with notes filled it). On a phone both take no typing
  (`filter_mode=None`: no keyboard, `inputMode` none, checked in Chrome). A new main scenario takes
  the old one into the comparison, first (`promoted`, `_moved` in `on_change`, by the value bound
  when the select drew). `app.yaml` keeps one list, the main one first: the guard lists `scenarios`
  old to new, `Save` writes it as one revision `Scenarios: main scenario`
  (`scenariofiles.save_default_scenarios`, as `Set as default` of the explorer; the last choice
  wins), off while the choice equals the list (an empty list counts as the first file that runs).
  The widgets are keyed by the list of `app.yaml`: a rename, a delete or a save elsewhere starts
  them anew (holding the old stem, one tap dropped it).
- The chooser `Edit scenario` (the scenario of the tabs) lists every scenario file in the order of
  its `extends` tree (`tree`: each root, then its children below it, each level without regard to
  case; a missing parent or the first file of a cycle is a root) as `stem · name`, `↳` below its
  parent, em spaces deeper, `(template)` for `abstract` (`label`). A select box with
  `persist_state="session"`: the choice survives a page switch. On a phone pills (a select box can
  open the keyboard) in a popover that names the choice with a pencil (`CHOOSER`) and closes on a
  tap (`fileactions.shut`): ten scenarios of pills filled the screen. It opens on the main scenario
  (`opening`). The query `?scenario=<stem>` opens one (`ui.SCENARIO`, removed once read: the
  hand-off of another page, the Overview and the explorer), with `&event=<type>` on the `Events` tab
  at that type (`ui.EVENT`, `events.open_type`), else `&tab=<title>` on that tab (`ui.TAB`, `TABS`,
  English titles: `Phases` for a phase before the new start of a roll; the strip shows them in words
  of the session and, stateless, opens on its default after a switch of the language: a key does not
  keep it). A file action and `Open <parent>` choose through `PENDING` or a callback: a drawn widget
  takes no new value in its run.
- File actions beside it (`src/dagobert/ui/fileactions.py`), on a phone in the popover `File`, its
  buttons in a row that wraps (a column of four ran past the screen in landscape), which a tap on an
  action closes (`key` and `on_change`: it covered the dialog): `New` (name first, then the file
  name, whose placeholder and default `ui.slug` makes of the name, `Früh in Rente!` gives
  `frueh-in-rente`; `Extends` at the main scenario, owner 2026-10-16: none dropped the phases and
  events of the plan; `Plan.parents`, the main one first, the others, `none: a scenario of its
  own` last, each `stem · name` by `Plan.said`, `titled` and `main_marked` on the raw files: a
  template is a parent, so not `ui.scenario_titles`; on a phone no typing, `filter_mode=None`),
  `Copy` (name and file name; the text with its comments and parent), `Rename file` (the file;
  every `extends` and entry of `app.yaml` follow, the name stays) and `Delete`; beside them, with a
  main scenario, the menu `Check a what-if` (rule `whatifs`). Each is an `st.dialog`, its title
  made per call and the language taken first (rule `i18n`: it reruns alone), that lists what it
  writes through the save
  guard (`listing`: the moved or copied file, each value with the one before, each row that it adds
  to a list or cell that it changes, the removed files; a value in words, never a Python repr,
  `worded`: phase changes `Work from 2026-10` by their labels, also a label that the edits define,
  events by `lineage.worded`, a stream kind by its title, a month `2026-10`; `features_off` per
  feature `job loss off → on`, as the Features page; `lines`, a line that the action words
  itself: the shift of `Stop earlier`, rule `whatifs`) or why it is refused
  (`Refused:`, `literal`: the store names the characters in words), says why its button is off
  (`why`: `Type a name first.`), and writes it as one revision `Scenarios: new b`, `Scenarios:
  rename scenarios/a.yaml → scenarios/b.yaml` (`revisions.renaming`: the Overview and the Flows
  comparison keep the days before it) (`scenariofiles.act`). A file name field has no capital first
  letter on a phone (`nocaps-`). The write checks what the run before listed for the same inputs
  (`LISTED`, `save.listed`; a refusal now keeps the button off): a file changed since refuses it
  (`save.changed_at`). After a rename or a delete the selections of other pages in the session
  follow (`FOLLOW`: the explorer's scenarios, the Cashflows and the Flows scenario; `followed`). A
  written action says what it did in a toast of the next run (`ui.tell`, `Created Früh in Rente!,
  which extends plan`): the dialog closes with a rerun, or `fileactions.confirm(page=)` opens that
  page of the navigation (`st.switch_page`; a page drawn alone stays).
- `Check a what-if` (owner 2026-10-16, for a first-time user; `ui/whatifs.menu`, rule `whatifs`):
  a popover after the file actions, also on a phone (no popover in `File`), with `Stop earlier`,
  `Lose the job` (the former `Add a job loss`: the month of the loss and, optional, of a new job,
  `scenariofiles.lost_job`, rule `store`; a new job where the main scenario is unemployed or has
  no phase is `Refused:`), `Take a course`, `Start a business`, `Buy a property`. Each dialog ends
  with `confirm(page="Overview")`: one revision `Scenarios: what-if <stem>`, the chooser takes the
  stem (`PENDING`) and the Overview opens on its block `What-ifs`. It shows in both modes (rule
  `mode`).

## Tabs

- On a phone the tab bar stays below the page header while a tab scrolls (`scenarios-tabs`, the
  container of the tabs; not the tabs of the event types), so the timeline gets the screen of a
  landscape phone. Its grids fade at the right edge while columns hide there (rule `page-style`).

- `Timeline`, read only (`timeline`): every phase and event that a run sees, after the `shift` and
  `events` overrides of the chain (`loader.written`), by month, an inheritance without a month after
  the dated rows with `at death` (`lineage.AT_DEATH`: the long `at_death` was cut in the month
  column), the givers and the sum of an inheritance or a gift as its detail (`lineage.describe`,
  after its note), a sale on a condition last with `on condition` as its month
  (`lineage.ON_CONDITION`, the word of the Cashflows page) and the condition after its detail, the
  type in words (`lineage.TITLES`, `Phase`), a phase by its label (`references.phases`, as the pages
  of the plan; a grid select writes its name); `set in` names the file of each, `this scenario` for
  its own (`lineage.THIS`). The phases and events of a parent that a file below drops follow with
  `left out by` (`lineage.inherited`, raw chain), a column only while one is dropped (`_marked`),
  before `detail` (`lineage.read_only`), so it shows without a scroll. `month` is pinned on a phone;
  on a desktop `detail` takes `DETAIL` px (`lineage.DETAIL`), as a cell does not wrap. The ids (the
  Overrides tab names items by them) show with `All columns` (`lineage.read_only(hidden=)`). Without
  a row an info names the tabs that add them. Below it `Open the parent <stem>` for each parent, the
  nearest first, and, unless a template, `Compare with <name> in the Explorer` (`compare_label`: the
  nearest parent that runs; `Run it in the Explorer` without one), a link with `?compare=<stem>`
  (rule `explorer`).
- `General`: a `forms.Form` on the scenario file with `name`, `note`, `extends` (empty: `none: a
  scenario of its own`, through `NULLS`; off where every other scenario extends it, rule `forms`)
  and `abstract` (label `Template: only a base for others, never run`). `drop` is no field here: the
  toggles of `Phases` and `Events` leave out the items of the parents where they show
  (`lineage.leave_out`), saved with the Save of `Phases` or of the type open in `Events`.
  `extends` offers the scenarios that do not extend it (`scenariofiles.parents`, so no cycle). The scenarios that extend it are named: a change reaches
  them. `refusals` (no model checks these) keeps Save off for a name of another scenario and for
  `Template` on the last scenario that runs: a warning, and `forms.save(ready=False)`; the write
  checks again (a `save.Grid` without edits).
- `Phases`: `phases.tab`. One form with the `phases` grid (`from` pinned on a phone; then `age`, the
  age in whole years at the month as saved, `tables.Computed` through `Form.computed`: a grid keeps
  its edits only while its data stays, so the guard says the age of a new month, `ui.at_age`;
  `phase` a select of the phases of `assumptions.yaml` in their order by their labels as written,
  `Column.words`, `references.phases`, no new name: a scenario defines none; `PHASE_HELP` names
  the Assumptions page; `id` only in advanced mode, `Form.hides`, with the note `Hidden in simple
  mode: ids.`; a row added or changed without an id takes one before the guard lists it,
  `phase_ids` through `forms.Shown.fill`: its phase, else with its year, `retired-2051`, else
  numbered, none that the chain holds, so the seek `Stop working` and the month sliders of the
  Explorer reach a plain plan). A new row whose phase a change of a parent that runs has
  (`repeats`) warns that that change stays, and where it has an id a toggle `Move <id (1 phase and
  2 events)> to <month (age)> instead` saves its move and leaves the row out of the save
  (`_without`; the grid shows it until the save starts it anew: a page cannot remove a row of a
  grid); the toggle is keyed by the phase and month of its row, so a row deleted above keeps it
  with its row. Below `Inherited phases`: a toggle per id of those that reach it (`lineage.reach`,
  `lineage.leave_out`), then the changes of the parents in a grid of fixed rows (`_moves`) by
  month, a timeline whatever file holds them, the month as the run sees it (`moving`, after
  `lineage.shifts`) the one cell to edit, `age`, the
  phase by its label, the id in advanced mode, `left out by` while one is dropped, `set in`. A month
  typed there saves `overrides.shift.<id>` of the file (`shifted`: the months from the month that
  the parent writes, cleared where that is what the parents give, so an emptied cell takes their
  month again; a child's shift replaces its parent's, `loader.merged_overrides`); a row without an
  id or one left out moves nothing and the guard notes it, so does a text that is no month
  (`2051-13`: it keeps its month, `typed_moves`). An id moves as one: the guard notes the new month
  of its other rows (`along`; the grid keeps their months until the save: new data would drop its
  edits), also of one whose month typed does not count. The guard lists `move retirement (1
  phase) 2051-06 (age 65) → 2049-06 (age 63)`. Its base (`Placed`) keeps the rows and a
  `revisions.Seen` per file of the chain of what places them (`_placing`: phases, drops, shifts,
  the revision taken before the read): a change without an edit starts it anew, with one a
  warning, `Discard my edits` and Save off; the write checks again. One Save for the tab (owner
  2026-10-16: three Saves read as three save models): the form, the moves and the drops as one
  revision; the Events tab saves its drops with the grid of the type open (rule `events`), the
  main scenario box has its own (`app.yaml`).
- `Events`: `events.tab` (rule `events`). `Overrides`: `scenario_overrides.tab` (rule
  `scenario-overrides`).
- Simple mode (rule `mode`; `mode.view` once per run): `Overrides` shows while the scenario holds
  `overrides` or `drop` (`Uses.overrides`; the Explorer's save writes `scale` overrides), a link
  asks for it (`?tab=Overrides`) or a form or grid of it holds an edit not saved yet
  (`scenario_overrides.unsaved`: a tab left out drops its widget state); else a note below the tabs
  names it (`Hidden in simple mode: Overrides.`). `General` takes `Template` (`TEMPLATE`) only for a
  template or a field with an edit (`forms.edited`), else the note `Template`; its `parts` keep the
  four keys (rule `forms`). The strip of the tabs is a new one when its titles change: it opens on
  its default after the switch.
- A tab with a form pins its Save into the header (`tables.SAVE_IN_HEADER`, its first element). Its
  revision source names the scenario (`forms.save` with `action`: `Scenarios: keep-flat`).
