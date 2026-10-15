"""The executions of a broker export (CSV) as new trades of an asset: `guess` maps the columns by
their headers, `read` takes the buys and sales, `merge` keeps those that the asset does not hold
yet and can replay, and `save` adds them as one revision.

The headers follow the exports that are described in public: the transaction export of Trade
Republic, the transactions of the Scalable Capital broker and the Depotumsätze of comdirect. The
user picks the columns of any other export.

The summary of an import and its slips speak the language of the session (rule `i18n`), English
in the CLI; the reasons of a refused line stay English, as the errors of an input do."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter, ValidationError

from dagobert import csvimport, lots, prices, revisions
from dagobert.i18n import _, ngettext
from dagobert.lots import TradeKind
from dagobert.model.assets import ISIN, Asset, EquityAsset, HoldingsAsset, Trade
from dagobert.money import format_eur
from dagobert.problems import RefusedError, dotted, errors, message
from dagobert.store import RowEdits

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from datetime import date
    from pathlib import Path

    from dagobert.store import RowFile

Row = dict[str, Any]
# the headers of each field, compared without case: whole first, then as the start of a header
ALIASES: dict[str, tuple[str, ...]] = {
    "date": ("datum", "date", "schlusstag", "handelstag", "ausführungstag", "geschäftstag"),
    "kind": ("art", "typ", "type", "kind", "transaktionsart", "umsatzart", "buchungsart"),
    "security": ("isin", "symbol"),
    "units": ("menge", "stück", "anzahl", "anteile", "shares", "units", "quantity", "nominale"),
    "amount": ("kurswert", "amount", "betrag", "umsatz"),
    "fees": ("gebühren", "gebühr", "fee", "entgelt", "provision", "spesen"),
    "name": ("bezeichnung", "wertpapier", "name", "description", "titel"),
    # of the amount: the price of a comdirect export may be in another currency
    "currency": ("kurswertwährung", *csvimport.CURRENCY_NAMES),
    "status": ("status", "orderstatus"),
}
FIELDS = tuple(ALIASES)
REQUIRED = ("date", "security", "units", "amount")
# the start of a cell of the kind column, without case; any other kind is no trade
KINDS = {
    "kauf": TradeKind.BUY,
    "buy": TradeKind.BUY,
    "sparplan": TradeKind.BUY,
    "savings plan": TradeKind.BUY,
    "savings_plan": TradeKind.BUY,
    "verkauf": TradeKind.SELL,
    "sell": TradeKind.SELL,
    "vorabpauschale": TradeKind.VORABPAUSCHALE,
}
# the start of a status of an execution: a cancelled, pending or rejected order is none
DONE = ("executed", "ausgeführt", "settled", "filled", "done", "completed", "gebucht")
# a count with its noun, singular for one, by the noun: `trade` or a kind of trade
COUNTED: dict[str, Callable[[int], str]] = {
    "trade": lambda n: ngettext("{n} trade", "{n} trades", n),
    TradeKind.BUY: lambda n: ngettext("{n} buy", "{n} buys", n),
    TradeKind.SELL: lambda n: ngettext("{n} sale", "{n} sales", n),
    TradeKind.VORABPAUSCHALE: lambda n: ngettext("{n} Vorabpauschale", "{n} Vorabpauschalen", n),
}
NOT_EUR = "not EUR: the trades take euros"
_ASSET: TypeAdapter[Asset] = TypeAdapter(Asset)
_ISIN = re.compile(ISIN)


@dataclass(frozen=True)
class Columns:
    """The column of each field of `ALIASES` by index, None for none, the decimal mark and the
    order of the date parts. Without a kind column a negative number of units sells, without a
    currency every row reads as EUR, without a status every row counts."""

    at: dict[str, int | None]
    decimal: csvimport.Decimal
    dates: csvimport.DateOrder

    @property
    def missing(self) -> list[str]:
        """The fields of `REQUIRED` without a column."""
        return [field for field in REQUIRED if self.at.get(field) is None]

    def describe(self, table: csvimport.Table) -> str:
        names = {f: "none" if (i := self.at.get(f)) is None else table.name(i) for f in FIELDS}
        names["date"] += f" ({self.dates})"
        decimal = f"decimal {csvimport.MARKS[self.decimal]}"
        return ", ".join([*(f"{f} {name}" for f, name in names.items()), decimal])


def guess(table: csvimport.Table) -> Columns:
    """Each field by the header of its column (`ALIASES`), each column for one field. Else the
    security is the first column of ISINs, and the date and the decimal mark are those of
    `csvimport.guess`. Raises ValueError without a column of dates or of numbers."""
    base = csvimport.guess(table)
    names = [table.name(i).casefold() for i in range(len(table.header))]
    at: dict[str, int] = {}
    for match in (str.__eq__, str.startswith):
        for field, aliases in ALIASES.items():
            hit = next(
                (
                    i
                    for alias in aliases
                    for i, name in enumerate(names)
                    if i not in at.values() and match(name, alias)
                ),
                None,
            )
            if field not in at and hit is not None:
                at[field] = hit
    at.setdefault("date", base.date)
    isins = (
        i
        for i in range(len(names))
        if i not in at.values() and csvimport.mostly(table.cells(i), _ISIN.fullmatch)
    )
    if "security" not in at and (found := next(isins, None)) is not None:
        at["security"] = found
    return Columns(
        {field: at.get(field) for field in FIELDS},
        base.decimal,
        csvimport.order(table.cells(at["date"])),
    )


class NoTrade(Exception):  # noqa: N818 a row to skip, not an error
    """A row that is no execution of a buy or sale: a dividend, a deposit, a cancelled order."""


@dataclass(frozen=True)
class Parsed:
    """The trades read with their line, oldest first, the refused lines with their reason and the
    other rows with their line and what they are (`Distribution`, `status Cancelled`)."""

    rows: list[tuple[int, Row]]
    refused: list[tuple[int, str]]
    others: list[tuple[int, str]]

    @property
    def skipped(self) -> Counter[str]:
        """The count of the other rows by what they are."""
        return Counter(what for _line, what in self.others)


def read(table: csvimport.Table, columns: Columns, *, today: date) -> Parsed:
    """The buys, sales and Vorabpauschalen of the table. Amounts and fees are in euros with cents,
    without their sign, as the units. A file with the newest row first is read backwards, so a
    sale follows the buy of its day. Raises `RefusedError` for a field of `REQUIRED` without a
    column."""
    if missing := columns.missing:
        msg = f"choose the column of {' and '.join(missing)}"
        raise RefusedError(msg)
    rows: list[tuple[int, Row]] = []
    refused: list[tuple[int, str]] = []
    others: list[tuple[int, str]] = []
    for line, cells in _oldest_first(table, columns):
        try:
            rows.append((line, _row(cells, columns, today)))
        except NoTrade as other:
            others.append((line, str(other)))
        except ValueError as err:
            refused.append((line, str(err)))
    return Parsed(sorted(rows, key=lambda found: found[1]["date"]), sorted(refused), sorted(others))


def _oldest_first(table: csvimport.Table, columns: Columns) -> list[tuple[int, list[str]]]:
    """The rows of `table`, backwards when its first date is newer than its last."""
    column = columns.at["date"]
    days = [
        day
        for _line, cells in table.rows
        if column is not None
        and len(cells) > column
        and (day := csvimport.read_date(cells[column], columns.dates)) is not None
    ]
    return table.rows[::-1] if days and days[0] > days[-1] else table.rows


def _row(cells: list[str], columns: Columns, today: date) -> Row:
    """One trade of `cells`. Raises `NoTrade` for a row of another kind or status, ValueError for
    a row that does not read."""
    at = {field: i for field, i in columns.at.items() if i is not None}
    if len(cells) <= (need := max(at.values())):
        msg = f"only {len(cells)} of {need + 1} cells"
        raise ValueError(msg)
    cell = {field: cells[i].strip() for field, i in at.items()}
    if "status" in cell and not cell["status"].casefold().startswith(DONE):
        raise NoTrade(f"status {cell['status'] or 'empty'}")
    kind = _kind(cell["kind"]) if "kind" in cell else None
    if cell.get("currency") and cell["currency"].upper() not in {"EUR", "€"}:
        raise ValueError(NOT_EUR)
    if (day := csvimport.day(cell["date"], columns.dates)) > today:
        msg = f"{day} is in the future"
        raise ValueError(msg)
    units, amount, fees = (
        csvimport.number(cell[f], f, columns.decimal) if cell.get(f) else None
        for f in ("units", "amount", "fees")
    )
    kind = kind or (TradeKind.SELL if units is not None and units < 0 else TradeKind.BUY)
    if kind == TradeKind.VORABPAUSCHALE:
        units = None
    elif not units:
        msg = f"the {kind} has no units"
        raise ValueError(msg)
    if amount is None:
        msg = f"the {kind} has no amount"
        raise ValueError(msg)
    if not (security := cell["security"].upper()):
        msg = f"the {kind} has no ISIN"
        raise ValueError(msg)
    row = {
        "date": day,
        "kind": kind.value,
        "security": security,
        "units": None if units is None else _whole(abs(units)),
        "amount": _whole(round(abs(amount), 2)),
        "fees": _whole(round(abs(fees or 0.0), 2)),
        "name": cell.get("name", ""),
    }
    return {k: v for k, v in row.items() if v not in (None, "") and (k != "fees" or v)}


def _kind(text: str) -> TradeKind:
    folded = text.casefold()
    if (kind := next((k for start, k in KINDS.items() if folded.startswith(start)), None)) is None:
        raise NoTrade(text or "no kind")
    return kind


def _whole(number: float) -> float:
    """Whole numbers stay whole in the file, like those typed."""
    return int(number) if number.is_integer() else number


@dataclass(frozen=True)
class Merged:
    """The rows to add, oldest first, how many the trades hold already and the refused lines."""

    added: list[Row]
    held: int
    refused: list[tuple[int, str]]


def merge(asset: HoldingsAsset, parsed: Parsed) -> Merged:
    """The rows of `parsed` that the trades of `asset` lack. A row with the date, security, units
    and amount of a trade is held already, each trade once: two equal executions of one day in a
    file need two trades. Refused are a row that the model refuses, a security that the asset
    does not take (equity and fixed income take ISINs) and a row that the trades so far cannot
    replay (`lots.book`: a sale of more units than held). A security without a name takes the
    name of its first row; a name given stays."""
    trades, added, refused = list(asset.trades), list[Row](), list[tuple[int, str]]()
    known, held = Counter(_same(t) for t in trades), 0
    for line, row in parsed.rows:
        try:
            trade = Trade.model_validate(row)
            if known[same := _same(trade)]:
                known[same] -= 1
                held += 1
                continue
            if not re.fullmatch(asset.securities, trade.security):
                msg = f"{trade.security} is no ISIN: a symbol is for gold or crypto"
                raise ValueError(msg)
            lots.book([*trades, trade])
        except ValueError as err:
            refused.append((line, _reason(err)))
            continue
        named = trade.security in lots.names(trades)
        trades.append(trade.model_copy(update={"name": ""}) if named else trade)
        added.append({k: v for k, v in row.items() if k != "name" or not named})
    return Merged(added, held, refused)


def _same(trade: Trade) -> tuple[date, str, float, float]:
    """What makes a row of a file the same as a trade, whatever the float arithmetic."""
    units = round(trade.units or 0.0, 6)
    return trade.date, trade.security, units, round(trade.amount, 2)


def _reason(err: ValueError) -> str:
    if not isinstance(err, ValidationError):
        return str(err)
    return "; ".join(f"{dotted(e.loc)}: " * bool(e.loc) + message(e) for e in errors(err))


def summary(parsed: Parsed, merged: Merged) -> tuple[str, str]:
    """How many trades a save adds, of which kinds and from when, and how many the trades hold
    already: `3 new trades from 2025-01-02 to 2025-03-03: 2 buys, 1 sale; 1 is in the trades
    already`. Then what it leaves out, empty for nothing: `4 other rows left out: Distribution 3,
    status Cancelled 1; 1 line refused`."""
    added, kinds = merged.added, Counter(row["kind"] for row in merged.added)
    found = (
        ngettext(
            "{n} new trade from {first} to {last}: {kinds}",
            "{n} new trades from {first} to {last}: {kinds}",
            len(added),
        ).format(
            n=len(added),
            first=added[0]["date"],
            last=added[-1]["date"],
            kinds=", ".join(counted(n, kind) for kind, n in kinds.items()),
        )
        if added
        else _("0 new trades")
    )
    if held := merged.held:
        already = ngettext("{n} is in the trades already", "{n} are in the trades already", held)
        found = f"{found}; {already.format(n=held)}"
    left: list[str] = []
    if others := len(parsed.others):
        other = ", ".join(f"{what} {n}" for what, n in parsed.skipped.most_common())
        left.append(
            ngettext(
                "{n} other row left out: {rows}", "{n} other rows left out: {rows}", others
            ).format(n=others, rows=other)
        )
    if lines := len(refused(parsed, merged)):
        left.append(ngettext("{n} line refused", "{n} lines refused", lines).format(n=lines))
    return found, "; ".join(left)


def counted(n: int, noun: str) -> str:
    """`n` with its noun (`COUNTED`), singular for one: `2 sales`, `2 Vorabpauschalen`."""
    return COUNTED[noun](n).format(n=n)


def refused(parsed: Parsed, merged: Merged) -> list[tuple[int, str]]:
    """The refused lines of the read and of the merge, in the order of the file."""
    return sorted(parsed.refused + merged.refused)


def slips(data_dir: Path, rows: Iterable[Row]) -> list[str]:
    """The new trades whose price per unit lies far from a stored price of their security
    (`prices.off_trades`) or from the series of gold or Bitcoin (`prices.off_series`): a decimal
    mark in the wrong place, grams typed as troy ounces."""
    trades = [Trade.model_validate(row) for row in rows]
    stored = (
        text
        for security in dict.fromkeys(t.security for t in trades)
        for text in prices.off_trades(
            [t for t in trades if t.security == security],
            prices.read_prices(prices.price_file(data_dir, security)),
        )
    )
    return [
        *prices.off_series(data_dir, trades),
        *(_("a stored price of {price}").format(price=t) for t in stored),
    ]


def holding(file: RowFile) -> tuple[HoldingsAsset, revisions.Seen]:
    """The asset whose trades `file` holds, and the `Seen` of those trades: a save goes only onto
    the trades that the import was checked against. Raises `RefusedError` for an asset that is gone
    or holds no securities."""
    revision = revisions.last_change(file.data_dir, file.name)  # before the read: see `digest`
    rows, holder = file.contents()
    asset = _ASSET.validate_python(holder | ({"trades": rows} if rows else {}))
    if not isinstance(asset, HoldingsAsset):
        msg = f"{asset.id} holds no securities: only equity, fixed income, gold and crypto do"
        raise RefusedError(msg)
    return asset, revisions.Seen(file.name, revision, revisions.digest(rows))


def replaced_basis(asset: HoldingsAsset) -> str | None:
    """The warning when trades replace the typed `cost_basis` of an equity asset (`save`, the
    trade form and grid): its lots then give the basis, and trades of recent months only leave
    out the cost of what it held before, so a run charges too much tax on a sale."""
    if isinstance(asset, EquityAsset) and asset.cost_basis is not None:
        return _(
            "the trades replace the cost basis of {basis} with the cost of their lots: they must "
            "go back to the first purchase"
        ).format(basis=format_eur(asset.cost_basis, cents=True))
    return None


def save(
    file: RowFile, asset: HoldingsAsset, added: list[Row], seen: revisions.Seen, *, source: str
) -> None:
    """Add the trades as one revision of `source`; an equity asset then takes its basis from its
    lots, and a typed `cost_basis` goes (`replaced_basis`). Raises `revisions.ConflictError` when
    its trades changed since `seen`."""
    basis = {"cost_basis": None} if isinstance(asset, EquityAsset) else {}
    file.apply(RowEdits(added=added, parent=basis), source=source, seen=seen)
