"""The risk of losing the ability to work (rule `disability`): the onset per path, the months of
Entgeltfortzahlung and Krankengeld, the EM-Rente on the pension from points, a BU policy. Relations
between runs of small plans with zero returns; the law in amounts is in `test_tax.py` and
`test_sv.py`."""

from collections.abc import Callable
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from builders import booked, cash, phases, plan, zero_run
from pydantic import ValidationError

from dagobert import loader, sv, tax
from dagobert.model.assets import AvDepot
from dagobert.model.assumptions import DEFAULT_HAZARD, Person
from dagobert.model.events import SetStreamEvent
from dagobert.model.months import add_months, months_between
from dagobert.model.plan import Plan, Scenario
from dagobert.model.streams import Stream, StreamKind
from dagobert.model.taxes import TaxOptions
from dagobert.result import (
    AV,
    BENEFIT,
    EM_RENTE,
    KRANKENGELD,
    KV,
    PV,
    RV,
    SALARY,
    SOURCE,
    SPENDING,
    RunResult,
)

TY = tax.for_year(2026)
START = date(2026, 1, 1)  # of the plans of `builders`
PERSON = Person(born=date(1977, 1, 1), rv_since=date(1999, 1, 1))
ONSET = date(2027, 3, 1)
M0 = months_between(START, ONSET)
AT67 = months_between(START, date(2044, 1, 1))  # born on the 1st: 67 in its month
RETIRES = Scenario.model_validate(
    {"name": "t", "phases": phases((START, "work"), (date(2044, 1, 1), "retired"))}
)
GKV = {"pkv": False}
SALARY_ROW = Stream(name="Gehalt", kind=StreamKind.SALARY, gross=6000, index=None, phases=["work"])
PENSION = Stream(
    name="Rente", kind=StreamKind.PENSION, points=30, point_value=40, phases=["retired"], index=None
)
SHOP = Stream(name="Laden", kind=StreamKind.SELF_EMPLOYED, amount=4000, index=None, phases=["work"])
BU = Stream(name="BU", kind=StreamKind.BU, cat="insurance", amount=2000, premium=-95)
POINT_MONTH = 6000 / TY.durchschnittsentgelt  # the points of a month of the salary


def disabled(
    streams: list[Stream], at: date | None = ONSET, scenario: Scenario = RETIRES, **kw: object
) -> Plan:
    """A plan of the person, forced disabled `at`, without `at` the default chances."""
    block = {"disability": {"at": at} if at else {}}
    return plan(streams, [cash(500_000)], scenario, person=PERSON, **(block | kw))


def run(
    streams: list[Stream], at: date | None = ONSET, scenario: Scenario = RETIRES, **kw: object
) -> RunResult:
    return zero_run(disabled(streams, at, scenario, **kw), AT67 + 24)


def pension(r: RunResult) -> np.ndarray:
    """The statutory pension of each month: the EM-Rente, after 67 under the stream's name."""
    return booked(r, EM_RENTE, SOURCE) + booked(r, "Rente", SOURCE)


def test_the_default_hazard_hits_its_anchors() -> None:
    """The yearly chance by age, weighted by the aktiv Versicherte of 15 to 64 at the end of 2024
    (DRV, Versicherte 2024, table 3.00 V), gives the 4.45 new EM-Renten per 1,000 of 2024 and the
    mean age at their start, 53.8, less the seven months before it; from 40, the age of the
    example, about one in five has an onset before 67."""
    weights = np.array(
        [
            *(113232, 225358, 345939, 464515, 543823, 593397, 613530, 641483, 679994, 734884),
            *(761696, 790894, 825281, 819602, 802371, 806878, 828997, 845126, 871959, 945075),
            *(935622, 958929, 941421, 923872, 897837, 889451, 889598, 905719, 897854, 902030),
            *(854201, 836648, 820706, 796597, 768847, 772522, 769631, 824778, 895711, 919110),
            *(974709, 1006730, 1017247, 1026963, 1007581, 1001087, 966784, 892781, 733252),
            472729,
        ],
        dtype=float,
    )
    ages = np.arange(15, 65)
    first = DEFAULT_HAZARD[0].age
    points = ([p.age for p in DEFAULT_HAZARD], [p.factor for p in DEFAULT_HAZARD])
    chance = np.where(ages < first, 0.0, np.interp(ages, *points))
    assert (chance * weights).sum() / weights.sum() == pytest.approx(171_732 / 38_573_053, 0.01)
    assert (ages * chance * weights).sum() / (chance * weights).sum() == pytest.approx(
        53.8 - 7 / 12, abs=0.1
    )
    monthly = 1 - (1 - np.interp(np.arange(40 * 12, 67 * 12) / 12, *points)) ** (1 / 12)
    assert 1 - np.prod(1 - monthly) == pytest.approx(0.2, abs=0.01)


def test_a_forced_onset_stops_the_pay_and_the_premium_and_starts_the_benefit() -> None:
    """The salary pays in the month of the onset and the next (§3 EFZG, six weeks), the premium
    of the BU policy in the month of the onset, the benefit from the next month to its
    `until_age`."""
    r = run([SALARY_ROW, BU])
    salary = booked(r, "Gehalt", SOURCE, SALARY)
    assert salary[: M0 + 2] == pytest.approx(6000.0)
    assert not salary[M0 + 2 :].any()
    premium, benefit = booked(r, "BU", SPENDING, "insurance"), booked(r, f"BU: {BENEFIT}", SOURCE)
    assert premium[: M0 + 1] == pytest.approx(95.0)
    assert not premium[M0 + 1 :].any()
    assert not benefit[: M0 + 1].any()
    assert benefit[M0 + 1 : AT67] == pytest.approx(2000.0)
    assert not benefit[AT67:].any()
    assert [str(m.month) for m in r.markers if m.kind == "disability"] == [str(ONSET)]


def test_a_fixed_run_draws_no_onset_and_a_forced_one_holds_on_every_path() -> None:
    """The default chances draw no onset in a single-path `fixed` run; a forced one is at M0."""
    assert not (run([SALARY_ROW], at=None).onset >= 0).any()
    assert (run([SALARY_ROW]).onset == M0).all()


@pytest.mark.parametrize(("opts", "sick"), [(GKV, True), ({}, False)])
def test_krankengeld_pays_a_member_of_the_gkv_until_the_em_rente(
    opts: dict[str, object], *, sick: bool
) -> None:
    """§§44, 47 SGB V: from the third month to the sixth after the onset the Krankengeld of the
    last salary, less the member's half of RV, ALV and PV on it, not on 80% of the salary (§170
    Abs. 1 Nr. 2 a SGB VI: "soweit sie auf die Leistung entfallen"); a PKV member gets none
    (no Krankentagegeld in the plan)."""
    r = run([SALARY_ROW, PENSION], tax=opts)
    paid = booked(r, KRANKENGELD, SOURCE)
    months = slice(M0 + 2, M0 + 7)
    if not sick:
        assert not paid.any()
        return
    expected = sv.krankengeld_month(
        6000.0, TaxOptions.model_validate(opts), PERSON, ONSET, TY, church=0.0, employed=True
    )
    assert paid[months] == pytest.approx(float(expected.gross))
    assert paid.sum() == pytest.approx(5 * float(expected.gross))
    assert booked(r, RV)[months] == pytest.approx(float(expected.rv))
    assert booked(r, AV)[months] == pytest.approx(float(expected.alv))
    assert booked(r, PV)[months] == pytest.approx(float(expected.pv))
    assert not booked(r, KV)[months].any()  # compulsory and free (§224 SGB V)


@pytest.mark.parametrize("krankengeld", [True, False])
def test_a_business_with_the_krankengeld_option_gets_it_on_its_profit(*, krankengeld: bool) -> None:
    """§47 Abs. 4 SGB V: 70% of the last Arbeitseinkommen, without the cap at the net, and the
    RV of a business in the GRV (§3 S. 1 Nr. 3 SGB VI); none without the Wahlerklärung."""
    opts = GKV | {"self_employed": {"rv": "income", "krankengeld": krankengeld}}
    r = run([SHOP], tax=opts)
    paid = booked(r, KRANKENGELD, SOURCE)[M0 + 2 : M0 + 7]
    assert paid == pytest.approx(TY.krankengeld_rate * 4000.0 * krankengeld)
    assert booked(r, RV)[M0 + 2 : M0 + 7] == pytest.approx(paid * TY.rv_rate)
    assert not booked(r, "Laden", SOURCE, "profit")[M0 + 2 :].any()


@pytest.mark.parametrize(("rv", "paid"), [("income", True), ("regular", True), ("none", False)])
def test_a_business_in_the_grv_pays_the_pflichtbeitraege_of_an_em_rente(
    rv: str, *, paid: bool
) -> None:
    """§43 Abs. 1 S. 1 Nr. 2, §55 Abs. 1 SGB VI: the contributions of a business in the GRV (§2,
    §4 Abs. 2) are Pflichtbeiträge: four years of it fill the three of the last five after the
    months before the start have left the window."""
    r = run([SHOP, PENSION], at=date(2030, 3, 1), tax={"self_employed": {"rv": rv}})
    assert booked(r, EM_RENTE, SOURCE).any() == paid == r.em[0]


def test_the_em_rente_starts_in_the_seventh_month_and_runs_on_at_67() -> None:
    """§101 Abs. 1 SGB VI: from the seventh calendar month after the onset, whatever the phases of
    the pension stream say; at the Regelaltersgrenze the Altersrente follows with the same
    points and factor (§88 Abs. 1 S. 2, §77 Abs. 3 S. 1): no step."""
    rente = pension(run([SALARY_ROW, PENSION]))
    assert not rente[: M0 + 7].any()
    assert rente[M0 + 7] > 0
    assert rente[M0 + 7 :] == pytest.approx(rente[M0 + 7])
    assert booked(run([SALARY_ROW, PENSION]), "Rente", SOURCE)[AT67] == rente[M0 + 7]


def _em_points(onset: date, months_paid: int) -> float:
    """The points of an EM-Rente by the law: the points reached, and the Zurechnungszeit to its
    end in the year of the Rentenbeginn at their average over the months since `rv_since`."""
    reached = 30 + months_paid * POINT_MONTH
    since = months_between(PERSON.rv_since or START, onset)
    end = TY.zurechnung_months(add_months(onset, 7).year)
    added = end - months_between(PERSON.born, onset)
    return reached * (1 + added / since)


@pytest.mark.parametrize("onset", [date(2027, 3, 1), date(2038, 3, 1)])
def test_the_em_rente_takes_the_points_and_the_zugangsfaktor_of_the_law(onset: date) -> None:
    """At 50 and at 61 the Rentenbeginn lies before 62, so both lose 10.8% (§77 Abs. 2 S. 1 Nr.
    3, S. 2 SGB VI): the earlier onset pays less only through its points."""
    rente = pension(run([SALARY_ROW, PENSION], at=onset))
    i = months_between(START, onset)
    expected = _em_points(onset, i) * 40 * float(sv.em_factor(50.0, TY))
    assert rente[i + 7] == pytest.approx(expected)


def test_voluntary_contributions_after_the_onset_add_nothing() -> None:
    """§75 Abs. 2 S. 1 SGB VI: no points after the onset count for the EM-Rente."""
    later = Stream(
        name="RV", kind=StreamKind.RV_VOLUNTARY, amount=-300, index=None, start=add_months(ONSET, 3)
    )
    plain = pension(run([SALARY_ROW, PENSION]))
    assert pension(run([SALARY_ROW, PENSION, later])) == pytest.approx(plain)


def test_a_gap_before_the_onset_lowers_the_zurechnungszeit_too() -> None:
    """§72 Abs. 3 SGB VI: a year without contributions stays in the months over which the
    Zurechnungszeit takes the average, so the EM-Rente falls by more than the points of that
    year."""
    onset = date(2029, 3, 1)
    i = months_between(START, onset)
    gap = [
        SALARY_ROW.model_copy(update={"end": date(2027, 1, 1)}),
        SALARY_ROW.model_copy(update={"start": date(2028, 1, 1)}),
    ]
    full = pension(run([SALARY_ROW, PENSION], at=onset))[i + 7]
    paused = pension(run([*gap, PENSION], at=onset))[i + 7]
    lost = 12 * POINT_MONTH * 40 * float(sv.em_factor(52.0, TY))
    assert full - paused == pytest.approx(lost * _em_points(onset, 0) / 30)


def test_a_salary_ended_long_before_the_onset_gives_no_em_rente() -> None:
    """§43 Abs. 1 S. 1 Nr. 2 SGB VI: three years of Pflichtbeiträge in the last five; the BU
    benefit pays anyway."""
    ended = SALARY_ROW.model_copy(update={"end": date(2026, 2, 1)})
    r = run([ended, PENSION, BU], at=date(2029, 3, 1))
    assert not booked(r, EM_RENTE, SOURCE).any()
    assert booked(r, f"BU: {BENEFIT}", SOURCE).any()


def test_the_benefit_is_taxed_at_its_ertragsanteil() -> None:
    """§22 Nr. 1 S. 3 a bb EStG, §55 Abs. 2 EStDV: the same euros as other income pay more tax."""
    other = Stream(
        name="Rente BU", kind=StreamKind.OTHER_INCOME, amount=2000, index=None, start=ONSET
    )
    benefit = run([BU.model_copy(update={"premium": 0.0})], at=add_months(ONSET, -1))
    taxed = run([other], at=None)
    year = slice(M0 + 10, M0 + 22)
    assert benefit.income[0, year] == pytest.approx(taxed.income[0, year])
    assert -benefit.taxes[0, year].sum() < -taxed.taxes[0, year].sum()


def test_a_voluntary_member_pays_kv_on_the_benefit_and_none_on_the_krankengeld() -> None:
    """BVSzGs, Katalog: a private BU-Rente is liable for a voluntary member, the KVdR of the
    EM-Rente leaves it free (§237 SGB V); the Krankengeld of a business is free (§224 Abs. 1)."""
    opts = GKV | {"self_employed": {"rv": "income", "krankengeld": True}}
    sick = slice(M0 + 2, M0 + 7)
    without, with_bu = (run([SHOP, PENSION, *bu], tax=opts) for bu in ([], [BU]))
    added = booked(with_bu, KV)[sick] - booked(without, KV)[sick]
    rate = 2 * (TY.kv_rate_reduced + TY.kv_zusatz_half)
    assert added == pytest.approx((2000.0 - TY.kv_min_base) * rate)  # without it the minimum
    assert booked(with_bu, KV)[M0 + 8] == booked(without, KV)[M0 + 8]  # the KVdR


def test_the_premium_changes_by_set_stream_or_by_a_second_row() -> None:
    """The owner's employer BU: no premium while the employer pays it, its own premium from the
    month of the leave. A `set_stream` of `premium` and two rows of one name give the same run;
    the benefit of a later onset pays from either."""
    leave = date(2026, 7, 1)
    employer = BU.model_copy(update={"premium": 0.0})
    event = SetStreamEvent(type="set_stream", at=leave, name="BU", premium=-95)
    scenario = RETIRES.model_copy(update={"events": [event]})
    rows = [
        employer.model_copy(update={"end": leave}),
        BU.model_copy(update={"start": leave}),
    ]
    by_event = run([SALARY_ROW, employer], scenario=scenario)
    by_rows = run([SALARY_ROW, *rows])
    premium = booked(by_event, "BU", SPENDING, "insurance")
    i = months_between(START, leave)
    assert not premium[:i].any()
    assert premium[i : M0 + 1] == pytest.approx(95.0)
    assert by_rows.liquid == pytest.approx(by_event.liquid)
    assert booked(by_rows, f"BU: {BENEFIT}", SOURCE)[M0 + 1 : AT67] == pytest.approx(2000.0)


@pytest.mark.parametrize("ended", ["end", "end_streams"])
@pytest.mark.parametrize("leave", [date(2026, 7, 1), add_months(ONSET, 12)])
def test_a_lapsed_policy_pays_the_claim_of_an_onset_before(ended: str, leave: date) -> None:
    """A BU that lapses when the employer stops paying: from that month no premium and no
    benefit of a later onset; an onset before is a claim, whose benefit runs to `until_age`."""
    if ended == "end":
        r = run([SALARY_ROW, BU.model_copy(update={"end": leave})])
    else:
        event = {"type": "end_streams", "at": leave, "names": ["BU"]}
        ends = Scenario.model_validate(RETIRES.model_dump(by_alias=True) | {"events": [event]})
        r = run([SALARY_ROW, BU], scenario=ends)
    assert not booked(r, "BU", SPENDING, "insurance")[months_between(START, leave) :].any()
    benefit = booked(r, f"BU: {BENEFIT}", SOURCE)
    assert not benefit[: M0 + 1].any()
    assert benefit[M0 + 1 : AT67] == pytest.approx(2000.0 * (leave > ONSET))
    assert not benefit[AT67:].any()


def test_a_policy_taken_after_the_onset_pays_nothing() -> None:
    late = BU.model_copy(update={"start": add_months(ONSET, 1)})
    assert not booked(run([SALARY_ROW, late]), f"BU: {BENEFIT}", SOURCE).any()


def test_the_bu_policy_stays_outside_the_spending_cut() -> None:
    """A contract is no flexible spending: a cut of its category leaves the premium."""
    liability = Stream(name="Haftpflicht", cat="insurance", amount=-10, index=None)
    rule = {"cut": 0.5, "trigger": 100, "categories": ["insurance"]}
    r = run([BU, liability], at=None, spending=rule, tax=GKV)
    assert booked(r, "BU", SPENDING, "insurance")[:12] == pytest.approx(95.0)
    assert booked(r, "Haftpflicht", SPENDING, "insurance")[1:12] == pytest.approx(5.0)


PATHS = 60
HAZARD = {"hazard": [{"age": 55, "factor": 0.08}]}


def _paths(disability: object = HAZARD, **kw: object) -> Plan:
    """A GKV member with a salary to 63, the pension from points with the KVdR, an
    Altersvorsorgedepot and a BU policy, at chances that disable about half the paths after 55.
    Insured since 1995, so 35 years let every path claim at 63: the old-age claim is the same on
    every path, by the months of the paths that pay."""
    retires = Scenario.model_validate(
        {"name": "t", "phases": phases((START, "work"), (date(2040, 1, 1), "retired"))}
    )
    depot = AvDepot(id="av", kind="av_depot", contribution=1200, start=date(2027, 1, 1))
    streams = [SALARY_ROW, PENSION, BU]
    assets: list[object] = [cash(300_000), depot]
    person = PERSON.model_copy(update={"rv_since": date(1995, 1, 1)})
    return plan(streams, assets, retires, person=person, tax=GKV, disability=disability, **kw)


def test_the_paths_of_a_drawn_onset_run_as_a_forced_one_and_the_others_as_without() -> None:
    """Per path the claim of the EM-Rente, its year for the tax, the Rentenfreibetrag, the KVdR
    and the payout of the Altersvorsorgedepot at the old-age claim: a path with a drawn onset is
    the run forced there, a path without one the run without the block."""
    p, months = _paths(), months_between(START, date(2047, 1, 1))
    drawn = zero_run(p, months, PATHS)
    assert 0.2 < (drawn.onset >= 0).mean() < 0.8
    without = zero_run(_paths(None), months)
    for k in np.flatnonzero(drawn.onset < 0)[:3]:
        assert drawn.liquid[k] == pytest.approx(without.liquid[0])
    for k in np.flatnonzero(drawn.onset >= 0)[:4]:
        at = add_months(START, int(drawn.onset[k]))
        alone = zero_run(_paths({"at": at}), months)
        assert drawn.liquid[k] == pytest.approx(alone.liquid[0]), at


def test_two_runs_draw_the_same_onsets_whatever_else_differs() -> None:
    """The draw has a purpose of its own (`disability`): the paths pair up."""
    months = months_between(START, date(2047, 1, 1))
    a = zero_run(_paths(), months, PATHS)
    b = zero_run(_paths(cash_buffer_months=2), months, PATHS)
    assert (a.onset == b.onset).all()


def test_the_model_refuses_what_a_bu_policy_cannot_be() -> None:
    """A BU runs by its contract: no phases, no factor, no period; a benefit of 0 or more, a
    premium of 0 or less; the fields of a BU belong to it alone."""
    for odd in ({"phases": ["work"]}, {"factor": {"work": 0.5}}, {"every": 12}, {"amount": -1}):
        with pytest.raises(ValidationError):
            Stream.model_validate(BU.model_dump() | odd)
    with pytest.raises(ValidationError):
        Stream.model_validate(BU.model_dump() | {"premium": 95})
    with pytest.raises(ValidationError, match="takes no premium"):
        Stream(name="x", kind=StreamKind.EXPENSE, amount=-1, premium=-5)


def test_a_set_stream_sets_the_premium_of_a_bu_policy_only() -> None:
    event = SetStreamEvent(type="set_stream", at=date(2026, 7, 1), name="Gehalt", premium=-95)
    with pytest.raises(ValidationError, match="it takes gross"):
        disabled([SALARY_ROW], scenario=RETIRES.model_copy(update={"events": [event]}))


@pytest.mark.parametrize(
    ("at", "refused"), [(date(2025, 12, 1), "before the start"), (date(2044, 1, 1), "age of 67")]
)
def test_an_onset_before_the_start_or_from_67_is_refused(at: date, refused: str) -> None:
    """A plan cannot start disabled, and from the Regelaltersgrenze the old-age pension pays."""
    with pytest.raises(ValidationError, match=refused):
        disabled([SALARY_ROW], at=at)
    disabled([SALARY_ROW], at=add_months(at, 1 if at < START else -1))


def test_an_onset_in_the_month_of_the_old_age_claim_leaves_no_trace() -> None:
    """§34 Abs. 2 SGB VI: after the old-age pension at 63 no EM-Rente, so an onset in its first
    month marks nothing and changes nothing."""
    claim = date(2040, 1, 1)
    early = Scenario.model_validate(
        {"name": "t", "phases": phases((START, "work"), (claim, "retired"))}
    )
    forced = run([SALARY_ROW, BU, PENSION], at=claim, scenario=early)
    plain = run([SALARY_ROW, BU, PENSION], at=None, scenario=early)
    assert not [m for m in forced.markers if m.kind == "disability"]
    assert not (forced.onset >= 0).any()
    assert forced.liquid == pytest.approx(plain.liquid)


def test_the_krankengeld_ends_with_the_old_age_claim() -> None:
    """§50 Abs. 1 S. 1 Nr. 1 SGB V: an onset two months before the old-age pension at 63 pays no
    Krankengeld from the month of the claim on, though its five months would run past it."""
    claim = date(2040, 1, 1)
    early = Scenario.model_validate(
        {"name": "t", "phases": phases((START, "work"), (claim, "retired"))}
    )
    r = run([SALARY_ROW, PENSION], at=add_months(claim, -2), scenario=early, tax=GKV)
    assert not booked(r, KRANKENGELD, SOURCE)[months_between(START, claim) :].any()


def test_a_scenario_forces_an_onset_without_the_block_of_the_plan(data: Path) -> None:
    """`overrides.disability.at` on a plan without the block takes the default chances, so a
    what-if needs no more than the month."""
    (data / "scenarios" / "disabled.yaml").write_text(
        "name: disabled\nextends: base\noverrides:\n  disability: {at: 2030-01-01}\n"
    )
    spec = loader.load_plan(data, data / "scenarios" / "disabled.yaml").assumptions.disability
    assert spec is not None
    assert spec.at == date(2030, 1, 1)
    assert spec.hazard == list(DEFAULT_HAZARD)


def test_the_tax_year_sets_the_months_before_the_em_rente(
    later_tax_year: Callable[..., int],
) -> None:
    """A year file with a later start of the EM-Rente reaches the engine."""
    year = later_tax_year(em_start_months=10)
    rente = pension(run([SALARY_ROW, PENSION], tax={"year": year}))
    assert not rente[: M0 + 10].any()
    assert rente[M0 + 10] > 0
