"""The `Scenarios` page: the main scenario and the others that the Explorer compares
(`app.yaml`), every scenario file in the order of its `extends` tree, the file actions
(`fileactions`), and the tabs of the scenario to edit: its timeline, its own fields, its phases
(`phases`) and its events with the inherited ones that it moves or leaves out, and its
overrides. Simple mode hides the
overrides of a scenario that holds none and the field `Template` of one that is none (rule
`mode`). A file that does not load still opens: the page reads the raw YAML and shows the
problems."""

from __future__ import annotations

import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING

import streamlit as st
from babel.lists import format_list
from streamlit.delta_generator import DeltaGenerator

from dagobert import i18n, loader, references, revisions, scenariofiles, store
from dagobert.i18n import N_, _
from dagobert.loader import APP
from dagobert.model.base import KeyPath
from dagobert.model.events import AcquisitionEvent, Event, InheritanceEvent, SellEvent
from dagobert.model.plan import Scenario
from dagobert.problems import InputError
from dagobert.references import References
from dagobert.ui import (
    COMPARE,
    EVENT,
    MAIN,
    SCENARIO,
    TAB,
    events,
    fold,
    guard,
    is_mobile,
    lineage,
    literal,
    mode,
    page_link,
    phases,
    scenario_overrides,
    source,
    tell,
    titled,
)
from dagobert.ui import fields as model_fields
from dagobert.ui.fileactions import KEY, NO_PARENT, PENDING, Doc, Plan, actions, shut
from dagobert.ui.forms import Form, edited, save, show
from dagobert.ui.gridcolumns import keyword
from dagobert.ui.lineage import (
    AT_DEATH,
    LEFT_OUT,
    ON_CONDITION,
    SET_IN,
    THIS,
    TITLES,
    Chain,
    describe,
)
from dagobert.ui.save import Grid, reason
from dagobert.ui.tables import save_in_header
from dagobert.ui.widgets import Names

if TYPE_CHECKING:
    from pathlib import Path

CHOSEN = f"{KEY}chosen"  # the stem of the scenario that the tabs show
PLAN = f"{KEY}plan"  # the box of the main scenario and the comparison, on a phone an expander
NOTE_CHARS = 60  # the start of a note in an option of the main scenario and the comparison
CHOOSER = f"{KEY}chooser"  # the popover of the scenarios on a phone, closed by a choice
# the tabs by their English title: the query `tab` names one (`ui.TAB`)
OVERRIDES = N_("Overrides")
TABS = (N_("Timeline"), N_("General"), N_("Phases"), N_("Events"), OVERRIDES)
FIELDS = {f.path: f for f in model_fields.of(Scenario)}
TEMPLATE = "abstract"
GENERAL = ("name", "note", "extends", TEMPLATE)
LABELS: dict[KeyPath, str] = {("abstract",): N_("Template: only a base for others, never run")}
NULLS: dict[KeyPath, str] = {("extends",): NO_PARENT}


@dataclass(frozen=True)
class Chosen:
    """The scenario file that the tabs show, as its raw mapping: a file that does not load still
    opens."""

    data_dir: Path
    stem: str
    doc: Doc

    @property
    def file(self) -> str:
        return scenariofiles.scenario_file(self.stem)

    @property
    def path(self) -> Path:
        return self.data_dir / self.file

    @property
    def parent(self) -> str | None:
        return _parent(self.doc)

    @cached_property
    def chain(self) -> Chain:
        """The raw files of the `extends` chain, the root first. A missing parent or a cycle
        raises `InputError`."""
        return loader.chain(self.path)


def _parent(doc: Doc) -> str | None:
    return parent if isinstance(parent := doc.get("extends"), str) else None


def _template(doc: Doc) -> bool:
    return doc.get("abstract") is True


def tree(parents: Mapping[str, str | None]) -> list[tuple[str, int]]:
    """The stems in the order of their `extends` tree, each with its depth: a root, then the
    scenarios that extend it below it, each level sorted without regard to case. A file whose
    parent is missing is a root, so is the first file of a cycle."""
    order: list[tuple[str, int]] = []

    def walk(stem: str, depth: int) -> None:
        order.append((stem, depth))
        for child in sorted((s for s, p in parents.items() if p == stem), key=str.casefold):
            if child not in dict(order):
                walk(child, depth + 1)

    for stem in sorted(parents, key=lambda s: (parents[s] in parents, s.casefold())):
        if stem not in dict(order):
            walk(stem, 0)
    return order


def label(stem: str, depth: int, doc: Doc) -> str:
    """A scenario in the chooser: its stem and its name, below its parent, `(template)` for one
    that does not run."""
    text = titled(stem, doc.get("name"))
    indent = "\u2003" * max(depth - 1, 0) + ("↳ " if depth else "")  # em spaces show
    return indent + (_("{scenario} (template)").format(scenario=text) if _template(doc) else text)


def refusals(stem: str, candidate: Doc, docs: Mapping[str, Doc]) -> list[str]:
    """What the general fields of `stem` may not hold that no model checks: the name of another
    scenario, which the results carry, and the template switch of the last scenario that runs."""
    out = []
    name = candidate.get("name")
    if taken := [s for s, doc in docs.items() if s != stem and name and doc.get("name") == name]:
        out.append(
            _("{scenario} has the name {name}: the results name a scenario by it").format(
                scenario=taken[0], name=name
            )
        )
    others = [s for s, doc in docs.items() if s != stem and not _template(doc)]
    if _template(candidate) and not others:
        out.append(_("the last scenario that runs cannot be a template: every page shows one"))
    return out


def _detail(event: Event) -> str:
    """What the timeline says of an event: its note or what it touches, with the condition of a
    sale without a month; of an inheritance or a gift the givers and the sum after its note."""
    if isinstance(event, AcquisitionEvent):
        given = describe(event.model_dump(by_alias=True))
        return f"{event.note} ({given})" if event.note else given
    when = event.when if isinstance(event, SellEvent) else None
    if when is None:
        return event.detail
    return f"{event.detail} ({lineage.condition(when.age, when.liquid_below)})"


def _month(day: object) -> str:
    return "" if day is None else str(day)[:7]


def _marked(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """The column `left out by` in every row once one row has it, else in none."""
    if any(LEFT_OUT in row for row in rows):
        return [row | {LEFT_OUT: row.get(LEFT_OUT, "")} for row in rows]
    return rows


def _phase(labels: Mapping[str, str], name: object) -> str:
    """A phase as the pages name it: its label, else its name."""
    return labels.get(text := str(name or ""), text)


def _item(kind: str) -> str:
    """An event type in words."""
    return _(TITLES[kind]) if kind in TITLES else kind


def timeline(data_dir: Path, path: Path, labels: Mapping[str, str]) -> list[dict[str, str]]:
    """Each phase change and event of the `extends` chain of `path` as its run sees it, moved by
    the `shift` and `events` overrides (`loader.written`), by month, an inheritance without one
    `AT_DEATH` after the dated rows, a sale on a condition last, each with its file (`THIS` for
    `path`); then each item that a file below drops, marked so. A
    phase shows by its label in `labels` (`references.phases`). In the language of the session.
    Raises `InputError` for a chain that does not load."""
    rows = []
    condition = _(ON_CONDITION)
    for file, own in loader.written(data_dir, path):
        where = _(THIS) if file.stem == path.stem else file.stem
        rows += [
            {"month": _month(p.at), "item": _("Phase"), "detail": _phase(labels, p.phase)}
            | {"id": p.id or "", SET_IN: where}
            for p in own.phases
        ]
        rows += [
            {
                "month": _month(e.at)
                if e.at
                else _(AT_DEATH)
                if isinstance(e, InheritanceEvent)
                else condition,
                "item": _item(e.type),
                "detail": _detail(e),
            }
            | {"id": e.id or "", SET_IN: where}
            for e in own.events
        ]
    chain = loader.chain(path)
    rows += [
        {
            "month": _month(i.row.get("from")) if key == "phases" else lineage.month(i.row),
            "item": _("Phase") if key == "phases" else _item(str(i.row.get("type", ""))),
            "detail": _phase(labels, i.row.get("phase"))
            if key == "phases"
            else lineage.detail(i.row),
            "id": str(i.row.get("id")),
            SET_IN: i.file,
            LEFT_OUT: i.dropped,
        }
        for key in ("phases", "events")
        for i in lineage.inherited(chain, key)
        if i.dropped
    ]
    return sorted(_marked(rows), key=lambda row: (row["month"] == condition, row["month"]))


def option(stem: str, doc: Doc) -> str:
    """A scenario in the choice of the main scenario and the comparison: its stem and name, and
    the start of its note."""
    text, note = titled(stem, doc.get("name")), doc.get("note")
    if not isinstance(note, str) or not note.strip():
        return text
    return f"{text} — {textwrap.shorten(note, NOTE_CHARS, placeholder=' …')}"


def promoted(old: str, new: str, others: Sequence[str]) -> list[str]:
    """The comparison after the main scenario moved from `old` to `new`: `old` joins it first and
    `new` leaves it, so the choice of the main one keeps the others."""
    return [s for s in dict.fromkeys([old, *others]) if s != new]


def opening(docs: Mapping[str, Doc], saved: object) -> tuple[list[str], str | None]:
    """The scenarios of `app.yaml` (`saved`) that run, and the first scenario of the pages that
    show one: the first of them, else the first file that runs, as
    `scenariofiles.first_scenario`."""
    running = [s for s, doc in docs.items() if not _template(doc)]
    listed = [s for s in saved if s in running] if isinstance(saved, list) else []
    return listed, (listed or running or [None])[0]


def _chooser(
    docs: Mapping[str, Doc],
    order: list[tuple[str, int]],
    first: str | None,
    row: DeltaGenerator,
) -> str:
    """The scenario of the tabs, from the files in the order of their tree (`order`), at first the
    `first` one: a select box; on a phone pills in a popover that names the choice and closes on
    a tap (a select box can open the keyboard, and many pills would fill the screen). A file
    action, a button that opens a parent and the query `scenario` choose one."""
    stems, depth = [s for s, _depth in order], dict(order)
    handed = st.query_params.pop(SCENARIO, None)  # the hand-off of another page
    wanted = st.session_state.pop(PENDING, None) or handed
    if wanted in stems:
        st.session_state[CHOSEN] = wanted
    if st.session_state.get(CHOSEN) not in stems:
        st.session_state[CHOSEN] = first or stems[0]

    def shown(stem: str) -> str:
        return label(stem, depth[stem], docs[stem])

    if not is_mobile():
        return str(
            row.selectbox(
                _("Edit scenario"),
                stems,
                format_func=shown,
                key=CHOSEN,
                width=420,
                persist_state="session",
            )
        )
    chosen = st.session_state[CHOSEN]
    with row.popover(
        label(chosen, 0, docs[chosen]), icon=":material/edit:", key=CHOOSER, on_change="rerun"
    ):
        picked = st.pills(
            _("Edit scenario"),
            stems,
            format_func=shown,
            key=CHOSEN,
            required=True,
            persist_state="session",
            on_change=shut,
            args=(CHOOSER,),
        )
    return str(picked)


def _open(stem: str) -> None:
    st.session_state[CHOSEN] = stem


def _moved(main: str, compare: str, old: str) -> None:
    st.session_state[compare] = promoted(
        old, st.session_state[main], st.session_state.get(compare, [])
    )


def _plan(data_dir: Path, docs: Mapping[str, Doc], saved: list[str], first: str) -> None:
    """The main scenario, the first of `app.yaml`, which the Overview, the Cashflows and Flows
    pages show and the Explorer runs first, and the others that the Explorer opens with,
    with their own Save: the explorer's `Set as default` writes the same list, the last choice
    wins. A bordered box above the chooser of the scenario to edit, on a phone an expander that
    names the main scenario, open by the link of the Overview (`?main=open`); its selects take no
    typing there, so no keyboard opens. One below the other, each as wide as the box: an option
    shows the start of a note. A new main scenario takes the old one into the comparison
    (`promoted`). The widgets are keyed by `saved`: a rename, a delete or a save elsewhere starts
    them anew, they would hold the old stems."""
    running = [s for s, doc in docs.items() if not _template(doc)]
    nonce = revisions.digest(saved)[:12]
    keys = f"{KEY}main-{nonce}", f"{KEY}compare-{nonce}"
    state = st.session_state
    if state.get(keys[0]) not in running:  # also one made a template since
        state[keys[0]] = first
    phone = is_mobile()
    title = _("Main scenario: {scenario}").format(scenario=titled(first, docs[first].get("name")))
    with (
        st.expander(title, key=PLAN, expanded=st.query_params.get(MAIN) == "open")
        if phone
        else st.container(border=True, key=PLAN)
    ):
        main = str(
            st.selectbox(
                _("Main scenario"),
                running,
                format_func=lambda stem: option(stem, docs[stem]),
                key=keys[0],
                on_change=_moved,
                args=(*keys, state[keys[0]]),
                help=_(
                    "The scenario of the Overview, Cashflows and Flows pages, and the first in the "
                    "Explorer."
                ),
                filter_mode=None if phone else "fuzzy",
            )
        )
        if isinstance(note := docs[main].get("note"), str):
            st.caption(literal(note))  # in full: an expander takes no fold
        offered = [s for s in running if s != main]
        state[keys[1]] = [s for s in state.get(keys[1], saved[1:]) if s in offered]
        others: list[str] = st.multiselect(
            _("Also compare in the Explorer"),
            offered,
            format_func=lambda stem: option(stem, docs[stem]),
            key=keys[1],
            help=_(
                "The Explorer opens with the main scenario and these, in this order. A template "
                "does not run."
            ),
            filter_mode=None if phone else "fuzzy",
        )
        picked, current = [main, *others], saved or [first]
        changes = [
            guard.Change(keyword("scenarios"), ", ".join(saved), ", ".join(picked), unit=None)
        ]
        guard.review(changes if picked != current else [], key=PLAN, hint="")
        if st.button(_("Save"), key=f"{PLAN}-save", disabled=picked == current):
            try:
                scenariofiles.save_default_scenarios(
                    data_dir, picked, source=source("main scenario")
                )
            except (OSError, ValueError) as err:
                st.error(_("Not saved: {reason}").format(reason=reason(err)))
            else:
                tell(
                    _("Saved: the main scenario {scenario}, compared with {others}").format(
                        scenario=main, others=format_list(others, locale=i18n.language())
                    )
                    if others
                    else _("Saved: the main scenario {scenario}, alone in the Explorer").format(
                        scenario=main
                    )
                )
                st.rerun()


def _general(chosen: Chosen, refs: References, docs: Mapping[str, Doc], view: mode.View) -> None:
    """`name`, `note`, `extends` (not itself, not one that extends it) and `Template`, which
    simple mode hides while the scenario is none and the field holds no edit. The scenarios that
    extend it are named: a change here reaches them."""
    key = f"{KEY}general-{chosen.stem}"
    save_in_header(f"{key}-save")
    template = view.advanced or _template(chosen.doc) or (TEMPLATE,) in edited(key)
    general = tuple(FIELDS[(n,)] for n in GENERAL if template or n != TEMPLATE)
    form = Form(key, chosen.file, general, Scenario, labels=LABELS, nulls=NULLS, parts=GENERAL)
    parents = Names(tuple(scenariofiles.parents(refs, chosen.stem)))
    shown = show(chosen.data_dir, form, options={("extends",): parents})
    if kids := scenariofiles.children(refs, chosen.stem):
        st.caption(
            _("Extended by {scenarios}: a change here reaches them.").format(
                scenarios=", ".join(kids)
            )
        )
    if not template:
        mode.hidden_note([_("Template")], ())
    if refused := refusals(chosen.stem, shown.candidate, docs):
        st.warning(
            _("Save stays off: {reasons}").format(reasons="; ".join(map(literal, refused))),
            icon=":material/edit_off:",
        )

    def check() -> None:  # inside the write: another device may have taken the name since
        if problems := refusals(
            chosen.stem, shown.candidate, scenariofiles.raw_scenarios(chosen.data_dir)
        ):
            raise ValueError(problems[0])

    flagged = guard.review(shown.changes(), key=key)
    grids = [Grid(store.Edit(chosen.file), check, f"{key}-check")] if shown.changed else []
    save(
        chosen.data_dir,
        [shown],
        grids,
        key=f"{key}-save",
        flagged=flagged,
        action=chosen.stem,
        ready=not refused,
    )


def _timeline(chosen: Chosen) -> None:
    """Every phase change and event that a run of the scenario sees, with the file that holds it,
    and a button per parent that opens it."""
    try:
        rows = timeline(chosen.data_dir, chosen.path, references.phases(chosen.data_dir))
    except InputError as err:
        st.error(str(err))
        return
    if rows:
        # the ids serve the Overrides tab, not a reader of the timeline
        everything = st.toggle(_("All columns"), key=f"{KEY}timeline-all")
        lineage.read_only(rows, "month", wide="detail", hidden=() if everything else ("id",))
    else:
        st.info(
            _("No phase change or event yet: add them in the tabs Phases and Events."),
            icon=":material/info:",
        )
    fold(
        _(
            "The months as the scenario runs them, after the moves of its overrides. A sale on a "
            "condition comes last. `set in` names the scenario that writes an item, `left out by` "
            "the scenario that leaves out an item of a scenario that it extends."
        )
    )
    parents = [file.stem for file, _raw in chosen.chain[:-1]]
    with st.container(horizontal=True, wrap=True, vertical_alignment="center"):
        for parent in reversed(parents):
            st.button(
                _("Open the parent {scenario}").format(scenario=parent),
                key=f"{KEY}up-{parent}",
                on_click=_open,
                args=(parent,),
                help=_("Show the scenario that this one extends"),
            )
        if not _template(chosen.doc):
            page_link("Explorer", compare_label(chosen.chain), {COMPARE: chosen.stem})


def compare_label(chain: Chain) -> str:
    """The link to the Explorer (`?compare=`): with the nearest parent that runs, which the
    Explorer runs beside the scenario and takes as A of the difference."""
    runs = [raw.get("name") or path.stem for path, raw in chain[:-1] if not _template(raw)]
    return (
        _("Compare with {scenario} in the Explorer").format(scenario=runs[-1])
        if runs
        else _("Run it in the Explorer")
    )


def page(data_dir: Path) -> None:
    st.title(_("Scenarios"))
    docs = scenariofiles.raw_scenarios(data_dir)
    refs = references.of(data_dir)
    order = tree({stem: _parent(doc) for stem, doc in docs.items()})
    saved, first = opening(docs, references.read(data_dir, APP).get("scenarios"))
    if first is not None:  # a scenario runs
        _plan(data_dir, docs, saved, first)
    row = st.container(horizontal=True, vertical_alignment="bottom", wrap=True)
    if not docs:
        st.info(_("No scenario yet: start one with `New`."))
        actions(data_dir, None, Plan(docs, first), row)
        return
    stem = _chooser(docs, order, first, row)
    chosen = Chosen(data_dir, stem, docs[stem])
    actions(data_dir, chosen, Plan(docs, first), row)
    try:
        loader.load_plan(data_dir, chosen.path)
    except InputError as err:
        st.warning(
            _(
                "This scenario does not load. A save here is refused only for a problem that it "
                "adds, so you can fix or delete it:"
            ),
            icon=":material/warning:",
        )
        st.code(str(err), language=None, wrap_lines=True)
    # the tab that another page links to, the type of an event there (`events.open_type`)
    tab = st.query_params.pop(TAB, None)
    if kind := st.query_params.pop(EVENT, None):
        events.open_type(stem, kind)
        tab = "Events"
    # simple mode shows the overrides of a scenario that holds some, or edits not saved yet
    view = mode.view(data_dir)
    overridden = (
        view.advanced
        or view.uses.overrides(stem)
        or tab == OVERRIDES
        or scenario_overrides.unsaved(stem)
    )
    titles = [t for t in TABS if overridden or t != OVERRIDES]
    # keyed: on a phone its tab bar stays at the top (`ui.PAGE_STYLE`)
    boxes = st.container(key="scenarios-tabs").tabs(
        [_(t) for t in titles], default=_(tab) if tab in titles else None
    )
    drawn = dict(zip(titles, boxes, strict=True))
    with drawn["Timeline"]:
        _timeline(chosen)
    with drawn["General"]:
        _general(chosen, refs, docs, view)
    with drawn["Phases"]:
        phases.tab(data_dir, chosen.path, view)
    with drawn["Events"]:
        events.tab(chosen.path)
    if overridden:
        with drawn[OVERRIDES]:
            scenario_overrides.tab(chosen.path)
    else:
        mode.hidden_note([_(OVERRIDES)], (), held=mode.Held.KINDS)
