"""Open a data directory: every entry (the app, the commands) brings its inputs to the schema of
this app first. An empty one starts a plan: an example, a quick start or an empty plan."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from dagobert import __version__, files, revisions, schema, sv, tax
from dagobert.model.assumptions import REGELALTERSGRENZE, REQUIRED_CLASSES
from dagobert.model.months import aged
from dagobert.model.plan import Feature
from dagobert.model.taxes import default_tax_year
from dagobert.problems import InputError, Problem

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

EXAMPLES = Path(__file__).parent / "examples"
ExampleName = Literal["engineer", "starter"]  # the directories of `EXAMPLES`
# the example of `dagobert init --example`, whose phases and return classes an empty plan takes
EXAMPLE = EXAMPLES / "engineer"
# the sources of their revisions
FROM_EXAMPLE, EMPTY_PLAN, QUICK_START = "example", "empty plan", "quick start"
SCENARIO = "plan"  # the stem of the scenario of an empty plan
CASH, DEPOT = "girokonto", "depot"  # the ids of the assets of a quick start
# the phases of the example that an empty plan takes: four fit the sheet on an upright phone
NEW_PHASES = ("work", "unemployed", "alt", "retired")
START = "start a plan with `dagobert init --example` or `dagobert init`, or in the app"
OLDEST = date(1900, 1, 1)  # the earliest date of birth that an empty plan takes


def empty(data_dir: Path) -> bool:
    """Whether `data_dir` has no input and no revision, or does not exist: a first run. A file is
    no empty directory."""
    if not data_dir.is_dir():
        return not data_dir.exists()
    return not (any(map(revisions.is_tracked, schema.Tree(data_dir))) or revisions.head(data_dir))


def check_born(born: date) -> None:
    """Raise ValueError for a date of birth after today or before `OLDEST`: a typing error."""
    if not OLDEST <= born <= date.today():
        msg = f"{born} is no date of birth: type one from {OLDEST} to today"
        raise ValueError(msg)


def open(data_dir: Path) -> revisions.Entry | None:
    """Migrate the inputs of `data_dir` to the current schema and write them back with the
    manifest as one revision, after the edits outside the app (`revisions.write`). Migrated
    inputs that do not load change nothing and raise. A read-only directory runs as it is when
    at most the manifest would be new, and raises when it needs a migration. An empty or missing
    directory raises with the way to start a plan. A directory with no manifest and no revisions
    log at all is written by hand in the current format: it gets the manifest and no step. Any
    history means Dagobert touched it, so its texts read as schema 1 and migrate."""
    if not (data_dir / "assumptions.yaml").is_file():
        msg = (
            f"{'no plan yet' if data_dir.is_dir() else 'no such directory'}: {START}"
            if empty(data_dir)
            else "not a data directory: it has no assumptions.yaml"
        )
        raise InputError([Problem(str(data_dir), None, "", msg)])
    tree = schema.Tree(data_dir)
    # written by hand: no manifest and no log at all; any history means Dagobert touched it
    by_hand = schema.MANIFEST not in tree and revisions.head(data_dir) is None
    old = schema.version(tree)

    def migrate(texts: Mapping[str, str]) -> dict[str, str]:
        # under the lock a manifest of another write counts: `by_hand` was looked at before it
        if by_hand and schema.MANIFEST not in texts:
            return {schema.MANIFEST: schema.manifest_text()}
        return schema.migrate(texts)

    migrated = migrate(tree)
    if not os.access(data_dir, os.W_OK):
        if migrated.keys() - {schema.MANIFEST}:
            msg = f"read-only, so the inputs of schema {old} cannot migrate: make it writable"
            raise InputError([Problem(str(data_dir), None, "", msg)])
        return None
    return revisions.write(
        data_dir,
        f"manifest {schema.current()} (Dagobert {__version__})"
        if by_hand
        else f"migrate {old} → {schema.current()} (Dagobert {__version__})",
        lambda: migrate(schema.Tree(data_dir)),
    )


def start_example(data_dir: Path, example: Path = EXAMPLE) -> revisions.Entry | None:
    """Copy the example directory `example` into the empty `data_dir` as its first revision,
    source `example`."""
    return _start(data_dir, FROM_EXAMPLE, schema.Tree(example))


@dataclass(frozen=True)
class Quick:
    """The answers of the quick start of the start page. The date of birth alone gives the empty
    plan; each other answer adds its key or its row, an empty one nothing, nor a zero amount
    (`texts`). Euros of the start, a month's for the salary, the spending and the savings plan."""

    born: date
    sex: Literal["m", "f"] | None = None
    gross: float | None = None  # the salary
    spending: float | None = None
    savings: float | None = None  # the depot today
    cash: float | None = None
    pkv: bool = False
    points: float | None = None  # the Rentenpunkte so far, from the Renteninformation
    since: int | None = None  # the year of the first contribution to the statutory pension
    plan: float | None = None  # the savings plan into the depot


def estimate(gross: float | None, since: int | None, start: date) -> float:
    """The Rentenpunkte so far of a quick start without them: for each year from `since` to the
    year of `start` the points of twelve months of the salary `gross` in the tax year of `start`,
    up to the BBG (`sv.pension_points`); 0 without the salary or the year."""
    if not gross or since is None:
        return 0.0
    return round(
        float(sv.pension_points(gross, tax.for_year(default_tax_year(start))) * 12)
        * max(start.year - since, 0),
        2,
    )


def first_month() -> date:
    """The start of a new plan: the current month."""
    return date.today().replace(day=1)


def starts_retired(born: date) -> bool:
    """A new plan of a person born on `born` starts in its last phase (`retired`): the person
    reaches the Regelaltersgrenze by its start, so a stream of the first phase never pays."""
    return aged(born, REGELALTERSGRENZE) <= first_month()


def _whole(euros: float) -> float:
    """Euros as the files write them, whole ones without a decimal point."""
    return int(euros) if euros.is_integer() else euros


def _assets(quick: Quick) -> Iterator[dict[str, object]]:
    if quick.cash:
        yield {"id": CASH, "name": "Girokonto", "kind": "cash", "value": _whole(quick.cash)}
    if quick.savings or quick.plan:  # a savings plan buys into the depot, a new one at 0
        value = _whole(quick.savings or 0.0)
        yield {"id": DEPOT, "name": "Depot", "kind": "equity", "value": value, "cost_basis": value}


def _streams(quick: Quick, start: date) -> Iterator[dict[str, object]]:
    """The streams of the answers, named in German as `starter` names them. A salary brings the
    pension that pays the points of its months, from the points so far."""
    if quick.gross:
        yield {
            "name": "Gehalt",
            "cat": "Gehalt",
            "kind": "salary",
            "gross": _whole(quick.gross),
            "phases": [NEW_PHASES[0]],
        }
    if quick.gross or quick.points:
        yield {
            "name": "Rente",
            "cat": "Rente",
            "kind": "pension",
            "points": estimate(quick.gross, quick.since, start)
            if quick.points is None
            else quick.points,
            "point_value": tax.for_year(default_tax_year(start)).rentenwert,
            "phases": [NEW_PHASES[-1]],
        }
    if quick.spending:
        yield {"name": "Lebenshaltung", "cat": "Leben", "amount": -_whole(quick.spending)}
    if quick.plan:
        yield {
            "name": "Sparplan",
            "kind": "savings",
            "amount": -_whole(quick.plan),
            "into": DEPOT,
            "phases": [NEW_PHASES[0]],
        }


def texts(quick: Quick) -> dict[str, str]:
    """The files of a new plan from `quick`, with the manifest, so the next `open` writes nothing:
    the person, the current month as the start, the phases (`NEW_PHASES`) and the return classes
    that every plan needs (those of the example), `tax.pkv`, the assets and streams of the
    answers, one scenario `plan` that the app opens with, in the first phase from the start and
    the last at the Regelaltersgrenze (with its id: the change that `goalseek.work` moves; from the
    start for a person who reached it), and every feature off: the plan uses none. A date of birth
    after today or before `OLDEST` raises ValueError (`check_born`)."""
    check_born(quick.born)
    example = files.yaml().load((EXAMPLE / "assumptions.yaml").read_text(encoding="utf-8"))
    start, retired = first_month(), NEW_PHASES[-1]
    since = date(quick.since, 1, 1) if quick.since is not None else None
    person = {"born": quick.born, "sex": quick.sex, "rv_since": since}
    assumptions = {
        "person": {key: value for key, value in person.items() if value is not None},
        "start": start,
        "phases": {k: v for k, v in example["phases"].items() if k in NEW_PHASES},
        "returns": {name: v for name, v in example["returns"].items() if name in REQUIRED_CLASSES},
        "tax": {"pkv": quick.pkv},
    }
    changes = (
        [{"from": start, "phase": retired}]
        if starts_retired(quick.born)
        else [
            {"from": start, "phase": NEW_PHASES[0]},
            {"from": aged(quick.born, REGELALTERSGRENZE), "phase": retired, "id": retired},
        ]
    )
    return {
        schema.MANIFEST: schema.manifest_text(),
        "assumptions.yaml": files.dump(assumptions),
        "assets.yaml": files.dump({"assets": list(_assets(quick))}),
        "cashflows.yaml": files.dump({"streams": list(_streams(quick, start))}),
        "app.yaml": files.dump({"scenarios": [SCENARIO], "features_off": [*map(str, Feature)]}),
        f"scenarios/{SCENARIO}.yaml": files.dump({"name": SCENARIO.title(), "phases": changes}),
    }


def start_quick(data_dir: Path, quick: Quick) -> revisions.Entry | None:
    """Start the plan of the quick start in the empty `data_dir` as its first revision, source
    `quick start` (`texts`)."""
    return _start(data_dir, QUICK_START, texts(quick))


def start_empty(data_dir: Path, born: date) -> revisions.Entry | None:
    """Start an empty plan in the empty `data_dir` as its first revision, source `empty plan`: the
    quick start of the date of birth alone, without asset or stream (`texts`)."""
    return _start(data_dir, EMPTY_PLAN, texts(Quick(born)))


def check_empty(data_dir: Path) -> None:
    """Raise `InputError` unless `data_dir` is an empty directory or none: a start never replaces a
    plan or a file."""
    if data_dir.exists() and not data_dir.is_dir():
        msg = "not a directory: a data directory is a folder"
        raise InputError([Problem(str(data_dir), None, "", msg)])
    if not empty(data_dir):
        msg = "holds a plan already: a start writes only into an empty data directory"
        raise InputError([Problem(str(data_dir), None, "", msg)])


def _start(data_dir: Path, source: str, texts: Mapping[str, str]) -> revisions.Entry | None:
    """Write `texts` into the empty `data_dir`, created when missing, as one revision. The check
    runs again under the lock: a start in another tab may have come first."""
    check_empty(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    def checked() -> dict[str, str]:
        check_empty(data_dir)
        return dict(texts)

    return revisions.write(data_dir, source, checked)
