"""The end of an asset: a term deposit that paid out, an account that was closed. `close` moves
its row of `assets.yaml` from `assets` into `closed`, with the day and what it paid out, and
`reopen` moves it back. No run and no table of the open assets reads a closed asset; the records
keep its values up to its end (`history.observations`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dagobert import references, revisions
from dagobert.loader import load_assets, load_closed
from dagobert.references import Kind
from dagobert.store import Where, assets_file, moved

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

FILE = "assets.yaml"


@dataclass(frozen=True)
class Close:
    asset: str
    ended: date
    payout: float

    def __str__(self) -> str:
        """The end of the source of its revision: `close festgeld`."""
        return f"close {self.asset}"


def check(data_dir: Path, close: Close) -> None:
    """Refuse (ValueError) an asset that is gone, an end before the date of its value, which
    would then be of a closed asset, and an asset that another input names: a sale, a savings
    plan or a loan would name nothing."""
    assets = {a.id: i for i, a in enumerate(load_assets(data_dir))}
    if close.asset not in assets:
        msg = f"the asset {close.asset} is gone"
        raise ValueError(msg)
    asof = load_assets(data_dir)[assets[close.asset]].asof
    if asof is not None and close.ended < asof:
        msg = f"its value is of {asof}, after the end: close it on that day or later"
        raise ValueError(msg)
    users = references.of(data_dir).orphans(
        Kind.ASSET, close.asset, FILE, ("assets", assets[close.asset])
    )
    if users:
        msg = f"other inputs name it: {'; '.join(str(u) for u in users[:3])}"
        raise ValueError(msg)


def apply(data_dir: Path, close: Close, *, source: str) -> None:
    """Close the asset as one revision of `source`, `check` inside the write."""

    def wrap(row: Any) -> dict[str, Any]:  # noqa: ANN401 a ruamel node
        return {"ended": close.ended, "payout": close.payout, "asset": row}

    def edit() -> revisions.Texts:
        check(data_dir, close)
        file = assets_file(data_dir)
        text = file.path.read_text(encoding="utf-8")
        return {FILE: moved(text, FILE, (*file.keys, Where("id", close.asset)), ("closed",), wrap)}

    revisions.write(data_dir, source, edit)


def reopen(data_dir: Path, asset: str, *, source: str) -> None:
    """Move the closed `asset` back into the assets, as it was, as one revision of `source`.
    ValueError when it is no closed asset any more."""

    def edit() -> revisions.Texts:
        at = next((i for i, c in enumerate(load_closed(data_dir)) if c.asset.id == asset), None)
        if at is None:
            msg = f"{asset} is no closed asset any more"
            raise ValueError(msg)
        text = (data_dir / FILE).read_text(encoding="utf-8")
        return {
            FILE: moved(
                text, FILE, ("closed", at), ("assets",), lambda row: row["asset"], required=False
            )
        }

    revisions.write(data_dir, source, edit)
