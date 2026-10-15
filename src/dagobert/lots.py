"""The lots of a depot or wallet from its trades: a sale takes the oldest units of the security
first (FIFO, §20 Abs. 4 S. 7 EStG; the BMF allows it for crypto, for gold it is an assumption), a
Vorabpauschale raises the basis of the lots it was charged on. Also the money-weighted return of
the trades."""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from dagobert.model.assets import Trade

EPSILON = 1e-6  # units left over by float arithmetic
Flow = tuple[date, float]  # the investor's view: buys negative, sales and the end value positive


class TradeKind(StrEnum):
    BUY = "buy"
    SELL = "sell"
    VORABPAUSCHALE = "vorabpauschale"


@dataclass(frozen=True)
class Lot:
    """Units of one purchase still held. `price` is per unit with fees, `vp` the Vorabpauschale
    per unit charged so far."""

    security: str
    name: str
    bought: date
    units: float
    price: float
    vp: float = 0.0

    @property
    def cost(self) -> float:
        return self.units * self.price

    @property
    def basis(self) -> float:
        """What a sale deducts from its proceeds: the cost and the Vorabpauschale taxed so far."""
        return self.units * (self.price + self.vp)


@dataclass(frozen=True)
class Sale:
    date: date
    security: str
    name: str
    units: float
    proceeds: float  # after fees
    taken: tuple[Lot, ...]  # the units it took of each lot, oldest first


@dataclass
class Book:
    """Open lots by security, oldest first, and the sales so far."""

    lots: defaultdict[str, deque[Lot]] = field(default_factory=lambda: defaultdict(deque))
    sales: list[Sale] = field(default_factory=list)

    @property
    def open(self) -> list[Lot]:
        return [lot for held in self.lots.values() for lot in held]


def names(trades: Iterable[Trade]) -> dict[str, str]:
    """The last name given per security. A security without one goes by its ISIN or symbol."""
    return {t.security: t.name for t in sorted(trades, key=lambda t: t.date) if t.name}


def book(trades: Iterable[Trade]) -> Book:
    """Replay the trades in date order; trades of one day keep their order."""
    ordered = sorted(trades, key=lambda t: t.date)
    label = names(ordered)
    out = Book()
    for t in ordered:
        held, name = out.lots[t.security], label.get(t.security, t.security)
        match t.kind:
            case TradeKind.BUY:
                units = _units(t)
                held.append(Lot(t.security, name, t.date, units, (t.amount + t.fees) / units))
            case TradeKind.SELL:
                taken = _take(held, t)
                out.sales.append(
                    Sale(t.date, t.security, name, _units(t), t.amount - t.fees, taken)
                )
            case TradeKind.VORABPAUSCHALE:
                out.lots[t.security] = _charge(held, t)
    return out


def _units(t: Trade) -> float:
    if t.units is None:
        msg = f"{t.kind} of {t.security} on {t.date}: needs units"
        raise ValueError(msg)
    return t.units


def _take(held: deque[Lot], t: Trade) -> tuple[Lot, ...]:
    """Remove the units of a sale from the oldest lots. Returns the units taken of each."""
    left, taken = _units(t), list[Lot]()
    while left > EPSILON:
        if not held:
            msg = f"sale of {t.security} on {t.date}: {left:g} units more than held"
            raise ValueError(msg)
        take = min(left, held[0].units)
        taken.append(replace(held[0], units=take))
        left -= take
        if held[0].units - take > EPSILON:
            held[0] = replace(held[0], units=held[0].units - take)
        else:
            held.popleft()
    return tuple(taken)


def _charge(held: deque[Lot], t: Trade) -> deque[Lot]:
    """Spread a Vorabpauschale, booked in January for the year before, over the units held
    then. A lot bought in that year bears one twelfth less per full month before its purchase
    (§18 Abs. 2 InvStG)."""
    year = t.date.year - 1
    shares = [_held_share(lot.bought, year) for lot in held]
    weight = sum(lot.units * s for lot, s in zip(held, shares, strict=True))
    if weight <= 0:
        msg = f"Vorabpauschale of {t.security} on {t.date}: no units held in {year}"
        raise ValueError(msg)
    return deque(
        replace(lot, vp=lot.vp + t.amount * s / weight) for lot, s in zip(held, shares, strict=True)
    )


def _held_share(bought: date, year: int) -> float:
    if bought.year < year:
        return 1.0
    return (13 - bought.month) / 12 if bought.year == year else 0.0


def flows(trades: Iterable[Trade]) -> list[Flow]:
    """The cash flows of the investor. A Vorabpauschale is tax, paid outside the depot."""
    return [
        (t.date, -(t.amount + t.fees) if t.kind == TradeKind.BUY else t.amount - t.fees)
        for t in trades
        if t.kind != TradeKind.VORABPAUSCHALE
    ]


def irr(cash: Sequence[Flow]) -> float | None:
    """The yearly rate at which the flows sum to zero (actual/365), by bisection. None when
    the flows do not change sign or the rate lies outside -99% to +1000%."""
    start = min(day for day, _ in cash)

    def npv(rate: float) -> float:
        return sum(v / math.pow(1 + rate, (day - start).days / 365) for day, v in cash)

    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(mid) * npv(lo) > 0 else (lo, mid)
    return (lo + hi) / 2
