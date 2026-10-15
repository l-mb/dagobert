# R20 Public repository

`l-mb/dagobert` on GitHub. Done in the tree: the URL in the README, the install guides,
`compose.yaml` and `series.USER_AGENT` (`dagobert/<version> (+<URL>)`); in the workflows the
attestation of the image (`actions/attest`, pushed to GHCR) and the SARIF upload of the image scan
into code scanning, both for a public repository only (rule `tooling`).

Left, the maintainer's steps:
- Create the public repository with one squashed commit of the audited tree. Rescan that exact
  tree before the push.
- Never make the private repository public instead: its pull request refs, Actions logs,
  issues and packages would become public with it.
- The settings of the public repository: a ruleset on `main` (no force push, no deletion, the
  checks of CI), code scanning on, Dependabot alerts on, private vulnerability reporting on.
- The first version `0.1.0`: the tag `v0.1.0` runs `release.yml`; then make the GHCR package
  public (a new package is private) and link it to the repository.
- Turn `docs/todo/` into issues.
- The public repository becomes the development repository, and the private one is archived.
- Clone the public repository again, because its history is new, and copy a local `data/`
  over.

Part of the [public release](release.md).
