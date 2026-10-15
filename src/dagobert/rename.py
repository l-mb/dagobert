"""A rename of an asset id, a stream name, a phase or a relative in every input that names it: each
definition and use that `references` finds, replaced in place (`textedit.scalars`, so every other
character stays, comments and flow mappings too), and of an asset its rows of `history.csv`. A page
shows the lines that change (`preview`) and writes them as one revision (`apply`)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dagobert import history, references, revisions
from dagobert.model.assumptions import phase_name, relative_name
from dagobert.problems import Keys
from dagobert.references import Kind, References
from dagobert.textedit import Key, scalars

if TYPE_CHECKING:
    from pathlib import Path

KINDS = (Kind.ASSET, Kind.STREAM, Kind.PHASE, Kind.RELATIVE)  # the names that the editors keep


@dataclass(frozen=True)
class Rename:
    kind: Kind
    old: str
    new: str

    def __str__(self) -> str:
        """`asset flat → home`, the end of the source of its revision: no `rename a → b`, which
        names a renamed file (`revisions.renaming`)."""
        return f"{self.kind} {self.old} → {self.new}"


def _check(data_dir: Path, rename: Rename, refs: References) -> None:
    """Refuse a kind whose names the editors do not keep, a name that is gone, a new name that is
    the old one, has spaces at its ends or more than one line, is no phase name (`phase_name`) or
    is in use in any case: by an input, also one that names nothing yet, or by `history.csv`. A
    relative takes a short name like a phase (`relative_name`)."""
    kind, old, new = rename.kind, rename.old, rename.new
    if kind not in KINDS:
        msg = f"a {kind} has no rename"
        raise ValueError(msg)
    if old not in refs.defined[kind]:
        msg = f"the {kind} {old} is gone"
        raise ValueError(msg)
    if new == old:
        msg = f"the {kind} has the name {old}"
        raise ValueError(msg)
    if not new or new != new.strip() or len(new.splitlines()) > 1:
        msg = "a name takes one line, without spaces at its ends"
        raise ValueError(msg)
    if kind is Kind.PHASE:
        phase_name(new)
    if kind is Kind.RELATIVE:
        relative_name(new)
    recorded = {a for _, a, _ in history.read_history(data_dir)} if kind is Kind.ASSET else set()
    for names, taken in (
        (refs.defined[kind], f"the {kind} {{}} exists"),
        (refs.used[kind], f"the inputs use the {kind} name {{}}"),
        (recorded, f"{history.FILE} holds values of {{}}"),
    ):
        if same := sorted(n for n in names if n != old and n.casefold() == new.casefold()):
            raise ValueError(taken.format(same[0]))


def texts(data_dir: Path, rename: Rename) -> dict[str, str]:
    """The new text of each input that names `rename.old`, from the files now. Raises ValueError
    with the reason when the rename is refused."""
    refs = references.of(data_dir)
    _check(data_dir, rename, refs)
    spots: defaultdict[str, dict[Keys, str | Key]] = defaultdict(dict)
    for site in [*refs.defined[rename.kind][rename.old], *refs.uses(rename.kind, rename.old)]:
        spots[site.file][site.keys] = Key(rename.new) if site.key else rename.new
    out = scalars(data_dir, spots)
    if rename.kind is Kind.ASSET:
        out |= history.renamed(data_dir, rename.old, rename.new)
    return dict(sorted(out.items()))


@dataclass(frozen=True)
class Line:
    """A line that a rename changes: its file, its number from 1, its text before and after."""

    file: str
    number: int
    old: str
    new: str


@dataclass(frozen=True)
class Preview:
    """A rename as a page showed it before the user confirmed it: the text of each file that it
    changes, before and after, and what it read of each, which the write checks."""

    rename: Rename
    before: dict[str, str]
    after: dict[str, str]
    seen: tuple[revisions.Seen, ...]

    @property
    def lines(self) -> list[Line]:
        """The changed lines, file by file. A rename keeps the number of lines of a file."""
        return [
            Line(file, n, old, new)
            for file, text in self.after.items()
            for n, (old, new) in enumerate(
                zip(self.before[file].splitlines(), text.splitlines(), strict=True), 1
            )
            if old != new
        ]


def _text(data_dir: Path, name: str) -> str | None:
    path = data_dir / name
    return path.read_bytes().decode("utf-8") if path.exists() else None


def preview(data_dir: Path, rename: Rename) -> Preview:
    """The texts of `rename` now and the `Seen` of each file that it changes, its revision taken
    before its text. Raises ValueError with the reason when the rename is refused."""
    after = texts(data_dir, rename)
    revision = {name: revisions.last_change(data_dir, name) for name in after}
    before = {name: _text(data_dir, name) or "" for name in after}
    return Preview(
        rename,
        before,
        after,
        tuple(revisions.Seen(n, revision[n], revisions.digest(before[n])) for n in after),
    )


def apply(data_dir: Path, shown: Preview, *, source: str) -> None:
    """Write the rename that a page showed (`preview`) as one revision of `source`. Inside the
    write a file that it changes and that changed since raises `ConflictError`, and a change
    elsewhere that changes the rename (a new use of the name) refuses it."""

    def edit() -> revisions.Texts:
        for seen in shown.seen:
            revisions.unchanged(data_dir, seen, _text(data_dir, seen.file))
        if (now := texts(data_dir, shown.rename)) != shown.after:
            msg = "the inputs changed since the list: look again"
            raise ValueError(msg)
        return now

    revisions.write(data_dir, source, edit)
