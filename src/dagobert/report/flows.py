"""The yearly flows of a run as bars, stacked up and down."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import plotly.graph_objects as go

from dagobert.budget import INCOME, TAXES
from dagobert.i18n import N_, _, ngettext
from dagobert.money import format_eur
from dagobert.report.charts import (
    EUR_TICKS,
    GRAY,
    age_axis,
    figure,
    legend_below,
    phase_bands,
    split_title,
    title_room,
)
from dagobert.result import CAPITAL_TAX, FloatArray, RunResult


@dataclass
class _Yearly:
    """Calendar-year buckets of a monthly result."""

    years: list[int]
    ages: FloatArray  # age on 1 January, also for a partial first year
    counts: FloatArray

    @classmethod
    def of(cls, r: RunResult) -> _Yearly:
        years = np.array([m.year for m in r.months])
        starts = np.flatnonzero(np.r_[True, np.diff(years) != 0])
        counts = np.diff(np.r_[starts, len(years)]).astype(float)
        offsets = np.array([(r.months[s].month - 1) / 12 for s in starts])
        return cls(years=years[starts].tolist(), ages=r.ages[starts] - offsets, counts=counts)

    @property
    def centers(self) -> FloatArray:
        """Bar positions: mid-year on the age axis, one year apart."""
        return self.ages + 0.5

    def median_sum(self, arr: FloatArray) -> FloatArray:
        """Median over paths of the calendar-year sum. Partial years stay partial."""
        starts = np.r_[0, np.cumsum(self.counts[:-1]).astype(int)]
        return np.asarray(np.median(np.add.reduceat(arr, starts, axis=1), axis=0))

    def hover(self, values: FloatArray) -> list[str]:
        """Per year its age, the amount and the months of a partial year, in the language of the
        session."""

        def partial(months: int) -> str:
            only = ngettext("{n} month only", "{n} months only", months).format(n=months)
            return "" if months == 12 else f"<br>{only}"

        return [
            _("{year} (age {age})").format(year=y, age=f"{a:.0f}")
            + f"<br>{format_eur(v)}{partial(int(n))}"
            for y, a, n, v in zip(self.years, self.ages, self.counts, values, strict=True)
        ]


OUTLIERS = 0.1  # the share of the years that a one-off stack can be


def _usual_top(stacks: FloatArray) -> float:
    """The tallest of `stacks` inside the upper Tukey fence (third quartile plus 1.5 times the
    interquartile range): a severance year falls outside, a salary year of several does not. When
    more than a tenth lies outside, they are a second level of years (a short working life before
    a long retirement), not one-offs: the fence applies to them again."""
    q1, q3 = np.percentile(stacks, (25, 75))
    outside = stacks > q3 + 1.5 * (q3 - q1)
    if outside.mean() > OUTLIERS:
        return _usual_top(stacks[outside])
    return float(stacks[~outside].max())


def _cut_labels(centers: FloatArray, stacks: FloatArray, edge: float) -> list[dict[str, object]]:
    """The value of each stack that reaches beyond `edge`, written inside the axis at `edge`."""
    return [
        {
            "x": x,
            "y": edge,
            "text": format_eur(v),
            "showarrow": False,
            "yanchor": "top" if edge > 0 else "bottom",
            "font": {"size": 11, "color": "#111418"},
            "bgcolor": "rgba(255,255,255,0.85)",
        }
        for x, v in zip(centers, stacks, strict=True)
        if abs(v) > abs(edge)
    ]


def flow_figure(r: RunResult, *, nominal: bool = False, compact: bool = False) -> go.Figure:
    """Yearly bars, stacked up and down. A one-off such as a severance would set the axis, so
    the axis ends 10% beyond the usual stacks (`_usual_top`), and a cut stack shows its value."""
    yearly = _Yearly.of(r)
    bars = [
        (_(name), yearly.median_sum(r.euros(arr, nominal=nominal)), color)
        for name, arr, color in (
            (INCOME, r.income, "#4dd08a"),
            (N_("expenses"), r.expenses, "#e06c75"),
            (TAXES, r.taxes, "#e5c07b"),
            (CAPITAL_TAX, r.capital_taxes, "#c678dd"),
        )
    ]
    stacked = np.array([values for _name, values, _color in bars])
    up, down = stacked.clip(min=0).sum(axis=0), stacked.clip(max=0).sum(axis=0)
    top, bottom = 1.1 * _usual_top(up), -1.1 * _usual_top(-down)
    labels = _cut_labels(yearly.centers, up, top) + _cut_labels(yearly.centers, down, bottom)
    # the median of the net of each path, not the sum of the medians of the bars
    net = yearly.median_sum(
        r.euros(r.income + r.expenses + r.taxes + r.capital_taxes, nominal=nominal)
    )
    title = split_title(r.label, _("income, spending and taxes, median"), compact=compact)
    return figure(
        [
            *(
                {
                    "type": "bar",
                    "x": yearly.centers,
                    "y": values,
                    "name": name,
                    "width": 0.8,
                    "marker": {"color": color},
                    "hovertext": yearly.hover(values),
                    "hoverinfo": "text",
                }
                for name, values, color in bars
            ),
            {
                "type": "scatter",
                "x": yearly.centers,
                "y": net,
                "name": _("net"),
                "mode": "lines+markers",
                "line": {"width": 2, "color": GRAY},
                "hovertext": yearly.hover(net),
                "hoverinfo": "text",
            },
        ],
        phase_bands(r),
        age_axis(yearly.centers, [date(y, 7, 1) for y in yearly.years], compact=compact),
        {
            "title": title,
            "yaxis": {
                "title": r.unit(nominal=nominal, yearly=True),
                "range": [bottom, top] if labels else None,
                "tickformat": EUR_TICKS,
            },
            "annotations": labels,
            "barmode": "relative",
        },
        legend_below(len(bars) + 1, top=100 + title_room(title), per_row=2) if compact else {},
    )
