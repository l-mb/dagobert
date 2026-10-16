"""The holdings of a run: the rebalancing, the flat tax and its loss pot, interest and term
deposits, the Vorabpauschale, the savings plans, and the private sales of gold, crypto and
property (§23 EStG)."""

from datetime import date

import numpy as np
import pytest
from builders import booked, cash, gold, phases, plan, purchase, zero_returns, zero_run

from dagobert import budget
from dagobert.engine.simulation import Engine, simulate
from dagobert.model.assets import (
    CryptoAsset,
    EquityAsset,
    FixedIncomeAsset,
    PropertyAsset,
    TermDeposit,
)
from dagobert.model.events import (
    BuyEvent,
    Event,
    LumpSumEvent,
    SaleTrigger,
    SellEvent,
    WriteOffEvent,
)
from dagobert.model.months import add_months
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import MOVE_OUT, SAVINGS_PLAN, TAX, RunResult
from dagobert.tax import flat_rate, for_year, income_tax

TY = for_year(2026)


def test_allocation_splits_surplus_and_rebalances_after_gain() -> None:
    alloc = {
        "fixed_income": [{"age": 40, "share": 0.5}],
        "rebalance_every": 12,
        "skip_after_loss": 12,
    }
    p = plan(
        [Stream(name="pay", kind=StreamKind.OTHER_INCOME, amount=1000)],
        [EquityAsset(id="e", kind="equity", value=10_000, cost_basis=0)],
        cash_buffer_months=0,
        allocation=alloc,
    )
    r = zero_run(p, 14)
    latent = 10_000 * flat_rate(0.0, TY) * 0.7
    assert r.liquid[0, 0] == pytest.approx(11_000 - latent)
    assert r.capital_taxes[0, 11] == pytest.approx(0.0)
    assert r.capital_taxes[0, 12] < 0  # rebalance at month 12 sold equity with gains
    # the final settlement refunds it: 12k other income stays below the Grundfreibetrag
    assert r.capital_taxes[0, 13] == pytest.approx(-r.capital_taxes[0, 12])
    assert r.taxes[0, 13] == pytest.approx(0.0)


def test_rebalance_skipped_after_equity_loss() -> None:
    alloc = {"fixed_income": [{"age": 40, "share": 0.5}], "rebalance_every": 1}
    p = plan(
        [],
        [EquityAsset(id="e", kind="equity", value=10_000, cost_basis=10_000)],
        cash_buffer_months=0,
        allocation=alloc,
    )
    z = zero_returns(3)
    z.rates["equity"][0, 1] = -0.1
    r = simulate(p, z, "fixed")
    assert r.liquid[0, 2] == pytest.approx(9000)
    assert r.taxes[0].tolist() == [0.0, 0.0, 0.0]


def test_a_loss_on_fixed_income_carries_into_the_next_year() -> None:
    """2026 loses 0.5% a month on 100,000 of fixed income, 2027 earns 1%. The loss of 2026
    offsets the interest of 2027. Other income keeps the tariff above the flat rate, a small
    expense keeps a cash buffer that pays the December bill."""
    p = plan(
        [
            Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=10_000, index=None),
            Stream(name="living", amount=-100, index=None),
        ],
        [
            cash(),
            FixedIncomeAsset(id="f", kind="fixed_income", value=100_000),
        ],
        tax={"sparer_pauschbetrag": 0},
    )
    returns = zero_returns(24)
    returns.rates["fixed_income"][:, :12] = -0.005
    returns.rates["fixed_income"][:, 12:] = 0.01
    r = simulate(p, returns, "fixed")
    loss = 100_000 * (1 - 0.995**12)
    interest = 100_000 * 0.995**12 * (1.01**12 - 1)
    assert -r.capital_taxes[0, :12].sum() == pytest.approx(0.0)
    assert -r.capital_taxes[0, 12:].sum() == pytest.approx(
        (interest - loss) * flat_rate(0.0, TY), rel=1e-6
    )


SEED = 5_000.0


def _interest(rate: float, **tax: float) -> tuple[RunResult, float]:
    """A year of 100,000 € of fixed income at `rate` a month without a Sparer-Pauschbetrag, and
    the loss pot (§20 Abs. 6 EStG) at its end. Other income keeps the tariff above the flat rate,
    so the Günstigerprüfung refunds nothing."""
    p = plan(
        [
            Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=10_000, index=None),
            Stream(name="living", amount=-100, index=None),
        ],
        [cash(), FixedIncomeAsset(id="f", kind="fixed_income", value=100_000)],
        tax={"sparer_pauschbetrag": 0} | tax,
    )
    returns = zero_returns(12)
    returns.rates["fixed_income"][:] = rate
    engine = Engine(p, returns, "fixed")
    return engine.run(), float(engine.losses[0])


@pytest.mark.parametrize("rate", [0.01, 0.002, 0.0], ids=["above the pot", "below it", "none"])
def test_a_capital_loss_carried_to_the_start_offsets_later_capital_income(rate: float) -> None:
    """`tax.capital_losses` seeds the loss pot: the interest pays less flat tax, and the pot
    shrinks by the interest that it offsets, at most to 0; without interest it stays."""
    (plain, _), (seeded, pot) = _interest(rate), _interest(rate, capital_losses=SEED)
    offset = (seeded.capital_taxes.sum() - plain.capital_taxes.sum()) / flat_rate(0.0, TY)
    interest = 100_000 * ((1 + rate) ** 12 - 1)
    assert offset == pytest.approx(min(interest, SEED))
    assert pot == pytest.approx(SEED - offset)


def test_a_capital_loss_of_zero_changes_nothing() -> None:
    (plain, _), (zero, _) = _interest(0.01), _interest(0.01, capital_losses=0)
    for name in ("income", "expenses", "taxes", "capital_taxes", "liquid", "total"):
        np.testing.assert_array_equal(getattr(zero, name), getattr(plain, name))


def test_fixed_income_interest_is_taxed_in_december() -> None:
    p = plan(
        [Stream(name="Gehalt", kind=StreamKind.SALARY, gross=8000)],
        [FixedIncomeAsset(id="f", kind="fixed_income", value=120_000)],
    )
    returns = zero_returns(12)
    returns.rates["fixed_income"][:, :6] = 0.01
    returns.rates["fixed_income"][:, 6] = -0.02  # a losing month offsets interest of the year
    r = simulate(p, returns, "fixed")

    interest = 120_000 * (1.01**6 * 0.98 - 1)
    assert r.capital_taxes[0, :11].tolist() == [0.0] * 11
    assert r.capital_taxes[0, 11] == pytest.approx(-(interest - 1000) * flat_rate(0.0, TY))


def test_term_deposit_pays_compounded_interest_and_tax_at_maturity() -> None:
    deposit = TermDeposit(
        id="t",
        kind="term_deposit",
        value=10_000,
        rate=0.10,
        start=date(2024, 3, 1),
        matures=date(2026, 3, 1),
    )
    p = plan([], [deposit], cash_buffer_months=0)
    r = zero_run(p, 4)

    paid = 10_000 * 1.10 ** (730 / 365)
    # the Sparer-Pauschbetrag, no Teilfreistellung
    tax_due = (paid - 10_000 - 1000) * flat_rate(0.0, TY)
    accrued = deposit.value_at(date(2026, 1, 1))
    assert r.liquid[0, 0] == pytest.approx(accrued - (accrued - 10_000) * flat_rate(0.0, TY))
    assert r.liquid[0, 2] == pytest.approx(paid - tax_due)
    assert r.capital_taxes[0, :3].tolist() == pytest.approx([0.0, 0.0, -tax_due])
    # without other income the Günstigerprüfung refunds the tax in the final settlement
    assert r.liquid[0, 3] == pytest.approx(paid)


def test_deficit_skips_a_term_deposit_and_sells_equity() -> None:
    deposit = TermDeposit(
        id="t",
        kind="term_deposit",
        value=10_000,
        rate=0.0,
        start=date(2025, 1, 1),
        matures=date(2030, 1, 1),
    )
    depot = EquityAsset(id="e", kind="equity", value=5_000, cost_basis=5_000)
    p = plan([Stream(name="Miete", amount=-1000, index=None)], [deposit, depot])
    r = zero_run(p, 8)

    assert r.balance["fixed_income"].tolist() == [10_000.0] * 8
    assert r.balance["equity"].tolist() == [4000.0, 3000.0, 2000.0, 1000.0, 0.0, 0.0, 0.0, 0.0]
    assert r.balance["cash"][-1] == pytest.approx(-3000.0)
    assert not r.broke.any()  # the locked deposit still counts as liquid net worth


def test_a_sale_for_the_december_bill_joins_the_guenstigerpruefung() -> None:
    """Other income of 15,600 owes its tax only in December. Cash is spent, so equity with an
    80% gain share pays the bill. Its gain is taxed at the tariff when that is lower."""
    p = plan(
        [
            Stream(name="rent in", kind=StreamKind.OTHER_INCOME, amount=1300, index=None),
            Stream(name="living", amount=-1300, index=None),
        ],
        [
            cash(),
            EquityAsset(id="e", kind="equity", value=10_000, cost_basis=2_000),
        ],
        tax={"sparer_pauschbetrag": 0},
    )
    r = zero_run(p, 12)
    rate = flat_rate(0.0, TY)
    zve = 15_600 - TY.sonderausgaben_pauschbetrag
    bill = float(income_tax(zve, TY))
    taxable = 0.7 * 0.8 * bill / (1 - rate * 0.7 * 0.8)
    tariff = float(income_tax(zve + taxable, TY)) - bill
    assert tariff < rate * taxable
    assert -r.capital_taxes[0].sum() == pytest.approx(tariff, abs=1.5)


def test_vorabpauschale_ignores_purchases_in_a_falling_market() -> None:
    """Money invested during the year is no growth: a falling fund owes no Vorabpauschale."""
    p = plan(
        [],
        [
            cash(300_000),
            EquityAsset(id="e", kind="equity", value=100_000, cost_basis=100_000),
        ],
        cash_buffer_months=0,
    )
    falling = zero_returns(12)
    falling.rates["equity"][:] = -0.01
    r = simulate(p, falling, "fixed")
    assert r.capital_taxes[0].sum() == pytest.approx(0.0)


def test_vorabpauschale_counts_only_what_was_held_all_year() -> None:
    """The salary stays in the cash (`invest_rest` off): only the sales change the units."""

    def december_tax(*spending: Stream) -> float:
        p = plan(
            # a salary keeps the Günstigerprüfung off
            [Stream(name="g", kind=StreamKind.SALARY, gross=20_000), *spending],
            [
                cash(),
                EquityAsset(id="e", kind="equity", value=1_000_000, cost_basis=1_000_000),
            ],
            invest_rest=False,
            tax={"sparer_pauschbetrag": 0},
        )
        rising = zero_returns(12)
        rising.rates["equity"][:] = 0.01
        return float(simulate(p, rising, "fixed").capital_taxes[0, 11])

    full = -1_000_000 * 0.7 * TY.basiszins * 0.7 * flat_rate(0.0, TY)
    assert december_tax() == pytest.approx(full)
    # about a fifth was sold by December
    assert full + 300 < december_tax(Stream(name="x", amount=-30_000)) < 0


@pytest.mark.parametrize(
    ("moves", "saved", "base"),
    [
        ({1: 12_000}, {}, 100_000 + 12_000),
        ({7: 12_000}, {}, 100_000 + 12_000 * 6 / 12),  # BMF 2019-05-21 Rz. 18.11: bought in July
        ({11: 12_000}, {}, 100_000 + 12_000 * 2 / 12),
        ({3: -30_000, 6: 12_000}, {}, 70_000 + 12_000 * 7 / 12),  # the sale takes January units
        # a savings plan buys before the settlement, units at the price after the return
        ({}, {12: 12_000}, 100_000 + 12_000 / 1.05 / 12),
    ],
    ids=["january", "july", "november", "sale before purchase", "december plan"],
)
def test_vorabpauschale_of_a_purchase_counts_a_twelfth_per_month_held(
    moves: dict[int, float], saved: dict[int, float], base: float
) -> None:
    """§18 Abs. 2 InvStG: in the year of the purchase a twelfth less for every full month before
    the month of the purchase. The price stays until a December return of 5%, above the
    Basisertrag, so the amount per January euro is the Basisertrag. A December salary, invested
    after the settlement, keeps the Günstigerprüfung off."""
    events: list[Event] = [
        LumpSumEvent(at=date(2026, month, 1), type="lump_sum", amount=amount)
        for month, amount in moves.items()
    ]
    once = [
        Stream(
            name=f"plan {month}",
            kind=StreamKind.SAVINGS,
            amount=-amount,
            start=date(2026, month, 1),
            end=add_months(date(2026, month, 1), 1),
        )
        for month, amount in saved.items()
    ]
    december_salary = Stream(
        name="g", kind=StreamKind.SALARY, gross=100_000, start=date(2026, 12, 1)
    )
    p = plan(
        [december_salary, *once],
        [
            cash(),
            EquityAsset(id="e", kind="equity", value=100_000, cost_basis=100_000),
        ],
        Scenario(name="t", events=events),
        cash_buffer_months=0,
        tax={"sparer_pauschbetrag": 0},
    )
    december = zero_returns(12)
    december.rates["equity"][:, 11] = 0.05
    vorab = base * TY.basisertrag_share * TY.basiszins
    tax = vorab * 0.7 * flat_rate(0.0, TY)
    assert simulate(p, december, "fixed").capital_taxes[0, 11] == pytest.approx(-tax)


def _depot(
    exempt: float | None = None, value: float = 100_000, basis: float = 50_000, name: str = "e"
) -> EquityAsset:
    return EquityAsset(
        id=name, kind="equity", value=value, cost_basis=basis, teilfreistellung=exempt
    )


SELL_ALL = LumpSumEvent(at=date(2026, 6, 1), type="lump_sum", amount=-1_000_000)
SELL_SOME = LumpSumEvent(at=date(2026, 6, 1), type="lump_sum", amount=-60_000)


def _capital_tax(
    depots: list[EquityAsset],
    *events: Event,
    streams: tuple[Stream, ...] = (),
    rising: float = 0.0,
    balance: float = 0.0,
    default: float = 0.3,
) -> float:
    """The capital gains tax of a year of `depots` whose equity rises by `rising` a month. Its
    salary keeps the Günstigerprüfung off and stays in the cash, a lump sum out of the cash
    sells equity."""
    p = plan(
        [Stream(name="g", kind=StreamKind.SALARY, gross=8000, index=None), *streams],
        [cash(balance), *depots],
        Scenario(name="t", events=list(events)),
        tax={"sparer_pauschbetrag": 0, "teilfreistellung": default},
        invest_rest=False,
    )
    returns = zero_returns(12)
    returns.rates["equity"][:] = rising
    return -float(simulate(p, returns, "fixed").capital_taxes.sum())


@pytest.mark.parametrize("default", [0.15, 0.3])
def test_a_sale_pays_after_the_teilfreistellung_of_its_depot(default: float) -> None:
    """§20 InvStG: a real-estate fund keeps more of its gain free than an equity fund, a share
    none. A depot without its own takes that of the assumptions."""
    taxes = [_capital_tax([_depot(exempt)], SELL_SOME) for exempt in (0.6, 0.3, 0.0)]
    assert 0 < taxes[0] < taxes[1] < taxes[2]
    assert _capital_tax([_depot()], SELL_SOME, default=default) == pytest.approx(
        _capital_tax([_depot(default)], SELL_SOME)
    )


def test_two_depots_of_equal_gain_shares_pay_as_one_at_their_mean() -> None:
    halves = [_depot(0.3, 50_000, 25_000, "a"), _depot(0.6, 50_000, 25_000, "b")]
    assert _capital_tax(halves, SELL_SOME) == pytest.approx(_capital_tax([_depot(0.45)], SELL_SOME))


def test_a_purchase_after_a_gain_leaves_the_tax_of_that_gain() -> None:
    """The gain of a real-estate fund stays 60% free beside an equity fund bought later, which
    has gained nothing: a rate of the pool on its plain basis would tax it at 45%."""
    bought = Stream(
        name="ETF",
        kind=StreamKind.SAVINGS,
        amount=-100_000,
        start=date(2026, 2, 1),
        end=date(2026, 3, 1),
    )
    immo = [_depot(0.6)]
    assert _capital_tax(immo, SELL_ALL, streams=(bought,), balance=100_000) == pytest.approx(
        _capital_tax(immo, SELL_ALL, balance=100_000)
    )


def test_a_depot_written_off_at_the_start_pays_as_a_plan_without_it() -> None:
    shares = _depot(0.0, 10_000, 4_000, "rsu")
    off = WriteOffEvent(at=date(2026, 2, 1), type="write_off", asset="rsu")
    assert _capital_tax([_depot(0.6), shares], off, SELL_SOME) == pytest.approx(
        _capital_tax([_depot(0.6)], SELL_SOME)
    )


def test_a_savings_plan_buys_at_the_teilfreistellung_of_its_depot() -> None:
    """Shares bought each month beside a real-estate fund, at a gain when sold: more tax than
    the same plan into the default of 30%, less than shares in both depots."""

    def tax(immo: float, shares: float, into: str | None = "shares") -> float:
        plan = Stream(name="ESPP", kind=StreamKind.SAVINGS, amount=-2000, into=into)
        depots = [_depot(immo), _depot(shares, 0, 0, "shares")]
        return _capital_tax(depots, SELL_ALL, streams=(plan,), rising=0.01)

    assert tax(0.6, 0.6) < tax(0.6, 0.0, into=None) < tax(0.6, 0.0) < tax(0.0, 0.0)


def test_shares_pay_more_tax_on_the_vorabpauschale_than_an_equity_fund() -> None:
    """The Vorabpauschale of a rising year after the Teilfreistellung, none for shares: the
    pool is total return, and the Vorabpauschale stands in for their dividends."""
    december = [_capital_tax([_depot(exempt, basis=100_000)], rising=0.01) for exempt in (0.3, 0)]
    assert 0 < december[0] < december[1]


ETF = Stream(name="ETF", kind=StreamKind.SAVINGS, amount=-500)


WAGE = Stream(name="g", kind=StreamKind.SALARY, gross=5000, index=None)


def _run(
    streams: list[Stream],
    assets: list[object],
    months: int,
    scenario: Scenario | None = None,
    **kw: object,
) -> RunResult:
    """By default the rest stays in cash: without expenses the buffer holds none."""
    p = plan(streams, assets, scenario, **({"invest_rest": False} | kw))
    return zero_run(p, months)


def test_a_savings_plan_moves_cash_into_equity_and_changes_no_flow() -> None:
    """At zero returns the plan is a move between own accounts: equity up and cash down by what
    it paid, the totals and the flows as without it."""
    assets: list[object] = [cash()]
    without, saving = _run([WAGE], assets, 24), _run([WAGE, ETF], assets, 24)
    for c, change in (("equity", 24 * 500), ("cash", -24 * 500)):
        assert saving.balance[c][-1] - without.balance[c][-1] == pytest.approx(change)
    for field in ("total", "liquid", "income", "expenses", "taxes", "capital_taxes"):
        assert getattr(saving, field) == pytest.approx(getattr(without, field))
    assert saving.ledger is not None
    assert budget.from_ledger(saving.ledger, range(24)).saved == pytest.approx({"ETF": 500})
    assert not [m for m in saving.markers if m.kind == "savings plan"]


@pytest.mark.parametrize(
    ("balance", "rent", "paid", "paused"),
    [(0, -100, 0.0, date(2026, 1, 1)), (700, 0, 500.0, date(2026, 2, 1))],
    ids=["no cash", "all or nothing"],
)
def test_a_savings_plan_pauses_while_the_cash_falls_short(
    balance: float, rent: float, paid: float, paused: date
) -> None:
    """A path whose cash does not cover the rate skips it, without a catch-up, and the deficit
    cover sells nothing for it: with 200 € left the plan of 500 € pays nothing."""
    assets: list[object] = [
        cash(balance),
        EquityAsset(id="e", kind="equity", value=10_000, cost_basis=5000),
    ]
    streams = [Stream(name="rent", amount=rent, index=None)] if rent else []
    without, saving = _run(streams, assets, 12), _run([*streams, ETF], assets, 12)
    assert saving.balance["equity"][-1] - without.balance["equity"][-1] == pytest.approx(paid)
    assert saving.capital_taxes == pytest.approx(without.capital_taxes)
    paused_plans = [(m.month, m.detail) for m in saving.markers if m.kind == "savings plan"]
    assert paused_plans == [(paused, "ETF")]


def test_a_savings_plan_pays_in_its_months_and_phases() -> None:
    """`every: 3` from the start month, in `work` only. The run rate spreads what it paid."""
    quarterly = Stream(name="q", kind=StreamKind.SAVINGS, amount=-300, every=3, phases=["work"])
    scenario = Scenario(
        name="t", phases=phases((date(2026, 1, 1), "work"), (date(2026, 7, 1), "alt"))
    )
    r = _run([quarterly], [cash(10_000)], 12, scenario)
    assert r.ledger is not None
    paid = booked(r, "q", MOVE_OUT, SAVINGS_PLAN)
    assert np.flatnonzero(paid).tolist() == [0, 3]
    assert budget.from_ledger(r.ledger, [1, 2], run_rate=True).saved == pytest.approx({"q": 100})
    assert budget.from_ledger(r.ledger, [1, 2]).saved == {}


@pytest.mark.parametrize(
    ("sold", "capital_from", "taxed"),
    [
        (date(2026, 12, 1), None, "taxes"),  # within the holding period: a private sale
        (date(2027, 3, 1), None, None),  # after it: free
        (date(2027, 3, 1), date(2026, 1, 1), "capital_taxes"),  # bought under §20: flat tax
    ],
    ids=["private sale", "free", "capital"],
)
def test_a_crypto_plan_buys_lots_of_its_month(
    sold: date, capital_from: date | None, taxed: str | None
) -> None:
    """Each purchase of a plan into crypto starts its own holding period (§23 EStG), or falls
    under §20 from `crypto_capital_from`."""
    once = Stream(
        name="btc", kind=StreamKind.SAVINGS, amount=-10_000, into="x", end=date(2026, 2, 1)
    )

    def run(*events: Event) -> RunResult:
        p = plan(
            [WAGE, once],
            [
                cash(20_000),
                CryptoAsset(id="x", kind="crypto", value=0),
            ],
            Scenario(name="t", events=list(events)),
            tax={"crypto_capital_from": capital_from},
        )
        returns = zero_returns(24)
        returns.rates["bitcoin"][:] = 0.02
        return simulate(p, returns, "fixed")

    kept, sale = run(), run(SellEvent(at=sold, type="sell", asset="x"))
    more = {
        f: bool(getattr(sale, f).sum() < getattr(kept, f).sum() - 1)
        for f in ("taxes", "capital_taxes")
    }
    assert more == {f: f == taxed for f in more}


def test_without_investing_the_rest_only_the_plans_invest() -> None:
    """`invest_rest: false` keeps the surplus above the buffer in cash."""
    assets: list[object] = [cash()]
    invested = _run([WAGE], assets, 12, invest_rest=True)
    kept = _run([WAGE, ETF], assets, 12)
    assert kept.balance["equity"][-1] == pytest.approx(12 * 500)
    assert kept.balance["cash"][-1] + 12 * 500 == pytest.approx(invested.balance["equity"][-1])


def _year_taxes(assets: list[object], *events: object, months: int = 24) -> float:
    """Income tax, Soli and SV of the salary years with `assets` and `events`."""
    p = plan(
        [Stream(name="g", kind=StreamKind.SALARY, gross=4000)],
        [cash(), *assets],
        Scenario.model_validate({"name": "s", "events": events}),
    )
    return float(zero_run(p, months).taxes[0].sum())


@pytest.mark.parametrize(
    ("bought", "sold", "taxed"),
    [
        (date(2025, 3, 10), date(2026, 3, 1), True),
        (date(2025, 3, 10), date(2026, 4, 1), False),
        (date(2025, 1, 5), date(2026, 1, 1), True),  # twelve months before the start
        (date(2024, 12, 5), date(2026, 1, 1), False),  # thirteen: free from the start
        (date(2026, 1, 20), date(2027, 1, 1), True),  # in the start month
        (date(2026, 1, 20), date(2027, 2, 1), False),
    ],
)
def test_a_gain_is_free_once_a_year_has_passed_after_the_purchase_month(
    bought: date, sold: date, taxed: bool
) -> None:
    """§23 Abs. 1 S. 1 Nr. 2 EStG, counted in whole months: a lot bought in month P is free
    from P + 13."""
    bars = gold(30_000, (bought, 10_000))
    sale = SellEvent(at=sold, type="sell", asset="g")
    assert (_year_taxes([bars], sale) < _year_taxes([bars])) == taxed


@pytest.mark.parametrize(("share", "taxed"), [(0.5, False), (0.75, True)])
def test_a_sale_takes_the_free_units_first(share: float, taxed: bool) -> None:
    bars = gold(20_000, (date(2026, 1, 15), 5000), (date(2020, 1, 15), 5000))
    sale = SellEvent(at=date(2026, 2, 1), type="sell", asset="g", share=share)
    assert (_year_taxes([bars], sale, months=12) < _year_taxes([bars], months=12)) == taxed


def test_a_property_loss_offsets_a_gold_gain_of_the_same_year() -> None:
    bars = gold(30_000, (date(2025, 12, 1), 10_000))
    flat = PropertyAsset(id="h", kind="property", sqm=100, per_sqm=1000, bought_for=120_000)
    sales = [
        SellEvent(at=date(2026, 6, 1), type="sell", asset="g"),
        SellEvent(at=date(2026, 9, 1), type="sell", asset="h", taxable=True),
    ]
    unsold = _year_taxes([bars, flat], months=12)
    assert _year_taxes([bars, flat], sales[0], months=12) < unsold
    assert _year_taxes([bars, flat], *sales, months=12) == pytest.approx(unsold)


def test_a_loss_on_a_taxable_sale_does_not_shelter_the_salary() -> None:
    def taxes(bought_for: float) -> float:
        scenario = Scenario(
            name="s",
            events=[SellEvent(at=date(2026, 6, 1), type="sell", asset="h", taxable=True)],
        )
        p = plan(
            [Stream(name="g", kind=StreamKind.SALARY, gross=5000)],
            [
                cash(),
                PropertyAsset(
                    id="h", kind="property", sqm=100, per_sqm=1000, bought_for=bought_for
                ),
            ],
            scenario,
        )
        return float(zero_run(p, 12).taxes[0].sum())

    assert taxes(140_000) == pytest.approx(taxes(100_000))
    assert taxes(60_000) < taxes(100_000)  # a gain is taxed


@pytest.mark.parametrize(
    ("held", "taxable", "price", "taxed"),
    [
        (108, True, 400_000, True),
        (120, True, 400_000, True),  # sold in the month ten years after the purchase month
        (121, True, 400_000, False),  # free from the month after, as gold after twelve
        (108, False, 400_000, False),  # lived in by the owner
        (24, True, 321_000, False),  # at its cost with the tax and the costs: no gain
    ],
)
def test_a_bought_property_is_a_private_sale_for_ten_years(
    held: int, taxable: bool, price: float, taxed: bool
) -> None:
    """§23 Abs. 1 S. 1 Nr. 1 EStG in whole months; Abs. 3 S. 1: the Anschaffungskosten with the
    Nebenkosten."""
    depot = FixedIncomeAsset(id="f", kind="fixed_income", value=400_000)
    buy = purchase()
    sale = {"at": add_months(date(2026, 3, 1), held), "type": "sell", "asset": "home"}
    sale |= {"price": price, "taxable": taxable}
    months = held + 14
    assert (
        _year_taxes([depot], buy, sale, months=months) < _year_taxes([depot], buy, months=months)
    ) == taxed


@pytest.mark.parametrize(("bought", "switch"), [(False, True), (True, False), (True, True)])
def test_crypto_bought_after_the_switch_pays_the_flat_tax(bought: bool, switch: bool) -> None:
    """The BMF draft: a coin bought in or after `crypto_capital_from` is capital income
    without a holding period; one bought before stays a private sale, free after a year."""
    coins = CryptoAsset.model_validate(
        {
            "id": "b",
            "kind": "crypto",
            "value": 20_000,
            "trades": [
                {"date": date(2025, 6, 1), "kind": "buy", "security": "BTC"}
                | {"units": 0.2, "amount": 10_000}
            ],
        }
    )
    events = [
        *([BuyEvent(at=date(2026, 7, 1), type="buy", asset="b", amount=10_000)] if bought else []),
        SellEvent(at=date(2028, 1, 1), type="sell", asset="b"),
    ]
    switched = {"crypto_capital_from": date(2026, 6, 1)} if switch else {}
    p = plan(
        [],
        [cash(50_000), coins],
        Scenario(name="s", events=events),
        tax={"sparer_pauschbetrag": 0} | switched,
    )
    rising = zero_returns(30)
    rising.rates["bitcoin"][:] = 0.02
    r = simulate(p, rising, "fixed")
    assert bool(r.capital_taxes[0, 24] < 0) == (bought and switch)
    assert not r.taxes.any()  # the coins of the private sale are free after a year


def test_deficits_sell_the_free_units_of_every_pool_before_young_ones() -> None:
    p = plan(
        [Stream(name="x", amount=-3000, index=None)],
        [
            cash(),
            EquityAsset(id="e", kind="equity", value=1000, cost_basis=1000),
            gold(6000, (date(2025, 12, 1), 1000)),
            CryptoAsset(id="b", kind="crypto", value=4000),  # without trades: held for longer
        ],
    )
    r = zero_run(p, 3)
    assert r.balance["equity"].tolist() == [0.0] * 3
    assert r.balance["crypto"].tolist() == pytest.approx([2000, 0, 0])
    assert r.balance["gold"].tolist() == pytest.approx([6000, 5000, 2000])


def test_a_december_sale_for_the_bill_joins_the_private_sales_of_the_year() -> None:
    """Spending takes every income: the second deficit cover of December sells gold to pay
    the bill, and a young lot adds its gain to the settlement of the year. The cover sells
    again for that tax, until the year is paid in December."""

    def december(bought: date) -> RunResult:
        p = plan(
            [
                Stream(name="i", kind=StreamKind.OTHER_INCOME, amount=10_000, index=None),
                Stream(name="x", amount=-10_000, index=None),
            ],
            [cash(), gold(100_000, (bought, 10_000))],
        )
        return zero_run(p, 13)

    young, aged = december(date(2025, 12, 1)), december(date(2024, 6, 1))
    assert young.taxes[0, 11] < aged.taxes[0, 11] < 0
    assert young.balance["cash"][11] > -0.01
    assert young.balance["gold"][12] == pytest.approx(young.balance["gold"][11])  # none in January
    assert young.ledger is not None
    taxes = sum(row.sum() for (side, *_), row in young.ledger.entries.items() if side == TAX)
    assert taxes == pytest.approx(-young.taxes[0].sum())


def test_a_conditional_sale_of_gold_fires_once() -> None:
    sale = SellEvent(type="sell", asset="g", share=0.5, when=SaleTrigger(age=49.1))
    p = plan([], [gold(10_000)], Scenario(name="s", events=[sale]))
    r = zero_run(p, 5)
    assert r.balance["gold"].tolist() == pytest.approx([10_000, 10_000, 5000, 5000, 5000])
    assert r.total[0].tolist() == pytest.approx([10_000] * 5)  # the proceeds are invested
