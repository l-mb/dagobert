"""Who refers to what across the inputs: per kind the names that exist and every use of each,
with its file, key path and label. The editors take their options from it and name the users
before they refuse a delete or a rename. It reads the raw YAML, so a file that does not load
counts as written."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum, StrEnum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, get_args

from dagobert.model.assets import Asset, Loan, PropertyAsset
from dagobert.model.assumptions import CPI_INDEX
from dagobert.model.streams import Stream
from dagobert.problems import Keys, dotted, parsed, read_text

if TYPE_CHECKING:
    from collections.abc import Collection, Iterator
    from pathlib import Path

    from pydantic import BaseModel


class Kind(StrEnum):
    ASSET = "asset"
    STREAM = "stream"
    TAG = "tag"
    CATEGORY = "category"  # of an expense stream that `scale` takes (`Stream.managed`)
    INDEX = "index"
    RETURN_CLASS = "return class"
    PHASE = "phase"  # a phase of `assumptions.yaml`, which the scenarios switch between
    RELATIVE = "relative"  # of `person.relatives`, who gives or bequeaths
    ITEM = "item"  # the `id` of a phase change or an event, which `overrides.shift` moves
    EVENT = "event"  # the `id` of an event, whose fields `overrides.events` set
    SCENARIO = "scenario"  # a file stem


@dataclass(frozen=True)
class Site:
    """A name in an input: the file under the data directory (`scenarios/a.yaml`), the key path
    from its top and what holds the name there. A built-in name has no file. `sort` tells what a
    defined asset id or stream name is: the kind of the asset or the stream. `item` is the id of
    the phase or event that holds the name, which a `drop` of a file below takes. `key`: the name
    is the last key of the path (`factor: {retired: 1.5}`), not the value there."""

    file: str
    keys: Keys
    label: str
    sort: str = ""
    item: str | None = None
    key: bool = False

    @property
    def scenario(self) -> str | None:
        """The stem of a scenario file, None for the other inputs."""
        path = PurePosixPath(self.file)
        return path.stem if path.parent.name == "scenarios" else None

    def within(self, file: str, keys: Keys) -> bool:
        return self.file == file and self.keys[: len(keys)] == keys

    def __str__(self) -> str:
        return f"{self.file}: {dotted(self.keys)} ({self.label})"


Table = dict[Kind, dict[str, list[Site]]]


def _table() -> Table:
    return {kind: {} for kind in Kind}


def _caseless(name: str) -> tuple[str, str]:
    return name.casefold(), name


@dataclass(frozen=True)
class References:
    """`defined` holds where each name is defined, `used` every use of each name, also of a name
    that nothing defines. A name defined outside the scenario files, and a scenario stem, counts
    in every file. One that a scenario file defines (an item or event id, an `add_stream`, an index
    or a return class of its overrides) counts there and in the files that extend it, until one
    of them drops the item that holds it."""

    defined: Table = field(default_factory=_table)
    used: Table = field(default_factory=_table)
    parents: dict[str, str | None] = field(default_factory=dict)  # `extends` by scenario stem
    drops: dict[str, set[str]] = field(default_factory=dict)  # `drop` by scenario stem

    def chain(self, scenario: str) -> list[str]:
        """The stems of the `extends` chain of `scenario`, the root first. It ends at a missing
        parent and at a cycle."""
        stems: list[str] = []
        stem: str | None = scenario
        while stem is not None and stem in self.parents and stem not in stems:
            stems.insert(0, stem)
            stem = self.parents[stem]
        return stems

    def names(
        self, kind: Kind, scenario: str | None = None, *, sorts: Collection[str] = ()
    ) -> list[str]:
        """The names of `kind` that count in the scenario file `scenario`, without one those that
        count everywhere, sorted without regard to case. `sorts` keeps the asset ids or stream
        names of these kinds."""
        return sorted(
            (
                name
                for name, sites in self.defined[kind].items()
                if any(
                    self._reaches(kind, site, scenario) and (not sorts or site.sort in sorts)
                    for site in sites
                )
            ),
            key=_caseless,
        )

    def uses(self, kind: Kind, name: str) -> list[Site]:
        return self.used[kind].get(name, [])

    def orphans(self, kind: Kind, name: str, file: str, keys: Keys = ()) -> list[Site]:
        """The uses of `name` that no definition reaches once what `file` holds below `keys` goes
        (the whole file by default): the users that a delete or a rename leaves behind. A use
        below `keys` goes with it."""
        left = [site for site in self.defined[kind].get(name, []) if not site.within(file, keys)]
        return [
            use
            for use in self.uses(kind, name)
            if not use.within(file, keys)
            and not any(self._reaches(kind, site, self._scope(use)) for site in left)
        ]

    def _scope(self, use: Site) -> str | None:
        """The scenario whose chain must define the name of `use`: for a `drop` the parent, since
        a file drops what its parents define, not its own items."""
        return self.parents.get(use.scenario or "") if use.keys[:1] == ("drop",) else use.scenario

    def _reaches(self, kind: Kind, site: Site, scenario: str | None) -> bool:
        if kind is Kind.SCENARIO or site.scenario is None:
            return True
        stems = [] if scenario is None else self.chain(scenario)
        return site.scenario in stems and not any(
            site.item in self.drops[stem] for stem in stems[stems.index(site.scenario) + 1 :]
        )


class _Step(Enum):
    EACH = "each"  # every item of a list, every value of a mapping
    KEY = "key"  # the keys of a mapping are the names


EACH, KEY = _Step.EACH, _Step.KEY
Pattern = tuple[str | _Step, ...]  # a key path with steps
Rules = tuple[tuple[Kind, Pattern], ...]  # a kind and where its names are

# an assumptions mapping: `assumptions.yaml` and the overrides of a scenario
SETTINGS_DEFINE: Rules = (
    (Kind.INDEX, ("indices", KEY)),
    (Kind.RETURN_CLASS, ("returns", KEY)),
    (Kind.RELATIVE, ("person", "relatives", KEY)),
)
SETTINGS_USE: Rules = (
    (Kind.PHASE, ("scale", "salary", KEY)),
    (Kind.INDEX, ("care", "index")),
    (Kind.CATEGORY, ("scale", "categories", KEY)),
    (Kind.STREAM, ("scale", "savings", KEY)),
    (Kind.CATEGORY, ("spending", "categories", EACH)),
    (Kind.CATEGORY, ("spending", "age_categories", EACH)),
)
ASSET_DEFINE: Rules = ((Kind.ASSET, ("id",)),)
# the phases in which the employer pays into a bAV policy, the salary of its conversion, the
# property that a loan financed
ASSET_USE: Rules = (
    (Kind.RETURN_CLASS, ("growth",)),
    (Kind.PHASE, ("phases", EACH)),
    (Kind.STREAM, ("salary",)),
    (Kind.ASSET, ("finances",)),
)
# a sale ends the streams that share a tag with the property
PROPERTY_USE: Rules = (*ASSET_USE, (Kind.TAG, ("tags", EACH)))
STREAM_DEFINE: Rules = ((Kind.STREAM, ("name",)),)
TAG_DEFINE: Rules = ((Kind.TAG, ("tags", EACH)),)
CATEGORY_DEFINE: Rules = ((Kind.CATEGORY, ("cat",)),)
STREAM_USE: Rules = (
    (Kind.INDEX, ("index",)),
    (Kind.STREAM, ("of",)),
    (Kind.ASSET, ("repays",)),
    (Kind.ASSET, ("after_sale_of",)),
    (Kind.ASSET, ("into",)),
    (Kind.ASSET, ("property",)),  # a let property
    (Kind.PHASE, ("phases", EACH)),
    (Kind.PHASE, ("factor", KEY)),
)
PHASE_DEFINE: Rules = ((Kind.PHASE, ("phases", KEY)),)  # in `assumptions.yaml` only
CHANGE_DEFINE: Rules = ((Kind.ITEM, ("id",)),)  # a phase change
CHANGE_USE: Rules = ((Kind.PHASE, ("phase",)),)
EVENT_DEFINE: Rules = (*CHANGE_DEFINE, (Kind.EVENT, ("id",)))
# a field of an event names one kind whatever the type, so the rules hold for `overrides.events`
EVENT_USE: Rules = (
    (Kind.ASSET, ("asset",)),
    (Kind.ASSET, ("loan",)),
    (Kind.ASSET, ("policy",)),
    (Kind.ASSET, ("bav", "policy")),
    (Kind.ASSET, ("then", EACH, "repay")),
    (Kind.STREAM, ("name",)),
    (Kind.STREAM, ("names", EACH)),
    (Kind.TAG, ("tags", EACH)),
    (Kind.RELATIVE, ("from",)),  # of an inheritance or a gift: one name or a list
    (Kind.RELATIVE, ("from", EACH)),
)
OVERRIDE_USE: Rules = (
    (Kind.ITEM, ("shift", KEY)),
    (Kind.EVENT, ("events", KEY)),
    (Kind.ASSET, ("assets", KEY)),
)
EXTENDS: Rules = ((Kind.SCENARIO, ("extends",)),)
DROP: Rules = ((Kind.ITEM, ("drop", EACH)),)  # an item of the parents
DEFAULTS: Rules = ((Kind.SCENARIO, ("scenarios", EACH)),)  # of `app.yaml`


def _kind(model: type[BaseModel]) -> str:
    kind: str = get_args(model.model_fields["kind"].annotation)[0]
    return kind


PROPERTY, LOAN = _kind(PropertyAsset), _kind(Loan)
# the return class of an asset without `growth`, by asset kind
GROWTH: dict[str, str] = {
    _kind(cls): cls.model_fields["growth"].default
    for cls in get_args(get_args(Asset)[0])
    if "growth" in cls.model_fields and not cls.model_fields["growth"].is_required()
}
EXPENSE = Stream.model_fields["kind"].default


def _at(node: Any, path: Pattern, keys: Keys) -> Iterator[tuple[Keys, Any]]:  # noqa: ANN401 raw YAML
    """What `path` reaches below `node`, with its key path after `keys`. A shape that the path
    does not expect yields nothing."""
    if not path:
        yield keys, node
        return
    step, rest = path[0], path[1:]
    if step is KEY and isinstance(node, dict):
        yield from (((*keys, key), key) for key in node)
    elif step is EACH and isinstance(node, dict | list):
        for key, item in node.items() if isinstance(node, dict) else enumerate(node):
            yield from _at(item, rest, (*keys, key))
    elif isinstance(step, str) and isinstance(node, dict) and step in node:
        yield from _at(node[step], rest, (*keys, step))


def _rows(node: Any, path: Pattern, where: Site) -> Iterator[tuple[dict[str, Any], Site]]:  # noqa: ANN401
    """The mappings that `path` reaches below `node`, which lies at `where`, with their sites."""
    for keys, row in _at(node, path, where.keys):
        if isinstance(row, dict):
            yield row, replace(where, keys=keys)


def _add(table: Table, rules: Rules, node: Any, where: Site) -> None:  # noqa: ANN401 raw YAML
    """The names that `rules` reach below `node`, which lies at `where`."""
    for kind, path in rules:
        for keys, name in _at(node, path, where.keys):
            if isinstance(name, str) and name:
                site = replace(where, keys=keys, key=path[-1] is KEY)
                table[kind].setdefault(name, []).append(site)


def _label(*parts: object) -> str:
    return " ".join(str(part) for part in parts if part not in (None, ""))


def _item(row: dict[str, Any]) -> str | None:
    """The id of a phase or an event, which a `drop` names."""
    return item if isinstance(item := row.get("id"), str) else None


def _month(day: object) -> str | None:
    return None if day is None else str(day)[:7]


@dataclass
class _Walk:
    """The definitions and uses that the walk through the files finds."""

    found: References = field(default_factory=References)

    def define(self, rules: Rules, node: Any, where: Site) -> None:  # noqa: ANN401 raw YAML
        _add(self.found.defined, rules, node, where)

    def use(self, rules: Rules, node: Any, where: Site) -> None:  # noqa: ANN401 raw YAML
        _add(self.found.used, rules, node, where)

    def settings(self, doc: Any, where: Site) -> None:  # noqa: ANN401 raw YAML
        self.define(SETTINGS_DEFINE, doc, where)
        self.use(SETTINGS_USE, doc, where)

    def asset(self, row: dict[str, Any], where: Site) -> None:
        kind = row["kind"] if isinstance(row.get("kind"), str) else ""
        where = replace(where, label=_label(kind, row.get("id")))
        self.define(ASSET_DEFINE, row, replace(where, sort=kind))
        self.asset_uses({"growth": GROWTH[kind]} | row if kind in GROWTH else row, kind, where)

    def asset_uses(self, row: dict[str, Any], kind: str, where: Site) -> None:
        self.use(PROPERTY_USE if kind == PROPERTY else ASSET_USE, row, where)

    def kind_of(self, asset: object) -> str:
        sites = self.found.defined[Kind.ASSET].get(asset, []) if isinstance(asset, str) else []
        return sites[0].sort if sites else ""

    def stream(self, row: dict[str, Any], where: Site) -> None:
        kind = row.get("kind", EXPENSE)
        where = replace(where, label=_label("stream", row.get("name")))
        self.define(STREAM_DEFINE, row, replace(where, sort=str(kind)))
        self.define(TAG_DEFINE, row, where)
        if kind == EXPENSE and not row.get("health") and not row.get("property"):  # `managed`
            self.define(CATEGORY_DEFINE, row, where)
        self.use(STREAM_USE, row, where)

    def event(self, row: dict[str, Any], where: Site) -> None:
        self.use(EVENT_USE, row, where)
        for stream, at in _rows(row, ("stream",), where):
            self.stream(stream, at)

    def bought(self, row: dict[str, Any], where: Site) -> None:
        """A `buy_property` defines its property and its loan, like an `add_stream` its stream."""
        for kind, held in ((PROPERTY, "property"), (LOAN, "loan")):
            for asset, at in _rows(row, (held,), where):
                self.define(ASSET_DEFINE, asset, replace(at, sort=kind))
                if kind == PROPERTY:
                    self.asset_uses({"growth": GROWTH[kind]} | asset, kind, at)

    def scenario(self, stem: str, doc: dict[str, Any]) -> None:
        top = Site(f"scenarios/{stem}.yaml", (), str(doc.get("name") or stem))
        self.found.defined[Kind.SCENARIO][stem] = [top]
        parent = doc.get("extends")
        self.found.parents[stem] = parent if isinstance(parent, str) else None
        self.found.drops[stem] = {i for _, i in _at(doc, ("drop", EACH), ()) if isinstance(i, str)}
        self.use(EXTENDS, doc, top)
        self.use(DROP, doc, replace(top, label="drop"))
        for row, where in _rows(doc, ("phases", EACH), top):
            label = _label("phase", row.get("phase"), _month(row.get("from")))
            change = replace(where, label=label, item=_item(row))
            self.define(CHANGE_DEFINE, row, change)
            self.use(CHANGE_USE, row, change)
        for row, where in _rows(doc, ("events", EACH), top):
            item = row.get("id")
            label = _label(row.get("type"), _month(row.get("at")), item and f"(id {item})")
            self.define(EVENT_DEFINE, row, event := replace(where, label=label, item=_item(row)))
            self.event(row, event)
            self.bought(row, event)
        overrides, under = doc.get("overrides"), Site(top.file, ("overrides",), "overrides")
        self.settings(overrides, under)
        self.use(OVERRIDE_USE, overrides, under)
        for row, where in _rows(overrides, ("events", EACH), under):
            self.event(row, where)
        for row, where in _rows(overrides, ("assets", EACH), under):
            self.asset_uses(row, self.kind_of(where.keys[-1]), where)


def read(data_dir: Path, name: str) -> dict[str, Any]:
    """The raw mapping of the input `name`, empty for a missing or empty file and for one without
    a mapping at the top. A file that does not parse raises `InputError`."""
    path = data_dir / name
    doc = parsed(read_text(path, name), name) if path.is_file() else None
    return doc if isinstance(doc, dict) else {}


def _labeled(found: object) -> dict[str, str]:
    """The names of the mapping `found` in its order, each with its `label` when it has one."""
    return {
        name: label if isinstance(label := (spec or {}).get("label"), str) and label else name
        for name, spec in (found.items() if isinstance(found, dict) else ())
        if isinstance(name, str) and isinstance(spec, dict | None)
    }


def phases(data_dir: Path) -> dict[str, str]:
    """The phases of `assumptions.yaml` in its order, each with how the pages name it (its `label`,
    else its name), from the raw file: one that does not load still gives them."""
    return _labeled(read(data_dir, "assumptions.yaml").get("phases"))


def relatives(data_dir: Path) -> dict[str, str]:
    """The relatives of `person.relatives` in `assumptions.yaml` in its order, each with how the
    pages name it (its `label`, else its short name), from the raw file, as `phases`."""
    person = read(data_dir, "assumptions.yaml").get("person")
    return _labeled(person.get("relatives") if isinstance(person, dict) else None)


def of(data_dir: Path) -> References:
    """The names and their uses in the inputs of `data_dir`."""
    walk = _Walk()
    walk.found.defined[Kind.INDEX][CPI_INDEX] = [Site("", (), "consumer prices")]
    assumptions = read(data_dir, "assumptions.yaml")
    walk.define(PHASE_DEFINE, assumptions, Site("assumptions.yaml", (), "phases"))
    walk.settings(assumptions, Site("assumptions.yaml", (), "assumptions"))
    for name, key, rows in (
        ("assets.yaml", "assets", walk.asset),
        ("cashflows.yaml", "streams", walk.stream),
    ):
        for row, where in _rows(read(data_dir, name), (key, EACH), Site(name, (), "")):
            rows(row, where)
    # as `scenariofiles.scenario_paths`, which imports this module
    for path in sorted((data_dir / "scenarios").glob("*.yaml")):
        walk.scenario(path.stem, read(data_dir, f"scenarios/{path.name}"))
    walk.use(DEFAULTS, read(data_dir, "app.yaml"), Site("app.yaml", (), "defaults"))
    return walk.found
