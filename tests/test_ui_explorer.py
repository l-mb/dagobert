"""The Explorer: its sliders, the runs they start, the sensitivity, the goal seek and
its sliders, the comparison of scenarios and of the run of the files."""

from __future__ import annotations

import json
import math
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from apps import EXPLORER, LEVERS, OVERVIEW, render
from builders import fixed_run, plan
from german import ACTIVATE, leaks, words
from streamlit.runtime.state import SafeSessionState, SessionState, session_state_proxy
from streamlit.testing.v1 import AppTest

from dagobert import goalseek, i18n, report, scenariofiles, sensitivity, series
from dagobert.loader import load_assumptions, load_plan, load_scenario, load_streams
from dagobert.model.assets import Asset, CryptoAsset, GoldAsset
from dagobert.model.assumptions import (
    Allocation,
    Assumptions,
    CareOptions,
    GlidePoint,
    Index,
    ReturnClass,
    Scale,
    Spending,
)
from dagobert.model.base import description
from dagobert.model.events import AddStreamEvent
from dagobert.model.months import add_months
from dagobert.model.plan import Feature, Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.report.summary import Shown
from dagobert.result import RunResult
from dagobert.runner import WORKERS_ENV, Options
from dagobert.ui import explorer, fixed, knobs, mode, runs, seek, sliders, tables
from dagobert.ui.explorer import Drawn


def test_slider_bounds_widen_to_include_the_configured_value() -> None:
    assert sliders.RATE.bounds(0.04) == (-2.0, 15.0)
    assert sliders.RATE.bounds(-0.05) == (-5.0, 15.0)
    assert sliders.SHARE.bounds(1.5) == (0.0, 150.0)
    assert sliders.EUR.bounds(12000) == (0.0, 12000.0)
    # a sensitivity step stays inside the range of the slider, widened to the file value
    assert [sliders.SPREAD.side(0.45, sign, 0.5) for sign in (-1, 1)] == [0.43, 0.47]
    assert [sliders.SPREAD.side(0.5, sign, 0.5) for sign in (-1, 1)] == [0.48, 0.5]


def test_index_help_names_the_streams_that_events_add(data: Path) -> None:
    a = load_assumptions(data)
    a = a.model_copy(update={"indices": {"wage": Index(mean=0.03)}})
    added = AddStreamEvent(
        at=date(2030, 1, 1),
        type="add_stream",
        stream=Stream(
            name="Consulting", cat="gehalt", kind=StreamKind.SALARY, gross=900, index="wage"
        ),
    )
    found = knobs.knobs(a, [], scenario=Scenario(name="s", events=[added]))
    assert next(k for k in found if k.path == ("indices", "wage", "mean")).help.endswith(
        "Followed by: Consulting."
    )


def test_an_index_sits_by_who_follows_it(data: Path) -> None:
    """Income only: `Income`, after the salary sliders. A cost, both or none: `Markets`, after
    the inflation. The group of the growth is gone."""
    a = load_assumptions(data).model_copy(
        update={"indices": {n: Index(mean=0.03) for n in ("wage", "rent", "mixed", "idle")}}
    )
    streams = [
        Stream(name="Lohn", kind=StreamKind.SALARY, gross=900, index="wage"),
        Stream(name="Miete", amount=-500, index="rent"),
        Stream(name="Gehalt", kind=StreamKind.SALARY, gross=900, index="mixed"),
        Stream(name="Essen", amount=-100, index="mixed"),
    ]
    found = {k.path: k.group for k in knobs.knobs(a, streams)}
    assert [found["indices", n, "mean"] for n in ("wage", "rent", "mixed", "idle")] == [
        sliders.SALARY,
        sliders.MARKETS,
        sliders.MARKETS,
        sliders.MARKETS,
    ]
    assert found["pension_growth",] == sliders.SALARY
    assert "growth" not in sliders.GROUPS
    order = [k.path for k in knobs.knobs(a, streams) if k.group == sliders.MARKETS]
    assert order[:2] == [("inflation", "mean"), ("indices", "rent", "mean")]


@pytest.mark.parametrize("phone", [False, True])
def test_a_phone_points_to_the_sliders_in_the_menu(data: Path, *, phone: bool) -> None:
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60)
    if phone:
        at.query_params["mobile"] = "1"
    at.run()
    assert not at.exception
    assert any(b.key == "open-sliders" for b in at.button) == phone


def test_a_month_slider_shows_the_age_at_its_position() -> None:
    knob = sliders.Knob(
        sliders.EVENTS,
        "x",
        ("shift", "x"),
        0.0,
        sliders.SHIFT,
        "",
        origin=date(2050, 3, 1),
        born=date(1980, 3, 1),
    )
    assert knob.reached(0) == "2050-03 (age 70)"
    assert knob.reached(-1) == "2050-02 (age 69)"
    with i18n.use("de"):
        assert knob.reached(12) == "2051-03 (Alter 71)"
    assert replace(knob, born=None).reached(0) == "2050-03"


def test_knobs_cover_the_optional_sections(data: Path) -> None:
    a = load_assumptions(data)
    full = a.model_copy(
        update={
            "spending": Spending(cut=0.2, trigger=0.9, categories=["reisen"]),
            "allocation": Allocation(fixed_income=[GlidePoint(age=50, share=0.2)]),
            "indices": {"bonus": Index(mean=0.8, cumulative=False), "wage": Index(mean=0.03)},
            "care": CareOptions.model_validate(
                {"hazard": [{"age": 80, "factor": 0.1}], "cost": 2000, "duration": {"mean": 24}}
            ),
        }
    )
    streams = [
        Stream(
            name="Gehalt",
            cat="gehalt",
            kind=StreamKind.SALARY,
            gross=5000,
            phases=["work"],
            index="bonus",
        ),
        Stream(name="Miete", cat="wohnen", amount=-500),
        Stream(name="Grundsteuer", cat="wohnen", amount=-120, every=12),
        Stream(name="Reisen", cat="reisen", amount=-400),
        Stream(name="PKV", cat="versicherung", amount=-700, health="kv"),
    ]
    salaries = knobs.Salaries("plan", {"alt": 3612.4})
    found = {k.path: k for k in knobs.knobs(full, streams, salaries)}
    assert len(found) == len(knobs.knobs(full, streams, salaries))
    assert [p[2] for p in found if p[:2] == ("scale", "categories")] == ["wohnen", "reisen"]
    salary = found["scale", "salary", "alt"]
    assert salary.unit.bounds(salary.value) == (0.0, 7500.0)
    assert salary.unit.text(salary.value) == "3.612 €"
    assert salary.lever(1.0).high == pytest.approx(4112.4 / 3612.4)
    dial = salary.dial(1.0)
    assert (dial.low, dial.text(1.0)) == (0.0, "3.612 €")
    assert (dial.high, dial.step) == pytest.approx((7500 / 3612.4, 500 / 3612.4))
    # beside it the growth of the phase, a rate per year from -5%: a lever and a dial; none for a
    # phase without pay in the run
    growth = found["scale", "growth", "alt"]
    paths = list(found)
    assert paths[paths.index(salary.path) + 1] == growth.path
    assert ("scale", "growth", "work") not in found
    assert (growth.group, growth.unit, growth.value) == (sliders.SALARY, sliders.RAISES, 0.0)
    assert (growth.lever(0.0).low, growth.lever(0.0).high) == (-0.005, 0.005)
    assert (growth.dial(0.0).low, growth.dial(0.0).text(0.02)) == (-0.05, "2.0%")
    assert "about 510 € per month" in found["scale", "categories", "wohnen"].help
    overall = found["scale", "spending"]
    assert (overall.group, overall.unit, overall.value) == (
        sliders.ALL_SPENDING,
        sliders.FACTOR,
        1.0,
    )
    assert "about 910 € per month" in overall.help
    assert knobs.knobs(full, [])[0].group != sliders.ALL_SPENDING  # no spending, no slider
    assert found["scale", "categories", "reisen"].lever(1.0).low == 0.9
    assert found["spending", "trigger"].unit is sliders.LEVEL
    assert found["indices", "bonus", "mean"].unit is sliders.SHARE
    # an index slider names the streams that follow it by their `index`
    assert found["indices", "bonus", "mean"].help.endswith("Followed by: Gehalt.")
    assert found["indices", "wage", "mean"].help.endswith("No stream of the plan follows it.")
    assert found["allocation", "rebalance_every"].unit.whole
    assert "reisen" in found["spending", "cut"].help
    # the help of a slider starts with that of its field on the Assumptions page, which edits lists
    cut = description(Assumptions, ("spending", "cut"))
    assert found["spending", "cut"].help.startswith(cut)
    assert "edit it on the Assumptions page" in found["allocation", "rebalance_every"].help
    care = (found["care", "cost"], found["care", "duration", "mean"])
    assert not any("fixed" in k.models for k in care)  # `fixed` draws no care episodes
    groups = [k.group for k in knobs.knobs(full, streams)]
    assert groups == sorted(groups, key=groups.index)
    bare = a.model_copy(update={"spending": None, "care": None, "allocation": None})
    assert not {"spending", "care", "allocation"} & {k.path[0] for k in knobs.knobs(bare, [])}


@pytest.mark.parametrize(("base", "increase"), [("start", 0.0), ("no_pay", 0.0), ("no_pay", 0.1)])
def test_the_increase_sliders_keep_apart_from_the_trigger(
    data: Path, base: str, increase: float
) -> None:
    """The increase only with the reference of the first month without pay, which the model
    requires; while it is on, in their own ranges no position of the trigger reaches one of the
    ceiling, which it refuses; while it is off, the trigger takes its whole range."""
    band = {"increase": increase, "ceiling": 1.5} if base == "no_pay" else {}
    rule = Spending.model_validate({"base": base, "trigger": 0.5} | band)
    a = load_assumptions(data).model_copy(update={"spending": rule})
    found = {k.path: k for k in knobs.knobs(a, [])}
    shown = ("spending", "increase") in found and ("spending", "ceiling") in found
    assert shown == (base == "no_pay")
    trigger = found["spending", "trigger"]
    if increase:
        ceiling = found["spending", "ceiling"]
        assert trigger.unit.bounds(trigger.value)[1] < ceiling.unit.bounds(ceiling.value)[0]
    else:
        assert trigger.unit is sliders.LEVEL


def test_vpw_takes_the_sliders_of_the_band(data: Path) -> None:
    """VPW replaces the cut and the increase: its growth, its age and its floor, each a lever and
    a dial; a flexible category says what its factor does under VPW, another does not."""
    rule = Spending.model_validate(
        {"base": "no_pay", "categories": ["reisen"], "vpw": {"growth": 0.037, "floor": 600}}
    )
    a = load_assumptions(data).model_copy(update={"spending": rule})
    streams = [Stream(name="Reisen", cat="reisen", amount=-400), Stream(name="Miete", amount=-500)]
    found = {k.path: k for k in knobs.knobs(a, streams) if k.group == sliders.SPENDING}
    vpw = ("spending", "vpw")
    assert list(found) == [
        ("cash_buffer_months",),
        (*vpw, "growth"),
        (*vpw, "horizon_age"),
        (*vpw, "floor"),
    ]
    growth, age, floor = (found[(*vpw, key)] for key in ("growth", "horizon_age", "floor"))
    assert (growth.unit.text(growth.value), age.unit.text(age.value)) == ("3.7%", "100")
    assert (floor.label, floor.dial(600).weights) == (
        "Spending floor",
        ((goalseek.FLOOR_PATH, 1.0),),
    )
    assert growth.help.startswith(description(Assumptions, (*vpw, "growth")))
    factors = {
        k.path[-1]: k.help for k in knobs.knobs(a, streams) if k.group == sliders.BY_CATEGORY
    }
    vpw_share = i18n._(knobs.VPW_SHARE)
    assert vpw_share in factors["reisen"]
    assert vpw_share not in factors[""]


@pytest.mark.parametrize(
    ("factor", "shown", "unit"), [(1.25, "5.000 €", "4.000 €"), (0, "0 €", "5.000 €")]
)
def test_a_salary_slider_shows_the_gross_that_its_scenario_pays(
    data: Path, factor: float, shown: str, unit: str
) -> None:
    """The run of a scenario with a salary factor paid the gross with it: the slider starts there,
    one step of the factor is the gross at the factor 1 (a factor 0 paid nothing: the run's gross),
    and its path is text for the scenario file that it saves."""
    a = load_assumptions(data).model_copy(update={"scale": Scale(salary={"work": factor})})
    knob = next(
        k
        for k in knobs.knobs(a, [], knobs.Salaries("plan", {"work": 5000.0}))
        if k.path[:2] == ("scale", "salary")
    )
    assert (knob.unit.text(knob.value), knob.unit.text(1.0)) == (shown, unit)
    assert [type(part) for part in knob.path] == [str, str, str]


def test_a_savings_plan_gets_a_slider_in_euros_per_month(data: Path) -> None:
    """Also the plan of an `add_stream`. The scenario saves 1.5 times the 200 € a month of the
    file. Its help names the age at which the plan takes the chance to run out: it ends at 51.
    `Invest the rest` and `Realize gains`, in a group of its own, are toggles: no lever, no
    dial."""
    a = load_assumptions(data).model_copy(update={"scale": Scale(savings={"ETF": 1.5})})
    gold = Stream(name="Gold plan", kind=StreamKind.SAVINGS, amount=-50, into="bars")
    added = AddStreamEvent(at=date(2027, 1, 1), type="add_stream", stream=gold)
    streams = [Stream(name="ETF", kind=StreamKind.SAVINGS, amount=-600, every=3)]
    found = {
        k.path: k for k in knobs.knobs(a, streams, scenario=Scenario(name="s", events=[added]))
    }
    etf = found["scale", "savings", "ETF"]
    assert etf.group == sliders.SAVINGS
    assert (etf.unit.text(etf.value), etf.unit.text(1.0)) == ("300 €", "200 €")
    assert etf.unit.bounds(etf.value) == (0.0, 1000.0)
    assert etf.dial(2.0).overrides(2.0) == {"scale": {"savings": {"ETF": 2.0}}}
    assert "the chance to run out of money by 51 little" in etf.help
    assert found["scale", "savings", "Gold plan"].unit.text(1.0) == "50 €"
    rest, harvest = knobs.switches(a)
    assert (rest.path, rest.value, rest.group) == (("invest_rest",), True, sliders.ALLOCATION)
    assert (harvest.path, harvest.value, harvest.group) == (
        ("tax", "harvest"),
        False,
        sliders.TAXES,
    )


@pytest.mark.parametrize(
    ("amount", "every"), [(-100, 3), (-600, 3), (-50, 1), (-75, 1), (-130, 1), (-10, 1)]
)
def test_the_savings_slider_steps_divide_the_rate(data: Path, amount: float, every: int) -> None:
    """The slider returns to the rate of the file, a quarterly plan of 100 € to its 33 € a
    month: its steps divide the rate, as few of them as keep each at most `SAVINGS_STEP`."""
    plan = [Stream(name="ETF", kind=StreamKind.SAVINGS, amount=amount, every=every)]
    found = knobs.knobs(load_assumptions(data), plan, scenario=Scenario(name="s"))
    [step] = [k.unit.step for k in found if k.path == ("scale", "savings", "ETF")]
    rate = -amount / every
    n = round(rate / step)
    assert rate / step == pytest.approx(n)
    assert step <= knobs.SAVINGS_STEP
    assert n == 1 or rate / (n - 1) > knobs.SAVINGS_STEP


def test_gold_and_crypto_classes_get_a_spread_and_a_correlation_beside_their_mean(
    data: Path,
) -> None:
    a = load_assumptions(data)
    a = a.model_copy(
        update={
            "returns": a.returns
            | {
                "gold": ReturnClass(mean=0.05, stdev=0.15),
                "bitcoin": ReturnClass(mean=0.3, stdev=0.85, equity_correlation=0.4),
            }
        }
    )
    held: list[Asset] = [
        GoldAsset(id="bars", kind="gold", value=1000),
        CryptoAsset(id="wallet", kind="crypto", value=1000),
    ]
    found = {k.path: k for k in knobs.knobs(a, [], assets=held)}
    assert {p[1] for p in found if p[-1] == "equity_correlation"} == {"gold", "bitcoin"}
    assert {
        found["returns", c, f].group for c in ("gold", "bitcoin") for f in ("stdev", "mean")
    } == {sliders.GOLD_CRYPTO}
    bitcoin, gold = found["returns", "bitcoin", "mean"], found["returns", "gold", "mean"]
    assert "8.8% a year" in bitcoin.help  # the median path, far below the mean
    assert "conservatively" in bitcoin.help
    assert "conservatively" not in gold.help
    spread = found["returns", "bitcoin", "stdev"].lever(0.85)
    assert (spread.low, spread.high) == (0.75, 0.95)
    # `historical` replays gold and equity, so their means and the spread of gold do nothing
    # there, and draws bitcoin
    off = {p[1:] for p, k in found.items() if p[0] == "returns" and "historical" not in k.models}
    assert {("equity", "mean"), ("gold", "mean"), ("gold", "stdev")} <= off
    assert not {("bitcoin", "mean"), ("bitcoin", "equity_correlation"), ("cash", "mean")} & off
    assert knobs.NOT_HISTORICAL in found["returns", "gold", "mean"].help
    bare = {k.path: k for k in knobs.knobs(a, [])}
    assert not any(p[-1] == "equity_correlation" for p in bare)
    assert bare["returns", "bitcoin", "stdev"].group == sliders.SPREADS
    # without the wallet the narrower range keeps a position of its own: 60% would not fit
    assert bare["returns", "bitcoin", "mean"].key != found["returns", "bitcoin", "mean"].key


def test_event_knobs_move_groups_and_set_amounts(data: Path) -> None:
    (data / "scenarios" / "base.yaml").write_text(
        "name: base\n"
        "phases:\n"
        "  - {from: 2026-01-01, phase: work}\n"
        "  - {from: 2040-09-01, phase: retired, id: retirement}\n"
        "events:\n"
        "  - {at: 2026-03-01, id: sale, type: sell, asset: flat, price: 412000, note: old flat}\n"
    )
    (data / "assets.yaml").write_text(
        "assets:\n  - {id: flat, kind: property, sqm: 10, per_sqm: 100}\n"
    )
    first = load_plan(data, data / "scenarios" / "base.yaml")
    found = {k.path: k for k in knobs.knobs(first.assumptions, [], scenario=first.scenario)}
    sale, price, retirement = (
        found["shift", "sale"],
        found["events", "sale", "price"],
        found["shift", "retirement"],
    )
    assert (sale.label, sale.origin, sale.unit.low) == ("Sale: month", date(2026, 3, 1), -2.0)
    assert "sell 2026-03 (old flat)" in sale.help
    assert (price.value, price.unit.high) == (412000, 825000)
    assert retirement.unit.low == sliders.SHIFT.low
    assert retirement.lever(0).high == 3
    dial = retirement.dial(0)
    assert (dial.whole, dial.text(3.0)) == (True, "2040-12 (age 63)")
    assert dial.overrides(3.0) == {"shift": {"retirement": 3}}


def test_the_price_of_a_purchase_stays_above_what_its_loan_needs(data: Path) -> None:
    """The model refuses a loan above the price with the tax and the costs, so the slider and
    the goal seek stop at that price: 300.000 € over 1.05 in Bavaria, 285.714 €, a step up."""
    (data / "scenarios" / "base.yaml").write_text(
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\nevents:\n"
        "  - {at: 2028-04-01, id: home, type: buy_property, price: 400000, land: BY,\n"
        "     costs: 0.015, property: {id: home},\n"
        "     loan: {id: l, balance: -300000, rate: 0.03, annuity: 1500}}\n"
    )
    first = load_plan(data, data / "scenarios" / "base.yaml")
    price = {k.path: k for k in knobs.knobs(first.assumptions, [], scenario=first.scenario)}[
        "events", "home", "price"
    ]
    assert (price.unit.low, price.unit.high) == (290_000, 800_000)
    assert knobs.LEAST in price.help


def test_explorer_offers_historical_once_the_equity_series_is_there(data: Path) -> None:
    assert runs.models(data) == ["fixed", "montecarlo"]
    series.save(series.SERIES[series.EQUITY], data, [series.Point(date(2000, 1, 1), 100.0)])
    assert runs.models(data) == ["fixed", "montecarlo", "historical"]


EQUITY = ("returns", "equity", "mean")


SEEK = """
from pathlib import Path
from dagobert.loader import load_assumptions
from dagobert.ui import explorer, knobs, runs, seek
data = Path({data!r})
found = {{k.path: k for k in knobs.knobs(load_assumptions(data), [])}}
knob = found["returns", "equity", "mean"]
dial = knob.dial(knob.value)
side = explorer.Sidebar(runs.options(data, "fixed", 1), {{}}, (), (), (dial,), False, {{}}, ())
base = data / "scenarios" / "base.yaml"
seek.goal_seek(side, {{base: "Base"}}, 0.0, [side.opts.run_one(base)])
"""


def test_a_seek_answer_is_kept_in_other_words(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A dial keys the kept answer without its words: the page in other words, as of another
    language, shows that answer in them and seeks no more. The target reads a decimal comma, and
    one beyond its bounds keeps the button off."""
    sought: list[goalseek.Dial] = []
    targets: list[float] = []

    def answer(job: goalseek.Job, dial: goalseek.Dial, __: object) -> goalseek.Found:
        sought.append(dial)
        targets.append(job.target)
        return goalseek.Found(dial.value, 0.04, 10, rising=True, age=51)

    monkeypatch.setattr(seek, "seek", answer)
    at = AppTest.from_string(SEEK.format(data=str(data)), default_timeout=30).run()
    target = at.text_input(key=f"{sliders.KEY}seek-target")
    assert (target.label, target.value) == ("Target, chance to run out by 51 (%)", "5")
    target.set_value("60").run()
    assert at.warning[-1].value == "Target: at most 50"
    assert at.button(key="seek").disabled
    at.text_input(key=f"{sliders.KEY}seek-target").set_value("4,5").run()
    at.selectbox(key=f"{sliders.KEY}seek-lever").set_value("returns.equity.mean").run()
    at.button(key="seek").click().run()
    monkeypatch.setitem(sliders.GROUPS, sliders.MARKETS, "Märkte")
    at.run()
    assert not at.exception
    assert len(sought) == 1
    assert targets == [pytest.approx(0.045)]
    assert any(m.value.startswith("**Base** · Märkte: ") for m in at.markdown)


def test_the_target_names_the_age_of_the_chosen_runs(data: Path) -> None:
    """The age that every run takes the chance to run out at, else 90 with the runs at another
    age in its help, as the summary; each answer names the age of its own runs."""
    short = fixed_run(data)  # 49 to 51
    whole = replace(short, scenario="whole", ages=np.linspace(60.0, 95.0, len(short.months)))
    alone = seek.Target.of([short])
    assert (alone.age, alone.label) == (51, "Target, chance to run out by 51 (%)")
    assert alone.help == "The highest chance to run out of money by 51 that you accept."
    both = seek.Target.of([whole, short])
    assert (both.age, both.label) == (90, "Target, chance to run out by 90 (%)")
    assert both.help.endswith(
        "by 90 that you accept. Where a run does not reach 90, its first "
        "or last age counts instead: base (51)."
    )
    dial = goalseek.Dial("Equity", ((EQUITY, 1.0),), 0.05, 0.0, 0.1, 0.01)
    found = goalseek.Found(0.07, 0.04, 10, rising=False, age=51)
    assert seek.seek_answer("Short", dial, found, 0.05).endswith(
        "A 4.0% chance to run out by 51 there."
    )


CARRIED = """
import streamlit as st
from dagobert.ui import sliders
sliders.carry(arrived=False)
if st.session_state.get("shown", True):
    st.slider("x", 0, 10, key=f"{sliders.KEY}x")
    st.button("Reset", key="reset", on_click=sliders.forget, args=([f"{sliders.KEY}x"],))
sliders.keep()
"""


def test_a_slider_keeps_its_position_while_no_run_draws_it() -> None:
    """As `main.py` runs the pages: a page switch or a closed tab drops the widgets that a run
    does not draw, `carry` brings their values back, and `Reset sliders` forgets them."""
    at = AppTest.from_string(CARRIED).run()
    at.slider(key=f"{sliders.KEY}x").set_value(5).run()
    at.session_state["shown"] = False
    at.run().run()
    at.session_state["shown"] = True
    assert at.run().slider(key=f"{sliders.KEY}x").value == 5
    at.button(key="reset").click().run()
    assert at.slider(key=f"{sliders.KEY}x").value == 0


@pytest.mark.usefixtures("threads")
def test_a_language_switch_runs_nothing_again(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The explorer's caches hold no words (rule `i18n`): in German it shows the runs and the
    sensitivity that English ran, the effects named by the levers in German."""
    ran: dict[str, int] = {"runs": 0, "sensitivity": 0}
    run_one, run = Options.run_one, sensitivity.run

    def counted(self: Options, *args: Any) -> RunResult | None:
        ran["runs"] += 1
        return run_one(self, *args)

    def sensed(*args: Any, **kwargs: Any) -> sensitivity.Sensitivity:
        ran["sensitivity"] += 1
        return run(*args, **kwargs)

    def equity(lang: i18n.Language) -> bool:
        """Whether a bar of the sensitivity charts names the equity return in `lang`."""
        with i18n.use(lang):
            [knob] = [k for k in knobs.knobs(load_assumptions(data), []) if k.path == EQUITY]
        return any(
            str(y).startswith(f"{knob.label} ±")
            for chart in at.get("plotly_chart")
            for trace in json.loads(chart.proto.spec)["data"]
            if trace.get("orientation") == "h"
            for y in trace.get("y", [])
        )

    monkeypatch.setattr(Options, "run_one", counted)
    monkeypatch.setattr(sensitivity, "run", sensed)
    at = opened(AppTest.from_string(ACTIVATE + EXPLORER.format(data=str(data)), default_timeout=60))
    english = dict(ran)
    assert equity("en")
    at.query_params["lang"] = "de"
    opened(at)
    assert not at.exception
    assert at.selectbox(key=f"{sliders.KEY}model").label == "Modell"
    assert all(english.values())
    assert ran == english
    assert equity("de") and not equity("en")


def opened(at: AppTest) -> AppTest:
    """A run with the fold `What moves the result` of the first tab open, as a click opens it:
    `AppTest` sends no state of an expander, so it closes again in the next run."""
    at.session_state[LEVERS] = True
    return at.run()


def figures(at: AppTest) -> int:
    """The sensitivity charts of the page: their bars lie."""
    return sum(
        any(trace.get("orientation") == "h" for trace in json.loads(chart.proto.spec)["data"])
        for chart in at.get("plotly_chart")
    )


class MovedError(Exception):
    """A rerun, as a moved slider raises it at the next Streamlit call of a wait."""


def moved() -> None:
    raise MovedError


@pytest.mark.parametrize("phone", [False, True])
def test_the_sensitivity_runs_while_its_fold_is_open_and_the_sliders_rest(
    data: Path, monkeypatch: pytest.MonkeyPatch, *, phone: bool
) -> None:
    """Closed at first, on a desktop too, so nothing runs. Open, it runs at once while the
    sliders stand. After a move it waits for the sliders to rest under a progress bar, with the
    last result faded and its caption; once they rest the new result replaces both."""
    sensed: list[object] = []
    rests: list[bool] = []
    run = sensitivity.run

    def counted(*args: Any, **kwargs: Any) -> sensitivity.Sensitivity:
        sensed.append(args)
        return run(*args, **kwargs)

    def resting(done: Callable[[], bool], _tick: object, _pause: object) -> None:
        rests.append(done())
        raise MovedError

    monkeypatch.setattr(sensitivity, "run", counted)
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    assert "What moves the result" in [e.label for e in at.expander]
    assert (sensed, figures(at)) == ([], 0)
    opened(at)
    assert (len(sensed), figures(at)) == (1, 2)
    monkeypatch.setattr(explorer, "settle", resting)
    next(s for s in at.slider if s.label == "Inflation").set_value(4.0)
    opened(at)
    assert rests == [False]  # it waits: the sliders just moved
    assert [p.proto.text for p in at.get("progress")] == [
        "What moves the result: starts when the sliders rest"
    ]
    assert "For the sliders before your last move" in [c.value for c in at.caption]
    assert (len(sensed), figures(at)) == (1, 2)  # the last result, faded
    monkeypatch.setattr(explorer, "REST", 0)
    monkeypatch.setattr(explorer, "settle", runs.settle)
    opened(at)
    assert not at.exception
    assert (len(sensed), figures(at)) == (2, 2)
    assert "For the sliders before your last move" not in [c.value for c in at.caption]


def test_the_sliders_rest_since_their_last_move() -> None:
    """Never moved, they rested long ago; a new position rests from the run that saw it."""
    first = explorer.rested(None, "a", 5.0)
    assert first == ("a", -math.inf)
    assert explorer.rested(first, "a", 9.0) == first
    assert explorer.rested(first, "b", 9.0) == ("b", 9.0)


def test_a_wait_calls_into_streamlit_each_tick_until_it_ends() -> None:
    """A rerun stops the script at a Streamlit call: the wait makes one each `TICK`."""
    clock = [0.0]
    ticks: list[float] = []

    def pause(seconds: float) -> None:
        clock[0] += seconds

    runs.settle(lambda: clock[0] >= 3.5 * runs.TICK, lambda: ticks.append(clock[0]), pause)
    assert ticks == pytest.approx([0, runs.TICK, 2 * runs.TICK, 3 * runs.TICK])
    with pytest.raises(MovedError):
        runs.settle(lambda: False, moved, pause)


def test_a_wait_yields_at_a_read_of_the_session_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Streamlit call of a wait (`yielded`) sends the browser nothing: a read of the session
    state, where Streamlit 1.65 checks for a rerun (the script runner's callback)."""
    state = SafeSessionState(SessionState(), moved)
    monkeypatch.setattr(session_state_proxy, "get_session_state", lambda: state)
    with pytest.raises(MovedError):
        runs.yielded()


def test_the_progress_of_the_sensitivity_draws_once_a_second_and_yields_between(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bar drawn after each run kept the browser busy: `throttled` draws at most each `REDRAW`
    and yields at the other ticks."""
    clock, drawn, yields = [0.0], list[int](), list[float]()
    monkeypatch.setattr(runs, "yielded", lambda: yields.append(clock[0]))
    tick = runs.throttled(drawn.append, lambda: clock[0])
    for share in range(1, 26):
        clock[0] = share * runs.REDRAW / 10
        tick(share)
    assert drawn == [10, 20]
    assert len(yields) == 23


def test_an_old_result_shows_in_the_words_and_the_levers_of_this_run() -> None:
    """Its numbers stay, its words follow this run, and an effect of a lever that this run lacks
    goes (a slider that simple mode or the model hides now)."""
    outcome = sensitivity.Outcome(0.1, (1.0,), (1.0,), (90,))
    old = [sensitivity.Lever(f"old {n}", (n,), 1, 0, 2, step="1") for n in "ab"]
    effects = tuple(sensitivity.Effect(lever, outcome, outcome) for lever in old)
    found = sensitivity.Sensitivity("base", date(2026, 1, 1), outcome, effects)
    now = sensitivity.Lever("neu a", ("a",), 1.5, 0.5, 2.5, step="2")
    [effect] = explorer.said(found, [now]).effects
    assert effect.lever == old[0]
    assert (effect.lever.label, effect.lever.step) == ("neu a", "2")


def test_the_run_cache_keeps_the_last_used_runs_within_its_bytes() -> None:
    """The least recently used run goes first, a hit makes a run the newest, and the newest stays
    even alone beyond the bound."""
    found: dict[str, int] = {}
    for key in "abc":
        runs.keep(found, key, 2, 5, int)
    assert list(found) == ["b", "c"]
    runs.keep(found, "b", found["b"], 5, int)
    runs.keep(found, "d", 2, 5, int)
    assert list(found) == ["b", "d"]
    runs.keep(found, "e", 9, 5, int)
    assert list(found) == ["e"]


def test_the_explorer_keeps_its_runs_by_their_bytes_and_computes_each_once(
    data: Path, monkeypatch: pytest.MonkeyPatch, threads: ThreadPoolExecutor
) -> None:
    """`nbytes` counts every array of a run, also those of its dicts. A session that asks for a
    run in the making waits for it, the least recently used run goes above `RUNS_BYTES`, and a
    run whose wait a move stopped lands in the cache all the same."""
    opts, scenario, stamp = runs.options(data, paths=20), data / "scenarios" / "base.yaml", (0.0, 0)
    run = opts.run_one(scenario)
    assert run is not None
    assert run.survival is not None
    wide, narrow = np.zeros(1000), np.zeros(1000, np.float32)
    assert runs.nbytes(replace(run, survival=None)) == runs.nbytes(run) - run.survival.nbytes
    more = replace(
        run, balance={**run.balance, "x": wide}, drivers={**run.drivers, ("x", "y"): narrow}
    )
    assert runs.nbytes(more) == runs.nbytes(run) + wide.nbytes + narrow.nbytes
    calls: list[dict[str, Any]] = []
    started, release = threading.Event(), threading.Event()

    def run_one(_opts: Options, _scenario: Path, overrides: dict[str, Any]) -> RunResult:
        calls.append(overrides)
        started.set()
        release.wait(10)
        return run

    found: dict[tuple[object, ...], RunResult | None] = {}
    monkeypatch.setattr(runs, "_runs", lambda: found)
    monkeypatch.setattr(runs, "RUNS_BYTES", 2 * runs.nbytes(run))
    monkeypatch.setattr(Options, "run_one", run_one)
    with ThreadPoolExecutor(1) as sessions:
        first = sessions.submit(runs.cached_run, opts, scenario, "{}", stamp)
        assert started.wait(10)
        with pytest.raises(MovedError):  # a second session waits for the same run, then moves
            runs.cached_run(opts, scenario, "{}", stamp, moved)
        release.set()
        assert first.result() is run
    for overrides in ('{"a": 1}', '{"a": 2}', "{}", '{"a": 2}'):
        runs.cached_run(opts, scenario, overrides, stamp)
    assert calls == [{}, {"a": 1}, {"a": 2}, {}]  # two runs fit: the first went, the last stayed
    assert runs.cached(opts, scenario, '{"a": 2}', stamp)
    assert not runs.cached(opts, scenario, '{"a": 1}', stamp)
    release.clear()
    with pytest.raises(MovedError):
        runs.cached_run(opts, scenario, '{"a": 3}', stamp, moved)
    assert not runs.cached(opts, scenario, '{"a": 3}', stamp)
    release.set()
    threads.shutdown()  # the runs done, and what they keep
    assert runs.cached(opts, scenario, '{"a": 3}', stamp)


def test_a_run_kept_since_the_miss_of_a_session_is_not_made_again(
    data: Path, monkeypatch: pytest.MonkeyPatch, threads: ThreadPoolExecutor
) -> None:
    """The run of another session lands in the cache between the miss of `cached_run` and its
    `submit`: the submit takes it from there."""
    opts, scenario, stamp = runs.options(data, paths=20), data / "scenarios" / "base.yaml", (0.0, 0)
    run = opts.run_one(scenario)
    found: dict[tuple[object, ...], RunResult | None] = {}
    monkeypatch.setattr(runs, "_runs", lambda: found)
    runs.keep(found, (opts, scenario, "{}", stamp), run)
    calls: list[object] = []
    monkeypatch.setattr(Options, "run_one", lambda *args: calls.append(args))
    future = runs.submit(opts, scenario, "{}", stamp)
    threads.shutdown()
    assert future.result(0) is run
    assert calls == []


def test_a_pool_whose_worker_died_gives_way_to_a_new_one(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worker killed for its memory breaks the pool for good: the next run takes a new pool."""
    monkeypatch.setenv(WORKERS_ENV, "1")
    found: dict[tuple[object, ...], RunResult | None] = {}
    monkeypatch.setattr(runs, "_runs", lambda: found)
    runs.pool.clear()
    broken = runs.pool()
    try:
        with pytest.raises(BrokenProcessPool):
            broken.submit(os._exit, 1).result(60)
        opts, scenario = runs.options(data, paths=20), data / "scenarios" / "base.yaml"
        assert runs.cached_run(opts, scenario, "{}", (0.0, 0)) is not None
        assert runs.pool() is not broken
    finally:
        runs.pool().shutdown()
        runs.pool.clear()


def test_a_run_from_the_cache_shows_no_progress(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Simulating` only while a run is missing: the second visit takes the runs of the first."""
    said: list[str] = []
    monkeypatch.setattr(explorer.Status, "busy", lambda _self, text, then="": said.append(text))
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    assert any(text.startswith("Simulating") for text in said)
    said.clear()
    at.run()
    assert not at.exception
    assert not any(text.startswith("Simulating") for text in said)


def test_a_restart_takes_the_runs_and_the_sensitivity_from_the_disk(
    data: Path, monkeypatch: pytest.MonkeyPatch, threads: ThreadPoolExecutor
) -> None:
    """A new process forgets the runs, the `fixed` run and the sensitivity; the next page takes
    them from `.cache`, also in German (the names hold no words), and runs no engine."""
    ran: dict[str, int] = {"runs": 0, "sensitivity": 0}
    run_one, run = Options.run_one, sensitivity.run

    def counted(self: Options, *args: Any) -> RunResult | None:
        ran["runs"] += 1
        return run_one(self, *args)

    def sensed(*args: Any, **kwargs: Any) -> sensitivity.Sensitivity:
        ran["sensitivity"] += 1
        return run(*args, **kwargs)

    monkeypatch.setattr(Options, "run_one", counted)
    monkeypatch.setattr(sensitivity, "run", sensed)
    opened(AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60))
    threads.shutdown()  # the runs done, and what they keep: a run after it raises
    assert all(ran.values())
    restarted: dict[tuple[object, ...], RunResult | None] = {}
    monkeypatch.setattr(runs, "_runs", lambda: restarted)
    runs.answers.clear()
    fixed.forget()
    ran.update(dict.fromkeys(ran, 0))
    at = AppTest.from_string(ACTIVATE + EXPLORER.format(data=str(data)), default_timeout=60)
    at.query_params["lang"] = "de"
    opened(at)
    assert not at.exception
    assert ran == {"runs": 0, "sensitivity": 0}
    assert restarted
    assert figures(at) == 2


def test_explorer_workers_follow_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(WORKERS_ENV, "3")
    assert runs.workers() == 3
    monkeypatch.delenv(WORKERS_ENV)
    assert 1 <= runs.workers() <= runs.WORKERS


def test_a_scenario_name_with_markdown_shows_as_written_in_the_strip_and_the_captions(
    data: Path,
) -> None:
    """`$400k vs $500k` is no LaTeX, `_rent` no emphasis: the strip of a phone and the caption of
    the difference escape the name; the Overview subheader too."""
    name = "Buy at $400k vs $500k_rent"
    (data / "scenarios" / "base.yaml").write_text(
        f"name: {name}\nphases: [{{from: 2026-01-01, phase: work}}]\n"
    )
    escaped = r"Buy at \$400k vs \$500k\_rent"
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60)
    at.query_params["mobile"] = "1"
    at.run()
    assert any(m.value.startswith(f"**{escaped}** ") for m in at.markdown)
    at.sidebar.selectbox[0].set_value("fixed")
    next(s for s in at.slider if s.label == "Inflation").set_value(4.0).run()
    assert any(c.value == f"{escaped} (as saved) less {escaped}" for c in at.caption)
    overview = AppTest.from_string(OVERVIEW.format(data=str(data)), default_timeout=60).run()
    assert [h.value for h in overview.subheader][:1] == [f"Main scenario: {escaped}"]


def test_explorer_reruns_on_slider(data: Path) -> None:
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    assert [row["Scenario"] for row in at.dataframe[0].value.to_dict("records")] == ["base"]
    assert any(
        c.value == "The sliders stand at the values of the run (as saved)." for c in at.caption
    )
    at.selectbox(key="explorer-seek-lever").set_value(seek.WORK).run()  # no salary: why
    assert any(m.value.startswith("**base** · No phase of the") for m in at.markdown)
    at.sidebar.selectbox[0].set_value("fixed")
    next(s for s in at.slider if s.label == "Inflation").set_value(4.0).run()
    assert not at.exception
    # the table keeps its rows and shows the change against the files, the tabs show both runs
    assert at.dataframe[0].value["Scenario"].tolist() == ["base"]
    assert at.dataframe[0].value[report.BROKE_AT][0].endswith(" pt)")
    assert [tab.label for tab in at.tabs] == ["base", "base (as saved)"]
    assert [h.value for h in at.subheader] == ["Difference of two runs"]
    assert any(c.value.startswith("Money in € of 2026-01.") for c in at.caption)
    moved = (
        "Sliders moved: Inflation 2.00% → 4.00%. "
        "In brackets: the change against the run (as saved)."
    )
    assert any(c.value == moved for c in at.caption)
    # more than three: a count, and a list with a line per slider
    for s in [s for s in at.slider if not s.disabled and s.label != "Inflation"][:3]:
        s.set_value(s.max)
    at.run()
    assert not at.exception
    assert not any(c.value.startswith("Sliders moved:") for c in at.caption)
    assert "4 sliders moved" in {p.proto.popover.label for p in at.get("popover")}
    lists = [m.value.split("\n") for m in at.markdown if m.value.startswith("- ")]
    assert any(len(x) == 4 and "- Inflation 2.00% → 4.00%" in x for x in lists)
    at.sidebar.toggle[0].set_value(True).run()
    assert not at.exception
    assert any(c.value.startswith("Money in nominal €.") for c in at.caption)


def test_a_chosen_scenario_that_does_not_load_stops_the_explorer_after_the_sidebar(
    data: Path,
) -> None:
    """Its run raises the problem, which the app shows; the sliders draw first, so a second
    scenario cannot hide them."""
    (data / "scenarios" / "broken.yaml").write_text(
        "name: broken\nphases: [{from: 2026-01-01, phase: work}]\n"
        "overrides: {assets: {ghost: {value: 1}}}\n"
    )
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60).run()
    assert at.multiselect[0].value == ["base", "broken"]
    assert at.exception[0].message.startswith("scenarios/broken.yaml:3: overrides.assets.ghost")
    assert any(s.label == "Inflation" for s in at.slider)


@pytest.mark.parametrize(
    ("rule", "refused", "phone"),
    [({"trigger": 0.25, "ceiling": 0}, 20, False), ({"trigger": 1.2, "ceiling": 1.5}, 100, True)],
    ids=["unset ceiling", "trigger above its range, phone"],
)
def test_a_slider_position_that_the_model_refuses_names_the_problem(
    data: Path, rule: dict[str, float], refused: float, *, phone: bool
) -> None:
    """A file value widens a range into the other slider: the ceiling at the trigger names the
    problem instead of the results, on a phone also in the strip above the sliders, the sliders
    stay, and moving one back runs again."""
    spending = {"base": "no_pay", "cut": 0.25, "increase": 0.1, "categories": ["wohnen"]} | rule
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(f"{assumptions.read_text()}spending: {json.dumps(spending)}\n")
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60)
    if phone:
        at.query_params["mobile"] = "1"
    at.run()

    def move(position: float) -> None:  # a run builds new elements: find the slider anew
        ceiling = next(s for s in at.slider if s.label == "Increase when wealth rises above")
        ceiling.set_value(position).run()
        assert not at.exception

    move(refused)
    assert "is not above trigger" in at.main.warning[0].value
    assert [w.value for w in at.sidebar.warning] == [at.main.warning[0].value] * phone
    assert any(c.value.startswith("Not simulated:") for c in at.caption)
    assert not at.dataframe
    move(rule["ceiling"] * 100)
    assert not at.warning
    assert at.dataframe[0].value["Scenario"].tolist() == ["base"]


def test_explorer_moves_the_classes_of_gold_and_crypto(data: Path) -> None:
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(
        f"{assumptions.read_text()}"
        "  gold: {mean: 0.05, stdev: 0.15}\n"
        "  bitcoin: {mean: 0.3, stdev: 0.85, equity_correlation: 0.4}\n"
    )
    assets_yaml = data / "assets.yaml"
    assets_yaml.write_text(
        f"{assets_yaml.read_text()}"
        "  - id: bars\n    kind: gold\n    value: 2000\n"
        "  - id: wallet\n    kind: crypto\n    value: 1000\n"
    )
    months = [add_months(date(2000, 1, 1), i) for i in range(36)]
    points = [series.Point(m, 100.0 * 1.01**i) for i, m in enumerate(months)]
    series.save(series.SERIES[series.EQUITY], data, points)
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60).run()
    assert not at.exception
    labels = [s.label for s in at.slider]
    assert labels.index("Bitcoin correlation") == labels.index("Bitcoin spread") + 1
    assert not at.slider[labels.index("Bitcoin correlation")].disabled
    at.slider[labels.index("Bitcoin correlation")].set_value(0.6).run()
    assert any(
        c.value.startswith("Sliders moved: Bitcoin correlation 0.40 → 0.60.") for c in at.caption
    )
    at.sidebar.selectbox[0].set_value("fixed").run()
    assert not at.exception
    assert at.slider[labels.index("Bitcoin correlation")].disabled  # `fixed` draws nothing
    # an off slider keeps its position but moves nothing
    assert not any(c.value.startswith("Sliders moved:") for c in at.caption)
    at.sidebar.selectbox[0].set_value("historical").run()
    assert not at.exception
    off = {s.label for s in at.slider if s.disabled}
    assert {"Gold return", "Gold spread", "Equity return"} <= off  # replayed
    assert not {"Bitcoin return", "Bitcoin correlation"} & off  # drawn


def test_the_help_of_a_slider_speaks_of_the_chance_to_run_out(data: Path) -> None:
    """Plain words: the term `P(broke)` stays in the column help of the table."""
    streams = [Stream(name="ETF", kind=StreamKind.SAVINGS, amount=-500)]
    helps = [k.help for k in knobs.knobs(load_assumptions(data), streams)]
    assert any("chance to run out of money" in h for h in helps)
    assert not [h for h in helps if "P(broke)" in h]


def _applied(
    dial: goalseek.Dial, found: goalseek.Found, by_path: dict[tuple[str, ...], sliders.Knob]
) -> dict[tuple[str, ...], float]:
    """The value that `Apply to sliders` gives each slider, by its path."""
    at = seek.slider_positions(dial, found, 0.05, by_path)
    return {k.path: at[k.key] for k in by_path.values() if k.key in at}


def test_apply_to_sliders_moves_the_month_of_the_change_out_of_work(data: Path) -> None:
    """The month slider of that change reaches the range of the work seek of every chosen
    scenario, beyond its own."""
    (data / "cashflows.yaml").write_text(
        "streams:\n  - {name: Lohn, kind: salary, gross: 5000, phases: [work]}\n"
    )
    for name, at in (("base", "2040-09"), ("early", "2030-01")):
        (data / "scenarios" / f"{name}.yaml").write_text(
            f"name: {name}\nphases:\n  - {{from: 2026-01-01, phase: work}}\n"
            f"  - {{from: {at}-01, phase: retired, id: retirement}}\n"
        )
    first, other = (load_plan(data, data / "scenarios" / f"{n}.yaml") for n in ("base", "early"))
    dials = [goalseek.work(first), goalseek.work(other)]
    early = goalseek.Found(dials[0].low, 0.04, 10, rising=False)  # 2026-01, 176 months earlier
    late = goalseek.Found(dials[1].high, 0.04, 10, rising=False)  # age 70 from 2030-01
    month = ("shift", "retirement")
    for work in ([], dials[:1], dials):
        by_path = {
            k.path: k
            for k in knobs.knobs(first.assumptions, [], scenario=first.scenario, work=work)
        }
        assert _applied(dials[0], early, by_path) == ({month: dials[0].low} if work else {})
        assert _applied(dials[1], late, by_path) == (
            {month: dials[1].high} if work == dials else {}
        )


def test_apply_to_sliders_sets_the_positions_of_the_value_found(data: Path) -> None:
    """A slider, or `All spending`; nothing when the target is
    missed, the lever has no effect, a path has no slider or the value lies beyond it."""
    streams = [
        Stream(name="Miete", cat="wohnen", amount=-500),
        Stream(name="Reisen", cat="reisen", amount=-400),
    ]
    by_path = {k.path: k for k in knobs.knobs(load_assumptions(data), streams)}
    inflation = by_path["inflation", "mean"]
    hit = goalseek.Found(0.03, 0.04, 10, rising=True)
    assert seek.slider_positions(inflation.dial(0.02), hit, 0.05, by_path) == {inflation.key: 3.0}
    overall = by_path["scale", "spending"]
    spending = goalseek.spending(plan([Stream(name="Miete", cat="wohnen", amount=-500)], []))
    found = goalseek.Found(1.2, 0.04, 10, rising=True)
    assert seek.slider_positions(spending, found, 0.05, by_path) == {overall.key: 120.0}
    missed = goalseek.Found(0.03, 0.06, 10, rising=True)
    flat = goalseek.Found(0.03, 0.04, 10, rising=None)
    beyond = goalseek.Found(
        2.5, 0.04, 10, rising=True
    )  # 250% of the housing, its slider ends at 200%
    unknown = goalseek.Dial("x", ((("x",), 1.0),), 1.0, 0.0, 2.0, 0.1)
    for dial, result in (
        (inflation.dial(0.02), missed),
        (inflation.dial(0.02), flat),
        (spending, beyond),
    ):
        assert seek.slider_positions(dial, result, 0.05, by_path) == {}
    assert seek.slider_positions(unknown, hit, 0.05, by_path) == {}


def test_a_scenario_compares_with_the_nearest_one_that_it_extends_and_runs(data: Path) -> None:
    """`Compare in the Explorer` runs a scenario beside its parent, a template skipped, and the
    difference takes the child as B, its parent as A; without such a pair the first two."""
    files = {
        "tpl": "name: Template\nabstract: true\nextends: base\n",
        "buy": "name: Buy\nextends: tpl\n",
        "solo": "name: Buy\nphases: [{from: 2026-01-01, phase: work}]\n",  # a shared name
    }
    for stem, text in files.items():
        (data / "scenarios" / f"{stem}.yaml").write_text(text)
    concrete = scenariofiles.concrete_scenarios(data)
    assert explorer.compared_with(concrete, "buy") == ["base", "buy"]
    assert explorer.compared_with(concrete, "base") == ["base"]
    stems = ("solo", "buy", "base")
    labels = scenariofiles.scenario_labels({s: load_scenario(concrete[s]).name for s in stems})
    parents = explorer.extended({concrete[s]: labels[s] for s in stems})
    assert parents == {"Buy (buy)": "base"}
    assert explorer.pair([labels[s] for s in stems], parents) == ("base", "Buy (buy)")
    assert explorer.pair(["Buy (solo)", "Buy (buy)"], parents) == ("Buy (solo)", "Buy (buy)")


def test_the_strip_of_a_phone_compares_with_the_run_of_the_files(data: Path) -> None:
    run = runs.options(data, "fixed").run_one(data / "scenarios" / "base.yaml")
    assert run is not None
    twin = replace(run, twin=True)
    alone = explorer.strip([run], nominal=False)
    twins = explorer.strip([run, twin], nominal=False)
    name, broke, _, total = alone.split(" ", 3)
    assert name == "**base**"
    assert twins == f"{name} {broke} (+0.0 pt) · {total} (+0 €)"  # one line, no change
    # the table holds the run of the sliders only, with the change against the files
    [row] = explorer.compared([run, twin], nominal=False)
    assert row["Scenario"] == "base"
    assert row[report.BROKE_AT] == f"{broke} (+0.0 pt)"
    assert row[report.TOTAL_AT].endswith(" (+0 €)")


def _row(**changed: Any) -> report.SummaryRow:
    row = report.SummaryRow(
        "t", 0.10, 0.05, 1000.0, 500_000.0, 400_000.0, 90_000.0, 80.0, 4, 2, 0.3, 0.2
    )
    return replace(row, **changed)


def test_the_table_shows_the_change_as_saved_in_every_column() -> None:
    mine = _row(
        p_broke=0.125, p_broke_alive=0.0, shortfall=2500.0, median_total=499_000.0,
        median_liquid=401_500.0, median_taxes=90_000.0, liquid_p5_zero_age=77.0,
        reduced_months=7, raised_months=1, p_care=0.3, p_disability=0.25,
    )  # fmt: skip
    changes = report.changes(mine, _row())
    assert changes == {
        report.BROKE_AT: "+2.5 pt",
        report.BROKE_ALIVE: "-5.0 pt",
        "Shortfall": "+1.500 €",
        report.TOTAL_AT: "-1.000 €",
        report.COLUMNS[5].term: "+1.500 €",
        "Taxes": "+0 €",
        "Liquid p5<0": "-3 years",
        "Cuts": "+3 months",
        "Raises": "-1 month",
        "P(care)": "+0.0 pt",
        "P(disability)": "+5.0 pt",
    }
    never, shortfall = _row(liquid_p5_zero_age=None), _row(shortfall=None)
    assert report.changes(never, _row())["Liquid p5<0"] == "as saved: 80"
    assert report.changes(_row(), never)["Liquid p5<0"] == "as saved: never"
    assert report.changes(_row(), shortfall)["Shortfall"] == "as saved: none"
    assert "Shortfall" not in report.changes(shortfall, shortfall)
    assert set(explorer.CHANGED_WIDTHS) == set(changes)


def test_the_summary_shows_long_scenario_names_on_a_desktop() -> None:
    long = ["FIRE at 50 with the flat kept, a sabbatical of a year and a move abroad", "Work"]
    columns = [Shown(c.term, c.term, "") for c in report.COLUMNS]
    desktop, phone, changed = (
        explorer.summary_widths(long, columns, compact=compact, changed=changed)
        for compact, changed in ((False, False), (True, False), (False, True))
    )
    # the grid sizes a name roughly and cut two variants of a plan to the same start
    assert desktop == {"Scenario": explorer.SCENARIO_WIDTH}
    assert phone == {"Scenario": tables.PHONE_PINNED}  # pinned while the numbers scroll
    assert changed == desktop | explorer.CHANGED_WIDTHS  # room for a change in brackets
    # short names leave the headers their room: the table fits 1,500 px with the sidebar
    short = explorer.summary_widths(
        ["Work to 65", "Stress test"], columns, compact=False, changed=False
    )
    assert short["Scenario"] < explorer.SCENARIO_WIDTH / 2


def test_a_long_header_widens_its_column_with_a_change() -> None:
    columns = [Shown(c.term, "x" * 40 if c.change else c.term, "") for c in report.COLUMNS]
    widths = explorer.summary_widths(["Work"], columns, compact=False, changed=True)
    assert all(widths[term] > explorer.CHANGED_WIDTHS[term] for term in explorer.CHANGED_WIDTHS)


def _labels(drawn: Drawn) -> set[str]:
    return {c.label for members in drawn.groups.values() for c in members}


def test_simple_mode_draws_the_sliders_that_the_plan_sets_or_the_viewer_moved(data: Path) -> None:
    """Simple mode leaves out a slider of an expert field at its default and of a class that no
    asset holds, and its note names them, a whole group by its name. A field that the files set
    away from its default and a moved slider show, and advanced mode shows all. A feature off
    hides its sliders in both modes, and the note names the feature."""
    first = load_plan(data, data / "scenarios" / "base.yaml")
    a = first.assumptions
    controls: list[sliders.Knob | sliders.Switch] = [
        *knobs.knobs(a, load_streams(data), assets=first.assets),
        *knobs.switches(a),
    ]
    held = knobs.classes(first.assets)
    assert held == {"equity", "fixed_income", "cash"}  # the giro: no property

    def drawn(advanced: bool, off: frozenset[Feature] = frozenset(), moved: str = "") -> Drawn:
        return explorer.drawn(
            controls, explorer.View(mode.View(mode.uses(data), off, advanced), held), {moved}
        )

    every = {c.label for c in controls}
    assert (_labels(drawn(advanced=True)), drawn(advanced=True).expert) == (every, [])
    simple = drawn(advanced=False)
    assert {"Wohnen", "Inflation", "Equity return", "Cash return"} <= _labels(simple)
    hidden = ["Property return", "Equity spread", "Pension growth", "Realize gains"]
    assert not set(hidden) & _labels(simple)
    assert {"Property return", "Equity spread", "Taxes"} <= set(simple.expert)
    growth = next(c for c in controls if c.path == ("pension_growth",))
    assert "Pension growth" in _labels(drawn(advanced=False, moved=growth.key))
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("pension_growth: 0.01\n")  # set away from its default (rule mode)
    assert _labels(drawn(advanced=False)) == _labels(simple) | {"Pension growth"}
    off = frozenset({Feature.PROPERTY})
    without = drawn(advanced=True, off=off)
    loan = "Loan rate after the fixed period"
    assert (_labels(without), without.off, without.expert) == (every - {loan}, off, [])


def test_what_the_viewer_moved_stays_in_simple_mode(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model, nominal euros, an expert slider and a switch set in advanced mode stay after
    the switch to simple mode and keep their overrides; what stands at its default goes, and a
    note names it. The levers of the goal seek are the sliders drawn. A desktop folds the charts
    as a phone; the sensitivity waits for its fold in either mode."""
    sensed: list[object] = []
    run = sensitivity.run

    def counted(*args: Any, **kwargs: Any) -> sensitivity.Sensitivity:
        sensed.append(args)
        return run(*args, **kwargs)

    monkeypatch.setattr(sensitivity, "run", counted)
    at = AppTest.from_string(EXPLORER.format(data=str(data)), default_timeout=60).run()
    at.selectbox(key=f"{sliders.KEY}model").set_value("fixed")
    at.toggle(key=f"{sliders.KEY}nominal").set_value(True)
    next(s for s in at.slider if s.label == "Pension growth").set_value(1.0)
    next(t for t in at.toggle if t.label == "Realize gains").set_value(True)
    at.run()
    assert sensed == []
    at.query_params["mode"] = "simple"
    at.run()
    assert not at.exception
    assert at.selectbox(key=f"{sliders.KEY}model").value == "fixed"
    assert at.toggle(key=f"{sliders.KEY}nominal").value
    drawn = [s.label for s in at.slider]
    assert "Pension growth" in drawn
    assert "Equity spread" not in drawn
    assert "Realize gains" in [t.label for t in at.toggle]
    assert "Paths" not in [s.label for s in at.select_slider]
    assert [tab.label for tab in at.tabs] == ["base", "base (as saved)"]  # the overrides hold
    moved = next(c.value for c in at.caption if c.value.startswith("Sliders moved:"))
    assert "Pension growth 0.00% → 1.00%" in moved
    assert "Realize gains off → on" in moved
    assert any(
        c.value.startswith("Hidden in simple mode (at the values as saved): Paths, Equity spread")
        for c in at.caption
    )
    levers = at.selectbox(key=f"{sliders.KEY}seek-lever").options[len(seek.LEVERS) :]
    assert [o.split(": ", 1)[1] for o in levers] == [s.label for s in at.slider if not s.disabled]
    folds = [e.label for e in at.expander]
    assert {"Net worth", "Will the money last?", "What moves the result"} <= set(folds)
    assert sensed == []
    at.button(key="sliders-reset").click().run()
    assert "Pension growth" not in [s.label for s in at.slider]
    assert "Realize gains" not in [t.label for t in at.toggle]


def test_simple_mode_speaks_german_in_the_explorer(data: Path) -> None:
    at = render(data, EXPLORER, lang="de", mode="simple")
    assert leaks(words(at)) == []
    assert any(c.value.startswith("Im einfachen Modus ausgeblendet") for c in at.caption)
