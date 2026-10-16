"""`assumptions.yaml`: the person, the returns, the allocation, the spending rule, care, the growth
indices and the phases."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from datetime import date
from itertools import pairwise
from typing import Annotated, Literal, LiteralString

import numpy as np
from pydantic import AfterValidator, Field, ValidationError, field_validator, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError

from dagobert.files import text_only
from dagobert.model.base import (
    Day,
    Euros,
    Factor,
    Month,
    Months,
    Number,
    Percent,
    Strict,
    Unit,
    Years,
    refuse_all,
    unit,
)
from dagobert.model.months import aged, months_between, months_of_age
from dagobert.model.taxes import Allowance, Relation, TaxOptions, default_tax_year

CPI_INDEX = "cpi"
REQUIRED_CLASSES = frozenset({"equity", "fixed_income", "cash", "property"})  # of `returns`


class Distribution(Strict):
    """A yearly rate: mean and standard deviation (0 for a fixed rate)."""

    mean: Percent = Field(description="Mean per year")
    stdev: Percent = Field(
        default=0.0,
        ge=0,
        description="Standard deviation of the yearly draw. Inflation and indices draw once per "
        "calendar year, returns every month. `fixed` ignores it, `historical` too, except for "
        "the class of a gold or crypto asset that no series replays, such as `bitcoin`: that "
        "class it draws",
    )


class ReturnClass(Distribution):
    """The yearly return of an asset class. Monte Carlo ties its monthly draw to the one of equity
    by `equity_correlation`."""

    equity_correlation: Number = Field(
        default=0.0,
        ge=-1,
        le=1,
        description="Correlation of the monthly draws with equity. 0 assumes none, which "
        "understates the risk of a class that falls with shares, such as Bitcoin",
    )


class Duration(Strict):
    """A length in months: mean and standard deviation of the draw."""

    mean: Months = Field(ge=0, description="Mean length")
    stdev: Months = Field(default=0.0, ge=0, description="Standard deviation of the length")


# A phase name is a key of the inputs, an item of a flow list, a widget key and a CSS class; so is
# the short name of a relative
PHASE_NAME = re.compile(r"[a-z][a-z0-9_-]{0,23}")


def _short_name(name: str, what: str) -> str:
    """A name that YAML reads as itself: `on` or `no` would read as a bool."""
    if not PHASE_NAME.fullmatch(name) or not text_only(name):
        msg = (
            f"{name} is no {what} name: small letters, digits, - and _, a letter first, at most "
            "24 characters, no word that YAML reads as yes, no or null, such as on or off"
        )
        raise ValueError(msg)
    return name


def phase_name(name: str) -> str:
    return _short_name(name, "phase")


def relative_name(name: str) -> str:
    return _short_name(name, "relative")


PhaseName = Annotated[str, AfterValidator(phase_name)]
RelativeName = Annotated[str, AfterValidator(relative_name)]


# The ages of a child of §32 EStG: to 18 (Abs. 3), to 25 in education (Abs. 4 S. 1 Nr. 2). Law that
# no tax year changes: the model reads no tax year
CHILD_AGE, EDUCATION_AGE = 18, 25
# The Regelaltersgrenze (§35 S. 2 SGB VI), `regelaltersgrenze` of the tax year: from it no onset
# of a disability counts
REGELALTERSGRENZE = 67


class Child(Strict):
    """A child of the person: it counts for the Kindergeld and the child allowances of §32 EStG from
    the month of its birth to the month before `until`."""

    born: Day = Field(description="Date of birth")
    until: Month | None = Field(
        default=None,
        description="The first month in which the child no longer counts for the Kindergeld and "
        "the child allowances. Empty: the month after its 18th birthday, of a birthday on the "
        "first that month. At most the month after its 25th birthday, for a child in education "
        "or training",
    )
    kindergeld: bool = Field(
        default=True,
        description="The Kindergeld of the child is paid to you: the plan pays it in each month "
        "in which the child counts, the amount of the tax year, in euros of the start. Off: "
        "another person receives it, or a stream of yours pays it. The tax compares it with the "
        "child allowances either way",
    )
    freibetrag: Allowance = Field(
        default=Allowance.HALF,
        description="Your share of the Kinderfreibetrag and the Betreuungsfreibetrag: half, the "
        "share of each parent, or full when the other parent pays no support and the allowances "
        "move to you on application. The tax takes them instead of the Kindergeld where that "
        "saves more",
    )
    erziehung: bool = Field(
        default=True,
        description="The years of raising the child count for your pension: pension points for "
        "the 36 months after the month of birth, and the months to the 10th birthday count as "
        "insured. Off: the other parent raised the child",
    )

    @property
    def end(self) -> date:
        """The first month in which the child no longer counts: `until`, else at 18."""
        return self.until or aged(self.born, CHILD_AGE)

    def counts(self, month: date) -> bool:
        """The child counts in `month` (§32 Abs. 3, 4 EStG): born by it, `until` not reached."""
        return months_between(self.born, month) >= 0 and month < self.end

    @model_validator(mode="after")
    def _until_while_a_child(self) -> Child:
        """`until` after the month of birth, at most at 25 (§32 Abs. 4 S. 1 Nr. 2 EStG)."""
        last = aged(self.born, EDUCATION_AGE)
        if self.until is None or self.born < self.until <= last:
            return self
        text = (
            "until {until} is not after the month of birth: the child would never count"
            if self.until <= self.born
            else "until {until} is after {last}: a child counts at most to its 25th birthday"
        )
        found = InitErrorDetails(
            type=PydanticCustomError(
                "until", text, {"until": f"{self.until:%Y-%m}", "last": f"{last:%Y-%m}"}
            ),
            loc=("until",),
            input=self.until,
        )
        raise ValidationError.from_exception_data(type(self).__name__, [found])


class Given(Strict):
    """A gift of a relative before the start: the Erbschaftsteuer adds it to a later acquisition
    from the same giver within ten years (§14 ErbStG)."""

    at: Month = Field(description="Month of the gift, before the start")
    value: Euros = Field(description="What it was worth then, nominal")
    tax: Euros = Field(default=0.0, ge=0, description="The Schenkungsteuer paid on it, nominal")


class Relative(Strict):
    """A relative from whom the person may inherit or receive gifts: `inheritance` and `gift`
    events name it. Its relation sets the tax class and the Freibetrag of the Erbschaftsteuer, its
    date of birth and sex the life table that draws the month of its death for an inheritance
    without a month."""

    label: str = Field(default="", description="How the pages name the relative. Empty: its key")
    born: Day = Field(description="Date of birth")
    sex: Literal["m", "f"] = Field(description="For the life table, which has only these two")
    relation: Relation = Field(
        description="What the relative is to you: a parent (also a step-parent) gives 400,000 € "
        "free of tax every ten years, a grandparent 200,000 €, the others 20,000 €"
    )
    given: list[Given] = Field(
        default=[],
        description="The gifts before the start, nominal, with the tax paid on each: ten years "
        "of them count with a later acquisition",
    )


class Person(Strict):
    born: Day = Field(
        description="Date of birth. A birthday after the first of the month is reached in the "
        "month after"
    )
    sex: Literal["m", "f"] = Field(
        default="m", description="For the life table, which has only these two"
    )
    horizon_age: Annotated[int, unit(Unit.YEARS)] = Field(
        default=105, ge=1, description="The run ends at this age"
    )
    children: Annotated[int, unit(Unit.NUMBER)] = Field(
        default=0,
        ge=0,
        description="Number of children, also grown ones. Without a child the "
        "Pflegeversicherung adds the surcharge for the childless. A child that still counts for "
        "the Kindergeld needs its row in `children_born`",
    )
    rv_since: Month | None = Field(
        default=None, description="First month of uninterrupted Rentenversicherung contributions"
    )
    kvdr: bool = Field(
        default=True,
        description="Statutory health insurance only (`tax.pkv` off, or from `tax.gkv_from`): "
        "the pension makes you a compulsory member (KVdR), which pays on the pension and a "
        "company pension only. That needs nine tenths of the second half of the working life in "
        "the statutory insurance, which a late switch from the PKV seldom reaches. Off: you stay a "
        "voluntary member and pay on all income, at least on a minimum, as in the months before "
        "the pension without a salary or ALG1",
    )
    children_born: list[Child] = Field(
        default=[],
        description="The children with their dates of birth, at most `children` of them. While "
        "it counts, a child pays its Kindergeld, takes the child allowances of the tax, raises "
        "ALG1 from 60% to 67% and gives a single parent the Entlastungsbetrag. A member of the "
        "GKV pays the surcharge for the childless up to the first birth, then 0.25 points less "
        "Pflegeversicherung for each child under 25 from the second, up to the fifth",
    )
    relatives: dict[RelativeName, Relative] = Field(
        default={},
        description="The relatives from whom you may inherit or receive gifts, by a short name "
        "that the events use: never a spouse",
    )

    @model_validator(mode="after")
    def _births_of_the_children(self) -> Person:
        if len(self.children_born) > self.children:
            msg = (
                f"children_born lists {len(self.children_born)} children, children counts "
                f"{self.children}"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _relatives_older(self) -> Person:
        """A relative who gives or bequeaths is older: a younger one is outside the model."""
        found = [
            InitErrorDetails(
                type=PydanticCustomError(
                    "relative", "{name} is born after you: only older relatives", {"name": name}
                ),
                loc=("relatives", name, "born"),
                input=relative.born,
            )
            for name, relative in self.relatives.items()
            if relative.born > self.born
        ]
        refuse_all(self, found)
        return self

    @property
    def relative_labels(self) -> dict[str, str]:
        """How the pages name each relative: its label, else its key."""
        return {name: r.label or name for name, r in self.relatives.items()}

    def children_under(self, age: int, month: date) -> int:
        """The children of `children_born` that are born by `month` and reach `age` in it or
        later: one born on the first reaches it in the month before its birthday."""
        return sum(
            months_between(c.born, month) >= 0 and months_of_age(c.born, month) < 12 * age
            for c in self.children_born
        )

    def children_in(self, age: int, year: int) -> int:
        """The children of `children_born` that are under `age` in some month of `year`: born by
        its December, `age` not reached by its January."""
        first, last = date(year, 1, 1), date(year, 12, 1)
        return sum(
            months_between(c.born, last) >= 0 and months_of_age(c.born, first) < 12 * age
            for c in self.children_born
        )

    def counting(self, month: date) -> list[Child]:
        """The children that count in `month` (`Child.counts`), oldest first."""
        return [c for c in sorted(self.children_born, key=lambda c: c.born) if c.counts(month)]

    def kindergeld_in(self, year: int) -> int:
        """The children whose Kindergeld you receive in some month of `year`."""
        months = [date(year, m, 1) for m in range(1, 13)]
        return sum(c.kindergeld and any(map(c.counts, months)) for c in self.children_born)

    def parent(self, month: date) -> bool:
        """A parent in `month`: a child without a date (a grown one) or one born by then, so the
        PV surcharge for the childless holds up to the first birth (§55 Abs. 3 SGB XI)."""
        undated = self.children - len(self.children_born)
        return undated > 0 or any(months_between(c.born, month) >= 0 for c in self.children_born)

    def age(self, month: date, plus: int = 0) -> float:
        """Age in whole months, `plus` months after `month`. A birthday after the first is
        reached the month after."""
        return (months_of_age(self.born, month) + plus) / 12


class Aged(Strict):
    """A point of a list by age, linear between the ages."""

    age: Years = Field(
        ge=0,
        description="Age in years, 67.5 for 67 and a half. Each age once, the value linear "
        "between two ages",
    )


class AgePoint(Aged):
    factor: Factor = Field(description="Factor on spending at this age, in real terms")


class HazardPoint(AgePoint):
    factor: Percent = Field(ge=0, le=1, description="Yearly probability of entering care")


def _each_age_once[P: Aged](points: list[P]) -> list[P]:
    if twice := sorted(age for age, n in Counter(p.age for p in points).items() if n > 1):
        msg = f"each age once: {', '.join(f'{age:g}' for age in twice)} twice"
        raise ValueError(msg)
    return points


def interpolate(points: Sequence[AgePoint], age: float) -> float:
    """Linear between age points, flat outside."""
    pts = sorted(points, key=lambda p: p.age)
    if age <= pts[0].age:
        return pts[0].factor
    for lo, hi in pairwise(pts):
        if age <= hi.age:
            return lo.factor + (hi.factor - lo.factor) * (age - lo.age) / (hi.age - lo.age)
    return pts[-1].factor


class GlidePoint(Aged):
    share: Percent = Field(
        ge=0, le=1, description="Share of the liquid investments held as fixed income"
    )


class Allocation(Strict):
    """Target share of liquid investments held as fixed income, linear between age points."""

    fixed_income: Annotated[list[GlidePoint], AfterValidator(_each_age_once)] = Field(
        min_length=1,
        description="The glide path: the fixed-income share by age, linear between the ages, "
        "the first one held before it",
    )
    rebalance_every: Annotated[int, unit(Unit.MONTHS)] = Field(
        default=12,
        ge=1,
        description="Months between two shifts towards the fixed-income share of the glide "
        "path. A sale of equity for it realizes gains and pays tax",
    )
    skip_after_loss: Annotated[int, unit(Unit.MONTHS)] = Field(
        default=12,
        ge=0,
        description="A rebalancing sells no equity when equity fell over this many months, so a "
        "crash is not locked in. 0 always rebalances",
    )

    def share_at(self, age: float) -> float:
        return interpolate([AgePoint(age=p.age, factor=p.share) for p in self.fixed_income], age)


VPW_CAP = 0.10  # the highest payment rate of VPW, as the Bogleheads table caps it


def pmt(rate: float, years: float) -> float:
    """The payment at the start of each of `years` years that spends 1 at `rate`: an annuity
    due, as the Bogleheads table of VPW takes it."""
    if rate == 0:
        return 1 / years
    return rate / (1 - math.pow(1 + rate, -years)) / (1 + rate)


class Vpw(Strict):
    """Variable percentage withdrawal: the budget of a year is the liquid wealth times the payment
    rate of the age, the flexible categories spend what the other flows of a month leave of it."""

    growth: Percent = Field(
        default=0.03,
        ge=0,
        le=0.1,
        description="The real growth per year that the rate assumes. Bogleheads takes stocks at "
        "5.0%, bonds at 1.8%: 60/40 at 3.7%, 50/50 at 3.4%. More spends more now and less later",
    )
    horizon_age: Annotated[int, unit(Unit.YEARS)] = Field(
        default=100,
        ge=60,
        le=120,
        description="The age by which the rates would spend the wealth: the rate of a year is "
        "the payment of an annuity at the growth over the years left to this age, paid at the "
        "start of each year, at most 10%",
    )
    floor: Euros = Field(
        default=0.0,
        ge=0,
        description="The least that the flexible categories spend per month in a month without "
        "pay, in start-year euros, while one of them pays: below it the rule pays the floor and "
        "sells for it. The roll forward changes it by the consumer prices",
    )

    def rate_at(self, age: float) -> float:
        """The share of the liquid wealth that the budget of a year takes at `age`."""
        return min(pmt(self.growth, max(self.horizon_age - age, 1)), VPW_CAP)


class Spending(Strict):
    """Cut flexible expenses while liquid wealth is below trigger * the reference wealth, raise
    them while it is above ceiling * the reference wealth (both in real terms), or spend them by
    VPW (`vpw`), and scale expenses by age (`age_curve`, real terms) in `age_categories`
    (default: all expense streams except the health premium and the costs of a let property)."""

    base: Literal["start", "no_pay"] = Field(
        default="start",
        description="The reference wealth that the cut and the increase compare with. `start`: "
        "the liquid wealth at the start, in every month. `no_pay`: the liquid wealth at the first "
        "month without a salary or a profit, and the rules act only in a month after a month "
        "without pay. After twelve months of pay in a row the next month without pay takes a new "
        "reference: the retirement after a career break and a new job takes its own",
    )
    reference: Euros | None = Field(
        default=None,
        description="The reference wealth of the start in start-year euros, with `start` or with "
        "`no_pay` when the plan starts without pay. Empty: the liquid wealth of the start, which "
        "changes with each new start. The roll forward changes a value by the consumer prices",
    )
    cut: Percent = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Share taken off the flexible categories while the trigger holds",
    )
    trigger: Percent = Field(
        default=0.0,
        ge=0,
        description="The cut applies in every month that starts with liquid wealth below this "
        "share of the reference wealth, in real terms. It ends when the wealth is back above it. "
        "0 switches the cut off",
    )
    increase: Percent = Field(
        default=0.0,
        ge=0,
        description="Share added to the flexible categories while the ceiling holds, only with "
        "the reference wealth of the first month without pay: while you work, your wealth soon "
        "passes the wealth of the start. 0 switches the increase off",
    )
    ceiling: Percent = Field(
        default=0.0,
        ge=0,
        description="The increase applies in every month that starts with liquid wealth above "
        "this share of the reference wealth, in real terms, and above the trigger. It ends when "
        "the wealth is back below it. 0 switches the increase off",
    )
    categories: list[str] = Field(
        default=[], description="The flexible categories that the cut, the increase or VPW change"
    )
    age_curve: Annotated[list[AgePoint], AfterValidator(_each_age_once)] = Field(
        default=[],
        description="Factor on spending by age, in real terms, linear between the ages, the "
        "first one held before it",
    )
    age_categories: list[str] | None = Field(
        default=None,
        description="The categories that the age curve reaches. None: every expense stream "
        "except the health premium and the costs of a let property",
    )
    vpw: Vpw | None = Field(
        default=None,
        description="Variable percentage withdrawal (VPW) instead of the cut and the increase: "
        "the budget of a year is the liquid wealth of its first month without pay times the "
        "rate of the age. In each month without pay the flexible categories spend a twelfth of "
        "it, plus the income of the month, less the other spending, the loan payments and a "
        "twelfth of the tax bill of the year before, at least the floor. In a month with pay "
        "they spend as planned. Needs `The first month without pay`",
    )

    @model_validator(mode="after")
    def _rules_fit(self) -> Spending:
        """An increase needs `no_pay` and a ceiling above the trigger, VPW `no_pay`, flexible
        categories and neither cut nor increase, at the field that sets it."""
        found: list[InitErrorDetails] = []

        def refuse(key: str, message: LiteralString, value: object, **context: str) -> None:
            error = PydanticCustomError("spending", message, context or None)
            found.append(InitErrorDetails(type=error, loc=(key,), input=value))

        if self.increase and self.base != "no_pay":
            refuse("increase", "an increase needs base: no_pay", self.increase)
        if self.increase and self.ceiling and self.ceiling <= self.trigger:
            refuse(
                "ceiling",
                "ceiling {ceiling} is not above trigger {trigger}",
                self.ceiling,
                ceiling=f"{self.ceiling * 100:g}%",
                trigger=f"{self.trigger * 100:g}%",
            )
        if (vpw := self.vpw) is not None:
            if self.base != "no_pay":
                refuse("vpw", "VPW needs base: no_pay", vpw.model_dump())
            if self.trigger or self.increase:
                refuse(
                    "vpw",
                    "VPW replaces the cut and the increase: set trigger and increase to 0",
                    vpw.model_dump(),
                )
            if not self.categories:
                refuse("vpw", "VPW needs the flexible categories", vpw.model_dump())
        refuse_all(self, found)
        return self


def hazard_at(points: Sequence[AgePoint], age: float) -> float:
    """Zero before the first age of a `hazard` table, flat after the last."""
    return 0.0 if age < min(p.age for p in points) else interpolate(points, age)


class CareOptions(Strict):
    """Stochastic long-term care episode per path. `fixed` draws none."""

    hazard: Annotated[list[HazardPoint], AfterValidator(_each_age_once)] = Field(
        min_length=1,
        description="Yearly probability of entering care by age, linear between the ages, zero "
        "before the first and flat after the last",
    )
    cost: Euros = Field(
        gt=0,
        description="Cost of a care episode per month above the Pflegeversicherung benefit, in "
        "start-year euros",
    )
    duration: Duration = Field(description="Length of a care episode")
    index: str | None = Field(
        default=CPI_INDEX,
        description="What the cost follows: `cpi`, the consumer prices, an index of `indices`, or "
        "null for nominal euros",
    )

    def hazard_at(self, age: float) -> float:
        return hazard_at(self.hazard, age)


class DisabilityPoint(AgePoint):
    factor: Percent = Field(
        ge=0, le=1, description="Yearly probability of a full Erwerbsminderung at this age"
    )


# The yearly chance of a full Erwerbsminderung by age: 171,732 new EM-Renten in 2024 on 38.6 Mio.
# aktiv Versicherte of 15 to 64 (DRV, Aktuelle Daten; RV in Zahlen 2026), 4.45 per 1,000, spread by
# their ages (DRV, Versicherte 2024, table 3.00 V) so that the rate-weighted age is the mean age at
# the start of an EM-Rente, 53.8, less the seven months before it (§101 Abs. 1 SGB VI)
DEFAULT_HAZARD = tuple(
    DisabilityPoint(age=age, factor=chance)
    for age, chance in (
        (20, 0.00044),
        (30, 0.00099),
        (40, 0.00226),
        (50, 0.00512),
        (55, 0.00772),
        (60, 0.01162),
        (64, 0.01614),
    )
)


class DisabilityOptions(Strict):
    """A full Erwerbsminderung (under three hours of work a day, §43 Abs. 2 SGB VI), at most once
    per path and to the end: an onset drawn per path by the yearly chance by age, or forced in
    every path at `at`."""

    hazard: Annotated[list[DisabilityPoint], AfterValidator(_each_age_once)] = Field(
        default=list(DEFAULT_HAZARD),
        min_length=1,
        description="Yearly probability of a full Erwerbsminderung by age, linear between the "
        "ages, zero before the first, flat after the last and zero from the Regelaltersgrenze. "
        "Default: a curve fitted to the new EM-Renten of the DRV, about 4.5 in 1,000 a year on "
        "average, rising with age",
    )
    at: Month | None = Field(
        default=None,
        description="A what-if: the onset in this month in every path, also in a `fixed` run, "
        "instead of the drawn one. Empty: drawn per path",
    )

    def hazard_at(self, age: float) -> float:
        return hazard_at(self.hazard, age)


class Scale(Strict):
    """What-if factors on the plan, 1 when absent. The explorer's sliders write them."""

    spending: Factor = Field(
        default=1.0,
        description="Every expense stream that `categories` reaches, on top of its category factor",
    )
    categories: dict[str, Factor] = Field(
        default={},
        description="Expense streams by `cat`, except the health premium and the costs of a let "
        "property",
    )
    salary: dict[str, Factor] = Field(
        default={},
        description="Every salary payment and profit of a business in a phase, before tax and SV",
    )
    savings: dict[str, Factor] = Field(
        default={}, description="The rate of a savings plan, by the name of its stream"
    )


class Index(Distribution):
    """Yearly draw, stepped each January. `floor` and `cap` clip the draws.

    Cumulative (default): the draw is annual growth and the level compounds.
    Non-cumulative: the draw itself is the level, for example a bonus payout ratio."""

    floor: Percent | None = Field(default=None, description="Lowest draw")
    cap: Percent | None = Field(default=None, description="Highest draw")
    cumulative: bool = Field(
        default=True,
        description="True: the draw is growth and compounds. False: the draw is the level, for "
        "example the payout ratio of a bonus",
    )

    @model_validator(mode="after")
    def _floor_below_cap(self) -> Index:
        if self.floor is not None and self.cap is not None and self.floor > self.cap:
            msg = f"floor {self.floor * 100:g}% is above cap {self.cap * 100:g}%"
            raise ValueError(msg)
        return self

    @property
    def at_mean(self) -> float:
        """The clipped mean: the draw of every year in the `fixed` and `historical` modes."""
        return float(np.clip(self.mean, self.floor, self.cap))


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue"})


def phase_name_for(label: str, taken: Collection[str]) -> str:
    """A phase name for a new phase from its label, one that `taken` lacks: small letters, the
    umlauts written out, `-` between the words (`Career break`: `career-break`), `phase-` before
    one that would start with a digit or read as a YAML word (`on`), a number after a taken one."""
    plain = unicodedata.normalize("NFKD", label.casefold().translate(_UMLAUTS))
    base = re.sub(r"[^a-z0-9]+", "-", plain.encode("ascii", "ignore").decode()).strip("-")
    if not re.match(r"[a-z]", base) or not text_only(base):
        base = f"phase-{base}".strip("-")
    name, n = base[:24].rstrip("-"), 1
    while name in taken:
        n += 1
        name = f"{base[: 23 - len(str(n))].rstrip('-')}-{n}"
    return name


class PhaseSpec(Strict):
    """A phase of life that a scenario switches to: the streams, the factors per phase, the bAV
    contributions and the salary scale name it."""

    label: str = Field(
        default="",
        description="How the pages name the phase, with capitals and umlauts: `Career break`. "
        "Empty: its name",
    )


UNKNOWN_PHASE: LiteralString = (
    "the phase {name} is not defined: add it under phases in assumptions.yaml (the Assumptions "
    "page) or name one of {known}"
)


def unknown_phase(loc: tuple[str | int, ...], name: str, known: Iterable[str]) -> InitErrorDetails:
    return InitErrorDetails(
        type=PydanticCustomError(
            "unknown_phase", UNKNOWN_PHASE, {"name": name, "known": ", ".join(known)}
        ),
        loc=loc,
        input=name,
    )


class Assumptions(Strict):
    person: Person
    start: Month = Field(
        description="First simulated month. Every amount in `cashflows.yaml` is in the euros of "
        "this month. The `Roll forward` of the Overview moves it"
    )
    phases: dict[PhaseName, PhaseSpec] = Field(
        min_length=1,
        description="The phases of life that the scenarios switch between, such as work, a "
        "career break or retirement, in the order of the columns and the colors. A stream pays "
        "in the phases of its row, the employer into a bAV policy in those of the policy, and the "
        "salary scale names them too. The name is what the files write: small letters, digits, - "
        "and _; a `label` names the phase on the pages, with capitals and umlauts. A phase that "
        "an input names keeps its name. Defined here only, not in a scenario",
    )
    inflation: Distribution = Field(
        default=Distribution(mean=0.02, stdev=0.01),
        description="Consumer prices per year. Every stream with the default `index: cpi` grows "
        "with them. Monte Carlo draws one rate per calendar year, at least -2%",
    )
    indices: dict[str, Index] = Field(
        default={},
        description="Named growth indices that streams can follow instead of the consumer prices",
    )
    returns: dict[str, ReturnClass] = Field(
        description="Nominal return per year by class: `equity`, `fixed_income`, `cash` and "
        "`property` are required, another class serves as the `growth` of an asset"
    )
    refinance_rate: Percent = Field(
        default=0.04,
        description="Rate of every loan after its `fixed_until`. The annuity stays, so a higher "
        "rate repays more slowly",
    )
    cash_buffer_months: Months = Field(
        default=3.0,
        ge=0,
        description="Months of expected expenses kept as cash before a surplus is invested. A "
        "ceiling only: a deficit does not refill it, and a savings plan draws below it",
    )
    invest_rest: bool = Field(
        default=True,
        description="Invest the cash above the buffer each month. False keeps it in cash: only "
        "the savings plans and the `invest` of a sale invest",
    )
    pension_growth: Percent = Field(
        default=0.0,
        description="Growth of the pension per year on top of the `index` of its stream, before "
        "and after the claim. The default index is the consumer prices, so this is the real "
        "growth: the Rentenwert follows the gross wages, damped by the Nachhaltigkeitsfaktor "
        "(§68 SGB VI). Below 0 the real pension falls every year",
    )
    allocation: Allocation | None = Field(
        default=None, description="Without it every surplus goes into equity"
    )
    spending: Spending | None = Field(
        default=None,
        description="A cut of the flexible categories while liquid wealth is low, an increase "
        "while it is high, and a factor on spending by age. Without it spending follows the plan",
    )
    care: CareOptions | None = Field(
        default=None,
        description="Long-term care episodes, drawn per path by the yearly chance by age. `fixed` "
        "draws none. Without it no path needs care",
    )
    disability: DisabilityOptions | None = Field(
        default=None,
        description="The risk of losing the ability to work: a full Erwerbsminderung drawn per "
        "path by the yearly chance by age, then Krankengeld, the EM-Rente of the pension and the "
        "benefit of a BU policy. `fixed` draws none, but a forced month `at`. Without it no path "
        "loses the ability to work",
    )
    scale: Scale = Scale()
    tax: TaxOptions = TaxOptions()
    seed: Annotated[int, unit(Unit.NUMBER)] = Field(
        default=7,
        description="Seed for engine draws: care episodes, the onset of a disability, sale prices",
    )

    @property
    def tax_year(self) -> int:
        """`tax.year`, else `default_tax_year` of `start`: the engine applies the constants in
        euros of the start."""
        return self.tax.year or default_tax_year(self.start)

    @property
    def phase_labels(self) -> dict[str, str]:
        """How the pages name each phase, in the order of `phases`."""
        return {name: spec.label or name for name, spec in self.phases.items()}

    @model_validator(mode="after")
    def _given_before_start(self) -> Assumptions:
        """A gift of `given` lies before the start: a later one is a `gift` event."""
        found = [
            InitErrorDetails(
                type=PydanticCustomError(
                    "given",
                    "the gift of {month} lies after the start {start}: make it a gift event",
                    {"month": f"{g.at:%Y-%m}", "start": f"{self.start:%Y-%m}"},
                ),
                loc=("person", "relatives", name, "given", i, "at"),
                input=g.at,
            )
            for name, relative in self.person.relatives.items()
            for i, g in enumerate(relative.given)
            if g.at >= self.start
        ]
        refuse_all(self, found)
        return self

    @model_validator(mode="after")
    def _disabled_in_the_run(self) -> Assumptions:
        """A forced onset lies in the run, before the Regelaltersgrenze: a plan that starts
        disabled is not modelled, and from that age the old-age pension pays (§43 SGB VI)."""
        at = self.disability.at if self.disability else None
        if at is None:
            return self
        age = int(self.person.age(at))
        if at < self.start:
            error = PydanticCustomError(
                "disability",
                "the onset {month} lies before the start {start}: a plan cannot start disabled, "
                "move it or remove it",
                {"month": f"{at:%Y-%m}", "start": f"{self.start:%Y-%m}"},
            )
        elif age >= REGELALTERSGRENZE:
            error = PydanticCustomError(
                "disability",
                "the onset {month} lies at the age of {age}: from {limit} the old-age pension "
                "pays, not a disability, move it or remove it",
                {"month": f"{at:%Y-%m}", "age": age, "limit": REGELALTERSGRENZE},
            )
        else:
            return self
        found = InitErrorDetails(type=error, loc=("disability", "at"), input=at)
        raise ValidationError.from_exception_data(type(self).__name__, [found])

    @model_validator(mode="after")
    def _phases_named(self) -> Assumptions:
        """The salary scale names defined phases, and no two phases show alike."""
        found = [
            unknown_phase(("scale", "salary", name), name, self.phases)
            for name in self.scale.salary
            if name not in self.phases
        ]
        shown = Counter(self.phase_labels.values())
        found += [
            InitErrorDetails(
                type=PydanticCustomError(
                    "phase_label", "another phase shows as {label} too", {"label": label}
                ),
                loc=("phases", name, "label"),
                input=label,
            )
            for name, label in self.phase_labels.items()
            if shown[label] > 1
        ]
        refuse_all(self, found)
        return self

    @field_validator("returns")
    @classmethod
    def _classes_known(cls, returns: dict[str, ReturnClass]) -> dict[str, ReturnClass]:
        if missing := sorted(REQUIRED_CLASSES - returns.keys()):
            msg = f"needs the class{'es' if len(missing) > 1 else ''} {', '.join(missing)}"
            raise ValueError(msg)
        if returns["equity"].equity_correlation:
            msg = "equity: equity_correlation belongs to another class"
            raise ValueError(msg)
        return returns

    @field_validator("indices")
    @classmethod
    def _cpi_reserved(cls, indices: dict[str, Index]) -> dict[str, Index]:
        if CPI_INDEX in indices:
            msg = f"the name {CPI_INDEX} is reserved for the consumer prices"
            raise ValueError(msg)
        return indices
