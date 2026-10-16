"""Three runs through the engine with the mean returns, `rich_plan`, `gkv_plan` and `gkv_plan`
with `DISABLED`: their yearly totals and ledger groups are a snapshot. After an intended change,
`uv run pytest -n0 tests/test_golden.py --snapshot-update` rewrites `__snapshots__/test_golden/`,
and its diff shows the effect per year."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from typing import Any

import numpy as np
import pytest
from builders import PHASES, levels, marked, phases
from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension

from dagobert import budget, carry
from dagobert.engine.simulation import horizon_months, simulate
from dagobert.model.assets import Asset, AvDepot, Loan, PensionPolicy, TermDeposit
from dagobert.model.assumptions import Assumptions, Person
from dagobert.model.months import add_months
from dagobert.model.plan import Plan, Scenario
from dagobert.result import (
    BENEFIT,
    CAPITAL_TAX,
    CONVERSION,
    EM_RENTE,
    KRANKENGELD,
    MOVE_IN,
    MOVE_OUT,
    MOVED,
    ONEOFF_CONTRIBUTION,
    ONEOFF_IN,
    ONEOFF_OUT,
    ONEOFF_TAX,
    PURCHASE_COSTS,
    SAVINGS_PLAN,
    SOURCE,
    SPENDING,
    TAX,
    FloatArray,
    RunResult,
)
from dagobert.returns import FixedProvider, Returns


def _buy(security: str, day: date, units: float, amount: float) -> dict[str, object]:
    return {"date": day, "kind": "buy", "security": security, "units": units, "amount": amount}


KV = {"health": "kv", "cat": "versicherung", "deductible": 0.8}
STREAMS: list[dict[str, Any]] = [
    {"name": "Gehalt", "kind": "salary", "gross": 7000, "index": "salary"}
    | {"phases": ["work", "part-time"], "factor": {"part-time": 0.5}},
    {"name": "Bonus", "kind": "salary", "of": "Gehalt", "share": 0.1, "every": 12}
    | {"start": date(2026, 12, 1), "phases": ["work"], "index": "bonus"},
    {"name": "VL", "kind": "other_income", "amount": 35, "index": None, "repays": "kredit"}
    | {"phases": ["work"]},
    # the rent of the let flat: less its AfA, Hausgeld, upkeep and interest a loss
    {"name": "Miete ein", "kind": "other_income", "amount": 500, "tags": ["wohnung"]}
    | {"property": "wohnung"},
    # the Aufhebungsvertrag of the severance brings a Sperrzeit; a course with a Bildungsgutschein
    # in the second half of 2029 uses its days at half the rate, 62 days are left
    {"name": "ALG1", "kind": "alg1", "phases": ["unemployed"], "sperrzeit": True},
    {"name": "Weiterbildung", "kind": "alg1", "training": True}
    | {"start": date(2029, 7, 1), "end": date(2030, 1, 1)},
    {"name": "RV voluntary", "kind": "rv_voluntary", "amount": -110, "phases": ["alt"]},
    # a trade business with a Hebesatz and a yearly project fee beside it, the founding set
    # earlier: half the Regelbeitrag up to 2033, the full one in 2034
    {"name": "Beratung", "kind": "self_employed", "amount": 7000, "index": "salary"}
    | {"phases": ["freelance"], "hebesatz": 4.1},
    {"name": "Projekt", "kind": "self_employed", "amount": 32_000, "every": 12}
    | {"start": date(2032, 6, 1), "phases": ["freelance"]},
    {"name": "Rente", "kind": "pension", "points": 30, "point_value": 40, "phases": ["retired"]},
    {"name": "Miete", "cat": "wohnen", "amount": -1200},
    {"name": "Miete danach", "cat": "wohnen", "amount": -900, "after_sale_of": "haus"},
    {"name": "Hausgeld", "cat": "wohnen", "amount": -300, "tags": ["wohnung"]}
    | {"property": "wohnung"},
    {"name": "Essen", "cat": "base", "amount": -600},
    {"name": "Hausrat", "cat": "versicherung", "amount": -300, "every": 12},
    # half of the gifts are donations (§10b), the cleaning a household service (§35a)
    {"name": "Geschenke", "cat": "base", "amount": -200, "deduct": "donation", "deductible": 0.5},
    {"name": "Putzhilfe", "cat": "wohnen", "amount": -150, "deduct": "household"},
    # a course paid by the person in the career break, work expenses without a salary: the loss
    # of 2030 beyond its capital income goes back into the severance year 2029 (§10d Abs. 1, §34
    # Abs. 1 S. 3 EStG), whose refund comes in December 2031
    {"name": "Kurs", "cat": "bildung", "amount": -5000, "deduct": "work"}
    | {"start": date(2030, 5, 1), "end": date(2030, 11, 1)},
    {"name": "PKV", "amount": -700, "index": "insurance"} | KV,
    {"name": "PKV Pflege", "amount": -70, "health": "pv", "cat": "versicherung"},
    # a BU policy to 65: its premium, as the fixed run draws no disability
    {"name": "BU", "kind": "bu", "cat": "versicherung", "amount": 2500, "premium": -80}
    | {"until_age": 65},
    # nominal, beside the investing of the rest: the Bitcoin buy of 2027-03 drains the cash, the
    # marker names that first pause; a month of ALG1 in 2029 pauses it again
    {"name": "ETF-Sparplan", "kind": "savings", "amount": -1500, "phases": ["work", "unemployed"]},
    {"name": "BTC-Sparplan", "kind": "savings", "amount": -150, "into": "btc", "every": 3}
    | {"start": date(2026, 2, 1), "end": date(2029, 1, 1)},  # young lots, §20 from 2027
]
ASSETS: list[dict[str, Any]] = [
    {"id": "giro", "kind": "cash", "value": 20_000},
    {"id": "tagesgeld", "kind": "fixed_income", "value": 30_000},
    {"id": "depot", "kind": "equity", "value": 180_000, "cost_basis": 135_000},
    {"id": "immo", "kind": "equity", "value": 20_000, "cost_basis": 15_000}
    | {"teilfreistellung": 0.6},  # an offener Immobilienfonds
    {"id": "rsu", "kind": "equity", "value": 6000, "cost_basis": 4000}  # shares, forfeited
    | {"teilfreistellung": 0},
    {"id": "festgeld", "kind": "term_deposit", "value": 20_000, "rate": 0.03}
    | {"start": date(2025, 6, 1), "matures": date(2027, 6, 1)},
    # let since its purchase: a sale within ten years is taxable, its basis less the AfA
    {"id": "wohnung", "kind": "property", "sqm": 60, "per_sqm": 5000, "upkeep": 0.01}
    | {"tags": ["wohnung"], "bought_for": 250_000, "bought": date(2019, 6, 1)}
    | {"afa": 0.02, "building_share": 0.8},
    {"id": "kredit", "kind": "loan", "balance": -80_000, "rate": 0.02, "annuity": 600}
    | {"fixed_until": date(2030, 12, 1), "asof": date(2025, 10, 1), "prepayment_penalty": 0.01}
    | {"finances": "wohnung"},
    # the employer pays 100 and the salary conversion of 200 its subsidy: of a PKV member above
    # the KV-BBG only what it saves of the RV and the ALV, 10.6%; the statement of October
    # rolls forward to the start with November and December
    {"id": "bav", "kind": "bav", "value": 10_000, "paid": 8000, "contribution": 100}
    | {"conversion": 200, "phases": ["work", "part-time"], "asof": date(2025, 10, 31)}
    | {"matures": date(2040, 1, 1), "growth": "equity", "cost": 0.004, "guarantee": 0.8},
    {"id": "rente", "kind": "bav", "value": 2000, "paid": 5000, "contribution": 0, "phases": []}
    | {"matures": date(2030, 1, 1), "growth": "cash", "guarantee": 1.0}
    | {"payout": "annuity", "annuity_per_10k": 50},  # topped up, paid out by 2046
    {"id": "av", "kind": "av_depot", "contribution": 1800, "start": date(2027, 1, 1)}
    | {"cost": 0.002},
    {"id": "gold", "kind": "gold", "value": 30_000, "cost": 0.002}
    | {
        "trades": [_buy("XAU", date(2020, 3, 10), 5, 7500), _buy("XAU", date(2025, 7, 15), 3, 8400)]
    },
    {"id": "btc", "kind": "crypto", "trades": [_buy("BTC", date(2025, 9, 20), 0.25, 14_000)]}
    | {"value": 20_000},
]
HAUS = {"id": "haus", "name": "Haus", "growth": "equity", "upkeep": 0.005, "tags": ["haus"]}
KREDIT = {"id": "hauskredit", "balance": -300_000, "rate": 0.035, "annuity": 1600}
KREDIT |= {"fixed_for": 120, "prepayment_penalty": 0.01}
EVENTS: list[dict[str, Any]] = [
    {"at": date(2026, 3, 1), "type": "sell", "asset": "btc", "share": 0.5},  # young: taxable
    {"at": date(2027, 3, 1), "type": "buy", "asset": "btc", "amount": 20_000},  # §20: the switch
    {"at": date(2028, 6, 1), "type": "sell", "asset": "wohnung", "costs": 0.05, "taxable": True}
    | {"then": [{"repay": "kredit"}, {"invest": "portfolio"}]},
    {"when": {"age": 51.5}, "type": "sell", "asset": "btc", "share": 0.8},  # free, then §20
    {"at": date(2028, 9, 1), "type": "sell", "asset": "gold", "costs": 0.01}  # aged: free
    | {"then": [{"invest": "portfolio"}]},
    {"at": date(2029, 1, 1), "type": "write_off", "asset": "rsu"},
    {"at": date(2029, 1, 1), "type": "severance", "gross": 150_000}
    | {"bav": {"policy": "bav", "amount": 20_000}},
    {"at": date(2035, 1, 1), "type": "lump_sum", "amount": 10_000, "taxable": False},
    {"at": date(2045, 1, 1), "type": "set_stream", "name": "Essen", "amount": -550},
    # a house instead of the rent, from cash and the depot with a loan; taxable when sold at 61,
    # within ten years: the loan runs on, a conditional sale repays nothing
    {"at": date(2031, 7, 1), "type": "buy_property", "price": 400_000, "land": "HH"}
    | {"property": HAUS, "loan": KREDIT, "costs": 0.02, "id": "haus", "note": "Haus statt Miete"},
    {"at": date(2031, 7, 1), "type": "end_streams", "names": ["Miete"], "id": "haus"},
    {"at": date(2031, 7, 1), "type": "add_stream", "id": "haus"}
    | {"stream": {"name": "Hausgeld Haus", "cat": "wohnen", "amount": -350, "tags": ["haus"]}},
    {"at": date(2036, 1, 1), "type": "repay", "loan": "hauskredit", "amount": 50_000},
    {"when": {"age": 61}, "type": "sell", "asset": "haus", "costs": 0.03, "taxable": True},
    # a gift and the estate of the mother at her median month, within ten years of each other;
    # the gift of 2023 before the start counts with the first (§14 ErbStG)
    {"at": date(2030, 6, 1), "type": "gift", "from": "mutter", "cash": 300_000},
    {"type": "inheritance", "from": "mutter", "cash": 240_000}
    | {"equity": {"value": 120_000, "cost_basis": 50_000}},
]
# the givers: `vater` stays unused here, the later death of two is a test of the paths
RELATIVES = {
    "mutter": {"label": "Mutter", "born": date(1950, 5, 1), "sex": "f", "relation": "parent"}
    | {"given": [{"at": date(2023, 1, 1), "value": 150_000, "tax": 0}]},
    "vater": {"born": date(1948, 1, 1), "sex": "m", "relation": "parent"},
}


def rich_plan() -> Plan:
    """Work, ALG1 at 52 after a Sperrzeit (12 weeks without ALG1, its PKV subsidy and points, a
    quarter of the claim gone) with a course of six months at half the days, years without
    income with voluntary contributions, self-employed at 55
    (a trade business with the Regelbeitrag of the GRV, a yearly project fee), part time at 58 in a
    phase of its own (half the salary, scaled by 1.2, the bAV goes on), the pension at 64 with 35
    years, a let flat at a loss against the salary (AfA, Hausgeld, upkeep, the interest of its
    loan), its taxable sale within ten years that repays the loan before its fixed rate ends (the
    basis less the AfA, the penalty a cost), a bAV by salary conversion, a severance with a bAV
    part, a share plan forfeited, a real-estate fund beside the equity fund (three
    Teilfreistellungen in one pool), a bAV annuity topped up to its guarantee that outlives its
    capital, an Altersvorsorgedepot, a term deposit, an allocation glide path.
    Gold and Bitcoin with lots inside and outside the holding period, a purchase under §20 and a
    conditional sale. A member of a church: 9% church tax, the reduced flat tax. Werbungskosten
    above the Pauschbetrag, by the salary months; gifts half of them donations, household services
    (§35a). A course of 30,000 € in the career break of 2030 (`deduct: work`): its loss beyond the
    capital income of 2030 goes back into the severance year 2029 (§10d Abs. 1, §34 Abs. 1 S. 3
    EStG), refunded in December 2031. Losses of capital income carried to the start (§20 Abs. 6
    EStG), which the capital income of 2026 uses up. The gains of the depot harvested each December
    in the tax-free room. A child in education to 2040: its Kindergeld, its half allowances where
    they save more (§31 EStG), in the base of the Soli and the church tax, its Kinderzulage, ALG1
    at 67%. ALG1 at 52 in the PKV marks the exemption that it assumes; the PKV ends with the part
    time at 58 (`gkv_from`, marked: §6 Abs. 3a SGB V usually blocks it): its premiums and
    subsidies stop, the salary pays the GKV and its conversion the KV and PV saved, the bAV lump
    sum of 2040 a Versorgungsbezug beside it, and the pension without the KVdR (`kvdr: false`) a
    voluntary member at the KV-BBG."""
    a = Assumptions.model_validate(
        {
            "person": {"born": date(1977, 1, 1), "horizon_age": 71, "rv_since": date(1999, 1, 1)}
            | {"relatives": RELATIVES, "children": 1, "kvdr": False}
            | {"children_born": [{"born": date(2015, 3, 1), "until": date(2040, 1, 1)}]},
            "start": date(2026, 1, 1),
            "phases": {
                **PHASES,
                "part-time": {"label": "Teilzeit"},
                "freelance": {"label": "Selbständig"},
            },
            "scale": {"salary": {"part-time": 1.2}},
            "inflation": {"mean": 0.02},
            "indices": {
                "salary": {"mean": 0.03},
                "insurance": {"mean": 0.03},
                "bonus": {"mean": 0.9, "cumulative": False},
            },
            "returns": {
                "equity": {"mean": 0.05},
                "fixed_income": {"mean": 0.03},
                "cash": {"mean": 0.0},
                "property": {"mean": 0.01},
                "gold": {"mean": 0.04},
                "bitcoin": {"mean": 0.1},
            },
            "allocation": {"fixed_income": [{"age": 50, "share": 0.2}, {"age": 70, "share": 0.4}]},
            # against the wealth of the first month without pay: of ALG1 at 52, the severance
            # paid; of the pension at 64, after more than twelve months of pay. Narrow, so that
            # the mean path raises in 2030 and cuts after the house of 2031
            "spending": {"base": "no_pay", "cut": 0.25, "trigger": 0.9}
            | {"increase": 0.1, "ceiling": 1.04, "categories": ["base"]},
            "disability": {},  # the default chances, which a fixed run draws none of
            "tax": {
                "werbungskosten": 2400,
                "church": True,
                "land": "HH",
                "harvest": True,
                "crypto_capital_from": date(2027, 1, 1),
                "capital_losses": 2_500,
                "gkv_from": date(2035, 1, 1),
                "self_employed": {"rv": "regular", "founded": date(2030, 1, 1)},
            },
        }
    )
    scenario = Scenario.model_validate(
        {
            "name": "rich",
            "phases": phases(
                (date(2026, 1, 1), "work"),
                (date(2029, 1, 1), "unemployed"),
                (date(2030, 4, 1), "alt"),
                (date(2032, 1, 1), "freelance"),
                (date(2035, 1, 1), "part-time"),
                (date(2041, 1, 1), "retired"),
            ),
            "events": EVENTS,
        }
    )
    return Plan.model_validate(
        {"assumptions": a, "assets": ASSETS, "streams": STREAMS, "scenario": scenario}
    )


@pytest.fixture(scope="module")
def rich() -> RunResult:
    p = rich_plan()
    return simulate(p, _returns(p), "fixed")


def _returns(p: Plan) -> Returns:
    return FixedProvider(p.assumptions).sample(horizon_months(p.assumptions))


@pytest.fixture(scope="module")
def level() -> FloatArray:
    return _levels(rich_plan())


@pytest.fixture
def snapshot_json(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    return snapshot.use_extension(JSONSnapshotExtension)


def by_year(r: RunResult) -> dict[str, dict[str, object]]:
    """Totals, the year-end balance and the ledger groups per year, in whole euros."""
    assert r.ledger is not None
    years = np.array([m.year for m in r.months])
    groups: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for (side, group, _), row in r.ledger.entries.items():
        for year in np.unique(years):
            groups[int(year)][f"{side}: {group}"] += float(row[years == year].sum())
    out: dict[str, dict[str, object]] = {}
    for year in np.unique(years).tolist():
        sel = years == year
        last = int(np.flatnonzero(sel)[-1])
        out[str(year)] = {
            "phases": sorted(set(np.array(r.phases)[sel].tolist())),
            **{
                name: round(float(getattr(r, name)[0, sel].sum()))
                for name in ("income", "expenses", "taxes", "capital_taxes")
            },
            "liquid": round(float(r.liquid[0, last])),
            "total": round(float(r.total[0, last])),
            "ledger": {k: round(v) for k, v in sorted(groups[year].items()) if round(v)},
        }
    return out


def test_rich_plan_by_year(rich: RunResult, snapshot_json: SnapshotAssertion) -> None:
    assert snapshot_json == {
        "years": by_year(rich),
        "markers": marked(rich),
    }


def _renamed(p: Plan, to: Callable[[str], str]) -> Plan:
    """`p` with every phase renamed and labeled as the pages named it before."""
    data = p.model_dump(by_alias=True)
    a, scenario = data["assumptions"], data["scenario"]
    a["phases"] = {to(n): {"label": label} for n, label in p.assumptions.phase_labels.items()}
    a["scale"]["salary"] = {to(n): f for n, f in a["scale"]["salary"].items()}
    added = [e["stream"] for e in scenario["events"] if e["type"] == "add_stream"]
    for s in [*data["streams"], *added]:
        s["phases"] = s["phases"] and [to(n) for n in s["phases"]]
        s["factor"] = {to(n): f for n, f in s["factor"].items()}
    for x in data["assets"]:
        if x["kind"] == "bav":
            x["phases"] = [to(n) for n in x["phases"]]
    for change in scenario["phases"]:
        change["phase"] = to(change["phase"])
    return Plan.model_validate(data)


def test_the_run_reads_no_phase_name(rich: RunResult) -> None:
    """Every phase renamed, labeled as before: the same run, the markers too, but for the names
    of the phases."""
    p = _renamed(rich_plan(), lambda name: f"x-{name}")
    other = simulate(p, _returns(p), "fixed")
    assert other.phases == [f"x-{name}" for name in rich.phases]
    assert other.markers == rich.markers
    years, renamed = (
        {
            year: {k: v for k, v in values.items() if k != "phases"}
            for year, values in by_year(r).items()
        }
        for r in (rich, other)
    )
    assert renamed == years


def _levels(p: Plan) -> FloatArray:
    """The price level of each month of the mean path of `p`: the ledger holds start-year euros
    at it."""
    return levels(_returns(p), p.assumptions.start.month)[1]


def _adds_up(r: RunResult, level: FloatArray) -> None:
    """Per year: the settlement is spread over its year, so months do not add up alone. The
    ledger is in start-year euros, the totals are nominal."""
    assert r.ledger is not None
    entries = r.ledger.entries
    years = np.array([m.year for m in r.months])

    def total(*keys: tuple[str, str | None], capital: bool = False) -> np.ndarray:
        """The rows of the sides, each of one group or of every group (None)."""
        rows = [
            row * level
            for (side, group, item), row in entries.items()
            if any(side == s and g in (None, group) for s, g in keys)
            and (item == CAPITAL_TAX) == capital
        ]
        return sum(rows, np.zeros(len(r.months)))

    for year in np.unique(years):
        sel = years == year
        income = total((SOURCE, None), (ONEOFF_IN, None))
        expenses = total((SPENDING, None), (ONEOFF_OUT, PURCHASE_COSTS))
        taxes = total((TAX, None), (ONEOFF_OUT, ONEOFF_TAX))
        assert income[sel].sum() == pytest.approx(r.income[0, sel].sum())
        assert expenses[sel].sum() == pytest.approx(-r.expenses[0, sel].sum())
        assert taxes[sel].sum() == pytest.approx(-r.taxes[0, sel].sum())
        assert total((TAX, None), capital=True)[sel].sum() == pytest.approx(
            -r.capital_taxes[0, sel].sum(),
            abs=1e-6,  # a year without: the noise of the rounds
        )


def test_ledger_adds_up_to_the_engine_totals(rich: RunResult, level: FloatArray) -> None:
    _adds_up(rich, level)


def gkv_plan(disabled: date | None = None) -> Plan:
    """The GKV beside the PKV of `rich_plan`, at a Zusatzbeitrag of its own: a salary, a trade
    business with Krankengeld, the GRV on the profit and a yearly fee, then years without either
    from a depot and a rent (a voluntary member: the minimum, the capital income of the year
    before, the rent net of its costs), a company pension paid at once (a Versorgungsbezug for 120
    months), a pension deferred to 67 with the KVdR, a company annuity and a Basisrente beside it,
    with a premium of its own while the salary pays, its annuity taxed at the share of 2044.
    The flat is let at a loss while its loan runs, to 2033: in the years without a salary the loss
    shelters the capital income of the depot (Günstigerprüfung, §32d Abs. 6 EStG). A Verlustvortrag
    of 20,000 € from before the start offsets the first year. The harvest of each December, capped
    in the voluntary years by the minimum base of the next. VPW spends `Leben` from the first year
    without pay: at its floor of 1,000 € until the pension (the lump sum of 2035 stays out of its
    month, the year after stays at its floor; the refund of the withholding goes to the wealth),
    above its plan from then. A BU policy pays its premium; with `disabled` the person can no longer
    work from that month (rule `disability`)."""
    a = Assumptions.model_validate(
        {
            "person": Person(
                born=date(1977, 1, 1), horizon_age=70, rv_since=date(1999, 1, 1)
            ).model_dump()
            | {
                "relatives": {
                    "tante": {"born": date(1955, 3, 1), "sex": "f", "relation": "aunt_uncle"}
                }
            },
            "start": date(2026, 1, 1),
            "phases": PHASES | {"gap": {"label": "Privatier"}},
            "inflation": {"mean": 0.02},
            "returns": {"equity": {"mean": 0.05}, "fixed_income": {"mean": 0.03}}
            | {"cash": {"mean": 0.0}, "property": {"mean": 0.01}},
            "tax": {"pkv": False, "kv_zusatz": 0.025, "loss_carryforward": 20_000}
            | {"harvest": True, "self_employed": {"rv": "income", "krankengeld": True}},
            "spending": {"base": "no_pay", "categories": ["base"]}
            | {"vpw": {"growth": 0.03, "floor": 1000}},
            "disability": {"at": disabled} if disabled else {},
        }
    )
    streams: list[dict[str, Any]] = [
        {"name": "Gehalt", "kind": "salary", "gross": 6000, "phases": ["work"]},
        {"name": "Laden", "kind": "self_employed", "amount": 6500, "hebesatz": 4.5}
        | {"phases": ["alt"]},
        {"name": "Projekt", "kind": "self_employed", "amount": 20_000, "every": 12}
        | {"start": date(2027, 6, 1), "phases": ["alt"]},
        {"name": "Miete ein", "kind": "other_income", "amount": 600, "property": "wohnung"},
        {
            "name": "Rente",
            "kind": "pension",
            "points": 30,
            "point_value": 40,
            "phases": ["retired"],
        },
        {"name": "Miete", "cat": "wohnen", "amount": -1200},
        {"name": "Leben", "cat": "base", "amount": -2500},
        {"name": "BU", "kind": "bu", "cat": "versicherung", "amount": 1500, "premium": -60},
    ]
    scenario = Scenario.model_validate(
        {
            "name": "gkv",
            "phases": phases(
                (date(2026, 1, 1), "work"),
                (date(2026, 7, 1), "alt"),
                (date(2029, 1, 1), "gap"),
                (date(2042, 1, 1), "retired"),
            ),
            "events": [
                {"at": date(2033, 1, 1), "type": "repay", "loan": "kredit"},
                # in the KVdR: the gift pays the class II tax, the KV stays what the pension pays
                {"at": date(2043, 1, 1), "type": "gift", "from": "tante", "cash": 100_000},
            ],
        }
    )
    policy = {"kind": "bav", "contribution": 0, "phases": [], "growth": "equity"}
    assets: list[dict[str, Any]] = [
        {"id": "giro", "kind": "cash", "value": 20_000},
        {"id": "depot", "kind": "equity", "value": 600_000, "cost_basis": 400_000},
        # let at a loss while its loan runs, repaid in 2033
        {"id": "wohnung", "kind": "property", "sqm": 50, "per_sqm": 4000, "upkeep": 0.01}
        | {"bought_for": 210_000, "bought": date(2020, 1, 1), "building_share": 0.75, "afa": 0.02},
        {"id": "kredit", "kind": "loan", "balance": -100_000, "rate": 0.035, "annuity": 650}
        | {"asof": date(2025, 12, 1), "finances": "wohnung"},
        {"id": "bav", "value": 30_000, "paid": 30_000, "matures": date(2035, 1, 1)} | policy,
        {"id": "pk", "value": 40_000, "matures": date(2044, 1, 1), "payout": "annuity"}
        | policy
        | {"annuity_per_10k": 45},
        {"id": "ruerup", "value": 20_000, "matures": date(2044, 1, 1), "payout": "annuity"}
        | policy
        | {"annuity_per_10k": 40, "basisrente": True, "premium": 300, "phases": ["work"]},
    ]
    return Plan.model_validate(
        {"assumptions": a, "assets": assets, "streams": streams, "scenario": scenario}
    )


@pytest.fixture(scope="module")
def gkv() -> RunResult:
    p = gkv_plan()
    return simulate(p, _returns(p), "fixed")


def test_gkv_plan_by_year(gkv: RunResult, snapshot_json: SnapshotAssertion) -> None:
    assert snapshot_json == {
        "years": by_year(gkv),
        "markers": marked(gkv),
    }


def test_the_ledger_of_a_gkv_member_adds_up_too(gkv: RunResult) -> None:
    assert gkv.ledger is not None
    assert {"KV", "PV", "RV", "trade tax"} <= {item for _, _, item in gkv.ledger.entries}
    _adds_up(gkv, _levels(gkv_plan()))


# the business with Krankengeld runs: its Krankengeld, the KV of a voluntary member on the BU
# benefit in those months, the EM-Rente from 2028-10 in the KVdR, years before the pension
DISABLED = date(2028, 3, 1)


@pytest.fixture(scope="module")
def gkv_disabled() -> RunResult:
    p = gkv_plan(DISABLED)
    return simulate(p, _returns(p), "fixed")


def test_gkv_disabled_by_year(gkv_disabled: RunResult, snapshot_json: SnapshotAssertion) -> None:
    """`gkv_plan`, unable to work from `DISABLED` (rule `disability`)."""
    assert snapshot_json == {
        "years": by_year(gkv_disabled),
        "markers": marked(gkv_disabled),
    }


def test_the_ledger_of_a_disabled_gkv_member_adds_up_too(gkv_disabled: RunResult) -> None:
    assert gkv_disabled.ledger is not None
    items = {item for _, _, item in gkv_disabled.ledger.entries}
    assert {KRANKENGELD, EM_RENTE, f"BU: {BENEFIT}"} <= items
    _adds_up(gkv_disabled, _levels(gkv_plan(DISABLED)))


def _opening(x: Asset, p: Plan) -> float:
    """What an asset is worth in the first month: a term deposit with its interest, a loan by its
    schedule, a pension policy and an Altersvorsorgedepot carried from an earlier `asof`."""
    a = p.assumptions
    before = add_months(a.start, -1)
    match x:
        case TermDeposit():
            return x.value_at(a.start)
        case Loan():
            return x.opening(a.start, a.refinance_rate)
        case PensionPolicy():
            return carry.policy(p, x, before)[0]
        case AvDepot():
            return carry.depot(p, x, before)
        case _:
            return x.value


def test_wealth_built_is_the_change_of_the_net_worth(rich: RunResult, level: FloatArray) -> None:
    """Per year, as the settlement is spread over its year: with the one-offs, `wealth built`
    is the change of the net worth before the latent tax, and without them too in a year
    without one-offs. Nominal: the ledger holds start-year euros at the level of the year."""
    p = rich_plan()
    book = budget.ledger(rich)
    worth = rich.total[0] - rich.nominal_balance["latent_tax"]
    opening = sum(_opening(x, p) for x in p.assets)
    before = np.concatenate([[opening], worth[:-1]])
    oneoff = [  # a savings plan and a salary conversion are no one-offs
        row
        for (side, group, _), row in book.entries.items()
        if (
            side in (ONEOFF_IN, ONEOFF_OUT, MOVE_IN, MOVE_OUT, MOVED)
            and group not in (SAVINGS_PLAN, CONVERSION)
        )
        or group == ONEOFF_CONTRIBUTION
    ]
    years = np.array([m.year for m in rich.months])
    drawn_quietly = False
    for year in np.unique(years):
        sel = np.flatnonzero(years == year).tolist()
        change = (worth[sel[-1]] - before[sel[0]]) / level[sel[0]] / len(sel)
        built = budget.from_ledger(book, sel, oneoffs=True)
        assert built.wealth_built == pytest.approx(change, abs=1e-6)
        if not any(row[sel].any() for row in oneoff):
            regular = budget.from_ledger(book, sel)
            assert regular.wealth_built == pytest.approx(change, abs=1e-6)
            drawn_quietly |= bool(regular.assets)  # the policies that pay a source
    assert drawn_quietly
