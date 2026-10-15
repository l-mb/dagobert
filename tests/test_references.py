"""Who refers to what across the inputs: definitions and uses by kind, their reach along the
`extends` chains and the drops, and the orphans of a delete."""

from pathlib import Path

import pytest

from dagobert import references
from dagobert.loader import load_plan
from dagobert.problems import InputError, Keys, dotted
from dagobert.references import Kind, References
from dagobert.scenariofiles import scenario_paths

ASSUMPTIONS = """
person: {born: 1977-01-01}
start: 2026-01-01
phases: {work: {}, unemployed: {}, alt: {}, retired: {}}
returns:
  equity: {mean: 0.05}
  fixed_income: {mean: 0.02}
  cash: {mean: 0.01}
  property: {mean: 0.02}
  bav: {mean: 0.03}
indices: {salary: {mean: 0.02}}
spending: {cut: 0.1, trigger: 1, categories: [Wohnen], age_categories: [auto]}
care: {hazard: [{age: 80, factor: 0.05}], cost: 1000, duration: {mean: 24}, index: salary}
"""
ASSETS = """
assets:
  - {id: giro, kind: cash, value: 100000}
  - {id: flat, kind: property, sqm: 50, per_sqm: 5000, tags: [flat]}
  - {id: loan-a, kind: loan, balance: -100000, rate: 0.02, annuity: 800, finances: flat}
  - {id: policy-a, kind: bav, value: 0, contribution: 0, conversion: 100, salary: Salary,
     phases: [], matures: 2040-01-01}
  - {id: depot, kind: equity, value: 1000, cost_basis: 1000}
  - {id: policy-b, kind: bav, value: 0, phases: [], matures: 2040-01-01, payout: annuity,
     annuity_per_10k: 30, basisrente: true}
"""
CASHFLOWS = """
streams:
  - {name: Salary, cat: pay, kind: salary, gross: 5000, index: salary, phases: [work]}
  - {name: Bonus, cat: pay, kind: salary, of: Salary, share: 0.1, every: 12}
  - {name: Rent, cat: Wohnen, amount: -800, tags: [flat]}
  - {name: Car, cat: auto, amount: -300}
  - {name: VL, kind: other_income, amount: 40, index: null, repays: loan-a}
  - {name: Rent out, kind: other_income, amount: 500, after_sale_of: flat}
  - {name: PKV, cat: health, amount: -500, health: kv}
  - {name: ETF, kind: savings, amount: -500, into: depot}
  - {name: Hausgeld, cat: Wohnen, amount: -100, property: flat}
"""
BASE = """
name: Base
abstract: true
phases:
  - {from: 2026-01-01, phase: work, id: begin}
  - {from: 2032-01-01, phase: retired, id: job-end}
events:
  - {at: 2030-01-01, id: flat-sale, type: sell, asset: flat, then: [{repay: loan-a}]}
  - {at: 2030-01-01, id: flat-sale, type: end_streams, names: [Car], tags: [flat]}
  - {at: 2032-01-01, id: job-end, type: lump_sum, amount: 1000}
"""
EARLY_EXIT = """
name: Early exit
extends: base
events:
  - {at: 2029-01-01, id: exit, type: severance, gross: 50000, bav: {policy: policy-a, amount: 1}}
  - {at: 2029-02-01, type: fund_policy, policy: policy-b, amount: 1000}
  - {at: 2029-03-01, type: write_off, asset: depot}
  - {at: 2027-04-01, type: repay, loan: loan-a, amount: 1000}
  - {at: 2029-05-01, type: set_stream, name: Rent, amount: -900}
  - at: 2029-06-01
    type: add_stream
    stream: {name: Side job, cat: work, kind: other_income, amount: 500, index: salary,
             factor: {alt: 0.5}}
overrides:
  shift: {job-end: 3, exit: 1}
  events: {flat-sale: {price: 300000}, job-end: {amount: 2000}}
  assets: {policy-a: {growth: equity}}
  scale: {categories: {Wohnen: 0.9}, savings: {ETF: 1.5}, salary: {work: 1.1}}
  indices: {salary: {mean: 0.03}, pension: {mean: 0.01}}
"""


@pytest.fixture
def data(tmp_path: Path) -> Path:
    for name, text in {
        "assumptions.yaml": ASSUMPTIONS,
        "assets.yaml": ASSETS,
        "cashflows.yaml": CASHFLOWS,
        "app.yaml": "scenarios: [early-exit]\n",
        "scenarios/base.yaml": BASE,
        "scenarios/early-exit.yaml": EARLY_EXIT,
    }.items():
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def _where(sites: list[references.Site]) -> list[str]:
    return [f"{site.file}: {dotted(site.keys)}" for site in sites]


def test_the_inputs_load(data: Path) -> None:
    for path in scenario_paths(data):
        load_plan(data, path)


USES = {
    (Kind.ASSET, "flat"): [
        "assets.yaml: assets[2].finances",
        "cashflows.yaml: streams[5].after_sale_of",
        "cashflows.yaml: streams[8].property",
        "scenarios/base.yaml: events[0].asset",
    ],
    (Kind.ASSET, "loan-a"): [
        "cashflows.yaml: streams[4].repays",
        "scenarios/base.yaml: events[0].then[0].repay",
        "scenarios/early-exit.yaml: events[3].loan",
    ],
    (Kind.ASSET, "policy-a"): [
        "scenarios/early-exit.yaml: events[0].bav.policy",
        "scenarios/early-exit.yaml: overrides.assets.policy-a",
    ],
    (Kind.ASSET, "policy-b"): ["scenarios/early-exit.yaml: events[1].policy"],
    (Kind.ASSET, "depot"): [
        "cashflows.yaml: streams[7].into",
        "scenarios/early-exit.yaml: events[2].asset",
    ],
    (Kind.STREAM, "Salary"): ["assets.yaml: assets[3].salary", "cashflows.yaml: streams[1].of"],
    (Kind.STREAM, "Car"): ["scenarios/base.yaml: events[1].names[0]"],
    (Kind.STREAM, "Rent"): ["scenarios/early-exit.yaml: events[4].name"],
    (Kind.STREAM, "ETF"): ["scenarios/early-exit.yaml: overrides.scale.savings.ETF"],
    (Kind.TAG, "flat"): [
        "assets.yaml: assets[1].tags[0]",
        "scenarios/base.yaml: events[1].tags[0]",
    ],
    (Kind.CATEGORY, "Wohnen"): [
        "assumptions.yaml: spending.categories[0]",
        "scenarios/early-exit.yaml: overrides.scale.categories.Wohnen",
    ],
    (Kind.CATEGORY, "auto"): ["assumptions.yaml: spending.age_categories[0]"],
    (Kind.INDEX, "salary"): [
        "assumptions.yaml: care.index",
        "cashflows.yaml: streams[0].index",
        "scenarios/early-exit.yaml: events[5].stream.index",
    ],
    (Kind.RETURN_CLASS, "property"): ["assets.yaml: assets[1].growth"],  # the default
    (Kind.RETURN_CLASS, "bav"): ["assets.yaml: assets[3].growth", "assets.yaml: assets[5].growth"],
    (Kind.RETURN_CLASS, "equity"): ["scenarios/early-exit.yaml: overrides.assets.policy-a.growth"],
    (Kind.ITEM, "job-end"): ["scenarios/early-exit.yaml: overrides.shift.job-end"],
    (Kind.EVENT, "flat-sale"): ["scenarios/early-exit.yaml: overrides.events.flat-sale"],
    (Kind.EVENT, "job-end"): ["scenarios/early-exit.yaml: overrides.events.job-end"],
    (Kind.PHASE, "work"): [
        "cashflows.yaml: streams[0].phases[0]",
        "scenarios/base.yaml: phases[0].phase",
        "scenarios/early-exit.yaml: overrides.scale.salary.work",
    ],
    (Kind.PHASE, "alt"): ["scenarios/early-exit.yaml: events[5].stream.factor.alt"],
    (Kind.SCENARIO, "base"): ["scenarios/early-exit.yaml: extends"],
    (Kind.SCENARIO, "early-exit"): ["app.yaml: scenarios[0]"],
    # defined, but used nowhere
    (Kind.ASSET, "giro"): [],
    (Kind.STREAM, "VL"): [],
    (Kind.INDEX, "pension"): [],
    (Kind.ITEM, "begin"): [],
    (Kind.PHASE, "unemployed"): [],
}


@pytest.mark.parametrize(("kind", "name"), USES)
def test_each_use_with_its_file_and_key_path(data: Path, kind: Kind, name: str) -> None:
    assert _where(references.of(data).uses(kind, name)) == USES[kind, name]


def test_the_phases_are_those_of_the_assumptions(data: Path) -> None:
    """In the order of the file, each named as the pages show it; every scenario takes them."""
    path = data / "assumptions.yaml"
    path.write_text(path.read_text().replace("alt: {}", "alt: {label: Career break}"))
    assert references.phases(data) == {
        "work": "work",
        "unemployed": "unemployed",
        "alt": "Career break",
        "retired": "retired",
    }
    refs = references.of(data)
    assert refs.names(Kind.PHASE, "early-exit") == ["alt", "retired", "unemployed", "work"]
    assert _where(
        refs.orphans(Kind.PHASE, "retired", "assumptions.yaml", ("phases", "retired"))
    ) == ["scenarios/base.yaml: phases[1].phase"]


def test_a_use_names_what_holds_it(data: Path) -> None:
    refs = references.of(data)
    assert str(refs.uses(Kind.ASSET, "flat")[-1]) == (
        "scenarios/base.yaml: events[0].asset (sell 2030-01 (id flat-sale))"
    )
    assert [use.label for use in refs.uses(Kind.STREAM, "Salary")] == [
        "bav policy-a",
        "stream Bonus",
    ]


def test_the_options_sort_without_regard_to_case(data: Path) -> None:
    refs = references.of(data)
    # of the expense streams that are no health premium
    assert refs.names(Kind.CATEGORY) == ["auto", "Wohnen"]
    assert refs.names(Kind.ASSET, sorts={"loan", "bav"}) == ["loan-a", "policy-a", "policy-b"]
    assert refs.names(Kind.STREAM, sorts={"salary"}) == ["Bonus", "Salary"]
    assert refs.names(Kind.SCENARIO) == ["base", "early-exit"]


def test_a_scenario_file_adds_names_to_itself_and_its_children(data: Path) -> None:
    refs = references.of(data)
    assert refs.names(Kind.INDEX) == ["cpi", "salary"]
    assert refs.names(Kind.INDEX, "early-exit") == ["cpi", "pension", "salary"]
    assert "Side job" not in refs.names(Kind.STREAM, "base")
    assert "Side job" in refs.names(Kind.STREAM, "early-exit")
    assert refs.names(Kind.ITEM, "base") == ["begin", "flat-sale", "job-end"]
    assert refs.names(Kind.EVENT, "base") == ["flat-sale", "job-end"]
    assert refs.names(Kind.ITEM, "early-exit") == ["begin", "exit", "flat-sale", "job-end"]


BASE_FILE, EARLY = "scenarios/base.yaml", "scenarios/early-exit.yaml"
ORPHANS = [
    (Kind.EVENT, "flat-sale", BASE_FILE, ("events", 0), []),  # the other event keeps the id
    (Kind.EVENT, "flat-sale", BASE_FILE, ("events",), [f"{EARLY}: overrides.events.flat-sale"]),
    # `shift` moves the phase of the id, `events` needs an event
    (Kind.ITEM, "job-end", BASE_FILE, ("events", 2), []),
    (Kind.EVENT, "job-end", BASE_FILE, ("events", 2), [f"{EARLY}: overrides.events.job-end"]),
    (
        Kind.ASSET,
        "depot",
        "assets.yaml",
        ("assets", 4),
        ["cashflows.yaml: streams[7].into", f"{EARLY}: events[2].asset"],
    ),
    (
        Kind.TAG,
        "flat",
        "cashflows.yaml",
        ("streams", 2, "tags"),
        ["assets.yaml: assets[1].tags[0]", f"{BASE_FILE}: events[1].tags[0]"],
    ),
    (  # the overrides of the child define the index too
        Kind.INDEX,
        "salary",
        "assumptions.yaml",
        ("indices",),
        ["assumptions.yaml: care.index", "cashflows.yaml: streams[0].index"],
    ),
    (Kind.SCENARIO, "base", BASE_FILE, (), [f"{EARLY}: extends"]),
    (Kind.ITEM, "exit", EARLY, ("events", 0), [f"{EARLY}: overrides.shift.exit"]),
    (Kind.ITEM, "exit", EARLY, (), []),  # the use goes with the file
]


@pytest.mark.parametrize(("kind", "name", "file", "keys", "users"), ORPHANS)
def test_orphans_are_the_uses_that_nothing_else_reaches(
    data: Path, kind: Kind, name: str, file: str, keys: Keys, users: list[str]
) -> None:
    assert _where(references.of(data).orphans(kind, name, file, keys)) == users


def test_a_drop_uses_an_item_of_the_parents(data: Path) -> None:
    """A file drops what its parents define: its own item of the id does not keep the drop."""
    late = data / "scenarios" / "late.yaml"
    late.write_text(
        "name: Late\nextends: early-exit\ndrop: [exit, job-end]\n"
        "events: [{at: 2033-01-01, id: job-end, type: lump_sum, amount: 1}]\n"
    )
    load_plan(data, late)
    refs = references.of(data)
    assert _where(refs.uses(Kind.ITEM, "exit")) == [
        f"{EARLY}: overrides.shift.exit",
        "scenarios/late.yaml: drop[0]",
    ]
    assert _where(refs.orphans(Kind.ITEM, "job-end", BASE_FILE)) == [
        f"{EARLY}: overrides.shift.job-end",
        "scenarios/late.yaml: drop[1]",
    ]


def test_a_drop_ends_the_reach_of_the_names_of_its_item(data: Path) -> None:
    scen = data / "scenarios"
    (scen / "mid.yaml").write_text(
        "name: Mid\nextends: base\ndrop: [flat-sale]\nevents:\n"
        "  - {at: 2029-06-01, id: side, type: add_stream,\n"
        "     stream: {name: Side, cat: work, amount: -1}}\n"
    )
    (scen / "leaf.yaml").write_text("name: Leaf\nextends: mid\ndrop: [side]\n")
    for name in ("mid", "leaf"):
        load_plan(data, scen / f"{name}.yaml")
    refs = references.of(data)
    assert refs.names(Kind.ITEM, "base") == ["begin", "flat-sale", "job-end"]
    assert refs.names(Kind.ITEM, "mid") == ["begin", "job-end", "side"]
    assert refs.names(Kind.ITEM, "leaf") == ["begin", "job-end"]
    assert ["Side" in refs.names(Kind.STREAM, s) for s in ("mid", "leaf")] == [True, False]
    assert ["work" in refs.names(Kind.CATEGORY, s) for s in ("mid", "leaf")] == [True, False]


def test_an_empty_file_has_no_names(data: Path) -> None:
    (data / "app.yaml").write_text("")
    (data / "scenarios" / "early-exit.yaml").write_text("- a list\n")
    refs = references.of(data)
    assert refs.names(Kind.SCENARIO) == ["base", "early-exit"]
    assert refs.uses(Kind.SCENARIO, "base") == refs.uses(Kind.SCENARIO, "early-exit") == []


def test_a_file_that_does_not_parse_raises(data: Path) -> None:
    (data / "app.yaml").write_text("scenarios: [\n")
    with pytest.raises(InputError, match=r"app\.yaml"):
        references.of(data)


def test_a_file_that_does_not_load_keeps_its_uses(data: Path) -> None:
    before = references.of(data)
    path = data / "scenarios" / "base.yaml"
    path.write_text(BASE.replace("type: sell, ", "") + "  - just text\noverrides: [1]\n")
    with pytest.raises(InputError):
        load_plan(data, path)
    after = references.of(data)
    for kind, name in USES:
        assert _where(after.uses(kind, name)) == _where(before.uses(kind, name))


def test_a_cycle_ends_the_chain() -> None:
    assert References(parents={"a": "b", "b": "a"}).chain("a") == ["b", "a"]
    assert References(parents={"a": "gone"}).chain("a") == ["a"]


def test_a_purchase_defines_its_property_and_loan_in_its_file_and_its_children(
    data: Path,
) -> None:
    scen = data / "scenarios"
    (scen / "buyer.yaml").write_text(
        "name: Buyer\nextends: base\nevents:\n"
        "  - {at: 2028-01-01, id: home, type: buy_property, price: 200000, land: BY,\n"
        "     property: {id: home, tags: [flat]},\n"
        "     loan: {id: home-loan, balance: -100000, rate: 0.03, annuity: 700}}\n"
    )
    (scen / "later.yaml").write_text(
        "name: Later\nextends: buyer\nevents: [{at: 2031-01-01, type: repay, loan: home-loan}]\n"
    )
    for name in ("buyer", "later"):
        load_plan(data, scen / f"{name}.yaml")
    refs = references.of(data)
    homes = [refs.names(Kind.ASSET, s, sorts=("property",)) for s in ("base", "buyer", "later")]
    assert homes == [["flat"], ["flat", "home"], ["flat", "home"]]
    assert refs.names(Kind.ASSET, "later", sorts=("loan",)) == ["home-loan", "loan-a"]
    assert "scenarios/buyer.yaml: events[0].property.tags[0]" in _where(refs.uses(Kind.TAG, "flat"))
    assert _where(refs.uses(Kind.RETURN_CLASS, "property")) == [
        "assets.yaml: assets[1].growth",
        "scenarios/buyer.yaml: events[0].property.growth",
    ]
