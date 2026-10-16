"""Goal seek: the value of one lever at which P(broke) meets a target."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

import numpy as np

from dagobert import sensitivity
from dagobert.engine.core import EARNED, pays
from dagobert.engine.simulation import horizon_months
from dagobert.i18n import N_, NP_, _, pgettext, use
from dagobert.loader import deep_merge, nested
from dagobert.model.events import AddStreamEvent, EndStreamsEvent
from dagobert.model.months import add_months, months_between, months_of_age
from dagobert.money import format_percent, printf
from dagobert.result import BROKE_AGE, age_at
from dagobert.sensitivity import outcome

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from concurrent.futures import Executor
    from datetime import date

    from dagobert.model.assumptions import Assumptions
    from dagobert.model.plan import Plan
    from dagobert.model.streams import Stream

SPENDING_RANGE = (0.25, 4.0)  # factors on the spending of the plan
SPENDING_STEP = 0.005  # half a percent of the spending
STOP = N_("Stop working")  # the label of the work dial
SPENDING = N_("All spending")  # the label of the spending dial
FLOOR = N_("Spending floor")  # the label of the spending dial under VPW
FLOOR_PATH = ("spending", "vpw", "floor")
FLOOR_STEP, FLOOR_LEAST = 50.0, 5000.0  # euros per month: the step, the least upper end
PER_MONTH = NP_("sprintf", "%'.,.0f € per month")  # its format: `EUR_COLUMN` per month
WORK_AGE = 70  # the latest month to stop working that the seek tries, before a later change
# what `work` moves, in the words of the Overview and the explorer (`stop_help`)
STOP_MOVES = N_(
    "moves the change out of the last phase in which a salary or a profit pays, from the start "
    "of that phase, or of the plan, to the next change of phase, at most to age {age}. It "
    "moves only what has the id of that change: events with the id move along, later changes, "
    "such as the pension, and the start and end dates of the streams stay. So a phase counts "
    "only while a stream pays in it by those dates, and the month goes no later than a date "
    "that ends the pay. The seek comes in from the latest month and stops at the first month "
    "that misses the target: an earlier month can meet it again."
)


def stop_help() -> str:
    """`STOP_MOVES` in the language of the page."""
    return _(STOP_MOVES).format(age=WORK_AGE)


def broke_age(a: Assumptions) -> int:
    """The whole age at which a run of `a` takes the chance to run out by `BROKE_AGE`, before
    the run: its months as the engine counts them, `RunResult.age_at`."""
    return age_at(np.array([a.person.age(a.start, i) for i in range(horizon_months(a))]), BROKE_AGE)


@dataclass(frozen=True)
class Dial:
    """What the seek moves: every path of `weights` gets the value times its weight. `value`,
    `low`, `high` and `step` are in the units of the value, `printf(format, value * scale)`
    shows it (the format in the context `sprintf` of the catalogue), a shift in months shows the
    month it reaches from `origin`, with the age of one `born` then. Label and format are words,
    no part of its identity: the answers of a seek key by the dial, the words follow the language
    of the page. A dial of `spending` or `work` keeps the English of `SPENDING` or `STOP`, a dial
    of a slider the words of the page that made it."""

    label: str = field(compare=False)
    weights: tuple[tuple[tuple[str, ...], float], ...]
    value: float
    low: float
    high: float
    step: float
    format: str = field(default="%g", compare=False)
    scale: float = 1.0
    whole: bool = False
    origin: date | None = None
    born: date | None = None

    @property
    def key(self) -> str:
        return ",".join(".".join(path) for path, _weight in self.weights)

    def text(self, value: float) -> str:
        if (reached := self.month(value)) is None:
            return printf(pgettext("sprintf", self.format), value * self.scale)
        month, age = reached
        if age is None:
            return f"{month:%Y-%m}"
        return _("{month} (age {age})").format(month=f"{month:%Y-%m}", age=age)

    def month(self, value: float) -> tuple[date, int | None] | None:
        """The month that a shift of `value` months reaches from `origin`, with the age of one
        `born` then; None for a dial without `origin`."""
        if self.origin is None:
            return None
        month = add_months(self.origin, round(value))
        return month, None if self.born is None else months_of_age(self.born, month) // 12

    def overrides(self, value: float) -> dict[str, Any]:
        return nested({p: round(value * w) if self.whole else value * w for p, w in self.weights})


@dataclass(frozen=True)
class Found:
    """`value` is the value nearest the risky end of the range that meets the target. When even
    the safe end misses it, `value` is the safe end and `p_broke` lies above the target. `age` is
    the whole age at which its runs take `p_broke` (`Outcome.ages`), which `seek` sets: a plan
    that ends before `BROKE_AGE` takes its last month."""

    value: float
    p_broke: float
    runs: int
    rising: bool | None  # P(broke) rises with the value; None: equal at both ends
    age: int = BROKE_AGE

    def limit(self, dial: Dial, target: float) -> str:
        if self.rising is None:
            return _("no effect in the range")
        if self.p_broke > target:
            return _("misses even at {value}").format(value=dial.text(self.value))
        if self.value == (dial.high if self.rising else dial.low):
            return _("holds from {low} to {high}").format(
                low=dial.text(dial.low), high=dial.text(dial.high)
            )
        value = dial.text(self.value)
        return (_("up to {value}") if self.rising else _("from {value}")).format(value=value)


def rounds(dial: Dial, width: int) -> int:
    """The rounds of `edge` at most after the ends: each narrows the bracket `width + 1` times,
    until it is one `step` wide."""
    span = (dial.high - dial.low) / dial.step
    return max(1, math.ceil(math.log(span) / math.log(width + 1))) if span > 1 else 1


def edge(
    evaluate: Callable[[Sequence[float]], Sequence[float]],
    dial: Dial,
    target: float,
    width: int,
    progress: Callable[[float], object] = lambda _share: None,
) -> Found:
    """The value nearest the risky end of the dial's range whose P(broke) is at most `target`.
    The end with the lower P(broke) is the safe one, and P(broke) is assumed to cross the target
    once in between. A round evaluates `width` values inside the bracket at once and narrows it
    `width + 1` times, until it is at most one `step` wide. `progress` takes the share of the
    rounds done (`rounds`), the ends first."""
    total, done = rounds(dial, width) + 1, 1
    p_low, p_high = evaluate([dial.low, dial.high])
    progress(done / total)
    runs = 2
    rising = None if p_low == p_high else p_high > p_low
    safe, p_safe, risky = (
        (dial.high, p_high, dial.low) if rising is False else (dial.low, p_low, dial.high)
    )
    if p_safe > target:
        return Found(safe, p_safe, runs, rising)
    if max(p_low, p_high) <= target:
        return Found(risky, max(p_low, p_high), runs, rising)
    while abs(risky - safe) > dial.step:
        points = [float(x) for x in np.linspace(safe, risky, width + 2)[1:-1]]
        if dial.whole:
            points = sorted(
                {float(round(x)) for x in points} - {safe, risky}, key=lambda x: abs(x - safe)
            )
        runs += len(points)
        for value, p in zip(points, evaluate(points), strict=True):
            if p > target:
                risky = value
                break
            safe, p_safe = value, p
        done += 1
        progress(min(done / total, 1.0))
    return Found(safe, p_safe, runs, rising)


def categories(plan: Plan) -> dict[str, float]:
    """The factor per category of the managed expense streams in the plan."""
    return {
        s.cat: plan.assumptions.scale.categories.get(s.cat, 1.0)
        for s in plan.streams
        if s.managed and s.amount
    }


def monthly(plan: Plan) -> float:
    """The managed spending per month with the category factors, before phase factors, in
    start-year euros."""
    scale = categories(plan)
    return -plan.assumptions.scale.spending * sum(
        (s.amount or 0.0) / s.every * scale[s.cat] for s in plan.streams if s.managed and s.amount
    )


def spending(plan: Plan) -> Dial:
    """One factor on `scale.spending`, on top of the factors in `plan`, shown as the
    spending per month. Under VPW the floor of the flexible spending instead, in euros of the
    start per month: VPW spends a share of the wealth, so a factor on the plan hardly moves the
    chance to run out, the floor that it guarantees does."""
    rule = plan.assumptions.spending
    if rule is not None and rule.vpw is not None:
        floor = rule.vpw.floor
        return Dial(
            FLOOR,
            ((FLOOR_PATH, 1.0),),
            value=floor,
            low=0.0,
            high=max(2 * monthly(plan), FLOOR_LEAST, floor),
            step=FLOOR_STEP,
            format=PER_MONTH,
        )
    return Dial(
        SPENDING,
        ((("scale", "spending"), plan.assumptions.scale.spending),),
        value=1.0,
        low=SPENDING_RANGE[0],
        high=SPENDING_RANGE[1],
        step=SPENDING_STEP,
        format=PER_MONTH,
        scale=monthly(plan),
    )


@dataclass(frozen=True)
class _Pay:
    """A salary or a profit with the months it pays in as the engine runs it: from its `start`
    or its `add_stream` to its `end` or the first `end_streams` that ends it, of id `ended_by`."""

    stream: Stream
    begin: date | None
    end: date | None
    ended_by: str | None = None

    def during(self, start: date, until: date | None) -> bool:
        """It pays in a month from `start` to before `until`."""
        first = max(start, self.begin or start)
        return (self.end is None or first < self.end) and (until is None or first < until)


def _pays(plan: Plan) -> list[_Pay]:
    """The salaries and profits of `plan`. The engine takes the events of a month in file order,
    and an `end_streams` ends the streams that it names or tags and that run by then."""
    found = [_Pay(s, s.start, s.end) for s in plan.streams]
    for e in sorted(plan.scenario.events, key=lambda e: e.at or plan.assumptions.start):
        if isinstance(e, AddStreamEvent) and e.at:
            found.append(_Pay(e.stream, max(e.at, e.stream.start or e.at), e.stream.end))
        elif isinstance(e, EndStreamsEvent) and e.at:
            at = e.at
            found = [
                replace(p, end=at, ended_by=e.id)
                if (p.stream.name in e.names or set(p.stream.tags) & set(e.tags))
                and (p.end is None or at < p.end)
                else p
                for p in found
            ]
    return [p for p in found if p.stream.kind in EARNED]


@dataclass(frozen=True)
class NoChange:
    """Why `work` finds no change to move, as data: a cache keeps it, `said` says it in the
    language of the page, `str` in English. `why` is a message of the catalogue with the fields
    `{phase}`, `{month}`, `{id}` and `{ended}`, the streams of `ends` that end by a date of their
    own; `every` names the streams without phases that pay in every phase."""

    why: str
    phase: str = ""
    month: str = ""
    id: str = ""
    ends: tuple[tuple[str, str], ...] = ()  # a stream and the month it ends
    every: tuple[str, ...] = ()

    def said(self) -> str:
        ended = "; ".join(
            _("{stream} ends in {month}").format(stream=stream, month=month)
            for stream, month in self.ends
        )
        text = _(self.why).format(phase=self.phase, month=self.month, id=self.id, ended=ended)
        if not self.every:
            return text
        more = _("A stream without phases pays in every phase: {streams}.")
        return f"{text} {more.format(streams=', '.join(self.every))}"

    def __str__(self) -> str:
        with use("en"):
            return self.said()


class NoChangeError(ValueError):
    """`work` refuses a scenario, `why` in words of the catalogue, the message in English."""

    def __init__(self, why: NoChange) -> None:
        super().__init__(str(why))
        self.why = why


def work(plan: Plan, shift: Mapping[str, float] | None = None) -> Dial:
    """The month of the change out of the last phase that pays a salary or a profit, as the
    `shift` of its id. The shift moves only the items of the id: later changes stay put, the
    events of the id move along, the dates of the streams (`start`, `end`, `add_stream` and
    `end_streams` of other ids) stay. So a phase counts while a stream pays in it by those
    dates. The month runs from the start of that phase, or of the run, to the next change, at
    most to age `WORK_AGE`, and to the date at which the pay ends when every stream that the
    change stops ends by its own date. A change into the phase that holds already changes
    nothing: it may share the id and moves along while it follows the change, before the next
    one. `shift` holds the months by which `plan` moved the ids (the explorer's sliders): the
    value and the range count from the month without them. Raises `NoChangeError` with the
    reason when the scenario has no such change, or when the pay ends by its own date before the
    change."""
    a, phases, events = plan.assumptions, plan.scenario.phases, plan.scenario.events
    starts = [i for i, c in enumerate(phases) if i == 0 or c.phase != phases[i - 1].phase]
    changes = [phases[i] for i in starts]
    rows = _pays(plan)

    def paid(i: int) -> list[_Pay]:
        c, until = changes[i], changes[i + 1].at if i + 1 < len(changes) else None
        return [p for p in rows if pays(p.stream, a, c.phase) and p.during(c.at, until)]

    last = max((i for i in range(len(changes)) if paid(i)), default=None)
    if last is None:
        raise NoChangeError(NoChange(N_("No phase of the scenario pays a salary or a profit.")))
    pay = paid(last)
    if last == len(changes) - 1:
        why = N_(
            "The scenario stays in {phase}, its last phase with a salary or a profit: no change "
            "out of it to move."
        )
        every = tuple(p.stream.name for p in pay if p.stream.phases is None)
        raise NoChangeError(NoChange(why, a.phase_labels[changes[last].phase], every=every))
    into, out = changes[last], changes[last + 1]
    change = (a.phase_labels[out.phase], f"{out.at:%Y-%m}")
    if out.at < a.start:
        why = N_(
            "The change to {phase} from {month} lies before the start: the work ended already."
        )
        raise NoChangeError(NoChange(why, *change))
    # the pay that the change stops: the shift moves an end of the id, not another date
    stopped = [
        p
        for p in pay
        if (out.id is not None and p.ended_by == out.id)
        or (not pays(p.stream, a, out.phase) and (p.end is None or p.end >= out.at))
    ]
    if not stopped:
        why = N_(
            "The change to {phase} from {month} does not stop the pay: {ended}, a date that the "
            "seek would not move."
        )
        raise NoChangeError(
            NoChange(
                why, *change, ends=tuple((p.stream.name, f"{p.end:%Y-%m}") for p in pay if p.end)
            )
        )
    if out.id is None:
        why = N_(
            "The change to {phase} from {month} has no id: give it one in the Phases tab of the "
            "Scenarios page, where a row that you add or change takes its phase as its id."
        )
        raise NoChangeError(NoChange(why, *change))
    # the entries that may share the id: the change and the repeats of its phase that follow it,
    # by list position as `loader.adjust` sorts them. A repeat before it would move into the
    # phase before at the earliest month
    own = range(starts[last + 1], [*starts, len(phases)][last + 2])
    if any(c.id == out.id for i, c in enumerate(phases) if i not in own):
        why = N_(
            "The change to {phase} from {month} shares its id {id} with another phase change, "
            "which would move with it: give it an id of its own."
        )
        raise NoChangeError(NoChange(why, *change, id=out.id))
    born, moved = a.person.born, (shift or {}).get(out.id, 0.0)
    # months from `out`: not before its phase or the run starts, no event of the id before the
    # start, which the engine refuses; not after the age, no phase change of the id past the next
    # change (its events move by as many months and may pass that one), not past the end of the
    # pay when each stopped stream ends by a date that stays
    dated = [e.at for e in events if e.id == out.id and e.at is not None and e.at >= a.start]
    moving = [phases[i].at for i in own if phases[i].id == out.id]
    ends = [end for p in stopped if (end := p.end) is not None and p.ended_by != out.id]
    earliest = max(
        [
            months_between(out.at, max(a.start, into.at)),
            *(months_between(at, a.start) for at in dated),
        ]
    )
    latest = min(
        [
            months_between(out.at, add_months(born, 12 * WORK_AGE + (born.day > 1))),
            *(months_between(at, c.at) for c in changes[last + 2 : last + 3] for at in moving),
            *((months_between(out.at, max(ends)),) if len(ends) == len(stopped) else ()),
        ]
    )
    return Dial(
        STOP,
        ((("shift", out.id), 1.0),),
        moved,
        moved + earliest,
        moved + max(latest, 0),
        1.0,
        whole=True,
        origin=add_months(out.at, -round(moved)),
        born=born,
    )


def stop(found: Found, dial: Dial, target: float) -> str:
    """The answer of the work seek in Markdown: the earliest month that meets the target, or the
    chance when the latest month misses it."""
    p, age = format_percent(found.p_broke), found.age
    if found.rising is None:
        return _(
            "Stopping work in {low} or in {high} leaves the same chance to run out by {age}, {p}: "
            "the seek finds no effect."
        ).format(low=dial.text(dial.low), high=dial.text(dial.high), age=age, p=p)
    if found.rising:
        return _("Working longer raises the chance to run out by {age} here: {limit}.").format(
            age=age, limit=found.limit(dial, target)
        )
    month, at_most = dial.text(found.value), format_percent(target, None)
    if found.p_broke > target:
        return _(
            "Even working until {month} leaves a {p} chance to run out by {age}, above the target "
            "of {target}."
        ).format(month=month, p=p, age=age, target=at_most)
    return _(
        "Stop working in **{month}** for at most {target} chance to run out by {age}: {p} there, "
        "against {plan} in the plan."
    ).format(month=month, target=at_most, age=age, p=p, plan=dial.text(dial.value))


@dataclass(frozen=True)
class Job(sensitivity.Job):
    target: float  # P(broke) by `BROKE_AGE`, at the age that the run takes it at (`Found.age`)


def seek(
    job: Job,
    dial: Dial,
    pool: Executor,
    width: int,
    progress: Callable[[float], object] = lambda _share: None,
) -> Found:
    """The edge of `dial` on top of the overrides of `job`, with the age at which its runs take
    P(broke). One run per value, with the seed of the options, `width` runs at a time in `pool`,
    `progress` after each round. Without the survival overlay: P(broke by 90) does not read it,
    so the runs skip the life table. No dial moves the end of a plan: its runs share the age."""
    opts = replace(job.opts, mortality=False)
    ages: set[int] = set()

    def evaluate(values: Sequence[float]) -> list[float]:
        runs = [
            pool.submit(outcome, opts, job.scenario, deep_merge(job.overrides, dial.overrides(v)))
            for v in values
        ]
        outcomes = [run.result()[-1] for run in runs]
        ages.update(o.ages[-1] for o in outcomes)  # `TOTAL_AGES` ends with `BROKE_AGE`
        return [o.p_broke for o in outcomes]

    found = edge(evaluate, dial, job.target, width, progress)
    (age,) = ages  # no dial moves the end of a plan
    return replace(found, age=age)
