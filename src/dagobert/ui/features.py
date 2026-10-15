"""The Features page: a switch per part of life that a plan may not model (`mode.FEATURES`), saved
as `features_off` of `app.yaml`, one revision `Features` of that file alone. A part that the
inputs use is locked on and names where (`Uses.where`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import revisions, store
from dagobert.i18n import N_, _, pgettext
from dagobert.loader import APP
from dagobert.model.plan import Feature
from dagobert.references import read
from dagobert.ui import fold, guard, is_mobile, mode, source, tell
from dagobert.ui.gridcolumns import on_off
from dagobert.ui.save import REFUSED, discard_form, form_not_saved, form_stale
from dagobert.ui.tables import save_in_header

if TYPE_CHECKING:
    from pathlib import Path

KEY = "features"
SAVE = f"{KEY}-save"
INTRO = N_(
    "Switch off the parts of life that your plan does not model: the app then hides them on "
    "every page."
)
ABOUT = N_(
    "A part that is off hides its pages, tabs, kinds, event types, fields, columns and sliders, "
    "in simple and in advanced mode, on every device that opens this plan: the switches are "
    "saved in `app.yaml`. A switch never changes your data, and the defaults of a hidden field "
    "still act in the simulation. A part that your plan uses stays on: its switch names where "
    "it is used. Simple and advanced mode is a choice of each browser, in the sidebar."
)


@dataclass(frozen=True)
class Base:
    """What the switches began with: the features off in `app.yaml` and the `Seen` of them."""

    off: frozenset[Feature]
    seen: revisions.Seen


def _listed(data_dir: Path) -> object:
    """The part of `app.yaml` that the page edits, as the file holds it."""
    return read(data_dir, APP).get(mode.FEATURES_OFF)


def _key(feature: Feature) -> str:
    return f"{KEY}-{feature}"


def _fresh() -> None:
    """A new start of the switches: they read `app.yaml` again."""
    for key in (f"{KEY}-base", *map(_key, Feature)):
        st.session_state.pop(key, None)


def _base(data_dir: Path) -> Base:
    """The base of the switches, kept in the session from their first run. The revision comes
    before the read: a write between the two counts as a change."""
    held: Base | None = st.session_state.get(f"{KEY}-base")
    if held is None:
        revision = revisions.last_change(data_dir, APP)
        part = _listed(data_dir)
        held = Base(mode.listed(part), revisions.Seen(APP, revision, revisions.digest(part)))
        st.session_state[f"{KEY}-base"] = held
    return held


def _edited(base: Base, uses: mode.Uses) -> bool:
    """Whether a switch that is free holds another state than its base, before it draws."""
    return any(
        st.session_state.get(_key(f), f not in base.off) == (f in base.off)
        for f in Feature
        if not uses.used(f)
    )


def _conflict(data_dir: Path, base: Base) -> revisions.ConflictError | None:
    """`forms.conflict` for the switches: they are no `Form`, their part is the listed features
    of the scenarios (`_listed`)."""
    try:
        revisions.unchanged(data_dir, base.seen, _listed(data_dir))
    except revisions.ConflictError as err:
        return err
    return None


def _switch(feature: Feature, base: Base, uses: mode.Uses) -> bool:
    """The switch of `feature`, on or off; locked on while the inputs use it, with where."""
    spec, phone = mode.FEATURES[feature], is_mobile()
    locked = uses.used(feature)
    if locked:  # a state from before the data came would show it off
        st.session_state.pop(_key(feature), None)
    on = st.toggle(
        _(spec.label),
        value=locked or feature not in base.off,
        key=_key(feature),
        disabled=locked,
        help=None if phone else _(spec.help),
    )
    if phone:  # the help icon sits in the label of a toggle: a tap on it flips the switch
        st.caption(_(spec.help))
    if where := uses.where.get(feature):
        st.caption(_("In use: {where}").format(where=", ".join(s.said() for s in where)))
    if locked and feature in base.off:
        st.caption(_("Switched off in `app.yaml`, but in use: it shows anyway."))
    return locked or on


def page(data_dir: Path) -> None:
    save_in_header(SAVE)
    st.title(_("Features"))
    st.caption(_(INTRO))
    fold(_(ABOUT), _("How the switches work"))
    uses, base = mode.uses(data_dir), _base(data_dir)
    changed = _conflict(data_dir, base)
    if changed and not _edited(base, uses):
        _fresh()
        st.rerun()
    if changed:
        form_stale(changed)
        discard_form(KEY, _fresh)
    on = {f: _switch(f, base, uses) for f in Feature}
    found = [
        guard.Change(
            pgettext("inline", mode.FEATURES[f].inline),
            on_off(f not in base.off),
            on_off(on[f]),
            unit=None,
            ratio=False,
            key=f.value,
        )
        for f in Feature
        if on[f] == (f in base.off)
    ]
    guard.review(found, key=KEY)
    _save(data_dir, base, [f for f in Feature if not on[f]], edits=bool(found), stale=bool(changed))


def _save(data_dir: Path, base: Base, off: list[Feature], *, edits: bool, stale: bool) -> None:
    """Save: the features `off` into `app.yaml` (the key goes when none is), off without `edits`
    and while the file changed since the switches began (`stale`), which the write checks
    again."""
    if not st.button(
        _("Save"),
        key=SAVE,
        type="primary",
        disabled=not edits or stale,
        help=None if edits else _("No changes to save"),
    ):
        return
    edit = store.Edit(APP, {(mode.FEATURES_OFF,): [f.value for f in off] or None})
    try:
        store.write(
            data_dir,
            [edit],
            source=source(),
            check=lambda: revisions.unchanged(data_dir, base.seen, _listed(data_dir)),
        )
    except (revisions.ConflictError, *REFUSED) as err:
        form_not_saved(err)
        return
    _fresh()
    tell(_("Saved {files}").format(files=APP))
    st.rerun()
