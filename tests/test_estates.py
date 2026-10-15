"""Inheritances and gifts from relatives in the engine: the Erbschaftsteuer of each giver over ten
years, the month of death drawn per path, the carried cost basis, the ledger and the markers."""

from datetime import date
from typing import Any

import numpy as np
import pytest
from builders import booked, gold, marked, plan, zero_returns

from dagobert import anatomy
from dagobert.engine.simulation import horizon_months, simulate
from dagobert.model.assets import CashAsset
from dagobert.model.assumptions import Person
from dagobert.model.plan import Plan, Scenario
from dagobert.model.streams import Stream
from dagobert.model.taxes import Relation, TaxOptions
from dagobert.mortality import survival_curve, table
from dagobert.result import (
    INHERITANCE,
    INHERITANCE_TAX,
    NONCASH,
    ONEOFF_CONTRIBUTION,
    ONEOFF_IN,
    ONEOFF_OUT,
    ONEOFF_TAX,
    RunResult,
)
from dagobert.returns import Returns
from dagobert.tax import erbschaftsteuer, for_year

TY = for_year(2026)
MUTTER: dict[str, Any] = {"label": "Mutter", "born": date(1950, 5, 1), "sex": "f"}
VATER: dict[str, Any] = {"label": "Vater", "born": date(1948, 1, 1), "sex": "m"}


def estate(
    *events: dict[str, Any],
    mutter: Relation = Relation.PARENT,
    vater: Relation = Relation.PARENT,
    given: tuple[dict[str, Any], ...] = (),
    assets: tuple[object, ...] = (),
    streams: tuple[Stream, ...] = (),
    key: str = "mutter",
    **kw: object,
) -> Plan:
    """A plan of `events` (dicts of the file), the relatives Mutter (by `key`) and Vater of the
    person (born 1977, start 2026-01)."""
    relatives = {
        key: MUTTER | {"relation": mutter, "given": list(given)},
        "vater": VATER | {"relation": vater},
    }
    person = Person.model_validate({"born": date(1977, 1, 1), "relatives": relatives})
    return plan(
        list(streams),
        list(assets),
        Scenario.model_validate({"name": "t", "events": events}),
        person=person,
        **kw,
    )


def run(p: Plan, paths: int = 1, returns: Returns | None = None) -> RunResult:
    months = horizon_months(p.assumptions)
    return simulate(
        p, returns or zero_returns(months, paths), "montecarlo" if paths > 1 else "fixed"
    )


def received(r: RunResult) -> np.ndarray:
    """Per path the month in which the liquid wealth first rises, the length of the run without:
    a plan whose only flow is what the relatives give."""
    rose = np.diff(r.liquid, axis=1, prepend=r.liquid[:, :1]) > 0
    return np.where(rose.any(axis=1), rose.argmax(axis=1), len(r.months))


def paid(r: RunResult) -> np.ndarray:
    """Per path the Erbschaftsteuer of the run: its only tax."""
    return -r.taxes.sum(axis=1)


GIFT = {"type": "gift", "from": "mutter", "at": date(2030, 6, 1), "cash": 500_000}
UNDATED = {"type": "inheritance", "from": "mutter", "cash": 240_000}


def test_the_heir_keeps_the_cash_less_the_erbschaftsteuer_in_the_month() -> None:
    """A dated inheritance raises the liquid wealth by its cash less the tax, which lands in the
    taxes of its month and in `tax on one-offs`; the cash is a one-off source."""
    month = 48  # 2030-01
    r = run(estate(UNDATED | {"at": date(2030, 1, 1), "cash": 500_000}))
    base = 500_000 - 15_000 - 400_000  # Erbfallkosten, Freibetrag of a parent: 11% of 85,000
    assert r.liquid[0, -1] == pytest.approx(500_000 - 0.11 * base)
    assert r.taxes[0, month] == pytest.approx(-0.11 * base)
    assert booked(r, f"Mutter: {INHERITANCE_TAX}", ONEOFF_OUT, ONEOFF_TAX)[month] == pytest.approx(
        0.11 * base
    )
    assert booked(r, "Mutter", ONEOFF_IN, INHERITANCE)[month] == 500_000
    assert marked(r)[1:] == ["2030-01 inheritance: Mutter"]


def test_securities_keep_the_cost_basis_of_the_giver() -> None:
    """Inherited securities join the depot as non-cash income; a later sale for a deficit taxes
    their gain over the giver's cost basis, none when the basis is their value."""

    def taxed(basis: float) -> float:
        events = [
            UNDATED
            | {"at": date(2027, 1, 1), "cash": 0}
            | {"equity": {"value": 100_000, "cost_basis": basis}},
            {"type": "lump_sum", "at": date(2028, 1, 1), "amount": -50_000},
        ]
        r = run(estate(*events))
        assert booked(r, "Mutter: equity", NONCASH, ONEOFF_CONTRIBUTION)[12] == 100_000
        return float(-r.capital_taxes.sum())

    assert taxed(100_000) == 0
    assert taxed(0) > 0


@pytest.mark.parametrize("inflation", [0.0, 0.003], ids=["no inflation", "inflation"])
def test_the_erbschaftsteuer_is_nominal(inflation: float) -> None:
    """The constants of the Erbschaftsteuer are not indexed: a gift of 500,000 nominal pays the
    same 11,000 whatever the prices did before it, unlike the income tax."""
    p = estate(GIFT)
    months = horizon_months(p.assumptions)
    returns = zero_returns(months)
    returns.inflation[:] = inflation
    assert paid(run(p, returns=returns))[0] == pytest.approx(11_000)


def test_the_relation_sets_the_class_and_the_freibetrag() -> None:
    """500,000 from a parent pays less than from a grandparent, the class II relatives pay alike
    and more, `other` (class III) most."""
    taxes = {relation: paid(run(estate(GIFT, mutter=relation)))[0] for relation in Relation}
    assert taxes[Relation.PARENT] < taxes[Relation.GRANDPARENT] < taxes[Relation.SIBLING]
    assert taxes[Relation.SIBLING] == taxes[Relation.AUNT_UNCLE] == taxes[Relation.PARENT_IN_LAW]
    assert taxes[Relation.SIBLING] < taxes[Relation.OTHER]


@pytest.mark.parametrize(("at", "tax"), [(date(2023, 1, 1), 22_000), (date(2019, 1, 1), 0)])
def test_a_gift_before_the_start_counts_ten_years(at: date, tax: float) -> None:
    """A gift of `given` within ten years before a gift of 300,000 adds to it (§14 ErbStG): 300,000
    more over the Freibetrag at 11%, the tax paid on it 0; one older than ten years does not."""
    given = {"at": at, "value": 300_000, "tax": 0}
    r = run(estate(GIFT | {"cash": 300_000}, given=(given,)))
    assert paid(r)[0] == pytest.approx(tax)


def test_a_gift_counts_with_the_estate_of_its_giver() -> None:
    """A gift within ten years before the estate of its giver adds to the estate (§14): the estate
    pays the tax of both less that of the gift."""
    gift, after = GIFT | {"cash": 300_000}, UNDATED | {"at": date(2035, 1, 1)}
    alone = paid(run(estate(after)))[0]
    both = paid(run(estate(gift, after)))[0]
    assert alone == 0
    assert both == pytest.approx(
        erbschaftsteuer(540_000, [], [], Relation.PARENT, TY, inheritance=True)
    )


def test_the_death_is_drawn_per_path_from_the_life_table() -> None:
    """Without a month the inheritance falls at the death of the relative: by the end of the run
    the share of the paths that received it is the share of the life table that died, two runs
    with one seed receive in the same months, so does a run with another asset, and a single
    path takes the median month."""
    p = estate(UNDATED)
    months = received(run(p, 2000))
    n = horizon_months(p.assumptions)
    curve = survival_curve(table(), p.assumptions.person.relatives["mutter"], date(2026, 1, 1), n)
    assert (months < n).mean() == pytest.approx(1 - curve[-1], abs=0.03)
    assert (months < 120).mean() == pytest.approx(1 - curve[119], abs=0.03)
    assert np.array_equal(received(run(p, 2000)), months)
    other = estate(UNDATED, assets=(gold(1000),))
    assert np.array_equal(received(run(other, 2000)), months)
    assert received(run(p))[0] == np.argmax(curve < 0.5)


def test_a_renamed_relative_draws_other_months() -> None:
    """The months of death follow the generator of the relative's key (`inheritance.<key>`): the
    same relative under another key dies in other months on the paths."""
    months = received(run(estate(UNDATED), 500))
    renamed = received(run(estate(UNDATED | {"from": "mama"}, key="mama"), 500))
    assert not np.array_equal(renamed, months)


def test_an_inheritance_without_a_month_drives_the_failure_anatomy() -> None:
    """Cash that lasts until about the median death of Mutter: the paths on which she dies later
    run out, so her inheritance is a driver of the anatomy; without it there is none."""
    spending = (Stream.model_validate({"name": "Leben", "amount": -1000}),)
    cash = (CashAsset(id="c", kind="cash", value=150_000),)
    key = (anatomy.INHERITANCE, "Mutter")
    found = anatomy.of(run(estate(UNDATED | {"cash": 350_000}, assets=cash, streams=spending), 500))
    assert found is not None
    bins = {d.key: d.bins for d in found.drivers}[key]
    assert bins[0].broke < bins[-1].broke  # the later she dies, the more paths run out
    assert key not in run(estate(assets=cash, streams=spending), 500).drivers


def test_the_later_death_of_two_givers_with_the_freibetrag_of_the_last() -> None:
    """A Berliner Testament: an inheritance from both falls at the later of their deaths on every
    path, taxed by the relation of the one who died last (a parent and a sibling: some paths pay
    the class II tax of the sibling)."""
    big = {"cash": 800_000}
    mutter = run(estate(UNDATED | big, vater=Relation.SIBLING), 500)
    vater = run(estate(UNDATED | big | {"from": "vater"}, vater=Relation.SIBLING), 500)
    both = run(estate(UNDATED | big | {"from": ["mutter", "vater"]}, vater=Relation.SIBLING), 500)
    first, second = received(mutter), received(vater)
    assert np.array_equal(received(both), np.maximum(first, second))
    last = np.where(first >= second, paid(mutter), paid(vater))
    assert np.allclose(paid(both), last)
    assert len(set(np.round(paid(both)))) > 1


def test_a_gift_of_a_giver_dead_by_then_joins_the_estate() -> None:
    """On a path on which the relative died before the gift, the gift is paid with the estate, in
    its month: one acquisition of both, taxed as one."""
    r = run(estate(GIFT | {"cash": 300_000}, UNDATED), 1000)
    gift_month = 53  # 2030-06
    early = received(r) < gift_month
    assert early.any()
    one = erbschaftsteuer(540_000, [], [], Relation.PARENT, TY, inheritance=True)
    assert np.allclose(r.liquid[early, -1], 540_000 - one)
    assert np.allclose(paid(r)[early], one)
    assert np.all(np.count_nonzero(r.taxes[early], axis=1) == 1)


def test_the_marker_falls_when_half_of_the_paths_received() -> None:
    r = run(estate(UNDATED), 500)
    month = int(np.argmax((received(r)[:, None] <= np.arange(len(r.months))).mean(axis=0) >= 0.5))
    assert f"{r.months[month]:%Y-%m} inheritance: Mutter (half of the paths)" in marked(r)


def test_an_inheritance_is_no_income_and_no_health_insurance_base() -> None:
    """No income tax and no KV on the cash of an inheritance: a GKV member with a salary pays the
    same KV, PV and income tax with and without it."""
    salary = Stream.model_validate({"name": "Gehalt", "kind": "salary", "gross": 5000})
    gkv = TaxOptions(pkv=False)
    with_it = run(estate(UNDATED | {"at": date(2027, 3, 1)}, streams=(salary,), tax=gkv))
    without = run(estate(streams=(salary,), tax=gkv))
    for item in ("KV", "PV", "income tax"):
        assert np.allclose(booked(with_it, item), booked(without, item))


def test_a_gift_before_the_start_is_an_error() -> None:
    with pytest.raises(ValueError, match="before the start"):
        run(estate(GIFT | {"at": date(2025, 6, 1)}))
