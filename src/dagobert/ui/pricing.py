"""The `Prices` expander of the Snapshot page: the stored prices of the held securities, a price
typed by hand, also for a past date, and the import of a downloaded price history, in euros
only. Each save also records the value of every asset whose securities all have a price
(`prices.record`), in the same revision. `mapper` maps the columns of a CSV of dated values. The
rows of `stored` and of the preview key their cells by English ids, which a table shows in words."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import csvimport, prices
from dagobert.i18n import N_, _
from dagobert.model.assets import SECURITY
from dagobert.money import decimal_mark, format_eur, format_number
from dagobert.ui import guard, keyboard, source, tell
from dagobert.ui.csvcolumns import DECIMAL, ColumnPick, ends, refused, said, select
from dagobert.ui.save import reason
from dagobert.ui.tradeform import CHOOSE_SECURITY, CODE, plain

if TYPE_CHECKING:
    from pathlib import Path

    from dagobert.history import Observation

OPEN, FORM, IMPORT = "prices-open", "prices-add", "prices-import"
CHOSEN = "prices-chosen"  # the security of the last added price
# the columns of `stored` and of the preview by their ids, in words: messages of the catalogue
HEADERS = {
    "security": N_("security"),
    "last price": N_("last price"),
    "price": N_("price"),
    "prices": N_("prices"),
    CODE: CODE,
    "date": N_("date"),
}
# the date of a last price that the series of gold or Bitcoin gave, by the series
FROM_SERIES = {"gold": N_("{day} (gold series)"), "bitcoin": N_("{day} (bitcoin series)")}


def stored(data_dir: Path, securities: prices.Securities) -> list[dict[str, str | int]]:
    """One row per held security: its last price (`prices.last_price`) with the date, the series
    that gave it for gold or Bitcoin, and the number of stored prices. Without a price the depot
    has no estimate. Then a price file of a security without trades, marked `(no trades)`: a
    history imported before its trades, which value no asset yet."""
    rows: list[dict[str, str | int]] = []
    for security in (i for i in securities.names if _listed(securities, i)):
        known = prices.read_prices(prices.price_file(data_dir, security))
        last = prices.last_price(data_dir, security, known)
        if last is None:
            when = _("none")
        elif last not in known[-1:]:
            when = _(FROM_SERIES[prices.BY_SYMBOL[security].series]).format(day=last[0])
        else:
            when = str(last[0])
        name = securities.names[security]
        rows.append(
            {
                "security": name
                if security in securities.trades
                else _("{name} (no trades)").format(name=name),
                "last price": when,
                "price": "" if last is None else format_eur(last[1], cents=True),
                "prices": len(known),
                CODE: security,
            }
        )
    return rows


def _listed(securities: prices.Securities, security: str) -> bool:
    """Held, or a price file without trades: a security sold in full needs no price."""
    return security in securities.units or security not in securities.trades


@dataclass(frozen=True)
class TypedPrice:
    """A price as typed into the form, with a decimal comma or point."""

    security: str
    day: date | None
    price: str

    def point(self, today: date) -> tuple[str, prices.Price]:
        """The security and the price. Raises ValueError for a missing date or one after `today`,
        a text that is no ISIN or symbol, a price that may hold a thousands group, or one that is
        no number above zero."""
        if self.day is None or self.day > today:
            raise ValueError(_("choose a date up to today"))
        if not re.fullmatch(SECURITY, security := self.security.strip().upper()):
            raise ValueError(_(CHOOSE_SECURITY))
        if not (price := plain(self.price, "price")):
            raise ValueError(
                _("price: type a number above zero, for example {price}").format(
                    price=format_number(80.12, 2)
                )
            )
        return security, (self.day, float(price))


# the toast of a typed price by whether it replaced one and whether units are held at it
RECEIPTS = {
    (False, False): N_("Added {name} at {price} per unit on {day}"),
    (True, False): N_("Added {name} at {price} per unit on {day}, in place of {old}"),
    (False, True): N_(
        "Added {name} at {price} per unit on {day}: the {units} units held are worth {value}"
    ),
    (True, True): N_(
        "Added {name} at {price} per unit on {day}, in place of {old}: the {units} units held "
        "are worth {value}"
    ),
}


def receipt(name: str, point: prices.Price, units: float, replaced: float | None) -> str:
    """The toast of a typed price: the value of the units held at it shows a slip of a mark."""
    day, price = point
    return _(RECEIPTS[replaced is not None, bool(units)]).format(
        name=name,
        price=format_eur(price, cents=True),
        day=day,
        old=format_eur(replaced or 0.0, cents=True),
        units=decimal_mark(f"{units:.12g}"),
        value=format_eur(units * price, cents=True),
    )


def recorded(observed: list[Observation]) -> str:
    """What `prices.record` wrote, empty for nothing."""
    if not observed:
        return ""
    return _("Recorded {values}").format(
        values=", ".join(
            _("{asset} {value} as of {day}").format(asset=asset, value=format_eur(value), day=day)
            for day, asset, value in observed
        )
    )


def mapper(table: csvimport.Table, key: str, value: str = N_("Price")) -> csvimport.Mapping:
    """The column mapping of a CSV of dated values (`csvcolumns.select`), the guess preselected;
    `value` names the value column, a message of the catalogue. Raises ValueError for a table
    without a column of dates or numbers."""
    guessed = csvimport.guess(table)
    fields = {
        "date": ColumnPick(N_("Date"), guessed.date),
        "value": ColumnPick(value, guessed.value),
        "currency": ColumnPick(N_("Currency"), guessed.currency, N_("none: read as EUR")),
    }
    at, dates, decimal = select(table, key, fields, guessed.dates, guessed.decimal)
    return csvimport.Mapping(
        at["date"] if at["date"] is not None else guessed.date,
        at["value"] if at["value"] is not None else guessed.value,
        decimal,
        dates,
        at["currency"],
    )


def _choose(
    securities: prices.Securities, key: str, chosen: str | None = None, *, empty: bool = False
) -> str:
    """The ISIN or symbol of a security, `chosen` first selected, or none with `empty`."""
    options = list(securities.names)
    security = st.selectbox(
        _("Security"),
        options,
        index=None if empty else options.index(chosen) if chosen in options else 0,
        format_func=lambda i: str(securities.names.get(i, i)),
        accept_new_options=True,
        placeholder=_("Choose or type an ISIN or symbol"),
        key=key,
    )
    return (security or "").strip().upper()


def _add(data_dir: Path, securities: prices.Securities) -> None:
    """The form `Add a price`, saved at once. A new form after a save, empty but for the
    security, which the next price is likely for too."""
    n = st.session_state.setdefault(FORM, 0)
    key, today = f"{FORM}-{n}", date.today()
    with st.form(key, border=False):
        security = _choose(securities, f"{key}-security", st.session_state.get(CHOSEN))
        with st.container(horizontal=True, wrap=True, vertical_alignment="bottom"):
            day = st.date_input(
                _("Date"),
                today,
                min_value=date(1970, 1, 1),
                max_value=today,
                format="YYYY-MM-DD",
                key=f"{key}-date",
                width=140,
            )
            text = st.text_input(
                _("Price €"),
                key=f"decimal-{key}-price",
                placeholder=format_number(80.12, 2),
                width=120,
            )
            sent = st.form_submit_button(_("Add"), type="primary", key=f"{key}-add")
        st.caption(
            _(
                "The price of one unit on a day, also a past one, saved at once. No thousands "
                "groups: 5432, or {fraction} for a fraction."
            ).format(fraction=decimal_mark("5.4320"))
        )
    if not sent:
        return
    try:
        typed = TypedPrice(security, day if isinstance(day, date) else None, text or "")
        security, point = typed.point(today)
        saved = prices.save(data_dir, security, [point], source=source())
    except (OSError, ValueError) as err:
        st.error(_("Not added: {reason}").format(reason=reason(err)))
        return
    name = securities.names.get(security, security)
    old = saved.replaced[0].old if saved.replaced else None
    change = guard.Change(f"{name} {point[0]}", old, point[1])
    warnings = [
        *([change.warning] if change.warning else []),
        *prices.off_trades(securities.trades.get(security, []), [point]),
    ]
    lines = [
        receipt(name, point, securities.units.get(security, 0.0), old),
        *([_("Check: {warnings}.").format(warnings="; ".join(warnings))] if warnings else []),
        recorded(saved.recorded),
    ]
    st.session_state[FORM], st.session_state[CHOSEN] = n + 1, security
    tell("  \n".join(line for line in lines if line), warn=bool(warnings))
    st.rerun()  # the tiles and the estimates take the new price


def _import(data_dir: Path, securities: prices.Securities) -> None:
    """A downloaded price history of one security: the mapper, a preview, the guard and the
    button that saves it. The security starts empty, also after an import: a preselected one
    took the history of another without a word."""
    n = st.session_state.setdefault(IMPORT, 0)
    security = _choose(securities, f"{IMPORT}-{n}-security", empty=True)
    upload = st.file_uploader(_("Price history (CSV)"), type=["csv", "txt"], key=f"{IMPORT}-{n}")
    if upload is None:
        return
    if not security:
        st.info(_("To read the file, {choose}.").format(choose=_(CHOOSE_SECURITY)))
        return
    if not re.fullmatch(SECURITY, security):
        st.error(_("Not read: {reason}").format(reason=_(CHOOSE_SECURITY)))
        return
    try:
        table = csvimport.sniff(upload.getvalue())
        mapping = mapper(table, IMPORT)
    except ValueError as err:
        st.error(_("Not read: {reason}").format(reason=err))
        return
    parsed = csvimport.parse(table, mapping, today=date.today())
    old = prices.read_prices(prices.price_file(data_dir, security))
    rows, replaced = prices.merge(old, parsed.points)
    _preview(parsed, len(rows) - len(old), len(replaced), currency=mapping.currency is not None)
    name = securities.names.get(security, security)
    changes = [guard.Change(f"{name} {r.day}", r.old, r.new) for r in replaced]
    flagged = [c for c in changes if c.warning]
    notes = [
        _("the import reads {price}").format(price=text)
        for text in prices.off_trades(securities.trades.get(security, []), parsed.points)
    ]
    warn = guard.review(flagged, key=IMPORT, notes=notes, hint=DECIMAL)
    if more := len(changes) - len(flagged):
        st.caption(_("{n} more replaced prices within half to double.").format(n=more))
    count = len(parsed.points)
    label = _("Import {n} prices").format(n=count)
    if not st.button(
        guard.marked(label, warn), key=f"{IMPORT}-save", type="primary", disabled=not count
    ):
        return
    try:
        saved = prices.save(data_dir, security, parsed.points, source=source())
    except (OSError, ValueError) as err:
        st.error(_("Not imported: {reason}").format(reason=reason(err)))
        return
    st.session_state[IMPORT] = n + 1  # a new upload field, empty
    imported = _("Imported {n} prices of {name}: {new} new, {replaced} replaced").format(
        n=count, name=name, new=len(rows) - len(old), replaced=len(saved.replaced)
    )
    tell("  \n".join(line for line in (imported, recorded(saved.recorded)) if line))
    st.rerun()


def _preview(parsed: csvimport.Parsed, added: int, replaced: int, *, currency: bool) -> None:
    """The first and the last three prices, how many, from when to when, and what they replace.
    The refused lines with their reason, the first three."""
    if not parsed.points:
        st.error(_("No price read. {refused}").format(refused=refused(parsed.refused)))
        return
    first, last, count = parsed.points[0][0], parsed.points[-1][0], len(parsed.points)
    read = (
        _("{n} prices from {first} to {last}: {new} new, {replaced} replace a stored price.")
        if currency
        else _(
            "{n} prices from {first} to {last}: {new} new, {replaced} replace a stored price, "
            "read as EUR."
        )
    )
    st.caption(read.format(n=count, first=first, last=last, new=added, replaced=replaced))
    with st.container(key="table-prices-preview"):
        st.table(
            said(
                [
                    {"date": str(day), "price": format_eur(price, cents=True)}
                    for day, price in ends(parsed.points)
                ],
                HEADERS,
            ),
            hide_index=True,
        )
    if parsed.refused:
        st.caption(
            _("{n} lines refused: {refused}").format(
                n=len(parsed.refused), refused=refused(parsed.refused)
            )
        )


def unpriced(securities: prices.Securities, rows: list[dict[str, str | int]]) -> list[str]:
    """The names of the held securities without a price among the `stored` rows: the asset that
    holds one has no estimate."""
    return [str(r["security"]) for r in rows if r[CODE] in securities.units and not r["price"]]


def section(
    data_dir: Path, securities: prices.Securities, rows: list[dict[str, str | int]]
) -> None:
    """The expander of the `stored` rows, open at first while a held security has no price."""
    with st.expander(_("Prices"), expanded=bool(unpriced(securities, rows)), key=OPEN):
        if rows:
            with st.container(key="table-prices"):
                st.table(said(rows, HEADERS), hide_index=True)
        st.caption(
            _(
                "The price per unit in euros of each security, from a downloaded price history or "
                "typed in. Gold (XAU, per troy ounce) and Bitcoin (BTC) take the last month of "
                "their series when it is newer. A depot whose securities all "
                "have a price gets an estimate, and each save records its value at the last "
                "prices, dated with the oldest of them."
            )
        )
        st.markdown(f"**{_('Add a price')}**")
        _add(data_dir, securities)
        st.markdown(f"**{_('Import a price history')}**")
        st.caption(
            _(
                "A CSV of dates and prices of one security, for example the download of an "
                "exchange or a bank. Euros only: a currency column with another currency refuses "
                "the line."
            )
        )
        _import(data_dir, securities)
    keyboard()
