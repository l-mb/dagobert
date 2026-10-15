"""The file actions of the Scenarios page: `New`, `Copy`, `Rename file` and `Delete`, each a
dialog that lists what it writes through the save guard, or why it is refused, and writes it as
one revision. The write refuses a file changed since the list, and after a rename or a delete the
selections of the other pages follow."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import i18n, references, revisions, scenariofiles, store
from dagobert.i18n import N_, _
from dagobert.problems import Keys, dotted
from dagobert.references import Kind, References
from dagobert.ui import (
    CASHFLOWS_SCENARIO,
    FLOWS_SCENARIO,
    guard,
    is_mobile,
    keyboard,
    language,
    literal,
    slug,
    source,
    tell,
)
from dagobert.ui.fields import ABSENT, lookup
from dagobert.ui.gridcolumns import keyword
from dagobert.ui.save import changed_at, listed, reason
from dagobert.ui.sliders import KEY as EXPLORER

if TYPE_CHECKING:
    from pathlib import Path

    from dagobert.ui.scenarios import Chosen

KEY = "scenarios-"
PENDING = f"{KEY}pending"  # the stem that the chooser takes in the next run: after a file action
FILE = f"{KEY}file"  # the popover of the file actions on a phone, closed by a tap on one
LISTED = f"{KEY}listed"  # what the open dialog listed in its last run, which its write checks
# the selections of other pages that hold a stem: they follow a rename and a delete
FOLLOW = (f"{EXPLORER}scenarios", CASHFLOWS_SCENARIO, FLOWS_SCENARIO)
NO_PARENT = N_("none: a scenario of its own")  # an empty `extends`
STEM_HELP = N_(
    "The name of the scenario file, made from the name unless you type one: letters, digits, "
    "spaces, dots, underscores or dashes. A scenario that extends it, the main scenario and the "
    "comparison of the Explorer name it by its file."
)
NAME_HELP = N_(
    "The name in the results, the tabs and the summary table. Two scenarios cannot share one."
)
Doc = Mapping[str, Any]


def followed(held: object, old: str, new: str | None) -> object:
    """A selection of another page (`FOLLOW`: a stem or a list of them) after the stem `old`
    became `new`, or went (None)."""
    if held == old:
        return new
    if isinstance(held, list):
        return [new if s == old else s for s in held if new or s != old]
    return held


def listing(
    edits: Sequence[store.Edit], read: Callable[[str], Doc]
) -> tuple[list[guard.Change], list[str]]:
    """What the edits of a file action write, for the save guard: the file that it moves or copies,
    each value that it sets with the value before (`read` gives the raw mapping of a file), and the
    files that it removes. A key as the pages name it."""
    moved = {e.origin for e in edits if e.origin} & {e.name for e in edits if e.remove}
    found: list[guard.Change] = []
    for edit in edits:
        if edit.origin in moved:
            found.append(guard.Change(_("file"), edit.origin, edit.name, unit=None))
        elif edit.origin:
            copy = _("copy of {file}").format(file=edit.origin)
            found.append(guard.Change(edit.name, None, copy, unit=None))
        before = read(edit.origin or edit.name) if not edit.create or edit.origin else {}
        found += [
            guard.Change(
                f"{edit.name} {_keys(keys)}",
                _shown(None if (old := lookup(before, keys)) is ABSENT else old),
                _shown(value),
                unit=None,
            )
            for keys, value in edit.values.items()
        ]
    return found, [e.name for e in edits if e.remove and e.name not in moved]


def _keys(keys: Keys) -> str:
    """A key path as the pages name its keys: `scenarios[0]`."""
    return dotted(tuple(keyword(k) if isinstance(k, str) else k for k in keys))


def _shown(value: object) -> str | None:
    return None if value is None else str(value)


def shut(popover: str) -> None:
    """Close a popover: what it opens or chooses would sit below it."""
    st.session_state[popover] = False


def _confirm(
    data_dir: Path,
    params: tuple[object, ...],
    action: scenariofiles.Action,
    *,
    button: str,
    what: str,
    done: str,
    then: str | None,
    ready: bool = True,
    why: str = "",
    moved: tuple[str, str | None] | None = None,
) -> None:
    """The end of a dialog: what `action` writes (`listing`), or why it is refused, and the
    button that writes it as one revision `Scenarios: <what>`; while it is not `ready`, `why`. The
    write checks what the last run listed for the same `params`: a file changed since
    refuses it. A written action closes the dialog with the toast `done`, the chooser takes
    `then`, and the selections of other pages follow the stem that it `moved` (old and new, None
    after a delete)."""
    now: scenariofiles.Listed | None = None
    if not ready and why:
        st.caption(why)
    if ready:
        try:
            now = scenariofiles.listed(data_dir, action)
        except ValueError as err:
            st.error(
                _("Refused: {reason}.").format(reason=literal(str(err))), icon=":material/block:"
            )
        else:
            found, gone = listing(now.edits, lambda name: references.read(data_dir, name))
            guard.review(found, gone, key=f"{KEY}dialog", hint="")
    shown = listed(LISTED, params, now)
    if not st.button(button, key=f"{KEY}confirm", type="primary", disabled=shown is None):
        return
    try:
        scenariofiles.act(data_dir, action, source=source(what), shown=shown)
    except revisions.ConflictError as err:
        st.error(
            _("Not saved: {changed} since this list. Look at it again.").format(
                changed=changed_at(err)
            )
        )
        return
    except (OSError, ValueError) as err:
        st.error(_("Not saved: {reason}").format(reason=reason(err)))
        return
    if moved is not None:
        _follow(*moved)
    st.session_state.pop(LISTED, None)
    st.session_state[PENDING] = then
    tell(done)
    st.rerun()


def _follow(old: str, new: str | None) -> None:
    """The selections of other pages in the session take the stem `new` for `old` (`followed`)."""
    for key in [k for k in FOLLOW if k in st.session_state]:
        if (value := followed(st.session_state[key], old, new)) is None:
            del st.session_state[key]
        else:
            st.session_state[key] = value


def _stem(label_text: str, key: str, value: str = "", placeholder: str = "") -> str:
    """A text field for a file name, without a capital first letter on a phone."""
    typed = st.text_input(
        label_text, value, key=f"nocaps-{KEY}{key}", help=_(STEM_HELP), placeholder=placeholder
    )
    keyboard()
    return typed.strip()


# A dialog reruns alone, without `main.py`, in a thread of its own: it takes the language of the
# session first. Its title comes per call, in the language of the session (`actions`).


def _new(data_dir: Path, options: list[str]) -> None:
    i18n.activate(language())
    name = st.text_input(_("Name"), key=f"{KEY}new-name", help=_(NAME_HELP)).strip()
    stem = _stem(_("File name"), "new-stem", placeholder=slug(name)) or slug(name)
    parent = st.selectbox(
        _("Extends"),
        options,
        index=None,
        placeholder=_(NO_PARENT),
        key=f"{KEY}new-parent",
        help=_("The scenario whose phases, events and overrides it starts from."),
    )
    _confirm(
        data_dir,
        ("new", stem, name, parent),
        lambda d: scenariofiles.created(d, stem, name or stem, parent),
        button=_("Create"),
        what=f"new {stem}",
        done=(
            _("Created {name}, which extends {parent}") if parent else _("Created {name}")
        ).format(name=name or stem, parent=parent),
        then=stem,
        ready=bool(stem),
        why=_("Type a name first."),
    )


def _copy(data_dir: Path, chosen: Chosen) -> None:
    i18n.activate(language())
    st.caption(
        _("A copy of `{file}` with its comments, which extends the same parent.").format(
            file=chosen.file
        )
    )
    named = _("{name} (copy)").format(name=chosen.doc.get("name") or chosen.stem)
    name = st.text_input(_("Name"), named, key=f"{KEY}copy-name", help=_(NAME_HELP)).strip()
    stem = _stem(_("File name of the copy"), "copy-stem", f"{chosen.stem}-copy")
    _confirm(
        data_dir,
        ("copy", chosen.stem, stem, name),
        lambda d: scenariofiles.copied(d, chosen.stem, stem, name or stem),
        button=_("Copy"),
        what=f"copy {chosen.stem} → {stem}",
        done=_("Copied {old} to {new}").format(old=chosen.stem, new=stem),
        then=stem,
        ready=bool(stem),
        why=_("Type a file name first."),
    )


def _rename(data_dir: Path, chosen: Chosen) -> None:
    i18n.activate(language())
    st.caption(
        _(
            "The file takes the new name, and the scenarios that extend it, the main scenario and "
            "the comparison of the Explorer follow. The name in the results stays: change it in "
            "the tab General."
        )
    )
    stem = _stem(_("New file name"), "rename-stem", chosen.stem)
    _confirm(
        data_dir,
        ("rename", chosen.stem, stem),
        lambda d: scenariofiles.renamed(d, chosen.stem, stem),
        button=_("Rename file"),
        what=revisions.renaming(chosen.file, scenariofiles.scenario_file(stem)),
        done=_("Renamed the file {old} to {new}").format(old=chosen.stem, new=stem),
        then=stem,
        ready=bool(stem) and stem != chosen.stem,
        why=_("Type a new file name first."),
        moved=(chosen.stem, stem),
    )


def _delete(data_dir: Path, chosen: Chosen) -> None:
    i18n.activate(language())
    st.caption(_("`{file}` goes. The revisions keep a copy of it.").format(file=chosen.file))
    _confirm(
        data_dir,
        ("delete", chosen.stem),
        lambda d: scenariofiles.removed(d, chosen.stem),
        button=_("Delete"),
        what=f"delete {chosen.stem}",
        done=_("Deleted {scenario}").format(scenario=chosen.stem),
        then=None,
        moved=(chosen.stem, None),
    )


def actions(data_dir: Path, chosen: Chosen | None, refs: References, row: DeltaGenerator) -> None:
    """The file actions: buttons beside the chooser, on a phone in a popover `File`, which closes
    when one is tapped: it would cover the dialog. Each opens its dialog with a fresh list, its
    title in the language of the session: a dialog takes it where it is made."""
    phone = is_mobile()
    holder = (
        row.popover(_("File"), icon=":material/folder:", key=FILE, on_change="rerun").container(
            horizontal=True, wrap=True
        )
        if phone
        else row
    )
    # by the key of the button: its label, the title of its dialog, the dialog and its arguments
    dialogs: dict[str, tuple[str, str, Callable[..., None], tuple[Any, ...]]] = {
        "new": (N_("New"), N_("New scenario"), _new, (data_dir, refs.names(Kind.SCENARIO))),
    }
    if chosen is not None:
        dialogs |= {
            "copy": (N_("Copy"), N_("Copy the scenario"), _copy, (data_dir, chosen)),
            "rename": (N_("Rename file"), N_("Rename the file"), _rename, (data_dir, chosen)),
            "delete": (N_("Delete"), N_("Delete the scenario"), _delete, (data_dir, chosen)),
        }
    for action, (text, title, dialog, args) in dialogs.items():
        if holder.button(
            _(text),
            key=f"{KEY}{action}",
            on_click=shut if phone else None,
            args=(FILE,),
        ):
            st.session_state.pop(LISTED, None)
            st.dialog(_(title))(dialog)(*args)
