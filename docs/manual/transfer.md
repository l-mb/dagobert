# Export and import

An export is a zip file of your data directory. It holds the inputs, your records and the prices of
your securities. It does not hold the fetched series in `series/` or the report in `out/`. Use an
export as a backup, or to work on a copy and bring the result back. The page `Export and import` in
the section Setup does both. The commands `dagobert export` and `dagobert import` do the same on
the command line.

## Make an export

1. Open the page `Export and import`.
2. If you want the change history in the zip, turn on `Include change history`. The change history
   is the revisions: a revision is a copy of the files that one save changed. The label shows their
   size.
3. Press `Download the export`. Your browser saves the file `dagobert-<revision>.zip`.

The line below the button shows the time of the last save in the data directory and the file name.
The revision in the file name is that last save. The import uses this revision to find what changed
on each side since the export.

An export holds at most 64 MB of files. If your change history makes it larger, the page tells
you, and you can export without it.

On the command line, run `uv run dagobert export --data data`. The command writes the zip into the
current directory. `--out FILE` or `--out DIRECTORY` writes it to another place. `--revisions` adds
the revisions.

## Back up your plan

An export with the change history is a backup of your plan. Make one from time to time, and before
you update Dagobert. If an update converts the data directory to a new file format, an older version
of Dagobert cannot open it.

Restore a backup into an empty data directory. The page [Start a plan](start-a-plan.md) shows the
import, and `uv run dagobert import <zip> --data <directory>` does the same. The data directory then
takes the revisions of the zip too. Do not use an import to undo changes in a data directory with
a plan. The import keeps each file that changed there after the export.

A copy of the whole data directory, `revisions/` included, is also a backup. It also holds the
fetched series.

## Work on a copy

You can work on a copy of your plan on your own computer, for example when the app runs on a
server. Install Dagobert there, as the README says under `Quick start without the container`.
Then download an export, and run the commands below in the directory of Dagobert. On Windows and
macOS, you can follow [Install Dagobert on Windows](../install/windows.md) or
[Install Dagobert on macOS](../install/macos.md) instead. Such an install runs `dagobert` in any
directory, so leave out `uv run` before it.

`uv run dagobert app --data dagobert-<revision>.zip` unpacks the zip into the directory
`dagobert-<revision>` next to it and opens the app on that directory. If you start the app again
with the same zip, it uses the same directory, with your changes. The copy has no fetched series.
Fetch the series that you need again on its Data page.

`uv run dagobert run --data dagobert-<revision>.zip plan.yaml` computes a scenario of the zip
without a copy. Name each scenario by its file name.

To bring your changes back, export the copy and import that zip into your data directory.

## Import an export

1. Open the page `Export and import`.
2. Upload the zip under `Choose a Dagobert export (.zip)`. The page takes a zip of at most 64 MB.
3. Read the table. It lists each file that differs, how it changed here and in the zip since the
   export, and what the import does with it. A line below the table counts the files that are the
   same on both sides. If all files are the same, the page says `Nothing to import` and shows no
   table.
4. Choose for each file that shows `keep or take?`, as described below.
5. Press `Import N files`. N is the number of files that the import adds, replaces or removes.
   After the import, a line names the time of the import and what it changed.

The import compares each file of the zip with the file in the data directory and with the file
at the revision of the export:

- If only the zip changed the file, the import takes the file of the zip.
- If only the data directory changed the file, the import keeps it.
- In all other cases, the import asks you.

The import asks for a file that changed on both sides and for a file that the import removes. It
also asks for every file that differs when the data directory does not have the revision of the
export. This occurs when the export comes from another data directory, or from one that you made
by an import without revisions. A yellow warning then names this case. The column `here` then
compares the file here with the zip: `not here`, `only here` or `differs`.

Each file that the import asks for has a box. `Keep this instance` keeps the file in the data
directory. `Take the import` writes the file of the zip, or removes the file if the zip does not
have it. `Every file in the zip` gives the same answer for all boxes of the files that the zip
has. A file that the zip does not have needs an answer in its own box, so that one tap removes no
file. Before you import, a warning names each file that the import removes.

Open `Difference` to see what changed. For your assets and their trades, streams, records and
prices, it lists each changed row as `old → new`, with the cents of each amount. For the other
files, it shows the lines that go (`-`) and the lines that come (`+`). If a file changed on both
sides, it shows the changes here, the changes in the zip, and what `Take the import` changes here.
That last list also names the rows here that the import drops.

Nothing changes before you press `Import`. The import writes one revision. If the data directory
changed after you uploaded the zip, the page shows a new table, and you must choose again. If the
files that you keep and take do not load together, the page shows the problems and changes
nothing.

If the zip has an older format, the import converts it and a line above the table says so. If the
zip comes from a newer version of Dagobert, the page refuses it. Update the app first.

An import into an empty data directory takes all files of the zip, and the revisions if the zip
has them. A data directory with inputs keeps its own revisions and ignores the revisions of the
zip. An empty data directory shows the page [Start a plan](start-a-plan.md) instead of this page.
The same import is on that page, and after it the Overview opens.

On the command line, run `uv run dagobert import dagobert-<revision>.zip --data data`. The command
shows the table and the difference of each file that it asks for. To answer:

1. Add `--keep FILE` to keep the file in the data directory, or `--take FILE` to take the file of
   the zip.
2. Add `--keep-all` or `--take-all` to answer for all files that you did not name.
3. Run the command again. It asks before it writes. `--yes` skips this question.
