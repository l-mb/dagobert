"""German income and capital tax rules of a `TaxYear`, the legal constants of a year (the social
insurance: `sv`). Array-native: floats in, float arrays out."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING

import numpy as np
import yaml
from numpy.typing import ArrayLike
from pydantic import field_validator

from dagobert.model.base import Strict
from dagobert.model.taxes import TAX_DIR, Land, Relation, TaxOptions
from dagobert.result import FloatArray

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dagobert.sv import SVResult

Num = float | FloatArray


def floats(value: object) -> FloatArray:
    """`value` as an array of floats."""
    return np.asarray(value, dtype=np.float64)


class Subsidy(Strict):
    """A share of a PKV premium paid by someone else. The Kranken- and the
    Pflegepflichtversicherung have a monthly cap each."""

    rate: float
    cap_kv: float
    cap_pv: float


class HaushaltCredit(Strict):
    """The credit of §35a EStG: a share of the labour costs, a yearly cap per kind."""

    rate: float
    household: float  # haushaltsnahe Dienstleistungen (Abs. 2 S. 1)
    craftsman: float  # Handwerkerleistungen (Abs. 3 S. 1)


class Haerte(Strict):
    """The Härteausgleich of §19 Abs. 3 ErbStG: the tax over a limit takes at most `below` of the
    excess at a rate up to `rate`, `above` at a higher one."""

    rate: float
    below: float
    above: float


class TaxYear(Strict):
    """The legal constants of one year, from `dagobert/data/tax/<year>.yaml`, where the comments
    name their sources."""

    year: int
    grundfreibetrag: float
    zone2_end: float
    zone3_end: float
    zone4_end: float
    zone2_a: float
    zone2_b: float
    zone3_a: float
    zone3_b: float
    zone3_c: float
    zone4_rate: float
    zone4_sub: float
    zone5_rate: float
    zone5_sub: float
    soli_rate: float
    soli_freigrenze: float
    soli_milderung_rate: float
    kirchensteuer: dict[Land, float]
    abgeltungsteuer_rate: float
    private_sale_months: int
    property_sale_months: int
    private_sale_freigrenze: float
    rv_rate: float
    alv_rate: float
    sv_bbg_month: float
    kv_rate: float
    kv_rate_reduced: float
    kv_zusatz_half: float
    pv_rate: float
    pv_kinderlos_zuschlag: float
    pv_child_discount: float
    pv_child_discount_max: float
    pv_child_age: int
    kv_pv_bbg_month: float
    werbungskosten_pauschale: float
    sonderausgaben_pauschbetrag: float
    childcare_share: float
    childcare_max: float
    childcare_age: int
    donation_share: float
    haushalt_credit: HaushaltCredit
    vorsorge_hoechstbetrag: float
    vorsorge_alv_cap: float
    pension_pauschbetrag: float
    employer_pkv_subsidy_cap_rate: float
    pkv_agentur: Subsidy
    bav_tax_free_share: float
    bav_sv_free_share: float
    bav_subsidy: float
    alg1_pauschal_abzug: float
    alg1_rate_base: float
    alg1_rate_kinder: float
    alg1_rv_share: float
    alg1_months: dict[int, int]
    alg1_year_days: int
    alg1_month_days: int
    lohnsteuer_year_days: int
    durchschnittsentgelt: float
    rentenwert: float  # the euros of a point a month from July (the quick start's `point_value`)
    regelaltersgrenze: float
    langjaehrig_age: float
    langjaehrig_years: float
    besonders_age: float
    besonders_years: float
    abschlag_per_month: float
    zuschlag_per_month: float
    pension_share: float
    pension_share_step: float
    pension_share_start_year: int
    pension_share_step_since: int
    efzg_months: int
    krankengeld_rate: float
    krankengeld_net_cap: float
    em_start_months: int
    em_wartezeit_months: int
    em_pflicht_months: int
    em_window_months: int
    em_reference_age: float
    em_floor_age: float
    zurechnung_end: dict[int, int]
    ertragsanteil_by_years: dict[int, float]
    pension_pkv_subsidy_cap_rate: float
    pv_rente_rate: float
    basiszins: float
    basisertrag_share: float
    pkv_basis_share: float
    av_first: float
    av_first_rate: float
    av_rate: float
    av_subsidized: float
    av_min_contribution: float
    av_kinderzulage: float
    kindergeld_month: float
    kinderfreibetrag: float
    betreuungsfreibetrag: float
    entlastungsbetrag: float
    entlastungsbetrag_more: float
    kez_months: int
    kez_points_month: float
    beruecksichtigung_age: int
    bezugsgroesse_month: float
    geringfuegigkeit_month: float
    rv_founding_years: int
    rv_founding_share: float
    gewst_freibetrag: float
    gewst_messzahl: float
    gewst_credit_factor: float
    versorgung_months: int
    kv_capital_werbungskosten: float
    gkv_return_age: float
    erbst_freibetrag: dict[Relation, float]
    erbst_klasse: dict[Relation, int]
    erbst_brackets: list[float]
    erbst_rates: dict[int, list[float]]
    erbst_haerte: Haerte
    erbst_erbfallkosten: float
    erbst_rounding: float

    @field_validator("kirchensteuer")
    @classmethod
    def _every_land(cls, rates: dict[Land, float]) -> dict[Land, float]:
        if missing := [land for land in Land if land not in rates]:
            msg = f"no church tax rate of {', '.join(missing)}"
            raise ValueError(msg)
        return rates

    @field_validator("erbst_freibetrag", "erbst_klasse")
    @classmethod
    def _every_relation[T](cls, by: dict[Relation, T]) -> dict[Relation, T]:
        if missing := [relation for relation in Relation if relation not in by]:
            msg = f"no value of {', '.join(missing)}"
            raise ValueError(msg)
        return by

    @property
    def kv_min_base(self) -> float:
        """The least monthly base of a freiwillige GKV member: the 90th part of the monthly
        Bezugsgröße per day, 30 days (§240 Abs. 4 S. 1 SGB V)."""
        return self.bezugsgroesse_month / 3

    @property
    def versorgung_freibetrag(self) -> float:
        """The Freigrenze of the Versorgungsbezüge and the Arbeitseinkommen of a Pflichtmitglied,
        and the Freibetrag of the KV on a company pension: a twentieth of the monthly Bezugsgröße
        (§226 Abs. 2 S. 1, 2 SGB V)."""
        return self.bezugsgroesse_month / 20

    @property
    def kv_half(self) -> float:
        """Half of the general KV rate plus half of the average Zusatzbeitrag: the share of the
        employer in the PKV subsidy (§257 Abs. 2 SGB V), and of the DRV (§106 SGB VI)."""
        return self.kv_rate + self.kv_zusatz_half

    @property
    def rv_rate_total(self) -> float:
        return 2 * self.rv_rate

    def rv_base(self, gross_month: Num) -> FloatArray:
        """The part of a monthly gross below the BBG of RV and ALV."""
        return np.minimum(floats(gross_month), self.sv_bbg_month)

    def zurechnung_months(self, year: int) -> int:
        """The end of the Zurechnungszeit in months of age for an EM-Rente that starts in `year`
        (§253a Abs. 3 SGB VI): the row of the year, the last one for a later year, the first for
        an earlier one (the table starts in 2020)."""
        rows = self.zurechnung_end
        return rows[max((y for y in rows if y <= year), default=min(rows))]


@cache
def for_year(year: int) -> TaxYear:
    path = TAX_DIR / f"{year}.yaml"
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in TAX_DIR.glob("*.yaml")))
        msg = f"no tax constants for {year}, only for {known}"
        raise ValueError(msg)
    ty = TaxYear.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if ty.year != year:
        msg = f"{path}: holds the year {ty.year}"
        raise ValueError(msg)
    return ty


def church_rate(opts: TaxOptions, ty: TaxYear) -> float:
    """The church tax as a share of the income tax: the rate of the Land, 0 outside a church
    (§51a EStG with the Kirchensteuergesetze)."""
    return ty.kirchensteuer[opts.land] if opts.church and opts.land else 0.0


def flat_rate(church: float, ty: TaxYear) -> float:
    """The Abgeltungsteuer with Soli and church tax on a euro of capital income. With the church
    tax the Abgeltungsteuer falls by a quarter of it (§32d Abs. 1 S. 3, 4 EStG: e / (4 + k)), so
    24.45% at 9% and 24.51% at 8%, 27.99% and 27.82% in all."""
    rate = ty.abgeltungsteuer_rate / (1 + ty.abgeltungsteuer_rate * church)
    return rate * (1 + ty.soli_rate + church)


def income_tax(zve: Num, ty: TaxYear) -> FloatArray:
    x = np.maximum(np.floor(floats(zve)), 0.0)
    y = (x - ty.grundfreibetrag) / 10000
    z = (x - ty.zone2_end) / 10000
    tax = np.select(
        [x <= ty.grundfreibetrag, x <= ty.zone2_end, x <= ty.zone3_end, x <= ty.zone4_end],
        [
            np.zeros_like(x),
            (ty.zone2_a * y + ty.zone2_b) * y,
            (ty.zone3_a * z + ty.zone3_b) * z + ty.zone3_c,
            ty.zone4_rate * x - ty.zone4_sub,
        ],
        default=ty.zone5_rate * x - ty.zone5_sub,
    )
    return floats(np.floor(tax))


def soli(tax: Num, ty: TaxYear) -> FloatArray:
    t = floats(tax)
    milderung = np.minimum(ty.soli_milderung_rate * (t - ty.soli_freigrenze), ty.soli_rate * t)
    return floats(np.where(t <= ty.soli_freigrenze, 0.0, milderung))


def _monthly_tax(zve_year: Num, ty: TaxYear, *, church: float) -> FloatArray:
    """Income tax, Soli and church tax on a year's zvE, spread over its twelve months."""
    return floats(year_tax(zve_year, ty, church=church) / 12)


def progression(zve: Num, alg1: Num, ty: TaxYear) -> FloatArray:
    """§32b EStG: the rate of zvE plus ALG1, applied to the zvE alone."""
    z, a = floats(zve), floats(alg1)
    rate = income_tax(z + a, ty) / np.maximum(z + a, 1.0)
    return floats(np.where(a > 0, rate * np.maximum(z, 0.0), income_tax(z, ty)))


def fuenftelregelung(zve: Num, severance: Num, ty: TaxYear, *, alg1: Num = 0.0) -> FloatArray:
    """§34 Abs. 1 EStG. ALG1 raises the rate in both steps and in the negative-zvE case
    (S. 3) joins the fifth in full (R 34.2 EStR, BFH IX R 23/11)."""
    z, s = floats(zve), floats(severance)
    base = progression(z, alg1, ty)
    regular = base + 5 * (progression(z + s / 5, alg1, ty) - base)
    negative = 5 * progression((z + s) / 5, alg1, ty)
    return floats(np.where((z < 0) & (z + s > 0), negative, regular))


def werbungskosten(salary_year: Num, pension_taxable: Num, ty: TaxYear, actual: Num) -> FloatArray:
    """§9a EStG: the Arbeitnehmer-Pauschbetrag on Arbeitslohn unless the `actual` work expenses
    are higher (S. 1 Nr. 1 a), and 102 EUR on the taxable pension (Nr. 3), each capped at the
    income it belongs to: costs beyond the Arbeitslohn would be a loss, left out. Other income
    gets neither."""
    work = np.maximum(ty.werbungskosten_pauschale, floats(actual))
    return floats(
        np.clip(floats(salary_year), 0.0, work)
        + np.clip(floats(pension_taxable), 0.0, ty.pension_pauschbetrag)
    )


def taxable_income(
    income_year: Num, werbungskosten_year: Num, rv_paid: Num, health_deductible: Num
) -> FloatArray:
    """zvE, which may be negative: a loss carries into the Fünftelregelung (§34 Abs 1 S 3)."""
    return floats(floats(income_year) - werbungskosten_year - rv_paid - health_deductible)


def _zve_year(gross_month: Num, sv: SVResult, health_month: Num, ty: TaxYear) -> FloatArray:
    """The zvE of the Lohnsteuer of a year: the Arbeitnehmer- and the Sonderausgaben-Pauschbetrag
    (§39b Abs. 2 S. 5 Nr. 1, 2 EStG, never the own costs) and the Vorsorgepauschale (Nr. 3)."""
    gross = floats(gross_month)
    return taxable_income(
        gross * 12 - ty.sonderausgaben_pauschbetrag,
        werbungskosten(gross * 12, 0.0, ty, 0.0),
        sv.rv * 12,
        (sv.kv + sv.pv + floats(health_month)) * 12,
    )


def year_tax(zve: Num, ty: TaxYear, *, church: float) -> FloatArray:
    """Income tax plus Soli and the `church` rate of it (§51a EStG) of a year."""
    t = income_tax(zve, ty)
    return floats(t + soli(t, ty) + church * t)


def withholding_oneoff(base: Num, amount: Num, ty: TaxYear, *, church: float) -> FloatArray:
    """Lohnsteuer, Soli and church tax on a sonstiger Bezug (§39b Abs. 3 EStG): the tax of the
    year with it less the tax without it, on top of `base`. A bonus and the lump of a profit
    take the yearly zvE of the regular pay; a severance takes the salary gross of the year so
    far, a stand-in: the December settlement corrects the year. An Entschädigung too: since 2025
    only the assessment applies the Fünftelregelung (§39b Abs. 3 S. 9 repealed)."""
    base = floats(base)
    return floats(
        year_tax(base + floats(amount), ty, church=church) - year_tax(base, ty, church=church)
    )


def withholding_with_bonus(
    regular_month: Num,
    bonus: Num,
    sv: tuple[SVResult, SVResult],
    health_month: Num,
    ty: TaxYear,
    *,
    church: float,
) -> FloatArray:
    """Withholding of a month: the regular salary as if paid all year, a `bonus` on top as a
    sonstiger Bezug less its own SV. `sv` holds the SV of the whole month and of the regular
    salary alone."""
    total, regular = sv
    base = _zve_year(regular_month, regular, health_month, ty)
    extra = (
        floats(bonus) - (total.rv - regular.rv) - (total.kv + total.pv - regular.kv - regular.pv)
    )
    return floats(
        _monthly_tax(base, ty, church=church) + withholding_oneoff(base, extra, ty, church=church)
    )


def profit_reserve(
    regular_month: Num, lump: Num, deductions_month: Num, ty: TaxYear, *, church: float
) -> FloatArray:
    """The monthly reserve for the Vorauszahlungen of a profit (§37 EStG, with those of the church
    tax, §51a Abs. 4): the tax of the regular monthly profit as if earned all year, less the SV
    and the deductible premium of the month, and on a payment every n months on top the tax of
    the year with it less without it. No Werbungskosten: the profit is after the business
    expenses. A loss reserves nothing."""
    base = 12 * (np.maximum(floats(regular_month), 0.0) - floats(deductions_month))
    lumps = np.maximum(floats(lump), 0.0)
    return floats(
        _monthly_tax(base, ty, church=church) + withholding_oneoff(base, lumps, ty, church=church)
    )


def trade_tax(profit_year: Num, hebesatz: float, ty: TaxYear) -> tuple[FloatArray, FloatArray]:
    """The Gewerbesteuer of the trade business of a natural person on the profit of its year: the
    Hebesatz on the Messbetrag, the Messzahl of the profit beyond the Freibetrag (§§11, 16 GewStG;
    no Hinzurechnungen, no rounding). Returns it and its credit against the income tax before the
    cap by the tariff tax: `gewst_credit_factor` times the Messbetrag, at most the Gewerbesteuer
    (§35 Abs. 1 S. 1 Nr. 1, S. 5 EStG)."""
    messbetrag = ty.gewst_messzahl * np.maximum(floats(profit_year) - ty.gewst_freibetrag, 0.0)
    gewst = hebesatz * messbetrag
    return floats(gewst), floats(np.minimum(ty.gewst_credit_factor * messbetrag, gewst))


@dataclass(frozen=True)
class ChildYear:
    """A child in the settlement of a year (§31, §32 Abs. 6 EStG): the months of the year in the
    run in which it counts, and whether you take the full allowances (S. 6)."""

    months: int
    full: bool = False

    def allowances(self, ty: TaxYear) -> float:
        """The Kinderfreibetrag and the Betreuungsfreibetrag of its months (S. 1, 5), your half or
        both halves."""
        return self.months / 12 * (ty.kinderfreibetrag + ty.betreuungsfreibetrag) * self._share

    def kindergeld(self, ty: TaxYear) -> float:
        """The Kindergeld that the tax adds where the allowances win: the claim of its months, of
        a parent who takes half of the allowances half of it (§31 S. 4), whoever receives it."""
        return self.months * ty.kindergeld_month * self._share / 2

    @property
    def _share(self) -> float:
        return 2.0 if self.full else 1.0


def entlastungsbetrag(counting: Sequence[int], ty: TaxYear) -> FloatArray:
    """§24b EStG of a single parent: per month of `counting` (the children that count in it) with
    a child a twelfth of the Entlastungsbetrag and of its increase for each further child (Abs. 2,
    4)."""
    return floats(
        sum(ty.entlastungsbetrag + ty.entlastungsbetrag_more * (n - 1) for n in counting if n) / 12
    )


@dataclass(frozen=True)
class YearIncome:
    salary_gross: Num = 0.0
    severance: Num = 0.0
    # the Lohnersatzleistungen under the Progressionsvorbehalt (§32b Abs. 1 S. 1 Nr. 1 a, b EStG):
    # ALG1 and the gross Krankengeld, before the member's shares of the SV
    alg1: Num = 0.0
    pension_taxable: Num = 0.0  # already reduced by `pension_share` or the Rentenfreibetrag
    other_taxable: Num = 0.0
    rent: Num = 0.0  # the net rent of the let properties (§21 EStG), part of `other_taxable`
    werbungskosten: Num = 0.0  # the work expenses of the salary months, when above the Pauschbetrag
    rv_paid: Num = 0.0  # own GRV share, voluntary contributions and Basisrente premiums
    rv_employer: Num = 0.0  # employer GRV share, counts against the Höchstbetrag only
    health_deductible: Num = 0.0
    capital_income: Num = 0.0  # taxable capital income after Teilfreistellung and Pauschbetrag
    capital_tax_paid: Num = 0.0  # Abgeltungsteuer already paid on it
    av_deduction: Num = 0.0  # Sonderausgabe of the Altersvorsorgedepot
    av_zulage: Num = 0.0  # its Zulage, which the tax takes back when the deduction applies
    church_paid: Num = 0.0  # church tax paid in the year, a Sonderausgabe; below 0 a refund
    trade_income: Num = 0.0  # the positive profits of the trade businesses, part of other_taxable
    trade_tax: Num = 0.0  # their Gewerbesteuer
    trade_credit: Num = 0.0  # its credit before the cap by the tariff tax (`trade_tax`)
    loss_carried: Num = 0.0  # the Verlustvortrag of the years before (§10d Abs. 2 EStG)
    donations: Num = 0.0  # Zuwendungen (§10b EStG)
    childcare: Num = 0.0  # the costs of the care of a child under 14 (§10 Abs. 1 Nr. 5)
    children: Num = 0.0  # the children under 14 in any month of the year
    # the children that count in the year (§32 EStG), oldest first: the check of §31
    child_years: tuple[ChildYear, ...] = ()
    entlastung: Num = 0.0  # the Entlastungsbetrag für Alleinerziehende (§24b)
    household: Num = 0.0  # haushaltsnahe Dienstleistungen (§35a Abs. 2), the labour costs
    craftsman: Num = 0.0  # Handwerkerleistungen (§35a Abs. 3), the labour costs


@dataclass(frozen=True)
class YearSettlement:
    tax: FloatArray  # the income tax after the credits of §35 and §35a, the Kindergeld added (§31)
    soli: FloatArray  # on the income tax with every child allowance (§3 Abs. 2 SolZG)
    church: FloatArray  # the same before the credit of §35 (§51a Abs. 2 S. 1, 3 EStG)
    trade_tax: FloatArray
    total: FloatArray  # the four
    refund: FloatArray  # Günstigerprüfung on flat-taxed capital income
    loss_left: FloatArray  # the Verlustvortrag into the next year
    credit: FloatArray  # the credits of §35 and §35a that came off the tariff tax


def health_deductible(basis: Num, subsidy: Num) -> FloatArray:
    """§10 Abs. 2 S. 1 Nr. 1 EStG, BFH IX R 43/13: a tax-free subsidy comes off the
    Basisabsicherung part of the premium in full, not pro rata."""
    return floats(np.maximum(floats(basis) - subsidy, 0.0))


def av_zulage(contribution: Num, children: Num, ty: TaxYear) -> FloatArray:
    """The Zulage of the Altersvorsorgedepots on a year's own contributions of the person, once
    whatever the number of depots (§84 S. 1 EStG): the Grundzulage and, from 2027, the Kinderzulage
    of each of the `children`, the contributions up to `av_kinderzulage` (§85 Abs. 1 S. 1), none
    below the Mindesteigenbeitrag (§86)."""
    c = floats(contribution)
    zulage = (
        ty.av_first_rate * np.minimum(c, ty.av_first)
        + ty.av_rate * np.clip(c - ty.av_first, 0.0, ty.av_subsidized - ty.av_first)
        + np.minimum(c, ty.av_kinderzulage) * floats(children)
    )
    return floats(np.where(c >= ty.av_min_contribution, zulage, 0.0))


def av_deduction(contribution: Num, zulage: Num, ty: TaxYear) -> FloatArray:
    """Sonderausgabe of the Altersvorsorgedepot (§10a EStG): the contributions up to the
    subsidized amount plus the Zulage."""
    return floats(np.minimum(floats(contribution), ty.av_subsidized) + zulage)


def rv_deductible(rv_paid: Num, rv_employer: Num, ty: TaxYear) -> FloatArray:
    """§10 Abs. 1 Nr. 2, Abs. 3 EStG: own and employer GRV contributions plus Basisrente
    premiums count up to the Höchstbetrag; the employer share is then taken off again."""
    total = np.minimum(floats(rv_paid) + floats(rv_employer), ty.vorsorge_hoechstbetrag)
    return floats(np.maximum(total - floats(rv_employer), 0.0))


def pension_share(start_year: int, ty: TaxYear) -> float:
    """Besteuerungsanteil by the first pension year (§22 Nr. 1 S. 3 a aa EStG), in half-point
    steps from `pension_share_step_since`. Raises ValueError for a start before it."""
    if start_year < ty.pension_share_step_since:
        msg = f"no Besteuerungsanteil for a pension that started in {start_year}"
        raise ValueError(msg)
    return min(
        1.0,
        ty.pension_share + ty.pension_share_step * (start_year - ty.pension_share_start_year),
    )


def ertragsanteil(years: Num, ty: TaxYear) -> FloatArray:
    """The taxable share of an abgekürzte Leibrente, such as a private BU-Rente (§22 Nr. 1 S. 3 a
    bb S. 4 EStG, §55 Abs. 2 EStDV), by its Laufzeit from the start to the contractual end in
    years, rounded down (R 22.4 Abs. 4, 5 EStR), at least one, at most the last row of the table."""
    ends = np.array(sorted(ty.ertragsanteil_by_years))
    shares = np.array([ty.ertragsanteil_by_years[e] for e in ends])
    whole = np.clip(np.floor(floats(years)), 1, ends[-1])
    return floats(shares[np.searchsorted(ends, whole)])


def guenstigerpruefung(
    tax: Num,
    tax_with_capital: Num,
    capital_tax_paid: Num,
    ty: TaxYear,
    *,
    church: float,
    bases: tuple[Num, Num] | None = None,
) -> FloatArray:
    """Refund when taxing capital income at the tariff costs less than the flat tax paid, both
    with Soli and church tax (§32d Abs. 6 EStG: "einschließlich Zuschlagsteuern"). `bases`: the
    income tax without and with the capital income that those take, with every child allowance
    (§3 Abs. 2 SolZG, §51a Abs. 2 EStG); without children the tax itself."""
    t = floats(tax)
    delta = floats(tax_with_capital) - t
    base, base_capital = (t, t + delta) if bases is None else (floats(b) for b in bases)
    zuschlag = church * (base_capital - base) + soli(base_capital, ty) - soli(base, ty)
    return floats(np.maximum(floats(capital_tax_paid) - delta - zuschlag, 0.0))


def carried(gde: Num, pot: Num) -> tuple[FloatArray, FloatArray]:
    """§10d Abs. 2 EStG: the losses carried `pot` offset the Gesamtbetrag der Einkünfte `gde`
    before the Sonderausgaben, and a negative one joins them (Abs. 1 S. 1 with §2 Abs. 3). A
    negative zvE from the Sonderausgaben alone carries nothing. Returns the losses used and those
    left."""
    g, p = floats(gde), floats(pot)
    used = np.minimum(p, np.maximum(g, 0.0))
    return floats(used), floats(p - used + np.maximum(-g, 0.0))


def sonderausgaben(income: YearIncome, gde: Num, ty: TaxYear) -> FloatArray:
    """The Sonderausgaben beside the Vorsorgeaufwendungen: the church tax paid (§10 Abs. 1 Nr. 4
    EStG), the care of the children (Nr. 5: `childcare_share` of the costs, at most `childcare_max`
    a year per child under `childcare_age` in any month of the year, not in twelfths) and the
    donations (§10b Abs. 1 S. 1 Nr. 1: up to `donation_share` of the Gesamtbetrag der Einkünfte
    `gde`; the rest is lost, its carry a gap), at least the Sonderausgaben-Pauschbetrag (§10c).
    A church tax refund beyond what the year paid, a negative `church_paid`, is added after them
    (§10 Abs. 4b S. 3): it raises no Gesamtbetrag der Einkünfte, so the losses carried do not
    offset it (BFH IX R 34/17)."""
    church = floats(income.church_paid)
    care = np.minimum(
        ty.childcare_share * floats(income.childcare), ty.childcare_max * floats(income.children)
    )
    gifts = np.minimum(floats(income.donations), ty.donation_share * np.maximum(floats(gde), 0.0))
    paid = np.maximum(church, 0.0) + care + gifts
    return floats(np.maximum(ty.sonderausgaben_pauschbetrag, paid) + np.minimum(church, 0.0))


def haushalt_credit(household: Num, craftsman: Num, ty: TaxYear) -> FloatArray:
    """§35a Abs. 2 S. 1, Abs. 3 S. 1 EStG: `rate` of the labour costs of haushaltsnahe
    Dienstleistungen and of Handwerkerleistungen, each up to its cap. The law carries no rest."""
    c = ty.haushalt_credit
    return floats(
        np.minimum(c.rate * floats(household), c.household)
        + np.minimum(c.rate * floats(craftsman), c.craftsman)
    )


@dataclass(frozen=True)
class _Credits:
    trade: Num  # the credit of the Gewerbesteuer before its cap (§35 Abs. 1 S. 1 Nr. 1)
    share: Num  # its cap, a share of the tariff tax (§35 Abs. 1 S. 2)
    haushalt: Num  # the credit of §35a


def _credited(
    zve: Num, income: YearIncome, alg1: Num, credits: _Credits, ty: TaxYear
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """The tariff tax of `zve` (Progressionsvorbehalt, Fünftelregelung) less the credits of §35
    and §35a, at least 0, with the Sonderausgabe of §10a where that saves more than the Zulage,
    which then comes on top (§10a Abs. 2): the credits come off the tariff tax before the Zulage
    (§2 Abs. 6 S. 2 EStG, R 2 Abs. 2 EStR, BFH X R 11/21), each side floored on its own. Returns
    the tax, the base of the church tax (without the credit of §35, §51a Abs. 2 S. 3) and the
    credits taken."""
    sides = []
    for deduction, zulage in ((0.0, 0.0), (income.av_deduction, income.av_zulage)):
        tariff = fuenftelregelung(floats(zve) - deduction, income.severance, ty, alg1=alg1)
        trade = np.minimum(credits.trade, tariff * credits.share)
        after = np.maximum(tariff - trade - credits.haushalt, 0.0)
        base = np.maximum(tariff - credits.haushalt, 0.0) + zulage
        sides.append((after + zulage, base, tariff - after))
    plain, deduct = sides
    take = deduct[0] < plain[0]
    tax, base, credit = (floats(np.where(take, d, p)) for d, p in zip(deduct, plain, strict=True))
    return tax, base, credit


@dataclass(frozen=True)
class Zve:
    """The zvE of a year (§2 Abs. 5 EStG), below 0 too, and the Verlustvortrag into the next (§10d
    Abs. 2), without and with the flat-taxed capital income, which the Günstigerprüfung adds to the
    Einkünfte (§32d Abs. 6 S. 1); the ALG1 of the Progressionsvorbehalt."""

    regular: FloatArray
    left: FloatArray
    capital: FloatArray
    left_capital: FloatArray
    alg1: FloatArray


def zve(income: YearIncome, ty: TaxYear) -> Zve:
    """The Werbungskosten of the Arbeitslohn are the Pauschbetrag unless the work expenses are
    higher (`werbungskosten`), the Sonderausgaben `sonderausgaben`. The Entlastungsbetrag comes off
    the Summe der Einkünfte, at most down to 0: it makes no loss (§2 Abs. 3, §24b). The losses
    carried offset the Gesamtbetrag der Einkünfte before the Sonderausgaben (`carried`), before
    and after the capital income joins it. ALG1 raises the rate less the part of the Pauschbetrag
    that the Arbeitslohn leaves unused (§32b Abs. 2 S. 1 Nr. 1)."""
    salary = floats(income.salary_gross)
    work = werbungskosten(salary + floats(income.severance), 0.0, ty, income.werbungskosten)
    wk = work + werbungskosten(0.0, income.pension_taxable, ty, 0.0)
    regular = salary + floats(income.pension_taxable) + income.other_taxable
    summe = regular - wk + income.severance
    relief = np.minimum(income.entlastung, np.maximum(summe, 0.0))
    gde = summe - relief  # §2 Abs. 3
    used, left = carried(gde, income.loss_carried)
    z = taxable_income(
        regular - used - relief,
        wk,
        rv_deductible(income.rv_paid, income.rv_employer, ty),
        floats(income.health_deductible) + sonderausgaben(income, gde, ty),
    )
    with_capital = summe + income.capital_income
    relief_capital = np.minimum(income.entlastung, np.maximum(with_capital, 0.0))
    used_capital, left_capital = carried(with_capital - relief_capital, income.loss_carried)
    return Zve(
        z,
        left,
        floats(z + income.capital_income + used - used_capital + relief - relief_capital),
        left_capital,
        floats(np.maximum(income.alg1 - np.maximum(ty.werbungskosten_pauschale - work, 0.0), 0.0)),
    )


def harvest_room(
    income: YearIncome, pauschbetrag_left: Num, losses: Num, ty: TaxYear
) -> FloatArray:
    """The capital income after the Teilfreistellung that the year can realize free of tax and of
    a cost later: the Sparer-Pauschbetrag left (§20 Abs. 9 EStG) and the room up to the
    Grundfreibetrag, where the Günstigerprüfung refunds the flat tax in full (§32d Abs. 6; ALG1
    raises the rate there, §32b). None while the loss pot `losses` holds losses: they come off
    first (§20 Abs. 6) and would shelter the next sale in full, while a basis stepped up reaches
    each later sale by its share. The tariff part is closed in a year of the Fünftelregelung (§34)
    and while a Verlustvortrag is left with the capital income of the year (§10d): the harvest
    would use up losses that offset the tariff of a later year."""
    z = zve(income, ty)
    tariff = np.maximum(ty.grundfreibetrag - z.capital - z.alg1, 0.0)
    free = (floats(income.severance) <= 0) & (z.left_capital <= 0)
    room = pauschbetrag_left + np.where(free, tariff, 0.0)
    return floats(np.where(floats(losses) > 0, 0.0, room))


def year_settlement(income: YearIncome, ty: TaxYear, *, church: float) -> YearSettlement:
    """Capital income already taxed at the flat rate is re-checked at the tariff of the year
    (Günstigerprüfung, §32d Abs. 6 EStG: it joins the zvE, so ALG1 and a severance raise its
    rate as well) and the difference refunded. The zvE with and without it (`zve`). The credits
    of the Gewerbesteuer, at most the share of the trade income in the positive income (§35 Abs.
    1 S. 2: all of it stands in for the Einkünfte, a negative rent left out), and of §35a come off
    the tariff tax before the Soli (§3 Abs. 2 SolZG), the church tax takes it before §35 (§51a
    Abs. 2 S. 3; `_credited`). The Günstigerprüfung settles the losses carried on the Gesamtbetrag
    der Einkünfte with the capital income, which joins the Einkünfte (§32d Abs. 6 S. 1), and where
    it refunds, its losses left hold. The children: the check of §31 (`_with_children`) on both
    sides, the Soli and the church tax on the tax with every child allowance, whichever wins (§3
    Abs. 2 SolZG, §51a Abs. 2 S. 1 EStG)."""
    z = zve(income, ty)
    other, rent, trade = (
        floats(x) for x in (income.other_taxable, income.rent, income.trade_income)
    )
    positive = (
        floats(income.salary_gross)
        + income.severance
        + income.pension_taxable
        + np.maximum(rent, 0.0)
        + np.maximum(other - rent, trade)
    )
    credits = _Credits(
        income.trade_credit,
        trade / np.maximum(positive, 1.0),
        haushalt_credit(income.household, income.craftsman, ty),
    )
    tax, credit = _with_children(z.regular, income, z.alg1, credits, ty)
    with_capital, _ = _with_children(z.capital, income, z.alg1, credits, ty)
    allowances = sum(child.allowances(ty) for child in income.child_years)
    base, church_base, _ = _credited(z.regular - allowances, income, z.alg1, credits, ty)
    base_capital, _, _ = _credited(z.capital - allowances, income, z.alg1, credits, ty)
    soli_amt = soli(base, ty)
    church_amt = floats(church * church_base)
    trade_tax = floats(np.zeros_like(tax) + income.trade_tax)
    total = floats(tax + soli_amt + church_amt + trade_tax)
    refund = guenstigerpruefung(
        tax,
        with_capital,
        income.capital_tax_paid,
        ty,
        church=church,
        bases=(base, base_capital),
    )
    loss_left = floats(np.where(refund > 0, z.left_capital, z.left))
    return YearSettlement(tax, soli_amt, church_amt, trade_tax, total, refund, loss_left, credit)


def _with_children(
    zve: Num, income: YearIncome, alg1: Num, credits: _Credits, ty: TaxYear
) -> tuple[FloatArray, FloatArray]:
    """The income tax of `zve` after the check of §31 EStG, per child and oldest first (R 31 Abs.
    1 S. 3 EStR): the allowances of a child come off the zvE where the tariff with them, the route
    of the Altersvorsorgedepot that costs less on each side, and the Kindergeld claim of the child
    cost less than the tariff without them. The tax of the zvE that wins, after the credits
    (`_credited`), then adds the Kindergeld of the children whose allowances came off (§2 Abs. 6
    S. 3). Returns the tax and the credits taken."""
    sev, ded, zul = income.severance, income.av_deduction, income.av_zulage

    def tariff(z: FloatArray) -> FloatArray:
        plain = fuenftelregelung(z, sev, ty, alg1=alg1)
        return floats(np.minimum(plain, fuenftelregelung(z - ded, sev, ty, alg1=alg1) + zul))

    z = floats(zve)
    added = np.zeros_like(z)
    best = tariff(z)
    for child in income.child_years:
        lower = floats(z - child.allowances(ty))
        cheaper = tariff(lower)
        take = cheaper + child.kindergeld(ty) < best
        z, best = np.where(take, lower, z), np.where(take, cheaper, best)
        added = added + np.where(take, child.kindergeld(ty), 0.0)
    tax, _, credit = _credited(z, income, alg1, credits, ty)
    return floats(tax + added), credit


def vorabpauschale(held_jan: Num, growth: Num, ty: TaxYear) -> FloatArray:
    """§18 InvStG on the value in January of what was held all year: the Basisertrag, at most
    the growth of the year. `growth` is the relative change of the fund price."""
    jan = floats(held_jan)
    return floats(np.maximum(0.0, jan * np.minimum(ty.basisertrag_share * ty.basiszins, growth)))


def capital_gains_tax(
    gain: Num,
    pauschbetrag_left: Num,
    opts: TaxOptions,
    ty: TaxYear,
    *,
    losses: Num,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Abgeltungsteuer with Soli and church tax (`flat_rate`) on capital income, of a fund after
    its Teilfreistellung (§20 InvStG): the general loss pot offsets first, then the Pauschbetrag
    (§20 Abs. 6 and 9 EStG). A negative result adds to the pot. Returns the tax, the Pauschbetrag
    left and the losses left."""
    income = floats(gain)
    pot = floats(losses) + np.maximum(-income, 0.0)
    offset = np.minimum(np.maximum(income, 0.0), pot)
    taxable = np.maximum(income, 0.0) - offset
    used = np.minimum(taxable, pauschbetrag_left)
    return (
        floats((taxable - used) * flat_rate(church_rate(opts, ty), ty)),
        floats(floats(pauschbetrag_left) - used),
        floats(pot - offset),
    )


def private_sales(net: Num, carried: Num, ty: TaxYear) -> tuple[FloatArray, FloatArray]:
    """§23 Abs. 3 EStG on the `net` result of a year's private sales, its losses offset (S. 7).
    A net gain below the Freigrenze stays free and leaves the losses `carried` from earlier
    years unused (S. 5). A larger one is taxable less those losses, also where they push it
    below the Freigrenze (S. 8 with §10d; BMF 2004-10-25 Tz. 52, BFH IX R 27/04, FG München
    1 K 2045/06). A net loss joins the carried losses. Returns the taxable gain and the losses
    left."""
    n, pot = floats(net), floats(carried)
    gain = np.where(n >= ty.private_sale_freigrenze, n, 0.0)
    offset = np.minimum(gain, pot)
    return floats(gain - offset), floats(pot - offset + np.maximum(-n, 0.0))


def erbschaftsteuer(
    acquired: Num,
    prior_values: ArrayLike,
    prior_tax: ArrayLike,
    relation: Relation,
    ty: TaxYear,
    *,
    inheritance: bool,
) -> FloatArray:
    """The Erbschaft- or Schenkungsteuer on an acquisition from one giver, nominal: the constants
    of the year are not indexed (the Freibeträge stand since 2009). `acquired` is its value, less
    the Erbfallkosten-Pauschbetrag of an `inheritance` (§10 Abs. 5 Nr. 3 ErbStG). §14 Abs. 1: the
    acquisitions from the giver within ten years before it, one row each of `prior_values` and
    `prior_tax`, add at their value (S. 1; a value of 0 or below stays out, S. 5), the tax of the
    sum is levied less the tax on them alone by the law of today or the tax paid on them, the
    larger (S. 2, 3), at least the tax on this acquisition alone (S. 4) and at most half of it
    (Abs. 3)."""
    own = np.maximum(floats(acquired) - (ty.erbst_erbfallkosten if inheritance else 0.0), 0.0)
    held = np.maximum(floats(prior_values), 0.0).sum(axis=0)
    paid = floats(prior_tax).sum(axis=0)
    deducted = np.maximum(_erbst_tariff(held, relation, ty), paid)
    tax = np.maximum(
        _erbst_tariff(own + held, relation, ty) - deducted, _erbst_tariff(own, relation, ty)
    )
    return floats(np.minimum(tax, own / 2))


def _erbst_tariff(value: Num, relation: Relation, ty: TaxYear) -> FloatArray:
    """§19 ErbStG on `value` less the Freibetrag of the relation (§16), rounded down to 100 (§10
    Abs. 1 S. 6), at the rate of its bracket in the class of the relation (§15), with the
    Härteausgleich of Abs. 3 over the limit of the bracket below."""
    rounding = ty.erbst_rounding
    taxable = np.floor(np.maximum(floats(value) - ty.erbst_freibetrag[relation], 0.0) / rounding)
    taxable = taxable * rounding
    rates = np.array(ty.erbst_rates[ty.erbst_klasse[relation]])
    limits = np.array([0.0, *ty.erbst_brackets])
    bracket = np.searchsorted(limits[1:], taxable)  # up to and including its limit
    below = np.maximum(bracket - 1, 0)
    share = np.where(
        rates[bracket] <= ty.erbst_haerte.rate, ty.erbst_haerte.below, ty.erbst_haerte.above
    )
    eased = rates[below] * limits[bracket] + share * (taxable - limits[bracket])
    return floats(
        np.where(bracket > 0, np.minimum(rates[bracket] * taxable, eased), rates[0] * taxable)
    )
