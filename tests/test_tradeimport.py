"""The import of a broker export into the trades of an asset: the exports with a public
description map by their headers, rows of other kinds are left out, a row that the trades hold
already is left out once, and one that they cannot replay is refused with its line."""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest
from builders import ASSETS
from typer.testing import CliRunner

from dagobert import csvimport, prices, revisions, tradeimport
from dagobert.cli import app
from dagobert.loader import load_assets
from dagobert.model.assets import EquityAsset, GoldAsset, HoldingsAsset

WORLD, EM = "IE00B4L5Y983", "IE00BKM4GZ66"
TODAY = date(2026, 10, 13)
# made-up rows in the layouts that Portfolio Performance, Wealthfolio importers and the brokers
# describe: Scalable Capital lists the newest first, with a decimal comma
SCALABLE = f"""\
date;time;status;reference;description;assetType;type;isin;shares;price;amount;fee;tax;currency
2026-08-03;02:00:00;Executed;"W 2";"World (Acc)";Cash;Distribution;{WORLD};;;5,10;0,00;0,00;EUR
2026-08-01;14:11:01;Executed;"S 3";"World";Security;Sell;{WORLD};0,5;100,20;50,10;0,99;0,00;EUR
2026-08-01;14:06:16;Executed;"S 2";"World";Security;Savings plan;{WORLD};1,5;100;-150,004;0;0;EUR
2026-07-31;02:00:00;Executed;"D 1";"Broker";Cash;Deposit;;;;550,00;0,00;;EUR
2026-07-01;14:49:02;Cancelled;"S 1";"Markets";Security;Buy;{EM};3;31,63;-94,89;0,00;0,00;EUR
"""
TRADE_REPUBLIC = f"""\
"datetime","date","account_type","category","type","asset_class","name","symbol","shares",\
"price","amount","fee","tax","currency","description","transaction_id"
"2026-01-15T10:40:16.000Z","2026-01-15","DEFAULT","CASH","CUSTOMER_INBOUND","","Me","","","",\
"1000.00","","","EUR","","1"
"2026-01-20T11:35:34.000Z","2026-01-20","DEFAULT","TRADING","BUY","FUND","Markets","{EM}",\
"2.0000000000","100.00","-200.00","-1.00","","EUR","","2"
"2026-03-15T03:00:00.000Z","2026-03-15","DEFAULT","CASH","DIVIDEND","FUND","Markets","{EM}",\
"2.0000000000","","0.50","","","EUR","","3"
"2026-05-20T09:00:00.000Z","2026-05-20","DEFAULT","TRADING","SELL","FUND","Markets","{EM}",\
"-1.0000000000","110.00","110.00","-1.00","","EUR","","4"
"""
COMDIRECT = f"""\ufeffDatum;Art;Bezeichnung;WKN;ISIN;Menge;Mengeneinheit;Kurs;Kurswährung;\
Devisenkurs;Kurswert;Kurswertwährung
10.02.2026;Kauf;World;A0RPWH;{WORLD};2,5;Stück;98,51;USD;1,08;246,28;EUR
11.02.2026;Umbuchung (Eingang);World;A0RPWH;{WORLD};1;Stück;;EUR;;;EUR
"""


def _table(text: str) -> csvimport.Table:
    return csvimport.sniff(text.encode())


def _read(text: str) -> tradeimport.Parsed:
    table = _table(text)
    return tradeimport.read(table, tradeimport.guess(table), today=TODAY)


def _depot(*trades: Mapping[str, object]) -> EquityAsset:
    basis = {"trades": list(trades)} if trades else {"cost_basis": 0}
    return EquityAsset.model_validate({"id": "depot", "kind": "equity", "value": 1} | basis)


@pytest.mark.parametrize(
    ("text", "mapping", "rows", "skipped"),
    [
        pytest.param(
            SCALABLE,
            "date date (ymd), kind type, security isin, units shares, amount amount, fees fee, "
            "name description, currency currency, status status, decimal comma",
            [  # the newest first: read backwards, so the sale follows the buy of its day
                (4, "2026-08-01", "buy", WORLD, 1.5, 150, None),
                (3, "2026-08-01", "sell", WORLD, 0.5, 50.1, 0.99),
            ],
            {"Distribution": 1, "Deposit": 1, "status Cancelled": 1},
            id="scalable",
        ),
        pytest.param(
            TRADE_REPUBLIC,
            "date date (ymd), kind type, security symbol, units shares, amount amount, fees fee, "
            "name name, currency currency, status none, decimal point",
            [
                (3, "2026-01-20", "buy", EM, 2, 200, 1),
                (5, "2026-05-20", "sell", EM, 1, 110, 1),
            ],
            {"CUSTOMER_INBOUND": 1, "DIVIDEND": 1},
            id="trade-republic",
        ),
        pytest.param(  # the currency of the amount, not that of the price
            COMDIRECT,
            "date Datum (dmy), kind Art, security ISIN, units Menge, amount Kurswert, fees none, "
            "name Bezeichnung, currency Kurswertwährung, status none, decimal comma",
            [(2, "2026-02-10", "buy", WORLD, 2.5, 246.28, None)],
            {"Umbuchung (Eingang)": 1},
            id="comdirect",
        ),
    ],
)
def test_the_exports_of_the_brokers_read_as_trades(
    text: str,
    mapping: str,
    rows: list[tuple[int, str, str, str, float, float, float | None]],
    skipped: dict[str, int],
) -> None:
    """Amounts and fees without their sign and in cents, rows of other kinds left out."""
    table = _table(text)
    assert tradeimport.guess(table).describe(table) == mapping
    parsed = _read(text)
    assert [
        (line, str(r["date"]), r["kind"], r["security"], r["units"], r["amount"], r.get("fees"))
        for line, r in parsed.rows
    ] == rows
    assert (parsed.refused, parsed.skipped) == ([], Counter(skipped))


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("01.01.2999;Kauf;1;100;EUR", "2999-01-01 is in the future"),
        ("01.02.2026;Kauf;1;100;USD", "not EUR: the trades take euros"),
        ("01.02.2026;Kauf;;100;EUR", "the buy has no units"),
        ("01.02.2026;Verkauf;1;;EUR", "the sell has no amount"),
        ("01.02.2026;Kauf;zwei;100;EUR", "units 'zwei' does not read as a number with a decimal"),
        ("2026-02-31;Kauf;1;100;EUR", "date '2026-02-31' does not read as dmy"),
        ("01.02.2026;Kauf;1", "only 4 of 6 cells"),
    ],
)
def test_a_line_that_does_not_read_is_refused_with_its_reason(row: str, reason: str) -> None:
    """Line 2 reads: an empty currency cell is no other currency."""
    header = "Datum;Art;Stück;Kurswert;Währung;ISIN"
    text = f"{header}\n01.01.2026;Kauf;2;200;;{WORLD}\n{row};{WORLD}\n"
    parsed = _read(text)
    assert [line for line, _ in parsed.rows] == [2]
    [(line, refused)] = parsed.refused
    assert line == 3
    assert refused.startswith(reason)


def test_without_a_kind_column_a_minus_before_the_units_sells() -> None:
    parsed = _read(f"Date,ISIN,Units,Amount\n2026-01-02,{WORLD},2,200\n2026-03-02,{WORLD},-1,90\n")
    assert [(r["kind"], r["units"]) for _, r in parsed.rows] == [("buy", 2), ("sell", 1)]


def test_a_headerless_export_keeps_its_first_row_as_a_trade() -> None:
    table = _table(f"2026-01-02,{WORLD},2,200\n2026-03-02,{WORLD},-1,90\n")
    columns = tradeimport.guess(table)
    assert columns.missing == ["units", "amount"]
    chosen = dataclasses.replace(columns, at=columns.at | {"units": 2, "amount": 3})
    parsed = tradeimport.read(table, chosen, today=TODAY)
    assert [(line, r["kind"], r["units"]) for line, r in parsed.rows] == [
        (1, "buy", 2),
        (2, "sell", 1),
    ]


def test_the_trades_held_already_are_left_out_once_each() -> None:
    """A second upload of the same months adds nothing; two equal executions of a day need two
    trades, so the file adds the second."""
    buy = {"date": date(2026, 2, 2), "kind": "buy", "security": WORLD, "units": 1, "amount": 99.5}
    text = "Date,ISIN,Units,Amount\n" + f"2026-02-02,{WORLD},1,99.50\n" * 2
    merged = tradeimport.merge(_depot(buy), _read(text))
    assert (merged.added, merged.held) == ([buy], 1)
    merged = tradeimport.merge(_depot(buy, buy), _read(text))
    assert (merged.added, merged.held) == ([], 2)


def test_a_row_that_the_trades_cannot_replay_is_refused_and_the_rest_stays() -> None:
    """A sale beyond the units held then, a symbol in a depot, a Vorabpauschale out of January."""
    text = (
        "Date,Type,ISIN,Units,Amount\n"
        f"2026-01-02,Buy,{WORLD},2,200\n"
        f"2026-02-02,Sell,{WORLD},3,330\n"
        f"2026-03-02,Sell,{WORLD},1,110\n"
        "2026-03-03,Buy,XAU,1,2500\n"
        f"2026-04-01,Vorabpauschale,{WORLD},,2\n"
    )
    parsed = _read(text)
    merged = tradeimport.merge(_depot(), parsed)
    assert [(r["date"], r["kind"]) for r in merged.added] == [
        (date(2026, 1, 2), "buy"),
        (date(2026, 3, 2), "sell"),
    ]
    assert [line for line, _ in merged.refused] == [3, 5, 6]
    assert "1 units more than held" in merged.refused[0][1]
    assert merged.refused[1][1] == "XAU is no ISIN: a symbol is for gold or crypto"
    assert "the bank books it in January" in merged.refused[2][1]
    assert tradeimport.summary(parsed, merged) == (
        "2 new trades from 2026-01-02 to 2026-03-02: 1 buy, 1 sale",
        "3 lines refused",
    )
    gold = GoldAsset.model_validate({"id": "coins", "kind": "gold", "value": 1})
    assert [r["security"] for r in tradeimport.merge(gold, parsed).added] == [WORLD, WORLD, "XAU"]


def test_a_security_without_a_name_takes_the_name_of_its_first_row() -> None:
    named = {"date": date(2025, 1, 2), "kind": "buy", "security": WORLD, "units": 1, "amount": 90}
    text = (
        "Datum;Art;ISIN;Menge;Kurswert;Bezeichnung\n"
        f"02.01.2026;Kauf;{WORLD};1;100;MSCI World\n02.01.2026;Kauf;{EM};1;30;EM IMI\n"
        f"03.02.2026;Kauf;{EM};1;31;EM Markets\n"
    )
    merged = tradeimport.merge(_depot(named | {"name": "World"}), _read(text))
    assert [r.get("name") for r in merged.added] == [None, "EM IMI", None]


def test_a_price_far_from_a_stored_one_is_a_slip(data: Path) -> None:
    prices.save(data, WORLD, [(date(2026, 2, 2), 100.0)], source="test")
    rows = [{"date": date(2026, 2, 2), "kind": "buy", "security": WORLD, "units": 1, "amount": 1}]
    assert tradeimport.slips(data, rows) == [
        "a stored price of 100,00 € on 2026-02-02, the buy of that day paid 1,00 € per unit"
    ]
    assert tradeimport.slips(data, [rows[0] | {"amount": 99}]) == []


def _export(tmp_path: Path, text: str = TRADE_REPUBLIC) -> str:
    (path := tmp_path / "export.csv").write_text(text)
    return str(path)


def test_the_command_adds_the_new_trades_once(data: Path, tmp_path: Path) -> None:
    """One revision; a depot then takes its basis from the lots; a second run adds nothing."""
    args = ["trades", "import", "depot", _export(tmp_path), "--data", str(data)]
    dry = CliRunner().invoke(app, [*args, "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "2 new trades from 2026-01-20 to 2026-05-20: 1 buy, 1 sale\n2 other rows" in dry.output
    assert "Check: the trades replace the cost basis of 4.000,00 € with" in dry.output
    assert "depot: added" not in dry.output
    [depot] = [a for a in load_assets(data) if a.id == "depot"]
    assert isinstance(depot, EquityAsset) and not depot.trades

    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "depot: added 2 trades" in result.output
    [depot] = [a for a in load_assets(data) if a.id == "depot"]
    assert isinstance(depot, EquityAsset)
    assert (depot.cost_basis, [t.kind for t in depot.trades]) == (None, ["buy", "sell"])
    assert revisions.entries(data)[-1].source == "trades import"

    again = CliRunner().invoke(app, args)
    assert again.exit_code == 0, again.output
    assert "0 new trades; 2 are in the trades already" in again.output


def test_the_command_stops_at_a_price_far_off_unless_forced(data: Path, tmp_path: Path) -> None:
    prices.save(data, EM, [(date(2026, 1, 20), 1.0)], source="test")
    args = ["trades", "import", "depot", _export(tmp_path), "--data", str(data)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "Check: a stored price of 1,00 € on 2026-01-20, the buy of that day paid" in (
        result.output
    )
    assert not next(a for a in load_assets(data) if isinstance(a, HoldingsAsset)).trades
    assert CliRunner().invoke(app, [*args, "--force"]).exit_code == 0


@pytest.mark.parametrize(
    ("asset", "options", "export", "message"),
    [
        ("depot", ["--column", "units=Stück"], TRADE_REPUBLIC, "no column 'Stück', the table has"),
        ("depot", ["--column", "units="], TRADE_REPUBLIC, "choose the column of units"),
        ("depot", ["--column", "price=price"], TRADE_REPUBLIC, "no field 'price': take one of"),
        ("depot", ["--decimal", ","], TRADE_REPUBLIC, "no trade to add"),
        # nothing added and nothing held already, but a refused line: a sale without units held
        ("depot", [], f"Date,ISIN,Units,Amount\n2026-03-02,{WORLD},-1,90\n", "line 2: sale of"),
        ("giro", [], TRADE_REPUBLIC, "giro holds no securities"),
        ("gone", [], TRADE_REPUBLIC, "no row with id gone"),
    ],
)
def test_the_command_refuses_with_its_reason(
    data: Path, tmp_path: Path, asset: str, options: list[str], export: str, message: str
) -> None:
    before = (data / "assets.yaml").read_text()
    args = ["trades", "import", asset, _export(tmp_path, export), "--data", str(data), *options]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert message in " ".join(result.output.split())
    assert (data / "assets.yaml").read_text() == before


def test_the_command_refuses_trades_that_a_hand_edit_left_no_list(
    data: Path, tmp_path: Path
) -> None:
    """The file and the line of the edit, no traceback, the file as it was."""
    (data / "assets.yaml").write_text(f"{ASSETS}    trades: 5\n")
    before = (data / "assets.yaml").read_text()
    args = ["trades", "import", "depot", _export(tmp_path), "--data", str(data)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "Not imported: assets.yaml:10: assets[1].trades holds no list: 5" in " ".join(
        result.output.split()
    )
    assert (data / "assets.yaml").read_text() == before


def test_an_error_of_the_code_is_no_refusal(
    data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slip of the code ends the command with its traceback, not as `Not imported`."""

    def slip(*_args: object) -> None:
        raise KeyError("added")

    monkeypatch.setattr(tradeimport, "merge", slip)
    args = ["trades", "import", "depot", _export(tmp_path), "--data", str(data)]
    result = CliRunner().invoke(app, args)
    assert isinstance(result.exception, KeyError)
    assert "Not imported" not in result.output
