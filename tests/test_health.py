"""The GKV beyond a salary: a freiwilliges Mitglied on all income, the KVdR, the Versorgungsbezüge
of a company pension. The law as amounts of `sv.py`, the engine as relations between runs."""

from collections.abc import Callable, Mapping
from datetime import date

import numpy as np
import pytest
from builders import booked, cash, harvested, phases, plan, zero_returns, zero_run
from pydantic import ValidationError

from dagobert.engine.simulation import simulate
from dagobert.model.assets import EquityAsset, PensionPolicy, TermDeposit
from dagobert.model.assumptions import Child, Person
from dagobert.model.events import EndStreamsEvent, Event, SetStreamEvent
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import TaxOptions
from dagobert.result import INCOME_TAX, FloatArray, RunResult
from dagobert.sv import kv_compulsory, kv_voluntary
from dagobert.tax import for_year

TY = for_year(2026)
MONTH = date(2026, 1, 1)
DECEMBER = date(2026, 12, 1)  # the first December of a harvest run
PARENT = Person(born=date(1960, 1, 1), children=1, children_born=[Child(born=date(1990, 1, 1))])
GKV = {"pkv": False}
OPTS = TaxOptions(pkv=False)
REDUCED = 2 * (TY.kv_rate_reduced + TY.kv_zusatz_half)  # 16.9% in 2026
GENERAL = 2 * TY.kv_half  # 17.5% in 2026


@pytest.mark.parametrize(
    ("rest", "krankengeld", "kv"),
    [
        (500.0, False, 222.80),
        (500.0, True, 230.71),
        (9000.0, False, 982.31),
        (9000.0, True, 1017.19),
    ],
)
def test_a_voluntary_member_matches_the_bmg_at_the_minimum_and_the_bbg(
    rest: float, *, krankengeld: bool, kv: float
) -> None:
    """BMG `Beiträge` 2026, KV only, with the average Zusatzbeitrag, on 1,318.33 and 5,812.50."""
    paid, pv = kv_voluntary((0.0, 0.0, rest), OPTS, PARENT, MONTH, TY, krankengeld=krankengeld)
    assert float(paid) == pytest.approx(kv, abs=0.005)
    assert float(pv) == pytest.approx(0.036 * min(max(rest, 1318.33), 5812.5), abs=0.005)


@pytest.mark.parametrize(
    ("income", "base", "versorgung"),
    [
        ((2000.0, 0.0, 0.0), 0.0, 0.0),  # the pension pays apart, above the minimum
        ((1000.0, 0.0, 0.0), 318.33, 0.0),  # up to the minimum at the rate of the rest
        ((0.0, 1000.0, 0.0), 1318.33, 1000.0),  # no Freibetrag, the general rate
        ((5000.0, 2000.0, 800.0), 812.5, 812.5),  # pension, Versorgungsbezüge, rest: to the BBG
        ((0.0, 0.0, -3000.0), 1318.33, 0.0),  # a loss offsets nothing
    ],
)
def test_a_voluntary_member_pays_by_kind_of_income_up_to_the_bbg(
    income: tuple[float, float, float], base: float, versorgung: float
) -> None:
    """§238a SGB V: the pension, the Versorgungsbezüge, the rest; BVSzGs §3 Abs. 4: no §226."""
    kv, pv = kv_voluntary(income, OPTS, PARENT, MONTH, TY)
    assert float(kv) == pytest.approx(versorgung * GENERAL + (base - versorgung) * REDUCED, 1e-4)
    assert float(pv) == pytest.approx(0.036 * base, 1e-4)


@pytest.mark.parametrize(
    ("income", "room", "kv", "pv"),
    [
        ((150.0, 0.0), 5812.5, 0.0, 0.0),  # within the Freigrenze
        ((197.75, 0.0), 5812.5, 0.0, 0.0),  # the Freigrenze itself
        ((1000.0, 0.0), 5812.5, 802.25 * GENERAL, 36.0),  # Freibetrag for the KV, not the PV
        ((150.0, 100.0), 5812.5, 100.0 * GENERAL, 9.0),  # a profit beside crosses the Freigrenze
        ((1000.0, 0.0), 500.0, 500.0 * GENERAL, 18.0),  # the room below the BBG
    ],
)
def test_a_compulsory_member_pays_on_the_company_pension_above_a_twentieth(
    income: tuple[float, float], room: float, kv: float, pv: float
) -> None:
    """§226 Abs. 2 SGB V: a Freigrenze of 197.75 on the Versorgungsbezüge and the
    Arbeitseinkommen together, then a Freibetrag of 197.75 off the company pension for the KV;
    §57 Abs. 1 SGB XI keeps the Freigrenze only. §248: the general rate."""
    paid, care = kv_compulsory(income, OPTS, PARENT, MONTH, TY, room=room)
    assert (float(paid), float(care)) == pytest.approx((kv, pv), abs=0.005)


def _run(
    *streams: Stream,
    months: int = 12,
    assets: list[object] | None = None,
    scenario: Scenario | None = None,
    **kw: object,
) -> RunResult:
    held: list[object] = assets or [cash(500_000)]
    kw.setdefault("tax", GKV)
    return zero_run(plan(list(streams), held, scenario, **kw), months)


def _kv(r: RunResult) -> FloatArray:
    """KV and PV by month."""
    return booked(r, "KV") + booked(r, "PV")


def _retired(start: date = MONTH) -> Scenario:
    return Scenario(name="r", phases=phases((start, "retired")))


PENSION = Stream(name="pension", kind=StreamKind.PENSION, gross=1500, index=None)
SHOP = Stream(name="shop", kind=StreamKind.SELF_EMPLOYED, amount=1000, index=None)


def test_a_month_without_salary_pays_the_minimum_of_a_voluntary_member() -> None:
    """A GKV member between jobs, without ALG1, pays 222.80 and the PV of the childless on
    1,318.33 €; a PKV member pays nothing more than the premium."""
    gap = _run()
    assert booked(gap, "KV") == pytest.approx(np.full(12, 222.80), abs=0.005)
    assert booked(gap, "PV") == pytest.approx(np.full(12, 0.042 * 1318.33), abs=0.005)
    assert not _kv(_run(tax={"pkv": True})).any()


@pytest.mark.parametrize(
    "main",
    [
        Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None),
        Stream(name="alg", kind=StreamKind.ALG1),
    ],
)
def test_a_salary_or_alg1_pays_nothing_on_the_other_income(main: Stream) -> None:
    """A Pflichtmitglied (§5 Abs. 1 Nr. 1, 2 SGB V) pays nothing on rent or capital, nor on a
    profit without a pension or a Versorgungsbezug (§226 Abs. 1 Nr. 4)."""
    rent = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=3000, index=None)
    alone, rented = (_run(main, *more, months=3) for more in ((), (rent, SHOP)))
    assert _kv(rented) == pytest.approx(_kv(alone))


def test_alg1_beyond_the_entitlement_is_a_voluntary_month() -> None:
    """12 months of ALG1 at 49, then the phase goes on without it: the minimum."""
    r = _run(Stream(name="alg", kind=StreamKind.ALG1), months=14)
    assert not _kv(r)[:12].any()
    assert booked(r, "KV")[12:] == pytest.approx([222.80, 222.80], abs=0.005)


def _living(
    *streams: Stream,
    cost_basis: float = 100_000,
    scenario: Scenario | None = None,
    **kw: object,
) -> RunResult:
    """Two years of spending 6,000 € a month, which sells equity of a depot."""
    depot = EquityAsset(id="d", kind="equity", value=500_000, cost_basis=cost_basis)
    spend = Stream(name="life", cat="base", amount=-6000, index=None)
    return _run(spend, *streams, months=24, assets=[cash(), depot], scenario=scenario, **kw)


def test_capital_income_raises_the_voluntary_kv_of_the_next_year() -> None:
    """The Kasse takes the capital income of the last proven year (BVSzGs §5 Abs. 2 S. 4): the
    gains of the first year raise the second, after the Teilfreistellung (§20 InvStG); a sale
    without a gain raises nothing."""
    gain, none = _living(), _living(cost_basis=500_000)
    assert _kv(gain)[:12] == pytest.approx(_kv(none)[:12])
    assert np.all(_kv(gain)[12:] > _kv(none)[12:])
    full = _living(tax=GKV | {"teilfreistellung": 0})
    assert np.all(_kv(full)[12:] > _kv(gain)[12:])


def test_a_partial_first_year_spreads_its_vorabpauschale_over_twelve_months() -> None:
    """BVSzGs §5 Abs. 2 S. 4 divides by the months in which the income was earned: twelve for the
    Vorabpauschale (§18 InvStG), a whole year's amount whenever the run starts."""

    def year_2027(start: date) -> FloatArray:
        returns = zero_returns(24)
        returns.rates["equity"][:] = 0.07 / 12
        depot = EquityAsset(id="d", kind="equity", value=2_000_000, cost_basis=2_000_000)
        held = plan([], [cash(100_000), depot], tax=GKV, start=start, invest_rest=False)
        return _kv(simulate(held, returns, "fixed"))[13 - start.month :][:12]

    january, july = year_2027(MONTH), year_2027(date(2026, 7, 1))
    assert july == pytest.approx(january)
    assert np.all(january > _kv(_run())[0])


def _interest(*, tax: Mapping[str, object]) -> RunResult:
    """Two years with interest of 20,000 € in July of the first."""
    deposit = TermDeposit(
        id="fest",
        kind="term_deposit",
        value=400_000,
        rate=0.05,
        start=date(2025, 7, 1),
        matures=date(2026, 7, 1),
    )
    return _run(months=24, assets=[cash(), deposit], tax=tax)


def test_the_sparer_pauschbetrag_lowers_the_tax_not_the_kv() -> None:
    """Interest of 20,000 € in July: the next year pays on 20,000 less 51 € of Werbungskosten
    over twelve months (BVSzGs §3 Abs. 1b S. 3), whatever the Sparer-Pauschbetrag."""
    runs = [_interest(tax={**GKV, **tax}) for tax in ({}, {"sparer_pauschbetrag": 0})]
    assert _kv(runs[0]) == pytest.approx(_kv(runs[1]))
    assert runs[0].capital_taxes.sum() > runs[1].capital_taxes.sum()  # taxes below zero
    base = (400_000 * 0.05 - 51) / 12
    assert booked(runs[0], "KV")[12:] == pytest.approx(np.full(12, base * REDUCED), rel=1e-3)


@pytest.mark.parametrize("kvdr", [True, False])
def test_only_a_voluntary_pensioner_pays_on_the_capital_income(*, kvdr: bool) -> None:
    """The KVdR (§237 SGB V) takes the pension and the Versorgungsbezüge only. Beside a pension
    above the minimum the two pay the same: the subsidy of the DRV (§106 SGB VI) halves the
    general rate on the pension."""
    person = Person(born=date(1959, 1, 1), kvdr=kvdr)
    paid = _kv(_living(PENSION, person=person, scenario=_retired()))
    alone = _kv(_run(PENSION, months=24, person=Person(born=date(1959, 1, 1)), scenario=_retired()))
    assert paid[:12] == pytest.approx(alone[:12])
    assert list(paid[12:] - alone[12:] > 1) == [not kvdr] * 12  # a euro more, or the same


def _policy(**kw: object) -> PensionPolicy:
    base: dict[str, object] = {"id": "bav", "kind": "bav", "value": 60_000, "growth": "cash"}
    return PensionPolicy.model_validate(
        base | {"contribution": 0, "phases": [], "matures": date(2026, 2, 1)} | kw
    )


def _pensioner(
    *policies: PensionPolicy, months: int = 12, year: int | None = None, kvdr: bool = True
) -> RunResult:
    return _run(
        PENSION,
        months=months,
        assets=[cash(100_000), *policies],
        person=Person(born=date(1959, 1, 1), kvdr=kvdr),
        scenario=_retired(),
        tax=GKV | {"year": year},
    )


@pytest.mark.parametrize(("lump", "pays"), [(20_000, False), (60_000, True)])
def test_a_lump_sum_counts_a_120th_for_120_months_from_the_next(lump: float, *, pays: bool) -> None:
    """§229 Abs. 1 S. 3 SGB V: 166.67 a month stays within the Freigrenze of 197.75, 500 pays
    on 302.25 for the KV and on 500 for the PV, from the month after the payout in February."""
    alone = _pensioner(months=136)
    paid = _kv(_pensioner(_policy(value=lump), months=136)) - _kv(alone)
    rate = 2 * TY.pv_rate + TY.pv_kinderlos_zuschlag
    monthly = (lump / 120 - 197.75) * GENERAL + lump / 120 * rate if pays else 0.0
    assert paid[:2] == pytest.approx([0.0, 0.0])
    assert paid[2:122] == pytest.approx(np.full(120, monthly))
    assert paid[122:] == pytest.approx(np.zeros(14))


def test_a_pension_beside_a_salary_leaves_the_company_pension_its_room() -> None:
    """§230 SGB V: the company pension takes the room below the BBG that the salary leaves (S.
    1), the pension counts apart (S. 2)."""
    salary = Stream(name="pay", kind=StreamKind.SALARY, gross=5000, index=None)
    company = _policy(payout="annuity", annuity_per_10k=500, value=40_000)
    person = Person(born=date(1959, 1, 1))

    def company_kv(*more: Stream) -> float:
        def kv(*held: object) -> float:
            run = _run(
                salary, *more, assets=[cash(100_000), *held], person=person, scenario=_retired()
            )
            return float(_kv(run)[1])

        return kv(company) - kv()

    assert company_kv(PENSION) == pytest.approx(company_kv())
    assert company_kv() == pytest.approx(
        812.5 * (GENERAL + 2 * TY.pv_rate + TY.pv_kinderlos_zuschlag)
    )


@pytest.mark.parametrize(
    ("pays", "company"),
    [
        ((Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None),), True),
        ((Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None), PENSION), False),
        ((Stream(name="alg", kind=StreamKind.ALG1),), True),
    ],
    ids=["salary-company", "salary-pension", "alg1-company"],
)
def test_a_profit_beside_a_pension_or_a_company_pension_pays_in_full(
    pays: tuple[Stream, ...], *, company: bool
) -> None:
    """§226 Abs. 1 Nr. 4 SGB V (by §232a Abs. 3 also with ALG1): the Arbeitseinkommen of a
    Pflichtmitglied counts beside a pension or Versorgungsbezüge, without a Freibetrag, at the
    general rate and the whole PV rate."""
    held: list[object] = [cash(100_000)]
    held += [_policy(payout="annuity", annuity_per_10k=125, value=40_000)] * company
    person = Person(born=date(1959, 1, 1))

    def kv(*more: Stream) -> FloatArray:
        return _kv(_run(*pays, *more, assets=held, person=person, scenario=_retired(), months=3))

    rate = GENERAL + 2 * TY.pv_rate + TY.pv_kinderlos_zuschlag
    assert (kv(SHOP) - kv())[1:] == pytest.approx(np.full(2, 1000 * rate))


def test_two_company_pensions_share_one_freibetrag() -> None:
    """The Freibetrag holds per member: two annuities of 150 pay as one of 300."""
    annuity = {"payout": "annuity", "annuity_per_10k": 25}
    two = _pensioner(_policy(**annuity), _policy(id="pk", **annuity))
    one = _pensioner(_policy(annuity_per_10k=50, payout="annuity"))
    assert _kv(two) == pytest.approx(_kv(one))
    assert _kv(one)[1] > _kv(_pensioner())[1]


def test_a_basisrente_pays_only_for_a_voluntary_member() -> None:
    """A Basisrente is no Versorgungsbezug (§229 SGB V): free in the KVdR, but income of a
    voluntary member, at the reduced rate, while a company pension takes the general one."""
    rente = {"payout": "annuity", "annuity_per_10k": 500, "value": 40_000}
    basis = _policy(basisrente=True, **rente)
    company = _policy(**rente)
    assert _kv(_pensioner(basis))[1:] == pytest.approx(_kv(_pensioner())[1:])
    base = _kv(_pensioner(kvdr=False))[1]
    paid = _kv(_pensioner(basis, kvdr=False))[1] - base
    more = _kv(_pensioner(company, kvdr=False))[1] - base
    assert more - paid == pytest.approx(2000 * (GENERAL - REDUCED))


@pytest.mark.parametrize(("other", "base"), [(1000, 4000), (-1000, 3000)])
def test_a_business_pays_on_its_other_income_and_a_loss_offsets_no_other_kind(
    other: float, base: float
) -> None:
    """The self-employed base follows the voluntary member (§240 SGB V): profit and rent. Other
    income below zero leaves the profit to pay in full (BSG B 12 KR 8/06 R)."""
    profit = Stream(name="shop", kind=StreamKind.SELF_EMPLOYED, amount=3000, index=None)
    rent = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=other, index=None)
    assert booked(_run(profit, rent, months=1), "KV")[0] == pytest.approx(base * REDUCED)


def test_the_tax_year_sets_the_months_of_a_lump_sum(later_tax_year: Callable[..., int]) -> None:
    """Half the months: twice the monthly Versorgungsbezug, for 60 months."""
    year = later_tax_year(versorgung_months=60)
    alone, now, later = (
        _kv(_pensioner(*policy, months=70, year=y))
        for policy, y in (((), TY.year), ((_policy(),), TY.year), ((_policy(),), year))
    )
    assert later[2] - alone[2] > 2 * (now[2] - alone[2])
    assert later[62:] == pytest.approx(alone[62:])
    assert np.all(now[62:] > alone[62:])


@pytest.mark.parametrize(
    "run",
    [
        lambda **kw: _run(Stream(name="pay", kind=StreamKind.SALARY, gross=6000, index=None), **kw),
        lambda **kw: _run(SHOP.model_copy(update={"amount": 6000}), **kw),  # voluntary, a profit
        _interest,  # on capital income, after a flat tax with its church tax
    ],
    ids=["salary", "profit", "capital"],
)
def test_the_church_tax_leaves_the_kv_base_alone(run: Callable[..., RunResult]) -> None:
    """§51a EStG adds the church tax to the income tax; no rule of the SV counts it."""
    plain, church = (run(tax=GKV | more) for more in ({}, {"church": True, "land": "NW"}))
    assert _kv(church) == pytest.approx(_kv(plain))
    paid = [r.taxes.sum() + r.capital_taxes.sum() for r in (plain, church)]
    assert paid[1] < paid[0]  # taxes below zero


RENT = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=1000, index=None)


def _harvests(
    *streams: Stream, scenario: Scenario, tax: Mapping[str, object] = GKV, **kw: object
) -> tuple[RunResult, RunResult]:
    """Two years with and without the harvest (`tax.harvest`) of a depot at a gain of half, the
    cash kept as cash: it pays the December bill, which would sell equity beyond the room."""
    held: list[object] = [
        cash(50_000),
        EquityAsset(id="d", kind="equity", value=200_000, cost_basis=100_000),
    ]
    on, off = (
        _run(
            *streams,
            months=24,
            assets=held,
            scenario=scenario,
            tax={**tax, "harvest": h},
            invest_rest=False,
            **kw,
        )
        for h in (True, False)
    )
    return on, off


@pytest.mark.parametrize(
    ("start", "job", "months"),
    [(MONTH, False, 12), (date(2026, 7, 1), False, 6), (MONTH, True, 0)],
    ids=["voluntary", "first half year", "job next january"],
)
def test_a_harvest_keeps_the_voluntary_kv_of_the_next_year(
    start: date, *, job: bool, months: int
) -> None:
    """A year without pay and a rent of 1,000 € a month: the harvest stops where the capital
    income of the year over its months in the run, less 51 € a year, fills the base of the next
    to its minimum (BVSzGs §5 Abs. 2 S. 4, §3 Abs. 1b S. 3), so the KV stays. Before a job in
    January, a Pflichtversicherung (§5 Abs. 1 Nr. 1 SGB V), it takes the tax-free room."""
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None, phases=["work"])
    changes = phases((start, "alt"), (date(2027, 1, 1), "work" if job else "alt"))
    pair = _harvests(RENT, pay, start=start, scenario=Scenario(name="h", phases=changes))
    assert _kv(pair[0]) == pytest.approx(_kv(pair[1]))
    full = 12 * (TY.kv_min_base - 1000) + TY.kv_capital_werbungskosten
    if job:
        assert harvested(pair, DECEMBER) > full
    else:
        assert harvested(pair, DECEMBER) == pytest.approx(full * months / 12)


def test_a_salary_ended_by_factor_zero_or_end_streams_is_voluntary_in_january() -> None:
    """Both ends leave no salary in January: the same voluntary KV in January, below that of
    a salary that goes on, and the same room for a harvest."""
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None)
    at = date(2026, 5, 1)
    ends: dict[str, list[Event]] = {
        "end_streams": [EndStreamsEvent(at=at, type="end_streams", names=["pay"])],
        "factor 0": [SetStreamEvent(at=at, type="set_stream", name="pay", factor=0)],
        "none": [],
    }
    ran = {
        how: _run(RENT, pay, scenario=Scenario(name="h", events=events), months=14)
        for how, events in ends.items()
    }
    january = {how: _kv(r)[12] for how, r in ran.items()}
    assert january["end_streams"] == pytest.approx(january["factor 0"])
    assert january["end_streams"] < january["none"]
    room = {
        how: harvested(_harvests(RENT, pay, scenario=Scenario(name="h", events=events)), DECEMBER)
        for how, events in ends.items()
    }
    assert room["end_streams"] == pytest.approx(room["factor 0"])


@pytest.mark.parametrize(
    ("stream", "kvdr", "harvests"),
    [
        (PENSION, True, True),
        (PENSION, False, False),
        (SHOP.model_copy(update={"amount": 3000}), True, False),
    ],
    ids=["kvdr", "voluntary pensioner", "business"],
)
def test_only_a_base_below_the_minimum_leaves_room_to_harvest(
    stream: Stream, *, kvdr: bool, harvests: bool
) -> None:
    """The KVdR takes no capital income (§237 SGB V): its harvest is the tax-free room. A
    voluntary member above the minimum pays on every euro of it: no harvest."""
    person = Person(born=date(1959, 1, 1), kvdr=kvdr)
    pair = _harvests(stream, person=person, scenario=_retired())
    assert (harvested(pair, DECEMBER) > 0) == harvests
    assert _kv(pair[0]) == pytest.approx(_kv(pair[1]))


def test_a_year_that_sells_every_month_harvests_nothing() -> None:
    """The sales of the year fill the base of the next beyond the minimum already."""
    on, off = (_living(tax=GKV | {"harvest": h}) for h in (True, False))
    assert on.liquid == pytest.approx(off.liquid)


def test_alg1_into_the_next_year_harvests_into_its_voluntary_months() -> None:
    """A job to June, then a year of ALG1 (§5 Abs. 1 Nr. 2 SGB V): next January is compulsory, so
    the harvest takes the tax-free room, here the Pauschbetrag, beyond the 871 € that a voluntary
    member with a rent of 1,250 € keeps to, and the voluntary months after the ALG1 pay on it."""
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None, phases=["work"])
    alg1 = Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"])
    rent = RENT.model_copy(update={"amount": 1250})
    changes = phases((MONTH, "work"), (date(2026, 7, 1), "unemployed"))
    on, off = _harvests(pay, alg1, rent, scenario=Scenario(name="a", phases=changes))
    assert harvested((on, off), DECEMBER) == pytest.approx(1000)
    assert _kv(on)[:18] == pytest.approx(_kv(off)[:18])
    assert np.all(_kv(on)[18:] > _kv(off)[18:])


SWITCH = date(2026, 7, 1)  # `tax.gkv_from` of the runs below: the PKV for half a year
PREMIUMS = (
    Stream(name="kv", amount=-600, health="kv", index=None),
    Stream(name="pv", amount=-80, health="pv", index=None),
)
JOB_LOSS = Scenario(name="j", phases=phases((MONTH, "work"), (SWITCH, "unemployed")))
AT_49 = Person(born=date(1977, 1, 1))
LOST_JOB = (
    Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None, phases=["work"]),
    Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"]),
)
# the streams of a run with the switch, its scenario and the person
SWITCHED: dict[str, tuple[tuple[Stream, ...], Scenario | None, Person]] = {
    "salary": ((Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None),), None, AT_49),
    "alg1": (LOST_JOB, JOB_LOSS, AT_49),
    "pension": ((PENSION,), _retired(), Person(born=date(1959, 1, 1))),
    "none": ((), None, AT_49),
}


@pytest.mark.parametrize("case", list(SWITCHED))
def test_a_switch_runs_the_pkv_before_its_month_and_the_gkv_from_it(case: str) -> None:
    """`tax.gkv_from`: before it a member of the PKV with its premiums and the subsidy of the
    employer, the Agentur or the DRV; from it a member of the GKV without them, the premiums
    ended by themselves: compulsory with a salary, ALG1 or the KVdR, else voluntary. Each month
    takes its own SV and withholding."""
    streams, scenario, person = SWITCHED[case]
    switched, pkv, gkv = (
        _run(*streams, *premiums, scenario=scenario, person=person, tax=tax)
        for premiums, tax in ((PREMIUMS, {"gkv_from": SWITCH}), (PREMIUMS, {}), ((), GKV))
    )
    for part in (_kv, lambda r: r.income[0], lambda r: r.expenses[0]):
        assert part(switched)[:6] == pytest.approx(part(pkv)[:6])
        assert part(switched)[6:] == pytest.approx(part(gkv)[6:])
    assert switched.taxes[0, :6] == pytest.approx(pkv.taxes[0, :6])
    assert switched.taxes[0, 6:11] == pytest.approx(gkv.taxes[0, 6:11])


def test_a_switch_needs_the_pkv() -> None:
    with pytest.raises(ValidationError, match="gkv_from needs pkv"):
        TaxOptions(pkv=False, gkv_from=SWITCH)


def test_the_settlement_of_the_switch_year_deducts_what_each_part_paid() -> None:
    """§10 Abs. 1 Nr. 3 EStG in the year of a switch in July: a higher PKV premium before it and
    a higher Zusatzbeitrag of the voluntary member after it each lower the income tax of the
    year. A switch in the first month leaves no premium to pay."""
    rent = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=4000, index=None)

    def income_tax(premium: float, zusatz: float, switch: date = SWITCH) -> float:
        kv = Stream(name="kv", amount=-premium, health="kv", index=None)
        r = _run(rent, kv, tax={"gkv_from": switch, "kv_zusatz": zusatz})
        return float(booked(r, INCOME_TAX).sum())

    assert income_tax(800, 0.025) < income_tax(600, 0.025)
    assert income_tax(600, 0.035) < income_tax(600, 0.025)
    assert income_tax(800, 0.025, MONTH) == pytest.approx(income_tax(600, 0.025, MONTH))


def test_the_harvest_before_a_switch_keeps_the_voluntary_kv_of_the_next_year() -> None:
    """A member of the PKV who is a voluntary member of the GKV from January: the harvest of
    December stops where the base of the next year reaches its minimum beside the rent, as for a
    member of the GKV (rule `harvest`), though its premiums leave more tax-free room."""
    pair = _harvests(
        RENT,
        *PREMIUMS,
        scenario=Scenario(name="h", phases=phases((MONTH, "alt"))),
        tax={"gkv_from": date(2027, 1, 1)},
    )
    assert _kv(pair[0]) == pytest.approx(_kv(pair[1]))
    full = 12 * (TY.kv_min_base - 1000) + TY.kv_capital_werbungskosten
    assert harvested(pair, DECEMBER) == pytest.approx(full)


@pytest.mark.parametrize(
    ("born", "tax", "marks"),
    [
        (date(1977, 1, 1), {}, ["2026-07 exemption"]),  # ALG1 at 49 in the PKV
        (date(1977, 1, 1), {"gkv_from": SWITCH}, []),  # ALG1 makes a compulsory member
        (date(1971, 1, 1), {}, []),  # at 55 §6 Abs. 3a SGB V keeps the PKV
        (date(1971, 1, 1), {"gkv_from": SWITCH}, ["2026-07 gkv"]),  # and seldom lets one switch
        (date(1977, 1, 1), GKV, []),
    ],
)
def test_alg1_in_the_pkv_before_55_and_a_switch_from_55_are_marked(
    born: date, tax: dict[str, object], marks: list[str]
) -> None:
    """§8 Abs. 1 S. 1 Nr. 1a SGB V: the run keeps the PKV on ALG1 only by an exemption on
    application; §6 Abs. 3a: from 55 a switch is usually closed. Markers, never refusals."""
    r = _run(*LOST_JOB, scenario=JOB_LOSS, person=Person(born=born), tax=tax)
    kinds = [f"{m.month:%Y-%m} {m.kind}" for m in r.markers if m.kind in ("exemption", "gkv")]
    assert kinds == marks
