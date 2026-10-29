"""The value of a security over time on the securities tab of the Assets page: the units held at
each stored price against their cost, with the buys and sales (`report.tracker.position_figure`),
in euros of the last price date or nominal (rule `tracking`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

from dagobert import lots
from dagobert.i18n import _
from dagobert.lots import TradeKind
from dagobert.prices import price_history
from dagobert.report.tracker import Position, Traded, position_figure
from dagobert.result import unit
from dagobert.ui import chart, is_mobile, month_labels

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import date
    from pathlib import Path

    from dagobert.model.assets import HoldingsAsset, Trade


def position(
    data_dir: Path, trades: Sequence[Trade], security: str, cpi: Callable[[date], float] | None
) -> Position:
    """`security` from its first buy: the value of the units held at each stored price, their
    cost with fees on each day with a price or a trade, both in euros of the last price date by
    `cpi` (each lot at the prices of its purchase), nominal without it. After a sale of all units
    without a later buy, nothing."""
    own = [t for t in trades if t.security == security]
    moves = [t for t in own if t.kind != TradeKind.VORABPAUSCHALE]
    first, last = min(t.date for t in moves), max(t.date for t in moves)
    prices = {day: price for day, price in price_history(data_dir, security) if day >= first}
    days = sorted({*prices, *(t.date for t in moves)})
    held = dict(zip(days, lots.held(own, days), strict=True))
    if not held[days[-1]]:
        days = [day for day in days if day <= last]
    end = max((day for day in days if day in prices), default=days[-1])

    def real(day: date) -> float:
        return 1.0 if cpi is None else cpi(end) / cpi(day)

    costs = {day: sum(lot.cost * real(lot.bought) for lot in held[day]) for day in days}
    return Position(
        [
            (day, sum(lot.units for lot in held[day]) * prices[day] * real(day))
            for day in days
            if day in prices
        ],
        list(costs.items()),
        [
            Traded(t.date, t.kind == TradeKind.SELL, t.units or 0.0, t.amount, costs[t.date])
            for t in moves
        ],
    )


def position_chart(
    data_dir: Path,
    asset: HoldingsAsset,
    securities: dict[str, str],
    cpi: Callable[[date], float],
) -> None:
    """The chart of one of `securities` (name by ISIN or symbol, in the order of the table), with
    a switch to nominal euros."""
    st.subheader(_("Value over time"))
    pick, switch = st.columns([3, 1], vertical_alignment="bottom")
    security = pick.selectbox(
        _("Security"),
        list(securities),
        format_func=securities.__getitem__,
        key=f"securities-position-{asset.id}",
    )
    nominal = switch.toggle(_("Nominal euros"), key="securities-position-nominal")
    if security is None:
        return
    shown = position(data_dir, asset.trades, security, None if nominal else cpi)
    if not shown.values:
        st.caption(_("No stored price of this security: import its prices on the Snapshot page."))
        return
    chart(
        position_figure(
            shown,
            unit(shown.values[-1][0], nominal=nominal),
            labels=month_labels(),
            compact=is_mobile(),
        ),
        key="securities-position-chart",
    )
    st.caption(
        _(
            "The value of the units held at each stored price, against their cost with fees. A "
            "few stored prices draw a few points: import a price history on the Snapshot page."
        )
    )
