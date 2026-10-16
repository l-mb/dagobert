"""Forms from the model: one widget per field (`ui.fields`, `ui.widgets`), shown and read in its
unit. An empty field takes its fallback, which its placeholder names with the source: the model
defaults of the mapping as edited (`fields.fallback`), in a scenario what its chain gives
(`overrides.fallback`). Each run checks the typed text and the model, the save guard lists the
changes, and Save writes the forms and grids of a tab as one revision (`store.write`). A form
shows the part of its file that it began with while its generation lives: a change on disk
without edits starts a new one, one with edits warns, and Save refuses it
(`revisions.unchanged`)."""

from __future__ import annotations

import copy
import dataclasses
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

import streamlit as st
from pydantic import BaseModel, ValidationError

from dagobert import overrides, revisions, store
from dagobert.i18n import N_, _
from dagobert.loader import nested, read_yaml
from dagobert.model.base import KeyPath, named
from dagobert.model.plan import SCENARIO_KEYS
from dagobert.overrides import DEFAULT, Leaf, own
from dagobert.problems import Keys, Problem, Source, dotted, errors, located
from dagobert.store import NULL, RowEdits
from dagobert.ui import guard, is_mobile, keyboard, literal, source, tell, widgets
from dagobert.ui.fields import ABSENT, SYMBOL, Field, Kind, dicts, fallback, lookup
from dagobert.ui.formguard import changes
from dagobert.ui.gridcolumns import Row
from dagobert.ui.gridstate import touched
from dagobert.ui.save import REFUSED, Grid, discard_form, form_not_saved, form_stale
from dagobert.ui.widgets import KEY, Names, Spot, prefix, same

if TYPE_CHECKING:
    from pathlib import Path

    from dagobert.ui.tables import Computed, MapRows

REQUIRED = N_("required")  # why a required field that is empty and has no fallback keeps Save off
# the source of a `derived` value in its placeholder: `own-flat from the name`
FROM = N_("the name")
# what an empty field of a form takes from the mapping after the edits, None for nothing
Derived = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class When:
    """A field that takes effect only while the field at `path`, drawn before it, holds one of
    `values`, or the field at `unless` holds a value: else it shows disabled, `why` after its
    label (`statutory insurance only`, unless a switch to it is set)."""

    path: KeyPath
    values: tuple[object, ...]
    why: str
    unless: KeyPath | None = None


@dataclass(frozen=True)
class Form:
    """The fields of a part of an input file that a tab edits: of the mapping at `keys` of `file`,
    also an item of a list (`("events", 0)`). `model` is the model of that mapping: its defaults
    are the fallback, and it checks the candidate. `override`: the mapping is the `overrides` of
    a scenario file, so an empty field inherits through its chain and the merged assumptions are
    checked (`model` is `Assumptions`). `new`: the form adds a row to the list at `keys`, with these
    fields fixed (`{"type": "sell"}`). `labels` replace the label of a field (`Pension insurance
    since`), of the heading of a model (`("care", "duration")`) and of a column of a grid (by the
    path of its field and its name: `("returns", "stdev")`; the key column of a mapping by name
    under `name`: `("returns", "name")`). `terms` name the technical term of a
    field before its help (`Sparer-Pauschbetrag`), `helps` replace its help where the model's
    names keys. `nulls` say what null stands for where the model takes it: the label of the
    toggle of a list, the option of a choice (`care.index`: nominal), the placeholder of an empty
    choice whose null is the default (`extends`: none). `choices` give the words of the options of
    a choice, `when` the field that a field takes effect with, `rows` the rows of a mapping by
    name (the phases, label first). `negative`: numbers typed without a sign and kept below zero
    (the loan of a purchase: the keypad of a phone may have no minus). `derived`: what an empty
    field takes from the others (the id of a purchase from its name), shown as its placeholder and
    written with the row. `plain`: a message of the model in plain words, by the end of its text.
    `parts`: the top keys of the part beyond those of `fields`, the keys of a tab whose fields the
    mode or a feature hides (rule `mode`): the part keeps its shape whatever shows. `hides`: the
    columns of a mapping by name, by its path, that the mode or a feature hides while no entry of
    the part holds them: they go behind `All columns`; of a list of rows they go (the `id` of a
    phase change in simple mode). `computed`: read-only columns of a list of rows by its path,
    which each row gives (the age of a phase change). The words of a page in these (labels,
    nulls, terms, helps, choices, `When.why`, plain words) are English: the form says them in the
    language of the session."""

    key: str
    file: str
    fields: tuple[Field, ...]
    model: type[BaseModel]
    keys: Keys = ()
    override: bool = False
    new: Mapping[str, Any] | None = None
    labels: Mapping[KeyPath, str] = dataclasses.field(default_factory=dict)
    nulls: Mapping[KeyPath, str] = dataclasses.field(default_factory=dict)
    terms: Mapping[KeyPath, str] = dataclasses.field(default_factory=dict)
    helps: Mapping[KeyPath, str] = dataclasses.field(default_factory=dict)
    negative: tuple[KeyPath, ...] = ()
    derived: Mapping[KeyPath, Derived] = dataclasses.field(default_factory=dict)
    plain: Mapping[str, str] = dataclasses.field(default_factory=dict)
    choices: Mapping[KeyPath, Mapping[object, str]] = dataclasses.field(default_factory=dict)
    when: Mapping[KeyPath, When] = dataclasses.field(default_factory=dict)
    rows: Mapping[KeyPath, MapRows] = dataclasses.field(default_factory=dict)
    parts: tuple[str, ...] = ()
    hides: Mapping[KeyPath, frozenset[str]] = dataclasses.field(default_factory=dict)
    computed: Mapping[KeyPath, tuple[Computed, ...]] = dataclasses.field(default_factory=dict)

    def label(self, field: Field) -> str:
        """The label of `field` in the language of the session."""
        return _(self.labels[field.path]) if field.path in self.labels else field.label

    def heading(self, parent: KeyPath) -> str:
        """The heading of the fields of a nested model, in the language of the session."""
        return _(self.labels.get(parent) or named(" ".join(parent)))

    def term(self, field: Field) -> str:
        """A field in a sentence (the save guard and the problems of a new row): its label without
        its unit, after the heading of its model unless the label is its own: `Loan · Rate`."""
        symbol, name = SYMBOL.get(field.unit), self.label(field)
        name = name.removesuffix(f" {symbol}") if symbol else name
        parent = field.path[:-1]
        own = field.path in self.labels or not parent or field.entry
        return name if own else f"{self.heading(parent)} · {name}"

    @property
    def button(self) -> str:
        """The button that writes the form, in the language of the session: `Add` for a new
        row."""
        return _("Save") if self.new is None else _("Add")

    def shown(self, field: Field) -> Field:
        """`field` as the form draws it: its help in words (`helps`), the technical term before it,
        its grid columns under their labels; a field of `negative` takes no minus."""
        if help_text := self.helps.get(field.path):
            field = replace(field, about=help_text, named=None, more=())
        if term := self.terms.get(field.path):
            field = replace(field, term=_(term))
        if field.path in self.negative:
            field = replace(field, low=0, open_low=True, high=None, open_high=False)
        if not field.columns:
            return field
        return replace(
            field,
            columns=tuple(
                replace(c, label=self.labels.get((*field.path, c.name), c.label))
                for c in field.columns
            ),
        )

    def mapping(self, doc: Mapping[str, Any]) -> dict[str, Any]:
        """The mapping that the form edits, as the file holds it now; none for a new row."""
        held = None if self.new is not None else lookup(doc, self.keys)
        return dict(held) if isinstance(held, dict) else {}

    def stored(self, path: KeyPath, value: Any) -> Any:  # noqa: ANN401 a value of a field
        """The value of the field at `path` as the file keeps it: a form whose `mapping` shows a
        value in another unit takes it back here (a salary factor shown in euros)."""
        del path
        return value

    @property
    def tops(self) -> list[str]:
        """The keys of the mapping that the fields lie under, and the `parts`."""
        return list(dict.fromkeys([*self.parts, *(f.path[0] for f in self.fields)]))

    def part(self, doc: Mapping[str, Any]) -> dict[str, Any]:
        """What the form shows of the file: the keys of the mapping that its fields lie under, so
        that two tabs of one file do not refuse each other."""
        held = self.mapping(doc)
        return {k: held[k] for k in self.tops if k in held}

    def leaves(self, data_dir: Path, candidate: Mapping[str, Any]) -> dict[KeyPath, Leaf]:
        """The fallback of each path that `candidate` lacks, a `derived` one too."""
        derived = {
            path: Leaf(value, _(FROM))
            for path, derive in self.derived.items()
            if (value := derive(candidate)) is not None
        }
        return self._defaults(data_dir, candidate) | derived

    def _defaults(self, data_dir: Path, candidate: Mapping[str, Any]) -> dict[KeyPath, Leaf]:
        if self.override:
            return overrides.fallback(data_dir, data_dir / self.file, candidate)
        paths = [f.path for f in self.fields]
        found = fallback(self.model, dict(self.new or {}) | dict(candidate), paths)
        # the model fills no nested model that the candidate lacks (the `stream` of a new
        # `add_stream`): its fields take their own defaults until it holds one
        return {
            f.path: Leaf(f.default, DEFAULT)
            for f in self.fields
            if len(f.path) > 1
            and f.kind is not Kind.SECTION
            and f.section is None
            and f.default is not ABSENT
            and not any(p[:1] == f.path[:1] for p in found)
        } | found

    def filled(self, candidate: Mapping[str, Any]) -> dict[KeyPath, Any]:
        """The `derived` values of the fields that `candidate` lacks."""
        return {
            path: value
            for path, derive in self.derived.items()
            if lookup(candidate, path) is ABSENT and (value := derive(candidate)) is not None
        }

    def explain(self, problem: Problem) -> str:
        """A problem of the model in words. Of a new row by the term of its field (none for the
        row itself) and in plain words where `plain` has them: the row is no line of the file
        yet. Else with its key path (`explain`)."""
        if self.new is None:
            return explain(problem)
        # a check of a row names its type and id first, as the file has many rows
        named = re.sub(rf"^{re.escape(str(self.new.get('type', '')))} \S*: ", "", problem.message)
        message = next((_(text) for end, text in self.plain.items() if named.endswith(end)), named)
        at = re.sub(rf"^{re.escape(dotted(self.keys))}\[\d+\]\.?", "", problem.path)
        terms = {".".join(map(str, f.path)): self.term(f) for f in self.fields}
        where = terms.get(at, at)
        return f"{where}: {message}" if where else message

    def problems(
        self, data_dir: Path, doc: Mapping[str, Any], candidate: Mapping[str, Any]
    ) -> list[Problem]:
        """What the model refuses of the mapping after the edits (`candidate` over what the file
        holds now), in an override of the assumptions that it merges into."""
        whole = {k: v for k, v in self.mapping(doc).items() if k not in self.tops} | dict(candidate)
        if self.new is not None:  # the row it adds comes last
            rows = lookup(doc, self.keys)
            at = (*self.keys, len(rows) if isinstance(rows, list) else 0)
            return problems(self.model, dict(self.new) | whole, self.file, at)
        if not self.override:
            return problems(self.model, whole, self.file, self.keys)
        merged = overrides.effective(data_dir, data_dir / self.file, whole)
        assumptions = nested({p: v.value for p, v in merged.items() if p[0] not in SCENARIO_KEYS})
        try:
            self.model.model_validate(assumptions)
        except ValidationError as err:
            sources = [
                Source(self.file, whole, self.keys),
                Source(self.file, assumptions, (), False),
            ]
            return located(errors(err), sources).problems
        return []


@dataclass(frozen=True)
class Typed:
    """What the widgets of a form hold: per field its value (`ABSENT` when empty, `NULL` for an
    explicit null, the old value while untouched), the edits of each list of rows that the file
    holds (`rows`), per optional section whether it is on, per field that does not read or is
    required and empty the problem, and the key of the widget of each field (`widgets`)."""

    values: dict[KeyPath, Any]
    on: dict[KeyPath, bool]
    unread: dict[KeyPath, str]
    rows: dict[KeyPath, RowEdits] = dataclasses.field(default_factory=dict)
    widgets: dict[str, KeyPath] = dataclasses.field(default_factory=dict)


def _within(path: KeyPath, start: KeyPath) -> bool:
    return path[: len(start)] == start


def _inherits(leaves: Mapping[KeyPath, Leaf], section: KeyPath) -> bool:
    """Whether the fallback holds the optional section `section` on."""
    return any(len(p) > len(section) and _within(p, section) for p in leaves)


def _leaf(leaves: Mapping[KeyPath, Leaf], path: KeyPath) -> Leaf | None:
    """The fallback at `path`, of a mapping by name gathered from the leaves below it."""
    if path in leaves:
        return leaves[path]
    below = {
        p[len(path) :]: v for p, v in leaves.items() if len(p) > len(path) and _within(p, path)
    }
    if not below:
        return None
    return Leaf(nested({p: v.value for p, v in below.items()}), next(iter(below.values())).source)


def _map_edits(path: KeyPath, old: object, new: object) -> dict[KeyPath, Any]:
    """The changes of a mapping by name by key path: a new entry whole, a removed one None, the
    changed fields of an entry each, so the store keeps the rest of its line."""
    before, after = (m if isinstance(m, dict) else {} for m in (old, new))
    out: dict[KeyPath, Any] = {(*path, k): None for k in before if k not in after}
    for name, entry in after.items():
        was = before.get(name, ABSENT)
        if isinstance(was, dict) and isinstance(entry, dict):
            out |= {(*path, name, k): None for k in was if k not in entry}
            out |= {
                (*path, name, k): v for k, v in entry.items() if not same(was.get(k, ABSENT), v)
            }
        elif not same(was, entry):
            out[(*path, name)] = entry
    return out


def edits(
    form: Form, part: Mapping[str, Any], typed: Typed, leaves: Mapping[KeyPath, Leaf]
) -> dict[KeyPath, Any]:
    """The changes of the widgets to `part` by key path, in the convention of the store: None
    removes a key, `NULL` writes null; a list of rows the file holds changes by `Typed.rows`. An
    optional section that is off goes; in an override it writes null where the fallback holds it.
    One that is on but holds nothing becomes `{}`, or in an override inherits again."""
    off = [s for s, on in typed.on.items() if not on]
    out: dict[KeyPath, Any] = {}
    for field in form.fields:
        path = field.path
        if field.kind is Kind.SECTION or path in typed.rows or any(_within(path, s) for s in off):
            continue
        old, new = lookup(part, path), typed.values.get(path, ABSENT)
        if field.kind is Kind.MAP and isinstance(old, dict) and isinstance(new, dict):
            out |= _map_edits(path, old, new)
        elif not same(old, new):
            out[path] = None if new is ABSENT else new
    return out | _sections(form, part, typed, leaves, out)


def _sections(
    form: Form,
    part: Mapping[str, Any],
    typed: Typed,
    leaves: Mapping[KeyPath, Leaf],
    found: Mapping[KeyPath, Any],
) -> dict[KeyPath, Any]:
    """The changes of the optional sections, after the changes `found` of the fields."""
    off = [s for s, on in typed.on.items() if not on]
    out: dict[KeyPath, Any] = {}
    for section in off:
        held = lookup(part, section)
        if any(_within(section, s) and s != section for s in off):
            continue
        if form.override and _inherits(leaves, section):
            if held is not None:
                out[section] = NULL
        elif isinstance(held, dict):  # a null stays: it is off already
            out[section] = None
    candidate = own(part, {**found, **out})
    for section, on in typed.on.items():
        held = lookup(candidate, section)
        if not on or any(_within(section, s) for s in off) or isinstance(held, dict):
            continue
        if not (form.override and _inherits(leaves, section)):
            out[section] = {}
        elif held is not ABSENT:  # a null of the file: inherit again
            out[section] = None
    return out


def _candidate(
    part: Mapping[str, Any], found: Mapping[KeyPath, Any], rows: Mapping[KeyPath, RowEdits]
) -> dict[str, Any]:
    """`part` after the edits: the values (`overrides.own`), then the lists of rows."""
    return own(own(part, found), {p: e.result(lookup(part, p)) for p, e in rows.items()})


def problems(
    model: type[BaseModel], mapping: Mapping[str, Any], file: str, keys: Keys = ()
) -> list[Problem]:
    """What `model` refuses of the mapping at `keys` of the input `file`, by key path, without
    lines: the live check of a form before a write, which then loads every input again."""
    try:
        model.model_validate(mapping)
    except ValidationError as err:
        return located(errors(err), [Source(file, mapping, keys)]).problems
    return []


def explain(problem: Problem) -> str:
    """A problem in words with its key path: `allocation.fixed_income: Field required`."""
    return f"{problem.path}: {problem.message}" if problem.path else problem.message


@dataclass(frozen=True)
class Base:
    """What a form showed first in its generation (`nonce`): its part of the file, and the
    revision of it (`revisions.Seen`), none for a new row, which no change elsewhere refuses."""

    part: dict[str, Any]
    seen: revisions.Seen | None
    nonce: int = 0


def _doc(data_dir: Path, form: Form) -> dict[str, Any]:
    path = data_dir / form.file
    return read_yaml(path) if path.exists() else {}


def conflict(data_dir: Path, form: Form, base: Base) -> revisions.ConflictError | None:
    """Whether the part of `form` changed on disk since its generation began: the change, with
    the time and the page of each revision since."""
    if base.seen is None:
        return None
    try:
        revisions.unchanged(data_dir, base.seen, form.part(_doc(data_dir, form)))
    except revisions.ConflictError as err:
        return err
    return None


@dataclass(frozen=True)
class Shown:
    """A form as drawn in this run: what it began with, what its widgets hold, its edits to its
    part, whether that part changed on disk since (`stale`), whether the edits changed the
    fallback that the placeholders show (`refresh`: `save` reruns the page unless it saves), what
    the model refuses of the candidate (`refused`: Save stays off, as a write would fail) and what
    it refuses that the file holds already (`broken`: Save stays on, the fix of another part)."""

    data_dir: Path
    form: Form
    base: Base
    typed: Typed
    edits: dict[KeyPath, Any]
    stale: bool
    refresh: bool = False
    refused: tuple[Problem, ...] = ()
    broken: tuple[Problem, ...] = ()

    @property
    def candidate(self) -> dict[str, Any]:
        return _candidate(self.base.part, self.edits, self.typed.rows)

    @property
    def changed(self) -> bool:
        return bool(self.edits or any(self.typed.rows.values()))

    def changes(self) -> list[guard.Change]:
        return changes(
            self.base.part,
            self.candidate,
            self.form.fields,
            override=self.form.override,
            rows=self.typed.rows,
            term=None if self.form.new is None else self.form.term,
        )

    def edit(self) -> store.Edit:
        """The edit of the file: the values and lists by key path, or the new row."""
        form = self.form
        if form.new is not None:
            added = RowEdits(added=[dict(form.new) | self.candidate])
            return store.Edit(form.file, rows={form.keys: added})
        return store.Edit(
            form.file,
            {(*form.keys, *path): form.stored(path, v) for path, v in self.edits.items()},
            {(*form.keys, *path): e for path, e in self.typed.rows.items() if e},
        )

    def check(self) -> None:
        """Inside the write: raise `revisions.ConflictError` when the part changed since."""
        if err := conflict(self.data_dir, self.form, self.base):
            raise err

    def fill(self, path: KeyPath, more: Callable[[Row], Row]) -> Shown:
        """The form with each row of the list at `path` that the save writes completed, before
        the guard lists it: an added or edited row, or each row of a list that the file lacks,
        takes the cells of `more` that it does not set (a cell cleared in the grid stays
        cleared): the id of a phase change."""

        def lacking(row: Row, cells: Row) -> Row:
            return {k: v for k, v in more(row).items() if k not in cells}

        if (edits := self.typed.rows.get(path)) is not None:
            held = dicts(lookup(self.base.part, path))
            filled = replace(
                edits,
                edited={i: c | lacking(held[i] | c, c) for i, c in edits.edited.items()},
                added=[new | lacking(new, new) for new in edits.added],
            )
            return replace(self, typed=replace(self.typed, rows=self.typed.rows | {path: filled}))
        if isinstance(listed := self.edits.get(path), list):
            rows = [row | lacking(row, row) for row in dicts(listed)]
            return replace(self, edits=self.edits | {path: rows})
        return self


def _nonce(key: str) -> str:
    return f"{key}-nonce"


def _fresh(key: str) -> None:
    """A new generation of the form `key`: its fields read the file again."""
    st.session_state[_nonce(key)] = st.session_state.get(_nonce(key), 0) + 1


def _based(form: Form, current: dict[str, Any], revision: str | None, nonce: int) -> Base:
    """The base of the generation of `form`, kept in the session from its first run; `revision`
    was taken before `current` was read."""
    held: Base | None = st.session_state.get(f"{form.key}-base")
    if held is None or held.nonce != nonce:
        seen = (
            None
            if form.new is not None
            else revisions.Seen(form.file, revision, revisions.digest(current))
        )
        held = st.session_state[f"{form.key}-base"] = Base(current, seen, nonce)
    return held


def _required(
    form: Form, typed: Typed, candidate: Mapping[str, Any], leaves: Mapping[KeyPath, Leaf]
) -> dict[KeyPath, str]:
    """Each field that the schema requires, that the candidate lacks and nothing falls back to,
    not in a section that is off, as `REQUIRED`."""
    off = [s for s, on in typed.on.items() if not on]
    return {
        f.path: REQUIRED
        for f in form.fields
        if f.kind is not Kind.SECTION
        and not f.entry
        and f.default is ABSENT
        and not any(_within(f.path, s) for s in off)
        and lookup(candidate, f.path) is ABSENT
        and not any(_within(p, f.path) for p in leaves)
    }


@dataclass(frozen=True)
class Leaves:
    """The fallback of the candidate of the last run of a generation of a form (`nonce`), which
    its placeholders show, and whether its change reran the page: once per edit."""

    nonce: int
    leaves: Mapping[KeyPath, Leaf]
    reran: bool = False


# the keys of a field's widgets beside its own: the toggles `Override` and of a null
OWN_KEYS = ("", "-own", "-null")


@dataclass(frozen=True)
class Drawn:
    """The last run of a generation of a form (`nonce`): the fields with an edit then, and the
    state of each widget with its field, for `edited`."""

    nonce: int
    edited: frozenset[KeyPath]
    states: Mapping[str, tuple[KeyPath, object]]


def _drawn(shown: Shown) -> Drawn:
    typed = shown.typed
    marked = [
        *shown.edits,
        *(path for path, rows in typed.rows.items() if rows),
        *(path for path, why in typed.unread.items() if why != REQUIRED),
    ]
    state = st.session_state
    return Drawn(
        shown.base.nonce,
        frozenset(marked),
        {
            key: (path, copy.deepcopy(state[key]))
            for widget, path in typed.widgets.items()
            for key in (f"{widget}{end}" for end in OWN_KEYS)
            if key in state
        },
    )


def edited(key: str) -> frozenset[KeyPath]:
    """The fields of the form `key` that hold an edit not saved yet, before it draws in this run
    (rule `mode`: a field that the mode or a feature hides stays while it holds one): those
    that its last run found, and those whose widget changed since, such as a text typed and the
    switch of the mode pressed before a run saw the text, or a grid whose edits a switch
    carried."""
    last: Drawn | None = st.session_state.get(f"{key}-drawn")
    if last is None or last.nonce != st.session_state.get(_nonce(key), 0):
        return frozenset()
    state = st.session_state
    return last.edited | {
        path
        for widget, (path, held) in last.states.items()
        if (widget in state and state[widget] != held) or touched(state.get(f"carried-{widget}"))
    }


def _evaluate(
    data_dir: Path,
    form: Form,
    typed: Typed,
    *,
    doc: Mapping[str, Any],
    current: dict[str, Any],
    base: Base,
    last: Leaves,
    stale: bool,
) -> tuple[Shown, Leaves]:
    """What the widgets `typed` make of the part that `form` began with, in the file `doc` whose
    part is `current` now: the edits, the fields required and empty, what the model refuses of
    the candidate, and its fallback for the placeholders of the next run."""
    found = edits(form, base.part, typed, last.leaves)
    found |= form.filled(_candidate(base.part, found, typed.rows))
    candidate = _candidate(base.part, found, typed.rows)
    now = form.leaves(data_dir, candidate)
    refresh = now != last.leaves and not last.reran
    typed = replace(typed, unread=_required(form, typed, candidate, now) | typed.unread)
    # the model check follows once every field reads: it would repeat what is missing; a new row
    # waits for its first edit, as it lacks what its type requires
    untouched = form.new is not None and not (found or any(typed.rows.values()))
    problems = [] if typed.unread or untouched else form.problems(data_dir, doc, candidate)
    # what the file holds already keeps Save on: the fix of another part, as the write checks it
    file_problems = {_problem(p) for p in form.problems(data_dir, doc, current)} if problems else ()
    refused = tuple(p for p in problems if _problem(p) not in file_problems)
    broken = tuple(p for p in problems if p not in refused)
    shown = Shown(data_dir, form, base, typed, found, stale, refresh, refused, broken)
    return shown, Leaves(base.nonce, now, refresh)


def show(
    data_dir: Path,
    form: Form,
    *,
    options: Mapping[KeyPath, Names] | None = None,
) -> Shown:
    """Draw `form` from the part of its file that its generation began with; `options` names the
    fields that name something in the inputs. The placeholders come from the fallback of the
    candidate of the run before; when the edits change it, `save` reruns the page once, unless
    Save was pressed with the edit: a rerun here would drop the press. A part that
    changed on disk since starts a new generation while the form has no edits, else a warning
    above the form names the change, keeps the edits and offers to discard them. Above the form
    too: the fields that do not read or are required and empty, which keep Save off, and the
    problems of the model."""
    revision = revisions.last_change(data_dir, form.file)
    doc = _doc(data_dir, form)
    current = form.part(doc)
    nonce = st.session_state.setdefault(_nonce(form.key), 0)
    base = _based(form, current, revision, nonce)
    key = f"{form.key}-leaves"
    last: Leaves | None = st.session_state.get(key)
    if last is None or last.nonce != nonce:
        last = Leaves(nonce, form.leaves(data_dir, base.part))
    top = st.container()
    typed = _draw(form, base.part, last.leaves, options or {})
    changed = conflict(data_dir, form, base)
    shown, leaves = _evaluate(
        data_dir, form, typed, doc=doc, current=current, base=base, last=last, stale=bool(changed)
    )
    st.session_state[key] = leaves
    st.session_state[f"{form.key}-drawn"] = _drawn(shown)
    if changed and not shown.changed:
        _fresh(form.key)
        st.rerun()
    with top:
        _notes(shown, changed, current)
    return shown


def _problem(problem: Problem) -> tuple[str, str]:
    """A problem of the model by its key path and message: a new row moves no line here."""
    return problem.path, problem.message


def _notes(shown: Shown, changed: revisions.ConflictError | None, current: dict[str, Any]) -> None:
    """The change on disk since the form began (the part `current`), the fields that keep Save
    off and the problems of the model."""
    form, typed = shown.form, shown.typed
    if changed:
        form_stale(changed)
        with st.expander(_("What changed there"), key=f"{form.key}-changed"):
            there = changes(shown.base.part, current, form.fields, override=form.override)
            st.markdown("  \n".join(c.text for c in there))
        discard_form(form.key, _fresh, form.key)
    # a new row waits for its first edit: its empty required fields are no news yet
    quiet = form.new is not None and not shown.changed
    if unread := [
        f"**{literal(form.label(f))}** {_(REQUIRED) if why == REQUIRED else why}"
        for f in form.fields
        if (why := typed.unread.get(f.path)) and not (quiet and why == REQUIRED)
    ]:
        st.warning(
            _("{button} stays off until these read: {fields}").format(
                button=form.button, fields="; ".join(unread)
            ),
            icon=":material/edit_off:",
        )
    if shown.refused:
        # a new row is no file yet: its problems are what to fill in
        head = (
            _("{button} stays off:")
            if form.new is not None
            else _("{button} stays off until the model takes these:")
        )
        st.warning(
            head.format(button=form.button)
            + "  \n"
            + "  \n".join(literal(form.explain(p)) for p in shown.refused),
            icon=":material/edit_off:",
        )
    if shown.broken:
        st.warning(
            _("The file does not load already, Save stays on:")
            + "  \n"
            + "  \n".join(literal(form.explain(p)) for p in shown.broken),
            icon=":material/warning:",
        )


def _draw(
    form: Form,
    part: Mapping[str, Any],
    leaves: Mapping[KeyPath, Leaf],
    options: Mapping[KeyPath, Names],
) -> Typed:
    """One widget per field of `form` with the value of `part`: the fields of one model in a row on
    a desktop, in one column on a phone. A section that is off hides its fields."""
    nonce = st.session_state[_nonce(form.key)]
    typed = Typed({}, {}, {})
    row, parent = None, None
    for field in map(form.shown, form.fields):
        path = field.path
        if any(_within(path, s) for s, on in typed.on.items() if not on):
            continue
        old = lookup(part, path)
        spot = Spot(
            key=f"{prefix(field)}{form.key}-{nonce}-{'.'.join(path)}",
            label=form.label(field),
            leaf=_leaf(leaves, path),
            names=options.get(path),
            override=form.override,
            none=(none := form.nulls.get(path)) and _(none),
            key_label=form.labels.get((*path, KEY.name)),  # a header: the column translates it
            words={option: _(text) for option, text in form.choices.get(path, {}).items()},
            off=_off(form.when.get(path), typed, part, leaves),
            rows=form.rows.get(path),
            hidden=form.hides.get(path, frozenset()),
            computed=form.computed.get(path, ()),
        )
        typed.widgets[spot.key] = path
        if field.kind is Kind.SECTION:
            inherited = form.override and old is ABSENT and _inherits(leaves, path)
            row, typed.on[path] = None, widgets.section(field, old, spot, inherited=inherited)
            continue
        if field.kind in (Kind.ROWS, Kind.MAP):
            row = None
            got = (widgets.rows if field.kind is Kind.ROWS else widgets.mapping)(field, old, spot)
            if isinstance(got, RowEdits):
                if got:
                    typed.rows[path] = got
                got = old
            typed.values[path] = got
            continue
        if row is None or path[:-1] != parent:
            parent = path[:-1]
            if parent and parent not in typed.on:
                st.markdown(f"**{form.heading(parent)}**")
            row = st.container(horizontal=not is_mobile(), wrap=True, vertical_alignment="bottom")
        unsigned = path in form.negative and isinstance(old, int | float)
        with row:
            try:
                got = widgets.plain(field, abs(old) if unsigned else old, spot)
            except ValueError as err:
                typed.values[path], typed.unread[path] = old, str(err)
                continue
        negative = path in form.negative and isinstance(got, int | float)
        typed.values[path] = -abs(got) if negative else got
    keyboard()
    return typed


def _off(
    when: When | None, typed: Typed, part: Mapping[str, Any], leaves: Mapping[KeyPath, Leaf]
) -> str:
    """Why a field has no effect now, in the language of the session: the field of `when` holds
    another value and its `unless` none, each as typed, else as the file or its fallback gives
    it."""

    def value(path: KeyPath) -> object:
        got = typed.values.get(path, lookup(part, path))
        if got is ABSENT:
            leaf = _leaf(leaves, path)
            got = None if leaf is None else leaf.value
        return None if got is NULL else got

    if when is None or value(when.path) in when.values:
        return ""
    return "" if when.unless is not None and value(when.unless) is not None else _(when.why)


def merged(found: Iterable[store.Edit]) -> list[store.Edit]:
    """The edits of a tab, one per file: the forms and grids of one file write together."""
    out: dict[str, store.Edit] = {}
    for edit in found:
        held = out.get(edit.name)
        out[edit.name] = (
            edit
            if held is None
            else replace(
                held,
                values=held.values | edit.values,
                rows=held.rows | edit.rows,
                create=held.create or edit.create,
                remove=held.remove or edit.remove,
                origin=held.origin or edit.origin,
            )
        )
    return list(out.values())


def save(
    data_dir: Path,
    shown_forms: Sequence[Shown],
    grids: Sequence[Grid] = (),
    *,
    key: str,
    flagged: bool,
    action: str = "",
    ready: bool = True,
    why: str = "",
) -> None:
    """The one Save of a tab: its forms and grids as one revision of the page and its `action`,
    the tab (`ui.source`: `Assumptions: Markets`), each part checked inside the write. Off while
    nothing changed (its help says so), a field does not read, the model refuses a form, a part
    changed on disk or the caller is not `ready` (a grid of its own whose cell does not read). A
    refused save keeps the edits and says why; a saved one starts a new generation of each form
    and grid. Without a press, a form whose placeholders lag behind its edits (`Shown.refresh`)
    reruns the page. `why`: its help while the caller is not `ready`. A save says `Saved <files>`
    in a toast of the run after it (`ui.tell`)."""
    found = merged([*(s.edit() for s in shown_forms if s.changed), *(g.edit for g in grids)])
    ready = ready and not any(s.typed.unread or s.stale or s.refused for s in shown_forms)
    if not st.button(
        guard.marked(_("Save"), flagged),
        key=key,
        type="primary",
        disabled=not found or not ready,
        help=why or (None if found else _("No changes to save")),
    ):
        if any(s.refresh for s in shown_forms):
            st.rerun()
        return

    def check() -> None:
        for form in shown_forms:
            form.check()
        for grid in grids:
            grid.check()

    try:
        store.write(data_dir, found, source=source(action), check=check)
    except (revisions.ConflictError, *REFUSED) as err:
        form_not_saved(err)
        return
    for s in shown_forms:
        _fresh(s.form.key)
    for g in grids:
        st.session_state[g.nonce] = st.session_state.get(g.nonce, 0) + 1
    tell(_("Saved {files}").format(files=", ".join(e.name for e in found)))
    st.rerun()
