"""Edit the YAML inputs as text: numbers, dates and texts replaced in place, keys renamed and
added, every other character kept. A dump of `ruamel.yaml` would rewrite the flow mappings."""

from __future__ import annotations

import operator
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from functools import reduce
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from dagobert.files import text_only
from dagobert.problems import Keys

if TYPE_CHECKING:
    from pathlib import Path

Scalar = float | date | str
# a quoted or a plain scalar that holds no space: a number or a date
_TOKEN = re.compile(r""""(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s,\]}#]+""")
# a text that stays plain in a block and in a flow collection; any other takes quotes
_PLAIN = re.compile(r"""[^\s'"\-?:,\[\]{}#&*!|>%@`][^:#,\[\]{}\n\r\t]*(?<!\s)""")
# the lines of a text with their ends, as ruamel.yaml counts them: `splitlines` also splits at
# `\x0b`, `\x0c` and `\x1c` to `\x1e`
_LINES = re.compile(r"[^\n]*\n|[^\n]+\Z")
# a null written as such
_NULL = re.compile(r"(?:null|Null|NULL|~)(?=[\s,\]}]|$)")


class First(Enum):
    """`After.key` of a mapping without an entry whose value takes one line: one whose entries
    all hold mappings, or `{}`."""

    FIRST = "first"


FIRST = First.FIRST


@dataclass(frozen=True)
class After:
    """The value of a key that the mapping lacks, a scalar or a flow mapping of scalars. It goes
    in after the entry `key`, whose value takes one line: on the next line of a block mapping,
    next to it in a flow mapping. `FIRST` puts it in front of the first entry, in its column,
    or into `{}`."""

    key: str | First
    value: Scalar | dict[str, Scalar]


@dataclass(frozen=True)
class Key:
    """A new name of the key at the end of a key path: its value and comments stay (a rename)."""

    name: str


# by file name under the data directory
Spots = Mapping[str, Mapping[Keys, Scalar | After | Key]]


def scalars(data_dir: Path, values: Spots) -> dict[str, str]:
    """The texts of the files with scalars replaced in place, keys renamed (`Key`) or scalars
    added (`After`), by file name under `data_dir` and key path from the top level: the rest of
    the text stays as it is, flow mappings and their spacing included. Read now: inside a write
    (`revisions.write`) they are the newest."""
    return {name: _replaced(data_dir / name, spots) for name, spots in values.items()}


def _replaced(path: Path, values: Mapping[Keys, Scalar | After | Key]) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")  # every write is LF (owner)
    doc = YAML().load(text)
    lines = _LINES.findall(text)
    spots: defaultdict[tuple[int, int, int], list[str]] = defaultdict(list)
    for k, v in values.items():
        line, col, end, new = _edit(path, lines, reduce(operator.getitem, k[:-1], doc), k[-1], v)
        spots[line, col, end].append(new)
    for (line, col, end), texts in sorted(spots.items(), reverse=True):  # from the end
        row = lines[line]
        # keys added at one place: into `{}` a comma between them, elsewhere each ends itself;
        # behind a last line without its newline each starts one, which they share
        joint = ", " if row[col - 1 : end + 1] == "{}" else ""
        lead = "\n" if not joint and all(t.startswith("\n") for t in texts) else ""
        added = joint.join(t.removeprefix(lead) for t in sorted(texts))
        lines[line] = row[:col] + lead + added + row[end:]
    return "".join(lines)


def _edit(
    path: Path,
    lines: list[str],
    node: Any,  # noqa: ANN401 ruamel nodes are untyped
    key: str | int,
    value: Scalar | After | Key,
) -> tuple[int, int, int, str]:
    """Line, first and end column of the text to replace, and the new text. A text that
    replaces a quoted one stays quoted, in single quotes."""
    if isinstance(value, Key):
        line, col = node.lc.key(key)
        end = _token(path, lines, line, col, key)
        return line, col, end, _scalar(value.name, quoted=lines[line][col] in "'\"")
    if not isinstance(value, After):
        if isinstance(key, str) and node[key] is None:
            return _null(path, lines, node, key, _scalar(value))
        line, col = node.lc.item(key) if isinstance(key, int) else node.lc.value(key)
        end = _token(path, lines, line, col, node[key])
        return line, col, end, _scalar(value, quoted=lines[line][col] in "'\"")
    new = value.value
    flow = ", ".join(f"{k}: {_scalar(v)}" for k, v in new.items()) if isinstance(new, dict) else ""
    entry = f"{key}: {{{flow}}}" if isinstance(new, dict) else f"{key}: {_scalar(new)}"
    if value.key is FIRST:
        return _first(lines, node, entry)
    if node.fa.flow_style():
        line, col = node.lc.value(value.key)
        end = _token(path, lines, line, col, node[value.key])
        return line, end, end, f", {entry}"
    line, col = node.lc.key(value.key)
    text, end = lines[line], len(lines[line])
    return line, end, end, ("" if text.endswith("\n") else "\n") + f"{' ' * col}{entry}\n"


def _first(lines: list[str], node: Any, entry: str) -> tuple[int, int, int, str]:  # noqa: ANN401
    """`_edit` of `entry` as the first entry of the mapping `node`: in front of its first key, or
    inside the braces of `{}` (which ruamel.yaml gives no flow style)."""
    if not node:
        line, col = node.lc.line, node.lc.col + 1
        return line, col, col, entry
    line, col = node.lc.key(next(iter(node)))
    return line, col, col, entry + (", " if node.fa.flow_style() else "\n" + " " * col)


def _null(
    path: Path,
    lines: list[str],
    node: Any,  # noqa: ANN401 ruamel nodes are untyped
    key: str,
    new: str,
) -> tuple[int, int, int, str]:
    """The edit that writes `new` for the null value of `key`: in place of its `null` or `~`, else
    behind the colon of the key. ruamel.yaml places a value that holds no text at what follows
    (`founded:` above `rv: none`), so a write there replaced the next key."""
    line, col = node.lc.key(key)
    text = lines[line]
    colon = text.index(":", _token(path, lines, line, col, key)) + 1
    after = len(text) - len(text[colon:].lstrip(" \t"))
    if written := _NULL.match(text, after):
        return line, after, written.end(), new
    return line, colon, after, f" {new}" + " " * text.startswith("#", after)


def _token(path: Path, lines: list[str], line: int, col: int, old: object) -> int:
    """The end column of the scalar `old` at `col`: a plain text as written, since a name holds
    spaces (`Rent from the flat`), else a quoted scalar or one without a space that reads as
    `old`."""
    if isinstance(old, str) and lines[line].startswith(old, col):
        return col + len(old)
    token = _TOKEN.match(lines[line], col)
    if (
        token is None
        or (isinstance(old, str) and token[0][0] not in "'\"")
        or not _reads(token[0], old)
    ):
        msg = f"{path.name}:{line + 1}: no scalar {old!r} at column {col + 1}"
        raise ValueError(msg)
    return token.end()


def _reads(token: str, old: object) -> bool:
    """Whether `token` alone reads as `old`. ruamel.yaml places an alias at its anchor."""
    try:
        loaded = YAML().load(token)
        return loaded == old and isinstance(loaded, bool) == isinstance(old, bool)
    except YAMLError, LookupError:  # a tag or an alias alone
        return False


def _scalar(value: Scalar, *, quoted: bool = False) -> str:
    """A value as YAML: a text plain where it reads as itself in a block and in a flow
    collection (`files.text_only`), else in single quotes."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        plain = not quoted and _PLAIN.fullmatch(value) and text_only(value)
        return value if plain else "'" + value.replace("'", "''") + "'"
    return str(int(value)) if float(value).is_integer() else repr(value)
