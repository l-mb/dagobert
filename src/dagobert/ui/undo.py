"""Undo: the last save of the session above every page until its next save, and on the Overview
the last revision of the data directory, each taken back as a new revision (`revisions.undo`),
never a rewrite of the log. A later revision of the same files refuses it."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import datadir, revisions
from dagobert.i18n import N_, _
from dagobert.ui import PAGES, SAVED, Saved, literal, source, tell
from dagobert.ui.fileactions import follow
from dagobert.ui.save import REFUSED, reason, when

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

LINE = "undo-line"  # the container of the line of the session, above every page
HELP = N_(
    "Writes the files of this save as they were before it, as a new save: both stay in the "
    "record of the changes. A later save of the same files, here, on another device or by a "
    "command, keeps it off."
)


def line(data_dir: Path) -> None:
    """The last save of the session with `Undo`, until its next save: `Saved at 14:03 on
    Cashflows.`, after an undo `Took back the save at 14:03 on Cashflows.` (`ui.SAVED`). Nothing
    before a save or when the log lacks it."""
    saved: Saved | None = st.session_state.get(SAVED)
    if saved is None:
        return
    log = revisions.entries(data_dir)
    found = {e.id: e for e in log if e.id in (saved.id, saved.undid)}
    if (entry := found.get(saved.id)) is None:
        return
    if saved.undid and (undid := found.get(saved.undid)):
        text = _("Took back the save {when}.").format(
            when=when(undid.source, undid.time, action=False)
        )
    else:
        text = _("Saved {when}.").format(when=when(entry.source, entry.time, action=False))
    _offer(data_dir, log, entry, text, key="undo")


def last(data_dir: Path) -> None:
    """On the Overview: the last revision of the data directory with `Undo`, `Last save at 14:03
    on Cashflows.`: a save of another session or device, a command or an edit outside the app.
    Not the last save of this session, which its line above the page offers, and not the first
    revision or one of `datadir.open`, which have nothing to take back."""
    log = revisions.entries(data_dir)
    saved: Saved | None = st.session_state.get(SAVED)
    if len(log) < 2 or (saved and saved.id == log[-1].id) or datadir.opened(log[-1]):
        return
    entry = log[-1]
    text = _("Last save {when}.").format(when=when(entry.source, entry.time, action=False))
    _offer(data_dir, log, entry, text, key="overview-undo")


def _offer(
    data_dir: Path, log: Sequence[revisions.Entry], entry: revisions.Entry, text: str, *, key: str
) -> None:
    """`text` with the button `Undo` of `entry`, or with why it is off: a later revision of its
    files (`revisions.check_undo`)."""
    with st.container(horizontal=True, vertical_alignment="center", key=f"{key}-row"):
        try:
            revisions.check_undo(log, entry)
        except (revisions.ConflictError, revisions.UndoError) as err:
            off = _("{text} Undo is off: {reason}.").format(text=text, reason=reason(err))
            st.caption(f":material/history: {off}")
            return
        st.caption(f":material/history: {text}", width="content")
        if st.button(_("Undo"), key=key, icon=":material/undo:", help=_(HELP)):
            _undo(data_dir, entry)


def _undo(data_dir: Path, entry: revisions.Entry) -> None:
    """Take back `entry` and rerun with the undo as the save of the session, the selections of
    other pages back on a scenario whose rename it took back; a refusal shows `Not undone:`."""
    try:
        done = revisions.undo(data_dir, entry, source=_source(entry))
    except (revisions.ConflictError, *REFUSED) as err:
        lines = "  \n".join(map(literal, reason(err).splitlines()))
        st.error(_("Not undone: {reason}").format(reason=lines))
        return
    if done is None:
        tell(_("Nothing to take back: the files are as before this save"), warn=True)
    else:
        st.session_state[SAVED] = Saved(done.id, undid=entry.id)
        if (moved := done.renamed) and all(p.startswith("scenarios/") for p in moved):
            follow(PurePosixPath(moved[0]).stem, PurePosixPath(moved[1]).stem)
        tell(
            _("Took back the save {when}").format(when=when(entry.source, entry.time, action=False))
        )
    st.rerun()


def _source(entry: revisions.Entry) -> str:
    """The source of the undo of `entry` in the log: `Cashflows: undo`, by the page that wrote
    `entry`, else by this page (`ui.source`): a command, an edit outside the app."""
    page = entry.source.partition(": ")[0]
    return f"{page}: undo" if page in st.session_state.get(PAGES, {}) else source("undo")
