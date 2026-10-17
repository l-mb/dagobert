"""The HTML report and its figures: tabs, charts, tables, the console summary."""

from __future__ import annotations

import base64
import dataclasses
import io
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, get_args

import numpy as np
import plotly.graph_objects as go
import plotly.io
import pytest
from builders import plan
from dateutil.relativedelta import relativedelta
from german import leaks, report_words
from rich.console import Console

from dagobert import i18n
from dagobert.actuals import Line
from dagobert.difference import Difference
from dagobert.engine.simulation import simulate
from dagobert.model.assets import EquityAsset
from dagobert.model.assumptions import ReturnClass
from dagobert.model.streams import Stream
from dagobert.money import PERCENT, format_eur
from dagobert.report import (
    BROKE_AT,
    TOTAL_AT,
    Observed,
    balance_figure,
    broke_probability_figure,
    charts,
    comparison_figure,
    console_table,
    difference_figure,
    difference_table,
    flow_figure,
    lasting_figure,
    lasting_shares,
    liquid_fan_figure,
    print_summary,
    summary,
    summary_columns,
    summary_row,
    summary_table,
    write_html,
)
from dagobert.report.flows import _usual_top
from dagobert.report.tracker import (
    LABEL_CHAR,
    LABEL_ROOM,
    MONTH_BAR,
    NEUTRAL,
    Band,
    Slice,
    bars_figure,
    history_figure,
    spend_figure,
    sunburst_figure,
    track_figure,
)
from dagobert.result import BALANCE_CLASSES, Marker, MarkerKind, RunResult
from dagobert.returns import MonteCarloProvider

PATHS, MONTHS = 50, 120
MONTH = date(2030, 1, 1)  # of a marker that no figure shows
_PATH_ARRAYS = (
    "liquid",
    "total",
    "income",
    "expenses",
    "taxes",
    "capital_taxes",
    "broke",
    "care",
    "cpi",
)


def _make_result(scenario: str, seed: int) -> RunResult:
    rng = np.random.default_rng(seed)
    months = [date(2026, 1, 1) + relativedelta(months=i) for i in range(MONTHS)]
    ages = np.linspace(49.0, 59.0, MONTHS)
    phases = ["work" if i % 2 == 0 else "retired" for i in range(MONTHS)]

    liquid = np.cumsum(rng.normal(500.0, 5000.0, (PATHS, MONTHS)), axis=1) + 20_000.0
    total = liquid + rng.normal(300_000.0, 20_000.0, (PATHS, MONTHS))
    income = rng.normal(3_000.0, 300.0, (PATHS, MONTHS))
    expenses = -rng.normal(2_000.0, 200.0, (PATHS, MONTHS))
    taxes = -rng.normal(500.0, 100.0, (PATHS, MONTHS))
    capital_taxes = -rng.normal(50.0, 10.0, (PATHS, MONTHS))
    broke = liquid < 0
    survival = np.linspace(1.0, 0.7, MONTHS)
    cpi = np.cumprod(1 + rng.normal(0.002, 0.002, (PATHS, MONTHS)), axis=1) / 1.002

    return RunResult(
        scenario=scenario,
        model="synthetic",
        months=months,
        ages=ages,
        phases=phases,
        liquid=liquid,
        total=total,
        income=income,
        expenses=expenses,
        taxes=taxes,
        capital_taxes=capital_taxes,
        broke=broke,
        reduced=np.zeros(PATHS, dtype=int),
        raised=np.zeros(PATHS, dtype=int),
        care=np.zeros_like(broke),
        onset=np.full(PATHS, -1),
        em=np.zeros(PATHS, dtype=bool),
        cpi=cpi.astype(np.float32),
        markers=[Marker(months[24], "phase", "Retirement")],
        survival=survival,
    )


def test_write_html(tmp_path: Path) -> None:
    sale = dataclasses.replace(_make_result("Verkauf", 2), note="Sell the flat & rent")
    results = [_make_result("Vermietung", 1), sale]
    content = write_html(results, tmp_path / "report.html").read_text(encoding="utf-8")

    assert "<h2>Summary in € of 2026-01: synthetic, 50 paths (" in content
    # a plain header, its help on hover starts with the term, and a list below for touch; the runs
    # end at 59, where they measure what they would at 67
    assert '<th title="Liquid@59: The money you can use at 59' in content
    assert ">Liquid at 59</th>" in content
    assert "<dt>Liquid at 59</dt><dd>Liquid@59: The money" in content
    assert "Chance to have run out by age" in content
    labels = re.findall(r'<button type="button" role="tab"[^>]*>([^<]*)</button>', content)
    assert labels == ["Comparison", "Difference from Vermietung", "Vermietung", "Verkauf"]
    assert content.index("<h2>Summary") < content.index('role="tablist"')
    assert re.findall(r'<div role="tabpanel" id="(panel-\d)"[^>]*?( hidden)?>', content) == [
        ("panel-0", ""),
        ("panel-1", " hidden"),
        ("panel-2", " hidden"),
        ("panel-3", " hidden"),
    ]
    panel_1 = content[content.index('id="panel-1"') : content.index('id="panel-2"')]
    assert [*re.findall(r"<h2>([^<]*)</h2>", panel_1)] == ["Verkauf less Vermietung"]
    assert "<th>Measure (€ of 2026-01)</th>" in panel_1
    panel_2 = content[content.index('id="panel-2"') : content.index('id="panel-3"')]
    assert [*re.findall(r"<h2>([^<]*)</h2>", panel_2)] == [
        "Liquid",
        "Will the money last?",
        "Flows",
    ]
    assert not panel_2.split(">", 1)[1].startswith("<p")  # a scenario without a note
    panel_3 = content[content.index('id="panel-3"') :]
    assert '<p class="note">Sell the flat &amp; rent</p><section>' in panel_3  # first in the tab
    # each figure in both variants, drawn when its tab shows, with the template of the scheme
    assert content.count('<div class="figure"') == 2 + 1 + 2 * 3
    assert content.count('{"wide":{"data"') == content.count(',"compact":{"data"') == 9
    figures = re.findall(r'<script type="application/json" id="data-[^>]*>([^<]*)<', content)
    assert len(figures) == 9
    assert not any('"template"' in figure for figure in figures)
    alone = write_html(results[:1], tmp_path / "alone.html").read_text(encoding="utf-8")
    assert ">Difference" not in alone


def test_a_german_report_shows_no_english_but_its_data_and_terms(tmp_path: Path) -> None:
    """The page and its figures speak German: only the names and notes of the inputs, the
    terms of the summary in its tips (`P(broke)@90`) and the model stay as written."""
    sale = dataclasses.replace(_make_result("Verkauf", 2), note="Sell the flat & rent")
    with i18n.use("de"):
        page = write_html([_make_result("Vermietung", 1), sale], tmp_path / "report.html")
    content = page.read_text(encoding="utf-8")

    assert leaks(report_words(content)) == []
    assert '<html lang="de">' in content
    assert "<h2>Zusammenfassung in €, Kaufkraft 2026-01: synthetic, 50 Verläufe (" in content
    labels = re.findall(r'<button type="button" role="tab"[^>]*>([^<]*)</button>', content)
    assert labels == ["Vergleich", "Unterschied zu Vermietung", "Vermietung", "Verkauf"]
    # the headings in a context, which `leaks` passes
    assert {"Liquides Vermögen", "Einnahmen, Ausgaben und Steuern", "Reicht das Geld?"} <= set(
        re.findall(r"<h2>([^<]*)</h2>", content)
    )
    assert '<th title="Liquid@59: Das Geld' in content


def test_a_measure_names_the_age_that_the_run_takes_it_at() -> None:
    """A run that ends before 90 measures the chance to run out at its end, one that starts after
    67 the net worth at its start, and the words name that age; a column keeps its term as its key.
    The difference shows a month once, and an age once: at the month of its measure."""
    late = dataclasses.replace(_make_result("late", 1), ages=np.linspace(70.0, 80.0, MONTHS))
    shown = {c.term: c for c in summary_columns([late])}
    assert (shown[BROKE_AT].label, shown[TOTAL_AT].label) == (
        "Chance to run out by 80",
        "Net worth at 70",
    )
    assert shown[TOTAL_AT].tip.startswith("Total@70: What you own at 70, less your debts")
    assert shown[BROKE_AT].tip.startswith("P(broke)@80: The chance to run out of money by age 80:")
    assert list(difference_table(Difference.of(late, late))[0])[1:] == ["at 70", "at 80"]
    short = _make_result("short", 1)  # 49 to 59: both ages fall on its last month
    assert list(difference_table(Difference.of(short, short))[0])[1:] == ["at 59"]
    steps = np.arange(16.0)  # a run from 89 to three months past 90: its end reads 90 too
    band = np.tile(steps, (3, 1))  # p5, median and p95
    months = [date(2026, 1, 1)] * len(steps)
    ended = Difference("A", "B", "€", months, 89 + steps / 12, band, band, steps, (steps, steps))
    assert difference_table(ended)[0] == {
        "Measure (€)": "Total, p5",
        "at 89": "+0 €",
        "at 90": "+12 €",
    }


def test_runs_that_take_a_measure_at_other_ages_name_the_age_of_its_term() -> None:
    """A summary of runs that take a measure at different ages names the age of its term, and
    its help the runs at another age; the end of the runs reads as the ages they end at."""
    early = dataclasses.replace(_make_result("early", 1), ages=np.linspace(70.0, 80.0, MONTHS))
    whole = dataclasses.replace(_make_result("whole", 2), ages=np.linspace(60.0, 95.0, MONTHS))
    shown = {c.term: c for c in summary_columns([whole, early])}
    assert (shown[BROKE_AT].label, shown[TOTAL_AT].label) == (
        "Chance to run out by 90",
        "Net worth at 67",
    )
    assert shown[BROKE_AT].tip.startswith("P(broke)@90: The chance to run out of money by age 90:")
    assert shown[BROKE_AT].tip.endswith("its first or last age counts instead: early (80).")
    assert shown[TOTAL_AT].tip.endswith("its first or last age counts instead: early (70).")
    assert "from the start to age 80 or 95," in shown["Taxes"].tip


def test_console_table_fits_120_columns() -> None:
    name = "Four-day week, then early retirement with a side job"
    results = [dataclasses.replace(_make_result(name, 1), note="Only in the report")]
    table = console_table(results)
    out = io.StringIO()
    Console(width=120, file=out).print(table)
    lines = out.getvalue().splitlines()

    assert str(table.title).startswith("Dagobert Summary in € of 2026-01: synthetic, 50 paths (")
    assert max(map(len, lines)) <= 120
    assert "Only in the report" not in out.getvalue()
    shown = zip(summary.COLUMNS, summary_table(results)[0].values(), strict=True)
    figures = [v.removesuffix(" €") for c, v in shown if c.console][1:]
    assert (
        next(line for line in lines if line.startswith("Four-day")).split()[-len(figures) :]
        == figures
    )


def test_print_summary_never_cuts_a_figure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    results = [_make_result("base", 1)]
    monkeypatch.setenv("COLUMNS", "60")
    print_summary(results)
    printed = capsys.readouterr().out
    assert "…" not in printed
    shown = zip(summary.COLUMNS, summary_table(results)[0].values(), strict=True)
    assert all(v.removesuffix(" €") in printed for c, v in shown if c.console)


def test_summary_title_names_unit_model_paths_and_time() -> None:
    fixed = dataclasses.replace(_make_result("a", 1), model="fixed")
    mc = _make_result("b", 2)
    assert re.fullmatch(
        r"Dagobert Summary in nominal €: fixed; synthetic, 50 paths "
        r"\(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\)",
        str(console_table([fixed, mc, mc], nominal=True).title),
    )


def test_p_care_is_survival_weighted() -> None:
    r = _make_result("Vermietung", 1)
    care = np.zeros_like(r.broke)
    care[0, MONTHS - 1] = True  # one path, episode starts in the last month
    r = dataclasses.replace(r, care=care)

    assert r.survival is not None
    assert summary_row(r).p_care == pytest.approx(r.survival[-1] / PATHS)
    unweighted = dataclasses.replace(r, survival=None)
    assert summary_row(unweighted).p_care == pytest.approx(1 / PATHS)


def test_flow_figure_sums_calendar_years_and_keeps_a_partial_one() -> None:
    """A bar per calendar year, mid-year on the age axis (the age on 1 January plus a half)."""
    r = _make_result("Vermietung", 1)
    r = dataclasses.replace(
        r,
        **{
            **{name: getattr(r, name)[:, :15] for name in _PATH_ARRAYS},
            "months": [date(2026, 10, 1) + relativedelta(months=i) for i in range(15)],
            "ages": np.arange(15, dtype=float),
            "phases": r.phases[:15],
            "income": np.ones((PATHS, 15)),
            "markers": [],
        },
    )

    income = next(
        t for t in flow_figure(r, nominal=True).to_dict()["data"] if t["name"] == "income"
    )

    np.testing.assert_allclose(_trace_data(income, "x"), [-0.25, 3.5])
    np.testing.assert_allclose(_trace_data(income), [3.0, 12.0])
    assert "3 months only" in income["hovertext"][0]
    assert "only" not in income["hovertext"][1]


@pytest.mark.parametrize(
    ("lang", "names", "title", "axis", "hover"),
    [
        (
            "en",
            ["income", "expenses", "taxes & SV", "capital gains tax", "net"],
            "Vermietung: income, spending and taxes, median",
            "€ of 2026-01 per year",
            "2026 (age 49)",
        ),
        (
            "de",
            ["Einnahmen", "Ausgaben", "Steuern & SV", "Abgeltungsteuer", "netto"],
            "Vermietung: Einnahmen, Ausgaben und Steuern, Median",
            "€ pro Jahr, Kaufkraft 2026-01",
            "2026 (Alter 49)",
        ),
    ],
)
def test_flow_figure_is_yearly_bars_plus_net(
    lang: i18n.Language, names: list[str], title: str, axis: str, hover: str
) -> None:
    r = _make_result("Vermietung", 1)
    with i18n.use(lang):
        fig = flow_figure(r).to_dict()

    bars = [t for t in fig["data"] if t["type"] == "bar"]
    assert [t["name"] for t in fig["data"]] == names  # the bars, then the net
    # the median of the net of each path in the first year, not the sum of the medians
    net = r.euros(r.income + r.expenses + r.taxes + r.capital_taxes)[:, :12].sum(axis=1)
    assert _trace_data(fig["data"][-1])[0] == pytest.approx(np.median(net))
    assert len(bars[0]["hovertext"]) == 10
    assert hover in fig["data"][-1]["hovertext"][0]
    assert (fig["layout"]["title"]["text"], fig["layout"]["yaxis"]["title"]["text"]) == (
        title,
        axis,
    )


@pytest.mark.parametrize(("lang", "point"), [("en", "."), ("de", ",")])
def test_a_band_hover_names_the_band_and_shows_a_percent(lang: i18n.Language, point: str) -> None:
    """The percent is text in the language of the page: plotly writes no space before its `%`."""
    with i18n.use(lang):
        data = lasting_figure(_make_result("Vermietung", 1)).to_dict()["data"]
    band = next(t for t in data if t["name"] in {"dead", "verstorben"})

    assert band["hovertemplate"] == "%{fullData.name}: %{customdata}<extra></extra>"
    assert all(re.fullmatch(rf"\d+\{point}\d{PERCENT[lang]}", text) for text in band["customdata"])


def test_a_percent_axis_writes_the_percent_of_the_language() -> None:
    """Plotly writes the decimal mark of the separators but no space before `%`: in German the
    labels of a percent axis take their words by `labelalias`, keyed as plotly writes them."""
    assert charts.tick_format(".0%", [1.0]) == {"tickformat": ".0%"}
    with i18n.use("de"):
        axis = charts.tick_format(".0%", [1.0])
        change: Any = charts.tick_format("+.1%", [-0.025, 0.01])["labelalias"]
        assert charts.tick_format(",.0f", [1.0]) == {"tickformat": ",.0f"}
    assert axis["tickformat"] == ".0%"
    whole: Any = axis["labelalias"]
    assert whole["70%"] == "70\u00a0%"
    assert "100%" in whole
    assert change["−2,5%"] == "−2,5\u00a0%"
    assert change["+1,0%"] == "+1,0\u00a0%"


def test_the_title_of_whether_the_money_lasts_rounds_the_age() -> None:
    r = _make_result("Vermietung", 1)
    r = dataclasses.replace(r, pay_ends=24, ages=r.ages + 0.9)

    assert (
        f"liquid net worth at {round(r.ages[24])}"
        in lasting_figure(r).to_dict()["layout"]["title"]["text"]
    )


@pytest.mark.parametrize("mortality", [True, False], ids=["mortality", "no mortality"])
@pytest.mark.parametrize("nominal", [False, True], ids=["real", "nominal"])
def test_the_bands_of_whether_the_money_lasts_add_up_to_all(mortality: bool, nominal: bool) -> None:
    """From the end of the pay every path that has not run out holds 1 to 2 times itself, and the
    bands, with the dead under the life table, add up to all in every month."""
    r = dataclasses.replace(_make_result("Vermietung", 1), pay_ends=24)
    r = r if mortality else dataclasses.replace(r, survival=None)

    shares = lasting_shares(r, nominal=nominal)

    assert np.allclose(sum(shares.values()), 1.0)
    assert ("dead" in shares) is mortality
    alive = 1.0 if r.survival is None else r.survival[24]
    assert shares["run out"][0] + shares["1× to 2×"][0] == pytest.approx(alive)
    assert _trace_data(lasting_figure(r).to_dict()["data"][0], "x")[0] == r.ages[24]


def test_a_path_without_liquid_net_worth_when_the_pay_ends_holds_below_1x() -> None:
    """No multiple of nothing: such a path holds the lowest band, the others the next."""
    r = _make_result("Vermietung", 1)
    liquid = np.full_like(r.liquid, 50_000.0)
    liquid[0, 24] = 0.0
    r = dataclasses.replace(r, liquid=liquid, broke=liquid < 0, pay_ends=24, survival=None)

    shares = lasting_shares(r, nominal=True)

    assert shares["below 1×"] == pytest.approx(1 / r.paths)
    assert shares["1× to 2×"] == pytest.approx(1 - 1 / r.paths)


def _lasting(spending: float) -> dict[str, np.ndarray]:
    """The bands of a depot over 30 years of spending, which never had pay."""
    p = plan(
        [Stream(name="Leben", amount=-spending)],
        [EquityAsset(id="d", kind="equity", value=400_000, cost_basis=400_000)],
        returns={"equity": ReturnClass(mean=0.05, stdev=0.15)}
        | {name: ReturnClass(mean=0.0) for name in ("fixed_income", "cash", "property")},
        cash_buffer_months=1,
    )
    return lasting_shares(
        simulate(p, MonteCarloProvider(p.assumptions, 400, seed=3).sample(360), "x")
    )


def test_less_spending_runs_out_less_and_holds_more() -> None:
    less, more = _lasting(1500), _lasting(2000)
    assert less["run out"][-1] < more["run out"][-1]
    assert less["5× or more"][-1] > more["5× or more"][-1]


def test_liquid_fan_figure_draws_the_bands_of_a_spread() -> None:
    """Two traces per band, none for a single path. The markers live on an axis of their own."""
    r = _make_result("Vermietung", 1)
    fig = liquid_fan_figure(r).to_dict()

    assert fig["layout"]["yaxis"]["rangemode"] == "tozero"
    assert fig["layout"]["yaxis2"]["overlaying"] == "y"
    bands = ("liquid, middle 90% of runs", "liquid, middle 50% of runs")
    assert [sum(t.get("legendgroup") == band for t in fig["data"]) for band in bands] == [2, 2]
    one = dataclasses.replace(r, **{k: getattr(r, k)[:1] for k in _PATH_ARRAYS})
    assert not {t.get("legendgroup") for t in liquid_fan_figure(one).to_dict()["data"]} & {*bands}


def test_liquid_fan_figure_opens_cut_above_p75() -> None:
    r = _make_result("Vermietung", 1)
    r.liquid[:4] *= 100  # a long tail in the top 8% of the paths
    p5, p75, p95 = r.percentiles(r.euros(r.liquid), (5, 75, 95))
    total = r.percentiles(r.euros(r.total), (50,))[0]
    layout = liquid_fan_figure(r).to_dict()["layout"]

    low, high = layout["yaxis"]["range"]
    assert low <= min(0.0, p5.min())
    assert max(p75.max(), total.max()) < high < p95.max()
    [menu] = layout["updatemenus"]
    assert [b["label"] for b in menu["buttons"]] == ["Up to p75", "All", "Log"]
    first = menu["buttons"][0]["args"][0]
    assert [first["yaxis.range[0]"], first["yaxis.range[1]"]] == [low, high]


@pytest.mark.parametrize(("field", "spike"), [("income", 500_000.0), ("taxes", -500_000.0)])
def test_flow_figure_cuts_the_axis_beyond_a_one_off(field: str, spike: float) -> None:
    r = _make_result("Vermietung", 1)
    plain = flow_figure(r).to_dict()["layout"]
    arr = getattr(r, field).copy()
    arr[:, 30] += spike  # a severance in the third year
    fig = flow_figure(dataclasses.replace(r, **{field: arr})).to_dict()

    assert not plain.get("annotations")
    assert "range" not in plain["yaxis"]
    bars = np.array([_trace_data(t) for t in fig["data"] if t["type"] == "bar"])
    up, down = bars.clip(min=0).sum(axis=0), bars.clip(max=0).sum(axis=0)
    low, high = fig["layout"]["yaxis"]["range"]
    others = np.arange(len(up)) != 2
    assert (up[others] <= high).all() and (down[others] >= low).all()
    stack = (up if spike > 0 else down)[2]
    assert not low <= stack <= high
    [label] = fig["layout"]["annotations"]
    assert label["text"] == format_eur(stack)


def test_a_short_working_life_before_a_long_retirement_is_no_one_off() -> None:
    """The salary years stay inside the axis; a single spike beside them is still cut."""
    stacks = np.array([100.0] * 25 + [40.0] * 55)
    assert _usual_top(stacks) == 100.0
    assert _usual_top(np.append(stacks, 500.0)) == 100.0


@pytest.mark.parametrize("figure", [liquid_fan_figure, lambda r: balance_figure(r, None)])
def test_markers_are_numbered_and_listed_below_the_plot(
    figure: Callable[[RunResult], go.Figure],
) -> None:
    r = _make_result("Vermietung", 1)
    r.balance = {name: np.zeros(MONTHS) for name in BALANCE_CLASSES}
    r.markers = [
        Marker(r.months[24], "phase", "retired"),
        Marker(r.months[24], "add_stream"),
        Marker(r.months[24], "add_stream"),
        Marker(r.months[25], "sell", "flat"),  # a month later: its badge moves a row down
        Marker(r.months[100], "lump_sum"),  # far off: back in the first row
    ]

    fig = figure(r).to_dict()

    badges = [t for t in fig["data"] if t.get("legend") == "legend2" and t.get("showlegend", True)]
    assert [b["name"] for b in badges] == [
        "1 · 2028-01 · Phase: retired; New payment ×2",
        "2 · 2028-02 · Sale: flat",
        "3 · 2034-05 · One-off payment",
    ]
    assert [list(b["text"]) for b in badges] == [["1"], ["2"], ["3"]]
    first, second, third = (b["y"][0] for b in badges)
    assert second < first == third
    assert {b["yaxis"] for b in badges} == {"y2"}  # the data axis keeps its range
    assert not fig["layout"].get("annotations")


@pytest.mark.parametrize(
    ("figure", "unified"),
    [
        (liquid_fan_figure, True),
        (lambda r, **kw: balance_figure(r, None, **kw), True),
        (flow_figure, False),
    ],
    ids=["fan", "balance", "flow"],
)
def test_compact_figures_put_the_legend_below_and_the_years_apart(
    figure: Callable[..., go.Figure], unified: bool
) -> None:
    r = _make_result("Vermietung", 1)
    r.balance = {name: np.zeros(MONTHS) for name in BALANCE_CLASSES}

    wide, narrow = (figure(r, compact=compact).to_dict()["layout"] for compact in (False, True))

    assert "orientation" not in wide.get("legend", {})  # beside the plot
    assert narrow["legend"]["orientation"] == "h"
    assert narrow["title"]["text"] == "Vermietung:<br>" + wide["title"]["text"].split(": ", 1)[1]
    assert "xaxis2" not in wide  # one axis: the ages with their years below
    ages = [[tick.split("<br>")[0] for tick in a["xaxis"]["ticktext"]] for a in (wide, narrow)]
    assert ages == [["50", "55"], ["50"]]  # every fifth age, compact every tenth
    assert wide["xaxis"]["ticktext"][0].endswith("<br>2027")
    assert (narrow.get("hovermode") == "x unified") is unified  # a tap lists every line
    assert "hovermode" not in wide


@pytest.mark.parametrize(
    "figure",
    [
        lambda r: comparison_figure([r], compact=True),
        lambda r: broke_probability_figure([r], compact=True),
        lambda r: liquid_fan_figure(r, compact=True),
        lambda r: flow_figure(r, compact=True),
        lambda r: lasting_figure(r, compact=True),
    ],
    ids=["comparison", "broke", "fan", "flow", "lasting"],
)
def test_a_compact_age_axis_keeps_room_for_its_last_label(
    figure: Callable[[RunResult], go.Figure],
) -> None:
    """A phone has no side margins, and plotly hides a tick label that runs past the figure."""
    assert figure(_make_result("Vermietung", 1)).to_dict()["layout"]["margin"]["r"] > 0


@pytest.mark.parametrize("figure", [liquid_fan_figure, flow_figure], ids=["fan", "flow"])
def test_a_long_scenario_wraps_in_a_compact_title_and_the_top_grows_by_it(
    figure: Callable[..., go.Figure],
) -> None:
    short, long = (
        figure(_make_result(name, 1), compact=True).to_dict()["layout"]
        for name in ("Vermietung", "Four-day week, then early retirement with a side job")
    )
    *scenario, _ = long["title"]["text"].split("<br>")
    assert len(scenario) == 2 and all(len(line) <= 38 for line in scenario)
    grown = long["margin"]["t"] - short["margin"]["t"]
    assert grown > 0 and long["height"] - short["height"] == grown  # the plot keeps its height
    colon = figure(_make_result("Plan: B", 1), compact=True).to_dict()["layout"]["title"]["text"]
    assert colon.split("<br>")[0] == "Plan: B:"  # a name keeps its own colon


@pytest.mark.parametrize(
    "figure",
    [liquid_fan_figure, lambda r, **kw: balance_figure(r, None, **kw)],
    ids=["fan", "balance"],
)
def test_a_long_marker_legend_keeps_the_legend_of_the_lines_in_the_lower_half(
    figure: Callable[..., go.Figure],
) -> None:
    """Plotly reserves the top margin down to a legend whose `y` is 0.5 or more, which left the
    plot no room: the figure grows instead, and the plot keeps at least its room."""
    r = _make_result("Vermietung", 1)
    r.balance = {name: np.ones(MONTHS) for name in BALANCE_CLASSES}
    plain = figure(r, compact=True).to_dict()["layout"]
    r.markers.extend(Marker(month, "set_stream", "a long label " * 4) for month in r.months[::6])
    layout = figure(r, compact=True).to_dict()["layout"]

    def room(layout: dict[str, Any]) -> float:  # between the top margin and the legend
        return float(layout["height"] * (1 - layout["legend"]["y"]) - layout["margin"]["t"])

    assert layout["legend"]["y"] < 0.5
    assert room(layout) >= room(plain)


def test_a_compact_marker_legend_wraps_and_the_figure_grows_by_it() -> None:
    r = _make_result("Vermietung", 1)
    short = liquid_fan_figure(r, compact=True).to_dict()
    r.markers.append(Marker(r.months[24], "set_stream", "a long label " * 4))
    long = liquid_fan_figure(r, compact=True).to_dict()

    [entry] = [t["name"] for t in long["data"] if t.get("legend") == "legend2" and t.get("name")]
    lines = entry.split("<br>")
    assert lines[0] == "1 · 2028-01 · Phase: Retirement"
    assert len(lines) > 2 and all(len(line) <= 34 for line in lines)  # an Explorer fold holds 36
    assert long["layout"]["height"] > short["layout"]["height"]


@pytest.mark.parametrize(
    ("marker", "shown"),
    [
        (Marker(MONTH, "lump_sum", "Replace the car"), "One-off payment: Replace the car"),
        (Marker(MONTH, "phase", "retired"), "Phase: retired"),
        (Marker(MONTH, "add_stream"), "New payment"),
        (Marker(MONTH, "sell", "flat", form="half"), "Sale: flat (half of the paths)"),
        # a payout names itself
        (Marker(MONTH, "bav", "Company pension", 5.4), "Company pension pays 5 €"),
        (Marker(MONTH, "av", "Depot", 9, form="once"), "Depot pays 9 € at once"),
        (Marker(MONTH, "bav", "bAV", 120, form="monthly"), "bAV pays 120 € per month"),
        (
            Marker(MONTH, "pension", amount=0.8587, years=40, since=date(2040, 2, 1)),
            "Pension: 85.9% with 40 years, deferred from 2040-02",
        ),
        (Marker(MONTH, "pension", amount=1.0, years=45), "Pension: 100% with 45 years"),
        (Marker(MONTH, "savings plan", "ETF"), "Savings plan: ETF paused"),
        (Marker(MONTH, "alg1"), "ALG1: on the last salary, not on the self-employment"),
        (Marker(MONTH, "alg1 used"), "ALG1: the claim is used up"),
        (
            Marker(MONTH, "alg1 expired"),
            "ALG1: the claim arose more than four years ago (§161\u00a0Abs.\u00a02\u00a0SGB"
            "\u00a0III)",
        ),
        # the law stays on one line of the legend
        (
            Marker(MONTH, "gkv"),
            "Statutory health insurance: at 55 or older §6\u00a0Abs.\u00a03a\u00a0SGB\u00a0V "
            "usually blocks the switch",
        ),
        (
            Marker(MONTH, "exemption"),
            "ALG1 in the PKV: the plan assumes the exemption from the GKV, applied for within "
            "three months and irrevocable (§8\u00a0Abs.\u00a01\u00a0S.\u00a01\u00a0Nr.\u00a01a"
            "\u00a0SGB\u00a0V)",
        ),
    ],
)
def test_a_marker_reads_in_words(marker: Marker, shown: str) -> None:
    assert charts.readable(marker) == shown


def test_every_kind_of_marker_has_its_words() -> None:
    """The type checker holds the kinds of the engine and the types of the events in
    `MarkerKind`."""
    assert set(charts.MARKER_KINDS) == set(get_args(MarkerKind))


def test_broke_probability_figure() -> None:
    results = [_make_result("Vermietung", 1), _make_result("Verkauf", 2)]

    fig = broke_probability_figure(results).to_dict()

    assert len(fig["data"]) == len(results)
    peak = max(np.maximum.accumulate(r.broke, axis=1).mean(axis=0).max() for r in results)
    assert fig["layout"]["yaxis"]["range"] == pytest.approx([0, 1.1 * max(peak, 0.01)])
    assert fig["layout"]["yaxis"]["range"][1] < 1


def _trace_data(trace: dict[str, object], axis: str = "y") -> np.ndarray:
    """Decode a to_dict() trace's data of `axis`, which plotly may pack as {dtype, bdata}."""
    values = trace[axis]
    if isinstance(values, dict):
        return np.frombuffer(base64.b64decode(values["bdata"]), dtype=values["dtype"])
    return np.asarray(values)


def test_comparison_figure_series() -> None:
    results = [_make_result("Vermietung", 1), _make_result("Verkauf", 2)]

    fig = comparison_figure(results).to_dict()

    assert [t["name"] for t in fig["data"]] == [
        "Vermietung: net worth",
        "Vermietung: liquid",
        "Verkauf: net worth",
        "Verkauf: liquid",
    ]
    for r, total_trace, liquid_trace in zip(
        results, fig["data"][0::2], fig["data"][1::2], strict=True
    ):
        np.testing.assert_allclose(
            _trace_data(total_trace), r.percentiles(r.euros(r.total), (50,))[0]
        )
        np.testing.assert_allclose(
            _trace_data(liquid_trace), r.percentiles(r.euros(r.liquid), (50,))[0]
        )
        assert total_trace["line"].get("dash") != "dot"
        assert liquid_trace["line"]["dash"] == "dot"


@pytest.mark.parametrize("compact", [False, True])
def test_a_figure_gives_the_same_bytes_from_its_json(compact: bool) -> None:
    """The app keeps a figure as its JSON (`ui.figures`): a revisit sends the bytes of the first
    draw, which the browser still holds, so it sends their hash only."""
    a, b = _make_result("a", 1), _make_result("b", 2)
    for fig in (
        comparison_figure([a, b], compact=compact),
        broke_probability_figure([a, b], compact=compact),
        liquid_fan_figure(a, compact=compact),
        lasting_figure(a, compact=compact),
        flow_figure(a, compact=compact),
        difference_figure(Difference.of(a, b), compact=compact),
    ):
        sent = plotly.io.to_json(fig.to_dict(), validate=False)  # as Streamlit sends it
        assert plotly.io.to_json(plotly.io.from_json(fig.to_json()).to_dict()) == sent


def test_write_html_rejects_empty_results(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-empty"):
        write_html([], tmp_path / "report.html")


_TINY_LIQUID = np.array(
    [
        [100.0, 200.0, 300.0, 400.0, 500.0],
        [-50.0, -10.0, 50.0, 100.0, 200.0],
        [-1000.0, -900.0, -800.0, -700.0, -600.0],
        [10.0, 20.0, 30.0, 40.0, 50.0],
    ]
)


def _tiny_result(liquid: np.ndarray = _TINY_LIQUID, cpi: float | np.ndarray = 1.0) -> RunResult:
    months = [date(2026, 1, 1) + relativedelta(months=i) for i in range(5)]
    ages = np.array([65.0, 66.0, 67.0, 68.0, 69.0])
    care = np.array(
        [
            [False, False, True, False, False],
            [False, False, False, False, False],
            [True, False, False, False, False],
            [False, False, False, False, False],
        ]
    )
    return RunResult(
        scenario="tiny",
        model="synthetic",
        months=months,
        ages=ages,
        phases=["work"] * 5,
        liquid=liquid,
        total=liquid + 5000.0,
        income=np.zeros_like(liquid),
        expenses=np.zeros_like(liquid),
        taxes=np.zeros_like(liquid),
        capital_taxes=np.zeros_like(liquid),
        broke=liquid < 0,
        reduced=np.array([2, 0, 4, 1]),
        raised=np.array([0, 3, 0, 1]),
        care=care,
        onset=np.array([-1, 1, -1, -1]),
        em=np.zeros(4, dtype=bool),
        cpi=np.broadcast_to(cpi, liquid.shape).astype(np.float32),
        markers=[],
        survival=None,
    )


def test_summary_row_values() -> None:
    row = summary_row(_tiny_result())

    assert row.p_broke == 0.5
    assert row.median_liquid == pytest.approx(40.0)
    assert row.median_total == pytest.approx(5040.0)
    assert row.liquid_p5_zero_age == 65
    assert (row.reduced_months, row.raised_months) == (1.5, 0.5)
    assert row.p_care == pytest.approx(0.5)
    assert row.p_disability == pytest.approx(0.25)


def test_medians_come_after_the_deflation_of_each_path() -> None:
    # at 67 the totals are 5300, 5050, 4200 and 5030. The second path saw prices double.
    r = _tiny_result(cpi=np.array([[1.0], [2.0], [1.0], [1.0]]))
    assert summary_row(r).median_total == pytest.approx((4200 + 5030) / 2)
    assert summary_row(r, nominal=True).median_total == pytest.approx((5030 + 5050) / 2)


@pytest.mark.parametrize(("nominal", "shown"), [(False, "€ of 2026-01"), (True, "nominal €")])
def test_money_axes_and_titles_name_their_unit(tmp_path: Path, nominal: bool, shown: str) -> None:
    r = _make_result("Vermietung", 1)
    content = write_html([r], tmp_path / "report.html", nominal=nominal).read_text("utf-8")
    assert f"<h2>Summary in {shown}:" in content
    assert f"Summary in {shown}:" in str(console_table([r], nominal=nominal).title)
    figures = [
        comparison_figure([r], nominal=nominal),
        liquid_fan_figure(r, nominal=nominal),
        flow_figure(r, nominal=nominal),
    ]
    assert all(shown in f.to_dict()["layout"]["yaxis"]["title"]["text"] for f in figures)


def test_median_taxes_sum_each_path_in_its_own_euros() -> None:
    r = dataclasses.replace(
        _tiny_result(cpi=np.array([[1.0], [1.0], [1.0], [3.0]])),
        taxes=np.full((4, 5), -100.0),
        capital_taxes=np.repeat([[0.0], [0.0], [-200.0], [-200.0]], 5, axis=1),
    )
    assert summary_row(r, nominal=True).median_taxes == pytest.approx((500 + 1500) / 2)
    assert summary_row(r).median_taxes == pytest.approx(500)


def test_summary_row_liquid_p5_zero_age_never() -> None:
    liquid = np.full((4, 5), 100.0) + np.arange(4).reshape(4, 1)
    row = summary_row(_tiny_result(liquid=liquid))

    assert row.liquid_p5_zero_age is None
    assert summary_table([_tiny_result(liquid=liquid)])[0]["Liquid p5<0"] == "never"
    assert row.shortfall is None


def test_broke_while_alive_counts_each_path_with_its_survival() -> None:
    liquid = _TINY_LIQUID.copy()
    liquid[3, 4] = -20.0  # the fourth path goes broke in the last month
    plain = _tiny_result(liquid)
    alive = dataclasses.replace(plain, survival=np.array([1.0, 0.9, 0.8, 0.7, 0.6]))

    assert plain.p_broke_alive() == plain.p_broke_by_age(69) == 0.75
    assert alive.p_broke_alive() == pytest.approx((1.0 + 1.0 + 0.6) / 4)


def test_shortfall_is_the_fall_before_death_in_euros_of_the_start() -> None:
    liquid = np.array([[-100.0, -100.0, -100.0, -5000.0, -5000.0], *[[10.0] * 5] * 3])
    plain = _tiny_result(liquid, cpi=np.array([1.0, 1.0, 1.0, 2.0, 2.0]))
    dead_by_the_fall = dataclasses.replace(plain, survival=np.array([1.0, 1.0, 1.0, 0.0, 0.0]))

    assert plain.shortfall() == 2500.0
    assert plain.shortfall(nominal=True) == 5000.0
    assert dead_by_the_fall.shortfall() == 100.0


def test_figures_group_thousands_like_format_eur() -> None:
    r = _make_result("base", 1)
    months = [(date(2026, 1, 1), {"liquid": 10.0}), (date(2026, 2, 1), {"liquid": 12.0})]
    for fig in (liquid_fan_figure(r), flow_figure(r), history_figure(months, labels=16)):
        layout = fig.to_dict()["layout"]
        assert layout["separators"] == ".."
        assert layout["yaxis"]["tickformat"] == ",.0f"


def test_balance_figure_stacks_assets_up_and_debts_down() -> None:
    r = _make_result("base", 1)
    r.nominal_balance = {
        name: np.full(MONTHS, 1000.0 * (i + 1)) for i, name in enumerate(BALANCE_CLASSES)
    }
    r.nominal_balance["loans"] *= -1
    r.nominal_balance["latent_tax"] *= -1
    r.balance = {name: values / 2 for name, values in r.nominal_balance.items()}
    # the consumer prices rose 2% from 2025-07 to the start in 2026-01
    records = Observed(
        [(date(2025, 7, 1), 250_000.0), (date(2026, 1, 1), 300_000.0)],
        lambda day: 100.0 if day < date(2026, 1, 1) else 102.0,
    )
    fig = balance_figure(r, records, nominal=True).to_dict()

    traces = {t["name"]: t for t in fig["data"] if t.get("name")}
    classes = [t for t in fig["data"] if "stackgroup" in t]
    assert [t["stackgroup"] for t in classes] == ["owned"] * 7 + ["owed"] * 2
    assert len({t["line"]["color"] for t in classes}) == 9
    # opaque: a translucent fill blends with the surface, and neighbors look alike
    assert all(t["fillcolor"] == t["line"]["color"] for t in classes)
    observed = traces["net worth (observed)"]
    # two snapshots six months apart: a gap after the first, so no line joins them
    assert list(observed["x"]) == pytest.approx([48.5, 48.5 + 1 / 12, 49.0])
    assert list(observed["y"]) == [250_000.0, None, 300_000.0]
    assert "net worth (observed)" not in {
        t.get("name") for t in balance_figure(r, None).to_dict()["data"]
    }
    # in euros of the start (2026-01) the earlier observation grows with the consumer prices
    real = {t["name"]: t for t in balance_figure(r, records).to_dict()["data"] if t.get("name")}
    assert _trace_data(real["cash"])[0] == _trace_data(traces["cash"])[0] / 2
    assert list(real["net worth (observed)"]["y"]) == pytest.approx([255_000.0, None, 300_000.0])
    r.balance["gold"] = np.zeros(MONTHS)  # a plan without gold: no legend entry
    assert "gold" not in {t.get("name") for t in balance_figure(r, None).to_dict()["data"]}


def test_sunburst_rings_add_up_and_inherit_colors() -> None:
    slices = [
        Slice(("wohnen", "Miete"), 900.0),
        Slice(("wohnen", "Strom"), 90.4),
        Slice(("medien", "Abo"), 12.0),
        Slice(("medien", "Alt"), 0.0),
    ]
    trace = sunburst_figure("expenses", slices, {("wohnen",): "#aaaaaa"}).to_dict()["data"][0]
    assert list(trace["labels"]) == ["expenses", "wohnen", "Miete", "Strom", "medien", "Abo"]
    assert list(trace["parents"]) == ["", "root", "0", "0", "root", "3"]
    assert list(trace["values"]) == [100240, 99040, 90000, 9040, 1200, 1200]
    assert trace["text"][0] == "1.002 €"
    assert trace["branchvalues"] == "total"
    assert list(trace["marker"]["colors"]) == [
        "rgba(0,0,0,0)",
        *["#aaaaaa"] * 3,
        NEUTRAL,
        NEUTRAL,
    ]


def test_bars_put_the_largest_on_top_and_inherit_colors() -> None:
    slices = [
        Slice(("gehalt", "Bonus"), 500.0),
        Slice(("gehalt", "Gehalt"), 9000.0),
        Slice(("gehalt", "Alt"), 0.0),
        Slice(("sonstiges", "Miete"), 700.0),
    ]
    trace = bars_figure(slices, {("gehalt",): "#aaaaaa"}).to_dict()["data"][0]
    assert list(trace["y"]) == ["Bonus", "Miete", "Gehalt"]  # plotly draws the first at the bottom
    assert list(trace["marker"]["color"]) == ["#aaaaaa", NEUTRAL, "#aaaaaa"]


@pytest.mark.parametrize(("compact", "cut"), [(False, False), (True, True)])
def test_bars_start_at_one_x_and_wrap_a_long_label(compact: bool, cut: bool) -> None:
    """The labels take a fixed room, so stacked charts share the origin of their bars. A label
    too long for it breaks at a space onto a second line, only a longer one is cut, and its bar
    keeps the full name for the hover and the pick."""
    long = "Employer contribution to the company pension plan"
    short, wrapped = (
        bars_figure([Slice(("a", name), 10.0)], {}, compact=compact).to_dict()
        for name in ("x", long)
    )
    assert short["layout"]["margin"]["l"] == wrapped["layout"]["margin"]["l"]
    assert list(wrapped["data"][0]["y"]) == [long]
    (label,) = wrapped["layout"]["yaxis"]["ticktext"]
    first, second = label.split("<br>")
    assert max(len(first), len(second)) <= LABEL_ROOM[compact] / LABEL_CHAR
    assert second.endswith("…") is cut
    assert long.startswith(f"{first} {second.removesuffix('…')}")


def test_signed_bars_keep_the_negative_slices_in_range() -> None:
    slices = [Slice(("a",), -30.0), Slice(("b",), 0.2), Slice(("c",), 10.0)]
    fig = bars_figure(slices, {}, signed=True).to_dict()
    assert list(fig["data"][0]["y"]) == ["a", "c"]
    assert list(fig["data"][0]["text"]) == ["-30 €", "+10 €"]
    low, high = fig["layout"]["xaxis"]["range"]
    assert low < -30 and high > 10  # room for the values beside the bars
    # a month saved as planned leaves no bar
    assert bars_figure(slices[1:2], {}, signed=True).to_dict()["layout"]["xaxis"]["range"] == [0, 0]


def test_spend_figure_shows_spending_upwards() -> None:
    traces = spend_figure({date(2026, 8, 1): Line(-100.0, -120.0)}, labels=8).to_dict()["data"]
    assert [(t["name"], list(t["y"])) for t in traces] == [("actual", [120.0]), ("plan", [100.0])]


MONTH_AXES = {  # months, labels that fit, the step between labels
    "short": (2, 20, "M1"),
    "as many as fit": (20, 20, "M1"),
    "one more": (21, 20, "M2"),
    "a year on a phone": (12, 5, "M3"),
}


@pytest.mark.parametrize(("count", "labels", "dtick"), MONTH_AXES.values(), ids=MONTH_AXES.keys())
def test_month_axes_label_the_last_month_and_no_more_than_fit(
    count: int, labels: int, dtick: str
) -> None:
    months = [date(2026, 1, 1) + relativedelta(months=i) for i in range(count)]
    track = track_figure(Band(months, *np.zeros((3, count))), [], "total", labels=labels)
    for fig in (
        history_figure([(month, {"liquid": 1.0}) for month in months], labels=labels),
        spend_figure(dict.fromkeys(months, Line(-1.0, -1.0)), labels=labels),
        track,
    ):
        axis = fig.to_dict()["layout"]["xaxis"]
        assert (axis["dtick"], axis["tick0"]) == (dtick, months[-1])
    low, high = track.to_dict()["layout"]["xaxis"]["range"]
    assert low < months[0] and high > months[-1]  # without bars, room for the end labels


def test_track_figure_draws_an_empty_band() -> None:
    nothing = np.array([])
    fig = track_figure(Band([], nothing, nothing, nothing), [], "total", labels=16)
    assert "dtick" not in fig.to_dict()["layout"]["xaxis"]


def test_history_figure_stacks_groups_under_net_worth() -> None:
    months = [
        (date(2026, 1, 1), {"liquid": 10.0, "debt": -4.0}),
        (date(2026, 2, 1), {"liquid": 12.0, "illiquid": 5.0, "debt": -4.0}),
    ]
    traces = history_figure(months, labels=16).to_dict()["data"]
    assert [t["name"] for t in traces] == ["liquid", "illiquid", "debt", "net worth"]
    assert list(traces[1]["y"]) == [0.0, 5.0]
    assert list(traces[3]["y"]) == [6.0, 13.0]
    r = _make_result("base", 1)
    r.balance = {name: np.ones(MONTHS) for name in BALANCE_CLASSES}
    balance = {t.get("name"): t for t in balance_figure(r, None).to_dict()["data"]}
    assert traces[2]["marker"]["color"] == balance["loans"]["line"]["color"]  # debt looks alike
    assert traces[3]["line"]["color"] == balance["net worth (median)"]["line"]["color"]


def test_records_far_apart_draw_no_line_between_them() -> None:
    """Two snapshots a year apart: bars a month wide, a marker each without a line between them,
    in the history and against the plan."""
    records = [(date(2025, 1, 1), 10.0), (date(2026, 1, 1), 12.0)]
    history = history_figure([(m, {"liquid": v}) for m, v in records], labels=16).to_dict()
    assert history["data"][0]["width"] == MONTH_BAR
    nothing = np.array([])
    track = track_figure(Band([], nothing, nothing, nothing), records, "total", labels=16)
    for trace in (history["data"][3], track.to_dict()["data"][3]):
        assert list(trace["y"]) == [10.0, None, 12.0]


@pytest.mark.parametrize(("until", "months"), [(date(2026, 3, 1), 3), (date(2031, 1, 1), 5)])
def test_band_ends_at_its_month_or_at_the_run(until: date, months: int) -> None:
    r = _tiny_result(cpi=np.linspace(1.0, 1.1, 5))
    band = Band.of(r, r.total, until)
    assert band.months == r.months[:months]
    assert band.median == pytest.approx(np.median(r.total[:, :months], axis=0))  # not deflated
    assert (band.low <= band.median).all()
    assert (band.median <= band.high).all()


def test_a_twin_takes_the_color_of_its_scenario_dashed_and_lighter() -> None:
    results = [_make_result("a", 1), _make_result("b", 2)]
    results += [dataclasses.replace(r, twin=True) for r in results]
    for fig in (comparison_figure(results), broke_probability_figure(results)):
        traces = fig.to_dict()["data"]
        runs, twins = traces[: len(traces) // 2], traces[len(traces) // 2 :]
        assert [t["line"]["color"] for t in runs] == [t["line"]["color"] for t in twins]
        assert len({t["line"]["color"] for t in runs}) == 2
        assert all(t["opacity"] == 1 for t in runs) and all(t["opacity"] < 1 for t in twins)
        assert [t["showlegend"] for t in traces] == [True] * len(runs) + [False] * len(twins)
    lines = [t["line"] for t in comparison_figure(results).to_dict()["data"]]
    assert [line["dash"] for line in lines] == ["solid", "dot"] * 2 + ["dash", "dashdot"] * 2
