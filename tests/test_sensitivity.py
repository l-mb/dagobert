"""The sensitivity run: the levers ranked by their effect on the plan."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dagobert import report, sensitivity
from dagobert.goalseek import Dial
from dagobert.loader import load_assumptions
from dagobert.report.charts import GRAY, GREEN, RED
from dagobert.runner import Options
from dagobert.sensitivity import Effect, Job, Lever, Outcome, Sensitivity, run
from dagobert.ui import knobs

EQUITY = Lever(
    "Equity return", ("returns", "equity", "mean"), 0.05, 0.04, 0.06, "%.2f%%", 100, "1.00%"
)
EQUITY_DIAL = Dial(
    "Markets: Equity return", ((EQUITY.path, 1.0),), 0.05, -0.02, 0.15, 0.0025, "%.2f%%", 100
)
REFINANCE = Lever("Refinance rate", ("refinance_rate",), 0.04, 0.03, 0.05)
AT_BOUND = Lever("Cash buffer", ("cash_buffer_months",), 0.0, 0.0, 3.0)
EVERY = 0.01  # seconds between two ticks: a test waits for no page


def _job(data: Path) -> Job:
    opts = Options(data=data, out=data, model="fixed", paths=1, seed=42, mortality=True)
    return Job(opts, data / "scenarios" / "base.yaml", {})


def test_levers_rank_by_effect_and_a_side_at_its_bound_is_the_base_run(data: Path) -> None:
    ticks: list[float] = []
    with ThreadPoolExecutor(2) as pool:
        found = run(_job(data), [REFINANCE, AT_BOUND, EQUITY], pool, 2, ticks.append, every=EVERY)
    assert found.scenario == "base"
    assert ticks == sorted(ticks)
    assert ticks[-1] == 1
    assert set(ticks) <= {i / 6 for i in range(7)}  # base, 2 + 1 + 2 sides
    first, *rest = found.effects
    assert first.lever is EQUITY
    assert first.low.totals[-1] < found.base.totals[-1] < first.high.totals[-1]
    by_label = {e.lever.label: e for e in rest}
    assert by_label["Refinance rate"].low == by_label["Refinance rate"].high == found.base
    assert by_label["Cash buffer"].low is found.base


@pytest.mark.parametrize(
    ("band", "side"),
    [({"trigger": 0.25, "ceiling": 0}, "high"), ({"trigger": 1.2, "ceiling": 1.3}, "low")],
    ids=["no ceiling", "above the ranges"],
)
def test_a_side_that_the_model_refuses_is_the_base_run(
    data: Path, band: dict[str, float], side: str
) -> None:
    """A step of the explorer's ceiling to the trigger or below it, which the model refuses:
    from a ceiling of 0 (the increase off) up, from file values above the ranges down."""
    rule = {"base": "no_pay", "increase": 0.1, "categories": ["wohnen"]} | band
    with (data / "assumptions.yaml").open("a") as f:
        f.write(f"spending: {json.dumps(rule)}\n")
    levers = [k.lever(k.value) for k in knobs.knobs(load_assumptions(data), [])]
    with ThreadPoolExecutor(2) as pool:
        found = run(_job(data), levers, pool, 2, lambda _: None, every=EVERY)
    ceiling = next(e for e in found.effects if e.lever.path == ("spending", "ceiling"))
    assert getattr(ceiling.lever, side) != ceiling.lever.value
    assert getattr(ceiling, side) is found.base


def test_a_tick_comes_while_a_run_takes_long_and_a_failing_one_stops_the_run(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tick comes every `every` seconds, also while no run ends, so a moved slider stops the
    run at once, whatever a run takes. At most `workers` runs go into the pool at a time, the
    next after a tick: a tick that raises leaves the pool to the next runs of the page."""

    class Counted(ThreadPoolExecutor):
        submitted = 0

        def submit(self, *args: Any, **kwargs: Any) -> Any:
            self.submitted += 1
            return super().submit(*args, **kwargs)

    release = threading.Event()
    ticks: list[float] = []

    def stop(share: float) -> None:
        ticks.append(share)
        if len(ticks) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(sensitivity, "outcome", lambda *_args: release.wait(10))
    with Counted(1) as pool, pytest.raises(KeyboardInterrupt):
        try:
            run(_job(data), [EQUITY], pool, 1, stop, every=EVERY)
        finally:
            release.set()
    assert ticks == [0, 0, 0]  # the base run has not ended
    assert pool.submitted == 1  # the base run, of three


def _bars(fig: dict[str, Any]) -> list[dict[str, Any]]:
    """The traces with bars, not the entries of a legend."""
    return [t for t in fig["data"] if any(t["y"])]


def test_sensitivity_figure_has_two_bars_per_measure(data: Path) -> None:
    with ThreadPoolExecutor(2) as pool:
        found = run(_job(data), [REFINANCE, EQUITY], pool, 2, lambda _: None, every=EVERY)
    fig = report.sensitivity_figure(found, plan=True).to_dict()
    assert fig["layout"]["title"]["text"] == "base: one step of each part of the plan"
    assert [t["name"] for t in _bars(fig)] == ["one step down", "one step up"] * 3
    down = [t for t in _bars(fig) if t["name"] == "one step down"]
    largest_on_top = ["Refinance rate", "Equity return ±1.00%"]  # plotly draws the first below
    assert all(list(t["y"]) == largest_on_top for t in down)
    assert fig["layout"]["barmode"] == "overlay"
    # opposite ways or no effect: full bars
    assert all(list(t["width"]) == [0.7, 0.7] for t in _bars(fig) if t["name"] == "one step up")
    assert all("Equity return 4.00%" in t["hovertext"][1] for t in down)
    # rent, no income; the run ends at 51, where it measures what it would at 67 and 90
    assert fig["layout"]["annotations"][0]["text"] == "Chance to run out by 51: 100.0%"
    total = "Net worth at 51,"
    assert fig["layout"]["annotations"][1]["text"].startswith(f"{total} € of 2026-01")
    nominal = report.sensitivity_figure(found, plan=False, nominal=True).to_dict()
    assert nominal["layout"]["title"]["text"] == "base: one step of each assumption"
    assert nominal["layout"]["annotations"][1]["text"].startswith(f"{total} nominal €")
    phone = report.sensitivity_figure(found, plan=True, compact=True, measure=1).to_dict()
    assert [t["name"] for t in _bars(phone)] == ["one step down", "one step up"]
    assert "annotations" not in phone["layout"]
    assert phone["layout"]["title"]["subtitle"]["text"].startswith(total)
    # zero and the end of the bars farther from it: plotly's own ticks turned on a phone, and a
    # nearer end ran into the label of zero
    far = max((x for t in _bars(phone) for x in t["x"]), key=abs)
    zero, end = phone["layout"]["xaxis"]["tickvals"]
    assert zero == 0 and 0 < end / far <= 1
    assert "tickvals" not in fig["layout"]["xaxis"]
    # the sides and the colors in one legend, whose rows line up
    keys = [t for t in phone["data"] if t not in _bars(phone)]
    assert len(keys) == 4 and all(t.get("legend", "legend") == "legend" for t in keys)


def _outcome(p_broke: float, total: float) -> Outcome:
    return Outcome(p_broke, (total, total), (total, total), (67, 90))


def test_a_bar_takes_the_color_of_its_effect_on_its_measure() -> None:
    """Green where the step improves the measure of its panel (less risk, more net worth), red
    where it worsens it; one step down striped. The legend and the hover name both."""
    base = _outcome(0.10, 500_000)
    spending = Lever("Spending", ("spending",), 1.0, 0.9, 1.1)
    equity = Lever("Equity share", ("allocation",), 0.6, 0.5, 0.7)  # at its bound below
    found = Sensitivity(
        "base",
        date(2026, 1, 1),
        base,
        (
            Effect(spending, _outcome(0.05, 600_000), _outcome(0.20, 400_000)),
            Effect(equity, base, _outcome(0.12, 550_000)),  # more risk, more net worth
        ),
    )
    fig = report.sensitivity_figure(found, plan=False).to_dict()
    colors = {
        (t["xaxis"], t["name"], lever): color
        for t in _bars(fig)
        for lever, color in zip(t["y"], t["marker"]["color"], strict=True)
    }
    up, down = "one step up", "one step down"
    for panel in ("x", "x2", "x3"):  # the risk, the net worth at 67 and at 90
        assert colors[panel, up, "Spending"] == RED
        assert colors[panel, down, "Spending"] == GREEN
        assert colors[panel, down, "Equity share"] == GRAY
    assert colors["x", up, "Equity share"] == RED
    assert colors["x2", up, "Equity share"] == colors["x3", up, "Equity share"] == GREEN
    assert all(("pattern" in t["marker"]) == (t["name"] == down) for t in _bars(fig))
    shown = [t["name"] for t in fig["data"] if t not in _bars(fig)]
    assert sorted(shown) == ["better", "one step down", "one step up", "worse"]
    risk_up = next(t for t in _bars(fig) if (t["xaxis"], t["name"]) == ("x", up))
    hover = next(h for h in risk_up["hovertext"] if h.startswith("Spending"))
    assert hover.startswith("Spending 1.1 (one step up)<br>")
    assert hover.endswith("20.0% (+10.0 pt, worse)")


def test_outcomes_carry_both_units(data: Path) -> None:
    """The explorer switches the unit without new runs. Prices rise by 2% a year by default,
    so the debt of the rent shrinks in euros of the start."""
    with ThreadPoolExecutor(1) as pool:
        found = run(_job(data), [], pool, 2, lambda _: None, every=EVERY)
    assert all(
        nominal < real < 0
        for real, nominal in zip(found.base.totals, found.base.nominal_totals, strict=True)
    )


@pytest.mark.parametrize("item", [EQUITY, EQUITY_DIAL], ids=["lever", "dial"])
def test_a_lever_and_a_dial_stay_the_same_in_other_words(item: Lever | Dial) -> None:
    """The explorer keeps the sensitivity runs and the seek answers by them: a page in another
    language finds them and names them in its own words."""
    worded = replace(item, label="Aktienrendite", format="%.2f %%")
    assert worded == item
    assert hash(worded) == hash(item)
    assert replace(item, value=0.06) != item
