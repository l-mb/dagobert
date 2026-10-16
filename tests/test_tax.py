"""The tax functions: tariffs, Vorabpauschale, Fünftelregelung and the year files."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from dagobert.model.assumptions import Person
from dagobert.model.taxes import Land, Relation, TaxOptions
from dagobert.sv import (
    agentur_pkv_subsidy,
    alg1_month,
    employer_pkv_subsidy,
    pension_net_month,
    pension_points,
    sv_employee,
    voluntary_points,
)
from dagobert.tax import (
    ChildYear,
    YearIncome,
    av_deduction,
    av_zulage,
    capital_gains_tax,
    carryback,
    church_rate,
    entlastungsbetrag,
    erbschaftsteuer,
    ertragsanteil,
    flat_rate,
    for_year,
    fuenftelregelung,
    guenstigerpruefung,
    harvest_room,
    haushalt_credit,
    health_deductible,
    income_tax,
    pension_share,
    private_sales,
    profit_reserve,
    rv_deductible,
    soli,
    sonderausgaben,
    taxable_income,
    trade_tax,
    vorabpauschale,
    werbungskosten,
    withholding_with_bonus,
    year_settlement,
    year_tax,
)
from dagobert.tax import zve as zve_of

PERSON = Person(born=date(1985, 1, 1))
MONTH = date(2026, 1, 1)
OPTS_PKV = TaxOptions(pkv=True)
OPTS_GKV = TaxOptions(pkv=False)
TY = for_year(2026)


CROSSOVER = 20350.0 * 0.119 / (0.119 - 0.055)  # Soli: the Milderungszone meets 5.5 %


@pytest.mark.parametrize(
    ("fn", "value", "expected"),
    [
        (soli, 20350.0, 0.0),
        (soli, 21000.0, 0.119 * (21000.0 - 20350.0)),
        (soli, CROSSOVER - 1000.0, 0.119 * (CROSSOVER - 1000.0 - 20350.0)),
        (soli, CROSSOVER + 1000.0, 0.055 * (CROSSOVER + 1000.0)),
        (soli, 100000.0, 5500.0),
        (pension_share, 2023, 0.825),
        (pension_share, 2026, 0.84),
        (pension_share, 2045, 0.935),
        (pension_share, 2059, 1.0),
    ],
)
def test_tariffs(fn: Callable[..., Any], value: float, expected: float) -> None:
    """The Soli Freigrenze and Milderungszone, the taxable share of a pension."""
    assert float(fn(value, TY)) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("growth", "expected"),
    [(0.10, 100000.0 * 0.032 * 0.7), (0.005, 500.0), (-0.10, 0.0)],
)
def test_vorabpauschale_is_the_basisertrag_at_most_the_gain(growth: float, expected: float) -> None:
    assert float(vorabpauschale(100000.0, growth, TY)) == pytest.approx(expected)


FIFTHS = [
    (40000.0, 30000.0, 17019.0),  # by hand: the tax of a fifth more, five times
    *((zve, 0.0, float(income_tax(zve, TY))) for zve in (0.0, 15000.0, 40000.0, 300000.0)),
    # §34 Abs. 1 S. 3: a loss spreads over all five fifths, not against one of them
    (-5000.0, 20000.0, 5 * float(income_tax(3000.0, TY))),
    (-1230.0, 100000.0, 5 * float(income_tax(98770.0 / 5, TY))),
    (-5000.0, 3000.0, 0.0),  # below zero in all
]


@pytest.mark.parametrize(("zve", "severance", "expected"), FIFTHS)
def test_fuenftelregelung(zve: float, severance: float, expected: float) -> None:
    """§34 Abs. 1 EStG: the tax of the year with a fifth of the severance less without it, five
    times."""
    assert float(fuenftelregelung(zve, severance, TY)) == pytest.approx(expected)


def test_fuenftelregelung_per_path() -> None:
    zve, severance, expected = (np.array(column) for column in zip(*FIFTHS, strict=True))
    assert np.allclose(fuenftelregelung(zve, severance, TY), expected)


def test_guenstigerpruefung_refunds_flat_tax_below_grundfreibetrag() -> None:
    paid = 10000.0 * 0.26375
    assert guenstigerpruefung(0.0, income_tax(10000.0, TY), paid, TY, church=0.0) == pytest.approx(
        paid
    )
    # high earner: tariff rate above the flat rate, nothing back
    assert (
        guenstigerpruefung(income_tax(200000.0, TY), income_tax(210000.0, TY), paid, TY, church=0.0)
        == 0.0
    )
    settled = year_settlement(
        YearIncome(capital_income=10000.0, capital_tax_paid=paid), TY, church=0.0
    )
    assert (settled.total, settled.refund) == pytest.approx((0.0, paid))


def test_guenstigerpruefung_partial_refund_in_the_middle_zone() -> None:
    zve, capital = 10000.0, 10000.0
    paid = capital * 0.26375
    tax = income_tax(zve, TY)
    refund = guenstigerpruefung(tax, income_tax(zve + capital, TY), paid, TY, church=0.0)
    tariff = income_tax(zve + capital, TY) - tax
    assert refund == pytest.approx(paid - tariff - (soli(tax + tariff, TY) - soli(tax, TY)))
    assert 0.0 < float(refund) < paid


def test_guenstigerpruefung_sees_the_progressionsvorbehalt() -> None:
    """§32d Abs. 6: capital income joins the zvE, so ALG1 sets its rate as well."""
    alg1, capital = 35000.0, 10000.0
    paid = capital * 0.26375
    settled = year_settlement(
        YearIncome(alg1=alg1, capital_income=capital, capital_tax_paid=paid), TY, church=0.0
    )
    # without a salary ALG1 counts less the Pauschbetrag (§32b Abs. 2 S. 1 Nr. 1), and the zvE
    # is the capital income less the Sonderausgaben-Pauschbetrag
    zve, rated = capital - TY.sonderausgaben_pauschbetrag, alg1 - TY.werbungskosten_pauschale
    rate = float(income_tax(zve + rated, TY)) / (zve + rated)
    assert settled.refund == pytest.approx(paid - rate * zve)
    assert 0.0 < float(settled.refund) < 0.3 * paid


def test_guenstigerpruefung_takes_the_route_of_the_altersvorsorgedepot() -> None:
    """§10a Abs. 2 EStG: where the deduction saves more than the Zulage, the tariff with the
    capital income takes it too, so the refund is that of an income lower by the deduction."""
    capital, zulage = 3000.0, float(av_zulage(1800.0, 0, TY))
    deduction = float(av_deduction(1800.0, zulage, TY))
    income = YearIncome(
        salary_gross=24000.0, capital_income=capital, capital_tax_paid=capital * 0.26375
    )
    depot = year_settlement(
        replace(income, av_deduction=deduction, av_zulage=zulage), TY, church=0.0
    )
    lower = year_settlement(replace(income, other_taxable=-deduction), TY, church=0.0)
    assert float(depot.tax - lower.tax) == pytest.approx(zulage)  # the deduction applies
    assert float(depot.refund) == pytest.approx(float(lower.refund))
    assert float(depot.refund) > 0.0


def test_guenstigerpruefung_sees_the_severance() -> None:
    paid = 10000.0 * 0.26375
    income = YearIncome(severance=500000.0, capital_income=10000.0, capital_tax_paid=paid)
    assert year_settlement(income, TY, church=0.0).refund == 0.0


@pytest.mark.parametrize(
    ("income", "zve", "left"),
    [
        # before the Sonderausgaben: 8,000 € of income use 5,000 € of the losses, though the
        # Sonderausgaben alone would leave no zvE
        (YearIncome(other_taxable=8000.0, health_deductible=8000.0), -5000.0, 0.0),
        # a negative Gesamtbetrag der Einkünfte joins the losses
        (YearIncome(other_taxable=-6000.0), -6000.0, 11000.0),
        # a severance takes the losses after the regular income, the rest of the zvE below zero
        # joins the fifth (§34 Abs. 1 S. 3)
        (YearIncome(other_taxable=2000.0, severance=10000.0), 2000.0 - 5000.0 - 1230.0, 0.0),
    ],
    ids=["sonderausgaben", "loss", "severance"],
)
def test_the_losses_carried_offset_the_income_before_the_sonderausgaben(
    income: YearIncome, zve: float, left: float
) -> None:
    """§10d Abs. 2 EStG, §2 Abs. 3, 4: 5,000 € carried from earlier years."""
    settled = year_settlement(replace(income, loss_carried=5000.0), TY, church=0.0)
    expected = fuenftelregelung(zve, income.severance, TY)
    assert (settled.tax, settled.loss_left) == pytest.approx((expected, left))


def test_sonderausgaben_alone_carry_no_loss() -> None:
    """§10d Abs. 1 S. 1: a negative Gesamtbetrag der Einkünfte carries, not a negative zvE."""
    settled = year_settlement(
        YearIncome(other_taxable=5000.0, health_deductible=8000.0), TY, church=0.0
    )
    assert settled.loss_left == 0.0


@pytest.mark.parametrize(
    ("capital", "refund", "left"),
    [(4000.0, True, 6000.0), (200_000.0, False, 10000.0)],
    ids=["refund", "flat tax"],
)
def test_the_guenstigerpruefung_takes_the_losses_against_the_capital_income(
    capital: float, *, refund: bool, left: float
) -> None:
    """§32d Abs. 6 S. 1 EStG: on application the capital income joins the Einkünfte, so a loss of
    the year shelters it first and carries the rest; the flat tax leaves the loss whole."""
    paid = capital * 0.26375
    settled = year_settlement(
        YearIncome(other_taxable=-10000.0, capital_income=capital, capital_tax_paid=paid),
        TY,
        church=0.0,
    )
    assert (float(settled.refund) > 0) == refund
    assert settled.loss_left == settled.loss == pytest.approx(left)


@pytest.mark.parametrize(
    "income",
    [
        YearIncome(other_taxable=8000.0, health_deductible=8000.0),
        YearIncome(other_taxable=2000.0, severance=10000.0),
    ],
    ids=["sonderausgaben", "severance"],
)
def test_a_loss_carried_back_comes_off_as_one_carried_forward(income: YearIncome) -> None:
    """§10d Abs. 1 S. 1 EStG: a loss of a later year comes off the Gesamtbetrag der Einkünfte
    before the Sonderausgaben, the regular income first, so beyond it the zvE below zero joins the
    fifth of a severance (R 34.1 Abs. 1 S. 3 EStR, §34 Abs. 1 S. 3), as the losses carried
    forward do, and carries nothing on. Its room is what the losses carried forward leave."""
    back = year_settlement(replace(income, loss_back=5000.0), TY, church=0.0)
    forward = year_settlement(replace(income, loss_carried=5000.0), TY, church=0.0)
    assert (back.tax, back.loss_left) == pytest.approx((forward.tax, 0.0))
    gde = zve_of(income, TY).room
    both = replace(income, loss_carried=3000.0, loss_back=1000.0)
    assert zve_of(both, TY).room == pytest.approx(gde - 4000.0)


@pytest.mark.parametrize(
    ("capital", "room", "refunded"),
    [(15_000.0, 20_000.0, 15_000.0 * 0.26375), (200_000.0, 5000.0, 0.0)],
    ids=["refund", "flat tax"],
)
def test_a_loss_goes_back_into_the_capital_income_that_the_tariff_taxed(
    capital: float, room: float, refunded: float
) -> None:
    """§10d Abs. 1 S. 1 with §32d Abs. 6 S. 1 EStG: where the Günstigerprüfung of a year refunds,
    its capital income joins the Gesamtbetrag der Einkünfte that a later loss takes back, and a
    loss of all of it refunds the whole flat tax; under the flat tax the regular income alone."""
    income = YearIncome(
        other_taxable=5000.0, capital_income=capital, capital_tax_paid=capital * 0.26375
    )
    assert year_settlement(income, TY, church=0.0).room == pytest.approx(room)
    again = year_settlement(replace(income, loss_back=room), TY, church=0.0)
    assert (again.total, again.refund) == pytest.approx((0.0, refunded))


@pytest.mark.parametrize(
    ("loss", "rooms", "taken"),
    [
        (5000.0, [3000.0, 10_000.0], [3000.0, 2000.0]),  # the year before first
        (5000.0, [0.0, 0.0], [0.0, 0.0]),  # no room: all of it carries forward
        (1_500_000.0, [300_000.0, 2_000_000.0], [300_000.0, 700_000.0]),  # 1 Mio. € in all
        (5000.0, [], []),  # the first year of a run
    ],
    ids=["two years", "no room", "limit", "first year"],
)
def test_a_loss_goes_back_one_year_then_two_up_to_its_limit(
    loss: float, rooms: list[float], taken: list[float]
) -> None:
    """§10d Abs. 1 S. 1, 2 EStG: into the year before, the rest into the second year before, at
    most 1,000,000 € of a single person."""
    assert [float(t) for t in carryback(loss, rooms, TY)] == pytest.approx(taken)


@pytest.mark.parametrize(
    ("income", "losses", "room"),
    [
        (YearIncome(), 0.0, 13_384.0),
        (YearIncome(), 2000.0, 0.0),
        (YearIncome(alg1=12_348.0), 0.0, 2266.0),
        (YearIncome(capital_income=2000.0), 0.0, 11_384.0),
        (YearIncome(health_deductible=3000.0), 0.0, 16_384.0),
        (YearIncome(other_taxable=5000.0, loss_carried=500.0), 0.0, 8884.0),
        (YearIncome(other_taxable=-3000.0), 0.0, 1000.0),
        (YearIncome(loss_carried=500.0), 0.0, 1000.0),
        (YearIncome(severance=10_000.0), 0.0, 1000.0),
    ],
    ids=[
        "zve 0",
        "loss pot",
        "alg1",
        "capital income",
        "negative zve",
        "pot used up",
        "negative gde",
        "pot left",
        "severance",
    ],
)
def test_the_harvest_room_ends_at_the_grundfreibetrag(
    income: YearIncome, losses: float, room: float
) -> None:
    """The Sparer-Pauschbetrag left of 1,000 € (§20 Abs. 9 EStG) and, at a zvE of 0 less the
    Sonderausgaben-Pauschbetrag of 36 € (§10c), the Grundfreibetrag of 12,348 € (§32a Abs. 1), less
    what ALG1 (§32b, less the Arbeitnehmer-Pauschbetrag that no Arbeitslohn takes, Abs. 2 S. 1
    Nr. 1) and the capital income of the year take. A negative zvE from the Sonderausgaben carries
    nothing and widens it; a
    Verlustvortrag left (§10d), also from a negative Gesamtbetrag, and a Fünftelregelung (§34)
    close the tariff part, a loss pot (§20 Abs. 6) all of it."""
    assert harvest_room(income, 1000.0, losses, TY) == pytest.approx(room)


GAINS = [
    (1400.0, 1000.0, 105.5, 0.0),  # less the Pauschbetrag
    (500.0, 1000.0, 0.0, 500.0),  # within the Pauschbetrag
    (-500.0, 1000.0, 0.0, 1000.0),  # a loss leaves it
    (5000.0, 0.0, 5000.0 * 0.26375, 0.0),
    (0.0, 400.0, 0.0, 400.0),
]


@pytest.mark.parametrize(("gain", "left", "tax", "rest"), GAINS)
def test_capital_gains_tax_after_the_pauschbetrag(
    gain: float, left: float, tax: float, rest: float
) -> None:
    taxed, after, _ = capital_gains_tax(gain, left, OPTS_PKV, TY, losses=0.0)
    assert (float(taxed), float(after)) == pytest.approx((tax, rest))


def test_capital_gains_tax_per_path() -> None:
    gain, left, tax, rest = (np.array(column) for column in zip(*GAINS, strict=True))
    taxed, after, _ = capital_gains_tax(gain, left, OPTS_PKV, TY, losses=0.0)
    assert np.allclose(taxed, tax)
    assert np.allclose(after, rest)


def test_a_loss_goes_into_the_pot_and_offsets_later_income() -> None:
    tax, left, pot = capital_gains_tax(-350.0, 1000.0, OPTS_PKV, TY, losses=0.0)
    assert [float(tax), float(left), float(pot)] == pytest.approx([0.0, 1000.0, 350.0])
    tax, left, pot = capital_gains_tax(1000.0, 0.0, OPTS_PKV, TY, losses=pot)
    assert (float(tax), float(pot)) == pytest.approx((650.0 * 0.26375, 0.0))
    tax, left, pot = capital_gains_tax(100.0, 500.0, OPTS_PKV, TY, losses=300.0)
    assert [float(tax), float(left), float(pot)] == pytest.approx([0.0, 500.0, 200.0])


PRIVATE_SALES = [
    (999.99, 0.0, 0.0, 0.0),  # below the Freigrenze: free
    (1000.0, 0.0, 1000.0, 0.0),  # at the Freigrenze: taxable in full
    (900.0, 500.0, 0.0, 500.0),  # free, so the carried loss stays unused
    (1500.0, 1000.0, 500.0, 0.0),  # the rest below the Freigrenze stays taxable
    (1500.0, 3000.0, 0.0, 1500.0),
    (-300.0, 500.0, 0.0, 800.0),  # a net loss joins the carried losses
]


@pytest.mark.parametrize(("net", "carried", "taxable", "left"), PRIVATE_SALES)
def test_private_sales_freigrenze_and_carried_losses(
    net: float, carried: float, taxable: float, left: float
) -> None:
    """§23 Abs. 3 S. 5, 7 and 8 EStG: the Freigrenze of 1,000 on the net of the year, checked
    before the carried losses offset (BMF 2004-10-25 Tz. 52, BFH IX R 27/04)."""
    assert [float(v) for v in private_sales(net, carried, TY)] == pytest.approx([taxable, left])


def test_private_sales_per_path() -> None:
    net, carried, taxable, left = (np.array(column) for column in zip(*PRIVATE_SALES, strict=True))
    assert np.allclose(private_sales(net, carried, TY), [taxable, left])


def test_the_withholding_takes_the_pkv_premium_and_settles_the_year() -> None:
    """The Lohnsteuer of a regular salary as if paid all year, the deductible PKV premium as its
    Vorsorgepauschale (§39b Abs. 2 S. 5 Nr. 3 EStG): the December settlement adds nothing."""
    gross, deductible = 9000.0, 0.8 * 960.40
    sv = sv_employee(gross, OPTS_PKV, PERSON, MONTH, TY)
    withheld = withholding_with_bonus(gross, 0.0, (sv, sv), deductible, TY, church=0.0)
    zve = taxable_income(gross * 12 - 36.0, 1230.0, sv.rv * 12, deductible * 12)
    assert float(withheld) == pytest.approx(float(year_tax(zve, TY, church=0.0)) / 12)
    settled = year_settlement(
        YearIncome(salary_gross=gross * 12, rv_paid=sv.rv * 12, health_deductible=deductible * 12),
        TY,
        church=0.0,
    )
    assert float(settled.total) == pytest.approx(12 * float(withheld), abs=1.0)


@pytest.mark.parametrize(
    ("salary", "yearly", "dated", "deducted"),
    [
        (5000.0, 20_000.0, 0.0, 5000.0),  # the yearly costs stop at the Arbeitslohn
        (5000.0, 20_000.0, 3000.0, 8000.0),  # dated ones count on top, beyond it
        (0.0, 9000.0, 3000.0, 3000.0),  # without a salary only the dated ones
        (50_000.0, 0.0, 500.0, 1230.0),  # below the Pauschbetrag: the Pauschbetrag
        (50_000.0, 1000.0, 500.0, 1500.0),
    ],
)
def test_dated_work_expenses_count_in_full(
    salary: float, yearly: float, dated: float, deducted: float
) -> None:
    """§9 EStG: the work expenses of a year at a date (a course, applications, vorweggenommene
    Werbungskosten) count without the cap at the Arbeitslohn that the yearly costs keep (§9a S.
    2), so they can make a loss (§2 Abs. 3)."""
    assert werbungskosten(salary, 0.0, TY, yearly, dated) == pytest.approx(deducted)


@pytest.mark.parametrize(
    ("salary", "dated", "rated"),
    [
        (0.0, 0.0, 10_000.0 - 1230.0),
        (500.0, 0.0, 10_000.0 - 730.0),  # the part of the Pauschbetrag that the salary leaves
        (0.0, 2000.0, 10_000.0),  # costs above the Pauschbetrag: none (BFH III R 61/12)
        (0.0, 500.0, 10_000.0 - 730.0),  # costs below it: the rest of it
        (0.0, 1229.0, 10_000.0 - 1.0),  # no jump at the Pauschbetrag (Rz. 17)
        (0.0, 1231.0, 10_000.0),
        (500.0, 300.0, 10_000.0 - 730.0),  # the Pauschbetrag came off
    ],
)
def test_alg1_rates_less_the_pauschbetrag_that_the_work_expenses_leave(
    salary: float, dated: float, rated: float
) -> None:
    """§32b Abs. 2 S. 1 Nr. 1 EStG: ALG1 raises the rate less the Arbeitnehmer-Pauschbetrag as far
    as the Arbeitslohn does not take it; not at all when higher costs came off (BFH III R 61/12 of
    2014-09-25), also dated costs in a year without a salary. Below it the costs and the
    Pauschbetrag never relieve both (Rz. 15), so the relief does not jump at it."""
    income = YearIncome(alg1=10_000.0, salary_gross=salary, work=dated)
    assert zve_of(income, TY).alg1 == pytest.approx(rated)


def test_werbungskosten_splits_salary_and_pension_per_9a() -> None:
    assert werbungskosten(50000.0, 0.0, TY, 0.0) == pytest.approx(1230.0)
    assert werbungskosten(500.0, 0.0, TY, 0.0) == pytest.approx(500.0)  # capped at the income
    assert werbungskosten(0.0, 30000.0, TY, 0.0) == pytest.approx(102.0)
    assert werbungskosten(50000.0, 30000.0, TY, 0.0) == pytest.approx(1332.0)
    assert werbungskosten(0.0, 0.0, TY, 0.0) == pytest.approx(0.0)
    # the own costs when higher than the Pauschbetrag, at most the Arbeitslohn; never the pension
    assert werbungskosten(50000.0, 30000.0, TY, 3000.0) == pytest.approx(3102.0)
    assert werbungskosten(50000.0, 0.0, TY, 1000.0) == pytest.approx(1230.0)
    assert werbungskosten(2000.0, 0.0, TY, 3000.0) == pytest.approx(2000.0)


def test_taxable_income_may_go_negative() -> None:
    assert taxable_income(1000.0, 1000.0, 500.0, 800.0) == pytest.approx(-1300.0)


@pytest.mark.parametrize(
    ("income", "tax"),
    [
        # the Arbeitnehmer- and the Sonderausgaben-Pauschbetrag, 1,230 and 36 (§§9a, 10c)
        (YearIncome(salary_gross=41266.0), float(income_tax(40000.0, TY))),
        (YearIncome(other_taxable=40036.0), float(income_tax(40000.0, TY))),  # 36 only
        (
            YearIncome(pension_taxable=30000.0 * 0.935),
            float(income_tax(30000.0 * 0.935 - 102.0 - 36.0, TY)),
        ),
        # §32b EStG: the rate of the zvE with ALG1
        (YearIncome(salary_gross=31266.0, alg1=10000.0), float(income_tax(40000.0, TY)) * 0.75),
        (YearIncome(alg1=5000.0, rv_paid=1000.0), 0.0),  # a negative zvE
        (
            YearIncome(salary_gross=41266.0, severance=30000.0),
            float(fuenftelregelung(40000.0, 30000.0, TY)),
        ),
        # a year without salary: the Pauschbetrag makes the zvE negative, §34 Abs. 1 S. 3
        (YearIncome(severance=100000.0), 5 * float(income_tax((100000.0 - 1266.0) / 5, TY))),
    ],
    ids=["salary", "other", "pension", "alg1", "loss", "severance", "severance alone"],
)
def test_year_settlement_takes_the_tariff_of_the_zve(income: YearIncome, tax: float) -> None:
    settled = year_settlement(income, TY, church=0.0)
    assert float(settled.tax) == pytest.approx(tax)
    assert float(settled.total) == pytest.approx(tax + float(soli(tax, TY)))


def test_rv_deductible_caps_at_the_hoechstbetrag_less_the_employer_share() -> None:
    assert rv_deductible(9000.0, 9000.0, TY) == pytest.approx(9000.0)
    assert rv_deductible(30826.0 + 600.0, 0.0, TY) == pytest.approx(30826.0)
    assert rv_deductible(30000.0, 9000.0, TY) == pytest.approx(30826.0 - 9000.0)


def test_year_settlement_deducts_ruerup_only_up_to_the_cap() -> None:
    capped = year_settlement(YearIncome(severance=200000.0, rv_paid=40000.0), TY, church=0.0)
    exact = year_settlement(YearIncome(severance=200000.0, rv_paid=30826.0), TY, church=0.0)
    assert capped.tax == pytest.approx(exact.tax)


def test_year_settlement_is_vectorized() -> None:
    salary = np.array([41266.0, 0.0, 101266.0])
    settled = year_settlement(YearIncome(salary_gross=salary), TY, church=0.0)
    expected = np.array([float(income_tax(40000.0, TY)), 0.0, float(income_tax(100000.0, TY))])
    assert np.allclose(settled.tax, expected)


def test_for_year_knows_its_files() -> None:
    with pytest.raises(ValueError, match="no tax constants for 2045, only for 2026"):
        for_year(2045)


SV = sv_employee(6000.0, OPTS_PKV, PERSON, MONTH, TY)
CALLS: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = [
    (income_tax, (50000.0, TY), {}),
    (soli, (30000.0, TY), {}),
    (fuenftelregelung, (40000.0, 30000.0, TY), {}),
    (werbungskosten, (50000.0, 30000.0, TY, 2000.0), {}),
    (taxable_income, (50000.0, 1230.0, 5000.0, 3000.0), {}),
    (withholding_with_bonus, (6000.0, 500.0, (SV, SV), 700.0, TY), {"church": 0.09}),
    (employer_pkv_subsidy, (1000.0, 70.0, 5000.0, TY), {}),
    (agentur_pkv_subsidy, (1000.0, 70.0, TY), {}),
    (alg1_month, (6000.0, TY), {"child": False}),
    (pension_points, (6000.0, TY), {}),
    (voluntary_points, (600.0, TY), {}),
    (vorabpauschale, (100000.0, 0.10, TY), {}),
    (guenstigerpruefung, (10000.0, 11500.0, 1300.0, TY), {"church": 0.09}),
    (profit_reserve, (8000.0, 20000.0, 1500.0, TY), {"church": 0.09}),
    (erbschaftsteuer, (500000.0, [], [], Relation.PARENT, TY), {"inheritance": True}),
]
CALL_IDS = [fn.__name__ for fn, _, _ in CALLS]


@pytest.mark.parametrize(("fn", "args", "kwargs"), CALLS, ids=CALL_IDS)
def test_a_float_gives_an_array_and_an_array_one_value_per_path(
    fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    """The functions of `tax` and `sv` take floats or arrays and always return arrays."""
    scalar = fn(*args, **kwargs)
    assert isinstance(scalar, np.ndarray)
    broadcast = fn(*[np.full(3, a) if isinstance(a, float) else a for a in args], **kwargs)
    assert np.allclose(broadcast, np.full(3, scalar))


def test_composite_results_are_arrays_for_scalar_input() -> None:
    sv = sv_employee(6000.0, OPTS_GKV, PERSON, MONTH, TY)
    assert all(isinstance(v, np.ndarray) for v in (sv.rv, sv.alv, sv.kv, sv.pv, sv.total))
    pkv = sv_employee(6000.0, OPTS_PKV, PERSON, MONTH, TY)
    assert all(isinstance(v, np.ndarray) for v in (pkv.rv, pkv.alv, pkv.kv, pkv.pv))
    pension = pension_net_month(2000.0, OPTS_GKV, PERSON, MONTH, TY, premium_month=0.0)
    assert all(isinstance(v, np.ndarray) for v in (pension.kvdr, pension.pv))
    pkv_pension = pension_net_month(2000.0, OPTS_PKV, PERSON, MONTH, TY, premium_month=500.0)
    assert isinstance(pkv_pension.pkv_subsidy, np.ndarray)
    assert all(
        isinstance(v, np.ndarray)
        for v in capital_gains_tax(2000.0, 1000.0, OPTS_PKV, TY, losses=0.0)
    )
    assert all(isinstance(v, np.ndarray) for v in private_sales(2000.0, 500.0, TY))
    settled = year_settlement(YearIncome(salary_gross=41230.0), TY, church=0.0)
    assert all(
        isinstance(v, np.ndarray)
        for v in (settled.tax, settled.soli, settled.trade_tax, settled.total)
    )


def test_health_deductible_takes_the_whole_subsidy_off_the_basis_part() -> None:
    """BFH IX R 43/13: 80% of 900 less 450, not 80% of what the person pays herself."""
    assert health_deductible(720.0, 450.0) == pytest.approx(720 - 450)
    assert health_deductible(720.0, 0.0) == pytest.approx(720.0)
    assert health_deductible(400.0, 813.75) == 0.0


@pytest.mark.parametrize(
    ("zve", "tax"),
    [
        (-5000.0, 0),  # a loss
        (12348.0, 0),  # Grundfreibetrag, zone 1/2 border
        (12349.0, 0),  # first Euro of zone 2
        (15000.0, 435),  # zone 2 interior
        (17799.0, 1034),  # zone 2 upper border
        (17800.0, 1035),  # first Euro of zone 3
        (40000.0, 7209),  # zone 3 interior
        (69878.0, 18213),  # zone 3 upper border
        (69879.0, 18213),  # first Euro of zone 4
        (100000.0, 30864),  # zone 4 interior
        (277825.0, 105550),  # zone 4 upper border
        (277826.0, 105551),  # first Euro of zone 5
        (300000.0, 115529),  # zone 5 interior
    ],
)
def test_income_tax_zone_borders_2026(zve: float, tax: int) -> None:
    """§32a Abs. 1 EStG 2026: hand-computed from the `TaxYear` coefficients and cross-checked
    against https://www.gesetze-im-internet.de/estg/__32a.html."""
    assert income_tax(zve, TY) == tax


@pytest.mark.parametrize(
    ("constant", "value"),
    [
        ("durchschnittsentgelt", 51944.0),  # provisional, Sozialversicherungs-Rechengrößen
        ("alg1_pauschal_abzug", 0.20),  # §153 Abs. 1 S. 2 Nr. 1 SGB III
        ("alg1_rv_share", 0.80),  # §166 Abs. 1 Nr. 2 SGB VI
        ("private_sale_months", 12),  # §23 Abs. 1 S. 1 Nr. 2 EStG: "nicht mehr als ein Jahr"
        ("kindergeld_month", 259.0),  # §66 Abs. 1 EStG
        ("kinderfreibetrag", 3414.0),  # §32 Abs. 6 S. 1 EStG, per parent
        ("betreuungsfreibetrag", 1464.0),
        ("entlastungsbetrag", 4260.0),  # §24b Abs. 2 EStG
        ("kez_points_month", 0.0833),  # §70 Abs. 2 S. 1 SGB VI
    ],
)
def test_the_year_file_holds_the_law_of_2026(constant: str, value: float) -> None:
    assert getattr(TY, constant) == pytest.approx(value)


def test_soli_honours_a_tax_year_override() -> None:
    assert soli(1000.0, TY) == 0.0
    assert soli(1000.0, TY.model_copy(update={"soli_freigrenze": 0.0})) == pytest.approx(55.0)


def test_pension_share_rejects_years_before_the_half_point_steps() -> None:
    with pytest.raises(ValueError, match="2005"):
        pension_share(2005, TY)


def test_progressionsvorbehalt_reaches_the_fuenftelregelung() -> None:
    """R 34.2 EStR: ALG1 sets the rate in both steps of §34 Abs. 1."""
    zve, severance, alg1 = 30000.0, 100000.0, 18000.0

    def at_rate(x: float) -> float:
        return float(income_tax(x + alg1, TY)) / (x + alg1) * x

    expected = at_rate(zve) + 5 * (at_rate(zve + severance / 5) - at_rate(zve))
    assert fuenftelregelung(zve, severance, TY, alg1=alg1) == pytest.approx(expected)
    settled = year_settlement(
        YearIncome(other_taxable=zve + 1266, severance=severance, alg1=alg1), TY, church=0.0
    )
    assert settled.tax == pytest.approx(expected)  # the Pauschbeträge, 1,230 and 36, come off
    assert expected > float(fuenftelregelung(zve, severance, TY))


def test_progressionsvorbehalt_with_a_negative_zve_joins_the_fifth() -> None:
    """BFH IX R 23/11: half a year of ALG1 beside a 400k severance costs about 7k."""
    zve, severance, alg1 = -8000.0, 400000.0, 12000.0
    fifth = (zve + severance) / 5
    expected = 5 * float(income_tax(fifth + alg1, TY)) / (fifth + alg1) * fifth
    assert fuenftelregelung(zve, severance, TY, alg1=alg1) == pytest.approx(expected)
    extra = expected - float(fuenftelregelung(zve, severance, TY))
    assert 4500 < extra < 11000


def test_av_zulage_and_deduction() -> None:
    assert av_zulage(1800.0, 0, TY) == pytest.approx(540.0)
    assert av_zulage(360.0, 0, TY) == pytest.approx(180.0)
    assert av_zulage(6000.0, 0, TY) == pytest.approx(540.0)
    assert av_zulage(100.0, 2, TY) == 0.0  # below the minimum contribution
    assert av_deduction(6000.0, 540.0, TY) == pytest.approx(2340.0)
    # the Kinderzulage of 2027: the contributions, at most 300 per child (§85 Abs. 1 S. 1)
    assert av_zulage(1800.0, 2, TY) == pytest.approx(540.0 + 2 * 300.0)
    assert av_zulage(200.0, 2, TY) == pytest.approx(100.0 + 2 * 200.0)


def test_av_deduction_applies_only_when_it_beats_the_zulage() -> None:
    high = YearIncome(salary_gross=90_000.0)
    with_av = replace(high, av_deduction=2340.0, av_zulage=540.0)
    saving = (
        year_settlement(high, TY, church=0.0).tax - year_settlement(with_av, TY, church=0.0).tax
    )
    assert 0 < saving < 2340 * 0.45 - 540
    low = YearIncome(salary_gross=10_000.0)
    assert (
        year_settlement(replace(low, av_deduction=2340.0, av_zulage=540.0), TY, church=0.0).tax
        == 0.0
    )


def test_the_trade_tax_credit_comes_off_the_income_tax_before_the_soli() -> None:
    """§35 EStG: four times the Messbetrag of 3,500 (3.5% of the profit beyond 24,500) comes off
    the tariff tax, so the Soli falls; the Gewerbesteuer at 410% is 14,350."""
    gewst, credit = trade_tax(124_500.0, 4.1, TY)
    assert (float(gewst), float(credit)) == pytest.approx((14_350.0, 14_000.0))
    plain = YearIncome(other_taxable=124_500.0)
    trade = replace(plain, trade_income=124_500.0, trade_tax=gewst, trade_credit=credit)
    without, settled = (
        year_settlement(plain, TY, church=0.0),
        year_settlement(trade, TY, church=0.0),
    )
    assert float(without.tax - settled.tax) == pytest.approx(14_000.0)
    assert float(settled.soli) < float(without.soli)
    assert float(settled.total) == pytest.approx(
        float(without.total) - 14_000.0 - float(without.soli - settled.soli) + 14_350.0
    )


def test_the_trade_tax_credit_is_at_most_the_tariff_tax_on_the_trade_income() -> None:
    """§35 Abs. 1 S. 2 EStG: a year of low tariff tax keeps the Gewerbesteuer it cannot offset."""
    year = YearIncome(other_taxable=60_000.0, rv_paid=30_000.0, health_deductible=15_000.0)
    gewst, credit = trade_tax(60_000.0, 4.0, TY)
    settled = year_settlement(
        replace(year, trade_income=60_000.0, trade_tax=gewst, trade_credit=credit), TY, church=0.0
    )
    assert float(settled.tax) == 0.0
    assert float(settled.total) == pytest.approx(float(gewst))


def test_the_reserve_of_a_profit_is_the_tax_of_its_year_without_werbungskosten() -> None:
    """A monthly profit as if earned all year, less the SV of the month, a yearly one on top of
    it; a loss reserves nothing."""
    monthly = float(profit_reserve(6000.0, 0.0, 1000.0, TY, church=0.0))
    assert 12 * monthly == pytest.approx(float(year_tax(60_000.0, TY, church=0.0)))
    lump = float(profit_reserve(6000.0, 24_000.0, 1000.0, TY, church=0.0)) - monthly
    assert lump == pytest.approx(
        float(year_tax(84_000.0, TY, church=0.0) - year_tax(60_000.0, TY, church=0.0))
    )
    assert float(profit_reserve(-500.0, 0.0, 400.0, TY, church=0.0)) == 0.0


@pytest.mark.parametrize(
    ("land", "rate", "flat"),
    [(Land.BY, 0.08, 0.27819), (Land.BW, 0.08, 0.27819), (Land.NW, 0.09, 0.27995)],
)
def test_church_tax_by_land_and_on_capital_income(land: Land, rate: float, flat: float) -> None:
    """8% of the income tax in BW and BY, 9% elsewhere. The Abgeltungsteuer falls to e / (4 + k)
    (§32d Abs. 1 S. 4 EStG), 24.51% and 24.45%, with Soli and church tax 27.82% and 27.99%."""
    church = church_rate(TaxOptions(church=True, land=land), TY)
    assert church == rate
    assert flat_rate(church, TY) / (1 + TY.soli_rate + church) == pytest.approx(1 / (4 + church))
    assert flat_rate(church, TY) == pytest.approx(flat, abs=5e-6)
    assert church_rate(TaxOptions(land=land), TY) == 0.0
    assert flat_rate(0.0, TY) == pytest.approx(0.26375)
    taxed, _, _ = capital_gains_tax(1000.0, 0.0, TaxOptions(church=True, land=land), TY, losses=0.0)
    assert float(taxed) == pytest.approx(1000.0 * flat_rate(church, TY))


def test_church_needs_a_land() -> None:
    with pytest.raises(ValidationError, match="church needs land"):
        TaxOptions(church=True)


def test_church_tax_is_a_share_of_the_income_tax_before_the_trade_tax_credit() -> None:
    """§51a Abs. 2 S. 3 EStG: its base leaves out the credit of §35, which the Soli takes. The
    withholding and the Vorauszahlungen take it on top of the tax too (§51a Abs. 4)."""
    gewst, credit = trade_tax(124_500.0, 4.1, TY)
    year = YearIncome(other_taxable=124_500.0, trade_income=124_500.0)
    year = replace(year, trade_tax=gewst, trade_credit=credit)
    plain, church = year_settlement(year, TY, church=0.0), year_settlement(year, TY, church=0.09)
    assert float(church.church) == pytest.approx(0.09 * float(plain.tax + credit))
    assert (church.tax, church.soli) == (plain.tax, plain.soli)
    assert float(church.total - plain.total) == pytest.approx(float(church.church))
    tax = float(income_tax(60_000.0, TY))
    assert float(year_tax(60_000.0, TY, church=0.09) - year_tax(60_000.0, TY, church=0.0)) == (
        pytest.approx(0.09 * tax)
    )
    reserve = profit_reserve(6000.0, 0.0, 1000.0, TY, church=0.09)
    assert 12 * float(reserve - profit_reserve(6000.0, 0.0, 1000.0, TY, church=0.0)) == (
        pytest.approx(0.09 * tax)
    )


def test_church_tax_paid_is_a_sonderausgabe() -> None:
    """§10 Abs. 1 Nr. 4 EStG: it lowers the zvE like any other deduction beyond the
    Sonderausgaben-Pauschbetrag of 36 (§10c), which it replaces; a refund raises it (§10 Abs. 4b
    S. 3), after the Pauschbetrag."""
    year = YearIncome(salary_gross=60_000.0)
    for paid, beyond in ((800.0, 764.0), (-300.0, -300.0)):
        settled = year_settlement(replace(year, church_paid=paid), TY, church=0.09)
        deducted = year_settlement(replace(year, health_deductible=beyond), TY, church=0.09)
        assert float(settled.total) == pytest.approx(float(deducted.total))
    assert float(year_settlement(replace(year, church_paid=800.0), TY, church=0.09).total) < float(
        year_settlement(year, TY, church=0.09).total
    )


def test_the_guenstigerpruefung_counts_the_church_tax_on_both_sides() -> None:
    """§32d Abs. 6 EStG: the tariff wins when the income tax with the Zuschlagsteuern is lower,
    against the flat tax paid with Soli and church tax."""
    zve, capital, church = 10_000.0, 10_000.0, 0.09
    paid = capital * flat_rate(church, TY)
    tax, more = income_tax(zve, TY), income_tax(zve + capital, TY)
    refund = guenstigerpruefung(tax, more, paid, TY, church=church)
    tariff = (1 + church) * (more - tax) + soli(more, TY) - soli(tax, TY)
    assert float(refund) == pytest.approx(paid - float(tariff))
    assert 0.0 < float(refund) < paid
    assert float(guenstigerpruefung(0.0, income_tax(9000.0, TY), paid, TY, church=church)) == (
        pytest.approx(paid)
    )


@pytest.mark.parametrize(
    ("acquired", "relation", "inheritance", "tax"),
    [
        # 500,000 from a parent: less 15,000 Erbfallkosten and 400,000, 11% of 85,000
        (500000, Relation.PARENT, True, 9350),
        (500000, Relation.PARENT, False, 11000),  # a gift has no Erbfallkosten
        (476000, Relation.PARENT, False, 5750),  # Härteausgleich: 5,250 + half of 1,000
        (475000, Relation.PARENT, False, 5250),  # 7% up to and including 75,000
        (500049, Relation.PARENT, False, 11000),  # rounded down to 100 (§10 Abs. 1 S. 6)
        (100000, Relation.SIBLING, False, 13750),  # class II, 20% eased to 11,250 + 2,500
        (100000, Relation.SIBLING, True, 9750),  # 65,000 at 15%
        (100000, Relation.AUNT_UNCLE, False, 13750),
        (100000, Relation.PARENT_IN_LAW, False, 13750),
        (100000, Relation.OTHER, False, 24000),  # class III, 30% of 80,000
        (300000, Relation.GRANDPARENT, False, 11000),  # 200,000 free, 11% of 100,000
        (10000, Relation.PARENT, True, 0),  # below the Freibetrag
    ],
)
def test_erbschaftsteuer_by_relation(
    acquired: float, relation: Relation, inheritance: bool, tax: float
) -> None:
    """§§10, 15, 16, 19 ErbStG on one acquisition: the Freibetrag and class of the relation, the
    rates with the Härteausgleich of §19 Abs. 3 (half the excess over a limit up to 30%)."""
    found = erbschaftsteuer(acquired, [], [], relation, TY, inheritance=inheritance)
    assert found == pytest.approx(tax)


@pytest.mark.parametrize(
    ("acquired", "values", "paid", "relation", "tax"),
    [
        # a second gift of 300,000 from a parent within ten years: 200,000 over the Freibetrag
        (300000, [300000], [0], Relation.PARENT, 22000),
        # the tax paid on the first, 70,000, is above the 60,000 of today's law: it comes off
        (450000, [800000], [70000], Relation.PARENT, 161500 - 70000),
        (450000, [800000], [0], Relation.PARENT, 161500 - 60000),
        # an earlier acquisition of a value of 0 or below counts nothing (S. 5)
        (500000, [-100000], [0], Relation.PARENT, 11000),
        # at least the tax on this acquisition alone (S. 4): 22,000 on 600,000
        (600000, [800000], [180000], Relation.PARENT, 22000),
        # at most half of this acquisition (Abs. 3): the next euros run at 50% eased to 75%
        (10000, [6020000], [0], Relation.OTHER, 5000),
    ],
)
def test_erbschaftsteuer_adds_ten_years_of_one_giver(
    acquired: float, values: list[float], paid: list[float], relation: Relation, tax: float
) -> None:
    """§14 Abs. 1 ErbStG: the earlier acquisitions from the giver add at their value, the tax on
    them alone or the tax paid, the larger, comes off, at least the tax on the last alone; Abs. 3
    caps it at half of the last."""
    found = erbschaftsteuer(acquired, values, paid, relation, TY, inheritance=False)
    assert found == pytest.approx(tax)


def test_erbschaftsteuer_takes_one_row_per_earlier_acquisition_and_path() -> None:
    """Arrays in, one value per path: each row an earlier acquisition, each column a path."""
    values = np.array([[300000.0, 0.0, 300000.0], [0.0, 0.0, 150000.0]])
    found = erbschaftsteuer(
        np.full(3, 300000.0), values, np.zeros((2, 3)), Relation.PARENT, TY, inheritance=False
    )
    # the third: 750,000 less 400,000 at 15%, less the tax on 450,000 alone, 7% of 50,000
    assert found == pytest.approx([22000, 0, 52500 - 3500])


@pytest.mark.parametrize(
    ("income", "gde", "expected"),
    [
        (YearIncome(), 50_000.0, 36.0),  # the Pauschbetrag (§10c)
        (YearIncome(church_paid=800.0), 50_000.0, 800.0),  # replaces it
        (YearIncome(church_paid=-300.0), 50_000.0, 36.0 - 300.0),  # a refund comes after it
        (YearIncome(donations=5000.0), 50_000.0, 5000.0),
        (YearIncome(donations=15_000.0), 50_000.0, 10_000.0),  # 20% of the GdE (§10b)
        (YearIncome(donations=15_000.0), -5000.0, 36.0),  # none of a loss
        (YearIncome(childcare=3000.0, children=1), 50_000.0, 2400.0),  # 80% (§10 Abs. 1 Nr. 5)
        (YearIncome(childcare=9000.0, children=1), 50_000.0, 4800.0),  # the cap per child
        (YearIncome(childcare=9000.0, children=2), 50_000.0, 7200.0),
        (YearIncome(childcare=9000.0), 50_000.0, 36.0),  # no child under 14, no deduction
    ],
)
def test_sonderausgaben_beside_the_vorsorge(
    income: YearIncome, gde: float, expected: float
) -> None:
    assert float(sonderausgaben(income, gde, TY)) == pytest.approx(expected)


def test_haushalt_credit_is_a_fifth_of_the_labour_up_to_its_caps() -> None:
    """§35a Abs. 2 S. 1, Abs. 3 S. 1 EStG."""
    assert float(haushalt_credit(1000.0, 0.0, TY)) == pytest.approx(200.0)
    assert float(haushalt_credit(30_000.0, 10_000.0, TY)) == pytest.approx(4000.0 + 1200.0)
    assert float(haushalt_credit(0.0, 5000.0, TY)) == pytest.approx(1000.0)


def test_the_haushalt_credit_comes_off_the_tariff_tax_and_never_below_0() -> None:
    """1,000 € of household services lower the tax by 200 € and the Soli on it; the credit ends at
    0 and takes nothing of the Zulage of the Altersvorsorgedepot, which comes after it (§2 Abs. 6
    S. 2 EStG, BFH X R 11/21), on either side of the check of §10a Abs. 2."""
    year = YearIncome(salary_gross=30_000.0)
    plain, helped = (
        year_settlement(replace(year, household=h), TY, church=0.0) for h in (0.0, 1000.0)
    )
    assert float(plain.tax - helped.tax) == pytest.approx(200.0)
    assert float(helped.credit) == pytest.approx(200.0)
    low = YearIncome(salary_gross=15_000.0, household=30_000.0)
    assert float(year_settlement(low, TY, church=0.0).tax) == 0.0
    # a credit beyond the tariff tax with the deduction, short of it without: the deduction saves
    # more than the Zulage, which then comes back in full
    zve = 26_000.0 - TY.sonderausgaben_pauschbetrag
    without, deducted = float(income_tax(zve, TY)), float(income_tax(zve - 2340.0, TY))
    credit = (deducted + without - 540.0) / 2
    assert deducted < credit < without - 540.0
    depot = YearIncome(other_taxable=26_000.0, household=credit / 0.2, av_deduction=2340.0)
    settled = year_settlement(replace(depot, av_zulage=540.0), TY, church=0.0)
    assert float(settled.tax) == pytest.approx(540.0)


def test_alg1_in_a_year_without_salary_counts_less_the_pauschbetrag() -> None:
    """§32b Abs. 2 S. 1 Nr. 1 EStG: the part of the Arbeitnehmer-Pauschbetrag that the Arbeitslohn
    leaves unused comes off the ALG1 of the Progressionsvorbehalt; the own costs use it up."""
    other, alg1 = 30_000.0, 12_000.0
    zve = other - TY.sonderausgaben_pauschbetrag

    def rated(benefit: float) -> float:
        return float(income_tax(zve + benefit, TY)) / (zve + benefit) * zve

    alone = year_settlement(YearIncome(other_taxable=other, alg1=alg1), TY, church=0.0)
    assert float(alone.tax) == pytest.approx(rated(alg1 - TY.werbungskosten_pauschale))
    month = year_settlement(
        YearIncome(salary_gross=500.0, other_taxable=other, alg1=alg1), TY, church=0.0
    )
    assert float(month.tax) == pytest.approx(rated(alg1 - TY.werbungskosten_pauschale + 500.0))
    # own costs of 3,000 a year: the Pauschbetrag is used up by a salary above them
    costs = YearIncome(salary_gross=10_000.0, alg1=alg1, werbungskosten=3000.0)
    full = replace(costs, werbungskosten=0.0)
    assert float(year_settlement(costs, TY, church=0.0).tax) < float(
        year_settlement(full, TY, church=0.0).tax
    )


CHILD = ChildYear(12)  # a child all year, half of the allowances


def _zve_of(zve: float, **kw: Any) -> YearIncome:
    """Other income whose zvE is `zve`: the Sonderausgaben-Pauschbetrag on top."""
    return YearIncome(other_taxable=zve + TY.sonderausgaben_pauschbetrag, **kw)


def test_a_child_year_takes_its_allowances_and_the_kindergeld_by_its_months() -> None:
    """§32 Abs. 6 S. 1, 5, 6 and §31 S. 4 EStG: half of 6,828 and 2,928 against half of 259 a month,
    a twelfth per month; both halves against all of it on transfer."""
    assert (CHILD.allowances(TY), CHILD.kindergeld(TY)) == (4878.0, 1554.0)
    assert (ChildYear(4).allowances(TY), ChildYear(4).kindergeld(TY)) == (1626.0, 518.0)
    full = ChildYear(12, full=True)
    assert (full.allowances(TY), full.kindergeld(TY)) == (9756.0, 3108.0)


@pytest.mark.parametrize(("zve", "wins"), [(43_000.0, False), (43_050.0, True)])
def test_the_half_allowances_win_from_a_zve_of_43050(zve: float, *, wins: bool) -> None:
    """§31 S. 4 EStG in 2026: the half allowances save more than the half Kindergeld that the tax
    then adds above a marginal rate of 31.9%."""
    settled = year_settlement(_zve_of(zve, child_years=(CHILD,)), TY, church=0.0)
    plain, allowed = float(income_tax(zve, TY)), float(income_tax(zve - 4878, TY)) + 1554
    assert (allowed < plain) is wins
    assert float(settled.tax) == min(plain, allowed)


def test_each_child_takes_its_allowances_on_its_own() -> None:
    """R 31 Abs. 1 S. 3 EStR: per child, oldest first, so two half children at a zvE of 45,500
    pay 8,961 (the allowances of the first), not 9,001 (of both) or 9,003 (none)."""
    settled = year_settlement(_zve_of(45_500.0, child_years=(CHILD, CHILD)), TY, church=0.0)
    assert float(settled.tax) == 8961.0


def test_the_allowances_and_the_altersvorsorgedepot_each_take_the_cheaper_route() -> None:
    """§31 and §10a Abs. 2 EStG: each check sees the other at its cheaper route, so the tax is the
    least of the four."""
    zve, depot = 80_000.0, {"av_deduction": 2340.0, "av_zulage": 540.0}
    settled = year_settlement(_zve_of(zve, child_years=(CHILD,), **depot), TY, church=0.0)
    routes = [
        float(income_tax(zve - allowed - deducted, TY)) + added + zulage
        for allowed, added in ((0.0, 0.0), (4878.0, 1554.0))
        for deducted, zulage in ((0.0, 0.0), (2340.0, 540.0))
    ]
    assert float(settled.tax) == pytest.approx(min(routes)) == routes[3]


def test_the_kindergeld_comes_back_after_the_credits() -> None:
    """§2 Abs. 6 EStG: the credit of §35 comes off the tariff tax of the zvE that wins, at most its
    share of it (here half), then the tax adds the Kindergeld."""
    zve = 100_000.0
    trade = {"trade_income": (zve + TY.sonderausgaben_pauschbetrag) / 2, "trade_credit": 1e6}
    settled = year_settlement(_zve_of(zve, child_years=(CHILD,), **trade), TY, church=0.0)
    assert float(settled.tax) == pytest.approx(float(income_tax(zve - 4878, TY)) / 2 + 1554)


@pytest.mark.parametrize("zve", [30_000.0, 100_000.0])
def test_the_soli_and_the_church_tax_take_every_allowance(zve: float) -> None:
    """§3 Abs. 2 SolZG, §51a Abs. 2 S. 1 EStG: both on the tax of the zvE less the allowances,
    whether the Kindergeld wins (30,000) or the allowances (100,000)."""
    settled = year_settlement(_zve_of(zve, child_years=(CHILD,)), TY, church=0.09)
    base = income_tax(zve - 4878, TY)
    assert float(settled.soli) == float(soli(base, TY))
    assert float(settled.church) == pytest.approx(0.09 * float(base))


def test_the_entlastungsbetrag_comes_off_the_income_but_makes_no_loss() -> None:
    """§24b Abs. 2, 4 EStG: 4,260 € for the first child, 240 € for each further one, a twelfth
    for each month with a child; off the Summe der Einkünfte, at most down to 0 (§2 Abs. 3)."""
    assert float(entlastungsbetrag([1] * 12, TY)) == pytest.approx(4260.0)
    assert float(entlastungsbetrag([2] * 6 + [0] * 6, TY)) == pytest.approx((4260.0 + 240.0) / 2)
    settled = year_settlement(_zve_of(30_000.0, entlastung=4260.0), TY, church=0.0)
    assert float(settled.tax) == float(income_tax(30_000.0 - 4260.0, TY))
    low = year_settlement(YearIncome(other_taxable=1000.0, entlastung=4260.0), TY, church=0.0)
    assert float(low.loss_left) == 0.0


@pytest.mark.parametrize(
    ("years", "share"),
    [(10.0, 0.12), (10.9, 0.12), (15.0, 0.16), (20.0, 0.21), (30.0, 0.30), (40.0, 0.39), (1, 0.0)],
)
def test_a_bu_rente_is_taxed_at_the_ertragsanteil_of_its_laufzeit(
    years: float, share: float
) -> None:
    """§55 Abs. 2 EStDV by the Laufzeit to the contractual end, rounded down (R 22.4 Abs. 4, 5
    EStR): 10.9 years are 12%, not 13%."""
    assert float(ertragsanteil(years, TY)) == pytest.approx(share)


@pytest.mark.parametrize(
    ("year", "months"), [(2026, 66 * 12 + 3), (2028, 66 * 12 + 6), (2040, 804)]
)
def test_the_zurechnungszeit_ends_by_the_year_of_the_rentenbeginn(year: int, months: int) -> None:
    """§253a Abs. 3 SGB VI: 66 years and 3 months in 2026, 67 from 2031."""
    assert TY.zurechnung_months(year) == months
