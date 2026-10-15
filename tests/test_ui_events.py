"""The event grids of a scenario file: the actions of a sale, an edit of a lifted stream, the events
that a file inherits, and the tab as a desktop and as a phone with its saves."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from builders import PHASE_LABELS
from german import edited
from streamlit.testing.v1 import AppTest

from dagobert import references, revisions
from dagobert.loader import lineage as chain_of
from dagobert.loader import read_yaml
from dagobert.model.events import SellEvent
from dagobert.store import Edit, RowEdits, RowFile
from dagobert.ui import events, fields, guard, lineage, mode
from dagobert.ui.gridstate import edits_from_state

STREAMS = """\
streams:
  - name: Salary
    kind: salary
    gross: 5000
  - name: Bonus
    kind: salary
    of: Salary
    share: 0.1
    every: 12
"""

ASSETS = """\
assets:
  - id: giro
    kind: cash
    value: 1000
  - id: flat
    kind: property
    sqm: 50
    per_sqm: 4000
  - id: loan-a
    kind: loan
    balance: -100000
    rate: 0.02
    annuity: 600
  - id: depot
    kind: equity
    value: 5000
    cost_basis: 4000
  - id: gold
    kind: gold
    value: 0
  - id: policy-a
    kind: bav
    value: 0
    phases: []
    matures: 2040-01-01
    payout: annuity
    annuity_per_10k: 30
    basisrente: true
"""
BASE = """\
name: base
phases:
  - {from: 2026-01-01, phase: work}
events:
  - at: 2030-01-01
    type: lump_sum
    amount: -20000
    id: car
  # the flat goes, and repays its loan
  - at: 2032-01-01
    type: sell
    asset: flat
    then:
      - {repay: loan-a}
      - {invest: portfolio}
    id: flat-sale
"""
CHILD = """\
name: child
extends: base
events:
  - at: 2031-01-01
    type: lump_sum
    amount: 5000
overrides:
  shift: {car: 12}
"""


@pytest.fixture
def plans(data: Path) -> Path:
    (data / "assets.yaml").write_text(ASSETS)
    with (data / "assumptions.yaml").open("a") as fh:  # below `returns`
        fh.write("  gold: {mean: 0.02}\n  bav: {mean: 0.02}\n")
    (data / "scenarios" / "base.yaml").write_text(BASE)
    (data / "scenarios" / "child.yaml").write_text(CHILD)
    return data


REPAY_A, INVEST = {"repay": "loan-a"}, {"invest": "portfolio"}


@pytest.mark.parametrize(
    ("then", "repays", "invest", "after"),
    [
        # a new repayment goes before `invest`, and without an amount it repays all
        (
            [REPAY_A, INVEST],
            RowEdits(added=[{"repay": "loan-b", "amount": None}]),
            True,
            [REPAY_A, {"repay": "loan-b"}, INVEST],
        ),
        ([REPAY_A, INVEST], RowEdits(), False, [REPAY_A]),
        ([REPAY_A], RowEdits(deleted=[0]), True, [INVEST]),
        (
            [REPAY_A, INVEST],
            RowEdits(edited={0: {"amount": 5000}}),
            True,
            [
                {"repay": "loan-a", "amount": 5000},
                INVEST,
            ],
        ),
    ],
)
def test_the_actions_of_a_sale_repay_first_and_invest_last(
    then: list[dict[str, Any]], repays: RowEdits, invest: bool, after: list[dict[str, Any]]
) -> None:
    result = events.actions(then, repays, invest).result(then)
    assert result == after
    sale = SellEvent.model_validate(
        {"at": date(2030, 1, 1), "type": "sell", "asset": "flat"} | {"then": result}
    )
    assert all(getattr(a, "amount", "all") in ("all", 5000) for a in sale.then)


def test_an_untouched_sale_keeps_its_actions() -> None:
    assert not events.actions([REPAY_A, INVEST], RowEdits(), True)


ADDED = """\
name: base
events:
  - at: 2040-06-01
    type: add_stream
    stream:
      name: New salary
      kind: salary
      # before the raise
      gross: 6200
      index: salary
    id: new-job
"""


@pytest.mark.parametrize(
    ("cells", "stream"),
    [
        ({"gross": 7000}, {"gross": 7000}),
        ({"factor retired": 0}, {"phases": ["work", "unemployed", "alt"]}),
        ({"factor alt": 0.5}, {"factor": {"alt": 0.5}}),
    ],
)
def test_an_edit_of_a_stream_cell_merges_into_the_stream(
    data: Path, cells: dict[str, Any], stream: dict[str, Any]
) -> None:
    path = data / "scenarios" / "base.yaml"
    path.write_text(ADDED)
    row = read_yaml(path)["events"][0]
    cols = events.table("base", "add_stream", PHASE_LABELS).columns(everything=True)
    edits = edits_from_state({"edited_rows": {"0": cells}}, cols, [(0, row)], {})
    text = Edit("scenarios/base.yaml", rows={("events",): edits}).text(data)
    assert text is not None
    path.write_text(text)
    after = read_yaml(path)["events"][0]
    assert after["stream"] == row["stream"] | stream
    assert "      # before the raise\n" in text  # the comment inside the stream stays


def test_an_inheritance_shows_its_relatives_as_a_list() -> None:
    """The grid heads its columns by the keys of the file (`from`, not the field `givers`), and
    one relative of the file shows as a list of one, not letter by letter."""
    cols = events.table("base", "inheritance", PHASE_LABELS).columns(everything=True)
    assert [c.name for c in cols] == [
        *("at", "from", "cash", "equity value", "equity cost_basis", "id", "note")
    ]
    row = {"type": "inheritance", "from": "mother", "cash": 1000}
    assert [c.shown(row) for c in cols][1:3] == [["mother"], 1000]


def test_a_saved_purchase_keeps_its_ids_and_saves_its_loan_negative() -> None:
    """Sales and repayments name the property and the loan by their ids. A phone keypad may lack
    the minus: the loan is saved negative, also in a new row, as in the grids of the Assets
    page, and shows as the amount borrowed, without a minus."""
    table = events.table("base", "buy_property", PHASE_LABELS)
    cols = table.columns(everything=True)
    row = {"type": "buy_property", "at": date(2028, 4, 1), "price": 330_000, "land": "NI"} | {
        "property": {"id": "home", "name": "Flat"},
        "loan": {"id": "home-loan", "balance": -300_000},
    }
    typed = {"property id": "flat", "property name": "Own flat", "loan id": "x", "loan balance": 1}
    [(cells, notes)] = [
        table.held(row, table.signed(row, cells))
        for cells in edits_from_state(
            {"edited_rows": {"0": typed}}, cols, [(0, row)], {}
        ).edited.values()
    ]
    assert RowEdits(edited={0: cells}).result([row])[0] == row | {
        "property": {"id": "home", "name": "Own flat"},
        "loan": {"id": "home-loan", "balance": -1},
    }
    assert [n.split("**")[-1] for n in notes] == [
        " keeps its property id home, flat is not saved",
        " keeps its loan id home-loan, x is not saved",
    ]
    added = edits_from_state({"added_rows": [{"loan balance": 5}]}, cols, [], table.fixed)
    assert table.signed({}, added.added[0])["loan"].changes == {"balance": -5}
    loan = {c.name: c for c in cols}["loan balance"]
    assert (loan.shown(row), loan.bounds) == (300_000, (0, None))


@pytest.mark.parametrize(
    ("typed", "ids"),
    [
        ({}, ("flat-2", "flat-2-loan")),  # `flat` is taken
        ({"loan name": "Bank"}, ("flat-2", "bank")),
        ({"loan balance": None}, ("flat-2", None)),  # no loan
    ],
)
def test_a_purchase_added_in_the_grid_makes_its_ids(
    typed: dict[str, object], ids: tuple[str, str | None]
) -> None:
    """As its form: the ids stay out of a new row of the grid, as they are locked, and the guard
    lists them with the numbers of the row."""
    table = events.table("base", "buy_property", PHASE_LABELS, taken=["flat"])
    cols = table.columns(everything=True)
    cells = {"at": "2029-03-01", "property name": "Flat", "price": 300_000, "land": "BE"}
    state = {"added_rows": [cells | {"loan balance": 250_000} | typed]}
    [new] = edits_from_state(state, cols, [], table.fixed).added
    edits = RowEdits(added=[table.filled(new)])
    [row] = edits.result([])
    assert (row["property"]["id"], row.get("loan", {}).get("id")) == ids
    listed = guard.changes([], edits, units=table.units(), names=table.names(), made=table.made)
    assert {c.key: c.new for c in listed if c.key.endswith(" id")} == {
        f"2029-03 Flat {key} id": made
        for key, made in zip(("property", "loan"), ids, strict=True)
        if made
    }


def test_inherited_events_carry_their_file_and_the_file_that_drops_them(tmp_path: Path) -> None:
    files: dict[str, dict[str, Any]] = {
        "a": {"name": "a", "events": [_lump("x"), _lump("y"), _lump(None)]},
        "b": {"name": "b", "extends": "a", "drop": ["x"], "events": [_lump("z")]},
        "c": {"name": "c", "extends": "b", "drop": ["y"]},
    }
    chained = [(tmp_path / f"{stem}.yaml", raw) for stem, raw in files.items()]
    found = [(i.file, i.row.get("id"), i.dropped) for i in lineage.inherited(chained)]
    assert found == [("a", "x", "b"), ("a", "y", "c"), ("a", None, None), ("b", "z", None)]
    # a toggle takes back what the file drops itself, not what a file between drops
    assert [i.row.get("id") for i in lineage.reach(chained)] == ["y", None, "z"]


def _lump(item: str | None) -> dict[str, Any]:
    return {"at": date(2030, 1, 1), "type": "lump_sum", "amount": 1} | (
        {"id": item} if item else {}
    )


@pytest.mark.parametrize(
    ("row", "said"),
    [
        ({"type": "sell", "at": date(2032, 1, 1), "asset": "flat"}, "2032-01 flat"),
        (
            {"type": "sell", "asset": "flat", "when": {"age": 78, "liquid_below": 30000}},
            "age 78 or liquid below 30.000 € flat",
        ),
        ({"type": "lump_sum", "at": date(2030, 1, 1), "amount": -20000}, "2030-01 -20.000 €"),
        ({"type": "end_streams", "names": ["Salary"], "tags": ["flat"]}, "never Salary, flat"),
        ({"type": "add_stream", "stream": {"name": "Rent"}}, "never Rent"),
        (
            {"type": "inheritance", "from": "mother", "cash": 30000, "equity": {"value": 60000}},
            "at the death of mother mother: 90.000 €",
        ),
        (
            {"type": "inheritance", "from": ["mother", "father"], "cash": 1000},
            "at the later death of mother and father mother, father: 1.000 €",
        ),
        ({"type": "gift", "at": date(2028, 2, 1), "from": "mother"}, "2028-02 mother"),
    ],
)
def test_an_event_reads_in_words(row: dict[str, Any], said: str) -> None:
    assert f"{lineage.when(row)} {lineage.describe(row)}" == said


@pytest.mark.parametrize(
    ("row", "label"),
    [
        ({"type": "lump_sum", "at": date(2030, 1, 1), "amount": 1}, "2030-01 lump_sum"),
        ({"type": "sell", "asset": "flat", "when": {"age": 78}}, "flat"),
        ({"type": "repay", "at": date(2030, 1, 1), "loan": "loan-a"}, "2030-01 loan-a"),
        (
            {"type": "repay", "at": date(2030, 1, 1), "loan": "loan-a", "id": "early"},
            "2030-01 early",
        ),
    ],
)
def test_the_guard_names_an_event_by_what_it_names(row: dict[str, Any], label: str) -> None:
    assert guard.label(row) == label


def test_a_derived_stream_is_no_base_of_a_new_one(data: Path) -> None:
    (data / "cashflows.yaml").write_text(STREAMS)
    rows = RowFile(data, "cashflows.yaml", ("streams",)).rows()
    spec = events.table("base", "add_stream", PHASE_LABELS, events.bonus_streams(rows))
    cols = spec.referenced(spec.columns(everything=True), references.of(data), "base", [])
    assert next(c for c in cols if c.key == "of").options == ("Salary",)  # not the bonus


HARNESS = """
from pathlib import Path
from dagobert.ui import events
events.tab(Path({path!r}))
"""


def _tab(data: Path, stem: str, *, phone: bool = False, simple: bool = False) -> AppTest:
    path = data / "scenarios" / f"{stem}.yaml"
    at = AppTest.from_string(HARNESS.format(path=str(path)), default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    if simple:
        at.query_params["mode"] = "simple"
    return at.run()


def _types(at: AppTest) -> set[str]:
    """The event types of the strip, by the start of their labels."""
    return {k for k in events.TYPES for t in at.tabs if t.label.startswith(lineage.TITLES[k])}


def test_simple_mode_shows_the_core_types_and_those_of_the_inputs(plans: Path) -> None:
    """A sale shows with a property, gold or crypto to sell; the others go into the note below the
    strip. A type whose grid holds a new row stays after the switch."""
    at = _tab(plans, "child", simple=True)
    assert not at.exception
    assert _types(at) == {"sell", "lump_sum", "end_streams", "set_stream", "add_stream"}
    [note] = [c.value for c in at.caption if c.value.startswith("Hidden in simple mode: ")]
    assert "write off shares" in note
    advanced = _tab(plans, "child")
    assert _types(advanced) == set(events.TYPES)
    edit = {"added_rows": [{"at": "2027-01", "asset": "depot"}]}
    edited(advanced, "events-child-write_off-0", edit)
    advanced.session_state[mode.MODE] = "simple"
    edited(advanced, "events-child-write_off-0", edit)
    assert "write_off" in _types(advanced)


def _pinned(at: AppTest) -> set[str]:
    return {
        name
        for grid in at.dataframe
        for name, column in json.loads(grid.proto.columns).items()
        if column.get("pinned")
    }


@pytest.mark.parametrize("phone", [False, True])
def test_the_tab_renders_with_a_grid_per_type(plans: Path, phone: bool) -> None:
    at = _tab(plans, "child", phone=phone)
    assert not at.exception
    labels = [t.label for t in at.tabs]
    # the types in words, with the events of the file and those that it inherits
    assert {"One-off payment (1, 1 inherited)", "Sell an asset (1 inherited)"} <= set(labels)
    assert "Repay a loan" in labels
    assert len(at.dataframe) == len(events.TYPES) + 1  # the grids and the inherited events
    assert _pinned(at) == ({"at", "month"} if phone else set())  # the month names a row
    assert any("-add-" in str(w.key) for w in at.text_input)  # the form `Add an event`


def test_a_toggle_leaves_out_an_inherited_event(plans: Path) -> None:
    at = _tab(plans, "child")
    toggle = next(t for t in at.toggle if t.label == "Leave out flat-sale (1 event)")
    toggle.set_value(True).run()
    assert any("**leave out flat-sale (1 event)** no → yes" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "Save what to leave out").click().run()
    assert not at.exception
    child = plans / "scenarios" / "child.yaml"
    assert read_yaml(child)["drop"] == ["flat-sale"]
    kept = [e.id for _, own in chain_of(child) for e in own.events]
    assert "flat-sale" not in kept
    assert revisions.entries(plans)[-1].source == "app"


def test_the_repayments_of_a_sale_save_by_themselves(plans: Path) -> None:
    at = _tab(plans, "base")
    assert not at.exception
    assert "repay" in _pinned(_tab(plans, "base", phone=True))
    next(t for t in at.toggle if t.label == "Invest the rest").set_value(False).run()
    sell = f"{lineage.TITLES['sell']} (1)"
    assert f"{sell}{events.EDITED}" in [t.label for t in at.tabs]  # holds edits
    next(b for b in at.button if b.label == "Save repayments").click().run()
    assert not at.exception
    assert sell in [t.label for t in at.tabs]
    path = plans / "scenarios" / "base.yaml"
    assert read_yaml(path)["events"][1]["then"] == [REPAY_A]
    assert "  # the flat goes, and repays its loan\n" in path.read_text()


def test_an_id_that_another_file_uses_is_named(plans: Path) -> None:
    at = _tab(plans, "base")
    assert any("**car** by child (shift)" in c.value for c in at.caption)


def test_the_form_names_what_it_lacks_after_the_first_edit(plans: Path) -> None:
    """An empty form says nothing yet, then names its button: `Add`, not `Save`."""
    at = _tab(plans, "child")
    assert not at.warning  # also no problem of the model with the empty row of each type
    when = next(w for w in at.text_input if str(w.key).endswith("events-child-sell-add-0-at"))
    when.input("2033-04").run()
    assert any(w.value.startswith("Add stays off until these read") for w in at.warning)


# per type what the form `Add an event` takes: text by field, then names to pick
TYPED: dict[str, tuple[dict[str, str], dict[str, str]]] = {
    "sell": ({}, {"asset": "flat"}),
    "repay": ({}, {"loan": "loan-a"}),
    "severance": ({"gross": "50.000"}, {}),
    "fund_policy": ({"amount": "1.000"}, {"policy": "policy-a"}),
    "lump_sum": ({"amount": "-1.500,50"}, {}),
    "write_off": ({}, {"asset": "depot"}),
    "end_streams": ({}, {"names": "Miete"}),
    "set_stream": ({"amount": "-600"}, {"name": "Miete"}),
    "add_stream": ({"stream.name": "Neu", "stream.amount": "-50"}, {}),
    "buy": ({"amount": "1.000"}, {"asset": "gold"}),
    "buy_property": ({"property.id": "home", "price": "300.000"}, {"land": "NI"}),
}


@pytest.mark.parametrize("kind", list(TYPED))
def test_the_form_adds_an_event_of_each_type(plans: Path, kind: str) -> None:
    at = _tab(plans, "child", phone=True)
    form = f"events-child-{kind}-add"
    texts, picks = TYPED[kind]

    def widget(elements: Any, path: str) -> Any:
        return next(w for w in elements if str(w.key).endswith(f"{form}-0-{path}"))

    widget(at.text_input, "at").input("2033-04")
    for path, text in texts.items():
        widget(at.text_input, path).input(text)
    for path, name in picks.items():
        found = widget([*at.selectbox, *at.multiselect], path)
        found.select(name)
    at.run()
    next(b for b in at.button if b.key == f"{form}-save").click().run()
    assert not at.exception
    assert not at.error, [e.value for e in at.error]
    added = read_yaml(plans / "scenarios" / "child.yaml")["events"][-1]
    assert (added["type"], added["at"]) == (kind, date(2033, 4, 1))
    assert revisions.entries(plans)[-1].source == "app"


def test_a_new_stream_asks_only_for_what_the_model_requires(plans: Path) -> None:
    at = _tab(plans, "child", phone=True)
    form = "events-child-add_stream-add-0"
    next(w for w in at.text_input if str(w.key).endswith(f"{form}-at")).input("2033-04").run()
    shown = " ".join(w.value for w in at.warning)
    assert "**Name** required" in shown
    assert not any(field in shown for field in ("Every", "Part", "Taxable"))  # they have defaults
    part = next(w for w in at.text_input if str(w.key).endswith(f"{form}-stream.part"))
    assert part.placeholder == "100 (default)"


def test_a_conditional_sale_takes_its_rule_in_the_form(plans: Path) -> None:
    at = _tab(plans, "child", phone=True)
    form = "events-child-sell-add"
    next(s for s in at.selectbox if str(s.key).endswith(f"{form}-0-asset")).select("flat")
    next(t for t in at.toggle if str(t.key).endswith(f"{form}-0-when")).set_value(True).run()
    next(w for w in at.text_input if str(w.key).endswith(f"{form}-0-when.age")).input("78").run()
    next(b for b in at.button if b.key == f"{form}-save").click().run()
    assert not at.exception
    added = read_yaml(plans / "scenarios" / "child.yaml")["events"][-1]
    assert added == {"type": "sell", "asset": "flat", "when": {"age": 78}}


def test_a_purchase_makes_its_ids_of_its_names_and_takes_its_loan_without_a_minus(
    plans: Path,
) -> None:
    """The form names the fields as labelled and a check of the model in plain words; a new row
    lists its values without `empty →`."""
    at = _tab(plans, "child", phone=True)
    form = "events-child-buy_property-add"

    def typed(path: str, text: str) -> None:
        next(w for w in at.text_input if str(w.key).endswith(f"{form}-0-{path}")).input(text)

    typed("at", "2033-04")
    typed("property.name", "Flat")  # the id `flat` names an asset already
    typed("price", "300.000")
    typed("transfer_tax", "0")
    next(s for s in at.selectbox if str(s.key).endswith(f"{form}-0-land")).select("NI").run()
    plain = next(iter(events.PLAIN.values()))
    assert [w.value for w in at.warning] == [f"Add stays off:  \n{plain}"]  # both
    next(s for s in at.selectbox if str(s.key).endswith(f"{form}-0-land")).set_value(None)
    next(t for t in at.toggle if str(t.key).endswith(f"{form}-0-loan")).set_value(True).run()
    for path, text in (("loan.balance", "250.000"), ("loan.rate", "3"), ("loan.annuity", "1.200")):
        typed(path, text)
    at.run()
    shown = " ".join(c.value for c in at.caption)
    assert "**Month** 2033-04" in shown
    assert "**Property id** flat-2" in shown
    assert "**Loan amount** -250.000,00 €" in shown
    next(b for b in at.button if b.key == f"{form}-save").click().run()
    assert not at.error, [e.value for e in at.error]
    added = read_yaml(plans / "scenarios" / "child.yaml")["events"][-1]
    assert (added["property"]["id"], added["loan"]["id"]) == ("flat-2", "flat-2-loan")
    assert added["loan"]["balance"] == -250_000


def test_the_id_of_a_nested_model_follows_its_name() -> None:
    order = [f.path for f in events.ordered(fields.of(events.TYPES["buy_property"]))]
    assert order.index(("property", "id")) > order.index(("property", "tags"))
    assert order.index(("loan", "id")) > order.index(("loan", "prepayment_penalty"))
    assert (order[0], order[-2:]) == (("at",), [("id",), ("note",)])
