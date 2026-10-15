# R21 Deploy

Done: the guide `docs/install/self-hosting.md` (compose with a named `/data` volume, Caddy with
forward auth, Traefik and nginx notes, backup, restore, update, the way back, the German UI, an
expired login) and the memory of `compose.yaml` (rule `container`).

The guide names the published image, `ghcr.io/l-mb/dagobert:<version>`.

Left, after R20: run the guide on a server with that image through Docker Compose: its steps ran
as `docker run` with the same settings only (no compose plugin here).

Needs: R20. Part of the [public release](release.md).
