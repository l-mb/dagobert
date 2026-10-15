"""Export and import: a zip of the inputs of a data directory, whose manifest names the revision
that it was taken at (`base`), and its import, which compares each file with that base."""

from __future__ import annotations

import difflib
import io
import os
import re
import shutil
import stat
import tempfile
import zipfile
import zlib
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, Final

from dagobert import datadir, files, loader, revisions, schema
from dagobert.i18n import N_, _
from dagobert.problems import InputError, Problem, decoded
from dagobert.revisions import REVISIONS
from dagobert.schema import MANIFEST

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# bytes of an export unpacked, which the import refuses beyond: it holds the zip, its files and
# their text in memory. Real data takes well under 1 MB.
LIMIT: Final = 64 * 2**20
UPLOAD_MB: Final = LIMIT // 2**20  # `server.maxUploadSize` of the app: a zip is not larger
LOG: Final = f"{REVISIONS}/{revisions.LOG}"
_DRIVE = re.compile(r"[A-Za-z]:")
_STALE = "The data directory changed since the preview: preview the import again."
STRANGER: Final = N_(  # the note of an export whose base this data directory does not know
    "The export names no revision of this data directory: it comes from another instance or "
    "history. Keep or take each file that differs from the one here."
)


def megabytes(size: int) -> int:
    """Bytes in MB, rounded up: 64 MB and a byte are more than the limit, 65 MB."""
    return -(-size // 2**20)


class ArchiveError(ValueError):
    """A zip that the app does not take: unsafe, or no export of a data directory."""


class StaleError(Exception):
    """The data directory changed between the preview of an import and its write."""


@dataclass(frozen=True)
class Export:
    """The inputs of a data directory at one revision, for a zip."""

    at: str | None  # the revision; None in a read-only directory without one
    base: str | None  # of the manifest of an unpacked export, else `at`
    inputs: Mapping[str, Path]  # each input by its path, the manifest aside
    copies: Mapping[str, Path]  # each copy of the revisions up to `at` by its path in the zip
    log: str  # the log up to `at`

    @property
    def name(self) -> str:
        return f"dagobert-{self.at}.zip" if self.at else "dagobert.zip"

    def size(self, *, history: bool = False) -> int:
        """The bytes of the files of the zip, unpacked: of the inputs, with `history` of the
        revisions too."""
        members = {**self.inputs, **(self.copies if history else {})}
        return sum(path.stat().st_size for path in members.values())

    def check(self, *, history: bool = False) -> None:
        """Raise `ArchiveError` when an import would refuse the zip for its size."""
        if (size := self.size(history=history)) > LIMIT:
            msg = (
                f"the export holds {megabytes(size)} MB, more than an import takes "
                f"({UPLOAD_MB} MB)" + (": export it without revisions" if history else "")
            )
            raise ArchiveError(msg)

    def zip(self, *, history: bool = False) -> bytes:
        """The zip: the inputs at the root, so that it unpacks into a data directory, a manifest
        with the base, with `history` the revisions. Raises `ArchiveError` when an import would
        refuse it for its size (`check`)."""
        self.check(history=history)
        members = {**self.inputs, **(self.copies if history else {})}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST, schema.manifest_text(self.base))
            for path, source in members.items():
                zf.write(source, path)
            if history:
                zf.writestr(LOG, self.log)
        return buf.getvalue()


def export(data_dir: Path) -> Export:
    """The inputs of `data_dir` at its head, after a migration and the edits outside the app
    (`datadir.open`): the copies of a revision never change, so the files of a zip belong
    together. A read-only directory, which takes no revision, gives its files as they are."""
    datadir.open(data_dir)
    at = revisions.head(data_dir)
    found = (
        revisions.state(data_dir, at)
        if os.access(data_dir, os.W_OK)
        else {path: data_dir / path for path in schema.Tree(data_dir) if revisions.is_tracked(path)}
    )
    own = (
        schema.manifest({MANIFEST: found[MANIFEST].read_text(encoding="utf-8")})
        if MANIFEST in found
        else None
    )
    log = [e for e in revisions.entries(data_dir) if at and e.id <= at]
    return Export(
        at,
        own.base if own and own.base else at,
        {path: copy for path, copy in found.items() if path != MANIFEST},
        {f"{REVISIONS}/{e.id}/{p}": data_dir / REVISIONS / e.id / p for e in log for p in e.files},
        ",".join(revisions.FIELDS) + "\n" + "".join(e.line() for e in log),
    )


@dataclass(frozen=True)
class Archive:
    """The files of an export zip, checked."""

    name: str
    files: Mapping[str, bytes]  # every file as it is, by path: the inputs and `revisions/`
    inputs: Mapping[str, str]  # the inputs migrated to the current schema, the manifest too
    base: str | None
    written: schema.Manifest | None  # the manifest of the zip as it is; None: schema 1

    @property
    def history(self) -> bool:
        return LOG in self.files

    @property
    def migration(self) -> str | None:
        """The migration of an older schema in words (the language of the preview, English in
        the CLI), None for a zip of the current one."""
        version = self.written.version if self.written else 1
        if version == schema.current():
            return None
        changed = [
            path
            for path, text in self.inputs.items()
            if path != MANIFEST and self.files.get(path) != text.encode()
        ]
        if self.written and changed:
            said = _(
                "The zip has schema {version} (Dagobert {app}): the import migrates it to "
                "schema {now}, which changes {files}."
            )
        elif self.written:
            said = _(
                "The zip has schema {version} (Dagobert {app}): the import migrates it to "
                "schema {now}."
            )
        elif changed:
            said = _(
                "The zip has schema {version}: the import migrates it to schema {now}, which "
                "changes {files}."
            )
        else:
            said = _("The zip has schema {version}: the import migrates it to schema {now}.")
        return said.format(
            version=version,
            app=self.written.app if self.written else "",
            now=schema.current(),
            files=", ".join(changed),
        )


def read(source: Path | IO[bytes]) -> Archive:
    """The files of an export zip. It refuses a path outside the data directory (absolute, `..`,
    a backslash, a drive), a symbolic link, a file that no data directory holds, more than
    `LIMIT` unpacked, a damaged entry, revisions whose log does not match their copies
    (`ArchiveError`), a newer schema (`SchemaError`) and inputs that do not load after the
    migration (`InputError`)."""
    name = source.name if isinstance(source, Path) else Path(str(source.name)).name
    try:
        with zipfile.ZipFile(source) as zf:
            _check(zf.infolist())
            # zipfile stops at the declared size, so the sizes checked bound what it reads
            files = {i.filename: zf.read(i) for i in zf.infolist() if not i.is_dir()}
    except (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, EOFError) as err:
        msg = f"{name}: damaged, or no zip: {err}"
        raise ArchiveError(msg) from err
    texts = {path: _text(path, data) for path, data in files.items() if revisions.is_tracked(path)}
    if "assumptions.yaml" not in texts:
        msg = f"{name}: no assumptions.yaml, so no export of a data directory"
        raise ArchiveError(msg)
    inputs = texts | schema.migrate(texts)
    with tempfile.TemporaryDirectory(prefix="dagobert-") as tmp:
        _put(Path(tmp), {**inputs, **_history(files)})
        loader.check(Path(tmp))
        _check_log(Path(tmp), files)
    found = schema.manifest(inputs)
    return Archive(name, files, inputs, found.base if found else None, schema.manifest(texts))


def _check(infos: list[zipfile.ZipInfo]) -> None:
    """Refuse the zip before a byte of it unpacks, with one line per problem."""
    twice = [name for name, n in Counter(i.filename for i in infos).items() if n > 1]
    problems = [
        *(f"{i.filename}: {why}" for i in infos if (why := _refusal(i))),
        *(f"{name}: twice in the zip" for name in twice),
    ]
    if (size := sum(i.file_size for i in infos)) > LIMIT:
        problems.append(f"{megabytes(size)} MB unpacked, more than {UPLOAD_MB} MB")
    if problems:
        raise ArchiveError("\n".join(problems))


def _refusal(info: zipfile.ZipInfo) -> str | None:
    name, path = info.filename, PurePosixPath(info.filename)
    if (
        "\\" in name
        or _DRIVE.match(name)
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != name.removesuffix("/")
    ):
        return "a path outside the data directory"
    if stat.S_ISLNK(info.external_attr >> 16):
        return "a symbolic link"
    if not info.is_dir() and not _holds(name):
        return "no file of a data directory"
    return None


def _holds(path: str) -> bool:
    """Whether a data directory holds `path`: an input, the log or the copy of an input."""
    parts = path.split("/")
    return (
        revisions.is_tracked(path)
        or path == LOG
        or (parts[0] == REVISIONS and len(parts) > 2 and revisions.is_tracked("/".join(parts[2:])))
    )


def _history(files: Mapping[str, bytes]) -> dict[str, bytes]:
    return {path: data for path, data in files.items() if path.startswith(f"{REVISIONS}/")}


def _text(path: str, data: bytes) -> str:
    try:
        return data.decode()
    except UnicodeDecodeError as err:
        msg = f"{path}: no UTF-8 text"
        raise ArchiveError(msg) from err


def _check_log(root: Path, files: Mapping[str, bytes]) -> None:
    """The revisions of the zip unpacked in `root`: a log whose ids rise and name inputs, and
    each copy that it names, no other. A line that is no entry raises `InputError`."""
    log = revisions.entries(root)
    ids = [e.id for e in log]
    named = {f"{REVISIONS}/{e.id}/{p}" for e in log for p in e.files}
    copies = _history(files).keys() - {LOG}
    problems = [
        *([f"{LOG}: the revisions are not in order"] if ids != sorted(set(ids)) else []),
        *(f"{LOG}: {p}: no input" for e in log for p in e.paths if not revisions.is_tracked(p)),
        *(f"{p}: missing, its revision names it" for p in sorted(named - copies)),
        *(f"{p}: no revision names it" for p in sorted(copies - named)),
    ]
    if problems:
        raise ArchiveError("\n".join(problems))


def _put(root: Path, files: Mapping[str, str | bytes]) -> None:
    for path, data in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(data.encode() if isinstance(data, str) else data)


class Choice(StrEnum):
    KEEP = "keep"  # the file of this data directory
    TAKE = "take"  # the file of the import


def _change(old: str | None, new: str | None) -> str:
    return "" if old == new else "added" if old is None else "removed" if new is None else "changed"


@dataclass(frozen=True)
class Side:
    """A file from one place to another: `base`, `here` or `zip`. None: no such file."""

    before: str
    after: str
    old: str | None
    new: str | None

    def unified(self, path: str) -> str:
        """The unified diff of the texts, the file names prefixed with their places."""
        return "".join(
            difflib.unified_diff(
                (self.old or "").splitlines(keepends=True),
                (self.new or "").splitlines(keepends=True),
                f"{self.before}/{path}",
                f"{self.after}/{path}",
            )
        )


@dataclass(frozen=True)
class Change:
    """A file that this data directory and the import hold differently. None: no such file."""

    path: str
    base: str | None  # at the base of the export; the file here when the base is unknown
    ours: str | None
    theirs: str | None
    known: bool  # a base to compare with: of the export, or nothing in an empty directory

    @property
    def here(self) -> str:
        """How the file changed here since the base: `added`, `removed`, `changed` or empty."""
        return _change(self.base, self.ours)

    @property
    def there(self) -> str:
        """How the file changed in the import since the base."""
        return _change(self.base, self.theirs)

    @property
    def conflict(self) -> bool:
        return bool(self.here and self.there)

    @property
    def default(self) -> Choice | None:
        """The side that changed the file. None where the import asks: a change on both sides, a
        file of another history, a file that the import would remove."""
        if not self.known or self.conflict:
            return None
        return Choice.KEEP if self.here else None if self.theirs is None else Choice.TAKE

    @property
    def sides(self) -> list[Side]:
        """The differences that show a file that the import asks for: at a conflict of each side
        against the base, then of the zip against the file here, which names what a take drops
        here too; else that one only."""
        taken = Side("here", "zip", self.ours, self.theirs)
        if self.conflict:
            return [
                Side("base", "here", self.base, self.ours),
                Side("base", "zip", self.base, self.theirs),
                taken,
            ]
        return [taken]

    def action(self, choice: Choice) -> str:
        """What the import does to the file here."""
        if choice is Choice.KEEP:
            return "keep"
        return "add" if self.ours is None else "remove" if self.theirs is None else "replace"


@dataclass(frozen=True)
class Preview:
    """What an import changes in a data directory."""

    archive: Archive
    head: str | None  # of the data directory at the preview
    known: bool  # the base of the export is a revision of the data directory
    empty: bool  # the data directory has no input and no revision: the history moves along
    changes: tuple[Change, ...]
    unchanged: int  # the inputs that both hold alike, the manifest aside

    @property
    def undecided(self) -> list[Change]:
        """The files without a default: the import asks keep or take."""
        return [c for c in self.changes if c.default is None]

    @property
    def stranger(self) -> bool:
        """Whether the export names a base that this data directory does not know (`STRANGER`)."""
        return not (self.known or self.empty)

    @property
    def remarks(self) -> list[str]:
        """What the preview says besides `STRANGER` and the list of files, in the language of the
        session (the CLI speaks English)."""
        history = self.archive.history
        return [
            *([_("The revisions of the zip move along.")] if history and self.empty else []),
            *(
                [_("The revisions of the zip are ignored: this data directory has its own.")]
                if history and not self.empty
                else []
            ),
            *filter(None, [self.archive.migration]),
        ]

    @property
    def notes(self) -> list[str]:
        """`STRANGER` if it holds, then the `remarks`."""
        return [*([_(STRANGER)] if self.stranger else []), *self.remarks]

    def texts(self, choices: Mapping[str, Choice]) -> dict[str, str | None]:
        """The files that the import writes, None removes: each file that its choice or else its
        default takes. Raises ValueError for a choice of a file without a change and for an
        undecided file without a choice."""
        if unknown := sorted(choices.keys() - {c.path for c in self.changes}):
            msg = f"the import changes no {', '.join(unknown)}"
            raise ValueError(msg)
        if open_ := [c.path for c in self.undecided if c.path not in choices]:
            msg = f"keep or take: {', '.join(open_)}"
            raise ValueError(msg)
        return {
            c.path: c.theirs for c in self.changes if choices.get(c.path, c.default) is Choice.TAKE
        }


def preview(data_dir: Path, source: Path | IO[bytes]) -> Preview:
    """Compare the export zip `source` with `data_dir`, after a migration and the edits outside
    the app (`datadir.open`) unless it is empty. Each file against the base of the export: a file
    changed on one side takes that side, one changed on both sides is a conflict. Without the
    base in the log here, against the files here: the import takes every file."""
    archive = read(source)
    if not (empty := datadir.empty(data_dir)):
        datadir.open(data_dir)
    log = revisions.entries(data_dir)
    known = archive.base in {e.id for e in log}
    ours = _inputs(
        {path: decoded((data_dir / path).read_bytes(), path) for path in schema.Tree(data_dir)}
    )
    theirs = _inputs(archive.inputs)
    base = _base(data_dir, archive.base) if known and archive.base else ours
    return Preview(
        archive,
        log[-1].id if log else None,
        known,
        empty,
        tuple(
            Change(path, base.get(path), ours.get(path), theirs.get(path), known or empty)
            for path in sorted(ours.keys() | theirs.keys())
            if ours.get(path) != theirs.get(path)
        ),
        sum(ours[path] == theirs[path] for path in ours.keys() & theirs.keys()),
    )


def _inputs(texts: Mapping[str, str]) -> dict[str, str]:
    """The inputs of `texts` without the manifest: an import keeps the one of the directory."""
    return {
        path: text
        for path, text in texts.items()
        if revisions.is_tracked(path) and path != MANIFEST
    }


def _base(data_dir: Path, at: str) -> dict[str, str]:
    """The inputs of the revision `at`, migrated like the zip: a migration since on either side
    is no change."""
    texts = {
        path: decoded(copy.read_bytes(), path)
        for path, copy in revisions.state(data_dir, at).items()
    }
    return _inputs(texts | schema.migrate(texts))


def apply(
    data_dir: Path, preview: Preview, choices: Mapping[str, Choice] | None = None
) -> revisions.Entry | None:
    """Write what `preview` takes as one revision, source `import <zip>`, the manifest here
    kept. Into an empty data directory the revisions of the zip move along first, with the
    inputs of their head. Raises `StaleError` when the data directory changed since the preview,
    and `InputError` when the files taken and kept do not load together: nothing changes then."""
    texts = preview.texts(choices or {})
    expected = preview.head
    if preview.empty:
        data_dir.mkdir(parents=True, exist_ok=True)
        if preview.archive.history:
            _take_history(data_dir, preview.archive)
            datadir.open(data_dir)
            expected = revisions.head(data_dir)

    def edit() -> revisions.Texts:
        if revisions.head(data_dir) != expected:
            raise StaleError(_STALE)
        new = {} if (data_dir / MANIFEST).is_file() else {MANIFEST: schema.manifest_text()}
        return texts | new

    return revisions.write(data_dir, f"import {preview.archive.name}", edit)


def _take_history(data_dir: Path, archive: Archive) -> None:
    """Move the revisions of the zip into the empty `data_dir`: first the inputs of their head as
    the live files, then `revisions/` by one rename. Interrupted before, the inputs stay without a
    history, and the next open records them as its baseline. The stage sits inside `data_dir`, a
    dot directory that no reader takes: its parent may be read-only or another file system."""
    if not datadir.empty(data_dir):
        raise StaleError(_STALE)
    if (data_dir / REVISIONS).exists():
        msg = "exists without a log: move it away, then import again"
        raise InputError([Problem(REVISIONS, None, "", msg)])
    stage = Path(tempfile.mkdtemp(prefix=".import.", dir=data_dir))
    try:
        _put(stage, _history(archive.files))
        for path, copy in revisions.state(stage).items():
            (data_dir / path).parent.mkdir(parents=True, exist_ok=True)
            files.atomic_write(data_dir / path, copy.read_bytes())
        (stage / REVISIONS).rename(data_dir / REVISIONS)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


@contextmanager
def temporary(path: Path) -> Iterator[Path]:
    """The inputs of the zip `path`, migrated, in a temporary directory that goes afterwards: for
    a run, which writes nothing back."""
    archive = read(path)
    with tempfile.TemporaryDirectory(prefix="dagobert-") as tmp:
        _put(Path(tmp), archive.inputs)
        yield Path(tmp)


def unpacked(path: Path) -> Path:
    """The directory `x/` beside the zip `x.zip`, with its files, for the app, which writes there
    and migrates it. An existing one serves only when its manifest names the base of the zip: an
    earlier unpack of the same export, with the edits since."""
    archive = read(path)
    target = path.with_suffix("")
    if target.exists():
        found = schema.manifest(schema.Tree(target)) if target.is_dir() else None
        if archive.base is None or found is None or found.base != archive.base:
            msg = (
                f"{target} exists and is no unpack of {path.name}: move it away, or serve it "
                f"with --data {target}"
            )
            raise ArchiveError(msg)
        return target
    tmp = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=path.parent))
    try:
        # a zip with history or manifest stays as it is, so that the open migrates it as a revision
        _put(tmp, archive.files if archive.written or archive.history else archive.inputs)
        tmp.rename(target)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return target
