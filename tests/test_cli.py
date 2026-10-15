"""The commands of the CLI and the option bundle `Options`."""

from __future__ import annotations

import os
import re
import sys
import threading
import tomllib
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import patch

import numpy as np
import pytest
from builders import NO_READ_ONLY_DIRECTORY
from click import unstyle
from streamlit import config as streamlit_config
from typer.testing import CliRunner

from dagobert import cli, datadir, i18n, prices, revisions, schema, series, transfer, ui
from dagobert.cli import app
from dagobert.runner import DATA_ENV, WORKERS_ENV, Options


def test_options_run_the_concrete_scenarios(data: Path) -> None:
    """A template (`abstract`) gives no run, a file named twice one, and two scenarios of one name
    take their files too. With `mortality` a run has its survival curve."""
    template = data / "scenarios" / "tpl.yaml"
    template.write_text("name: tpl\nabstract: true\n")
    base = data / "scenarios" / "base.yaml"
    copy = data / "scenarios" / "copy.yaml"
    copy.write_text(base.read_text())
    opts = Options(data=data, out=data / "out", model="fixed", paths=1, seed=42, mortality=True)

    assert [r.scenario for r in opts.run_all([base, template, copy, base])] == [
        "base (base)",
        "base (copy)",
    ]
    [result] = opts.run_all([base, template])

    assert opts.run_one(template) is None
    assert (result.scenario, result.paths) == ("base", 1)
    assert result.survival is not None
    assert len(result.survival) == len(result.months)
    assert result.survival[0] == pytest.approx(1.0)
    assert np.all(np.diff(result.survival) <= 0)
    plain = replace(opts, mortality=False).run_one(base)
    assert plain is not None
    assert plain.survival is None


@pytest.mark.parametrize(("flags", "shown"), [([], "€ of 2026-01"), (["--nominal"], "nominal €")])
def test_run_shows_euros_of_the_start_unless_nominal(
    data: Path, flags: list[str], shown: str
) -> None:
    """The data directory comes from the environment (`DAGOBERT_DATA`)."""
    out = data / "out"
    args = ["run", str(data / "scenarios" / "base.yaml"), "--out", str(out), "--model", "fixed"]
    result = CliRunner().invoke(app, [*args, *flags], env={DATA_ENV: str(data)})
    assert result.exit_code == 0, result.output
    assert f"<h2>Summary in {shown}: fixed (" in (out / "index.html").read_text("utf-8")


@pytest.mark.parametrize(
    ("flags", "env"), [(["--lang", "de"], {}), ([], {cli.LANG_ENV: "de_DE.UTF-8"})]
)
def test_run_writes_the_report_in_the_language_asked(
    data: Path, flags: list[str], env: dict[str, str]
) -> None:
    """The language of `--lang` or of a locale (`DAGOBERT_LANG`) writes the report, not the
    console summary."""
    out = data / "out"
    args = ["run", str(data / "scenarios" / "base.yaml"), "--data", str(data), "--out", str(out)]
    result = CliRunner().invoke(app, [*args, "--model", "fixed", *flags], env=env)
    assert result.exit_code == 0, result.output
    content = (out / "index.html").read_text("utf-8")
    assert '<html lang="de">' in content
    assert "<h2>Zusammenfassung in €, Kaufkraft 2026-01: fixed (" in content
    assert ">Risiko bis 51</th>" in content  # the run ends at 51
    assert "Summary in € of 2026-01" in result.output
    assert "Chance to" in result.output
    assert i18n.language() == "en"


def test_run_names_the_language_in_its_help() -> None:
    result = CliRunner().invoke(app, ["run", "--help"], env={"COLUMNS": "200"})
    assert "--lang" in result.output
    assert cli.LANG_ENV in result.output


def test_run_refuses_no_paths_with_a_usage_error(data: Path) -> None:
    args = ["run", str(data / "scenarios" / "base.yaml"), "--data", str(data), "--paths", "0"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "Traceback" not in result.output


def test_run_refuses_a_language_without_a_catalogue(data: Path) -> None:
    args = ["run", str(data / "scenarios" / "base.yaml"), "--data", str(data), "--lang", "fr"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2
    assert "'fr' is no language of the report: en or de" in " ".join(
        result.output.replace("│", " ").split()
    )


def test_run_leaves_out_the_templates_and_refuses_only_templates(data: Path) -> None:
    """A template (`abstract`) runs only through a scenario that extends it: a note names the ones
    left out, and without another scenario the command ends with one line and exit code 1."""
    (data / "scenarios" / "tpl.yaml").write_text("name: tpl\nabstract: true\n")
    run = ["run", "--out", str(data / "out"), "--model", "fixed"]
    env = {DATA_ENV: str(data)}
    alone = CliRunner().invoke(app, [*run, str(data / "scenarios" / "tpl.yaml")], env=env)
    assert alone.exit_code == 1
    assert alone.stderr.splitlines() == [
        "nothing to run: tpl: a template (abstract) runs only through a scenario that extends it"
    ]
    assert not (data / "out").exists()
    both = CliRunner().invoke(
        app, [*run, *(str(data / "scenarios" / s) for s in ("tpl.yaml", "base.yaml"))], env=env
    )
    assert both.exit_code == 0, both.output
    assert "Templates (abstract), not run: tpl" in both.output


def test_run_refuses_two_files_of_one_name(data: Path, tmp_path: Path) -> None:
    """The report names a run by its file, so one of two `base.yaml` would go missing. One file
    named twice, in two spellings, is no second file."""
    base = data / "scenarios" / "base.yaml"
    (other := tmp_path / "other" / "base.yaml").parent.mkdir()
    other.write_text(base.read_text())
    run = ["run", "--data", str(data), "--out", str(data / "out"), "--model", "fixed"]
    result = CliRunner().invoke(app, [*run, str(base), str(other)])
    assert result.exit_code == 2
    # rich wraps the message in a box (at 80 columns on GitHub Actions, where typer forces a
    # terminal and colours the paths)
    said = re.sub(r"[\s│]", "", unstyle(result.output))
    assert re.sub(r"\s", "", f"files of one name, {base} and {other}: the report") in said
    assert not (data / "out").exists()
    again = data / "scenarios" / ".." / "scenarios" / "base.yaml"
    assert CliRunner().invoke(app, [*run, str(base), str(again)]).exit_code == 0


def test_run_opens_the_data_directory(data: Path) -> None:
    """A directory without a manifest gets one. An input that does not load ends the run with
    its file, line and key path, without a traceback."""
    args = ["run", str(data / "scenarios" / "base.yaml"), "--data", str(data), "--model", "fixed"]
    args += ["--out", str(data / "out")]
    assert CliRunner().invoke(app, args).exit_code == 0
    assert (data / "manifest.yaml").exists()
    assets = data / "assets.yaml"
    assets.write_text(assets.read_text().replace("value: 5000", "valu: 5000"))
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert result.output.splitlines() == [
        "assets.yaml:6: assets[1].value: Field required",
        "assets.yaml:8: assets[1].valu: unknown key",
    ]


@NO_READ_ONLY_DIRECTORY
def test_a_directory_that_refuses_a_write_ends_a_command_with_one_line(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As on Windows, which does not tell in advance (`os.access`) that a folder is read-only:
    the first write fails with a plain `PermissionError`, which ends the command as one line."""
    monkeypatch.setattr(os, "access", lambda *_args, **_kwargs: True)
    data.chmod(0o500)
    try:
        result = CliRunner().invoke(
            app, ["run", str(data / "scenarios" / "base.yaml"), "--data", str(data)]
        )
    finally:
        data.chmod(0o700)
    assert result.exit_code == 1
    assert result.output.startswith("[Errno 13] Permission denied: ")


def test_historical_runs_once_the_equity_series_is_imported(data: Path, tmp_path: Path) -> None:
    run = [
        "run",
        str(data / "scenarios" / "base.yaml"),
        "--data",
        str(data),
        "--out",
        str(tmp_path),
    ]
    result = CliRunner().invoke(app, [*run, "--model", "historical"])
    assert result.exit_code == 1
    assert "The historical model needs the series msci-world." in result.output
    download = tmp_path / "msci.csv"
    download.write_text("Date,Close\n2000-01-03,99.5\n2000-01-31,100.0\n2000-02-29,101.0\n")
    imported = CliRunner().invoke(
        app, ["series", "import", "msci-world", str(download), "--data", str(data)]
    )
    assert imported.exit_code == 0, imported.output
    assert "msci-world: 2 months, 2000-01 to 2000-02" in imported.output
    assert [p.value for p in series.read(series.SERIES["msci-world"], data)] == [100.0, 101.0]
    result = CliRunner().invoke(app, [*run, "--model", "historical"])
    assert result.exit_code == 0, result.output
    listed = CliRunner().invoke(app, ["series", "list", "--data", str(data)])
    assert listed.exit_code == 0, listed.output
    assert "fetched" in listed.output


def test_series_import_reads_month_value_rows_as_they_are_and_refuses_a_gap(
    data: Path, tmp_path: Path
) -> None:
    """The `msci_world.csv` of an older data directory imports without a mapping."""
    old = tmp_path / "msci_world.csv"
    args = ["series", "import", "msci-world", str(old), "--data", str(data)]
    old.write_text("month,value\n1969-12,141.36\n1970-01,133.52\n")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert series.read(series.SERIES["msci-world"], data) == [
        series.Point(date(1969, 12, 1), 141.36),
        series.Point(date(1970, 1, 1), 133.52),
    ]
    old.write_text("month,value\n1969-12,141.36\n1970-02,133.52\n")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "no month from 1970-01 to 1970-01" in result.output
    assert len(series.read(series.SERIES["msci-world"], data)) == 2  # the import before stays


def test_series_import_of_a_bad_row_ends_with_one_line_naming_it(
    data: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "msci_world.csv"
    bad.write_text("month,value\n1969-12,141.36\n1970-01,abc\n")
    result = CliRunner().invoke(
        app, ["series", "import", "msci-world", str(bad), "--data", str(data)]
    )
    assert result.exit_code == 1
    said = " ".join(result.output.split())  # rich wraps the line
    assert said.startswith("Not imported: line 3: ")
    assert said.count("Not imported") == 1
    assert "Traceback" not in said


def test_only_an_equity_series_takes_an_import(data: Path) -> None:
    result = CliRunner().invoke(app, ["series", "import", "vpi", str(data / "assets.yaml")])
    assert result.exit_code == 2
    assert "cannot import vpi, only msci-world" in result.output


@pytest.mark.parametrize(
    "command",
    [
        ["prices", "import", "XAU"],
        ["trades", "import", "depot"],
        ["series", "import", "msci-world"],
    ],
)
def test_an_import_refuses_a_file_that_is_no_text(
    data: Path, tmp_path: Path, command: list[str]
) -> None:
    """A spreadsheet or a PDF named by mistake, neither UTF-8 nor cp1252: no traceback."""
    (binary := tmp_path / "export.xlsx").write_bytes(b"\x81\x8d")
    result = CliRunner().invoke(app, [*command, str(binary), "--data", str(data)])
    assert result.exit_code == 1
    assert "Not imported: not a text table" in result.output


@pytest.mark.parametrize(
    ("names", "asked"),
    [
        ([], ["vpi", "msci-world", "bitcoin", "usd-eur"]),
        (["msci-world", "vpi", "umlaufsrendite"], ["msci-world", "vpi"]),
    ],
)
def test_series_fetch_asks_no_source_again_that_refused(
    data: Path, names: list[str], asked: list[str]
) -> None:
    calls: list[str] = []

    def update(s: series.Series, _data: Path, _get: series.Getter) -> series.Update:
        calls.append(s.name)
        if s.name == "vpi":
            raise series.FetchError(series.RATE_LIMIT)
        return series.Update([date(2026, 9, 1)], [], date(2026, 9, 1))

    with patch.object(series, "update", update):
        result = CliRunner().invoke(app, ["series", "fetch", *names, "--data", str(data)])
    assert calls == asked
    assert result.exit_code == 1
    assert "umlaufsrendite: not fetched: api.statistiken.bundesbank.de refused" in result.output
    assert "msci-world: added 1 month, up to 2026-09" in result.output


def test_series_fetch_names_a_record_that_the_inputs_refuse(data: Path) -> None:
    """One line instead of a traceback, the other series go on, and the exit code is 1."""

    def fetch(s: series.Series, _data: Path, *, source: str) -> prices.Fetched:
        del source
        if s.name == "bitcoin":
            msg = "assets.yaml: refused"
            raise ValueError(msg)
        return prices.Fetched(series.Update([date(2026, 9, 1)], [], date(2026, 9, 1)), [])

    with patch.object(prices, "fetch_series", fetch):
        result = CliRunner().invoke(app, ["series", "fetch", "--data", str(data)])
    assert result.exit_code == 1
    assert "bitcoin: not saved: assets.yaml: refused\n" in result.output
    assert "usd-eur: added 1 month, up to 2026-09" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("args", "answer", "source"),
    [
        (["--example"], "", datadir.FROM_EXAMPLE),
        (["--example", "starter"], "", datadir.FROM_EXAMPLE),
        (["--born", "1985-03-14"], "", datadir.EMPTY_PLAN),
        ([], "1985-13-01\n1985-03-14\n", datadir.EMPTY_PLAN),  # asked again until a date reads
    ],
)
def test_init_starts_a_plan_in_an_empty_directory_only(
    tmp_path: Path, args: list[str], answer: str, source: str
) -> None:
    """A run on a missing directory names the start instead of a traceback. A start into a
    directory with a plan changes nothing. A home folder may hold umlauts and spaces."""
    data = tmp_path / "Jürgen Weiß" / "data"
    run = ["run", str(data / "scenarios" / "plan.yaml"), "--data", str(data), "--model", "fixed"]
    result = CliRunner().invoke(app, [*run, "--out", str(tmp_path / "out")])
    assert result.exit_code == 1
    assert result.output == f"{data}: no such directory: {datadir.START}\n"
    init = ["init", "--data", str(data)]
    result = CliRunner().invoke(app, [*init, *args], input=answer)
    assert result.exit_code == 0, result.output
    assert [e.source for e in revisions.entries(data)] == [source]
    result = CliRunner().invoke(app, [*run, "--out", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    result = CliRunner().invoke(app, [*init, "--born", "1985-03-14"])
    assert (result.exit_code, result.output) == (
        1,
        f"{data}: holds a plan already: a start writes only into an empty data directory\n",
    )
    assert len(revisions.entries(data)) == 1


@pytest.mark.parametrize(
    ("args", "why"),
    [
        (["--born", "1899-12-31"], "is no date"),
        (["--born", "2999-01-01"], "is no date"),
        (["--born", "14.03.1985"], "is no date"),
        (["starter"], "start it with --example starter"),
        (["--example", "nope"], "'nope' is not one of 'engineer', 'starter'"),
    ],
)
def test_init_refuses_an_implausible_date_of_birth_or_example(
    tmp_path: Path, args: list[str], why: str
) -> None:
    result = CliRunner().invoke(app, ["init", "--data", str(tmp_path / "data"), *args])
    assert result.exit_code == 2
    assert why in " ".join(result.output.replace("│", " ").split())
    assert not (tmp_path / "data").exists()


def test_init_refuses_a_file_as_its_data_directory(tmp_path: Path) -> None:
    (file := tmp_path / "data").write_text("")
    result = CliRunner().invoke(app, ["init", "--data", str(file), "--example"])
    assert (result.exit_code, result.output) == (
        1,
        f"{file}: not a directory: a data directory is a folder\n",
    )


@pytest.mark.parametrize(
    ("args", "env", "address", "workers", "opens"),
    [
        ([], {}, "localhost", None, True),
        (["--address", "0.0.0.0", "--no-browser", "--workers", "2"], {}, "0.0.0.0", "2", False),
        (
            [],
            {"DAGOBERT_ADDRESS": "0.0.0.0", "DAGOBERT_BROWSER": "false", WORKERS_ENV: "2"},
            "0.0.0.0",
            "2",
            False,
        ),
    ],
)
def test_app_serves_as_its_options_or_the_environment_say(
    data: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    env: dict[str, str],
    address: str,
    workers: str | None,
    opens: bool,
) -> None:
    served: list[list[str]] = []
    opened = threading.Event()
    monkeypatch.setattr(sys, "argv", sys.argv)  # restored after the test: the command sets it
    monkeypatch.setattr("streamlit.web.cli.main", lambda: served.append(list(sys.argv)))
    monkeypatch.setattr(ui, "session_seen", threading.Event())
    monkeypatch.setattr(cli, "RECONNECT_WAIT", 0.0)
    monkeypatch.setattr("webbrowser.open", lambda _url: opened.set())

    with patch.dict(os.environ):  # restored after the test: the command sets variables
        for name in [
            DATA_ENV,
            WORKERS_ENV,
            "DAGOBERT_ADDRESS",
            "DAGOBERT_BROWSER",
            *cli.STREAMLIT_ENV,
        ]:
            os.environ.pop(name, None)
        os.environ.update(env, STREAMLIT_CLIENT_TOOLBAR_MODE="auto")  # set by the deployment
        result = CliRunner().invoke(app, ["app", "--data", str(data), *args])

        assert result.exit_code == 0, result.output
        assert f"--server.address={address}" in served[0]
        assert os.environ.get(WORKERS_ENV) == workers
        assert os.environ["STREAMLIT_SERVER_HEADLESS"] == "true"
        assert os.environ["STREAMLIT_CLIENT_TOOLBAR_MODE"] == "auto"
    assert opened.wait(2 if opens else 0.2) is opens


def _settings(table: Mapping[str, object], prefix: str = "") -> Iterator[tuple[str, object]]:
    """The values of a TOML table by their dotted keys."""
    for name, value in table.items():
        if isinstance(value, Mapping):
            yield from _settings(cast("Mapping[str, object]", value), f"{prefix}{name}.")
        else:
            yield f"{prefix}{name}", value


def test_app_sets_the_settings_of_the_test_server() -> None:
    """`dagobert app` and a server started in the repository root look and behave the same."""
    toml = tomllib.loads((Path(__file__).parents[1] / ".streamlit" / "config.toml").read_text())
    options = streamlit_config.get_config_options()
    for key, value in _settings(toml):
        written = str(value).lower() if isinstance(value, bool) else str(value)  # TOML `false`
        assert cli.STREAMLIT_ENV[options[key].env_var] == written, key


def _export(data: Path, out: Path) -> Path:
    result = CliRunner().invoke(app, ["export", "--data", str(data), "--out", str(out)])
    assert result.exit_code == 0, result.output
    return out if out.suffix == ".zip" else next(out.glob("*.zip"))


def test_run_takes_an_export_zip_as_its_data(
    data: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The zip unpacks into a temporary directory: the same summary, nothing written beside it."""
    away = tmp_path_factory.mktemp("away")
    zipped = _export(data, away)
    args = ["--model", "fixed", "--out", str(away / "out")]
    from_zip = CliRunner().invoke(app, ["run", "base.yaml", "--data", str(zipped), *args])
    from_dir = CliRunner().invoke(
        app, ["run", str(data / "scenarios" / "base.yaml"), "--data", str(data), *args]
    )
    assert from_zip.exit_code == 0, from_zip.output
    # the title of the summary holds the time to the second: two runs may fall into two seconds
    clock = re.compile(r"\d{2}:\d{2}:\d{2}")
    assert clock.sub("", from_zip.output) == clock.sub("", from_dir.output)
    assert sorted(p.name for p in away.iterdir()) == sorted([zipped.name, "out"])


def test_import_asks_at_a_conflict_until_a_choice(
    data: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    away = tmp_path_factory.mktemp("away")
    local = transfer.unpacked(_export(data, away / "x.zip"))
    for directory, value in [(local, "7000"), (data, "6000")]:  # outside the app
        assets = directory / "assets.yaml"
        assets.write_text(assets.read_text().replace("value: 5000", f"value: {value}"))
    args = ["import", str(_export(local, away / "back.zip")), "--data", str(data)]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1
    assert "keep or take?" in result.output
    assert "+    value: 7000" in result.output  # the diff of the zip against the base
    assert "keep or take: assets.yaml" in result.output
    declined = CliRunner().invoke(app, [*args, "--take", "assets.yaml"], input="n\n")
    assert declined.exit_code == 1
    assert "value: 6000" in (data / "assets.yaml").read_text()
    both = CliRunner().invoke(app, [*args, "--take-all", "--keep-all"])
    assert both.exit_code == 2
    taken = CliRunner().invoke(app, [*args, "--take-all", "--yes"])
    assert taken.exit_code == 0, taken.output
    assert "value: 7000" in (data / "assets.yaml").read_text()
    assert revisions.entries(data)[-1].source == "import back.zip"


def test_app_serves_an_export_zip_unpacked_beside_it(
    data: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    zipped = _export(data, tmp_path_factory.mktemp("away") / "x.zip")
    monkeypatch.setattr(sys, "argv", sys.argv)  # restored after the test: the command sets it
    monkeypatch.setattr("streamlit.web.cli.main", lambda: None)
    serve = ["app", "--data", str(zipped), "--no-browser"]
    with patch.dict(os.environ):  # restored after the test: the command sets variables
        result = CliRunner().invoke(app, serve)
        assert result.exit_code == 0, result.output
        assert os.environ[DATA_ENV] == str(zipped.with_suffix(""))
    assert (zipped.with_suffix("") / "assumptions.yaml").is_file()
    (zipped.with_suffix("") / schema.MANIFEST).write_text("schema: 2\napp: 0.1.0\nbase: other\n")
    with patch.dict(os.environ):
        result = CliRunner().invoke(app, serve)
    assert result.exit_code == 1
    assert "is no unpack of x.zip" in result.output
