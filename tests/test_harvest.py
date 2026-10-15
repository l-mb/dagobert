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


def depot(value: float = 100_000, basis: float = 50_000) -> EquityAsset:
    """An equity fund at a Teilfreistellung of 30%."""
    return EquityAsset(id="d", kind="equity", value=value, cost_basis=basis)


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
        ([Stream(name="shop", kind=StreamKind.SELF_EMPLOYED, amount=-500, index=None)], [], [], {}),
        ([], [], [], {"loss_carryforward": 20_000}),
    ],
    ids=["salary", "severance", "bav lump sum", "business loss", "verlustvortrag"],
)
def test_without_tariff_room_the_harvest_takes_the_pauschbetrag(
    streams: list[Stream], assets: list[object], events: list[object], tax: dict[str, object]
) -> None:
    """A zvE above the Grundfreibetrag, a Fünftelregelung (a bAV lump sum takes it by
    `fuenftel`), a Verlustvortrag left, also of a loss of the year: the Pauschbetrag only."""
    pair = runs(
        *streams,
        assets=[cash(10_000), depot(), *assets],
        scenario=Scenario.model_validate({"name": "t", "events": events}),
        tax=tax,
    )
    assert harvested(pair) == pytest.approx(1000)


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


def test_a_carried_capital_loss_waits_for_a_sale() -> None:
    """Fixed income loses 2% a month in 2026: the loss pot (§20 Abs. 6 EStG) would come off a
    harvest first, so none. A car in 2027 sells equity whose gain uses the pot up: that December
    harvests again."""
    returns = zero_returns(24)
    returns.rates["fixed_income"][:, :12] = -0.02
    bucket = FixedIncomeAsset(id="f", kind="fixed_income", value=20_000)
    car = LumpSumEvent(at=date(2027, 3, 1), type="lump_sum", amount=-60_000)
    pair = runs(
        assets=[cash(10_000), depot(), bucket],
        scenario=Scenario(name="t", events=[car]),
        returns=returns,
    )
    assert harvested(pair, 11) == 0
    assert harvested(pair, 23) > 0


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
