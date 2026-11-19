"""The end of an asset: `closed` of `assets.yaml`, what the records keep of it, and `opened`."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest
import yaml

from dagobert import closing, history, rename, revisions
from dagobert.history import actual_totals
from dagobert.loader import load_assets, load_closed, load_plan
from dagobert.model.assets import Assets
from dagobert.problems import InputError
from dagobert.references import Kind
from dagobert.ui import closing as page
from dagobert.ui import summary

if TYPE_CHECKING:
    from pathlib import Path

ASSETS = """\
assets:
  - id: giro
    kind: cash
    value: 1000
  # matured in November
  - id: festgeld
    kind: term_deposit
    value: 2000
    rate: 0.05
    start: 2025-01-01
    matures: 2026-01-01
    asof: 2025-01-01
  # the depot
  - id: depot
    kind: fixed_income
    value: 0
    trades:
      - {date: 2025-02-01, kind: buy, security: LU0290358497, units: 2, amount: 200}
      # sold in full
      - {date: 2026-02-01, kind: sell, security: LU0290358497, units: 2, amount: 210}
"""
CLOSE = closing.Close("festgeld", date(2026, 2, 10), 2090.0)


@pytest.fixture
def held(data: Path) -> Path:
    (data / "assets.yaml").write_text(ASSETS)
    return data


def test_a_close_moves_the_asset_out_of_the_plan_and_a_reopen_brings_it_back(held: Path) -> None:
    closing.apply(held, CLOSE, source="test")
    assert [a.id for a in load_assets(held)] == ["giro", "depot"]
    [closed] = load_closed(held)
    assert (closed.asset.id, closed.ended, closed.payout) == ("festgeld", CLOSE.ended, 2090.0)
    text = (held / "assets.yaml").read_text()
    assert "# matured in November" in text  # the comments around it stay, each once
    assert text.count("# the depot") == 1
    assert "festgeld" not in {a.id for a in load_plan(held, held / "scenarios/base.yaml").assets}

    closing.apply(held, closing.Close("depot", date(2026, 2, 10), 0.0), source="test")
    assert "# sold in full" in (held / "assets.yaml").read_text()  # the comments inside go along
    closing.reopen(held, "depot", source="test")
    closing.reopen(held, "festgeld", source="test")
    before = Assets.model_validate(yaml.safe_load(ASSETS)).assets
    assert {a.id: a for a in load_assets(held)} == {a.id: a for a in before}  # as they were
    assert "closed" not in (held / "assets.yaml").read_text()
    with pytest.raises(ValueError, match="no closed asset"):
        closing.reopen(held, "festgeld", source="test")


def test_a_close_is_refused_before_the_value_and_for_an_asset_in_use(held: Path) -> None:
    with pytest.raises(ValueError, match="its value is of 2025-01-01"):
        closing.check(held, closing.Close("festgeld", date(2024, 12, 31), 0.0))
    with pytest.raises(ValueError, match="the asset gone is gone"):
        closing.check(held, closing.Close("gone", date(2026, 2, 10), 0.0))
    with (held / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: Sparplan, kind: savings, amount: -50, into: depot}\n")
    with pytest.raises(ValueError, match=r"other inputs name it: cashflows\.yaml"):
        closing.apply(held, closing.Close("depot", date(2026, 2, 10), 0.0), source="test")
    assert not load_closed(held)


def test_the_id_of_a_closed_asset_stays_taken(held: Path) -> None:
    closing.apply(held, CLOSE, source="test")
    with pytest.raises(ValueError, match="the closed asset festgeld has the name"):
        rename.preview(held, rename.Rename(Kind.ASSET, "giro", "festgeld"))
    text = (held / "assets.yaml").read_text()
    (held / "assets.yaml").write_text(text.replace("id: giro", "id: festgeld"))
    with pytest.raises(InputError, match="asset ids must be unique: festgeld"):
        load_assets(held)


def test_the_records_keep_a_closed_asset_up_to_its_end(held: Path) -> None:
    """The deposit counts with its value until its end and as 0 from then; the account that took
    its payout holds it."""
    text = (held / "assets.yaml").read_text()
    (held / "assets.yaml").write_text(
        text.replace("value: 1000", "value: 3090\n    asof: 2026-03-05")
    )
    observed = [(date(2026, 1, 15), "giro", 1000.0)]
    revisions.write(held, "test", lambda: history.appended(held, observed))
    assert actual_totals(held) == [(date(2026, 1, 1), 3000.0), (date(2026, 3, 1), 5090.0)]
    closing.apply(held, CLOSE, source="test")
    assert actual_totals(held) == [
        (date(2026, 1, 1), 3000.0),
        (date(2026, 2, 1), 1000.0),  # the month of its end counts it as 0
        (date(2026, 3, 1), 3090.0),
    ]
    # the tile: 2,000 left the deposit, the account took 2,090
    days = date(2026, 3, 6), date(2026, 1, 31)
    assert summary.change(held, load_assets(held), *days) == {"liquid": 90.0}
    # a value recorded after its end counts no more
    late = [(date(2026, 4, 1), "festgeld", 9.0)]
    revisions.write(held, "test", lambda: history.appended(held, late))
    assert actual_totals(held)[-1] == (date(2026, 3, 1), 3090.0)
    assert page.rows(held) == [
        {
            "asset": "festgeld",
            "kind": "term deposit",
            "ended": "2026-02-10",
            "last value": 2100.0,
            "paid out": 2090.0,
        }
    ]


def test_an_opened_asset_counts_as_nothing_before(data: Path) -> None:
    """Money moved into a new account is no loss: with `opened` the account counts from 0, and
    the recorded net worth does not wait for its first value."""
    assets = (
        "assets:\n"
        "  - {id: giro, kind: cash, value: 200, asof: 2026-02-10}\n"
        "  - {id: neu, kind: fixed_income, value: 800, asof: 2026-02-10%s}\n"
    )
    (data / "assets.yaml").write_text(assets % "")
    observed = [(date(2026, 1, 15), "giro", 1000.0)]
    revisions.write(data, "test", lambda: history.appended(data, observed))
    days = date(2026, 3, 1), date(2026, 1, 31)
    assert summary.change(data, load_assets(data), *days) == {"liquid": -800.0}
    assert actual_totals(data) == [(date(2026, 2, 1), 1000.0)]

    (data / "assets.yaml").write_text(assets % ", opened: 2026-02-10")
    assert summary.change(data, load_assets(data), *days) == {"liquid": 0.0}
    assert actual_totals(data) == [(date(2026, 1, 1), 1000.0), (date(2026, 2, 1), 1000.0)]


def test_the_dialog_offers_the_maturity_of_a_deposit_that_matured(held: Path) -> None:
    deposit, giro = (next(a for a in load_assets(held) if a.id == i) for i in ("festgeld", "giro"))
    assert page.ended(deposit, date(2026, 11, 18)) == date(2026, 1, 1)
    assert page.ended(deposit, date(2025, 6, 1)) == date(2025, 6, 1)  # ended early
    assert page.ended(giro, date(2026, 11, 18)) == date(2026, 11, 18)
