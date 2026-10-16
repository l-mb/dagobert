"""The events of one scenario file, the `Events` tab of the Scenarios page (`tab`): a tab per event
type, named in plain words (`TITLES`), with the form `Add an event` and the grid of the events of
the file (`tables.edit_table`), under the grid of the sales the repayments of one sale, and below
the types the events that the file inherits through `extends`, with a toggle per id that leaves
its items out (`drop`), then the events read only with their file. Each Save is one revision
through the save guard, refused when what it changes changed elsewhere since it was
drawn."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cached_property, partial
from itertools import chain, count
from pathlib import PurePosixPath
from string import Template
from typing import TYPE_CHECKING, Any, get_args

import streamlit as st

from dagobert import loader, references
from dagobert.i18n import N_, _, pgettext
from dagobert.model.base import Unit, description
from dagobert.model.events import Event, EventBase, InvestAction, RepayAction
from dagobert.model.streams import SAVINGS_TARGETS
from dagobert.problems import InputError
from dagobert.references import Kind, References
from dagobert.scenariofiles import scenario_file
from dagobert.store import RowEdits, RowFile, keyed
from dagobert.ui import (
    fields,
    fold,
    forms,
    gridcolumns,
    gridstate,
    guard,
    lineage,
    literal,
    mode,
    save,
    slug,
    tables,
)
from dagobert.ui.gridcolumns import Row, on_off
from dagobert.ui.lineage import (
    INLINE,
    TITLES,
    Chain,
    Inherited,
    describe,
    inherited,
    reach,
    when,
)
from dagobert.ui.tables import Ref, Table, edit_table
from dagobert.ui.widgets import Names

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from dagobert.model.base import KeyPath

TYPES: dict[str, type[EventBase]] = {
    get_args(model.model_fields["type"].annotation)[0]: model
    for model in get_args(get_args(Event)[0])
}
BUY_PROPERTY = "buy_property"
# the columns of a type whose nested models hold rare fields, by column name: `property name`. A
# purchase shows what tells it apart, so the grid fits a desktop without a sideways scroll
FIELDS = {BUY_PROPERTY: ("property name", "price", "land", "loan balance")}
# the rare fields of a type, behind `All columns` of its grid
MORE = {
    "sell": ("price_stdev", "costs", "taxable", "end_tagged"),
    "severance": ("bav",),
    "set_stream": ("factor", "premium"),
    BUY_PROPERTY: (
        *("property id", "transfer_tax", "costs", "property growth", "property upkeep"),
        *("property tags", "property building_share", "property afa"),
        *("loan id", "loan name", "loan rate", "loan annuity", "loan fixed_for"),
        "loan prepayment_penalty",
    ),
}
# the headers of the event grids by column name, the labels of the form by key path: English,
# marked for the catalogue, said in the language of the session by the grids and the forms
HEADERS = {
    "at": N_("month"),
    "when age": N_("or at age"),
    "when liquid_below": N_("or when liquid below"),
    "share": N_("share sold"),
    "price_stdev": N_("price spread"),
    "costs": N_("sale costs"),
    "end_tagged": N_("ends tagged streams"),
    "bav policy": N_("into bAV policy"),
    "bav amount": N_("bAV amount"),
    "land": N_("Bundesland"),
    "transfer_tax": N_("or transfer tax"),
    "loan balance": N_("loan amount"),
    "loan fixed_for": N_("loan fixed for (months)"),
    "from": N_("relatives"),
    "cash": N_("cash"),
    "equity value": N_("securities"),
    "equity cost_basis": N_("their cost basis"),
    "property building_share": N_("building share"),
    "property afa": N_("AfA rate"),
}
LABELS: dict[KeyPath, str] = {
    ("at",): N_("Month"),
    ("when", "age"): N_("Or at age"),
    ("when", "liquid_below"): N_("Or when liquid below €"),
    ("share",): N_("Share sold %"),
    ("price_stdev",): N_("Price spread %"),
    ("costs",): N_("Sale costs %"),
    ("end_tagged",): N_("Ends tagged streams"),
    ("bav", "policy"): N_("Into bAV policy"),
    ("bav", "amount"): N_("bAV amount €"),
    ("land",): N_("Bundesland"),
    ("transfer_tax",): N_("Transfer tax %"),
    ("property", "id"): N_("Property id"),
    ("property", "growth"): N_("Return of the property"),
    ("property", "building_share"): N_("Building share %"),
    ("property", "afa"): N_("AfA rate %"),
    ("loan", "id"): N_("Loan id"),
    ("loan", "balance"): N_("Loan amount €"),
    ("loan", "fixed_for"): N_("Loan fixed for (months)"),
    ("id",): N_("Event id (optional)"),
    ("from",): N_("Relatives"),
    ("cash",): N_("Cash €"),
    ("equity", "value"): N_("Value €"),
    ("equity", "cost_basis"): N_("Cost basis €"),
    # the headings of nested models that no field names
    ("property",): N_("Property"),
    ("stream", "factor"): N_("Stream factor"),
    ("equity",): N_("Securities"),
}
# the help of a field of the form where that of the model speaks of the file
HELPS: dict[KeyPath, str] = {
    ("property", "id"): N_(
        "The short name by which later sales and repayments name the property. Empty: made from "
        "its name."
    ),
    ("property", "growth"): N_(
        "The market return that the value of the property follows: a return class of the "
        "Assumptions page."
    ),
    ("loan", "id"): N_(
        "The short name by which later repayments name the loan. Empty: made from its name, else "
        "from the property."
    ),
    ("loan", "balance"): N_(
        "The amount borrowed at the purchase. Type it without a minus: the file keeps a debt "
        "below zero."
    ),
}
# a check of the model in the words of the form, by the end of its message
PLAIN = {
    "needs exactly one of `land` and `transfer_tax`": N_(
        "Choose a Bundesland or type a transfer tax, one of the two."
    )
}
EITHER = N_(  # above the form of a purchase: the model takes one of the two
    "Fill in one of Bundesland and Transfer tax: the Bundesland sets the Grunderwerbsteuer of the "
    "month, or type the rate, such as 0 for a purchase from a spouse, parents or children."
)
# above the form of a type: what its fields take that the model leaves to the reader
CAPTIONS = {
    BUY_PROPERTY: EITHER,
    "inheritance": N_(
        "Leave the month empty: the inheritance falls at the death of the relative, drawn for "
        "each simulated future from the life table, of two relatives at the later death (a "
        "Berliner Testament). The relatives are on the Assumptions page."
    ),
    "gift": N_(
        "A gift of one relative in a month. Where an inheritance without a month draws the death "
        "of the relative before it, the gift joins that inheritance."
    ),
}
# by column name: the ids that other events name stay in a saved row (`Rename` changes them with
# their uses), a loan is saved negative whatever sign is typed, as in the grids of the Assets
# page, and shows as the amount borrowed
LOCKED = {BUY_PROPERTY: ("property id", "loan id")}
NEGATIVE = {BUY_PROPERTY: ("loan balance",)}
LOAN_BALANCE: KeyPath = ("loan", "balance")  # of the form: typed without a minus
# the headers and labels of one type where its field means another thing: the costs of a purchase
TYPE_HEADERS = {BUY_PROPERTY: {"costs": N_("purchase costs")}}
TYPE_LABELS: dict[str, dict[KeyPath, str]] = {BUY_PROPERTY: {("costs",): N_("Purchase costs %")}}
ADD = "add_stream"  # its grid lifts the fields of its `stream`
FACTORS: KeyPath = ("stream", "factor")  # of an `add_stream`: a number per phase in its form
STREAM_PHASES: KeyPath = ("stream", "phases")
SELL = "sell"
# names an event among the others for a save: no field is unique, `store.keyed` counts equals
IDENTITY = ("type", "at", "id")
THEN = ("repay", "invest")  # names an action of a sale
# A type opened by a link or first: a strip scrolls only to a tapped tab, and the tab of the type
# can lie beyond its end. A one-shot script: it waits as long as the tabs take to draw, then until
# the strip shows (the Events tab may open later), and scrolls once; after 10 s it stops watching.
_REVEAL = Template("""<script>
(() => {
  const until = Date.now() + 10000;
  const watch = () => {
    const strip = document.querySelector(".$strip [role=tablist]");
    if (!strip) {
      if (Date.now() < until) requestAnimationFrame(watch);
      return;
    }
    const shown = new ResizeObserver(() => {
      const tab = strip.querySelector("[role=tab][aria-selected=true]");
      if (tab && strip.clientWidth) {
        tab.scrollIntoView({block: "nearest", inline: "nearest"});
        shown.disconnect();
      }
    });
    shown.observe(strip);
    setTimeout(() => shown.disconnect(), until - Date.now());
  };
  watch();
})();
</script>""")
LOAN = Ref(Kind.ASSET, sorts=("loan",))
POLICY = Ref(Kind.ASSET, sorts=("bav",))
# what a field names, by its key path in the event: a select in the grid and in the form
REFS: dict[str, dict[KeyPath, Ref]] = {
    SELL: {("asset",): Ref(Kind.ASSET, sorts=("property", "gold", "crypto"))},
    "buy": {("asset",): Ref(Kind.ASSET, sorts=("gold", "crypto"))},
    BUY_PROPERTY: {
        ("property", "growth"): Ref(Kind.RETURN_CLASS),
        ("property", "tags"): Ref(Kind.TAG, new=True),
    },
    "repay": {("loan",): LOAN},
    "severance": {("bav", "policy"): POLICY},
    "fund_policy": {("policy",): POLICY},
    "write_off": {("asset",): Ref(Kind.ASSET, sorts=("equity",))},
    "end_streams": {("names",): Ref(Kind.STREAM), ("tags",): Ref(Kind.TAG)},
    "set_stream": {("name",): Ref(Kind.STREAM)},
    "inheritance": {("from",): Ref(Kind.RELATIVE)},
    "gift": {("from",): Ref(Kind.RELATIVE)},
    ADD: {
        ("stream", "index"): Ref(Kind.INDEX),
        ("stream", "of"): Ref(Kind.STREAM, sorts=("salary",)),
        ("stream", "repays"): LOAN,
        ("stream", "after_sale_of"): Ref(Kind.ASSET, sorts=("property",)),
        ("stream", "property"): Ref(Kind.ASSET, sorts=("property",)),
        ("stream", "tags"): Ref(Kind.TAG, new=True),
        ("stream", "into"): Ref(Kind.ASSET, sorts=SAVINGS_TARGETS),
    },
}
# the columns of an `add_stream` grid: the event, then those of the stream grids of the Cashflows
# page, the rare ones behind `All columns`
STREAM_FIELDS = (
    "at",
    "id",
    "note",
    *("name", "kind", "cat", "amount", "gross", "every", "start", "end", "factor", "tags", "index"),
)
STREAM_MORE = (
    *("part", "of", "share", "points", "point_value", "health", "deduct", "deductible"),
    *("repays", "after_sale_of", "property", "taxable", "into", "hebesatz"),
    *("sperrzeit", "training"),
)
ID_HELP = N_(
    "An id names the items that the Overrides tab moves (Dates) and changes (Event fields), here "
    "and in the scenarios that extend this one; items that share one move together."
)
DROP_HELP = N_(
    "These events come from the scenarios that this one extends. A switch leaves out every phase "
    "and event of those scenarios with its id, here and in the scenarios that extend this one, "
    "together with what their overrides move or change for it. An event without an id cannot be "
    "left out: give it one in its own scenario."
)
EDITED = " ●"  # on the label of a tab whose grid holds edits not saved yet


def ref_columns(kind: str, bonuses: frozenset[str] = frozenset()) -> dict[KeyPath, Ref]:
    """What the fields of an event of `kind` name, by key path: the `of` of a stream leaves out
    the streams `bonuses` (derived from another), a bonus is no base."""
    return {
        path: replace(ref, without=bonuses) if path[-1] == "of" else ref
        for path, ref in REFS.get(kind, {}).items()
    }


def table(
    stem: str,
    kind: str,
    phases: Mapping[str, str],
    bonuses: frozenset[str] = frozenset(),
    taken: Collection[str] = (),
) -> Table:
    """The grid of the events of `kind` in the scenario file `stem`: `at` first and pinned on a
    phone, `id` and `note` last. An `add_stream` row lifts the fields of its stream, a `factor`
    per phase of `phases` (each with how the pages name it); its `of` leaves out the streams
    `bonuses` (derived from another). A new purchase makes its ids as its form does, none of
    `taken`."""
    model, lifted, more = TYPES[kind], kind == ADD, MORE.get(kind, ())
    skip = ("at", "note", "id", "type", "then", *more)
    # the fields as the file writes them: `from` of an inheritance
    own = FIELDS.get(kind) or [
        name for f, info in model.model_fields.items() if (name := info.alias or f) not in skip
    ]
    return Table(
        model,
        f"events-{stem}-{kind}",
        identity=IDENTITY,
        fixed={"type": kind},
        fields=STREAM_FIELDS if lifted else ("at", *own, "id", "note"),
        more=STREAM_MORE if lifted else more,
        titles=HEADERS | TYPE_HEADERS.get(kind, {}),
        gates={"factor": "phases"} if lifted else {},
        entries={"factor": phases} if lifted else {},
        pinned=("at",),
        negative=NEGATIVE.get(kind, ()),
        unsigned=NEGATIVE.get(kind, ()),
        inner="stream" if lifted else None,
        locked=LOCKED.get(kind, ()),
        rename=Kind.ASSET if kind in LOCKED else None,
        derived=purchase_ids(taken) if kind == BUY_PROPERTY else {},
        # the options of a column by its name: `bav policy`, a lifted field by its own name
        options={
            path[-1] if lifted else " ".join(path): ref
            for path, ref in ref_columns(kind, bonuses).items()
        },
    )


def actions(then: Sequence[Row], repays: RowEdits, invest: bool) -> RowEdits:
    """The edits of the actions `then` of a sale from the edits of its repayments (by their index
    in `then`) and the toggle `Invest the rest`: the repayments first, `invest` last. A repayment
    without `amount` repays all."""
    held = [k for k, action in enumerate(then) if "invest" in action]
    moved = held if not invest or repays.added else []  # it goes, or moves behind the new ones
    return RowEdits(
        edited=dict(repays.edited),
        added=[
            *repays.added,
            *([{"invest": "portfolio"}] if invest and (not held or repays.added) else []),
        ],
        deleted=[*repays.deleted, *moved],
    )


def bonus_streams(streams: Iterable[object]) -> frozenset[str]:
    """The names of the streams that derive from another (`of`)."""
    return frozenset(
        str(s["name"]) for s in streams if isinstance(s, dict) and s.get("of") and s.get("name")
    )


@dataclass(frozen=True)
class Tab:
    """What the tab draws on: the scenario file `name` under `data_dir`, its events now (`rows`),
    the names of the inputs and the streams that derive from another."""

    data_dir: Path
    name: str  # `scenarios/<stem>.yaml`
    rows: list[Row]
    refs: References
    bonuses: frozenset[str]

    @property
    def stem(self) -> str:
        return PurePosixPath(self.name).stem

    @property
    def events(self) -> RowFile:
        return RowFile(self.data_dir, self.name, ("events",))

    @cached_property
    def phases(self) -> dict[str, str]:
        """The phases of `assumptions.yaml`, each with how the pages name it."""
        return references.phases(self.data_dir)

    def table(self, kind: str) -> Table:
        return table(self.stem, kind, self.phases, self.bonuses, self.taken)

    @cached_property
    def taken(self) -> list[str]:
        """The asset ids that a new purchase must not take."""
        return self.refs.names(Kind.ASSET, self.stem)

    def names(self, kind: str) -> dict[KeyPath, Names]:
        """The options of the fields of the form `Add an event` of `kind`, of an `add_stream` also
        the phases of its stream."""
        return {
            path: Names(ref.names(self.refs, self.stem), new=ref.new)
            for path, ref in ref_columns(kind, self.bonuses).items()
        } | ({STREAM_PHASES: Names(tuple(self.phases))} if kind == ADD else {})


def _label(kind: str, own: int, parents: int, *, edited: bool = False) -> str:
    """The tab of an event type in words with its events: `Sell an asset (1)`, `(2 inherited)`,
    `(1, 2 inherited)`, and `EDITED` while its grid or its repayments hold edits not saved yet."""
    counts = [
        *([str(own)] if own else []),
        *([_("{n} inherited").format(n=parents)] if parents else []),
    ]
    count = f" ({', '.join(counts)})" if counts else ""
    return f"{_(TITLES[kind])}{count}{EDITED if edited else ''}"


def _opened(stem: str) -> str:
    """The session key of the event type whose tab is open in the scenario file `stem`."""
    return f"events-{stem}-open"


def _open(key: str, kinds: Mapping[str, str]) -> None:
    """Keep the type of the tab that opened, by its label (`kinds`)."""
    st.session_state[key] = kinds[str(st.session_state[f"{key}-tabs"])]


def open_type(stem: str, kind: str) -> None:
    """Open the tab of the event type `kind` when the Events tab of `stem` draws next and scroll
    it into view: a link to an event, such as one that refuses the roll forward."""
    st.session_state[_opened(stem)] = kind
    st.session_state[f"{_opened(stem)}-reveal"] = True


def tab(path: Path) -> None:
    """The events of the scenario file `path` (`<data>/scenarios/<stem>.yaml`), opened on the type
    opened last (`open_type`), else on the first type with events, else the first shown; below
    the types the note of those that the mode or a feature hides."""
    data_dir, name = path.parents[1], scenario_file(path.stem)
    rows = RowFile(data_dir, name, ("events",)).rows()
    try:
        chain = loader.chain(path)
    except InputError as err:
        st.warning(
            _("The inherited events do not read: {error}").format(error=err),
            icon=":material/error:",
        )
        chain = [(path, {})]
    parents = inherited(chain)
    kept = [i.row for i in parents if i.dropped is None]
    added = [r.get("stream") for r in [*rows, *kept] if r.get("type") == ADD]
    here = Tab(
        data_dir,
        name,
        rows,
        tables.known(data_dir),
        bonus_streams([*RowFile(data_dir, "cashflows.yaml", ("streams",)).rows(), *added]),
    )
    own, run = (Counter(str(row.get("type")) for row in found) for found in (rows, kept))
    edited = {k: _edited(here, k) for k in TYPES}
    # the types that the mode and the features show (`mode.View`), the file or its parents hold,
    # or whose grid holds edits not saved yet
    view = mode.view(data_dir)
    kinds = [
        k
        for k in TYPES
        if view.shows(mode.Item(mode.Sort.EVENT, (k,))) or own[k] or run[k] or edited[k]
    ]
    labels = {k: _label(k, own[k], run[k], edited=edited[k]) for k in kinds}
    # a label that a count or an edit changes makes a new tab strip, which opens on its default:
    # the type that is open
    opened = _opened(here.stem)
    # at first the type of the file's first event, else of an inherited one: a strip that opened
    # on an empty grid of inherited sales hid the purchase of the file far to the right
    held = [*(str(row.get("type")) for row in rows), *(k for k in kinds if run[k])]
    if opened not in st.session_state and held and held[0] != kinds[0]:
        st.session_state[f"{opened}-reveal"] = True  # it may lie beyond the end of the strip
    first = next(k for k in (st.session_state.get(opened), *held, *kinds) if k in kinds)
    st.session_state[opened] = first
    boxes = st.tabs(
        list(labels.values()),
        default=labels[first],
        key=f"{opened}-tabs",
        on_change=_open,
        args=(opened, {label: kind for kind, label in labels.items()}),
    )
    if st.session_state.pop(f"{opened}-reveal", False):
        strip = tables.key_class(f"{opened}-tabs")
        st.html(_REVEAL.substitute(strip=strip), unsafe_allow_javascript=True)
    for k, box in zip(kinds, boxes, strict=True):
        with box:
            _type(here, k)
    hidden = (mode.Item(mode.Sort.EVENT, (k,)) for k in TYPES if k not in kinds)
    view.note({h: _(INLINE[h.key[0]]) for h in hidden}, held=mode.Held.KINDS)
    _inherited(here, parents, chain)


def _edited(here: Tab, kind: str) -> bool:
    """Whether the grid of `kind`, or the repayments of the sale chosen, hold edits not saved yet,
    before they draw in this run."""
    if tables.unsaved(here.table(kind)):
        return True
    picked = st.session_state.get(f"events-{here.stem}-sale")
    key = _then_key(here.stem, picked) if kind == SELL and picked else None
    return key is not None and (base := save.kept(key)) is not None and _then_held(key, base)


def _type(here: Tab, kind: str) -> None:
    """The tab of one event type: the form that adds one, the grid, the ids that other items use,
    and under the sales the repayments of one."""
    spec = here.table(kind)
    _add(here, kind, spec)
    edit_table(here.events, spec)
    _ids(here, [row for row in here.rows if row.get("type") == kind])
    if kind == SELL:
        _repayments(here)


def ordered(found: Sequence[fields.Field]) -> tuple[fields.Field, ...]:
    """The fields of a form `Add an event`: `at` first, `id` and `note` last, the id of a nested
    model after its other fields: the form makes it of the name above it."""
    last = {f.path[:-1]: n for n, f in enumerate(found)}

    def place(item: tuple[int, fields.Field]) -> tuple[int, float]:
        n, f = item
        rank = {"at": 0, "id": 2, "note": 3}.get(f.path[0], 1)
        nested_id = len(f.path) > 1 and f.path[-1] == "id"
        return rank, last[f.path[:-1]] + 0.5 if nested_id else n

    return tuple(f for _n, f in sorted(enumerate(found), key=place))


def made(name: object, taken: Collection[str]) -> str | None:
    """An id made from a name (`ui.slug`), numbered where the inputs hold it already: `own-flat`,
    `own-flat-2`. None without a name."""
    if not (base := slug(str(name or ""))):
        return None
    return next(i for i in chain([base], (f"{base}-{n}" for n in count(2))) if i not in taken)


def purchase_ids(taken: Collection[str]) -> dict[KeyPath, forms.Derived]:
    """The ids of a purchase that its form makes when they stay empty: of the property from its
    name, of the loan from its name, else from the property (`home-loan`); none that the inputs
    hold (`taken`)."""

    def home(row: Mapping[str, Any]) -> str | None:
        held = row.get("property") or {}
        return held.get("id") or made(held.get("name"), taken)

    def loan(row: Mapping[str, Any]) -> str | None:
        if not isinstance(held := row.get("loan"), dict):
            return None
        at = home(row)
        return made(held.get("name") or (at and f"{at} loan"), {*taken, *filter(None, [at])})

    return {("property", "id"): home, ("loan", "id"): loan}


def _add(here: Tab, kind: str, spec: Table) -> None:
    """The form that adds an event of `kind` at once, with only the fields of its type: on a phone
    the grid adds a row at the end of its list, out of view. It waits for unsaved edits of the
    grid. The actions of a sale follow under the grid once it is saved. A purchase makes its ids
    of its names and takes its loan without a minus."""
    model = TYPES[kind]
    found = ordered(
        [
            entry
            for f in fields.of(model)
            if f.path[0] != "then"
            for entry in (fields.entries(f, here.phases) if f.path == FACTORS else [f])
        ]
    )
    # said here: a label of a phase is written by the user
    factors = {
        (*FACTORS, p): _("Factor in {phase}").format(phase=label)
        for p, label in here.phases.items()
    }
    purchase = kind == BUY_PROPERTY
    form = forms.Form(
        f"{spec.key}-add",
        here.name,
        found,
        model,
        keys=("events",),
        new={"type": kind},
        labels=LABELS | TYPE_LABELS.get(kind, {}) | factors,
        helps=HELPS,
        negative=(LOAN_BALANCE,) if purchase else (),
        derived=purchase_ids(here.taken) if purchase else {},
        plain=PLAIN,
    )
    with st.expander(_("Add an event"), icon=":material/add:", key=f"{form.key}-open"):
        if caption := CAPTIONS.get(kind):
            st.caption(_(caption))
        shown = forms.show(here.data_dir, form, options=here.names(kind))
        flagged = guard.review(shown.changes(), key=form.key)
        held = tables.unsaved(spec)  # the add would change the rows of the grid
        forms.save(
            here.data_dir,
            [shown],
            key=f"{form.key}-save",
            flagged=flagged,
            ready=not held,
            why=_("Save or discard the edits of the events below first.") if held else "",
        )


def _ids(here: Tab, rows: list[Row]) -> None:
    """The ids of the events of this grid that another item uses: an override that moves or
    changes them, a scenario that drops them. Such a use needs a changed id too."""
    refs, stem = here.refs, here.stem
    users: dict[str, dict[str, list[str]]] = {}
    for item in dict.fromkeys(row["id"] for row in rows if isinstance(row.get("id"), str)):
        for site in (*refs.uses(Kind.ITEM, item), *refs.uses(Kind.EVENT, item)):
            scenario = site.scenario or ""
            if stem in refs.chain(scenario):  # the item of this file, not one of the same id
                what = "drop" if site.keys[0] == "drop" else str(site.keys[1])
                users.setdefault(item, {}).setdefault(scenario, []).append(what)
    if users:
        uses = "; ".join(
            _("{item} by {users}").format(
                item=f"**{literal(item)}**",
                users=", ".join(f"{literal(s)} ({', '.join(w)})" for s, w in by.items()),
            )
            for item, by in users.items()
        )
        st.caption(
            _("Ids in use: {uses}. {help} A changed id must change there too.").format(
                uses=uses, help=_(ID_HELP)
            )
        )


def _invests(then: Sequence[Row]) -> bool:
    return any("invest" in action for action in then)


def _then_held(key: str, base: save.Base) -> bool:
    """Whether the repayments of the base hold edits: a cell of the grid or the toggle."""
    widget = f"{key}-{base.nonce}"
    toggle = st.session_state.get(f"{widget}-invest", _invests(base.rows))
    repays = sum("repay" in action for action in base.rows)
    return gridstate.touched(gridstate.grid_state(widget, repays)) or toggle != _invests(base.rows)


def _then_key(stem: str, name: tuple[tuple[Any, ...], int]) -> str:
    """The key of the repayments of the sale `name` (`store.keyed`)."""
    values, count = name
    return "-".join(str(v) for v in ("events", stem, "then", *values, count) if v is not None)


def _repayments(here: Tab) -> None:
    """The actions of one sale: a grid of the loans that it repays (an empty amount repays all)
    and `Invest the rest`, saved with their own button. A conditional sale repays nothing."""
    rows, stem = here.rows, here.stem
    sales = {n: i for n, i in keyed(rows, IDENTITY).items() if rows[i].get("type") == SELL}
    if not sales:
        return
    st.markdown(f"**{_('Repayments')}**")
    picked = st.selectbox(
        _("Sale"),
        list(sales),
        format_func=lambda n: f"{when(rows[sales[n]])} {describe(rows[sales[n]])}",
        key=f"events-{stem}-sale",
    )
    if picked is None:
        return
    sale, key = rows[sales[picked]], _then_key(stem, picked)
    file = RowFile(here.data_dir, here.name, ("events", sales[picked], "then"))
    base, changed = save.base(file, key, list, partial(_then_held, key))
    then, widget = base.rows, f"{key}-{base.nonce}"
    cols = [
        replace(col, options=LOAN.names(here.refs, stem))
        if col.key == "repay"
        else replace(col, about=N_("Empty repays all of the loan."), named=None, more=())
        for col in gridcolumns.columns(RepayAction)
    ]
    units = {"amount": Unit.EUR}
    if changed is not None:
        save.warn(changed, key=key, identity=THEN, units=units)
    listed = [(k, action) for k, action in enumerate(then) if "repay" in action]
    edits = RowEdits()
    if isinstance(sale.get("when"), dict):
        st.caption(_("A conditional sale sells in some paths only, so it repays no loan."))
    else:
        edits = tables.small_grid(cols, listed, widget, helps=False)
    had = _invests(then)
    invest = st.toggle(
        _("Invest the rest"),
        value=had,
        key=f"{widget}-invest",
        help=_(description(InvestAction, ("invest",))),
    )
    found, removed = _then_changes(then, edits, had=had, invest=invest)
    save.button(
        file,
        actions(then, edits, invest),
        [],
        read=base.read(THEN),
        label=_("Save repayments"),
        key=f"{key}-save",
        nonce_key=f"{key}-nonce",
        toast=_("Saved {files}").format(files=file.path.name),
        flagged=guard.review(found, removed, key=key),
    )


def _action(action: Mapping[str, Any]) -> str:
    """A repayment in the guard: its key as the pages name it and its loan as written."""
    return f"{gridcolumns.keyword('repay')} {action.get('repay', '')}".strip()


def _sum(action: Mapping[str, Any]) -> guard.Cell:
    """The amount of a repayment as the guard shows it: euros, or `all`."""
    amount = action.get("amount")
    return float(amount) if isinstance(amount, int | float) else pgettext("amount", "all")


def _then_changes(
    then: Sequence[Row], edits: RowEdits, *, had: bool, invest: bool
) -> tuple[list[guard.Change], list[str]]:
    """What a save of the repayments writes, in the guard's terms, and the repayments it
    removes."""
    found = [
        guard.Change(
            f"{_action(then[i])} {gridcolumns.keyword(field)}",
            _sum(then[i]) if field == "amount" else then[i].get(field),
            _sum(cells) if field == "amount" else value,
            unit=Unit.EUR if field == "amount" else None,
        )
        for i, cells in edits.edited.items()
        for field, value in cells.items()
    ]
    found += [guard.Change(_action(new), None, _sum(new)) for new in edits.added]
    if had != invest:
        found.append(guard.Change(_("invest the rest"), on_off(had), on_off(invest), unit=None))
    return found, [_action(then[i]) for i in edits.deleted]


def _inherited(here: Tab, parents: list[Inherited], chain: Chain) -> None:
    """The events that the file inherits: a toggle per id that leaves them out
    (`lineage.leave_out`), then the events read only with their file and the file below that
    drops them."""
    if not parents:
        return
    st.markdown(f"**{_('Inherited events')}**")
    ids = lineage.ids(reach(chain))
    lineage.leave_out(
        here.data_dir, here.name, ids, chain, key=f"events-{here.stem}-drop", stale=True
    )
    lineage.table(parents)
    fold(_(DROP_HELP), _("About inherited events"))
