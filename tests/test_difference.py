"""Two runs compared path by path."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from builders import cash, plan

from dagobert import report
from dagobert.difference import Difference
from dagobert.engine.simulation import simulate
from dagobert.model.assets import EquityAsset, PropertyAsset
from dagobert.model.assumptions import Distribution, ReturnClass
from dagobert.model.events import SellEvent
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream
from dagobert.result import RunResult
from dagobert.returns import MonteCarloProvider

MONTHS = 48
CARE = {
    "hazard": [{"age": 40, "factor": 0.2}],
    "cost": 1000,
    "index": None,
    "duration": {"mean": 12, "stdev": 6},
}


def _run(sale: date, paths: int = 300) -> RunResult:
    """Drawn returns, care episodes and a sale price with a spread. Without the sale the
    liquid assets last about two years."""
    p = plan(
        [Stream(name="Leben", amount=-2000)],
        [
            cash(20_000),
            EquityAsset(id="d", kind="equity", value=30_000, cost_basis=20_000),
            PropertyAsset(id="h", kind="property", sqm=100, per_sqm=1000),
        ],
        Scenario(
            name=f"sale {sale:%Y-%m}",
            events=[SellEvent(at=sale, type="sell", asset="h", price_stdev=0.1)],
        ),
        care=CARE,
        inflation=Distribution(mean=0.02, stdev=0.01),
        returns={
            "equity": ReturnClass(mean=0.06, stdev=0.16),
            "fixed_income": ReturnClass(mean=0.03, stdev=0.02),
            "cash": ReturnClass(mean=0.0),
            "property": ReturnClass(mean=0.02, stdev=0.03),
        },
        cash_buffer_months=1,
    )
    return simulate(
        p, MonteCarloProvider(p.assumptions, paths, seed=1).sample(MONTHS), "montecarlo"
    )


def test_a_run_against_itself_is_zero_everywhere() -> None:
    r = _run(date(2027, 1, 1))
    d = Difference.of(r, r)
    for values in (d.total, d.liquid, d.taxes, *d.broke_only):
        assert not np.any(values)
    cells = {c for row in report.difference_table(d) for k, c in row.items() if k.startswith("at")}
    assert cells == {"+0 €", "0.0%"}


def test_a_later_event_changes_nothing_before_its_date() -> None:
    early, late = _run(date(2027, 1, 1)), _run(date(2029, 1, 1))
    d = Difference.of(early, late)
    for values in (d.total, d.liquid, d.taxes[None], *(b[None] for b in d.broke_only)):
        assert not np.any(values[:, :12])
    assert np.all(d.total[:, 12:24] != 0)
    assert d.broke_only[0].max() == 0 < d.broke_only[1].max()  # only the late sale runs dry


def test_runs_of_different_paths_do_not_pair() -> None:
    with pytest.raises(ValueError, match="months or paths"):
        Difference.of(_run(date(2027, 1, 1)), _run(date(2027, 1, 1), paths=100))


def test_a_phone_stacks_total_and_liquid_on_one_scale() -> None:
    d = Difference.of(_run(date(2027, 1, 1)), _run(date(2029, 1, 1)))
    wide, narrow = (
        report.difference_figure(d, compact=c).to_dict()["layout"] for c in (False, True)
    )
    assert wide["xaxis2"]["domain"][0] > wide["xaxis"]["domain"][1]  # side by side
    assert narrow["yaxis2"]["domain"][1] < narrow["yaxis"]["domain"][0]  # one above the other
    assert narrow["yaxis2"]["matches"] == "y"
    # the one age axis with its years, compact its title once below both plots
    assert wide["xaxis"]["title"]["text"] == wide["xaxis2"]["title"]["text"] == "Age and year"
    assert "<br>20" in wide["xaxis"]["ticktext"][0]
    assert "text" not in narrow["xaxis"].get("title", {})
    assert narrow["xaxis2"]["title"]["text"] == "Age and year"
    # the selectors name A and B: a long name does not fit the title or a pinned first column
    assert narrow["title"]["text"] == "B less A, path by path"
    rows = [next(iter(row.values())) for row in report.difference_table(d, compact=True)]
    assert rows[-2:] == ["Broke by then, only A", "Broke by then, only B"]
