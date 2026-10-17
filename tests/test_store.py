"""YAML store: comments survive, invalid edits roll back."""

from __future__ import annotations

import difflib
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from builders import ASSETS
from builders import seen as seen_by
from ruamel.yaml.representer import RepresenterError

from dagobert import references, revisions
from dagobert.loader import APP, read_yaml
from dagobert.overrides import own
from dagobert.problems import InputError, Keys, RefusedError
from dagobert.scenariofiles import (
    act,
    concrete_scenarios,
    copied,
    created,
    listed,
    parents,
    removed,
    renamed,
    save_default_scenarios,
)
from dagobert.store import (
    NULL,
    Edit,
    Merge,
    Read,
    RowEdits,
    RowFile,
    assets_file,
    keyed,
    streams_file,
    write,
)


def test_empty_edit_keeps_the_file(data: Path) -> None:
    assets_file(data).apply(RowEdits(), source="test")
    assert (data / "assets.yaml").read_text() == ASSETS


def test_edit_add_delete(data: Path) -> None:
    file = assets_file(data)
    file.apply(
        RowEdits(
            edited={0: {"value": 1500.5, "asof": date(2026, 9, 1)}},
            added=[{"id": "tagesgeld", "kind": "fixed_income", "value": 200}],
            deleted=[1],
        ),
        source="test",
    )
    text = file.path.read_text()
    assert "# salary account" in text
    assert [r["id"] for r in file.rows()] == ["giro", "tagesgeld"]
    assert yaml.safe_load(text)["assets"][0] == {
        "id": "giro",
        "kind": "cash",
        "value": 1500.5,
        "asof": date(2026, 9, 1),
    }


def test_one_date_on_several_rows_is_written_out_each_time(data: Path) -> None:
    day = date(2026, 9, 17)
    file = assets_file(data)
    file.apply(RowEdits(edited={0: {"asof": day}, 1: {"asof": day}}), source="test")
    assert file.path.read_text().count("asof: 2026-09-17\n") == 2


COMMENTED = """\
assets:
  - id: giro
    kind: cash
{giro}  # the depot
  # of the bank
  - id: depot
    kind: equity
    value: 5000
    trades:
      - date: 2020-01-01
        kind: buy
        security: IE00B4L5Y983
        units: 10
        amount: 4000
  # the end
"""
DAY = date(2026, 9, 1)


@pytest.mark.parametrize(
    ("giro", "row", "changes", "written"),
    [
        # ruamel.yaml hangs the comment lines on the last key: a new key goes in before them
        ("    value: 1000\n", 0, {"asof": DAY}, "1000\n    asof: 2026-09-01\n  # the depot"),
        ("    value: 1000  # eol\n", 0, {"asof": DAY}, "# eol\n    asof: 2026-09-01\n  # the"),
        ("    value: 1000  # eol\n    asof: 2026-01-01\n", 0, {"asof": None}, "# eol\n  # the"),
        ("    value: 1000\n", 1, {"asof": DAY}, "4000\n    asof: 2026-09-01\n  # the end"),
        # on the last item of a block list, never inside a flow list
        (
            "    value: 1\n    tags:\n      - a\n",
            0,
            {"asof": DAY},
            "- a\n    asof: 2026-09-01\n  # the",
        ),
        (
            "    value: 1\n    tags:\n      - a\n    asof: 2026-01-01\n",
            0,
            {"asof": None},
            "- a\n  # the",
        ),
        (
            "    value: 1\n    tags: [a]\n    asof: 2026-01-01\n",
            0,
            {"asof": None},
            "tags: [a]\n  # the",
        ),
        ("    value: 1000\n", 0, {"tags": ["a"]}, "1000\n    tags:\n      - a\n  # the"),
        (  # the comment above a key after a flow list stays too
            "    value: 1\n    tags: [a]\n    # stamped\n    asof: 2026-01-01\n",
            0,
            {"asof": None},
            "tags: [a]\n    # stamped\n  # the",
        ),
    ],
)
def test_comment_lines_stay_above_the_next_row(
    data: Path, giro: str, row: int, changes: dict[str, object], written: str
) -> None:
    (data / "assets.yaml").write_text(COMMENTED.format(giro=giro))
    assets_file(data).apply(RowEdits(edited={row: changes}), source="test")
    text = (data / "assets.yaml").read_text()
    assert written in text
    assert "  # the depot\n  # of the bank\n  - id: depot\n" in text
    assert text.endswith("  # the end\n")


ROWS = (  # after a flow list ruamel.yaml keeps the comment lines on the next row
    "  - name: a\n    amount: -1  # eol a\n    tags: [x]\n",
    "  - name: b\n    amount: -2\n    tags:\n      - x\n",
    "  - name: c\n    amount: -3  # eol c\n",
)
AFTER = ("  # above b\n", "  # above c\n", "  # the end\n")


@pytest.mark.parametrize("head", ["", "  # above a\n"])
@pytest.mark.parametrize("gone", [0, 1, 2])
def test_a_deleted_row_leaves_every_other_comment_in_place(
    data: Path, head: str, gone: int
) -> None:
    text = "streams:\n" + head + "".join(r + a for r, a in zip(ROWS, AFTER, strict=True))
    (data / "cashflows.yaml").write_text(text)
    streams_file(data).apply(RowEdits(deleted=[gone]), source="test")
    assert (data / "cashflows.yaml").read_text() == text.replace(ROWS[gone], "")


def test_an_added_row_goes_above_the_comment_at_the_end(data: Path) -> None:
    text = "streams:\n" + ROWS[0] + AFTER[2]
    (data / "cashflows.yaml").write_text(text)
    streams_file(data).apply(RowEdits(added=[{"name": "d", "amount": -4}]), source="test")
    added = "  - name: d\n    amount: -4\n"
    assert (data / "cashflows.yaml").read_text() == text.replace(AFTER[2], added + AFTER[2])


BUY = "      - date: 202{}-01-01\n        kind: buy\n        security: IE00B4L5Y983\n"
BUY += "        units: 1\n"
BUYS = tuple(BUY.format(year) + "        amount: 100\n" for year in (0, 1))
TRADES = "    trades:\n      # first\n" + BUYS[0] + "      # second\n" + BUYS[1]
FONDS = "assets:\n  - id: fonds\n    kind: fixed_income\n    value: 5000\n"
FONDS += TRADES + "  # the giro\n  - id: giro\n    kind: cash\n    value: 1000\n"


DEPOT = "assets:\n  - id: depot\n    kind: equity\n    value: 100\n{basis}"
DEPOT += "  # the giro\n  - id: giro\n    kind: cash\n    value: 1000\n"


@pytest.mark.parametrize(
    ("trades", "edits", "removed"),
    [
        (False, RowEdits(edited={0: {"trades": None}}), TRADES),  # the comments inside go too
        (True, RowEdits(deleted=[0, 1]), TRADES),  # an empty block list cannot hold `# the giro`
        (True, RowEdits(deleted=[0]), BUYS[0]),
        (True, RowEdits(deleted=[1]), BUYS[1]),
    ],
    ids=["drop-list", "delete-all", "delete-first", "delete-last"],
)
def test_a_removed_list_leaves_the_comment_after_it(
    data: Path, trades: bool, edits: RowEdits, removed: str
) -> None:
    (data / "assets.yaml").write_text(FONDS)
    (assets_file(data).child("fonds", "trades") if trades else assets_file(data)).apply(
        edits, source="test"
    )
    assert (data / "assets.yaml").read_text() == FONDS.replace(removed, "")


def test_none_removes_key_and_null_is_explicit(data: Path) -> None:
    file = streams_file(data)
    file.apply(RowEdits(edited={0: {"cat": None, "index": NULL}}), source="test")
    assert yaml.safe_load(file.path.read_text())["streams"][0] == {
        "name": "Miete",
        "amount": -500,
        "index": None,
    }
    assert "index: null" in file.path.read_text()


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({1: {"cost_basis": None}}, ValueError),  # a depot without trades needs its basis
        ({0: {"value": np.float64(1234.5)}}, RepresenterError),  # the dump fails
    ],
    ids=["invalid", "dump"],
)
def test_a_failed_edit_leaves_the_file(
    data: Path, changes: dict[int, dict[str, Any]], error: type[Exception]
) -> None:
    with pytest.raises(error):
        assets_file(data).apply(RowEdits(edited=changes), source="test")
    assert (data / "assets.yaml").read_text() == ASSETS


def test_a_new_scenario_writes_its_name_parent_and_overrides(data: Path) -> None:
    act(data, lambda d: created(d, "whatif", "What if", "base", {"seed": 3}), source="test")
    assert read_yaml(data / "scenarios" / "whatif.yaml") == {
        "name": "What if",
        "extends": "base",
        "overrides": {"seed": 3},
    }
    with pytest.raises(ValueError, match="the scenario whatif exists"):
        created(data, "whatif", "Other")


def test_a_new_scenario_that_does_not_load_is_not_written(data: Path) -> None:
    with pytest.raises(ValueError, match=r"overrides\.shift\.severance: no event or phase with"):
        act(
            data,
            lambda d: created(d, "whatif", "w", "base", {"shift": {"severance": 2}}),
            source="t",
        )
    assert not (data / "scenarios" / "whatif.yaml").exists()


@pytest.mark.parametrize(
    ("stem", "name", "refused"),
    [
        *((stem, "new", "is no file name") for stem in ("", ".hidden", "../evil", "a/b", "-dash")),
        ("base", "new", "the scenario base exists"),
        ("BASE", "new", "the scenario base exists"),  # a file system may not tell them apart
        *((stem, "new", "Windows keeps") for stem in ("con", "Aux", "nul.old", "COM1", "lpt9")),
        *(
            (stem, "new", "YAML reads")
            for stem in ("on", "No", "null", "1_000", "12", "2026-01-01")
        ),
        ("new", "base", "base has the name base"),  # the results carry the name
    ],
)
def test_a_new_stem_is_a_file_name_and_its_name_is_new(
    data: Path, stem: str, name: str, refused: str
) -> None:
    for action in (created, lambda d, s, n: copied(d, "base", s, n)):
        with pytest.raises(ValueError, match=refused):
            action(data, stem, name)


CHILD = "# the child keeps this\nname: child\nextends: base\nnote: More\n"


def _family(data: Path, app: str = "scenarios: [other, base]  # what opens\n") -> None:
    (data / "scenarios" / "child.yaml").write_text(CHILD)
    (data / "scenarios" / "other.yaml").write_text("name: other\n")
    (data / APP).write_text(app)


def test_a_rename_moves_the_file_and_rewrites_extends_and_app_yaml(data: Path) -> None:
    _family(data)
    text = (data / "scenarios" / "base.yaml").read_text()
    act(data, lambda d: renamed(d, "base", "plan"), source="Scenarios: rename base → plan")
    assert not (data / "scenarios" / "base.yaml").exists()
    assert (data / "scenarios" / "plan.yaml").read_text() == text  # moved as it is
    child = (data / "scenarios" / "child.yaml").read_text()
    assert child == CHILD.replace("extends: base", "extends: plan")
    assert (data / APP).read_text() == "scenarios: [other, plan]  # what opens\n"
    [entry] = revisions.entries(data)[-1:]
    assert entry.source == "Scenarios: rename base → plan"
    assert entry.removed == ("scenarios/base.yaml",)


def test_a_copy_keeps_the_comments_and_the_parent_and_takes_its_name(data: Path) -> None:
    _family(data)
    act(data, lambda d: copied(d, "child", "child2", "Child two"), source="test")
    assert (data / "scenarios" / "child2.yaml").read_text() == CHILD.replace(
        "name: child", "name: Child two"
    )
    assert (data / "scenarios" / "child.yaml").read_text() == CHILD
    with pytest.raises(ValueError, match="the scenario gone is gone"):  # deleted elsewhere
        copied(data, "gone", "child3", "Child three")
    with pytest.raises(ValueError, match="the scenario gone is gone"):
        renamed(data, "gone", "child3")


def test_a_string_that_yaml_reads_as_a_value_is_written_in_quotes(data: Path) -> None:
    """ruamel.yaml writes YAML 1.2, where `on` is text; the loader reads YAML 1.1, where it is
    true: a stream named `on` must stay a name."""
    edit = Edit("cashflows.yaml", {("streams", 0, "name"): "on", ("streams", 0, "cat"): "Yes"})
    write(data, [edit], source="test")
    assert streams_file(data).rows()[0] | {} == {"name": "on", "cat": "Yes", "amount": -500}
    assert yaml.safe_load((data / "cashflows.yaml").read_text())["streams"][0]["name"] == "on"


@pytest.mark.parametrize(
    ("stem", "refused"),
    [
        ("base", "child extends it: give it another parent or delete it first"),
        ("other", "it is the last scenario that runs"),  # every page shows one
    ],
)
def test_a_delete_is_refused_while_others_extend_it_and_for_the_last_that_runs(
    data: Path, stem: str, refused: str
) -> None:
    _family(data)
    for name in ("base", "child"):
        path = data / "scenarios" / f"{name}.yaml"
        path.write_text(path.read_text() + "abstract: true\n")
    with pytest.raises(ValueError, match=refused):
        removed(data, stem)


def test_the_scenarios_that_run_follow_each_edit_of_their_files(data: Path) -> None:
    """`concrete_scenarios` keeps its answer by the texts of the scenario files: a page asks
    several times a run, and an edit, also by hand, counts at once."""
    _family(data)
    assert list(concrete_scenarios(data)) == ["base", "child", "other"]
    other = data / "scenarios" / "other.yaml"
    other.write_text("name: other\nabstract: true\n")
    assert list(concrete_scenarios(data)) == ["base", "child"]
    other.write_text("name: other\n")
    assert list(concrete_scenarios(data)) == ["base", "child", "other"]


def test_a_delete_removes_the_file_and_its_entries_of_app_yaml(data: Path) -> None:
    _family(data, "scenarios:\n  - other\n  # the reference\n  - base\n  - child\n")
    act(data, lambda d: removed(d, "child"), source="test")
    assert not (data / "scenarios" / "child.yaml").exists()
    assert (data / APP).read_text() == "scenarios:\n  - other\n  # the reference\n  - base\n"
    assert revisions.entries(data)[-1].removed == ("scenarios/child.yaml",)


def test_the_parents_leave_out_the_scenario_and_those_that_extend_it(data: Path) -> None:
    _family(data)
    (data / "scenarios" / "grandchild.yaml").write_text("name: g\nextends: child\n")
    refs = references.of(data)
    assert parents(refs, "base") == ["other"]
    assert parents(refs, "child") == ["base", "other"]


def test_a_file_action_is_refused_when_its_files_changed_since_the_list(data: Path) -> None:
    _family(data)
    shown = listed(data, lambda d: removed(d, "other"))
    write(data, [Edit("scenarios/other.yaml", {("note",): "new"})], source="other device")
    with pytest.raises(revisions.ConflictError, match="by other device"):
        act(data, lambda d: removed(d, "other"), source="test", shown=shown)
    shown = listed(data, lambda d: removed(d, "other"))
    (data / "scenarios" / "late.yaml").write_text("name: late\nextends: other\n")
    with pytest.raises(ValueError, match="late extends it"):
        act(data, lambda d: removed(d, "other"), source="test", shown=shown)
    assert (data / "scenarios" / "other.yaml").exists()


@pytest.mark.parametrize("basis", ["", "    cost_basis: 90\n"])
def test_a_new_list_goes_above_the_comment_after_its_row(data: Path, basis: str) -> None:
    text = DEPOT.format(basis=basis)
    (data / "assets.yaml").write_text(text)
    buy = {"date": date(2020, 1, 1), "kind": "buy", "security": "IE00B4L5Y983", "units": 1}
    edits = RowEdits(added=[buy | {"amount": 100}], parent={"cost_basis": None})
    assets_file(data).child("depot", "trades").apply(edits, source="test")
    trades = "    trades:\n" + BUYS[0]
    assert (data / "assets.yaml").read_text() == text.replace(basis, "").replace(
        "  # the giro", trades + "  # the giro"
    )


def test_result_previews_the_rows() -> None:
    edits = RowEdits(edited={0: {"a": 2, "b": None}}, added=[{"a": 9}], deleted=[1])
    assert edits.result([{"a": 1, "b": 1}, {"a": 5}]) == [{"a": 2}, {"a": 9}]
    nulls = RowEdits(edited={0: {"a": NULL}})
    assert nulls.result([{"a": 1, "c": None}]) == [{"a": None, "c": None}]
    rows = [{"at": 1, "stream": {"name": "Abo", "amount": -6}}]
    merged = RowEdits(edited={0: {"stream": Merge({"amount": -7, "every": 3})}}).result(rows)
    assert merged == [{"at": 1, "stream": {"name": "Abo", "amount": -7, "every": 3}}]
    assert rows[0]["stream"] == {"name": "Abo", "amount": -6}


TRADE = {"date": date(2026, 1, 5), "kind": "buy", "security": "IE00B4L5Y983", "units": 1}
NAMED_BY = ("date", "kind", "security")


def _by_name(rows: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    return {name: dict(rows[i]) for name, i in keyed(rows, NAMED_BY).items()}


@pytest.mark.parametrize(
    "after",
    [
        [TRADE | {"units": 2}, TRADE | {"kind": "sell"}],  # an edit
        [TRADE, TRADE | {"kind": "sell"}, TRADE | {"units": 3}],  # a second of one name
        [TRADE | {"kind": "sell"}],  # a removal
        [TRADE | {"kind": "sell"}, TRADE],  # a new order
        [TRADE | {"units": None, "fees": 1}, TRADE | {"kind": "sell"}],  # a null, a field
        [{k: v for k, v in TRADE.items() if k != "units"}, TRADE | {"kind": "sell"}],  # one less
    ],
    ids=["edit", "addition", "removal", "order", "null", "field"],
)
def test_between_gives_the_edits_from_one_version_to_another(after: list[dict[str, Any]]) -> None:
    before = [TRADE, TRADE | {"kind": "sell"}]
    edits = RowEdits.between(before, after, NAMED_BY)
    assert _by_name(edits.result(before)) == _by_name(after)
    assert not RowEdits.between(before, list(reversed(before)), NAMED_BY)


def test_onto_moves_the_edits_by_name() -> None:
    before = [{"id": "giro", "value": 1}, {"id": "depot", "value": 2}, {"id": "bau", "value": 3}]
    after = [{"id": "neu", "value": 0}, before[2], before[0]]  # depot removed, neu new
    edits = RowEdits(edited={0: {"value": 5}}, added=[{"id": "x"}], deleted=[2], parent={"a": 1})
    moved = edits.onto(before, after, ("id",))
    assert moved == RowEdits({2: {"value": 5}}, [{"id": "x"}], [1], {"a": 1})
    with pytest.raises(KeyError):
        RowEdits(edited={1: {"value": 5}}).onto(before, after, ("id",))


BAR = "  - id: bar\n    kind: cash\n    value: 5\n"  # an asset that another device puts first


def test_a_save_refuses_an_edit_of_a_row_changed_since(data: Path) -> None:
    """Row by row: an edit of a row that another device changed is refused, an edit of another
    row goes onto the file as it is now, not by the index that the page read."""
    file = assets_file(data)
    read = Read(*file.contents(), revisions.last_change(data, file.name), ("id",))
    (data / "assets.yaml").write_text(ASSETS.replace("assets:\n", "assets:\n" + BAR))
    file.apply(RowEdits(edited={1: {"value": 900}}), source="phone")
    other = file.path.read_text()
    with pytest.raises(revisions.ConflictError, match="by phone") as caught:
        file.apply(RowEdits(edited={0: {"value": 1100}}), source="desktop", read=read)
    assert caught.value.file == "assets.yaml"
    assert file.path.read_text() == other
    file.apply(RowEdits(edited={1: {"value": 6000}}), source="desktop", read=read)
    assert {r["id"]: r["value"] for r in file.rows()} == {"bar": 5, "giro": 900, "depot": 6000}


@pytest.mark.parametrize(("field", "refused"), [("value", False), ("cost_basis", True)])
def test_a_save_of_trades_checks_the_basis_that_it_clears(
    data: Path, field: str, refused: bool
) -> None:
    """The first buy of a depot clears its `cost_basis` (`RowEdits.parent`): a basis changed since
    refuses it, another field of the asset, such as a value that a price records, does not."""
    trades = assets_file(data).child("depot", "trades")
    read = Read(*trades.contents(), revisions.last_change(data, "assets.yaml"), NAMED_BY)
    assets_file(data).apply(RowEdits(edited={1: {field: 4500}}), source="phone")
    buy = RowEdits(added=[TRADE | {"amount": 100}], parent={"cost_basis": None})
    if refused:
        with pytest.raises(revisions.ConflictError, match="by phone"):
            trades.apply(buy, source="desktop", read=read)
        assert assets_file(data).rows()[1]["cost_basis"] == 4500
    else:
        trades.apply(buy, source="desktop", read=read)
        assert "cost_basis" not in assets_file(data).rows()[1]


def test_new_rows_checked_against_all_rows_refuse_any_change_of_them(data: Path) -> None:
    """The trade import checks its rows against every trade (`seen`): a trade added since refuses
    them, a value recorded on the asset does not."""
    buy = TRADE | {"amount": 100}
    trades = assets_file(data).child("depot", "trades")
    trades.apply(RowEdits(added=[buy], parent={"cost_basis": None}), source="test")
    seen = seen_by(data, "assets.yaml", trades.rows())
    assets_file(data).apply(RowEdits(edited={1: {"value": 4500}}), source="Snapshot")
    later = buy | {"date": date(2026, 2, 2)}
    trades.apply(RowEdits(added=[later]), source="desktop", seen=seen)
    other = assets_file(data).path.read_text()
    with pytest.raises(revisions.ConflictError, match="by desktop"):
        trades.apply(RowEdits(added=[later | {"units": 2}]), source="phone", seen=seen)
    assert assets_file(data).path.read_text() == other


def test_rows_of_an_asset_are_found_by_its_id(data: Path) -> None:
    """A row inserted before the asset on another device, or the asset removed: its trades go
    into it or nowhere. Its first trade starts the list; a trade that the lots refuse, nothing."""
    trades = assets_file(data).child("depot", "trades")
    assert trades.rows() == []
    (data / "assets.yaml").write_text(ASSETS.replace("assets:\n", "assets:\n" + BAR))
    buy = TRADE | {"amount": 100}
    trades.apply(RowEdits(added=[buy], parent={"cost_basis": None}), source="test")
    assert [dict(t) for t in trades.rows()] == [buy]
    assert "cost_basis" not in assets_file(data).rows()[2]
    with pytest.raises(ValueError, match="units more than held"):
        trades.apply(RowEdits(added=[buy | {"kind": "sell", "units": 2}]), source="test")
    assets_file(data).apply(RowEdits(deleted=[2]), source="test")
    with pytest.raises(RefusedError, match="no row with id depot"):
        trades.apply(RowEdits(added=[buy]), source="test")


LAYOUT = """\
# the world
person: { born: 1977-01-01, horizon_age: 51 }  # me
start: 2026-01-01
phases: {work: {}, unemployed: {}, alt: {}, retired: {}}
returns:
  equity: { mean: 0.05,
    stdev: 0.15 }
  fixed_income: {mean: 0.03}
  cash: {mean: 0.02}
  property: {mean: 0.01}
allocation:
  fixed_income:
  - {age: 30, share: 0.2}
  - {age: 50, share: 0.4}  # later
  # every year
  rebalance_every: 12
# the end
"""


def _changed(old: str, new: str) -> list[str]:
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), n=0, lineterm="")
    return [line for line in diff if line[:1] in "+-" and line[:3] not in ("+++", "---")]


def test_after_one_dump_an_edit_changes_its_own_lines(data: Path) -> None:
    path = data / "assumptions.yaml"
    path.write_text(LAYOUT)
    assert Edit(path.name).text(data) == LAYOUT  # nothing to change, no dump
    write(data, [Edit(path.name, {("seed",): 7})], source="test")
    once = path.read_text()
    assert [line for line in once.splitlines() if "#" in line] == [
        "# the world",
        "person: {born: 1977-01-01, horizon_age: 51}    # me",
        "    - {age: 50, share: 0.4} # later",
        "  # every year",
        "# the end",
    ]
    glide = RowEdits(added=[{"age": 60, "share": 0.5}])
    values: dict[Keys, Any] = {
        ("returns", "equity", "stdev"): 0.17,
        ("returns", "gold"): {"mean": 0.04},
    }
    edit = Edit(path.name, values, {("allocation", "fixed_income"): glide})
    write(data, [edit], source="test")
    assert _changed(once, path.read_text()) == [
        "-  equity: {mean: 0.05, stdev: 0.15}",
        "+  equity: {mean: 0.05, stdev: 0.17}",
        "+  gold: {mean: 0.04}",  # a new entry of scalars in the style of the one before it
        "+    - {age: 60, share: 0.5}",
    ]
    assert "    - {age: 60, share: 0.5}\n  # every year\n" in path.read_text()


EVENTS = """\
name: base
phases: [{from: 2026-01-01, phase: work}]
events:
  - at: 2027-01-01
    type: add_stream
    # the subscription
    stream:
      name: Abo
      amount: -6  # monthly
    # after the stream
  # the gift
  - at: 2028-01-01
    type: lump_sum
    amount: 1000
"""


@pytest.mark.parametrize(
    ("changes", "old", "new"),
    [
        ({"amount": -7, "every": 3}, "-6  # monthly\n", "-7  # monthly\n      every: 3\n"),
        ({"amount": None}, "      name: Abo\n      amount: -6  # monthly\n", "      name: Abo\n"),
    ],
)
def test_a_merge_keeps_the_comment_lines_of_the_event(
    data: Path, changes: dict[str, Any], old: str, new: str
) -> None:
    path = data / "scenarios" / "base.yaml"
    path.write_text(EVENTS)
    edits = RowEdits(edited={0: {"stream": Merge(changes)}})
    assert RowFile(data, "scenarios/base.yaml", ("events",)).text(edits) == EVENTS.replace(old, new)


SPENDING = """\
person: {born: 1977-01-01, horizon_age: 51}
start: 2026-01-01
phases: {work: {}, unemployed: {}, alt: {}, retired: {}}
returns:
  equity: {mean: 0.05}
  fixed_income: {mean: 0.03}
  cash: {mean: 0.02}
  property: {mean: 0.01}
# the rule
spending:
  cut: 0.1
{trigger}# the seed
seed: 7
"""


@pytest.mark.parametrize(
    ("trigger", "gone"),
    [("", "spending:\n  cut: 0.1\n"), ("  trigger: 0.2\n", "  cut: 0.1\n")],
    ids=["last-key", "sibling"],
)
def test_a_clear_removes_the_mapping_it_empties(data: Path, trigger: str, gone: str) -> None:
    """The comment lines around it stay, also those after the mapping that goes."""
    text = SPENDING.replace("{trigger}", trigger)
    (data / "assumptions.yaml").write_text(text)
    edit = Edit("assumptions.yaml", {("spending", "cut"): None})
    assert edit.text(data) == text.replace(gone, "")


OVERRIDES = {
    "inflation": {"mean": 0.03, "stdev": 0.01},
    "spending": {"cut": 0.1},
    "allocation": None,
    "events": {"job-end": {"gross": 5000}},
}


@pytest.mark.parametrize(
    "changes",
    [
        {("inflation", "mean"): 0.04},
        {("inflation", "mean"): None},
        {("spending", "cut"): None},
        {("spending", "cut"): None, ("inflation", "mean"): None, ("inflation", "stdev"): None},
        {("care",): NULL},
        {("allocation", "rebalance_every"): 6},
        {("allocation", "rebalance_every"): None},
        {("events", "job-end", "gross"): None, ("shift", "job-end"): 3},
        {("returns", "gold"): {"mean": 0.03, "stdev": 0.1}},
        {("indices", "salary", "mean"): None},
    ],
)
def test_an_edit_of_the_overrides_writes_what_own_gives(
    data: Path, changes: dict[tuple[str, ...], Any]
) -> None:
    """The editor checks the candidate of `overrides.own` and saves the same changes by key path
    into the document."""
    (data / "scenarios" / "base.yaml").write_text(yaml.safe_dump({"overrides": OVERRIDES}))
    values: dict[Keys, Any] = {("overrides", *path): value for path, value in changes.items()}
    text = Edit("scenarios/base.yaml", values).text(data)
    assert text is not None
    assert yaml.safe_load(text).get("overrides", {}) == own(OVERRIDES, changes)


def test_one_write_changes_every_file_or_none(data: Path) -> None:
    before = {p: p.read_text() for p in (data / "assumptions.yaml", data / "scenarios/base.yaml")}
    edits = [
        Edit("assumptions.yaml", {("inflation", "mean"): 0.03}),
        Edit("scenarios/base.yaml", {("overrides", "shift", "job-end"): 2}),
    ]
    with pytest.raises(ValueError, match=r"overrides\.shift\.job-end: no event or phase with"):
        write(data, edits, source="test")
    assert {p: p.read_text() for p in before} == before
    write(
        data,
        [*edits[:1], *created(data, "new", "new")],
        source="test",
    )
    assert revisions.entries(data)[-1].files == ("assumptions.yaml", "scenarios/new.yaml")
    write(data, [Edit("scenarios/new.yaml", remove=True)], source="test")
    assert revisions.entries(data)[-1].removed == ("scenarios/new.yaml",)
    assert not (data / "scenarios" / "new.yaml").exists()


def test_two_edits_of_one_file_are_refused(data: Path) -> None:
    edits = [Edit("assumptions.yaml", {("seed",): 1}), Edit("assumptions.yaml", {("seed",): 2})]
    with pytest.raises(ValueError, match=r"one edit per file: assumptions\.yaml"):
        write(data, edits, source="test")
    assert revisions.entries(data) == ()


def test_check_runs_inside_the_write(data: Path) -> None:
    """A part that changed since the page read it refuses the save."""
    file = "assumptions.yaml"

    def part() -> object:
        return read_yaml(data / file).get("inflation")

    seen = seen_by(data, file, part())
    write(data, [Edit(file, {("inflation", "mean"): 0.03})], source="other device")
    text = (data / file).read_text()
    with pytest.raises(revisions.ConflictError, match="by other device"):
        write(
            data,
            [Edit(file, {("inflation", "stdev"): 0.02})],
            source="test",
            check=lambda: revisions.unchanged(data, seen, part()),
        )
    assert (data / file).read_text() == text


def test_an_unknown_key_of_app_yaml_is_refused(data: Path) -> None:
    with pytest.raises(InputError, match=r"app\.yaml:1: model: unknown key"):
        write(data, [Edit(APP, {("model",): "fixed"})], source="test")
    assert not (data / APP).exists()


ADDED = RowEdits(added=[{"id": "x"}])


@pytest.mark.parametrize(
    ("text", "edit", "error"),
    [
        (
            None,
            Edit("assumptions.yaml", {("start", "month"): 1}),
            r"assumptions\.yaml:2: start holds no mapping: 2026",
        ),
        (
            "streams: 5\n",
            Edit("cashflows.yaml", rows={("streams",): ADDED}),
            r"cashflows\.yaml:1: streams holds no list: 5",
        ),
        (
            "# hand edit\n- id: giro\n",
            Edit("assets.yaml", rows={("assets",): ADDED}),
            r"assets\.yaml:2: no mapping at the top level",
        ),
    ],
    ids=["value-on-the-way", "rows-a-scalar", "top-level-a-list"],
)
def test_a_hand_edit_of_another_shape_refuses_an_edit(
    data: Path, text: str | None, edit: Edit, error: str
) -> None:
    """A hand edit refuses the edit with its file and line, not as an error of the code."""
    if text:
        (data / edit.name).write_text(text)
    with pytest.raises(RefusedError, match=error):
        edit.text(data)


@pytest.mark.parametrize(
    ("text", "keys", "error"),
    [
        ("- id: giro\n", ("assets",), r"assets\.yaml:1: no mapping at the top level"),
        ("5\n", ("assets",), r"assets\.yaml: no mapping at the top level"),
        (
            "person:\n  relatives:\n    anna: 5\n",
            ("person", "relatives", "anna", "given"),
            r"assets\.yaml:3: person\.relatives\.anna holds no mapping: 5",
        ),
    ],
    ids=["list", "scalar", "holder"],
)
def test_a_hand_edit_of_another_shape_refuses_a_read(
    data: Path, text: str, keys: Keys, error: str
) -> None:
    (data / "assets.yaml").write_text(text)
    with pytest.raises(RefusedError, match=error):
        RowFile(data, "assets.yaml", keys).rows()


EQUAL = """\
tax:
  pkv: true
spending:
  cut: 0.10  # ten percent
  categories: [food, fun]
  age_curve:
    # at 80
    - age: 80
      factor: 0.9
    # at 90
    - age: 90
      factor: 0.8
"""


@pytest.mark.parametrize(
    ("values", "old", "new"),
    [
        ({("spending", "cut"): 0.1, ("spending", "categories"): ["food", "fun"]}, "", ""),
        (
            {("spending", "age_curve"): [{"age": 80, "factor": 0.9}, {"age": 90, "factor": 0.8}]},
            "",
            "",
        ),
        ({("tax", "pkv"): 1}, "pkv: true", "pkv: 1"),
        ({("spending", "cut"): 0.2}, "0.10  # ten", "0.2   # ten"),
    ],
    ids=["scalars", "list", "bool-is-no-number", "changed"],
)
def test_an_equal_value_keeps_its_text(
    data: Path, values: dict[Keys, Any], old: str, new: str
) -> None:
    (data / "assumptions.yaml").write_text(EQUAL)
    assert Edit("assumptions.yaml", values).text(data) == EQUAL.replace(old, new)


ONE_EVENT = """\
name: base
events:
  # the gift
  - at: 2028-01-01
    type: lump_sum
    amount: 1000
  # after it
# the end
"""
FLOW_ROWS = """\
spending:
  cut: 0.1
  age_curve:
    - {age: 80, factor: 0.9}
    - {age: 90, factor: 0.8}
# the seed
seed: 7
"""
CURVE = "  age_curve:\n    - {age: 80, factor: 0.9}\n    - {age: 90, factor: 0.8}\n"


@pytest.mark.parametrize(
    ("text", "edit", "written"),
    [
        (
            ONE_EVENT,
            Edit("scenarios/base.yaml", rows={("events",): RowEdits(deleted=[0])}),
            "name: base\nevents: []\n  # the gift\n  # after it\n# the end\n",
        ),
        (
            ONE_EVENT,
            Edit("scenarios/base.yaml", {("events", 0): None}),
            "name: base\nevents: []\n  # the gift\n  # after it\n# the end\n",
        ),
        (
            FLOW_ROWS,
            Edit("assumptions.yaml", {("spending", "age_curve"): None}),
            FLOW_ROWS.replace(CURVE, ""),
        ),
        (
            FLOW_ROWS,
            Edit("assumptions.yaml", rows={("spending", "age_curve"): RowEdits(deleted=[0, 1])}),
            FLOW_ROWS.replace(CURVE, ""),
        ),
        (
            FLOW_ROWS,
            Edit("assumptions.yaml", {("spending", "trigger"): 0.2}),
            FLOW_ROWS.replace("# the seed", "  trigger: 0.2\n# the seed"),
        ),
    ],
    ids=["last-row", "last-item", "flow-rows-cleared", "flow-rows-deleted", "after-flow-rows"],
)
def test_a_list_that_goes_keeps_the_comments_around_it(
    data: Path, text: str, edit: Edit, written: str
) -> None:
    """A top-level list stays as `[]`, with the comment lines that it held behind it: in front of
    `[]` they do not parse. Comment lines after flow rows stay after them."""
    (data / edit.name).write_text(text)
    assert edit.text(data) == written
    assert yaml.safe_load(written) is not None


def test_rows_of_a_missing_section_start_it(data: Path) -> None:
    glide = RowFile(data, "assumptions.yaml", ("allocation", "fixed_income"))
    assert glide.rows() == []
    text = SPENDING.replace("{trigger}", "") + "# the end\n"
    (data / "assumptions.yaml").write_text(text)
    glide.apply(RowEdits(added=[{"age": 30, "share": 0.2}]), source="test")
    added = "allocation:\n  fixed_income:\n    - age: 30\n      share: 0.2\n"
    assert (data / "assumptions.yaml").read_text() == text.replace("# the end", added + "# the end")


def test_default_scenarios_keep_the_comments_and_the_style_of_app_yaml(data: Path) -> None:
    save_default_scenarios(data, ["base"], source="test")
    assert (data / "app.yaml").read_text() == "scenarios:\n  - base\n"
    (data / "app.yaml").write_text("# what opens\nscenarios: [base]  # the first one counts\n")
    for names in (["other", "base"], ["base", "other"]):
        save_default_scenarios(data, names, source="test")
        assert (data / "app.yaml").read_text() == (
            f"# what opens\nscenarios: [{', '.join(names)}] # the first one counts\n"
        )
