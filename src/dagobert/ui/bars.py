"""The bars of one phase, which the Cashflows page and the Flows page share: the outflows per
group with the items of the one picked (`outflow_bars`), the income streams with the non-cash
income of the run (`income_chart`), the colors of the roles of the run (`ROLES`), and the phases
that a scenario reaches (`reached`, `phase_control`)."""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import date
from string import Template

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import cashplan
from dagobert.budget import TAXES, Budget, said
from dagobert.i18n import N_, _
from dagobert.model.plan import Plan
from dagobert.money import format_eur
from dagobert.report.charts import AMBER, BLUE, GREEN, ORANGE, PURPLE
from dagobert.report.tracker import Slice, bars_figure
from dagobert.result import CAPITAL_TAX, CONVERSION, LOAN_PRINCIPAL, NONCASH
from dagobert.ui import chart, is_mobile
from dagobert.ui.tables import key_class, row_colors

RUN = N_("from the run")  # the flows that no stream pays, from the `fixed` run of a scenario
NONCASH_NOTE = N_(  # what the non-cash income of the run is, for every note that names it
    "Non-cash income is the growth of the assets (equity, fixed income, cash, term deposits, "
    "property and policies) and what goes into a policy without passing the cash: the "
    "employer's bAV contributions and subsidies and the Zulage of an Altersvorsorgedepot. It "
    "stays invested. "
    "The growth is nominal, converted to euros of the start like every amount here: the part "
    "of it that only keeps up with inflation does not raise the real net worth. The growth of "
    "equity is before the capital gains tax that a sale owes on it."
)
# Color names the role of a flow of the run, the label names the flow: about twenty categories
# have no distinct hues. The palette of `report.charts`, validated on both themes. The outflow
# bars of the Flows page color every group by its role, the bars of the plan only the groups of
# `GROUP_ROLES`: the other groups of the run stay gray beside the colors of the categories.
ROLES = {
    "income": GREEN,
    "taxes": ORANGE,
    "spending": BLUE,
    "loans": AMBER,
    "savings": PURPLE,
    "hub": "#8a8f98",
}
GROUP_ROLES = {
    TAXES: "taxes",
    CAPITAL_TAX: "taxes",
    LOAN_PRINCIPAL: "loans",
    CONVERSION: "savings",
    NONCASH: "savings",
}
# the line under the outflows by what of them stays in net worth: (loans, a salary conversion),
# each by whether it rounds to a euro; both where only their sum does
KEPT = {
    (True, False): N_("of which {amount} repays loans: stays in net worth"),
    (False, True): N_(
        "of which {amount} is salary conversion into a company pension: stays in net worth"
    ),
    (True, True): N_(
        "of which {amount} repays loans or goes into a company pension: stays in net worth"
    ),
}
NONCASH_LINE = N_(
    "plus {amount} non-cash income: growth of the assets and payments into policies, stays invested"
)
# A new pick of `outflow_bars` scrolls its detail into view, as little as needed, once its chart
# is drawn, the run has ended and the detail has kept its place for ten frames: what fills in
# above it late, such as a slow run, would move it. A hand on the page meanwhile (wheel, touch,
# pointer, key) ends the wait, so the page never jumps late, and so does a minute. The comment
# names the pick: a changed text runs the script again.
_SCROLL = Template("""<script>
// $picked
(() => {
  const hands = ["wheel", "touchstart", "pointerdown", "keydown"];
  const until = Date.now() + 60000;
  let quiet = 0, last = "", touched = false;
  const touch = () => { touched = true; };
  const done = () => hands.forEach((type) => removeEventListener(type, touch, true));
  hands.forEach((type) => addEventListener(type, touch, {capture: true, passive: true}));
  const wait = () => {
    if (touched || Date.now() > until) return done();
    const detail = document.querySelector(".$detail");
    const box = detail?.getBoundingClientRect();
    const ready = detail?.querySelector(".main-svg")
      && !document.querySelector("[data-testid=stStatusWidget]");
    const place = ready ? box.top + " " + box.bottom : "";
    quiet = place && place === last ? quiet + 1 : 0;
    last = place;
    if (quiet < 10) return requestAnimationFrame(wait);
    done();
    detail.scrollIntoView({block: "nearest", behavior: "smooth"});
  };
  wait();
})();
</script>""")


def flows_of(
    rows: list[cashplan.Row], day: date, phase: str, run: Budget | None, *, income: bool
) -> list[Slice]:
    """Monthly amounts of one phase, an outflow positive. Income: the streams on `day` by
    category and name, then the sources of the run under `RUN`. Outflows: the expense streams
    by category and name, then the outflows of the run by group and item."""
    sign = 1 if income else -1
    extra = run or Budget()
    return [
        *(
            Slice(path, sign * v)
            for path, v in cashplan.by_stream(rows, day, phase, income=income).items()
        ),
        *(
            (Slice((RUN, name), v) for name, v in extra.sources.items())
            if income
            else (
                Slice((group, item), v)
                for group, items in extra.outflows.items()
                for item, v in items.items()
            )
        ),
    ]


def role(group: str) -> str:
    """The role of a group of the run: every group outside `GROUP_ROLES` spends."""
    return GROUP_ROLES.get(group, "spending")


def _colors(rows: list[cashplan.Row], *, income: bool) -> dict[tuple[str, ...], str]:
    """The colors of the blocks of the stream tables, then those of the roles of the run: the
    non-cash income among the income, the taxes, the loan principal and a salary conversion among
    the outflows. The other flows of the run take none: gray."""
    kind = cashplan.INCOME if income else cashplan.EXPENSE
    cats = [str(r.get("cat", "")) for r in rows if cashplan.role(r) == kind]
    colors: dict[tuple[str, ...], str] = {(c,): color for c, color in row_colors(cats).items()}
    return colors | {
        (group,): ROLES[kind] for group, kind in GROUP_ROLES.items() if (group == NONCASH) == income
    }


def noncash_of(run: Budget | None, taken: Collection[str]) -> list[Slice]:
    """The non-cash income in `run`, per month, a bar per item in the words of the session
    (`said`). An item named like a bar in `taken` gets ` (non-cash)`: bars of one name would share
    one place."""
    named = [(said(item), value) for item, value in (run.noncash if run else {}).items()]
    return [
        Slice((NONCASH, _("{item} (non-cash)").format(item=name) if name in taken else name), value)
        for name, value in named
    ]


def _in_words(slices: Iterable[Slice], factor: float = 1.0) -> list[Slice]:
    """`slices` times `factor`, each part of a path in the words of the session (`said`): a
    category, a name or a label as written."""
    return [Slice(tuple(map(said, s.path)), factor * s.value) for s in slices]


def _colors_in_words(colors: Mapping[tuple[str, ...], str]) -> dict[tuple[str, ...], str]:
    """`colors` by the paths of `_in_words`."""
    return {tuple(map(said, path)): color for path, color in colors.items()}


def income_chart(
    rows: list[cashplan.Row],
    day: date,
    phase: str,
    per: tuple[str, int],
    run: Budget | None,
    *,
    key: str,
    label: str,
) -> None:
    """The income streams of one phase as bars, the largest on top, and below them the non-cash
    income of the run, which stays out of the total. A bar of an asset that shrinks grows to the
    left. `label` names the phase, `per` the period in English (`ui.PER`) and its multiplier."""
    unit, factor = per
    cash = _in_words(flows_of(rows, day, phase, run, income=True), factor)
    noncash = [Slice(s.path, factor * s.value) for s in noncash_of(run, {s.path[-1] for s in cash})]
    if not any(s.value > 0 for s in cash + noncash):
        st.caption(_("No income in this phase."))
        return
    _headline(
        _("All income in `{phase}`: **{total}** {unit}").format(
            phase=label, total=format_eur(sum(s.value for s in cash)), unit=_(unit)
        ),
        sum(s.value for s in noncash),
        NONCASH_LINE,
    )
    chart(
        bars_figure(
            cash + noncash,
            _colors_in_words(_colors(rows, income=True)),
            signed=any(round(s.value) < 0 for s in noncash),
            below={NONCASH},
            compact=is_mobile(),
        ),
        key=key,
    )


def _headline(text: str, extra: float, line: str) -> None:
    """`text`, and below it the message `line` with `extra` in euros for `{amount}` unless that
    rounds to zero."""
    below = f"  \n{_(line).format(amount=format_eur(extra))}" if round(extra) else ""
    st.markdown(text + below)


def outflows_chart(
    rows: list[cashplan.Row],
    day: date,
    phase: str,
    per: tuple[str, int],
    run: Budget | None,
    *,
    key: str,
    label: str,
    detail: DeltaGenerator | None = None,
) -> None:
    """The outflows of one phase per category (`outflow_bars`): the streams of a category, the
    items of a group of the run. `label` names the phase."""
    unit, factor = per
    outflow_bars(
        [Slice(s.path, factor * s.value) for s in flows_of(rows, day, phase, run, income=False)],
        _colors(rows, income=False),
        key=f"{key}-{phase}",
        scope=_("in `{phase}`").format(phase=label),
        unit=unit,
        detail=detail,
    )


def outflow_bars(
    slices: Sequence[Slice],
    colors: dict[tuple[str, ...], str],
    *,
    key: str,
    scope: str,
    unit: str,
    detail: DeltaGenerator | None = None,
) -> None:
    """The outflows `scope` (in words, for example in `work`) per group, the first part of each
    path, the largest on top, and the items of one group, both in the words of the session
    (`said`). `unit` names the period in English (`ui.PER`). On a phone pills above the chart pick
    the group, its items show right below them whatever `detail` says, and the chart takes no
    tap, so a swipe over it scrolls. On a desktop a click on a bar picks it, and its items show in
    `detail`, by default above the chart. A new pick scrolls its items into view. The pick is the
    group as the ledger names it, whatever the words."""
    groups: dict[str, float] = {}
    for s in slices:
        groups[s.path[0]] = groups.get(s.path[0], 0.0) + s.value
    shown = sorted((g for g, v in groups.items() if v > 0), key=groups.__getitem__, reverse=True)
    if not shown:
        st.caption(_("No outflows {scope}.").format(scope=scope))
        return
    loans, converted = (groups.get(group, 0.0) for group in (LOAN_PRINCIPAL, CONVERSION))
    total = format_eur(sum(groups.values()))
    _headline(
        _("All outflows {scope}: **{total}** {unit}").format(
            scope=scope, total=total, unit=_(unit)
        ),
        loans + converted,
        KEPT.get((bool(round(loans)), bool(round(converted))), KEPT[True, True]),
    )
    words = _colors_in_words(colors)
    phone = is_mobile()
    bars = bars_figure(
        [Slice((said(group),), v) for group, v in groups.items()], words, compact=phone
    )
    inside = f"outflow-detail-{key}"  # `ui.PAGE_STYLE` keeps it clear of the header
    if phone:
        picked = st.pills(
            _("Show the streams of"),
            shown,
            format_func=said,
            key=f"{key}-pick",
            wrap=True,
            persist_state="page",
        )
        below = st.container(key=inside)
        chart(bars, key=key)
    else:
        below = st.container(key=inside) if detail is None else detail.container(key=inside)
        event = chart(bars, on_select="rerun", key=key)
        bar = {said(group): group for group in groups}  # a bar names its group in words
        picked = next((bar[p["y"]] for p in event.selection.points if p.get("y") in bar), None)
        if picked is None:
            below.caption(_("Click a bar of the outflows to show its streams."))
    if picked is not None:
        with below:
            st.markdown(
                _("**{group}** {scope}: **{total}** {unit}").format(
                    group=said(picked), scope=scope, total=format_eur(groups[picked]), unit=_(unit)
                )
            )
            chart(
                bars_figure(
                    _in_words(s for s in slices if s.path[0] == picked), words, compact=phone
                ),
                key=f"{key}-{picked}",
            )
            if picked != st.session_state.get(f"{inside}-shown"):
                st.html(
                    _SCROLL.substitute(
                        picked=json.dumps(picked).replace("<", r"\u003c"),
                        detail=key_class(inside),
                    ),
                    unsafe_allow_javascript=True,
                )
    st.session_state[f"{inside}-shown"] = picked


def reached(plan: Plan) -> dict[str, str]:
    """The phases that the scenario of `plan` switches to, each with its label, in the order of
    `assumptions.yaml`: a phase that it never reaches has no column, as on the Flows page. The
    streams keep a factor per phase: `cashflows.yaml` serves every scenario."""
    held = {c.phase for c in plan.scenario.phases}
    return {p: label for p, label in plan.assumptions.phase_labels.items() if p in held}


def phase_control(key: str, plan: Plan, day: date) -> str:
    """The phases that the scenario of `plan` reaches, at first its phase on `day`. The key holds
    the names, so a removed phase leaves no value behind."""
    labels = reached(plan)
    return str(
        st.segmented_control(
            _("Phase"),
            list(labels),
            format_func=labels.__getitem__,
            default=plan.scenario.phase_of(day),
            required=True,
            key=f"{key}-{'-'.join(labels)}",
            wrap=True,
        )
    )
