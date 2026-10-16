"""Observed asset values over time: `history.csv` plus the dated values in `assets.yaml`."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from dateutil.relativedelta import relativedelta

from dagobert.files import finite, read_csv
from dagobert.loader import load_assets, load_assumptions
from dagobert.model.assets import Asset, Loan, TermDeposit

FILE = "history.csv"
FIELDS = ("date", "asset", "value")
Observation = tuple[date, str, float]  # day, asset id, value (loans negative)


def appended(data_dir: Path, observed: Sequence[Observation]) -> dict[str, str]:
    """The text of `history.csv` with the observed asset values appended (long format, one row
    per asset), for the write of the caller, which records the new values with them. Nothing
    without observations."""
    if not observed:
        return {}
    path = data_dir / FILE
    before = _text(path)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if not before:
        writer.writerow(FIELDS)
    elif not before.endswith("\n"):  # a hand edit without the last line end
        writer.writerow([])
    writer.writerows((day.isoformat(), asset, f"{value:.2f}") for day, asset, value in observed)
    return {FILE: before + buf.getvalue()}


def renamed(data_dir: Path, old: str, new: str) -> dict[str, str]:
    """The text of `history.csv` with the rows of the asset `old` under `new`, every other
    character kept but the line ends, for the write of a rename. Nothing without such a row."""
    lines = _text(data_dir / FILE).splitlines(keepends=True)
    out = lines[:1] + [_renamed(line, old, new) for line in lines[1:]]
    return {FILE: "".join(out)} if out != lines else {}


def corrected(data_dir: Path, month: date, changes: Mapping[int, float | None]) -> dict[str, str]:
    """The text of `history.csv` with rows of `month` corrected, each by its place among the rows
    of the month in the file (`of_month`): a new value, None removes the row. Every other
    character stays but the line ends, for the write of the caller. Nothing without a change.
    ValueError where the file holds other columns than `FIELDS`, as a hand edit may leave it."""
    lines = _text(data_dir / FILE).splitlines(keepends=True)
    places = [i for i, line in enumerate(lines) if i and _month(line) == month]
    columns = [h.strip().lstrip("\ufeff") for h in next(csv.reader(lines[:1]), [])]
    if columns != list(FIELDS) or max(changes, default=-1) >= len(places):
        msg = f"{FILE} holds other columns than {', '.join(FIELDS)}: correct it by hand"
        raise ValueError(msg)
    out = list(lines)
    for place, value in changes.items():
        line = lines[places[place]]
        cut = line.rindex(",") + 1
        ending = line[len(line.rstrip("\n")) :]
        out[places[place]] = "" if value is None else f"{line[:cut]}{value:.2f}{ending}"
    return {FILE: "".join(out)} if out != lines else {}


def _month(line: str) -> date | None:
    """The month of a row of `history.csv`, None for a line that holds no row."""
    row = next(csv.reader([line]), [])
    try:
        return date.fromisoformat(row[0]).replace(day=1) if len(row) == len(FIELDS) else None
    except ValueError:
        return None


def months(observed: Sequence[Observation]) -> list[date]:
    """The months with a recorded value, as their first day, newest first."""
    return sorted({day.replace(day=1) for day, _, _ in observed}, reverse=True)


def of_month(observed: Sequence[Observation], month: date) -> list[Observation]:
    """The recorded values of `month`, in the order of the file: the places of `corrected`."""
    return [o for o in observed if o[0].replace(day=1) == month]


def _text(path: Path) -> str:
    """The text of `path` with LF line ends, as every write leaves it (owner, 2026-10-13):
    earlier appends wrote CRLF. Empty for a missing file."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n") if path.exists() else ""


def _renamed(line: str, old: str, new: str) -> str:
    """`line` with `new` in the asset cell of `old`, quoted as the cell was or as `new` needs
    (an id may hold `,` or `"`): the date and the value before and after it hold no comma."""
    row = next(csv.reader([line]), [])
    if len(row) != len(FIELDS) or row[1] != old:
        return line
    start, end = line.index(",") + 1, line.rindex(",")
    cell = io.StringIO()
    if line[start:end].startswith('"'):
        csv.writer(cell, lineterminator="", quoting=csv.QUOTE_ALL).writerow([new])
    else:
        csv.writer(cell, lineterminator="").writerow([new])
    return line[:start] + cell.getvalue() + line[end:]


def read_history(data_dir: Path) -> list[Observation]:
    return read_csv(
        data_dir / FILE,
        FILE,
        FIELDS,
        lambda r: (date.fromisoformat(r["date"]), r["asset"], finite(r["value"])),
    )


def worth(asset: Asset, day: date) -> float:
    if isinstance(asset, TermDeposit):
        return asset.value_at(day)
    return asset.balance if isinstance(asset, Loan) else asset.value


def observations(data_dir: Path, assets: list[Asset]) -> list[Observation]:
    """The observed values of `assets` by date: `history.csv` and the value in `assets.yaml`
    at `asof` (the simulation start without one)."""
    start = load_assumptions(data_dir).start
    ids = {a.id for a in assets}
    return sorted(
        [
            *((a.asof or start, a.id, worth(a, a.asof or start)) for a in assets),
            *(o for o in read_history(data_dir) if o[1] in ids),
        ],
        key=lambda o: o[0],
    )


def values_at(observed: list[Observation], day: date) -> dict[str, float]:
    """The last value of each asset observed on or before `day`. `observed` is sorted by date."""
    return {asset: value for when, asset, value in observed if when <= day}


def actual_totals(data_dir: Path) -> list[tuple[date, float]]:
    """Observed net worth at the end of each month with a snapshot, from the first month in
    which every asset is known.

    An asset counts from its first observation and keeps its last value until the next
    one. Before every asset has a value the sum would show entries as growth."""
    return [(month, sum(values.values())) for month, values in actual_values(data_dir)]


def actual_values(data_dir: Path) -> list[tuple[date, dict[str, float]]]:
    """Observed value per asset at the end of each month that holds an observation (a snapshot),
    from the first month in which every asset is known, see `actual_totals`. A month between two
    snapshots holds none: it would repeat the last values, as if observed (owner, 2026-10-13:
    people record rarely). Nothing without an asset."""
    assets = load_assets(data_dir)
    if not assets:
        return []
    observed = observations(data_dir, assets)
    first_seen: dict[str, date] = {}
    for day, asset, _ in observed:
        first_seen.setdefault(asset, day)
    first = max(first_seen[a.id] for a in assets).replace(day=1)
    months = sorted({day.replace(day=1) for day, _, _ in observed if day >= first})
    return [
        (month, values_at(observed, month + relativedelta(months=1, days=-1))) for month in months
    ]
