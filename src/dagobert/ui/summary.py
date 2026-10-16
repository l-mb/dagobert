"""Totals of the asset sheet: by liquidity, by kind, net worth, change, allocation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING

import streamlit as st
from dateutil.relativedelta import relativedelta

from dagobert.history import observations, values_at, worth
from dagobert.i18n import N_, _
from dagobert.loader import load_assets, load_assumptions
from dagobert.model.assets import Asset, HoldingsAsset, TermDeposit
from dagobert.model.events import SellEvent
from dagobert.money import format_eur, format_number, format_percent
from dagobert.prices import market_value
from dagobert.report.charts import AMBER, BLUE, GOLD, GREEN, ORANGE, PINK, PLUM, PURPLE
from dagobert.report.tracker import Slice, sunburst_figure
from dagobert.ui import chart, fold, is_mobile

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path

    from dagobert.lots import Lot
    from dagobert.model.plan import Scenario

# `liquid` follows the engine: what can pay expenses without a sale event. The groups are messages
# of the catalogue: `_()` where they show.
LIQUID, ILLIQUID, DEBT = N_("liquid"), N_("illiquid"), N_("debt")
LIQUIDITY = {
    "cash": LIQUID,
    "term_deposit": LIQUID,
    "fixed_income": LIQUID,
    "equity": LIQUID,
    "gold": LIQUID,
    "crypto": LIQUID,
    "property": ILLIQUID,
    "bav": ILLIQUID,
    "av_depot": ILLIQUID,
    "loan": DEBT,
}
# readable names of the asset kinds for tabs, tables and charts, messages of the catalogue. The
# YAML keeps the keys.
KINDS = {
    "cash": N_("cash"),
    "term_deposit": N_("term deposit"),
    "fixed_income": N_("fixed income"),
    "equity": N_("equity"),
    "gold": N_("gold"),
    "crypto": N_("crypto"),
    "property": N_("property"),
    "bav": N_("pension policy"),
    "av_depot": N_("pension depot"),
    "loan": N_("loan"),
}
# the colors of the sectors: those of the classes of the balance sheet (`report.balance_figure`)
COLORS: dict[tuple[str, ...], str] = {
    (LIQUID,): "#4b5a6e",
    (ILLIQUID,): "#6e604b",
    **{
        (LIQUIDITY[kind], KINDS[kind]): color
        for kind, color in {
            "cash": BLUE,
            "term_deposit": ORANGE,
            "fixed_income": ORANGE,
            "equity": GREEN,
            "gold": GOLD,
            "crypto": PLUM,
            "property": AMBER,
            "bav": PINK,
            "av_depot": PURPLE,
        }.items()
    },
}
# months after which a recorded value needs an update, by kind, else `UPDATE_MONTHS`: people
# record rarely (owner, 2026-10-13). None: never. A term deposit has its value from the contract,
# a property from a rare appraisal, unless a scenario sells it on a date (`SALE_MONTHS`).
UPDATE_MONTHS, SALE_MONTHS = 12, 6
UPDATE_EVERY: dict[str, int | None] = {"term_deposit": None, "property": None}
STALE_STYLE = "color: #d64545; font-weight: 600"
PHONE_RINGS = {"maxdepth": 3, "height": 340}  # on a phone two rings, low enough for landscape


def selling(scenario: Scenario) -> set[str]:
    """The assets that `scenario` sells on a date: their value moves while the sale runs."""
    return {e.asset for e in scenario.events if isinstance(e, SellEvent) and e.at is not None}


def update_months(asset: Asset, on_sale: Collection[str] = ()) -> int | None:
    """Months after which the value of `asset` needs an update, None for never: its
    `update_every`, else `SALE_MONTHS` while it is `on_sale`, else the months of its kind."""
    if asset.update_every is not None:
        return asset.update_every
    return SALE_MONTHS if asset.id in on_sale else UPDATE_EVERY.get(asset.kind, UPDATE_MONTHS)


def stale(asset: Asset, day: date, on_sale: Collection[str] = ()) -> bool:
    """The value of `asset` is older on `day` than its `update_months`."""
    months = update_months(asset, on_sale)
    return (
        months is not None
        and asset.asof is not None
        and day > asset.asof + relativedelta(months=months)
    )


def needs_update(asset: Asset, day: date, on_sale: Collection[str] = ()) -> bool:
    """The value of `asset` is `stale` on `day`, or has no `asof`. An empty asset needs no date,
    and neither does a term deposit: its contract gives the value."""
    if asset.asof is not None:
        return stale(asset, day, on_sale)
    return not isinstance(asset, TermDeposit) and bool(round(worth(asset, day)))


def totals(assets: list[Asset], day: date) -> tuple[dict[str, float], dict[str, float]]:
    """Sums by liquidity and by kind. Term deposits count with the interest accrued by `day`."""
    by_liquidity: dict[str, float] = defaultdict(float)
    by_kind: dict[str, float] = defaultdict(float)
    for asset in assets:
        by_liquidity[LIQUIDITY[asset.kind]] += worth(asset, day)
        by_kind[asset.kind] += worth(asset, day)
    return dict(by_liquidity), dict(by_kind)


def change(data_dir: Path, assets: list[Asset], day: date, since: date) -> dict[str, float] | None:
    """Change by liquidity from `since` to `day`, over the assets observed by `since`: an asset
    recorded later would show its entry as growth. None while no asset has a value by `since`:
    nothing to compare with, as in a new plan."""
    if not (then := values_at(observations(data_dir, assets), since)):
        return None
    delta: dict[str, float] = defaultdict(float)
    for asset in assets:
        if asset.id in then:
            delta[LIQUIDITY[asset.kind]] += worth(asset, day) - then[asset.id]
    return dict(delta)


def asset_slices(data_dir: Path, assets: list[Asset], day: date) -> list[Slice]:
    """Liquidity, kind, asset, and for an asset with trades its securities, split by their last
    stored prices. Loans are no sectors."""
    slices: list[Slice] = []
    for asset in assets:
        if asset.kind == "loan":
            continue
        path = (LIQUIDITY[asset.kind], KINDS[asset.kind], asset.name or asset.id)
        lots = _lots(data_dir, asset)
        whole = sum(lots.values())
        slices += (
            [Slice((*path, name), worth(asset, day) * v / whole) for name, v in lots.items()]
            if whole
            else [Slice(path, worth(asset, day))]
        )
    return slices


def _lots(data_dir: Path, asset: Asset) -> dict[str, float]:
    """Market value per security, empty unless every lot has a price."""
    if not isinstance(asset, HoldingsAsset):
        return {}
    named: dict[str, list[Lot]] = defaultdict(list)
    for lot in asset.book.open:
        named[lot.name].append(lot)
    priced = {name: market_value(data_dir, lots) for name, lots in named.items()}
    return {} if None in priced.values() else {name: p[0] for name, p in priced.items() if p}


def fixed_income_share(assets: list[Asset], day: date) -> float | None:
    """The share that the engine rebalances: fixed income over fixed income and equity. A term
    deposit joins fixed income when it matures."""
    _, by_kind = totals(assets, day)
    pool = by_kind.get("fixed_income", 0.0) + by_kind.get("equity", 0.0)
    return by_kind.get("fixed_income", 0.0) / pool if pool else None


def tiles(data_dir: Path, page: str) -> None:
    """Net worth, liquid, illiquid and debt today, each with the change in the current month, in
    gray without an arrow when there is none, so every tile keeps the line; none of them while no
    asset has a value from before the month (`change`). The key of their container names the
    `page` and starts with `tiles` for `ui.PAGE_STYLE`."""
    assets = load_assets(data_dir)
    today = date.today()
    since = today.replace(day=1) - timedelta(days=1)
    by_liquidity, by_kind = totals(assets, today)
    delta = change(data_dir, assets, today, since)
    moves = delta or {}
    shown = {N_("net worth"): (sum(by_kind.values()), sum(moves.values()))} | {
        name: (by_liquidity.get(name, 0.0), moves.get(name, 0.0))
        for name in dict.fromkeys(LIQUIDITY.values())
    }
    for column, (label, (value, moved)) in zip(
        st.container(key=f"tiles-{page}").columns(len(shown)), shown.items(), strict=True
    ):
        moving = bool(round(moved))
        column.metric(
            _(label),
            format_eur(value),
            delta=None
            if delta is None
            else (_("{amount} since {day}") if moving else _("no change since {day}")).format(
                amount=format_eur(moved), day=since
            ),
            delta_color="normal" if moving else "off",
            delta_arrow="auto" if moving else "off",
        )


def breakdown(data_dir: Path, height: int) -> None:
    """Asset sunburst `height` pixels high and the fixed-income share against the glide path. A
    phone shows two rings, the others open by a tap. Without an asset, the way to add one."""
    assets = load_assets(data_dir)
    if not assets:
        st.info(_("No asset yet: add your accounts and depots on the Assets page."))
        return
    today = date.today()
    phone = is_mobile()
    chart(
        sunburst_figure(
            _("assets\nbefore debt").replace("\n", "<br>"),
            [Slice(said(s.path), s.value) for s in asset_slices(data_dir, assets, today)],
            {said(path): color for path, color in COLORS.items()},
            **(PHONE_RINGS if phone else {"height": height}),
        ),
        key="overview-assets",
    )
    by_liquidity, by_kind = totals(assets, today)
    if debt := by_liquidity.get("debt"):
        st.caption(
            _("less loans {debt} = net worth {total}").format(
                debt=format_eur(debt), total=format_eur(sum(by_kind.values()))
            )
        )
    if phone:
        st.caption(_("Tap a ring to open it, the middle to go back."))
    assumptions = load_assumptions(data_dir)
    share = fixed_income_share(assets, today)
    if assumptions.allocation is not None and share is not None:
        age = assumptions.person.age(today.replace(day=1))
        target = assumptions.allocation.share_at(age)
        st.caption(
            _(
                "fixed-income share **{share}**: {points} points against the target of {target} "
                "at {age}"
            ).format(
                share=format_percent(share),
                points=format_number(100 * (share - target), 1, signed=True),
                target=format_percent(target),
                age=f"{age:.0f}",
            )
        )
    fold(
        _(
            "Recorded values before the tax on unrealized gains. The middle shows the assets "
            "before debt: the loans are not in the rings, the line below the chart takes them "
            "off. An asset with trades splits into its securities by their last stored prices. "
            "The fixed-income share is what the simulation rebalances towards the target share "
            "of your allocation on the Assumptions page: fixed income over fixed income and "
            "equity. Term deposits join it when they mature."
        ),
        _("How to read the assets"),
    )


def said(path: tuple[str, ...]) -> tuple[str, ...]:
    """A path of `asset_slices` or `COLORS` in the language of the session: its group and its kind
    in words, the asset and its securities as written."""
    return tuple(_(part) for part in path[:2]) + path[2:]
