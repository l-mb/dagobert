"""EUR prices per security in `<data>/prices/<security>.csv` (`date,close`, one row per date,
sorted): imported from a downloaded price history or typed in by hand, also for a past date. Gold
(`XAU`) and Bitcoin (`BTC`) without a price file take the last month of their series. The market
value of the open lots at the last price, and its record in `assets.yaml` and `history.csv` with
the save of the prices and after a fetch that changes the series of gold or Bitcoin. The warnings
of a price far off speak the language of the session (rule `i18n`), English in the CLI."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING

from dagobert import history, lots, revisions, series
from dagobert.files import finite, read_csv
from dagobert.history import Observation
from dagobert.i18n import N_, _
from dagobert.loader import load_assets
from dagobert.lots import TradeKind
from dagobert.model.assets import SECURITY, HoldingsAsset, Trade
from dagobert.model.months import add_months
from dagobert.money import format_eur
from dagobert.problems import RefusedError
from dagobert.store import RowEdits, assets_file

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from dagobert.lots import Lot

Price = tuple[date, float]
Prices = list[Price]
NEAR = 5  # days: a trade this close to a price shows what a unit cost then
# times the price of that trade or the stored price: a slip of the decimal mark is 10, 100 or 1,000
OFF = (0.5, 2.0)
GRAMS_PER_TROY_OUNCE = 31.1034768  # exact, the international troy ounce of 1959: one unit of XAU


@dataclass(frozen=True)
class Symbol:
    """Gold or a coin that its series prices without a price file: the name of the series, and
    how far the price of a trade may lie from the series before `off_series` warns: `off` times
    the month of the trade, or of up to `lag` months before when the series ends earlier. What
    one unit is: `OFF_SERIES`."""

    series: str
    lag: int
    off: tuple[float, float]


BY_SYMBOL = {
    # gold moves a few percent a month: grams typed as troy ounces lie 31 times off
    "XAU": Symbol("gold", 3, OFF),
    # Bitcoin doubled within months: only a slip of the unit, such as mBTC, lies that far off
    "BTC": Symbol("bitcoin", 1, (0.2, 5.0)),
}
# a stored price far from the price per unit of a trade, by the kind of the trade and whether it
# is of the day of the price
OFF_TRADE = {
    (TradeKind.BUY, True): N_("{price} on {day}, the buy of that day paid {paid} per unit"),
    (TradeKind.BUY, False): N_("{price} on {day}, the buy of {when} paid {paid} per unit"),
    (TradeKind.SELL, True): N_("{price} on {day}, the sell of that day paid {paid} per unit"),
    (TradeKind.SELL, False): N_("{price} on {day}, the sell of {when} paid {paid} per unit"),
}
# a trade of a symbol far from its series, by the kind of the trade and the symbol
OFF_SERIES = {
    (TradeKind.BUY, "XAU"): N_(
        "the buy of {day} paid {paid} per unit of {security}, the gold series {value} per troy "
        "ounce in {month}"
    ),
    (TradeKind.SELL, "XAU"): N_(
        "the sell of {day} paid {paid} per unit of {security}, the gold series {value} per troy "
        "ounce in {month}"
    ),
    (TradeKind.BUY, "BTC"): N_(
        "the buy of {day} paid {paid} per unit of {security}, the bitcoin series {value} per "
        "bitcoin in {month}"
    ),
    (TradeKind.SELL, "BTC"): N_(
        "the sell of {day} paid {paid} per unit of {security}, the bitcoin series {value} per "
        "bitcoin in {month}"
    ),
}


@dataclass(frozen=True)
class Replaced:
    """A stored price that a save changes."""

    day: date
    old: float
    new: float


def price_file(data_dir: Path, security: str) -> Path:
    """Raises `RefusedError` for a text that is no security: it names the file."""
    if not re.fullmatch(SECURITY, security):
        msg = f"{security!r} is no security: an ISIN such as IE00B4L5Y983, or a symbol such as XAU"
        raise RefusedError(msg)
    return data_dir / "prices" / f"{security}.csv"


def read_prices(path: Path) -> Prices:
    return read_csv(
        path,
        f"{path.parent.name}/{path.name}",
        ("date", "close"),
        lambda r: (date.fromisoformat(r["date"]), finite(r["close"])),
    )


def merge(old: Prices, new: Prices) -> tuple[Prices, list[Replaced]]:
    """One row per date, sorted, the new price winning, and the stored prices that it changes."""
    known = dict(old)
    return sorted((known | dict(new)).items()), [
        Replaced(day, known[day], price)
        for day, price in new
        if day in known and known[day] != price
    ]


@dataclass(frozen=True)
class Saved:
    """What a save of prices changed: the stored prices that it replaced and the market values
    that it recorded."""

    replaced: list[Replaced]
    recorded: list[Observation]


def save(data_dir: Path, security: str, new: Prices, *, source: str) -> Saved:
    """Merge `new` into the price file of `security`, the one writer of the price files, and
    record the market values that the prices give (`record`), as one revision of `source`."""
    path = price_file(data_dir, security)

    def edit() -> tuple[dict[str, str | None], Saved]:
        rows, replaced = merge(read_prices(path), new)
        corrected = {(security, r.day) for r in replaced}
        texts, observed = record(data_dir, {security: rows}, corrected)
        # 12 digits: `g` alone keeps 6 and cut a price of 1234.5678 to 1234.57
        text = "date,close\n" + "".join(f"{day},{price:.12g}\n" for day, price in rows)
        return {path.relative_to(data_dir).as_posix(): text} | texts, Saved(replaced, observed)

    return revisions.write_returning(data_dir, source, edit)


def off_trades(trades: Iterable[Trade], points: Prices) -> list[str]:
    """The price nearest to each trade within `NEAR` days, when it lies outside `OFF` times the
    price per unit of the trade (Kurswert over units)."""
    by_day = dict(points)
    found: list[str] = []
    for trade in sorted(trades, key=lambda t: t.date):
        if not trade.units or not trade.amount:
            continue
        paid = trade.amount / trade.units
        near = (
            trade.date + timedelta(offset) for offset in sorted(range(-NEAR, NEAR + 1), key=abs)
        )
        day = next((d for d in near if d in by_day), None)
        if day is not None and not OFF[0] <= by_day[day] / paid <= OFF[1]:
            found.append(
                _(OFF_TRADE[trade.kind, day == trade.date]).format(
                    price=format_eur(by_day[day], cents=True),
                    day=day,
                    when=trade.date,
                    paid=format_eur(paid, cents=True),
                )
            )
    return found


def off_series(data_dir: Path, trades: Iterable[Trade]) -> list[str]:
    """The trades of a symbol of `BY_SYMBOL` whose price per unit lies outside its `Symbol.off`
    times its series in euros, of the month of the trade or up to `Symbol.lag` months before:
    grams typed as troy ounces. A month average or close, so only a slip of the unit shows."""
    priced = sorted(
        ((t, t.amount / t.units) for t in trades if t.security in BY_SYMBOL and t.units),
        key=lambda found: found[0].date,
    )
    months = {
        symbol: {p.month: p.value for p in series.in_euros(series.SERIES[s.series], data_dir)}
        for symbol, s in BY_SYMBOL.items()
        if any(t.security == symbol for t, _price in priced)
    }
    found: list[str] = []
    for trade, paid in priced:
        known, symbol = months[trade.security], BY_SYMBOL[trade.security]
        near = (add_months(trade.date.replace(day=1), -lag) for lag in range(symbol.lag + 1))
        if not paid or (at := next((m for m in near if m in known), None)) is None:
            continue
        if not symbol.off[0] <= paid / known[at] <= symbol.off[1]:
            found.append(
                _(OFF_SERIES[trade.kind, trade.security]).format(
                    day=trade.date,
                    paid=format_eur(paid, cents=True),
                    security=trade.security,
                    value=format_eur(known[at], cents=True),
                    month=f"{at:%Y-%m}",
                )
            )
    return found


def far_off(data_dir: Path, security: str, new: Prices) -> list[str]:
    """The prices of `new` that lie outside `OFF` times the stored price of their date or the
    price per unit of a trade nearby (`off_trades`)."""
    replaced = merge(read_prices(price_file(data_dir, security)), new)[1]
    return [
        *(
            f"{format_eur(r.new, cents=True)} on {r.day} replaces {format_eur(r.old, cents=True)}"
            for r in replaced
            if not OFF[0] <= r.new / r.old <= OFF[1]
        ),
        *off_trades(Securities.of(data_dir).trades.get(security, []), new),
    ]


@dataclass(frozen=True)
class Securities:
    """The securities of the assets with trades: the names by security, the held ones first, then
    the others traded, then those with a price file only (a history imported before its trades,
    no holding); the units held and the trades."""

    names: dict[str, str]
    units: dict[str, float]
    trades: dict[str, list[Trade]]

    @classmethod
    def of(cls, data_dir: Path) -> Securities:
        holdings = [a for a in load_assets(data_dir) if isinstance(a, HoldingsAsset)]
        units: defaultdict[str, float] = defaultdict(float)
        trades: defaultdict[str, list[Trade]] = defaultdict(list)
        for asset in holdings:
            for lot in asset.book.open:
                units[lot.security] += lot.units
            for trade in asset.trades:
                trades[trade.security].append(trade)
        label = lots.names(t for ts in trades.values() for t in ts)
        files = {
            p.stem for p in (data_dir / "prices").glob("*.csv") if re.fullmatch(SECURITY, p.stem)
        }
        names = {i: label.get(i, i) for i in {*trades, *files}}
        order = sorted(names, key=lambda i: (i not in units, i not in trades, names[i].casefold()))
        return cls({i: names[i] for i in order}, dict(units), dict(trades))


def series_price(data_dir: Path, security: str) -> Price | None:
    """The last month of the series of a symbol of `BY_SYMBOL` in euros, dated on its last day:
    the close of that day (Bitcoin) or the average up to it (gold). A provisional month, whose
    close or rate may still change, is dated on its first day: no later day is certain. None for
    another security and for a series without months, such as Bitcoin before its first fetch."""
    symbol = BY_SYMBOL.get(security)
    found = series.in_euros(series.SERIES[symbol.series], data_dir) if symbol else []
    if not found:
        return None
    last = found[-1]
    return (
        last.month if last.provisional else add_months(last.month, 1) - timedelta(days=1),
        last.value,
    )


def last_price(data_dir: Path, security: str, rows: Prices | None = None) -> Price | None:
    """The newer of the last stored price (of `rows`, else of the price file) and the one of its
    series (`series_price`), the stored one on the same day: a newer month of the series
    overrides an older typed price."""
    stored = read_prices(price_file(data_dir, security)) if rows is None else rows
    found = series_price(data_dir, security)
    return max([*stored[-1:], *([found] if found else [])], key=itemgetter(0), default=None)


def market_value(data_dir: Path, lots: Sequence[Lot]) -> tuple[float, date] | None:
    """Units times the last price (`last_price`), with the oldest of those dates.

    None without lots or when a lot has no price."""
    return _valued(lots, lambda security: last_price(data_dir, security))


def _valued(lots: Sequence[Lot], last: Callable[[str], Price | None]) -> tuple[float, date] | None:
    """`market_value` at the last price that `last` gives per security."""
    found = {s: last(s) for s in {lot.security for lot in lots}}
    known = {s: price for s, price in found.items() if price is not None}
    if not lots or len(known) < len(found):
        return None
    return (
        sum(lot.units * known[lot.security][1] for lot in lots),
        min(day for day, _price in known.values()),
    )


def record(
    data_dir: Path, stored: Mapping[str, Prices], corrected: set[tuple[str, date]]
) -> tuple[dict[str, str | None], list[Observation]]:
    """The texts of `assets.yaml` and `history.csv` with the market value of every asset whose
    open lots all have a price, dated with the oldest of those prices and counting the lots held
    on that date (`_row`), and the values. `stored` holds the price files of a save as it will
    write them. An asset recorded on that date or later keeps its value, unless the save replaced
    the last price of one of its securities (`corrected`: security and day): a corrected price of
    the day of `asof` records again."""

    def last(security: str) -> Price | None:
        return last_price(data_dir, security, stored.get(security))

    file = assets_file(data_dir)
    observed = [
        (day, asset.id, round(value, 2))
        for asset in load_assets(data_dir)
        if isinstance(asset, HoldingsAsset) and (row := _row(asset, last))
        for value, day, held in [row]
        if asset.asof is None
        or asset.asof < day
        or (asset.asof == day and _corrected(held, corrected, last))
    ]
    if not observed:
        return {}, []
    index = {row["id"]: i for i, row in enumerate(file.rows())}
    edits = RowEdits({index[i]: {"value": v, "asof": day} for day, i, v in observed})
    return {file.name: file.text(edits)} | history.appended(data_dir, observed), observed


def _row(
    asset: HoldingsAsset, last: Callable[[str], Price | None]
) -> tuple[float, date, list[Lot]] | None:
    """The value of a history row of `asset`, its date and the lots it counts. The date is the
    oldest last price of the lots held today; the row counts the lots held on that date (the
    trades up to it), each at its last price: a lot bought later does not count, a lot sold since
    does. None when a lot lacks a price or none was held then."""
    if (today := _valued(asset.book.open, last)) is None:
        return None
    held = lots.book(t for t in asset.trades if t.date <= today[1]).open
    priced = _valued(held, last)
    return None if priced is None else (priced[0], today[1], held)


@dataclass(frozen=True)
class Fetched:
    """What a fetch of a series changed: its months, and the market values recorded after it."""

    update: series.Update
    recorded: list[Observation]


def fetch_series(
    entry: series.Series, data_dir: Path, get: series.Getter = series.http_get, *, source: str
) -> Fetched:
    """`series.update`, then the record of the market values (`record`) as a revision of
    `source` when the fetch changed the last price of a symbol of `BY_SYMBOL`: a month of its
    series or of the dollar rate; it runs also when the fetch found nothing new, so a record that
    failed after an earlier fetch is made up. `series/` is no input, so the fetch itself stays
    outside the revision. A new price of the same day, such as a provisional month again, is
    corrected."""
    before = _symbols(data_dir)
    update = series.update(entry, data_dir, get)
    after = _symbols(data_dir)
    corrected = {
        (symbol, price[0])
        for symbol, price in after.items()
        if price and (old := before[symbol]) and old[0] == price[0] and old != price
    }
    recorded = revisions.write_returning(data_dir, source, lambda: record(data_dir, {}, corrected))
    return Fetched(update, recorded)


def _symbols(data_dir: Path) -> dict[str, Price | None]:
    return {symbol: last_price(data_dir, symbol) for symbol in BY_SYMBOL}


def _corrected(
    held: Sequence[Lot], corrected: set[tuple[str, date]], last: Callable[[str], Price | None]
) -> bool:
    """The last price of a security of `held` is one that a save replaced."""
    return any(
        (security, price[0]) in corrected
        for security in {lot.security for lot in held}
        if (price := last(security))
    )
