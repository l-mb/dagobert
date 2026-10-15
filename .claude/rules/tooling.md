---
paths:
  - ".pre-commit-config.yaml"
  - ".github/**"
  - "scripts/{pii-check,rules-check}"
  - "{pyproject.toml,uv.lock,.python-version,.gitattributes,vulture_whitelist.py}"
---

# Hooks and CI

- `uv run pre-commit install` installs the git hook of `.pre-commit-config.yaml`, once per clone.
  Every commit runs gitleaks on the staged changes and stops when they hold a secret, for example a
  token or a password. pre-commit builds gitleaks from source with Go and installs Go when it is
  missing. `scripts/pii-check` then stops a commit whose staged files hold a term of a list of
  personal data (names, the birth date, cities, banks, amounts): the list lives outside the
  repository, or it would leak itself, at `~/.config/dagobert/pii-terms` or in `DAGOBERT_PII_TERMS`.
  Without the list the hook passes with a note. `scripts/pii-check --all` scans every tracked file.
  Both skip `data/` and the shipped series `src/dagobert/data/*.csv`: raw public downloads, whose
  digits can match an amount of the list. They are verified against their source instead
  (`SOURCES.md`). Both skip the tax years `src/dagobert/data/tax/`: public values of the law with
  their sources, such as the Rentenwert (owner, 2026-10-14). Both skip `tests/__snapshots__/`:
  numbers the engine computes from the made-up plans of the tests, which the check reads, so a
  figure there matches the list only by chance (owner, 2026-10-14). Both skip `LICENSE` too: its
  copyright line names the owner, who publishes under their real name by choice. When the commit
  changes a Python file, `pyproject.toml` or `uv.lock`, the hook also runs `ruff check --fix` and
  `ruff format` on the staged Python files, then `mypy` and `basedpyright` on the whole project,
  through `uv run --locked` with the versions of `uv.lock`. A commit without Python files takes less
  than a second, a Python commit about 6 s. What else a commit needs: the root `CLAUDE.md`.
- `scripts/rules-check` checks `.claude/rules/`: each rule has frontmatter that parses with a
  `paths:` list, each glob (each alternative of a brace group) matches a tracked file, each
  tracked file under `src/`, `tests/`, `scripts/` and `.github/` matches a rule, no rule holds an
  `@` import, the root `CLAUDE.md` has at most 180 lines and a rule at most 200. The hook runs it
  on every commit, CI with the quality gates.
- `scripts/i18n check` checks the German catalogue against the code (rule `i18n`). The hook
  `i18n-check` runs it when a commit changes `src/` or the script, CI after `rules-check`. mypy
  takes both scripts without a suffix as modules of their names (`scripts_are_modules`): as
  `__main__` they clashed.
- `uvx vulture` lists dead code by `[tool.vulture]` of `pyproject.toml`: `src`, `scripts` and the
  two scripts without a suffix (a directory scan reads `*.py` only), skips the pydantic validators
  and the typer commands by their decorators, and `vulture_whitelist.py` names what a library reads
  by name (`model_config`, the attributes of ruamel.yaml, the `Land` options; `ignore_names` covers
  `schema`). No hook or CI runs it. Code that only tests use goes; a test sets up through a helper
  of `tests/builders.py`.
- CI (`.github/workflows/ci.yml`) runs the quality gates, with `ruff format --check`, a check that
  the `FROM python:` of the `Dockerfile` has the minor of `.python-version`, gitleaks over the whole
  history, and the image: build, a smoke test (read-only root, healthy) and Grype
  (`anchore/scan-action`), which fails on a high or critical finding with a fix; in a public
  repository a second scan uploads every finding as SARIF into code scanning (`security-events:
  write`, which `release.yml` grants the CI it calls: a called workflow gets no more). It runs on a
  push to `main`, on a pull request, weekly (new CVEs in the base image), by hand and for the
  release. uv takes the Python of `.python-version` (3.14, also for local work and the image);
  `requires-python` and ruff's `target-version` say 3.14 too: CI and the type checkers run no other
  (ruff then formats `except A, B:` without parentheses, PEP 758). The job `platforms` runs the
  tests alone (no linters, licences or image) on `windows-latest` and `macos-latest` (arm64),
  `fail-fast: false`, with the same uv: the guides `docs/install/windows.md` and `macos.md` rest on
  it, as the author uses neither system. It skips a tag (`github.ref_type`): a release publishes the
  Linux image, which `check` tests, and the commit of a tag passed it on `main`. A failure there is
  real: fix the code, or skip a test that the system cannot run with its reason (`sys.platform ==
  "win32"`: a directory has no read-only mode). Code that differs by system fakes it in a test
  (`files.WINDOWS`). Both test steps set `PYTHONWARNDEFAULTENCODING=1`, and `filterwarnings` in
  `pyproject.toml` turns an `EncodingWarning` of the package into an error: a text `open`,
  `read_text` or `write_text` of `dagobert` without `encoding="utf-8"` fails CI (Python 3.14 reads
  cp1252 on Windows; ruff's PLW1514 is in preview and misses `Path` methods). Locally the warning
  stays off unless the variable is set. `.gitattributes` checks every text file out with LF, also
  under `core.autocrlf` of Windows (the app writes LF, tests compare bytes), and the shipped series
  as they are (`-text`: `ecb_usd_eur.csv` is CRLF, as its source wrote it). The licence check syncs
  the runtime dependencies alone (`--no-dev --no-install-project`, the set of `uv export --no-dev`)
  into an environment under `RUNNER_TEMP` and runs `pip-licenses` (a dev dependency) on it with
  `--partial-match`: each package needs a permissive term (`--allow-only`, which passes on any one
  term) and none may hold a copyleft term (`--fail-on`, which also finds one inside an `AND`
  expression). It skips certifi (MPL-2.0, allowed by the release decisions). A new licence string
  that fails: read the licence, then extend a list. `release.yml` runs on a tag `v<version>`: the
  tag must be `v` plus the version of `pyproject.toml`, then all of CI, then the amd64 image goes to
  `ghcr.io/<repository>` (tags `0.1.0` and `0.1`, provenance and SBOM) with a GitHub attestation of
  its build (`actions/attest`, pushed to the registry; no storage record, which needs an
  organization). It runs in a public repository only: in the private one a tag publishes nothing.
  Dependabot (`.github/dependabot.yml`) raises every week `uv.lock` (one group; the bounds of
  `pyproject.toml` stay, `lockfile-only`, which raises the direct dependencies only: a transitive
  one gets no pull request, dependabot-core#14073), the image pins of the `Dockerfile` and
  `compose.yaml` (not a Python minor: it goes with `.python-version` by hand), the Actions (the SHA
  pins with their version comment) and the pre-commit hooks (gitleaks). It does not see the
  `docker://` gitleaks step (raise it with the hook) or the uv `version` of setup-uv (keep it at the
  uv of the `Dockerfile`).
