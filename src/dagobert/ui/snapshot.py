"""Record observed asset values: updates `assets.yaml` and appends to `history.csv`. The columns
of the grid keep English ids, which the column configs head in words (rule `i18n`)."""

from __future__ import annotations

from datetime import date
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple

import pandas as pd
import streamlit as st

from dagobert import carry, prices
from dagobert.history import Observation
from dagobert.i18n import N_, _, ngettext, pgettext
from dagobert.loader import load_plan
from dagobert.lots import book
from dagobert.model.assets import Assets, AvDepot, Loan, PensionPolicy, TermDeposit, Trade
from dagobert.model.plan import Plan
from dagobert.money import EUR_COLUMN
from dagobert.scenariofiles import first_scenario, scenario_file
from dagobert.store import RowEdits, RowFile
from dagobert.ui import (
    fold,
    gridcolumns,
    guard,
    is_mobile,
    page_link,
    pricing,
    save,
    summary,
    tables,
    tell,
)
from dagobert.ui.assets import opened
from dagobert.ui.save import value_field, worth

SAME = "unchanged"  # the checkbox that confirms the current value as observed
# what to enter first, then what to check: `new` beside `current` and `estimate` on a phone too
COLUMNS = ("asset", "current", "estimate", "new", SAME, "asof", "kind", "measure", "cost_basis")
# what `current` and `new` hold, by the value field of the asset
MEASURES = {"value": N_("value"), "balance": N_("balance"), "per_sqm": N_("price per m²")}
PHONE_ASSET = 140  # pixels of the pinned name on a phone: current, estimate and new fit beside it
PHONE_NAME = 19  # characters of a name that fit the pinned column, 3 less beside the mark
KIND_WIDTH = 160  # pixels of the kind: the longest in words, `Altersvorsorgedepot`, fits
# on the name of an asset that needs an update: no red reaches 4.5:1 on both themes, and the
# pinned column of a phone mutes it, so the name stays gray there
STALE_MARK = "⚠ "
Cells = dict[int, dict[str, float | bool | None]]  # entered cells by table row
GRID = "snapshot"  # the key of the grid: its nonce, its base (`save.base`)
TAKEN = "snapshot-taken"  # the estimates that `Take estimates` filled in, by nonce
IDENTITY = ("id",)  # names an asset row
# why an entry is not saved, by its column (`unchanged` counts as `new`), see `takes`
REFUSED = {
    "new": N_("A term deposit takes its value from its contract, not saved for {names}."),
    "cost_basis": N_("A cost basis is for a depot without trades only, not saved for {names}."),
}
# why `Take estimates` leaves an empty `new` cell, see `take_estimates`
DEPOSIT = N_("term deposit: its value is the amount invested, without interest")
EQUAL = N_("equal to the current value: tick unchanged to confirm it")
HOW = N_(
    "- **current** is the value in your inputs, **estimate** what the app expects today: a loan "
    "after its scheduled payments, a term deposit with its interest so far, a pension policy or "
    "depot with the mean return of its class and the contributions since its date, an asset with "
    "trades at the last prices of its securities. For gold (XAU) and Bitcoin (BTC) that is the "
    "last month of their series when it is newer than your last price.\n"
    "- **new** takes the value that you observed: for a loan its balance, with or without the "
    "minus, for a property the price per m² (see **measure**). A term deposit takes none: its "
    "contract gives the value.\n"
    "- **unchanged** confirms a value that is still correct: **Record** dates it with the day "
    "above, without a new value.\n"
    "- **⚠** marks a value that needs an update, as in the attention table of the Overview: its "
    "date (**as of**, `asof` in the files) is older than the update interval of the asset, or it "
    "has none (**never**). The interval is **check every** on the Assets page, else 12 months, "
    "never for a term deposit or a property. The links below the table open each such asset on "
    "the Assets page, where its **as of** takes any date.\n"
    "- **Take estimates** fills the empty **new** cells from **estimate**. It skips a term "
    "deposit and an estimate equal to the current value, and its message names them.\n"
    "- **cost basis** is what you paid for a depot without trades. A depot with trades takes it "
    "from them.\n"
    "- A price saved under **Prices** also records the value of each asset whose securities "
    "all have a price, dated with the oldest of those prices."
)


def asset_cell(name: str, *, stale: bool, phone: bool) -> str:
    """The `asset` cell: `STALE_MARK` before the name of an asset that needs an update. On a
    phone a long name keeps its start and its end in the pinned column, which tells two loans of
    one bank apart."""
    mark, room = (STALE_MARK, PHONE_NAME - 3) if stale else ("", PHONE_NAME)
    if not phone or len(name) <= room:
        return mark + name
    return f"{mark}{name[: room - room // 2 - 1]}…{name[-(room // 2) :]}"


def takes(row: dict[str, Any], column: str) -> bool:
    """Whether the asset of `row` takes an entry in `column`. A `cost_basis` only an equity asset
    without trades: the model rejects it on any other row. A value, new or `unchanged`, not a term
    deposit: its `value` is the amount invested, and the history counts its interest."""
    if column == "cost_basis":
        return row["kind"] == "equity" and not row.get("trades")
    return column not in ("new", SAME) or row["kind"] != "term_deposit"


def _entered(column: str, value: float | bool | None) -> bool:
    """Whether a cell holds an entry: a number, or a ticked `unchanged`."""
    if column == SAME:
        return value is True
    return value is not None and not pd.isna(value)


def stray(shown: list[tuple[int, dict[str, Any]]], entered: Cells) -> dict[str, list[str]]:
    """The assets with an entry that they do not take (`takes`), by its column, `unchanged` as
    `new` (`REFUSED`): `snapshot_edits` drops it, so one stray cell does not block the others."""
    found: dict[str, list[str]] = {}
    for position, cells in sorted(entered.items()):
        row = shown[position][1]
        for column in dict.fromkeys(
            "new" if k == SAME else k
            for k, v in cells.items()
            if _entered(k, v) and not takes(row, k)
        ):
            found.setdefault(column, []).append(_label(row))
    return found


class Estimate(NamedTuple):
    """What the app expects today (`estimate`): the value, of a dated pension policy also its
    `paid`, the contributions by the day."""

    value: float | None = None
    paid: float | None = None


def estimate(data_dir: Path, row: dict[str, Any], day: date, plan: Plan) -> Estimate:
    """Accrued deposit, the lots of the trades at the last price (`prices.last_price`: of gold
    and Bitcoin also their series), or a value carried from its `asof` in the main scenario
    `plan`: a scheduled loan balance, a pension policy with its `paid` or a depot
    (`carry`)."""
    if row["kind"] == "term_deposit":
        return Estimate(round(TermDeposit.model_validate(dict(row)).value_at(day), 2))
    if row.get("trades"):
        priced = prices.market_value(
            data_dir, book(Trade.model_validate(t) for t in row["trades"]).open
        )
        return Estimate(None if priced is None else round(priced[0], 2))
    if row.get("asof") is None:
        return Estimate()
    refinance = plan.assumptions.refinance_rate
    match row["kind"]:
        case "loan":
            carried = Loan.model_validate(dict(row)).balance_at(day, refinance)
        case "bav":
            carried, paid = carry.policy(plan, PensionPolicy.model_validate(dict(row)), day)
            return Estimate(round(carried, 2), round(paid, 2))
        case "av_depot":
            carried = carry.depot(plan, AvDepot.model_validate(dict(row)), day)
        case _:
            carried = None
    return Estimate(None if carried is None else round(carried, 2))


def snapshot_edits(
    shown: list[tuple[int, dict[str, Any]]], estimates: list[Estimate], entered: Cells, day: date
) -> tuple[RowEdits, list[Observation]]:
    """File edits and history values for the cells entered per table row. `shown` holds the
    file index and the row per table row. A value in `new` or a ticked `unchanged`, which
    observes the current value, gives a new `asof` and a history row; a cost basis alone keeps
    the date of the value. A pension policy takes with its new `asof` the `paid` of its estimate:
    `paid` counts the contributions by `asof`. An entry that the row does not take is left out
    (`stray`)."""
    edits = RowEdits()
    history: list[Observation] = []
    for position, cells in entered.items():
        i, row = shown[position]
        taken = {k: v for k, v in cells.items() if _entered(k, v) and takes(row, k)}
        same = bool(taken.pop(SAME, False))
        changes = save.signed(
            {value_field(row) if k == "new" else k: v for k, v in taken.items()},
            [("balance",)],  # of a loan
        )
        if not (changes or same):
            continue
        observed = "new" in taken or same
        paid = estimates[position].paid
        moved = {} if not observed or paid in (None, row.get("paid", 0.0)) else {"paid": paid}
        edits.edited[i] = changes | ({"asof": day} if observed else {}) | moved
        if observed:
            value = changes.get(value_field(row), row[value_field(row)])
            history.append((day, row["id"], worth(row, value)))
    return edits, history


def take_estimates(
    shown: list[tuple[int, dict[str, Any]]], estimates: list[Estimate], entered: Cells
) -> tuple[Cells, dict[str, list[str]]]:
    """`entered` with the empty `new` cells filled from `estimates`, and the assets that keep an
    empty cell, by the reason. A term deposit (`DEPOSIT`): its `value` is the amount invested,
    the estimate adds the interest. An asset whose estimate is its value (`EQUAL`), for example a
    depot that `prices.record` recorded: a new `asof` would claim a later observation, which a
    tick of `unchanged` confirms. A row with a ticked `unchanged` stays as it is."""
    filled, skipped = dict(entered), dict[str, list[str]]()
    for position, ((_i, row), (estimated, _paid)) in enumerate(zip(shown, estimates, strict=True)):
        cells = entered.get(position, {})
        if estimated is None or any(_entered(k, cells.get(k)) for k in ("new", SAME)):
            continue
        if reason := (
            DEPOSIT
            if row["kind"] == "term_deposit"
            else EQUAL
            if estimated == row[value_field(row)]
            else None
        ):
            skipped.setdefault(reason, []).append(_label(row))
        else:
            filled[position] = cells | {"new": estimated}
    return filled, skipped


def took(count: int, skipped: dict[str, list[str]]) -> str:
    """The message of `Take estimates`: how many it took, and which it skipped and why."""
    if not skipped:
        return ngettext("Took {n} estimate", "Took {n} estimates", count).format(n=count)
    return ngettext(
        "Took {n} estimate, skipped {skipped}: {why}",
        "Took {n} estimates, skipped {skipped}: {why}",
        count,
    ).format(
        n=count,
        skipped=sum(map(len, skipped.values())),
        why="; ".join(f"{', '.join(names)} ({_(reason)})" for reason, names in skipped.items()),
    )


def page(file: RowFile) -> None:
    tables.save_in_header("snapshot-save")
    st.title(_("Snapshot"))
    summary.tiles(file.data_dir, "snapshot")
    st.caption(
        _(
            "Type each value that you see today in **new**, tick **unchanged** for one that is "
            "still correct, then press **Record** at the top."
        )
    )
    phone = is_mobile()
    securities = prices.Securities.of(file.data_dir)
    stored = pricing.stored(file.data_dir, securities)
    if missing := pricing.unpriced(securities, stored):
        st.info(
            _(
                "No price yet for {securities}: add one under **Prices** below the table, then "
                "its asset gets an estimate."
            ).format(securities=", ".join(missing))
        )
    day = st.date_input(
        _("Observed on"), date.today(), format="YYYY-MM-DD", key="snapshot-day", width=200
    )
    base, changed = save.base(file, GRID, _part, _held)
    rows, nonce = base.rows, base.nonce
    shown = [(i, rows[i]) for i in _order(rows)]
    units, names = gridcolumns.asset_units(), gridcolumns.asset_names()
    if changed is not None:
        save.warn(changed, key=GRID, identity=IDENTITY, units=units, names=names)
    widget = f"{GRID}-{nonce}"
    taken: Cells = st.session_state.get(TAKEN, {}).get(nonce, {})
    plan = load_plan(file.data_dir, file.data_dir / scenario_file(first_scenario(file.data_dir)))
    estimates = [estimate(file.data_dir, r, day, plan) for _i, r in shown]
    on_sale = summary.selling(plan.scenario)
    # of the rows that the grid shows, also of an asset that another device removed since
    assets = Assets.model_validate({"assets": rows}).assets
    old = [summary.needs_update(assets[i], day, on_sale) for i, _r in shown]
    table = pd.DataFrame(
        {
            "asset": [
                asset_cell(_label(r), stale=flag, phone=phone)
                for (_i, r), flag in zip(shown, old, strict=True)
            ],
            "kind": [_(summary.KINDS[r["kind"]]) for _i, r in shown],
            "asof": [
                str(r.get("asof") or (_("never") if flag else ""))
                for (_i, r), flag in zip(shown, old, strict=True)
            ],
            "measure": [_(MEASURES[value_field(r)]) for _i, r in shown],
            "current": [float(r[value_field(r)]) for _i, r in shown],
            "estimate": [e.value for e in estimates],
            SAME: pd.Series(
                [taken.get(i, {}).get(SAME) is True for i in range(len(shown))], dtype=bool
            ),
        }
        | {
            column: pd.Series(
                [taken.get(i, {}).get(column) for i in range(len(shown))], dtype=float
            )
            for column in ("new", "cost_basis")
        }
    )
    money = partial(st.column_config.NumberColumn, format=EUR_COLUMN)
    config = {
        "asset": st.column_config.TextColumn(_("asset"), width=PHONE_ASSET if phone else None),
        "current": money(_("current"), help=_("The value in your inputs")),
        "estimate": money(
            _("estimate"), help=_("What the app expects today, see How the columns work")
        ),
        "new": money(_("new"), help=_("The value that you observed. A term deposit takes none.")),
        SAME: st.column_config.CheckboxColumn(
            _("unchanged"),
            help=_("Still correct: Record dates the current value with the day above"),
        ),
        "asof": st.column_config.TextColumn(_("as of"), help=_("The date of the current value")),
        "kind": st.column_config.TextColumn(_("kind"), width=KIND_WIDTH),
        "measure": st.column_config.TextColumn(_("measure"), help=_("What current and new hold")),
        "cost_basis": money(
            _("cost basis"), help=_("What you paid, for a depot without trades only")
        ),
    }
    tables.pin(config, "asset")
    st.data_editor(
        table.style.apply(
            lambda column: [summary.STALE_STYLE if flag else "" for flag in old],
            subset=["asof"] if phone else ["asset", "asof"],
        ),
        disabled=["asset", "kind", "asof", "measure", "current", "estimate"],
        column_config=config,
        column_order=COLUMNS,
        hide_index=True,
        height="content",
        placeholder="",
        key=widget,
    )
    if stale := [r for (_i, r), flag in zip(shown, old, strict=True) if flag]:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(_("⚠ Edit the value and its date on the Assets page:"))
            for r in stale:
                page_link("Assets", _label(r), opened(r["id"], value_field(r), "asof"))
    fold(_(HOW), _("How the columns work"))
    edited = {int(i): c for i, c in st.session_state[widget].get("edited_rows", {}).items()}
    entered = {i: taken.get(i, {}) | edited.get(i, {}) for i in {*taken, *edited}}
    filled, skipped = take_estimates(shown, estimates, entered)
    edits, history = snapshot_edits(shown, estimates, entered, day)
    for column, refused in stray(shown, entered).items():
        st.warning(_(REFUSED[column]).format(names=", ".join(refused)), icon=":material/warning:")
    flagged = guard.check(
        rows, edits, [i for i, _r in shown], key="snapshot", units=units, names=names
    )
    # A new editor key shows the filled cells: the editor cannot take them as edits. It keeps the
    # base, on whose rows their positions hold.
    if st.button(
        _("Take estimates"), key="snapshot-take", disabled=filled == entered and not skipped
    ):
        count = sum(filled[p] != entered.get(p) for p in filled)
        tell(took(count, skipped), warn=bool(skipped))
        if count:
            st.session_state[TAKEN] = {save.renew(GRID, base): filled}
        st.rerun()
    count = len(edits.edited)
    save.button(
        file,
        edits,
        history,
        read=base.read(IDENTITY),
        label=ngettext("Record {n} change", "Record {n} changes", count).format(n=count)
        if count
        else pgettext("button", "Record"),
        key="snapshot-save",
        nonce_key=f"{GRID}-nonce",
        toast=_("Recorded {values}").format(
            values=", ".join(_label(rows[i]) for i in edits.edited)
        ),
        flagged=flagged,
    )
    pricing.section(file.data_dir, securities, stored)  # a saved price reruns the page


def _label(row: dict[str, Any]) -> str:
    return str(row.get("name") or row["id"])


def _order(rows: list[dict[str, Any]]) -> list[int]:
    """The rows of the grid by kind and name."""
    kinds = list(summary.LIQUIDITY)
    return sorted(
        range(len(rows)), key=lambda i: (kinds.index(rows[i]["kind"]), _label(rows[i]).lower())
    )


def _part(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [rows[i] for i in _order(rows)]


def _held(base: save.Base) -> bool:
    """Whether the grid on `base` holds entries: typed ones or taken estimates."""
    state = st.session_state.get(f"{GRID}-{base.nonce}", {})
    return bool(state.get("edited_rows") or st.session_state.get(TAKEN, {}).get(base.nonce))
