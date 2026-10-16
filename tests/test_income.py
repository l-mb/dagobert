"""The streams of a run: the salary with its SV and withholding, other income, the church tax, the
PKV and its subsidies, the GKV, the pension and its claim, a severance, the bAV policies and the
Altersvorsorgedepot. Relations between runs, and amounts of the law."""

from datetime import date

import numpy as np
import pytest
from builders import cash, levels, phases, plan, zero_returns, zero_run

from dagobert.engine.simulation import horizon_months, simulate
from dagobert.model.assets import AvDepot, PensionPolicy, PropertyAsset
from dagobert.model.assumptions import Child, Person
from dagobert.model.events import (
    FundPolicyEvent,
    LumpSumEvent,
    PolicyFunding,
    SaleTrigger,
    SellEvent,
    SeveranceEvent,
)
from dagobert.model.months import months_between
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import FloatArray, RunResult
from dagobert.sv import alg1_month
from dagobert.tax import for_year, income_tax, pension_share, soli, year_tax

TY = for_year(2026)
SA = TY.sonderausgaben_pauschbetrag  # §10c EStG, every settlement deducts it


def test_scale_changes_the_salary_of_one_phase_and_its_derived_bonus_once() -> None:
    scenario = Scenario(
        name="s", phases=phases((date(2026, 1, 1), "work"), (date(2026, 3, 1), "alt"))
    )
    streams = [
        Stream(name="g", kind=StreamKind.SALARY, gross=4000, index=None),
        Stream(name="b", kind=StreamKind.SALARY, of="g", share=0.1, every=12, index=None),
    ]
    r = simulate(
        plan(streams, [cash()], scenario, scale={"salary": {"alt": 1.5}}), zero_returns(13), "fixed"
    )
    assert r.income[0, [0, 1, 2, 3]].tolist() == [4000 + 4800, 4000, 6000, 6000]
    assert r.income[0, 12] == pytest.approx(6000 + 1.5 * 4800)


@pytest.mark.parametrize(
    "pay",
    [
        Stream(name="g", kind=StreamKind.SALARY, gross=4000, index=None),
        Stream(name="g", kind=StreamKind.SELF_EMPLOYED, amount=4000, index=None),
    ],
)
def test_the_growth_of_a_phase_steps_each_january_from_each_of_its_starts(pay: Stream) -> None:
    """The salary or the profit of `work` only, the other income stays; `work` comes back in
    2029-06 at the amount of the stream. A growth of 0 is the run without it."""
    scenario = Scenario(
        name="s",
        phases=phases(
            (date(2026, 1, 1), "work"), (date(2028, 3, 1), "alt"), (date(2029, 6, 1), "work")
        ),
    )
    other = Stream(name="o", kind=StreamKind.OTHER_INCOME, amount=1000, index=None)

    def run(growth: dict[str, float]) -> RunResult:
        return zero_run(plan([pay, other], [cash()], scenario, scale={"growth": growth}), 60)

    base = run({}).income[0]
    steps = np.ones(60)
    steps[12:24], steps[24:26], steps[48:] = 1.1, 1.21, 1.1  # 2027, 2028-01 to 02, 2030
    np.testing.assert_array_equal(run({"work": 0.0}).income[0], base)
    assert run({"work": 0.1}).income[0] == pytest.approx(base + 4000 * (steps - 1))


def test_the_growth_stacks_on_the_index_and_the_scale_and_alg1_takes_the_grown_salary() -> None:
    """10% on `work` pays from its first January as a salary 10% higher: its index and its scale
    alike, the bonus of it once, and ALG1 after the phase on the grown last salary."""
    scenario = Scenario(
        name="s", phases=phases((date(2026, 1, 1), "work"), (date(2028, 1, 1), "unemployed"))
    )

    def run(gross: float, growth: dict[str, float]) -> RunResult:
        streams = [
            Stream(name="g", kind=StreamKind.SALARY, gross=gross, index="salary", phases=["work"]),
            Stream.model_validate(
                {"name": "b", "kind": "salary", "of": "g", "share": 0.1, "every": 12}
                | {"index": None, "start": date(2026, 12, 1), "phases": ["work"]}
            ),
            Stream(name="a", kind=StreamKind.ALG1, phases=["unemployed"]),
        ]
        scale = {"salary": {"work": 1.5}, "growth": growth}
        p = plan(streams, [cash()], scenario, indices={"salary": {"mean": 0.03}}, scale=scale)
        returns = zero_returns(36)
        returns.indices["salary"] = (1.03 ** (np.arange(36) // 12))[None, :].astype(np.float64)
        return simulate(p, returns, "fixed")

    grown = run(3000, {"work": 0.1}).income[0]
    assert grown[:12] == pytest.approx(run(3000, {}).income[0, :12])
    assert grown[12:] == pytest.approx(run(3300, {}).income[0, 12:])
    assert grown[24] > 0  # ALG1


def test_derived_salary_follows_the_active_row_after_a_raise() -> None:
    p = plan(
        [
            Stream(name="g", kind=StreamKind.SALARY, gross=5000, end=date(2026, 7, 1)),
            Stream(name="g", kind=StreamKind.SALARY, gross=6000, start=date(2026, 7, 1)),
            Stream(name="b", kind=StreamKind.SALARY, of="g", share=0.1, every=6),
        ],
        [cash()],
    )
    r = zero_run(p, 12)
    assert r.income[0, 0] == pytest.approx(5000 + 0.1 * 6 * 5000)
    assert r.income[0, 6] == pytest.approx(6000 + 0.1 * 6 * 6000)


def test_a_bonus_between_the_rows_of_its_base_follows_the_one_that_paid_last() -> None:
    """No row of the base pays in the month of the bonus: it follows the row that started
    last, not a later raise."""

    def paid(*rows: Stream) -> float:
        bonus = Stream(
            name="b", kind=StreamKind.SALARY, of="g", share=0.1, every=12, start=date(2026, 12, 1)
        )
        r = zero_run(plan([*rows, bonus], [cash()]), 12)
        return float(r.income[0, 11])

    first = Stream(name="g", kind=StreamKind.SALARY, gross=5000, end=date(2026, 7, 1))
    later = Stream(name="g", kind=StreamKind.SALARY, gross=9000, start=date(2027, 1, 1))
    assert paid(first, later) == pytest.approx(paid(first)) == pytest.approx(0.1 * 12 * 5000)


def _salary(name: str, gross: float) -> Stream:
    return Stream(name=name, kind=StreamKind.SALARY, gross=gross, phases=["work"], index=None)


def test_concurrent_salary_streams_sum_for_tax_and_alg1() -> None:
    """Splitting one salary in two must change neither the net pay nor the ALG1 that
    references it: the engine sums the month's monthly salaries instead of keeping the last."""
    scenario = Scenario(
        name="u",
        phases=phases((date(2026, 1, 1), "work"), (date(2026, 4, 1), "unemployed")),
    )
    alg1 = Stream(name="a", kind=StreamKind.ALG1, phases=["unemployed"])

    def run(*salaries: Stream) -> RunResult:
        p = plan([*salaries, alg1], [cash(100_000)], scenario)
        return zero_run(p, 6)

    whole = run(_salary("g", 8000))
    split = run(_salary("g1", 6000), _salary("g2", 2000))
    assert whole.income[0, 3] > 2000  # ALG1 really is paid
    np.testing.assert_allclose(split.income[0], whole.income[0])


def test_a_bonus_is_withheld_as_a_sonstiger_bezug() -> None:
    """A bonus month withholds the tax of the year with the bonus less without it, not the
    bonus as if it were paid every month. December then settles close to zero."""
    p = plan(
        [
            Stream(name="salary", kind=StreamKind.SALARY, gross=5000, index=None),
            Stream(
                name="bonus",
                kind=StreamKind.SALARY,
                of="salary",
                share=0.2,
                every=12,
                start=date(2026, 6, 1),
                index=None,
            ),
        ],
        [cash()],
    )
    r = zero_run(p, 12)
    november, december = -r.taxes[0, 10], -r.taxes[0, 11]
    assert december == pytest.approx(november, abs=5)


def test_taxes_follow_inflation_index() -> None:
    p = plan(
        [Stream(name="g", kind=StreamKind.SALARY, gross=8000, phases=["work"])],
        [cash()],
    )
    flat = zero_run(p, 24)
    inflated = zero_returns(24)
    inflated.inflation[0, 11] = 0.1  # prices step once, into January 2027
    hot = simulate(p, inflated, "fixed")
    cpi, _ = levels(inflated)
    # income_tax floors euro amounts, so scaled results differ by rounding only
    np.testing.assert_allclose(hot.income[0], flat.income[0] * cpi, rtol=1e-4)
    np.testing.assert_allclose(hot.taxes[0], flat.taxes[0] * cpi, atol=5.0)


def test_a_year_converts_at_one_price_level() -> None:
    """A January severance and its December settlement convert at the mean price level of
    the year: the tax is the start-year tariff at that level."""
    inflated = zero_returns(24)
    inflated.inflation[:] = 0.004
    cpi, level = levels(inflated)
    assert level[:12] == pytest.approx(1.0)
    assert level[12] == pytest.approx(cpi[12:].mean() / cpi[:12].mean())
    gross = 200_000.0
    hot = simulate(plan([], [cash()], _severance_at(date(2027, 1, 1), gross)), inflated, "fixed")
    flat = simulate(
        plan([], [cash()], _severance_at(date(2027, 1, 1), gross / level[12])),
        zero_returns(24),
        "fixed",
    )
    assert hot.taxes[0, 12:].sum() == pytest.approx(flat.taxes[0, 12:].sum() * level[12], abs=5)


def test_tax_free_other_income_is_not_settled() -> None:
    def december_tax(*, taxable: bool) -> float:
        income = Stream(name="i", kind=StreamKind.OTHER_INCOME, amount=5000, taxable=taxable)
        p = plan([income], [cash()])
        return float(zero_run(p, 12).taxes[0, 11])

    assert december_tax(taxable=False) == 0.0
    assert december_tax(taxable=True) < 0.0


def test_taxable_lump_sum_is_settled_in_december() -> None:
    scenario = Scenario(
        name="l",
        events=[LumpSumEvent(at=date(2026, 6, 1), type="lump_sum", amount=60_000, taxable=True)],
    )
    p = plan([], [cash()], scenario)
    r = zero_run(p, 12)
    # other income gets no Werbungskosten-Pauschbetrag, the Sonderausgaben-Pauschbetrag
    assert r.taxes[0, 11] == pytest.approx(-float(income_tax(60_000 - SA, TY)))


def _church_taxes(kind: StreamKind, church: bool) -> FloatArray:
    """The taxes of each year of a plan of 5,000 a month of `kind`, as a member of a church in
    NW or not."""
    paid = {"gross" if kind == StreamKind.SALARY else "amount": 5000}
    income = Stream.model_validate({"name": "i", "kind": kind, "index": None} | paid)
    tax = {"church": church, "land": "NW"}
    p = plan([income], [cash()], tax=tax)
    return np.asarray(zero_run(p, 24).taxes[0].reshape(2, 12).sum(axis=1))


def _with_church(zve: float, paid: float) -> float:
    """Income tax, Soli and 9% church tax of a year that deducts the church tax `paid`, at least
    the Sonderausgaben-Pauschbetrag (§10c EStG)."""
    t = float(income_tax(zve - max(paid, SA), TY))
    return t + float(soli(t, TY)) + 0.09 * t


def test_the_church_tax_paid_in_a_year_is_its_sonderausgabe() -> None:
    """9% of the income tax (§51a EStG), deducted in the year of its payment (§10 Abs. 1 Nr. 4):
    the withholding of a salary in the year itself; the settlement of other income, which the
    engine pays in December, as in the next year's assessment."""
    zve = 60_000 - TY.werbungskosten_pauschale - 12 * 5000 * TY.rv_rate  # the employer's RV aside
    plain, church = _church_taxes(StreamKind.SALARY, False), _church_taxes(StreamKind.SALARY, True)
    t = float(income_tax(zve - SA, TY))
    assert church[0] - plain[0] == pytest.approx(-(_with_church(zve, 0.09 * t) - t - soli(t, TY)))
    plain = _church_taxes(StreamKind.OTHER_INCOME, False)
    church = _church_taxes(StreamKind.OTHER_INCOME, True)
    t = float(income_tax(60_000 - SA, TY))
    assert plain[0] == plain[1] == pytest.approx(-(t + soli(t, TY)))
    assert church[0] == pytest.approx(-_with_church(60_000, 0.0))
    assert church[1] == pytest.approx(-_with_church(60_000, 0.09 * t))


def test_health_premium_parts_are_streams() -> None:
    scenario = Scenario(
        name="h", phases=phases((date(2026, 1, 1), "work"), (date(2026, 3, 1), "unemployed"))
    )
    p = plan(
        [
            Stream(name="salary", kind=StreamKind.SALARY, gross=5000, phases=["work"]),
            Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"]),
            Stream(name="kv", amount=-900, health="kv", index=None),
            Stream(name="zuschlag", amount=-80, health="kv", index=None, end=date(2026, 2, 1)),
            Stream(name="ktg", amount=-40, health="kv", index=None, phases=["work"]),
            Stream(name="pv", amount=-70, health="pv", index=None),
        ],
        [cash(100_000)],
        scenario,
    )
    r = zero_run(p, 4)
    assert r.expenses[0].tolist() == pytest.approx([-1090, -1010, -970, -970])
    # employer: 8.75% of the salary below the BBG, under half of KV, plus half of PV. Agentur:
    # KV up to 813.75 plus PV.
    alg1 = float(alg1_month(5000, TY, child=False))
    assert r.income[0].tolist() == pytest.approx(
        [5000 + 437.5 + 35, 5000 + 437.5 + 35, alg1 + 813.75 + 70, alg1 + 813.75 + 70]
    )


def test_the_pkv_subsidy_follows_the_salary_and_alg1_not_the_phase() -> None:
    """§257 Abs. 2 SGB V: 8.75% of the month's contributory salary, a one-off within the BBG of
    the year included, at most half the premium, none in `work` without a salary. §174 SGB III:
    the Agentur while ALG1 pays, in any phase."""
    p = plan(
        [
            Stream(
                name="pay",
                kind=StreamKind.SALARY,
                gross=4000,
                phases=["alt"],
                end=date(2026, 4, 1),
            ),
            Stream(
                name="bonus", kind=StreamKind.SALARY, gross=2000, every=12, start=date(2026, 3, 1)
            ),
            Stream(name="alg", kind=StreamKind.ALG1, start=date(2026, 4, 1)),
            Stream(name="kv", amount=-1100, health="kv", index=None),
            Stream(name="pv", amount=-220, health="pv", index=None),
        ],
        [cash(100_000)],
        Scenario(name="s", phases=phases((date(2026, 1, 1), "work"), (date(2026, 2, 1), "alt"))),
    )
    r = zero_run(p, 4)
    alg1 = float(alg1_month(4000, TY, child=False))
    # below the caps of half the premium (550 and 110): the bonus counts in March
    assert r.income[0].tolist() == pytest.approx(
        [0.0, 4000 + 350 + 72, 6000 + 525 + 108, alg1 + 813.75 + 167.40]
    )


def test_health_premium_only_falls_due_on_its_own_period() -> None:
    p = plan(
        [
            Stream(name="kk", amount=-300, health="kv", every=3, index=None),
            Stream(name="pay", kind=StreamKind.SALARY, gross=6000, index=None),
        ],
        [cash(100_000)],
    )
    r = zero_run(p, 4)
    assert r.expenses[0].tolist() == [-300.0, 0.0, 0.0, -300.0]
    # the salary and the employer's half of the premium, below the cap
    assert r.income[0].tolist() == [6150.0, 6000.0, 6000.0, 6150.0]


def test_only_the_deductible_share_of_a_premium_is_a_sonderausgabe() -> None:
    """Per month, the employer pays 485 of the premium. The Basisabsicherung is 450 + 70 with
    half of KV deductible, 720 + 70 with the default share: 270 less to deduct."""

    def taxes(share: float | None) -> float:
        p = plan(
            [
                Stream(name="salary", kind=StreamKind.SALARY, gross=6000, phases=["work"]),
                Stream(name="kv", amount=-900, health="kv", index=None, deductible=share),
                Stream(name="pv", amount=-70, health="pv", index=None),
            ],
            [cash()],
        )
        return float(-zero_run(p, 12).taxes[0].sum())

    more = taxes(0.5) - taxes(None)
    assert 0.3 * 270 * 12 < more < 0.45 * 270 * 12


def test_health_subsidy_and_deduction_follow_inflation() -> None:
    """The PKV subsidy caps are start-year constants, so the engine must deflate the
    premium before applying them. The caps then follow the price level of the year."""
    scenario = Scenario(
        name="u",
        phases=phases((date(2026, 1, 1), "work"), (date(2030, 1, 1), "unemployed")),
    )
    p = plan(
        [
            Stream(name="g", kind=StreamKind.SALARY, gross=8000, phases=["work"]),
            Stream(name="kk", amount=-1200, health="kv"),
            Stream(name="a", kind=StreamKind.ALG1, phases=["unemployed"]),
        ],
        [cash(500_000)],
        scenario,
    )
    flat = zero_run(p, 120)
    inflated = zero_returns(120)
    inflated.inflation[:] = 0.05 / 12
    hot = simulate(p, inflated, "fixed")
    cpi, level = levels(inflated)
    # the salary follows the CPI, the capped subsidy the price level of the year. ALG1 is
    # granted as a nominal amount at entry, on the last nominal salary at the new level.
    paid = flat.income[0, 48:] > 0
    granted = alg1_month(8000 * cpi[47] / level[48], TY, child=False) * level[48]
    expected = flat.income[0] * level
    expected[:48] += 8000 * (cpi[:48] - level[:48])
    plain = alg1_month(8000.0, TY, child=False) * level[48:]
    expected[48:] += np.where(paid, granted - plain, 0.0)
    np.testing.assert_allclose(hot.income[0], expected, rtol=1e-4, atol=2.0)
    assert hot.income[0, 49] - hot.income[0, 48] < 0.01 * granted


def test_gkv_contributions_are_deducted_in_the_settlement() -> None:
    p = plan(
        [Stream(name="g", kind=StreamKind.SALARY, gross=5000)],
        [cash()],
        tax={"pkv": False},
    )
    r = zero_run(p, 12)
    assert abs(r.taxes[0, 11] - r.taxes[0, 10]) < 100  # withholding already was about right


def test_the_pv_discount_ends_with_the_month_of_the_25th_birthday() -> None:
    """The elder of two children turns 25 in June 2027: the discount of 0.25 points of the
    second child under 25 holds through that month and ends after it."""

    def run(*born: date) -> RunResult:
        p = plan(
            [Stream(name="g", kind=StreamKind.SALARY, gross=5000)],
            [cash()],
            person=Person(
                born=date(1977, 1, 1), children=2, children_born=[Child(born=b) for b in born]
            ),
            tax={"pkv": False},
        )
        return zero_run(p, 24)

    discounted, plain = run(date(2002, 6, 15), date(2015, 1, 1)).taxes[0], run().taxes[0]
    assert np.all(discounted[:18] > plain[:18])  # taxes are negative: less SV
    assert discounted[18:23] == pytest.approx(plain[18:23])


def _retire_at(month: date) -> Scenario:
    return Scenario(name="r", phases=phases((date(2026, 1, 1), "alt"), (month, "retired")))


def _pension_stream() -> Stream:
    return Stream(
        name="r",
        kind=StreamKind.PENSION,
        points=50.0,
        point_value=40.0,
        phases=["retired"],
        index=None,
    )


def test_pension_claim_at_63_with_abschlag_and_voluntary_years() -> None:
    # born 1977-01: 63 in 2040-01. rv_since gives 32 years at start, voluntary fills the gap.
    voluntary = Stream(name="v", kind=StreamKind.RV_VOLUNTARY, amount=-110, phases=["alt"])
    p = plan(
        [voluntary, _pension_stream()],
        [cash(100_000)],
        _retire_at(date(2040, 2, 1)),
        person=Person(born=date(1977, 1, 1), rv_since=date(1994, 1, 1)),
        pension_growth=0.0,
    )
    n = horizon_months(p.assumptions)
    r = zero_run(p, n)
    first = months_between(date(2026, 1, 1), date(2040, 2, 1))
    assert r.income[0, first - 1] == 0.0
    earned = first * 110 / (TY.rv_rate_total * TY.durchschnittsentgelt)
    abschlag = (67 - (63 + 1 / 12)) * 12 * 0.003  # claim at 63 and one month
    assert r.income[0, first] == pytest.approx((50 + earned) * 40 * (1 - abschlag))
    assert any(m.kind == "pension" and round(m.amount, 3) == 0.859 for m in r.markers)


def test_salary_and_voluntary_count_one_month_each() -> None:
    # rv_since 2000-01: 26 years at start, alt with salary and voluntary until 2040-02: 40 years.
    voluntary = Stream(name="v", kind=StreamKind.RV_VOLUNTARY, amount=-110, phases=["alt"])
    salary = Stream(name="s", kind=StreamKind.SALARY, gross=1000, phases=["alt"], index=None)
    p = plan(
        [voluntary, salary, _pension_stream()],
        [cash(100_000)],
        _retire_at(date(2040, 2, 1)),
        person=Person(born=date(1977, 1, 1), rv_since=date(2000, 1, 1)),
    )
    r = zero_run(p, horizon_months(p.assumptions))
    assert any(m.kind == "pension" and round(m.years) == 40 for m in r.markers)


def test_pension_deferred_to_67_without_35_years() -> None:
    p = plan(
        [_pension_stream()],
        [cash(100_000)],
        _retire_at(date(2040, 2, 1)),
        person=Person(born=date(1977, 1, 1), rv_since=date(2010, 1, 1)),
        pension_growth=0.0,
    )
    n = horizon_months(p.assumptions)
    r = zero_run(p, n)
    at_63 = months_between(date(2026, 1, 1), date(2040, 2, 1))
    at_67 = months_between(date(2026, 1, 1), date(2044, 1, 1))
    assert r.income[0, at_63] == 0.0
    assert r.income[0, at_67 - 1] == 0.0
    assert r.income[0, at_67] == pytest.approx(50 * 40)
    assert any(m.kind == "pension" and m.since == date(2040, 2, 1) for m in r.markers)


@pytest.mark.parametrize("index", ["cpi", None])
def test_the_pension_follows_its_index_and_grows_on_top(index: str | None) -> None:
    """In euros of the start, like every stream: the consumer prices of the path by default, and
    `pension_growth` on top, stepped each January."""
    pension = Stream(name="r", kind=StreamKind.PENSION, gross=1000, phases=["retired"], index=index)
    p = plan(
        [pension],
        [cash()],
        _retire_at(date(2026, 1, 1)),
        person=Person(born=date(1959, 1, 1)),
        pension_growth=0.01,
    )
    returns = zero_returns(24)
    returns.inflation[:] = 0.002
    r = simulate(p, returns, "fixed")
    prices = 1.002 ** np.arange(24) if index else np.ones(24)
    assert r.income[0] == pytest.approx(1000 * prices * 1.01 ** (np.arange(24) // 12))


def test_pension_waits_for_the_sale_that_starts_it() -> None:
    scenario = Scenario(
        name="x",
        phases=phases((date(2026, 1, 1), "retired")),
        events=[SellEvent(type="sell", asset="h", when=SaleTrigger(age=200))],
    )
    p = plan(
        [
            Stream(
                name="r",
                kind=StreamKind.PENSION,
                gross=1000,
                phases=["retired"],
                index=None,
                after_sale_of="h",
            )
        ],
        [
            cash(1000),
            PropertyAsset(id="h", kind="property", sqm=1, per_sqm=1),
        ],
        scenario,
        person=Person(born=date(1959, 1, 1)),  # 67 at the start, so the claim is possible
    )
    r = zero_run(p, 2)
    assert r.income[0].tolist() == [0.0, 0.0]


def test_two_pensions_share_one_pkv_subsidy() -> None:
    def income(*gross: float) -> float:
        scenario = Scenario(name="r", phases=phases((date(2026, 1, 1), "retired")))
        p = plan(
            [
                *(
                    Stream(name=f"r{n}", kind=StreamKind.PENSION, gross=g)
                    for n, g in enumerate(gross)
                ),
                Stream(name="kk", amount=-300, health="kv"),
            ],
            [cash(100_000)],
            scenario,
            person=Person(born=date(1959, 1, 1)),
        )
        return float(zero_run(p, 1).income[0, 0])

    assert income(2000, 2000) == pytest.approx(income(4000))
    assert income(4000) == pytest.approx(4000 + 150)  # capped at half of the premium


def test_rentenfreibetrag_is_fixed_after_the_first_full_year() -> None:
    """The tax-free part of the pension is frozen in euros at the end of the first full
    year, so every later increase of the pension is taxed in full."""
    p = plan(
        [
            Stream(name="r", kind=StreamKind.PENSION, gross=2000, phases=["retired"]),
            Stream(name="x", amount=-1000, index=None),  # keeps the cash buffer above the cash
        ],
        [cash(500_000)],
        _retire_at(date(2044, 1, 1)),
        person=Person(born=date(1977, 1, 1), rv_since=date(1994, 1, 1)),
        pension_growth=0.02,
    )
    n = months_between(date(2026, 1, 1), date(2047, 1, 1))
    r = zero_run(p, n)

    share = pension_share(2044, TY)
    gross = {y: 12 * 2000 * 1.02 ** (y - 2026) for y in (2044, 2045, 2046)}
    freibetrag = gross[2045] * (1 - share)

    def settled(taxable: float) -> float:
        t = float(income_tax(max(taxable - TY.pension_pauschbetrag - SA, 0.0), TY))
        return t + float(soli(t, TY))

    def december(year: int) -> int:
        return months_between(date(2026, 1, 1), date(year, 12, 1))

    assert r.taxes[0, december(2044)] == pytest.approx(-settled(gross[2044] * share), rel=1e-3)
    assert r.taxes[0, december(2045)] == pytest.approx(-settled(gross[2045] * share), rel=1e-3)
    assert r.taxes[0, december(2046)] == pytest.approx(-settled(gross[2046] - freibetrag), rel=1e-3)
    assert settled(gross[2046] - freibetrag) > settled(gross[2046] * share)


def _severance_at(month: date, gross: float, bav: PolicyFunding | None = None) -> Scenario:
    return Scenario(
        name="s", events=[SeveranceEvent(at=month, type="severance", gross=gross, bav=bav)]
    )


def test_severance_is_reported_as_income_and_withholding() -> None:
    scenario = Scenario(
        name="s",
        events=[SeveranceEvent(at=date(2026, 6, 1), type="severance", gross=100_000)],
    )
    p = plan([], [cash()], scenario)
    r = zero_run(p, 12)
    assert r.income[0, 5] == pytest.approx(100_000)
    # the employer withholds the full tariff, December applies the Fünftelregelung
    assert r.taxes[0, 5] == pytest.approx(-float(year_tax(100_000, TY, church=0.0)))
    assert r.taxes[0, 11] > 0
    assert r.liquid[0, 11] == pytest.approx(r.income[0].sum() + r.taxes[0].sum())


def _work_then_retire(month: date) -> Scenario:
    return Scenario(name="b", phases=phases((date(2026, 1, 1), "work"), (month, "retired")))


def _policy(**kw: object) -> PensionPolicy:
    base: dict[str, object] = {
        "id": "bav",
        "kind": "bav",
        "value": 1000,
        "paid": 1000,
        "contribution": 100,
        "phases": ["work"],
        "matures": date(2027, 1, 1),
        "growth": "fixed_income",
    }
    return PensionPolicy.model_validate(base | kw)


def test_bav_lump_sum_with_guarantee_floor_and_fuenftelregelung() -> None:
    policy = _policy(value=0, paid=10_000, guarantee=0.8)
    p = plan([], [cash(), policy], _work_then_retire(date(2026, 2, 1)))
    r = zero_run(p, 13)
    assert r.liquid[0, 11] == 0.0
    assert r.liquid[0, 12] == pytest.approx(0.8 * 10_100)  # below the Grundfreibetrag, untaxed
    assert any((m.kind, m.detail, round(m.amount)) == ("bav", "bav", 8080) for m in r.markers)


def test_bav_lump_sum_taxed_at_tariff_without_fuenftel() -> None:
    policy = _policy(value=100_000, paid=0, matures=date(2026, 6, 1), fuenftel=False)
    p = plan([], [cash(), policy], _work_then_retire(date(2026, 1, 1)))
    r = zero_run(p, 12)
    assert r.liquid[0, 5] == pytest.approx(100_000)
    assert -40_000 < r.taxes[0, 11] < -25_000


def test_bav_annuity_is_taxable_income() -> None:
    policy = _policy(value=120_000, paid=0, payout="annuity", annuity_per_10k=250)
    p = plan([], [cash(), policy], _work_then_retire(date(2026, 1, 1)))
    r = zero_run(p, 36)
    assert r.income[0, 11] == 0.0
    assert r.income[0, 12] == pytest.approx(3000)
    assert r.income[0, 35] == pytest.approx(3000)
    # the capital less payments received stays in total, floored at zero
    assert r.total[0, 12] - r.liquid[0, 12] == pytest.approx(117_000)
    assert r.total[0, 35] - r.liquid[0, 35] == pytest.approx(48_000)
    assert -8000 < r.taxes[0, 23] < -4000


BASISRENTE = {"basisrente": True, "payout": "annuity", "annuity_per_10k": 40}


def _empty_policy(**kw: object) -> PensionPolicy:
    empty: dict[str, object] = {"value": 0, "paid": 0, "contribution": 0, "phases": []}
    return _policy(**(empty | {"matures": date(2030, 1, 1)} | kw))


def test_severance_bav_part_is_tax_free_and_lands_in_the_policy() -> None:
    plain = simulate(
        plan([], [cash(), _empty_policy()], _severance_at(date(2026, 6, 1), 100_000)),
        zero_returns(12),
        "fixed",
    )
    funding = PolicyFunding(policy="bav", amount=40_000)
    split = simulate(
        plan([], [cash(), _empty_policy()], _severance_at(date(2026, 6, 1), 100_000, funding)),
        zero_returns(12),
        "fixed",
    )
    assert split.income[0, 5] == pytest.approx(60_000)
    assert split.total[0, 5] - split.liquid[0, 5] == pytest.approx(40_000)
    assert split.taxes[0].sum() > plain.taxes[0].sum()
    zve = 60_000 - TY.werbungskosten_pauschale - TY.sonderausgaben_pauschbetrag
    assert split.taxes[0].sum() == pytest.approx(-5 * float(income_tax(zve / 5, TY)))


def test_fund_policy_moves_cash_into_a_basisrente_and_deducts() -> None:
    scenario = Scenario(
        name="f",
        events=[
            LumpSumEvent(at=date(2026, 3, 1), type="lump_sum", amount=100_000, taxable=True),
            FundPolicyEvent(at=date(2026, 6, 1), type="fund_policy", policy="bav", amount=20_000),
        ],
    )
    p = plan([], [cash(), _empty_policy(**BASISRENTE)], scenario)
    r = zero_run(p, 12)
    assert r.liquid[0, 5] == pytest.approx(80_000)
    assert r.total[0, 5] == pytest.approx(100_000)
    tax = income_tax(80_000 - TY.sonderausgaben_pauschbetrag, TY)
    assert r.taxes[0, 11] == pytest.approx(-float(tax + soli(tax, TY)))


def test_empty_policy_pays_nothing_and_leaves_no_marker() -> None:
    p = plan([], [cash(), _empty_policy(matures=date(2026, 6, 1))])
    r = zero_run(p, 12)
    assert not any(m.kind == "bav" for m in r.markers)
    assert r.liquid[0, 11] == 0.0


def test_av_depot_takes_the_contribution_and_pays_out_from_the_regelaltersgrenze() -> None:
    """Born 1961: salary in 2027, 67 in January 2028. December 2027 pays 1,800 and the
    Zulage of 540 into the depot, January 2028 pays 30% at once and the rest over 216 months."""
    depot = AvDepot(id="av", kind="av_depot", start=date(2027, 1, 1))
    scenario = Scenario(
        name="av",
        phases=phases((date(2026, 1, 1), "work"), (date(2028, 1, 1), "retired")),
    )
    p = plan(
        [Stream(name="salary", kind=StreamKind.SALARY, gross=5000, phases=["work"])],
        [cash(), depot],
        scenario,
        person=Person(born=date(1961, 1, 1)),
    )
    r = zero_run(p, 26)
    assert r.total[0, 23] - r.liquid[0, 23] == pytest.approx(2340.0)
    assert r.total[0, 11] == pytest.approx(r.liquid[0, 11])  # no subsidy before 2027
    assert r.income[0, 24] == pytest.approx(0.3 * 2340 + 0.7 * 2340 / 216)
    assert r.total[0, 25] - r.liquid[0, 25] == pytest.approx(0.7 * 2340 * 214 / 216)


def test_a_pension_in_a_start_year_before_the_oldest_year_file_takes_its_share() -> None:
    """A start before 2023 taxes the pension of its first year at the Besteuerungsanteil of 2023."""
    pension = Stream(name="r", kind=StreamKind.PENSION, gross=2000, index=None)
    p = plan([pension], [cash()], start=date(2021, 1, 1), person=Person(born=date(1950, 1, 1)))
    r = simulate(p, zero_returns(36), "fixed")
    assert r.taxes[0, 11] < 0
