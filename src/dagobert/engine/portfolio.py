"""The holdings of a run: the returns of the month, the savings plans, what the surplus buys and
a deficit sells, the rebalancing, and the flat tax of a sale."""

from __future__ import annotations

from datetime import date

import numpy as np

from dagobert import tax
from dagobert.engine.core import Core
from dagobert.engine.state import AvState, PolicyState
from dagobert.holdings import Pool, Taken
from dagobert.model.assets import TermDeposit
from dagobert.model.months import add_months
from dagobert.model.streams import StreamKind
from dagobert.result import (
    CAPITAL_TAX,
    CASH,
    EQUITY,
    FIXED_INCOME,
    MOVE_OUT,
    NONCASH,
    SAVINGS_PLAN,
    TAX,
    FloatArray,
)
from dagobert.returns import grown


class Portfolio(Core):
    def _apply_returns(self) -> None:
        """The month's return of every pool, property, policy and depot."""
        r = self.returns.rates
        i = self.m.i
        if self.ledger is not None:
            self._note_growth()
        self.equity *= 1 + r["equity"][:, i]
        self.eq_price = self.eq_index[:, i]
        earned = np.maximum(self.cash, 0) * r["cash"][:, i] + self.fixed * r["fixed_income"][:, i]
        self.acc.interest += earned / self.deflator
        self.cash *= 1 + r["cash"][:, i]
        self.fixed *= 1 + r["fixed_income"][:, i]
        for prop in self.properties.values():
            prop.value = prop.value * (1 + r[prop.spec.growth][:, i])
        for pol in self.policies:
            if not pol.done:
                pol.value = grown(pol.value, r[pol.spec.growth][:, i], pol.spec.cost)
        for av in self.av:
            av.value = grown(av.value, r[av.spec.growth][:, i], av.spec.cost)
        for pool in self.pools.values():
            pool.price = grown(pool.price, r[pool.spec.growth][:, i], pool.spec.cost)

    def _pay_matured_deposits(self) -> None:
        """A term deposit that matures this month pays: its interest owes the flat tax, the net
        goes into the bucket or the cash, and the deposit is gone."""
        for did, deposit in list(self.deposits.items()):
            if due := self._due(deposit):
                paid = deposit.value_at(due)
                interest_tax = self._flat_tax(np.full(self.paths, paid - deposit.value))
                self._report_capital_tax(interest_tax)
                net = paid - interest_tax
                if self.a.allocation:
                    self.fixed += net
                else:
                    self.cash += net
                del self.deposits[did]

    def _note_growth(self) -> None:
        """The growth of every asset in this month, before `_apply_returns` adds it. A term
        deposit grows by what `_deposits` counts more than in the month before, in its last
        month up to what it pays: its months add up to what it pays beyond its value at the
        start. A policy that paid out grows no more."""
        rate = {name: rates[:, self.m.i] for name, rates in self.returns.rates.items()}
        before = add_months(self.m.month, -1) if self.m.i else self.m.month
        # both lists typed: mypy joins the states, and the tuples, to `object`
        growing: list[PolicyState | AvState | Pool] = [
            *(p for p in self.policies if not p.done),
            *self.av,
            *self.pools.values(),
        ]
        gains: list[tuple[str, str, FloatArray | float]] = [
            ("equity", EQUITY, self.equity * rate["equity"]),
            ("fixed_income", FIXED_INCOME, self.fixed * rate["fixed_income"]),
            ("cash", CASH, self.cash * rate["cash"]),
            *(
                (d.kind, d.label, d.value_at(self._due(d) or self.m.month) - d.value_at(before))
                for d in self.deposits.values()
            ),
            *(
                ("property", p.spec.label, p.held * rate[p.spec.growth])
                for p in self.properties.values()
            ),
            *(
                (
                    h.spec.kind,
                    h.spec.label,
                    grown(h.value, rate[h.spec.growth], h.spec.cost) - h.value,
                )
                for h in growing
            ),
        ]
        for group, item, gain in gains:
            self._note(NONCASH, group, item, gain)

    def _due(self, deposit: TermDeposit) -> date | None:
        """The maturity of `deposit` when it pays this month."""
        return deposit.matures if self.m.month >= deposit.matures.replace(day=1) else None

    def _save_plans(self) -> None:
        """The savings plans that pay this month, in file order, from the cash into their
        assets, ignoring the cash buffer. A path whose cash does not cover the rate skips it, as
        a broker skips an execution: no deficit cover and no catch-up. A marker names the first
        month in which half of the paths skip a plan."""
        for s in self.streams:
            spec = s.spec
            if spec.kind != StreamKind.SAVINGS or not self._pays(s):
                continue
            due = -self._nominal(s) * self.a.scale.savings.get(spec.name, 1.0)
            paid = np.where(self.cash >= due, due, 0.0)
            self.cash -= paid
            self._put(spec.into, paid)
            self._note_move(SAVINGS_PLAN, spec.name, paid)
            self._spread((MOVE_OUT, SAVINGS_PLAN, spec.name), paid, spec.every)
            if spec.name not in self.paused and (due > paid).mean() >= 0.5:
                self.paused.add(spec.name)
                self._mark("savings plan", spec.name)

    def _put(self, into: str | None, amount: FloatArray) -> None:
        """Euros from the cash into the asset `into` of a savings plan, by default equity."""
        if into in self.pools:
            self.pools[into].buy(amount, self.m.i, self.m.month)
        elif into in self.bucket:
            self.fixed += amount
        else:
            self._buy_equity(amount, into)

    def _invest_surplus(self) -> None:
        if not self.a.invest_rest:
            return
        buffer = self.a.cash_buffer_months * -self._run_rate(StreamKind.EXPENSE)
        self._invest(np.maximum(self.cash - buffer, 0))

    def _cover_deficit(self) -> None:
        deficit = np.maximum(-self.cash, 0)
        take = np.minimum(deficit, self.fixed)
        self.fixed -= take
        self.cash += take
        deficit -= take
        self._sell_equity(deficit)
        self._sell_holdings()

    def _sell_holdings(self) -> None:
        """Cover what equity left with gold and crypto, the pools in file order: first the free
        units of every pool, then the rest of each, the young rows at face value (their tax
        comes with the settlement) and the §20 part grossed up for the flat tax."""
        if not (self.cash < 0).any():
            return
        for pool in self.pools.values():
            self._sell_units(pool, np.minimum(np.maximum(-self.cash, 0) / pool.price, pool.aged))
        for pool in self.pools.values():
            deficit = np.maximum(-self.cash, 0)
            young = np.minimum(deficit / pool.price, pool.young.sum(axis=0))
            gross = (deficit - young * pool.price) / (1 - self.flat_rate * pool.gain_share)
            self._sell_units(pool, young + np.minimum(gross / pool.price, pool.capital))

    def _sell_units(self, pool: Pool, units: FloatArray) -> None:
        """Most months the paths in deficit hold no units: nothing to sell."""
        if units.any():
            self._cash_in(pool.take(units, self.m.i))

    def _cash_in(self, taken: Taken) -> FloatArray:
        """The proceeds of gold or crypto into cash. A gain within the holding period joins the
        private sales of the year, the §20 part pays the flat tax at once, without
        Teilfreistellung. Returns the proceeds less that tax."""
        self.acc.private_sales += taken.private_gain / self.deflator
        net = taken.proceeds
        if taken.capital_proceeds.any():
            flat = self._flat_tax(taken.capital_proceeds - taken.capital_basis)
            self._report_capital_tax(flat)
            net = net - flat
        self.cash += net
        return net

    def _flat_tax(self, gain: FloatArray, *, vorab: bool = False) -> FloatArray:
        """Nominal Abgeltungsteuer on a nominal gain, of a fund after its Teilfreistellung. A
        loss goes into the loss pot, which carries over the years. It uses up the Pauschbetrag
        and keeps the flat-taxed income for the Günstigerprüfung in December, and before the
        Pauschbetrag for the freiwillige KV of the next year: `vorab`, the Vorabpauschale, apart
        (`Health._kv_last`)."""
        left = self.acc.pauschbetrag_left
        t, self.acc.pauschbetrag_left, self.losses = tax.capital_gains_tax(
            gain / self.deflator,
            self.acc.pauschbetrag_left,
            self.a.tax,
            self.ty,
            losses=self.losses,
        )
        self.acc.capital_tax_paid += t
        self.acc.capital_income += t / self.flat_rate
        kv = t / self.flat_rate + left - self.acc.pauschbetrag_left
        if vorab:
            self.acc.kv_vorab += kv
        else:
            self.acc.kv_capital += kv
        return t * self.deflator

    def _report_capital_tax(self, nominal: FloatArray, *, since: int | None = None) -> None:
        self.flows.capital_taxes -= nominal
        self._note(TAX, "", CAPITAL_TAX, nominal, since=since)

    def _invest(self, amount: FloatArray) -> None:
        """Move cash into the portfolio, split by the fixed-income target share."""
        share = self._fixed_share()
        self.fixed += amount * share
        self._buy_equity(amount * (1 - share))
        self.cash -= amount

    def _buy_equity(
        self, amount: FloatArray, depot: str | None = None, basis: FloatArray | None = None
    ) -> None:
        """The one purchase of equity, at the Teilfreistellung of `depot`, by default that of the
        assumptions, its basis `amount` or the `basis` that an heir takes over (§20 Abs. 4 S. 6
        EStG). Its units count in January euros, at the price of now, and their Vorabpauschale of
        the year in twelfths: the month of the purchase and the months after it (§18 Abs. 2
        InvStG)."""
        kept = 1 - self.exempt[depot]
        total = self.equity + amount
        self.taxable_share = np.divide(
            self.equity * self.taxable_share + amount * kept,
            total,
            out=self.taxable_share.copy(),
            where=total > 0,
        )
        self.taxable_basis += (amount if basis is None else basis) * kept
        self.equity += amount
        units = amount * self.acc.index_jan / self.eq_price
        self.acc.bought += units
        self.acc.weighted += units * (13 - self.m.month.month) / 12

    def _sell_equity(self, amount: FloatArray) -> None:
        """Sell enough equity to net `amount` after capital gains tax: a slice of every depot."""
        safe = np.where(self.equity > 0, self.equity, 1.0)
        taxed = self.taxable_gain / safe  # per euro sold, negative: the sale realizes a loss
        sell = np.minimum(amount / (1 - self.flat_rate * np.maximum(taxed, 0)), self.equity)
        t = self._flat_tax(sell * taxed)
        self.taxable_basis -= self.taxable_basis * sell / safe
        self.equity -= sell
        self.cash += sell - t
        self._report_capital_tax(t)

    def _rebalance(self) -> None:
        """Move towards the target fixed-income share. Shifts out of equity only after gains."""
        alloc = self.a.allocation
        i = self.m.i
        if alloc is None or i == 0 or i % alloc.rebalance_every:
            return
        target = self._fixed_share() * (self.equity + self.fixed)
        excess = np.maximum(self.fixed - target, 0)
        self.fixed -= excess
        self._buy_equity(excess)
        lookback = max(i - alloc.skip_after_loss, 0)
        gained = self.eq_index[:, i] >= self.eq_index[:, lookback]
        shortfall = np.where(gained, np.maximum(target - self.fixed, 0), 0)
        cash_before = self.cash.copy()
        self._sell_equity(shortfall)
        self.fixed += self.cash - cash_before
        self.cash = cash_before
