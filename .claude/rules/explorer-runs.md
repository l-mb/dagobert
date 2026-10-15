---
paths:
  - "src/dagobert/ui/{explorer,runs,seek,outlook,main}.py"
  - "tests/test_ui_explorer.py"
---

# Explorer runs

The runs of the Explorer, their caches and the process pool, which the Overview shares. The
page: rule `explorer`; the sensitivity run: rule `analyses`; the memory in a container: rule
`container`.

- No cache key holds words, so a page in another language finds the runs (rule `i18n`):
  `sensitivity.Lever` (`label`, `format`, `step`) and `goalseek.Dial` compare without their words
  (`_found`, `_seeks`), and `_sensitivity` names the effects by the levers of this run. A run
  carries the label of its scenario (`scenario_labels`: a shared name with its file), so tabs,
  table, strip and difference tell them apart, and `extended` pairs by it; a run of the files is
  `RunResult.twin` (rule `charts`).
- The explorer runs the sensitivity last, so the page shows first, in a spawned process pool (kept
  by `st.cache_resource`) of `runs.workers()` processes: `DAGOBERT_WORKERS`, else one per CPU of the
  process (`os.process_cpu_count`, which follows a cpuset) up to `runs.WORKERS`, 8. Python does not
  see the CPU quota of a container, so set the variable there. A worker holds one run, about 750 MB
  at 5000 paths (rule `container`). `runs.cached_run` keeps the runs of all sessions up to
  `runs.RUNS_BYTES`, 1 GiB by `nbytes` (the arrays, also those of its dicts: about 200 MiB a run of
  65 years at 5000 paths), the least recently used out first (`keep` with `size`). It computes one
  run at a time in the process (`_RUNNING`, one lock for all keys, not one per key: the main process
  holds at most one run in the making, also with two sessions, rule `container`); a session that
  asks for a run in the making waits and takes it from the cache, and a second session waits for
  the run of the first. About 90 runs take 7 s per scenario at 500 paths, on a phone for
  the open tab and an open fold only. The step per slider is `Unit.delta`, inside the range of the
  slider, which widens to the file value (`Unit.side`). The progress bar, which also writes the
  `Status` line above the table, is the point where a moved slider interrupts the run (a rerun
  waits for it: no fast reruns, rule `container`), and `run` then cancels what did not start. So
  no `st.cache_data` there: `explorer._found` keeps the results.
  A spawned worker imports the main script again (as `__mp_main__`), so all of `ui/main.py`, imports
  included, sits under `if __name__ == "__main__":`. Without the guard every worker draws the page
  in bare mode and logs Streamlit warnings. So does an `AppTest` script that reaches the pool
  (`apps.EXPLORER`): its workers wrote them past the capture of pytest.
- `src/dagobert/ui/outlook.py`: the plan on the Overview, `plan` (tiles, spending and work seek) and
  `on_track`. The tiles take the explorer's cached run (`runs.files_run`, the key of `runs.options`
  with no overrides), so an explorer opened with the same scenario shows at once. The seek runs in
  the explorer's pool (`runs.seek`) under a progress bar per round (`runs.tick`, also in the
  explorer); `runs.keep` bounds its answers and `_found` at `runs.KEPT`. The page fills `plan` into
  an `st.empty` below the tiles as its last step, so the rest of the page draws before the run.
