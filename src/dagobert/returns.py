"""Monthly return path providers: fixed, Monte Carlo, and historical rolling cycles."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING, Literal, Protocol, overload

import numpy as np
from numpy.typing import NDArray

from dagobert import series
from dagobert.model.assets import LotAsset
from dagobert.model.assumptions import Assumptions, Distribution, ReturnClass
from dagobert.model.plan import Plan
from dagobert.result import FloatArray

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence
    from datetime import date
    from pathlib import Path

    from dagobert.series import MonthlySeries


@dataclass(frozen=True)
class Returns:
    rates: dict[str, FloatArray]  # asset class -> monthly simple returns, shape (paths, months)
    inflation: FloatArray  # monthly inflation rates, shape (paths, months)
    indices: dict[str, FloatArray] = field(default_factory=dict)  # name -> level (paths, months)


# The lowest yearly inflation of a draw: a normal draw has no lower bound, and no year of the
# consumer prices since 1962 (`series.cpi`) fell by more than 0.2%
INFLATION_FLOOR = -0.02


def generator(seed: int, purpose: str) -> np.random.Generator:
    """The random numbers of one purpose, named by its path in the assumptions (`returns.equity`,
    `indices.salary`) or in the engine (`care`, `sale.<asset>`). Two runs with the same seed
    draw the same numbers for a purpose, whatever else they draw: their paths pair up."""
    return np.random.default_rng([seed, *purpose.encode()])


def years_of(first_month: int, months: int) -> NDArray[np.int_]:
    """The calendar year of each month from the start, 0 in the year of the start, whose
    calendar month is `first_month`."""
    return (first_month - 1 + np.arange(months)) // 12


def index_levels(
    a: Assumptions, months: int, paths: int, seed: int | None
) -> dict[str, FloatArray]:
    """Level of each named index per month, stepped every January.

    Cumulative indices start at 1.0 in the start year and compound the yearly growth.
    Non-cumulative indices are the clipped draw itself. Without `seed` (fixed and
    historical modes) every year uses the mean."""
    year_of_month = years_of(a.start.month, months)
    n_years = int(year_of_month.max()) + 1
    levels = {}
    for name, spec in a.indices.items():
        if seed is not None and spec.stdev:
            draw = generator(seed, f"indices.{name}").normal(
                spec.mean, spec.stdev, size=(paths, n_years)
            )
        else:
            draw = np.full((paths, n_years), spec.mean)
        draw = np.clip(draw, spec.floor, spec.cap)
        if spec.cumulative:
            draw[:, 0] = 0.0
            draw = np.cumprod(1 + draw, axis=1)
        levels[name] = draw[:, year_of_month]
    return levels


class ReturnProvider(Protocol):
    @property
    def name(self) -> str: ...

    def sample(self, months: int) -> Returns: ...


@overload
def monthly_rate(annual_mean: float) -> float: ...
@overload
def monthly_rate(annual_mean: FloatArray) -> FloatArray: ...
def monthly_rate(annual_mean: float | FloatArray) -> float | FloatArray:
    """The monthly rate that compounds to `annual_mean` in a year."""
    return (1 + annual_mean) ** (1 / 12) - 1


def grown[T: (float, FloatArray)](value: T, rate: T | float, cost: float) -> T:
    """`value` after a month that earns `rate` and costs the yearly share `cost`."""
    return value * (1 + rate) * (1 - cost / 12)


def median_growth(d: Distribution) -> float:
    """The growth per year of the median path of the lognormal draw: a spread pulls it below
    the mean, `fixed` compounds the mean."""
    return (1 + d.mean) / math.sqrt(1 + d.stdev**2 / (1 + d.mean) ** 2) - 1


def _lognormal(
    cls: str, d: ReturnClass, equity: FloatArray, seed: int, *, tied: bool = True
) -> FloatArray:
    """Lognormal monthly returns of a class, one per path and month of `equity`, the standard
    normal shocks of equity. The class draws its own shocks e from `returns.<cls>` and mixes them
    with those of equity, rho * z + sqrt(1 - rho**2) * e for rho = `equity_correlation`, which
    keeps their spread at 1. Without a correlation, or not `tied` (equity without spread has no
    shock to tie to), its draw is e alone, bit for bit, so runs pair up whatever the other
    classes draw. A class without spread keeps its mean and draws nothing.

    `d.mean`/`d.stdev` are the annual arithmetic mean/stdev of the simple return. Converted to
    the lognormal's underlying annual mu/sigma, then to i.i.d. monthly log-return parameters
    (mu/12, sigma/sqrt(12)) so the compounded annual return matches both moments exactly."""
    if d.stdev == 0:
        return np.full(equity.shape, monthly_rate(d.mean))
    rho = d.equity_correlation if tied else 0.0
    own = (
        equity
        if cls == "equity"
        else generator(seed, f"returns.{cls}").standard_normal(equity.shape)
    )
    shocks = rho * equity + np.sqrt(1 - rho**2) * own if rho else own
    sigma_y2 = np.log(1 + d.stdev**2 / (1 + d.mean) ** 2)
    mu_y = np.log(1 + d.mean) - sigma_y2 / 2
    draws: FloatArray = mu_y / 12 + np.sqrt(sigma_y2 / 12) * shocks
    return np.exp(draws) - 1


@dataclass(frozen=True)
class FixedProvider:
    assumptions: Assumptions
    name: str = "fixed"

    def sample(self, months: int) -> Returns:
        rates = {
            cls: np.full((1, months), monthly_rate(d.mean))
            for cls, d in self.assumptions.returns.items()
        }
        inflation = np.full((1, months), monthly_rate(self.assumptions.inflation.mean))
        indices = index_levels(self.assumptions, months, 1, None)
        return Returns(rates=rates, inflation=inflation, indices=indices)


@dataclass(frozen=True)
class MonteCarloProvider:
    assumptions: Assumptions
    paths: int = 5000
    seed: int = 42
    name: str = "montecarlo"

    def sample(self, months: int) -> Returns:
        equity = generator(self.seed, "returns.equity").standard_normal((self.paths, months))
        rates = {
            cls: _lognormal(cls, d, equity, self.seed)
            for cls, d in self.assumptions.returns.items()
        }
        inflation = self._sample_inflation(generator(self.seed, "inflation"), months)
        indices = index_levels(self.assumptions, months, self.paths, self.seed)
        return Returns(rates=rates, inflation=inflation, indices=indices)

    def _sample_inflation(self, rng: np.random.Generator, months: int) -> FloatArray:
        """One normal draw per calendar year, stepped each January like `index_levels`,
        clipped at `INFLATION_FLOOR`."""
        d = self.assumptions.inflation
        year_of_month = years_of(self.assumptions.start.month, months)
        n_years = int(year_of_month.max()) + 1
        annual: FloatArray = rng.normal(d.mean, d.stdev, size=(self.paths, n_years))
        return monthly_rate(np.clip(annual, INFLATION_FLOOR, None))[:, year_of_month]


def _align(*series: MonthlySeries) -> tuple[list[date], list[FloatArray]]:
    common = sorted(set(series[0].months).intersection(*(s.months for s in series[1:])))
    for prev, cur in pairwise(common):
        if (cur.year - prev.year) * 12 + (cur.month - prev.month) != 1:
            msg = f"historical series: gap between {prev:%Y-%m} and {cur:%Y-%m} in aligned months"
            raise ValueError(msg)
    aligned = []
    for s in series:
        pos = {m: i for i, m in enumerate(s.months)}
        aligned.append(np.array([s.values[pos[m]] for m in common], dtype=np.float64))
    return common, aligned


@dataclass(frozen=True)
class HistoricalProvider:
    """One path per possible start month. Monthly returns wrap around to the series start
    when the horizon runs past the end of the aligned series.

    Equity, the consumer prices, the bond yields and the price series of `replayed` (class to
    series) align month by month. A class of `drawn` that no series replays draws as in Monte
    Carlo, with the log return of the replayed equity month, standardized over the whole series,
    as the equity shock; a series without spread gives none, so the class draws its own alone.
    Every other class keeps its mean."""

    assumptions: Assumptions
    equity_series: MonthlySeries
    cpi_series: MonthlySeries
    bond_series: MonthlySeries
    replayed: dict[str, MonthlySeries] = field(default_factory=dict)
    drawn: frozenset[str] = frozenset()
    seed: int = 42
    name: str = "historical"

    def sample(self, months: int) -> Returns:
        common, (equity, cpi, bond, *prices) = _align(
            self.equity_series, self.cpi_series, self.bond_series, *self.replayed.values()
        )
        n = len(common)
        if n < 2:
            msg = "historical provider: fewer than 2 months in the aligned series"
            raise ValueError(msg)
        idx = (np.arange(n - 1)[:, None] + np.arange(months)[None, :]) % (n - 1)
        growth = equity[1:] / equity[:-1]
        inflation = (cpi[1:] / cpi[:-1] - 1)[idx]
        rates = {
            "equity": (growth - 1)[idx],
            "fixed_income": monthly_rate(bond[1:][idx] / 100),
            **{
                cls: (p[1:] / p[:-1] - 1)[idx] for cls, p in zip(self.replayed, prices, strict=True)
            },
        }
        log = np.log(growth)
        spread = log.std()
        shocks = ((log - log.mean()) / (spread or 1.0))[idx]
        for cls, d in self.assumptions.returns.items():
            if cls not in rates:
                rates[cls] = (
                    _lognormal(cls, d, shocks, self.seed, tied=bool(spread))
                    if cls in self.drawn
                    else np.full((n - 1, months), monthly_rate(d.mean))
                )
        indices = index_levels(self.assumptions, months, n - 1, None)
        return Returns(rates=rates, inflation=inflation, indices=indices)


REPLAYED = ("gold",)  # the classes that `historical` replays from the series of their name


def historical_replays(held: Iterable[str]) -> frozenset[str]:
    """The classes whose series `historical` replays, so their means do nothing there: equity,
    fixed income and those of `REPLAYED` among the classes of the gold and crypto assets,
    `held`."""
    return frozenset({"equity", "fixed_income"} | (set(REPLAYED) & set(held)))


def historical_draws(held: Iterable[str]) -> frozenset[str]:
    """The classes of the gold and crypto assets, `held`, that `historical` draws as
    `montecarlo` does, with their spread and correlation: no series replays them."""
    return frozenset(held) - historical_replays(held)


def make_provider(
    name: Literal["fixed", "montecarlo", "historical"],
    plan: Plan,
    data_dir: Path,
    *,
    paths: int = 5000,
    seed: int = 42,
) -> ReturnProvider:
    """`historical` replays the series of `data_dir` (`series`) and raises
    `series.MissingSeriesError` without the equity series. The classes of the gold and crypto
    assets replay their series (`REPLAYED`), which then joins the window, or draw, such as
    `bitcoin`: its prices start in 2010 and hold a growth by a factor of about 10,000 up to 2013,
    no sample of the future."""
    a = plan.assumptions
    if name == "fixed":
        return FixedProvider(a)
    if name == "montecarlo":
        return MonteCarloProvider(a, paths=paths, seed=seed)
    if name == "historical":
        equity, bond = (_needed(s, data_dir) for s in (series.EQUITY, "umlaufsrendite"))
        held = frozenset(asset.growth for asset in plan.assets if isinstance(asset, LotAsset))
        return HistoricalProvider(
            a,
            equity,
            series.cpi(data_dir),
            bond,
            {cls: _needed(cls, data_dir) for cls in REPLAYED if cls in held},
            historical_draws(held),
            seed,
        )
    msg = f"unknown return provider {name!r}"
    raise ValueError(msg)


def _needed(name: str, data_dir: Path) -> MonthlySeries:
    if (found := series.load(name, data_dir)) is None:
        msg = (
            f"The historical model needs the series {name}. Run `dagobert series fetch {name}` or "
            f"`dagobert series import {name} FILE`."
        )
        raise series.MissingSeriesError(msg)
    return found


def deflate(
    values: Sequence[tuple[date, float]], cpi: Callable[[date], float], to: date
) -> list[tuple[date, float]]:
    """Dated amounts in euros of `to`, each by the consumer prices of its month."""
    end = cpi(to)
    return [(day, v * end / cpi(day)) for day, v in values]
