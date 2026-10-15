"""Self-employment in the engine: the GKV and the GRV on the profit, the reserve, the trade tax,
as relations between runs."""

from collections.abc import Callable
from datetime import date

import numpy as np
import pytest
from builders import booked, cash, phases, plan, zero_run

from dagobert.model.assets import AvDepot
from dagobert.model.months import months_between
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import RunResult
from dagobert.tax import for_year

TY = for_year(2026)
GKV = {"pkv": False}


def _profit(amount: float, name: str = "consulting", **kw: object) -> Stream:
    return Stream.model_validate(
        {"name": name, "kind": "self_employed", "amount": amount, "index": None} | kw
    )


def _run(
    *streams: Stream, months: int = 12, scenario: Scenario | None = None, **kw: object
) -> RunResult:
    held = plan(list(streams), [cash(100_000)], scenario, **kw)
    return zero_run(held, months)


def _sv(r: RunResult, month: int = 0) -> tuple[float, float, float]:
    kv, pv, rv = (float(booked(r, item)[month]) for item in ("KV", "PV", "RV"))
    return kv, pv, rv


def _paid(r: RunResult) -> float:
    """Income tax, Soli, trade tax and SV of the run, positive."""
    return float(-r.taxes[0].sum())


@pytest.mark.parametrize(
    ("profit", "same"),
    [(1000, TY.kv_min_base), (0, TY.kv_min_base), (-2000, TY.kv_min_base), (10_000, 5812.5)],
)
def test_the_gkv_takes_the_profit_between_the_least_base_and_the_bbg(
    profit: float, same: float
) -> None:
    """§240 Abs. 4 SGB V: a month of little, no or negative profit pays on a third of the
    Bezugsgröße while the business runs, a large one on the KV-BBG."""
    low, high = (_run(_profit(p), months=1, tax=GKV) for p in (profit, same))
    assert _sv(low)[:2] == pytest.approx(_sv(high)[:2])
    assert _sv(low)[0] > 0


def test_krankengeld_takes_the_general_rate() -> None:
    """The Wahlerklärung (§44 Abs. 2 SGB V) costs 0.6 points of the base more."""
    plain, sick = (
        _run(_profit(4000), months=1, tax=GKV | {"self_employed": {"krankengeld": kg}})
        for kg in (False, True)
    )
    assert _sv(sick)[0] - _sv(plain)[0] == pytest.approx(0.006 * 4000)
    assert _sv(sick)[1] == pytest.approx(_sv(plain)[1])


def test_a_factor_of_0_switches_the_business_off() -> None:
    """A factor of 0 in the phase leaves a voluntary member without a business: the minimum KV
    at the reduced rate and no Regelbeitrag. `amount: 0` is a slump of a running business, whose
    Krankengeld takes the general rate on the minimum."""
    own = GKV | {"self_employed": {"rv": "regular", "krankengeld": True}}
    off = _run(_profit(3000, factor={"work": 0}), months=1, tax=own)
    slump = _run(_profit(0), months=1, tax=own)
    assert _sv(off)[0] == pytest.approx(
        TY.kv_min_base * 2 * (TY.kv_rate_reduced + TY.kv_zusatz_half)
    )
    assert _sv(slump)[0] - _sv(off)[0] == pytest.approx(TY.kv_min_base * 0.006)
    assert _sv(off)[2] == 0.0 < _sv(slump)[2]


@pytest.mark.parametrize("amount", [400, 4000])
def test_two_businesses_pay_the_sv_of_one_on_their_sum(amount: float) -> None:
    """One person: the minimum and the Regelbeitrag once, on the sum of the profits."""
    regular = {"self_employed": {"rv": "regular", "founded": date(2020, 1, 1)}}
    two = _run(_profit(amount), _profit(amount, "teaching"), months=1, tax=GKV | regular)
    one = _run(_profit(2 * amount), months=1, tax=GKV | regular)
    assert _sv(two) == pytest.approx(_sv(one))


def test_a_yearly_profit_pays_its_sv_in_every_month_at_its_run_rate() -> None:
    """A profit paid once a year costs the SV of a twelfth each month, and the year the same
    tax as the monthly profit."""
    yearly = _run(_profit(60_000, every=12), tax=GKV | {"self_employed": {"rv": "income"}})
    monthly = _run(_profit(5000), tax=GKV | {"self_employed": {"rv": "income"}})
    for item in ("KV", "PV", "RV"):
        assert booked(yearly, item) == pytest.approx(booked(monthly, item))
    assert _paid(yearly) == pytest.approx(_paid(monthly))


@pytest.mark.parametrize(
    ("founded", "full"),
    [(None, date(2031, 1, 1)), (date(2026, 1, 1), date(2030, 1, 1))],
)
def test_the_regelbeitrag_is_half_up_to_the_third_year_after_the_founding(
    founded: date | None, full: date
) -> None:
    """§165 Abs. 1 S. 2 SGB VI: the founding is the first month of the business, 2027-03, or
    `founded`; the RV of the regular base is the same for any profit."""
    rv = {"rv": "regular", "founded": founded}
    r = _run(_profit(5000, start=date(2027, 3, 1)), months=72, tax={"self_employed": rv})
    rich = _run(_profit(50_000, start=date(2027, 3, 1)), months=72, tax={"self_employed": rv})
    paid = booked(r, "RV")
    switch = r.months.index(full)
    assert paid[14] == pytest.approx(
        TY.rv_founding_share * TY.bezugsgroesse_month * TY.rv_rate_total
    )
    assert paid[switch - 1] == pytest.approx(paid[14])
    assert paid[switch] == pytest.approx(2 * paid[14])
    assert booked(rich, "RV") == pytest.approx(paid)


def test_a_later_business_phase_moves_the_derived_founding() -> None:
    """Without `founded` the first month of the business is the founding: the phase a year later
    pays the whole Regelbeitrag a year later."""

    def full(at: date) -> date:
        scenario = Scenario(name="s", phases=phases((date(2026, 1, 1), "work"), (at, "alt")))
        r = _run(
            _profit(5000, phases=["alt"]),
            months=96,
            scenario=scenario,
            tax={"self_employed": {"rv": "regular"}},
        )
        rv = booked(r, "RV")
        return r.months[int(np.argmax(rv > 1.5 * rv[rv > 0][0]))]

    assert months_between(full(date(2027, 3, 1)), full(date(2028, 3, 1))) == 12


def test_the_income_based_rv_at_the_bbg_is_twice_the_employee_share() -> None:
    """The self-employed pays the whole rate, own and no employer share."""
    salary = Stream(name="pay", kind=StreamKind.SALARY, gross=10_000, index=None)
    employed = _run(salary, months=1)
    own = _run(_profit(10_000), months=1, tax={"self_employed": {"rv": "income"}})
    assert _sv(own)[2] == pytest.approx(2 * _sv(employed)[2])


@pytest.mark.parametrize(
    ("constant", "rv", "item"),
    [("bezugsgroesse_month", "none", 0), ("geringfuegigkeit_month", "income", 2)],
)
def test_the_tax_year_sets_the_least_bases(
    later_tax_year: Callable[..., int], constant: str, rv: str, item: int
) -> None:
    """Twice the Bezugsgröße doubles the minimum KV, twice the Geringfügigkeitsgrenze the least
    RV on a proven income."""
    later = later_tax_year(**{constant: getattr(TY, constant) * 2})
    before, after = (
        _sv(_run(_profit(100), months=1, tax=GKV | {"year": year, "self_employed": {"rv": rv}}))
        for year in (TY.year, later)
    )
    assert after[item] == pytest.approx(2 * before[item])


def test_a_self_employed_month_gets_no_pkv_subsidy() -> None:
    """§257 SGB V names employees: the profit takes the whole premium, a salary half of it."""
    premium = Stream(name="kv", amount=-800, health="kv", index=None)
    salary = Stream(name="pay", kind=StreamKind.SALARY, gross=5000, index=None)
    assert _run(_profit(5000), premium, months=1).income[0, 0] == pytest.approx(5000)
    assert _run(salary, premium, months=1).income[0, 0] == pytest.approx(5000 + 400)


@pytest.mark.parametrize(
    "other",
    [
        Stream(name="main", kind=StreamKind.SALARY, gross=5000, index=None),
        Stream(name="main", kind=StreamKind.ALG1),
    ],
)
def test_a_profit_beside_a_salary_or_alg1_pays_no_sv_of_its_own(other: Stream) -> None:
    """A side business: the KV of the salary or of the Agentur (§5 Abs. 1 Nr. 2 SGB V) covers
    it, so it changes no SV."""
    with_profit = _run(other, _profit(2000), months=1, tax=GKV)
    alone = _run(other, months=1, tax=GKV)
    assert _sv(with_profit) == pytest.approx(_sv(alone))


@pytest.mark.parametrize(("hebesatz", "more"), [(4.0, False), (4.9, True)])
def test_the_trade_tax_up_to_400_percent_costs_nothing_but_lowers_the_soli(
    hebesatz: float, *, more: bool
) -> None:
    """§35 EStG: four times the Messbetrag comes off the income tax before the Soli. Up to a
    Hebesatz of 400% the trade tax is paid back in full and the Soli falls with the tax."""
    freelance = _run(_profit(12_000))
    trade = _run(_profit(12_000, hebesatz=hebesatz))
    assert booked(trade, "trade tax").sum() > 0
    assert (_paid(trade) > _paid(freelance)) == more


def test_a_loss_offsets_the_other_income_of_its_year() -> None:
    rent = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=3000, index=None)
    loss, nil = (_run(rent, _profit(p), tax=GKV) for p in (-1000, 0))
    assert _paid(loss) < _paid(nil)
    assert booked(loss, "KV") == pytest.approx(booked(nil, "KV"))


def test_a_self_employed_year_pays_into_the_altersvorsorgedepot() -> None:
    """From 2027 the self-employed are eligible without a compulsory pension insurance: 1,800
    and the Zulage of 540 in December."""
    depot = AvDepot(id="av", kind="av_depot", start=date(2027, 1, 1))
    p = plan([_profit(4000)], [cash(), depot])
    r = zero_run(p, 24)
    assert r.total[0, 23] - r.liquid[0, 23] == pytest.approx(2340.0)


def test_a_freelance_year_settles_little_in_december() -> None:
    """The reserve takes the SV and the deductible premium as the settlement does."""
    r = _run(_profit(8000), tax=GKV | {"self_employed": {"rv": "regular"}})
    assert abs(r.taxes[0, 11] - r.taxes[0, 10]) < 100


def test_alg1_after_self_employment_marks_its_base() -> None:
    """Without §28a SGB III a business earns no ALG1: the engine pays it on the last salary."""
    scenario = Scenario(
        name="s",
        phases=phases(
            (date(2026, 1, 1), "work"), (date(2026, 3, 1), "alt"), (date(2026, 6, 1), "unemployed")
        ),
    )
    r = _run(
        Stream(name="pay", kind=StreamKind.SALARY, gross=5000, phases=["work"], index=None),
        _profit(3000, phases=["alt"]),
        Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"]),
        scenario=scenario,
    )
    assert any(m.kind == "alg1" for m in r.markers)
