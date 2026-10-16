"""The results that outlive a restart of the app: the folder `.cache` of the data directory, one
`.npz` file per run or answer, the least recently used out first beyond `BYTES`. The name of an
entry hashes what gives it: the contents of the inputs that a run reads, the run options, the
overrides and the engine code. A file holds the arrays and one JSON text that names the rest, read
without pickle: a data directory of another person runs no code. The cache is no input: no
revision, export, import, stamp or migration sees it."""

from __future__ import annotations

import functools
import hashlib
import io
import json
import os
import platform
import re
from contextlib import suppress
from dataclasses import fields, is_dataclass
from datetime import date
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from zipfile import BadZipFile

import numpy as np

from dagobert import files, revisions, schema, series
from dagobert.goalseek import Dial, Found
from dagobert.result import Ledger, Marker, RunResult
from dagobert.sensitivity import Effect, Lever, Outcome, Sensitivity

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from numpy.typing import NDArray

    from dagobert.runner import Options

CACHE: Final = ".cache"
# What an engine run reads of the inputs: neither the manifest nor `app.yaml`, which names what the
# app shows (the scenarios that it opens with, the features off), not what a run computes
RUN_INPUTS: Final = (
    *(p for p in revisions.PLAN if p != schema.MANIFEST),
    f"{series.FETCHED}/*.csv",
)
RUN: Final = "run"  # the kind of an entry of a run, beside the answers of the pages
BYTES = 1 << 30  # what the files of the cache take at most: about 50 runs at 500 paths
# `memory`: no cache on disk, as for an export zip as `dagobert app --data`
MEMORY_ENV: Final = "DAGOBERT_CACHE"
MISSING: Final = object()  # what `read` gives for no entry: a kept answer may be None
PACKAGE: Final = Path(__file__).parent
PAGES: Final = ("ui", "report")  # the modules of the pages, which no run reads
_META: Final = "meta"  # the array of the JSON text in a file
NAME: Final = re.compile(r"[0-9a-f]{40}")  # the name of an entry: the hex digest of `key`
# the dataclasses that an entry may hold, by name: a file names no other type
TYPES: Final[dict[str, Callable[..., object]]] = {
    t.__name__: t
    for t in (RunResult, Marker, Ledger, Sensitivity, Effect, Lever, Outcome, Found, Dial)
}

# what a file that does not read raises: torn, of another format, with a pickle (ValueError), a
# type or fields of no entry, a JSON text nested too deep, an array too large to hold
UNREAD: Final = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    EOFError,
    BadZipFile,
    RecursionError,
    MemoryError,
)

type Json = bool | int | float | str | list[Json] | dict[str, Json] | None


@functools.cache
def code() -> str:
    """The hash of the engine code, once per process: `engine_code` of the package with the
    `libraries`."""
    return engine_code(PACKAGE, *libraries())


def libraries() -> list[str]:
    """Python and every installed distribution with its version: a new numpy draws other random
    numbers, a new pydantic or YAML parser may read an input otherwise. All of them, as a list of
    those that the engine imports would miss a new import, so a new Streamlit drops the entries
    too."""
    return [
        f"Python {platform.python_version()}",
        *sorted(f"{d.name} {d.version}" for d in metadata.distributions()),
    ]


def engine_code(root: Path, *versions: str) -> str:
    """The hash of the modules under `root` but those of the pages (`PAGES`), of the files of
    `data/` (the tax years, the series that ship) and of the `versions` of the libraries: a new
    engine computes new results, a change of a page keeps them."""
    shipped = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and (
            p.relative_to(root).parts[0] == "data"
            or (p.suffix == ".py" and p.relative_to(root).parts[0] not in PAGES)
        )
    ]
    return _hashed(root, shipped, *versions)


def digest(data: Path) -> str:
    """The hash of the contents of the files of `RUN_INPUTS` in `data`, with their paths: a run
    reads what they hold, whenever they were written. Read again when a file changes its size or
    its time in ns, comes or goes: also one put back with an older time (`cp -p`) while another is
    newer, which keeps `ui.run_stamp`."""
    stats = {
        p.relative_to(data).as_posix(): p.stat()
        for pattern in RUN_INPUTS
        for p in data.glob(pattern)
        if p.is_file()
    }
    return _digest(data, tuple(sorted((n, s.st_size, s.st_mtime_ns) for n, s in stats.items())))


@functools.lru_cache(maxsize=16)
def _digest(data: Path, signature: tuple[tuple[str, int, int], ...]) -> str:
    return _hashed(data, (data / name for name, _size, _time in signature))


def _hashed(root: Path, paths: Iterable[Path], *more: str) -> str:
    found = hashlib.blake2b(digest_size=20)
    for path in sorted(paths):
        content = path.read_bytes()
        found.update(f"{path.relative_to(root).as_posix()}\0{len(content)}\0".encode())
        found.update(content)
    for text in more:
        found.update(f"{text}\0".encode())
    return found.hexdigest()


def key(kind: str, opts: Options, scenario: Path, *parts: object) -> str:
    """The name of an entry of `kind` (a run, an answer) of `scenario` on the inputs of `opts.data`
    by their contents (`digest`) with the options `opts`, the overrides and the other `parts`: no
    data directory (a moved one keeps its entries) and no words (a `Lever` and a `Dial` by the
    fields that they compare), so a page in another language finds them."""
    held = {f.name: getattr(opts, f.name) for f in fields(opts) if f.name not in ("data", "out")}
    named = [
        kind,
        code(),
        digest(opts.data),
        held,
        scenario.relative_to(opts.data).as_posix(),
        *(_plain(part, {}, identity=True) for part in parts),
    ]
    return hashlib.blake2b(json.dumps(named).encode(), digest_size=20).hexdigest()


def kept_run(store: Path, opts: Options, scenario: Path) -> RunResult | None:
    """The run of `scenario` on the files of `opts.data` without overrides, from the cache of
    `store` by their contents (`digest`), else made and kept there: the `fixed` run of the files,
    a run of the inputs of a revision. None for an abstract scenario."""
    if isinstance(found := read(store, key(RUN, opts, scenario, "{}")), RunResult):
        return found
    return made(opts, scenario, "{}", store)


def made(opts: Options, scenario: Path, overrides: str, store: Path | None) -> RunResult | None:
    """The run of `scenario` with the `overrides` (JSON), kept in the cache of `store` (None: in
    none) by `kept`: what a worker of the pool runs, so the name hashes the inputs as it starts,
    not as it went into the queue."""
    if store is None:
        return opts.run_one(scenario, json.loads(overrides))
    return kept(
        store,
        functools.partial(key, RUN, opts, scenario, overrides),
        functools.partial(opts.run_one, scenario, json.loads(overrides)),
    )


def kept[T](store: Path, name: Callable[[], str], make: Callable[[], T]) -> T:
    """`make()`, kept in the cache of `store` under `name()` when the name before it still holds
    after it: a save while it runs leaves the result without a name, as an undo back to the inputs
    before would find it under theirs."""
    before = name()
    value = make()
    if name() == before:
        write(store, before, value)
    return value


def folder(data: Path) -> Path | None:
    """The cache of `data`, None for memory only: a data directory that takes no write, or
    `MEMORY_ENV`."""
    if os.environ.get(MEMORY_ENV) == "memory" or not os.access(data, os.W_OK):
        return None
    return data / CACHE


def read(data: Path, name: str) -> object:
    """The entry `name` in the cache of `data`, its file touched: the least recently used goes
    first. `MISSING` without one, also for a file that does not read (`UNREAD`), which goes."""
    if (held := folder(data)) is None:
        return MISSING
    path = _file(held, name)
    try:
        with np.load(path, allow_pickle=False) as stored:
            arrays = {k: stored[k] for k in stored.files}
        value = _value(json.loads(arrays.pop(_META).tobytes()), arrays)
    except FileNotFoundError:
        return MISSING
    except UNREAD:
        with suppress(OSError):
            path.unlink()
        return MISSING
    with suppress(OSError):
        os.utime(path)
    return value


def write(data: Path, name: str, value: object) -> None:
    """`value` under `name` in the cache of `data` (`files.atomic_write`, so another session never
    reads half a file), then the least recently used entries out while all take more than
    `BYTES`. A cache that takes no write (a read-only folder on Windows, a full disk) keeps
    nothing."""
    if (held := folder(data)) is None:
        return
    arrays: dict[str, NDArray[Any]] = {}
    text = json.dumps(_plain(value, arrays))
    buffer = io.BytesIO()
    np.savez(
        buffer, allow_pickle=False, **arrays, **{_META: np.frombuffer(text.encode(), np.uint8)}
    )
    path = _file(held, name)
    with suppress(OSError):
        held.mkdir(exist_ok=True)
        files.atomic_write(path, buffer.getvalue())
        _evict(held, BYTES)


def _file(held: Path, name: str) -> Path:
    """The file of the entry `name`, a name that `key` gives: no path."""
    if not NAME.fullmatch(name):
        msg = f"{name!r} is no name of an entry"
        raise ValueError(msg)
    return held / f"{name}.npz"


def size(data: Path) -> int:
    """The bytes that the cache of `data` takes on disk."""
    return sum(n for _time, n, _path in _entries(folder(data)))


def clear(data: Path) -> None:
    """Every file of the cache of `data` out."""
    for _time, _size, path in _entries(folder(data)):
        with suppress(OSError):
            os.unlink(path)


def _entries(held: Path | None) -> list[tuple[float, int, str]]:
    """The files of the cache, the least recently used first, with their sizes."""
    if held is None:
        return []
    try:
        with os.scandir(held) as found:
            stats = [(e.path, e.stat()) for e in found if e.is_file(follow_symlinks=False)]
    except OSError:
        return []
    return sorted((s.st_mtime, s.st_size, path) for path, s in stats)


def _evict(held: Path, limit: int) -> None:
    """The least recently used files out while all take more than `limit`, the newest kept."""
    entries = _entries(held)
    total = sum(n for _time, n, _path in entries)
    for _time, n, path in entries[:-1]:
        if total <= limit:
            return
        with suppress(OSError):
            os.unlink(path)
            total -= n


def _plain(  # noqa: PLR0911 one return per kind of value
    value: object, arrays: dict[str, NDArray[Any]], *, identity: bool = False
) -> Json:
    """`value` as JSON, its arrays into `arrays` by the names that it gives them. `identity`: a
    dataclass without the fields that it does not compare (its words)."""
    match value:
        case np.ndarray():
            arrays[name := f"a{len(arrays)}"] = value
            return {"array": name}
        case np.generic():
            return _plain(value.item(), arrays, identity=identity)
        case None | bool() | int() | float() | str():
            return value
        case date():
            return {"date": value.isoformat()}
        case tuple() | list():
            items = [_plain(v, arrays, identity=identity) for v in value]
            return {"tuple": items} if isinstance(value, tuple) else items
        case dict():
            pairs: list[Json] = [
                [_plain(k, arrays, identity=identity), _plain(v, arrays, identity=identity)]
                for k, v in value.items()
            ]
            return {"dict": pairs}
        case _ if is_dataclass(value) and TYPES.get(type(value).__name__) is type(value):
            return {
                "type": type(value).__name__,
                "fields": {
                    f.name: _plain(getattr(value, f.name), arrays, identity=identity)
                    for f in fields(value)
                    if f.compare or not identity
                },
            }
    msg = f"{type(value).__name__} does not go into the cache"
    raise TypeError(msg)


def _value(node: Json, arrays: dict[str, NDArray[Any]]) -> object:  # noqa: PLR0911 one per kind
    """What `_plain` wrote as `node`, with its `arrays`. KeyError or TypeError for a node that it
    does not write."""
    match node:
        case list():
            return [_value(v, arrays) for v in node]
        case {"array": str(name)}:
            return arrays[name]
        case {"date": str(day)}:
            return date.fromisoformat(day)
        case {"tuple": list(items)}:
            return tuple(_value(v, arrays) for v in items)
        case {"dict": list(pairs)}:
            return {_value(k, arrays): _value(v, arrays) for k, v in map(_pair, pairs)}
        case {"type": str(name), "fields": dict(held)}:
            return TYPES[name](**{k: _value(v, arrays) for k, v in held.items()})
        case dict():
            msg = f"no value: {sorted(node)}"
            raise TypeError(msg)
    return node


def _pair(pair: Json) -> tuple[Json, Json]:
    match pair:
        case [k, v]:
            return k, v
    msg = "no pair"
    raise TypeError(msg)
