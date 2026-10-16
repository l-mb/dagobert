"""The `Phases` tab of the Scenarios page: the phase changes of a scenario file as a grid (each
phase by its label, the age beside the month, the ids in advanced mode), a warning where a new row
repeats an inherited change with the offer to move that one instead, and the changes of the
parents: their months to move (a `shift` of their id) and the toggles that leave them out. One
Save writes them all as one revision."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import partial
from itertools import chain as chained
from itertools import count
from typing import TYPE_CHECKING, Any

import pandas as pd
import streamlit as st

from dagobert import loader, references, revisions, scenariofiles
from dagobert.i18n import N_, _
from dagobert.model.base import KeyPath
from dagobert.model.months import add_months, months_between, months_of_age
from dagobert.model.plan import Scenario
from dagobert.problems import InputError, Keys
from dagobert.references import Kind
from dagobert.store import Edit
from dagobert.ui import at_age, fold, guard, lineage, literal, mode
from dagobert.ui import fields as model_fields
from dagobert.ui.fileactions import KEY
from dagobert.ui.forms import Form, Shown, save, show
from dagobert.ui.gridcolumns import Row, keyword
from dagobert.ui.gridstate import drawn, grid_state, touched
from dagobert.ui.lineage import LEFT_OUT, READ, SET_IN, Chain, Inherited
from dagobert.ui.save import Grid, form_stale
from dagobert.ui.tables import Computed, known, pin, save_in_header

if TYPE_CHECKING:
    from pathlib import Path

PHASES: KeyPath = ("phases",)
FIELD = next(f for f in model_fields.of(Scenario) if f.path == PHASES)
PHASE_HELP = N_("The Assumptions page defines them.")
AGE = N_("age")  # the read-only column of the age in the month of a phase change
IDS = N_("ids")  # what simple mode hides in the grids of the tab
INHERITED_HELP = N_(
    "The phase changes of the scenarios that this one extends, which it runs too. Type another "
    "month in a row to move that change here: the scenario saves a move of its id (`shift` in "
    "its overrides), and the events with that id move with it. The scenario that holds the "
    "change keeps it as it is. Empty the month to take the month of the parent again. A change "
    "without an id does not move: change it in its own scenario. The switches above leave out "
    "every phase change and event of an id."
)


def month_of(value: object) -> date | None:
    """A month of a raw file on its first day: a date, or a text `2051-06` or `2051-06-01`."""
    if isinstance(value, date):
        return value.replace(day=1)
    try:
        return date.fromisoformat(f"{str(value)[:7]}-01")
    except ValueError:
        return None


def age(birth: date | None, month: object) -> str:
    """The age in whole years at the start of `month`, empty without the birth or the month."""
    day = month_of(month) if month is not None else None
    return "" if birth is None or day is None else str(months_of_age(birth, day) // 12)


def grid_field(labels: Mapping[str, str]) -> model_fields.Field:
    """The `phases` field of a scenario file: its `phase` a select of the phases of
    `assumptions.yaml` in their order, shown by their labels as written (`references.phases`)."""
    return replace(
        FIELD,
        columns=tuple(
            replace(
                c, options=tuple(labels), words=tuple(labels.items()), more=(*c.more, PHASE_HELP)
            )
            if c.name == "phase"
            else c
            for c in FIELD.columns
        ),
    )


FROM = next(c for c in FIELD.columns if c.name == "from")


def phase_ids(taken: Collection[str]) -> Callable[[Row], dict[str, str]]:
    """The id of a phase change that a save of the tab writes without one: its phase (`retired`),
    else with the year of its month (`retired-2051`), else numbered, none that the chain
    (`taken`) or this save holds. The seek `Stop working` and the month sliders of the Explorer
    move a change by its id."""
    used = set(taken)

    def fill(row: Row) -> dict[str, str]:
        if row.get("id") or not (phase := row.get("phase")):
            return {}
        year = f"{phase}-{str(row.get('from', ''))[:4]}"
        made = next(
            i
            for i in chained([str(phase), year], (f"{year}-{n}" for n in count(2)))
            if i not in used
        )
        used.add(made)
        return {"id": made}

    return fill


@dataclass(frozen=True)
class Moving:
    """A phase change of a parent (`lineage.Inherited`), its month as the parent writes it (`raw`)
    and as the run of the file sees it (`month`): moved by the `shift` of its id in the chain,
    unless a file below drops it."""

    item: Inherited
    raw: date | None
    month: date | None

    @property
    def id(self) -> str:
        return str(self.item.row.get("id") or "")

    @property
    def phase(self) -> str:
        return str(self.item.row.get("phase") or "")

    @property
    def movable(self) -> bool:
        """It moves by a `shift` of the file: it has an id and a month, and no file drops it."""
        return bool(self.id) and self.raw is not None and self.item.dropped is None


def moving(chain: Chain) -> list[Moving]:
    """The phase changes of the parents in the raw chain `chain` by their month as the run of the
    last file sees it (`lineage.shifts`), those of one month the root first, a change without a
    month last: a timeline, whatever file holds them."""
    moves = lineage.shifts(chain)
    found = []
    for item in lineage.inherited(chain, "phases"):
        raw = month_of(item.row.get("from"))
        shift = moves.get(str(item.row.get("id"))) if item.dropped is None else None
        month = add_months(raw, round(shift)) if raw is not None and shift is not None else raw
        found.append(Moving(item, raw, month))
    return sorted(found, key=lambda m: (m.month is None, m.month or date.min))


def shifted(
    rows: Sequence[Moving], typed: Mapping[int, date | None], inherited: Mapping[str, float]
) -> dict[str, tuple[Moving, date, int | None]]:
    """What the months typed into the inherited rows (`typed` by row, None for an emptied cell:
    the parents' month) save, by id: the row, its new month, and the `shift` of the file, the
    months from the month that the parent writes, None where that is what the parents give
    (`inherited`): the file then sets none. A row that does not move (`Moving.movable`) or keeps
    its month saves nothing; of two rows of one id the first."""
    out: dict[str, tuple[Moving, date, int | None]] = {}
    for i, typed_month in sorted(typed.items()):
        row = rows[i]
        if not row.movable or row.id in out or row.raw is None:
            continue
        given = inherited.get(row.id, 0)
        month = typed_month or add_months(row.raw, round(given))
        if month == row.month:
            continue
        months = months_between(row.raw, month)
        out[row.id] = (row, month, None if months == given else months)
    return out


def along(
    rows: Sequence[Moving],
    typed: Mapping[int, date | None],
    found: Mapping[str, tuple[Moving, date, int | None]],
) -> list[tuple[Moving, date, bool]]:
    """The other rows of each id that `found` moves (`shifted`): an id moves as one, so each moves
    by as many months as the row that moves it, which the grid does not show until the save. Each
    with its new month and whether another month was typed into it (`typed`), which does not
    count."""
    return [
        (row, then, i in typed and typed[i] != then)
        for i, row in enumerate(rows)
        if row.id in found
        and row.raw is not None
        and (first := found[row.id][0]) is not row
        and first.raw is not None
        for then in [add_months(row.raw, months_between(first.raw, found[row.id][1]))]
    ]


def repeats(added: Sequence[Row], rows: Sequence[Moving]) -> dict[int, Moving]:
    """The new rows (by their place in `added`) with a month that repeat a phase change of the
    parents that runs: the same phase, not left out. A change with an id comes first: it can
    move instead."""
    return {
        n: found
        for n, row in enumerate(added)
        if row.get("from") and row.get("phase")
        for found in [
            next(
                (
                    r
                    for r in sorted(rows, key=lambda r: not r.movable)
                    if r.phase == row["phase"] and r.item.dropped is None
                ),
                None,
            )
        ]
        if found is not None
    }


def _added(shown: Shown) -> list[Row]:
    """The rows that a save of the form adds: of a list of the file its new rows, else the list."""
    if (edits := shown.typed.rows.get(PHASES)) is not None:
        return edits.added
    held = shown.edits.get(PHASES)
    return [r for r in held if isinstance(r, dict)] if isinstance(held, list) else []


def _without(shown: Shown, gone: Collection[int]) -> Shown:
    """The form without the new rows `gone` (by their place in `_added`): their change moves the
    inherited one instead. The grid keeps showing them until the save starts it anew."""
    if not gone:
        return shown
    kept = [row for n, row in enumerate(_added(shown)) if n not in gone]
    if (edits := shown.typed.rows.get(PHASES)) is not None:
        rows = shown.typed.rows | {PHASES: replace(edits, added=kept)}
        return replace(shown, typed=replace(shown.typed, rows=rows))
    others = {path: v for path, v in shown.edits.items() if path != PHASES}
    return replace(shown, edits=others | ({PHASES: kept} if kept else {}))


@dataclass(frozen=True)
class Placed:
    """The inherited phase changes as their grid drew them first in its generation (`nonce`), and
    the `Seen` of what places them in each file of the chain (`_placing`)."""

    rows: tuple[Moving, ...]
    seen: tuple[revisions.Seen, ...]
    nonce: int


def _placing(raw: Mapping[str, Any]) -> dict[str, Any]:
    """What places the phase changes of a raw scenario file: its phases, drops and shifts."""
    own = raw.get("overrides")
    return {
        "phases": raw.get("phases"),
        "drop": raw.get("drop"),
        "shift": own.get("shift") if isinstance(own, dict) else None,
    }


def _check(data_dir: Path, seen: Sequence[revisions.Seen]) -> None:
    """Raise `revisions.ConflictError` when a file of the chain moved its phase changes since."""
    for one in seen:
        revisions.unchanged(data_dir, one, _placing(references.read(data_dir, one.file)))


def typed_moves(
    rows: Sequence[Moving],
    cells: Mapping[int, str],
    inherited: Mapping[str, float],
    labels: Mapping[str, str],
) -> tuple[dict[str, tuple[Moving, date, int | None]], list[str]]:
    """What the months typed into the inherited rows (`cells` by row, empty: the parents' month)
    save (`shifted`), and the notes of the save guard: a row that does not move, a text that is
    no month (it keeps its month), and the other rows of an id that moves (`along`)."""
    typed = {i: month_of(text) if text else None for i, text in cells.items()}

    def said(row: Moving) -> dict[str, str]:  # as the grid shows it
        month = f"{row.month:%Y-%m}" if row.month else str(row.item.row.get("from") or "")[:7]
        return {"phase": labels.get(row.phase, row.phase), "month": month}

    notes = [
        (
            _("{phase} from {month} has no id, so it does not move: change it in {file}")
            if not r.id
            else _("{phase} from {month} is left out, so it does not move")
        ).format(**said(r), file=r.item.file)
        for i in typed
        if not (r := rows[i]).movable
    ]
    notes += [
        _("{phase} from {month}: {typed} is no month, so it does not move").format(
            **said(rows[i]), typed=text
        )
        for i, text in cells.items()
        if text and typed[i] is None and rows[i].movable
    ]
    read = {i: month for i, month in typed.items() if month or not cells[i]}
    found = shifted(rows, read, inherited)
    notes += [
        (
            _("{id} moves as one: {phase} from {month} moves to {then}, not to the month typed")
            if retyped
            else _("{id} moves as one: {phase} from {month} moves to {then} too")
        ).format(id=row.id, **said(row), then=f"{then:%Y-%m}")
        for row, then, retyped in along(rows, read, found)
    ]
    return found, notes


@dataclass(frozen=True)
class Moves:
    """What the grid of the inherited phase changes saves: the shifts by id with their rows and
    months (`shifted`), the notes of edits that it cannot take, the check of the write, the key of
    its nonce, and whether a save may take it (not while the chain changed under its edits)."""

    shifts: dict[str, tuple[Moving, date, int | None]]
    notes: list[str]
    check: Callable[[], None]
    nonce: str
    ready: bool = True


def _placed(data_dir: Path, path: Path, key: str) -> tuple[Placed, Chain]:
    """The base of the grid `key` of the inherited changes of `path` and the raw chain now. The
    revision of each file is taken before its read: a write between counts as a change."""
    names = [scenariofiles.scenario_file(p.stem) for p in scenariofiles.scenario_paths(data_dir)]
    before = {name: revisions.last_change(data_dir, name) for name in names}
    chain = loader.chain(path)
    now = tuple(
        revisions.Seen(
            file := scenariofiles.scenario_file(p.stem),
            before.get(file),
            revisions.digest(_placing(raw)),
        )
        for p, raw in chain
    )
    nonce = st.session_state.setdefault(f"{key}-nonce", 0)
    held: Placed | None = st.session_state.get(f"{key}-base")
    if held is None or held.nonce != nonce:
        held = st.session_state[f"{key}-base"] = Placed(tuple(moving(chain)), now, nonce)
    return held, chain


def _moves(
    data_dir: Path, path: Path, key: str, labels: Mapping[str, str], view: mode.View
) -> tuple[Moves, Chain]:
    """The grid of the inherited phase changes: `from` takes a month, the rest is read only. A
    change of the chain since it drew starts it anew while it holds no edit; with an edit a
    warning offers to discard it, and Save stays off. Returns what it saves, the rows now and the
    chain."""
    birth = references.born(data_dir)
    base, chain = _placed(data_dir, path, key)
    widget = f"{key}-{base.nonce}"
    state = grid_state(widget, len(base.rows))
    changed = None
    try:
        _check(data_dir, base.seen)
    except revisions.ConflictError as err:
        if not touched(state):
            st.session_state[f"{key}-nonce"] = base.nonce + 1
            base, chain = _placed(data_dir, path, key)
            widget, state = f"{key}-{base.nonce}", {}
        else:
            changed = err
    rows = list(base.rows)
    if changed is not None:
        form_stale(changed)
        if st.button(_("Discard my edits"), key=f"{key}-discard"):
            st.session_state[f"{key}-nonce"] += 1
            st.rerun()
    data = pd.DataFrame(
        [
            {
                "from": f"{r.month:%Y-%m}" if r.month else "",
                "age": age(birth, r.month),
                "phase": labels.get(r.phase, r.phase),
                "id": r.id,
                SET_IN: r.item.file,
                LEFT_OUT: r.item.dropped or "",
            }
            for r in rows
        ]
    )
    config = {name: st.column_config.TextColumn(_(READ[name]), disabled=True) for name in READ}
    config |= {
        "from": FROM.config(),
        "age": st.column_config.TextColumn(_(AGE), disabled=True),
        "id": st.column_config.TextColumn(keyword("id"), disabled=True),
    }
    pin(config, "from")
    dropped = any(r.item.dropped for r in rows)
    order = [
        "from",
        "age",
        "phase",
        *(["id"] if view.advanced else []),
        *([LEFT_OUT] if dropped else []),
        SET_IN,
    ]
    drawn({widget: len(rows)})
    st.data_editor(
        data,
        column_config=config,
        column_order=order,
        disabled=[c for c in data.columns if c != "from"],
        num_rows="fixed",
        hide_index=True,
        height="content",
        placeholder="",
        key=widget,
    )
    cells = {
        int(i): str(edit["from"] or "")
        for i, edit in grid_state(widget, len(rows)).get("edited_rows", {}).items()
        if "from" in edit
    }
    found, notes = typed_moves(rows, cells, lineage.shifts(chain, own=False), labels)
    check = partial(_check, data_dir, base.seen)
    return Moves(found, notes, check, f"{key}-nonce", ready=changed is None), chain


def _moved(
    found: Mapping[str, tuple[Moving, date, int | None]], chain: Chain, birth: date | None
) -> list[guard.Change]:
    """The save guard of the moves: `move retirement (1 phase and 2 events)` from the month of the
    run to the new one, each with the age."""
    items = lineage.by_id(chain)
    return [
        guard.Change(
            _("move {item}").format(item=lineage.named(i, items)),
            at_age(row.month, birth) if row.month else None,
            at_age(month, birth),
            unit=None,
        )
        for i, (row, month, _shift) in found.items()
    ]


def tab(data_dir: Path, path: Path, view: mode.View) -> None:
    """The Phases tab of the scenario file `path`: its grid, the warnings of new rows that repeat
    an inherited change, the inherited changes to move or leave out, and one Save of them all."""
    stem, file = path.stem, scenariofiles.scenario_file(path.stem)
    key = f"{KEY}phases-{stem}"
    save_in_header(f"{key}-save")
    labels, birth = references.phases(data_dir), references.born(data_dir)
    form = Form(
        key,
        file,
        (grid_field(labels),),
        Scenario,
        hides={} if view.advanced else {PHASES: frozenset({"id"})},
        computed={PHASES: (Computed("age", AGE, "from", lambda row: age(birth, row.get("from"))),)},
    )
    shown = show(data_dir, form)
    chain: Chain = [(path, {})]
    try:
        chain = loader.chain(path)
    except InputError as err:
        st.error(str(err))
    rows = moving(chain)
    instead = _instead(key, _added(shown), rows, Said(labels, birth, chain))
    shown = _without(shown, instead)
    held = [r for r in shown.candidate.get("phases") or [] if isinstance(r, dict)]
    taken = {*known(data_dir).names(Kind.ITEM, stem), *(r.get("id") for r in held)}
    shown = shown.fill(PHASES, phase_ids({str(i) for i in taken if i}))
    if not view.advanced:
        mode.hidden_note([_(IDS)], (), held=mode.Held.KINDS)
    grids: list[Grid] = []
    changes, notes, ready = shown.changes(), [], True
    if rows:
        st.markdown(f"**{_('Inherited phases')}**")
        ids = list(dict.fromkeys(r.id for r in rows if r.id and r.item.dropped in (None, stem)))
        leave = lineage.leave_out(data_dir, file, ids, chain, key=f"{key}-drop")
        moves, chain = _moves(data_dir, path, f"{key}-move", labels, view)
        fold(_(INHERITED_HELP), _("About inherited phases"))
        found = moves.shifts | {
            row.id: (row, month, _months(row, month, chain)) for row, month in instead.values()
        }
        if found:
            shifts: dict[Keys, int | None] = {
                ("overrides", "shift", i): months for i, (_r, _m, months) in found.items()
            }
            grids.append(Grid(Edit(file, shifts), moves.check, moves.nonce))
        grids += leave.grids
        changes += [*_moved(found, chain, birth), *leave.changes]
        notes, ready = moves.notes, moves.ready and leave.ready
    save(
        data_dir,
        [shown],
        grids,
        key=f"{key}-save",
        flagged=guard.review(changes, key=key, notes=notes),
        action=stem,
        ready=ready,
    )


def _months(row: Moving, month: date, chain: Chain) -> int | None:
    """The `shift` of the file that moves `row` to `month`: None where the parents give it."""
    given = lineage.shifts(chain, own=False).get(row.id, 0)
    months = months_between(row.raw, month) if row.raw else 0
    return None if months == given else months


@dataclass(frozen=True)
class Said:
    """What the warnings of the tab say a phase change with: the labels of the phases, the date
    of birth for the age, the raw chain for what an id names."""

    labels: Mapping[str, str]
    birth: date | None
    chain: Chain


def _instead(
    key: str, added: Sequence[Row], rows: Sequence[Moving], said: Said
) -> dict[int, tuple[Moving, date]]:
    """A warning per new row that repeats an inherited phase change (`repeats`): the run keeps
    that change. Where it moves, a toggle moves it to the month of the new row instead of adding
    the row. Returns the new rows that a move replaces, by their place, with the change and its
    new month."""
    nonce = st.session_state.get(f"{key}-nonce", 0)
    items = lineage.by_id(said.chain)
    out: dict[int, tuple[Moving, date]] = {}
    seen: Counter[tuple[str, date]] = Counter()
    for n, found in repeats(added, rows).items():
        if (month := month_of(added[n]["from"])) is None or found.month is None:
            continue
        # keyed by what the row says, not by its place: a row deleted above moves the places
        seen[found.phase, month] += 1
        toggle = f"{key}-instead-{nonce}-{found.phase}-{month:%Y-%m}-{seen[found.phase, month]}"
        text = _(
            "The new change to {phase} in {month} repeats the change to {phase} of {file} in "
            "{then}, which stays."
        ).format(
            phase=literal(said.labels.get(found.phase, found.phase)),
            month=f"{month:%Y-%m}",
            file=found.item.file,
            then=f"{found.month:%Y-%m}",
        )
        if not found.movable:
            st.warning(
                f"{text} {_('It has no id, so it does not move here.')}", icon=":material/warning:"
            )
            continue
        st.warning(text, icon=":material/warning:")
        if st.toggle(
            _("Move {item} to {month} instead").format(
                item=lineage.named(found.id, items), month=at_age(month, said.birth)
            ),
            key=toggle,
            help=_("Saves a move of the inherited change and leaves out the new row."),
        ):
            out[n] = (found, month)
    return out
