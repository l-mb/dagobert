"""Landing page: net worth today, the outlook of the plan, what needs attention, where the money
sits and the record so far. The roll forward keeps the keys of the files in its words (rule
`i18n`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st

from dagobert import actuals, cashplan, revisions, rollforward
from dagobert.history import actual_values
from dagobert.i18n import N_, _, ngettext
from dagobert.loader import load_assets, load_assumptions, load_plan, load_scenario, written
from dagobert.model.assets import Asset, Loan, TermDeposit
from dagobert.model.events import BuyPropertyEvent, Event
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Plan, Scenario
from dagobert.model.streams import StreamKind
from dagobert.money import format_eur
from dagobert.report.tracker import history_figure
from dagobert.scenariofiles import concrete_scenarios, first_scenario, scenario_file
from dagobert.store import RowFile, streams_file
from dagobert.ui import (
    EVENT,
    SCENARIO,
    TAB,
    cashflows,
    chart,
    fixed,
    fold,
    is_mobile,
    literal,
    mode,
    month_labels,
    outlook,
    page_link,
    runs,
    save,
    source,
    summary,
)
from dagobert.ui.assets import TRADES, opened
from dagobert.ui.save import VALUE_FIELD, reason
from dagobert.ui.spend import SHOW

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PLAN_MONTHS, DUE_MONTHS = 3, 12
PHONE_ITEM = 140  # pixels of the item of the roll on a phone: old and new fit beside it
# pixels of a grid of the roll: on a phone in landscape a swipe beside it still scrolls the page
GRID, PHONE_GRID = 250, 160
ROW = 35  # pixels of a row of a grid, also of its header
# pixels of the asset rings and of the recorded net worth beside them; a phone stacks them, and
# its rings take `summary.PHONE_RINGS`
CHART_HEIGHT, PHONE_CHART_HEIGHT = 460, 340
RECORDS = mode.Item(mode.Sort.DATA, ("records",))  # the recorded net worth, against the plan too
SNAPSHOT, SPEND = (mode.Item(mode.Sort.PAGE, (title,)) for title in ("Snapshot", "Spend"))
# after the setup: on to the Explorer and the scenarios, past the pages that record (owner,
# 2026-10-13: people configure once and explore); also the start page (`welcome`)
EXPLORE = N_("Explore your plan on the Explorer page and compare its scenarios.")
# the pages of the records that the mode and the features show: they are no part of the plan
KEEP = {
    frozenset({"Snapshot", "Spend"}): N_(
        "The Snapshot and Spend pages keep records, when you want to: the plan needs none."
    ),
    frozenset({"Snapshot"}): N_(
        "The Snapshot page keeps records of your assets, when you want to: the plan needs none."
    ),
    frozenset({"Spend"}): N_(
        "The Spend page keeps your actual spending, when you want to: the plan needs none."
    ),
}


def explore(view: mode.View) -> str:
    """The line to the Explorer, with the pages of the records that `view` shows: a page that the
    mode or a feature hides goes unnamed."""
    keep = KEEP.get(frozenset(page.key[0] for page in (SNAPSHOT, SPEND) if view.shows(page)))
    return " ".join([_(EXPLORE), *([_(keep)] if keep else [])])


@dataclass(frozen=True)
class Link:
    """The page that fixes an item, by its title in the navigation, with the query that opens its
    place there. Its label is as written (a file), else `Open <page>` in words (`said`)."""

    page: str
    label: str | None = None
    query: Mapping[str, str] = field(default_factory=dict)

    def said(self) -> str:
        return self.label or _("Open {page}").format(page=_(self.page))


CASHFLOWS = Link("Cashflows")


def edit(asset: Asset, *fields: str) -> Link:
    """The row of `asset` on the Assets page, with `fields` to check (`assets.opened`)."""
    return Link("Assets", query=opened(asset.id, *fields))


def dated(asset: Asset) -> Link:
    """The value of `asset` and its date on the Assets page."""
    return edit(asset, VALUE_FIELD.get(asset.kind, "value"), "asof")


def spend_month(month: date) -> Link:
    """The month on the Spend page."""
    return Link("Spend", query={SHOW: f"{month:%Y-%m}"})


def placed(chain: Sequence[tuple[Path, Scenario]], event: Event) -> Link:
    """The type of `event` in the `Events` tab of the file of the `extends` chain that writes it,
    the nearest first (`loader.written`), else of the scenario."""
    file = next((f for f, own in reversed(chain) if event in own.events), chain[-1][0])
    return Link("Scenarios", query={SCENARIO: file.stem, EVENT: event.type})


@dataclass(frozen=True)
class Notice:
    when: date | None  # None: never dated
    item: str
    what: str
    late: bool = False  # the inputs need an update
    fix: Link | None = None  # the page that updates them


def attention(data_dir: Path, scenario: str, day: date, *, stale: bool = True) -> list[Notice]:
    """What needs a look on `day`, by date: a simulation start before the month of `day`, with
    `stale` the values that need an update (`summary.needs_update`), the changes of the plan with
    the events of `scenario` in the next `PLAN_MONTHS` months, the term deposits and fixed loan
    rates that end within `DUE_MONTHS` months or ended already, the months without actual
    spending (`actuals.missing`), a plan that draws a disability without a pension from
    points, which pays no EM-Rente then, and the savings plans that pause (`_paused`)."""
    plan = load_plan(data_dir, data_dir / scenario_file(scenario))
    assets = load_assets(data_dir)
    on_sale = summary.selling(plan.scenario)
    notices = [
        *_lagging(load_assumptions(data_dir).start, day),
        *_no_em_rente(data_dir, scenario, plan),
        *_paused(data_dir, scenario),
        *(
            Notice(
                a.asof,
                a.label,
                _("last updated more than {n} months ago").format(
                    n=summary.update_months(a, on_sale)
                )
                if a.asof
                else _("the value has no date yet"),
                late=True,
                fix=dated(a),
            )
            for a in assets
            if stale and summary.needs_update(a, day, on_sale)
        ),
        *_plan_changes(data_dir, scenario, plan, day),
        *(
            notice
            for a in assets
            if (notice := _end(a, plan.assumptions.refinance_rate, day))
            and notice.when
            and months_between(day, notice.when) <= DUE_MONTHS
        ),
        *(
            [
                Notice(
                    gap.month,
                    _("actual spending"),
                    _("{month}: {recorded} of {planned} planned categories").format(
                        month=f"{gap.month:%Y-%m}", recorded=gap.recorded, planned=gap.planned
                    ),
                    True,
                    spend_month(gap.month),
                )
            ]
            if (
                gap := actuals.missing(
                    actuals.read(data_dir),
                    [dict(r) for r in streams_file(data_dir).rows()],
                    plan.scenario,
                    day,
                )
            )
            else []
        ),
    ]
    return sorted(notices, key=lambda n: (n.when or date.min, n.item))


def _no_em_rente(data_dir: Path, scenario: str, plan: Plan) -> list[Notice]:
    """A plan with the risk of a disability whose pension, if any, takes no points: an EM-Rente
    rides on the statutory pension from points (rule `disability`). With points, a forced onset
    (`disability.at`) that the run of the files leaves without an EM-Rente (the Wartezeit or the
    3-in-5 rule is not met), linked to where the onset is written."""
    if plan.assumptions.disability is None:
        return []
    if not any(s.kind == StreamKind.PENSION and s.points is not None for s in plan.all_streams):
        what = _("no pension from points, so a disability pays no EM-Rente")
        return [Notice(None, _("disability"), what, fix=CASHFLOWS)]
    if plan.assumptions.disability.at is None or not (
        (r := fixed.result(data_dir, scenario)) and r.onset[0] >= 0 and not r.em[0]
    ):
        return []
    file = next(
        (
            f
            for f, own in reversed(written(data_dir / scenario_file(scenario)))
            if isinstance(block := own.overrides.get(rollforward.DISABILITY), dict)
            and "at" in block
        ),
        data_dir / "assumptions.yaml",
    )
    at = r.months[r.onset[0]]
    what = _("the disability from {month} pays no EM-Rente (insurance time or contributions)")
    link = fix(rollforward.Passed(file.name, at, "", rollforward.DISABILITY, ()))
    return [Notice(at, _("disability"), what.format(month=f"{at:%Y-%m}"), fix=link)]


def _paused(data_dir: Path, scenario: str) -> list[Notice]:
    """The savings plans that pause in the run of the files: the engine marks the first month in
    which the cash does not cover the rate of each (`savings plan`, rule `engine`), whenever it
    lies; linked to the Cashflows page, where its rate and the spending change."""
    if (run := fixed.result(data_dir, scenario)) is None:
        return []
    what = _("pauses: the cash does not cover its rate")
    return [
        Notice(m.month, m.detail, what, fix=CASHFLOWS)
        for m in run.markers
        if m.kind == "savings plan"
    ]


def _lagging(start: date, day: date) -> list[Notice]:
    behind = months_between(start, day)
    what = ngettext(
        "{n} month ago, see Roll forward", "{n} months ago, see Roll forward", behind
    ).format(n=behind)
    return [Notice(start, _("simulation start"), what, late=True)] if behind > 0 else []


def _plan_changes(data_dir: Path, scenario: str, plan: Plan, day: date) -> list[Notice]:
    """The dated changes of the Cashflows page, each with its effect in the phase of its date,
    and the purchases of a property, each with what it takes from the cash. A change of a stream
    links to the Cashflows page, one of an event and a purchase to the event (`placed`)."""
    rows = cashflows.estimated([dict(r) for r in streams_file(data_dir).rows()], day, plan)
    labels = plan.assumptions.phase_labels
    chain = written(data_dir / scenario_file(scenario))
    changes = [
        *cashplan.scheduled(rows, day, list(labels), paired=True),
        *cashplan.scenario_changes(rows, plan, day, list(labels)),
    ]
    return [
        Notice(
            c.when,
            c.name,
            f"{c.what}, {_effect(c, str(plan.scenario.phase_of(c.when)), labels)}",
            fix=CASHFLOWS if c.event is None else placed(chain, c.event),
        )
        for c in changes
        if c.when is not None and months_between(day, c.when) <= PLAN_MONTHS
    ] + [
        Notice(e.at, e.property.label, _purchase(e), fix=placed(chain, e))
        for e in plan.bought
        if e.at is not None and e.at > day and months_between(day, e.at) <= PLAN_MONTHS
    ]


def _purchase(ev: BuyPropertyEvent) -> str:
    """What a purchase takes from the cash and the liquid assets, nominal at its date."""
    if ev.loan is None:
        return _(
            "bought for {price}, {cost} with the transfer tax and the costs from cash and liquid "
            "assets"
        ).format(price=format_eur(ev.price), cost=format_eur(ev.cost))
    return _(
        "bought for {price}, {cost} with the transfer tax and the costs: {paid} from cash and "
        "liquid assets"
    ).format(
        price=format_eur(ev.price),
        cost=format_eur(ev.cost),
        paid=format_eur(ev.cost + ev.loan.balance),
    )


def _effect(change: cashplan.Change, phase: str, labels: Mapping[str, str]) -> str:
    monthly = change.monthly[phase]
    return (
        _("{amount} per month in {phase}").format(
            amount=format_eur(monthly, signed=True), phase=labels[phase]
        )
        if round(monthly)
        else _("no effect in {phase}").format(phase=labels[phase])
    )


def _end(asset: Asset, refinance: float, day: date) -> Notice | None:
    """The maturity of a term deposit or the end of the fixed rate of a loan. When it lies in
    the past, the inputs need an update."""
    match asset:
        case TermDeposit(matures=end) if end < day:
            what, late = _("matured, the inputs need an update"), True
            fields: tuple[str, ...] = ("matures", "value")
        case TermDeposit(matures=end):
            what = _("matures, pays {value}").format(value=format_eur(asset.value_at(end)))
            late, fields = False, ("matures",)
        case Loan(fixed_until=date() as end) if months_between(day, end) < 0:
            what, late = _("the fixed rate ended, the inputs need an update"), True
            fields = ("fixed_until", "rate")
        case Loan(fixed_until=date() as end):
            what = _(
                "last month at the fixed rate of {rate}, the plan then uses {refinance}"
            ).format(rate=f"{asset.rate:.2%}", refinance=f"{refinance:.2%}")
            late, fields = False, ("fixed_until", "rate")
        case _:
            return None
    return Notice(end, asset.label, what, late, edit(asset, *fields))


def _linked(
    key: str, header: Sequence[str], rows: Sequence[tuple[Sequence[str], Link | None]]
) -> None:
    """A table of Markdown cells whose last column links a row to the page that fixes it.
    `st.table` takes no widget, so the container `key` is a CSS grid of four columns, and each row
    a container on its columns (`ui/page.css`): a row without a link leaves the last one empty."""
    with st.container(key=key):
        with st.container():
            for cell in header:
                st.caption(cell)
        for cells, fix in rows:
            with st.container():
                for cell in cells:
                    st.markdown(cell)
                if fix:
                    page_link(fix.page, fix.said(), fix.query)


def _date(text: str, late: bool) -> str:
    """A date cell, red and bold when the inputs need an update."""
    return f":red[**{text}**]" if late else text


# What the attention table lists, each part while the page shows it: the values that need an
# update while records are kept, the month without actual spending while the Spend page shows
LISTS = (
    N_(
        "The table lists values older than their update interval, and values without a date. "
        "The interval is **check every** of the asset on the Assets page, else 12 months, never "
        "for a term deposit (its contract gives the value) or a property. A property that the "
        "scenario sells on a date takes six months while the sale runs. An empty asset needs no "
        "date."
    ),
    N_(
        "The table lists plan changes in the next three months, and term deposits and fixed loan "
        "rates that end within twelve months or have ended. A red date needs an update of the "
        "inputs. The link of a row opens the place where you change it: an asset on its row of "
        "the Assets page, the fields to check marked, a change of the plan at its stream on the "
        "Cashflows page or at its event on the Scenarios page. The plan changes use the events of "
        "your main scenario, {scenario}, which the top of the Scenarios page sets. Each shows its "
        "effect per month in the phase of its date, in euros of the start of the plan."
    ),
    N_(
        "A savings plan that pauses in your main scenario shows with the first month in which the "
        "cash does not cover its rate: lower it or the spending on the Cashflows page."
    ),
    N_(
        "While you keep your actual spending on the Spend page (a record in the last three "
        "months), the table also names the first complete month without a record since your "
        "first one, with a link to that month there."
    ),
    N_(
        "A start of the plan before the current month shows how far it lags: the **Roll "
        "forward** below moves it."
    ),
)


def _attention(data_dir: Path, view: mode.View) -> None:
    today = date.today()
    scenario = first_scenario(data_dir)
    st.subheader(_("Needs attention"))
    stale = view.shows(RECORDS) or view.shows(TRADES)
    notices = attention(data_dir, scenario, today, stale=stale)
    if notices:
        _linked(
            "overview-attention",
            (_("date"), _("item"), _("what"), ""),
            [
                (
                    (
                        _date(n.when.isoformat() if n.when else _("never"), n.late),
                        literal(n.item),
                        literal(n.what),
                    ),
                    n.fix,
                )
                for n in notices
            ],
        )
    else:
        st.caption(_("Nothing."))
    values, planned, paused, spent, lag = LISTS
    parts = [
        *([values] if stale else []),
        planned,
        paused,
        *([spent] if view.shows(SPEND) else []),
        lag,
    ]
    name = literal(load_scenario(data_dir / scenario_file(scenario)).name)
    fold(" ".join(_(part).format(scenario=name) for part in parts), _("What the table lists"))


ROLLED = "overview-rolled"  # the summary of a roll, shown once after the rerun
SHOWN = "overview-roll-shown"  # the inputs of the roll that the last run listed, by its month
ROLL, OPEN = "roll", "open"  # the query parameter of a link that opens the `Roll forward`
ROLL_HELP = N_(
    "The roll sets `start` in `assumptions.yaml` to the chosen month. The amounts in euros of the "
    "old start that follow the consumer prices change by the consumer prices between the two "
    "months, rounded to cents: `amount`, `gross` and `point_value` of the `cpi` streams (the "
    "pension too), in `cashflows.yaml` and in `add_stream` and `set_stream` events, the "
    "`liquid_below` of a conditional sale, the `spending.reference` of the spending rule, the "
    "`cash` of an inheritance without a month, and the care cost and the Altersvorsorgedepot "
    "contribution when they follow the consumer prices, also as scenario overrides. The rest "
    "stays: nominal amounts, the streams of the other indices (for example a salary index) and "
    "the event amounts that are nominal at their date (severance, lump sum, sale price). A stream "
    "paid every n months without `start` counts its "
    "payment months from the start, so the roll writes the old start into it, in `cashflows.yaml` "
    "and in `add_stream` events, and it pays in the same months as before. A business that runs "
    "before the new start would count it as its founding, which starts the years of the half "
    "Regelbeitrag: the roll writes its first month as `founded` into the options "
    "`tax.self_employed` that its scenarios take. Losses that the plan carries to the new start "
    "for the income tax (a Verlustvortrag, such as of a let flat) would be lost too: the roll "
    "writes them as `loss_carryforward` into the options `tax` that its scenarios take, the "
    "losses of capital income as `capital_losses`. A gift "
    "before the new start moves from its scenario file into the gifts before the start of its "
    "relative on the Assumptions page, with the Schenkungsteuer that the roll computes, so the "
    "ten years of §14 ErbStG keep it. The roll refuses while an event other than a stream event "
    "or a gift lies before the new start. The roll is one revision. "
    "The `Changes since` table of the Cashflows page shows what it changed in the streams."
)
# a loss pot that the roll carries, by its key: the line above its grid, the line of the summary
CARRIED = {
    rollforward.LOSSES: N_(
        "The plan carries losses of the income tax to {month}: it writes them as "
        "`loss_carryforward`, so they offset the income after it:"
    ),
    rollforward.CAPITAL_LOSSES: N_(
        "The plan carries losses of capital income to {month}: it writes them as "
        "`capital_losses`, so they offset the capital income after it:"
    ),
}
KEPT = {
    rollforward.LOSSES: N_("{file} keeps the losses carried, {amount}, as `loss_carryforward`."),
    rollforward.CAPITAL_LOSSES: N_(
        "{file} keeps the losses of capital income carried, {amount}, as `capital_losses`."
    ),
}
# the asset values after a roll, which no roll changes, by whether the Snapshot page shows
VALUES = {
    True: N_("Asset values stay as they are: the Snapshot page records them."),
    False: N_("Asset values stay as they are: the Assets page updates them."),
}
# the end of the refusal of a roll, by whether the Snapshot page shows
OUTCOME = {
    True: N_("Then record the real outcome, for example the sale proceeds, on the Snapshot page."),
    False: N_("Then enter the real outcome, for example the sale proceeds, on the Assets page."),
}


def _roll_forward(data_dir: Path, view: mode.View) -> None:
    """While the simulation start lags the current month: move it to a later month. Its words name
    the pages that `view` shows."""
    if done := st.session_state.pop(ROLLED, None):
        st.success(done)
    start = load_assumptions(data_dir).start
    behind = months_between(start, date.today())
    if behind <= 0:
        return
    with st.expander(
        ngettext(
            "Roll forward: the simulation starts {start}, {n} month ago",
            "Roll forward: the simulation starts {start}, {n} months ago",
            behind,
        ).format(start=f"{start:%Y-%m}", n=behind),
        expanded=st.query_params.get(ROLL) == OPEN,  # a link from the Assumptions page
        key="overview-roll-open",
    ):
        values = _(VALUES[view.shows(SNAPSHOT)])
        fold(f"{_(ROLL_HELP)} {values}", _("What the roll changes"))
        new = st.selectbox(
            _("New start"),
            [add_months(start, n) for n in range(behind, 0, -1)],
            format_func=lambda month: f"{month:%Y-%m}",
            key="overview-roll-to",
        )
        # the inputs of the list that the button belongs to: a tap reruns the page and draws the
        # list again, from the inputs as they are then. Without them every input counts as new.
        shown = st.session_state.get(SHOWN, {}).get(new, [])
        st.session_state[SHOWN] = {new: rollforward.seen(data_dir)}
        try:
            roll = rollforward.check(data_dir, new)
        except ValueError as error:
            st.error(str(error))
            return
        _roll_check(roll, len(concrete_scenarios(data_dir)), snapshot=view.shows(SNAPSHOT))
        if st.button(
            _("Roll forward to {month}").format(month=f"{new:%Y-%m}"),
            type="primary",
            disabled=bool(roll.events),
            key="overview-roll",
        ):
            try:
                rolled = rollforward.apply(data_dir, new, source=source("roll forward"), read=shown)
            except revisions.ConflictError as error:
                st.error(
                    _(
                        "Nothing changed: the inputs changed since the list above ({changed}). It "
                        "shows them now."
                    ).format(changed=save.changed_at(error))
                )
            except (OSError, ValueError) as error:
                st.error(_("Nothing changed: {reason}").format(reason=reason(error)))
            else:
                st.session_state[ROLLED] = _rolled(rolled)
                st.rerun()


def _roll_check(roll: rollforward.Roll, scenarios: int, *, snapshot: bool) -> None:
    """What the roll changes and what refuses it; the real outcome of a passed event goes to the
    Snapshot page while it shows (`snapshot`), else to the Assets page."""
    new = f"{roll.cpi.new:%Y-%m}"
    if roll.events:
        refused = _(
            "**Refused.** These events lie before {month}, and only you know what became of "
            "them. Remove each event from its file on the Scenarios page (the link of the file "
            "opens its events of that type), together with what it stands for: for a sale the "
            "property, the loans it repays and the streams it ends (`tags`) or starts "
            "(`after_sale_of`); for a payment the asset it fills; for the purchase of a "
            "property add the property and its loan on the Assets page first."
        ).format(month=new)
        st.error(f"{refused} {_(OUTCOME[snapshot])}")
        _passed(roll.events, scenarios, "events")
    if roll.phases:
        st.warning(
            _(
                "The runs start after these phases. What they set up before {month} is lost, for "
                "example the salary that sets the ALG1 of a later phase without a job. The link "
                "of the file opens its phases on the Scenarios page."
            ).format(month=new)
        )
        _passed(roll.phases, scenarios, "phases")
    if roll.undated:
        st.warning(
            _(
                "These loans have no date for their balance: the run takes their balance as the "
                "balance at {month}. Give each its balance and its date on the Assets page:"
            ).format(month=new)
        )
        with st.container(horizontal=True):
            for loan in roll.undated:
                page_link("Assets", loan.label, dated(loan).query)
    cpi = roll.cpi
    st.markdown(
        _("Consumer prices {old} to {new}: **× {factor}**, from {source}.").format(
            old=f"{cpi.old:%Y-%m}", new=new, factor=f"{cpi.factor:.4f}", source=cpi.source
        )
    )
    if cpi.estimated:  # while the navigation shows the page (`ui.page_link`)
        page_link("Data", _("Data: fetch newer consumer prices"))
    st.markdown(_("The roll changes {n} amounts:").format(n=len(roll.changes)))
    _roll_grid(
        [
            {
                "item": c.item,
                "old": format_eur(c.old, cents=True),
                "new": format_eur(c.new, cents=True),
                "file": c.file,
            }
            for c in roll.changes
        ],
        ["item", "old", "new", "file"],
        PHONE_ITEM if is_mobile() else None,
    )
    if roll.periodic:
        st.markdown(
            _(
                "It writes the old start {old} as `start` into {n} streams paid every n months, so "
                "they keep their payment months:"
            ).format(old=f"{cpi.old:%Y-%m}", n=len(roll.periodic))
        )
        _roll_grid(
            [{"stream": p.name, "every": p.every, "file": p.file} for p in roll.periodic],
            ["stream", "every", "file"],
        )
    if roll.founded:
        st.markdown(
            _(
                "A business runs before {month}: it writes its first month as `founded`, so the "
                "years of its half Regelbeitrag keep their start:"
            ).format(month=new)
        )
        _roll_grid(
            [
                {
                    "founded": f"{f.month:%Y-%m}",
                    "scenarios": _reach(f.scenarios, scenarios),
                    "file": f.file,
                }
                for f in roll.founded
            ],
            ["founded", "scenarios", "file"],
        )
    for key, words in CARRIED.items():
        if pots := [c for c in roll.carried if c.key == key]:
            st.markdown(_(words).format(month=new))
            _roll_grid(
                [
                    {
                        key: format_eur(c.amount, cents=True),
                        "scenarios": _reach(c.scenarios, scenarios),
                        "file": c.file,
                    }
                    for c in pots
                ],
                [key, "scenarios", "file"],
            )
    if roll.gifts:
        st.markdown(
            _(
                "These gifts lie before {month}: it moves each into the gifts before the start of "
                "its relative, with the tax that it computes on them:"
            ).format(month=new)
        )
        _roll_grid(
            [
                {
                    "item": g.item,
                    "month": f"{g.at:%Y-%m}",
                    "value": format_eur(g.value, cents=True),
                    "tax": format_eur(g.tax, cents=True),
                    "file": g.file,
                }
                for g in roll.gifts
            ],
            ["item", "month", "value", "tax", "file"],
        )


# the headers of the grids of the roll in words, but its keys (`every`, `founded`)
ROLL_HEADERS = {
    "item": N_("item"),
    "old": N_("old"),
    "new": N_("new"),
    "file": N_("file"),
    "stream": N_("stream"),
    "scenarios": N_("scenarios"),
    "month": N_("month"),
    "value": N_("value"),
    "tax": N_("tax"),
}


def _roll_grid(rows: list[dict[str, object]], columns: list[str], item: int | None = None) -> None:
    """A grid of the roll at its fixed height, or as high as its rows when they need less, its
    `item` column `item` pixels wide."""
    height = PHONE_GRID if is_mobile() else GRID
    st.dataframe(
        pd.DataFrame(rows, columns=columns),
        column_config={
            column: st.column_config.Column(
                _(ROLL_HEADERS[column]), width=item if column == "item" else None
            )
            for column in columns
            if column in ROLL_HEADERS
        },
        hide_index=True,
        height="content" if ROW * (len(rows) + 1) + 3 <= height else height,
    )


def _passed(items: list[rollforward.Passed], scenarios: int, what: str) -> None:
    """The file links to its place on the Scenarios page (`fix`)."""
    _linked(
        f"overview-passed-{what}",
        (_("date"), _("item"), _("scenarios"), _("file")),
        [
            (
                (
                    f"{p.at:%Y-%m}",
                    literal(p.what),
                    literal(_reach(p.scenarios, scenarios)),
                ),
                fix(p),
            )
            for p in items
        ],
    )


def _reach(names: tuple[str, ...], scenarios: int) -> str:
    """The scenarios that an item reaches, `all` for every one of the `scenarios`."""
    return _("all") if len(names) == scenarios else ", ".join(names)


def fix(item: rollforward.Passed) -> Link:
    """The place that fixes an item before the new start: the file that holds it on the
    Scenarios page, on the type of an event in its `Events` tab, a forced onset of a disability
    in its `Overrides`, else on its `Phases`; such an onset of `assumptions.yaml` on the
    Assumptions page."""
    file = Path(item.file)
    if item.kind == rollforward.DISABILITY:
        if file.name == "assumptions.yaml":
            return Link("Assumptions", file.name)
        return Link("Scenarios", file.name, {SCENARIO: file.stem, TAB: "Overrides"})
    where = {EVENT: item.kind} if item.kind else {TAB: "Phases"}
    return Link("Scenarios", file.name, {SCENARIO: file.stem} | where)


def _rolled(roll: rollforward.Roll) -> str:
    cpi, months = roll.cpi, months_between(roll.cpi.old, roll.cpi.new)
    rolled = ngettext(
        "Rolled forward {n} month to {month}. The amounts that follow the consumer prices "
        "changed by × {factor}, from {source}: {changes} amounts in {files}.",
        "Rolled forward {n} months to {month}. The amounts that follow the consumer prices "
        "changed by × {factor}, from {source}: {changes} amounts in {files}.",
        months,
    ).format(
        n=months,
        month=f"{cpi.new:%Y-%m}",
        factor=f"{cpi.factor:.4f}",
        source=cpi.source,
        changes=len(roll.changes),
        files=", ".join(sorted({c.file for c in roll.changes})) or _("no file"),
    )
    periodic = [
        _("{n} streams paid every n months took {old} as `start`.").format(
            n=len(roll.periodic), old=f"{cpi.old:%Y-%m}"
        )
    ]
    founded = (
        _("{file} keeps the founding of a business, {month}, as `founded`.").format(
            file=f.file, month=f"{f.month:%Y-%m}"
        )
        for f in roll.founded
    )
    carried = (
        _(KEPT[c.key]).format(file=c.file, amount=format_eur(c.amount, cents=True))
        for c in roll.carried
    )
    gifts = ngettext(
        "{n} gift moved into the gifts before the start.",
        "{n} gifts moved into the gifts before the start.",
        len(roll.gifts),
    ).format(n=len(roll.gifts))
    return " ".join(
        [
            rolled,
            *(periodic if roll.periodic else []),
            *founded,
            *carried,
            *([gifts] if roll.gifts else []),
        ]
    )


def page(streams: RowFile) -> None:
    """The tiles, the plan, what needs attention, the roll forward, the assets and, while the mode
    and the features show the records (`mode.View`), the recorded net worth and the records
    against the plan."""
    data_dir = streams.data_dir
    scenario, view = first_scenario(data_dir), mode.view(data_dir)
    st.title(_("Overview"))
    summary.tiles(data_dir, "overview")
    plan = st.empty()  # filled last: its Monte Carlo run must not hold up the rest of the page
    if not runs.files_cached(data_dir, concrete_scenarios(data_dir)[scenario]):  # a hit: no wait
        plan.caption(_("Simulating the plan …"))
    _attention(data_dir, view)
    _roll_forward(data_dir, view)
    loaded = load_assets(data_dir)
    kinds = {asset.id: summary.LIQUIDITY[asset.kind] for asset in loaded}
    months = [(month, _by_group(values, kinds)) for month, values in actual_values(data_dir)]
    # side by side once there is a history to chart: its info alone left half the row empty
    assets, recorded = st.columns(2, gap="large") if len(months) > 1 else (st.container(),) * 2
    with assets:
        st.subheader(_("Assets"))
        summary.breakdown(data_dir, CHART_HEIGHT)
    with recorded:
        if view.shows(RECORDS):
            _recorded(months, view)
        else:
            _explore(view)
    mode.off_note(data_dir)
    with plan.container():
        outlook.plan(data_dir, scenario)
    if view.shows(RECORDS):
        outlook.on_track(data_dir, scenario, months, loaded)
    page_link("Cashflows", _("Cashflows: where the money goes"))


def _explore(view: mode.View) -> None:
    """On to the Explorer: people who configure once and explore (owner, 2026-10-14)."""
    st.markdown(explore(view))
    page_link("Explorer", _("Explore scenarios"))


def _recorded(months: outlook.Records, view: mode.View) -> None:
    st.subheader(_("Recorded net worth"))
    if len(months) > 1:
        chart(
            history_figure(
                months,
                labels=month_labels(2),
                height=PHONE_CHART_HEIGHT if is_mobile() else CHART_HEIGHT,
            ),
            key="overview-history",
        )
        st.caption(
            _(
                "Each month with a record shows the liquid and the illiquid assets above zero, the "
                "debt below and a dot for the net worth: the assets less the debt."
            )
        )
    else:
        st.info(_("The chart starts with a second month of records."))
        _explore(view)
    fold(
        _(
            "The values at the end of each month with a record, from the records of the "
            "Snapshot page and the values on the Assets page: an asset without a record in that "
            "month counts with its last value. A line joins only the dots of consecutive months, "
            "so two records far apart show no growth between them that nobody observed. The "
            "chart starts in the first month in which every asset has a value, so an entry never "
            "looks like growth."
        ),
        _("How to read the recorded net worth"),
    )


def _by_group(values: dict[str, float], groups: dict[str, str]) -> dict[str, float]:
    sums = dict.fromkeys(dict.fromkeys(groups.values()), 0.0)
    for asset, value in values.items():
        sums[groups[asset]] += value
    return sums
