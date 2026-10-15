"""Where the money of a stretch of a scenario goes: income sources against taxes, spending and
loans. The numbers are the engine's own, read from the `Ledger` of a single-path run, so
repaid loans, sales, the end of ALG1 and the start of the pension are all in it."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import groupby

import numpy as np

from dagobert.i18n import N_, _
from dagobert.model.events import AddStreamEvent
from dagobert.model.plan import Plan
from dagobert.result import (
    CAPITAL_TAX,
    CONVERSION,
    DRAW,
    LOAN_PRINCIPAL,
    MOVE_IN,
    MOVE_OUT,
    MOVED,
    NONCASH,
    ONEOFF_CONTRIBUTION,
    ONEOFF_IN,
    ONEOFF_OUT,
    ONEOFF_TAX,
    PROFIT,
    SALARY,
    SAVINGS_PLAN,
    SOURCE,
    SPENDING,
    TAX,
    Ledger,
    RunResult,
)
from dagobert.result import WORDS as LEDGER_WORDS

ONEOFFS = N_("one-offs")
TAXES = N_("taxes & SV")
SAVED = N_("into savings plans")  # the line of `Budget.saved` in `totals` and on the sheet
REFUND = N_("{tax} refund")  # a source: a tax that pays back
CAPITAL_TAX_ITEM = "Abgeltungsteuer"  # the one item of the group `CAPITAL_TAX`
# the lines of `Budget.totals`
INCOME, TAXED, SPENT, SURPLUS = N_("income"), N_("taxes"), N_("spending"), N_("surplus")
INTO_ASSETS, NONCASH_INCOME = N_("into assets"), N_("non-cash income")
WEALTH_BUILT = N_("wealth built")
# The words of a budget: English data like the ledger's (`result.WORDS`), said by `said`
WORDS = LEDGER_WORDS | {
    *(ONEOFFS, TAXES, SAVED, INCOME, TAXED, SPENT, SURPLUS, INTO_ASSETS, NONCASH_INCOME),
    WEALTH_BUILT,
}


def said(name: str) -> str:
    """A name of the ledger or of a budget in the language of the session: its words (`WORDS`)
    translated, a label, a name or a category as written. A name of parts says each part:
    `<label>: employer`, `sale: <asset>`; a refund of a tax its own words."""
    tax = name.removesuffix(REFUND.format(tax=""))
    if tax != name and tax in WORDS:
        return _(REFUND).format(tax=said(tax))
    return ": ".join(_(part) if part in WORDS else part for part in name.split(": "))


@dataclass(frozen=True)
class Budget:
    """Per month, in euros of the simulation start."""

    sources: dict[str, float] = field(default_factory=dict)
    taxes: dict[str, float] = field(default_factory=dict)  # income tax, own SV, tax on one-offs
    spending: dict[str, dict[str, float]] = field(default_factory=dict)  # group, then item
    # non-cash income by item: the growth of the assets and what goes into a policy without
    # passing the cash. No cash flow, outside `net` and `surplus`
    noncash: dict[str, float] = field(default_factory=dict)
    # how the flows change an asset other than the cash, or a loan, beyond the loan principal,
    # by `group: item`: a premium puts into a policy, a payout takes out of it (negative)
    assets: dict[str, float] = field(default_factory=dict)
    # what the savings plans paid into their assets, by plan: part of the surplus, which they
    # move out of the cash
    saved: dict[str, float] = field(default_factory=dict)

    @property
    def income(self) -> float:
        return sum(self.sources.values())

    @property
    def net(self) -> float:
        return self.income - sum(self.taxes.values())

    @property
    def surplus(self) -> float:
        """What is left to save. Negative: the stretch draws on the savings."""
        return self.net - sum(sum(items.values()) for items in self.spending.values())

    @property
    def into_assets(self) -> float:
        """What the flows put into the assets other than the cash and into the loans, less
        what they take out: the loan principal and a salary conversion, less what a policy pays
        out as income, with the one-offs also a premium, a purchase and a repayment, less a sale
        at the value of the asset, a policy paid out at once and a write-off."""
        return sum(self.spending.get(LOAN_PRINCIPAL, {}).values()) + sum(self.assets.values())

    @property
    def wealth_built(self) -> float:
        """The change of the net worth before the latent tax: the surplus, what went into the
        assets and the non-cash income. Without the one-offs it leaves them out on both sides."""
        return self.surplus + self.into_assets + sum(self.noncash.values())

    @property
    def outflows(self) -> dict[str, dict[str, float]]:
        """The taxes as one group, then the spending groups: item to amount."""
        return ({TAXES: self.taxes} if self.taxes else {}) | self.spending

    @property
    def lines(self) -> dict[str, float]:
        """Each source, then each group of the outflows as a negative sum."""
        return self.sources | {g: -sum(items.values()) for g, items in self.outflows.items()}

    @property
    def totals(self) -> dict[str, float]:
        """The lines of the comparison table on the Flows page, signed like the sheet of the
        Cashflows page: what goes out below zero, so `surplus` is the sum of the lines above it
        and `wealth built` that of `surplus` and the lines below it but the savings plans."""
        return {
            INCOME: self.income,
            TAXED: self.net - self.income,
            SPENT: self.surplus - self.net,
            SURPLUS: self.surplus,
            SAVED: sum(self.saved.values()),
            INTO_ASSETS: self.into_assets,
            NONCASH_INCOME: sum(self.noncash.values()),
            WEALTH_BUILT: self.wealth_built,
        }


@dataclass(frozen=True)
class Stretch:
    """Contiguous months of one phase. `label` names it as the pages do and adds the years when
    the phase occurs twice, `key` (the phase and how often it occurred before) finds it in
    another run."""

    phase: str
    months: list[int]
    label: str
    key: tuple[str, int]


def stretches(result: RunResult) -> list[Stretch]:
    runs = [
        (phase, [i for i, _phase in group])
        for phase, group in groupby(enumerate(result.phases), key=lambda item: item[1])
    ]
    count = Counter(phase for phase, _months in runs)
    seen: Counter[str] = Counter()
    out: list[Stretch] = []
    for phase, months in runs:
        years = f"{result.months[months[0]]:%Y}–{result.months[months[-1]]:%Y}"
        shown = result.phase_labels.get(phase, phase)
        label = shown if count[phase] == 1 else f"{shown} {years}"
        out.append(Stretch(phase, months, label, (phase, seen[phase])))
        seen[phase] += 1
    return out


def ledger(result: RunResult) -> Ledger:
    if result.ledger is None:
        msg = "the budget needs the ledger of a single-path run"
        raise ValueError(msg)
    return result.ledger


def regular_salary(result: RunResult) -> dict[str, float]:
    """Gross salary and self-employed profit of a usual month per phase, in start-year euros: the
    median over the months of the phase that pay either, so a bonus month does not count. A phase
    without them is absent: `scale.salary` scales both."""
    book = ledger(result)
    paid = sum(
        (
            row
            for (side, group, _item), row in book.entries.items()
            if side == SOURCE and group in (SALARY, PROFIT)
        ),
        np.zeros(book.months),
    )
    phases = np.array(result.phases)[paid > 0]
    return {
        phase: float(np.median(paid[paid > 0][phases == phase]))
        for phase in dict.fromkeys(phases.tolist())
    }


def _oneoff(side: str, group: str) -> bool:
    """A one-off or a move, both its sides, and among the non-cash income the part of a
    severance that goes into a policy and the top-up of a policy to its guarantee. A salary
    conversion is none: its policy side counts like the loan principal."""
    if side == NONCASH:
        return group == ONEOFF_CONTRIBUTION
    return side in (ONEOFF_IN, ONEOFF_OUT, MOVE_IN, MOVE_OUT, MOVED) and group != CONVERSION


def from_ledger(
    book: Ledger,
    months: Sequence[int],
    *,
    oneoffs: bool = False,
    run_rate: bool = False,
    without: Collection[str] = (),
) -> Budget:
    """Monthly average over `months` (indices of the run). One-off capital moves (sales,
    severance, purchases, repayments from them and their tax) count only with `oneoffs`, the tax
    on them (also the Grunderwerbsteuer) under the taxes, so `net` is after all taxes, the costs
    of a purchase under the spending `one-offs`. With `run_rate` a stream paid every n months
    counts 1/n of its payment in each month that earns it. A tax that pays back over the
    stretch becomes a source. The capital gains tax is no tax on the income: a withdrawal
    triggers it and pays it, so it is a spending group of its own. `without` names streams to
    leave out: a stream books its flows under its name. The non-cash income goes into
    `noncash` whatever `without` says, its one-off contributions (the tax-free part of a
    severance paid into a policy, the top-up of a policy to its guarantee) only with `oneoffs`,
    like the severance. `assets` takes the other side of the flows: the draws out of a policy
    that pays a source, and the side of the one-offs and the moves only with `oneoffs`. What a
    savings plan pays goes into `saved`, its other side nowhere: the surplus holds it."""
    sources: dict[str, float] = {}
    taxes: dict[str, float] = {}
    spending: dict[str, dict[str, float]] = {}
    noncash: dict[str, float] = {}
    assets: dict[str, float] = {}
    rows = dict(book.entries)
    for key, rate in book.run_rate.items() if run_rate else ():
        rows[key] = rows.get(key, np.zeros(book.months)) + rate
    means = {key: float(row[list(months)].sum()) / len(months) for key, row in rows.items()}
    saved = {
        item: amount
        for (side, group, item), amount in means.items()
        if (side, group) == (MOVE_OUT, SAVINGS_PLAN) and amount
    }
    for (side, group, item), amount in means.items():
        if (
            not amount
            or group == SAVINGS_PLAN
            or (_oneoff(side, group) and not oneoffs)
            or (side in (SOURCE, SPENDING) and item in without)
        ):
            continue
        taxed = side == TAX or (side, group) == (ONEOFF_OUT, ONEOFF_TAX)
        if taxed and amount < 0:
            label = REFUND.format(tax=item if side == TAX else group)
            sources[label] = sources.get(label, 0.0) - amount
        elif side in (SOURCE, ONEOFF_IN, MOVE_IN):
            label = item if side == SOURCE else f"{group}: {item}"
            sources[label] = sources.get(label, 0.0) + amount
        elif (side, item) == (TAX, CAPITAL_TAX):
            spending[CAPITAL_TAX] = {CAPITAL_TAX_ITEM: amount}
        elif taxed:
            taxes[item if side == TAX else f"{group}: {item}"] = amount
        elif side == NONCASH:
            noncash[item] = noncash.get(item, 0.0) + amount
        elif side in (DRAW, MOVED):
            assets[f"{group}: {item}"] = assets.get(f"{group}: {item}", 0.0) + amount
        elif side == SPENDING:
            spending.setdefault(group, {})[item] = amount
        else:
            spending.setdefault(ONEOFFS, {})[f"{group}: {item}"] = amount
    return Budget(sources, taxes, spending, noncash, assets, saved)


def ahead(result: RunResult, since: date, count: int = 12) -> dict[str, list[int]]:
    """Per phase, its first `count` months of the run from the month of `since` on. A phase that
    the run does not reach by then is absent."""
    first = since.replace(day=1)
    out: dict[str, list[int]] = {}
    for i, (month, phase) in enumerate(zip(result.months, result.phases, strict=True)):
        if month >= first and len(months := out.setdefault(phase, [])) < count:
            months.append(i)
    return out


def beyond_streams(result: RunResult, plan: Plan, since: date) -> dict[str, Budget]:
    """Per phase that the run reaches from `since` on, what no stream pays: the taxes, the PKV
    subsidy, the loans, the property upkeep, the capital gains tax, care and policy payouts, and
    in `noncash` the growth of the assets and the employer's bAV contributions and the Zulage of
    an Altersvorsorgedepot (no one-offs). The mean over the months of `ahead`, with the run
    rate. The streams of the scenario's `add_stream` events are streams too."""
    names = {s.name for s in plan.streams} | {
        ev.stream.name for ev in plan.scenario.events if isinstance(ev, AddStreamEvent)
    }
    return {
        phase: from_ledger(ledger(result), months, run_rate=True, without=names)
        for phase, months in ahead(result, since).items()
    }
