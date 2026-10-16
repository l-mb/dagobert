"""The social insurance of a month (SGB III, IV, V, VI, XI) under a `TaxYear`: the SV of a salary
and of a business, the KV and PV of the GKV, the PKV subsidies, the salary conversion of a bAV, the
pension, the Erwerbsminderung and ALG1. Array-native, as `tax`: floats in, float arrays out."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
from numpy.typing import NDArray

from dagobert.model.assumptions import Person
from dagobert.model.taxes import TaxOptions
from dagobert.result import FloatArray
from dagobert.tax import Num, TaxYear, floats, werbungskosten, withholding_with_bonus, year_tax


def kv_member_half(opts: TaxOptions, ty: TaxYear) -> float:
    """The share of a GKV member in the KV on a salary or a pension: half of the general rate
    and half of the Zusatzbeitrag of the own Kasse (§242, §247, §249, §249a SGB V)."""
    return ty.kv_rate + kv_zusatz(opts, ty) / 2


def kv_zusatz(opts: TaxOptions, ty: TaxYear) -> float:
    """The Zusatzbeitrag of the member's Kasse (§242 Abs. 1 SGB V): `kv_zusatz` of the options,
    else the average of the year (§242a)."""
    return 2 * ty.kv_zusatz_half if opts.kv_zusatz is None else opts.kv_zusatz


def pv_rate(base: float, person: Person, month: date, ty: TaxYear) -> float:
    """The PV rate of a member in `month`: `base` (the employee share, or the whole rate on a
    pension) plus the surcharge for the childless up to the first birth, or less 0.25 points for
    each child under 25 from the second to the fifth (§55 Abs. 3 SGB XI). The member bears both
    alone."""
    if not person.parent(month):
        return base + ty.pv_kinderlos_zuschlag
    young = person.children_under(ty.pv_child_age, month)
    return base - min(ty.pv_child_discount * max(young - 1, 0), ty.pv_child_discount_max)


@dataclass(frozen=True)
class SVResult:
    rv: FloatArray
    alv: FloatArray
    kv: FloatArray
    pv: FloatArray

    @property
    def total(self) -> FloatArray:
        return floats(self.rv + self.alv + self.kv + self.pv)


def sv_employee(
    gross_month: Num, opts: TaxOptions, person: Person, month: date, ty: TaxYear
) -> SVResult:
    """SV of a month's gross, each part capped at its monthly BBG."""
    bases = (ty.rv_base(gross_month), np.minimum(floats(gross_month), ty.kv_pv_bbg_month))
    return sv_on(bases, opts, person, month, ty)


def sv_on(
    bases: tuple[Num, Num], opts: TaxOptions, person: Person, month: date, ty: TaxYear
) -> SVResult:
    """SV on the contributory bases of RV and ALV, and of KV and PV (none in a month of the
    PKV)."""
    rv_alv, kv_pv = floats(bases[0]), floats(bases[1])
    rv, alv = floats(rv_alv * ty.rv_rate), floats(rv_alv * ty.alv_rate)
    if opts.pkv_in(month):
        return SVResult(rv, alv, np.zeros_like(rv), np.zeros_like(rv))
    return SVResult(
        rv,
        alv,
        floats(kv_pv * kv_member_half(opts, ty)),
        floats(kv_pv * pv_rate(ty.pv_rate, person, month, ty)),
    )


def sv_bases(
    regular: Num, oneoff: Num, months: Num, used: tuple[Num, Num], ty: TaxYear
) -> tuple[FloatArray, FloatArray]:
    """Contributory bases of RV and of KV in a month (§23a SGB IV): the regular salary up to
    the monthly BBG, a one-off payment up to what the BBG of the `months` with a salary so far,
    this one included, leaves after the bases `used` before."""

    def base(bbg: float, before: Num) -> FloatArray:
        plain = np.minimum(floats(regular), bbg)
        room = np.maximum(floats(months) * bbg - before - plain, 0.0)
        return floats(plain + np.minimum(floats(oneoff), room))

    return base(ty.sv_bbg_month, used[0]), base(ty.kv_pv_bbg_month, used[1])


def employer_sv(gross_month: Num, opts: TaxOptions, month: date, ty: TaxYear) -> FloatArray:
    """The employer's share of the SV of a month's gross: RV and ALV on the RV base, and of a GKV
    member in `month` half of the KV with the Zusatzbeitrag of the Kasse and half of the PV rate on
    the KV base (§249 Abs. 1 SGB V, §58 Abs. 1 SGB XI). A PKV subsidy is no SV contribution."""
    gross = floats(gross_month)
    shares = ty.rv_base(gross) * (ty.rv_rate + ty.alv_rate)
    if opts.pkv_in(month):
        return floats(shares)
    kv_pv = np.minimum(gross, ty.kv_pv_bbg_month) * (kv_member_half(opts, ty) + ty.pv_rate)
    return floats(shares + kv_pv)


def employer_pkv_subsidy(
    premium_month: Num, pflege_month: Num, kv_base: Num, ty: TaxYear
) -> FloatArray:
    """The employer's share of a PKV premium (§257 Abs. 2 S. 2 SGB V, §61 Abs. 2 S. 2 SGB XI):
    its GKV and SPV share of a contribution on `kv_base`, the month's contributory salary
    (`sv_bases`): half of the general rate plus half of the average Zusatzbeitrag, half of the
    PV rate (§58 Abs. 1). At most `employer_pkv_subsidy_cap_rate` of each part of the premium.
    `pflege_month` is the Pflegepflicht part of the premium."""
    base = floats(kv_base)
    return _premium_share(
        premium_month,
        pflege_month,
        ty.employer_pkv_subsidy_cap_rate,
        (ty.kv_half * base, ty.pv_rate * base),
    )


def agentur_pkv_subsidy(premium_month: Num, pflege_month: Num, ty: TaxYear) -> FloatArray:
    """The Agentur's share of a PKV premium during ALG1 (§174 SGB III), with the caps of
    `pkv_agentur`. `pflege_month` is the Pflegepflicht part of the premium."""
    s = ty.pkv_agentur
    return _premium_share(premium_month, pflege_month, s.rate, (s.cap_kv, s.cap_pv))


def _premium_share(
    premium_month: Num, pflege_month: Num, rate: float, caps: tuple[Num, Num]
) -> FloatArray:
    """`rate` of the KV and of the PV part of a PKV premium, each up to its cap."""
    pflege = floats(pflege_month)
    return floats(
        np.minimum(rate * (floats(premium_month) - pflege), caps[0])
        + np.minimum(rate * pflege, caps[1])
    )


@dataclass(frozen=True)
class Conversion:
    """An Entgeltumwandlung of a month: what the employer adds, and what the conversion takes off
    the gross of the income tax and of the SV. Below zero, the subsidy beyond the room joins it."""

    subsidy: FloatArray
    tax_free: FloatArray
    sv_free: FloatArray


def conversion(
    converted: Num,
    regular_month: Num,
    employer: Num,
    opts: TaxOptions,
    ty: TaxYear,
    *,
    month: date,
    subsidy: float | None,
) -> Conversion:
    """`converted` of the monthly salary `regular_month` into a Pensionsfonds, a Pensionskasse or
    a Direktversicherung (§1 Abs. 2 Nr. 3 BetrAVG). The employer adds the `subsidy` share of it,
    without one 15% as far as it saves SV: at most its shares on the drop of the bases in `month`
    (`employer_sv`, §1a Abs. 1a BetrAVG). Conversion and subsidy are free of income tax within a
    twelfth of 8% of the yearly BBG of the RV (§3 Nr. 63 S. 1 EStG; a twelfth a month, BMF Rn. 30)
    and of SV within a twelfth of 4% (§1 Abs. 1 S. 1 Nr. 9 SvEV), after what the `employer` pays
    in the month already, which fills both first (BMF Rn. 31; SvEV: "insgesamt"). What lies
    beyond stays in the gross. The saving counts the conversion within the room alone: a subsidy
    that runs beyond it saves a little less than counted."""
    c, paid = floats(converted), floats(employer)
    tax_room = np.maximum(ty.bav_tax_free_share * ty.sv_bbg_month - paid, 0.0)
    sv_room = np.maximum(ty.bav_sv_free_share * ty.sv_bbg_month - paid, 0.0)
    if subsidy is None:
        gross = floats(regular_month)
        saved = employer_sv(gross, opts, month, ty) - employer_sv(
            gross - np.minimum(c, sv_room), opts, month, ty
        )
        added = np.minimum(ty.bav_subsidy * c, saved)
    else:
        added = subsidy * c
    return Conversion(
        floats(added),
        floats(np.minimum(c, tax_room - added)),
        floats(np.minimum(c, sv_room - added)),
    )


def conversions(
    converted: Sequence[tuple[Num, float | None]],
    regular_month: Num,
    employer: Num,
    opts: TaxOptions,
    ty: TaxYear,
    *,
    month: date,
) -> list[Conversion]:
    """The conversions of a month in turn, each with the share of its subsidy (`conversion`): one
    takes the rooms that the `employer`'s contributions and the conversions before it with their
    subsidies leave, and saves on the salary that their parts free of SV leave."""
    out: list[Conversion] = []
    gross, paid = floats(regular_month), floats(employer)
    for amount, subsidy in converted:
        conv = conversion(amount, gross, paid, opts, ty, month=month, subsidy=subsidy)
        gross, paid = gross - conv.sv_free, paid + amount + conv.subsidy
        out.append(conv)
    return out


def kv_compulsory(
    income: tuple[Num, Num],
    opts: TaxOptions,
    person: Person,
    month: date,
    ty: TaxYear,
    *,
    room: Num,
) -> tuple[FloatArray, FloatArray]:
    """KV and PV of a Pflichtmitglied (a salary, ALG1, the KVdR) on its `income`: the
    Versorgungsbezüge (§229 Abs. 1 S. 1 Nr. 5 SGB V: a company pension) and the Arbeitseinkommen
    beside a pension or Versorgungsbezüge (§226 Abs. 1 Nr. 4, §232a Abs. 3, §237 Nr. 3), in the
    `room` that the salary or the pension leaves below the KV-BBG (§§230, 238), the member alone
    (§250 Abs. 1): the general rate (§248 S. 1) plus the Zusatzbeitrag of the Kasse (§242 Abs. 1,
    `kv_zusatz`) and the whole PV rate. Nothing while both stay within a twentieth of the
    Bezugsgröße, a Freigrenze (§226 Abs. 2 S. 1, by §232a Abs. 3 and §237 S. 4 also for ALG1 and
    the KVdR, by §57 Abs. 1 SGB XI also for the PV); above it the KV takes a Freibetrag of that
    size off the company pension (§226 Abs. 2 S. 2), the PV not (§57 Abs. 1 names S. 1 and 3
    only)."""
    v, e = floats(income[0]), np.maximum(floats(income[1]), 0.0)
    free = ty.versorgung_freibetrag
    over = v + e > free
    kv = np.where(over, np.minimum(v - np.minimum(v, free) + e, room), 0.0)
    pv = np.where(over, np.minimum(v + e, room), 0.0)
    return (
        floats(kv * (2 * ty.kv_rate + kv_zusatz(opts, ty))),
        floats(pv * pv_rate(2 * ty.pv_rate, person, month, ty)),
    )


def kv_voluntary(
    income: tuple[Num, Num, Num],
    opts: TaxOptions,
    person: Person,
    month: date,
    ty: TaxYear,
    *,
    krankengeld: bool | NDArray[np.bool_] = False,
) -> tuple[FloatArray, FloatArray]:
    """KV and PV of a freiwilliges Mitglied in a month (§240 SGB V, §57 Abs. 4 SGB XI), the member
    alone (§250 Abs. 2). `income`: the pension, the Versorgungsbezüge and the rest (profit, other
    income, capital), each at least 0 (no offset of a loss across kinds), in this order up to the
    KV-BBG, all together at least `kv_min_base` (§240 Abs. 4 S. 1, §238a; BVSzGs §7 Abs. 3). No
    Freibetrag (BVSzGs §3 Abs. 4: §226 Abs. 2 does not hold). The general rate on the
    Versorgungsbezüge (§248 by §240 Abs. 2 S. 5), the reduced one on the rest (§243, no
    Krankengeld) or with `krankengeld` the general one (§44 Abs. 2 Nr. 2), each plus the
    Zusatzbeitrag of the Kasse (§242 Abs. 1, `kv_zusatz`); the whole PV rate. The pension pays apart
    (`pension_net_month`): the general rate and the Zusatzbeitrag on it (§247) less the subsidy of
    the DRV (§106 Abs. 2 SGB VI: half of both) is its KVdR share."""
    pension, versorgung, rest = (np.maximum(floats(x), 0.0) for x in income)
    total = np.clip(pension + versorgung + rest, ty.kv_min_base, ty.kv_pv_bbg_month)
    base = np.maximum(total - pension, 0.0)
    v = np.minimum(versorgung, base)
    general, reduced = (2 * rate + kv_zusatz(opts, ty) for rate in (ty.kv_rate, ty.kv_rate_reduced))
    kv = v * general + (base - v) * np.where(krankengeld, general, reduced)
    return floats(kv), floats(base * pv_rate(2 * ty.pv_rate, person, month, ty))


def rv_self_employed(
    profit_month: Num, opts: TaxOptions, month: date, ty: TaxYear, *, founded: date
) -> FloatArray:
    """The GRV of a self-employed month (`opts.self_employed.rv`, §165 Abs. 1 SGB VI), the member
    alone: on the Bezugsgröße, `rv_founding_share` of it up to the end of the
    `rv_founding_years`-th calendar year after the `founded` one (S. 2), or on the profit between
    the Geringfügigkeitsgrenze and the BBG. Its KV and PV: `kv_voluntary`."""
    profit = floats(profit_month)
    match opts.self_employed.rv:
        case "regular":
            early = month.year <= founded.year + ty.rv_founding_years
            base = np.full_like(
                profit, ty.bezugsgroesse_month * (ty.rv_founding_share if early else 1)
            )
        case "income":
            base = np.clip(profit, ty.geringfuegigkeit_month, ty.sv_bbg_month)
        case _:
            base = np.zeros_like(profit)
    return floats(base * ty.rv_rate_total)


def pension_points(gross_month: Num, ty: TaxYear) -> FloatArray:
    """Rentenpunkte earned in one month: BBG-capped gross over the Durchschnittsentgelt."""
    return floats(ty.rv_base(gross_month) / ty.durchschnittsentgelt)


def voluntary_points(contribution_month: Num, ty: TaxYear) -> FloatArray:
    """Rentenpunkte bought with a voluntary monthly contribution."""
    return floats(floats(contribution_month) / (ty.rv_rate_total * ty.durchschnittsentgelt))


def em_factor(age: Num, ty: TaxYear) -> FloatArray:
    """The Zugangsfaktor of an EM-Rente that starts at `age` (§77 Abs. 2 S. 1 Nr. 3, S. 2 SGB VI):
    `abschlag_per_month` less for each month before `em_reference_age`, counted from
    `em_floor_age` at the earliest. A full Erwerbsminderung: the Rentenartfaktor is 1."""
    early = np.maximum(ty.em_reference_age - np.maximum(floats(age), ty.em_floor_age), 0.0)
    return floats(1.0 - 12 * early * ty.abschlag_per_month)


@dataclass(frozen=True)
class Krankengeld:
    """The Krankengeld of a month before the member's shares, and those shares of RV, ALV and PV."""

    gross: FloatArray
    rv: FloatArray
    alv: FloatArray
    pv: FloatArray


def krankengeld_month(
    base: Num,
    opts: TaxOptions,
    person: Person,
    month: date,
    ty: TaxYear,
    *,
    church: float,
    employed: bool,
) -> Krankengeld:
    """The Krankengeld of the GKV for a month (§47 SGB V): `krankengeld_rate` of the regular `base`
    up to the KV-BBG (Abs. 6). An `employed` member's base is the Arbeitsentgelt, the Krankengeld at
    most `krankengeld_net_cap` of its net after the Lohnsteuer with Soli and the church tax (Abs.
    1). The Kasse pays RV, ALV and PV on 80% of the base (§166 Abs. 1 Nr. 2 SGB VI, §345 Nr. 5
    SGB III, §57 Abs. 2 SGB XI); the member bears half of them only "soweit sie auf die Leistung
    entfallen", so half the rates on the Krankengeld paid, the Kasse the rest (§170 Abs. 1 Nr. 2 a
    SGB VI, §347 Nr. 5 SGB III, §59 Abs. 2, 5 SGB XI: the PV surcharge too). A self-employed
    member's base is the last Arbeitseinkommen, without the cap (Abs. 4), and only the RV of a
    business in the GRV before (§3 S. 1 Nr. 3 SGB VI); its PV (§57 Abs. 2 SGB XI) is left out."""
    b = floats(base)
    gross = ty.krankengeld_rate * np.minimum(b, ty.kv_pv_bbg_month)
    if not employed:
        rv = gross * ty.rv_rate if opts.self_employed.rv != "none" else np.zeros_like(gross)
        return Krankengeld(floats(gross), floats(rv), np.zeros_like(gross), np.zeros_like(gross))
    paid = sv_employee(b, opts, person, month, ty)
    net = b - paid.total - withholding_with_bonus(b, 0.0, (paid, paid), 0.0, ty, church=church)
    gross = np.minimum(gross, ty.krankengeld_net_cap * np.maximum(net, 0.0))
    return Krankengeld(
        floats(gross),
        floats(gross * ty.rv_rate),
        floats(gross * ty.alv_rate),
        floats(gross * pv_rate(ty.pv_rate, person, month, ty)),
    )


def pension_claim(age: float, years: float, ty: TaxYear) -> float | None:
    """Factor on the pension for a claim at `age` with `years` of Versicherungszeit.

    None when no claim is possible yet. Before the Regelaltersgrenze the pension needs
    35 years (0.3% Abschlag per month) or 45 years from 65 (no Abschlag). After the
    Regelaltersgrenze each month adds 0.5%."""
    if age >= ty.regelaltersgrenze:
        return 1.0 + (age - ty.regelaltersgrenze) * 12 * ty.zuschlag_per_month
    if years >= ty.besonders_years and age >= ty.besonders_age:
        return 1.0
    if years >= ty.langjaehrig_years and age >= ty.langjaehrig_age:
        return 1.0 - (ty.regelaltersgrenze - age) * 12 * ty.abschlag_per_month
    return None


@dataclass(frozen=True)
class PensionMonth:
    gross: FloatArray
    kvdr: FloatArray
    pv: FloatArray
    pkv_subsidy: FloatArray


def pension_net_month(
    gross_month: Num,
    opts: TaxOptions,
    person: Person,
    month: date,
    ty: TaxYear,
    *,
    premium_month: Num,
) -> PensionMonth:
    """KVdR and PV of a GKV member on a pension (half of the general rate and of the Zusatzbeitrag
    of the Kasse, §247, §249a SGB V), or in a month of the PKV the subsidy of the DRV: half of the
    general KV rate plus the average Zusatzbeitrag (§106 Abs. 3 SGB VI, 8.75% in 2026), at most
    half of the premium."""
    gross = floats(gross_month)
    zero = np.zeros_like(gross)
    if opts.pkv_in(month):
        subsidy = np.minimum(ty.kv_half * gross, ty.pension_pkv_subsidy_cap_rate * premium_month)
        return PensionMonth(gross, zero, zero, floats(subsidy))
    return PensionMonth(
        gross,
        floats(gross * kv_member_half(opts, ty)),
        floats(gross * pv_rate(ty.pv_rente_rate, person, month, ty)),
        zero,
    )


def alg1_months(age_at_start: float, ty: TaxYear) -> int:
    """The months of ALG1 by the age at its start (§147 SGB III)."""
    return ty.alg1_months[max(age for age in ty.alg1_months if age <= age_at_start)]


def alg1_month(last_gross_month: Num, ty: TaxYear, *, child: bool) -> FloatArray:
    """ALG1 of a full month (§§149, 151, 153, 154 SGB III): 60% of the Leistungsentgelt of 30
    days, 67% with a `child` of §32 Abs. 1, 3 to 5 EStG in the first month of the claim. That is
    the salary per day (the BBG caps it), less 20% for the SV and less the Lohnsteuer and Soli of
    the day in Steuerklasse I: 1/360 of those of the year (§39b Abs. 2 S. 9 EStG), with the
    Vorsorgepauschale of a GKV member at the reduced KV rate and the PV rate without surcharge or
    discount (§153 Abs. 1 S. 4), no church tax (S. 2). The Selbstberechnungsprogramm of the
    Bundesagentur gives the same to about 1 € a month."""
    rate = ty.alg1_rate_kinder if child else ty.alg1_rate_base
    day = ty.rv_base(last_gross_month) * 12 / ty.alg1_year_days
    wage = day * ty.lohnsteuer_year_days
    kv_pv = (ty.kv_rate_reduced + ty.kv_zusatz_half + ty.pv_rate) * np.minimum(
        wage, 12 * ty.kv_pv_bbg_month
    )
    alv = np.minimum(ty.alv_rate * wage, np.maximum(ty.vorsorge_alv_cap - kv_pv, 0.0))
    zve = (
        wage
        - werbungskosten(wage, 0.0, ty, 0.0)  # the Pauschbetrag, never the own costs (§153)
        - ty.sonderausgaben_pauschbetrag
        - (ty.rv_rate * wage + kv_pv + alv)
    )
    net = (
        day * (1 - ty.alg1_pauschal_abzug) - year_tax(zve, ty, church=0.0) / ty.lohnsteuer_year_days
    )
    return floats(ty.alg1_month_days * rate * net)
