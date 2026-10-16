"""Edits of the YAML inputs as text: every other character stays."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from dagobert.problems import Keys
from dagobert.textedit import After, Key, scalars


def test_scalars_keep_the_layout(data: Path) -> None:
    flow = "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
    flow += "events: [{ at: 2027-01-01, type: lump_sum, amount: 1000 }]  # gift\n"
    (data / "scenarios" / "base.yaml").write_text(flow, newline="\n")
    out = scalars(
        data,
        {
            "scenarios/base.yaml": {
                ("events", 0, "at"): date(2027, 2, 1),
                ("events", 0, "amount"): 1234.5,
            },
            "cashflows.yaml": {("streams", 0, "amount"): -510.0},
        },
    )
    assert out["scenarios/base.yaml"] == flow.replace(
        "2027-01-01, type: lump_sum, amount: 1000", "2027-02-01, type: lump_sum, amount: 1234.5"
    )
    assert "    amount: -510\n" in out["cashflows.yaml"]


def test_scalars_add_a_key_after_another(data: Path) -> None:
    flow = "name: base\nphases: [{from: 2026-01-01, phase: work}]\nevents:\n  - {at: 2027-01-01, "
    flow += "type: add_stream, stream: {name: Abo, amount: -6, every: 3}}  # tv\n"
    block = "streams:\n  - name: Kfz\n    amount: -600\n    every: 12  # yearly\n    index: null\n"
    (data / "scenarios" / "base.yaml").write_text(flow, newline="\n")
    (data / "cashflows.yaml").write_text(block, newline="\n")
    start = After("every", date(2026, 1, 1))
    out = scalars(
        data,
        {
            "scenarios/base.yaml": {
                ("events", 0, "stream", "start"): start,
                ("events", 0, "stream", "amount"): -7,
            },
            "cashflows.yaml": {("streams", 0, "start"): start},
        },
    )
    assert out["scenarios/base.yaml"] == flow.replace(
        "amount: -6, every: 3}", "amount: -7, every: 3, start: 2026-01-01}"
    )
    assert out["cashflows.yaml"] == block.replace("# yearly\n", "# yearly\n    start: 2026-01-01\n")


def test_scalars_add_two_keys_behind_a_last_line_without_its_newline(data: Path) -> None:
    (data / "assumptions.yaml").write_text("tax:\n  pkv: true", newline="\n")
    spots: dict[Keys, After] = {("tax", "b"): After("pkv", 2), ("tax", "a"): After("pkv", 1)}
    out = scalars(data, {"assumptions.yaml": spots})["assumptions.yaml"]
    assert out == "tax:\n  pkv: true\n  a: 1\n  b: 2\n"


@pytest.mark.parametrize(
    ("null", "written"),
    [
        ("a:\n  founded:\n  rv: regular\n", "a:\n  founded: 2026-02-01\n  rv: regular\n"),
        ("a:\n  founded:   # c\n  rv: x\n", "a:\n  founded: 2026-02-01 # c\n  rv: x\n"),
        ("a: {founded: , rv: x}\n", "a: {founded: 2026-02-01, rv: x}\n"),
        ("a: {rv: x, founded: ~}\n", "a: {rv: x, founded: 2026-02-01}\n"),
        ("a:\n  founded: null\n", "a:\n  founded: 2026-02-01\n"),
        ("a:\n  founded:", "a:\n  founded: 2026-02-01"),
    ],
)
def test_scalars_replace_a_null_with_or_without_its_text(
    data: Path, null: str, written: str
) -> None:
    """ruamel.yaml places a null without text at what follows it: the next key stays."""
    (data / "assumptions.yaml").write_text(null, newline="\n")
    out = scalars(data, {"assumptions.yaml": {("a", "founded"): date(2026, 2, 1)}})
    assert out["assumptions.yaml"] == written


def test_scalars_refuse_a_text_that_does_not_read_as_the_value(data: Path) -> None:
    """ruamel.yaml places an alias at its anchor: the write would replace `&x`."""
    (data / "assumptions.yaml").write_text("a: &x 5\nb: *x\n", newline="\n")
    with pytest.raises(ValueError, match="no scalar 5 at column 4"):
        scalars(data, {"assumptions.yaml": {("b",): 6}})


def test_scalars_write_lf_also_for_a_file_with_crlf(data: Path) -> None:
    """A file saved on Windows comes back with LF line ends, as every write of the app."""
    text = "streams:\r\n  - name: Kfz\r\n    amount: -600\r\n    every: 12\r\n"
    (data / "cashflows.yaml").write_bytes(text.encode())
    start = After("every", date(2026, 1, 1))
    spots: dict[Keys, int | After] = {
        ("streams", 0, "amount"): -660,
        ("streams", 0, "start"): start,
    }
    out = scalars(data, {"cashflows.yaml": spots})["cashflows.yaml"]
    assert out == text.replace("-600", "-660").replace("\r\n", "\n") + "    start: 2026-01-01\n"


def test_scalars_rename_a_key_and_quote_a_text_only_where_needed(data: Path) -> None:
    text = "streams:\n  - name: Rent of the flat  # cold\n    factor: {work: 0.5}\n"
    text += "    phases: [work, alt]\n  - name: 'Miete'\n"
    (data / "cashflows.yaml").write_text(text, newline="\n")
    spots: dict[Keys, str | Key] = {
        ("streams", 0, "name"): "Cold rent",
        ("streams", 0, "factor", "work"): Key("job"),
        ("streams", 0, "phases", 0): "on",
        ("streams", 1, "name"): "Rent: flat",
    }
    out = scalars(data, {"cashflows.yaml": spots})["cashflows.yaml"]
    assert out == (
        "streams:\n  - name: Cold rent  # cold\n    factor: {job: 0.5}\n"
        "    phases: ['on', alt]\n  - name: 'Rent: flat'\n"
    )
    assert yaml.safe_load(out)["streams"][0]["phases"] == ["on", "alt"]
