"""The fetch of the closes of the held securities from EODHD: the listing on Xetra in euros, the
days that the price files lack in one revision, the refusals, and a key that no error names."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from builders import FakeGet
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from dagobert import eodhd, prices, revisions, series
from dagobert.cli import app
from dagobert.series import FetchError, Response

WORLD, EM = "IE00B4L5Y983", "IE00BKM4GZ66"
KEY = "k-test"
TODAY = date(2026, 10, 29)
BUY: dict[str, object] = {"date": "2020-01-01", "kind": "buy", "units": 3, "amount": 24}


def _ok(rows: object) -> Response:
    return Response(200, "application/json", json.dumps(rows).encode())


def _listing(isin: str, code: str, currency: str = "EUR") -> Response:
    row = {"Code": code, "Exchange": "XETRA", "ISIN": isin, "Currency": currency}
    return _ok([row, row | {"Exchange": "F"}])  # Frankfurt too, which the fetch leaves


def _closes(*points: tuple[str, float]) -> Response:
    return _ok([{"date": day, "close": close, "adjusted_close": 1.0} for day, close in points])


def _assets(data: Path, *trades: dict[str, object]) -> None:
    """The depot `d` of 3 units of `WORLD` bought in 2020 at 8 € each, and `trades`."""
    depot = {
        "id": "d",
        "kind": "equity",
        "value": 1.0,
        "trades": [BUY | {"security": WORLD}, *trades],
    }
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [depot]}))


def _fetch(data: Path, get: FakeGet, **options: object) -> eodhd.Fetched:
    return eodhd.fetch(data, KEY, get, today=TODAY, source="test", **options)  # type: ignore[arg-type]


def test_a_fetch_adds_the_days_that_the_price_file_lacks(data: Path) -> None:
    """The closes as traded, from the first trade at most a year back; a stored price stays. One
    revision with the values that it records."""
    _assets(data)
    prices.save(data, {WORLD: [(date(2026, 10, 27), 9.0)]}, source="test")
    get = FakeGet([_listing(WORLD, "EUNL"), _closes(("2026-10-27", 9.5), ("2026-10-28", 9.6))])
    fetched = _fetch(data, get)
    assert (fetched.added, fetched.refused, fetched.calls) == ({WORLD: 1}, {}, 2)
    assert fetched.recorded == [(date(2026, 10, 28), "d", 28.8)]
    assert prices.read_prices(prices.price_file(data, WORLD)) == [
        (date(2026, 10, 27), 9.0),
        (date(2026, 10, 28), 9.6),
    ]
    search, eod = get.urls
    assert search.startswith(f"{eodhd.API}/search/{WORLD}?exchange=XETRA&")
    assert eod.startswith(f"{eodhd.API}/eod/EUNL.XETRA?from=2025-10-29&period=d&order=a&")
    assert revisions.entries(data)[-1].source == "test"
    assert len(revisions.entries(data)) == 3  # the baseline, the stored price, the fetch


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        (_listing(EM, "EMIM", "USD"), "trades on Xetra in USD, not in euros"),
        (_ok([]), "EODHD knows no listing"),
        (Response(500, "text/html", b"oops"), "HTTP 500"),
    ],
)
def test_a_security_without_a_listing_in_euros_takes_no_price(
    data: Path, answer: Response, why: str
) -> None:
    """No conversion: a close in another currency is refused. The other securities go on."""
    _assets(data, BUY | {"security": EM})
    get = FakeGet([_listing(WORLD, "EUNL"), _closes(("2026-10-28", 9.6)), answer])
    fetched = _fetch(data, get)
    assert fetched.added == {WORLD: 1}
    assert why in fetched.refused[EM]


def test_a_used_up_plan_stops_the_calls_and_keeps_what_came(data: Path) -> None:
    _assets(data, BUY | {"security": EM})
    used_up = Response(402, "text/plain", b"API Rate Limit Exceeded.")
    get = FakeGet([_listing(WORLD, "EUNL"), _closes(("2026-10-28", 9.6)), used_up])
    fetched = _fetch(data, get)
    assert (fetched.added, fetched.calls) == ({WORLD: 1}, 3)
    assert fetched.stopped is not None
    assert "midnight GMT" in fetched.stopped


def test_a_price_far_from_a_trade_nearby_skips_its_security_unless_forced(data: Path) -> None:
    """A trade of 8 € per unit two days before a close of 80 €: a unit or a listing amiss."""
    _assets(data, BUY | {"security": WORLD, "date": "2026-10-26"})
    for force, added in ((False, {}), (True, {WORLD: 1})):
        get = FakeGet([_listing(WORLD, "EUNL"), _closes(("2026-10-28", 80.0))])
        fetched = _fetch(data, get, force=force)
        assert fetched.added == added
        assert (WORLD in fetched.refused) != force


def test_no_error_names_the_key(data: Path) -> None:
    """The key travels in the URL, which `http_get` writes into its errors."""
    _assets(data)

    def offline(url: str) -> Response:
        msg = f"No answer from `{url}`: timed out"
        raise FetchError(msg)

    fetched = eodhd.fetch(data, KEY, offline, today=TODAY, source="test")
    assert fetched.stopped is not None
    assert "timed out" in fetched.stopped
    assert KEY not in fetched.stopped
    refused = eodhd.fetch(
        data,
        KEY,
        FakeGet([Response(401, "text/plain", b"Unauthenticated")]),
        today=TODAY,
        source="test",
    )
    assert refused.stopped == eodhd.STOPS[401]


def test_the_key_comes_from_the_variable_or_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(eodhd.KEY, raising=False)
    monkeypatch.delenv(eodhd.KEY_FILE, raising=False)
    assert eodhd.key() is None
    (secret := tmp_path / "key").write_text(f"{KEY}\n")
    monkeypatch.setenv(eodhd.KEY_FILE, str(secret))
    assert eodhd.key() == KEY
    secret.write_text("\n")
    with pytest.raises(FetchError, match="holds no key"):
        eodhd.key()
    monkeypatch.setenv(eodhd.KEY, "other")
    assert eodhd.key() == "other"  # the variable first


def test_the_command_fetches_with_the_key_of_the_variable(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _assets(data)
    monkeypatch.delenv(eodhd.KEY_FILE, raising=False)
    args = ["prices", "fetch", "--data", str(data)]
    unset = CliRunner().invoke(app, args, env={eodhd.KEY: ""})
    assert unset.exit_code == 1
    assert eodhd.KEY in unset.output
    get = FakeGet([_listing(WORLD, "EUNL"), _closes(("2026-10-28", 9.6))])
    monkeypatch.setattr(series, "http_get", get)
    result = CliRunner().invoke(app, args, env={eodhd.KEY: KEY})
    assert result.exit_code == 0, result.output
    assert f"{WORLD}: 1 price added" in result.output
    assert "2 calls to EODHD" in result.output
    assert KEY not in result.output


SNAPSHOT = """
from pathlib import Path
from dagobert.store import assets_file
from dagobert.ui import snapshot, told
told()
snapshot.page(assets_file(Path({data!r})))
"""


def test_the_prices_of_the_snapshot_fetch_with_the_key_of_the_environment(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without a key the section says how to set one; with one the button fetches."""
    _assets(data)
    monkeypatch.delenv(eodhd.KEY, raising=False)
    monkeypatch.delenv(eodhd.KEY_FILE, raising=False)
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    assert not [b for b in at.button if b.label == "Fetch prices"]
    assert any(eodhd.KEY in c.value for c in at.caption)
    monkeypatch.setenv(eodhd.KEY, KEY)
    monkeypatch.setattr(
        series, "http_get", FakeGet([_listing(WORLD, "EUNL"), _closes(("2026-10-28", 9.6))])
    )
    at = AppTest.from_string(SNAPSHOT.format(data=str(data)), default_timeout=30).run()
    next(b for b in at.button if b.label == "Fetch prices").click().run()
    assert not at.exception
    [shown] = at.success
    assert f"{WORLD}: 1 price added" in shown.value
    assert KEY not in shown.value


@pytest.mark.parametrize(("named", "why"), [("XAU", "no ISIN"), (EM, "not held")])
def test_a_named_security_that_takes_no_fetch_says_why(data: Path, named: str, why: str) -> None:
    """Gold takes its series; a security without units has nothing to value."""
    (data / "assets.yaml").write_text(
        yaml.safe_dump(
            {
                "assets": [
                    {"id": "c", "kind": "gold", "value": 1.0, "trades": [BUY | {"security": "XAU"}]}
                ]
            }
        )
    )
    fetched = _fetch(data, FakeGet([]), only=(named,))
    assert why in fetched.refused[named]
    assert fetched.calls == 0
