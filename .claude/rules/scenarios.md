---
paths:
  - "src/dagobert/ui/{scenarios,fileactions}.py"
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
  `frueh-in-rente`; parent), `Copy` (name and file name; the text with its comments and parent),
  `Rename file` (the file; every `extends` and entry of `app.yaml` follow, the name stays),
  `Delete`. Each is an `st.dialog`, its title made per call and the language taken first (rule
  `i18n`: it reruns alone), that lists what it writes through the save guard (`listing`: the moved
  or copied file, each value with the one before, the removed files) or why it is refused
  (`Refused:`, `literal`: the store names the characters in words), says why its button is off
  (`why`: `Type a name first.`), and writes it as one revision `Scenarios: new b`, `Scenarios:
  rename scenarios/a.yaml → scenarios/b.yaml` (`revisions.renaming`: the Overview and the Flows
  comparison keep the days before it) (`scenariofiles.act`). A file name field has no capital first
  letter on a phone (`nocaps-`). The write checks what the run before listed for the same inputs
  (`LISTED`, `save.listed`; a refusal now keeps the button off): a file changed since refuses it
  (`save.changed_at`). After a rename or a delete the selections of other pages in the session
  follow (`FOLLOW`: the explorer's scenarios, the Cashflows and the Flows scenario; `followed`). A
  written action says what it did in a toast of the next run (`ui.tell`, `Created Früh in Rente!,
  which extends plan`): the dialog closes with a rerun.

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
  (`lineage.leave_out`). `extends` offers the scenarios that do not extend it
  (`scenariofiles.parents`, so no cycle). The scenarios that extend it are named: a change reaches
  them. `refusals` (no model checks these) keeps Save off for a name of another scenario and for
  `Template` on the last scenario that runs: a warning, and `forms.save(ready=False)`; the write
  checks again (a `forms.Grid` without edits).
- `Phases`: one form with the `phases` grid (`from` pinned on a phone; `phase` a select of the
  phases of `assumptions.yaml` in their order, `references.phases`, no new name: a scenario defines
  none; `PHASE_HELP` names the Assumptions page; a row added or changed without an id takes one
  before the guard lists it, `phase_ids` through `forms.Shown.fill`: its phase, else with its year,
  `retired-2051`, else numbered, none that the chain holds, so the seek `Stop working` and the month
  sliders of the Explorer reach a plain plan), and below it `Inherited phases`: a toggle per id of
  those that reach it (`lineage.reach`, `lineage.leave_out`) with `Save what to leave out`, then the
  phases of the parents read only (`inherited_phases`, raw chain), each with its file (`set in`)
  and, where a file below drops its id, `left out by`.
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
