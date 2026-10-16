"""Actual spending per month and expense category: `actuals.csv`, written by the Spend page.

One row per month and category with the monthly sum, expenses negative like the streams.
The Spend page fills it by hand."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from dagobert import cashplan, revisions
from dagobert.files import finite, read_csv
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Scenario

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FILE = "actuals.csv"
FIELDS = ("month", "category", "amount")
Amounts = dict[str, float]  # category to the sum of a month, expenses negative
Months = dict[date, Amounts]  # by first of the month, oldest first
# an edit of a category: the amount of the file when the edit began and the amount after it,
# None for no amount
Edit = tuple[float | None, float | None]
Draft = dict[str, Edit]  # the unsaved edits of a month by category
KEEPING = 3  # months back in which a record shows that the user keeps the actuals (`missing`)
# euros of plan a month from which the comparison gives a difference as a share of the plan too:
# of a smaller plan a share reads as a jump: -375% of 20 € a month
SHARE_FROM = 100.0


def read(data_dir: Path) -> Months:
    """The recorded months, oldest first. Rows of one month and category add up, in cents: a
    float sum such as -30.299999999999997 would differ from what the grid saves."""
    months: Months = {}
    rows = read_csv(
        data_dir / FILE,
        FILE,
        FIELDS,
        lambda r: (date.fromisoformat(f"{r['month'][:7]}-01"), r["category"], finite(r["amount"])),
    )
    for month, cat, amount in rows:
        sums = months.setdefault(month, {})
        sums[cat] = round(sums.get(cat, 0.0) + amount, 2)
    return dict(sorted(months.items()))


def _text(months: Months) -> str:
    """The file of `months`, sorted by month and category."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(
        (f"{m:%Y-%m}", cat, f"{value:.2f}")
        for m in sorted(months)
        for cat, value in sorted(months[m].items())
    )
    return buf.getvalue()


def _write(
    data_dir: Path, month: date, change: Callable[[Amounts], Amounts], source: str
) -> tuple[Amounts, Amounts]:
    """Replace the amounts of `month` with `change` of them, as one revision of `source`. The
    amounts before and after, read under the lock of the write, so a change on another device
    counts too."""
    month = month.replace(day=1)

    def edit() -> tuple[dict[str, str], tuple[Amounts, Amounts]]:
        months = read(data_dir)
        before = months.get(month, {})
        after = change(before)
        return {FILE: _text(months | {month: after})}, (before, after)

    return revisions.write_returning(data_dir, source, edit)


def add_spent(amounts: Amounts, cat: str, spent: float) -> Amounts:
    """`amounts` with `spent` euros more spent in `cat`: spending is negative."""
    return amounts | {cat: round(amounts.get(cat, 0.0) - spent, 2)}


def add(
    data_dir: Path, month: date, cat: str, spent: float, *, source: str
) -> tuple[Amounts, Amounts]:
    """Add `spent` euros to the spending of `cat` in `month`, as one revision of `source`. The
    amounts of the month before and after, read under the lock of the write: two quick adds at
    once both count, and an add never conflicts."""
    return _write(data_dir, month, lambda before: add_spent(before, cat, spent), source)


@dataclass(frozen=True)
class Clash:
    """A category of a draft that the file changed since the edit began, to another amount."""

    category: str
    was: float | None  # the file when the edit began
    yours: float | None
    file: float | None


class ClashError(Exception):
    """A draft that edits categories that the file changed since: nothing was saved."""

    def __init__(self, month: date, clashes: list[Clash]) -> None:
        self.month, self.clashes = month, clashes
        super().__init__(
            f"{FILE} changed in {month:%Y-%m} since the edit of "
            + ", ".join(c.category for c in clashes)
        )


def applied(saved: Amounts, draft: Draft) -> Amounts:
    """`saved` with the edits of `draft`. An edit replaces only its category, so the others keep
    what the file holds by now, also after a change on another device."""
    edited = {cat: now for cat, (_, now) in draft.items()}
    return {cat: value for cat, value in (saved | edited).items() if value is not None}


def merge(saved: Amounts, draft: Draft) -> tuple[Amounts, list[Clash]]:
    """`saved` with the edits of `draft`, three ways: an edit applies where the file still holds
    what it held when the edit began, or the edit itself. Else the category clashes and keeps the
    file. A category without an edit keeps the file."""
    clashes = [
        Clash(cat, was, now, saved.get(cat))
        for cat, (was, now) in sorted(draft.items())
        if saved.get(cat) not in (was, now)
    ]
    clashing = {clash.category for clash in clashes}
    return applied(saved, {c: e for c, e in draft.items() if c not in clashing}), clashes


def save_draft(data_dir: Path, month: date, draft: Draft, *, source: str) -> Amounts:
    """Merge `draft` into `month` as the file holds it under the lock of the write, as one
    revision of `source`: the amounts after it. A clash raises `ClashError` and saves nothing."""

    def merged(saved: Amounts) -> Amounts:
        amounts, clashes = merge(saved, draft)
        if clashes:
            raise ClashError(month, clashes)
        return amounts

    return _write(data_dir, month, merged, source)[1]


def categories(recorded: Months) -> set[str]:
    """The categories with a record in any month."""
    return {cat for sums in recorded.values() for cat in sums}


def planned(rows: list[cashplan.Row], scenario: Scenario, month: date) -> Amounts:
    """What the expense streams plan per category in `month`, in the phase of `scenario` then
    (`Scenario.phase_of`): the monthly equivalents of the Cashflows sheet, in euros of the
    simulation start."""
    phase = str(scenario.phase_of(month))
    return {
        cat: sums[phase] for cat, sums in cashplan.sheet(rows, month, [phase])["expenses"].items()
    }


@dataclass(frozen=True)
class Coverage:
    """How many of the categories that the plan of a month holds have an actual there, 0
    counts. Other categories, such as cash, do not count."""

    month: date
    recorded: int
    planned: int

    @classmethod
    def of(
        cls, recorded: Months, rows: list[cashplan.Row], scenario: Scenario, month: date
    ) -> Coverage:
        plan = planned(rows, scenario, month)
        return cls(month, len(plan.keys() & recorded.get(month, {}).keys()), len(plan))


def missing(
    recorded: Months, rows: list[cashplan.Row], scenario: Scenario, today: date
) -> Coverage | None:
    """The first complete month since the first record in which a planned category has no
    actual, also a gap before a later record. None unless a month from `KEEPING` months before
    the month of `today` on holds a record: the reminder serves a user who keeps the actuals, not
    one who never or no longer records (owner, 2026-10-13)."""
    if not any(month >= add_months(today.replace(day=1), -KEEPING) for month in recorded):
        return None
    first = min(recorded)
    months = (add_months(first, i) for i in range(months_between(first, today)))
    gaps = (Coverage.of(recorded, rows, scenario, month) for month in months)
    return next((gap for gap in gaps if gap.recorded < gap.planned), None)


@dataclass(frozen=True)
class Line:
    plan: float
    actual: float

    @property
    def difference(self) -> float:
        """Actual less plan: below zero more was spent than planned."""
        return self.actual - self.plan

    def share(self, months: int = 1) -> float | None:
        """The difference as a share of the planned spending, None where the plan over `months`
        months stays below `SHARE_FROM` euros a month."""
        return (
            self.difference / abs(self.plan)
            if round(abs(self.plan), 2) >= SHARE_FROM * months
            else None
        )

    def __add__(self, other: Line) -> Line:
        return Line(self.plan + other.plan, self.actual + other.actual)


NONE = Line(0.0, 0.0)


@dataclass(frozen=True)
class Comparison:
    """Plan and actual per month and category. A category counts in a month only with an
    actual there: an empty cell is no record, 0 is."""

    cells: dict[date, dict[str, Line]]

    @classmethod
    def of(
        cls, recorded: Months, rows: list[cashplan.Row], scenario: Scenario, count: int = 12
    ) -> Comparison:
        """The last `count` recorded months."""
        return cls(
            {
                month: _lines(planned(rows, scenario, month), recorded[month])
                for month in sorted(recorded)[-count:]
            }
        )

    def by_month(self) -> dict[date, Line]:
        return {month: sum(lines.values(), NONE) for month, lines in self.cells.items()}

    def by_category(self) -> dict[str, tuple[Line, int]]:
        """The sums over the months per category and the number of its months, by name."""
        cats = sorted({cat for lines in self.cells.values() for cat in lines}, key=str.casefold)
        return {
            cat: (
                sum((lines[cat] for lines in self.cells.values() if cat in lines), NONE),
                sum(cat in lines for lines in self.cells.values()),
            )
            for cat in cats
        }


def _lines(plan: Amounts, actual: Amounts) -> dict[str, Line]:
    """In cents like the actuals, so a month that took the plan differs by nothing."""
    return {cat: Line(round(plan.get(cat, 0.0), 2), value) for cat, value in actual.items()}
