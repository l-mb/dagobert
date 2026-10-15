"""The save guard: what a Save writes, money with cents, and a warning for a number that looks
off.

A number cell of a grid reads `,` and `.` by the language of the browser: `-20,50` becomes
-2.050 in an English one, `131.500` becomes 131,5 in a German one. The grid shows whole euros,
so only this list shows such an entry before it is written. The list sits below its grid, so a
new warning also shows once as a toast, and the Save button carries `MARK` while one lasts. Each
number shows in the unit of its field (`model.base.units`): euros with cents, a share or a rate in
percent as the grids take it, the file keeps the fraction."""

from __future__ import annotations

import dataclasses
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeIs

import streamlit as st

from dagobert.i18n import N_, _, ngettext
from dagobert.model.base import Unit
from dagobert.money import format_eur
from dagobert.store import NULL, Merge, RowEdits
from dagobert.ui import literal
from dagobert.ui.gridcolumns import Row

LOW, HIGH = 0.5, 2.0  # a new number outside these times the old one gets a warning
MARK = " ⚠"  # on the label of a Save button while a change has a warning
LOCALE = N_("A number cell reads `,` and `.` by the language of the browser")
NAMES = ("name", "id", "security", "asset", "loan", "policy")  # what names a row, in this order
# a rate above 100% by law, the Gewerbesteuer-Hebesatz of 200% or more, and the factors of the
# spending rule that rise above it: its increase and its ceiling
ABOVE_ONE = ("hebesatz", "increase", "ceiling")
Cell = float | str | None  # a number, text, or nothing


@dataclass(frozen=True)
class Change:
    """One cell to save. `old` is None for a new row or an empty cell, `new` for a cleared
    cell. `label` says it in the language of the session, `key` names it in English, where a
    caller tells the field by its key path or its column (`assumptions.hint`); empty, the
    label is the key."""

    label: str
    old: Cell
    new: Cell
    unit: Unit | None = Unit.EUR  # of a number: euros with cents, percent of a fraction, plain
    outflow: bool = False  # negative as spending is: a number above zero gets a warning
    ratio: bool = True  # a sign change or a jump gets a warning
    capped: bool = True  # a percent above 100% gets a warning: a share or a rate, not a factor
    # nor a field of `ABOVE_ONE`: the caller knows the field, the label may be words
    added: bool = False  # of a new row: the value alone, as nothing stands before it
    key: str = dataclasses.field(default="", compare=False)

    @property
    def named(self) -> str:
        """The key of the cell in English: `returns equity mean`."""
        return self.key or self.label

    @property
    def warning(self) -> str | None:
        """A number above zero for an outflow, above 100% for a share or a rate, or a number set
        to zero, of another sign or outside `LOW` to `HIGH` times the old one, in the language of
        the session."""
        if self.outflow and _is_number(self.new) and self.new > 0:
            return _("above zero, which records a refund")
        if self.capped and self.unit is Unit.PERCENT and _is_number(self.new) and self.new > 1:
            return _("above 100%")
        if not (self.ratio and _is_number(self.old) and _is_number(self.new) and self.old):
            return None
        if not self.new:
            return _("set to zero")
        if self.old * self.new < 0:
            return _("the sign changed")
        ratio = self.new / self.old
        return None if LOW <= ratio <= HIGH else _times(ratio)

    def _shown(self, value: Cell) -> str:
        if not _is_number(value):
            return _("empty") if value is None else literal(value)
        match self.unit:
            case Unit.EUR:
                return format_eur(value, cents=True)
            case Unit.PERCENT:
                return f"{value * 100:.10g}%"
            case _:
                return f"{value:.10g}"

    @property
    def text(self) -> str:
        if self.added:
            return f"**{literal(self.label)}** {self._shown(self.new)}"
        return f"**{literal(self.label)}** {self._shown(self.old)} → {self._shown(self.new)}"


def _times(ratio: float) -> str:
    """A jump in words, without an exponent: `1000 times`, `0.49 times`, `1/1004` of the old
    value."""
    if ratio < 0.01:
        return _("1/{n} of the old value").format(n=f"{1 / ratio:.0f}")
    return _("{n} times the old value").format(n=f"{ratio:{'.0f' if ratio >= 100 else '.3g'}}")


def label(row: Row) -> str:
    """A row in the list: its name, else its id or security, after the date of a trade or the
    month of an event. An event without them by the asset, loan, policy, stream or property that
    it names, else by its type."""
    held = [_merged(None, row.get(k)) for k in ("stream", "property")]  # of a new row its fields
    nested = [h.get("name") or h.get("id") for h in held if isinstance(h, dict)]
    named = next((row[k] for k in NAMES if isinstance(row.get(k), str) and row[k]), None)
    named = named or next(filter(None, nested), None)
    at = row.get("at")
    when = row.get("date") or (f"{at:%Y-%m}" if isinstance(at, date) else at)
    return " ".join(str(part) for part in (when, named or row.get("type")) if part)


def _is_number(value: Cell) -> TypeIs[float]:
    return isinstance(value, int | float)


def cell(  # noqa: PLR0911 one return per kind
    value: object, unit: Unit | None = None, *, empty: object = None, null: object = NULL
) -> Cell:
    """A value as a cell: `empty` is no cell, `null` shows as `null`. A form file reads a YAML
    null as `None` and a missing key as `ABSENT`, a grid row the other way round."""
    match value:
        case _ if value is empty:
            return None
        case _ if value is null:
            return "null"
        case bool():
            return str(value).lower()
        case int() | float():
            return float(value)
        case date():
            return f"{value:%Y-%m}" if unit is Unit.MONTH else value.isoformat()
        case list():
            return _items(value)
        case _:
            return str(value)


def _items(value: list[object]) -> str:
    """A list as a cell: its items, or how many rows a list of mappings holds, such as the trades
    of a depot that changed elsewhere (`save.warn`)."""
    if value and all(isinstance(item, dict) for item in value):
        return ngettext("{n} row", "{n} rows", len(value)).format(n=len(value))
    return f"[{', '.join(map(str, value))}]"


def _cells(
    key: str, old: object, new: object, units: Mapping[str, Unit]
) -> Iterator[tuple[str, Cell, Cell]]:
    """A cell before and after, one per entry of a mapping (`factor` per phase, the fields of a
    nested model), named by its key path, a month as `2027-05`."""
    new = _merged(old, new)
    if isinstance(old, dict) or isinstance(new, dict):
        before, after = (v if isinstance(v, dict) else {} for v in (old, new))
        for part in dict.fromkeys([*before, *after]):
            yield from _cells(f"{key} {part}", before.get(part), after.get(part), units)
    else:
        yield key, cell(old, units.get(key)), cell(new, units.get(key))


def _merged(old: object, new: object) -> object:
    """A `Merge` as the mapping that it leaves, entry by entry; any other value as it is."""
    if not isinstance(new, Merge):
        return new
    out = dict(old) if isinstance(old, dict) else {}
    for key, value in new.changes.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = _merged(out.get(key), value)
    return out


def _row(
    row: Row,
    named: Row,
    cells: Row,
    units: Mapping[str, Unit],
    names: Mapping[str, str],
    *,
    made: Collection[str],
) -> list[Change]:
    """The changed cells of one row, of a new row (`row` empty) its numbers and the cells of
    `made`. `asof` comes with every new value (`save.stamp`), so a row with a changed amount
    leaves it out."""
    found = [
        (
            key,
            Change(
                f"{label(named)} {names.get(name, name)}".strip(),
                old,
                new,
                units.get(name),
                capped=name.split()[-1] not in ABOVE_ONE,
                key=f"{label(named)} {name}".strip(),
            ),
        )
        for key, value in cells.items()
        for name, old, new in _cells(key, row.get(key), value, units)
        if old != new and (row or _is_number(new) or name in made)
    ]
    money = any(c.unit is Unit.EUR for _key, c in found)
    return [c for key, c in found if not (money and key == "asof")]


def changes(
    rows: list[Row],
    edits: RowEdits,
    order: Sequence[int] = (),
    *,
    units: Mapping[str, Unit],
    names: Mapping[str, str] | None = None,
    made: Collection[str] = (),
) -> list[Change]:
    """The cells that `edits` changes, the edited rows in the order of the grid (`order`, file
    indices) or else of the file, then the numbers of the new rows: their label names them.
    `units` gives the unit of a cell by its name (`gridcolumns.units`), `names` how a line names
    it (`gridcolumns.names`; without one, by its name). `made` names the cells that a table
    makes for a new row (`Table.derived`: the ids of a purchase), which a new row lists too: the
    grid shows none of them before the save."""
    touched = [
        *((rows[i], rows[i], edits.edited[i]) for i in _ordered(edits.edited, order, len(rows))),
        *(({}, new, new) for new in edits.added),
    ]
    return [
        c
        for row, named, cells in touched
        for c in _row(row, named, cells, units, names or {}, made=made)
    ]


def review(
    found: list[Change],
    removed: Iterable[str] = (),
    *,
    key: str,
    notes: Sequence[str] = (),
    hint: str | None = None,
) -> bool:
    """The cells to save, money with cents, and a warning for the numbers that look off. Saving
    stays possible: a big change is sometimes real, for example after a sale. `notes` are
    warnings of no single cell, such as an imported price far from the price of a trade that
    day. `hint` ends the warning, by default the reading of number cells by the language of the
    browser (`LOCALE`; a message of the catalogue, said in the language of the session). A
    warning that is new to the list `key` also shows once as a toast. Returns whether there is a
    warning."""
    flagged = [c for c in found if c.warning]
    warnings = [f"{c.text}, {c.warning}" for c in flagged] + list(notes)
    if hint is None:
        hint = LOCALE if flagged else ""
    if warnings:
        text = (
            _("Check before you save: {warnings}. {hint}.")
            if hint
            else _("Check before you save: {warnings}.")
        )
        st.warning(
            text.format(warnings="; ".join(warnings), hint=_(hint) if hint else ""),
            icon=":material/warning:",
        )
    listing(found, removed)
    shown = f"guard-{key}"  # the warnings of the last run: a rerun does not repeat a toast
    if new := [w for w in warnings if w not in st.session_state.get(shown, ())]:
        st.toast(
            _("Check before you save: {warnings}").format(warnings="; ".join(new)),
            icon=":material/warning:",
            duration="long",
        )
    st.session_state[shown] = warnings
    return bool(warnings)


def listing(found: list[Change], removed: Iterable[str] = (), *, title: str | None = None) -> None:
    """The cells of `found` and the rows `removed` as a caption under `title`, `To save` without
    one: what a save writes, or what changed elsewhere since a grid was drawn."""
    lines = [c.text for c in found] + [
        _("{name} removed").format(name=f"**{literal(name)}**") for name in removed
    ]
    if lines:
        st.caption(f"{title or _('To save')}:  \n" + "  \n".join(lines))


def check(
    rows: list[Row],
    edits: RowEdits,
    order: Sequence[int] = (),
    *,
    key: str,
    units: Mapping[str, Unit],
    names: Mapping[str, str] | None = None,
    made: Collection[str] = (),
    notes: Sequence[str] = (),
) -> bool:
    """`review` of the edits of a row file, in the order of the grid."""
    removed = [label(rows[i]) for i in _ordered(edits.deleted, order, len(rows))]
    found = changes(rows, edits, order, units=units, names=names, made=made)
    return review(found, removed, key=key, notes=notes)


def _ordered(indices: Iterable[int], order: Sequence[int], rows: int) -> list[int]:
    """File indices in the order of the grid, else of the file."""
    rank = {i: n for n, i in enumerate(order or range(rows))}
    return sorted(indices, key=rank.__getitem__)


def marked(label: str, flagged: bool) -> str:
    """The label of a Save button, with `MARK` while a change has a warning."""
    return label + MARK if flagged else label
