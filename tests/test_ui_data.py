"""The Data page: the fetch of the series and the import of a history."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from builders import FakeGet
from streamlit.testing.v1 import AppTest

from dagobert import prices, series
from dagobert.model.months import add_months
from dagobert.ui import data as data_page

DATA = """
from pathlib import Path
from dagobert.ui import data
data.page(Path({data!r}))
"""


def test_a_fetch_runs_on_its_button_and_a_refused_one_changes_nothing(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    last = series.read(series.SERIES["vpi"], data)[-1]
    later = add_months(last.month, 1)
    rows = f"{last.month:%Y-%m};{last.value:.1f};\n{later:%Y-%m};200.0;\n".replace(".", ",")
    answers = [
        series.Response(400, "text/html", b"<html>Rate-Limit exceeded</html>"),
        series.Response(200, series.BBK_CSV, rows.encode()),
    ]
    get = FakeGet(answers)
    monkeypatch.setattr(series, "http_get", get)
    at = AppTest.from_string(DATA.format(data=str(data)), default_timeout=30).run()
    assert not at.exception and not get.urls  # nothing fetches by itself
    vpi = next(b for b in at.button if b.label == "Fetch missing months")  # the first fetchable
    vpi.click().run()
    assert [e.value for e in at.error] == [series.RATE_LIMIT]
    assert not series.fetched_file(data, "vpi").exists()
    next(b for b in at.button if b.label == "Fetch missing months").click().run()
    assert len(get.urls) == 2
    assert [s.value for s in at.success] == [f"Added 1 month, up to {later:%Y-%m}."]
    assert series.read(series.SERIES["vpi"], data)[-1] == series.Point(later, 200.0)
    assert any(f", fetched up to {later:%Y-%m} on " in m.value for m in at.markdown)


def test_the_data_page_names_the_optional_series_not_fetched_yet(data: Path) -> None:
    """Every shipped series is ready; MSCI World and Bitcoin come only with a fetch. Bitcoin held
    without a price of its own needs its series: it comes first, and the page warns."""
    assert not data_page.needed(data)
    told = data_page.summary(data, {})
    assert told.startswith(f"{len(series.SERIES) - 2} of {len(series.SERIES)} series are ready.")
    assert "MSCI World" in told
    assert "Bitcoin" in told
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("  bitcoin: {mean: 0.1}\n")
    buy = {"date": "2026-01-02", "kind": "buy", "security": "BTC", "units": 0.5, "amount": 4000}
    wallet = {"id": "w", "kind": "crypto", "value": 1.0, "trades": [buy]}
    (data / "assets.yaml").write_text(yaml.safe_dump({"assets": [wallet]}))
    assert data_page.needed(data) == {"bitcoin": "BTC"}
    told = data_page.summary(data, data_page.needed(data))
    assert told.index("Bitcoin") < told.index("MSCI World")
    assert "your assets hold BTC without a price" in told
    at = AppTest.from_string(DATA.format(data=str(data)), default_timeout=30).run()
    assert any("hold BTC without a price of their own" in w.value for w in at.warning)
    assert any("Snapshot page" in w.value or "Assets page" in w.value for w in at.warning)
    prices.save(data, "BTC", [(date(2026, 1, 2), 8000.0)], source="test")
    assert not data_page.needed(data)  # a price of its own values it


def test_an_imported_history_keeps_the_last_value_of_each_month(data: Path) -> None:
    at = AppTest.from_string(DATA.format(data=str(data)), default_timeout=30).run()
    assert any("Not fetched yet" in i.value for i in at.info)
    download = b"Date,Close\n2024-01-15,1.5\n2024-01-31,2.0\n2024-02-29,3.0\n2999-01-01,4.0\n"
    at.file_uploader[0].upload("history.csv", download, "text/csv").run()
    assert not at.exception and not at.error
    captions = [c.value for c in at.caption]
    assert "2 months from 2024-01 to 2024-02: 2 new, read as EUR." in captions
    assert any("line 5: 2999-01-01 is in the future" in c for c in captions)
    next(b for b in at.button if b.label == "Import 2 months").click().run()
    assert series.read(series.SERIES["msci-world"], data) == [
        series.Point(date(2024, 1, 1), 2.0),
        series.Point(date(2024, 2, 1), 3.0),
    ]
    assert [s.value for s in at.success] == ["Imported 2 months, up to 2024-02."]
    assert not at.file_uploader[0].value  # a new upload field

    def again(download: bytes) -> tuple[list[str], list[str], bool]:
        at.file_uploader[0].upload("history.csv", download, "text/csv").run()
        assert not at.exception
        [button] = [b for b in at.button if b.label.startswith("Import")]
        return [e.value for e in at.error], [w.value for w in at.warning], button.disabled

    errors, warnings, disabled = again(b"Date,Close\n2024-02-29,30.0\n2024-04-30,5.0\n")
    assert errors == [
        "Not importable: no month from 2024-03 to 2024-03. The months must follow each other."
    ]
    assert disabled  # the historical model needs months that follow each other
    errors, warnings, disabled = again(b"Date,Close\n2024-02-29,30.0\n2024-03-29,5.0\n")
    assert (errors, disabled) == ([], False)
    assert warnings[0].endswith(": 2024-01 go, the file lacks them; another value in 1 month.")
    assert any(b.label == "Import 2 months ⚠" for b in at.button)  # the replace shows
