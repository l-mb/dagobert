"""The phase changes and events of a scenario, and the `shift` of their months."""

from __future__ import annotations

import builtins
from datetime import date
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, model_validator

from dagobert.model.assets import AFA, ANNUITY, BUILDING_SHARE, PREPAYMENT_PENALTY, Loan
from dagobert.model.base import (
    Euros,
    Factor,
    Month,
    Percent,
    Strict,
    Unit,
    Years,
    exactly_one,
    unit,
)
from dagobert.model.months import add_months
from dagobert.model.streams import Stream
from dagobert.model.taxes import Land, transfer_tax_rate
from dagobert.money import format_eur

ID_HELP = "Address for `overrides.events` and `overrides.shift`. Items that share it move together"
# `overrides.shift`: the whole months by which each id moves, a fraction refused
Shift = dict[str, Annotated[int, unit(Unit.MONTHS)]]


class PhaseChange(Strict):
    at: Month = Field(alias="from")
    phase: str = Field(description="A phase of `assumptions.yaml`")
    id: str | None = Field(default=None, description=ID_HELP)

    model_config = ConfigDict(populate_by_name=True)


class EventBase(Strict):
    """The fields of every event. Only a sale on a condition (`SellEvent.when`) and an inheritance
    at a death have no month."""

    at: Month | None = Field(default=None, description="Month of the event")
    note: str = ""
    id: str | None = Field(default=None, description=ID_HELP)

    @property
    def detail(self) -> str:
        """Marker text; subclasses fall back to the asset or loan they touch."""
        return self.note


class DatedEvent(EventBase):
    """An event in a month: every event but a sale and an inheritance."""

    # frozen, so the narrower type is safe; pyright does not see the `frozen` of `model_config`
    at: Month = Field(description="Month of the event")  # pyright: ignore[reportIncompatibleVariableOverride]


class SaleTrigger(Strict):
    """Sell in each path once the age is reached or liquid wealth falls below the floor.

    `liquid_below` is in start-year euros and follows the path's CPI."""

    age: Years | None = Field(default=None, ge=0)
    liquid_below: Euros | None = None

    @model_validator(mode="after")
    def _any(self) -> SaleTrigger:
        if self.age is None and self.liquid_below is None:
            msg = "sale trigger needs age or liquid_below"
            raise ValueError(msg)
        return self


AmountOrAll = Euros | Literal["all"]


class RepayAction(Strict):
    repay: str
    amount: AmountOrAll = "all"


class InvestAction(Strict):
    invest: Literal["portfolio"] = Field(
        description="Put what is left of the proceeds into the portfolio, split by the "
        "allocation share; the cash buffer stays"
    )


class SellEvent(EventBase):
    """Sell a property, or a share of a gold or crypto asset, the oldest units first."""

    type: Literal["sell"]
    asset: str
    when: SaleTrigger | None = Field(
        default=None, description="Conditional sale per path instead of a fixed month"
    )
    share: Percent = Field(
        default=1.0, gt=0, le=1, description="Gold or crypto: the share of the holding to sell"
    )
    price: Euros | None = Field(
        default=None, ge=0, description="Property: default its current value, 0 for a gift"
    )
    price_stdev: Percent = Field(
        default=0.0,
        ge=0,
        description="Property: relative spread of the achieved price across paths, lognormal "
        "around the price",
    )
    costs: Percent = Field(
        default=0.0, ge=0, le=1, description="Selling costs as a share of the price"
    )
    taxable: bool = Field(default=False, description="Property: a private sale (§23 EStG)")
    end_tagged: bool = Field(
        default=True, description="Property: the sale ends the streams that share a tag with it"
    )
    then: list[RepayAction | InvestAction] = Field(default=[])

    @property
    def detail(self) -> str:
        return self.note or self.asset

    @staticmethod
    def foreign(*, holding: bool) -> tuple[str, ...]:
        """The fields that the sale of a property, or of gold or crypto (a `holding`), does not
        take."""
        return ("price", "price_stdev", "taxable", "end_tagged") if holding else ("share",)

    def misfits(self, *, holding: bool) -> list[str]:
        """The `foreign` fields off their defaults: by value, since an override that moves the
        event writes every field."""
        fields = type(self).model_fields
        return [f for f in self.foreign(holding=holding) if getattr(self, f) != fields[f].default]

    @model_validator(mode="after")
    def _at_or_when(self) -> SellEvent:
        if not exactly_one(self.at is not None, self.when is not None):
            msg = f"sell {self.asset}: needs exactly one of `at` and `when`"
            raise ValueError(msg)
        if self.when is not None and any(isinstance(a, RepayAction) for a in self.then):
            msg = f"sell {self.asset}: a conditional sale cannot repay loans"
            raise ValueError(msg)
        return self


class BuyEvent(DatedEvent):
    """Pay euros from cash into a gold or crypto asset, at the price of the month."""

    type: Literal["buy"]
    asset: str
    amount: Euros = Field(gt=0, description="Euros, nominal at the event date")

    @property
    def detail(self) -> str:
        return self.note or self.asset


class BoughtProperty(Strict):
    """The property of a `buy_property`: held from the purchase on like one of `assets.yaml`,
    worth the price then."""

    id: str = Field(description="The short name by which sales and streams name it")
    name: str = ""
    growth: str = Field(default="property", description="Return class")
    upkeep: Percent = Field(
        default=0.0,
        ge=0,
        description="Yearly upkeep as a share of the value. For a flat: what the Hausgeld does "
        "not cover, the inside of the flat",
    )
    tags: list[str] = Field(default=[], description="A sale ends the streams that share a tag")
    building_share: Percent | None = Field(default=None, ge=0, le=1, description=BUILDING_SHARE)
    afa: Percent | None = Field(default=None, ge=0, le=1, description=AFA)

    @property
    def label(self) -> str:
        return self.name or self.id


class NewLoan(Strict):
    """The loan of a `buy_property`: the fields of a loan in `assets.yaml`, the fixed rate as
    months from the purchase, so a shift of the purchase moves its end too."""

    id: str = Field(description="The short name by which repayments name it")
    name: str = ""
    balance: Euros = Field(lt=0, description="Negative amount borrowed at the purchase")
    rate: Percent
    annuity: Euros = Field(gt=0, description=ANNUITY)
    fixed_for: Annotated[int, unit(Unit.MONTHS)] | None = Field(
        default=None,
        ge=0,
        description="Months of the fixed rate from the purchase, 180 for 15 years. Empty: the "
        "rate and the prepayment penalty hold for the whole term",
    )
    prepayment_penalty: Percent = Field(
        default=0.0,
        ge=0,
        le=1,
        description=PREPAYMENT_PENALTY,
    )

    def taken(self, at: date) -> Loan:
        """The loan as of the purchase in the month `at`: the first annuity is due a month
        later."""
        return Loan(
            kind="loan",
            id=self.id,
            name=self.name,
            balance=self.balance,
            rate=self.rate,
            annuity=self.annuity,
            fixed_until=None if self.fixed_for is None else add_months(at, self.fixed_for),
            prepayment_penalty=self.prepayment_penalty,
        )


class BuyPropertyEvent(DatedEvent):
    """Buy a property from cash and liquid assets, with the Grunderwerbsteuer and the costs on
    top, the loan less."""

    type: Literal["buy_property"]
    property: BoughtProperty
    price: Euros = Field(gt=0, description="Euros, nominal at the event date")
    land: Land | None = Field(
        default=None,
        description="The Bundesland of the property: its rate of the Grunderwerbsteuer at the "
        "event date",
    )
    transfer_tax: Percent | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Grunderwerbsteuer as a share of the price, instead of the rate of `land`: 0 "
        "for a purchase from a spouse, parents or children (§3 Nr. 4, 6 GrEStG)",
    )
    costs: Percent = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Notary and land register (about 1.5%) and the buyer's share of a broker "
        "(up to 3.57%) as a share of the price",
    )
    loan: NewLoan | None = Field(default=None, description="A loan taken for the purchase")

    @builtins.property
    def detail(self) -> str:
        return self.note or self.property.label

    @builtins.property
    def transfer_rate(self) -> float:
        """The Grunderwerbsteuer as a share of the price."""
        if self.transfer_tax is not None:
            return self.transfer_tax
        if self.land is None:
            msg = f"buy_property {self.property.id}: needs `land`"
            raise ValueError(msg)
        return transfer_tax_rate(self.land, self.at)

    @builtins.property
    def ids(self) -> list[tuple[tuple[str, ...], str]]:
        """The new ids, of the property and of the loan, with their key paths."""
        loan = [(("loan", "id"), self.loan.id)] if self.loan else []
        return [(("property", "id"), self.property.id), *loan]

    @builtins.property
    def cost(self) -> float:
        """What the purchase costs with the Grunderwerbsteuer and the other costs, in euros."""
        return self.price * (1 + self.transfer_rate + self.costs)

    @model_validator(mode="after")
    def _fits(self) -> BuyPropertyEvent:
        if not exactly_one(self.land is not None, self.transfer_tax is not None):
            msg = f"buy_property {self.property.id}: needs exactly one of `land` and `transfer_tax`"
            raise ValueError(msg)
        cost = self.cost  # the Land has a rate in the month
        if self.loan is not None and -self.loan.balance > cost:
            msg = (
                f"buy_property {self.property.id}: the loan of {format_eur(-self.loan.balance)} is "
                f"more than the price with tax and costs, {format_eur(cost)}"
            )
            raise ValueError(msg)
        return self


class RepayEvent(DatedEvent):
    type: Literal["repay"]
    loan: str
    amount: AmountOrAll = "all"

    @property
    def detail(self) -> str:
        return self.note or self.loan


class PolicyFunding(Strict):
    policy: str = Field(description="Id of a `bav` asset")
    amount: Euros = Field(gt=0)


class SeveranceEvent(DatedEvent):
    type: Literal["severance"]
    gross: Euros = Field(description="Nominal at the event date")
    bav: PolicyFunding | None = Field(
        default=None,
        description="Part of the gross the employer pays tax-free into a policy "
        "(Vervielfältigung, §3 Nr. 63 S. 3 EStG)",
    )

    @model_validator(mode="after")
    def _bav_fits(self) -> SeveranceEvent:
        if self.bav is not None and self.bav.amount > self.gross:
            msg = (
                f"severance: bav amount {format_eur(self.bav.amount)} "
                f"exceeds gross {format_eur(self.gross)}"
            )
            raise ValueError(msg)
        return self


class FundPolicyEvent(DatedEvent):
    """Pay cash into a Basisrente: an Altersvorsorgeaufwand (§10 Abs. 1 Nr. 2 b EStG, capped in
    the settlement). A company pension takes none (`Plan`)."""

    type: Literal["fund_policy"]
    policy: str = Field(description="Id of a `bav` asset with `basisrente`")
    amount: Euros = Field(gt=0)

    @property
    def detail(self) -> str:
        return self.note or self.policy


class LumpSumEvent(DatedEvent):
    type: Literal["lump_sum"]
    amount: Euros = Field(description="Signed: below zero pays out")
    taxable: bool = False


class WriteOffEvent(DatedEvent):
    """An equity asset leaves the depot without proceeds and without tax, for example a
    share plan forfeited without payment."""

    type: Literal["write_off"]
    asset: str

    @property
    def detail(self) -> str:
        return self.note or self.asset


def _listed(value: object) -> object:
    """One name reads as a list of one."""
    return [value] if isinstance(value, str) else value


class Securities(Strict):
    """The securities of an estate or a gift: they join the one equity pool with the cost basis
    of the giver."""

    value: Euros = Field(
        ge=0,
        description="What they are worth, in euros of the start: the equity index carries it to "
        "the month. Update it after a roll forward",
    )
    cost_basis: Euros = Field(
        ge=0,
        description="What the giver paid for them, nominal: the heir takes it over (§20 Abs. 4 "
        "S. 6 EStG), so their gain is taxed at a sale",
    )


class AcquisitionEvent(EventBase):
    """Cash and securities from relatives of `person.relatives`: the Erbschaftsteuer by the
    relation of the giver, no income tax and no health insurance."""

    givers: Annotated[list[str], BeforeValidator(_listed)] = Field(
        alias="from", min_length=1, description="The relatives who give, by their short names"
    )
    cash: Euros = Field(
        default=0.0,
        ge=0,
        description="Euros, nominal at the event, like a lump sum: the net proceeds of a property "
        "too",
    )
    equity: Securities | None = Field(default=None, description="Securities into the depot")

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _brings(self) -> AcquisitionEvent:
        if not self.cash and self.equity is None:
            msg = "an inheritance or a gift needs cash or equity"
            raise ValueError(msg)
        return self


class InheritanceEvent(AcquisitionEvent):
    """An estate. Without a month it falls at the death of its givers, drawn per path from the
    life table; with two givers at the later death (a Berliner Testament)."""

    type: Literal["inheritance"]
    at: Month | None = Field(
        default=None,
        description="Month of the inheritance. Empty: the month of the death of the relative, "
        "drawn per path from the life table, of two relatives the later one",
    )


class GiftEvent(AcquisitionEvent):
    """A gift of one relative in a month. When an inheritance draws the death of the relative
    before it, the gift joins that estate."""

    type: Literal["gift"]
    # required, as on a `DatedEvent`
    at: Month = Field(description="Month of the event")  # pyright: ignore[reportIncompatibleVariableOverride]

    @model_validator(mode="after")
    def _one_giver(self) -> GiftEvent:
        if len(self.givers) > 1:
            msg = "gift: from names one relative, a gift of two is a gift of each"
            raise ValueError(msg)
        return self


Acquired = InheritanceEvent | GiftEvent  # what an heir or a donee receives


class EndStreamsEvent(DatedEvent):
    type: Literal["end_streams"]
    tags: list[str] = Field(default=[])
    names: list[str] = Field(default=[])

    @model_validator(mode="after")
    def _ends_some(self) -> EndStreamsEvent:
        if not self.names and not self.tags:
            msg = "end_streams: needs names or tags"
            raise ValueError(msg)
        return self


class SetStreamEvent(DatedEvent):
    type: Literal["set_stream"]
    name: str
    amount: Euros | None = None
    gross: Euros | None = None
    premium: Euros | None = Field(
        default=None,
        le=0,
        description="BU policy: the new monthly premium, below 0, such as your own once an "
        "employer no longer pays it",
    )
    factor: Factor | None = Field(
        default=None, description="Multiplier in every phase, instead of the one per phase"
    )

    @model_validator(mode="after")
    def _sets_some(self) -> SetStreamEvent:
        if all(v is None for v in (self.amount, self.gross, self.premium, self.factor)):
            msg = f"set_stream {self.name}: needs amount, gross, premium or factor"
            raise ValueError(msg)
        return self

    @property
    def update(self) -> dict[str, float | None]:
        """The fields that it sets on a row: a fixed gross replaces a pension from points."""
        new = {
            k: v
            for k, v in (("amount", self.amount), ("gross", self.gross), ("premium", self.premium))
            if v is not None
        }
        return new | ({"points": None} if self.gross is not None else {})

    def applied(self, stream: Stream) -> Stream:
        """`stream` with the new amount or gross, validated as a row of `cashflows.yaml`."""
        return Stream.model_validate(stream.model_dump() | self.update)

    def targets(self, spans: list[tuple[date | None, date | None]]) -> list[int]:
        """The rows of its name that it changes, by their `start` and `end`: those that run in its
        month, else the next one that starts. A later row keeps its values, a change after it."""
        at = self.at
        running = [
            k
            for k, (start, end) in enumerate(spans)
            if (start is None or start <= at) and (end is None or at < end)
        ]
        later = sorted(
            (start, k)
            for k, (start, end) in enumerate(spans)
            if start is not None and start > at and (end is None or start < end)
        )
        return running or [k for _, k in later[:1]]


class AddStreamEvent(DatedEvent):
    type: Literal["add_stream"]
    stream: Stream


Event = Annotated[
    SellEvent
    | RepayEvent
    | SeveranceEvent
    | FundPolicyEvent
    | LumpSumEvent
    | WriteOffEvent
    | EndStreamsEvent
    | SetStreamEvent
    | AddStreamEvent
    | BuyEvent
    | BuyPropertyEvent
    | InheritanceEvent
    | GiftEvent,
    Field(discriminator="type"),
]

# Events that only change streams. Dated before the start they apply in the first month:
# moving `start` past a premium change must not bring the old premium back.
STATE_EVENTS = (SetStreamEvent, AddStreamEvent, EndStreamsEvent)
