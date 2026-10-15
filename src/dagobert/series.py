"""The market and price series: the registry, the files that ship in the package, the months
that a fetch adds in `<data>/series/`, the chained consumer prices and the dollar series in euros.

A fetch runs only on a user action. The shipped files stay as their source delivered them, or
are extracts with unchanged values."""

from __future__ import annotations

import csv
import http.client
import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from dagobert import __version__
from dagobert.files import atomic_write
from dagobert.i18n import N_, _
from dagobert.model.months import add_months
from dagobert.result import FloatArray

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

SHIPPED = Path(__file__).parent / "data"
FETCHED = "series"  # below the data directory
USER_AGENT = f"dagobert/{__version__} (+https://github.com/l-mb/dagobert)"
TIMEOUT = 30  # seconds
BBK_CSV = "application/vnd.bbk.data+csv"
CURVO = "https://curvo.eu/backtest/data/msci-world.json"
COIN_METRICS = (  # the community API: no key, 10 requests in 6 seconds
    "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
    "?assets=btc&metrics=PriceUSD&frequency=1d&page_size=10000&paging_from=start"
)
COIN_METRICS_ORIGIN = "https://community-api.coinmetrics.io/"  # the only host a next page may name
COIN_METRICS_PAGES = 100
COIN_METRICS_DOCS = "https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data"
WORLD_BANK = "https://www.worldbank.org/en/research/commodity-markets"  # links the Pink Sheet
WORLD_BANK_TERMS = "https://www.worldbank.org/ext/en/legal/terms-conditions/datasets"
ECB_TERMS = (
    "https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/"
    "usage_policy.en.html"
)
DEM_PER_EUR = 1.95583  # the conversion rate of Council Regulation (EC) No 2866/98
RATE_LIMIT = (
    "The Bundesbank refused the request, probably for its rate limit. Try again later: "
    "a block can last more than 20 minutes."
)
DESTATIS_REPORTS = "https://www.destatis.de/DE/Themen"
DL_DE_BY = "Datenlizenz Deutschland – Namensnennung – Version 2.0"
DL_DE_BY_URL = "https://www.govdata.de/dl-de/by-2-0"
BBK_TERMS = N_("Terms of use of the Deutsche Bundesbank, §4.1")
BBK_TERMS_URL = (
    "https://www.bundesbank.de/de/startseite/benutzerhinweise/"
    "nutzungsbedingungen-fuer-den-allgemeinen-gebrauch-der-website-763554"
)
# The report of the shipped life table: scripts/refresh_shipped.py names a newer one
LIFE_TABLE_SOURCE = (
    f"{DESTATIS_REPORTS}/Gesellschaft-Umwelt/Bevoelkerung/Sterbefaelle-Lebenserwartung/"
    "Publikationen/Downloads-Sterbefaelle/statistischer-bericht-sterbetafeln-5126207257005.html"
)
LIFE_TABLE_ATTRIBUTION = "© Statistisches Bundesamt (Destatis), 2026"


class FetchError(Exception):
    """A source refused the request or sent a response that is not the series."""


class MissingSeriesError(LookupError):
    """A series or table without rows."""


@dataclass(frozen=True)
class MonthlySeries:
    months: list[date]
    values: FloatArray


@dataclass(frozen=True)
class Point:
    month: date  # first of the month
    value: float
    provisional: bool = False


@dataclass(frozen=True)
class Response:
    status: int
    type: str  # content type, lower case, without parameters
    body: bytes


type Getter = Callable[[str], Response]  # url -> response; tests pass a fake one


def http_get(url: str) -> Response:
    """The answer of the server, an error status too. Raises `FetchError` without one."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as r:
            return Response(r.status, r.headers.get_content_type(), r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, e.headers.get_content_type(), e.read())
    except (OSError, http.client.HTTPException) as e:
        reason = e.reason if isinstance(e, urllib.error.URLError) else e
        msg = f"No answer from `{url}`: {reason}"
        raise FetchError(msg) from e


def _month(text: str) -> date:
    return date.fromisoformat(f"{text[:7]}-01")


def parse_month_value(text: str) -> list[Point]:
    """A `month,value[,provisional]` file: a shipped extract, a fetched file of `<data>/series/`
    or the `msci_world.csv` of an older data directory."""
    rows = csv.DictReader(io.StringIO(text.removeprefix("\ufeff")))
    try:
        return [
            Point(_month(r["month"]), float(r["value"]), r.get("provisional") == "1") for r in rows
        ]
    except (TypeError, ValueError) as err:
        msg = f"line {rows.line_num}: month or value missing or unreadable ({err})"
        raise ValueError(msg) from err


def month_values(text: str) -> list[Point] | None:
    """The points of a file in the format of `parse_month_value`, None for another header."""
    header = text.removeprefix("\ufeff").partition("\n")[0].strip().split(",")
    formats = (["month", "value"], ["month", "value", "provisional"])
    return parse_month_value(text) if header in formats else None


_BBK_ROW = re.compile(r"(\d{4}-\d{2});(-?\d+(?:,\d+)?);(.*)")


def parse_bbk(text: str) -> list[Point]:
    """The rows of a `bbk_csv` answer of the Bundesbank, whatever its header block holds. A row
    with a flag (`Geschätzter Wert`) is provisional. A month without a value is left out."""
    return [
        Point(_month(m[1]), float(m[2].replace(",", ".")), bool(m[3].strip(' ;"')))
        for m in map(_BBK_ROW.fullmatch, text.splitlines())
        if m
    ]


PROVISIONAL = {"E", "F", "P"}  # an estimate, a forecast or a provisional value (SDMX OBS_STATUS)


def parse_ecb(text: str) -> list[Point]:
    """The rows of a `csvdata` answer of the ECB data portal by their columns `TIME_PERIOD` and
    `OBS_VALUE`, with or without the other columns. An empty answer has none."""
    return [
        Point(_month(r["TIME_PERIOD"]), float(r["OBS_VALUE"]), r.get("OBS_STATUS") in PROVISIONAL)
        for r in csv.DictReader(io.StringIO(text))
        if r["OBS_VALUE"]
    ]


@dataclass(frozen=True)
class Sdmx:
    """A monthly series of an SDMX web service that needs no account (`bundesbank`, `ecb`). Its
    answer ships as delivered."""

    key: str  # flow/series key
    agency: str  # for a message: `The Bundesbank`
    root: str  # URL up to the flow
    query: str  # the format of the answer
    type: str  # content type of an answer that holds the series
    parse: Callable[[str], list[Point]]
    html: str = ""  # what an HTML page means

    def url(self, since: date | None) -> str:
        start = f"&startPeriod={since:%Y-%m}" if since else ""
        return f"{self.root}{self.key}?{self.query}{start}"

    def raw(self, get: Getter, since: date | None = None) -> bytes:
        """The answer as delivered, from the month `since` on, else whole."""
        r = get(self.url(since))
        if r.status == 200 and r.type == self.type:
            return r.body
        msg = (
            self.html
            if self.html and r.type == "text/html"
            else f"{self.agency} answered HTTP {r.status} ({r.type}) for `{self.key}`."
        )
        raise FetchError(msg)

    def __call__(self, get: Getter, since: date | None) -> list[Point]:
        try:
            return self.parse(self.raw(get, since).decode("utf-8-sig"))
        except (ValueError, KeyError) as e:
            msg = f"{self.agency} sent no series for `{self.key}`."
            raise FetchError(msg) from e


def bundesbank(key: str) -> Sdmx:
    return Sdmx(
        key,
        "The Bundesbank",
        "https://api.statistiken.bundesbank.de/rest/data/",
        "format=bbk_csv",
        BBK_CSV,
        parse_bbk,
        RATE_LIMIT,
    )


def ecb(key: str) -> Sdmx:
    return Sdmx(
        key,
        "The ECB",
        "https://data-api.ecb.europa.eu/service/data/",
        "format=csvdata",
        "text/csv",
        parse_ecb,
    )


def curvo(get: Getter, since: date | None) -> list[Point]:
    """The whole MSCI World file of Curvo, one value per month end: it takes no start month."""
    r = get(CURVO)
    msg = f"Curvo sent no MSCI World series (HTTP {r.status}, {r.type})."
    if r.status != 200:
        raise FetchError(msg)
    try:
        return [
            Point(_month(p["date"]), float(p["value"])) for p in json.loads(r.body.decode("utf-8"))
        ]
    except (ValueError, KeyError, TypeError) as e:
        raise FetchError(msg) from e


def coin_metrics(get: Getter, since: date | None) -> list[Point]:
    """The daily close of Bitcoin in US dollars from the first day of the month `since` on, else
    all, over every page of the answer: the close of the last day of each month. A month whose
    last day has no close yet is provisional."""
    url = COIN_METRICS + (f"&start_time={since:%Y-%m-%d}" if since else "")
    days: list[tuple[date, float]] = []
    for _page in range(COIN_METRICS_PAGES):
        r = get(url)
        msg = f"Coin Metrics sent no Bitcoin prices (HTTP {r.status}, {r.type})."
        if r.status != 200:
            raise FetchError(msg)
        try:
            page = json.loads(r.body.decode("utf-8"))
            days += [
                (date.fromisoformat(d["time"][:10]), float(d["PriceUSD"])) for d in page["data"]
            ]
            following = page.get("next_page_url")
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise FetchError(msg) from e
        if not following:
            break
        if not following.startswith(COIN_METRICS_ORIGIN):
            raise FetchError(msg)
        url = following
    else:
        msg = f"Coin Metrics sent more than {COIN_METRICS_PAGES} pages of Bitcoin prices."
        raise FetchError(msg)
    ends = {day.replace(day=1): (day, value) for day, value in sorted(days)}
    return [
        Point(month, value, (day + timedelta(days=1)).day != 1)
        for month, (day, value) in ends.items()
    ]


@dataclass(frozen=True)
class Series:
    name: str  # CLI argument and file stem
    title: str  # English, marked for the catalogue: `_()` where it shows, as `used_by`
    used_by: str
    source: str  # URI of the data set
    attribution: str  # the source note that the terms require
    licence: str  # its name, English (`N_` where words): `_()` where it shows
    terms: str  # URL
    shipped: str | None = None  # file in SHIPPED: an extract, or the answer of `delivered`
    delivered: Sdmx | None = None  # the service whose answer `shipped` holds as it came
    fetch: Callable[[Getter, date | None], list[Point]] | None = None  # from a month, or all
    imports: bool = False  # a download can stand in for the fetch (`month_ends`, `save`)
    final: bool = False  # the source adds no months
    usd: bool = False  # in US dollars: `load` gives euros (`in_euros`)

    @property
    def parse(self) -> Callable[[str], list[Point]]:
        """The reader of the shipped file."""
        return self.delivered.parse if self.delivered else parse_month_value


VPI = bundesbank("BBDP1/M.DE.N.VPI.C.A00000.I20.A")
UMLAUFSRENDITE = bundesbank("BBSIS/M.I.UMR.RD.EUR.A.B.A.A.R.A.A._Z._Z.A")
USD_DEM = bundesbank("BBEX3/M.USD.DEM.AA.AC.A02")
USD_EUR = ecb("EXR/M.USD.EUR.SP00.A")
EQUITY = "msci-world"  # the equity series of the historical model
SERIES = {
    s.name: s
    for s in (
        Series(
            "vpi-west",
            N_("Consumer prices, former West Germany, all private households (1995=100)"),
            N_("the consumer prices before 1991"),
            f"{DESTATIS_REPORTS}/Wirtschaft/Preise/Verbraucherpreisindex/Publikationen/"
            "Downloads-Verbraucherpreise/"
            "statistischer-bericht-preisindizes-lebenshaltung-lange-reihen-5611111999005.html",
            "© Statistisches Bundesamt (Destatis), 2025. Extract: one column, values unchanged.",
            DL_DE_BY,
            DL_DE_BY_URL,
            "destatis_vpi_west.csv",
            final=True,
        ),
        Series(
            "vpi",
            N_("Consumer price index (VPI), Germany (2020=100)"),
            N_(
                "the consumer prices from 1991: the historical model, your records in euros of "
                "the start, the roll forward"
            ),
            VPI.url(None),
            "Quelle: Deutsche Bundesbank; Statistisches Bundesamt, Wiesbaden",
            BBK_TERMS,
            BBK_TERMS_URL,
            "bundesbank_vpi.csv",
            VPI,
            VPI,
        ),
        Series(
            "umlaufsrendite",
            N_("Yield of German bonds outstanding (Umlaufsrendite), monthly"),
            N_("fixed income in the historical model"),
            UMLAUFSRENDITE.url(None),
            "Quelle: Deutsche Bundesbank",
            BBK_TERMS,
            BBK_TERMS_URL,
            "bundesbank_umlaufsrendite.csv",
            UMLAUFSRENDITE,
            UMLAUFSRENDITE,
        ),
        Series(
            EQUITY,
            N_("MSCI World Net Total Return EUR, month ends"),
            N_("equity in the historical model, which is off without it"),
            CURVO,
            "MSCI World Net Total Return EUR, via Curvo. Personal use only.",
            N_("MSCI index terms: informational, non-commercial use"),
            "https://www.msci.com/legal/index-terms",
            fetch=curvo,
            imports=True,
        ),
        Series(
            "gold",
            N_("Gold, US dollars per troy ounce, monthly average"),
            N_(
                "the value of gold (XAU) without a price file of your own, and a gold asset in "
                "the historical model"
            ),
            WORLD_BANK,
            "The World Bank: Commodity Prices - History and Projections (Pink Sheet): Bloomberg "
            "Finance L.P.; Kitco.com; International Monetary Fund, International Financial "
            "Statistics; London Bullion Market; Metals Week; Platts Metals Week; Shearson Lehman "
            "Brothers, Metal Market Weekly Review; Thomson Reuters Datastream; World Bank. "
            "Extract: the column Gold of the sheet Monthly Prices, values unchanged.",
            N_("CC BY 4.0, World Bank terms of use for datasets"),
            WORLD_BANK_TERMS,
            "worldbank_gold.csv",
            usd=True,
        ),
        Series(
            "bitcoin",
            N_("Bitcoin, US dollars, close of the last day of each month"),
            N_("the value of Bitcoin (BTC) without a price file of your own"),
            COIN_METRICS_DOCS,
            "Source: Coin Metrics Community Data. Non-commercial use only.",
            N_("Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0)"),
            "https://creativecommons.org/licenses/by-nc/4.0/",
            fetch=coin_metrics,
            usd=True,
        ),
        Series(
            "usd-dem",
            N_("Deutsche Mark per US dollar, Frankfurt exchange, monthly average"),
            N_("gold in euros before 1999"),
            USD_DEM.url(None),
            "Quelle: Deutsche Bundesbank",
            BBK_TERMS,
            BBK_TERMS_URL,
            "bundesbank_usd_dem.csv",
            USD_DEM,
            final=True,
        ),
        Series(
            "usd-eur",
            N_("US dollars per euro, ECB reference rate, monthly average"),
            N_("gold and Bitcoin in euros from 1999"),
            USD_EUR.url(None),
            "Source: ECB statistics.",
            N_("ECB policy on the reuse of statistics: source quoted, statistics not modified"),
            ECB_TERMS,
            "ecb_usd_eur.csv",
            USD_EUR,
            USD_EUR,
        ),
    )
}


def fetched_file(data_dir: Path, name: str) -> Path:
    return data_dir / FETCHED / f"{name}.csv"


def _read_fetched(path: Path) -> list[Point]:
    return parse_month_value(path.read_text(encoding="utf-8")) if path.exists() else []


def _write_fetched(path: Path, points: Iterable[Point]) -> None:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(("month", "value", "provisional"))
    writer.writerows(
        (f"{p.month:%Y-%m}", repr(p.value), "1" if p.provisional else "") for p in points
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, out.getvalue())


def _merge(*parts: Iterable[Point]) -> list[Point]:
    """One point per month, sorted: a later part wins."""
    return sorted({p.month: p for part in parts for p in part}.values(), key=lambda p: p.month)


def read(series: Series, data_dir: Path) -> list[Point]:
    """The shipped rows, then the fetched ones: a fetched row replaces the shipped row of its
    month."""
    shipped = (
        series.parse((SHIPPED / series.shipped).read_text(encoding="utf-8-sig"))
        if series.shipped
        else []
    )
    return _merge(shipped, _read_fetched(fetched_file(data_dir, series.name)))


def _monthly(points: list[Point]) -> MonthlySeries:
    return MonthlySeries([p.month for p in points], np.array([p.value for p in points]))


def load(name: str, data_dir: Path) -> MonthlySeries | None:
    """The series as the model reads it, one in US dollars in euros. None for a series without
    rows, such as the equity series before its first fetch."""
    entry = SERIES[name]
    points = in_euros(entry, data_dir) if entry.usd else read(entry, data_dir)
    return _monthly(points) if points else None


def usd_per_eur(data_dir: Path) -> MonthlySeries:
    """US dollars per euro by month: the ECB rate from its first month, before that the Deutsche
    Mark per US dollar of the Bundesbank at `DEM_PER_EUR`. The shipped files stay as delivered:
    the app converts in memory."""
    ecb = read(SERIES["usd-eur"], data_dir)
    dem = read(SERIES["usd-dem"], data_dir)
    older = (Point(p.month, DEM_PER_EUR / p.value) for p in dem if p.month < ecb[0].month)
    return _monthly([*older, *ecb])


def in_euros(entry: Series, data_dir: Path) -> list[Point]:
    """A series in US dollars in euros, each month at its `usd_per_eur`. A month after the last
    rate takes the last one and is provisional until the rate of its month comes."""
    rates = usd_per_eur(data_dir)
    by_month, last = dict(zip(rates.months, rates.values.tolist(), strict=True)), rates.months[-1]
    return [
        Point(p.month, p.value / by_month[min(p.month, last)], p.provisional or p.month > last)
        for p in read(entry, data_dir)
    ]


def cpi(data_dir: Path) -> MonthlySeries:
    """The consumer prices from 1962: West Germany up to the month before the first month of the
    VPI, rescaled to the VPI level of that month, then the VPI as published."""
    west, vpi = read(SERIES["vpi-west"], data_dir), read(SERIES["vpi"], data_dir)
    first = vpi[0]
    scale = first.value / next(p.value for p in west if p.month == first.month)
    older = (replace(p, value=p.value * scale) for p in west if p.month < first.month)
    return _monthly([*older, *vpi])


def consumer_prices(data_dir: Path) -> Callable[[date], float]:
    """The consumer prices (`cpi`) of the month of a day. A day after the end of the series takes
    its last value."""
    prices = cpi(data_dir)
    by_month = dict(zip(prices.months, prices.values.tolist(), strict=True))
    return lambda day: by_month[min(day.replace(day=1), prices.months[-1])]


@dataclass(frozen=True)
class Update:
    added: list[date]  # months that were not known
    replaced: list[date]  # final months that the source revised: the fetch took the whole series
    last: date | None  # the last month after the update

    @property
    def text(self) -> str:
        """What the fetch changed. A stored month that differs from the source is a revision of
        the source or a month of an import."""
        last = f"up to {self.last:%Y-%m}" if self.last else "no months"
        if self.replaced:
            n = _months(self.replaced)
            return f"replaced the stored months, {last}: {n} differed from the source"
        if self.added:
            return f"added {_months(self.added)}, {last}"
        return f"already current, {last}"


def _months(months: list[date]) -> str:
    return f"{len(months)} month{'s' * (len(months) != 1)}"


def _since(known: list[Point], fetched: list[Point]) -> date | None:
    """The first provisional month, else the last one, so the overlap shows a revision. A first
    fetched month before it comes first: a newer shipped file can revise the fetched months, and
    the fetch then sees that they differ from the source. A series without a shipped file passes
    none, or each fetch would ask for all of it."""
    if not known:
        return None
    edge = next((p for p in known if p.provisional), known[-1]).month
    return min(fetched[0].month, edge) if fetched else edge


def update(series: Series, data_dir: Path, get: Getter = http_get) -> Update:
    """Fetch the months from `_since` on. A final month that changed means the source revised
    its history: then the whole series replaces the fetched file. An empty answer is up to date.
    Raises `FetchError` and leaves the files as they are."""
    if series.fetch is None:
        msg = f"{series.name} has no fetch"
        raise ValueError(msg)
    known, path = read(series, data_dir), fetched_file(data_dir, series.name)
    rows = series.fetch(get, _since(known, _read_fetched(path) if series.shipped else []))
    final = {p.month: p.value for p in known if not p.provisional}
    if any(final.get(p.month, p.value) != p.value for p in rows):
        whole = rows if rows[0].month <= known[0].month else series.fetch(get, None)
        _write_fetched(path, whole)
        replaced = [p.month for p in whole if final.get(p.month, p.value) != p.value]
    else:
        changed = set(rows) - set(known)
        if changed:
            _write_fetched(path, _merge(_read_fetched(path), changed))
        replaced = []
    after = read(series, data_dir)
    added = sorted({p.month for p in after} - {p.month for p in known})
    return Update(added, replaced, after[-1].month if after else None)


def month_ends(values: Iterable[tuple[date, float]], *, today: date) -> list[Point]:
    """The last value of each month of dated values, such as a downloaded index history. The
    month of `today` has not ended, so its value is provisional."""
    this = today.replace(day=1)
    return _merge(Point(day.replace(day=1), value, day >= this) for day, value in sorted(values))


def gap(points: Sequence[Point]) -> str:
    """The first run of missing months between sorted points, empty when the months follow each
    other: the `historical` model aligns its series month by month. In the language of the session
    (the CLI speaks English)."""
    return next(
        (
            _("no month from {first} to {last}").format(
                first=f"{add_months(a.month, 1):%Y-%m}", last=f"{add_months(b.month, -1):%Y-%m}"
            )
            for a, b in pairwise(points)
            if add_months(a.month, 1) != b.month
        ),
        "",
    )


def save(series: Series, data_dir: Path, points: Sequence[Point]) -> None:
    """Replace the fetched months of `series` with `points`, such as the months of an import.
    Raises ValueError for a `gap`."""
    if found := gap(points):
        msg = f"{series.name}: {found}, the months must follow each other"
        raise ValueError(msg)
    _write_fetched(fetched_file(data_dir, series.name), points)


@dataclass(frozen=True)
class LifeTableFile:
    path: Path
    period: str  # the years of the period table, `2023-2025`
    source: str  # URI of the report
    attribution: str
    licence: str
    terms: str  # URL


def life_table() -> LifeTableFile:
    """The one shipped Destatis life table, `sterbetafel-<period>.csv`."""
    match sorted(SHIPPED.glob("sterbetafel-*.csv")):
        case [path]:
            return LifeTableFile(
                path,
                path.stem.removeprefix("sterbetafel-"),
                LIFE_TABLE_SOURCE,
                LIFE_TABLE_ATTRIBUTION,
                DL_DE_BY,
                DL_DE_BY_URL,
            )
        case found:
            msg = f"{SHIPPED} holds {len(found)} files sterbetafel-*.csv, not one"
            raise MissingSeriesError(msg)
