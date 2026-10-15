"""Small plans for engine tests: zero returns, a run without them, neutral assumptions, a plan
from parts, a salary, a cash account, a gold asset and a purchase, the ledger row of an item, the
gain of a harvest. Writes of a data directory: recorded spending, the revision of edits outside
the app."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from dagobert import actuals, files, revisions, schema
from dagobert.engine.core import year_levels
from dagobert.engine.simulation import simulate
from dagobert.model.assets import CashAsset, GoldAsset
from dagobert.model.assumptions import Assumptions, Distribution, Person, PhaseSpec, ReturnClass
from dagobert.model.events import PhaseChange
from dagobert.model.plan import Plan, Scenario
from dagobert.model.streams import Stream
from dagobert.report.charts import said
from dagobert.result import TAX, FloatArray, RunResult
from dagobert.returns import Returns
from dagobert.revisions import Entry
from dagobert.runner import Options
from dagobert.series import Response
from dagobert.tax import flat_rate, for_year

# `chmod` refuses nothing on Windows and for root, who writes to any directory
NO_READ_ONLY_DIRECTORY = pytest.mark.skipif(
    files.WINDOWS or os.geteuid() == 0, reason="no read-only directory on Windows or for root"
)
HISTORY = "date,asset,value\n2026-01-01,giro,1000.00\n"
FIXTURES = Path(__file__).parent / "schemas"  # a data directory per schema version
CLASSES = ("equity", "fixed_income", "cash", "property", "gold", "bitcoin")
# the phases of a new plan (`datadir.NEW_PHASES`) by name, with their labels
PHASE_LABELS = {
    "work": "Work",
    "unemployed": "Unemployed",
    "alt": "Career break",
    "retired": "Retired",
}
PHASES = {name: PhaseSpec(label=label) for name, label in PHASE_LABELS.items()}
PHASES_TEXT = (  # in YAML
    "phases: {work: {label: Work}, unemployed: {label: Unemployed}, alt: {label: Career break}, "
    "retired: {label: Retired}}\n"
)
# `assets.yaml` of the fixture `data`
ASSETS = """\
assets:
  - id: giro
    kind: cash
    # salary account
    value: 1000
  - id: depot
    kind: equity
    value: 5000
    cost_basis: 4000
"""


@dataclass
class FakeGet:
    """A `series.http_get` that sends the answers in turn and keeps the urls asked."""

    answers: list[Response]
    urls: list[str] = field(default_factory=list)

    def __call__(self, url: str) -> Response:
        self.urls.append(url)
        return self.answers.pop(0)


def zero_returns(months: int, paths: int = 1) -> Returns:
    z = np.zeros((paths, months))
    return Returns(rates={name: z.copy() for name in CLASSES}, inflation=z.copy())


def levels(returns: Returns, start_month: int = 1) -> tuple[FloatArray, FloatArray]:
    """The consumer prices of the engine (the inflation of the month before) and the price level of
    each month of the first path, the mean of its calendar year (`year_levels`)."""
    cpi = np.cumprod(np.concatenate([[1.0], 1 + returns.inflation[0, :-1]]))
    return cpi, year_levels(cpi[None, :], start_month)[0]


def zero_run(p: Plan, months: int, paths: int = 1) -> RunResult:
    """The plan on zero returns and inflation, `paths` identical paths (one is a `fixed` run)."""
    return simulate(p, zero_returns(months, paths), "montecarlo" if paths > 1 else "fixed")


def salary(gross: float = 5000.0, **kw: object) -> Stream:
    """A salary `Gehalt` without index."""
    return Stream.model_validate(
        {"name": "Gehalt", "kind": "salary", "gross": gross, "index": None} | kw
    )


def assumptions(**kw: object) -> Assumptions:
    """Born 1977, start 2026-01, the four phases, no inflation, no returns, a cash buffer that
    holds all cash."""
    base: dict[str, object] = {
        "person": Person(born=date(1977, 1, 1)),
        "start": date(2026, 1, 1),
        "phases": PHASES,
        "inflation": Distribution(mean=0.0),
        "returns": {name: ReturnClass(mean=0.0) for name in CLASSES},
        "cash_buffer_months": 1000,
    }
    return Assumptions.model_validate(base | kw)


def plan(
    streams: list[Stream], assets: list[object], scenario: Scenario | None = None, **kw: object
) -> Plan:
    """A plan of the parts, its scenario in `work` from the start until its first change."""
    a = assumptions(**kw)
    return Plan.model_validate(
        {
            "assumptions": a,
            "assets": assets,
            "streams": streams,
            "scenario": started(scenario or Scenario(name="t"), a.start),
        }
    )


def started(scenario: Scenario, start: date) -> Scenario:
    """`scenario` in `work` from `start` until its first change: a run needs a phase there."""
    if scenario.phase_at(start) is not None:
        return scenario
    return scenario.model_copy(update={"phases": [*phases((start, "work")), *scenario.phases]})


def phases(*changes: tuple[date, str]) -> list[PhaseChange]:
    return [PhaseChange.model_validate({"from": at, "phase": p}) for at, p in changes]


def marked(r: RunResult) -> list[str]:
    """The markers of `r` by month in the words of the engine, `2031-04 sell: flat`: its kind
    before what it says (`report.charts.said`)."""
    return [f"{m.month:%Y-%m} {f'{m.kind}: {s}' if (s := said(m)) else m.kind}" for m in r.markers]


def booked(r: RunResult, item: str, side: str = TAX, group: str = "") -> FloatArray:
    """The ledger row of `item` by month, by default of a tax or an SV part, 0 where the run
    books none."""
    assert r.ledger is not None
    return r.ledger.entries.get((side, group, item), np.zeros(len(r.months)))


def harvested(
    pair: tuple[RunResult, RunResult], month: int | date = 11, rate: float | None = None
) -> float:
    """The taxable gain that a harvest stepped up by `month` (an index or a date) in the pair of
    runs with and without it: the latent tax that it saved, over the flat rate."""
    on, off = (
        r.nominal_balance["latent_tax"][r.months.index(month) if isinstance(month, date) else month]
        for r in pair
    )
    return float((on - off) / (flat_rate(0.0, for_year(2026)) if rate is None else rate))


def cash(value: float = 0) -> CashAsset:
    """The cash account `c`."""
    return CashAsset(id="c", kind="cash", value=value)


def gold(value: float, *lots: tuple[date, float], **kw: object) -> GoldAsset:
    """The gold asset `g` worth `value`, with one `XAU` buy of one unit per (date, amount)."""
    trades = [
        {"date": day, "kind": "buy", "security": "XAU", "units": 1, "amount": amount}
        for day, amount in lots
    ]
    return GoldAsset.model_validate(
        {"id": "g", "kind": "gold", "value": value, "trades": trades} | kw
    )


def purchase(at: date = date(2026, 3, 1), **kw: object) -> dict[str, object]:
    """A `buy_property` of `home` for 300,000 € in Niedersachsen (5% Grunderwerbsteuer), 2% costs,
    no loan."""
    buy = {"at": at, "type": "buy_property", "property": {"id": "home"}, "price": 300_000}
    return buy | {"land": "NI", "costs": 0.02} | kw


def spent(data: Path, month: date, amounts: dict[str, float], source: str = "test") -> None:
    """Record `amounts` in `month` of `actuals.csv`, which holds none there yet, as the Save of the
    Spend page does."""
    actuals.save_draft(data, month, {cat: (None, a) for cat, a in amounts.items()}, source=source)


def fixed_run(data: Path, scenario: str = "base") -> RunResult:
    """The one path of a `fixed` run of a scenario of a data directory, without mortality."""
    options = Options(data=data, out=data, model="fixed", paths=1, seed=0, mortality=False)
    result = options.run_one(data / "scenarios" / f"{scenario}.yaml")
    assert result is not None
    return result


def live(data: Path) -> dict[str, str]:
    """The inputs of a data directory by path."""
    return {path: (data / path).read_text() for path in schema.Tree(data)}


def state_at(data: Path, at: str | None = None) -> dict[str, str]:
    """The inputs at a revision (the head without one)."""
    return {path: copy.read_text() for path, copy in revisions.state(data, at).items()}


def adopt(data: Path, *, validate: bool = True) -> Entry | None:
    """The revision of the edits outside the app, the baseline without a log, which every write
    records first: a write without changes."""
    head = revisions.head(data)
    revisions.write(data, "test", lambda: {}, validate=validate)
    return revisions.entries(data)[-1] if revisions.head(data) != head else None


def seen(data: Path, file: str, part: object) -> revisions.Seen:
    """What a page that read `part` of `file` now holds."""
    return revisions.Seen(file, revisions.last_change(data, file), revisions.digest(part))
