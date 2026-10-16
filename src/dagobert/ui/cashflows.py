"""Cashflow plan: monthly sheet by category, scheduled changes, changes since a day."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from dagobert import budget, cashplan, revisions, sv, tax
from dagobert.budget import NONCASH_INCOME, SURPLUS, Budget, said
from dagobert.i18n import N_, _
from dagobert.loader import load_assumptions, load_plan
from dagobert.model.assets import PensionPolicy
from dagobert.model.months import add_months
from dagobert.model.plan import Plan
from dagobert.model.streams import SAVINGS_TARGETS, Stream, StreamKind
from dagobert.money import format_eur
from dagobert.references import Kind
from dagobert.scenariofiles import concrete_scenarios, first_scenario, scenario_file
from dagobert.store import RowFile
from dagobert.ui import (
    CASHFLOWS_SCENARIO,
    GAIN,
    LOSS,
    TOTAL,
    day_said,
    fixed,
    fold,
    mode,
    page_link,
    per_control,
    scenario_note,
    scenario_titles,
    since,
)
from dagobert.ui.bars import NONCASH_NOTE, RUN, income_chart, outflows_chart, phase_control, reached
from dagobert.ui.tables import Ref, Table, edit_table, unsaved

_WHEN = ("every", "start", "end", "factor")
_GATES = {"factor": "phases"}  # one cell per phase: multiplier, 0 switches the phase off
Labels = Mapping[str, str]  # how the pages name each phase, in the order of `assumptions.yaml`
SAVINGS_NOTE = N_(
    "A savings plan pays its `amount` (negative, like an expense) from the cash into an asset "
    "each month, or every `every` months: `into` names an equity, fixed-income, gold or crypto "
    "asset, empty buys the equity of the depot. It ignores the cash buffer, and when the cash does "
    "not cover a rate it skips it, as a broker does. It runs nominal, as a broker runs it, unless "
    "`index` names one: an index with a spread of 0 raises it each January (Dynamisierung). The "
    "rate is part of the surplus, so the sheet shows it below the surplus and the scheduled "
    "changes give it no effect. The Explorer has a slider per plan."
)
BU_NOTE = N_(
    "A disability insurance (Berufsunfähigkeitsversicherung, BU) pays its monthly benefit from the "
    "month after you lose the ability to work, until the age at which the contract ends, and "
    "waives its premium from then on. The plan draws that onset per simulated future by the "
    "yearly chance of the Assumptions page (Rules, Disability). Enter 0 as the premium while an "
    "employer pays it. When you leave the employer, a `set_stream` of the scenario sets your own "
    "premium from that month, or the policy ends there (`end`, or `end_streams` of a scenario). "
    "The benefit stays nominal unless `index` names one (a dynamic contract). The sheet shows the "
    "premium; the benefit shows only in a run that is disabled."
)
# The phases and the terms of the law and of the run in plain words, under the sheet, the terms
# also under the table of the Flows page: folded, a tooltip of this length ran off a phone
PHASES = N_(
    "A column per phase that the scenario reaches, in the order of the Assumptions page: the "
    "Scenarios page sets when it switches."
)
TERMS = (
    N_("Terms:"),
    N_(
        "SV: social insurance (Sozialversicherung), its parts RV (pension), AV (unemployment), "
        "KV (health) and PV (long-term care)"
    ),
    N_(
        "PKV: private health insurance. Its subsidy comes from the employer, the Agentur für "
        "Arbeit or the pension insurance"
    ),
    N_(
        "GKV: statutory health insurance. A month without a salary, ALG1 or KVdR (the health "
        "insurance of pensioners) is voluntary: KV and PV on all income, at least on a minimum. "
        "A company pension pays KV and PV too (a Versorgungsbezug), a lump sum for ten years"
    ),
    N_("Soli: the solidarity surcharge on the income tax"),
    N_(
        "Kirchensteuer: the church tax of a church member, 8% or 9% of the income tax. The rows "
        "of the income tax hold it, with the Soli"
    ),
    N_("Abgeltungsteuer: the flat tax on capital gains"),
    N_("ALG1: unemployment benefit (Arbeitslosengeld)"),
    N_("bAV: a company pension (betriebliche Altersversorgung)"),
    N_(
        "Salary conversion: the part of the gross salary that goes into a company pension "
        "(Entgeltumwandlung), before the income tax and the SV. It stays in the net worth"
    ),
    N_("Altersvorsorgedepot: a pension depot from 2027 with a state grant, the Zulage"),
    N_("Basisrente: a private pension whose premiums reduce the income tax (Rürup)"),
    N_(
        "Werbungskosten: the costs of the work, such as the commute. The income tax takes the "
        "flat {werbungskosten} a year, or the higher sum that you enter on the Assumptions page"
    ),
    N_(
        "Sonderausgaben: costs that lower the taxable income, such as the church tax, donations "
        "and childcare. At least {sonderausgaben} a year"
    ),
    N_(
        "§35a EStG: 20% of the labour costs of household services and of a craftsman come off "
        "the income tax"
    ),
    N_(
        "Gewerbesteuer: the trade tax of a business with a Hebesatz. The income tax takes most "
        "of it back (§35 EStG)"
    ),
)


def listed(lines: Sequence[str], **fields: str) -> str:
    """A title and its items (`TERMS`, `flows.LINES`) as a Markdown list in the language of the
    session, each formatted with `fields`."""
    title, *items = lines
    return "\n".join([_(title), *(f"- {_(item).format(**fields)}" for item in items)])


def terms(plan: Plan) -> str:
    """`TERMS` with the Pauschbeträge of the tax year of `plan`."""
    ty = _year(plan)
    return listed(
        TERMS,
        werbungskosten=format_eur(ty.werbungskosten_pauschale),
        sonderausgaben=format_eur(ty.sonderausgaben_pauschbetrag),
    )


# The names a stream refers to. The category stays free text: a row defines its category.
_REFS = {
    "index": Ref(Kind.INDEX),
    "of": Ref(Kind.STREAM, sorts=(StreamKind.SALARY,), unless="of"),  # a base salary
    "repays": Ref(Kind.ASSET, sorts=("loan",)),
    "after_sale_of": Ref(Kind.ASSET, sorts=("property",)),
    "property": Ref(Kind.ASSET, sorts=("property",)),  # a let one
    "tags": Ref(Kind.TAG, new=True),
}
EXPENSES = Table(
    Stream,
    "streams-expenses",
    match=lambda row: cashplan.role(row) == cashplan.EXPENSE and row.get("kind") != "bu",
    fields=("name", "amount", *_WHEN, "tags"),
    more=(
        "cat",
        "kind",
        "index",
        "health",
        "deduct",
        "deductible",
        "after_sale_of",
        "property",
    ),
    gates=_GATES,
    sort_by=("cat", "name", "start"),
    pinned=("name",),
    negative=("amount",),
    group_by="cat",
    options=_REFS,
    locked=("name",),
    rename=Kind.STREAM,
    identity=("name", "start"),
    titles={"deduct": N_("deductible as")},
    grid="streams",
    helps={
        "deductible": N_(
            "The share that counts for the tax, in percent. Of a health premium the share that "
            "the tax office accepts, from the insurer's certificate: empty is all of the care "
            "insurance and 80% of the health insurance. Of an expense that is deductible as "
            "something the share that counts, such as the labour part of a craftsman's bill or "
            "the donations among the gifts: empty is all of it."
        )
    },
)
INCOME = Table(
    Stream,
    "streams-income",
    match=lambda row: cashplan.role(row) == cashplan.INCOME,
    fields=("name", "kind", "gross", "part", "of", "share", "amount", *_WHEN),
    more=(
        "cat",
        "points",
        "point_value",
        "index",
        "tags",
        "repays",
        "after_sale_of",
        "property",
        "taxable",
        "hebesatz",
        "sperrzeit",
        "training",
    ),
    gates=_GATES,
    sort_by=("cat", "name", "start"),
    pinned=("name",),
    group_by="cat",
    options=_REFS,
    locked=("name",),
    rename=Kind.STREAM,
    identity=("name", "start"),
    titles={"hebesatz": N_("trade tax rate (Hebesatz)")},
    grid="streams",
    helps={
        "hebesatz": N_(
            "The Gewerbesteuer-Hebesatz of the municipality of a trade business, at least 200%, "
            "in percent: 430 for 430%. Empty: a freelancer, no trade tax."
        )
    },
)
BU = Table(
    Stream,
    "streams-bu",
    fixed={"kind": StreamKind.BU.value},
    fields=("name", "amount", "premium", "until_age", "start", "end"),
    more=("cat", "index", "tags", "after_sale_of"),
    sort_by=("name", "start"),
    pinned=("name",),
    negative=("premium",),
    options=_REFS,
    grid="streams",
    locked=("name",),
    rename=Kind.STREAM,
    identity=("name", "start"),
    titles={
        "amount": N_("Monthly benefit €"),
        "premium": N_("Monthly premium €"),
        "until_age": N_("Pays until age"),
    },
    helps={
        "index": N_(
            "Growth index that the benefit and the premium follow: 'cpi' or a name from "
            "assumptions.indices, for a dynamic contract. Empty or null: nominal, as the contract "
            "guarantees it"
        )
    },
)
SAVINGS = Table(
    Stream,
    "streams-savings",
    fixed={"kind": StreamKind.SAVINGS.value},
    fields=("name", "amount", "into", *_WHEN, "index"),
    more=("tags", "after_sale_of"),
    gates=_GATES,
    sort_by=("name", "start"),
    pinned=("name",),
    negative=("amount",),
    options=_REFS | {"into": Ref(Kind.ASSET, sorts=SAVINGS_TARGETS)},
    grid="streams",
    locked=("name",),
    rename=Kind.STREAM,
    identity=("name", "start"),
    helps={
        "index": N_(
            "Growth index that the amount follows: 'cpi' or a name from assumptions.indices. "
            "Empty or null: a nominal amount"
        )
    },
)


def _alg1(rows: list[cashplan.Row], day: date, plan: Plan) -> float:
    """The monthly ALG1 that the engine pays, in start-year euros, on the last salary before the
    claim: in the month before the first change to a phase in which an ALG1 stream pays (not a
    course, `training`, which runs beside one), of the newest phase before it with a salary.
    Without such a change or salary, on `day`: of the phase of the scenario then, else of the
    newest phase before it with a salary. At 67% with a child that counts in the month after
    that salary, the first of the claim."""
    a, changes = plan.assumptions, plan.scenario.phases
    rows = cashplan.with_levels(rows, a.indices)
    alg1 = [r for r in rows if r.get("kind") == "alg1" and not r.get("training")]
    claim = next(
        (n for n, c in enumerate(changes) if any(cashplan.applies(r, c.phase) for r in alg1)),
        0,
    )
    before = [c.phase for c in reversed(changes[:claim])]
    back = [c.phase for c in reversed(changes) if c.at <= day] or [c.phase for c in changes[:1]]
    tries = [(add_months(changes[claim].at, -1), before)] if claim else []
    phase, gross, at = next(
        (
            (*found, at)
            for at, phases in [*tries, (day, back)]
            if (found := cashplan.alg1_reference(rows, at, phases))
        ),
        ("", 0.0, day),
    )
    converted = _converted(plan, rows, phase, at, gross)
    child = bool(a.person.counting(add_months(at, 1)))
    return float(sv.alg1_month(gross - converted, _year(plan), child=child))


def _year(plan: Plan) -> tax.TaxYear:
    return tax.for_year(plan.assumptions.tax_year)


def _converted(plan: Plan, rows: list[cashplan.Row], phase: str, day: date, gross: float) -> float:
    """What the salary conversions of the bAV policies that pay in `phase` on `day`, before they
    mature, take off the contributory `gross` (`sv.conversions`, after the employer's
    contributions), each from its salary as the engine takes it (`Income._source`)."""
    salaries = [
        (row, cashplan.monthly(row, rows, phase, day) or 0.0)
        for row in rows
        if row.get("kind") == "salary"
        and row.get("every", 1) == 1
        and cashplan.active(row, day, phase)
    ]
    paying = [
        a
        for a in plan.assets
        if isinstance(a, PensionPolicy) and phase in a.phases and day < a.matures
    ]
    taken = [
        (min(p.conversion, pay), p.subsidy)
        for p in paying
        if p.conversion and (pay := _salary_of(p, salaries)) is not None
    ]
    convs = sv.conversions(
        taken,
        gross,
        sum(p.contribution for p in paying),
        plan.assumptions.tax,
        _year(plan),
        month=day,
    )
    return sum(float(c.sv_free) for c in convs)


def _salary_of(policy: PensionPolicy, salaries: list[tuple[cashplan.Row, float]]) -> float | None:
    """The monthly gross of the salary that the conversion of `policy` takes among `salaries`,
    the rows that pay with their gross: the one that `salary` names, else the first without
    `of`."""
    return next(
        (
            pay
            for row, pay in salaries
            if (row.get("name") == policy.salary if policy.salary else "of" not in row)
        ),
        None,
    )


def _paid(rows: list[cashplan.Row], plan: Plan, alg1: float) -> list[cashplan.Row]:
    a = plan.assumptions
    return cashplan.with_gkv(
        cashplan.with_alg1(cashplan.with_levels(rows, a.indices), alg1), a.tax.gkv_from
    )


def estimated(rows: list[cashplan.Row], day: date, plan: Plan) -> list[cashplan.Row]:
    """`rows` as a `fixed` run of `plan` pays them: a stream of a non-cumulative index at its level
    (a bonus at the mean payout ratio), ALG1 on the last salary before the claim (`_alg1`), the
    PKV premiums up to `tax.gkv_from`."""
    return _paid(rows, plan, _alg1(rows, day, plan))


def run_flows(data_dir: Path, scenario: str, day: date) -> dict[str, Budget]:
    """Per phase, what no stream pays in the `fixed` run of `scenario` from `day` on
    (`budget.beyond_streams`). Empty for an abstract scenario."""
    result = fixed.result(data_dir, scenario)
    if result is None:
        return {}
    plan = load_plan(data_dir, data_dir / scenario_file(scenario))
    return budget.beyond_streams(result, plan, day)


def with_phases(table: Table, labels: Labels) -> Table:
    """`table` with a `factor` column per phase, headed by its label."""
    return replace(table, entries={"factor": labels})


def _with_totals(table: Table, day: date, plan: Plan) -> Table:
    """`table` with a column and a total row per phase: the monthly sum on `day` per category."""
    labels = plan.assumptions.phase_labels

    def totals(members: list[cashplan.Row], rows: list[cashplan.Row]) -> dict[str, str]:
        alg1 = _alg1(rows, day, plan)
        sums = cashplan.phase_totals(
            _paid(members, plan, alg1), _paid(rows, plan, alg1), day, labels
        )
        return {"name": _("per month")} | {f"factor {p}": format_eur(v) for p, v in sums.items()}

    return replace(with_phases(table, labels), totals=totals)


Amounts = Mapping[str, float | None]  # per phase, None where the run never gets
_Line = tuple[dict[str, str], Amounts]  # label cells, then the amount per phase


def _shown(value: object) -> bool:
    return isinstance(value, float) and bool(value) and not math.isnan(value)


def _amount(value: object) -> str:
    return format_eur(value) if isinstance(value, float) and _shown(value) else "–"


def _phase_table(
    lines: list[_Line],
    labels: Labels,
    *,
    key: str,
    totals: Collection[int] = (),
    signed: Collection[int] = (),
) -> None:
    """Static table with one amount column per phase, headed by its label, in the container
    `table-cashflows-<key>` (`ui.PAGE_STYLE`). `totals` are the positions of the bold rows,
    `signed` those that color their amounts by sign."""
    phases = list(labels.values())

    def look(row: pd.Series[Any]) -> list[str]:
        color = {True: f"color: {GAIN}; ", False: f"color: {LOSS}; "}
        return [
            (TOTAL if row.name in totals else "")
            + ("text-align: right; " if column in phases else "")
            + (
                color[value > 0]
                if column in phases and row.name in signed and _shown(value)
                else ""
            )
            for column, value in row.items()
        ]

    st.container(key=f"table-cashflows-{key}").table(
        pd.DataFrame(
            [cells | {labels[p]: v for p, v in amounts.items()} for cells, amounts in lines]
        )
        .style.apply(look, axis=1)
        .format(_amount, subset=pd.Index(phases)),
        border="horizontal",
        hide_index=True,
    )


def _show_changes(
    changes: list[cashplan.Change],
    labels: Labels,
    *,
    key: str,
    dated: bool = False,
    total: bool = False,
) -> None:
    """`stream`, `date` when `dated`, `change`, then the phases: `ui/page.css` finds `change` by
    its place from the start (st.table keeps no class of a column), whatever the phases."""
    if not changes:
        st.caption(_("None."))
        return
    stream, when, change = _("stream"), _("date"), _("change")
    lines: list[_Line] = [
        (
            {stream: c.name}
            | ({when: c.when.isoformat() if c.when else _("on condition")} if dated else {})
            | {change: c.what},
            c.monthly,
        )
        for c in changes
    ]
    if total:
        lines.append(
            (
                {stream: _("total"), change: ""},
                {p: sum(c.monthly[p] for c in changes) for p in labels},
            )
        )
    _phase_table(
        lines, labels, key=key, totals=[len(changes)] if total else (), signed=range(len(lines))
    )


def _changes_since(
    data_dir: Path,
    bases: Mapping[revisions.Day, str],
    rows: list[cashplan.Row],
    day: date,
    plan: Plan,
) -> None:
    """The changes of the streams since the start of a day with a revision of them, against the
    revision before that day (`bases`)."""
    labels = reached(plan)
    st.subheader(_("Changes since"))
    chosen = st.selectbox(
        _("Day"), list(bases), format_func=day_said, key="cashflows-since", width=400
    )
    st.caption(
        _(
            "The changes of the streams since the start of the chosen day, its own included, "
            "with the effect per month per phase. A day names the saves that changed the streams."
        )
    )
    base = bases[chosen]
    try:
        old, start = cashplan.plan_at(data_dir, base)
    except ValueError as err:
        st.warning(
            _("The streams before {day} do not read: {error}").format(day=chosen.day, error=err)
        )
        return
    _show_changes(
        cashplan.diff(estimated(old, day, plan), rows, list(labels), start),
        labels,
        key="since",
        total=True,
    )


def sheet_lines(
    rows: list[cashplan.Row], day: date, run: Mapping[str, Budget], phases: Sequence[str]
) -> list[tuple[str, Amounts, bool]]:
    """The rows of the sheet, each with its amount per phase and whether it is a sum: the
    categories of the plan on `day` with the sums `income` and `expenses`, then what the run pays
    beyond the streams (`run`, per phase) with its sum `RUN`, then the `surplus`, and below it what
    the savings plans paid in the run, if any, and the non-cash income of the run, both not part of
    it. A phase that the run does not reach has no amount in the rows of the run, in the surplus
    and below it."""
    lines: list[tuple[str, Amounts, bool]] = []
    plan = dict.fromkeys(phases, 0.0)
    for section, cats in cashplan.sheet(rows, day, list(phases)).items():
        subtotal = {p: sum(sums[p] for sums in cats.values()) for p in phases}
        plan = {p: plan[p] + subtotal[p] for p in phases}
        lines += [*((cat, sums, False) for cat, sums in cats.items()), (section, subtotal, True)]
    extra = {phase: b.lines for phase, b in run.items()}
    labels = dict.fromkeys(label for amounts in extra.values() for label in amounts)
    lines += [
        (label, {p: extra[p].get(label, 0.0) if p in extra else None for p in phases}, False)
        for label in labels
    ]
    beyond = {p: sum(extra[p].values()) if p in extra else None for p in phases}
    saved = {p: sum(run[p].saved.values()) if p in run else None for p in phases}
    return [
        *lines,
        (RUN, beyond, True),
        (SURPLUS, {p: None if v is None else plan[p] + v for p, v in beyond.items()}, True),
        *([(budget.SAVED, saved, False)] if any(saved.values()) else []),
        (
            NONCASH_INCOME,
            {p: sum(run[p].noncash.values()) if p in run else None for p in phases},
            False,
        ),
    ]


def _sheet(lines: list[tuple[str, Amounts, bool]], labels: Labels, factor: int) -> None:
    """The lines of `sheet_lines` in the words of the session: a sum is a message, a category of
    the plan as written, a line of the run as `said`."""
    category = _("category")
    _phase_table(
        [
            (
                {category: _(label) if bold else said(label)},
                {p: None if v is None else factor * v for p, v in sums.items()},
            )
            for label, sums, bold in lines
        ],
        labels,
        key="sheet",
        totals=[i for i, (_label, _sums, bold) in enumerate(lines) if bold],
        signed=[i for i, (label, _sums, _bold) in enumerate(lines) if label == SURPLUS],
    )


def _covered(data_dir: Path, scenario: str, day: date, labels: Labels) -> str:
    """The months of the run behind each phase of the sheet."""
    result = fixed.result(data_dir, scenario)
    if result is None:
        return _("none")
    return ", ".join(
        _("`{phase}` {first} to {last}").format(
            phase=labels.get(phase, phase),
            first=f"{result.months[months[0]]:%Y-%m}",
            last=f"{result.months[months[-1]]:%Y-%m}",
        )
        for phase, months in budget.ahead(result, day).items()
    )


# The sections of the page, for the jump links at its top: the anchor of its heading, the label
SECTIONS = {
    "sheet": N_("Sheet"),
    "bars": N_("Bars"),
    "changes": N_("Changes"),
    "streams": N_("Streams"),
}


def page(file: RowFile) -> None:
    st.title(_("Cashflows"))
    data_dir = file.data_dir
    # a long page on a phone: links to its sections
    links = " · ".join(f"[{_(label)}](#{at})" for at, label in SECTIONS.items())
    st.caption(_("Go to {links}").format(links=links))
    left, middle, right = st.columns(3)
    person = load_assumptions(data_dir).person
    day = left.date_input(
        _("As of"),
        date.today(),
        # the end of the plan: the default allows ten years
        max_value=max(date(person.born.year + person.horizon_age, 12, 31), date.today()),
        format="YYYY-MM-DD",
        key="cashflows-day",
        help=_("The date of the plan: the streams that run then, the run from then on."),
    )
    main = first_scenario(data_dir)
    titles = scenario_titles(concrete_scenarios(data_dir), main)
    scenario = middle.selectbox(
        _("Scenario"),
        list(titles),
        index=list(titles).index(main),
        format_func=titles.__getitem__,
        key=CASHFLOWS_SCENARIO,
        help=_("Its run gives the rows down to `{run}`, its events the scheduled changes.").format(
            run=_(RUN)
        ),
    )
    per = per_control(right, "cashflows-per")
    plan = load_plan(data_dir, data_dir / scenario_file(scenario))
    with middle:  # below the select that it belongs to
        scenario_note(plan.scenario.note)
    rows = estimated([dict(r) for r in file.rows()], day, plan)
    run = run_flows(data_dir, scenario, day)
    labels = reached(plan)

    st.subheader(_("Sheet"), anchor="sheet")
    _sheet(sheet_lines(rows, day, run, list(labels)), labels, per[1])
    sheet = _(
        "The plan on {day}: its streams, and from the run the first 12 months of each phase. The "
        "Flows page shows the means of the run over whole phases, so its figures differ."
    ).format(day=day)
    st.caption(f"{_(PHASES)} {sheet}")
    page_link("Flows", _("Flows: where the money goes over a whole phase"))
    fold(terms(plan), _("What the terms mean"))
    reading = _(
        "Euros of the simulation start, money out below zero. The rows down to `expenses` are "
        "the streams of the plan on the `As of` date in each phase. Salaries and pensions are "
        "gross. A bonus counts at the mean payout ratio of its index in `{scenario}`, as its "
        "run pays it. The unemployment benefit (ALG1) is an estimate: what the simulation pays "
        "on the monthly salary of that date in the phase of the scenario then, or in the last "
        "phase before it with a salary, net and only for the 12 to 24 months of the claim. A "
        "stream paid every n months counts in the n months that end with its first payment. "
        "Streams that wait for a property sale are left out. The rows down to `{run}` are what "
        "no stream pays, such as the taxes and the loans: a single run of `{scenario}` with the "
        "mean returns, the mean over the first 12 months of each phase from the `As of` date on "
        "({covered}), a bonus spread over the months that earn it. A phase that the run does "
        "not reach from then on shows `–`. `surplus` adds up all rows above it: what is left to "
        "save. It takes the streams of the plan, not those of the run, so it differs from the "
        "surplus of the Flows page by what the run changes in the streams (the growth of the "
        "indices, the events) and by the months that a phase of the Flows page covers. `{saved}` "
        "below it, with a savings plan, is what the plans paid into their assets in the run, so "
        "a month that paused one shows: a part of the surplus, not taken off it. `non-cash "
        "income` below it comes from the run over the same months and is not part of the "
        "surplus."
    ).format(
        scenario=scenario,
        run=_(RUN),
        covered=_covered(data_dir, scenario, day, labels) or _("none"),
        saved=_(budget.SAVED),
    )
    fold(f"{reading} {_(NONCASH_NOTE)}", _("How to read the sheet"))

    st.subheader(_("Bars of one phase"), anchor="bars")
    phase = phase_control("cashflows-phase", plan, day)
    outflows, income = st.container(key="cashflows-bars").columns(2, gap="large")
    with income:  # first: on a desktop the streams of a clicked category go below it
        income_chart(
            rows, day, phase, per, run.get(phase), key="cashflows-income", label=labels[phase]
        )
    with outflows:
        outflows_chart(
            rows,
            day,
            phase,
            per,
            run.get(phase),
            key="cashflows-outflows",
            label=labels[phase],
            detail=income,
        )
    bars = _(
        "One phase like the sheet, without signs: the outflows by category, the income by "
        "stream, colored like the blocks of the stream tables. The other bars come from the run: "
        "the taxes and social insurance and the capital gains tax orange, the loan principal "
        "amber, the rest gray. The loan principal leaves the cash but pays off debt, so it stays "
        "in net worth. The purple bars at the bottom are the non-cash income, which stays out of "
        "the income total."
    )
    fold(f"{bars} {_(NONCASH_NOTE)}", _("How to read the bars"))

    _scheduled(rows, day, plan, scenario)
    if bases := since(data_dir, lambda path: path == cashplan.FILE):
        _changes_since(data_dir, bases, rows, day, plan)
    _streams(file, day, plan)


def _scheduled(rows: list[cashplan.Row], day: date, plan: Plan, scenario: str) -> None:
    """The dated changes of the streams and those of the events of `scenario` after `day`."""
    labels = reached(plan)
    st.subheader(_("Scheduled changes"), anchor="changes")
    st.caption(_("The change of the monthly total of each phase: green more money, red less."))
    events = cashplan.scenario_changes(rows, plan, day, list(labels))
    _show_changes(
        sorted(
            [*cashplan.scheduled(rows, day, list(labels), paired=True), *events],
            key=lambda c: (c.when or date.max, c.name),
        ),
        labels,
        key="scheduled",
        dated=True,
    )
    fold(
        _(
            "The start and end dates of the streams, and what the events of `{scenario}` change, "
            "such as the streams that a sale ends. A stream that ends on the date on which a row "
            "of its name starts, a raise or a new price, is one change. A sale on a condition has "
            "no date and comes last. A savings plan has no effect: it takes its rate out of the "
            "surplus into an asset."
        ).format(scenario=scenario),
        _("About the changes"),
    )


def _streams(file: RowFile, day: date, plan: Plan) -> None:
    """The editable streams in a tab per role, their columns and kinds by the mode and the
    features (`mode.View`), and below them the note of the kinds that these hide."""
    view = mode.view(file.data_dir)
    st.subheader(_("Streams"), anchor="streams")
    st.caption(_("Open a category, change a cell or add a row, then press `Save` at the top."))
    fold(
        _(
            "One block per category, a new row takes the category of its block. The phase "
            "columns hold a multiplier: 1 applies in full, 0 means the stream does not apply in "
            "that phase. For a known price change, set `end` on the row and add a row with the "
            "same name, the new amount and `start`. A bonus is a salary stream with `of` and "
            "`share`, see the help of their columns. The header of a block, and on a wide screen "
            "the bold row under its grid, holds the monthly sum per phase at the `As of` date, "
            "unsaved edits included. An expense is saved negative whatever sign is typed. The "
            "sheet above shows the saved file. `All columns` shows the rare fields, among them "
            "`cat` to move a stream or to start a new category."
        ),
        _("How to edit the streams"),
    )
    insured = view.shows(mode.Item(mode.Sort.STREAM, (StreamKind.BU.value,))) or unsaved(BU)
    tabs = (N_("expenses"), N_("income"), N_("savings"), *[N_("disability insurance")] * insured)
    expenses, income, savings, *bu = st.tabs([_(t) for t in tabs], key="cashflows-tabs")
    with expenses:
        edit_table(file, _with_totals(EXPENSES, day, plan), view)
    with income:
        edit_table(file, _with_totals(INCOME, day, plan), view)
    with savings:
        fold(_(SAVINGS_NOTE), _("How savings plans work"))
        edit_table(file, with_phases(SAVINGS, plan.assumptions.phase_labels), view)
    for policies in bu:
        with policies:
            fold(_(BU_NOTE), _("How a disability insurance works"))
            edit_table(file, BU, view)
    kinds = {mode.Item(mode.Sort.STREAM, (k,)): title for k, title in StreamKind.titles().items()}
    view.note(
        {k: _(title) for k, title in kinds.items() if not view.shows(k)}, held=mode.Held.KINDS
    )
