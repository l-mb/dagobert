"""Goal seek: the edge search and the spending and work dials of a scenario."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from functools import cache
from typing import TYPE_CHECKING

import pytest
from builders import PHASES_TEXT, plan

from dagobert import goalseek, i18n
from dagobert.loader import load_plan
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import BROKE_AGE
from dagobert.runner import Options
from dagobert.sensitivity import Outcome, outcome

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

FACTOR = goalseek.Dial("factor", ((("x",), 1.0),), 1.0, 0.25, 4.0, 0.005)
MONTHS = goalseek.Dial("months", ((("x",), 1.0),), 0.0, -24.0, 48.0, 1.0, whole=True)


def _rising(values: Sequence[float]) -> list[float]:
    return [v / 10 for v in values]


def _falling(values: Sequence[float]) -> list[float]:
    return [(4 - v) / 10 for v in values]


def _months(values: Sequence[float]) -> list[float]:
    return [(v + 24) / 100 for v in values]


@pytest.mark.parametrize(
    ("dial", "evaluate", "rising"),
    [(FACTOR, _rising, True), (FACTOR, _falling, False), (MONTHS, _months, True)],
)
def test_edge_is_the_last_value_that_meets_the_target(
    dial: goalseek.Dial, evaluate: Callable[[Sequence[float]], list[float]], rising: bool
) -> None:
    """It reports its progress after the ends and after each round."""
    shares: list[float] = []
    found = goalseek.edge(evaluate, dial, 0.05, width=4, progress=shares.append)
    beyond = found.value + (dial.step if rising else -dial.step)
    assert found.rising is rising
    assert found.p_broke <= 0.05 < evaluate([beyond])[0]
    assert found.runs < 25
    assert not dial.whole or found.value == round(found.value)
    assert shares == sorted(shares)
    assert shares[-1] <= 1.0
    assert len(shares) <= goalseek.rounds(dial, 4) + 1


@pytest.mark.parametrize(
    ("evaluate", "target", "limit"),
    [
        (_rising, 0.01, "misses even at 0.25"),
        (_falling, 0.5, "holds from 0.25 to 4"),
        (lambda vs: [0.0] * len(vs), 0.05, "no effect in the range"),
    ],
)
def test_edge_reports_the_ends_of_the_range(
    evaluate: Callable[[Sequence[float]], list[float]], target: float, limit: str
) -> None:
    found = goalseek.edge(evaluate, FACTOR, target, width=4)
    assert (found.runs, found.limit(FACTOR, target)) == (2, limit)


def test_spending_finds_the_edge_of_a_fixed_run(data: Path) -> None:
    opts = Options(data=data, out=data, model="fixed", paths=1, seed=42, mortality=False)
    base = data / "scenarios" / "base.yaml"
    dial = goalseek.spending(load_plan(data, base))
    with ThreadPoolExecutor(2) as pool:
        found = goalseek.seek(goalseek.Job(opts, base, {}, 0.05), dial, pool, 2)
    assert dial.text(dial.value) == "500 € per month"
    assert dial.low < found.value < dial.high
    assert (found.p_broke, found.rising, found.age) == (0.0, True, 51)  # the plan ends at 51
    beyond = {"scale": {"categories": {"wohnen": found.value * 1.05}}}
    assert outcome(opts, base, beyond)[-1].p_broke == 1.0


def test_under_vpw_the_spending_seek_moves_the_floor(data: Path) -> None:
    """VPW spends a share of the wealth: the dial is the floor of the flexible spending, at which
    the rent and the floor run out of money by 90."""
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(
        assumptions.read_text().replace("horizon_age: 51", "horizon_age: 91")
        + "spending: {base: no_pay, categories: [leben], vpw: {}}\n"
    )
    (data / "assets.yaml").write_text("assets: [{id: giro, kind: cash, value: 350000}]\n")
    (data / "cashflows.yaml").write_text(
        "streams:\n"
        "  - {name: Miete, cat: wohnen, amount: -500}\n"
        "  - {name: Leben, cat: leben, amount: -2000}\n"
    )
    opts = Options(data=data, out=data, model="fixed", paths=1, seed=42, mortality=False)
    base = data / "scenarios" / "base.yaml"
    dial = goalseek.spending(load_plan(data, base))
    assert dial.weights == ((goalseek.FLOOR_PATH, 1.0),)
    assert (dial.label, dial.text(dial.value), dial.high) == (goalseek.FLOOR, "0 € per month", 5000)
    with ThreadPoolExecutor(2) as pool:
        found = goalseek.seek(goalseek.Job(opts, base, {}, 0.05), dial, pool, 2)
    assert (found.p_broke, found.rising) == (0.0, True)
    assert dial.low < found.value < dial.high
    beyond = {"spending": {"vpw": {"floor": found.value + 2 * dial.step}}}
    assert outcome(opts, base, beyond)[-1].p_broke == 1.0


@pytest.mark.parametrize(
    ("born", "horizon", "age"),
    [
        ("1977-01-01", 51, 51),  # ends before 90: its last month
        ("1966-01-01", 91, 90),
        ("1933-03-15", 100, 93),  # starts after 90: its first month
        ("1946-07-20", 80, 80),  # a birthday after the first: 79 and 10 months at the end
    ],
)
def test_a_plan_names_the_age_that_its_run_takes_the_chance_to_run_out_at(
    data: Path, born: str, horizon: int, age: int
) -> None:
    """Before the run, as `RunResult.age_at` after it: the label of a seek has no run yet."""
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(
        assumptions.read_text().replace(
            "{born: 1977-01-01, horizon_age: 51}", f"{{born: {born}, horizon_age: {horizon}}}"
        )
    )
    base = data / "scenarios" / "base.yaml"
    run = Options(data=data, out=data, model="fixed", paths=1, seed=42, mortality=False).run_one(
        base
    )
    assert run is not None
    assert goalseek.broke_age(load_plan(data, base).assumptions) == run.age_at(BROKE_AGE) == age


def test_the_survival_overlay_leaves_what_a_seek_reads(data: Path) -> None:
    """The seeks and the sensitivity run without the overlay: it weights the lifetime chance to
    run out, while P(broke by 90) and the medians count every path."""
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(
        assumptions.read_text()
        .replace("horizon_age: 51", "horizon_age: 91")
        .replace("equity: {mean: 0.05}", "equity: {mean: 0.05, stdev: 0.15}")
    )
    (data / "assets.yaml").write_text(
        "assets: [{id: depot, kind: equity, value: 500000, cost_basis: 500000}]\n"
    )
    (data / "cashflows.yaml").write_text("streams: [{name: Miete, cat: wohnen, amount: -1500}]\n")
    alive = Options(
        data=data, out=data, model="montecarlo", paths=100, seed=42, mortality=True
    ).run_one(data / "scenarios" / "base.yaml")
    assert alive is not None
    every = replace(alive, survival=None)
    assert Outcome.of(alive) == Outcome.of(every)
    assert 0 < alive.p_broke_alive() < every.p_broke_alive()


SAVINGS = goalseek.Dial("ETF", ((("scale", "savings", "ETF"), 1.0),), 1.0, 0.0, 2.0, 0.1)


def _seek_savings(data: Path, *, invest_rest: bool) -> tuple[Options, Path, goalseek.Found]:
    """Cash that covers the rent until 78 and a savings plan into equity, which earns more."""
    assumptions = (
        (data / "assumptions.yaml").read_text().replace("horizon_age: 51", "horizon_age: 91")
    )
    (data / "assumptions.yaml").write_text(
        f"{assumptions}invest_rest: {str(invest_rest).lower()}\n"
    )
    (data / "assets.yaml").write_text("assets: [{id: giro, kind: cash, value: 350000}]\n")
    (data / "cashflows.yaml").write_text(
        "streams:\n"
        "  - {name: Miete, cat: wohnen, amount: -1000}\n"
        "  - {name: ETF, kind: savings, amount: -2000}\n"
    )
    opts = Options(data=data, out=data, model="fixed", paths=1, seed=42, mortality=False)
    base = data / "scenarios" / "base.yaml"
    with ThreadPoolExecutor(2) as pool:
        return opts, base, goalseek.seek(goalseek.Job(opts, base, {}, 0.05), SAVINGS, pool, 2)


def test_a_savings_rate_finds_its_edge_while_the_rest_stays_in_cash(data: Path) -> None:
    opts, base, found = _seek_savings(data, invest_rest=False)
    assert found.rising is False
    assert SAVINGS.low < found.value < SAVINGS.high
    assert found.p_broke == 0.0
    below = {"scale": {"savings": {"ETF": found.value - SAVINGS.step}}}
    assert outcome(opts, base, below)[-1].p_broke == 1.0


def test_a_savings_rate_has_no_effect_while_the_rest_is_invested(data: Path) -> None:
    """The cash above the buffer goes into equity anyway."""
    assert _seek_savings(data, invest_rest=True)[2].rising is None


SALARY = Stream(name="Lohn", kind=StreamKind.SALARY, gross=5000, phases=["work"])
PROFIT = Stream(name="Laden", kind=StreamKind.SELF_EMPLOYED, amount=4000, phases=["alt"])


def _scenario(*changes: tuple[str, str, str | None], events: Sequence[object] = ()) -> Scenario:
    """Phase changes as month, phase and id."""
    return Scenario.model_validate(
        {
            "name": "s",
            "phases": [{"from": f"{at}-01", "phase": p, "id": i} for at, p, i in changes],
            "events": events,
        }
    )


FIRE = _scenario(  # the profit of `alt` after ALG1, then a change into `retired` that repeats
    ("2026-01", "work", None),
    ("2027-06", "alt", "a"),
    ("2028-07", "unemployed", "b"),
    ("2029-10", "alt", "b"),
    ("2041-05", "retired", "r"),
    ("2045-05", "retired", "r"),
)
PENSION = _scenario(  # a later change stays, the lump sum of the id stays after the start
    ("2026-01", "work", None),
    ("2040-01", "retired", "r"),
    ("2044-01", "alt", None),
    events=[{"type": "lump_sum", "at": date(2027, 1, 1), "amount": 1000, "id": "r"}],
)
NO_JOB = _scenario(  # the profit of `alt` ends in the month it starts: no pay there
    ("2026-01", "work", None),
    ("2030-01", "alt", "a"),
    ("2040-01", "retired", "r"),
    events=[
        {"type": "add_stream", "at": date(2030, 1, 1), "id": "a", "stream": PROFIT},
        {"type": "end_streams", "at": date(2030, 1, 1), "names": ["Laden"]},
    ],
)
RETIRE = [("2026-01", "work", None), ("2040-01", "retired", "r")]
EVERY = Stream(name="Lohn", kind=StreamKind.SALARY, gross=5000)  # no phases: every phase
ENDING = Stream(  # its own end stays where the change moves
    name="Vertrag", kind=StreamKind.SALARY, gross=5000, phases=["work"], end=date(2042, 1, 1)
)
ENDED_BY_ID = _scenario(  # the end of the pay moves with the change
    *RETIRE, events=[{"type": "end_streams", "at": date(2040, 1, 1), "names": ["Lohn"], "id": "r"}]
)


@pytest.mark.parametrize(
    ("streams", "scenario", "key", "low", "high"),
    [
        ([SALARY, PROFIT], FIRE, "shift.r", "2029-10 (age 52)", "2047-01 (age 70)"),
        ([SALARY], PENSION, "shift.r", "2039-01 (age 62)", "2044-01 (age 67)"),
        ([SALARY, PROFIT], NO_JOB, "shift.a", "2026-01 (age 49)", "2040-01 (age 63)"),
        (
            [EVERY.model_copy(update={"factor": {"retired": 0.0}})],
            _scenario(*RETIRE),
            "shift.r",
            "2026-01 (age 49)",
            "2047-01 (age 70)",
        ),
        ([ENDING], _scenario(*RETIRE), "shift.r", "2026-01 (age 49)", "2042-01 (age 65)"),
        ([ENDING, SALARY], _scenario(*RETIRE), "shift.r", "2026-01 (age 49)", "2047-01 (age 70)"),
        ([EVERY], ENDED_BY_ID, "shift.r", "2026-01 (age 49)", "2047-01 (age 70)"),
    ],
)
def test_work_moves_the_change_out_of_the_last_phase_with_earned_income(
    streams: list[Stream], scenario: Scenario, key: str, low: str, high: str
) -> None:
    """A phase counts while a stream pays there by its dates, which the shift does not move, and
    the month stops where such a date ends the pay."""
    dial = goalseek.work(plan(streams, [], scenario))
    assert (dial.key, dial.text(dial.low), dial.text(dial.high)) == (key, low, high)
    assert dial.overrides(dial.low) == {"shift": {key[6:]: round(dial.low)}}


@pytest.mark.parametrize(
    ("streams", "changes", "why"),
    [
        ([], RETIRE, "No phase .* pays"),
        ([SALARY], [("2026-01", "alt", None), ("2040-01", "work", "r")], "stays in Work"),
        ([EVERY], RETIRE, "stays in Retired.* without phases pays in every phase: Lohn"),
        (
            [ENDING.model_copy(update={"end": date(2035, 1, 1)})],
            RETIRE,
            "does not stop the pay: Vertrag ends in 2035-01",
        ),
        ([SALARY], [("2026-01", "work", None), ("2040-01", "retired", None)], "has no id"),
        (
            [SALARY],
            [("2026-01", "work", None), ("2040-01", "alt", "r"), ("2042-01", "retired", "r")],
            "shares its id r",
        ),
        (  # the repeat of `work` would move into `alt` at the earliest month
            [SALARY],
            [
                ("2026-01", "alt", None),
                ("2034-01", "work", None),
                ("2036-01", "work", "r"),
                ("2040-01", "retired", "r"),
            ],
            "shares its id r",
        ),
        ([SALARY], [("2020-01", "work", None), ("2025-01", "alt", "r")], "before the start"),
    ],
)
def test_work_refuses_a_scenario_without_a_change_to_move(
    streams: list[Stream], changes: list[tuple[str, str, str | None]], why: str
) -> None:
    """The reason is data that the explorer caches, said in the language of each page."""
    with pytest.raises(goalseek.NoChangeError, match=why) as refused:
        goalseek.work(plan(streams, [], _scenario(*changes)))
    with i18n.use("de"):
        assert refused.value.why.said() != str(refused.value)


def test_work_finds_the_earliest_month_that_meets_the_target(data: Path) -> None:
    """A lower target takes a later month, more savings an earlier one. The month found meets
    the target, the one before it misses it. The value and the range count from the file month
    while a slider moved the change. One run per value and depot: the seeks share them."""
    (data / "assumptions.yaml").write_text(
        "person: {born: 1966-01-01, horizon_age: 91}\nstart: 2026-01-01\n"
        f"{PHASES_TEXT}returns:\n  equity: {{mean: 0.05, stdev: 0.15}}\n"
        "  fixed_income: {mean: 0.03}\n  cash: {mean: 0.02}\n  property: {mean: 0.01}\n"
    )
    (data / "cashflows.yaml").write_text(
        "streams:\n  - {name: Lohn, kind: salary, gross: 6000, phases: [work]}\n"
        "  - {name: Miete, cat: wohnen, amount: -2500}\n"
    )
    base = data / "scenarios" / "base.yaml"
    base.write_text(  # a year without work first, a later change that stays
        "name: base\nphases:\n  - {from: 2026-01-01, phase: unemployed}\n"
        "  - {from: 2027-01-01, phase: work}\n"
        "  - {from: 2028-01-01, phase: retired, id: retirement}\n"
        "  - {from: 2030-01-01, phase: alt}\n"
    )
    opts = Options(data=data, out=data, model="montecarlo", paths=100, seed=42, mortality=False)
    dial = goalseek.work(load_plan(data, base))
    assert (dial.text(dial.low), dial.text(dial.high)) == ("2027-01 (age 61)", "2030-01 (age 64)")
    moved = {"shift": {"retirement": -5}}
    assert goalseek.work(load_plan(data, base, moved), moved["shift"]) == replace(dial, value=-5)

    @cache
    def p_broke(months: float, depot: int = 700_000) -> float:
        assets = {"assets": {"depot": {"value": depot, "cost_basis": depot}}}
        return outcome(opts, base, assets | dial.overrides(months))[-1].p_broke

    def stop(target: float, depot: int = 700_000) -> goalseek.Found:
        return goalseek.edge(lambda vs: [p_broke(v, depot) for v in vs], dial, target, 2)

    found, stricter, richer = stop(0.45), stop(0.4), stop(0.45, 800_000)
    assert dial.low <= richer.value < found.value < stricter.value < dial.high
    assert p_broke(found.value) <= 0.45 < p_broke(found.value - 1)
    assert goalseek.stop(found, dial, 0.45).startswith(
        f"Stop working in **{dial.text(found.value)}** for at most 45% chance to run out by 90"
    )


def test_the_spending_dial_moves_scale_spending_on_top_of_its_factor() -> None:
    streams = [Stream(name="Miete", cat="wohnen", amount=-500)]
    dial = goalseek.spending(
        plan(streams, [], scale={"spending": 0.8, "categories": {"wohnen": 2}})
    )
    assert dial.weights == ((("scale", "spending"), 0.8),)
    assert dial.overrides(1.5) == {"scale": {"spending": pytest.approx(1.2)}}
    assert dial.text(1.0) == "800 € per month"
