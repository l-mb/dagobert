"""The `Data` page: a summary of the series that are ready and the optional ones not fetched yet,
then the external series with their months, source note, license and terms, a fetch per series
that has one and the import of a series that takes one (`Series.imports`). Nothing fetches by
itself: a fetch runs only on its button."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import streamlit as st

from dagobert import csvimport, prices, series
from dagobert.i18n import N_, _, ngettext
from dagobert.model.months import add_months
from dagobert.ui import Outcome, fold, guard, mode, source
from dagobert.ui.csvcolumns import ends, refused
from dagobert.ui.pricing import mapper, recorded
from dagobert.ui.save import reason

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

RESULT = "data-result-"  # session state per series: the `Outcome` of its last fetch or import
IMPORT = "data-import-"  # session state per series: a nonce, so a saved import starts empty
INTRO = N_(
    "The prices and rates that the simulation uses. Most ship with Dagobert, two are optional "
    "and come only when you fetch them."
)
READING = N_(
    "Nothing is fetched by itself: the app asks a source only when you press its button. Fetched "
    "months stay in the folder `series/` of your data directory, and an export leaves them out. "
    "An estimate is a month that its source can still revise: the next fetch takes the final "
    "value."
)
# the measures of the survival overlay, as the report names them
LIFE_TABLE_USE = N_(
    "the survival overlay: chance to run out, lifetime, chance of care, chance of disability, "
    "how deep the money falls when it runs out"
)
# what a preview counts against the stored months
NEW, CHANGED, DROPPED = N_("{n} new"), N_("{n} changed"), N_("{n} dropped")


def _month(day: date) -> str:
    return f"{day:%Y-%m}"


def _span(first: date, last: date) -> str:
    return _("{first} to {last}").format(first=_month(first), last=_month(last))


def ranges(months: list[date]) -> str:
    """Sorted months as runs that follow each other: `1969-12 to 2023-12, 2026-09`."""
    runs: list[list[date]] = []
    for month in months:
        if runs and add_months(runs[-1][-1], 1) == month:
            runs[-1].append(month)
        else:
            runs.append([month])
    return ", ".join(_span(run[0], run[-1]) if len(run) > 1 else _month(run[0]) for run in runs)


def held(entry: series.Series, data_dir: Path) -> str:
    """The months of a series, a provisional one, and up to when they ship and were fetched or
    imported (on the date of the file). Empty without months."""
    points = series.read(entry, data_dir)
    if not points:
        return ""
    provisional = ", ".join(_month(p.month) for p in points if p.provisional)
    months = (_("{span}, {months} an estimate.") if provisional else _("{span}.")).format(
        span=_span(points[0].month, points[-1].month), months=provisional
    )
    return f"{months} {_origin(entry, data_dir)}"


def _origin(entry: series.Series, data_dir: Path) -> str:
    """Up to when the months of a series ship, and up to when they were fetched (or imported, for
    a series with `imports`) on the date of the file."""
    shipped = (
        _month(
            entry.parse((series.SHIPPED / entry.shipped).read_text(encoding="utf-8-sig"))[-1].month
        )
        if entry.shipped
        else ""
    )
    path = series.fetched_file(data_dir, entry.name)
    fetched = series.parse_month_value(path.read_text(encoding="utf-8")) if path.exists() else []
    if not fetched:
        return _("Shipped up to {month}.").format(month=shipped) if shipped else ""
    said = (
        (
            _("Shipped up to {month}, fetched or imported up to {fetched} on {day}.")
            if entry.imports
            else _("Shipped up to {month}, fetched up to {fetched} on {day}.")
        )
        if shipped
        else _("Fetched or imported up to {fetched} on {day}.")
        if entry.imports
        else _("Fetched up to {fetched} on {day}.")
    )
    return said.format(
        month=shipped,
        fetched=_month(fetched[-1].month),
        day=date.fromtimestamp(path.stat().st_mtime),
    )


def updated(update: series.Update) -> str:
    """What a fetch changed (`series.Update`) in a sentence."""
    last = _month(update.last) if update.last else ""
    if n := len(update.replaced):
        return ngettext(
            "Replaced the stored months, up to {last}: {n} month differed from the source.",
            "Replaced the stored months, up to {last}: {n} months differed from the source.",
            n,
        ).format(last=last, n=n)
    if n := len(update.added):
        return ngettext(
            "Added {n} month, up to {last}.", "Added {n} months, up to {last}.", n
        ).format(last=last, n=n)
    return (
        _("Already current, up to {last}.").format(last=last)
        if last
        else _("Already current, no months.")
    )


def chain(data_dir: Path) -> str:
    """How `series.cpi` joins the two consumer price series."""
    first = series.read(series.SERIES["vpi"], data_dir)[0].month
    return _(
        "The app joins the two consumer price series: West Germany up to {last}, rescaled to the "
        "VPI level of {first}."
    ).format(last=_month(add_months(first, -1)), first=_month(first))


def conversion(data_dir: Path) -> str:
    """How `series.in_euros` converts the dollar series."""
    first = series.read(series.SERIES["usd-eur"], data_dir)[0].month
    return _(
        "The app converts gold and Bitcoin to euros, month by month: from {first} at the ECB "
        "rate, before that at the Deutsche Mark rate and {rate} DEM per euro. A month after the "
        "last rate takes the last one."
    ).format(first=_month(first), rate=f"{series.DEM_PER_EUR:.5f}")


NOTES = {"vpi": chain, "usd-eur": conversion}  # a caption below the series


def needed(data_dir: Path) -> dict[str, str]:
    """The series without months that the assets need, each with the symbol that they hold without
    a price of its own: Bitcoin before its first fetch, while no price file values it."""
    units = prices.Securities.of(data_dir).units
    return {
        symbol.series: code
        for code, symbol in prices.BY_SYMBOL.items()
        if units.get(code, 0) > 0 and prices.last_price(data_dir, code) is None
    }


def summary(data_dir: Path, wanted: Mapping[str, str]) -> str:
    """How many series hold months, and the optional ones that do not yet, with their use, first
    those that the assets need (`needed`): those that ship always do. A series by the part of its
    title before the first comma."""
    missing = sorted(
        (e for e in series.SERIES.values() if not series.read(e, data_dir)),
        key=lambda e: e.name not in wanted,
    )
    if not missing:
        return _("All {n} series are ready.").format(n=len(series.SERIES))
    optional = "; ".join(
        (
            _("{title}, for {use}: your assets hold {code} without a price")
            if e.name in wanted
            else _("{title}, for {use}")
        ).format(title=_(e.title).split(",")[0], use=_(e.used_by), code=wanted.get(e.name))
        for e in missing
    )
    return _("{ready} of {n} series are ready. Optional, not fetched yet: {optional}.").format(
        ready=len(series.SERIES) - len(missing), n=len(series.SERIES), optional=optional
    )


def _terms(used_by: str, held: series.Series | series.LifeTableFile, name: str = "") -> None:
    """What uses a series and its source note, which its terms require in the product; the
    license, the links and the name of the command line behind `License and source`."""
    used = _("Used for {use}.").format(use=_(used_by))
    st.caption(f"{used}  \n{_('Source note: {note}').format(note=held.attribution)}")
    with st.expander(_("License and source"), key=f"data-terms-{name or 'life-table'}"):
        st.markdown(
            _("License: {licence}. {source}.").format(
                licence=f"[{_(held.licence)}]({held.terms})",
                source=f"[{_('Source')}]({held.source})",
            )
        )
        if name:
            st.caption(
                _("Its name in the command `dagobert series` and in `series/`: `{name}`.").format(
                    name=name
                )
            )


def _fetch(entry: series.Series, data_dir: Path) -> None:
    """The button: a fetch and the values that it records, then a rerun with its outcome for
    `_series`."""
    if st.button(_("Fetch missing months"), key=f"data-fetch-{entry.name}"):
        with st.spinner(_("Fetching {title}…").format(title=_(entry.title))):
            try:
                # the getter is looked up at the click: tests replace it
                fetched = prices.fetch_series(entry, data_dir, series.http_get, source=source())
                told = [updated(fetched.update)]
                if values := recorded(fetched.recorded):
                    told.append(f"{values}.")
                result = Outcome(ok=True, text=" ".join(told))
            except series.FetchError as err:
                result = Outcome(ok=False, text=str(err))
            except (OSError, ValueError) as err:  # a record that the inputs refuse
                result = Outcome(ok=False, text=_("Not saved: {reason}").format(reason=reason(err)))
        st.session_state[RESULT + entry.name] = result
        st.rerun()  # the months above take the fetch


def _import(entry: series.Series, data_dir: Path) -> None:
    """A downloaded history of the index: the mapper, a preview of the months and the button that
    replaces the fetched months with them."""
    key = IMPORT + entry.name
    n = st.session_state.setdefault(key, 0)
    with st.expander(_("Import a CSV"), key=f"{key}-open"):
        st.caption(
            _(
                "A history of the index in euros, or of an ETF that tracks it: for example the "
                "download of the MSCI end of day index data or the price history of an exchange. "
                "The last value of each month counts, and the months must follow each other. The "
                "import replaces all stored months. A later fetch replaces the whole import when "
                "one of its final months differs from the source, as it does for another index or "
                "an ETF."
            )
        )
        upload = st.file_uploader(_("History (CSV)"), type=["csv", "txt"], key=f"{key}-{n}")
        if upload is None:
            return
        try:
            table = csvimport.sniff(upload.getvalue())
            mapping = mapper(table, key, value=N_("Value"))
        except ValueError as err:
            st.error(_("Not read: {reason}").format(reason=err))
            return
        today = date.today()
        parsed = csvimport.parse(table, mapping, today=today)
        months = series.month_ends(parsed.points, today=today)
        importable, warns = _preview(
            entry, data_dir, months, parsed.refused, currency=mapping.currency is not None
        )
        count = len(months)
        label = ngettext("Import {n} month", "Import {n} months", count).format(n=count)
        if not st.button(
            guard.marked(label, warns),
            key=f"data-save-{entry.name}",
            type="primary",
            disabled=not importable,
        ):
            return
        try:
            series.save(entry, data_dir, months)
        except (OSError, ValueError) as err:
            st.error(_("Not saved: {reason}").format(reason=reason(err)))
            return
    st.session_state[key] = n + 1  # a new upload field, empty
    st.session_state[RESULT + entry.name] = Outcome(
        ok=True,
        text=ngettext(
            "Imported {n} month, up to {last}.", "Imported {n} months, up to {last}.", count
        ).format(n=count, last=_month(months[-1].month)),
    )
    st.rerun()


def _preview(
    entry: series.Series,
    data_dir: Path,
    months: list[series.Point],
    rejected: list[tuple[int, str]],
    *,
    currency: bool,
) -> tuple[bool, bool]:
    """How many months from when to when, what they change, the first and last three, and the
    first three refused lines with their reason. An error for a gap, a warning for the stored
    months that go or change. Whether the months can be imported, and whether it warns."""
    if not months:
        st.error(_("No value read. {lines}").format(lines=refused(rejected)))
        return False, False
    known = {p.month: p.value for p in series.read(entry, data_dir)}
    dropped = sorted(known.keys() - {p.month for p in months})
    changed = sum(known.get(p.month, p.value) != p.value for p in months)
    counts = {
        NEW: sum(p.month not in known for p in months),
        CHANGED: changed,
        DROPPED: len(dropped),
    }
    effect = ", ".join(_(said).format(n=n) for said, n in counts.items() if n) or _("no change")
    n = len(months)
    st.caption(
        (
            ngettext(
                "{n} month from {first} to {last}: {effect}.",
                "{n} months from {first} to {last}: {effect}.",
                n,
            )
            if currency
            else ngettext(
                "{n} month from {first} to {last}: {effect}, read as EUR.",
                "{n} months from {first} to {last}: {effect}, read as EUR.",
                n,
            )
        ).format(n=n, first=_month(months[0].month), last=_month(months[-1].month), effect=effect)
    )
    if found := series.gap(months):
        st.error(_("Not importable: {gap}. The months must follow each other.").format(gap=found))
    lost = [_("{months} go, the file lacks them").format(months=ranges(dropped))] if dropped else []
    lost += (
        [
            ngettext("another value in {n} month", "another value in {n} months", changed).format(
                n=changed
            )
        ]
        if changed
        else []
    )
    if lost:
        st.warning(
            _(
                "The import replaces all stored months, since an ETF and the index differ in "
                "scale: {lost}."
            ).format(lost="; ".join(lost)),
            icon=":material/warning:",
        )
    with st.container(key="table-data-preview"):
        st.table(
            [
                {
                    _("month"): _("{month} provisional").format(month=_month(p.month))
                    if p.provisional
                    else _month(p.month),
                    _("value"): f"{p.value:.2f}",
                }
                for p in ends(months)
            ],
            hide_index=True,
        )
    if rejected:
        st.caption(
            ngettext(
                "{n} line refused: {lines}", "{n} lines refused: {lines}", len(rejected)
            ).format(n=len(rejected), lines=refused(rejected))
        )
    return not found, bool(lost)


SNAPSHOT = mode.Item(mode.Sort.PAGE, ("Snapshot",))
# the warning of a series that assets need, by whether the Snapshot page shows
UNPRICED = {
    True: N_(
        "Not fetched yet, and your assets hold {code} without a price of their own: fetch it, or "
        "type in a price on the Snapshot page, to value them."
    ),
    False: N_(
        "Not fetched yet, and your assets hold {code} without a price of their own: fetch it, or "
        "update their value on the Assets page, to value them."
    ),
}


def _series(entry: series.Series, data_dir: Path, wanted: Mapping[str, str]) -> None:
    with st.container(border=True, key=f"data-{entry.name}"):
        text = held(entry, data_dir)
        later = (
            ""
            if entry.fetch
            else _("The source is final: nothing to fetch.")
            if entry.final
            else _("A release brings the next months.")
        )
        origin = _("Ships with Dagobert.") if entry.shipped else _("Optional, fetched on request.")
        said = " ".join(filter(None, (origin, text, later)))
        st.markdown(f"**{_(entry.title)}**  \n{said}")
        if not text and entry.name in wanted:
            st.warning(
                _(UNPRICED[mode.view(data_dir).shows(SNAPSHOT)]).format(code=wanted[entry.name]),
                icon=":material/warning:",
            )
        elif not text:
            st.info(
                _("Not fetched yet. Fetch it or import a CSV to use it.")
                if entry.imports
                else _("Not fetched yet. Fetch it to use it."),
                icon=":material/info:",
            )
        _terms(entry.used_by, entry, entry.name)
        if entry.fetch:
            _fetch(entry, data_dir)
        if (result := st.session_state.get(RESULT + entry.name)) is not None:
            (st.success if result.ok else st.error)(result.text)
        if entry.imports:
            _import(entry, data_dir)


def _life_table() -> None:
    with st.container(border=True, key="data-life-table"):
        try:
            table = series.life_table()
        except series.MissingSeriesError as err:
            st.error(str(err))
            return
        title = _("Life table (Sterbetafel), Germany")
        period = _("Period {period}. Shipped: a release brings the next table.").format(
            period=table.period
        )
        st.markdown(f"**{title}**  \n{period}")
        _terms(LIFE_TABLE_USE, table)


def page(data_dir: Path) -> None:
    st.title(_("Data"))
    st.caption(_(INTRO))
    fold(_(READING))
    wanted = needed(data_dir)
    (st.warning if wanted else st.info)(summary(data_dir, wanted), icon=":material/fact_check:")
    for entry in series.SERIES.values():
        _series(entry, data_dir, wanted)
        if told := NOTES.get(entry.name):
            st.caption(told(data_dir))
    _life_table()
