"""The Assets page: one editable table per asset kind, and the securities of the assets with
trades: value and return per security, the open lots, the sales and the trades themselves (the
form `tradeform`, the import `tradeimport`). Its words are messages of the catalogue (rule
`i18n`): a constant is marked `N_` and said where it shows, the cells of a securities table keep
English ids, which `formats` heads in words."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

import streamlit as st
from dateutil.relativedelta import relativedelta

from dagobert import lots, series, tax
from dagobert.i18n import N_, _
from dagobert.loader import load_assets, load_assumptions
from dagobert.model.assets import (
    CryptoAsset,
    EquityAsset,
    GoldAsset,
    HoldingsAsset,
    LotAsset,
    Trade,
)
from dagobert.model.streams import StreamKind
from dagobert.money import EUR_COLUMN, NUMBER_COLUMN
from dagobert.prices import market_value
from dagobert.references import Kind
from dagobert.returns import deflate
from dagobert.store import RowFile
from dagobert.ui import SECURITIES_ASSET, Stamp, arrived, data_stamp, fold, is_mobile, mode, summary
from dagobert.ui.gridcolumns import ASSET_MODELS, HOLDING_KINDS, Row, columns
from dagobert.ui.position import position_chart
from dagobert.ui.tables import COLUMNS_MEAN, Ref, Table, edit_table, focus, focused, pin, unsaved
from dagobert.ui.tradeform import (
    CODE,
    add_trade,
    basis_check,
    counts,
    series_notes,
    trades_own_basis,
)
from dagobert.ui.tradeimport import import_trades

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from pydantic import BaseModel
    from streamlit.elements.lib.column_types import ColumnConfig

# the headers of the grids where the key of the file is no plain word, a key with an underscore
# with spaces. The help of such a column names the key; any other column the key itself, in
# German its word (`gridcolumns.keyword`).
TITLES = {
    "id": N_("ID"),
    "asof": N_("as of"),
    "update_every": N_("check every (months)"),
    "sqm": N_("m²"),
    "per_sqm": N_("price per m²"),
    "fixed_until": N_("fixed rate until"),
    "annuity": N_("monthly payment"),
    "annuity_per_10k": N_("pension per 10.000 €"),
    "until_age": N_("paid until age"),
    "paid": N_("paid in"),
    "fuenftel": N_("one-fifth rule"),
    "basisrente": N_("Basisrente"),
    "conversion": N_("salary conversion"),
    "premium": N_("own premium per month"),
    "salary": N_("converted salary"),
    "subsidy": N_("employer subsidy"),
    "security": CODE,
    "bought_for": N_("bought for"),
    "cost_basis": N_("cost basis"),
    "teilfreistellung": N_("Fund gains tax-free %"),  # as on the Assumptions page, its default
    "lump_sum": N_("lump sum"),
    "prepayment_penalty": N_("prepayment penalty"),
    "bought": N_("bought in"),
    "building_share": N_("building share"),
    "afa": N_("AfA rate"),
    "finances": N_("financed property"),
}


# Scrolls the strip of the tabs to the tab that a link opened: on a phone it lay out of view, and
# Streamlit 1.65 does not bring a default tab into view. Its text never changes, so it runs once
# per drawing of the page, not on a rerun, whose strip the viewer may have moved since.
SHOW_TAB = """<script>{
  let frames = 0;
  const show = () => {
    const tab = document.querySelector(".st-key-assets-tab [aria-selected=true]");
    if (tab && tab.offsetWidth) {
      const strip = tab.parentElement, at = tab.getBoundingClientRect();
      const box = strip.getBoundingClientRect();
      strip.scrollLeft += at.left - box.left - (box.width - at.width) / 2;
    } else if (++frames != 300) requestAnimationFrame(show);
  };
  requestAnimationFrame(show);
}</script>"""
# The query of a link to an asset: `?asset=flat&fields=per_sqm,asof` opens the tab of its kind on
# its row, with the columns to check (`tables.Focus`), until a save of the row or another page
ASSET, FIELDS = "asset", "fields"


def opened(asset: str, *fields: str) -> dict[str, str]:
    """The query of a link that opens `asset` on this page with `fields` to check."""
    return {ASSET: asset, FIELDS: ",".join(fields)}


def titles(model: type[BaseModel]) -> dict[str, str]:
    """The header of each column of `model` that `TITLES` names."""
    return {c.name: TITLES[c.name] for c in columns(model) if c.name in TITLES}


SALARY = Ref(Kind.STREAM, sorts=(StreamKind.SALARY,))


def unconverted(streams: Iterable[object]) -> frozenset[str]:
    """The names of the salary streams that a conversion cannot take (`Plan._plan_checks`): no row
    of the name pays every month without `of`, such as a bonus."""
    named = [s for s in streams if isinstance(s, dict) and s.get("name")]
    monthly = {s["name"] for s in named if not s.get("of") and s.get("every", 1) == 1}
    return frozenset(str(s["name"]) for s in named if s["name"] not in monthly)


@st.cache_data(max_entries=4, show_spinner=False)  # only the latest stamp is hit
def _unconverted(data_dir: Path, stamp: Stamp) -> frozenset[str]:
    """`unconverted` of `cashflows.yaml`, once per state of the inputs (`stamp`)."""
    del stamp
    return unconverted(RowFile(data_dir, "cashflows.yaml", ("streams",)).rows())


TABLES = {
    kind: Table(
        model,
        f"assets-{kind}",
        fixed={"kind": kind},
        pinned=("id",),
        # the pinned id takes half of a phone in portrait: what an asset is worth next to it
        lead=("value", "balance", "per_sqm", "rate"),
        negative=("balance",),  # of a loan
        track=True,
        options={
            "growth": Ref(Kind.RETURN_CLASS),
            "tags": Ref(Kind.TAG, new=True),
            # a bAV policy: its phases, the salary of its conversion (`page` leaves out the bonuses)
            **({"phases": Ref(Kind.PHASE), "salary": SALARY} if kind == "bav" else {}),
            **({"finances": Ref(Kind.ASSET, sorts=("property",))} if kind == "loan" else {}),
        },
        locked=("id",),
        rename=Kind.ASSET,
        identity=("id",),
        titles=titles(model),
        help_label=COLUMNS_MEAN,
        grid="assets",
    )
    for kind, model in ASSET_MODELS.items()
}
# what a trade is worth first, the name last: on a phone the rest needs a swipe
TRADE_FIELDS = ("date", "kind", "security", "units", "amount", "fees", "name")
TRADE_IDENTITY = ("date", "kind", "security")  # names a trade among those of an asset
TRADES = mode.Item(mode.Sort.DATA, ("trades",))  # the securities tab, its trades and prices


def trades(depot: str) -> Table:
    """The grid of the trades of the asset `depot`."""
    return Table(
        Trade,
        f"trades-{depot}",
        fields=TRADE_FIELDS,
        sort_by=("date",),
        pinned=("date",),
        identity=TRADE_IDENTITY,
        titles=titles(Trade),
        help_label=COLUMNS_MEAN,
    )


# above the grid of gold or crypto: what the trades of an asset decide and how the simulation
# reads them (decided: the asset without trades, one security per asset), with `COUNTS`
LOT_KINDS = {
    "gold": (
        GoldAsset,
        N_(
            "Bars, coins, or a note backed by gold. Their trades go into the **securities** tab. "
            "{counts}"
        ),
    ),
    "crypto": (
        CryptoAsset,
        N_(
            "One wallet or account per asset, its trades in the **securities** tab. {counts} "
            "Another coin takes its own return class in **growth**."
        ),
    ),
}
LOT_HELD = N_(
    "Without trades an asset counts as held for more than a year: a sale is free of tax. Keep "
    "one security per asset: the simulation splits the **value** over the lots by their cost "
    "across securities, as it reads no prices. A **tax** of **capital** (a note without "
    "physical backing) needs trades."
)
# below the asset select of the securities tab, for gold or crypto
LOT_TAX = N_(
    "A sale of gold or crypto is free of tax once the units were held for more than a year "
    "(§23 EStG): **free from** is the day after the first anniversary of the purchase, and "
    "**tax-free units** are those a sale today pays no tax on. Before, the gain is a private "
    "sale for the Anlage SO: the sales list it by **tax**, with the dates of the purchases. "
    "**capital** units (an asset with the tax **capital**, or crypto bought from the month that "
    "the Assumptions page sets for crypto as capital income) pay the flat tax whenever sold "
    "(§20 EStG). A sale takes the oldest units first. The simulation counts whole months, so it "
    "frees a unit up to a month later."
)
# below the tables of the securities tab
HOLDINGS = N_(
    "Enter the trades as the bank lists them, the amounts in euros: the **amount** is the price "
    "of all units without fees (the Kurswert), or the Vorabpauschale of a fund: the part of its "
    "expected gain that is taxed each year before a sale, booked in January for the year "
    "before. A sale takes the oldest units of the security first (FIFO). The yearly returns are "
    "money-weighted and before tax, the real ones in euros of the last price date by the "
    "consumer prices. A lot counts from its purchase. Under a year they stay empty: a few months "
    "would inflate them to a rate per year."
)
# the tax of a lot of gold or crypto, by its sale or by today: free after the holding period,
# a private sale (§23 EStG) before, capital income (§20 EStG) for `tax: capital` and for crypto
# bought from `tax.crypto_capital_from`
FREE, PRIVATE_SALE, CAPITAL = N_("free"), N_("private sale"), N_("capital")
TAX_FREE = N_(
    "tax-free units"
)  # of a security of gold or crypto: those that a sale today pays none on
YEARLY, REAL = N_("yearly return %"), N_("real yearly return %")  # of a security or a lot
YEAR = relativedelta(years=1)  # the shortest span with a yearly return (GIPS: none annualized)
SOLD_SHOWN = relativedelta(months=3)  # a security sold in full stays listed this long (owner)
VP = N_("Vorabpauschale per unit")  # of an open lot of a fund
RETURNS = {  # the percentages of a security with their help
    "gain %": N_("The gain over the cost of the units held"),
    YEARLY: N_(
        "The money-weighted return per year (% p.a.) up to the last price, before tax: of all "
        "trades of a security, of the purchase of a lot. Empty under a year."
    ),
    REAL: N_("The same after inflation, in euros of the last price date"),
}
# the columns of the securities tables by their ids, in words
HEADERS = {
    "security": N_("security"),
    "value": N_("value"),
    "gain": N_("gain"),
    "gain %": N_("gain %"),
    YEARLY: YEARLY,
    REAL: REAL,
    "units": N_("units"),
    TAX_FREE: TAX_FREE,
    "cost": N_("cost"),
    CODE: CODE,
    "as of": N_("as of"),
    "bought": N_("bought"),
    "price": N_("price"),
    VP: VP,
    "tax": N_("tax"),
    "free from": N_("free from"),
    "date": N_("date"),
    "proceeds": N_("proceeds"),
}
# the formats of the number columns: units group their thousands by a space, a grouping dot would
# read as the decimal point of the price
FORMATS = {
    **dict.fromkeys(("units", TAX_FREE), NUMBER_COLUMN),
    **dict.fromkeys(RETURNS, "%.1f"),
    **dict.fromkeys(("price", VP), "%.4f"),
    **dict.fromkeys(("cost", "value", "gain", "proceeds"), EUR_COLUMN),
}
HELPS = RETURNS | {
    "price": N_("Per unit, with fees"),
    VP: N_(
        "Vorabpauschale: the part of the expected gain of a fund that is taxed each year before a "
        "sale. It raises the cost basis of the lot."
    ),
}
# what a security is worth and earned first: on a phone the rest needs a swipe
SECURITY_COLUMNS = (
    "security",
    "value",
    "gain",
    "gain %",
    YEARLY,
    REAL,
    "units",
    TAX_FREE,  # gold and crypto only
    "cost",
    CODE,
    "as of",
)


@dataclass(frozen=True)
class Holding:
    """The tax of the lots of a gold or crypto asset: a sale is free after `months` (§23 Abs. 1
    S. 1 Nr. 2 EStG: not more than a year between purchase and sale is a private sale), and
    capital income (§20 EStG) for a lot bought on or after `capital_from`. `today` counts the
    units that a sale now takes free."""

    months: int
    capital_from: date | None
    today: date

    @classmethod
    def of(cls, data_dir: Path, asset: LotAsset) -> Holding:
        """`tax: capital`, or for crypto `tax.crypto_capital_from` of `assumptions.yaml`."""
        assumptions = load_assumptions(data_dir)
        capital_from = (
            date.min
            if asset.tax == "capital"
            else assumptions.tax.crypto_capital_from
            if isinstance(asset, CryptoAsset)
            else None
        )
        months = tax.for_year(assumptions.tax_year).private_sale_months
        return cls(months, capital_from, date.today())

    def free_from(self, lot: lots.Lot) -> date | None:
        """The day after the holding period: the period ends with the day of the purchase a year
        on (§188 BGB). None for capital income, which no period frees."""
        if self.capital_from is not None and lot.bought >= self.capital_from:
            return None
        return lot.bought + relativedelta(months=self.months) + timedelta(days=1)

    def rule(self, lot: lots.Lot, day: date) -> str:
        """`FREE`, `PRIVATE_SALE` or `CAPITAL` for a sale of `lot` on `day`."""
        free = self.free_from(lot)
        return CAPITAL if free is None else FREE if day >= free else PRIVATE_SALE


def holding(data_dir: Path, asset: HoldingsAsset) -> Holding | None:
    """The tax of the lots of a gold or crypto asset, None for a depot or fixed income."""
    return Holding.of(data_dir, asset) if isinstance(asset, LotAsset) else None


def formats() -> dict[str, ColumnConfig]:
    """New column configs of a securities table, since `pin` changes them: each column headed in
    words (`HEADERS`), a number in its format (`FORMATS`), some with a help (`HELPS`)."""
    return {
        column: st.column_config.NumberColumn(
            _(header), format=FORMATS[column], help=_(HELPS[column]) if column in HELPS else None
        )
        if column in FORMATS
        else st.column_config.Column(_(header))
        for column, header in HEADERS.items()
    }


def _table(rows: list[dict[str, Any]]) -> None:
    """A read-only securities table. On a phone the security stays in view, and the grid grows
    with its rows: an inner scroll would hold the swipe that should scroll the page."""
    config = formats()
    pin(config, "security")
    st.dataframe(
        rows,
        hide_index=True,
        column_config=config,
        height="content" if is_mobile() else "auto",
        placeholder="",
    )


def securities(
    data_dir: Path,
    asset: HoldingsAsset,
    cpi: Callable[[date], float],
    rules: Holding | None,
    today: date,
) -> list[dict[str, Any]]:
    """One row per security held, or sold in full within `SOLD_SHOWN` before `today`, the
    largest value first, then the whole asset with all its trades: the open units, their cost and
    their value at the last stored price, and the yearly return of all trades with that value
    (money-weighted, before tax), in euros and in euros of today. Gold and crypto (`rules`) add
    the units that a sale today takes free of tax."""
    label = lots.names(asset.trades)
    shown = {lot.security for lot in asset.book.open} | {
        t.security
        for t in asset.trades
        if t.kind == lots.TradeKind.SELL and t.date + SOLD_SHOWN >= today
    }
    rows = [
        _security(
            data_dir,
            (label.get(code, code), code),
            [t for t in asset.trades if t.security == code],
            cpi,
            rules,
        )
        for code in dict.fromkeys(t.security for t in asset.trades)
        if code in shown
    ]
    return [
        *sorted(rows, key=lambda row: -(row.get("value") or 0.0)),
        _security(data_dir, (_("total"), None), asset.trades, cpi, rules),
    ]


def _security(
    data_dir: Path,
    security: tuple[str, str | None],
    trades: list[Trade],
    cpi: Callable[[date], float],
    rules: Holding | None,
) -> dict[str, Any]:
    """`security` is the name and the ISIN or symbol, which the total row has none of. A security
    with a lot that has no price shows no value and no return."""
    name, code = security
    open_lots = lots.book(trades).open
    cost = sum(lot.cost for lot in open_lots)
    row: dict[str, Any] = {
        "security": name,
        "units": None if code is None else sum(lot.units for lot in open_lots),
        "cost": round(cost, 2),
        CODE: code or "",
    }
    if rules is not None and code is not None:
        row[TAX_FREE] = sum(lot.units for lot in open_lots if rules.rule(lot, rules.today) == FREE)
    priced = market_value(data_dir, open_lots)
    if not open_lots or priced is not None:
        value, day = priced or (0.0, None)
        row |= {
            "value": round(value, 2),
            "gain": round(value - cost, 2),
            "gain %": round(100 * (value / cost - 1), 1) if cost else None,
            "as of": day,
        } | _yearly(lots.flows(trades) + ([(day, value)] if day is not None else []), cpi)
    return {k: row.get(k) for k in SECURITY_COLUMNS if rules is not None or k != TAX_FREE}


def _yearly(cash: list[lots.Flow], cpi: Callable[[date], float]) -> dict[str, float | None]:
    """The money-weighted return per year of the flows in percent, nominal and in euros of the
    last flow. None over less than a `YEAR`: a few months would inflate it to a rate per year."""
    days = [day for day, _ in cash]
    if not days or min(days) + YEAR > max(days):
        return dict.fromkeys((YEARLY, REAL))
    return {
        column: None if rate is None else round(100 * rate, 1)
        for column, rate in (
            (YEARLY, lots.irr(cash)),
            (REAL, lots.irr(deflate(cash, cpi, max(days)))),
        )
    }


def open_lots(
    data_dir: Path, asset: HoldingsAsset, cpi: Callable[[date], float], rules: Holding | None
) -> list[dict[str, Any]]:
    """Each open lot at the last stored price, with the yearly return since its purchase. `price`
    is per unit with fees. A lot of gold or crypto (`rules`) shows its tax if sold today and the
    day from which a sale is free, a lot of a fund the Vorabpauschale charged on it."""
    return [
        {
            "security": lot.name,
            "bought": lot.bought,
            "value": None if priced is None else round(priced[0], 2),
            "gain %": None
            if priced is None or not lot.cost
            else round(100 * (priced[0] / lot.cost - 1), 1),
        }
        | _yearly([] if priced is None else [(lot.bought, -lot.cost), (priced[1], priced[0])], cpi)
        | {
            "units": lot.units,
            "price": lot.price,
        }
        | (
            {VP: lot.vp}
            if rules is None
            else {"tax": _(rules.rule(lot, rules.today)), "free from": rules.free_from(lot)}
        )
        for lot in asset.book.open
        for priced in [market_value(data_dir, [lot])]
    ]


def sales(asset: HoldingsAsset, rules: Holding | None) -> list[dict[str, Any]]:
    """Each sale with the cost of the lots it took, oldest first. A sale of gold or crypto
    (`rules`) takes a row per tax of the lots it took, with its share of the proceeds and the dates
    of their purchase: the lines of a private sale for the Anlage SO."""
    return [
        _sale(s, rule, taken) for s in asset.book.sales for rule, taken in _parts(s, rules).items()
    ]


def _sale(sale: lots.Sale, rule: str | None, taken: list[lots.Lot]) -> dict[str, Any]:
    """The part of `sale` that took the lots `taken`, with its share of the proceeds."""
    units = sum(lot.units for lot in taken)
    proceeds, cost = sale.proceeds * units / sale.units, sum(lot.cost for lot in taken)
    return {
        "date": sale.date,
        "security": sale.name,
        "gain": round(proceeds - cost, 2),
        **({} if rule is None else {"tax": _(rule)}),
        "proceeds": round(proceeds, 2),
        "cost": round(cost, 2),
        "units": units,
        **({} if rule is None else {"bought": _dates(taken)}),
    }


def _parts(sale: lots.Sale, rules: Holding | None) -> dict[str | None, list[lots.Lot]]:
    """The lots that `sale` took by their tax, all under None without `rules`."""
    parts: dict[str | None, list[lots.Lot]] = {}
    for lot in sale.taken:
        parts.setdefault(None if rules is None else rules.rule(lot, sale.date), []).append(lot)
    return parts


def _dates(taken: list[lots.Lot]) -> str:
    """The purchase dates of the lots, the first to the last."""
    first, last = min(lot.bought for lot in taken), max(lot.bought for lot in taken)
    return str(first) if first == last else _("{first} to {last}").format(first=first, last=last)


def securities_tab(file: RowFile) -> None:
    rows = file.rows()
    index = {  # the asset with the most trades first
        row["id"]: i
        for i, row in sorted(enumerate(rows), key=lambda item: -len(item[1].get("trades") or ()))
        if row["kind"] in HOLDING_KINDS
    }
    depot = st.selectbox(
        _("Asset"),
        list(index),
        format_func=lambda i: _choice(rows[index[i]]),
        key=SECURITIES_ASSET,
    )
    if depot is None:
        st.info(_("No equity, fixed-income, gold or crypto asset: only these hold securities."))
        return
    asset = {a.id: a for a in load_assets(file.data_dir) if isinstance(a, HoldingsAsset)}[depot]
    rules = holding(file.data_dir, asset)
    if asset.trades:
        cpi = series.consumer_prices(file.data_dir)
        rows = securities(file.data_dir, asset, cpi, rules, date.today())
        _table(rows)
        with st.expander(_("Open lots"), key="securities-lots"):
            _table(open_lots(file.data_dir, asset, cpi, rules))
        if asset.book.sales:
            with st.expander(_("Sales"), key="securities-sales"):
                _table(sales(asset, rules))
        position_chart(file.data_dir, asset, {row[CODE]: row["security"] for row in rows[:-1]}, cpi)
    else:
        st.info(no_trades(asset))
    fold(_(HOLDINGS), _("How to read the securities"))
    if rules is not None:
        fold(_(LOT_TAX), _("How the tax of a sale works"))
    grid = replace(
        trades(depot),
        parent=trades_own_basis if isinstance(asset, EquityAsset) else None,
        check=basis_check(asset) if rules is None else partial(series_notes, file.data_dir),
    )
    st.subheader(_("Trades"))
    if is_mobile():
        add_trade(file.child(depot, "trades"), asset, grid)
    import_trades(file.child(depot, "trades"), grid)
    edit_table(file.child(depot, "trades"), grid)


def _choice(row: Row) -> str:
    name = row.get("name") or row["id"]
    return name if row.get("trades") else _("{name} (no trades)").format(name=name)


def no_trades(asset: HoldingsAsset) -> str:
    """What an asset without trades means, and how to start them."""
    if isinstance(asset, LotAsset):
        text = N_(
            "{name} has no trades, so it counts as held for more than a year: a sale is free of "
            "tax. To track when its units become free, add the first buy below."
        )
    elif isinstance(asset, EquityAsset):
        text = N_(
            "{name} has no trades, so it shows no securities. An account without securities, "
            "such as Tagesgeld, needs none: its value is enough. To track "
            "securities in it, add the first buy below. The trades then replace its cost basis."
        )
    else:
        text = N_(
            "{name} has no trades, so it shows no securities. An account without securities, "
            "such as Tagesgeld, needs none: its value is enough. To track "
            "securities in it, add the first buy below."
        )
    return _(text).format(name=asset.label)


def _arrival(file: RowFile) -> str | None:
    """The kind of the asset that a link opened (`opened`): its grid opens on its row. A link to
    another asset, or the page opened without one, ends the focus of the run before."""
    asset = st.query_params.pop(ASSET, None)
    fields = tuple(filter(None, st.query_params.pop(FIELDS, "").split(",")))
    if asset is not None or arrived():
        row = next((r for r in file.rows() if r.get("id") == asset), None)
        for kind, table in TABLES.items():
            focus(table, row if row and row.get("kind") == kind else None, fields)
    return next((kind for kind, table in TABLES.items() if focused(table)), None)


def page(file: RowFile) -> None:
    """A tab per asset kind that the mode and the features show (`mode.View`), the inputs hold or
    a grid with unsaved edits, then `securities` likewise, and the note of what they hide."""
    st.title(_("Assets"))
    summary.tiles(file.data_dir, "assets")
    view, opens = mode.view(file.data_dir), _arrival(file)
    kinds = [
        kind
        for kind, table in TABLES.items()
        if kind == opens or view.shows(mode.Item(mode.Sort.KIND, (kind,))) or unsaved(table)
    ]
    traded = view.shows(TRADES) or any(
        unsaved(trades(row["id"]))
        for row in file.rows()
        if row.get("kind") in HOLDING_KINDS and "id" in row
    )
    tabs = st.tabs(
        [*(_(summary.KINDS[kind]) for kind in kinds), *([_("securities")] if traded else [])],
        default=_(summary.KINDS[opens]) if opens else None,
        key="assets-tab",
    )
    salary = replace(SALARY, without=_unconverted(file.data_dir, data_stamp(file.data_dir)))
    for tab, kind in zip(tabs, kinds, strict=False):
        with tab:
            if kind in LOT_KINDS:
                model, text = LOT_KINDS[kind]
                about = _(text).format(counts=counts(model))
                fold(f"{about} {_(LOT_HELD)}", _("About gold and crypto"))
            table = TABLES[kind]
            bav = kind == "bav"
            edit_table(
                file,
                replace(table, options={**table.options, "salary": salary}) if bav else table,
                view,
            )
    if traded:
        with tabs[-1]:
            securities_tab(file)
    hidden = {mode.Item(mode.Sort.KIND, (k,)): summary.KINDS[k] for k in TABLES if k not in kinds}
    hidden |= {} if traded else {TRADES: N_("securities")}
    view.note({item: _(words) for item, words in hidden.items()}, held=mode.Held.KINDS)
    if opens:
        st.html(SHOW_TAB, unsafe_allow_javascript=True)
