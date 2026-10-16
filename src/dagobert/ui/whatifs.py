"""The what-ifs (owner 2026-10-16, issue #14): a dialog per step of `dagobert.whatifs`, each a few
fields with defaults and their misfits below them, what it writes through the save guard and its
one revision (`fileactions.confirm`), then the Overview, whose block `What-ifs` compares it; and
the steps as a menu `Check a what-if` (the Scenarios page, the Overview) or as buttons (the
invitation of the Overview)."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from datetime import date
from functools import partial
from itertools import chain, count
from typing import TYPE_CHECKING, Any

import streamlit as st

from dagobert import datadir, goalseek, i18n, references, whatifs
from dagobert.i18n import N_, _, pgettext
from dagobert.model.base import Unit
from dagobert.model.months import months_of_age
from dagobert.model.taxes import Land
from dagobert.money import format_eur, format_percent
from dagobert.scenariofiles import scenario_file
from dagobert.store import streams_file
from dagobert.ui import at_age, fields, guard, is_mobile, keyboard, language, literal, slug
from dagobert.ui.fileactions import LISTED, NAME_HELP, Lines, Plan, confirm, shut
from dagobert.ui.gridcolumns import in_order
from dagobert.ui.widgets import SHAPE

if TYPE_CHECKING:
    from pathlib import Path

    from streamlit.delta_generator import DeltaGenerator

KEY = "whatif-"
MENU = f"{KEY}menu"  # the popover of the steps per page, closed by a tap on one
CHECK = N_("Check a what-if")
MONTH = fields.Field(("month",), fields.Kind.DATE, Unit.MONTH)
AGE = fields.Field(("age",), fields.Kind.INTEGER, low=0, high=goalseek.WORK_AGE)
MONTHS = fields.Field(("months",), fields.Kind.INTEGER, Unit.MONTHS, low=1, high=60)
EUROS = fields.Field(("euros",), fields.Kind.NUMBER, Unit.EUR, low=0)
PRICE = fields.Field(("price",), fields.Kind.NUMBER, Unit.EUR, low=0, open_low=True)
COURSE_MONTHS = 6  # the default length of a course: six months in a row extend a short claim
EARLIER = 5  # the default of `Stop earlier`: so many years before the plan stops now
# what a course follows, by its id: its words
AFTER = {"loss": N_("a job loss"), "break": N_("a career break")}
MISSING = N_("Fill in the fields above first.")
MISFIT = N_("Change the fields marked above.")
DONE = N_("Added {name}: the Overview compares it with your plan.")


@dataclass
class _Form:
    """The fields of a dialog: what each read (None: empty or not read), whether all read, and
    a slot below each for why it does not fit the plan (`whatifs.Step.misfits`)."""

    values: dict[str, Any] = field(default_factory=dict)
    slots: dict[str, DeltaGenerator] = field(default_factory=dict)
    read: bool = True

    def typed(
        self,
        key: str,
        label: str,
        typed: fields.Field,
        *,
        value: Any = None,  # noqa: ANN401 a value of the file
        placeholder: str | None = None,
        help: str | None = None,
    ) -> Any:  # noqa: ANN401 a value of the file
        """A text field read by `fields.parse` (`decimal-`: the keypad of a phone), its default
        `value` as the field shows it, why it does not read below it, then its slot."""
        text = st.text_input(
            label,
            fields.shown(typed, value),
            key=f"decimal-{KEY}{key}",
            placeholder=placeholder,
            help=help,
        )
        try:
            self.values[key] = fields.parse(typed, text)
        except ValueError as err:
            st.error(literal(str(err)), icon=":material/error:")
            self.values[key], self.read = None, False
        self.slots[key] = st.empty()
        return self.values[key]

    def slot(self, key: str) -> None:
        self.slots[key] = st.empty()

    def mark(self, misfits: dict[str, str]) -> None:
        for key, why in misfits.items():
            self.slots[key].error(literal(why), icon=":material/error:")


def _free(first: str, taken: Collection[str], numbered: Callable[[int], str]) -> str:
    """`first`, else the first of its `numbered` forms from 2 that is not `taken`."""
    return next(n for n in chain([first], map(numbered, count(2))) if n not in taken)


def _age(data_dir: Path, month: date | None) -> int | None:
    """The age in whole years in `month`."""
    born = references.born(data_dir)
    return months_of_age(born, month) // 12 if born and month else None


def _named(data_dir: Path, plan: Plan, named: str) -> tuple[str, str]:
    """The name of the scenario, by default `named`, numbered `(2)` where another has it, and its
    file name, its slug, numbered `-2` where taken."""
    taken = {str(doc.get("name")) for doc in plan.docs.values()}
    default = _free(named, taken, lambda k: f"{named} ({k})")
    name = (
        st.text_input(_("Name"), key=f"{KEY}name", placeholder=default, help=_(NAME_HELP)).strip()
        or default
    )
    base = slug(name)
    stems = {s.casefold() for s in plan.docs}
    return name, _free(base, stems, lambda k: f"{base}-{k}")


def _next_year() -> date:
    """The default month of a start: the next January."""
    return date(date.today().year + 1, 1, 1)


def _finish(
    data_dir: Path,
    key: str,
    step: whatifs.Step | None,
    form: _Form,
    lines: Callable[[], Lines] | None = None,
) -> None:
    """The misfits of `step` below their fields, what it writes (the `lines` that it words
    itself) and its button (`confirm`): one revision `<page>: what-if <stem>`, then the
    Overview."""
    misfits = step.misfits(data_dir) if step is not None else {}
    form.mark(misfits)
    keyboard()
    confirm(
        data_dir,
        (key, step),
        lambda d: [] if step is None else step.edits(d),
        button=_("Add and compare"),
        what=f"what-if {step.stem if step else ''}",
        done=_(DONE).format(name=step.name if step else ""),
        then=step.stem if step else None,
        ready=step is not None and not misfits,
        why=_(MISFIT) if misfits else _(MISSING),
        page="Overview",
        lines=lines,
    )


# A dialog reruns alone, without `main.py`, in a thread of its own: it takes the language of the
# session first. Its title comes per call, in the language of the session (`menu`).


def _stop(data_dir: Path, plan: Plan) -> None:
    """The age to stop working, earlier than the main scenario (`whatifs.Earlier`)."""
    i18n.activate(language())
    main = str(plan.main)
    st.caption(
        _(
            "A new scenario that extends {scenario} and stops working at the age that you type: "
            "the salary and the savings plan end, the pension starts as before. It moves the "
            "change out of work as the slider of the Explorer does."
        ).format(scenario=plan.said(main))
    )
    form = _Form()
    held = whatifs.ages(data_dir, main)
    age = form.typed(
        "age",
        _("Stop working at age"),
        AGE,
        value=None if held is None else max(held[0], held[1] - EARLIER),
        help=None
        if held is None
        else _("Your plan stops working at {age} now.").format(age=held[1]),
    )
    named = _("Stop at {age}").format(age=age) if age is not None else _("Stop earlier")
    name, stem = _named(data_dir, plan, named)
    step = None if age is None else whatifs.Earlier(main, age, name, stem)
    _finish(data_dir, "stop", step, form, None if step is None else partial(_moved, data_dir, step))


def _moved(data_dir: Path, step: whatifs.Earlier) -> Lines:
    """The line of the save guard of the `shift` of `Stop earlier`: the month of the stop before
    and after it, with the age then, as the work slider of the Explorer says them."""
    born, (before, after) = references.born(data_dir), step.months(data_dir)
    file = scenario_file(step.stem)
    return {
        (file, ("overrides",)): guard.Change(
            f"{file} {_(goalseek.STOP)}", at_age(before, born), at_age(after, born), unit=None
        )
    }


def _job_loss(data_dir: Path, plan: Plan) -> None:
    """The months of a job loss and of a new job (`whatifs.Loss`)."""
    i18n.activate(language())
    main = str(plan.main)
    st.caption(
        _(
            "A new scenario that extends {scenario}. From the month of the job loss the salary "
            "stops and ALG1 pays, until the month of a new job, if you type one. Where the plan "
            "lacks them, the app adds the payment ALG1, a phase without a job and the feature "
            "Job loss."
        ).format(scenario=plan.said(main))
    )
    form = _Form()
    shape = _(SHAPE[Unit.MONTH])
    lost = form.typed("lost", _("Month of the job loss"), MONTH, placeholder=shape)
    back = form.typed("back", _("Month of a new job (optional)"), MONTH, placeholder=shape)
    age = _age(data_dir, lost)
    named = _("Job loss at {age}").format(age=age) if age is not None else _("Job loss")
    name, stem = _named(data_dir, plan, named)
    unemployed = pgettext("phase", "Unemployed")
    step = (
        whatifs.Loss(main, lost, back, name, stem, unemployed)
        if lost is not None and form.read
        else None
    )
    _finish(data_dir, "job-loss", step, form)


def _course(data_dir: Path, plan: Plan) -> None:
    """A course after a job loss or in a career break, its months and costs (`whatifs.Course`)."""
    i18n.activate(language())
    main = str(plan.main)
    st.caption(
        _(
            "A new scenario that extends {scenario}: a course of some months, then back to work. "
            "After a job loss ALG1 pays during the course and uses half of the days of the "
            "claim (Arbeitslosengeld bei Weiterbildung); in a career break nothing pays. The "
            "costs count as work expenses for the income tax."
        ).format(scenario=plan.said(main))
    )
    form = _Form()
    after = st.segmented_control(
        _("The course follows"),
        list(AFTER),
        format_func=lambda option: _(AFTER[option]),
        default="loss",
        required=True,
        key=f"{KEY}course-after",
    )
    form.slot("loss")
    start = form.typed("start", _("Course starts in (month)"), MONTH, value=_next_year())
    months = form.typed("months", _("Months of the course"), MONTHS, value=COURSE_MONTHS)
    cost = form.typed(
        "cost",
        _("Costs of the course €"),
        EUROS,
        placeholder="0",
        help=_(
            "All that the course costs you, spread over its months. With a Bildungsgutschein "
            "after a job loss the Agentur für Arbeit pays them: type 0."
        ),
    )
    age = _age(data_dir, start)
    named = _("Course at {age}").format(age=age) if age is not None else _("Course")
    name, stem = _named(data_dir, plan, named)
    step = (
        whatifs.Course(main, start, months, cost or 0, after == "loss", name, stem)
        if start is not None and months is not None and form.read
        else None
    )
    _finish(data_dir, "course", step, form)


def _salary(data_dir: Path) -> float | None:
    """The gross of the first salary of `cashflows.yaml`: the default profit of a business."""
    gross = next(
        (r.get("gross") for r in streams_file(data_dir).rows() if r.get("kind") == "salary"),
        None,
    )
    return gross if isinstance(gross, int | float) else None


def _business(data_dir: Path, plan: Plan) -> None:
    """The month and the monthly profit of a business (`whatifs.Business`)."""
    i18n.activate(language())
    main = str(plan.main)
    st.caption(
        _(
            "A new scenario that extends {scenario}: from the month that you type you run a "
            "business instead of your job, until the plan stops working. In this phase the "
            "salary and the savings plan stop and the profit pays. You pay its income tax and "
            "your health insurance yourself, and no statutory pension insurance: the Assumptions "
            "page changes that."
        ).format(scenario=plan.said(main))
    )
    form = _Form()
    start = form.typed("start", _("Start the business in (month)"), MONTH, value=_next_year())
    profit = form.typed(
        "profit",
        _("Profit per month €"),
        EUROS,
        value=_salary(data_dir),
        help=_(
            "What the business earns in a month after its costs, before income tax and social "
            "insurance. Your gross salary at first."
        ),
    )
    age = _age(data_dir, start)
    named = _("Business at {age}").format(age=age) if age is not None else _("Business")
    name, stem = _named(data_dir, plan, named)
    step = (
        whatifs.Business(main, start, profit, name, stem)
        if start is not None and profit is not None and form.read
        else None
    )
    _finish(data_dir, "business", step, form)


def _land(data_dir: Path) -> Land | None:
    """The Land of the tax options, the default of a purchase."""
    tax = references.read(data_dir, "assumptions.yaml").get("tax")
    held = tax.get("land") if isinstance(tax, dict) else None
    return Land(held) if held in set(Land) else None


def _property(data_dir: Path, plan: Plan) -> None:
    """The month, the price, the own funds, the Land and the rent that ends of a purchase
    (`whatifs.Purchase`); the spending that the rent comes off where the plan has several."""
    i18n.activate(language())
    main = str(plan.main)
    st.caption(
        _(
            "A new scenario that extends {scenario}: you buy a property, pay the "
            "Grunderwerbsteuer and {costs} of the price for the notary and a broker from your own "
            "funds and borrow the rest. The rent that you type ends with the purchase."
        ).format(scenario=plan.said(main), costs=format_percent(whatifs.COSTS, None))
    )
    form = _Form()
    at = form.typed("at", _("Buy in (month)"), MONTH, value=_next_year())
    price = form.typed("price", _("Price €"), PRICE)
    own = form.typed(
        "own",
        _("Own funds €"),
        EUROS,
        placeholder="0",
        help=_("What you pay from your cash and savings. A loan pays the rest."),
    )
    lands = in_order(list(Land), Land.titles().items())
    held = _land(data_dir)
    land = st.selectbox(
        _("Land"),
        lands,
        index=lands.index(held) if held is not None else None,
        format_func=lambda option: _(Land.titles()[option]),
        placeholder=_("Choose the Land"),
        key=f"{KEY}property-land",
        filter_mode=None if is_mobile() else "fuzzy",  # no keyboard on a phone
        help=_("Where the property lies: the Land sets the Grunderwerbsteuer."),
    )
    form.slot("land")
    rent = form.typed(
        "rent",
        _("Rent that ends (€ a month)"),
        EUROS,
        placeholder="0",
        help=_(
            "The rent and the costs of your current home that the purchase ends: from its month "
            "they come off your spending."
        ),
    )
    stream = _spending(whatifs.spending(data_dir, main, at) if at is not None else {})
    age = _age(data_dir, at)
    named = _("Property at {age}").format(age=age) if age is not None else _("Property")
    name, stem = _named(data_dir, plan, named)
    step = (
        whatifs.Purchase(main, at, price, own or 0, land, name, stem, rent or 0, stream)
        if at is not None and price is not None and form.read
        else None
    )
    if step is not None and step.land is not None and (owed := step.cost - step.own) > 0:
        st.caption(
            _(
                "It costs {cost} with tax and costs. The loan of {loan} at {rate} with {repayment} "
                "repayment a year pays {payment} a month."
            ).format(
                cost=format_eur(step.cost),
                loan=format_eur(owed),
                rate=format_percent(datadir.LOAN_RATE, None),
                repayment=format_percent(datadir.REPAYMENT, None),
                payment=format_eur(datadir.payment(owed)),
            )
        )
    _finish(data_dir, "property", step, form)


def _spending(held: dict[str, float]) -> str:
    """The spending that the rent comes off: with several a select, by default
    `whatifs.living`."""
    default = whatifs.living(held)
    if len(held) < 2:
        return default
    names = list(held)
    return st.selectbox(
        _("Spending that holds the rent"),
        names,
        index=names.index(default),
        key=f"{KEY}property-stream",
        filter_mode=None if is_mobile() else "fuzzy",
        help=_("The rent ends in this spending, a row of the Cashflows page."),
    )


# by key: the label of the button, also the title of its dialog, and the dialog
STEPS: dict[str, tuple[str, Callable[[Path, Plan], None]]] = {
    "stop": (N_("Stop earlier"), _stop),
    "job-loss": (N_("Lose the job"), _job_loss),
    "course": (N_("Take a course"), _course),
    "business": (N_("Start a business"), _business),
    "property": (N_("Buy a property"), _property),
}


def menu(
    data_dir: Path, plan: Plan, holder: DeltaGenerator, where: str, *, inline: bool = False
) -> None:
    """The steps: a button each in `holder` (`inline`: the invitation of the Overview), else in the
    popover `Check a what-if`, which a tap on one closes: it would cover the dialog. Each opens
    its dialog with a fresh list, its title in the language of the session. A step extends the
    main scenario: none without one. The keys name the page, `where`; the popover's also the
    count of the scenarios: after a step it is a new one, closed (Streamlit 1.65 opened the old
    one again after the page switch of a step)."""
    if plan.main is None:
        return
    phone, popover = is_mobile(), f"{MENU}-{where}-{len(plan.docs)}"
    box = (
        holder
        if inline
        else holder.popover(
            _(CHECK), icon=":material/alt_route:", key=popover, on_change="rerun"
        ).container(horizontal=phone, wrap=True)
    )
    for key, (label, dialog) in STEPS.items():
        if box.button(
            _(label),
            key=f"{KEY}{where}-{key}",
            on_click=None if inline else shut,
            args=(popover,),
        ):
            st.session_state.pop(LISTED, None)
            st.dialog(_(label))(dialog)(data_dir, plan)
