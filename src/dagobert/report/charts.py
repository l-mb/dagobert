"""The shared parts of every figure: the layout, the color palette, titles and legends, the hover
labels, and the age axis with the bands of the phases and the markers. A figure speaks the
language of the page that builds it (rule `i18n`): the builders translate where they write.

A builder composes its traces and its layout as mappings and makes the figure once (`figure`):
plotly validates each property that a setter (`add_trace`, `update_layout`) sets, so a figure
of setters took some 40 ms, of mappings a few."""

from __future__ import annotations

import math
import textwrap
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import reduce
from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from dagobert.budget import stretches
from dagobert.i18n import N_, NP_, _, language, pgettext
from dagobert.loader import deep_merge
from dagobert.model.base import named
from dagobert.model.months import add_months, months_between
from dagobert.money import (
    PERCENT,
    decimal_mark,
    format_eur,
    format_number,
    format_percent,
    separators,
)
from dagobert.result import FloatArray, Marker, MarkerKind, RunResult

type Trace = dict[str, Any]  # a trace of plotly as a mapping, its `type` included
type Layout = dict[str, Any]


def layout() -> dict[str, object]:
    """The layout of every figure. The app replaces the template with its own theme, the
    separators stay: the decimal mark of the language (`money.separators`), euros read like
    `format_eur`."""
    return {"template": "plotly_dark", "separators": separators()}


def merged(*layouts: Mapping[str, Any]) -> Layout:
    """`layouts` merged in their order, as `update_layout` applies them one after the other: a
    mapping merges into the one before, any other value replaces it."""
    return reduce(deep_merge, map(dict, layouts), {})


def figure(traces: Iterable[Trace], *layouts: Mapping[str, Any]) -> go.Figure:
    """The figure of `traces` and the `layouts`, merged (`merged`), validated once. Built so, its
    JSON gives the same figure, byte for byte, as the app keeps it (`ui.figures`)."""
    return go.Figure(data=list(traces), layout=merged(layout(), *layouts))


class Grid:
    """Plots in rows and columns as `make_subplots` (its keywords) lays them out: the layout of
    their axes and titles, the axes of a trace in a plot, the names of the axes."""

    def __init__(self, *, rows: int, cols: int, **subplots: Any) -> None:  # noqa: ANN401
        self.rows, self.cols = rows, cols
        self._plots = make_subplots(rows=rows, cols=cols, **subplots)

    @property
    def layout(self) -> Layout:
        return {k: v for k, v in self._plots.layout.to_plotly_json().items() if k != "template"}

    def _names(self, row: int, col: int) -> dict[str, str]:
        plot = self._plots.get_subplot(row, col)
        return {k: str(getattr(plot, k).plotly_name) for k in ("xaxis", "yaxis")}

    def axes(self, row: int, col: int) -> dict[str, str]:
        """The `xaxis` and `yaxis` of a trace in the plot of `row` and `col`: `x2`, `y2`."""
        return {k: name.replace("axis", "") for k, name in self._names(row, col).items()}

    def names(self, axis: str, col: int | None = None) -> list[str]:
        """The names of the `xaxis` or the `yaxis` of the plots, of one column or all:
        `yaxis4`."""
        cols = range(1, self.cols + 1) if col is None else (col,)
        return [self._names(r, c)[axis] for r in range(1, self.rows + 1) for c in cols]


def hline(y: float, line: Mapping[str, object], plots: Iterable[Mapping[str, str]]) -> Layout:
    """A line across each of the `plots` (`Grid.axes`) at `y`, as `add_hline` draws it."""
    return {
        "shapes": [
            {
                "type": "line",
                "x0": 0,
                "x1": 1,
                "xref": f"{p['xaxis']} domain",
                "y0": y,
                "y1": y,
                "yref": p["yaxis"],
                "line": line,
            }
            for p in plots
        ]
    }


EUR_TICKS = ",.0f"  # euro axes: whole euros with thousands separators

# Categorical steps validated on the dark surface of the report and on the light theme of
# the app: reused for the balance sheet classes (`balance.py`, `ui.summary.COLORS`) and for the
# flow roles (`ui.cashflows.ROLES`), where twenty categories have no distinct hues. RED marks debt,
# and with GREEN a step of the sensitivity that worsens or improves a measure (ΔE 10.6 under a
# color-vision deficiency). GRAY is the muted ink of the dataviz palette: a net worth line in it
# reads on both surfaces.
GREEN = "#199e70"
ORANGE = "#d95926"
BLUE = "#3987e5"
AMBER = "#c98500"
PURPLE = "#9085e9"
PINK = "#d55181"
# Gold and crypto, beyond the eight hues of the dataviz palette: validated as opaque fills in the
# stack of the balance sheet (equity, gold, crypto, property; also without one of the two), ΔE ≥
# 12 under a color-vision deficiency and ≥ 16 without to each neighbor. Labels tell them from the
# classes further off: GOLD lies near orange under a deficiency.
GOLD = "#7a6a00"
PLUM = "#a32b9e"
RED = "#b92d2d"
GRAY = "#898781"

SCENARIO_PALETTE = ("#4da3ff", "#f5c542", "#dc5050", "#50c878", "#c678dd", "#e5a56a")
BROKE_BY_AGE = N_("chance to have run out by age")
RUN_OUT = N_("Chance to run out by {age}")  # P(broke)@90 in words (`run_out`)
# the return classes of the plan in words, another class by its key (`class_name`)
CLASSES = {
    "equity": NP_("class", "Equity"),
    "fixed_income": NP_("class", "Fixed income"),
    "cash": NP_("class", "Cash"),
    "property": NP_("class", "Property"),
    "gold": NP_("class", "Gold"),
    "bitcoin": NP_("class", "Bitcoin"),
}


def run_out(age: int) -> str:
    """`RUN_OUT` in the language of the page, `age` the one that the run measures at
    (`RunResult.age_at` of `BROKE_AGE`)."""
    return _(RUN_OUT).format(age=age)


def class_name(name: str) -> str:
    """A return class (`returns` of the assumptions) in the language of the page: `Equity`, a
    class of the user as its key reads (`model.base.named`)."""
    return pgettext("class", CLASSES[name]) if name in CLASSES else named(name)


# `compact` figures, for a phone: the title broken after the scenario, the legend below the
# plot, a tap lists every line at its age. Pixels: the plot, the axis below it, a legend entry
# and each further line of one.
PLOT, AXIS, ENTRY, LINE = 300, 60, 21, 15
# A percentage in a hover is text of `percents` in `customdata`: the locale of plotly takes the
# decimal mark of `separators` but writes no space before its `%`
EUR_HOVER, PCT_HOVER = "%{y:,.0f} €", "%{customdata}"
# compact: the characters of a title line, and the top margin of each line beyond two: plotly
# centers the first line of a title in the margin and lets the others flow below, so a line
# takes twice its height of 21 pixels
_TITLE_WRAP, _TITLE_LINE = 38, 42


def split_title(name: str, subject: str, *, compact: bool) -> str:
    """`name: subject` (a scenario, or the comparison), compact the subject on a line of its own
    and a long name or subject (German runs longer) wrapped: plotly does not wrap a title.
    `title_room` gives the height of its extra lines."""
    if not compact:
        return f"{name}: {subject}"
    return "<br>".join(
        [*textwrap.wrap(f"{name}:", _TITLE_WRAP), *textwrap.wrap(subject, _TITLE_WRAP)]
    )


def title_room(title: str) -> int:
    """Pixels of the lines of a title beyond the two that a top margin holds."""
    return _TITLE_LINE * max(0, title.count("<br>") - 1)


def tap_lists_all(traces: Iterable[Trace], value: str) -> Layout:
    """Compact: a tap anywhere lists every line at its age, by name and `value`, a template of
    `y`: the traces of a hover text take it instead. The layout of `unified`."""
    for trace in traces:
        if trace.get("hoverinfo") == "text":
            trace.pop("hovertext", None)
            trace["hovertemplate"] = f"%{{fullData.name}}: {value}<extra></extra>"
    return unified()


def unified(axes: Iterable[str] = ("xaxis",)) -> Layout:
    """The hover lists every line at its age, on the x `axes`."""
    title = _("age {age}").format(age="%{x:.1f}")
    return {"hovermode": "x unified"} | {a: {"unifiedhovertitle": {"text": title}} for a in axes}


# the bands of the phases, by their order in `assumptions.yaml`: the four of a new plan first
PHASE_COLORS = ("#2b6cb0", "#9b2c2c", "#805ad5", "#276749", "#b7791f", "#2c7a7b", "#97266d")


def percents(values: Iterable[float]) -> list[str]:
    """Shares as `money.format_percent` writes them, the `customdata` of `PCT_HOVER`."""
    return [format_percent(v) for v in values]


def tick_format(fmt: str, values: Sequence[float]) -> dict[str, object]:
    """The `tickformat` of an axis, and of a percent (`.0%`, `+.1%`) whose ticks lie around
    `values` in a language with a space before its `%` the labels in its words (`labelalias`,
    which must match a label of plotly: its decimal mark, its minus sign U+2212). Plotly writes the
    decimal mark of `separators`, but no space."""
    sign = PERCENT[language()]
    if not fmt.endswith("%") or sign == "%":
        return {"tickformat": fmt}
    step = 10.0 ** -int(fmt[-2])
    # a quarter beyond the values: plotly pads its range
    low, high = (round(edge * 125 / step) for edge in (min(0.0, *values), max(0.0, *values)))
    labels = (
        decimal_mark(f"{n * step:{fmt[:-1]}f}").replace("-", "\u2212")
        for n in range(low - 1, high + 2)
    )
    return {"tickformat": fmt, "labelalias": {f"{t}%": t + sign for t in labels}}


def hover_text(
    r: RunResult, values: FloatArray, fmt: Callable[[float], str] = format_eur
) -> list[str]:
    return [f"{m:%Y-%m}<br>{fmt(v)}" for m, v in zip(r.months, values, strict=True)]


def gapped(records: Sequence[tuple[date, float]]) -> list[tuple[date, float | None]]:
    """`records` by month with a gap after a month that the next record does not follow: a line
    joins only the records of consecutive months (plotly breaks it at None), and a marker shows
    each, so two records far apart draw no line between them as if observed."""
    out: list[tuple[date, float | None]] = []
    for month, value in records:
        if out and months_between(out[-1][0], month) > 1:
            out.append((add_months(out[-1][0], 1), None))
        out.append((month, value))
    return out


def _phase_colors(r: RunResult) -> dict[str, str]:
    """A color per phase, by its order in the plan, else in the run."""
    order = [*r.phase_labels, *(p for p in dict.fromkeys(r.phases) if p not in r.phase_labels)]
    return {phase: PHASE_COLORS[i % len(PHASE_COLORS)] for i, phase in enumerate(order)}


def phase_bands(r: RunResult) -> Layout:
    """One band per stretch of a phase, the shapes of the layout."""
    # No annotation text: the markers of `_markers` name the phase transitions.
    colors = _phase_colors(r)
    return {
        "shapes": [
            {
                "type": "rect",
                "xref": "x",
                "yref": "y domain",
                "x0": float(r.ages[s.months[0]]),
                "x1": float(r.ages[s.months[-1]]),
                "y0": 0,
                "y1": 1,
                "fillcolor": colors[s.phase],
                "opacity": 0.10,
                "line": {"width": 0},
            }
            for s in stretches(r)
        ]
    }


# Marker badges: a badge closer to the one before than this share of the age axis (the second
# compact) moves one row down. The rows are in the share of the plot height.
_BADGE_GAP, _BADGE_TOP, _BADGE_ROW = (1 / 40, 1 / 12), 0.95, 0.075
# characters of a line of the marker legend, compact and wide: plotly cuts a line longer than an
# entry, which takes the plot width; compact in the fold of an Explorer tab on a phone (346 px)
# one of more than about 36
_WRAP, _WIDE_WRAP = 34, 110
# pixels right of a compact plot for half a tick label: plotly hides one that runs past the figure
TICK_ROOM = 32
GZ = N_("Gründungszuschuss")
# the kind of a marker (`MarkerKind`: what the engine marks, or the type of an event) in words
MARKER_KINDS: dict[MarkerKind, str] = {
    "phase": N_("Phase"),
    "pension": N_("Pension"),
    "sell": N_("Sale"),
    "buy": N_("Purchase"),
    "buy_property": N_("Purchase"),
    "repay": N_("Repayment"),
    "severance": N_("Severance"),
    "fund_policy": N_("Payment into a policy"),
    "lump_sum": N_("One-off payment"),
    "write_off": N_("Write-off"),
    "end_streams": N_("Payments end"),
    "set_stream": N_("Payment changes"),
    "add_stream": N_("New payment"),
    "inheritance": N_("Inheritance"),
    "gift": N_("Gift"),
    "bav": "",  # `<policy> pays …` says it
    "av": "",
    "alg1": N_("ALG1"),
    "alg1 used": N_("ALG1"),
    "alg1 expired": N_("ALG1"),
    "gz gap": GZ,
    "gz days": GZ,
    "gz salary": GZ,
    "savings plan": N_("Savings plan"),
    "harvest": N_("Gains realized"),
    "disability": N_("Unable to work"),
    "exemption": N_("ALG1 in the PKV"),
    "gkv": N_("Statutory health insurance"),
}
# what a marker of a kind always says
SAYS: dict[MarkerKind, str] = {
    "alg1": N_("on the last salary, not on the self-employment"),
    "alg1 used": N_("the claim is used up"),
    "alg1 expired": N_("the claim arose more than four years ago ({law})"),
    "gz gap": N_("not paid, no ALG1 up to a month before the business ({law})"),
    "gz days": N_("not paid, fewer than 150 days of ALG1 left ({law})"),
    "gz salary": N_("not paid, a salary beside the business ({law})"),
    "exemption": N_(
        "the plan assumes the exemption from the GKV, applied for within three months and "
        "irrevocable ({law})"
    ),
    "gkv": N_("at 55 or older {law} usually blocks the switch"),
}
# the law that a marker names, on one line of its legend
LAWS: dict[MarkerKind, str] = {
    "alg1 expired": "§161 Abs. 2 SGB III",
    "gz gap": "§93 Abs. 2 Nr. 1 SGB III",
    "gz days": "§93 Abs. 2 Nr. 1 SGB III",
    "gz salary": "§93 Abs. 1 SGB III",
    "exemption": "§8 Abs. 1 S. 1 Nr. 1a SGB V",
    "gkv": "§6 Abs. 3a SGB V",
}
# how a policy pays, by `Marker.form`
PAID = {
    "monthly": N_("{policy} pays {amount} per month"),
    "once": N_("{policy} pays {amount} at once"),
}


def said(m: Marker) -> str:
    """What a marker says after its kind, in the language of the page: `Car`, `Policy pays 5 €
    per month`, `85.9% with 40 years`, a full claim `100% with 45 years`, the gain of a harvest
    `19.120 €`, the law of the health insurance behind ALG1 in the PKV and a late switch, the
    end of the claim to ALG1."""
    if (always := SAYS.get(m.kind)) is not None:
        return _(always).format(law=LAWS.get(m.kind, "").replace(" ", "\u00a0"))
    match m.kind:
        case "bav" | "av":
            paid = PAID.get(m.form) or N_("{policy} pays {amount}")
            return _(paid).format(policy=m.detail, amount=format_eur(m.amount))
        case "pension":
            claim, years = format_percent(round(m.amount, 3), None), f"{m.years:.0f}"
            text = (
                _("{claim} with {years} years")
                if m.since is None
                else _("{claim} with {years} years, deferred from {month}")
            )
            return text.format(claim=claim, years=years, month=m.since and f"{m.since:%Y-%m}")
        case "savings plan":
            return _("{plan} paused").format(plan=m.detail)
        case "harvest":
            return format_eur(m.amount)
    return _("{item} (half of the paths)").format(item=m.detail) if m.form == "half" else m.detail


def readable(m: Marker) -> str:
    """A marker with its kind in words: a `lump_sum` of a car reads `One-off payment: Car`, a
    `bav` payout `Policy pays 5 €`."""
    kind = MARKER_KINDS[m.kind]
    return ": ".join(filter(None, (kind and _(kind), said(m))))


def _marker_groups(r: RunResult) -> dict[int, list[str]]:
    """The labels of the markers in words by month index. A label that repeats in a month shows
    once with its count."""
    index = {(m.year, m.month): i for i, m in enumerate(r.months)}
    groups: dict[int, list[str]] = {}
    for marker in r.markers:
        if (i := index.get((marker.month.year, marker.month.month))) is not None:
            groups.setdefault(i, []).append(readable(marker))
    return {
        i: [label if n == 1 else f"{label} ×{n}" for label, n in Counter(labels).items()]
        for i, labels in sorted(groups.items())
    }


@dataclass(frozen=True)
class Overlays:
    """The chrome that `liquid_fan_figure` and `balance_figure` share: the traces and the layout
    of the phase bands, the event markers and the axis of ages and years, and the height of the
    compact marker legend."""

    traces: list[Trace]
    layout: Layout
    legend: int


def _markers(r: RunResult, *, compact: bool) -> Overlays:
    """A dashed line per month with markers and a numbered badge on it. The legend below the
    plot lists the numbers with their labels, and a click on an entry hides line and badge.
    Badges that would touch stagger downwards. They live on a hidden paper-scaled y-axis, so
    they never widen the autorange of the data axis. Compact: a line per label, wrapped."""
    groups = _marker_groups(r)
    if not groups:
        return Overlays([], {}, 0)
    gap = _BADGE_GAP[compact] * float(r.ages[-1] - r.ages[0])
    rows: list[float] = []  # age of the last badge in each row
    traces: list[Trace] = []
    legend = lines = 0
    for n, (i, labels) in enumerate(groups.items(), start=1):
        age, month = float(r.ages[i]), f"{r.months[i]:%Y-%m}"
        row = next((k for k, last in enumerate(rows) if age - last >= gap), len(rows))
        if row < len(rows):
            rows[row] = age
        else:
            rows.append(age)
        group = f"marker {n}"
        if compact:
            first, *rest = labels
            entry = [
                part
                for label in (f"{n} · {month} · {first}", *rest)
                for part in textwrap.wrap(label, _WRAP)
            ]
            legend += ENTRY + LINE * (len(entry) - 1)
            name = "<br>".join(entry)
        else:
            wrapped = textwrap.wrap(f"{n} · {month} · {'; '.join(labels)}", _WIDE_WRAP)
            lines += len(wrapped)
            name = "<br>".join(wrapped)
        traces += [
            {
                "type": "scatter",
                "x": [age, age],
                "y": [0, 1],
                "yaxis": "y2",
                "legend": "legend2",
                "legendgroup": group,
                "mode": "lines",
                "line": {"color": GRAY, "width": 1, "dash": "dash"},
                "showlegend": False,
                "hoverinfo": "skip",
            },
            {
                "type": "scatter",
                "x": [age],
                "y": [_BADGE_TOP - _BADGE_ROW * row],
                "yaxis": "y2",
                "legendgroup": group,
                "cliponaxis": False,
                "mode": "markers+text",
                "marker": {"size": 17, "color": GRAY},
                "text": [str(n)],
                "textfont": {"color": "white", "size": 11},
                "name": name,
                "legend": "legend2",
                "hovertext": "<br>".join(
                    [_("{month}, age {age}").format(month=month, age=f"{age:.0f}"), *labels]
                ),
                # compact a tap lists the lines at its age (`tap_lists_all`), and the nearest
                # badge, even a far one, would join them: the legend has the labels
                "hoverinfo": "skip" if compact else "text",
            },
        ]
    return Overlays(
        traces,
        {
            "yaxis2": {"overlaying": "y", "range": [0, 1], "visible": False, "fixedrange": True},
            "legend2": {
                "orientation": "h",
                "yref": "container",
                "y": 0,
                "yanchor": "bottom",
                "x": 0,
                "xanchor": "left",
                "tracegroupgap": 0,  # each entry is a group of its own
            }
            # all of the height, an entry per row also in landscape from the edge of the figure:
            # the builder makes room
            | ({"maxheight": 1, "xref": "container"} | _row_share(1) if compact else {}),
            # the entries wrap into about one row per two, compact the builder sets the height
            "height": None if compact else 450 + 12 * lines,
        },
        legend,
    )


def age_axis(
    ages: FloatArray, months: list[date], *, compact: bool, axes: Iterable[str] = ("xaxis",)
) -> Layout:
    """One axis, each of the x `axes`: a tick at every fifth age, compact every tenth, with its
    calendar year below. Compact a right margin keeps the label of the last age: a phone has no
    side margins."""
    step = 10 if compact else 5
    vals = list(range(math.ceil(float(ages[0]) / step) * step, int(ages[-1]) + 1, step))
    years = [months[int(np.searchsorted(ages, age))].year for age in vals]
    ticks = [f"{age}<br>{year}" for age, year in zip(vals, years, strict=True)]
    return {
        a: {
            "tickmode": "array",
            "tickvals": vals,
            "ticktext": ticks,
            "title": _("Age and year"),
            "automargin": True,
        }
        for a in axes
    } | ({"margin": {"r": TICK_ROOM}} if compact else {})


def overlays(r: RunResult, *, compact: bool) -> Overlays:
    """Phase bands, event markers and the axis of ages and years."""
    marked = _markers(r, compact=compact)
    return Overlays(
        marked.traces,
        merged(phase_bands(r), marked.layout, age_axis(r.ages, r.months, compact=compact)),
        marked.legend,
    )


def _row_share(per_row: int | None) -> dict[str, object]:
    """Compact legend entries of an equal share of the plot width: `per_row` in each row, also
    where more would fit, so the height that a builder reserves holds in portrait and landscape.
    The legend clips a name longer than its share. None: as wide as their names, so a long name
    moves the legend left to the edge of the figure."""
    return {} if per_row is None else {"entrywidth": 1 / per_row, "entrywidthmode": "fraction"}


# characters of the legend entries that share a row of a phone in portrait (`shared`)
ROW_CHARS = 30


def shared(names: Sequence[str], per_row: int) -> int | None:
    """`per_row` compact legend entries in a row, or a row each (None) when a name is longer than
    its share of `ROW_CHARS`, which the legend would clip: German names run longer."""
    return per_row if max(map(len, names)) <= ROW_CHARS // per_row else None


def legend_below(
    entries: int,
    markers: int = 0,
    top: int = 100,
    order: str = "normal",
    *,
    per_row: int | None = None,
    plots: int = 1,
) -> Layout:
    """Compact: the legend of `entries` at the bottom above the marker legend of `markers`
    pixels, `per_row` in a row (`_row_share`: two short names fit on a phone; None for names
    of any length, which takes a row each on a phone), the top margin of `top` pixels and the
    height that keeps each of `plots` stacked plots at `PLOT` pixels: plotly takes the room of a
    legend from the plot. The legend stays in the lower half, the plots grow for a long marker
    legend: plotly reserves the top margin down to a legend whose `y` is 0.5 or more, which left
    the plot no room (`Something went wrong with axis scaling`). The `order` is explicit: the
    legend groups of the markers would put each entry in a row of its own."""
    rows = -(-entries // (per_row or 1))
    height = max(top + plots * PLOT + AXIS + ENTRY * rows + markers, 2 * markers + 1)
    return {
        "height": height,
        "margin": {"t": top},
        "legend": {"orientation": "h", "x": 0, "yref": "container", "y": markers / height}
        | {"yanchor": "bottom", "traceorder": order}
        | _row_share(per_row),
    }


def points(value: float) -> str:
    """A change of a share in percentage points: `+1.5 pt`."""
    return _("{value} pt").format(value=format_number(value * 100, 1, signed=True))


def signed_eur(value: float) -> str:
    return format_eur(value, signed=True)
