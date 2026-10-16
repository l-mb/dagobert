# CLAUDE.md

Guidance for Claude Code in this repository.

## Project

Dagobert projects personal wealth over a lifetime under German tax rules. Inputs are YAML
files in `data/`, outputs are an HTML report in `out/` and a console summary. `data/` is
gitignored: the code repository holds no inputs. Development uses a local copy in `data/` or
`DAGOBERT_DATA`. Tests never read it.

## Where to document what

- This file: what every change needs (commands, checks, tests, rules for every change) and one
  layout line per module, at most 180 lines. Brackets name the rules in `.claude/rules/` that hold
  the details. A new detail goes there, with at most a summary line here.
- `.claude/rules/<topic>.md`: the rules of one area, with their code names and legal citations.
  Its `paths:` name the source files and their tests: it loads when you read or edit one of them.
  Write into the rule whose `paths:` cover the code that it constrains: the engine into `engine`,
  the tax and SV law into `tax`, a page into the rule of its module (the table in rule `ui`). A
  new module goes into the `paths:` of a rule and gets a layout line here. At most 200 lines per
  rule: split it by files. No `@` imports: they load at once. A rule without `paths:`, or whose
  frontmatter does not parse, loads in every session.
- `.claude/skills/app-check/SKILL.md`: how to run the app and take screenshots for a check.
- `docs/manual/`: the user guide in plain English, a page per app page, `models.md` and
  `configuration.md` (the input files: `model/` is the authority, change both together).
- `docs/install/`: an install guide per system (Windows, macOS) and a server, plain English.
- Planned work: the issues of `l-mb/dagobert` (`gh issue list`). Deferred work becomes an issue
  that the owner opens; the commit that does the work closes it (`Closes #<n>`).
- A new, moved or renamed file: update every `paths:` that names it
  (`grep -rn '<path>' .claude/rules`), then run `uv run python scripts/rules-check`: it checks
  the rules and the limits, also in the hook and in CI.
- Read a file before any edit, also before a shell edit (`sed -i`, a script): its rules load only
  when Read, Edit or Write touches it or `cat` or `head` shows it alone, not through Grep or Glob.

## Commands

- `uv sync` installs the environment.
- `uv run dagobert run data/scenarios/*.yaml` simulates the scenarios and writes the
  report. Options with defaults:
  - `--data data`: input directory, or an export zip [transfer]. `--out out`: output directory.
  - `--model montecarlo`: `fixed`, `montecarlo` or `historical` (needs the equity series, see
    `series`). `--paths 5000` and `--seed 42` for the return provider.
  - `--mortality/--no-mortality`: survival overlay from the life table.
  - `--nominal`: nominal euros, else euros of the simulation start, each path deflated by its own
    consumer prices. `--lang en` (`DAGOBERT_LANG`): `de` writes the report in German [i18n].

  Like `export`, `import`, `prices import`, `series fetch|import` and the app, it first brings the
  data directory to the current schema and writes it back as one revision (`datadir.open`). Inputs
  that do not load end it with one line per problem on stderr, `file:line: key.path: message`
  (`problems.InputError`), and exit code 1, so does `historical` without the equity series.

- `uv run dagobert app` opens the Streamlit app in the browser [ui; options: container], never
  for a check (skill `app-check`). `export` and `import` move the inputs as a zip [transfer].
- `uv run dagobert prices import SECURITY FILE` merges a downloaded price history into
  `data/prices/<SECURITY>.csv` and records the market values [prices]; `trades import ASSET FILE`
  adds the new buys and sales of a broker CSV to the trades of an asset [tracking].
- `uv run dagobert series list|fetch [NAME...]|import msci-world FILE` lists the external
  series, fetches the months they lack (only on this command or the button of the Data page)
  and imports an equity history into `data/series/`; maintainers refresh the shipped series
  before a release with `uv run python scripts/refresh_shipped.py` [series].
- Quality gates: `uv run ruff check src tests scripts`, `uv run ruff format src tests scripts`,
  `uv run mypy`, `uv run basedpyright`, `uv run pytest`. All must be clean before you stop.
- `uv run pre-commit install` once per clone. A commit runs gitleaks, `scripts/pii-check`,
  `scripts/rules-check`, `scripts/i18n check` [i18n], and with Python changes ruff, mypy and
  basedpyright, not pytest. When ruff changes a file, the commit stops: add the file again and
  commit. Fix a failed hook, never skip it with `--no-verify` [tooling].
- `docker build -t dagobert .` builds the image, `compose.yaml` runs it [container]. CI runs the
  gates, gitleaks and the image checks, `release.yml` publishes a tag [tooling].

## Checks

- A change under `src/dagobert/ui/` is done when the skill `app-check` ran it as a desktop and
  as a phone, a module of `i18n_check.TRANSLATED` in English and in German (`?lang=de`).
- A change of `src/dagobert/report/` or of a figure is done when the check of rule `charts` ran.
- A change of the engine, the tax rules, the ledger or `budget.py` needs the check of rule `engine`.
- A change of the image, `compose.yaml` or the `Caddyfile` is done when the check of the rule
  `container` ran.
- Every Chrome start needs `--password-store=basic`. Without it Chrome asks the Secret
  Service for its keyring, and a password manager may pop up a confirmation.
- Write temporary outputs to `tmp/` (for example `--out tmp/out-hist`), never next to `out/`.

## Testing

- `tests/test_golden.py` runs `rich_plan` (salary, bonus, ALG1 with Sperrzeit and course, severance
  with a bAV part, a sale repaying a loan, term deposit, bAV, Altersvorsorgedepot, a business,
  pension, allocation, inflation; PKV, then GKV) and compares its yearly totals, ledger groups and
  markers with a snapshot. The ledger adds up to the engine totals, also of a GKV plan. A feature
  that the plan does not reach goes into `rich_plan`, not into a new bookkeeping test.
- A unit test is for a legal rule (an amount the law defines) or an edge case the rich plan
  cannot show. Write engine tests as a relation between runs (with and without X, lower,
  equal) instead of totals derived by hand. Merge similar cases with `parametrize`.
- Do not assert private details: widget keys, counts of kinds, tuple shapes, private helpers.
  The UI is tested through its pure functions and one render per page, as a desktop and as a
  phone (`test_pages_render`: `at.query_params["mobile"] = "1"`, AppTest sends no user agent).
- `tests/builders.py` holds the small-plan helpers (`plan`, `assumptions`, `zero_returns`,
  `phases`). While you work, run the affected test files. Run the whole suite before a
  commit: about 15 s on every core (pytest-xdist; `-n0` for a debugger, `--snapshot-update`).

## Rules for every change

- Use a dataclass for option bundles (see `runner.Options`). Typer commands take keyword-only
  options after `*` to satisfy ruff's argument limits.
- Money shows in one format everywhere, `1.234.567 €`, and charts and tables show euros of the
  simulation start by default [money].
- The phone (412 x 915 CSS px, touch only) uses every page, and the desktop keeps its look [ui].
- A save passes the save guard [save-guard], is one revision [revisions], checks conflicts [grids].
- The Flows page and the rows of the run on the Cashflows page read the ledger and never
  re-derive engine rules [ledger].
- Every random draw has a generator of its own purpose [engine].
- A model change needs a matching update in the YAML inputs and the examples, the tests and
  `docs/manual/configuration.md`, and a migration when inputs do not pass [migrations, examples].

## Layout

- `src/dagobert/model/`: pydantic inputs [persistence, bav, plan, harvest, disability, children]:
  `base.py` field units (`units`), `months.py` month arithmetic, `assets.py` (`Loan.step`),
  `streams.py`, `events.py`, `taxes.py`, `assumptions.py`, `plan.py` scenario, `app.yaml`, `Plan`.
- `src/dagobert/loader.py`: YAML loading, `extends` composition, `overrides` merge [persistence].
- `src/dagobert/overrides.py`: each override path of a scenario with its value and source,
  edits of a file's own overrides, the rows of `shift`, `events`, `assets` [persistence].
- `src/dagobert/problems.py`: `InputError`, one `Problem` per error, the reads [problems].
  `references.py`: who refers to what in the inputs, `rename.py` renames by it [references].
- `src/dagobert/schema.py`, `datadir.py`: the schema version and its migrations, `open`, which
  brings a data directory to it [migrations], a start [first-run]. `transfer.py`: zips [transfer].
- `src/dagobert/store.py`: writes the YAML inputs with `ruamel.yaml`, `yamlcomments.py` its
  comments, `textedit.py` as text, `scenariofiles.py` scenario file actions [store, revisions].
- `src/dagobert/revisions.py`: the revision store, the one writer of the inputs: `write` under the
  lock of the data directory, one revision per write, the inputs at a time, for the plan
  comparisons, Changes since and the Flows comparison [revisions].
- `src/dagobert/files.py`: `atomic_write` (synced temp file, `os.replace`) under `revisions.write`;
  `yaml()`, `dump()`: the YAML of the store; `read_csv`: the CSV inputs [revisions].
- `src/dagobert/rollforward.py`: moves `start` to a later month [rollforward].
- `src/dagobert/engine/`: monthly path simulation [engine, tax, ledger, bav, harvest, spending,
  disability, children]: `simulation.py` month loop, `core.py` setup, helpers, `state.py`,
  `income.py` streams, `portfolio.py` holdings and sales, `events.py`, `settlement.py` December
  settlement, `profit.py` [self-employment], `alg1.py` the claim to ALG1 [alg1], `health.py`
  [gkv]. Also `holdings.py` gold, crypto pools, `carry.py` values from `asof`, `result.py`
  `RunResult`, `Ledger` [money].
- `src/dagobert/tax.py`, `sv.py` (SV): array functions, a year a file in `src/dagobert/data/tax/`
  [tax, tax-options, bav, gkv, rental, deductions, harvest, disability, children, alg1].
- `src/dagobert/returns.py`: the return providers [returns]; `mortality.py`: the survival curve of
  the Destatis life table, which `runner.Options.run_one` loads [engine].
- `src/dagobert/series.py`: the registry of the external series, their reads, the fetch and the
  import, the chained consumer prices, the dollar series (gold, Bitcoin) in euros [series].
- `src/dagobert/budget.py`: the `Budget` of a stretch of months of the ledger [ledger].
- `src/dagobert/cashplan.py`: the cashflow plan on raw YAML rows [cashflows, disability].
- `src/dagobert/sensitivity.py`, `anatomy.py`, `difference.py`, `goalseek.py`: the sensitivity run,
  the failure anatomy, two runs path by path, the goal seek [analyses, goalseek, disability].
- `src/dagobert/history.py`: `history.csv` and the observed values per month, `lots.py` replays the
  `trades` of an asset into lots and sales, `tradeimport.py` adds a broker CSV [tracking].
- `src/dagobert/prices.py`: the price files and the series of XAU and BTC, `market_value` of
  lots, `record`. `csvimport.py`: a downloaded table of dated values [prices].
- `src/dagobert/actuals.py`: `actuals.csv` [spend].
- `src/dagobert/cli.py`: the commands, the options of `dagobert app` [container, money];
  `runner.py`: `Options` and the runs, which the explorer's workers unpickle [money].
- `src/dagobert/i18n.py`: `_()`, the language of a session; `i18n_check.py` checks `locale/` [i18n].
- `src/dagobert/report/`: plotly HTML, rich table [charts, money]: `page.py`, `summary.py`
  [disability], `charts.py` shared parts, the others a figure each; `*.css`, `tabs.js` package data.
- `src/dagobert/money.py`: `format_eur` and the grid formats, one euro format everywhere [money].
- `src/dagobert/ui/`: Streamlit pages [ui, money]: `main.py` the entry script, `__init__.py` shared
  helpers, `page.css` the style, `fixed.py` the cached `fixed` run, `mode.py` the mode and feature
  predicate [mode]. `tables.py`, `gridstate.py`, `gridcolumns.py` [grids], `guard.py`, `save.py`
  [save-guard], `rename.py` [references], `summary.py` [tracking], `pricing.py`, `csvcolumns.py`
  [prices], `fields.py`, `widgets.py`, `forms.py`, `formguard.py` [forms]. `outlook.py`: the plan on
  the Overview, `runs.py` its runs with the explorer, `sliders.py`, `knobs.py` its sliders,
  `seek.py` its goal seek [overview, explorer, explorer-runs]. Pages: `overview.py`, `snapshot.py`,
  `assets.py` (`tradeform.py`, `tradeimport.py`) [grids, tracking], `cashflows.py` (`bars.py`,
  `refusals.py`), `spend.py`, `explorer.py`, `flows.py`, `features.py` [mode], `data.py`,
  `assumptions.py`, `transfer.py`, `welcome.py`, `scenarios.py` (`fileactions.py`; tabs `phases.py`,
  `events.py`, `scenario_overrides.py`, `overridegrids.py`; `lineage.py`).
- `src/dagobert/data/`: shipped series, read only, see `SOURCES.md` there [series].
- `data/`: personal inputs; `tmp/`: scratch files; both gitignored. In `data/`: `history.csv`
  [tracking], `actuals.csv` [spend], `prices/` [prices], `revisions/` [revisions], `series/`: the
  fetched or imported months, `msci-world.csv` and `bitcoin.csv` never redistributed [series].
- `Dockerfile`, `.dockerignore`, `compose.yaml`, `Caddyfile`: the image and its examples, see
  Commands [container]. `.github/`: `workflows/ci.yml`, `release.yml`, `dependabot.yml` [tooling].
- `scripts/`: `pii-check`, `rules-check` [tooling], `i18n` [i18n], `refresh_shipped.py` [series].
  `.streamlit/config.toml`: the Streamlit options and themes of the app [ui, page-style, container].
- `src/dagobert/examples/`: made-up data directories for `dagobert init` and the README [examples].
