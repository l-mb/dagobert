"""The overrides of one scenario file, the `Overrides` tab of the Scenarios page (`tab`). The
sections of the Assumptions page in override mode: an empty field inherits through the `extends`
chain, and its placeholder names the value and the file it comes from. `Scale`: a factor per
expense category and per savings plan, and the salary of each phase in euros of a usual month,
as the explorer's slider shows it. The overrides by id as grids (`overridegrids`). One Save
writes the tab as one revision through the save guard, once the plans of the scenario and of
those that extend it load with the edits (the live check), refused when a part changed elsewhere
since it was drawn."""

from __future__ import annotations

import dataclasses
import shutil
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from dagobert import budget, loader, overrides, revisions, scenariofiles, store
from dagobert.i18n import N_, _
from dagobert.model.assumptions import Assumptions
from dagobert.model.base import KeyPath, Unit
from dagobert.money import format_eur
from dagobert.overrides import ASSUMPTIONS, DEFAULT, Leaf
from dagobert.problems import InputError, Problem
from dagobert.references import Kind, phases
from dagobert.ui import (
    Stamp,
    assumptions,
    data_stamp,
    fields,
    fixed,
    fold,
    forms,
    guard,
    literal,
    mode,
    overridegrids,
    tables,
)
from dagobert.ui.assumptions import TABS, AssumptionsForm, Tab
from dagobert.ui.gridcolumns import number
from dagobert.ui.overridegrids import KEY, OWN, Grids, Here, doc
from dagobert.ui.tables import save_in_header
from dagobert.ui.widgets import Names

SCALE = Tab("scale", N_("Scale"), ("scale",))
SALARY: KeyPath = ("scale", "salary")
GROWTH: KeyPath = ("scale", "growth")
SPENDING: KeyPath = ("scale", "spending")
CATEGORIES: KeyPath = ("scale", "categories")
SAVINGS: KeyPath = ("scale", "savings")
FACTORS = {
    SPENDING: N_("All spending"),
    CATEGORIES: N_("Spending by category"),
    SAVINGS: N_("Savings plans"),
}  # in percent
NAMES = {(*CATEGORIES, "name"): N_("category"), (*SAVINGS, "name"): N_("savings plan")}  # keys
STREAMS = "cashflows.yaml"  # the source of a salary at the factor 1
INTRO = N_(
    "What this scenario changes of `assumptions.yaml` and of the items of the scenarios that it "
    "extends. An empty field takes what it inherits, in gray with where it comes from: the "
    "default, `assumptions.yaml` or a scenario that this one extends. A value that you set here "
    "stays when that changes later, also when it equals it now. Shares and rates in percent: 2.5 "
    "for 2.5%."
)
FACTOR_HELP = {
    SPENDING: N_(
        "Factor on every expense stream of the categories, in percent: 90 spends 10% less."
    ),
    CATEGORIES: N_(
        "Factor on the expense streams of the category, in percent: 90 spends 10% less."
    ),
    SAVINGS: N_(
        "Factor on the rate of the savings plan, in percent: 150 saves half as much again."
    ),
}
SCALE_HELP = N_(
    "A salary shows as the gross of a usual month in the phase, in euros of the start, as on the "
    "slider of the Explorer. The file keeps a factor on every salary payment of the phase, so a "
    "bonus changes by the same share. A phase without a salary in the run shows the factor. The "
    "growth of a phase is a rate per year in percent on top of the index of the streams, stepped "
    "each January from the start of the phase."
)


@dataclass(frozen=True)
class ScaleForm(AssumptionsForm):
    """`scale` of a scenario file: a factor per expense category, and per phase with a salary in
    the run its usual gross at the factor 1 (`gross`): the field shows the factor times it in
    euros, and the file keeps the factor (`stored`)."""

    gross: Mapping[str, float] = dataclasses.field(default_factory=dict)

    def mapping(self, doc: Mapping[str, Any]) -> dict[str, Any]:
        return _salaries(super().mapping(doc), self.euros)

    def stored(self, path: KeyPath, value: Any) -> Any:  # noqa: ANN401 a value of a field
        phase = _phase(path)
        if phase is None or phase not in self.gross or not number(value):
            return value
        return round(value / self.gross[phase], 6)  # as the explorer's slider

    def leaves(self, data_dir: Path, candidate: Mapping[str, Any]) -> dict[KeyPath, Leaf]:
        """The fallback of `AssumptionsForm` in euros, a salary without one at the factor 1: the
        gross that the streams pay; a growth without one 0, the default."""
        found = super().leaves(data_dir, self.factors(candidate))
        growth = [f.path for f in self.fields if f.path[:2] == GROWTH and f.path not in found]
        return (
            found
            | {
                (*SALARY, phase): Leaf(self.euros(phase, held.value), held.source)
                if (held := found.get((*SALARY, phase)))
                else Leaf(gross, STREAMS)
                for phase, gross in self.gross.items()
            }
            | dict.fromkeys(growth, Leaf(0.0, DEFAULT))
        )

    def problems(
        self, data_dir: Path, doc: Mapping[str, Any], candidate: Mapping[str, Any]
    ) -> list[Problem]:
        return super().problems(data_dir, doc, self.factors(candidate))

    def euros(self, phase: str, factor: Any) -> Any:  # noqa: ANN401 a value of the file
        """A factor of the salary of `phase` as the euros that it pays, where the phase has a
        gross."""
        if phase not in self.gross or not number(factor):
            return factor
        return round(factor * self.gross[phase], 2)

    def factors(self, part: Mapping[str, Any]) -> dict[str, Any]:
        """`part` with its salaries as the file keeps them."""
        return _salaries(part, lambda phase, euros: self.stored((*SALARY, phase), euros))


def _phase(path: KeyPath) -> str | None:
    return path[-1] if len(path) == 3 and path[:2] == SALARY else None


def _per_phase(path: KeyPath) -> bool:
    """A salary or a growth of a phase."""
    return len(path) == 3 and path[:2] in (SALARY, GROWTH)


def _salaries(part: Mapping[str, Any], convert: Callable[[str, Any], Any]) -> dict[str, Any]:
    """`part` with `convert(phase, value)` of each salary of its `scale`, a copy."""
    scale = part.get("scale")
    salary = scale.get("salary") if isinstance(scale, dict) else None
    if not isinstance(scale, dict) or not isinstance(salary, dict):
        return dict(part)
    return {**part, "scale": {**scale, "salary": {p: convert(p, v) for p, v in salary.items()}}}


def gross(data_dir: Path, stem: str, leaves: Mapping[KeyPath, Leaf]) -> dict[str, float] | None:
    """The gross of a usual month per phase with a salary at the factor 1, in euros of the start,
    from the `fixed` run of the files (`budget.regular_salary`, as the explorer's slider) over the
    factor that the run took (`leaves`: `overrides.effective` of the file). None without a run: a
    template, a scenario that does not load."""
    try:
        result = fixed.result(data_dir, stem)
    except InputError:
        return None
    if result is None:
        return None
    found = {}
    for phase, paid in budget.regular_salary(result).items():
        leaf = leaves.get((*SALARY, str(phase)))
        factor = 1 if leaf is None else leaf.value
        if number(factor) and factor:
            found[str(phase)] = round(paid / factor, 2)
    return found


def scale_form(
    file: str,
    stem: str,
    salaries: Mapping[str, float] | None,
    held: Collection[KeyPath],
    phases: Mapping[str, str],
) -> ScaleForm:
    """The form of `scale` in the scenario file `file`: the factors by category, then of the
    `phases` (each with how the pages name it) per phase with a salary in the run (`salaries`) its
    gross in euros and its growth, per phase without one the factor and the growth that the chain
    holds (`held`, by key path); without a run every phase with both. Keyed by the gross: a value
    shown in euros means another factor once the run changes."""
    gross = {p: g for p, g in (salaries or {}).items() if g}
    found, labels = [], {SALARY: N_("Scale salary"), GROWTH: N_("Raises per year")}
    empty = {SALARY: fields.EMPTY_ONE, GROWTH: fields.EMPTY_ZERO}
    for field in (
        entry
        for top in SCALE.fields
        for entry in (fields.entries(top, phases, empty[top.path]) if top.path in empty else [top])
    ):
        phase = _phase(field.path)
        if _per_phase(field.path) and not (
            salaries is None or field.path[-1] in gross or field.path in held
        ):
            continue  # a phase without pay in the run, which the chain sets nothing for
        if field.path[:2] == GROWTH:
            found.append(field)
            label = _("Raises in {phase}").format(phase=phases[field.path[-1]])
            labels[field.path] = f"{label} %"
        elif phase in gross:
            # in words of the session here, with the label of the phase as written; `said` formats
            # `about` once more, so its braces double
            usual = _("A usual month in `{phase}` pays {amount} at the factor 1.").format(
                phase=phases[phase], amount=format_eur(gross[phase])
            )
            about = f"{usual} {_(field.about)}".replace("{", "{{").replace("}", "}}")
            found.append(replace(field, unit=Unit.EUR, about=about))
            labels[field.path] = _("Salary and profit in {phase} €").format(phase=phases[phase])
        elif field.path in FACTORS:  # a factor in percent, as on the explorer's slider
            text = FACTOR_HELP[field.path]
            cols = tuple(
                replace(c, unit=Unit.PERCENT, about=text, named=None, more=())
                for c in field.columns
            )
            found.append(
                replace(field, columns=cols)
                if cols
                else replace(field, unit=Unit.PERCENT, about=text, named=None, more=())
            )
        else:
            found.append(field)
            if phase is not None:
                labels[field.path] = _("Salary and profit in {phase}").format(phase=phases[phase])
    return ScaleForm(
        f"{KEY}-{stem}-scale-{revisions.digest(gross)[:8]}",
        file,
        tuple(found),
        Assumptions,
        OWN,
        override=True,
        labels=assumptions.LABELS | FACTORS | NAMES | labels,
        nulls=assumptions.NULLS,
        gross=gross,
    )


def trial(data_dir: Path, edit: store.Edit, stems: Sequence[str]) -> list[Problem]:
    """What the plans of the scenarios `stems` refuse with `edit` written: the live check before
    a Save, on a copy of the plan files (`revisions.PLAN`) in a temporary directory. Raises
    ValueError for an edit that the file cannot take (a value below one that is no mapping)."""
    written = edit.text(data_dir)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for pattern in revisions.PLAN:
            for path in data_dir.glob(pattern):
                copy = root / path.relative_to(data_dir)
                copy.parent.mkdir(exist_ok=True)
                shutil.copyfile(path, copy)
        if written is None:
            (root / edit.name).unlink(missing_ok=True)
        else:
            (root / edit.name).write_text(written, encoding="utf-8")
        return plans(root, stems)


def plans(data_dir: Path, stems: Sequence[str]) -> list[Problem]:
    """What the plans of the scenarios `stems` refuse, each problem once."""
    found: dict[Problem, None] = {}
    for stem in stems:
        try:
            loader.load_plan(data_dir, data_dir / scenariofiles.scenario_file(stem))
        except InputError as err:
            found |= dict.fromkeys(err.problems)
    return list(found)


@st.cache_data(max_entries=8, show_spinner=False)  # a few scenarios at the latest stamp
def _held(data_dir: str, stems: tuple[str, ...], stamp: Stamp) -> set[tuple[str, str, str]]:
    """The problems of the plans `stems` as the files hold them (`_problem`), once per state of
    the inputs (`stamp`): a scenario with many children takes about 25 ms each."""
    del stamp
    return {_problem(p) for p in plans(Path(data_dir), stems)}


def _problem(problem: Problem) -> tuple[str, str, str]:
    """A problem without its line, which an edit above it moves (as the write compares them)."""
    return problem.file, problem.path, problem.message


def _checked(
    here: Here,
    shown: Sequence[forms.Shown],
    grids: Grids,
    top: DeltaGenerator,
) -> bool:
    """The live check: whether the plans of the scenario and of those that extend it load with
    the edits, or refuse only what they refused before. What the edits add shows in `top`. It
    follows once every form and grid reads: it would repeat what they show."""
    edits = [*(s.edit() for s in shown if s.changed), *([grids.grid.edit] if grids.grid else [])]
    blocked = grids.unread or grids.stale or any(map(_blocked, shown))
    if not edits or blocked:
        return not blocked
    try:
        found = trial(here.data_dir, forms.merged(edits)[0], here.below)
    except ValueError as err:
        added = [str(err)]
    else:
        held = _held(str(here.data_dir), tuple(here.below), data_stamp(here.data_dir))
        added = [str(p) for p in found if _problem(p) not in held]
    if added:
        with top:
            st.warning(
                "  \n".join([_("Save stays off until the plan loads:"), *map(literal, added)]),
                icon=":material/edit_off:",
            )
    return not added


def _hint(shown: Sequence[forms.Shown], grids: Grids) -> str:
    """The sentence of the guard on the language of the browser, for a number cell of a grid."""
    hints = [assumptions.hint(s.form, changes(s)) for s in shown]
    months = any(c.warning and c.named.startswith("shift ") for c in grids.listed)
    return guard.LOCALE if months or any(hints) else ""


def tab(path: Path) -> None:
    """The overrides of the scenario file `path` (`<data>/scenarios/<stem>.yaml`): the sections
    of the assumptions with the fields that the mode and the features show (`assumptions.Tab`,
    a note of the rest), `Scale` and the grids by id, each in an expander, open while the file
    sets something there; one Save for all of them."""
    data_dir = path.parents[1]
    save_key = f"{KEY}-{path.stem}-save"
    save_in_header(save_key)
    try:
        here = Here(path, loader.chain(path), tables.known(data_dir))
        leaves = overrides.effective(data_dir, path)
    except InputError as err:
        said = _(
            "The overrides inherit through `extends`, which does not read: change it in the tab "
            "`General`."
        )
        st.warning(f"{said}  \n{literal(str(err))}", icon=":material/error:")
        return
    st.caption(_("What this scenario changes of the assumptions and of the scenarios it extends."))
    fold(_(INTRO))
    _start(leaves, here.stem)
    top = st.container()
    own = overrides.leaves(_own(doc(path)))
    names = assumptions.options(here.refs, here.stem) | {
        CATEGORIES: Names(tuple(here.refs.names(Kind.CATEGORY, here.stem))),
        SAVINGS: Names(tuple(here.refs.names(Kind.STREAM, here.stem, sorts=("savings",)))),
    }
    held = [p for p in leaves if _per_phase(p)]
    salaries = gross(data_dir, here.stem, leaves)
    view = mode.view(data_dir)
    tabs = {
        t: t.form(file=here.file, keys=OWN, override=True, key=here.key, view=view) for t in TABS
    }
    parts = [
        *((t, form) for t, form in tabs.items() if form.fields),
        (SCALE, scale_form(here.file, here.stem, salaries, held, phases(data_dir))),
    ]
    shown = []
    for part, form in parts:
        count = sum(p[0] in form.tops for p in own)
        label = _(part.title) + (f" ({count})" if count else "")
        with st.expander(label, expanded=bool(count), key=f"{here.key}-{part.key}-open"):
            if isinstance(form, ScaleForm):
                fold(_(SCALE_HELP), _("About the salary"))
            shown.append(forms.show(data_dir, form, options=names))
            if part in tabs:
                view.note(part.hidden(form, view, override=True), held=mode.Held.INHERITED)
    # a part without a field to show, by what it hides
    left = (t.hidden(form, view, override=True) for t, form in tabs.items() if not form.fields)
    view.note(
        {item: words for hidden in left for item, words in hidden.items()}, held=mode.Held.INHERITED
    )
    grids = overridegrids.grids(here, leaves, top)
    ready = _checked(here, shown, grids, top)
    with top:
        if waiting := [_(t.title) for (t, _f), s in zip(parts, shown, strict=True) if _blocked(s)]:
            st.warning(
                _("Save stays off: see {parts} below.").format(parts=", ".join(waiting)),
                icon=":material/edit_off:",
            )
        if grids.unread:
            st.warning(
                _("Save stays off until these read: {rows}").format(
                    rows="; ".join(
                        f"**{literal(r)}** {literal(p)}" for r, p in grids.unread.items()
                    )
                ),
                icon=":material/edit_off:",
            )
    found = [c for s in shown for c in changes(s)] + grids.listed
    flagged = guard.review(found, key=here.key, hint=_hint(shown, grids))
    forms.save(
        data_dir,
        shown,
        [grids.grid] if grids.grid else [],
        key=save_key,
        flagged=flagged,
        action=here.stem,
        ready=ready,
    )


def unsaved(stem: str) -> bool:
    """Whether a form or a grid of the tab of the scenario `stem` holds an edit not saved yet,
    before it draws: the tab stays while simple mode would hide it (rule `mode`). The form of
    `Scale` is keyed by the gross of its run (`scale_form`), so it is found by its start."""
    key, state = f"{KEY}-{stem}", st.session_state
    scale = (
        k.removesuffix("-drawn")
        for k in map(str, state)
        if k.startswith(f"{key}-scale-") and k.endswith("-drawn")
    )
    keys = [*(f"{key}-{t.key}" for t in TABS), *scale]
    return overridegrids.unsaved(stem) or any(forms.edited(k) for k in keys)


def changes(shown: forms.Shown) -> list[guard.Change]:
    """The guard list of a form of the tab: a factor of a category or of a savings plan shows in
    percent, and above 100% it is no share that the guard warns of."""
    factors = tuple(" ".join(path) + " " for path in FACTORS)
    found = shown.changes()
    return [replace(c, capped=False) if c.named.startswith(factors) else c for c in found]


def _start(leaves: Mapping[KeyPath, Leaf], stem: str) -> None:
    """A `start` that a scenario file overrides, read only: the roll forward moves the one of
    `assumptions.yaml`."""
    held = leaves.get(("start",))
    if held is None or held.source in (ASSUMPTIONS, DEFAULT):
        return
    month = f"{held.value:%Y-%m}" if isinstance(held.value, date) else str(held.value)
    said = (
        _(
            "Start overridden: {month}, in this file. This tab does not edit it, and the roll "
            "forward on the Overview moves only the start of `assumptions.yaml`."
        )
        if held.source == stem
        else _(
            "Start overridden: {month}, from {source}. This tab does not edit it, and the roll "
            "forward on the Overview moves only the start of `assumptions.yaml`."
        )
    )
    st.caption(said.format(month=month, source=held.source))


def _blocked(shown: forms.Shown) -> bool:
    """Whether a form keeps Save off: a field that does not read, a refusal of the model, a change
    on disk since it was drawn. It says why above its fields, which an expander may hide."""
    return bool(shown.typed.unread or shown.refused or shown.stale)


def _own(doc: Mapping[str, Any]) -> dict[str, Any]:
    found = doc.get("overrides")
    return dict(found) if isinstance(found, dict) else {}
