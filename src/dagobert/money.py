"""Euro formatting: one format for text, tables, grids and charts. A leaf: the model, the inputs
and the pages import it without the figures."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

# The same format for a numeric column or a slider of Streamlit, whatever the browser locale.
# Streamlit's sprintf takes the custom padding character (`'.`) as the thousands separator of the
# `,` flag. It groups whole numbers only: a decimal part would also get a '.'.
GROUPED = "%'.,.0f"
EUR_COLUMN = f"{GROUPED} €"
# A plain number, such as the units of a security, keeps its decimals: a narrow no-break space
# groups the thousands, which no reader takes for a decimal mark. Ten significant digits drop
# the noise of a sum of lots.
NUMBER_COLUMN = "%'\u202f,.10g"
# Plotly: decimal point, thousands dot. Money in a figure is whole euros (`charts.EUR_TICKS`),
# so no number shows both.
SEPARATORS = ".."


def format_eur(
    value: float, *, signed: bool = False, cents: bool = False, symbol: bool = True
) -> str:
    """Thousands separators, no decimals: '1.234.567 €', or '+1.234.567 €' when `signed`.
    `cents` adds them after a decimal comma: '1.234,56 €'. Without `symbol`: '1.234.567'. A half
    rounds away from zero, as in a grid cell (`EUR_COLUMN`), and what rounds to zero has no
    minus."""
    exact = Decimal(str(value))
    if exact.is_finite():
        exact = exact.quantize(Decimal("0.01" if cents else "1"), ROUND_HALF_UP) + 0
    text = f"{exact:{'+' if signed else ''},.{2 if cents else 0}f}{' €' if symbol else ''}"
    return text.translate(str.maketrans(",.", ".,"))


def format_number(value: float, *, signed: bool = False) -> str:
    """A plain number as `NUMBER_COLUMN` shows it in a grid: `1 234.5678`, `+2` when `signed`."""
    return f"{value:{'+' if signed else ''},.10g}".replace(",", "\u202f")


def printf(fmt: str, value: float) -> str:
    """`fmt % value` as Streamlit's sprintf shows it, so a text reads like its slider: `GROUPED`
    groups like `format_eur`."""
    if GROUPED in fmt:
        return fmt.replace(GROUPED, "%s") % format_eur(value, symbol=False)
    return fmt % value
