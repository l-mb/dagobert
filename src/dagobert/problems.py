"""Errors of the inputs that name the file, the line and the key path:
`assets.yaml:42: assets[3].trades[0].unit: unknown key`."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import count
from typing import TYPE_CHECKING, Any, NamedTuple

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedBase, CommentedMap, CommentedSeq
from ruamel.yaml.error import YAMLError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from pydantic import ValidationError

Keys = tuple[str | int, ...]


@dataclass(frozen=True)
class Problem:
    """What does not load at a key path of an input file. Overrides outside a file have no
    line, a file that does not parse no key path."""

    file: str
    line: int | None
    path: str
    message: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return ": ".join([where, *([self.path] if self.path else []), self.message])


class InputError(ValueError):
    """Inputs that do not load, one line per problem, sorted: `file:line: key.path: message`."""

    def __init__(self, problems: Iterable[Problem]) -> None:
        self.problems = sorted(problems, key=lambda p: (p.file, p.line or 0))
        super().__init__(self.problems)  # pickles: the explorer's process pool sends it back

    def __str__(self) -> str:
        return "\n".join(map(str, self.problems))


class RefusedError(ValueError):
    """What an import or a write refuses, with the reason in words: a file that holds no table, a
    column that it lacks, a row that is gone. A caller catches it, and an error of the code still
    raises."""


class Error(NamedTuple):
    """One error at a location of a document, as pydantic gives it, with the value there."""

    loc: Keys
    type: str
    msg: str
    input: object = None


def dotted(keys: Keys) -> str:
    """A key path as a problem shows it: `assets[3].trades[0].unit`."""
    return "".join(f"[{k}]" if isinstance(k, int) else f".{k}" for k in keys).removeprefix(".")


def message(error: Error) -> str:
    """What a problem says of `error`: `unknown key`, a check of the model without the `Value
    error, ` of pydantic, else the message of pydantic."""
    if error.type == "extra_forbidden":
        return "unknown key"
    return error.msg.removeprefix("Value error, ")


def errors(err: ValidationError, prefix: Keys = ()) -> list[Error]:
    """The errors of `err`, their locations below `prefix`."""
    return [
        Error((*prefix, *e["loc"]), e["type"], e["msg"], e["input"])
        for e in err.errors(include_url=False)
    ]


@dataclass(frozen=True)
class Source:
    """Where a key path may be written: in `doc` of `file`, below `prefix`. `root`: an error of
    the whole document may come from it."""

    file: str
    doc: Any  # from `with_lines`, or a plain mapping without lines
    prefix: Keys = ()
    root: bool = True


def with_lines(text: str) -> Any:  # noqa: ANN401 ruamel nodes are untyped
    """`text` parsed by ruamel.yaml, whose nodes know their lines. Without lines where only
    PyYAML, which reads the inputs, parses it."""
    reader = YAML()
    reader.allow_duplicate_keys = True  # as PyYAML
    try:
        return reader.load(text)
    except YAMLError:
        return yaml.safe_load(text)


NOT_UTF8 = "not UTF-8: save the file as UTF-8"


def decoded(data: bytes, file: str) -> str:
    """The UTF-8 text of `data`, `file` in a problem. Bytes that are not UTF-8 (a text saved as
    Windows-1252) raise `InputError` at the line of the first byte that is not. Newlines stay."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as err:
        raise InputError([Problem(file, data[: err.start].count(b"\n") + 1, "", NOT_UTF8)]) from err


def read_text(path: Path, file: str) -> str:
    """The text of the input `path`, as `decoded`, with LF newlines (CRLF and lone CR)."""
    return decoded(path.read_bytes(), file).replace("\r\n", "\n").replace("\r", "\n")


def parsed(text: str, file: str) -> Any:  # noqa: ANN401 parsed YAML
    """The YAML `text` of the input `file` as PyYAML, the reader of the inputs, reads it. Text that
    does not parse raises `InputError` (`syntax`)."""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as err:
        raise syntax(file, err, text) from err


def syntax(file: str, err: Exception, text: str) -> InputError:
    """A YAML `text` that does not parse (PyYAML or ruamel.yaml), with the line of the problem: of
    its mark, or of the character that the reader refuses (a control character)."""
    mark, position = getattr(err, "problem_mark", None), getattr(err, "position", None)
    if mark:
        line = mark.line + 1
    else:
        line = text[:position].count("\n") + 1 if isinstance(position, int) else None
    message = getattr(err, "problem", None) or getattr(err, "context", None)
    return InputError([Problem(file, line, "", str(message or str(err).partition("\n")[0]))])


def located(found: Iterable[Error], sources: Sequence[Source]) -> InputError:
    """Each error in the source that `deep_merge` takes its value from, `sources` in the order of
    precedence: the last one takes what no other holds."""
    return InputError(_problem(error, sources) for error in found)


class _Walk(NamedTuple):
    held: int  # the parts of the location that the document holds
    keys: Keys
    line: int | None
    merges: tuple[bool, ...]  # per part held: a mapping, which merges with the sources below


def _problem(error: Error, sources: Sequence[Source]) -> Problem:
    source, walk = _owner(error, [(source, _walk(source.doc, error)) for source in sources])
    return Problem(source.file, walk.line, dotted((*source.prefix, *walk.keys)), message(error))


def _owner(error: Error, walks: list[tuple[Source, _Walk]]) -> tuple[Source, _Walk]:
    """At each depth the first source that holds the location there, until one holds no mapping
    and replaces all below. An error of the whole document belongs to the first `root` source."""
    if not error.loc:
        return next((w for w in walks if w[0].root), walks[-1])
    owner = walks[-1]
    for depth in count(1):
        holder = next((w for w in walks if w[1].held >= depth), None)
        if holder is None:
            break
        owner = holder
        if not holder[1].merges[depth - 1]:
            break
    return owner


def _walk(doc: Any, error: Error) -> _Walk:  # noqa: ANN401 ruamel nodes are untyped
    """Follow the location of `error` through `doc`. A part that is no key or index there is the
    tag of a discriminated union and drops out, except the field that a `missing` error names."""
    node, keys, merges = doc, list[str | int](), list[bool]()
    line = doc.lc.line + 1 if isinstance(doc, CommentedBase) else None
    for i, part in enumerate(error.loc):
        if _holds(node, part):
            node, line = node[part], _line(node, part)
            keys.append(part)
            merges.append(isinstance(node, Mapping))
        elif i == len(error.loc) - 1 and error.type == "missing":
            keys.append(part)
    return _Walk(len(merges), tuple(keys), line, tuple(merges))


def _holds(node: Any, part: str | int) -> bool:  # noqa: ANN401
    if isinstance(node, Mapping):
        return part in node
    return (
        isinstance(node, Sequence)
        and not isinstance(node, str)
        and isinstance(part, int)
        and 0 <= part < len(node)
    )


def _line(node: Any, part: str | int) -> int | None:  # noqa: ANN401
    match node:
        case CommentedMap():
            return int(node.lc.key(part)[0]) + 1
        case CommentedSeq():
            return int(node.lc.item(part)[0]) + 1
    return None
