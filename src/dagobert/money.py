"""Euro formatting: one format for text, tables, grids and charts, in both languages. Percentages
and plain numbers take the decimal mark of the language of the session (`i18n.language`): `36.6%`
and `5.00` in English, `36,6 %` and `5,00` in German. A leaf besides `i18n`: the model, the
inputs and the pages import it without the figures."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

from dagobert.i18n import language

# The same format for a numeric column or a slider of Streamlit, whatever the browser locale.
# Streamlit's sprintf takes the custom padding character (`'.`) as the thousands separator of the
# `,` flag. It groups whole numbers only: a decimal part would also get a '.'.
GROUPED = "%'.,.0f"
EUR_COLUMN = f"{GROUPED} €"
# A plain number, such as the units of a security, keeps its decimals: a narrow no-break space
# groups the thousands, which no reader takes for a decimal mark. Ten significant digits drop
# the noise of a sum of lots. Streamlit's sprintf writes a decimal point in either language.
NUMBER_COLUMN = "%'\u202f,.10g"
# Plotly per language: the decimal mark, then the thousands dot. Money in a figure is whole
# euros (`charts.EUR_TICKS`), so it reads `1.234.567` in both.
SEPARATORS = {"en": "..", "de": ",."}
# The sign after a percentage: German puts a no-break space before it
PERCENT = {"en": "%", "de": "\u00a0%"}
# a conversion of Streamlit's sprintf, as `i18n_check.SPRINTF` reads it
_CONVERSION = re.compile(r"%(?:'.|[-+ 0#,])*\d*(?:\.\d+)?[a-zA-Z%]")


def separators() -> str:
    """The `separators` of a plotly figure in the language of the session."""
    return SEPARATORS[language()]


def format_eur(
    value: float, *, signed: bool = False, cents: bool = False, symbol: bool = True
) -> str:
    """Thousands separators, no decimals: '1.234.567 €', or '+1.234.567 €' when `signed`.
    `cents` adds them after a decimal comma: '1.234,56 €'. Without `symbol`: '1.234.567'. A half
    rounds away from zero, as in a grid cell (`EUR_COLUMN`), and what rounds to zero has no
    minus. The same in both languages."""
    exact = Decimal(str(value))
    if exact.is_finite():
        exact = exact.quantize(Decimal("0.01" if cents else "1"), ROUND_HALF_UP) + 0
    text = f"{exact:{'+' if signed else ''},.{2 if cents else 0}f}{' €' if symbol else ''}"
    return text.translate(str.maketrans(",.", ".,"))


def decimal_mark(text: str) -> str:
    """A number written with a decimal point, in the decimal mark of the language: `0.5`,
    German `0,5`."""
    return text.replace(".", ",") if language() == "de" else text


def _plain(value: float, decimals: int | None, *, signed: bool, grouped: bool) -> str:
    """`decimals` fixed, else ten significant digits, with a decimal point."""
    spec = ".10g" if decimals is None else f".{decimals}f"
    return f"{value:{'+' if signed else ''}{',' if grouped else ''}{spec}}".replace(",", "\u202f")


def format_number(value: float, decimals: int | None = None, *, signed: bool = False) -> str:
    """A plain number in the decimal mark of the language, its thousands grouped by a narrow
    no-break space: `decimals` fixed (`5.00`, German `5,00`), else ten significant digits as a
    grid shows them (`NUMBER_COLUMN`: `1 234.5678`, German `1 234,5678`). `+2` when `signed`."""
    return decimal_mark(_plain(value, decimals, signed=signed, grouped=True))


def format_percent(fraction: float, decimals: int | None = 1, *, signed: bool = False) -> str:
    """A share or a rate in percent: `36.6%`, German `36,6 %` (a no-break space). `decimals` None
    keeps the decimals of the value (a loan rate `2.25%`, a full claim `100%`, a slip `1500%`)."""
    text = _plain(fraction * 100, decimals, signed=signed, grouped=False)
    return decimal_mark(text) + PERCENT[language()]


def format_size(size: int) -> str:
    """Bytes as a size of files, by 1024: `456 kB` below a tenth of a MB, `12.3 MB`, from a GB
    `1.2 GB`, in the decimal mark of the language (`12,3 MB`)."""
    if size < 2**20 // 10:
        return f"{size / 2**10:.0f} kB"
    if size < 2**30:
        return f"{format_number(size / 2**20, 1)} MB"
    return f"{format_number(size / 2**30, 1)} GB"


def printf(fmt: str, value: float) -> str:
    """`fmt % value` as Streamlit's sprintf shows it, in the decimal mark of the language, so a
    text reads like its slider: `GROUPED` groups like `format_eur`. Streamlit's sprintf writes a
    decimal point in either language: a German slider shows `2.25 %`, its text `2,25 %`."""

    def one(conversion: re.Match[str]) -> str:
        spec = conversion[0]
        if spec == "%%":
            return "%"
        return format_eur(value, symbol=False) if spec == GROUPED else decimal_mark(spec % value)

    return _CONVERSION.sub(one, fmt)
