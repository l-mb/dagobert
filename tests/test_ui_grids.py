"""The editable grids without a browser: the columns from the schema, the cells as shown
and stored, the edits in the widget state, the blocks and their totals, the phone order."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest
import yaml
from apps import STREAMS
from builders import PHASE_LABELS
from german import edited
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Dataframe

from dagobert import datadir, i18n, references
from dagobert.loader import load_assumptions
from dagobert.model.assets import AvDepot, Loan, PensionPolicy, PropertyAsset
from dagobert.model.assumptions import Child
from dagobert.model.base import Unit
from dagobert.model.events import AddStreamEvent, RepayEvent, SellEvent
from dagobert.model.streams import Stream
from dagobert.money import EUR_COLUMN, NUMBER_COLUMN
from dagobert.problems import RefusedError
from dagobert.store import NULL, RowEdits, RowFile, streams_file
from dagobert.ui import (
    SIDE_PADDING,
    assets,
    cashflows,
    gridcolumns,
    gridstate,
    guard,
    mode,
    save,
    tables,
)


def _columns(model: type) -> dict[str, gridcolumns.Column]:
    return {c.name: c for c in gridcolumns.columns(model)}


EXPENSES = cashflows.with_phases(cashflows.EXPENSES, PHASE_LABELS)


def test_column_types() -> None:
    cols = _columns(Stream)
    assert cols["name"].required
    assert (cols["amount"].type, cols["every"].type, cols["start"].type) == (
        "number",
        "integer",
        "date",
    )
    assert "salary" in cols["kind"].options
    assert (cols["factor"].type, cols["factor"].unit) == ("object", Unit.FACTOR)
    assert cols["every"].help.endswith(" (default: 1)")
    assert "default" not in _columns(SellEvent)["note"].help  # an empty text names no default


def test_a_mapping_takes_a_column_per_name_of_the_table() -> None:
    """`factor` per phase of the inputs, headed by its label and as wide as it; a table without
    names for a mapping shows no column of it."""
    named = tables.Table(Stream, "s", ("name",), entries={"factor": {"alt": "Teilzeit mit Kind"}})
    cols = {c.name: c for c in named.columns()}
    alt = cols["factor alt"]
    assert (alt.key, alt.part, alt.label, alt.unit) == (
        "factor",
        "alt",
        "Teilzeit mit Kind",
        Unit.FACTOR,
    )
    assert alt.width == gridcolumns.ENTRY_PAD + gridcolumns.ENTRY_CHAR * len("Teilzeit mit Kind")
    assert "factor" not in cols
    assert not {"factor", "factor alt"} & {
        c.name for c in tables.Table(Stream, "s", ("name",)).columns()
    }


def _config(col: gridcolumns.Column) -> dict[str, object]:
    config: dict[str, object] = json.loads(json.dumps(col.config()))["type_config"]
    return config


def test_a_number_column_takes_the_format_bounds_and_step_of_its_unit() -> None:
    """Euros whole and grouped, a share or a rate in percent as typed. A minimum of 0 keeps the
    minus off the cell editor. A share takes no maximum, nor does a field saved negative: the
    grid would turn a number above it into the bound without a word."""
    policy = _columns(PensionPolicy)
    assert _config(policy["guarantee"]) == {
        "type": "number",
        "format": "%g%%",
        "min_value": 0,
        "max_value": None,  # the guard warns above 100%, the model refuses on save
        "step": 0.001,
    }
    value = _config(policy["value"])
    assert (value["format"], value["min_value"], value["step"]) == (EUR_COLUMN, 0, 0.01)
    assert _config(_columns(Loan)["update_every"])["format"] is None  # months: plain
    # a plain number keeps its decimals, a narrow space groups its thousands
    assert _config(_columns(PropertyAsset)["sqm"])["format"] == NUMBER_COLUMN
    assert _config(_columns(Loan)["balance"])["max_value"] == 0
    saved = {c.name: _config(c) for c in assets.TABLES["loan"].columns()}
    assert (saved["balance"]["min_value"], saved["balance"]["max_value"]) == (None, None)


def test_a_number_column_keeps_its_decimals() -> None:
    """Whole numbers only would make an integer column, whose editor drops the decimal mark:
    `100,5` m² became 1005. A number without a step of its unit takes any decimals."""
    cols = [c for c in gridcolumns.columns(PropertyAsset) if c.name in {"sqm", "per_sqm"}]
    cells = gridstate.frame(cols, [{"sqm": 100, "per_sqm": 5000}, {"sqm": 104}])
    assert list(cells.dtypes) == [float, float]
    sqm = next(c for c in cols if c.name == "sqm")
    assert _config(sqm)["step"] is None
    assert sqm.stored(100.5) == 100.5


def test_a_share_or_a_rate_shows_and_reads_in_percent() -> None:
    rate = _columns(Loan)["rate"]
    assert rate.shown({"rate": 0.0298}) == 2.98
    assert (rate.stored(2.98), rate.stored(1.1)) == (0.0298, 0.011)
    assert rate.help.endswith(gridcolumns.PERCENT_HELP)
    assert "(default: 30%)" in _columns(AvDepot)["lump_sum"].help
    # a default in the format of its unit, also zero and a switch
    assert "(default: 1.800 €)" in _columns(AvDepot)["contribution"].help
    assert "(default: 0%)" in _columns(Loan)["prepayment_penalty"].help


def test_the_help_of_a_column_names_a_titled_default_in_the_language() -> None:
    column = _columns(Child)["freibetrag"]
    assert "(default: half)" in column.help
    with i18n.use("de"):
        assert "halb" in column.help
        assert "(Standard: halb)" in column.help


def test_an_amount_or_all_shows_all_as_an_empty_cell() -> None:
    """An empty cell removes the key, so `all` applies again."""
    amount = _columns(RepayEvent)["amount"]
    assert amount.type == "number"
    assert (amount.shown({"amount": "all"}), amount.shown({"amount": 5000.0})) == (None, 5000.0)
    assert (amount.stored(None), amount.stored(5000.0)) == (None, 5000.0)
    assert "(default: all)" in amount.help


def test_shown_and_stored_round_trip() -> None:
    """A month shows as `2027-03`, as a form shows it, and reads with any day as the first."""
    cols = {c.name: c for c in STREAMS.columns()}
    assert cols["start"].shown({"start": date(2027, 3, 1)}) == "2027-03"
    assert cols["start"].stored("2027-03") == cols["start"].stored("2027-03-15") == date(2027, 3, 1)
    assert cols["factor retired"].shown({"factor": {"retired": 0.5}}) == 0.5
    assert cols["factor work"].shown({"factor": {"retired": 0.5}}) is None
    assert cols["index"].shown({"index": None}) == "null"
    assert cols["index"].stored("null") is NULL
    assert cols["index"].shown({}) is None
    assert cols["cat"].stored("") is None
    assert cols["every"].stored(3.0) == 3


def test_an_emptied_list_stays_where_absent_means_another_thing() -> None:
    """The bAV phases are required: `[]` is a policy that only events fund."""
    assert _columns(PensionPolicy)["phases"].stored([]) == []
    assert _columns(Stream)["phases"].stored([]) is None


def test_edits_from_state_maps_shown_rows_to_file_rows() -> None:
    edits = gridstate.edits_from_state(
        {
            "edited_rows": {"1": {"value": 10.0}},
            "added_rows": [{"id": "neu", "value": 1.0}, {}, {"value": None}],
            "deleted_rows": [0],
        },
        gridcolumns.columns(gridcolumns.ASSET_MODELS["cash"], skip=frozenset({"kind"})),
        shown=[(2, {}), (5, {})],
        fixed={"kind": "cash"},
    )
    assert edits.edited == {5: {"value": 10.0}}
    assert edits.added == [{"kind": "cash", "id": "neu", "value": 1.0}]
    assert edits.deleted == [2]


def test_edits_carried_over_all_columns_add_up_to_one_grid() -> None:
    """`All columns` draws a new grid on the rows with the edits of the old one: both sets of
    edits as one show the same rows, so they save the same. Edits of a hidden column stay."""
    cells = [{"a": 1, "b": 1}, {"a": 2, "b": 2}, {"a": 3, "b": 3}, {"a": 4, "b": 4}]
    carried = {
        "edited_rows": {"1": {"a": 20, "hidden": 9}, 3: {"a": 40}},
        "added_rows": [{"a": 5}, {"a": 6}],
        "deleted_rows": [0],
    }
    # on top: rows 1 and 3, the first new row edited, row 2 and the second new row deleted
    state = {
        "edited_rows": {0: {"b": 21}, 2: {"b": 41}, "3": {"b": 51}},
        "added_rows": [{"a": 7}],
        "deleted_rows": [1, 4],
    }
    folded = gridstate.fold(carried, state, len(cells))
    assert gridstate.applied(cells, folded) == gridstate.applied(
        gridstate.applied(cells, carried), state
    )
    assert folded["edited_rows"][1] == {"a": 20, "hidden": 9, "b": 21}
    assert gridstate.fold({}, carried, len(cells)) == gridstate.fold(carried, {}, len(cells))
    # a second turn carries the folded edits under those of a third grid: off and on again
    again = {"edited_rows": {"0": {"a": 22}, 3: {"b": 77}}, "added_rows": [], "deleted_rows": [1]}
    twice = gridstate.fold(folded, again, len(cells))
    assert gridstate.applied(cells, twice) == gridstate.applied(
        gridstate.applied(cells, folded), again
    )


@pytest.mark.parametrize(
    ("table", "row", "cells", "saved"),
    [
        (cashflows.EXPENSES, {"name": "Miete", "amount": -5.0}, {"amount": 9.0}, {"amount": -9.0}),
        (cashflows.EXPENSES, {}, {"kind": "rv_voluntary", "amount": 9.0}, {"amount": -9.0}),
        # a stream that moves to the income keeps its sign
        (cashflows.EXPENSES, {"amount": -5.0}, {"kind": "other_income", "amount": 9.0}, {}),
        (
            assets.TABLES["loan"],
            {"kind": "loan", "balance": -5.0},
            {"balance": 9.0},
            {"balance": -9.0},
        ),
        # the asset tables share `negative`: another kind keeps its sign (it raised KeyError)
        (assets.TABLES["cash"], {"kind": "cash"}, {"value": 5}, {}),
    ],
)
def test_an_expense_or_a_debt_is_saved_negative_without_a_minus(
    table: tables.Table, row: gridcolumns.Row, cells: gridcolumns.Row, saved: gridcolumns.Row
) -> None:
    assert table.signed(row, cells) == cells | saved


def test_factor_cells_merge_into_the_mapping() -> None:
    shown = [(0, {"factor": {"retired": 0.5}}), (1, {"factor": {"alt": 0.8}}), (2, {})]
    edits = gridstate.edits_from_state(
        {
            "edited_rows": {
                "0": {"factor work": 0.9},
                "1": {"factor alt": None},
                "2": {"factor retired": 0.7, "amount": -5.0},
            },
            "added_rows": [{"name": "Neu", "amount": -1.0, "factor alt": 0.5}],
        },
        STREAMS.columns(),
        shown,
        fixed={},
    )
    assert edits.result([row for _, row in shown]) == [
        {"factor": {"retired": 0.5, "work": 0.9}},
        {},
        {"factor": {"retired": 0.7}, "amount": -5.0},
        {"name": "Neu", "amount": -1.0, "factor": {"alt": 0.5}},
    ]


def test_nested_and_lifted_cells_merge_into_their_mapping(tmp_path: Path) -> None:
    """A nested model takes a column per field (`when age`), a lifted one (the `stream` of an
    `add_stream`) its fields under their own names. An edit merges into the mapping and keeps
    what no cell changes, the comment lines inside it too. `then`, a list of mappings, takes no
    column."""
    sale = gridcolumns.columns(SellEvent, frozenset({"type"}))
    assert {"when age", "when liquid_below"} <= {c.name for c in sale}
    assert "then" not in {c.key for c in sale}
    rows: list[gridcolumns.Row] = [{"when": {"age": 70}}, {"when": {"age": 70}}, {"at": 2030}]
    edits = gridstate.edits_from_state(
        {
            "edited_rows": {
                "0": {"when liquid_below": 50000.0},
                "1": {"when age": None},
                "2": {"when age": 75.0},
            }
        },
        sale,
        list(enumerate(rows)),
        fixed={"type": "sell"},
    )
    assert edits.result(rows) == [
        {"when": {"age": 70, "liquid_below": 50000.0}},
        {},  # the last field goes with its mapping
        {"at": 2030, "when": {"age": 75.0}},
    ]
    table = tables.Table(
        AddStreamEvent,
        "add",
        ("type", "at"),
        fixed={"type": "add_stream"},
        inner="stream",
        gates={"factor": "phases"},
        entries={"factor": PHASE_LABELS},
    )
    cols = table.columns()
    stream = {"name": "Rente", "kind": "pension", "gross": 1500.0, "index": None}
    by_name = {c.name: c for c in cols}
    assert [by_name[name].shown({"stream": stream}) for name in ("gross", "index")] == [
        1500.0,
        "null",
    ]
    assert by_name["share"].unit is Unit.PERCENT
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios" / "x.yaml").write_text(
        "name: x\n"
        "events:\n"
        "  - type: add_stream\n"
        "    at: 2040-01-01\n"
        "    stream:\n"
        "      name: Rente\n"
        "      kind: pension\n"
        "      # Renteninformation 2026\n"
        "      gross: 1500\n"
        "      index: null\n"
    )
    file = RowFile(tmp_path, "scenarios/x.yaml", ("events",))
    edits = gridstate.edits_from_state(
        {
            "edited_rows": {"0": {"gross": 1600.0, "note": "later", "factor retired": 0.5}},
            "added_rows": [{"at": "2041-01-01", "name": "Neu", "amount": -50.0}],
        },
        cols,
        list(enumerate(file.rows())),
        fixed=table.fixed,
    )
    text = str(file.text(edits))
    assert "      # Renteninformation 2026\n      gross: 1600.0\n" in text
    assert yaml.safe_load(text)["events"] == [
        {
            "type": "add_stream",
            "at": date(2040, 1, 1),
            "note": "later",
            "stream": stream | {"gross": 1600.0, "factor": {"retired": 0.5}},  # null stays
        },
        {"type": "add_stream", "at": date(2041, 1, 1), "stream": {"name": "Neu", "amount": -50.0}},
    ]
    found = guard.changes(file.rows(), edits, units=table.units())
    # an event by its month and the stream it adds
    assert guard.Change("2040-01 Rente stream gross", 1500.0, 1600.0) in found
    assert guard.Change("2041-01 Neu stream amount", None, -50.0) in found


def test_map_rows_round_trip() -> None:
    """A mapping of mappings as rows with a key column and back, with a renamed key and a removed
    row."""
    returns = {"equity": {"mean": 0.07, "stdev": 0.15}, "gold": {"mean": 0.03}, "x": {}}
    rows = tables.MapRows()
    assert rows.mapping(rows.rows(returns)) == returns
    edits = RowEdits(edited={1: {"name": "silver", "stdev": 0.2}}, deleted=[2])
    assert rows.mapping(edits.result(rows.rows(returns))) == {
        "equity": {"mean": 0.07, "stdev": 0.15},
        "silver": {"mean": 0.03, "stdev": 0.2},
    }
    factors = tables.MapRows("category", "factor")
    assert factors.rows({"wohnen": 0.9}) == [{"category": "wohnen", "factor": 0.9}]
    assert factors.mapping([{"category": "wohnen", "factor": 0.9}, {"factor": 1.0}]) == {
        "wohnen": 0.9
    }


def test_a_saved_row_keeps_its_id_or_name() -> None:
    """Other inputs and the history name a row by it: the edit is dropped and named, a new row
    takes any."""
    loan = assets.TABLES["loan"]
    cells, notes = loan.held({"id": "kredit", "name": "KfW"}, {"id": "kredit2", "rate": 0.02})
    assert cells == {"rate": 0.02}
    assert notes == ["**KfW** keeps its id kredit, kredit2 is not saved"]
    assert loan.held({"id": "kredit"}, {"id": None})[1] == [
        "**kredit** keeps its id kredit, empty is not saved"
    ]
    assert loan.held({"id": "kredit"}, {"id": "kredit", "rate": 0.02}) == (
        {"id": "kredit", "rate": 0.02},
        [],
    )
    assert cashflows.EXPENSES.locked == ("name",)
    assert tables.LOCKED_HELP in {c.name: c for c in cashflows.EXPENSES.columns()}["name"].help


def test_reference_columns_take_the_names_that_exist(data: Path) -> None:
    """`index` takes the consumer prices, the indices and null (a nominal amount), `of` a salary
    stream that is no bonus, `repays` a loan, `after_sale_of` a property, `tags` also a new
    name."""
    (data / "assumptions.yaml").write_text(
        (data / "assumptions.yaml").read_text() + "indices:\n  salary: {mean: 0.03}\n"
    )
    (data / "assets.yaml").write_text(
        "assets:\n"
        "  - {id: flat, kind: property, sqm: 50, per_sqm: 4000}\n"
        "  - {id: kredit, kind: loan, balance: -1000, rate: 0.02, annuity: 100}\n"
    )
    (data / "cashflows.yaml").write_text(
        "streams:\n"
        "  - {name: Gehalt, kind: salary, gross: 5000, tags: [job]}\n"
        "  - {name: Bonus, kind: salary, of: Gehalt, share: 0.1, every: 12}\n"
        "  - {name: Miete, cat: wohnen, amount: -500, tags: [flat]}\n"
    )
    table, rows = cashflows.INCOME, streams_file(data).rows()
    everything = table.columns(everything=True)
    cols = {c.name: c for c in table.referenced(everything, references.of(data), None, rows)}
    assert _config(cols["index"])["options"] == ["cpi", "salary", "null"]
    assert (cols["of"].options, cols["repays"].options, cols["after_sale_of"].options) == (
        ("Gehalt",),
        ("kredit",),
        ("flat",),
    )
    tags = _config(cols["tags"])
    assert (tags["type"], tags["accept_new_options"]) == ("multiselect", True)
    assert cols["tags"].options == ("flat", "job")


@pytest.mark.parametrize(
    ("edit", "amount"), [({"name": "Handy"}, -11.95), ({"amount": -27.49}, -27.49)]
)
def test_edits_keep_the_cents_that_the_grid_hides(
    data: Path, edit: dict[str, object], amount: float
) -> None:
    """The grid shows whole euros. The file keeps the cents, edited or not."""
    file = streams_file(data)
    file.path.write_text("streams:\n  - name: Abo\n    cat: medien\n    amount: -11.95\n")
    table = cashflows.EXPENSES
    file.apply(
        gridstate.edits_from_state(
            {"edited_rows": {"0": edit}}, table.columns(), list(enumerate(file.rows())), fixed={}
        ),
        source="test",
    )
    assert file.rows()[0]["amount"] == amount
    assert f"amount: {amount}\n" in file.path.read_text()


def test_table_filters_orders_and_colors() -> None:
    rows = [
        {"name": "b", "cat": "wohnen"},
        {"name": "Gehalt", "cat": "gehalt", "kind": "salary"},
        {"name": "a", "cat": "wohnen"},
        {"name": "Abo", "cat": "medien"},
    ]
    assert cashflows.EXPENSES.indices(rows) == [3, 2, 0]
    assert cashflows.INCOME.indices(rows) == [1]
    assert {"of", "share"} <= {c.name for c in cashflows.INCOME.columns()}  # a bonus shows it
    names = [c.name for c in EXPENSES.columns()]
    assert names[:2] == ["name", "amount"]
    assert "factor retired" in names
    assert not {"gross", "phases", "cat", "index"} & set(names)
    everything = [c.name for c in EXPENSES.columns(everything=True)]
    assert everything[: len(names)] == names and {"cat", "index"} <= set(everything)
    assert "phases" not in everything
    colors = tables.row_colors(["wohnen", "medien", "wohnen"])
    assert len(set(colors.values())) == len(colors) == 2


def test_total_row_puts_the_phase_sums_under_their_columns() -> None:
    cols = EXPENSES.columns()
    line = tables.total_row(cols, {"name": "per month", "factor alt": "-90 €", "cat": "unlisted"})
    cells = re.findall(r'">([^<]*)</div>', line)
    upto_alt = cols[: [c.name for c in cols].index("factor alt") + 1]
    assert cells == [
        "per month" if c.name == "name" else "-90 €" * (c.part == "alt") for c in upto_alt
    ]
    assert f"width: {gridcolumns.WIDTHS['name']}px" in line and "unlisted" not in line


def test_block_label_names_the_group_and_its_totals() -> None:
    cols = EXPENSES.columns()
    cells = {"name": "per month", "factor alt": "-90 €", "factor work": "-100 €", "cat": "x"}
    assert tables.block_label("wohnen", 3, cols, cells).replace("\u00a0", "_") == (
        "**wohnen** (3) · per_month · Work_-100_€ · Career_break_-90_€"  # each on one line
    )
    assert tables.block_label("a_*b*", 1, [], {}) == r"**a\_\*b\*** (1)"  # the group is user text


def test_a_phone_shows_what_an_asset_is_worth_beside_its_id() -> None:
    loan = assets.TABLES["loan"]
    assert [c.name for c in loan.phone_order(loan.columns())][:3] == ["id", "balance", "rate"]
    assert [c.name for c in loan.columns()][:2] == ["id", "name"]  # the desktop keeps its order
    streams = cashflows.EXPENSES.columns()
    assert cashflows.EXPENSES.phone_order(streams) == streams


@pytest.mark.parametrize(
    ("table", "window"), [(cashflows.EXPENSES, 1500), (cashflows.INCOME, 1760)]
)
def test_stream_grids_fit_their_window(table: tables.Table, window: int) -> None:
    """With the phases of a new plan, `alt` labeled."""
    content = window - 300 - 2 * SIDE_PADDING  # less the sidebar and the side padding
    labels = load_assumptions(datadir.EXAMPLE).phase_labels
    new = {name: label for name, label in labels.items() if name in datadir.NEW_PHASES}
    shown = cashflows.with_phases(table, new)
    assert tables.ROW_MARKER + sum(c.width for c in shown.columns()) <= content


def test_phase_cells_carry_phases_and_factor() -> None:
    cols = EXPENSES.columns()
    by_name = {c.name: c for c in cols}
    gated: gridcolumns.Row = {"phases": ["work", "alt"], "factor": {"alt": 0.8}}
    cells = [by_name[f"factor {p}"].shown(gated) for p in ("work", "unemployed", "alt", "retired")]
    assert cells == [1.0, 0.0, 0.8, 0.0]
    assert by_name["factor work"].shown({}) == 1.0
    # an explicit YAML null is the same as a missing `phases` key: all phases apply
    assert by_name["factor work"].shown({"phases": None}) == 1.0
    assert by_name["factor alt"].shown({"phases": None, "factor": {"alt": 0.5}}) == 0.5

    shown: list[tuple[int, gridcolumns.Row]] = [
        (0, gated),
        (1, {"amount": -5}),
        (2, {"phases": ["work"]}),
        (3, gated),
    ]
    edits = gridstate.edits_from_state(
        {
            "edited_rows": {
                "0": {"factor retired": 0.5},  # switch retired on at half
                "1": {"factor work": 0, "factor alt": 1},  # switch work off, 1 is the default
                "2": {"factor unemployed": None, "factor alt": None, "factor retired": None},
                "3": {"amount": -7.0},  # phase cells untouched
            }
        },
        cols,
        shown,
        fixed={},
    )
    assert edits.edited == {
        0: {"factor": {"alt": 0.8, "retired": 0.5}, "phases": ["work", "alt", "retired"]},
        1: {"factor": None, "phases": ["unemployed", "alt", "retired"]},
        2: {"factor": None, "phases": None},
        3: {"amount": -7.0},
    }


def test_rare_and_hidden_columns_show_only_with_all_columns() -> None:
    """`more` and the columns that the mode or a feature hides leave the grid until `All
    columns`, also of a table that shows every field."""
    rare = {"cat", "index"}
    assert not rare & {c.name for c in EXPENSES.columns()}
    assert rare <= {c.name for c in EXPENSES.columns(everything=True)}
    prop = assets.TABLES["property"]
    assert "tags" not in {c.name for c in prop.columns(hidden={"tags"})}
    assert "tags" in {c.name for c in prop.columns(everything=True, hidden={"tags"})}
    assert "of" not in {c.name for c in cashflows.INCOME.columns(hidden={"of"})}


MODE_GRID = """
from pathlib import Path
from dagobert.store import assets_file, streams_file
from dagobert.ui import assets, cashflows, mode, tables
data = Path({data!r})
tables.edit_table(assets_file(data), assets.TABLES["cash"], mode.view(data))
tables.edit_table(assets_file(data), assets.TABLES["property"], mode.view(data))
income = cashflows.with_phases(cashflows.INCOME, {{"work": "Work"}})
tables.edit_table(streams_file(data), income, mode.view(data))
mode.mode_switch()
"""


def _grid(data: Path, *, simple: bool = False) -> AppTest:
    at = AppTest.from_string(MODE_GRID.format(data=str(data)), default_timeout=60)
    if simple:
        at.query_params["mode"] = "simple"
    return at.run()


def _drawn(at: AppTest, key: str) -> Dataframe:
    """The grid whose key starts with `key`."""
    return next(g for g in at.dataframe if str(g.key).startswith(key))


def _shown(at: AppTest, key: str) -> list[str]:
    return list(_drawn(at, key).value.columns)


def _options(at: AppTest, key: str, column: str) -> set[str]:
    config = json.loads(_drawn(at, key).proto.columns)[column]["type_config"]
    return {option["value"] for option in config["options"]}


def test_simple_mode_hides_the_expert_columns_and_kinds_of_a_grid(data: Path) -> None:
    """Behind `All columns` in simple mode: the expert columns that no row holds; the `kind` of
    a stream offers the core kinds and those that a row holds. Advanced shows all."""
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: Gehalt, kind: salary, cat: gehalt, gross: 4000}\n")
    simple, advanced = _grid(data, simple=True), _grid(data)
    assert not {"tags", "update_every"} & set(_shown(simple, "assets-cash"))
    assert {"tags", "update_every"} <= set(_shown(advanced, "assets-cash"))
    assert simple.toggle(key="assets-cash-more")  # their way back
    kinds = _options(simple, "streams-income", "kind")
    assert kinds == {"expense", "salary", "pension", "other_income", "savings"}
    assert kinds < _options(advanced, "streams-income", "kind")
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: ALG, kind: alg1, cat: gehalt}\n")
    assert "alg1" in _options(_grid(data, simple=True), "streams-income", "kind")


def test_the_afa_of_a_property_shows_once_a_property_holds_it(data: Path) -> None:
    """Advanced shows the columns of the AfA; simple mode once a property holds them."""
    afa = {"bought", "building_share", "afa"}
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - {id: flat, kind: property, sqm: 50, per_sqm: 4000}\n")
    assert afa <= set(_shown(_grid(data), "assets-property"))
    assert not afa & set(_shown(_grid(data, simple=True), "assets-property"))
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - {id: let, kind: property, sqm: 40, per_sqm: 4000, bought: 2020-01-01,\n")
        fh.write("     building_share: 0.7, afa: 0.02}\n")
    assert afa <= set(_shown(_grid(data, simple=True), "assets-property"))


def test_a_grid_keeps_its_columns_while_it_holds_edits(data: Path) -> None:
    """A feature switched off elsewhere hides its column only once the grid holds no edits: a new
    column set would be a new editor, without them."""
    at = _grid(data)
    edit = {"edited_rows": {"0": {"value": 2000}}}
    edited(at, str(_drawn(at, "assets-cash").key), edit)
    (data / "app.yaml").write_text("features_off: [tracking]\n")
    edited(at, str(_drawn(at, "assets-cash").key), edit)
    assert "update_every" in _shown(at, "assets-cash")
    at.button(key="assets-cash-save").click()
    edited(at, str(_drawn(at, "assets-cash").key), edit)  # a browser sends them with the press
    assert not at.exception
    assert yaml.safe_load((data / "assets.yaml").read_text())["assets"][0]["value"] == 2000
    assert "update_every" not in _shown(at, "assets-cash")  # the new grid after the save
    (data / "app.yaml").unlink()
    assert "update_every" in _shown(at.run(), "assets-cash")  # without edits at once


def test_the_mode_switch_keeps_the_edits_of_a_grid(data: Path) -> None:
    """Simple mode hides columns, so Streamlit draws a new editor: the switch carries the edits,
    which the new grid shows and the guard lists."""
    at = _grid(data)
    edit, old = {"edited_rows": {"0": {"value": 2000}}}, _drawn(at, "assets-cash")
    edited(at, str(old.key), edit)
    at.sidebar.segmented_control(key=mode.MODE).set_value("simple")
    edited(at, str(old.key), edit)  # the old grid sends its edits with the switch
    assert not at.exception
    new = _drawn(at, "assets-cash")
    assert new.proto.id != old.proto.id
    assert "tags" not in new.value.columns
    assert new.value["value"].tolist() == [2000]
    at.run()
    assert "To save:  \n**giro value** 1.000,00 € → 2.000,00 €" in [c.value for c in at.caption]


def test_a_hidden_option_stays_for_a_row_of_the_file_by_key_and_an_edit_by_name() -> None:
    """A column whose name differs from its key: the rows of the file hold the key, the edits of
    the grid the name."""
    column = gridcolumns.Column("Type", "string", ("expense", "savings"), None, True, "", "kind")
    hidden = frozenset({mode.Item(mode.Sort.STREAM, ("savings",))})

    def options(rows: list[dict[str, str]], edit: dict[str, str]) -> tuple[str, ...]:
        return tables.limited([column], "streams", rows, [edit], hidden)[0].options

    assert options([{"name": "a", "kind": "expense"}], {}) == ("expense",)
    assert options([{"name": "a", "kind": "savings"}], {}) == ("expense", "savings")
    assert options([{"name": "a", "kind": "expense"}], {"Type": "savings"}) == (
        "expense",
        "savings",
    )
    assert options([{"name": "a", "kind": "expense"}], {"kind": "savings"}) == ("expense",)


def test_a_save_shows_a_refusal_and_lets_a_bug_raise() -> None:
    """A row gone since, a lock or the model show as `Not saved`; a KeyError of the code does
    not."""
    assert issubclass(RefusedError, save.REFUSED)
    assert issubclass(PermissionError, save.REFUSED)
    assert not issubclass(KeyError, save.REFUSED)
    assert not issubclass(IndexError, save.REFUSED)
