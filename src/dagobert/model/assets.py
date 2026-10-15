"""`assets.yaml`: cash, term deposits, holdings with their trades, property, loans and pension
policies."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from dagobert.lots import Book, TradeKind, book
from dagobert.model.base import Day, Euros, Month, Number, Percent, Strict, Unit, Years, unit
from dagobert.model.months import add_months, months_between


class AssetBase(Strict):
    id: str = Field(description="The short name by which other inputs and the history name it")
    name: str = ""
    tags: list[str] = Field(default=[])
    asof: Day | None = Field(default=None, description="The date of the value")
    update_every: Annotated[int, unit(Unit.MONTHS)] | None = Field(
        default=None,
        gt=0,
        description="Months after which the value needs an update, for example 12 for a yearly "
        "statement. Default by kind",
    )

    @property
    def label(self) -> str:
        return self.name or self.id


class CashAsset(AssetBase):
    kind: Literal["cash"]
    value: Euros


class TermDeposit(AssetBase):
    """Festgeld. Interest compounds yearly and is paid, and taxed, once at `matures`."""

    kind: Literal["term_deposit"]
    value: Euros = Field(description="Amount invested at `start`, without interest")
    rate: Percent
    start: Day
    matures: Day

    @model_validator(mode="after")
    def _term(self) -> TermDeposit:
        if self.start >= self.matures:
            msg = f"{self.id}: start must be before matures"
            raise ValueError(msg)
        return self

    def value_at(self, day: date) -> float:
        """Invested amount with the interest accrued by `day` (actual/365)."""
        held = (min(max(day, self.start), self.matures) - self.start).days
        return float(self.value * (1 + self.rate) ** (held / 365))


_ISIN = "[A-Z]{2}[A-Z0-9]{9}[0-9]"
ISIN = f"^{_ISIN}$"
# an ISIN, or the symbol of gold or a coin: 2 to 10 capitals and digits, so a typo of an ISIN
# (11 or 12 characters) is no symbol
SECURITY = f"^(?:{_ISIN}|[A-Z][A-Z0-9]{{1,9}})$"


class Trade(Strict):
    """One booking of a security, as the bank or the exchange lists it. All amounts are in EUR."""

    date: Day
    kind: TradeKind = Field(
        description="buy, sell, or vorabpauschale: the Vorabpauschale is the part of the expected "
        "gain of a fund that is taxed each year before a sale, which the bank books each January"
    )
    security: str = Field(
        pattern=SECURITY,
        description="The ISIN, or for gold and crypto a symbol: XAU counts troy ounces, BTC "
        "bitcoins",
    )
    name: str = Field(default="", description="The last name given names the security")
    units: Number | None = Field(
        default=None, gt=0, description="Units bought or sold, none for a Vorabpauschale"
    )
    amount: Euros = Field(
        ge=0,
        description="Kurswert of a buy or sale, without fees, or the Vorabpauschale of the "
        "fund, booked in January for the year before",
    )
    fees: Euros = Field(default=0.0, ge=0, description="Fees of a buy or sale")

    @model_validator(mode="after")
    def _shape(self) -> Trade:
        if (self.units is None) != (self.kind == TradeKind.VORABPAUSCHALE):
            msg = f"{self.kind} of {self.security} on {self.date}: units belong to a buy or sale"
            raise ValueError(msg)
        if self.kind == TradeKind.VORABPAUSCHALE and self.date.month != 1:
            msg = f"Vorabpauschale of {self.security} on {self.date}: the bank books it in January"
            raise ValueError(msg)
        return self


class HoldingsAsset(AssetBase):
    """An asset of securities. Its `trades` give the lots for the price import, the valuation
    and the return."""

    trades: list[Trade] = Field(default=[])
    securities: ClassVar[str] = ISIN  # what its trades may name

    @property
    def book(self) -> Book:
        return book(self.trades)

    @model_validator(mode="after")
    def _named(self) -> HoldingsAsset:
        """Equity and fixed income take ISINs: a symbol belongs to gold or crypto."""
        if odd := {
            t.security for t in self.trades if not re.fullmatch(self.securities, t.security)
        }:
            msg = f"{self.id}: {', '.join(sorted(odd))} is no ISIN: a symbol is for gold or crypto"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _replays(self) -> HoldingsAsset:
        try:
            book(self.trades)
        except ValueError as err:
            msg = f"{self.id}: {err}"
            raise ValueError(msg) from err
        return self


class FixedIncomeAsset(HoldingsAsset):
    """Tagesgeld, bond and money-market funds: earns the fixed_income return, part of the
    allocation bucket."""

    kind: Literal["fixed_income"]
    value: Euros


class EquityAsset(HoldingsAsset):
    """A depot, or the funds of one class in it. The engine uses `value`, `basis` and
    `teilfreistellung`."""

    kind: Literal["equity"]
    value: Euros
    cost_basis: Euros | None = Field(
        default=None, description="Only without trades, their lots give the basis"
    )
    teilfreistellung: Percent | None = Field(
        default=None,
        ge=0,
        le=1,
        description="The share of the gains that is free of tax, the Teilfreistellung (§20 "
        "InvStG): 30% for an equity fund, 15% for a mixed fund, 60% for a real-estate fund, 80% "
        "for one of foreign real estate, 0 for shares, bonds, certificates and funds of gold or "
        "crypto. Keep one asset per class. Empty: `tax.teilfreistellung` of the assumptions",
    )

    @property
    def basis(self) -> float:
        if self.cost_basis is not None:
            return self.cost_basis
        return sum(lot.basis for lot in self.book.open)

    @model_validator(mode="after")
    def _one_cost_basis(self) -> EquityAsset:
        if bool(self.trades) == (self.cost_basis is not None):
            msg = f"{self.id}: needs trades or a cost_basis, not both"
            raise ValueError(msg)
        return self


class LotAsset(HoldingsAsset):
    """Gold or crypto, one asset per depot or wallet. Its lots keep their purchase month: a gain
    is free after a year of holding, else a private sale (§23 EStG), unless `tax` is `capital`
    (§20 EStG). An asset without trades counts as held for more than a year."""

    securities: ClassVar[str] = SECURITY
    value: Euros = Field(description="Market value at the start")
    growth: str = Field(description="Return class")
    cost: Percent = Field(
        default=0.0, ge=0, le=1, description="Yearly custody as a share of the value"
    )
    tax: Literal["private_sale", "capital"] = Field(
        default="private_sale",
        description="`capital` for a note without physical backing (§20 Abs. 2 S. 1 Nr. 7 EStG)",
    )

    @model_validator(mode="after")
    def _lots(self) -> LotAsset:
        if any(t.kind == TradeKind.VORABPAUSCHALE for t in self.trades):
            msg = f"{self.id}: a Vorabpauschale belongs to a fund, not to gold or crypto"
            raise ValueError(msg)
        if self.tax == "capital" and not self.trades:
            msg = f"{self.id}: tax: capital needs trades, their lots give the basis"
            raise ValueError(msg)
        return self


class GoldAsset(LotAsset):
    """Bars, coins, or a note fully backed by gold such as Xetra-Gold: `XAU` counts troy ounces,
    a note goes by its ISIN."""

    kind: Literal["gold"]
    growth: str = Field(default="gold", description="Return class")


class CryptoAsset(LotAsset):
    """One wallet or account of coins, as the BMF counts them: `BTC` counts bitcoins."""

    kind: Literal["crypto"]
    growth: str = Field(default="bitcoin", description="Return class, another for another coin")


BUILDING_SHARE = (
    "The share of the building in what the purchase cost, the land is the rest and is not "
    "depreciated. The Arbeitshilfe Kaufpreisaufteilung of the BMF gives a first estimate. Needed "
    "for a let property"
)
ANNUITY = "Monthly payment (interest + principal)"
PREPAYMENT_PENALTY = (
    "Fraction of repaid balance charged when repaid within the fixed rate. "
    "Nothing is due from ten years and six months after the full payout (§489 Abs. 1 Nr. 2 "
    "BGB): 0 for a repayment that late"
)
AFA = (
    "The yearly AfA (depreciation) of the building of a let property, by the year of its "
    "completion (§7 Abs. 4 S. 1 Nr. 2 EStG): 3% after 2022, 2% from 1925 to 2022, 2.5% before "
    "1925. A shorter useful life that you can prove takes its own rate (S. 2); 0 for none, such "
    "as an inherited flat without data. Needed for a let property"
)


class PropertyAsset(AssetBase):
    kind: Literal["property"]
    sqm: Number = Field(gt=0, description="Living space in m²")
    per_sqm: Euros = Field(ge=0, description="Current market value per m²")
    bought_for: Euros | None = Field(
        default=None,
        description="What the purchase cost: the price with the Grunderwerbsteuer, the notary and "
        "the broker. The basis of the tax of a private sale (§23 EStG) and, times the building "
        "share, of the AfA",
    )
    growth: str = "property"
    upkeep: Percent = Field(default=0.0, ge=0, description="Yearly upkeep as a share of value")
    bought: Month | None = Field(
        default=None,
        description="The month of the purchase: a taxable sale within ten years of it pays the "
        "tax of a private sale (§23 EStG), and a let property has taken the AfA since then",
    )
    building_share: Percent | None = Field(default=None, ge=0, le=1, description=BUILDING_SHARE)
    afa: Percent | None = Field(default=None, ge=0, le=1, description=AFA)

    @property
    def value(self) -> float:
        return self.sqm * self.per_sqm


class Loan(AssetBase):
    kind: Literal["loan"]
    balance: Euros = Field(lt=0, description="Negative outstanding balance")
    rate: Percent
    annuity: Euros = Field(gt=0, description=ANNUITY)
    fixed_until: Month | None = Field(
        default=None,
        description="The last month of the fixed rate (Zinsbindung), after it the refinance "
        "rate of the assumptions. Empty: the rate and the prepayment penalty hold for the whole "
        "term",
    )
    prepayment_penalty: Percent = Field(
        default=0.0,
        ge=0,
        le=1,
        description=PREPAYMENT_PENALTY,
    )
    finances: str | None = Field(
        default=None,
        description="The id of the property that the loan paid for: while the property is let, "
        "the interest is a cost of the rent (Werbungskosten)",
    )

    def fixed_at(self, month: date) -> bool:
        """Inside the Zinsbindung, including the `fixed_until` month itself; without one the
        whole term: the rate of a month and the penalty of a repayment. The end of the penalty
        by §489 Abs. 1 Nr. 2 BGB is left to the input: a loan has no date of its payout."""
        return self.fixed_until is None or months_between(month, self.fixed_until) >= 0

    def step(self, balance: float, month: date, refinance: float) -> tuple[float, float]:
        """One month of the schedule: the new balance and the payment."""
        accrued = balance * (1 + (self.rate if self.fixed_at(month) else refinance) / 12)
        pay = min(self.annuity, -accrued)
        return accrued + pay, pay

    def opening(self, start: date, refinance: float) -> float:
        """The balance before the payment of `start`: a balance of an earlier `asof` rolls
        forward, a later one stays."""
        rolled = self.balance_at(add_months(start, -1), refinance)
        return self.balance if rolled is None else rolled

    def balance_at(self, day: date, refinance: float) -> float | None:
        """Scheduled balance at `day`, amortized from `asof`. Ignores extra repayments."""
        if self.asof is None:
            return None
        balance = self.balance
        for n in range(months_between(self.asof, day)):
            balance, _ = self.step(balance, add_months(self.asof, n + 1), refinance)
        return balance


class PensionPolicy(AssetBase):
    """Betriebliche Altersversorgung, or with `basisrente` a Basisrente, illiquid until `matures`.

    Employer contributions are tax-free and never touch cash. A `conversion` comes off the gross
    of a salary with the employer's subsidy, free of tax and SV within the limits of a
    Pensionsfonds, a Pensionskasse or a Direktversicherung (`sv.conversion`). The value grows
    with the `growth` return class less a yearly `cost`. At `matures` the policy pays at least
    `guarantee` of all contributions: as a lump sum into cash, taxed as Arbeitslohn
    (Fünftelregelung when `fuenftel`), or as a nominal monthly annuity of
    `annuity_per_10k` per 10,000 EUR capital, taxed in full, of a Basisrente at the taxable
    share of the year it starts. Scenario events can fund a policy with lump sums
    (`severance.bav` a company pension, `fund_policy` a Basisrente). A Basisrente takes the own
    `premium` from cash, deductible as Altersvorsorgeaufwand, and neither `contribution` nor
    `conversion`: money free of tax on the way in is taxed in full on the way out."""

    kind: Literal["bav"]
    value: Euros = Field(ge=0, description="Current policy value")
    paid: Euros = Field(default=0.0, ge=0, description="Contributions so far, guarantee base")
    contribution: Euros = Field(
        default=0.0,
        ge=0,
        description="Monthly contribution of the employer on top of the salary, nominal",
    )
    conversion: Euros = Field(
        default=0.0,
        ge=0,
        description="Monthly salary conversion (Entgeltumwandlung), nominal: the part of the gross "
        "of `salary` that goes into the policy, free of income tax up to 8% and of social "
        "insurance up to 4% of the contribution ceiling of the pension insurance, with the "
        "employer's contribution and subsidy",
    )
    salary: str | None = Field(
        default=None,
        description="The monthly salary stream of the conversion. Empty: the first monthly salary "
        "that pays in the month",
    )
    premium: Euros = Field(
        default=0.0,
        ge=0,
        description="Basisrente: your own premium per month from the cash, nominal, in the "
        "`phases` until `matures`. It lowers the income tax like the pension insurance, up to "
        "its Höchstbetrag. Only a policy with `basisrente` takes it, and a Basisrente takes "
        "neither a contribution of the employer nor a salary conversion",
    )
    subsidy: Percent | None = Field(
        default=None,
        ge=0,
        description="Share of the conversion that the employer adds. Empty: the 15% of the law, as "
        "far as the conversion saves the employer social insurance; a share of the contract is "
        "paid in full",
    )
    phases: list[str] = Field(
        description="The phases in which the employer pays the contribution and the conversion, "
        "usually those of the job of this policy. Empty: none, for a policy that only events fund"
    )
    matures: Month
    guarantee: Percent = Field(
        default=0.0, ge=0, le=1, description="Share of all contributions paid at least at maturity"
    )
    growth: str = "bav"
    cost: Percent = Field(default=0.0, ge=0, le=1, description="Yearly fee as a share of the value")
    payout: Literal["lump_sum", "annuity"] = "lump_sum"
    fuenftel: bool = Field(
        default=True, description="Tax a lump sum with the one-fifth rule (Fünftelregelung)"
    )
    annuity_per_10k: Number = Field(
        default=0.0, ge=0, description="Annuity: euros per month per 10,000 € of capital"
    )
    basisrente: bool = Field(
        default=False,
        description="A Basisrente (Rürup) instead of a company pension. It pays an annuity: the "
        "law allows no lump sum. Your own premiums and payments into it lower the income tax, "
        "and the annuity is taxed at the share of the year it starts, as the statutory pension. "
        "In the statutory health insurance a company pension pays health and care contributions "
        "(a Versorgungsbezug), a Basisrente only for a voluntary member",
    )

    @model_validator(mode="after")
    def _payout(self) -> PensionPolicy:
        if self.payout == "annuity" and self.annuity_per_10k == 0:
            msg = f"{self.id}: annuity payout needs annuity_per_10k"
            raise ValueError(msg)
        if self.basisrente and self.payout == "lump_sum":  # §10 Abs. 1 Nr. 2 S. 2 EStG
            msg = f"{self.id}: a Basisrente pays an annuity, no lump sum: set payout to annuity"
            raise ValueError(msg)
        # money free of tax under §3 Nr. 63 EStG comes out taxed in full (§22 Nr. 5 S. 1)
        if self.basisrente and (self.contribution or self.conversion):
            msg = (
                f"{self.id}: a Basisrente takes no contribution of an employer and no salary "
                "conversion: your own payments are its premium"
            )
            raise ValueError(msg)
        if self.premium and not self.basisrente:
            msg = f"{self.id}: a premium of your own needs basisrente: a company pension takes none"
            raise ValueError(msg)
        return self


class AvDepot(AssetBase):
    """Altersvorsorgedepot (Altersvorsorgereformgesetz 2026). Each December of a year with
    compulsory GRV insurance (a salary or ALG1 month) the engine pays `contribution` from cash
    and adds the Zulage. From the start of the pension it pays `lump_sum` of the value at once
    and the rest as an Auszahlplan until `until_age`, both taxed as other income. No tax inside,
    illiquid until the payout."""

    kind: Literal["av_depot"]
    value: Euros = 0.0
    contribution: Euros = Field(
        default=1800.0,
        ge=0,
        description="Per eligible year, in start-year euros. The subsidy counts up to 1,800",
    )
    start: Month = Field(description="First year with a contribution, 2027 or later")
    growth: str = Field(default="equity", description="Return class")
    cost: Percent = Field(default=0.0, ge=0, description="Yearly cost as a share of the value")
    lump_sum: Percent = Field(
        default=0.3, ge=0, le=0.3, description="Share paid at the start of the payout"
    )
    until_age: Years = Field(default=85.0, ge=85, description="End of the Auszahlplan")

    @model_validator(mode="after")
    def _from_2027(self) -> AvDepot:
        if self.start.year < 2027:
            msg = f"{self.id}: the Altersvorsorgedepot starts in 2027"
            raise ValueError(msg)
        return self


Asset = Annotated[
    CashAsset
    | TermDeposit
    | FixedIncomeAsset
    | EquityAsset
    | GoldAsset
    | CryptoAsset
    | PropertyAsset
    | Loan
    | PensionPolicy
    | AvDepot,
    Field(discriminator="kind"),
]


class Assets(Strict):
    assets: list[Asset]

    @model_validator(mode="after")
    def _unique_ids(self) -> Assets:
        if twice := sorted(i for i, n in Counter(a.id for a in self.assets).items() if n > 1):
            msg = f"asset ids must be unique: {', '.join(twice)} more than once"
            raise ValueError(msg)
        return self
