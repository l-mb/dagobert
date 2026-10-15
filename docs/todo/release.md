# Public release

Release Dagobert publicly so that others can deploy it themselves from the published container
image. Each item is a file `docs/todo/release-<topic>.md`, numbered R7 to R21. R7 to R19 are
done.

## Decisions (2026-10-12)

- Scope: every item below ships before the first public release. A local container runs on a
  local data directory from R8 on. The mobile device check needs a phone on a deployed container.
- Repositories: work happens in a private development repository. The release is a new public
  repository with one squashed commit (R20).
- No git in the image: revision files in the data directory replace git (R10).
- External data: shipped only where the terms allow it. Everything else is fetched only on an
  explicit user action and stays in the data directory (R11).
- ETF prices: the justETF AGB (§3.1, 2025-06-18) forbid "Programme zur automatisierten
  Kursabfrage", so the fetch goes, also as a button. Prices come from a CSV import and from
  price points entered by hand, also past ones (R11).
- Shiller: dropped (no licence, S&P 500 in USD, only a fallback without MSCI data).
- TODOs: `docs/todo/` files until the release, then issues of the public repository. GitHub
  cannot move an issue from a private to a public repository.
- Inputs: edited in the web UI. Local work runs a checkout of the code on an export (R14).
- Audience: German tax rules, English UI. i18n (German first) is future work if there is
  interest. Superseded on 2026-10-13: the pages and the report speak German too (rule `i18n`;
  the examples stay English, todo `german-example`).
- Image: maintained, secure and stable first, size last. amd64 now, arm64 possible later
  without changes (R8).
- Versions: semantic versioning from `0.1.0`, the version of `pyproject.toml`. A release tag
  is `v<version>`.

## Design decisions (2026-10-12)

The design drafts behind these are local, in `tmp/release/` (`r9-r14-data-layer.md`,
`r11-external-data.md`, `r13-editor.md`, `r15-gold-bitcoin.md`, `container/`).

- Data layer: the selectors of On track, Changes since and Flows list one entry per local day;
  the Flows comparison gets a select of days and opens before the newest day with a plan change.
  Revisions are plain copies (a `thin` command later). `dagobert app --data x.zip` unpacks next
  to the zip into `x/`. `dagobert run` on an old schema migrates and writes back, like the app.
  An import with conflicts asks per file (a row-level merge is a later item). Revisions inside
  an imported zip are ignored when the target has inputs. An edit outside the app is recorded
  as `outside the app`, without a notice. Days follow the time zone of the browser. Undo is a
  later item.
- External data: no GENESIS calls (the API needs an account; Bundesbank BBDP1 carries the same
  VPI). The CPI ships from 1962-01 (West Germany, then Germany). Prices in another currency are
  refused. The Data page opens a new navigation section `Setup`, which the editors join. A
  maintainer script outside the package refreshes the shipped files (no openpyxl at run time).
  `--msci` goes: an equity series comes in through a CSV import on the Data page and
  `dagobert series import`.
- Gold and Bitcoin: a switch `crypto_capital_from` for the BMF draft (Bitcoin bought after 2026
  under §20), off until it is law. Gold before 1999 converts with the Bundesbank USD/DEM rate.
  Deficits sell gold and crypto after equity. The engine buys them only through `buy` events.
  `fixed` keeps the mean; crypto defaults must be conservative, and crypto is revisited later.
  `historical` draws Bitcoin conditionally. `isin` becomes `security` through an R9 migration,
  gold counts in troy ounces (`XAU`). Gold notes without backing take `tax: capital` (§20);
  funds of gold or Bitcoin stay out. Kinds `gold` and `crypto`, return classes `gold` and
  `bitcoin`. Staking, gold lending and the loss carryback stay out.
- Editor: the first editor save writes a file through one `ruamel.yaml` dump (the layout changes
  once, comments stay). Shares and rates take percent everywhere, grids too (`2.5` is 2.5%). A
  scenario rename renames the file and rewrites `extends` and `app.yaml`, and R10 records it.
  Deleting a scenario that others extend is refused with the children named. `start` is read only,
  with a link to the roll forward. `app.yaml` holds the default scenarios only. `scale` is edited in
  scenario overrides only. `tax.church` stays in the model, hidden in the editor (until the church
  tax of 2026-10-13, which uses it and shows it). A child drops an inherited event or phase with
  `drop: [<id>]`. Asset ids and stream names are locked in the grids (a rename with references is a
  later item). An unknown stream name in `set_stream` or `end_streams` is a model error for a
  concrete scenario. A correction of `history.csv` is a later item.
- Container: Python 3.14 for local work, CI and the image (`.python-version`). certifi
  (MPL-2.0) is allowed. Dependabot updates uv, the Docker digest and the Actions. The root
  `.streamlit/config.toml` stays for the local server; the image sets `STREAMLIT_*` defaults.
  No health route through the proxy: the container's own health check suffices. The image user
  is UID 10001; compose runs it as the host user so a local data directory stays writable.

## Simple mode (2026-10-14)

The draft is local: `tmp/release/design-simple-mode.md`. Where these differ from it, these win.

- A key of `assumptions.yaml` at the default of its field (`children: 0`, `alleinerziehend:
  false`, `relatives: {}`) does not count as used: it acts like an absent key, so it locks no
  feature, and its field hides in simple mode while it holds the default. The draft said
  "present means chosen, also at the default value". An override of a scenario still counts at a
  default: it overrides the value of its parent (rule `mode`).

## Order

Each item names what it needs. Items in one cell do not depend on each other and can run in
parallel worktrees.

| Phase | Items |
|---|---|
| 1 Local container | R7 serve options; then R8 Dockerfile |
| 2 Data layer | R9 schema version; then R10 revision files, R11 external data; then R12 save conflicts |
| 3 Features | R13 editor, R14 import and export, R15 gold and Bitcoin |
| 4 Release preparation | R17 examples; then R16 first run, R18 docs and licence |
| 5 Release | R19 release audit; then R20 public repository; then R21 deploy |

Phase 1, R9 and the R11 units U1 (series core) and U4 (prices) can run in parallel:
the R11 draft shows that neither needs R9.

## Future

- German copies of the examples and of the empty plan (todo `german-example`); the pages and the
  report speak German since 2026-10-13 (rule `i18n`).
- Tax years after 2026.
