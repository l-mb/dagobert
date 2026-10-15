"""The overrides of a scenario file as the editor sees them: the value of each override path with
the source it comes from, edits of the file's own overrides, and the rows of the `shift`,
`events` and `assets` overrides."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from types import UnionType
from typing import TYPE_CHECKING, Any, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from dagobert.loader import chain, deep_merge, flatten, kept, merged_overrides, nested, read_yaml
from dagobert.model.assumptions import Assumptions
from dagobert.model.base import KeyPath
from dagobert.store import NULL

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

DEFAULT = "default"  # the source of a value that no file writes
ASSUMPTIONS = "assumptions.yaml"
DEPTH = {"events": 3, "assets": 3}  # a value there replaces the field of an item whole
ROWS = {  # the columns of the rows of an override of the scenario: its keys, then the value
    "shift": ("id", "months"),
    "events": ("id", "field", "value"),
    "assets": ("asset", "field", "value"),
}


@dataclass(frozen=True)
class Leaf:
    """The value at an override path and where it comes from: `DEFAULT`, `ASSUMPTIONS` or the
    stem of a scenario file."""

    value: Any
    source: str


def leaves(overrides: Mapping[str, Any]) -> dict[KeyPath, Any]:
    """The override paths of `overrides` with their values: `loader.flatten`, down to the field of
    an item in `events` and `assets`."""
    return {
        path: value
        for key, mapping in overrides.items()
        for path, value in flatten({key: mapping}, DEPTH.get(key)).items()
    }


def effective(
    data_dir: Path, scenario: Path, overrides: Mapping[str, Any] | None = None
) -> dict[KeyPath, Leaf]:
    """Each override path of `scenario` with its value and source, merged as `load_plan` merges
    them: the model defaults, `assumptions.yaml`, then the overrides of the `extends` chain, the
    root first. `overrides` stand in for those of `scenario` itself. Raw YAML, so a file that does
    not load still gives its values. A value of the assumptions reads as the model reads it (a
    month on its first day), unless it does not load."""
    return _resolved(*_read(data_dir, scenario, overrides))


def fallback(
    data_dir: Path, scenario: Path, overrides: Mapping[str, Any] | None = None
) -> dict[KeyPath, Leaf]:
    """The placeholder of each override path: what it takes when `overrides` (default: those of
    `scenario`) do not set it, the rest of them kept, `effective` after `own` clears the path. A
    path that it lacks has nothing to inherit: a section that is off, the mean of a new index."""
    base, layers = _read(data_dir, scenario, overrides)
    stem, written = layers[-1]
    paths = leaves(written)
    found = {
        path: leaf
        for path, leaf in _resolved(base, layers).items()
        if not any(_within(path, at) for at in paths)
    }
    for at in paths:
        cleared = _resolved(base, [*layers[:-1], (stem, own(written, {at: None}))])
        found |= {path: leaf for path, leaf in cleared.items() if _within(path, at)}
    return found


def own(overrides: Mapping[str, Any], changes: Mapping[KeyPath, Any]) -> dict[str, Any]:
    """The overrides of a scenario file with `changes` by override path, in the convention of the
    store: `None` clears the path, so its value is inherited again, and a mapping that loses its
    last key goes too. `store.NULL` writes null: an optional section is off. A value replaces
    what holds a part of its path as no mapping. All else stays, also a value equal to the
    inherited one: it holds when the parent changes later. The result is the candidate for the
    checks, plain dicts: a save writes the same changes by key path into the document, so its
    comments and flow style stay."""
    out = dict(overrides)
    for path, value in changes.items():
        out = (
            _cleared(out, path)
            if value is None
            else _set(out, path, None if value is NULL else value)
        )
    return out


def rows(key: str, mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The `shift`, `events` or `assets` override as rows with the columns of `ROWS`, in the order
    of the file. A value stays as the file writes it."""
    names = ROWS[key]
    return [
        dict(zip(names, (*path, value), strict=True))
        for path, value in flatten(mapping, len(names) - 1).items()
        if len(path) == len(names) - 1  # an id without fields gives no row
    ]


def from_rows(key: str, entries: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The override `key` from rows with the columns of `ROWS`. A row with an empty cell goes, so
    an empty value inherits. Of two rows with the same id and field the later one wins."""
    *keys, value = ROWS[key]
    return nested(
        {
            tuple(row[k] for k in keys): row[value]
            for row in entries
            if all(row.get(name) not in (None, "") for name in ROWS[key])
        }
    )


def _read(
    data_dir: Path, scenario: Path, overrides: Mapping[str, Any] | None
) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """`assumptions.yaml`, and the overrides of each file of the chain by stem, the root first,
    less those of the ids that a file below drops (`loader.kept`)."""
    files = chain(scenario)
    layers = [
        (file.stem, kept(_own(raw), {i for _, below in files[n + 1 :] for i in _drop(below)}))
        for n, (file, raw) in enumerate(files)
    ]
    if overrides is not None:
        layers[-1] = (scenario.stem, dict(overrides))
    return read_yaml(data_dir / "assumptions.yaml"), layers


def _resolved(
    base: dict[str, Any], layers: list[tuple[str, dict[str, Any]]]
) -> dict[KeyPath, Leaf]:
    merged = deep_merge(filled(Assumptions, base), merged_overrides(doc for _, doc in layers))
    return {
        path: Leaf(value, _source(path, layers[::-1], base))
        for path, value in leaves(filled(Assumptions, merged)).items()
    }


def _within(path: KeyPath, prefix: KeyPath) -> bool:
    return path[: len(prefix)] == prefix


def _drop(raw: Mapping[str, Any]) -> list[str]:
    """The ids of the `drop` of the raw mapping of a scenario file."""
    found = raw.get("drop")
    return [i for i in found if isinstance(i, str)] if isinstance(found, list) else []


def _own(raw: Mapping[str, Any]) -> dict[str, Any]:
    """The overrides of the raw mapping of a scenario file."""
    found = raw.get("overrides")
    return found if isinstance(found, dict) else {}


def filled(model: type[BaseModel], raw: Mapping[str, Any]) -> dict[str, Any]:
    """`raw` with the defaults of `model` where it lacks a key and each value of a scalar field
    as the model reads it, as `model_dump` gives them after a validation, also inside a section and
    the models of a mapping (`returns`, `indices`). A required field stays missing, a value that
    does not load and a key that the model lacks stay as they are."""
    out = dict(raw)
    for name, field in model.model_fields.items():
        key = field.alias or name
        value = out.get(key)
        if key not in out and not field.is_required():
            default = field.get_default(call_default_factory=True)
            out[key] = default.model_dump() if isinstance(default, BaseModel) else default
        elif isinstance(value, dict) and (section := _model(field.annotation)):
            out[key] = filled(section, value)
        elif isinstance(value, dict) and (item := _model(_values(field.annotation))):
            out[key] = {k: filled(item, v) if isinstance(v, dict) else v for k, v in value.items()}
        elif key in out and not isinstance(value, dict | list):
            out[key] = _read_as(model, name, value)
    return out


def _read_as(model: type[BaseModel], name: str, value: Any) -> Any:  # noqa: ANN401
    """`value` as the field `name` of `model` reads it, a month on its first day."""
    try:
        return _adapter(model, name).validate_python(value)
    except ValidationError:
        return value


@cache
def _adapter(model: type[BaseModel], name: str) -> TypeAdapter[Any]:
    return TypeAdapter(model.model_fields[name].rebuild_annotation())


def _model(annotation: Any) -> type[BaseModel] | None:  # noqa: ANN401 any type of a field
    """The model of a field of type `X` or `X | None`."""
    options = get_args(annotation) if get_origin(annotation) is UnionType else (annotation,)
    return next((t for t in options if isinstance(t, type) and issubclass(t, BaseModel)), None)


def _values(annotation: Any) -> Any:  # noqa: ANN401 any type of a field
    """The type of the values of a field of type `dict[K, V]`, else None."""
    return get_args(annotation)[1] if get_origin(annotation) is dict else None


def _source(
    path: KeyPath, layers: Iterable[tuple[str, Mapping[str, Any]]], base: Mapping[str, Any]
) -> str:
    """The highest layer that holds `path`. A layer that holds a part of it as no mapping cuts
    off the layers below. The scenario layers merge with each other first, so the base holds a
    path that none of them holds, unless the model fills it in."""
    for name, doc in layers:
        held = _held(doc, path)
        if held is not None:
            return name if held else _base(path, base)
    return _base(path, base)


def _base(path: KeyPath, base: Mapping[str, Any]) -> str:
    return ASSUMPTIONS if _held(base, path) else DEFAULT


def _held(doc: Mapping[str, Any], path: KeyPath) -> bool | None:
    """True when `doc` holds `path`, False when it holds a part of it as no mapping, None when it
    lacks it."""
    node: Any = doc
    for key in path:
        if not isinstance(node, dict):
            return False
        if key not in node:
            return None
        node = node[key]
    return True


def _set(node: Mapping[str, Any], path: KeyPath, value: Any) -> dict[str, Any]:  # noqa: ANN401
    head, *rest = path
    inner = node.get(head)
    return {
        **node,
        head: _set(inner if isinstance(inner, dict) else {}, tuple(rest), value) if rest else value,
    }


def _cleared(node: dict[str, Any], path: KeyPath) -> dict[str, Any]:
    head, *rest = path
    inner = node.get(head)
    if not rest:
        below = {}
    elif isinstance(inner, dict):
        below = _cleared(inner, tuple(rest))
    else:
        return node  # no value below a value that is no mapping
    if head not in node or below is inner:
        return node
    return {**node, head: below} if below else {k: v for k, v in node.items() if k != head}
