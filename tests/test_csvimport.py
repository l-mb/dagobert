"""The column mapper of a downloaded price history: the common layouts guess right, and a line
that does not read is refused with its reason while the others stay."""

from __future__ import annotations

from datetime import date

import pytest

from dagobert import csvimport
from dagobert.csvimport import Mapping
from dagobert.problems import RefusedError

GERMAN = (
    "Datum;Eröffnung;Hoch;Tief;Schluss;Volumen\n"
    "02.01.2026;101,10;102,00;100,50;1.101,50;12.345\n"
    "31.12.2025;100,00;101,20;99,50;1.100,90;1.234\n"
)
DECEMBER, JANUARY = date(2025, 12, 31), date(2026, 1, 2)
TODAY = date(2026, 1, 6)


@pytest.mark.parametrize(
    ("raw", "mapping", "points"),
    [
        pytest.param(
            GERMAN.encode(),
            Mapping(0, 4, ",", "dmy"),
            [(DECEMBER, 1100.9), (JANUARY, 1101.5)],
            id="german",
        ),
        pytest.param(
            b"Date,Open,High,Low,Close,Adj Close,Volume\n"
            b"2025-12-31,100.1,101.2,99.5,100.9,98.7,12345\n"
            b"2026-01-02,101.1,102.0,100.5,101.5,99.3,23456\n",
            Mapping(0, 4, ".", "ymd"),
            [(DECEMBER, 100.9), (JANUARY, 101.5)],
            id="english",
        ),
        pytest.param(  # `Close` before `Adj Close`, which a dividend lowers backwards
            b'Date,Adj Close,Close,Volume\n2025-12-31,"1,198.70","1,234.50","12,345"\n',
            Mapping(0, 2, ".", "ymd"),
            [(DECEMBER, 1234.5)],
            id="adj-close",
        ),
        pytest.param(
            b"\xef\xbb\xbf" + GERMAN.encode(),
            Mapping(0, 4, ",", "dmy"),
            [(DECEMBER, 1100.9), (JANUARY, 1101.5)],
            id="bom",
        ),
        pytest.param(
            "Datum;Rücknahmepreis;Währung\n31.12.2025;12,34;EUR\n".encode("cp1252"),
            Mapping(0, 1, ",", "dmy", 2),
            [(DECEMBER, 12.34)],
            id="cp1252",
        ),
        pytest.param(
            b"Fondspreise\nISIN;IE00B4L5Y983\nZeitraum;01.12.2025 - 31.12.2025\n\n"
            b"Datum;Kurs\n31.12.2025;100,5\n",
            Mapping(0, 1, ",", "dmy"),
            [(DECEMBER, 100.5)],
            id="preamble",
        ),
        pytest.param(
            b"Date,Price\n12/31/2025,100.5\n01/02/2026,101\n",
            Mapping(0, 1, ".", "mdy"),
            [(DECEMBER, 100.5), (JANUARY, 101.0)],
            id="mdy",
        ),
        pytest.param(
            b"Date,Price\n02/01/2026,101\n31/12/2025,100.5\n",
            Mapping(0, 1, ".", "dmy"),
            [(DECEMBER, 100.5), (JANUARY, 101.0)],
            id="dmy-slashes",
        ),
        pytest.param(  # the date names the month, quoted for its comma
            b'"Date","Price","Open"\n"Jan 02, 2026","101.50","101.10"\n'
            b'"Dec 31, 2025","1,100.90","100.00"\n',
            Mapping(0, 1, ".", "mdy"),
            [(DECEMBER, 1100.9), (JANUARY, 101.5)],
            id="month-name-english",
        ),
        pytest.param(
            b"Datum;Schluss\n2. Jan. 2026;101,5\n31. Dez. 2025;1.100,9\n",
            Mapping(0, 1, ",", "dmy"),
            [(DECEMBER, 1100.9), (JANUARY, 101.5)],
            id="month-name-german",
        ),
        pytest.param(  # no price header: the last numeric column that holds no volume
            b"Day\tFirst\tLast\tVolume\n2025-12-31\t12.3\t12.3456\t100\n",
            Mapping(0, 2, ".", "ymd"),
            [(DECEMBER, 12.3456)],
            id="tab",
        ),
    ],
)
def test_common_layouts_guess_right(
    raw: bytes, mapping: Mapping, points: list[tuple[date, float]]
) -> None:
    table = csvimport.sniff(raw)
    assert csvimport.guess(table) == mapping
    parsed = csvimport.parse(table, mapping, today=TODAY)
    assert parsed.points == points
    assert parsed.refused == []


@pytest.mark.parametrize(
    ("cell", "day"),
    [
        *(
            (cell, DECEMBER)
            for cell in (
                "Dec 31, 2025",
                "December 31, 2025",
                "dec 31 2025",
                "Dez. 31, 2025",
                "31-Dec-2025",
                "31-Dec-25",
                "31 Dec 2025",
                "31 December 2025",
                "31. Dez. 2025",
                "31. Dez 2025",
                "31.Dez.2025",
                "31. Dezember 2025",
                "31. DEZ. 2025 17:30",
            )
        ),
        ("3. März 2025", date(2025, 3, 3)),
        ("3. Mrz 2025", date(2025, 3, 3)),
        ("Mar 3, 2025", date(2025, 3, 3)),
        ("1. Mai 2025", date(2025, 5, 1)),
        ("May 1, 2025", date(2025, 5, 1)),
        ("1. Okt. 2025", date(2025, 10, 1)),
        ("Sept 1, 2025", date(2025, 9, 1)),
        ("2. Jän. 2026", JANUARY),
        ("30. Feb. 2025", None),
        ("31. Foo 2025", None),
        ("Quartal 4 2025", None),
    ],
)
@pytest.mark.parametrize("order", csvimport.DATE_ORDERS)
def test_a_named_month_reads_in_any_order(
    cell: str, day: date | None, order: csvimport.DateOrder
) -> None:
    assert csvimport.read_date(cell, order) == day


def test_a_line_that_does_not_read_is_refused_and_the_others_stay() -> None:
    table = csvimport.sniff(
        b"Datum;Schluss;W\xc3\xa4hrung\n"
        b"30.12.2025;100,10;EUR\n"
        b"31.12.2025;95,10;USD\n"
        b"02.01.2026;n/a;EUR\n"
        b"32.01.2026;101,00;EUR\n"
        b"30.12.2025;100,20;EUR\n"
        b"05.01.2026;100.10;EUR\n"
        b"06.01.2026;0;EUR\n"
        b"07.01.2026;101,00;EUR\n"
        b"Quelle: Boerse\n"
    )
    mapping = csvimport.guess(table)
    assert mapping.currency == 2
    parsed = csvimport.parse(table, mapping, today=TODAY)
    assert parsed.points == [(date(2025, 12, 30), 100.1)]
    assert parsed.refused == [
        (3, csvimport.NOT_EUR),
        (4, "value 'n/a' does not read as a number with a decimal comma"),
        (5, "date '32.01.2026' does not read as dmy"),
        (6, "2025-12-30 again"),
        (7, "value '100.10' does not read as a number with a decimal comma"),
        (8, "value 0 is not above zero"),
        (9, "2026-01-07 is in the future"),
        (10, "only 1 of 3 cells"),
    ]


def test_the_mapping_takes_columns_by_name() -> None:
    table = csvimport.sniff(GERMAN.encode())
    assert table.column(" schluss") == 4
    with pytest.raises(ValueError, match="no column 'Kurs', the table has Datum, "):
        table.column("Kurs")
    assert Mapping(0, 4, ",", "dmy").describe(table) == (
        "date Datum (dmy), value Schluss, decimal comma, currency none, read as EUR"
    )


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "no table found"),
        (b"Datum;Schluss\n", "no table found"),
        (b"just text\nwithout numbers\n", "no table found"),
        (b"Datum;Schluss\nheute;100\n", "no table found"),
        (b"\x81\x8d", "not a text table"),  # neither UTF-8 nor cp1252: a spreadsheet, a PDF
    ],
)
def test_a_file_without_dated_values_is_no_table(raw: bytes, message: str) -> None:
    with pytest.raises(RefusedError, match=message):
        csvimport.sniff(raw)


def test_a_file_without_a_header_keeps_its_first_row() -> None:
    table = csvimport.sniff(b"2025-01-02;100,50\n2025-01-03;101,00\n2025-01-06;102,25\n")
    assert [line for line, _ in table.rows] == [1, 2, 3]
    assert csvimport.guess(table).describe(table).startswith("date column 1")
