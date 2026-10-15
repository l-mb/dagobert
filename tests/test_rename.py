"""A rename of an asset id, a stream name, a phase or a relative with every input that names
it."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from builders import fixed_run

from dagobert import datadir, history, references, revisions, store, textedit
from dagobert.references import Kind
from dagobert.rename import Rename, apply, preview

SOURCE = "Page: rename"
ARRAYS = ("liquid", "total", "income", "expenses", "taxes", "capital_taxes")


@pytest.fixture
def example(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    shutil.copytree(datadir.EXAMPLES / "engineer", data)
    datadir.open(data)  # the baseline, a revision of its own
    return data


def _comments(data: Path) -> dict[Path, list[str]]:
    return {
        path: [line for line in path.read_text().splitlines() if line.lstrip().startswith("#")]
        for path in sorted([*data.glob("*.yaml"), *data.glob("scenarios/*.yaml")])
    }


def _sites(data: Path, kind: Kind, name: str) -> int:
    refs = references.of(data)
    return len(refs.defined[kind].get(name, [])) + len(refs.uses(kind, name))


@pytest.mark.parametrize(
    ("kind", "old", "new", "scenario"),
    [
        # the sale of `plan`, `overrides.assets.flat`, `shift: {flat-sale: 24}`; the tag `flat`,
        # the asset `flat-loan` and the event id `flat-sale` stay
        (Kind.ASSET, "flat", "rented-flat", "stress"),
        # the ids of a purchase (the Rename of the Events tab), not the tag `home`
        (Kind.ASSET, "home", "own-home", "buy-home"),
        (Kind.ASSET, "home-loan", "mortgage", "buy-home"),
        # two rows, `of: Salary` of the bonus, `names: [Salary, …]` of an `end_streams`
        (Kind.STREAM, "Salary", "Base salary", "severance"),
        # the key in `assumptions.yaml`, `phases: [work]` of streams and the bAV, phase changes
        (Kind.PHASE, "work", "job", "sabbatical"),
        # the key in `person.relatives`, `from: mother` of the inheritance and of the gift
        (Kind.RELATIVE, "mother", "mum", "sabbatical"),
    ],
)
def test_a_rename_rewrites_every_input_and_keeps_the_run(
    example: Path, kind: Kind, old: str, new: str, scenario: str
) -> None:
    def run() -> tuple[list[str], list[np.ndarray]]:
        result = fixed_run(example, scenario)
        return result.phases, [getattr(result, name) for name in ARRAYS]

    (phases, arrays), comments = run(), _comments(example)
    sites, before = _sites(example, kind, old), revisions.entries(example)
    shown = preview(example, Rename(kind, old, new))
    assert all(old in line.old and new in line.new for line in shown.lines)
    apply(example, shown, source=SOURCE)
    [entry] = revisions.entries(example)[len(before) :]
    assert (entry.source, entry.renamed) == (SOURCE, None)
    assert set(entry.files) == {line.file for line in shown.lines}
    assert (_sites(example, kind, old), _sites(example, kind, new)) == (0, sites)
    assert _comments(example) == comments
    renamed, after = run()
    assert renamed == [new if phase == old else phase for phase in phases]
    assert all(map(np.array_equal, after, arrays, strict=True))


def test_an_asset_takes_its_history(example: Path) -> None:
    def rows(asset: str) -> list[tuple[date, float]]:
        return [(day, value) for day, held, value in history.read_history(example) if held == asset]

    depot = rows("depot")
    apply(example, preview(example, Rename(Kind.ASSET, "depot", "broker")), source=SOURCE)
    assert (rows("depot"), rows("broker")) == ([], depot)
    assert "into: broker" in (example / "cashflows.yaml").read_text()


@pytest.mark.parametrize(
    ("kind", "old", "new", "refusal"),
    [
        (Kind.ASSET, "flat", "Flat-Loan", "the asset flat-loan exists"),
        (Kind.ASSET, "flat", "home", "the asset home exists"),  # bought in `buy-home`
        (Kind.ASSET, "gone", "new", "the asset gone is gone"),
        (Kind.STREAM, "Rent", "Hausgeld", "the stream Hausgeld exists"),  # of an `add_stream`
        (Kind.STREAM, "Rent", " Rent ", "one line, without spaces at its ends"),
        (Kind.STREAM, "Rent", "Rent", "has the name Rent"),
        (Kind.PHASE, "work", "Job", "is no phase name"),
        (Kind.PHASE, "work", "on", "is no phase name"),
        (Kind.PHASE, "work", "retired", "the phase retired exists"),
        (Kind.RELATIVE, "mother", "Mum", "is no relative name"),
        (Kind.TAG, "flat", "home", "a tag has no rename"),
    ],
)
def test_a_rename_is_refused(example: Path, kind: Kind, old: str, new: str, refusal: str) -> None:
    with pytest.raises(ValueError, match=refusal):
        preview(example, Rename(kind, old, new))


def test_a_rename_is_refused_for_a_name_of_the_history_or_a_use(example: Path) -> None:
    with (example / "history.csv").open("a") as fh:
        fh.write("2026-01-31,old-car,9000.00\n")
    with pytest.raises(ValueError, match=r"history\.csv holds values of old-car"):
        preview(example, Rename(Kind.ASSET, "flat", "old-car"))
    (example / "scenarios" / "car.yaml").write_text(
        "name: Car\nextends: plan\nevents: [{at: 2030-01-01, type: repay, loan: car-loan}]\n"
    )
    with pytest.raises(ValueError, match="the inputs use the asset name car-loan"):
        preview(example, Rename(Kind.ASSET, "flat-loan", "car-loan"))


def test_a_rename_refuses_inputs_changed_since_its_list(example: Path) -> None:
    shown = preview(example, Rename(Kind.STREAM, "Rent", "Rent of the home"))
    rent = next(i for i, s in enumerate(store.streams_file(example).rows()) if s["name"] == "Rent")
    amount: textedit.Spots = {"cashflows.yaml": {("streams", rent, "amount"): -1500}}
    revisions.write(example, "Cashflows", lambda: textedit.scalars(example, amount))
    with pytest.raises(revisions.ConflictError, match=r"cashflows\.yaml"):
        apply(example, shown, source=SOURCE)
    shown = preview(example, Rename(Kind.STREAM, "Rent", "Rent of the home"))
    extra = example / "scenarios" / "extra.yaml"
    extra.write_text("name: Extra\nextends: plan\nevents:\n")
    extra.write_text(extra.read_text() + "  - {at: 2030-01-01, type: end_streams, names: [Rent]}\n")
    with pytest.raises(ValueError, match="the inputs changed since the list"):
        apply(example, shown, source=SOURCE)
    assert "names: [Rent]" in extra.read_text()
