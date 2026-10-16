"""The file actions of the Scenarios page: `New`, `Copy`, `Rename file`, `Delete` and `Add a job
loss`, each a dialog that lists what it writes through the save guard, in words, or why it is
refused, and writes it as one revision. The write refuses a file changed since the list, and
after a rename or a delete the selections of the other pages follow."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from itertools import chain, count
from typing import TYPE_CHECKING, Any

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import i18n, references, revisions, scenariofiles, store
from dagobert.i18n import N_, _, pgettext
from dagobert.model.base import Unit
from dagobert.model.events import PhaseChange
from dagobert.model.months import months_of_age
from dagobert.model.streams import StreamKind
from dagobert.problems import Keys, dotted
from dagobert.ui import (
    CASHFLOWS_SCENARIO,
    FLOWS_SCENARIO,
    guard,
    is_mobile,
    keyboard,
    language,
    lineage,
    literal,
    main_marked,
    mode,
    slug,
    source,
    tell,
    titled,
)
from dagobert.ui import fields as model_fields
from dagobert.ui.fields import ABSENT, dicts, lookup, parse
from dagobert.ui.gridcolumns import keyword, on_off
from dagobert.ui.save import changed_at, listed, reason
from dagobert.ui.sliders import KEY as EXPLORER
from dagobert.ui.widgets import SHAPE

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
MONTH = next(f for f in model_fields.of(PhaseChange) if f.unit is Unit.MONTH)  # a month typed


def followed(held: object, old: str, new: str | None) -> object:
    """A selection of another page (`FOLLOW`: a stem or a list of them) after the stem `old`
    became `new`, or went (None)."""
    if held == old:
        return new
    if isinstance(held, list):
        return [new if s == old else s for s in held if new or s != old]
    return held


def listing(
    edits: Sequence[store.Edit], read: Callable[[str], Doc], labels: Mapping[str, str] | None = None
) -> tuple[list[guard.Change], list[str]]:
    """What the edits of a file action write, for the save guard: the file that it moves or copies,
    each value that it sets with the value before (`read` gives the raw mapping of a file), each
    row that it adds or changes in a list, and the files that it removes. A key as the pages name
    it, a value in words (`worded`, the phases by their `labels`, also those that the edits
    define), a feature as on the Features page, `on` or `off`."""
    moved = {e.origin for e in edits if e.origin} & {e.name for e in edits if e.remove}
    defined: dict[str, str] = {
        str(keys[1]): str(value["label"])
        for e in edits
        if e.name == "assumptions.yaml"
        for keys, value in e.values.items()
        if keys[:1] == ("phases",) and len(keys) == 2 and isinstance(value, dict)
    }
    said = {**(labels or {}), **defined}
    found: list[guard.Change] = []
    for edit in edits:
        if edit.origin in moved:
            found.append(guard.Change(_("file"), edit.origin, edit.name, unit=None))
        elif edit.origin:
            copy = _("copy of {file}").format(file=edit.origin)
            found.append(guard.Change(edit.name, None, copy, unit=None))
        before = read(edit.origin or edit.name) if not edit.create or edit.origin else {}
        for keys, value in edit.values.items():
            old = None if (held := lookup(before, keys)) is ABSENT else held
            if keys == ("features_off",):
                found += _features(old, value)
                continue
            found.append(
                guard.Change(
                    f"{edit.name} {_keys(keys)}",
                    worded(keys, old, said),
                    worded(keys, value, said),
                    unit=None,
                )
            )
        for way, rows in edit.rows.items():
            keys = tuple(k for k in way if isinstance(k, str | int))  # no `Where` in a new file
            found += _rows(f"{edit.name} {_keys(keys)}", dicts(lookup(before, keys)), rows, said)
    return found, [e.name for e in edits if e.remove and e.name not in moved]


def _features(old: object, new: object) -> list[guard.Change]:
    """A change of `features_off` as the Features page lists it: `job loss on → off`."""
    was, now = mode.listed(old), mode.listed(new)
    return [
        guard.Change(mode.said([f]), on_off(f not in was), on_off(f not in now), unit=None)
        for f in mode.FEATURES
        if (f in was) != (f in now)
    ]


def _rows(
    where: str, held: Sequence[Doc], rows: store.RowEdits, labels: Mapping[str, str]
) -> list[guard.Change]:
    """The rows that a file action adds to a list, in words, and the cells that it changes, each
    row by its name or id."""

    def named(row: Doc, n: int) -> str:
        return str(row.get("name") or row.get("id") or n + 1)

    def cells(row: Doc) -> str:
        return ", ".join(f"{keyword(k)} {worded((k,), v, labels)}" for k, v in row.items())

    return [
        *(
            guard.Change(
                f"{where} {named(held[i], i)} {keyword(k)}",
                worded((k,), held[i].get(k), labels),
                worded((k,), v, labels),
                unit=None,
            )
            for i, changed in rows.edited.items()
            for k, v in changed.items()
        ),
        *(guard.Change(where, None, cells(row), unit=None, added=True) for row in rows.added),
    ]


def worded(  # noqa: PLR0911 one return per kind of value
    keys: Keys, value: object, labels: Mapping[str, str]
) -> str | None:
    """A value that a file action writes, in words, never as Python writes it: the phase changes
    by their labels and months (`Work from 2026-10`), the phases of a stream by their labels, the
    events by their type, month and what they name, a stream kind by its title, a month as the
    pages write it, a mapping by its label or its keys."""
    last = keys[-1] if keys else None
    match value:
        case None:
            return None
        case date():
            return f"{value:%Y-%m}"
        case list() if last == "phases" and dicts(value):
            return ", ".join(
                _("{phase} from {month}").format(
                    phase=labels.get(str(r.get("phase")), str(r.get("phase"))),
                    month=worded((), r.get("from"), labels),
                )
                for r in dicts(value)
            )
        case list() if last == "phases":
            return ", ".join(labels.get(str(p), str(p)) for p in value)
        case list() if last == "events":
            return "; ".join(lineage.worded(row) for row in dicts(value))
        case list():
            return ", ".join(str(worded((), v, labels)) for v in value)
        case dict() if isinstance(value.get("label"), str):
            return str(value["label"])
        case dict():
            return ", ".join(f"{keyword(k)} {worded((k,), v, labels)}" for k, v in value.items())
        case str() if last == "kind" and value in (kinds := StreamKind.titles()):
            return _(kinds[value])
    return str(value)


def _keys(keys: Keys) -> str:
    """A key path as the pages name its keys: `scenarios[0]`."""
    return dotted(tuple(keyword(k) if isinstance(k, str) else k for k in keys))


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
            labels = references.phases(data_dir)
            found, gone = listing(now.edits, partial(references.read, data_dir), labels)
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


def _new(data_dir: Path, plan: Plan) -> None:
    i18n.activate(language())
    name = st.text_input(_("Name"), key=f"{KEY}new-name", help=_(NAME_HELP)).strip()
    stem = _stem(_("File name"), "new-stem", placeholder=slug(name)) or slug(name)
    parent = st.selectbox(
        _("Extends"),
        plan.parents,
        format_func=lambda stem: _(NO_PARENT) if stem is None else plan.said(stem),
        key=f"{KEY}new-parent",
        filter_mode=None if is_mobile() else "fuzzy",  # no keyboard on a phone
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


def _month(label_text: str, key: str) -> tuple[date | None, str]:
    """A month typed into a text field, and why it does not read."""
    typed = st.text_input(label_text, key=f"{KEY}{key}", placeholder=_(SHAPE[Unit.MONTH]))
    try:
        return parse(MONTH, typed), ""
    except ValueError as err:
        return None, str(err)


def _free(first: str, taken: Collection[str], numbered: Callable[[int], str]) -> str:
    """`first`, else the first of its `numbered` forms from 2 that is not `taken`."""
    return next(n for n in chain([first], map(numbered, count(2))) if n not in taken)


def _job_loss(data_dir: Path, plan: Plan) -> None:
    """The months of a job loss and of a new job, the name of its scenario, and what the action
    writes (`scenariofiles.lost_job`)."""
    i18n.activate(language())
    main = str(plan.main)
    st.caption(
        _(
            "A new scenario that extends {scenario}. From the month of the job loss the salary "
            "stops and ALG1 pays, until the month of a new job, if you type one. Where the plan "
            "lacks them, the app adds the payment ALG1, a phase without a job and the feature "
            "Job loss."
        ).format(scenario=plan.said(main))
    )
    lost, problem = _month(_("Month of the job loss"), "loss-lost")
    back, later = _month(_("Month of a new job (optional)"), "loss-back")
    birth = references.born(data_dir)
    named = (
        _("Job loss at {age}").format(age=months_of_age(birth, lost) // 12)
        if lost and birth
        else _("Job loss")
    )
    taken = {str(doc.get("name")) for doc in plan.docs.values()}
    default = _free(named, taken, lambda k: f"{named} ({k})")
    name = st.text_input(
        _("Name"), key=f"{KEY}loss-name", placeholder=default, help=_(NAME_HELP)
    ).strip()
    stems = {s.casefold() for s in plan.docs}
    base = slug(name or default)
    stem = _free(base, stems, lambda k: f"{base}-{k}")
    loss = (
        None
        if lost is None
        else scenariofiles.JobLoss(
            main, lost, back, name or default, stem, pgettext("phase", "Unemployed")
        )
    )
    _confirm(
        data_dir,
        ("job-loss", loss),
        lambda d: [] if loss is None else scenariofiles.lost_job(d, loss),
        button=_("Add the job loss"),
        what=f"job loss {stem}",
        done=_("Created {name}: a job loss in {month}").format(
            name=name or default, month=f"{lost:%Y-%m}" if lost else ""
        ),
        then=stem,
        ready=loss is not None and not later,
        why=problem or later or _("Type the month of the job loss first."),
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


@dataclass(frozen=True)
class Plan:
    """The scenarios that the dialogs offer: the raw files by stem, and the main scenario, None
    while none runs."""

    docs: Mapping[str, Doc]
    main: str | None

    def said(self, stem: str) -> str:
        """A scenario in a select: `stem · name`, the main one marked (`ui.main_marked`)."""
        shown = {stem: titled(stem, self.docs.get(stem, {}).get("name"))}
        return main_marked(shown, stem)[stem] if stem == self.main else shown[stem]

    @property
    def parents(self) -> list[str | None]:
        """What a new scenario may extend: the main scenario first, the others, then none."""
        others = sorted((s for s in self.docs if s != self.main), key=str.casefold)
        return [*([self.main] if self.main else []), *others, None]


def actions(data_dir: Path, chosen: Chosen | None, plan: Plan, row: DeltaGenerator) -> None:
    """The file actions: buttons beside the chooser, on a phone in a popover `File`, which closes
    when one is tapped: it would cover the dialog. Each opens its dialog with a fresh list, its
    title in the language of the session: a dialog takes it where it is made. `Add a job loss`
    needs a main scenario to extend."""
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
        "new": (N_("New"), N_("New scenario"), _new, (data_dir, plan)),
    }
    if chosen is not None:
        dialogs |= {
            "copy": (N_("Copy"), N_("Copy the scenario"), _copy, (data_dir, chosen)),
            "rename": (N_("Rename file"), N_("Rename the file"), _rename, (data_dir, chosen)),
            "delete": (N_("Delete"), N_("Delete the scenario"), _delete, (data_dir, chosen)),
        }
    if plan.main is not None:
        dialogs["job-loss"] = (
            N_("Add a job loss"),
            N_("Add a job loss"),
            _job_loss,
            (data_dir, plan),
        )
    for action, (text, title, dialog, args) in dialogs.items():
        if holder.button(
            _(text),
            key=f"{KEY}{action}",
            on_click=shut if phone else None,
            args=(FILE,),
        ):
            st.session_state.pop(LISTED, None)
            st.dialog(_(title))(dialog)(*args)
