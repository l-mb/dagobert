"""The fields of a model for the forms: one `Field` per leaf from the JSON schema, with its unit,
bounds, default and help, and how a value of the file shows and reads in that unit. Euros take a
decimal comma or point whatever the language, a share or a rate is typed in percent and stored as
the fraction, a month takes `2027-05` or `05.2027` and reads any day as the first, a date
`1965-03-14` or `14.03.1965`. A field keeps the English of the model: its label and help speak
the language of the session where the form draws."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import numpy as np

from dagobert.i18n import N_, _
from dagobert.loader import flatten
from dagobert.model.base import TITLES, KeyPath, Unit, named
from dagobert.money import format_eur
from dagobert.overrides import DEFAULT, Leaf, filled, own
from dagobert.store import NULL
from dagobert.ui.gridcolumns import (
    PERCENT_HELP,
    Column,
    columns,
    default_said,
    number,
    oneline,
    resolve,
    said,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

ABSENT: Any = object()  # no key at a path, no default of a required field
NULL_TEXT = "null"  # how an explicit null shows, where it differs from the default
SYMBOL: dict[Unit | None, str] = {Unit.EUR: "€", Unit.PERCENT: "%"}
HINT: dict[Unit | None, str] = {
    Unit.PERCENT: PERCENT_HELP,
    Unit.MONTH: N_("A month: 2027-05 or 05.2027, any day counts as the first."),
    Unit.DATE: N_("A date: 1965-03-14 or 14.03.1965."),
}
EMPTY_ONE = N_("Empty counts as 1.")  # the help of an entry of a mapping of numbers (`entries`)
# euros with a decimal comma or point: groups of three after a mark are thousands
_EUROS = re.compile(r"(-?)(\d{1,3}(?:([.,])\d{3})+|\d+)(?:([.,])(\d{1,2}))?")
_DECIMAL = re.compile(r"-?(?:\d+(?:[.,]\d*)?|[.,]\d+)")  # one mark, always decimal
_MONTH, _DAY = re.compile(r"\d{4}-\d{2}"), re.compile(r"\d{4}-\d{2}-\d{2}")
# German order, day first: `14.03.1965`, `4.3.1965`; a month `03.2027`
_TAG, _MONAT = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})"), re.compile(r"(\d{1,2})\.(\d{4})")
_BOOLS = {"true": True, "yes": True, "on": True, "false": False, "no": False, "off": False}


class Kind(StrEnum):
    """What a field holds, which sets its widget."""

    NUMBER = "number"  # a float in its unit: a text field
    INTEGER = "integer"  # a whole number: a number input
    DATE = "date"  # a day, or a calendar month for `Unit.MONTH`: ISO text
    CHOICE = "choice"  # one of `options`
    BOOL = "bool"
    TEXT = "text"
    NAMES = "names"  # a list of names
    ROWS = "rows"  # a list of mappings (a glide path): a small grid of `columns`
    MAP = "map"  # a mapping by name (`returns`): a grid with a key column and `columns`
    SECTION = "section"  # an optional model (`allocation`), on or off


@dataclass(frozen=True)
class Field:
    """A leaf of a model by its key path below the mapping that a form edits. The bounds are those
    of the file; `default` is the default of the field itself, `ABSENT` for a required one (what an
    empty field takes depends on its siblings: `fallback`). `nullable`: the model takes null.
    `empty`: what an empty field stands for besides a number (`all` of a repayment). `section`:
    the optional model that holds the field. `entry`: a key of a mapping of numbers (`salary` per
    phase, `entries`). `columns`: of the rows of a `ROWS` field, of the entries of a `MAP` (a
    `value` column for a mapping of numbers). The help in parts, in English: `about` (the
    description, of the field, else of its model, or a help of the page), `named` (the default that
    it names, of the mapping that holds the field where it has one), `more` (sentences after it,
    messages of the catalogue) and `term` (the technical term before it: `Sparer-Pauschbetrag`)."""

    path: KeyPath
    kind: Kind
    unit: Unit | None = None
    options: tuple[Any, ...] = ()
    low: float | None = None
    high: float | None = None
    open_low: bool = False  # `low` itself is refused (`gt`)
    open_high: bool = False
    default: Any = ABSENT
    nullable: bool = False
    empty: Any = None
    about: str = ""
    named: Any = None
    more: tuple[str, ...] = ()
    term: str = ""
    section: KeyPath | None = None
    columns: tuple[Column, ...] = ()
    entry: bool = False
    titles: tuple[tuple[str, str], ...] = ()  # the options in words (`model.base.Titled`)

    @property
    def label(self) -> str:
        """The label in the language of the session where a page gives none: the words of its key
        (`Cash buffer months`, an acronym as written: `AfA`, `model.base.named`), of an entry after
        those of its mapping (`Salary work`), with the symbol of its unit."""
        holder, key = ("", *self.path)[-2:]
        name = (
            f"{_(named(holder))} {key.replace('_', ' ').lower()}" if self.entry else _(named(key))
        )
        return " ".join(filter(None, (name, SYMBOL.get(self.unit))))

    @property
    def help(self) -> str:
        """The help in the language of the session: the description, the default that it names
        (`(default: 30%)`), how its unit reads, after the technical term."""
        text = said(self.about, default_said(self.named, self.unit), self.more)
        return f"{self.term}: {text}" if self.term else text

    @property
    def null(self) -> bool:
        """Whether a null is a value of its own: the default is something else (`index` null is
        nominal, its default `cpi`)."""
        return self.nullable and self.default not in (None, ABSENT)


def of(model: type[BaseModel], prefix: KeyPath = ()) -> list[Field]:
    """One `Field` per leaf of `model`, from its JSON schema, below `prefix`. A nested model gives
    its fields, an optional one first a `SECTION`; a mapping by name a `MAP`. A tag (`type` of an
    event) is no field."""
    schema = model.model_json_schema()
    return list(_walk(schema, schema, prefix, None))


def _walk(
    spec: dict[str, Any],
    schema: dict[str, Any],
    path: KeyPath,
    section: KeyPath | None,
    outer: Mapping[str, Any] | None = None,
) -> Iterator[Field]:
    """The fields of `spec`; `outer` is the default of the mapping that holds them (`inflation`),
    whose values their help names."""
    required = spec.get("required", ())
    for name, prop in spec["properties"].items():
        union = prop.get("anyOf", [prop])
        value = resolve(next(p for p in union if p.get("type") != "null"), schema)
        if "const" in value:
            continue
        at = (*path, name)
        default = ABSENT if name in required else prop.get("default")
        named = (outer or {}).get(name, prop.get("default"))
        nullable = any(p.get("type") == "null" for p in union)
        hint = HINT.get(Unit(value["unit"])) if "unit" in value else None
        common = {
            "default": default,
            "about": oneline(prop.get("description") or value.get("description") or ""),
            "named": named,
            "more": (hint,) if hint else (),
            "section": section,
        }
        if "properties" in value:
            if nullable:
                yield Field(at, Kind.SECTION, **common)
            held = named if isinstance(named, dict) else None
            yield from _walk(value, schema, at, at if nullable else section, held)
        else:
            yield replace(_leaf(at, value, union, schema), nullable=nullable, **common)


def entries(field: Field, names: Iterable[str]) -> list[Field]:
    """A mapping of numbers by name (`scale.salary`, a `MAP` with a `value` column) as one number
    per name of `names`, a phase: empty counts as 1."""
    value = field.columns[0]
    return [
        Field(
            (*field.path, name),
            Kind.NUMBER,
            unit=value.unit,
            low=value.bounds[0],
            high=value.bounds[1],
            about=field.about,
            named=field.named,
            more=(*field.more, EMPTY_ONE),
            section=field.section,
            entry=True,
        )
        for name in names
    ]


def _leaf(
    at: KeyPath, value: dict[str, Any], union: list[dict[str, Any]], schema: dict[str, Any]
) -> Field:
    items = resolve(value.get("items", {}), schema)
    kind = _kind(value, items, schema)
    entries = value.get("additionalProperties")
    return Field(
        at,
        kind,
        unit=Unit(value["unit"]) if "unit" in value else None,
        options=tuple(value.get("enum") or items.get("enum") or ()),
        titles=tuple((value.get(TITLES) or items.get(TITLES) or {}).items()),
        low=value.get("minimum", value.get("exclusiveMinimum")),
        high=value.get("maximum", value.get("exclusiveMaximum")),
        open_low="exclusiveMinimum" in value,
        open_high="exclusiveMaximum" in value,
        empty=next((option["const"] for option in union if "const" in option), None),
        columns=_columns(items, schema)
        if kind is Kind.ROWS
        else _entries(entries, schema)
        if kind is Kind.MAP and isinstance(entries, dict)
        else (),
    )


def _kind(value: dict[str, Any], items: dict[str, Any], schema: dict[str, Any]) -> Kind:
    if "enum" in value:
        return Kind.CHOICE
    if value.get("format") == "date":
        return Kind.DATE
    if value.get("type") == "array":
        return Kind.ROWS if all("properties" in m for m in _members(items, schema)) else Kind.NAMES
    kinds = {"number": Kind.NUMBER, "integer": Kind.INTEGER, "boolean": Kind.BOOL}
    return (
        Kind.MAP if value.get("type") == "object" else kinds.get(str(value.get("type")), Kind.TEXT)
    )


def _columns(items: dict[str, Any], schema: dict[str, Any]) -> tuple[Column, ...]:
    """The grid columns of the rows of a list, of every model that a row can be (`then`). A list
    of mappings inside a row takes no column (the gifts of a relative): a cell holds no table."""
    found: dict[str, Column] = {}
    for member in _members(items, schema):
        required = member.get("required", ())
        for name, prop in member["properties"].items():
            for col in Column.of(name, prop, schema, required=name in required):
                if col.type != "rows":
                    found.setdefault(col.name, col)
    return tuple(found.values())


def _members(items: dict[str, Any], schema: dict[str, Any]) -> list[dict[str, Any]]:
    """The models that an item of a list can be: one, or those of a union (`anyOf`, or `oneOf` of
    a discriminated one such as the events)."""
    return [resolve(m, schema) for m in items.get("anyOf") or items.get("oneOf") or [items]]


def _entries(entry: dict[str, Any], schema: dict[str, Any]) -> tuple[Column, ...]:
    """The grid columns of the entries of a mapping by name: the fields of its model, or `value`."""
    spec = resolve(entry, schema)
    return (
        _columns(spec, schema) if "properties" in spec else tuple(Column.of("value", entry, schema))
    )


def euros(text: str, *, signed: bool = False) -> float | None:
    """An amount in euros, typed with a decimal comma or point whatever the language: `20,50`,
    `20.5`, `1.234,50`, `1,234.50`, also `1.234` for 1,234 euros. A minus only when `signed`.
    None for anything else."""
    match = _EUROS.fullmatch(text.strip(" €"))
    if not match or (match[3] and match[3] == match[4]) or (match[1] and not signed):
        return None
    number = float(re.sub(r"[.,]", "", match[2]) + "." + (match[5] or "0"))
    return -number if match[1] else number


def shown(field: Field, value: Any) -> str:  # noqa: ANN401, PLR0911 a value of the file
    """The text of `value` in the unit of `field`: euros `1.234,56`, a share or a rate in percent
    `2.5`, a month `2027-05`; empty for none, `null` for a null that differs from the default.
    `parse` reads it back to the same value."""
    if value is NULL or (value is None and field.null):
        return NULL_TEXT
    if value is ABSENT or value is None or (field.empty is not None and value == field.empty):
        return ""
    match value:
        case bool():
            return str(value).lower()
        case int() | float() if field.unit is Unit.EUR:
            return format_eur(value, cents=not float(value).is_integer(), symbol=False)
        case int() | float():
            number = float(value * 100 if field.unit is Unit.PERCENT else value)
            return np.format_float_positional(round(number, 9), trim="-")  # not 2.98000004
        case date() if field.unit is Unit.MONTH:
            return f"{value:%Y-%m}"
        case date():
            return value.isoformat()
        case list():
            return ", ".join(map(str, value))
    return str(value)


def parse(field: Field, text: str) -> Any:  # noqa: ANN401 a value of the file
    """The value of `text` typed into `field`, as the file holds it: euros with a sign, a percent
    as the fraction, a month on its first day; `NULL` for `null` where a null is a value of its
    own; None for an empty text, which takes the fallback. Raises ValueError, with what to type,
    for a text that does not read or a number outside the bounds of the model: `at least 0%`."""
    if not (text := text.strip()):
        return None
    if field.null and text == NULL_TEXT:
        return NULL
    value = _read(field, text)
    if (problem := _outside(field, value)) is not None:
        raise ValueError(problem)
    return value


def _read(field: Field, text: str) -> Any:  # noqa: ANN401 a value of the file
    match field.kind:
        case Kind.NUMBER | Kind.INTEGER:
            return _number(field, text)
        case Kind.DATE:
            return _date(field, text)
        case Kind.BOOL if text.lower() in _BOOLS:
            return _BOOLS[text.lower()]
        case Kind.CHOICE if found := [o for o in field.options if str(o) == text]:
            return found[0]
        case Kind.BOOL | Kind.CHOICE:
            options = ", ".join(map(str, field.options or ("true", "false")))
            raise ValueError(_("one of {options}").format(options=options))
        case Kind.NAMES:
            return [name for part in text.split(",") if (name := part.strip())]
        case Kind.TEXT:
            return text
    msg = f"{' '.join(field.path)}: a {field.kind} field takes no text"
    raise TypeError(msg)


def _number(field: Field, text: str) -> float:
    """A number as the file holds it: a whole one as an int, as the other writers keep it (`4`,
    not `4.0`)."""
    if field.unit is Unit.EUR:
        if (number := euros(text, signed=True)) is None:
            raise ValueError(_("type euros, such as 1.234,56 or 1234.56"))
        return _whole(number)
    plain = text.removesuffix("%").rstrip() if field.unit is Unit.PERCENT else text
    if not _DECIMAL.fullmatch(plain):
        raise ValueError(_("type a number, such as 2,5 or 2.5"))
    number = float(plain.replace(",", "."))
    if field.kind is Kind.INTEGER and not number.is_integer():
        raise ValueError(_("type a whole number"))
    # 1.1% is 0.011, not 0.011000000000000001
    return _whole(round(number / 100, 12) if field.unit is Unit.PERCENT else number)


def _whole(number: float) -> float:
    return int(number) if number.is_integer() else number


def day(text: str) -> date | None:
    """A date typed in ISO order or day first with dots, `1965-03-14` or `14.03.1965`; None for
    anything else. Bare digits stay unread: `14031965` could be either order."""
    text = text.strip()
    try:
        if _DAY.fullmatch(text):
            return date.fromisoformat(text)
        if found := _TAG.fullmatch(text):
            return date(int(found[3]), int(found[2]), int(found[1]))
    except ValueError:
        return None
    return None


def _date(field: Field, text: str) -> date:
    month = field.unit is Unit.MONTH
    try:
        if month and _MONTH.fullmatch(text):
            return date.fromisoformat(f"{text}-01")
        if month and (found := _MONAT.fullmatch(text)):
            return date(int(found[2]), int(found[1]), 1)
    except ValueError:
        pass
    if (typed := day(text)) is not None:
        return typed.replace(day=1) if month else typed
    raise ValueError(
        _("type a month, such as 2027-05 or 05.2027")
        if month
        else _("type a date, such as 1965-03-14 or 14.03.1965")
    )


def _outside(field: Field, value: Any) -> str | None:  # noqa: ANN401 a value of the file
    """What the bounds of the model ask of a number, in the unit of the field: `at most 100%`."""
    if not number(value):
        return None
    if field.low is not None and (value <= field.low if field.open_low else value < field.low):
        text = _("above {bound}") if field.open_low else _("at least {bound}")
        return text.format(bound=_bound(field, field.low))
    if field.high is not None and (value >= field.high if field.open_high else value > field.high):
        text = _("below {bound}") if field.open_high else _("at most {bound}")
        return text.format(bound=_bound(field, field.high))
    return None


def _bound(field: Field, value: float) -> str:
    symbol = SYMBOL.get(field.unit, "")
    return shown(field, value) + (symbol if field.unit is Unit.PERCENT else f" {symbol}".rstrip())


def read(field: Field, text: str, old: Any) -> Any:  # noqa: ANN401 a value of the file
    """`parse` of what a text field holds, `ABSENT` when empty. The text that `shown` gives `old`
    stays `old`: cents beyond two, which the text cannot show, are not rewritten."""
    if text.strip() == shown(field, old):
        return old
    value = parse(field, text)
    return ABSENT if value is None else value


def placeholder(field: Field, leaf: Leaf | None) -> str:
    """The fallback of an empty field with its source: `2 (default)`, `3 from base`, `1.000 from
    assumptions.yaml`. Empty without one."""
    if leaf is None or not (text := shown(field, leaf.value)):
        return ""
    return marked(text, leaf)


def marked(text: str, leaf: Leaf) -> str:
    """`text` as the fallback `leaf` with its source, in the language of the session: `2
    (default)`, `3 from base`. A source is a file or a scenario as written."""
    if leaf.source == DEFAULT:
        return _("{value} (default)").format(value=text)
    return _("{value} from {source}").format(value=text, source=leaf.source)


def messages(model: type[BaseModel]) -> Iterator[tuple[str | None, str]]:
    """The words of `model` that the forms and the grids show, as messages of the catalogue with
    their context (`i18n_check.schema`): the descriptions, the labels of the fields that a page does
    not name, their keys and the options in words, of its fields (`of`) and of its columns
    (`gridcolumns.columns`), each by the function that shows it, and the description of each field
    of the model, also of one that holds a model (`inflation`: the help of a slider of the
    explorer, `knobs._about`)."""
    found = list(of(model))
    for field in found:
        yield from ((None, text) for text in (field.about, named(field.path[-1])) if text)
        yield from (("key", key) for key in field.path)
        yield from ((None, title) for _option, title in field.titles)
    for col in [*columns(model), *(c for f in found for c in f.columns)]:
        yield from ((None, text) for text in (col.about,) if text)
        yield from (("key", key) for key in col.name.split())
        yield from ((None, title) for _option, title in col.titles)
    yield from (
        (None, oneline(f.description)) for f in model.model_fields.values() if f.description
    )


def fallback(
    model: type[BaseModel], candidate: Mapping[str, Any], paths: Iterable[KeyPath] = ()
) -> dict[KeyPath, Leaf]:
    """What each path takes from the model (`overrides.filled`) when `candidate`, a mapping of
    `model` without a parent (`assumptions.yaml`, an item of a list), lacks it: the default of its
    field in the mapping that holds it, of that mapping's own default where it goes too
    (`inflation`), nothing for a required field. The placeholder of an empty field. Of the `paths`
    that `candidate` holds, what each takes once cleared, as `overrides.fallback` gives it: so a
    field does not change its own fallback."""
    held = flatten(dict(candidate))
    found = {
        path: Leaf(value, DEFAULT)
        for path, value in flatten(filled(model, candidate)).items()
        if path not in held
    }
    for path in (p for p in paths if p in held):
        cleared = flatten(filled(model, own(candidate, {path: None})))
        found |= {p: Leaf(v, DEFAULT) for p, v in cleared.items() if p[: len(path)] == path}
    return found


def lookup(node: Any, path: Sequence[str | int]) -> Any:  # noqa: ANN401 a value of the file
    """The value at `path`, through mappings and lists, `ABSENT` where the way lacks it."""
    for key in path:
        if isinstance(node, list) and isinstance(key, int):
            node = node[key] if 0 <= key < len(node) else ABSENT
        elif isinstance(node, dict):
            node = node.get(key, ABSENT)
        else:
            return ABSENT
    return node


def dicts(value: object) -> list[dict[str, Any]]:
    """The mappings of a list of rows, none of anything else."""
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else []
