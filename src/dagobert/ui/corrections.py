"""`Correct a recorded month` on the Snapshot page: change or remove values of `history.csv` that
were recorded by mistake, through the save guard, as one revision. The value in `assets.yaml`
stays: the grid of the page records a new one."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd
import streamlit as st

from dagobert import history, revisions
from dagobert.history import Observation
from dagobert.i18n import N_, _, ngettext
from dagobert.money import EUR_COLUMN
from dagobert.ui import guard, is_mobile, source, tell
from dagobert.ui.save import REFUSED, changed_at, discard, reason, stays

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, Sequence
    from datetime import date
    from pathlib import Path

KEY = "snapshot-correct"  # the grid: its nonce, its base
REMOVE = "remove"
COLUMNS = ("date", "asset", "value", REMOVE)
PHONE_COLUMNS = ("date", "value", REMOVE, "asset")  # what to edit in view, a long name after it
ABOUT = N_(
    "Change or remove a value that you recorded by mistake. The charts of your records take the "
    "correction. The value in your inputs, **current** above, stays: record it again above, or "
    "change it on the Assets page."
)
VALUE_HELP = N_("As recorded: a property its full value, a loan its balance below zero")
Fixes = dict[int, float | None]  # a new value or a removal (None) by the place in the month


@dataclass(frozen=True)
class Base:
    """The rows of a month as the grid first showed them, while its nonce lives: the places of
    its edits hold when another device records into the month."""

    nonce: int
    month: date
    seen: revisions.Seen
    rows: list[Observation]


def corrections(
    rows: Sequence[Observation], edited: Mapping[int, Mapping[str, Any]], loans: Collection[str]
) -> Fixes:
    """The corrections of the grid by the place of a row: a ticked `remove` removes it, a new value
    replaces it, saved below zero for a loan whatever sign is typed. An emptied cell or the value
    as recorded is none."""
    fixes: Fixes = {}
    for place, cells in edited.items():
        value = cells.get("value")
        if cells.get(REMOVE):
            fixes[place] = None
        elif value is not None and not pd.isna(value):
            _day, asset, old = rows[place]
            new = round(-abs(value) if asset in loans else float(value), 2)
            if new != old:
                fixes[place] = new
    return fixes


def listed(
    rows: Sequence[Observation], fixes: Fixes, names: Mapping[str, str]
) -> tuple[list[guard.Change], list[str]]:
    """The lines of the save guard: each changed value old to new, each removed row, by its date
    and its asset."""
    label = {p: f"{rows[p][0]} {names.get(rows[p][1], rows[p][1])}" for p in fixes}
    changed = [
        guard.Change(label[p], rows[p][2], value)
        for p, value in sorted(fixes.items())
        if value is not None
    ]
    return changed, [label[p] for p, value in sorted(fixes.items()) if value is None]


def section(data_dir: Path, assets: Sequence[Mapping[str, Any]]) -> None:
    """The expander: a month with a record, its values in a grid with `remove`, the save guard
    (a removal warns) and `Save the correction`. `assets`: the rows of `assets.yaml`, which name
    the assets and tell the loans."""
    revision = revisions.last_change(data_dir, history.FILE)  # before the read: see `digest`
    if not (observed := history.read_history(data_dir)):
        return
    with st.expander(_("Correct a recorded month"), key=f"{KEY}-open", icon=":material/edit:"):
        st.caption(_(ABOUT))
        month = st.selectbox(
            _("Month"),
            history.months(observed),
            format_func=lambda m: f"{m:%Y-%m}",
            key=f"{KEY}-month",
            width=200,
        )
        base, changed = _base(data_dir, month, history.of_month(observed, month), revision)
        if changed is not None:
            st.warning(
                _(
                    "{changed} since this table was drawn. Save refuses your edits: discard them "
                    "to see the month as it is now."
                ).format(changed=changed_at(changed)),
                icon=":material/sync_problem:",
            )
            discard(KEY)
        names = {str(a["id"]): str(a.get("name") or a["id"]) for a in assets}
        widget = _widget(base)
        st.data_editor(
            pd.DataFrame(
                {
                    "date": [day.isoformat() for day, _a, _v in base.rows],
                    "asset": [names.get(asset, asset) for _d, asset, _v in base.rows],
                    "value": pd.Series([value for _d, _a, value in base.rows], dtype=float),
                    REMOVE: pd.Series([False] * len(base.rows), dtype=bool),
                }
            ),
            disabled=["date", "asset"],
            column_config={
                "date": st.column_config.TextColumn(_("date")),
                "asset": st.column_config.TextColumn(_("asset")),
                "value": st.column_config.NumberColumn(
                    _("value"), format=EUR_COLUMN, help=_(VALUE_HELP)
                ),
                REMOVE: st.column_config.CheckboxColumn(
                    _("remove"), help=_("Removes the recorded value")
                ),
            },
            column_order=PHONE_COLUMNS if is_mobile() else COLUMNS,
            hide_index=True,
            height="content",
            width="content",
            key=widget,
        )
        edited = {int(i): c for i, c in st.session_state[widget].get("edited_rows", {}).items()}
        loans = {str(a["id"]) for a in assets if a["kind"] == "loan"}
        fixes = corrections(base.rows, edited, loans)
        found, removed = listed(base.rows, fixes, names)
        gone = len(removed)
        flagged = guard.review(
            found,
            removed,
            key=KEY,
            notes=[
                ngettext(
                    "{n} recorded value goes: the charts of your records lose it",
                    "{n} recorded values go: the charts of your records lose them",
                    gone,
                ).format(n=gone)
            ]
            if gone
            else [],
        )
        if st.button(
            guard.marked(_("Save the correction"), flagged),
            key=f"{KEY}-save",
            disabled=not fixes or changed is not None,
        ):
            _save(data_dir, base, fixes)


def _widget(base: Base) -> str:
    return f"{KEY}-{base.month:%Y-%m}-{base.nonce}"


def _held(base: Base) -> bool:
    return bool(st.session_state.get(_widget(base), {}).get("edited_rows"))


def _base(
    data_dir: Path, month: date, now: list[Observation], revision: str | None
) -> tuple[Base, revisions.ConflictError | None]:
    """The base of the grid of `month`: it stays while the grid holds edits, with the change of
    the month since, if any (`save.stays`); without edits the grid follows the file."""
    nonce = st.session_state.setdefault(f"{KEY}-nonce", 0)
    kept: Base | None = st.session_state.get(f"{KEY}-base")
    if kept is not None and (kept.nonce, kept.month) != (nonce, month):
        kept = None
    old, err = stays(data_dir, KEY, kept, now, _held)
    if old is not None and (err is not None or old.seen.revision == revision or _held(old)):
        return old, err
    seen = revisions.Seen(history.FILE, revision, revisions.digest(now))
    new = Base(st.session_state[f"{KEY}-nonce"], month, seen, now)
    st.session_state[f"{KEY}-base"] = new
    return new, None


def _save(data_dir: Path, base: Base, fixes: Fixes) -> None:
    """Write `fixes` into the month as one revision, refused when its rows changed since the grid
    drew; then a new grid."""

    def edit() -> revisions.Texts:
        rows = history.of_month(history.read_history(data_dir), base.month)
        revisions.unchanged(data_dir, base.seen, rows)
        return history.corrected(data_dir, base.month, fixes)

    try:
        revisions.write(data_dir, source(f"correct {base.month:%Y-%m}"), edit)
    except revisions.ConflictError as err:
        st.error(
            _("Not saved: {changed} since this table was drawn").format(changed=changed_at(err))
        )
        return
    except REFUSED as err:
        st.error(_("Not saved: {reason}").format(reason=reason(err)))
        return
    st.session_state[f"{KEY}-nonce"] += 1
    tell(_("Corrected {month}").format(month=f"{base.month:%Y-%m}"))
    st.rerun()
