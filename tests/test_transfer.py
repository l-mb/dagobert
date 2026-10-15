"""Export and import: the zip, its checks, the comparison against the base of the export, and
the page."""

from __future__ import annotations

import io
import shutil
import stat
import struct
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from builders import FIXTURES, HISTORY, adopt, live, state_at
from streamlit.testing.v1 import AppTest

from dagobert import datadir, revisions, schema, transfer
from dagobert.files import WINDOWS
from dagobert.problems import NOT_UTF8, InputError
from dagobert.schema import SchemaError
from dagobert.transfer import ArchiveError, Choice, Side
from dagobert.ui import transfer as page

if TYPE_CHECKING:
    from collections.abc import Iterable


def _export(data: Path, dest: Path, *, history: bool = False) -> Path:
    taken = transfer.export(data)
    (path := dest / taken.name).write_bytes(taken.zip(history=history))
    return path


def _write(data: Path, path: str, text: str | None) -> None:
    assert revisions.write(data, "test", lambda: {path: text})


def _value(data: Path, value: int) -> str:
    return (data / "assets.yaml").read_text().replace("value: 5000", f"value: {value}")


def _zip(path: Path, entries: Iterable[tuple[str | zipfile.ZipInfo, str | bytes]]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return path


@pytest.fixture
def away(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A directory outside the data directory, for zips and other data directories."""
    return tmp_path_factory.mktemp("away")


def _local(data: Path, away: Path, path: str, text: str | None) -> Path:
    """An export of `data`, unpacked as for the app, `path` changed there, and exported again."""
    local = transfer.unpacked(_export(data, away))
    _write(local, path, text)
    (back := away / "back").mkdir()
    return _export(local, back)


def test_an_export_into_its_unchanged_instance_changes_nothing(data: Path, away: Path) -> None:
    preview = transfer.preview(data, _export(data, away, history=True))
    log = revisions.entries(data)
    assert preview.known
    assert preview.changes == ()
    assert preview.notes == [
        "The revisions of the zip are ignored: this data directory has its own."
    ]
    assert transfer.apply(data, preview) is None
    assert revisions.entries(data) == log


def test_a_change_of_another_file_on_each_side_keeps_both(data: Path, away: Path) -> None:
    """A local round trip keeps a record that the instance made meanwhile."""
    cashflows = (data / "cashflows.yaml").read_text().replace("-500", "-600")
    back = _local(data, away, "cashflows.yaml", cashflows)
    _write(data, "history.csv", HISTORY)
    preview = transfer.preview(data, back)
    assert not preview.undecided
    assert {c.path: (c.here, c.there, c.default) for c in preview.changes} == {
        "cashflows.yaml": ("", "changed", Choice.TAKE),
        "history.csv": ("added", "", Choice.KEEP),
    }
    entry = transfer.apply(data, preview)
    assert entry is not None
    assert (entry.source, entry.files) == (f"import {back.name}", ("cashflows.yaml",))
    assert (data / "cashflows.yaml").read_text() == cashflows
    assert (data / "history.csv").read_text() == HISTORY
    assert "base" not in (data / schema.MANIFEST).read_text()
    assert adopt(data) is None


@pytest.mark.parametrize(("choice", "value"), [(Choice.TAKE, 7000), (Choice.KEEP, 6000)])
def test_a_file_changed_on_both_sides_waits_for_a_choice(
    data: Path, away: Path, choice: Choice, value: int
) -> None:
    back = _local(data, away, "assets.yaml", _value(data, 7000))
    _write(data, "assets.yaml", _value(data, 6000))
    preview = transfer.preview(data, back)
    assert [(c.path, c.here, c.there, c.default) for c in preview.undecided] == [
        ("assets.yaml", "changed", "changed", None)
    ]
    # each side against the base, then what a take does here
    assert [(s.before, s.after) for s in preview.undecided[0].sides] == [
        ("base", "here"),
        ("base", "zip"),
        ("here", "zip"),
    ]
    log = revisions.entries(data)
    with pytest.raises(ValueError, match=r"keep or take: assets\.yaml"):
        transfer.apply(data, preview)
    assert revisions.entries(data) == log
    transfer.apply(data, preview, {"assets.yaml": choice})
    assert f"value: {value}\n" in (data / "assets.yaml").read_text()


def test_an_export_of_another_history_asks_for_every_file(data: Path, away: Path) -> None:
    """An instance made by an import has none of the revisions of the source: its later exports
    name an unknown base, and the import takes or removes nothing on its own."""
    target = away / "target"
    transfer.apply(target, transfer.preview(target, _export(data, away)))
    _write(data, "cashflows.yaml", (data / "cashflows.yaml").read_text().replace("-500", "-600"))
    _write(target, "history.csv", HISTORY)
    (later := away / "later").mkdir()
    preview = transfer.preview(target, _export(data, later))
    assert not preview.known
    assert preview.notes[0].startswith("The export names no revision of this data directory")
    assert {c.path: (c.there, c.default, c.action(Choice.TAKE)) for c in preview.undecided} == {
        "cashflows.yaml": ("changed", None, "replace"),
        "history.csv": ("removed", None, "remove"),
    }
    with pytest.raises(ValueError, match=r"keep or take: cashflows\.yaml, history\.csv"):
        transfer.apply(target, preview)
    transfer.apply(target, preview, {"cashflows.yaml": Choice.TAKE, "history.csv": Choice.KEEP})
    assert live(target) == live(data) | {"history.csv": HISTORY}


def test_a_file_that_the_import_removes_waits_for_a_take(data: Path, away: Path) -> None:
    _write(data, "history.csv", HISTORY)
    preview = transfer.preview(data, _local(data, away, "history.csv", None))
    assert [(c.path, c.here, c.there, c.default) for c in preview.undecided] == [
        ("history.csv", "", "removed", None)
    ]
    with pytest.raises(ValueError, match=r"keep or take: history\.csv"):
        transfer.apply(data, preview)
    transfer.apply(data, preview, {"history.csv": Choice.TAKE})
    assert not (data / "history.csv").exists()


def test_a_migration_since_the_base_is_no_change(away: Path) -> None:
    """An export of schema 1 from before the instance migrated: only its own edit counts."""
    instance = shutil.copytree(FIXTURES / "1", away / "instance")
    (instance / schema.MANIFEST).write_text("schema: 1\napp: 0.0.1\n")
    baseline = adopt(instance)
    assert baseline is not None
    texts = live(instance)
    edited = texts["cashflows.yaml"] + "# edited\n"
    manifest = f"schema: 1\napp: 0.0.1\nbase: {baseline.id}\n"
    old = _zip(
        away / "old.zip", (texts | {"cashflows.yaml": edited, schema.MANIFEST: manifest}).items()
    )
    preview = transfer.preview(instance, old)  # migrates the instance first
    assert "security: " in (instance / "assets.yaml").read_text()
    assert [(c.path, c.here, c.there) for c in preview.changes] == [
        ("cashflows.yaml", "", "changed")
    ]
    assert preview.notes == [
        "The zip has schema 1 (Dagobert 0.0.1): the import migrates it to schema "
        f"{schema.current()}, "
        "which changes assets.yaml, assumptions.yaml, scenarios/base.yaml."
    ]


def test_an_import_refuses_after_a_change_since_its_preview(data: Path, away: Path) -> None:
    cashflows = (data / "cashflows.yaml").read_text()
    preview = transfer.preview(data, _local(data, away, "cashflows.yaml", cashflows + "# x\n"))
    (data / "history.csv").write_text(HISTORY)  # outside the app
    with pytest.raises(transfer.StaleError, match="preview the import again"):
        transfer.apply(data, preview)
    assert (data / "cashflows.yaml").read_text() == cashflows


def test_a_local_file_that_is_not_utf8_ends_the_preview_as_an_input_error(
    data: Path, away: Path
) -> None:
    (data / "history.csv").write_text(HISTORY)
    zipped = _export(data, away, history=True)
    (data / "history.csv").write_bytes(HISTORY.replace("giro", "Gebühr").encode("cp1252"))
    with pytest.raises(InputError, match=NOT_UTF8):
        transfer.preview(data, zipped)


@pytest.mark.parametrize("history", [True, False])
def test_an_import_into_an_empty_directory_takes_the_inputs(
    data: Path, away: Path, history: bool
) -> None:
    """With the revisions, the inputs of every revision move along."""
    _write(data, "assets.yaml", _value(data, 6000))
    _write(data, "history.csv", HISTORY)
    zipped = _export(data, away, history=history)
    log = revisions.entries(data)
    target = away / "new"
    preview = transfer.preview(target, zipped)
    assert preview.empty
    assert {(c.default, c.action(Choice.TAKE)) for c in preview.changes} == {(Choice.TAKE, "add")}
    transfer.apply(target, preview)
    assert live(target) == live(data)
    if history:
        assert revisions.entries(target) == log
        assert all(state_at(target, e.id) == state_at(data, e.id) for e in log)
    else:
        assert [e.source for e in revisions.entries(target)] == [f"import {preview.archive.name}"]
    assert adopt(target) is None


def test_the_series_and_the_report_stay_out_of_an_export(data: Path) -> None:
    for path in ["series/msci-world.csv", "out/index.html", "notes.txt", "prices/README.md"]:
        (data / path).parent.mkdir(exist_ok=True)
        (data / path).write_text("x\n")
    taken = transfer.export(data)
    names = zipfile.ZipFile(io.BytesIO(taken.zip(history=True))).namelist()
    assert sorted(names) == sorted(
        [
            *(p for p in schema.Tree(data) if revisions.is_tracked(p)),
            "revisions/log.csv",
            *(f"revisions/{e.id}/{p}" for e in revisions.entries(data) for p in e.files),
        ]
    )


def _symlink() -> zipfile.ZipInfo:
    info = zipfile.ZipInfo("scenarios/link.yaml")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


@pytest.mark.parametrize(
    ("name", "content", "error", "message"),
    [
        ("../assumptions.yaml", "", ArchiveError, "a path outside the data directory"),
        ("/scenarios/a.yaml", "", ArchiveError, "a path outside the data directory"),
        pytest.param(
            "scenarios\\a.yaml",
            "",
            ArchiveError,
            "a path outside the data directory",
            marks=pytest.mark.skipif(WINDOWS, reason="zipfile reads a backslash as a separator"),
        ),
        ("C:/scenarios/a.yaml", "", ArchiveError, "a path outside the data directory"),
        ("scenarios/./a.yaml", "", ArchiveError, "a path outside the data directory"),
        (_symlink(), "/etc/passwd", ArchiveError, "a symbolic link"),
        ("notes.txt", "", ArchiveError, "no file of a data directory"),
        ("series/msci-world.csv", "", ArchiveError, "no file of a data directory"),
        ("revisions/.lock", "", ArchiveError, "no file of a data directory"),
        ("history.csv", b"\xff", ArchiveError, "history.csv: no UTF-8 text"),
        (schema.MANIFEST, "schema: 99\napp: 9.9.9\n", SchemaError, "Update the app"),
        ("scenarios/b.yaml", "name: b\nbogus: 1\n", InputError, "scenarios/b.yaml:2: bogus"),
        ("revisions/20261012T000000.000000Z/assets.yaml", "", ArchiveError, "no revision names"),
    ],
)
def test_a_zip_is_refused(
    data: Path,
    away: Path,
    name: str | zipfile.ZipInfo,
    content: str | bytes,
    error: type[Exception],
    message: str,
) -> None:
    """A valid export with the entry `name`."""
    entries = [(path, text) for path, text in live(data).items() if path != name]
    with pytest.raises(error, match=message):
        transfer.read(_zip(away / "x.zip", [*entries, (name, content)]))


def test_a_damaged_zip_is_refused(data: Path, away: Path) -> None:
    zipped = _export(data, away)
    with zipfile.ZipFile(zipped) as zf:
        info = zf.getinfo("assets.yaml")
    raw = bytearray(zipped.read_bytes())
    name, extra = struct.unpack("<HH", raw[info.header_offset + 26 : info.header_offset + 30])
    start = info.header_offset + 30 + name + extra
    raw[start : start + info.compress_size] = b"\xff" * info.compress_size  # no deflate block
    zipped.write_bytes(raw)
    with pytest.raises(ArchiveError, match="damaged, or no zip: Error -3"):
        transfer.read(zipped)


def test_a_zip_larger_than_the_limit_is_refused(
    data: Path, away: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zipped = _export(data, away)
    assert [transfer.megabytes(n) for n in (2**20, 2**20 + 1)] == [1, 2]  # never 64 over 64
    monkeypatch.setattr(transfer, "LIMIT", 100)
    with pytest.raises(ArchiveError, match="more than an import takes"):
        transfer.export(data).zip()
    with pytest.raises(ArchiveError, match="unpacked, more than"):
        transfer.read(zipped)


def test_an_unpacked_zip_without_manifest_is_schema_1(away: Path) -> None:
    old = _zip(away / "old.zip", live(FIXTURES / "1").items())
    local = transfer.unpacked(old)
    datadir.open(local)
    assert "security: " in (local / "assets.yaml").read_text()


def test_an_unpacked_zip_without_manifest_and_with_history_migrates_as_a_revision(
    away: Path,
) -> None:
    old = shutil.copytree(FIXTURES / "1", away / "old")
    adopt(old, validate=False)  # the baseline
    files = [
        (p.relative_to(old).as_posix(), p.read_bytes())
        for p in old.rglob("*")
        if p.is_file() and p.name != ".lock"
    ]
    local = transfer.unpacked(_zip(away / "hist.zip", files))
    datadir.open(local)
    assert revisions.entries(local)[-1].source.startswith("migrate 1")
    assert "security: " in (local / "assets.yaml").read_text()


def test_an_unpacked_export_serves_again_only_for_its_base(data: Path, away: Path) -> None:
    zipped = _export(data, away)
    local = transfer.unpacked(zipped)
    _write(local, "history.csv", HISTORY)
    assert transfer.unpacked(zipped) == local
    assert (local / "history.csv").read_text() == HISTORY  # the edits since stay
    _write(data, "history.csv", HISTORY)
    other = _export(data, away)
    shutil.move(other, zipped)  # another export under the same name
    with pytest.raises(ArchiveError, match="is no unpack of"):
        transfer.unpacked(zipped)


def test_a_temporary_unpack_migrates_and_goes(away: Path) -> None:
    old = _zip(away / "old.zip", live(FIXTURES / "1").items())
    with transfer.temporary(old) as inputs:
        assert "security: " in (inputs / "assets.yaml").read_text()
        datadir.open(inputs)  # current: nothing to migrate
    assert not inputs.exists()
    assert sorted(p.name for p in away.iterdir()) == ["old.zip"]


def test_the_table_and_the_count_follow_the_choices(data: Path, away: Path) -> None:
    back = _local(data, away, "assets.yaml", _value(data, 7000))
    _write(data, "assets.yaml", _value(data, 6000))
    _write(data, "history.csv", HISTORY)
    preview = transfer.preview(data, back)
    assert page.rows(preview, {}) == [
        {"file": "assets.yaml", "here": "changed", "zip": "changed", "action": page.OPEN},
        {"file": "history.csv", "here": "added", "zip": "", "action": "keep"},
    ]
    assert [r["action"] for r in page.rows(preview, {"assets.yaml": Choice.TAKE})] == [
        "replace",
        "keep",
    ]
    assert page.effect(preview, {"assets.yaml": Choice.TAKE}) == "1 replaced, 1 kept, 3 unchanged"
    assert [page.why(c) for c in preview.undecided] == [
        "changed here and changed in the import since the export"
    ]


ROWS = "assets:\n  - {id: giro, kind: cash, value: 1000}\n  - {id: depot, kind: cash, value: 5}\n"
DEPOT = "assets:\n  - id: depot\n    kind: equity\n    value: 5000\n    trades:\n"
BUY = "      - {{date: 2026-01-02, kind: buy, security: IE00B4L5Y983, units: 10, amount: {}}}\n"


@pytest.mark.parametrize(
    ("path", "old", "new", "found", "removed"),
    [
        (
            "assets.yaml",
            ROWS,
            "# a comment\nassets:\n  - {id: giro, kind: cash, value: 1200.5}\n",
            ["**giro value** 1.000,00 € → 1.200,50 €"],
            ["depot"],
        ),
        (
            "assets.yaml",
            f"{DEPOT}{BUY.format(2850)}{BUY.format(290).replace('01-02', '02-02')}",
            f"{DEPOT}{BUY.format(2950)}",
            ["**depot trades 2026-01-02 IE00B4L5Y983 amount** 2.850,00 € → 2.950,00 €"],
            ["depot trades 2026-02-02 IE00B4L5Y983"],
        ),
        (
            "history.csv",
            "date,asset,value\n2026-01-01,giro,1000.00\n2026-02-01,giro,1100.00\n",
            "date,asset,value\n2026-03-01,giro,900\n2026-01-01,giro,1200.00\n",
            [
                "**2026-01-01 giro** 1.000,00 € → 1.200,00 €",
                "**2026-03-01 giro** empty → 900,00 €",
            ],
            ["2026-02-01 giro"],
        ),
        (
            "prices/IE00B4L5Y983.csv",
            "date,close\n2026-01-02,98.765\n",
            "date,close\n2026-01-02,98.7651\n",
            ["**2026-01-02** 98.765 → 98.7651"],
            [],
        ),
    ],
)
def test_a_difference_lists_rows_by_their_key(
    path: str, old: str, new: str, found: list[str], removed: list[str]
) -> None:
    """In the format of the save guard: a new order is no change, money shows with cents."""
    difference = page.difference(path, Side("here", "zip", old, new))
    assert ([c.text for c in difference.found], difference.removed) == (found, removed)
    assert not difference.diff


@pytest.mark.parametrize(
    ("path", "old", "new"),
    [
        ("scenarios/a.yaml", "name: a\n", "name: b\n"),
        ("assets.yaml", ROWS, ROWS + "# only a comment\n"),  # no row differs
        ("assets.yaml", ROWS, "assets: [\n"),  # does not parse
        ("actuals.csv", "month,category,amount\n", "month,amount\n2026-01,-5\n"),  # columns
    ],
)
def test_a_difference_without_rows_shows_the_lines(path: str, old: str, new: str) -> None:
    difference = page.difference(path, Side("here", "zip", old, new))
    assert (difference.found, difference.removed) == ([], [])
    assert difference.diff.startswith(f"--- here/{path}\n+++ zip/{path}\n")


PAGE = """
from pathlib import Path
from dagobert.ui import transfer
transfer.page(Path({data!r}))
"""


@pytest.mark.parametrize("phone", [False, True])
def test_the_page_imports_after_a_choice_and_asks_again_after_a_change(
    data: Path, away: Path, phone: bool
) -> None:
    back = _local(data, away, "assets.yaml", _value(data, 7000))
    _write(data, "assets.yaml", _value(data, 6000))
    at = AppTest.from_string(PAGE.format(data=str(data)), default_timeout=30)
    at.query_params["mobile"] = str(int(phone))
    at.run()
    assert [b.label for b in at.download_button] == ["Download the export"]
    at.file_uploader[0].upload(back.name, back.read_bytes(), "application/zip").run()
    assert not at.exception and not at.error

    def importable() -> bool:
        return not next(b for b in at.button if b.label.startswith("Import")).disabled

    assert not importable()
    assert at.table[0].value["action"].tolist() == [page.OPEN]
    at.segmented_control[0].set_value(Choice.TAKE).run()
    assert at.table[0].value["action"].tolist() == ["replace"]
    assert importable()
    _write(data, "history.csv", HISTORY)  # another device: a new preview, without the choice
    at.run()
    assert [w.value for w in at.warning] == [page.MOVED]
    assert at.segmented_control[0].value is None
    assert not importable()
    at.segmented_control[0].set_value(Choice.TAKE).run()
    next(b for b in at.button if b.label == "Import 1 file").click().run()
    assert not at.exception and not at.error
    assert "value: 7000\n" in (data / "assets.yaml").read_text()
    assert (data / "history.csv").read_text() == HISTORY
    assert revisions.entries(data)[-1].source == f"import {back.name}"
    assert [s.value for s in at.success] == [
        f"Imported {back.name} at {page.stamp(str(revisions.head(data)))}: 1 replaced, 1 kept, "
        "3 unchanged."
    ]
    assert not at.file_uploader[0].value  # a new upload field
    assert page.HELD not in at.session_state  # no archive held


def test_every_file_in_the_zip_takes_one_choice_and_a_removal_its_own(
    data: Path, away: Path
) -> None:
    """With an export of another history: one tap removes no file."""
    target = away / "target"
    transfer.apply(target, transfer.preview(target, _export(data, away)))
    _write(data, "cashflows.yaml", (data / "cashflows.yaml").read_text().replace("-500", "-600"))
    _write(data, "assets.yaml", _value(data, 6000))
    _write(target, "history.csv", HISTORY)
    (later := away / "later").mkdir()
    zipped = _export(data, later)
    at = AppTest.from_string(PAGE.format(data=str(target)), default_timeout=30).run()
    at.file_uploader[0].upload(zipped.name, zipped.read_bytes(), "application/zip").run()
    assert [w.value for w in at.warning] == [transfer.STRANGER]
    table = at.table[0].value
    assert table["here"].tolist() == ["differs", "differs", "only here"]
    assert table["zip"].tolist() == ["changed", "changed", "removed"]
    at.segmented_control[0].set_value(Choice.KEEP).run()  # every file in the zip
    assert [c.value for c in at.segmented_control] == [Choice.KEEP] * 3 + [None]
    at.segmented_control[3].set_value(Choice.TAKE).run()
    assert [w.value for w in at.warning][1:] == ["The import removes history.csv."]
    at.segmented_control[1].set_value(Choice.TAKE).run()
    assert at.segmented_control[0].value is None  # the files differ
    assert at.table[0].value["action"].tolist() == ["replace", "keep", "remove"]


def test_the_page_shows_why_a_zip_is_refused(data: Path, away: Path) -> None:
    at = AppTest.from_string(PAGE.format(data=str(data)), default_timeout=30).run()
    at.file_uploader[0].upload("x.zip", b"PK no zip", "application/zip").run()
    assert [e.value for e in at.error] == ["Not importable: x.zip"]
    assert at.code[0].value.startswith("x.zip: damaged, or no zip")
