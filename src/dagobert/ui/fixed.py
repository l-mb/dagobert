"""The single-path run of a scenario with the mean returns and the mean inflation: the engine's
own numbers behind the Flows page, the Cashflows sheet and bars, the disability check of the
Overview, the salary sliders of the explorer and the salary factors of the Overrides tab."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from dagobert import cache
from dagobert.result import RunResult
from dagobert.runner import Options
from dagobert.scenariofiles import scenario_file
from dagobert.ui import Stamp, run_stamp


def options(data_dir: Path) -> Options:
    """The options of the `fixed` run of the inputs in `data_dir`: one path, no life table."""
    return Options(data_dir, data_dir, "fixed", 1, seed=0, mortality=False)


@st.cache_data(max_entries=8, show_spinner=False)  # a few scenarios at the latest stamp
def _cached(data_dir: str, scenario: str, stamp: Stamp) -> RunResult | None:
    """Below it the cache on disk (`cache.kept_run`): a restart takes the run from there."""
    del stamp  # cache key only: an input changed
    data = Path(data_dir)
    return cache.kept_run(data, options(data), data / scenario_file(scenario))


def forget() -> None:
    """The runs that the process keeps out (`runs.forget`): the next takes the disk or runs."""
    _cached.clear()


def result(data_dir: Path, scenario: str) -> RunResult | None:
    """The run of the files, cached until one that a run reads changes (`ui.run_stamp`)."""
    return _cached(str(data_dir), scenario, run_stamp(data_dir))
