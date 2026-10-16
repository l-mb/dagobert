"""Money flow of one phase as a Sankey diagram: income sources, taxes, spending, saving."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import revisions
from dagobert.budget import (
    INCOME,
    SAVED,
    SURPLUS,
    TAXES,
    WEALTH_BUILT,
    Budget,
    Stretch,
    from_ledger,
    ledger,
    said,
    stretches,
)
from dagobert.i18n import N_, _, ngettext
from dagobert.loader import load_plan
from dagobert.money import EUR_COLUMN, format_eur
from dagobert.report import charts
from dagobert.report.tracker import Slice
from dagobert.result import RunResult
from dagobert.scenariofiles import concrete_scenarios, first_scenario, scenario_file
from dagobert.ui import (
    FLOWS_SCENARIO,
    chart,
    day_said,
    fixed,
    fold,
    is_mobile,
    page_link,
    per_control,
    runs,
    scenario_note,
    scenario_titles,
    since,
    step_button,
)
from dagobert.ui.bars import NONCASH_NOTE, ROLES, outflow_bars, role
from dagobert.ui.cashflows import listed, terms

# The nodes of the diagram beside the names of the budget (`budget.said`)
BUDGET, FROM_SAVINGS, SAVED_NODE = N_("budget"), N_("from savings"), N_("saved")
NODES = frozenset({BUDGET, FROM_SAVINGS, SAVED_NODE})
NET = N_("net")  # a tile: the income after the taxes
LEAF = 4  # the level of the items: the last column
PAD = 14  # pixels between the nodes of a column
Node = tuple[int, str, str]  # level, label, group: two groups can hold the same item name
NODE_WIDTH = 0.012  # as a share of the plot width, like `LEVEL_X`
LEVEL_X = (0.0, 0.24, 0.43, 0.62, 1 - NODE_WIDTH)  # the last gap holds the labels of two columns
LABEL_GAP = 0.004
LABEL_SIZE = 14  # pixels, like the text of the tracker figures
PITCH = LABEL_SIZE + 4  # pixels from the top of a node to the next at least: room for its label
CHART = "flows-sankey-"  # the key prefix of the containers of the charts (`ui.PAGE_STYLE`)
# Plotly writes the text color into each label. The theme of the app gives a light gray there:
# the labels take the color of the page text instead, dark on the light theme, light on the dark.
LABEL_INK = (
    f'<style>[class*="st-key-{CHART}"] g.textpoint text {{fill: currentColor !important}}</style>'
)
CURVE_STEPS = 24


@dataclass
class _Links:
    scale: float
    nodes: dict[Node, str] = field(default_factory=dict)  # node to role
    links: list[tuple[Node, Node, float]] = field(default_factory=list)

    def add(self, source: Node, target: Node, value: float, roles: tuple[str, str]) -> None:
        if value > 0:
            self.nodes.setdefault(source, roles[0])
            self.nodes.setdefault(target, roles[1])
            self.links.append((source, target, value * self.scale))


def _folded(items: dict[str, float], floor: float) -> dict[str, float]:
    """Largest first. Items under `floor` fold into one `other` item, in the words of the
    session, unless there is only one."""
    small = {name: value for name, value in items.items() if 0 <= value < floor}
    kept = items if len(small) < 2 else {n: v for n, v in items.items() if n not in small}
    ordered = dict(sorted(kept.items(), key=lambda item: -item[1]))
    other = _("other ({n})").format(n=len(small))
    return ordered | ({other: sum(small.values())} if len(small) > 1 else {})


def _said(name: str) -> str:
    """A node of the diagram in the words of the session."""
    return _(name) if name in NODES else said(name)


def flow_links(b: Budget, *, floor: float = 0.0, scale: float = 1.0) -> _Links:
    """Sources, `income`, then taxes beside the `budget`, then the spending groups, then the
    items of all of them in the order of their groups. A deficit enters the budget as `from
    savings` in the column of `income`, so its band does not run behind that node. The nodes keep
    the English of the budget (`flow_figure` says them)."""
    gross, spend, taxes = (1, INCOME, ""), (2, BUDGET, ""), (2, TAXES, "")
    out = _Links(scale)
    for name, value in _folded(b.sources, floor).items():
        out.add((0, name, ""), gross, value, ("income", "hub"))
    out.add(gross, taxes, sum(b.taxes.values()), ("hub", "taxes"))
    out.add(gross, spend, b.net, ("hub", "hub"))
    out.add((1, FROM_SAVINGS, ""), spend, -b.surplus, ("savings", "hub"))
    for name, value in _folded(b.taxes, floor).items():
        out.add(taxes, (LEAF, name, taxes[1]), value, ("taxes", "taxes"))
    groups = sorted(b.spending.items(), key=lambda group: -sum(group[1].values()))
    for group, items in groups:
        kind = role(group)
        out.add(spend, (3, group, ""), sum(items.values()), ("hub", kind))
        for name, value in _folded(items, floor).items():
            out.add((3, group, ""), (LEAF, name, group), value, (kind, kind))
    # through a node of its own in the column of the groups: a band from the budget straight
    # to the last column would cross every group
    out.add(spend, (3, SURPLUS, ""), b.surplus, ("hub", "savings"))
    out.add((3, SURPLUS, ""), (LEAF, SAVED_NODE, SURPLUS), b.surplus, ("savings", "savings"))
    return out


def outflow_slices(b: Budget, *, floor: float = 0.0, scale: float = 1.0) -> list[Slice]:
    """The outflows of `b` by group and item, the items folded like those of `flow_links`."""
    return [
        Slice((group, name), value * scale)
        for group, items in b.outflows.items()
        for name, value in _folded(items, floor).items()
    ]


def _rgba(color: str, alpha: float) -> str:
    return f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, {alpha})"


@dataclass(frozen=True)
class Ribbon:
    source: Node
    target: Node
    value: float
    at_source: float  # top edge in pixels where it leaves the source
    at_target: float  # top edge where it enters the target
    width: float


@dataclass(frozen=True)
class Layout:
    """Pixel geometry of the diagram. Plotly's own Sankey trace cannot serve: it takes node
    positions, but it orders the bands at a node by its internal layout, so a thin band beside
    a wide one crosses it. Here the items stack in the order of their groups, every node to
    their left sits in the middle of what it pays for, the sources stack as one block around
    the middle of the hubs, and the bands at a node follow the order of their other ends."""

    height: float
    totals: dict[Node, float]  # what flows through a node
    spans: dict[Node, tuple[float, float]]  # top and bottom per node
    ribbons: list[Ribbon]

    @classmethod
    def of(cls, flows: _Links) -> Layout:
        if not flows.nodes:  # a stretch without any flow: nothing to lay out
            return cls(0.0, {}, {}, [])
        totals = _totals(flows)
        leaves = [node for node in flows.nodes if node[0] == LEAF]
        height = max(520.0, 24.0 * len(leaves))
        per_euro = (height - PAD * (len(leaves) - 1)) / sum(totals[leaf] for leaf in leaves)
        spans = _spans(flows, totals, per_euro)
        return cls(
            max(bottom for _, bottom in spans.values()),
            totals,
            spans,
            _ribbons(flows, spans, per_euro),
        )


def _totals(flows: _Links) -> dict[Node, float]:
    """What flows through each node: the larger of what enters and what leaves."""
    paid_in, paid_out = dict.fromkeys(flows.nodes, 0.0), dict.fromkeys(flows.nodes, 0.0)
    for source, target, value in flows.links:
        paid_in[target] += value
        paid_out[source] += value
    return {node: max(paid_in[node], paid_out[node]) for node in flows.nodes}


def _spans(
    flows: _Links, totals: dict[Node, float], per_euro: float
) -> dict[Node, tuple[float, float]]:
    """Top and bottom per node, from the items leftwards: a node sits in the middle of what it
    pays for, the sources as one block around the middle of the hubs. The next node of a column
    starts at least `PITCH` lower, so a sliver keeps room for its label."""
    children: dict[Node, list[Node]] = {}
    for source, target, _value in flows.links:
        children.setdefault(source, []).append(target)
    spans: dict[Node, tuple[float, float]] = {}
    for level in range(LEAF, -1, -1):
        column = [node for node in flows.nodes if node[0] == level]
        steps = [max(totals[node] * per_euro + PAD, PITCH) for node in column]
        block = sum(steps) - PAD
        cursor = 0.0
        if not level:
            hub = spans[next(node for node in flows.nodes if node[0] in (1, 2))]
            cursor = max(0.0, sum(hub) / 2 - block / 2)
        for node, step in zip(column, steps, strict=True):
            size = totals[node] * per_euro
            paid = [spans[child] for child in children.get(node, [])] if level else []
            middle = (min(t for t, _ in paid) + max(b for _, b in paid)) / 2 if paid else 0.0
            top = max(cursor, middle - size / 2)
            spans[node] = (top, top + size)
            cursor = top + step
    return spans


def _ribbons(
    flows: _Links, spans: dict[Node, tuple[float, float]], per_euro: float
) -> list[Ribbon]:
    """The bands stack at each node in the order of their other ends."""
    cursor_out = {node: top for node, (top, _) in spans.items()}
    cursor_in = dict(cursor_out)
    leaves_at: dict[tuple[Node, Node], float] = {}
    enters_at: dict[tuple[Node, Node], float] = {}
    for source, target, value in sorted(flows.links, key=lambda link: spans[link[1]][0]):
        leaves_at[source, target] = cursor_out[source]
        cursor_out[source] += value * per_euro
    for source, target, value in sorted(flows.links, key=lambda link: spans[link[0]][0]):
        enters_at[source, target] = cursor_in[target]
        cursor_in[target] += value * per_euro
    return [
        Ribbon(
            source,
            target,
            value,
            leaves_at[source, target],
            enters_at[source, target],
            value * per_euro,
        )
        for source, target, value in flows.links
    ]


def _band(ribbon: Ribbon) -> tuple[list[float], list[float]]:
    """Outline of a band: an S-curve along its top edge and back along its bottom edge."""
    x0, x1 = LEVEL_X[ribbon.source[0]] + NODE_WIDTH, LEVEL_X[ribbon.target[0]]
    steps = [i / CURVE_STEPS for i in range(CURVE_STEPS + 1)]
    top = [
        ribbon.at_source + (ribbon.at_target - ribbon.at_source) * (3 * t * t - 2 * t**3)
        for t in steps
    ]
    xs = [x0 + (x1 - x0) * t for t in steps]
    return xs + xs[::-1], top + [y + ribbon.width for y in reversed(top)]


def _area(xs: list[float], ys: list[float], color: str, text: str) -> go.Scatter:
    return go.Scatter(
        x=xs,
        y=ys,
        fill="toself",
        fillcolor=color,
        mode="lines",
        line={"width": 0},
        hoveron="fills",
        hoverinfo="text",
        text=text,
    )


def flow_figure(flows: _Links, title: str) -> go.Figure:
    """The diagram of `flows`, its nodes in the words of the session (`_said`)."""
    layout = Layout.of(flows)
    fig = go.Figure()
    for ribbon in layout.ribbons:
        roles = flows.nodes[ribbon.target], flows.nodes[ribbon.source]
        source, target = _said(ribbon.source[1]), _said(ribbon.target[1])
        fig.add_trace(
            _area(
                *_band(ribbon),
                _rgba(ROLES[next((role for role in roles if role != "hub"), "hub")], 0.35),
                f"{source} → {target}: {format_eur(ribbon.value)}",
            )
        )
    labels: dict[bool, list[tuple[float, float, str]]] = {False: [], True: []}
    for node, (top, bottom) in layout.spans.items():
        x, amount, name = LEVEL_X[node[0]], format_eur(layout.totals[node]), _said(node[1])
        fig.add_trace(
            _area(
                [x, x + NODE_WIDTH, x + NODE_WIDTH, x],
                [top, top, bottom, bottom],
                ROLES[flows.nodes[node]],
                f"{name}: {amount}",
            )
        )
        leaf = node[0] == LEAF
        at = x - LABEL_GAP if leaf else x + NODE_WIDTH + LABEL_GAP
        labels[leaf].append((at, (top + bottom) / 2, f"{name}  {amount}"))
    for leaf, entries in labels.items():
        fig.add_trace(
            go.Scatter(
                x=[x for x, _, _ in entries],
                y=[y for _, y, _ in entries],
                text=[text for _, _, text in entries],
                mode="text",
                textposition="middle left" if leaf else "middle right",
                textfont={"size": LABEL_SIZE},
                hoverinfo="skip",
            )
        )
    hidden = {"visible": False, "fixedrange": True}
    fig.update_layout(
        charts.layout(),
        title=title,
        height=layout.height + 2 * PAD + 70,
        margin={"l": 10, "r": 10, "t": 50, "b": 20},
        font={"size": 12},
        showlegend=False,
        hovermode="closest",
        hoverlabel={"font": {"size": LABEL_SIZE}},
        xaxis=hidden | {"range": [0, 1]},
        yaxis=hidden | {"range": [layout.height + PAD, -PAD]},  # room for the outer labels
    )
    return fig


Change = tuple[float, float | None]  # the whole-stretch mean and its change, None without a base


def compare(
    result: RunResult, base: RunResult | None, *, oneoffs: bool, run_rate: bool = False
) -> dict[str, dict[str, Change]]:
    """Per stretch: each line of `Budget.totals` as the mean over its months, and the change
    against the same stretch of `base`."""
    before = (
        {
            s.key: from_ledger(base.ledger, s.months, oneoffs=oneoffs, run_rate=run_rate).totals
            for s in stretches(base)
        }
        if base is not None and base.ledger is not None
        else {}
    )
    out: dict[str, dict[str, Change]] = {}
    for s in stretches(result):
        now = from_ledger(ledger(result), s.months, oneoffs=oneoffs, run_rate=run_rate).totals
        old = before.get(s.key)
        out[s.label] = {
            line: (v, None if old is None else v - old[line]) for line, v in now.items()
        }
    return out


def _cell(change: Change, factor: int) -> str:
    value, delta = (x * factor if x is not None else None for x in change)
    moved = (
        f" ({format_eur(delta, signed=True)})" if delta is not None and abs(delta) >= 0.5 else ""
    )
    return format_eur(value or 0.0) + moved


LINES = (  # what each line of the table holds, folded with the terms below it
    N_("Lines:"),
    N_("income: everything that comes in, gross"),
    N_("taxes: income tax, Soli and social insurance (SV)"),
    N_("spending: everything else that goes out, also the repayment of a loan"),
    N_(
        "surplus: income, taxes and spending added up: what is left to save, below zero what "
        "comes from the savings"
    ),
    N_("{saved}: what the savings plans paid into their assets, a part of the surplus"),
    N_("into assets: the repayment of the loans, less what a policy pays out as income"),
    N_(
        "non-cash income: the growth of the assets and what goes into a policy without passing "
        "the cash"
    ),
    N_(
        "wealth built: the surplus, into assets and the non-cash income added up: the change of "
        "the net worth before the tax on unrealized gains. A stretch that ends before December "
        "can differ a little: it counts its share of the tax settlement of December, which the "
        "net worth pays only then"
    ),
)


def _comparison(
    table: dict[str, dict[str, Change]], factor: int, since: date | None, glossary: str
) -> None:
    """The means per stretch, with the change against the inputs before the day `since`. The
    line of the savings plans shows only with a plan, `glossary` (`cashflows.terms`) below it.
    Signed like the sheet of the Cashflows page, which it links."""
    lines = [
        line
        for line in next(iter(table.values()), {})
        if line != SAVED or any(any(cells[line]) for cells in table.values())
    ]
    st.container(key="table-flows").table(
        pd.DataFrame(
            {
                label: [_cell(cells[line], factor) for line in lines]
                for label, cells in table.items()
            },
            index=[said(line) for line in lines],
        ),
        border="horizontal",
    )
    mean = (
        _(
            "The mean per month over a phase of the run, in euros of the simulation start, money "
            "out below zero: the surplus adds up the three lines above it."
        )
        if factor == 1
        else _(
            "{factor} times the mean per month over a phase of the run, in euros of the "
            "simulation start, money out below zero: the surplus adds up the three lines above it."
        ).format(factor=factor)
    )
    salary = _(
        "A salary can differ a little from the figure you typed, because it rises with its own "
        "growth rate and prices change during the year."
    )
    change = (
        _("In brackets the change against the inputs before {day}. No brackets: no change.").format(
            day=since
        )
        if since
        else _("No earlier inputs of the scenario to compare with.")
    )
    unreached = _("A phase that the scenario does not reach has no column.")
    st.caption(f"{mean} {salary} {unreached} {change}")
    lines_and_terms = f"{listed(LINES, saved=_(SAVED))}\n\n{glossary}"
    fold(lines_and_terms, _("What the lines and terms mean"))
    st.caption(
        _(
            "The Cashflows page shows the plan on one date and 12 months of the run, so its "
            "figures differ."
        )
    )
    page_link("Cashflows", _("Cashflows: the plan on one date"))


@dataclass(frozen=True)
class Controls:
    """What the controls above the tabs chose."""

    scenario: str
    per: str
    factor: int
    floor: float
    oneoffs: bool
    run_rate: bool


FLOOR = 50  # the default of the fold slider, euros per month
# the parts of the social insurance among the taxes, named under the stretch where one shows: the
# boxes of the diagram name them by their short form
SV_PARTS = {"RV", "AV", "KV", "PV"}
SV_TERMS = N_("SV: RV pension, AV unemployment, KV health and PV care insurance.")


@dataclass(frozen=True)
class Option:
    """A switch of the options: its label, default and help, and how the label of the options
    names it while it is on."""

    label: str
    default: bool
    help: str
    on: str


SWITCHES = {
    "flows-oneoffs": Option(
        N_("One-offs"),
        False,
        N_("Sales, a severance, policy payouts, the repayments from them and the tax on them."),
        N_("one-offs"),
    ),
    "flows-run-rate": Option(
        N_("Run rate"),
        True,
        N_(
            "A payment every n months counts 1/n in each month that earns it: a bonus or a "
            "yearly bill shows as its rate."
        ),
        N_("run rate"),
    ),
}


def _options() -> str:
    """The label of the options: the switches that are on and a fold other than the default. On
    a phone only their number, so the button keeps its place beside the amounts."""
    on = [_(s.on) for key, s in SWITCHES.items() if st.session_state.get(key, s.default)]
    if (floor := st.session_state.get("flows-floor", FLOOR)) != FLOOR:
        on.append(
            _("fold below {amount}").format(amount=format_eur(floor)) if floor else _("no fold")
        )
    if not on:
        return _("Options")
    if is_mobile():
        return _("Options ({n})").format(n=len(on))
    return _("Options: {chosen}").format(chosen=", ".join(on))


def _controls(data_dir: Path) -> tuple[Controls, DeltaGenerator]:
    """Scenario and amounts, the rarely changed settings in a popover, in a row that wraps. The
    row, for the select of the comparison."""
    row = st.container(horizontal=True, vertical_alignment="bottom")
    main = first_scenario(data_dir)
    titles = scenario_titles(concrete_scenarios(data_dir), main)
    scenario = row.selectbox(
        _("Scenario"),
        list(titles),
        index=list(titles).index(main),
        format_func=titles.__getitem__,
        key=FLOWS_SCENARIO,
        width=240,
    )
    per, factor = per_control(row, "flows-per")
    with row.popover(_options(), icon=":material/tune:", key="flows-options"):
        floor = st.slider(
            _("Fold items below, per month"),
            0,
            200,
            FLOOR,
            step=10,
            format=EUR_COLUMN,
            help=_("The items of a group below this amount join one `{other}` item.").format(
                other=_("other")
            ),
            key="flows-floor",
        )
        oneoffs, run_rate = (
            st.toggle(_(s.label), value=s.default, help=_(s.help), key=key)
            for key, s in SWITCHES.items()
        )
    return Controls(scenario, per, factor, floor, oneoffs, run_rate), row


WHOLE = 0  # the first position of the period slider: the whole stretch


def _pick(key: str, result: RunResult, stretch: Stretch) -> list[int]:
    """The months of the whole stretch, or of one of its calendar years: a slider between two
    step buttons, which on a phone reach a year in one tap."""
    years: dict[int, list[int]] = {}
    for i in stretch.months:
        years.setdefault(result.months[i].year, []).append(i)
    if len(years) == 1:
        return stretch.months

    def label(year: int) -> str:
        if year == WHOLE:
            n = len(stretch.months)
            return ngettext("whole phase ({n} month)", "whole phase ({n} months)", n).format(n=n)
        return f"{year} ({len(years[year])}/12)"

    options = [WHOLE, *years]
    if st.session_state.get(key) not in options:
        st.session_state[key] = WHOLE
    with st.container(horizontal=True, vertical_alignment="bottom"):
        step_button(key, options, -1, "year")
        picked: int = st.select_slider(
            _("Period"), options, key=key, format_func=label, persist_state="page"
        )
        step_button(key, options, 1, "year")
    return stretch.months if picked == WHOLE else years[picked]


def _stretch(result: RunResult, stretch: Stretch, view: Controls) -> None:
    """One tab: the period, the tiles, the Sankey diagram, and in a narrow main area the outflow
    bars instead of it (`ui.PAGE_STYLE`): its labels need the width. A switch there shows the
    diagram anyway, in a box that scrolls sideways."""
    slug = "-".join(map(str, stretch.key))
    months = _pick(f"flows-period-{view.scenario}-{slug}", result, stretch)
    b = from_ledger(ledger(result), months, oneoffs=view.oneoffs, run_rate=view.run_rate)
    first, last = result.months[months[0]], result.months[months[-1]]
    n = len(months)
    stretched = ngettext(
        "{first} to {last}, age {age}: {n} month in `{phase}`.",
        "{first} to {last}, age {age}: {n} months in `{phase}`.",
        n,
    ).format(
        first=f"{first:%Y-%m}",
        last=f"{last:%Y-%m}",
        age=f"{result.ages[months[0]]:.0f}",
        n=n,
        phase=result.phase_labels.get(stretch.phase, stretch.phase),
    )
    amounts = (
        _("Amounts are the mean per month of those months.")
        if view.factor == 1
        else _("Amounts are {factor} times the mean per month of those months.").format(
            factor=view.factor
        )
    )
    sv = f" {_(SV_TERMS)}" if SV_PARTS & b.taxes.keys() else ""
    st.caption(f"{stretched} {amounts}{sv}")
    tiles = {INCOME: b.income, NET: b.net, SURPLUS: b.surplus, WEALTH_BUILT: b.wealth_built}
    with st.container(key=f"tiles-flows-{slug}"):
        for column, (label, value) in zip(st.columns(len(tiles)), tiles.items(), strict=True):
            column.metric(f"{_(label)} {_(view.per)}", format_eur(view.factor * value))
    links = flow_links(b, floor=view.floor, scale=view.factor)
    if not links.nodes:
        st.info(_("No flows in this period."))
        return
    switch = f"flows-diagram-{slug}"
    wide = bool(st.session_state.get(switch))
    # one of the two shows (`ui.PAGE_STYLE`), or with the switch the diagram in a box that scrolls
    with st.container(key=f"flows-{'scroll' if wide else 'view'}-{slug}"):
        with st.container(key=f"{CHART}{slug}"):
            chart(
                flow_figure(links, f"{stretch.label}, {_(view.per)}"),
                key=f"flows-figure-{slug}",
            )
        with st.container(key=f"flows-bars-{slug}"):
            st.caption(
                _("The diagram is wider than the screen: swipe it sideways.")
                if wide
                else _("The flow diagram needs more width: turn the phone or close the sidebar.")
                if is_mobile()
                else _("The flow diagram needs more width: widen the window or close the sidebar.")
            )
            st.toggle(_("Show the diagram anyway"), key=switch, persist_state="page")
            if not wide:
                outflow_bars(
                    outflow_slices(b, floor=view.floor, scale=view.factor),
                    {(group,): ROLES[role(group)] for group in b.outflows},
                    key=f"flows-outflows-{slug}",
                    scope=_("in `{phase}`").format(phase=stretch.label)
                    if months == stretch.months
                    else _("in {year}").format(year=f"{first:%Y}"),
                    unit=view.per,
                )


def page(data_dir: Path) -> None:
    st.title(_("Flows"))
    st.html(LABEL_INK)
    view, row = _controls(data_dir)
    result = fixed.result(data_dir, view.scenario)
    if result is None:
        st.error(_("This scenario is abstract and has no run."))
        return
    # the file of the scenario at each revision: a rename keeps its history
    name = revisions.named(revisions.entries(data_dir), scenario_file(view.scenario))
    bases = {
        day: (at, then)
        for day, at in since(data_dir, revisions.is_plan).items()
        if (then := name(at))
    }
    day = (
        row.selectbox(
            _("Compare with the inputs before"),
            list(bases),
            format_func=day_said,
            key="flows-since",
            width=280,
        )
        if bases
        else None
    )
    scenario_note(result.note)
    past = runs.baseline(data_dir, bases[day][1], bases[day][0], "fixed") if day else None
    base = past if isinstance(past, RunResult) else None
    if day and not isinstance(past, RunResult):
        st.warning(
            runs.refusal(
                past, _("`{scenario}` before {day}").format(scenario=view.scenario, day=day.day)
            )
        )
    _comparison(
        compare(result, base, oneoffs=view.oneoffs, run_rate=view.run_rate),
        view.factor,
        day.day if day and base else None,
        terms(load_plan(data_dir, data_dir / scenario_file(view.scenario))),
    )
    parts = stretches(result)
    labels = [s.label for s in parts]
    # a phone draws the open tab only: the hidden Sankey diagrams would weigh about 1 MB per run
    tabs = (
        st.tabs(labels, key="flows-tab", on_change="rerun")
        if is_mobile()
        else st.tabs(labels, key="flows-tab")
    )
    for tab, stretch in zip(tabs, parts, strict=True):
        if tab.open is not False:
            with tab:
                _stretch(result, stretch, view)
    fold(_reading())


def _reading() -> str:
    """How to read the page."""
    run = _(
        "The simulation's own numbers: a single run of the scenario with the mean returns and "
        "the mean inflation, in euros of the simulation start. Every tab is a stretch of one "
        "phase and opens on all its months, the slider picks one calendar year. Repaid loans, a "
        "sale, the end of the unemployment benefit and the start of the pension are therefore in "
        "it. The December tax settlement is spread over the months of its year by their taxable "
        "income, so a half year without income carries none. The run rate spreads a bonus or a "
        "yearly bill over the months that earn it. `non-cash income` is no cash flow, so the "
        "diagram leaves it out."
    )
    lines = _(
        "With the one-offs it also holds the tax-free part of a severance paid into a policy and "
        "the top-up of a bAV policy to its guarantee. `into assets` is what the flows put into "
        "your assets other than the cash and into your loans, less what they take out: the loan "
        "principal, less what a policy pays out as income. With the one-offs it also holds "
        "premiums, purchases and repayments, less a sale at the value of the asset, a policy paid "
        "out at once and a write-off. `wealth built` is the surplus plus `into assets` plus the "
        "non-cash income: the change of the net worth before the tax on unrealized gains. A "
        "stretch that ends before December counts its share of the December tax settlement, "
        "which the net worth pays only then, so the two differ a little there. Property upkeep "
        "is a provision of the yearly share of the value. Investing, withdrawals and maturing "
        "deposits are moves between your own accounts and no flows: the rest shows as `saved` "
        "or `from savings`. With a savings plan, `{saved}` is what the plans paid into their "
        "assets: a part of the surplus, which they move out of the cash. One-offs are left out "
        "unless you switch them on."
    ).format(saved=_(SAVED))
    return f"{run} {_(NONCASH_NOTE)} {lines}"
