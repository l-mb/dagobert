"""The version of the data format: a manifest at the root of the data directory, and the
migrations of the raw files from one version to the next."""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Iterator, Mapping
from datetime import date
from itertools import accumulate
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import yaml
from pydantic import Field, TypeAdapter, ValidationError
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

from dagobert import __version__, files
from dagobert.loader import drops_below, validate
from dagobert.model.base import Month, Strict
from dagobert.model.events import Shift
from dagobert.model.months import add_months
from dagobert.problems import parsed, read_text, syntax

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

MANIFEST = "manifest.yaml"
# the files that a migration sees, by their path in the data directory
INPUTS = (
    MANIFEST,
    "assumptions.yaml",
    "assets.yaml",
    "cashflows.yaml",
    "app.yaml",
    "history.csv",
    "actuals.csv",
    "scenarios/*.yaml",
    "prices/*.csv",
)


class Manifest(Strict):
    version: int = Field(alias="schema", ge=1)
    app: str  # the version of Dagobert that set the schema
    # in an export and a directory unpacked from one: the revision of the instance it came from
    base: str | None = None


class SchemaError(ValueError):
    """The data directory has a newer schema than this app reads."""


class Inputs:
    """The raw files of a data directory, a YAML file parsed on first access as a round-trip
    document of ruamel.yaml, so comments survive. A step changes it in place, or replaces the text
    of a file with `set_text`, which keeps every other character of a file that no step parsed. A
    file that does not parse raises `InputError`."""

    def __init__(self, texts: Mapping[str, str]) -> None:
        self._texts = texts
        self._parsed: dict[str, CommentedMap] = {}
        self._written: dict[str, str] = {}

    def paths(self, pattern: str = "*") -> list[str]:
        return sorted(fnmatch.filter(self._texts, pattern))

    def text(self, path: str) -> str:
        """The text of `path` with the changes of the steps before: of a parsed file in the layout
        of the store, else as `set_text` left it."""
        if path in self._parsed:
            return files.dump(self._parsed[path])
        return self._written[path] if path in self._written else self._texts[path]

    def set_text(self, path: str, text: str) -> None:
        self._written[path] = text
        self._parsed.pop(path, None)

    def yaml(self, path: str) -> CommentedMap:
        if path not in self._parsed:
            text = self.text(path)
            try:
                self._parsed[path] = files.yaml().load(text)
            except YAMLError as err:
                raise syntax(path, err, text) from err
        return self._parsed[path]

    def texts(self, paths: Iterable[str]) -> dict[str, str]:
        """The changed files `paths` as text (`text`)."""
        return {path: self.text(path) for path in sorted(paths)}


def _items(node: object, key: str) -> list[CommentedMap]:
    """The mappings in the list under `key` of the mapping `node`. Nothing where the input has
    another shape: the loader names that problem after the migration."""
    found = node.get(key) if isinstance(node, CommentedMap) else None
    return [i for i in found if isinstance(i, CommentedMap)] if isinstance(found, list) else []


def _rename(row: CommentedMap, old: str, new: str) -> bool:
    """Rename the key `old` in place, with its position and its comments. False without it."""
    if old not in row:
        return False
    at, comment = list(row).index(old), row.ca.items.pop(old, None)
    row.insert(at, new, row.pop(old))
    if comment:
        row.ca.items[new] = comment
        if comment[2] is not None:  # an end of line comment keeps its distance
            comment[2].column += len(new) - len(old)
    return True


def _child(node: object, key: str) -> CommentedMap:
    """The mapping under `key` of the mapping `node`, empty where the input has another shape."""
    found = node.get(key) if isinstance(node, CommentedMap) else None
    return found if isinstance(found, CommentedMap) else CommentedMap()


def _trades(inputs: Inputs) -> dict[str, list[CommentedMap]]:
    """The trades by file: of the assets, and of the asset overrides of each scenario."""
    assets = {
        **{path: _items(inputs.yaml(path), "assets") for path in inputs.paths("assets.yaml")},
        **{
            path: list(_child(_child(inputs.yaml(path), "overrides"), "assets").values())
            for path in inputs.paths("scenarios/*.yaml")
        },
    }
    return {path: [t for a in found for t in _items(a, "trades")] for path, found in assets.items()}


def to_2(inputs: Inputs) -> set[str]:
    """The `isin` of a trade becomes `security`, also in the asset overrides of a scenario: gold
    and crypto take a symbol such as XAU."""
    return {
        path
        for path, trades in _trades(inputs).items()
        if sum(_rename(trade, "isin", "security") for trade in trades)  # not `any`: rename all
    }


# the phases of schema 2, which named them in the model, `work` before the first change
PHASES = (
    "# The phases of life that the scenarios switch between, in the order of the columns\n"
    "phases:\n"
    "  work: {label: Work}\n"
    "  unemployed: {label: Unemployed}\n"
    "  alt: {label: Career break}\n"
    "  retired: {label: Retired}\n"
)
WORK = "work"
_START = re.compile(r"^start:[^\n]*(?:\n[ \t]+[^\n]*)*\n?", re.MULTILINE)  # with its continuation


def to_3(inputs: Inputs) -> set[str]:
    """The phases become inputs (`PHASES`, inserted after `start` as text: no other character of
    `assumptions.yaml` changes). A bAV policy without `phases` takes `[work]`, the default of
    schema 2. A concrete scenario without a phase at the start gets `work` from the start in the
    root of its chain: schema 2 ran `work` before the first change."""
    changed: set[str] = set()
    for path in inputs.paths("assumptions.yaml"):
        text, found = inputs.text(path), _plain(inputs, path)
        if isinstance(found, dict) and "phases" not in found:
            at = _START.search(text)
            end = at.end() if at else len(text)
            head = text[:end] if text[:end].endswith("\n") or not end else text[:end] + "\n"
            inputs.set_text(path, head + PHASES + text[end:])
            changed.add(path)
            if (start := _valid(_MONTH, found.get("start"))) is not None:
                changed |= _work_at(inputs, start)
    for path in inputs.paths("assets.yaml"):
        policies = [
            row
            for row in _items(inputs.yaml(path), "assets")
            if row.get("kind") == "bav" and "phases" not in row
        ]
        for row in policies:
            row.insert(_after(row, "contribution"), "phases", _flow(CommentedSeq([WORK])))
        if policies:
            changed.add(path)
    return changed


def _plain(inputs: Inputs, path: str) -> object:
    """The YAML file `path` as PyYAML reads it, for a step that writes it as text."""
    return parsed(inputs.text(path), path)


def _flow[T: CommentedMap | CommentedSeq](node: T) -> T:
    node.fa.set_flow_style()
    return node


def _after(row: CommentedMap, key: str) -> int:
    """The position after `key` in `row`, the end without it."""
    return list(row).index(key) + 1 if key in row else len(row)


def _valid[T](adapter: TypeAdapter[T], value: object) -> T | None:
    """`value` as `adapter` reads it, None in another shape: the loader names that problem."""
    try:
        return adapter.validate_python(value)
    except ValidationError:
        return None


_MONTH, _SHIFT = TypeAdapter(Month), TypeAdapter(Shift)


def _work_at(inputs: Inputs, start: date) -> set[str]:
    """`work` first in the root of the chain of each concrete scenario without a phase change in
    or before `start` as its run sees them (`_changes`), from `start` or the earliest change of a
    scenario of that root: it sorts before every change, and one in its month wins
    (`Scenario.phase_at` takes the later item). So `work` holds before the first change, as in
    schema 2, also in a scenario of that root with a change of its own before `start`."""
    docs = _scenarios(inputs)
    first: dict[str, date] = {}  # by root: the earliest change of a scenario of its chain
    lacking: set[str] = set()  # the roots of the concrete scenarios without a change by `start`
    for stem, (_, doc) in docs.items():
        root, *_ = chain = _chain(docs, stem)
        months = _changes([docs[s][1] for s in chain])
        first[root] = min([first.get(root, start), *months])
        if doc.get("abstract") is not True and all(month > start for month in months):
            lacking.add(root)
    for root in lacking:
        doc = docs[root][1]
        work = _flow(CommentedMap([("from", first[root]), ("phase", WORK)]))
        if isinstance(phases := doc.get("phases"), CommentedSeq):
            phases.insert(0, work)
        else:
            doc.insert(_after(doc, "extends"), "phases", CommentedSeq([work]))
    return {docs[root][0] for root in lacking}


Docs = dict[str, tuple[str, CommentedMap]]  # the scenarios by stem: path and document


def _scenarios(inputs: Inputs) -> Docs:
    return {
        PurePosixPath(path).stem: (path, doc)
        for path in inputs.paths("scenarios/*.yaml")
        if isinstance(doc := inputs.yaml(path), CommentedMap)
    }


def _chain(docs: Docs, stem: str) -> list[str]:
    """The stems of the `extends` chain of `stem`, the root first, up to a missing or circular
    parent: the loader names it."""
    chain = [stem]
    while isinstance(parent := docs[chain[0]][1].get("extends"), str) and parent not in chain:
        if parent not in docs:
            break
        chain.insert(0, parent)
    return chain


def _changes(chain: list[CommentedMap]) -> list[date]:
    """The months of the phase changes of a raw `extends` chain, the root first, as its run sees
    them: without those that a file below drops (`loader.drops_below`), moved by the merged
    `shift` (`loader.adjust`)."""
    drops = drops_below([_names(node.get("drop")) for node in chain])
    layers = list(zip(chain, drops, strict=True))
    merged: dict[str, object] = {}
    for node, gone in layers:
        shift = _child(_child(node, "overrides"), "shift")
        merged |= {i: v for i, v in shift.items() if i not in gone}
    moves = _valid(_SHIFT, merged) or {}
    return [
        add_months(month, moves[i]) if i in moves else month
        for node, gone in layers
        for row in _items(node, "phases")
        if (month := _valid(_MONTH, row.get("from"))) is not None
        and (i := row["id"] if isinstance(row.get("id"), str) else None) not in gone
    ]


def _names(found: object) -> list[str]:
    """The texts in `found`, a list: nothing where the input has another shape."""
    return [i for i in found if isinstance(i, str)] if isinstance(found, list) else []


# `pension_growth` and `inflation.mean` without a value in schema 3
NOMINAL, INFLATION = 0.02, 0.02
_PENSION_GROWTH = re.compile(r"^pension_growth:[ \t]*[^\s#]+", re.MULTILINE)
REAL = "Growth on top of the consumer prices since schema 4: {} nominal less inflation.mean {}"
_CONVERTED = REAL.partition(":")[0]  # in the `assumptions.yaml` of a directory that `to_4` ran on


def to_4(inputs: Inputs) -> set[str]:
    """The pension follows the index of its stream, the consumer prices by default, and
    `pension_growth` becomes the growth on top. A file that sets the nominal growth of schema 3 or
    the inflation gets that growth less its `inflation.mean`, with a comment (`REAL`), so the mean
    path pays the pension of schema 3: `assumptions.yaml` always, as text, so no other character
    changes, also where its default of 2% stays 0; a scenario whose overrides set either, with the
    values of its chain, where its own differs from what it inherits. Every scenario reads the
    values of schema 3 before any is written: a child must not read its parent's new real growth
    as the nominal one. A directory whose `assumptions.yaml` holds the comment is on schema 4
    already and stays: one whose history holds its lost manifest counts as schema 1, so the
    step runs again."""
    paths = inputs.paths("assumptions.yaml")
    if any(_CONVERTED in inputs.text(path) for path in paths):
        return set()
    changed: set[str] = set()
    base = (NOMINAL, INFLATION)
    for path in paths:
        found = _plain(inputs, path)
        if not isinstance(found, dict):
            continue
        base, text = _growth(found, base), inputs.text(path)
        line = f"# {REAL.format(*base)}\npension_growth: {_real(base)!r}"
        if "pension_growth" not in found:
            inputs.set_text(
                path, text + ("\n" if text and not text.endswith("\n") else "") + line + "\n"
            )
        elif _number(found["pension_growth"]) is not None and (at := _PENSION_GROWTH.search(text)):
            inputs.set_text(path, text[: at.start()] + line + text[at.end() :])
        else:
            continue  # a value of another shape: the loader names it
        changed.add(path)
    docs = _scenarios(inputs)
    writes: list[tuple[str, CommentedMap, tuple[float, float]]] = []
    for stem, (path, doc) in docs.items():
        *above, _ = _chain(docs, stem)
        inherited = base
        for parent in above:
            inherited = _growth(_child(docs[parent][1], "overrides"), inherited)
        own = _child(doc, "overrides")
        values = _growth(own, inherited)
        if _number(own.get("pension_growth")) is not None or _real(values) != _real(inherited):
            writes.append((path, own, values))
    for path, own, values in writes:
        own.fa.set_block_style()  # a comment needs it
        own["pension_growth"] = _real(values)
        own.yaml_set_comment_before_after_key("pension_growth", REAL.format(*values), indent=2)
        changed.add(path)
    return changed


def _real(growth: tuple[float, float]) -> float:
    """The nominal growth less the inflation, as the file writes it: no float noise, no -0.0."""
    return round(growth[0] - growth[1], 6) + 0.0


def _number(value: object) -> float | None:
    """A number of the input, None in another shape: the loader names that problem."""
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _growth(node: Mapping[str, object], below: tuple[float, float]) -> tuple[float, float]:
    """The nominal `pension_growth` of schema 3 and the `inflation.mean` that `node`, the
    assumptions or the overrides of a scenario, sets, else those of `below`."""
    inflation = node.get("inflation")
    mean = _number(inflation.get("mean")) if isinstance(inflation, Mapping) else None
    nominal = _number(node.get("pension_growth"))
    return (below[0] if nominal is None else nominal, below[1] if mean is None else mean)


# the comment on a policy that `to_5` makes a Basisrente
BASISRENTE = "A Basisrente since schema 5: only deductible fund_policy events pay into it"


def to_5(inputs: Inputs) -> set[str]:
    """`fund_policy` loses `deductible`: a payment into a Basisrente is an Altersvorsorgeaufwand
    by law (§10 Abs. 1 Nr. 2 b EStG), one into a company pension `Plan` refuses. In the events of
    every scenario and in its `overrides.events` (an emptied override goes). A policy of
    `assets.yaml` without `basisrente` that only payments with `deductible: true` fund, in every
    scenario as its chain merges them (`_funded`), becomes a Basisrente with a comment
    (`BASISRENTE`) where it can be one: an annuity without a contribution of the employer or a
    conversion, which no severance funds (owner 2026-10-14). Any other stays, also one that a
    payment without the flag funds too, and the loader names its payment with the way out
    (`FUNDING`). Files of schema 5 hold no `deductible` of an event, so the step changes nothing
    on them."""
    docs = _scenarios(inputs)
    paid, severed = _funded(docs)
    deducted = {policy for policy, flags in paid.items() if flags == {True}} - severed
    changed: set[str] = set()
    for path, doc in docs.values():
        for row in _items(doc, "events"):
            if row.get("type") == "fund_policy" and "deductible" in row:
                row.pop("deductible")
                changed.add(path)
        overrides = _child(_child(doc, "overrides"), "events")
        for name, row in list(overrides.items()):
            if isinstance(row, CommentedMap) and "deductible" in row:
                row.pop("deductible")
                if not row:
                    del overrides[name]
                changed.add(path)
    for path in inputs.paths("assets.yaml"):
        for row in _items(inputs.yaml(path), "assets"):
            if (
                row.get("kind") == "bav"
                and row.get("id") in deducted
                and "basisrente" not in row
                and row.get("payout") == "annuity"
                and not row.get("contribution")
                and not row.get("conversion")
            ):
                row.fa.set_block_style()  # a comment needs it
                # before `payout`: the comments after the last key belong to the next asset
                row.insert(list(row).index("payout"), "basisrente", True)
                row.yaml_set_comment_before_after_key("basisrente", BASISRENTE, indent=4)
                changed.add(path)
    return changed


def _funded(docs: Docs) -> tuple[dict[object, set[bool]], set[object]]:
    """The policies that a `fund_policy` pays into, each with the `deductible` of its payments,
    and those that a severance funds: of the events of every scenario as its `extends` chain
    merges them, less what a file drops, with the `overrides.events` of the chain."""
    paid: dict[object, set[bool]] = {}
    severed: set[object] = set()
    for stem in docs:
        events: dict[object, dict[str, object]] = {}
        for n, parent in enumerate(_chain(docs, stem)):
            doc = docs[parent][1]
            for name in _names(doc.get("drop")):
                events.pop(name, None)
            for i, row in enumerate(_items(doc, "events")):
                events[row["id"] if isinstance(row.get("id"), str) else (n, i)] = dict(row)
            for name, override in _child(_child(doc, "overrides"), "events").items():
                if name in events and isinstance(override, Mapping):
                    events[name] |= override
        for event in events.values():
            if event.get("type") == "fund_policy":
                paid.setdefault(event.get("policy"), set()).add(event.get("deductible") is True)
            if isinstance(bav := event.get("bav"), Mapping):
                severed.add(bav.get("policy"))
    return paid, severed


# the comment above a list of children that `to_6` migrated: the mark of schema 6
KINDERGELD = "The app pays the Kindergeld since schema 6: set kindergeld true, delete its stream"


def to_6(inputs: Inputs) -> set[str]:
    """The engine pays the Kindergeld of a child with `kindergeld`, true by default: every child
    of schema 5 gets `kindergeld: false`, so a plan pays as before, by its stream. In
    `assumptions.yaml` and in the `overrides.person` of every scenario, a flow or a block row
    keeps its style, with the comment `KINDERGELD` above the list. A file that holds the comment
    is migrated: a directory that lost its manifest changes no more."""
    changed: set[str] = set()
    places: list[tuple[str, tuple[str, ...]]] = [
        *((path, ("person",)) for path in inputs.paths("assumptions.yaml")),
        *((path, ("overrides", "person")) for path, _ in _scenarios(inputs).values()),
    ]
    for path, keys in places:
        *_, person = holders = list(accumulate(keys, _child, initial=inputs.yaml(path)))[1:]
        rows = [row for row in _items(person, "children_born") if "kindergeld" not in row]
        if not rows or KINDERGELD in inputs.text(path):
            continue
        for row in rows:
            row["kindergeld"] = False
        for mapping in holders:
            mapping.fa.set_block_style()  # a comment needs it
        person.yaml_set_comment_before_after_key("children_born", KINDERGELD, indent=2 * len(keys))
        changed.add(path)
    return changed


# One step per version, named after its target (`to_2`): `STEPS[n - 1]` migrates schema n to
# n + 1 in place and returns the paths that it changed. It may move a field between files.
# `datadir.open` writes the migrated files with the manifest as one revision. A step must change
# nothing on files of a later schema: files without a manifest count as schema 1 (a directory that
# lost it, a revision before the first manifest), so every step runs on them. Each step has a
# fixture of the schema before it in `tests/schemas/<n>/`.
Step = Callable[[Inputs], set[str]]
STEPS: tuple[Step, ...] = (to_2, to_3, to_4, to_5, to_6)


def current() -> int:
    """The schema that this app reads and writes."""
    return len(STEPS) + 1


def manifest(texts: Mapping[str, str]) -> Manifest | None:
    return validate(Manifest, texts[MANIFEST], MANIFEST) if MANIFEST in texts else None


def version(texts: Mapping[str, str]) -> int:
    """The schema of the files: 1 without a manifest, the format of the first release. One newer
    than this app reads raises `SchemaError`."""
    found = manifest(texts)
    if found and found.version > current():
        msg = (
            f"{MANIFEST}: schema {found.version}, written by Dagobert {found.app}. This is "
            f"Dagobert {__version__}, which reads schema {current()} at most. Update the app."
        )
        raise SchemaError(msg)
    return found.version if found else 1


def migrate(texts: Mapping[str, str]) -> dict[str, str]:
    """The files that change on the way to the current schema, by path, the manifest last.
    Nothing when they are current. Files without a manifest count as schema 1, the format of the
    first release, so every step runs on them (and changes nothing on files of a later schema) and
    the manifest comes last. The other files keep every character."""
    start, found = version(texts), manifest(texts)
    if start == current():
        return {}
    inputs = Inputs(texts)
    changed = set[str]().union(*(step(inputs) for step in STEPS[start - 1 :]))
    return inputs.texts(changed) | {MANIFEST: manifest_text(found.base if found else None)}


def manifest_text(base: str | None = None) -> str:
    """A new manifest, of a migration, the first open or an export, which names its `base`."""
    return "# Written by Dagobert. Do not edit.\n" + yaml.safe_dump(
        {"schema": current(), "app": __version__} | ({"base": base} if base else {}),
        sort_keys=False,
    )


class Tree(Mapping[str, str]):
    """The texts of the `INPUTS` of a data directory by path, read on access."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._paths = sorted(
            {
                path.relative_to(root).as_posix()
                for pattern in INPUTS
                for path in root.glob(pattern)
                if path.is_file()
            }
        )

    def __getitem__(self, path: str) -> str:
        if path not in self._paths:
            raise KeyError(path)
        return read_text(self.root / path, path)

    def __contains__(self, path: object) -> bool:
        return path in self._paths

    def __iter__(self) -> Iterator[str]:
        return iter(self._paths)

    def __len__(self) -> int:
        return len(self._paths)


def migrate_dir(directory: Path) -> None:
    """Migrate the files of `directory` in place, unchecked: for a temporary copy."""
    for path, text in migrate(Tree(directory)).items():
        files.atomic_write(directory / path, text)
