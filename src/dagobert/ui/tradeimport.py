"""The import of a broker export into the trades of an asset, above the trades grid of the
`securities` tab of the Assets page: the upload, the columns, a preview, the save guard and the
button that adds the new trades as one revision (`tradeimport`). Its words are messages of the
catalogue, the cells of the preview keep English ids, which `HEADERS` gives in words."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING, Any

import streamlit as st

from dagobert import csvimport, lots, revisions, tradeimport
from dagobert.i18n import N_, _, ngettext
from dagobert.model.assets import Trade
from dagobert.money import format_eur, format_number
from dagobert.ui import fold, guard, joined, source, tell
from dagobert.ui.csvcolumns import DECIMAL, ColumnPick, ends, of_file, refused, said, select
from dagobert.ui.save import REFUSED, changed_at, reason
from dagobert.ui.tables import unsaved
from dagobert.ui.tradeform import CODE, WAIT

if TYPE_CHECKING:
    from dagobert.model.assets import HoldingsAsset
    from dagobert.store import RowFile
    from dagobert.ui.tables import Table

# the select box of each field of `tradeimport.ALIASES`, and the words of no column
FIELDS = {
    "date": ColumnPick(N_("Date"), None),
    "kind": ColumnPick(N_("Kind"), None, N_("none (minus = sale)")),
    "security": ColumnPick(CODE, None),
    "units": ColumnPick(N_("Units"), None),
    "amount": ColumnPick(N_("Amount €"), None),
    "fees": ColumnPick(N_("Fees €"), None, N_("none")),
    "name": ColumnPick(N_("Name"), None, N_("none")),
    "currency": ColumnPick(N_("Currency"), None, N_("none: read as EUR")),
    "status": ColumnPick(N_("Status"), None, N_("none: every row")),
}
# the columns of the preview by their ids, in words
HEADERS = {
    "security": N_("security"),
    CODE: CODE,
    "new trades": N_("new trades"),
    "units": N_("units"),
    "date": N_("date"),
    "kind": N_("kind"),
    "price": N_("price"),
    "amount": N_("amount"),
    "fees": N_("fees"),
    "line": N_("line"),
    "left out as": N_("left out as"),
    "row": N_("row"),
}
HELP = N_(
    "A CSV export of the buys and sales of a broker, in euros. The trades that the asset holds "
    "already are left out."
)
# where the brokers whose exports `tradeimport.ALIASES` follows put them
WHERE = N_(
    "- **Trade Republic**: in the app (since April 2026), Profile > Account statements > "
    "Transaction export (Kontoauszüge > Transaktionsexport), then the period and Create.\n"
    "- **Scalable Capital**: in the transactions of the broker, select all and export them as CSV "
    "(PRIME and PRIME+).\n"
    "- **comdirect**: the Depotumsätze of the depot as CSV.\n"
    "- **Another broker**: a CSV of its buys and sales, one per row: choose its columns after the "
    "upload."
)
NOT_READ = N_(
    "Check that this is the export of the transactions (CSV), not a PDF or the statement of the "
    "cash account."
)
COLUMNS = N_("Check the columns read from the file")


def import_trades(file: RowFile, table: Table) -> None:
    """The expander `Import trades` above the trades grid `table` of the asset whose trades `file`
    holds. It waits for unsaved edits of the grid, and adds only onto the trades that its preview
    was checked against (`RowFile.apply(seen=…)`). A new upload field after an import."""
    key = f"{table.key}-import"
    n = st.session_state.setdefault(key, 0)
    with st.expander(_("Import trades"), icon=":material/upload_file:", key=f"{key}-open"):
        st.caption(_(HELP))
        fold(_(WHERE), _("Where to get the file"))
        upload = st.file_uploader(_("Broker export (CSV)"), type=["csv", "txt"], key=f"{key}-{n}")
        if upload is not None:
            _import(file, table, upload.getvalue(), key)


def _import(file: RowFile, table: Table, raw: bytes, key: str) -> None:
    try:
        csv = csvimport.sniff(raw)
        guessed = tradeimport.guess(csv)
    except ValueError as err:
        st.error(_("Not read: {reason}. {check}").format(reason=err, check=_(NOT_READ)))
        return
    try:
        # folded while the guess found every column that a trade needs
        with st.expander(_(COLUMNS), expanded=bool(guessed.missing), key=of_file(csv, f"{key}-at")):
            columns = mapper(csv, key, guessed)
        if columns.missing:
            labels = joined(_(FIELDS[field].label) for field in columns.missing)
            st.info(_("To read the file, choose the column of {fields}.").format(fields=labels))
            return
        asset, seen = tradeimport.holding(file)
        parsed = tradeimport.read(csv, columns, today=date.today())
    except ValueError as err:
        st.error(_("Not read: {reason}").format(reason=err))
        return
    merged = tradeimport.merge(asset, parsed)
    _preview(asset, csv, parsed, merged)
    slips = tradeimport.slips(file.data_dir, merged.added)
    basis = tradeimport.replaced_basis(asset) if merged.added else None
    notes = [*slips, *filter(None, [basis])]
    warn = guard.review([], key=key, notes=notes, hint=DECIMAL if slips else None)
    # the trades that the preview of the last run was checked against: what the user confirms
    previewed = st.session_state.get(f"{key}-seen")
    st.session_state[f"{key}-seen"] = seen
    count = len(merged.added)
    label = ngettext("Import {n} trade", "Import {n} trades", count).format(n=count)
    held = unsaved(table)  # the import would change the rows of the grid
    if not st.button(
        guard.marked(label, warn),
        key=f"{key}-save",
        type="primary",
        disabled=not count or held,
        help=_(WAIT) if held else None,
    ):
        return
    try:
        tradeimport.save(file, asset, merged.added, previewed or seen, source=source())
    except revisions.ConflictError as err:
        st.error(
            _(
                "Not imported: {changed} since the preview. It shows the trades now: look at it "
                "again."
            ).format(changed=changed_at(err))
        )
        return
    except REFUSED as err:
        st.error(_("Not imported: {reason}").format(reason=reason(err)))
        return
    st.session_state[key] += 1  # a new upload field, empty
    first, last = merged.added[0]["date"], merged.added[-1]["date"]
    added = ngettext(
        "Added {n} trade from {first} to {last}", "Added {n} trades from {first} to {last}", count
    )
    tell(added.format(n=count, first=first, last=last))
    st.rerun()


def mapper(table: csvimport.Table, key: str, guessed: tradeimport.Columns) -> tradeimport.Columns:
    """The columns of a broker export (`csvcolumns.select`), the guess preselected."""
    fields = {name: ColumnPick(f.label, guessed.at[name], f.none) for name, f in FIELDS.items()}
    at, dates, decimal = select(table, key, fields, guessed.dates, guessed.decimal)
    return tradeimport.Columns(at, decimal, dates)


def _preview(
    asset: HoldingsAsset,
    table: csvimport.Table,
    parsed: tradeimport.Parsed,
    merged: tradeimport.Merged,
) -> None:
    """What the import adds, the new trades per security, so that a stray one shows, the first and
    the last three with their price per unit, so that a decimal mark in the wrong place shows.
    Then what it leaves out, the other rows folded, and the first refused lines with their
    reason."""
    found, left = tradeimport.summary(parsed, merged)
    st.caption(f"{found}.")
    names = lots.names([*asset.trades, *map(Trade.model_validate, merged.added)])
    if merged.added:
        with st.container(key="table-trades-import"):
            st.table(said(per_security(merged.added, names), HEADERS), hide_index=True)
            st.table(
                said([shown(row, names) for row in ends(merged.added)], HEADERS), hide_index=True
            )
    if left:
        st.caption(f"{left}.")
    if parsed.others:
        with (
            st.expander(
                _("Other rows left out ({n})").format(n=len(parsed.others)), key="trades-left-out"
            ),
            st.container(key="table-trades-left-out"),
        ):
            st.table(said(others(table, parsed.others), HEADERS), hide_index=True)
    if lines := tradeimport.refused(parsed, merged):
        st.caption(_("Refused: {lines}").format(lines=refused(lines)))


def per_security(rows: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, str]]:
    """Per security of the new trades: how many and the units that they add, net of sales."""
    count, units = defaultdict[str, int](int), defaultdict[str, float](float)
    for row in rows:
        count[row["security"]] += 1
        sign = -1 if row["kind"] == lots.TradeKind.SELL else 1
        units[row["security"]] += sign * row.get("units", 0)
    return [
        {
            "security": names.get(code, code),
            CODE: code,
            "new trades": str(n),
            "units": format_number(units[code], signed=True),
        }
        for code, n in count.items()
    ]


def shown(row: dict[str, Any], names: dict[str, str]) -> dict[str, str]:
    """A new trade as the preview shows it, in the formats of the trades grid: units with a
    decimal point, whole euros, no fees blank. Its price per unit shows a slip of a mark."""
    units, security, fees = row.get("units"), str(row["security"]), row.get("fees", 0)
    return {
        "date": str(row["date"]),
        "kind": str(row["kind"]),
        "security": names.get(security, security),
        "units": "" if units is None else format_number(units),
        "price": "" if units is None else format_eur(row["amount"] / units),
        "amount": format_eur(row["amount"]),
        "fees": format_eur(fees) if fees else "",
    }


def others(table: csvimport.Table, lines: list[tuple[int, str]]) -> list[dict[str, str]]:
    """The rows that are no trade, by their line, with what they are and their cells."""
    cells = dict(table.rows)
    return [
        {
            "line": str(line),
            "left out as": what,
            "row": " · ".join(c.strip() for c in cells.get(line, []) if c.strip()),
        }
        for line, what in lines
    ]
