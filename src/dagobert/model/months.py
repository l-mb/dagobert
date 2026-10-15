"""The month arithmetic of every module: days within a month do not count."""

from __future__ import annotations

from datetime import date


def months_between(start: date, end: date) -> int:
    """Whole calendar months from `start` to `end`, days ignored."""
    return (end.year - start.year) * 12 + end.month - start.month


def months_of_age(born: date, month: date) -> int:
    """Whole months of age at the start of `month`. An age is reached at the end of the day
    before the birthday (§187 Abs. 2 S. 2, §188 Abs. 2 BGB): a birthday on the first of a month
    at its start, a later one in the month after."""
    return months_between(born, month) - (born.day > 1)


def add_months(day: date, n: int) -> date:
    """The first of the month `n` months after `day`."""
    total = day.year * 12 + day.month - 1 + n
    return date(total // 12, total % 12 + 1, 1)


def aged(born: date, age: int) -> date:
    """The first month at whose start a person born on `born` is `age` years old: the month after
    the birthday, of a birthday on the first its month (`months_of_age`)."""
    return add_months(born, 12 * age + (born.day > 1))
