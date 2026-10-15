"""The return providers: fixed, Monte Carlo and historical rates and the index levels."""

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from builders import PHASES, plan
from dateutil.relativedelta import relativedelta

from dagobert import series
from dagobert.model.assets import CryptoAsset, GoldAsset, LotAsset
from dagobert.model.assumptions import Assumptions, Index, Person, ReturnClass
from dagobert.model.months import add_months, months_between
from dagobert.returns import (
    FixedProvider,
    HistoricalProvider,
    MonteCarloProvider,
    Returns,
    make_provider,
    median_growth,
)
from dagobert.series import MissingSeriesError, MonthlySeries

PERSON = Person(born=date(1985, 1, 1))


def _assumptions(**returns: ReturnClass) -> Assumptions:
    return Assumptions(person=PERSON, start=date(2026, 1, 1), phases=PHASES, returns=returns)


def _standard_returns() -> dict[str, ReturnClass]:
    return {
        "equity": ReturnClass(mean=0.08, stdev=0.18),
        "fixed_income": ReturnClass(mean=0.03),
        "cash": ReturnClass(mean=0.02),
        "property": ReturnClass(mean=0.03),
    }


def test_fixed_provider_compounds_to_annual_mean() -> None:
    a = _assumptions(**_standard_returns())
    r = FixedProvider(a).sample(12)
    for cls, dist in a.returns.items():
        assert np.prod(1 + r.rates[cls][0]) == pytest.approx(1 + dist.mean, abs=1e-9)
    assert np.prod(1 + r.inflation[0]) == pytest.approx(1 + a.inflation.mean, abs=1e-9)
    assert r.inflation.shape == (1, 12)


def test_index_levels_step_each_january() -> None:
    a = Assumptions(
        person=PERSON,
        phases=PHASES,
        start=date(2026, 10, 1),
        returns=_standard_returns(),
        indices={"salary": Index(mean=0.05, stdev=0.0)},
    )
    r = FixedProvider(a).sample(15)
    levels = r.indices["salary"][0]
    assert levels[:3].tolist() == [1.0, 1.0, 1.0]  # Oct-Dec 2026
    assert levels[3] == pytest.approx(1.05)  # Jan 2027
    assert levels[14] == pytest.approx(1.05)  # Dec 2027


def test_index_floor_clips_draws() -> None:
    a = Assumptions(
        person=PERSON,
        phases=PHASES,
        start=date(2026, 1, 1),
        returns=_standard_returns(),
        indices={"salary": Index(mean=0.0, stdev=0.5, floor=0.0)},
    )
    r = MonteCarloProvider(a, paths=200, seed=3).sample(24)
    assert np.all(r.indices["salary"] >= 1.0)
    assert np.any(r.indices["salary"][:, 12] > 1.0)


def test_non_cumulative_index_is_clipped_draw() -> None:
    a = Assumptions(
        person=PERSON,
        phases=PHASES,
        start=date(2026, 1, 1),
        returns=_standard_returns(),
        indices={"bonus": Index(mean=0.9, stdev=0.5, floor=0.0, cap=1.0, cumulative=False)},
    )
    r = MonteCarloProvider(a, paths=300, seed=5).sample(24)
    levels = r.indices["bonus"]
    assert np.all((levels >= 0.0) & (levels <= 1.0))
    assert np.any(levels[:, 0] == 1.0) and np.any(levels[:, 0] == 0.0)
    assert np.all(levels[:, 0] == levels[:, 11])
    assert FixedProvider(a).sample(3).indices["bonus"][0].tolist() == [0.9, 0.9, 0.9]


def test_montecarlo_keeps_the_mean_and_the_spread_of_the_assumption() -> None:
    """The mean and the stdev are of the annual simple return: both moments survive the
    lognormal monthly draw and the compounding over 12 months. A class without spread keeps
    its mean."""
    a = _assumptions(**_standard_returns())
    r = MonteCarloProvider(a, paths=20000, seed=1).sample(12)
    annual = np.prod(1 + r.rates["equity"], axis=1) - 1
    assert annual.mean() == pytest.approx(0.08, abs=0.005)
    assert annual.std() == pytest.approx(0.18, abs=0.01)
    assert r.rates["cash"].shape == (20000, 12)
    assert np.all(r.rates["cash"] == r.rates["cash"][0, 0])


def test_inflation_steps_align_with_index_levels() -> None:
    a = Assumptions(
        person=PERSON,
        phases=PHASES,
        start=date(2026, 10, 1),
        returns=_standard_returns(),
        indices={"salary": Index(mean=0.05, stdev=0.0)},
    )
    r = MonteCarloProvider(a, paths=5, seed=11).sample(15)
    # both "years" run Oct-Dec 2026 then Jan-Dec 2027: inflation is constant within each block.
    assert np.all(r.inflation[:, :3] == r.inflation[:, :1])
    assert np.all(r.inflation[:, 3:15] == r.inflation[:, 3:4])
    assert np.any(r.inflation[:, 3] != r.inflation[:, 2])


def _drawn(salary: float, fixed_income: float) -> Returns:
    a = Assumptions(
        person=PERSON,
        phases=PHASES,
        start=date(2026, 1, 1),
        returns=_standard_returns()
        | {
            "fixed_income": ReturnClass(mean=0.03, stdev=fixed_income),
            "property": ReturnClass(mean=0.03, stdev=0.05),
        },
        indices={
            "salary": Index(mean=0.03, stdev=salary),
            "insurance": Index(mean=0.03, stdev=0.02),
        },
    )
    return MonteCarloProvider(a, paths=50, seed=1).sample(24)


@pytest.mark.parametrize(("salary", "fixed_income"), [(0.0, 0.02), (0.03, 0.0)])
def test_a_spread_of_zero_keeps_the_draws_of_the_others(salary: float, fixed_income: float) -> None:
    """A distribution without spread draws nothing. The draws of the others stay, so two
    scenarios pair up path by path."""
    base, changed = _drawn(0.03, 0.02), _drawn(salary, fixed_income)
    assert np.array_equal(base.indices["insurance"], changed.indices["insurance"])
    assert np.array_equal(base.rates["property"], changed.rates["property"])
    assert np.array_equal(base.inflation, changed.inflation)


def test_montecarlo_seed_reproducible() -> None:
    a = _assumptions(**_standard_returns())
    r1 = MonteCarloProvider(a, paths=100, seed=7).sample(24)
    r2 = MonteCarloProvider(a, paths=100, seed=7).sample(24)
    assert np.array_equal(r1.rates["equity"], r2.rates["equity"])
    assert np.array_equal(r1.inflation, r2.inflation)


def _tie(rates: dict[str, np.ndarray], cls: str) -> float:
    """The correlation of the monthly log returns of a class with those of equity."""
    return float(np.corrcoef(np.log1p(rates[cls]).ravel(), np.log1p(rates["equity"]).ravel())[0, 1])


def _bitcoin_draws(rho: float, equity: float = 0.18) -> dict[str, np.ndarray]:
    returns = _standard_returns() | {
        "equity": ReturnClass(mean=0.08, stdev=equity),
        "property": ReturnClass(mean=0.03, stdev=0.05),
        "bitcoin": ReturnClass(mean=0.3, stdev=0.85, equity_correlation=rho),
    }
    return MonteCarloProvider(_assumptions(**returns), paths=50, seed=1).sample(24).rates


def test_a_correlation_changes_the_draw_of_its_class_only() -> None:
    """Equity and the other classes draw as without it, so the paths of two runs pair up.
    Without a correlation a class draws apart from equity, whatever the spread of equity."""
    free, tied = _bitcoin_draws(0.0), _bitcoin_draws(0.5)
    assert all(np.array_equal(free[c], tied[c]) for c in ("equity", "property", "cash"))
    assert not np.array_equal(free["bitcoin"], tied["bitcoin"])
    assert np.array_equal(_bitcoin_draws(0.0, equity=0.0)["bitcoin"], free["bitcoin"])


@pytest.mark.parametrize("rho", [-0.4, 0.0, 0.5])
def test_a_correlated_class_keeps_its_moments(rho: float) -> None:
    gold = ReturnClass(mean=0.1, stdev=0.3, equity_correlation=rho)
    r = MonteCarloProvider(_assumptions(**_standard_returns(), gold=gold), paths=20000, seed=2)
    rates = r.sample(12).rates
    annual = np.prod(1 + rates["gold"], axis=1) - 1
    assert annual.mean() == pytest.approx(0.1, abs=0.01)
    assert annual.std() == pytest.approx(0.3, abs=0.01)
    assert _tie(rates, "gold") == pytest.approx(rho, abs=0.01)


@pytest.mark.parametrize(
    ("mean", "spread", "median"),
    [(0.15, 0.8, -0.056), (0.15, 0.6, 0.020), (0.3, 0.85, 0.088), (0.06, 0.16, 0.048)],
)
def test_a_spread_pulls_the_median_path_below_the_mean(
    mean: float, spread: float, median: float
) -> None:
    """The growth per year of the median path over 40 years, which the explorer shows."""
    bitcoin = ReturnClass(mean=mean, stdev=spread)
    assert median_growth(bitcoin) == pytest.approx(median, abs=5e-4)
    a = _assumptions(**_standard_returns(), bitcoin=bitcoin)
    rates = MonteCarloProvider(a, paths=4000, seed=1).sample(480).rates["bitcoin"]
    assert np.median(np.prod(1 + rates, axis=1)) ** (1 / 40) - 1 == pytest.approx(median, abs=0.005)


def _monthly_series(start: date, values: np.ndarray) -> MonthlySeries:
    months = [start + relativedelta(months=i) for i in range(len(values))]
    return MonthlySeries(months=months, values=values)


def test_historical_wraparound() -> None:
    n = 24
    equity = _monthly_series(date(2000, 1, 1), np.linspace(100.0, 200.0, n))
    cpi = _monthly_series(date(2000, 1, 1), np.linspace(100.0, 110.0, n))
    bond = _monthly_series(date(2000, 1, 1), np.full(n, 3.0))
    a = _assumptions(
        equity=ReturnClass(mean=0.05),
        fixed_income=ReturnClass(mean=0.02),
        cash=ReturnClass(mean=0.01),
        property=ReturnClass(mean=0.03),
    )
    provider = HistoricalProvider(a, equity, cpi, bond)
    r = provider.sample(12)

    assert r.rates["equity"].shape == r.inflation.shape == (n - 1, 12)
    # a path per start month: the first starts with the first monthly return
    assert r.rates["equity"][0, 0] == pytest.approx(equity.values[1] / equity.values[0] - 1)

    # start = last return: the second step wraps around to the first monthly return
    wrapped = r.rates["equity"][n - 2, 1]
    expected = equity.values[1] / equity.values[0] - 1
    assert wrapped == pytest.approx(expected)

    # property has no series: the mean of its assumption in every month
    monthly_property = (1.03) ** (1 / 12) - 1
    assert r.rates["property"] == pytest.approx(monthly_property)

    # a constant yield of 3% a year, compounded monthly
    monthly_bond = (1.03) ** (1 / 12) - 1
    assert r.rates["fixed_income"] == pytest.approx(monthly_bond)


def test_historical_refuses_a_gap_in_the_aligned_months() -> None:
    full = _monthly_series(date(2000, 1, 1), np.arange(1.0, 6.0))
    gap = MonthlySeries(
        months=[date(2000, 1, 1), date(2000, 2, 1), date(2000, 4, 1)], values=np.arange(1.0, 4.0)
    )
    provider = HistoricalProvider(_assumptions(**_standard_returns()), full, full, gap)
    with pytest.raises(ValueError, match="gap"):
        provider.sample(12)


def test_historical_needs_the_equity_series_of_the_data_directory(tmp_path: Path) -> None:
    """No fallback: without the equity series the model is off. With it, the consumer prices
    and the bond yields come from the shipped series."""
    p = plan([], [], returns=_standard_returns())
    assert isinstance(make_provider("montecarlo", p, tmp_path, paths=2), MonteCarloProvider)
    with pytest.raises(MissingSeriesError, match="series msci-world"):
        make_provider("historical", p, tmp_path)
    series.save(series.SERIES[series.EQUITY], tmp_path, [series.Point(date(2000, 1, 1), 100.0)])
    provider = make_provider("historical", p, tmp_path)
    assert isinstance(provider, HistoricalProvider)
    assert provider.equity_series.values.tolist() == [100.0]
    assert provider.cpi_series.months[0] == date(1962, 1, 1)


@pytest.fixture
def replay(tmp_path: Path) -> Path:
    """A data directory whose equity series runs from 1995 to 1999, across the start of the
    euro."""
    values = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0.005, 0.04, 60))
    points = [
        series.Point(add_months(date(1995, 1, 1), i), v) for i, v in enumerate(values.tolist())
    ]
    series.save(series.SERIES[series.EQUITY], tmp_path, points)
    return tmp_path


def _replayed(
    data: Path, returns: dict[str, ReturnClass], *assets: LotAsset, seed: int = 1
) -> Returns:
    p = plan([], list(assets), returns=returns)
    return make_provider("historical", p, data, seed=seed).sample(24)


def test_historical_replays_gold_in_euros_across_the_start_of_the_euro(replay: Path) -> None:
    """Dollars at the Deutsche Mark rate up to 1998-12, at the ECB rate from 1999-01. The
    window and the replay of equity stay as without gold. Without a gold asset the class keeps
    its mean, so its series does not join the window."""
    without = _replayed(replay, _standard_returns())
    returns = _standard_returns() | {"gold": ReturnClass(mean=0.05)}
    r = _replayed(replay, returns, GoldAsset(id="g", kind="gold", value=1000))
    assert np.unique(_replayed(replay, returns).rates["gold"]).size == 1
    assert np.array_equal(r.rates["equity"], without.rates["equity"])
    dec, jan = date(1998, 12, 1), date(1999, 1, 1)
    usd, dem, ecb = (
        {p.month: p.value for p in series.read(series.SERIES[name], replay)}
        for name in ("gold", "usd-dem", "usd-eur")
    )
    euros = usd[jan] / ecb[jan], usd[dec] * dem[dec] / series.DEM_PER_EUR
    path = months_between(date(1995, 1, 1), dec)  # the window starts with the equity series
    assert r.rates["gold"][path, 0] == pytest.approx(euros[0] / euros[1] - 1)


def test_historical_draws_the_class_of_a_crypto_asset_tied_to_the_replayed_equity(
    replay: Path,
) -> None:
    """Bitcoin prices start in 2010, no replay: the class draws with the standardized log
    return of the equity month as the equity shock. Without a crypto asset it keeps its mean."""
    returns = _standard_returns() | {
        "bitcoin": ReturnClass(mean=0.3, stdev=0.85, equity_correlation=0.9)
    }
    wallet = CryptoAsset(id="w", kind="crypto", value=1000)
    r = _replayed(replay, returns, wallet)
    assert np.array_equal(r.rates["equity"], _replayed(replay, _standard_returns()).rates["equity"])
    assert np.array_equal(r.rates["bitcoin"], _replayed(replay, returns, wallet).rates["bitcoin"])
    other = _replayed(replay, returns, wallet, seed=2)
    assert not np.array_equal(r.rates["bitcoin"], other.rates["bitcoin"])
    assert _tie(r.rates, "bitcoin") == pytest.approx(0.9, abs=0.05)
    assert np.unique(_replayed(replay, returns).rates["bitcoin"]).size == 1


def test_historical_draws_a_class_alone_when_equity_has_no_spread() -> None:
    """A flat window gives no equity shock to tie to: the class keeps its full spread, whatever
    its correlation."""
    flat = _monthly_series(date(2000, 1, 1), np.full(24, 100.0))

    def bitcoin(rho: float) -> np.ndarray:
        a = _assumptions(
            **_standard_returns(),
            bitcoin=ReturnClass(mean=0.3, stdev=0.85, equity_correlation=rho),
        )
        provider = HistoricalProvider(a, flat, flat, flat, drawn=frozenset({"bitcoin"}))
        return provider.sample(12).rates["bitcoin"]

    assert np.array_equal(bitcoin(0.9), bitcoin(0.0))
