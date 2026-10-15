"""The euro format and the printf formats of grid columns."""

from dagobert.money import EUR_COLUMN, format_eur, printf


def test_format_eur() -> None:
    assert format_eur(1_234_567.4) == "1.234.567 €"
    assert format_eur(-98_765) == "-98.765 €"
    assert format_eur(12, signed=True) == "+12 €"
    assert format_eur(-20.5) == "-21 €"  # a half away from zero, as in a grid cell
    assert format_eur(-0.4) == "0 €"
    assert printf(f"{EUR_COLUMN} per year", 1800) == "1.800 € per year"
    assert printf("%.2f%%", 14.1) == "14.10%"
