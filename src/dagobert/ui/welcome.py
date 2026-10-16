"""The first-run page: `main.py` shows it instead of the pages while the data directory is empty
or missing (`datadir.empty`). It starts a plan from an example (then the Overview, which seeks
when to stop working once), a quick start with its goals (the same, without a salary or at 67 the
Assumptions page) or an export zip (the import of the `Export and import` page, then the
Overview)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

import streamlit as st
from babel.dates import format_date
from babel.lists import format_list

from dagobert import datadir, goalseek, i18n, scenariofiles
from dagobert.i18n import N_, _, ngettext
from dagobert.loader import load_assumptions, load_scenario
from dagobert.model.assumptions import REGELALTERSGRENZE, Person
from dagobert.model.base import Unit, description
from dagobert.model.plan import Feature
from dagobert.money import format_eur, format_number
from dagobert.ui import PAGES, fields, is_mobile, keyboard, literal, mode, outlook
from dagobert.ui.gridcolumns import also
from dagobert.ui.overview import explore
from dagobert.ui.transfer import import_zip
from dagobert.ui.widgets import SHAPE

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from streamlit.delta_generator import DeltaGenerator

    from dagobert import revisions


@dataclass(frozen=True)
class Example:
    """An example of the package with its line on the page, in English (`_()` where it shows)."""

    name: datadir.ExampleName
    title: str
    text: str
    button: str

    @property
    def path(self) -> Path:
        return datadir.EXAMPLES / self.name


EXAMPLES = (
    Example(
        "starter",
        N_("Start simple"),
        N_(
            "a made-up employee of 31 who wants to stop working early, with a salary and a "
            "company pension, an ETF savings plan, the statutory health insurance and a rented "
            "flat. The names and notes of this example are in German."
        ),
        N_("Start from the simple example"),
    ),
    Example(
        "engineer",
        N_("Full example"),
        N_(
            "a made-up engineer of 40 with one child, private health insurance (PKV), a rented "
            "home and a rented-out flat with a loan. It uses every feature of Dagobert. The names "
            "and notes of this example are in English."
        ),
        N_("Start from the full example"),
    ),
)
DATES = N_(
    "Their plans start in {start}, and their values date from then. From a later month on, the "
    "Overview offers to roll the start forward and marks the values as old."
)
QUICK = N_(
    "Your plan from a few numbers. Only the date of birth is needed: an empty field adds nothing, "
    "and you can add it later on the pages Assets, Cashflows and Scenarios. With a salary and "
    "under 67 the Overview opens next and finds by when you could stop working. Otherwise the "
    "Assumptions page opens: check the person and the markets."
)
# the warning above `Start my plan` while the rough net salary misses what goes out (`budget`)
BUDGET = N_(
    "After tax and social insurance your salary leaves about {net} a month, {short} less than "
    "what goes out: {out} for spending, savings plan and loan. The plan takes the gap from your "
    "cash and your depot, and the savings plan pauses whenever the cash runs short."
)
UNPAID = N_(
    "Without a salary the savings plan of {plan} a month comes from your cash, and it pauses "
    "whenever the cash runs short."
)
PREMIUM = N_("Your PKV premium comes on top.")
# the line below the loan of an own property
PAYMENT = N_(
    "The plan pays {payment} a month for the loan: {rate} interest and {repayment} repayment a "
    "year. Leave it out of your spending. The Assets page takes your own rate and payment."
)
OWNER_HELP = N_(
    "Your home or a flat that you own: its value counts in your net worth, and the part of the "
    "app for property turns on."
)
EXPORT = N_(
    "Your plan from another Dagobert or from a backup: upload the zip file that the page Export "
    "and import made there. Every file of it is new here, and an export with its change history "
    "brings that along. Then the Overview opens."
)
BORN = N_("Date of birth")
NEEDS_BORN = N_("Type your date of birth first: every age in the plan counts from it.")
SEXES: dict[Literal["f", "m"], str] = {"f": N_("Female"), "m": N_("Male")}
# the lines below the empty pension points (`pension_note`) and below the savings plan
ESTIMATED = N_(
    "Estimated: {points} points, {years} years at your salary of today. Your Renteninformation "
    "has the exact number."
)
NO_POINTS = N_(
    "Without the points or the year, the pension counts only the points that the salary earns in "
    "the plan. Your Renteninformation has the points so far."
)
RETIRED = N_(
    "At 67 or older the plan starts retired: the salary and the savings plan do not pay, and the "
    "Assumptions page opens next. The Scenarios page adds a phase of work."
)


@dataclass(frozen=True)
class Answer:
    """A field of the quick start: the field of `datadir.Quick` that it answers and its words, in
    English (`_()` where it shows). Euros and points read at least 0, the year (`unit` None) from
    the birth to this year, an age (`Unit.YEARS`) up to the latest that the work seek tries, a
    month (`field`)."""

    key: str
    label: str
    help: str
    unit: Unit | None = Unit.EUR


ANSWERS = {
    a.key: a
    for a in (
        Answer(
            "gross",
            N_("Gross salary per month €"),
            N_(
                "Before tax and social insurance, without a bonus. The plan pays it until you "
                "stop working, at the age of your goal below, else at 67."
            ),
        ),
        Answer(
            "spending",
            N_("Spending per month €"),
            N_(
                "All that you spend in a month, with the rent, as one expense, without the payment "
                "of a loan: the plan pays the loan of a property below. The Cashflows page splits "
                "it into categories."
            ),
        ),
        Answer(
            "savings",
            N_("Savings today €"),
            N_(
                "The value of your funds and shares today, as one depot of equity. The tax counts "
                "no gain in it yet."
            ),
        ),
        Answer("cash", N_("Cash today €"), N_("What your current account holds today.")),
        Answer(
            "points",
            N_("Pension points so far"),
            N_(
                "The Rentenpunkte of your Renteninformation, the yearly letter of the Deutsche "
                "Rentenversicherung. Empty: an estimate from your salary and the year since which "
                "you are insured."
            ),
            Unit.NUMBER,
        ),
        Answer(
            "since",
            N_("Pension insurance since (year)"),
            N_("The year of your first contribution to the statutory pension insurance."),
            None,
        ),
        Answer(
            "plan",
            N_("Savings plan per month €"),
            N_("Goes into the depot each month until you stop working."),
        ),
        Answer(
            "stop",
            N_("Stop working at age"),
            N_(
                "The age at which the salary and the savings plan stop. Empty: 67. The statutory "
                "pension starts at 67, from 63 after 35 years of insurance, with a deduction. The "
                "Overview then finds the earliest age that your money allows."
            ),
            Unit.YEARS,
        ),
        Answer(
            "lost",
            N_("Check a job loss in (month)"),
            N_(
                "A month in which you might lose your job. The plan gets a second scenario of "
                "it: ALG1 for a year or more, then no salary until you stop working. The Explorer "
                "compares it with your plan, and the Scenarios page adds a new job."
            ),
            Unit.MONTH,
        ),
        Answer(
            "home",
            N_("Value of the property €"),
            N_(
                "What it would sell for today. The plan writes it as 1 m² at this price: the "
                "Assets page takes the living space and the price per m²."
            ),
        ),
        Answer(
            "owed",
            N_("Loan still owed €"),
            N_("The balance of its loan today, if any."),
        ),
    )
}
ROWS = (("gross", "spending"), ("savings", "cash"), ("points", "since"), ("plan",))
GOALS, HOME = ("stop", "lost"), ("home", "owed")
# the placeholder of a field by its unit: the shape of a month, the age at which the plan stops
PLACEHOLDERS: dict[Unit | None, str] = {
    Unit.MONTH: SHAPE[Unit.MONTH],
    Unit.YEARS: str(REGELALTERSGRENZE),
}


def field(answer: Answer, born: date | None) -> fields.Field:
    """The field that reads `answer` (`fields.parse`, which says what to type): euros or points at
    least 0, a whole year from the birth to this year, an age up to the latest month that the
    work seek tries (`goalseek.WORK_AGE`), a month."""
    key = (answer.key,)
    match answer.unit:
        case None:
            low = (born or datadir.OLDEST).year
            return fields.Field(key, fields.Kind.INTEGER, low=low, high=date.today().year)
        case Unit.YEARS:
            return fields.Field(key, fields.Kind.INTEGER, low=0, high=goalseek.WORK_AGE)
        case Unit.MONTH:
            return fields.Field(key, fields.Kind.DATE, Unit.MONTH)
        case _:
            return fields.Field(key, fields.Kind.NUMBER, answer.unit, low=0)


def scenarios(example: Path) -> list[tuple[str, str]]:
    """The name and the note of each scenario of an example, those that the app opens with
    first. Read from the package, never opened: an open would write into it."""
    paths = scenariofiles.concrete_scenarios(example)
    first = scenariofiles.default_scenarios(example)
    ordered = [*first, *(stem for stem in paths if stem not in first)]
    return [(s.name, s.note) for s in map(load_scenario, (paths[stem] for stem in ordered))]


def _scenarios(example: Example) -> str:
    """The scenarios of an example as a Markdown list below its title. Names and notes are data,
    in the language of the example."""
    rows = (f"- **{literal(n)}**: {literal(t)}" for n, t in scenarios(example.path))
    return "\n".join([f"**{_(example.title)}**", "", *rows])


def birth(text: str) -> date:
    """The date of birth typed day first with dots or in ISO order. Raises ValueError with what to
    type, also for a date after today or before 1900 (`datadir.check_born`)."""
    if (day := fields.day(text)) is None:
        msg = _("type it as 20.05.1986 or 1986-05-20")
        raise ValueError(msg)
    datadir.check_born(day)
    return day


def said(born: date, today: date) -> str:
    """A date of birth in words with the age today, so a slip of the order shows: `Born 20 May
    1986, age 40.`"""
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    day = format_date(born, _("d MMMM y"), locale=i18n.language())
    return _("Born {day}, age {age}.").format(day=day, age=age)


def _start(data_dir: Path, begin: Callable[[], revisions.Entry | None], then: str) -> None:
    """Start the plan and go to the page `then` of the navigation (a page drawn alone, as in a
    test, has none), or show why it did not start: a directory that holds a plan by now, one that
    is read-only or locked, a date of birth out of range (`birth` checks it already). The
    Overview of a new plan seeks when to stop working once (`outlook.SEEK_FIRST`). The mode stays
    that of the browser (`mode.advanced`): a new one starts simple."""
    try:
        begin()
    except (ValueError, OSError) as err:  # `InputError` is a ValueError
        st.error(
            _("Not started: {directory}: {reason}").format(
                directory=literal(str(data_dir)), reason=literal(str(err))
            )
        )
        return
    st.session_state[outlook.SEEK_FIRST] = then == "Overview"
    if (page := st.session_state.get(PAGES, {}).get(then)) is not None:
        st.switch_page(page)


def _born(width: Literal["stretch"] | int) -> date | None:
    """The date of birth as typed (the decimal keypad of a phone has the dot), and below it the
    date in words or why it does not read."""
    text = st.text_input(
        _(BORN),
        placeholder=_("DD.MM.YYYY"),
        help=also(
            _(description(Person, ("born",))), _("Type it as 20.05.1986 or 1986-05-20.")
        ),  # the help of the date of birth on the Assumptions page, how to type it
        key="decimal-welcome-born",
        width=width,
    )
    keyboard()
    if not text.strip():
        st.caption(_(NEEDS_BORN))
        return None
    try:
        born = birth(text)
    except ValueError as err:
        st.error(
            _("Not a date of birth: {reason}.").format(reason=literal(str(err))),
            icon=":material/error:",
        )
        return None
    st.caption(said(born, date.today()))
    return born


def pension_note(values: Mapping[str, Any], start: date) -> str | None:
    """The line below empty pension points: their estimate (`datadir.estimate`), or with a salary
    but no year that the pension counts only the points of the run; None with points."""
    if values.get("points") is not None:
        return None
    if points := datadir.estimate(values.get("gross"), values.get("since"), start):
        return _(ESTIMATED).format(
            points=format_number(points),
            years=start.year - values["since"],
        )
    return _(NO_POINTS) if values.get("gross") and values.get("since") is None else None


def _row(
    row: tuple[str, ...],
    born: date | None,
    values: dict[str, Any],
    slots: dict[str, DeltaGenerator],
    *,
    off: bool = False,
) -> bool:
    """The fields of `row` two to a row (stacked on a phone), each read into `values` with why it
    does not read below it, then a slot for why it does not fit (`datadir.misfits`); whether all
    read. A field that is `off` reads as empty."""
    read = True
    for column, key in zip(st.columns(2), row, strict=False):
        answer = ANSWERS[key]
        with column:
            text = st.text_input(
                _(answer.label),
                key=f"decimal-welcome-{key}",
                help=_(answer.help),
                placeholder=_(PLACEHOLDERS[answer.unit]) if answer.unit in PLACEHOLDERS else None,
                disabled=off,
            )
            try:
                values[key] = None if off else fields.parse(field(answer, born), text)
            except ValueError as err:
                st.error(literal(str(err)), icon=":material/error:")
                read = False
            slots[key] = st.empty()
    return read


def _answers(born: date | None, values: dict[str, Any], slots: dict[str, DeltaGenerator]) -> bool:
    """The numbers of the quick start by their keys of `datadir.Quick`, below the points
    `pension_note`, at the end for a person past the Regelaltersgrenze with a salary or a savings
    plan that neither pays (`RETIRED`); whether all read."""
    read = True
    for row in ROWS:
        read &= _row(row, born, values, slots)
        if "points" in row and (note := pension_note(values, datadir.first_month())):
            st.caption(note)
    if (
        born is not None
        and datadir.starts_retired(born)
        and (values.get("gross") or values.get("plan"))
    ):
        st.caption(_(RETIRED))
    return read


def _goals(born: date | None, values: dict[str, Any], slots: dict[str, DeltaGenerator]) -> bool:
    """The goals: the age to stop working and a job loss (off for a plan that starts retired),
    and an own property with its loan and the payment that the plan takes; whether all read."""
    st.markdown(f"**{_('Your goals')}**")
    retired = born is not None and datadir.starts_retired(born)
    read = _row(GOALS, born, values, slots, off=retired)
    if st.toggle(_("I own a property"), key="welcome-owner", help=_(OWNER_HELP)):
        read &= _row(HOME, born, values, slots)
        if values.get("home") and (owed := values.get("owed")):
            st.caption(
                _(PAYMENT).format(
                    payment=format_eur(datadir.payment(owed)),
                    rate=f"{datadir.LOAN_RATE:.0%}",
                    repayment=f"{datadir.REPAYMENT:.0%}",
                )
            )
    return read


def budget(quick: datadir.Quick) -> str:
    """The warning of a plan whose rough net salary misses what goes out while it works
    (`datadir.Quick.short`); with a PKV its premium comes on top."""
    said = (
        _(BUDGET).format(
            net=format_eur(quick.net), short=format_eur(quick.short), out=format_eur(quick.out)
        )
        if quick.gross
        else _(UNPAID).format(plan=format_eur(quick.plan or 0.0))
    )
    return f"{said} {_(PREMIUM)}" if quick.pkv else said


def _quick(data_dir: Path, button: Literal["stretch", "content"]) -> None:
    """The quick start: the date of birth, a few numbers, the goals, a warning while the salary
    does not pay what goes out, and `Start my plan`, which switches off every feature that the
    plan does not use (`datadir.unused`, a count below it), then goes to the Overview with a
    salary that pays, else to the Assumptions page."""
    st.subheader(_("Quick start"))
    view = mode.View(mode.Uses(), frozenset(Feature), advanced=True)
    st.markdown(f"{_(QUICK)} {explore(view)}")
    left, right = st.columns(2)
    with left:
        born = _born("stretch")
    with right:
        sex = st.segmented_control(
            _("Sex"),
            list(SEXES),
            format_func=lambda s: _(SEXES[s]),
            key="welcome-sex",
            help=also(_(description(Person, ("sex",))), _("Without a choice: male.")),
        )
    values: dict[str, Any] = {}
    slots: dict[str, DeltaGenerator] = {}
    read = _answers(born, values, slots)
    read &= _goals(born, values, slots)
    keyboard()
    pkv = st.toggle(
        _("Private health insurance (PKV)"),
        key="welcome-pkv",
        help=_(
            "Off: the statutory health insurance (GKV). On: add your premium on the Cashflows "
            "page, so that the subsidy of your employer and the tax count it."
        ),
    )
    quick = (
        datadir.Quick(born, sex, pkv=pkv, lang=i18n.language(), **values)
        if born is not None and read
        else None
    )
    misfits = datadir.misfits(quick) if quick else {}
    for key, why in misfits.items():
        slots[key].error(literal(why), icon=":material/error:")
    if quick is not None and quick.short:
        st.warning(budget(quick), icon=":material/warning:")
    clicked = st.button(
        _("Start my plan"),
        type="primary",
        disabled=quick is None or bool(misfits),
        width=button,
        key="welcome-quick",
    )
    off = len(datadir.unused(quick)) if quick else len(Feature)
    st.caption(
        ngettext(
            "The quick start switches off {n} part of the app that your plan does not use: the "
            "Features page turns it on.",
            "The quick start switches off {n} parts of the app that your plan does not use: the "
            "Features page turns them on.",
            off,
        ).format(n=off)
    )
    if clicked and quick is not None and not misfits:
        then = (
            "Overview" if quick.gross and not datadir.starts_retired(quick.born) else "Assumptions"
        )
        _start(data_dir, partial(datadir.start_quick, data_dir, quick), then)


def page(data_dir: Path) -> None:
    st.title(_("Start a plan"))
    st.caption(
        _(
            "Your data directory holds no plan yet. Start from an example, with a quick start or "
            "from an export of your plan."
        )
    )
    button: Literal["stretch", "content"] = "stretch" if is_mobile() else "content"
    example, quick = st.columns(2, gap="large")
    with example:
        st.subheader(_("An example"))
        for ex in EXAMPLES:
            st.markdown(f"**{_(ex.title)}:** {_(ex.text)}")
            if st.button(_(ex.button), width=button, key=f"welcome-{ex.name}"):
                _start(data_dir, partial(datadir.start_example, data_dir, ex.path), "Overview")
        with st.expander(_("Their scenarios"), icon=":material/list:", key="welcome-scenarios"):
            st.markdown("\n\n".join(map(_scenarios, EXAMPLES)))
        with st.expander(_("Their dates"), icon=":material/info:", key="welcome-dates"):
            starts = sorted({load_assumptions(ex.path).start for ex in EXAMPLES})
            months = format_list([f"{s:%Y-%m}" for s in starts], locale=i18n.language())
            st.markdown(_(DATES).format(start=months))
    with quick:
        _quick(data_dir, button)
    st.subheader(_("An export"))
    st.markdown(_(EXPORT))
    import_zip(data_dir, then="Overview")
    st.caption(_("Data directory: {path}").format(path=literal(str(data_dir))))
