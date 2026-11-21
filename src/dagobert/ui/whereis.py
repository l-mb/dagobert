"""The page `Where is what`: the inputs of the plan by subject, each a link to the page and the
tab that holds it. A subject is spread over pages (the health insurance: the insurance on the
Assumptions page, its premiums on Cashflows, a prepayment an event of a scenario), and a user who
comes a few times a year looks for it by subject. The links take `?tab=` (`ui.TAB`), which the
Assumptions, Cashflows and Scenarios pages open."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from dagobert.i18n import N_, _
from dagobert.ui import PAGES, TAB, page_link

# the tabs of the Assumptions page by key (`assumptions.Tab`), of the other pages by their name
PERSON, MARKETS, INVESTING, RISKS, INSURANCE, TAX = (
    ("person", N_("Person")),
    ("markets", N_("Markets")),
    ("investing", N_("Investing")),
    ("risks", N_("Spending and risks")),
    ("insurance", N_("Health insurance")),
    ("tax", N_("Tax")),
)
INTRO = N_("Where each input of your plan is, by subject. A link opens its page and tab.")


@dataclass(frozen=True)
class Place:
    """What a user looks for, the page that holds it (its English title) and its tab there: the
    value of `?tab=` and its words."""

    what: str
    page: str
    tab: tuple[str, str] | None = None

    @property
    def where(self) -> str:
        """The page and its tab in the language of the session, joined by a chevron."""
        return " › ".join(_(part) for part in (self.page, *(self.tab[1:] if self.tab else ())))

    def link(self) -> None:
        """What it is and, beside it, the link to its place: below it where the row is too
        narrow, as on a phone, where one label of both was cut. Nothing for a page that the
        navigation leaves out."""
        if st.session_state.get(PAGES, {}).get(self.page) is None:
            return
        with st.container(horizontal=True, wrap=True, vertical_alignment="center"):
            st.markdown(_(self.what))
            page_link(self.page, self.where, {TAB: self.tab[0]} if self.tab else None)


def _stream(what: str, tab: str) -> Place:
    return Place(what, "Cashflows", (tab, tab))


def _scenario(what: str, tab: str) -> Place:
    return Place(what, "Scenarios", (tab, tab))


def _assumed(what: str, tab: tuple[str, str]) -> Place:
    return Place(what, "Assumptions", tab)


EXPENSES, INCOME, SAVINGS = N_("expenses"), N_("income"), N_("savings")
PREMIUMS, BU = N_("health insurance"), N_("disability insurance")
PHASES, EVENTS, OVERRIDES = N_("Phases"), N_("Events"), N_("Overrides")
SUBJECTS: dict[str, tuple[Place, ...]] = {
    N_("You and the phases of your life"): (
        _assumed(N_("Date of birth, the age that the plan reaches, children"), PERSON),
        _assumed(N_("The phases, their names and their raises"), PERSON),
        _scenario(N_("When a phase begins"), PHASES),
    ),
    N_("Work and income"): (
        _stream(N_("Salary, bonus, other income"), INCOME),
        _assumed(N_("Raises per year in a phase"), PERSON),
        _assumed(N_("The index that a salary follows"), MARKETS),
        _scenario(N_("A job loss, a severance, a new job"), EVENTS),
        _scenario(N_("Another salary in one scenario only"), OVERRIDES),
        _stream(N_("The profit of a business"), INCOME),
        _assumed(N_("Pension and health insurance of a business"), TAX),
    ),
    N_("Health insurance"): (
        _assumed(N_("Private or statutory, a change, a cap of the premium"), INSURANCE),
        _stream(N_("The premiums of a private insurance, Krankentagegeld"), PREMIUMS),
        _scenario(N_("Premiums paid in advance"), EVENTS),
    ),
    N_("Pension"): (
        _stream(N_("The statutory pension and its points"), INCOME),
        _assumed(N_("Pension insurance since, pension growth"), PERSON),
        Place(N_("Company pension, Basisrente, Altersvorsorgedepot"), "Assets"),
    ),
    N_("Investing"): (
        Place(N_("Accounts, depots, trades, gold and crypto"), "Assets"),
        _stream(N_("Savings plans"), SAVINGS),
        _assumed(N_("Returns, volatility, inflation"), MARKETS),
        _assumed(N_("Cash buffer and allocation"), INVESTING),
        _assumed(N_("Realize gains each year"), TAX),
    ),
    N_("Property and loans"): (
        Place(N_("A property and its loan"), "Assets"),
        _stream(N_("Rent and the costs of a let property"), INCOME),
        _scenario(N_("Buy or sell a property, repay a loan"), EVENTS),
        _assumed(N_("The loan rate after the fixed period"), MARKETS),
    ),
    N_("What you spend"): (
        _stream(N_("Your expenses by category"), EXPENSES),
        _assumed(N_("The spending rule: cuts in bad years"), RISKS),
        _scenario(N_("A one-off payment, such as a car"), EVENTS),
        Place(N_("What you spent in a month"), "Spend"),
    ),
    N_("Taxes"): (
        _assumed(N_("Church tax, Bundesland, losses, work expenses"), TAX),
        _stream(N_("An expense that lowers the tax"), EXPENSES),
        _assumed(N_("A change of the law as a stress test"), TAX),
    ),
    N_("Risks"): (
        _assumed(N_("Disability and long-term care"), RISKS),
        _stream(N_("A disability insurance (BU)"), BU),
        _assumed(N_("Relatives you may inherit from"), PERSON),
        _scenario(N_("An inheritance or a gift"), EVENTS),
    ),
    N_("Records"): (
        Place(N_("Today's values of your accounts, prices"), "Snapshot"),
        Place(N_("Price and inflation series"), "Data"),
    ),
}


def page() -> None:
    st.title(_("Where is what"))
    st.caption(_(INTRO))
    for subject, places in SUBJECTS.items():
        with st.container(key=f"whereis-{list(SUBJECTS).index(subject)}"):
            st.subheader(_(subject))
            for place in places:
                place.link()
