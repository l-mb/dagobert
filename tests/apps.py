"""What several UI test modules share: AppTest scripts, the pages drawn on a plan that reaches
every page (`render`), a plan that reaches every phase, the stream grid, gold coins, a revision
written on a given day and the headers of the summary."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from pathlib import Path

import pytest
import yaml
from builders import HISTORY, PHASE_LABELS, PHASES, PHASES_TEXT
from german import ACTIVATE
from streamlit.testing.v1 import AppTest

from dagobert import i18n, report, revisions
from dagobert.model.streams import Stream
from dagobert.ui import assets, main, runs, tables

# the stream grids with a `factor` column per phase
STREAMS = tables.Table(Stream, "streams", ("name",), entries={"factor": PHASE_LABELS})


# As in `main.py`: a spawned worker of the process pool imports the script as `__mp_main__`, which
# must not draw the page again (bare, it logged hundreds of warnings past the capture of pytest)
EXPLORER = """
if __name__ == "__main__":
    from pathlib import Path
    from dagobert.ui import explorer
    explorer.page(Path({data!r}))
"""


XAU_TRADES = [
    {"date": "2024-01-10", "kind": "buy", "security": "XAU", "units": 2, "amount": 4000},
    {"date": "2025-06-01", "kind": "buy", "security": "XAU", "units": 1, "amount": 2500},
    {"date": "2025-09-01", "kind": "sell", "security": "XAU", "units": 2.5, "amount": 7500},
]


COINS = {"id": "coins", "kind": "gold", "value": 9000, "trades": XAU_TRADES}


ASSUMPTIONS = """
from pathlib import Path
from dagobert.ui import assumptions
assumptions.page(Path({data!r}))
"""


MAIN = main.__file__


# Every page but the Explorer (`EXPLORER`), each drawn alone after the other
PAGE = """
from pathlib import Path
from dagobert.store import assets_file, streams_file
from dagobert.ui import assets, assumptions, cashflows, features, flows, overview, scenarios
from dagobert.ui import snapshot, spend
from dagobert.ui import data as data_page
data = Path({data!r})
overview.page(streams_file(data))
snapshot.page(assets_file(data))
assets.page(assets_file(data))
cashflows.page(streams_file(data))
spend.page(streams_file(data))
flows.page(data)
features.page(data)
data_page.page(data)
assumptions.page(data)
scenarios.page(data)
"""


def note(pages: str) -> str:
    """The note of the scenario: a long one on the editors, which a phone folds, a short one on the
    explorer, which stays a caption."""
    return " ".join(["Rent out *the* flat_1 and retire on $5 a day."] * (5 if pages == PAGE else 1))


def render(
    data: Path,
    pages: str,
    *,
    phone: bool = False,
    lang: i18n.Language = "en",
    mode: str | None = None,
) -> AppTest:
    """`pages` of a plan with the note of `note`, a fifth phase, gold and crypto with their tax
    columns, a savings plan into the crypto wallet, VPW on the rent and a recorded value (its
    correction on the Snapshot page), in the `mode` of `?mode=`."""
    scenario = data / "scenarios" / "base.yaml"
    scenario.write_text(f"{scenario.read_text()}note: {note(pages)}\n")
    with (data / "assumptions.yaml").open("a") as fh:  # gold and crypto with their tax columns
        fh.write("  gold: {mean: 0.04, stdev: 0.15}\n  bitcoin: {mean: 0.1, stdev: 0.6}\n")
        fh.write("spending: {base: no_pay, categories: [wohnen], vpw: {floor: 300}}\n")
    assumptions = data / "assumptions.yaml"  # a fifth phase, labeled: a column of each sheet
    assumptions.write_text(
        assumptions.read_text().replace(
            PHASES_TEXT, PHASES_TEXT.replace("}}", "}, x: {label: Teilzeit mit Kind}}")
        )
    )
    reach_every_phase(scenario, ["x"])
    btc = {"date": "2025-12-01", "kind": "buy", "security": "BTC", "units": 0.1, "amount": 9000}
    wallet = {"id": "wallet", "kind": "crypto", "value": 9000, "trades": [btc]}
    held = yaml.safe_load((data / "assets.yaml").read_text())["assets"]
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [*held, COINS, wallet]}))
    with (data / "cashflows.yaml").open("a") as fh:  # its tab, its row and its slider
        fh.write("  - {name: Coins, kind: savings, amount: -150, into: wallet, every: 3}\n")
    (data / "history.csv").write_text(HISTORY)
    at = AppTest.from_string(ACTIVATE + pages.format(data=str(data)), default_timeout=60)
    at.query_params["mobile"] = str(int(phone))
    at.query_params["lang"] = lang
    if mode:
        at.query_params["mode"] = mode
    for key, value in assets.opened("giro", "value", "asof").items():  # a link of the Overview
        at.query_params[key] = value
    at.run()
    assert not at.exception
    return at


def reach_every_phase(scenario: Path, more: list[str] | None = None) -> None:
    """Phase changes of `scenario` into every phase of `PHASES` and `more`: the Cashflows page
    shows a column for a phase that the scenario reaches."""
    every = [*PHASES, *(more or [])]
    changes = ", ".join(f"{{from: 2026-{n + 1:02d}-01, phase: {p}}}" for n, p in enumerate(every))
    text = scenario.read_text().replace("phases: [{from: 2026-01-01, phase: work}]", "")
    scenario.write_text(f"{text}phases: [{changes}]\n")


def record(data: Path, stamp: str, source: str, texts: revisions.Texts) -> None:
    """Write `texts` as the app does, on the day of `stamp`."""
    when = datetime.strptime(stamp, "%Y%m%dT%H%M%S.%f%z")

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Frozen:
            return cls.fromtimestamp(when.timestamp(), UTC)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(revisions, "datetime", Frozen)
        revisions.write(data, source, lambda: texts, validate=False)


def labels(data: Path, lang: i18n.Language = "en") -> dict[str, str]:
    """The headers of the summary by term, in `lang`, as they head a run of the base scenario."""
    run = runs.options(data, "fixed").run_one(data / "scenarios" / "base.yaml")
    assert run is not None
    with i18n.use(lang):
        return {c.term: c.label for c in report.summary_columns([run])}
