"""One-at-a-time sensitivity: each lever moves down and up by one step, the rest stays."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, wait
from dataclasses import dataclass, field, replace
from datetime import date
from typing import TYPE_CHECKING, Any

from dagobert.loader import deep_merge, nested
from dagobert.problems import InputError
from dagobert.result import BROKE_AGE, TOTAL_AGES

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from concurrent.futures import Executor, Future
    from pathlib import Path

    from dagobert.result import RunResult
    from dagobert.runner import Options


@dataclass(frozen=True)
class Lever:
    """One number of the assumptions. A side that equals `value` is at its bound and not run, one
    that the model refuses (a ceiling stepped to the trigger) counts as the base run too.
    `money.printf(format, value * scale)` shows a value where the words are made. `label` (the
    slider), `format` and `step` (one step as text) are words, no part of its identity: a cached
    run keys by the lever, the words follow the language of the page."""

    label: str = field(compare=False)
    path: tuple[str, ...]
    value: float
    low: float
    high: float
    format: str = field(default="%g", compare=False)
    scale: float = 1.0
    step: str = field(default="", compare=False)

    @property
    def stepped(self) -> str:
        """The slider and its step, a bar of the sensitivity chart: `Equity return ±1.00%`."""
        return f"{self.label} ±{self.step}" if self.step else self.label


@dataclass(frozen=True)
class Outcome:
    p_broke: float  # by `BROKE_AGE`
    totals: tuple[float, ...]  # median net worth at `TOTAL_AGES` in euros of the start
    nominal_totals: tuple[float, ...]
    ages: tuple[int, ...]  # the whole ages that `TOTAL_AGES` take in the run (`RunResult.age_at`)

    @classmethod
    def of(cls, r: RunResult) -> Outcome:
        real, nominal = (
            tuple(r.median_at_age(total, age) for age in TOTAL_AGES)
            for total in (r.euros(r.total), r.total)
        )
        return cls(r.p_broke_by_age(BROKE_AGE), real, nominal, tuple(map(r.age_at, TOTAL_AGES)))

    def distance(self, other: Outcome) -> tuple[float, float]:
        """Ranking key: the change in P(broke) in whole points, which a few hundred paths can
        tell apart, then the change in the last median net worth in euros of the start."""
        return (
            round(abs(self.p_broke - other.p_broke), 2),
            abs(self.totals[-1] - other.totals[-1]),
        )


@dataclass(frozen=True)
class Effect:
    lever: Lever
    low: Outcome
    high: Outcome


@dataclass(frozen=True)
class Sensitivity:
    scenario: str
    start: date  # the first simulated month: the euros of `Outcome.totals`
    base: Outcome
    effects: tuple[Effect, ...]  # largest first


@dataclass(frozen=True)
class Job:
    opts: Options
    scenario: Path
    overrides: dict[str, Any]


def outcome(opts: Options, scenario: Path, overrides: dict[str, Any]) -> tuple[str, date, Outcome]:
    """Top level, so a process pool can pickle it."""
    result = opts.run_one(scenario, overrides)
    if result is None:
        msg = f"{scenario.stem} is abstract"
        raise ValueError(msg)
    return result.scenario, result.months[0], Outcome.of(result)


def _side(future: Future[tuple[str, date, Outcome]], base: Outcome) -> Outcome:
    """The base run for a side that the model refuses: only the base run tells inputs that do
    not load."""
    try:
        return future.result()[-1]
    except InputError:
        return base


def run(
    job: Job,
    levers: Sequence[Lever],
    pool: Executor,
    workers: int,
    tick: Callable[[float], object],
    *,
    every: float,
) -> Sensitivity:
    """2 runs per lever on top of the overrides of `job`, with the seed of its options (common
    random numbers, so the differences carry far less noise than the values), at most `workers`
    in the pool at a time: a run in its queue cannot be cancelled, so a run that the page starts
    next waits for no more than these. `tick` gets the share of finished runs every `every`
    seconds, also while no run ends, and after a run ends, before the next goes in. When it
    raises, no more go in, and those that wait are cancelled. A side that the model refuses
    counts as the base run."""
    opts = replace(job.opts, mortality=False)
    sides = [
        (lever, side) for lever in levers for side in (lever.low, lever.high) if side != lever.value
    ]
    calls = [
        job.overrides,
        *(deep_merge(job.overrides, nested({lever.path: side})) for lever, side in sides),
    ]
    futures: list[Future[tuple[str, date, Outcome]]] = []
    running: set[Future[tuple[str, date, Outcome]]] = set()
    try:
        while len(futures) < len(calls) or running:
            while len(running) < workers and len(futures) < len(calls):
                futures.append(pool.submit(outcome, opts, job.scenario, calls[len(futures)]))
                running.add(futures[-1])
            running = wait(running, every, FIRST_COMPLETED).not_done
            tick((len(futures) - len(running)) / len(calls))
    finally:
        for future in running:
            future.cancel()
    base_run, *side_runs = futures
    by_side = dict(zip(sides, side_runs, strict=True))
    name, start, base = base_run.result()
    effects = [
        Effect(
            lever,
            *(
                _side(by_side[lever, side], base) if (lever, side) in by_side else base
                for side in (lever.low, lever.high)
            ),
        )
        for lever in levers
    ]
    effects.sort(key=lambda e: max(e.low.distance(base), e.high.distance(base)), reverse=True)
    return Sensitivity(name, start, base, tuple(effects))
