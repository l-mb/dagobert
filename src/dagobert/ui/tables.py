"""The `Table` spec and `edit_table` of every editable grid (assets, streams, events, overrides,
trades), `small_grid` of the forms, and their shared helpers: pinning, column help, Save in the
header, the references of the selects. A `Table` is drawn as one grid or a grid per group, its
edits (`gridstate`) saved through the save guard. The columns come from the model
(`gridcolumns`), their options from the names that exist in the inputs (`references`)."""

from __future__ import annotations

import colorsys
import html
import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import streamlit as st
from pydantic import BaseModel
from streamlit.elements.lib.column_types import ColumnConfig

from dagobert import references, revisions
from dagobert.i18n import N_, _
from dagobert.model.base import KeyPath, Unit
from dagobert.references import Kind, References, Site
from dagobert.store import Merge, RowEdits, RowFile
from dagobert.ui import Stamp, data_stamp, guard, is_mobile, joined, literal, mode, rename, save
from dagobert.ui.gridcolumns import (
    WIDTHS,
    Column,
    Row,
    columns,
    key_paths,
    keyword,
    keywords,
    names,
    number,
    units,
)
from dagobert.ui.gridstate import carry, drawn, edits_from_state, frame, grid_state, touched

COLUMNS_HELP = N_("Columns")  # the label of the popover of the column help, see `column_help`
COLUMNS_MEAN = N_("What the columns mean")  # the same where the columns need more words
LOCKED_HELP = N_("Stays once saved: other inputs name the row by it.")
RENAME_HELP = N_("`Rename` above the table changes it there too.")
IN_FILE = N_("In the file: {name}.")  # after the help of a column with a header in words
ROW_MARKER = 33  # pixels of the checkbox column that a dynamic `st.data_editor` puts first
# pixels of the pinned name of a block grid on a phone: at 200 a single column fits beside it
PHONE_PINNED = 120
FIRST_COLUMNS = (
    "id",
    "security",
    "name",
    "cat",
    "kind",
    "amount",
    "gross",
    "value",
    "balance",
    "start",
    "end",
)


_NONE = object()  # what `_at` finds where a row holds no value


def _at(cells: Mapping[str, Any], path: KeyPath, default: object = None) -> Any:  # noqa: ANN401 a cell
    """The value at `path` of a row or of its edited cells, through the `Merge` of a nested
    model, else `default`."""
    value: Any = cells
    for key in path:
        value = value.changes if isinstance(value, Merge) else value
        if not isinstance(value, Mapping) or key not in value:
            return default
        value = value[key]
    return value


def _with(cells: Row, path: KeyPath, value: object) -> Row:
    """The edited `cells` with `value` at `path`, inside the `Merge` of a nested model."""
    key, *inner = path
    if not inner:
        return {**cells, key: value}
    held = cells.get(key)
    return {
        **cells,
        key: Merge(_with(held.changes if isinstance(held, Merge) else {}, tuple(inner), value)),
    }


def _plain(cells: Mapping[str, Any]) -> dict[str, Any]:
    """The edited `cells` as the file would hold them: a `Merge` as its mapping."""
    return {k: _plain(v.changes) if isinstance(v, Merge) else v for k, v in cells.items()}


def _without(cells: Row, path: KeyPath) -> Row:
    """The edited `cells` without the one at `path`; a `Merge` that it leaves empty goes too."""
    key, *inner = path
    held = cells[key]
    rest = _without(held.changes, tuple(inner)) if inner and isinstance(held, Merge) else {}
    return {k: Merge(rest) if k == key else v for k, v in cells.items() if k != key or rest}


# Pins the Save button of the visible table into the page header, left of the Streamlit menu.
# Up to 768 px the open sidebar overlays the page, and its close button lies under Save: Save
# hides then. In portrait it moves beside the button that opens the sidebar: the status widget
# of a run would lie under it next to the menu.
SAVE_IN_HEADER = (
    "<style>.{0} {{position: fixed; top: 0.6rem; right: 9rem; z-index: 1000000; width: auto}}"
    "@media (max-width: 768px) {{.stApp:has([data-testid=stSidebar][aria-expanded=true]) .{0} "
    "{{visibility: hidden}}}}"
    "@media (max-width: 640px) {{.{0} {{left: 4.5rem; right: auto}}}}</style>"
)
GATE_HELP = N_(
    "Multiplier in the {phase} phase. 0 means the stream does not apply, empty counts as 1."
)


@dataclass(frozen=True)
class Ref:
    """The options of a column: the names of `kind` that count in the file of the grid
    (`References.names`), of the asset or stream kinds `sorts` only. `new` takes a name that is
    not there yet, where a new one is legal (a tag). `unless` leaves out the `name` of a row of
    the grid's file that holds this field: a bonus (`of`) is no base of another. `without` leaves
    out names whatever the file of the grid holds, such as the bonuses of another file."""

    kind: Kind
    sorts: tuple[str, ...] = ()
    new: bool = False
    unless: str | None = None
    without: frozenset[str] = frozenset()

    def names(self, refs: References, scenario: str | None) -> tuple[str, ...]:
        """The names of `kind` that count in the scenario file `scenario`, less `without`."""
        found = refs.names(self.kind, scenario, sorts=self.sorts)
        return tuple(name for name in found if name not in self.without)


@dataclass(frozen=True)
class Focus:
    """The row of a grid that a link opened, by the values of its `Table.identity`: first in the
    grid, the headers of `fields` marked and a line above it that names the row and them, until a
    save changes the row (`digest`: the row when the link came). Streamlit 1.65 styles no editable
    cell, so the grid cannot mark the cells themselves."""

    row: tuple[object, ...]
    fields: tuple[str, ...]
    digest: str


FOCUS_MARK = "⚠ "  # before the header of a column of a `Focus`


@dataclass(frozen=True)
class Table:
    """What one editable table shows of a `RowFile`."""

    model: type[BaseModel]
    key: str
    # the fields that name a row (`store.keyed`): a save finds the rows that it edits by them in
    # the file as it is then, not by their place
    identity: tuple[str, ...]
    fixed: Row = field(default_factory=dict)  # filters the rows and is set on new ones
    match: Callable[[Row], bool] | None = None  # row filter instead of `fixed`
    fields: tuple[str, ...] = ()  # YAML keys to show, in this order; empty shows all
    more: tuple[str, ...] = ()  # rarely used keys behind the "All columns" toggle
    # mapping field to the list field it absorbs: `factor` cells also say which `phases` apply
    gates: dict[str, str] = field(default_factory=dict)
    # a mapping field to the names of its number columns with their headers: `factor` per phase.
    # A mapping field without them shows no column
    entries: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    sort_by: tuple[str, ...] = ()
    pinned: tuple[str, ...] = ()  # columns that stay in view on a phone, see `pin`
    lead: tuple[str, ...] = ()  # on a phone right after the pinned columns, see `phone_order`
    negative: tuple[str, ...] = ()  # columns saved negative whatever sign is typed, see `signed`
    # columns of `negative` shown without their minus, whose header names the direction: the loan
    # of a purchase (rule `money`)
    unsigned: tuple[str, ...] = ()
    # one editor per value of this key, under a colored heading: the grid cannot shade rows
    group_by: str | None = None
    # bold row under each grouped grid: column name to text, from the rows of the group and
    # all rows of the file, both with the unsaved edits
    totals: Callable[[list[Row], list[Row]], dict[str, str]] | None = None
    # maps the rows after the edit to changes of the mapping that holds them
    parent: Callable[[list[Row]], Row] | None = None
    track: bool = False  # date new asset values with today and log them in the history
    inner: str | None = None  # a nested model whose fields take a column each, see `columns`
    options: Mapping[str, Ref] = field(default_factory=dict)  # reference selects by column name
    locked: tuple[str, ...] = ()  # columns that keep their value in a saved row, see `held`
    # the kind of the names of the `locked` columns: `Rename` beside the grid (`ui.rename`)
    rename: Kind | None = None
    num_rows: Literal["dynamic", "add"] = "dynamic"  # `add`: no row can go
    # warnings of no single cell about the edited and added rows, for the save guard: a trade of
    # gold whose price lies far from the gold series
    check: Callable[[list[Row]], list[str]] | None = None
    # readable headers by column name (`Column.label`), English (`Column.header` says them): the
    # cells, the edits and the guard keep the name of the field
    titles: Mapping[str, str] = field(default_factory=dict)
    # the help of a column by its name where the schema says another default: a savings plan
    # without `index` is nominal, the field default `cpi`
    helps: Mapping[str, str] = field(default_factory=dict)
    help_label: str = COLUMNS_HELP  # the popover of the column help on a phone, see `column_help`
    # what a new row takes from its other cells where it lacks the cell at a key path, as the form
    # of the rows does (`forms.Form.derived`): the ids of a purchase, `locked` columns, which
    # Streamlit disables for a new row too
    derived: Mapping[KeyPath, Callable[[Mapping[str, Any]], object]] = field(default_factory=dict)
    focus: Focus | None = None  # the row that a link opened, see `focus`; `edit_table` sets it
    # the grid of `mode` that names its columns (`assets`, `streams`): a column that the mode or a
    # feature hides goes behind `All columns`, an option of a select that they hide goes
    grid: str | None = None
    # what a new row starts with (`starts`): in the columns of `common` (by key or name) the cell
    # that most rows of its grid hold, the kind of a stream and its factor per phase; in a table
    # without rows the cells of `first` by column name
    common: tuple[str, ...] = ()
    first: Mapping[str, str | float] = field(default_factory=dict)

    def keeps(self, row: Row) -> bool:
        return (
            self.match(row) if self.match else all(row.get(k) == v for k, v in self.fixed.items())
        )

    def part(self, rows: list[Row]) -> list[Row]:
        """The rows of the grid, in its order."""
        return [rows[i] for i in self.indices(rows)]

    def signed(self, row: Row, cells: Row) -> Row:
        """The edited `cells` of `row` as saved: a column of `negative` turns negative while the
        row stays in the table (`save.signed`). A column that the model lacks is none: the asset
        tables share `negative`, a loan's `balance`."""
        paths = key_paths(self.model, self.inner)
        return (
            save.signed(cells, [paths[name] for name in self.negative if name in paths])
            if self.keeps(row | cells)
            else cells
        )

    def filled(self, new: Row) -> Row:
        """The cells of the `new` row with the `derived` values of those that it lacks."""
        for path, derive in self.derived.items():
            if _at(new, path, _NONE) is _NONE and (value := derive(_plain(new))) is not None:
                new = _with(new, path, value)
        return new

    @property
    def made(self) -> list[str]:
        """The cells of `derived` as the guard names them, which it lists in a new row."""
        return [" ".join(path) for path in self.derived]

    def held(self, row: Row, cells: Row) -> tuple[Row, list[str]]:
        """The edited `cells` of the saved `row` without a change of a `locked` column, and each
        such change in words: other inputs and the history name the row by it, so `rename` changes
        it with them."""
        paths = key_paths(self.model, self.inner)
        moved = {
            name: path
            for name in self.locked
            if (new := _at(cells, path := paths[name], _NONE)) is not _NONE
            and new != _at(row, path)
        }
        kept = cells
        for path in moved.values():
            kept = _without(kept, path)
        return kept, [
            _("{row} keeps its {field} {old}, {new} is not saved").format(
                row=f"**{literal(guard.label(row))}**",
                field=keywords(name),
                old=literal(str(_at(row, path))),
                new=_("empty") if (new := _at(cells, path)) is None else literal(str(new)),
            )
            for name, path in moved.items()
        ]

    def identified(self, row: Row) -> tuple[object, ...]:
        """The values of `identity` in `row`."""
        return tuple(row.get(k) for k in self.identity)

    def indices(self, rows: list[Row]) -> list[int]:
        """The rows of the grid by `sort_by`, the row of `focus` first."""
        first = self.focus.row if self.focus else None
        shown = [i for i, row in enumerate(rows) if self.keeps(row)]
        return sorted(
            shown,
            key=lambda i: (
                self.identified(rows[i]) != first,
                [str(rows[i].get(k, "")).lower() for k in self.sort_by],
            ),
        )

    def columns(self, *, everything: bool = False, hidden: Collection[str] = ()) -> list[Column]:
        """The columns of the grid: `fields` in their order, else every field with
        `FIRST_COLUMNS` first; those of `more` and of `hidden` (by the mode or a feature) only
        with `everything`."""
        skip = frozenset(self.fixed) | set(self.gates.values())
        cols = [
            self._column(c)
            for col in columns(self.model, skip, lift=self.inner)
            for c in (col.entries(self.entries.get(col.key, {})) if col.type == "object" else [col])
        ]
        if self.fields:  # a field by its key, a field of a nested model also by its column
            names = self.fields + self.more
            found = [c for name in names for c in cols if name in (c.key, c.name)]
        else:
            found = sorted(cols, key=lambda c: c.name not in FIRST_COLUMNS)
        rare = () if everything else (*self.more, *hidden)
        return [c for c in found if c.key not in rare and c.name not in rare]

    def _column(self, col: Column) -> Column:
        """`col` with the rules of the table: its help, its title, whose help names the key of the
        file, the gate of its entries, no bounds for a
        field that is saved negative (a bound would turn a number typed without the minus into
        it) unless it shows without its minus (then no minus), the help of a locked field, which
        names `Rename` where the table has it."""
        if col.name in self.helps:
            col = replace(col, about=self.helps[col.name], named=None, more=())
        if (title := self.titles.get(col.name, col.name)) != col.name:
            col = replace(col, label=title, more=(*col.more, IN_FILE))
        if col.key in self.gates:
            col = replace(col, gate=self.gates[col.key], about=GATE_HELP, named=None, more=())
        if col.name in self.negative:
            unsigned = col.name in self.unsigned
            col = replace(col, bounds=(0 if unsigned else None, None), unsigned=unsigned)
        if col.name in self.locked:
            locked = (LOCKED_HELP,) if self.rename is None else (LOCKED_HELP, RENAME_HELP)
            col = replace(col, more=(*col.more, *locked))
        return col

    def units(self) -> dict[str, Unit]:
        """The units of all columns, also those behind `All columns`, for the save guard."""
        return units(self.columns(everything=True))

    def names(self) -> dict[str, str]:
        """How the save guard names each cell, also of the columns behind `All columns` and of the
        list that a gate fills (`phases`), in the language of the session."""
        return names(self.columns(everything=True)) | {g: keyword(g) for g in self.gates.values()}

    def referenced(
        self, cols: list[Column], refs: References, scenario: str | None, rows: list[Row]
    ) -> list[Column]:
        """`cols` with the options of `options`: the names that count in the scenario file
        `scenario`, else everywhere, less those that `Ref.unless` leaves out of `rows`. The options
        are the same in every row: a row cannot leave out itself."""

        def names(ref: Ref) -> tuple[str, ...]:
            out = {str(row.get("name")) for row in rows if ref.unless and row.get(ref.unless)}
            return tuple(n for n in ref.names(refs, scenario) if n not in out)

        return [
            replace(c, options=names(ref), new=ref.new) if (ref := self.options.get(c.name)) else c
            for c in cols
        ]

    def starts(self, cols: list[Column], rows: list[Row]) -> list[Column]:
        """`cols` of a grid of `rows` with the cell that a new row starts with (`Column.start`): in
        the columns of `common`, in their order, the one that most of the rows like it hold, the
        rows with its cells so far (a tie: the first in the grid). So a new income takes the kind
        of most rows, then the factor per phase of most rows of that kind. Without rows the cells
        of `first`. The rows are those of the base, which stay while the grid holds edits: a new
        start would be a new editor, without them."""
        if not rows:
            return [
                replace(c, start=self.first[c.name]) if c.name in self.first else c for c in cols
            ]
        started, like = [], rows
        for col in cols:
            value = None
            if col.key in self.common or col.name in self.common:
                value = Counter(col.shown(row) for row in like).most_common(1)[0][0]
                like = [row for row in like if col.shown(row) == value]
            started.append(
                replace(col, start=value) if isinstance(value, str) or number(value) else col
            )
        return started

    def flat(self) -> Table:
        """The table of a file without its rows as one grid: no block holds a new row, so the
        column of `group_by` shows, after the first."""
        by = str(self.group_by)
        return replace(
            self,
            group_by=None,
            fields=(*self.fields[:1], by, *self.fields[1:]),
            more=tuple(m for m in self.more if m != by),
        )

    def phone_order(self, cols: list[Column]) -> list[Column]:
        """`cols` with the pinned ones first, then the fields of `focus` and `lead`: a phone shows
        few columns beside the pinned ones."""
        rank = [*self.pinned, *(self.focus.fields if self.focus else ()), *self.lead]
        return sorted(cols, key=lambda c: rank.index(c.name) if c.name in rank else len(rank))


def row_colors(values: list[str]) -> dict[str, str]:
    """One pastel per distinct value, spread over the hue circle in sorted order."""
    distinct = sorted(set(values))
    return {
        value: "#{:02x}{:02x}{:02x}".format(
            *(round(255 * c) for c in colorsys.hls_to_rgb(i / len(distinct), 0.72, 0.55))
        )
        for i, value in enumerate(distinct)
    }


def _fixed(table: Table, group: str | None) -> Row:
    """What a new row of a grid gets: the fixed fields, and in a group the value of its block."""
    if table.group_by is None or group is None:
        return dict(table.fixed)
    return table.fixed | {table.group_by: group}


@dataclass(frozen=True)
class MapRows:
    """A mapping of mappings (`returns`, `indices`) as rows with a key column, and back. A
    mapping of numbers (`scale.categories`) takes `value`, the column of the number. `lead`: the
    column that leads the grid, the key column then last and behind `All columns` (the label of a
    phase, `assumptions.LabeledRows`)."""

    key: str = "name"
    value: str | None = None
    lead: str | None = None

    def rows(self, mapping: Mapping[str, Any]) -> list[Row]:
        return [
            {self.key: name} | ({self.value: entry} if self.value else dict(entry or {}))
            for name, entry in mapping.items()
        ]

    def mapping(self, rows: Iterable[Row]) -> dict[str, Any]:
        """The rows as a mapping in their order. A row without a key goes."""
        return {
            str(row[self.key]): row.get(self.value)
            if self.value
            else {k: v for k, v in row.items() if k != self.key}
            for row in rows
            if row.get(self.key) not in (None, "")
        }


def _edits(
    table: Table, cols: list[Column], shown: list[tuple[int, Row]], widget: str, group: str | None
) -> tuple[RowEdits, list[str]]:
    """The edits of a grid from its widget state, also before the grid draws in this run, and
    the warnings of the guard: the changes of a locked field that they leave out (`Table.held`)
    and those of `Table.check` on the edited and added rows. `cols` holds every column, also
    those behind `All columns`: a cell keeps its edit while its column hides."""
    edits = edits_from_state(grid_state(widget, len(shown)), cols, shown, _fixed(table, group))
    rows = dict(shown)
    held = {i: table.held(rows[i], cells) for i, cells in edits.edited.items()}
    edits.edited = {i: table.signed(rows[i], cells) for i, (cells, _notes) in held.items() if cells}
    edits.added = [table.signed({}, table.filled(new)) for new in edits.added]
    notes = [note for _cells, notes in held.values() for note in notes]
    if table.check is not None and edits:
        touched = RowEdits(dict(enumerate(edits.edited.values())), edits.added)
        notes += table.check(touched.result([rows[i] for i in edits.edited]))
    return edits, notes


@st.cache_data(max_entries=4, show_spinner=False)  # only the latest stamp is hit
def _references(data_dir: Path, stamp: Stamp) -> References:
    """`references.of`, once per state of the inputs (`stamp`): a page draws many grids."""
    del stamp
    return references.of(data_dir)


def known(data_dir: Path) -> References:
    """The names in the inputs and their uses (`references.of`), cached until an input changes."""
    return _references(data_dir, data_stamp(data_dir))


def _options(table: Table, file: RowFile, base: save.Base, cols: list[Column]) -> list[Column]:
    """`cols` with the names that the reference columns of `table` take in `file` as the grid read
    it (`base`): new options would start a new grid, without its edits."""
    if base.refs is None:
        return cols
    return table.referenced(cols, base.refs, Site(file.name, (), "").scenario, base.rows)


def _hidden(table: Table, view: mode.View) -> dict[bool, frozenset[mode.Item]]:
    """What the mode or a feature hides of the grid of `table` by the inputs now, in simple
    (False) and in advanced mode (True): its columns and the options of its selects."""
    grid, cols = str(table.grid), table.columns(everything=True)
    items = [
        *(mode.Item(mode.Sort.COLUMN, (grid, c.key)) for c in cols),
        *(mode.option(grid, c.key, option) for c in cols for option in c.options),
    ]
    return {
        advanced: frozenset(i for i in items if not mode.shown(i, view.uses, view.off, advanced))
        for advanced in (False, True)
    }


def _edited_cells(table: Table, base: save.Base) -> list[dict[str, Any]]:
    """The cells of the edited and added rows of the grids of `table`, by column name, also the
    edits carried over a switch of the mode."""
    return [
        cells
        for name, count in _grids(table, base).items()
        for state in [grid_state(name, count)]
        for cells in [*state["edited_rows"].values(), *state["added_rows"]]
    ]


def limited(
    cols: list[Column],
    grid: str,
    rows: list[dict[str, Any]],
    edits: list[dict[str, Any]],
    hidden: frozenset[mode.Item],
) -> list[Column]:
    """`cols` of grid `grid` without the options of a select that the mode or a feature hides
    (`hidden`), but one that a row of the file (by key) or an edit (by column name) holds."""
    return [
        replace(
            c,
            options=tuple(
                option
                for option in c.options
                if mode.option(grid, c.key, option) not in hidden
                or any(row.get(c.key) == option for row in rows)
                or any(cells.get(c.name) == option for cells in edits)
            ),
        )
        if c.options
        else c
        for c in cols
    ]


def pin(config: Mapping[str, ColumnConfig], *names: str, width: int | None = None) -> None:
    """Pin the columns `names` on a phone, at `width` pixels when given: they stay in view while
    the grid scrolls sideways. On a desktop a pinned column turns gray and shrinks to its
    content, so it stays as it is."""
    if is_mobile():
        for name in names:
            if name in config:
                config[name]["pinned"] = True
                if width is not None:
                    config[name]["width"] = width


@dataclass(frozen=True)
class Computed:
    """A read-only column of a small grid that each row gives, after the column `after`: the age
    of a phase change. `header` is English, said in the language of the session. It shows the
    row as saved: a grid keeps its edits only while its data stays."""

    name: str
    header: str
    after: str
    value: Callable[[Row], object]


def computed(
    data: pd.DataFrame, config: dict[str, Any], extra: Sequence[Computed], rows: Sequence[Row]
) -> None:
    """The columns `extra` inserted into the cells `data` of `rows` and their configs, read only.
    A new row of the carried edits has none."""
    for c in extra:
        if c.after in data.columns:
            cells = [c.value(row) for row in rows] + [None] * (len(data) - len(rows))
            data.insert(list(data.columns).index(c.after) + 1, c.name, cells)
            config[c.name] = st.column_config.TextColumn(_(c.header), disabled=True)


def small_grid(
    cols: list[Column],
    rows: Sequence[tuple[int, Row]],
    key: str,
    *,
    shown: list[Column] | None = None,
    add_only: bool = False,
    helps: bool = True,
    extra: Sequence[Computed] = (),
) -> RowEdits:
    """A grid of `rows`, each with its index in its list, in the columns `shown` (all of `cols`
    without them) and the read-only columns `extra`, and its edits by those indices: a list of a
    form, the repayments of a sale, an override by id. It grows with its rows, its first column
    stays in view on a phone, and with `helps` the help of its columns sits in a popover there
    (`column_help`). The edits are read with every column, also those carried over a new grid
    (`gridstate.carry`), which a switch of the language draws (`gridstate.drawn`)."""
    visible = shown or cols
    if helps:
        column_help({c.header: text for c in visible if (text := c.help)})
    config = {c.name: c.config() for c in visible}
    pin(config, visible[0].name)
    drawn({key: len(rows)})
    data = frame(visible, [row for _i, row in rows], st.session_state.get(f"carried-{key}"))
    computed(data, config, extra, [row for _i, row in rows])
    st.data_editor(
        data,
        column_config=config,
        num_rows="add" if add_only else "dynamic",
        hide_index=True,
        height="content",
        placeholder="",
        key=key,
    )
    return edits_from_state(grid_state(key, len(rows)), cols, list(rows), {})


def column_help(helps: Mapping[str, str], label: str = COLUMNS_HELP) -> None:
    """On a phone, a popover `label` (English, said in the language of the session) with the help
    of each column header: a tap on a header sorts the grid and shows no help."""
    if is_mobile() and helps:
        st.popover(_(label), icon=":material/help:").markdown(
            "\n".join(f"- **{literal(name)}**: {text}" for name, text in helps.items())
        )


def _editor(
    table: Table, cols: list[Column], shown: list[tuple[int, Row]], widget: str, group: str | None
) -> None:
    """One grid, whose new row starts with the cells of `Table.starts`. In a group the columns get
    fixed widths, so the grids line up. On a phone it grows with its rows: an inner scroll would
    hold the swipe that should scroll the page. There the `lead` columns follow the pinned ones,
    which in a group narrow to `PHONE_PINNED`."""
    cols = table.starts(cols, [row for _i, row in shown])
    if is_mobile():
        cols = table.phone_order(cols)
    config = {c.name: c.config(fixed_width=group is not None) for c in cols}
    for name in table.focus.fields if table.focus else ():
        if name in config:
            config[name]["label"] = FOCUS_MARK + str(config[name].get("label"))
    pin(config, *table.pinned, width=None if group is None else PHONE_PINNED)
    if table.group_by in config and group is not None:
        config[table.group_by] = st.column_config.TextColumn(default=group, width=WIDTHS["string"])
    st.data_editor(
        frame(cols, [row for _i, row in shown], st.session_state.get(f"carried-{widget}")),
        column_config=config,
        num_rows=table.num_rows,
        hide_index=True,
        # a stretched grid widens its columns, the total row below needs the configured widths
        width="stretch" if group is None else "content",
        height="content" if len(shown) < 25 or is_mobile() else 800,
        placeholder="",
        key=widget,
    )


def total_row(cols: list[Column], cells: dict[str, str]) -> str:
    """HTML row with the fixed widths of a grouped grid, so the cells sit under their columns."""
    last = max((i for i, c in enumerate(cols) if c.name in cells), default=-1)
    boxes = "".join(
        f'<div style="flex: none; box-sizing: border-box; width: {c.width}px; padding: 0 8px; '
        f'text-align: {"left" if c.type == "string" else "right"}">'
        f"{html.escape(cells.get(c.name, ''))}</div>"
        for c in cols[: last + 1]  # no empty tail: the row scrolls only when a total is cut
    )
    return (
        f'<div class="dg-total" style="display: flex; overflow-x: auto; margin-top: -0.8rem; '
        f"padding-left: {ROW_MARKER}px; font-size: 0.875rem; font-weight: 700; "
        f'white-space: nowrap">{boxes}</div>'
    )


def key_class(key: str) -> str:
    """The CSS class that Streamlit gives an element with `key`."""
    return "st-key-" + re.sub(r"[^a-zA-Z0-9_-]", "-", key)


def save_in_header(key: str) -> None:
    """Pin the Save button `key` into the page header (`SAVE_IN_HEADER`): the first element of
    its page or tab, as an element before it whose place changes would drop the style for a moment
    in a rerun, and the button with it."""
    st.html(SAVE_IN_HEADER.format(key_class(key)))


def block_label(group: str, count: int, cols: list[Column], cells: dict[str, str]) -> str:
    """Header of a collapsed block: the group, its number of rows and its total row. A narrow
    header breaks between the totals, not inside one."""
    totals = [
        f"{literal(c.header) if c.label else ''} {cells[c.name]}".strip().replace(" ", "\u00a0")
        for c in cols
        if c.name in cells
    ]
    return " · ".join([f"**{literal(group)}** ({count})", *totals])


def _grouped(
    table: Table, cols: list[Column], shown: list[tuple[int, Row]], rows: list[Row], widget: str
) -> tuple[RowEdits, bool]:
    """One collapsed block per group under a colored header, with the guard of its edits. The
    edits of all grids come first: a derived stream follows another group, and a header shows
    the totals with the unsaved edits. Returns the edits and whether one has a warning."""
    by = str(table.group_by)
    groups = {
        group: [(i, row) for i, row in shown if str(row.get(by, "")) == group]
        for group in _groups(table, [row for _i, row in shown])
    }
    colors, every = row_colors(list(groups)), table.columns(everything=True)
    parts = {
        group: _edits(table, every, members, f"{widget}-{group}", group)
        for group, members in groups.items()
    }
    edits = RowEdits()
    for part, _notes in parts.values():
        edits.edited |= part.edited
        edits.added += part.added
        edits.deleted += part.deleted
    after = edits.result(rows)
    looks = {
        # on the dark theme a dim header, with a stripe in the color of the bars
        f".{key_class(f'{table.key}-block-{group}')} summary": (
            f"{{background: light-dark({color}, color-mix(in srgb, {color} 35%, #0e1117)); "
            f"box-shadow: inset 6px 0 light-dark(transparent, {color}); "
            "color: light-dark(#1a1a1a, #fafafa)}"
        )
        for group, color in colors.items()
    }
    st.html(
        "<style>"
        + "".join(f"{summary} {look}" for summary, look in looks.items())
        # a tap leaves the header hovered, which would gray it until the next tap elsewhere
        + "@media (hover: none) {"
        + "".join(f"{summary}:hover {look}" for summary, look in looks.items())
        + "}</style>"
    )
    flagged, units, said = False, table.units(), table.names()
    for group, members in groups.items():
        cells = (
            table.totals(
                [r for r in after if table.keeps(r) and str(r.get(by, "")) == group], after
            )
            if table.totals is not None
            else {}
        )
        with st.expander(
            block_label(
                group or _("(no {key})").format(key=keyword(by)), len(members), cols, cells
            ),
            key=f"{table.key}-block-{group}",
        ):
            _editor(table, cols, members, f"{widget}-{group}", group)
            if cells and not is_mobile():  # the grid took the order and widths of a phone
                st.html(total_row(cols, cells))
            part, notes = parts[group]
            flagged |= guard.check(
                rows,
                part,
                [i for i, _row in members],
                key=f"{table.key}-block-{group}",
                units=units,
                names=said,
                made=table.made,
                notes=notes,
            )
    return edits, flagged


def _groups(table: Table, rows: Iterable[Row]) -> list[str]:
    """The blocks of the grid of `table` that shows `rows`, in their order."""
    return list(dict.fromkeys(str(row.get(str(table.group_by), "")) for row in rows))


def _widget(table: Table, base: save.Base) -> str:
    """The key of the grid of `table` on `base`, new after each save. A block adds its group."""
    return f"{table.key}-{base.nonce}"


def _grids(table: Table, base: save.Base) -> dict[str, int]:
    """The key of each grid of `table` on `base`, one or one per block, with its number of rows:
    one without rows too (`Table.flat`)."""
    widget, part = _widget(table, base), table.part(base.rows)
    if table.group_by is None or not part:
        return {widget: len(part)}
    return {
        f"{widget}-{group}": count
        for group, count in Counter(str(row.get(table.group_by, "")) for row in part).items()
    }


def _held(table: Table, base: save.Base) -> bool:
    """Whether a grid of `table` on `base` holds edits, also a blank new row, also carried over a
    turn of `All columns`: its widget state holds them before it draws."""
    return any(touched(grid_state(name, count)) for name, count in _grids(table, base).items())


def unsaved(table: Table) -> bool:
    """Whether the grid of `table`, one without blocks, holds edits not saved yet, also in a
    column of `more`, before it draws in this run."""
    base = save.kept(table.key)
    if base is None:
        return False
    shown = [(i, base.rows[i]) for i in table.indices(base.rows)]
    cols = table.columns(everything=True)
    return bool(_edits(table, cols, shown, _widget(table, base), None)[0])


def focus(table: Table, row: Row | None, fields: Iterable[str] = ()) -> None:
    """Open the grid of `table` on `row` with `fields` to check (`Focus`) from its next draw on, or
    on no row. The focus lives in the session: a rerun that drew the grid in another order would
    drop its edits."""
    if row is None:
        st.session_state.pop(f"{table.key}-focus", None)
    else:
        found = Focus(table.identified(row), tuple(fields), revisions.digest(row))
        st.session_state[f"{table.key}-focus"] = found


def focused(table: Table) -> bool:
    """Whether the grid of `table` opens on a row that a link opened (`focus`)."""
    return f"{table.key}-focus" in st.session_state


def _focus_line(table: Table, row: Row) -> None:
    """Above the grid: the row of the focus, which comes first, and the columns to check."""
    headers = {c.name: c.header for c in table.columns(everything=True)}
    named = f"**{literal(guard.label(row))}**"
    fields = table.focus.fields if table.focus else ()
    marked = [f"**{FOCUS_MARK}{headers[f]}**" for f in fields if f in headers]
    st.info(
        _("{row}: check {columns}. Its row comes first until a save changes it.").format(
            row=named, columns=joined(marked)
        )
        if marked
        else _("{row} comes first until a save changes it.").format(row=named),
        icon=":material/arrow_downward:",
    )


def _lead(table: Table, rows: list[Row]) -> Row | None:
    """The row of the focus of `table` among `rows`, the rows that its grid shows, as the link
    found it. A changed row ends the focus: a save of the grid starts it on the rows of the file,
    while edits keep the rows that it showed first (`save.base`)."""
    if table.focus is None:
        return None
    row = next((r for r in rows if table.identified(r) == table.focus.row), None)
    if row is None or revisions.digest(row) != table.focus.digest:
        focus(table, None)
        return None
    return row


def edit_table(
    file: RowFile, table: Table, view: mode.View = mode.EVERYTHING, part: save.Part = save.NO_PART
) -> None:
    """Show the rows of `table` as its grid read them first (`save.base`): the edits keep their
    rows when another device changes the file, and a change of the rows of the grid shows with
    the difference. Save the edits on request, onto the file as it is then. A row that a link
    opened (`focus`) comes first. A column that the mode or a feature hides by `view` goes
    behind `All columns`, an option that they hide goes: what the other inputs give stays with
    the base while the grid holds edits, the mode follows its switch, which carries them. The
    Save of a table without groups also writes `part` and lists its changes (the drops of the
    Events tab)."""
    save_key = f"{table.key}-save"
    save_in_header(save_key)
    table = replace(table, focus=st.session_state.get(f"{table.key}-focus"))
    base, changed = save.base(
        file,
        table.key,
        table.part,
        partial(_held, table),
        refs=lambda: known(file.data_dir) if table.options else None,
        hidden=partial(_hidden, table, view) if table.grid else dict,
    )
    if table.group_by is not None and not table.part(base.rows):
        table = table.flat()
    hidden = base.hidden.get(view.advanced, frozenset())
    rare = {i.key[1] for i in hidden if i.sort is mode.Sort.COLUMN}
    if (lead := _lead(table, base.rows)) is None:
        table = replace(table, focus=None)
    else:
        _focus_line(table, lead)
    rows, widget = base.rows, _widget(table, base)
    drawn(_grids(table, base))
    shown = [(i, rows[i]) for i in table.indices(rows)]
    toolbar = is_mobile() or table.rename is not None
    with st.container(horizontal=True, vertical_alignment="center") if toolbar else nullcontext():
        some = len(table.columns(hidden=rare)) < len(table.columns(everything=True))
        everything = some and st.toggle(
            _("All columns"),
            key=f"{table.key}-more",
            on_change=carry,
            args=(_grids(table, base),),
        )
        cols = _options(table, file, base, table.columns(everything=everything, hidden=rare))
        if hidden:
            cols = limited(
                cols, str(table.grid), table.part(base.rows), _edited_cells(table, base), hidden
            )
        column_help({c.header: text for c in cols if (text := c.help)}, table.help_label)
        if table.rename is not None:
            paths = key_paths(table.model, table.inner)  # `property id` and `loan id` too
            locked = [
                str(name)
                for row in table.part(rows)
                for column in table.locked
                if (name := _at(row, paths[column]))
            ]
            held = _held(table, base)
            rename.button(file.data_dir, table.rename, locked, key=table.key, held=held)
    if changed is not None:
        save.warn(
            changed,
            key=table.key,
            identity=table.identity,
            units=table.units(),
            names=table.names(),
        )
    notes: list[str] = []
    if table.group_by is not None:
        edits, flagged = _grouped(table, cols, shown, rows, widget)
    else:
        every = table.columns(everything=True)
        (edits, notes), flagged = _edits(table, every, shown, widget, None), False
        _editor(table, cols, shown, widget, None)
    if table.parent is not None and edits:
        edits.parent = table.parent(edits.result(rows))
    edits, observed = save.stamp(rows, edits, date.today()) if table.track else (edits, [])
    if table.group_by is None:  # a block lists its own edits; after `stamp`, which sets `asof`
        flagged = guard.check(
            rows,
            edits,
            [i for i, _row in shown],
            key=table.key,
            units=table.units(),
            names=table.names(),
            made=table.made,
            notes=notes,
            more=part.changes,
        )
    save.button(
        file,
        edits,
        observed,
        read=base.read(table.identity),
        label=_("Save"),
        key=save_key,
        nonce_key=f"{table.key}-nonce",
        toast=_("Saved {files}").format(files=file.path.name),
        flagged=flagged,
        part=part,
    )
