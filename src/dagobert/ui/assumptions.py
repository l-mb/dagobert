"""The `Assumptions` page: `assumptions.yaml` in four tabs of forms from the model (`ui.forms`),
`Person`, `Markets`, `Rules` and `Tax`, each with one Save, one revision `Assumptions: <tab>`.
`start` shows read only: the roll forward of the Overview moves it together with the amounts in
euros of the start. `scale` is set in the overrides of a scenario, so it does not show. The
`phases` and the relatives of `Person` show their name on the pages first (`LabeledRows`) and keep
a short name that the inputs use (`refused`): `Rename` below the tables renames it with them
(`ui.rename`). Below them the gifts of a relative before the start (`_given`), with a Save of
their own. The Overrides tab of a scenario takes the same tabs on its file (`Tab.form`), without
the phases, which a scenario does not define. Simple mode and the features leave out the fields
that the inputs do not use (`Tab.shown`, rule `mode`), a tab without a field to show whole, and a
note names them."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from functools import partial
from typing import TYPE_CHECKING, Any

import streamlit as st

from dagobert import references, tax
from dagobert.i18n import N_, _, pgettext
from dagobert.loader import read_yaml
from dagobert.model.assumptions import Assumptions, Given, phase_name_for
from dagobert.model.base import KeyPath, description
from dagobert.model.months import months_between
from dagobert.model.taxes import TAX_YEARS, default_tax_year
from dagobert.overrides import Leaf
from dagobert.references import Kind, References
from dagobert.store import RowFile
from dagobert.ui import (
    fold,
    forms,
    gridcolumns,
    gridstate,
    guard,
    is_mobile,
    literal,
    mode,
    overview,
    page_link,
    rename,
    save,
    tables,
)
from dagobert.ui.fields import SYMBOL, Field, lookup, of
from dagobert.ui.fields import Kind as FieldKind
from dagobert.ui.forms import Form, When, show
from dagobert.ui.forms import save as save_tab
from dagobert.ui.gridcolumns import said
from dagobert.ui.tables import MapRows, save_in_header
from dagobert.ui.widgets import WIDTH, Names

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping
    from pathlib import Path

    from dagobert.problems import Keys

FILE = "assumptions.yaml"
KEY = "assumptions"
TAX_YEAR: KeyPath = ("tax", "year")
KV_ZUSATZ: KeyPath = ("tax", "kv_zusatz")
RV: KeyPath = ("tax", "self_employed", "rv")
PKV: KeyPath = ("tax", "pkv")
GKV_FROM: KeyPath = ("tax", "gkv_from")
FIELDS = tuple(of(Assumptions))
PHASES = "phases"  # defined in `assumptions.yaml` only, not in the overrides of a scenario
RELATIVES: KeyPath = ("person", "relatives")
SHOWN = 3  # the uses that the refusal of a removed phase names
RENAME = N_("Type the name back: `Rename` below the table changes it there too.")
# Plain words: the technical term is in `TERMS`, the key path in the save guard. A key path of
# a grid column ends in its name, of a heading in its model. English, marked for the catalogue:
# the forms say them in the language of the session.
AVERAGE, SPREAD = N_("average"), N_("volatility")
LABELS: dict[KeyPath, str] = {
    ("person", "born"): N_("Date of birth"),
    ("person", "horizon_age"): N_("Plan up to age"),
    ("person", "rv_since"): N_("Pension insurance since"),
    ("person", "kvdr"): N_("Health insurance of pensioners (KVdR)"),
    ("person", "children_born"): N_("Children by date of birth"),
    ("person", "children_born", "born"): N_("date of birth"),
    ("person", "children_born", "until"): N_("counts as a child until"),
    ("person", "children_born", "kindergeld"): N_("Kindergeld paid to you"),
    ("person", "children_born", "freibetrag"): N_("child allowance"),
    ("person", "children_born", "erziehung"): N_("child-raising years credited to your pension"),
    RELATIVES: N_("Relatives you may inherit from"),
    (*RELATIVES, "name"): N_("short name in the files"),
    (*RELATIVES, "label"): N_("name on the pages"),
    (*RELATIVES, "born"): N_("date of birth"),
    (*RELATIVES, "sex"): N_("sex"),
    (*RELATIVES, "relation"): N_("relation"),
    (PHASES,): N_("Phases of life"),
    (PHASES, "name"): N_("short name in the files"),
    (PHASES, "label"): N_("name on the pages"),
    ("inflation", "mean"): N_("Average per year %"),
    ("inflation", "stdev"): N_("Volatility %"),
    ("indices",): N_("Growth indices"),
    ("indices", "name"): N_("index"),
    ("indices", "mean"): AVERAGE,
    ("indices", "stdev"): SPREAD,
    ("indices", "floor"): N_("lowest"),
    ("indices", "cap"): N_("highest"),
    ("indices", "cumulative"): N_("compounds"),
    ("returns",): N_("Returns by asset class"),
    ("returns", "name"): N_("asset class"),
    ("returns", "mean"): AVERAGE,
    ("returns", "stdev"): SPREAD,
    ("returns", "equity_correlation"): N_("correlation with equity"),
    ("refinance_rate",): N_("Loan rate after the fixed period %"),
    ("pension_growth",): N_("Pension growth per year %"),
    ("cash_buffer_months",): N_("Cash buffer (months)"),
    ("allocation", "fixed_income"): N_("Fixed-income share by age"),
    ("allocation", "rebalance_every"): N_("Rebalance every (months)"),
    ("allocation", "skip_after_loss"): N_("Skip after a loss (months)"),
    ("spending",): N_("Spending rule"),
    ("spending", "base"): N_("Reference wealth from"),
    ("spending", "reference"): N_("Reference wealth at the start €"),
    ("spending", "cut"): N_("Cut in a bad time %"),
    ("spending", "trigger"): N_("Cut below this share of the reference wealth %"),
    ("spending", "increase"): N_("Increase in a good time %"),
    ("spending", "ceiling"): N_("Increase above this share of the reference wealth %"),
    ("spending", "categories"): N_("Flexible categories"),
    ("spending", "age_curve"): N_("Spending by age"),
    ("spending", "age_categories"): N_("Categories of the spending by age"),
    ("spending", "vpw"): N_("Variable percentage withdrawal (VPW)"),
    ("spending", "vpw", "growth"): N_("Growth trend, real % per year"),
    ("spending", "vpw", "horizon_age"): N_("Spend down to age"),
    ("spending", "vpw", "floor"): N_("Floor of the flexible spending € per month"),
    ("care",): N_("Long-term care"),
    ("care", "hazard"): N_("Yearly chance of care by age"),
    ("care", "hazard", "factor"): N_("chance"),
    ("care", "cost"): N_("Cost per month €"),
    ("care", "duration"): N_("Length of a care episode"),
    ("care", "duration", "mean"): N_("Average (months)"),
    ("care", "duration", "stdev"): N_("Volatility (months)"),
    ("care", "index"): N_("Cost follows"),
    ("disability",): N_("Disability"),
    ("disability", "hazard"): N_("Yearly chance of a disability by age"),
    ("disability", "hazard", "factor"): N_("chance"),
    ("disability", "at"): N_("Disabled from (what-if)"),
    ("tax", "year"): N_("Tax year"),
    ("tax", "sparer_pauschbetrag"): N_("Tax-free capital income €"),
    ("tax", "teilfreistellung"): N_("Fund gains tax-free %"),
    ("tax", "werbungskosten"): N_("Work expenses per year €"),
    ("tax", "harvest"): N_("Realize gains each December within the tax-free room"),
    PKV: N_("Private health insurance (PKV)"),
    GKV_FROM: N_("Statutory health insurance from"),
    ("tax", "kv_zusatz"): N_("Health fund extra rate %"),
    ("tax", "church"): N_("Church tax"),
    ("tax", "land"): N_("Bundesland"),
    ("tax", "crypto_capital_from"): N_("Crypto taxed like shares from"),
    ("tax", "loss_carryforward"): N_("Losses carried forward €"),
    ("tax", "loss_carryback"): N_("Carry a loss back into the two years before"),
    ("tax", "capital_losses"): N_("Capital losses carried forward €"),
    ("tax", "alleinerziehend"): N_("Single parent (Entlastungsbetrag)"),
    ("tax", "self_employed"): N_("Self-employment"),
    ("tax", "self_employed", "rv"): N_("Pension insurance of a business"),
    ("tax", "self_employed", "krankengeld"): N_("Sick pay in the GKV"),
    ("tax", "self_employed", "founded"): N_("Business founded"),
    ("invest_rest",): N_("Invest the rest"),
    ("seed",): N_("Random seed"),
}
# the technical term of a field, before its help: German in both languages
TERMS: dict[KeyPath, str] = {
    ("person", "rv_since"): "Rentenversicherung (RV)",
    ("person", "kvdr"): "Krankenversicherung der Rentner",
    ("tax", "sparer_pauschbetrag"): "Sparer-Pauschbetrag",
    ("tax", "teilfreistellung"): "Teilfreistellung",
    ("tax", "werbungskosten"): "Werbungskosten",
    ("tax", "harvest"): "Günstigerprüfung",
    PKV: "Private Krankenversicherung",
    GKV_FROM: "Gesetzliche Krankenversicherung",
    ("tax", "kv_zusatz"): "Zusatzbeitrag",
    ("tax", "church"): "Kirchensteuer",
    ("tax", "loss_carryforward"): "Verlustvortrag",
    ("tax", "loss_carryback"): "Verlustrücktrag",
    ("tax", "capital_losses"): "Verlustvortrag aus Kapitalvermögen",
    ("tax", "self_employed", "rv"): "Rentenversicherung (RV)",
    ("tax", "self_employed", "krankengeld"): "Krankengeld",
}
# help in words where the description of the model names keys of the files
HELPS: dict[KeyPath, str] = {
    (PHASES,): N_(
        "The phases of life that the scenarios switch between, such as work, a career break or "
        "retirement, in the order of the columns and the colors. A stream pays in the phases of "
        "its row, the employer into a pension policy in those of the policy. The name on the pages "
        "takes capitals and umlauts. The short name is used inside the data files (All columns): a "
        "new phase takes it from its name on the pages. A phase in use keeps its short name here: "
        "Rename below the table changes it everywhere. The phases are the same in every scenario."
    ),
    RELATIVES: N_(
        "The relatives from whom you may inherit or receive gifts, never a spouse: the "
        "inheritances and gifts of the scenarios name them by their short name (All columns), "
        "which a new row takes from its name on the pages. The relation sets the tax class and the "
        "Freibetrag of the Erbschaftsteuer every ten years: 400,000 € from a parent or "
        "step-parent, 200,000 € from a grandparent, 20,000 € from the others. The date of birth "
        "and the sex draw the month of death from the life table. A relative in use keeps its "
        "short name here: Rename a relative changes it everywhere."
    ),
    RV: N_(
        "Statutory pension insurance on the profit of your business, in a month in which it is "
        "your main work. None: no compulsory contribution; a voluntary one is a stream on the "
        "Cashflows page. Fixed contribution: the Regelbeitrag on the Bezugsgröße, half of it up to "
        "the end of the third calendar year after the founding. By profit: on the profit up to the "
        "contribution ceiling, at least on the Geringfügigkeitsgrenze, never half. The law makes "
        "both compulsory for some trades (§2 SGB VI) or on application (§4 Abs. 2) (default: none)"
    ),
    ("person", "children_born"): N_(
        "Your children with their dates of birth, also grown ones. A child counts up to its 18th "
        "birthday; a child in education up to the month before the one in `counts as a child "
        "until`, at most to its 25th birthday. While it counts, the plan pays its Kindergeld when "
        "it is paid to you, the tax takes the child allowances instead where that saves more, "
        "ALG1 pays 67% instead of 60%, and a single parent deducts the Entlastungsbetrag. The "
        "child allowance is half for each parent, or full when the other parent pays no support. "
        "The child-raising years give pension points for the three years after the birth. A "
        "member of the statutory health insurance pays less Pflegeversicherung for the second "
        "child under 25 and each further one."
    ),
    ("tax", "loss_carryforward"): N_(
        "The losses of earlier years in your last Feststellungsbescheid (§10d Abs. 4 EStG), such "
        "as of a let flat or a business: they offset your income before the Sonderausgaben, in "
        "euros of the start month. The roll forward writes the losses that the plan carries to "
        "the new start (default: 0 €)"
    ),
    ("spending", "base"): N_(
        "The wealth that the cut and the increase compare with. The start, always: the liquid "
        "wealth at the start, and the rules act in every month. The first month without pay: the "
        "liquid wealth when your salary and your profit stop, and the rules act only in the months "
        "after a month without them. ALG1 and other income are no pay. After twelve months of pay "
        "in a row the next month without pay takes a new reference wealth: a retirement after a "
        "career break and a new job compares with its own wealth (default: the start, always)"
    ),
    ("spending", "reference"): N_(
        "The reference wealth of the start, in euros of the start: always with The start, always, "
        "else when the plan starts without pay. Empty: the liquid wealth of the start, so a new "
        "start after a crash stops the cut, one after a boom the increase. The roll forward "
        "changes a value by the consumer prices (default: none)"
    ),
    GKV_FROM: N_(
        "With private health insurance: the first month in the statutory health insurance (GKV). "
        "From it the rules of the GKV apply, and the premiums of the private insurance end. "
        "Before 55 a salary below the Jahresarbeitsentgeltgrenze or ALG1 makes you a compulsory "
        "member (§5 SGB V); from 55 §6 Abs. 3a usually blocks the return. A scenario sets it to "
        "compare both. Empty: the private insurance for the whole run (default: none)"
    ),
    ("tax", "self_employed", "founded"): N_(
        "The month in which your business was founded. With a fixed contribution the Regelbeitrag "
        "is half up to the end of the third calendar year after it. Empty: the first month in "
        "which a business runs. The roll forward fills it in when a business runs before the new "
        "start"
    ),
}
# the words of the options of a choice
CHOICES: dict[KeyPath, dict[object, str]] = {
    ("spending", "base"): {
        "start": N_("The start, always"),
        "no_pay": N_("The first month without pay"),
    },
    RV: {
        "none": N_("None"),
        "regular": N_("Fixed contribution (Regelbeitrag)"),
        "income": N_("By profit"),
    },
}
# the fields that take effect only with a value of another
WHEN: dict[KeyPath, When] = {
    GKV_FROM: When(PKV, (True,), N_("private insurance only")),
    ("tax", "self_employed", "krankengeld"): When(
        PKV, (False,), N_("statutory insurance only"), unless=GKV_FROM
    ),
    ("tax", "self_employed", "founded"): When(RV, ("regular",), N_("fixed contribution only")),
    **{
        ("spending", key): When(("spending", "base"), ("no_pay",), N_("without pay only"))
        for key in ("increase", "ceiling", "vpw")
    },
}
NULLS: dict[KeyPath, str] = {
    ("spending", "age_categories"): N_("Every category except the health premium"),
    ("care", "index"): N_("none: nominal euros"),
}
INTRO = N_("What every scenario assumes: you, the markets, the rules of the run and the tax.")
READING = N_(
    "A scenario changes these values in its overrides, the Explorer with its sliders without "
    "saving. An empty field takes the value that it shows in gray. Type shares and rates in "
    "percent: 2.5 for 2.5%. The help icon of a field explains it and names its default."
)
START = N_(
    "Every amount of the plan is in euros of this month. The roll forward on the Overview moves "
    "it once the month has passed, and changes those amounts by the consumer prices: a start "
    "moved without them would change what each amount means."
)


@dataclass(frozen=True)
class AssumptionsForm(Form):
    """A form of the assumptions, whose empty `tax.year` takes the year of `start`
    (`model.taxes.default_tax_year`; in a scenario the merged `start`, with its source) and whose
    empty `tax.kv_zusatz` the average of that year: the model leaves both to the plan, so their
    default is none. The year counts also while simple mode hides its field."""

    def leaves(self, data_dir: Path, candidate: Mapping[str, Any]) -> dict[KeyPath, Leaf]:
        found = super().leaves(data_dir, candidate)
        year = found.get(TAX_YEAR)
        if year is None or year.value is None:
            start = found.get(("start",))
            if start is None or start.value is None:
                start = Leaf(read_yaml(data_dir / FILE).get("start"), pgettext("source", "start"))
            year = (
                Leaf(default_tax_year(start.value), start.source)
                if isinstance(start.value, date)
                else None
            )
            if year is not None and self._empty(found, TAX_YEAR):
                found[TAX_YEAR] = year
        if year is not None and year.value in TAX_YEARS and self._empty(found, KV_ZUSATZ):
            average = 2 * tax.for_year(year.value).kv_zusatz_half
            found[KV_ZUSATZ] = Leaf(average, _("tax year {year}").format(year=year.value))
        return found

    def _empty(self, found: Mapping[KeyPath, Leaf], path: KeyPath) -> bool:
        """The form shows `path`, and nothing gives it a value."""
        held = found.get(path)
        return any(f.path == path for f in self.fields) and (held is None or held.value is None)


@dataclass(frozen=True)
class LabeledRows(MapRows):
    """The phases or the relatives with their name on the pages first: an empty label shows as
    the pages name it, by its short name, a label equal to that is not written, and a new row
    without a short name takes one from its label (`phase_name_for`)."""

    lead: str | None = "label"

    def rows(self, mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
        return [
            {self.key: name} | dict(entry or {}) | {"label": _label(entry) or name}
            for name, entry in mapping.items()
        ]

    def mapping(self, rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """The rows as phases in their order; a row without a name and a label goes."""
        listed = list(rows)
        taken = {str(row[self.key]) for row in listed if row.get(self.key)}
        found: dict[str, Any] = {}
        for row in listed:
            label = _label(row)
            if not (name := str(row.get(self.key) or "")):
                if not label:
                    continue
                name = phase_name_for(label, taken | set(found))
            kept = {k: v for k, v in row.items() if k not in (self.key, "label")}
            found[name] = kept | ({"label": label} if label not in ("", name) else {})
        return found


def _label(entry: Mapping[str, Any] | None) -> str:
    label = (entry or {}).get("label")
    return label.strip() if isinstance(label, str) else ""


@dataclass(frozen=True)
class Tab:
    """A tab of the page: the keys of the assumptions whose fields it shows, in this order. `key`
    names its widgets, `title` is words, English: the revision source of its Save, translated
    where it shows."""

    key: str
    title: str
    tops: tuple[str, ...]

    @property
    def fields(self) -> tuple[Field, ...]:
        return tuple(f for top in self.tops for f in FIELDS if f.path[0] == top)

    def shown(
        self, *, override: bool, view: mode.View | None = None, kept: Collection[KeyPath] = ()
    ) -> tuple[Field, ...]:
        """The fields of the tab, in an override without the phases, that `view` shows by their
        head (`mode.head`: a section in use shows whole) or whose head holds an edit not saved
        yet (`kept`, `forms.edited`): every field without a view."""
        return tuple(
            f
            for f in self.fields
            if not (override and f.path[0] == PHASES)
            and (
                view is None
                or view.shows(head := mode.head(f.path))
                or any(k[: len(head.key)] == head.key for k in kept)
            )
        )

    def form(
        self,
        *,
        file: str = FILE,
        keys: Keys = (),
        override: bool = False,
        key: str = KEY,
        view: mode.View | None = None,
    ) -> Form:
        """The form of the tab on `assumptions.yaml`, or in a scenario file on its `overrides`
        (`keys`), where an empty field inherits (`override`), with the fields that `view` shows.
        Its part holds every top key of the tab (`Form.parts`), so it keeps its shape whatever
        shows."""
        name = f"{key}-{self.key}"
        kept = () if view is None else forms.edited(name)
        shown = self.shown(override=override, view=view, kept=kept)
        return AssumptionsForm(
            name,
            file,
            shown,
            Assumptions,
            keys,
            override,
            labels=LABELS,
            nulls=NULLS,
            terms=TERMS,
            helps=HELPS,
            choices=CHOICES,
            when=WHEN,
            rows={(PHASES,): LabeledRows(), RELATIVES: LabeledRows()},
            parts=tuple(t for t in self.tops if not (override and t == PHASES)),
            hides={} if view is None else {f.path: c for f in shown if (c := _columns(f, view))},
        )

    def hidden(
        self, form: Form, view: mode.View, *, override: bool = False
    ) -> dict[mode.Item, str]:
        """The heads of the fields of the tab that `form` leaves out, each once with its words,
        for the note of the page (`mode.View.note`): one below another that hides names none,
        unless a feature off hides it (`spending.vpw` below `spending`)."""
        drawn = {f.path for f in form.fields}
        heads = {
            mode.head(f.path): None
            for f in self.fields
            if f.path not in drawn and not (override and f.path[0] == PHASES)
        }
        return {
            item: self.named(form, item.key)
            for item in heads
            if mode.feature(item) in view.off
            or not any(o != item and item.key[: len(o.key)] == o.key for o in heads)
        }

    def named(self, form: Form, path: KeyPath) -> str:
        """A field or a nested model in a note: its label without its unit, after the heading of
        its model unless the tab is named by it (`Inflation · Volatility`, `Tax year`)."""
        field = next((f for f in FIELDS if f.path == path), None)
        if field is None:
            return form.heading(path)
        name = form.label(field).removesuffix(f" {SYMBOL.get(field.unit)}")
        parent = path[:-1]
        return name if parent in ((), (self.key,)) else f"{form.heading(parent)} · {name}"


def _columns(field: Field, view: mode.View) -> frozenset[str]:
    """The columns of a mapping by name that the mode or a feature hides by a head of their own
    (`returns.*.equity_correlation`), whatever the inputs use: the grid shows one that an entry
    holds (`widgets.mapping`), so its columns stay while it holds edits."""
    return frozenset(
        c.name
        for c in field.columns
        if (cell := mode.head((*field.path, "*", c.name))) != mode.head(field.path)
        and not mode.shown(cell, mode.Uses(), view.off, view.advanced)
    )


PERSON = Tab("person", N_("Person"), ("person", PHASES))
TABS = (
    PERSON,
    Tab(
        "markets",
        N_("Markets"),
        ("inflation", "returns", "indices", "refinance_rate", "pension_growth"),
    ),
    Tab(
        "rules",
        N_("Rules"),
        (
            "cash_buffer_months",
            "invest_rest",
            "seed",
            "allocation",
            "spending",
            "care",
            "disability",
        ),
    ),
    Tab("tax", N_("Tax"), ("tax",)),
)


def options(refs: References, scenario: str | None = None) -> dict[KeyPath, Names]:
    """The names that the fields of the tabs take, in a scenario file those that count there: the
    expense categories of the spending rule, the indices of the care cost (with `cpi`)."""
    categories = Names(tuple(refs.names(references.Kind.CATEGORY, scenario)))
    return {
        ("spending", "categories"): categories,
        ("spending", "age_categories"): categories,
        ("care", "index"): Names(tuple(refs.names(references.Kind.INDEX, scenario))),
    }


# what keeps its short name while inputs name it, by its key path in the file
KEPT = {
    (PHASES,): (Kind.PHASE, N_("the phase {name} keeps its name while inputs name it: {uses}")),
    RELATIVES: (
        Kind.RELATIVE,
        N_("the relative {name} keeps its name while inputs name it: {uses}"),
    ),
}


def refused(refs: References, before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Each phase or relative of `before` that `after` (the part of the Person tab, the file and
    the edits) removes or renames while an input names it, with the first of its uses: `Rename`
    below the tables renames it with them."""
    found = []
    for path, (kind, text) in KEPT.items():
        held, kept = (
            p if isinstance(p := lookup(part, path), dict) else {} for part in (before, after)
        )
        found += [
            _(text).format(name=name, uses=_first(uses))
            for name in held
            if name not in kept and (uses := refs.orphans(kind, name, FILE, (*path, name)))
        ]
    return found


def _first(uses: list[references.Site]) -> str:
    """The first `SHOWN` uses, and how many more."""
    listed = "; ".join(map(str, uses[:SHOWN]))
    more = len(uses) - SHOWN
    return _("{uses} and {n} more").format(uses=listed, n=more) if more > 0 else listed


def hint(form: Form, found: list[guard.Change]) -> str:
    """The sentence of the guard on the language of the browser, for a warning of a grid cell:
    a text field reads a comma and a point alike."""
    grids = tuple(
        f"{' '.join(f.path)} " for f in form.fields if f.kind in (FieldKind.ROWS, FieldKind.MAP)
    )
    return guard.LOCALE if any(c.warning and c.named.startswith(grids) for c in found) else ""


def _start(data_dir: Path) -> None:
    """`start`, read only, with the way to the roll forward."""
    start = read_yaml(data_dir / FILE).get("start")
    st.markdown(f"**{_('Simulation start')}**")
    shown = f"{start:%Y-%m}" if isinstance(start, date) else str(start or "")
    st.text_input(
        _("Start month (read only)"),
        value=shown,
        key=f"{KEY}-start-{shown}",  # a roll forward shows its month
        disabled=True,
        help=said(description(Assumptions, ("start",)), more=(START,)),
        width="stretch" if is_mobile() else WIDTH,
    )
    st.caption(_("The roll forward on the Overview moves it, together with your amounts."))
    if isinstance(start, date) and months_between(start, date.today()) > 0:
        page_link(
            "Overview",
            _("Roll forward on the Overview"),
            {overview.ROLL: overview.OPEN},
            icon=":material/fast_forward:",
        )


@dataclass(frozen=True)
class Here:
    """What every tab of the page draws on: the inputs, the names that its fields take, what
    the inputs name, and what the mode and the features show."""

    data_dir: Path
    names: dict[KeyPath, Names]
    refs: References
    view: mode.View


def _tab(here: Here, tab: Tab, form: Form) -> None:
    """A tab with its form, the renames and gifts of `Person` while its grids show, the note of
    the fields that the view hides, the guard and Save."""
    data_dir, refs = here.data_dir, here.refs
    save_key = f"{form.key}-save"
    save_in_header(save_key)
    shown = show(data_dir, form, options=here.names)
    found = shown.changes()
    kept: list[str] = []
    if tab is PERSON:
        held = bool(found or shown.typed.unread)
        relatives = references.relatives(data_dir)
        estates = any(f.path == RELATIVES for f in form.fields)
        with st.container(horizontal=True, wrap=True):
            rename.button(
                data_dir, Kind.PHASE, list(references.phases(data_dir)), key=KEY, held=held
            )
            if estates:
                rename.button(
                    data_dir,
                    Kind.RELATIVE,
                    list(relatives),
                    key=f"{KEY}-relatives",
                    held=held,
                    label=N_("Rename a relative"),
                )
        if kept := refused(refs, shown.base.part, shown.candidate):
            st.warning(
                _("Save stays off: {reasons}. {rename}").format(
                    reasons="; ".join(map(literal, kept)), rename=_(RENAME)
                ),
                icon=":material/edit_off:",
            )
        if estates:
            _given(data_dir, relatives)
        _start(data_dir)
    here.view.note(tab.hidden(form, here.view))
    flagged = guard.review(found, key=form.key, hint=hint(form, found))
    save_tab(data_dir, [shown], key=save_key, flagged=flagged, action=tab.title, ready=not kept)


GIVEN = N_(
    "The gifts of a relative before the start, nominal, with the Schenkungsteuer paid on each: the "
    "Erbschaftsteuer adds the gifts of ten years to a later inheritance or gift of the same "
    "relative (§14 ErbStG). The roll forward moves a gift of a scenario here once it passed."
)
# the columns of the gifts before the start in words
GIVEN_HEADERS = {"at": N_("month"), "value": N_("value"), "tax": N_("tax paid")}


def _given(data_dir: Path, relatives: Mapping[str, str]) -> None:
    """The gifts of one relative before the start (`given`): a select of the relatives of the
    file by their names on the pages, a grid of its gifts and `Save gifts`, one revision of the
    page, refused where a row that it edits changed since (rule `grids`)."""
    st.markdown(f"**{_('Gifts received before the start')}**")
    fold(_(GIVEN), _("About gifts before the start"))
    if not relatives:
        st.caption(_("Add a relative above first, and save it."))
        return
    picked = st.selectbox(
        _("Relative"),
        list(relatives),
        format_func=lambda key: relatives.get(key, key),
        key=f"{KEY}-given-relative",
    )
    if picked is None:
        return
    key = f"{KEY}-given-{picked}"
    file = RowFile(data_dir, FILE, (*RELATIVES, picked, "given"))
    base, changed = save.base(file, key, list, partial(_given_held, key))
    cols = [replace(c, label=GIVEN_HEADERS.get(c.name)) for c in gridcolumns.columns(Given)]
    units, names = gridcolumns.units(cols), gridcolumns.names(cols)
    if changed is not None:
        save.warn(changed, key=key, identity=("at",), units=units, names=names)
    edits = tables.small_grid(cols, list(enumerate(base.rows)), f"{key}-{base.nonce}")
    save.button(
        file,
        edits,
        [],
        read=base.read(("at",)),
        label=_("Save gifts"),
        key=f"{key}-save",
        nonce_key=f"{key}-nonce",
        toast=_("Saved {files}").format(files=FILE),
        flagged=guard.check(base.rows, edits, key=key, units=units, names=names),
    )


def _given_held(key: str, base: save.Base) -> bool:
    """Whether the grid of the gifts holds edits."""
    return gridstate.touched(gridstate.grid_state(f"{key}-{base.nonce}", len(base.rows)))


def page(data_dir: Path) -> None:
    st.title(_("Assumptions"))
    st.caption(_(INTRO))
    fold(_(READING))
    refs = references.of(data_dir)
    here = Here(data_dir, options(refs), refs, mode.view(data_dir))
    tabs = {tab: tab.form(view=here.view) for tab in TABS}
    drawn = [tab for tab, form in tabs.items() if form.fields]
    for box, tab in zip(st.tabs([_(t.title) for t in drawn]), drawn, strict=True):
        with box:
            _tab(here, tab, tabs[tab])
    # a tab without a field to show, by what it hides
    left = (tab.hidden(form, here.view) for tab, form in tabs.items() if tab not in drawn)
    here.view.note({item: words for hidden in left for item, words in hidden.items()})
