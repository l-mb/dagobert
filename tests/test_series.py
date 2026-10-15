"""Series: the Bundesbank format, the overlay of fetched months, the chained consumer prices, the
dollar series in euros and the incremental fetch. A fake getter stands in for the network. The
values are invented."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pytest
from builders import FakeGet
from dateutil.relativedelta import relativedelta

from dagobert import series
from dagobert.model.months import add_months
from dagobert.series import (
    BBK_CSV,
    COIN_METRICS,
    COIN_METRICS_ORIGIN,
    COIN_METRICS_PAGES,
    CURVO,
    SERIES,
    FetchError,
    Point,
    Response,
    cpi,
    fetched_file,
    in_euros,
    life_table,
    load,
    month_ends,
    parse_bbk,
    parse_ecb,
    read,
    save,
    update,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

# The header blocks as delivered, with shorter comments
VPI_KEY, UMR_KEY = "BBDP1.M.DE.N.VPI.C.A00000.I20.A", "BBSIS.M.I.UMR.RD.EUR.A.B.A.A.R.A.A._Z._Z.A"
VPI_HEAD = f"""\ufeff"";{VPI_KEY};{VPI_KEY}_FLAGS
"";Verbraucherpreisindex / Deutschland / Ursprungswerte Insgesamt;
"";;;
Dezimalstellen;1;;
Einheit;2020=100;;
Hinweise zur Methodik;Letzter Datenpunkt basiert zeitweise auf eigenen Schätzungen.;;
Stand vom;30.09.2026 15:41:20 Uhr;
"""
UMR_HEAD = f"""\ufeff"";{UMR_KEY};{UMR_KEY}_FLAGS
"";Umlaufsrenditen inländischer Inhaberschuldverschreibungen / Insgesamt / Monatswerte;
BBK_UNIT_ENG;percent;
Dezimalstellen;2;
Kommentar;Anpassung des Kreises der einbezogenen Papiere zum 01.05.2020.;
Kommentar (englisch);"Adjustment of the scope of securities included on 1 May 2020.";
Stand vom;01.10.2026 10:32:49 Uhr;
"""
ECB_HEAD = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE"
# A Bundesbank series with a shipped file of its own, see `ship`
TEST = replace(SERIES["umlaufsrendite"], name="test", shipped="test.csv")
MSCI, BITCOIN, USD_EUR = SERIES["msci-world"], SERIES["bitcoin"], SERIES["usd-eur"]


def _m(month: int, year: int = 2026) -> date:
    return date(year, month, 1)


def _bbk(*rows: str, head: str = UMR_HEAD) -> Response:
    return Response(200, BBK_CSV, (head + "".join(f"{r}\n" for r in rows)).encode())


def _curvo(*values: float) -> Response:
    """Month ends from 1970-01 on."""
    ends = [date(1970, 2, 1) + relativedelta(months=i, days=-1) for i in range(len(values))]
    body = json.dumps(
        [{"date": d.isoformat(), "value": v} for d, v in zip(ends, values, strict=True)]
    )
    return Response(200, "application/json", body.encode())


def _ecb(*rows: str) -> Response:
    """Rows `month,value` in the columns of an answer without the attributes, empty without."""
    lines = (f"EXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,{r}\n" for r in rows)
    return Response(200, "text/csv", (f"{ECB_HEAD}\n{''.join(lines)}" if rows else "").encode())


def _coins(*days: tuple[str, float], more: str | None = None) -> Response:
    """A page of daily closes of Coin Metrics, `more` the URL of the next page."""
    data = [
        {"asset": "btc", "time": f"{d}T00:00:00.000000000Z", "PriceUSD": str(v)} for d, v in days
    ]
    page = {"data": data} | ({"next_page_url": more} if more else {})
    return Response(200, "application/json", json.dumps(page).encode())


@pytest.fixture
def ship(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """The shipped file of `TEST` in a package directory of the test, without rows until the
    test writes some."""
    package = tmp_path / "package"
    package.mkdir()
    monkeypatch.setattr(series, "SHIPPED", package)

    def write(*rows: str) -> None:
        (package / "test.csv").write_bytes(_bbk(*rows).body)

    write()
    return write


def _known(data: Path, *rows: str, name: str = TEST.name) -> bytes:
    path = fetched_file(data, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("month,value,provisional\n" + "".join(f"{r}\n" for r in rows))
    return path.read_bytes()


@pytest.mark.parametrize("head", [VPI_HEAD, UMR_HEAD])
def test_parse_bbk_skips_the_header_block_and_marks_a_flagged_row(head: str) -> None:
    rows = (
        "2016-06;0,1;",
        "2016-07;-0,10;",
        "2016-08;.;Kein Wert vorhanden",
        "2016-09;2,5;Geschätzt",
    )
    assert parse_bbk(head + "\n".join(rows)) == [
        Point(_m(6, 2016), 0.1),
        Point(_m(7, 2016), -0.1),
        Point(_m(9, 2016), 2.5, provisional=True),
    ]


def test_a_fetched_month_replaces_the_shipped_one_and_later_ones_extend_it(
    tmp_path: Path,
) -> None:
    shipped = read(SERIES["vpi"], tmp_path)
    last, later = shipped[-1].month, shipped[-1].month + relativedelta(months=1)
    path = fetched_file(tmp_path, "vpi")
    path.parent.mkdir()
    path.write_text(f"month,value,provisional\n{last:%Y-%m},200.5,\n{later:%Y-%m},201.0,1\n")
    assert read(SERIES["vpi"], tmp_path) == [
        *shipped[:-1],
        Point(last, 200.5),
        Point(later, 201.0, provisional=True),
    ]


def test_cpi_chains_west_germany_to_the_vpi(tmp_path: Path) -> None:
    west, vpi, chain = (
        read(SERIES["vpi-west"], tmp_path),
        read(SERIES["vpi"], tmp_path),
        cpi(tmp_path),
    )
    join = chain.months.index(vpi[0].month)
    assert chain.months == [_m(1, 1962) + relativedelta(months=i) for i in range(len(chain.months))]
    assert chain.values[join:].tolist() == [p.value for p in vpi]
    old = np.array([p.value for p in west if p.month <= vpi[0].month])
    assert np.allclose(chain.values[1 : join + 1] / chain.values[:join], old[1:] / old[:-1])


@pytest.mark.parametrize("name", [n for n, s in SERIES.items() if s.shipped])
def test_shipped_series_have_no_gap_and_only_the_last_month_provisional(
    tmp_path: Path, name: str
) -> None:
    points = read(SERIES[name], tmp_path)
    months = [p.month for p in points]
    assert months == [months[0] + relativedelta(months=i) for i in range(len(months))]
    assert not any(p.provisional for p in points[:-1])


def test_the_equity_series_loads_only_once_fetched(tmp_path: Path) -> None:
    assert load("msci-world", tmp_path) is None
    update(MSCI, tmp_path, FakeGet([_curvo(100.0, 101.0)]))
    loaded = load("msci-world", tmp_path)
    assert loaded is not None
    assert loaded.months == [_m(1, 1970), _m(2, 1970)]


def test_consumer_prices_of_a_day_after_the_series_take_its_last_month(tmp_path: Path) -> None:
    chain, prices = cpi(tmp_path), series.consumer_prices(tmp_path)
    assert prices(date(1991, 1, 20)) == chain.values[chain.months.index(_m(1, 1991))]
    assert prices(date(2999, 1, 1)) == chain.values[-1]


def test_life_table_finds_the_one_shipped_table() -> None:
    table = life_table()
    assert table.path.exists()
    assert re.fullmatch(r"\d{4}-\d{4}", table.period)


@pytest.mark.parametrize(
    ("shipped", "fetched", "since"),
    [
        (("2026-07;1,0;", "2026-08;1,1;Geschätzt", "2026-09;1,2;Geschätzt"), (), "2026-08"),
        (("2026-07;1,0;", "2026-08;1,1;"), (), "2026-08"),
        (("2026-06;0,9;", "2026-07;1,0;", "2026-08;1,1;"), ("2026-07,1.0,",), "2026-07"),
        ((), ("2026-07,1.0,", "2026-08,1.1,1"), "2026-07"),
        ((), (), None),
    ],
)
def test_update_asks_from_the_first_fetched_or_provisional_month_else_the_last(
    tmp_path: Path,
    ship: Callable[..., None],
    shipped: tuple[str, ...],
    fetched: tuple[str, ...],
    since: str | None,
) -> None:
    ship(*shipped)
    _known(tmp_path, *fetched)
    get = FakeGet([_bbk()])
    update(TEST, tmp_path, get)
    assert len(get.urls) == 1
    assert get.urls[0].endswith(f"?format=bbk_csv&startPeriod={since}" if since else "bbk_csv")


@pytest.mark.parametrize("answer", [_bbk(), _bbk("2026-07;1,0;", "2026-08;1,1;")])
@pytest.mark.usefixtures("ship")
def test_an_answer_without_news_leaves_the_file(tmp_path: Path, answer: Response) -> None:
    before = _known(tmp_path, "2026-07,1.0,", "2026-08,1.1,")
    result = update(TEST, tmp_path, FakeGet([answer]))
    assert (result.added, result.replaced, result.last) == ([], [], _m(8))
    assert fetched_file(tmp_path, TEST.name).read_bytes() == before


def test_a_fetch_replaces_the_shipped_estimate_and_adds_a_month(tmp_path: Path) -> None:
    """On the shipped VPI: its last month, an estimate or not, then a new month."""
    last = read(SERIES["vpi"], tmp_path)[-1]
    later = last.month + relativedelta(months=1)
    value = last.value + 0.1 if last.provisional else last.value
    get = FakeGet(
        [
            _bbk(
                f"{last.month:%Y-%m};{value:.1f}".replace(".", ",") + ";",
                f"{later:%Y-%m};200,0;Geschätzter Wert",
                head=VPI_HEAD,
            )
        ]
    )
    result = update(SERIES["vpi"], tmp_path, get)
    assert get.urls[0].endswith(f"&startPeriod={last.month:%Y-%m}")
    assert (result.added, result.replaced, result.last) == ([later], [], later)
    assert read(SERIES["vpi"], tmp_path)[-2:] == [
        Point(last.month, round(value, 1)),
        Point(later, 200.0, provisional=True),
    ]


def test_a_newer_shipped_file_heals_the_fetched_months_it_revised(
    tmp_path: Path, ship: Callable[..., None]
) -> None:
    """A release rebased the shipped months that a fetch before it stored: the next fetch asks
    from the first fetched month, sees the revision and takes the whole series."""
    whole = ("2026-07;100,0;", "2026-08;100,2;", "2026-09;100,8;", "2026-10;101,0;")
    ship(*whole)
    _known(tmp_path, "2026-08,125.8,", "2026-09,126.6,")
    get = FakeGet([_bbk(*whole[1:]), _bbk(*whole)])
    result = update(TEST, tmp_path, get)
    assert get.urls[0].endswith("&startPeriod=2026-08")
    assert "startPeriod" not in get.urls[1]
    assert (result.added, result.replaced) == ([], [_m(8), _m(9)])
    assert read(TEST, tmp_path) == parse_bbk("\n".join(whole))


@pytest.mark.usefixtures("ship")
def test_a_revised_month_replaces_the_fetched_file(tmp_path: Path) -> None:
    """The answer starts with the first fetched month: it holds all of them, one request."""
    _known(tmp_path, "2026-07,1.0,", "2026-08,1.1,")
    answer = ("2026-07;1,05;", "2026-08;1,2;", "2026-09;1,3;")
    get = FakeGet([_bbk(*answer)])
    result = update(TEST, tmp_path, get)
    assert len(get.urls) == 1
    assert (result.added, result.replaced) == ([_m(9)], [_m(7), _m(8)])
    assert read(TEST, tmp_path) == parse_bbk("\n".join(answer))


def test_curvo_adds_only_new_months(tmp_path: Path) -> None:
    """The stored values read back exactly, so a second fetch of the same file changes nothing."""
    values = (141.36467290798652, 133.52600179523867)
    update(MSCI, tmp_path, FakeGet([_curvo(*values)]))
    path = fetched_file(tmp_path, MSCI.name)
    first = path.read_bytes()
    again = update(MSCI, tmp_path, FakeGet([_curvo(*values)]))
    assert (again.added, path.read_bytes()) == ([], first)
    more = update(MSCI, tmp_path, FakeGet([_curvo(*values, 137.7)]))
    assert (more.added, more.replaced) == ([_m(3, 1970)], [])


def test_curvo_replaces_a_series_that_differs_in_one_request(tmp_path: Path) -> None:
    path = fetched_file(tmp_path, MSCI.name)
    path.parent.mkdir()
    path.write_text("month,value,provisional\n1970-02,1.0,\n1970-03,1.1,\n")
    get = FakeGet([_curvo(100.0, 101.0, 102.0, 103.0)])
    result = update(MSCI, tmp_path, get)
    assert len(get.urls) == 1
    assert result.replaced == [_m(2, 1970), _m(3, 1970)]
    assert result.added == [_m(1, 1970), _m(4, 1970)]
    assert [p.value for p in read(MSCI, tmp_path)] == [100.0, 101.0, 102.0, 103.0]


def test_an_import_takes_the_place_of_the_fetched_months_until_a_fetch_differs(
    tmp_path: Path,
) -> None:
    """The last value of each month counts. The month of today has not ended: its value is
    provisional, so a fetch that differs there revises nothing."""
    update(MSCI, tmp_path, FakeGet([_curvo(100.0, 101.0, 102.0)]))
    daily = [(date(1970, 1, 15), 1.0), (date(1970, 1, 31), 2.0), (date(1970, 2, 3), 3.0)]
    save(MSCI, tmp_path, month_ends(reversed(daily), today=date(1970, 2, 3)))
    assert read(MSCI, tmp_path) == [  # the fetched 1970-03 went
        Point(_m(1, 1970), 2.0),
        Point(_m(2, 1970), 3.0, provisional=True),
    ]
    result = update(MSCI, tmp_path, FakeGet([_curvo(100.0, 101.0)]))
    assert (result.added, result.replaced) == ([], [_m(1, 1970)])


def test_no_network_names_the_reason_and_the_url_as_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """The page renders the text as markdown, which took the `_` of a key for italics."""

    def offline(*_: object, **__: object) -> None:
        raise urllib.error.URLError("Temporary failure in name resolution")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    with pytest.raises(FetchError) as caught:
        series.http_get(CURVO)
    assert str(caught.value) == f"No answer from `{CURVO}`: Temporary failure in name resolution"


def test_an_import_with_a_gap_is_refused(tmp_path: Path) -> None:
    """The historical model aligns its series month by month: a gap would stop it."""
    points = [Point(_m(1), 1.0), Point(_m(2), 1.1), Point(_m(5), 1.2)]
    assert series.gap(points) == "no month from 2026-03 to 2026-04"
    assert series.gap(points[:2]) == ""
    with pytest.raises(ValueError, match="no month from 2026-03 to 2026-04"):
        save(MSCI, tmp_path, points)
    assert not fetched_file(tmp_path, MSCI.name).exists()


def test_dollars_take_the_mark_before_1999_and_the_ecb_rate_from_then(tmp_path: Path) -> None:
    """A euro is 1.95583 Deutsche Mark: Council Regulation (EC) No 2866/98."""
    usd, dem, ecb = (
        {p.month: p.value for p in read(SERIES[name], tmp_path)}
        for name in ("gold", "usd-dem", "usd-eur")
    )
    gold = load("gold", tmp_path)
    assert gold is not None
    euros = dict(zip(gold.months, gold.values.tolist(), strict=True))
    december, january = _m(12, 1998), _m(1, 1999)
    assert euros[december] == pytest.approx(usd[december] * dem[december] / 1.95583)
    assert euros[january] == pytest.approx(usd[january] / ecb[january])


def test_a_dollar_month_after_the_last_rate_takes_it_and_stays_provisional(tmp_path: Path) -> None:
    last = read(USD_EUR, tmp_path)[-1]
    later = add_months(last.month, 1)
    _known(tmp_path, f"{last.month:%Y-%m},100.0,", f"{later:%Y-%m},200.0,", name=BITCOIN.name)
    assert in_euros(BITCOIN, tmp_path) == [
        Point(last.month, 100.0 / last.value),
        Point(later, 200.0 / last.value, provisional=True),
    ]


def test_the_ecb_rates_extend_the_shipped_ones_and_an_empty_answer_is_up_to_date(
    tmp_path: Path,
) -> None:
    last = read(USD_EUR, tmp_path)[-1]
    later = add_months(last.month, 1)
    get = FakeGet([_ecb(), _ecb(f"{last.month:%Y-%m},{last.value!r}", f"{later:%Y-%m},1.2")])
    assert update(USD_EUR, tmp_path, get).added == []
    assert not fetched_file(tmp_path, USD_EUR.name).exists()
    assert update(USD_EUR, tmp_path, get).added == [later]
    assert all(url.endswith(f"?format=csvdata&startPeriod={last.month:%Y-%m}") for url in get.urls)
    assert read(USD_EUR, tmp_path)[-2:] == [last, Point(later, 1.2)]


def test_bitcoin_takes_the_close_of_the_last_day_of_each_month_over_all_pages(
    tmp_path: Path,
) -> None:
    """A month whose last day has no close yet is provisional, and the next fetch starts there."""
    first = FakeGet(
        [
            _coins(("2015-01-30", 1.0), ("2015-01-31", 2.0), more=f"{COIN_METRICS_ORIGIN}next"),
            _coins(("2015-02-01", 3.0), ("2015-02-27", 4.0)),
        ]
    )
    update(BITCOIN, tmp_path, first)
    assert first.urls == [COIN_METRICS, f"{COIN_METRICS_ORIGIN}next"]
    assert read(BITCOIN, tmp_path) == [
        Point(_m(1, 2015), 2.0),
        Point(_m(2, 2015), 4.0, provisional=True),
    ]
    again = FakeGet([_coins(("2015-02-28", 5.0), ("2015-03-01", 6.0))])
    assert update(BITCOIN, tmp_path, again).added == [_m(3, 2015)]
    assert again.urls == [f"{COIN_METRICS}&start_time=2015-02-01"]
    assert read(BITCOIN, tmp_path)[1:] == [
        Point(_m(2, 2015), 5.0),
        Point(_m(3, 2015), 6.0, provisional=True),
    ]


@pytest.mark.parametrize(
    ("status", "provisional"), [("A", False), ("P", True), ("E", True), ("F", True)]
)
def test_an_ecb_month_with_a_flagged_status_is_provisional(status: str, provisional: bool) -> None:
    """A provisional, estimated or forecast value (SDMX OBS_STATUS), in the full `csvdata`."""
    text = f"{ECB_HEAD},OBS_STATUS\nEXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,2026-09,1.15,{status}\n"
    assert parse_ecb(text) == [Point(_m(9), 1.15, provisional)]


@pytest.mark.parametrize(
    ("name", "answer", "message"),
    [
        ("vpi", Response(400, "text/html", b"<html>Rate-Limit exceeded</html>"), "rate limit"),
        ("vpi", Response(404, "application/json", b'{"status":404}'), "HTTP 404"),
        ("bitcoin", Response(429, "application/json", b'{"error":{}}'), "HTTP 429"),
        ("bitcoin", Response(200, "application/json", b"[1, 2]"), "Coin Metrics sent no Bitcoin"),
        ("bitcoin", Response(200, "text/html", b"<html></html>"), "Coin Metrics sent no Bitcoin"),
        ("usd-eur", Response(200, "text/html", b"<html></html>"), "The ECB answered HTTP 200"),
        ("usd-eur", Response(200, "text/csv", b"A,B\n1,2\n"), "The ECB sent no series"),
        ("bitcoin", _coins(("2026-07-31", 1.0), more="file:///etc/passwd"), "Coin Metrics sent no"),
    ],
)
def test_a_fetch_refuses_an_answer_that_is_not_the_series_and_leaves_the_file(
    tmp_path: Path, name: str, answer: Response, message: str
) -> None:
    before = _known(tmp_path, "2026-07,1.0,", name=name)
    with pytest.raises(FetchError, match=message):
        update(SERIES[name], tmp_path, FakeGet([answer]))
    assert fetched_file(tmp_path, name).read_bytes() == before


def test_a_fetch_stops_at_a_loop_of_pages(tmp_path: Path) -> None:
    again = f"{COIN_METRICS_ORIGIN}next"
    get = FakeGet([_coins(("2026-07-31", 1.0), more=again)] * COIN_METRICS_PAGES)
    with pytest.raises(FetchError, match="more than"):
        update(SERIES["bitcoin"], tmp_path, get)


def test_a_fetch_takes_the_last_page_that_the_cap_allows(tmp_path: Path) -> None:
    again = f"{COIN_METRICS_ORIGIN}next"
    pages = [_coins(("2026-07-31", 1.0), more=again)] * (COIN_METRICS_PAGES - 1)
    update(SERIES["bitcoin"], tmp_path, FakeGet([*pages, _coins(("2026-08-31", 2.0))]))
    assert fetched_file(tmp_path, "bitcoin").exists()


@pytest.mark.parametrize(
    ("text", "line"),
    [("month,value\n2024-01,1\n2024-02\n", "line 3"), ("month,value\n2024-01,abc\n", "line 2")],
)
def test_a_bad_row_of_a_month_file_names_its_line(text: str, line: str) -> None:
    with pytest.raises(ValueError, match=line):
        series.parse_month_value(text)
