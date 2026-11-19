"""`Close` beside an asset table: a dialog that takes the asset, the day it ended and what it paid
out, and moves it out of the assets as one revision (`closing.apply`); and the list of the closed
assets below the tabs of the Assets page, with `Reopen` (`closing.reopen`)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import closing, i18n, revisions
from dagobert.history import worth
from dagobert.i18n import N_, _
from dagobert.loader import load_assets, load_closed
from dagobert.model.assets import TermDeposit
from dagobert.money import EUR_COLUMN, format_eur
from dagobert.problems import RefusedError
from dagobert.ui import is_mobile, keyboard, language, literal, recording, source, summary, tell
from dagobert.ui.fields import euros
from dagobert.ui.save import reason

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from dagobert.model.assets import Asset

KEY = "close-"
ABOUT = N_(
    "For an asset that ended: a term deposit that paid out, an account that you closed, a loan "
    "that you paid off. It leaves the plan and the tables. The recorded net worth keeps its "
    "values up to that day and counts it as 0 from then. Record the money where it went: the "
    "value of the account that took it, or a new asset with its **opened** day."
)
HELP = N_("End an asset that paid out or that you closed. Its records stay.")
HELD = N_("Save or discard the edits of the table first: a close removes a row.")
CLOSED = N_("Closed assets")
HEADERS = {
    "asset": N_("asset"),
    "kind": N_("kind"),
    "ended": N_("ended"),
    "last value": N_("last value"),
    "paid out": N_("paid out"),
}


def ended(asset: Asset, today: date) -> date:
    """The day that the dialog offers: the maturity of a term deposit that matured, else today."""
    return min(asset.matures, today) if isinstance(asset, TermDeposit) else today


def button(data_dir: Path, names: Sequence[str], *, key: str, held: bool) -> None:
    """`Close` beside the table `key` of the assets `names`, off while the table `held` edits."""
    if st.button(
        _("Close"),
        key=f"{key}-close",
        icon=":material/archive:",
        disabled=held or not names,
        help=_(HELD) if held else _(HELP),
    ):
        st.dialog(_("Close an asset"))(_dialog)(data_dir, list(dict.fromkeys(names)), key)


def _dialog(data_dir: Path, names: list[str], table: str) -> None:
    """The asset, the day and the payout, then what the close does or why it is refused. It
    reruns alone, without `main.py`: it takes the language of the session first."""
    i18n.activate(language())
    st.caption(_(ABOUT))
    assets = {a.id: a for a in load_assets(data_dir) if a.id in names}
    chosen = st.selectbox(
        _("Asset"), list(assets), format_func=lambda i: assets[i].label, key=f"{KEY}{table}-asset"
    )
    if chosen is None:
        return
    asset, today = assets[chosen], date.today()
    # keyed by the asset: another one starts from its own day and value
    day = st.date_input(
        _("Ended on"), ended(asset, today), max_value=today, key=f"{KEY}{table}-{chosen}-day"
    )
    last = abs(worth(asset, day))
    text = st.text_input(
        _("Paid out €"),
        f"{last:.2f}".replace(".", ","),
        key=f"decimal-{KEY}{table}-{chosen}-payout",
        help=_("What you got at its end, after tax where the bank withheld it. 0 for none."),
    )
    keyboard()
    close = None if (payout := euros(text)) is None else closing.Close(chosen, day, payout)
    refused = _("type the amount in euros") if close is None else _refusal(data_dir, close)
    if refused:
        st.error(_("Refused: {reason}.").format(reason=literal(refused)), icon=":material/block:")
    elif close is not None:
        st.markdown(
            _(
                "**{name}** ends on {day}: last value {last}, paid out {payout}. From then it "
                "counts as 0."
            ).format(
                name=literal(asset.label),
                day=day,
                last=format_eur(last, cents=True),
                payout=format_eur(close.payout, cents=True),
            )
        )
    if (
        not st.button(_("Close"), key=f"{KEY}confirm", type="primary", disabled=bool(refused))
        or close is None
    ):
        return
    try:
        with recording():  # a dialog reruns alone, without `main.py`
            closing.apply(data_dir, close, source=source(str(close)))
    except (OSError, ValueError, RefusedError) as err:
        st.error(_("Not saved: {reason}").format(reason=literal(reason(err))))
        return
    tell(_("Closed {name}").format(name=asset.label))
    st.rerun()


def _refusal(data_dir: Path, close: closing.Close) -> str:
    """Why the close is refused now (English, as an input error), empty when it is not."""
    try:
        closing.check(data_dir, close)
    except ValueError as err:
        return str(err)
    return ""


def rows(data_dir: Path) -> list[dict[str, object]]:
    """The closed assets, the last one first: name, kind, day, the value at its end and the
    payout."""
    return [
        {
            "asset": c.asset.label,
            "kind": _(summary.KINDS[c.asset.kind]),
            "ended": c.ended.isoformat(),
            "last value": worth(c.asset, c.ended),
            "paid out": c.payout,
        }
        for c in sorted(load_closed(data_dir), key=lambda c: c.ended, reverse=True)
    ]


def closed(data_dir: Path) -> None:
    """The closed assets in a fold below the tabs, none without one, and `Reopen`, which moves
    one back into its table as it was."""
    if not (found := load_closed(data_dir)):
        return
    with st.expander(f"{_(CLOSED)} ({len(found)})", key="assets-closed"):
        st.dataframe(
            rows(data_dir),
            hide_index=True,
            height="content" if is_mobile() else "auto",
            column_config={
                name: st.column_config.NumberColumn(_(words), format=EUR_COLUMN)
                if name in ("last value", "paid out")
                else st.column_config.TextColumn(_(words))
                for name, words in HEADERS.items()
            },
        )
        labels = {c.asset.id: c.asset.label for c in found}
        with st.container(horizontal=True, vertical_alignment="bottom"):
            asset = st.selectbox(
                _("Asset"), list(labels), format_func=lambda i: labels[i], key="assets-closed-asset"
            )
            pressed = st.button(
                _("Reopen"),
                key="assets-closed-reopen",
                icon=":material/unarchive:",
                help=_("Move the asset back into its table as it was, for a close by mistake."),
            )
        if not pressed or asset is None:
            return
        try:
            closing.reopen(data_dir, asset, source=source(f"reopen {asset}"))
        except (OSError, ValueError, revisions.ConflictError) as err:
            st.error(_("Not saved: {reason}").format(reason=literal(reason(err))))
            return
        tell(_("Reopened {name}").format(name=labels[asset]))
        st.rerun()
