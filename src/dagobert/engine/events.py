"""The events of a scenario in the month they fall in, and the sales on a condition."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from dagobert import tax
from dagobert.engine.income import Income
from dagobert.engine.portfolio import Portfolio
from dagobert.engine.state import Acquisition, LoanState, PolicyState
from dagobert.model.assets import EquityAsset, PropertyAsset
from dagobert.model.events import (
    Acquired,
    AddStreamEvent,
    BuyEvent,
    BuyPropertyEvent,
    EndStreamsEvent,
    Event,
    FundPolicyEvent,
    InheritanceEvent,
    LumpSumEvent,
    PolicyFunding,
    RepayAction,
    RepayEvent,
    SellEvent,
    SetStreamEvent,
    SeveranceEvent,
    WriteOffEvent,
)
from dagobert.result import (
    EQUITY,
    GIFT,
    GIFT_TAX,
    INHERITANCE,
    INHERITANCE_TAX,
    LOAN,
    LUMP_SUM,
    MOVE_IN,
    MOVED,
    NONCASH,
    ONEOFF_CONTRIBUTION,
    ONEOFF_IN,
    ONEOFF_OUT,
    ONEOFF_TAX,
    PREMIUM,
    PURCHASE,
    PURCHASE_COSTS,
    SALE,
    SEVERANCE,
    TRANSFER_TAX,
    WRITE_OFF,
    BoolArray,
    FloatArray,
    MarkerForm,
)
from dagobert.returns import generator


class Events(Income, Portfolio):
    def _apply_events(self) -> None:
        """The inheritances and gifts of the month, then its other events in file order."""
        self._check_acquisitions()
        for ev in self.events[self.m.i]:
            self._apply_event(ev)

    def _apply_event(self, ev: Event) -> None:
        if ev.at is not None and ev.at >= self.start:  # a stream event before it marks nothing
            self._mark(ev.type, ev.detail)
        match ev:
            case SellEvent():
                self._sell(ev, np.ones(self.paths, dtype=bool))
            case BuyEvent():
                self._buy(ev)
            case BuyPropertyEvent():
                self._buy_property(ev)
            case RepayEvent():
                self._repay(ev.loan, ev.amount)
            case SeveranceEvent():
                self._severance_event(ev)
            case FundPolicyEvent():
                self._fund_from_cash(ev)
            case LumpSumEvent():
                self._lump_sum(ev)
            case WriteOffEvent():
                self._write_off(ev)
            case EndStreamsEvent():
                self._end_streams(ev)
            case SetStreamEvent():
                self._set_stream(ev)
            case AddStreamEvent():
                self.streams.append(self._stream_state(ev.stream))

    def _check_acquisitions(self) -> None:
        """The inheritances and gifts on the paths whose month this is. The marker falls in the
        month in which half of the paths have received one, of a dated one in its month."""
        for got in self.acquisitions:
            due = got.month == self.m.i
            if not due.any():
                continue
            before = got.done.mean()
            got.done |= due
            amount = self._acquire(got, due)
            if before < 0.5 <= got.done.mean():
                form: MarkerForm = "" if got.done.all() else "half"
                self._mark(got.event.type, self._givers(got.event), amount=amount, form=form)

    def _givers(self, ev: Acquired) -> str:
        """The marker of an inheritance or a gift: its note, else the labels of its givers."""
        labels = self.a.person.relative_labels
        return ev.note or ", ".join(labels[key] for key in ev.givers)

    def _acquire(self, got: Acquisition, due: NDArray[np.bool_]) -> float:
        """The cash and securities of an inheritance or a gift on the paths `due`, with the gifts
        that join an estate on the paths of each, less the Erbschaftsteuer of the giver of each
        path, nominal (§14 ErbStG: with what the giver gave within ten years, `Received`). The
        securities join the equity at the index of the month before its return, with the giver's
        basis. No income tax, no health insurance. Returns the median that they received."""
        ev = got.event
        parts = [(ev, due), *((gift, due & waits) for gift, waits in got.joined)]
        price = self.eq_price
        cash = sum((np.where(on, e.cash, 0.0) for e, on in parts), np.zeros(self.paths))
        securities = [(e.equity, on) for e, on in parts if e.equity is not None]
        value = sum(
            (np.where(on, s.value * price, 0.0) for s, on in securities), np.zeros(self.paths)
        )
        basis = sum((np.where(on, s.cost_basis, 0.0) for s, on in securities), np.zeros(self.paths))
        acquired, owed = cash + value, np.zeros(self.paths)
        inherited = isinstance(ev, InheritanceEvent)
        for k, key in enumerate(ev.givers):
            mine = due & (got.giver == k)
            if not mine.any():
                continue
            given, relation = self.received[key], self.a.person.relatives[key].relation
            levied = tax.erbschaftsteuer(
                acquired, *given.prior(self.m.i), relation, self.ty, inheritance=inherited
            )
            owed = np.where(mine, levied, owed)
            given.record(ev, mine, self.m.i, acquired, owed)
        self._receive(cash, owed)
        self._buy_equity(value, basis=basis)
        label = self.a.person.relative_labels[ev.givers[int(got.giver[0])]]
        group, word = (INHERITANCE, INHERITANCE_TAX) if inherited else (GIFT, GIFT_TAX)
        self._note(ONEOFF_IN, group, label, cash)
        self._note(ONEOFF_OUT, ONEOFF_TAX, f"{label}: {word}", owed)
        self._note(NONCASH, ONEOFF_CONTRIBUTION, f"{label}: {EQUITY}", value)
        return float(np.median(acquired[due]))

    def _end_streams(self, ev: EndStreamsEvent) -> None:
        for s in self.streams:
            if s.spec.name in ev.names or set(s.spec.tags) & set(ev.tags):
                s.end = self.m.month

    def _write_off(self, ev: WriteOffEvent) -> None:
        """The depots are one pool: the asset leaves with its start value at today's index, and
        the taxable share and basis of the pool lose its part after its Teilfreistellung."""
        spec = next(x for x in self.plan.assets if x.id == ev.asset and isinstance(x, EquityAsset))
        grown = spec.value * (self.eq_index[:, self.m.i - 1] if self.m.i else 1.0)
        taken = np.minimum(grown, self.equity)
        kept, taxed = self.equity - taken, 1 - self.exempt[spec.id]
        # the start value at the index ignores the sales since: keep the share a share
        self.taxable_share = np.clip(
            np.divide(
                self.equity * self.taxable_share - taken * taxed,
                kept,
                out=self.taxable_share.copy(),
                where=kept > 0,
            ),
            0.0,
            1.0,
        )
        self.taxable_basis -= np.minimum(spec.basis * taxed, self.taxable_basis)
        self.equity = kept
        self._note(MOVED, WRITE_OFF, spec.label, -taken)

    def _severance_event(self, ev: SeveranceEvent) -> None:
        """The tax-free part in `bav` goes into the policy without passing the cash."""
        self._severance(ev.gross - self._fund(ev.bav))
        if ev.bav is not None:
            self._note(
                NONCASH,
                ONEOFF_CONTRIBUTION,
                f"{self._policy(ev.bav.policy).spec.label}: {SEVERANCE}",
                ev.bav.amount,
            )

    def _lump_sum(self, ev: LumpSumEvent) -> None:
        self._receive(ev.amount)
        self._note(ONEOFF_IN, LUMP_SUM, ev.note or LUMP_SUM, ev.amount)
        if ev.taxable:
            self.acc.other_taxable += ev.amount / self.deflator
            self.acc.kv_oneoff += ev.amount / self.deflator

    def _set_stream(self, ev: SetStreamEvent) -> None:
        named = [s for s in self.streams if s.spec.name == ev.name]
        for k in ev.targets([(s.spec.start, s.end) for s in named]):
            named[k].spec = ev.applied(named[k].spec)
            if ev.factor is not None:
                named[k].factor_override = ev.factor

    def _fund_from_cash(self, ev: FundPolicyEvent) -> None:
        """A premium into a Basisrente (`Plan` refuses another policy): an Altersvorsorgeaufwand
        (§10 Abs. 1 Nr. 2 b EStG)."""
        self.cash -= self._fund(ev)
        self._note_move(PREMIUM, self._policy(ev.policy).spec.label, ev.amount)
        self.acc.rv_paid += ev.amount / self.deflator

    def _check_triggers(self, liquid_prev: FloatArray) -> None:
        """Conditional sales fire per path, once, on age or on liquid drawdown."""
        for ev, fired in self.conditional:
            owned = ev.asset in self.properties or ev.asset in self.pools  # a purchase may follow
            if ev.when is None or fired.all() or not owned:
                continue
            hit = np.zeros(self.paths, dtype=bool)
            if ev.when.age is not None:
                hit |= self._age(self.m.i) >= ev.when.age
            if ev.when.liquid_below is not None:
                hit |= liquid_prev < ev.when.liquid_below * self.deflator
            hit &= ~fired
            if ev.asset in self.properties:
                hit &= ~self.properties[ev.asset].sold
            if not hit.any():
                continue
            before = fired.mean()
            fired[hit] = True
            self._sell(ev, hit)
            if before < 0.5 <= fired.mean():
                self._mark("sell", ev.detail, form="" if fired.all() else "half")

    def _sell(self, ev: SellEvent, mask: BoolArray) -> None:
        if ev.asset in self.pools:
            self._sell_holding(ev, mask)
        else:
            self._sell_property(ev, mask)

    def _sell_holding(self, ev: SellEvent, mask: BoolArray) -> None:
        """`share` of the gold or crypto, the oldest units first. It ends no streams."""
        pool = self.pools[ev.asset]
        before = pool.value
        taken = pool.take(np.where(mask, ev.share * pool.units, 0.0), self.m.i, ev.costs)
        self._note(MOVE_IN, SALE, pool.spec.label, taken.proceeds)
        self._note(MOVED, SALE, pool.spec.label, pool.value - before)
        self._then(ev, self._cash_in(taken))

    def _buy(self, ev: BuyEvent) -> None:
        """Euros from cash into gold or crypto at the price of the month."""
        pool = self.pools[ev.asset]
        pool.buy(ev.amount, self.m.i, self.m.month)
        self.cash -= ev.amount
        self._note_move(PURCHASE, pool.spec.label, ev.amount)

    def _buy_property(self, ev: BuyPropertyEvent) -> None:
        """The price, the Grunderwerbsteuer and the costs from cash, the loan into it. The
        property is worth the price on every path, its basis for §23 EStG is all it cost."""
        bought, at = ev.property, ev.at
        transfer_tax, costs = ev.price * ev.transfer_rate, ev.price * ev.costs
        spec = PropertyAsset(  # one m² at the price
            kind="property",
            id=bought.id,
            name=bought.name,
            tags=bought.tags,
            sqm=1,
            per_sqm=ev.price,
            bought_for=ev.cost,
            growth=bought.growth,
            upkeep=bought.upkeep,
            bought=at,
            building_share=bought.building_share,
            afa=bought.afa,
        )
        self.properties[bought.id] = self._property(spec, np.full(self.paths, ev.price))
        self.cash -= ev.cost
        self.flows.taxes -= transfer_tax
        self.flows.expenses -= costs
        self._note_move(PURCHASE, spec.label, ev.price)
        self._note(ONEOFF_OUT, ONEOFF_TAX, f"{spec.label}: {TRANSFER_TAX}", transfer_tax)
        self._note(ONEOFF_OUT, PURCHASE_COSTS, spec.label, costs)
        if ev.loan is not None:
            loan = ev.loan.taken(at)
            self.loans.append(LoanState(loan, loan.balance, since=self.m.i + 1, finances=bought.id))
            self.cash -= loan.balance
            self._note(MOVE_IN, LOAN, loan.label, -loan.balance)
            self._note(MOVED, LOAN, loan.label, loan.balance)

    def _sell_property(self, ev: SellEvent, mask: BoolArray) -> None:
        """A `taxable` sale within `property_sale_months` of the purchase (any time for a
        property of the file without `bought`) is a private sale (§23 EStG): its basis is what
        the purchase cost less the AfA taken (Abs. 3 S. 4), the penalty of a repayment from the
        proceeds a cost of the sale (BFH IX R 42/13). It ends the streams that name the property,
        with `end_tagged` also those that share a tag with it."""
        prop = self.properties[ev.asset]
        price = np.full(self.paths, ev.price) if ev.price is not None else prop.value
        if ev.price_stdev and self.paths > 1:  # one draw per path and asset: it sells once
            # lognormal: the price keeps its mean and its relative spread, and stays above zero
            spread = np.sqrt(np.log1p(ev.price_stdev**2))
            z = generator(self.a.seed, f"sale.{ev.asset}").standard_normal(self.paths)
            price = price * np.exp(spread * z - spread**2 / 2)
        sold_now = mask & ~prop.sold  # also at a price of 0, a gift
        proceeds = np.where(sold_now, price * (1 - ev.costs), 0.0)
        self.cash += proceeds
        self._note(MOVE_IN, SALE, prop.spec.label, proceeds)
        self._note(MOVED, SALE, prop.spec.label, -np.where(sold_now, prop.held, 0.0))
        prop.sold |= sold_now
        penalty = self._then(ev, proceeds)
        months_held = None if prop.bought is None else self.m.i - prop.bought
        if (
            ev.taxable
            and prop.spec.bought_for is not None
            and (months_held is None or months_held <= self.ty.property_sale_months)
        ):
            # §23 Abs. 3 S. 7 EStG: a loss offsets other private sales only, never the salary
            basis = prop.spec.bought_for - prop.afa_taken
            gain = np.where(sold_now, proceeds - penalty - basis, 0.0)
            self.acc.private_sales += gain / self.deflator
        for s in self.streams:
            tagged = ev.end_tagged and set(s.spec.tags) & set(prop.spec.tags)
            if tagged or s.spec.property == ev.asset:
                s.mask = s.mask * ~sold_now
            if s.spec.after_sale_of == ev.asset:
                s.mask = np.maximum(s.mask, sold_now)

    def _then(self, ev: SellEvent, left: FloatArray) -> float:
        """Repay loans from the proceeds `left`, then invest what is left of them: the cash
        buffer stays. Returns the penalties of the repayments."""
        penalties = 0.0
        for action in ev.then:
            if isinstance(action, RepayAction):
                pay, penalty = self._repay(action.repay, action.amount)
                left, penalties = left - pay - penalty, penalties + penalty
            else:
                self._invest(np.clip(left, 0.0, np.maximum(self.cash, 0.0)))
        return penalties

    def _policy(self, policy_id: str) -> PolicyState:
        """The policy that takes funding: known and not paid out."""
        pol = next((p for p in self.policies if p.spec.id == policy_id), None)
        if pol is None or pol.done:
            msg = f"cannot fund policy {policy_id!r}: unknown or already paid out"
            raise ValueError(msg)
        return pol

    def _fund(self, funding: PolicyFunding | FundPolicyEvent | None) -> float:
        """Add a lump sum to a policy's capital; returns the amount, 0 without funding."""
        if funding is None:
            return 0.0
        pol = self._policy(funding.policy)
        pol.value = pol.value + funding.amount
        pol.paid += funding.amount
        return funding.amount
