"""Engine output shared by report and CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from dagobert.i18n import N_, _

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
IntArray = NDArray[np.int_]


# Balance sheet classes, in stacking order. Deposits count as fixed income: they roll into it
# with an allocation, else into cash.
BALANCE_CLASSES = (
    "cash",
    "fixed_income",
    "equity",
    "gold",
    "crypto",
    "property",
    "policies",
    "loans",
    "latent_tax",
)
LIQUID = ("cash", "fixed_income", "equity", "gold", "crypto", "latent_tax")  # liquid net worth
# The ages of the measures of a run: the chance to have run out by `BROKE_AGE` (the summary, the
# goal seek, the sensitivity, the failure anatomy) and the median net worth at `TOTAL_AGES`, the
# last of them `BROKE_AGE`. A run that does not reach one takes its first or its last month
# (`RunResult.age_index`), and the words name that age (`RunResult.age_at`).
MEDIAN_AGE, BROKE_AGE = 67, 90
TOTAL_AGES = (MEDIAN_AGE, BROKE_AGE)
# Percentiles of `total` that bound the paths behind `RunResult.balance`.
MEDIAN_BAND = (45, 55)
TWIN = N_("{scenario} (as saved)")  # the name of the explorer's run of a scenario without sliders


# the unit of money by `nominal` and `yearly`: one message each, as German puts `pro Jahr` after
# the `€` (`€ pro Jahr, Kaufkraft 2026-10`)
UNITS = {
    (False, False): N_("€ of {month}"),
    (True, False): N_("nominal €"),
    (False, True): N_("€ of {month} per year"),
    (True, True): N_("nominal € per year"),
}


def age_index(ages: FloatArray, age: float) -> int:
    """The month of a run with `ages` that a measure at `age` takes: the first at `age`, else the
    first or the last month."""
    return min(int(np.searchsorted(ages, age)), len(ages) - 1)


def age_at(ages: FloatArray, age: float) -> int:
    """The whole age of the month that a measure at `age` takes (`age_index`): `age`, or the
    first or the last age of a run that does not reach it."""
    return round(float(ages[age_index(ages, age)]))


def unit(start: date, *, nominal: bool = False, yearly: bool = False) -> str:
    """The unit of money in charts and tables, in the language of the session: euros of the
    first simulated month, or nominal; `yearly` an amount per year."""
    return _(UNITS[nominal, yearly]).format(month=f"{start:%Y-%m}")


# The ledger names a flow `(side, group, item)`. The sides stay inside the code; the groups and
# items are English data, its words marked here (`WORDS`), which the pages say in the language of
# the session (`budget.said`), a label or a category as written.
SOURCE, TAX, SPENDING = "source", "tax", "spending"
# One-offs inside the engine totals: severance, lump sum, policy payout, the cash of an
# inheritance or a gift in `income`, the tax on them (`ONEOFF_TAX`, with the Grunderwerbsteuer of
# a purchase and the Erbschaftsteuer) in `taxes`, the costs of a purchase (`PURCHASE_COSTS`) in
# `expenses`.
ONEOFF_IN, ONEOFF_OUT = "one-off in", "one-off out"
ONEOFF_TAX, PURCHASE_COSTS = N_("tax on one-offs"), N_("purchase costs")  # groups of `ONEOFF_OUT`
# One-off moves of assets, outside the engine totals: a sale, a purchase, a repayment, a policy
# premium, the loan of a purchase.
MOVE_IN, MOVE_OUT = "move in", "move out"
# The group of what a savings plan pays from the cash into an asset, `MOVE_OUT` and `MOVED` by
# the name of the plan, and of the own premium of a Basisrente or an Altersvorsorgedepot,
# `<label>: premium`: no one-off, the budget keeps it apart from the spending.
SAVINGS_PLAN = "savings plan"
# The other side of a flow, outside the engine totals: how it changes an asset other than the
# cash, or a loan, beyond the loan principal. `DRAW`: what a payout that a source books (a bAV
# annuity, an Auszahlplan) takes out of its policy, the kind of the asset as the group. `MOVED`,
# a one-off: what a move or a one-off puts into an asset or takes out of it, its group as the
# move's (a sale at the value of the asset, a purchase, a repayment, a premium, a policy payout
# at once) or `write-off`. The item is the label of the asset.
DRAW, MOVED = "draw", "moved"
# Non-cash income, outside the engine totals: the growth of the assets, with the kind of the
# asset as the group and the item `equity`, `fixed income`, `cash` (the pools) or the label of
# the asset, and what goes into a policy without passing the cash, in `CONTRIBUTION` (the
# employer's bAV contribution, the Zulage of an Altersvorsorgedepot) or `ONEOFF_CONTRIBUTION`
# (the tax-free part of a severance, `<label>: severance`, and the top-up of a bAV policy to its
# guarantee at maturity, `<label>: guarantee`).
NONCASH = "non-cash"
CONTRIBUTION, ONEOFF_CONTRIBUTION = "contribution", "one-off contribution"
LOAN_INTEREST, LOAN_PRINCIPAL = N_("loan interest"), N_("loan principal")  # groups of `SPENDING`
CARE, UPKEEP = N_("care"), N_("property upkeep")  # groups of `SPENDING`, care also its item
# A group of `SPENDING`: the part of a salary that goes into a bAV policy (Entgeltumwandlung),
# with the policy label as the item and its `MOVED` side, no one-off: it stays in the net worth.
CONVERSION = N_("salary conversion")
# Groups of `SOURCE`: the gross of a salary stream, the profit of a self-employed one. Every other
# source has none.
SALARY, PROFIT = "salary", "profit"
PKV_SUBSIDY = N_("PKV subsidy")  # an item of `SOURCE`
KINDERGELD = "Kindergeld"  # an item of `SOURCE`, German already
# Items of `SOURCE` after the onset of a disability, German already: the Krankengeld (its shares
# book as `RV`, `AV`, `PV`) and the EM-Rente outside the phases of its pension stream, in them under
# the name of the stream. The benefit of a BU policy is `<name>: benefit`.
KRANKENGELD, EM_RENTE, BENEFIT = "Krankengeld", "EM-Rente", N_("benefit")
CAPITAL_TAX = N_("capital gains tax")  # item of `TAX`: Abgeltungsteuer net of the Günstigerprüfung
# The other items of `TAX`: the SV parts are German already
INCOME_TAX, TRADE_TAX = N_("income tax"), N_("trade tax")
RV, AV, KV, PV = "RV", "AV", "KV", "PV"
# The groups of the one-offs and the moves, an item of `ONEOFF_TAX` (`SETTLEMENT`: what a
# severance adds to the December settlement), `LUMP_SUM` and `SEVERANCE` also the item without a
# label
LUMP_SUM, SEVERANCE, SETTLEMENT = N_("lump sum"), N_("severance"), N_("settlement")
PREMIUM, PAYOUT = N_("policy premium"), N_("policy payout")
SALE, PURCHASE, LOAN = N_("sale"), N_("purchase"), N_("loan")
REPAYMENT, WRITE_OFF = N_("repayment"), N_("write-off")
# The items of the growth of the pools (`NONCASH`, the kind of the asset as the group)
EQUITY, FIXED_INCOME, CASH = N_("equity"), N_("fixed income"), N_("cash")
# After the label of a policy or a property: `<label>: employer`. `Zulage` is German already.
# `OWN_PREMIUM`: the own premium of a Basisrente or an Altersvorsorgedepot under `SAVINGS_PLAN`, so
# a policy named like a savings plan never merges with it.
EMPLOYER, SUBSIDY, ZULAGE, OWN_PREMIUM = N_("employer"), N_("subsidy"), "Zulage", N_("premium")
GUARANTEE, TRANSFER_TAX = N_("guarantee"), N_("transfer tax")
# The groups of `ONEOFF_IN` of an inheritance and a gift, by the label of the relative; their
# Erbschaftsteuer `<label>: inheritance tax` (or `gift tax`) in `ONEOFF_TAX`, their securities
# `<label>: equity` in `ONEOFF_CONTRIBUTION`
INHERITANCE, GIFT = N_("inheritance"), N_("gift")
INHERITANCE_TAX, GIFT_TAX = N_("inheritance tax"), N_("gift tax")
WORDS = frozenset(
    {
        *(ONEOFF_TAX, PURCHASE_COSTS, LOAN_INTEREST, LOAN_PRINCIPAL, CARE, UPKEEP, CONVERSION),
        *(PKV_SUBSIDY, KINDERGELD, CAPITAL_TAX, INCOME_TAX, TRADE_TAX, RV, AV, KV, PV),
        *(KRANKENGELD, EM_RENTE, BENEFIT),
        *(LUMP_SUM, SEVERANCE, SETTLEMENT, PREMIUM, PAYOUT, SALE, PURCHASE, LOAN, REPAYMENT),
        *(WRITE_OFF, EQUITY, FIXED_INCOME, CASH, EMPLOYER, SUBSIDY, ZULAGE, GUARANTEE),
        *(TRANSFER_TAX, OWN_PREMIUM, INHERITANCE, GIFT, INHERITANCE_TAX, GIFT_TAX),
    }
)


@dataclass
class Ledger:
    """Every cash flow of a single-path run by month, in euros of the simulation start. A key
    is `(side, group, item)`. Moves between the own accounts (investing, withdrawals,
    maturing deposits) are no flows. The December tax settlement is spread over the months of
    its year, so a part of a year carries its share. The side `NONCASH` holds the growth of the
    assets in each month and what goes into a policy without passing the cash, nominal at the
    price level of its year like every entry, and the sides `DRAW` and `MOVED` how a flow
    changes an asset other than the cash: with them the entries of a year add up to the change
    of the net worth before the latent tax (`budget.Budget.wealth_built` with the one-offs)."""

    months: int
    entries: dict[tuple[str, str, str], FloatArray] = field(default_factory=dict)
    # run rate of the streams paid every n months: added to `entries`, it spreads each payment
    # over the n months that end with it. A payment early in the run loses the months before.
    run_rate: dict[tuple[str, str, str], FloatArray] = field(default_factory=dict)

    def add(
        self,
        key: tuple[str, str, str],
        months: range,
        amount: float,
        weights: FloatArray | None = None,
    ) -> None:
        """Spread `amount` over `months` by `weights`, evenly without or when they sum to 0."""
        if amount:
            row = self.entries.setdefault(key, np.zeros(self.months))
            share = (
                weights / weights.sum()
                if weights is not None and weights.sum() > 0
                else np.full(len(months), 1 / len(months))
            )
            row[months.start : months.stop] += amount * share

    def accrue(self, key: tuple[str, str, str], month: int, amount: float) -> None:
        if amount:
            self.run_rate.setdefault(key, np.zeros(self.months))[month] += amount


MarkerForm = Literal["", "monthly", "once", "half"]
# What a marker marks: what the engine marks, then the type of an event, which `Core._mark` takes
# as it is (the type checker holds the two lists equal)
MarkerKind = Literal[
    "phase",
    "pension",
    "bav",
    "av",
    "alg1",
    "savings plan",
    "harvest",
    "disability",
    "exemption",
    "gkv",
    "sell",
    "buy",
    "buy_property",
    "repay",
    "severance",
    "fund_policy",
    "lump_sum",
    "write_off",
    "end_streams",
    "set_stream",
    "add_stream",
    "inheritance",
    "gift",
]


@dataclass(frozen=True)
class Marker:
    """What the engine marks in a month, as data: the pages write the words
    (`report.charts.readable`). `kind` is an event type or what the engine marks (`MarkerKind`),
    `detail` a name as the inputs write it (of an event, a policy, a plan, the label of a phase),
    `amount` the median euros (what a policy pays, an inheritance or a gift brings, a harvest
    realizes) or the claim factor of a pension, `years` its insured years and `since` the month of
    the claim that it deferred, `form` (`MarkerForm`) how it pays or happens: `monthly`, at `once`,
    or when `half` of the paths have."""

    month: date
    kind: MarkerKind
    detail: str = ""
    amount: float = 0.0
    years: float = 0.0
    since: date | None = None
    form: MarkerForm = ""


@dataclass
class RunResult:
    """Arrays are shaped (paths, months) unless noted."""

    scenario: str
    model: str
    months: list[date]
    ages: FloatArray  # (months,) age in years at each month
    phases: list[str]  # (months,)
    liquid: FloatArray  # cash, deposits, fixed income, equity, gold, crypto, less latent tax
    total: FloatArray  # liquid + property + policies and Altersvorsorgedepots - debt
    income: FloatArray  # gross monthly income, including PKV subsidies
    expenses: FloatArray  # monthly expenses (negative)
    # income, church and trade tax, Soli, SV, Grunderwerbsteuer and Erbschaftsteuer (negative)
    taxes: FloatArray
    capital_taxes: FloatArray  # Abgeltungsteuer net of the Günstigerprüfung (negative)
    broke: BoolArray  # liquid net worth below zero
    reduced: IntArray  # (paths,) months in which the spending rule cut
    raised: IntArray  # (paths,) months in which the spending rule raised
    care: BoolArray  # long-term care episode active in this month
    onset: IntArray  # (paths,) the month index of the onset of a disability, -1 without
    em: BoolArray  # (paths,) an EM-Rente is paid after the onset
    cpi: NDArray[np.float32]  # consumer price level of the path, 1 in the first month
    note: str = ""  # `Scenario.note`: what the scenario stands for
    # how the pages name each phase of `assumptions.yaml`, in its order, which sets the colors
    phase_labels: dict[str, str] = field(default_factory=dict)
    markers: list[Marker] = field(default_factory=list)
    survival: FloatArray | None = None  # (months,) probability alive
    # (months,) mean per class of BALANCE_CLASSES over the paths inside MEDIAN_BAND of `total`,
    # both deflated to euros of the first month. Per path the classes add up to `total`, so
    # the band means add up to about its median. Class medians do not: a per-path sale keeps
    # the property median at full value. Real values cannot come from nominal band means, so
    # the engine reduces both: `nominal_balance` over the band of the nominal `total`.
    balance: dict[str, FloatArray] = field(default_factory=dict)
    nominal_balance: dict[str, FloatArray] = field(default_factory=dict)
    # (paths,) one number per path and random driver, by its kind and the name of its class or
    # index: `anatomy.drivers`
    drivers: dict[tuple[str, str], NDArray[np.float32]] = field(default_factory=dict)
    ledger: Ledger | None = None  # single-path runs only
    twin: bool = False  # the explorer's run of the files beside the run of its sliders
    # the month index of the first month after the last pay, a salary or a profit by the dates and
    # phases of the streams (`engine.core.pays`, the same on every path); 0 for a plan without pay
    # or whose pay runs to the end
    pay_ends: int = 0

    @property
    def label(self) -> str:
        """How the pages name the run: its scenario, a twin as `TWIN` says, in the language of
        the page."""
        return _(TWIN).format(scenario=self.scenario) if self.twin else self.scenario

    @property
    def paths(self) -> int:
        return int(self.liquid.shape[0])

    @property
    def broke_by(self) -> BoolArray:
        """Broke in the month or before: once broke, stays broke."""
        return np.maximum.accumulate(self.broke, axis=1)

    def euros(self, arr: FloatArray, *, nominal: bool = False) -> FloatArray:
        """`arr` in euros of the first month, each path deflated by its own price level. Take
        medians and percentiles after this, never before."""
        return arr if nominal else arr / self.cpi

    def unit(self, *, nominal: bool = False, yearly: bool = False) -> str:
        return unit(self.months[0], nominal=nominal, yearly=yearly)

    def taxes_paid(self, *, nominal: bool = False) -> FloatArray:
        """Income, church and trade tax, Soli, SV, Grunderwerbsteuer, Erbschaftsteuer and capital
        gains tax of each path and month, less refunds, as a positive amount."""
        return -self.euros(self.taxes + self.capital_taxes, nominal=nominal)

    def percentiles(
        self, arr: FloatArray, qs: tuple[float, ...] = (5, 25, 50, 75, 95)
    ) -> FloatArray:
        """Shape (len(qs), months)."""
        return np.asarray(np.percentile(arr, qs, axis=0))

    def age_index(self, age: float) -> int:
        return age_index(self.ages, age)

    def age_at(self, age: float) -> int:
        return age_at(self.ages, age)

    def median_at_age(self, arr: FloatArray, age: float) -> float:
        return float(np.median(arr[:, self.age_index(age)]))

    @property
    def broke_share(self) -> FloatArray:
        """(months,) share of the paths broke in the month or before."""
        return np.asarray(self.broke_by.mean(axis=0))

    def p_broke_by_age(self, age: int) -> float:
        return float(self.broke_share[self.age_index(age)])

    @property
    def deaths(self) -> FloatArray:
        """(months,) probability to die in each month, the survivors counted in the last. Paths
        do not die: without `survival` every path lives to the end of the run."""
        alive = np.ones(len(self.months)) if self.survival is None else self.survival
        return -np.diff(alive, append=0.0)

    def p_broke_alive(self) -> float:
        """Probability to be broke in some month while alive: to die after the path went broke."""
        return float(self.deaths @ self.broke_share)

    def shortfall(self, *, nominal: bool = False) -> float | None:
        """How far liquid net worth fell below zero before death, over the lives that go broke:
        the median of the lowest liquid value by each month of death on each path, weighted by
        the probability to die then. Without `survival` the lowest value of the broke paths.
        None when no life goes broke."""
        low = np.minimum.accumulate(self.euros(self.liquid, nominal=nominal), axis=1)
        broke = low < 0
        weights = np.broadcast_to(self.deaths, low.shape)[broke]
        if not weights.sum():
            return None
        order = np.argsort(low[broke])
        cum = np.cumsum(weights[order])
        return float(-low[broke][order][np.searchsorted(cum, cum[-1] / 2)])
