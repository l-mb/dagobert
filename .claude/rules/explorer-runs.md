---
paths:
  - "src/dagobert/ui/{explorer,runs,seek,outlook,main,fixed,figures}.py"
  - "src/dagobert/cache.py"
  - "tests/test_{ui_explorer,cache}.py"
---

# Explorer runs

The runs of the Explorer, their caches in the process and on disk and the process pool, which the
Overview shares. The page: rule `explorer`; the sensitivity run: rule `analyses`; the memory in a
container: rule `container`.

- No cache key holds words, so a page in another language finds the runs (rule `i18n`):
  `sensitivity.Lever` (`label`, `format`, `step`) and `goalseek.Dial` compare without their words
  (`runs.answers`, `cache.key`), and `explorer.said` names the effects by the levers of this run. A
  run carries the label of its scenario (`scenario_labels`: a shared name with its file), so tabs,
  table, strip and difference tell them apart, and `extended` pairs by it; a run of the files is
  `RunResult.twin` (rule `charts`).
- Every run of the Explorer and of the plan of the Overview runs in a spawned process pool (kept by
  `st.cache_resource`) of `runs.workers()` processes: `DAGOBERT_WORKERS`, else one per CPU of the
  process (`os.process_cpu_count`, which follows a cpuset) up to `runs.WORKERS`, 8. Python does not
  see the CPU quota of a container, so set the variable there. A worker holds one run, about 750 MB
  at 5000 paths (rule `container`). A worker that dies (the kernel kills it for its memory) breaks
  the pool for good: `runs.pool` validates it (`_whole`, the `_broken` of CPython) and makes a new
  one at the next call, so only the runs that waited on the broken one raise `BrokenProcessPool`.
  A rerun stops a script only at its next Streamlit call (no fast reruns, rule `container`), so a
  page never blocks on a run: `runs.settle` calls a `tick` every `runs.TICK`, 0.1 s, until the run
  is done, and a moved slider ends the wait at once. The tick is `runs.yielded`, a read of the
  session state: Streamlit 1.65 checks for a rerun there as at an element (`SafeSessionState`;
  check it after an upgrade, `test_a_wait_yields_at_a_read_of_the_session_state`) and sends the
  browser nothing. An element each tick (the `Status` line, a bar) kept the browser so busy that a
  move reached the server 0.2 to 0.7 s late, and so did a bar drawn after each run of the
  sensitivity (about four a second, up to 1 s). So a page draws its message once before the wait,
  on a miss (`runs.cached`), and the progress of the sensitivity at most each `runs.REDRAW`, 1 s
  (`throttled`), the ticks between yield. A spawned
  worker imports the main script again (as `__mp_main__`), so all of `ui/main.py`, imports
  included, sits under `if __name__ == "__main__":`. Without the guard every worker draws the page
  in bare mode and logs Streamlit warnings. So does an `AppTest` script that reaches the pool
  (`apps.EXPLORER`, `OVERVIEW`, `PAGE`): its workers wrote them past the capture of pytest. A test
  that counts engine runs takes the pool as threads (fixture `threads`).
- `runs.cached_run` keeps the runs of all sessions up to `runs.RUNS_BYTES`, 1 GiB by `nbytes` (the
  arrays, also those of its dicts: about 200 MiB a run of 65 years at 5000 paths), the least
  recently used out first (`keep` with `size`). A miss goes into the pool (`runs.submit`), once for
  all sessions: `_MAKING` holds the future of each key in the making, and a second session waits for
  that one. The thread of the pool keeps a run done (`_made`, under `_STARTING` with its removal
  from `_MAKING`), so a run that a move left lands in the cache, and the move back takes it.
  `submit` looks into the cache under `_STARTING` too: a run kept since the miss of its caller
  comes as a future done, so no key starts twice. The main process makes no run: the results
  arrive one at a time in that thread, so it holds at most one in the making, also with two
  sessions. `_results` submits the runs of the files and of the sliders that the cache lacks
  together, a worker each, then waits for those of the files first. A run left by a move is not
  cancelled: with fewer workers than runs (a container at 5000 paths), quick moves queue the runs
  of each position in turn.
- The sensitivity runs last, so the page shows first, only while its fold is open (rule `explorer`)
  and after the sliders rest (`explorer.REST`); about 110 runs take some 35 s per scenario at 500
  paths and 8 workers. The step per slider is `Unit.delta`, inside the range of the slider, which
  widens to the file value (`Unit.side`). `sensitivity.run` puts at most `runs.workers()` runs into
  the pool at a time, the next after a tick: a run in the queue of a process pool cannot be
  cancelled (`EXTRA_QUEUED_CALLS` and the call queue). It ticks every `runs.TICK` (`every`), also
  while no run ends, so a move stops it within a tick whatever a run takes, and `run` then puts no
  more in. The runs that started go on: the main runs of the move wait for the first worker that
  one of them frees (at 500 paths and 8 workers a run takes about 2 s, so some 0.25 s on average;
  at 5000 paths ten times as long). The tick, the progress bar that also writes the `Status` line
  above the table, is where a moved slider interrupts it. So no `st.cache_data` there:
  `runs.answers(SENSITIVITY)` keeps the results.
- Measured on 2026-10-16 in Chrome (example `engineer`, two scenarios, 500 paths, 8 workers,
  desktop; a host of 16 CPUs shared with other work, load 7 to 15; `ArrowRight` on `Inflation`, the
  first engine run of the new position in the worker): a release to the main results 1.6 s (2.6 to
  3.0 s with the two runs in the Streamlit process; the review could not reproduce that figure). A
  second move during the main runs starts its runs 0.35 to 0.6 s after its release, during the
  sensitivity 0.3 to 0.6 s in 10 of 12 tries (1.0 s twice). Of that the browser takes up to 0.1 s to
  send the move, the server 0.3 to 0.5 s (the tick, the page up to `_results`, a worker that the
  sensitivity frees). The same code with an element each tick and a bar per run of the sensitivity,
  alternated with it: 0.5 to 1.2 s and 0.7 to 1.8 s, the browser 0.2 to 0.7 s of it. A move in the 3
  s after the results arrive waits for the browser, which draws the charts of the page (long tasks
  back to back), 0.3 to 1.1 s, with or without the change; the server then takes 0.2 to 0.35 s. The
  review measured again that day: a second move starts its runs at a median of 0.5 to 0.7 s, a tail
  to 1.3 s (the bound of #27), the floor 0.25 to 0.34 s to the first moved frame of an idle page,
  1.2 to 1.3 s after a restart of the server. Unverified: the rest sits in the build of the page
  before `_levers`. The sensitivity goes to the pool by `sensitivity.run`, not through
  `runs.submit`: two sessions of one key compute its runs twice (about 110), `answers` takes them
  when the whole sensitivity ends.
- The runs and what they give key by `ui.run_stamp`: the sums of the mtimes (ns) and the sizes and
  the count of `cache.RUN_INPUTS`, the plan files of `revisions.PLAN` without the manifest and
  `series/*.csv`, what a run reads (`load_plan`, `make_provider`; the life table ships). So
  `cached_run`, `files_run`, `fixed`, `runs.answers` (the sensitivity, the seeks) and `seek._dial`
  keep their runs over a save of `app.yaml` (`Set as default`, Features, the order of the
  scenarios), a price and `revisions/`. No run reads `app.yaml`: `features_off` and the mode only
  hide sliders, and a hidden slider stands at its file value, so the overrides of a key hold all
  that they change. The other caches of the inputs keep `ui.data_stamp` (`STAMPED`, also
  `app.yaml`). A sum, not the latest time: a write right after a read takes a time later than its
  file's, but maybe that of another file (Linux hands out such a time,
  `test_the_runs_follow_what_they_read_only`), and the latest time missed the edit. A profile of
  2026-10-16 found no engine run on a page switch. `runs.cached` tells a hit: `Simulating …` of the
  Explorer (`_results`) and `Simulating the plan …` of the Overview (`runs.files_cached`) draw on a
  miss only, as a hit looked like a run.
- Below the caches of the process the cache on disk (`src/dagobert/cache.py`, owner 2026-10-16,
  issue #28): `data/.cache`, one `.npz` per entry, so the pages after a restart show at once. It
  keeps a run at `runs.PATHS` (`cached_run`, `cached`: a hit on disk fills the process cache, so
  `Simulating …` stays off; the worker writes it, `cache.made`, about 30 ms at 500 paths; a run of
  other paths stays in memory, 10 times the room at 5000), the `fixed` run of the files
  (`fixed.result`) and a baseline of a revision (`cache.kept_run`), and every answer of
  `runs.answers` (`SENSITIVITY`, `SEEK`, `PLAN_SEEK`; a plan without the dial as None; a seek also
  by its dial, `outlook._stored` too: `SEEKS` names the dial of a button, a page that the engine
  code leaves out). Each through `cache.kept`: named as it starts, a run in its worker (not as it
  went into the queue, where a save gave the result of the new inputs the name of the old, which an
  undo back to them found), written only when the name still holds after it, so a save while it runs
  leaves it unnamed (a save and its undo within one run slip past). The name (`cache.key`) hashes
  the kind, the engine code (`cache.code`, once per process: every module of the package but those
  of `ui/` and `report/`, every file of `data/` with the tax years, and `cache.libraries`: Python
  and every installed distribution with its version, as a new numpy draws other numbers and a new
  pydantic or YAML parser may read an input otherwise; all, so a new import cannot slip past, and a
  new Streamlit drops the entries too; not `locale/` nor `examples/`, so a page or a translation
  keeps the entries), the contents of `RUN_INPUTS` (`cache.digest`; not their times, so a restored
  file hits; hashed again, `_digest`, when a file changes its size or its mtime in ns, comes or
  goes: a file put back with an older time, `cp -p`, changes `run_stamp` too, the sum of the times),
  the `Options` without `data` and `out` (a moved folder keeps its entries), the scenario by its
  path in the data, the overrides and the other parts of the key that compare (a `Lever` and a
  `Dial` without their words). A file holds the arrays and one JSON text of the rest (`_plain`:
  dates, tuples, dicts of any key, the dataclasses of `cache.TYPES` by name), read by
  `np.load(allow_pickle=False)`: an import may bring the folder of another person, and a pickle runs
  code as it loads. A file that does not read (`cache.UNREAD`: torn, foreign, a pickle, a type or
  fields of no entry, a JSON text nested too deep, an array too large to hold) is a miss and goes,
  never an error; an array that claims a few GiB allocates them for a moment before the miss. A hit
  touches its file; a write evicts the least recently used files beyond `cache.BYTES`, 1 GiB (about
  50 runs at 500 paths), the newest kept. Every write goes through `files.atomic_write`; one that
  fails (`OSError`: a read-only folder on Windows, a full disk) keeps nothing, never an error on a
  page. Memory only (`cache.folder` is None): a data directory that `os.access` finds read-only, and
  `DAGOBERT_CACHE=memory`, which `dagobert app --data x.zip` sets (a copy to work on). `.cache` is
  no input: `is_tracked`, `schema.Tree`, the stamps and the export take none of it, an import keeps
  the one here and refuses a zip that holds one (`test_cache.test_the_cache_is_no_input`).
  `Clear cache` on the Data page (rule `series`) empties it and, by `runs.forget`, the runs, `fixed`
  runs, answers and baselines of the process; no revision. Measured on 2026-10-17 (example
  `engineer`, two scenarios, 500 paths, 8 workers, a desktop, load 8 to 12 on 16 CPUs; Playwright
  from `goto` to the first tile, to `Up to date` and to the first chart of the opened fold
  `What moves the result`): the first Overview after a restart 3.9 to 4.6 s before, 2.0 s after (0.9
  s on a warm server; the `fixed` run took 0.9 s of it); the first Explorer 1.6 s before, 1.1 s
  after, with the sensitivity of the first tab 25 to 32 s before, 2.5 s after.
- `src/dagobert/ui/figures.py`: the figures of the page (the comparison, the chance by age, the
  difference, the charts of each tab; not the sensitivity, which `answers` keeps) kept as their JSON
  for all sessions (`kept`, `st.cache_resource`, up to `FIGURES_BYTES`, 64 MiB, the least recently
  used out first, `runs.keep` by `len`): by the builder, its keyword arguments (`nominal`,
  `compact`), the language (the one process cache that holds words, rule `i18n`) and the keys of
  what it shows, `explorer.Ran.key` of each run (the key of `cached_run`, the label and `twin`,
  which a figure shows), in order for the comparison (its palette), A and B for the difference,
  `observed.totals` for the balance sheet (`history.csv` is no input of `run_stamp`). A hit draws
  the figure from its JSON (`plotly.io.from_json`, 5 ms a figure), a miss the figure that it built:
  a builder of `charts.figure` gives the same bytes from its JSON
  (`test_a_figure_gives_the_same_bytes_from_its_json`), so a revisit sends what the browser holds.
  The browser keeps an element of 10 kB or more for `global.maxCachedMessageAge` runs after it last
  drew it, and the server then sends its hash (rule `container`): 10, as the default of 2 lost the
  figures after two other pages. `Difference.of` (22 ms), the table and the sliders run each rerun.
- Reruns without an engine run, measured on 2026-10-17 (example `engineer`, two scenarios, 500
  paths; Chrome by Playwright cycling Cashflows, Explorer, Overview after two warm cycles, the
  median of 5 visits, alternated with main at the same load, 1 to 6 on 16 CPUs; server: the script
  with its garbage collection; browser: the main thread, CDP `TaskDuration`). Desktop: Overview 0.47
  to 0.15 s, browser 0.36 to 0.21 s; Cashflows 0.41 to 0.24 s (its grids, `tables.edit_table`, take
  most of the rest), browser 0.37 to 0.29 s; Explorer 0.55 to 0.17 s, 1.93 MB to 65 kB sent, browser
  1.09 to 0.71 s. Phone (412 px, the open tab only): Overview 0.45 to 0.14 s, browser 0.52 to 0.40
  s; Cashflows 0.38 to 0.22 s; Explorer 0.46 to 0.16 s, 796 to 64 kB, browser 0.93 to 0.71 s. Of it:
  YAML parses 75 to 160 a rerun, 0.13 to 0.28 s, to none (rule `problems`), `concrete_scenarios`
  (rule `store`), the collection after each script, 55 to 60 ms (rule `container`), the figures 13
  builds of 0.33 s to 13 hits of 0.07 s; a build from mappings 0.24 s for the 13 (`charts.figure`).
  Left in the Explorer revisit: the figures from JSON and through Streamlit (0.08 s), the sliders
  (0.04 s), `Difference.of`, the summary (0.03 s); the browser draws every chart again
  (`Plotly.react`), with or without their bytes.
- `runs.baseline`, the plan of a day of `Records against the plan` and the Flows comparison: while
  no revision after it changed a path of `cache.RUN_INPUTS` (`revisions.changed_after`;
  `datadir.open` keeps the files at the head) the run of the files (`files_run`, `fixed.result`),
  else `at_revision` in a temporary directory (`_baseline`, `st.cache_resource` by revision, below
  it the disk, `cache.kept_run`): about 1.1 s less on the first Overview after a restart. The tiles
  ran `files_run` before, so it is a hit.
- `src/dagobert/ui/outlook.py`: the plan on the Overview, `plan` (tiles, spending and work seek) and
  `on_track`. The tiles take the explorer's cached run (`runs.files_run`, the key of `runs.options`
  with no overrides), so an explorer opened with the same scenario shows at once; a miss waits in
  the pool under `Simulating the plan …`, drawn once (`runs.files_cached`). The seek runs in the
  explorer's pool (`runs.seek`) under a progress bar per round (`runs.tick`, also in the explorer);
  `runs.keep` bounds each kind of `runs.answers` at `runs.KEPT`. The page fills `plan` into an
  `st.empty` below the tiles as its last step, so the rest of the page draws before the run, then
  its what-ifs into the one after it (`overview._whatifs`, rule `whatifs`): `files_run` of each
  compared scenario in turn, in the pool as the Explorer runs its scenarios, so `Compare` opens the
  Explorer on cached runs. A step writes plan files: the next Overview runs the plan and every
  what-if again (`run_stamp`).
