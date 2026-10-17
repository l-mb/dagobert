"""The tornado chart of the sensitivity run."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go

from dagobert.i18n import N_, _, pgettext
from dagobert.money import format_eur, format_percent, printf
from dagobert.report.charts import (
    ENTRY,
    EUR_TICKS,
    GRAY,
    GREEN,
    RED,
    TICK_ROOM,
    Grid,
    Layout,
    Trace,
    figure,
    points,
    run_out,
    shared,
    signed_eur,
    split_title,
    tick_format,
    title_room,
)
from dagobert.result import unit
from dagobert.sensitivity import Lever, Outcome, Sensitivity


@dataclass(frozen=True)
class _Measure:
    title: str
    get: Callable[[Outcome], float]
    show: Callable[[float], str]
    show_change: Callable[[float], str]
    ticks: str  # of the change
    better: int  # the sign of a change that improves it: -1 a risk, 1 net worth


# A bar takes the color of its effect on the measure of its panel, the direction of its lever the
# fill: one step down striped. Faint white stripes over the full color keep the hue, which a
# lighter fill lost under a color-vision deficiency (rule `charts`).
_EFFECTS = {1: (GREEN, N_("better")), -1: (RED, N_("worse")), 0: (GRAY, N_("no change"))}
_SIDES = {"low": N_("one step down"), "high": N_("one step up")}
_STRIPES = {
    "shape": "/",
    "fillmode": "overlay",
    "fgcolor": "white",
    "fgopacity": 0.4,
    "size": 6,
    "solidity": 0.3,
}
_BAR, _THIN_BAR = 0.7, 0.3
_LEVER, _TICKS = 23, 30  # compact: pixels of a lever, of the tick labels below the plot
_PANEL_LINE = 44  # characters of a panel title on one line, a third of 1,500 px with the sidebar
_ROW = 0.96  # compact: the share of the legend width that its entries in a row take: plotly
# wraps a row that they fill exactly


def _one_digit(value: float) -> float:
    """`value` rounded toward zero to one significant digit."""
    step = 10.0 ** np.floor(np.log10(abs(value)))
    return float(np.trunc(value / step) * step)


def _end_ticks(changes: list[float]) -> list[float]:
    """Compact: zero and the end of the bars farther from it, to one digit. Plotly's own ticks
    turned on a narrow plot and ran into the legend, fewer of them could leave zero alone, and
    the nearer end ran into the label of zero on a phone of 360 px."""
    far = max([0.0, *changes], key=abs)
    return [0.0, _one_digit(far)] if far else [0.0]


def _shown(lever: Lever, value: float) -> str:
    """A value of a lever as its slider shows it, in the language of the page."""
    return printf(pgettext("sprintf", lever.format), value * lever.scale)


def _panel(title: str, value: str, *, compact: bool) -> str:
    """The title of a panel with its base value. Of three side by side, one longer than
    `_PANEL_LINE` breaks before the value: a German title ran into the next."""
    text = f"{title}: {value}"
    return text if compact or len(text) <= _PANEL_LINE else f"{title}:<br>{value}"


def _total(i: int, *, nominal: bool) -> Callable[[Outcome], float]:
    return lambda o: (o.nominal_totals if nominal else o.totals)[i]


def _marker(side: str, color: str | list[str]) -> dict[str, object]:
    return {"color": color, **({"pattern": _STRIPES} if side == "low" else {})}


def _key(name: str, marker: dict[str, object], *, legend: str, group: str) -> Trace:
    """A legend entry, no bar."""
    return {
        "type": "bar",
        "x": [None],
        "y": [None],
        "name": name,
        "legend": legend,
        "legendgroup": group,
        "marker": marker,
        "hoverinfo": "skip",
    }


def sensitivity_figure(
    s: Sensitivity,
    top: int = 12,
    *,
    plan: bool,
    nominal: bool = False,
    compact: bool = False,
    measure: int = 0,
) -> go.Figure:
    """Tornado chart: per lever the change against the base run for the value one step down and
    one step up, green where it improves the measure, red where it worsens it (`_EFFECTS`). One
    panel per measure, the levers with the largest effect on top. Compact only the one of index
    `measure`, its title below the figure title: centered over the panel, the title of a total
    ran past the edge. The title names the levers of the plan or of the assumptions (`plan`)."""
    measures = [
        _Measure(run_out(s.base.ages[-1]), lambda o: o.p_broke, format_percent, points, "+.1%", -1),
        *(
            _Measure(
                _("Net worth at {age}, {unit}").format(
                    age=age, unit=unit(s.start, nominal=nominal)
                ),
                _total(i, nominal=nominal),
                format_eur,
                signed_eur,
                f"+{EUR_TICKS}",
                1,
            )
            for i, age in enumerate(s.base.ages)
        ),
    ]
    if compact:
        measures = [measures[measure]]
    effects = s.effects[:top][::-1]
    labels = [e.lever.stepped for e in effects]
    panels = [_panel(m.title, m.show(m.get(s.base)), compact=compact) for m in measures]
    grid = Grid(
        rows=1,
        cols=len(measures),
        shared_yaxes=True,
        horizontal_spacing=0.03,
        subplot_titles=None if compact else panels,
    )
    sides = {side: _(name) for side, name in _SIDES.items()}
    spans: list[float] = []  # of the bars
    bars: list[Trace] = []
    ticks: Layout = {}  # of the axis of each panel
    for col, m in enumerate(measures, start=1):
        base = m.get(s.base)
        same_way = [(m.get(e.low) - base) * (m.get(e.high) - base) > 0 for e in effects]
        panel: list[float] = []
        for side, name in sides.items():
            changes = [m.get(getattr(e, side)) - base for e in effects]
            panel += changes
            effect = [_EFFECTS[int(np.sign(change)) * m.better] for change in changes]
            bars.append(
                {
                    "type": "bar",
                    "y": labels,
                    "x": changes,
                    "orientation": "h",
                    "name": name,
                    "legendgroup": side,
                    "showlegend": False,
                    "marker": _marker(side, [color for color, _word in effect]),
                    # Both sides share the row. Where both point the same way, the upper trace
                    # is thin, so neither hides the other.
                    "width": [_THIN_BAR if side == "high" and same else _BAR for same in same_way],
                    "hovertext": [
                        f"{e.lever.label} {_shown(e.lever, getattr(e.lever, side))} ({name})"
                        f"<br>{m.title}: {m.show(m.get(getattr(e, side)))} "
                        f"({m.show_change(change)}, {_(word)})"
                        for e, change, (_color, word) in zip(effects, changes, effect, strict=True)
                    ],
                    "hoverinfo": "text",
                }
                | grid.axes(1, col)
            )
        spans += panel
        ticks |= {name: tick_format(m.ticks, panel) for name in grid.names("xaxis", col=col)}
    # The sides in gray: a click hides the bars of one in every panel. Wide the colors in a
    # legend of their own, which a click does not change; compact in the one legend, which
    # lines up its rows: of two legends below the plot, plotly moved the one too wide for the
    # rest of the figure to its edge and left the other at the plot
    colors = {word: color for color, word in (_EFFECTS[1], _EFFECTS[-1])}
    keys = [
        *(
            _key(name, _marker(side, GRAY), legend="legend", group=side)
            for side, name in sides.items()
        ),
        *(
            _key(
                _(word),
                _marker("high", color),
                legend="legend" if compact else "legend2",
                group=word,
            )
            for word, color in colors.items()
        ),
    ]
    subject = _("one step of each part of the plan") if plan else _("one step of each assumption")
    title = split_title(s.scenario, subject, compact=compact)
    legend = {"orientation": "h", "y": -0.08}
    phone: Layout = {}
    if compact:
        head = 24 + title_room(title)  # pixels of the subtitle and title lines
        plot = _LEVER * max(len(effects), 1)
        # Below the tick labels the sides, then the colors, two in a row where the names are
        # short, else a row each (German), as wide as the plot and its labels. Below and left of
        # the plot plotly gives a legend that width, at `y` in pixels of the plot.
        per_row = shared([*sides.values(), *map(_, colors)], 2) or 1
        rows = 4 // per_row
        phone = {
            "title": {"subtitle": {"text": panels[0], "font": {"size": 14}}},
            "height": 100 + head + plot + _TICKS + rows * ENTRY,
            "margin": {"t": 100 + head, "r": TICK_ROOM, "b": _TICKS + rows * ENTRY},
            "legend": {
                "x": -0.001,
                "xanchor": "left",
                "y": -_TICKS / plot,
                "yanchor": "top",
                "tracegroupgap": 0,
                "itemdoubleclick": False,  # it would hide every bar for a color
                "entrywidth": _ROW / per_row,
                "entrywidthmode": "fraction",
            },
        } | {name: {"tickvals": _end_ticks(spans), "tickangle": 0} for name in grid.names("xaxis")}
    return figure(
        [*bars, *keys],
        grid.layout,
        ticks,
        {
            "title": {"text": title},
            "barmode": "overlay",
            "height": 140 + 26 * len(effects),
            # one row: the sides left, the colors right
            "legend": legend,
            "legend2": legend
            | {"itemclick": False, "itemdoubleclick": False, "x": 1, "xanchor": "right"},
        },
        phone,
    )
