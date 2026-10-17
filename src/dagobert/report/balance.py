"""Stacked by age: the balance sheet of a run with the observed net worth, and whether the money
lasts: the share of the paths that ran out or hold a multiple of their liquid net worth when the
pay ends, and the chance to have died."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np
import plotly.graph_objects as go

from dagobert.i18n import N_, _
from dagobert.model.months import months_between
from dagobert.money import format_eur
from dagobert.report.charts import (
    AMBER,
    BLUE,
    ENTRY,
    EUR_HOVER,
    EUR_TICKS,
    GOLD,
    GRAY,
    GREEN,
    ORANGE,
    PCT_HOVER,
    PINK,
    PLUM,
    PURPLE,
    RED,
    Trace,
    age_axis,
    figure,
    gapped,
    hover_text,
    legend_below,
    overlays,
    percents,
    shared,
    split_title,
    tap_lists_all,
    tick_format,
    title_room,
    unified,
)
from dagobert.result import FloatArray, RunResult
from dagobert.returns import deflate

_BALANCE_STYLE = {  # fixed per class
    "cash": (N_("cash"), BLUE),
    "fixed_income": (N_("fixed income & deposits"), ORANGE),
    "equity": (N_("equity"), GREEN),
    "gold": (N_("gold"), GOLD),
    "crypto": (N_("crypto"), PLUM),
    "property": (N_("property"), AMBER),
    "policies": (N_("pension policies"), PINK),
    "loans": (N_("loans"), RED),
    "latent_tax": (N_("tax on unrealized gains"), PURPLE),
}


def _age_at(r: RunResult, day: date) -> float:
    first = r.months[0]
    return float(r.ages[0]) + months_between(first, day) / 12


@dataclass(frozen=True)
class Observed:
    """The observed net worth of each month with a snapshot in nominal euros
    (`history.actual_totals`) and the consumer prices of a day (`series.consumer_prices`): a
    figure builder reads no file."""

    totals: list[tuple[date, float]]
    cpi: Callable[[date], float]

    def at(self, start: date, *, nominal: bool) -> list[tuple[date, float]]:
        """In euros of `start` each total deflates by the consumer prices of its month."""
        return self.totals if nominal else deflate(self.totals, self.cpi, start)


def balance_figure(
    r: RunResult,
    observed: Observed | None,
    *,
    nominal: bool = False,
    compact: bool = False,
) -> go.Figure:
    """Projected balance sheet by class (paths around the median) with the observed net worth.

    Assets stack upwards, loans and the latent tax downwards. A class that is zero in every month,
    such as gold in a plan without it, takes no legend entry."""
    balance = r.nominal_balance if nominal else r.balance
    held = {key: style for key, style in _BALANCE_STYLE.items() if balance[key].any()}
    traces: list[Trace] = [
        {
            "type": "scatter",
            "x": r.ages,
            "y": balance[key],
            "name": _(label),
            "mode": "lines",
            "stackgroup": "owed" if key in ("loans", "latent_tax") else "owned",
            "line": {"color": color, "width": 1},
            # opaque: the translucent default blends with the surface, and neighbors such as
            # fixed income and equity, or gold and property, then look alike
            "fillcolor": color,
            "hovertext": hover_text(r, balance[key]),
            "hoverinfo": "text",
        }
        for key, (label, color) in held.items()
    ]
    total = r.percentiles(r.euros(r.total, nominal=nominal), (50,))[0]
    traces.append(
        {
            "type": "scatter",
            "x": r.ages,
            "y": total,
            "name": _("net worth (median)"),
            "mode": "lines",
            "line": {"color": GRAY, "width": 2, "dash": "dot"},
            "hovertext": hover_text(r, total),
            "hoverinfo": "text",
        }
    )
    actual = gapped(observed.at(r.months[0], nominal=nominal)) if observed else []
    if actual:
        traces.append(
            {
                "type": "scatter",
                "x": [_age_at(r, day) for day, _value in actual],
                "y": [value for _day, value in actual],
                "name": _("net worth (observed)"),
                "mode": "lines+markers",
                "line": {"color": GRAY, "width": 2},
                "marker": {"size": 8, "line": {"color": "#111418", "width": 2}},
                "hovertext": [
                    "" if value is None else f"{day:%Y-%m}<br>{format_eur(value)}"
                    for day, value in actual
                ],
                "hoverinfo": "text",
            }
        )
    taps = tap_lists_all(traces, EUR_HOVER) if compact else {}
    chrome = overlays(r, compact=compact)
    title = split_title(r.label, _("balance sheet"), compact=compact)
    entries = len(held) + 1 + bool(actual)
    return figure(
        [*traces, *chrome.traces],
        taps,
        chrome.layout,
        {"title": title, "yaxis": {"title": r.unit(nominal=nominal), "tickformat": EUR_TICKS}},
        # compact the stack top down, a row per entry: two of the long names do not fit in a row
        legend_below(entries, chrome.legend, 100 + title_room(title), "reversed", per_row=1)
        if compact
        # a figure drawn in a hidden tab keeps the legend of its smaller plot: room for all
        else {"legend": {"maxheight": ENTRY * entries + ENTRY}},
    )


# The bands of `lasting_figure` from the bottom: run out (`RED`), the liquid net worth of a path
# below its value when the pay ends, from 1 to 2 times it, from 2 to 5 times it, 5 times or more
# (`GREENS`, lighter to deeper: one hue, OKLCH 152°, L 0.75 to 0.43, rule `charts`), dead (`GRAY`).
RUN_OUT, DEAD = N_("run out"), N_("dead")
MULTIPLES = (1, 2, 5)
HELD = (N_("below 1×"), N_("1× to 2×"), N_("2× to 5×"), N_("5× or more"))
GREENS = ("#58c97d", "#2ea55c", "#1b8245", "#116031")
_COLORS: dict[str, str] = {RUN_OUT: RED} | dict(zip(HELD, GREENS, strict=True)) | {DEAD: GRAY}


def lasting_shares(r: RunResult, *, nominal: bool = False) -> dict[str, FloatArray]:
    """The bands of `lasting_figure` from the bottom by their English names, each the share of
    the paths per month from `RunResult.pay_ends`. A path that ran out (`RunResult.broke_by`)
    counts as run out, another by its liquid net worth against its own at that month, both in
    euros of the start or both nominal, in the lowest band without any then. With the survival
    each band takes the chance to be alive and `DEAD` the rest, so the bands add up to 1 in every
    month."""
    liquid = r.euros(r.liquid, nominal=nominal)[:, r.pay_ends :]
    reference = liquid[:, :1]
    held = sum(liquid >= m * reference for m in MULTIPLES) * (reference > 0)  # its band in HELD
    broke = r.broke_by[:, r.pay_ends :]
    alive = np.ones(liquid.shape[1]) if r.survival is None else r.survival[r.pay_ends :]
    shares = {RUN_OUT: broke.mean(axis=0) * alive} | {
        name: (~broke & (held == i)).mean(axis=0) * alive for i, name in enumerate(HELD)
    }
    return shares if r.survival is None else shares | {DEAD: 1 - alive}


def lasting_reading(r: RunResult) -> str:
    """How to read `lasting_figure` in a line: the month that each path is measured against, and
    with the survival the gray band."""
    against = (
        _(
            "The share of the paths that ran out of money, and how much liquid net worth the "
            "others hold: less than, 1 to 2, 2 to 5, or 5 or more times as much as in {month}, "
            "the first month after the last salary or profit."
        ).format(month=f"{r.months[r.pay_ends]:%Y-%m}")
        if r.pay_ends
        else _(
            "The share of the paths that ran out of money, and how much liquid net worth the "
            "others hold: less than, 1 to 2, 2 to 5, or 5 or more times as much as at the start."
        )
    )
    return against if r.survival is None else f"{against} {_('Gray: the chance to have died.')}"


def lasting_figure(r: RunResult, *, nominal: bool = False, compact: bool = False) -> go.Figure:
    """Will the money last: the share of the paths by age that ran out or hold a multiple of their
    liquid net worth at `RunResult.pay_ends`, with the survival the chance to have died on top,
    stacked to 100%. A legend click hides a band, the hover lists every band at its age."""
    shares = lasting_shares(r, nominal=nominal)
    title = split_title(
        r.label,
        _("Will the money last? 1× is the liquid net worth at {age}").format(
            age=round(float(r.ages[r.pay_ends]))
        ),
        compact=compact,
    )
    names = [_(key) for key in shares]
    return figure(
        (
            {
                "type": "scatter",
                "x": r.ages[r.pay_ends :],
                "y": values,
                "name": name,
                "mode": "lines",
                "stackgroup": "one",
                "line": {"width": 0, "color": _COLORS[key]},
                "fillcolor": _COLORS[key],  # opaque, as in the balance sheet
                "customdata": percents(values),
                "hovertemplate": f"%{{fullData.name}}: {PCT_HOVER}<extra></extra>",
            }
            for (key, values), name in zip(shares.items(), names, strict=True)
        ),
        {
            "title": title,
            "yaxis": {"title": _("Share of paths"), "range": [0, 1]} | tick_format(".0%", [1.0]),
            "legend": {"traceorder": "reversed"},  # top down as the stack
        },
        age_axis(r.ages[r.pay_ends :], r.months[r.pay_ends :], compact=compact),
        unified(),
        legend_below(
            len(names), top=100 + title_room(title), order="reversed", per_row=shared(names, 2)
        )
        if compact
        else {},
    )
