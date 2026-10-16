"""What a scenario file inherits through its `extends` chain: the phases and events of its
parents (`inherited`, `reach`) and the months they move by (`shifts`), a toggle per id that
leaves their items out (`leave_out`, which writes `drop`) and their read-only tables
(`read_only`, `table`), with an event in words (`TITLES`, `describe`, `when`, `said`). The Events
tab and the Phases and Timeline tabs of the Scenarios page share them."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

import streamlit as st

from dagobert import loader, revisions
from dagobert.i18n import N_, _, ngettext
from dagobert.money import decimal_mark, format_eur
from dagobert.store import Edit, RowFile
from dagobert.ui import gridcolumns, guard, is_mobile, joined, save, tables
from dagobert.ui.gridcolumns import Row

if TYPE_CHECKING:
    from pathlib import Path

# each type in plain words: the tabs, the timeline of the Scenarios page, the inherited events
TITLES = {
    "sell": N_("Sell an asset"),
    "repay": N_("Repay a loan"),
    "severance": N_("Severance pay"),
    "fund_policy": N_("Pay into a policy"),
    "lump_sum": N_("One-off payment"),
    "write_off": N_("Write off shares"),
    "end_streams": N_("End streams"),
    "set_stream": N_("Change a stream"),
    "add_stream": N_("Add a stream"),
    "buy": N_("Buy gold or crypto"),
    "buy_property": N_("Buy a property"),
    "inheritance": N_("Inheritance"),
    "gift": N_("Gift"),
}
# each type inside a sentence: the help of a toggle that leaves out an inherited event
INLINE = {
    "sell": N_("sell an asset"),
    "repay": N_("repay a loan"),
    "severance": N_("severance pay"),
    "fund_policy": N_("pay into a policy"),
    "lump_sum": N_("one-off payment"),
    "write_off": N_("write off shares"),
    "end_streams": N_("end streams"),
    "set_stream": N_("change a stream"),
    "add_stream": N_("add a stream"),
    "buy": N_("buy gold or crypto"),
    "buy_property": N_("buy a property"),
    "inheritance": N_("an inheritance"),
    "gift": N_("a gift"),
}
Chain = Sequence[tuple["Path", Mapping[str, Any]]]  # raw files of an `extends` chain, root first
DETAIL = 560  # pixels of what an item does on a desktop: a cell does not wrap a sale's condition
LEFT_OUT = N_("left out by")  # the column of an item of a parent that a file below drops
ON_CONDITION = N_("on condition")  # the month of a sale on a condition, which comes last
AT_DEATH = N_("at death")  # the month of an inheritance without one in a table of events
SET_IN = N_("set in")  # the column of the file that writes an item
THIS = N_("this scenario")  # in `SET_IN`: the file itself
# the headers of the read-only tables of phases and events by column (`read_only`), English
READ = {
    "month": N_("month"),
    "item": N_("item"),
    "detail": N_("detail"),
    "event": N_("event"),
    "what": N_("what"),
    "from": N_("from"),
    "phase": N_("phase"),
    SET_IN: SET_IN,
    LEFT_OUT: LEFT_OUT,
}


@dataclass(frozen=True)
class Inherited:
    """A phase or an event of a parent: the stem of its file, the row as written, and the stem of
    the nearest file below that drops its id (`drop`), None while none does."""

    file: str
    row: Row
    dropped: str | None


def inherited(chain: Chain, key: str = "events") -> list[Inherited]:
    """The rows `key` (`events`, `phases`) of the parents in the `extends` chain `chain` (raw, as
    `loader.chain` gives it, so a file that does not load shows too; the root first, the file
    itself last), each with the stem of its file and of the nearest file below that drops its id,
    None while none does."""
    found: list[Inherited] = []
    for n, (path, raw) in enumerate(chain[:-1]):
        gone: dict[str, str] = {}
        for below, held in chain[n + 1 :]:
            for item in _listed(held.get("drop")):
                gone.setdefault(str(item), below.stem)
        found += [
            Inherited(path.stem, row, gone.get(str(row.get("id"))))
            for row in _listed(raw.get(key))
            if isinstance(row, dict)
        ]
    return found


def reach(chain: Chain, key: str = "events") -> list[Inherited]:
    """The rows `key` of the parents that reach the file of `chain`: those that it drops itself
    too, which a toggle takes back, not those that a file between drops."""
    return [i for i in inherited(chain, key) if i.dropped in (None, chain[-1][0].stem)]


def shifts(chain: Chain, *, own: bool = True) -> dict[str, float]:
    """The `shift` of each id as a run of the last file of `chain` takes it: those of the files
    merged, the root first, so a later file replaces the months of an earlier one, less those of
    an id that a file below drops (`loader.kept`). Without `own` those of the parents alone: what
    the file inherits when it sets none."""
    found: dict[str, float] = {}
    for n, (_path, raw) in enumerate(chain if own else chain[:-1]):
        gone = {str(i) for _below, held in chain[n + 1 :] for i in _listed(held.get("drop"))}
        mine = raw.get("overrides")
        moves = loader.kept(mine if isinstance(mine, dict) else {}, gone).get("shift")
        if isinstance(moves, dict):
            found |= {str(i): m for i, m in moves.items() if isinstance(m, int | float)}
    return found


def _listed(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def either(age: str, below: str) -> str:
    """The condition of a sale in words from its parts (`age 60`, `liquid below 1.000 €`), each
    empty without it."""
    if age and below:
        return _("{age} or {below}").format(age=age, below=below)
    return age or below


def describe(row: Mapping[str, Any]) -> str:
    """What an event names or pays, in a few words: the asset, loan, policy or stream, the
    relatives of an inheritance or a gift with what they give, else its sum."""
    if givers := _givers(row):
        equity = row["equity"] if isinstance(row.get("equity"), dict) else {}
        worth = [v for v in (row.get("cash"), equity.get("value")) if isinstance(v, int | float)]
        return f"{', '.join(givers)}: {format_eur(sum(worth))}" if worth else ", ".join(givers)
    for key in ("asset", "loan", "policy", "name"):
        if isinstance(row.get(key), str):
            return str(row[key])
    for key in ("stream", "property"):  # the name of a stream, of a property also its id
        if isinstance(held := row.get(key), dict):
            return str(held.get("name") or held.get("id", ""))
    if listed := [*_listed(row.get("names")), *_listed(row.get("tags"))]:
        return ", ".join(map(str, listed))
    money = row.get("amount", row.get("gross"))
    return format_eur(money) if isinstance(money, int | float) else ""


def _givers(row: Mapping[str, Any]) -> list[str]:
    """The relatives of an inheritance or a gift as written: one name or a list."""
    givers = row.get("from")
    return [givers] if isinstance(givers, str) else [str(g) for g in _listed(givers)]


def at_death(givers: Sequence[str]) -> str:
    """When an inheritance without a month falls: at the death of its relative, of two at the
    later death."""
    if len(givers) > 1:
        return _("at the later death of {relatives}").format(relatives=joined(givers))
    return _("at the death of {relative}").format(relative=", ".join(givers))


def condition(age: object, below: object) -> str:
    """The condition of a sale in words, from its age and its `liquid_below` (None: not set)."""
    return either(
        _("age {age}").format(age=decimal_mark(f"{age:g}") if isinstance(age, int | float) else age)
        if age is not None
        else "",
        _("liquid below {amount}").format(
            amount=format_eur(below) if isinstance(below, int | float) else below
        )
        if below is not None
        else "",
    )


def when(row: Mapping[str, Any]) -> str:
    """The month of an event, or when an inheritance without one or a conditional sale falls."""
    if (at := row.get("at")) is not None:
        return str(at)[:7]
    if row.get("type") == "inheritance":
        return at_death(_givers(row))
    rule = row["when"] if isinstance(row.get("when"), dict) else {}
    return condition(rule.get("age"), rule.get("liquid_below")) or _("never")


def worded(row: Mapping[str, Any]) -> str:
    """An event in a few words: its type, when it falls and what it names, `Sell an asset
    2036-06: flat`."""
    kind = str(row.get("type"))
    event, named = _(TITLES[kind]) if kind in TITLES else kind, describe(row)
    text = _("{event} {when}: {what}") if named else _("{event} {when}")
    return text.format(event=event, when=when(row), what=named)


def month(row: Mapping[str, Any]) -> str:
    """The month of an event as the timeline and the table sort it: its own, else `AT_DEATH` for
    an inheritance, else `ON_CONDITION`."""
    if (at := row.get("at")) is not None:
        return str(at)[:7]
    return _(AT_DEATH if row.get("type") == "inheritance" else ON_CONDITION)


def detail(row: Mapping[str, Any]) -> str:
    """An event in the timeline as the rows it runs show it (`scenarios._detail`): its note or
    what it touches; of an inheritance or a gift also the givers and the sum, in brackets after
    the note; of a sale without a month its condition."""
    note = str(row.get("note") or "")
    if _givers(row):
        named = describe(row)
        return f"{note} ({named})" if note else named
    text = note or describe(row)
    return f"{text} ({when(row)})" if row.get("type") == "sell" and row.get("at") is None else text


def read_only(
    rows: Sequence[Mapping[str, Any]],
    first: str,
    *,
    wide: str = "",
    hidden: Collection[str] = (),
    scroll: bool = False,
) -> None:
    """A read-only table of phases and events, its text columns headed in the language of the
    session (`READ`, the keys `id` and `note` as the pages name them), `wide` as wide as the
    condition of a sale on a desktop (`DETAIL`: a cell does not wrap), `first` pinned on a phone,
    without the columns `hidden`. `left out by` comes before `wide`, so a dropped row shows as such
    without a scroll. It grows with its rows; with `scroll` a desktop scrolls a long one inside the
    default height."""
    config = {
        name: st.column_config.TextColumn(
            _(READ[name]) if name in READ else gridcolumns.keyword(name),
            width=("medium" if is_mobile() else DETAIL) if name == wide else None,
        )
        for name in rows[0]
    }
    tables.pin(config, first)
    order = [name for name in rows[0] if name not in hidden and name != LEFT_OUT]
    if LEFT_OUT in rows[0]:
        order.insert(order.index(wide) if wide in order else len(order), LEFT_OUT)
    st.dataframe(
        rows,
        hide_index=True,
        column_config=config,
        column_order=order,
        placeholder="",
        height="auto" if scroll and not is_mobile() else "content",
    )


def leave_out(
    data_dir: Path, name: str, ids: Sequence[str], chain: Chain, *, key: str, stale: bool = False
) -> save.Part:
    """A toggle `Leave out <id> (2 events)` per id of the items of the parents that reach the
    scenario file `name` (`ids`), its help the phases and events of that id, and what a save of
    them writes (a `save.Part`: no grid without a toggled switch), its `drop` list: the order
    kept, new ids last, the key gone when empty. The caller lists it and saves it with the Save of
    its tab, the Phases tab with its rows, the Events tab with the grid of the type open. With
    `stale` also the ids that the file drops and no item of the parents has, which keep it from
    loading. Save conflicts: the toggles keep the list that they drew while one differs
    (`save.base`); a change of it elsewhere then warns, and the part is not `ready`: Save stays
    off. The write checks again (`_drop_check`)."""
    file = RowFile(data_dir, name, ("drop",))
    items = by_id(chain)
    base, changed = save.base(file, key, list, partial(_drop_held, key, ids))
    toggles, held = f"{key}-{base.nonce}", [str(item) for item in base.rows]  # what it drops
    shown = [*ids, *(i for i in held if stale and i not in items and i not in ids)]
    if changed is not None:
        st.warning(
            _(
                "{changed} since these switches were drawn: the file now leaves out {drops}. "
                "Saving stays off: `Discard my edits` shows the file now."
            ).format(
                changed=save.changed_at(changed.error),
                drops=", ".join(map(str, changed.after)) or _("nothing"),
            ),
            icon=":material/sync_problem:",
        )
        save.discard(key)
    with st.container(horizontal=not is_mobile(), wrap=True):
        wanted = {
            item: st.toggle(
                _("Leave out {item}").format(item=named(item, items)),
                value=item in held,
                key=f"{toggles}-{item}",
                help=_("Leaves out {items}.").format(items="; ".join(map(_said, items[item])))
                if item in items
                else _(
                    "No phase or event of the parents has this id, so the scenario does not "
                    "load: switch it off."
                ),
            )
            for item in shown
        }
    toggled = {item: on for item, on in wanted.items() if on != (item in held)}
    drops = [item for item in held if toggled.get(item, True)]
    drops += [item for item, on in toggled.items() if on and item not in held]
    changes = [
        guard.Change(
            _("leave out {item}").format(item=named(i, items)), _yes(not on), _yes(on), unit=None
        )
        for i, on in toggled.items()
    ]
    edit = save.Grid(
        Edit(name, {("drop",): drops or None}), partial(_drop_check, file, base), f"{key}-nonce"
    )
    ready = changed is None or not toggled
    return save.Part((edit,) if toggled else (), tuple(changes), ready=ready)


def _yes(value: bool) -> str:
    return _("yes") if value else _("no")


def named(item: str, items: Mapping[str, Sequence[Inherited]]) -> str:
    """An id with what it leaves out: `car (2 events)`, `job-end (1 phase and 1 event)`."""
    found = items.get(item, ())
    phases = sum("phase" in i.row for i in found)
    events = len(found) - phases
    counts = [
        ngettext("{n} phase", "{n} phases", phases).format(n=phases) if phases else "",
        ngettext("{n} event", "{n} events", events).format(n=events) if events else "",
    ]
    said = (
        _("{phases} and {events}").format(phases=counts[0], events=counts[1])
        if all(counts)
        else counts[0] or counts[1]
    )
    return f"{item} ({said})" if said else item


def ids(parents: Sequence[Inherited]) -> list[str]:
    return list(dict.fromkeys(i.row["id"] for i in parents if isinstance(i.row.get("id"), str)))


def _drop_held(key: str, ids: Sequence[str], base: save.Base) -> bool:
    """Whether a toggle differs from what the file dropped when the toggles drew."""
    held = {str(item) for item in base.rows}
    return any(
        st.session_state.get(f"{key}-{base.nonce}-{item}", item in held) != (item in held)
        for item in ids
    )


def _drop_check(file: RowFile, base: save.Base) -> None:
    """Inside the write: refuse when the drops of the file changed since the toggles drew."""
    revisions.unchanged(file.data_dir, base.seen, file.rows())


def by_id(chain: Chain) -> dict[str, list[Inherited]]:
    """Per id, the phases and events of the parents with it that reach the file."""
    found: dict[str, list[Inherited]] = {}
    for item in [*reach(chain, "phases"), *reach(chain)]:
        if isinstance(name := item.row.get("id"), str):
            found.setdefault(name, []).append(item)
    return found


def _said(item: Inherited) -> str:
    """A phase or an event of a parent in words with its file: `the phase retired from 2051-06
    (plan)`, `sell an asset 2036-06: flat (plan)`."""
    row = item.row
    if "phase" in row:
        return _("the phase {phase} from {month} ({file})").format(
            phase=row["phase"], month=str(row.get("from"))[:7], file=item.file
        )
    kind = str(row.get("type"))
    said = _(INLINE[kind]) if kind in INLINE else kind
    named = describe(row)
    return (_("{event} {when}: {what} ({file})") if named else _("{event} {when} ({file})")).format(
        event=said, when=when(row), what=named, file=item.file
    )


def table(parents: list[Inherited]) -> None:
    """The inherited events by date, read only, with their file and the file below that drops
    them; the inheritances without a month (`AT_DEATH`), then the sales on a condition after the
    dated ones (`_order`)."""
    shown = [
        {
            "month": month(i.row),
            "event": _(TITLES[kind]) if (kind := str(i.row.get("type"))) in TITLES else kind,
            "what": describe(i.row) if timed else f"{describe(i.row)} ({when(i.row)})",
            "id": i.row.get("id"),
            "note": i.row.get("note", ""),
            SET_IN: i.file,
            LEFT_OUT: i.dropped,
        }
        for i in sorted(parents, key=_order)
        for timed in [i.row.get("at") is not None or i.row.get("type") == "inheritance"]
    ]
    read_only(shown, "month", wide="what", scroll=True)


def _order(item: Inherited) -> tuple[bool, bool, str]:
    """Dated events by month, then the inheritances without one, then the sales on a condition,
    as the timeline."""
    undated = item.row.get("at") is None
    return undated, undated and item.row.get("type") != "inheritance", when(item.row)
