"""What a form changes, in the lines of the save guard (`changes`): one `guard.Change` per field
labeled by its key path, each key as the pages name it, or by the words of a new row; a cell of a
list of rows or a field of an entry of a mapping by name each, in the unit of its field."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from itertools import zip_longest
from typing import Any

from dagobert.i18n import _
from dagobert.model.base import KeyPath, Unit
from dagobert.store import RowEdits
from dagobert.ui import guard
from dagobert.ui.fields import ABSENT, Field, Kind, dicts, lookup
from dagobert.ui.gridcolumns import Column, keyword, keywords
from dagobert.ui.widgets import same


def _state(mapping: Mapping[str, Any], section: KeyPath, *, override: bool) -> str | None:
    held = lookup(mapping, section)
    if isinstance(held, dict):
        return "on"
    return None if held is ABSENT and override else "off"


def _cell(value: object, unit: Unit | None = None) -> guard.Cell:
    return guard.cell(value, unit, empty=ABSENT, null=None)


def changes(
    old: Mapping[str, Any],
    new: Mapping[str, Any],
    found: Sequence[Field],
    *,
    override: bool = False,
    rows: Mapping[KeyPath, RowEdits] | None = None,
    term: Callable[[Field], str] | None = None,
) -> list[guard.Change]:
    """What `new` changes of `old`, one `guard.Change` per field labeled by its key path (`returns
    equity mean`, each key as the pages name it, `gridcolumns.keyword`; its `key` the key path),
    or by `term` (the words of a new row: `Loan · Rate`, `Change.added`), in the unit of the field.
    An optional section shows `on` or `off` (empty while an override inherits it), its fields only
    while it is on. A list of rows shows per cell, by the `rows` edits of a list of the file (a
    deleted row empties its cells, a new one numbers after the last), else by position; a mapping
    by name per entry and field."""
    out: list[guard.Change] = []
    for field in found:
        key = " ".join(field.path)
        label = term(field) if term else _path(field)
        before, after = lookup(old, field.path), lookup(new, field.path)
        if field.kind is Kind.SECTION:
            was, now = (_state(m, field.path, override=override) for m in (old, new))
            if was != now:
                out.append(guard.Change(label, _said(was), _said(now), unit=None, key=key))
        elif field.section is not None and _state(new, field.section, override=override) == "off":
            continue
        elif field.kind is Kind.ROWS:
            edited = (rows or {}).get(field.path)
            pairs = _edited(before, edited) if edited else None
            out += _cells((key, label), pairs or _positional(before, after), field.columns)
        elif field.kind is Kind.MAP:
            out += _cells((key, label), _entries(field, before, after), field.columns)
        elif not same(before, after):
            cells = _cell(before, field.unit), _cell(after, field.unit)
            out.append(
                guard.Change(
                    label,
                    *cells,
                    unit=field.unit,
                    capped=field.path[-1] not in guard.ABOVE_ONE,
                    added=term is not None,
                    key=key,
                )
            )
    return out


def _path(field: Field) -> str:
    """A field in a line of the save guard: its key path, each key as the pages name it, the name
    of an entry as written (`scale salary work`)."""
    *keys, last = field.path
    return " ".join([*map(keyword, keys), last if field.entry else keyword(last)])


def _said(state: str | None) -> str | None:
    """`on` or `off` of a section in the language of the session."""
    return {"on": _("on"), "off": _("off")}.get(state or "")


Pair = tuple[str, Mapping[str, Any], Mapping[str, Any]]  # a row or an entry before and after


def _positional(old: object, new: object) -> list[Pair]:
    return [
        (str(i + 1), was or {}, now or {})
        for i, (was, now) in enumerate(zip_longest(dicts(old), dicts(new)))
    ]


def _edited(old: object, edits: RowEdits) -> list[Pair]:
    """The rows of a list of the file before and after `edits`, numbered as the file holds them,
    a new row after the last."""
    before = dicts(old)
    after = edits.result(before)
    kept = [i for i in range(len(before)) if i not in edits.deleted]
    return [
        *((str(i + 1), before[i], after[n]) for n, i in enumerate(kept)),
        *((str(len(before) + n + 1), {}, row) for n, row in enumerate(after[len(kept) :])),
        *((str(i + 1), before[i], {}) for i in sorted(set(edits.deleted))),
    ]


def _entries(field: Field, old: object, new: object) -> list[Pair]:
    """The entries of a mapping by name before and after, a number under `value`."""
    before, after = (m if isinstance(m, dict) else {} for m in (old, new))
    scalar = [c.name for c in field.columns] == ["value"]

    def row(entry: object) -> Mapping[str, Any]:
        if entry is ABSENT:
            return {}
        return {"value": entry} if scalar else entry if isinstance(entry, dict) else {}

    return [
        (str(name), row(before.get(name, ABSENT)), row(after.get(name, ABSENT)))
        for name in dict.fromkeys([*before, *after])
    ]


def _cells(
    path: tuple[str, str], pairs: Iterable[Pair], cols: Sequence[Column]
) -> Iterator[guard.Change]:
    """The changed cells of rows or entries, labeled `<path> <row> <column>`: `path` is the key
    path of the list and its label."""
    head, shown = path
    for name, was, now in pairs:
        for col in cols:
            at = (col.key, col.part) if col.part else (col.key,)
            before, after = lookup(was, at), lookup(now, at)
            if not same(before, after):
                key, label = (
                    (f"{head} {name}", f"{shown} {name}")
                    if col.name == "value"
                    else (f"{head} {name} {col.name}", f"{shown} {name} {keywords(col.name)}")
                )
                capped = at[-1] not in guard.ABOVE_ONE
                yield guard.Change(
                    label,
                    _cell(before, col.unit),
                    _cell(after, col.unit),
                    unit=col.unit,
                    capped=capped,
                    key=key,
                )
