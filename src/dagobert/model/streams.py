"""`cashflows.yaml`: the streams of income, expenses and savings."""

from __future__ import annotations

import builtins
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from dagobert.model.assumptions import CPI_INDEX
from dagobert.model.base import (
    Euros,
    Factor,
    Month,
    Number,
    Percent,
    Strict,
    Titled,
    Unit,
    Years,
    exactly_one,
    unit,
)


class StreamKind(Titled):
    EXPENSE = "expense"
    SALARY = "salary"
    ALG1 = "alg1"
    PENSION = "pension"
    OTHER_INCOME = "other_income"
    RV_VOLUNTARY = "rv_voluntary"  # voluntary pension contribution, counts as Versicherungszeit
    SAVINGS = "savings"  # a savings plan: from cash into an asset, paused while cash is short
    SELF_EMPLOYED = "self_employed"  # the profit of a business before tax and own SV
    BU = "bu"  # a Berufsunfähigkeitsversicherung: a premium while able to work, then a benefit

    @classmethod
    def titles(cls) -> dict[str, str]:
        return {
            "expense": "Expense",
            "salary": "Salary",
            "alg1": "Unemployment benefit (ALG1)",
            "pension": "Pension",
            "other_income": "Other income",
            "rv_voluntary": "Voluntary pension contribution",
            "savings": "Savings plan",
            "self_employed": "Self-employed profit",
            "bu": "Disability insurance (BU)",
        }


SAVINGS_TARGETS = ("equity", "fixed_income", "gold", "crypto")  # the kinds that `into` names


class Deduction(Titled):
    """What an expense is for the income tax: a Sonderausgabe or the base of a credit."""

    DONATION = "donation"  # §10b EStG
    CHILDCARE = "childcare"  # §10 Abs. 1 Nr. 5 EStG
    HOUSEHOLD = "household"  # §35a Abs. 2 EStG
    CRAFTSMAN = "craftsman"  # §35a Abs. 3 EStG

    @classmethod
    def titles(cls) -> dict[str, str]:
        return {
            "donation": "donation",
            "childcare": "childcare",
            "household": "household services (§35a)",
            "craftsman": "craftsman's labour (§35a)",
        }


# the kinds whose amount is nominal without an `index`: a savings plan as a broker runs it, a BU
# policy as its contract guarantees it
NOMINAL = frozenset({StreamKind.SAVINGS, StreamKind.BU})


def stream_index(row: dict[str, Any]) -> str | None:
    """The `index` of a raw stream row as the model reads it: absent is `cpi`, for a savings plan
    and a BU policy null."""
    return row.get("index", None if row.get("kind") in NOMINAL else CPI_INDEX)


# the fields of a stream that only some kinds take, by kind: a category is no field of a plan
TAKES: dict[StreamKind, frozenset[str]] = {
    StreamKind.EXPENSE: frozenset({"cat", "amount", "health", "deduct", "deductible", "property"}),
    StreamKind.SALARY: frozenset({"cat", "gross", "of", "share", "part"}),
    StreamKind.ALG1: frozenset({"cat"}),
    StreamKind.PENSION: frozenset({"cat", "gross", "points", "point_value"}),
    StreamKind.OTHER_INCOME: frozenset({"cat", "amount", "taxable", "repays", "property"}),
    StreamKind.RV_VOLUNTARY: frozenset({"cat", "amount"}),
    StreamKind.SAVINGS: frozenset({"amount", "into"}),
    StreamKind.SELF_EMPLOYED: frozenset({"cat", "amount", "hebesatz"}),
    StreamKind.BU: frozenset({"cat", "amount", "premium", "until_age"}),
}
KIND_FIELDS = frozenset().union(*TAKES.values())


class Stream(Strict):
    name: str
    cat: str = ""
    kind: StreamKind = StreamKind.EXPENSE
    amount: Euros | None = None
    gross: Euros | None = None
    of: str | None = Field(
        default=None,
        description="Salary: the base salary stream that this payment follows, for a bonus: a "
        "salary stream with `of` and `share`",
    )
    share: Percent | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Salary: one payment is this share of the base stream's gross of `every` "
        "months (10% with every 12: a tenth of the yearly base salary), times the payout ratio "
        "of the stream's index",
    )
    points: Number | None = Field(default=None, description="Pension: Rentenpunkte reached so far")
    point_value: Number | None = Field(
        default=None, description="Pension: monthly euros per point in start-year euros"
    )
    part: Percent = Field(default=1.0, ge=0, le=1, description="Salary: part time")
    every: Annotated[int, unit(Unit.MONTHS)] = Field(
        default=1, ge=1, description="Period in months"
    )
    phases: list[str] | None = Field(
        default=None, description="The phases in which the stream pays, none for every phase"
    )
    factor: dict[str, Factor] = Field(default={}, description="Multiplier per phase")
    tags: list[str] = Field(default=[])
    start: Month | None = Field(
        default=None,
        description="The first month in which it pays. Empty: from the start of the run, of an "
        "added stream from its event",
    )
    end: Month | None = Field(
        default=None,
        description="The first month in which it no longer pays: 2031-01 pays through December "
        "2030. Empty: to the end",
    )
    index: str | None = Field(
        default=CPI_INDEX,
        description="Growth index the amount follows: 'cpi', a name from assumptions.indices, "
        "or null for a nominal amount. Default 'cpi', for a savings plan and a BU policy null",
    )
    into: str | None = Field(
        default=None,
        description="Savings plan: the id of the equity, fixed-income, gold or crypto asset that "
        "it buys. Default the equity of the depot",
    )
    health: Literal["kv", "pv"] | None = Field(
        default=None,
        description="Part of the PKV premium: Kranken- or Pflegepflichtversicherung. "
        "Subsidies cap the two apart.",
    )
    deduct: Deduction | None = Field(
        default=None,
        description="Expense: what it is for the income tax. A donation (up to 20% of the income) "
        "and childcare (80% of the costs of a child under 14, at most 4.800 € a year per child) "
        "lower the taxable income; household services and a craftsman's labour lower the tax by "
        "20% of the costs, at most 4.000 € and 1.200 € a year (§35a EStG). The cash flow stays an "
        "expense",
    )
    deductible: Percent | None = Field(
        default=None,
        ge=0,
        le=1,
        description="The share that counts for the tax. Of a `health` premium the share that is "
        "Basisabsicherung and a Sonderausgabe, from the insurer's certificate: default all of a "
        "`pv` part, `pkv_basis_share` of the tax year for a `kv` part. Of a `deduct` expense the "
        "share that counts, such as the labour part of a bill or the donations among the gifts: "
        "default all of it",
    )
    repays: str | None = Field(
        default=None, description="Loan id that receives this income directly, bypassing cash"
    )
    after_sale_of: str | None = Field(
        default=None, description="Property id whose sale starts this stream, per path"
    )
    hebesatz: Percent | None = Field(
        default=None,
        ge=2,
        description="Self-employed: the Gewerbesteuer-Hebesatz of the municipality of a trade "
        "business, at least 200% (§16 Abs. 4 GewStG). Empty: a Freiberufler, no Gewerbesteuer",
    )
    taxable: bool = Field(
        default=True,
        description="Other income: false for a tax-free benefit outside the Progressionsvorbehalt,"
        " for example the Gründungszuschuss (§3 Nr. 2 EStG)",
    )
    # the field shadows the builtin in the class body, so the methods take `builtins.property`
    property: str | None = Field(
        default=None,
        description="The id of a let property. Other income: the rent of this property, taxed "
        "after the AfA, the interest of its loans, its upkeep and the expenses that name it. "
        "Expense: a cost of letting it, which the rent deducts",
    )

    premium: Euros = Field(
        default=0.0,
        le=0,
        description="BU policy: the monthly premium, below 0 like an expense. It is paid while you "
        "can work and up to `until_age`, and waived from the month after the onset of a "
        "disability. 0 while an employer pays it",
    )
    until_age: Years = Field(
        default=67.0,
        gt=0,
        description="BU policy: the age at which the contract ends, the premium and the benefit "
        "with it",
    )

    @builtins.property
    def managed(self) -> bool:
        """An expense that `scale` and the age curve act on: not the health premium, not a cost
        of a let property (no spending, it lowers the tax of the rent)."""
        return self.kind == StreamKind.EXPENSE and not self.health and self.property is None

    @builtins.property
    def amount_key(self) -> str | None:
        """The field of its amount, which a `set_stream` sets: `gross` of a salary or a pension,
        none of ALG1 or a derived salary (`of`), else `amount`."""
        if self.kind == StreamKind.ALG1 or self.of is not None:
            return None
        return "gross" if self.kind in (StreamKind.SALARY, StreamKind.PENSION) else "amount"

    @model_validator(mode="before")
    @classmethod
    def _nominal_plan(cls, data: Any) -> Any:  # noqa: ANN401 the raw input of a model
        """A savings plan runs nominal, as a broker runs it, and a BU policy as its contract
        guarantees it, unless it names an index."""
        if isinstance(data, dict) and data.get("kind") in NOMINAL:
            return {"index": None} | data
        return data

    @model_validator(mode="after")
    def _fits_its_kind(self) -> Stream:
        """A field of another kind (`TAKES`) stays at its default: the engine would ignore it, or
        read it where it means something else (`health` of an income as a premium)."""
        fields = type(self).model_fields
        if odd := [
            f for f in KIND_FIELDS - TAKES[self.kind] if getattr(self, f) != fields[f].default
        ]:
            msg = f"{self.name}: a stream of kind {self.kind} takes no {', '.join(sorted(odd))}"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _together(self) -> Stream:
        """The fields that need each other within a kind."""
        if self.deductible is not None and self.health is None and self.deduct is None:
            msg = f"{self.name}: `deductible` belongs to a `health` premium or a `deduct` expense"
            raise ValueError(msg)
        # a deduction is an expense of the person: no premium of the health insurance, no cost of
        # a let property, which the rent deducts and §35a Abs. 5 S. 1 EStG excludes
        if self.deduct is not None and (self.health or self.property is not None):
            msg = f"{self.name}: deduct takes no health premium and no cost of a let property"
            raise ValueError(msg)
        if self.repays is not None and self.index is not None:
            msg = f"{self.name}: repays needs index null"
            raise ValueError(msg)
        if self.property is not None and self.health is not None:
            msg = f"{self.name}: a cost of a let property is no health premium"
            raise ValueError(msg)
        if self.property is not None and not self.taxable:
            msg = f"{self.name}: the rent of a property is taxable: remove taxable: false"
            raise ValueError(msg)
        if exactly_one(self.of is not None, self.share is not None):
            msg = f"{self.name}: of and share go together"
            raise ValueError(msg)
        if self.of is not None and self.gross is not None:
            msg = f"{self.name}: of takes no gross"
            raise ValueError(msg)
        phased = self.phases is not None or self.factor or self.every > 1
        if self.kind == StreamKind.BU and phased:
            msg = (
                f"{self.name}: a BU policy runs by its contract, not by phase: it takes no phases, "
                "factor or every (a yearly premium: its twelfth a month)"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _amount_or_gross(self) -> Stream:
        """ALG1 and a derived stream take their amount elsewhere."""
        if self.kind == StreamKind.ALG1 or self.of is not None:
            return self
        match self.kind:
            case StreamKind.PENSION:
                points = self.points is not None and self.point_value is not None
                problem = (
                    "pension needs either gross or points with point_value"
                    if not exactly_one(self.gross is not None, points)
                    else None
                )
            case StreamKind.SALARY:
                problem = "salary needs gross" if self.gross is None else None
            case _:
                problem = self._amount_problem()
        if problem:
            msg = f"{self.name}: {problem}"
            raise ValueError(msg)
        return self

    def _amount_problem(self) -> str | None:
        if self.amount is None:
            return "needs amount"
        if self.kind == StreamKind.RV_VOLUNTARY and self.amount >= 0:
            return "rv_voluntary needs a negative amount"
        if self.kind in (StreamKind.EXPENSE, StreamKind.SAVINGS) and self.amount > 0:
            return f"{self.kind} needs a non-positive amount"
        if self.kind == StreamKind.BU and self.amount < 0:
            return "bu needs a benefit of 0 or more"
        return None


class Cashflows(Strict):
    streams: list[Stream]
