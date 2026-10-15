# Install Dagobert on Windows

The author of Dagobert uses Linux and did not test these steps on Windows. The automatic tests of
Dagobert run on Windows, but nobody used the app there by hand. Please tell us what happens when
you follow this guide: open an issue or a pull request in the Dagobert repository. A report that
every step works as written helps as much as a correction.

This guide installs Dagobert with uv, a tool that installs Python programs. Dagobert then runs on
your computer, and you use it in your browser. The last section shows an alternative: Dagobert in
a container of Docker Desktop.

## What you need

- Windows 10 or Windows 11 on a PC with an Intel or AMD processor (x64). Some libraries of
  Dagobert have no ready build for Windows on Arm.
- Git, which uv uses to download Dagobert. If you do not have it, install Git for Windows from
  <https://git-scm.com/downloads/win>.
- About 1 GB of free disk space for Python, Dagobert and its libraries.

## Install uv

1. Open PowerShell from the Start menu.
2. Run the official installer of uv:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. Close PowerShell and open it again, so that it finds the command `uv`.

## Install Dagobert

1. Install Dagobert as a command:

   ```powershell
   uv tool install --python 3.14 git+https://github.com/l-mb/dagobert@v0.1.0
   ```

   uv downloads Python 3.14, Dagobert and its libraries. This takes a few minutes.
2. If uv says that its directory of commands is not on your `PATH`, run `uv tool update-shell`.
   Then close PowerShell and open it again.
3. Make sure that the command works:

   ```powershell
   dagobert --help
   ```

## Choose a data directory

All your data stays in one folder, the data directory. Without a choice, Dagobert uses the folder
`data` in the folder where you start it. A fixed folder is easier: every start finds your data.

Do not use a folder that OneDrive synchronizes, such as `Documents` or `Desktop` when OneDrive
backs them up. A save locks the data directory and replaces files in it, and a sync service can
block that. The folder `Dagobert` in your user folder is a good choice.

Dagobert must be able to write to the data directory. On Windows, Dagobert cannot find out in
advance that a folder does not let you write to it, for example a folder on a read-only drive or
a folder of another user. In such a folder, each command stops with the message
`[Errno 13] Permission denied` and the name of a file, and each page of the app stops with a
`PermissionError`. Use a folder in your user folder, where you can write.

1. Set the variable `DAGOBERT_DATA` to that folder:

   ```powershell
   setx DAGOBERT_DATA "$HOME\Dagobert"
   ```

2. Close PowerShell and open it again. The variable applies to new windows only.

Dagobert makes the folder when it starts a plan. Each command also takes `--data <folder>` for
another data directory.

## Start the app

1. Optional: start a plan from the simple example. Without this step, the app shows the page
   `Start a plan`, where you choose an example, the quick start or an import.

   ```powershell
   dagobert init --example starter
   ```

2. Start the app:

   ```powershell
   dagobert app
   ```

   The app opens a tab in your browser at <http://localhost:8321>. If no tab opens, open that
   address yourself.
3. If Windows Defender Firewall asks about Python, select `Cancel`. The app listens on this
   computer only, so it needs no access from the network.
4. To stop the app, press Ctrl+C in PowerShell.

The [README](../../README.md) explains the first start and the examples. The
[user guide](../manual/index.md) explains each page of the app.

## Write a report

The command `dagobert run` computes scenarios, prints a summary and writes an HTML report:

```powershell
cd $env:DAGOBERT_DATA
dagobert run scenarios\*.yaml
start out\index.html
```

The report is the file `out\index.html` in the data directory. The command `start` shows it in
your browser. For a report in German, add `--lang de` to `dagobert run`.

## Back up your data

An export is a zip file of your data directory. Make one in one of these ways:

- In the app, open the page `Export and import` in the section Setup. Turn on `Include change
  history`, and then download the export.
- In PowerShell, run `dagobert export --revisions --out $HOME`. The command writes
  `dagobert-<revision>.zip` into your user folder.

A copy of the whole data directory is a backup too. Stop the app before you copy it. To restore an
export, import it into an empty data directory on the page `Start a plan`. The section
[Backup and local work](../../README.md#backup-and-local-work) of the README gives the details.

## Update Dagobert

1. Make a backup. A new version can convert the data directory to a new file format, which an
   older version cannot open.
2. Stop the app.
3. Update Dagobert. Replace `<version>` with the number of the new release, for example `0.1.1`.
   The releases are on <https://github.com/l-mb/dagobert/releases>:

   ```powershell
   uv tool install --python 3.14 --force git+https://github.com/l-mb/dagobert@v<version>
   ```

4. Start the app again. If the file format changed, the app converts the data directory at its
   first start.

To remove Dagobert, run `uv tool uninstall dagobert`. The command keeps your data directory.

## Work on the code

If you want to change the code, use a clone of the repository instead of `uv tool install`:

```powershell
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

1. Install Docker Desktop for Windows from <https://www.docker.com/products/docker-desktop/> with
   the WSL 2 backend, and start it.
2. Clone the repository and go into its directory:

   ```powershell
   git clone https://github.com/l-mb/dagobert dagobert
   cd dagobert
   ```

3. Make the data directory:

   ```powershell
   mkdir data
   ```

4. Build the image and start the app:

   ```powershell
   docker compose up -d --build
   ```

5. Open <http://localhost:8321> in your browser.

The quick start of the README sets `DAGOBERT_USER` to your user ID. That step is for Linux: leave
it out on Windows. Docker Desktop shares the folder with the container.

To use another data directory, make a file `.env` next to `compose.yaml` with a line such as
`DAGOBERT_DATA_DIR=C:/Users/<you>/Dagobert`. Run a command of Dagobert in the container with
`docker compose run --rm dagobert`, for example `docker compose run --rm dagobert init --example
starter`. To stop the app, run `docker compose down`. To update, run `git pull` and then
`docker compose up -d --build`.

This container runs on your computer only. To run Dagobert on a server with a login in front of
it, read [Run Dagobert on a server](self-hosting.md).
