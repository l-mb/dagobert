"""The plan on the Overview: the risk of the main scenario, the spending that a target allows,
and the recorded net worth over the projection of the plan of an earlier day."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date
from functools import partial
from pathlib import Path

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import cache, goalseek, report, revisions
from dagobert.i18n import N_, _
from dagobert.loader import load_plan
from dagobert.model.assets import Asset, AvDepot, PensionPolicy
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Plan
from dagobert.money import format_eur, format_percent
from dagobert.report.summary import Shown
from dagobert.report.tracker import Band, track_figure
from dagobert.result import RunResult
from dagobert.scenariofiles import concrete_scenarios, scenario_file
from dagobert.ui import (
    MAIN,
    chart,
    day_said,
    fold,
    literal,
    month_labels,
    page_link,
    run_stamp,
    runs,
    scenario_note,
    timezone,
)
from dagobert.ui.seek import TARGET, Target, target_field

# the columns of the explorer's summary that the tiles show, by their plain headers
TILES = (report.BROKE_ALIVE, report.BROKE_AT, report.TOTAL_AT, "Shortfall")
SEEK = N_("Find the spending limit")
WORK_SEEK = N_("Find when to stop working")
STOP = "overview-stop"  # the button of the work seek, whose answer the fifth tile shows
# session state: the Overview of a plan that the start page started seeks when to stop, once
SEEK_FIRST = "overview-seek-first"
AHEAD = 6  # months of the projection after the last record
# by the array of the run that they show: its words, the name of the records and their reading
MEASURES = {"total": N_("net worth"), "liquid": N_("liquid")}
RECORDED = {"total": N_("recorded net worth"), "liquid": N_("recorded liquid")}
READING = {
    "total": N_(
        "The recorded net worth of each month with a record over the projection of your main "
        "scenario, as the plan stood at the end of the chosen day: the Explorer's run with its "
        "default options, from the start of the plan on that day to {ahead} months after the "
        "last record."
    ),
    "liquid": N_(
        "The recorded liquid of each month with a record over the projection of your main "
        "scenario, as the plan stood at the end of the chosen day: the Explorer's run with its "
        "default options, from the start of the plan on that day to {ahead} months after the "
        "last record."
    ),
}
READING_MORE = N_(
    "A line joins only the records of consecutive months. A day names the saves that changed the "
    "plan. It opens on the plan as it stood when the record began: the newest day before the "
    "first recorded month ended. In nominal euros, as recorded: deflating the latest months "
    "would take the last value of the consumer price series. The projection counts the tax on "
    "unrealized gains, the records do not, so a record that meets the plan sits a little above "
    "its median."
)
Records = list[tuple[date, dict[str, float]]]  # per month the recorded sums by liquidity
Seek = tuple[goalseek.Found, goalseek.Dial] | None  # an answer: None for a plan without its dial
# the help that the two tiles of the chance to run out share, below the column's own
LIFETIME_HELP = N_(
    "The lifetime figure can be lower than the figure by {age}: it counts a path only with the "
    "chance that you are alive in the month the money runs out, so a path that runs out late "
    "counts little."
)
# under VPW: the help of the tiles of the chance to run out, and of the seeks
VPW_RISK = N_(
    "Under VPW the spending follows the wealth: this is the chance that the essential spending "
    "and the floor of the flexible spending use the wealth up, small with a floor of 0 €."
)
VPW_SEEKS = N_(
    "Under VPW, **{seek}** looks for the floor of the flexible spending instead, as **{floor}** "
    "in the goal seek of the Explorer: the spending that VPW guarantees in each month without "
    "pay, in euros of the start. The floor also makes **{work_seek}** a question: when the "
    "wealth carries the essential spending and that floor."
)


def _allowed(found: goalseek.Found, dial: goalseek.Dial, target: float) -> str:
    """The spending at the edge that the seek found, as a factor and per month, and the chance to
    run out by the age of its runs; under VPW the floor (`_floor`)."""
    if goalseek.FLOOR_PATH in dict(dial.weights):
        return _floor(found, dial, target)
    amount = format_eur(found.value * dial.scale)
    if found.rising is None:
        return _(
            "Spending does not change the chance to run out by {age} between {low} and {high} a "
            "month."
        ).format(
            age=found.age,
            low=format_eur(dial.low * dial.scale),
            high=format_eur(dial.high * dial.scale),
        )
    chance = format_percent(found.p_broke)
    change = _change(found.value)
    if found.p_broke > target:
        return _(
            "Even {amount} a month, {change}, leaves a {chance} chance to run out by {age}, above "
            "the target."
        ).format(amount=amount, change=change, age=found.age, chance=chance)
    return _(
        "Spend at most **{amount} a month**, {change}. The chance to run out by {age} is {chance} "
        "there."
    ).format(amount=amount, change=change, age=found.age, chance=chance)


def _change(factor: float) -> str:
    """A factor on the spending in words: `14% less than now`."""
    if round(abs(factor - 1) * 100) == 0:
        return _("the same as now")
    return (_("{share} less than now") if factor < 1 else _("{share} more than now")).format(
        share=format_percent(abs(factor - 1), 0)
    )


def _floor(found: goalseek.Found, dial: goalseek.Dial, target: float) -> str:
    """The floor of the flexible spending under VPW at the edge that the seek found."""
    chance, amount = format_percent(found.p_broke), format_eur(found.value)
    if found.rising is None:
        return _(
            "The floor does not change the chance to run out by {age} from {low} to {high} per "
            "month."
        ).format(age=found.age, low=format_eur(dial.low), high=format_eur(dial.high))
    if found.p_broke > target:
        return _(
            "Misses the target even at a floor of {amount} per month: a chance to run out by "
            "{age} of {chance}."
        ).format(amount=amount, age=found.age, chance=chance)
    return _(
        "A floor of up to **{amount} per month** of flexible spending, against {plan} in the "
        "plan: a chance to run out by {age} of {chance} there, from {runs} runs."
    ).format(
        amount=amount,
        plan=format_eur(dial.value),
        age=found.age,
        chance=chance,
        runs=found.runs,
    )


# by button key: its label, the dial that it seeks in a plan (`goalseek.NoChangeError` for a plan
# without one) and the answer in words
SEEKS: dict[
    str,
    tuple[
        str,
        Callable[[Plan], goalseek.Dial],
        Callable[[goalseek.Found, goalseek.Dial, float], str],
    ],
] = {
    "overview-seek": (SEEK, goalseek.spending, _allowed),
    STOP: (WORK_SEEK, goalseek.work, goalseek.stop),
}


def _dial(dial_of: Callable[[Plan], goalseek.Dial], plan: Plan) -> goalseek.Dial | None:
    """The dial of `plan` that `dial_of` gives, None for a plan without it."""
    try:
        return dial_of(plan)
    except goalseek.NoChangeError:
        return None


def _sought(
    answers: DeltaGenerator, job: goalseek.Job, label: str, dial: goalseek.Dial | None
) -> Seek:
    """What the seek of `dial` finds, under a progress bar in `answers` that goes when it ends or
    raises; None for a plan without the dial."""
    if dial is None:
        return None
    bar = answers.progress(0.0)
    try:
        text = _("{seek}: round by round").format(seek=_(label))
        return runs.seek(job, dial, partial(runs.tick, bar, text, 0, 1)), dial
    finally:
        bar.empty()


def _stored(job: goalseek.Job, button: str, dial: goalseek.Dial | None) -> str:
    """The name on disk of the answer of the seek of `button` (`cache.key`), by its dial too:
    `SEEKS`, which gives it, is a page, which the engine code leaves out."""
    return cache.key(runs.PLAN_SEEK, job.opts, job.scenario, job.target, button, dial)


def _recall(
    seeks: dict[tuple[object, ...], Seek],
    key: tuple[object, ...],
    job: goalseek.Job,
    button: str,
    dial: goalseek.Dial | None,
) -> None:
    """The answer of the seek of `button` on `dial` from the disk into `seeks` under `key`."""
    match cache.read(job.opts.data, _stored(job, button, dial)):
        case None:
            runs.keep(seeks, key, None)
        case (goalseek.Found() as found, goalseek.Dial() as held):
            runs.keep(seeks, key, (found, held))


def stopped(kept: Seek, target: float) -> tuple[date, int | None] | None:
    """The month to stop working that a work seek found, with the age then. None for a plan
    without the change and when no month meets `target`."""
    if kept is None:
        return None
    found, dial = kept
    return dial.month(found.value) if found.rising is False and found.p_broke <= target else None


def _stop_tile(column: DeltaGenerator, ran: bool, kept: Seek, target: float, by: int) -> None:
    """The fifth tile: the month of the work seek once it `ran`, with the age then, else a dash
    and why; when even the latest month misses the target, `not even at` that age; its help names
    the age of the target, `by`."""
    hint: str | None
    if (month := stopped(kept, target) if ran else None) is not None:
        when, age = month
        value, hint = f"{when:%Y-%m}", None if age is None else _("age {age}").format(age=age)
    elif ran and (last := latest(kept, target)) is not None:
        value, hint = _("not even at {age}").format(age=last), None
    else:
        value, hint = "–", _("see the answer below") if ran else _("not searched yet")
    column.metric(
        _(goalseek.STOP),
        value,
        delta=hint,
        delta_color="off",
        delta_arrow="off",
        help=_(
            "The earliest month to stop working at which the chance to run out by {age} meets "
            "the target, as **{seek}** below finds it. The answer stays until an input or the "
            "target changes."
        ).format(age=by, seek=_(WORK_SEEK)),
    )


def latest(kept: Seek, target: float) -> int | None:
    """The age at the latest month to stop working, when even that month misses `target`."""
    if kept is None or kept[0].rising is not False or kept[0].p_broke <= target:
        return None
    return age if (reached := kept[1].month(kept[1].high)) and (age := reached[1]) else None


def assumed(plan: Plan) -> str | None:
    """The month and age at which `plan` stops working, in a sentence; None for a plan without a
    change out of work."""
    try:
        dial = goalseek.work(plan)
    except goalseek.NoChangeError:
        return None
    month, age = dial.month(dial.value) or (None, None)
    return (
        None
        if month is None
        else _("The plan stops working in {month} (age {age}).").format(
            month=f"{month:%Y-%m}", age=age
        )
    )


def _risks(
    columns: list[DeltaGenerator],
    row: dict[str, str],
    shown: dict[str, Shown],
    age: int,
    vpw: bool,
) -> None:
    """The four tiles of the summary; the two of the chance to run out say how they differ."""
    for column, term in zip(columns, TILES, strict=True):
        tip = [shown[term].tip]
        if term in (report.BROKE_ALIVE, report.BROKE_AT):
            tip.append(_(LIFETIME_HELP).format(age=age))
            if vpw:
                tip.append(_(VPW_RISK))
        column.metric(shown[term].label, row[term], help=" ".join(tip))


def _answer(
    answers: DeltaGenerator, button: str, kept: Seek, target: float, scenario_plan: Plan
) -> None:
    """The answer of a seek in words, with a link to the Explorer when it misses the target; for
    a plan without the dial the reason, in the language of the session."""
    _label, dial_of, say = SEEKS[button]
    if kept is None:
        try:
            dial_of(scenario_plan)
        except goalseek.NoChangeError as err:
            answers.markdown(literal(err.why.said()))
        return
    answers.markdown(say(*kept, target))
    if kept[0].rising is not None and kept[0].p_broke > target:
        with answers:
            page_link("Explorer", _("Explorer: try less spending or more saving"))


def plan(data_dir: Path, scenario: str) -> None:
    """The tiles of the explorer's run of the main `scenario`, named with its note and a link that
    changes it, and, on request, the spending it allows and the month to stop working, which the
    last tile shows: of a plan that the start page started at once (`SEEK_FIRST`). On a miss the
    run waits in the pool under `Simulating the plan …`."""
    path = concrete_scenarios(data_dir)[scenario]
    waiting = st.empty()
    if not runs.files_cached(data_dir, path):
        waiting.caption(_("Simulating the plan …"))
    result = runs.files_run(data_dir, path)
    waiting.empty()
    if result is None:
        return
    st.subheader(_("Main scenario: {scenario}").format(scenario=literal(result.scenario)))
    scenario_note(result.note)
    page_link("Scenarios", _("Change the main scenario"), {MAIN: "open"})
    st.caption(
        _(
            "The chances come from {paths} simulated futures of markets and prices, the amounts "
            "are in euros of {month}."
        ).format(paths=runs.PATHS, month=f"{result.months[0]:%Y-%m}")
    )
    scenario_plan = load_plan(data_dir, path)
    if (said := assumed(scenario_plan)) is not None:
        st.markdown(said)
    row = report.summary_table([result])[0]
    aim = Target.of([result])
    shown = {c.term: c for c in report.summary_columns([result])}
    rule = scenario_plan.assumptions.spending
    vpw = rule is not None and rule.vpw is not None
    *tiles, stop = st.container(key="tiles-plan").columns(len(TILES) + 1)
    _risks(tiles, row, shown, aim.age, vpw)
    seek = st.container(horizontal=True, vertical_alignment="bottom")
    typed = target_field(seek, aim, "overview-seek-target")  # beside the button on a phone
    job = goalseek.Job(runs.options(data_dir), path, {}, (TARGET if typed is None else typed) / 100)
    # the answer of each seek per run options, scenario, target, state of the inputs and button,
    # without words: the page says it in the language of its session
    seeks: dict[tuple[object, ...], Seek] = runs.answers(runs.PLAN_SEEK)
    stamp = run_stamp(data_dir)
    # a target that does not read keeps no answer
    key = (job.opts, path, None if typed is None else job.target, stamp)
    answers = st.container()
    first = st.session_state.pop(SEEK_FIRST, False)  # a new plan: its stop tile not left empty
    for button, (label, dial_of, _say) in SEEKS.items():
        asked = seek.button(_(label), key=button, disabled=typed is None) or (
            first and button == STOP
        )
        if typed is None or (not asked and (*key, button) in seeks):
            continue
        dial = _dial(dial_of, scenario_plan)
        if asked:
            sought = partial(_sought, answers, job, label, dial)
            named = partial(_stored, job, button, dial)
            runs.keep(seeks, (*key, button), cache.kept(data_dir, named, sought))
        else:
            _recall(seeks, (*key, button), job, button, dial)
    for button in SEEKS:
        if (*key, button) in seeks:
            _answer(
                answers,
                button,
                seeks[(*key, button)],
                job.target,
                scenario_plan,
            )
    _stop_tile(stop, (*key, STOP) in seeks, seeks.get((*key, STOP)), job.target, aim.age)
    fold(
        _(
            "The outlook of your main scenario, {scenario}, as the Explorer opens it: a Monte "
            "Carlo run of {paths} paths on your inputs, "
            "without the sliders, in {unit}. The help icon of each tile explains its figure. "
            "**{seek}** looks for one factor on all spending at which the chance to run out of "
            "money by {age} ({term}) meets the target, as **All spending** in the goal seek of "
            "the Explorer: the spending per month before the factors of the phases, without the "
            "health insurance premium, in euros of the start. **{work_seek}** looks for the "
            "earliest month to stop working that meets the target, as **{stop}** in the goal "
            "seek of the Explorer: it {stop_help} Random noise blurs the last step. Choose the "
            "main scenario at the top of the Scenarios page."
        ).format(
            scenario=literal(result.scenario),
            paths=runs.PATHS,
            unit=result.unit(),
            seek=_(SEEK),
            age=aim.age,
            term=report.BROKE_AT,
            work_seek=_(WORK_SEEK),
            stop=_(goalseek.STOP),
            stop_help=goalseek.stop_help(),
        )
        + (
            " " + _(VPW_SEEKS).format(seek=_(SEEK), floor=_(goalseek.FLOOR), work_seek=_(WORK_SEEK))
            if vpw
            else ""
        ),
        _("How to read the outlook"),
    )


def default_day(days: list[revisions.Day], first: date) -> revisions.Day:
    """The plan as it stood when the record began: the newest day before the first recorded
    month ended, else the oldest."""
    end = add_months(first, 1)
    return next((d for d in days if d.day < end), days[-1])


def plan_days(data_dir: Path, scenario: str) -> dict[revisions.Day, str]:
    """The days with a revision of the plan whose inputs hold `scenario` at their end, newest
    first, each with the file of the scenario then: before a rename its old one
    (`revisions.named`)."""
    log = revisions.entries(data_dir)
    name = revisions.named(log, scenario_file(scenario))
    return {
        day: then
        for day in revisions.days(log, selected=revisions.is_plan, tz=timezone())
        if (then := name(day.last))
    }


def on_track(data_dir: Path, scenario: str, records: Records, assets: Iterable[Asset]) -> None:
    """The recorded net worth per month over the projection of the plan of an earlier day, with
    the `assets` that the page loaded."""
    st.subheader(_("Records against the plan"))
    files = plan_days(data_dir, scenario)
    days = list(files)
    if len(records) < 2 or not days:
        st.info(
            _(
                "The comparison starts with a second month of records, see above, and needs a "
                "saved version of the plan."
            )
        )
        return
    first, last = records[0][0], records[-1][0]
    choice = st.container(horizontal=True, vertical_alignment="bottom")
    # a date, not a `Day`: a save elsewhere that changes the sources of a day keeps the choice
    by_date = {d.day: d for d in days}
    day = by_date[
        choice.selectbox(
            _("Compare with plan saved on"),
            list(by_date),
            index=days.index(default_day(days, first)),
            format_func=lambda d: day_said(by_date[d]),
            key="overview-track-day",
        )
    ]
    measure = str(
        choice.segmented_control(
            _("Measure"),
            list(MEASURES),
            format_func=lambda option: _(MEASURES[option]),
            default="total",
            required=True,
            key="overview-track-what",
        )
    )
    with st.spinner(_("Running the plan of {day}").format(day=day.day)):
        result = runs.baseline(data_dir, files[day], day.last, "explorer")
    if not isinstance(result, RunResult):
        st.warning(runs.refusal(result, _("The plan saved on {day}").format(day=day.day)))
        return
    total = measure == "total"
    values = result.total if total else result.liquid
    band = Band.of(result, values, add_months(last, AHEAD))
    shown = [
        (month, sum(sums.values()) if total else sums.get("liquid", 0.0))
        for month, sums in records
        if band.months and band.months[0] <= month <= band.months[-1]
    ]
    if shown:
        month, record = shown[-1]
        below = float((values[:, months_between(result.months[0], month)] < record).mean())
        st.markdown(
            _("The last record, {month}, lies above **{share}** of the paths of the plan.").format(
                month=f"{month:%Y-%m}", share=format_percent(below, 0)
            )
        )
    chart(
        track_figure(band, shown, _(RECORDED[measure]), labels=month_labels()),
        key="overview-track",
    )
    if carried(assets):
        st.caption(
            _(
                "The plan carries your pension policies forward from the date of their value with "
                "returns and payments, the records keep the values that you typed: **Take "
                "estimates** on the Snapshot page updates them."
            )
        )
    fold(
        f"{_(READING[measure]).format(ahead=AHEAD)} {_(READING_MORE)}",
        _("How to read the comparison"),
    )


def carried(assets: Iterable[Asset]) -> bool:
    """Whether the plan carries a pension policy or depot from the date of its value
    (`carry`), while its records keep that value."""
    return any(isinstance(a, PensionPolicy | AvDepot) and a.asof for a in assets)
