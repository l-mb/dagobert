"""The spending rule: the cut below and the increase above a reference wealth, the reference of
the start or of the first month without pay, its arming and re-arming; VPW, its budget, the
fixed draws, the floor, the months with pay and the one-offs."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from builders import booked, cash, phases, plan, purchase, zero_returns

from dagobert.engine.simulation import simulate
from dagobert.model.assets import AvDepot, CashAsset, PensionPolicy
from dagobert.model.assumptions import Person, Vpw
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import SPENDING, FloatArray, RunResult
from dagobert.returns import Returns

FUN = Stream(name="fun", cat="fun", amount=-2000)
NO_PAY: dict[str, object] = {"base": "no_pay", "categories": ["fun"]}
CUT = NO_PAY | {"cut": 0.5, "trigger": 1.0}  # a cut in every month below the reference


def _salary(**kw: object) -> Stream:
    """A salary of 8,000 € a month in `work`."""
    job: dict[str, object] = {"name": "job", "kind": "salary", "gross": 8000, "phases": ["work"]}
    return Stream.model_validate(job | kw)


def _month(i: int) -> date:
    return date(2026 + i // 12, i % 12 + 1, 1)


def _run(
    streams: list[Stream], spending: dict[str, object], *changes: tuple[int, str], months: int = 40
) -> RunResult:
    """A run of `streams` from 50,000 € of cash, in `work` until the first of the `changes`
    (month index, phase)."""
    scenario = Scenario(name="s", phases=phases(*((_month(i), p) for i, p in changes)))
    return simulate(
        plan(streams, [CashAsset(id="c", kind="cash", value=50_000)], scenario, spending=spending),
        zero_returns(months),
        "fixed",
    )


def test_the_increase_raises_above_the_ceiling_and_never_while_it_cuts() -> None:
    """Retired from the start: an income for half a year lifts the wealth above the ceiling, the
    spending then takes it down below the trigger. A raised month spends a tenth more than the
    run without the increase, a cut month 1,000 €, never both."""
    gift = Stream(
        name="gift", kind=StreamKind.OTHER_INCOME, amount=20_000, end=_month(6), taxable=False
    )
    rule = NO_PAY | {"cut": 0.5, "trigger": 0.5, "increase": 0.1, "ceiling": 1.5}
    raised, plain = (
        _run([FUN, gift], rule | {"increase": increase}, (0, "retired"), months=120)
        for increase in (0.1, 0.0)
    )
    spent, without = raised.expenses[0], plain.expenses[0]
    more = spent < without  # expenses are below zero
    assert more.sum() == raised.raised[0] > 0
    assert spent[more] == pytest.approx(without[more] * 1.1)
    assert (spent == -1000).sum() == raised.reduced[0] > 0
    assert plain.raised[0] == 0


@pytest.mark.parametrize("base", ["start", "no_pay"])
def test_a_trigger_of_zero_never_cuts(base: str) -> None:
    """A trigger of 0 switches the cut off, also on a path that runs out of money."""
    off, plain = (
        _run([FUN], CUT | {"base": base, "trigger": 0.0, "cut": cut}, (0, "retired"))
        for cut in (0.5, 0.0)
    )
    assert off.liquid[0, -1] < 0
    assert off.reduced[0] == 0
    assert (off.expenses == plain.expenses).all()


def test_no_pay_acts_while_no_salary_pays() -> None:
    """A wealth that falls under a salary: `start` cuts while the salary pays, `no_pay` not."""
    job = _salary(gross=2000)
    start, no_pay = (_run([FUN, job], CUT | {"base": base}) for base in ("start", "no_pay"))
    assert start.reduced[0] > 0
    assert no_pay.reduced[0] == 0


@pytest.mark.parametrize(
    "streams",
    [[FUN], [FUN, Stream(name="minijob", kind=StreamKind.OTHER_INCOME, amount=500)]],
    ids=["retired", "other income"],
)
def test_no_pay_from_a_retired_start_equals_start(streams: list[Stream]) -> None:
    """A plan that starts retired arms in its first month, and other income is no pay."""
    start, no_pay = (_run(streams, CUT | {"base": b}, (0, "retired")) for b in ("start", "no_pay"))
    assert no_pay.reduced[0] == start.reduced[0] > 0
    assert (no_pay.expenses == start.expenses).all()


def test_the_rule_arms_in_the_month_after_the_last_pay() -> None:
    """A job that ends after five or eight months: the rule cuts from the second month after its
    end on, so the later end cuts three months less."""
    early, late = (_run([FUN, _salary()], CUT, (0, "work"), (end, "retired")) for end in (5, 8))
    assert early.reduced[0] - late.reduced[0] == 3


def test_a_late_payment_suspends_the_rule_for_a_month_and_keeps_the_reference() -> None:
    """A bonus two months after the end of the job: the month after it does not cut, the next
    cuts again against the reference of the retirement, not the wealth after the bonus."""
    bonus = _salary(name="bonus", gross=1000, start=_month(6), end=_month(7), phases=None)
    with_bonus, without = (
        _run([FUN, _salary(), *extra], CUT, (0, "work"), (4, "retired")) for extra in ([bonus], [])
    )
    assert with_bonus.reduced[0] == without.reduced[0] - 1


@pytest.mark.parametrize(("job", "kept"), [(11, True), (12, False)])
def test_twelve_months_of_pay_take_a_new_reference(job: int, kept: bool) -> None:
    """A career break from the start, a job, the retirement: after a job of twelve months the
    retirement compares with its own wealth and raises nothing, after one of eleven it keeps the
    reference of the break, which its savings pass by half."""
    rule = NO_PAY | {"increase": 0.1, "ceiling": 1.5}
    changes = ((0, "alt"), (12, "work"), (12 + job, "retired"))
    r = _run([FUN, _salary(gross=12_000)], rule, *changes, months=80)
    assert (r.raised[0] > 0) == kept


@pytest.mark.parametrize(("reference", "more"), [(50_000, False), (60_000, True)])
def test_a_reference_replaces_the_wealth_of_the_start(reference: float, more: bool) -> None:
    """The wealth of the start as the reference cuts as without one, a higher one cuts more."""
    rule = CUT | {"base": "start", "trigger": 0.9}
    given, plain = (_run([FUN], rule | extra) for extra in ({"reference": reference}, {}))
    assert (given.reduced[0] > plain.reduced[0]) == more
    assert (given.reduced[0] >= plain.reduced[0]) and (given.expenses >= plain.expenses).all()


# VPW: retired from the start, no returns, `fun` the one flexible category
VPW: dict[str, object] = {"base": "no_pay", "categories": ["fun"], "vpw": {}}
WEALTH = 600_000


def _vpw(
    streams: list[Stream],
    *changes: tuple[int, str],
    assets: tuple[object, ...] = (),
    vpw: dict[str, object] | None = None,
    wealth: float = WEALTH,
    months: int = 24,
    returns: Returns | None = None,
    events: tuple[dict[str, object], ...] = (),
    **kw: object,
) -> RunResult:
    """A run of `streams` under VPW (`vpw` its fields) from `wealth` in cash, retired from the
    start unless `changes` say otherwise."""
    scenario = Scenario.model_validate(
        {
            "name": "s",
            "phases": phases(*((_month(i), p) for i, p in changes or ((0, "retired"),))),
            "events": list(events),
        }
    )
    spending = VPW | {"vpw": vpw or {}}
    return simulate(
        plan(streams, [cash(wealth), *assets], scenario, spending=spending, **kw),
        returns or zero_returns(months),
        "fixed",
    )


def _fun(r: RunResult) -> FloatArray:
    """What the flexible category `fun` spent per month, above zero."""
    return booked(r, "fun", SPENDING, "fun")


def _rate(r: RunResult, i: int) -> float:
    """The VPW rate of the defaults at the age of January of month `i` (the run starts in one)."""
    return Vpw().rate_at(float(r.ages[i - i % 12]))


def _cash_at(rate: float, months: int) -> Returns:
    """No returns but the cash at `rate` a year."""
    returns = zero_returns(months)
    returns.rates["cash"][:] = (1 + rate) ** (1 / 12) - 1
    return returns


QUARTERLY = Stream(name="fun", cat="fun", amount=-6000, every=3)
RENT = Stream(name="rent", cat="rent", amount=-500)
TAX_FREE = {"sparer_pauschbetrag": 1e9}  # the interest of the cash pays no tax


@pytest.mark.parametrize("fun", [FUN, QUARTERLY], ids=["monthly", "quarterly"])
def test_vpw_spends_a_twelfth_of_the_rate_of_the_wealth(fun: Stream) -> None:
    """The flexible spending of each month of the first year is the rate of the age times the
    wealth of the start over twelve, monthly also for a stream paid every three months."""
    r = _vpw([fun], months=12)
    assert _fun(r) == pytest.approx(np.full(12, _rate(r, 0) * WEALTH / 12))
    assert (r.expenses[0] == -_fun(r)).all()


def test_the_fixed_draws_come_out_of_the_budget() -> None:
    """A fixed rent leaves the total spending as it was and the flexible spending lower by it,
    an income raises the flexible spending by itself."""
    alone, rent = (_vpw([FUN, *more]) for more in ([], [RENT]))
    assert rent.expenses[0] == pytest.approx(alone.expenses[0])
    assert _fun(rent) == pytest.approx(_fun(alone) - 500)
    gift = Stream(name="gift", kind=StreamKind.OTHER_INCOME, amount=1000, taxable=False)
    assert _fun(_vpw([FUN, gift])) == pytest.approx(_fun(alone) + 1000)


def test_twice_the_wealth_spends_twice_and_an_older_start_a_higher_share() -> None:
    plain, rich = (_vpw([FUN], wealth=w) for w in (WEALTH, 2 * WEALTH))
    assert _fun(rich) == pytest.approx(2 * _fun(plain))
    older = _vpw([FUN], person=Person(born=date(1967, 1, 1)))
    assert _fun(older)[0] > _fun(plain)[0]


@pytest.mark.parametrize(("rate", "trend"), [(0.03, 0), (0.05, 1), (0.01, -1)])
def test_the_budget_holds_when_the_wealth_grows_by_the_trend(rate: float, trend: int) -> None:
    """The PMT invariant: with the cash growing at the 3% of `growth`, no other flow and no tax,
    each January spends what the one before did (the twelfths earn inside a year, which the
    annuity due of the rate leaves out: about 0.05% a year); faster growth raises it, slower
    lowers it."""
    r = _vpw([FUN], months=12 * 15, returns=_cash_at(rate, 12 * 15), tax=TAX_FREE)
    january = _fun(r)[::12]
    if trend == 0:
        assert january[1:] == pytest.approx(january[:-1], rel=1e-3)
    else:
        assert (np.sign(np.diff(january)) == trend).all()


def test_the_floor_holds_the_flexible_spending() -> None:
    """A floor above the budget pays the floor in every month, and the wealth falls faster."""
    plain, floored = (_vpw([FUN], vpw={"floor": f}, wealth=120_000) for f in (0, 1500))
    assert _fun(plain)[0] < 1500
    assert _fun(floored) == pytest.approx(np.full(24, 1500.0))
    assert (floored.liquid[0, 1:] < plain.liquid[0, 1:]).all()
    assert floored.reduced[0] == 24
    assert floored.raised[0] == 0


def test_a_month_with_pay_pays_the_plan() -> None:
    """A salary for six months: the flexible spending is the plan, the first month without pay
    takes the budget from the wealth at its start."""
    r = _vpw([FUN, _salary()], (0, "work"), (6, "retired"), months=12)
    assert _fun(r)[:6] == pytest.approx(np.full(6, 2000.0))
    assert _fun(r)[6] == pytest.approx(_rate(r, 6) * r.liquid[0, 5] / 12)


def test_a_late_bonus_pays_the_plan_in_its_month_only() -> None:
    """A bonus two months after the end of the job: its month spends the plan, the other months of
    the year as without it."""
    bonus = _salary(name="bonus", gross=1000, start=_month(6), end=_month(7), phases=None)
    with_bonus, without = (
        _vpw([FUN, _salary(), *extra], (0, "work"), (4, "retired"), months=12)
        for extra in ([bonus], [])
    )
    assert _fun(with_bonus)[6] == pytest.approx(2000)
    assert _fun(with_bonus)[4:6] == pytest.approx(_fun(without)[4:6])
    assert _fun(with_bonus)[7:] == pytest.approx(_fun(without)[7:])


def test_a_january_with_pay_takes_a_new_budget_in_the_next_month() -> None:
    """A bonus in the second January: the first month without pay of that year takes the budget
    from the wealth that holds the bonus."""
    bonus = _salary(name="bonus", gross=10_000, start=_month(12), end=_month(13), phases=None)
    with_bonus, without = (_vpw([FUN, *extra], months=14) for extra in ([bonus], []))
    fun = _fun(with_bonus)
    assert fun[12] == pytest.approx(2000)
    assert fun[13] == pytest.approx(_rate(with_bonus, 13) * with_bonus.liquid[0, 12] / 12)
    assert fun[13] > _fun(without)[13]


# a company pension of 30,000 € paid at once
LUMP = {
    "kind": "bav",
    "value": 30_000,
    "paid": 30_000,
    "contribution": 0,
    "phases": [],
    "growth": "fixed_income",
}


@pytest.mark.parametrize(
    ("assets", "events"),
    [
        ((PensionPolicy.model_validate(LUMP | {"id": "b", "matures": _month(3)}),), ()),
        (
            (
                PensionPolicy.model_validate(
                    LUMP | {"id": "b", "matures": _month(3), "fuenftel": False}
                ),
            ),
            (),
        ),
        ((), (purchase(_month(3), property={"id": "home", "upkeep": 0}),)),
    ],
    ids=["lump sum", "lump sum without fifths", "purchase"],
)
def test_a_one_off_leaves_the_flexible_spending_of_its_month(
    assets: tuple[object, ...], events: tuple[dict[str, object], ...]
) -> None:
    """A lump sum of a policy and a purchase go to the wealth and the next budget: the month
    spends as without them."""
    one_off, plain = (
        _vpw([FUN], assets=a, events=e, months=12) for a, e in ((assets, events), ((), ()))
    )
    assert _fun(one_off) == pytest.approx(_fun(plain))


def test_the_lump_sum_of_an_altersvorsorgedepot_stays_out_and_its_payments_count() -> None:
    """At 67 the depot pays 30% at once, outside the flexible spending, and the rest monthly over
    the 18 years to 85, which the flexible spending takes as income."""
    depot = AvDepot(id="av", kind="av_depot", value=21_600, start=date(2027, 1, 1))
    born = Person(born=date(1959, 1, 1))
    paid, plain = (_vpw([FUN], assets=a, months=2, person=born) for a in ((depot,), ()))
    assert _fun(paid) == pytest.approx(_fun(plain) + 0.7 * 21_600 / 216)


def test_a_basisrente_premium_comes_out_of_the_flexible_spending() -> None:
    premium = PensionPolicy.model_validate(
        LUMP
        | {"id": "r", "value": 0, "paid": 0, "matures": _month(60), "payout": "annuity"}
        | {"basisrente": True, "premium": 300, "phases": ["retired"], "annuity_per_10k": 40}
    )
    paid, plain = (_vpw([FUN], assets=a, months=12) for a in ((premium,), ()))
    assert _fun(paid) == pytest.approx(_fun(plain) - 300)


def test_the_months_at_the_floor_and_above_the_plan_count_apart() -> None:
    """A yearly insurance bill of 5,000 € puts its months at the floor, the budget of a large
    wealth puts the others above the plan of 2,000 €."""
    bill = Stream(name="insurance", cat="insurance", amount=-5000, every=12)
    r = _vpw([FUN, bill], vpw={"floor": 500}, wealth=1_000_000)
    assert _fun(r)[[0, 12]] == pytest.approx([500, 500])
    assert r.reduced[0] == 2
    assert r.raised[0] == 22


def test_the_tax_bill_of_a_year_comes_out_of_the_next() -> None:
    """A taxable income against a tax-free twin: the first year spends alike, the second less, as
    a twelfth of the first December's bill comes off each month, so the draws of the second year
    and the bill of the first come to its budget."""
    income = {"name": "income", "kind": StreamKind.OTHER_INCOME, "amount": 2000}
    taxed, free = (
        _vpw([FUN, Stream.model_validate(income | {"taxable": t})]) for t in (True, False)
    )
    assert _fun(taxed)[:12] == pytest.approx(_fun(free)[:12])
    assert (_fun(taxed)[12:] < _fun(free)[12:]).all()
    bill = -taxed.taxes[0, 11]
    assert bill > 0
    drawn = -taxed.expenses[0, 12:].sum() - taxed.income[0, 12:].sum()
    assert drawn + bill == pytest.approx(_rate(taxed, 12) * taxed.liquid[0, 11])


def test_the_settlement_of_a_severance_is_a_one_off_not_flexible_spending() -> None:
    """A severance taxed by the Fünftelregelung settles in December against its withholding. The
    difference goes to the wealth: the next year draws its budget, with no regular bill."""
    r = _vpw([FUN], events=({"at": _month(2), "type": "severance", "gross": 100_000},), months=24)
    assert r.taxes[0, 11] != 0
    drawn = -r.expenses[0, 12:].sum() - r.income[0, 12:].sum()
    assert drawn == pytest.approx(_rate(r, 12) * r.liquid[0, 11])


def test_the_cut_leaves_a_premium_of_a_flexible_category_alone() -> None:
    """A health premium is no spending (`managed`): the band cuts the stream `fun` of the same
    category in every month and the premium in none."""
    premium = Stream(name="kv", kind=StreamKind.EXPENSE, cat="fun", amount=-400, health="kv")
    cut, plain = (_run([FUN, premium], rule, months=6) for rule in (CUT, NO_PAY))
    assert cut.expenses[0, -1] == plain.expenses[0, -1] + 1000
