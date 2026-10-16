"""The overrides by id of a scenario file as grids, a part of the `Overrides` tab: `Dates`
(`shift`), `Event fields` (`events`) and `Assets` (`assets`), each value read in the unit of its
field, with what the file inherits below each grid. They keep the rows that they showed first
(`Base`) until a save or `Discard my edits`, and refuse a save when their part changed elsewhere
since."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import streamlit as st
import yaml
from streamlit.delta_generator import DeltaGenerator

from dagobert import i18n, loader, overrides, revisions, scenariofiles, store
from dagobert.i18n import N_, NP_, _, pgettext
from dagobert.loader import flatten
from dagobert.model.base import KeyPath, Unit
from dagobert.model.months import add_months
from dagobert.model.plan import SCENARIO_KEYS
from dagobert.money import PERCENT
from dagobert.overrides import Leaf
from dagobert.references import Kind, References
from dagobert.ui import fields, formguard, gridstate, guard, joined, literal, tables
from dagobert.ui.events import TYPES
from dagobert.ui.gridcolumns import ASSET_MODELS, Column, Row, keyword, number
from dagobert.ui.lineage import read_only
from dagobert.ui.save import Grid, changed_at, discard, stays
from dagobert.ui.widgets import same

if TYPE_CHECKING:
    from pydantic import BaseModel

    from dagobert.problems import Keys

KEY = "overrides"
OWN: Keys = ("overrides",)  # where a scenario file holds its overrides
# what a row of `events` or `assets` sets whole: a value of one line
LEAVES = frozenset(
    {
        fields.Kind.NUMBER,
        fields.Kind.INTEGER,
        fields.Kind.DATE,
        fields.Kind.CHOICE,
        fields.Kind.BOOL,
        fields.Kind.TEXT,
        fields.Kind.NAMES,
    }
)
NOT_SET = {  # the fields that name or describe an item, which no override sets
    "events": frozenset({"type", "id", "note"}),
    "assets": frozenset({"id", "name", "tags", "asof", "update_every"}),
}
SUFFIX: dict[Unit | None, str] = {Unit.EUR: " €"}  # a percent takes `money.PERCENT`
MONTHS = fields.Field(("months",), fields.Kind.INTEGER, unit=Unit.MONTHS)
# the overrides by id, each a grid; `shift` is no field of a model: the guard names it by its word
GRIDS = (NP_("key", "shift"), "events", "assets")
# the help of the columns of the grids by id, and the header of those that name no key of a model
HELP = {
    "id": N_("The id of the phases and events that the row changes, as their files write it."),
    "asset": N_("The asset whose field the row sets."),
    "months": N_("How many months every phase and event with this id moves: below zero earlier."),
    "field": N_(
        "The field that the row sets. The save refuses a field that no item of the id has."
    ),
    "value": N_(
        "In the unit of the field: euros 1.234,56, a share or a rate in percent (7 for 7%), a "
        "month 2027-05, a date 2027-05-14, true or false, names with commas between them. Empty, "
        "or a deleted row: the field takes the value of the item again."
    ),
}
HEADS = {"months": N_("months"), "field": N_("field"), "value": N_("value")}
GRID_HELP = {
    "shift": N_(
        "Moves every phase and event with the id by whole months, here and in the scenarios that "
        "extend this one."
    ),
    "events": N_(
        "Sets a field of every event with the id that has the field: a price, a sum, a month. The "
        "row replaces the value that the event file writes."
    ),
    "assets": N_(
        "Sets a field of an asset of `assets.yaml` for this scenario only: a contribution, a "
        "rate, the upkeep."
    ),
}


@cache
def settable(model: type[BaseModel], key: str) -> dict[str, fields.Field]:
    """The fields of `model` that a row of the override `key` (`events`, `assets`) sets: a value
    of one line, not a nested model or a list of rows, nor what names or describes the item."""
    return {
        f.path[0]: f
        for f in fields.of(model)
        if len(f.path) == 1 and f.kind in LEAVES and f.path[0] not in NOT_SET[key]
    }


@dataclass(frozen=True)
class ById:
    """An override by id as a grid of its rows (`overrides.rows`): `shift` moves the dates of the
    items of an id by months, `events` sets a field of the events of an id, `assets` a field of
    an asset. `ids` are the names of its first column, `known` the fields that each takes."""

    key: str
    ids: tuple[str, ...]
    known: Mapping[str, Mapping[str, fields.Field]] = dataclasses.field(default_factory=dict)

    @property
    def names(self) -> tuple[str, ...]:
        return overrides.ROWS[self.key]

    def field(self, row: Mapping[str, Any]) -> fields.Field | None:
        """The field of a row, by its id and its field: the unit of its value."""
        if self.key == "shift":
            return MONTHS
        return self.known.get(str(row.get(self.names[0])), {}).get(str(row.get("field")))

    def columns(self, rows: Sequence[Row]) -> list[Column]:
        """The columns of the grid: the id (a select, also of an id that the file holds and the
        inputs lack), then `months`, or `field` (a select) and `value` (text in its unit)."""
        first = self.names[0]
        ids = (*self.ids, *sorted({str(r[first]) for r in rows} - set(self.ids)))
        head = Column(first, "string", ids, None, False, HELP[first], first)
        if self.key == "shift":
            return [head, _column("months", "integer", (), unit=Unit.MONTHS)]
        names = {*(n for known in self.known.values() for n in known), *(r["field"] for r in rows)}
        return [
            head,
            _column("field", "string", tuple(sorted(names))),
            _column("value", "string", ()),
        ]

    def shown(self, held: Mapping[str, Any]) -> list[Row]:
        """The rows of the override as the file holds it (`held`), a value as its text."""
        return [
            row | ({"value": text(self.field(row), row["value"])} if "value" in row else {})
            for row in overrides.rows(self.key, held)
        ]

    def listed(self, held: Mapping[str, Any], found: Mapping[KeyPath, Any]) -> list[guard.Change]:
        """The guard list of `found`, changes of this override as the file holds it (`held`), each
        in the unit of its field: `events flat-sale price 160.000,00 € → 170.000,00 €`."""
        shown = [
            replace(
                self.field(dict(zip(self.names, path[1:], strict=False)))
                or fields.Field(path, fields.Kind.TEXT),
                path=path,
            )
            for path in found
        ]
        part = {self.key: dict(held)}
        return formguard.changes(part, overrides.own(part, found), shown)


def _column(name: str, kind: str, options: tuple[str, ...], unit: Unit | None = None) -> Column:
    """A column of a grid by id that names no key of a model, headed in words (`HEADS`)."""
    return Column(name, kind, options, None, False, HELP[name], name, label=HEADS[name], unit=unit)


def text(field: fields.Field | None, value: Any) -> str:  # noqa: ANN401 a value of the file
    """A value of an override in the unit of its field: `170.000 €`, `7%`, `2027-05`; of a field
    that the id does not take, as YAML."""
    if field is None:
        dumped = yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=1000)
        return dumped.strip().removesuffix("...").strip()
    found = fields.shown(field, value)
    suffix = PERCENT[i18n.language()] if field.unit is Unit.PERCENT else SUFFIX.get(field.unit, "")
    return found + suffix if found else found


def value(field: fields.Field | None, typed: str) -> Any:  # noqa: ANN401 a value of the file
    """The value of a row typed as `typed`, read in the unit of its field (`fields.parse`, which
    raises ValueError with what to type); of a field that the id does not take, as YAML. None
    for an empty one: the field inherits again."""
    if field is None:
        return yaml.safe_load(typed) if typed.strip() else None
    return fields.parse(field, typed)


def edited(
    spec: ById, held: Mapping[str, Any], edits: store.RowEdits
) -> tuple[dict[KeyPath, Any], dict[str, str]]:
    """The changes that the edits of the grid of `spec` make to its override as the file holds
    it (`held`), by override path (None clears: the field or the date inherits again), and per row
    whose value does not read or that lacks a cell the problem. A value that the row keeps stays
    as the file holds it, also under another id or field; a typed one reads in the unit of its
    field. A row of the file whose value is emptied inherits again; a new one, or one without its
    id or field, waits for them."""
    before = overrides.rows(spec.key, held)
    kept = [i for i in range(len(before)) if i not in edits.deleted]
    pairs = [*((before[i], edits.edited.get(i, {})) for i in kept), *(({}, r) for r in edits.added)]
    rows, unread = [], {}
    for old, cells in pairs:
        row = old | cells
        named = " ".join(str(row.get(n) or "?") for n in spec.names[:-1])
        if spec.key != "shift" and ("value" in cells or not old):
            typed = cells.get("value")
            try:
                row["value"] = None if typed is None else value(spec.field(row), _typed(typed))
            except ValueError as err:
                unread[named] = str(err)
                row["value"] = old.get("value")
        lacks = [n for n in spec.names if row.get(n) in (None, "")]
        if lacks and (not old or lacks != [spec.names[-1]]):
            unread.setdefault(named, _("needs {fields}").format(fields=joined(map(keyword, lacks))))
        rows.append(row)
    depth = len(spec.names) - 1
    was, now = (_by_id(m, depth) for m in (held, overrides.from_rows(spec.key, rows)))
    gone = {(spec.key, *p): None for p in was if p not in now}
    return gone | {
        (spec.key, *p): v for p, v in now.items() if p not in was or not same(was[p], v)
    }, unread


def _typed(cell: object) -> str:
    """The text of a value cell: the grid reads `null` as null, the field reads it."""
    return "null" if cell is store.NULL else str(cell)


def _by_id(mapping: Mapping[str, Any], depth: int) -> dict[KeyPath, Any]:
    """The values of an override by id, `depth` keys down, as `overrides.rows` gives its rows."""
    return {p: v for p, v in flatten(dict(mapping), depth).items() if len(p) == depth}


def moved(
    chain: Sequence[tuple[Path, Mapping[str, Any]]], shift: Mapping[str, tuple[Any, str]]
) -> list[str]:
    """Each group of items that `shift` (by id: the months and the file that sets them) moves, as
    `job-end 2027-05 → 2027-08`, from its first month as the files of the chain write it; with
    the file of a shift that this one inherits."""
    first: dict[str, date] = {}
    for _path, raw in chain:
        for key, month in (("phases", "from"), ("events", "at")):
            for row in fields.dicts(raw.get(key)):
                day, item = row.get(month), row.get("id")
                if isinstance(day, date) and isinstance(item, str):
                    first[item] = min(first.get(item, day), day)
    return [
        _("{moved} (from {source})").format(moved=line, source=source) if source else line
        for item, (months, source) in shift.items()
        if item in first and number(months) and round(months)
        for line in [f"{item} {first[item]:%Y-%m} → {add_months(first[item], round(months)):%Y-%m}"]
    ]


@dataclass(frozen=True)
class Base:
    """What the grids showed first in their generation (`nonce`): the overrides by id of the file
    (`part`) and the `Seen` of them."""

    nonce: int
    part: dict[str, Any]
    seen: revisions.Seen


def part(doc: Mapping[str, Any]) -> dict[str, Any]:
    """What the grids show of a scenario file: its overrides by id."""
    own = doc.get("overrides")
    return {k: own[k] for k in SCENARIO_KEYS if isinstance(own, dict) and k in own}


@dataclass(frozen=True)
class Here:
    """What the tab draws on: the scenario file `path`, its raw `extends` chain (the file alone
    when a parent is missing) and the names of the inputs."""

    path: Path
    chain: Sequence[tuple[Path, Mapping[str, Any]]]
    refs: References

    @property
    def data_dir(self) -> Path:
        return self.path.parents[1]

    @property
    def stem(self) -> str:
        return self.path.stem

    @property
    def file(self) -> str:
        return scenariofiles.scenario_file(self.stem)

    @property
    def key(self) -> str:
        return f"{KEY}-{self.stem}"

    def specs(self) -> list[ById]:
        """The grids: the ids that count in the file, the fields of the events of each id in the
        chain and of each asset by its kind."""
        events: dict[str, dict[str, fields.Field]] = {}
        for _path, raw in self.chain:
            for row in fields.dicts(raw.get("events")):
                model, item = TYPES.get(str(row.get("type"))), row.get("id")
                if model is not None and isinstance(item, str):
                    events[item] = settable(model, "events") | events.get(item, {})
        assets = {
            name: settable(ASSET_MODELS[site.sort], "assets")
            for name, sites in self.refs.defined[Kind.ASSET].items()
            for site in sites[:1]
            if site.sort in ASSET_MODELS
        }
        return [
            ById("shift", tuple(self.refs.names(Kind.ITEM, self.stem))),
            ById("events", tuple(self.refs.names(Kind.EVENT, self.stem)), events),
            ById("assets", tuple(self.refs.names(Kind.ASSET)), assets),
        ]

    @property
    def below(self) -> list[str]:
        """The file and the scenarios that extend it: their plans take its overrides."""
        return [self.stem, *(s for s in self.refs.parents if self.stem in self.refs.chain(s)[:-1])]


@dataclass(frozen=True)
class Grids:
    """The grids of a run: their changes by override path, the guard list, the rows whose value
    does not read, whether their part changed on disk since they were drawn while they hold
    edits, and what they add to the Save."""

    found: dict[KeyPath, Any]
    listed: list[guard.Change]
    unread: dict[str, str]
    stale: bool
    grid: Grid | None


def _widget(here: Here, nonce: int, key: str) -> str:
    return f"{here.key}-grids-{nonce}-{key}"


def _touched(key: str, old: Base) -> bool:
    """Whether the grids of the key `key` (`<Here.key>-grids`) on `old` hold edits."""
    return any(
        gridstate.touched(
            gridstate.grid_state(
                f"{key}-{old.nonce}-{k}", len(overrides.rows(k, old.part.get(k, {})))
            )
        )
        for k in GRIDS
    )


def unsaved(stem: str) -> bool:
    """Whether the grids of the scenario `stem` hold edits not saved yet, before they draw."""
    key = f"{KEY}-{stem}-grids"
    held: Base | None = st.session_state.get(f"{key}-base")
    return (
        held is not None
        and held.nonce == st.session_state.get(f"{key}-nonce")
        and _touched(key, held)
    )


def _base(here: Here) -> tuple[Base, revisions.ConflictError | None]:
    """The base of the grids, whose nonce is `<key>-nonce`: it stays while they hold edits, with
    the change of their part since; without edits a changed part starts a new generation."""
    key = f"{here.key}-grids"
    revision = revisions.last_change(here.data_dir, here.file)  # before the read
    now = part(doc(here.path))
    nonce = st.session_state.setdefault(f"{key}-nonce", 0)
    held: Base | None = st.session_state.get(f"{key}-base")
    kept, err = stays(
        here.data_dir,
        key,
        held if held is not None and held.nonce == nonce else None,
        now,
        lambda old: _touched(key, old),
    )
    if kept is not None:
        return kept, err
    nonce = st.session_state[f"{key}-nonce"]
    base = Base(nonce, now, revisions.Seen(here.file, revision, revisions.digest(now)))
    st.session_state[f"{key}-base"] = base
    return base, None


def doc(path: Path) -> dict[str, Any]:
    return loader.read_yaml(path) if path.exists() else {}


def _grid(here: Here, spec: ById, base: Base) -> store.RowEdits:
    """The grid of one override by id (`tables.small_grid`) and its edits."""
    rows = spec.shown(base.part.get(spec.key, {}))
    widget = _widget(here, base.nonce, spec.key)
    return tables.small_grid(spec.columns(rows), list(enumerate(rows)), widget)


def _inherited(spec: ById, leaves: Mapping[KeyPath, Leaf], stem: str) -> None:
    """The rows of the override that the file inherits and does not set, read only, each with
    the file that sets it."""
    rows = []
    for path, leaf in leaves.items():
        if path[0] == spec.key and len(path) == len(spec.names) and leaf.source != stem:
            row: Row = dict(zip(spec.names, path[1:], strict=False))
            rows.append(
                row | {spec.names[-1]: text(spec.field(row), leaf.value), "from": leaf.source}
            )
    if rows:
        st.caption(_("Inherited, until a row above sets the same:"))
        read_only(rows, spec.names[0])


def grids(here: Here, leaves: Mapping[KeyPath, Leaf], top: DeltaGenerator) -> Grids:
    """The grids of `shift`, `events` and `assets`, each in its expander, with what the file
    inherits (`leaves`: `overrides.effective` of the file) below it and below the dates the groups
    that move; the change of their part on disk since they were drawn goes into the container
    `top`."""
    base, changed = _base(here)
    found: dict[KeyPath, Any] = {}
    listed: list[guard.Change] = []
    unread: dict[str, str] = {}
    for spec in here.specs():
        held = base.part.get(spec.key, {})
        own = len(_by_id(held, len(spec.names) - 1))
        title = _title(spec.key) + (f" ({own})" if own else "")
        with st.expander(title, expanded=bool(own), key=f"{here.key}-{spec.key}-open"):
            st.caption(_(GRID_HELP[spec.key]))
            changes, bad = edited(spec, held, _grid(here, spec, base))
            if spec.key == "shift":
                shift = _shifts(here.stem, held, leaves, changes)
                if lines := moved(here.chain, shift):
                    st.caption("  \n".join(map(literal, lines)))
            _inherited(spec, leaves, here.stem)
        found |= changes
        listed += spec.listed(held, changes)
        unread |= {f"{keyword(spec.key)} {row}": problem for row, problem in bad.items()}
    if changed is not None:
        with top:
            _changed(here, changed)
    grid = (
        Grid(
            store.Edit(here.file, {(*OWN, *p): v for p, v in found.items()}),
            lambda: revisions.unchanged(here.data_dir, base.seen, part(doc(here.path))),
            f"{here.key}-grids-nonce",
        )
        if found
        else None
    )
    return Grids(found, listed, unread, changed is not None, grid)


def _title(key: str) -> str:
    """The title of the grid of an override by id: `Assets` names asset fields here, not the
    page."""
    return {
        "shift": _("Dates"),
        "events": _("Event fields"),
        "assets": pgettext("overrides", "Assets"),
    }[key]


def _shifts(
    stem: str, held: Mapping[str, Any], leaves: Mapping[KeyPath, Leaf], found: Mapping[KeyPath, Any]
) -> dict[str, tuple[Any, str]]:
    """The shift that a run of the scenario `stem` takes after the changes `found` of its own
    (`held`, as the file holds it), by id with the file of a shift that it inherits (empty for its
    own): the overrides of the chain merge, the own one wins."""
    inherited = {
        path[1]: (leaf.value, leaf.source)
        for path, leaf in leaves.items()
        if path[0] == "shift" and leaf.source != stem
    }
    own = overrides.own({"shift": dict(held)}, found).get("shift", {})
    return inherited | {item: (months, "") for item, months in own.items()}


def _changed(here: Here, err: revisions.ConflictError) -> None:
    st.warning(
        _(
            "{changed} since these tables were drawn. Your edits stay, but Save refuses them: "
            "discard them to see the file as it is now."
        ).format(changed=changed_at(err)),
        icon=":material/sync_problem:",
    )
    discard(f"{here.key}-grids")
