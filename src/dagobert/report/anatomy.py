"""The failure anatomy figure: the chance to run out (P(broke)) per group of each random
driver, and its words."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dagobert.anatomy import (
    AGES,
    CARE,
    DISABLED,
    EARLY,
    EARLY_YEARS,
    GROUPS,
    INDEX,
    INFLATION,
    INHERITANCE,
    RETURN,
    Anatomy,
    Bin,
    Driver,
    holding_return,
)
from dagobert.i18n import N_, NP_, _, pgettext
from dagobert.model.base import named
from dagobert.money import format_percent
from dagobert.report.charts import (
    BLUE,
    GRAY,
    Grid,
    Trace,
    class_name,
    figure,
    hline,
    run_out,
    split_title,
    tick_format,
    title_room,
)

if TYPE_CHECKING:
    import plotly.graph_objects as go

COLUMNS = 3
ROW, GAP, TOP = 240, 110, 180  # pixels: a row of panels, the gap between rows, the top margin
# pixels of the top margin per line of the subtitle beyond those of `READING`: plotly centers the
# title in the margin, so a line of 16 px takes twice that
LINE = 32
COMPACT_ROW, COMPACT_TOP = 180, 150  # one panel in a row, the title clear of the first panel
READING = (  # the subtitle, compact a note below the figure: plotly does not wrap it
    N_(
        "Each panel sorts the paths by one random driver into {groups} groups of equal size (care "
        "and a disability by the age at their start) and shows the share of each group that ran "
        "out of money by {age}."
    ),
    N_(
        "A steep panel is a driver that decides. Dashed: all paths. Growth rates are nominal, per "
        "year."
    ),
)
# with the panel of a gold or crypto class: its `equity_correlation` gives it part of the slope of
# equity, so a steep panel need not mean that the class decides
TIED = N_("The return of a class that moves with equity shows part of the equity pattern.")
LABELS = {  # each kind of driver in words
    EARLY: N_("Equity return per year, first {years} years"),
    RETURN: N_("{name} return per year to {age}"),
    INFLATION: N_("Inflation per year to {age}"),
    INDEX: N_("{name} growth per year to {age}"),
    CARE: N_("Care starts at age"),
    DISABLED: N_("Disability starts at age"),
    INHERITANCE: N_("Inheritance from {name} at age"),
}


def reading(a: Anatomy) -> tuple[str, ...]:
    """`READING`, with `TIED` when a panel shows the return of a gold or crypto class, in the
    language of the page."""
    lines = (*READING, TIED) if any(holding_return(d.key) for d in a.drivers) else READING
    return tuple(_(line).format(groups=GROUPS, age=a.age) for line in lines)


def label(d: Driver, age: int) -> str:
    """What the driver is (`LABELS`), its class or index by name: `Equity return per year to
    90`, `age` that of `Anatomy.age`."""
    kind, name = d.key
    return _(LABELS[kind]).format(
        years=EARLY_YEARS,
        age=age,
        name=class_name(name) if kind == RETURN else name if kind == INHERITANCE else named(name),
    )


def groups(d: Driver, age: int) -> str:
    """The broke paths against the others: the medians, of an age driver (care, disability,
    inheritance) the shares with the event by `BROKE_AGE`."""
    if d.key[0] in AGES:
        return _("by {age}: ran out {broke}, others {others}").format(
            age=age, broke=format_percent(d.broke, 0), others=format_percent(d.others, 0)
        )
    return _("median: ran out {broke}, others {others}").format(
        broke=format_percent(d.broke), others=format_percent(d.others)
    )


# the last group of an age, the paths without the event by then: one German word per event
NONE_BY = {
    CARE: ("care", NP_("care", "none by\n{age}")),
    DISABLED: ("disability", NP_("disability", "none by\n{age}")),
    INHERITANCE: ("inheritance", NP_("inheritance", "none by\n{age}")),
}


def bin_label(d: Driver, b: Bin) -> str:
    """The range of a group in two lines: `below<br>2.0%`, `80 to<br>85`, `none by<br>90`."""
    kind = d.key[0]
    is_age = kind in AGES
    low, high = (
        None if v is None else f"{v:.0f}" if is_age else format_percent(v) for v in (b.low, b.high)
    )
    if low is None:
        text = (
            _("before\n{age}").format(age=high)
            if is_age
            else _("below\n{value}").format(value=high)
        )
    elif high is None:
        text = (
            pgettext(*NONE_BY[kind]).format(age=low)
            if is_age
            else _("above\n{value}").format(value=low)
        )
    else:
        text = _("{low} to\n{high}").format(low=low, high=high)
    return text.replace("\n", "<br>")


def anatomy_figure(a: Anatomy, *, compact: bool = False) -> go.Figure:
    """Small multiples on one probability axis, so the steepest panel stands out. Compact: one
    column, and the caller shows `reading`."""
    ran_out = _("{broke} of {paths} paths ran out by {age} ({p})").format(
        broke=a.broke, paths=a.paths, age=a.age, p=format_percent(a.p_broke)
    )
    title, lines = split_title(a.scenario, ran_out, compact=compact), reading(a)
    columns, row, margin = (
        (1, COMPACT_ROW, COMPACT_TOP + title_room(title))
        if compact
        else (COLUMNS, ROW, TOP + LINE * (len(lines) - len(READING)))
    )
    rows = -(-len(a.drivers) // columns)
    plot = rows * (row + GAP) - GAP
    grid = Grid(
        rows=rows,
        cols=columns,
        shared_yaxes=True,  # and one range for all rows below
        horizontal_spacing=0.03,
        vertical_spacing=GAP / plot,
        subplot_titles=[f"{label(d, a.age)}<br><sup>{groups(d, a.age)}</sup>" for d in a.drivers],
    )
    plots = [grid.axes(*(n + 1 for n in divmod(i, columns))) for i in range(len(a.drivers))]
    traces: list[Trace] = []
    for d, axes in zip(a.drivers, plots, strict=True):
        bins = [bin_label(d, b) for b in d.bins]
        traces.append(
            {
                "type": "bar",
                "x": bins,
                "y": [b.broke for b in d.bins],
                "marker": {"color": BLUE},
                "hovertext": [
                    "<br>".join(
                        [
                            f"{label(d, a.age)}: {shown.replace('<br>', ' ')}",
                            _("ran out by {age}: {p} of {paths} paths").format(
                                age=a.age, p=format_percent(b.broke), paths=b.paths
                            ),
                        ]
                    )
                    for b, shown in zip(d.bins, bins, strict=True)
                ],
                "hoverinfo": "text",
                "showlegend": False,
            }
            | axes
        )
    top = max(b.broke for d in a.drivers for b in d.bins)
    top = 1.1 * max(top, a.p_broke)
    first = grid.names("yaxis", col=1)
    return figure(
        traces,
        grid.layout,
        hline(a.p_broke, {"color": GRAY, "dash": "dash", "width": 1.5}, plots),
        {
            name: {"range": [0, top]}
            | tick_format(".0%", [top])
            | ({"title": run_out(a.age)} if name in first else {})
            for name in grid.names("yaxis")
        },
        {name: {"tickfont": {"size": 11}} for name in grid.names("xaxis")},
        {
            "title": {"text": title}
            | ({} if compact else {"subtitle": {"text": "<br>".join(lines)}}),
            "height": margin + plot + 80,  # the default bottom margin
            "margin": {"t": margin},
            "bargap": 0.15,
        },
    )
