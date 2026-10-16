"""Edit the YAML inputs in place: comments survive, every save is validated against the model and
recorded as one revision (`revisions.write`)."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import reduce
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from dagobert import history, revisions
from dagobert.files import dump, yaml
from dagobert.loader import APP, validate
from dagobert.model.plan import AppSettings
from dagobert.problems import Keys, RefusedError, dotted
from dagobert.yamlcomments import drop, emptied, end, last, move_comment, settle


class _Null:
    """The edit value that writes an explicit YAML null. One object, also through a copy: a
    widget state of Streamlit is a deep copy, and `is NULL` must still hold."""

    def __copy__(self) -> _Null:
        return self

    def __deepcopy__(self, _memo: object) -> _Null:
        return self

    def __reduce__(self) -> str:
        return "NULL"

    def __repr__(self) -> str:
        return "NULL"


NULL = _Null()
# the inputs that no load of a scenario reads, with the model that checks a write of them
_MODELS: dict[str, type[BaseModel]] = {APP: AppSettings}
_MISSING = object()
Row = Mapping[str, Any]
Name = tuple[tuple[Any, ...], int]  # what names a row among others, see `keyed`


@dataclass(frozen=True)
class Where:
    """A step of a key path to the item of a list whose `key` holds `value`, found when the file
    is read: an index taken earlier names another row once another device adds one before it."""

    key: str
    value: object


Way = tuple[str | int | Where, ...]  # a key path whose steps may name an item by its value


class _MisfitError(RefusedError):
    """Another value at `keys` below `node` than the `want` (a mapping, a list) that an edit needs
    there: a hand edit. The edit of a file names it with the line of the value (`of`)."""

    def __init__(self, node: Any, keys: Keys, want: str) -> None:  # noqa: ANN401 ruamel nodes
        # ruamel.yaml keeps the line of a mapping value and of a list item second to last
        spot = node.lc.data.get(keys[-1]) if isinstance(node, CommentedMap | CommentedSeq) else None
        self.line = spot[-2] + 1 if spot else None
        super().__init__(f"{dotted(keys)} holds no {want}: {_get(node, keys[-1])}")

    def of(self, file: str) -> RefusedError:
        return RefusedError(f"{file}:{self.line}: {self}" if self.line else f"{file}: {self}")


@dataclass
class RowEdits:
    """Changes to a list of mappings. Indices refer to the list before the edit.

    A `None` value removes the key, so the model default applies again. `NULL` writes null.
    `parent` changes the mapping that holds the list, in the same write."""

    edited: dict[int, dict[str, Any]] = field(default_factory=dict)
    added: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)
    parent: dict[str, Any] = field(default_factory=dict)

    def result(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The rows after the edit, as plain dicts. An edit to `None` removes the key, `NULL`
        and a null in the file read as `None`."""
        kept = [
            _updated(dict(row), self.edited.get(i, {}))
            for i, row in enumerate(rows)
            if i not in self.deleted
        ]
        return kept + [_updated({}, new) for new in self.added]

    def __bool__(self) -> bool:
        return bool(self.edited or self.added or self.deleted or self.parent)

    @classmethod
    def between(cls, a: Sequence[Row], b: Sequence[Row], key: Sequence[str]) -> RowEdits:
        """The edits that turn the rows `a` into `b`, row by row (`keyed`), so a new order is no
        edit: `result(a)` holds the rows of `b`, those of `a` in their order, the new ones last.
        An edited row sets each field that differs, `NULL` for a null, None for a field that `b`
        lacks."""
        old, new = keyed(a, key), keyed(b, key)
        return cls(
            edited={
                i: changes
                for name, i in old.items()
                if name in new and (changes := _difference(a[i], b[new[name]]))
            },
            added=[dict(b[j]) for name, j in new.items() if name not in old],
            deleted=[i for name, i in old.items() if name not in new],
        )

    def onto(self, a: Sequence[Row], b: Sequence[Row], key: Sequence[str]) -> RowEdits:
        """These edits of the rows `a` as edits of `b`, a newer version of them: an edited or a
        deleted row by its name in `b` (`keyed`), the new rows and `parent` as they are. A row
        that `b` lacks raises `KeyError`."""
        names, at = {i: name for name, i in keyed(a, key).items()}, keyed(b, key)
        return RowEdits(
            {at[names[i]]: changes for i, changes in self.edited.items()},
            list(self.added),
            [at[names[i]] for i in self.deleted],
            dict(self.parent),
        )


def keyed(rows: Sequence[Row], key: Sequence[str]) -> dict[Name, int]:
    """The index of each row by its name: the values of its fields `key`, and its place among
    the rows with those values. The second trade of one day, kind and security is `((day, kind,
    security), 1)`. Without fields a row is named by its place."""
    count: Counter[tuple[Any, ...]] = Counter()
    out: dict[Name, int] = {}
    for i, row in enumerate(rows):
        values = tuple(row.get(f) for f in key)
        out[values, count[values]] = i
        count[values] += 1
    return out


def _difference(old: Row, new: Row) -> dict[str, Any]:
    """The fields of `new` that differ from `old`, as an edit (`RowEdits.between`)."""
    return {
        k: None if k not in new else NULL if new[k] is None else new[k]
        for k in dict.fromkeys([*old, *new])
        if old.get(k, _MISSING) != new.get(k, _MISSING)
    }


@dataclass(frozen=True)
class Read:
    """The rows of a `RowFile` as a page read them, to which its edits refer by index, and the
    other fields of the mapping that holds them (`RowFile.contents`), which `RowEdits.parent`
    changes: `revision` is the last change of the file before the read
    (`revisions.last_change`), `key` the fields that name a row (`keyed`)."""

    rows: list[dict[str, Any]]
    holder: dict[str, Any]
    revision: str | None
    key: tuple[str, ...]


@dataclass(frozen=True)
class RowFile:
    """A list of mappings inside one input file, found by `keys` from the top level.

    `("assets",)` is the asset list, `("assets", Where("id", "depot"), "trades")` the trades of
    the asset `depot`. A missing last key reads as an empty list and is created on the first added
    row."""

    data_dir: Path
    name: str
    keys: Way

    @property
    def path(self) -> Path:
        return self.data_dir / self.name

    def rows(self) -> list[dict[str, Any]]:
        """The rows now. A `Where` that names no row raises `RefusedError`."""
        return self.contents()[0]

    def contents(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """The rows now and the other fields of the mapping that holds them, such as the
        `cost_basis` of the asset whose trades they are."""
        doc = _document(self.path.read_text(encoding="utf-8"), self.name)
        keys = _found(doc, self.keys)
        if not isinstance(holder := _at(doc, keys[:-1]), dict | None):
            raise _MisfitError(_at(doc, keys[:-2]), keys[:-1], "mapping").of(self.name)
        if not isinstance(rows := _at(doc, keys), list | None):
            raise _MisfitError(holder, keys, "list").of(self.name)
        # a missing section starts with the first row
        return list(rows or []), {k: v for k, v in (holder or {}).items() if k != keys[-1]}

    def child(self, row_id: str, key: str) -> RowFile:
        """The list `key` of the row whose `id` is `row_id`, found by it at each read and
        write."""
        return RowFile(self.data_dir, self.name, (*self.keys, Where("id", row_id), key))

    def apply(
        self,
        edits: RowEdits,
        *,
        source: str,
        observed: Sequence[history.Observation] = (),
        read: Read | None = None,
        seen: revisions.Seen | None = None,
        values: Mapping[Keys, Any] | None = None,
        check: Callable[[], object] = lambda: None,
    ) -> None:
        """Write the edits as one revision of `source`, with the `observed` asset values that
        they set appended to `history.csv`. With `read`, the edits refer to the rows that a page
        read, and go onto the rows of the file then (`moved`). With `seen`, every row must be
        as a page showed them, or `revisions.ConflictError` refuses the edits: new rows that were
        checked against all of them (the trade import). `values` of the file (`Edit.values`)
        save with the rows, `check` runs first inside the write (the drops of a scenario with
        the Save of its events). An input that no scenario can load changes nothing and
        raises."""

        def edit() -> dict[str, str | None]:
            check()
            if seen is not None:
                revisions.unchanged(self.data_dir, seen, self.rows())
            moved = edits if read is None else self.moved(edits, read)
            text = Edit(self.name, dict(values or {}), {self.keys: moved}).text(self.data_dir)
            return {self.name: text} | history.appended(self.data_dir, observed)

        revisions.write(self.data_dir, source, edit)

    def moved(self, edits: RowEdits, read: Read) -> RowEdits:
        """`edits` of the rows `read` as edits of the rows now, row by row (`RowEdits.onto`). A
        row that they change or remove, or a field of the holder that `parent` sets, that changed
        since raises `revisions.ConflictError` with the revisions since. Other rows and fields
        keep what changed since, the new rows too: a value that a price records on the asset
        does not refuse a save of its trades."""
        now, holder = self.contents()
        names, at = (
            {i: name for name, i in keyed(read.rows, read.key).items()},
            keyed(now, read.key),
        )
        touched = [*edits.edited, *edits.deleted]
        revisions.unchanged(
            self.data_dir,
            revisions.Seen(
                self.name,
                read.revision,
                revisions.digest(
                    [
                        *(read.rows[i] for i in touched),
                        {k: read.holder.get(k) for k in edits.parent},
                    ]
                ),
            ),
            [
                *(now[at[names[i]]] if names[i] in at else None for i in touched),
                {k: holder.get(k) for k in edits.parent},
            ],
        )
        return edits.onto(read.rows, now, read.key)

    def text(self, edits: RowEdits) -> str | None:
        """`Edit.text` of the rows: the file after the edits, read now."""
        return Edit(self.name, rows={self.keys: edits}).text(self.data_dir)


@dataclass(frozen=True)
class Merge:
    """A value that changes some keys of the mapping in its place and keeps the others, in the
    convention of an edit: the `stream` of an `add_stream` event in a row edit. A missing
    mapping, or a value there that is none, becomes one."""

    changes: dict[str, Any]


@dataclass(frozen=True)
class Edit:
    """Changes to one input file, `name` under the data directory (`assumptions.yaml`,
    `scenarios/a.yaml`, `app.yaml`), made in its ruamel.yaml document so that the comments stay.

    First `rows` edit the lists of mappings at their key paths (`RowFile`), then `values` set the
    value at each key path: `None` clears it, and each mapping above that holds nothing else goes
    with it, up to a list or the top (a leftover `{}` over a parent's null would switch a section
    on). `NULL` writes null, `Merge` changes some keys of a mapping. A missing key on the way, or a
    value there that is none, becomes a block mapping. A new value takes the flow style of the
    list or mapping that it replaces, a new row that of the row before it, a new mapping of
    scalars that of the entry before it (a class of `returns`). A missing file starts empty, or
    from the text of the file `origin` (a copy, a rename), `create` refuses one that exists,
    `remove` removes it.

    The first edit of a file dumps it: its layout changes once (`{ a: b }` becomes `{a: b}`, a
    flow mapping over several lines takes one line, a list under a key gets an indent). After
    that an edit changes its own lines only."""

    name: str
    values: dict[Keys, Any] = field(default_factory=dict)
    rows: dict[Way, RowEdits] = field(default_factory=dict)
    create: bool = False
    remove: bool = False
    origin: str | None = None

    def text(self, data_dir: Path) -> str | None:
        """The file after the edit, read now: inside a write it is the newest. None when there is
        no file after it. An edit without values or rows keeps the text as it is, also the text
        of `origin` (a rename), unless it creates an empty file."""
        path = data_dir / self.name
        if self.create and path.exists():
            msg = f"{path} exists"
            raise FileExistsError(msg)
        if self.remove:
            return None
        start = data_dir / self.origin if self.origin else path
        return self.onto(start.read_text(encoding="utf-8") if start.exists() else None)

    def onto(self, old: str | None) -> str | None:
        """The text `old` after the edit: of the file now, or of a write before it in the same
        revision (the scalars of a roll forward)."""
        changed = self.values or any(self.rows.values())
        if not changed and (old is not None or not self.create):
            return old
        doc = _document(old, self.name)
        settle(doc)
        try:
            for way, edits in self.rows.items():
                if edits:
                    _edit_rows(doc, _found(doc, way), edits)
            for keys, value in self.values.items():
                _apply(doc, keys, value)
        except _MisfitError as err:
            raise err.of(self.name) from err
        return dump(doc)


def write(
    data_dir: Path,
    edits: Sequence[Edit],
    *,
    source: str,
    check: Callable[[], object] = lambda: None,
) -> None:
    """The edits of several files as one revision of `source`, or none of them. `check` runs
    first, inside the write: `revisions.unchanged` of what a page read, a save conflict. Every
    scenario loads after the write, unless it changes only `app.yaml`: no run reads that."""
    names = [edit.name for edit in edits]
    if twice := sorted({name for name in names if names.count(name) > 1}):
        msg = f"one edit per file: {', '.join(twice)}"
        raise ValueError(msg)

    def texts() -> dict[str, str | None]:
        check()
        out = {edit.name: edit.text(data_dir) for edit in edits}
        for name, text in out.items():
            if text is not None and name in _MODELS:
                validate(_MODELS[name], text, name)
        return out

    revisions.write(data_dir, source, texts, validate=any(edit.name != APP for edit in edits))


def _edit_rows(doc: Any, keys: Keys, edits: RowEdits) -> None:  # noqa: ANN401 ruamel nodes
    """Apply `edits` to the list of mappings at `keys`. The comment lines between rows stay above
    the row that follows them (`drop`). A missing list is created with its first row, a nested
    one that ends empty goes, since a missing list reads as empty, a top-level one stays as `[]`
    (`emptied`): ruamel.yaml would write the comment lines inside an empty list in front of its
    `[]`, which does not parse."""
    if not isinstance(found := _at(doc, keys), list | None):
        raise _MisfitError(_at(doc, keys[:-1]), keys, "list")
    rows = CommentedSeq() if found is None else found
    for i, changes in edits.edited.items():
        _update(rows[i], changes)
    for new in edits.added:
        row = _styled(CommentedMap(), rows[-1] if rows else None)
        _update(row, new)
        before = last(rows)
        rows.append(row)
        move_comment(before, last(rows))
    if rows is not found:
        if rows:
            _set(doc, keys, rows)
    elif len(set(edits.deleted)) == len(rows) and len(keys) == 1:
        emptied(doc, keys[0])
    elif len(set(edits.deleted)) == len(rows):
        _clear(doc, keys)
    else:
        for i in sorted(edits.deleted, reverse=True):
            drop(rows, i)
    for key, value in edits.parent.items():
        _apply(doc, (*keys[:-1], key), value)


def _updated(row: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    """`_update` on a copy: a `Merge` changes a mapping inside."""
    out = copy.deepcopy(dict(row))
    _update(out, changes)
    return out


def _update(row: dict[str, Any], changes: dict[str, Any]) -> None:
    """Apply `changes` by key. The comment lines below a row stay above the next one, also when a
    key is added or removed."""
    for key, value in changes.items():
        _apply(row, (key,), value)


def _apply(node: Any, keys: Keys, value: Any) -> None:  # noqa: ANN401 ruamel nodes are untyped
    """Set, clear (`None`) or merge into (`Merge`) the value at `keys` below `node`."""
    if isinstance(value, Merge):
        for key, inner in value.changes.items():
            _apply(node, (*keys, key), inner)
    elif value is None:
        _clear(node, keys)
    else:
        _set(node, keys, value)


def _set(node: Any, keys: Keys, value: Any) -> None:  # noqa: ANN401 ruamel nodes are untyped
    """Set the value at `keys` below `node`. A missing key on the way, or a null there, becomes a
    block mapping, built whole before it goes in, so that the comment lines after `node` and after
    the old value stay after the new one; any other value on the way raises. A value equal to the
    old one keeps the old node, with its text and the comments inside."""
    *way, key = keys
    for i, part in enumerate(way):
        inner = _get(node, part)
        if isinstance(inner, dict | list):
            node = inner
            continue
        if inner is not None or isinstance(part, int):
            raise _MisfitError(node, keys[: i + 1], "mapping")
        value = reduce(lambda held, k: {k: held}, reversed(keys[i + 1 :]), value)
        key = part
        break
    old = _get(node, key)
    new = _styled(_node(value), old if _has(node, key) else _neighbour(node, value))
    if _has(node, key) and _same(old, new):
        return
    after = end(node, key) if _has(node, key) else None
    before = last(node)
    node[key] = new
    move_comment(after, end(node, key))
    move_comment(before, last(node))


def _same(old: Any, new: Any) -> bool:  # noqa: ANN401 any YAML value
    """Whether `new` equals `old` in value and kind: a bool is no number."""
    if isinstance(old, dict) and isinstance(new, dict):
        return old.keys() == new.keys() and all(_same(old[k], new[k]) for k in old)
    if isinstance(old, list) and isinstance(new, list):
        return len(old) == len(new) and all(map(_same, old, new, strict=True))
    scalar = not isinstance(old, dict | list)
    return scalar and isinstance(old, bool) == isinstance(new, bool) and old == new


def _clear(node: Any, keys: Keys) -> None:  # noqa: ANN401 ruamel nodes are untyped
    """Remove the value at `keys` below `node`, and each mapping or nested list above it that holds
    nothing else, up to a list item or `node`. A list held by `node` stays as `[]` (`emptied`).
    The comment lines around it stay (`drop`)."""
    way = [node]
    for key in keys[:-1]:
        way.append(_get(way[-1], key))
        if not isinstance(way[-1], dict | list):
            return
    if not _has(way[-1], keys[-1]):
        return
    at = len(keys) - 1
    while (
        at
        and len(way[at]) == 1
        and isinstance(way[at - 1], dict)
        and (isinstance(way[at], dict) or at > 1)
    ):
        at -= 1
    if isinstance(way[at], list) and len(way[at]) == 1 and at:
        emptied(way[at - 1], keys[at - 1])
    else:
        drop(way[at], keys[at])


def _document(text: str | None, name: str) -> CommentedMap:
    """The YAML document of the input file `name`, an empty mapping for none. A top level that
    is no mapping (a hand edit) raises `RefusedError` with the file and the line. An empty `{}`
    starts a block mapping too."""
    if (doc := yaml().load(text) if text else None) is None or doc == {}:
        return CommentedMap()
    if not isinstance(doc, CommentedMap):
        line = f":{doc.lc.line + 1}" if isinstance(doc, CommentedSeq) else ""
        msg = f"{name}{line}: no mapping at the top level"
        raise RefusedError(msg)
    return doc


def _at(node: Any, keys: Keys) -> Any:  # noqa: ANN401 ruamel nodes are untyped
    """The value at `keys` below `node`, None when the way lacks one."""
    for key in keys:
        node = _get(node, key)
    return node


def _found(doc: Any, way: Way) -> Keys:  # noqa: ANN401 ruamel nodes are untyped
    """`way` with each `Where` as the index of the item that it names. Raises `RefusedError` when
    none does: the row was removed since."""
    keys: Keys = ()
    for step in way:
        if not isinstance(step, Where):
            keys = (*keys, step)
            continue
        items = _at(doc, keys)
        found = next(
            (
                i
                for i, item in enumerate(items if isinstance(items, list) else [])
                if isinstance(item, dict) and item.get(step.key) == step.value
            ),
            None,
        )
        if found is None:
            msg = f"{dotted(keys)} holds no row with {step.key} {step.value} any more"
            raise RefusedError(msg)
        keys = (*keys, found)
    return keys


def _get(node: Any, key: str | int) -> Any:  # noqa: ANN401 ruamel nodes are untyped
    return node[key] if _has(node, key) else None


def _has(node: Any, key: str | int) -> bool:  # noqa: ANN401 ruamel nodes are untyped
    if isinstance(node, dict):
        return key in node
    return isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node)


def _node(value: Any) -> Any:  # noqa: ANN401
    """A new value as ruamel.yaml nodes all the way down, which can carry the comment lines after
    them. `NULL` writes null."""
    match value:
        case CommentedMap() | CommentedSeq():
            return value
        case dict():
            return CommentedMap({k: _node(v) for k, v in value.items()})
        case list():
            return CommentedSeq(_node(v) for v in value)
    return None if value is NULL else value


def _neighbour(node: Any, value: Any) -> Any:  # noqa: ANN401 ruamel nodes are untyped
    """What a new entry of the mapping `node` takes its style from, as a new row from the row
    before it: the last entry, for a mapping of scalars (a class of `returns`). A mapping that holds
    more, such as a section, stays a block."""
    flat = isinstance(value, dict) and not any(isinstance(v, dict | list) for v in value.values())
    return node[next(reversed(node))] if flat and isinstance(node, dict) and node else None


def _styled(new: Any, like: Any) -> Any:  # noqa: ANN401 ruamel nodes are untyped
    """`new` in the flow style of `like` when both are mappings or both lists."""
    alike = isinstance(new, CommentedMap | CommentedSeq) and type(new) is type(like)
    if alike and like.fa.flow_style():
        new.fa.set_flow_style()
    return new


def assets_file(data_dir: Path) -> RowFile:
    return RowFile(data_dir, "assets.yaml", ("assets",))


def streams_file(data_dir: Path) -> RowFile:
    return RowFile(data_dir, "cashflows.yaml", ("streams",))
