"""Budget of a stretch of a scenario from the engine ledger. Its Sankey is in test_ui_flows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date

import pytest
from builders import cash, phases, plan, zero_run

from dagobert import budget
from dagobert.budget import Budget
from dagobert.model.assets import Loan, PensionPolicy, PropertyAsset, TermDeposit
from dagobert.model.events import (
    AddStreamEvent,
    FundPolicyEvent,
    PolicyFunding,
    RepayEvent,
    SellEvent,
    SeveranceEvent,
)
from dagobert.model.plan import Plan, Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import LOAN_INTEREST, LOAN_PRINCIPAL, TAX, RunResult


def _plan() -> Plan:
    """Two years of work with a loan that an event repays and an employer's contribution to a
    policy, then a year off with a severance, part of it into the policy, a sale and a premium
    into a Basisrente."""
    scenario = Scenario(
        name="s",
        phases=phases((date(2026, 1, 1), "work"), (date(2028, 1, 1), "alt")),
        events=[
            RepayEvent(at=date(2027, 1, 1), type="repay", loan="haus"),
            SeveranceEvent(
                at=date(2028, 1, 1),
                type="severance",
                gross=100_000,
                bav=PolicyFunding(policy="rente", amount=12_000),
            ),
            SellEvent(at=date(2028, 3, 1), type="sell", asset="wohnung"),
            FundPolicyEvent(at=date(2028, 4, 1), type="fund_policy", policy="basis", amount=20_000),
        ],
    )
    streams = [
        Stream(name="Gehalt", kind=StreamKind.SALARY, gross=6000, phases=["work"]),
        Stream(name="Bonus", kind=StreamKind.SALARY, gross=12_000, every=12, phases=["work"]),
        Stream(name="PKV", cat="versicherung", amount=-800, health="kv"),
        Stream(name="Miete", cat="wohnen", amount=-900),
    ]
    deposit = TermDeposit(
        id="festgeld",
        kind="term_deposit",
        value=100_000,
        rate=0.03,
        start=date(2025, 6, 1),
        matures=date(2027, 6, 1),
    )
    policy = PensionPolicy(
        id="rente",
        kind="bav",
        value=0,
        paid=0,
        contribution=200,
        phases=["work"],
        matures=date(2045, 1, 1),
        growth="equity",
    )
    basis = policy.model_copy(
        update={"id": "basis", "contribution": 0, "phases": [], "basisrente": True}
        | {"payout": "annuity", "annuity_per_10k": 40}
    )
    loan = Loan(id="haus", kind="loan", balance=-50_000, rate=0.024, annuity=500)
    flat = PropertyAsset(id="wohnung", kind="property", sqm=50, per_sqm=4800, upkeep=0.01)
    return plan(streams, [cash(500_000), loan, flat, deposit, policy, basis], scenario)


def _run(of: Plan | None = None) -> RunResult:
    return zero_run(of or _plan(), 36)


def _business() -> Plan:
    """A salary in `work`, then a business with a yearly project in `alt`."""
    scenario = Scenario(
        name="s", phases=phases((date(2026, 1, 1), "work"), (date(2026, 7, 1), "alt"))
    )
    streams = [
        Stream(name="Gehalt", kind=StreamKind.SALARY, gross=6000, phases=["work"], index=None),
        Stream(
            name="Laden", kind=StreamKind.SELF_EMPLOYED, amount=4000, phases=["alt"], index=None
        ),
        Stream.model_validate(
            {"name": "Projekt", "kind": "self_employed", "amount": 9000, "every": 12}
            | {"start": date(2026, 12, 1), "phases": ["alt"], "index": None}
        ),
    ]
    return plan(streams, [cash()], scenario)


@pytest.mark.parametrize(
    ("of", "paid"),
    [(_plan, {"work": 6000}), (_business, {"work": 6000, "alt": 4000})],
    ids=["without the bonus", "a profit too"],
)
def test_regular_salary_is_the_usual_month(of: Callable[[], Plan], paid: dict[str, float]) -> None:
    """A bonus month does not count, a phase without pay is absent (`alt` of the first plan),
    and the salary slider scales a profit too: a phase of a business has its usual month."""
    assert budget.regular_salary(_run(of())) == paid


def test_many_paths_keep_no_ledger() -> None:
    two = zero_run(plan([], []), 3, 2)
    assert two.ledger is None
    with pytest.raises(ValueError, match="single-path"):
        budget.regular_salary(two)


def test_budget_follows_the_scenario() -> None:
    r = _run()
    assert r.ledger is not None
    first = budget.from_ledger(r.ledger, range(12))
    assert first.sources == {
        "Gehalt": pytest.approx(6000.0),
        "Bonus": pytest.approx(1000.0),
        "PKV subsidy": pytest.approx(400.0),
    }
    assert 0.25 < sum(first.taxes.values()) / 7000 < 0.40
    assert first.spending[LOAN_INTEREST]["haus"] == pytest.approx(50_000 * 0.024 / 12, rel=0.06)
    assert first.spending[LOAN_PRINCIPAL]["haus"] + first.spending[LOAN_INTEREST][
        "haus"
    ] == pytest.approx(500.0)
    assert first.spending["property upkeep"] == {"wohnung": pytest.approx(200.0)}
    # zero returns: only the term deposit grows, by its interest, and the employer pays into
    # the policy, and neither passes the cash
    assert set(first.noncash) == {"festgeld", "rente: employer"}
    assert first.noncash["rente: employer"] == pytest.approx(200.0)
    assert first.wealth_built == pytest.approx(
        first.surplus + first.spending[LOAN_PRINCIPAL]["haus"] + sum(first.noncash.values())
    )
    assert budget.from_ledger(r.ledger, range(12), oneoffs=True).noncash == first.noncash

    second = budget.from_ledger(r.ledger, range(12, 24))  # the event repaid the loan
    assert LOAN_INTEREST not in second.spending
    assert budget.ONEOFFS not in second.spending
    assert (
        "repayment: haus"
        in budget.from_ledger(r.ledger, range(12, 24), oneoffs=True).spending[budget.ONEOFFS]
    )

    third = budget.from_ledger(
        r.ledger, range(24, 36)
    )  # `alt`: no salary, the severance is a one-off
    assert "Gehalt" not in third.sources
    assert "severance: severance" not in third.sources
    # no salary and no bAV contribution in this phase, zero returns leave no growth, and the
    # severance part paid into the policy is a one-off: absent without `oneoffs`
    assert third.noncash == {}
    with_oneoffs = budget.from_ledger(r.ledger, range(24, 36), oneoffs=True)
    # the part paid into the policy is a one-off too, but no cash
    assert with_oneoffs.sources["severance: severance"] == pytest.approx(88_000 / 12)
    assert with_oneoffs.noncash == {"rente: severance": pytest.approx(12_000 / 12)}
    # the tax on the one-offs is a tax, the one-offs group keeps the moves
    oneoff_tax = sum(v for k, v in with_oneoffs.taxes.items() if k.startswith("tax on one-offs"))
    assert oneoff_tax > 0
    assert not any(k.startswith("tax on") for k in third.taxes)
    gain = {line: with_oneoffs.totals[line] - v for line, v in third.totals.items()}
    assert gain["taxes"] == pytest.approx(-oneoff_tax)  # what goes out is below zero
    assert gain["non-cash income"] == pytest.approx(12_000 / 12)
    assert gain["spending"] == pytest.approx(-sum(with_oneoffs.spending[budget.ONEOFFS].values()))
    assert set(with_oneoffs.spending[budget.ONEOFFS]) == {"policy premium: basis"}


def test_a_purchase_is_a_one_off_its_transfer_tax_a_tax_its_costs_a_spending() -> None:
    """Of the net worth only the Grunderwerbsteuer and the costs go: the price moves into the
    property, the loan into the cash."""
    buy = {"at": date(2026, 2, 1), "type": "buy_property", "property": {"id": "home"}}
    buy |= {"price": 300_000, "land": "NI", "costs": 0.02}
    buy |= {"loan": {"id": "l", "name": "Home loan", "balance": -200_000, "rate": 0, "annuity": 1}}
    bought = plan([], [cash(200_000)], Scenario.model_validate({"name": "s", "events": [buy]}))
    r = zero_run(bought, 2)
    assert r.ledger is not None
    month = budget.from_ledger(r.ledger, [1], oneoffs=True)
    assert month.taxes == {"tax on one-offs: home: transfer tax": 15_000}
    assert month.spending[budget.ONEOFFS] == {
        "purchase: home": 300_000,
        "purchase costs: home": 6000,
    }
    assert month.sources == {"loan: Home loan": 200_000}
    assert month.assets == {"purchase: home": 300_000, "loan: Home loan": -200_000}
    assert month.wealth_built == pytest.approx(-21_000)
    assert budget.from_ledger(r.ledger, [1]) == Budget()


def test_ahead_takes_the_first_months_of_each_phase_from_a_date() -> None:
    r = _run()
    assert budget.ahead(r, date(2026, 3, 31)) == {
        "work": list(range(2, 14)),
        "alt": list(range(24, 36)),
    }
    assert budget.ahead(r, date(2027, 7, 1), count=3) == {"work": [18, 19, 20], "alt": [24, 25, 26]}
    assert budget.ahead(r, date(2028, 2, 1)) == {"alt": list(range(25, 36))}  # work never again
    assert budget.ahead(r, date(2030, 1, 1)) == {}


def test_beyond_streams_keeps_what_no_stream_pays() -> None:
    p = _plan()
    side_job = Stream(name="Nebenjob", kind=StreamKind.OTHER_INCOME, amount=1000)
    events = [
        *p.scenario.events,
        AddStreamEvent(at=date(2028, 1, 1), type="add_stream", stream=side_job),
    ]
    vl = Stream(name="VL", kind=StreamKind.OTHER_INCOME, amount=35, index=None, repays="haus")
    p = p.model_copy(
        update={
            "scenario": p.scenario.model_copy(update={"events": events}),
            "streams": [*p.streams, vl],
        }
    )
    r = _run(p)
    assert r.ledger is not None
    beyond = budget.beyond_streams(r, p, date(2026, 1, 1))
    # the VL pays into the loan: its principal stays, booked with the loan's own
    assert set(beyond["work"].spending[LOAN_PRINCIPAL]) == {"haus"}
    full = budget.from_ledger(r.ledger, range(12), run_rate=True)
    assert beyond["work"].sources == {"PKV subsidy": full.sources["PKV subsidy"]}
    assert beyond["work"].taxes == full.taxes
    assert beyond["work"].spending == {  # the loan and the upkeep, not the streams
        group: items
        for group, items in full.spending.items()
        if group not in {"versicherung", "wohnen"}
    }
    assert {LOAN_INTEREST, LOAN_PRINCIPAL, "property upkeep"} <= set(beyond["work"].spending)
    assert "Nebenjob" in budget.from_ledger(r.ledger, range(24, 36)).sources
    assert "Nebenjob" not in beyond["alt"].sources  # an added stream is a stream too
    assert beyond["work"].lines[budget.TAXES] == -sum(full.taxes.values())


def test_a_tax_that_pays_back_is_a_source() -> None:
    r = _run()
    assert r.ledger is not None
    r.ledger.add((TAX, "", "income tax"), range(24, 36), -12 * 300.0)
    third = budget.from_ledger(r.ledger, range(24, 36))
    assert third.sources["income tax refund"] > 0
    assert "income tax" not in third.taxes


def test_stretches_split_a_phase_that_occurs_twice() -> None:
    r = _run()
    [work, alt] = budget.stretches(r)
    assert (work.label, work.key, work.months[0], alt.label) == (
        "Work",
        ("work", 0),
        0,
        "Career break",
    )
    twice = replace(r, phases=["work"] * 12 + ["alt"] * 12 + ["work"] * (len(r.phases) - 24))
    labels = [(s.label, s.key) for s in budget.stretches(twice)]
    assert labels == [
        ("Work 2026–2026", ("work", 0)),
        ("Career break", ("alt", 0)),
        ("Work 2028–2028", ("work", 1)),
    ]


def _half_year() -> RunResult:
    """Work from January to June 2026 with a yearly bonus of 12,000 in June, then no income."""
    scenario = Scenario(
        name="h", phases=phases((date(2026, 1, 1), "work"), (date(2026, 7, 1), "alt"))
    )
    salary = {"kind": StreamKind.SALARY, "phases": ["work"], "index": None}
    streams = [
        Stream.model_validate({"name": "salary", "gross": 5000} | salary),
        Stream.model_validate(
            {"name": "bonus", "of": "salary", "share": 0.2, "every": 12}
            | {"start": date(2026, 6, 1)}
            | salary
        ),
    ]
    return zero_run(plan(streams, [cash(100_000)], scenario), 12)


def test_the_run_rate_spreads_a_bonus_over_the_months_that_earn_it() -> None:
    ledger = _half_year().ledger
    assert ledger is not None
    work = range(6)
    assert budget.from_ledger(ledger, work).sources["bonus"] == pytest.approx(2000)
    assert budget.from_ledger(ledger, work, run_rate=True).sources["bonus"] == pytest.approx(1000)


def test_the_settlement_lands_in_the_months_that_earn() -> None:
    ledger = _half_year().ledger
    assert ledger is not None
    income_tax = ledger.entries[TAX, "", "income tax"]
    assert (income_tax[6:] == 0).all()
    assert income_tax[:6].sum() > 0
