"""What sets the broke paths apart: P(broke) per group of each random driver."""

from __future__ import annotations

from datetime import date
from functools import cache

import pytest
from builders import plan

from dagobert import anatomy, i18n, report
from dagobert.anatomy import Driver, Key
from dagobert.engine.simulation import simulate
from dagobert.model.assets import CryptoAsset, EquityAsset
from dagobert.model.assumptions import Distribution, Person, ReturnClass
from dagobert.model.streams import Stream
from dagobert.report.anatomy import READING, TIED, bin_label, reading
from dagobert.result import RunResult
from dagobert.returns import MonteCarloProvider

MONTHS = 121  # from 80 to 90


@cache
def _run(equity: float, paths: int = 1000, wallet: float = 0.0, spread: float = 0.6) -> RunResult:
    """A depot that lasts ten years of spending and care in most paths at 6% returns, and
    bitcoins worth `wallet` with the `spread`."""
    p = plan(
        [
            Stream(name="Leben", amount=-2000),
            Stream(name="PKV", amount=-500, index="insurance"),
            Stream(name="Beitrag", amount=-100, index="flat"),
        ],
        [
            EquityAsset(id="d", kind="equity", value=400_000, cost_basis=400_000),
            *([CryptoAsset(id="w", kind="crypto", value=wallet)] if wallet else []),
        ],
        person=Person(born=date(1946, 1, 1)),
        inflation=Distribution(mean=0.02, stdev=0.01),
        returns={
            "equity": ReturnClass(mean=equity, stdev=0.16),
            "bitcoin": ReturnClass(mean=0.1, stdev=spread, equity_correlation=0.4),
            **{name: ReturnClass(mean=0.0) for name in ("fixed_income", "cash", "property")},
        },
        indices={
            name: {"mean": 0.03, "stdev": stdev}
            for name, stdev in (("insurance", 0.02), ("flat", 0.0), ("unused", 0.02))
        },
        care={
            "hazard": [{"age": 80, "factor": 0.1}],
            "cost": 2000,
            "duration": {"mean": 24, "stdev": 12},
        },
        cash_buffer_months=1,
    )
    return simulate(
        p, MonteCarloProvider(p.assumptions, paths, seed=3).sample(MONTHS), "montecarlo"
    )


def _driver(r: RunResult, key: Key) -> Driver:
    found = anatomy.of(r)
    assert found is not None
    return next(d for d in found.drivers if d.key == key)


def test_poor_early_equity_returns_break_more_paths() -> None:
    low, high = (_driver(_run(mean), (anatomy.EARLY, "equity")).bins for mean in (0.03, 0.06))
    assert low[0].broke > high[0].broke
    assert high[0].broke > high[-1].broke


def test_care_by_90_breaks_more_paths() -> None:
    *cared, none = _driver(_run(0.06), (anatomy.CARE, "")).bins
    assert sum(b.broke * b.paths for b in cared) / sum(b.paths for b in cared) > none.broke


@pytest.mark.parametrize(
    ("wallet", "spread", "key", "shown"),
    [
        (0, 0.6, (anatomy.INDEX, "insurance"), True),
        (0, 0.6, (anatomy.INDEX, "flat"), False),
        (0, 0.6, (anatomy.INDEX, "unused"), False),
        (40_000, 0.6, (anatomy.RETURN, "bitcoin"), True),
        (40_000, 0.0, (anatomy.RETURN, "bitcoin"), False),
        (0, 0.6, (anatomy.RETURN, "bitcoin"), False),
    ],
    ids=[
        "an index that a stream follows",
        "an index without spread",
        "an index that nothing follows",
        "a crypto class held",
        "a crypto class without spread",
        "a crypto class held by nothing",
    ],
)
def test_a_driver_shows_when_the_plan_follows_its_spread(
    wallet: float, spread: float, key: Key, shown: bool
) -> None:
    """A growth index that a stream follows, the class of a crypto asset: each with a spread."""
    found = anatomy.of(_run(0.06, wallet=wallet, spread=spread))
    assert found is not None
    assert (key in {d.key for d in found.drivers}) is shown


def test_the_reading_names_the_pattern_of_equity_beside_a_class() -> None:
    """Bitcoin at a correlation of 0.4 looks almost as steep as equity: its panel needs the
    sentence."""
    held, without = anatomy.of(_run(0.06, wallet=40_000)), anatomy.of(_run(0.06))
    assert held is not None and without is not None
    assert reading(held) == (*reading(without), TIED)
    assert len(reading(without)) == len(READING)
    subtitle = report.anatomy_figure(held).to_dict()["layout"]["title"]["subtitle"]["text"]
    assert subtitle.endswith(TIED)


def test_the_words_follow_the_language_of_the_page() -> None:
    """The run holds no words (the app caches it for every session): its figure speaks the
    language of the page that draws it."""
    found = anatomy.of(_run(0.06))
    assert found is not None
    english = report.anatomy_figure(found).to_dict()["layout"]["annotations"][0]["text"]
    with i18n.use("de"):
        german = report.anatomy_figure(found).to_dict()["layout"]["annotations"][0]["text"]
    assert english.startswith("Equity return per year, first 10 years")
    assert german.startswith("Rendite Aktien pro Jahr, erste 10 Jahre")


@pytest.mark.parametrize(
    ("kind", "german"),
    [
        (anatomy.CARE, "ohne Pflege"),
        (anatomy.DISABLED, "erwerbsfähig"),
        (anatomy.INHERITANCE, "keine"),
    ],
)
def test_the_last_age_group_is_named_in_german_for_each_driver(kind: str, german: str) -> None:
    driver = Driver((kind, ""), 0.0, 0.0, ())
    last = anatomy.Bin(90, None, 1, 0.0)
    assert "none by" in bin_label(driver, last)
    with i18n.use("de"):
        assert bin_label(driver, last).startswith(german)


def test_a_single_path_has_nothing_to_show() -> None:
    assert anatomy.of(_run(0.06, paths=1)) is None


@pytest.mark.parametrize("compact", [False, True])
def test_figure_shows_the_share_broke_per_group(compact: bool) -> None:
    found = anatomy.of(_run(0.06))
    assert found is not None
    fig = report.anatomy_figure(found, compact=compact).to_dict()
    bars = [t for t in fig["data"] if t["type"] == "bar"]
    assert [list(t["y"]) for t in bars] == [[b.broke for b in d.bins] for d in found.drivers]
    columns = {tuple(v["domain"]) for k, v in fig["layout"].items() if k.startswith("xaxis")}
    assert len(columns) == (1 if compact else min(len(found.drivers), 3))  # a phone: one
    assert ("subtitle" in fig["layout"]["title"]) is not compact  # the page shows it below
