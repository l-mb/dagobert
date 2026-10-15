"""The first-run page: `main.py` shows it instead of the pages while the data directory is empty
or missing (`datadir.empty`). It starts a plan from an example (then the Overview), a quick start
(then the Overview, without a salary or at 67 the Assumptions page) or an export zip (the import
of the `Export and import` page, then the Overview)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

import streamlit as st
from babel.dates import format_date
from babel.lists import format_list

from dagobert import datadir, i18n, scenariofiles
from dagobert.i18n import N_, _
from dagobert.loader import load_assumptions, load_scenario
from dagobert.model.assumptions import Person
from dagobert.model.base import Unit, description
from dagobert.model.plan import Feature
from dagobert.money import format_number
from dagobert.ui import PAGES, fields, is_mobile, keyboard, literal, mode
from dagobert.ui.gridcolumns import also
from dagobert.ui.overview import explore
from dagobert.ui.transfer import import_zip

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

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
    "under 67 the Overview opens next, where `Find when to stop working` tells you by when you "
    "could stop. Otherwise the Assumptions page opens: check the person and the markets."
)
OFF = N_(
    "The quick start switches off the parts you did not name ({names}): the Features page turns "
    "them on."
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
    """A number of the quick start: the field of `datadir.Quick` that it answers and its words, in
    English (`_()` where it shows). Euros and points read at least 0, the year (`unit` None) from
    the birth to this year (`field`)."""

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
                "stop working, at 67 at the latest."
            ),
        ),
        Answer(
            "spending",
            N_("Spending per month €"),
            N_(
                "All that you spend in a month, with the rent, as one expense. The Cashflows page "
                "splits it into categories."
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
    )
}
ROWS = (("gross", "spending"), ("savings", "cash"), ("points", "since"), ("plan",))


def field(answer: Answer, born: date | None) -> fields.Field:
    """The field that reads `answer` (`fields.parse`, which says what to type): euros or points at
    least 0, a whole year from the birth to this year."""
    if answer.unit is None:
        low = (born or datadir.OLDEST).year
        return fields.Field((answer.key,), fields.Kind.INTEGER, low=low, high=date.today().year)
    return fields.Field((answer.key,), fields.Kind.NUMBER, answer.unit, low=0)


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
    is read-only or locked, a date of birth out of range (`birth` checks it already). A new plan
    opens in simple mode, which the cookie keeps from the next run on (`mode.mode_switch`)."""
    try:
        begin()
    except (ValueError, OSError) as err:  # `InputError` is a ValueError
        st.error(
            _("Not started: {directory}: {reason}").format(
                directory=literal(str(data_dir)), reason=literal(str(err))
            )
        )
        return
    st.session_state[mode.MODE], st.session_state[mode.MODE_CHOSEN] = "simple", True
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


def _answers(born: date | None) -> dict[str, Any] | None:
    """The numbers of the quick start by their keys of `datadir.Quick`, two to a row (stacked on a
    phone), below a field why it does not read, below the points `pension_note`, at the end for a
    person past the Regelaltersgrenze with a salary or a savings plan that neither pays (`RETIRED`);
    None while a field does not read."""
    values: dict[str, Any] = {}
    unread = False
    for row in ROWS:
        for column, key in zip(st.columns(2), row, strict=False):
            answer = ANSWERS[key]
            with column:
                text = st.text_input(
                    _(answer.label), key=f"decimal-welcome-{key}", help=_(answer.help)
                )
                try:
                    values[key] = fields.parse(field(answer, born), text)
                except ValueError as err:
                    st.error(literal(str(err)), icon=":material/error:")
                    unread = True
        if "points" in row and (note := pension_note(values, datadir.first_month())):
            st.caption(note)
    if (
        born is not None
        and datadir.starts_retired(born)
        and (values.get("gross") or values.get("plan"))
    ):
        st.caption(_(RETIRED))
    keyboard()
    return None if unread else values


def _quick(data_dir: Path, button: Literal["stretch", "content"]) -> None:
    """The quick start: the date of birth, a few numbers and `Start my plan`, which switches off
    every feature (`OFF`), then goes to the Overview with a salary that pays, else to the
    Assumptions page."""
    st.subheader(_("Quick start"))
    st.markdown(_(QUICK))
    st.markdown(explore(mode.View(mode.Uses(), frozenset(Feature), advanced=True)))
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
    values = _answers(born)
    pkv = st.toggle(
        _("Private health insurance (PKV)"),
        key="welcome-pkv",
        help=_(
            "Off: the statutory health insurance (GKV). On: add your premium on the Cashflows "
            "page, so that the subsidy of your employer and the tax count it."
        ),
    )
    clicked = st.button(
        _("Start my plan"),
        disabled=born is None or values is None,
        width=button,
        key="welcome-quick",
    )
    st.caption(_(OFF).format(names=mode.said(Feature)))
    if clicked and born is not None and values is not None:
        quick = datadir.Quick(born, sex, pkv=pkv, **values)
        then = "Overview" if quick.gross and not datadir.starts_retired(born) else "Assumptions"
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
