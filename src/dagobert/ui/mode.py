"""Simple and advanced mode, and the features: which pages, kinds, event types, fields, columns
and Explorer groups the app shows (`shown`). The mode is a habit of the viewer (`advanced`, its
switch and cookie), a feature a fact of the plan (`features_off` of `app.yaml`), and what the
inputs use (`Uses`) always shows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum, StrEnum, auto
from functools import cache
from typing import TYPE_CHECKING, NamedTuple

import streamlit as st
from babel.lists import format_list

from dagobert import actuals, history, i18n, series
from dagobert.i18n import N_, NP_, _, ngettext, pgettext
from dagobert.loader import APP
from dagobert.model.assumptions import Assumptions
from dagobert.model.plan import Feature
from dagobert.problems import InputError
from dagobert.references import read
from dagobert.scenariofiles import raw_scenarios, scenario_file
from dagobert.ui import SHORT_NOTE, chose, data_stamp, is_mobile, literal, note, page_link, remember
from dagobert.ui.fields import ABSENT, dicts, of
from dagobert.ui.sliders import (
    ALL_SPENDING,
    BY_CATEGORY,
    CARE,
    EVENTS,
    GOLD_CRYPTO,
    MARKETS,
    SALARY,
    SAVINGS,
)

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
    from pathlib import Path

    from dagobert.model.base import KeyPath

MODE = "ui-mode"  # session state, the key of the switch: `simple` or `advanced`
MODE_CHOSEN = "ui-mode-chosen"  # session state: the viewer chose the mode on the switch
MODE_COOKIE = "dagobert-mode"  # the mode that the viewer chose last, for the next visit
MODES = {"simple": N_("Simple"), "advanced": N_("Advanced")}
DEFAULT = "simple"  # the mode of a viewer without a choice: a new browser (owner, 2026-10-16)
MODE_HELP = N_(
    "Simple hides the expert settings that your plan does not use, Advanced shows them all. Each "
    "browser keeps its choice. The Features page switches off parts of life for every device."
)
ASSUMPTIONS = "assumptions.yaml"
FEATURES_OFF = "features_off"  # the key of `app.yaml`
ITEM_OVERRIDES = ("shift", "events", "assets")  # overrides of items by id, no key path
SELLABLE = ("property", "gold", "crypto")  # the kinds that a `sell` takes: it shows with one
# the stream columns that a kind brings into view as if a row used them: a salary may get a bonus,
# a row with `of` and `share`, which a first-timer could not add while they hid
BRINGS = {"salary": ("of", "share")}
PLACES_SHOWN = 3  # the places in use that the Features page names per feature


class Sort(StrEnum):
    """What an item is: its key names it within its sort."""

    PAGE = "page"  # by its English title
    KIND = "kind"  # of an asset
    STREAM = "stream"  # the kind of a stream
    EVENT = "event"  # the type of an event
    PATH = "path"  # a key path of the assumptions, `*` for any entry of a mapping
    COLUMN = "column"  # of a grid: the table (`assets`, `streams`) and the column
    OPTION = "option"  # of a select column: the table, the column and the option
    GROUP = "group"  # of the Explorer sidebar, by id (`sliders.GROUPS`)
    DATA = "data"  # what the records hold: `records`, `actuals`, `trades`, `series`


class Item(NamedTuple):
    sort: Sort
    key: tuple[str, ...]


def _items(sort: Sort, *names: str) -> frozenset[Item]:
    """Items by their dotted names: `tax.harvest`, `streams.hebesatz`."""
    return frozenset(Item(sort, tuple(name.split("."))) for name in names)


PAGES = (
    "Overview",
    "Snapshot",
    "Assets",
    "Cashflows",
    "Spend",
    "Explorer",
    "Flows",
    "Features",
    "Data",
    "Assumptions",
    "Scenarios",
    "Export and import",
)
# Shown in simple mode too: the core. A path or a column is core unless `EXPERT` lists it, so a
# new field shows until a line hides it.
CORE = (
    _items(Sort.PAGE, *(p for p in PAGES if p not in ("Snapshot", "Spend", "Data")))
    | _items(Sort.KIND, "cash", "fixed_income", "equity", "bav")
    | _items(Sort.STREAM, "expense", "salary", "pension", "other_income", "savings")
    | _items(Sort.EVENT, "lump_sum", "end_streams", "set_stream", "add_stream")
    | _items(Sort.GROUP, ALL_SPENDING, BY_CATEGORY, SALARY, SAVINGS, EVENTS, MARKETS)
)
EXPERT = _items(
    Sort.PATH,
    "person.horizon_age",
    "person.kvdr",
    "person.children",
    "person.children_born",
    "person.relatives",
    "inflation.stdev",
    "indices",
    "returns.*.stdev",
    "returns.*.equity_correlation",
    "refinance_rate",
    "pension_growth",
    "scale.growth",
    "cash_buffer_months",
    "invest_rest",
    "seed",
    "allocation",
    "spending",
    "care",
    "disability",
    "tax.year",
    "tax.sparer_pauschbetrag",
    "tax.teilfreistellung",
    "tax.harvest",
    "tax.gkv_from",
    "tax.kv_zusatz",
    "tax.crypto_capital_from",
    "tax.loss_carryforward",
    "tax.loss_carryback",
    "tax.capital_losses",
    "tax.alleinerziehend",
    "tax.self_employed",
) | _items(
    Sort.COLUMN,
    *(
        f"assets.{c}"
        for c in (
            "update_every",
            "tags",
            "growth",
            "cost",
            "guarantee",
            "fuenftel",
            "salary",
            "paid",
            "fixed_until",
            "prepayment_penalty",
            "finances",
            "basisrente",
            "premium",
            "bought",  # the AfA of a let property
            "building_share",
            "afa",
        )
    ),
    *(
        f"streams.{c}"
        for c in (
            "index",
            "tags",
            "after_sale_of",
            "repays",
            "property",
            "deduct",
            "deductible",
            "health",
            "taxable",
            "of",
            "share",
            "hebesatz",
            "gruendungszuschuss",
            "gz_extension",
            "sperrzeit",
            "training",
        )
    ),
)


@dataclass(frozen=True)
class Spec:
    """A feature: its toggle (`label`, `help`: what it hides), its name inside a sentence
    (`inline`, in the context `inline`) and the items that it hides."""

    label: str
    inline: str
    help: str
    hides: frozenset[Item]


FEATURES = {
    Feature.TRACKING: Spec(
        N_("Records: the Snapshot and Spend pages, trades and prices"),
        NP_("inline", "records"),
        N_(
            "Off hides the Snapshot and Spend pages, the trades and prices of the securities, the "
            "column `update_every` and what the Overview says about your records."
        ),
        _items(Sort.PAGE, "Snapshot", "Spend")
        | _items(Sort.DATA, "records", "actuals", "trades")
        | _items(Sort.COLUMN, "assets.update_every"),
    ),
    Feature.GOLD_CRYPTO: Spec(
        N_("Gold and crypto"),
        NP_("inline", "gold and crypto"),
        N_(
            "Off hides the asset kinds gold and crypto, the event `buy`, their sliders in the "
            "Explorer and the option `crypto_capital_from`."
        ),
        _items(Sort.KIND, "gold", "crypto")
        | _items(Sort.EVENT, "buy")
        | _items(Sort.GROUP, GOLD_CRYPTO)
        | _items(Sort.PATH, "tax.crypto_capital_from"),
    ),
    Feature.PROPERTY: Spec(
        N_("Property, rental and loans"),
        NP_("inline", "property, rental and loans"),
        N_(
            "Off hides the asset kinds property and loan, the events `buy_property` and `repay`, "
            "the stream columns `property`, `after_sale_of` and `repays` and the refinance rate."
        ),
        _items(Sort.KIND, "property", "loan")
        | _items(Sort.EVENT, "buy_property", "repay")
        | _items(Sort.COLUMN, "streams.property", "streams.after_sale_of", "streams.repays")
        | _items(Sort.PATH, "refinance_rate"),
    ),
    Feature.SELF_EMPLOYMENT: Spec(
        N_("Self-employment"),
        NP_("inline", "self-employment"),
        N_(
            "Off hides the stream kind of a self-employed profit, the columns `hebesatz`, "
            "`gruendungszuschuss` and `gz_extension` and the tax options of self-employment."
        ),
        _items(Sort.STREAM, "self_employed")
        | _items(
            Sort.COLUMN, "streams.hebesatz", "streams.gruendungszuschuss", "streams.gz_extension"
        )
        | _items(Sort.PATH, "tax.self_employed"),
    ),
    Feature.CHILDREN: Spec(
        N_("Children"),
        NP_("inline", "children"),
        N_(
            "Off hides your children, the option `alleinerziehend` and childcare as a deduction "
            "of an expense."
        ),
        _items(Sort.PATH, "person.children", "person.children_born", "tax.alleinerziehend")
        | _items(Sort.OPTION, "streams.deduct.childcare"),
    ),
    Feature.ESTATES: Spec(
        N_("Inheritance and gifts"),
        NP_("inline", "inheritance and gifts"),
        N_(
            "Off hides your relatives with the gifts from them before the start, and the events "
            "`inheritance` and `gift`."
        ),
        _items(Sort.PATH, "person.relatives") | _items(Sort.EVENT, "inheritance", "gift"),
    ),
    Feature.JOB_LOSS: Spec(
        N_("Job loss: ALG1 and severance"),
        NP_("inline", "job loss"),
        N_(
            "Off hides the stream kind ALG1 with its columns `sperrzeit` and `training`, and the "
            "event `severance`."
        ),
        _items(Sort.STREAM, "alg1")
        | _items(Sort.COLUMN, "streams.sperrzeit", "streams.training")
        | _items(Sort.EVENT, "severance"),
    ),
    Feature.DISABILITY: Spec(
        N_("Disability (BU)"),
        NP_("inline", "disability"),
        N_("Off hides the risk of disability (`disability`) and the stream kind of a BU policy."),
        _items(Sort.PATH, "disability") | _items(Sort.STREAM, "bu"),
    ),
    Feature.DEDUCTIONS: Spec(
        N_("Deductions and Basisrente"),
        NP_("inline", "deductions and Basisrente"),
        N_(
            "Off hides the Werbungskosten, the column `deduct` of an expense, the Basisrente of "
            "a policy (`basisrente`, `premium`) and the event `fund_policy`."
        ),
        # not `deductible`: the share of a PKV premium that the tax takes, which no switch hides
        _items(Sort.PATH, "tax.werbungskosten")
        | _items(Sort.COLUMN, "streams.deduct", "assets.basisrente", "assets.premium")
        | _items(Sort.EVENT, "fund_policy"),
    ),
    Feature.SPENDING_RULES: Spec(
        N_("Spending rules beyond the cut"),
        NP_("inline", "spending rules beyond the cut"),
        N_(
            "Off hides the increase of the spending rule, its ceiling, the spending by age and "
            "VPW (`increase`, `ceiling`, `age_curve`, `age_categories`, `vpw`). The cut stays."
        ),
        _items(
            Sort.PATH,
            "spending.increase",
            "spending.ceiling",
            "spending.age_curve",
            "spending.age_categories",
            "spending.vpw",
        ),
    ),
    Feature.CARE: Spec(
        N_("Long-term care"),
        NP_("inline", "long-term care"),
        N_("Off hides the risk of long-term care (`care`) and its sliders in the Explorer."),
        _items(Sort.PATH, "care") | _items(Sort.GROUP, CARE),
    ),
    Feature.ALLOCATION: Spec(
        N_("Allocation and glide path"),
        NP_("inline", "allocation and glide path"),
        N_(
            "Off hides the allocation and its glide path (`allocation`) and their sliders in the "
            "Explorer. `Invest the rest` stays."
        ),
        _items(Sort.PATH, "allocation"),
    ),
}


def _under(path: KeyPath, head: KeyPath) -> bool:
    """Whether `path` is `head` or lies below it; `*` in either matches any key."""
    pairs = zip(head, path, strict=False)
    return len(path) >= len(head) and all(h in (p, "*") or p == "*" for h, p in pairs)


@cache
def feature(item: Item) -> Feature | None:
    """The feature that hides `item`, a path also below the path of a feature; none for an item
    of no feature, which counts as on."""

    def hides(spec: Spec) -> bool:
        if item.sort is Sort.PATH:
            return any(h.sort is Sort.PATH and _under(item.key, h.key) for h in spec.hides)
        return item in spec.hides

    return next((f for f, spec in FEATURES.items() if hides(spec)), None)


@cache
def head(path: KeyPath) -> Item:
    """The item by which a field of a form shows: its key path up to the deepest path of `EXPERT`
    or of a feature above it (`care` of `care.duration.mean`, `spending.vpw` of its fields), so a
    section or a nested model that the inputs use shows whole."""
    listed = (
        i.key
        for i in (*EXPERT, *(h for spec in FEATURES.values() for h in spec.hides))
        if i.sort is Sort.PATH and _under(path, i.key)
    )
    return Item(Sort.PATH, max(listed, key=len, default=path))


def core(item: Item) -> bool:
    """Whether simple mode shows `item`: a page, kind, event type or group of `CORE`, a path or
    a column that `EXPERT` leaves out, any option and no record."""
    match item.sort:
        case Sort.PATH:
            return not any(e.sort is Sort.PATH and _under(item.key, e.key) for e in EXPERT)
        case Sort.COLUMN:
            return item not in EXPERT
        case Sort.OPTION:
            return True
    return item in CORE


def option(grid: str, column: str, value: str) -> Item:
    """The item of an option of a select column of the grid `grid`: the `kind` of a stream is a
    stream kind, any other option an `OPTION`."""
    if (grid, column) == ("streams", "kind"):
        return Item(Sort.STREAM, (value,))
    return Item(Sort.OPTION, (grid, column, value))


class Source(NamedTuple):
    """Where the inputs use a feature, as ids (a cached value holds no words, rule `i18n`): the
    file, the row and why (`coins (gold)`, `buy 2027-03`, a key path) or the rows of a CSV."""

    file: str
    what: str = ""
    rows: int = 0

    def said(self) -> str:
        if self.rows:
            return ngettext("{file}: {n} row", "{file}: {n} rows", self.rows).format(
                file=f"`{self.file}`", n=self.rows
            )
        return f"`{self.file}`: {literal(self.what)}" if self.what else f"`{self.file}`"

    def within(self, other: Source) -> bool:
        """The same place as `other`, or a key below its key path in the same file."""
        return self == other or (
            self.file == other.file and bool(other.what) and self.what.startswith(f"{other.what}.")
        )


Use = tuple[Item, Source]  # an item that the inputs use, and where


@dataclass(frozen=True)
class Uses:
    """What the inputs use, from the raw files (a file that does not load still counts): the
    items (a key path with every path above it), the first places of each feature in use
    (`where`), the scenarios with overrides or drops. `everything` for inputs that do not parse:
    every item counts as used, so the error screen comes with every page."""

    items: frozenset[Item] = frozenset()
    where: Mapping[Feature, tuple[Source, ...]] = field(default_factory=dict)
    overridden: frozenset[str] = frozenset()
    everything: bool = False

    def __contains__(self, item: object) -> bool:
        """Whether the inputs use `item`; a path with `*` when any entry there holds it."""
        if self.everything or item in self.items:
            return True
        return (
            isinstance(item, Item)
            and item.sort is Sort.PATH
            and "*" in item.key
            and any(
                u.sort is Sort.PATH and len(u.key) == len(item.key) and _under(u.key, item.key)
                for u in self.items
            )
        )

    def used(self, feature: Feature) -> bool:
        """Whether the inputs use an item of `feature`: its switch stays on."""
        return self.everything or bool(self.where.get(feature))

    def overrides(self, stem: str) -> bool:
        """Whether the scenario `stem` holds `overrides` or `drop`."""
        return self.everything or stem in self.overridden


ALL = Uses(everything=True)


def shown(item: Item, uses: Uses, off: Collection[Feature], advanced: bool) -> bool:
    """The one predicate: what the inputs use shows, else an item whose feature is on, in advanced
    mode or in the core."""
    return item in uses or (feature(item) not in off and (advanced or core(item)))


def pages(uses: Uses, off: Collection[Feature], advanced: bool) -> frozenset[str]:
    """The titles of the pages that the navigation registers."""
    return frozenset(t for t in PAGES if shown(Item(Sort.PAGE, (t,)), uses, off, advanced))


class Held(Enum):
    """What the items of a note stand at: fields `DEFAULTS`, in an override `INHERITED` from the
    files a scenario extends, an Explorer slider at `VALUES` of the files; `KINDS` and types
    hold no value."""

    DEFAULTS = auto()
    INHERITED = auto()
    VALUES = auto()
    KINDS = auto()


@dataclass(frozen=True)
class View:
    """What a page shows (`view`): what the inputs use, the features off and the mode."""

    uses: Uses
    off: frozenset[Feature]
    advanced: bool

    def shows(self, item: Item) -> bool:
        return shown(item, self.uses, self.off, self.advanced)

    def note(self, hidden: Mapping[Item, str], *, held: Held = Held.DEFAULTS) -> None:
        """The note of a page (`hidden_note`) on the items `hidden`, each with its words: those
        of a feature off name it, the others simple mode hides."""
        hidden_note(
            [words for item, words in hidden.items() if feature(item) not in self.off],
            self.off.intersection(map(feature, hidden)),
            held=held,
        )


EVERYTHING = View(Uses(), frozenset(), advanced=True)  # a grid of a page that hides nothing


def _paths(mapping: Mapping[str, object], above: KeyPath = ()) -> Iterator[tuple[KeyPath, object]]:
    """Every key path of a nested mapping with its value, the paths above a key too; a list is a
    leaf."""
    for key, value in mapping.items():
        path = (*above, str(key))
        yield path, value
        if isinstance(value, dict):
            yield from _paths(value, path)


@cache
def _defaults() -> dict[KeyPath, object]:
    """The default of each field of `assumptions.yaml` by its key path, `ABSENT` for none."""
    return {f.path: f.default for f in of(Assumptions)}


OPTIONS = {i.key[:2] for spec in FEATURES.values() for i in spec.hides if i.sort is Sort.OPTION}


def _cells(file: str, table: str, name: object, row: dict[str, object]) -> Iterator[Use]:
    for key, value in row.items():
        yield Item(Sort.COLUMN, (table, key)), Source(file, f"{name} ({key})")
        if (table, key) in OPTIONS and isinstance(value, str):
            yield Item(Sort.OPTION, (table, key, value)), Source(file, f"{name} ({key}: {value})")


def _stream(file: str, row: dict[str, object]) -> Iterator[Use]:
    kind, name = row.get("kind", "expense"), row.get("name")
    where = Source(file, f"{name} ({kind})")
    yield Item(Sort.STREAM, (str(kind),)), where
    yield from ((Item(Sort.COLUMN, ("streams", c)), where) for c in BRINGS.get(str(kind), ()))
    yield from _cells(file, "streams", name, row)


def _event(file: str, row: dict[str, object]) -> Iterator[Use]:
    kind, at = str(row.get("type")), row.get("at")
    where = Source(file, f"{kind} {at:%Y-%m}" if isinstance(at, date) else kind)
    yield Item(Sort.EVENT, (kind,)), where
    if kind == "buy_property":
        yield from ((Item(Sort.KIND, (k,)), where) for k in ("property", "loan"))
    if kind == "add_stream" and isinstance(stream := row.get("stream"), dict):
        yield from _stream(file, stream)


def _count(path: Path) -> int:
    """The data rows of a CSV file below its header, counted in bytes: a file that does not
    decode counts too, and its page names the problem."""
    if not path.is_file():
        return 0
    return max(0, sum(1 for line in path.read_bytes().splitlines() if line.strip()) - 1)


def _keys(
    mapping: Mapping[str, object],
    file: str,
    *above: str,
    defaults: Mapping[KeyPath, object] | None = None,
) -> Iterator[Use]:
    """The key paths of `mapping` in `file`, named below the keys `above` there, but a value at
    the default of its field (`defaults`: `children: 0`, `relatives: {}`), which holds nothing
    that acts."""
    for path, value in _paths(mapping):
        if defaults is None or defaults.get(path, ABSENT) != value:
            yield Item(Sort.PATH, path), Source(file, ".".join((*above, *path)))


def _asset(row: dict[str, object]) -> Iterator[Use]:
    kind, name = str(row.get("kind")), row.get("id")
    yield Item(Sort.KIND, (kind,)), Source("assets.yaml", f"{name} ({kind})")
    if kind in SELLABLE:
        yield Item(Sort.EVENT, ("sell",)), Source("assets.yaml", f"{name} ({kind})")
    yield from _cells("assets.yaml", "assets", name, row)
    if row.get("trades"):
        yield from _recorded("trades", Source("assets.yaml", f"{name} (trades)"))


def _scenario(file: str, doc: Mapping[str, object]) -> Iterator[Use]:
    """The key paths that its overrides set (not those of items by id) and its events."""
    if isinstance(overrides := doc.get("overrides"), dict):
        plain = {str(k): v for k, v in overrides.items() if k not in ITEM_OVERRIDES}
        yield from _keys(plain, file, "overrides")
    for row in dicts(doc.get("events")):
        yield from _event(file, row)


# the page of what the records hold
RECORDED = {"records": "Snapshot", "trades": "Snapshot", "actuals": "Spend", "series": "Data"}


def _recorded(data: str, where: Source) -> Iterator[Use]:
    """What the records hold, and their page."""
    yield Item(Sort.DATA, (data,)), where
    yield Item(Sort.PAGE, (RECORDED[data],)), where


def _records(data_dir: Path) -> Iterator[Use]:
    """The rows of the history and the actuals, the price files and the fetched series."""
    for name, data in ((history.FILE, "records"), (actuals.FILE, "actuals")):
        if rows := _count(data_dir / name):
            yield from _recorded(data, Source(name, rows=rows))
    for folder, data in (("prices", "trades"), (series.FETCHED, "series")):
        for csv in sorted((data_dir / folder).glob("*.csv")):
            yield from _recorded(data, Source(f"{folder}/{csv.name}"))


def _found(data_dir: Path, scenarios: Mapping[str, Mapping[str, object]]) -> Iterator[Use]:
    """Each item that the inputs use with its place."""
    yield from _keys(read(data_dir, ASSUMPTIONS), ASSUMPTIONS, defaults=_defaults())
    for row in dicts(read(data_dir, "assets.yaml").get("assets")):
        yield from _asset(row)
    for row in dicts(read(data_dir, "cashflows.yaml").get("streams")):
        yield from _stream("cashflows.yaml", row)
    for stem, doc in scenarios.items():
        yield from _scenario(scenario_file(stem), doc)
    yield from _records(data_dir)


def _where(found: Iterable[Use]) -> dict[Feature, tuple[Source, ...]]:
    """The first `PLACES_SHOWN` places of each feature in use, a key below a listed one left out."""
    where: dict[Feature, list[Source]] = {}
    for item, source in found:
        if (f := feature(item)) is not None:
            listed = where.setdefault(f, [])
            if len(listed) < PLACES_SHOWN and not any(source.within(s) for s in listed):
                listed.append(source)
    return {f: tuple(sources) for f, sources in where.items()}


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


type Stamp = tuple[float, int, float, float, float]  # `ui.Stamp` and three mtimes


def stamp(data_dir: Path) -> Stamp:
    """The cache key of `uses`: `ui.data_stamp` and what it leaves out, the records, the actuals
    and the folders of the prices (a file added or removed)."""
    return (
        *data_stamp(data_dir),
        _mtime(data_dir / history.FILE),
        _mtime(data_dir / actuals.FILE),
        _mtime(data_dir / "prices"),
    )


@st.cache_data(max_entries=4, show_spinner=False)  # only the latest stamp is hit
def _uses(data_dir: Path, stamp: Stamp) -> Uses:
    del stamp
    try:
        scenarios = raw_scenarios(data_dir)
        found = list(_found(data_dir, scenarios))
    except InputError:
        return ALL
    overridden = (s for s, doc in scenarios.items() if doc.get("overrides") or doc.get("drop"))
    return Uses(frozenset(item for item, _place in found), _where(found), frozenset(overridden))


def uses(data_dir: Path) -> Uses:
    """What the inputs of `data_dir` use, once per state of its files (`stamp`)."""
    return _uses(data_dir, stamp(data_dir))


def listed(value: object) -> frozenset[Feature]:
    """The features of a raw `features_off`: the known ids of a list."""
    if not isinstance(value, list):
        return frozenset()
    return frozenset(Feature(v) for v in value if isinstance(v, str) and v in Feature)


def features_off(data_dir: Path) -> frozenset[Feature]:
    """The features that `app.yaml` switches off, from the raw file: an unknown id or a file that
    does not load switches nothing off, and the page that loads it names the problem."""
    try:
        return listed(read(data_dir, APP).get(FEATURES_OFF))
    except InputError:
        return frozenset()


def said(features: Iterable[Feature]) -> str:
    """`features` inside a sentence, in the order of `FEATURES`, set apart by semicolons as a name
    holds an `and`: `gold and crypto; long-term care`."""
    return "; ".join(
        pgettext("inline", s.inline) for f, s in FEATURES.items() if f in set(features)
    )


def advanced() -> bool:
    """Whether the viewer sees everything: `?mode=simple|advanced` (tests and links; taken once,
    so the switch can change it), the switch (`mode_switch`), the cookie of an earlier choice,
    else `DEFAULT`: a new browser starts simple."""
    chosen = next(
        (
            mode
            for mode in (
                st.query_params.pop("mode", ""),
                st.session_state.get(MODE),
                st.context.cookies.get(MODE_COOKIE),
            )
            if mode in MODES
        ),
        DEFAULT,
    )
    st.session_state[MODE] = chosen
    return chosen == "advanced"


def view(data_dir: Path) -> View:
    """What a page on `data_dir` shows: what its inputs use, the features off, the mode."""
    return View(uses(data_dir), features_off(data_dir), advanced())


def mode_switch() -> None:
    """The mode switch at the end of the sidebar, above the language switch. A choice carries the
    grid edits and persists in a cookie (`ui.chose`, `ui.remember`)."""
    st.sidebar.segmented_control(
        f":material/tune: {_('Mode')}",
        list(MODES),
        format_func=lambda mode: _(MODES[mode]),
        key=MODE,
        required=True,
        on_change=chose,
        args=(MODE_CHOSEN,),
        help=_(MODE_HELP),
    )
    remember(MODE_COOKIE, MODE_CHOSEN, st.session_state[MODE])


MENU = N_("Switch to Advanced in the menu to change them.")
SIDEBAR = N_("Switch to Advanced in the sidebar to change them.")
# the sentences of a note on the items that simple mode hides, each on a phone (in the menu) and
# on a desktop (in the sidebar)
HIDDEN = {
    Held.DEFAULTS: (N_("Hidden in simple mode (at their defaults): {names}."), MENU, SIDEBAR),
    Held.INHERITED: (
        N_("Hidden in simple mode (inherited from the files it extends): {names}."),
        MENU,
        SIDEBAR,
    ),
    Held.VALUES: (
        N_("Hidden in simple mode (at the values as saved): {names}."),
        MENU,
        SIDEBAR,
    ),
    Held.KINDS: (
        N_("Hidden in simple mode: {names}."),
        N_("Switch to Advanced in the menu to use them."),
        N_("Switch to Advanced in the sidebar to use them."),
    ),
}
HIDDEN_LABEL = N_("Hidden in simple mode")  # the fold of a long note on a phone


def hidden_text(
    expert: Sequence[str], off: Collection[Feature], *, phone: bool, held: Held = Held.DEFAULTS
) -> str:
    """The note of a page that hides something: the `expert` items in words that simple mode
    hides (`held` says what they stand at), then the features `off` whose items the page would
    show; empty when it hides nothing."""
    sentences = []
    if expert:
        names = format_list(list(expert), locale=i18n.language())
        hidden, menu, sidebar = HIDDEN[held]
        sentences += [_(hidden).format(names=names), _(menu if phone else sidebar)]
    if off:
        text = _("Off in Features: {names}. Turn them on there to use them.")
        sentences.append(text.format(names=said(off)))
    return " ".join(sentences)


def hidden_note(
    expert: Sequence[str], off: Collection[Feature], *, held: Held = Held.DEFAULTS
) -> None:
    """`hidden_text` as a caption, folded on a phone when long (`ui.note`, labelled
    `HIDDEN_LABEL`), and a link to the Features page while it names a feature."""
    text = hidden_text(expert, off, phone=is_mobile(), held=held)
    if len(text) > SHORT_NOTE:
        note(text, _(HIDDEN_LABEL))
    elif text:
        st.caption(text)
    if off:
        page_link("Features", _("Features"))


def off_note(data_dir: Path) -> None:
    """The caption of the Overview while `app.yaml` switches off features that the plan does not
    use, their count with a link to the Features page, which names them: a newcomer whose plan
    began with them off finds it."""
    found = uses(data_dir)
    if n := len([f for f in features_off(data_dir) if not found.used(f)]):
        st.caption(
            ngettext(
                "{n} part of the app is switched off: the Features page turns it on.",
                "{n} parts of the app are switched off: the Features page turns them on.",
                n,
            ).format(n=n)
        )
        page_link("Features", _("Features"))
