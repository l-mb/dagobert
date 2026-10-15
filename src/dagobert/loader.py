"""Load YAML inputs and compose a scenario into a Plan."""

from __future__ import annotations

from dataclasses import replace
from functools import partial, reduce
from typing import TYPE_CHECKING, Any, NamedTuple

from pydantic import BaseModel, TypeAdapter, ValidationError

from dagobert.model.assets import Asset, Assets, LotAsset
from dagobert.model.assumptions import Assumptions
from dagobert.model.base import KeyPath
from dagobert.model.events import EventBase, SellEvent, Shift
from dagobert.model.months import add_months
from dagobert.model.plan import AppSettings, Plan, Scenario
from dagobert.model.streams import Cashflows, Stream, StreamKind
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
    from collections.abc import Callable, Collection, Iterable, Mapping
    from datetime import date
    from pathlib import Path

# overrides that change the scenario and the assets, not the assumptions
SCENARIO_KEYS = ("events", "shift", "assets")
ITEM_KEYS = ("events", "shift")  # overrides by the id of a phase or an event
NOT_KEPT = "no phase or event that the parents keep has this id"
OWN_PHASES = "a scenario defines no phases: assumptions.yaml does, for every scenario"
NO_PATH = "the file name of a scenario beside this one, without .yaml, such as base: no path"
APP = "app.yaml"  # what the app opens with
SLIDERS = "explorer sliders"  # where the overrides of `load_plan` come from in an error
BAND = ("cut", "trigger", "increase", "ceiling")  # the spending rule that VPW replaces
_FIELDS = TypeAdapter(dict[str, dict[str, Any]])  # `events` and `assets`: {id: {field: value}}
_MONTHS = TypeAdapter(Shift)  # `shift`: {id: months}


class _OverrideError(Exception):
    """Errors at key paths of the overrides, before the file that writes them is known."""

    def __init__(self, found: list[Error]) -> None:
        super().__init__(found)
        self.found = found


def _label(path: Path) -> str:
    """The name of an input in an error, relative to the data directory."""
    return "/".join(path.parts[-2:]) if path.parent.name == "scenarios" else path.name


def _mapping(text: str, file: str) -> dict[str, Any]:
    if not isinstance(data := parsed(text, file), dict):
        problem = "empty" if data is None else "no mapping at the top level"
        raise InputError([Problem(file, None, "", problem)])
    return data


def _text(path: Path) -> str:
    return read_text(path, _label(path))


def read_yaml(path: Path) -> dict[str, Any]:
    return _mapping(_text(path), _label(path))


def validate[T: BaseModel](cls: type[T], text: str, file: str) -> T:
    """`cls` from the YAML `text` of the input `file`. An error names the line and key path."""
    try:
        return cls.model_validate(_mapping(text, file))
    except ValidationError as err:
        raise located(errors(err), [Source(file, with_lines(text))]) from err


def _load[T: BaseModel](cls: type[T], path: Path) -> T:
    return validate(cls, _text(path), _label(path))


def _validated[T: BaseModel](cls: type[T], data: dict[str, Any], path: Path) -> T:
    """`cls` from the raw mapping of the input `path`, which is read again only on an error."""
    try:
        return cls.model_validate(data)
    except ValidationError as err:
        raise located(errors(err), [_source(path)]) from err


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def chain(path: Path, seen: frozenset[Path] = frozenset()) -> list[tuple[Path, dict[str, Any]]]:
    """Each file of the `extends` chain with its raw mapping, the root first. Raw, so a file that
    does not load as a `Scenario` still gives its overrides. A missing or circular parent, or one
    with a path, raises at the line of `extends`."""
    text = _text(path)
    raw = _mapping(text, _label(path))
    if not isinstance(stem := raw.get("extends"), str):
        return [(path, raw)]  # none, or a type that the model names
    if any(separator in stem for separator in "/\\"):
        problem = NO_PATH
    elif (parent := path.with_name(f"{stem}.yaml")) in seen | {path}:
        problem = f"a cycle through {parent.name}"
    elif not parent.is_file():
        problem = f"no {parent.name}"
    else:
        return [*chain(parent, seen | {path}), (path, raw)]
    raise located(
        [Error(("extends",), "extends", problem)], [Source(_label(path), with_lines(text))]
    )


class _Layer(NamedTuple):
    """A file of an `extends` chain with its own content and the ids that the files below drop."""

    file: Path
    own: Scenario
    dropped: set[str]


def _layers(path: Path) -> list[_Layer]:
    """Each file of the `extends` chain of `path`, the root first. An id of a `drop` that no
    phase or event above the file has, after the drops of the files above, raises at its line."""
    layers: list[_Layer] = []
    for file, raw in chain(path):
        own = _validated(Scenario, raw, file)
        above_ids = {
            item.id
            for _, above, gone in layers
            for item in (*above.phases, *above.events)
            if item.id not in gone
        }
        if missing := [n for n, i in enumerate(own.drop) if i not in above_ids]:
            raise located([Error(("drop", n), "drop", NOT_KEPT) for n in missing], [_source(file)])
        for layer in layers:
            layer.dropped.update(own.drop)
        layers.append(_Layer(file, own, set()))
    return layers


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
    return [(file, _without(own, dropped)) for file, own, dropped in _layers(path)]


def merged_overrides(layers: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """The overrides of the files of an `extends` chain, the root first, as one mapping. They
    merge with each other before they merge over the assumptions: a mapping of a child over a
    null of its parent merges with the assumptions again."""
    return reduce(deep_merge, map(dict, layers), {})


def load_scenario(path: Path) -> Scenario:
    """Resolve `extends` chains; the child's phases and events append to the parent's, less
    those that it drops (`lineage`)."""
    files = lineage(path)
    child = files[-1][1]
    return Scenario(
        name=child.name,
        note=child.note,
        abstract=child.abstract,
        phases=[p for _, own in files for p in own.phases],
        events=[e for _, own in files for e in own.events],
        overrides=merged_overrides(own.overrides for _, own in files),
    )


def written(path: Path) -> list[tuple[Path, Scenario]]:
    """Each file of the `extends` chain of `path` with the phases and events written in it,
    moved by the `events` and `shift` overrides of `path` as its run sees them: their months and
    details. Without the assets every sale takes the fields of a property sale (`_takes`), so an
    override of `share` or `price` can differ from the run."""
    files = lineage(path)
    changes = split(merged_overrides(own.overrides for _, own in files))[1]
    try:
        return [(file, adjust(own, changes, strict=False)) for file, own in files]
    except _OverrideError as err:
        raise located(err.found, _override_sources(path, {})) from err


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


def split(overrides: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The overrides of the assumptions, and those of the scenario (`SCENARIO_KEYS`)."""
    return (
        {k: v for k, v in overrides.items() if k not in SCENARIO_KEYS},
        {k: v for k, v in overrides.items() if k in SCENARIO_KEYS},
    )


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
        return add_months(day, round(shift[group])) if day and group in shift else day

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
    `overrides`), a check across the inputs the scenario."""
    scenario = load_scenario(scenario_path)
    own, extra = split(scenario.overrides), split(overrides or {})
    assumptions, assets, streams = (
        load_assumptions(data_dir),
        load_assets(data_dir),
        load_streams(data_dir),
    )
    try:
        spending = deep_merge(assumptions.model_dump(), own[0]).get("spending")
        sliders = _plans_of(extra[0], [*streams, *scenario.added_streams], spending)
        assumptions = _assumptions(assumptions, deep_merge(own[0], sliders))
        assets = set_assets(set_assets(assets, own[1]), extra[1], strict=False)
        holdings = {a.id for a in assets if isinstance(a, LotAsset)}
        scenario = adjust(
            adjust(scenario, own[1], holdings=holdings), extra[1], strict=False, holdings=holdings
        )
    except _OverrideError as err:
        raise located(err.found, _override_sources(scenario_path, overrides or {})) from err
    try:
        return Plan(assumptions=assumptions, assets=assets, streams=streams, scenario=scenario)
    except ValidationError as err:
        raise _plan_error(errors(err), data_dir, scenario_path, overrides or {}) from err


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


def _source(path: Path) -> Source:
    """An input with the lines of its keys."""
    return Source(_label(path), with_lines(_text(path)))


def _plan_error(
    found: list[Error], data_dir: Path, scenario_path: Path, overrides: dict[str, Any]
) -> InputError:
    """A check across the inputs names the place of the use, else the scenario. One at a field of
    an event names where the value comes from: the `events` override that sets the field
    (`_override_sources`), else the file of the `extends` chain that writes the event, with the
    line and the key path there. The
    events that the files keep follow each other in the scenario (`load_scenario`). A problem in
    another file names the scenario and the ids that its chain drops below the event: the file of
    the event loads alone, a drop below it may take the stream that the event names. A phase that
    a stream names is in `cashflows.yaml`, one of a bAV policy in the `assets` override that sets
    it, else in `assets.yaml`, one of a phase change in each file of the chain that writes it, and
    a missing phase at the start in the scenario. A name in the assumptions is in the override that
    sets it, else in `assumptions.yaml`."""
    layers = _layers(scenario_path)
    owners = [
        (file, i, event, dropped)
        for file, own, dropped in layers
        for i, event in enumerate(own.events)
        if event.id not in dropped
    ]
    chained = split(merged_overrides(_without(o, d).overrides for _, o, d in layers))[1]
    changes = deep_merge(chained, split(overrides)[1])
    scenario = _label(scenario_path)
    problems: list[Problem] = []
    for error in found:
        match error.loc:
            case ("scenario", "events", int(n), str(name), *rest):
                file, i, event, dropped = owners[n]
                key: str | int = i
                sources = [_source(file)]
                if event.id is not None and name in changes.get("events", {}).get(event.id, {}):
                    key, sources = event.id, _override_sources(scenario_path, overrides)
                drops = f", whose chain drops {', '.join(sorted(dropped))}" if dropped else ""
                problems += [
                    p
                    if p.file == scenario
                    else replace(p, message=f"{p.message} (for {scenario}{drops})")
                    for p in located(
                        [error._replace(loc=("events", key, name, *rest))], sources
                    ).problems
                ]
            case ("scenario", "phases", int(), "phase"):
                problems += _phase_changes(error, layers)
            case ("scenario", "phases"):
                problems += located(
                    [error._replace(loc=("phases",))], [_source(scenario_path)]
                ).problems
            case ("streams", *_):
                problems += located([error], [_source(data_dir / "cashflows.yaml")]).problems
            case ("assets", int(i), str(name), *rest):
                asset = read_yaml(data_dir / "assets.yaml")["assets"][i]["id"]
                held = name in changes.get("assets", {}).get(asset, {})
                problems += located(
                    [error._replace(loc=("assets", asset, name, *rest))] if held else [error],
                    _override_sources(scenario_path, overrides)
                    if held
                    else [_source(data_dir / "assets.yaml")],
                ).problems
            case ("assumptions", *rest):
                problems += located(
                    [error._replace(loc=tuple(rest))],
                    _override_sources(
                        scenario_path, overrides, _source(data_dir / "assumptions.yaml")
                    ),
                ).problems
            case _:
                problems += located([error], [Source(scenario, {})]).problems
    return InputError(dict.fromkeys(problems))


def _phase_changes(error: Error, layers: list[_Layer]) -> list[Problem]:
    """Each phase change of the files of an `extends` chain, less those that a file below drops,
    that names the phase of `error`: the merged changes are sorted and shifted, so their place
    names no file."""
    found: list[Problem] = []
    for file, _, dropped in layers:
        source = _source(file)
        rows = source.doc.get("phases") if isinstance(source.doc, dict) else None
        found += [
            p
            for k, row in enumerate(rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
            and row.get("phase") == error.input
            and row.get("id") not in dropped
            for p in located([error._replace(loc=("phases", k, "phase"))], [source]).problems
        ]
    return found


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


def _override_sources(
    scenario_path: Path, extra: dict[str, Any], rest: Source | None = None
) -> list[Source]:
    """Where an override can come from, in the order of precedence: the explorer, then the files
    of the `extends` chain from the last. `rest` takes the rest, by default the scenario. Only a
    source that overrides the assumptions can cause an error of all of them."""
    files = [
        (_label(path), with_lines(_text(path)).get("overrides"))
        for path, _ in reversed(chain(scenario_path))
    ]
    return [
        Source(SLIDERS, extra, root=bool(split(extra)[0])),
        *(
            Source(file, doc, ("overrides",), root=bool(split(doc)[0]))
            for file, doc in files
            if doc
        ),
        rest or Source(_label(scenario_path), {}),
    ]
