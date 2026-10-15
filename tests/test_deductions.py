"""What lowers the income tax beyond the Vorsorge (rule `deductions`): the Werbungskosten above
the Pauschbetrag, the expenses with `deduct` (donations, childcare, the credit of §35a), the
premium of a Basisrente and its payout at the share of its start, the Zulage of the
Altersvorsorgedepots once per person with the Kinderzulage of 2027. Relations between runs of small
plans with zero returns; the law in amounts is in `test_tax.py`."""

from datetime import date
from typing import Any

import numpy as np
import pytest
from builders import booked, cash, phases, plan, salary, zero_run
from pydantic import ValidationError

from dagobert import tax
from dagobert.model.assets import AvDepot, PensionPolicy
from dagobert.model.assumptions import Child, Person
from dagobert.model.events import Event, FundPolicyEvent, PolicyFunding, SeveranceEvent
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import RunResult

YEAR, NEXT = slice(0, 12), slice(12, 24)


def expense(amount: float, **kw: object) -> Stream:
    """A nominal expense of the category `life`."""
    return Stream.model_validate(
        {"name": "Ausgabe", "cat": "life", "amount": amount, "index": None} | kw
    )


def other(amount: float, **kw: object) -> Stream:
    return Stream.model_validate(
        {"name": "Zins", "kind": "other_income", "amount": amount, "index": None} | kw
    )


def run(
    streams: list[Stream],
    months: int = 12,
    assets: list[Any] | None = None,
    scenario: Scenario | None = None,
    **kw: object,
) -> RunResult:
    p = plan(streams, [cash(500_000), *(assets or [])], scenario, **kw)
    return zero_run(p, months)


def taxed(r: RunResult, months: slice = YEAR) -> float:
    """The income tax, Soli and SV of the months."""
    return float(-r.taxes[0, months].sum())


@pytest.mark.parametrize(("costs", "lower"), [(3000.0, True), (1230.0, False), (1000.0, False)])
def test_werbungskosten_above_the_pauschbetrag_lower_the_tax(costs: float, *, lower: bool) -> None:
    """§9a S. 1 Nr. 1 a EStG: the own costs count when they are higher than the Pauschbetrag."""
    plain = run([salary()])
    own = run([salary()], tax={"werbungskosten": costs})
    assert (taxed(own) < taxed(plain)) == lower
    assert taxed(own) <= taxed(plain)


def test_werbungskosten_count_by_the_salary_months() -> None:
    """A year with three months of salary takes a quarter of the yearly costs: 24,000 € in three
    months with 12,000 € of costs a year pays what 24,000 € in six months with 6,000 € pays, both
    3,000 € of costs. Below the BBG and without a PKV premium the SV is the same. A year without a
    salary takes none."""
    short = run([salary(8000.0, end=date(2026, 4, 1))], tax={"werbungskosten": 12_000})
    longer = run([salary(4000.0, end=date(2026, 7, 1))], tax={"werbungskosten": 6000})
    plain = run([salary(4000.0, end=date(2026, 7, 1))])
    assert taxed(short) == pytest.approx(taxed(longer), abs=1)
    assert taxed(longer) < taxed(plain)
    idle = [other(3000.0)]
    assert taxed(run(idle, tax={"werbungskosten": 9000})) == taxed(run(idle))


def test_the_alg1_of_the_bundesagentur_ignores_the_own_costs() -> None:
    """§153 SGB III takes the Pauschbetrag into the Leistungsentgelt, never the own costs."""
    scenario = Scenario(
        name="a", phases=phases((date(2026, 1, 1), "work"), (date(2026, 7, 1), "unemployed"))
    )
    streams = [salary(phases=["work"]), Stream(name="ALG1", kind=StreamKind.ALG1)]
    plain = run(streams, scenario=scenario)
    own = run(streams, scenario=scenario, tax={"werbungskosten": 8000})
    assert own.income[0, 6:].tolist() == pytest.approx(plain.income[0, 6:].tolist())
    assert taxed(own) < taxed(plain)


def test_a_donation_lowers_the_tax_up_to_a_fifth_of_the_income_and_carries_nothing() -> None:
    """§10b Abs. 1 EStG: up to 20% of the Gesamtbetrag der Einkünfte, the rest is lost (its carry
    is a gap), so the next year pays as without it."""
    later = date(2027, 1, 1)

    def donating(amount: float) -> RunResult:
        gift = expense(amount, every=12, start=date(2026, 12, 1), end=later, deduct="donation")
        return run([other(5000.0), gift] if amount else [other(5000.0)], months=24)

    plain, some, all_of_it, more = (donating(a) for a in (0, -2000, -20_000, -40_000))
    assert taxed(some) < taxed(plain)
    assert taxed(all_of_it) == pytest.approx(taxed(more))  # 20% of 60,000 €: both above
    assert taxed(all_of_it) < taxed(some)
    assert taxed(more, NEXT) == pytest.approx(taxed(plain, NEXT))


def test_a_deduction_counts_what_was_paid_its_share_that_counts() -> None:
    """The expense after `scale.categories` and the spending cut, times `deductible`: half of a
    gift of 4,000 € deducts as a donation of 2,000 €, and a gift of 4,000 € that the scale halves
    the same."""
    income = other(5000.0)
    half = run([income, expense(-4000.0, deduct="donation", deductible=0.5)])
    scaled = run([income, expense(-4000.0, deduct="donation")], scale={"categories": {"life": 0.5}})
    plain = run([income, expense(-2000.0, deduct="donation")])
    assert taxed(half) == pytest.approx(taxed(plain))
    assert taxed(scaled) == pytest.approx(taxed(plain))


def test_a_deduction_under_the_spending_cut_counts_what_was_paid() -> None:
    """The cut of the spending rule lowers the expense and with it the deduction."""
    rule = {"cut": 0.5, "trigger": 10.0, "categories": ["life"]}  # cuts from the first month
    cut = run([other(5000.0), expense(-4000.0, deduct="donation")], spending=rule)
    plain = run([other(5000.0), expense(-2000.0, deduct="donation")])
    assert cut.expenses[0, 0] == pytest.approx(-2000.0)
    assert taxed(cut) == pytest.approx(taxed(plain))


def test_household_services_lower_the_tax_by_a_fifth_and_never_below_zero() -> None:
    """§35a Abs. 2 EStG: 1,000 € of household services take 200 € off the income tax of the year
    (no Soli at this income), a large bill not below zero: no refund beyond the tax."""
    help_ = expense(-1000.0, every=12, start=date(2026, 12, 1), deduct="household")
    plain, helped = run([other(3000.0)]), run([other(3000.0), help_])
    assert taxed(plain) - taxed(helped) == pytest.approx(200.0)
    huge = expense(-1000.0, deduct="craftsman")  # 12,000 € a year: at most 1,200 € of credit
    low = run([other(1500.0), huge, help_.model_copy(update={"amount": -30_000.0})])
    assert taxed(low) == 0.0


def test_childcare_counts_the_months_of_a_child_under_14_and_its_cap_per_year() -> None:
    """§10 Abs. 1 Nr. 5 EStG: 80% of the costs of a child under 14, at most 4,800 € a year per
    child, which a child who turns 14 in May reaches with the costs of January to April: the cap
    is no twelfths. Without a date of birth no child counts."""
    child = Person(born=date(1977, 1, 1), children=1, children_born=[Child(born=date(2012, 5, 1))])
    care = expense(-2000.0, deduct="childcare")
    whole = run([other(6000.0), care], person=child)
    april = run([other(6000.0), care.model_copy(update={"end": date(2026, 5, 1)})], person=child)
    capped = run(
        [other(6000.0), care.model_copy(update={"amount": -1500.0, "end": date(2026, 5, 1)})],
        person=child,
    )
    plain = run([other(6000.0)], person=child)
    assert taxed(whole) == pytest.approx(taxed(april))  # the months from May count nothing
    assert taxed(april) == pytest.approx(taxed(capped))  # 6,400 € and 4,800 € reach the cap
    assert taxed(capped) < taxed(plain)
    undated = Person(born=date(1977, 1, 1), children=1)
    assert taxed(run([other(6000.0), care], person=undated)) == pytest.approx(
        taxed(run([other(6000.0)], person=undated))
    )


def _policy(**kw: object) -> PensionPolicy:
    fields = {"id": "r", "kind": "bav", "value": 0, "phases": ["work"], "growth": "cash"}
    annuity = {"payout": "annuity", "annuity_per_10k": 50, "basisrente": True}
    return PensionPolicy.model_validate(fields | annuity | {"matures": date(2040, 1, 1)} | kw)


def test_a_premium_lowers_the_tax_like_a_payment_of_the_same_sum() -> None:
    """The own premium of a Basisrente is an Altersvorsorgeaufwand (§10 Abs. 1 Nr. 2 b EStG), like
    a `fund_policy` of the year's sum; both move the cash into the policy."""
    monthly = run([other(6000.0)], assets=[_policy(premium=500)])
    paid = FundPolicyEvent(at=date(2026, 6, 1), type="fund_policy", policy="r", amount=6000)
    once = run([other(6000.0)], assets=[_policy()], scenario=Scenario(name="f", events=[paid]))
    plain = run([other(6000.0)], assets=[_policy()])
    assert taxed(monthly) == pytest.approx(taxed(once))
    assert taxed(monthly) < taxed(plain)
    assert monthly.total[0, -1] == pytest.approx(once.total[0, -1])
    assert monthly.liquid[0, 0] == pytest.approx(plain.liquid[0, 0] - 500)


def _annuity(*, basisrente: bool, pkv: bool = True) -> RunResult:
    """A policy of 200,000 € that pays 2,000 € a month from 2026."""
    fields = {"value": 200_000, "paid": 200_000, "phases": [], "matures": date(2026, 1, 1)}
    fields |= {"annuity_per_10k": 100}
    policy = _policy(**fields | {"basisrente": basisrente})
    return run([], months=12, assets=[policy], tax={"pkv": pkv})


def test_a_basisrente_pays_its_tax_at_the_share_of_its_start() -> None:
    """§22 Nr. 1 S. 3 a aa EStG: 84% of an annuity that starts in 2026, of a company pension
    all."""
    base, company = _annuity(basisrente=True), _annuity(basisrente=False)
    assert taxed(base) < taxed(company)
    share = tax.pension_share(2026, tax.for_year(2026))
    zve = 24_000 * share - 102 - 36  # the Pauschbeträge of §9a S. 1 Nr. 3 and §10c
    assert taxed(base) == pytest.approx(float(tax.income_tax(zve, tax.for_year(2026))))


def test_the_kv_of_a_voluntary_member_takes_the_whole_basisrente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The GKV takes the annuity in full whatever share the income tax takes."""
    shared = _annuity(basisrente=True, pkv=False)
    monkeypatch.setattr(tax, "pension_share", lambda start, ty: 1.0)
    full = _annuity(basisrente=True, pkv=False)
    assert booked(shared, "KV").tolist() == pytest.approx(booked(full, "KV").tolist())
    assert taxed(shared) < taxed(full)


@pytest.mark.parametrize(
    "fields",
    [{"contribution": 100}, {"conversion": 100}, {"premium": 100, "basisrente": False}],
    ids=["contribution", "conversion", "premium of a company pension"],
)
def test_a_basisrente_takes_no_money_free_of_tax(fields: dict[str, object]) -> None:
    """Money free of tax under §3 Nr. 63 EStG comes out taxed in full (§22 Nr. 5 S. 1), so a
    Basisrente takes neither the employer's money nor a conversion; a premium of your own goes
    into a Basisrente only."""
    with pytest.raises(ValidationError):
        _policy(**fields)


@pytest.mark.parametrize("into_basisrente", [True, False])
def test_a_severance_funds_a_company_pension_and_a_payment_a_basisrente(
    *, into_basisrente: bool
) -> None:
    company = _policy(id="k", basisrente=False, payout="lump_sum", phases=[])
    target = "r" if into_basisrente else "k"
    event: Event = (
        SeveranceEvent(
            at=date(2026, 6, 1),
            type="severance",
            gross=50_000,
            bav=PolicyFunding(policy=target, amount=10_000),
        )
        if into_basisrente
        else FundPolicyEvent(at=date(2026, 6, 1), type="fund_policy", policy=target, amount=1000)
    )
    with pytest.raises(ValidationError, match=f"but {target} "):
        plan([], [cash(), _policy(), company], Scenario(name="s", events=[event]))


def _depots(*contributions: float, person: Person | None = None) -> RunResult:
    """Depots that start in 2027 with a salary all year: their value at the end of 2027."""
    depots = [
        AvDepot(id=f"av{i}", kind="av_depot", contribution=c, start=date(2027, 1, 1))
        for i, c in enumerate(contributions)
    ]
    return run([salary()], months=24, assets=depots, person=person or Person(born=date(1977, 1, 1)))


def _in_depots(r: RunResult) -> float:
    return float(r.total[0, 23] - r.liquid[0, 23])


def test_two_depots_earn_one_zulage_and_one_room() -> None:
    """§84 S. 1 EStG: one Grundzulage per person, on the contributions to all depots, and one room
    of §10a: two depots of 900 € pay what one of 1,800 € pays."""
    one, two = _depots(1800), _depots(900, 900)
    assert _in_depots(two) == pytest.approx(_in_depots(one)) == pytest.approx(1800 + 540)
    assert taxed(two, NEXT) == pytest.approx(taxed(one, NEXT))


@pytest.mark.parametrize(
    ("child", "extra"),
    [
        (Child(born=date(2012, 3, 1)), 300.0),
        (Child(born=date(2005, 5, 1)), 0.0),  # 18 in 2023
        (Child(born=date(2005, 5, 1), until=date(2030, 5, 1)), 300.0),  # in education
        (Child(born=date(2012, 3, 1), kindergeld=False), 0.0),
    ],
)
def test_a_child_with_kindergeld_in_any_month_earns_the_kinderzulage(
    child: Child, extra: float
) -> None:
    """§85 Abs. 1 S. 1 EStG from 2027: the contributions, at most 300 € per child whose
    Kindergeld you receive in some month of the year: to 18, to its `until` in education."""
    parent = Person(born=date(1977, 1, 1), children=1, children_born=[child])
    assert _in_depots(_depots(1800, person=parent)) == pytest.approx(1800 + 540 + extra)
    assert np.isclose(_in_depots(_depots(200, person=parent)), 200 + 100 + min(200.0, extra))
