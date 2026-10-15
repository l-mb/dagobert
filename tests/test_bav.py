"""A salary conversion into a bAV policy (Entgeltumwandlung): the law in amounts, the engine as
relations between runs with and without it."""

from collections.abc import Callable
from datetime import date

import pytest
from builders import CLASSES, booked, cash, phases, plan, zero_run

from dagobert import budget, carry
from dagobert.model.assets import PensionPolicy
from dagobert.model.assumptions import Person
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import TaxOptions
from dagobert.result import CONVERSION, SOURCE, SPENDING, RunResult
from dagobert.sv import alg1_month, conversion
from dagobert.tax import for_year

TY = for_year(2026)
GKV, PKV = TaxOptions(pkv=False), TaxOptions(pkv=True)


@pytest.mark.parametrize(
    ("gross", "converted", "employer", "opts", "subsidy", "expected"),
    [
        # a GKV member below the KV-BBG: the employer saves 21.15% (RV 9.3, ALV 1.3, KV 8.75,
        # PV 1.8) and adds 15%
        (4000, 200, 0, GKV, None, (30, 200, 200)),
        # above the KV-BBG of 5,812.50 it saves only the RV and the ALV, 10.6%, as for a PKV member
        (7000, 200, 0, GKV, None, (21.2, 200, 200)),
        (4000, 200, 0, PKV, None, (21.2, 200, 200)),
        # above the RV-BBG of 8,450 it saves nothing
        (9000, 200, 0, GKV, None, (0, 200, 200)),
        # 4% of the BBG, 338 a month: the subsidy beyond it stays in the SV gross
        (4000, 338, 0, GKV, None, (50.7, 338, 287.3)),
        # beyond 8%, 676, the tax too; the saving counts the 338 free of SV alone: 35.83
        (4000, 800, 0, PKV, None, (35.828, 640.172, 302.172)),
        # the employer's own contribution fills both rooms first: 38 left of the SV, 4.03 saved
        (4000, 200, 300, PKV, None, (4.028, 200, 33.972)),
        # a subsidy of the contract is paid in full
        (9000, 200, 0, GKV, 0.2, (40, 200, 200)),
    ],
)
def test_the_conversion_within_the_limits_of_2026(
    gross: float,
    converted: float,
    employer: float,
    opts: TaxOptions,
    subsidy: float | None,
    expected: tuple[float, float, float],
) -> None:
    """§3 Nr. 63 EStG, §1 Abs. 1 S. 1 Nr. 9 SvEV, §1a Abs. 1a BetrAVG, BMF Rn. 30 f."""
    got = conversion(converted, gross, employer, opts, TY, subsidy=subsidy)
    assert (got.subsidy, got.tax_free, got.sv_free) == pytest.approx(expected, abs=1e-3)


def _run(converted: float, *, pkv: bool) -> RunResult:
    """Born 1960: a salary of 4,000 for six months, ALG1 for six, the pension from 2027 at 67."""
    streams = [
        Stream(name="pay", kind=StreamKind.SALARY, gross=4000, phases=["work"], index=None),
        Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"]),
        Stream(
            name="rente", kind=StreamKind.PENSION, points=30, point_value=40, phases=["retired"]
        ),
    ]
    if pkv:  # below the caps of half the premium: the subsidy follows the salary
        streams += [
            Stream(name="kv", amount=-1200, health="kv", index=None),
            Stream(name="pv", amount=-200, health="pv", index=None),
        ]
    policy = PensionPolicy(
        id="bav",
        kind="bav",
        value=0,
        contribution=0,
        conversion=converted,
        phases=["work"],
        matures=date(2040, 1, 1),
        growth="fixed_income",
    )
    scenario = Scenario(
        name="c",
        phases=phases(
            (date(2026, 1, 1), "work"),
            (date(2026, 7, 1), "unemployed"),
            (date(2027, 1, 1), "retired"),
        ),
    )
    p = plan(
        streams,
        [cash(100_000), policy],
        scenario,
        person=Person(born=date(1960, 1, 1)),
        tax={"pkv": pkv},
    )
    return zero_run(p, 13)


def test_a_conversion_lowers_the_contributory_salary_and_the_tax() -> None:
    """The SV, the ALG1 and the Entgeltpunkte follow the salary less the conversion (§151 Abs. 1
    SGB III: the contributory salary), the policy takes it with the subsidy, the tax falls."""
    plain, converted = _run(0, pkv=False), _run(200, pkv=False)
    ratio = 3800 / 4000
    for item in ("RV", "AV", "KV"):
        assert booked(converted, item)[:6] == pytest.approx(ratio * booked(plain, item)[:6])
    assert booked(converted, "income tax").sum() < booked(plain, "income tax").sum()
    added = converted.nominal_balance["policies"] - plain.nominal_balance["policies"]
    assert added[5] == pytest.approx(6 * 230)  # 15%: the employer saves more
    alg1 = float(alg1_month(3800, TY, child=False))
    assert booked(converted, "alg", SOURCE)[6] == pytest.approx(alg1)
    # six months of salary and six of ALG1, which earn 80% of the points of its salary
    lost = (6 + 6 * TY.alg1_rv_share) * 200 / TY.durchschnittsentgelt * 40
    pension_lost = booked(plain, "rente", SOURCE)[12] - booked(converted, "rente", SOURCE)[12]
    assert pension_lost == pytest.approx(lost)


def test_a_conversion_lowers_the_pkv_subsidy_of_the_employer() -> None:
    """§257 Abs. 2 SGB V takes the contributory salary; the subsidy of the conversion is what
    the employer saves of the RV and the ALV, 10.6%."""
    plain, converted = _run(0, pkv=True), _run(200, pkv=True)
    assert booked(converted, "PKV subsidy", SOURCE)[:6] == pytest.approx(
        3800 / 4000 * booked(plain, "PKV subsidy", SOURCE)[:6]
    )
    added = converted.nominal_balance["policies"] - plain.nominal_balance["policies"]
    assert added[5] == pytest.approx(6 * 221.2)


def test_the_conversion_leaves_the_surplus_and_stays_in_the_net_worth() -> None:
    """A spending group of its own, whose policy side counts like the loan principal, and the
    subsidy as non-cash income."""
    r = _run(200, pkv=False)
    assert r.ledger is not None
    first = budget.from_ledger(r.ledger, range(6))
    assert first.spending[CONVERSION] == {"bav": pytest.approx(200)}
    assert first.assets == {f"{CONVERSION}: bav": pytest.approx(200)}
    assert first.noncash == {"bav: subsidy": pytest.approx(30)}
    assert first.wealth_built - first.surplus == pytest.approx(230)


@pytest.mark.parametrize(
    ("salary", "months"), [(None, [200.0] * 6), ("b", [0.0] * 3 + [200.0] * 3)]
)
def test_the_conversion_takes_from_its_salary(salary: str | None, months: list[float]) -> None:
    """Without a name from the monthly salary that pays, else from the named one alone."""
    pay = [
        Stream(name=name, kind=StreamKind.SALARY, gross=3000, phases=[phase], index=None)
        for name, phase in (("a", "work"), ("b", "alt"))
    ]
    policy = PensionPolicy(
        id="bav",
        kind="bav",
        value=0,
        contribution=0,
        conversion=200,
        salary=salary,
        phases=["work", "alt"],
        matures=date(2040, 1, 1),
        growth="cash",
    )
    scenario = Scenario(
        name="s", phases=phases((date(2026, 1, 1), "work"), (date(2026, 4, 1), "alt"))
    )
    r = zero_run(plan(pay, [policy], scenario), 6)
    assert booked(r, "bav", SPENDING, CONVERSION) == pytest.approx(months)


def test_conversions_from_one_salary_take_at_most_its_gross() -> None:
    """Each takes what the conversions before it leave of the salary."""
    policies = [
        PensionPolicy(
            id=name,
            kind="bav",
            value=0,
            conversion=800,
            phases=["work"],
            matures=date(2040, 1, 1),
            growth="cash",
        )
        for name in ("a", "b")
    ]
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=1000, index=None)
    r = zero_run(plan([pay], [cash(), *policies]), 1)
    taken = [float(booked(r, name, SPENDING, CONVERSION)[0]) for name in ("a", "b")]
    assert taken == pytest.approx([800, 200])


def test_a_conversion_names_a_monthly_salary() -> None:
    bonus = Stream(name="bonus", kind=StreamKind.SALARY, of="pay", share=0.1, every=12)
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=3000)
    policy = PensionPolicy(
        id="bav",
        kind="bav",
        value=0,
        contribution=0,
        conversion=100,
        salary="bonus",
        phases=[],
        matures=date(2040, 1, 1),
    )
    with pytest.raises(
        ValueError, match="no monthly salary stream without `of` has the name bonus"
    ):
        plan([pay, bonus], [policy])


def test_the_tax_year_sets_the_limits_of_a_conversion(later_tax_year: Callable[..., int]) -> None:
    """Half the room of the SV: 169 less the subsidy of 30 is free of SV, not all 200."""
    later = later_tax_year(bav_sv_free_share=TY.bav_sv_free_share / 2)
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None)
    policy = PensionPolicy(
        id="bav",
        kind="bav",
        value=0,
        contribution=0,
        conversion=200,
        phases=["work"],
        matures=date(2040, 1, 1),
        growth="cash",
    )

    def rv(year: int) -> float:
        p = plan([pay], [policy], tax={"pkv": False, "year": year})
        return float(booked(zero_run(p, 1), "RV")[0])

    assert rv(TY.year) == pytest.approx((4000 - 200) * TY.rv_rate)
    assert rv(later) == pytest.approx((4000 - 139) * TY.rv_rate)


CARRIED = {
    # without a date, or a date in the start month: the value at the start
    "undated": ({}, (10_000, 8000)),
    "start month": ({"asof": date(2026, 1, 15)}, (10_000, 8000)),
    # October to December: the employer's 100, the conversion of 200 and its subsidy of 15%,
    # below the 21.15% that the employer of a GKV member below the KV-BBG saves (§1a Abs. 1a
    # BetrAVG)
    "contributions": ({"asof": date(2025, 9, 30)}, (10_000 + 3 * 330, 8000 + 3 * 330)),
    # a phase without the policy pays none; the mean return of its class less the cost grows it
    "outside its phases": ({"asof": date(2025, 9, 30), "phases": ["alt"]}, (10_000, 8000)),
    "growth": (
        {"asof": date(2025, 9, 30), "growth": "equity", "cost": 0.012, "phases": []},
        (10_000 * 1.1 ** (3 / 12) * 0.999**3, 8000),
    ),
    "matured": ({"asof": date(2025, 9, 30), "matures": date(2025, 11, 1)}, (10_330, 8330)),
}


@pytest.mark.parametrize(("fields", "carried"), CARRIED.values(), ids=CARRIED.keys())
def test_a_policy_carries_its_value_from_its_date(
    fields: dict[str, object], carried: tuple[float, float]
) -> None:
    """Value and paid through the month before the start, as the engine opens them: matured in
    November, October alone counts."""
    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=4000, index=None)
    policy = PensionPolicy.model_validate(
        {"id": "bav", "kind": "bav", "value": 10_000, "paid": 8000, "contribution": 100}
        | {"conversion": 200, "phases": ["work"], "matures": date(2040, 1, 1), "growth": "cash"}
        | fields
    )
    returns = {c: {"mean": 0.1 if c == "equity" else 0.0} for c in CLASSES}
    p = plan([pay], [policy], tax={"pkv": False}, returns=returns)
    assert carry.policy(p, policy, date(2025, 12, 1)) == pytest.approx(carried)


@pytest.mark.parametrize(("phases", "months"), [(["work"], 3), (["alt"], 0)])
def test_a_basisrente_carries_its_own_premium(phases: list[str], months: int) -> None:
    """The own premium of a Basisrente adds to value and paid in each month of its phases, as the
    engine pays it from the start: October to December."""

    def carried(premium: float) -> tuple[float, float]:
        policy = PensionPolicy.model_validate(
            {"id": "basis", "kind": "bav", "value": 10_000, "paid": 8000, "premium": premium}
            | {"basisrente": True, "payout": "annuity", "annuity_per_10k": 30, "phases": phases}
            | {"matures": date(2040, 1, 1), "growth": "cash", "asof": date(2025, 9, 30)}
        )
        p = plan([], [policy], returns={c: {"mean": 0.0} for c in CLASSES})
        return carry.policy(p, policy, date(2025, 12, 1))

    (value, paid), (value_0, paid_0) = carried(200), carried(0)
    assert (value - value_0, paid - paid_0) == pytest.approx((months * 200, months * 200))


def test_a_monthly_share_of_a_salary_counts_in_the_gross_of_a_conversion() -> None:
    """The carry reads the regular gross of every monthly salary, also of a share of another
    (`of`), as the engine does: 4500 and a share of 100% of it lie above the RV-BBG of 8450 like
    one salary of 9000, so the conversion saves the employer no SV and takes no subsidy, while
    4500 alone takes 15% (October to December). Without `salary` the conversion comes off the
    salary without `of`, also behind a share of 1% that pays less than it converts."""
    policy = PensionPolicy.model_validate(
        {"id": "bav", "kind": "bav", "value": 0, "contribution": 0, "conversion": 200}
        | {"phases": ["work"], "matures": date(2040, 1, 1), "growth": "cash"}
        | {"asof": date(2025, 9, 30)}
    )

    def carried(*streams: Stream) -> tuple[float, float]:
        p = plan(list(streams), [policy], tax={"pkv": False})
        return carry.policy(p, policy, date(2025, 12, 1))

    pay = Stream(name="pay", kind=StreamKind.SALARY, gross=4500, index=None)
    share = Stream(name="extra", kind=StreamKind.SALARY, of="pay", share=1, index=None)
    small = share.model_copy(update={"share": 0.01})
    assert carried(pay, share) == carried(pay.model_copy(update={"gross": 9000})) == (600, 600)
    assert carried(pay) == pytest.approx((690, 690))
    assert carried(small, pay) == carried(pay, small) == pytest.approx((690, 690))
