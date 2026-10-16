"""Loading the inputs: `extends` chains and drops, the overrides, and errors that name the file,
the line and the key path."""

import pickle
from datetime import date
from pathlib import Path

import pytest
from builders import phases

from dagobert.loader import (
    NO_PATH,
    NOT_KEPT,
    adjust,
    check,
    deep_merge,
    load_app_settings,
    load_plan,
    load_scenario,
    nested,
    problems,
    written,
)
from dagobert.model.assets import EquityAsset, GoldAsset
from dagobert.model.events import BuyPropertyEvent, SellEvent
from dagobert.model.plan import Scenario
from dagobert.problems import NOT_UTF8, InputError

ASSUMPTIONS = """
person: {born: 1977-01-01}
start: 2026-10-01
phases: {work: {}, unemployed: {}, alt: {}, retired: {}}
returns:
  equity: {mean: 0.05}
  fixed_income: {mean: 0.03}
  cash: {mean: 0.02}
  property: {mean: 0.01}
"""
ASSETS = """
assets:
  - {id: cash, kind: cash, value: 1000}
"""
CASHFLOWS = """
streams:
  - {name: Miete, cat: wohnen, amount: -500}
  - {name: Gehalt, kind: salary, gross: 5000, phases: [work]}
"""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    (tmp_path / "assumptions.yaml").write_text(ASSUMPTIONS)
    (tmp_path / "assets.yaml").write_text(ASSETS)
    (tmp_path / "cashflows.yaml").write_text(CASHFLOWS)
    scen = tmp_path / "scenarios"
    scen.mkdir()
    (scen / "base.yaml").write_text(
        "name: base\nphases: [{from: 2026-10-01, phase: work}]\nnote: Work on\n"
    )
    (scen / "child.yaml").write_text(
        "name: child\nextends: base\n"
        "phases: [{from: 2028-07-01, phase: unemployed}]\n"
        "events: [{at: 2027-03-01, type: severance, gross: 100000}]\n"
        "overrides: {inflation: {mean: 0.04}}\n"
    )
    return tmp_path


def test_a_child_extends_its_parent_and_overrides_the_assumptions(data_dir: Path) -> None:
    child = load_scenario(data_dir / "scenarios" / "child.yaml")
    assert [p.phase for p in child.phases] == ["work", "unemployed"]
    assert len(child.events) == 1
    assert child.extends is None
    assert child.note == ""  # the note of the parent says what the parent stands for
    plan = load_plan(data_dir, data_dir / "scenarios" / "child.yaml")
    assert (plan.assumptions.inflation.mean, plan.assumptions.inflation.stdev) == (0.04, 0.01)
    assert len(plan.streams) == 2


def test_explicit_override_wins_and_merges_with_scenario_overrides(data_dir: Path) -> None:
    """The scenario's own `overrides: {inflation: {mean: 0.04}}` yields to the explicit
    override on `mean`, while the explicit override's other keys still apply."""
    plan = load_plan(
        data_dir,
        data_dir / "scenarios" / "child.yaml",
        overrides={"inflation": {"mean": 0.09, "stdev": 0.02}, "tax": {"sparer_pauschbetrag": 500}},
    )
    assert plan.assumptions.inflation.mean == pytest.approx(0.09)
    assert plan.assumptions.inflation.stdev == pytest.approx(0.02)
    assert plan.assumptions.tax.sparer_pauschbetrag == pytest.approx(500.0)


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"a": "b", "b": "a"}, "scenarios/b.yaml:2: extends: a cycle through a.yaml"),
        ({"a": "a"}, "scenarios/a.yaml:2: extends: a cycle through a.yaml"),
        ({"a": "gone"}, "scenarios/a.yaml:2: extends: no gone.yaml"),
        ({"a": "sub/plan"}, f"scenarios/a.yaml:2: extends: {NO_PATH}"),
        ({"a": "..\\base"}, f"scenarios/a.yaml:2: extends: {NO_PATH}"),
    ],
)
def test_extends_names_a_cycle_or_a_missing_parent(
    data_dir: Path, files: dict[str, str], expected: str
) -> None:
    for name, parent in files.items():
        (data_dir / "scenarios" / f"{name}.yaml").write_text(f"name: {name}\nextends: {parent}\n")
    with pytest.raises(InputError) as caught:
        load_scenario(data_dir / "scenarios" / "a.yaml")
    assert str(caught.value) == expected


def test_extends_three_levels(data_dir: Path) -> None:
    scen = data_dir / "scenarios"
    (scen / "gp.yaml").write_text(
        "name: gp\n"
        "phases: [{from: 2026-01-01, phase: work}]\n"
        "overrides: {inflation: {mean: 0.01, stdev: 0.02}, tax: {sparer_pauschbetrag: 500}}\n"
    )
    (scen / "mid.yaml").write_text(
        "name: mid\nextends: gp\n"
        "phases: [{from: 2029-01-01, phase: alt}]\n"
        "overrides: {inflation: {mean: 0.02}}\n"
    )
    (scen / "leaf.yaml").write_text(
        "name: leaf\nextends: mid\n"
        "phases: [{from: 2027-01-01, phase: unemployed}]\n"
        "overrides: {inflation: {mean: 0.03}}\n"
    )
    leaf = load_scenario(scen / "leaf.yaml")
    assert [p.phase for p in leaf.phases] == ["work", "unemployed", "alt"]
    assert leaf.overrides["inflation"] == {"mean": 0.03, "stdev": 0.02}
    assert leaf.overrides["tax"] == {"sparer_pauschbetrag": 500}


DROPPED_FROM = """\
name: base
phases:
  - {from: 2026-10-01, phase: work}
  - {from: 2030-01-01, phase: retired, id: exit}
events:
  - {at: 2029-01-01, id: gift, type: lump_sum, amount: 1000}
  - {at: 2030-01-01, id: exit, type: lump_sum, amount: 5000}
"""


def _scenarios(data_dir: Path, **texts: str) -> Path:
    scen = data_dir / "scenarios"
    for name, text in texts.items():
        (scen / f"{name}.yaml").write_text(text)
    return scen


def test_a_child_drops_the_phases_and_events_of_an_id(data_dir: Path) -> None:
    scen = _scenarios(
        data_dir,
        base=DROPPED_FROM,
        kept="name: kept\nextends: base\n",
        dropped="name: dropped\nextends: base\ndrop: [exit]\n",
    )
    kept, dropped = (load_plan(data_dir, scen / f"{n}.yaml").scenario for n in ("kept", "dropped"))
    assert [p for p in kept.phases if p.id != "exit"] == dropped.phases != kept.phases
    assert [e for e in kept.events if e.id != "exit"] == dropped.events != kept.events
    events = [e for _, own in written(data_dir, scen / "dropped.yaml") for e in own.events]
    assert events == dropped.events
    assert load_scenario(scen / "base.yaml").events == kept.events


def test_an_override_follows_the_items_that_a_child_drops(data_dir: Path) -> None:
    """The middle file moves `exit`. A child that only adds an `exit` moves it with the group,
    one that drops the group first keeps the date of its own."""
    own_exit = "events: [{at: 2031-01-01, id: exit, type: lump_sum, amount: 1}]\n"
    scen = _scenarios(
        data_dir,
        base=DROPPED_FROM,
        mid="name: mid\nextends: base\noverrides: {shift: {exit: 2}}\n",
        added="name: added\nextends: mid\n" + own_exit,
        replaced="name: replaced\nextends: mid\ndrop: [exit]\n" + own_exit,
    )
    exits = {
        name: [e.at for e in load_plan(data_dir, scen / f"{name}.yaml").scenario.events if e.id]
        for name in ("added", "replaced")
    }
    assert exits == {
        "added": [date(2029, 1, 1), date(2030, 3, 1), date(2031, 3, 1)],
        "replaced": [date(2029, 1, 1), date(2031, 1, 1)],
    }


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        ({"base": DROPPED_FROM + "drop: [gift]\n"}, f"scenarios/base.yaml:8: drop[0]: {NOT_KEPT}"),
        (
            {"child": "name: child\nextends: base\ndrop: [exit, typo]\n"},
            f"scenarios/child.yaml:3: drop[1]: {NOT_KEPT}",
        ),
        (  # the parent dropped it already
            {
                "mid": "name: mid\nextends: base\ndrop: [exit]\n",
                "child": "name: child\nextends: mid\ndrop: [exit]\n",
            },
            f"scenarios/child.yaml:3: drop[0]: {NOT_KEPT}",
        ),
        (  # an override of the dropping file or below needs an item that is left
            {"child": "name: child\nextends: base\ndrop: [exit]\noverrides: {shift: {exit: 1}}\n"},
            "scenarios/child.yaml:4: overrides.shift.exit: no event or phase with this id",
        ),
        (  # one of a parent goes with the dropped item, the rest stays
            {
                "base": DROPPED_FROM + "overrides: {shift: {gift: 5, typo: 1}}\n",
                "child": "name: child\nextends: base\ndrop: [gift]\n",
            },
            "scenarios/base.yaml:8: overrides.shift.typo: no event or phase with this id",
        ),
    ],
)
def test_a_drop_takes_an_item_that_the_parents_keep(
    data_dir: Path, texts: dict[str, str], expected: str
) -> None:
    scen = _scenarios(data_dir, **({"base": DROPPED_FROM} | texts))
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, scen / "child.yaml")
    assert str(caught.value) == expected


def test_a_check_after_a_dropped_event_names_its_line(data_dir: Path) -> None:
    """The events that the files keep follow each other in the scenario, each at its index in
    the file that writes it."""
    scen = _scenarios(
        data_dir,
        base=DROPPED_FROM + "  - {at: 2027-01-01, type: set_stream, name: Mite, amount: -1}\n",
        child="name: child\nextends: base\ndrop: [gift]\n"
        "events: [{at: 2028-01-01, type: set_stream, name: Gehal, gross: 1}]\n",
    )
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, scen / "child.yaml")
    assert [line.split(", which")[0] for line in str(caught.value).splitlines()] == [
        "scenarios/base.yaml:8: events[2].name: set_stream of 2027-01 names the stream Mite",
        "scenarios/child.yaml:4: events[0].name: set_stream of 2028-01 names the stream Gehal",
    ]


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            "{at: 2027-01-01, type: set_stream, name: Miete, amount: 500}",
            "scenarios/x.yaml:4: events[0].amount: set_stream of 2027-01 sets amount of the stream "
            "Miete: expense needs a non-positive amount",
        ),
        (
            "{at: 2026-06-01, type: lump_sum, amount: 1000}",
            "scenarios/x.yaml:4: events[0].at: lump_sum of 2026-06 lies before the start 2026-10",
        ),
        (
            "{at: 2027-01-01, type: add_stream, stream: {name: Side, amount: -1, end: 2027-06-01}}"
            "\n  - {at: 2028-01-01, type: set_stream, name: Side, amount: -2}",
            "scenarios/x.yaml:5: events[1].at: set_stream of 2028-01 changes no row of Side: every "
            "row ended before it",
        ),
    ],
)
def test_an_event_that_the_run_cannot_take_names_its_line(
    data_dir: Path, event: str, expected: str
) -> None:
    """The model refuses what the run would end in a traceback for."""
    scen = _scenarios(
        data_dir, x=f"name: x\nphases: [{{from: 2026-10-01, phase: work}}]\nevents:\n  - {event}\n"
    )
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, scen / "x.yaml")
    assert str(caught.value).startswith(expected)


def test_an_event_that_a_drop_breaks_names_the_scenario(data_dir: Path) -> None:
    """The parent loads alone: its `set_stream` fails only where a child drops the stream."""
    scen = _scenarios(
        data_dir,
        base="name: base\nphases: [{from: 2026-10-01, phase: work}]\nevents:\n"
        "  - {at: 2027-01-01, id: side, type: add_stream, stream: {name: Side, amount: -1}}\n"
        "  - {at: 2028-01-01, type: set_stream, name: Side, amount: -2}\n",
        child="name: child\nextends: base\ndrop: [side]\n",
    )
    load_plan(data_dir, scen / "base.yaml")
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, scen / "child.yaml")
    message = str(caught.value)
    assert message.startswith("scenarios/base.yaml:5: events[1].name: set_stream of 2028-01")
    assert message.endswith("(for scenarios/child.yaml, whose chain drops side)")


def test_abstract_parent_yields_a_concrete_child(data_dir: Path) -> None:
    scen = data_dir / "scenarios"
    (scen / "tpl.yaml").write_text(
        "name: tpl\nabstract: true\nphases: [{from: 2026-10-01, phase: work}]\n"
    )
    (scen / "leaf.yaml").write_text("name: leaf\nextends: tpl\n")
    assert load_scenario(scen / "tpl.yaml").abstract
    leaf = load_scenario(scen / "leaf.yaml")
    assert not leaf.abstract
    assert [p.phase for p in leaf.phases] == ["work"]


def test_scenario_sorts_unordered_phases() -> None:
    scenario = Scenario(
        name="x", phases=phases((date(2030, 1, 1), "retired"), (date(2026, 1, 1), "work"))
    )
    assert [p.phase for p in scenario.phases] == ["work", "retired"]


def test_deep_merge_preserves_siblings_and_replaces_lists() -> None:
    base = {
        "returns": {"equity": {"mean": 0.05, "stdev": 0.15}, "cash": {"mean": 0.02}},
        "tags": ["a", "b"],
    }
    override = {"returns": {"equity": {"mean": 0.07}}, "tags": ["c"]}
    merged = deep_merge(base, override)
    assert merged["returns"]["equity"] == {"mean": 0.07, "stdev": 0.15}
    assert merged["returns"]["cash"] == {"mean": 0.02}
    assert merged["tags"] == ["c"]


def test_nested_overrides() -> None:
    assert nested({("returns", "equity", "mean"): 0.05, ("pension_growth",): 0.01}) == {
        "returns": {"equity": {"mean": 0.05}},
        "pension_growth": 0.01,
    }


def test_non_mapping_top_level(data_dir: Path) -> None:
    (data_dir / "scenarios" / "list.yaml").write_text("- 1\n- 2\n")
    with pytest.raises(ValueError, match="mapping"):
        load_scenario(data_dir / "scenarios" / "list.yaml")


@pytest.mark.parametrize(
    ("file", "data", "expected"),
    [
        (
            "cashflows.yaml",
            CASHFLOWS.replace("Miete", "Gebühr").encode("cp1252"),
            f"cashflows.yaml:3: {NOT_UTF8}",
        ),
        (
            "scenarios/child.yaml",
            b"name: child\nextends: base\nnote: \x07\n",
            "scenarios/child.yaml:3: unacceptable character #x0007: special characters are not "
            "allowed",
        ),
        ("assumptions.yaml", ASSUMPTIONS.encode() + b"\xff\n", f"assumptions.yaml:10: {NOT_UTF8}"),
    ],
)
def test_a_file_that_does_not_read_names_its_line(
    data_dir: Path, file: str, data: bytes, expected: str
) -> None:
    """A text saved as Windows-1252, a control character: the check of a save names them, also
    for the scenarios that the file breaks."""
    (data_dir / file).write_bytes(data)
    assert {str(p) for p in problems(data_dir)} == {expected}


def test_a_file_with_lone_cr_line_ends_names_its_line(data_dir: Path) -> None:
    text = ASSUMPTIONS.replace("start:", "bogus_key: 1\nstart:", 1).replace("\n", "\r")
    (data_dir / "assumptions.yaml").write_bytes(text.encode())
    assert {str(p) for p in problems(data_dir)} == {"assumptions.yaml:3: bogus_key: unknown key"}


DEPOT = """\
  - id: depot
    kind: equity
    value: 100
    trades:
      - {date: 2026-01-05, kind: buy, security: IE00B4L5Y983, units: 1, amount: 100}
"""


@pytest.mark.parametrize(
    ("file", "old", "new", "expected"),
    [
        (
            "assumptions.yaml",
            "start:",
            "bogus_key: 1\nstart:",
            "assumptions.yaml:3: bogus_key: unknown key",
        ),
        (
            "assets.yaml",
            "value: 1000}\n",
            "value: 1000}\n" + DEPOT.replace("amount: 100}", "amount: 100, unit: 1}"),
            "assets.yaml:8: assets[1].trades[0].unit: unknown key",
        ),
        (  # a check of the asset model: its kind names a union member, not a key
            "assets.yaml",
            "value: 1000}\n",
            "value: 1000}\n" + DEPOT.replace("value: 100", "value: 100\n    cost_basis: 90"),
            "assets.yaml:4: assets[1]: depot: needs trades or a cost_basis, not both",
        ),
        (
            "assets.yaml",
            "kind: cash, value: 1000",
            "kind: cash",
            "assets.yaml:3: assets[0].value: Field required",
        ),
        (
            "cashflows.yaml",
            "gross: 5000",
            "gross: 5000, every: 0",
            "cashflows.yaml:4: streams[1].every: Input should be greater than or equal to 1",
        ),
        (
            "scenarios/child.yaml",
            "gross: 100000",
            "gros: 100000",
            "scenarios/child.yaml:4: events[0].gros: unknown key",
        ),
        (
            "scenarios/child.yaml",
            "{mean: 0.04}",
            "{meen: 0.04}",
            "scenarios/child.yaml:5: overrides.inflation.meen: unknown key",
        ),
        (
            "scenarios/base.yaml",
            "phases:",
            "overrides: {care: {cost: 100}}\nphases:",
            "scenarios/base.yaml:2: overrides.care.hazard: Field required",
        ),
        (
            "cashflows.yaml",
            "streams:",
            "streams: [",
            "cashflows.yaml:3: expected the node content, but found '-'",
        ),
        ("assets.yaml", ASSETS, "", "assets.yaml: empty"),
        (  # a check across the inputs names the use
            "cashflows.yaml",
            "amount: -500",
            "amount: -500, index: rent",
            "cashflows.yaml:3: streams[0].index: the index rent is not defined: add it to "
            "assumptions.indices",
        ),
        (
            "assumptions.yaml",
            "returns:",
            "spending: {categories: [wohnen, personnal]}\nreturns:",
            "assumptions.yaml:5: spending.categories[1]: no expense stream has the category "
            "personnal",
        ),
        (
            "scenarios/child.yaml",
            "{inflation: {mean: 0.04}}",
            "{spending: {categories: [x]}}",
            "scenarios/child.yaml:5: overrides.spending.categories[0]: no expense stream has the "
            "category x",
        ),
        (  # a check of a mapping of the assumptions names the override that holds it
            "scenarios/child.yaml",
            "{inflation: {mean: 0.04}}",
            "{indices: {cpi: {mean: 0.02}}}",
            "scenarios/child.yaml:5: overrides.indices: the name cpi is reserved for the consumer "
            "prices",
        ),
        (
            "scenarios/child.yaml",
            "type: severance, gross: 100000}]\noverrides: {",
            "id: sev, type: severance, gross: 100000}]\noverrides: {events: {sev: {gross: x}}, ",
            "scenarios/child.yaml:5: overrides.events.sev.gross: "
            "Input should be a valid number, unable to parse string as a number",
        ),
        (
            "scenarios/child.yaml",
            "{inflation: {mean: 0.04}}",
            "{assets: {cash: {valu: 1}}}",
            "scenarios/child.yaml:5: overrides.assets.cash.valu: unknown key",
        ),
    ],
)
def test_an_input_error_names_file_line_and_key_path(
    data_dir: Path, file: str, old: str, new: str, expected: str
) -> None:
    path = data_dir / file
    path.write_text(path.read_text().replace(old, new, 1))
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, data_dir / "scenarios" / "child.yaml")
    assert expected in str(caught.value).splitlines()
    assert str(pickle.loads(pickle.dumps(caught.value))) == str(caught.value)  # the process pool


BAV = (
    "  - {id: bav, kind: bav, value: 0, contribution: 1, phases: [work], matures: 2040-01-01,\n"
    "     growth: cash}\n"
)
UNKNOWN = "the phase job is not defined: add it under phases in assumptions.yaml"


@pytest.mark.parametrize(
    ("file", "old", "new", "expected"),
    [
        (
            "cashflows.yaml",
            "phases: [work]",
            "phases: [job]",
            "cashflows.yaml:4: streams[1].phases[0]",
        ),
        (
            "cashflows.yaml",
            "-500}",
            "-500, factor: {job: 0.5}}",
            "cashflows.yaml:3: streams[0].factor.job",
        ),
        (
            "assets.yaml",
            "1000}\n",
            "1000}\n" + BAV.replace("[work]", "[job]"),
            "assets.yaml:4: assets[1].phases[0]",
        ),
        (
            "scenarios/base.yaml",
            "phase: work",
            "phase: job",
            "scenarios/base.yaml:2: phases[0].phase",
        ),
        (
            "scenarios/child.yaml",
            "type: severance, gross: 100000",
            "type: add_stream, stream: {name: Neu, amount: -1, phases: [job]}",
            "scenarios/child.yaml:4: events[0].stream.phases[0]",
        ),
        (
            "assumptions.yaml",
            "start:",
            "scale: {salary: {job: 1.1}}\nstart:",
            "assumptions.yaml:3: scale.salary.job",
        ),
        (
            "scenarios/child.yaml",
            "{inflation: {mean: 0.04}}",
            "{scale: {salary: {job: 1.1}}}",
            "scenarios/child.yaml:5: overrides.scale.salary.job",
        ),
    ],
)
def test_an_unknown_phase_names_where_it_is_written(
    data_dir: Path, file: str, old: str, new: str, expected: str
) -> None:
    """In a stream, a factor, a bAV policy, a phase change of a parent, an added stream, the
    salary scale of the assumptions and of an override."""
    path = data_dir / file
    path.write_text(path.read_text().replace(old, new, 1))
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, data_dir / "scenarios" / "child.yaml")
    assert f"{expected}: {UNKNOWN}" in str(caught.value)


def test_a_let_property_names_the_fields_that_it_lacks(data_dir: Path) -> None:
    """A rent names a flat of `assets.yaml` without `afa`, another the flat that the child buys
    without `building_share`: each problem at the asset or the event that lacks the field."""
    flat = "  - {id: flat, kind: property, sqm: 50, per_sqm: 4000, bought_for: 200000,\n"
    flat += "     bought: 2018-03-01, building_share: 0.7}\n"
    (data_dir / "assets.yaml").write_text(ASSETS + flat)
    rents = "  - {name: Miete ein, kind: other_income, amount: 700, property: flat}\n"
    (data_dir / "cashflows.yaml").write_text(CASHFLOWS + rents)
    child = data_dir / "scenarios" / "child.yaml"
    buy = "  - {at: 2027-01-01, type: buy_property, property: {id: home, afa: 0.02}, price: 1,\n"
    buy += "     land: NI}\n  - at: 2027-02-01\n    type: add_stream\n"
    buy += "    stream: {name: Miete home, kind: other_income, amount: 1, property: home}\n"
    child.write_text(
        child.read_text().replace(
            "events: [{at: 2027-03-01, type: severance, gross: 100000}]\n", ""
        )
        + f"events:\n{buy}"
    )
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, child)
    let = (
        "names {0} as its property, so {0} is let: its AfA and the tax of its sale need this field"
    )
    assert [str(p) for p in caught.value.problems] == [
        f"assets.yaml:4: assets[1].afa: the stream Miete ein {let.format('flat')}",
        f"scenarios/child.yaml:6: events[0].property.building_share: the stream Miete home "
        f"{let.format('home')}",
    ]


def test_a_phase_of_a_policy_names_the_override_that_sets_it(data_dir: Path) -> None:
    (data_dir / "assets.yaml").write_text(ASSETS + BAV)
    child = data_dir / "scenarios" / "child.yaml"
    text = child.read_text().replace(
        "{inflation: {mean: 0.04}}", "{assets: {bav: {phases: [job]}}}"
    )
    child.write_text(text)
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, child)
    assert str(caught.value).startswith(
        f"scenarios/child.yaml:5: overrides.assets.bav.phases[0]: {UNKNOWN}"
    )


def test_a_scenario_defines_no_phases_and_starts_in_one(data_dir: Path) -> None:
    """The phases are those of `assumptions.yaml` for every scenario, and a concrete one starts
    in one: no phase stands for the months before its first change."""
    child = data_dir / "scenarios" / "child.yaml"
    defining = child.read_text().replace("{inflation: {mean: 0.04}}", "{phases: {job: {}}}")
    child.write_text(defining)
    with pytest.raises(
        InputError, match=r"^scenarios/child.yaml:5: overrides.phases: a scenario defines no phases"
    ):
        load_plan(data_dir, child)
    base = data_dir / "scenarios" / "base.yaml"
    base.write_text(base.read_text().replace("2026-10-01", "2026-11-01"))
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, base)
    assert str(caught.value).startswith(
        "scenarios/base.yaml:2: phases: the scenario has no phase at its start 2026-10"
    )
    base.write_text(f"{base.read_text()}abstract: true\n")  # a template leaves it to its children
    load_plan(data_dir, base)


def test_an_override_names_the_file_that_writes_it(data_dir: Path) -> None:
    """The child writes the key path, the base and the assumptions hold its start: the line of
    the child. The explorer's sliders merge last."""
    base = data_dir / "scenarios" / "base.yaml"
    base.write_text(base.read_text() + "overrides: {inflation: {mean: 0.03, meen: 0.02}}\n")
    child = data_dir / "scenarios" / "child.yaml"
    child.write_text(child.read_text().replace("{mean: 0.04}", "{meen: 0.04}"))
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, child, {"inflation": {"stdev": 0.01, "sd": 0.01}})
    assert str(caught.value).splitlines() == [
        "explorer sliders: inflation.sd: unknown key",
        "scenarios/child.yaml:5: overrides.inflation.meen: unknown key",
    ]


def _line(path: Path, start: str) -> int:
    """The number of the first line of `path` that starts with `start`."""
    lines = path.read_text().splitlines()
    return next(n for n, line in enumerate(lines, 1) if line.startswith(start))


def test_an_unknown_stream_names_where_the_event_gets_it(data_dir: Path) -> None:
    """The events of the parent come first in the scenario: the child counts its own. A name
    that an `events` override sets belongs to the override."""
    base = data_dir / "scenarios" / "base.yaml"
    base.write_text(
        base.read_text()
        + "events: [{at: 2027-01-01, type: end_streams, names: [Miete, Mite]},\n"
        + "  {at: 2027-02-01, id: g, type: set_stream, name: Miete, amount: -400}]\n"
    )
    child = data_dir / "scenarios" / "child.yaml"
    set_gehal = "gross: 100000}, {at: 2028-01-01, type: set_stream, name: Gehal, gross: 1}]"
    child.write_text(
        child.read_text()
        .replace("gross: 100000}]", set_gehal)
        .replace("overrides: {", "overrides: {events: {g: {name: Mete}}, ")
    )
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, child)
    events, overrides = _line(child, "events"), _line(child, "overrides")
    assert [line.split(", which")[0] for line in str(caught.value).splitlines()] == [
        f"scenarios/base.yaml:{_line(base, 'events')}: events[0].names[1]: "
        "end_streams of 2027-01 names the stream Mite",
        f"scenarios/child.yaml:{events}: events[1].name: set_stream of 2028-01 names the stream "
        "Gehal",
        f"scenarios/child.yaml:{overrides}: overrides.events.g.name: set_stream of 2027-02 names "
        "the stream Mete",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, []),
        ("", []),
        ("scenarios: [child]\n", ["child"]),
        ("scenarios: [child]\nmodel: fixed\n", "app.yaml:2: model: unknown key"),
    ],
)
def test_app_yaml_loads_with_the_inputs(
    data_dir: Path, text: str | None, expected: list[str] | str
) -> None:
    if text is not None:
        (data_dir / "app.yaml").write_text(text)
    if isinstance(expected, str):
        with pytest.raises(InputError, match=expected):
            check(data_dir)
        return
    check(data_dir)
    assert load_app_settings(data_dir).scenarios == expected


def test_a_list_that_a_child_replaces_belongs_to_the_child(data_dir: Path) -> None:
    """`deep_merge` replaces a list whole: the parent's glide path holds the missing age."""
    scen = data_dir / "scenarios"
    glide = "overrides: {{allocation: {{fixed_income: [{point}]}}}}\n"
    (scen / "base.yaml").write_text(
        (scen / "base.yaml").read_text() + glide.format(point="{age: 50, share: 0.2}")
    )
    child = scen / "child.yaml"
    child.write_text(
        child.read_text().replace("overrides: {inflation: {mean: 0.04}}\n", "")
        + glide.format(point="{share: 0.3}")
    )
    with pytest.raises(InputError) as caught:
        load_plan(data_dir, child)
    assert str(caught.value) == (
        "scenarios/child.yaml:5: overrides.allocation.fixed_income[0].age: Field required"
    )


SHIFTED = """\
name: s
phases:
  - {from: 2026-01-01, phase: work}
  - {from: 2027-02-01, phase: alt, id: leave}
  - {from: 2028-03-01, phase: unemployed, id: alg1}
  - {from: 2029-06-01, phase: alt, id: alg1}
events:
  - {at: 2028-01-01, id: severance, type: severance, gross: 100000}
  - {at: 2028-01-01, id: severance, type: lump_sum, amount: 5000, taxable: false}
"""


def test_overrides_move_groups_and_set_amounts(data: Path) -> None:
    path = data / "scenarios" / "s.yaml"
    path.write_text(
        SHIFTED + "overrides: {shift: {leave: 1}, events: {severance: {gross: 90000}}}\n"
    )
    plan = load_plan(data, path, {"shift": {"alg1": -2, "other": 3}, "events": {"x": {"gross": 1}}})
    assert [(p.at, p.phase) for p in plan.scenario.phases] == [
        (date(2026, 1, 1), "work"),
        (date(2027, 3, 1), "alt"),
        (date(2028, 1, 1), "unemployed"),
        (date(2029, 4, 1), "alt"),
    ]
    severance, lump = plan.scenario.events
    assert (severance.at, getattr(severance, "gross", None)) == (date(2028, 1, 1), 90000)
    assert getattr(lump, "amount", None) == 5000  # the field set skips events without it


@pytest.mark.parametrize(
    ("bad", "expected"),
    [
        ("{shift: {typo: 1}}", "overrides.shift.typo: no event or phase with this id"),
        (
            "{events: {severance: {price: 1}}}",
            "overrides.events.severance.price: no event of this id has this field",
        ),
        (
            "{shift: {leave: x}}",
            "overrides.shift.leave: Input should be a valid integer, unable to parse string as an "
            "integer",
        ),
        (  # whole months: a half moved by half to even before
            "{shift: {leave: 2.5}}",
            "overrides.shift.leave: Input should be a valid integer, got a number with a "
            "fractional part",
        ),
        (
            "{events: {severance: 5}}",
            "overrides.events.severance: Input should be a valid dictionary",
        ),
        ("{assets: [giro]}", "overrides.assets: Input should be a valid dictionary"),
        (  # the shift moves the month after its check
            "{events: {severance: {at: 2031-05}}, shift: {severance: 1}}",
            "overrides.events.severance.at: Input should be a valid date or datetime, input is "
            "too short",
        ),
    ],
)
def test_a_file_override_needs_its_item(data: Path, bad: str, expected: str) -> None:
    path = data / "scenarios" / "s.yaml"
    path.write_text(SHIFTED + f"overrides: {bad}\n")
    with pytest.raises(InputError) as caught:
        load_plan(data, path)
    assert str(caught.value) == f"scenarios/s.yaml:10: {expected}"


def test_overrides_set_asset_fields(data: Path) -> None:
    path = data / "scenarios" / "base.yaml"
    plan = load_plan(data, path, {"assets": {"depot": {"value": 7000}, "gone": {"value": 1}}})
    assert [a.value for a in plan.assets if isinstance(a, EquityAsset)] == [7000]
    path.write_text(path.read_text() + "overrides: {assets: {gone: {value: 1}}}\n")
    with pytest.raises(InputError, match=r"overrides\.assets\.gone: no asset with this id"):
        load_plan(data, path)


def test_the_sliders_skip_a_savings_plan_that_the_scenario_lacks(data: Path) -> None:
    """The explorer reaches every chosen scenario, a plan of an `add_stream` only its own."""
    path = data / "scenarios" / "base.yaml"
    added = "events: [{at: 2027-01-01, type: add_stream, stream: {name: ETF, kind: savings, "
    path.write_text(path.read_text() + added + "amount: -100}}]\n")
    sliders = {"scale": {"savings": {"ETF": 2.0, "gone": 3.0}}}
    assert load_plan(data, path, sliders).assumptions.scale.savings == {"ETF": 2.0}
    path.write_text(path.read_text() + "overrides: {scale: {savings: {gone: 3}}}\n")
    with pytest.raises(InputError, match="no stream of kind savings has the name gone"):
        load_plan(data, path)


def test_the_sliders_of_vpw_and_of_the_band_reach_only_their_rule(data: Path) -> None:
    """The floor of a scenario with VPW gives a scenario without it no VPW, the trigger of one
    with the band reaches no scenario with VPW, whose model refuses both."""
    rule = "spending: {base: no_pay, categories: [wohnen], trigger: 0.5, cut: 0.2}\n"
    (data / "assumptions.yaml").write_text((data / "assumptions.yaml").read_text() + rule)
    band = data / "scenarios" / "base.yaml"
    vpw = data / "scenarios" / "vpw.yaml"
    vpw.write_text(band.read_text() + "overrides: {spending: {trigger: 0, vpw: {floor: 500}}}\n")
    sliders = {"spending": {"trigger": 0.6, "vpw": {"floor": 900}}}
    kept = load_plan(data, band, sliders).assumptions.spending
    assert kept is not None
    assert (kept.vpw, kept.trigger) == (None, 0.6)
    moved = load_plan(data, vpw, sliders).assumptions.spending
    assert moved is not None
    assert moved.vpw is not None
    assert (moved.vpw.floor, moved.trigger) == (900, 0)
    plain = data / "scenarios" / "plain.yaml"
    plain.write_text(band.read_text() + "overrides: {spending: null}\n")
    assert (
        load_plan(data, plain, {"spending": {"vpw": {"floor": 900}}}).assumptions.spending is None
    )


GOLD = "  - {id: g, kind: gold, value: 9000}\n"


def _with_gold(data: Path, events: str) -> Path:
    (data / "assets.yaml").write_text((data / "assets.yaml").read_text() + GOLD)
    text = (
        data / "assumptions.yaml"
    ).read_text() + "  gold: {mean: 0.05, equity_correlation: 0.1}\n"
    (data / "assumptions.yaml").write_text(text)
    path = data / "scenarios" / "base.yaml"
    path.write_text(path.read_text() + (f"events: {events}\n" if events else ""))
    return path


@pytest.mark.parametrize(
    "events",
    [
        "",
        "[{at: 2027-01-01, type: buy, asset: g, amount: 100}]",
        "[{at: 2027-01-01, type: sell, asset: g, share: 0.5}]",
    ],
)
def test_gold_its_purchases_and_sales_load(data: Path, events: str) -> None:
    plan = load_plan(data, _with_gold(data, events))
    assert [a.id for a in plan.assets if isinstance(a, GoldAsset)] == ["g"]


def test_an_event_override_skips_the_fields_that_a_sale_lacks() -> None:
    sale = {"type": "sell", "at": date(2027, 1, 1), "id": "exit"}
    scenario = Scenario.model_validate(
        {"name": "s", "events": [sale | {"asset": "flat"}, sale | {"asset": "g"}]}
    )
    changes = {"events": {"exit": {"price": 500_000, "share": 0.5}}}
    flat, gold = adjust(scenario, changes, holdings={"g"}).events
    assert isinstance(flat, SellEvent)
    assert isinstance(gold, SellEvent)
    assert (flat.price, flat.share, gold.price, gold.share) == (500_000, 1, None, 0.5)


def test_the_files_show_a_gold_sale_as_its_run_takes_it(data: Path) -> None:
    """`written` takes the gold and crypto ids of `assets.yaml`: an override of `share` reaches
    the gold sale there too, which a property sale lacks."""
    path = _with_gold(data, "[{at: 2027-01-01, type: sell, asset: g, id: exit}]")
    path.write_text(path.read_text() + "overrides: {events: {exit: {share: 0.5}}}\n")
    events = [e for _, own in written(data, path) for e in own.events]
    assert events == load_plan(data, path).scenario.events != load_scenario(path).events


def test_a_shift_moves_a_purchase_with_its_fixed_rate_and_an_override_sets_its_price() -> None:
    """`fixed_for` counts from the purchase: the Zinsbindung keeps its length. A `price` reaches
    the purchase, not a gold purchase of the same id, which has none."""
    loan = {"id": "l", "balance": -200_000, "rate": 0.03, "annuity": 1000, "fixed_for": 120}
    buy = {"type": "buy_property", "at": date(2028, 4, 1), "id": "home", "land": "NI"}
    buy |= {"property": {"id": "home"}, "price": 300_000, "loan": loan}
    gold = {"type": "buy", "at": date(2028, 4, 1), "id": "home", "asset": "g", "amount": 100}
    scenario = Scenario.model_validate({"name": "s", "events": [buy, gold]})
    changes = {"shift": {"home": 12}, "events": {"home": {"price": 250_000}}}
    moved, _ = adjust(scenario, changes, holdings={"g"}).events
    assert isinstance(moved, BuyPropertyEvent)
    assert moved.loan is not None
    assert (moved.at, moved.price) == (date(2029, 4, 1), 250_000)
    assert moved.loan.taken(date(2029, 4, 1)).fixed_until == date(2039, 4, 1)


def test_a_sale_before_the_purchase_of_a_parent_is_an_error_at_its_own_line(data: Path) -> None:
    scen = data / "scenarios"
    (scen / "buyer.yaml").write_text(
        "name: buyer\nextends: base\nevents:\n"
        "  - {at: 2028-01-01, type: buy_property, price: 200000, land: BY, property: {id: home}}\n"
    )
    (scen / "seller.yaml").write_text(
        "name: seller\nextends: buyer\nevents:\n  - {at: 2027-01-01, type: sell, asset: home}\n"
    )
    with pytest.raises(InputError) as caught:
        load_plan(data, scen / "seller.yaml")
    assert [str(p) for p in caught.value.problems] == [
        "scenarios/seller.yaml:4: events[0].asset: sell of 2027-01 names home in or before the "
        "month of the buy_property that brings it, 2028-01"
    ]
