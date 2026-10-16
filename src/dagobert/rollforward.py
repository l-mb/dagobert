"""Move the simulation start to a later month: what stands in the way, the amounts in euros of
the old start that the consumer prices carry to the new one, and the gifts that become gifts
before the start."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from dagobert import references, revisions, schema, series, tax
from dagobert.engine.simulation import before
from dagobert.engine.state import TEN_YEARS
from dagobert.i18n import _, ngettext
from dagobert.loader import (
    chain,
    lineage,
    load_assets,
    load_assumptions,
    load_plan,
    read_yaml,
    written,
)
from dagobert.model.assets import Loan
from dagobert.model.assumptions import CPI_INDEX, Assumptions
from dagobert.model.events import STATE_EVENTS, GiftEvent, SellEvent, SetStreamEvent
from dagobert.model.months import add_months, months_between
from dagobert.model.streams import stream_index
from dagobert.problems import Keys, dotted
from dagobert.references import Kind
from dagobert.scenariofiles import concrete_scenarios, scenario_file, scenario_paths
from dagobert.store import Edit, RowEdits
from dagobert.textedit import FIRST, After, First, Scalar, scalars

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

    from dagobert.model.events import Event, PhaseChange
    from dagobert.model.plan import Scenario
    from dagobert.series import MonthlySeries

Amount = tuple[str, Keys, str, float]  # file under the data directory, key path, item, value
KEPT = (*STATE_EVENTS, GiftEvent)  # events before the new start that refuse no roll
DISABILITY = "disability"  # the kind of a forced onset of a disability (`disability.at`)
OPTIONS: Keys = ("tax", "self_employed")  # the social insurance of a business
LOSSES = "loss_carryforward"  # of the options `tax`: the Verlustvortrag (§10d EStG)
CAPITAL_LOSSES = "capital_losses"  # of the options `tax`: the losses of §20 Abs. 6 EStG
START = "start"


@dataclass(frozen=True)
class Passed:
    """An item of a scenario file that lies before the new start, with the concrete scenarios
    (file stems) that run it."""

    file: str
    at: date
    what: str
    kind: str | None  # the type of an event, `DISABILITY`, None for a phase
    scenarios: tuple[str, ...]


# file, date, item, type: the scenarios
Found = defaultdict[tuple[str, date, str, str | None], list[str]]


def passed(data_dir: Path, start: date) -> tuple[list[Passed], list[Passed]]:
    """The events before `start` that a run refuses (all but the stream events, which apply in
    the first month, and the gifts, which the roll moves, `gifts`), with a forced onset of a
    disability before it (the model refuses a plan that starts disabled), and the phases that end
    before it. Each item once per file where it is written, at its date after the `shift` and
    `events` overrides of the scenario."""
    events: Found = defaultdict(list)
    phases: Found = defaultdict(list)
    onset = (read_yaml(data_dir / "assumptions.yaml").get(DISABILITY) or {}).get("at")
    for name, path in concrete_scenarios(data_dir).items():
        layers = written(data_dir, path)
        for file, own in layers:
            for e in own.events:
                if e.at is not None and e.at < start and not isinstance(e, KEPT):
                    events[scenario_file(file.stem), e.at, _event(e), e.type].append(name)
        where, at = next(
            (
                (scenario_file(file.stem), block.get("at"))
                for file, own in reversed(layers)
                if isinstance(block := own.overrides.get(DISABILITY), dict) and "at" in block
            ),
            ("assumptions.yaml", onset),
        )
        if at is not None and (month := date.fromisoformat(str(at)[:10]).replace(day=1)) < start:
            events[where, month, f"{DISABILITY} at", DISABILITY].append(name)
        ordered = sorted(
            ((p, file) for file, own in layers for p in own.phases), key=lambda x: x[0].at
        )
        for (p, file), (following, _then) in pairwise(ordered):
            if following.at <= start:
                phases[scenario_file(file.stem), p.at, _phase(p, following), None].append(name)
    return _listed(events), _listed(phases)


def _listed(found: Found) -> list[Passed]:
    return sorted(
        (Passed(*key, tuple(names)) for key, names in found.items()), key=lambda p: (p.at, p.file)
    )


def _event(e: Event) -> str:
    return " ".join(filter(None, [e.type, e.detail, f"(id {e.id})" if e.id else ""]))


def _phase(p: PhaseChange, following: PhaseChange) -> str:
    return f"phase {p.phase} to {add_months(following.at, -1):%Y-%m}"


@dataclass(frozen=True)
class CpiChange:
    """Consumer prices at `new` over those at `old`. The series ends at `last`, the `estimated`
    months after it grow at `mean` a year."""

    old: date
    new: date
    factor: float
    last: date
    estimated: int
    mean: float

    @property
    def source(self) -> str:
        """Where the factor comes from, after `from` in a sentence of the Overview, in the
        language of the session."""
        span, rate = months_between(self.old, self.new), f"{self.mean:.1%}"
        if not self.estimated:
            return _("the consumer prices of {old} and {new}").format(
                old=f"{self.old:%Y-%m}", new=f"{self.new:%Y-%m}"
            )
        if self.estimated == span:
            return ngettext(
                "{rate} a year (`inflation.mean`) for all {n} month: the consumer prices end "
                "{last}",
                "{rate} a year (`inflation.mean`) for all {n} months: the consumer prices end "
                "{last}",
                span,
            ).format(rate=rate, n=span, last=f"{self.last:%Y-%m}")
        return ngettext(
            "the consumer prices to {last}, then {rate} a year (`inflation.mean`) for {n} month",
            "the consumer prices to {last}, then {rate} a year (`inflation.mean`) for {n} months",
            self.estimated,
        ).format(last=f"{self.last:%Y-%m}", rate=rate, n=self.estimated)


def cpi_change(old: date, new: date, mean: float, prices: MonthlySeries) -> CpiChange:
    last = prices.months[-1]
    by_month = dict(zip(prices.months, prices.values.tolist(), strict=True))
    beyond = [max(months_between(last, month), 0) for month in (old, new)]
    levels = [
        by_month[min(month, last)] * (1 + mean) ** (months / 12)
        for month, months in zip((old, new), beyond, strict=True)
    ]
    return CpiChange(old, new, levels[1] / levels[0], last, beyond[1] - beyond[0], mean)


@dataclass(frozen=True)
class Change:
    file: str
    keys: Keys
    item: str
    old: float
    new: float


def rebase(data_dir: Path, factor: float) -> list[Change]:
    """The amounts in euros of the start that follow the consumer prices, times `factor` and
    rounded to cents, where that changes them: `amount`, `gross` and `point_value` of the `cpi`
    streams (a pension too), in `cashflows.yaml` and in `add_stream` and `set_stream` events, the
    `liquid_below` of a conditional sale, the reference wealth of the spending rule, the yearly
    Werbungskosten, a `cpi` care cost and the contribution of an Altersvorsorgedepot, also as
    scenario overrides, those of an event by its id too."""
    return [
        Change(file, keys, item, old, new)
        for file, keys, item, old in _sites(data_dir)
        if (new := round(old * factor, 2)) != old
    ]


def _sites(data_dir: Path) -> Iterator[Amount]:
    streams: list[dict[str, Any]] = read_yaml(data_dir / "cashflows.yaml")["streams"]
    assumptions = read_yaml(data_dir / "assumptions.yaml")
    assets: list[dict[str, Any]] = read_yaml(data_dir / "assets.yaml")["assets"]
    paths = scenario_paths(data_dir)
    scenarios = {scenario_file(path.stem): read_yaml(path) for path in paths}
    care = assumptions.get("care") or {}
    av = {a["id"] for a in assets if a.get("kind") == "av_depot"}
    indexed: defaultdict[str, set[bool]] = defaultdict(set)
    for row in [*streams, *(row for doc in scenarios.values() for _at, row in _added(doc))]:
        indexed[row["name"]].add(_follows_cpi(row))
    for i, row in enumerate(streams):
        yield from _stream("cashflows.yaml", ("streams", i), row)
    lines = {path: lineage(path) for path in paths}
    for path in paths:
        file = scenario_file(path.stem)
        yield from _scenario_sites(file, scenarios[file], indexed, av, care.get("index", CPI_INDEX))
        yield from _overridden(file, scenarios[file], _reached(path, lines), indexed)
    yield from _reference("assumptions.yaml", (), assumptions)
    if care.get("index", CPI_INDEX) == CPI_INDEX and "cost" in care:
        yield "assumptions.yaml", ("care", "cost"), "care cost", care["cost"]
    for i, a in enumerate(assets):
        if a["id"] in av and "contribution" in a:
            yield (
                "assets.yaml",
                ("assets", i, "contribution"),
                f"{a['id']} contribution",
                a["contribution"],
            )


def _scenario_sites(
    file: str,
    doc: dict[str, Any],
    indexed: dict[str, set[bool]],
    av: set[str],
    care_index: str | None,
) -> Iterator[Amount]:
    for keys, row in _added(doc):
        yield from _stream(file, keys, row)
    for i, e in enumerate(doc.get("events") or []):
        match e.get("type"):
            case "set_stream":
                yield from _set_stream(file, ("events", i), e, indexed.get(e["name"], set()))
            case "sell" if "liquid_below" in (e.get("when") or {}):
                yield (
                    file,
                    ("events", i, "when", "liquid_below"),
                    f"sell {e['asset']} liquid_below",
                    e["when"]["liquid_below"],
                )
            case "inheritance" if e.get("at") is None and isinstance(e.get("cash"), int | float):
                yield file, ("events", i, "cash"), f"inheritance {_givers(e)} cash", e["cash"]
    overrides = doc.get("overrides") or {}
    yield from _reference(file, ("overrides",), overrides)
    care = overrides.get("care") or {}
    if care.get("index", care_index) == CPI_INDEX and "cost" in care:
        yield file, ("overrides", "care", "cost"), "care cost", care["cost"]
    for asset, fields in (overrides.get("assets") or {}).items():
        if asset in av and "contribution" in fields:
            yield (
                file,
                ("overrides", "assets", asset, "contribution"),
                f"{asset} contribution",
                fields["contribution"],
            )


def _givers(event: dict[str, Any]) -> str:
    """The relatives of an inheritance or a gift as written: one name or a list."""
    givers = event.get("from")
    return ", ".join(map(str, givers)) if isinstance(givers, list) else str(givers)


def _reached(
    path: Path, lines: Mapping[Path, list[tuple[Path, Scenario]]]
) -> dict[str | None, list[Event]]:
    """By id, the events that the `events` overrides of the scenario file at `path` reach
    (`loader.adjust`): those of the chain of each scenario file whose chain holds it, its own and
    its descendants' (`lines`: `loader.lineage` by file), so also an event that only a child
    writes, less an id that a file below drops (`loader.kept` leaves its override out)."""
    reached: defaultdict[str | None, list[Event]] = defaultdict(list)
    for files in lines.values():
        own = dict(files).get(path)
        if own is not None and isinstance(ids := own.overrides.get("events"), dict):
            for e in (e for _file, scenario in files for e in scenario.events if e.id in ids):
                reached[e.id].append(e)
    return reached


def _overridden(
    file: str,
    doc: dict[str, Any],
    reached: Mapping[str | None, Sequence[Event]],
    indexed: Mapping[str, set[bool]],
) -> Iterator[Amount]:
    """What the `events` overrides of a scenario file set on the events of an id that they reach
    (`_reached`; `loader.adjust`: on each one that has the field): `amount` and `gross` where those
    events are `set_stream`s on streams that follow the consumer prices (mixed with other indices
    or with nominal amounts, it raises), and the `liquid_below` of a sale. A `stream`: `_added`."""
    for id_, fields in _event_overrides(doc).items():
        keys, group = ("overrides", "events", id_), reached.get(id_, [])
        for field in ("amount", "gross"):
            takers = [e for e in group if field in type(e).model_fields]
            if not isinstance(fields.get(field), int | float) or not takers:
                continue
            names = [fields.get("name", e.name) for e in takers if isinstance(e, SetStreamEvent)]
            cpi = set[bool]().union(*(indexed.get(name, set()) for name in names))
            if len(names) < len(takers):
                cpi.add(False)  # an event amount, nominal at its date
            if len(cpi) > 1:
                msg = (
                    f"{file}: overrides.events.{id_}.{field}: the events of this id follow the "
                    "consumer prices and other indices, give them ids of their own"
                )
                raise ValueError(msg)
            if cpi == {True}:
                item = f"{', '.join(dict.fromkeys(names))} {field}"
                yield file, (*keys, field), item, fields[field]
        sales = [e for e in group if isinstance(e, SellEvent)]
        if sales and "liquid_below" in (when := fields.get("when") or {}):
            item = f"sell {fields.get('asset', sales[0].asset)} liquid_below"
            yield file, (*keys, "when", "liquid_below"), item, when["liquid_below"]


def _event_overrides(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return (doc.get("overrides") or {}).get("events") or {}


# the options of the assumptions in euros of the start, by their key paths, with their items
START_EUROS = (
    (("spending", "reference"), "spending reference"),
    (("spending", "vpw", "floor"), "spending vpw floor"),
    (("tax", "werbungskosten"), "werbungskosten"),
)


def _reference(file: str, keys: Keys, holder: dict[str, Any]) -> Iterator[Amount]:
    """The options of `holder` in start-year euros like `liquid_below` (`START_EUROS`): the
    reference wealth and the VPW floor of the spending rule, the yearly Werbungskosten."""
    for path, item in START_EUROS:
        if isinstance(value := _at(holder, path), int | float):
            yield file, (*keys, *path), item, value


def _added(doc: dict[str, Any]) -> Iterator[tuple[Keys, dict[str, Any]]]:
    """The streams of the `add_stream` events of a scenario file, and those that its `events`
    overrides set, with their key paths."""
    for i, e in enumerate(doc.get("events") or []):
        if e.get("type") == "add_stream":
            yield ("events", i, "stream"), e["stream"]
    for id_, fields in _event_overrides(doc).items():
        if isinstance(fields.get("stream"), dict):
            yield ("overrides", "events", id_, "stream"), fields["stream"]


def _follows_cpi(row: dict[str, Any]) -> bool:
    return stream_index(row) == CPI_INDEX


def _stream(file: str, keys: Keys, row: dict[str, Any]) -> Iterator[Amount]:
    if _follows_cpi(row):
        yield from _amounts(file, keys, row)


def _set_stream(file: str, keys: Keys, event: dict[str, Any], cpi: set[bool]) -> Iterator[Amount]:
    """The new amounts follow the index of the streams of that name, `cpi` tells which."""
    if len(cpi) > 1:
        msg = (
            f"{file}: set_stream {event['name']}: the streams of that name follow the consumer "
            "prices and other indices, give them names of their own"
        )
        raise ValueError(msg)
    if cpi == {True}:
        yield from _amounts(file, keys, event)


def _amounts(file: str, keys: Keys, holder: dict[str, Any]) -> Iterator[Amount]:
    for field in ("amount", "gross", "point_value", "premium"):
        if isinstance(holder.get(field), int | float):
            yield file, (*keys, field), f"{holder['name']} {field}", holder[field]


@dataclass(frozen=True)
class Periodic:
    """A stream paid every `every` months without `start`: its payment months count from the
    simulation start, so the roll writes the old start into it."""

    file: str
    keys: Keys
    name: str
    every: int


def periodic(data_dir: Path) -> list[Periodic]:
    """The streams paid every n months without `start`, in `cashflows.yaml` and in `add_stream`
    events."""
    streams: list[dict[str, Any]] = read_yaml(data_dir / "cashflows.yaml")["streams"]
    rows = [("cashflows.yaml", ("streams", i), row) for i, row in enumerate(streams)] + [
        (scenario_file(path.stem), keys, row)
        for path in scenario_paths(data_dir)
        for keys, row in _added(read_yaml(path))
    ]
    return [
        Periodic(file, keys, row["name"], row["every"])
        for file, keys, row in rows
        if row.get("every", 1) > 1 and "start" not in row
    ]


@dataclass(frozen=True)
class Founded:
    """The first month of a business that runs before the new start: a run from the new start
    would take that as the founding. The roll writes it as `founded` into the options
    `tax.self_employed` at `keys` in `file` that `scenarios` take, behind the key `after`
    (`FIRST`: as their first entry, None: in place of a null `founded`)."""

    file: str
    keys: Keys
    after: str | First | None
    month: date
    scenarios: tuple[str, ...]


@dataclass(frozen=True)
class Carried:
    """A loss pot that a run builds up to the new start: a run from the new start would lose it.
    `key` names it: `LOSSES`, the Verlustvortrag (§10d EStG), or `CAPITAL_LOSSES`, the losses of
    capital income (§20 Abs. 6 EStG), both nominal as the law carries them. The roll writes it as
    `key` into the options `tax` at `keys` in `file` that `scenarios` take, behind the key `after`
    (`FIRST`: as their first entry, None: in place); without such options, into a new `tax` behind
    `start` in `assumptions.yaml` (`keys` empty)."""

    file: str
    keys: Keys
    after: str | First | None
    key: str
    amount: float
    scenarios: tuple[str, ...]


# file, key path of the options, the key to write behind (`FIRST`: first, None: in place)
Anchor = tuple[str, Keys, str | First | None]


def built(data_dir: Path, new: date) -> tuple[list[Founded], list[Carried]]:
    """What the concrete scenarios build before `new` that a run from `new` needs, by a `fixed`
    run from the start (`engine.simulation.before`), each by the options that the scenario takes:
    the nearest `overrides` of its `extends` chain that hold them, else `assumptions.yaml`.
    `Founded`: a business that runs, in a scenario without `founded` and with the options
    `tax.self_employed` (without them `rv` is `none`, which takes no founding); scenarios that
    share them take the earliest month. `Carried`: per pot the smallest of the scenarios that
    share the options (errs towards more tax), where it differs from the one they take now: the
    Verlustvortrag (`Core.income_losses`) and the losses of capital income (`Core.losses`), as
    written: the law keeps both nominal, so a pot that the run leaves alone stays as it is."""
    founded: dict[Anchor, tuple[date, list[str]]] = {}
    # by pot and options: the pot that they take now, the pots of the runs, the scenarios
    carried: dict[tuple[str, Anchor], tuple[float, list[float], list[str]]] = {}
    assumptions = read_yaml(data_dir / "assumptions.yaml")
    for name, path in concrete_scenarios(data_dir).items():
        plan = load_plan(data_dir, path)
        engine = before(plan, new)
        if engine is None:
            continue
        month = None if plan.assumptions.tax.self_employed.founded else engine.first_profit
        spot = _options(path, assumptions, OPTIONS, "founded")
        if month is not None and spot is not None:
            earliest, names = founded.get(spot, (month, []))
            founded[spot] = (min(month, earliest), [*names, name])
        taken = plan.assumptions.tax
        for key, now, pot in (
            (LOSSES, taken.loss_carryforward, engine.income_losses[0]),
            (CAPITAL_LOSSES, taken.capital_losses, engine.losses[0]),
        ):
            spot = _options(path, assumptions, ("tax",), key) or ("assumptions.yaml", (), START)
            _now, pots, names = carried.setdefault((key, spot), (now, [], []))
            pots.append(round(float(pot), 2))
            names.append(name)
    return (
        [Founded(*spot, month, tuple(names)) for spot, (month, names) in founded.items()],
        [
            Carried(*spot, key, min(pots), tuple(names))
            for (key, spot), (now, pots, names) in carried.items()
            if min(pots) != now
        ],
    )


def _options(path: Path, assumptions: dict[str, Any], keys: Keys, key: str) -> Anchor | None:
    """Where the options at `keys` (`tax.self_employed`, `tax`) of the scenario at `path` are
    written: the file, the key path and the key behind which `key` goes, the last one whose value
    takes a line (`FIRST`: none does, None: `key` is there). None: no file holds them."""
    holders = [
        *((scenario_file(file.stem), ("overrides", *keys), raw) for file, raw in chain(path)[::-1]),
        ("assumptions.yaml", keys, assumptions),
    ]
    for file, at, doc in holders:
        if not isinstance(options := _at(doc, at), dict):
            continue
        if key in options:
            return file, at, None
        lines = [k for k, v in options.items() if not isinstance(v, dict | list)]
        return file, at, lines[-1] if lines else FIRST
    return None


def _at(doc: Any, keys: Keys) -> Any:  # noqa: ANN401 raw YAML
    for key in keys:
        doc = doc.get(key) if isinstance(doc, dict) else None
    return doc


@dataclass(frozen=True)
class Moved:
    """A gift before the new start, the row `index` of the events of `file`: the roll moves it
    into the gifts before the start of its relative (`given` in `assumptions.yaml`), its cash and
    securities as their `value`, with the Schenkungsteuer that it computes on them (§14 ErbStG:
    with the gifts before it within ten years)."""

    file: str
    index: int
    relative: str
    at: date
    value: float
    tax: float

    @property
    def item(self) -> str:
        return f"gift {self.relative}"


def gifts(data_dir: Path, start: date) -> list[Moved]:
    """The gifts of the scenario files before `start` as written, oldest first, each with its
    tax. Raises ValueError for a gift that a scenario moves across `start` or that an override or
    a `drop` names (`_movable`), and for a relative that `assumptions.yaml` lacks (defined in the
    overrides of a scenario): its `given` has no place there."""
    a = load_assumptions(data_dir)
    found = sorted(
        (
            (gift.at, scenario_file(path.stem), i, gift)
            for path in scenario_paths(data_dir)
            for i, row in enumerate(read_yaml(path).get("events") or [])
            if row.get("type") == "gift"
            and (gift := GiftEvent.model_validate(row)).at is not None
            and gift.at < start
        ),
        key=lambda found: found[:3],
    )
    _movable(data_dir, start, [(file, gift) for _at, file, _i, gift in found])
    held: defaultdict[str, list[tuple[date, float, float]]] = defaultdict(
        list, {k: [(g.at, g.value, g.tax) for g in r.given] for k, r in a.person.relatives.items()}
    )
    moved: list[Moved] = []
    for at, file, i, gift in found:
        if (key := gift.givers[0]) not in a.person.relatives:
            msg = (
                f"{file}: the gift of {at:%Y-%m} names {key}, whom person.relatives of "
                "assumptions.yaml lacks: the roll moves a gift there, so define the relative there"
            )
            raise ValueError(msg)
        value = gift.cash + (gift.equity.value if gift.equity else 0.0)
        levied = _gift_tax(a, key, at, value, held[key])
        held[key].append((at, value, levied))
        moved.append(Moved(file, i, key, at, value, levied))
    return moved


def _movable(data_dir: Path, start: date, moved: Sequence[tuple[str, GiftEvent]]) -> None:
    """Raise ValueError for a gift that a concrete scenario sees on the other side of `start` than
    its file writes it (`loader.written`: its `shift` and `events` overrides), as the roll moves a
    gift by its file, and for a `shift`, an `events` override or a `drop` of the chain of a moved
    gift (`moved`: its file and the gift) that names its id: it would name nothing after the move,
    or no longer the gift."""
    for name, file, at, run in _crossing(data_dir, start):
        msg = (
            f"{file}: the gift of {at:%Y-%m} falls in {run:%Y-%m} in the scenario {name} (its "
            f"overrides), across the new start {start:%Y-%m}: the roll moves a gift by the month "
            "of its file, so give each scenario a gift of its own or remove the override"
        )
        raise ValueError(msg)
    refs = references.of(data_dir)
    for file, gift in moved:
        for use in (u for kind in (Kind.ITEM, Kind.EVENT) for u in refs.uses(kind, gift.id or "")):
            if PurePosixPath(file).stem in refs.chain(use.scenario or ""):
                msg = (
                    f"{use.file}: {dotted(use.keys)} names the gift {gift.id} of {file} "
                    f"({gift.at:%Y-%m}), which the roll moves into the gifts before the start: "
                    "remove that first"
                )
                raise ValueError(msg)


def _crossing(data_dir: Path, start: date) -> Iterator[tuple[str, str, date, date]]:
    """Per concrete scenario the gifts whose month in its run lies on the other side of `start`
    than in their file: the scenario, the file, the two months."""
    for name, path in concrete_scenarios(data_dir).items():
        for (file, own), (_file, seen) in zip(lineage(path), written(data_dir, path), strict=True):
            yield from (
                (name, scenario_file(file.stem), e.at, run.at)
                for e, run in zip(own.events, seen.events, strict=True)
                if isinstance(e, GiftEvent)
                and e.at
                and run.at
                and (e.at < start) != (run.at < start)
            )


def _gift_tax(
    a: Assumptions, key: str, at: date, value: float, before: list[tuple[date, float, float]]
) -> float:
    """The Schenkungsteuer of a gift of `value` from the relative `key` in the month `at`, with
    the gifts `before` it within ten years."""
    recent = [(v, t) for day, v, t in before if 0 <= months_between(day, at) <= TEN_YEARS]
    return float(
        tax.erbschaftsteuer(
            value,
            [v for v, _t in recent],
            [t for _v, t in recent],
            a.person.relatives[key].relation,
            tax.for_year(a.tax_year),
            inheritance=False,
        )
    )


def _moving(moved: Sequence[Moved]) -> list[Edit]:
    """The edits of the moved gifts: their rows out of the scenario files, into `given` of their
    relatives in `assumptions.yaml`."""
    files: defaultdict[str, list[int]] = defaultdict(list)
    given: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in moved:
        files[m.file].append(m.index)
        given[m.relative].append({"at": m.at, "value": _euros(m.value), "tax": _euros(m.tax)})
    return [
        *(Edit(file, rows={("events",): RowEdits(deleted=rows)}) for file, rows in files.items()),
        Edit(
            "assumptions.yaml",
            rows={
                ("person", "relatives", key, "given"): RowEdits(added=rows)
                for key, rows in given.items()
            },
        ),
    ]


def _euros(amount: float) -> float | int:
    """Cents, a whole number as an int: as the editors write it."""
    return int(amount) if amount == int(amount) else round(amount, 2)


@dataclass(frozen=True)
class Roll:
    """A roll of the start to `cpi.new`: the events that block it, the phases that the run no
    longer sees, the loans whose balance counts at the new start, the changed amounts, the
    streams that get the old start, the businesses that get their founding, the losses that
    carry to the new start and the gifts that become gifts before the start."""

    cpi: CpiChange
    events: list[Passed]
    phases: list[Passed]
    undated: list[Loan]
    changes: list[Change]
    periodic: list[Periodic]
    founded: list[Founded]
    carried: list[Carried]
    gifts: list[Moved]


def check(data_dir: Path, new: date) -> Roll:
    """What a roll of the start to the month of `new` meets and changes, by the consumer prices
    of `data_dir` (`series.cpi`: shipped, then fetched)."""
    a, month = load_assumptions(data_dir), new.replace(day=1)
    if month <= a.start:
        msg = f"the new start {month:%Y-%m} must lie after the start {a.start:%Y-%m}"
        raise ValueError(msg)
    cpi = cpi_change(a.start, month, a.inflation.mean, series.cpi(data_dir))
    events, phases = passed(data_dir, month)
    undated = [x for x in load_assets(data_dir) if isinstance(x, Loan) and x.asof is None]
    return Roll(
        cpi,
        events,
        phases,
        undated,
        rebase(data_dir, cpi.factor),
        periodic(data_dir),
        *built(data_dir, month),
        gifts(data_dir, month),
    )


def inputs(data_dir: Path) -> dict[str, str]:
    """The text of every YAML input by its path: what a roll reads."""
    tree = schema.Tree(data_dir)
    return {path: tree[path] for path in tree if path.endswith(".yaml")}


def seen(data_dir: Path) -> list[revisions.Seen]:
    """Every YAML input as a page reads it when it draws `check`, for `apply`: the revision of
    each before its text."""
    tree = schema.Tree(data_dir)
    return [
        revisions.Seen(path, revisions.last_change(data_dir, path), revisions.digest(tree[path]))
        for path in tree
        if path.endswith(".yaml")
    ]


def _unchanged(data_dir: Path, read: Sequence[revisions.Seen]) -> None:
    """Raise `ConflictError` when a YAML input changed since `read`, also a new one."""
    now = inputs(data_dir)
    for file in read:
        revisions.unchanged(data_dir, file, now.get(file.file))
    if new := sorted(now.keys() - {file.file for file in read}):
        log = revisions.entries(data_dir)
        raise revisions.ConflictError(new[0], [e for e in log if new[0] in e.paths])


def apply(
    data_dir: Path, new: date, *, source: str, read: Sequence[revisions.Seen] | None = None
) -> Roll:
    """Re-base the amounts, write the old start into the periodic streams without one, the
    founding of a business that runs before the new start, the loss pots that the run carries
    there and `start`, move the gifts before it into `given` of their relatives (`Edit.onto` the
    scalars: those files are dumped once), all files in one checked write, one revision of
    `source`. `check` runs inside the write, on the newest inputs; with `read` (`seen`, when the
    page showed the roll) a YAML input that changed since raises `ConflictError`. Raises while an
    event lies before the new start: only the user can say what became of it."""

    def texts() -> tuple[dict[str, str], Roll]:
        if read is not None:
            _unchanged(data_dir, read)
        roll = check(data_dir, new)
        if roll.events:
            msg = f"{len(roll.events)} events lie before {roll.cpi.new:%Y-%m}: remove them first"
            raise ValueError(msg)
        values: defaultdict[str, dict[Keys, Scalar | After]] = defaultdict(dict)
        for c in roll.changes:
            values[c.file][c.keys] = c.new
        for p in roll.periodic:
            values[p.file][(*p.keys, "start")] = After("every", roll.cpi.old)
        for f in roll.founded:
            values[f.file][(*f.keys, "founded")] = (
                f.month if f.after is None else After(f.after, f.month)
            )
        fresh: dict[str, Scalar] = {}  # the pots without options `tax` to hold them
        for loss in roll.carried:
            if loss.keys:
                values[loss.file][(*loss.keys, loss.key)] = (
                    loss.amount if loss.after is None else After(loss.after, loss.amount)
                )
            else:
                fresh[loss.key] = loss.amount
        if fresh:
            values["assumptions.yaml"]["tax",] = After(START, fresh)
        values["assumptions.yaml"]["start",] = roll.cpi.new
        texts = scalars(data_dir, values)
        for edit in _moving(roll.gifts) if roll.gifts else []:
            held = texts.get(edit.name) or (data_dir / edit.name).read_text(encoding="utf-8")
            texts[edit.name] = edit.onto(held) or ""
        return texts, roll

    return revisions.write_returning(data_dir, source, texts)
