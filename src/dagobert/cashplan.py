"""The cashflow plan as a sheet: monthly amounts, scheduled changes, changes between revisions.

Works on the raw YAML rows, so a revision from before a model change still loads. Amounts
are in the euros of the simulation start, salaries and pensions gross."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, cast

import yaml
from babel.lists import format_list

from dagobert import i18n, revisions, schema
from dagobert.i18n import N_, _, pgettext
from dagobert.model.assets import PropertyAsset
from dagobert.model.assumptions import Index
from dagobert.model.base import Unit, units
from dagobert.model.events import (
    AddStreamEvent,
    EndStreamsEvent,
    Event,
    SaleTrigger,
    SellEvent,
    SetStreamEvent,
)
from dagobert.model.months import add_months
from dagobert.model.plan import Plan
from dagobert.model.streams import Stream
from dagobert.money import format_eur

Row = dict[str, Any]
FILE = "cashflows.yaml"
INCOME_KINDS = frozenset({"salary", "pension", "alg1", "other_income", "self_employed"})
INCOME, EXPENSE, SAVINGS = "income", "expense", "savings"  # the roles of a stream (`role`)
LEVEL = "level"  # added by `with_levels`: the level of a non-cumulative index
STARTS, ENDS = N_("starts"), N_("ends")  # a scheduled change of a row
_UNITS = {path[0]: unit for path, unit in units(Stream).items() if len(path) == 1}


def _day(value: object) -> date:
    return date.fromisoformat(str(value)[:10])


def _tags(row: Row) -> set[str]:
    return set(row.get("tags", []))


def key(row: Row) -> tuple[str, str]:
    """A price change is a successor row with the same name, so the start is part of the key."""
    return row["name"], str(row.get("start", ""))


def _base(row: Row, rows: list[Row], phase: str, day: date | None) -> Row | None:
    """The salary row that a derived stream (`of`) follows. A raise is a successor row with
    the same name, so the row active on `day` wins, like in the engine."""
    named = [r for r in rows if "of" in row and r.get("name") == row["of"]]
    return next((r for r in named if day and active(r, day, phase)), named[-1] if named else None)


def monthly(row: Row, rows: list[Row], phase: str, day: date | None = None) -> float | None:
    """Monthly equivalent in `phase`, None when the stream has no amount of its own (ALG1). A
    row from `with_levels` counts at the level of its index. A BU policy counts its premium: its
    benefit pays only after the onset of a disability, which the run draws."""
    base = _base(row, rows, phase, day)
    if base is not None:
        amount = row["share"] * (monthly(base, rows, phase) or 0.0) * row.get("every", 1)
    elif row.get("kind") == "bu":
        amount = row.get("premium", 0.0)
    elif "amount" in row:
        amount = row["amount"]
    elif "gross" in row:
        amount = row["gross"] * row.get("part", 1.0)
    elif "points" in row:
        amount = row["points"] * row["point_value"]
    else:
        return None
    return float(
        amount * row.get("factor", {}).get(phase, 1.0) * row.get(LEVEL, 1.0) / row.get("every", 1)
    )


def with_levels(rows: list[Row], indices: Mapping[str, Index]) -> list[Row]:
    """`rows` with the level at which a `fixed` run pays a stream of a non-cumulative index, the
    clipped mean: a bonus at the mean of its payout ratio. A cumulative index grows from 1 in the
    euros of the start, so its streams stay at 100 %."""
    levels = {name: spec.at_mean for name, spec in indices.items() if not spec.cumulative}
    return [
        row | {LEVEL: levels[row["index"]]} if row.get("index") in levels else row for row in rows
    ]


def alg1_reference(rows: list[Row], day: date, phases: Iterable[str]) -> tuple[str, float] | None:
    """The salary that the engine bases ALG1 on, the last one paid before the claim, before a
    salary conversion: the first of `phases` that pays a monthly (`every: 1`) salary on `day`,
    with their sum. `phases` are those of a scenario up to `day`, the newest first
    (`ui.cashflows._alg1`)."""
    return next(
        (
            (phase, paid)
            for phase in phases
            if (
                paid := sum(
                    monthly(row, rows, phase, day) or 0.0
                    for row in rows
                    if row.get("kind") == "salary"
                    and row.get("every", 1) == 1
                    and active(row, day, phase)
                )
            )
        ),
        None,
    )


def with_alg1(rows: list[Row], amount: float) -> list[Row]:
    """`rows` with `amount` on the ALG1 streams, which have none of their own."""
    return [row | {"amount": amount} if row.get("kind") == "alg1" else row for row in rows]


def role(row: Row) -> str:
    """`INCOME`, `EXPENSE` or `SAVINGS`: a savings plan moves money out of the surplus into an
    asset, so it is neither, and the sheet leaves it out."""
    kind = row.get("kind", "expense")
    return INCOME if kind in INCOME_KINDS else SAVINGS if kind == SAVINGS else EXPENSE


def applies(row: Row, phase: str) -> bool:
    return "phases" not in row or phase in row["phases"]


def accrues_from(row: Row) -> date:
    """A payment every n months is earned or saved up over the n months that end with it. So a
    yearly bonus with its first payment next January already counts today."""
    return add_months(_day(row["start"]), 1 - row.get("every", 1))


def active(row: Row, day: date, phase: str) -> bool:
    return (
        ("start" not in row or accrues_from(row) <= day)
        and ("end" not in row or day < _day(row["end"]))
        and applies(row, phase)
        and "after_sale_of" not in row
    )


def phase_totals(
    members: list[Row], rows: list[Row], day: date, phases: Iterable[str]
) -> dict[str, float]:
    """Monthly sum per phase of the `members` active on `day`. `rows` resolves `of`."""
    return {
        phase: sum(
            monthly(row, rows, phase, day) or 0.0 for row in members if active(row, day, phase)
        )
        for phase in phases
    }


def by_stream(
    rows: list[Row], day: date, phase: str, *, income: bool
) -> dict[tuple[str, str], float]:
    """Monthly amount in `phase` on `day` per category and stream name, of the income or the
    expense streams. Successor rows of a stream add up."""
    sums: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        if role(row) == (INCOME if income else EXPENSE) and active(row, day, phase):
            sums[row.get("cat", ""), row["name"]] += monthly(row, rows, phase, day) or 0.0
    return dict(sums)


def sheet(rows: list[Row], day: date, phases: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    """`income` and `expenses`, each category to its monthly sum per phase. A category that
    pays nothing in every phase is left out, so are the savings plans."""
    sections: dict[str, dict[str, dict[str, float]]] = {}
    for section, kind in ((N_("income"), INCOME), (N_("expenses"), EXPENSE)):
        members = [r for r in rows if role(r) == kind]
        totals = {
            cat: phase_totals([r for r in members if r.get("cat", "") == cat], rows, day, phases)
            for cat in sorted({r.get("cat", "") for r in members})
        }
        sections[section] = {cat: sums for cat, sums in totals.items() if any(sums.values())}
    return sections


def _effects(row: Row | None, rows: list[Row], phases: list[str]) -> dict[str, float]:
    """The effect of `row` on the monthly total of each phase: none for a savings plan, which
    lies outside it."""
    return {
        phase: (monthly(row, rows, phase) or 0.0)
        if row and applies(row, phase) and role(row) != SAVINGS
        else 0.0
        for phase in phases
    }


@dataclass(frozen=True)
class Change:
    when: date | None  # None: a change between revisions, not a scheduled one
    name: str
    what: str
    monthly: dict[str, float]  # effect on the monthly total, per phase
    # the event of the scenario that makes it (`scenario_changes`), for a link to its place
    event: Event | None = field(default=None, compare=False)


def shown(name: str, value: Any) -> str:  # noqa: ANN401 a raw YAML value
    """The value of the field `name` of a stream row as the grids show it: euros as `-1.450 €`, a
    share in percent, a mapping as `work 1, retired 0.5`, a date as `2027-01-01`, none as a dash."""
    if isinstance(value, dict):
        return ", ".join(f"{key} {shown('', v)}" for key, v in value.items())
    if isinstance(value, list):
        return ", ".join(map(str, value))
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "–" if value is None else str(value)
    if (unit := _UNITS.get(name)) is Unit.EUR:
        return format_eur(value, cents=round(value) != value)
    return f"{value * 100:g}%" if unit is Unit.PERCENT else f"{value:g}"


def _field(name: str, was: Any, now: Any) -> str:  # noqa: ANN401 raw YAML values
    """A changed field of a stream row, `amount: -1.450 € → -1.300 €`, its key in the words of the
    session (`ui.gridcolumns.keyword`: the key itself in English)."""
    return f"{pgettext('key', name)}: {shown(name, was)} → {shown(name, now)}"


def _fields(was: Row, now: Row, *, skip: Iterable[str] = ()) -> str:
    """What differs between two versions of a stream row, field by field (`_field`)."""
    differ = sorted(f for f in {*was, *now} - {*skip, LEVEL} if was.get(f) != now.get(f))
    return ", ".join(_field(f, was.get(f), now.get(f)) for f in differ)


def _successor(when: date, was: Row, now: Row, rows: list[Row], phases: list[str]) -> Change:
    """One change for the row `was` that ends on the date on which `now`, a row of its name,
    starts."""
    before, after = _effects(was, rows, phases), _effects(now, rows, phases)
    what = _fields(was, now, skip=("start", "end")) or _("continues")
    return Change(when, now["name"], what, {p: after[p] - before[p] for p in phases})


def scheduled(
    rows: list[Row], after: date, phases: list[str], *, paired: bool = False
) -> list[Change]:
    """Streams that start or end after `after`, in date order. A periodic stream that already
    accrues on `after` is part of the sheet and no change. With `paired`, a row that ends on the
    date on which a row of its name starts (a raise, a new price) makes one change with the
    fields that differ."""
    dated = [
        (_day(row[field]), row, label, sign)
        for row in rows
        for field, label, sign in (("start", STARTS, 1), ("end", ENDS, -1))
        if field in row and (accrues_from(row) if field == "start" else _day(row[field])) > after
    ]
    ends = {(when, row["name"]): row for when, row, label, _sign in dated if label == ENDS}
    starts = {(when, row["name"]): row for when, row, label, _sign in dated if label == STARTS}
    pairs = ends.keys() & starts.keys() if paired else set()
    changes = [
        Change(
            when,
            row["name"],
            _(label),
            {phase: sign * v for phase, v in _effects(row, rows, phases).items()},
        )
        for when, row, label, sign in dated
        if (when, row["name"]) not in pairs
    ] + [
        _successor(when, ends[when, name], starts[when, name], rows, phases) for when, name in pairs
    ]
    return sorted(changes, key=lambda c: (c.when, c.name))


def _bound(row: Row, key: str) -> date | None:
    """The `start` or `end` of a row, None without one."""
    return _day(row[key]) if key in row else None


def _runs_on(row: Row, day: date) -> bool:
    return ("start" not in row or _day(row["start"]) <= day) and (
        "end" not in row or day < _day(row["end"])
    )


def _condition(when: SaleTrigger | None) -> str:
    if when is None:
        return ""
    parts = []
    if when.age is not None:
        parts.append(pgettext("condition", "at {age}").format(age=f"{when.age:g}"))
    if when.liquid_below:
        # a narrow table breaks the text at its spaces, but never before the euro sign
        below = format_eur(when.liquid_below).replace(" ", "\u00a0")
        parts.append(_("with liquid wealth below {amount}").format(amount=below))
    return f" ({format_list(parts, style='or', locale=i18n.language())})"


def scenario_changes(rows: list[Row], plan: Plan, after: date, phases: list[str]) -> list[Change]:
    """What the events of the scenario of `plan` change in the plan after `after`: the streams
    that a sale (also of a property that an event buys) or `end_streams` ends, that start after a
    sale or by `add_stream`, and `set_stream`, by date. A sale on a condition has no date. A
    stream that an event ended, also before `after`, changes no more; one added again under its
    name does. An added stream counts at the level of its index, as `with_levels` gives it."""
    tags = {a.id: set(a.tags) for a in plan.assets if isinstance(a, PropertyAsset)}
    tags |= {e.property.id: set(e.property.tags) for e in plan.bought}
    events = _Events(rows, phases, tags, plan.assumptions.indices)
    changes: list[Change] = []
    for ev in sorted(plan.scenario.events, key=lambda e: e.at or date.max):  # a month in file order
        found = [replace(c, event=ev) for c in events.of(ev, ev.at or after)]
        changes += found if ev.at is None or ev.at > after else []
    return sorted(changes, key=lambda c: (c.when or date.max, c.name))


@dataclass
class _Events:
    """The plan that the events of one scenario change, in their order."""

    rows: list[Row]
    phases: list[str]
    tags: dict[str, set[str]]  # of the assets
    indices: Mapping[str, Index]
    added: list[Row] = field(default_factory=list)  # a derived stream can follow an added one
    ended: set[int] = field(default_factory=set)  # the rows that an event ended, by `id`

    def of(self, ev: Event, day: date) -> list[Change]:
        """The changes of one event, which acts on the streams that run on `day`."""
        note = f" ({ev.note})" if ev.note else ""
        running = [
            r for r in [*self.rows, *self.added] if _runs_on(r, day) and id(r) not in self.ended
        ]
        match ev:
            case SellEvent():
                return self._sale(ev, running)
            case EndStreamsEvent():
                names, tags = set(ev.names), set(ev.tags)
                ending = self._end(running, lambda r: r["name"] in names or tags & _tags(r))
                return [self._change(ev.at, r, f"{_(ENDS)}{note}", -1) for r in ending]
            case AddStreamEvent():
                self.added += with_levels(
                    [ev.stream.model_dump(mode="json", exclude_none=True)], self.indices
                )
                return [self._change(ev.at, self.added[-1], f"{_(STARTS)}{note}", 1)]
            case SetStreamEvent():
                named = [
                    r
                    for r in [*self.rows, *self.added]
                    if r["name"] == ev.name and id(r) not in self.ended
                ]
                spans = [(_bound(r, "start"), _bound(r, "end")) for r in named]
                return [self._set(ev, named[k], note) for k in ev.targets(spans)]
            case _:
                return []

    def _end(self, running: list[Row], ends: Callable[[Row], object]) -> list[Row]:
        """The rows of `running` that `ends`. As in the engine, every row so far that `ends`
        ends, also one that starts later; one that an `add_stream` adds afterwards runs."""
        self.ended |= {id(r) for r in [*self.rows, *self.added] if ends(r)}
        return [r for r in running if ends(r)]

    def _sale(self, ev: SellEvent, running: list[Row]) -> list[Change]:
        """A dated sale ends the rows that name the property and its tagged rows on every path,
        a conditional one on some."""
        why = _("sale of {asset}").format(asset=ev.asset) + _condition(ev.when)
        tagged = self.tags.get(ev.asset, set()) if ev.end_tagged else set()

        def ends(r: Row) -> bool:
            return bool(tagged & _tags(r)) or r.get("property") == ev.asset

        ending = self._end(running, ends) if ev.at else [r for r in running if ends(r)]
        return [self._change(ev.at, r, _("ends: {why}").format(why=why), -1) for r in ending] + [
            self._change(ev.at, r, _("starts: after the {why}").format(why=why), 1)
            for r in self.rows
            if r.get("after_sale_of") == ev.asset
        ]

    def _set(self, ev: SetStreamEvent, row: Row, note: str) -> Change:
        new = {k: v for k in ("amount", "gross", "premium") if (v := getattr(ev, k)) is not None}
        if ev.factor is not None:
            new["factor"] = dict.fromkeys(self.phases, ev.factor)
        now, was = self._effects(row | new), self._effects(row)
        what = ", ".join(
            _field(k, row.get(k), v)
            for k in ("amount", "gross", "premium", "factor")
            if (v := getattr(ev, k)) is not None
        )
        return Change(ev.at, row["name"], what + note, {p: now[p] - was[p] for p in self.phases})

    def _effects(self, row: Row) -> dict[str, float]:
        return _effects(row, [*self.rows, *self.added], self.phases)

    def _change(self, when: date | None, row: Row, what: str, sign: int) -> Change:
        return Change(when, row["name"], what, {p: sign * v for p, v in self._effects(row).items()})


def diff(old: list[Row], new: list[Row], phases: list[str], start: date) -> list[Change]:
    """Added, removed and edited streams between two versions of the plan, and the derived
    streams (`of`) whose base changed. `start` is the simulation start of `old`: a row without
    `start` there and the row of the same name that starts then in `new` are one stream, unless
    `new` keeps a row of that name without `start`. A roll forward writes the old start into the
    streams paid every n months."""
    after = {key(r): r for r in new}
    before = {key(r): r for r in (_rolled(r, start, after) for r in old)}
    changes: list[Change] = []
    for k in dict.fromkeys([*before, *after]):
        was, now = before.get(k), after.get(k)
        was_monthly, now_monthly = _effects(was, old, phases), _effects(now, new, phases)
        if was is None or now is None:
            what = _("added") if was is None else _("removed")
        elif was != now:
            what = _fields(was, now)
        elif was_monthly != now_monthly:  # only a derived stream follows another row
            what = _("follows {base}").format(base=now["of"])
        else:
            continue
        changes.append(
            Change(None, k[0], what, {p: now_monthly[p] - was_monthly[p] for p in phases})
        )
    return changes


def _rolled(row: Row, start: date, new: dict[tuple[str, str], Row]) -> Row:
    """`row` with the start that a roll forward gave it in `new`."""
    rolled = new.get((row["name"], str(start)))
    if "start" in row or rolled is None or key(row) in new:
        return row
    return row | {"start": rolled["start"]}


def plan_at(data_dir: Path, revision: str) -> tuple[list[Row], date]:
    """The streams of `cashflows.yaml` and the simulation start of `assumptions.yaml` at
    `revision`, from one read of its inputs, migrated to the current schema but raw, so a revision
    that the model of today refuses still reads. `ValueError` when they do not read."""
    texts = {
        path: copy.read_text(encoding="utf-8")
        for path, copy in revisions.state(data_dir, revision).items()
        if revisions.is_plan(path)
    }
    migrated = texts | schema.migrate(texts)

    def read(name: str, key: str) -> Any:  # noqa: ANN401 parsed YAML
        try:
            return yaml.safe_load(migrated[name])[key]
        except (KeyError, TypeError, yaml.YAMLError) as err:
            msg = f"{name} of the revision {revision} does not read: {err!r}"
            raise ValueError(msg) from err

    return cast("list[Row]", read(FILE, "streams")), _day(read("assumptions.yaml", "start"))
