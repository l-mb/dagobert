"""Input model rules that the loader tests do not reach."""

from __future__ import annotations

import re
from contextlib import AbstractContextManager, nullcontext
from datetime import date

import pytest
from builders import PHASES, cash, started
from pydantic import BaseModel, ValidationError

from dagobert.loader import adjust
from dagobert.lots import TradeKind
from dagobert.model.assets import (
    Asset,
    Assets,
    CryptoAsset,
    EquityAsset,
    GoldAsset,
    HoldingsAsset,
    Loan,
    LotAsset,
    PensionPolicy,
    PropertyAsset,
    Trade,
)
from dagobert.model.assumptions import Assumptions, Vpw, phase_name, phase_name_for
from dagobert.model.base import EACH, Strict, Unit, named, units
from dagobert.model.events import (
    AddStreamEvent,
    BuyPropertyEvent,
    RepayEvent,
    SaleTrigger,
    SellEvent,
    SetStreamEvent,
    Shift,
)
from dagobert.model.plan import AppSettings, Plan, Scenario
from dagobert.model.streams import Cashflows, Stream, StreamKind
from dagobert.model.taxes import Land, transfer_tax_rate

ISIN = "IE00B4L5Y983"
BUY = Trade(date=date(2020, 3, 1), kind=TradeKind.BUY, security=ISIN, units=10, amount=400)


def _refused(problem: str | None, *, literal: bool = False) -> AbstractContextManager[object]:
    """Nothing for a valid row, else the error that names `problem` (a regex, or the text itself
    with `literal`)."""
    if problem is None:
        return nullcontext()
    return pytest.raises(ValidationError, match=re.escape(problem) if literal else problem)


def test_trade_shape() -> None:
    with pytest.raises(ValidationError, match="security"):
        Trade(date=date(2020, 3, 1), kind=TradeKind.BUY, security="IE00B4L5Y98", units=1, amount=1)
    with pytest.raises(ValidationError, match="units belong to a buy or sale"):
        Trade(date=date(2020, 3, 1), kind=TradeKind.BUY, security=ISIN, amount=1)
    with pytest.raises(ValidationError, match="units belong to a buy or sale"):
        Trade(
            date=date(2021, 1, 4), kind=TradeKind.VORABPAUSCHALE, security=ISIN, units=1, amount=1
        )
    with pytest.raises(ValidationError, match="in January"):
        Trade(date=date(2020, 12, 31), kind=TradeKind.VORABPAUSCHALE, security=ISIN, amount=1)


def test_basis_comes_from_the_lots_with_their_vorabpauschale() -> None:
    vp = Trade(date=date(2021, 1, 4), kind=TradeKind.VORABPAUSCHALE, security=ISIN, amount=10)
    depot = EquityAsset(id="d", kind="equity", value=1000, trades=[BUY, BUY, vp])
    assert depot.basis == 810


def test_equity_needs_trades_or_a_cost_basis() -> None:
    assert EquityAsset(id="d", kind="equity", value=1000, cost_basis=500).basis == 500
    with pytest.raises(ValidationError, match="not both"):
        EquityAsset(id="d", kind="equity", value=1000)
    with pytest.raises(ValidationError, match="not both"):
        EquityAsset(id="d", kind="equity", value=1000, cost_basis=500, trades=[BUY])


def test_trades_must_replay() -> None:
    sell = Trade(date=date(2021, 1, 1), kind=TradeKind.SELL, security=ISIN, units=11, amount=500)
    with pytest.raises(ValidationError, match=r"d: sale of .* 1 units more than held"):
        EquityAsset(id="d", kind="equity", value=1000, trades=[BUY, sell])


def test_loan_balance_follows_the_schedule() -> None:
    loan = Loan(
        id="l", kind="loan", balance=-1000.0, rate=0.12, annuity=110.0, asof=date(2026, 1, 15)
    )
    assert loan.balance_at(date(2026, 3, 1), 0.04) == pytest.approx(-799.0)
    assert loan.balance_at(date(2030, 1, 1), 0.04) == 0.0
    assert loan.model_copy(update={"asof": None}).balance_at(date(2026, 3, 1), 0.04) is None
    # after the Zinsbindung the refinance rate applies: February at 12%, March at 0%
    refinanced = loan.model_copy(update={"fixed_until": date(2026, 2, 1)})
    assert refinanced.balance_at(date(2026, 3, 1), 0.0) == pytest.approx(-900.0 + 110.0)


@pytest.mark.parametrize(
    ("stream", "problem"),
    [
        ({"amount": -100, "health": "kv", "deductible": 0.8}, None),
        ({"amount": -100, "deductible": 0.5}, "belongs to a `health` premium"),
        ({"amount": 100}, "expense needs a non-positive amount"),
        ({"kind": "salary", "gross": 1000, "taxable": False}, "salary takes no taxable"),
        ({"kind": "salary", "gross": 1000}, None),
        ({"kind": "salary"}, "salary needs gross"),
        (
            {"kind": "salary", "points": 10, "point_value": 40},
            "salary takes no point_value, points",
        ),
        ({"kind": "salary", "gross": 1000, "amount": 900}, "kind salary takes no amount"),
        ({"amount": -1, "gross": 1, "points": 2, "part": 0.5}, "takes no gross, part, points"),
        ({"kind": "alg1", "amount": 1, "gross": 1}, "kind alg1 takes no amount, gross"),
        ({"kind": "alg1", "sperrzeit": True}, None),
        ({"kind": "alg1", "training": True, "sperrzeit": True}, "a course takes no Sperrzeit"),
        ({"kind": "salary", "gross": 1000, "sperrzeit": True}, "salary takes no sperrzeit"),
        ({"kind": "other_income", "amount": 1, "health": "kv"}, "other_income takes no health"),
        ({"kind": "other_income", "amount": 500, "property": "flat"}, None),  # a rent
        ({"amount": -60, "property": "flat"}, None),  # a cost of letting
        (
            {"kind": "other_income", "amount": 500, "property": "flat", "taxable": False},
            "the rent of a property is taxable",
        ),
        ({"kind": "salary", "gross": 1000, "property": "flat"}, "kind salary takes no property"),
        ({"amount": -60, "health": "kv", "property": "flat"}, "let property is no health premium"),
    ],
)
def test_a_stream_takes_the_fields_of_its_kind(
    stream: dict[str, object], problem: str | None
) -> None:
    with _refused(problem):
        Stream.model_validate({"name": "s"} | stream)


def test_a_basisrente_pays_no_lump_sum() -> None:
    """§10 Abs. 1 Nr. 2 S. 2 EStG: a Basisrente is not kapitalisierbar."""
    policy = {"id": "r", "kind": "bav", "value": 0, "contribution": 0, "phases": []}
    policy |= {"matures": date(2040, 1, 1), "basisrente": True}
    PensionPolicy.model_validate(policy | {"payout": "annuity", "annuity_per_10k": 40})
    with pytest.raises(ValidationError, match="r: a Basisrente pays an annuity, no lump sum"):
        PensionPolicy.model_validate(policy)


@pytest.mark.parametrize(
    ("stream", "problem"),
    [
        ({"kind": "self_employed", "amount": -2000, "hebesatz": 4.1}, None),  # a loss
        ({"kind": "self_employed", "amount": 9000, "hebesatz": 1.5}, "greater than or equal to 2"),
        (
            {"kind": "other_income", "amount": 9000, "hebesatz": 4.1},
            "kind other_income takes no hebesatz",
        ),
        ({"kind": "self_employed"}, "needs amount"),
    ],
)
def test_a_self_employed_profit_may_be_negative_and_takes_a_hebesatz_of_200_percent(
    stream: dict[str, object], problem: str | None
) -> None:
    """§16 Abs. 4 S. 2 GewStG: a Hebesatz of at least 200%, only of a business."""
    with _refused(problem):
        Stream.model_validate({"name": "b"} | stream)


PLAN = {"name": "ETF", "kind": "savings", "amount": -500}


@pytest.mark.parametrize(
    ("stream", "problem"),
    [
        (PLAN, None),
        (PLAN | {"amount": 500}, "savings needs a non-positive amount"),
        (PLAN | {"cat": "invest"}, "kind savings takes no cat"),
        (PLAN | {"health": "kv"}, "kind savings takes no health"),
        (PLAN | {"repays": "loan", "index": None}, "kind savings takes no repays"),
        ({"name": "rent", "amount": -500, "into": "depot"}, "kind expense takes no into"),
    ],
)
def test_a_savings_plan_spends_nothing(stream: dict[str, object], problem: str | None) -> None:
    with _refused(problem):
        Stream.model_validate(stream)


def test_a_savings_plan_runs_nominal() -> None:
    """A broker runs a plan nominal: its default index is null, an explicit one stays."""
    assert Stream.model_validate(PLAN).index is None
    assert Stream.model_validate(PLAN | {"index": "cpi"}).index == "cpi"


GOLD = {"id": "g", "kind": "gold", "value": 3000}
XAU = {"date": date(2025, 5, 12), "kind": "buy", "security": "XAU", "units": 3.2, "amount": 9100}


@pytest.mark.parametrize(
    ("model", "asset", "problem"),
    [
        (GoldAsset, GOLD | {"trades": [XAU, XAU | {"security": ISIN}]}, None),  # bars and an ETC
        (CryptoAsset, GOLD | {"kind": "crypto", "trades": [XAU | {"security": "BTC"}]}, None),
        (EquityAsset, {"id": "d", "kind": "equity", "value": 1, "trades": [XAU]}, "is no ISIN"),
        (
            GoldAsset,
            GOLD
            | {
                "trades": [
                    XAU,
                    XAU | {"kind": "vorabpauschale", "date": date(2026, 1, 5), "units": None},
                ]
            },
            "a Vorabpauschale belongs to a fund",
        ),
        (GoldAsset, GOLD | {"tax": "capital"}, "tax: capital needs trades"),
    ],
)
def test_gold_and_crypto_hold_lots_of_a_symbol_or_an_isin(
    model: type[HoldingsAsset], asset: dict[str, object], problem: str | None
) -> None:
    with _refused(problem):
        model.model_validate(asset)


@pytest.mark.parametrize(
    ("model", "kind", "growth"), [(GoldAsset, "gold", "gold"), (CryptoAsset, "crypto", "bitcoin")]
)
def test_gold_and_crypto_grow_by_their_class_and_sell_privately(
    model: type[LotAsset], kind: str, growth: str
) -> None:
    found = model.model_validate(GOLD | {"kind": kind})
    assert (found.growth, found.tax) == (growth, "private_sale")


CLASSES = ("equity", "fixed_income", "cash", "property")


def _plan(
    streams: list[Stream],
    scenario: Scenario,
    assets: tuple[Asset, ...] = (),
    returns: dict[str, dict[str, float]] | None = None,
    **more: object,
) -> Plan:
    assumptions = Assumptions.model_validate(
        {
            "person": {"born": date(1977, 1, 1)},
            "start": date(2026, 1, 1),
            "phases": PHASES,
            "returns": {c: {"mean": 0.0} for c in CLASSES} | (returns or {}),
            **more,
        }
    )
    return Plan(
        assumptions=assumptions,
        assets=[cash(), *assets],
        streams=streams,
        scenario=started(scenario, assumptions.start),
    )


@pytest.mark.parametrize(
    ("returns", "problem"),
    [
        ({"bitcoin": {"mean": 0.3, "stdev": 0.85, "equity_correlation": 0.4}}, None),
        ({"bitcoin": {"mean": 0.3, "equity_correlation": 1.5}}, "less than or equal to 1"),
        ({"equity": {"mean": 0.05, "equity_correlation": 0.5}}, "belongs to another class"),
        ({}, "the return class bitcoin is not defined"),
    ],
)
def test_a_return_class_correlates_with_equity(
    returns: dict[str, dict[str, float]], problem: str | None
) -> None:
    coins = (CryptoAsset(id="w", kind="crypto", value=1000),)
    with _refused(problem):
        _plan([], Scenario(name="s"), coins, returns)


SALE = {"type": "sell", "at": date(2027, 1, 1), "id": "x"}


@pytest.mark.parametrize(
    ("event", "problem"),
    [
        (SALE | {"asset": "g", "share": 0.5, "then": [{"invest": "portfolio"}]}, None),
        (SALE | {"asset": "g", "price": 100}, "sell g: price only for the sale of a property"),
        (SALE | {"asset": "g", "taxable": True, "end_tagged": False}, "taxable, end_tagged only"),
        (SALE | {"asset": "flat", "share": 0.5}, "share only for the sale of gold or crypto"),
        (SALE | {"asset": "flat", "price": 0}, None),
        (SALE | {"asset": "flat", "price": 0, "taxable": True}, r"gift \(price 0\) is no taxable"),
        (SALE | {"type": "buy", "asset": "g", "amount": 500}, None),
        (
            SALE | {"type": "buy", "asset": "flat", "amount": 500},
            "no gold or crypto asset has the id flat",
        ),
    ],
)
def test_a_sale_or_a_purchase_fits_its_asset(event: dict[str, object], problem: str | None) -> None:
    """The checks read values: an override that moves the event writes every field."""
    scenario = adjust(
        Scenario.model_validate({"name": "s", "events": [event]}), {"shift": {"x": 1}}
    )
    assets = (
        GoldAsset.model_validate(GOLD),
        PropertyAsset(id="flat", kind="property", sqm=50, per_sqm=4000),
    )
    with _refused(problem):
        _plan([], scenario, assets, {"gold": {"mean": 0.05}})


def test_plan_rejects_references_to_unknown_assets() -> None:
    vl = Stream(name="vl", kind=StreamKind.OTHER_INCOME, amount=40, index=None, repays="nope")
    with pytest.raises(ValidationError, match="no loan has the id nope"):
        _plan([vl], Scenario(name="s"))
    sell = SellEvent(at=date(2027, 1, 1), type="sell", asset="nope")
    with pytest.raises(ValidationError, match="no property, gold or crypto asset has the id nope"):
        _plan([], Scenario(name="s", events=[sell]))
    repay = RepayEvent(at=date(2027, 1, 1), type="repay", loan="nope")
    with pytest.raises(ValidationError, match="no loan has the id nope"):
        _plan([], Scenario(name="s", events=[repay]))
    rent = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=500, property="nope")
    with pytest.raises(ValidationError, match="no property has the id nope"):
        _plan([rent], Scenario(name="s"))
    loan = Loan(id="l", kind="loan", balance=-1000, rate=0.0, annuity=100, finances="nope")
    with pytest.raises(ValidationError, match="no property has the id nope"):
        _plan([], Scenario(name="s"), (loan,))


LET = {"bought_for": 200_000, "bought": date(2018, 3, 1), "building_share": 0.7, "afa": 0.02}


@pytest.mark.parametrize(
    ("let", "missing"),
    [(LET, []), ({}, list(LET)), ({k: v for k, v in LET.items() if k != "afa"}, ["afa"])],
)
def test_a_let_property_needs_its_purchase_and_its_afa(
    let: dict[str, object], missing: list[str]
) -> None:
    """No default sets a tax base in silence: a property that a rent names needs `bought_for`,
    `bought`, `building_share` and `afa` (0 for none), each a problem at its field. A cost of
    letting alone, or a loan that `finances` it, makes no property let."""
    flat = PropertyAsset.model_validate(
        {"id": "flat", "kind": "property", "sqm": 50, "per_sqm": 4000} | let
    )
    rent = Stream(name="rent", kind=StreamKind.OTHER_INCOME, amount=500, property="flat")
    cost = Stream(name="Hausgeld", amount=-100, property="flat")
    _plan([cost], Scenario(name="s"), (flat.model_copy(update=dict.fromkeys(LET)),))
    if not missing:
        _plan([rent, cost], Scenario(name="s"), (flat,))
        return
    with pytest.raises(ValidationError) as caught:
        _plan([rent, cost], Scenario(name="s"), (flat,))
    errors = caught.value.errors()
    assert [e["loc"] for e in errors] == [("assets", 1, name) for name in missing]
    assert "the stream rent names flat as its property, so flat is let" in errors[0]["msg"]


def test_a_property_of_the_file_is_bought_by_the_start() -> None:
    """A later purchase is a `buy_property`: a `bought` after `start` would count the AfA and the
    ten years of §23 EStG from before the purchase."""
    flat = {"id": "flat", "kind": "property", "sqm": 50, "per_sqm": 4000}
    _plan([], Scenario(name="s"), (PropertyAsset.model_validate(flat | LET),))
    later = PropertyAsset.model_validate(flat | LET | {"bought": date(2026, 2, 1)})
    with pytest.raises(ValidationError) as caught:
        _plan([], Scenario(name="s"), (later,))
    errors = caught.value.errors()
    assert [e["loc"] for e in errors] == [("assets", 1, "bought")]
    assert errors[0]["msg"].startswith("flat is bought after the start 2026-01: a later purchase")


PURCHASE = {"type": "buy_property", "at": date(2028, 4, 1), "property": {"id": "home"}}
PURCHASE |= {"price": 300_000, "land": "NI"}
LOAN = {"id": "home-loan", "balance": -300_000, "rate": 0.03, "annuity": 1500}


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({}, None),
        ({"transfer_tax": 0.0}, "needs exactly one of `land` and `transfer_tax`"),
        ({"land": None}, "needs exactly one of `land` and `transfer_tax`"),
        ({"land": None, "transfer_tax": 0.0, "loan": LOAN}, None),
        ({"loan": LOAN | {"balance": -315_001}}, "more than the price with tax and costs, 315.000"),
        ({"costs": 0.05, "loan": LOAN | {"balance": -330_000}}, None),
        ({"at": date(1996, 12, 1)}, "no Grunderwerbsteuer of NI before 1997-01-01"),
    ],
)
def test_a_purchase_takes_a_land_or_a_rate_and_a_loan_up_to_its_cost(
    change: dict[str, object], problem: str | None
) -> None:
    with _refused(problem):
        BuyPropertyEvent.model_validate(PURCHASE | change)


def test_every_land_has_the_rate_of_the_law_since_1997() -> None:
    """§11 Abs. 1 GrEStG: 3.5% since 1997, until a Land sets its own rate."""
    assert {transfer_tax_rate(land, date(1997, 1, 1)) for land in Land} == {0.035}
    assert transfer_tax_rate(Land.HB, date(2025, 6, 30)) < transfer_tax_rate(
        Land.HB, date(2025, 7, 1)
    )


VL = {"name": "vl", "kind": "other_income", "amount": 40, "index": None, "repays": "home-loan"}
RENT = {"name": "rent", "kind": "other_income", "amount": 900, "property": "home"}
HOME = {"id": "home", "building_share": 0.8, "afa": 0.02}  # let: it needs its AfA
EARLY, LATER, RETIRED = date(2027, 1, 1), date(2030, 1, 1), date(2035, 1, 1)


@pytest.mark.parametrize(
    ("events", "vl", "problem"),
    [
        (
            [
                PURCHASE | {"loan": LOAN},
                {"type": "sell", "at": LATER, "asset": "home", "then": [{"repay": "home-loan"}]},
                {"type": "sell", "when": {"age": 50}, "asset": "home"},  # waits for the purchase
            ],
            VL | {"start": date(2028, 5, 1), "after_sale_of": "home"},
            None,
        ),
        ([PURCHASE | {"property": {"id": "flat"}}], None, "the id flat is taken"),
        ([PURCHASE | {"loan": LOAN | {"id": "home"}}], None, "the id home is taken"),
        ([PURCHASE, PURCHASE | {"at": LATER}], None, "the id home is taken"),
        (
            [PURCHASE, {"type": "sell", "at": date(2028, 4, 1), "asset": "home"}],
            None,
            "sell of 2028-04 names home in or before the month of the buy_property that brings "
            "it, 2028-04",
        ),
        (
            [
                PURCHASE | {"loan": LOAN},
                {"type": "repay", "at": LATER, "loan": "home-loan"},
                {"type": "repay", "at": date(2027, 1, 1), "loan": "home-loan"},
            ],
            None,
            "repay of 2027-01 names home-loan",
        ),
        ([PURCHASE | {"loan": LOAN}], VL, "the stream vl names home-loan"),
        ([PURCHASE | {"loan": LOAN}], VL | {"phases": ["work"]}, "the stream vl names home-loan"),
        ([PURCHASE | {"loan": LOAN}], VL | {"phases": ["retired"]}, None),  # from RETIRED on
        ([PURCHASE | {"loan": LOAN}], VL | {"phases": ["alt"]}, None),  # never pays
        ([PURCHASE | {"loan": LOAN}], VL | {"start": EARLY, "end": EARLY}, None),  # ends first
        *(
            (
                [PURCHASE | {"loan": LOAN}, {"type": "add_stream", "at": EARLY, "stream": stream}],
                None,
                problem,
            )
            for stream, problem in (
                (VL | {"start": LATER}, None),
                (VL | {"phases": ["retired"]}, None),
                (VL | {"phases": ["work"]}, "add_stream of 2027-01 names home-loan"),
            )
        ),
        (
            [PURCHASE | {"property": {"id": "home", "growth": "nope"}}],
            None,
            "the return class nope is not defined",
        ),
        *(
            (
                [PURCHASE | {"property": HOME}, {"type": "add_stream", "at": at, "stream": RENT}],
                None,
                problem,
            )
            for at, problem in ((LATER, None), (EARLY, "add_stream of 2027-01 names home"))
        ),
        (
            [PURCHASE, {"type": "add_stream", "at": LATER, "stream": RENT}],
            None,
            "the stream rent names home as its property, so home is let",
        ),
    ],
)
def test_a_purchase_brings_new_ids_that_nothing_uses_before_it(
    events: list[dict[str, object]], vl: dict[str, object] | None, problem: str | None
) -> None:
    """A stream names them from the first month in which it pays: by its `start`, its own or of
    its `add_stream`, and its `phases`."""
    scenario = Scenario.model_validate(
        {"name": "s", "phases": [{"from": RETIRED, "phase": "retired"}], "events": events}
    )
    streams = [Stream.model_validate(vl)] if vl else []
    flat = PropertyAsset(id="flat", kind="property", sqm=50, per_sqm=4000)
    with _refused(problem):
        _plan(streams, scenario, (flat,))


@pytest.mark.parametrize(
    ("into", "scale", "problem"),
    [
        ("depot", {"ETF": 2.0}, None),
        ("g", {}, None),
        ("flat", {}, "no equity, fixed-income, gold or crypto asset has the id flat"),
        ("nope", {}, "no equity, fixed-income, gold or crypto asset has the id nope"),
        ("depot", {"Rent": 2.0}, "no stream of kind savings has the name Rent"),
    ],
)
def test_a_savings_plan_buys_equity_fixed_income_gold_or_crypto(
    into: str, scale: dict[str, float], problem: str | None
) -> None:
    """Also as the stream of an `add_stream` event."""
    added = AddStreamEvent(
        at=date(2027, 1, 1), type="add_stream", stream=Stream.model_validate(PLAN | {"into": into})
    )
    assets = (
        EquityAsset(id="depot", kind="equity", value=1000, cost_basis=1000),
        GoldAsset.model_validate(GOLD),
        PropertyAsset(id="flat", kind="property", sqm=50, per_sqm=4000),
    )
    rent = Stream(name="Rent", cat="housing", amount=-800)
    scenario = Scenario(name="s", events=[added])
    with _refused(problem):
        _plan([rent], scenario, assets, {"gold": {"mean": 0.0}}, scale={"savings": scale})


@pytest.mark.parametrize(
    ("stream", "problem"),
    [
        ({"amount": -1, "index": "nosuch"}, r"stream\.index\n .*the index nosuch is"),
        (
            {"kind": "salary", "of": "nosuch", "share": 0.1, "every": 12},
            r"stream\.of\n .*no salary stream without `of` has the name nosuch",
        ),
        ({"amount": -1, "after_sale_of": "nosuch"}, r"after_sale_of\n .*no property"),
        (
            {"kind": "other_income", "amount": 40, "index": None, "repays": "nosuch"},
            r"stream\.repays\n .*no loan has the id nosuch",
        ),
    ],
    ids=["index", "of", "after_sale_of", "repays"],
)
def test_an_added_stream_names_what_the_plan_has(stream: dict[str, object], problem: str) -> None:
    """The engine would fail on the unknown name, or never pay."""
    added = {"at": EARLY, "type": "add_stream", "stream": {"name": "x"} | stream}
    with pytest.raises(ValidationError, match=problem):
        _plan([], Scenario.model_validate({"name": "s", "events": [added]}))


@pytest.mark.parametrize(
    ("event", "problem"),
    [
        ({"type": "end_streams"}, "end_streams: needs names or tags"),
        (
            {"type": "set_stream", "name": "rent"},
            "set_stream rent: needs amount, gross, premium or factor",
        ),
    ],
)
def test_a_stream_event_changes_something(event: dict[str, object], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        Scenario.model_validate({"name": "s", "events": [event | {"at": EARLY}]})


def test_asset_ids_are_unique() -> None:
    asset = {"kind": "cash", "value": 1}
    with pytest.raises(ValidationError, match="asset ids must be unique: c more than once"):
        Assets.model_validate(
            {"assets": [asset | {"id": "c"}, asset | {"id": "d"}, asset | {"id": "c"}]}
        )


def test_plan_rejects_two_streams_with_the_same_name_and_start() -> None:
    with pytest.raises(
        ValidationError,
        match=r"streams\.1\.name\n .*another stream has the name x and the same start",
    ):
        _plan([Stream(name="x", amount=-1), Stream(name="x", amount=-2)], Scenario(name="s"))


SET = "set_stream of 2027-01 names the stream x, which is neither in cashflows.yaml"
END = "end_streams of 2027-01 names the {} x, which"


@pytest.mark.parametrize(
    ("events", "abstract", "problem"),
    [
        (
            [{"type": "end_streams", "names": ["rent", "x"]}],
            False,
            rf"names\.1\n *{END.format('stream')}",
        ),
        ([{"type": "set_stream", "name": "x", "amount": -1}], False, rf"events\.0\.name\n *{SET}"),
        ([{"type": "set_stream", "name": "x", "amount": -1}], True, None),  # a template
        (
            [
                {"type": "set_stream", "name": "job", "gross": 4000},
                {"type": "add_stream", "stream": {"name": "job", "kind": "salary", "gross": 1}},
            ],
            False,
            None,
        ),
        (
            [{"type": "end_streams", "tags": ["home", "x"]}],
            False,
            rf"tags\.1\n *{END.format('tag')}",
        ),
        (
            [
                {"type": "end_streams", "tags": ["job"]},
                {"type": "add_stream", "stream": {"name": "job", "amount": -1, "tags": ["job"]}},
            ],
            False,
            None,
        ),
    ],
)
def test_stream_events_name_streams_and_tags_of_the_plan(
    events: list[dict[str, object]], *, abstract: bool, problem: str | None
) -> None:
    """An unknown name or tag would change nothing. A template leaves the check to its
    children. The message names the event, so a renamed stream shows as the cause."""
    scenario = Scenario.model_validate(
        {"name": "s", "abstract": abstract, "events": [e | {"at": EARLY} for e in events]}
    )
    rent = Stream(name="rent", amount=-500, tags=["home"])
    with _refused(problem):
        _plan([rent], scenario)


UPDATE = "set_stream of 2027-01 sets {} of the stream {}: {}"
FUNDED = {"policy": "r", "amount": 1}


@pytest.mark.parametrize(
    ("event", "problem"),
    [
        ({"name": "rent", "amount": -600}, None),
        ({"name": "rent", "amount": 1000}, ("amount", "rent", "expense needs a non-positive")),
        ({"name": "rent", "gross": 1000}, ("gross", "rent", "it takes amount")),
        ({"name": "rv", "amount": 100}, ("amount", "rv", "rv_voluntary needs a negative amount")),
        ({"name": "job", "gross": 5000}, None),
        ({"name": "job", "amount": 5000}, ("amount", "job", "it takes gross")),
        ({"name": "bonus", "gross": 5000}, ("gross", "bonus", "it takes no amount")),
        ({"name": "rente", "gross": 1500}, None),  # a fixed gross replaces the points
        ({"name": "bu", "premium": -50}, None),
        (
            {"name": "bu", "factor": 0.5},
            ("factor", "bu", "a BU policy runs by its contract, not by phase"),
        ),
        ({"name": "bu", "factor": 0.5, "gross": 900}, ("gross", "bu", "it takes amount")),
    ],
)
def test_set_stream_keeps_the_rows_of_its_name_valid(
    event: dict[str, object], problem: tuple[str, str, str] | None
) -> None:
    """The engine takes the changed row as a row of `cashflows.yaml`: a sign typo of an expense
    would invest money that does not exist, a field that the kind does not read changes
    nothing."""
    streams = [
        Stream(name="rent", amount=-500),
        Stream(name="rv", kind=StreamKind.RV_VOLUNTARY, amount=-100),
        Stream(name="job", kind=StreamKind.SALARY, gross=4000),
        Stream(name="bonus", kind=StreamKind.SALARY, of="job", share=0.1, every=12),
        Stream(name="rente", kind=StreamKind.PENSION, points=30, point_value=40),
        Stream(name="bu", kind=StreamKind.BU, amount=1000, premium=-60),
    ]
    scenario = Scenario.model_validate(
        {"name": "s", "events": [event | {"at": EARLY, "type": "set_stream"}]}
    )
    with _refused(problem and UPDATE.format(*problem), literal=True):
        _plan(streams, scenario)


@pytest.mark.parametrize(
    ("rows", "abstract", "refused"),
    [
        ([{"end": date(2026, 6, 1)}], False, True),
        ([{"end": EARLY}], False, True),  # `end` is the first month without it
        ([{"end": date(2026, 6, 1)}, {"start": date(2028, 1, 1)}], False, False),  # the next row
        ([{"end": date(2026, 6, 1)}], True, False),  # a scenario that extends it may add a row
    ],
    ids=["ended", "ends-at-it", "later-row", "template"],
)
def test_set_stream_changes_a_row_of_its_name(
    rows: list[dict[str, object]], *, abstract: bool, refused: bool
) -> None:
    """A `set_stream` after every row of its name ended would change nothing in silence."""
    streams = [Stream.model_validate({"name": "rent", "amount": -500} | row) for row in rows]
    event = {"type": "set_stream", "at": EARLY, "name": "rent", "amount": -600}
    scenario = Scenario.model_validate({"name": "s", "abstract": abstract, "events": [event]})
    with _refused("changes no row of rent: every row ended" if refused else None):
        _plan(streams, scenario)


@pytest.mark.parametrize(
    ("events", "problem"),
    [
        ([{"type": "lump_sum", "at": date(2025, 12, 1), "amount": 1}], "lies before the start"),
        ([{"type": "set_stream", "at": date(2025, 12, 1), "name": "rent", "amount": -1}], None),
        ([{"type": "fund_policy", "at": date(2030, 1, 1), "policy": "r", "amount": 1}], None),
        (
            [{"type": "fund_policy", "at": date(2030, 2, 1), "policy": "r", "amount": 1}],
            "fund_policy of 2030-02 funds the policy r, which pays out in 2030-01",
        ),
        ([{"type": "severance", "at": date(2031, 1, 1), "gross": 9}], None),
        (
            [{"type": "severance", "at": date(2031, 1, 1), "gross": 9, "bav": FUNDED}],
            "severance of 2031-01 funds the policy r",
        ),
    ],
)
@pytest.mark.parametrize("abstract", [False, True])
def test_a_dated_event_lies_where_the_run_takes_it(
    events: list[dict[str, object]], problem: str | None, *, abstract: bool
) -> None:
    """Before the start only the stream events apply, a policy takes funding up to its payout:
    a refusal of the model names the line of the event, a run would end in a traceback. A
    template leaves the check to the scenarios that extend it, which may drop the event. A
    `fund_policy` pays into a Basisrente, a severance into a company pension."""
    basisrente = any(e["type"] == "fund_policy" for e in events)
    policy = PensionPolicy.model_validate(
        {"id": "r", "kind": "bav", "value": 0, "phases": [], "matures": date(2030, 1, 1)}
        | {"growth": "cash", "basisrente": basisrente}
        | ({"payout": "annuity", "annuity_per_10k": 40} if basisrente else {})
    )
    scenario = Scenario.model_validate({"name": "s", "abstract": abstract, "events": events})
    streams = [Stream(name="rent", amount=-500)]
    with _refused(None if abstract else problem):
        _plan(streams, scenario, (policy,))


@pytest.mark.parametrize(
    ("stream", "when", "problem"),
    [
        ({"after_sale_of": "flat"}, {"liquid_below": 1000}, "starts the stream vl on some paths"),
        ({"tags": ["flat"]}, {"liquid_below": 1000}, "the sale of flat at `liquid_below` ends"),
        ({"property": "flat"}, {"liquid_below": 1000}, "the sale of flat at `liquid_below` ends"),
        ({"tags": ["flat"]}, {"age": 60}, None),  # the same month on every path
        ({}, {"liquid_below": 1000}, None),
    ],
)
def test_a_stream_that_repays_a_loan_pays_alike_on_every_path(
    stream: dict[str, object], when: dict[str, object], problem: str | None
) -> None:
    """The loan is one for all paths: a sale on the liquid wealth would end or start the
    repayment on some of them."""
    vl = Stream.model_validate(
        {"name": "vl", "kind": "other_income", "amount": 40, "index": None, "repays": "l"} | stream
    )
    assets = (
        PropertyAsset(
            id="flat",
            kind="property",
            sqm=1,
            per_sqm=1,
            tags=["flat"],
            bought=date(2020, 1, 1),
            bought_for=1,
            building_share=0.5,
            afa=0.02,
        ),
        Loan(id="l", kind="loan", balance=-1000, rate=0.0, annuity=10),
    )
    scenario = Scenario.model_validate(
        {"name": "s", "events": [{"type": "sell", "asset": "flat", "when": when}]}
    )
    with _refused(problem):
        _plan([vl], scenario, assets)


BORN = {"born": date(1977, 1, 1)}
CARE = {"cost": 2000, "duration": {"mean": 24}}
VPW = {"base": "no_pay", "categories": ["fun"], "vpw": {}}


@pytest.mark.parametrize(
    ("model", "data", "problem"),
    [
        (Assumptions, {"person": BORN | {"children": -1}}, "greater than or equal to 0"),
        (
            Assumptions,
            {"person": BORN | {"children": 1, "children_born": [BORN, BORN]}},
            "children_born lists 2 children, children counts 1",
        ),
        (Assumptions, {"person": BORN | {"horizon_age": 0}}, "greater than or equal to 1"),
        (Assumptions, {"inflation": {"mean": 0.02, "stdev": -0.01}}, "greater than or equal"),
        (Assumptions, {"indices": {"x": {"mean": 0.02, "stdev": -0.01}}}, "greater than or equal"),
        (Assumptions, {"indices": {"x": {"mean": 0.9, "floor": 1, "cap": 0}}}, "floor 100% is"),
        (Assumptions, {"indices": {"x": {"mean": 0.9, "floor": 1, "cap": 1}}}, None),
        (Assumptions, {"cash_buffer_months": -1}, "greater than or equal to 0"),
        (Assumptions, {"tax": {"teilfreistellung": 1.5}}, "less than or equal to 1"),
        (Assumptions, {"tax": {"sparer_pauschbetrag": -1}}, "greater than or equal to 0"),
        (Assumptions, {"tax": {"year": 2025}}, "no tax constants for 2025, only for 2026"),
        (
            Assumptions,
            {"allocation": {"fixed_income": [{"age": 60, "share": 0.2}] * 2}},
            "each age once: 60 twice",
        ),
        (
            Assumptions,
            {"spending": {"age_curve": [{"age": 70, "factor": 1}, {"age": 70, "factor": 0.8}]}},
            "each age once: 70 twice",
        ),
        (Assumptions, {"spending": {"increase": 0.1, "ceiling": 1.5}}, "needs base: no_pay"),
        (Assumptions, {"spending": {"increase": 0, "ceiling": 0.5, "trigger": 0.5}}, None),
        (Assumptions, {"spending": {"increase": 0.1, "base": "no_pay"}}, None),  # no ceiling
        (
            Assumptions,
            {"spending": {"increase": 0.1, "ceiling": 0.5, "trigger": 0.5, "base": "no_pay"}},
            r"spending\.ceiling\n.*ceiling 50% is not above trigger 50%",
        ),
        (Assumptions, {"spending": {"base": "no_pay", "reference": 250_000}}, None),
        (Assumptions, {"spending": {"base": "pay"}}, "'start' or 'no_pay'"),
        (Assumptions, {"spending": VPW}, None),
        (Assumptions, {"spending": VPW | {"base": "start"}}, r"spending\.vpw\n.*needs base"),
        (Assumptions, {"spending": VPW | {"trigger": 0.5}}, "VPW replaces the cut"),
        (Assumptions, {"spending": VPW | {"increase": 0.1}}, "VPW replaces the cut"),
        (Assumptions, {"spending": VPW | {"categories": []}}, "VPW needs the flexible"),
        (Assumptions, {"spending": VPW | {"vpw": {"growth": 0.11}}}, "less than or equal to 0.1"),
        (Assumptions, {"tax": {"capital_losses": -1}}, "greater than or equal to 0"),
        (
            Assumptions,
            {"care": CARE | {"hazard": [{"age": 80, "factor": 0.1}, {"age": 80, "factor": 0.2}]}},
            "each age once: 80 twice",
        ),
        (
            Assumptions,
            {"care": CARE | {"hazard": [{"age": 80, "factor": 2}]}},
            "less than or equal to 1",  # a probability
        ),
        (
            Assumptions,
            {"care": CARE | {"hazard": [{"age": -1, "factor": 0.1}]}},
            "greater than or equal to 0",
        ),
        (
            Assumptions,
            {"care": CARE | {"hazard": [{"age": 80, "factor": 0.1}], "duration": {"mean": -1}}},
            "greater than or equal to 0",
        ),
        (Stream, {"name": "rent", "amount": -1, "factor": {"retired": -0.5}}, "greater than"),
        (SetStreamEvent, {"at": EARLY, "type": "set_stream", "name": "x", "factor": -1}, "greater"),
        (SaleTrigger, {"age": -1}, "greater than or equal to 0"),
        (AppSettings, {"scenarios": ["base"], "model": "fixed"}, "Extra inputs are not permitted"),
        (
            EquityAsset,
            {"id": "d", "kind": "equity", "value": 1, "cost_basis": 1, "teilfreistellung": 1.5},
            "less than or equal to 1",
        ),
    ],
)
def test_a_value_out_of_bounds_is_refused(
    model: type[BaseModel], data: dict[str, object], problem: str | None
) -> None:
    if model is Assumptions:
        data = {
            "person": BORN,
            "start": EARLY,
            "phases": PHASES,
            "returns": {c: {"mean": 0.0} for c in CLASSES},
        } | data
    with _refused(problem):
        model.model_validate(data)


@pytest.mark.parametrize(
    ("phases", "problem"),
    [
        ({"work": {}, "part-time": {"label": "Teilzeit"}, "job_2": {}}, None),
        ({"on": {}}, "on is no phase name"),  # YAML 1.1 reads `[on]` as true
        ({"null": {}}, "null is no phase name"),
        ({"Teilzeit": {}}, "Teilzeit is no phase name: small letters"),  # its label has capitals
        ({"2nd": {}}, "2nd is no phase name"),
        ({}, "at least 1 item"),
        ({"a": {"label": "Job"}, "b": {"label": "Job"}}, "another phase shows as Job too"),
        ({"a": {}, "b": {"label": "a"}}, "another phase shows as a too"),
    ],
)
def test_a_phase_is_a_name_of_the_files_with_a_label_of_the_pages(
    phases: dict[str, object], problem: str | None
) -> None:
    with _refused(problem):
        Assumptions.model_validate(_with_phases(phases))


def _with_phases(phases: dict[str, object]) -> dict[str, object]:
    return {
        "person": BORN,
        "start": EARLY,
        "phases": phases,
        "returns": {c: {"mean": 0.0} for c in CLASSES},
    }


def test_a_phase_shows_its_label_else_its_name() -> None:
    phases: dict[str, object] = {"work": {}, "part-time": {"label": "Teilzeit"}}
    assert Assumptions.model_validate(_with_phases(phases)).phase_labels == {
        "work": "work",
        "part-time": "Teilzeit",
    }


@pytest.mark.parametrize(
    ("label", "name"),
    [
        ("Career break", "career-break"),
        ("Übergang in die Rente", "uebergang-in-die-rente"),  # umlauts written out
        ("On", "phase-on"),  # YAML 1.1 reads `on` as true
        ("2. Job", "phase-2-job"),
        ("Elternzeit für das zweite und dritte Kind", "elternzeit-fuer-das-zwei"),  # 24 characters
        ("Work", "work-2"),  # taken
        ("…", "phase"),
    ],
)
def test_a_new_phase_takes_a_name_from_its_label(label: str, name: str) -> None:
    assert phase_name_for(label, {"work"}) == name
    assert phase_name(name) == name


def test_units_by_key_path() -> None:
    """A mapping key and a list item are `EACH`, a discriminated union adds its tag."""
    found = units(Assumptions)
    assert found["care", "cost"] == Unit.EUR
    assert found["care", "duration", "mean"] == Unit.MONTHS
    assert found["returns", EACH, "mean"] == Unit.PERCENT
    assert found["care", "hazard", EACH, "factor"] == Unit.PERCENT  # a probability
    assert found["spending", "age_curve", EACH, "factor"] == Unit.FACTOR
    assert (found["start",], found["person", "born"]) == (Unit.MONTH, Unit.DATE)
    assert units(Assets)["assets", EACH, "term_deposit", "start"] == Unit.DATE
    assert units(Assets)["assets", EACH, "av_depot", "start"] == Unit.MONTH
    assert units(Scenario)["events", EACH, "repay", "amount"] == Unit.EUR  # or `all`
    assert units(Shift) == {(EACH,): Unit.MONTHS}  # `overrides.shift`, no model of its own


@pytest.mark.parametrize("model", [Assumptions, Assets, Cashflows, Scenario, AppSettings])
def test_every_number_and_date_has_a_unit(model: type[BaseModel]) -> None:
    """`units` refuses a number or a date without one. A choice (`tax.year`) needs none."""
    assert all(isinstance(unit, Unit) for unit in units(model).values())

    class Bare(Strict):
        share: float

    with pytest.raises(TypeError, match="share: a number or a date needs a unit"):
        units(Bare)


@pytest.mark.parametrize(
    ("key", "label"),
    [
        ("bav", "bAV"),
        ("bav_return", "bAV return"),
        ("fixed_income", "Fixed income"),
        ("flat-sale", "Flat sale"),
        ("ETF plan", "ETF plan"),
        ("", ""),
    ],
)
def test_a_key_reads_as_a_label(key: str, label: str) -> None:
    """Words apart, the first capital, an acronym as written, the rest kept."""
    assert named(key) == label


MOTHER = {"born": date(1950, 5, 1), "sex": "f", "relation": "parent"}
INHERITANCE = {"type": "inheritance", "from": "mother", "cash": 1000}


@pytest.mark.parametrize(
    ("relatives", "event", "problem"),
    [
        ({}, INHERITANCE, "no relative of person.relatives has the name mother"),
        ({"mother": MOTHER}, INHERITANCE, None),
        ({"mother": MOTHER}, INHERITANCE | {"from": ["mother", "mother"]}, None),
        ({"mother": MOTHER}, INHERITANCE | {"cash": 0}, "needs cash or equity"),
        ({"mother": MOTHER}, INHERITANCE | {"type": "gift"}, "at\n  Field required"),
        (
            {"mother": MOTHER, "father": MOTHER},
            INHERITANCE | {"type": "gift", "at": date(2028, 1, 1), "from": ["mother", "father"]},
            "a gift of two is a gift of each",
        ),
        ({"mother": MOTHER | {"born": date(1980, 1, 1)}}, None, "born after you"),
        ({"Mother": MOTHER}, None, "Mother is no relative name"),
        (
            {"mother": MOTHER | {"given": [{"at": date(2026, 3, 1), "value": 1}]}},
            None,
            "the gift of 2026-03 lies after the start 2026-01",
        ),
    ],
)
def test_inheritances_and_gifts_come_from_older_relatives_of_the_person(
    relatives: dict[str, object], event: dict[str, object] | None, problem: str | None
) -> None:
    with _refused(problem, literal=True):
        scenario = Scenario.model_validate({"name": "s", "events": [event] if event else []})
        _plan([], scenario, person={"born": date(1977, 1, 1), "relatives": relatives})


def test_one_relative_reads_as_a_list_of_one() -> None:
    """`from` names one relative or several: an override of the field reaches it by that name."""
    one = Scenario.model_validate({"name": "s", "events": [INHERITANCE | {"id": "erbe"}]})
    assert one.events[0].model_dump(by_alias=True)["from"] == ["mother"]
    moved = adjust(one, {"events": {"erbe": {"from": ["mother", "father"]}}})
    assert moved.events[0].model_dump(by_alias=True)["from"] == ["mother", "father"]


@pytest.mark.parametrize(
    ("growth", "age", "rate"),
    [
        (0.03, 70, 0.04953),  # the annuity due over 30 years
        (0.0372, 65, 0.0497),  # 60/40: the Bogleheads table, 5.0, 5.4, 6.9%
        (0.0372, 70, 0.0539),
        (0.0372, 80, 0.0692),
        (0.03, 95, 0.10),  # the cap
        (0.03, 100, 0.10),  # the last year: the whole wealth, capped
        (0.03, 130, 0.10),  # past the horizon, a year is left
        (0.0, 60, 1 / 40),  # no growth: a share of the years left
    ],
)
def test_vpw_rate_by_age(growth: float, age: float, rate: float) -> None:
    assert Vpw(growth=growth).rate_at(age) == pytest.approx(rate, abs=5e-5)
