"""FIFO lots, the Vorabpauschale on them, and the money-weighted return."""

from __future__ import annotations

from datetime import date

import pytest

from dagobert import lots
from dagobert.lots import TradeKind
from dagobert.model.assets import Trade
from dagobert.returns import deflate

ISIN = "IE00B4L5Y983"


def _trade(
    day: date, kind: TradeKind, amount: float, units: float | None = None, **more: object
) -> Trade:
    return Trade.model_validate(
        {"date": day, "kind": kind, "security": ISIN, "units": units, "amount": amount} | more
    )


@pytest.mark.parametrize("security", [ISIN, "XAU"])  # gold and crypto go by a symbol
def test_a_sale_takes_the_oldest_units_first(security: str) -> None:
    book = lots.book(
        [
            _trade(date(2022, 5, 1), TradeKind.SELL, 150, 15, fees=1, security=security),
            _trade(date(2020, 1, 1), TradeKind.BUY, 40, 10, security=security),  # the order is free
            _trade(date(2021, 1, 1), TradeKind.BUY, 50, 10, fees=10, security=security),
        ]
    )
    [sale] = book.sales
    assert (sale.proceeds, sum(lot.cost for lot in sale.taken)) == (149, 40 + 5 * 6)
    assert [(lot.bought.year, lot.units) for lot in sale.taken] == [(2020, 10), (2021, 5)]
    assert book.open == [lots.Lot(security, security, date(2021, 1, 1), 5, 6.0)]


def test_the_vorabpauschale_spares_the_months_before_a_purchase() -> None:
    book = lots.book(
        [
            _trade(date(2022, 6, 1), TradeKind.BUY, 100, 10),
            _trade(date(2023, 4, 10), TradeKind.BUY, 100, 10),  # 9 of 12 months held
            _trade(date(2024, 1, 2), TradeKind.VORABPAUSCHALE, 35),
            _trade(date(2024, 1, 3), TradeKind.BUY, 100, 10),  # after the year
        ]
    )
    assert [lot.vp for lot in book.open] == [2.0, 1.5, 0.0]
    assert [lot.basis for lot in book.open] == [120, 115, 100]


def test_a_vorabpauschale_needs_units() -> None:
    with pytest.raises(ValueError, match="no units held in 2023"):
        lots.book([_trade(date(2024, 1, 2), TradeKind.VORABPAUSCHALE, 35)])


def test_flows_leave_out_the_tax() -> None:
    trades = [
        _trade(date(2020, 1, 1), TradeKind.BUY, 100, 10, fees=1),
        _trade(date(2021, 1, 4), TradeKind.VORABPAUSCHALE, 3),
        _trade(date(2022, 1, 1), TradeKind.SELL, 120, 10, fees=2),
    ]
    assert lots.flows(trades) == [(date(2020, 1, 1), -101), (date(2022, 1, 1), 118)]


def test_names_take_the_last_one_given() -> None:
    trades = [
        _trade(date(2021, 1, 1), TradeKind.BUY, 1, 1, name="Later"),
        _trade(date(2020, 1, 1), TradeKind.BUY, 1, 1, name="First"),
        _trade(date(2022, 1, 1), TradeKind.BUY, 1, 1),
    ]
    assert lots.names(trades) == {ISIN: "Later"}
    assert lots.book(trades).open[0].name == "Later"


def test_irr_and_its_real_twin() -> None:
    cash = [(date(2021, 1, 1), -100.0), (date(2022, 1, 1), 110.0)]
    assert lots.irr(cash) == pytest.approx(0.10)
    assert lots.irr([(date(2021, 1, 1), -100.0), (date(2022, 1, 1), -1.0)]) is None
    real = deflate(cash, lambda day: 100.0 if day.year == 2021 else 110.0, date(2022, 1, 1))
    assert real == [(date(2021, 1, 1), -110.0), (date(2022, 1, 1), 110.0)]
    assert lots.irr(real) == pytest.approx(0.0, abs=1e-9)
