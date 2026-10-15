"""The catalog of the explorer's sliders and switches: each number or yes or no of the inputs
that it moves, with its range, steps and help, by sidebar group (`knobs`, `switches`). The catalog
is built in each run, in the language of the page."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from pydantic import BaseModel

from dagobert import goalseek, tax
from dagobert.i18n import N_, _, pgettext
from dagobert.model.assets import Asset, AvDepot, CryptoAsset, LotAsset
from dagobert.model.assumptions import Assumptions, Distribution, ReturnClass, Vpw
from dagobert.model.base import description, named
from dagobert.model.events import AddStreamEvent, BuyPropertyEvent, Event, PhaseChange
from dagobert.model.months import months_between
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.money import format_eur
from dagobert.report.charts import class_name
from dagobert.returns import historical_draws, historical_replays, median_growth
from dagobert.runner import ModelName
from dagobert.ui.gridcolumns import keyword
from dagobert.ui.sliders import (
    AGE,
    ALL_SPENDING,
    ALLOCATION,
    AMOUNT,
    ASSETS,
    BY_CATEGORY,
    CARE,
    CORRELATION,
    CRYPTO_RATE,
    CRYPTO_SPREAD,
    EUR,
    EVENTS,
    FACTOR,
    GOLD_CRYPTO,
    LEVEL,
    MARKETS,
    MODELS,
    MONTHS,
    PER_YEAR,
    PERIOD,
    RATE,
    SALARY,
    SAVINGS,
    SHARE,
    SHIFT,
    SPENDING,
    SPREAD,
    SPREADS,
    TAXES,
    TREND,
    Knob,
    Switch,
)

SALARY_STEP = 500.0
SAVINGS_STEP = 50.0
AMOUNT_FIELDS = ("gross", "price")  # event fields with a slider
LEAST = N_(  # the help of the price of a purchase with a loan
    "It starts at the lowest price for the loan: the loan may not be more than the price with "
    "the transfer tax and the costs."
)

STANDING = frozenset({"equity", "fixed_income"})  # the classes that every plan invests in
DRAWN: tuple[ModelName, ...] = ("montecarlo",)  # the models that draw from a spread
UNREPLAYED: tuple[ModelName, ...] = ("fixed", "montecarlo")  # `historical` replays a series
CARED: tuple[ModelName, ...] = ("montecarlo", "historical")  # `fixed` draws no care episodes
NOT_HISTORICAL = N_("Historical replays the series instead.")
# the help of the return of a class, sentences of the catalogue
RETURN_HELP = {
    "equity": (
        N_(
            "Nominal return of the depot per year. Every surplus goes here, less the fixed-income "
            "share of the allocation, and deficits sell from it."
        ),
        NOT_HISTORICAL,
    ),
    "fixed_income": (
        N_(
            "Nominal return of the fixed-income bucket per year (Tagesgeld, Festgeld ladder, bond "
            "funds). The interest is taxed each December."
        ),
        NOT_HISTORICAL,
    ),
    "property": (
        N_(
            "Nominal growth of the property values per year. It sets the price of a sale without "
            "a `price` and the upkeep."
        ),
    ),
    "cash": (
        N_(
            "Nominal return on cash per year, taxed each December. While `Invest the rest` is on, "
            "cash is near zero once deficits start, so the effect is small. Off, the cash above "
            "the buffer stays and earns it."
        ),
    ),
}
OTHER_RETURN = N_("Nominal return per year of the assets with `growth: {name}`.")
SAVINGS_RATE = N_(
    "While `Invest the rest` is on, the rate changes the chance to run out of money by {age} "
    "little: the cash above the buffer goes into the portfolio anyway. The goal seek assumes that "
    "this chance crosses the target once between the ends of the slider, and more equity can "
    "raise it as well as lower it."
)
INVEST_REST_HELP = N_(
    "On (the default): each month the cash above the buffer goes into the portfolio. Off: it "
    "stays in cash and earns the cash return, and only the savings plans and the `invest` of a "
    "sale invest. No lever of the sensitivity, no goal seek."
)
NO_LEVER = N_("No lever of the sensitivity, no goal seek.")
VPW_SHARE = N_(  # the help of a flexible category under VPW
    "In a month without pay VPW sets how much the flexible categories spend: this factor sets "
    "their split and the plan that the months of raises compare with. In a month with pay it "
    "sets the level."
)
FLEXIBLE = N_("The flexible categories: {categories}.")
# The model refuses a ceiling at or below the trigger while the increase is on: then the two
# sliders keep apart, the trigger below the reference wealth, the ceiling from it up. A file value
# widens a range, so they can meet (a ceiling of 0), and so can an increase that a slider turns on:
# the explorer then names the problem instead of the results.
CEILING = replace(LEVEL, low=100.0, high=300.0)
TRIGGER = replace(LEVEL, high=CEILING.low - LEVEL.step)
CONSERVATIVE = N_(
    "Set it conservatively: Bitcoin fell by 75% or more four times since 2011 (a spread of 60% "
    "to 90% gives that), and a mean of 15% with a spread of 80% loses money on the median path."
)


def said(*texts: str, **fields: object) -> str:
    """Sentences of the catalogue in the language of the page, one after the other, with
    `fields`; an empty text is none."""
    return " ".join(_(text).format(**fields) for text in texts if text)


def _about(
    path: tuple[str, ...], *more: str, of: type[BaseModel] = Assumptions, **fields: object
) -> str:
    """The help of a slider: the description of its field (`model.base.description`, which the
    Assumptions page shows too), then the sentences `more` that the slider adds."""
    return f"{_(description(of, path))}. {said(*more, **fields)}".rstrip()


def _held(assets: list[Asset]) -> dict[str, bool]:
    """The return classes of the gold and crypto assets but equity, true for one of crypto."""
    held: dict[str, bool] = {}
    for x in assets:
        if isinstance(x, LotAsset) and x.growth != "equity":
            held.setdefault(x.growth, isinstance(x, CryptoAsset))
    return held


def classes(assets: Sequence[Asset], scenario: Scenario | None = None) -> frozenset[str]:
    """The return classes that the plan holds: `STANDING`, the `growth` of an asset or of a
    purchase of `scenario`, and `cash` with a cash asset. Simple mode shows the sliders of these
    classes only."""
    events = scenario.events if scenario else []
    bought = [e.property.growth for e in events if isinstance(e, BuyPropertyEvent)]
    grown = [getattr(x, "growth", "cash" if x.kind == "cash" else None) for x in assets]
    return STANDING | {c for c in [*grown, *bought] if c}


def _holding_knobs(name: str, d: ReturnClass, *, crypto: bool) -> list[Knob]:
    """Mean, spread and correlation of the class of a gold or crypto asset, in a group of their
    own: rarely the first lever. A wide spread pulls the median path far below the mean, so the
    help gives its growth at the file values."""
    label = class_name(name)
    drawn = name in historical_draws([name])
    models: tuple[ModelName, ...] = (*DRAWN, "historical") if drawn else DRAWN
    read = N_("Monte Carlo and Historical read it.") if drawn else N_("Only Monte Carlo reads it.")
    median = N_(
        "A spread pulls the growth of the median path below the mean: g = (1 + mean) / "
        "√(1 + spread² / (1 + mean)²) − 1, {growth} a year at a mean of {mean} and a spread of "
        "{spread} in the scenario."
    )
    growth = {
        "growth": f"{median_growth(d):.1%}",
        "mean": f"{d.mean:.1%}",
        "spread": f"{d.stdev:.1%}",
        "name": name,
    }
    historical = (
        N_("Historical draws it as Monte Carlo does, tied to the replayed equity month.")
        if drawn
        else NOT_HISTORICAL
    )
    return [
        Knob(
            GOLD_CRYPTO,
            _("{name} return").format(name=label),
            ("returns", name, "mean"),
            d.mean,
            CRYPTO_RATE if crypto else RATE,
            said(
                N_(
                    "Nominal return per year of the coins with `growth: {name}`, before the "
                    "custody `cost`."
                )
                if crypto
                else N_(
                    "Nominal return per year of the gold with `growth: {name}`, before the custody "
                    "`cost`."
                ),
                CONSERVATIVE if crypto else "",
                median,
                N_("Fixed compounds the mean, so its path runs above the median one."),
                historical,
                **growth,
            ),
            models=MODELS if drawn else UNREPLAYED,
        ),
        Knob(
            GOLD_CRYPTO,
            _("{name} spread").format(name=label),
            ("returns", name, "stdev"),
            d.stdev,
            CRYPTO_SPREAD if crypto else SPREAD,
            said(
                N_(
                    "Standard deviation of the return per year, drawn every month. It widens the "
                    "fan."
                ),
                median,
                read,
                **growth,
            ),
            models=models,
        ),
        Knob(
            GOLD_CRYPTO,
            _("{name} correlation").format(name=label),
            ("returns", name, "equity_correlation"),
            d.equity_correlation,
            CORRELATION,
            said(
                N_(
                    "Correlation of the monthly draw with the one of equity, from -1 to 1. 0 "
                    "assumes none, which understates the risk of a class that falls with shares. "
                    "Per month against the MSCI World: gold about 0, Bitcoin 0.3 to 0.5 since "
                    "2014, higher in a crash."
                ),
                N_(
                    "Monte Carlo and Historical read it, and in Historical the skewed equity "
                    "months lift the mean a little."
                )
                if drawn
                else read,
            ),
            models=models,
        ),
    ]


def _return_knob(name: str, d: ReturnClass, *, replayed: bool) -> Knob:
    """Off in `historical` when it replays the series of the class."""
    return Knob(
        MARKETS,
        _("{name} return").format(name=class_name(name)),
        ("returns", name, "mean"),
        d.mean,
        RATE,
        said(*RETURN_HELP.get(name, (OTHER_RETURN,)), name=name),
        models=UNREPLAYED if replayed else MODELS,
    )


def _market_knobs(a: Assumptions, held: Mapping[str, bool], costs: Sequence[Knob]) -> list[Knob]:
    """The classes of the gold and crypto assets sit in `GOLD_CRYPTO`; the indices that only costs
    follow (`_index_knobs`) stand beside the inflation."""
    first = {name: a.returns[name] for name in RETURN_HELP if name in a.returns}
    replays = historical_replays(held)
    returns = {
        name: _return_knob(name, d, replayed=name in replays)
        for name, d in (first | a.returns).items()
        if name not in held
    }
    equity = returns.pop("equity")
    return [
        Knob(
            MARKETS,
            _("Inflation"),
            ("inflation", "mean"),
            a.inflation.mean,
            RATE,
            _about(
                ("inflation",),
                N_(
                    "The slider sets the mean. Unless `Nominal euros` is on, the table and the "
                    "charts deflate each path by its own price level. A higher value lowers every "
                    "real return, the real pension and the real loan rates."
                ),
                NOT_HISTORICAL,
            ),
            models=UNREPLAYED,
        ),
        *costs,
        equity,
        Knob(
            MARKETS,
            _("{name} spread").format(name=class_name("equity")),
            ("returns", "equity", "stdev"),
            a.returns["equity"].stdev,
            SPREAD,
            _(
                "Standard deviation of the equity return per year. It widens the fan and raises "
                "the chance to run out of money: bad early years count most. Only Monte Carlo "
                "draws from it."
            ),
            models=DRAWN,
        ),
        *returns.values(),
        Knob(
            MARKETS,
            _("Loan rate after the fixed period"),
            ("refinance_rate",),
            a.refinance_rate,
            RATE,
            _about(("refinance_rate",)),
        ),
    ]


def _holdings(a: Assumptions, held: Mapping[str, bool]) -> list[Knob]:
    return [
        knob
        for name, d in a.returns.items()
        if name in held
        for knob in _holding_knobs(name, d, crypto=held[name])
    ]


def _spending_knobs(a: Assumptions, streams: list[Stream]) -> list[Knob]:
    """The plan itself, not the world: the `scale` factor on all spending, then one per category,
    the largest first."""
    spending: dict[str, list[Stream]] = {}
    for s in streams:
        if s.managed and s.amount:
            spending.setdefault(s.cat, []).append(s)
    per_month = {
        cat: -sum((s.amount or 0.0) / s.every for s in rows) for cat, rows in spending.items()
    }
    rule = a.spending
    flexible = set(rule.categories) if rule and rule.vpw else set()
    planned = sum(per_month[cat] * a.scale.categories.get(cat, 1.0) for cat in per_month)
    overall = [
        Knob(
            ALL_SPENDING,
            _("All spending"),
            ("scale", "spending"),
            a.scale.spending,
            FACTOR,
            _(
                "Factor on every expense stream of the categories below, about {amount} per month "
                "with their factors, before phase factors. The factors of the categories, the "
                "spending cut and the age curve apply on top."
            ).format(amount=format_eur(planned)),
        )
    ]
    return (overall if spending else []) + [
        Knob(
            BY_CATEGORY,
            named(cat) or _("No category"),
            ("scale", "categories", cat),
            a.scale.categories.get(cat, 1.0),
            FACTOR,
            said(
                N_(
                    "Factor on the expense streams of `{cat}`, about {amount} per month before "
                    "phase factors: {streams}. The spending cut and the age curve apply on top."
                ),
                VPW_SHARE if cat in flexible else "",
                cat=cat,
                amount=format_eur(per_month[cat]),
                streams=", ".join(dict.fromkeys(s.name for s in spending[cat])),
            ),
        )
        for cat in sorted(spending, key=lambda c: per_month[c], reverse=True)
    ]


@dataclass(frozen=True)
class Salaries:
    """Regular gross per month and phase of the scenario that the salary sliders show."""

    scenario: str = ""
    by_phase: Mapping[str, float] = field(default_factory=dict)


NO_SALARIES = Salaries()


def _salary_knobs(a: Assumptions, salaries: Salaries) -> list[Knob]:
    """A `scale` factor on the salary and the profit of each phase with one, in the order of
    `phases`, shown as the gross of a usual month."""
    return [
        Knob(
            SALARY,
            _("Salary and profit in {phase}").format(phase=label),
            ("scale", "salary", phase),
            a.scale.salary.get(phase, 1.0),
            replace(
                EUR,
                high=SALARY_STEP * math.ceil(2 * gross / SALARY_STEP),
                step=SALARY_STEP,
                delta=SALARY_STEP,
                # the gross at the factor 1: the run paid it with the factor of the scenario
                # (a factor 0 pays nothing, the run's gross is then the only one there is)
                scale=gross / (a.scale.salary.get(phase, 1.0) or 1.0),
            ),
            _(
                "Gross salary and profit of a business of a usual month in the phase "
                "`{phase}`, in euros of {month}: a stream that follows an index which grows "
                "faster than prices lies above its amount in the file in a later phase. "
                "{scenario} pays {amount}. The slider sets a factor on every salary payment "
                "and profit of the phase, so a bonus and the other scenarios change by the "
                "same share. Tax, SV, pension points and a later ALG1 follow the new gross."
            ).format(
                phase=label,
                month=f"{a.start:%Y-%m}",
                scenario=salaries.scenario,
                amount=format_eur(gross),
            ),
        )
        for phase, label in a.phase_labels.items()
        if (gross := salaries.by_phase.get(phase)) is not None
    ]


def _savings_knobs(a: Assumptions, streams: list[Stream]) -> list[Knob]:
    """A slider per savings plan in euros per month, like the salary: the rate of its first row,
    times the factor of `scale.savings`, which the slider sets. Its steps divide the rate, at most
    `SAVINGS_STEP`: a quarterly plan of 100 € saves 33 € a month, which steps of 50 € miss. Its
    help names the chance to run out by the age that the plan takes it at (`goalseek.broke_age`)."""
    rates: dict[str, float] = {}
    age = goalseek.broke_age(a)  # of the plan whose values the sliders start at
    for s in streams:
        if s.kind == StreamKind.SAVINGS and s.amount:
            rates.setdefault(s.name, -s.amount / s.every)
    return [
        Knob(
            SAVINGS,
            _("{plan} per month").format(plan=name),
            ("scale", "savings", name),
            a.scale.savings.get(name, 1.0),
            replace(
                EUR,
                high=step * math.ceil(max(2 * rate, 1000) / step),
                step=step,
                delta=2 * step,
                scale=rate,
            ),
            said(
                N_(
                    "The rate of the savings plan `{plan}` per month, {amount} in its file, in "
                    "the euros of its amount (nominal unless it names an index). The slider sets "
                    "a factor on every row of the plan. A month whose cash does not cover the "
                    "rate skips it."
                ),
                SAVINGS_RATE,
                plan=name,
                amount=format_eur(rate),
                age=age,
            ),
        )
        for name, rate in rates.items()
        for step in [rate / math.ceil(rate / SAVINGS_STEP)]
    ]


def _event_knobs(scenario: Scenario, a: Assumptions, work: Sequence[goalseek.Dial]) -> list[Knob]:
    """The items of the scenario with an `id`, in the order of their first date: one slider
    moves the dates of a group, one sets each amount of its events. The month of a group reaches
    the range of each dial of `work` (`goalseek.work` per chosen scenario) that moves it, so the
    goal seek can set it."""
    start, born = a.start, a.person.born
    groups: dict[str, list[PhaseChange | Event]] = {}
    for item in sorted(
        [*scenario.phases, *(e for e in scenario.events if e.at)], key=lambda x: x.at or start
    ):
        if item.id is not None:
            groups.setdefault(item.id, []).append(item)
    out: list[Knob] = []
    for group, items in groups.items():
        name = named(group)
        first = items[0].at or start
        dials = [d for d in work if d.weights[0][0] == ("shift", group)]
        low = min(
            [float(min(0, max(SHIFT.low, -months_between(start, first)))), *(d.low for d in dials)]
        )
        high = max([SHIFT.high, *(d.high for d in dials)])
        out.append(
            Knob(
                EVENTS,
                _("{id}: month").format(id=name),
                ("shift", group),
                0.0,
                replace(SHIFT, low=low, high=high),
                _("Moves every item with `id: {id}` by whole months: {items}.").format(
                    id=group, items="; ".join(map(_item, items))
                ),
                origin=first,
                born=born,
            )
        )
        for name_of in AMOUNT_FIELDS:
            values = [v for x in items if (v := getattr(x, name_of, None)) is not None]
            if values:
                low = _least(items) if name_of == "price" else 0.0
                out.append(
                    Knob(
                        EVENTS,
                        f"{name}: {keyword(name_of)}",
                        ("events", group, name_of),
                        values[0],
                        replace(
                            AMOUNT,
                            low=AMOUNT.step * math.ceil(low / AMOUNT.step),
                            high=AMOUNT.step * math.ceil(2 * values[0] / AMOUNT.step),
                        ),
                        said(
                            N_(
                                "`{field}` of the events with `id: {id}`, nominal at the event "
                                "date."
                            ),
                            LEAST if low else "",
                            field=name_of,
                            id=group,
                        ),
                    )
                )
    return out


def _least(items: list[PhaseChange | Event]) -> float:
    """The lowest price of the purchases among `items` that their loans allow (the model refuses
    a loan above the price with the Grunderwerbsteuer and the costs)."""
    return max(
        (
            -e.loan.balance / (e.cost / e.price)
            for e in items
            if isinstance(e, BuyPropertyEvent) and e.loan is not None
        ),
        default=0.0,
    )


def _asset_knobs(a: Assumptions, assets: list[Asset]) -> list[Knob]:
    ty = tax.for_year(a.tax_year)
    limit, zulage = ty.av_subsidized, float(tax.av_zulage(ty.av_subsidized, 0, ty))
    return [
        Knob(
            ASSETS,
            f"{depot.label}: {keyword('contribution')}",
            ("assets", depot.id, "contribution"),
            depot.contribution,
            PER_YEAR,
            _(
                "Own contribution per year with compulsory pension insurance, in start-year "
                "euros. Up to {limit} earns the Zulage ({zulage} at {limit}) and a "
                "Sonderausgabe, the payout is taxed as other income. 0 means no depot."
            ).format(limit=format_eur(limit), zulage=format_eur(zulage)),
        )
        for depot in assets
        if isinstance(depot, AvDepot)
    ]


def _item(item: PhaseChange | Event) -> str:
    """An item of an id in the help of its month slider: its type as the file writes it."""
    if isinstance(item, PhaseChange):
        return _("phase {phase} from {month}").format(phase=item.phase, month=f"{item.at:%Y-%m}")
    when = f"{item.at:%Y-%m}" if item.at else _("on a condition")
    return f"{item.type} {when}" + (f" ({item.note})" if item.note else "")


LISTED = 6  # stream names in the help of an index slider before `and n more`


INCOME = frozenset(
    {
        StreamKind.SALARY,
        StreamKind.ALG1,
        StreamKind.PENSION,
        StreamKind.OTHER_INCOME,
        StreamKind.SELF_EMPLOYED,
    }
)


def _followers(streams: Sequence[Stream], index: str) -> str:
    """The help sentence on the streams that follow `index` by their `index` field."""
    names = list(dict.fromkeys(s.name for s in streams if s.index == index))
    if not names:
        return said(N_("No stream of the plan follows it."))
    listed = ", ".join(names[:LISTED])
    if len(names) > LISTED:
        listed = _("{names} and {n} more").format(names=listed, n=len(names) - LISTED)
    return said(N_("Followed by: {streams}."), streams=listed)


def _income_only(a: Assumptions, streams: Sequence[Stream], index: str) -> bool:
    """Whether an index belongs to the income: some income stream follows it and no cost does
    (an expense, or the care cost). One that both or none follow is a price level: it stands
    beside the inflation."""
    kinds = {s.kind for s in streams if s.index == index}
    cost = bool(kinds - INCOME) or (a.care is not None and a.care.index == index)
    return bool(kinds & INCOME) and not cost


def _index_knobs(a: Assumptions, streams: Sequence[Stream]) -> list[Knob]:
    """A slider per index of the assumptions, in `SALARY` where only income follows it, else in
    `MARKETS`."""
    return [
        Knob(
            SALARY if _income_only(a, streams, name) else MARKETS,
            (_("{index} growth") if d.cumulative else _("{index} level")).format(index=named(name)),
            ("indices", name, "mean"),
            d.mean,
            RATE if d.cumulative else SHARE,
            (
                _(
                    "Mean nominal growth per year of the streams with `index: {index}`, "
                    "stepped each January. It replaces the inflation for them, so the gap to "
                    "the inflation is their real growth."
                )
                if d.cumulative
                else _(
                    "Mean level of the streams with `index: {index}` in a year, for example "
                    "the payout ratio of a bonus. It does not compound."
                )
            ).format(index=name)
            + f" {_followers(streams, name)}",
        )
        for name, d in a.indices.items()
    ]


def _pension_growth(a: Assumptions) -> Knob:
    return Knob(
        SALARY,
        _("Pension growth"),
        ("pension_growth",),
        a.pension_growth,
        RATE,
        _about(("pension_growth",)),
    )


def _rule_knobs(a: Assumptions) -> list[Knob]:
    out = [
        Knob(
            SPENDING,
            _("Cash buffer"),
            ("cash_buffer_months",),
            a.cash_buffer_months,
            MONTHS,
            _about(("cash_buffer_months",)),
        )
    ]
    if a.spending and a.spending.vpw:  # the model refuses the cut and the increase beside it
        cats = ", ".join(a.spending.categories)
        out += _vpw_knobs(a.spending.vpw, cats)
    elif a.spending:
        cats = ", ".join(a.spending.categories)
        out += [
            Knob(
                SPENDING,
                _("Cut in bad months"),
                ("spending", "cut"),
                a.spending.cut,
                SHARE,
                f"{_(description(Assumptions, ('spending', 'cut')))}: {cats}.",
            ),
            Knob(
                SPENDING,
                _("Cut when wealth falls below"),
                ("spending", "trigger"),
                a.spending.trigger,
                TRIGGER if a.spending.increase else LEVEL,  # an increase needs `no_pay`
                _about(("spending", "trigger")),
            ),
        ]
        if a.spending.base == "no_pay":  # the model refuses an increase without it
            out += [
                Knob(
                    SPENDING,
                    _("Increase in good months"),
                    ("spending", "increase"),
                    a.spending.increase,
                    SHARE,
                    _about(("spending", "increase"), FLEXIBLE, categories=cats),
                ),
                Knob(
                    SPENDING,
                    _("Increase when wealth rises above"),
                    ("spending", "ceiling"),
                    a.spending.ceiling,
                    CEILING,
                    _about(("spending", "ceiling")),
                ),
            ]
    if a.care:
        out += [
            Knob(
                CARE,
                _("Care cost"),
                ("care", "cost"),
                a.care.cost,
                EUR,
                _about(
                    ("care", "cost"),
                    N_("It grows with `index: {index}`. Fixed draws no episodes."),
                    index=a.care.index,
                ),
                models=CARED,
            ),
            Knob(
                CARE,
                _("Care duration"),
                ("care", "duration", "mean"),
                a.care.duration.mean,
                replace(MONTHS, delta=12.0),
                _about(
                    ("care", "duration"),
                    N_(
                        "The slider sets the mean. The yearly chance to enter care by age "
                        "(`care.hazard`) is a list: edit it on the Assumptions page. Fixed draws "
                        "no episodes."
                    ),
                ),
                models=CARED,
            ),
        ]
    if a.allocation:
        out += [
            Knob(
                ALLOCATION,
                pgettext("slider", "Rebalance every"),  # its unit follows: no `(months)`
                ("allocation", "rebalance_every"),
                a.allocation.rebalance_every,
                PERIOD,
                _about(
                    ("allocation", "rebalance_every"),
                    N_("The glide path itself is a list: edit it on the Assumptions page."),
                ),
            ),
            Knob(
                ALLOCATION,
                _("Skip after a loss"),
                ("allocation", "skip_after_loss"),
                a.allocation.skip_after_loss,
                replace(PERIOD, low=0.0),
                _about(("allocation", "skip_after_loss")),
            ),
        ]
    return out


def _vpw_knobs(vpw: Vpw, cats: str) -> list[Knob]:
    path = ("spending", "vpw")
    return [
        Knob(
            SPENDING,
            _("VPW growth"),
            (*path, "growth"),
            vpw.growth,
            TREND,
            _about((*path, "growth"), FLEXIBLE, categories=cats),
        ),
        Knob(
            SPENDING,
            _("Spend down to age"),
            (*path, "horizon_age"),
            vpw.horizon_age,
            AGE,
            _about((*path, "horizon_age")),
        ),
        Knob(
            SPENDING,
            _(goalseek.FLOOR),
            (*path, "floor"),
            vpw.floor,
            EUR,
            _about((*path, "floor")),
        ),
    ]


def switches(a: Assumptions) -> list[Switch]:
    """The toggles, each in its group of the sliders, which it opens without its sliders."""
    return [
        Switch(
            ALLOCATION, _("Invest the rest"), ("invest_rest",), a.invest_rest, _(INVEST_REST_HELP)
        ),
        Switch(
            TAXES,
            _("Realize gains"),
            ("tax", "harvest"),
            a.tax.harvest,
            _about(("tax", "harvest"), NO_LEVER),
        ),
    ]


def _spread_knobs(a: Assumptions, held: Mapping[str, bool]) -> list[Knob]:
    """The spread of equity sits in `MARKETS`, those of the gold and crypto classes in
    `GOLD_CRYPTO`."""
    spreads: dict[tuple[str, ...], tuple[str, Distribution]] = {
        ("inflation",): (_("Inflation"), a.inflation),
        **{
            ("returns", n): (class_name(n), d)
            for n, d in a.returns.items()
            if n != "equity" and n not in held
        },
        **{("indices", n): (named(n), d) for n, d in a.indices.items()},
    }
    return [
        Knob(
            SPREADS,
            _("{name} spread").format(name=name),
            (*path, "stdev"),
            d.stdev,
            SPREAD,
            _about(("stdev",), of=Distribution),
            models=DRAWN,
        )
        for path, (name, d) in spreads.items()
    ]


def knobs(
    a: Assumptions,
    streams: list[Stream],
    salaries: Salaries = NO_SALARIES,
    scenario: Scenario | None = None,
    assets: list[Asset] | None = None,
    *,
    work: Sequence[goalseek.Dial] = (),
) -> list[Knob]:
    """In sidebar order, the levers of the plan first. The groups are contiguous."""
    held = _held(assets or [])
    added = [e.stream for e in scenario.events if isinstance(e, AddStreamEvent)] if scenario else []
    every = [*streams, *added]
    indices = _index_knobs(a, every)
    return [
        *_spending_knobs(a, streams),
        *_salary_knobs(a, salaries),
        *(k for k in indices if k.group == SALARY),
        _pension_growth(a),
        *_savings_knobs(a, every),
        *(_event_knobs(scenario, a, work) if scenario else []),
        *_asset_knobs(a, assets or []),
        *_market_knobs(a, held, [k for k in indices if k.group == MARKETS]),
        *_holdings(a, held),
        *_rule_knobs(a),
        *_spread_knobs(a, held),
    ]
