"""The `Export and import` page (rule `transfer`): the zip of the data directory to download,
with or without its change history (the revisions), and the upload of one. Its preview lists what
the import changes per file, asks keep or take where the import cannot tell, and nothing is
written before `Import N files`."""

from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import streamlit as st
import yaml
from babel.dates import format_datetime

from dagobert import i18n, revisions, transfer
from dagobert.i18n import N_, _, ngettext, pgettext
from dagobert.model.assets import Trade
from dagobert.model.base import Unit
from dagobert.model.streams import Stream
from dagobert.money import format_size
from dagobert.problems import InputError
from dagobert.schema import SchemaError
from dagobert.store import NULL, RowEdits
from dagobert.transfer import Choice
from dagobert.ui import PAGES, Outcome, gridcolumns, guard, note, tell, timezone
from dagobert.ui.assets import TRADE_IDENTITY
from dagobert.ui.cashflows import EXPENSES
from dagobert.ui.fields import dicts
from dagobert.ui.save import reason
from dagobert.ui.snapshot import IDENTITY

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from streamlit.runtime.uploaded_file_manager import UploadedFile

    from dagobert.transfer import Change, Preview, Side

HELD = "transfer-preview"  # session state: the `Held` preview, the one archive a session holds
UPLOAD = "transfer-upload"  # session state: a nonce, so that an import empties the upload field
DONE = "transfer-done"  # session state: the `Outcome` of the last import, shown once
CHOICES = {Choice.KEEP: N_("Keep this instance"), Choice.TAKE: N_("Take the import")}
OPEN = N_("keep or take?")  # the action of a file without a choice
WRAP = "\u200b"  # a zero-width space: a file name in the table may wrap after a slash
MOVED = N_("The data directory changed since the preview: check the new one and choose again.")
# the words of a `transfer.Change`: how a file changed since the export (`here`, `there`) and what
# the import does with it (`action`)
SAID = {
    "added": N_("added"),
    "removed": N_("removed"),
    "changed": N_("changed"),
    "add": N_("add"),
    "remove": N_("remove"),
    "replace": N_("replace"),
    "keep": N_("keep"),
}
DONE_AS = {
    "add": N_("{n} added"),
    "replace": N_("{n} replaced"),
    "remove": N_("{n} removed"),
    "keep": N_("{n} kept"),
}
LINES = 40  # of a difference: a longer one shows its start
SIDES = {  # a side of a file, as `Change.sides` gives it: what it changed, that it removed it
    ("base", "here"): (N_("Changed here since the export"), N_("Removed here since the export.")),
    ("base", "zip"): (N_("Changed in the import since the export"), N_("Removed in the import.")),
    ("here", "zip"): (N_("Taking the import changes"), N_("Taking the import removes the file.")),
}
INTRO = N_(
    "An export is a zip file of your plan: the inputs, your records and the prices of your "
    "securities, without the fetched series. Keep it as a backup, or move your plan to another "
    "Dagobert. An import compares each file with the file at the time of the export, so the "
    "changes made here since then stay."
)
UPLOADER = N_("Choose a Dagobert export (.zip)")
READING = N_(
    "The import asks for a file that changed here and in the import, for a file that it would "
    "remove, and for every file that differs when the export comes from another history. "
    "`Keep this instance` keeps the file here, `Take the import` writes the file of the zip, or "
    "removes the file when the zip lacks it. `Difference` lists the changed rows as `old → new`, "
    "money with cents, and other files as lines that go (`-`) and come (`+`)."
)


@dataclass(frozen=True)
class Rows:
    """An input that holds a list of rows: its difference is row by row, in the format of the save
    guard."""

    key: str  # the list in the file
    identity: Sequence[str]  # the fields that name a row (`store.keyed`)
    units: Callable[[], Mapping[str, Unit]]


ROW_FILES = {
    "assets.yaml": Rows("assets", IDENTITY, gridcolumns.asset_units),
    "cashflows.yaml": Rows(
        "streams", EXPENSES.identity, lambda: gridcolumns.units(gridcolumns.columns(Stream))
    ),
}
# a field of a row that holds rows of its own: compared row by row too, else a changed trade of
# a depot that keeps their number would show as `2 rows → 2 rows`, which the guard leaves out
NESTED = {
    "trades": Rows("trades", TRADE_IDENTITY, lambda: gridcolumns.units(gridcolumns.columns(Trade)))
}
EUROS = {"value": Unit.EUR, "amount": Unit.EUR}  # the last column of a CSV input, if money


@dataclass(frozen=True)
class Difference:
    """A file against another: the changed and new rows and the removed ones in the format of the
    save guard, or, where rows do not apply or none differs, a unified diff."""

    found: list[guard.Change]
    removed: list[str]
    diff: str = ""


def difference(path: str, side: Side) -> Difference:
    """The rows of a row file (`ROW_FILES`) or of a CSV input by key: every column but the last
    names a row (`(month, category)`, `(date, asset)`, the date of a price). Else, and where no
    row differs (a comment, another key) or a file does not parse, the unified diff."""
    old, new = side.old or "", side.new or ""
    try:
        found, removed = (
            _yaml_rows(ROW_FILES[path], old, new)
            if path in ROW_FILES
            else _csv_rows(old, new)
            if path.endswith(".csv")
            else ([], [])
        )
    except yaml.YAMLError, csv.Error:
        found, removed = [], []
    return (
        Difference(found, removed) if found or removed else Difference([], [], side.unified(path))
    )


def _yaml_rows(spec: Rows, old: str, new: str) -> tuple[list[guard.Change], list[str]]:
    before, after = (_rows(yaml.safe_load(text) if text else None, spec.key) for text in (old, new))
    return _changes(spec, before, after)


def _changes(
    spec: Rows, before: list[dict[str, Any]], after: list[dict[str, Any]], prefix: str = ""
) -> tuple[list[guard.Change], list[str]]:
    """The changed cells and the removed rows, those of a `NESTED` field row by row too, each named
    after the row that holds it (`prefix`)."""
    edits = RowEdits.between(before, after, spec.identity)
    flat = {
        i: {key: value for key, value in cells.items() if key not in NESTED}
        for i, cells in edits.edited.items()
    }
    found = [
        replace(c, label=prefix + c.label)
        for c in guard.changes(before, RowEdits(flat, edits.added), units=spec.units())
    ]
    removed = [prefix + guard.label(before[i]) for i in edits.deleted]
    for i, cells in edits.edited.items():
        for key in sorted(cells.keys() & NESTED.keys()):
            inner, gone = _changes(
                NESTED[key],
                _rows(before[i], key),
                _rows(cells, key),
                f"{prefix}{guard.label(before[i])} {key} ",
            )
            found += inner
            removed += gone
    return found, removed


def _rows(doc: object, key: str) -> list[dict[str, Any]]:
    """The mappings in the list under `key` of the mapping `doc`."""
    return dicts(doc.get(key) if isinstance(doc, dict) else None)


def _csv_rows(old: str, new: str) -> tuple[list[guard.Change], list[str]]:
    (columns, before), (theirs, after) = _table(old), _table(new)
    if columns and theirs and columns != theirs:
        return [], []  # another layout: the unified diff shows it
    *key, value = columns or theirs or [""]
    edits = RowEdits.between(before, after, key)

    def named(row: Mapping[str, str | None]) -> str:
        return " ".join(row.get(k) or "" for k in key)

    def change(row: Mapping[str, str | None], field: str, old: Any, new: Any) -> guard.Change:  # noqa: ANN401
        label = named(row) if field == value else f"{named(row)} {field}"
        return guard.Change(label, _number(old), _number(new), EUROS.get(field))

    return [
        *(
            change(before[i], field, before[i].get(field), cell)
            for i, cells in edits.edited.items()
            for field, cell in cells.items()
        ),
        *(change(row, value, None, row.get(value)) for row in edits.added),
    ], [named(before[i]) for i in edits.deleted]


def _table(text: str) -> tuple[list[str], list[dict[str, str | None]]]:
    reader = csv.DictReader(io.StringIO(text))
    return list(reader.fieldnames or []), list(reader)


def _number(cell: object) -> float | str | None:
    if cell is None or cell is NULL:
        return None
    try:
        return float(str(cell))
    except ValueError:
        return str(cell)


def rows(preview: Preview, choices: Mapping[str, Choice]) -> list[dict[str, str]]:
    """The table of the preview, headed in the language of the session: per file how it changed
    here and in the zip since the base, and what the import does with it, by its choice or else
    its default. Without the base the zip against the file here, and the file here against the
    zip. A file name may wrap after a slash (`WRAP`)."""
    return [
        {
            _("file"): c.path.replace("/", "/" + WRAP),
            _("here"): _said(c.here) if c.known else _against(c.ours, c.theirs),
            _("zip"): _said(c.there),
            _("action"): _said(c.action(choice))
            if (choice := choices.get(c.path, c.default))
            else _(OPEN),
        }
        for c in preview.changes
    ]


def _said(word: str) -> str:
    """A word of a `transfer.Change` in the language of the session, empty for none."""
    return _(SAID[word]) if word else ""


def _against(ours: str | None, theirs: str | None) -> str:
    return _("not here") if ours is None else _("only here") if theirs is None else _("differs")


def effect(preview: Preview, choices: Mapping[str, Choice]) -> str:
    """What the import does in numbers: `1 added, 2 replaced, 3 kept, 9 unchanged`."""
    done = Counter(
        c.action(choice) for c in preview.changes if (choice := choices.get(c.path, c.default))
    )
    return ", ".join(
        [_(said).format(n=done[action]) for action, said in DONE_AS.items() if done[action]]
        + ([_("{n} unchanged").format(n=preview.unchanged)] if preview.unchanged else [])
    )


def removals(preview: Preview, choices: Mapping[str, Choice]) -> list[str]:
    """The files that the import removes: each by a choice of its own (`Every file in the zip`
    takes none)."""
    return [
        c.path for c in preview.changes if c.theirs is None and choices.get(c.path) is Choice.TAKE
    ]


def why(change: Change) -> str:
    """Why the import asks for the file."""
    if change.conflict:
        return _("{here} here and {there} in the import since the export").format(
            here=_said(change.here), there=_said(change.there)
        )
    if change.theirs is None:
        return _("not in the import") if not change.known else _("removed in the import")
    return _("only in the import") if change.ours is None else _("differs from the file here")


def page(data_dir: Path) -> None:
    st.title(_("Export and import"))
    st.caption(_(INTRO))
    _export(data_dir)
    st.markdown(f"**{_('Import')}**")
    import_zip(data_dir)


def stamp(revision: str) -> str:
    """The time of a revision in the time zone of the browser and the language of the session:
    `12 Oct 2026, 21:33`, `12. Okt. 2026, 21:33`."""
    at = revisions.time_of(revision).astimezone(timezone())
    return format_datetime(at, _("d MMM y, HH:mm"), locale=i18n.language())


def _export(data_dir: Path) -> None:
    """The toggle of the revisions and the download, which builds the zip on the click: a zip that
    an import would refuse shows why instead (a failed callable reaches the browser without its
    reason)."""
    st.markdown(f"**{_('Export')}**")
    taken = transfer.export(data_dir)
    history = st.toggle(
        _("Include change history ({size})").format(
            size=format_size(sum(p.stat().st_size for p in taken.copies.values()))
        ),
        key="transfer-history",
        help=_(
            "A copy of the files of every save so far (the revisions). An import into an empty "
            "data directory takes them along, one into a plan ignores them."
        ),
    )
    try:
        taken.check(history=history)
    except transfer.ArchiveError as err:
        st.error(_("Not exported: {reason}.").format(reason=err), icon=":material/error:")
        return
    st.download_button(
        _("Download the export"),
        data=lambda: taken.zip(history=history),
        file_name=taken.name,
        mime="application/zip",
        on_click="ignore",
        icon=":material/download:",
        key="transfer-export",
    )
    if taken.at:
        st.caption(
            _("Your plan as of its last save, {time}. File: {file}").format(
                time=stamp(taken.at), file=taken.name
            )
        )


def import_zip(data_dir: Path, then: str | None = None) -> None:
    """The upload of an export zip, its preview and `Import`. A done import shows its revision and
    count on this page, or goes to the page `then` of the navigation (the start page of an empty
    data directory goes to the Overview)."""
    n = st.session_state.setdefault(UPLOAD, 0)
    if (done := st.session_state.pop(DONE, None)) is not None:
        (st.success if done.ok else st.warning)(done.text)
    upload = st.file_uploader(
        _(UPLOADER), type="zip", max_upload_size=transfer.UPLOAD_MB, key=f"{UPLOAD}-{n}"
    )
    # a larger file never reaches the page: Streamlit names the reason only in a tooltip
    st.caption(
        _(
            "At most {mb} MB: the app refuses a larger file. Export it without its change history "
            "then."
        ).format(mb=transfer.UPLOAD_MB)
    )
    if upload is None:
        st.session_state.pop(HELD, None)
        return
    if (preview := _preview(data_dir, upload)) is not None:
        _show(data_dir, preview, upload.file_id, n, then)


@dataclass(frozen=True)
class Held:
    """The preview of the upload `upload` (its file id)."""

    upload: str
    preview: Preview


def _preview(data_dir: Path, upload: UploadedFile) -> Preview | None:
    """The preview of the upload: the one held while the upload and the head of the data directory
    stay, else a new one in its place, so that a session holds one archive at most."""
    held: Held | None = st.session_state.pop(HELD, None)
    if held is not None and held.upload == upload.file_id:
        if held.preview.head == revisions.head(data_dir):
            st.session_state[HELD] = held
            return held.preview
        st.warning(_(MOVED), icon=":material/sync_problem:")
    del held  # free the old archive before the new one reads
    try:
        preview = transfer.preview(data_dir, upload)
    except (transfer.ArchiveError, SchemaError, InputError) as err:
        st.error(_("Not importable: {file}").format(file=upload.name), icon=":material/error:")
        st.code(str(err), language=None, wrap_lines=True)
        return None
    st.session_state[HELD] = Held(upload.file_id, preview)
    return preview


def _show(data_dir: Path, preview: Preview, upload: str, n: int, then: str | None) -> None:
    """The notes, the table of the files, the choice per file that the import asks for, and
    `Import`, off while one lacks a choice."""
    if preview.stranger:
        st.warning(_(transfer.STRANGER), icon=":material/warning:")
    for line in preview.remarks:
        st.caption(line)
    if not preview.changes:
        st.info(
            ngettext(
                "Nothing to import: the {n} file of the zip is the same as here.",
                "Nothing to import: the {n} files of the zip are the same as here.",
                preview.unchanged,
            ).format(n=preview.unchanged),
            icon=":material/check:",
        )
        return
    # a new preview (another upload, a change here) starts without choices
    keys = {c.path: f"transfer-{upload}-{preview.head}-{c.path}" for c in preview.undecided}
    choices = {path: Choice(v) for path, key in keys.items() if (v := st.session_state.get(key))}
    base = preview.archive.base
    st.caption(
        _("Since the export of {time}:").format(time=stamp(base))
        if preview.known and base
        else _("Against the files here:")
    )
    with st.container(key="table-transfer"):
        st.table(rows(preview, choices), hide_index=True)
    if n_same := preview.unchanged:
        st.caption(
            ngettext(
                "{n} more file is the same here and in the zip.",
                "{n} more files are the same here and in the zip.",
                n_same,
            ).format(n=n_same)
        )
    if preview.undecided:
        _choices(preview.undecided, keys, choices)
    _apply(data_dir, preview, choices, n, then)


def _choices(
    undecided: list[Change], keys: Mapping[str, str], choices: Mapping[str, Choice]
) -> None:
    """A segmented control per file, and one for every file in the zip when there are several: it
    shows the choice that they share. A file that the zip lacks takes a choice of its own, so that
    one tap removes no file."""
    note(_(READING))
    if len(held := [c for c in undecided if c.theirs is not None]) > 1:
        every = f"{keys[held[0].path]}-every"
        shared = {choices.get(c.path) for c in held}
        st.session_state[every] = shared.pop() if len(shared) == 1 else None
        st.segmented_control(
            _("Every file in the zip"),
            list(CHOICES),
            format_func=_choice,
            key=every,
            on_change=_every,
            args=(every, [keys[c.path] for c in held]),
            help=_(
                "A file that the zip lacks takes a choice of its own: `Take the import` removes it."
            ),
        )
    for change in undecided:
        with st.container(border=True):
            st.markdown(f"`{change.path}`: {why(change)}")
            st.segmented_control(
                change.path,
                list(CHOICES),
                format_func=_choice,
                key=keys[change.path],
                label_visibility="collapsed",
            )
            with st.expander(_("Difference"), key=f"{keys[change.path]}-difference"):
                for side in change.sides:
                    _side(change.path, side)


def _choice(choice: Choice) -> str:
    return _(CHOICES[choice])


def _every(every: str, keys: list[str]) -> None:
    if (choice := st.session_state[every]) is not None:
        for key in keys:
            st.session_state[key] = choice


def _side(path: str, side: Side) -> None:
    changed, gone = (_(text) for text in SIDES[side.before, side.after])
    if side.new is None:
        st.caption(gone)
        return
    found = difference(path, side)
    if found.diff:
        lines = found.diff.splitlines(keepends=True)
        hidden = len(lines) - LINES
        more = ngettext("… {n} more line", "… {n} more lines", hidden).format(n=hidden)
        st.caption(f"{changed}:")
        st.code("".join(lines[:LINES]) + (f"{more}\n" if hidden > 0 else ""), language="diff")
        return
    shown = found.found[:LINES]
    guard.listing(shown, found.removed[: LINES - len(shown)], title=changed)
    if (hidden := len(found.found) + len(found.removed) - LINES) > 0:
        st.caption(ngettext("… {n} more row", "… {n} more rows", hidden).format(n=hidden))


def _apply(
    data_dir: Path, preview: Preview, choices: Mapping[str, Choice], n: int, then: str | None
) -> None:
    """`Import`: one revision of what the choices and the defaults take, then the page `then`. A
    change here since the preview shows a new one, files that do not load together their
    problems."""
    open_ = [c.path for c in preview.undecided if c.path not in choices]
    texts = {} if open_ else preview.texts(choices)
    taken = sum(
        c.action(choice) != "keep"
        for c in preview.changes
        if (choice := choices.get(c.path, c.default))
    )
    if gone := removals(preview, choices):
        st.warning(
            _("The import removes {files}.").format(files=", ".join(gone)), icon=":material/delete:"
        )
    st.caption(
        _("Keep or take: {files}.").format(files=", ".join(open_))
        if open_
        else _("Files: {effect}.").format(effect=effect(preview, choices))
        if texts
        else _("Nothing to import: every file here stays.")
    )
    label = (
        ngettext("Import {n} file", "Import {n} files", taken).format(n=taken)
        if texts and taken
        else pgettext("button", "Import")
    )
    if not st.button(label, type="primary", key="transfer-import", disabled=not texts):
        return
    try:
        entry = transfer.apply(data_dir, preview, choices)
    except transfer.StaleError:
        done = Outcome(ok=False, text=_(MOVED))
    except InputError as err:
        st.error(
            _("Not imported: the files kept and taken do not load together:"),
            icon=":material/error:",
        )
        st.code(str(err), language=None, wrap_lines=True)
        return
    except (OSError, ValueError) as err:
        st.error(_("Not imported: {reason}").format(reason=reason(err)), icon=":material/error:")
        return
    else:
        st.session_state[UPLOAD] = n + 1
        name, effects = preview.archive.name, effect(preview, choices)
        done = Outcome(
            ok=True,
            text=_("Imported {name} at {time}: {effect}.").format(
                name=name, time=stamp(entry.id), effect=effects
            )
            if entry
            else _("Imported {name}: {effect}.").format(name=name, effect=effects),
        )
    st.session_state.pop(HELD, None)
    if done.ok and (landing := st.session_state.get(PAGES, {}).get(then)) is not None:
        tell(done.text)  # the page of `then` says it
        st.switch_page(landing)
    st.session_state[DONE] = done
    st.rerun()
