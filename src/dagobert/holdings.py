"""Gold and crypto in the engine: one pool per asset, as a holder keeps a depot or a wallet. A
pool counts its units by purchase month, so a sale knows which gains are private sales (§23
EStG), and keeps the units that are capital income (§20 EStG) apart."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import numpy as np

from dagobert.model.assets import CryptoAsset, GoldAsset
from dagobert.model.months import months_between

if TYPE_CHECKING:
    from dagobert.lots import Lot
    from dagobert.result import FloatArray


@dataclass(frozen=True)
class Taken:
    """What a sale took from a pool, nominal and after the costs of the sale: the proceeds, the
    gain of the units bought within the holding period, and the proceeds and the basis of the
    §20 part."""

    proceeds: FloatArray
    private_gain: FloatArray
    capital_proceeds: FloatArray
    capital_basis: FloatArray


@dataclass
class Pool:
    """One gold or crypto asset. A unit is worth one euro at the start, and `price` follows the
    return class of the asset less its custody `cost`. `young` holds the units bought in each of
    the last months of the holding period, a ring by month index (`young_cost` their nominal
    cost); a row becomes free and moves into `aged` once the period has passed. `capital` holds
    the units under §20 with their nominal `capital_basis`. Each row is one value per path."""

    spec: GoldAsset | CryptoAsset
    capital_from: date | None  # a purchase in or after this month falls under §20
    price: FloatArray
    aged: FloatArray
    young: FloatArray  # (holding period in months + 1, paths)
    young_cost: FloatArray
    capital: FloatArray
    capital_basis: FloatArray

    @classmethod
    def opening(
        cls,
        spec: GoldAsset | CryptoAsset,
        start: date,
        paths: int,
        holding: int,
        crypto_capital_from: date | None,
    ) -> Pool:
        """The pool at `start`: `value` spread over the open lots (`_worth`). A lot bought within
        `holding` months before the start month, or in it, goes into the row of its month, an
        older one into `aged`, one under §20 into `capital`. A lot dated after the start counts
        in the start month. Without open lots the whole value counts as held for longer."""
        capital_from = (
            date.min
            if spec.tax == "capital"
            else crypto_capital_from
            if isinstance(spec, CryptoAsset)
            else None
        )
        rows, lots = holding + 1, spec.book.open
        young, young_cost = np.zeros(rows), np.zeros(rows)
        aged, capital, basis = 0.0 if lots else spec.value, 0.0, 0.0
        for lot, worth in zip(lots, _worth(lots, spec.value), strict=True):
            month = min(months_between(start, lot.bought), 0)
            if capital_from is not None and lot.bought >= capital_from:
                capital, basis = capital + worth, basis + lot.basis
            elif month < -holding:
                aged += worth
            else:
                young[month % rows] += worth
                young_cost[month % rows] += lot.basis
        ones = np.ones(paths)
        return cls(
            spec,
            capital_from,
            ones.copy(),
            ones * aged,
            young[:, None] * ones,
            young_cost[:, None] * ones,
            ones * capital,
            ones * basis,
        )

    @property
    def units(self) -> FloatArray:
        return self.aged + self.young.sum(axis=0) + self.capital

    @property
    def value(self) -> FloatArray:
        return self.units * self.price

    @property
    def latent(self) -> FloatArray:
        """The gain of the §20 part. The young rows count none: they become free within the
        holding period, and a sale takes the aged units first."""
        return np.maximum(self.capital * self.price - self.capital_basis, 0.0)

    @property
    def gain_share(self) -> FloatArray:
        """The share of gain in the value of the §20 part, 0 for a loss."""
        value = self.capital * self.price
        return np.maximum(_share(value - self.capital_basis, value), 0.0)

    def age(self, i: int) -> None:
        """Month `i` starts: the row of the month a holding period ago becomes free, and the
        row takes the purchases of month `i`."""
        row = i % len(self.young)
        self.aged += self.young[row]
        self.young[row] = 0.0
        self.young_cost[row] = 0.0

    def buy(self, amount: FloatArray | float, i: int, month: date) -> None:
        """Nominal euros into the pool at the price of month `i`, per path or one for all."""
        units = amount / self.price
        if self.capital_from is not None and month >= self.capital_from:
            self.capital += units
            self.capital_basis += amount
        else:
            self.young[i % len(self.young)] += units
            self.young_cost[i % len(self.young)] += amount

    def take(self, units: FloatArray, i: int, costs: float = 0.0) -> Taken:
        """Sell `units` per path in month `i`, the oldest first: `aged`, the rows from the
        oldest month, then the §20 part. `costs` is the share of the proceeds that the sale
        costs. Only the paths that sell take part: a deficit reaches few of them."""
        n, on = len(self.young), np.flatnonzero(units)
        rows = np.ix_((i + 1 + np.arange(n)) % n, on)
        young = self.young[rows]
        layers = np.vstack([self.aged[on], young, self.capital[on]])
        taken = np.clip(units[on] - (np.cumsum(layers, axis=0) - layers), 0.0, layers)
        cost = self.young_cost[rows] * _share(taken[1:-1], young)
        basis = self.capital_basis[on] * _share(taken[-1], self.capital[on])
        self.aged[on] -= taken[0]
        self.young[rows] -= taken[1:-1]
        self.young_cost[rows] -= cost
        self.capital[on] -= taken[-1]
        self.capital_basis[on] -= basis
        net = self.price[on] * (1 - costs)
        out = np.zeros((4, len(units)))
        out[:, on] = (
            taken.sum(axis=0) * net,
            taken[1:-1].sum(axis=0) * net - cost.sum(axis=0),
            taken[-1] * net,
            basis,
        )
        return Taken(*out)


def _share(part: FloatArray, whole: FloatArray) -> FloatArray:
    """`part / whole`, 0 where `whole` is 0."""
    return np.divide(part, whole, out=np.zeros_like(part), where=whole > 0)


def _worth(lots: list[Lot], value: float) -> list[float]:
    """`value` spread over `lots`: by units within a security, which has one price, and by cost
    across securities, since the engine reads no price files."""
    cost: defaultdict[str, float] = defaultdict(float)
    units: defaultdict[str, float] = defaultdict(float)
    for lot in lots:
        cost[lot.security] += lot.basis
        units[lot.security] += lot.units
    total = sum(cost.values())
    return [
        value
        * (cost[lot.security] / total if total else 1 / len(cost))
        * lot.units
        / units[lot.security]
        for lot in lots
    ]
