"""History file and observed totals."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from dagobert import revisions
from dagobert.history import (
    Observation,
    actual_totals,
    actual_values,
    appended,
    corrected,
    months,
    of_month,
    read_history,
    renamed,
    values_at,
)


def _append(data: Path, observed: list[Observation]) -> None:
    revisions.write(data, "test", lambda: appended(data, observed))


def test_history_appends(data: Path) -> None:
    assert appended(data, []) == {}
    _append(data, [(date(2026, 9, 1), "giro", 1500.5)])
    day = date(2026, 10, 1)
    _append(data, [(day, "giro", 1600), (day, "depot", 5100)])
    assert (data / "history.csv").read_text().splitlines() == [
        "date,asset,value",
        "2026-09-01,giro,1500.50",
        "2026-10-01,giro,1600.00",
        "2026-10-01,depot,5100.00",
    ]
    assert read_history(data)[-1] == (day, "depot", 5100.0)
    with (data / "history.csv").open("a") as fh:  # a hand edit without the last line end
        fh.write("2026-10-02,giro,1700")
    _append(data, [(day, "giro", 1800)])
    assert read_history(data)[-2:] == [(date(2026, 10, 2), "giro", 1700.0), (day, "giro", 1800.0)]


def test_a_rename_changes_the_asset_cell_only(data: Path) -> None:
    """Quotes and the other rows stay as written, also a row of an asset `flat2`; the line ends
    of an earlier append become LF."""
    text = 'date,asset,value\r\n2026-09-01,"flat",1.0\r\n2026-09-01,flat2,2\r\n2026-10-01,flat,3'
    (data / "history.csv").write_bytes(text.encode())
    assert renamed(data, "flat", "home") == {
        "history.csv": 'date,asset,value\n2026-09-01,"home",1.0\n2026-09-01,flat2,2\n'
        "2026-10-01,home,3"
    }
    assert renamed(data, "giro", "cash") == {}


def test_a_correction_changes_or_removes_rows_of_its_month_only(data: Path) -> None:
    """A row by its place among the rows of its month: a new value with cents, a removal; the
    other rows keep every character, quotes too, and the line ends become LF."""
    text = (
        'date,asset,value\r\n2026-09-01,giro,1.0\r\n2026-10-01,"flat",2\r\n'
        "2026-10-15,giro,3\r\n2026-10-20,depot,4"
    )
    (data / "history.csv").write_bytes(text.encode())
    october = date(2026, 10, 1)
    assert [o[1] for o in of_month(read_history(data), october)] == ["flat", "giro", "depot"]
    assert months(read_history(data)) == [october, date(2026, 9, 1)]
    assert corrected(data, october, {0: 2500.5, 2: None}) == {
        "history.csv": 'date,asset,value\n2026-09-01,giro,1.0\n2026-10-01,"flat",2500.50\n'
        "2026-10-15,giro,3\n"
    }
    assert corrected(data, october, {}) == {}


def test_a_correction_refuses_a_file_of_other_columns(data: Path) -> None:
    """A hand edit that added a column: the save says why instead of breaking."""
    (data / "history.csv").write_text("date,asset,value,note\n2026-10-01,giro,1.0,x\n")
    with pytest.raises(ValueError, match="other columns"):
        corrected(data, date(2026, 10, 1), {0: 2.0})


def test_an_append_writes_lf_also_over_crlf_rows(data: Path) -> None:
    """Every write leaves LF line ends (owner, 2026-10-13), also over the CRLF of earlier
    appends."""
    (data / "history.csv").write_bytes(b"date,asset,value\r\n2026-09-01,giro,1.0\r\n")
    text = appended(data, [(date(2026, 10, 1), "giro", 2.0)])["history.csv"]
    assert "\r" not in text
    assert text.endswith("2026-09-01,giro,1.0\n2026-10-01,giro,2.00\n")


@pytest.mark.parametrize(
    ("old", "new"),
    [("flat", 'Flat "A", 2nd'), ('Flat "A", 2nd', "flat"), ("a,b", "a,b,c")],
)
def test_a_rename_keeps_the_history_readable(data: Path, old: str, new: str) -> None:
    """An id may hold a comma or a quote: the cell is quoted as CSV needs it."""
    _append(data, [(date(2026, 9, 1), old, 1.0), (date(2026, 9, 1), "giro", 2.0)])
    revisions.write(data, "test", lambda: renamed(data, old, new))
    assert [asset for _, asset, _ in read_history(data)] == [new, "giro"]


def test_actual_totals_start_when_every_asset_is_known(data: Path) -> None:
    # conftest: giro 1000 and depot 5000 without asof, simulation start 2026-01
    assert actual_totals(data) == [(date(2026, 1, 1), 6000.0)]
    _append(data, [(date(2026, 3, 15), "giro", 1500.0), (date(2025, 6, 1), "depot", 4000.0)])
    # the months with a snapshot only: February would repeat January as if observed
    assert actual_totals(data) == [(date(2026, 1, 1), 6000.0), (date(2026, 3, 1), 6500.0)]
    assert actual_values(data)[-1] == (date(2026, 3, 1), {"giro": 1500.0, "depot": 5000.0})


def test_actual_totals_ignores_history_of_removed_assets(data: Path) -> None:
    # conftest: giro and depot only, simulation start 2026-01
    _append(data, [(date(2026, 2, 10), "sold_asset", 10_000.0)])
    assert actual_totals(data) == [(date(2026, 1, 1), 6000.0)]


def test_values_at_takes_the_last_observation_by_then() -> None:
    observed = [
        (date(2026, 1, 1), "giro", 1.0),
        (date(2026, 2, 1), "giro", 2.0),
        (date(2026, 3, 1), "depot", 5.0),
    ]
    assert values_at(observed, date(2026, 2, 15)) == {"giro": 2.0}
    assert values_at(observed, date(2025, 12, 31)) == {}


def test_no_asset_records_no_net_worth(data: Path) -> None:
    (data / "assets.yaml").write_text("assets: []\n")
    assert actual_totals(data) == []
