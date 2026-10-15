"""Command line interface."""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Annotated
from urllib.parse import urlsplit

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from dagobert import (
    csvimport,
    datadir,
    files,
    history,
    i18n,
    prices,
    report,
    revisions,
    series,
    store,
    tradeimport,
    transfer,
)
from dagobert.loader import load_scenario
from dagobert.money import format_eur
from dagobert.problems import InputError, RefusedError
from dagobert.runner import DATA_ENV, WORKERS_ENV, ModelName, Options
from dagobert.schema import SchemaError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()
DataDir = Annotated[
    Path,
    typer.Option("--data", envvar=DATA_ENV, help="Directory with assumptions/assets/cashflows"),
]
OutDir = Annotated[Path, typer.Option("--out", help="Output directory")]
ModelOpt = Annotated[ModelName, typer.Option("--model")]
PathsOpt = Annotated[int, typer.Option("--paths", min=1, help="Monte Carlo paths")]
SeedOpt = Annotated[int, typer.Option("--seed")]
MortalityOpt = Annotated[bool, typer.Option("--mortality/--no-mortality")]
NominalOpt = Annotated[
    bool, typer.Option("--nominal", help="Nominal euros instead of euros of the start")
]
LANG_ENV = "DAGOBERT_LANG"


def _language(tag: str) -> i18n.Language:
    """A language of the app by a language tag or a locale: `de`, `de-DE`, `de_DE.UTF-8`."""
    if (lang := i18n.negotiate([tag])) is None:
        msg = f"{tag!r} is no language of the report: {' or '.join(i18n.LANGUAGES)}"
        raise typer.BadParameter(msg)
    return lang


LangOpt = Annotated[
    i18n.Language,
    typer.Option(
        "--lang",
        envvar=LANG_ENV,
        parser=_language,
        metavar="|".join(i18n.LANGUAGES),
        help="The language of the report, also a locale such as de_DE; the console summary "
        "stays English",
    ),
]


def _render(
    opts: Options, scenarios: list[Path], *, nominal: bool = False, lang: i18n.Language = "en"
) -> None:
    """The unit of money and the language are no run options: the explorer switches them
    without new runs. The console summary stays English."""
    results = opts.run_all(scenarios)
    opts.out.mkdir(parents=True, exist_ok=True)
    with i18n.use(lang):
        path = report.write_html(
            results,
            opts.out / "index.html",
            observed=report.Observed(
                history.actual_totals(opts.data), series.consumer_prices(opts.data)
            ),
            nominal=nominal,
        )
    report.print_summary(results, nominal=nominal)
    console.print(f"[dim]{path}[/dim]")


# What ends a command with its problems, without a traceback: inputs that do not load, a
# missing series, a zip that is refused or changed inputs, and what the system refuses
# (`OSError`): a lock that another write holds (`revisions.BusyError`), a read-only directory
# (`revisions.ReadOnlyError`; on Windows a plain `PermissionError` at the first write).
PROBLEMS = (
    InputError,
    SchemaError,
    series.MissingSeriesError,
    OSError,
    transfer.ArchiveError,
    transfer.StaleError,
)


@contextmanager
def _reported() -> Iterator[None]:
    try:
        yield
    except PROBLEMS as err:
        typer.echo(err, err=True)
        raise typer.Exit(1) from err


@contextmanager
def _opened(data: Path, *, archive: bool = False) -> Iterator[Path]:
    """The data directory, brought to the current schema first (`datadir.open`). With `archive`
    an export zip as `data` unpacks into a temporary directory, migrated, without a revision."""
    with _reported():
        if archive and data.is_file():
            with transfer.temporary(data) as directory:
                yield directory
        else:
            datadir.open(data)
            yield data


@app.command()
def run(
    scenarios: list[Path],
    *,
    data: DataDir = Path("data"),
    out: OutDir = Path("out"),
    model: ModelOpt = "montecarlo",
    paths: PathsOpt = 5000,
    seed: SeedOpt = 42,
    mortality: MortalityOpt = True,
    nominal: NominalOpt = False,
    lang: LangOpt = "en",
) -> None:
    """Simulate one or more scenarios and write the report. With an export zip as `--data` a
    scenario is named by its file name, such as `plan.yaml`."""
    with _opened(data, archive=True) as inputs:
        named = scenarios if inputs == data else [inputs / "scenarios" / s.name for s in scenarios]
        if missing := [
            s.name for s, path in zip(scenarios, named, strict=True) if not path.is_file()
        ]:
            msg = f"no scenario {', '.join(missing)}"
            raise typer.BadParameter(msg)
        stems = Counter(s.stem for s in {s.resolve() for s in named})
        if shared := list(dict.fromkeys(str(s) for s in named if stems[s.stem] > 1)):
            msg = f"files of one name, {' and '.join(shared)}: the report names a run by its file"
            raise typer.BadParameter(msg)
        if templates := [s.stem for s in dict.fromkeys(named) if load_scenario(s).abstract]:
            if len(templates) == len(set(named)):
                typer.echo(
                    f"nothing to run: {', '.join(templates)}: a template (abstract) runs only "
                    "through a scenario that extends it",
                    err=True,
                )
                raise typer.Exit(1)
            console.print(f"[dim]Templates (abstract), not run: {', '.join(templates)}[/dim]")
        _render(
            Options(inputs, out, model, paths, seed, mortality), named, nominal=nominal, lang=lang
        )


def _born(text: str) -> date:
    """A date of birth, as `datadir.start_empty` takes it."""
    try:
        born = date.fromisoformat(text)
    except ValueError:
        msg = f"{text!r} is no date: type it as 1985-03-14"
        raise typer.BadParameter(msg) from None
    try:
        datadir.check_born(born)
    except ValueError as err:
        raise typer.BadParameter(str(err)) from None
    return born


@app.command()
def init(
    name: Annotated[
        datadir.ExampleName | None,
        typer.Argument(
            metavar="[NAME]",
            show_default=False,
            help=f"With --example: the example to start, by default {datadir.EXAMPLE.name}. "
            "starter: a simple plan in German of an employee of 31 who wants to stop working "
            "early. "
            "engineer: the plan of an engineer of 40 that uses every feature",
        ),
    ] = None,
    *,
    data: DataDir = Path("data"),
    example: Annotated[bool, typer.Option("--example", help="Start from an example")] = False,
    born: Annotated[
        date | None,
        typer.Option(
            "--born",
            parser=_born,
            metavar="YYYY-MM-DD",
            help="Your date of birth, for an empty plan. Asked for without it",
        ),
    ] = None,
) -> None:
    """Start a plan in an empty or missing data directory, as its first revision: an example,
    or an empty plan of one scenario to fill in with the app, the Assumptions page first. A data
    directory that holds a plan stays as it is."""
    if example and born:
        msg = "--example or --born, not both"
        raise typer.BadParameter(msg)
    if name and not example:
        msg = f"{name} is the name of an example: start it with --example {name}"
        raise typer.BadParameter(msg)
    chosen = datadir.EXAMPLES / name if name else datadir.EXAMPLE
    with _reported():
        datadir.check_empty(data)
        entry = (
            datadir.start_example(data, chosen)
            if example
            else datadir.start_empty(
                data, born or typer.prompt("Date of birth (YYYY-MM-DD)", value_proc=_born)
            )
        )
    plan = f"the example {chosen.name}" if example else "an empty plan"
    then = "" if example else ", the Assumptions page first"
    console.print(
        f"{data}: {plan}{f' as {entry.id}' if entry else ''}. Next: `dagobert app`{then}."
    )


RECONNECT_WAIT = 6.0  # seconds


def _open_unless_reconnected(url: str) -> None:
    """A tab left open by the previous run reconnects by itself and starts a fresh session.

    Only when none does within `RECONNECT_WAIT` a new tab opens. Streamlit backs off its
    reconnect attempts, so a tab that waited for minutes can come too late."""
    from dagobert.ui import session_seen  # noqa: PLC0415 keeps streamlit out of `run`

    if not session_seen.wait(RECONNECT_WAIT):
        webbrowser.open(url)


# Fixed settings of the app. A STREAMLIT_* variable of the deployment overrides each.
STREAMLIT_ENV = {
    "STREAMLIT_SERVER_HEADLESS": "true",  # no email prompt, Streamlit opens no tab itself
    "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    "STREAMLIT_CLIENT_TOOLBAR_MODE": "viewer",  # hides the Deploy button
    # a phone that leaves the tab keeps its session and its unsaved edits for an hour
    "STREAMLIT_SERVER_DISCONNECTED_SESSION_TTL": "3600",
    # the server refuses a larger upload whatever the uploader says: every export fits
    "STREAMLIT_SERVER_MAX_UPLOAD_SIZE": str(transfer.UPLOAD_MB),
    # no `Source file changed` banner over the header and its Save: the package does not change
    "STREAMLIT_SERVER_FILE_WATCHER_TYPE": "none",
    # a rerun waits for the next Streamlit call of the run before: with fast reruns each quick move
    # of a slider started a script thread, and the engine runs of eight piled up past 8 GB
    "STREAMLIT_RUNNER_FAST_RERUNS": "false",
    # a blue accent per scheme (`.streamlit/config.toml` says why)
    "STREAMLIT_THEME_LIGHT_PRIMARY_COLOR": "#1c64d1",
    "STREAMLIT_THEME_DARK_PRIMARY_COLOR": "#4a8ff0",
}


@app.command("app")
def ui(
    *,
    data: DataDir = Path("data"),
    address: Annotated[
        str,
        typer.Option(
            "--address",
            envvar="DAGOBERT_ADDRESS",
            help="Listen address. The app has no login and serves one user: on any other "
            "address than localhost, serve it behind a proxy that authenticates",
        ),
    ] = "localhost",
    port: Annotated[int, typer.Option("--port", envvar="DAGOBERT_PORT")] = 8321,
    browser: Annotated[
        bool,
        typer.Option(
            "--browser/--no-browser",
            envvar="DAGOBERT_BROWSER",
            help="Open a tab when none reconnects",
        ),
    ] = True,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers",
            envvar=WORKERS_ENV,
            min=1,
            help="Processes of the explorer, about 750 MB each at 5000 paths",
            show_default="one per CPU, at most 8",
        ),
    ] = None,
) -> None:
    """Serve the app (overview, editors, explorer) and open it in the browser. An export zip as
    `--data` unpacks into the directory beside it of its name, which the app then serves."""
    from streamlit.web import cli as streamlit_cli  # noqa: PLC0415

    if data.is_file():
        with _reported():
            data = transfer.unpacked(data)
    os.environ[DATA_ENV] = str(data.resolve())
    if workers:
        os.environ[WORKERS_ENV] = str(workers)
    for name, value in STREAMLIT_ENV.items():
        os.environ.setdefault(name, value)
    script = Path(__file__).parent / "ui" / "main.py"
    sys.argv = [
        "streamlit",
        "run",
        str(script),
        f"--server.port={port}",
        f"--server.address={address}",
    ]
    if browser:
        threading.Thread(
            target=_open_unless_reconnected, args=(f"http://localhost:{port}",), daemon=True
        ).start()
    streamlit_cli.main()


@app.command()
def export(
    *,
    data: DataDir = Path("data"),
    with_revisions: Annotated[
        bool, typer.Option("--revisions", help="With the revisions: every save so far")
    ] = False,
    out: Annotated[
        Path, typer.Option("--out", help="The zip, or a directory for dagobert-<revision>.zip")
    ] = Path(),
) -> None:
    """Export the inputs and the records of the data directory as a zip: a backup, or a copy to
    work on (`app --data <zip>`) that `import` brings back. The series and the report stay out."""
    with _reported():
        taken = transfer.export(data)
        path = out / taken.name if out.is_dir() else out
        files.atomic_write(path, taken.zip(history=with_revisions))
    console.print(
        f"{path}: the inputs at revision {taken.at}"
        f"{' with the revisions' if with_revisions else ''}"
    )


@app.command("import")
def import_zip(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="An export zip")],
    *,
    data: DataDir = Path("data"),
    keep: Annotated[
        list[str] | None, typer.Option("--keep", help="Keep this file of the data directory")
    ] = None,
    take: Annotated[
        list[str] | None, typer.Option("--take", help="Take this file of the zip")
    ] = None,
    keep_all: Annotated[
        bool, typer.Option("--keep-all", help="Keep the file here wherever the import asks")
    ] = False,
    take_all: Annotated[
        bool, typer.Option("--take-all", help="Take the file of the zip wherever the import asks")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Import without asking")] = False,
) -> None:
    """Import an export zip as one revision. Each file against the revision that the export was
    taken at: a file changed on one side takes that side. The import asks keep or take for a file
    changed on both sides, for one that it would remove and, with an export of another history,
    for every file that differs: `--keep` and `--take` per file, `--keep-all` or `--take-all` for
    the rest. Into an empty data directory the revisions of the zip move along."""
    if keep_all and take_all:
        msg = "--keep-all or --take-all, not both"
        raise typer.BadParameter(msg)
    rest = transfer.Choice.KEEP if keep_all else transfer.Choice.TAKE if take_all else None
    with _reported():
        preview = transfer.preview(data, file)
        choices = (
            ({c.path: rest for c in preview.undecided} if rest else {})
            | dict.fromkeys(keep or [], transfer.Choice.KEEP)
            | dict.fromkeys(take or [], transfer.Choice.TAKE)
        )
        _show(preview, choices)
        try:
            taken = preview.texts(choices)
        except ValueError as err:
            typer.echo(err, err=True)
            raise typer.Exit(1) from err
        if not taken:
            console.print("Nothing to import: every file here stays.")
            return
        if not yes:
            typer.confirm(f"Import {file.name} into {data}?", abort=True)
        entry = transfer.apply(data, preview, choices)
    console.print(f"{file.name}: imported into {data}{f' as {entry.id}' if entry else ''}")


def _show(preview: transfer.Preview, choices: Mapping[str, transfer.Choice]) -> None:
    """The notes and the files of an import, and the difference of each file that it asks for:
    of both sides against the base, or of the zip against the file here. None for a removal."""
    for note in preview.notes:
        console.print(f"[yellow]{note}[/yellow]")
    since = f"Since {preview.archive.base}" if preview.known else "Against the files here"
    table = Table("File", "Here", "In the zip", "Action", title=since)
    for change in preview.changes:
        choice = choices.get(change.path, change.default)
        action = change.action(choice) if choice else "[red]keep or take?[/red]"
        table.add_row(change.path, change.here, change.there, action)
    console.print(table)
    for c in preview.undecided:
        for side in c.sides:
            if side.new is not None:
                typer.echo(side.unified(c.path))


GUESS = "Default: the guess"
DateColumnOpt = Annotated[str | None, typer.Option("--date", help=f"Column. {GUESS}")]
ValueOpt = Annotated[str | None, typer.Option("--value", help=f"Column of the values. {GUESS}")]
DecimalOpt = Annotated[csvimport.Decimal | None, typer.Option("--decimal", help=GUESS)]
DatesOpt = Annotated[
    csvimport.DateOrder | None, typer.Option("--dates", help=f"Date order. {GUESS}")
]
CurrencyOpt = Annotated[
    str | None, typer.Option("--currency", help=f"Column, '' for none: read as EUR. {GUESS}")
]
FileArg = Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="The download")]


@dataclass(frozen=True)
class Columns:
    """The column options of an import: None takes the guess of `csvimport`."""

    day: str | None  # the column of the dates
    value: str | None
    decimal: csvimport.Decimal | None
    dates: csvimport.DateOrder | None
    currency: str | None

    def read(self, file: Path) -> list[tuple[date, float]]:
        """The dated values of `file`. Prints the mapping and the refused lines, raises
        `RefusedError` when no value reads."""
        table = csvimport.sniff(file.read_bytes())
        guessed = csvimport.guess(table)
        mapping = csvimport.Mapping(
            guessed.date if self.day is None else table.column(self.day),
            guessed.value if self.value is None else table.column(self.value),
            self.decimal or guessed.decimal,
            self.dates or guessed.dates,
            guessed.currency if self.currency is None else _column(table, self.currency),
        )
        console.print(f"Mapping: {mapping.describe(table)}")
        parsed = csvimport.parse(table, mapping, today=date.today())
        for line, reason in parsed.refused:
            console.print(f"[yellow]line {line}: {reason}[/yellow]")
        if not parsed.points:
            msg = "no value read"
            raise RefusedError(msg)
        return parsed.points


prices_app = typer.Typer(no_args_is_help=True, help="EUR prices per security in `<data>/prices/`.")
app.add_typer(prices_app, name="prices")


@prices_app.command("import")
def import_prices(
    security: Annotated[str, typer.Argument(help="An ISIN, or a symbol such as XAU")],
    file: FileArg,
    *,
    data: DataDir = Path("data"),
    date_column: DateColumnOpt = None,
    value: ValueOpt = None,
    decimal: DecimalOpt = None,
    dates: DatesOpt = None,
    currency: CurrencyOpt = None,
    force: Annotated[
        bool, typer.Option(help="Save a price far from the one it replaces or from a trade")
    ] = False,
) -> None:
    """Import a downloaded price history of one security in euros, then record the value of
    every asset whose securities all have a price. A price far from the stored one or from a
    trade nearby stops the import unless `--force`: a decimal mark in the wrong place."""
    with _opened(data):
        try:
            points = Columns(date_column, value, decimal, dates, currency).read(file)
            for slip in (slips := prices.far_off(data, security, points)):
                console.print(f"[yellow]Check: {slip}[/yellow]")
            if slips and not force:
                msg = "a price lies far off: look at --decimal, or save with --force"
                raise RefusedError(msg)
            saved = prices.save(data, security, points, source="prices import")
        except (OSError, RefusedError) as err:
            console.print(f"[red]Not imported: {err}[/red]")
            raise typer.Exit(1) from None
        (first, _), (last, _) = points[0], points[-1]
        console.print(
            f"{security}: {len(points)} prices from {first} to {last}, "
            f"{len(saved.replaced)} replaced"
        )
        _recorded(saved.recorded)


def _recorded(observed: list[history.Observation]) -> None:
    for day, asset, worth in observed:
        console.print(f"{asset}: {format_eur(worth)} as of {day}")


trades_app = typer.Typer(no_args_is_help=True, help="The trades of the assets in `assets.yaml`.")
app.add_typer(trades_app, name="trades")
TradeColumnOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--column",
        help=f"FIELD=HEADER, '' for none, once per field: {', '.join(tradeimport.FIELDS)}. "
        + GUESS,
    ),
]


@trades_app.command("import")
def import_trades(
    asset: Annotated[str, typer.Argument(help="The id of an equity, fixed-income, gold or crypto")],
    file: FileArg,
    *,
    data: DataDir = Path("data"),
    column: TradeColumnOpt = None,
    decimal: DecimalOpt = None,
    dates: DatesOpt = None,
    dry_run: Annotated[bool, typer.Option(help="Show what the import adds, save nothing")] = False,
    force: Annotated[
        bool, typer.Option(help="Save a trade far from a stored price or from its series")
    ] = False,
) -> None:
    """Add the buys and sales of a broker export (CSV) to the trades of an asset, as one revision.
    A row that the trades hold already is left out, one that they cannot take is refused. A price
    per unit far from a stored price stops the import unless `--force`: a decimal mark in the
    wrong place."""
    with _opened(data):
        try:
            trades = store.assets_file(data).child(asset, "trades")
            table = csvimport.sniff(file.read_bytes())
            columns = _trade_columns(table, column or [], decimal, dates)
            console.print(f"Mapping: {columns.describe(table)}")
            held, seen = tradeimport.holding(trades)
            parsed = tradeimport.read(table, columns, today=date.today())
            merged = tradeimport.merge(held, parsed)
            for line, reason in tradeimport.refused(parsed, merged):
                console.print(f"[yellow]line {line}: {reason}[/yellow]")
            for part in filter(None, tradeimport.summary(parsed, merged)):
                console.print(part)
            if not merged.added and not merged.held and tradeimport.refused(parsed, merged):
                msg = "no trade to add"
                raise RefusedError(msg)
            for slip in (slips := tradeimport.slips(data, merged.added)):
                console.print(f"[yellow]Check: {slip}[/yellow]")
            if merged.added and (basis := tradeimport.replaced_basis(held)):
                console.print(f"[yellow]Check: {basis}[/yellow]")
            if dry_run or not merged.added:
                return
            if slips and not force:
                msg = "a price lies far off: look at --decimal, or save with --force"
                raise RefusedError(msg)
            tradeimport.save(trades, held, merged.added, seen, source="trades import")
        # an asset row that the model refuses (`ValidationError`), not an error of the code
        except (OSError, RefusedError, ValidationError, revisions.ConflictError) as err:
            console.print(f"[red]Not imported: {err}[/red]")
            raise typer.Exit(1) from None
        console.print(f"{asset}: added {tradeimport.counted(len(merged.added), 'trade')}")


def _trade_columns(
    table: csvimport.Table,
    named: list[str],
    decimal: csvimport.Decimal | None,
    dates: csvimport.DateOrder | None,
) -> tradeimport.Columns:
    """The guess of `tradeimport`, with the columns `named` as `FIELD=HEADER` (empty: none), the
    decimal mark and the date order of the options. Raises `RefusedError` for a field or a header
    that the table lacks."""
    guessed = tradeimport.guess(table)
    at: dict[str, int | None] = {}
    for text in named:
        field, _sep, header = text.partition("=")
        if field not in tradeimport.FIELDS:
            msg = f"no field {field!r}: take one of {', '.join(tradeimport.FIELDS)}"
            raise RefusedError(msg)
        at[field] = _column(table, header)
    return tradeimport.Columns(guessed.at | at, decimal or guessed.decimal, dates or guessed.dates)


def _column(table: csvimport.Table, header: str) -> int | None:
    """The column of `header` as an option names it, none for an empty one (`''`)."""
    return table.column(header) if header.strip() else None


series_app = typer.Typer(
    no_args_is_help=True,
    help="The external series: shipped, or fetched and imported into `<data>/series/`.",
)
app.add_typer(series_app, name="series")


def _months(points: list[series.Point]) -> str:
    return f"{points[0].month:%Y-%m} to {points[-1].month:%Y-%m}" if points else "none"


@series_app.command("list")
def list_series(*, data: DataDir = Path("data")) -> None:
    """One row per series and the life table: months, provisional months, origin, source note."""
    table = Table("Series", "Months", "Provisional", "Origin", "Source note")
    for s in series.SERIES.values():
        points, file = series.read(s, data), series.fetched_file(data, s.name)
        origin = (
            "shipped" if s.shipped else "",
            f"fetched {date.fromtimestamp(file.stat().st_mtime)}" if file.exists() else "",
        )
        table.add_row(
            s.name,
            _months(points),
            ", ".join(f"{p.month:%Y-%m}" for p in points if p.provisional),
            ", ".join(filter(None, origin)),
            s.attribution,
        )
    life = series.life_table()
    table.add_row("life table", life.period, "", "shipped", life.attribution)
    console.print(table)


def _series(
    names: list[str], action: str, can: Callable[[series.Series], object]
) -> list[series.Series]:
    """The named series, without names every one that `can` take the action. Raises
    BadParameter for one that cannot."""
    able = {n: s for n, s in series.SERIES.items() if can(s)}
    if wrong := [n for n in names if n not in able]:
        msg = f"cannot {action} {', '.join(wrong)}, only {', '.join(able)}"
        raise typer.BadParameter(msg)
    return [able[n] for n in names] if names else list(able.values())


@series_app.command("fetch")
def fetch_series(
    names: Annotated[list[str] | None, typer.Argument(help="Default: every fetchable one")] = None,
    *,
    data: DataDir = Path("data"),
) -> None:
    """Fetch the months that the named series lack, without names every fetchable one, and record
    the market values of gold and Bitcoin that a new month or rate changes. After a refusal no
    further request goes to that source. Nothing else fetches."""
    refused: set[str] = set()  # hosts
    failed = False
    with _opened(data):
        for s in _series(names or [], "fetch", lambda s: s.fetch):
            if (host := urlsplit(s.source).netloc) in refused:
                console.print(
                    f"[red]{s.name}: not fetched: {host} refused the request before[/red]"
                )
                continue
            try:
                fetched = prices.fetch_series(s, data, source="series fetch")
            except series.FetchError as err:
                refused.add(host)
                console.print(f"[red]{s.name}: not fetched: {err}[/red]")
                continue
            except (OSError, ValueError) as err:  # a record of the values that the inputs refuse
                failed = True
                console.print(f"[red]{s.name}: not saved: {err}[/red]")
                continue
            console.print(f"{s.name}: {fetched.update.text}")
            _recorded(fetched.recorded)
        if refused or failed:
            raise typer.Exit(1)


@series_app.command("import")
def import_series(
    name: str,
    file: FileArg,
    *,
    data: DataDir = Path("data"),
    date_column: DateColumnOpt = None,
    value: ValueOpt = None,
    decimal: DecimalOpt = None,
    dates: DatesOpt = None,
    currency: CurrencyOpt = None,
) -> None:
    """Replace the fetched months of an equity series by a downloaded index history, such as an
    MSCI export or the prices of an ETF: the last value of each month, the current one
    provisional. A file of `month,value` rows, such as the `msci_world.csv` of an older data
    directory, reads as it is. Months with a gap are refused. A later fetch that differs in a
    final month replaces the import."""
    [s] = _series([name], "import", lambda s: s.imports)
    with _opened(data):
        try:
            months = series.month_values(file.read_bytes().decode("utf-8", "replace")) or (
                series.month_ends(
                    Columns(date_column, value, decimal, dates, currency).read(file),
                    today=date.today(),
                )
            )
            series.save(s, data, months)
        except ValueError as err:
            console.print(f"[red]Not imported: {err}[/red]")
            raise typer.Exit(1) from None
        console.print(f"{name}: {len(months)} months, {_months(months)}")
