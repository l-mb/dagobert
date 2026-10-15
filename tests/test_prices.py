"""Price files: one row per date, imported or typed in, the valuation of the lots and its
record, gold and Bitcoin at their series, and the checks that catch a decimal mark in the wrong
place."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml
from builders import FakeGet, plan
from typer.testing import CliRunner

from dagobert import prices, revisions, series
from dagobert.cli import app
from dagobert.history import Observation, read_history
from dagobert.lots import Lot
from dagobert.model.assets import Trade
from dagobert.model.months import add_months
from dagobert.money import format_eur
from dagobert.ui import pricing, snapshot
from dagobert.ui.tradeform import CODE

ISIN = "IE00B4L5Y983"
SOLD = "IE00B5BMR087"
BUY = {"date": "2020-01-01", "kind": "buy", "units": 3, "amount": 24}
DEPOT = {"id": "d", "kind": "equity", "value": 1.0, "trades": [BUY | {"security": ISIN}]}


def _prices(data_dir: Path, text: str) -> None:
    path = prices.price_file(data_dir, ISIN)
    path.parent.mkdir()
    path.write_text("date,close\n" + text)


def test_merge_keeps_one_price_per_date_and_the_new_one_wins() -> None:
    old = [(date(2026, 9, 16), 9.5), (date(2026, 9, 18), 10.0)]
    new = [(date(2026, 9, 17), 9.8), (date(2026, 9, 16), 9.6), (date(2026, 9, 18), 10.0)]
    rows, replaced = prices.merge(old, new)
    assert rows == [(date(2026, 9, 16), 9.6), (date(2026, 9, 17), 9.8), (date(2026, 9, 18), 10.0)]
    assert replaced == [prices.Replaced(date(2026, 9, 16), 9.5, 9.6)]  # an equal price stays


def _save(data: Path, *points: prices.Price, security: str = ISIN) -> prices.Saved:
    return prices.save(data, security, list(points), source="test")


def test_save_writes_the_merged_file(data: Path) -> None:
    _save(data, (date(2026, 9, 17), 1234.5678))
    assert _save(data, (date(2026, 9, 16), 9.0), (date(2026, 9, 17), 9.5)).replaced == [
        prices.Replaced(date(2026, 9, 17), 1234.5678, 9.5)
    ]
    _save(data, (date(2026, 9, 18), 1234.5678))
    assert prices.price_file(data, ISIN).read_text().splitlines() == [
        "date,close",
        "2026-09-16,9",
        "2026-09-17,9.5",
        "2026-09-18,1234.5678",  # all digits of a price
    ]


@pytest.mark.parametrize("security", ["../assets", "", "ie00b4l5y983", "IE00B4L5Y98", "X"])
def test_a_price_file_is_named_by_a_security(data: Path, security: str) -> None:
    _save(data, (date(2026, 9, 17), 3800.0), security="XAU")  # a symbol of gold or crypto
    with pytest.raises(ValueError, match="is no security"):
        _save(data, (date(2026, 9, 17), 1.0), security=security)


def test_securities_list_the_held_ones_first(data: Path) -> None:
    trade = {"date": "2020-01-01", "kind": "buy", "units": 1, "amount": 1}
    (data / "assets.yaml").write_text(
        yaml.safe_dump(
            {
                "assets": [
                    {
                        "id": "depot",
                        "kind": "equity",
                        "value": 1,
                        "trades": [
                            trade | {"security": SOLD, "name": "A sold"},
                            trade | {"security": ISIN, "name": "World"},
                            trade | {"date": "2021-01-01", "kind": "sell", "security": SOLD},
                        ],
                    },
                    {"id": "mm", "kind": "fixed_income", "value": 1}
                    | {"trades": [trade | {"security": "LU0274208692"}]},
                ]
            }
        )
    )
    (data / "prices").mkdir()
    for name in ("DE0005933931", "notes"):
        (data / "prices" / f"{name}.csv").write_text("date,close\n")
    found = prices.Securities.of(data)
    assert found.names == {
        "LU0274208692": "LU0274208692",
        ISIN: "World",
        SOLD: "A sold",
        "DE0005933931": "DE0005933931",
    }
    assert found.units == {ISIN: 1, "LU0274208692": 1}
    assert [t.kind for t in found.trades[SOLD]] == ["buy", "sell"]
    # the table of the prices: the held ones, then a history imported before its trades, not the
    # security sold in full
    rows = {row[CODE]: row["security"] for row in pricing.stored(data, found)}
    assert rows == {
        "LU0274208692": "LU0274208692",
        ISIN: "World",
        "DE0005933931": "DE0005933931 (no trades)",
    }


def test_market_value_needs_every_price(tmp_path: Path) -> None:
    _prices(tmp_path, "2026-09-16,9.5\n2026-09-17,10\n")
    lot = Lot(ISIN, "World", date(2020, 1, 1), 3, 8.0)
    assert prices.market_value(tmp_path, [lot]) == (30.0, date(2026, 9, 17))
    assert prices.market_value(tmp_path, [lot, replace(lot, security=SOLD)]) is None
    assert prices.market_value(tmp_path, []) is None

    day, empty = date(2026, 9, 18), plan([], [])
    assert snapshot.estimate(tmp_path, DEPOT, day, empty).value == 30.0
    money = DEPOT | {"kind": "fixed_income"}
    assert snapshot.estimate(tmp_path, money, day, empty).value == 30.0
    assert snapshot.estimate(tmp_path, money | {"trades": []}, day, empty).value is None


def test_a_save_records_the_market_value(data: Path) -> None:
    newer = DEPOT | {"id": "n", "asof": date(2026, 9, 18)}  # the bank showed a later value
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT, newer]}))

    saved = _save(data, (date(2026, 9, 16), 9.5), (date(2026, 9, 17), 10.0))
    assert saved.recorded == [(date(2026, 9, 17), "d", 30.0)]
    assert _save(data, (date(2026, 9, 17), 10.0)).recorded == []  # no new price, no observation
    assert [e.files for e in revisions.entries(data)[1:]] == [  # one revision per save
        ("assets.yaml", "history.csv", f"prices/{ISIN}.csv")
    ]
    rows = yaml.safe_load((data / "assets.yaml").read_text())["assets"]
    assert [(r["value"], r["asof"]) for r in rows] == [
        (30.0, date(2026, 9, 17)),
        (1.0, date(2026, 9, 18)),
    ]
    assert read_history(data) == [(date(2026, 9, 17), "d", 30.0)]


def test_only_a_newer_price_records_a_value(data: Path) -> None:
    """A past price leaves the last price, so the recorded value stays."""
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    _save(data, (date(2026, 9, 17), 10.0))

    assert _save(data, (date(2026, 9, 1), 9.0)).recorded == []
    assert _save(data, (date(2026, 9, 18), 11.0)).recorded == [(date(2026, 9, 18), "d", 33.0)]
    [row] = yaml.safe_load((data / "assets.yaml").read_text())["assets"]
    assert (row["value"], row["asof"]) == (33.0, date(2026, 9, 18))


def test_a_corrected_price_of_the_asof_day_records_again(data: Path) -> None:
    """A typo in the last price is recorded at once; its correction replaces that value. A
    record without a corrected price keeps a value of that day, which the bank may have shown."""
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    assert _save(data, (date(2026, 9, 17), 1101.5)).recorded == [(date(2026, 9, 17), "d", 3304.5)]

    assert _save(data, (date(2026, 9, 16), 1100.0)).recorded == []  # not the last price
    _save(data, (date(2026, 9, 17), 5.0), security=SOLD)
    assert _save(data, (date(2026, 9, 17), 6.0), security=SOLD).recorded == []  # not held
    assert _save(data, (date(2026, 9, 17), 110.15)).recorded == [(date(2026, 9, 17), "d", 330.45)]
    [row] = yaml.safe_load((data / "assets.yaml").read_text())["assets"]
    assert (row["value"], row["asof"]) == (330.45, date(2026, 9, 17))


def test_a_history_row_counts_the_lots_held_on_its_date(data: Path) -> None:
    """The row takes the date of the oldest price: a lot bought later does not count, a lot sold
    since does."""
    trades = [
        BUY | {"security": ISIN},
        BUY | {"security": ISIN, "date": "2026-09-18", "kind": "sell", "units": 1, "amount": 10},
        BUY | {"security": SOLD, "date": "2026-09-19", "units": 2, "amount": 12},
    ]
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT | {"trades": trades}]}))
    assert _save(data, (date(2026, 9, 20), 6.0), security=SOLD).recorded == []  # no price of ISIN
    assert _save(data, (date(2026, 9, 17), 10.0)).recorded == [(date(2026, 9, 17), "d", 30.0)]
    assert read_history(data) == [(date(2026, 9, 17), "d", 30.0)]  # 3 units, not 2 and 2 more


def _dated(data_dir: Path, name: str) -> prices.Price:
    """The last month of a series in euros, on its last day, a provisional one on its first."""
    last = series.in_euros(series.SERIES[name], data_dir)[-1]
    end = add_months(last.month, 1) - timedelta(days=1)
    return (last.month if last.provisional else end, last.value)


def test_gold_and_bitcoin_take_their_series_when_it_is_newer(data: Path) -> None:
    """A final month is dated on its last day, a provisional one on its first. A typed price wins
    from the day of the series on."""
    assert prices.last_price(data, "XAU") == _dated(data, "gold")
    assert prices.last_price(data, "BTC") is None  # not fetched
    assert prices.last_price(data, ISIN) is None

    btc = [series.Point(date(2026, 8, 1), 90_000.0), series.Point(date(2026, 9, 1), 100_000.0)]
    series.save(series.SERIES["bitcoin"], data, btc)
    assert prices.last_price(data, "BTC") == (date(2026, 9, 30), _dated(data, "bitcoin")[1])
    provisional = series.Point(date(2026, 10, 1), 1.0, provisional=True)
    series.save(series.SERIES["bitcoin"], data, [*btc, provisional])
    assert prices.last_price(data, "BTC") == (date(2026, 10, 1), _dated(data, "bitcoin")[1])

    day, gold = _dated(data, "gold")
    _save(data, (day - timedelta(days=1), 3800.0), security="XAU")
    assert prices.last_price(data, "XAU") == (day, gold)
    _save(data, (day, 3800.0), security="XAU")
    assert prices.last_price(data, "XAU") == (day, 3800.0)


def test_a_save_records_gold_at_its_series(data: Path) -> None:
    """Coins of `XAU` count troy ounces at the gold series in euros: a save of any price records
    them, the Snapshot estimates them, and the price table names the series."""
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("  gold: {mean: 0.04}\n")
    coins = BUY | {"security": "XAU", "units": 2.5, "amount": 4000, "name": "Coins"}
    gold = {"id": "g", "kind": "gold", "value": 1.0, "trades": [coins]}
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT, gold]}))
    day, price = _dated(data, "gold")

    saved = _save(data, (date(2026, 9, 17), 10.0))
    assert saved.recorded == [(date(2026, 9, 17), "d", 30.0), (day, "g", round(2.5 * price, 2))]
    assert snapshot.estimate(data, gold, day, plan([], [])).value == round(2.5 * price, 2)
    _save(data, (day - timedelta(days=1), 3800.0), security="XAU")  # older than the series
    rows = {row[CODE]: row for row in pricing.stored(data, prices.Securities.of(data))}
    assert rows["XAU"] == {
        "security": "Coins",
        "last price": f"{day} (gold series)",
        "price": format_eur(price, cents=True),
        "prices": 1,
        CODE: "XAU",
    }


def _answers(*bodies: tuple[str, str]) -> FakeGet:
    """A getter that sends the answers in turn, each as content type and body."""
    return FakeGet([series.Response(200, kind, body.encode()) for kind, body in bodies])


def _coins(day: str, usd: float) -> tuple[str, str]:
    data = [{"asset": "btc", "time": f"{day}T00:00:00.000000000Z", "PriceUSD": str(usd)}]
    return "application/json", json.dumps({"data": data})


def test_a_fetch_records_bitcoin_when_its_price_in_euros_changes(data: Path) -> None:
    """A new month of Bitcoin or of the dollar rate records the wallet as a revision of its own,
    dated on the first day of a provisional month: the coins bought after it do not count. The
    same month again with a new close or rate records again; a fetch without news, nothing."""
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("  bitcoin: {mean: 0.1}\n")
    coins = [BUY | {"security": "BTC", "units": 0.5, "amount": 4000}]
    coins.append(coins[0] | {"date": "2026-10-05", "units": 0.25, "amount": 25_000})
    wallet = {"id": "w", "kind": "crypto", "value": 1.0, "trades": coins}
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [wallet]}))
    bitcoin, rates = series.SERIES["bitcoin"], series.SERIES["usd-eur"]
    october = _coins("2026-10-06", 110_000.0)

    def fetch(entry: series.Series, *answers: tuple[str, str]) -> prices.Fetched:
        return prices.fetch_series(entry, data, _answers(*answers), source="test")

    def worth() -> list[Observation]:
        day, price = _dated(data, "bitcoin")
        assert day == date(2026, 10, 1)  # provisional
        return [(day, "w", round(0.5 * price, 2))]

    assert fetch(bitcoin, october).recorded == worth()
    ecb = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
    rate = ("text/csv", ecb + "EXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,2026-10,1.2\n")
    assert fetch(rates, rate).recorded == worth()
    assert fetch(bitcoin, _coins("2026-10-07", 120_000.0)).recorded == worth()
    assert fetch(bitcoin, _coins("2026-10-07", 120_000.0)).recorded == []
    assert [(e.source, e.files) for e in revisions.entries(data)[1:]] == 3 * [
        ("test", ("assets.yaml", "history.csv"))
    ]
    [row] = yaml.safe_load((data / "assets.yaml").read_text())["assets"]
    assert [(row["asof"], "w", row["value"])] == worth()


def test_a_price_far_from_a_trade_nearby_warns() -> None:
    """A decimal mark in the wrong place shows as a factor of 100 against the price paid."""
    buy = Trade.model_validate(BUY | {"security": ISIN, "date": "2024-03-01", "amount": 240.36})
    assert prices.off_trades([buy], [(date(2024, 3, 1), 80.0), (date(2024, 3, 4), 0.8)]) == []
    assert prices.off_trades([buy], [(date(2024, 3, 4), 0.8012), (date(2024, 2, 1), 80.0)]) == [
        "0,80 € on 2024-03-04, the buy of 2024-03-01 paid 80,12 € per unit"
    ]
    assert prices.off_trades([buy], [(date(2024, 3, 7), 0.8)]) == []  # no price within 5 days


def test_a_trade_of_gold_far_from_its_series_warns(data: Path) -> None:
    """Grams typed as troy ounces: one ounce bought as `GRAMS_PER_TROY_OUNCE` units. A trade after
    the last month of the series takes that month, up to `Symbol.lag` months; Bitcoin needs its
    fetch."""
    last = series.in_euros(series.SERIES["gold"], data)[-1]
    ounce = Trade.model_validate(
        BUY | {"security": "XAU", "date": last.month, "units": 1, "amount": last.value}
    )
    grams = ounce.model_copy(update={"units": prices.GRAMS_PER_TROY_OUNCE})
    later = grams.model_copy(update={"date": add_months(last.month, prices.BY_SYMBOL["XAU"].lag)})
    assert prices.off_series(data, [ounce, ounce.model_copy(update={"security": "BTC"})]) == []
    [far] = prices.off_series(
        data, [grams, later.model_copy(update={"date": add_months(later.date, 1)})]
    )
    paid = format_eur(last.value / prices.GRAMS_PER_TROY_OUNCE, cents=True)
    assert far.startswith(f"the buy of {last.month} paid {paid}")
    assert far.endswith(
        f"the gold series {format_eur(last.value, cents=True)} per troy ounce in {last.month:%Y-%m}"
    )
    assert len(prices.off_series(data, [later])) == 1


@pytest.mark.parametrize(("factor", "warns"), [(2.5, False), (0.3, False), (1000, True)])
def test_bitcoin_warns_only_of_a_slip_of_the_unit(data: Path, factor: float, warns: bool) -> None:
    """Bitcoin doubled within months, so a price far from its month is real; one that is 1,000
    times off is a slip, such as mBTC typed as bitcoins."""
    series.save(series.SERIES["bitcoin"], data, [series.Point(date(2026, 8, 1), 90_000.0)])
    [month] = series.in_euros(series.SERIES["bitcoin"], data)
    buy = BUY | {"security": "BTC", "date": "2026-09-14", "units": 1}
    trade = Trade.model_validate(buy | {"amount": round(month.value * factor, 2)})
    assert bool(prices.off_series(data, [trade])) is warns


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (pricing.TypedPrice(" ie00b4l5y983", date(2026, 9, 1), "80,12"), 80.12),
        (pricing.TypedPrice(ISIN, date(2026, 9, 1), "5432"), 5432.0),
        (pricing.TypedPrice(ISIN, date(2026, 9, 1), "5,4320"), 5.432),
        (pricing.TypedPrice(ISIN, date(2026, 9, 1), "5.432"), "price 5.432: type 5432 for whole"),
        (pricing.TypedPrice(ISIN, date(2026, 9, 1), "0"), "type a number above zero"),
        (pricing.TypedPrice(ISIN, date(2026, 9, 1), "-1"), "type a number above zero"),
        (pricing.TypedPrice("", date(2026, 9, 1), "1"), "choose a security"),
        (pricing.TypedPrice(ISIN, None, "1"), "choose a date"),
        (pricing.TypedPrice(ISIN, date(2026, 10, 1), "1"), "choose a date up to today"),
        (pricing.TypedPrice(" xau", date(2026, 9, 1), "3800"), 3800.0),  # a symbol of gold
    ],
)
def test_a_typed_price_takes_no_thousands_groups(
    typed: pricing.TypedPrice, expected: float | str
) -> None:
    if isinstance(expected, str):
        with pytest.raises(ValueError, match=expected):
            typed.point(date(2026, 9, 30))
    else:
        security = typed.security.strip().upper()
        assert typed.point(date(2026, 9, 30)) == (security, (date(2026, 9, 1), expected))


def test_the_command_imports_and_records(data: Path, tmp_path: Path) -> None:
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    download = tmp_path / "download.csv"
    download.write_text("Datum;Schluss\n17.09.2026;10,00\n18.09.2026;11,00\n01.01.2999;12,00\n")
    args = ["prices", "import", ISIN, str(download), "--data", str(data)]

    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "date Datum (dmy), value Schluss, decimal comma" in result.output
    assert "line 4: 2999-01-01 is in the future" in result.output
    assert "d: 33 € as of 2026-09-18" in result.output
    assert prices.last_price(data, ISIN) == (date(2026, 9, 18), 11.0)

    result = CliRunner().invoke(app, [*args, "--decimal", "."])  # 10,00 does not read
    assert result.exit_code == 1
    assert "no value read" in result.output


def test_the_command_stops_at_a_price_far_off_unless_forced(data: Path, tmp_path: Path) -> None:
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    _save(data, (date(2026, 9, 18), 11.0))
    download = tmp_path / "download.csv"
    download.write_text("Date,Close\n2026-09-18,1100\n")  # the decimal mark got lost
    args = ["prices", "import", ISIN, str(download), "--data", str(data)]

    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "Check: 1.100,00 € on 2026-09-18 replaces 11,00 €" in result.output
    assert prices.last_price(data, ISIN) == (date(2026, 9, 18), 11.0)

    result = CliRunner().invoke(app, [*args, "--force"])
    assert result.exit_code == 0, result.output
    assert "d: 3.300 € as of 2026-09-18" in result.output  # a corrected last price records


def test_the_command_needs_the_file(data: Path) -> None:
    result = CliRunner().invoke(app, ["prices", "import", ISIN, str(data / "none.csv")])
    assert result.exit_code == 2  # a usage error, no traceback
    assert "does not exist" in result.output


@pytest.mark.parametrize("row", ["18.09.2026,11", "2026-09-18"])
def test_a_price_file_edited_by_hand_names_the_line_that_does_not_read(
    data: Path, tmp_path: Path, row: str
) -> None:
    _prices(data, f"2026-09-17,10\n{row}\n")
    download = tmp_path / "download.csv"
    download.write_text("Date,Close\n2026-09-18,11\n")
    result = CliRunner().invoke(app, ["prices", "import", ISIN, str(download), "--data", str(data)])
    assert result.exit_code == 1  # an input error, no traceback
    assert f"prices/{ISIN}.csv:3: " in result.output  # `files.read_csv`


def test_a_record_that_failed_after_a_fetch_is_made_up_by_the_next_fetch(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wallet = {"id": "w", "kind": "crypto", "value": 1.0, "trades": [BUY | {"security": "BTC"}]}
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [wallet]}))
    answer = _coins("2026-10-06", 110_000.0)
    bitcoin = series.SERIES["bitcoin"]

    def broken(*_: object) -> None:
        raise revisions.BusyError("x")

    with monkeypatch.context() as patched:
        patched.setattr(prices, "record", broken)
        with pytest.raises(revisions.BusyError):
            prices.fetch_series(bitcoin, data, _answers(answer), source="test")
    assert prices.fetch_series(bitcoin, data, _answers(answer), source="test").recorded
