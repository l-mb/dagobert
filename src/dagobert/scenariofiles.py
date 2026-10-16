"""The scenario files as a whole: which of them run, which the pages open with, and the file
actions of the Scenarios page (new, copy, rename, delete, a job loss), each a list of
`store.Edit`s that `act` writes as one revision."""

from __future__ import annotations

import ntpath
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from itertools import chain, count
from pathlib import Path
from typing import Any

from dagobert import references, revisions
from dagobert.files import text_only
from dagobert.loader import APP, load_app_settings, load_scenario, written
from dagobert.model.plan import Feature
from dagobert.problems import InputError, Keys, Problem
from dagobert.references import Kind, References
from dagobert.store import Edit, RowEdits, streams_file, write

_SCENARIO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]*")


def scenario_paths(data_dir: Path) -> list[Path]:
    return sorted((data_dir / "scenarios").glob("*.yaml"))


def concrete_scenarios(data_dir: Path) -> dict[str, Path]:
    """The scenario files that `run` simulates, by file stem. `abstract` templates are left out."""
    return {p.stem: p for p in scenario_paths(data_dir) if not load_scenario(p).abstract}


def scenario_labels(names: Mapping[str, str]) -> dict[str, str]:
    """The name of each scenario by file stem, with the stem where two share a name: the pages and
    the report tell the runs apart by it."""
    return {
        stem: name if list(names.values()).count(name) == 1 else f"{name} ({stem})"
        for stem, name in names.items()
    }


def scenario_file(stem: str) -> str:
    """The input of the scenario `stem` under the data directory."""
    return f"scenarios/{stem}.yaml"


def raw_scenarios(data_dir: Path) -> dict[str, dict[str, Any]]:
    """The raw mapping of each scenario file by stem, empty for one without a mapping: a file that
    does not load still has its place. One that does not parse raises `InputError`."""
    return {
        p.stem: references.read(data_dir, scenario_file(p.stem)) for p in scenario_paths(data_dir)
    }


def parents(refs: References, stem: str) -> list[str]:
    """The scenarios that `stem` may extend: all but itself and those that extend it, directly or
    through others, so that no cycle comes up."""
    return [s for s in refs.names(Kind.SCENARIO) if stem not in refs.chain(s)]


def children(refs: References, stem: str) -> list[str]:
    """The scenarios that extend `stem` directly."""
    return sorted((s for s, parent in refs.parents.items() if parent == stem), key=str.casefold)


def _fresh(data_dir: Path, stem: str, name: str | None = None) -> References:
    """Refuse a new stem that is no file name, also one that Windows keeps for a device (`con`,
    `aux.x`: a plan moves between systems), that YAML reads as a value (`extends: on` is true) or
    that exists in any case (a file system may not tell `Plan` from `plan`), and a `name` that
    another scenario has: the results carry the name."""
    if not _SCENARIO_NAME.fullmatch(stem):
        msg = (
            f"{stem!r} is no file name: use letters, digits, spaces, dots, underscores or "
            "dashes, and start with a letter or a digit"
        )
        raise ValueError(msg)
    if ntpath.isreserved(scenario_file(stem)):
        msg = f"Windows keeps {stem!r} for a device: choose another file name"
        raise ValueError(msg)
    if not text_only(stem):
        msg = f"YAML reads {stem!r} as a value, such as true or a number: choose another file name"
        raise ValueError(msg)
    refs = references.of(data_dir)
    if same := [s for s in refs.defined[Kind.SCENARIO] if s.casefold() == stem.casefold()]:
        msg = f"the scenario {same[0]} exists"
        raise ValueError(msg)
    taken = [s for s, [site] in refs.defined[Kind.SCENARIO].items() if site.label == name]
    if taken:
        msg = f"{taken[0]} has the name {name}"
        raise ValueError(msg)
    return refs


def created(
    data_dir: Path,
    stem: str,
    name: str,
    extends: str | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> list[Edit]:
    """The edit of a new scenario file `{name, extends, overrides}` (`New` of the Scenarios page,
    the scenario of the explorer). One of its own starts in the first phase of `assumptions.yaml`
    from the start: a run needs a phase there. One that does not load is not written."""
    _fresh(data_dir, stem, name)
    values: dict[Keys, Any] = {("name",): name}
    if extends is not None:
        values["extends",] = extends
    elif (first := next(iter(references.phases(data_dir)), None)) is not None:
        start = references.read(data_dir, "assumptions.yaml").get("start")
        values["phases",] = [{"from": start, "phase": first}]
    if overrides:
        values["overrides",] = dict(overrides)
    return [Edit(scenario_file(stem), values, create=True)]


def copied(data_dir: Path, stem: str, new: str, name: str) -> list[Edit]:
    """A copy of the scenario `stem` as `new` with the `name`: its text, so the comments stay, and
    its parent. The scenarios that extend `stem` keep it."""
    _held(data_dir, stem)
    _fresh(data_dir, new, name)
    return [Edit(scenario_file(new), {("name",): name}, create=True, origin=scenario_file(stem))]


def _held(data_dir: Path, stem: str) -> None:
    """Refuse an action on a scenario that is gone, deleted or renamed elsewhere since."""
    if not (data_dir / scenario_file(stem)).is_file():
        msg = f"the scenario {stem} is gone"
        raise ValueError(msg)


def renamed(data_dir: Path, stem: str, new: str) -> list[Edit]:
    """The scenario `stem` moved to the file `new`, its text kept, with each `extends` and entry of
    `app.yaml` that names it (`references`)."""
    _held(data_dir, stem)
    refs, file = _fresh(data_dir, new), scenario_file(stem)
    uses: dict[str, dict[Keys, Any]] = {}
    for site in refs.orphans(Kind.SCENARIO, stem, file):
        uses.setdefault(site.file, {})[site.keys] = new
    moved = [Edit(scenario_file(new), create=True, origin=file), Edit(file, remove=True)]
    return moved + [Edit(name, values) for name, values in uses.items()]


def removed(data_dir: Path, stem: str) -> list[Edit]:
    """The scenario `stem` removed, with its entries of `app.yaml`. Refused while a scenario
    extends it (named) and for the last concrete one: every page shows one."""
    _held(data_dir, stem)
    refs, file = references.of(data_dir), scenario_file(stem)
    users = refs.orphans(Kind.SCENARIO, stem, file)
    if extending := sorted({str(site.scenario) for site in users if site.scenario}, key=str.lower):
        one = len(extending) == 1
        msg = (
            f"{', '.join(extending)} extend{'s' * one} it: give {'it' if one else 'them'} another "
            f"parent or delete {'it' if one else 'them'} first"
        )
        raise ValueError(msg)
    concrete = [s for s, doc in raw_scenarios(data_dir).items() if doc.get("abstract") is not True]
    if concrete == [stem]:
        msg = "it is the last scenario that runs: every page shows one"
        raise ValueError(msg)
    # the entries of `app.yaml` from the last: a removed item moves those after it
    entries = sorted((site.keys for site in users if site.file == APP), reverse=True)
    return [Edit(file, remove=True)] + ([Edit(APP, dict.fromkeys(entries))] if entries else [])


IDLE = "unemployed"  # the phase of a job loss that a plan without one gets
ALG1 = {"name": "ALG1", "cat": "ALG1", "kind": "alg1"}  # the stream that a job loss adds
LOSS_IDS = ("job-loss", "new-job")  # the ids of its phase changes, numbered where taken


@dataclass(frozen=True)
class JobLoss:
    """A job loss to add as a scenario (`lost_job`): the scenario that it extends (`main`), the
    month of the loss and of a new job (None: none), the name and the file name of the scenario,
    and the label of the phase of unemployment where the plan has none (`IDLE`)."""

    main: str
    lost: date
    back: date | None
    name: str
    stem: str
    label: str


def _idle(phases: Mapping[str, str], streams: list[dict[str, Any]]) -> str | None:
    """The phase of unemployment: the first phase of an ALG1 stream, else `IDLE`, None while the
    plan has neither."""
    named = [p for s in streams if s.get("kind") == "alg1" for p in s.get("phases") or []]
    return next((p for p in [*named, IDLE] if p in phases), None)


def _phase_at(data_dir: Path, stem: str, month: date) -> str | None:
    """The phase of the scenario `stem` in `month`, as its run sees it (`loader.written`)."""
    changes = sorted(
        (
            (p.at, p.phase)
            for _file, own in written(data_dir, data_dir / scenario_file(stem))
            for p in own.phases
        ),
        key=lambda c: c[0],
    )
    return next((phase for at, phase in reversed(changes) if at <= month), None)


def _id(name: str, taken: set[str]) -> str:
    made = next(i for i in chain([name], (f"{name}-{n}" for n in count(2))) if i not in taken)
    taken.add(made)
    return made


def lost_job(data_dir: Path, loss: JobLoss) -> list[Edit]:
    """The edits of a job loss as a scenario of its own, which extends `loss.main`: the change to
    the phase of unemployment in the month of the loss, and back to the phase that the main
    scenario has in the month of a new job, if any; an ALG1 stream in that phase where
    `cashflows.yaml` has none (its amount comes from the salary before), that phase in
    `assumptions.yaml` where the plan has none, a salary without phases limited to the other
    phases while no scenario runs that phase (a change of no scenario), so it stops, and the
    feature `job_loss` on. Raises ValueError with the reason: a loss before the start, a new
    job before the loss or in a month where the main scenario has no phase or that of
    unemployment (it would change no phase), a taken file name or name."""
    _fresh(data_dir, loss.stem, loss.name)
    assumptions = references.read(data_dir, "assumptions.yaml")
    start = assumptions.get("start")
    if isinstance(start, date) and loss.lost < start.replace(day=1):
        msg = f"the job loss lies before the start {start:%Y-%m}"
        raise ValueError(msg)
    if loss.back is not None and loss.back <= loss.lost:
        msg = "the new job starts before the job loss"
        raise ValueError(msg)
    phases, streams = references.phases(data_dir), streams_file(data_dir).rows()
    idle = _idle(phases, streams) or IDLE
    back = _phase_at(data_dir, loss.main, loss.back) if loss.back else None
    if loss.back is not None and back in (None, idle):
        msg = (
            f"the main scenario {loss.main} is unemployed or has no phase in {loss.back:%Y-%m}, "
            "the month of the new job: type a later month"
        )
        raise ValueError(msg)
    taken = set(references.of(data_dir).names(Kind.ITEM, loss.main))
    changes = [{"from": loss.lost, "phase": idle, "id": _id(LOSS_IDS[0], taken)}]
    if loss.back is not None:
        changes.append({"from": loss.back, "phase": back, "id": _id(LOSS_IDS[1], taken)})
    scenario: dict[Keys, Any] = {
        ("name",): loss.name,
        ("extends",): loss.main,
        ("phases",): changes,
    }
    edits = [Edit(scenario_file(loss.stem), scenario, create=True)]
    if idle not in phases:
        edits.append(Edit("assumptions.yaml", {("phases", idle): {"label": loss.label}}))
    others = [p for p in phases if p != idle]
    unused = not any(  # so a limit of the salary changes no scenario
        isinstance(row, dict) and row.get("phase") == idle
        for doc in raw_scenarios(data_dir).values()
        for row in doc.get("phases") or []
    )
    rows = RowEdits(
        edited={
            i: {"phases": others}
            for i, s in enumerate(streams)
            if unused and s.get("kind") == "salary" and not s.get("phases")
        },
        added=[] if any(s.get("kind") == "alg1" for s in streams) else [ALG1 | {"phases": [idle]}],
    )
    if rows:
        edits.append(Edit("cashflows.yaml", rows={("streams",): rows}))
    off = references.read(data_dir, APP).get("features_off")
    if isinstance(off, list) and Feature.JOB_LOSS in off:
        rest = [f for f in off if f != Feature.JOB_LOSS]
        edits.append(Edit(APP, {("features_off",): rest or None}))
    return edits


Action = Callable[[Path], list[Edit]]  # the edits of a file action from the files now


@dataclass(frozen=True)
class Listed:
    """What a page listed of a file action before the user confirmed it: its edits, and what it
    read of each file that they change, taken before the read: the write refuses a file
    changed since."""

    edits: tuple[Edit, ...]
    seen: tuple[revisions.Seen, ...]


def _read_text(data_dir: Path, name: str) -> str | None:
    path = data_dir / name
    return path.read_text(encoding="utf-8") if path.exists() else None


def listed(data_dir: Path, action: Action) -> Listed:
    """The edits of `action` now and the `Seen` of each file that they change, its revision taken
    before its text: a write between counts as a change. Raises ValueError with the reason when
    the action is refused."""
    edits = tuple(action(data_dir))
    revision = {e.name: revisions.last_change(data_dir, e.name) for e in edits if not e.create}
    return Listed(
        edits,
        tuple(
            revisions.Seen(name, at, revisions.digest(_read_text(data_dir, name)))
            for name, at in revision.items()
        ),
    )


def act(data_dir: Path, action: Action, *, source: str, shown: Listed | None = None) -> None:
    """Write a file action as one revision of `source`: the edits that a page listed (`shown`,
    else those now). Inside the write it is refused when a file that they change changed since,
    or when the action now gives other edits (a new scenario that extends the one to delete)."""
    shown = shown or listed(data_dir, action)

    def check() -> None:
        for seen in shown.seen:
            revisions.unchanged(data_dir, seen, _read_text(data_dir, seen.file))
        if tuple(action(data_dir)) != shown.edits:
            msg = "the inputs changed since the list: look again"
            raise ValueError(msg)

    write(data_dir, shown.edits, source=source, check=check)


def default_scenarios(data_dir: Path) -> list[str]:
    """File stems of the concrete scenarios the explorer opens with."""
    concrete = concrete_scenarios(data_dir)
    return [name for name in load_app_settings(data_dir).scenarios if name in concrete]


def first_scenario(data_dir: Path) -> str:
    """The main scenario: the first default scenario, else the first concrete one. The pages that
    show one scenario open with it. Raises `InputError` without a concrete scenario."""
    if not (names := default_scenarios(data_dir) or list(concrete_scenarios(data_dir))):
        msg = "no scenario runs: add one, or set a scenario to `abstract: false`"
        raise InputError([Problem("scenarios", None, "", msg)])
    return names[0]


def save_default_scenarios(data_dir: Path, names: list[str], *, source: str) -> None:
    write(data_dir, [Edit(APP, {("scenarios",): names})], source=source)
