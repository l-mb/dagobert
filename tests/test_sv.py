"""The social insurance of `sv`: the law in amounts of 2026."""

from datetime import date
from typing import Literal

import pytest

from dagobert.model.assumptions import Child, Person
from dagobert.model.taxes import TAX_YEARS, SelfEmployed, TaxOptions
from dagobert.sv import (
    agentur_pkv_subsidy,
    alg1_month,
    alg1_months,
    em_factor,
    employer_pkv_subsidy,
    krankengeld_month,
    kv_compulsory,
    kv_voluntary,
    pension_claim,
    pension_net_month,
    pension_points,
    rv_self_employed,
    sv_bases,
    sv_employee,
    voluntary_points,
)
from dagobert.tax import for_year

PERSON = Person(born=date(1985, 1, 1))
PERSON_KIDS = Person(born=date(1985, 1, 1), children=1)
MONTH = date(2026, 1, 1)
OPTS_PKV = TaxOptions(pkv=True)
OPTS_GKV = TaxOptions(pkv=False)
TY = for_year(2026)


@pytest.mark.parametrize(
    ("gross", "opts", "person", "parts"),
    [
        (6000.0, OPTS_GKV, PERSON, (558.0, 78.0, 508.59375, 139.5)),
        (6000.0, OPTS_GKV, PERSON_KIDS, (558.0, 78.0, 508.59375, 5812.5 * 0.018)),  # no surcharge
        (9000.0, OPTS_PKV, PERSON, (785.85, 109.85, 0.0, 0.0)),
    ],
    ids=["gkv childless", "gkv with a child", "pkv"],
)
def test_sv_employee(
    gross: float, opts: TaxOptions, person: Person, parts: tuple[float, float, float, float]
) -> None:
    """RV, ALV, KV and PV of the employee, each up to its BBG; a PKV member pays no KV or PV."""
    sv = sv_employee(gross, opts, person, MONTH, TY)
    assert (float(sv.rv), float(sv.alv), float(sv.kv), float(sv.pv)) == pytest.approx(parts)


def family(*born: date, children: int = 0) -> Person:
    return Person(
        born=date(1985, 1, 1),
        children=children or len(born),
        children_born=[Child(born=b) for b in born],
    )


@pytest.mark.parametrize(
    ("person", "points"),
    [
        (family(date(2014, 3, 1)), 0.0),
        (family(date(2014, 3, 1), date(2018, 1, 1)), 0.25),
        (family(date(2014, 3, 1), date(2018, 1, 1), date(2020, 6, 1)), 0.5),
        (family(*(date(2010 + i, 1, 1) for i in range(6))), 1.0),  # up to the fifth child
        (family(date(2001, 1, 2), date(2018, 1, 1)), 0.25),  # 25 on 2026-01-01: counts
        (family(date(2001, 1, 1), date(2018, 1, 1)), 0.0),  # 25 on 2025-12-31: none
        (family(date(2000, 12, 1), date(2018, 1, 1)), 0.0),  # 25 in November 2025: none
        (family(date(2000, 12, 1), date(2018, 1, 1), date(2020, 6, 1)), 0.25),
        (family(date(2018, 1, 1), date(2027, 1, 1)), 0.0),  # not born yet
        (family(date(2018, 1, 1), children=3), 0.0),  # births unknown: no discount
    ],
)
def test_pv_discount_for_children_under_25(person: Person, points: float) -> None:
    """§55 Abs. 3 S. 4 SGB XI: 0.25 points less for each child from the second to the fifth, up
    to the end of the month in which it completes its 25th year, a child born on the first in
    the month before its birthday (§187 Abs. 2 S. 2, §188 Abs. 2 BGB); a child of 25 does not
    count. The member bears it alone: the employee share and the whole rate on a pension both
    fall by it (TK, Beiträge in der Pflegeversicherung, 2026)."""
    base = TY.kv_pv_bbg_month
    salary = sv_employee(6000.0, OPTS_GKV, person, MONTH, TY).pv
    assert salary == pytest.approx(base * (0.018 - points / 100))
    pension = pension_net_month(2000.0, OPTS_GKV, person, MONTH, TY, premium_month=0.0).pv
    assert pension == pytest.approx(2000.0 * (0.036 - points / 100))


def test_a_one_off_payment_uses_the_yearly_bbg() -> None:
    """June, five months of 8,000 before: the yearly RV BBG of six months (50,700) leaves 2,700
    for a bonus. A salary above the BBG leaves nothing, the KV BBG neither."""
    rv, kv = sv_bases(8000.0, 10_000.0, 6, (40_000.0, 5 * 5812.5), TY)
    assert (float(rv), float(kv)) == pytest.approx((10_700.0, 5812.5))
    rv, _ = sv_bases(9000.0, 5000.0, 6, (5 * 8450.0, 0.0), TY)
    assert float(rv) == pytest.approx(8450.0)


@pytest.mark.parametrize(
    ("premium", "pflege", "base", "kv", "pv"),
    [
        (2000.0, 400.0, 5812.5, 508.59, 104.63),  # the published maxima of 2026 at the BBG
        (1000.0, 200.0, 4000.0, 350.0, 72.0),  # 8.75% and 1.8% of a salary below the BBG
        (960.40, 64.20, 5812.5, 448.10, 32.10),  # half of each part of the premium
        (1000.0, 200.0, 0.0, 0.0, 0.0),  # no salary
    ],
)
def test_employer_pkv_subsidy_follows_the_salary_up_to_half_the_premium(
    premium: float, pflege: float, base: float, kv: float, pv: float
) -> None:
    """§257 Abs. 2 S. 2 SGB V, §61 Abs. 2 S. 2 SGB XI."""
    subsidy = employer_pkv_subsidy(premium, pflege, base, TY)
    assert subsidy == pytest.approx(kv + pv, abs=0.01)


def test_pkv_subsidy_agentur_cap() -> None:
    assert agentur_pkv_subsidy(1400.0, 0.0, TY) == pytest.approx(813.75)
    assert agentur_pkv_subsidy(500.0, 0.0, TY) == pytest.approx(500.0)
    # KV 880.00 hits its cap, the Pflegepflicht part of 64.20 is paid in full
    assert agentur_pkv_subsidy(944.20, 64.20, TY) == pytest.approx(813.75 + 64.20)
    assert agentur_pkv_subsidy(1200.0, 200.0, TY) == pytest.approx(813.75 + 167.40)


@pytest.mark.parametrize("year", TAX_YEARS)
def test_pkv_caps_follow_the_rates(year: int) -> None:
    """The published caps are rounded: a new Zusatzbeitrag must change them too."""
    ty = for_year(year)
    bbg = ty.kv_pv_bbg_month
    assert ty.pkv_agentur.cap_kv == pytest.approx(0.8 * bbg * 2 * ty.kv_half, abs=0.01)
    assert ty.pkv_agentur.cap_pv == pytest.approx(0.8 * bbg * ty.pv_rente_rate, abs=0.01)


@pytest.mark.parametrize(
    ("opts", "person", "premium", "parts"),
    [
        (OPTS_PKV, PERSON, 500.0, (0.0, 0.0, 175.0)),
        (OPTS_PKV, PERSON, 300.0, (0.0, 0.0, 150.0)),  # at most half of the premium
        (OPTS_GKV, PERSON, 0.0, (2000.0 * (0.073 + 0.0145), 2000.0 * (0.036 + 0.006), 0.0)),
        (OPTS_GKV, PERSON_KIDS, 0.0, (2000.0 * (0.073 + 0.0145), 2000.0 * 0.036, 0.0)),
    ],
    ids=["pkv", "pkv capped", "gkv childless", "gkv with a child"],
)
def test_pension_net_month(
    opts: TaxOptions, person: Person, premium: float, parts: tuple[float, float, float]
) -> None:
    """The KVdR and the PV of a GKV member (§247, §249a SGB V), or the PKV subsidy of the DRV
    (§106 Abs. 3 SGB VI): half of 14.6% plus the average Zusatzbeitrag of 2.9% in 2026, 8.75%
    (DRV, Rentner und ihre Krankenversicherung, 21. Auflage 2/2026, p. 27)."""
    month = pension_net_month(2000.0, opts, person, MONTH, TY, premium_month=premium)
    assert (float(month.kvdr), float(month.pv), float(month.pkv_subsidy)) == pytest.approx(parts)


@pytest.mark.parametrize("zusatz", [0.0, 0.025, 0.04])
def test_the_own_zusatzbeitrag_reaches_the_member_and_not_the_subsidies(zusatz: float) -> None:
    """Half of it on a salary and on the pension (§249, §249a SGB V), all of it on a profit and on
    a company pension (§242, §250); the PKV subsidy of the DRV takes the average (§106 Abs. 3
    SGB VI)."""
    own, average = TaxOptions(pkv=False, kv_zusatz=zusatz), OPTS_GKV
    gap = zusatz - 2 * TY.kv_zusatz_half
    salary = sv_employee(5000.0, own, PERSON, MONTH, TY).kv
    assert float(salary - sv_employee(5000.0, average, PERSON, MONTH, TY).kv) == (
        pytest.approx(5000.0 * gap / 2)
    )
    pension = pension_net_month(2000.0, own, PERSON, MONTH, TY, premium_month=0.0).kvdr
    assert float(
        pension - pension_net_month(2000.0, average, PERSON, MONTH, TY, premium_month=0.0).kvdr
    ) == (pytest.approx(2000.0 * gap / 2))
    profit, plain = (
        kv_voluntary((0.0, 0.0, 4000.0), o, PERSON, MONTH, TY)[0] for o in (own, average)
    )
    assert float(profit - plain) == pytest.approx(4000.0 * gap)
    company, plain = (
        kv_compulsory((1000.0, 0.0), o, PERSON, MONTH, TY, room=5812.5)[0] for o in (own, average)
    )
    assert float(company - plain) == pytest.approx((1000.0 - TY.versorgung_freibetrag) * gap)
    subsidy = [
        pension_net_month(2000.0, o, PERSON, MONTH, TY, premium_month=900.0).pkv_subsidy
        for o in (own.model_copy(update={"pkv": True}), OPTS_PKV)
    ]
    assert subsidy[0] == subsidy[1] == pytest.approx(2000.0 * TY.kv_half)


def _own(rv: Literal["none", "regular", "income"]) -> TaxOptions:
    return TaxOptions(self_employed=SelfEmployed(rv=rv))


@pytest.mark.parametrize(("month", "rv"), [(date(2029, 12, 1), 367.82), (date(2030, 1, 1), 735.63)])
def test_rv_self_employed_pays_half_the_regelbeitrag_in_the_founding_years(
    month: date, rv: float
) -> None:
    """§165 Abs. 1 SGB VI on the Bezugsgröße of 2026 (VGSD), founded in 2026: half up to the
    end of 2029, whatever the profit."""
    paid = rv_self_employed(9000.0, _own("regular"), month, TY, founded=MONTH)
    assert float(paid) == pytest.approx(rv, abs=0.01)


@pytest.mark.parametrize(("profit", "base"), [(100.0, 603.0), (5000.0, 5000.0), (9000.0, 8450.0)])
def test_rv_self_employed_on_the_income_between_the_geringfuegigkeitsgrenze_and_the_bbg(
    profit: float, base: float
) -> None:
    paid = rv_self_employed(profit, _own("income"), MONTH, TY, founded=MONTH)
    assert float(paid) == pytest.approx(TY.rv_rate_total * base)


def test_pension_points_capped_by_bbg() -> None:
    a_year = pension_points(TY.durchschnittsentgelt / 12, TY) * 12
    assert a_year == pytest.approx(1.0)
    assert pension_points(20000.0, TY) == pytest.approx(pension_points(TY.sv_bbg_month, TY))


def test_voluntary_points() -> None:
    a_year = voluntary_points(TY.rv_rate_total * TY.durchschnittsentgelt / 12, TY) * 12
    assert a_year == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("age", "years", "factor"),
    [
        (62.0, 40.0, None),  # too young
        (62.99, 40.0, None),  # just short of 63
        (63.0, 34.99, None),  # just short of 35 years
        (63.0, 30.0, None),  # too few years
        (63.0, 35.0, 1 - 0.144),
        (64.0, 45.0, 1 - 0.108),  # 45 years still take the Abschlag before 65
        (65.0, 35.0, 1 - 0.072),
        (65.0, 45.0, 1.0),
        (66.99, 45.0, 1.0),
        (67.0, 20.0, 1.0),
        (67.0, 45.0, 1.0),
        (68.0, 20.0, 1.06),
    ],
)
def test_pension_claim_rules(age: float, years: float, factor: float | None) -> None:
    result = pension_claim(age, years, TY)
    assert result == (pytest.approx(factor) if factor is not None else None)


@pytest.mark.parametrize(
    ("age", "months"),
    [(30, 12), (49, 12), (50, 15), (54, 15), (55, 18), (57, 18), (58, 24), (65, 24)],
)
def test_alg1_months(age: int, months: int) -> None:
    assert alg1_months(age, TY) == months


@pytest.mark.parametrize(
    ("gross", "child", "paid"),
    [
        (2000.0, False, 895.20),
        (3000.0, False, 1246.80),
        (5000.0, False, 1902.60),
        (7000.0, False, 2468.40),
        (8450.0, False, 2810.10),
        (12000.0, False, 2810.10),
        (8450.0, True, 3138.00),
    ],
)
def test_alg1_month_matches_the_bundesagentur(gross: float, child: bool, paid: float) -> None:
    """The Selbstberechnungsprogramm of the Bundesagentur for 2026 (pub.arbeitsagentur.de,
    Steuerklasse I/IV, queried on 2026-10-12): 30 days of ALG1, which it rounds per day. Above
    the BBG of 8,450 the salary counts as the BBG."""
    assert float(alg1_month(gross, TY, child=child)) == pytest.approx(paid, abs=1.0)


@pytest.mark.parametrize(("age", "factor"), [(50.0, 0.892), (61.0, 0.892), (64.0, 0.964), (66, 1)])
def test_the_em_rente_loses_0_3_percent_a_month_before_65_counted_from_62(
    age: float, factor: float
) -> None:
    """§77 Abs. 2 S. 1 Nr. 3, S. 2 SGB VI: at most 36 months, 10.8%."""
    assert float(em_factor(age, TY)) == pytest.approx(factor)


@pytest.mark.parametrize(
    ("gross", "paid"),
    [
        (12_000.0, 4068.75),  # 70% of the KV-BBG of 5,812.50: the net cap lies above it
        (5812.50, 3188.88),  # 90% of the net of the BBG salary binds
        (3000.0, 1851.15),  # and of a lower one
    ],
)
def test_krankengeld_takes_70_percent_up_to_the_bbg_at_most_90_percent_of_the_net(
    gross: float, paid: float
) -> None:
    """§47 Abs. 1, 6 SGB V for a childless employee in Steuerklasse I: less 13.0% for the shares
    of RV, ALV and PV (§170 SGB VI, §347 SGB III, §59 SGB XI: 9.3, 1.3 and 2.4 with the surcharge
    for the childless), 12.4% with a child. The shares fall on the Krankengeld paid ("soweit sie
    auf die Leistung entfallen"), not on the 80% of the gross that the Kasse pays on: at 3,000 the
    RV share is 172, not 223 (Finanztip, Krankengeld, the example of 3,000)."""
    sick = krankengeld_month(gross, OPTS_GKV, PERSON, MONTH, TY, church=0.0, employed=True)
    assert float(sick.gross) == pytest.approx(paid, abs=0.01)
    assert float(sick.rv + sick.alv + sick.pv) == pytest.approx(0.130 * paid)
    parent = krankengeld_month(gross, OPTS_GKV, PERSON_KIDS, MONTH, TY, church=0.0, employed=True)
    assert float((parent.rv + parent.alv + parent.pv) / parent.gross) == pytest.approx(0.124)


def test_krankengeld_of_a_business_takes_no_net_cap_and_only_its_rv() -> None:
    """§47 Abs. 4 SGB V: the Arbeitseinkommen up to the BBG; RV only after RV-Pflicht."""
    none = TaxOptions(pkv=False, self_employed=SelfEmployed(rv="none", krankengeld=True))
    income = TaxOptions(pkv=False, self_employed=SelfEmployed(rv="income", krankengeld=True))
    alone = krankengeld_month(9000.0, none, PERSON, MONTH, TY, church=0.0, employed=False)
    insured = krankengeld_month(9000.0, income, PERSON, MONTH, TY, church=0.0, employed=False)
    assert float(alone.gross) == pytest.approx(4068.75)
    assert float(alone.rv + alone.alv + alone.pv) == 0.0
    assert float(insured.rv + insured.alv + insured.pv) == pytest.approx(4068.75 * TY.rv_rate)
