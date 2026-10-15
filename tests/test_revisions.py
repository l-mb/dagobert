"""Revision files: one revision per write, the inputs at each revision, recovery, the lock."""

from __future__ import annotations

import errno
import ntpath
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest
import yaml
from builders import HISTORY, NO_READ_ONLY_DIRECTORY, adopt, live, seen, state_at
from filelock import FileLock

from dagobert import (
    __version__,
    actuals,
    datadir,
    files,
    history,
    prices,
    rename,
    revisions,
    rollforward,
    scenariofiles,
    schema,
    store,
)
from dagobert.problems import InputError
from dagobert.references import Kind
from dagobert.revisions import Day, Entry
from dagobert.store import RowEdits

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from dagobert.schema import Inputs

OTHER = "name: other\nphases: [{from: 2026-01-01, phase: work}]\n"


def _tree(data: Path) -> dict[str, bytes]:
    """Every file of the data directory, revisions included."""
    return {p.relative_to(data).as_posix(): p.read_bytes() for p in data.rglob("*") if p.is_file()}


def _assets(data: Path, value: str) -> str:
    return (data / "assets.yaml").read_text().replace("value: 5000", f"value: {value}")


def test_the_inputs_at_each_revision_are_the_files_after_its_write(data: Path) -> None:
    (data / "history.csv").write_text(HISTORY)
    writes: list[tuple[str, Callable[[], dict[str, str | None]]]] = [
        ("Assets", lambda: {"assets.yaml": _assets(data, "6000")}),
        ("Explorer", lambda: {"scenarios/other.yaml": OTHER, "history.csv": HISTORY * 2}),
        ("Explorer", lambda: {"scenarios/other.yaml": None, "app.yaml": "scenarios: [base]\n"}),
    ]
    after = [live(data)]
    for source, edit in writes:
        assert revisions.write(data, source, edit)
        after.append(live(data))
        assert state_at(data) == after[-1]
    log = revisions.entries(data)
    assert [e.source for e in log] == ["baseline", "Assets", "Explorer", "Explorer"]
    assert log[-1].removed == ("scenarios/other.yaml",)
    assert [state_at(data, e.id) for e in log] == after


def test_a_write_whose_inputs_do_not_load_changes_nothing(data: Path) -> None:
    adopt(data)
    before = _tree(data)
    bad = _assets(data, "6000\n    bogus: 1")
    with pytest.raises(InputError, match=r"assets\[1\]\.bogus: unknown key"):
        revisions.write(data, "Assets", lambda: {"assets.yaml": bad, "history.csv": HISTORY})
    assert _tree(data) == before


class Crash(BaseException):
    """The process ends."""


def _torn_log(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    """The append of the log line, after the live files changed, writes a torn line and fails."""

    def torn(data_dir: Path, entry: Entry) -> None:
        with (data_dir / revisions.REVISIONS / revisions.LOG).open("a") as fh:
            fh.write(entry.line()[:10])
        raise error

    monkeypatch.setattr(revisions, "_log", torn)


def _crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """The process ends in the append of the log line: no handler undoes the write."""
    _torn_log(monkeypatch, Crash())
    monkeypatch.setattr(revisions, "_recover", lambda _: None)


@pytest.mark.parametrize("by_hand", [False, True])
def test_the_next_write_undoes_an_interrupted_one(
    data: Path, monkeypatch: pytest.MonkeyPatch, by_hand: bool
) -> None:
    """A file edited by hand after the crash keeps the edit, as an edit outside the app."""
    adopt(data)
    before, log = live(data), revisions.entries(data)
    _crash(monkeypatch)
    with pytest.raises(Crash):
        revisions.write(data, "Roll", lambda: {"assets.yaml": _assets(data, "1"), "app.yaml": ""})
    assert live(data) != before
    assert revisions.entries(data) == log  # the torn line does not count
    monkeypatch.undo()
    hand = {"assets.yaml": before["assets.yaml"].replace("5000", "7000")} if by_hand else {}
    for path, text in hand.items():
        (data / path).write_text(text)
    revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})
    assert live(data) == before | hand | {"actuals.csv": "month,category,amount\n"}
    assert live(data) == state_at(data)
    sources = ["baseline", *(["outside the app"] if by_hand else []), "Spend"]
    assert [e.source for e in revisions.entries(data)] == sources
    folders = {p.name for p in (data / revisions.REVISIONS).iterdir() if p.is_dir()}
    assert folders == {e.id for e in revisions.entries(data)}


def test_a_failed_append_to_the_log_undoes_the_write(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adopt(data)
    before = _tree(data)
    _torn_log(monkeypatch, OSError(errno.ENOSPC, "No space left on device"))
    with pytest.raises(OSError, match="No space"):
        revisions.write(data, "Roll", lambda: {"assets.yaml": _assets(data, "1"), "app.yaml": ""})
    assert _tree(data) == before


def _log_file(data: Path) -> Path:
    return data / revisions.REVISIONS / revisions.LOG


@pytest.mark.parametrize("lost", [True, False])
def test_a_lost_or_older_log_changes_no_input(data: Path, lost: bool) -> None:
    adopt(data)
    backup = _log_file(data).read_bytes()
    revisions.write(data, "Assets", lambda: {"assets.yaml": _assets(data, "6000")})
    revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})
    before = live(data)
    if lost:
        _log_file(data).unlink()
    else:
        _log_file(data).write_bytes(backup)
    with pytest.raises(InputError, match=r"^revisions/log\.csv: .*restore the log"):
        revisions.write(data, "Snapshot", lambda: {"history.csv": HISTORY})
    assert live(data) == before


def test_a_log_one_revision_behind_keeps_the_input(data: Path) -> None:
    """The revision that the log lacks committed: its file is an edit outside the app."""
    adopt(data)
    backup = _log_file(data).read_bytes()
    revisions.write(data, "Assets", lambda: {"assets.yaml": _assets(data, "6000")})
    before = live(data)
    _log_file(data).write_bytes(backup)
    revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})
    assert live(data) == before | {"actuals.csv": "month,category,amount\n"}
    sources = [e.source for e in revisions.entries(data)]
    assert sources == ["baseline", "outside the app", "Spend"]


def test_a_broken_log_line_names_its_line(data: Path) -> None:
    adopt(data)
    with _log_file(data).open("a") as fh:
        fh.write("garbage\n")
    with pytest.raises(InputError, match=r"^revisions/log\.csv:3: no revision: 1 columns, not 4$"):
        revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})


def test_a_missing_copy_is_copied_again(data: Path) -> None:
    baseline = adopt(data)
    assert baseline
    (data / revisions.REVISIONS / baseline.id / "assets.yaml").unlink()
    revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})
    assert live(data) == state_at(data)


def test_an_interrupted_adopt_keeps_the_edit_outside_the_app(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adopt(data)
    edited = _assets(data, "7000")
    (data / "assets.yaml").write_text(edited)
    _crash(monkeypatch)
    with pytest.raises(Crash):
        adopt(data)
    monkeypatch.undo()
    adopted = adopt(data)
    assert adopted
    assert adopted.files == ("assets.yaml",)
    assert (data / "assets.yaml").read_text() == edited


def test_writes_of_two_threads_take_turns(data: Path) -> None:
    (data / "actuals.csv").write_text("0\n")

    def add() -> None:
        for _ in range(50):
            revisions.write(
                data,
                "Spend",
                lambda: {"actuals.csv": f"{int((data / 'actuals.csv').read_text()) + 1}\n"},
            )

    with ThreadPoolExecutor(2) as pool:
        for future in [pool.submit(add) for _ in range(2)]:
            future.result()
    assert (data / "actuals.csv").read_text() == "100\n"
    assert len(revisions.entries(data)) == 101


def test_a_write_without_a_change_writes_nothing(data: Path) -> None:
    adopt(data)
    before = _tree(data)
    same = (data / "assets.yaml").read_bytes().decode()  # the line ends of the file
    assert revisions.write(data, "Assets", lambda: {"assets.yaml": same, "app.yaml": None}) is None
    assert _tree(data) == before


def test_a_write_inside_a_write_raises(data: Path) -> None:
    def nested() -> dict[str, str | None]:
        adopt(data)
        return {}

    with pytest.raises(RuntimeError, match="inside another one"):
        revisions.write(data, "outer", nested)


def test_a_write_waits_for_the_lock_of_another_one(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(revisions, "LOCK_WAIT", 0.2)
    (data / revisions.REVISIONS).mkdir()
    with (
        FileLock(data / revisions.REVISIONS / revisions.LOCK),
        pytest.raises(revisions.BusyError, match="Another save is running"),
    ):
        revisions.write(data, "Spend", lambda: {"actuals.csv": "x\n"})
    assert not (data / "actuals.csv").exists()


@NO_READ_ONLY_DIRECTORY
def test_a_read_only_directory_takes_no_write(data: Path) -> None:
    data.chmod(0o555)
    try:
        with pytest.raises(revisions.ReadOnlyError, match="the data directory is read-only"):
            revisions.write(data, "Spend", lambda: {"actuals.csv": "x\n"})
    finally:
        data.chmod(0o755)
    assert not (data / revisions.REVISIONS).exists()


def test_a_write_on_windows_syncs_no_directory(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows opens no directory, so a sync of one there would fail every write."""
    monkeypatch.setattr(files, "WINDOWS", True)
    real = os.open

    def opened(path: str, flags: int, *args: int) -> int:
        if os.path.isdir(path):
            raise PermissionError(errno.EACCES, "Permission denied", path)
        return real(path, flags, *args)

    monkeypatch.setattr(os, "open", opened)
    entry = revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})
    assert entry
    assert entry.files == ("actuals.csv",)
    assert not ntpath.isreserved(entry.id)  # the id names a directory there too: no colon


@pytest.mark.parametrize("windows", [True, False])
def test_a_replace_that_a_reader_blocks_tries_again_on_windows_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, windows: bool
) -> None:
    """Windows refuses to replace a file that another process holds open, such as a reader of
    the inputs or a virus scanner, until it lets go. Elsewhere a refusal is final."""
    monkeypatch.setattr(files, "WINDOWS", windows)
    monkeypatch.setattr(files, "REPLACE_WAITS", (0.0, 0.0, 0.0))
    refusals = [PermissionError(errno.EACCES, "Access is denied")] * 2
    replace = os.replace

    def held(source: str, target: Path) -> None:
        if refusals:
            raise refusals.pop()
        replace(source, target)

    monkeypatch.setattr(os, "replace", held)
    with nullcontext() if windows else pytest.raises(PermissionError):
        files.atomic_write(tmp_path / "a.yaml", "a: 1\n")
    assert [p.name for p in tmp_path.iterdir()] == (["a.yaml"] if windows else [])


@pytest.mark.skipif(files.WINDOWS, reason="Windows keeps no permission bits")
def test_a_write_keeps_the_mode_of_the_file(tmp_path: Path) -> None:
    """A backup job or a host user beside the container still reads the inputs after a save."""
    old, new = tmp_path / "old.yaml", tmp_path / "new.yaml"
    old.write_text("a: 1\n")
    old.chmod(0o640)
    for path in (old, new):
        files.atomic_write(path, "a: 2\n")
    assert [stat.S_IMODE(p.stat().st_mode) for p in (old, new)] == [0o640, files.NEW_MODE]


CSV_INPUTS: dict[str, Callable[[Path], object]] = {
    "history.csv": history.read_history,
    "actuals.csv": actuals.read,
    "prices/XAU.csv": lambda data: prices.read_prices(data / "prices" / "XAU.csv"),
}


@pytest.mark.parametrize(
    ("file", "text", "problem"),
    [
        ("history.csv", "\ufeffdate,asset,value\n2026-01-01,giro,1000\n", None),  # Excel
        ("history.csv", "date,asset,value\n2026-01-01,giro,1.234,56\n", ":2: 4 cells, the header"),
        ("actuals.csv", "month,category,amount\n2026-01,food,-5\n2026-02,food,\n", ":3: could not"),
        ("prices/XAU.csv", "day,close\n2026-01-01,2500\n", ":1: no column date"),
        ("history.csv", "date,asset,value\n2026-01-01,giro,nan\n", ":2: 'nan' is no finite"),
        ("prices/XAU.csv", "date,close\n2026-01-01,2500\n2026-02-01,inf\n", ":3: 'inf' is no"),
    ],
    ids=["bom", "cells", "number", "header", "nan", "inf"],
)
def test_a_csv_input_names_the_line_that_does_not_read(
    data: Path, file: str, text: str, problem: str | None
) -> None:
    """A hand edit of a CSV input fails a page or a save that reads it, with the line."""
    (data / file).parent.mkdir(exist_ok=True)
    (data / file).write_text(text, encoding="utf-8")
    if problem is None:
        assert CSV_INPUTS[file](data) == [(date(2026, 1, 1), "giro", 1000.0)]
        return
    with pytest.raises(InputError, match=f"{file}{problem}"):
        CSV_INPUTS[file](data)


ISIN = "IE00B4L5Y983"
DEPOT = "  - {id: fonds, kind: equity, value: 1, trades: [{date: 2020-01-01, kind: buy, "
DEPOT += f"security: {ISIN}, units: 2, amount: 10}}]}}\n"
SOURCE = "Page: action"


def _named(inputs: Inputs) -> set[str]:
    for row in inputs.yaml("assets.yaml")["assets"]:
        row["name"] = row["id"].title()
    return {"assets.yaml"}


WRITERS: dict[str, Callable[[Path], object]] = {
    "RowFile.apply": lambda data: store.assets_file(data).apply(
        RowEdits({0: {"value": 1500, "asof": date(2026, 9, 1)}}),
        source=SOURCE,
        observed=[(date(2026, 9, 1), "giro", 1500.0)],
    ),
    "act": lambda data: scenariofiles.act(
        data,
        lambda d: scenariofiles.created(
            d, "whatif", "whatif", "base", {"inflation": {"mean": 0.04}}
        ),
        source=SOURCE,
    ),
    "act (rename)": lambda data: scenariofiles.act(
        data, lambda d: scenariofiles.renamed(d, "base", "plan"), source=SOURCE
    ),
    "save_default_scenarios": lambda data: scenariofiles.save_default_scenarios(
        data, ["base"], source=SOURCE
    ),
    "add": lambda data: actuals.add(data, date(2026, 9, 1), "wohnen", 20.5, source=SOURCE),
    "save_draft": lambda data: actuals.save_draft(
        data, date(2026, 9, 1), {"wohnen": (None, -500.0)}, source=SOURCE
    ),
    "prices.save": lambda data: prices.save(data, ISIN, [(date(2026, 9, 17), 7.0)], source=SOURCE),
    "rollforward.apply": lambda data: rollforward.apply(data, date(2026, 3, 1), source=SOURCE),
    "rename.apply": lambda data: rename.apply(
        data, rename.preview(data, rename.Rename(Kind.ASSET, "giro", "konto")), source=SOURCE
    ),
    "datadir.open": datadir.open,
}


@pytest.mark.parametrize("writer", WRITERS)
def test_every_writer_records_one_revision(
    data: Path, monkeypatch: pytest.MonkeyPatch, writer: str
) -> None:
    """A writer that skips the log leaves a change for `adopt`, and a selector of the inputs at a
    time misses it."""
    with (data / "assets.yaml").open("a") as fh:
        fh.write(DEPOT)
    monkeypatch.setattr(schema, "STEPS", (_named,))
    (data / schema.MANIFEST).write_text("schema: 1\napp: 0.0.1\n")
    adopt(data)  # the baseline
    if writer != "datadir.open":
        datadir.open(data)
    before = revisions.entries(data)
    WRITERS[writer](data)
    assert adopt(data) is None
    [entry] = revisions.entries(data)[len(before) :]
    migrated = f"migrate 1 → 2 (Dagobert {__version__})"
    assert entry.source == (migrated if writer == "datadir.open" else SOURCE)
    assert entry.files
    assert live(data) == state_at(data)


def test_a_write_takes_only_inputs(data: Path) -> None:
    with pytest.raises(ValueError, match=r"not an input of the data directory: out/index\.html"):
        revisions.write(data, "report", lambda: {"out/index.html": ""})


@pytest.mark.parametrize(
    ("path", "tracked", "plan"),
    [
        ("manifest.yaml", True, True),
        ("assets.yaml", True, True),
        ("scenarios/base.yaml", True, True),
        ("app.yaml", True, False),
        ("history.csv", True, False),
        ("prices/IE00B4L5Y983.csv", True, False),
        ("scenarios/.base.yaml.x1y2.tmp", False, False),
        ("scenarios/.base.yaml", False, False),
        ("scenarios/old/base.yaml", False, False),
        ("scenarios/a;b.yaml", False, False),
        ("assets.yaml~", False, False),
        ("series/cpi_de.csv", False, False),
        ("revisions/log.csv", False, False),
    ],
)
def test_tracked_paths(path: str, tracked: bool, plan: bool) -> None:
    assert (revisions.is_tracked(path), revisions.is_plan(path)) == (tracked, plan)


def test_adopt_records_edits_outside_the_app_once(data: Path) -> None:
    (data / "history.csv").write_text(HISTORY)
    baseline = adopt(data)
    assert baseline
    assert (baseline.source, set(baseline.files)) == ("baseline", set(live(data)))
    (data / "assets.yaml").write_text(_assets(data, "7000"))
    os.utime(data / "assets.yaml", (0, 0))  # an old time stamp still comes after the baseline
    (data / "history.csv").unlink()
    revisions.write(data, "Spend", lambda: {"actuals.csv": "month,category,amount\n"})
    assert adopt(data) is None
    log = revisions.entries(data)
    assert [(e.source, e.files, e.removed) for e in log[1:]] == [
        ("outside the app", ("assets.yaml",), ("history.csv",)),
        ("Spend", ("actuals.csv",), ()),
    ]
    assert log[0].id < log[1].id < log[2].id
    assert revisions.head(data) == log[-1].id
    assert live(data) == state_at(data)


def test_days_group_the_revisions_of_a_plan_by_local_day() -> None:
    def entry(utc: str, source: str, *paths: str) -> Entry:
        return Entry(f"{utc}.000000Z", paths, (), source)

    log = [
        entry("20261010T120000", "Explorer", "scenarios/b.yaml"),
        entry("20261011T143000", "Snapshot", "history.csv"),
        entry("20261011T153000", "Cashflows", "cashflows.yaml"),  # 00:30 in Tokyo
        entry("20261012T080000", "Cashflows", "cashflows.yaml"),
        entry("20261012T090000", "Snapshot", "assets.yaml", "history.csv"),
    ]
    tokyo = ZoneInfo("Asia/Tokyo")
    found = revisions.days(log, selected=revisions.is_plan, tz=tokyo)
    assert found == [
        Day(date(2026, 10, 12), log[4].id, (("Cashflows", 2), ("Snapshot", 1))),
        Day(date(2026, 10, 10), log[0].id, (("Explorer", 1),)),
    ]
    assert found[0].said(str) == "2026-10-12 · Cashflows ×2, Snapshot"
    assert [d.day for d in revisions.days(log, selected=revisions.is_plan, tz=UTC)] == [
        date(2026, 10, 12),
        date(2026, 10, 11),
        date(2026, 10, 10),
    ]
    assert revisions.before(log, datetime(2026, 10, 12, tzinfo=tokyo)) == log[1].id
    assert revisions.before(log, log[0].time) is None
    with pytest.raises(ValueError, match="without a time zone"):
        revisions.before(log, datetime(2026, 10, 12))


def test_a_renamed_file_keeps_its_history() -> None:
    """A rename that the source names (`renaming`) leads back to the old path; a source that only
    looks like one, without the removal, does not."""

    def entry(day: int, files: tuple[str, ...], removed: tuple[str, ...], source: str) -> Entry:
        return Entry(f"202610{day:02}T120000.000000Z", files, removed, source)

    a, b, c = (f"scenarios/{s}.yaml" for s in "abc")
    log = [
        entry(1, (a,), (), "baseline"),
        entry(2, (b,), (a,), f"Scenarios: {revisions.renaming(a, b)}"),
        entry(3, (b,), (), "Scenarios"),
        entry(4, (c,), (b,), f"Scenarios: {revisions.renaming(b, c)}"),
        entry(5, (a,), (), "Explorer"),  # a new file of the old name
        entry(6, ("assets.yaml",), (), f"Assets: {revisions.renaming(a, c)}"),  # no rename
    ]
    name = revisions.named(log, c)
    assert [name(e.id) for e in log] == [a, b, b, c, c, c]
    assert log[1].renamed == (a, b)
    assert log[5].renamed is None
    assert [revisions.named(log, a)(e.id) for e in log] == [None, None, None, None, a, a]


def test_a_write_is_refused_only_for_the_problems_that_it_adds(data: Path) -> None:
    """Two files that do not load: a save elsewhere, the fix of one, the rename and the removal
    of the other go through; a write that breaks a third names only its problem."""
    scenarios = data / "scenarios"
    (scenarios / "a.yaml").write_text("name: a\nphases: [{from: 2026-01-01, phase: nap}]\n")
    (scenarios / "b.yaml").write_text("name: b\nextends: gone\n")
    store.write(data, [store.Edit("scenarios/base.yaml", {("note",): "fine"})], source="t")
    store.write(
        data, [store.Edit("scenarios/a.yaml", {("phases", 0, "phase"): "work"})], source="t"
    )
    scenariofiles.act(
        data,
        lambda d: scenariofiles.renamed(d, "b", "b2"),
        source=f"t: {revisions.renaming('scenarios/b.yaml', 'scenarios/b2.yaml')}",
    )
    scenariofiles.act(data, lambda d: scenariofiles.removed(d, "b2"), source="t")
    with pytest.raises(InputError) as err:
        store.write(
            data, [store.Edit("scenarios/base.yaml", {("extends",): "nowhere"})], source="t"
        )
    assert [(p.file, p.path) for p in err.value.problems] == [("scenarios/base.yaml", "extends")]
    assert "nowhere" not in (scenarios / "base.yaml").read_text()


def test_materialize_migrates_the_plan_at_a_revision(
    data: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    (data / "history.csv").write_text(HISTORY)
    first = adopt(data)
    assert first
    revisions.write(data, "Assets", lambda: {"assets.yaml": _assets(data, "6000")})
    monkeypatch.setattr(schema, "STEPS", (_named,))
    dest = tmp_path_factory.mktemp("at")
    revisions.materialize(data, first.id, dest)
    assets = yaml.safe_load((dest / "assets.yaml").read_text())["assets"]
    assert [(a["name"], a["value"]) for a in assets] == [("Giro", 1000), ("Depot", 5000)]
    assert yaml.safe_load((dest / schema.MANIFEST).read_text())["schema"] == 2
    assert not (dest / "history.csv").exists()  # not part of the plan


def test_a_save_refuses_when_the_part_it_read_changed(data: Path) -> None:
    def row(asset: int) -> object:
        return yaml.safe_load((data / "assets.yaml").read_text())["assets"][asset]

    adopt(data)
    giro = seen(data, "assets.yaml", row(0))
    revisions.write(data, "Assets", lambda: {"assets.yaml": _assets(data, "6000")})

    def save() -> dict[str, str | None]:
        revisions.unchanged(data, giro, row(0))
        return {"history.csv": HISTORY}

    revisions.write(data, "Snapshot", save)  # another row changed: no conflict
    edited = (data / "assets.yaml").read_text().replace("value: 1000", "value: 900")
    revisions.write(data, "Phone", lambda: {"assets.yaml": edited})
    with pytest.raises(revisions.ConflictError, match=r"^assets\.yaml changed") as caught:
        revisions.write(data, "Snapshot", save)
    assert [e.source for e in caught.value.since] == ["Assets", "Phone"]
