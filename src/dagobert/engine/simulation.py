"""Monthly wealth simulation, vectorized over return paths: the month loop of `Engine` and its
result."""

from __future__ import annotations

from datetime import date

import numpy as np
from numpy.typing import NDArray

from dagobert import anatomy
from dagobert.engine.core import pays
from dagobert.engine.events import Events
from dagobert.engine.settlement import Settlement
from dagobert.engine.state import MonthFlows, MonthState, YearAcc
from dagobert.model.assumptions import Assumptions
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Plan
from dagobert.result import BALANCE_CLASSES, LIQUID, MEDIAN_BAND, FloatArray, RunResult
from dagobert.returns import FixedProvider, Returns


class Engine(Events, Settlement):
    """A run of a plan. `Core` holds its state, `Portfolio`, `Income`, `Events` and `Settlement`
    the steps of a month, `run` the months in their order."""

    def run(self) -> RunResult:
        n, p = self.n_months, self.paths
        months = [add_months(self.start, i) for i in range(n)]
        liquid, total, income, expenses, taxes, capital_taxes = (np.zeros((p, n)) for _ in range(6))
        balance, nominal_balance = (np.zeros((len(BALANCE_CLASSES), n)) for _ in range(2))
        phases: list[str] = []
        paid: list[bool] = []  # by the static predicate of the spending rule's first month
        last_phase: str | None = None
        for i, month in enumerate(months):
            phase = self.plan.phase_at(month)
            self.m = MonthState(i, month, phase)
            self.flows = MonthFlows.new(p)
            for pool in self.pools.values() if i else ():
                pool.age(i)
            if i and month.month == 1:
                self.kv_last = self._kv_last()
                self.acc = YearAcc.new(
                    self.equity, self.eq_index[:, i - 1], self.a.tax.sparer_pauschbetrag
                )
            liquid_prev = liquid[:, i - 1] if i else liquid_of(self._balance())
            self._update_spending_rule(liquid_prev)
            self._check_triggers(liquid_prev)
            if phase != last_phase:
                self._mark("phase", self.a.phase_labels[phase])
                last_phase = phase
            self._apply_events()
            paid.append(
                any(
                    s.active(month, phase) and pays(s.spec, self.a, phase, s.factor_override)
                    for s in self.streams
                )
            )
            self._apply_returns()
            self._pay_matured_deposits()
            self.cash_mark = self.cash.copy()  # VPW: what the month draws from here on
            self._service_loans()
            self._apply_streams()
            self._take_afa()
            self._save_plans()
            self._cover_deficit()
            self._rebalance()
            if month.month == 12 or i == n - 1:
                self._contribute_av()
                self._settle_december()
            self._invest_surplus()  # last, so the December bill comes out of cash
            parts = self._balance()
            classes = np.array([parts[c] for c in BALANCE_CLASSES])
            liquid[:, i] = liquid_of(parts)
            total[:, i] = classes.sum(axis=0)
            nominal_balance[:, i] = band_mean(classes, total[:, i])
            balance[:, i] = band_mean(classes / self.cpi[:, i], total[:, i] / self.cpi[:, i])
            income[:, i], expenses[:, i] = self.flows.income, self.flows.expenses
            taxes[:, i], capital_taxes[:, i] = self.flows.taxes, self.flows.capital_taxes
            phases.append(phase)
        result = RunResult(
            scenario=self.plan.scenario.name,
            note=self.plan.scenario.note,
            model=self.model,
            months=months,
            ages=np.array([self._age(i) for i in range(n)]),
            phases=phases,
            phase_labels=self.a.phase_labels,
            liquid=liquid,
            total=total,
            income=income,
            expenses=expenses,
            taxes=taxes,
            capital_taxes=capital_taxes,
            broke=liquid < 0,
            reduced=self.months_cut,
            raised=self.months_raised,
            care=self.care,
            onset=self.onset,
            em=self.pension.em,
            cpi=self.cpi.astype(np.float32),
            markers=self.markers,
            balance=dict(zip(BALANCE_CLASSES, balance, strict=True)),
            nominal_balance=dict(zip(BALANCE_CLASSES, nominal_balance, strict=True)),
            ledger=self.ledger,
            pay_ends=pay_ends(paid),
        )
        result.drivers = anatomy.drivers(
            result, self._class_levels(), self._stream_indices(), self._inherited()
        )
        return result

    def _inherited(self) -> dict[str, NDArray[np.intp]]:
        """The month index per path of each inheritance without a month, by the labels of its
        givers."""
        labels = self.a.person.relative_labels
        return {
            ", ".join(labels[key] for key in got.event.givers): got.month
            for got in self.acquisitions
            if got.event.at is None
        }

    def _class_levels(self) -> dict[str, FloatArray]:
        """Levels of equity and of the return classes of the gold and crypto assets, before
        their custody cost."""
        rates = self.returns.rates
        return {"equity": self.eq_index} | {
            cls: np.cumprod(1 + rates[cls], axis=1)
            for cls in dict.fromkeys(pool.spec.growth for pool in self.pools.values())
            if cls != "equity"
        }

    def _stream_indices(self) -> dict[str, FloatArray]:
        """Levels of the growth indices that a stream or the care cost follows."""
        used = {s.spec.index for s in self.streams} | {self.a.care.index if self.a.care else None}
        return {
            name: self.returns.indices[name]
            for name, spec in self.a.indices.items()
            if spec.cumulative and name in used
        }


def liquid_of(parts: dict[str, FloatArray]) -> FloatArray:
    """The liquid net worth of the classes of a balance sheet."""
    return np.sum([parts[c] for c in LIQUID], axis=0)


def band_mean(classes: FloatArray, total: FloatArray) -> FloatArray:
    """Mean of each row of `classes` over the paths whose `total` lies inside MEDIAN_BAND."""
    low, high = np.percentile(total, MEDIAN_BAND)
    return np.asarray(classes[:, (total >= low) & (total <= high)].mean(axis=1))


def pay_ends(paid: list[bool]) -> int:
    """The month after the last paid one. 0 without pay, with pay to the end or up to the month
    before it: one point is no chart."""
    ends = max((i for i, p in enumerate(paid) if p), default=-1) + 1
    return 0 if ends >= len(paid) - 1 else ends


def horizon_months(a: Assumptions) -> int:
    end = add_months(a.person.born, 12 * a.person.horizon_age)
    return max(months_between(a.start, end), 1)


def simulate(plan: Plan, returns: Returns, model: str) -> RunResult:
    return Engine(plan, returns, model).run()


def before(plan: Plan, until: date) -> Engine | None:
    """A `fixed` run of `plan` from its start through the month before `until`, for what it
    built by then (the roll forward): the first month of a business (`Core.first_profit`), the
    founding that the engine takes without `tax.self_employed.founded`, and the Verlustvortrag
    (`Core.income_losses`). None when `until` is not after the start."""
    months = months_between(plan.assumptions.start, until)
    if months <= 0:
        return None
    engine = Engine(plan, FixedProvider(plan.assumptions).sample(months), "fixed")
    engine.run()
    return engine
