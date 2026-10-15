"""Shared fixtures."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest
import yaml
from builders import ASSETS, PHASES_TEXT

from dagobert import tax
from dagobert.model import taxes
from dagobert.model.taxes import TAX_DIR, TAX_YEARS


@pytest.fixture(autouse=True)
def plain_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI output without ANSI codes: typer forces a rich terminal under GitHub Actions."""
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture
def data(tmp_path: Path) -> Path:
    """A data directory: born 1977, `horizon_age` 51, start 2026-01, the four phases, the assets
    `giro` (cash 1,000) and `depot` (equity 5,000, cost basis 4,000), the stream `Miete` of
    -500 in `wohnen`, and `scenarios/base.yaml` in `work`."""
    (tmp_path / "assumptions.yaml").write_text(
        "person: {born: 1977-01-01, horizon_age: 51}\n"
        "start: 2026-01-01\n"
        f"{PHASES_TEXT}"
        "returns:\n"
        "  equity: {mean: 0.05}\n"
        "  fixed_income: {mean: 0.03}\n"
        "  cash: {mean: 0.02}\n"
        "  property: {mean: 0.01}\n"
    )
    (tmp_path / "assets.yaml").write_text(ASSETS)
    (tmp_path / "cashflows.yaml").write_text(
        "streams:\n  - name: Miete\n    cat: wohnen\n    amount: -500\n"
    )
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios" / "base.yaml").write_text(
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
    )
    return tmp_path


@pytest.fixture
def later_tax_year(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., int]:
    """A tax data directory of its own with every year file. `make(**changes)` adds the year
    after the newest: the constants of 2026, the year of the test plans, with `changes`. It
    returns that year. Read its constants through the engine or `tax.for_year`, never a
    `for_year` imported before the fixture: that one caches across tests."""
    folder = tmp_path / "tax"
    shutil.copytree(TAX_DIR, folder)
    monkeypatch.setattr(tax, "TAX_DIR", folder)
    monkeypatch.setattr(tax, "for_year", cache(tax.for_year.__wrapped__))

    def make(**changes: float) -> int:
        later = tax.for_year(2026).model_copy(update=changes | {"year": TAX_YEARS[-1] + 1})
        (folder / f"{later.year}.yaml").write_text(yaml.safe_dump(later.model_dump(mode="json")))
        monkeypatch.setattr(taxes, "TAX_YEARS", (*TAX_YEARS, later.year))
        return later.year

    return make
