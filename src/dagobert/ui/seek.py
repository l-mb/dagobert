"""The goal seek of the Explorer: per chosen scenario the value of one lever at which the chance to
run out of money meets a target, a sentence each, and `Apply to sliders`. Its caches hold no
words: a switch of the language runs nothing again."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import goalseek, report
from dagobert.i18n import N_, _
from dagobert.loader import load_plan
from dagobert.money import format_number, format_percent
from dagobert.problems import InputError
from dagobert.result import BROKE_AGE, RunResult
from dagobert.ui import Stamp, fields, literal, note
from dagobert.ui.runs import keep, seek, tick
from dagobert.ui.sliders import KEY, Knob

if TYPE_CHECKING:
    from dagobert.ui.explorer import Sidebar

TARGET = 5.0  # the default target of the goal seek: P(broke by `BROKE_AGE`) in %
TARGETS = fields.Field(("target",), fields.Kind.NUMBER, low=0.5, high=50.0)  # how it reads
# the target of the goal seek and of the seeks of the Overview, in the same words (`Target`)
TARGET_LABEL = N_("Target, chance to run out by {age} (%)")
TARGET_HELP = N_("The highest chance to run out of money by {age} that you accept.")
SPENDING_ALL = "spending"  # the goal seek option of `goalseek.spending`
WORK = "work"  # the goal seek option of `goalseek.work`
# the options of no single slider, their words the labels of their dials
LEVERS = {SPENDING_ALL: goalseek.SPENDING, WORK: goalseek.STOP}
SEEK_HELP = N_(  # `{stop} {moves}`: the lever `Stop working` and what it moves
    "Moves one lever until the chance to run out of money by {age} meets the target, in each "
    "chosen scenario with the sliders as they stand, with the chosen model and paths. It runs "
    "both ends of the slider and narrows the step where the target is crossed, so it assumes "
    "that the chance moves one way along the lever: up to a value, or from a value on. All "
    "spending is one factor on all spending, per month before the factors of the phases, in "
    "euros of the start, without the health insurance premium; under VPW it moves the floor of "
    "the flexible spending instead. {stop} {moves} The change needs "
    "an id. Its month slider then reaches the range of every chosen scenario. Random noise "
    "blurs the last step."
)


@dataclass(frozen=True)
class Target:
    """The words of the target for some runs: the age at which every run takes the chance to run
    out (`report.taken_at`, as the summary), else `BROKE_AGE` and the runs at another age in its
    help."""

    age: int
    label: str
    help: str

    @classmethod
    def of(cls, results: Sequence[RunResult]) -> Target:
        age, apart = report.taken_at(results, BROKE_AGE)
        said = _(TARGET_HELP).format(age=age)
        return cls(age, _(TARGET_LABEL).format(age=age), f"{said} {apart}".rstrip())


def target_field(row: DeltaGenerator, aim: Target, key: str) -> float | None:
    """The target in percent in `row`, of the goal seek and the seeks of the Overview: a text
    field, read with a decimal comma or a point in either language (`5,5`): a number input
    shows a decimal point (`5.00`), and the browser reads a mark by its own language. Its
    container `decimal-…` gives a phone the decimal keypad (`ui.keyboard`). None, with what to
    type below the row, for a text that does not read or lies outside `TARGETS`."""
    st.session_state.setdefault(key, format_number(TARGET))
    text = row.container(key=f"decimal-{key}", width="content").text_input(
        aim.label, key=key, help=aim.help, width=220
    )
    try:
        if (typed := fields.parse(TARGETS, text)) is not None:
            return float(typed)
        problem = _("type a number, such as 2.5")
    except ValueError as e:
        problem = str(e)
    st.warning(_("Target: {problem}").format(problem=problem))
    return None


@st.cache_resource(show_spinner=False)
def _seeks() -> dict[tuple[object, ...], goalseek.Found]:
    return {}


def goal_seek(
    side: Sidebar, chosen: Mapping[Path, str], stamp: Stamp, results: Sequence[RunResult]
) -> None:
    """The edge of one lever per scenario at a target P(broke), on request: a sentence per
    scenario, and a button that sets the sliders there. The target names the age of the runs of
    the chosen scenarios among `results`."""
    with st.expander(_("Goal seek: the limit of one lever"), expanded=False, key=f"{KEY}seek-open"):
        dials = {d.key: d for d in side.dials}
        lever_key = f"{KEY}seek-lever"
        if st.session_state.get(lever_key) not in {*LEVERS, *dials}:
            st.session_state[lever_key] = SPENDING_ALL
        aim = Target.of([r for r in results if not r.twin])
        row = st.container(horizontal=True, vertical_alignment="bottom")
        lever = row.selectbox(
            _("Lever"),
            [*LEVERS, *dials],
            format_func=lambda k: dials[k].label if k in dials else _(LEVERS[k]),
            key=lever_key,
            width=360,
        )
        typed = target_field(row, aim, f"{KEY}seek-target")  # beside the lever on a desktop
        jobs = [
            (
                goalseek.Job(
                    side.opts, p, side.overrides, (TARGET if typed is None else typed) / 100
                ),
                dials.get(lever)
                or _named(_dial(lever, side.opts.data, p, json.dumps(side.overrides), stamp)),
            )
            for p in chosen
        ]
        found = _seeks()
        keys = [
            (job.opts, job.scenario, json.dumps(job.overrides), job.target, dial, stamp)
            for job, dial in jobs
        ]
        # no `KEY`: `main.py` cannot carry a button
        if row.button(_("Find the limit"), key="seek", type="primary", disabled=typed is None):
            _find(found, dict(zip(keys, jobs, strict=True)), chosen)
        for i, (key, (job, dial)) in enumerate(zip(keys, jobs, strict=True)):
            name = chosen[job.scenario]
            if isinstance(dial, goalseek.NoChange):  # a scenario without the lever says why at once
                st.markdown(f"**{literal(name)}** · {literal(dial.said())}")
                continue
            if typed is None or key not in found:
                continue
            answer = st.container(horizontal=True, vertical_alignment="center")
            answer.markdown(seek_answer(name, dial, found[key], job.target, work=lever == WORK))
            if positions := slider_positions(dial, found[key], job.target, side.sliders):
                answer.button(
                    _("Apply to sliders"),
                    key=f"seek-apply-{i}",
                    on_click=_apply,
                    args=(positions,),
                    help=_("Sets the sliders to this value, for every chosen scenario."),
                    width="content",
                )
        stop, moves = _(goalseek.STOP), goalseek.stop_help()
        note(_(SEEK_HELP).format(stop=stop, moves=moves, age=aim.age))


def _named(dial: goalseek.Dial | goalseek.NoChange) -> goalseek.Dial | goalseek.NoChange:
    """A cached dial of `spending` or `work` with its label in the language of the page."""
    if isinstance(dial, goalseek.NoChange):
        return dial
    return replace(dial, label=_(dial.label))


def _find(
    found: dict[tuple[object, ...], goalseek.Found],
    jobs: Mapping[tuple[object, ...], tuple[goalseek.Job, goalseek.Dial | goalseek.NoChange]],
    chosen: Mapping[Path, str],
) -> None:
    """The seek of each scenario with a dial, by its key in `found`, under one progress bar, which
    goes when they end or one raises."""
    dialed = [
        (key, job, dial) for key, (job, dial) in jobs.items() if isinstance(dial, goalseek.Dial)
    ]
    bar = st.progress(0.0)
    try:
        for n, (key, job, dial) in enumerate(dialed):
            text = _("Seeking in {scenario}: round by round").format(
                scenario=literal(chosen[job.scenario])
            )
            keep(found, key, seek(job, dial, partial(tick, bar, text, n, len(dialed))))
    finally:
        bar.empty()


@st.cache_data(max_entries=64, show_spinner=False)
def _dial(
    lever: str, data: Path, scenario: Path, overrides: str, stamp: Stamp
) -> goalseek.Dial | goalseek.NoChange:
    """The dial of a lever of no single slider in `scenario` with the sliders (`overrides` as
    JSON), or why the scenario has none. Cached until an input changes: the sidebar asks for the
    work dials on every rerun. No words: the label is the English of `LEVERS` (`_named`), the
    reason a message of the catalogue with its fields."""
    del stamp  # cache key only: an input changed
    sliders = json.loads(overrides)
    plan = load_plan(data, scenario, sliders)
    if lever == SPENDING_ALL:
        return goalseek.spending(plan)
    try:
        return goalseek.work(plan, sliders.get("shift"))
    except goalseek.NoChangeError as err:
        return err.why


def work_dials(data: Path, scenarios: Sequence[Path], stamp: Stamp) -> list[goalseek.Dial]:
    """The work dials of the chosen scenarios without the sliders, whose month sliders reach
    their ranges. A scenario that does not load has none: its run raises after the sidebar."""
    dials = []
    for scenario in scenarios:
        with suppress(InputError):
            if isinstance(dial := _dial(WORK, data, scenario, "{}", stamp), goalseek.Dial):
                dials.append(dial)
    return dials


def seek_answer(
    scenario: str, dial: goalseek.Dial, found: goalseek.Found, target: float, *, work: bool = False
) -> str:
    """One sentence: the limit that the seek found, where the lever stands, and the chance to run
    out there by the age of its runs; for `Stop working` the sentence of `goalseek.stop`."""
    if work:
        return f"**{literal(scenario)}** · {goalseek.stop(found, dial, target)}"
    limit = _("{lever} — {limit}, now {value}. A {p} chance to run out by {age} there.").format(
        lever=dial.label,
        limit=found.limit(dial, target),
        value=dial.text(dial.value),
        p=format_percent(found.p_broke),
        age=found.age,
    )
    return f"**{literal(scenario)}** · {limit}"


def slider_positions(
    dial: goalseek.Dial,
    found: goalseek.Found,
    target: float,
    sliders: Mapping[tuple[str, ...], Knob],
) -> dict[str, float]:
    """The slider positions by widget key that set the lever to the value found, when it meets
    the target: one slider, or the factor on all spending. None when a path has no slider
    that acts or the value lies beyond its range, which a slider refuses."""
    if found.rising is None or found.p_broke > target:
        return {}
    positions = {}
    for path, weight in dial.weights:
        if (knob := sliders.get(path)) is None:
            return {}
        low, high = knob.unit.bounds(knob.value)
        if not low <= (position := knob.position(found.value * weight)) <= high:
            return {}
        positions[knob.key] = position
    return positions


def _apply(positions: dict[str, float]) -> None:
    for key, position in positions.items():
        st.session_state[key] = position
