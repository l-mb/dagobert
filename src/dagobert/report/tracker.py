"""Figures of the tracker pages: multi-ring donuts, bars, the observed balance sheet, the actual
spending and the records within the band of a run."""

from __future__ import annotations

import textwrap
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from typing import TYPE_CHECKING

import plotly.graph_objects as go

from dagobert.i18n import N_, _
from dagobert.model.months import months_between
from dagobert.money import format_eur, format_number, format_percent
from dagobert.report.charts import AMBER, BLUE, EUR_TICKS, GRAY, RED, gapped, layout

if TYPE_CHECKING:
    from dagobert.actuals import Line
    from dagobert.result import FloatArray, RunResult

NEUTRAL = "#6b7280"
# Larger text than the plotly default of 12, so the labels of the tracker charts read well.
# The theme of the app sets the size of ticks and legend itself, so they need it too. After
# `charts.layout()`.
FONT = {"size": 14}
TRACKER: dict[str, object] = {
    "margin": {"l": 10, "r": 10, "t": 10, "b": 10},
    "font": FONT,
    "legend": {"font": FONT},
    "xaxis": {"tickfont": FONT},
    "yaxis": {"tickfont": FONT},
}
LEGEND_ABOVE = {"orientation": "h", "y": 1.02, "yanchor": "bottom"}
# pixels left of the bars of `bars_figure` for their labels, compact on a phone: one fixed margin
# gives stacked charts one origin, where plotly's automargin fits each to its longest label. A
# label longer than `LABEL_ROOM / LABEL_CHAR` characters breaks at a space onto a second line,
# which the bar pitch of 40 px holds, and only a longer one is cut; its hover names it in full.
LABEL_ROOM = {False: 240, True: 150}
# pixels per character of a label at 14 px with the gap to the bars: at 7.5 the plot still cut the
# first letter of `Company pension: em…` on a phone
LABEL_CHAR = 8
# milliseconds of a bar of a month on a date axis, as wide as plotly draws monthly bars: by
# default a bar takes the distance to the next, a year for two records a year apart
MONTH_BAR = 24 * 24 * 3600 * 1000
# the groups of `history_figure`: the words, messages of the catalogue, and the color
GROUPS = {
    "liquid": (N_("liquid"), BLUE),
    "illiquid": (N_("illiquid"), AMBER),
    "debt": (N_("debt"), RED),
}


@dataclass(frozen=True)
class Slice:
    """One sector of the outer ring. `path` names the sectors from the inner ring outwards."""

    path: tuple[str, ...]
    value: float


def sunburst_figure(
    center: str,
    slices: Sequence[Slice],
    colors: dict[tuple[str, ...], str],
    *,
    height: int = 560,
    maxdepth: int = -1,
) -> go.Figure:
    """Rings from the inner group to the single item, `center` and the total in the hole.

    A sector takes its color from `colors` by path, else from its parent. Only positive values
    make sectors. Values are whole cents, so the parents add up exactly (`branchvalues`).
    `maxdepth` counts the hole as a level and shows the rings within it; a click opens a sector
    with its deeper rings."""
    cents: dict[tuple[str, ...], int] = defaultdict(int)
    for s in slices:
        if s.value > 0:
            for depth in range(1, len(s.path) + 1):  # a parent enters before its children
                cents[s.path[:depth]] += round(100 * s.value)
    nodes = list(cents)
    ident = {path: str(i) for i, path in enumerate(nodes)}
    total = sum(cents[path] for path in nodes if len(path) == 1)
    values = [total, *(cents[p] for p in nodes)]
    fig = go.Figure(
        go.Sunburst(
            ids=["root", *(ident[p] for p in nodes)],
            labels=[center, *(p[-1] for p in nodes)],
            parents=["", *(ident.get(p[:-1], "root") for p in nodes)],
            values=values,
            text=[format_eur(v / 100) for v in values],
            # the share of the total as text: `percentRoot` writes no space before its `%`
            customdata=[format_percent(v / (total or 1)) for v in values],
            branchvalues="total",
            marker={"colors": ["rgba(0,0,0,0)", *(_color(p, colors) for p in nodes)]},
            texttemplate="%{label}<br>%{text}",
            hovertemplate="%{label}<br>%{text}<br>%{customdata}<extra></extra>",
            leaf={"opacity": 1},
            maxdepth=maxdepth,
        )
    )
    fig.update_layout(
        layout() | TRACKER,
        height=height,
        uniformtext={"minsize": FONT["size"], "mode": "hide"},  # a label too small is hidden
    )
    return fig


def _color(path: tuple[str, ...], colors: dict[tuple[str, ...], str]) -> str:
    """The color of `path` in `colors`, else of its nearest parent there."""
    return next((colors[path[:d]] for d in range(len(path), 0, -1) if path[:d] in colors), NEUTRAL)


def bars_figure(
    slices: Sequence[Slice],
    colors: dict[tuple[str, ...], str],
    *,
    signed: bool = False,
    below: Collection[str] = (),
    compact: bool = False,
) -> go.Figure:
    """Horizontal bars of the positive slices, the largest on top, named by the last part of the
    path. A bar takes its color like a sector of `sunburst_figure`. With `signed` a negative
    slice counts too: its bar grows to the left of a zero line, and the values carry a sign and
    sit inside a bar long enough for them, so they keep clear of the labels. The bars of the
    groups in `below` (the first part of a path) go below the others. The labels take a fixed
    room (`LABEL_ROOM`), so the bars of every such chart start at one x: a long label takes two
    lines (`_fit`)."""
    shown = sorted(
        (s for s in slices if (round(s.value) != 0 if signed else s.value > 0)),
        key=lambda s: (s.path[0] not in below, s.value),  # from the bottom
    )
    fig = go.Figure(
        go.Bar(
            x=[s.value for s in shown],
            y=[s.path[-1] for s in shown],
            orientation="h",
            marker_color=[_color(s.path, colors) for s in shown],
            text=[format_eur(s.value, signed=signed) for s in shown],
            textposition="auto" if signed else "outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{text}<extra></extra>",
        )
    )
    room, names = LABEL_ROOM[compact], [s.path[-1] for s in shown]
    fig.update_layout(
        layout() | TRACKER,
        height=80 + 40 * len(shown),
        margin={"l": room, "r": 80, "t": 30},  # the modebar stays clear of the top bar
        xaxis=_zero_axis([s.value for s in shown]) if signed else {"visible": False},
        yaxis={
            "automargin": False,
            "tickvals": names,
            "ticktext": [_fit(name, int(room / LABEL_CHAR)) for name in names],
        },
    )
    return fig


def _fit(text: str, length: int) -> str:
    """`text` in at most two lines of `length` characters, broken at spaces, a line beyond it cut
    with an ellipsis: on one line a long name lost its end (German `<label>: Arbeitgeber`)."""
    first, *rest = textwrap.wrap(text, length, break_long_words=False) or [text]
    return "<br>".join(
        line if len(line) <= length else f"{line[: length - 1]}…"
        for line in (first, *([" ".join(rest)] if rest else []))
    )


def _zero_axis(values: list[float]) -> dict[str, object]:
    """An axis without ticks but with its zero line, and room for the values beside the bars
    on both sides: plotly leaves text outside the bars out of its range."""
    low, high = min([0.0, *values]), max([0.0, *values])
    room = (high - low) / 3
    return {
        "range": [low - room if low else 0.0, high + room if high else 0.0],
        "showticklabels": False,
        "showgrid": False,
        "zeroline": True,
        "zerolinecolor": GRAY,
    }


def _month_axis(months: Sequence[date], labels: int, *, padded: bool = False) -> dict[str, object]:
    """Month ticks over `months`, every month or every n-th so that at most `labels` show, the
    last month among them. Plotly's own step leaves about 80 px to a label: every second month
    where each fits, and days on a short span. `padded` widens the range by half a step on each
    side for a figure without bars: plotly hides a label that runs past the figure."""
    if not months:
        return {"tickformat": "%Y-%m"}
    step = ceil((months_between(months[0], months[-1]) + 1) / labels)
    axis: dict[str, object] = {"tickformat": "%Y-%m", "dtick": f"M{step}", "tick0": months[-1]}
    if padded:
        pad = timedelta(days=15 * step)
        axis["range"] = [months[0] - pad, months[-1] + pad]
    return axis


def spend_figure(months: Mapping[date, Line], *, labels: int) -> go.Figure:
    """Spending per month, actual as bars and plan as a line, both upwards, with at most
    `labels` month labels."""
    x = list(months)
    fig = go.Figure(
        [
            go.Bar(
                x=x,
                y=[-line.actual for line in months.values()],
                name=_("actual"),
                marker_color=BLUE,
                hovertext=[format_eur(-line.actual) for line in months.values()],
                hoverinfo="text+name",
            ),
            go.Scatter(
                x=x,
                y=[-line.plan for line in months.values()],
                name=_("plan"),
                mode="lines+markers",
                line={"color": GRAY, "width": 2},
                marker={"size": 8},
                hovertext=[format_eur(-line.plan) for line in months.values()],
                hoverinfo="text+name",
            ),
        ]
    )
    fig.update_layout(
        layout() | TRACKER,
        height=380,
        yaxis={"tickformat": EUR_TICKS, "ticksuffix": " €", "rangemode": "tozero"},
        xaxis=_month_axis(x, labels),
        legend=LEGEND_ABOVE,
    )
    return fig


def history_figure(
    months: Sequence[tuple[date, dict[str, float]]], *, labels: int, height: int = 380
) -> go.Figure:
    """Observed liquid and illiquid assets as bars of the months with a record, debt below zero,
    net worth as markers, a line between consecutive months only (`gapped`), with at most
    `labels` month labels, `height` pixels high."""
    fig = go.Figure()
    x = [month for month, _sums in months]
    for group, (name, color) in GROUPS.items():
        fig.add_trace(
            go.Bar(
                x=x,
                y=[sums.get(group, 0.0) for _month, sums in months],
                width=MONTH_BAR,
                name=_(name),
                marker_color=color,
                hovertext=[format_eur(sums.get(group, 0.0)) for _month, sums in months],
                hoverinfo="text+name",
            )
        )
    fig.add_trace(_records([(month, sum(sums.values())) for month, sums in months], _("net worth")))
    fig.update_layout(
        layout() | TRACKER,
        barmode="relative",
        height=height,
        yaxis={"tickformat": EUR_TICKS, "ticksuffix": " €"},
        xaxis=_month_axis(x, labels),
        legend=LEGEND_ABOVE,
    )
    return fig


@dataclass(frozen=True)
class Band:
    """A projection per month over the paths: the 5th percentile, the median and the 95th."""

    months: list[date]
    low: FloatArray
    median: FloatArray
    high: FloatArray

    @classmethod
    def of(cls, result: RunResult, values: FloatArray, until: date) -> Band:
        """`values` of `result`, shaped (paths, months), from its first month up to `until`."""
        months = result.months[: max(0, months_between(result.months[0], until) + 1)]
        low, median, high = result.percentiles(values[:, : len(months)], (5, 50, 95))
        return cls(months, low, median, high)


def _records(records: Sequence[tuple[date, float]], name: str) -> go.Scatter:
    """The records by month in `GRAY`, a marker each, a line between consecutive months only."""
    shown = gapped(records)
    return go.Scatter(
        x=[month for month, _value in shown],
        y=[value for _month, value in shown],
        name=name,
        mode="lines+markers",
        line={"color": GRAY, "width": 2},
        marker={"size": 8},
        hovertext=["" if value is None else format_eur(value) for _month, value in shown],
        hoverinfo="text+name",
    )


def track_figure(
    band: Band, records: Sequence[tuple[date, float]], recorded: str, *, labels: int
) -> go.Figure:
    """The records of the months with one, named `recorded`, within the band of a projection,
    over the band and its median, with at most `labels` month labels."""
    fig = go.Figure(
        [
            go.Scatter(
                x=band.months,
                y=band.low,
                mode="lines",
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
            ),
            go.Scatter(
                x=band.months,
                y=band.high,
                name=_("plan, middle 90% of runs"),
                mode="lines",
                fill="tonexty",
                fillcolor="rgba(57,135,229,0.2)",
                line={"width": 0},
                hovertext=[
                    _("{low} to {high}").format(low=format_eur(low), high=format_eur(high))
                    for low, high in zip(band.low, band.high, strict=True)
                ],
                hoverinfo="text+name",
            ),
            go.Scatter(
                x=band.months,
                y=band.median,
                name=_("plan median"),
                mode="lines",
                line={"color": BLUE, "width": 2, "dash": "dot"},
                hovertext=[format_eur(v) for v in band.median],
                hoverinfo="text+name",
            ),
            _records(records, recorded),
        ]
    )
    fig.update_layout(
        layout() | TRACKER,
        height=420,
        hovermode="x unified",
        hoverlabel={"namelength": -1},  # plotly cuts a name at 15 characters
        yaxis={"tickformat": EUR_TICKS, "ticksuffix": " €"},
        xaxis=_month_axis(band.months, labels, padded=True),
        legend=LEGEND_ABOVE,
    )
    return fig


@dataclass(frozen=True)
class Traded:
    """A buy or a sale of a security: its units and euros as traded, and the cost of the units
    held after it, where its marker sits."""

    day: date
    sale: bool
    units: float
    amount: float
    cost: float


@dataclass(frozen=True)
class Position:
    """A security over time: the value of the units held on each day with a price, their cost on
    each day with a price or a trade, and its trades."""

    values: list[tuple[date, float]]
    costs: list[tuple[date, float]]
    trades: list[Traded]


# a line of prices this sparse marks each price: a few typed prices read as points, not a curve
SPARSE = 60


# pixels above the plot of a compact `position_figure`: its legend takes two rows there, below
# the Fullscreen button of the phone, which covered its last entry
COMPACT_TOP = 80


def position_figure(
    position: Position, unit: str, *, labels: int, compact: bool = False
) -> go.Figure:
    """The value of the units held as a line and their cost as steps, each buy and sale a
    triangle on the steps, the euros in `unit`, with at most `labels` month labels; `compact`
    for a phone."""
    values, costs = position.values, position.costs
    fig = go.Figure(
        [
            go.Scatter(
                x=[day for day, _value in costs],
                y=[cost for _day, cost in costs],
                name=_("cost"),
                mode="lines",
                line={"color": GRAY, "width": 2, "dash": "dot", "shape": "hv"},
                hovertext=[format_eur(cost) for _day, cost in costs],
                hoverinfo="text+name",
            ),
            go.Scatter(
                x=[day for day, _value in values],
                y=[value for _day, value in values],
                name=_("value"),
                legendrank=1,  # first in the legend, drawn over the cost
                mode="lines+markers" if len(values) <= SPARSE else "lines",
                line={"color": BLUE, "width": 2},
                marker={"size": 8},
                hovertext=[format_eur(value) for _day, value in values],
                hoverinfo="text+name",
            ),
            *(
                go.Scatter(
                    x=[t.day for t in shown],
                    y=[t.cost for t in shown],
                    name=name,
                    mode="markers",
                    marker={"color": GRAY, "size": 11, "symbol": symbol},
                    hovertext=[
                        _("{units} units for {amount}").format(
                            units=format_number(t.units), amount=format_eur(t.amount)
                        )
                        for t in shown
                    ],
                    hoverinfo="text+name",
                )
                for sale, name, symbol in (
                    (False, _("purchase"), "triangle-up"),
                    (True, _("sale"), "triangle-down"),
                )
                if (shown := [t for t in position.trades if t.sale == sale])
            ),
        ]
    )
    days = [day for day, _cost in costs]
    fig.update_layout(
        layout() | TRACKER,
        height=420,
        hovermode="x unified",
        margin={"t": COMPACT_TOP if compact else 10},
        yaxis={"tickformat": EUR_TICKS, "ticksuffix": " €", "title": unit, "rangemode": "tozero"},
        xaxis=_month_axis(days[:1] + days[-1:], labels, padded=True) | {"hoverformat": "%Y-%m-%d"},
        legend=LEGEND_ABOVE,
    )
    return fig
