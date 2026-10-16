"""A slider and a switch of the explorer: how a slider shows a value (`Unit` and the units), a
number of the inputs as a slider (`Knob`) with its lever of the sensitivity run and its dial of
the goal seek, a yes or no as a toggle (`Switch`), and the sidebar groups by id (`GROUPS`). A key
holds no words."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date
from typing import TYPE_CHECKING, get_args

import streamlit as st
from streamlit.errors import StreamlitWidgetAlreadyInstantiatedError

from dagobert import goalseek
from dagobert.i18n import N_, NP_, _, pgettext
from dagobert.model.months import add_months, months_of_age
from dagobert.money import EUR_COLUMN, printf
from dagobert.runner import ModelName
from dagobert.sensitivity import Lever

if TYPE_CHECKING:
    from collections.abc import Collection

KEY = "explorer-"  # the widget keys of the explorer, whose values `carry` keeps across pages
CARRIED = "ui-explorer"  # session state: the `Carried` of the last run


@dataclass(frozen=True)
class Carried:
    """The values of the explorer widgets at the end of a run (`keep`) and the keys of those that
    the run drew."""

    values: dict[str, object] = field(default_factory=dict)
    drawn: frozenset[str] = frozenset()


def carry(*, arrived: bool) -> None:
    """At the start of a run (`main.py`), the value of each explorer widget that the run before
    did not draw, as plain session state, of all of them in a run that opens a page: Streamlit
    drops a widget that a run does not draw (a page switch those of the page before), and a widget
    that comes back shows a value only after a write. A widget of the run before stays as it is: a
    write tells it to take the value, and a slider that a key press moved while the page ran went
    back a step."""
    carried = st.session_state.get(CARRIED, Carried())
    for key, value in carried.values.items():
        if arrived or key not in carried.drawn:
            st.session_state[key] = st.session_state.get(key, value)


def keep() -> None:
    """At the end of a run (`main.py`), the values of the explorer widgets for `carry`, and which
    of them it drew: a widget of this run refuses the write that keeps the others."""
    values: dict[str, object] = {}
    drawn: set[str] = set()
    for key in [k for k in st.session_state if str(k).startswith(KEY)]:
        values[key] = st.session_state[key]
        try:
            st.session_state[key] = values[key]
        except StreamlitWidgetAlreadyInstantiatedError:
            drawn.add(key)
    st.session_state[CARRIED] = Carried(values, frozenset(drawn))


def forget(keys: Collection[str]) -> None:
    """The values of `keys` gone, also for `carry`: `Reset sliders` sets them to the files."""
    carried = st.session_state.get(CARRIED, Carried())
    values = {key: value for key, value in carried.values.items() if key not in keys}
    st.session_state[CARRIED] = Carried(values, carried.drawn - set(keys))
    for key in keys:
        st.session_state.pop(key, None)


@dataclass(frozen=True)
class Unit:
    """How a slider shows a value: the range before widening, in `scale` times the YAML value.
    `format` is in the dialect of Streamlit's sprintf, which groups euros (`printf`), and in
    English: one with words is a message in the context `sprintf` (`shown`)."""

    low: float
    high: float
    step: float
    format: str
    delta: float  # one step of the sensitivity run
    scale: float = 1.0
    whole: bool = False
    hard: bool = True  # the sensitivity run stays inside `low` and `high`

    @property
    def shown(self) -> str:
        """`format` in the language of the page."""
        return pgettext("sprintf", self.format)

    def bounds(self, value: float) -> tuple[float, float]:
        """Widened to include `value`, so the slider never clamps and rejects the file value."""
        return min(self.low, value * self.scale), max(self.high, value * self.scale)

    def text(self, value: float) -> str:
        return printf(self.shown, value * self.scale)

    def side(self, value: float, sign: int, origin: float) -> float:
        """`value` one sensitivity step down or up, in YAML terms, inside the range of a slider
        that starts at `origin`."""
        moved = value * self.scale + sign * self.delta
        if self.hard:
            low, high = self.bounds(origin)
            moved = min(max(moved, low), high)
        return round(moved) if self.whole else round(moved / self.scale, 6)


RATE = Unit(-2.0, 15.0, 0.25, "%.2f%%", delta=1.0, scale=100, hard=False)
SPREAD = Unit(0.0, 40.0, 0.5, "%.1f%%", delta=2.0, scale=100)
SHARE = Unit(0.0, 100.0, 1.0, "%.0f%%", delta=10.0, scale=100)
LEVEL = Unit(0.0, 150.0, 5.0, "%.0f%%", delta=10.0, scale=100)
EUR = Unit(0.0, 10000.0, 100.0, EUR_COLUMN, delta=500.0)
MONTHS = Unit(0.0, 60.0, 1.0, NP_("sprintf", "%.0f months"), delta=3.0)
FACTOR = replace(LEVEL, high=200.0)
PERIOD = Unit(1.0, 60.0, 1.0, NP_("sprintf", "%.0f months"), delta=6.0, whole=True)
SHIFT = replace(MONTHS, low=-24.0, high=48.0, whole=True)
AMOUNT = replace(EUR, step=5000.0, delta=25000.0)
# the ceiling of a payment into one Altersvorsorgedepot: 570 euros a month
PER_YEAR = Unit(0.0, 6840.0, 60.0, NP_("sprintf", "%'.,.0f € per year"), delta=600.0)
CRYPTO_RATE = Unit(-20.0, 60.0, 1.0, "%.0f%%", delta=5.0, scale=100, hard=False)
CRYPTO_SPREAD = Unit(0.0, 150.0, 5.0, "%.0f%%", delta=10.0, scale=100)
CORRELATION = Unit(-1.0, 1.0, 0.05, "%.2f", delta=0.2)
TREND = Unit(0.0, 8.0, 0.1, "%.1f%%", delta=0.5, scale=100)  # a real growth: VPW
AGE = Unit(80.0, 110.0, 1.0, "%.0f", delta=5.0, whole=True)

MARKETS = "markets"  # the sidebar groups by id, `GROUPS` their words
GOLD_CRYPTO = "gold-crypto"
SALARY = "salary"
SAVINGS = "savings"
EVENTS = "events"
ASSETS = "assets"
ALL_SPENDING = "all-spending"
BY_CATEGORY = "categories"
SPENDING = "spending"
CARE = "care"
ALLOCATION = "allocation"
SPREADS = "spreads"
TAXES = "taxes"
GROUPS = {
    MARKETS: N_("Markets"),
    GOLD_CRYPTO: N_("Gold and crypto"),
    SALARY: N_("Income"),
    SAVINGS: N_("Savings plans"),
    EVENTS: N_("Events and phases"),
    ASSETS: N_("Assets"),
    ALL_SPENDING: N_("Total spending"),
    BY_CATEGORY: N_("Spending by category"),
    SPENDING: N_("Spending rule"),
    CARE: N_("Care"),
    ALLOCATION: N_("Allocation"),
    SPREADS: N_("Spread per year (Monte Carlo)"),
    TAXES: N_("Taxes"),
}
MODELS: tuple[ModelName, ...] = get_args(ModelName)


@dataclass(frozen=True)
class Knob:
    """One number of the assumptions as a slider, its label and help in the language of the page
    that built it."""

    group: str  # an id of `GROUPS`
    label: str
    path: tuple[str, ...]
    value: float
    unit: Unit
    help: str
    origin: date | None = None  # a shift of dates in months, shown as the month it reaches
    born: date | None = None  # with `origin`: the age at that month shows too
    models: tuple[ModelName, ...] = MODELS  # where it acts: off in the others

    @property
    def key(self) -> str:
        """With the scale, the range and the value: a stored position is in shown units and holds
        for that scale and range only (a class of crypto takes a wider one than without the
        asset), and for the scenario that set the value."""
        unit = self.unit
        return (
            f"{KEY}{'.'.join(self.path)}@{unit.scale:g}[{unit.low:g},{unit.high:g}]:{self.value:g}"
        )

    def position(self, value: float) -> float:
        """The position of the slider at `value`, in YAML terms."""
        return round(value) if self.unit.whole else round(value * self.unit.scale, 6)

    @property
    def start(self) -> float:
        """The position at the file value, in shown units. A select slider finds its option by
        equality of type too: 0.0 is not the option 0."""
        shown = self.value * self.unit.scale
        return round(shown) if self.unit.whole else shown

    @property
    def moved(self) -> bool:
        """Whether its position, which `main.py` carries across runs and pages, left the file
        value: simple mode shows it then (rule `mode`)."""
        return not math.isclose(st.session_state.get(self.key, self.start), self.start)

    def reached(self, shift: int) -> str:
        """The month that a shift of `shift` months reaches from `origin`, with the age then."""
        assert self.origin is not None
        month = add_months(self.origin, shift)
        if self.born is None:
            return f"{month:%Y-%m}"
        age = months_of_age(self.born, month) // 12
        return _("{month} (age {age})").format(month=f"{month:%Y-%m}", age=age)

    def slider(self, *, disabled: bool = False) -> float:
        unit = self.unit
        st.session_state.setdefault(self.key, self.start)
        tip = _("Set in this scenario: {value}").format(value=unit.text(self.value))
        tip = f"{self.help}\n\n{tip}"
        if self.origin is not None:
            months: int = st.select_slider(
                self.label,
                list(range(round(unit.low), round(unit.high) + 1)),
                format_func=self.reached,
                key=self.key,
                help=tip,
                disabled=disabled,
            )
            return months
        shown: float = st.slider(
            self.label,
            *unit.bounds(self.value),
            step=unit.step,
            format=unit.shown,
            key=self.key,
            help=tip,
            disabled=disabled,
        )
        return round(shown) if unit.whole else round(shown / unit.scale, 6)

    def lever(self, value: float) -> Lever:
        """Around `value`, the position of the slider."""
        unit = self.unit
        return Lever(
            self.label,
            self.path,
            value,
            unit.side(value, -1, self.value),
            unit.side(value, 1, self.value),
            unit.format,
            unit.scale,
            printf(unit.shown, unit.delta),
        )

    def dial(self, value: float) -> goalseek.Dial:
        """At `value`, the position of the slider, across the range of the slider."""
        unit = self.unit
        low, high = (x / unit.scale for x in unit.bounds(self.value))
        return goalseek.Dial(
            f"{_(GROUPS[self.group])}: {self.label}",
            ((self.path, 1.0),),
            value,
            low,
            high,
            unit.step / unit.scale,
            unit.format,
            unit.scale,
            unit.whole,
            self.origin,
            self.born,
        )


@dataclass(frozen=True)
class Switch:
    """One yes or no of the assumptions as a toggle: no lever and no dial."""

    group: str  # an id of `GROUPS`
    label: str
    path: tuple[str, ...]
    value: bool
    help: str

    @property
    def key(self) -> str:
        return f"{KEY}{'.'.join(self.path)}:{self.value}"

    @property
    def moved(self) -> bool:
        """Whether it differs from the file value: simple mode shows it then."""
        return bool(st.session_state.get(self.key, self.value) != self.value)

    def toggle(self, *, compact: bool) -> bool:
        """On a phone a caption below gives the help: the icon of a `help` sits in the label of a
        toggle, and a tap on it flips the switch."""
        st.session_state.setdefault(self.key, self.value)
        on = st.toggle(self.label, key=self.key, help=None if compact else self.help)
        if compact:
            st.caption(self.help)
        return on
