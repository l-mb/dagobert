"""The harvest (`tax.harvest`): each December the equity whose gain fits the tax-free room of the
year is sold and bought back at once. Relations between the runs with and without it; the room in
amounts in `test_tax.py`, the cap of a voluntary GKV member in `test_health.py`."""

from datetime import date

import numpy as np
import pytest
from builders import cash, harvested, marked, phases, plan, zero_returns

from dagobert.engine.simulation import simulate
from dagobert.model.assets import EquityAsset, FixedIncomeAsset, PensionPolicy
from dagobert.model.events import LumpSumEvent, SeveranceEvent
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import Land
from dagobert.result import RunResult
from dagobert.returns import Returns
from dagobert.tax import flat_rate, for_year

TY = for_year(2026)
RATE = flat_rate(0.0, TY)
# at a zvE of 0: the Grundfreibetrag, the Sonderausgaben- (§10c) and the Sparer-Pauschbetrag
ROOM = TY.grundfreibetrag + TY.sonderausgaben_pauschbetrag + 1000
SALARY = Stream(name="pay", kind=StreamKind.SALARY, gross=3000, index=None)
SHOP = Stream(name="shop", kind=StreamKind.SELF_EMPLOYED, amount=-500, index=None)
CAR = LumpSumEvent(at=date(2027, 3, 1), type="lump_sum", amount=-60_000)


def depot(value: float = 100_000, basis: float = 50_000) -> EquityAsset:
    """An equity fund at a Teilfreistellung of 30%."""
    return EquityAsset(id="d", kind="equity", value=value, cost_basis=basis)


def taxes(r: RunResult) -> float:
    """The income tax, the SV and the capital tax of the run and the latent tax at its end, below
    zero."""
    return float(r.taxes.sum() + r.capital_taxes.sum() + r.nominal_balance["latent_tax"][-1])


def runs(
    *streams: Stream,
    assets: list[object] | None = None,
    scenario: Scenario | None = None,
    returns: Returns | None = None,
    tax: dict[str, object] | None = None,
) -> tuple[RunResult, RunResult]:
    """The runs with and without the harvest, by default of a year at zero returns, the cash kept
    as cash."""
    held = assets or [cash(10_000), depot()]
    on, off = (
        simulate(
            plan(
                list(streams), held, scenario, tax=(tax or {}) | {"harvest": h}, invest_rest=False
            ),
            returns or zero_returns(12),
            "fixed",
        )
        for h in (True, False)
    )
    return on, off


@pytest.mark.parametrize("church", [False, True])
def test_a_harvest_steps_up_the_basis_inside_the_tax_free_room(*, church: bool) -> None:
    """A year without income: the Grundfreibetrag, the Sonderausgaben- and the
    Sparer-Pauschbetrag, 13,384 € after the Teilfreistellung, a gain of 19,120 €. The cash and the
    equity stay, the flat tax on the part above the Pauschbetrag (27.99% with the church tax) comes
    back in the same December, and the liquid wealth rises by the latent tax saved."""
    tax = {"church": True, "land": "BE"} if church else {}
    rate = flat_rate(TY.kirchensteuer[Land.BE] if church else 0.0, TY)
    pair = on, off = runs(tax=tax)
    assert harvested(pair, rate=rate) == pytest.approx(ROOM)
    for kind in ("cash", "equity"):
        assert on.nominal_balance[kind] == pytest.approx(off.nominal_balance[kind])
    assert on.capital_taxes == pytest.approx(off.capital_taxes)
    assert on.liquid[0, 11] - off.liquid[0, 11] == pytest.approx(ROOM * rate)
    assert marked(on)[-1] == "2026-12 harvest: 19.120 €"


def test_a_later_sale_pays_less_tax() -> None:
    """A salary from 2027 and a car that sells the depot: the gain stepped up in 2026 is free."""
    car = LumpSumEvent(at=date(2027, 6, 1), type="lump_sum", amount=-80_000)
    pay = SALARY.model_copy(update={"start": date(2027, 1, 1)})
    on, off = runs(pay, returns=zero_returns(24), scenario=Scenario(name="t", events=[car]))
    assert on.capital_taxes.sum() > off.capital_taxes.sum()  # below zero: less tax
    assert on.liquid[0, -1] > off.liquid[0, -1]


def test_a_year_whose_sales_used_the_room_harvests_nothing() -> None:
    """Spending sells 36,000 € of equity at a gain of 80%: 20,160 € after the
    Teilfreistellung, beyond the room."""
    spend = Stream(name="life", cat="base", amount=-3000, index=None)
    on, off = runs(spend, assets=[cash(), depot(500_000, 100_000)])
    assert on.liquid == pytest.approx(off.liquid)


@pytest.mark.parametrize(
    ("streams", "assets", "events", "tax"),
    [
        ([SALARY], [], [], {}),
        ([], [], [SeveranceEvent(at=date(2026, 6, 1), type="severance", gross=10_000)], {}),
        (
            [],
            [
                PensionPolicy.model_validate(
                    {"id": "bav", "kind": "bav", "value": 10_000, "growth": "cash"}
                    | {"contribution": 0, "phases": [], "matures": date(2026, 6, 1)}
                )
            ],
            [],
            {},
        ),
        ([], [], [], {"loss_carryforward": 20_000}),
    ],
    ids=["salary", "severance", "bav lump sum", "verlustvortrag"],
)
def test_without_tariff_room_the_harvest_takes_the_pauschbetrag(
    streams: list[Stream], assets: list[object], events: list[object], tax: dict[str, object]
) -> None:
    """A zvE above the Grundfreibetrag, a Fünftelregelung (a bAV lump sum takes it by
    `fuenftel`), a Verlustvortrag beyond the tariff room: the Pauschbetrag only."""
    pair = runs(
        *streams,
        assets=[cash(10_000), depot(), *assets],
        scenario=Scenario.model_validate({"name": "t", "events": events}),
        tax=tax,
    )
    assert harvested(pair) == pytest.approx(1000)


def test_a_loss_of_the_year_closes_the_tariff_room_only_with_a_year_to_go_back_to() -> None:
    """§10d Abs. 1 EStG: a business loss of 2027 may go back into the salary of 2026, and a harvest
    would shrink what it refunds: 2027 takes the Pauschbetrag only, as 2026 with its salary. In
    the first year of a run the loss goes forward only: the harvest takes it along as a
    Verlustvortrag."""
    pay = SALARY.model_copy(update={"end": date(2027, 1, 1)})
    shop = SHOP.model_copy(update={"start": date(2027, 1, 1)})
    assert harvested(runs(pay, shop, returns=zero_returns(24)), 23) == pytest.approx(2000)
    assert harvested(runs(SHOP)) > 1000


def test_a_harvest_keeps_the_verlustvortrag() -> None:
    """20,000 € carried from before the start offset the salary of 2027 alike."""
    pay = SALARY.model_copy(update={"start": date(2027, 1, 1)})
    on, off = runs(pay, returns=zero_returns(24), tax={"loss_carryforward": 20_000})
    assert on.taxes == pytest.approx(off.taxes)


def test_alg1_takes_room_from_the_harvest() -> None:
    """Half a year of salary, then ALG1 against a career break: the Progressionsvorbehalt (§32b
    EStG) counts the ALG1 in the zvE that the Günstigerprüfung sees."""

    def harvest(phase: str) -> float:
        changes = phases((date(2026, 1, 1), "work"), (date(2026, 7, 1), phase))
        pay = SALARY.model_copy(update={"gross": 2000, "phases": ["work"]})
        alg1 = Stream(name="alg", kind=StreamKind.ALG1, phases=["unemployed"])
        return harvested(runs(pay, alg1, scenario=Scenario(name="t", phases=changes)))

    assert 1000 < harvest("unemployed") < harvest("alt") < ROOM


@pytest.mark.parametrize(
    ("rate", "tax", "pot"),
    [(-0.02, {}, 20_000 * (1 - 0.98**12)), (0.0, {"capital_losses": 4_000}, 4_000)],
    ids=["run", "start"],
)
def test_a_harvest_takes_a_capital_loss_pot_below_the_room_along(
    rate: float, tax: dict[str, object], pot: float
) -> None:
    """Fixed income loses 2% a month in 2026, or `tax.capital_losses` carries a loss to the
    start: the gain uses up the loss pot (§20 Abs. 6 EStG) first, and the room beyond it is
    larger, so the harvest steps up both. With a salary from 2027 and a car that sells equity the
    run pays less tax in all, paid and latent, than without the harvest."""
    returns = zero_returns(24)
    returns.rates["fixed_income"][:, :12] = rate
    bucket = FixedIncomeAsset(id="f", kind="fixed_income", value=20_000)
    pay = SALARY.model_copy(update={"start": date(2027, 1, 1)})
    pair = on, off = runs(
        pay,
        assets=[cash(10_000), depot(), bucket],
        scenario=Scenario(name="t", events=[CAR]),
        returns=returns,
        tax=tax,
    )
    assert harvested(pair, 11) == pytest.approx(pot + ROOM)
    assert taxes(on) > taxes(off)  # below zero: less tax


def test_a_capital_loss_pot_beyond_the_room_waits_for_a_sale() -> None:
    """A loss pot of 20,000 €: a harvest would use up more of it than it steps up beyond it, so
    none. A car in 2027 sells equity whose gain uses most of the pot: that December takes the rest
    along with the room."""
    pair = runs(
        returns=zero_returns(24),
        scenario=Scenario(name="t", events=[CAR]),
        tax={"capital_losses": 20_000},
    )
    assert harvested(pair, 11) == 0
    assert harvested(pair, 23) > ROOM


@pytest.mark.parametrize(
    ("streams", "tax", "pot"),
    [
        ([], {"loss_carryforward": 5_000}, 5_000),
        ([SHOP], {"loss_carryback": False}, 6_000),
    ],
    ids=["carried", "loss forward only"],
)
def test_a_verlustvortrag_below_the_tariff_room_goes_along(
    streams: list[Stream], tax: dict[str, object], pot: float
) -> None:
    """A Verlustvortrag (§10d Abs. 2 EStG), from before the start or a business loss of the year
    that goes forward only, comes off the gain before the tariff room, which is larger: the harvest
    takes it along."""
    assert harvested(runs(*streams, tax=tax)) == pytest.approx(pot + ROOM)


def test_a_harvest_that_takes_the_verlustvortrag_along_pays_less_tax_in_all() -> None:
    """5,000 € carried from before the start go with the harvest of 2026: the salary of 2027 pays
    more income tax, the stepped-up basis saves more flat tax, paid and latent."""
    pay = SALARY.model_copy(update={"start": date(2027, 1, 1)})
    on, off = runs(pay, returns=zero_returns(24), tax={"loss_carryforward": 5_000})
    assert on.taxes.sum() < off.taxes.sum()  # below zero: more tax
    assert taxes(on) > taxes(off)


def test_a_negative_zve_from_the_premiums_widens_the_room() -> None:
    """A PKV premium is a Sonderausgabe: a zvE below 0 that carries nothing (§10d Abs. 1)."""
    premium = Stream(name="pkv", cat="versicherung", amount=-500, index=None, health="kv")
    assert harvested(runs(premium)) > ROOM


def test_the_harvest_repeats_each_december_while_a_gain_is_left() -> None:
    """Two years without income step up twice the room, the second December finds the rest."""
    pair = runs(returns=zero_returns(24), assets=[cash(10_000), depot(100_000, 70_000)])
    assert harvested(pair, 11) == pytest.approx(ROOM)
    assert harvested(pair, 23) == pytest.approx(30_000 * 0.7)
    assert np.all(pair[0].liquid[0, 23:] >= pair[1].liquid[0, 23:])
