"""The Flows page: its tabs, its years and the Sankey of a budget."""

from __future__ import annotations

import itertools
import json
from datetime import date
from pathlib import Path

import pytest
from builders import cash, phases, plan, zero_run
from german import ACTIVATE
from streamlit.testing.v1 import AppTest

from dagobert import budget
from dagobert.budget import Budget
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.result import LOAN_PRINCIPAL, RunResult
from dagobert.ui import flows


def _run() -> RunResult:
    """A year of salary in `work`, then a year in `alt`."""
    scenario = Scenario(
        name="s", phases=phases((date(2026, 1, 1), "work"), (date(2027, 1, 1), "alt"))
    )
    salary = Stream(name="salary", kind=StreamKind.SALARY, gross=5000, phases=["work"], index=None)
    return zero_run(plan([salary], [cash(50_000)], scenario), 24)


def test_layout_of_an_empty_budget_has_no_nodes() -> None:
    layout = flows.Layout.of(flows.flow_links(budget.Budget()))
    assert layout == flows.Layout(0.0, {}, {}, [])


def test_compare_gives_the_change_per_stretch() -> None:
    r = _run()
    same = flows.compare(r, r, oneoffs=False)
    assert all(delta == 0 for cells in same.values() for _, delta in cells.values())
    assert list(same["Work"]) == [
        "income",
        "taxes",
        "spending",
        "surplus",
        "into savings plans",
        "into assets",
        "non-cash income",
        "wealth built",
    ]
    income, _ = same["Work"]["income"]
    assert income > 0
    # signed like the sheet of the Cashflows page: each sum is the sum of its lines
    for cells in same.values():
        v = {line: value for line, (value, _) in cells.items()}
        assert v["taxes"] <= 0 and v["spending"] <= 0
        assert v["surplus"] == pytest.approx(v["income"] + v["taxes"] + v["spending"])
        assert v["wealth built"] == pytest.approx(
            v["surplus"] + v["into assets"] + v["non-cash income"]
        )
    assert all(
        delta is None
        for cells in flows.compare(r, None, oneoffs=False).values()
        for _, delta in cells.values()
    )


def test_links_conserve_the_money_and_fold_small_items() -> None:
    b = Budget(
        {"Gehalt": 5000.0},
        {"income tax": 1000.0},
        {"base": {"Essen": 600.0, "a": 10.0, "b": 20.0}, LOAN_PRINCIPAL: {"haus": 500.0}},
    )
    links = flows.flow_links(b, floor=50, scale=12)
    assert sum(v for s, _, v in links.links if s[0] == 0) == 12 * 5000
    leaves = {t[1]: v for _, t, v in links.links if t[0] == flows.LEAF}
    assert leaves == {
        "income tax": 12_000,
        "Essen": 7200,
        "other (2)": 360,
        "haus": 6000,
        "saved": 12 * 2870,
    }
    assert links.nodes[(3, LOAN_PRINCIPAL, "")] == "loans"
    assert [s for s, t, _ in links.links if t[1] == "saved"] == [(3, "surplus", "")]
    # the outflow bars of a phone show the same items
    assert {s.path: s.value for s in flows.outflow_slices(b, floor=50, scale=12)} == {
        (t[2], t[1]): v for _, t, v in links.links if t[0] == flows.LEAF and t[1] != "saved"
    }


def test_figure_places_a_deficit_without_income() -> None:
    b = Budget(spending={"base": {"Essen": 600.0}, "medien": {"Essen": 5.0}})
    links = flows.flow_links(b)
    layout = flows.Layout.of(links)
    assert {node[:2] for node in layout.spans} == {
        (1, "from savings"),
        (2, "budget"),
        (3, "base"),
        (3, "medien"),
        (flows.LEAF, "Essen"),
    }
    assert len(layout.spans) == 6  # `Essen` is one node per group
    tops = [layout.spans[node][0] for node in links.nodes if node[0] == flows.LEAF]
    assert tops == sorted(tops)  # items keep the order of their groups
    texts = [
        t for trace in flows.flow_figure(links, "alt").to_dict()["data"] for t in [trace["text"]]
    ]
    assert "from savings → budget: 605 €" in texts


def test_slivers_keep_room_for_their_labels() -> None:
    # a severance scales the small items down to slivers: each label still gets a line
    b = Budget({"Abfindung": 100_000.0}, spending={"base": {f"item {i}": 60.0 for i in range(9)}})
    layout = flows.Layout.of(flows.flow_links(b))
    middles = sorted(
        (top + bottom) / 2
        for (level, *_), (top, bottom) in layout.spans.items()
        if level == flows.LEAF
    )
    assert min(b - a for a, b in itertools.pairwise(middles)) >= flows.PITCH


def test_bands_leave_a_node_in_the_order_of_their_targets() -> None:
    # a thin tax band beside a wide budget band: plotly's own Sankey trace crossed them
    b = Budget({"Rente": 2500.0}, {"income tax": 100.0}, {"base": {"Essen": 7000.0}})
    layout = flows.Layout.of(flows.flow_links(b))
    income = (1, "income", "")
    bands = {r.target[1]: r for r in layout.ribbons if r.source == income}
    assert bands["taxes & SV"].at_source == layout.spans[income][0]
    assert bands["budget"].at_source == pytest.approx(
        bands["taxes & SV"].at_source + bands["taxes & SV"].width
    )
    assert layout.spans[bands["taxes & SV"].target][0] < layout.spans[bands["budget"].target][0]
    for ribbon in layout.ribbons:  # every band lies inside its two nodes
        for at, node in ((ribbon.at_source, ribbon.source), (ribbon.at_target, ribbon.target)):
            top, bottom = layout.spans[node]
            assert top - 1e-6 <= at and at + ribbon.width <= bottom + 1e-6


def test_a_loss_does_not_fold_away_a_small_source() -> None:
    """A negative source stays out of the `other` item, so a small positive one still shows."""
    links = flows.flow_links(budget.Budget(sources={"interest": 30.0, "loss": -200.0}), floor=50.0)
    assert [(source[1], value) for source, _target, value in links.links if source[0] == 0] == [
        ("interest", 30.0)
    ]


FLOWS = """
from pathlib import Path
from dagobert.ui import flows
flows.page(Path({data!r}))
"""


def test_the_diagram_speaks_german(data: Path) -> None:
    """The title and the nodes of the diagram in the words of the session: the phase label and
    the categories as written, the words of the ledger and of the budget translated."""
    (data / "cashflows.yaml").write_text(
        "streams:\n"
        "  - {name: Gehalt, cat: gehalt, kind: salary, gross: 5000, phases: [work]}\n"
        "  - {name: Miete, cat: wohnen, amount: -500}\n"
    )
    at = AppTest.from_string(ACTIVATE + FLOWS.format(data=str(data)), default_timeout=30)
    at.query_params["lang"] = "de"
    at.run()
    assert not at.exception
    specs = (json.loads(c.proto.spec) for c in at.get("plotly_chart"))
    (diagram,) = (s for s in specs if s["layout"].get("title"))  # beside the outflow bars
    nodes = {
        text.split("  ")[0]
        for trace in diagram["data"]
        if trace.get("mode") == "text"
        for text in trace["text"]
    }
    assert diagram["layout"]["title"]["text"] == "Work, pro Monat"
    assert {
        "Gehalt",
        "Einnahmen",
        "Steuern & SV",
        "Einkommensteuer",
        "Budget",
        "Überschuss",
    } <= nodes
    assert {"wohnen", "Miete"} <= nodes
    assert not nodes & {"income", "taxes & SV", "income tax", "surplus", "saved"}


@pytest.mark.parametrize("phone", [False, True])
def test_flows_draws_the_tabs_and_steps_through_the_years(data: Path, phone: bool) -> None:
    (data / "scenarios" / "base.yaml").write_text(
        "name: base\n"
        "phases: [{from: 2026-01-01, phase: work}, {from: 2027-07-01, phase: retired}]\n"
    )
    at = AppTest.from_string(FLOWS.format(data=str(data)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    assert not at.exception
    titles = [
        json.loads(c.proto.spec)["layout"].get("title", {}).get("text")
        for c in at.get("plotly_chart")
    ]
    # a phone draws the open tab only, with its outflow bars
    assert [t for t in titles if t] == ["Work, per month"] + (
        [] if phone else ["Retired, per month"]
    )
    assert [p.options for p in at.pills] == ([["wohnen"]] if phone else [])
    back, ahead = (
        next(b for b in at.button if b.help == h) for h in ("Previous year", "Next year")
    )
    assert back.disabled and not ahead.disabled
    ahead.click().run()
    assert at.select_slider[0].value == 2026
    # on a narrow screen the diagram anyway, in place of the outflow bars
    next(t for t in at.toggle if t.label == "Show the diagram anyway").set_value(True).run()
    assert not at.exception
    assert not at.pills
    assert any("swipe it sideways" in c.value for c in at.caption)
