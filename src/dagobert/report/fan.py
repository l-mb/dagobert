"""Fan charts: liquid net worth with its bands, and the difference of two runs path by path."""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dagobert.difference import Difference
from dagobert.i18n import _
from dagobert.report.charts import (
    EUR_HOVER,
    EUR_TICKS,
    PLOT,
    add_overlays,
    age_axis,
    hover_text,
    layout,
    legend_below,
    shared,
    signed_eur,
    split_title,
    tap_lists_all,
    title_room,
    unified,
)
from dagobert.result import FloatArray, RunResult

_BUTTONS, _FAN_TOP = 8, 134  # pixels: the range buttons above the plot, the top with them


def _add_band(
    fig: go.Figure,
    x: FloatArray,
    lower: FloatArray,
    upper: FloatArray,
    *,
    name: str,
    fillcolor: str,
    cell: tuple[int, int] | None = None,
) -> None:
    """In the subplot `cell` (row, column), shown in the legend only in the first."""
    row, col = cell or (None, None)
    fig.add_trace(
        go.Scatter(
            x=x,
            y=lower,
            legendgroup=name,
            line={"width": 0},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=upper,
            name=name,
            legendgroup=name,
            line={"width": 0},
            fill="tonexty",
            fillcolor=fillcolor,
            showlegend=cell in (None, (1, 1)),
            hoverinfo="skip",
        ),
        row=row,
        col=col,
    )


def liquid_fan_figure(r: RunResult, *, nominal: bool = False, compact: bool = False) -> go.Figure:
    """Liquid net worth with its bands and the median total. The axis opens cut above p75 and
    the median total: with the long tail of p95, even of p90 in nominal euros, the median looks
    flat. Compact: the range buttons get a row of their own under the title."""
    p5, p25, p50, p75, p95 = r.percentiles(r.euros(r.liquid, nominal=nominal))
    total = r.percentiles(r.euros(r.total, nominal=nominal), (50,))[0]
    low, high = min(0.0, float(p5.min())), max(float(p75.max()), float(total.max()))
    pad = 0.05 * (high - low)
    bottom, top = low - pad if low < 0 else 0.0, high + pad
    fig = go.Figure()
    names = [
        _("liquid, middle 90% of runs"),
        _("liquid, middle 50% of runs"),
        _("liquid (median)"),
        _("total (median)"),
    ]
    if r.paths > 1:  # a single path has no spread, the bands would only clutter the legend
        _add_band(fig, r.ages, p5, p95, name=names[0], fillcolor="rgba(77,163,255,0.15)")
        _add_band(fig, r.ages, p25, p75, name=names[1], fillcolor="rgba(77,163,255,0.35)")
    else:
        names = names[2:]
    fig.add_trace(
        go.Scatter(
            x=r.ages,
            y=p50,
            name=names[-2],
            mode="lines",
            line={"color": "#4da3ff", "width": 2},
            hovertext=hover_text(r, p50),
            hoverinfo="text",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=r.ages,
            y=total,
            name=names[-1],
            mode="lines",
            line={"color": "#f5c542", "width": 2, "dash": "dot"},
            hovertext=hover_text(r, total),
            hoverinfo="text",
        )
    )
    if compact:
        tap_lists_all(fig, EUR_HOVER)
    markers = add_overlays(fig, r, compact=compact)
    title = split_title(r.label, _("liquid & total"), compact=compact)
    fig.update_layout(
        layout(),
        title=title,
        yaxis={
            "title": r.unit(nominal=nominal),
            "range": [bottom, top],
            "rangemode": "tozero",
            "tickformat": EUR_TICKS,
        },
        updatemenus=[
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
    )
    if compact:
        top = _FAN_TOP + title_room(title)
        legend_below(fig, len(names), markers, top, per_row=shared(names, 2))
    return fig


def difference_figure(d: Difference, *, compact: bool = False) -> go.Figure:
    """B less A on each path: the median and the p5 to p95 band over the paths, total and
    liquid net worth on one axis, side by side, compact one above the other."""
    rows, cols = (2, 1) if compact else (1, 2)
    fig = make_subplots(
        rows=rows,
        cols=cols,
        shared_xaxes=compact,
        shared_yaxes=not compact,
        horizontal_spacing=0.03,
        vertical_spacing=0.12,
        subplot_titles=[_("Total net worth"), _("Liquid net worth")],
    )
    for i, (p5, p50, p95) in enumerate((d.total, d.liquid), start=1):
        cell = (i, 1) if compact else (1, i)
        if not np.array_equal(p5, p95):  # a single path has no spread
            _add_band(
                fig,
                d.ages,
                p5,
                p95,
                name=_("middle 90% of runs"),
                fillcolor="rgba(77,163,255,0.15)",
                cell=cell,
            )
        fig.add_trace(
            go.Scatter(
                x=d.ages,
                y=p50,
                name=_("median"),
                legendgroup="median",
                showlegend=i == 1,
                mode="lines",
                line={"color": "#4da3ff", "width": 2},
                hovertext=[
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
                hoverinfo="text",
            ),
            *cell,
        )
    fig.add_hline(y=0, line={"color": "#9aa4b2", "width": 1}, row="all", col="all")
    age_axis(fig, d.ages, d.months, compact=compact)
    if compact:  # one title below both plots
        fig.update_xaxes(title=None, row=1)
    fig.update_layout(
        layout(),
        # compact the selectors above name A and B: a long name ran off the screen
        title=_("{b} less {a}, path by path").format(
            b="B" if compact else d.b, a="A" if compact else d.a
        ),
        yaxis={"title": d.unit, "tickformat": EUR_TICKS},
        legend={"orientation": "h", "y": -0.15},
    )
    if compact:
        fig.update_layout(yaxis2={"title": d.unit, "tickformat": EUR_TICKS, "matches": "y"})
        unified(fig)
        legend_below(fig, 2, per_row=2, plots=2)
    return fig
