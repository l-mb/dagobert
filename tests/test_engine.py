"""The month of a run: flows, loans, the events and sales, the purchase of a property, the
ledger, care, the tax year of a plan and the price levels."""

from collections.abc import Callable
from datetime import date

import numpy as np
import pytest
from builders import (
    assumptions,
    booked,
    cash,
    gold,
    levels,
    marked,
    plan,
    purchase,
    zero_returns,
    zero_run,
)

from dagobert import carry, tax
from dagobert.engine.simulation import horizon_months, simulate
from dagobert.model.assets import (
    AvDepot,
    CryptoAsset,
    EquityAsset,
    FixedIncomeAsset,
    Loan,
    PensionPolicy,
    PropertyAsset,
    TermDeposit,
)
from dagobert.model.assumptions import Person
from dagobert.model.events import (
    AddStreamEvent,
    BuyPropertyEvent,
    EndStreamsEvent,
    FundPolicyEvent,
    InvestAction,
    PolicyFunding,
    RepayAction,
    RepayEvent,
    SaleTrigger,
    SellEvent,
    SetStreamEvent,
    SeveranceEvent,
    WriteOffEvent,
)
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import TAX_YEARS
from dagobert.result import DRAW, MOVE_IN, MOVE_OUT, MOVED, NONCASH, FloatArray, RunResult
from dagobert.returns import Returns
from dagobert.tax import for_year

TY = for_year(2026)


def test_month_index() -> None:
    assert months_between(date(2026, 1, 1), date(2027, 3, 15)) == 14
    assert horizon_months(assumptions()) == (2082 - 2026) * 12


def test_broke_flag() -> None:
    p = plan([Stream(name="x", amount=-1000)], [cash(2500)])
    r = zero_run(p, 6)
    assert list(r.broke[0]) == [False, False, True, True, True, True]


@pytest.mark.parametrize(
    ("phases", "events", "month"),
    [
        (["work"], [], 4),  # work, a gap, work again: after the last work
        (["work"], [{"at": date(2026, 2, 1), "type": "end_streams", "names": ["pay"]}], 1),
        (["unemployed"], [], 3),  # no pay at the start
        (["retired"], [], 0),  # pay to the end: the start
        (["alt"], [], 0),  # never pays: the start
        (
            ["work", "retired"],
            [{"at": date(2026, 6, 1), "type": "end_streams", "names": ["pay"]}],
            0,
        ),
        (
            ["work", "retired"],
            [{"at": date(2026, 5, 1), "type": "end_streams", "names": ["pay"]}],
            4,
        ),
    ],
    ids=["gap", "end_streams", "late", "to the end", "none", "one month short", "two short"],
)
def test_the_pay_ends_after_the_last_salary(
    phases: list[str], events: list[dict[str, object]], month: int
) -> None:
    scenario = Scenario.model_validate(
        {
            "name": "s",
            "phases": [
                {"from": date(2026, 1, 1), "phase": "work"},
                {"from": date(2026, 3, 1), "phase": "unemployed"},
                {"from": date(2026, 4, 1), "phase": "work"},
                {"from": date(2026, 5, 1), "phase": "retired"},
            ],
            "events": events,
        }
    )
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None, phases=phases)
    assert zero_run(plan([pay], [cash()], scenario), 6).pay_ends == month


def test_loan_amortizes_and_ends() -> None:
    loan = Loan(id="l", kind="loan", balance=-1200, rate=0.0, annuity=100)
    p = plan([], [cash(5000), loan])
    r = zero_run(p, 15)
    assert r.liquid[0, 11] == pytest.approx(3800)
    assert r.liquid[0, 14] == pytest.approx(3800)
    assert r.total[0, 0] == pytest.approx(4900 - 1100)


def test_conditional_sale_on_liquid_drawdown_swaps_streams() -> None:
    scenario = Scenario(
        name="cond",
        events=[
            SellEvent(
                type="sell",
                asset="home",
                when=SaleTrigger(liquid_below=500),
                then=[InvestAction(invest="portfolio")],
            )
        ],
    )
    p = plan(
        [
            Stream(name="hausgeld", amount=-300, tags=["home"]),
            Stream(name="rent", amount=-100, after_sale_of="home"),
        ],
        [
            cash(1000),
            PropertyAsset(id="home", kind="property", sqm=100, per_sqm=1000, tags=["home"]),
        ],
        scenario,
        cash_buffer_months=0,
    )
    r = zero_run(p, 5)
    # cash 1000 -> 700 -> 400; the third month starts below 500 and sells at 100_000
    assert r.expenses[0].tolist() == [-300, -300, -100, -100, -100]
    assert r.liquid[0, 1] == pytest.approx(400)
    assert r.liquid[0, 2] == pytest.approx(400 + 100_000 - 100)
    assert r.total[0, 2] == pytest.approx(r.liquid[0, 2])
    assert ("sell", "home", "") in [(m.kind, m.detail, m.form) for m in r.markers]  # not half


def test_balance_adds_up_to_median_total_when_some_paths_sold() -> None:
    scenario = Scenario(
        name="cond",
        events=[
            SellEvent(
                type="sell",
                asset="home",
                when=SaleTrigger(liquid_below=800),
                costs=0.1,
                then=[InvestAction(invest="portfolio")],
            )
        ],
    )
    p = plan(
        [],
        [
            EquityAsset(id="e", kind="equity", value=1000, cost_basis=1000),
            PropertyAsset(id="home", kind="property", sqm=100, per_sqm=10),
        ],
        scenario,
        cash_buffer_months=0,
    )
    returns = zero_returns(24, paths=500)
    rng = np.random.default_rng(1)
    returns.rates["equity"] = rng.normal(0, 0.05, (500, 24))
    returns.inflation[:] = rng.normal(0.002, 0.01, (500, 24))
    r = simulate(p, returns, "montecarlo")
    sold = r.total[:, -1] == r.liquid[:, -1]
    assert 0.2 < sold.mean() < 0.5  # the property median alone still shows the full value
    for balance, total in ((r.nominal_balance, r.total), (r.balance, r.euros(r.total))):
        stack = sum(balance.values(), np.zeros(24))
        assert stack == pytest.approx(np.median(total, axis=0), rel=0.01)
    assert r.euros(r.total)[:, 0] == pytest.approx(r.total[:, 0])  # the first month is at 1


CASH = cash()


@pytest.mark.parametrize(
    ("build", "problem"),
    [
        (lambda: SellEvent(type="sell", asset="home"), "exactly one of `at` and `when`"),
        (
            lambda: SellEvent(
                type="sell", asset="home", when=SaleTrigger(age=80), then=[RepayAction(repay="l")]
            ),
            "cannot repay",
        ),
        (
            lambda: plan([Stream(name="x", amount=-1, index="nope")], [CASH]),
            "the index nope is not defined",
        ),
        (
            lambda: plan(
                [],
                [CASH],
                Scenario.model_validate(
                    {
                        "name": "f",
                        "events": [
                            {"at": date(2026, 1, 1), "type": "fund_policy", "policy": "nope"}
                            | {"amount": 1}
                        ],
                    }
                ),
            ),
            "no bAV policy has the id nope",
        ),
        (
            lambda: plan(
                [],
                [CASH],
                Scenario.model_validate(
                    {
                        "name": "w",
                        "events": [{"at": date(2026, 3, 1), "type": "write_off", "asset": "c"}],
                    }
                ),
            ),
            "no equity asset has the id c",
        ),
        (
            lambda: TermDeposit(
                id="t",
                kind="term_deposit",
                value=1,
                rate=0.1,
                start=date(2026, 3, 1),
                matures=date(2026, 3, 1),
            ),
            "start must be before matures",
        ),
    ],
    ids=["sale", "conditional repay", "index", "policy", "write-off", "term deposit"],
)
def test_a_plan_refuses_what_the_engine_cannot_run(
    build: Callable[[], object], problem: str
) -> None:
    with pytest.raises(ValueError, match=problem):
        build()


def test_spending_rule_cuts_flexible_categories() -> None:
    spending = {"cut": 0.5, "trigger": 0.9, "categories": ["fun"]}
    p = plan(
        [Stream(name="fun", cat="fun", amount=-100), Stream(name="rent", amount=-100)],
        [cash(1000)],
        spending=spending,
    )
    r = zero_run(p, 4)
    assert r.expenses[0].tolist() == [-200, -150, -150, -150]
    assert r.reduced.tolist() == [3]


def test_scale_changes_spending_by_category_but_not_the_health_premium() -> None:
    streams = [
        Stream(name="fun", cat="fun", amount=-100),
        Stream(name="pkv", cat="fun", amount=-300, health="kv"),
        Stream(name="rent", cat="home", amount=-500),
        Stream(name="gift", cat="fun", kind=StreamKind.OTHER_INCOME, amount=50),
        Stream(name="pay", kind=StreamKind.SALARY, gross=6000, index=None),
    ]
    held: list[object] = [cash(10_000)]
    r = zero_run(plan(streams, held, scale={"categories": {"fun": 0.5}}), 2)
    assert r.expenses[0].tolist() == [-850, -850]
    # the salary, the gift and the employer's half of the whole premium
    assert r.income[0].tolist() == [6200, 6200]
    with pytest.raises(ValueError, match="no expense stream has the category typo"):
        plan(streams, held, scale={"categories": {"typo": 0.5}})


def test_scale_spending_equals_every_category_at_the_same_factor() -> None:
    streams = [
        Stream(name="fun", cat="fun", amount=-100),
        Stream(name="pkv", cat="fun", amount=-300, health="kv"),
        Stream(name="rent", cat="home", amount=-500),
    ]
    held: list[object] = [cash(10_000)]

    def spent(**scale: object) -> list[float]:
        r = zero_run(plan(streams, held, scale=scale), 2)
        return list(r.expenses[0].tolist())

    assert spent(spending=0.9) == spent(categories={"fun": 0.9, "home": 0.9}) == [-840, -840]
    assert spent(spending=0.5, categories={"fun": 0.5}) == spent(
        categories={"fun": 0.25, "home": 0.5}
    )


def test_a_dated_loan_balance_rolls_forward_to_the_start() -> None:
    """The statement of January 2026 shows 10,000. February and March pay 100 each, the first
    simulated month, April, pays the third."""

    def first_total(asof: date | None) -> float:
        loan = Loan(id="l", kind="loan", balance=-10_000, rate=0.0, annuity=100, asof=asof)
        p = plan([], [cash(), loan], start=date(2026, 4, 1))
        return float(zero_run(p, 2).total[0, 0])

    assert first_total(date(2026, 1, 1)) == pytest.approx(-100 - 9_700)
    assert first_total(None) == pytest.approx(-100 - 9_900)
    assert first_total(date(2026, 6, 1)) == pytest.approx(-100 - 9_900)  # after the start


@pytest.mark.parametrize(
    ("asset", "start", "added"),
    [
        # February and March: the employer's 100 each
        (
            PensionPolicy(
                id="bav",
                kind="bav",
                value=1000,
                contribution=100,
                phases=["work"],
                matures=date(2040, 1, 1),
                growth="cash",
                asof=date(2026, 1, 31),
            ),
            date(2026, 4, 1),
            200.0,
        ),
        # the December of a year with a salary: the contribution and the Zulage
        (
            AvDepot(
                id="av",
                kind="av_depot",
                value=1000,
                start=date(2027, 1, 1),
                asof=date(2027, 6, 30),
            ),
            date(2028, 3, 1),
            1800 + float(tax.av_zulage(1800, 0, tax.for_year(2026))),
        ),
    ],
)
def test_a_dated_policy_value_rolls_forward_to_the_start(
    asset: PensionPolicy | AvDepot, start: date, added: float
) -> None:
    """A value of an earlier `asof` takes the contributions since, a later one stays."""
    salary = Stream(name="salary", kind=StreamKind.SALARY, gross=3000, index=None)

    def first_total(asof: date | None) -> float:
        dated = asset.model_copy(update={"asof": asof})
        p = plan([salary], [cash(), dated], start=start)
        return float(zero_run(p, 1).total[0, 0])

    assert first_total(asset.asof) - first_total(None) == pytest.approx(added)
    assert first_total(add_months(start, 2)) == first_total(None)


def test_a_salary_without_gross_carries_no_depot_contribution() -> None:
    """A carried depot takes the contribution of a year only with a salary that pays, as the
    engine opens the year (`YearAcc.compulsory`): one at factor 0 in its phase counts as none."""
    depot = AvDepot(
        id="av", kind="av_depot", value=1000, start=date(2027, 1, 1), asof=date(2027, 6, 30)
    )

    def carried(*factors: float) -> float:
        streams = [
            Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None, factor={"work": f})
            for f in factors
        ]
        return carry.depot(plan(streams, [depot]), depot, date(2027, 12, 1))

    assert carried(0) == carried() == 1000
    assert carried(1) > 1000


def _rv_and_capital_tax(start: date = date(2026, 1, 1), **year: int) -> tuple[float, float]:
    """The RV and the capital gains tax of a year with a salary of twice the BBG and interest
    on fixed income, in the tax year `year` if given. The tariff stays above the flat rate."""
    p = plan(
        [Stream(name="salary", kind=StreamKind.SALARY, gross=20_000, index=None)],
        [
            cash(),
            FixedIncomeAsset(id="f", kind="fixed_income", value=100_000),
        ],
        tax={"sparer_pauschbetrag": 0, **year},
        start=start,
    )
    returns = zero_returns(12)
    returns.rates["fixed_income"][:] = 0.005
    r = simulate(p, returns, "fixed")
    return float(booked(r, "RV").sum()), float(r.capital_taxes[0].sum())


@pytest.mark.parametrize(
    ("constant", "factor", "changed"),
    [("sv_bbg_month", 2.0, 0), ("abgeltungsteuer_rate", 0.5, 1)],
)
def test_the_tax_year_of_the_plan_sets_the_sv_bases_and_the_flat_tax(
    later_tax_year: Callable[..., int], constant: str, factor: float, changed: int
) -> None:
    """A year file of twice the BBG doubles the RV, one of half the flat rate halves the capital
    gains tax, and neither changes the other."""
    later = later_tax_year(**{constant: getattr(TY, constant) * factor})
    before, after = _rv_and_capital_tax(year=TY.year), _rv_and_capital_tax(year=later)
    assert after[changed] == pytest.approx(before[changed] * factor)
    assert after[1 - changed] == pytest.approx(before[1 - changed])


NEWEST = TAX_YEARS[-1]


@pytest.mark.parametrize(
    ("start", "takes"),
    [
        (TAX_YEARS[0] - 1, TAX_YEARS[0]),
        (NEWEST, NEWEST),
        (NEWEST + 1, NEWEST + 1),
        (NEWEST + 5, NEWEST + 1),
    ],
)
def test_a_plan_without_a_tax_year_takes_the_newest_file_up_to_its_start(
    later_tax_year: Callable[..., int], start: int, takes: int
) -> None:
    """The engine applies the constants in euros of the start: a year file after the newest, of
    twice the BBG, serves the plans that start in its year or later, not the earlier ones."""
    later_tax_year(sv_bbg_month=TY.sv_bbg_month * 2)
    begin = date(start, 1, 1)
    assert _rv_and_capital_tax(begin) == pytest.approx(_rv_and_capital_tax(begin, year=takes))


@pytest.mark.parametrize(("first_age", "onset"), [(40, 0), (49.25, 3)])
def test_care_episode_costs_and_is_reported(first_age: float, onset: int) -> None:
    """Born 1977-01, so 49.25 is reached in the fourth month: no care before the hazard table."""
    care = {
        "hazard": [{"age": first_age, "factor": 1.0}],
        "cost": 1000,
        "index": None,
        "duration": {"mean": 2, "stdev": 0},
    }
    p = plan([], [cash(100_000)], care=care)
    r = zero_run(p, onset + 4, 3)
    episode = slice(onset, onset + 2)
    assert r.care[:, episode].all() and r.care.sum() == 3 * 2
    assert r.expenses[:, onset].tolist() == [-1000.0] * 3
    assert r.expenses[:, onset + 3].tolist() == [0.0] * 3
    single = zero_run(p, 4)
    assert not single.care.any()


def test_sale_price_spread_across_paths() -> None:
    scenario = Scenario(
        name="s",
        events=[SellEvent(at=date(2026, 2, 1), type="sell", asset="h", price_stdev=0.1)],
    )
    p = plan(
        [],
        [
            cash(),
            PropertyAsset(id="h", kind="property", sqm=100, per_sqm=1000),
        ],
        scenario,
        cash_buffer_months=0,
    )
    r = zero_run(p, 2, 500)
    prices = r.liquid[:, 1]
    assert 95_000 < prices.mean() < 105_000
    assert 5_000 < prices.std() < 15_000


def test_sales_in_another_order_draw_the_same_prices() -> None:
    """Each asset draws its own prices, so the order of the sales changes no price."""

    def sold(*order: str) -> RunResult:
        houses = [
            PropertyAsset(id=h, kind="property", sqm=100, per_sqm=per_sqm)
            for h, per_sqm in (("h", 1000), ("g", 3000))
        ]
        scenario = Scenario(
            name="s",
            events=[
                SellEvent(at=date(2026, 2 + i, 1), type="sell", asset=h, price_stdev=0.1)
                for i, h in enumerate(order)
            ],
        )
        p = plan([], [cash(), *houses], scenario)
        return zero_run(p, 4, 50)

    assert np.array_equal(sold("h", "g").total[:, -1], sold("g", "h").total[:, -1])


@pytest.mark.parametrize(("price", "spread"), [(0.0, 0.0), (None, 0.6)])
def test_a_sale_takes_the_property_out_on_every_path(price: float | None, spread: float) -> None:
    """A gift at a price of 0 and a wide spread of the price: every path sells, so the tagged
    stream ends and the one after the sale starts, and no path pays into the sale."""
    scenario = Scenario(
        name="s",
        events=[
            SellEvent(at=date(2026, 2, 1), type="sell", asset="h", price=price, price_stdev=spread)
        ],
    )
    p = plan(
        [
            Stream(name="upkeep", amount=-100, tags=["h"], index=None),
            Stream(name="rent", amount=-500, after_sale_of="h", index=None),
        ],
        [
            cash(10_000),
            PropertyAsset(id="h", kind="property", sqm=100, per_sqm=1000, tags=["h"]),
        ],
        scenario,
    )
    r = zero_run(p, 3, 1000)
    assert np.array_equal(r.total[:, 1:], r.liquid[:, 1:])
    assert (r.expenses[:, 1:] == -500).all()
    assert (r.liquid[:, 1] >= r.liquid[:, 0] - 500).all()


def test_set_stream_changes_the_row_that_runs_and_keeps_a_later_raise() -> None:
    """A later row of the name is a change after the event and keeps its amount. Before the
    first row of a name the event changes the next one."""
    scenario = Scenario(
        name="e",
        events=[
            SetStreamEvent(at=date(2026, 2, 1), type="set_stream", name="rent", amount=-90),
            SetStreamEvent(at=date(2026, 2, 1), type="set_stream", name="club", amount=-30),
        ],
    )
    p = plan(
        [
            Stream(name="rent", amount=-100, end=date(2026, 4, 1), index=None),
            Stream(name="rent", amount=-120, start=date(2026, 4, 1), index=None),
            Stream(name="club", amount=-50, start=date(2026, 3, 1), index=None),
        ],
        [cash(10_000)],
        scenario,
    )
    r = zero_run(p, 5)
    assert r.expenses[0].tolist() == [-100.0, -90.0, -120.0, -150.0, -150.0]


def test_a_stream_that_repays_a_loan_ends_with_its_sale() -> None:
    """After the sale that ends it the loan receives nothing and the cash pays nothing."""

    def repaid(*events: SellEvent) -> RunResult:
        vl = {"name": "vl", "kind": "other_income", "amount": 100, "index": None}
        p = plan(
            [Stream.model_validate(vl | {"repays": "l", "tags": ["h"]})],
            [
                cash(),
                PropertyAsset(id="h", kind="property", sqm=1, per_sqm=1, tags=["h"]),
                Loan(id="l", kind="loan", balance=-10_000, rate=0.0, annuity=1),
            ],
            Scenario(name="s", events=list(events)),
            cash_buffer_months=0,
        )
        return zero_run(p, 4)

    sold = repaid(SellEvent(at=date(2026, 3, 1), type="sell", asset="h"))
    kept = repaid()
    assert (sold.expenses[0, 2:] == -1.0).all()  # the annuity alone
    assert (kept.expenses[0, 2:] == -101.0).all()


def test_age_curve_scales_expenses_but_not_health() -> None:
    spending = {"age_curve": [{"age": 40, "factor": 1.0}, {"age": 50, "factor": 0.5}]}
    p = plan(
        [Stream(name="food", amount=-100), Stream(name="kk", amount=-100, health="kv")],
        [cash(10_000)],
        spending=spending,
        person=Person(born=date(1976, 1, 1)),  # 50 at start
    )
    r = zero_run(p, 1)
    assert r.expenses[0, 0] == pytest.approx(-150.0)


def test_prepayment_penalty_applies_inside_the_fixed_period() -> None:
    """Without `fixed_until` the rate, and so the penalty, holds for the whole term."""

    def repay_at(at: date, fixed_until: date | None = date(2026, 3, 31)) -> float:
        loan = Loan(
            id="l",
            kind="loan",
            balance=-100_000,
            rate=0.0,
            annuity=100,
            fixed_until=fixed_until,
            prepayment_penalty=0.1,
        )
        scenario = Scenario(name="r", events=[RepayEvent(at=at, type="repay", loan="l")])
        p = plan([], [cash(200_000), loan], scenario)
        return float(zero_run(p, 6).liquid[0, 5])

    inside = repay_at(date(2026, 3, 1))  # the fixed_until month still costs the penalty
    after = repay_at(date(2026, 4, 1))
    assert after - inside == pytest.approx(0.1 * (100_000 - 2 * 100))
    assert after - repay_at(date(2026, 4, 1), None) == pytest.approx(0.1 * (100_000 - 3 * 100))


@pytest.mark.parametrize(("month", "sold"), [(6, True), (12, False)])
def test_the_december_bill_comes_out_of_the_cash_in_december(month: int, *, sold: bool) -> None:
    """A taxable lump sum: its bill and the sale that pays it land in December, January has
    nothing left to pay. The lump sum of a December pays it before the surplus is invested, so
    no equity is sold and bought back."""
    lump = {"at": date(2026, month, 1), "type": "lump_sum", "amount": 200_000, "taxable": True}
    p = plan(
        [],
        [CASH, EquityAsset(id="e", kind="equity", value=300_000, cost_basis=0)],
        Scenario.model_validate({"name": "l", "events": [lump]}),
        cash_buffer_months=0,
    )
    r = zero_run(p, 14)
    assert r.taxes[0, 11] < -50_000
    assert r.taxes[0, 12] == pytest.approx(0.0)
    assert (r.liquid[0] >= 0).all()
    assert bool(r.capital_taxes[0, 11] < 0) == sold


def test_set_add_and_end_stream_events() -> None:
    scenario = Scenario(
        name="e",
        events=[
            SetStreamEvent(at=date(2026, 2, 1), type="set_stream", name="rent", amount=-200),
            AddStreamEvent(
                at=date(2026, 3, 1),
                type="add_stream",
                stream=Stream(name="club", amount=-50, tags=["fun"], index=None),
            ),
            EndStreamsEvent(at=date(2026, 4, 1), type="end_streams", tags=["fun"], names=["rent"]),
        ],
    )
    p = plan(
        [Stream(name="rent", amount=-100, index=None)],
        [cash(10_000)],
        scenario,
    )
    r = zero_run(p, 5)
    assert r.expenses[0].tolist() == [-100.0, -200.0, -250.0, 0.0, 0.0]


@pytest.mark.parametrize("rent", [0, -9000])  # the rent overdraws the cash: its rate costs
def test_noncash_income_is_what_the_assets_gain_beyond_the_flows(rent: int) -> None:
    """The growth, the employer's bAV contribution, the Zulage and the severance part paid
    into a policy: what the assets gain that no flow of the engine totals brings. A premium
    from the cash is a move and no income, the other side of a flow (`DRAW`, `MOVED`) books
    what it puts into a policy or draws out of it. In nominal euros: each entry times the price
    level of its year."""
    months = 30
    rates = {"equity": 0.005, "fixed_income": 0.002, "cash": 0.001, "property": 0.001}
    rates |= {"gold": 0.004, "bitcoin": 0.01}
    returns = Returns(
        rates={name: np.full((1, months), rate) for name, rate in rates.items()},
        inflation=np.full((1, months), 0.003),
    )
    deposit = TermDeposit(
        id="d",
        kind="term_deposit",
        value=10_000,
        rate=0.03,
        start=date(2025, 6, 1),
        matures=date(2027, 3, 15),
    )
    assets: list[object] = [
        cash(10_000),
        FixedIncomeAsset(id="f", kind="fixed_income", value=20_000),
        EquityAsset(id="e", kind="equity", value=100_000, cost_basis=80_000),
        deposit,
        PropertyAsset(id="p", kind="property", sqm=50, per_sqm=4000),
        PensionPolicy(  # pays an annuity from its capital, which then earns nothing
            id="b",
            kind="bav",
            value=5000,
            paid=4000,
            contribution=0,
            phases=[],
            matures=date(2027, 6, 1),
            growth="equity",
            cost=0.01,
            payout="annuity",
            annuity_per_10k=40,
        ),
        PensionPolicy(  # a Basisrente: a premium of its own in each month of `work`
            id="r",
            kind="bav",
            value=0,
            paid=0,
            premium=100,
            phases=["work"],
            matures=date(2040, 1, 1),
            growth="equity",
            payout="annuity",
            annuity_per_10k=40,
            basisrente=True,
        ),
        PensionPolicy(  # the employer pays in each month of `work`
            id="k",
            kind="bav",
            value=0,
            paid=0,
            contribution=300,
            phases=["work"],
            matures=date(2040, 1, 1),
            growth="equity",
        ),
        AvDepot(  # a salary in 2027: the contribution and the Zulage in December
            id="a",
            kind="av_depot",
            value=3000,
            contribution=1800,
            start=date(2027, 1, 1),
            cost=0.002,
        ),
        gold(5000, (date(2025, 12, 1), 4000), cost=0.01),  # the rent sells it
        CryptoAsset(id="x", kind="crypto", value=3000),
    ]
    streams = [
        Stream(name="Gehalt", kind=StreamKind.SALARY, gross=4000, index=None),
        Stream(name="ETF", kind=StreamKind.SAVINGS, amount=-500),  # a rent pauses the plans
        Stream(name="Coins", kind=StreamKind.SAVINGS, amount=-150, into="x", every=3),
    ]
    streams += [Stream(name="Miete", amount=rent, index=None)] if rent else []
    events = [
        SeveranceEvent(
            at=date(2027, 2, 1),
            type="severance",
            gross=50_000,
            bav=PolicyFunding(policy="k", amount=20_000),
        ),
        FundPolicyEvent(at=date(2026, 9, 1), type="fund_policy", policy="r", amount=5000),
        # the tax and the costs leave the net worth in the totals, the price moves into it
        BuyPropertyEvent.model_validate(purchase(date(2026, 5, 1), price=60_000, costs=0.03)),
    ]
    r = simulate(plan(streams, assets, Scenario(name="t", events=events)), returns, "fixed")
    assert r.ledger is not None
    book = r.ledger.entries
    _, level = levels(returns)

    def entries(*sides: str) -> FloatArray:
        rows = (row for (s, *_), row in book.items() if s in sides)
        return np.asarray(level * sum(rows, np.zeros(months)), dtype=float)

    held = sum(
        r.nominal_balance[c]
        for c in ("cash", "fixed_income", "equity", "gold", "crypto", "property", "policies")
    )
    opening = 10_000 + 20_000 + 100_000 + deposit.value_at(date(2026, 1, 1)) + 200_000 + 8000
    opening += 5000 + 3000
    # the annuity counts as income but comes out of the policy: no new wealth
    flows = (r.income + r.expenses + r.taxes + r.capital_taxes)[0] + entries(DRAW, MOVED)
    moves = entries(MOVE_IN) - entries(MOVE_OUT)
    assert np.diff(held, prepend=opening) == pytest.approx(entries(NONCASH) + flows + moves)
    assert entries(DRAW)[-1] < 0
    assert (r.balance["cash"] < 0).any() == bool(rent)


def test_stream_events_before_the_start_still_apply() -> None:
    """Moving `start` past a premium change must not bring the old premium back."""
    scenario = Scenario(
        name="p",
        events=[
            SetStreamEvent(at=date(2025, 6, 1), type="set_stream", name="kk", amount=-700),
            EndStreamsEvent(at=date(2025, 6, 1), type="end_streams", names=["gone"]),
        ],
    )
    p = plan(
        [Stream(name="kk", amount=-500), Stream(name="gone", amount=-100)],
        [cash(10_000)],
        scenario,
    )
    r = zero_run(p, 2)
    assert r.expenses[0, 0] == pytest.approx(-700)
    assert not [m for m in r.markers if m.kind in ("set_stream", "end_streams")]


def test_invest_action_keeps_the_cash_buffer() -> None:
    scenario = Scenario(
        name="s",
        events=[
            SellEvent(
                at=date(2026, 2, 1),
                type="sell",
                asset="h",
                then=[RepayAction(repay="l"), InvestAction(invest="portfolio")],
            )
        ],
    )
    p = plan(
        [Stream(name="x", amount=-1000)],  # the helper keeps 1000 months of it as buffer
        [
            cash(5000),
            PropertyAsset(id="h", kind="property", sqm=100, per_sqm=1000),
            Loan(id="l", kind="loan", balance=-40_000, rate=0.0, annuity=100),
        ],
        scenario,
    )
    r = zero_run(p, 3)
    assert r.balance["equity"][2] == pytest.approx(100_000 - 39_900)
    assert r.balance["cash"][2] == pytest.approx(5000 - 100 - 3 * 1000)


def test_write_off_takes_an_equity_asset_out_of_the_depot() -> None:
    scenario = Scenario(
        name="w",
        events=[WriteOffEvent(at=date(2026, 3, 1), type="write_off", asset="shares")],
    )
    p = plan(
        [],
        [
            cash(),
            EquityAsset(id="depot", kind="equity", value=100_000, cost_basis=60_000),
            EquityAsset(id="shares", kind="equity", value=10_000, cost_basis=0),
        ],
        scenario,
    )
    rising = zero_returns(4)
    rising.rates["equity"][:] = 0.10
    r = simulate(p, rising, "fixed")
    assert r.balance["equity"][1] == pytest.approx(110_000 * 1.21)
    assert r.balance["equity"][2] == pytest.approx(100_000 * 1.331)  # left at its grown value
    assert not r.income.any()
    assert not r.capital_taxes.any()


def _bought(*events: dict[str, object], months: int = 12, **kw: object) -> RunResult:
    """A run with 400,000 € of cash."""
    scenario = Scenario.model_validate({"name": "s", "events": events})
    p = plan([], [cash(400_000)], scenario, **kw)
    return zero_run(p, months)


@pytest.mark.parametrize("sold", [False, True])
def test_a_purchase_costs_the_net_worth_its_tax_and_costs(sold: bool) -> None:
    """Without returns a sale a month later at the value changes nothing more."""
    sale = [{"at": date(2026, 4, 1), "type": "sell", "asset": "home"}] if sold else []
    r = _bought(purchase(), *sale)
    assert r.total[0, -1] == pytest.approx(400_000 - 300_000 * (0.05 + 0.02))
    assert (r.taxes[0].sum(), r.expenses[0].sum()) == pytest.approx((-15_000, -6000))


@pytest.mark.parametrize(
    ("at", "land_tax", "rate"),
    [
        (date(2026, 3, 1), {"land": "BY"}, 0.035),
        (date(2026, 3, 1), {"land": "NW"}, 0.065),
        (date(2026, 3, 1), {"land": None, "transfer_tax": 0.0}, 0.0),  # from the parents
        (date(2025, 6, 1), {"land": "HB"}, 0.05),  # the rate of the day of the purchase
        (date(2025, 7, 1), {"land": "HB"}, 0.055),
    ],
)
def test_the_transfer_tax_is_the_rate_of_the_land_at_the_purchase(
    at: date, land_tax: dict[str, object], rate: float
) -> None:
    """§11 GrEStG and the rates of the Länder; §3 Nr. 6 exempts a purchase from the parents."""
    r = _bought(purchase(at, **land_tax), months=24, start=date(2025, 1, 1))
    assert r.taxes[0].sum() == pytest.approx(-300_000 * rate)


def test_the_loan_of_a_purchase_pays_like_one_of_the_file_from_the_month_after() -> None:
    """Its first annuity is due a month after the purchase, `fixed_for` counts from it."""
    terms = {"id": "l", "balance": -200_000, "rate": 0.03, "annuity": 1200, "fixed_for": 24}
    bought = _bought(purchase(loan=terms), months=36, refinance_rate=0.06)
    loan = Loan(
        id="l",
        kind="loan",
        balance=-200_000,
        rate=0.03,
        annuity=1200,
        fixed_until=date(2028, 3, 1),
    )
    p = plan([], [cash(400_000), loan], start=date(2026, 4, 1), refinance_rate=0.06)
    file = zero_run(p, 33)
    loans = bought.nominal_balance["loans"]
    assert loans[2] == -200_000
    assert loans[3:] == pytest.approx(file.nominal_balance["loans"])


def test_a_conditional_sale_waits_for_the_purchase() -> None:
    """An age reached before the purchase sells in the month after it."""
    sale: dict[str, object] = {"type": "sell", "asset": "home", "when": {"age": 40}}
    r = _bought(sale, purchase(date(2026, 6, 1)))
    assert [m for m in marked(r) if "home" in m] == [
        "2026-06 buy_property: home",
        "2026-07 sell: home",
    ]


def test_a_purchase_takes_the_cash_then_fixed_income_then_equity() -> None:
    assets: list[object] = [
        cash(50_000),
        FixedIncomeAsset(id="f", kind="fixed_income", value=100_000),
        EquityAsset(id="e", kind="equity", value=200_000, cost_basis=200_000),
    ]
    scenario = Scenario.model_validate({"name": "s", "events": [purchase()]})
    r = zero_run(plan([], assets, scenario), 4)
    held = {c: r.nominal_balance[c][2] for c in ("cash", "fixed_income", "equity", "property")}
    assert held == pytest.approx(
        {"cash": 0, "fixed_income": 0, "equity": 200_000 - 171_000, "property": 300_000}
    )


def test_a_set_stream_factor_of_zero_ends_the_pay_like_an_end_of_the_stream() -> None:
    """The month of `pay_ends` follows what the salary pays, a factor set by an event included."""
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None)
    at = date(2026, 3, 1)
    stopped = Scenario(
        name="s", events=[SetStreamEvent(at=at, type="set_stream", name="pay", factor=0)]
    )
    ended = Scenario(name="s", events=[EndStreamsEvent(at=at, type="end_streams", names=["pay"])])
    ends = [
        simulate(plan([pay], [cash()], s), zero_returns(6), "fixed").pay_ends
        for s in (stopped, ended)
    ]
    assert ends[0] == ends[1] == 2
