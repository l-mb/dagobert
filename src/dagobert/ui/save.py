"""Saving the rows of an input file: what a grid read of them (`Base`), a change of those rows
elsewhere since, the Save button, the date of each new asset value, and the sign of an amount
that is negative by its field."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import TYPE_CHECKING, Protocol

import streamlit as st

from dagobert import revisions
from dagobert.history import Observation
from dagobert.i18n import N_, _
from dagobert.store import Merge, Read, RowEdits, RowFile
from dagobert.ui import guard, joined, literal, page_said, source, tell, timezone
from dagobert.ui.gridcolumns import Row

if TYPE_CHECKING:
    from pathlib import Path

    from dagobert.model.base import KeyPath, Unit
    from dagobert.references import References
    from dagobert.ui.mode import Item

VALUE_FIELD = {"loan": "balance", "property": "per_sqm"}


def value_field(row: Row) -> str:
    return VALUE_FIELD.get(row["kind"], "value")


def worth(row: Row, value: float) -> float:
    return value * row["sqm"] if row["kind"] == "property" else value


def signed(cells: Row, negative: Iterable[KeyPath]) -> Row:
    """`cells` as saved: the numbers at the key paths `negative` below zero whatever sign was
    typed, since the keypad of a phone may have no minus. A field of a nested model sits in the
    `Merge` of its mapping (the `loan` of a purchase)."""
    out = dict(cells)
    for key, *inner in negative:
        held = out.get(key)
        if inner and isinstance(held, Merge):
            out[key] = Merge(signed(held.changes, [tuple(inner)]))
        elif not inner and isinstance(held, int | float):
            out[key] = -abs(held)
    return out


def stamp(rows: list[Row], edits: RowEdits, day: date) -> tuple[RowEdits, list[Observation]]:
    """`edits` with every new value dated (`asof` becomes `day` unless the edit sets one) and the
    observations of those values for the history."""

    def dated(row: Row, changes: Row) -> Row:
        if changes.get(value_field(row)) is None:
            return changes
        return changes | {"asof": changes.get("asof", day)}

    edited = {i: dated(rows[i], cells) for i, cells in edits.edited.items()}
    added = [dated(new, new) for new in edits.added]
    observed = [
        (cells["asof"], (dict(row) | cells)["id"], worth(dict(row) | cells, value))
        for row, cells in [*((rows[i], c) for i, c in edited.items()), *((n, n) for n in added)]
        if (value := cells.get(value_field(row))) is not None
    ]
    return replace(edits, edited=edited, added=added), observed


@dataclass(frozen=True)
class Base:
    """What a grid showed first: the rows of its file then with the other fields of the mapping
    that holds them (`RowFile.contents`), the `Seen` of its part (the rows that it shows) and the
    names of its selects. While its nonce lives the grid shows these rows, so the positions of its
    edits hold when another device adds, removes or changes rows."""

    nonce: int
    rows: list[Row]
    holder: Row
    seen: revisions.Seen
    refs: References | None = None
    # what the mode or a feature hides of the grid by the other inputs, in simple (False) and in
    # advanced mode (True), `tables._hidden`: a change of them elsewhere keeps its columns
    hidden: Mapping[bool, frozenset[Item]] = field(default_factory=dict)

    def read(self, key: tuple[str, ...]) -> Read:
        """What a save of the edits of the grid needs, rows named by the fields `key`."""
        return Read(self.rows, self.holder, self.seen.revision, key)


@dataclass(frozen=True)
class Changed:
    """The part of a grid changed since its base while the grid holds edits."""

    error: revisions.ConflictError  # the file and the revisions since
    before: list[Row]  # the part as the grid shows it
    after: list[Row]  # the part now


def kept(key: str) -> Base | None:
    """The base of the grid `key` as its last run left it, None before it drew or after a save."""
    held: Base | None = st.session_state.get(f"{key}-base")
    return held if held is not None and held.nonce == st.session_state.get(f"{key}-nonce") else None


class Generation(Protocol):
    """What grids drew first while their nonce lives: a `Base`, the overrides by id of a
    scenario (`overridegrids.Base`)."""

    @property
    def nonce(self) -> int: ...

    @property
    def seen(self) -> revisions.Seen: ...


def stays[G: Generation](
    data_dir: Path, key: str, old: G | None, now: object, held: Callable[[G], bool]
) -> tuple[G | None, revisions.ConflictError | None]:
    """Whether the base `old` of the grids `key` stays: its part unchanged since (`now`), or
    changed while the grids hold edits (`held`, read from their widget state before they draw),
    with that change. A part changed without edits starts a new nonce (`<key>-nonce`) and gives
    None: the grids start on the file now. A form knows its edits only after it draws, so it
    asks after (`forms.conflict`)."""
    if old is None:
        return None, None
    try:
        revisions.unchanged(data_dir, old.seen, now)
    except revisions.ConflictError as err:
        if held(old):
            return old, err
        st.session_state[f"{key}-nonce"] = old.nonce + 1
        return None, None
    return old, None


def base(
    file: RowFile,
    key: str,
    part: Callable[[list[Row]], list[Row]],
    held: Callable[[Base], bool],
    *,
    refs: Callable[[], References | None] = lambda: None,
    hidden: Callable[[], Mapping[bool, frozenset[Item]]] = dict,
) -> tuple[Base, Changed | None]:
    """The base of the grid `key`, whose nonce is `<key>-nonce`. It stays while the grid holds
    edits (`held`, read from its widget state before it draws), with the change of its part
    since, if any. Without edits the grid follows the file: a changed part starts a new nonce,
    and a write elsewhere in the file or a change of what the mode or a feature hides
    (`hidden`) renews the base."""
    revision = revisions.last_change(file.data_dir, file.name)  # before the read: see `digest`
    rows, holder = file.contents()
    st.session_state.setdefault(f"{key}-nonce", 0)
    old, err = stays(file.data_dir, key, kept(key), part(rows), held)
    if old is not None and err is not None:
        return old, Changed(err, part(old.rows), part(rows))
    now = hidden()
    if old is not None and ((old.seen.revision == revision and old.hidden == now) or held(old)):
        return old, None
    seen = revisions.Seen(file.name, revision, revisions.digest(part(rows)))
    new = Base(st.session_state[f"{key}-nonce"], rows, holder, seen, refs(), now)
    st.session_state[f"{key}-base"] = new
    return new, None


def renew(key: str, old: Base) -> int:
    """A new grid of `key` on the same base, for cells that come as its data (`Take estimates`):
    their positions hold. Returns its nonce."""
    nonce = st.session_state[f"{key}-nonce"] = old.nonce + 1
    st.session_state[f"{key}-base"] = replace(old, nonce=nonce)
    return nonce


def listed[T](key: str, params: object, now: T | None) -> T | None:
    """What the button of a dialog writes: the list that the run before showed for the same
    `params`, so the write refuses what changed since (`revisions.Seen` inside it), else the list
    `now`; None while `now` refuses, as the list before would still write. Keeps `now` under
    `key` for the next run."""
    held = st.session_state.get(key)
    st.session_state[key] = (params, now)
    return held[1] if now is not None and held and held[0] == params and held[1] else now


def changed_at(err: revisions.ConflictError) -> str:
    """`` `assets.yaml` changed at 14:03 on Snapshot ``, in the language of the session: each
    source of the revisions since, at the time of its last one in the time zone of the browser,
    with the date before today, its page in words (`ui.page_said`). Without a revision since, the
    file alone."""
    tz = timezone()
    today, last = datetime.now(tz).date(), {e.source: e.time.astimezone(tz) for e in err.since}

    def one(by: str, at: datetime) -> str:
        when = f"{at:%H:%M}" if at.date() == today else f"{at:%Y-%m-%d %H:%M}"
        if by == revisions.OUTSIDE:
            return _("at {time} outside the app").format(time=when)
        return _("at {time} on {page}").format(time=when, page=page_said(by))

    times = [one(*item) for item in sorted(last.items(), key=lambda item: item[1])]
    if not times:
        return _("`{file}` changed").format(file=err.file)
    return _("`{file}` changed {times}").format(file=err.file, times=joined(times))


# What a save refuses with `Not saved:`, after a `revisions.ConflictError`: a lock, a read-only
# directory (OSError), the model or the inputs (ValueError: InputError, SchemaError, and the
# `RefusedError` of a row gone since). Any other error is a bug: it shows its traceback.
REFUSED = (OSError, ValueError)
# Why a save failed, by the type of its error: a refusal of the model or the inputs stays as it
# is, English
REASONS: dict[type[Exception], str] = {
    revisions.BusyError: N_("Another save is running. Save again."),
    revisions.ReadOnlyError: N_("the data directory is read-only"),
}


def reason(err: Exception) -> str:
    """Why a save failed, in the language of the session where the app knows the error by its
    type: another save that holds the lock, a read-only data directory, a change since the page
    read the file (`changed_at`). Else the message of the error, in English, as the inputs and
    the model write it."""
    if isinstance(err, revisions.ConflictError):
        return changed_at(err)
    return next((_(text) for kind, text in REASONS.items() if isinstance(err, kind)), str(err))


def warn(
    changed: Changed,
    *,
    key: str,
    identity: Sequence[str],
    units: Mapping[str, Unit],
    names: Mapping[str, str] | None = None,
) -> None:
    """A change of the rows of the grid `key` elsewhere while it holds edits: where and when, the
    difference cell by cell (`RowEdits.between`, rows named by `identity`, cells by `names`) and
    `Discard my edits`, which starts a new grid on the rows now. A new change also shows once as a
    toast: the list above the grid can be out of view."""
    changed_there = changed_at(changed.error)
    st.warning(
        " ".join(
            [
                _("{changed} since this table was drawn.").format(changed=changed_there),
                _(
                    "The table still shows the rows as they were, with your edits. Save puts your "
                    "edits into the file as it is now, but refuses them when a row that you "
                    "edited changed there. `Discard my edits` shows the rows now."
                ),
            ]
        ),
        icon=":material/sync_problem:",
    )
    difference = RowEdits.between(changed.before, changed.after, identity)
    guard.listing(
        guard.changes(changed.before, difference, units=units, names=names),
        [guard.label(changed.before[i]) for i in difference.deleted],
        title=_("Changed there"),
    )
    shown = f"{key}-changed"  # the revisions of the last toast: a rerun does not repeat it
    if (ids := [e.id for e in changed.error.since]) != st.session_state.get(shown):
        st.toast(
            _("{changed} since this table was drawn: see above the table").format(
                changed=changed_there
            ),
            icon=":material/sync_problem:",
            duration="long",
        )
    st.session_state[shown] = ids
    discard(key)


def form_stale(changed: revisions.ConflictError) -> None:
    """The warning above a form whose part changed on disk since it was drawn."""
    st.warning(
        _(
            "{changed} since this form was drawn. Your edits stay, but Save refuses them: "
            "discard them to see the file as it is now."
        ).format(changed=changed_at(changed)),
        icon=":material/sync_problem:",
    )


def discard_form(key: str, fresh: Callable[..., None], *args: object) -> None:
    """`Discard my edits` of the form `key`: `fresh(*args)` starts a new generation on the file."""
    st.button(_("Discard my edits"), key=f"{key}-discard", on_click=fresh, args=args)


def form_not_saved(err: Exception) -> None:
    """The error of a refused save of a form: a conflict or a `REFUSED` one."""
    if isinstance(err, revisions.ConflictError):
        st.error(
            _("Not saved: {changed} since this form was drawn").format(changed=changed_at(err))
        )
    else:
        lines = "  \n".join(map(literal, reason(err).splitlines()))
        st.error(_("Not saved: {reason}").format(reason=lines))


def discard(key: str) -> None:
    """`Discard my edits` of the grid `key`: a new nonce (`<key>-nonce`), which shows the rows
    now."""
    if st.button(_("Discard my edits"), key=f"{key}-discard"):
        st.session_state[f"{key}-nonce"] += 1
        st.rerun()


def button(
    file: RowFile,
    edits: RowEdits,
    observed: list[Observation],
    *,
    read: Read,
    label: str,
    key: str,
    nonce_key: str,
    toast: str,
    flagged: bool,
) -> None:
    """The Save button: write `edits` of the rows `read` and `observed` into the history as one
    revision, bump the nonce and rerun. The edits go onto the rows of the file then, row by row;
    a row that they change and that changed since refuses the save and keeps the edits. A failed
    write shows the error instead of saving (`reason`). The caller lists the edits first
    (`guard.check`) with the rows it holds, and its label carries a mark while one of them has a
    warning (`flagged`)."""
    if st.button(guard.marked(label, flagged), key=key, disabled=not edits, type="primary"):
        try:
            file.apply(edits, source=source(), observed=observed, read=read)
        except revisions.ConflictError as err:
            text = _("Not saved: {changed}, in a row that you edited").format(
                changed=changed_at(err)
            )
            more = _(
                "The list above the table shows the change. `Discard my edits` shows the rows now."
            )
            st.error(f"{text}. {more}")
            st.toast(text, icon=":material/sync_problem:", duration="long")
        except REFUSED as err:
            st.error(_("Not saved: {reason}").format(reason=reason(err)))
        else:
            st.session_state[nonce_key] += 1
            tell(toast)
            st.rerun()
