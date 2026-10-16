---
paths:
  - "{Dockerfile,.dockerignore,compose.yaml,Caddyfile}"
  - "docs/install/*.md"
  - "src/dagobert/cli.py"
  - "tests/test_cli.py"
---

# Image and deployment

CI builds and scans the image: rule `tooling`.

- Options of `dagobert app`, each also from a variable: `--data data` (`DAGOBERT_DATA`, also
  for every other command; an export zip unpacks beside it, rule `transfer`), `--address
  localhost` (`DAGOBERT_ADDRESS`, `0.0.0.0` in a
  container), `--port 8321` (`DAGOBERT_PORT`), `--browser/--no-browser` (`DAGOBERT_BROWSER`;
  without a browser no thread waits for a reconnecting tab), `--workers` (`DAGOBERT_WORKERS`,
  the processes of the explorer, see `runs.workers`). The fixed Streamlit settings (headless,
  no usage statistics, toolbar `viewer`, the session lifetime, the upload limit
  `transfer.UPLOAD_MB`, no file watcher: its `Source file changed` banner covered Save in the
  header, no fast reruns: a rerun waits for the next Streamlit call of the running script, else each
  quick slider move started a thread whose engine runs piled up, the accent of the theme, rule `ui`)
  are `os.environ.setdefault`s (`cli.STREAMLIT_ENV`, the same but the watcher in
  `.streamlit/config.toml` for a server started by hand, a test holds them equal), so a
  `STREAMLIT_*` variable of a deployment wins; only port and address are flags. The server refuses
  an upload above `server.maxUploadSize` whatever `st.file_uploader(max_upload_size=…)` says, so the
  setting must fit every export. Every other Streamlit setting is a plain `STREAMLIT_*` variable,
  for a proxy `STREAMLIT_SERVER_ALLOWED_HOSTS` (the public host name: the WebSocket check then
  refuses another Host, against DNS rebinding) and `STREAMLIT_SERVER_BASE_URL_PATH` (a sub path; the
  health route moves below it). CORS and XSRF protection stay on: through a proxy every request
  is same-origin. One user per instance: the app has no login and no user model,
  `st.cache_resource` shares the runs, the worker pool and the sensitivity results between all
  sessions, and all sessions write the same files. Each person needs an instance and a data
  directory of their own, and any address but localhost needs a proxy that authenticates.
- `docker build -t dagobert .` builds the image (`Dockerfile`): the official
  `python:<version>-slim-trixie` of `.python-version`, tag and digest pinned (also the uv image,
  as a stage, so that Dependabot sees it). A build stage installs the locked runtime
  dependencies with uv and compiles the bytecode; the final stage holds Python and the venv
  only: no uv, no source, no git (the comparisons read `revisions/` of the data directory). It
  runs as UID 10001 with `VOLUME /data`, `WORKDIR /data` and
  `DAGOBERT_DATA=/data` (`dagobert run scenarios/x.yaml` writes `/data/out`),
  `DAGOBERT_ADDRESS=0.0.0.0`, no browser, `STREAMLIT_SERVER_FILE_WATCHER_TYPE=none` and
  `STREAMLIT_LOGGER_HIDE_WELCOME_MESSAGE=true` (without it Streamlit asks
  `checkip.amazonaws.com` for the external address at every start on a wildcard address) and
  `GLIBC_TUNABLES=glibc.malloc.mmap_threshold=1048576`: glibc maps a block of 1 MiB or more on
  its own and gives it back when it is freed. By default the threshold rises up to 32 MiB with the
  first freed block, so the freed `(paths, months)` arrays of the runs and the charts stayed in the
  arenas of the script threads (measured on the host: the main process 1.6 GB, of which 0.57 GB
  free in the arenas, 1.15 GB after a `malloc_trim`; a cap of two arenas kept more). The cost is
  about 6% per engine run (2.0 s to 2.1 s at 5000 paths). A server started by hand
  (`dagobert app`, skill `app-check`) lacks it. The
  entry point is `dagobert`, the command `app`; a glob needs `--entrypoint sh`. The
  `HEALTHCHECK` asks `/_stcore/health` on `DAGOBERT_PORT` below
  `STREAMLIT_SERVER_BASE_URL_PATH`, with Python (slim has no curl). A read-only root works: the
  app writes only `/data` (also the fetched series, `/data/series`, and up to 1 GiB of results,
  `/data/.cache`: rule `explorer-runs`), `/tmp` (a tmpfs) and `/dev/shm` (the worker pool).
  `.dockerignore` is an allow list (`pyproject.toml`, `uv.lock`, `src/`), so no data reaches a
  layer; the examples are package data under `src/`. An empty `/data` (the anonymous volume, an
  empty bind mount) opens the page `Start a plan` (rule `first-run`); `docker compose run --rm
  dagobert init --example` starts one on the command line. No architecture in the file: `docker
  buildx --platform linux/arm64` works as is. The image is about 640 MB.
- `compose.yaml` runs the image locally as the owner of the data directory
  (`DAGOBERT_USER=$(id -u):$(id -g) docker compose up -d`; `DAGOBERT_DATA_DIR`, default
  `./data`; bash keeps `UID` read-only and does not export it): `atomic_write` replaces a file by a
  new one, which the user of the container owns (in the mode of the old one). Read-only root,
  `init` (reaps the workers), `cap_drop: ALL`, 2 workers in 5 GB with `memswap_limit` the same
  (without it the container may use as much swap again), on `127.0.0.1:8321` only. A missing
  bind source is made by Docker for root, which the user cannot write: the README makes `data`
  first.
  A host with SELinux needs `:z` on the bind mounts (`:Z` locks out a `docker compose run` beside
  the app); the `Caddyfile` mount is `:ro,z`. The profile `server` adds Caddy with the example
  `Caddyfile` (placeholders): `forward_auth` on every route, the health route too (the container
  checks its own health), the Host header unchanged (the WebSocket check compares it with Origin),
  `stream_close_delay`. Caddy 2.11.7 or later.
- Memory, measured on 2026-10-14 in the image on a copy of the example `engineer` with its two
  default scenarios (65 years) and `DAGOBERT_WORKERS=2`, as the cgroup's `memory.peak` (`docker
  stats` shows a few percent less: it drops inactive file cache) and `memory.current`, the split
  by `docker top`: the idle app 0.1 GB; the Explorer at 500 paths with the sensitivity 0.5 GB; at
  5000 paths with the sensitivity of both tabs and a goal seek 2.1 GB (the main process 0.7 GB,
  each worker 0.75 GB while it holds a run, 0.1 GB idle); each slider move at 5000 paths adds the
  two runs of its position to the main process (`runs.cached_run`, 200 MiB a run) up to
  `runs.RUNS_BYTES`, 1 GiB: 2.7 GB after 12 quick moves and the full sensitivity of the last; four
  further moves, each to its end, kept the peak at 2.7 GB and `memory.current` at 1.3 GB (the main
  process 1.2 GB); a second session at 5000 paths that moved another slider at the same time as
  the first, twice, 3.2 GB (one run in the making at a time, the workers shared); the main process
  at idle after it 1.06 GB. Since 2026-10-16 the workers make the two runs of a position too (rule
  `explorer-runs`): the main process makes no run, it takes the results one at a time (a result
  and its pickle, 400 MB at 5000 paths, while it arrives), and at most `DAGOBERT_WORKERS` runs are
  in the making. Measured so in the image on 2026-10-16 (two sessions at 5000 paths, six quick
  moves of each at the same time, four more each to its end, then the sensitivity of one for 60 s
  while the other moved twice): a peak of 3.19 GB, in the quick moves (the main process 1.74 GB),
  0.7 GB a worker that holds a run, 1.4 GB at idle after it (the main process 1.28 GB). A worker
  killed for its memory breaks the pool, which the next run makes anew (rule `explorer-runs`).
  Before: with 16 entries and fast reruns 6.4 GB, and a run of the measure 8 GB, OOM. `dagobert
  run` of the seven scenarios at 5000 paths 2.1 GB (0.8 GB for one,
  0.2 GB for each more; 2026-10-13), under the same `mem_limit` through `docker compose run`. So
  5 GB: 1.8 GB above two sessions that compute at the same time, for a longer plan (a run in the
  making and a worker grow with the months) or a third session; 3 GB hold the Explorer at 500 paths
  and the report. Above the limit (1.5 GB, 5000 paths) the container restarted, and the tab
  reloaded at 500 paths without an error.
- `docs/install/self-hosting.md`: the guide for a server (plain English). Its own compose file:
  the published image at a version tag (`ghcr.io/l-mb/dagobert:<version>`), a named
  volume on `/data` (it takes the owner 10001 of the image's `/data`, so no `user:`), no `ports`,
  `STREAMLIT_SERVER_ALLOWED_HOSTS`, the memory above, Caddy; the `Caddyfile` without comments
  (both checked: the compose schema, `caddy adapt --validate`); Traefik and nginx in words (Traefik
  passes WebSockets and the Host, `passHostHeader`, by default, doc.traefik.io; nginx needs the
  WebSocket headers and `Host $host`: its default `$proxy_host` fails the Origin check;
  Streamlit pings every 30 s, within the 60 s of `proxy_read_timeout`). The volume holds
  `.cache`, the results kept over a restart (rule `explorer-runs`), up to 1 GiB. Backup and
  restore with the app stopped, `tar` to stdout through `docker compose run --rm -T --entrypoint
  tar` as the image user (no root-owned file on the host; slim has tar and gzip), without
  `.cache` (`--exclude=./.cache`, GNU tar: the app computes it again), into an empty volume. The
  update with a backup first, the migration at the first page (`datadir.open`), the way back
  (`SchemaError` names the newer schema: restore the backup). The language switch. An expired
  login is the proxy's concern (owner decision 2026-10-13): one sentence in the guide. The Caddy
  image has tag and digest like `compose.yaml`; the guide notes SELinux `:ro,z`. Its compose
  commands ran as `docker run` with the same settings: no compose plugin on the author's host.
- Windows and macOS: the guides `docs/install/windows.md` and `macos.md` (plain English, a note
  first that the author did not test them, which invites issues and pull requests; the README links
  them from `Windows and macOS`). `uv tool install --python 3.14
  git+https://github.com/l-mb/dagobert` or a clone, `DAGOBERT_DATA` on a fixed folder outside
  OneDrive and iCloud, `dagobert app` (`webbrowser` opens the tab, the explorer's pool spawns as on
  Linux, `runs.pool`), or Docker Desktop with `compose.yaml` and without `DAGOBERT_USER` (`$(id -u)`
  is Linux; Docker Desktop shares the folder). CI runs the tests there (job `platforms`, rule
  `tooling`), no one the app. PowerShell passes a `*` as it is, and Typer expands it on Windows
  (`windows_expand_args`), so `dagobert run scenarios\*.yaml` works. A change of a command, an
  option, the compose file, the `Caddyfile`, the Caddy image pin or the memory changes the guides
  too, `self-hosting.md` with them. A read-only folder on Windows passes `os.access`: the first
  write raises a plain `PermissionError`, which `cli.PROBLEMS` (`OSError`) end as one line, exit 1
  (`windows.md`).
- New files take the mode of the umask (`files.NEW_MODE`, rule `revisions`), so the README
  (`Privacy and access`), `macos.md` and the backup of `self-hosting.md` tell a shared machine to
  make the folder of the data private (`chmod 700`).

## Check

- For the image, build it and run it on the copy in `tmp/rt` like `compose.yaml` does, on a
  port of your own: `docker run -d --name <name> --init --read-only --tmpfs /tmp --cap-drop ALL
  --user <uid>:<gid> -e DAGOBERT_PORT=<port> -v <worktree>/tmp/rt:/data:z -p
  127.0.0.1:<port>:<port> dagobert`. It is `healthy` (`docker inspect`) after a few seconds;
  then take the Playwright screenshots as for the app. `docker exec` runs with umask 0000, so a
  directory it creates is open to everyone: write with `docker run` or `docker compose run`.
  hadolint and actionlint run as containers (`hadolint/hadolint`, `rhysd/actionlint` with
  `--user <uid>`: the files are 0600; outside a git checkout actionlint needs the files named).
