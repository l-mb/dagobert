"""The daily closes of the held securities from EODHD (eodhd.com; its free plan serves a year of
history and 20 calls a day), each user with a key of their own (`KEY`, or the file that
`KEY_FILE` names: the terms allow no shared account). A fetch runs on a user action only
(`prices fetch`, the button of the `Prices` expander): per held ISIN the search for its listing
on Xetra in euros, then its closes since the first trade, at most `HISTORY` back. It adds the
days that the price file lacks, never replaces a stored price, and saves all in one revision
with the values that they record (`prices.save`). The key travels in the URL: no error names it
(rule `prices`)."""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dateutil.relativedelta import relativedelta

from dagobert import prices
from dagobert.model.assets import ISIN
from dagobert.series import FetchError, Getter, Response, http_get

if TYPE_CHECKING:
    from collections.abc import Collection

    from dagobert.history import Observation

KEY, KEY_FILE = "EODHD_API_KEY", "EODHD_API_KEY_FILE"
API = "https://eodhd.com/api"
EXCHANGE = "XETRA"
HISTORY = relativedelta(years=1)  # what the free plan serves
TERMS = "https://eodhd.com/financial-apis/terms-conditions"
# the answers that end the whole fetch: no further call would get through
STOPS = {
    401: f"EODHD refused the key: check {KEY} or the file that {KEY_FILE} names",
    402: "the calls of the EODHD plan for today are used up: they renew at midnight GMT",
    429: "EODHD took too many calls this minute: try again in a minute",
}


class UnpricedError(Exception):
    """A security that the fetch cannot price; the others go on."""


def key() -> str | None:
    """The key: `KEY`, else the text of the file that `KEY_FILE` names; None without either."""
    if found := os.environ.get(KEY, "").strip():
        return found
    if not (path := os.environ.get(KEY_FILE)):
        return None
    try:
        found = Path(path).read_text(encoding="utf-8").strip()
    except OSError as e:
        msg = f"{KEY_FILE}: `{path}` does not read: {e.strerror}"
        raise FetchError(msg) from None
    if not found:
        msg = f"{KEY_FILE}: `{path}` holds no key"
        raise FetchError(msg)
    return found


@dataclass
class _Client:
    """The calls of one fetch with `key`, counted."""

    key: str
    get: Getter
    calls: int = 0

    def json(self, path: str, query: str, what: str) -> list[dict[str, Any]]:
        """The rows of `API/path?query`. A refusal of `STOPS` raises `FetchError`, another
        answer that is no list of rows `UnpricedError` with `what`; an error never names the key."""
        self.calls += 1
        try:
            r: Response = self.get(f"{API}/{path}?{query}&fmt=json&api_token={self.key}")
        except FetchError as e:
            raise FetchError(str(e).replace(self.key, "…")) from None
        if stop := STOPS.get(r.status):
            raise FetchError(stop)
        if r.status != 200:
            msg = f"EODHD sent no {what} (HTTP {r.status})"
            raise UnpricedError(msg)
        try:
            rows = json.loads(r.body.decode("utf-8"))
        except ValueError:
            rows = None
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            msg = f"EODHD sent no {what} ({r.type})"
            raise UnpricedError(msg)
        return rows

    def listing(self, isin: str) -> str:
        """The code of `isin` on Xetra in euros, such as `EUNL`."""
        rows = self.json(f"search/{isin}", f"exchange={EXCHANGE}", f"listing of {isin}")
        found = [r for r in rows if r.get("ISIN") == isin and r.get("Exchange") == EXCHANGE]
        euros = [str(r.get("Code")) for r in found if r.get("Currency") == "EUR"]
        if len(euros) == 1:
            return euros[0]
        if euros:
            msg = f"{isin} has {len(euros)} listings in euros on Xetra: {', '.join(euros)}"
        elif found:
            currencies = ", ".join(sorted({str(r.get("Currency")) for r in found}))
            msg = f"{isin} trades on Xetra in {currencies}, not in euros"
        else:
            msg = f"EODHD knows no listing of {isin} on Xetra"
        raise UnpricedError(msg)

    def closes(self, code: str, since: date) -> prices.Prices:
        """The daily closes of `code` on Xetra from `since` on: as traded, not adjusted for
        distributions, which `adjusted_close` rewrites with each one."""
        ticker = f"{code}.{EXCHANGE}"
        rows = self.json(f"eod/{ticker}", f"from={since:%Y-%m-%d}&period=d&order=a", ticker)
        try:
            points = [(date.fromisoformat(r["date"]), float(r["close"])) for r in rows]
        except KeyError, TypeError, ValueError:
            points = []
        if len(points) < len(rows) or not all(math.isfinite(p) and p > 0 for _, p in points):
            msg = f"EODHD sent closes of {ticker} that do not read"
            raise UnpricedError(msg)
        return points


@dataclass(frozen=True)
class Fetched:
    """What a fetch did: the prices added by security, why a security took none, the values
    that the save recorded, the calls it made, and why it stopped early."""

    added: dict[str, int] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)
    recorded: list[Observation] = field(default_factory=list)
    calls: int = 0
    stopped: str | None = None


def fetch(
    data_dir: Path,
    secret: str,
    get: Getter = http_get,
    *,
    today: date,
    source: str,
    only: Collection[str] = (),
    force: bool = False,
) -> Fetched:
    """The closes of each held ISIN (of `only`, when given) that its price file lacks, from its
    first trade, at most `HISTORY` before `today`, saved in one revision of `source`. A security
    without a listing on Xetra in euros, or with a new price far from a trade nearby
    (`prices.far_off`, unless `force`), takes none. A refusal of `STOPS` ends the calls; the
    prices found before it are saved."""
    held = prices.Securities.of(data_dir)
    client = _Client(secret, get)
    new: dict[str, prices.Prices] = {}
    refused = {
        s: "not held" if s not in held.units else "no ISIN: gold and crypto take their series"
        for s in only
        if s not in held.units or not re.fullmatch(ISIN, s)
    }
    stopped = None
    for isin in (s for s in held.units if re.fullmatch(ISIN, s) and (not only or s in only)):
        stored = {day for day, _ in prices.read_prices(prices.price_file(data_dir, isin))}
        since = max(min(t.date for t in held.trades[isin]), today - HISTORY)
        try:
            points = [
                p
                for p in client.closes(client.listing(isin), since)
                if p[0] not in stored and p[0] <= today
            ]
        except UnpricedError as e:
            refused[isin] = str(e)
            continue
        except FetchError as e:
            stopped = str(e)
            break
        if not force and (slips := prices.far_off(data_dir, isin, points)):
            refused[isin] = (
                f"a price lies far off: {'; '.join(slips)}; `prices fetch --force` saves it"
            )
        elif points:
            new[isin] = points
    recorded = prices.save(data_dir, new, source=source).recorded if new else []
    return Fetched({s: len(p) for s, p in new.items()}, refused, recorded, client.calls, stopped)
