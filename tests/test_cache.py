"""The results on disk (`cache`): what comes back, what names an entry, the bound, the folders that
take no write, the files that do not read, and the inputs that never see the cache."""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import zipfile
from dataclasses import fields, is_dataclass, replace
from datetime import date
from functools import partial
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
from builders import fixed_run
from numpy.typing import NDArray

from dagobert import cache, datadir, revisions, schema, transfer
from dagobert.goalseek import Dial, Found
from dagobert.runner import Options
from dagobert.sensitivity import Effect, Lever, Outcome, Sensitivity
from dagobert.ui import data_stamp, run_stamp

BASE = Path("scenarios/base.yaml")
LEVER = Lever("Inflation", ("inflation", "mean"), 0.02, 0.01, 0.03, "%.2f%%", 100, "1.00%")
OUTCOME = Outcome(0.04, (300_000.0, 120_000.0), (500_000.0, 410_000.0), (67, 90))
DIAL = Dial(
    "Stop working",
    ((("shift", "retire"), 1.0),),
    0.0,
    -24.0,
    36.0,
    1.0,
    whole=True,
    origin=date(2045, 1, 1),
    born=date(1977, 1, 1),
)
FOUND = Found(-6.0, 0.049, 27, rising=False, age=89)
SENSED = Sensitivity("base", date(2026, 1, 1), OUTCOME, (Effect(LEVER, OUTCOME, OUTCOME),))


def options(data: Path, paths: int = 20) -> Options:
    return Options(data, data, "montecarlo", paths, seed=42, mortality=True)


def name(data: Path, *parts: object, opts: Options | None = None) -> str:
    """The name of an entry of the run of `base` with `parts` on the inputs of `data`."""
    opts = opts or options(data)
    return cache.key(cache.RUN, opts, opts.data / BASE, *parts)


def same(a: object, b: object) -> bool:
    """Equal, an array also in its dtype, a dataclass and a container item by item."""
    if isinstance(a, np.ndarray):
        return isinstance(b, np.ndarray) and a.dtype == b.dtype and np.array_equal(a, b)
    if is_dataclass(a) and not isinstance(a, type):
        return type(a) is type(b) and all(
            same(getattr(a, f.name), getattr(b, f.name)) for f in fields(a)
        )
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        return type(a) is type(b) and len(a) == len(b) and all(map(same, a, b, strict=True))
    return type(a) is type(b) and a == b


def test_a_run_and_each_answer_come_back_from_the_disk_as_they_went(data: Path) -> None:
    """A run of many paths and the `fixed` run with its ledger: equal arrays of equal dtypes, the
    markers, months and dicts of tuples; the sensitivity, a seek, a seek of the Overview with its
    dial, and a plan without the dial (None, which a miss is not)."""
    run, single = options(data).run_one(data / BASE), fixed_run(data)
    assert run is not None and run.survival is not None and single.ledger is not None
    assert run.drivers and single.markers
    kept = [run, single, SENSED, FOUND, (FOUND, DIAL), None]
    for n, value in enumerate(kept):
        cache.write(data, name(data, n), value)
    assert cache.read(data, name(data, "none")) is cache.MISSING
    for n, value in enumerate(kept):
        assert same(cache.read(data, name(data, n)), value)


def test_the_name_follows_the_contents_and_the_engine_never_the_words_or_the_pages(
    data: Path, tmp_path: Path
) -> None:
    """The contents of what a run reads, not their times; not `app.yaml` nor the cache; a lever
    and a dial without their words; a data directory moved elsewhere; the engine code, the shipped
    data and the versions of the libraries, not the pages."""
    first = name(data, "{}", LEVER, DIAL)
    os.utime(data / "assumptions.yaml", (1e9, 1e9))
    (data / "app.yaml").write_text("scenarios: [base]\n")
    cache.write(data, first, FOUND)
    german = replace(LEVER, label="Inflation", format="%.2f %%", step="1,00 %")
    assert name(data, "{}", german, replace(DIAL, label="Arbeitsende")) == first
    assert name(data, "{}", replace(LEVER, value=0.03), DIAL) != first
    assert name(data, '{"a": 1}', LEVER, DIAL) != first
    assert name(data, "{}", LEVER, DIAL, opts=options(data, paths=21)) != first
    moved = shutil.copytree(data, tmp_path / "moved")
    assert name(moved, "{}", LEVER, DIAL, opts=options(moved)) == first
    before = first
    for changed in ("assumptions.yaml", "series/vpi.csv"):
        (moved / changed).parent.mkdir(exist_ok=True)
        with (moved / changed).open("a") as fh:
            fh.write("\n")
        now = name(moved, "{}", LEVER, DIAL, opts=options(moved))
        assert now != before
        before = now
    package = tmp_path / "package"
    for module in ("engine.py", "ui/page.py", "report/figure.py", "data/tax/2026.yaml"):
        (package / module).parent.mkdir(parents=True, exist_ok=True)
        (package / module).write_text("x = 1\n")
    code = cache.engine_code(package)
    for page in ("ui/page.py", "report/figure.py", "ui/new.py"):
        (package / page).write_text("x = 2\n")
        assert cache.engine_code(package) == code
    for engine in ("engine.py", "data/tax/2026.yaml"):
        (package / engine).write_text("x = 3\n")
        assert cache.engine_code(package) != code
        code = cache.engine_code(package)
    assert cache.engine_code(package, "numpy 2.5.0") != cache.engine_code(package, "numpy 2.5.1")
    assert f"numpy {np.__version__}" in cache.libraries()


def test_a_file_put_back_with_an_older_time_names_its_contents(data: Path) -> None:
    """`cp -p` of an older copy keeps the latest time and the count of the inputs; the name of an
    entry follows their contents, also in the same process, and so does `run_stamp`, the sum of
    their times."""
    path = data / "assumptions.yaml"
    os.utime(path, (1e9, 1e9))  # older than the other inputs
    stamp, first = run_stamp(data), name(data, "{}")
    path.write_text(path.read_text().replace("0.05", "0.06"))  # the same size
    os.utime(path, (1e9 - 60, 1e9 - 60))
    assert run_stamp(data) != stamp
    assert name(data, "{}") != first


@pytest.mark.parametrize("saved", [False, True])
def test_a_result_is_kept_under_the_inputs_that_it_read(data: Path, saved: bool) -> None:
    """A save while a run runs leaves its result without a name: an undo back to the inputs before
    would find it under theirs."""
    path, before = data / "assumptions.yaml", name(data, "{}")

    def make() -> str:
        if saved:
            path.write_text(path.read_text().replace("0.05", "0.06"))
        return "run"

    assert cache.kept(data, partial(name, data, "{}"), make) == "run"
    expected = cache.MISSING if saved else "run"
    assert cache.read(data, before) == cache.read(data, name(data, "{}")) == expected


def test_the_least_recently_used_entries_go_beyond_the_bound(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read makes an entry the newest; a write removes the oldest until all fit."""
    names = [name(data, n) for n in range(4)]
    for n, entry in enumerate(names[:3]):
        cache.write(data, entry, SENSED)
        os.utime(data / cache.CACHE / f"{entry}.npz", (1e9 + n, 1e9 + n))
    one = cache.size(data) // 3
    monkeypatch.setattr(cache, "BYTES", 3 * one)
    assert cache.read(data, names[0]) == SENSED
    cache.write(data, names[3], SENSED)
    assert [cache.read(data, entry) is cache.MISSING for entry in names] == [
        False,
        True,
        False,
        False,
    ]


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="a folder that refuses the owner"
)
def test_a_data_directory_that_takes_no_write_keeps_results_in_memory_only(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only data directory, and `dagobert app` with an export zip (`MEMORY_ENV`), write no
    cache and read none."""
    entry = name(data, "{}")
    cache.write(data, entry, FOUND)
    monkeypatch.setenv(cache.MEMORY_ENV, "memory")
    assert cache.folder(data) is None
    assert cache.read(data, entry) is cache.MISSING
    monkeypatch.delenv(cache.MEMORY_ENV)
    data.chmod(0o555)
    try:
        assert cache.folder(data) is None
        cache.write(data, name(data, "other"), FOUND)
    finally:
        data.chmod(0o755)
    assert cache.read(data, name(data, "other")) is cache.MISSING
    assert cache.read(data, entry) == FOUND


def _npz(**arrays: NDArray[Any]) -> bytes:
    buffer = io.BytesIO()
    np.savez(buffer, **cast("dict[str, Any]", arrays))  # with a pickle for an object array
    return buffer.getvalue()


def _meta(node: object) -> NDArray[np.uint8]:
    return np.frombuffer(json.dumps(node).encode(), np.uint8)


def _huge() -> bytes:
    """A file whose array claims 8 PiB, so numpy cannot allocate it."""
    header = io.BytesIO()
    np.lib.format.write_array_header_1_0(
        header, {"descr": "<f8", "fortran_order": False, "shape": (1 << 50,)}
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("meta.npy", header.getvalue())
    return buffer.getvalue()


@pytest.mark.parametrize(
    "content",
    [
        b"torn",
        _npz(meta=_meta({"array": "a0"}), a0=np.array([object()], dtype=object)),  # a pickle
        _npz(meta=_meta({"type": "Path", "fields": {}})),  # a type of no entry
        _npz(meta=_meta({"type": "Found", "fields": {"value": 1}})),  # fields that it lacks
        _npz(meta=np.frombuffer(b"[" * 100_000, np.uint8)),  # nested beyond the stack
        _huge(),
    ],
    ids=["torn", "pickle", "type", "fields", "nested", "huge"],
)
def test_a_file_that_does_not_read_is_a_miss_and_goes(data: Path, content: bytes) -> None:
    """A torn or foreign file, one with a pickle, which runs code as it loads, a JSON text nested
    too deep or an array too large to hold: a miss, never an error on a page."""
    entry = name(data, "{}")
    cache.write(data, entry, FOUND)
    path = data / cache.CACHE / f"{entry}.npz"
    path.write_bytes(content)
    assert cache.read(data, entry) is cache.MISSING
    assert not path.exists()
    with pytest.raises(ValueError, match="no name of an entry"):
        cache.read(data, "../assets")


def test_the_cache_is_no_input(data: Path, tmp_path: Path) -> None:
    """No revision, stamp, migration, export or import sees `.cache`: an export leaves it out,
    an import keeps the one here and refuses a zip that holds one. `clear` empties it."""
    datadir.open(data)
    stamps = data_stamp(data), run_stamp(data)
    cache.write(data, name(data, "{}"), FOUND)
    assert (data_stamp(data), run_stamp(data)) == stamps
    assert datadir.open(data) is None
    assert not any(".cache" in p for e in revisions.entries(data) for p in e.paths)
    assert not any(".cache" in p for p in schema.Tree(data))
    export = tmp_path / "export.zip"
    export.write_bytes(transfer.export(data).zip(history=True))
    with zipfile.ZipFile(export) as archive:
        assert not any(".cache" in n for n in archive.namelist())
        entries = {n: archive.read(n) for n in archive.namelist()}
    (other := tmp_path / "other").mkdir()
    cache.write(other, name(data, "here"), DIAL)
    transfer.apply(other, transfer.preview(other, export))
    assert cache.size(other) and (other / "assumptions.yaml").exists()
    smuggled = tmp_path / "smuggled.zip"
    with zipfile.ZipFile(smuggled, "w") as archive:
        for entry, content in entries.items():
            archive.writestr(entry, content)
        archive.writestr(f".cache/{name(data, '{}')}.npz", b"x")
    with pytest.raises(transfer.ArchiveError, match=r"\.cache"):
        transfer.read(smuggled)
    cache.clear(data)
    assert cache.size(data) == 0
