"""Atomic file writes: a temp file in the same directory, synced, then `os.replace`. The YAML
layout of every input that the app writes, and `text_only`, its YAML 1.1 check of a text. The
reader of the CSV inputs (`read_csv`, `finite`)."""

from __future__ import annotations

import csv
import io
import math
import os
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Final, cast

import yaml as pyyaml
from ruamel.yaml import YAML
from ruamel.yaml.nodes import ScalarNode
from ruamel.yaml.representer import RoundTripRepresenter

from dagobert.problems import InputError, Problem

WINDOWS: Final = sys.platform == "win32"
# seconds between the tries of a replace that Windows refuses while another process holds the file
REPLACE_WAITS: Final = (0.05, 0.1, 0.2, 0.4)


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


# the mode of a new file: `mkstemp` makes 0600, which `os.replace` would keep
NEW_MODE: Final = 0o666 & ~_umask()


def atomic_write(path: Path, text: str | bytes) -> None:
    """Write `text` (a string as UTF-8, bytes as they are) to `path` so a crash or a failed
    write leaves the previous content in place: nothing touches `path` until the replacement is
    on disk. It keeps the mode of `path`, a new file takes that of the umask."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode) if path.exists() else NEW_MODE)
            fh.write(text.encode() if isinstance(text, str) else text)
            fh.flush()
            os.fsync(fh.fileno())
        _replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _replace(source: str, target: Path) -> None:
    """`os.replace`. Windows refuses it while another process holds `target` open (a reader of
    the inputs, a virus scanner), so there it tries again after `REPLACE_WAITS`."""
    for wait in REPLACE_WAITS if WINDOWS else ():
        try:
            os.replace(source, target)
        except PermissionError:
            time.sleep(wait)
        else:
            return
    os.replace(source, target)


def fsync_dir(directory: Path) -> None:
    """Make the entries of `directory` durable: a file created, replaced or removed there stays
    so after a crash. Windows opens no directory to sync it: NTFS logs its entries itself."""
    if WINDOWS:
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


STR = "tag:yaml.org,2002:str"
# the tag that the loader (PyYAML, YAML 1.1) gives a scalar: of a plain one with `(True, False)`
_RESOLVE: Callable[[type[pyyaml.Node], str, tuple[bool, bool]], str] = (
    pyyaml.resolver.Resolver().resolve
)


def text_only(value: str) -> bool:
    """Whether the loader reads `value`, written plain, as this text: not `on`, `no`, `null`,
    `1_000` or a date, which YAML 1.1 reads as something else."""
    return _RESOLVE(pyyaml.ScalarNode, value, (True, False)) == STR


def _string(rep: RoundTripRepresenter, value: str) -> ScalarNode:
    """A string, quoted where the loader would read it plain as something else: ruamel.yaml writes
    YAML 1.2, where `on` is text."""
    if "\n" not in value and not text_only(value):
        return rep.represent_scalar(STR, value, style="'")
    return cast("ScalarNode", rep.represent_str(value))


# ruamel.yaml keeps representers per class: these two hold for every round trip of the process
RoundTripRepresenter.add_representer(
    type(None), lambda rep, _: rep.represent_scalar("tag:yaml.org,2002:null", "null")
)
RoundTripRepresenter.add_representer(str, _string)


def yaml() -> YAML:
    """A round trip of a YAML input: comments and quotes survive, no line wraps, no anchors, a
    string that the loader would read as something else in quotes (`text_only`)."""
    out = YAML()
    out.preserve_quotes = True
    out.width = 4096
    out.indent(mapping=2, sequence=4, offset=2)
    # one `asof` date on several rows would become an anchor and aliases
    out.representer.ignore_aliases = lambda _: True
    return out


def dump(doc: Any) -> str:  # noqa: ANN401 ruamel nodes are untyped
    """`doc` as YAML text, in the layout of `yaml()`."""
    buf = io.StringIO()
    yaml().dump(doc, buf)
    return buf.getvalue()


def read_csv[T](
    path: Path, file: str, fields: Sequence[str], row: Callable[[dict[str, str]], T]
) -> list[T]:
    """`row` of each line of the CSV input at `path` (`file` under the data directory), its cells
    by header: `history.csv`, `actuals.csv`, a price file. Nothing for a missing or empty file. The
    BOM of Excel's `CSV UTF-8` is no part of the first header. A missing column, a line of more or
    fewer cells than the header and a cell that `row` does not read raise `InputError` with the
    line: a hand edit such as `1.234,56` read silently as 1.234."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        lines = csv.reader(fh)
        try:
            header = next(lines, [])
            if missing := [f for f in fields if f not in header] if header else []:
                msg = f"no column {', '.join(missing)} in the header"
                raise ValueError(msg)
            return [row(_cells(header, cells)) for cells in lines if cells]
        except (ValueError, csv.Error) as err:
            raise InputError([Problem(file, lines.line_num, "", str(err))]) from err


def finite(cell: str) -> float:
    """The number of a cell of a CSV input. Raises ValueError for one that does not read and for
    `nan` and `inf`, which `float` reads and every sum then carries."""
    if not math.isfinite(number := float(cell)):
        msg = f"{cell!r} is no finite number"
        raise ValueError(msg)
    return number


def _cells(header: list[str], cells: list[str]) -> dict[str, str]:
    if len(cells) != len(header):
        msg = f"{len(cells)} cells, the header names {len(header)}"
        raise ValueError(msg)
    return dict(zip(header, cells, strict=True))
