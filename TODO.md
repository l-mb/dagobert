# Planned work

One file per item in `docs/todo/`. The list below gives the order. When the work is committed,
delete its file and its line. Known engine gaps stay in `.claude/rules/tax.md`.

## Order

The public release comes first: its decisions and phases are in
[docs/todo/release.md](docs/todo/release.md), and each item names what it needs. The other
items follow; each file says what it waits for, if anything.

The target is a phone of 412 x 915 CSS px, landscape 915 x 412, touch only. The desktop keeps
its look and its widths. What CSS cannot do branches on `ui.is_mobile()` (the user agent,
`?mobile=1` for tests). Fixes that help both apply everywhere.

- [Public release](docs/todo/release.md) — decisions, phases and future work of the release
- [R20 Public repository](docs/todo/release-public-repository.md) — one squashed commit, the settings of the repository, the tag, issues
- [R21 Deploy](docs/todo/release-deploy.md) — after R20: run the server guide with the published image
- [Model and loader: small cleanups](docs/todo/model-cleanups.md) — `np.interp`, the error sourcing and the `extends` chain in one place, whole-month shifts, one migration in `datadir.open`, `written` with the holdings
- [Mobile leftovers: device check](docs/todo/mobile-leftovers-device-check.md) — check the phone fixes on a real phone: keypad, keyboard, taps, pull-to-refresh, session lifetime
- [German example](docs/todo/german-example.md) — `engineer` and the empty plan in German, if the owner asks
- [Stock loss carryforward](docs/todo/stock-loss-carryforward.md) — a start value of the loss pot as an input, once the BVerfG decides on §20 Abs. 6 S. 4 EStG
- [Flows: Monte Carlo variant](docs/todo/flows-monte-carlo-variant.md) — Flows over the paths around the median surplus, only if the fixed run is missed
- [Riester contracts before 2027](docs/todo/riester-contracts.md) — old Riester rules as an extension of the depot kind
- [Realize gains beside the loss pots](docs/todo/harvest-with-loss-pots.md) — the harvest room with the §20 and §10d pots, not off while they hold losses (owner: later)
- [Salary growth per phase](docs/todo/salary-growth-per-phase.md) — an independent growth lever for every phase with a salary or a profit (owner idea)
- [Elterngeld](docs/todo/elterngeld.md) — parental allowance by rule with its tax and insurance effects; waits for four review points
