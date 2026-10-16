"""A scenario file, `app.yaml`, and the `Plan` of a run: the inputs together, with the checks
across them."""

from __future__ import annotations

from collections import Counter
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Any, LiteralString, NamedTuple

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError

from dagobert.model.assets import (
    Asset,
    AssetBase,
    AvDepot,
    EquityAsset,
    FixedIncomeAsset,
    Loan,
    LotAsset,
    PensionPolicy,
    PropertyAsset,
)
from dagobert.model.assumptions import CPI_INDEX, Assumptions, unknown_phase
from dagobert.model.base import Strict, refuse_all
from dagobert.model.events import (
    STATE_EVENTS,
    AcquisitionEvent,
    AddStreamEvent,
    BuyEvent,
    BuyPropertyEvent,
    EndStreamsEvent,
    Event,
    EventBase,
    FundPolicyEvent,
    PhaseChange,
    PolicyFunding,
    RepayAction,
    RepayEvent,
    SellEvent,
    SetStreamEvent,
    SeveranceEvent,
    WriteOffEvent,
)
from dagobert.model.streams import Stream, StreamKind

if TYPE_CHECKING:
    from collections.abc import Mapping

# the keys of `overrides` that change the scenario and the assets; the others the assumptions
SCENARIO_KEYS = ("events", "shift", "assets")


def split(overrides: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The overrides of the assumptions, and those of the scenario (`SCENARIO_KEYS`)."""
    return (
        {k: v for k, v in overrides.items() if k not in SCENARIO_KEYS},
        {k: v for k, v in overrides.items() if k in SCENARIO_KEYS},
    )


class Scenario(Strict):
    name: str = Field(description="The name in the results, the tabs and the summary table")
    note: str = ""
    extends: str | None = Field(
        default=None,
        description="The scenario that this one starts from: its phases, events and overrides "
        "apply here too, unless this one leaves them out or changes them",
    )
    abstract: bool = Field(
        default=False,
        description="A template: only a base for other scenarios, it does not run itself",
    )
    phases: list[PhaseChange] = Field(default=[])
    events: list[Event] = Field(default=[])
    drop: list[str] = Field(
        default=[],
        description="Ids of the phases and events of the parents that this scenario leaves out",
    )
    overrides: dict[str, object] = Field(default={})

    @field_validator("phases", mode="after")
    @classmethod
    def _sorted_phases(cls, phases: list[PhaseChange]) -> list[PhaseChange]:
        return sorted(phases, key=lambda p: p.at)

    @property
    def added_streams(self) -> list[Stream]:
        """The streams of the `add_stream` events."""
        return [e.stream for e in self.events if isinstance(e, AddStreamEvent)]

    def phase_at(self, month: date) -> str | None:
        """The phase of the last change on or before `month`, none before the first."""
        return next((p.phase for p in reversed(self.phases) if p.at <= month), None)

    def phase_of(self, month: date) -> str | None:
        """`phase_at`, before the first change the phase of the first: a recorded month before
        the start compares with the plan of the start."""
        return self.phase_at(month) or next((p.phase for p in self.phases), None)


class Feature(StrEnum):
    """A part of life that a plan may not model: the app hides its items while it is off and its
    data is absent (`ui.mode.FEATURES`)."""

    TRACKING = "tracking"
    GOLD_CRYPTO = "gold_crypto"
    PROPERTY = "property"
    SELF_EMPLOYMENT = "self_employment"
    CHILDREN = "children"
    ESTATES = "estates"
    JOB_LOSS = "job_loss"
    DISABILITY = "disability"
    DEDUCTIONS = "deductions"
    SPENDING_RULES = "spending_rules"
    CARE = "care"
    ALLOCATION = "allocation"


class AppSettings(Strict):
    """`app.yaml`: what the app opens with."""

    scenarios: list[str] = Field(
        default=[],
        description="File stems of the scenarios that the explorer opens with. The first one "
        "opens the pages that show one scenario",
    )
    features_off: list[Feature] = Field(
        default=[],
        description="The parts of life that the plan does not model: the app hides them while "
        "their data is absent",
    )


# what an event names that no stream has: the stream name or the tag
UNKNOWN_STREAM: dict[str, LiteralString] = {
    "name": "{event} of {month} names the stream {name}, which is neither in cashflows.yaml nor "
    "an add_stream of the scenario: after a rename, change or remove the event too",
    "tag": "{event} of {month} names the tag {name}, which no stream of cashflows.yaml or of an "
    "add_stream of the scenario has: after a change of the tags, change or remove the event too",
}


def _stream_refs(event: EventBase) -> list[tuple[tuple[str | int, ...], str, str]]:
    """The stream names and tags that `event` sets or ends: their key paths in it, `name` or
    `tag`, and the name or the tag."""
    match event:
        case SetStreamEvent():
            return [(("name",), "name", event.name)]
        case EndStreamsEvent():
            return [
                *((("names", i), "name", name) for i, name in enumerate(event.names)),
                *((("tags", i), "tag", tag) for i, tag in enumerate(event.tags)),
            ]
    return []


STREAM_UPDATE: LiteralString = "{event} of {month} sets {key} of the stream {name}: {problem}"
STREAM_ENDED: LiteralString = (
    "{event} of {month} changes no row of {name}: every row ended before it"
)
# what a sale refuses: a field of the other kind of asset, a gift (no price) taxed as a sale
SALE: dict[str, LiteralString] = {
    "misfit": "sell {asset}: {fields} only for the sale of {other}",
    "gift": "sell {asset}: a gift (price 0) is no taxable sale",
}


def _sale_problems(event: SellEvent, *, holding: bool) -> list[tuple[str, str, dict[str, str]]]:
    """What `event` refuses (a key of `SALE`), at its key with what the message names: a field
    of the other kind of asset, a gift of a property marked `taxable`, which booked its cost as a
    §23 loss."""
    if odd := event.misfits(holding=holding):
        other = "a property" if holding else "gold or crypto"
        return [(odd[0], "misfit", {"fields": ", ".join(odd), "other": other})]
    if event.price == 0 and event.taxable:
        return [("taxable", "gift", {})]
    return []


def _update_problems(event: SetStreamEvent, stream: Stream) -> dict[str, str]:
    """What is wrong with the fields that `event` sets on `stream`, by key: one that its kind does
    not read (`Stream.amount_key`), or a row that fails with it, such as an expense above zero."""
    keys = [k for k in ("amount", "gross", "premium") if getattr(event, k) is not None]
    takes = stream.amount_key
    wrong = {
        k: f"it takes {takes or 'no amount'}"
        for k in keys
        if k != takes and not (k == "premium" and stream.kind == StreamKind.BU)
    }
    if event.factor is not None and stream.kind == StreamKind.BU:
        wrong["factor"] = "a BU policy runs by its contract, not by phase"
    if wrong:
        return wrong
    try:
        event.applied(stream)
    except ValidationError as err:
        why = "; ".join(
            e["msg"].removeprefix("Value error, ").removeprefix(f"{stream.name}: ")
            for e in err.errors()
        )
        return dict.fromkeys(keys, why)
    return {}


def _phases_of(stream: Stream) -> list[tuple[tuple[str | int, ...], str]]:
    """The phases that `stream` names, with their key paths in it."""
    return [
        *((("phases", j), name) for j, name in enumerate(stream.phases or [])),
        *((("factor", name), name) for name in stream.factor),
    ]


NO_PHASE: LiteralString = (
    "the scenario has no phase at its start {start}: add a change from {start} or earlier to its "
    "phases or to those of a scenario that it extends, to one of {known}"
)

Loc = tuple[str | int, ...]
Use = tuple[Loc, str | None]  # a name that the inputs use, at its key path


class Check(NamedTuple):
    """Names that the inputs use, with the names they may use: an unknown one is a `problem`."""

    problem: LiteralString  # of the `{name}`
    uses: list[Use]
    known: set[str]


TWICE: LiteralString = (
    "another stream has the name {name} and the same start: events and the plan cannot tell them "
    "apart"
)


# what a purchase refuses: an id that another asset has, a use before the purchase
PURCHASE: dict[str, LiteralString] = {
    "taken": "{what}: the id {name} is taken, by an asset or by another buy_property",
    "early": "{what} names {name} in or before the month of the buy_property that brings it, "
    "{bought}",
}


# what a dated event of a concrete scenario refuses: a month the run cannot reach
UNTIMELY: dict[str, LiteralString] = {
    "start": "{event} of {month} lies before the start {start}: only end_streams, set_stream and "
    "add_stream apply from the first month. Once it happened, change the inputs that it changed "
    "and remove it",
    "matures": "{event} of {month} funds the policy {policy}, which pays out in {matures}: date "
    "it in that month or before",
}


PER_PATH: LiteralString = (
    "the sale of {asset} at `liquid_below` ends or starts the stream {name} on some paths, "
    "which repays the loan {loan}: a loan is the same on every path. Sell it at an age or a date, "
    "or take the stream out of it (its `property`, tags, `after_sale_of`, `end_tagged`)"
)


def _funded(event: EventBase) -> str | None:
    """The policy that `event` pays into, None for another event."""
    match event:
        case FundPolicyEvent():
            return event.policy
        case SeveranceEvent(bav=PolicyFunding() as bav):
            return bav.policy
    return None


def _named_assets(stream: Stream) -> list[tuple[str, str]]:
    """The keys of `stream` that name an asset in its months: the loan that it repays, the
    property that it lets or costs."""
    return [(key, name) for key in ("repays", "property") if (name := getattr(stream, key))]


LET: LiteralString = (
    "the stream {stream} names {id} as its property, so {id} is let: its AfA and the tax of its "
    "sale need this field"
)
LATE: LiteralString = (
    "{id} is bought after the start {start}: a later purchase is a buy_property event"
)
# what a policy refuses: money free of tax that a Basisrente would pay out at its share, a premium
# of your own into a company pension, whose payout is taxed in full
FUNDING: dict[str, LiteralString] = {
    "bav": "a severance pays its tax-free part into a company pension, but {id} is a "
    "Basisrente: name a policy without basisrente",
    "basisrente": "fund_policy pays your own premium into a Basisrente, but {id} has no "
    "basisrente: set basisrente on {id} if it is one, else remove the event (a private top-up of "
    "a company pension is not modelled)",
}


def _fundings(event: EventBase) -> list[tuple[tuple[str, ...], str, str, bool]]:
    """The policies that `event` pays into: the key path of each in it, the kind of the payment
    (`FUNDING`), the id and whether the policy must be a Basisrente."""
    match event:
        case SeveranceEvent(bav=PolicyFunding() as bav):
            return [(("bav", "policy"), "bav", bav.policy, False)]
        case FundPolicyEvent():
            return [(("policy",), "basisrente", event.policy, True)]
    return []


def _purchase_error(
    kind: str,
    loc: tuple[str | int, ...],
    what: str,
    name: str,
    buy: BuyPropertyEvent | None = None,
) -> InitErrorDetails:
    bought = f"{buy.at:%Y-%m}" if buy else ""
    return InitErrorDetails(
        type=PydanticCustomError(
            "purchase", PURCHASE[kind], {"what": what, "name": name, "bought": bought}
        ),
        loc=loc,
        input=name,
    )


def _listed(loc: Loc, names: list[str] | None) -> list[Use]:
    """The `names` of a list at `loc`, each at its key path."""
    return [((*loc, j), name) for j, name in enumerate(names or [])]


def _bases(streams: list[Stream]) -> list[Stream]:
    """The salary streams that a stream may follow (`of`) and a bAV policy convert: none follows
    another."""
    return [s for s in streams if s.kind == StreamKind.SALARY and s.of is None]


class Plan(Strict):
    """Fully composed input for one engine run."""

    assumptions: Assumptions
    assets: list[Asset]
    streams: list[Stream]
    scenario: Scenario

    @property
    def bought(self) -> list[BuyPropertyEvent]:
        return [e for e in self.scenario.events if isinstance(e, BuyPropertyEvent)]

    def phase_at(self, month: date) -> str:
        """The phase of the scenario in `month`. Raises ValueError before its first change: a
        concrete scenario has one at or before `start`."""
        if (phase := self.scenario.phase_at(month)) is None:
            msg = f"{self.scenario.name}: no phase in {month:%Y-%m}, before its first change"
            raise ValueError(msg)
        return phase

    def _ids(self, kind: type[AssetBase]) -> set[str]:
        """The ids of the assets of `kind`, of a property or a loan also those of a purchase."""
        bought: dict[type[AssetBase], set[str]] = {
            PropertyAsset: {e.property.id for e in self.bought},
            Loan: {e.loan.id for e in self.bought if e.loan},
        }
        return {a.id for a in self.assets if isinstance(a, kind)} | bought.get(kind, set())

    @property
    def all_streams(self) -> list[Stream]:
        """The streams of the plan and of the `add_stream` events."""
        return [*self.streams, *self.scenario.added_streams]

    def _plan_uses(self, field: str) -> list[Use]:
        """`field` of each stream of the plan, at its key path."""
        return [(("streams", k, field), getattr(s, field)) for k, s in enumerate(self.streams)]

    def _added_uses(self, field: str) -> list[Use]:
        """`field` of the stream of each `add_stream` event, at its key path."""
        return [
            (("scenario", "events", i, "stream", field), getattr(e.stream, field))
            for i, e in enumerate(self.scenario.events)
            if isinstance(e, AddStreamEvent)
        ]

    def _event_uses(self, kind: type[EventBase], field: str) -> list[Use]:
        """`field` of each event of `kind`, at its key path."""
        return [
            (("scenario", "events", i, field), getattr(e, field))
            for i, e in enumerate(self.scenario.events)
            if isinstance(e, kind)
        ]

    def _asset_uses(self, kinds: tuple[type[AssetBase], ...], field: str) -> list[Use]:
        """`field` of each asset of `kinds`, at its key path."""
        return [
            (("assets", i, field), getattr(a, field))
            for i, a in enumerate(self.assets)
            if isinstance(a, kinds)
        ]

    def _plan_checks(self) -> list[Check]:
        """Names that streams, the assumptions and the assets use, with the names they may use. A
        stream of the plan follows a salary of the plan: an added one may come after it."""
        a, streams, sp = self.assumptions, self.all_streams, self.assumptions.spending
        return [
            Check(
                "the index {name} is not defined: add it to assumptions.indices",
                [
                    *self._plan_uses("index"),
                    *self._added_uses("index"),
                    *([(("assumptions", "care", "index"), a.care.index)] if a.care else []),
                ],
                {CPI_INDEX, *a.indices},
            ),
            Check(
                "no expense stream has the category {name}",
                [
                    *((("assumptions", "scale", "categories", c), c) for c in a.scale.categories),
                    *_listed(
                        ("assumptions", "spending", "categories"), sp.categories if sp else None
                    ),
                    *_listed(
                        ("assumptions", "spending", "age_categories"),
                        sp.age_categories if sp else None,
                    ),
                ],
                {s.cat for s in streams if s.managed},
            ),
            Check(
                "no stream of kind savings has the name {name}",
                [(("assumptions", "scale", "savings", n), n) for n in a.scale.savings],
                {s.name for s in streams if s.kind == StreamKind.SAVINGS},
            ),
            Check(
                "no salary stream without `of` of cashflows.yaml has the name {name}",
                self._plan_uses("of"),
                {s.name for s in _bases(self.streams)},
            ),
            Check(
                "no salary stream without `of` has the name {name}",
                self._added_uses("of"),
                {s.name for s in _bases(streams)},
            ),
            Check(
                "no monthly salary stream without `of` has the name {name}",
                self._asset_uses((PensionPolicy,), "salary"),
                {s.name for s in _bases(streams) if s.every == 1},
            ),
            Check(
                "the return class {name} is not defined in returns",
                [
                    *self._asset_uses((PropertyAsset, PensionPolicy, AvDepot, LotAsset), "growth"),
                    *(
                        (("scenario", "events", i, "property", "growth"), e.property.growth)
                        for i, e in enumerate(self.scenario.events)
                        if isinstance(e, BuyPropertyEvent)
                    ),
                ],
                set(a.returns),
            ),
        ]

    def _event_checks(self) -> list[Check]:
        """Assets and loans that events and streams name, with the ones that exist."""
        events = self.scenario.events
        return [
            Check(
                "no property has the id {name}",
                [
                    *self._plan_uses("after_sale_of"),
                    *self._added_uses("after_sale_of"),
                    *self._plan_uses("property"),
                    *self._added_uses("property"),
                    *self._asset_uses((Loan,), "finances"),
                ],
                self._ids(PropertyAsset),
            ),
            Check(
                "no equity, fixed-income, gold or crypto asset has the id {name}",
                [*self._plan_uses("into"), *self._added_uses("into")],
                self._ids(EquityAsset) | self._ids(FixedIncomeAsset) | self._ids(LotAsset),
            ),
            Check(
                "no property, gold or crypto asset has the id {name}",
                self._event_uses(SellEvent, "asset"),
                self._ids(PropertyAsset) | self._ids(LotAsset),
            ),
            Check(
                "no gold or crypto asset has the id {name}",
                self._event_uses(BuyEvent, "asset"),
                self._ids(LotAsset),
            ),
            Check(
                "no bAV policy has the id {name}",
                [
                    *self._event_uses(FundPolicyEvent, "policy"),
                    *(
                        (("scenario", "events", i, "bav", "policy"), e.bav.policy)
                        for i, e in enumerate(events)
                        if isinstance(e, SeveranceEvent) and e.bav
                    ),
                ],
                self._ids(PensionPolicy),
            ),
            Check(
                "no equity asset has the id {name}",
                self._event_uses(WriteOffEvent, "asset"),
                self._ids(EquityAsset),
            ),
            Check(
                "no relative of person.relatives has the name {name}",
                [
                    (("scenario", "events", i, "from"), giver)
                    for i, e in enumerate(events)
                    if isinstance(e, AcquisitionEvent)
                    for giver in e.givers
                ],
                set(self.assumptions.person.relatives),
            ),
            Check(
                "no loan has the id {name}",
                [
                    *self._plan_uses("repays"),
                    *self._added_uses("repays"),
                    *self._event_uses(RepayEvent, "loan"),
                    *(
                        (("scenario", "events", i, "then", j, "repay"), t.repay)
                        for i, e in enumerate(events)
                        if isinstance(e, SellEvent)
                        for j, t in enumerate(e.then)
                        if isinstance(t, RepayAction)
                    ),
                ],
                self._ids(Loan),
            ),
        ]

    @model_validator(mode="after")
    def _references_known(self) -> Plan:
        """Every name that a stream, an asset, an event or the assumptions use exists, and no two
        streams of the plan share name and start. An `add_stream` may add a name again, so an
        event changes the new one. The errors are at the uses, so the loader names their files."""
        rows = Counter((s.name, s.start) for s in self.streams)
        found = [
            InitErrorDetails(
                type=PydanticCustomError("unknown", check.problem, {"name": name}),
                loc=loc,
                input=name,
            )
            for check in [*self._plan_checks(), *self._event_checks()]
            for loc, name in check.uses
            if name is not None and name not in check.known
        ] + [
            InitErrorDetails(
                type=PydanticCustomError("twice", TWICE, {"name": s.name}),
                loc=("streams", k, "name"),
                input=s.name,
            )
            for k, s in enumerate(self.streams)
            if rows[s.name, s.start] > 1
        ]
        refuse_all(self, found)
        return self

    @model_validator(mode="after")
    def _events_in_time(self) -> Plan:
        """A dated event of a concrete scenario lies in the run: before the start only the stream
        events apply (`STATE_EVENTS`, in the first month), and a policy takes funding up to the
        month in which it pays out. A template leaves the check to the scenarios that extend it,
        which may drop the event. The errors are at the event, so the loader names its file."""
        found = [
            InitErrorDetails(
                type=PydanticCustomError(
                    "untimely", UNTIMELY[kind], {"event": e.type, "month": f"{e.at:%Y-%m}"} | said
                ),
                loc=("scenario", "events", i, "at"),
                input=e.at,
            )
            for i, e in enumerate([] if self.scenario.abstract else self.scenario.events)
            if (why := self._untimely(e))
            for kind, said in [why]
        ]
        refuse_all(self, found)
        return self

    @model_validator(mode="after")
    def _repayments_on_every_path(self) -> Plan:
        """A stream that `repays` a loan pays the same on every path, as the loan is one: no sale
        at `liquid_below` ends it (`property`, or `end_tagged` and a shared tag) or starts it
        (`after_sale_of`). An age is the same on every path. The error is at the sale, so the loader
        names its file."""
        tags = {a.id: set(a.tags) for a in self.assets if isinstance(a, PropertyAsset)}
        tags |= {e.property.id: set(e.property.tags) for e in self.bought}
        found = [
            InitErrorDetails(
                type=PydanticCustomError(
                    "per_path", PER_PATH, {"asset": e.asset, "name": s.name, "loan": s.repays}
                ),
                loc=("scenario", "events", i, "when"),
                input=e.asset,
            )
            for i, e in enumerate(self.scenario.events)
            if isinstance(e, SellEvent) and e.when is not None and e.when.liquid_below is not None
            for s in self.all_streams
            if s.repays
            and (
                e.asset in {s.after_sale_of, s.property}
                or (e.end_tagged and set(s.tags) & tags.get(e.asset, set()))
            )
        ]
        refuse_all(self, found)
        return self

    def _untimely(self, event: EventBase) -> tuple[str, dict[str, str]] | None:
        """Why the run cannot reach `event` (a key of `UNTIMELY`) with what the message names,
        None when it can."""
        at, start = event.at, self.assumptions.start
        if at is None:
            return None
        if at < start and not isinstance(event, STATE_EVENTS):
            return "start", {"start": f"{start:%Y-%m}"}
        policy = next(
            (a for a in self.assets if isinstance(a, PensionPolicy) and a.id == _funded(event)),
            None,
        )
        if policy is not None and at > policy.matures:
            return "matures", {"policy": policy.id, "matures": f"{policy.matures:%Y-%m}"}
        return None

    @model_validator(mode="after")
    def _sales_fit(self) -> Plan:
        """A sale takes the fields of the kind of its asset, and a gift is no taxable sale
        (`_sale_problems`). The errors are at the event, so the loader names its file."""
        holdings = self._ids(LotAsset)
        found = [
            InitErrorDetails(
                type=PydanticCustomError("sale", SALE[kind], {"asset": e.asset} | said),
                loc=("scenario", "events", i, key),
                input=getattr(e, key),
            )
            for i, e in enumerate(self.scenario.events)
            if isinstance(e, SellEvent)
            for key, kind, said in _sale_problems(e, holding=e.asset in holdings)
        ]
        refuse_all(self, found)
        return self

    def _first_pay(self, stream: Stream, since: date) -> date | None:
        """The first month from `since` in which `stream` pays by its `start`, `end` and
        `phases`, None when it never does: the phase of the scenario holds from one change to the
        next."""
        first = max(since, stream.start or since)
        months = [first, *(c.at for c in self.scenario.phases if c.at > first)]
        return next(
            (
                m
                for m in months
                if (stream.end is None or m < stream.end)
                and (stream.phases is None or self.scenario.phase_at(m) in stream.phases)
            ),
            None,
        )

    def _uses(self, event: EventBase) -> list[tuple[tuple[str | int, ...], str, date | None]]:
        """The assets that a dated event sells or repays, or that an added stream repays or lets:
        their key paths in the event, the ids and the month from which the event needs them, None
        for a stream that never pays."""
        match event:
            case SellEvent(at=date() as at):
                return [
                    (("asset",), event.asset, at),
                    *(
                        (("then", k, "repay"), a.repay, at)
                        for k, a in enumerate(event.then)
                        if isinstance(a, RepayAction)
                    ),
                ]
            case RepayEvent():
                return [(("loan",), event.loan, event.at)]
            case AddStreamEvent():
                return [
                    (("stream", key), name, self._first_pay(event.stream, event.at))
                    for key, name in _named_assets(event.stream)
                ]
        return []

    @model_validator(mode="after")
    def _purchases_fit(self) -> Plan:
        """The property and the loan of a purchase take ids that no other asset has, and no
        sale, repayment or stream (`repays`, `property`) names them before the purchase: a stream
        from the first month in which it pays. The errors are at the events, so the loader names
        their files."""
        events = self.scenario.events
        new = [
            (i, keys, name, e)
            for i, e in enumerate(events)
            if isinstance(e, BuyPropertyEvent)
            for keys, name in e.ids
        ]
        count = Counter([*(a.id for a in self.assets), *(name for _, _, name, _ in new)])
        owner = {name: e for _, _, name, e in new}
        on = ("scenario", "events")
        found = [
            _purchase_error("taken", (*on, i, *keys), f"buy_property of {e.at:%Y-%m}", name)
            for i, keys, name, e in new
            if count[name] > 1
        ]
        uses = [
            ((*on, i, *keys), f"{e.type} of {e.at:%Y-%m}", name, day)
            for i, e in enumerate(events)
            for keys, name, day in self._uses(e)
        ] + [
            (
                ("streams", k, key),
                f"the stream {s.name}",
                name,
                self._first_pay(s, self.assumptions.start),
            )
            for k, s in enumerate(self.streams)
            for key, name in _named_assets(s)
        ]
        found += [
            _purchase_error("early", loc, what, name, buy)
            for loc, what, name, day in uses
            if day and (buy := owner.get(name)) and day <= buy.at
        ]
        refuse_all(self, found)
        return self

    @model_validator(mode="after")
    def _let_known(self) -> Plan:
        """A property that a rent names (`Stream.property` of other income) is let: its AfA and
        the tax of its sale need the purchase, its cost and the AfA, and no default sets such a
        tax base in silence. A property of `assets.yaml` needs `bought_for` and `bought`, one of a
        `buy_property` has them from the event. The errors are at the fields, so the loader names
        their files."""
        rents = {
            s.property: s.name
            for s in self.all_streams
            if s.property and s.kind == StreamKind.OTHER_INCOME
        }
        held = [
            (("assets", i), x, ("bought_for", "bought", "building_share", "afa"))
            for i, x in enumerate(self.assets)
            if isinstance(x, PropertyAsset)
        ] + [
            (("scenario", "events", i, "property"), e.property, ("building_share", "afa"))
            for i, e in enumerate(self.scenario.events)
            if isinstance(e, BuyPropertyEvent)
        ]
        found = [
            InitErrorDetails(
                # `missing`: the problem names the field that the file lacks
                type=PydanticCustomError("missing", LET, {"id": x.id, "stream": rents[x.id]}),
                loc=(*at, name),
                input=None,
            )
            for at, x, needed in held
            if x.id in rents
            for name in needed
            if getattr(x, name) is None
        ]
        refuse_all(self, found)
        return self

    @model_validator(mode="after")
    def _fundings_fit(self) -> Plan:
        """A severance pays into a company pension, a `fund_policy` into a Basisrente. The
        errors are at the events, so the loader names their files."""
        basisrente = {a.id: a.basisrente for a in self.assets if isinstance(a, PensionPolicy)}
        found = [
            InitErrorDetails(
                type=PydanticCustomError("funding", FUNDING[kind], {"id": policy}),
                loc=("scenario", "events", i, *keys),
                input=policy,
            )
            for i, e in enumerate(self.scenario.events)
            for keys, kind, policy, wanted in _fundings(e)
            if basisrente.get(policy, wanted) != wanted
        ]
        refuse_all(self, found)
        return self

    @model_validator(mode="after")
    def _held_at_start(self) -> Plan:
        """A property of `assets.yaml` is held at the start: bought in its month or before, else
        the tax of its sale and its AfA would count months before the purchase. The error is at
        the field, so the loader names its file."""
        start = self.assumptions.start
        late = [
            InitErrorDetails(
                type=PydanticCustomError("late", LATE, {"id": x.id, "start": f"{start:%Y-%m}"}),
                loc=("assets", i, "bought"),
                input=x.bought,
            )
            for i, x in enumerate(self.assets)
            if isinstance(x, PropertyAsset) and x.bought and x.bought > start
        ]
        refuse_all(self, late)
        return self

    @model_validator(mode="after")
    def _streams_exist(self) -> Plan:
        """`set_stream` and `end_streams` of a concrete scenario name streams and tags of the plan
        or of an `add_stream` event: an unknown one would change nothing. A template leaves them
        to the scenarios that extend it. The error is at the event, so the loader names its
        file."""
        events = self.scenario.events
        streams = self.all_streams
        known = {"name": {s.name for s in streams}, "tag": {t for s in streams for t in s.tags}}
        unknown = [
            InitErrorDetails(
                type=PydanticCustomError(
                    "unknown_stream",
                    UNKNOWN_STREAM[kind],
                    {"event": e.type, "month": f"{e.at:%Y-%m}", "name": name},
                ),
                loc=("scenario", "events", i, *at),
                input=name,
            )
            for i, e in enumerate(events)
            for at, kind, name in _stream_refs(e)
            if name not in known[kind]
        ]
        if not self.scenario.abstract:
            refuse_all(self, unknown)
        return self

    @model_validator(mode="after")
    def _stream_updates_fit(self) -> Plan:
        """A `set_stream` sets the field of the amount of the rows of its name, which stay valid
        with it: the engine takes them as rows of `cashflows.yaml`. In a concrete scenario it
        changes a row (`SetStreamEvent.targets`): one whose rows all ended before it changed
        nothing in silence, and a template leaves it to the scenarios that may add a row. The
        errors are at the event, so the loader names its file."""
        ended = {
            (i, "at"): InitErrorDetails(
                type=PydanticCustomError(
                    "stream_ended",
                    STREAM_ENDED,
                    {"event": e.type, "month": f"{e.at:%Y-%m}", "name": e.name},
                ),
                loc=("scenario", "events", i, "at"),
                input=e.at,
            )
            for i, e in enumerate([] if self.scenario.abstract else self.scenario.events)
            if isinstance(e, SetStreamEvent)
            and (spans := [(s.start, s.end) for s in self.all_streams if s.name == e.name])
            and not e.targets(spans)
        }
        found = ended | {
            (i, key): InitErrorDetails(
                type=PydanticCustomError(
                    "stream_update",
                    STREAM_UPDATE,
                    {
                        "event": e.type,
                        "month": f"{e.at:%Y-%m}",
                        "key": key,
                        "name": e.name,
                        "problem": problem,
                    },
                ),
                loc=("scenario", "events", i, key),
                input=getattr(e, key),
            )
            for i, e in enumerate(self.scenario.events)
            if isinstance(e, SetStreamEvent)
            for s in self.all_streams
            if s.name == e.name
            for key, problem in _update_problems(e, s).items()
        }
        refuse_all(self, list(found.values()))
        return self

    @model_validator(mode="after")
    def _phases_known(self) -> Plan:
        """Every phase that a stream, a bAV policy or a phase change names is defined, and a
        concrete scenario has a phase at the start: a template may leave it to the scenarios that
        extend it. The errors are at the uses, so the loader names their files."""
        known, events = self.assumptions.phases, self.scenario.events
        uses = [
            *(
                (("streams", i, *keys), name)
                for i, s in enumerate(self.streams)
                for keys, name in _phases_of(s)
            ),
            *(
                (("scenario", "events", i, "stream", *keys), name)
                for i, e in enumerate(events)
                if isinstance(e, AddStreamEvent)
                for keys, name in _phases_of(e.stream)
            ),
            *(
                (("assets", i, "phases", j), name)
                for i, a in enumerate(self.assets)
                if isinstance(a, PensionPolicy)
                for j, name in enumerate(a.phases)
            ),
            *(
                (("scenario", "phases", n, "phase"), c.phase)
                for n, c in enumerate(self.scenario.phases)
            ),
        ]
        found = [unknown_phase(loc, name, known) for loc, name in uses if name not in known]
        start = self.assumptions.start
        if not self.scenario.abstract and self.scenario.phase_at(start) is None:
            found.append(  # `missing`: the problem names `phases` where a file lacks it
                InitErrorDetails(
                    type=PydanticCustomError(
                        "missing", NO_PHASE, {"start": f"{start:%Y-%m}", "known": ", ".join(known)}
                    ),
                    loc=("scenario", "phases"),
                    input=[c.phase for c in self.scenario.phases],
                )
            )
        refuse_all(self, found)
        return self
