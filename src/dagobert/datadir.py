"""Open a data directory: every entry (the app, the commands) brings its inputs to the schema of
this app first. An empty one starts a plan: an example, a quick start or an empty plan."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Literal

from dagobert import __version__, files, i18n, revisions, scenariofiles, schema, sv, tax
from dagobert.i18n import N_, _
from dagobert.loader import APP
from dagobert.model.assumptions import REGELALTERSGRENZE, REQUIRED_CLASSES, Assumptions, Person
from dagobert.model.months import aged, months_of_age
from dagobert.model.plan import Feature
from dagobert.model.taxes import TaxOptions, default_tax_year
from dagobert.problems import InputError, Problem
from dagobert.store import Edit

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

EXAMPLES = Path(__file__).parent / "examples"
ExampleName = Literal["engineer", "starter"]  # the directories of `EXAMPLES`
# the example of `dagobert init --example`, whose return classes an empty plan takes
EXAMPLE = EXAMPLES / "engineer"
# the sources of their revisions
FROM_EXAMPLE, EMPTY_PLAN, QUICK_START = "example", "empty plan", "quick start"
SCENARIO = "plan"  # the stem of the scenario of an empty plan
# the phases of a new plan, those of `engineer`: four fit the sheet on an upright phone
NEW_PHASES = ("work", "unemployed", "alt", "retired")
START = "start a plan with `dagobert init --example` or `dagobert init`, or in the app"
OLDEST = date(1900, 1, 1)  # the earliest date of birth that an empty plan takes
# the loan of an own property of a quick start: the refinance rate of the model, and a first
# yearly repayment of 2%, a common one; the Assets page takes the real ones
LOAN_RATE: float = Assumptions.model_fields["refinance_rate"].default
REPAYMENT = 0.02


@dataclass(frozen=True)
class Names:
    """The names that a new plan writes, in one language: data of the user, never through `_()`
    (rule `i18n`). An id and a stem are ASCII."""

    phases: Mapping[str, str]  # the label of each of `NEW_PHASES`
    cash: tuple[str, str]  # the id and the name of an asset
    depot: tuple[str, str]
    home: tuple[str, str]
    loan: tuple[str, str]
    salary: tuple[str, str]  # the name and the category of a stream
    pension: tuple[str, str]
    living: tuple[str, str]
    savings: str  # the name of the savings plan
    job_loss: tuple[str, str]  # the stem and the name of the scenario of a job loss, by `{age}`


NAMES: dict[i18n.Language, Names] = {
    "en": Names(
        {"work": "Work", "unemployed": "Unemployed", "alt": "Career break", "retired": "Retired"},
        ("cash", "Current account"),
        ("depot", "Depot"),
        ("home", "Home"),
        ("home-loan", "Home loan"),
        ("Salary", "salary"),
        ("Pension", "pension"),
        ("Living costs", "living"),
        "Savings plan",
        ("job-loss", "Job loss at {age}"),
    ),
    "de": Names(
        {"work": "Arbeit", "unemployed": "Arbeitslos", "alt": "Auszeit", "retired": "Ruhestand"},
        ("girokonto", "Girokonto"),
        ("depot", "Depot"),
        ("wohnung", "Wohnung"),
        ("darlehen", "Darlehen"),
        ("Gehalt", "Gehalt"),
        ("Rente", "Rente"),
        ("Lebenshaltung", "Leben"),
        "Sparplan",
        ("jobverlust", "Jobverlust mit {age}"),
    ),
}


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
    history means Dagobert touched it, so its texts read as schema 1 and migrate. A newer schema
    or a broken manifest raises before any write."""
    if not (data_dir / "assumptions.yaml").is_file():
        msg = (
            f"{'no plan yet' if data_dir.is_dir() else 'no such directory'}: {START}"
            if empty(data_dir)
            else "not a data directory: it has no assumptions.yaml"
        )
        raise InputError([Problem(str(data_dir), None, "", msg)])
    tree = schema.Tree(data_dir)
    old = schema.version(tree)  # an older app records nothing in the folder of a newer one
    # written by hand: no manifest and no log at all; any history means Dagobert touched it
    by_hand = schema.MANIFEST not in tree and revisions.head(data_dir) is None

    def fresh(texts: Mapping[str, str]) -> bool:
        # under the lock a manifest of another write counts: `by_hand` was looked at before it
        return by_hand and schema.MANIFEST not in texts

    def migrate(texts: Mapping[str, str]) -> dict[str, str]:
        return {schema.MANIFEST: schema.manifest_text()} if fresh(texts) else schema.migrate(texts)

    def source() -> str:
        # under the lock after `migrate`, which read the same files
        texts = schema.Tree(data_dir)
        if fresh(texts):
            return f"manifest {schema.current()} (Dagobert {__version__})"
        return f"migrate {schema.version(texts)} → {schema.current()} (Dagobert {__version__})"

    if not os.access(data_dir, os.W_OK):
        if migrate(tree).keys() - {schema.MANIFEST}:
            msg = f"read-only, so the inputs of schema {old} cannot migrate: make it writable"
            raise InputError([Problem(str(data_dir), None, "", msg)])
        return None
    return revisions.write(data_dir, source, lambda: migrate(schema.Tree(data_dir)))


def start_example(data_dir: Path, example: Path = EXAMPLE) -> revisions.Entry | None:
    """Copy the example directory `example` into the empty `data_dir` as its first revision,
    source `example`."""
    return _start(data_dir, FROM_EXAMPLE, schema.Tree(example))


@dataclass(frozen=True)
class Quick:
    """The answers of the quick start of the start page. The date of birth alone gives the empty
    plan; each other answer adds its key or its row, an empty one nothing, nor a zero amount
    (`texts`). Euros of the start, a month's for the salary, the spending and the savings plan.
    The goals: the age to stop working, the month of a job loss, an own property with the balance
    of its loan. The names are those of `lang`."""

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
    stop: int | None = None  # the age to stop working, else the Regelaltersgrenze
    lost: date | None = None  # the month of a job loss: a scenario of its own
    home: float | None = None  # the value of an own property
    owed: float | None = None  # the balance of its loan
    lang: i18n.Language = "en"

    @property
    def stops(self) -> date:
        """The month of the change to `retired`: at `stop`, else at the Regelaltersgrenze."""
        return aged(self.born, self.stop or REGELALTERSGRENZE)

    @property
    def payment(self) -> float:
        """The monthly payment of the loan of an own property (`payment`), else 0."""
        return payment(self.owed) if self.home and self.owed else 0.0

    @property
    def net(self) -> float:
        """A rough net of the salary a month: less the SV and the Lohnsteuer of the start month
        (Steuerklasse I, no church, a PKV premium apart: the form does not ask for it); 0
        without one."""
        if not self.gross:
            return 0.0
        month, opts = first_month(), TaxOptions(pkv=self.pkv)
        ty = tax.for_year(default_tax_year(month))
        paid = sv.sv_employee(self.gross, opts, Person(born=self.born), month, ty)
        withheld = tax.withholding_with_bonus(
            self.gross, 0.0, (paid, paid), 0.0, ty, church=tax.church_rate(opts, ty)
        )
        return float(self.gross - paid.total - withheld)

    @property
    def out(self) -> float:
        """What goes out each month while the plan works: the spending, the savings plan and the
        payment of the loan."""
        return (self.spending or 0.0) + (self.plan or 0.0) + self.payment

    @property
    def short(self) -> float:
        """By how much the rough `net` misses `out` while the plan works, with a salary or a
        savings plan: 0 when it covers it, also for a plan that starts retired."""
        if starts_retired(self.born) or not (self.gross or self.plan):
            return 0.0
        return max(self.out - self.net, 0.0)


def payment(owed: float) -> float:
    """The monthly payment of a loan of `owed` euros: `LOAN_RATE` and `REPAYMENT` a year."""
    return round(owed * (LOAN_RATE + REPAYMENT) / 12, 2)


def youngest(born: date) -> int:
    """The youngest age to stop working that a new plan takes: the first whose month lies after
    its start."""
    return months_of_age(born, first_month()) // 12 + 1


def unused(quick: Quick) -> list[Feature]:
    """The features that a new plan switches off: all but property with an own property and job
    loss with a job loss."""
    used = {Feature.PROPERTY: bool(quick.home), Feature.JOB_LOSS: quick.lost is not None}
    return [f for f in Feature if not used.get(f)]


# why a goal does not fit the other answers, by the key of its field (`misfits`): words of the
# start page, the CLI says them in English
STOP_EARLY = N_("type an age ahead of you, {age} or more")
LOSS_EARLY = N_("type a month from {month} on")
LOSS_LATE = N_("type a month before you stop working in {month}")
LOSS_UNPAID = N_("a job loss needs a salary: type it above")
OWED_ALONE = N_("type the value of the property first")


def misfits(quick: Quick) -> dict[str, str]:
    """Why a goal of `quick` does not fit the other answers, by the key of its field, in the
    language of the session: an age to stop working at or before the start, a job loss before
    the start, at or after the stop or without a salary, a loan without its property."""
    found: dict[str, str] = {}
    start = first_month()
    if quick.stop is not None and quick.stops <= start:
        found["stop"] = _(STOP_EARLY).format(age=youngest(quick.born))
    if quick.lost is not None and quick.lost < start:
        found["lost"] = _(LOSS_EARLY).format(month=f"{start:%Y-%m}")
    elif quick.lost is not None and quick.lost >= quick.stops:
        found["lost"] = _(LOSS_LATE).format(month=f"{quick.stops:%Y-%m}")
    elif quick.lost is not None and not quick.gross:
        found["lost"] = _(LOSS_UNPAID)
    if quick.owed and not quick.home:
        found["owed"] = _(OWED_ALONE)
    return found


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


def _assets(quick: Quick, names: Names) -> Iterator[dict[str, object]]:
    """The assets of the answers: an own property at its value as 1 m² (as a purchase of a
    scenario), its loan dated today, at `LOAN_RATE` and `Quick.payment`."""
    if quick.cash:
        cash, name = names.cash
        yield {"id": cash, "name": name, "kind": "cash", "value": _whole(quick.cash)}
    if quick.savings or quick.plan:  # a savings plan buys into the depot, a new one at 0
        value = _whole(quick.savings or 0.0)
        depot, name = names.depot
        yield {"id": depot, "name": name, "kind": "equity", "value": value, "cost_basis": value}
    if quick.home:
        home, name = names.home
        yield {
            "id": home,
            "name": name,
            "kind": "property",
            "sqm": 1,
            "per_sqm": _whole(quick.home),
        }
        if quick.owed:
            loan, name = names.loan
            yield {
                "id": loan,
                "name": name,
                "kind": "loan",
                "balance": -_whole(quick.owed),
                "rate": LOAN_RATE,
                "annuity": _whole(quick.payment),
                "asof": date.today(),
                "finances": home,
            }


def _streams(quick: Quick, names: Names, start: date) -> Iterator[dict[str, object]]:
    """The streams of the answers. A salary brings the pension that pays the points of its
    months, from the points so far."""
    if quick.gross:
        yield {
            "name": names.salary[0],
            "cat": names.salary[1],
            "kind": "salary",
            "gross": _whole(quick.gross),
            "phases": [NEW_PHASES[0]],
        }
    if quick.gross or quick.points:
        yield {
            "name": names.pension[0],
            "cat": names.pension[1],
            "kind": "pension",
            "points": estimate(quick.gross, quick.since, start)
            if quick.points is None
            else quick.points,
            "point_value": tax.for_year(default_tax_year(start)).rentenwert,
            "phases": [NEW_PHASES[-1]],
        }
    if quick.spending:
        name, cat = names.living
        yield {"name": name, "cat": cat, "amount": -_whole(quick.spending)}
    if quick.plan:
        yield {
            "name": names.savings,
            "kind": "savings",
            "amount": -_whole(quick.plan),
            "into": names.depot[0],
            "phases": [NEW_PHASES[0]],
        }


def texts(quick: Quick) -> dict[str, str]:
    """The files of a new plan from `quick`, with the manifest, so the next `open` writes nothing:
    the person, the current month as the start, the phases (`NEW_PHASES`) and the return classes
    that every plan needs (those of the example), `tax.pkv`, the assets and streams of the
    answers, one scenario `plan` that the app opens with, in the first phase from the start and
    the last from `Quick.stops` (with its id: the change that `goalseek.work` moves; from the
    start for a person who reached the Regelaltersgrenze), and every feature off that the plan
    does not use: `property` with a property, `job_loss` with a job loss (`_lost`). The names of
    `quick.lang` (`NAMES`). A date of birth after today or before `OLDEST` raises ValueError
    (`check_born`), so does a goal that the plan cannot take (`misfits`)."""
    check_born(quick.born)
    if problems := misfits(quick):
        raise ValueError("; ".join(f"{key}: {why}" for key, why in problems.items()))
    names = NAMES[quick.lang]
    example = files.yaml().load((EXAMPLE / "assumptions.yaml").read_text(encoding="utf-8"))
    start, retired = first_month(), NEW_PHASES[-1]
    since = date(quick.since, 1, 1) if quick.since is not None else None
    person = {"born": quick.born, "sex": quick.sex, "rv_since": since}
    assumptions = {
        "person": {key: value for key, value in person.items() if value is not None},
        "start": start,
        "phases": {phase: {"label": names.phases[phase]} for phase in NEW_PHASES},
        "returns": {name: v for name, v in example["returns"].items() if name in REQUIRED_CLASSES},
        "tax": {"pkv": quick.pkv},
    }
    changes = (
        [{"from": start, "phase": retired}]
        if starts_retired(quick.born)
        else [
            {"from": start, "phase": NEW_PHASES[0]},
            {"from": quick.stops, "phase": retired, "id": retired},
        ]
    )
    off = [str(f) for f in unused(quick)]
    plan = {
        schema.MANIFEST: schema.manifest_text(),
        "assumptions.yaml": files.dump(assumptions),
        "assets.yaml": files.dump({"assets": list(_assets(quick, names))}),
        "cashflows.yaml": files.dump({"streams": list(_streams(quick, names, start))}),
        APP: files.dump({"scenarios": [SCENARIO], "features_off": off}),
        f"scenarios/{SCENARIO}.yaml": files.dump({"name": SCENARIO.title(), "phases": changes}),
    }
    return plan if quick.lost is None else _lost(plan, quick.born, quick.lost, names)


def _lost(plan: Mapping[str, str], born: date, lost: date, names: Names) -> dict[str, str]:
    """The files `plan` with a job loss in `lost` as a scenario of its own that extends the plan,
    without a new job (`scenariofiles.lost_job`, on a copy of the files), and second in
    `app.yaml`: the Explorer compares it."""
    stem, name = names.job_loss
    loss = scenariofiles.JobLoss(
        SCENARIO,
        lost,
        None,
        name.format(age=months_of_age(born, lost) // 12),
        stem,
        names.phases[scenariofiles.IDLE],
    )
    with TemporaryDirectory() as copy:
        for file, text in plan.items():
            (Path(copy) / file).parent.mkdir(parents=True, exist_ok=True)
            (Path(copy) / file).write_text(text, encoding="utf-8")
        edits = scenariofiles.lost_job(Path(copy), loss)
    out = dict(plan)
    for edit in [*edits, Edit(APP, {("scenarios",): [SCENARIO, stem]})]:
        out[edit.name] = edit.onto(out.get(edit.name)) or ""
    return out


def start_quick(data_dir: Path, quick: Quick) -> revisions.Entry | None:
    """Start the plan of the quick start in the empty `data_dir` as its first revision, source
    `quick start` (`texts`)."""
    return _start(data_dir, QUICK_START, texts(quick))


def start_empty(data_dir: Path, born: date, lang: i18n.Language = "en") -> revisions.Entry | None:
    """Start an empty plan in the empty `data_dir` as its first revision, source `empty plan`: the
    quick start of the date of birth alone, without asset or stream (`texts`), its names in
    `lang`."""
    return _start(data_dir, EMPTY_PLAN, texts(Quick(born, lang=lang)))


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
