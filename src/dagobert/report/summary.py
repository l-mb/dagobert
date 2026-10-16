"""The summary of runs: the numbers of each run (`SummaryRow`) and its columns (`COLUMNS`), which
the report, the explorer and the tiles of the Overview show, the difference of two runs as a
table, and the console summary."""

from __future__ import annotations

import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from babel.lists import format_list
from rich import box
from rich.console import Console
from rich.table import Table

from dagobert import i18n
from dagobert.difference import SPREAD, Difference
from dagobert.i18n import N_, _, ngettext
from dagobert.money import format_eur
from dagobert.report.charts import RUN_OUT, points
from dagobert.result import BROKE_AGE, MEDIAN_AGE, TOTAL_AGES, BoolArray, IntArray, RunResult

CONSOLE_WIDTH = 120
HEADER_LINE = 9  # characters of a line of a console header: no wider than `1.234.567`
DIFFERENCE_NOTE = N_(
    "The table and the chart take B less A on each path, then the median and the 5th and 95th "
    "percentile over the paths. Both runs use the same random draws on every path: returns, "
    "inflation, indices, care episodes and sale prices. So the difference shows the effect of "
    "the plan, not of luck. The onsets of a disability pair up the same way. A scenario that "
    "changes a spread changes the draws of that item "
    "only. A positive value means that B has more, or that B pays more tax. Broke means liquid "
    "net worth below zero. The last two rows count the paths that are broke in one run but not "
    "in the other."
)
# the help of a measure of runs that take it at different ages (`RunResult.age_at`)
APART = N_("Where a run does not reach {age}, its first or last age counts instead: {runs}.")


@dataclass
class SummaryRow:
    scenario: str
    p_broke: float  # by `BROKE_AGE`
    p_broke_alive: float
    shortfall: float | None
    median_total: float
    median_liquid: float
    median_taxes: float
    liquid_p5_zero_age: float | None  # None: never
    reduced_months: float
    raised_months: float
    p_care: float
    p_disability: float


def summary_row(r: RunResult, *, nominal: bool = False) -> SummaryRow:
    p5 = r.percentiles(r.euros(r.liquid, nominal=nominal), (5,))[0]
    below = np.flatnonzero(p5 < 0)
    return SummaryRow(
        scenario=r.label,
        p_broke=r.p_broke_by_age(BROKE_AGE),
        p_broke_alive=r.p_broke_alive(),
        shortfall=r.shortfall(nominal=nominal),
        median_total=r.median_at_age(r.euros(r.total, nominal=nominal), MEDIAN_AGE),
        median_liquid=r.median_at_age(r.euros(r.liquid, nominal=nominal), MEDIAN_AGE),
        median_taxes=float(np.median(r.taxes_paid(nominal=nominal).sum(axis=1))),
        liquid_p5_zero_age=float(r.ages[below[0]]) if below.size else None,
        reduced_months=float(np.median(r.reduced)),
        raised_months=float(np.median(r.raised)),
        p_care=_alive_at(r, r.care.any(axis=1), r.care.argmax(axis=1)),
        p_disability=_alive_at(r, r.onset >= 0, np.maximum(r.onset, 0)),
    )


def _alive_at(r: RunResult, has: BoolArray, month: IntArray) -> float:
    """Share of the paths that `has` an event, each weighted by the survival to its `month`."""
    if r.survival is None:
        return float(has.mean())
    return float(np.where(has, r.survival[month], 0.0).mean())


Cell = Callable[[SummaryRow, bool], str]  # the text of a value, with ` €` by the `bool`


def _share(value: Callable[[SummaryRow], float]) -> Cell:
    return lambda row, _symbol: f"{value(row):.0%}"


def _euros(value: Callable[[SummaryRow], float | None]) -> Cell:
    """A dash for none: no life runs out."""
    return lambda row, symbol: "–" if (v := value(row)) is None else format_eur(v, symbol=symbol)


Change = Callable[[SummaryRow, SummaryRow], str | None]  # mine against the files, for brackets


def _change(
    value: Callable[[SummaryRow], float | None],
    show: Callable[[float], str],
    plain: Callable[[float], str],
    absent: str,
) -> Change:
    """The difference of a value from the run of the files by `show`. Where one side is None, the
    value of the files in words (`absent` for none, else `plain`); None where both are."""

    def change(mine: SummaryRow, files: SummaryRow) -> str | None:
        a, b = value(mine), value(files)
        if a is not None and b is not None:
            return show(a - b)
        if a is b:
            return None
        return _("as saved: {value}").format(value=plain(b) if b is not None else _(absent))

    return change


def _share_change(value: Callable[[SummaryRow], float]) -> Change:
    return _change(value, points, lambda v: f"{v:.0%}", "")


def _euros_change(value: Callable[[SummaryRow], float | None]) -> Change:
    return _change(value, lambda d: format_eur(d, signed=True), format_eur, N_("none"))


def _years(delta: float) -> str:
    return ngettext("{n} year", "{n} years", abs(round(delta))).format(n=f"{delta:+.0f}")


def _months(delta: float) -> str:
    return ngettext("{n} month", "{n} months", abs(round(delta))).format(n=f"{delta:+.0f}")


@dataclass(frozen=True)
class Column:
    """A column of the summary. `name` is its term in the report, with `{age}` the age of its
    measure (`age`). `header` (the plain words of the tiles of the Overview, `{age}` the age) and
    `help` (the meaning first, then how it is counted) are messages of the catalogue; `unmortal`
    follows the help for a run without the life table. `console` keeps it in the console summary,
    whose 120 columns hold eleven, the scenario among them."""

    name: str
    header: str
    help: str
    cell: Cell
    unmortal: str = ""
    age: int = 0
    console: bool = True
    change: Change | None = None  # the difference from the run of the files, in brackets

    @property
    def term(self) -> str:
        """The key of the column in a row: `P(broke)@90`."""
        return self.name.format(age=self.age)


BROKE = Column(
    "P(broke)@{age}",
    RUN_OUT,
    N_(
        "The chance to run out of money by age {broke}: the share of the simulated futures "
        "(paths) in which the liquid money (cash, deposits, funds, shares) falls below zero at or "
        "before {broke}, alive or not. Property does not count as liquid. The goal seek and the "
        "sensitivity charts of the Explorer use this figure, the chart of the chance by age shows "
        "every age."
    ),
    _share(lambda row: row.p_broke),
    age=BROKE_AGE,
    change=_share_change(lambda row: row.p_broke),
)
ALIVE = Column(
    "P(broke) alive",
    N_("Chance to run out, lifetime"),
    N_(
        "The chance to run out of money while you are alive: each path counts with the chance to "
        "be alive in its first month without money (Destatis life table)."
    ),
    _share(lambda row: row.p_broke_alive),
    N_(
        "A run without the life table (`--no-mortality`) counts every path in full, as if the "
        "person lived to {end}."
    ),
    change=_share_change(lambda row: row.p_broke_alive),
)
TOTAL = Column(
    "Total@{age}",
    N_("Net worth at {age}"),
    N_(
        "What you own at {median}, less your debts, in the median path: liquid assets plus "
        "property and pension policies minus loans, {money}."
    ),
    _euros(lambda row: row.median_total),
    age=MEDIAN_AGE,
    change=_euros_change(lambda row: row.median_total),
)
COLUMNS = (
    Column(
        "Scenario",
        N_("Scenario"),
        N_("The name of the scenario."),
        lambda row, _symbol: row.scenario,
    ),
    BROKE,
    ALIVE,
    Column(
        "Shortfall",
        N_("Typical shortfall"),
        N_(
            "How deep the money falls below zero before death, in the lives that run out: the "
            "median of the lowest liquid value up to death, each path and age of death weighted "
            "by the chance to die then, {money}. A dash means that no life runs out."
        ),
        _euros(lambda row: row.shortfall),
        N_(
            "A run without the life table takes the lowest value of each path that runs out up to "
            "{end}."
        ),
        change=_euros_change(lambda row: row.shortfall),
    ),
    TOTAL,
    Column(
        "Liquid@{age}",
        N_("Liquid at {age}"),
        N_(
            "The money you can use at {median} in the median path: cash, deposits, fixed income "
            "and shares, after the tax on unrealized gains, {money}."
        ),
        _euros(lambda row: row.median_liquid),
        age=MEDIAN_AGE,
        change=_euros_change(lambda row: row.median_liquid),
    ),
    Column(
        "Taxes",
        N_("Taxes"),
        N_(
            "The taxes of the whole life in the median path: income tax, Soli, social insurance "
            "and capital gains tax from the start to age {end}, less refunds, {money}."
        ),
        _euros(lambda row: row.median_taxes),
        change=_euros_change(lambda row: row.median_taxes),
    ),
    Column(
        "Liquid p5<0",
        N_("1 in 20 runs out at"),
        N_(
            "The first age at which one path in twenty has run out of money: the 5th percentile of "
            "liquid net worth falls below zero. `never` when it does not."
        ),
        lambda row, _symbol: (
            _("never") if (age := row.liquid_p5_zero_age) is None else f"{age:.0f}"
        ),
        change=_change(
            lambda row: row.liquid_p5_zero_age, _years, lambda v: f"{v:.0f}", N_("never")
        ),
    ),
    Column(
        "Cuts",
        N_("Months of cuts"),
        N_(
            "The months in which the spending rule cut the flexible spending, in the median path. "
            "Under VPW the months at the floor: the rate of the wealth alone would have spent "
            "less."
        ),
        lambda row, _symbol: f"{row.reduced_months:.0f}",
        change=_change(lambda row: row.reduced_months, _months, lambda v: f"{v:.0f}", ""),
    ),
    Column(
        "Raises",
        N_("Months of raises"),
        N_(
            "The months in which the spending rule raised the flexible spending, in the median "
            "path. Under VPW the months above the plan of the flexible categories."
        ),
        lambda row, _symbol: f"{row.raised_months:.0f}",
        change=_change(lambda row: row.raised_months, _months, lambda v: f"{v:.0f}", ""),
    ),
    Column(
        "P(care)",
        N_("Chance of care"),
        N_(
            "The chance to need long-term care during your life: the paths with a care episode, "
            "each weighted by the chance to be alive at its start. A `fixed` run draws none."
        ),
        _share(lambda row: row.p_care),
        change=_share_change(lambda row: row.p_care),
    ),
    Column(
        "P(disability)",
        N_("Chance of disability"),
        N_(
            "The chance to lose the ability to work before the statutory pension age: the paths "
            "with the onset of a full Erwerbsminderung, each weighted by the chance to be alive "
            "then. A `fixed` run draws none, but a forced month."
        ),
        _share(lambda row: row.p_disability),
        console=False,
        change=_share_change(lambda row: row.p_disability),
    ),
)
# the terms of the summary that the explorer strip and the tiles of the Overview show
BROKE_AT, BROKE_ALIVE, TOTAL_AT = BROKE.term, ALIVE.term, TOTAL.term


@dataclass(frozen=True)
class Shown:
    """A column of the summary of some runs, in the language of the page: its plain header and its
    help, the term of the report first where the English header differs from it."""

    term: str
    label: str
    tip: str


def taken_at(results: Sequence[RunResult], age: int) -> tuple[int, str]:
    """The age that names a measure at `age`: the one that every run takes it at
    (`RunResult.age_at`), else `age` and a sentence that names the runs at another age. The
    summary and the target of the goal seek."""
    at = [(r.label, r.age_at(age)) for r in results]
    if len(ages := {a for _label, a in at}) == 1:
        return ages.pop(), ""
    runs = [f"{label} ({a})" for label, a in at if a != age]
    return age, _(APART).format(age=age, runs=format_list(runs, locale=i18n.language()))


def summary_columns(results: list[RunResult], *, nominal: bool = False) -> list[Shown]:
    """The columns of the summary of `results`. The summary title or the caption of the table
    names the unit of money, the help of a column the unit too. A measure names the age that the
    runs take it at (`taken_at`): `by 80` where every run ends at 80, its key stays."""
    money = (
        _("in nominal euros")
        if nominal
        else _("in euros of {month}, each path deflated by its own consumer prices").format(
            month=f"{results[0].months[0]:%Y-%m}"
        )
    )
    taken = {age: taken_at(results, age) for age in TOTAL_AGES}
    ends = sorted({f"{r.ages[-1]:.0f}" for r in results}, key=int)
    fields = {
        "broke": taken[BROKE_AGE][0],
        "median": taken[MEDIAN_AGE][0],
        "end": format_list(ends, style="or", locale=i18n.language()),
        "money": money,
    }
    without = any(r.survival is None for r in results)  # the life table

    def shown(c: Column) -> Shown:
        age, apart = taken.get(c.age, (c.age, ""))
        said = (_(t).format(**fields) for t in (c.help, c.unmortal if without else "") if t)
        text = " ".join(filter(None, (*said, apart)))
        tip = text if c.header.format(age=c.age) == c.term else f"{c.name.format(age=age)}: {text}"
        return Shown(c.term, _(c.header).format(age=age), tip)

    return [shown(c) for c in COLUMNS]


def changes(mine: SummaryRow, theirs: SummaryRow) -> dict[str, str]:
    """The change of each column of the summary from `theirs` to `mine` that has a value, by
    term: against the run of the files in the Explorer, against the main scenario in the
    what-ifs of the Overview."""
    return {
        c.term: change
        for c in COLUMNS
        if c.change and (change := c.change(mine, theirs)) is not None
    }


def summary_table(results: list[RunResult], *, nominal: bool = False) -> list[dict[str, str]]:
    """One dict per scenario, keyed by the terms of the columns."""
    return [
        {c.term: c.cell(row, True) for c in COLUMNS}
        for row in (summary_row(r, nominal=nominal) for r in results)
    ]


def summary_title(results: list[RunResult], *, nominal: bool) -> str:
    """The model of a run by its name on the command line (`--model`)."""
    runs = dict.fromkeys(
        r.model
        if r.model == "fixed"
        else ngettext("{model}, {n} path", "{model}, {n} paths", r.paths).format(
            model=r.model, n=r.paths
        )
        for r in results
    )
    return _("Summary in {unit}: {runs} ({time})").format(
        unit=results[0].unit(nominal=nominal),
        runs="; ".join(runs),
        time=f"{datetime.now().astimezone():%Y-%m-%d %H:%M:%S}",
    )


def difference_table(d: Difference, *, compact: bool = False) -> list[dict[str, str]]:
    """One row per measure of B less A, one column per month: those of `TOTAL_AGES` and the end
    of the run, each headed by its whole age (a run that does not reach an age takes its first or
    last month, `Difference.index`), the first of two months of one age (an end a few months past
    90). The caller names B and A: a long first header leaves no room on a phone. Compact the rows
    name them A and B too: a pinned first column cuts a long name."""
    a, b = ("A", "B") if compact else (d.a, d.b)
    at = _("at {age}")
    ages: dict[str, int] = {}  # the month of each column by its header
    for age in (*TOTAL_AGES, float(d.ages[-1])):
        i = d.index(age)
        ages.setdefault(at.format(age=f"{d.ages[i]:.0f}"), i)
    only = _("Broke by then, only {run}")
    rows = [
        *(
            (f"{name}, {_('median') if q == 50 else f'p{q}'}", values, True)
            for name, spread in ((_("Total"), d.total), (_("Liquid"), d.liquid))
            for q, values in zip(SPREAD, spread, strict=True)
        ),
        (_("Taxes paid up to then, median"), d.taxes, True),
        (only.format(run=a), d.broke_only[0], False),
        (only.format(run=b), d.broke_only[1], False),
    ]
    return [
        {_("Measure ({unit})").format(unit=d.unit): label}
        | {
            column: format_eur(values[i], signed=True) if money else f"{values[i]:.1%}"
            for column, i in ages.items()
        }
        for label, values, money in rows
    ]


def console_table(results: list[RunResult], *, nominal: bool = False) -> Table:
    """Fits a terminal of `CONSOLE_WIDTH` columns: the title names the unit of money once, a
    plain header breaks into lines of `HEADER_LINE` characters, a long scenario name folds, a
    figure never wraps."""
    table = Table(
        title=f"Dagobert {summary_title(results, nominal=nominal)}",
        box=box.SIMPLE_HEAD,
        show_edge=False,
        pad_edge=False,
        collapse_padding=True,
    )
    shown = zip(summary_columns(results, nominal=nominal), COLUMNS, strict=True)
    for i, column in enumerate(s for s, c in shown if c.console):
        table.add_column(
            "\n".join(textwrap.wrap(column.label, HEADER_LINE)),
            justify="right" if i else "left",
            no_wrap=i > 0,
        )
    for r in results:
        row = summary_row(r, nominal=nominal)
        table.add_row(*(c.cell(row, False) for c in COLUMNS if c.console))
    return table


def print_summary(results: list[RunResult], *, nominal: bool = False) -> None:
    """In a terminal narrower than `CONSOLE_WIDTH` the lines run over: rich would cut the
    figures to fit."""
    console = Console()
    console.width = max(console.width, CONSOLE_WIDTH)
    console.print(console_table(results, nominal=nominal))
