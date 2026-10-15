"""The trade form of the `securities` tab of the Assets page, `Add a trade` on a phone: a buy, a
sale or a Vorabpauschale typed with a decimal comma or point, refused in plain words with the
fields to correct, saved at once with a toast that names units, price and euros, so a slip of a
mark shows. Also the words and checks of a trade that the tab shares: the ISIN or symbol (`CODE`),
what a unit of gold or crypto counts (`counts`), a trade far from its series (`series_notes`)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import streamlit as st
from pydantic import ValidationError

from dagobert import lots
from dagobert.i18n import N_, _
from dagobert.model.assets import (
    CryptoAsset,
    EquityAsset,
    GoldAsset,
    HoldingsAsset,
    LotAsset,
    Trade,
)
from dagobert.money import format_eur
from dagobert.prices import GRAMS_PER_TROY_OUNCE, off_series
from dagobert.store import RowEdits
from dagobert.tradeimport import replaced_basis
from dagobert.ui import keyboard, source, tell
from dagobert.ui.fields import euros
from dagobert.ui.forms import explain, problems
from dagobert.ui.save import REFUSED, reason
from dagobert.ui.tables import key_class, unsaved

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from streamlit.delta_generator import DeltaGenerator

    from dagobert.store import RowFile
    from dagobert.ui.gridcolumns import Row
    from dagobert.ui.tables import Table

CODE = N_("ISIN or symbol")  # the column of what a trade names in `security`, beside its name
# the help of `Add` and `Import N trades` while the trades grid holds edits: both change its rows
WAIT = N_("Save or discard the edits of the trades below first.")
# what a typed trade lacks, by its empty fields
MISSING = {
    ("units",): N_("enter the number of units"),
    ("amount",): N_("enter the amount in euros"),
    ("units", "amount"): N_("enter the number of units and the amount in euros"),
}
NUMBERS = {"units": N_("units"), "amount": N_("amount"), "fees": N_("fees")}  # of a typed trade
CHOOSE_SECURITY = N_(
    "choose a security or type its ISIN, such as IE00B4L5Y983, or the symbol of gold or a coin, "
    "such as XAU"
)
# the symbol that the trade form of gold or crypto offers, and what one unit of it is
SYMBOLS: dict[type[LotAsset], str] = {GoldAsset: "XAU", CryptoAsset: "BTC"}
# units and prices with a decimal comma or point: they show without thousands groups, so a mark
# is decimal
_PLAIN = re.compile(r"\d*[.,]?\d+")
# 1.200 may group thousands like the euros: 1200 units, or 1.2
_GROUPED = re.compile(r"[1-9]\d{0,2}[.,]\d{3}")


def _comma(number: float) -> str:
    """A number in a hint of what to type, with the decimal comma of every hint of the forms."""
    return f"{number}".replace(".", ",")


COUNTS = {
    "XAU": N_("XAU counts troy ounces of {grams} g: a 100 g bar is {ounces} troy ounces."),
    "BTC": N_("BTC counts bitcoins."),
}


def counts(model: type[LotAsset]) -> str:
    """What one unit of the symbol of a gold or crypto asset is (`COUNTS`)."""
    return _(COUNTS[SYMBOLS[model]]).format(
        grams=_comma(GRAMS_PER_TROY_OUNCE), ounces=_comma(round(100 / GRAMS_PER_TROY_OUNCE, 4))
    )


def trades_own_basis(trades: list[Row]) -> Row:
    """An equity asset with trades takes its basis from their lots."""
    return {"cost_basis": None} if trades else {}


def basis_check(asset: HoldingsAsset) -> Callable[[list[Row]], list[str]] | None:
    """The `Table.check` of the trades of an equity asset with a typed `cost_basis`, which its
    first trade replaces (`tradeimport.replaced_basis`)."""
    note = replaced_basis(asset)
    return None if note is None else lambda _rows: [note]


class TypedError(ValueError):
    """A typed number or trade that is not saved, with the fields of the form to correct."""

    def __init__(self, message: str, *fields: str) -> None:
        super().__init__(message)
        self.fields = fields


# the hint of a number of `field` that may group thousands
GROUPED = {
    "units": N_("units {text}: type {whole} for whole units, or {fraction} for a fraction"),
    "price": N_("price {text}: type {whole} for whole euros, or {fraction} for a fraction"),
}


def plain(text: str, field: str) -> float | None:
    """A number without thousands groups (the units of a trade, a price per unit), typed with a
    decimal comma or point: whole numbers stay whole in the file, like the others. None for
    anything else. Raises `TypedError` for a mark before three digits, which may group thousands:
    1.200 may be 1200 whole units or euros or 1,2, which the hint (`GROUPED`) gives with the
    comma of every hint."""
    if _GROUPED.fullmatch(text := text.strip()):
        units, fraction = re.split("[.,]", text)
        msg = _(GROUPED[field]).format(
            text=text, whole=units + fraction, fraction=f"{units},{fraction.rstrip('0') or '0'}"
        )
        raise TypedError(msg, field)
    if not _PLAIN.fullmatch(text):
        return None
    number = float(text.replace(",", "."))
    return int(number) if number.is_integer() else number


@dataclass(frozen=True)
class Typed:
    """A trade as typed into the form: the numbers as text, with a decimal comma or point."""

    day: date | None
    kind: str
    security: str
    name: str = ""
    units: str = ""
    amount: str = ""
    fees: str = ""

    def row(self) -> Row:
        """The trade as a row of `trades`. Raises `TypedError` for a missing date, units or amount,
        units that may hold a thousands group, a number that does not read or a trade that the
        model refuses."""
        if self.day is None:
            raise TypedError(_("choose a date"))
        numbers = {
            "units": plain(self.units, "units"),
            "amount": euros(self.amount),
            "fees": euros(self.fees),
        }
        if bad := [k for k, v in numbers.items() if v is None and getattr(self, k).strip()]:
            fields = ", ".join(_(NUMBERS[k]) for k in bad)
            raise TypedError(
                _("{fields}: type a number, for example 12,5").format(fields=fields), *bad
            )
        needed = {"units": self.kind != lots.TradeKind.VORABPAUSCHALE, "amount": True}
        if missing := tuple(
            k for k, need in needed.items() if need and not getattr(self, k).strip()
        ):
            raise TypedError(_(MISSING[missing]), *missing)
        typed = {
            "date": self.day,
            "kind": self.kind,
            "security": self.security.strip().upper(),
            "name": self.name.strip() or None,
        }
        row = {k: v for k, v in (typed | numbers).items() if v is not None and (k != "fees" or v)}
        if refused := problems(Trade, row, "assets.yaml"):
            # the pattern of a security means nothing to a user
            words = (_(CHOOSE_SECURITY) if p.path == "security" else explain(p) for p in refused)
            raise TypedError("; ".join(words), *(p.path for p in refused))
        return row


def choices(asset: HoldingsAsset) -> tuple[list[str], list[lots.TradeKind]]:
    """The securities of the trade form, that of the latest trade first, and the kinds of trade.
    Gold and crypto offer their symbol (`SYMBOLS`) and no Vorabpauschale: that belongs to a
    fund."""
    latest = dict.fromkeys(
        t.security for t in sorted(asset.trades, key=lambda t: t.date, reverse=True)
    )
    if not isinstance(asset, LotAsset):
        return list(latest), list(lots.TradeKind)
    latest.setdefault(SYMBOLS[type(asset)])
    return list(latest), [lots.TradeKind.BUY, lots.TradeKind.SELL]


def _trade_form(
    asset: HoldingsAsset, key: str, *, held: bool
) -> tuple[Typed | None, DeltaGenerator]:
    """The fields of the form `key`, None until it is sent, and the place of its message, right
    below the button, which is off while the grid `held` edits. The security of the latest trade
    comes first, a new one is typed as its ISIN or symbol."""
    label = lots.names(asset.trades)
    codes, kinds = choices(asset)
    with st.form(key, border=False):
        code = st.selectbox(
            _("Security"),
            codes,
            format_func=lambda i: str(label.get(i, i)),
            accept_new_options=True,
            placeholder=_("Choose or type an ISIN or symbol"),
            key=f"{key}-security",
        )
        with st.container(horizontal=True, wrap=True, vertical_alignment="bottom"):
            day = st.date_input(
                _("Date"),
                date.today(),
                min_value=date(1970, 1, 1),
                format="YYYY-MM-DD",
                key=f"{key}-date",
                width=140,
            )
            kind = st.segmented_control(
                _("Kind"),
                kinds,
                format_func=lambda option: _(TRADE_KINDS[option]),
                default=lots.TradeKind.BUY,
                required=True,
                key=f"{key}-kind",
            )
            numbers = {
                field: st.text_input(
                    _(text), key=f"decimal-{key}-{field}", placeholder=example, width=width
                )
                or ""
                for field, text, example, width in (
                    ("units", N_("Units"), "10", 100),
                    ("amount", N_("Amount €"), "104,20", 120),
                    ("fees", N_("Fees €"), "0", 100),
                )
            }
            name = st.text_input(
                _("Name"), placeholder=_("of a new security"), key=f"{key}-name", width=200
            )
            sent = st.form_submit_button(
                _("Add"),
                type="primary",
                key=f"{key}-add",
                disabled=held,
                help=_(WAIT) if held else None,
            )
        message = st.empty()
        saved = _(
            "Saved at once. Units take no thousands groups: 1200, or 1,2 for a fraction. The "
            "amount is the price of all units without fees (the Kurswert)."
        )
        st.caption(f"{saved} {counts(type(asset))}" if isinstance(asset, LotAsset) else saved)
    if not sent:
        return None, message
    typed = Typed(
        day if isinstance(day, date) else None, str(kind), code or "", name or "", **numbers
    )
    return typed, message


# the kinds of trade in the form, by their value in the files
TRADE_KINDS = {
    lots.TradeKind.BUY: N_("buy"),
    lots.TradeKind.SELL: N_("sell"),
    lots.TradeKind.VORABPAUSCHALE: N_("vorabpauschale"),
}
# the toast of an added trade by its kind: a buy or sale with its units, a Vorabpauschale without
RECEIPTS = {
    lots.TradeKind.BUY: N_(
        "Added the buy of {units} × {name} at {price} per unit, {amount} on {day}"
    ),
    lots.TradeKind.SELL: N_(
        "Added the sell of {units} × {name} at {price} per unit, {amount} on {day}"
    ),
    lots.TradeKind.VORABPAUSCHALE: N_("Added the vorabpauschale of {amount} for {name} on {day}"),
}


def receipt(row: Row, names: Mapping[str, str]) -> str:
    """The toast of an added trade, with the names of the securities so far. Units, euros and the
    price per unit show a slip of a mark."""
    units = row.get("units")
    return _(RECEIPTS[row["kind"]]).format(
        units=f"{units:.12g}" if units else "",
        name=row.get("name") or names.get(row["security"], row["security"]),
        price=format_eur(row["amount"] / units, cents=True) if units else "",
        amount=format_eur(row["amount"], cents=True),
        day=row["date"],
    )


def add_trade(file: RowFile, asset: HoldingsAsset, table: Table) -> None:
    """On a phone, a form above the trades that saves one at once: the grid adds a row at the end
    of its list, out of view. It waits for unsaved edits of the grid, which shows the trades as
    they were until a save (`save.base`). `file` finds the asset by its id in the write: a
    removed one refuses the trade."""
    form = f"trades-add-{asset.id}"
    n = st.session_state.setdefault(form, 0)
    with st.expander(_("Add a trade"), icon=":material/add:", key=f"{form}-open"):
        typed, message = _trade_form(asset, f"{form}-{n}", held=unsaved(table))
    keyboard()
    if typed is None:
        return
    try:
        row = typed.row()
        equity = isinstance(asset, EquityAsset)
        file.apply(
            RowEdits(added=[row], parent=trades_own_basis([row]) if equity else {}),
            source=source(),
        )
    except REFUSED as err:
        message.error(_("Not added: {reason}").format(reason=reason(err)))
        if isinstance(err, TypedError) and err.fields:  # the fields to correct, framed in red
            fields = ", ".join(f".{key_class(f'decimal-{form}-{n}-{f}')}" for f in err.fields)
            st.html(
                f"<style>:is({fields}) [data-testid=stTextInputRootElement] "
                "{border-color: light-dark(#d64545, #ff6b6b) !important}</style>"
            )
        return
    st.session_state[form] = n + 1  # a new form, empty
    tell(receipt(row, lots.names(asset.trades)))
    basis = replaced_basis(asset) if equity else None
    for far in [*series_notes(file.data_dir, [row]), *filter(None, [basis])]:
        tell(_("Check: {warning}").format(warning=far), warn=True)
    st.rerun()


def series_notes(data_dir: Path, rows: list[Row]) -> list[str]:
    """`prices.off_series` of the trades among the edited and added `rows`, the warnings of the
    trades grid of gold and crypto. A row that the model refuses is left to the save."""
    return off_series(data_dir, [t for row in rows if (t := _trade(row)) is not None])


def _trade(row: Row) -> Trade | None:
    try:
        return Trade.model_validate(row)
    except ValidationError:
        return None
