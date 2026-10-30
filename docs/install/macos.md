# Install Dagobert on macOS

The author of Dagobert uses Linux and did not test these steps on macOS. The automatic tests of
Dagobert run on macOS with Apple silicon, but nobody used the app there by hand. Please tell us
what happens when you follow this guide: open an issue or a pull request in the Dagobert
repository. A report that every step works as written helps as much as a correction.

This guide installs Dagobert with uv, a tool that installs Python programs. Dagobert then runs on
your Mac, and you use it in your browser. The last section shows an alternative: Dagobert in a
container of Docker Desktop.

## What you need

- macOS 12 (Monterey) or later, on a Mac with Apple silicon or with an Intel processor. The
  automatic tests do not run on an Intel Mac.
- Git, which uv uses to download Dagobert. If you do not have it, run `xcode-select --install` in
  Terminal. The command installs the Command Line Tools of Apple, which include Git.
- About 1 GB of free disk space for Python, Dagobert and its libraries.

## Install uv

1. Open Terminal. It is in the folder `Utilities` of your `Applications`.
2. Run the official installer of uv:

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. Close the Terminal window and open a new one, so that it finds the command `uv`.

## Install Dagobert

1. Install Dagobert as a command:

   ```sh
   uv tool install --python 3.14 git+https://github.com/l-mb/dagobert@v0.1.0
   ```

   uv downloads Python 3.14, Dagobert and its libraries. This takes a few minutes.
2. If uv says that its directory of commands is not on your `PATH`, run `uv tool update-shell`.
   Then open a new Terminal window.
3. Make sure that the command works:

   ```sh
   dagobert --help
   ```

## Choose a data directory

All your data stays in one folder, the data directory. Without a choice, Dagobert uses the folder
`data` in the folder where you start it. A fixed folder is easier: every start finds your data.

Do not use a folder in iCloud Drive, also not `Desktop` or `Documents` when iCloud keeps them. A
save locks the data directory and replaces files in it, and a sync service can block that. The
folder `Dagobert` in your home folder is a good choice.

Dagobert does not make its files private. A new file gets the permissions that the umask allows.
The umask is a setting of macOS that removes permissions from new files, and by default it lets
other users read them. If other people have an account on this Mac, make the folder private
before the first start:

```sh
mkdir -p ~/Dagobert && chmod 700 ~/Dagobert
```

1. Set the variable `DAGOBERT_DATA` to that folder for every new Terminal window. The default
   shell of macOS, zsh, reads the file `~/.zshrc` at its start:

   ```sh
   echo 'export DAGOBERT_DATA="$HOME/Dagobert"' >> ~/.zshrc
   ```

2. Open a new Terminal window. The variable applies to new windows only.

Dagobert makes the folder when it starts a plan. Each command also takes `--data <folder>` for
another data directory.

To fetch the prices of your securities from EODHD, put your key into a file in your user folder.
Then set the variable `EODHD_API_KEY_FILE` to that file in the same way. The
[user guide](../manual/snapshot.md#prices) explains the fetch.

## Start the app

1. Optional: start a plan from the simple example. Without this step, the app shows the page
   `Start a plan`, where you choose an example, the quick start or an import.

   ```sh
   dagobert init --example starter
   ```

2. Start the app:

   ```sh
   dagobert app
   ```

   The app opens a tab in your browser at <http://localhost:8321>. If no tab opens, open that
   address yourself.
3. If macOS asks whether Python can accept incoming network connections, select `Deny`. The app
   listens on this Mac only, so it needs no access from the network.
4. To stop the app, press Control-C in Terminal.

The [README](../../README.md) explains the first start and the examples. The
[user guide](../manual/index.md) explains each page of the app.

## Write a report

The command `dagobert run` computes scenarios, prints a summary and writes an HTML report:

```sh
cd "$DAGOBERT_DATA"
dagobert run scenarios/*.yaml
open out/index.html
```

The report is the file `out/index.html` in the data directory. The command `open` shows it in
your browser. For a report in German, add `--lang de` to `dagobert run`.

## Back up your data

An export is a zip file of your data directory. Make one in one of these ways:

- In the app, open the page `Export and import` in the section Setup. Turn on `Include change
  history`, and then download the export.
- In Terminal, run `dagobert export --revisions --out ~`. The command writes
  `dagobert-<revision>.zip` into your home folder.

A copy of the whole data directory is a backup too. Time Machine copies it with your home folder.
Stop the app before you copy the folder by hand. To restore an export, import it into an empty data
directory on the page `Start a plan`. The section
[Backup and local work](../../README.md#backup-and-local-work) of the README gives the details.

## Update Dagobert

1. Make a backup. A new version can convert the data directory to a new file format, which an
   older version cannot open.
2. Stop the app.
3. Update Dagobert. Replace `<version>` with the number of the new release, for example `0.1.1`.
   The releases are on <https://github.com/l-mb/dagobert/releases>:

   ```sh
   uv tool install --python 3.14 --force git+https://github.com/l-mb/dagobert@v<version>
   ```

4. Start the app again. If the file format changed, the app converts the data directory at its
   first start.

To remove Dagobert, run `uv tool uninstall dagobert`. The command keeps your data directory.

## Work on the code

If you want to change the code, use a clone of the repository instead of `uv tool install`:

```sh
git clone https://github.com/l-mb/dagobert dagobert
cd dagobert
uv sync
uv run dagobert app
```

In a clone, each command starts with `uv run`. To update the clone, run `git pull` and then
`uv sync`.

## Alternative: Docker Desktop

Docker Desktop runs Dagobert in a container, from the file `compose.yaml` of the repository. You
do not need uv for it. Docker Desktop is free for personal use. Read its license terms for other
uses.

1. Install Docker Desktop for Mac from <https://www.docker.com/products/docker-desktop/>, the
   version for your processor, and start it.
2. Clone the repository and go into its directory:

   ```sh
   git clone https://github.com/l-mb/dagobert dagobert
   cd dagobert
   ```

3. Make the data directory:

   ```sh
   mkdir data
   ```

4. Build the image and start the app:

   ```sh
   docker compose up -d --build
   ```

5. Open <http://localhost:8321> in your browser.

The quick start of the README sets `DAGOBERT_USER` to your user ID. That step is for Linux: leave
it out on macOS. Docker Desktop shares the folder with the container.

To use another data directory, make a file `.env` next to `compose.yaml` with a line such as
`DAGOBERT_DATA_DIR=/Users/<you>/Dagobert`. Run a command of Dagobert in the container with
`docker compose run --rm dagobert`, for example `docker compose run --rm dagobert init --example
starter`. To stop the app, run `docker compose down`. To update, run `git pull` and then
`docker compose up -d --build`.

This container runs on your computer only. To run Dagobert on a server with a login in front of
it, read [Run Dagobert on a server](self-hosting.md).
