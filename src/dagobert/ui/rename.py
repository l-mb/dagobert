"""`Rename` beside a name that the grids keep (an asset id, a stream name, a phase, a relative): a
dialog that takes the name and the new one, lists every line that the rename changes, file by file
(`rename.preview`), and writes them as one revision (`rename.apply`)."""

from __future__ import annotations

from itertools import groupby
from operator import attrgetter
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import i18n, rename, revisions
from dagobert.i18n import N_, _, ngettext
from dagobert.references import Kind
from dagobert.ui import (
    SECURITIES_ASSET,
    guard,
    keyboard,
    language,
    literal,
    recording,
    source,
    tell,
)
from dagobert.ui.save import changed_at, listed, reason

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

KEY = "rename-"
LISTED = f"{KEY}listed"  # what the open dialog listed in its last run, which its write checks
SHOWN = 6  # the lines of a file that the list names; the rest as their number
# By the kind of the name: what the dialog says first, the label of its select, the help of
# `Rename`, the toast of a rename
ABOUT = {
    Kind.ASSET: N_(
        "The id changes in every input that names the asset: the sales, repayments and "
        "purchases of the scenarios and their overrides, the streams and savings plans that name "
        "it, and its values in the history."
    ),
    Kind.STREAM: N_(
        "The name changes on every row of the stream and in every input that names it: a bonus "
        "that follows it, the events and overrides of the scenarios."
    ),
    Kind.PHASE: N_(
        "The short name changes in every input that names the phase: the streams and pension "
        "policies that pay in it, the phase changes of the scenarios and their salary scale. Its "
        "name on the pages stays."
    ),
    Kind.RELATIVE: N_(
        "The short name changes in every input that names the relative: the inheritances and "
        "gifts of the scenarios. Its name on the pages stays."
    ),
}
KINDS = {
    Kind.ASSET: N_("Asset"),
    Kind.STREAM: N_("Stream"),
    Kind.PHASE: N_("Phase"),
    Kind.RELATIVE: N_("Relative"),
}
HELPS = {
    Kind.ASSET: N_("A new name for one asset, here and in every input that names it."),
    Kind.STREAM: N_("A new name for one stream, here and in every input that names it."),
    Kind.PHASE: N_("A new name for one phase, here and in every input that names it."),
    Kind.RELATIVE: N_("A new short name for one relative, here and in every input that names it."),
}
RENAMED = {
    Kind.ASSET: N_("Renamed the asset {old} to {new}"),
    Kind.STREAM: N_("Renamed the stream {old} to {new}"),
    Kind.PHASE: N_("Renamed the phase {old} to {new}"),
    Kind.RELATIVE: N_("Renamed the relative {old} to {new}"),
}
HELD = N_("Save or discard the edits of the table first: a rename changes its rows.")
# the selections of other pages that hold a name: they follow a rename
FOLLOW = {Kind.ASSET: (SECURITIES_ASSET,)}


def listing(shown: rename.Preview) -> tuple[list[guard.Change], list[str]]:
    """The lines that a rename changes for the save guard, the first `SHOWN` of each file, and how
    many more each file holds."""
    found: list[guard.Change] = []
    more: list[str] = []
    for file, group in groupby(shown.lines, key=attrgetter("file")):
        lines = list(group)
        found += [
            guard.Change(f"{file}:{line.number}", line.old.strip(), line.new.strip(), unit=None)
            for line in lines[:SHOWN]
        ]
        if (rest := len(lines) - SHOWN) > 0:
            more.append(
                ngettext("{n} more line of `{file}`", "{n} more lines of `{file}`", rest).format(
                    n=rest, file=file
                )
            )
    return found, more


def button(
    data_dir: Path,
    kind: Kind,
    names: Sequence[str],
    *,
    key: str,
    held: bool,
    label: str = N_("Rename"),
) -> None:
    """`Rename` (or `label`, English, said here) beside the table `key` of the `names`, off while
    the table `held` edits: a rename changes its rows. A rename of the last run says so in a
    toast (`ui.tell`)."""
    if st.button(
        _(label),
        key=f"{key}-rename",
        icon=":material/edit:",
        disabled=held or not names,
        help=_(HELD) if held else _(HELPS[kind]),
    ):
        st.session_state.pop(LISTED, None)
        # the title in the language of the session: a dialog takes it where it is made
        st.dialog(_("Rename"))(_dialog)(data_dir, kind, list(dict.fromkeys(names)), key)


def _dialog(data_dir: Path, kind: Kind, names: list[str], table: str) -> None:
    """The name, the new one and the list of what the rename writes, or why it is refused. The
    write checks what the last run listed for the same names: a file changed since refuses
    it. A rerun of the dialog alone runs in a new thread without `main.py`: it takes the language
    of the session first."""
    i18n.activate(language())
    st.caption(_(ABOUT[kind]))
    # the fields of the table that opened it: those of another table hold other names
    old = st.selectbox(_(KINDS[kind]), names, key=f"{KEY}{table}-old")
    caps = "" if kind is Kind.STREAM else "nocaps-"  # an id and a phase take small letters
    new = st.text_input(_("New name"), key=f"{caps}{KEY}{table}-new", placeholder=old).strip()
    keyboard()
    now: rename.Preview | None = None
    if old is None or new in ("", old):
        st.caption(_("Type a new name first."))
    else:
        try:
            now = rename.preview(data_dir, rename.Rename(kind, old, new))
        except ValueError as err:
            st.error(
                _("Refused: {reason}.").format(reason=literal(str(err))), icon=":material/block:"
            )
        else:
            found, more = listing(now)
            guard.review(found, key=f"{KEY}dialog", hint="")
            if more:
                st.caption(", ".join(more) + ".")
    shown = listed(LISTED, (kind, old, new), now)
    pressed = st.button(_("Rename"), key=f"{KEY}confirm", type="primary", disabled=shown is None)
    if shown is None or not pressed:
        return
    try:
        with recording():  # a dialog reruns alone, without `main.py`
            rename.apply(data_dir, shown, source=source(str(shown.rename)))
    except revisions.ConflictError as err:
        st.error(
            _("Not saved: {changed} since this list. Look at it again.").format(
                changed=changed_at(err)
            )
        )
        return
    except (OSError, ValueError) as err:
        st.error(_("Not saved: {reason}").format(reason=literal(reason(err))))
        return
    for followed in FOLLOW.get(kind, ()):
        if st.session_state.get(followed) == shown.rename.old:
            st.session_state[followed] = shown.rename.new
    st.session_state.pop(LISTED, None)
    tell(_(RENAMED[kind]).format(old=shown.rename.old, new=shown.rename.new))
    st.rerun()
