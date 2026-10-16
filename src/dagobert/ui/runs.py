"""The runs of the explorer, which the Overview shares: cached by their options, overrides and the
inputs, and the process pool of the goal seek and the sensitivity."""

from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, fields
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
_KEEPING = threading.Lock()  # sessions run in threads of their own
_RUNNING = threading.Lock()  # one engine run at a time in the process (`cached_run`)


@st.cache_resource(show_spinner=False)
def _runs() -> dict[tuple[object, ...], RunResult | None]:
    return {}


def nbytes(run: RunResult | None) -> int:
    """The bytes of the arrays of `run`, also of those in its dicts (`balance`, `drivers`)."""
    held = [] if run is None else [getattr(run, f.name) for f in fields(run)]
    arrays = [*held, *(a for d in held if isinstance(d, dict) for a in d.values())]
    return sum(a.nbytes for a in arrays if isinstance(a, np.ndarray))


def cached_run(opts: Options, scenario: Path, overrides: str, stamp: Stamp) -> RunResult | None:
    """The run of `scenario` with the `overrides` (JSON) on the inputs of `stamp`, kept by the
    process for every session up to `RUNS_BYTES`, the least recently used out first. The process
    computes one run at a time: a session waits for the run of another, also of the same key,
    which it then takes from the cache, so the process holds at most one run in the making."""
    runs, key = _runs(), (opts, scenario, overrides, stamp)
    try:
        run = runs[key]
    except KeyError:
        with _RUNNING:
            run = runs[key] if key in runs else opts.run_one(scenario, json.loads(overrides))
            return keep(runs, key, run, RUNS_BYTES, nbytes)
    return keep(runs, key, run, RUNS_BYTES, nbytes)


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
    return fixed.result(data, Path(file).stem) if model == "fixed" else files_run(data, data / file)


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


@st.cache_resource(show_spinner=False)
def pool() -> ProcessPoolExecutor:
    """Spawned, not forked: Streamlit runs threads. The workers stay warm between reruns."""
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
