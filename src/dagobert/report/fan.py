"""Fan charts: liquid net worth with its bands, and the difference of two runs path by path."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from dagobert.difference import Difference
from dagobert.i18n import _
from dagobert.report.charts import (
    EUR_HOVER,
    EUR_TICKS,
    PLOT,
    Grid,
    Trace,
    age_axis,
    figure,
    hline,
    hover_text,
    legend_below,
    overlays,
    shared,
    signed_eur,
    split_title,
    tap_lists_all,
    title_room,
    unified,
)
from dagobert.result import FloatArray, RunResult

if TYPE_CHECKING:
    import plotly.graph_objects as go

_BUTTONS, _FAN_TOP = 8, 134  # pixels: the range buttons above the plot, the top with them


def _band(
    x: FloatArray,
    lower: FloatArray,
    upper: FloatArray,
    *,
    name: str,
    fillcolor: str,
    legend: bool = True,
) -> list[Trace]:
    """The two traces of a band, the upper one filled down to the lower one."""
    return [
        {
            "type": "scatter",
            "x": x,
            "y": lower,
            "legendgroup": name,
            "line": {"width": 0},
            "showlegend": False,
            "hoverinfo": "skip",
        },
        {
            "type": "scatter",
            "x": x,
            "y": upper,
            "name": name,
            "legendgroup": name,
            "line": {"width": 0},
            "fill": "tonexty",
            "fillcolor": fillcolor,
            "showlegend": legend,
            "hoverinfo": "skip",
        },
    ]


def liquid_fan_figure(r: RunResult, *, nominal: bool = False, compact: bool = False) -> go.Figure:
    """Liquid net worth with its bands and the median total. The axis opens cut above p75 and
    the median total: with the long tail of p95, even of p90 in nominal euros, the median looks
    flat. Compact: the range buttons get a row of their own under the title."""
    p5, p25, p50, p75, p95 = r.percentiles(r.euros(r.liquid, nominal=nominal))
    total = r.percentiles(r.euros(r.total, nominal=nominal), (50,))[0]
    low, high = min(0.0, float(p5.min())), max(float(p75.max()), float(total.max()))
    pad = 0.05 * (high - low)
    bottom, top = low - pad if low < 0 else 0.0, high + pad
    names = [
        _("liquid, middle 90% of runs"),
        _("liquid, middle 50% of runs"),
        _("liquid (median)"),
        _("total (median)"),
    ]
    traces: list[Trace] = []
    if r.paths > 1:  # a single path has no spread, the bands would only clutter the legend
        traces += _band(r.ages, p5, p95, name=names[0], fillcolor="rgba(77,163,255,0.15)")
        traces += _band(r.ages, p25, p75, name=names[1], fillcolor="rgba(77,163,255,0.35)")
    else:
        names = names[2:]
    traces += [
        {
            "type": "scatter",
            "x": r.ages,
            "y": values,
            "name": name,
            "mode": "lines",
            "line": line,
            "hovertext": hover_text(r, values),
            "hoverinfo": "text",
        }
        for values, name, line in (
            (p50, names[-2], {"color": "#4da3ff", "width": 2}),
            (total, names[-1], {"color": "#f5c542", "width": 2, "dash": "dot"}),
        )
    ]
    taps = tap_lists_all(traces, EUR_HOVER) if compact else {}
    chrome = overlays(r, compact=compact)
    title = split_title(r.label, _("liquid & total"), compact=compact)
    return figure(
        [*traces, *chrome.traces],
        taps,
        chrome.layout,
        {
            "title": title,
            "yaxis": {
                "title": r.unit(nominal=nominal),
                "range": [bottom, top],
                "rangemode": "tozero",
                "tickformat": EUR_TICKS,
            },
            "updatemenus": [
                {
                    "type": "buttons",
                    "direction": "left",
                    "showactive": True,
                    "x": 1.0,
                    "xanchor": "right",
                    "y": 1 + _BUTTONS / PLOT if compact else 1.2,
                    "yanchor": "bottom" if compact else "top",
                    # plotly.js paints the active button #F4FAFF, whatever the theme: dark text
                    "bgcolor": "#9aa4b2",
                    "bordercolor": "#444",
                    "font": {"color": "#111418", "size": 14 if compact else 11},
                    "buttons": [
                        {
                            # compact on two lines, wide on one
                            "label": _("Up to\np75").replace("\n", "<br>" if compact else " "),
                            "method": "relayout",
                            # plotly.js converts a range array to log in place: pass the ends
                            "args": [
                                {
                                    "yaxis.type": "linear",
                                    "yaxis.range[0]": bottom,
                                    "yaxis.range[1]": top,
                                }
                            ],
                        },
                        {
                            "label": _("All"),
                            "method": "relayout",
                            "args": [{"yaxis.type": "linear", "yaxis.autorange": True}],
                        },
                        {
                            "label": _("Log"),
                            "method": "relayout",
                            "args": [{"yaxis.type": "log", "yaxis.autorange": True}],
                        },
                    ],
                }
            ],
        },
        legend_below(
            len(names), chrome.legend, _FAN_TOP + title_room(title), per_row=shared(names, 2)
        )
        if compact
        else {},
    )


def difference_figure(d: Difference, *, compact: bool = False) -> go.Figure:
    """B less A on each path: the median and the p5 to p95 band over the paths, total and
    liquid net worth on one axis, side by side, compact one above the other."""
    grid = Grid(
        rows=2 if compact else 1,
        cols=1 if compact else 2,
        shared_xaxes=compact,
        shared_yaxes=not compact,
        horizontal_spacing=0.03,
        vertical_spacing=0.12,
        subplot_titles=[_("Total net worth"), _("Liquid net worth")],
    )
    plots = [grid.axes(*((i, 1) if compact else (1, i))) for i in (1, 2)]
    traces: list[Trace] = []
    for i, ((p5, p50, p95), axes) in enumerate(zip((d.total, d.liquid), plots, strict=True), 1):
        if not np.array_equal(p5, p95):  # a single path has no spread
            band = _band(
                d.ages,
                p5,
                p95,
                name=_("middle 90% of runs"),
                fillcolor="rgba(77,163,255,0.15)",
                legend=i == 1,
            )
            traces += [trace | axes for trace in band]
        traces.append(
            {
                "type": "scatter",
                "x": d.ages,
                "y": p50,
                "name": _("median"),
                "legendgroup": "median",
                "showlegend": i == 1,
                "mode": "lines",
                "line": {"color": "#4da3ff", "width": 2},
                "hovertext": [
                    "<br>".join(
                        [
                            _("{month}, age {age}").format(month=f"{m:%Y-%m}", age=f"{age:.0f}"),
                            _("median {value}").format(value=signed_eur(mid)),
                            _("middle 90%: {low} to {high}").format(
                                low=signed_eur(low), high=signed_eur(high)
                            ),
                        ]
                    )
                    for m, age, low, mid, high in zip(d.months, d.ages, p5, p50, p95, strict=True)
                ],
                "hoverinfo": "text",
            }
            | axes
        )
    xaxes = ("xaxis", "xaxis2")
    return figure(
        traces,
        grid.layout,
        hline(0, {"color": "#9aa4b2", "width": 1}, plots),
        age_axis(d.ages, d.months, compact=compact, axes=xaxes),
        {"xaxis": {"title": None}} if compact else {},  # one title below both plots
        {
            # compact the selectors above name A and B: a long name ran off the screen
            "title": _("{b} less {a}, path by path").format(
                b="B" if compact else d.b, a="A" if compact else d.a
            ),
            "yaxis": {"title": d.unit, "tickformat": EUR_TICKS},
            "legend": {"orientation": "h", "y": -0.15},
        },
        {"yaxis2": {"title": d.unit, "tickformat": EUR_TICKS, "matches": "y"}}
        | unified(xaxes)
        | legend_below(2, per_row=2, plots=2)
        if compact
        else {},
    )
