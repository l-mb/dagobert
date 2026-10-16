"""Revision files: a write of the inputs copies each file that it changes into
`revisions/<id>/` and adds a line to `revisions/log.csv`, under a lock of the data directory. The
inputs at a time are the newest copy of each file at or before it."""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import json
import os
import re
import shutil
import threading
from collections import Counter
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from filelock import FileLock, Timeout

from dagobert import files, schema
from dagobert.loader import problems
from dagobert.problems import InputError, Problem

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence
    from datetime import tzinfo
    from pathlib import Path

type Texts = Mapping[str, str | None]  # tracked path -> new text, None removes the file

REVISIONS: Final = "revisions"
LOG: Final = "log.csv"
LOCK: Final = ".lock"
ENTRY: Final = ".entry"  # the log line of a write while it replaces live files
FIELDS: Final = ("time", "files", "removed", "source")
LOCK_WAIT = 10.0  # seconds until `BusyError`
PLAN: Final = (
    schema.MANIFEST,
    "assumptions.yaml",
    "assets.yaml",
    "cashflows.yaml",
    "scenarios/*.yaml",
)
OUTSIDE: Final = "outside the app"
BASELINE: Final = "baseline"
_FORMAT: Final = "%Y%m%dT%H%M%S.%fZ"  # ISO basic, UTC: no colons, sorts in time order
_ID = re.compile(r"\d{8}T\d{6}\.\d{6}Z")
_RENAME = re.compile(r"rename (.+) → (.+)$")  # the end of the source of a rename, see `renaming`
_held = threading.local()


def _matches(path: str, patterns: Iterable[str]) -> bool:
    return any(PurePosixPath(path).full_match(pattern) for pattern in patterns)


def is_tracked(path: str) -> bool:
    """Whether `path` (relative to the data directory, with `/`) takes part in revisions: an
    input of `schema.INPUTS`, no dotfile, no `;` (the log joins paths with it)."""
    return (
        ";" not in path
        and not PurePosixPath(path).name.startswith(".")
        and _matches(path, schema.INPUTS)
    )


def is_plan(path: str) -> bool:
    """Whether `path` changes a run: the manifest, the plan files and the scenarios."""
    return is_tracked(path) and _matches(path, PLAN)


def _id(when: datetime) -> str:
    return when.astimezone(UTC).strftime(_FORMAT)


def time_of(stamp: str) -> datetime:
    """The time of the revision `stamp`, its id."""
    return datetime.strptime(stamp, _FORMAT).replace(tzinfo=UTC)


def _paths(joined: str) -> tuple[str, ...]:
    return tuple(joined.split(";")) if joined else ()


@dataclass(frozen=True)
class Entry:
    """A revision: one line of the log."""

    id: str
    files: tuple[str, ...]
    removed: tuple[str, ...]
    source: str  # the page or the command that wrote it

    @property
    def time(self) -> datetime:
        return time_of(self.id)

    @property
    def paths(self) -> tuple[str, ...]:
        return self.files + self.removed

    @property
    def renamed(self) -> tuple[str, str] | None:
        """The old and the new path of a file that this revision renamed: its source ends with
        `renaming`, it removes the old path and writes the new one."""
        found = _RENAME.search(self.source)
        if found and found[1] in self.removed and found[2] in self.files:
            return found[1], found[2]
        return None

    def line(self) -> str:
        buf = io.StringIO()
        row = (self.id, ";".join(self.files), ";".join(self.removed), self.source)
        csv.writer(buf, lineterminator="\n").writerow(row)
        return buf.getvalue()

    @classmethod
    def of(cls, row: Sequence[str]) -> Entry:
        if len(row) != len(FIELDS):
            msg = f"{len(row)} columns, not {len(FIELDS)}"
            raise ValueError(msg)
        stamp, joined, removed, source = row
        if not _ID.fullmatch(stamp):
            msg = f"no revision id: {stamp!r}"
            raise ValueError(msg)
        return cls(stamp, _paths(joined), _paths(removed), source)


def _read(text: str, file: str, *, header: bool) -> tuple[Entry, ...]:
    """The entries of a log text. A line that is no entry raises with its file and line."""
    rows = csv.reader(io.StringIO(text))
    try:
        if header:
            next(rows, None)
        return tuple(Entry.of(row) for row in rows)
    except (ValueError, csv.Error) as err:
        raise InputError([Problem(file, rows.line_num, "", f"no revision: {err}")]) from err


def entries(data_dir: Path) -> tuple[Entry, ...]:
    """The revisions, oldest first. A last line without its line end is a torn append: it does
    not count."""
    log = data_dir / REVISIONS / LOG
    try:
        stat = log.stat()
    except FileNotFoundError:
        return ()
    return _parsed(log, stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=8)
def _parsed(log: Path, size: int, _mtime: int) -> tuple[Entry, ...]:
    data = log.read_bytes()[:size]
    return _read(data[: data.rfind(b"\n") + 1].decode(), f"{REVISIONS}/{LOG}", header=True)


def head(data_dir: Path) -> str | None:
    found = entries(data_dir)
    return found[-1].id if found else None


def last_change(data_dir: Path, path: str) -> str | None:
    """The id of the newest revision that writes or removes `path`."""
    return next((e.id for e in reversed(entries(data_dir)) if path in e.paths), None)


def changed_after(data_dir: Path, at: str, patterns: Iterable[str]) -> bool:
    """Whether a revision after `at` writes or removes a path of `patterns`."""
    later = (e for e in entries(data_dir) if e.id > at)
    return any(_matches(path, patterns) for entry in later for path in entry.paths)


def state(data_dir: Path, at: str | None = None) -> dict[str, Path]:
    """The inputs at the revision `at` (the head without), as the copy of each tracked path: its
    newest at or before `at`. A path that its newest entry removes is absent."""
    newest: dict[str, str] = {}  # path -> the id of its copy: every page run reads this
    for entry in entries(data_dir):
        if at is not None and entry.id > at:
            break
        newest |= dict.fromkeys(entry.files, entry.id)
        for path in entry.removed:
            newest.pop(path, None)
    return {path: data_dir / REVISIONS / stamp / path for path, stamp in newest.items()}


def materialize(
    data_dir: Path, at: str, dest: Path, *, only: Callable[[str], bool] = is_plan
) -> None:
    """Copy the inputs at `at` that `only` takes into `dest`, migrated to the current schema: a
    data directory for the loader."""
    dest.mkdir(parents=True, exist_ok=True)
    for path, copy in state(data_dir, at).items():
        if only(path):
            (dest / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(copy, dest / path)
    schema.migrate_dir(dest)


class BusyError(TimeoutError):
    """Another write held the lock of the data directory for `LOCK_WAIT`."""


class ReadOnlyError(PermissionError):
    """The data directory takes no write: a read-only mount or file mode."""


@contextmanager
def lock(data_dir: Path) -> Iterator[None]:
    """Hold the lock of the data directory: one writer at a time, threads of one process and
    other processes alike (`filelock`: `flock` on Unix, `LockFileEx` on Windows). Each call takes
    a lock of its own, so threads take turns. A thread that holds it already would wait for
    itself, so it raises. A read-only directory raises `ReadOnlyError`: a page shows it as the
    reason of a save that failed."""
    if getattr(_held, "on", False):
        msg = "a write of the inputs inside another one"
        raise RuntimeError(msg)
    if not os.access(data_dir, os.W_OK):
        msg = "the data directory is read-only"
        raise ReadOnlyError(msg)
    (data_dir / REVISIONS).mkdir(exist_ok=True)
    try:
        held = FileLock(data_dir / REVISIONS / LOCK, timeout=LOCK_WAIT).acquire()
    except Timeout as err:
        msg = "Another save is running. Save again."
        raise BusyError(msg) from err
    with held:
        _held.on = True
        try:
            yield
        finally:
            _held.on = False


def write(
    data_dir: Path,
    source: str,
    edit: Callable[[], Texts],
    *,
    validate: bool = True,
) -> Entry | None:
    """Run `edit` under the lock of the data directory and record what it changes as one
    revision. `edit` reads the files that it changes, so it sees the newest content, and it can
    raise `ConflictError`. A text equal to the current file does not count: None when nothing
    changes. Edits outside the app get a revision of their own first (`_adopt`). If a YAML input
    changes and `validate` is set, every scenario loads after the write: if one fails, the files
    and the log stay as before and the error goes up."""
    return _write(data_dir, source, lambda: (edit(), None), validate=validate)[0]


def write_returning[T](
    data_dir: Path,
    source: str,
    edit: Callable[[], tuple[Texts, T]],
    *,
    validate: bool = True,
) -> T:
    """`write` of the texts of `edit`, and what `edit` found with them under the lock: the roll
    that a roll forward made, the prices that a save replaced."""
    return _write(data_dir, source, edit, validate=validate)[1]


def _write[T](
    data_dir: Path, source: str, edit: Callable[[], tuple[Texts, T]], *, validate: bool
) -> tuple[Entry | None, T]:
    with lock(data_dir):
        _recover(data_dir)
        _adopt(data_dir)
        texts, found = edit()
        changes = _changes(data_dir, texts)
        if not changes:
            return None, found
        stamp = _next(head(data_dir), datetime.now(UTC))
        return _save(data_dir, stamp, source, changes, live=True, validate=validate), found


def _adopt(data_dir: Path) -> None:
    """Record the tracked files that differ from the head (changed, new or removed outside the
    app) as one revision. Without a log, every tracked file, as the baseline."""
    at_head = state(data_dir)
    live = {path for path in schema.Tree(data_dir) if is_tracked(path)}
    changes: dict[str, bytes | None] = {
        path: (data_dir / path).read_bytes()
        for path in sorted(live)
        if _differs(data_dir / path, at_head.get(path))
    } | {path: None for path in at_head.keys() - live}
    if not changes:
        return
    now = datetime.now(UTC)
    newest = max(
        (_mtime(data_dir / path) for path, data in changes.items() if data is not None),
        default=now,
    )
    last = head(data_dir)
    stamp = _next(last, min(newest, now))
    _save(data_dir, stamp, OUTSIDE if last else BASELINE, changes, live=False, validate=False)


def _differs(live: Path, copy: Path | None) -> bool:
    """Whether the live file differs from its copy. A missing copy differs: `_adopt` copies the
    file again."""
    return (
        copy is None
        or not copy.is_file()
        or live.stat().st_size != copy.stat().st_size
        or live.read_bytes() != copy.read_bytes()
    )


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(0, UTC) + timedelta(microseconds=path.stat().st_mtime_ns // 1000)


def _next(last: str | None, when: datetime) -> str:
    """The id of `when`, at least one microsecond after `last`: ids sort in time order."""
    if last is not None and when <= time_of(last):
        when = time_of(last) + timedelta(microseconds=1)
    return _id(when)


def _encoded(texts: Texts) -> dict[str, bytes | None]:
    if wrong := [path for path in texts if not is_tracked(path)]:
        msg = f"not an input of the data directory: {', '.join(wrong)}"
        raise ValueError(msg)
    return {path: None if text is None else text.encode() for path, text in texts.items()}


def _changes(data_dir: Path, texts: Texts) -> dict[str, bytes | None]:
    """The new content of each path that `texts` changes, None for a removal."""
    return {
        path: data
        for path, data in _encoded(texts).items()
        if data != ((data_dir / path).read_bytes() if (data_dir / path).is_file() else None)
    }


def _save(
    data_dir: Path,
    stamp: str,
    source: str,
    changes: Mapping[str, bytes | None],
    *,
    live: bool,
    validate: bool,
) -> Entry:
    """Write the revision directory, then with `live` the live files, and append the log line,
    the commit point. A failure undoes what the log does not hold (`_recover`). Only a write of
    the live files puts `.entry` first, and removes it after the commit: the recovery brings
    back the live files of an orphan with `.entry`, and must neither lose a revision that
    records the live files as they are (`_adopt`) nor one that a log restored from a
    backup lacks."""
    if "\n" in source or "\r" in source:
        msg = f"a source takes one line: {source!r}"
        raise ValueError(msg)
    entry = Entry(
        stamp,
        tuple(sorted(path for path, data in changes.items() if data is not None)),
        tuple(sorted(path for path, data in changes.items() if data is None)),
        source,
    )
    log = data_dir / REVISIONS / LOG
    # the header goes in before the first revision: a log that goes missing later is lost
    if not log.is_file() or not log.stat().st_size:
        files.atomic_write(log, ",".join(FIELDS) + "\n")
        files.fsync_dir(log.parent)
    folder = data_dir / REVISIONS / stamp
    folder.mkdir()
    try:
        if live:
            files.atomic_write(folder / ENTRY, entry.line())
        for path, data in changes.items():
            if data is not None:
                _copy(folder / path, data)
        _sync({folder, folder.parent} | {(folder / path).parent for path in entry.files})
        if live:
            checked = validate and any(path.endswith(".yaml") for path in changes)
            known = _known(problems(data_dir), entry.renamed) if checked else set()
            _replace(data_dir, changes)
            if checked and (new := [p for p in problems(data_dir) if _key(p) not in known]):
                raise InputError(new)
        _log(data_dir, entry)
    except BaseException:
        _recover(data_dir)
        raise
    (folder / ENTRY).unlink(missing_ok=True)
    return entry


def renaming(old: str, new: str) -> str:
    """The end of the source of a write that renames the file `old` to `new`, which the log keeps
    (`Entry.renamed`): the history of the file follows it (`named`)."""
    return f"rename {old} → {new}"


def _key(problem: Problem) -> tuple[str, str, str]:
    """A problem without its line, which an edit above it moves."""
    return problem.file, problem.path, problem.message


def _known(found: Iterable[Problem], renamed: tuple[str, str] | None) -> set[tuple[str, str, str]]:
    """The problems of the inputs before a write, by `_key`, those of a renamed file under its new
    path too: a write is refused only for a problem that it adds, so a file that was broken
    already does not block the fix or the removal of another."""
    keys = {_key(p) for p in found}
    if renamed:
        keys |= {(renamed[1], path, message) for file, path, message in keys if file == renamed[0]}
    return keys


def _copy(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def _sync(directories: Iterable[Path]) -> None:
    for directory in directories:
        files.fsync_dir(directory)


def _replace(data_dir: Path, changes: Mapping[str, bytes | None]) -> None:
    """Bring the live files to `changes`: replace each one, remove it for None. A directory that
    the first file of its kind makes (`prices/`) is synced in its parent too."""
    made: set[Path] = set()
    for path, data in changes.items():
        live = data_dir / path
        if data is None:
            live.unlink(missing_ok=True)
        else:
            made.update(
                d.parent for d in live.parents if d.is_relative_to(data_dir) and not d.is_dir()
            )
            live.parent.mkdir(parents=True, exist_ok=True)
            files.atomic_write(live, data)
    parents = {(data_dir / path).parent for path in changes}
    _sync(made | {d for d in parents if d.is_dir()})


def _log(data_dir: Path, entry: Entry) -> None:
    """Append the line of `entry` to the log in one write: the commit point of a revision."""
    # O_BINARY: Windows opens a descriptor in text mode, which writes `\r\n`
    fd = os.open(data_dir / REVISIONS / LOG, os.O_WRONLY | os.O_APPEND | getattr(os, "O_BINARY", 0))
    try:
        os.write(fd, entry.line().encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def _recover(data_dir: Path) -> None:
    """Cut a torn last line off the log, then undo the revision directory without a log line (an
    orphan) that an interrupted write leaves. The lock lets one write run at a time, so there is
    at most one, newer than the head, and the log exists before it. Anything else is a lost or
    older log: that raises, and the live files stay as they are."""
    log = data_dir / REVISIONS / LOG
    data = log.read_bytes() if log.exists() else b""
    complete = data[: data.rfind(b"\n") + 1]
    if complete != data:
        os.truncate(log, len(complete))
    known = entries(data_dir)
    ids = {entry.id for entry in known}
    with os.scandir(data_dir / REVISIONS) as found:  # every page run lists them: no stat each
        unknown = sorted(
            e.name for e in found if e.name not in ids and _ID.fullmatch(e.name) and e.is_dir()
        )
    if not unknown:
        return
    if not complete or len(unknown) > 1 or (known and unknown[0] < known[-1].id):
        what = "missing" if not complete else f"without the revisions {', '.join(unknown)}"
        msg = f"{what}: restore the log, or move {REVISIONS}/ away to start a new history"
        raise InputError([Problem(f"{REVISIONS}/{LOG}", None, "", msg)])
    _undo(data_dir, data_dir / REVISIONS / unknown[0])


def _undo(data_dir: Path, folder: Path) -> None:
    """Bring each live file that the revision in `folder` wrote back to the head, then remove the
    folder. A live file that differs from the revision (not written yet, or edited since) stays,
    for `_adopt`. Without `.entry` the revision changed no live file."""
    if (folder / ENTRY).exists():
        (entry,) = _read(
            (folder / ENTRY).read_text(encoding="utf-8"),
            f"{REVISIONS}/{folder.name}/{ENTRY}",
            header=False,
        )
        at_head = state(data_dir)
        _replace(
            data_dir,
            {
                path: at_head[path].read_bytes() if path in at_head else None
                for path in entry.paths
                if _bytes(data_dir / path) == _bytes(folder / path)
            },
        )
    shutil.rmtree(folder)


def _bytes(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


@dataclass(frozen=True)
class Day:
    """The revisions of one local day that change a selected file."""

    day: date
    last: str  # the id of the last of them
    sources: tuple[tuple[str, int], ...]  # each source with its count, in order of time

    def said(self, source: Callable[[str], str]) -> str:
        """The label with each source as `source` says it: a page in words (`ui.page_said`)."""
        counts = (source(s) if n == 1 else f"{source(s)} ×{n}" for s, n in self.sources)
        return f"{self.day.isoformat()} · {', '.join(counts)}"


def days(log: Sequence[Entry], *, selected: Callable[[str], bool], tz: tzinfo) -> list[Day]:
    """One `Day` per local day of `tz` with a revision that writes or removes a `selected` path,
    newest first."""
    groups: dict[date, list[Entry]] = {}
    for entry in log:
        if any(selected(path) for path in entry.paths):
            groups.setdefault(entry.time.astimezone(tz).date(), []).append(entry)
    return [
        Day(day, group[-1].id, tuple(Counter(e.source for e in group).items()))
        for day, group in reversed(groups.items())
    ]


def before(log: Sequence[Entry], when: datetime) -> str | None:
    """The id of the last revision before `when`, a time with its time zone."""
    if when.tzinfo is None:
        msg = f"a time without a time zone: {when}"
        raise ValueError(msg)
    i = bisect.bisect_left(log, _id(when), key=lambda entry: entry.id)
    return log[i - 1].id if i else None


def named(log: Sequence[Entry], path: str) -> Callable[[str], str | None]:
    """The path that the file `path` of the head had at a revision, following its renames
    (`Entry.renamed`) back from the head; None when the inputs then do not hold it: its newest
    entry at or before that revision does not write it, as in `state`, or a later rename moved
    the file of that path away, so the file of the head came after it."""
    renames = [(entry.id, *found) for entry in reversed(log) if (found := entry.renamed)]

    def name(at: str) -> str | None:
        then = path
        for _, old, new in (r for r in renames if r[0] > at):  # newest first
            if old == then:
                return None
            if new == then:
                then = old
        marks = [entry for entry in log if then in entry.paths]
        i = bisect.bisect_right(marks, at, key=lambda entry: entry.id)
        return then if i and then in marks[i - 1].files else None

    return name


@dataclass(frozen=True)
class Seen:
    """What a page read of one file: the revision of its last change then, and a digest of the
    part that the page shows."""

    file: str
    revision: str | None
    digest: str


def digest(part: object) -> str:
    """The digest of a part in a `Seen`. A page that takes the revision (`last_change`) before it
    reads the part builds its `Seen` with it: a write between the two then counts as a change."""
    return hashlib.sha256(json.dumps(part, sort_keys=True, default=str).encode()).hexdigest()


class ConflictError(Exception):
    """The part of a file that a page read changed since: the file and the revisions since."""

    def __init__(self, file: str, since: Sequence[Entry]) -> None:
        self.file = file
        self.since = tuple(since)
        changes = "; ".join(f"{e.time:%Y-%m-%d %H:%M} UTC by {e.source}" for e in since)
        super().__init__(f"{file} changed since it was read: {changes}")


def unchanged(data_dir: Path, seen: Seen, part: object) -> None:
    """Raise `ConflictError` when `part`, the current content of what `seen` read, differs from
    it. It runs inside the `edit` of a write, so it compares with the newest content under the
    lock. Without a revision of the file since, it does not compare."""
    if last_change(data_dir, seen.file) == seen.revision or digest(part) == seen.digest:
        return
    raise ConflictError(
        seen.file,
        [
            e
            for e in entries(data_dir)
            if (seen.revision is None or e.id > seen.revision) and seen.file in e.paths
        ],
    )
