"""The Snapshot and Assets pages: the observed values, the securities with their lots
and sales, the trade form and import, the prices, the values that need an update."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import german
import pytest
import yaml
from apps import COINS, MAIN, XAU_TRADES
from builders import plan
from pydantic import TypeAdapter
from streamlit.testing.v1 import AppTest

from dagobert import history, i18n, lots, prices, revisions, series
from dagobert.loader import load_assets
from dagobert.model.assets import Asset, EquityAsset, GoldAsset, HoldingsAsset, LotAsset
from dagobert.model.plan import Scenario
from dagobert.money import NUMBER_COLUMN
from dagobert.runner import DATA_ENV
from dagobert.store import RowEdits, assets_file
from dagobert.ui import (
    CAME,
    PAGE,
    PAGES,
    assets,
    corrections,
    gridcolumns,
    snapshot,
    summary,
    tradeform,
)
from dagobert.ui import tradeimport as tradeimport_ui

SNAPPED = date(2026, 9, 1)  # the day of `test_snapshot_edits`
TAB = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import assets, told
told()
assets.securities_tab(assets_file(Path({data!r})))
"""


@pytest.mark.parametrize(
    ("rows", "order", "entered", "edited", "history", "stray"),
    [
        pytest.param(
            [
                {"id": "flat", "kind": "property", "sqm": 54, "per_sqm": 3600},
                {"id": "depot", "kind": "equity", "value": 1.0, "cost_basis": 1.0},
                {"id": "giro", "kind": "cash", "value": 1.0},
                {"id": "kredit", "kind": "loan", "balance": -9.0},
            ],
            [2, 1, 0, 3],
            {
                2: {"new": 200000.0},  # the value of a property: saved as its price per m²
                1: {"new": 9.0, "cost_basis": 8.0},
                0: {"new": None},
                3: {"new": 8.0},
            },
            # a loan typed without the minus; the history takes the value of the saved price, which
            # comes back to the cent
            {
                0: {"per_sqm": 3703.7037, "asof": SNAPPED},
                1: {"value": 9.0, "cost_basis": 8.0, "asof": SNAPPED},
                3: {"balance": -8.0, "asof": SNAPPED},
            },
            [("flat", 3703.7037 * 54), ("depot", 9.0), ("kredit", -8.0)],
            {},
            id="typed",
        ),
        pytest.param(
            [
                {"id": "depot", "kind": "equity", "value": 1.0, "cost_basis": 1.0},
                {"id": "traded", "kind": "equity", "value": 1.0, "trades": [{"kind": "buy"}]},
                {"id": "giro", "kind": "cash", "value": 1.0},
                {"id": "fest", "kind": "term_deposit", "value": 1000.0},
            ],
            [0, 1, 2, 3],
            {
                0: {"cost_basis": 2.0},
                1: {"new": 3.0, "cost_basis": 2.0},
                2: {"cost_basis": 2.0},
                3: {"new": 1010.0, snapshot.SAME: True},
            },
            # a cost basis alone keeps the date of the value
            {0: {"cost_basis": 2.0}, 1: {"value": 3.0, "asof": SNAPPED}},
            [("traded", 3.0)],
            {"cost_basis": ["traded", "giro"], "new": ["fest"]},
            id="not-taken",
        ),
        pytest.param(
            [
                {"id": "gold", "kind": "gold", "value": 500.0, "asof": date(2026, 3, 31)},
                {"id": "flat", "kind": "property", "sqm": 100, "per_sqm": 5000.0},
                {"id": "giro", "kind": "cash", "value": 1.0},
            ],
            [0, 1, 2],
            {
                0: {snapshot.SAME: True},
                1: {snapshot.SAME: True, "new": 510000.0},
                2: {snapshot.SAME: False},
            },
            {0: {"asof": SNAPPED}, 1: {"per_sqm": 5100.0, "asof": SNAPPED}},
            [("gold", 500.0), ("flat", 510000.0)],
            {},
            id="unchanged",
        ),
    ],
)
def test_snapshot_edits(
    rows: list[gridcolumns.Row],
    order: list[int],
    entered: snapshot.Cells,
    edited: dict[int, gridcolumns.Row],
    history: list[tuple[str, float]],
    stray: dict[str, list[str]],
) -> None:
    """Each value typed or ticked `unchanged` is dated and recorded, a typed value before a tick;
    an untick records nothing. A cost basis belongs to a depot without trades, a value not to a
    term deposit: its contract gives the value, and the history counts its interest."""
    shown = [(i, rows[i]) for i in order]
    edits, recorded = snapshot.snapshot_edits(
        shown, [snapshot.Estimate()] * len(order), entered, SNAPPED
    )
    assert edits.edited == edited
    assert recorded == [(SNAPPED, asset, value) for asset, value in history]
    assert snapshot.stray(shown, entered) == stray


def test_a_correction_takes_what_changes_a_recorded_value() -> None:
    """A tick removes, a loan stays below zero whatever sign is typed, an emptied cell or the
    value as recorded is no correction."""
    day = date(2026, 9, 1)
    rows = [(day, "giro", 1000.0), (day, "loan", -50000.0), (day, "depot", 5000.0)]
    edited: dict[int, dict[str, Any]] = {
        0: {"value": 1000.004},
        1: {"value": 49000},
        2: {"value": None, corrections.REMOVE: True},
    }
    fixes = corrections.corrections(rows, edited, {"loan"})
    assert fixes == {1: -49000.0, 2: None}
    found, removed = corrections.listed(rows, fixes, {"loan": "Home loan"})
    assert [c.text for c in found] == ["**2026-09-01 Home loan** -50.000 € → -49.000 €"]
    assert removed == ["2026-09-01 depot"]


def test_a_recorded_month_is_corrected_through_the_guard(data: Path) -> None:
    """The month of the grid, a value changed and one removed by its place there: the guard
    lists both and warns of the removal, and Save writes them as one revision."""
    (data / "history.csv").write_text(
        "date,asset,value\n2026-08-01,giro,900.00\n2026-09-01,giro,1000.00\n"
        "2026-09-15,depot,5000.00\n"
    )
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    month = at.selectbox(key="snapshot-correct-month")
    assert month.options == ["2026-09", "2026-08"]
    edit = {"edited_rows": {"0": {"value": 1100}, "1": {corrections.REMOVE: True}}}
    german.edited(at, "snapshot-correct-2026-09-0", edit)
    assert "**2026-09-01 giro** 1.000 € → 1.100 €  \n**2026-09-15 depot** removed" in [
        c.value.removeprefix("To save:  \n") for c in at.caption
    ]
    assert any("1 recorded value goes" in w.value for w in at.warning)
    save = at.button(key="snapshot-correct-save")
    assert save.label == "Save the correction ⚠"
    save.click()
    german.edited(at, "snapshot-correct-2026-09-0", edit)
    assert not at.exception and not at.error
    assert (data / "history.csv").read_text() == (
        "date,asset,value\n2026-08-01,giro,900.00\n2026-09-01,giro,1100.00\n"
    )
    assert revisions.entries(data)[-1].source == "app: correct 2026-09"
    assert [t.value for t in at.toast] == ["Corrected 2026-09"]


SECURITIES = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import assets, snapshot
snapshot.page(assets_file(Path({data!r})))
assets.securities_tab(assets_file(Path({data!r})))
"""


WORLD, SOLD = "IE00B4L5Y983", "IE00B5BMR087"


TRADES = [
    {"date": "2021-01-01", "kind": "buy", "security": WORLD, "name": "World", "units": 10}
    | {"amount": 100},
    {"date": "2021-01-01", "kind": "buy", "security": SOLD, "units": 5, "amount": 50},
    {"date": "2022-01-01", "kind": "sell", "security": SOLD, "units": 5, "amount": 55},
]


DEPOT = {"id": "depot", "kind": "equity", "value": 1, "trades": TRADES}


def _depot(data: Path) -> None:
    (data / "prices").mkdir()
    (data / "prices" / f"{WORLD}.csv").write_text("date,close\n2022-01-01,12\n")
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))


def test_securities_value_the_lots_and_return_all_trades(data: Path) -> None:
    _depot(data)
    [depot] = load_assets(data)
    assert isinstance(depot, EquityAsset)
    world, sold, total = assets.securities(data, depot, lambda _: 100.0, None)  # largest first
    # what a security is worth and earned first: on a phone the rest needs a swipe
    assert list(world)[:3] == ["security", "value", "gain"]
    assert world == {
        "security": "World",
        "ISIN or symbol": WORLD,
        "units": 10,
        "cost": 100,
        "value": 120,
        "gain": 20,
        "gain %": 20.0,
        assets.YEARLY: 20.0,
        assets.REAL: 20.0,
        "as of": date(2022, 1, 1),
    }
    assert (sold["security"], sold["units"], sold["value"], sold[assets.YEARLY]) == (
        SOLD,
        0,
        0,
        10.0,
    )
    # 175 for 150
    assert (total["ISIN or symbol"], total["units"], total[assets.YEARLY]) == ("", None, 16.7)
    [sale] = assets.sales(depot, None)
    assert list(sale)[:3] == ["date", "security", "gain"]
    assert sale["gain"] == 5
    [lot] = assets.open_lots(data, depot, None)
    assert list(lot)[:4] == ["security", "bought", "value", "gain %"]
    assert assets.TAX_FREE not in world and "tax" not in sale  # gold and crypto only


def test_a_lot_of_cost_zero_shows_no_gain_percentage(data: Path) -> None:
    """Bonus shares or a gift of shares cost nothing: no gain percentage, no division."""
    _depot(data)
    free = {"date": "2021-06-01", "kind": "buy", "security": WORLD, "units": 1, "amount": 0}
    (data / "assets.yaml").write_text(
        yaml.safe_dump({"assets": [DEPOT | {"trades": [*TRADES, free]}]})
    )
    [asset] = load_assets(data)
    assert isinstance(asset, HoldingsAsset)
    gains = {lot["bought"]: lot["gain %"] for lot in assets.open_lots(data, asset, None)}
    assert gains[date(2021, 6, 1)] is None
    assert gains[date(2021, 1, 1)] == 20.0


def test_securities_group_units_by_a_space() -> None:
    """A grouping dot would read as the decimal point of the price beside them."""
    config = json.loads(json.dumps(assets.formats()))
    for name in ("units", assets.TAX_FREE):
        assert config[name]["type_config"]["format"] == NUMBER_COLUMN


@pytest.mark.parametrize(
    ("bought", "sold", "rule"),
    [
        (date(2026, 1, 14), date(2027, 1, 14), assets.PRIVATE_SALE),
        (date(2026, 1, 14), date(2027, 1, 15), assets.FREE),
        (date(2024, 2, 29), date(2025, 2, 28), assets.PRIVATE_SALE),
        (date(2024, 2, 29), date(2025, 3, 1), assets.FREE),
        (date(2027, 1, 1), date(2030, 1, 1), assets.CAPITAL),  # bought from `capital_from`
    ],
)
def test_a_lot_of_gold_or_crypto_is_free_the_day_after_a_year(
    bought: date, sold: date, rule: str
) -> None:
    """§23 Abs. 1 S. 1 Nr. 2 EStG: a private sale when not more than a year lies between purchase
    and sale. The year ends with the day of the purchase a year on (§188 Abs. 2 BGB), for the 29th
    of February with the end of February (Abs. 3)."""
    rules = assets.Holding(12, date(2027, 1, 1), sold)
    assert rules.rule(lots.Lot("BTC", "Bitcoin", bought, 1.0, 1.0), sold) == rule


def test_a_sale_of_gold_lists_its_free_and_its_taxable_part(data: Path) -> None:
    """The lines of the Anlage SO: the units held over a year are free, the others a private
    sale, each part with its share of the proceeds. Open lots and securities show when the units
    become free."""
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("  gold: {mean: 0.04}\n")
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [COINS]}))
    [coins] = load_assets(data)
    assert isinstance(coins, GoldAsset)
    rules = assets.Holding.of(data, coins)
    free, young = assets.sales(coins, rules)
    assert list(free)[:4] == ["date", "security", "gain", "tax"]
    assert (free["tax"], free["units"], free["proceeds"], free["gain"]) == (
        assets.FREE,
        2,
        6000,
        2000,
    )
    assert (young["tax"], young["units"], young["gain"]) == (assets.PRIVATE_SALE, 0.5, 250)
    assert (free["bought"], young["bought"]) == ("2024-01-10", "2025-06-01")
    for today, rule, tax_free in [
        (date(2026, 6, 1), assets.PRIVATE_SALE, 0.0),
        (date(2026, 6, 2), assets.FREE, 0.5),
    ]:
        day = replace(rules, today=today)
        [lot] = assets.open_lots(data, coins, day)
        assert (lot["tax"], lot["free from"]) == (rule, date(2026, 6, 2))
        assert "Vorabpauschale per unit" not in lot
        held, total = assets.securities(data, coins, lambda _: 100.0, day)
        assert (held["units"], held[assets.TAX_FREE], total[assets.TAX_FREE]) == (
            0.5,
            tax_free,
            None,
        )
        assert held["value"] is not None  # at the gold series


def test_capital_income_has_no_holding_period(data: Path) -> None:
    """A gold note without backing, and crypto bought from `crypto_capital_from` (the BMF draft
    of 2026-09-30), pay the flat tax whenever sold."""
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("  gold: {mean: 0.04}\n  bitcoin: {mean: 0.1}\n")
        fh.write("tax: {crypto_capital_from: 2025-01-01}\n")
    btc = [t | {"security": "BTC"} for t in XAU_TRADES]
    wallet = COINS | {"id": "wallet", "kind": "crypto", "trades": btc}
    (data / "assets.yaml").write_text(
        yaml.safe_dump({"assets": [COINS | {"tax": "capital"}, wallet]})
    )
    note, coins = (a for a in load_assets(data) if isinstance(a, LotAsset))
    [lot] = assets.open_lots(data, note, assets.Holding.of(data, note))
    assert (lot["tax"], lot["free from"]) == (assets.CAPITAL, None)
    # the lot of 2024 stays a private sale, held over a year
    taxes = [part["tax"] for part in assets.sales(coins, assets.Holding.of(data, coins))]
    assert taxes == [assets.FREE, assets.CAPITAL]


def test_the_trade_form_of_gold_offers_its_symbol_and_no_vorabpauschale() -> None:
    assert tradeform.choices(GoldAsset(id="coins", kind="gold", value=1)) == (
        ["XAU"],
        [lots.TradeKind.BUY, lots.TradeKind.SELL],
    )
    codes, kinds = tradeform.choices(EquityAsset.model_validate(DEPOT))
    assert codes == [SOLD, WORLD]  # the latest trade first
    assert lots.TradeKind.VORABPAUSCHALE in kinds


def test_the_trades_of_gold_warn_of_grams_typed_as_ounces(data: Path) -> None:
    """The grid of trades warns through the save guard (`Table.check`): a 100 g bar holds
    100 / `GRAMS_PER_TROY_OUNCE` troy ounces, not 100 units. A row that the model refuses is left
    to the save."""
    last = series.in_euros(series.SERIES["gold"], data)[-1]
    ounces = 100 / prices.GRAMS_PER_TROY_OUNCE
    bar = {"date": str(last.month), "kind": "buy", "security": "XAU", "units": ounces}
    bar["amount"] = round(ounces * last.value, 2)
    assert tradeform.series_notes(data, [bar, {"date": "?"}]) == []
    [far] = tradeform.series_notes(data, [bar | {"units": 100}])
    assert "per troy ounce" in far


def test_the_converted_salary_offers_the_monthly_salaries_without_of() -> None:
    """As the model takes them: a bonus and a yearly payment are no salary of a conversion, a
    name with a monthly row is, also beside a raise row."""
    rows: list[gridcolumns.Row] = [
        {"name": "Gehalt", "kind": "salary", "gross": 5000},
        {"name": "Gehalt", "kind": "salary", "gross": 5200, "start": "2027-01-01"},
        {"name": "Bonus", "kind": "salary", "of": "Gehalt", "every": 12},
        {"name": "Weihnachtsgeld", "kind": "salary", "gross": 3000, "every": 12},
    ]
    assert assets.unconverted(rows) == {"Bonus", "Weihnachtsgeld"}


DAY = date(2026, 10, 9)


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        (
            tradeform.Typed(DAY, "buy", "ie00b4l5y983 ", units="2,5", amount="1.234,5"),
            {"units": 2.5, "amount": 1234.5},
        ),
        (
            tradeform.Typed(DAY, "sell", WORLD, "World", "0.125", "12.50", "1,5"),
            {"name": "World", "units": 0.125, "amount": 12.5, "fees": 1.5},
        ),
        (  # euros with groups
            tradeform.Typed(DAY, "buy", WORLD, units="1", amount="1.000"),
            {"units": 1, "amount": 1000},
        ),
        (
            tradeform.Typed(DAY, "buy", WORLD, units="1.000", amount="1.000"),
            "units 1.000: type 1000 for whole units",
        ),
        (tradeform.Typed(DAY, "buy", WORLD, units="-1", amount="5"), "units: type a number"),
        (tradeform.Typed(DAY, "buy", WORLD, amount="5"), "enter the number of units"),
        (tradeform.Typed(DAY, "sell", WORLD, units="1"), "enter the amount in euros"),
        (
            tradeform.Typed(date(2027, 1, 9), "vorabpauschale", WORLD, units="1", amount="3"),
            "units belong to a buy",
        ),
        (tradeform.Typed(DAY, "buy", " ", units="1", amount="5"), "choose a security"),
        (tradeform.Typed(None, "buy", WORLD, units="1", amount="5"), "choose a date"),
        (tradeform.Typed(date(2027, 1, 9), "vorabpauschale", WORLD, amount="3"), {"amount": 3}),
    ],
)
def test_a_typed_trade_reads_a_comma_and_a_point_alike(
    typed: tradeform.Typed, expected: dict[str, object] | str
) -> None:
    """Units have no thousands groups, so their mark is decimal, but one before three digits may
    group them and is refused. Euros read like the Spend quick add. An empty name or fee stays
    out of the row."""
    if isinstance(expected, str):
        with pytest.raises(ValueError, match=expected):
            typed.row()
    else:
        assert typed.row() == {"date": typed.day, "kind": typed.kind, "security": WORLD} | expected


def test_a_typed_trade_names_the_fields_to_correct() -> None:
    """The form frames them in red, and its hint gives a fraction in the decimal mark of the
    language, like the others."""
    with pytest.raises(tradeform.TypedError, match="units and the amount") as refused:
        tradeform.Typed(DAY, "buy", WORLD).row()
    assert refused.value.fields == ("units", "amount")
    with pytest.raises(tradeform.TypedError, match=r"or 1\.2 for a fraction") as refused:
        tradeform.Typed(DAY, "buy", WORLD, units="1.200", amount="5").row()
    assert refused.value.fields == ("units",)
    with i18n.use("de"), pytest.raises(tradeform.TypedError, match="oder 1,2 für") as refused:
        tradeform.Typed(DAY, "buy", WORLD, units="1.200", amount="5").row()


def test_an_added_trade_shows_its_price() -> None:
    """A slip of a mark in the units shows as a price off by a factor of 1000."""
    buy = tradeform.Typed(DAY, "buy", WORLD, units="1200", amount="6.900").row()
    assert "1200 × World at 5,75 € per unit, 6.900,00 €" in tradeform.receipt(buy, {WORLD: "World"})


def test_a_phone_adds_a_trade_at_once(data: Path) -> None:
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT | {"trades": TRADES[:1]}]}))
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30)
    at.query_params["mobile"] = "1"
    at.run()
    assert next(s for s in at.selectbox if s.label == "Security").value == WORLD  # the latest
    typed = {"Units": "2,5", "Amount €": "1.234,50"}
    for widget in at.text_input:
        widget.set_value(typed.get(widget.label, ""))
    next(b for b in at.button if b.label == "Add").click().run()
    assert not at.exception and not at.error
    [depot] = load_assets(data)
    assert isinstance(depot, HoldingsAsset)
    assert (depot.trades[-1].kind, depot.trades[-1].units, depot.trades[-1].amount) == (
        "buy",
        2.5,
        1234.5,
    )
    assert next(t for t in at.text_input if t.label == "Units").value == ""  # a new form
    next(b for b in at.button if b.label == "Add").click().run()  # without units and amount
    assert "Not added" in at.error[0].value
    assert load_assets(data) == [depot]


EXPORT = (  # made up, in the layout of the Depotumsätze of comdirect
    "Datum;Art;Bezeichnung;ISIN;Menge;Kurswert;Kurswertwährung\n"
    f"01.01.2021;Kauf;World;{WORLD};10;100,00;EUR\n"
    f"02.02.2022;Kauf;World;{WORLD};2;24,00;EUR\n"
    f"03.02.2022;Umbuchung (Eingang);World;{WORLD};1;;EUR\n"
)


@pytest.mark.parametrize("phone", [False, True])
def test_an_imported_broker_export_adds_the_trades_that_its_preview_showed(
    data: Path, phone: bool
) -> None:
    """The preview leaves out the trade held already and the transfer. A trade added elsewhere
    after the preview refuses the import until the preview shows it."""
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    at.file_uploader[0].upload("export.csv", EXPORT.encode(), "text/csv").run()
    assert not at.exception and not at.error
    assert {
        "1 new trade from 2022-02-02 to 2022-02-02: 1 buy; 1 is in the trades already.",
        "1 other row left out: Umbuchung (Eingang) 1.",
    } <= {c.value for c in at.caption}
    # every column was found: the mapping stays folded
    assert not next(e for e in at.expander if e.label == tradeimport_ui.COLUMNS).proto.expanded
    by_security, ends, left_out = at.table
    assert by_security.value.values.tolist() == [["World", WORLD, "1", "+2"]]
    assert ends.value[["date", "units", "price", "amount", "fees"]].values.tolist() == [
        ["2022-02-02", "2", "12 €", "24 €", ""]  # as in the trades grid
    ]
    row = f"03.02.2022 · Umbuchung (Eingang) · World · {WORLD} · 1 · EUR"
    assert left_out.value.values.tolist() == [["4", "Umbuchung (Eingang)", row]]
    sell = {"date": DAY, "kind": "sell", "security": WORLD, "units": 1, "amount": 12}
    assets_file(data).child("depot", "trades").apply(RowEdits(added=[sell]), source="phone")
    next(b for b in at.button if b.label == "Import 1 trade").click().run()
    assert "Not imported: `assets.yaml` changed at" in at.error[0].value
    assert len(next(a for a in load_assets(data) if isinstance(a, HoldingsAsset)).trades) == 4

    next(b for b in at.button if b.label == "Import 1 trade").click().run()
    assert not at.exception and not at.error
    [depot] = load_assets(data)
    assert isinstance(depot, HoldingsAsset)
    assert [(t.date, t.units, t.amount) for t in depot.trades[-1:]] == [(date(2022, 2, 2), 2, 24)]
    assert [t.value for t in at.toast] == ["Added 1 trade from 2022-02-02 to 2022-02-02"]
    assert not at.file_uploader[0].value  # a new upload field


def test_an_import_warns_before_it_replaces_a_typed_cost_basis(data: Path) -> None:
    """A broker export of recent months only would lose the basis of a depot held for years."""
    depot = {"id": "depot", "kind": "equity", "value": 1, "cost_basis": 4000}
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [depot]}))
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30).run()
    at.file_uploader[0].upload("export.csv", EXPORT.encode(), "text/csv").run()
    assert not at.exception and not at.error
    assert "the trades replace the cost basis of 4.000,00 € with" in at.warning[0].value
    assert any(b.label == "Import 2 trades ⚠" for b in at.button)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n", tradeimport_ui.NOT_READ),  # a statement as a PDF
        (EXPORT.replace("Menge;", "").replace(";10;", ";").replace(";2;", ";").encode(), "Units"),
    ],
)
def test_a_broker_export_that_does_not_read_says_what_to_do(
    data: Path, raw: bytes, message: str
) -> None:
    """A file that is no table names the export to take; a column without a guess opens the
    columns and names the field by its label."""
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30).run()
    at.file_uploader[0].upload("export.csv", raw, "text/csv").run()
    assert not at.exception
    assert message in next(m.value for m in [*at.error, *at.info])
    columns = [e.proto.expanded for e in at.expander if e.label == tradeimport_ui.COLUMNS]
    assert columns == ([] if message == tradeimport_ui.NOT_READ else [True])


def _grid(at: AppTest, *columns: str) -> Any:
    """The rows of the grid whose first columns are `columns`: AppTest shows no key of a grid."""
    return next(d.value for d in at.dataframe if [*d.value.columns[: len(columns)]] == [*columns])


def test_securities_tab_and_snapshot_render(data: Path) -> None:
    _depot(data)
    at = AppTest.from_string(SECURITIES.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    snapshot = _grid(at, "asset")
    assert snapshot["estimate"].tolist() == [120.0]
    assert snapshot[["asset", "asof"]].values.tolist() == [["⚠ depot", "never"]]
    # the securities with their total, the open lot, the sale and the trades editor
    assert [len(_grid(at, *c)) for c in (("security", "value"), ("security", "bought"))] == [3, 1]
    assert [len(_grid(at, "date", c)) for c in ("security", "kind")] == [1, len(TRADES)]
    assert [b.disabled for b in at.button if b.label == "Record"] == [True]  # nothing entered
    [stored] = at.table  # the held securities under `Prices`, closed while each has a price
    assert stored.value[["security", "last price", "prices"]].values.tolist() == [
        ["World", "2022-01-01", 1]
    ]
    assert not next(e for e in at.expander if e.label == "Prices").proto.expanded


# `told` first, as `main.py`: the toasts of a save that reran the page
SNAPSHOT = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import snapshot, told
told()
snapshot.page(assets_file(Path({data!r})))
"""


def test_the_snapshot_shows_a_property_at_its_value_and_its_fields_by_their_headers(
    data: Path,
) -> None:
    """`current` holds what a property is worth, its price per m² a column of its own, and the
    guard names a field as the Assets grid heads it: a tick of `unchanged` lists `as of`."""
    flat = {"id": "flat", "name": "Flat", "kind": "property", "sqm": 54, "per_sqm": 3600.0}
    (data / "assets.yaml").write_text(
        yaml.safe_dump({"assets": [flat | {"asof": date(2026, 4, 30)}]})
    )
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    grid = _grid(at, "asset")
    assert grid[["current", "per_sqm", "measure"]].values.tolist() == [[194400.0, 3600.0, "value"]]
    german.edited(at, "snapshot-0", {"edited_rows": {"0": {snapshot.SAME: True}}})
    assert f"**Flat as of** 2026-04-30 → {date.today()}" in [
        c.value.removeprefix("To save:  \n") for c in at.caption
    ]


def test_a_typed_price_saves_at_once_and_records_the_depot(data: Path) -> None:
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [DEPOT]}))
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    assert next(e for e in at.expander if e.label == "Prices").proto.expanded  # World has none
    assert at.table[0].value["last price"].tolist() == ["none"]
    assert at.dataframe[0].value["estimate"].isna().all()
    next(t for t in at.text_input if t.label == "Price €").set_value("12,5")
    next(d for d in at.date_input if d.label == "Date").set_value(date(2026, 9, 1))
    next(b for b in at.button if b.label == "Add").click().run()
    assert not at.exception and not at.error
    assert prices.last_price(data, WORLD) == (date(2026, 9, 1), 12.5)
    _, added = revisions.entries(data)  # after the baseline: the price and its record, at once
    assert added.files == ("assets.yaml", "history.csv", f"prices/{WORLD}.csv")
    [depot] = load_assets(data)
    assert isinstance(depot, EquityAsset)
    assert (depot.value, depot.asof) == (125.0, date(2026, 9, 1))  # 10 units at 12,50 €
    assert at.dataframe[0].value["estimate"].tolist() == [125.0]
    assert [t.value for t in at.toast] == [
        "Added World at 12,50 € per unit on 2026-09-01: the 10 units held are worth 125,00 €  \n"
        "Recorded depot 125 € as of 2026-09-01"
    ]
    assert next(t for t in at.text_input if t.label == "Price €").value == ""  # a new form

    next(s for s in at.selectbox if s.label == "Security").set_value(SOLD)
    next(t for t in at.text_input if t.label == "Price €").set_value("5")
    next(b for b in at.button if b.label == "Add").click().run()
    assert prices.last_price(data, SOLD) == (date.today(), 5.0)
    assert next(s for s in at.selectbox if s.label == "Security").value == SOLD  # kept

    next(t for t in at.text_input if t.label == "Price €").set_value("1.250")
    next(b for b in at.button if b.label == "Add").click().run()
    assert "Not added: price 1.250: type 1250 for whole euros" in at.error[0].value


def test_an_imported_price_history_passes_the_guard(data: Path) -> None:
    """A lost decimal mark shows against the stored price and against the buy of that day."""
    _depot(data)  # 10 World bought for 10 € each, a price of 12 € on 2022-01-01
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    download = b"Datum;Schluss\n01.01.2021;1.000,00\n01.01.2022;1.200,00\n01.01.2999;1,00\n"
    at.file_uploader[0].upload("download.csv", download, "text/csv").run()
    assert not at.exception and not at.error
    assert at.info and not any(b.label.startswith("Import") for b in at.button)  # whose prices?
    [_, security] = [s for s in at.selectbox if s.label == "Security"]
    assert security.value is None  # nothing preselected: the history of one went into another
    security.set_value(WORLD).run()
    [warning] = [w.value for w in at.warning if w.value.startswith("Check before you save")]
    assert "**World 2022-01-01** 12 € → 1.200 €, 100 times the old value" in warning
    assert "the import reads 1.000,00 € on 2021-01-01, the buy of that day paid 10,00 €" in warning
    assert warning.endswith(". Look at the decimal mark.")  # not the language of the browser
    assert any("line 4: 2999-01-01 is in the future" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "Import 2 prices ⚠").click().run()
    assert not at.exception
    assert prices.read_prices(prices.price_file(data, WORLD)) == [
        (date(2021, 1, 1), 1000.0),
        (date(2022, 1, 1), 1200.0),
    ]
    [depot] = load_assets(data)
    assert isinstance(depot, EquityAsset)
    assert (depot.value, depot.asof) == (12000.0, date(2022, 1, 1))
    assert not at.file_uploader[0].value  # a new upload field
    assert [s.value for s in at.selectbox if s.label == "Security"][1] is None  # and no security


def test_securities_tab_explains_an_asset_without_trades(data: Path) -> None:
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    assert at.selectbox(key="securities-asset").options == ["depot (no trades)"]
    assert "depot has no trades" in at.info[0].value
    assert "replace its cost basis" in at.info[0].value
    assert _grid(at, "date", "kind").empty  # the editor for the first trade

    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("  gold: {mean: 0.04}\n")
    (data / "assets.yaml").write_text("assets:\n  - {id: bars, kind: gold, value: 1}\n")
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    assert "counts as held for more than a year" in at.info[0].value  # a sale is free

    (data / "assets.yaml").write_text("assets:\n  - {id: giro, kind: cash, value: 1}\n")
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    assert "No equity, fixed-income, gold or crypto asset" in at.info[0].value
    assert not at.dataframe


def test_securities_tab_opens_on_the_asset_with_the_most_trades(data: Path) -> None:
    few = DEPOT | {"id": "few", "trades": TRADES[:1]}
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [few, DEPOT]}))
    at = AppTest.from_string(TAB.format(data=str(data)), default_timeout=30).run()
    assert at.selectbox(key="securities-asset").options == ["depot", "few"]


ASSETS_PAGE = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import assets
assets.page(assets_file(Path({data!r})))
"""


def _open_tab(block: Any) -> int | None:
    """The index of the tab that the first tab strip under `block` (of `AppTest`) opens on."""
    if (proto := getattr(block, "proto", None)) is not None:
        fields = type(proto).DESCRIPTOR.fields_by_name
        if "tab_container" in fields and proto.HasField("tab_container"):
            return int(proto.tab_container.default_tab_index)
    children = getattr(block, "children", {})
    found = (_open_tab(child) for child in children.values())
    return next((index for index in found if index is not None), None)


def test_a_link_opens_an_asset_on_its_row(data: Path) -> None:
    """`?asset=bank&fields=…` opens the tab of its kind with its row first, the columns to check
    marked and named above the grid, over the reruns of the page, until a save changes the row or
    the page opens without a link."""
    (data / "assets.yaml").write_text(
        "assets:\n"
        "  - {id: giro, kind: cash, value: 1000}\n"
        "  - {id: other, kind: loan, balance: -500, rate: 0.02, annuity: 50, asof: 2026-09-01}\n"
        "  - {id: bank, kind: loan, balance: -1000, rate: 0.02, annuity: 100, asof: 2024-01-01}\n"
    )
    at = AppTest.from_string(ASSETS_PAGE.format(data=str(data)), default_timeout=30)

    def loans() -> list[str]:
        return next(g for g in at.dataframe if "balance" in g.value).value["id"].tolist()

    def opened() -> None:
        for key, value in assets.opened("bank", "balance", "asof").items():
            at.query_params[key] = value
        at.run()

    opened()
    assert not at.exception
    assert _open_tab(at.main) == list(gridcolumns.ASSET_MODELS).index("loan")
    assert loans() == ["bank", "other"]
    line = "**bank**: check **⚠ balance** and **⚠ as of**. Its row comes first until a save "
    line += "changes it."
    assert [i.value for i in at.info if "bank" in i.value] == [line]
    configs = [c for g in at.dataframe for c in json.loads(g.proto.columns).values()]
    assert {"⚠ balance", "⚠ as of"} <= {c.get("label") for c in configs}
    at.session_state[CAME] = at.session_state[PAGE] = "Assets"  # a rerun of the page
    at.run()
    assert loans() == ["bank", "other"]
    assets_file(data).apply(RowEdits({2: {"balance": -900, "asof": date(2026, 9, 1)}}), source="t")
    at.run()  # as after a save of the row
    assert loans() == ["other", "bank"]
    assert not [i for i in at.info if "bank" in i.value]
    opened()
    at.session_state[CAME] = "Overview"  # the navigation opens the page again
    at.run()
    assert loans() == ["other", "bank"]


def test_a_stale_value_links_to_its_row_on_the_assets_page(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Snapshot page records a value with the day observed, the Assets page also takes its
    date: a row marked `⚠` links there."""
    (data / "assets.yaml").write_text(
        "assets:\n  - {id: giro, kind: cash, value: 1000}\n"
        f"  - {{id: depot, kind: equity, value: 5000, cost_basis: 4000, asof: {date.today()}}}\n"
    )
    monkeypatch.setenv(DATA_ENV, str(data))
    pages = AppTest.from_file(MAIN, default_timeout=60).run().session_state[PAGES]
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=60)
    at.session_state[PAGES] = pages
    at.run()
    assert not at.exception
    assert [(link.proto.label, link.proto.query_string) for link in at.get("page_link")] == [
        ("giro", "asset=giro&fields=value%2Casof")
    ]


def test_trades_own_basis() -> None:
    assert tradeform.trades_own_basis([{"kind": "buy"}]) == {"cost_basis": None}
    assert tradeform.trades_own_basis([]) == {}


def test_summary_totals(data: Path) -> None:
    by_liquidity, by_kind = summary.totals(load_assets(data), date(2026, 9, 1))
    assert by_liquidity == {"liquid": 6000.0}
    assert by_kind == {"cash": 1000.0, "equity": 5000.0}
    assert set(gridcolumns.ASSET_MODELS) == set(summary.LIQUIDITY) == set(summary.KINDS)


def test_asset_slices_add_up_to_the_assets(data: Path) -> None:
    isin, other = "IE00B4L5Y983", "IE00BKM4GZ66"
    buy = "{date: 2020-01-01, kind: buy, security: "
    (data / "assets.yaml").write_text(
        "assets:\n"
        "  - {id: giro, kind: cash, value: 1000}\n"
        "  - {id: flat, name: Flat, kind: property, sqm: 10, per_sqm: 100}\n"
        "  - {id: loan, kind: loan, balance: -500, rate: 0.01, annuity: 10}\n"
        "  - {id: depot, kind: equity, value: 5000, trades: ["
        f"{buy}{isin}, name: World, units: 3, amount: 3}}, "
        f"{buy}{other}, name: Again, units: 1, amount: 1}}]}}\n"
        "  - {id: swap, kind: fixed_income, value: 20, trades: ["
        f"{buy}{isin}, name: Overnight, units: 2, amount: 2}}]}}\n"
    )
    (data / "prices").mkdir()
    (data / "prices" / f"{isin}.csv").write_text("date,close\n2026-09-17,10\n")
    (data / "prices" / f"{other}.csv").write_text("date,close\n2026-09-17,10\n")
    assets = load_assets(data)
    slices = summary.asset_slices(data, assets, date(2026, 9, 18))
    assert {s.path: s.value for s in slices} == {
        ("liquid", "cash", "giro"): 1000.0,
        ("illiquid", "property", "Flat"): 1000.0,
        ("liquid", "equity", "depot", "World"): 3750.0,
        ("liquid", "equity", "depot", "Again"): 1250.0,
        ("liquid", "fixed income", "swap", "Overnight"): 20.0,
    }
    by_liquidity, _ = summary.totals(assets, date(2026, 9, 18))
    assert sum(s.value for s in slices) == by_liquidity["liquid"] + by_liquidity["illiquid"]


def test_the_lots_of_a_security_sum_per_name_and_an_unpriced_one_gives_no_split(
    data: Path,
) -> None:
    isin, other = "IE00B4L5Y983", "IE00BKM4GZ66"
    buy = "{date: 2020-01-01, kind: buy, name: World, units: "
    (data / "assets.yaml").write_text(
        "assets:\n  - {id: depot, kind: equity, value: 5000, trades: ["
        f"{buy}2, security: {isin}, amount: 2}}, {buy}1, security: {isin}, amount: 1}}]}}\n"
        "  - {id: unpriced, kind: equity, value: 600, trades: ["
        f"{buy}1, security: {other}, amount: 1}}]}}\n"
    )
    (data / "prices").mkdir()
    (data / "prices" / f"{isin}.csv").write_text("date,close\n2026-09-17,10\n")
    slices = summary.asset_slices(data, load_assets(data), date(2026, 9, 18))
    assert {s.path: s.value for s in slices} == {
        ("liquid", "equity", "depot", "World"): 5000.0,  # 3 units at 10, scaled to the asset
        ("liquid", "equity", "unpriced"): 600.0,
    }


def test_change_counts_the_assets_known_by_then(data: Path) -> None:
    # simulation start 2026-01-01: the depot counts from there
    (data / "assets.yaml").write_text(
        "assets:\n"
        "  - {id: giro, kind: cash, value: 1500, asof: 2026-02-10}\n"
        "  - {id: depot, kind: equity, value: 5000, cost_basis: 4000}\n"
        "  - {id: neu, kind: cash, value: 300, asof: 2026-02-15}\n"
    )
    observed = [(date(2026, 1, 15), "giro", 1200.0)]
    revisions.write(data, "test", lambda: history.appended(data, observed))
    assets = load_assets(data)
    assert summary.change(data, assets, date(2026, 3, 1), date(2026, 1, 31)) == {"liquid": 300.0}
    # nothing known before the start: the tiles show no change, as of a new plan
    assert summary.change(data, assets, date(2026, 3, 1), date(2025, 12, 31)) is None


def test_fixed_income_share_leaves_out_deposits_and_cash(data: Path) -> None:
    (data / "assets.yaml").write_text(
        "assets:\n"
        "  - {id: giro, kind: cash, value: 1000}\n"
        "  - {id: bonds, kind: fixed_income, value: 1000}\n"
        "  - {id: depot, kind: equity, value: 3000, cost_basis: 3000}\n"
    )
    assert summary.fixed_income_share(load_assets(data), date(2026, 9, 18)) == 0.25
    assert summary.fixed_income_share([], date(2026, 9, 18)) is None


STALE_CASES = {
    "old cash": ("cash, value: 1, asof: 2025-09-17", True),  # twelve months by default
    "recent cash": ("cash, value: 1, asof: 2025-09-18", False),
    "old policy": ("av_depot, start: 2027-01-01, value: 1, asof: 2025-09-17", True),
    "undated": ("cash, value: 1", True),
    "undated empty": ("cash, value: 0", False),
    "undated deposit": (
        "term_deposit, value: 1, rate: 0.03, start: 2020-01-01, matures: 2030-01-01",
        False,
    ),
    "deposit": (  # the contract gives the value
        "term_deposit, value: 1, rate: 0.03, start: 2020-01-01, matures: 2030-01-01, "
        "asof: 2020-01-01",
        False,
    ),
    "yearly loan": ("loan, balance: -1, rate: 0.02, annuity: 1, asof: 2025-10-01", False),
    "old loan": ("loan, balance: -1, rate: 0.02, annuity: 1, asof: 2025-09-17", True),
    "property": ("property, sqm: 1, per_sqm: 1, asof: 2018-06-30", False),
    "quarterly statement": ("fixed_income, value: 1, update_every: 3, asof: 2026-06-17", True),
}


@pytest.mark.parametrize(("fields", "expected"), STALE_CASES.values(), ids=STALE_CASES.keys())
def test_values_that_need_an_update(fields: str, expected: bool) -> None:
    asset = TypeAdapter[Asset](Asset).validate_python(yaml.safe_load(f"{{id: a, kind: {fields}}}"))
    assert summary.needs_update(asset, date(2026, 9, 18)) is expected


def test_a_property_on_sale_goes_stale() -> None:
    flat = TypeAdapter[Asset](Asset).validate_python(
        {"id": "flat", "kind": "property", "sqm": 1, "per_sqm": 1, "asof": date(2023, 1, 1)}
    )
    scenario = Scenario.model_validate(
        {"name": "s", "events": [{"at": date(2028, 7, 1), "type": "sell", "asset": "flat"}]}
    )
    assert summary.stale(flat, date(2026, 9, 18), summary.selling(scenario))


POLICY = {"id": "bav", "kind": "bav", "value": 1000.0, "contribution": 100, "growth": "cash"}
POLICY |= {"phases": ["work"], "matures": date(2040, 1, 1), "asof": date(2026, 6, 30)}


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (POLICY, 1300.0),  # July to September: the employer's 100 each
        (POLICY | {"asof": None}, None),  # without a date nothing to carry
        (POLICY | {"matures": date(2026, 8, 1)}, 1100.0),  # July only
    ],
)
def test_the_snapshot_estimates_a_policy_from_its_date(
    row: dict[str, object], expected: float | None
) -> None:
    """A pension policy as the engine starts from it: so `Take estimates` fills it."""
    assert snapshot.estimate(Path(), row, date(2026, 9, 18), plan([], [])).value == expected


@pytest.mark.parametrize("recorded", ["estimate", "unchanged"])
def test_a_recorded_policy_counts_its_contributions_by_the_new_date(recorded: str) -> None:
    """`paid` is the guarantee base by `asof`: a policy recorded on a later day, by its estimate
    or a tick of `unchanged`, adds the contributions of the months between (July to September:
    the employer's 100 each), so the next carry starts from both values of that day."""
    day, row = date(2026, 9, 18), POLICY | {"paid": 500.0}
    shown, estimates = [(0, row)], [snapshot.estimate(Path(), row, day, plan([], []))]
    entered: snapshot.Cells = (
        snapshot.take_estimates(shown, estimates, {})[0]
        if recorded == "estimate"
        else {0: {snapshot.SAME: True}}
    )
    edits, _ = snapshot.snapshot_edits(shown, estimates, entered, day)
    assert edits.edited[0] == {"asof": day, "paid": 500.0 + 3 * 100} | (
        {"value": 1300.0} if recorded == "estimate" else {}
    )


def test_take_estimates_fills_the_empty_cells() -> None:
    rows = [
        {"id": "depot", "kind": "equity", "value": 100.0},
        {"id": "fest", "kind": "term_deposit", "value": 1000.0},
        {"id": "giro", "kind": "cash", "value": 1.0},
        {"id": "loan", "kind": "loan", "balance": -1000.0},
        {"id": "fetched", "kind": "equity", "value": 200.0},
    ]
    shown = list(enumerate(rows))
    estimates = [snapshot.Estimate(v) for v in (120.0, 1050.0, None, -900.0, 200.0)]
    entered: snapshot.Cells = {0: {"cost_basis": 90.0}, 3: {"new": -950.0}}
    filled, skipped = snapshot.take_estimates(shown, estimates, entered)
    # a typed value wins, a deposit keeps the amount invested, an unchanged value its date
    assert filled == {0: {"cost_basis": 90.0, "new": 120.0}, 3: {"new": -950.0}}
    assert skipped == {snapshot.DEPOSIT: ["fest"], snapshot.EQUAL: ["fetched"]}
    assert snapshot.took(1, skipped) == (
        f"Took 1 estimate, skipped 2: fest ({snapshot.DEPOSIT}); fetched ({snapshot.EQUAL})"
    )
    assert snapshot.take_estimates(shown, estimates, filled)[0] == filled
    # a tick of `unchanged` confirms the value as it is: no estimate, no reason to name it
    confirmed: snapshot.Cells = {**filled, 4: {snapshot.SAME: True}}
    assert snapshot.take_estimates(shown, estimates, confirmed)[1] == {snapshot.DEPOSIT: ["fest"]}
    edits, _ = snapshot.snapshot_edits(shown, estimates, filled, date(2026, 9, 28))
    assert edits.edited[0] == {"value": 120.0, "cost_basis": 90.0, "asof": date(2026, 9, 28)}
