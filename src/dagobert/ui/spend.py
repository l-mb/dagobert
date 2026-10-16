"""Record the actual spending per month and category, and compare it with the plan."""

from __future__ import annotations

import zlib
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import actuals, cashplan, i18n
from dagobert.actuals import (
    NONE,
    Amounts,
    Clash,
    ClashError,
    Comparison,
    Coverage,
    Draft,
    Months,
    applied,
    merge,
)
from dagobert.i18n import N_, _, ngettext
from dagobert.loader import load_assumptions, load_scenario
from dagobert.model.assumptions import Assumptions
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Scenario
from dagobert.money import EUR_COLUMN, format_eur
from dagobert.report.tracker import Slice, bars_figure, spend_figure
from dagobert.scenariofiles import first_scenario, scenario_file
from dagobert.store import RowFile
from dagobert.ui import (
    GAIN,
    LOSS,
    TOTAL,
    chart,
    fold,
    guard,
    is_mobile,
    keyboard,
    literal,
    month_labels,
    source,
    step_button,
    tell,
)
from dagobert.ui.fields import euros
from dagobert.ui.gridcolumns import Column
from dagobert.ui.save import reason
from dagobert.ui.tables import row_colors, save_in_header, total_row

MONTH, NONCE = "spend-month", "spend-nonce"
SHOW = "month"  # the query of a link that opens a month on the grid: `?month=2026-01`
DRAFTS = "spend-drafts"  # the unsaved edits of the grid by month
BASE = "spend-base"  # the amounts that the current grid started from, by its key
CATEGORY = "spend-category"  # the category of the last quick add
ADD_MONTH = "spend-add-month"  # the month of the last quick add
ADDED = "spend-added"  # a quick add saved: the next run empties the amount
LAST = "spend-last"  # the last quick add saved, which the line under the form names
CLASHES = "spend-clashes"  # the clashes of the last run: a toast names only new ones
HEADER = "spend-header"  # Discard and Save of the grid, pinned into the page header
# the quick add fields, keyed for the keyboard of a phone (`ui.KEYBOARD`)
PICK, SPENT, TO_MONTH = "nocaps-spend-pick", "decimal-spend-spent", "spend-to-month"
MONTHS_BACK = 24  # months before the current one to choose from, besides the recorded ones
REJECTED = ":red[:material/error: {error}]"  # a rejected quick add, under the form
COLUMNS = [
    Column(name, kind, (), None, False, "", name)
    for name, kind in (("category", "string"), ("plan", "number"), ("actual", "number"))
]
# the headers of the grid and of the comparison by column, said where they show
HEADERS = {
    "category": N_("category"),
    "months": N_("months"),
    "plan": N_("plan"),
    "actual": N_("actual"),
    "difference": N_("difference"),
    "share": N_("difference %"),
}


def canonical(cat: str, known: Iterable[str]) -> str:
    """`cat` without spaces around it, spelled like the known category that differs only in case:
    a phone keyboard starts a word with a capital."""
    cat = cat.strip()
    return next((k for k in known if k.casefold() == cat.casefold()), cat)


def quick(typed: str | None, text: str, known: Iterable[str]) -> tuple[str, float] | None:
    """Category and euros of a quick add, None without either: a category of spaces is none."""
    cat, spent = canonical(typed or "", known), euros(text)
    return (cat, spent) if cat and spent else None


@dataclass(frozen=True)
class Added:
    """A saved quick add, which the line under the form names until the next one."""

    category: str
    month: date
    spent: float  # as typed, above zero
    now: float  # what the month holds in the category after it, below zero as spending is

    @property
    def text(self) -> str:
        """In the sign of the form, euros spent: the grid shows the month below zero."""
        now = guard.Change(self.category, None, self.now, outflow=True, ratio=False)
        added = _("Added {amount} to **{category}**, {month}: now {total} spent.").format(
            amount=format_eur(self.spent, cents=True),
            category=literal(self.category),
            month=f"{self.month:%Y-%m}",
            total=format_eur(-self.now, cents=True),
        )
        warned = _("⚠ The month is {warning}.").format(warning=now.warning)
        return f"{added} {warned}" if now.warning else added


def entered(shown: list[tuple[str, float | None]], state: dict[str, Any]) -> Amounts:
    """The amounts that the grid holds after the edits in `state`. `shown` holds category and
    actual per row before them. A row without a category or an actual records nothing, and
    rows of one category add up, also in another case."""
    cats = [cat for cat, _ in shown]
    edited = {int(i): cells for i, cells in state.get("edited_rows", {}).items()}
    deleted = set(state.get("deleted_rows", []))
    amounts: Amounts = {}
    for row in [
        {"category": cat, "actual": actual} | edited.get(i, {})
        for i, (cat, actual) in enumerate(shown)
        if i not in deleted
    ] + list(state.get("added_rows", [])):
        cat, value = canonical(str(row.get("category") or ""), [*cats, *amounts]), row.get("actual")
        if cat and value is not None and not pd.isna(value):
            amounts[cat] = round(amounts.get(cat, 0.0) + float(value), 2)
    return amounts


def take_plan(plan: Amounts, amounts: Amounts) -> Amounts:
    """`amounts` with the plan in each category that has none."""
    return {cat: round(value, 2) for cat, value in plan.items()} | amounts


def edits(saved: Amounts, amounts: Amounts, draft: Draft | None = None) -> Draft:
    """The categories in which `amounts` differs from `saved`, None where it has no amount, each
    with what the file held when its edit began: in `draft` where that edits it already, else in
    `saved`. So a change on another device since stays a clash (`actuals.merge`)."""
    began = draft or {}
    return {
        cat: (began[cat][0] if cat in began else saved.get(cat), amounts.get(cat))
        for cat in sorted({*saved, *amounts})
        if saved.get(cat) != amounts.get(cat)
    }


def moved(draft: Draft, cat: str, spent: float) -> Draft:
    """`draft` after a quick add of `spent` euros to `cat` on this device: an edit of `cat` takes
    it at both ends, so the cell counts it and the add clashes with nothing. A change on another
    device before it stays a clash."""
    if cat not in draft:
        return draft
    was, now = draft[cat]
    return draft | {cat: (round((was or 0.0) - spent, 2), round((now or 0.0) - spent, 2))}


def chosen(draft: Draft, clashes: Iterable[Clash], *, yours: bool) -> Draft:
    """`draft` after a choice for `clashes`: yours keeps each edit and takes the amount of the file
    as its start, else the edit goes and the file stays."""
    picked = {clash.category: clash.file for clash in clashes}
    return {
        cat: (picked[cat], now) if cat in picked else (was, now)
        for cat, (was, now) in draft.items()
        if yours or cat not in picked
    }


def changes(saved: Amounts, amounts: Amounts) -> list[guard.Change]:
    """What a save changes, per category. An amount above zero gets a warning."""
    return [
        guard.Change(cat, saved.get(cat), new, outflow=True)
        for cat, (_, new) in edits(saved, amounts).items()
    ]


def months(recorded: Months, today: date) -> list[date]:
    """The months to choose from: `MONTHS_BACK` before the current one and every recorded."""
    this = today.replace(day=1)
    first, last = min([add_months(this, -MONTHS_BACK), *recorded]), max([this, *recorded])
    return [add_months(first, i) for i in range(months_between(first, last) + 1)]


def _fresh() -> None:
    """A new grid, which starts from the draft or the saved amounts of its month."""
    st.session_state[NONCE] = st.session_state.get(NONCE, 0) + 1


def _draft(month: date, amounts: Amounts, saved: Amounts) -> None:
    """Keep the edits of the unsaved `amounts` of `month`, so that they outlive its grid, each
    with what the file held when it began."""
    drafts = st.session_state.setdefault(DRAFTS, {})
    if draft := edits(saved, amounts, drafts.get(month)):
        drafts[month] = draft
    else:
        drafts.pop(month, None)


def _keep(widget: str, month: date, shown: list[tuple[str, float | None]], saved: Amounts) -> None:
    """The edits of a grid as the draft of its month, before the run: a tap that leaves the month
    can come with the last edit."""
    _draft(month, entered(shown, st.session_state[widget]), saved)


def _add(data_dir: Path, options: list[date], known: list[str]) -> None:
    """One amount spent, added to a category of a month and saved at once. A rejected entry
    stays in the form. Category and month stay for the next one, also after another page. The
    line under the form says what happened."""
    if st.session_state.pop(ADDED, False):
        st.session_state[SPENT], st.session_state[PICK] = "", st.session_state[CATEGORY]
    st.session_state.setdefault(PICK, st.session_state.get(CATEGORY))
    if st.session_state.get(TO_MONTH) not in options:
        last = st.session_state.get(ADD_MONTH)
        st.session_state[TO_MONTH] = last if last in options else date.today().replace(day=1)
    with (
        st.form("spend-quick"),
        st.container(horizontal=True, vertical_alignment="bottom"),
    ):
        typed = st.selectbox(
            _("Category"),
            known,
            accept_new_options=True,
            placeholder=_("Choose or type"),
            key=PICK,
            width=180,
        )
        text = st.text_input(_("Spent"), placeholder="20,50", key=SPENT, width=120)
        month: date = st.selectbox(
            _("Add to month"), options, format_func=lambda m: f"{m:%Y-%m}", key=TO_MONTH, width=140
        )
        added = st.form_submit_button(_("Add"), type="primary", key="spend-add")
    if not added:
        _said()
        return
    if not (entry := quick(typed, text, known)):
        _said(_("Choose a category and enter the euros spent, above zero."))
        return
    cat, spent = entry
    try:  # the file under the lock of the write: an add on another device counts too
        new = actuals.add(data_dir, month, cat, spent, source=source())[1]
    except OSError as err:
        _said(_("Not added: {reason}").format(reason=reason(err)))
        return
    st.session_state[ADDED], st.session_state[ADD_MONTH] = True, month
    if draft := st.session_state.get(DRAFTS, {}).get(month):  # an edited category takes it too
        st.session_state[DRAFTS][month] = moved(draft, cat, spent)
    st.session_state[CATEGORY] = cat
    st.session_state[LAST] = Added(cat, month, spent, new[cat])
    st.rerun()  # the page shows the saved amount, the form starts on an empty one


def _said(error: str = "") -> None:
    """The line under the form, in its place on every run, so nothing moves: a rejected entry, the
    last add with a button that shows its month in the grid, or how to enter one."""
    with st.container(horizontal=True, vertical_alignment="center", key="spend-said", wrap=False):
        if error:
            st.markdown(REJECTED.format(error=error))
        elif last := st.session_state.get(LAST):
            st.markdown(f":material/check_circle: {last.text}")
            if last.month != st.session_state.get(MONTH):
                st.button(
                    _("Show {month}").format(month=f"{last.month:%Y-%m}"),
                    type="tertiary",
                    icon=":material/arrow_downward:",
                    key="spend-show",
                    on_click=_show,
                    args=[last.month],
                )
        else:
            st.caption(_("Enter the euros spent without a minus, for example 20,50."))


def _show(month: date) -> None:
    """The grid on `month`."""
    st.session_state[MONTH] = month
    _fresh()


def linked(month: str) -> date | None:
    """The month of a link (`SHOW`), None for a text that is no `YYYY-MM`."""
    try:
        return datetime.strptime(month, "%Y-%m").date()
    except ValueError:
        return None


def _month(options: list[date]) -> date:
    """The month control, at first on the last complete month, or on the month of a link."""
    if (shown := linked(st.query_params.pop(SHOW, ""))) is not None and shown in options:
        _show(shown)
    elif st.session_state.get(MONTH) not in options:
        st.session_state[MONTH] = add_months(date.today(), -1)
    with st.container(horizontal=True, vertical_alignment="bottom"):
        step_button(MONTH, options, -1, "month", after=_fresh)
        month: date = st.selectbox(
            _("Month"),
            options,
            format_func=lambda m: f"{m:%Y-%m}",
            key=MONTH,
            on_change=_fresh,
            width=140,
        )
        step_button(MONTH, options, 1, "month", after=_fresh)
    return month


def _status(coverage: Coverage) -> None:
    """What the file holds of the month of the grid, and the other months with unsaved edits."""
    others = [f"{m:%Y-%m}" for m in sorted(st.session_state.get(DRAFTS, {})) if m != coverage.month]
    recorded = _("Recorded: {recorded} of {planned} planned categories.").format(
        recorded=coverage.recorded, planned=coverage.planned
    )
    unsaved = _("Unsaved edits also in {months}.").format(months=", ".join(others))
    st.caption(f"{recorded} {unsaved}" if others else recorded)


def _entry(data_dir: Path, plan: Amounts, recorded: Months, month: date) -> None:
    """The grid of one month, its total row with `Take plan`, and Discard and Save, which the page
    pins into its header."""
    saved = recorded.get(month, {})
    # The key holds what the rows come from besides the draft, so a grid starts again from the
    # draft when they change: the editor would lose its edits with its rows. So does the language
    # of its headers: a new column config is a new editor, without the edits of the old one.
    version = zlib.crc32(
        repr(
            (sorted(saved.items()), sorted(plan.items()), sorted(actuals.categories(recorded)))
        ).encode()
    )
    nonce = st.session_state.setdefault(NONCE, 0)
    widget = f"spend-{month:%Y-%m}-{nonce}-{version:x}-{i18n.language()}"
    # A grid drawn in the last run keeps its start. A new one, also back from another page, where
    # Streamlit dropped the edits, starts from the draft.
    bases = st.session_state.get(BASE, {}) if widget in st.session_state else {}
    initial: Amounts = bases.get(
        widget, applied(saved, st.session_state.get(DRAFTS, {}).get(month, {}))
    )
    st.session_state[BASE] = {widget: initial}
    cats = sorted({*plan, *initial, *actuals.categories(recorded)}, key=str.casefold)
    shown = [(cat, initial.get(cat)) for cat in cats]
    above = st.empty()  # the clashes, known after the grid: the sticky bar has no room
    st.data_editor(
        pd.DataFrame(
            {
                "category": pd.Series(cats, dtype=str),  # text also without a row
                "plan": pd.Series([plan.get(cat) for cat in cats], dtype=float),
                "actual": pd.Series([actual for _, actual in shown], dtype=float),
            }
        ),
        column_config={
            c.name: st.column_config.NumberColumn(
                _(HEADERS[c.name]), width=c.width, format=EUR_COLUMN
            )
            if c.type == "number"
            else st.column_config.TextColumn(_(HEADERS[c.name]), width=c.width)
            for c in COLUMNS
        },
        disabled=["plan"],
        num_rows="dynamic",
        hide_index=True,
        width="content",  # fixed widths: the total row below lines up
        height="content",
        placeholder="",
        key=widget,
        on_change=_keep,
        args=(widget, month, shown, saved),
    )
    amounts = entered(shown, st.session_state[widget])
    _draft(month, amounts, saved)  # also drops a draft that the file holds by now
    draft: Draft = st.session_state[DRAFTS].get(month, {})
    clashes = merge(saved, draft)[1]
    flagged = guard.review(changes(saved, amounts), key="spend")
    filled = take_plan(plan, amounts)
    with above.container():
        _clashes(month, draft, clashes)
    with st.container(key="spend-actions"):
        st.html(
            total_row(
                COLUMNS,
                {
                    "category": _("total"),
                    "plan": format_eur(sum(plan.values())),
                    "actual": format_eur(sum(amounts.values())),
                },
            )
        )
        # A new grid shows the filled cells: the editor cannot take them as edits.
        if st.button(_("Take plan"), key="spend-plan", disabled=filled == amounts):
            _draft(month, filled, saved)
            _fresh()
            st.rerun()
    with st.container(key=HEADER, horizontal=True):  # in the page header, `page` pins it
        discard = st.button(_("Discard"), key="spend-discard", disabled=not draft)
        # keyed, so the label mark does not change its identity: a tap that comes with the edit
        # that turns the mark on or off would be lost
        save = st.button(
            guard.marked(_("Save"), flagged),
            key="spend-save",
            type="primary",
            disabled=not draft or bool(clashes),
        )
    if discard:
        st.session_state[DRAFTS].pop(month, None)
        _fresh()
        st.rerun()
    if save:  # outside the header: a failed save shows its error under the grid
        _save(data_dir, month, draft)


def _cents(value: float | None) -> str:
    return _("empty") if value is None else format_eur(value, cents=True)


# The two choices for a clash: take the file, keep yours; for one category or for all
CHOICES = {
    False: (N_("Take the file"), N_("Keep yours")),
    True: (N_("Take the file for all"), N_("Keep yours for all")),
}


def _clashes(month: date, draft: Draft, clashes: list[Clash]) -> None:
    """The edited categories that the file changed since their edit began, each with both amounts
    and a choice, and one choice for all of several. Save waits for them, so a new one also shows
    as a toast: the list above the grid can be out of view."""
    if new := [c.category for c in clashes if c not in st.session_state.get(CLASHES, [])]:
        st.toast(
            _("{categories} changed elsewhere since your edit: choose above the grid").format(
                categories=", ".join(new)
            ),
            icon=":material/sync_problem:",
            duration="long",
        )
    st.session_state[CLASHES] = clashes
    if not clashes:
        return
    st.warning(
        _("Changed elsewhere since your edit, choose before you save."),
        icon=":material/sync_problem:",
    )
    rows = [
        (
            [clash],
            f"one-{clash.category}",
            _("**{category}**: file {file}, yours {yours}, at the start {start}").format(
                category=literal(clash.category),
                file=_cents(clash.file),
                yours=_cents(clash.yours),
                start=_cents(clash.was),
            ),
            False,
        )
        for clash in clashes
    ]
    for some, key, text, every in rows + ([(clashes, "all", "", True)] * (len(rows) > 1)):
        if (yours := _choice(key, text, every=every)) is not None:
            st.session_state[DRAFTS][month] = chosen(draft, some, yours=yours)
            if not yours:
                _fresh()  # the grid shows the file
            st.rerun()


def _choice(key: str, text: str, *, every: bool) -> bool | None:
    """`Take the file` and `Keep yours` after `text`, for all clashes with `every`: True when
    yours, False when the file, None without a tap."""
    take_label, keep_label = CHOICES[every]
    with st.container(horizontal=True, vertical_alignment="center"):
        if text:
            st.markdown(text)
        take = st.button(_(take_label), key=f"spend-take-{key}")
        keep = st.button(_(keep_label), key=f"spend-keep-{key}")
    return True if keep else False if take else None


def _save(data_dir: Path, month: date, draft: Draft) -> None:
    """Merge the draft into the month as the file holds it under the lock of the write: a clash
    since this run read the file saves nothing, and the rerun lists it."""
    try:
        actuals.save_draft(data_dir, month, draft, source=source())
    except ClashError as err:
        tell(
            _("Not saved: {categories} changed elsewhere since your edit").format(
                categories=", ".join(c.category for c in err.clashes)
            ),
            warn=True,
        )
    except OSError as err:
        st.error(_("Not saved: {reason}").format(reason=reason(err)))
        return
    else:
        st.session_state[DRAFTS].pop(month, None)
        if (last := st.session_state.get(LAST)) and last.month == month:
            del st.session_state[LAST]  # its sum is the one before the save
        tell(_("Saved {month}").format(month=f"{month:%Y-%m}"))
    st.rerun()


def _look(row: pd.Series[Any], last: int, signed: Collection[str]) -> list[str]:
    """The total row bold, the difference and its share (`signed`, as the headers say them)
    green when the plan was undercut by a euro or more, red when it was overrun: as it shows."""
    shown = format_eur(float(row[_(HEADERS["difference"])]))
    color = "" if shown == format_eur(0) else f"color: {LOSS if '-' in shown else GAIN}; "
    bold = TOTAL if row.name == last else ""
    return [bold + (color if c in signed else "") for c in row.index]


def _money(value: object) -> str:
    return format_eur(value) if isinstance(value, float) else "–"


def _share(value: object) -> str:
    if not isinstance(value, float) or pd.isna(value):
        return "–"
    return f"{value:+.1%}" if round(value, 3) else "0.0%"


def _table(comparison: Comparison) -> None:
    """Per category the sums over its months, then the total. `months` stays the second column:
    `ui/page.css` hides it in portrait by position (`tr > :nth-child(2)`)."""
    lines = comparison.by_category()
    total = sum((line for line, _count in lines.values()), NONE)
    header = {column: _(words) for column, words in HEADERS.items()}
    frame = pd.DataFrame(
        [
            {
                header["category"]: cat,
                header["months"]: count,
                header["plan"]: line.plan,
                header["actual"]: line.actual,
                header["difference"]: line.difference,
                header["share"]: line.share,
            }
            for cat, (line, count) in [
                *lines.items(),
                (_("total"), (total, len(comparison.cells))),
            ]
        ]
    )
    last, signed = len(frame) - 1, (header["difference"], header["share"])
    money = pd.Index([header["plan"], header["actual"], header["difference"]])
    st.container(key="table-spend").table(
        frame.style.apply(lambda row: _look(row, last, signed), axis=1)
        .format(_money, subset=money)
        .format(_share, subset=[header["share"]]),
        border="horizontal",
        hide_index=True,
    )


def _comparison(
    rows: list[cashplan.Row],
    scenario: Scenario,
    recorded: Months,
    beside: DeltaGenerator,
) -> None:
    """The complete months: the quick add records the current one on the go. The table `beside`
    the month, the charts below both."""
    beside.subheader(_("Actual against plan"))
    this = date.today().replace(day=1)
    if not (complete := {month: sums for month, sums in recorded.items() if month < this}):
        beside.info(_("No complete month recorded yet."))
        return
    comparison = Comparison.of(complete, rows, scenario)
    with beside:
        _table(comparison)
    colors = row_colors(
        [str(r.get("cat", "")) for r in rows if cashplan.role(r) == cashplan.EXPENSE]
    )
    left, right = st.container(key="spend-charts").columns(2, gap="large")
    months, less = _("Spending per month"), _("Actual less plan per category")
    with left:
        st.markdown(f"**{months}**")
        chart(spend_figure(comparison.by_month(), labels=month_labels(2)), key="spend-months")
    with right:
        st.markdown(f"**{less}**")
        chart(
            bars_figure(
                [
                    Slice((c,), line.difference)
                    for c, (line, _count) in comparison.by_category().items()
                ],
                {(cat,): color for cat, color in colors.items()},
                signed=True,
                compact=is_mobile(),
            ),
            key="spend-deviation",
        )
    n = len(comparison.cells)
    fold(
        ngettext(
            "The last {n} recorded month, at most twelve, without the current one until it ends. "
            "A category counts in a month only when that month has an actual for it. The "
            "difference is actual less plan: below zero more was spent than planned, and the bar "
            "grows to the left. A stream paid every n months counts one n-th in each month, so "
            "compare over several months.",
            "The last {n} recorded months, at most twelve, without the current one until it "
            "ends. A category counts in a month only when that month has an actual for it. The "
            "difference is actual less plan: below zero more was spent than planned, and the bar "
            "grows to the left. A stream paid every n months counts one n-th in each month, so "
            "compare over several months.",
            n,
        ).format(n=n),
        _("How to read the comparison"),
    )


def _phase(assumptions: Assumptions, scenario: Scenario, month: date) -> str:
    """The phase of `month` in `scenario` as the pages name it."""
    phase = str(scenario.phase_of(month))
    return assumptions.phase_labels.get(phase, phase)


def page(streams: RowFile) -> None:
    save_in_header(HEADER)  # Save and Discard at the top as on the other pages with grids
    data_dir = streams.data_dir
    st.title(_("Spend"))
    keyboard()
    name = first_scenario(data_dir)
    scenario = load_scenario(data_dir / scenario_file(name))
    assumptions = load_assumptions(data_dir)
    rows = cashplan.with_gkv(
        cashplan.with_levels([dict(r) for r in streams.rows()], assumptions.indices),
        assumptions.tax.gkv_from,
    )
    recorded = actuals.read(data_dir)
    today = date.today()
    options = months(recorded, today)
    known = sorted(
        {*actuals.planned(rows, scenario, today.replace(day=1)), *actuals.categories(recorded)},
        key=str.casefold,
    )
    _add(data_dir, options, known)
    # the month and the comparison side by side where both fit (`ui.PAGE_STYLE`), else stacked
    row = st.container(horizontal=True, gap="large", key="spend-columns")
    with row.container(key="spend-whole"):
        st.subheader(_("A whole month"))
        month = _month(options)
        _status(Coverage.of(recorded, rows, scenario, month))
        # The total row and `Take plan` stick to the bottom of the screen only while the grid
        # shows.
        with st.container(key="spend-grid"):
            _entry(data_dir, actuals.planned(rows, scenario, month), recorded, month)
        fold(
            _(
                "The grid holds a whole month per category, spending below zero as in your "
                "streams, a refund above zero. `plan` is what your expense streams pay in that "
                "month, as on the Cashflows page, in the phase `{phase}` of your main scenario "
                "`{scenario}`: the "
                "amounts as written, in euros of the simulation start, without inflation and "
                "without the events of the scenario. A stream changed in place without a "
                "successor row changes past months too. `Take plan` fills the empty `actual` "
                "cells with the plan, so you only change what differs. An empty cell records "
                "nothing: enter 0 for a category without spending. A new row records a category "
                "that the plan does not have, for example cash. Rows of one category add up, a "
                "deleted row records nothing. `Save` at the top of the page, as on the other "
                "pages, saves the month that the grid shows into `actuals.csv`. The other "
                "categories keep what the file holds by then, also after a quick add on another "
                "device. A category that you edited and that changed elsewhere since shows both "
                "amounts: take the file or keep yours. Unsaved edits stay with their month while "
                "you look at another, `Discard` drops them. A month is recorded when every "
                "category of its plan has an actual, 0 included: the line above the grid counts "
                "them, and the Overview names the first complete month that lacks one."
            ).format(phase=_phase(assumptions, scenario, month), scenario=name),
            _("How to enter a month"),
        )
    _comparison(rows, scenario, recorded, row.container(key="spend-against"))
