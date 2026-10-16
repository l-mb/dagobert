"""A pension policy or depot carried from its `asof` to a later month: the mean return of its class
less its cost and the contributions of the months between, as a `fixed` run adds them. The engine
starts from it, the Snapshot page estimates today with it. A loan carries by its schedule
(`Loan.balance_at`), a term deposit by its interest (`TermDeposit.value_at`).

The contributions follow the streams of `cashflows.yaml` only: the events of the scenario that add,
end or set a stream before the start are left out, an approximation."""

from __future__ import annotations

from datetime import date

from dagobert import sv, tax
from dagobert.model.assets import AvDepot, PensionPolicy
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Plan
from dagobert.model.streams import Stream, StreamKind
from dagobert.returns import grown, monthly_rate

# a month of these streams opens the year of an Altersvorsorgedepot (`YearAcc.compulsory`)
INSURED = (StreamKind.SALARY, StreamKind.ALG1, StreamKind.SELF_EMPLOYED)


def months(asof: date | None, to: date) -> list[date]:
    """The months after the month of `asof` up to the month of `to`, as `Loan.balance_at`
    counts them: none without `asof` or for an `asof` in or after the month of `to`."""
    if asof is None:
        return []
    return [add_months(asof.replace(day=1), n) for n in range(1, months_between(asof, to) + 1)]


def policy(plan: Plan, spec: PensionPolicy, to: date) -> tuple[float, float]:
    """`value` and `paid` of `spec` carried through the month of `to`, at most through the month
    before `matures`: each month the mean return of its class less its `cost`, then in its
    `phases` (`Scenario.phase_of`) the employer's `contribution`, the own `premium` of a
    Basisrente and the conversion with its subsidy (`_converted`)."""
    rate = monthly_rate(plan.assumptions.returns[spec.growth].mean)
    value, paid = spec.value, spec.paid
    for month in months(spec.asof, min(to, add_months(spec.matures, -1))):
        value = grown(value, rate, spec.cost)
        if (phase := plan.scenario.phase_of(month)) in spec.phases:
            added = spec.contribution + spec.premium + _converted(plan, spec, month, str(phase))
            value, paid = value + added, paid + added
    return value, paid


def depot(plan: Plan, spec: AvDepot, to: date) -> float:
    """`value` of `spec` carried through the month of `to`: each month the mean return of its
    class less its `cost`, each December from `start` of a year in which a stream of `INSURED`
    pays the `contribution` and its share of the one Zulage of the person, on the contributions
    of all depots with the children of the year (`Income._contribute_av`)."""
    rate = monthly_rate(plan.assumptions.returns[spec.growth].mean)
    ty = tax.for_year(plan.assumptions.tax_year)
    depots = [a for a in plan.assets if isinstance(a, AvDepot)]
    value = spec.value
    for month in months(spec.asof, to):
        value = grown(value, rate, spec.cost)
        if month.month == 12 and month >= spec.start and _insured(plan, month.year):
            total = sum(d.contribution for d in depots if month >= d.start)
            children = plan.assumptions.person.kindergeld_in(month.year)
            zulage = float(tax.av_zulage(total, children, ty))
            value += spec.contribution + (zulage * spec.contribution / total if total else 0.0)
    return value


def _active(s: Stream, month: date, phase: str) -> bool:
    return (
        (s.start is None or s.start <= month)
        and (s.end is None or month < s.end)
        and (s.phases is None or phase in s.phases)
    )


def _gross(plan: Plan, s: Stream, month: date, phase: str) -> float:
    """The gross of one payment of the salary `s` in `month`, in euros of the start, without
    `scale` (`Income._salary_nominal`): a share of another (`of`) follows the row of that name
    that pays in `month`, else its last row."""
    own = s.factor.get(phase, 1.0)
    if s.of is None or s.share is None:
        return (s.gross or 0.0) * s.part * own
    named = [b for b in plan.streams if b.name == s.of]
    base = next((b for b in named if _active(b, month, phase)), named[-1])
    return s.share * s.every * _gross(plan, base, month, phase) * own


def _insured(plan: Plan, year: int) -> bool:
    """A month of `year` pays a stream of `INSURED` in its phase, a salary only with a gross
    above zero (`_gross`), as the engine opens the year."""
    return any(
        s.kind in INSURED
        and _active(s, month, phase)
        and (s.kind != StreamKind.SALARY or _gross(plan, s, month, phase) > 0)
        for month in (date(year, m, 1) for m in range(1, 13))
        for phase in [str(plan.scenario.phase_of(month))]
        for s in plan.streams
    )


def _converts(p: PensionPolicy, s: Stream) -> bool:
    """Whether the conversion of `p` comes off the salary `s` (`Income._source`): the one that
    its `salary` names, else one without `of`."""
    return s.name == p.salary if p.salary else s.of is None


def _converted(plan: Plan, spec: PensionPolicy, month: date, phase: str) -> float:
    """The conversion of `spec` in `month` with its subsidy, as `Income._convert` takes it: from
    the gross of its salary (`_converts`, the first that pays), in the rooms that the employer's
    contributions of the policies that pay and the conversions before it in file order leave
    (`sv.conversions`), on the regular gross of every monthly salary (`_gross`), a share of
    another (`of`) too."""
    salaries = [
        (s, _gross(plan, s, month, phase))
        for s in plan.streams
        if s.kind == StreamKind.SALARY and s.every == 1 and _active(s, month, phase)
    ]
    # `spec` in the place of the policy of its id, else last
    policies = {p.id: p for p in plan.assets if isinstance(p, PensionPolicy)} | {spec.id: spec}
    paying = [p for p in policies.values() if phase in p.phases and month < p.matures]
    taken = [
        (p, min(p.conversion, pay))
        for p in paying
        if p.conversion
        and (pay := next((g for s, g in salaries if _converts(p, s)), None)) is not None
    ]
    convs = sv.conversions(
        [(amount, p.subsidy) for p, amount in taken],
        sum(g for _, g in salaries),
        sum(p.contribution for p in paying),
        plan.assumptions.tax,
        tax.for_year(plan.assumptions.tax_year),
        month=month,
    )
    paid = ((p, amount + float(c.subsidy)) for (p, amount), c in zip(taken, convs, strict=True))
    return next((added for p, added in paid if p is spec), 0.0)
