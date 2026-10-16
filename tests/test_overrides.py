"""The overrides of a scenario file for the editor: each path with its value and source, the
placeholders, the edits of its own overrides and their rows."""

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from dagobert.loader import flatten, load_plan, load_scenario, nested
from dagobert.model.assumptions import Assumptions
from dagobert.model.plan import split
from dagobert.overrides import (
    ASSUMPTIONS,
    DEFAULT,
    Leaf,
    effective,
    fallback,
    from_rows,
    leaves,
    own,
    rows,
)
from dagobert.problems import InputError
from dagobert.store import NULL

BASE = """\
name: base
phases:
  - {from: 2026-01-01, phase: work}
  - {from: 2030-01-01, phase: alt, id: leave}
events:
  - {at: 2030-01-01, id: sev, type: severance, gross: 100000}
overrides:
  inflation: {stdev: 0.02}
  person: {rv_since: 1995-09-15}
  care: {hazard: [{age: 80, factor: 0.05}], cost: 2000, duration: {mean: 24}}
"""
MID = """\
name: mid
extends: base
overrides:
  allocation: null
  tax: {sparer_pauschbetrag: 500}
  shift: {leave: 2}
  events: {sev: {gross: 90000}}
"""
LEAF = """\
name: leaf
extends: mid
overrides:
  allocation: {fixed_income: [{age: 60, share: 0.4}]}
  inflation: {mean: 0.03}
  shift: {leave: 3}
  assets: {depot: {value: 7000}}
"""


@pytest.fixture
def leaf(data: Path) -> Path:
    """A chain of three files over assumptions with an allocation that the middle file switches
    off and the last one on again."""
    assumptions = data / "assumptions.yaml"
    assumptions.write_text(
        assumptions.read_text()
        + "inflation: {mean: 0.025}\n"
        + "allocation: {fixed_income: [{age: 50, share: 0.2}], rebalance_every: 6}\n"
    )
    for name, text in {"base": BASE, "mid": MID, "leaf": LEAF}.items():
        (data / "scenarios" / f"{name}.yaml").write_text(text)
    return data / "scenarios" / "leaf.yaml"


def _values(found: dict[tuple[str, ...], Leaf]) -> dict[str, Any]:
    return nested({path: leaf.value for path, leaf in found.items()})


def test_the_effective_overrides_give_the_plan_of_the_chain(data: Path, leaf: Path) -> None:
    world, scenario = split(_values(effective(data, leaf)))
    assert Assumptions.model_validate(world) == load_plan(data, leaf).assumptions
    assert scenario == split(load_scenario(leaf).overrides)[1]


def test_the_overrides_of_a_dropped_item_go_with_it(data: Path, leaf: Path) -> None:
    """The middle file sets the `gross` of `sev`, which a child of the last file drops."""
    last = leaf.with_name("last.yaml")
    last.write_text("name: last\nextends: leaf\ndrop: [sev]\n")
    found = effective(data, last)
    assert ("events", "sev", "gross") in effective(data, leaf)
    assert not any(path[0] == "events" for path in [*found, *fallback(data, last)])
    world, scenario = split(_values(found))
    assert Assumptions.model_validate(world) == load_plan(data, last).assumptions
    assert scenario == split(load_scenario(last).overrides)[1]


@pytest.mark.parametrize(
    ("path", "value", "source"),
    [
        (("person", "born"), date(1977, 1, 1), ASSUMPTIONS),
        (("person", "rv_since"), date(1995, 9, 1), "base"),  # a month, as the model reads it
        (("returns", "equity", "stdev"), 0.0, DEFAULT),
        (("inflation", "mean"), 0.03, "leaf"),
        (("inflation", "stdev"), 0.02, "base"),
        # the middle file's null gives way to the last file's mapping, which merges with the
        # assumptions again
        (("allocation", "fixed_income"), [{"age": 60, "share": 0.4}], "leaf"),
        (("allocation", "rebalance_every"), 6, ASSUMPTIONS),
        (("allocation", "skip_after_loss"), 12, DEFAULT),
        # a section that an override switches on takes the defaults of the model
        (("care", "cost"), 2000, "base"),
        (("care", "index"), "cpi", DEFAULT),
        (("care", "duration", "stdev"), 0.0, DEFAULT),
        (("tax", "sparer_pauschbetrag"), 500, "mid"),
        (("scale", "categories"), {}, DEFAULT),
        (("shift", "leave"), 3, "leaf"),
        (("events", "sev", "gross"), 90000, "mid"),
        (("assets", "depot", "value"), 7000, "leaf"),
    ],
)
def test_each_override_path_names_its_source(
    data: Path, leaf: Path, path: tuple[str, ...], value: object, source: str
) -> None:
    assert effective(data, leaf)[path] == Leaf(value, source)


def test_the_fallback_is_the_value_after_a_clear(data: Path, leaf: Path) -> None:
    written = yaml.safe_load(LEAF)["overrides"]
    inherited = fallback(data, leaf)
    for path in effective(data, leaf):
        assert inherited.get(path) == effective(data, leaf, own(written, {path: None})).get(path)


def test_the_fallback_with_the_own_overrides_gives_the_plan(data: Path, leaf: Path) -> None:
    written = leaves(yaml.safe_load(LEAF)["overrides"])
    inherited = {
        path: found.value
        for path, found in fallback(data, leaf).items()
        if not any(path[: len(at)] == at for at in written)
    }
    world = split(nested(inherited | written))[0]
    assert Assumptions.model_validate(world) == load_plan(data, leaf).assumptions


@pytest.mark.parametrize(
    ("scenario", "overrides", "path", "expected"),
    [
        ("leaf", None, ("inflation", "mean"), Leaf(0.025, ASSUMPTIONS)),
        ("leaf", None, ("assets", "depot", "value"), None),
        # the middle file's null switches the section off and the own mapping on again: what the
        # file leaves out merges with the assumptions, what it sets has the section off to inherit
        ("leaf", None, ("allocation", "rebalance_every"), Leaf(6, ASSUMPTIONS)),
        ("leaf", None, ("allocation", "fixed_income"), None),
        # an own null switches off a section that it inherits
        ("base", {"allocation": None}, ("allocation", "rebalance_every"), Leaf(6, ASSUMPTIONS)),
        # a new index: the defaults of the fields that the file leaves out
        (
            "leaf",
            {"indices": {"gold": {"mean": 0.03}}},
            ("indices", "gold", "stdev"),
            Leaf(0.0, DEFAULT),
        ),
        ("leaf", {"indices": {"gold": {"mean": 0.03}}}, ("indices", "gold", "mean"), None),
    ],
)
def test_the_fallback_names_what_a_path_inherits(
    data: Path,
    leaf: Path,
    scenario: str,
    overrides: dict[str, Any] | None,
    path: tuple[str, ...],
    expected: Leaf | None,
) -> None:
    assert fallback(data, leaf.with_stem(scenario), overrides).get(path) == expected


def test_a_file_that_does_not_load_still_gives_its_overrides(data: Path, leaf: Path) -> None:
    mid = data / "scenarios" / "mid.yaml"
    mid.write_text(mid.read_text() + "events: [{type: bogus}]\n")
    with pytest.raises(InputError):
        load_plan(data, leaf)
    assert effective(data, leaf)[("tax", "sparer_pauschbetrag")] == Leaf(500, "mid")


@pytest.mark.parametrize(
    ("before", "changes", "after"),
    [
        (
            {"inflation": {"mean": 0.03}},
            {("inflation", "stdev"): 0.02},
            {"inflation": {"mean": 0.03, "stdev": 0.02}},
        ),
        # a cleared last leaf removes its mappings
        (
            {"care": {"duration": {"mean": 24}}, "seed": 3},
            {("care", "duration", "mean"): None},
            {"seed": 3},
        ),
        ({"spending": {}}, {("spending", "cut"): None}, {"spending": {}}),
        ({"spending": None}, {("spending", "cut"): None}, {"spending": None}),
        ({"spending": {"cut": 0.1}}, {("spending",): NULL}, {"spending": None}),
        (
            {"allocation": None},
            {("allocation", "rebalance_every"): 6},
            {"allocation": {"rebalance_every": 6}},
        ),
        ({"seed": 3, "tax": {"pkv": True}}, {("seed",): 4}, {"seed": 4, "tax": {"pkv": True}}),
    ],
)
def test_own_sets_and_clears_override_paths(
    before: dict[str, Any], changes: dict[tuple[str, ...], Any], after: dict[str, Any]
) -> None:
    assert own(before, changes) == after
    assert list(own(before, changes)) == list(after)


def test_a_value_equal_to_the_fallback_stays(data: Path, leaf: Path) -> None:
    path = ("inflation", "mean")
    written = {"inflation": {"mean": 0.025}}
    assert own(written, {path: fallback(data, leaf)[path].value}) == written


@pytest.mark.parametrize(
    ("key", "mapping"),
    [
        ("shift", {"job-end": 3, "flat-sale": -2}),
        (
            "events",
            {
                "job-end": {"gross": 90000, "at": date(2027, 5, 1)},
                "flat-sale": {"when": {"age": 70}},
            },
        ),
        ("assets", {"flat": {"per_sqm": 5000}, "loan-a": {"rate": 0.03}}),
    ],
)
def test_override_rows_go_back_unchanged(key: str, mapping: dict[str, Any]) -> None:
    assert from_rows(key, rows(key, mapping)) == mapping


def test_override_rows_name_their_columns() -> None:
    assert rows("events", {"job-end": {"gross": 1}}) == [
        {"id": "job-end", "field": "gross", "value": 1}
    ]
    assert rows("assets", {"flat": {}}) == []


def test_a_row_with_an_empty_cell_inherits_and_the_later_row_wins() -> None:
    assert from_rows(
        "events",
        [
            {"id": "a", "field": "gross", "value": None},
            {"id": "", "field": "amount", "value": 1},
            {"id": "a", "field": "gross", "value": 1},
            {"id": "a", "field": "gross", "value": 2},
        ],
    ) == {"a": {"gross": 2}}


def test_leaves_end_at_lists_nulls_empty_mappings_and_item_fields() -> None:
    mapping = {
        "a": {"b": 1, "c": [1, 2], "d": None, "e": {}},
        "events": {"s": {"when": {"age": 70}}},
    }
    assert leaves(mapping) == {
        ("a", "b"): 1,
        ("a", "c"): [1, 2],
        ("a", "d"): None,
        ("a", "e"): {},
        ("events", "s", "when"): {"age": 70},
    }
    assert nested(leaves(mapping)) == mapping == nested(flatten(mapping))
