"""The widget of each kind of field of a form (`ui.fields`): what it shows of a value of the file,
and what it holds after an edit, `ABSENT` when empty, the old value while untouched."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, cast

import streamlit as st

from dagobert.i18n import N_, _
from dagobert.model.base import Unit
from dagobert.overrides import DEFAULT, Leaf
from dagobert.store import NULL, RowEdits
from dagobert.ui import fold, is_mobile
from dagobert.ui.fields import ABSENT, Field, Kind, marked, placeholder, read, shown
from dagobert.ui.gridcolumns import Column, also, in_order, number
from dagobert.ui.gridstate import carry, frame
from dagobert.ui.tables import Computed, MapRows, pin, small_grid

PROSE = frozenset({"name", "note"})  # text for people, which a phone may start with a capital
LONG = frozenset({"note"})  # text that takes a text area
WIDTH = 220  # pixels of a field on a desktop, where the fields of one model share a row
SHAPE: dict[Unit | None, str] = {
    Unit.MONTH: N_("YYYY-MM or MM.YYYY"),
    Unit.DATE: N_("YYYY-MM-DD or DD.MM.YYYY"),
}
KEY = Column(
    name="name", type="string", options=(), default=None, required=True, about="", key="name"
)  # the key column of a mapping by name


@dataclass(frozen=True)
class Names:
    """The options of a field that names something in the inputs (`references.References.names`).
    `new`: a name that is not there yet is legal, such as a new tag."""

    names: tuple[str, ...]
    new: bool = False


@dataclass(frozen=True)
class Spot:
    """Where a widget draws: its key, its label, the fallback of its field, the names it takes,
    whether its form is an override (an empty field inherits), what null stands for where the
    model takes it: the label of the toggle of a list (`Default` without one), the option of a
    choice (`null` without one; `care.index`: nominal), the header of the key column of a
    mapping by name (`name` without one; `returns`: `asset class`), the words of the options of a
    choice (`rv`: `By profit` for `income`), why the field has no effect now (it shows disabled,
    `off` after its label), the rows of a mapping by name (`MapRows` without them), its columns
    that the mode hides (`hidden`: of a mapping while no entry holds them, of a list of rows
    always) and the read-only columns of a list of rows (`computed`: the age of a phase change).
    The texts are in the language of the session (`forms.Form` translates them)."""

    key: str
    label: str
    leaf: Leaf | None = None
    names: Names | None = None
    override: bool = False
    none: str | None = None
    key_label: str | None = None
    words: Mapping[object, str] = dataclasses.field(default_factory=dict)
    off: str = ""
    rows: MapRows | None = None
    hidden: frozenset[str] = frozenset()
    computed: tuple[Computed, ...] = ()


def prefix(field: Field) -> str:
    """The start of the widget key that sets the keyboard of a phone (`ui.keyboard`): the decimal
    keypad for a number in a text field whose bounds allow no minus, which the keypad may lack;
    no capital first letter for an id or a name that may be typed."""
    if field.kind is Kind.NUMBER:
        return "decimal-" if field.low is not None and field.low >= 0 else ""
    if field.kind in (Kind.CHOICE, Kind.NAMES, Kind.MAP) or (
        field.kind is Kind.TEXT and field.path[-1] not in PROSE
    ):
        return "nocaps-"
    return ""


def same(old: object, new: object) -> bool:
    """Equal in value and kind (a bool is no number). A null of the file is `NULL`."""
    old, new = (NULL if v is None else v for v in (old, new))
    if isinstance(old, bool) or isinstance(new, bool):
        return type(old) is type(new) and old == new
    return bool(old == new)


def _option(field: Field, option: object, spot: Spot) -> str:
    """An option, null by what it stands for, marked where it is the fallback of an empty field:
    `m (default)`."""
    leaf = spot.leaf
    title = dict(field.titles).get(str(option))
    words = spot.words.get(option) or (_(title) if title else None)
    text = (spot.none if option is NULL else None) or words or shown(field, option) or str(option)
    return text if leaf is None or not same(leaf.value, option) else marked(text, leaf)


def _seed(key: str, value: object) -> None:
    """The value of the file as the first state of a widget whose own default stays empty: a
    number input or a select box that starts with a value has no empty state, so it could not be
    cleared again to take the fallback."""
    if value is not ABSENT and key not in st.session_state:
        st.session_state[key] = value


def _kept(old: object, held: object, picked: object) -> object:
    """What a choice holds: `old` while it shows what the file holds, `ABSENT` when cleared (an
    empty choice is no null, which is an option of its own)."""
    if picked is None:
        return old if held is ABSENT else ABSENT
    return old if same(picked, held) else picked


def plain(field: Field, old: object, spot: Spot) -> Any:  # noqa: ANN401, PLR0911 a file value
    """The widget of a field that is no section, list of rows or mapping by name. One that is off
    says why after the label of a bool, else in place of its fallback: a label of 220 px wraps.
    Raises ValueError for a text that does not read."""
    hint = spot.off or placeholder(field, spot.leaf)
    width: int | Literal["stretch"] = "stretch" if is_mobile() else WIDTH
    off = spot.off and field.kind is Kind.BOOL
    common: dict[str, Any] = {
        "label": f"{spot.label} ({spot.off})" if off else spot.label,
        "help": field.help or None,
        "key": spot.key,
        "disabled": bool(spot.off),
    }
    held = NULL if old is None and field.null else ABSENT if old is None else old
    known = (
        [True, False]
        if field.kind is Kind.BOOL
        else list(spot.names.names if spot.names else in_order(field.options, field.titles))
    )
    choices = [*known, *([NULL] if field.null and known else [])]
    if held is not ABSENT and choices and field.kind is not Kind.NAMES and held not in choices:
        choices.append(held)  # a name that the inputs lack: the check names it
    match field.kind:
        case Kind.BOOL if not spot.override:
            # a toggle shows no other value than a bool: the model names one
            effective = old if isinstance(old, bool) else bool(spot.leaf and spot.leaf.value)
            toggled = st.toggle(**common, value=effective)
            return old if toggled == effective else toggled
        case Kind.BOOL | Kind.CHOICE if len(choices) <= 4 and not spot.names:
            picked = st.segmented_control(
                **common,
                options=choices,
                format_func=lambda o: _option(field, o, spot),
                default=None if held is ABSENT else held,
                width="stretch" if is_mobile() else "content",  # the fallback lengthens an option
            )
            return _kept(old, held, picked)
        case Kind.CHOICE | Kind.TEXT if spot.names and not spot.names.new and not choices:
            # nothing in the inputs fits: no field to type a name that the check refuses
            st.selectbox(
                spot.label,
                help=also(field.help, _("Nothing in the inputs fits here.")),
                key=spot.key,
                options=[],
                index=None,
                placeholder=hint or spot.none or _("Nothing to choose"),
                disabled=True,
                width=width,
            )
            return old
        case Kind.CHOICE | Kind.TEXT if choices:
            _seed(spot.key, held)
            picked = st.selectbox(
                **common,
                options=choices,
                index=None,
                format_func=lambda o: _option(field, o, spot),
                # empty is null where null is the default: `Form.nulls` names it (`extends`)
                placeholder=hint or (None if field.null else spot.none) or _("Choose"),
                accept_new_options=bool(spot.names and spot.names.new),
                width=width,
            )
            return _kept(old, held, picked)
        case Kind.NAMES:
            return _names(field, old, spot, known, common=common)
        case Kind.INTEGER if held is ABSENT or _fits(field, old):
            low, high = _whole(field)
            before = None if held is ABSENT else int(cast("float", old))  # `_fits` checked it
            _seed(spot.key, ABSENT if before is None else before)
            number = st.number_input(
                **common,
                value=None,
                min_value=low,
                max_value=high,
                step=1,
                placeholder=hint or None,
                width=width,
            )
            return old if number == before else ABSENT if number is None else number
        case Kind.TEXT if field.path[-1] in LONG:
            text = st.text_area(**common, value=shown(field, old), placeholder=hint)
            return read(field, text, old)
    shape = SHAPE.get(field.unit)
    text = st.text_input(
        **common, value=shown(field, old), placeholder=hint or (shape and _(shape)), width=width
    )
    return read(field, text, old)


def _names(
    field: Field,
    old: object,
    spot: Spot,
    known: list[Any],
    *,
    common: dict[str, Any],
) -> object:
    """A list of names as a multiselect, which takes the rest of its row: a field of 220 px cut
    its second name. Empty is `ABSENT`, one name of the file a list of one. A list that the model
    also takes as null (`age_categories`: null is every category) has a toggle that stands for
    null, so an empty list is a value of its own; null is the default, or in an override an
    explicit null over an inherited list."""
    # one name reads as a list of one (`from` of an inheritance)
    listed = (
        [str(n) for n in old] if isinstance(old, list) else [old] if isinstance(old, str) else []
    )
    # what an empty field stands for: in an override what it inherits, else its default (not the
    # fallback of the candidate, which follows what this field holds)
    inherited = spot.leaf.value if spot.override and spot.leaf else field.default
    nulled = old is None or (old is ABSENT and inherited is None)
    off = field.nullable and st.toggle(
        spot.none or _("Default"), value=nulled, key=f"{spot.key}-null", help=field.help or None
    )
    picked = (
        None
        if off
        else st.multiselect(
            **common,
            options=[*known, *(n for n in listed if n not in known)],
            default=listed,
            placeholder=placeholder(field, spot.leaf) or _("Choose"),
            accept_new_options=not known or bool(spot.names and spot.names.new),
            width="stretch",
        )
    )
    if off == (field.nullable and nulled) and (off or picked == listed):
        return old
    if off:
        return NULL if spot.override and inherited is not None else ABSENT
    return picked if picked or field.nullable else ABSENT


def _fits(field: Field, value: object) -> bool:
    """Whether a number input can show `value`: a whole number within the bounds of the field."""
    low, high = _whole(field)
    return (
        number(value)
        and float(value).is_integer()
        and (low is None or value >= low)
        and (high is None or value <= high)
    )


def _whole(field: Field) -> tuple[int | None, int | None]:
    """The bounds of a whole number: `gt=0` is at least 1."""
    low = None if field.low is None else int(field.low) + field.open_low
    high = None if field.high is None else int(field.high) - field.open_high
    return low, high


def section(field: Field, old: object, spot: Spot, *, inherited: bool) -> bool:
    """The heading of an optional section, its help and the toggle `Use`: on while the file holds
    it, in an override also while it `inherited` it. One that is off (`Spot.off`) says why after
    `Use` and cannot be turned on, but off: the model refuses it there."""
    _heading(field, spot)
    on = isinstance(old, dict) or inherited
    label = f"{_('Use')} ({spot.off})" if spot.off else _("Use")
    return st.toggle(label, value=on, key=spot.key, disabled=bool(spot.off) and not on)


def _heading(field: Field, spot: Spot) -> None:
    """The label of a section, a list or a mapping as a heading, its help folded below it."""
    st.markdown(f"**{spot.label}**")
    if help_text := field.help:
        fold(help_text, _("About {label}").format(label=spot.label))


def _own(spot: Spot, old: object) -> bool:
    """In an override, the toggle `Override` of a list or a mapping: off while it inherits."""
    return not spot.override or st.toggle(
        _("Override"), value=old is not ABSENT, key=f"{spot.key}-own"
    )


def _inherited(cols: list[Column], rows: list[dict[str, Any]], spot: Spot) -> None:
    """What a list or a mapping inherits, read only."""
    if spot.leaf is not None and rows:
        st.caption(
            _("Inherited by default:")
            if spot.leaf.source == DEFAULT
            else _("Inherited from {source}:").format(source=spot.leaf.source)
        )
        st.dataframe(
            frame(cols, rows), column_config=_config(cols), hide_index=True, placeholder=""
        )


def _config(cols: Sequence[Column]) -> dict[str, Any]:
    """The column configs of a small grid, its first column pinned on a phone."""
    config = {c.name: c.config() for c in cols}
    pin(config, cols[0].name)
    return config


def _editor(
    cols: list[Column],
    rows: list[dict[str, Any]],
    key: str,
    *,
    add_only: bool = False,
    shown: list[Column] | None = None,
    extra: Sequence[Computed] = (),
) -> RowEdits:
    """A small grid of `rows` (`tables.small_grid`) and its edits by their indices, so the store
    keeps the comments and the layout of the rows it does not change."""
    return small_grid(cols, list(enumerate(rows)), key, shown=shown, add_only=add_only, extra=extra)


def rows(field: Field, old: object, spot: Spot) -> object:
    """A list of rows as a small grid in the units of its columns, without those that the mode
    hides (`Spot.hidden`), with the read-only columns of `Spot.computed`. A list of the file gives
    `RowEdits`, kept per row and cell; without one, the rows as a list (`ABSENT` for none). In an
    override the toggle `Override` starts it from the inherited list; off shows that list read
    only."""
    _heading(field, spot)
    cols = list(field.columns)
    shown = [c for c in cols if c.name not in spot.hidden] if spot.hidden else None
    inherited = spot.leaf.value if spot.leaf and isinstance(spot.leaf.value, list) else []
    if not _own(spot, old):
        _inherited(shown or cols, inherited, spot)
        return ABSENT
    held = old if isinstance(old, list) else inherited if spot.override else []
    edits = _editor(cols, held, spot.key, shown=shown, extra=spot.computed)
    return edits if isinstance(old, list) else edits.result(held) or ABSENT


def mapping(field: Field, old: object, spot: Spot) -> object:
    """A mapping by name (`returns`, `scale.categories`) as a small grid with a key column
    (`tables.MapRows`), whose options are the names of `spot`. Rows with a `lead` column show it
    first and the key column behind `All columns` (the phases), and so do the columns that the
    mode hides while no entry holds them (`Spot.hidden`). In an override it adds entries and
    removes none (an override cannot remove a key); the toggle `Override` starts it, off shows
    the inherited mapping read only. Returns the mapping, `old` while unchanged; an entry whose
    row shows as before keeps what the file holds (a label equal to its default)."""
    _heading(field, spot)
    scalar = [c.name for c in field.columns] == ["value"]
    rows_of = spot.rows or MapRows(value="value" if scalar else None)
    names = spot.names.names if spot.names else ()
    key = replace(KEY, options=names, label=spot.key_label)
    cols = [key, *field.columns]
    inherited = spot.leaf.value if spot.leaf and isinstance(spot.leaf.value, dict) else {}
    if not _own(spot, old):
        _inherited(cols, rows_of.rows(inherited), spot)
        return ABSENT
    held = old if isinstance(old, dict) else {}
    before = rows_of.rows(held)
    rare = {n for n in spot.hidden if not any(n in row for row in before)}
    if rows_of.lead:
        cols = [*sorted(field.columns, key=lambda c: c.name != rows_of.lead), key]
        rare.add(key.name)
    shown = cols
    if rare and not st.toggle(
        _("All columns"),
        key=f"{spot.key}-more",
        on_change=carry,
        args=({spot.key: len(before)},),
    ):
        shown = [c for c in cols if c.name not in rare]
    edits = _editor(cols, before, spot.key, add_only=spot.override, shown=shown)
    after = {
        name: held[name]
        if name in held and rows_of.rows({name: held[name]}) == rows_of.rows({name: entry})
        else entry
        for name, entry in rows_of.mapping(edits.result(before)).items()
    }
    return old if after == held else after or ABSENT
