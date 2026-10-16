"""Load YAML inputs and compose a scenario into a Plan."""

from __future__ import annotations

from functools import partial, reduce
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel, TypeAdapter, ValidationError

from dagobert.model.assets import Asset, Assets, LotAsset
from dagobert.model.assumptions import Assumptions
from dagobert.model.base import KeyPath
from dagobert.model.events import EventBase, SellEvent, Shift
from dagobert.model.months import add_months
from dagobert.model.plan import AppSettings, Plan, Scenario, split
from dagobert.model.streams import Cashflows, Stream, StreamKind
from dagobert.origins import Composed, label, override_sources, plan_error, source
from dagobert.problems import (
    Error,
    InputError,
    Problem,
    Source,
    errors,
    located,
    parsed,
    read_text,
    with_lines,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
    from datetime import date
    from pathlib import Path

ITEM_KEYS = ("events", "shift")  # overrides by the id of a phase or an event
NOT_KEPT = "no phase or event that the parents keep has this id"
OWN_PHASES = "a scenario defines no phases: assumptions.yaml does, for every scenario"
NO_PATH = "the file name of a scenario beside this one, without .yaml, such as base: no path"
APP = "app.yaml"  # what the app opens with
BAND = ("cut", "trigger", "increase", "ceiling")  # the spending rule that VPW replaces
_FIELDS = TypeAdapter(dict[str, dict[str, Any]])  # `events` and `assets`: {id: {field: value}}
_MONTHS = TypeAdapter(Shift)  # `shift`: {id: months}


class _OverrideError(Exception):
    """Errors at key paths of the overrides, before the file that writes them is known."""

    def __init__(self, found: list[Error]) -> None:
        super().__init__(found)
        self.found = found


def _mapping(text: str, file: str) -> dict[str, Any]:
    if not isinstance(data := parsed(text, file), dict):
        problem = "empty" if data is None else "no mapping at the top level"
        raise InputError([Problem(file, None, "", problem)])
    return data


def _text(path: Path) -> str:
    return read_text(path, label(path))


def read_yaml(path: Path) -> dict[str, Any]:
    return _mapping(_text(path), label(path))


def validate[T: BaseModel](cls: type[T], text: str, file: str) -> T:
    """`cls` from the YAML `text` of the input `file`. An error names the line and key path."""
    try:
        return cls.model_validate(_mapping(text, file))
    except ValidationError as err:
        raise located(errors(err), [Source(file, with_lines(text))]) from err


def _load[T: BaseModel](cls: type[T], path: Path) -> T:
    return validate(cls, _text(path), label(path))


def _validated[T: BaseModel](cls: type[T], data: dict[str, Any], path: Path) -> T:
    """`cls` from the raw mapping of the input `path`, which is read again only on an error."""
    try:
        return cls.model_validate(data)
    except ValidationError as err:
        raise located(errors(err), [source(path)]) from err


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ancestry[T](start: T, parent: Callable[[T], T | None]) -> list[T]:
    """`start` and its parents by `parent`, the root first, up to one without a parent or whose
    parent the chain holds already: a cycle."""
    found = [start]
    while (up := parent(found[0])) is not None and up not in found:
        found.insert(0, up)
    return found


def drops_below(drops: Sequence[Collection[str]]) -> list[set[str]]:
    """Per file of an `extends` chain, the root first, the ids that the files below it drop:
    their items and the `shift` and `events` overrides of the ids (`kept`) go."""
    return [set[str]().union(*drops[n + 1 :]) for n in range(len(drops))]


def _parent(file: Path, stem: object) -> Path | None:
    """The file that `extends: <stem>` of `file` names: none for no text or one with a path."""
    if not isinstance(stem, str) or any(separator in stem for separator in "/\\"):
        return None
    return file.with_name(f"{stem}.yaml")


def chain(path: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Each file of the `extends` chain with its raw mapping, the root first (`ancestry`). Raw, so
    a file that does not load as a `Scenario` still gives its overrides. A missing or circular
    parent, or one with a path, raises at the line of `extends`: `references` reads the chain up
    to it, the loader names it."""
    raws: dict[Path, dict[str, Any]] = {}

    def parent(file: Path) -> Path | None:
        raws[file] = read_yaml(file)
        up = _parent(file, raws[file].get("extends"))
        return up if up is not None and up.is_file() else None

    files = ancestry(path, parent)
    if not isinstance(stem := raws[root := files[0]].get("extends"), str):
        return [(file, raws[file]) for file in files]  # none, or a type that the model names
    up = _parent(root, stem)
    if up is None:
        problem = NO_PATH
    else:
        problem = f"a cycle through {up.name}" if up in files else f"no {up.name}"
    raise located([Error(("extends",), "extends", problem)], [source(root)])


class Layer(NamedTuple):
    """A file of an `extends` chain with its own content and the ids that the files below drop."""

    file: Path
    own: Scenario
    dropped: set[str]


def _layers(path: Path) -> list[Layer]:
    """Each file of the `extends` chain of `path`, the root first. An id of a `drop` that no
    phase or event above the file has, after the drops of the files above, raises at its line."""
    owns: list[tuple[Path, Scenario]] = []
    for file, raw in chain(path):
        own = _validated(Scenario, raw, file)
        gone = drops_below([above.drop for _, above in owns])
        held = {
            item.id
            for (_, above), out in zip(owns, gone, strict=True)
            for item in (*above.phases, *above.events)
            if item.id not in out
        }
        if missing := [n for n, i in enumerate(own.drop) if i not in held]:
            raise located([Error(("drop", n), "drop", NOT_KEPT) for n in missing], [source(file)])
        owns.append((file, own))
    gone = drops_below([own.drop for _, own in owns])
    return [Layer(file, own, out) for (file, own), out in zip(owns, gone, strict=True)]


def kept(overrides: Mapping[str, Any], ids: Collection[str]) -> dict[str, Any]:
    """The overrides of a file without their `events` and `shift` entries of `ids`, which a file
    below drops: an override follows its item. A mapping that loses all its entries goes."""
    out = dict(overrides)
    for key in ITEM_KEYS:
        if isinstance(entries := out.get(key), dict) and any(i in ids for i in entries):
            out[key] = {i: v for i, v in entries.items() if i not in ids}
            if not out[key]:
                del out[key]
    return out


def _without(scenario: Scenario, ids: Collection[str]) -> Scenario:
    """`scenario` without the phases and events of `ids` and their overrides (`kept`)."""
    return scenario.model_copy(
        update={
            "phases": [p for p in scenario.phases if p.id not in ids],
            "events": [e for e in scenario.events if e.id not in ids],
            "overrides": kept(scenario.overrides, ids),
        }
    )


def lineage(path: Path) -> list[tuple[Path, Scenario]]:
    """Each file of the `extends` chain with its own content, the root first, less what the files
    below it drop (`_without`)."""
    return _lineage(_layers(path))


def _lineage(layers: Sequence[Layer]) -> list[tuple[Path, Scenario]]:
    return [(file, _without(own, dropped)) for file, own, dropped in layers]


def merged_overrides(layers: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The overrides of the files of an `extends` chain, the root first, as one mapping. They
    merge with each other before they merge over the assumptions: a mapping of a child over a
    null of its parent merges with the assumptions again."""
    return reduce(deep_merge, map(dict, layers), {})


def load_scenario(path: Path) -> Scenario:
    """Resolve `extends` chains; the child's phases and events append to the parent's, less
    those that it drops (`lineage`)."""
    return _composed(_layers(path))


def _composed(layers: Sequence[Layer]) -> Scenario:
    files = _lineage(layers)
    child = files[-1][1]
    return Scenario(
        name=child.name,
        note=child.note,
        abstract=child.abstract,
        phases=[p for _, own in files for p in own.phases],
        events=[e for _, own in files for e in own.events],
        overrides=merged_overrides(own.overrides for _, own in files),
    )


def written(data_dir: Path, path: Path) -> list[tuple[Path, Scenario]]:
    """Each file of the `extends` chain of `path` with the phases and events written in it,
    moved by the `events` and `shift` overrides of `path` as its run sees them: their months and
    details, a sale of gold or crypto with its own fields (`_holdings` of `assets.yaml`)."""
    layers = _layers(path)
    files = _lineage(layers)
    changes = split(merged_overrides(own.overrides for _, own in files))[1]
    holdings = _holdings(load_assets(data_dir))
    try:
        return [
            (file, adjust(own, changes, strict=False, holdings=holdings)) for file, own in files
        ]
    except _OverrideError as err:
        raise located(err.found, override_sources(layers, {})) from err


def load_assumptions(data_dir: Path) -> Assumptions:
    return _load(Assumptions, data_dir / "assumptions.yaml")


def nested(leaves: Mapping[KeyPath, Any]) -> dict[str, Any]:
    """A mapping from its leaves by key path, the other way round of `flatten`."""
    out: dict[str, Any] = {}
    for path, value in leaves.items():
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = value
    return out


def flatten(mapping: Mapping[str, Any], depth: int | None = None) -> dict[KeyPath, Any]:
    """The leaves of `mapping` by key path: a value that is no mapping (a list is one leaf, so is
    null), an empty mapping (over a section that is off it switches the section on) and any value
    `depth` keys down."""
    return {
        (key, *path): leaf
        for key, value in mapping.items()
        for path, leaf in (
            flatten(value, None if depth is None else depth - 1).items()
            if isinstance(value, dict) and value and depth != 1
            else [((), value)]
        )
    }


def load_assets(data_dir: Path) -> list[Asset]:
    return _load(Assets, data_dir / "assets.yaml").assets


def load_streams(data_dir: Path) -> list[Stream]:
    return _load(Cashflows, data_dir / "cashflows.yaml").streams


def _shaped[T](adapter: TypeAdapter[T], changes: dict[str, Any], key: str) -> T:
    """The override `key` of `changes`, empty when absent, if it has the shape of `adapter`."""
    try:
        return adapter.validate_python(changes.get(key, {}))
    except ValidationError as err:
        raise _OverrideError(errors(err, (key,))) from err


def _revalidated[T: BaseModel](item: T, data: dict[str, Any], keys: tuple[str, ...]) -> T:
    """`item` with the fields that the overrides at `keys` set."""
    try:
        return type(item).model_validate(data)
    except ValidationError as err:
        raise _OverrideError(errors(err, keys)) from err


def _holdings(assets: Iterable[Asset]) -> set[str]:
    """The ids of the gold and crypto assets: their sales take other fields (`_takes`)."""
    return {a.id for a in assets if isinstance(a, LotAsset)}


def _takes(event: EventBase, name: str, holdings: Collection[str]) -> bool:
    """`event` has the field `name`, as the files write it (`from` of an inheritance). A sale lacks
    those of the other kind of asset: a gold sale that shares its id with the sale of a property
    takes no `price`."""
    foreign = event.foreign(holding=event.asset in holdings) if isinstance(event, SellEvent) else ()
    named = any((f.alias or n) == name for n, f in type(event).model_fields.items())
    return named and name not in foreign


def adjust(
    scenario: Scenario,
    changes: dict[str, Any],
    *,
    strict: bool = True,
    holdings: Collection[str] = (),
) -> Scenario:
    """Apply `events` (`{id: {field: value}}`, set on every event of the group that has the
    field) and then `shift` (`{id: months}`, moves `at` and `from` of every item of the group).
    An id or field that the scenario lacks raises when `strict`. The explorer is not strict:
    its sliders reach every chosen scenario, with the item or without. `holdings` are the ids of
    the gold and crypto assets (`_takes`)."""
    fields, shift = _shaped(_FIELDS, changes, "events"), _shaped(_MONTHS, changes, "shift")
    ids = {e.id for e in scenario.events} | {p.id for p in scenario.phases}
    missing = [
        Error((key, i), "id", "no event or phase with this id")
        for key, group in (("events", fields), ("shift", shift))
        for i in group
        if i not in ids
    ] + [
        Error(("events", i, name), "field", "no event of this id has this field")
        for i, values in fields.items()
        for name in values
        if i in ids and not any(e.id == i and _takes(e, name, holdings) for e in scenario.events)
    ]
    if strict and missing:
        raise _OverrideError(missing)

    def moved(day: date | None, group: str | None) -> date | None:
        return add_months(day, shift[group]) if day and group in shift else day

    def changed[E: EventBase](event: E) -> E:
        """`event` with its fields, then moved: a shift moves the validated month."""
        keys, own = ("events", event.id or ""), fields.get(event.id or "", {})
        data = {k: v for k, v in own.items() if _takes(event, k, holdings)}
        new = _revalidated(event, event.model_dump(by_alias=True) | data, keys) if data else event
        if new.id not in shift:
            return new
        return _revalidated(
            new, new.model_dump(by_alias=True) | {"at": moved(new.at, new.id)}, keys
        )

    events = [changed(e) for e in scenario.events]
    phases = [p.model_copy(update={"at": moved(p.at, p.id)}) for p in scenario.phases]
    return scenario.model_copy(
        update={"events": events, "phases": sorted(phases, key=lambda p: p.at)}
    )


def set_assets(assets: list[Asset], changes: dict[str, Any], *, strict: bool = True) -> list[Asset]:
    """Apply `assets` (`{id: {field: value}}`). An unknown id raises when `strict`."""
    fields = _shaped(_FIELDS, changes, "assets")
    missing = sorted(set(fields) - {a.id for a in assets})
    if strict and missing:
        raise _OverrideError([Error(("assets", i), "id", "no asset with this id") for i in missing])
    return [
        _revalidated(a, a.model_dump() | fields[a.id], ("assets", a.id)) if a.id in fields else a
        for a in assets
    ]


def _assumptions(base: Assumptions, overrides: dict[str, Any]) -> Assumptions:
    """`base` with `overrides`, which define no phase: the sheets, the grids and the sliders show
    the phases of `assumptions.yaml` for every scenario."""
    if "phases" in overrides:
        raise _OverrideError([Error(("phases",), "phases", OWN_PHASES)])
    try:
        return Assumptions.model_validate(deep_merge(base.model_dump(), overrides))
    except ValidationError as err:
        raise _OverrideError(errors(err)) from err


def load_plan(data_dir: Path, scenario_path: Path, overrides: dict[str, Any] | None = None) -> Plan:
    """`overrides` merge last, on top of the scenario's own overrides. Their `events` and
    `shift` change the scenario, see `adjust`. An error names the file and the key path: an
    override the file of the `extends` chain that writes it (`explorer sliders` for
    `overrides`), a check across the inputs the place of the use (`origins`)."""
    layers, sliders = _layers(scenario_path), overrides or {}
    scenario = _composed(layers)
    own, extra = split(scenario.overrides), split(sliders)
    assumptions, assets, streams = (
        load_assumptions(data_dir),
        load_assets(data_dir),
        load_streams(data_dir),
    )
    try:
        spending = deep_merge(assumptions.model_dump(), own[0]).get("spending")
        reached = _plans_of(extra[0], [*streams, *scenario.added_streams], spending)
        assumptions = _assumptions(assumptions, deep_merge(own[0], reached))
        assets = set_assets(set_assets(assets, own[1]), extra[1], strict=False)
        holdings = _holdings(assets)
        scenario = adjust(
            adjust(scenario, own[1], holdings=holdings), extra[1], strict=False, holdings=holdings
        )
    except _OverrideError as err:
        raise located(err.found, override_sources(layers, sliders)) from err
    try:
        return Plan(assumptions=assumptions, assets=assets, streams=streams, scenario=scenario)
    except ValidationError as err:
        changes = deep_merge(own[1], extra[1])
        raise plan_error(errors(err), Composed(data_dir, layers, sliders, changes, assets)) from err


def _plans_of(sliders: dict[str, Any], streams: list[Stream], spending: object) -> dict[str, Any]:
    """`sliders` without what the scenario lacks, as the explorer's sliders reach every chosen
    scenario: the factors of `scale.savings` for the plans that `streams` lack (the plan of an
    `add_stream` reaches only its own), `spending.vpw` where its `spending` (`assumptions.yaml`
    with its own overrides) has no VPW and the band (`BAND`) where it has: the model refuses VPW
    beside the cut and the increase."""
    out = dict(sliders)
    scale = sliders.get("scale")
    if isinstance(scale, dict) and isinstance(savings := scale.get("savings"), dict):
        names = {s.name for s in streams if s.kind == StreamKind.SAVINGS}
        out["scale"] = scale | {"savings": {n: f for n, f in savings.items() if n in names}}
    if isinstance(rule := sliders.get("spending"), dict):
        vpw = isinstance(spending, dict) and spending.get("vpw") is not None
        out["spending"] = {k: v for k, v in rule.items() if k not in (BAND if vpw else ("vpw",))}
        if not out["spending"]:  # no rule where the scenario has none
            del out["spending"]
    return out


def load_app_settings(data_dir: Path) -> AppSettings:
    """`app.yaml`, the defaults without one or in an empty one."""
    path = data_dir / APP
    text = _text(path) if path.is_file() else ""
    return validate(AppSettings, text, APP) if text.strip() else AppSettings()


def problems(data_dir: Path) -> list[Problem]:
    """What does not load of the inputs, as a save checks them: `app.yaml` and every scenario,
    whose plans load the other files; a problem of a file that every plan loads once."""
    found: dict[Problem, None] = {}
    loads: list[Callable[[], object]] = [
        lambda: load_app_settings(data_dir),
        *(partial(load_plan, data_dir, s) for s in sorted((data_dir / "scenarios").glob("*.yaml"))),
    ]
    for load in loads:
        try:
            load()
        except InputError as err:
            found |= dict.fromkeys(err.problems)
    return list(found)


def check(data_dir: Path) -> None:
    """Load every input as a save checks it (`problems`). A problem raises `InputError`."""
    if found := problems(data_dir):
        raise InputError(found)
