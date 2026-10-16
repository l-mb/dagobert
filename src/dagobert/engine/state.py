"""The state of a run beside the arrays of the engine: one dataclass per asset, stream or
claim, the accumulators of a year and of a month, the month being simulated."""

from __future__ import annotations

from collections import deque
from dataclasses import MISSING, dataclass, field, fields
from datetime import date
from typing import Any

import numpy as np
from numpy.typing import NDArray

from dagobert.model.assets import AvDepot, Loan, PensionPolicy, PropertyAsset
from dagobert.model.assumptions import Assumptions
from dagobert.model.events import Acquired, GiftEvent
from dagobert.model.streams import Stream
from dagobert.result import BoolArray, FloatArray, IntArray
from dagobert.tax import YearIncome, YearSettlement

TEN_YEARS = 120  # months in which §14 ErbStG adds the acquisitions from one giver


@dataclass
class LoanState:
    spec: Loan
    balance: float
    since: int = 0  # the month index of the first annuity
    finances: str | None = None  # the property whose rent deducts the interest
    interest: float = 0.0  # nominal, of the month: `Core._service_loans` writes it


@dataclass
class PropertyState:
    spec: PropertyAsset
    value: FloatArray
    sold: NDArray[np.bool_]
    afa_taken: FloatArray  # nominal, lowers the basis of a sale (§23 Abs. 3 S. 4 EStG)
    bought: int | None = None  # the month index of the purchase, below 0 before the start

    @property
    def held(self) -> FloatArray:
        return self.value * ~self.sold

    @property
    def afa_base(self) -> float:
        """What the building cost, nominal: the purchase with its costs times the building share
        (§7 Abs. 4 EStG; the land is not depreciated)."""
        return (self.spec.bought_for or 0.0) * (self.spec.building_share or 0.0)

    @property
    def afa_month(self) -> FloatArray:
        """The AfA of a let month: a twelfth of the yearly rate, up to the base left."""
        year = (self.spec.afa or 0.0) * self.afa_base
        return np.minimum(year / 12, self.afa_base - self.afa_taken)


@dataclass
class PolicyState:
    """A pension policy. Once `done`, an annuity's `value` holds the capital less the payments."""

    spec: PensionPolicy
    value: FloatArray
    paid: FloatArray  # the guarantee base, per path: a conversion follows the salary
    annuity: FloatArray | None = None  # nominal monthly pension once converted
    # the taxable share of the annuity: of a Basisrente that of the year it starts (§22 Nr. 1 S. 3
    # a aa EStG), the same euros every year as the annuity is fixed; of a company pension all
    taxable: float = 1.0
    done: bool = False
    # a lump sum counts its 120th as a monthly Versorgungsbezug from the month after the payout
    # (§229 Abs. 1 S. 3 SGB V): nominal, and the month index of its first month
    tail: FloatArray | None = None
    tail_from: int = 0


@dataclass(eq=False)  # identity, so a StreamState keys the salaries of `MonthPay`
class StreamState:
    spec: Stream
    end: date | None
    mask: FloatArray  # per path 0/1, conditional sales switch streams off or on
    # of a BU policy the paths with an onset while it was in force: no later end stops the claim
    claim: BoolArray
    factor_override: float | None = None  # a `set_stream` factor holds in every phase

    def active(self, month: date, phase: str) -> bool:
        return (
            (self.spec.start is None or month >= self.spec.start)
            and (self.end is None or month < self.end)
            and (self.spec.phases is None or phase in self.spec.phases)
        )

    def factor(self, phase: str) -> float:
        return (
            self.factor_override
            if self.factor_override is not None
            else self.spec.factor.get(phase, 1.0)
        )

    def earned_scale(self, phase: str, a: Assumptions) -> float:
        """What an earned stream pays of its amount in `phase`: its factor times `scale.salary`."""
        return self.factor(phase) * a.scale.salary.get(phase, 1.0)

    @property
    def amount(self) -> float:
        return self.spec.amount or 0.0

    @property
    def gross(self) -> float:
        return self.spec.gross or 0.0


@dataclass
class Acquisition:
    """An inheritance or a gift: per path its month index (the length of the run: none in it),
    of an inheritance without a month the later death of its givers, and the index in `from` of
    the giver, of two the one who died last; the paths that received it; the dated gifts that
    join an estate, each with the paths on which its giver died before its month."""

    event: Acquired
    month: NDArray[np.intp]
    giver: NDArray[np.intp]
    done: BoolArray
    joined: list[tuple[GiftEvent, BoolArray]] = field(default_factory=list)


@dataclass
class Received:
    """What one relative gave, for §14 ErbStG: per acquisition and path its month index, nominal
    value and the nominal tax paid on it, a row for each gift before the start and for each event
    that names the relative (`rows`, by the `id` of the event), 0 on a path without it."""

    month: NDArray[np.intp]  # (acquisitions, paths)
    value: FloatArray
    tax: FloatArray
    rows: dict[int, int]

    def prior(self, i: int) -> tuple[FloatArray, FloatArray]:
        """The values and the tax of the acquisitions within ten years up to month `i`."""
        recent = self.month >= i - TEN_YEARS
        return np.where(recent, self.value, 0.0), np.where(recent, self.tax, 0.0)

    def record(
        self, event: object, paths: BoolArray, i: int, value: FloatArray, tax: FloatArray
    ) -> None:
        """The acquisition of `event` in month `i` on `paths`."""
        row = self.rows[id(event)]
        self.month[row, paths], self.value[row, paths] = i, value[paths]
        self.tax[row, paths] = tax[paths]


@dataclass
class PensionState:
    """Claim bookkeeping: points, Versicherungszeit, the months of Pflichtbeiträge, the old-age
    claim, the year of the first pension month and the Rentenfreibetrag per path, an EM-Rente."""

    points: FloatArray
    insured_months: int
    # the last months by whether each was one of Pflichtbeiträge (§43 Abs. 1 S. 1 Nr. 2 SGB VI)
    compulsory: deque[bool]
    # per path the year of the first pension month (§22 Nr. 1 S. 3 a aa EStG), 0 before, and the
    # nominal Rentenfreibetrag after the first full pension year, NaN before
    start_year: IntArray
    freibetrag: FloatArray
    # per path an EM-Rente: whether it pays, its points frozen at the onset with the
    # Zurechnungszeit (§75 Abs. 2 S. 1 SGB VI) and its Zugangsfaktor (§77 Abs. 2 S. 1 Nr. 3)
    em: BoolArray
    em_points: FloatArray
    em_factor: FloatArray
    counts_now: bool = False  # the month being simulated is a Versicherungsmonat
    compulsory_now: bool = False  # and one of Pflichtbeiträge
    # the old-age claim, the same on every path without an EM-Rente: its month and factor
    claimed: date | None = None
    regular: float = 1.0
    wanted: date | None = None

    @classmethod
    def new(cls, paths: int, insured_months: int, compulsory: int, window: int) -> PensionState:
        """`compulsory` months of Pflichtbeiträge right before the start, of the last `window`."""
        return cls(
            np.zeros(paths),
            insured_months,
            deque([True] * min(compulsory, window), maxlen=window),
            np.zeros(paths, dtype=np.int_),
            np.full(paths, np.nan),
            np.zeros(paths, dtype=bool),
            np.zeros(paths),
            np.ones(paths),
        )


@dataclass
class SickPay:
    """The Krankengeld of a path, fixed in its first month: nominal per month before the member's
    shares, and those shares of RV, ALV and PV; 0 without one."""

    gross: FloatArray
    rv: FloatArray
    alv: FloatArray
    pv: FloatArray
    employed: BoolArray  # from a salary: a compulsory member, else from a business

    @classmethod
    def new(cls, paths: int) -> SickPay:
        zero = np.zeros(paths)
        return cls(zero, zero.copy(), zero.copy(), zero.copy(), np.zeros(paths, dtype=bool))


@dataclass
class AvState:
    """An Altersvorsorgedepot. `months_left` of its Auszahlplan, None before the payout."""

    spec: AvDepot
    value: FloatArray
    months_left: int | None = None


@dataclass
class Alg1State:
    """The claim to ALG1, the same on every path (`engine.alg1`), in days of the claim: a month
    of 30 (§339 SGB III). The fields from `row` on hold the month of the run."""

    start: int | None = None  # the month in which it arose, the first with an ALG1 row
    days: float = 0.0  # left
    resting: float = 0.0  # of a Sperrzeit still to run (§159)
    rested: set[StreamState] = field(default_factory=set)  # the rows whose Sperrzeit began
    fresh: bool = False  # the stretch began within the four years of §161 Abs. 2
    course: int = 0  # months of the course that runs, for §148 Abs. 3
    extended: bool = False  # by §148 Abs. 3, once
    ended: bool = False  # its marker fell: used up or expired
    monthly: FloatArray | None = None  # nominal, fixed at entry like the Bewilligungsbescheid
    row: StreamState | None = None  # the ALG1 row that books the month, none without one
    share: float = 0.0  # of the month that ALG1 pays
    status: bool = False  # it pays or rests in a Sperrzeit: the KVdA (§5 Abs. 1 Nr. 2 SGB V)


@dataclass
class Trade:
    """A trade business in a year: the Hebesatz of its row, the profit so far in start-year
    euros."""

    hebesatz: float
    profit: FloatArray


@dataclass
class YearAcc:
    """Per-path accumulators for the December settlement, rebuilt every January. Money is in
    start-year euros, the unit of the law, except `equity_jan`, `bought` and `weighted`: nominal
    at the January price."""

    equity_jan: FloatArray
    index_jan: FloatArray  # equity index before the first return of the year
    pauschbetrag_left: FloatArray
    salary_gross: FloatArray
    severance: FloatArray
    lohnersatz: FloatArray  # ALG1 and the gross Krankengeld, under the Progressionsvorbehalt
    pension_gross: FloatArray
    other_taxable: FloatArray
    rent: FloatArray  # the net rent of the let properties, part of `other_taxable`
    basisrente: FloatArray  # the taxable part of the Basisrente annuities, a pension's
    rv_paid: FloatArray
    rv_employer: FloatArray
    health_deductible: FloatArray
    withheld: FloatArray
    severance_withheld: FloatArray  # the part of `withheld` that a severance paid
    church_withheld: FloatArray  # the church tax in `withheld`, a Sonderausgabe of the year
    capital_income: FloatArray
    capital_tax_paid: FloatArray
    interest: FloatArray  # on cash and the fixed-income bucket, net of losing months
    # 1 once a month of the year opens the Altersvorsorgedepot: compulsory GRV, or a business
    compulsory: FloatArray
    sv_months: FloatArray  # months with a salary, for the yearly BBG of a one-off (§23a SGB IV)
    rv_used: FloatArray  # contributory bases of RV and KV so far
    kv_used: FloatArray
    av_deduction: FloatArray  # Sonderausgabe of the Altersvorsorgedepots
    av_zulage: FloatArray
    private_sales: FloatArray  # net result of the private sales (§23 EStG), losses offset
    # what the freiwillige KV of the next year takes: the capital income after Teilfreistellung
    # and loss offset, before the Pauschbetrag, earned in the months of the run (sales, interest)
    # or for the whole year (the Vorabpauschale), and the one-offs (a taxable lump sum, the part
    # of an Altersvorsorgedepot paid at once)
    kv_capital: FloatArray
    kv_vorab: FloatArray
    kv_oneoff: FloatArray
    # equity bought this year in January euros, and weighted by the twelfths that its
    # Vorabpauschale carries (§18 Abs. 2 InvStG)
    bought: FloatArray
    weighted: FloatArray
    # by the name of its stream: a raise is a row of the same name, one Freibetrag per business
    trade: dict[str, Trade] = field(default_factory=dict)
    # what the expenses with `deduct` paid, by its kind, the share that counts
    deduct: dict[str, FloatArray] = field(default_factory=dict)

    @classmethod
    def new(cls, equity_jan: FloatArray, index_jan: FloatArray, pauschbetrag: float) -> YearAcc:
        zeros: dict[str, Any] = {
            f.name: np.zeros_like(equity_jan) for f in fields(cls) if f.default_factory is MISSING
        }
        return cls(
            **{
                **zeros,
                "equity_jan": equity_jan.copy(),
                "index_jan": index_jan,
                "pauschbetrag_left": np.full_like(equity_jan, pauschbetrag),
            }
        )


@dataclass
class Assessed:
    """A settled year that a loss of one of the two years after it amends (§10d Abs. 1 EStG): its
    income as settled, with the losses carried back into it, its settlement and its price level;
    of its `loss_back` the part of the last loss, which a waiver takes out again."""

    income: YearIncome
    settlement: YearSettlement
    level: FloatArray
    pending: FloatArray | float = 0.0


@dataclass
class MonthFlows:
    """What the month reports, nominal: gross income, the taxes and SV on income, the capital
    gains tax and the expenses, below zero; and what a lump sum of a policy or of an
    Altersvorsorgedepot paid into the cash (`oneoff`), which VPW leaves to the wealth."""

    income: FloatArray
    taxes: FloatArray
    capital_taxes: FloatArray
    expenses: FloatArray
    oneoff: FloatArray

    @classmethod
    def new(cls, paths: int) -> MonthFlows:
        return cls(*(np.zeros(paths) for _ in fields(cls)))


@dataclass
class MonthPay:
    """What the salaries and the pensions of a month pay before their SV and tax."""

    salary_real: FloatArray  # the gross of the salaries
    recurring_real: FloatArray  # of it the monthly salaries: the regular gross
    rente: FloatArray  # the statutory pensions, nominal
    # the monthly salaries that pay, by stream: a salary conversion takes from them
    salaries_real: dict[StreamState, FloatArray] = field(default_factory=dict)

    @classmethod
    def new(cls, paths: int) -> MonthPay:
        return cls(np.zeros(paths), np.zeros(paths), np.zeros(paths))


@dataclass(frozen=True)
class MonthState:
    """The month being simulated, with the first month of the stretch of its phase (at the
    earliest the start): the growth of its pay steps from there (`Core._earned`)."""

    i: int
    month: date
    phase: str
    since: date
