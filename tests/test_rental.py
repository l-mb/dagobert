"""Letting a property (§21 EStG): the rent net of the AfA, the interest, the upkeep and the costs
that name the property, the Verlustvortrag (§10d EStG), the AfA off the basis of a sale (§23 Abs. 3
S. 4) and the GKV on the net rent. Relations between runs of small plans with zero returns: a cost
lowers the tax as much as a rent lower by it."""

from dataclasses import replace
from datetime import date
from typing import Any

import pytest
from builders import booked, plan, purchase, zero_returns, zero_run

from dagobert.engine.simulation import simulate
from dagobert.model.assets import CashAsset, Loan, PropertyAsset, TermDeposit
from dagobert.model.events import EndStreamsEvent, InvestAction, RepayAction, SellEvent
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import LOAN_INTEREST, SPENDING, RunResult
from dagobert.tax import YearIncome, for_year, income_tax, year_settlement

TY = for_year(2026)
CASH = CashAsset(id="c", kind="cash", value=600_000)
SALARY = Stream(name="Gehalt", kind=StreamKind.SALARY, gross=6000, index=None)
YEAR, NEXT = slice(0, 12), slice(12, 24)
BASE = 250_000 * 0.8  # what the building cost


def flat(**kw: object) -> PropertyAsset:
    """A flat worth 300,000 €, bought in 2020-01 for 250,000 € with its costs, 80% of it the
    building, 2% AfA, no upkeep."""
    fields = {"id": "flat", "kind": "property", "sqm": 60, "per_sqm": 5000}
    let = {"bought_for": 250_000, "bought": date(2020, 1, 1), "building_share": 0.8, "afa": 0.02}
    return PropertyAsset.model_validate(fields | let | kw)


def rent(amount: float = 1000.0, **kw: object) -> Stream:
    """The rent of the flat, nominal."""
    fields = {"name": "Miete", "kind": "other_income", "amount": amount, "index": None}
    return Stream.model_validate(fields | {"property": "flat"} | kw)


def other(amount: float, **kw: object) -> Stream:
    """Taxable other income that lets nothing, nominal."""
    return Stream.model_validate(
        {"name": "Zins", "kind": "other_income", "amount": amount, "index": None} | kw
    )


def run(
    streams: list[Stream],
    assets: list[Any],
    scenario: Scenario | None = None,
    months: int = 12,
    **kw: object,
) -> RunResult:
    return zero_run(plan(streams, [CASH, *assets], scenario, **kw), months)


def taxed(r: RunResult, months: slice = YEAR) -> float:
    """The income tax, Soli and SV of the months."""
    return float(-r.taxes[0, months].sum())


def test_a_let_rent_pays_the_tax_of_its_net() -> None:
    """The rent of a let flat less its AfA (§7 Abs. 4 S. 1 Nr. 2 EStG), upkeep and Hausgeld
    (§9 Abs. 1 S. 3 EStG) is taxed like other income of that net, and the cash stays the
    same."""
    upkeep, hausgeld = 0.01, -200.0
    costs = BASE * 0.02 / 12 + 300_000 * upkeep / 12 - hausgeld
    cost = Stream(name="Hausgeld", cat="flat", amount=hausgeld, index=None, property="flat")
    let = run([SALARY, rent(), cost], [flat(upkeep=upkeep)])
    plain = run([SALARY, other(1000), cost.model_copy(update={"property": None})], [flat()])
    net = run([SALARY, other(1000 - costs)], [flat()])
    assert taxed(let) == pytest.approx(taxed(net), abs=1)
    assert taxed(let) < taxed(plain) - 0.3 * 12 * costs
    assert let.income[0] == pytest.approx(plain.income[0])
    assert let.expenses[0] == pytest.approx(plain.expenses[0] - 300_000 * upkeep / 12)


def test_the_interest_of_the_loan_that_financed_the_flat_is_a_cost() -> None:
    """§9 Abs. 1 S. 3 Nr. 1 EStG: `finances` takes the interest off the rent, the cash flows are
    those of the loan without it."""
    loan = {"id": "l", "kind": "loan", "balance": -120_000, "rate": 0.03, "annuity": 800}
    financed = run([SALARY, rent()], [flat(), Loan.model_validate(loan | {"finances": "flat"})])
    alone = run([SALARY, rent()], [flat(), Loan.model_validate(loan)])
    interest = float(booked(alone, "l", SPENDING, LOAN_INTEREST)[YEAR].sum())
    assert interest > 3000
    lower = run([SALARY, rent(1000 - interest / 12)], [flat(), Loan.model_validate(loan)])
    assert taxed(financed) == pytest.approx(taxed(lower), abs=1)
    assert financed.expenses[0] == pytest.approx(alone.expenses[0])


@pytest.mark.parametrize(
    ("let", "same"),
    [
        ({"building_share": 1.0}, {"building_share": 0.5, "rent": 1000 - 250_000 * 0.01 / 12}),
        ({"afa": 0.03}, {"afa": 0.02, "rent": 1000 - BASE * 0.01 / 12}),
        ({"bought": date(1975, 1, 1)}, {"afa": 0.0, "rent": 1000.0}),  # depreciated by 2025
    ],
    ids=["building share", "rate", "done"],
)
def test_the_afa_takes_the_rate_of_the_building_share_of_the_cost(
    let: dict[str, object], same: dict[str, Any]
) -> None:
    """A rate on the building share of `bought_for`, for 50 years at 2%: one AfA is a rent lower
    by the difference."""
    amount = same.pop("rent")
    assert taxed(run([SALARY, rent()], [flat(**let)])) == pytest.approx(
        taxed(run([SALARY, rent(amount)], [flat(**same)])), abs=1
    )


@pytest.mark.parametrize(
    "ends",
    [
        EndStreamsEvent(type="end_streams", at=date(2027, 1, 1), names=["Miete"]),
        SellEvent(type="sell", at=date(2027, 1, 1), asset="flat"),  # the rent has no tag
    ],
    ids=["end_streams", "sale"],
)
def test_the_end_of_the_rent_ends_the_costs(ends: EndStreamsEvent | SellEvent) -> None:
    """A property is let while a rent names it: own use is `end_streams`, and a sale ends the
    streams that name it, tag or no tag. After it neither the AfA nor the Hausgeld count."""
    cost = Stream(name="Hausgeld", cat="flat", amount=-300, index=None, property="flat")
    after = run([SALARY, rent(), cost], [flat()], Scenario(name="t", events=[ends]), months=24)
    never = run([SALARY, cost], [flat()], months=24)
    assert taxed(after, NEXT) == pytest.approx(taxed(never, NEXT), abs=1)
    assert after.income[0, NEXT] == pytest.approx(never.income[0, NEXT])


@pytest.mark.parametrize(("bought", "more"), [(date(2020, 1, 1), True), (date(2015, 1, 1), False)])
def test_a_taxable_sale_of_a_let_flat_counts_the_afa_taken(bought: date, *, more: bool) -> None:
    """§23 Abs. 3 S. 4 EStG: the basis is the cost less the AfA taken, so within ten years of
    `bought` the gain of a let flat is larger than that of one never let; after ten years
    neither is taxed."""

    def extra(streams: list[Stream], held: PropertyAsset) -> float:
        def sold(*, taxable: bool) -> float:
            sale = SellEvent(type="sell", at=date(2026, 6, 1), asset="flat", taxable=taxable)
            return taxed(run(streams, [held], Scenario(name="t", events=[sale])))

        return sold(taxable=True) - sold(taxable=False)

    let = extra([SALARY, rent()], flat(bought=bought))
    never = extra([SALARY, other(1000)], flat(bought=bought, afa=None))
    assert (let > never + 0.3 * BASE * 0.02 * 6) if more else (let == never == 0.0)


def test_the_penalty_of_a_repayment_from_a_taxable_sale_lowers_the_gain() -> None:
    """BFH IX R 42/13: the Vorfälligkeitsentschädigung of a loan repaid from a sale is a cost of
    the private sale (§23 Abs. 3 S. 1 EStG)."""
    loan = {"id": "l", "kind": "loan", "balance": -100_000, "rate": 0.03, "annuity": 800}
    then: list[RepayAction | InvestAction] = [RepayAction(repay="l")]
    sale = SellEvent(type="sell", at=date(2026, 6, 1), asset="flat", taxable=True, then=then)

    def bill(penalty: float) -> float:
        held = Loan.model_validate(
            loan | {"fixed_until": date(2030, 1, 1), "prepayment_penalty": penalty}
        )
        return taxed(run([SALARY, rent()], [flat(), held], Scenario(name="t", events=[sale])))

    balance = 100_000 - 4 * 550  # about the balance in June
    top_rate_with_soli = 0.42 * 1.055  # the sale lies in the top bracket (§32a EStG, §4 SolzG)
    assert bill(0.0) - bill(0.02) == pytest.approx(top_rate_with_soli * 0.02 * balance, rel=0.1)


@pytest.mark.parametrize("pkv", [True, False], ids=["pkv", "gkv"])
def test_the_afa_taken_lowers_the_basis_of_a_sale_once(*, pkv: bool) -> None:
    """The KV of a voluntary member reads the net rent as the tax does, and the AfA of a month
    counts once: a taxable sale in 2026-06 of the flat let since 2020-01 costs as much as one of
    a flat never let, whose cost is lower by the AfA of the 77 months before the month of the
    sale, with the same income."""
    sale, afa = date(2026, 6, 1), BASE * 0.02 / 12

    def extra(streams: list[Stream], held: PropertyAsset) -> float:
        def sold(*, taxable: bool) -> float:
            event = SellEvent(type="sell", at=sale, asset="flat", taxable=taxable)
            scenario = Scenario(name="t", events=[event])
            return taxed(run(streams, [held], scenario, tax={"pkv": pkv}))

        return sold(taxable=True) - sold(taxable=False)

    let = extra([rent()], flat())
    never = extra([other(1000 - afa, end=sale)], flat(afa=None, bought_for=250_000 - 77 * afa))
    assert let > 0.3 * (300_000 - 250_000)
    assert let == pytest.approx(never, abs=1)


def test_the_age_curve_and_the_scale_leave_the_costs_of_the_flat() -> None:
    """A cost of letting is no spending: the age curve and `scale.categories` shrink the other
    expenses of its category, not the Hausgeld, so the tax of the rent stays."""
    costs = [
        Stream(name="Hausgeld", cat="flat", amount=-300, index=None, property="flat"),
        Stream(name="Rücklage", cat="flat", amount=-100, index=None),
    ]
    plain = run([SALARY, rent(), *costs], [flat()])
    shrunk = run(
        [SALARY, rent(), *costs],
        [flat()],
        spending={"age_curve": [{"age": 40, "factor": 0.5}]},
        scale={"categories": {"flat": 0.5}},
    )
    assert taxed(shrunk) == taxed(plain)
    assert shrunk.expenses[0] == pytest.approx(plain.expenses[0] + 0.75 * 100)


def test_a_loss_carries_into_the_next_year() -> None:
    """§10d Abs. 2 EStG: a loss of a let flat in a year without other income lowers the income of
    the next year, nominal, before the Sonderausgaben."""
    hausgeld = Stream(name="Hausgeld", cat="flat", amount=-2000, index=None, property="flat")
    end = date(2027, 1, 1)
    loss = 12 * (2000 - 1000 + BASE * 0.02 / 12)
    later = other(4000, start=end)
    carried = run(
        [rent(end=end), hausgeld.model_copy(update={"end": end}), later], [flat()], months=24
    )
    lower = run([other(4000 - loss / 12, start=date(2027, 1, 1))], [flat()], months=24)
    plain = run([later], [flat()], months=24)
    assert taxed(carried, YEAR) == taxed(lower, YEAR) == 0.0
    assert taxed(carried, NEXT) == pytest.approx(taxed(lower, NEXT), abs=1)
    assert taxed(carried, NEXT) < taxed(plain, NEXT)


def test_a_year_below_the_grundfreibetrag_uses_the_losses_too() -> None:
    """The Verlustvortrag offsets the Gesamtbetrag der Einkünfte whatever its tax: 20,000 € of
    losses, 5,000 € of income in the year after, so 15,000 € reach the third year."""
    years = [date(2027, 1, 1), date(2028, 1, 1)]
    income = [other(5000 / 12, start=years[0], end=years[1]), other(40_000 / 12, start=years[1])]
    carried = run(income, [flat()], months=36, tax={"loss_carryforward": 20_000})
    lower = run([income[0], other(25_000 / 12, start=years[1])], [flat()], months=36)
    assert taxed(carried, slice(24, 36)) == pytest.approx(taxed(lower, slice(24, 36)), abs=1)


def test_inflation_leaves_the_nominal_losses() -> None:
    """The law carries a loss in euros of its year: with prices that rise the losses offset the
    same nominal income as without."""
    hausgeld = Stream(name="Hausgeld", cat="flat", amount=-3000, index=None, property="flat")
    end = date(2027, 1, 1)
    later = other(5000, start=end)
    loss = 12 * (3000 - 1000 + BASE * 0.02 / 12)
    rates = zero_returns(24)
    rates.inflation[:] = 0.05 / 12

    def rising(streams: list[Stream]) -> RunResult:
        return simulate(plan(streams, [CASH, flat()]), rates, "fixed")

    carried = rising([rent(end=end), hausgeld.model_copy(update={"end": end}), later])
    lower = rising([other(5000 - loss / 12, start=date(2027, 1, 1))])
    assert taxed(carried, NEXT) == pytest.approx(taxed(lower, NEXT), abs=2)


def test_the_loss_carryforward_of_the_inputs_lowers_the_first_year() -> None:
    """`tax.loss_carryforward`, the Verlustvortrag of the last Feststellungsbescheid."""
    seeded = run([other(4000)], [], tax={"loss_carryforward": 10_000})
    assert taxed(seeded) == pytest.approx(taxed(run([other(4000 - 10_000 / 12)], [])), abs=1)


def test_a_business_loss_carries_too() -> None:
    """A loss of a business (§§15, 18 EStG) in a year without other income carries forward."""
    shop = Stream(
        name="shop", kind=StreamKind.SELF_EMPLOYED, amount=-1000, index=None, end=date(2027, 1, 1)
    )
    later = other(4000, start=date(2027, 1, 1))
    carried = run([shop, later], [], months=24)
    lower = run([other(3000, start=date(2027, 1, 1))], [], months=24)
    assert taxed(carried, NEXT) == pytest.approx(taxed(lower, NEXT), abs=1)


def yearly(*months: float, back: bool = True) -> RunResult:
    """Other income of each year from 2026 by its monthly amount, a run of those years and one
    more, in which the refund of a carryback comes; `back` the option `tax.loss_carryback`."""
    streams = [
        other(amount, start=date(2026 + i, 1, 1), end=date(2027 + i, 1, 1))
        for i, amount in enumerate(months)
        if amount
    ]
    return run(streams, [], months=12 * len(months) + 12, tax={"loss_carryback": back})


def test_a_loss_goes_back_into_the_year_before_and_refunds_a_december_later() -> None:
    """§10d Abs. 1 S. 1 EStG: 12,000 € of loss in 2027 come off the income of 2026, whose tax
    falls to that of 12,000 € less; the assessment of 2027 refunds it in December 2028. Without
    the carryback the loss waits for later income."""
    back, forward = yearly(4000, -1000), yearly(4000, -1000, back=False)
    refund = taxed(back, YEAR) - taxed(yearly(3000), YEAR)
    assert refund > 2000
    assert back.taxes[0, 12:35].tolist() == forward.taxes[0, 12:35].tolist() == [0.0] * 23
    assert back.taxes[0, 35] == pytest.approx(refund)
    assert forward.taxes[0, 35] == 0.0
    assert back.liquid[0, -1] == pytest.approx(forward.liquid[0, -1] + refund)


def test_switched_off_a_loss_carries_forward_only() -> None:
    """`tax.loss_carryback: false` waives the carryback (§10d Abs. 1 S. 6): the loss offsets the
    income of 2028 as the Verlustvortrag did alone, and with the carryback 2028 pays the tax of
    its whole income less the refund of 2026."""
    loss = (4000, -1000, 4000)
    forward = yearly(*loss, back=False)
    back, plain = yearly(*loss), yearly(4000, 0, 4000)
    third = slice(24, 36)
    assert taxed(forward, third) == pytest.approx(taxed(yearly(4000, 0, 3000), third), abs=1)
    refund = taxed(plain, YEAR) - taxed(yearly(3000), YEAR)
    assert taxed(back, third) == pytest.approx(taxed(plain, third) - refund, abs=1)


def test_a_loss_beyond_the_year_before_goes_into_the_second() -> None:
    """§10d Abs. 1 S. 2 EStG: 25,000 € of loss in 2028 take the 10,000 € of 2027 and 15,000 € of
    the 30,000 € of 2026."""
    back = yearly(2500, 10_000 / 12, -25_000 / 12)
    two = slice(0, 24)
    refund = taxed(yearly(2500, 10_000 / 12), two) - taxed(yearly(1250), two)
    assert back.taxes[0, 47] == pytest.approx(refund, abs=1)


def test_a_loss_goes_back_into_the_capital_income_that_the_tariff_taxed() -> None:
    """§10d Abs. 1 S. 1 with §32d Abs. 6 S. 1 EStG: a term deposit pays 21,000 € of interest in
    2026, which the Günstigerprüfung taxes at the tariff, so it joins the Gesamtbetrag der
    Einkünfte; 10,000 € of loss in 2027 go back into it and refund in December 2028 what the same
    loss in 2026 saved."""
    deposit = TermDeposit(
        id="t",
        kind="term_deposit",
        value=100_000,
        rate=0.10,
        start=date(2024, 3, 1),
        matures=date(2026, 3, 1),
    )

    def paid(streams: list[Stream], months: slice) -> float:
        r = run(streams, [deposit], months=36)
        return float(-(r.taxes[0, months] + r.capital_taxes[0, months]).sum())

    def lost(year: int) -> list[Stream]:
        return [other(-10_000 / 12, start=date(year, 1, 1), end=date(year + 1, 1, 1))]

    saved = paid([], YEAR) - paid(lost(2026), YEAR)
    assert saved > 1000
    assert paid(lost(2027), slice(35, 36)) == pytest.approx(-saved, abs=1)


def test_a_carryback_takes_the_grundfreibetrag_of_a_year_of_low_income() -> None:
    """Since 2022 the law waives the carryback only as a whole (§10d Abs. 1 S. 6): 10,000 € of
    loss go back into the 15,000 € of 2026 and refund its little tax, the Grundfreibetrag of 2026
    unused; carried forward they would have saved more of the tax of 2028."""
    loss = (1250, -10_000 / 12, 20_000 / 12)
    back, forward = yearly(*loss), yearly(*loss, back=False)
    plain = yearly(1250, 0, 20_000 / 12)
    third = slice(24, 36)
    assert taxed(back, third) == pytest.approx(taxed(plain, third) - taxed(plain, YEAR), abs=1)
    assert taxed(forward, third) == pytest.approx(taxed(yearly(1250, 0, 10_000 / 12), third))
    assert taxed(forward, slice(0, 48)) < taxed(back, slice(0, 48))


def test_a_bought_flat_takes_its_afa_from_the_purchase() -> None:
    """A `buy_property` with a rent from the month after: its cost with tax and costs is the
    basis of the AfA, and its loan finances it."""
    loan = {"id": "l", "balance": -200_000, "rate": 0.03, "annuity": 1000}
    bought = {"id": "flat", "building_share": 0.8, "afa": 0.02}
    buy = purchase(property=bought, loan=loan)

    def letting(**link: str) -> RunResult:
        added = {"name": "Miete", "kind": "other_income", "amount": 1500} | link
        rented = {"at": date(2026, 4, 1), "type": "add_stream", "stream": added}
        return run([SALARY], [], Scenario.model_validate({"name": "t", "events": [buy, rented]}))

    let, plain = letting(property="flat"), letting()
    cost = 300_000 * (1 + 0.05 + 0.02) * 0.8 * 0.02 / 12 * 9  # nine months from 2026-04
    assert taxed(plain) - taxed(let) > 0.3 * cost


def test_a_voluntary_member_pays_on_the_net_rent_at_least_the_minimum() -> None:
    """BVSzGs §3 Abs. 1b: the KV of a freiwilliges Mitglied takes the rent after its Werbungskosten,
    the interest among them, never below the minimum base."""
    loan = {"id": "l", "kind": "loan", "balance": -300_000, "rate": 0.04, "annuity": 1500}
    gkv = {"pkv": False}
    big = rent(4000)
    financed = run([big], [flat(), Loan.model_validate(loan | {"finances": "flat"})], tax=gkv)
    alone = run([big], [flat(), Loan.model_validate(loan)], tax=gkv)
    nothing = run([], [], tax=gkv)
    assert booked(financed, "KV")[0] < booked(alone, "KV")[0]
    assert booked(financed, "KV")[0] >= booked(nothing, "KV")[0] - 0.005


def test_a_rental_loss_leaves_the_positive_income_of_the_trade_credit() -> None:
    """§35 Abs. 1 S. 2 EStG: the credit of the Gewerbesteuer takes at most the share of the trade
    income in the sum of the positive income; a loss of a let flat is none, so it does not raise
    that share as the other income, which holds it, would."""
    trade, annuity, loss = 30_000.0, 100_000.0, 110_000.0
    year = YearIncome(
        other_taxable=trade + annuity - loss, rent=-loss, trade_income=trade, trade_credit=5000.0
    )
    settled = year_settlement(year, TY, church=0.0)
    tariff = float(income_tax(trade + annuity - loss - TY.sonderausgaben_pauschbetrag, TY))
    assert float(settled.credit) == pytest.approx(tariff * trade / (trade + annuity))
    inside = year_settlement(replace(year, rent=0.0), TY, church=0.0)  # the loss in the other
    assert float(inside.credit) > float(settled.credit)


def test_a_church_tax_refund_comes_after_the_losses_carried() -> None:
    """A refund of church tax beyond what the year paid is added like a negative Sonderausgabe
    (§10 Abs. 4b S. 3 EStG): it raises no Gesamtbetrag der Einkünfte, so the losses carried do
    not offset it and stay as they are (BFH IX R 34/17, BStBl II 2019, 658)."""
    year = YearIncome(salary_gross=60_000.0, loss_carried=200_000.0)
    plain = year_settlement(year, TY, church=0.0)
    refunded = year_settlement(replace(year, church_paid=-20_000.0), TY, church=0.0)
    assert float(refunded.loss_left) == pytest.approx(float(plain.loss_left))
    assert float(plain.tax) == 0.0
    taxed_refund = income_tax(20_000.0 - TY.sonderausgaben_pauschbetrag, TY)
    assert float(refunded.tax) == pytest.approx(float(taxed_refund))
