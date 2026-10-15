"""The edits of a grid in the state of its `st.data_editor`: read as the edits of the rows of a file
(`edits_from_state`), the cells of a nested model merged into its mapping, and carried over a new
grid, which Streamlit draws when `All columns` turns or the language switches (`carry`, `fold`,
`grid_state`): the new grid shows them in its rows (`frame`, `applied`)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from dagobert.store import Merge, RowEdits
from dagobert.ui.gridcolumns import Column, Row

DRAWN = "ui-grids"  # session state: the editors drawn so far with their rows, see `drawn`


def _merge(key: str, cells: Row, holder: Mapping[str, Any]) -> Row:
    """`{key: Merge(cells)}`: the edited entries go into the mapping `key`, the others stay. A
    cleared entry that `holder`, the mapping now, lacks is left out, so a new row gets none."""
    kept = {k: v for k, v in cells.items() if v is not None or k in holder}
    return {key: Merge(kept)} if kept else {}


def _mapping(parts: list[Column], changes: dict[str, Any], holder: Row) -> Row:
    """The changes of the mapping `key` from the cells of one row. A gated mapping (`factor` per
    phase) goes whole with its gate list, from all its cells: 1 is never written, 0 leaves the
    entry out of the gate. Any other takes the edited entries (`_merge`)."""
    key, gate = parts[0].key, parts[0].gate
    if gate is None:
        edited = {str(c.part): c.stored(changes[c.name]) for c in parts if c.name in changes}
        return _merge(key, edited, holder.get(key) or {})
    cells = {
        str(c.part): c.stored(changes[c.name]) if c.name in changes else c.entry(holder)
        for c in parts
    }
    entries = {**(holder.get(key) or {}), **cells}
    off = [p for p, v in cells.items() if v == 0]
    return {
        key: {p: v for p, v in entries.items() if v is not None and v not in (0, 1)} or None,
        gate: [p for p in cells if p not in off] if off else None,
    }


def _stored(cols: list[Column], changes: dict[str, Any], holder: Row) -> Row:
    """The edited cells of one mapping (a row, or the nested mapping of a lifted model) as
    saved: a value per field, the changes of a mapping per field with entries."""
    by_name = {c.name: c for c in cols}
    out: Row = {
        by_name[name].key: by_name[name].stored(value)
        for name, value in changes.items()
        if by_name[name].part is None
    }
    for key in dict.fromkeys(by_name[n].key for n in changes if by_name[n].part is not None):
        out |= _mapping([c for c in cols if c.key == key and c.part is not None], changes, holder)
    return out


def edits_from_state(
    state: dict[str, Any], cols: list[Column], shown: list[tuple[int, Row]], fixed: Row
) -> RowEdits:
    """Translate the `st.data_editor` state. `shown` holds file index and row per table row. The
    cells of a nested or a lifted model (`Column.inner`) merge into its mapping (`Merge`): the
    comment lines inside it stay."""
    by_name = {c.name: c for c in cols}

    def stored(changes: dict[str, Any], row: Row) -> Row:
        known = {name: value for name, value in changes.items() if name in by_name}
        out: Row = {}
        for inner in dict.fromkeys(by_name[name].inner for name in known):
            holder = (row.get(inner) or {}) if inner else row
            cells = _stored(
                [c for c in cols if c.inner == inner],
                {n: v for n, v in known.items() if by_name[n].inner == inner},
                holder,
            )
            out |= cells if inner is None else _merge(inner, cells, holder)
        return out

    return RowEdits(
        edited={
            shown[int(i)][0]: stored(changes, shown[int(i)][1])
            for i, changes in state.get("edited_rows", {}).items()
        },
        added=[
            fixed | new
            for new in (stored(row, {}) for row in state.get("added_rows", []))
            # a blank row carries nothing but column defaults
            if any(v is not None for v in new.values())
        ],
        deleted=[shown[i][0] for i in state.get("deleted_rows", [])],
    )


def applied(cells: list[Row], state: Mapping[str, Any]) -> list[Row]:
    """The cells of a grid after the edits `state` of its editor, in the order of the grid: the
    rows that stay, then the new ones."""
    deleted = {int(i) for i in state.get("deleted_rows", [])}
    edited = {int(i): changes for i, changes in state.get("edited_rows", {}).items()}
    return [row | edited.get(i, {}) for i, row in enumerate(cells) if i not in deleted] + [
        dict(new) for new in state.get("added_rows", [])
    ]


def fold(carried: Mapping[str, Any], state: Mapping[str, Any], count: int) -> dict[str, Any]:
    """One editor state of a grid of `count` rows from the edits `carried` and the edits `state`
    of a grid that showed them in its rows (`applied`): `All columns` draws a new grid."""
    deleted = {int(i) for i in carried.get("deleted_rows", [])}
    edited = {int(i): dict(changes) for i, changes in carried.get("edited_rows", {}).items()}
    added = [dict(new) for new in carried.get("added_rows", [])]
    # the row of the first grid that each row of the second shows, a new one as -1 - its place
    places = [i for i in range(count) if i not in deleted] + [-1 - k for k in range(len(added))]
    for i, changes in state.get("edited_rows", {}).items():
        at = places[int(i)]
        (edited.setdefault(at, {}) if at >= 0 else added[-1 - at]).update(changes)
    dropped = {places[int(i)] for i in state.get("deleted_rows", [])}
    deleted |= {at for at in dropped if at >= 0}
    return {
        "edited_rows": {i: changes for i, changes in edited.items() if i not in deleted},
        "added_rows": [new for k, new in enumerate(added) if -1 - k not in dropped]
        + list(state.get("added_rows", [])),
        "deleted_rows": sorted(deleted),
    }


def grid_state(widget: str, count: int) -> dict[str, Any]:
    """The edits of the grid `widget` of `count` rows: those carried over a new grid (`carry`) and
    those of its editor."""
    return fold(
        st.session_state.get(f"carried-{widget}", {}), st.session_state.get(widget) or {}, count
    )


def carry(grids: Mapping[str, int]) -> None:
    """Before a run that turns `All columns` or switches the language: the grids then take other
    columns or other words, so Streamlit draws new ones and would drop the edits. They move from
    each editor to `carried-<grid>`, which the new grid shows in its rows and `grid_state` adds to
    its own edits."""
    for widget, count in grids.items():
        st.session_state[f"carried-{widget}"] = grid_state(widget, count)
        if widget in st.session_state:
            del st.session_state[widget]


def drawn(grids: Mapping[str, int]) -> None:
    """Note the editors of this run with their rows: a switch of the language carries their
    edits (`ui.language_switch`)."""
    st.session_state.setdefault(DRAWN, {}).update(grids)


def frame(
    cols: list[Column], rows: list[Row], carried: Mapping[str, Any] | None = None
) -> pd.DataFrame:
    """The cells of a grid, with the edits `carried` over a turn of `All columns` (`applied`). A
    number column is a float column: of whole numbers only, it would become an integer column,
    whose editor drops the decimal mark (`100,5` m² read 1005)."""
    cells = applied([{c.name: c.shown(row) for c in cols} for row in rows], carried or {})
    return pd.DataFrame(
        {
            c.name: pd.Series(
                [cell.get(c.name) for cell in cells], dtype=float if c.type == "number" else object
            )
            for c in cols
        }
    )


def touched(state: object) -> bool:
    """Whether the widget state of a grid holds edits, also a blank new row."""
    return isinstance(state, Mapping) and any(
        state.get(k) for k in ("edited_rows", "added_rows", "deleted_rows")
    )
