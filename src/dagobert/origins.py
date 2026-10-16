"""Where an error of a plan comes from: the file, the line and the key path that
`loader.load_plan` names for an override that does not fit and for a check across the inputs
(`Plan`), one function per kind of error."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from dagobert.model.plan import split
from dagobert.problems import InputError, Source, located, read_text, with_lines

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from dagobert.loader import Layer
    from dagobert.model.assets import Asset
    from dagobert.problems import Error, Keys, Problem

SLIDERS = "explorer sliders"  # where the overrides of `load_plan` come from in an error


def label(path: Path) -> str:
    """The name of an input in an error, relative to the data directory."""
    return "/".join(path.parts[-2:]) if path.parent.name == "scenarios" else path.name


def source(path: Path) -> Source:
    """An input with the lines of its keys."""
    return Source(label(path), with_lines(read_text(path, label(path))))


def override_sources(
    layers: Sequence[Layer], sliders: Mapping[str, Any], rest: Source | None = None
) -> list[Source]:
    """Where an override can come from, in the order of precedence: the explorer (`sliders`),
    then the files of the `extends` chain (`layers`, the root first) from the last. `rest` takes
    the rest, by default the scenario. Only a source that overrides the assumptions can cause an
    error of all of them."""
    files = [source(layer.file) for layer in reversed(layers)]
    return [
        Source(SLIDERS, sliders, root=bool(split(sliders)[0])),
        *(
            Source(file.file, doc, ("overrides",), root=bool(split(doc)[0]))
            for file in files
            if (doc := file.doc.get("overrides"))
        ),
        rest or Source(label(layers[-1].file), {}),
    ]


@dataclass(frozen=True)
class Composed:
    """A plan as `loader.load_plan` composes it: the data directory, the files of the `extends`
    chain of its scenario (the root first), the overrides of the explorer (`sliders`), the
    `events`, `shift` and `assets` overrides that it applies (`changes`) and its assets."""

    data_dir: Path
    layers: Sequence[Layer]
    sliders: Mapping[str, Any]
    changes: Mapping[str, Any]
    assets: Sequence[Asset]

    @property
    def scenario(self) -> str:
        return label(self.layers[-1].file)

    def sources(self, rest: Source | None = None) -> list[Source]:
        return override_sources(self.layers, self.sliders, rest)

    def changed(self, key: str, item: str, field: str) -> bool:
        """The override `key` (`events`, `assets`) sets `field` of `item`."""
        return field in self.changes.get(key, {}).get(item, {})


def plan_error(found: Sequence[Error], plan: Composed) -> InputError:
    """A check across the inputs (`found`, at key paths of the `Plan`) names the place of the
    use, each problem once: an event, a phase change, a missing phase at the start, a stream in
    `cashflows.yaml`, an asset, a name of the assumptions; else the scenario."""
    return InputError(dict.fromkeys(p for error in found for p in _placed(error, plan)))


def _placed(error: Error, plan: Composed) -> list[Problem]:
    match error.loc:
        case ("scenario", "events", int(n), str(name), *rest):
            found = _event(error, plan, n, (name, *rest))
        case ("scenario", "phases", int(), "phase"):
            found = _phase_changes(error, plan.layers)
        case ("scenario", "phases"):
            found = _start(error, plan)
        case ("streams", *_):
            found = located([error], [source(plan.data_dir / "cashflows.yaml")]).problems
        case ("assets", int(i), str(name), *rest):
            found = _asset(error, plan, i, (name, *rest))
        case ("assumptions", *rest):
            found = _assumption(error._replace(loc=tuple(rest)), plan)
        case _:
            found = located([error], [Source(plan.scenario, {})]).problems
    return found


def _event(error: Error, plan: Composed, n: int, field: tuple[str, *Keys]) -> list[Problem]:
    """An error at `field` of the `n`th event of the scenario names where the value comes from:
    the `events` override that sets the field, else the file of the `extends` chain that writes
    the event, with the line and the key path there. The events that the files keep follow each
    other in the scenario (`loader.load_scenario`). A problem in another file names the scenario
    and the ids that its chain drops below the event: the file of the event loads alone, a drop
    below it may take the stream that the event names."""
    file, i, event, dropped = [
        (layer.file, i, event, layer.dropped)
        for layer in plan.layers
        for i, event in enumerate(layer.own.events)
        if event.id not in layer.dropped
    ][n]
    key: str | int = i
    sources = [source(file)]
    if event.id is not None and plan.changed("events", event.id, field[0]):
        key, sources = event.id, plan.sources()
    drops = f", whose chain drops {', '.join(sorted(dropped))}" if dropped else ""
    return [
        p
        if p.file == plan.scenario
        else replace(p, message=f"{p.message} (for {plan.scenario}{drops})")
        for p in located([error._replace(loc=("events", key, *field))], sources).problems
    ]


def _phase_changes(error: Error, layers: Sequence[Layer]) -> list[Problem]:
    """An unknown phase of a phase change names each change of the files of an `extends` chain,
    less those that a file below drops, that names the phase of `error` (`Error.input`): the
    merged changes are sorted and shifted, so their place names no file."""
    found: list[Problem] = []
    for file, _, dropped in layers:
        held = source(file)
        rows = held.doc.get("phases") if isinstance(held.doc, dict) else None
        found += [
            p
            for k, row in enumerate(rows if isinstance(rows, list) else [])
            if isinstance(row, dict)
            and row.get("phase") == error.input
            and row.get("id") not in dropped
            for p in located([error._replace(loc=("phases", k, "phase"))], [held]).problems
        ]
    return found


def _start(error: Error, plan: Composed) -> list[Problem]:
    """A missing phase at the start names the `phases` of the scenario."""
    return located([error._replace(loc=("phases",))], [source(plan.layers[-1].file)]).problems


def _asset(error: Error, plan: Composed, i: int, field: tuple[str, *Keys]) -> list[Problem]:
    """An error at `field` of the `i`th asset names the `assets` override that sets the field,
    else `assets.yaml`: an unknown phase of a bAV policy, a field that a check refuses."""
    asset = plan.assets[i].id
    if plan.changed("assets", asset, field[0]):
        return located([error._replace(loc=("assets", asset, *field))], plan.sources()).problems
    return located([error], [source(plan.data_dir / "assets.yaml")]).problems


def _assumption(error: Error, plan: Composed) -> list[Problem]:
    """An error at a key path of the assumptions names the override that sets it, else
    `assumptions.yaml`."""
    return located([error], plan.sources(source(plan.data_dir / "assumptions.yaml"))).problems
