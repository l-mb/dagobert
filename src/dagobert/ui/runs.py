"""The runs of the explorer, which the Overview shares: cached by their options, overrides and the
inputs, and the process pool that makes them, the goal seek and the sensitivity."""

from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
import threading
import time
from concurrent.futures import Future, ProcessPoolExecutor, wait
from dataclasses import dataclass, fields
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args

import numpy as np
import streamlit as st

from dagobert import goalseek, revisions, series
from dagobert.i18n import _
from dagobert.loader import load_plan
from dagobert.problems import InputError
from dagobert.result import RunResult
from dagobert.runner import WORKERS_ENV, ModelName, Options
from dagobert.schema import SchemaError
from dagobert.ui import RUN_INPUTS, Stamp, fixed, literal, run_stamp

if TYPE_CHECKING:
    from collections.abc import Callable

    from streamlit.delta_generator import DeltaGenerator

PATHS = 500  # the default of `Paths`, also of the plan tiles of the Overview
WORKERS = 8  # the default cap: a worker holds one run, about 750 MB at 5000 paths
KEPT = 64  # the answers of a seek or a sensitivity run that a process cache keeps (`keep`)
# the bytes of the runs that the process keeps (`cached_run`): a run of 65 years takes about
# 200 MiB at 5000 paths, so 1 GiB holds two scenarios with moved sliders and their runs of the files
RUNS_BYTES = 1 << 30
TICK = 0.1  # seconds between two Streamlit calls of a page that waits (`settle`)
REDRAW = 1.0  # seconds at least between two draws of the progress of the sensitivity (`throttled`)
_YIELD = "ui-runs-yield"  # a key of the session state that nothing sets: `yielded` reads it
_KEEPING = threading.Lock()  # sessions run in threads of their own
_STARTING = threading.Lock()  # `_MAKING`
# the runs in the pool by their key, for all sessions: a key never starts twice (`_making`)
_MAKING: dict[tuple[object, ...], Future[RunResult | None]] = {}

type Tick = Callable[[], object]


@st.cache_resource(show_spinner=False)
def _runs() -> dict[tuple[object, ...], RunResult | None]:
    return {}


def nbytes(run: RunResult | None) -> int:
    """The bytes of the arrays of `run`, also of those in its dicts (`balance`, `drivers`)."""
    held = [] if run is None else [getattr(run, f.name) for f in fields(run)]
    arrays = [*held, *(a for d in held if isinstance(d, dict) for a in d.values())]
    return sum(a.nbytes for a in arrays if isinstance(a, np.ndarray))


def yielded() -> None:
    """A Streamlit call that sends nothing: a read of the session state, where a rerun stops the
    script as at an element (`SafeSessionState` of Streamlit 1.65). An element each `TICK` kept
    the browser so busy that a move reached the server up to 0.7 s late."""
    st.session_state.get(_YIELD)


def throttled[T](
    show: Callable[[T], object], clock: Callable[[], float] = time.monotonic
) -> Callable[[T], None]:
    """`show` at most every `REDRAW` seconds, else `yielded`: a bar drawn after each of the runs
    of the sensitivity, about four a second, kept the browser so busy that a move reached the
    server up to 1 s late."""
    drawn = clock()

    def tick(value: T) -> None:
        nonlocal drawn
        if (now := clock()) - drawn < REDRAW:
            yielded()
            return
        drawn = now
        show(value)

    return tick


def settle(done: Callable[[], bool], tick: Tick, pause: Callable[[float], object]) -> None:
    """`tick` every `TICK` seconds (`pause`) until `done`: a Streamlit call in `tick` (`yielded`)
    is where a rerun stops the script, so a moved slider ends the wait at once."""
    while not done():
        tick()
        pause(TICK)


def cached_run(
    opts: Options, scenario: Path, overrides: str, stamp: Stamp, tick: Tick = yielded
) -> RunResult | None:
    """The run of `scenario` with the `overrides` (JSON) on the inputs of `stamp`, kept by the
    process for every session up to `RUNS_BYTES`, the least recently used out first. A miss runs
    in the pool (`submit`), and the page waits with a `tick` each `TICK`: a move stops the wait at
    once, and the run lands in the cache all the same. The page says that it simulates before,
    on a miss (`cached`)."""
    runs, key = _runs(), (opts, scenario, overrides, stamp)
    try:
        run = runs[key]
    except KeyError:
        future = submit(opts, scenario, overrides, stamp)
        settle(future.done, tick, lambda seconds: wait([future], seconds))
        run = future.result()
    return keep(runs, key, run, RUNS_BYTES, nbytes)


def submit(opts: Options, scenario: Path, overrides: str, stamp: Stamp) -> Future[RunResult | None]:
    """The run of `cached_run` in the pool, which a run in the making serves, also for another
    session, and a run that `_made` kept since the caller missed it, as a future done: no key
    starts twice. The runs of a page start together, a worker each. The main process makes no
    run: the results arrive one at a time, in the thread of the pool that keeps them (`_made`),
    so it holds at most one in the making."""
    runs, key = _runs(), (opts, scenario, overrides, stamp)
    with _STARTING:
        if (future := _MAKING.get(key)) is not None:
            return future
        try:
            run = runs[key]
        except KeyError:
            future = _MAKING[key] = pool().submit(opts.run_one, scenario, json.loads(overrides))
        else:
            future = Future()
            future.set_result(run)
            return future
    # outside the lock: a run done already calls back at once, in this thread
    future.add_done_callback(partial(_made, runs, key))
    return future


def _made(
    runs: dict[tuple[object, ...], RunResult | None],
    key: tuple[object, ...],
    future: Future[RunResult | None],
) -> None:
    """A run done goes into the cache, also when no session waits any more, and out of `_MAKING`
    at once. A run that raised starts again on request."""
    with _STARTING:
        if not future.cancelled() and future.exception() is None:
            keep(runs, key, future.result(), RUNS_BYTES, nbytes)
        if _MAKING.get(key) is future:
            del _MAKING[key]


def cached(opts: Options, scenario: Path, overrides: str, stamp: Stamp) -> bool:
    """Whether `cached_run` holds this run: a page says that it simulates on a miss only, so a hit
    never looks like a run."""
    return (opts, scenario, overrides, stamp) in _runs()


def options(data: Path, model: ModelName = "montecarlo", paths: int = PATHS) -> Options:
    """The run options of the explorer, part of the key of its cached runs."""
    return Options(data, data, model, paths, seed=42, mortality=True)


@dataclass(frozen=True)
class Refused:
    """Why the engine of today refuses the inputs of a revision that load: its ValueError as
    written, English like an input error, so a process cache may hold it."""

    why: str


def at_revision(
    data: Path, at: str, file: str, run: Callable[[Path, Path], RunResult | None]
) -> RunResult | Refused | None:
    """`run` of the data directory and the scenario `file` as the inputs stood at the revision
    `at`. None when they lack the scenario or do not load with the model of today, `Refused` when
    the engine refuses them (a ValueError: a past plan that the code of today does not run); any
    other error of the run raises. A cache keeps the answer: it keeps no exception."""
    with tempfile.TemporaryDirectory() as tmp:
        then = Path(tmp)
        try:
            revisions.materialize(data, at, then)
            load_plan(then, then / file)
        except InputError, SchemaError, FileNotFoundError:
            return None
        try:
            return run(then, then / file)
        except ValueError as err:
            return Refused(str(err))


def baseline(
    data: Path, file: str, at: str, model: Literal["fixed", "explorer"]
) -> RunResult | Refused | None:
    """The `fixed` run or the explorer's run of the scenario `file` on the inputs at the revision
    `at`. While no later revision changed what a run reads (`ui.RUN_INPUTS`), the run of the
    files, which `datadir.open` keeps at the head: a first Overview runs nothing more, and a
    ValueError of the engine raises as in `files_run` (the tiles ran those files first). Else
    `at_revision` in a directory of its own, which gives a refusal as `Refused`."""
    if revisions.changed_after(data, at, RUN_INPUTS):
        return _baseline(str(data), file, at, model)
    if model == "fixed":
        return fixed.result(data, Path(file).stem)
    return files_run(data, data / file)


@st.cache_resource(max_entries=8, show_spinner=False)
def _baseline(
    data_dir: str, file: str, at: str, model: Literal["fixed", "explorer"]
) -> RunResult | Refused | None:
    return at_revision(
        Path(data_dir),
        at,
        file,
        (lambda d, f: fixed.run(d, f.stem))
        if model == "fixed"
        else (lambda d, f: options(d).run_one(f)),
    )


def refusal(past: Refused | None, subject: str) -> str:
    """The warning that `subject`, the inputs of an earlier day, gives no run: `past` is None
    when they do not load, else the refusal of the engine."""
    return (
        _("{subject} does not load with this version of the app. Choose a newer day.").format(
            subject=subject
        )
        if past is None
        else _(
            "{subject} does not run with this version of the app ({why}). Choose a newer day."
        ).format(subject=subject, why=literal(past.why))
    )


def models(data: Path) -> list[ModelName]:
    """The models that can run on `data`: `historical` needs the equity series."""
    return [
        m
        for m in get_args(ModelName)
        if m != "historical" or series.load(series.EQUITY, data) is not None
    ]


def files_run(data: Path, scenario: Path) -> RunResult | None:
    """The run of the files with the default options: the explorer opens with it, so the
    Overview shares its cache."""
    return cached_run(options(data), scenario, "{}", run_stamp(data))


def files_cached(data: Path, scenario: Path) -> bool:
    """Whether `files_run` takes its run from the cache."""
    return cached(options(data), scenario, "{}", run_stamp(data))


def workers() -> int:
    """`DAGOBERT_WORKERS`, else one per CPU of the process up to `WORKERS`. Python does not see
    the CPU quota of a container: set the variable there."""
    return int(os.environ.get(WORKERS_ENV) or min(WORKERS, os.process_cpu_count() or 1))


def _whole(executor: ProcessPoolExecutor) -> bool:
    """Whether no worker died: a pool whose worker the kernel killed (out of memory) raises
    BrokenProcessPool on every call. `_broken`: no public API tells it (CPython 3.14)."""
    return not executor._broken  # pyright: ignore[reportPrivateUsage]


@st.cache_resource(show_spinner=False, validate=_whole)
def pool() -> ProcessPoolExecutor:
    """Spawned, not forked: Streamlit runs threads. The workers stay warm between reruns. A
    broken pool gives way to a new one at the next call (`_whole`)."""
    return ProcessPoolExecutor(workers(), mp_context=multiprocessing.get_context("spawn"))


def seek(
    job: goalseek.Job, dial: goalseek.Dial, progress: Callable[[float], object]
) -> goalseek.Found:
    """In the process pool, as many runs at a time as it has workers, `progress` after each
    round: about 2 + 25 runs per round, some 10 s at 500 paths."""
    return goalseek.seek(job, dial, pool(), workers(), progress)


def tick(bar: DeltaGenerator, text: str, n: int, count: int, share: float) -> None:
    """The progress bar of a seek in the `n`th of `count` scenarios, `share` of its rounds done."""
    bar.progress((n + share) / count, text)


def keep[K, V](
    found: dict[K, V], key: K, value: V, limit: int = KEPT, size: Callable[[V], int] = lambda _v: 1
) -> V:
    """`value` under `key` as the newest entry of a cache of the process (`st.cache_resource`),
    the oldest out while the sizes of the entries add up beyond `limit`, the newest kept: a cache
    of the answers grows with every slider position and input."""
    with _KEEPING:
        found.pop(key, None)
        found[key] = value
        while len(found) > 1 and sum(map(size, found.values())) > limit:
            del found[next(iter(found))]
    return value
