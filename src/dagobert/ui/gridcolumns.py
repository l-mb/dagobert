"""The columns of a grid, derived from the pydantic models: their type, unit, bounds and help come
from the JSON schema, their options from an enum. A column keeps the English of the model, and
its header and help speak the language of the session where the grid draws (`header`, `help`)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import date
from functools import cache
from typing import Any, TypeIs, get_args

import pandas as pd
import streamlit as st
from pydantic import BaseModel
from streamlit.elements.lib.column_types import ColumnConfig

from dagobert.i18n import N_, _, pgettext
from dagobert.model.assets import Asset, HoldingsAsset
from dagobert.model.base import TITLES, KeyPath, Unit
from dagobert.money import EUR_COLUMN, NUMBER_COLUMN, format_eur
from dagobert.store import NULL

ASSET_MODELS: dict[str, type[BaseModel]] = {
    get_args(model.model_fields["kind"].annotation)[0]: model
    for model in get_args(get_args(Asset)[0])
}
HOLDING_KINDS = frozenset(k for k, m in ASSET_MODELS.items() if issubclass(m, HoldingsAsset))
ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"
ISO_MONTH = r"^\d{4}-\d{2}(-\d{2})?$"  # a day too: any day reads as the first
# Pixels by column name, else by type: grouped grids must line up. A header needs about 38
# pixels besides its text, a cell 16.
WIDTHS = {
    "name": 200,
    "category": 160,  # of the Spend page
    "deduct": 240,  # of an expense: `haushaltsnahe Dienstleistung (§35a)`
    "entry": 72,  # an entry of a mapping, such as a phase: the bold total below it fits too
    "string": 105,
    "number": 88,
    "integer": 70,
    "date": 82,  # an ISO date
    "array": 90,
}
# A grid shows euros whole and grouped like the tiles, a share or a rate in percent, as typed, a
# plain number with its decimals: a printf format reads the same in every browser language
FORMATS: dict[Unit | None, str] = {
    Unit.EUR: EUR_COLUMN,
    Unit.PERCENT: "%g%%",
    Unit.NUMBER: NUMBER_COLUMN,
}
PERCENT_HELP = N_("In percent: 2.5 for 2.5%.")
# the help of an entry of a mapping of numbers per phase without a gate (`Column.entries`)
ENTRY_HELP = N_("{key} in the {phase} phase, empty means 1")
DEFAULT_HELP = N_("{text} (default: {value})")  # a help that names the default of its field
# pixels of the header of an entry of a mapping (a phase) besides its text, and per character
ENTRY_PAD, ENTRY_CHAR = 40, 7


Row = dict[str, Any]
Bounds = tuple[float | None, float | None]  # of a number, in the unit of the file


def keyword(key: str) -> str:
    """A key of the inputs as the pages name it, in the language of the session: the key itself
    in English (`cash_buffer_months`, as the grids head their columns), its word in German."""
    return pgettext("key", key)


def keywords(name: str) -> str:
    """The keys of a column name or a key path, each as the pages name it: `loan balance`."""
    return " ".join(map(keyword, name.split()))


def in_order[T](options: Iterable[T], titles: Iterable[tuple[str, str]]) -> list[T]:
    """The options of a choice: by their words in the language of the session where the English
    lists them so (a `Land`: `Niedersachsen` after `Mecklenburg-Vorpommern`), else as the model
    lists them."""
    english = dict(titles)
    named = [english.get(str(option), str(option)) for option in options]
    if not english or named != sorted(named):
        return list(options)
    return sorted(options, key=lambda option: _(english.get(str(option), str(option))))


def oneline(text: str) -> str:
    """A description of the model on one line: the message of its help."""
    return " ".join(text.split())


def on_off(value: bool) -> str:
    """A switch in words: `on` or `off`."""
    return _("on") if value else _("off")


def default_said(value: object, unit: Unit | None) -> str | None:
    """A default as a help names it, in the language of the session: `on`, `1.000 €`, `30%`,
    `105`; None for none, a list or a mapping."""
    match value:
        case bool():
            return on_off(value)
        case int() | float() if unit is Unit.EUR:
            return format_eur(value)
        case int() | float() if unit is Unit.PERCENT:
            return f"{value * 100:g}%"
        case int() | float():
            return f"{value:g}"
        case str():
            return value
    return None


def said(about: str, named: str | None = None, more: Iterable[str] = (), **fields: str) -> str:
    """A help in the language of the session from its English parts: `about` (a description of
    the model or a help of a page), the default that it names, `named` (`(default: 30%)`), and the
    sentences `more`, each a message of the catalogue, formatted with `fields`. An empty default
    (the text of a `note`) names none."""
    text = _(about).format(**fields) if about else ""
    if named:
        text = _(DEFAULT_HELP).format(text=text.rstrip("."), value=named).strip()
    for sentence in more:
        text = also(text, _(sentence).format(**fields))
    return text


def _names(value: object) -> list[str]:
    """The cells of a list: one name reads as a list of one (`from` of an inheritance), a null
    written by hand as none, not as the chip `None`."""
    if value is None:
        return []
    return [str(v) for v in (value if isinstance(value, list) else [value])]


@dataclass(frozen=True)
class Column:
    """One model field as a table column. It keeps the English of the model: its `header` and its
    `help` speak the language of the session. `about` is the description of the field (or a help of
    the page that replaces it), `named` the default that the help names, `more` the sentences after
    it, each a message of the catalogue: in them `{name}` stands for the name of the column, `{key}`
    for its key as the pages name it and `{phase}` for the phase of an entry."""

    name: str
    type: str  # JSON schema type, `date` for date strings, `rows` for a list of mappings
    options: tuple[str, ...]
    default: Any
    required: bool
    about: str
    key: str  # YAML key, differs from `name` for one entry of a mapping
    part: str | None = None  # entry of the mapping `key`
    gate: str | None = None  # list field that names the active entries; 0 in the cell is "off"
    label: str | None = None  # the header, if not `name`: the phase of a `factor` cell
    unit: Unit | None = None  # how a number shows and reads: euros, percent, plain
    bounds: Bounds = (None, None)
    empty: object = None  # the value besides a number that an empty cell stands for: `all`
    null: bool = False  # an explicit null differs from the default (`index` null: nominal)
    new: bool = False  # a list takes names besides its options, such as a new tag
    inner: str | None = None  # the field of the row whose mapping holds this one, see `columns`
    titles: tuple[tuple[str, str], ...] = ()  # the options in words (`model.base.Titled`)
    # a number that the file keeps below zero, shown without its minus: the loan of a purchase,
    # whose header names the direction. The table saves it negative (`Table.negative`)
    unsigned: bool = False
    named: object = None  # the default that the help names (`default_said`): `30%`
    more: tuple[str, ...] = ()
    per_phase: bool = False  # an entry of a mapping per phase: `label` is the label of the phase

    @property
    def header(self) -> str:
        """The header in the language of the session: the label of a phase as written, a label of
        the page in words, else the keys of the name (`keywords`)."""
        if self.per_phase and self.label is not None:
            return self.label
        return _(self.label) if self.label else keywords(self.name)

    @property
    def help(self) -> str:
        """The help in the language of the session (`said`): of an entry by its phase."""
        phase = self.label or str(self.part)
        titles = dict(self.titles)
        return said(
            self.about,
            _(titles[self.named])
            if isinstance(self.named, str) and self.named in titles
            else default_said(self.named, self.unit),
            self.more,
            name=self.name,
            key=keyword(self.key),
            phase=phase,
        )

    @property
    def said_name(self) -> str:
        """The name of the column in a sentence, such as a line of the save guard: its keys as the
        pages name them, of an entry its phase as written (`factor work`)."""
        if self.per_phase:
            return f"{keyword(self.key)} {self.part}"
        return keywords(self.name)

    @classmethod
    def of(
        cls, name: str, prop: dict[str, Any], schema: dict[str, Any], *, required: bool = False
    ) -> list[Column]:
        """One column per field. A mapping of numbers by name (`factor` per phase) gets one
        column of the type `object` with the unit and bounds of its numbers, which a table turns
        into a number column per name (`Table.entries`); a nested model (`when` of a sale) one
        column per field, so nobody types a mapping into a cell."""
        spec = resolve(_value(prop), schema)
        entry = spec.get("additionalProperties")
        if isinstance(entry, dict) and spec.get("type") == "object":
            return [
                cls(
                    name,
                    "object",
                    (),
                    None,
                    False,
                    ENTRY_HELP,
                    name,
                    unit=_unit(entry),
                    bounds=_bounds(entry),
                )
            ]
        if "properties" in spec:  # one level: a nested model holds numbers, names and dates
            return [
                replace(c, name=f"{name} {c.name}", key=name, part=c.key, required=False)
                for c in _fields(spec, schema)
                if c.part is None
            ]
        return [cls._plain(name, prop, spec, schema, required=required)]

    @classmethod
    def _plain(
        cls,
        name: str,
        prop: dict[str, Any],
        spec: dict[str, Any],
        schema: dict[str, Any],
        *,
        required: bool,
    ) -> Column:
        items = resolve(spec.get("items", {}), schema)
        default, unit, union = prop.get("default"), _unit(spec), prop.get("anyOf", [])
        return cls(
            name=name,
            key=name,
            type="date"
            if spec.get("format") == "date"
            else "rows"
            if _is_row(items, schema)
            else spec.get("type", "string"),
            options=tuple(spec.get("enum") or items.get("enum") or ()),
            titles=tuple((spec.get(TITLES) or items.get(TITLES) or {}).items()),
            default=default,
            required=required,
            about=oneline(prop.get("description") or ""),
            named=default,
            more=(PERCENT_HELP,) if unit is Unit.PERCENT else (),
            unit=unit,
            bounds=_bounds(spec),
            empty=next((option["const"] for option in union if "const" in option), None),
            null=default is not None and any(option.get("type") == "null" for option in union),
        )

    @property
    def width(self) -> int:
        if self.part is not None and self.label is not None:  # an entry of a mapping: a phase
            return max(WIDTHS["entry"], ENTRY_PAD + ENTRY_CHAR * len(self.label))
        return WIDTHS.get(self.name, WIDTHS.get(self.type, 110))

    def entries(self, named: Mapping[str, str]) -> list[Column]:
        """A mapping column (`object`) as one number column per entry of `named`, by key with its
        header: `factor work`, headed by the label of the phase."""
        return [
            replace(
                self,
                name=f"{self.name} {key}",
                type="number",
                part=key,
                label=label,
                per_phase=True,
            )
            for key, label in named.items()
        ]

    def config(self, *, fixed_width: bool = False) -> ColumnConfig:  # noqa: PLR0911
        """The column of the grid, its header and help in the language of the session. A number
        takes the format, the bounds and the step of its unit: a minimum of 0 keeps the minus off
        the cell editor. A share or a rate takes no maximum, which the grid would put in silently:
        the guard warns above 100%, the model refuses the bound on save. Without a step of its
        unit a float takes any decimals."""
        common: dict[str, Any] = {
            "width": self.width if fixed_width else None,
            "label": self.header,
            "help": self.help or None,
            "required": self.required,
        }
        match self.type:
            case "number" | "integer":
                low, high = (None if b is None else self._scaled(b) for b in self.bounds)
                return st.column_config.NumberColumn(
                    **common,
                    format=FORMATS.get(self.unit),
                    min_value=low,
                    max_value=None if self.unit is Unit.PERCENT else high,
                    step=1 if self.type == "integer" else self.unit.step if self.unit else None,
                    default=1 if self.gate else None,
                )
            case "boolean":
                return st.column_config.CheckboxColumn(
                    self.header, help=self.help or None, width=common["width"], default=self.checked
                )
            case "date":  # a DateColumn edits in the browser locale (mm/dd/yyyy)
                return st.column_config.TextColumn(
                    **common, validate=ISO_MONTH if self.month else ISO_DATE
                )
            case "array" if self.options:
                return st.column_config.MultiselectColumn(
                    **common, options=list(self.options), accept_new_options=self.new
                )
            case "array":
                return st.column_config.ListColumn(**common)
            case _ if self.options:
                titles = {option: _(title) for option, title in self.titles}
                return st.column_config.SelectboxColumn(
                    **common,
                    options=[
                        *in_order(self.options, self.titles),
                        *(["null"] if self.null else []),
                    ],
                    format_func=(lambda o: titles.get(str(o), str(o))) if titles else None,
                )
            case _:
                return st.column_config.TextColumn(**common)

    @property
    def month(self) -> bool:
        """Whether the column holds a calendar month: its cell shows `2027-05`, as a form does."""
        return self.unit is Unit.MONTH

    @property
    def checked(self) -> bool | None:
        """What an empty checkbox stands for: its default, which an empty cell would hide (it
        reads as false), also in a new row. None for another column."""
        return self.default if self.type == "boolean" and isinstance(self.default, bool) else None

    def shown(self, row: Row) -> object:
        """Cell value for a YAML row. A missing key, or an explicit null, stays empty like a
        missing one, the help names the default; a checkbox shows its default, since an empty one
        reads as false. A share or a rate shows in percent."""
        holder = (row.get(self.inner) or {}) if self.inner else row
        if self.part is not None:
            return self._cell(self.entry(holder))
        if self.key not in holder:
            return [] if self.type == "array" else self.checked
        value = holder[self.key]
        match self.type:
            case "date":
                return str(value)[: 7 if self.month else 10]
            case "array":
                return _names(value)
            case "string" if value is None:
                return "null"
            case _:
                return self._cell(value)

    def entry(self, holder: Row) -> object:
        """The entry `part` of the mapping `key` in `holder`, as the file holds it. A gated
        entry is 0 where the gate leaves it out and 1 without one: an empty cell that applies
        reads oddly."""
        gated = holder.get(self.gate) if self.gate is not None else None
        if gated is not None and self.part not in gated:
            return 0.0
        return (holder.get(self.key) or {}).get(self.part, 1.0 if self.gate else None)

    def _cell(self, value: object) -> object:
        if value is None or value == self.empty:
            return None
        if number(value):
            return abs(value) if self.unsigned else self._scaled(value)
        return value

    def _scaled(self, value: float) -> float:
        """A number of the file as the cell shows it: a share or a rate in percent."""
        return round(value * 100, 9) if self.unit is Unit.PERCENT else value  # not 2.98000004

    def stored(self, value: object) -> object:  # noqa: PLR0911
        """YAML value for an edited cell. None removes the key, so does a checkbox at its default,
        which a new row shows. A percent becomes the fraction. An emptied list stays `[]` where
        none would mean another thing: a required one (`phases` of a bAV policy) or one with a
        default."""
        if value is None or value == "" or (isinstance(value, float) and pd.isna(value)):
            return None
        if self.checked is not None and value == self.checked:
            return None
        match self.type:
            case "date" if self.month:
                return date.fromisoformat(f"{str(value)[:7]}-01")
            case "date":
                return date.fromisoformat(str(value)[:10])
            case "integer" if isinstance(value, int | float):
                return int(value)
            case "number" if self.unit is Unit.PERCENT and isinstance(value, int | float):
                return round(value / 100, 12)  # 1.1 / 100 is 0.011000000000000001
            case "array" if isinstance(value, list):
                return value if value or self.default or self.required else None
            case "string" if value == "null":
                return NULL
            case _:
                return value


def resolve(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """`spec`, or the model that its `$ref` names in `schema`."""
    return schema["$defs"][spec["$ref"].rsplit("/", 1)[1]] if "$ref" in spec else spec


def _value(prop: dict[str, Any]) -> dict[str, Any]:
    """The schema of a field without its null; of `float | "all"` the number."""
    return next(p for p in prop.get("anyOf", [prop]) if p.get("type") != "null")


def _unit(spec: dict[str, Any]) -> Unit | None:
    return Unit(spec["unit"]) if "unit" in spec else None


def _bounds(spec: dict[str, Any]) -> Bounds:
    """The bounds of a number. A grid has no exclusive ones: the model refuses the bound."""
    return (
        spec.get("minimum", spec.get("exclusiveMinimum")),
        spec.get("maximum", spec.get("exclusiveMaximum")),
    )


def also(text: str, more: str) -> str:
    """`more` as a sentence after `text`: the descriptions of the model end without a stop."""
    return f"{text.rstrip('.')}. {more}" if text and more else text or more


def number(value: object) -> TypeIs[float]:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _is_row(spec: dict[str, Any], schema: dict[str, Any]) -> bool:
    """Whether the items of a list are mappings, also of several models (`then` of a sale)."""
    spec = resolve(spec, schema)
    union = spec.get("anyOf", [])
    return spec.get("type") == "object" or (bool(union) and all(_is_row(p, schema) for p in union))


def _fields(spec: dict[str, Any], schema: dict[str, Any]) -> Iterator[Column]:
    required = spec.get("required", ())
    for name, prop in spec["properties"].items():
        yield from Column.of(name, prop, schema, required=name in required)


def columns(
    model: type[BaseModel], skip: frozenset[str] = frozenset(), lift: str | None = None
) -> list[Column]:
    """Lists of mappings (`trades`, `then`) are left out, they get a table of their own. The
    fields of the nested model `lift` (`stream` of an `add_stream`) take a column each, under
    their own names: the model and the nested one share no field name."""
    schema = model.model_json_schema()
    found = [
        replace(col, inner=name) if name == lift else col
        for name, prop in schema["properties"].items()
        if name not in skip
        for col in (
            _fields(resolve(_value(prop), schema), schema)
            if name == lift
            else Column.of(name, prop, schema, required=name in schema.get("required", ()))
        )
    ]
    return [col for col in found if col.type != "rows" and col.key not in skip]


def _guard_name(col: Column) -> str:
    """The name that the save guard gives a cell of `col` (`guard.changes`): the name of the
    column, after the nested model it is lifted from."""
    return " ".join(filter(None, (col.inner, col.name)))


def units(cols: Iterable[Column]) -> dict[str, Unit]:
    """The unit of each column by the name that the save guard gives its cells."""
    return {_guard_name(c): c.unit for c in cols if c.unit}


def names(cols: Iterable[Column]) -> dict[str, str]:
    """Each column in a sentence (`Column.said_name`) by the name that the save guard gives its
    cells."""
    return {
        _guard_name(c): " ".join(filter(None, (c.inner and keyword(c.inner), c.said_name)))
        for c in cols
    }


@cache
def key_paths(model: type[BaseModel], lift: str | None = None) -> dict[str, KeyPath]:
    """The key path in a row of each column of `model` by its name: `loan balance` is `("loan",
    "balance")`, a field lifted from `lift` lies in it (`columns`)."""
    return {
        c.name: tuple(filter(None, (c.inner, c.key, c.part))) for c in columns(model, lift=lift)
    }


@cache
def _asset_columns() -> tuple[Column, ...]:
    return tuple(c for model in ASSET_MODELS.values() for c in columns(model))


@cache
def asset_units() -> dict[str, Unit]:
    """The units of the fields of every asset kind: one name has one unit."""
    return units(_asset_columns())


def asset_names() -> dict[str, str]:
    """The fields of every asset kind as a line of the save guard names them (`names`), in the
    language of the session, so not cached."""
    return names(_asset_columns())
