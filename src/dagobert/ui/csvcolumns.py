"""The select boxes of the columns of a CSV import: one per field, then the date order and the
decimal mark, each preselected with the guess. They are keyed by the header, so a new file starts
from its guess. The words of a `ColumnPick` are messages of the catalogue, said where they show."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import csvimport
from dagobert.i18n import N_, _

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PREVIEW = 3  # rows at each end of an import, and refused lines, that its preview shows
WIDTH = 160  # pixels of a select box: two fit beside each other on a phone
DECIMAL = N_("Look at the decimal mark")  # the hint of the guess of an import
_ORDERS = {"ymd": N_("year month day"), "dmy": N_("day month year"), "mdy": N_("month day year")}
_MARKS = {",": N_("comma: 1.234,56"), ".": N_("point: 1,234.56")}


@dataclass(frozen=True)
class ColumnPick:
    """A select box: its label, the guessed column and, for a field that may lack a column, the
    words of no column, both messages of the catalogue."""

    label: str
    guess: int | None
    none: str | None = None


def of_file(table: csvimport.Table, key: str) -> str:
    """`key` for the widgets of one file, by its header: a new file starts from its guess."""
    return f"{key}-{zlib.crc32(chr(31).join(table.header).encode())}"


def select(
    table: csvimport.Table,
    key: str,
    fields: Mapping[str, ColumnPick],
    dates: csvimport.DateOrder,
    decimal: csvimport.Decimal,
) -> tuple[dict[str, int | None], csvimport.DateOrder, csvimport.Decimal]:
    """The column of each field (None for none, or for a field without a guess until one is
    chosen), the date order and the decimal mark."""
    key = of_file(table, key)
    with st.container(horizontal=True, wrap=True):
        chosen = {name: _column(table, f"{key}-{name}", field) for name, field in fields.items()}
        order = st.selectbox(
            _("Date order"),
            csvimport.DATE_ORDERS,
            index=csvimport.DATE_ORDERS.index(dates),
            format_func=lambda option: _(_ORDERS[option]),
            key=f"{key}-dates",
            width=WIDTH,
        )
        mark = st.selectbox(
            _("Decimal mark"),
            csvimport.DECIMALS,
            index=csvimport.DECIMALS.index(decimal),
            format_func=lambda option: _(_MARKS[option]),
            key=f"{key}-decimal",
            width=WIDTH,
        )
    return chosen, order, mark


def _column(table: csvimport.Table, key: str, field: ColumnPick) -> int | None:
    """The select box of one field: no column first for a field that may lack one, none chosen
    for a field without a guess."""
    options: list[int | None] = [*([None] if field.none else []), *range(len(table.header))]
    return st.selectbox(
        _(field.label),
        options,
        index=None if field.guess is None and not field.none else options.index(field.guess),
        format_func=lambda i: _(str(field.none)) if i is None else table.name(i),
        key=key,
        width=WIDTH,
        placeholder=_("Choose a column"),
    )


def ends[T](rows: Sequence[T]) -> list[T]:
    """The first and the last `PREVIEW` rows of an import."""
    return [*rows[:PREVIEW], *rows[PREVIEW:][-PREVIEW:]]


def refused(lines: Sequence[tuple[int, str]]) -> str:
    """The first `PREVIEW` refused lines of an import with their reason, `…` when more."""
    text = "; ".join(
        _("line {line}: {reason}").format(line=n, reason=why) for n, why in lines[:PREVIEW]
    )
    return text + ("…" if len(lines) > PREVIEW else "")


def said[V](rows: Sequence[Mapping[str, V]], headers: Mapping[str, str]) -> list[dict[str, V]]:
    """Rows of a table with their columns in words (`headers`: each English id with its message)."""
    return [{_(headers[k]): v for k, v in row.items()} for row in rows]
