"""The children of the person (rule `children`): the Kindergeld that the engine pays, the check
of §31 EStG against the allowances, the Entlastungsbetrag, ALG1 at 67%, the PV surcharge up to the
first birth and the child-raising years of the pension. Relations between runs of small plans with
zero returns; the law in amounts is in `test_tax.py`."""

from datetime import date

import numpy as np
import pytest
from builders import booked, cash, phases, plan, salary, zero_run
from pydantic import ValidationError

from dagobert import sv, tax
from dagobert.engine.simulation import before
from dagobert.model.assumptions import Child, Person
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import Allowance
from dagobert.result import INCOME_TAX, KINDERGELD, SOURCE, RunResult

TY = tax.for_year(2026)
START = date(2026, 1, 1)  # of the plans of `builders`
YEAR = slice(0, 12)


def parent(*children: Child, **kw: object) -> Person:
    """Born 1977, as the parent of `builders`, with `children`."""
    return Person.model_validate(
        {"born": date(1977, 1, 1), "children": len(children), "children_born": children} | kw
    )


def run(person: Person, streams: list[Stream], months: int = 12, **kw: object) -> RunResult:
    p = plan(streams, [cash(500_000)], None, person=person, **kw)
    return zero_run(p, months)


def income_tax(r: RunResult, months: slice = YEAR) -> float:
    """The income tax, Soli and church tax of the months."""
    return float(booked(r, INCOME_TAX)[months].sum())


@pytest.mark.parametrize(
    ("child", "first", "end"),
    [
        (Child(born=date(2026, 5, 20)), 4, 36),  # born in the run: from its month
        (Child(born=date(2010, 2, 1), until=date(2027, 3, 1)), 0, 14),  # in education
        (Child(born=date(2008, 7, 15)), 0, 7),  # 18 in July 2026: counts through July
        (Child(born=date(2008, 7, 1)), 0, 6),  # 18 on 2026-07-01: through June
        (Child(born=date(2020, 1, 1), kindergeld=False), 0, 0),  # another person receives it
    ],
)
def test_the_kindergeld_pays_in_the_months_that_the_child_counts(
    child: Child, first: int, end: int
) -> None:
    """§66 EStG, §32 Abs. 3: 259 € a month from the month of birth to the month before `until`,
    by default to the month in which the child turns 18, free of tax."""
    r = run(parent(child), [], months=36)
    paid = np.zeros(36)
    paid[first:end] = TY.kindergeld_month
    assert booked(r, KINDERGELD, SOURCE) == pytest.approx(paid)
    assert r.income[0] == pytest.approx(paid)
    assert income_tax(r, slice(0, 36)) == 0.0


@pytest.mark.parametrize(("gross", "saves"), [(9000.0, True), (3000.0, False)])
def test_the_allowances_replace_the_kindergeld_where_they_save_more(
    gross: float, *, saves: bool
) -> None:
    """§31 EStG: with a child a high salary pays less income tax, as the half allowances save more
    than the half Kindergeld that the tax then adds; a low one pays the same tax."""
    child = Child(born=date(2015, 1, 1))
    plain, raised = run(parent(), [salary(gross)]), run(parent(child), [salary(gross)])
    saved = income_tax(plain) - income_tax(raised)
    assert saved > 0 if saves else saved == 0.0


def test_full_allowances_save_more_than_half() -> None:
    """§32 Abs. 6 S. 6 EStG: both allowances of a child move to you on application."""
    half, full = (
        run(parent(Child(born=date(2015, 1, 1), freibetrag=f)), [salary(9000)]) for f in Allowance
    )
    assert income_tax(full) < income_tax(half)


def test_the_soli_and_the_church_tax_take_the_allowances_whichever_wins() -> None:
    """§3 Abs. 2 SolZG, §51a Abs. 2 EStG: the church tax falls with a child also where the
    Kindergeld wins and the income tax stays."""
    child = Child(born=date(2015, 1, 1))
    church = {"church": True, "land": "BE"}
    plain, raised = (run(parent(*c), [salary(3000)], tax=church) for c in ((), (child,)))
    assert income_tax(raised) < income_tax(plain)
    assert raised.taxes[0, :11] == pytest.approx(plain.taxes[0, :11])  # the withholding


@pytest.mark.parametrize("children", [1, 2])
def test_a_single_parent_deducts_the_entlastungsbetrag(children: int) -> None:
    """§24b EStG: 4,260 € a year off the income for the first child, 240 € more for each further
    one, a twelfth for each month in which a child counts."""
    kids = [Child(born=date(2015, 1, 1), kindergeld=False) for _ in range(children)]
    alone, together = (
        run(parent(*kids), [salary(4000)], tax={"alleinerziehend": a}) for a in (True, False)
    )
    relief = TY.entlastungsbetrag + TY.entlastungsbetrag_more * (children - 1)
    saved = income_tax(together) - income_tax(alone)
    assert 0.2 * relief < saved < 0.45 * relief
    assert income_tax(run(parent(), [salary(4000)], tax={"alleinerziehend": True})) == (
        pytest.approx(income_tax(run(parent(), [salary(4000)])))
    )


@pytest.mark.parametrize(
    ("child", "rate"),
    [
        (Child(born=date(2015, 1, 1)), TY.alg1_rate_kinder),
        (Child(born=date(2000, 1, 1)), TY.alg1_rate_base),  # grown: no child of §32
        (None, TY.alg1_rate_base),  # a child without a date counts for nothing
    ],
)
def test_alg1_pays_67_percent_with_a_child_that_counts(child: Child | None, rate: float) -> None:
    """§149 SGB III: 67% with a child of §32 Abs. 1, 3 to 5 EStG in the first month of the claim,
    else 60%."""
    person = parent(child) if child else parent(children=1)
    scenario = Scenario(name="s", phases=phases((START, "work"), (date(2026, 7, 1), "unemployed")))
    streams = [salary(4000, phases=["work"])]
    streams += [Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"])]
    p = plan(streams, [cash(100_000)], scenario, person=person)
    paid = booked(zero_run(p, 12), "alg", SOURCE)[6]
    plain = float(sv.alg1_month(4000, TY, child=False))
    assert paid == pytest.approx(plain * rate / TY.alg1_rate_base)


def test_the_pv_surcharge_for_the_childless_holds_up_to_the_first_birth() -> None:
    """§55 Abs. 3 SGB XI: a parent from the month of the birth; a child without a date is grown
    and counts at once."""
    expecting = parent(Child(born=date(2027, 3, 15)))
    rates = [sv.pv_rate(TY.pv_rate, expecting, date(2027, m, 1), TY) for m in (2, 3)]
    assert rates == [TY.pv_rate + TY.pv_kinderlos_zuschlag, TY.pv_rate]
    assert sv.pv_rate(TY.pv_rate, parent(children=1), START, TY) == TY.pv_rate


def _points(gross: float, *, raised: bool) -> float:
    """The pension points of a parent with this salary through the 36 months after a birth in
    the run."""
    born = date(2026, 3, 10)
    person = parent(Child(born=born, erziehung=raised))
    p = plan([salary(gross)] if gross else [], [cash(500_000)], person=person)
    engine = before(p, add_months(born, TY.kez_months + 1))
    assert engine is not None
    return float(engine.pension.points[0])


@pytest.mark.parametrize("gross", [0.0, 3000.0, 7500.0, TY.sv_bbg_month])
def test_the_child_raising_years_add_points_up_to_the_hoechstwert(gross: float) -> None:
    """§56, §70 Abs. 2 SGB VI: 0.0833 points for each of the 36 months after the month of birth,
    on top of the points of the salary, up to the BBG over the Durchschnittsentgelt: at 7,500 € the
    cap less the salary's points, at the BBG nothing."""
    cap = TY.sv_bbg_month / TY.durchschnittsentgelt
    own = gross / TY.durchschnittsentgelt
    added = TY.kez_months * min(TY.kez_points_month, cap - own)
    assert _points(gross, raised=True) - _points(gross, raised=False) == pytest.approx(added)


def test_the_years_with_a_young_child_count_for_the_35_years() -> None:
    """§57, §51 Abs. 3 SGB VI: the months to the 10th birthday of a child that you raised count
    as insured (the 36 months of §56 among them), so a claim at 63 with 35 years opens without a
    salary in the run: 25 years before the start and 121 months; without them it waits for 67."""
    pension = Stream(name="r", kind=StreamKind.PENSION, gross=1000, phases=["retired"])
    wanted = date(2040, 2, 1)  # 63 and a month
    retire = Scenario(name="r", phases=phases((START, "alt"), (wanted, "retired")))
    claims = []
    for raised in (True, False):
        child = Child(born=date(2026, 1, 15), erziehung=raised)
        p = plan(
            [pension], [cash(500_000)], retire, person=parent(child, rv_since=date(2001, 1, 1))
        )
        r = zero_run(p, months_between(START, wanted) + 60)
        claims.append(next((m.years, m.since) for m in r.markers if m.kind == "pension"))
    assert claims == [(pytest.approx(25 + 121 / 12), None), (25, wanted)]


@pytest.mark.parametrize(
    ("until", "problem"),
    [
        (date(2016, 4, 1), "is not after the month of birth"),
        (date(2041, 6, 1), "a child counts at most to its 25th birthday"),
    ],
)
def test_until_lies_between_the_birth_and_the_25th_birthday(until: date, problem: str) -> None:
    """§32 Abs. 4 S. 1 Nr. 2 EStG: a child in education counts to 25, its `until` at most the month
    after that birthday."""
    Child(born=date(2016, 4, 10), until=date(2041, 5, 1))
    with pytest.raises(ValidationError, match=problem):
        Child(born=date(2016, 4, 10), until=until)
