"""The tax options of the assumptions: the tax year of a plan, the Land with its Grunderwerbsteuer
and church tax, the relation of a relative for the Erbschaftsteuer."""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from typing import Annotated, Literal, TypedDict

import yaml
from pydantic import Field, TypeAdapter, field_validator, model_validator

from dagobert.model.base import Euros, Month, Percent, Strict, Titled

TAX_DIR = Path(__file__).parents[1] / "data" / "tax"
TAX_YEARS = tuple(sorted(int(p.stem) for p in TAX_DIR.glob("*.yaml")))


def default_tax_year(start: date) -> int:
    """The tax year of a plan without `tax.year`: the newest file up to the year of `start`, the
    oldest when none is."""
    return max((year for year in TAX_YEARS if year <= start.year), default=TAX_YEARS[0])


class Land(Titled):
    """A German Land, by its ISO 3166-2:DE code without `DE-`: it sets the Grunderwerbsteuer and
    the rate of the church tax. The selects show its name, in the order of the names."""

    BW = "BW"
    BY = "BY"
    BE = "BE"
    BB = "BB"
    HB = "HB"
    HH = "HH"
    HE = "HE"
    NI = "NI"
    MV = "MV"
    NW = "NW"
    RP = "RP"
    SL = "SL"
    SN = "SN"
    ST = "ST"
    SH = "SH"
    TH = "TH"

    @classmethod
    def titles(cls) -> dict[str, str]:
        return {
            "BW": "Baden-Württemberg",
            "BY": "Bavaria",
            "BE": "Berlin",
            "BB": "Brandenburg",
            "HB": "Bremen",
            "HH": "Hamburg",
            "HE": "Hesse",
            "NI": "Lower Saxony",
            "MV": "Mecklenburg-Western Pomerania",
            "NW": "North Rhine-Westphalia",
            "RP": "Rhineland-Palatinate",
            "SL": "Saarland",
            "SN": "Saxony",
            "ST": "Saxony-Anhalt",
            "SH": "Schleswig-Holstein",
            "TH": "Thuringia",
        }


class Relation(Titled):
    """What a relative who gives or bequeaths is to the person: it sets the tax class of the
    Erbschaftsteuer and the Freibetrag (§§15, 16 ErbStG). A step-parent gives as a parent (§15
    Abs. 1 I Nr. 2)."""

    PARENT = "parent"
    GRANDPARENT = "grandparent"
    SIBLING = "sibling"
    AUNT_UNCLE = "aunt_uncle"
    PARENT_IN_LAW = "parent_in_law"
    OTHER = "other"

    @classmethod
    def titles(cls) -> dict[str, str]:
        return {
            "parent": "Parent",
            "grandparent": "Grandparent",
            "sibling": "Sibling",
            "aunt_uncle": "Aunt or uncle",
            "parent_in_law": "Parent-in-law",
            "other": "Other",
        }


class Allowance(Titled):
    """The Kinderfreibetrag and the Betreuungsfreibetrag of a child (§32 Abs. 6 EStG): half of each
    for each parent, or the full ones for you on application when the other parent pays no
    support (S. 6)."""

    HALF = "half"
    FULL = "full"

    @classmethod
    def titles(cls) -> dict[str, str]:
        return {"half": "half", "full": "full"}


TRANSFER_TAX = Path(__file__).parents[1] / "data" / "grunderwerbsteuer.yaml"


class _Rate(TypedDict):
    since: date
    rate: float


@cache
def _transfer_rates() -> dict[Land, list[tuple[date, float]]]:
    """The rates of the Grunderwerbsteuer of each Land with the day from which each holds."""
    table = TypeAdapter(dict[Land, list[_Rate]]).validate_python(
        yaml.safe_load(TRANSFER_TAX.read_text(encoding="utf-8"))
    )
    return {land: sorted((r["since"], r["rate"]) for r in rows) for land, rows in table.items()}


def transfer_tax_rate(land: Land, day: date) -> float:
    """The Grunderwerbsteuer of `land` on a purchase on `day`, as a share of the price."""
    rates = [rate for since, rate in _transfer_rates()[land] if since <= day]
    if not rates:
        msg = f"no Grunderwerbsteuer of {land} before {_transfer_rates()[land][0][0]}"
        raise ValueError(msg)
    return rates[-1]


class SelfEmployed(Strict):
    """The social insurance of the person in a month in which a `self_employed` stream runs as
    the main work: without a salary and outside ALG1."""

    rv: Literal["none", "regular", "income"] = Field(
        default="none",
        description="Statutory pension insurance on the profit. `none`: no compulsory "
        "contribution, voluntary ones are `rv_voluntary` streams. `regular`: the Regelbeitrag on "
        "the Bezugsgröße, half of it up to the end of the third calendar year after the founding. "
        "`income`: on the profit up to the contribution ceiling, at least on the "
        "Geringfügigkeitsgrenze, never half. Both are compulsory by law for some trades "
        "(§2 SGB VI) or on application (§4 Abs. 2)",
    )
    krankengeld: bool = Field(
        default=False,
        description="GKV only: sick pay from the seventh week (Wahlerklärung, §44 Abs. 2 SGB V), "
        "at the general rate of 14.6% instead of the reduced 14.0%",
    )
    founded: Month | None = Field(
        default=None,
        description="The month of the founding, which starts the years of the half Regelbeitrag "
        "of `rv: regular`. Empty: the first month in which a self-employed stream runs. The roll "
        "forward writes it when a business runs before the new start",
    )


class TaxOptions(Strict):
    year: Annotated[int, Field(json_schema_extra={"enum": list(TAX_YEARS)})] | None = Field(
        default=None,
        description="The year whose legal constants apply, one of the years that the app knows. "
        "Empty: the newest of them up to the year of `start`, the oldest when none is",
    )
    sparer_pauschbetrag: Euros = Field(
        default=1000.0, ge=0, description="Capital income free of tax per year"
    )
    teilfreistellung: Percent = Field(
        default=0.30,
        ge=0,
        le=1,
        description="Share of the gains of an equity fund free of tax, for every depot without "
        "its own",
    )
    werbungskosten: Euros = Field(
        default=0.0,
        ge=0,
        description="Your work expenses (Werbungskosten) of a year with a salary all year, as the "
        "Steuerbescheid lists them: the commute, a home office, work equipment, union dues, in "
        "euros of the start. A year with fewer salary months counts its share, at most the salary "
        "of the year. They count when above the Arbeitnehmer-Pauschbetrag (1.230 € in 2026), which "
        "applies anyway. The monthly withholding ignores them: the settlement refunds. Costs at a "
        "date, such as a course, are an expense deductible as work expenses on the Cashflows page",
    )
    harvest: bool = Field(
        default=False,
        description="Each December, sell the equity whose gains fit into the tax-free room of the "
        "year and buy it back at the next price: the Sparer-Pauschbetrag left and what your other "
        "income leaves of the Grundfreibetrag, where the Günstigerprüfung refunds the flat tax. A "
        "later sale then pays less tax. Carried losses come off a gain first, of the income tax "
        "and of capital income, so it uses them only where the tax-free room beyond them is at "
        "least as large. A voluntary member of the statutory health insurance in the next "
        "January realizes only what keeps the contribution of that year at its minimum",
    )
    pkv: bool = Field(
        default=True,
        description="Privately insured: no statutory KV and PV, the `health` streams take the "
        "subsidies and the deduction. Up to `gkv_from`, when it is set",
    )
    gkv_from: Month | None = Field(
        default=None,
        description="With `pkv`: the first month in the statutory health insurance (GKV). From "
        "it the rules of the GKV apply and the `health` streams end. Before 55 a salary below "
        "the Jahresarbeitsentgeltgrenze or ALG1 makes you a compulsory member (§5 SGB V); from "
        "55 §6 Abs. 3a usually blocks the return. A scenario sets it to compare. Empty: the "
        "PKV for the whole run",
    )
    kv_zusatz: Percent | None = Field(
        default=None,
        ge=0,
        description="The Zusatzbeitrag of your own Krankenkasse (§242 SGB V), the whole rate: the "
        "member pays half of it on a salary and on the pension, all of it on the other income "
        "that pays, such as a company pension or a profit. Empty: the "
        "average of the tax year (§242a), 2.9% in 2026. GKV only",
    )
    church: bool = Field(
        default=False,
        description="A member of a church that levies the church tax: 8% of the income tax in "
        "Baden-Württemberg and Bavaria, 9% elsewhere (§51a EStG, the Kirchensteuergesetze), by "
        "`land`. On capital income the flat tax falls to 24.51% or 24.45% with the church tax on "
        "top (§32d Abs. 1 EStG). Leaving the church is a lever of a scenario",
    )
    land: Land | None = Field(
        default=None,
        description="The Land where you live: it sets the rate of the church tax. Needed with "
        "`church`",
    )
    crypto_capital_from: Month | None = Field(
        default=None,
        description="A crypto unit bought in or after this month is capital income (§20 EStG), as "
        "the BMF draft of 2026-09-30 plans for 2027. None: the law of today, a private sale",
    )
    loss_carryforward: Euros = Field(
        default=0.0,
        ge=0,
        description="The Verlustvortrag of your last Feststellungsbescheid (§10d Abs. 4 EStG): "
        "losses of earlier years, such as of a let flat or a business, that offset your income "
        "before the Sonderausgaben, in euros of `start`. The roll forward writes the losses that "
        "the plan carries to the new start",
    )
    loss_carryback: bool = Field(
        default=True,
        description="A loss of a year, when the income of the year is below zero, can go back "
        "(§10d Abs. 1 EStG): into the year before, the rest into the year before that, up to their "
        "income and 1.000.000 €; what is left carries forward. The refund comes in the December "
        "after the year of the loss. The carryback comes off before the Sonderausgaben and can use "
        "up the tax-free Grundfreibetrag of a year of low income. Since 2022 the law lets you "
        "waive it only as a whole. On: in that December the simulation waives it on each path "
        "where the loss saves more tax in the year after it than the refund brings; later years "
        "do not count. Off: the loss always carries forward only",
    )
    capital_losses: Euros = Field(
        default=0.0,
        ge=0,
        description="Losses of capital income carried forward at the start (§20 Abs. 6 EStG), in "
        "euros of the start month: the losses that your bank still holds in its loss pot (its "
        "yearly tax statement) plus those of your last Feststellungsbescheid (a loss certificate "
        "of the bank moves them there). They offset later capital income, gains and interest, "
        "before the "
        "Sparer-Pauschbetrag. A loss from the sale of single shares (Aktienverlusttopf) counts "
        "here only if the BVerfG strikes §20 Abs. 6 S. 4 EStG, which lets it offset only gains of "
        "shares (2 BvL 3/21): set it in a scenario to compare both outcomes. The roll forward "
        "writes the losses that the plan carries to the new start",
    )
    alleinerziehend: bool = Field(
        default=False,
        description="You raise your children alone, without another adult in the household: the "
        "Entlastungsbetrag (§24b EStG) of the tax year, higher for each further child, comes off "
        "the taxable income in each month in which a child counts",
    )
    self_employed: SelfEmployed = Field(
        default=SelfEmployed(),
        description="The pension and the health insurance in a month with a business of your own",
    )

    def pkv_in(self, month: date) -> bool:
        """Privately insured in `month`: `pkv`, before `gkv_from`."""
        return self.pkv and (self.gkv_from is None or month < self.gkv_from)

    @model_validator(mode="after")
    def _church_in_a_land(self) -> TaxOptions:
        if self.church and self.land is None:
            msg = "church needs land: the Land sets the rate of the church tax"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _gkv_after_pkv(self) -> TaxOptions:
        if self.gkv_from is not None and not self.pkv:
            msg = "gkv_from needs pkv: it is the month in which the private insurance ends"
            raise ValueError(msg)
        return self

    @field_validator("year")
    @classmethod
    def _constants_known(cls, year: int | None) -> int | None:
        if year is not None and year not in TAX_YEARS:
            msg = f"no tax constants for {year}, only for {', '.join(map(str, TAX_YEARS))}"
            raise ValueError(msg)
        return year
