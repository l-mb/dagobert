# Run Dagobert on a server

This guide runs Dagobert on a server of your own. Then you can open it from a phone and from
other computers. Dagobert runs in a container, an isolated process with its own files. Docker
Compose starts the container. Docker Compose is a tool that starts containers from one file. A
reverse proxy in front of Dagobert asks for a login before it passes a request on. A reverse proxy
is a web server that receives the requests from the internet and passes them on to the app.

This guide uses placeholders. Replace them with your values:

- `<version>` in `ghcr.io/l-mb/dagobert:<version>`: the version of the published image of Dagobert,
  for example `0.1`. The tag `0.1` always gives the newest release 0.1.x. The tag `0.1.0` gives that
  release only.
- `dagobert.example.com`: the host name of your server.
- `authelia:9091`: the address of your auth service.

## Before you start

The app has no login and no user accounts. Everybody who reaches the app sees and changes the same
data. So keep to these rules:

- Run one instance for each person: a container and a data volume of its own.
- Never publish the port of the app. The reverse proxy must be the only program that connects
  to it.
- Let only the owner of the instance through the login. A login that any user of your auth service
  can pass gives all of them the data.

## What you need

- A Linux server with Docker Engine and the Docker Compose plugin, on a processor of type amd64
  (x86-64). The image is published for amd64 only.
- Memory for Dagobert: up to 5 GB when the Explorer computes 5000 paths, and 3 GB when it stays
  at 500 paths. The Explorer is the page of Dagobert for what-if runs. A path is one possible
  future of the markets. The section [Memory and workers](#memory-and-workers) gives the
  measurements.
- A host name, for example `dagobert.example.com`, whose DNS record points to the server. The
  ports 80 and 443 of the server must be open to the internet, because Caddy gets the certificate
  for HTTPS from Let's Encrypt.
- An auth service for single sign-on that does forward authentication, for example Authelia or
  authentik. Forward authentication means that the proxy asks the auth service about each request
  before it passes the request on. This guide does not set up the auth service. Read its
  documentation for that.

## Make the configuration

Make a directory for the configuration on the server, for example `/srv/dagobert`. Put the two
files below into it.

The file `compose.yaml` starts Dagobert and Caddy:

```yaml
services:
  dagobert:
    image: ghcr.io/l-mb/dagobert:<version>
    init: true
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    environment:
      DAGOBERT_WORKERS: "2"
      STREAMLIT_SERVER_ALLOWED_HOSTS: "dagobert.example.com"
    volumes:
      - dagobert-data:/data
    mem_limit: 5g
    memswap_limit: 5g
    restart: unless-stopped

  caddy:
    image: caddy:2.11.7@sha256:f2a1290d0463aad60660d4ec134943f183ee2a5f6c3eb7bf32dd984f2f020772
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro,z
      - caddy-data:/data
      - caddy-config:/config
    restart: unless-stopped

volumes:
  dagobert-data:
  caddy-data:
  caddy-config:
```

The lines of the service `dagobert` do these things:

- `image` names the version of Dagobert. Do not use `latest`. With `latest`, every `docker
  compose pull` can update Dagobert, also when you made no backup before. A tag such as `0.1`
  follows the patch releases (0.1.1, 0.1.2). Use a full number, such as `0.1.0`, if you want no
  change before you edit the line.
- `dagobert-data:/data` keeps your data in a named volume, a storage area that Docker manages. The
  volume holds your inputs, your records, the revisions, the fetched series and the reports. A
  revision is a copy of each file that a save changed. The volume also holds the folder `.cache`,
  which keeps up to 1 GB of results of the Explorer and the Overview. With it, the pages show at
  once after a restart of the container. A new version of Dagobert computes them again.
- The service has no `user` line. The image user (UID 10001) owns the new volume and writes the
  files.
- `STREAMLIT_SERVER_ALLOWED_HOSTS` is the host name of your server. The app then refuses a
  connection for another host name, which protects against DNS rebinding (a foreign domain that
  points to your server).
- The service has no `ports`. Only the containers of this Compose project can connect to it.
- `read_only`, `cap_drop` and `no-new-privileges` remove rights that the app does not need. The app
  writes only to `/data`, `/tmp` and `/dev/shm`. The worker processes of the Explorer need
  `/dev/shm`, and Docker keeps it writable.
- `DAGOBERT_WORKERS`, `mem_limit` and `memswap_limit` set the processes of the Explorer and the
  memory. The section [Memory and workers](#memory-and-workers) explains them.

The `image` of Caddy names a version and a digest, a checksum of the image. Both make sure that
you always get the same image. Use Caddy 2.11.7 or a later version. Versions before 2.11.5 have a
fault in `forward_auth` (GHSA-6365-7ppr-5r92).

If your server uses SELinux, the `z` in `:ro,z` of the `Caddyfile` line lets Caddy read the file.
SELinux is a Linux security layer that blocks a container from files it does not own. Without
`z`, Caddy cannot read the `Caddyfile`. The named volumes need no `z`.

The file `Caddyfile` tells Caddy to ask the auth service about each request:

```caddyfile
dagobert.example.com {
	forward_auth authelia:9091 {
		uri /api/authz/forward-auth
		copy_headers Remote-User Remote-Groups Remote-Email Remote-Name
	}
	reverse_proxy dagobert:8321 {
		stream_close_delay 5m
	}
}
```

This example is for Authelia. For authentik, use `uri /outpost.goauthentik.io/auth/caddy` and the
headers that the documentation of authentik gives. Also add `reverse_proxy
/outpost.goauthentik.io/* <outpost>` before `forward_auth`.

These rules apply to the Caddyfile:

- Every request needs the login, also the health route of the app. The health check of the
  container runs inside the container and does not go through the proxy.
- Caddy passes WebSockets without more configuration. The app uses a WebSocket, a connection that
  stays open, for everything that you see and do on a page.
- Do not change the `Host` header with `header_up Host`. The app accepts the WebSocket only when
  the host in its `Origin` header is the same as the `Host` header.
- `stream_close_delay 5m` keeps open connections for 5 minutes when Caddy loads a changed
  configuration. Without it, every open page loses its connection at once.

Caddy must be able to connect to the auth service. If the auth service runs in another Compose
project, connect Caddy to the network of that project. The Docker documentation explains
networks in Compose.

## Start Dagobert

1. Go into the directory of the configuration:

   ```sh
   cd /srv/dagobert
   ```

2. Download the images:

   ```sh
   docker compose pull
   ```

3. Start the containers:

   ```sh
   docker compose up -d
   ```

4. Make sure that Dagobert runs. After a few seconds, `docker compose ps` shows `healthy` in the
   status of the service `dagobert`.
5. Open `https://dagobert.example.com` in your browser. The auth service shows its login page.
   After the login, Dagobert shows the page `Start a plan`.
6. Start from an example, from the quick start, or import an export of your plan from another
   instance. The section [The first start](../../README.md#the-first-start) of the README explains
   the three choices.

If Dagobert does not start, read its log with `docker compose logs dagobert`.

To serve Dagobert under a path, for example `https://example.com/dagobert`, set
`STREAMLIT_SERVER_BASE_URL_PATH: "dagobert"` in `environment`. The health check of the container
follows the path.

## Other reverse proxies

If you use another reverse proxy, such as Traefik or nginx, keep to the same rules:

- Every request goes through forward authentication.
- WebSockets pass through.
- The `Host` header of the browser goes to the app unchanged.

Traefik does this with the middleware `ForwardAuth` on the router of Dagobert. Traefik passes
WebSockets and the `Host` header by default.

nginx does forward authentication with the module `auth_request`. Read the guide of your auth
service for nginx. nginx does not pass WebSockets by default. In the `location` of Dagobert, set
`proxy_http_version 1.1`, `proxy_set_header Upgrade $http_upgrade` and `proxy_set_header Connection
"upgrade"`. Also set `proxy_set_header Host $host`. Without it, nginx sends the name of the
upstream server as `Host`, and the app refuses the WebSocket. The app sends a ping every 30
seconds, so the default `proxy_read_timeout` of 60 seconds keeps an idle page connected.

## When the login expires

The proxy handles the login and its expiry. Dagobert does not know about the login. When the login
expires, the proxy sends you to the login page of the auth service.

## Memory and workers

The Explorer computes the sensitivity, `What moves the result`, and the goal seek in worker
processes. `DAGOBERT_WORKERS` sets their number. Python sees all processors of the server, unless
a cpuset limits them. A cpuset is a list of processors that a container may use. So set
`DAGOBERT_WORKERS` to the number of processors that you give the container.

The memory depends on the number of paths that the Explorer computes. The Explorer starts with 500
paths, and its slider `Paths` goes up to 5000. The author measured the memory with the full example,
`engineer`, its two default scenarios and two workers:

- At 500 paths, Dagobert needs about 0.5 GB, also for `What moves the result`.
- At 5000 paths, the first run of the two scenarios needs about 2.1 GB. This includes `What moves
  the result` in the tabs of both scenarios and one goal seek. Each worker needs about 0.75 GB of
  it.
- At 5000 paths, each slider that you move adds two runs of about 0.2 GB each. Dagobert keeps
  runs up to 1 GB and drops the oldest first. The author moved a slider 16 times: 12 quick moves,
  then 4 moves that each waited for `What moves the result`. Dagobert needed at most 2.7 GB, and
  1.3 GB between the moves.
- A second device that computes at the same time needs little more, because the two devices share
  the runs and the workers. With two devices that each moved a slider at the same time, Dagobert
  needed at most 3.2 GB.
- A report of the command line, `dagobert run` with all seven scenarios at 5000 paths, needs about
  2.1 GB. `docker compose run` gives it the same `mem_limit`.

So the configuration of this guide sets 5 GB. The rest is for a plan that covers more years, or
for a third device. At 500 paths in the Explorer, 3 GB are enough. A report at 5000 paths also
fits (2.1 GB). More scenarios at a time need more memory.

`memswap_limit` the same as `mem_limit` stops the container from using swap. If Dagobert needs more
memory than `mem_limit`, the kernel stops a process of the container, and the container restarts.
The page then loads again with 500 paths. Edits that you did not save are lost. If that happens,
give the container more memory, use fewer paths, or use fewer workers.

## Make a backup

The backup is a copy of the whole data volume. Stop Dagobert before the copy, so that no save
changes the files during the copy.

The backup file holds all your data. Your shell makes it with the permissions that your umask
allows. The umask is a setting of the system that removes permissions from new files, and on most
servers it lets other users read them. If other people log in to the server, make the directory
of the configuration private before the first backup:

```sh
chmod 700 /srv/dagobert
```

1. Go into the directory of the configuration, `/srv/dagobert`.
2. Stop Dagobert:

   ```sh
   docker compose stop dagobert
   ```

3. Copy the volume into a file in the current directory. The command leaves out the folder
   `.cache`, because the app can compute its results again:

   ```sh
   docker compose run --rm -T --entrypoint tar dagobert -C /data --exclude=./.cache -czf - . > dagobert-backup.tar.gz
   ```

4. Start Dagobert again:

   ```sh
   docker compose start dagobert
   ```

5. Copy the file `dagobert-backup.tar.gz` to another computer. A backup on the same disk is lost
   together with the disk.

The page `Export and import` of the app also makes a backup: an export with `Include change
history`. The export holds the inputs, your records and the revisions. It does not hold the
fetched series, the reports and the folder `.cache`. You do not have to stop Dagobert for an
export.

## Restore a backup

A restore replaces all data of the instance with the backup.

1. Go into the directory of the configuration, `/srv/dagobert`.
2. Stop and remove the containers. The command keeps the volumes:

   ```sh
   docker compose down
   ```

3. Find the name of the data volume. Compose adds the name of the project, by default the name of
   the directory, for example `dagobert_dagobert-data`:

   ```sh
   docker volume ls
   ```

4. Remove the data volume. This deletes all data of the instance. Do this only when you have the
   backup:

   ```sh
   docker volume rm dagobert_dagobert-data
   ```

5. Copy the backup into a new volume. Compose makes the new volume:

   ```sh
   docker compose run --rm -T --entrypoint tar dagobert -C /data -xzf - < dagobert-backup.tar.gz
   ```

6. Start the containers:

   ```sh
   docker compose up -d
   ```

To restore an export zip instead, do the steps 1 to 4, and then start the containers. The empty
volume shows the page `Start a plan`, where `Import` under `An export` takes the zip.

## Update Dagobert

1. Read the release notes of the new version.
2. Make a backup, as the section [Make a backup](#make-a-backup) says. Keep this backup until you
   are sure that the new version works.
3. In `compose.yaml`, change the version in `image` to the new version.
4. Download the new image and start it:

   ```sh
   docker compose pull dagobert
   docker compose up -d
   ```

5. Open Dagobert. If the new version uses a new file format, it converts the data directory when
   you open the first page. The conversion is a revision with the source `migrate <old> → <new>
   (Dagobert <version>)`. A command in the container, such as `dagobert run`, also converts the
   data directory first.

## Go back to the previous version

1. In `compose.yaml`, change the version in `image` back to the previous version.
2. Start it:

   ```sh
   docker compose up -d
   ```

3. Open Dagobert. If the update converted the data directory, the previous version cannot read
   it. Every page then shows `The inputs do not load:` and the error `manifest.yaml: schema <n>,
   written by Dagobert <version>`.
4. If you see this error, restore the backup that you made before the update, as the section
   [Restore a backup](#restore-a-backup) says. The saves that you made with the new version are
   not in that backup.

## The app in German

The app shows its pages in English or in German. On the first visit, it uses the language of your
browser, and English if that is not German. To change the language, use the switch `Sprache ·
Language` at the end of the sidebar. A cookie in your browser keeps your choice, so each browser
can have its own language. The [user guide](../manual/index.md#language) lists the text that stays
in English.
