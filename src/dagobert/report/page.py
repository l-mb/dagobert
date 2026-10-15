"""The HTML page of the report: the summary table, the tabs of the figures and `write_html`. Its
style (`report.css`, `phone.css`) and its tab script (`tabs.js`) are files of the package."""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import plotly.io as pio
from plotly.io.json import to_json_plotly
from plotly.offline import get_plotlyjs

from dagobert import anatomy, i18n
from dagobert.difference import Difference
from dagobert.files import atomic_write
from dagobert.i18n import _, pgettext
from dagobert.report.anatomy import anatomy_figure, reading
from dagobert.report.balance import Observed, balance_figure, lasting_figure, lasting_reading
from dagobert.report.charts import SCENARIO_PALETTE
from dagobert.report.comparison import broke_probability_figure, comparison_figure
from dagobert.report.fan import difference_figure, liquid_fan_figure
from dagobert.report.flows import flow_figure
from dagobert.report.summary import (
    DIFFERENCE_NOTE,
    Shown,
    difference_table,
    summary_columns,
    summary_table,
    summary_title,
)
from dagobert.result import RunResult

# A phone below `PHONE` pixels takes `phone.css` and the compact figures. The first column of a
# table wraps a name longer than `LONG` characters (it pushed the figures off the screen).
PHONE = 700
LONG = 16
SAME = "@wide"  # a field of a compact trace that the wide one holds, see `_figure_html`
STYLE, PHONE_STYLE, TABS_SCRIPT = (
    (files(__package__) / name).read_text("utf-8")
    for name in ("report.css", "phone.css", "tabs.js")
)


def _table_html(rows: list[dict[str, str]], columns: Sequence[Shown] = ()) -> str:
    """The keys of the first row head the columns, a term of `columns` by its plain header with its
    help on hover. The table scrolls in its own box. A long name in the first column may wrap: a
    short one keeps its width."""
    shown = {c.term: c for c in columns}
    header = "".join(
        f'<th title="{html.escape(c.tip)}">{html.escape(c.label)}</th>'
        if (c := shown.get(key))
        else f"<th>{html.escape(key)}</th>"
        for key in rows[0]
    )
    body = "\n".join(
        f"<tr><td{' class="long"' * (len(name) > LONG)}>{html.escape(name)}</td>"
        + "".join(f"<td>{html.escape(c)}</td>" for c in rest)
        + "</tr>"
        for name, *rest in (row.values() for row in rows)
    )
    return (
        f'<div class="scroll"><table><thead><tr>{header}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _summary_table_html(results: list[RunResult], *, nominal: bool) -> str:
    """The table and below it what each column means: a touch screen shows no hover."""
    columns = summary_columns(results, nominal=nominal)
    meanings = "".join(
        f"<dt>{html.escape(c.label)}</dt><dd>{html.escape(c.tip)}</dd>" for c in columns[1:]
    )
    return (
        _table_html(summary_table(results, nominal=nominal), columns)
        + f'<details class="columns"><summary>{html.escape(_("What the columns mean"))}</summary>'
        + f"<dl>{meanings}</dl></details>"
    )


Figure = Callable[[bool], go.Figure]  # a figure by `compact`: the report holds both variants


@dataclass(frozen=True)
class _Tab:
    """A tab of the report: its sections, each a heading and its parts (figures and HTML), and
    the note above them."""

    label: str
    accent: str
    sections: list[tuple[str, list[Figure | str]]]
    note: str = ""


def _scenario_tab(i: int, r: RunResult, observed: Observed | None, *, nominal: bool) -> _Tab:
    """The headings in the context `heading`: `Liquid` and `Flows` say more than the word in a
    table and the page name."""
    sections: list[tuple[str, list[Figure | str]]] = [
        (
            pgettext("heading", "Liquid"),
            [lambda c: liquid_fan_figure(r, nominal=nominal, compact=c)],
        )
    ]
    if r.balance:
        sections.append(
            (
                _("Balance sheet"),
                [lambda c: balance_figure(r, observed, nominal=nominal, compact=c)],
            )
        )
    sections.append(
        (
            _("Will the money last?"),
            [
                lambda c: lasting_figure(r, nominal=nominal, compact=c),
                f'<p class="note">{html.escape(lasting_reading(r))}</p>',
            ],
        )
    )
    sections.append(
        (pgettext("heading", "Flows"), [lambda c: flow_figure(r, nominal=nominal, compact=c)])
    )
    if (why := anatomy.of(r)) is not None:
        # compact the figure leaves its reading to the page
        text = f'<p class="note phone">{html.escape(" ".join(reading(why)))}</p>'
        sections.append((_("Why paths run out"), [lambda c: anatomy_figure(why, compact=c), text]))
    return _Tab(r.scenario, SCENARIO_PALETTE[i % len(SCENARIO_PALETTE)], sections, r.note)


def _difference_parts(a: RunResult, b: RunResult, *, nominal: bool) -> list[Figure | str]:
    try:
        d = Difference.of(a, b, nominal=nominal)
    except ValueError as err:
        return [f'<p class="note">{html.escape(str(err))}</p>']
    return [_table_html(difference_table(d)), lambda c: difference_figure(d, compact=c)]


def _difference_tab(results: list[RunResult], *, nominal: bool) -> _Tab:
    """Each scenario against the first: the order of the command line picks the reference, which
    the label names."""
    first = results[0]
    return _Tab(
        _("Difference from {scenario}").format(scenario=first.scenario),
        "var(--fg)",
        [
            (
                _("{b} less {a}").format(b=b.scenario, a=first.scenario),
                _difference_parts(first, b, nominal=nominal),
            )
            for b in results[1:]
        ],
        _("Each scenario less the first, {scenario}, path by path.").format(scenario=first.scenario)
        + f" {_(DIFFERENCE_NOTE)}",
    )


def _json_script(key: str, value: object) -> str:
    """`value` as JSON in a script element that does not run: `</` would end it."""
    text = str(to_json_plotly(value)).replace("</", "<\\/")
    return f'<script type="application/json" id="{key}">{text}</script>'


def _variant(fig: go.Figure) -> dict[str, Any]:
    """Without the template: the page sets the one of the color scheme."""
    spec: dict[str, Any] = fig.to_plotly_json()
    spec["layout"].pop("template", None)
    return spec


def _figure_html(key: str, figure: Figure) -> str:
    """An empty element that the tab script draws, and both variants of the figure. A field of a
    compact trace that equals the one of the wide trace at its place is `SAME`: the data of a
    figure takes most of the page."""
    wide, compact = _variant(figure(False)), _variant(figure(True))
    for mine, theirs in zip(compact["data"], wide["data"], strict=False):
        for field, value in mine.items():
            if field in theirs and to_json_plotly(value) == to_json_plotly(theirs[field]):
                mine[field] = SAME
    variants = {"wide": wide, "compact": compact}
    return f'<div class="figure" id="{key}"></div>' + _json_script(f"data-{key}", variants)


def _tabs_html(tabs: list[_Tab]) -> str:
    buttons = "".join(
        f'<button type="button" role="tab" id="tab-{t}" aria-controls="panel-{t}" '
        f'aria-selected="{str(t == 0).lower()}" data-key="{html.escape(tab.label)}" '
        f'style="--accent: {tab.accent}">{html.escape(tab.label)}</button>'
        for t, tab in enumerate(tabs)
    )
    panels = "\n".join(
        f'<div role="tabpanel" id="panel-{t}" aria-labelledby="tab-{t}"{" hidden" * (t > 0)}>'
        + (f'<p class="note">{html.escape(tab.note)}</p>' if tab.note else "")
        + "".join(
            f"<section><h2>{html.escape(heading)}</h2>"
            + "".join(
                part if isinstance(part, str) else _figure_html(f"fig-{t}-{j}-{k}", part)
                for k, part in enumerate(parts)
            )
            + "</section>"
            for j, (heading, parts) in enumerate(tab.sections)
        )
        + "</div>"
        for t, tab in enumerate(tabs)
    )
    return f'<div role="tablist" aria-label="{html.escape(_("Views"))}">{buttons}</div>\n{panels}'


TEMPLATES = {"dark": "plotly_dark", "light": "plotly_white"}  # by the color scheme of the page


def write_html(
    results: list[RunResult],
    out: Path,
    title: str = "Dagobert",
    observed: Observed | None = None,
    *,
    nominal: bool = False,
) -> Path:
    """Follows the color scheme of the browser and draws the compact figures on a phone. In the
    language of `i18n.use`."""
    if not results:
        msg = "results must be non-empty"
        raise ValueError(msg)

    comparison = _Tab(
        _("Comparison"),
        "var(--fg)",
        [
            (_("Net worth"), [lambda c: comparison_figure(results, nominal=nominal, compact=c)]),
            (
                _("Chance to have run out by age"),
                [lambda c: broke_probability_figure(results, compact=c)],
            ),
        ],
    )
    tabs = [
        comparison,
        *([_difference_tab(results, nominal=nominal)] if len(results) > 1 else []),
        *(_scenario_tab(i, r, observed, nominal=nominal) for i, r in enumerate(results)),
    ]
    config = {
        "templates": {s: pio.templates[name].to_plotly_json() for s, name in TEMPLATES.items()},
        "same": SAME,
    }

    page = f"""<!doctype html>
<html lang="{i18n.language()}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{STYLE}</style>
<style id="phone" media="(max-width: {PHONE}px)">{PHONE_STYLE}</style>
<script>{get_plotlyjs()}</script>
</head>
<body>
<h1>{html.escape(title)}</h1>
<section><h2>{html.escape(summary_title(results, nominal=nominal))}</h2>
{_summary_table_html(results, nominal=nominal)}</section>
{_tabs_html(tabs)}
{_json_script("config", config)}
<script>{TABS_SCRIPT}</script>
</body>
</html>
"""
    atomic_write(out, page)
    return out
