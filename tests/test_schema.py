"""The manifest and the migration chain: its rules with toy steps, the real steps on the
fixtures of `tests/schemas/<n>/`, one data directory of schema n each."""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from builders import FIXTURES, HISTORY, NO_READ_ONLY_DIRECTORY, adopt

from dagobert import __version__, datadir, loader, revisions, scenariofiles, schema
from dagobert.loader import load_plan
from dagobert.problems import NOT_UTF8, InputError
from dagobert.schema import Inputs, SchemaError

# what `to_4` appends to an `assumptions.yaml` without growth and inflation: the mark of schema 4
MARK = f"# {schema.REAL.format(0.02, 0.02)}\npension_growth: 0.0\n"


def _steps(ran: list[str], extra: dict[str, object] | None = None) -> tuple[schema.Step, ...]:
    """`to_2` names every asset after its id, plus `extra`; `to_3` writes the asset ids of
    `history.csv` in capitals."""

    def to_2(inputs: Inputs) -> set[str]:
        ran.append("to_2")
        for row in inputs.yaml("assets.yaml")["assets"]:
            row.update({"name": row["id"].title(), **(extra or {})})
        return {"assets.yaml"}

    def to_3(inputs: Inputs) -> set[str]:
        ran.append("to_3")
        inputs.set_text("history.csv", inputs.text("history.csv").replace(",giro,", ",GIRO,"))
        return {"history.csv"}

    return to_2, to_3


def _opened_before(data: Path) -> Path:
    """`data` as a folder that Dagobert opened once and that lost its manifest: its history holds
    one. Without it a folder without manifest was written by hand in the current format."""
    revisions.write(
        data, "manifest", lambda: {schema.MANIFEST: schema.manifest_text()}, validate=False
    )
    (data / schema.MANIFEST).unlink()
    return data


def _manifest(data: Path) -> dict[str, object]:
    found: dict[str, object] = yaml.safe_load((data / schema.MANIFEST).read_text())
    return found


@pytest.mark.parametrize(("start", "ran"), [(None, ["to_2", "to_3"]), (2, ["to_3"]), (3, [])])
def test_migrate_runs_the_steps_from_the_schema_of_the_manifest(
    data: Path, monkeypatch: pytest.MonkeyPatch, start: int | None, ran: list[str]
) -> None:
    (data / "history.csv").write_text(HISTORY)
    base = {"base": "20261012T140312.123456Z"} if start else {}  # of an unpacked export
    if start:
        (data / schema.MANIFEST).write_text(f"schema: {start}\napp: 0.0.1\nbase: {base['base']}\n")
    called: list[str] = []
    monkeypatch.setattr(schema, "STEPS", _steps(called))
    before = dict(schema.Tree(data))
    texts = schema.migrate(schema.Tree(data))
    assert called == ran
    if not ran:
        assert texts == {}  # current: nothing to write
        return
    assert list(texts)[-1] == schema.MANIFEST
    assert yaml.safe_load(texts[schema.MANIFEST]) == {"schema": 3, "app": __version__} | base
    assert texts["history.csv"] == HISTORY.replace("giro", "GIRO")
    if "to_2" in ran:
        assert "    # salary account\n    value: 1000\n    name: Giro\n" in texts["assets.yaml"]
    # a file that no step changed keeps every character
    assert all(before[path] == text for path, text in schema.Tree(data).items())


def test_a_directory_without_a_manifest_has_schema_1(data: Path) -> None:
    """Every step runs, and only `to_4` changes these files, once: its mark stops it."""
    tree = schema.Tree(data)
    assert schema.version(tree) == 1
    manifest = (
        f"# Written by Dagobert. Do not edit.\nschema: {schema.current()}\napp: {__version__}\n"
    )
    migrated = schema.migrate(tree)
    assert migrated == {
        "assumptions.yaml": tree["assumptions.yaml"] + MARK,
        schema.MANIFEST: manifest,
    }
    again = {**tree, "assumptions.yaml": migrated["assumptions.yaml"]}
    assert schema.migrate(again) == {schema.MANIFEST: manifest}


def test_a_newer_schema_names_both_versions(data: Path) -> None:
    (data / schema.MANIFEST).write_text("schema: 9\napp: 9.9.9\n")
    message = f"schema 9, written by Dagobert 9.9.9. This is Dagobert {__version__}, which reads"
    with pytest.raises(SchemaError, match=message):
        datadir.open(data)
    assert not (data / revisions.REVISIONS).exists()  # an older app records nothing there


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("schema: 1\napp: 0.1.0\nhead: x\n", "manifest.yaml:3: head: unknown key"),
        ("", "manifest.yaml: empty"),
    ],
)
def test_a_broken_manifest_names_its_problem(data: Path, text: str, expected: str) -> None:
    (data / schema.MANIFEST).write_text(text)
    with pytest.raises(InputError) as caught:
        datadir.open(data)
    assert str(caught.value) == expected


def test_open_needs_a_data_directory(tmp_path: Path) -> None:
    """An empty or missing directory names the start of a plan, one with other inputs is none."""
    with pytest.raises(InputError, match=r"no such directory: start a plan with `dagobert init"):
        datadir.open(tmp_path / "missing")
    with pytest.raises(InputError, match=r"no plan yet: start a plan with `dagobert init"):
        datadir.open(tmp_path)
    (tmp_path / "assets.yaml").write_text("assets: []\n")
    with pytest.raises(InputError, match=r"not a data directory: it has no assumptions\.yaml"):
        datadir.open(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["assets.yaml"]


@NO_READ_ONLY_DIRECTORY
def test_a_read_only_directory_runs_without_a_manifest_but_not_without_a_migration(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (data / "history.csv").write_text(HISTORY)
    before = revisions.entries(_opened_before(data))
    with (data / "assumptions.yaml").open("a") as f:
        f.write(MARK)  # migrated, the manifest lost
    data.chmod(0o555)
    try:
        datadir.open(data)
        monkeypatch.setattr(schema, "STEPS", _steps([]))
        with pytest.raises(InputError, match="read-only, so the inputs of schema 1 cannot migrate"):
            datadir.open(data)
    finally:
        data.chmod(0o755)
    assert not (data / schema.MANIFEST).exists()
    assert revisions.entries(data) == before


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        (b"assets:\n  - {id: giro\n", "assets.yaml:3: "),
        (b"assets:\n  - {id: giro, kind: cash, value: 1, note: \x07}\n", "assets.yaml:2: "),
        ("assets:\n  - {id: giro, name: Gebühr}\n".encode("cp1252"), f"assets.yaml:2: {NOT_UTF8}"),
    ],
)
def test_a_step_names_a_file_that_does_not_parse(
    data: Path, monkeypatch: pytest.MonkeyPatch, written: bytes, expected: str
) -> None:
    (data / "assets.yaml").write_bytes(written)
    monkeypatch.setattr(schema, "STEPS", _steps([]))
    with pytest.raises(InputError, match=f"^{re.escape(expected)}"):
        schema.migrate(schema.Tree(data))


def test_a_step_reads_the_changes_of_the_steps_before(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`set_text` on a file that an earlier step changed in place keeps that change."""

    def to_3(inputs: Inputs) -> set[str]:
        inputs.set_text("assets.yaml", inputs.text("assets.yaml") + "# end\n")
        return {"assets.yaml"}

    monkeypatch.setattr(schema, "STEPS", (_steps([])[0], to_3))
    text = schema.migrate(schema.Tree(data))["assets.yaml"]
    assert "    name: Giro\n" in text
    assert text.endswith("\n# end\n")


def test_a_folder_written_by_hand_gets_the_manifest_and_no_step(tmp_path: Path) -> None:
    """Without manifest and `revisions/` it is of the current format: `to_4` would turn the real
    growth and inflation of its scenario into other values. A folder that lost its manifest
    (`revisions/`) migrates from schema 1."""
    hand = shutil.copytree(datadir.EXAMPLE, tmp_path / "hand")
    (hand / schema.MANIFEST).unlink()
    (hand / "scenarios" / "hand.yaml").write_text("overrides:\n  inflation: {mean: 0.05}\n")
    texts = dict(schema.Tree(hand))
    lost = shutil.copytree(hand, tmp_path / "lost")
    datadir.open(hand)
    datadir.open(_opened_before(lost))
    assert dict(schema.Tree(hand)) == texts | {
        schema.MANIFEST: (hand / schema.MANIFEST).read_text()
    }
    assert _manifest(hand) == {"schema": schema.current(), "app": __version__}
    assert (lost / "scenarios/hand.yaml").read_text() != texts["scenarios/hand.yaml"]  # `to_4`
    first, *_ = revisions.entries(hand)
    assert first.source == "baseline"


@pytest.mark.parametrize("outside", [False, True])
def test_a_schema_1_folder_with_a_log_before_the_manifest_migrates(
    tmp_path: Path, outside: bool
) -> None:
    old = shutil.copytree(FIXTURES / "1", tmp_path / "old")
    adopt(old, validate=False)  # the baseline
    if outside:
        (old / "assets.yaml").write_text((old / "assets.yaml").read_text() + "\n")
        adopt(old, validate=False)  # outside the app
    assert revisions.entries(old)[0].source == "baseline"
    datadir.open(old)
    assert revisions.entries(old)[-1].source.startswith("migrate 1")
    loader.check(old)


def test_a_manifest_stamped_between_the_look_and_the_lock_is_kept(tmp_path: Path) -> None:
    hand = shutil.copytree(datadir.EXAMPLE, tmp_path / "hand")
    (hand / schema.MANIFEST).unlink()
    real = revisions.write

    def stamped(data_dir: Path, source: str, edit: Any, **kw: bool) -> Any:
        real(data_dir, "other", lambda: {schema.MANIFEST: schema.manifest_text("base")}, **kw)
        return real(data_dir, source, edit, **kw)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(revisions, "write", stamped)
        datadir.open(hand)
    assert _manifest(hand).get("base") == "base"
    assert [e.source for e in revisions.entries(hand)].count("other") == 1
    assert len(revisions.entries(hand)) == 2


def test_open_writes_the_manifest_once(data: Path) -> None:
    datadir.open(data)
    assert _manifest(data) == {"schema": schema.current(), "app": __version__}
    stamp = (data / schema.MANIFEST).stat().st_mtime_ns
    datadir.open(data)
    assert (data / schema.MANIFEST).stat().st_mtime_ns == stamp


def test_open_writes_back_a_migration_as_one_revision(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After the baseline of the files as they were, so an old revision migrates again."""
    (data / "history.csv").write_text(HISTORY)
    _opened_before(data)
    monkeypatch.setattr(schema, "STEPS", _steps([]))
    datadir.open(data)
    assert _manifest(data)["schema"] == 3
    assert "name: Depot" in (data / "assets.yaml").read_text()
    assert (data / "history.csv").read_text() == HISTORY.replace("giro", "GIRO")
    baseline, *_, migrated = revisions.entries(data)
    assert baseline.source == "baseline"
    assert migrated.source == f"migrate 1 → 3 (Dagobert {__version__})"
    assert migrated.files == ("assets.yaml", "history.csv", schema.MANIFEST)


def test_a_migration_whose_inputs_do_not_load_changes_nothing(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model stays strict after a migration."""
    (data / "history.csv").write_text(HISTORY)
    before = dict(schema.Tree(_opened_before(data)))
    monkeypatch.setattr(schema, "STEPS", _steps([], {"bogus": 1}))
    with pytest.raises(InputError) as caught:
        datadir.open(data)
    assert str(caught.value).splitlines() == [
        "assets.yaml:7: assets[0].bogus: unknown key",
        "assets.yaml:13: assets[1].bogus: unknown key",
    ]
    assert dict(schema.Tree(data)) == before  # no manifest either


def test_migrate_dir_migrates_a_copy_in_place(data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (data / "history.csv").write_text(HISTORY)
    monkeypatch.setattr(schema, "STEPS", _steps([]))
    schema.migrate_dir(data)
    assert _manifest(data)["schema"] == 3
    assert "name: Giro" in (data / "assets.yaml").read_text()


@pytest.mark.parametrize("version", range(1, schema.current()))
def test_a_fixture_of_an_old_schema_migrates_and_loads(tmp_path: Path, version: int) -> None:
    """Every scenario loads after the migration."""
    data = shutil.copytree(FIXTURES / str(version), tmp_path / "data")
    datadir.open(_opened_before(data))
    assert _manifest(data)["schema"] == schema.current()
    for scenario in scenariofiles.scenario_paths(data):
        load_plan(data, scenario)


@pytest.mark.parametrize("path", ["assets.yaml", "scenarios/base.yaml"])  # also in overrides
def test_to_2_renames_isin_to_security_in_place(tmp_path: Path, path: str) -> None:
    data = _opened_before(shutil.copytree(FIXTURES / "1", tmp_path / "data"))
    before = (data / path).read_text()
    datadir.open(data)
    assert (data / path).read_text() == before.replace("isin: ", "security: ")


def test_to_3_writes_the_phases_of_schema_2_and_keeps_every_other_character(tmp_path: Path) -> None:
    """The phases follow `start` as text. A bAV policy without phases pays in `work`, and a
    concrete scenario without a phase at the start works from it, written first in the root of its
    chain from the earliest change of a scenario there: schema 2 ran `work` before the first
    change, after `shift`, and a sibling's change before the start still holds."""
    data = shutil.copytree(FIXTURES / "2", tmp_path / "data")
    before = dict(schema.Tree(data))
    datadir.open(data)
    after = dict(schema.Tree(data))
    changed = {path for path, text in after.items() if before.get(path) != text}
    assert changed == {
        "assumptions.yaml",
        "assets.yaml",
        "scenarios/late.yaml",
        "scenarios/shifted.yaml",
        "scenarios/tpl.yaml",
        schema.MANIFEST,
    }
    start = "start: 2026-01-01\n"
    assert after["assumptions.yaml"] == (
        before["assumptions.yaml"].replace(start, start + schema.PHASES) + MARK
    )
    assert "    contribution: 100\n    phases: [work]\n" in after["assets.yaml"]
    assert after["assets.yaml"].count("phases:") == 2  # an empty list stays
    work = "  - {from: 2026-01-01, phase: work}\n"
    assert work + "  - {from: 2030-01-01" in after["scenarios/late.yaml"]
    assert work + "  - {from: 2026-01-01, phase: alt" in after["scenarios/shifted.yaml"]
    # from the change of `early`, which wins in its month
    assert after["scenarios/tpl.yaml"].endswith("phases:\n  - {from: 2025-06-01, phase: work}\n")
    plans = {path.stem: load_plan(data, path) for path in scenariofiles.scenario_paths(data)}
    assert {name: p.phase_at(p.assumptions.start) for name, p in plans.items()} == dict.fromkeys(
        ("base", "child", "late", "shifted", "tpl"), "work"
    ) | {"early": "unemployed"}
    assert plans["shifted"].phase_at(date(2026, 7, 1)) == "alt"
    assert plans["late"].assumptions.phase_labels["alt"] == "Career break"


def test_to_3_names_an_assumptions_file_that_does_not_parse(tmp_path: Path) -> None:
    data = shutil.copytree(FIXTURES / "2", tmp_path / "data")
    (data / "assumptions.yaml").write_text("start: 2026-01-01\nperson: {born: 1977-01-01: x}\n")
    before = dict(schema.Tree(data))
    with pytest.raises(InputError, match=r"^assumptions.yaml:2: "):
        datadir.open(data)
    assert dict(schema.Tree(data)) == before


def test_to_4_turns_the_nominal_pension_growth_real(tmp_path: Path) -> None:
    """Each file that sets the growth or the inflation gets the growth less its inflation, with a
    comment: `assumptions.yaml` as text, a scenario with the values of its chain. One that sets the
    inflation of its parent keeps what it inherits. The mean path pays the pension of schema 3,
    whichever file of a chain the step reads first (`boost` before its child `burn`)."""
    data = shutil.copytree(FIXTURES / "3", tmp_path / "data")
    before = dict(schema.Tree(data))
    datadir.open(data)
    after = dict(schema.Tree(data))
    changed = {path for path, text in after.items() if before.get(path) != text}
    assert changed == {
        "assumptions.yaml",
        "scenarios/boost.yaml",
        "scenarios/burn.yaml",
        "scenarios/hot.yaml",
        "scenarios/tpl.yaml",
        schema.MANIFEST,
    }
    old = "pension_growth: 0.01  # below the prices\n"
    new = f"# {schema.REAL.format(0.01, 0.03)}\npension_growth: -0.02  # below the prices\n"
    assert after["assumptions.yaml"] == before["assumptions.yaml"].replace(old, new)
    hot = f"  # {schema.REAL.format(0.01, 0.05)}\n  pension_growth: -0.04\n"
    assert hot in after["scenarios/hot.yaml"]
    plans = {path.stem: load_plan(data, path) for path in scenariofiles.scenario_paths(data)}
    nominal = {
        name: round(p.assumptions.pension_growth + p.assumptions.inflation.mean, 6)
        for name, p in plans.items()
    }
    assert nominal == {
        "base": 0.01,
        "boost": 0.04,
        "burn": 0.04,
        "hot": 0.01,
        "tpl": 0.03,
        "child": 0.03,
    }


def test_to_4_runs_once_on_a_directory_that_lost_its_manifest(tmp_path: Path) -> None:
    """Without its manifest a directory counts as schema 1, so every step runs again: the mark in
    `assumptions.yaml` stops `to_4`, also for the real growth of a scenario written since."""
    data = shutil.copytree(FIXTURES / "3", tmp_path / "data")
    datadir.open(data)
    scenarios = data / "scenarios"
    (scenarios / "new.yaml").write_text(
        "name: new\nextends: base\noverrides: {inflation: {mean: 0.05}}\n"
    )
    (scenarios / "own.yaml").write_text(
        "name: own\nextends: base\noverrides: {pension_growth: 0.01}\n"
    )
    migrated = dict(schema.Tree(data))
    (data / schema.MANIFEST).unlink()
    datadir.open(data)
    assert dict(schema.Tree(data)) == migrated


@pytest.mark.parametrize(
    ("inflation", "mean", "written"), [("", 0.02, 0.0), ("{mean: 0.029}", 0.029, -0.009)]
)
def test_to_4_writes_the_default_growth_of_schema_3(
    tmp_path: Path, inflation: str, mean: float, written: float
) -> None:
    """Schema 3 grew the pension by 2% without `pension_growth`, whatever the inflation. The step
    writes it also where it stays 0: the comment marks the directory."""
    data = shutil.copytree(FIXTURES / "3", tmp_path / "data")
    text = (data / "assumptions.yaml").read_text()
    text = text.replace("pension_growth: 0.01  # below the prices\n", "").replace(
        "inflation: {mean: 0.03, stdev: 0.01}\n", f"inflation: {inflation}\n" if inflation else ""
    )
    (data / "assumptions.yaml").write_text(text)
    datadir.open(data)
    after = (data / "assumptions.yaml").read_text()
    assert after == text + f"# {schema.REAL.format(0.02, mean)}\npension_growth: {written}\n"


def test_to_5_drops_deductible_and_flags_a_policy_that_only_deductible_payments_fund(
    tmp_path: Path,
) -> None:
    """A payment into a Basisrente deducts by law: the flag goes, also from the overrides (one
    that held only it goes). A policy that only deductible payments fund, in every scenario,
    becomes a Basisrente with a comment, and the comments of the user stay (owner 2026-10-14). A
    second run changes nothing, also on a directory that lost its manifest."""
    data = shutil.copytree(FIXTURES / "4", tmp_path / "data")
    before = dict(schema.Tree(data))
    datadir.open(data)
    after = dict(schema.Tree(data))
    changed = {path for path, text in after.items() if before.get(path) != text}
    assert changed == {
        "assets.yaml",
        "scenarios/base.yaml",
        "scenarios/child.yaml",
        schema.MANIFEST,
    }
    assert "deductible" not in after["scenarios/base.yaml"] + after["scenarios/child.yaml"]
    assert "    rurup:" not in after["scenarios/child.yaml"]
    assert (
        f"    # {schema.BASISRENTE}\n    basisrente: true\n"
        "    payout: annuity  # the comments of the user stay\n" in after["assets.yaml"]
    )
    assert "  # a Rürup without the flag" in after["assets.yaml"]
    plan = load_plan(data, data / "scenarios" / "child.yaml")
    policies = {a.id: getattr(a, "basisrente", None) for a in plan.assets}
    assert policies == {"giro": None, "ruerup": True, "basis": True, "firma": False}
    (data / schema.MANIFEST).unlink()
    datadir.open(data)
    assert dict(schema.Tree(data)) == after


# a payment into the Rürup without the flag, a deductible one into the company pension
PLAIN = "  - {at: 2030-01-01, type: fund_policy, policy: ruerup, amount: 1}\n"
INTO_FIRMA = "  - {at: 2030-01-01, type: fund_policy, policy: firma, amount: 1, deductible: true}\n"


@pytest.mark.parametrize(
    ("path", "old", "new", "policy"),
    [
        (
            "scenarios/child.yaml",
            "rurup: {deductible: true}",
            "rurup: {deductible: false}",
            "ruerup",
        ),
        ("scenarios/base.yaml", "events:\n", "events:\n" + PLAIN, "ruerup"),
        ("scenarios/base.yaml", "events:\n", "events:\n" + INTO_FIRMA, "firma"),
    ],
    ids=["override", "event", "company"],
)
def test_to_5_leaves_a_policy_of_mixed_payments_to_the_loader(
    tmp_path: Path, path: str, old: str, new: str, policy: str
) -> None:
    """A policy that a payment without `deductible` funds too, in its scenario or by the override
    of a child, stays as it is, and so does a company pension that a severance funds: the
    migration, whose inputs do not load, writes nothing and names the way out."""
    data = shutil.copytree(FIXTURES / "4", tmp_path / "data")
    file = data / path
    file.write_text(file.read_text().replace(old, new, 1))
    before = dict(schema.Tree(data))
    with pytest.raises(InputError, match=rf"\.policy: .* set basisrente on {policy}"):
        datadir.open(data)
    assert dict(schema.Tree(data)) == before


def test_to_6_keeps_the_kindergeld_of_a_stream(tmp_path: Path) -> None:
    """The engine pays the Kindergeld of a child: each child of schema 5 gets `kindergeld: false`,
    in `assumptions.yaml` and in the overrides of a scenario (a flow mapping turns block for the
    comment above the list, the rows keep their style), so a plan pays as before by its stream.
    A second run changes nothing, also on a directory that lost its manifest."""
    data = shutil.copytree(FIXTURES / "5", tmp_path / "data")
    before = dict(schema.Tree(data))
    datadir.open(data)
    after = dict(schema.Tree(data))
    changed = {path for path, text in after.items() if before.get(path) != text}
    assert changed == {"assumptions.yaml", "scenarios/base.yaml", schema.MANIFEST}
    assert (
        f"  # {schema.KINDERGELD}\n  children_born:\n"
        "    - {born: 2016-04-01, kindergeld: false} # the comments of the user stay\n"
        "    - born: 2003-07-15\n      kindergeld: false\n" in after["assumptions.yaml"]
    )
    assert f"    # {schema.KINDERGELD}\n    children_born: [{{" in after["scenarios/base.yaml"]
    plan = load_plan(data, data / "scenarios" / "child.yaml")
    assert [c.kindergeld for c in plan.assumptions.person.children_born] == [False] * 3
    (data / schema.MANIFEST).unlink()
    datadir.open(data)
    assert dict(schema.Tree(data)) == after
