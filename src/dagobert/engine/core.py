"""`Core`, the base of every step of a month: the setup of a run from the plan and the return
paths (the holdings, the streams and their events, the care episodes, the onsets of a disability,
the ledger and the markers)
and the helpers that every step reads: the price levels, the indices and amounts of the streams,
the loans, the liquid net worth and its latent tax."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date

import numpy as np
from numpy.typing import NDArray

from dagobert import carry, mortality, tax
from dagobert.engine.state import (
    Acquisition,
    Alg1State,
    AvState,
    LoanState,
    MonthFlows,
    MonthState,
    PensionState,
    PolicyState,
    PropertyState,
    Received,
    SickPay,
    StreamState,
    YearAcc,
)
from dagobert.holdings import Pool
from dagobert.model.assets import (
    AvDepot,
    CashAsset,
    CryptoAsset,
    EquityAsset,
    FixedIncomeAsset,
    GoldAsset,
    Loan,
    PensionPolicy,
    PropertyAsset,
    TermDeposit,
)
from dagobert.model.assumptions import CPI_INDEX, Assumptions, interpolate
from dagobert.model.events import (
    STATE_EVENTS,
    Acquired,
    Event,
    GiftEvent,
    SellEvent,
)
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Plan
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import (
    LOAN_INTEREST,
    LOAN_PRINCIPAL,
    MOVE_OUT,
    MOVED,
    REPAYMENT,
    SPENDING,
    FloatArray,
    IntArray,
    Ledger,
    Marker,
    MarkerForm,
    MarkerKind,
)
from dagobert.returns import Returns, generator, years_of

EARNED = (StreamKind.SALARY, StreamKind.SELF_EMPLOYED)  # pay: ALG1 replaces it, it is none
REARM = 12  # the months of pay in a row after which a month without pay takes a new reference


def pays(s: Stream, a: Assumptions, phase: str, factor_override: float | None = None) -> bool:
    """A salary or a profit pays in `phase`: one of its `phases` (none: every phase), an amount,
    no factor (`factor_override`: a `set_stream` one) or salary scale of 0. The goal seek takes
    the phases of the pay by it, the spending rule the pay of its first month."""
    factor = s.factor.get(phase, 1.0) if factor_override is None else factor_override
    return (
        s.kind in EARNED
        and (s.phases is None or phase in s.phases)
        and (s.of is not None or bool(s.gross or s.amount))
        and factor * a.scale.salary.get(phase, 1.0) != 0
    )


def year_levels(cpi: FloatArray, first_month: int) -> FloatArray:
    """One price level per calendar year and path, the mean CPI of its months, 1 in the start
    year. `cpi` has one column per month from the start, `first_month` is its calendar month."""
    year = years_of(first_month, cpi.shape[1])
    level = np.empty_like(cpi)
    for y in range(year[-1] + 1):
        level[:, year == y] = cpi[:, year == y].mean(axis=1, keepdims=True)
    return level / level[:, :1]


class Core:
    def __init__(self, plan: Plan, returns: Returns, model: str) -> None:
        self.plan = plan
        self.a: Assumptions = plan.assumptions
        self.returns = returns
        self.model = model
        self.paths, self.n_months = returns.inflation.shape
        self.start = self.a.start
        self.ty = tax.for_year(self.a.tax_year)
        self.church = tax.church_rate(self.a.tax, self.ty)  # a share of the income tax
        self.flat_rate = tax.flat_rate(self.church, self.ty)  # on a euro of capital income
        self.markers: list[Marker] = []
        self.ledger = Ledger(self.n_months) if self.paths == 1 else None
        self.earned = np.zeros(self.n_months)  # taxable income of the year so far, with a ledger
        self.m = MonthState(0, self.start, self.plan.phase_at(self.start))
        self._init_paths()
        self._init_assets()
        self._init_streams()
        self._init_acquisitions()
        self._init_bookkeeping()

    def _init_paths(self) -> None:
        growth = 1 + self.returns.inflation  # inflation during month i, so month 0 is at 1.0
        self.cpi = np.cumprod(np.hstack([np.ones((self.paths, 1)), growth[:, :-1]]), axis=1)
        self.level = year_levels(self.cpi, self.start.month)
        self.eq_index = np.cumprod(1 + self.returns.rates["equity"], axis=1)
        self.eq_price = np.ones(self.paths)  # the equity index now: before or after the return
        self.age_factor = self._age_factors()
        self.care = self._draw_care()
        self.onset = self._draw_disability()

    def _assets[T](self, kind: type[T]) -> list[T]:
        return [x for x in self.plan.assets if isinstance(x, kind)]

    def _init_assets(self) -> None:
        ones = np.ones(self.paths)
        self.cash: FloatArray = ones * sum(x.value for x in self._assets(CashAsset))
        self.deposits = {x.id: x for x in self._assets(TermDeposit)}
        eq = self._assets(EquityAsset)
        # the Teilfreistellung (§20 InvStG) of each depot by its id, None that of the assumptions
        self.exempt: dict[str | None, float] = {None: self.a.tax.teilfreistellung} | {
            x.id: self.a.tax.teilfreistellung if x.teilfreistellung is None else x.teilfreistellung
            for x in eq
        }
        value = sum(x.value for x in eq)
        self.equity = ones * value
        # the depots are one pool: the share of its value and its basis after the
        # Teilfreistellung of each, which the one return keeps and a sale of a slice too
        taxed = sum(x.value * (1 - self.exempt[x.id]) for x in eq)
        self.taxable_share = ones * (taxed / value if value > 0 else 1 - self.exempt[None])
        self.taxable_basis = ones * sum(x.basis * (1 - self.exempt[x.id]) for x in eq)
        bucket = self._assets(FixedIncomeAsset)
        self.fixed = ones * sum(x.value for x in bucket)
        self.bucket = {x.id for x in bucket}  # the fixed-income assets: one pool
        self.properties = {
            x.id: self._property(x, ones * x.value) for x in self._assets(PropertyAsset)
        }
        before = add_months(self.start, -1)  # a value of an earlier `asof` rolls forward
        self.policies = [
            PolicyState(x, ones * value, ones * paid)
            for x in self._assets(PensionPolicy)
            for value, paid in [carry.policy(self.plan, x, before)]
        ]
        self.av = [
            AvState(x, ones * carry.depot(self.plan, x, before)) for x in self._assets(AvDepot)
        ]
        self.pools = {  # in file order, which a deficit sells by
            x.id: Pool.opening(
                x,
                self.start,
                self.paths,
                self.ty.private_sale_months,
                self.a.tax.crypto_capital_from,
            )
            for x in self.plan.assets
            if isinstance(x, GoldAsset | CryptoAsset)
        }

    def _init_streams(self) -> None:
        scenario = self.plan.scenario
        self.streams = [self._stream_state(s) for s in self.plan.streams]
        self.loans = [
            LoanState(x, x.opening(self.start, self.a.refinance_rate), finances=x.finances)
            for x in self._assets(Loan)
        ]
        self.events: defaultdict[int, list[Event]] = defaultdict(list)
        dated = [(months_between(self.start, e.at), e) for e in scenario.events if e.at is not None]
        for i, e in sorted(dated, key=lambda x: x[0]):  # stable: a month keeps the file order
            if i < 0 and not isinstance(e, STATE_EVENTS):
                msg = f"{e.type} event at {e.at} lies before the start {self.start}"
                raise ValueError(msg)
            if not isinstance(e, Acquired):  # `acquisitions`
                self.events[max(i, 0)].append(e)
        self.conditional = [  # with the paths in which each has fired
            (e, np.zeros(self.paths, dtype=bool))
            for e in scenario.events
            if isinstance(e, SellEvent) and e.when is not None
        ]

    def _init_acquisitions(self) -> None:
        """The inheritances and gifts (`Acquisition`), in file order. One without a month falls at
        the death of its givers: the month of each relative that one names, drawn per path, the
        later one of two. A dated gift of a giver dead by its month joins the first such estate
        of that giver on that path. Per relative what it gave (`Received`): the gifts before the
        start and a row per event that names it."""
        events = [e for e in self.plan.scenario.events if isinstance(e, Acquired)]
        deaths = {key: self._death(key) for e in events if e.at is None for key in e.givers}
        self.acquisitions = [self._acquisition(e, deaths) for e in events]
        for got in self.acquisitions:
            key = got.event.givers[0]
            if isinstance(got.event, GiftEvent) and key in deaths:
                waits = deaths[key] <= got.month
                estate = next(
                    b for b in self.acquisitions if b.event.at is None and key in b.event.givers
                )
                estate.joined.append((got.event, waits))
                got.month = np.where(waits, self.n_months, got.month)
        self.received: dict[str, Received] = {}
        for key, relative in self.a.person.relatives.items():
            given = relative.given
            named = [e for e in events if key in e.givers]
            rows = len(given) + len(named)
            month = np.zeros((rows, self.paths), dtype=np.intp)
            value, paid = np.zeros((rows, self.paths)), np.zeros((rows, self.paths))
            for row, g in enumerate(given):
                month[row], value[row], paid[row] = months_between(self.start, g.at), g.value, g.tax
            ids = {id(e): len(given) + n for n, e in enumerate(named)}
            self.received[key] = Received(month, value, paid, ids)

    def _acquisition(self, e: Acquired, deaths: dict[str, NDArray[np.intp]]) -> Acquisition:
        """`e` in its month, without one at the later death of its givers, with the giver who
        died last."""
        unpaid = np.zeros(self.paths, dtype=bool)
        if e.at is not None:
            month = np.full(self.paths, months_between(self.start, e.at))
            return Acquisition(e, month, np.zeros(self.paths, np.intp), unpaid)
        months = np.array([deaths[key] for key in e.givers])
        return Acquisition(e, months.max(axis=0), months.argmax(axis=0), unpaid)

    def _death(self, key: str) -> NDArray[np.intp]:
        """The month index of the death of the relative `key` per path, from the shipped life
        table, alive at the start (`inheritance.<key>`); the median month in a single-path run;
        the length of the run beyond it."""
        curve = mortality.survival_curve(
            mortality.table(), self.a.person.relatives[key], self.start, self.n_months
        )
        draw = (
            np.full(1, 0.5)
            if self.paths == 1
            else generator(self.a.seed, f"inheritance.{key}").random(self.paths)
        )
        return mortality.death_months(curve, draw)

    def _init_bookkeeping(self) -> None:
        self.acc = YearAcc.new(self.equity, np.ones(self.paths), self.a.tax.sparer_pauschbetrag)
        self.flows = MonthFlows.new(self.paths)
        self._init_spending_rule()
        self.last_salary = np.zeros(self.paths)  # nominal contributory salary: the ALG1 base
        self.losses = np.zeros(self.paths)  # general loss pot in start-year euros (§20 Abs. 6)
        self.private_losses = np.zeros(self.paths)  # §23 losses carried, start-year euros
        # the Verlustvortrag of the income tax (§10d Abs. 2 EStG), nominal as the law carries it
        self.income_losses = np.full(self.paths, self.a.tax.loss_carryforward)
        # the monthly base of a freiwilliges GKV member from the last year (`Health._kv_last`)
        self.kv_last = np.zeros(self.paths)
        # the rest of that base in the month, what caps a harvest (`Health._kv_room`)
        self.kv_rest = np.zeros(self.paths)
        # the church tax of the last settlement less its withholding: paid in the next year
        self.church_due = np.zeros(self.paths)  # nominal
        self.paused: set[str] = set()  # the savings plans with a marker
        self.harvested = False  # the harvest has its marker
        self.first_profit: date | None = None  # the first month of a self-employed stream
        self.alg1 = Alg1State()
        since = self.a.person.rv_since
        insured = months_between(since, self.start) if since else 0
        # the run cannot see the months before the start: those since `rv_since` count as months
        # of Pflichtbeiträge when the first month pays a salary or a profit
        self.pension = PensionState.new(
            self.paths, insured, insured * bool(self.earns.any()), self.ty.em_window_months
        )
        self.em_ok = np.zeros(self.paths, dtype=bool)  # an onset that an EM-Rente follows
        self.sick = SickPay.new(self.paths)
        self.bu_paid = np.zeros(self.paths)  # nominal, the benefits of the BU policies this month

    def _init_spending_rule(self) -> None:
        """Per path the state of the spending rule: whether it cuts or raises this month, the
        months it did so, its reference in start-year euros (none before the first month that
        arms it), whether the month before paid a salary or a profit (`earns`, the first month by
        the phase of the start) and the months of pay in a row before it. Of VPW: the budget of
        the year, nominal (none before its first month without pay), the year that set it, the
        bill of the last December, the cash after the returns of the month and the liquid wealth
        at its start."""
        self.reduced = np.zeros(self.paths, dtype=bool)
        self.raised = np.zeros(self.paths, dtype=bool)
        self.months_cut = np.zeros(self.paths, dtype=int)
        self.months_raised = np.zeros(self.paths, dtype=int)
        self.reference = np.full(self.paths, np.nan)
        self.paying = np.zeros(self.paths, dtype=int)
        self.budget = np.full(self.paths, np.nan)
        self.budget_year = np.full(self.paths, -1)
        self.settled = np.zeros(self.paths)
        self.oneoff_tax = np.zeros(self.paths)
        self.cash_mark = self.cash.copy()
        self.liquid_prev = np.zeros(self.paths)
        phase = self.m.phase
        self.earns = (
            sum(
                (
                    s.mask
                    for s in self.streams
                    if s.active(self.start, phase)
                    and pays(s.spec, self.a, phase, s.factor_override)
                ),
                np.zeros(self.paths),
            )
            > 0
        )

    def _property(self, spec: PropertyAsset, value: FloatArray) -> PropertyState:
        """A property worth `value`, held since `bought` (a month index below 0 before the start).
        It has taken the AfA of each month from then to the start: a property of the file with
        `afa` counts as let since its purchase (§7 Abs. 1 S. 4 EStG: from the month of the
        purchase)."""
        bought = None if spec.bought is None else months_between(self.start, spec.bought)
        state = PropertyState(
            spec, value, np.zeros(self.paths, dtype=bool), np.zeros(self.paths), bought
        )
        before = max(-(bought or 0), 0) * (spec.afa or 0.0) * state.afa_base / 12
        state.afa_taken = np.full(self.paths, min(before, state.afa_base))
        return state

    def _stream_state(self, spec: Stream) -> StreamState:
        off = spec.after_sale_of is not None
        return StreamState(
            spec, spec.end, np.full(self.paths, 0.0 if off else 1.0), np.zeros(self.paths, bool)
        )

    def _age_factors(self) -> FloatArray:
        curve = self.a.spending.age_curve if self.a.spending else []
        if not curve:
            return np.ones(self.n_months)
        return np.array([interpolate(curve, self._age(i)) for i in range(self.n_months)])

    def _first_month(self, rng: np.random.Generator, yearly: FloatArray, none: int) -> IntArray:
        """Per path the first month index in which a uniform draw falls below the monthly chance
        of the `yearly` hazards, `none` where no month does."""
        hit = rng.random((self.paths, len(yearly))) < 1 - (1 - yearly) ** (1 / 12)
        return np.where(hit.any(axis=1), hit.argmax(axis=1), none)

    def _draw_care(self) -> NDArray[np.bool_]:
        """Per path and month: is the person in a care episode? Single-path runs draw none."""
        care = self.a.care
        in_care = np.zeros((self.paths, self.n_months), dtype=bool)
        if care is None or self.paths == 1:
            return in_care
        yearly = np.array([care.hazard_at(self._age(i)) for i in range(self.n_months)])
        rng = generator(self.a.seed, "care")
        start = self._first_month(rng, yearly, self.n_months)
        months = np.maximum(rng.normal(care.duration.mean, care.duration.stdev, self.paths), 1)
        end = start + np.round(months).astype(int)
        span = np.arange(self.n_months)[None, :]
        return np.asarray((span >= start[:, None]) & (span < end[:, None]), dtype=bool)

    def _draw_disability(self) -> IntArray:
        """Per path the month index of the onset of a full Erwerbsminderung, -1 without: `at` in
        every path, else the first month in which a draw of its own purpose falls below the
        monthly chance by age (`DisabilityOptions.hazard_at`), before the Regelaltersgrenze
        (§43 SGB VI). Single-path runs draw none but `at`. The month of the old-age claim and the
        months after it drop an onset (`Income._claim_pension`)."""
        none = np.full(self.paths, -1)
        spec = self.a.disability
        before = [self._age(i) < self.ty.regelaltersgrenze for i in range(self.n_months)]
        months = sum(before)  # the ages fall into the run in order
        if spec is None:
            return none
        if spec.at is not None:
            i = months_between(self.start, spec.at)
            return np.full(self.paths, i) if i < months else none
        if self.paths == 1 or not months:
            return none
        yearly = np.array([spec.hazard_at(self._age(i)) for i in range(months)])
        return self._first_month(generator(self.a.seed, "disability"), yearly, -1)

    @property
    def working(self) -> FloatArray:
        """Per path 1 while the person works or is paid on (§3 EFZG: `efzg_months` from the
        onset), else 0: a salary, a profit, ALG1 and the employer's bAV contribution stop."""
        stopped = (self.onset >= 0) & (self.m.i >= self.onset + self.ty.efzg_months)
        return np.where(stopped, 0.0, 1.0)

    def _level(self, index: str | None) -> FloatArray:
        """This month's level of a growth index, 1 for a nominal amount."""
        if index is None:
            return np.ones(self.paths)
        return (self.cpi if index == CPI_INDEX else self.returns.indices[index])[:, self.m.i]

    def _care_cost(self) -> FloatArray:
        care = self.a.care
        if care is None:
            return np.zeros(self.paths)
        return -care.cost * self._level(care.index) * self.care[:, self.m.i]

    @property
    def deflator(self) -> FloatArray:
        """Path price level of this calendar year. Tax rules apply in start-year euros, as if
        their constants were indexed each January: every flow of a year and its December
        settlement convert at the same level."""
        return self.level[:, self.m.i]

    @property
    def taxable_gain(self) -> FloatArray:
        """The gain of the depots after the Teilfreistellung of each, below 0 a loss: what a sale
        of all of them taxes. Every depot earns the one return, so a slice of the pool holds the
        same share of it."""
        return self.equity * self.taxable_share - self.taxable_basis

    def _mark(
        self,
        kind: MarkerKind,
        detail: str = "",
        *,
        amount: float = 0.0,
        years: float = 0.0,
        since: date | None = None,
        form: MarkerForm = "",
    ) -> None:
        self.markers.append(Marker(self.m.month, kind, detail, amount, years, since, form))

    def _note(
        self,
        side: str,
        group: str,
        item: str,
        nominal: FloatArray | float,
        *,
        since: int | None = None,
        weights: FloatArray | None = None,
    ) -> None:
        """Ledger entry of this month, spread over the months from `since` when given, by
        `weights` when given."""
        if self.ledger is not None:
            real = float(np.ravel(nominal / self.deflator)[0])
            span = range(self.m.i if since is None else since, self.m.i + 1)
            self.ledger.add((side, group, item), span, real, weights)

    def _note_move(self, group: str, item: str, nominal: FloatArray | float) -> None:
        """A move of the cash into an asset: out of the cash and into the asset."""
        for side in (MOVE_OUT, MOVED):
            self._note(side, group, item, nominal)

    def _withhold(self, withholding: Callable[[float], FloatArray]) -> FloatArray:
        """A withholding in start-year euros, `withholding` at the church rate of the plan: its
        church tax joins what the year paid of it, a Sonderausgabe (§10 Abs. 1 Nr. 4 EStG)."""
        withheld = withholding(self.church)
        self.acc.withheld += withheld
        if self.church:
            self.acc.church_withheld += withheld - withholding(0.0)
        return withheld

    def _receive(self, gross: FloatArray | float, taken: FloatArray | float = 0.0) -> None:
        """Nominal gross income less the taxes and SV `taken` off it into the cash, both
        reported."""
        self.flows.income += gross
        self.flows.taxes -= taken
        self.cash += gross - taken

    def _spend(self, nominal: FloatArray | float) -> None:
        """Nominal expenses of the month, below zero, out of the cash, reported."""
        self.flows.expenses += nominal
        self.cash += nominal

    def _pays(self, s: StreamState) -> bool:
        first = months_between(self.start, s.spec.start) if s.spec.start else 0
        return s.active(self.m.month, self.m.phase) and (self.m.i - first) % s.spec.every == 0

    def _spread(self, key: tuple[str, str, str], paid: FloatArray, every: int) -> None:
        """The run rate of a payment every n months: it counts 1/n in each of the n months that
        end with it, as far as the run reaches back."""
        if self.ledger is None or every == 1:
            return
        real = float(np.ravel(paid / self.deflator)[0])
        for month in range(max(self.m.i - every + 1, 0), self.m.i + 1):
            self.ledger.accrue(key, month, real / every)
        self.ledger.accrue(key, self.m.i, -real)

    def _index(self, s: StreamState) -> FloatArray:
        """Per-path multiplier: the growth index, `scale.spending`, `scale.categories`, the
        spending cut, the age curve and the sale on/off mask."""
        spec = s.spec
        base = s.mask * self._level(spec.index)
        if spec.managed:
            base = base * self.a.scale.spending * self.a.scale.categories.get(spec.cat, 1.0)
        rule = self.a.spending
        if rule is None:
            return base
        if spec.managed and spec.cat in rule.categories:
            base = base * np.where(
                self.reduced, 1 - rule.cut, np.where(self.raised, 1 + rule.increase, 1.0)
            )
        if spec.managed and (rule.age_categories is None or spec.cat in rule.age_categories):
            base = base * self.age_factor[self.m.i]
        return base

    def _flexible(self, s: StreamState) -> bool:
        """An expense of a flexible category under VPW: `Income._pay_flexible` pays it."""
        rule = self.a.spending
        return (
            rule is not None
            and rule.vpw is not None
            and s.spec.managed
            and s.spec.cat in rule.categories
        )

    def _nominal(self, s: StreamState) -> FloatArray:
        """Nominal amount of one plain stream this month."""
        return s.amount * s.factor(self.m.phase) * self._index(s)

    def _run_rate(self, kind: StreamKind, *, taxable: bool = False) -> FloatArray:
        """Nominal run rate of the streams of `kind` active this month, with `taxable` of the
        taxable ones that let no property (a rent counts through `_rent_net`): a stream paid
        every n months counts 1/n in each month."""
        return sum(
            (
                self._nominal(s) / s.spec.every
                for s in self.streams
                if s.spec.kind == kind
                and s.active(self.m.month, self.m.phase)
                and (not taxable or (s.spec.taxable and s.spec.property is None))
            ),
            np.zeros(self.paths),
        )

    def _let(self, prop: PropertyState) -> NDArray[np.bool_]:
        """Per path: a rent of the property (other income that names it) is active this month,
        by its dates, phases and the mask of a sale, and the property is not sold. A rent paid
        every n months lets it in each month, at a factor of 0 too: a vacant month."""
        rents = [
            s.mask > 0
            for s in self.streams
            if s.spec.property == prop.spec.id
            and s.spec.kind == StreamKind.OTHER_INCOME
            and s.active(self.m.month, self.m.phase)
        ]
        let = np.any(rents, axis=0) if rents else np.zeros(self.paths, dtype=bool)
        return np.asarray(let & ~prop.sold)

    def _rent_net(self) -> FloatArray:
        """Nominal income of the month from letting (§21 Abs. 1 S. 1 Nr. 1 EStG) per path: of
        each let property the run rate of its rents less its Werbungskosten (§9 Abs. 1 S. 3 Nr.
        1, 2, 7): the AfA of the month, the interest of the loans that finance it, its upkeep and
        the run rate of the expenses that name it. Below zero a loss. Pure, so `Income` and
        `Health` both take it; `_take_afa` advances the AfA once."""
        net = np.zeros(self.paths)
        for prop in self.properties.values():
            let = self._let(prop)
            if not let.any():
                continue
            linked = sum(
                (
                    self._nominal(s) / s.spec.every
                    for s in self.streams
                    if s.spec.property == prop.spec.id and s.active(self.m.month, self.m.phase)
                ),
                np.zeros(self.paths),
            )
            interest = sum(loan.interest for loan in self.loans if loan.finances == prop.spec.id)
            costs = prop.afa_month + interest + prop.value * prop.spec.upkeep / 12
            net += np.where(let, linked - costs, 0.0)
        return net

    def _take_afa(self) -> None:
        """Once a month, after the streams: each let property takes the AfA of the month. A
        month not let takes none (§9 Abs. 1 S. 2 EStG)."""
        for prop in self.properties.values():
            prop.afa_taken = prop.afa_taken + self._let(prop) * prop.afa_month

    def _fixed_share(self) -> float:
        return self.a.allocation.share_at(self._age(self.m.i)) if self.a.allocation else 0.0

    def _update_spending_rule(self, liquid_prev: FloatArray) -> None:
        """The cut and the increase of this month by the liquid wealth at its start against the
        reference, in real terms. `start` acts in every month and arms in the first; `no_pay`
        acts in a month after a month without pay and arms in the first such month, again after
        `REARM` months of pay in a row. VPW keeps the liquid wealth for its budget
        (`Income._pay_flexible`)."""
        rule = self.a.spending
        if rule is None:
            return
        if rule.vpw is not None:
            self.liquid_prev = liquid_prev
            return
        free = ~self.earns if rule.base == "no_pay" else np.ones(self.paths, dtype=bool)
        arm = free & (np.isnan(self.reference) | (self.paying >= REARM))
        first = rule.reference if self.m.i == 0 and rule.reference is not None else None
        self.reference = np.where(
            arm, liquid_prev / self.deflator if first is None else first, self.reference
        )
        self.paying = np.where(free, 0, self.paying + 1)
        level = self.reference * self.deflator
        self.reduced = free & (rule.trigger > 0) & (liquid_prev < rule.trigger * level)
        self.raised = (
            free
            & ~self.reduced
            & (rule.increase * rule.ceiling > 0)
            & (liquid_prev > rule.ceiling * level)
        )
        self.months_cut += self.reduced
        self.months_raised += self.raised

    def _loan_by_id(self, loan_id: str) -> LoanState:
        for loan in self.loans:
            if loan.spec.id == loan_id:
                return loan
        msg = f"unknown loan {loan_id}"
        raise KeyError(msg)

    def _repay(self, loan_id: str, amount: float | str) -> tuple[float, float]:
        """Returns what left the cash account: the repayment and the penalty."""
        loan = self._loan_by_id(loan_id)
        pay = -loan.balance if amount == "all" else min(float(amount), -loan.balance)
        penalty = pay * loan.spec.prepayment_penalty if loan.spec.fixed_at(self.m.month) else 0.0
        loan.balance += pay
        self.cash -= pay + penalty
        self._note(MOVE_OUT, REPAYMENT, loan.spec.label, pay + penalty)
        self._note(MOVED, REPAYMENT, loan.spec.label, pay)
        return pay, penalty

    def _service_loans(self) -> None:
        """The annuities of the month, an expense."""
        for loan in self.loans:
            loan.interest = 0.0
            if loan.balance >= 0 or self.m.i < loan.since:
                continue
            after, pay = loan.spec.step(loan.balance, self.m.month, self.a.refinance_rate)
            principal = after - loan.balance
            loan.interest = pay - principal
            self._note(SPENDING, LOAN_INTEREST, loan.spec.label, loan.interest)
            self._note(SPENDING, LOAN_PRINCIPAL, loan.spec.label, principal)
            loan.balance = after
            self._spend(-pay)

    @property
    def _january(self) -> int:
        """The month index of January of this year, or of the first month of the run."""
        return max(self.m.i - self.m.month.month + 1, 0)

    def _age(self, i: int) -> float:
        """Age in whole months. A birthday after the first is reached the month after."""
        return self.a.person.age(self.start, i)

    def _latent_tax(self) -> FloatArray:
        """Tax due if the equity gains, the accrued deposit interest and the gains of the gold
        and crypto under §20 were realized today."""
        invested = sum(spec.value for spec in self.deposits.values())
        flat = self._deposits() - invested + sum((p.latent for p in self.pools.values()), 0.0)
        return (np.maximum(self.taxable_gain, 0) + flat) * self.flat_rate

    def _deposits(self) -> FloatArray:
        """Term deposits with the interest accrued so far."""
        return np.full(
            self.paths, sum(spec.value_at(self.m.month) for spec in self.deposits.values())
        )

    def _pool_value(self, kind: str) -> FloatArray:
        """The value of the gold or of the crypto."""
        return sum(
            (p.value for p in self.pools.values() if p.spec.kind == kind), np.zeros(self.paths)
        )

    def _balance(self) -> dict[str, FloatArray]:
        """Nominal value of each class of `BALANCE_CLASSES` now: per path they add up to the net
        worth, those of `LIQUID` to the liquid net worth."""
        zero = np.zeros(self.paths)
        return {
            "cash": self.cash,
            "fixed_income": self._deposits() + self.fixed,
            "equity": self.equity,
            "gold": self._pool_value("gold"),
            "crypto": self._pool_value("crypto"),
            "property": sum((prop.held for prop in self.properties.values()), zero),
            "policies": sum((pol.value for pol in self.policies), zero)
            + sum((av.value for av in self.av), zero),
            "loans": np.full(self.paths, sum(loan.balance for loan in self.loans)),
            "latent_tax": -self._latent_tax(),
        }
