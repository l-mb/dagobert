"""A downloaded table of dated values, such as a price history: `sniff` reads the file, `guess`
maps its columns, `parse` reads the dates and values by a mapping that the user can change.

Two families are common: German exports (`;`, `1.234,56`, `31.12.2025`) and English ones
(`,`, `1,234.56`, `2025-12-31`). Some name the month: `31. Dez. 2025`, `Dec 31, 2025`."""

from __future__ import annotations

import csv
import io
import itertools
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal, get_args

from dagobert.problems import RefusedError

Decimal = Literal[",", "."]
DateOrder = Literal["ymd", "dmy", "mdy"]
DECIMALS: tuple[Decimal, ...] = get_args(Decimal)
DATE_ORDERS: tuple[DateOrder, ...] = get_args(DateOrder)
MARKS: dict[Decimal, str] = {",": "comma", ".": "point"}  # a decimal mark in words
DELIMITERS = (";", "\t", ",")
# headers of a price column, the better first: `Close` before `Adj Close`, which a dividend
# lowers backwards
VALUE_NAMES = ("schluss", "schlusskurs", "close", "kurs", "price", "nav", "rücknahmepreis")
CURRENCY_NAMES = ("währung", "currency", "ccy")
VOLUME_NAMES = ("volume", "volumen", "umsatz", "stück")  # numeric, but no price
NOT_EUR = "not EUR: import the EUR price history"
SAMPLE = 50  # rows that the guess looks at
_TIME = r"(?:[ T]\d{1,2}:\d{2}.*)?"  # after the date, ignored
_DATE = re.compile(rf"(\d{{1,4}})([-./])(\d{{1,2}})\2(\d{{2,4}}){_TIME}")
# the English and German names and abbreviations of each month
MONTHS = {
    name: month
    for month, names in enumerate(
        (
            ("jan", "january", "januar", "jän", "jänner"),
            ("feb", "february", "februar"),
            ("mar", "march", "mär", "märz", "mrz"),
            ("apr", "april"),
            ("may", "mai"),
            ("jun", "june", "juni"),
            ("jul", "july", "juli"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october", "okt", "oktober"),
            ("nov", "november"),
            ("dec", "december", "dez", "dezember"),
        ),
        start=1,
    )
    for name in names
}
_MONTH = rf"(?P<month>{'|'.join(sorted(MONTHS, key=len, reverse=True))})\.?"
_YEAR = r"(?P<year>\d{4}|\d{2})"
# `31. Dez. 2025`, `31-Dec-25`; `Dec 31, 2025`
_DAY_FIRST = re.compile(rf"(?P<day>\d{{1,2}})\.?[-/ ]?{_MONTH}[-/ ]?{_YEAR}{_TIME}", re.IGNORECASE)
_MONTH_FIRST = re.compile(rf"{_MONTH}[-/ ](?P<day>\d{{1,2}}),?[-/ ]{_YEAR}{_TIME}", re.IGNORECASE)
_NUMBER = re.compile(r"[-+]?\d[\d.,]*")
# a mark followed by other than three digits at the end of a number is no thousands group
_FRACTION = re.compile(r"\d([.,])(?:\d{1,2}|\d{4,})$")


@dataclass(frozen=True)
class Table:
    """The rows after the header, each with its line in the file."""

    delimiter: str
    header: list[str]
    rows: list[tuple[int, list[str]]]

    def name(self, column: int) -> str:
        return self.header[column].strip() or f"column {column + 1}"

    def column(self, name: str) -> int:
        """The index of the column `name`, compared without case. Raises `RefusedError`."""
        names = [self.name(i).casefold() for i in range(len(self.header))]
        if name.strip().casefold() not in names:
            msg = (
                f"no column {name!r}, the table has {', '.join(map(self.name, range(len(names))))}"
            )
            raise RefusedError(msg)
        return names.index(name.strip().casefold())

    def cells(self, column: int) -> list[str]:
        """The non-empty cells of `column` in the first `SAMPLE` rows."""
        return [
            cells[column].strip()
            for _, cells in self.rows[:SAMPLE]
            if len(cells) > column and cells[column].strip()
        ]


@dataclass(frozen=True)
class Mapping:
    """Columns by index, the decimal mark of the values and the order of the date parts."""

    date: int
    value: int
    decimal: Decimal
    dates: DateOrder
    currency: int | None = None  # without one every row reads as EUR

    def describe(self, table: Table) -> str:
        currency = "none, read as EUR" if self.currency is None else table.name(self.currency)
        return (
            f"date {table.name(self.date)} ({self.dates}), value {table.name(self.value)}, "
            f"decimal {MARKS[self.decimal]}, currency {currency}"
        )


@dataclass(frozen=True)
class Parsed:
    """The values by date, sorted, and the refused lines with their reason."""

    points: list[tuple[date, float]]
    refused: list[tuple[int, str]]


def sniff(raw: bytes) -> Table:
    """The table of a downloaded file: UTF-8 with or without BOM, else cp1252, delimited by `;`,
    tab or `,`. The header is the first row whose next row holds a date and a number, so lines
    before it (a title, the ISIN, the period) drop. A file whose first row is data has no header.
    Raises `RefusedError` without such a row, and for a file in neither encoding: a spreadsheet,
    a PDF."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError as err:
            msg = f"not a text table: byte {err.start + 1} reads as neither UTF-8 nor cp1252"
            raise RefusedError(msg) from None
    for delimiter in DELIMITERS:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = [(reader.line_num, cells) for cells in reader if any(c.strip() for c in cells)]
        for n, ((_, header), (_, first)) in enumerate(itertools.pairwise(rows)):
            if _is_data(first) and len(header) > 1:
                if _is_data(header):
                    return Table(delimiter, [""] * len(header), rows[n:])
                return Table(delimiter, header, rows[n + 1 :])
    msg = "no table found: no row is followed by a row with a date and a number"
    raise RefusedError(msg)


def _is_date(cell: str) -> bool:
    return bool(_DATE.fullmatch(cell) or _named(cell))


def _named(cell: str) -> re.Match[str] | None:
    """A date that names its month, which fixes the order of day and month."""
    return _DAY_FIRST.fullmatch(cell) or _MONTH_FIRST.fullmatch(cell)


def _is_data(cells: list[str]) -> bool:
    dates = [i for i, c in enumerate(cells) if _is_date(c.strip())]
    return bool(dates) and any(
        _NUMBER.fullmatch(c.strip().rstrip(" €")) for i, c in enumerate(cells) if i not in dates
    )


def guess(table: Table) -> Mapping:
    """The date column is the first whose cells read as dates. The value column has a header
    such as `Schluss` or `Close`, else it is the last numeric column that holds no volume. Raises
    `RefusedError` without a column of dates or of numbers."""
    columns = range(len(table.header))
    dates = [i for i in columns if mostly(table.cells(i), _is_date)]
    numeric = [i for i in columns if i not in dates and mostly(table.cells(i), _NUMBER.fullmatch)]
    if not dates or not numeric:
        msg = f"no column of {'dates' if not dates else 'numbers'}"
        raise RefusedError(msg)
    names = [table.name(i).casefold() for i in columns]
    named = next(
        (
            i
            for match in (str.__eq__, str.startswith)
            for name in VALUE_NAMES
            for i in numeric
            if match(names[i], name)
        ),
        None,
    )
    prices = [i for i in numeric if not names[i].startswith(VOLUME_NAMES)] or numeric
    return Mapping(
        dates[0],
        prices[-1] if named is None else named,
        _decimal(table, numeric),
        order(table.cells(dates[0])),
        next((i for i in columns if names[i].startswith(CURRENCY_NAMES)), None),
    )


def mostly(cells: list[str], match: Callable[[str], object]) -> bool:
    """More than half of `cells` match: a stray footer does not hide a column."""
    return 2 * sum(bool(match(c.rstrip(" €"))) for c in cells) > len(cells)


def _decimal(table: Table, numeric: list[int]) -> Decimal:
    """A number with both marks ends with the decimal one, and a mark before other than three
    digits is decimal. Else a `;` delimiter goes with a decimal comma, any other with a point."""
    cells = [c.rstrip(" €") for i in numeric for c in table.cells(i)]
    both = [c for c in cells if "." in c and "," in c]
    if both:
        return "," if both[0].rfind(",") > both[0].rfind(".") else "."
    if found := next((m[1] for c in cells if (m := _FRACTION.search(c))), None):
        return "," if found == "," else "."
    return "," if table.delimiter == ";" else "."


def order(cells: list[str]) -> DateOrder:
    """A year first is `ymd`, dots are `dmy`. Else a first part above 12 means `dmy`, and
    `mdy` otherwise. Named months give the order they are written in."""
    parts = [m.groups() for c in cells if (m := _DATE.fullmatch(c))]
    if not parts:
        return "mdy" if any(_MONTH_FIRST.fullmatch(c) for c in cells) else "dmy"
    first, mark = parts[0][0], parts[0][1]
    if len(first) == 4:
        return "ymd"
    if mark == "." or any(int(p[0]) > 12 for p in parts):
        return "dmy"
    return "mdy"


def read_date(cell: str, order: DateOrder) -> date | None:
    """`cell` as a date in the order `order`, a two-digit year from 1969 to 2068. A month by its
    English or German name or abbreviation (`Dec 31, 2025`, `31. Dez. 2025`) fixes the order
    itself. A time after the date is ignored."""
    month: int | str
    if named := _named(cell := cell.strip()):
        year, month, day = named["year"], MONTHS[named["month"].casefold()], named["day"]
    elif match := _DATE.fullmatch(cell):
        first, _, second, third = match.groups()
        year, month, day = {
            "ymd": (first, second, third),
            "dmy": (third, second, first),
            "mdy": (third, first, second),
        }[order]
        if len(year) not in {2, 4} or len(day) > 2:
            return None
    else:
        return None
    full = int(year) + (0 if len(year) == 4 else 1900 if int(year) >= 69 else 2000)
    try:
        return date(full, int(month), int(day))
    except ValueError:
        return None


def day(cell: str, order: DateOrder) -> date:
    """`cell` as a date (`read_date`). Raises ValueError with the cell."""
    if (found := read_date(cell, order)) is None:
        msg = f"date {cell!r} does not read as {order}"
        raise ValueError(msg)
    return found


def read_number(cell: str, decimal: Decimal) -> float | None:
    """`cell` as a number with the decimal mark `decimal`. Thousands groups take the other mark
    and three digits each, a `€` after the number is ignored."""
    group = re.escape("." if decimal == "," else ",")
    pattern = rf"([-+]?)(\d{{1,3}}(?:{group}\d{{3}})+|\d+)(?:{re.escape(decimal)}(\d+))?"
    if not (match := re.fullmatch(pattern, cell.strip().rstrip(" €").replace(" ", ""))):
        return None
    sign, whole, fraction = match.groups()
    return float(sign + re.sub(r"\D", "", whole) + "." + (fraction or "0"))


def number(cell: str, field: str, decimal: Decimal) -> float:
    """`cell` as a number (`read_number`). Raises ValueError with the field and the cell."""
    if (found := read_number(cell, decimal)) is None:
        msg = f"{field} {cell!r} does not read as a number with a decimal {MARKS[decimal]}"
        raise ValueError(msg)
    return found


def parse(table: Table, mapping: Mapping, *, today: date) -> Parsed:
    """The values by date. A line is refused with its reason when it lacks a cell, holds no date,
    a date after `today` or no value above zero, repeats a date or names another currency than
    EUR."""
    points: dict[date, float] = {}
    refused: list[tuple[int, str]] = []
    for line, cells in table.rows:
        try:
            found, value = _row(cells, mapping)
            if found in points or found > today:
                msg = f"{found} {'again' if found in points else 'is in the future'}"
                raise ValueError(msg)
        except ValueError as err:
            refused.append((line, str(err)))
            continue
        points[found] = value
    return Parsed(sorted(points.items()), refused)


def _row(cells: list[str], mapping: Mapping) -> tuple[date, float]:
    if len(cells) <= (need := max(mapping.date, mapping.value, mapping.currency or 0)):
        msg = f"only {len(cells)} of {need + 1} cells"
        raise ValueError(msg)
    if mapping.currency is not None and cells[mapping.currency].strip().upper() not in {"EUR", "€"}:
        raise ValueError(NOT_EUR)
    found = day(cells[mapping.date].strip(), mapping.dates)
    value = number(raw := cells[mapping.value].strip(), "value", mapping.decimal)
    if value <= 0:
        msg = f"value {raw} is not above zero"
        raise ValueError(msg)
    return found, value
