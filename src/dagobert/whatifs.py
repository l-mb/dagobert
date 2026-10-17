"""The what-ifs of a first-time user (owner 2026-10-16, issue #14): stop working earlier, lose the
job, take a course, start a business, buy a property. Each is a scenario of its own that extends
the main one and joins the comparison of the Explorer last, with the phases, streams, events and
features that it needs: `edits` gives the `store.Edit`s that `scenariofiles.act` writes as one
revision, `misfits` why the answers do not fit the plan, by the key of their field, in the
language of the session."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import TypeAdapter

from dagobert import datadir, goalseek, references, scenariofiles
from dagobert.engine.alg1 import Refusal, refusal
from dagobert.engine.simulation import before
from dagobert.i18n import N_, _, pgettext
from dagobert.loader import load_plan, load_scenario
from dagobert.model.events import SetStreamEvent, Shift
from dagobert.model.months import add_months, aged, months_between, months_of_age
from dagobert.model.plan import Feature
from dagobert.model.taxes import Land, transfer_tax_rate
from dagobert.money import format_eur
from dagobert.references import Kind
from dagobert.scenariofiles import ALG1, JobLoss, Leave, scenario_file, unique
from dagobert.store import Edit, streams_file

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

BREAK = "alt"  # the phase of a career break, that of a new plan (`datadir.NEW_PHASES`)
BUSINESS = "self-employed"  # the phase of a business that a plan without it gets
COURSE_IDS = ("course", "after-course")
BUSINESS_IDS = ("business", "after-business")
# a property bought in a what-if: a yearly upkeep of 1% of its value, a common rule of thumb, and
# the notary, the land register and the buyer's share of a broker, as in the full example
UPKEEP, COSTS = 0.01, 0.05

# why an answer does not fit the plan, by the key of its field (`misfits`)
EARLY, LATE = datadir.LOSS_EARLY, datadir.LOSS_LATE
NOT_EARLIER = N_("type an age below {age}, at which your plan stops working now")
TOO_EARLY = N_("type an age from {age} on: your plan can stop in {month} at the earliest")
COURSE_LATE = N_("the course ends after you stop working in {month}: type fewer months")
BUSINESS_LATE = N_("type a month before {month}, when the last phase of your plan begins")
UNPAID = N_("a job loss needs a salary: the Cashflows page adds one")
NEW_JOB_EARLY = N_("type a month after the job loss")
OWN_MORE = N_("type at most the price with tax and costs, {cost}")
OWN_MOST = N_("type at most the price with the highest Grunderwerbsteuer and costs, {cost}")
NO_LAND = N_("choose the Land where the property lies")
NO_SPENDING = N_("your plan has no spending that the rent is part of: the Cashflows page adds it")
RENT_MORE = N_("type at most the amount of {stream}, {amount} a month")


class Step(Protocol):
    """A what-if: the scenario that it extends, its name and file name, why its answers do not
    fit the plan and what it writes."""

    @property
    def main(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def stem(self) -> str: ...
    def misfits(self, data_dir: Path) -> dict[str, str]: ...
    def edits(self, data_dir: Path) -> list[Edit]: ...


def _early(data_dir: Path, month: date) -> str | None:
    """Why `month` does not fit: before the start of the plan."""
    start = references.read(data_dir, "assumptions.yaml").get("start")
    if not isinstance(start, date) or month >= (start := start.replace(day=1)):
        return None
    return _(EARLY).format(month=f"{start:%Y-%m}")


def _work(data_dir: Path, main: str) -> goalseek.Dial:
    """The change of the main scenario out of work (`goalseek.work`), its month `origin`. Raises
    `goalseek.NoChangeError` without one."""
    return goalseek.work(load_plan(data_dir, data_dir / scenario_file(main)))


def stops(data_dir: Path, main: str) -> date | None:
    """The month in which the main scenario stops working, None without that change."""
    try:
        return _work(data_dir, main).origin
    except goalseek.NoChangeError:
        return None


def ages(data_dir: Path, main: str) -> tuple[int, int] | None:
    """The earliest whole age at which the main scenario can stop working and the age at which it
    stops now, None without the change."""
    try:
        dial = _work(data_dir, main)
    except goalseek.NoChangeError:
        return None
    born, stop = _dated(dial)
    return _youngest(dial), months_of_age(born, stop) // 12


def _dated(dial: goalseek.Dial) -> tuple[date, date]:
    """The date of birth and the month of the stop, which `goalseek.work` gives its dial."""
    if dial.born is None or dial.origin is None:
        msg = "a dial of work holds the date of birth and the month of the change"
        raise ValueError(msg)
    return dial.born, dial.origin


def _youngest(dial: goalseek.Dial) -> int:
    """The earliest whole age whose month the work dial reaches."""
    born, stop = _dated(dial)
    earliest = add_months(stop, round(dial.low))
    age = months_of_age(born, earliest) // 12
    return age + (aged(born, age) < earliest)


def _last_change(data_dir: Path, main: str) -> date | None:
    """The month of the last change of phase of the main scenario, None without one."""
    phases = load_plan(data_dir, data_dir / scenario_file(main)).scenario.phases
    changes = [c.at for i, c in enumerate(phases) if i and c.phase != phases[i - 1].phase]
    return changes[-1] if changes else None


def _salaried(data_dir: Path) -> bool:
    return any(row.get("kind") == "salary" for row in streams_file(data_dir).rows())


def _refused(misfits: dict[str, str]) -> None:
    if misfits:
        raise ValueError("; ".join(misfits.values()))


@dataclass(frozen=True)
class Earlier:
    """Stop working at `age`, earlier than the main scenario: the `shift` of the id of its change
    out of work (`goalseek.work`), as the work slider of the Explorer moves it. A child's shift
    replaces its parent's, so it counts from the month that the files write."""

    main: str
    age: int
    name: str
    stem: str

    def misfits(self, data_dir: Path) -> dict[str, str]:
        """An age at or after the stop of the plan, or before the earliest month of the dial;
        a plan without the change says why (`goalseek.NoChange`)."""
        try:
            dial = _work(data_dir, self.main)
        except goalseek.NoChangeError as err:
            return {"age": err.why.said()}
        born, stop = _dated(dial)
        moved = months_between(stop, aged(born, self.age))
        if moved >= 0:
            return {"age": _(NOT_EARLIER).format(age=months_of_age(born, stop) // 12)}
        if moved < dial.low:
            earliest = add_months(stop, round(dial.low))
            return {"age": _(TOO_EARLY).format(age=_youngest(dial), month=f"{earliest:%Y-%m}")}
        return {}

    def months(self, data_dir: Path) -> tuple[date, date]:
        """The month in which the main scenario stops working and the one in which this stops."""
        born, stop = _dated(_work(data_dir, self.main))
        return stop, aged(born, self.age)

    def edits(self, data_dir: Path) -> list[Edit]:
        _refused(self.misfits(data_dir))
        dial = _work(data_dir, self.main)
        (_shift, item), _weight = dial.weights[0]
        held = load_scenario(data_dir / scenario_file(self.main)).overrides.get("shift", {})
        own = TypeAdapter(Shift).validate_python(held)
        born, stop = _dated(dial)
        moved = round(own.get(item, 0)) + months_between(stop, aged(born, self.age))
        return [
            *scenariofiles.created(
                data_dir, self.stem, self.name, self.main, {"shift": {item: moved}}
            ),
            scenariofiles.compared(data_dir, self.main, self.stem),
        ]


@dataclass(frozen=True)
class Loss(JobLoss):
    """A job loss (`scenariofiles.lost_job`), with the misfits of its fields."""

    def misfits(self, data_dir: Path) -> dict[str, str]:
        """A loss before the start or at or after the stop, a plan without a salary, a new job
        not after the loss."""
        found: dict[str, str] = {}
        stop = stops(data_dir, self.main)
        if (early := _early(data_dir, self.lost)) is not None:
            found["lost"] = early
        elif stop is not None and self.lost >= stop:
            found["lost"] = _(LATE).format(month=f"{stop:%Y-%m}")
        elif not _salaried(data_dir):
            found["lost"] = _(UNPAID)
        if self.back is not None and self.back <= self.lost:
            found["back"] = _(NEW_JOB_EARLY)
        return found

    def edits(self, data_dir: Path) -> list[Edit]:
        _refused(self.misfits(data_dir))
        return scenariofiles.lost_job(data_dir, self)


def _added(at: date, stream: dict[str, Any]) -> dict[str, Any]:
    return {"at": at, "type": "add_stream", "stream": stream}


@dataclass(frozen=True)
class Course:
    """A course of `months` months from `start`. After a job loss (`loss`): unemployed from
    `start` (`scenariofiles.jobless`), an ALG1 row with `training` in the months of the course
    beside the ALG1 row (ALG1 bei Weiterbildung, rule `alg1`), a new job after it. Else a career
    break (`BREAK`) without pay, back to work after it. Its costs, if any, an expense over its
    months that deducts as work expenses (`deduct: work`, rule `deductions`): whole cents a month
    that add up to `cost`, the cents that do not divide in its last month (`costs`)."""

    main: str
    start: date
    months: int
    cost: float
    loss: bool
    name: str
    stem: str

    @property
    def end(self) -> date:
        return add_months(self.start, self.months)

    def misfits(self, data_dir: Path) -> dict[str, str]:
        """A start before the start of the plan, an end after its stop, a job loss without a
        salary."""
        found: dict[str, str] = {}
        stop = stops(data_dir, self.main)
        if (early := _early(data_dir, self.start)) is not None:
            found["start"] = early
        elif stop is not None and self.end > stop:
            found["months"] = _(COURSE_LATE).format(month=f"{stop:%Y-%m}")
        if self.loss and not _salaried(data_dir):
            found["loss"] = _(UNPAID)
        return found

    def leave(self, data_dir: Path) -> Leave:
        """The stretch of the course, its streams added in its first month."""
        if self.loss:
            unemployed = pgettext("phase", "Unemployed")
            base = scenariofiles.jobless(
                data_dir,
                JobLoss(self.main, self.start, self.end, self.name, self.stem, unemployed),
            )
            training = ALG1 | {
                "name": pgettext("data", "ALG1 during the course"),
                "training": True,
                "phases": [base.phase],
                "end": self.end,
            }
            events = [_added(self.start, training)]
        else:
            base = Leave(
                self.main,
                BREAK,
                pgettext("phase", "Career break"),
                self.start,
                self.end,
                self.name,
                self.stem,
                COURSE_IDS,
                ("course", "end of the course"),
            )
            events = []
        if not self.cost:
            return replace(base, events=tuple(events))
        return replace(
            base,
            events=(*events, *self.costs()),
            features=(*base.features, Feature.DEDUCTIONS),
        )

    def costs(self) -> list[dict[str, Any]]:
        """The costs as an expense from the start in whole cents a month, and the cents that do
        not divide as one more in the last month: an expense of its own there."""
        per, rest = divmod(round(self.cost * 100), self.months)
        last = add_months(self.end, -1)
        spans = [(self.start, last, per), (last, self.end, per + rest)] if rest else []
        return [
            _added(
                start,
                {
                    "name": pgettext("data", "Course costs"),
                    "cat": pgettext("data", "course"),
                    "amount": -datadir.whole(cents / 100),
                    "end": end,
                    "deduct": "work",
                },
            )
            for start, end, cents in spans or [(self.start, self.end, per)]
        ]

    def edits(self, data_dir: Path) -> list[Edit]:
        _refused(self.misfits(data_dir))
        return scenariofiles.away(data_dir, self.leave(data_dir))


@dataclass(frozen=True)
class Founding:
    """The claim to ALG1 of a scenario before a business starts in `month`: the days left and why
    it gives no Gründungszuschuss (`engine.alg1.refusal`), None when it can."""

    month: date
    days: float
    why: Refusal | None


def founding(data_dir: Path, main: str, month: date) -> Founding | None:
    """The claim of the scenario `main` before `month`, as its run has it then
    (`simulation.before`); None without one: no job loss before."""
    plan = load_plan(data_dir, data_dir / scenario_file(main))
    engine = before(plan, month)
    if engine is None or engine.alg1.start is None:
        return None
    i = months_between(plan.assumptions.start, month)
    return Founding(month, engine.alg1.days, refusal(engine.alg1, i, engine.ty))


@dataclass(frozen=True)
class Business:
    """A business from `start` with a `profit` a month before tax and own social insurance: the
    change to the phase `BUSINESS`, which stops the salary, and a `self_employed` stream that pays
    in it (rule `self-employment`; `tax.self_employed` at its defaults: no statutory pension,
    no sick pay), with `gruendungszuschuss` where `founded` (rule `alg1`). The changes after it
    stay: the business ends at the next, the stop of work or a job loss of the main scenario, and
    starts after a job loss without a new job too, which stops the work."""

    main: str
    start: date
    profit: float
    name: str
    stem: str
    founded: bool = False

    def misfits(self, data_dir: Path) -> dict[str, str]:
        """A start before the start of the plan or in its last phase, which it would replace to
        the end of the plan."""
        last = _last_change(data_dir, self.main)
        if (early := _early(data_dir, self.start)) is not None:
            return {"start": early}
        if last is not None and self.start >= last:
            return {"start": _(BUSINESS_LATE).format(month=f"{last:%Y-%m}")}
        return {}

    def edits(self, data_dir: Path) -> list[Edit]:
        _refused(self.misfits(data_dir))
        business = pgettext("data", "Business")
        profit = {
            "name": business,
            "cat": business,
            "kind": "self_employed",
            "amount": self.profit,
            "phases": [BUSINESS],
        } | ({"gruendungszuschuss": True} if self.founded else {})
        leave = Leave(
            self.main,
            BUSINESS,
            pgettext("phase", "Self-employed"),
            self.start,
            None,
            self.name,
            self.stem,
            BUSINESS_IDS,
            ("business", "end of the business"),
            events=(_added(self.start, profit),),
            features=(Feature.SELF_EMPLOYMENT,),
        )
        return scenariofiles.away(data_dir, leave)


def spending(data_dir: Path, main: str, at: date) -> dict[str, float]:
    """The spending of the main scenario that a rent may be part of, by name, with its amount a
    month in `at`, above zero: a monthly expense of `cashflows.yaml` that runs then, no health
    premium, no cost of a let property and no deduction, at the amount of its row or of the last
    `set_stream` of the scenario up to then."""
    plan = load_plan(data_dir, data_dir / scenario_file(main))
    held = {
        s.name: -s.amount
        for s in plan.streams
        if s.managed
        and s.deduct is None
        and s.every == 1
        and s.amount is not None
        and (s.start is None or s.start <= at)
        and (s.end is None or at < s.end)
    }
    for e in sorted(
        (e for e in plan.scenario.events if isinstance(e, SetStreamEvent) and e.at <= at),
        key=lambda e: e.at,
    ):
        if e.name in held and e.amount is not None:
            held[e.name] = -e.amount
    return {name: amount for name, amount in held.items() if amount > 0}


def living(held: Mapping[str, float]) -> str:
    """The spending that a rent comes off by default: the living costs of a quick start
    (`datadir.NAMES`, in either language), else the largest; empty without spending."""
    named = {names.living[0] for names in datadir.NAMES.values()}
    return next((s for s in held if s in named), max(held, key=held.__getitem__, default=""))


@dataclass(frozen=True)
class Purchase:
    """Buy a property in `at` for `price`: a `buy_property` with the Grunderwerbsteuer of `land`,
    `COSTS` and `UPKEEP`, and a loan of what the `own` funds leave of the cost, at
    `datadir.LOAN_RATE` with `datadir.REPAYMENT`, as the loan of a quick start. The `rent` a month
    that it ends (the rent and the costs of the current home, euros of the start) comes off the
    spending `stream` (`spending`, by default `living`) from `at`: a `set_stream` of its amount
    less the rent, with the id of the purchase, so a shift moves both. Its ids those of the
    scenario, numbered where taken."""

    main: str
    at: date
    price: float
    own: float
    land: Land | None
    name: str
    stem: str
    rent: float = 0.0
    stream: str = ""

    @property
    def cost(self) -> float:
        """The price with the Grunderwerbsteuer and the costs; without a Land at the highest rate
        of any Land."""
        rates = [transfer_tax_rate(land, self.at) for land in ([self.land] if self.land else Land)]
        return self.price * (1 + max(rates) + COSTS)

    def misfits(self, data_dir: Path) -> dict[str, str]:
        """A month before the start, own funds beyond the cost (without a Land beyond the highest
        cost, so it shows at once), no Land, a rent without spending or above its amount."""
        found: dict[str, str] = {}
        if (early := _early(data_dir, self.at)) is not None:
            found["at"] = early
        elif self.own > (cost := self.cost):
            found["own"] = _(OWN_MORE if self.land else OWN_MOST).format(cost=format_eur(cost))
        if self.land is None:
            found["land"] = _(NO_LAND)
        if self.rent and early is None:
            held = spending(data_dir, self.main, self.at)
            if self.stream not in held:
                found["rent"] = _(NO_SPENDING)
            elif self.rent > (amount := held[self.stream]):
                found["rent"] = _(RENT_MORE).format(stream=self.stream, amount=format_eur(amount))
        return found

    def edits(self, data_dir: Path) -> list[Edit]:
        _refused(self.misfits(data_dir))
        refs = references.of(data_dir)
        assets = set(refs.names(Kind.ASSET, self.main))
        home = unique(self.stem, assets)
        event: dict[str, Any] = {
            "at": self.at,
            "type": "buy_property",
            "property": {"id": home, "name": pgettext("data", "New property"), "upkeep": UPKEEP},
            "price": self.price,
            "land": str(self.land),
            "costs": COSTS,
        }
        if (owed := datadir.whole(round(self.cost - self.own, 2))) > 0:
            event["loan"] = {
                "id": unique(f"{home}-loan", assets),
                "name": pgettext("data", "Loan of the new property"),
                "balance": -owed,
                "rate": datadir.LOAN_RATE,
                "annuity": datadir.whole(datadir.payment(owed)),
            }
        event["id"] = unique(self.stem, set(refs.names(Kind.ITEM, self.main)))
        events = [event]
        if self.rent:
            left = spending(data_dir, self.main, self.at)[self.stream] - self.rent
            events.append(
                {
                    "at": self.at,
                    "type": "set_stream",
                    "name": self.stream,
                    "amount": -datadir.whole(round(left, 2)),
                    "id": event["id"],
                }
            )
        return [
            *scenariofiles.created(data_dir, self.stem, self.name, self.main, events=events),
            scenariofiles.compared(data_dir, self.main, self.stem, (Feature.PROPERTY,)),
        ]
