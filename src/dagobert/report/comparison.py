"""The scenarios side by side by age: net worth and the chance to have run out."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dagobert.i18n import _
from dagobert.money import format_percent
from dagobert.report.charts import (
    BROKE_BY_AGE,
    EUR_HOVER,
    EUR_TICKS,
    PCT_HOVER,
    SCENARIO_PALETTE,
    Trace,
    age_axis,
    figure,
    hover_text,
    legend_below,
    percents,
    split_title,
    tap_lists_all,
    tick_format,
    title_room,
)
from dagobert.result import RunResult

if TYPE_CHECKING:
    import plotly.graph_objects as go

TWIN_OPACITY = 0.5  # a twin draws lighter: the runs of the sliders stand out; no legend entry


def _styles(results: list[RunResult], dash: str, twin_dash: str) -> list[dict[str, object]]:
    """The line of each result in the color of its scenario, so six colors serve six scenarios
    with their twins. A twin takes `twin_dash` and `TWIN_OPACITY`."""
    order = list(dict.fromkeys(r.scenario for r in results))
    return [
        {
            "line": {
                "color": SCENARIO_PALETTE[order.index(r.scenario) % len(SCENARIO_PALETTE)],
                "width": 2,
                "dash": twin_dash if r.twin else dash,
            },
            "opacity": TWIN_OPACITY if r.twin else 1.0,
        }
        for r in results
    ]


def broke_probability_figure(results: list[RunResult], *, compact: bool = False) -> go.Figure:
    shares = [r.broke_share for r in results]
    traces: list[Trace] = [
        {
            "type": "scatter",
            "x": r.ages,
            "y": share,
            "name": r.label,
            "showlegend": not r.twin,
            "mode": "lines",
            "hovertext": hover_text(r, share, format_percent),
            "hoverinfo": "text",
            "customdata": percents(share) if compact else None,  # `tap_lists_all`
            **style,
        }
        for r, share, style in zip(results, shares, _styles(results, "solid", "dash"), strict=True)
    ]
    twins = sum(r.twin for r in results)
    top = 1.1 * max(*(float(share.max()) for share in shares), 0.05)
    title = split_title(_("Comparison"), _(BROKE_BY_AGE), compact=compact)
    taps = tap_lists_all(traces, PCT_HOVER) if compact else {}
    return figure(
        traces,
        # whole-percent ticks stay distinct
        {
            "title": title,
            "yaxis": {"title": _("Share of paths"), "range": [0, top]} | tick_format(".0%", [top]),
        },
        age_axis(results[0].ages, results[0].months, compact=compact),
        taps,
        legend_below(len(results) - twins, top=100 + title_room(title)) if compact else {},
    )


def comparison_figure(
    results: list[RunResult], *, nominal: bool = False, compact: bool = False
) -> go.Figure:
    traces: list[Trace] = []
    for r, *styles in zip(
        results,
        _styles(results, "solid", "dash"),
        _styles(results, "dot", "dashdot"),
        strict=True,
    ):
        for values, words, style in zip(
            (r.total, r.liquid),
            (_("{scenario}: net worth"), _("{scenario}: liquid")),
            styles,
            strict=True,
        ):
            median = r.percentiles(r.euros(values, nominal=nominal), (50,))[0]
            traces.append(
                {
                    "type": "scatter",
                    "x": r.ages,
                    "y": median,
                    "mode": "lines",
                    "name": words.format(scenario=r.label),
                    "showlegend": not r.twin,
                    "hovertext": hover_text(r, median),
                    "hoverinfo": "text",
                    **style,
                }
            )
    twins = sum(r.twin for r in results)
    title = split_title(_("Comparison"), _("median net worth and liquid by age"), compact=compact)
    taps = tap_lists_all(traces, EUR_HOVER) if compact else {}
    return figure(
        traces,
        {
            "title": title,
            "yaxis": {"title": results[0].unit(nominal=nominal), "tickformat": EUR_TICKS},
        },
        age_axis(results[0].ages, results[0].months, compact=compact),
        taps,
        legend_below(2 * (len(results) - twins), top=100 + title_room(title)) if compact else {},
    )
