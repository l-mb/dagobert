"""What-if explorer: sliders become assumption overrides, nothing is written until you save. Its
words follow the language of the page, its cache keys hold none: a switch of the language runs
nothing again."""

from __future__ import annotations

import json
import math
import time
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.elements.lib.column_types import ColumnConfig

from dagobert import anatomy, budget, goalseek, loader, report, revisions, sensitivity, series
from dagobert.difference import Difference
from dagobert.history import actual_totals
from dagobert.i18n import N_, _, ngettext
from dagobert.loader import (
    load_assumptions,
    load_plan,
    load_scenario,
    load_streams,
    nested,
)
from dagobert.model.base import KeyPath
from dagobert.model.plan import SCENARIO_KEYS, Feature, Plan
from dagobert.money import format_eur, format_percent
from dagobert.problems import InputError
from dagobert.report.anatomy import reading
from dagobert.report.charts import run_out
from dagobert.report.summary import Shown
from dagobert.result import RunResult
from dagobert.runner import ModelName, Options
from dagobert.scenariofiles import (
    act,
    concrete_scenarios,
    created,
    default_scenarios,
    save_default_scenarios,
    scenario_file,
    scenario_labels,
)
from dagobert.sensitivity import Lever, Sensitivity
from dagobert.ui import (
    COMPARE,
    SCENARIO,
    Stamp,
    chart,
    fixed,
    is_mobile,
    literal,
    main_marked,
    mode,
    note,
    page_link,
    run_stamp,
    scenario_note,
    source,
)
from dagobert.ui.gridcolumns import on_off
from dagobert.ui.knobs import NO_SALARIES, STANDING, Salaries, classes, knobs, switches
from dagobert.ui.runs import (
    PATHS,
    TICK,
    cached,
    cached_run,
    keep,
    models,
    options,
    pool,
    settle,
    submit,
    throttled,
    workers,
    yielded,
)
from dagobert.ui.save import REFUSED, reason
from dagobert.ui.seek import goal_seek, work_dials
from dagobert.ui.sliders import ALL_SPENDING, GROUPS, KEY, Knob, Switch, forget
from dagobert.ui.tables import COLUMNS_MEAN, PHONE_PINNED, column_help, pin

PATH_CHOICES = (200, 500, 1000, 5000)
# the columns of the summary that a phone shows unless `All columns` is on
PHONE_COLUMNS = ("Scenario", report.BROKE_AT, report.TOTAL_AT)  # those of the strip, as they fit
MOVED_SHOWN = 3  # moved sliders named in the line above the table, more fold into a popover
# pixels of the `Scenario` column of the summary on a desktop, at most: the grid measures text
# roughly and cut a long name, so two variants of a plan looked the same. A column of short names
# takes 6.5 pixels per character (the font takes 5.5 to 6.2 for a name, 11 for a `W`) and the
# padding of a cell, so the headers keep the room: names of up to 16 characters fit 1,500 pixels.
SCENARIO_WIDTH = 400
CHAR_WIDTH, NAME_PAD = 6.5, 24
# pixels of a column of the summary with a change in brackets that its header does not hold: money
# needs more than a share, an age or a count of months; the lifetime chance has a long header
# (the least, English); a longer header, German for one, takes `HEADER_PAD` and `HEADER_CHAR` pixels
# per character (`summary_widths`)
CHANGED_WIDTHS = {
    c.term: 190
    if c.name in ("Shortfall", "Total@{age}", "Liquid@{age}", "Taxes", "P(broke) alive")
    else 150
    for c in report.COLUMNS
    if c.change
}
HEADER_PAD, HEADER_CHAR = 34, 5.8
MODEL_NAMES: dict[ModelName, str] = {
    "fixed": N_("Fixed"),
    "montecarlo": N_("Monte Carlo"),
    "historical": N_("Historical"),
}
MODEL_HELP = N_(
    "Monte Carlo draws random markets and prices for each path. Fixed runs one path at the mean "
    "values, without care episodes and without a disability but a forced one. Historical replays "
    "the cycles of the equity series since 1970, one path per start month."
)
# On a phone the sidebar covers the page: `Show results` closes it and `Move the sliders` opens
# it. Streamlit has no call for either, so the script clicks its own button of the sidebar.
SIDEBAR_BUTTONS = """<script>
if (!window.dgSidebarButtons) {
  window.dgSidebarButtons = true;
  const clicked = {
    ".st-key-show-results button": '[data-testid="stSidebarCollapseButton"] button',
    ".st-key-open-sliders button": '[data-testid="stExpandSidebarButton"]',
  };
  document.addEventListener("click", (event) => {
    for (const [mine, theirs] of Object.entries(clicked)) {
      if (event.target.closest(mine)) document.querySelector(theirs)?.click();
    }
  }, true);
}
</script>"""
PLAN_KEYS = ("scale", *SCENARIO_KEYS)  # override paths of the plan, not of the world
REST = 2.0  # seconds that the sliders rest before the sensitivity starts
MOVED = "ui-explorer-moved"  # session state: the positions of the sliders and since when (`rested`)
SHOWN = "ui-explorer-sensed"  # session state: the last sensitivity shown per scenario (`_shown`)
RESTING = N_("What moves the result: starts when the sliders rest")

NOMINAL_HELP = N_(
    "Off: euros of the simulation start, each path divided by its own consumer prices, so "
    "medians compare buying power. On: nominal euros, as paid at the time. No new runs."
)
NO_HISTORICAL = N_("Historical needs the equity series `{series}`: fetch or import it first.")


def measures(s: Sensitivity) -> list[str]:
    """The panels of `report.sensitivity_figure` in words, at the ages of the run, of which a phone
    shows one at a time (its selector holds the index)."""
    worth = _("Net worth at {age}")
    return [run_out(s.base.ages[-1]), *(worth.format(age=age) for age in s.base.ages)]


@st.cache_resource(show_spinner=False)
def _found() -> dict[tuple[object, ...], Sensitivity]:
    """Not `st.cache_data`: the run reports progress, and a call into Streamlit is also where
    a moved slider interrupts it."""
    return {}


def said(s: Sensitivity, levers: Sequence[Lever]) -> Sensitivity:
    """`s` in the words of `levers`, those of this run: a lever keys the caches without its words.
    An effect whose lever this run lacks goes (an old result of other sliders, `_levers`)."""
    words = {lever.path: lever for lever in levers}
    return replace(
        s,
        effects=tuple(
            replace(e, lever=replace(e.lever, label=w.label, format=w.format, step=w.step))
            for e in s.effects
            if (w := words.get(e.lever.path)) is not None
        ),
    )


def rested(last: tuple[object, float] | None, sliders: object, now: float) -> tuple[object, float]:
    """The positions of the sliders and since when they stand there: since ever at first, from
    `now` when they differ from `last`."""
    if last is None:
        return sliders, -math.inf
    return last if last[0] == sliders else (sliders, now)


def _rested(opts: Options, overrides: dict[str, Any]) -> float:
    """Since when the sliders, the model and the paths of this session stand where they are."""
    moved = rested(st.session_state.get(MOVED), (opts, json.dumps(overrides)), time.monotonic())
    st.session_state[MOVED] = moved
    return moved[1]


def _shown() -> dict[Path, Sensitivity]:
    """The last sensitivity that this session showed per scenario, without the words of a run."""
    shown: dict[Path, Sensitivity] = st.session_state.setdefault(SHOWN, {})
    return shown


@dataclass(frozen=True)
class Levers:
    """The fold `What moves the result` of the scenario tab `i`, its scenario named as the tab
    names it, and how its charts show."""

    i: int
    scenario: str
    nominal: bool
    compact: bool

    def charts(self, s: Sensitivity, *, fresh: bool) -> None:
        """The plan apart: next to the world its levers never rank. A phone shows the measure of
        its selector, which a fresh result draws, an old one only reads."""
        key = "sensitivity" if fresh else "stale"
        measure = (
            (_measure(s) if fresh else st.session_state.get(f"{KEY}measure", 0))
            if self.compact
            else 0
        )
        for mine in (True, False):
            part = tuple(e for e in s.effects if (e.lever.path[0] in PLAN_KEYS) == mine)
            figure = report.sensitivity_figure(
                replace(s, scenario=self.scenario, effects=part),
                plan=mine,
                nominal=self.nominal,
                compact=self.compact,
                measure=measure,
            )
            chart(figure, key=f"{key}-{self.i}-{mine}")


def _levers(
    job: sensitivity.Job,
    levers: tuple[Lever, ...],
    stamp: Stamp,
    status: Status,
    *,
    fold: Levers,
    since: float,
) -> None:
    """The charts of the fold, in the words of this run (`said`). A miss waits until the sliders
    have rested `REST` seconds (`since`), then runs in the pool, under a progress bar above the
    last result of the scenario that this session showed, faded (`explorer-stale-`), while the
    charts of the run before go at once; a moved slider stops the wait and the run at their next
    tick. A tick draws the bar and the `Status` line at most every `REDRAW` seconds, else it only
    yields (`throttled`). A hit updates the charts in place."""
    found, shown = _found(), _shown()
    key = (job.opts, job.scenario, json.dumps(job.overrides), levers, stamp)
    waiting = st.empty()  # on a hit too: the charts keep their place
    if (result := found.get(key)) is None:
        with waiting.container():
            bar = st.progress(0.0, _(RESTING))
            if (last := shown.get(job.scenario)) is not None:
                st.caption(_("For the sliders before your last move"))
                with st.container(key=f"explorer-stale-{fold.i}"):
                    fold.charts(said(last, levers), fresh=False)
        drawn = st.empty()  # replaces the charts of the run before, which a container would keep
        settle(lambda: time.monotonic() - since >= REST, yielded, time.sleep)
        n = 2 * len(levers)
        text = ngettext("What moves the result: {n} run", "What moves the result: {n} runs", n)
        bar.progress(0.0, text.format(n=n))
        name = load_scenario(job.scenario).name
        busy = ngettext(
            "What moves the result: {n} run of {scenario}, {share}",
            "What moves the result: {n} runs of {scenario}, {share}",
            n,
        )

        def progress(share: float) -> None:
            bar.progress(share, text.format(n=n))
            status.busy(busy.format(n=n, scenario=name, share=format_percent(share, 0)))

        result = keep(
            found,
            key,
            sensitivity.run(job, levers, pool(), workers(), throttled(progress), every=TICK),
        )
        waiting.empty()
        box = drawn.container()
    else:
        box = st.container()
    shown[job.scenario] = result
    with box:
        fold.charts(said(result, levers), fresh=True)


def _salaries(data: Path, scenario: Path) -> Salaries:
    """From the `fixed` run of the files: the numbers of the Flows page, not a copy of the
    rules."""
    result = fixed.result(data, scenario.stem)
    if result is None:
        return NO_SALARIES
    return Salaries(result.scenario, budget.regular_salary(result))


@dataclass(frozen=True)
class Sidebar:
    """The run options, the overrides of the sliders and the same as text, the levers of the
    sensitivity run, the dials of the goal seek, the unit of money, the sliders that act by path
    (`Apply to sliders` of the goal seek sets them) and the widget keys of all (`Reset`)."""

    opts: Options
    overrides: dict[str, Any]
    moved: tuple[str, ...]  # `label from → to` per moved slider
    levers: tuple[Lever, ...]
    dials: tuple[goalseek.Dial, ...]
    nominal: bool
    sliders: Mapping[tuple[str, ...], Knob]
    keys: tuple[str, ...]


@dataclass(frozen=True)
class View:
    """What the sidebar shows of its sliders and switches (rule `mode`): what the page shows
    (`mode.View`) and the return classes of the first scenario (`knobs.classes`)."""

    base: mode.View
    held: frozenset[str]

    def shows(self, path: KeyPath) -> bool:
        """Simple mode leaves out every slider of a class that the plan does not hold."""
        if not self.base.advanced and path[0] == "returns" and path[1] not in self.held:
            return False
        return self.base.shows(mode.Item(mode.Sort.PATH, path))

    def switched_off(self, path: KeyPath) -> Feature | None:
        """The feature off that hides `path` in either mode."""
        found = mode.feature(mode.Item(mode.Sort.PATH, path))
        return found if found in self.base.off else None


@dataclass(frozen=True)
class Drawn:
    """The sliders and switches that the sidebar draws, by group in order, and what it leaves
    out: in words what simple mode hides (a group whole by its name), the features off that hide
    one."""

    groups: dict[str, list[Knob | Switch]]
    expert: list[str]
    off: frozenset[Feature]


def drawn(controls: Sequence[Knob | Switch], view: View, moved: Collection[str]) -> Drawn:
    """A control shows while `view` shows its path or it is `moved` (by key), so a hidden one
    stands at its file value and sets nothing; a group shows with a control in it."""
    groups: dict[str, list[Knob | Switch]] = {}
    for c in controls:
        groups.setdefault(c.group, []).append(c)
    shown: dict[str, list[Knob | Switch]] = {}
    expert: list[str] = []
    off: set[Feature] = set()
    for group, members in groups.items():
        kept = [c for c in members if c.key in moved or view.shows(c.path)]
        left = [c for c in members if c not in kept]
        off |= {f for c in left if (f := view.switched_off(c.path))}
        by_mode = [c.label for c in left if view.switched_off(c.path) is None]
        if kept:
            shown[group] = kept
            expert += by_mode
        elif by_mode:
            expert.append(_(GROUPS[group]))
    return Drawn(shown, expert, frozenset(off))


def _run_options(
    data: Path, *, advanced: bool, compact: bool
) -> tuple[ModelName, int, bool, list[str]]:
    """`Model`, `Paths` and `Nominal euros`, in simple mode each only while it differs from its
    default (`montecarlo`, `PATHS`, off): the model, the paths, the unit, the labels hidden."""
    available = models(data)
    model_key, paths_key, nominal_key = (f"{KEY}{n}" for n in ("model", "paths", "nominal"))
    if st.session_state.get(model_key) not in available:
        st.session_state[model_key] = "montecarlo"
    model: ModelName = st.session_state[model_key]
    paths: int = st.session_state.setdefault(paths_key, PATHS)
    nominal: bool = st.session_state.setdefault(nominal_key, False)
    hidden = []
    if advanced or model != "montecarlo":
        model = (
            st.selectbox(
                _("Model"),
                available,
                format_func=lambda m: _(MODEL_NAMES[m]),
                key=model_key,
                help=_(MODEL_HELP),
            )
            or "montecarlo"
        )
        if "historical" not in available:
            st.caption(_(NO_HISTORICAL).format(series=series.EQUITY))
            page_link("Data", _("Data: fetch or import the series"))
    else:
        hidden.append(_("Model"))
    if advanced or paths != PATHS:
        paths = st.select_slider(
            _("Paths"), PATH_CHOICES, disabled=model != "montecarlo", key=paths_key
        )
    else:
        hidden.append(_("Paths"))
    if advanced or nominal:
        # on a phone the help icon sits in the label, so a tap on it flips the switch
        nominal = st.toggle(
            _("Nominal euros"), key=nominal_key, help=None if compact else _(NOMINAL_HELP)
        )
        if compact:
            st.caption(_(NOMINAL_HELP))
    else:
        hidden.append(_("Nominal euros"))
    return model, paths, nominal, hidden


def _sidebar(
    box: DeltaGenerator,
    data: Path,
    salaries: Salaries,
    first: Plan | None,
    work: Sequence[goalseek.Dial],
    *,
    advanced: bool,
    compact: bool,
) -> Sidebar:
    """The controls in `box` of the sidebar that the mode, the features and the inputs show
    (`View`, `drawn`), with the note of what they hide below the groups. The sliders start at the
    values of the first scenario, its own overrides included; a month slider reaches the range of
    each dial of `work` that moves it. Every group starts closed, the levers of the plan first.
    The buttons stay at the bottom while the sliders scroll (`explorer-actions`); on a phone `Show
    results` closes the sidebar, which covers the page."""
    with box:
        model, paths, nominal, hidden = _run_options(data, advanced=advanced, compact=compact)
        a = first.assumptions if first else load_assumptions(data)
        held = classes(first.assets, first.scenario) if first else STANDING
        view = View(mode.view(data), held)
        base = (
            knobs(a, load_streams(data), salaries, first.scenario, first.assets, work=work)
            if first
            else knobs(a, load_streams(data), salaries)
        )
        controls: list[Knob | Switch] = [*base, *switches(a)]
        layout = drawn(controls, view, {c.key for c in controls if c.moved})
        picked = _Picked()
        for group, members in layout.groups.items():
            with st.expander(
                _(GROUPS[group]),
                expanded=not compact and group == ALL_SPENDING,
                key=f"{KEY}group-{group}",
            ):
                for c in members:
                    if isinstance(c, Switch):
                        picked.flip(c, compact=compact)
                    else:
                        picked.slide(c, model)
        mode.hidden_note([*hidden, *layout.expert], layout.off, held=mode.Held.VALUES)
        keys = tuple(c.key for c in controls)
        actions = st.container(key="explorer-actions", horizontal=True)
        # no `KEY`: `main.py` cannot carry a button
        actions.button(_("Reset sliders"), key="sliders-reset", on_click=forget, args=(keys,))
        if compact:
            actions.button(_("Show results"), key="show-results", type="primary")

    opts = options(data, model, paths)
    return Sidebar(
        opts,
        nested(picked.changes),
        tuple(picked.moved),
        tuple(picked.levers),
        tuple(picked.dials),
        nominal,
        picked.sliders,
        keys,
    )


@dataclass
class _Picked:
    """What the drawn sliders and toggles of the sidebar set: the overrides by path, the moved
    ones as text, the levers of the sensitivity run, the dials of the goal seek and the sliders
    that act by path."""

    changes: dict[tuple[str, ...], float | bool] = field(default_factory=dict)
    moved: list[str] = field(default_factory=list)
    levers: list[Lever] = field(default_factory=list)
    dials: list[goalseek.Dial] = field(default_factory=list)
    sliders: dict[tuple[str, ...], Knob] = field(default_factory=dict)

    def slide(self, k: Knob, model: ModelName) -> None:
        """A slider that its model does not read keeps its position for another one."""
        acts = model in k.models
        v = k.slider(disabled=not acts)
        if not acts:
            return
        self.sliders[k.path] = k
        dial = k.dial(v)
        if abs(v - k.value) > 1e-9:
            self.changes[k.path] = v
            self.moved.append(f"{k.label} {dial.text(k.value)} → {dial.text(v)}")
        self.levers.append(k.lever(v))
        self.dials.append(dial)

    def flip(self, t: Switch, *, compact: bool) -> None:
        on = t.toggle(compact=compact)
        if on != t.value:
            self.changes[t.path] = on
            self.moved.append(f"{t.label} {on_off(t.value)} → {on_off(on)}")


def _save_form(data: Path, parents: list[Path], overrides: dict[str, Any]) -> None:
    """The keys hold no `KEY`: a page switch starts the form anew, and the file name anew with
    each parent."""
    with st.expander(_("Save the sliders as a scenario"), expanded=False, key="whatif-open"):
        parent = st.selectbox(_("Extends"), [p.stem for p in parents], key="whatif-parent")
        name = st.text_input(_("File name"), f"{parent}-whatif", key=f"whatif-name-{parent}")
        if st.button(_("Write scenario"), key="whatif-write", disabled=not overrides):
            try:
                act(data, lambda d: created(d, name, name, parent, overrides), source=source())
            except (revisions.ConflictError, *REFUSED) as err:
                st.error(_("Not saved: {reason}").format(reason=reason(err)))
            else:
                st.success(_("Wrote {file}").format(file=scenario_file(name)))
                page_link(
                    "Scenarios",
                    _("{name} on the Scenarios page").format(name=name),
                    {SCENARIO: name},
                )


def _grid(rows: list[dict[str, Any]], config: dict[str, ColumnConfig] | None = None) -> None:
    """The first column names the row: on a phone it stays in view while the rest scrolls."""
    first = next(iter(rows[0]))
    config = config or {first: st.column_config.Column()}
    pin(config, first)
    st.dataframe(rows, hide_index=True, column_config=config)


def above(path: Path, among: Collection[str]) -> str | None:
    """The nearest scenario of the `extends` chain of `path` among the stems `among`, None for
    none or a chain that does not load."""
    try:
        chain = loader.chain(path)
    except InputError:
        return None
    return next((p.stem for p, _ in reversed(chain[:-1]) if p.stem in among), None)


def extended(chosen: Mapping[Path, str]) -> dict[str, str]:
    """By the label of each chosen scenario (`scenario_labels`, which tells a shared name apart),
    the label of the nearest chosen one that it extends: the run of a scenario and that of its
    parent pair up in the difference."""
    labels = {p.stem: label for p, label in chosen.items()}
    return {
        label: labels[parent]
        for p, label in chosen.items()
        if (parent := above(p, labels)) is not None
    }


def pair(names: Sequence[str], parents: Mapping[str, str]) -> tuple[str, str]:
    """A and B of the difference at first: the first run whose scenario extends another chosen one
    as B, that one as A (buy or rent: B less A is the purchase); else the first two."""
    return next(((parents[n], n) for n in names if parents.get(n) in names), (names[0], names[1]))


def _difference(
    results: list[RunResult], parents: Mapping[str, str], *, nominal: bool, compact: bool
) -> None:
    """Two of the runs path by path: a scenario and the one that it extends (`pair`) unless
    chosen. A select holds the id of a run, its scenario and whether it is a twin, and shows its
    label: the label of a twin is words."""
    st.subheader(_("Difference of two runs"))
    labels = {(r.scenario, r.twin): r.label for r in results}
    ids = list(labels)
    by_label = {label: run for run, label in labels.items()}
    first = [by_label[label] for label in pair(list(labels.values()), parents)]
    left, right = st.columns(2)
    picks: list[tuple[str, bool]] = []
    for column, side, tip, start in (
        (left, "A", _("The run that B is compared with."), first[0]),
        (right, "B", _("The run whose difference from A the table and the chart show."), first[1]),
    ):
        key = f"{KEY}difference-{side}"
        # a run that left the selection gives way to the first run that the other side does not show
        other = picks[0] if picks else st.session_state.get(f"{KEY}difference-B")
        default = start if start != other else next(run for run in ids if run != other)
        if st.session_state.get(key) not in ids:
            st.session_state[key] = default
        picks.append(
            column.selectbox(side, ids, format_func=labels.__getitem__, key=key, help=tip)
            or default
        )
    a, b = (results[ids.index(run)] for run in picks)
    try:
        difference = Difference.of(a, b, nominal=nominal)
    except ValueError as err:
        st.warning(str(err))
        return
    st.caption(_("{b} less {a}").format(b=literal(difference.b), a=literal(difference.a)))
    _grid(report.difference_table(difference, compact=compact))
    chart(report.difference_figure(difference, compact=compact), key="difference")
    note(_(report.DIFFERENCE_NOTE))


def _scenarios(data: Path, *, compact: bool) -> dict[Path, str]:
    """The chosen scenarios with their names. A phone picks from pills, as many rows as they
    need, and the button goes below them: the input of a multiselect can open the keyboard. The
    options show the names of the scenarios, the main one (`first_scenario`) marked, the help their
    files and the start of their notes."""
    concrete = concrete_scenarios(data)
    loaded = {stem: load_scenario(path) for stem, path in concrete.items()}
    labels = scenario_labels({stem: s.name for stem, s in loaded.items()})
    saved = default_scenarios(data)
    shown = main_marked(labels, (saved or list(concrete))[0])
    key = f"{KEY}scenarios"
    if (handed := st.query_params.pop(COMPARE, None)) in concrete:  # from the Scenarios page
        st.session_state[key] = compared_with(concrete, handed)
        for side in ("A", "B"):
            st.session_state.pop(f"{KEY}difference-{side}", None)
    st.session_state.setdefault(key, saved or list(concrete)[:3])
    about = "\n".join(
        f"- **{literal(labels[stem])}** (`{stem}.yaml`)"
        + (f": {literal(s.note.split('. ')[0].rstrip('.'))}." if s.note else "")
        for stem, s in loaded.items()
    )
    row = st.container(horizontal=not compact, vertical_alignment="bottom")
    chosen: list[str] = (
        row.pills(
            _("Scenarios"),
            list(concrete),
            selection_mode="multi",
            format_func=shown.__getitem__,
            key=key,
            help=about,
        )
        if compact
        else row.multiselect(
            _("Scenarios"), list(concrete), format_func=shown.__getitem__, key=key, help=about
        )
    )
    if row.button(
        _("Set as default, the first as main"),
        key="set-default",  # no `KEY`: `main.py` cannot carry a button
        disabled=not chosen or chosen == saved,
        width="content",
        help=(
            _("Choose a scenario first.")
            if not chosen
            else _("This choice is the default already.")
            if chosen == saved
            else _(
                "The Explorer opens with this choice, and its first scenario, {scenario}, becomes "
                "your main scenario: the Overview, Cashflows and Flows pages show "
                "it. The top of the Scenarios page sets the same."
            ).format(scenario=literal(labels[chosen[0]]))
        ),
    ):
        try:
            save_default_scenarios(data, chosen, source=source())
        except OSError as err:
            st.error(_("Not saved: {reason}").format(reason=reason(err)))
        else:
            st.rerun()
    if compact and chosen and chosen != saved:  # pills show no order, a touch screen no help
        row.caption(
            _("Set as default makes {scenario}, the first one chosen, your main scenario.").format(
                scenario=literal(labels[chosen[0]])
            )
        )
    if not chosen:
        st.info(_("Choose a scenario."))
    return {concrete[name]: labels[name] for name in chosen if name in concrete}


def compared_with(concrete: Mapping[str, Path], stem: str) -> list[str]:
    """The scenarios of a comparison of `stem` (`?compare=`): the nearest one that it extends and
    that runs, then `stem`; alone without one."""
    return [*filter(None, [above(concrete[stem], concrete)]), stem]


def _pairs(results: list[RunResult]) -> list[tuple[RunResult, RunResult | None]]:
    """Each run of the sliders with its run of the files, if there is one."""
    files = {r.scenario: r for r in results if r.twin}
    return [(r, files.get(r.scenario)) for r in results if not r.twin]


def compared(results: list[RunResult], *, nominal: bool) -> list[dict[str, str]]:
    """The summary of the runs of the sliders, keyed by term (`report.summary_table`), the
    change against the run of the files in brackets in the columns of `COMPARED`."""
    rows = []
    for r, files in _pairs(results):
        row = report.summary_table([r], nominal=nominal)[0]
        if files is not None:
            mine, theirs = (report.summary_row(x, nominal=nominal) for x in (r, files))
            for term, change in report.changes(mine, theirs).items():
                row[term] += f" ({change})"
        rows.append(row)
    return rows


def strip(results: list[RunResult], *, nominal: bool) -> str:
    """Markdown of P(broke)@90 and Total@67 of each scenario (`report.summary_row`), the change
    against its run of the files in brackets, a line per scenario: the results of a phone, where
    the sidebar covers the page. Its caption names the figures."""
    lines = []
    for r, files in _pairs(results):
        row = report.summary_row(r, nominal=nominal)
        broke, worth = format_percent(row.p_broke, 0), format_eur(row.median_total)
        if files is not None:
            moved = report.changes(row, report.summary_row(files, nominal=nominal))
            broke += f" ({moved[report.BROKE_AT]})"
            worth += f" ({moved[report.TOTAL_AT]})"
        lines.append(f"**{literal(r.label)}** {broke} · {worth}")
    return "  \n".join(lines)


def summary_widths(
    names: list[str], columns: Sequence[Shown], *, compact: bool, changed: bool
) -> dict[str, int]:
    """The pixels of the columns of the summary that the grid would size too narrow: the
    `Scenario` column, pinned and narrower on a phone, on a desktop as wide as its longest name up
    to `SCENARIO_WIDTH`, and with a run of the files the columns of `CHANGED_WIDTHS`. The grid
    keeps the widths of its first data."""
    longest = round(NAME_PAD + CHAR_WIDTH * max(map(len, ["Scenario", *names])))
    return {"Scenario": PHONE_PINNED if compact else min(SCENARIO_WIDTH, longest)} | (
        {
            c.term: max(CHANGED_WIDTHS[c.term], round(HEADER_PAD + HEADER_CHAR * len(c.label)))
            for c in columns
            if c.term in CHANGED_WIDTHS
        }
        if changed
        else {}
    )


def _summary(results: list[RunResult], *, nominal: bool, compact: bool) -> None:
    """The runs of the sliders, the numbers right. On a phone the `Scenario` column is narrower
    and stays in view while the numbers scroll, and the table shows the columns of `PHONE_COLUMNS`
    unless `All columns` is on; the help of the columns sits in a popover beside it."""
    columns = report.summary_columns(results, nominal=nominal)
    if compact:
        row = st.container(horizontal=True, vertical_alignment="center")
        with row:
            everything = st.toggle(_("All columns"), key=f"{KEY}all-columns")
            column_help({c.label: c.tip for c in columns[1:]}, COLUMNS_MEAN)
        if not everything:
            columns = [c for c in columns if c.term in PHONE_COLUMNS]
    rows = compared(results, nominal=nominal)
    widths = summary_widths(
        [str(row["Scenario"]) for row in rows],
        columns,
        compact=compact,
        changed=any(r.twin for r in results),
    )
    _grid(
        [{c.term: row[c.term] for c in columns} for row in rows],
        {
            c.term: st.column_config.Column(
                c.label,
                help=c.tip,
                width=widths.get(c.term),
                alignment=None if c.term == "Scenario" else "right",
            )
            for c in columns
        },
    )
    money = _("Money in {unit}.").format(unit=results[0].unit(nominal=nominal))
    st.caption(money if compact else f"{money} {_('Hover over a column title for its meaning.')}")


def _measure(s: Sensitivity) -> int:
    """The panel of the sensitivity charts that a phone shows. It sits in a fold of a tab, which
    drops its state when it closes: `persist_state`."""
    key = f"{KEY}measure"
    st.session_state.setdefault(key, 0)
    words = measures(s)
    measure: int | None = st.segmented_control(
        _("Show the effect on"),
        range(len(words)),
        format_func=words.__getitem__,
        required=True,
        key=key,
        persist_state="page",
    )
    return measure or 0


@dataclass(frozen=True)
class Status:
    """One line above the table, which never goes: what runs, then what ran or why it did not."""

    slot: DeltaGenerator
    strip: DeltaGenerator | None = None  # of a phone, whose open sidebar covers the page

    def busy(self, text: str, then: str = "") -> None:
        self.slot.caption(f":material/hourglass_top: {text} …{then}")

    def done(self, text: str) -> None:
        self.slot.caption(text)

    def refused(self, err: InputError) -> None:
        """The problem of slider positions that the model refuses, instead of the results: below
        the moved sliders and in the strip of a phone."""
        self.done(
            _("Not simulated: the inputs do not allow the sliders where they stand. Move one back.")
        )
        problem = literal(str(err))
        st.warning(problem, icon=":material/error:")
        if self.strip is not None:
            self.strip.warning(problem, icon=":material/error:")


def _moved(side: Sidebar) -> None:
    """Always one line with its button, so the table does not jump when the first slider
    moves. More than `MOVED_SHOWN` moved sliders (all spending after `Apply to sliders`) made a
    line of many: a popover lists them."""
    row = st.container(horizontal=True, vertical_alignment="center")
    moved, changes = side.moved, _("In brackets: the change against the run (as saved).")
    if len(moved) > MOVED_SHOWN:
        label = ngettext("{n} slider moved", "{n} sliders moved", len(moved))
        # a key: without one the label, which holds the count, is its identity
        row.popover(label.format(n=len(moved)), width="content", key="sliders-moved").markdown(
            "\n".join(f"- {literal(m)}" for m in moved)
        )
        row.caption(changes)
    else:
        row.caption(
            f"{_('Sliders moved: {moved}.').format(moved=' · '.join(moved))} {changes}"
            if moved
            else _("The sliders stand at the values of the run (as saved).")
        )
    row.button(
        _("Reset sliders"),
        key="sliders-reset-moved",  # no `KEY`: `main.py` cannot carry a button
        on_click=forget,
        args=(side.keys,),
        disabled=not side.moved,
        width="content",
    )


def _how(opts: Options, scenarios: int) -> str:
    runs = {
        "montecarlo": _("Monte Carlo, {paths} paths"),
        "fixed": _("fixed, one path at the means"),
        "historical": _("historical cycles"),
    }[opts.model].format(paths=opts.paths)
    how = ngettext("{n} scenario, {runs}", "{n} scenarios, {runs}", scenarios)
    return how.format(n=scenarios, runs=runs)


def _fold(title: str, key: str, *, folded: bool, expanded: bool = False) -> DeltaGenerator | None:
    """A group of charts of a scenario tab. `folded` (a phone, simple mode, the sensitivity): a
    fold that draws them only while open, as the page is long and the sensitivity takes most of a
    run. None while closed."""
    if not folded:
        return st.container()
    fold = st.expander(title, expanded=expanded, key=key, on_change="rerun")
    return fold if fold.open else None


def _tab(
    i: int,
    r: RunResult,
    observed: report.Observed,
    *,
    nominal: bool,
    compact: bool,
    folded: bool,
    plan: bool,
) -> DeltaGenerator | None:
    """The charts of a scenario tab, compact on a phone, and the slot of its sensitivity when
    `plan` (a run of the files has none) and its fold is open: a fold on a desktop too, as the
    sensitivity takes most of a run."""
    scenario_note(r.note)
    if (
        box := _fold(_("Net worth"), f"{KEY}fold-worth-{i}", folded=folded, expanded=True)
    ) is not None:
        with box:
            chart(report.liquid_fan_figure(r, nominal=nominal, compact=compact), key=f"fan-{i}")
            chart(
                report.balance_figure(r, observed, nominal=nominal, compact=compact),
                key=f"balance-{i}",
            )
    if (box := _fold(_("Will the money last?"), f"{KEY}fold-last-{i}", folded=folded)) is not None:
        with box:
            chart(report.lasting_figure(r, nominal=nominal, compact=compact), key=f"lasting-{i}")
            st.caption(report.lasting_reading(r))
    if (
        box := _fold(_("Income, spending and taxes"), f"{KEY}fold-flow-{i}", folded=folded)
    ) is not None:
        with box:
            chart(report.flow_figure(r, nominal=nominal, compact=compact), key=f"flow-{i}")
    why = anatomy.of(r)
    if (
        why is not None
        and (box := _fold(_("Why paths run out"), f"{KEY}fold-why-{i}", folded=folded)) is not None
    ):
        with box:
            chart(report.anatomy_figure(why, compact=compact), key=f"anatomy-{i}")
            if compact:
                st.caption(" ".join(reading(why)))
    if not plan:
        return None
    box = _fold(_("What moves the result"), f"{KEY}fold-levers-{i}", folded=True)
    return None if box is None else box.container()


def _runs(
    opts: Options, chosen: Mapping[Path, str], overrides: dict[str, Any], stamp: Stamp
) -> list[tuple[Path, RunResult]]:
    """The runs of the chosen scenarios but the abstract ones by their file, named as the select
    shows them: two scenarios of one name differ by their file."""
    return [
        (p, replace(r, scenario=chosen[p]))
        for p in chosen
        if (r := cached_run(opts, p, json.dumps(overrides), stamp)) is not None
    ]


def _results(
    opts: Options,
    chosen: Mapping[Path, str],
    overrides: dict[str, Any],
    stamp: Stamp,
    status: Status,
) -> list[tuple[Path, RunResult]]:
    """The runs with the sliders, then, with a slider moved, those of the files as twins: the same
    scenarios as the files define them, in the charts and tabs. The runs that the cache lacks
    start together in the pool, and `status` says `Simulating` while they run: a hit takes no time
    and must not look like a run. The runs of the files come first: inputs that do not load raise
    there (`main.py` shows them), so a refusal of the runs with the sliders is one of their
    positions, which `status` names: no results."""
    missing = [
        (p, o)
        for o in dict.fromkeys(("{}", json.dumps(overrides)))
        for p in chosen
        if not cached(opts, p, o, stamp)
    ]
    if missing:
        status.busy(
            _("Simulating {how}").format(how=_how(opts, len(chosen))),
            f" {_('A faded result below is the last one.')}",
        )
    for p, o in missing:
        submit(opts, p, o, stamp)
    files = _runs(opts, chosen, {}, stamp)
    if not overrides:
        return files
    try:
        results = _runs(opts, chosen, overrides, stamp)
    except InputError as err:  # a range that a file value widened: a ceiling at the trigger
        status.refused(err)
        return []
    return [*results, *((p, replace(r, twin=True)) for p, r in files)]


def _fill_strip(
    box: DeltaGenerator, results: list[RunResult], *, changed: bool, nominal: bool
) -> None:
    """The lines of `strip` with the caption that names its figures."""
    box.markdown(strip(results, nominal=nominal))
    headers = {c.term: c.label for c in report.summary_columns(results, nominal=nominal)}
    box.caption(
        (
            _("{broke} · {worth}, in {unit}; in brackets the change against the run (as saved).")
            if changed
            else _("{broke} · {worth}, in {unit}.")
        ).format(
            broke=headers[report.BROKE_AT],
            worth=headers[report.TOTAL_AT],
            unit=results[0].unit(nominal=nominal),
        )
    )


def _sidebar_buttons() -> None:
    """On a phone the sliders sit in the closed sidebar, which nothing else points to."""
    st.button(_("Move the sliders"), key="open-sliders", icon=":material/tune:")
    st.html(SIDEBAR_BUTTONS, unsafe_allow_javascript=True)


def page(data: Path) -> None:
    st.title(_("Explorer"))
    compact = is_mobile()
    if compact:
        _sidebar_buttons()
    chosen = _scenarios(data, compact=compact)
    paths = list(chosen)
    stamp = run_stamp(data)
    # the controls of the page in one box of the sidebar: its sticky strip and buttons end with it,
    # so they never cover the language switch that `main.py` draws below
    box = st.sidebar.container(key="explorer-sidebar")
    # on a phone the sidebar covers the page: the results above the sliders. Created first, so a
    # rerun keeps the last lines in view until the runs replace them
    results_box = box.container(border=True, key="explorer-strip") if compact and chosen else None
    salaries = _salaries(data, paths[0]) if chosen else NO_SALARIES
    advanced = mode.advanced()
    side = _sidebar(
        box,
        data,
        salaries,
        load_plan(data, paths[0]) if chosen else None,
        work_dials(data, paths, stamp),
        advanced=advanced,
        compact=compact,
    )
    opts, overrides, nominal = side.opts, side.overrides, side.nominal
    since = _rested(opts, overrides)  # in every run: a move counts with every fold closed
    if not chosen:
        return
    status = Status(st.empty(), results_box)
    _moved(side)
    ran = _results(opts, chosen, overrides, stamp, status)
    if not ran:
        return
    results = [r for _p, r in ran]
    done = _("Up to date: {how}.").format(how=_how(opts, len(paths)))
    status.done(done)
    if results_box is not None:  # in portrait it stays at the top while the sliders scroll
        _fill_strip(results_box, results, changed=bool(overrides), nominal=nominal)
    _summary(results, nominal=nominal, compact=compact)
    _save_form(data, paths, overrides)
    goal_seek(side, chosen, stamp, results)
    if len(results) > 1:  # the fan chart of the only tab shows the same medians
        chart(report.comparison_figure(results, nominal=nominal, compact=compact), key="comparison")
    chart(report.broke_probability_figure(results, compact=compact), key="broke")
    if len(results) > 1:
        _difference(results, extended(chosen), nominal=nominal, compact=compact)
    observed = report.Observed(actual_totals(data), series.consumer_prices(data))
    labels = [r.label for r in results]
    # a phone draws and runs the open tab only: with `on_change` a tab knows whether it is open
    tabs = (
        st.tabs(labels, key=f"{KEY}tab", on_change="rerun")
        if compact
        else st.tabs(labels, key=f"{KEY}tab")
    )
    slots = []
    for i, (tab, (p, r)) in enumerate(zip(tabs, ran, strict=True)):
        if tab.open is False:
            continue
        with tab:
            slot = _tab(
                i,
                r,
                observed,
                nominal=nominal,
                compact=compact,
                folded=compact or not advanced,  # simple mode: the folds of a phone
                plan=not r.twin,
            )
        if slot is not None:
            slots.append((i, p, slot))
    for i, p, slot in slots:  # last: the page shows first
        with slot:
            job = sensitivity.Job(opts, p, overrides)
            fold = Levers(i, chosen[p], nominal, compact)
            _levers(job, side.levers, stamp, status, fold=fold, since=since)
    status.done(done)
