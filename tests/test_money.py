"""The euro format, the percentages and plain numbers of each language, and the printf formats of
grid columns and sliders."""

import pytest

from dagobert import i18n
from dagobert.i18n import pgettext
from dagobert.money import (
    EUR_COLUMN,
    format_eur,
    format_number,
    format_percent,
    format_size,
    printf,
    separators,
)


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_format_eur(lang: i18n.Language) -> None:
    """One euro format in both languages."""
    with i18n.use(lang):
        assert format_eur(1_234_567.4) == "1.234.567 €"
        assert format_eur(-98_765) == "-98.765 €"
        assert format_eur(12, signed=True) == "+12 €"
        assert format_eur(-20.5) == "-21 €"  # a half away from zero, as in a grid cell
        assert format_eur(-0.4) == "0 €"
        assert format_eur(1234.56, cents=True) == "1.234,56 €"
        assert printf(f"{EUR_COLUMN} per year", 1800) == "1.800 € per year"


@pytest.mark.parametrize(
    ("lang", "percents", "numbers", "said"),
    [
        (
            "en",
            ["36.6%", "+1.2%", "2.25%", "100%", "1500%", "36%"],
            ["5.00", "1\u202f234.5678", "+0.5", "9.24", "1 kB", "12.3 MB", "1.5 GB"],
            ["14.10%", "0.25", "3 months"],
        ),
        (
            "de",
            ["36,6\u00a0%", "+1,2\u00a0%", "2,25\u00a0%", "100\u00a0%", "1500\u00a0%", "36\u00a0%"],
            ["5,00", "1\u202f234,5678", "+0,5", "9,24", "1 kB", "12,3 MB", "1,5 GB"],
            ["14,10\u00a0%", "0,25", "3 Mon."],
        ),
    ],
)
def test_a_percent_and_a_plain_number_take_the_decimal_mark_of_the_language(
    lang: i18n.Language, percents: list[str], numbers: list[str], said: list[str]
) -> None:
    """German writes a decimal comma and a no-break space before `%`, English a point and none; a
    rate keeps its decimals; a plain number groups its thousands by a narrow no-break space, a
    percent never; a size of files takes the unit that it reaches. A sprintf format of a slider
    reads in the language of the page: its text in the decimal mark of the language, the figures
    with their separators."""
    with i18n.use(lang):
        assert [
            format_percent(0.366),
            format_percent(0.012, signed=True),
            format_percent(0.0225, None),
            format_percent(1.0, None),
            format_percent(15.0, None),
            format_percent(0.364, 0),
        ] == percents
        assert [
            format_number(5, 2),
            format_number(1234.5678),
            format_number(0.5, signed=True),
            format_number(9.2449, 2),
            format_size(1000),
            format_size(12_900_000),
            format_size(3 * 2**29),
        ] == numbers
        assert [
            printf(pgettext("sprintf", "%.2f%%"), 14.1),
            printf("%.2f", 0.25),
            printf(pgettext("sprintf", "%.0f months"), 3),
        ] == said
        assert separators() == {"en": "..", "de": ",."}[lang]
