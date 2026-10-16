"""The Cashflows page: the sheet from the run, the bars of the outflows, the ALG1
estimate, the columns of the page style."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pytest
from apps import reach_every_phase
from builders import PHASE_LABELS, PHASES, phases, plan
from german import edited, leaks
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from dagobert import budget, i18n
from dagobert.budget import Budget
from dagobert.model.assets import PensionPolicy
from dagobert.model.assumptions import PhaseSpec
from dagobert.model.months import add_months
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.report import tracker
from dagobert.result import CONVERSION, LOAN_PRINCIPAL
from dagobert.sv import alg1_month
from dagobert.tax import for_year
from dagobert.ui import bars, cashflows, gridcolumns
from dagobert.ui.refusals import refusals

OUTFLOWS = """
from dagobert.report.tracker import Slice
from dagobert.ui import bars
bars.outflow_bars(
    [Slice(("wohnen", "Miete"), 500.0), Slice(("wohnen", "Strom"), 80.0)]
    + [Slice(("taxes & SV", "income tax"), 900.0)],
    {},
    key="outflows",
    scope="in `work`",
    unit="per month",
)
"""


def test_a_phone_picks_outflows_with_pills_and_shows_them_above_the_bars() -> None:
    def drawn() -> list[tuple[list[str], bool]]:  # the labels from the bottom, and a click picks
        return [
            (json.loads(c.proto.spec)["data"][0]["y"], bool(c.proto.selection_mode))
            for c in at.get("plotly_chart")
        ]

    at = AppTest.from_string(OUTFLOWS)
    at.query_params["mobile"] = "0"
    assert not at.run().pills
    assert drawn() == [(["wohnen", "taxes & SV"], True)]

    at.query_params["mobile"] = "1"
    at.run()
    assert at.pills[0].options == ["taxes & SV", "wohnen"]  # the largest first, like the bars
    assert drawn() == [(["wohnen", "taxes & SV"], False)]  # no click: a swipe over it scrolls
    at.pills[0].set_value("wohnen").run()
    assert drawn() == [(["Strom", "Miete"], False), (["wohnen", "taxes & SV"], False)]
    scrolls = [h for h in at.get("html") if "scrollIntoView" in h.proto.body]
    assert len(scrolls) == 1  # a new pick scrolls its streams into view
    assert not [h for h in at.run().get("html") if "scrollIntoView" in h.proto.body]  # once


CASHFLOWS = """
from pathlib import Path
from dagobert.store import streams_file
from dagobert.ui import cashflows
cashflows.page(streams_file(Path({data!r})))
"""


def test_a_tab_without_rows_takes_a_salary_in_the_phase_of_the_start(data: Path) -> None:
    """The income tab of `data` holds no row: one grid without blocks, with `cat`. Its new row is
    a salary that pays in `work`, the phase of the start, an expense in every phase. A row that
    the model refuses says why under its grid, in words, before Save."""
    at = AppTest.from_string(CASHFLOWS.format(data=str(data)), default_timeout=30).run()
    income = next(g for g in at.dataframe if g.key == "streams-income-0")
    config = json.loads(income.proto.columns)
    assert "cat" in income.value.columns
    assert config["kind"]["default"] == cashflows.FIRST_INCOME
    assert [config[f"factor {p}"]["default"] for p in PHASE_LABELS] == [1, 0, 0, 0]
    new = {"name": "Bonus", "cat": "Gehalt", "kind": "expense", "amount": 500}
    edited(at, "streams-income-0", {"added_rows": [new]})
    assert not at.exception
    assert any("**Bonus**: the kind Expense is money out" in w.value for w in at.warning)


# A row per check of the model that the grids say in words, and a bound of a field
REFUSED: list[gridcolumns.Row] = [
    {"kind": "salary", "gross": 1000, "amount": 900},
    {"amount": -100, "deductible": 0.5},
    {"amount": -60, "deduct": "donation", "health": "kv"},
    {"kind": "other_income", "amount": 26, "repays": "loan"},
    {"amount": -60, "health": "kv", "property": "flat"},
    {"kind": "other_income", "amount": 500, "property": "flat", "taxable": False},
    {"kind": "salary", "of": "Salary"},
    {"kind": "salary", "of": "Salary", "share": 0.1, "gross": 1},
    {"kind": "alg1", "training": True, "sperrzeit": True},
    {"kind": "bu", "amount": 1000, "every": 12},
    {"kind": "pension"},
    {"kind": "salary"},
    {"amount": 100},
    {"kind": "bu", "amount": -1},
    {"kind": "salary", "of": "Salary", "share": 2},
    {"kind": "expense", "amount": -100, "start": "soon"},
]


@pytest.mark.parametrize("lang", ["en", "de"])
def test_a_refused_stream_says_which_field_and_what_to_enter(lang: i18n.Language) -> None:
    """Each check of `Stream` by its type, in the language of the session, never the English of
    the model, which the command line keeps."""
    rows = [{"name": f"s{n}"} | row for n, row in enumerate(REFUSED)]
    with i18n.use(lang):
        said = refusals(rows, {"amount": "Monthly benefit €"})
    assert [line.split("**")[1] for line in said] == [row["name"] for row in rows]
    for row, line in zip(rows, said, strict=True):
        with pytest.raises(ValidationError) as caught:
            Stream.model_validate(row)
        assert caught.value.errors()[0]["msg"].removeprefix(f"{row['name']}: ") not in line
    assert said[12] == (
        "**s12**: the kind Expense is money out: enter `Monthly benefit €` with a minus, or choose "
        "another kind"
        if lang == "en"
        else "**s12**: Die Art Ausgabe gibt Geld aus: Gib `Monatliche BU-Rente €` mit Minus ein "
        "oder wähle eine andere Art"
    )
    assert lang == "en" or leaks(said) == []
    with i18n.use(lang):
        (nameless,) = refusals([{"kind": "expense", "amount": -100}])
    assert nameless == (
        "**new row**: enter `name`" if lang == "en" else "**neue Zeile**: Gib `Name` ein"
    )


def test_a_savings_plan_without_an_index_is_nominal_in_its_help() -> None:
    """The schema names `cpi` as the default of `index`, which a savings plan does not take."""
    [index] = [c for c in cashflows.SAVINGS.columns() if c.name == "index"]
    assert "nominal" in index.help
    assert "default cpi" not in index.help


def test_the_columns_stand_where_the_page_style_finds_them(data: Path) -> None:
    """`ui/page.css` finds `change` by its place from the start, before the phases: it wraps,
    the cells after it keep one line. A column per phase, headed by its label, in the sheet after
    the category: its sixth header cell is a fifth phase, which scrolls it sideways in portrait."""
    reach_every_phase(data / "scenarios" / "base.yaml")
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write(f"    end: {add_months(date.today(), 3)}\n")
    at = AppTest.from_string(CASHFLOWS.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    changes = next(t.value for t in at.table if "change" in t.value.columns)
    assert list(changes.columns) == [
        "stream",
        "date",
        "change",
        *PHASE_LABELS.values(),
    ]
    sheet = next(t.value for t in at.table if "category" in t.value.columns)
    assert list(sheet.columns) == ["category", *PHASE_LABELS.values()]


def test_the_alg1_estimate_takes_the_tax_year_of_the_scenario(
    later_tax_year: Callable[..., int],
) -> None:
    rows: list[gridcolumns.Row] = [
        {"name": "Gehalt", "cat": "gehalt", "kind": "salary", "gross": 5000},
        {"name": "ALG", "cat": "gehalt", "kind": "alg1", "phases": ["unemployed"]},
    ]
    now = for_year(2026)
    later = later_tax_year(alg1_rate_base=now.alg1_rate_base / 2)
    before, after = (
        cashflows.estimated(rows, date(2026, 3, 1), plan([], [], tax={"year": year}))
        for year in (now.year, later)
    )
    assert after[1]["amount"] == pytest.approx(before[1]["amount"] / 2)
    assert after[0] == before[0]


def test_the_alg1_estimate_takes_the_last_salary_before_the_claim() -> None:
    """As the engine: after a change of jobs the salary of the new one, on any date. A course
    beside the ALG1 row, in every phase by its dates, starts no claim and pays nothing of its
    own: the claim pays once."""
    rows: list[gridcolumns.Row] = [
        {"name": "Old", "cat": "gehalt", "kind": "salary", "gross": 4000, "phases": ["old"]},
        {"name": "New", "cat": "gehalt", "kind": "salary", "gross": 6000, "phases": ["new"]},
        {"name": "ALG", "cat": "gehalt", "kind": "alg1", "phases": ["unemployed"]},
        {"name": "Kurs", "cat": "gehalt", "kind": "alg1", "training": True}
        | {"start": date(2028, 6, 1), "end": date(2028, 12, 1)},
    ]
    years = {"old": 2026, "new": 2027, "unemployed": 2028}
    scenario = Scenario(name="t", phases=phases(*((date(y, 1, 1), p) for p, y in years.items())))
    p = plan([], [], scenario, phases={name: PhaseSpec() for name in years})
    paid = {cashflows.estimated(rows, date(y, 3, 1), p)[2]["amount"] for y in years.values()}
    assert paid == {float(alg1_month(6000, for_year(p.assumptions.tax_year), child=False))}
    assert "amount" not in cashflows.estimated(rows, date(2028, 7, 1), p)[3]


@pytest.mark.parametrize(
    ("policy", "salary"),
    [
        ({}, 4800),
        ({"matures": date(2026, 12, 1)}, 5000),  # matured by the last salary before the claim
        ({"salary": "Nebenjob"}, 5000),  # converts a salary that does not pay then
    ],
)
def test_the_alg1_estimate_takes_the_salary_less_its_conversion(
    policy: dict[str, object], salary: float
) -> None:
    """As the engine: the contributory salary (§151 Abs. 1 SGB III), which a salary conversion
    that pays in the month lowers by its part free of SV."""
    rows: list[gridcolumns.Row] = [
        {"name": "Gehalt", "cat": "gehalt", "kind": "salary", "gross": 5000, "phases": ["work"]},
        {"name": "Nebenjob", "cat": "gehalt", "kind": "salary", "gross": 900, "phases": ["alt"]},
        {"name": "ALG", "cat": "gehalt", "kind": "alg1", "phases": ["unemployed"]},
    ]
    bav = PensionPolicy.model_validate(
        {
            "id": "bav",
            "kind": "bav",
            "value": 0,
            "conversion": 200,
            "phases": ["work"],
            "matures": date(2040, 1, 1),
            "growth": "cash",
        }
        | policy
    )
    scenario = Scenario(name="t", phases=phases((date(2027, 1, 1), "unemployed")))
    side = Stream(name="Nebenjob", kind=StreamKind.SALARY, gross=900, phases=["alt"])
    p = plan([side], [bav], scenario)
    [*_, alg] = cashflows.estimated(rows, date(2026, 3, 1), p)
    ty = for_year(p.assumptions.tax_year)
    assert alg["amount"] == pytest.approx(float(alg1_month(salary, ty, child=False)))


def test_the_cashflows_show_the_phases_that_the_scenario_reaches() -> None:
    """As the Flows page: a phase that the scenario never switches to has no column."""
    changes = phases((date(2026, 1, 1), "work"), (date(2040, 1, 1), "retired"))
    reaches = plan([], [], Scenario(name="s", phases=changes))
    assert bars.reached(reaches) == {"work": "Work", "retired": "Retired"}


def test_sheet_adds_what_the_run_pays_and_the_bars_cover_it() -> None:
    rows: list[gridcolumns.Row] = [
        {"name": "Gehalt", "cat": "gehalt", "kind": "salary", "gross": 5000},
        {"name": "Miete", "cat": "wohnen", "amount": -900},
    ]
    day = date(2026, 3, 1)
    run = Budget(
        {"PKV subsidy": 300.0},
        {"income tax": 1200.0},
        {LOAN_PRINCIPAL: {"haus": 400.0}},
        {"equity": 700.0, "cash": 10.0},
    )
    lines = {
        label: amounts
        for label, amounts, _ in cashflows.sheet_lines(rows, day, {"work": run}, list(PHASES))
    }
    assert lines["surplus"]["work"] == 5000 - 900 + 300 - 1200 - 400
    # below the surplus, not part of it
    assert list(lines)[-2:] == ["surplus", "non-cash income"]
    assert lines["non-cash income"] == {
        "work": 710,
        "unemployed": None,
        "alt": None,
        "retired": None,
    }
    assert lines[bars.RUN]["work"] == 300 - 1200 - 400
    assert (lines[budget.TAXES]["work"], lines[LOAN_PRINCIPAL]["work"]) == (-1200, -400)
    # a phase that the run does not reach keeps the plan, but has no surplus
    assert lines["expenses"]["retired"] == -900
    assert lines[budget.TAXES]["retired"] is None and lines["surplus"]["retired"] is None
    outflows = bars.flows_of(rows, day, "work", run, income=False)
    assert sum(s.value for s in outflows) == 900 + 1200 + 400
    assert {s.path for s in outflows} == {
        ("wohnen", "Miete"),
        (budget.TAXES, "income tax"),
        (LOAN_PRINCIPAL, "haus"),
    }
    income = bars.flows_of(rows, day, "work", run, income=True)
    assert sum(s.value for s in income) == 5000 + 300


CHARTS = """
from datetime import date
from dagobert.budget import Budget
from dagobert.result import CONVERSION, LOAN_INTEREST, LOAN_PRINCIPAL
from dagobert.ui import bars
rows = [
    {"name": "Gehalt", "cat": "gehalt", "kind": "salary", "gross": 5000},
    {"name": "Miete", "cat": "wohnen", "amount": -900},
]
run = Budget(
    {"PKV subsidy": 300.0},
    {"income tax": 1200.0},
    {LOAN_PRINCIPAL: {"haus": 400.0}, LOAN_INTEREST: {"haus": 100.0}, CONVERSION: {"bav": 200.0}},
    # cash below zero costs its rate, the employer pays into a policy
    {"equity": 800.0, "Gehalt": 50.0, "cash": -20.0, "bav: employer": 100.0},
)
for draw in (bars.outflows_chart, bars.income_chart):
    draw(rows, date(2026, 3, 1), "work", ("per month", 1), run, key=draw.__name__, label="Job")
"""


def test_the_bars_set_apart_what_stays_in_net_worth() -> None:
    at = AppTest.from_string(CHARTS)
    at.query_params["mobile"] = "0"
    at.run()
    assert not at.exception
    outflows, income = (m.value for m in at.markdown)
    assert outflows == (
        "All outflows in `Job`: **2.800 €** per month  \n"
        "of which 600 € repays loans or goes into a company pension: stays in net worth"
    )
    assert income == (  # out of the total: no cash flow
        "All income in `Job`: **5.300 €** per month  \n"
        "plus 930 € non-cash income: growth of the assets and payments into policies, "
        "stays invested"
    )
    figures = [json.loads(c.proto.spec)["data"][0] for c in at.get("plotly_chart")]
    colors = {
        y: color
        for bar in figures
        for y, color in zip(bar["y"], bar["marker"]["color"], strict=True)
    }
    # the non-cash income below the cash income, the bar of a shrinking asset too
    assert set(figures[-1]["y"][:4]) == {"equity", "Gehalt (non-cash)", "cash", "bav: employer"}
    assert dict(zip(figures[-1]["y"], figures[-1]["x"], strict=True))["cash"] == -20
    assert {y: colors[y] for y in (budget.TAXES, LOAN_PRINCIPAL, CONVERSION, "loan interest")} == {
        budget.TAXES: bars.ROLES["taxes"],
        LOAN_PRINCIPAL: bars.ROLES["loans"],
        CONVERSION: bars.ROLES["savings"],
        "loan interest": tracker.NEUTRAL,  # a cost like the other flows of the run
    }
    # the growth of an asset named like a stream keeps a bar of its own
    held = ("equity", "Gehalt (non-cash)", "bav: employer")
    assert {y: colors[y] for y in held} == dict.fromkeys(held, bars.ROLES["savings"])
    assert colors["Gehalt"] != bars.ROLES["savings"]


KEPT = """
from dagobert.report.tracker import Slice
from dagobert.result import CONVERSION, LOAN_PRINCIPAL
from dagobert.ui import bars
bars.outflow_bars(
    [Slice(("wohnen", "Miete"), 500.0), Slice((LOAN_PRINCIPAL, "haus"), {loans})]
    + [Slice((CONVERSION, "bav"), {converted})],
    {{}},
    key="outflows",
    scope="in `work`",
    unit="per month",
)
"""


@pytest.mark.parametrize(
    ("loans", "converted", "line"),
    [
        # neither part rounds to a euro, their sum does
        (0.4, 0.4, "of which 1 € repays loans or goes into a company pension: stays in net worth"),
        (
            0.3,
            200.0,
            "of which 200 € is salary conversion into a company pension: stays in net worth",
        ),
        (0.4, 0.0, ""),
    ],
)
def test_the_line_under_the_outflows_names_the_parts_of_its_amount(
    loans: float, converted: float, line: str
) -> None:
    at = AppTest.from_string(KEPT.format(loans=loans, converted=converted))
    at.query_params["mobile"] = "0"
    assert at.run().markdown[0].value.partition("  \n")[2] == line
