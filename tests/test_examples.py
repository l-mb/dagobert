"""The examples in `src/dagobert/examples/`: data directories of made-up people, `engineer` with
every feature in English, `starter` a simple plan in German. Each is at the current schema, loads,
and lasts on its mean path. Nothing here writes into them. A first run copies one into an empty data
directory, or starts an empty plan."""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest

from dagobert import (
    actuals,
    datadir,
    goalseek,
    history,
    i18n,
    loader,
    revisions,
    scenariofiles,
    schema,
    tax,
)
from dagobert.model.assets import Asset, Loan
from dagobert.model.events import AddStreamEvent, Event
from dagobert.model.months import aged
from dagobert.model.plan import Feature, Plan
from dagobert.model.streams import StreamKind
from dagobert.problems import InputError
from dagobert.runner import Options
from dagobert.sensitivity import outcome
from dagobert.ui import mode, welcome

DIRS = sorted(p for p in datadir.EXAMPLES.iterdir() if p.is_dir())
SCENARIOS = [path for d in DIRS for path in scenariofiles.concrete_scenarios(d).values()]
STARTER = datadir.EXAMPLES / "starter"


def _tags(union: Any, field: str) -> set[str]:
    """The literal values of `field` over the members of a discriminated union."""
    return {get_args(m.model_fields[field].annotation)[0] for m in get_args(get_args(union)[0])}


def test_every_example_can_start() -> None:
    """The command line and the start page name each example of the package."""
    names = {d.name for d in DIRS}
    assert set(get_args(datadir.ExampleName)) == names == {e.name for e in welcome.EXAMPLES}


@pytest.mark.parametrize("data", DIRS, ids=lambda d: d.name)
def test_example_is_current_and_complete(data: Path) -> None:
    """The full example uses every kind of the model, the simple one what it needs."""
    assert schema.migrate(schema.Tree(data)) == {}  # a migration step migrates the examples too
    loader.check(data)
    assert scenariofiles.default_scenarios(data) == loader.load_app_settings(data).scenarios
    assert len(history.actual_totals(data)) > 1  # the Overview draws the recorded net worth
    assert actuals.read(data)
    plans = [
        loader.load_plan(data, path) for path in scenariofiles.concrete_scenarios(data).values()
    ]
    phases = loader.load_assumptions(data).phases
    assert {c.phase for p in plans for c in p.scenario.phases} == set(phases)  # each used
    assert any(spec.label for spec in phases.values())  # a phase named in words
    if data != datadir.EXAMPLE:
        return
    events = [e for p in plans for e in p.scenario.events]
    added = [e.stream for e in events if isinstance(e, AddStreamEvent)]
    assert {a.kind for a in loader.load_assets(data)} == _tags(Asset, "kind")
    assert {s.kind for s in [*loader.load_streams(data), *added]} == set(StreamKind)
    assert {e.type for e in events} == _tags(Event, "type")


@pytest.mark.parametrize("data", DIRS, ids=lambda d: d.name)
def test_an_example_switches_off_the_features_that_it_does_not_use(data: Path) -> None:
    """The simple example opens as a newcomer's plan would, the full one with every feature."""
    unused = {f for f in Feature if not mode.uses(data).used(f)}
    assert set(loader.load_app_settings(data).features_off) == unused
    assert bool(unused) == (data != datadir.EXAMPLE)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda p: f"{p.parents[1].name}/{p.stem}")
def test_scenario_lasts_on_its_mean_path(scenario: Path, tmp_path: Path) -> None:
    """Also without the spending cut and the increase: the difference of `buy-home` and `plan`,
    the pair of the guide `buy-or-rent.md`, is the purchase alone. VPW sets the flexible spending
    of every month without pay, so it cuts or raises in each."""
    data = scenario.parents[1]
    options = Options(data=data, out=tmp_path, model="fixed", paths=1, seed=42, mortality=False)
    result = options.run_one(scenario)
    assert result is not None
    assert not result.broke.any()
    rule = loader.load_plan(data, scenario).assumptions.spending
    if rule is None or rule.vpw is None:
        assert not (result.reduced.any() or result.raised.any())


def test_the_starter_finds_when_to_stop_working(tmp_path: Path) -> None:
    """`Find when to stop working` of the Overview has a month to find on the scenario that the
    app opens with: its mean path runs out when she stops at the start of the plan and lasts when
    she stops in the month of the file, so the seek ends between them."""
    scenario = scenariofiles.concrete_scenarios(STARTER)[scenariofiles.first_scenario(STARTER)]
    dial = goalseek.work(loader.load_plan(STARTER, scenario))
    opts = Options(data=STARTER, out=tmp_path, model="fixed", paths=1, seed=42, mortality=False)
    assert dial.low < dial.value
    assert [
        outcome(opts, scenario, dial.overrides(v))[-1].p_broke for v in (dial.low, dial.value)
    ] == [1.0, 0.0]


@pytest.mark.parametrize(
    ("files", "empty"),
    [
        ([], True),
        (["lost+found/x", "series/vpi.csv", "notes.txt"], True),  # no input among them
        (["history.csv"], False),
        (["revisions/log.csv"], False),
    ],
)
def test_a_data_directory_without_inputs_and_revisions_is_empty(
    tmp_path: Path, files: list[str], empty: bool
) -> None:
    assert datadir.empty(tmp_path / "missing")
    for name in files:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("time,files,removed,source\n20260101T000000.000000Z,,,x\n")
    assert datadir.empty(tmp_path) == empty


@pytest.mark.parametrize("example", [*DIRS, None], ids=lambda d: d.name if d else "empty plan")
def test_a_first_run_starts_a_plan_as_one_revision(tmp_path: Path, example: Path | None) -> None:
    """An example as it is, or an empty plan that the pages open with: one revision, which the
    next open neither migrates nor records again. A second start changes nothing."""
    data = tmp_path / "missing" / "data"
    if example:
        datadir.start_example(data, example)
    else:
        datadir.start_empty(data, date(1985, 3, 14))
    source = datadir.FROM_EXAMPLE if example else datadir.EMPTY_PLAN
    assert [e.source for e in revisions.entries(data)] == [source]
    assert datadir.open(data) is None
    loader.check(data)
    if example:
        assert dict(schema.Tree(data)) == dict(schema.Tree(example))
    else:
        plan = _first(data)
        assert plan.assumptions.start == date.today().replace(day=1)
        assert (plan.assumptions.person.born, plan.assets, plan.streams) == (
            date(1985, 3, 14),
            [],
            [],
        )
        assert tuple(plan.assumptions.phases) == datadir.NEW_PHASES  # not the example's `new-job`
    with pytest.raises(InputError, match="holds a plan already"):
        datadir.start_example(data)
    assert len(revisions.entries(data)) == 1


BORN = date(1985, 3, 14)
FULL = datadir.Quick(
    BORN, "f", gross=5000, spending=2200, savings=40000, cash=6000, since=2010, plan=500
)


def _first(data: Path) -> Plan:
    """The plan of the scenario that the app opens with."""
    stem = scenariofiles.first_scenario(data)
    return loader.load_plan(data, scenariofiles.concrete_scenarios(data)[stem])


def test_a_quick_start_of_a_date_alone_is_the_empty_plan(tmp_path: Path) -> None:
    """The form of the start page with a date alone writes the empty plan of `dagobert init`, file
    by file: GKV, the change to `retired` at 67, which the work seek moves once a salary pays, and
    every feature off."""
    datadir.start_quick(quick := tmp_path / "quick", datadir.Quick(BORN))
    datadir.start_empty(empty := tmp_path / "empty", BORN)
    assert dict(schema.Tree(quick)) == dict(schema.Tree(empty))
    assert [e.source for e in revisions.entries(quick)] == [datadir.QUICK_START]
    assert loader.load_app_settings(quick).features_off == list(Feature)
    assert not _first(quick).assumptions.tax.pkv


@pytest.mark.parametrize(
    ("born", "retired"),
    [
        (date(1985, 3, 14), date(2052, 4, 1)),
        (date(1985, 3, 1), date(2052, 3, 1)),
        (date(1950, 5, 5), None),
    ],
)
def test_a_new_plan_retires_in_the_month_of_67(
    tmp_path: Path, born: date, retired: date | None
) -> None:
    """A birthday after the first reaches the age in the month after; a person past 67 starts
    retired, which the start page says."""
    datadir.start_empty(tmp_path, born)
    start = datadir.first_month()
    expected = [(start, "work"), (retired, "retired")] if retired else [(start, "retired")]
    assert [(c.at, c.phase) for c in _first(tmp_path).scenario.phases] == expected
    assert datadir.starts_retired(born) == (retired is None)


def test_a_quick_start_with_a_salary_pays_a_pension_and_finds_when_to_stop(tmp_path: Path) -> None:
    """The salary earns the points that the pension pays in `retired`, and `Find when to stop
    working` moves the change to it. The plan uses no feature: switched off, none hides a value."""
    datadir.start_quick(data := tmp_path / "data", FULL)
    scenario = scenariofiles.concrete_scenarios(data)[scenariofiles.first_scenario(data)]
    opts = Options(data=data, out=tmp_path, model="fixed", paths=1, seed=42, mortality=False)
    result = opts.run_one(scenario)
    assert result is not None
    assert (result.phases[0], result.phases[-1]) == ("work", "retired")
    assert result.income[0, 0] > 0 and result.income[0, -1] > 0  # the salary, the pension
    dial = goalseek.work(_first(data))
    assert dial.low < dial.value
    assert not [f for f in Feature if mode.uses(data).used(f)]


@pytest.mark.parametrize("gross", [3000, 20000])  # below and above the BBG
def test_the_points_estimate_takes_a_year_of_the_salary_per_year(gross: float) -> None:
    """Points of the salary up to the BBG over the Durchschnittsentgelt (§70 Abs. 1 SGB VI,
    Anlage 2b); typed points win."""
    ty, start = tax.for_year(2026), date(2026, 10, 1)
    year = 12 * min(gross, ty.sv_bbg_month) / ty.durchschnittsentgelt
    assert datadir.estimate(gross, 2016, start) == pytest.approx(10 * year, abs=0.005)
    assert datadir.estimate(gross, None, start) == datadir.estimate(None, 2016, start) == 0


def test_typed_pension_points_win_over_the_estimate(tmp_path: Path) -> None:
    datadir.start_quick(tmp_path, dataclasses.replace(FULL, points=10))
    pension = [s for s in _first(tmp_path).streams if s.kind is StreamKind.PENSION]
    rentenwert = tax.for_year(_first(tmp_path).assumptions.tax_year).rentenwert
    assert [(s.points, s.point_value) for s in pension] == [(10, rentenwert)]


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_a_new_plan_names_its_data_in_the_language_of_the_session(
    tmp_path: Path, lang: i18n.Language
) -> None:
    """Phase labels, assets, streams and categories in `lang`, ids ASCII; an empty plan too."""
    names = datadir.NAMES[lang]
    datadir.start_quick(data := tmp_path / "quick", dataclasses.replace(FULL, lang=lang))
    datadir.start_empty(empty := tmp_path / "empty", BORN, lang)
    for plan in (_first(data), _first(empty)):
        assert dict(plan.assumptions.phase_labels) == dict(names.phases)
    plan = _first(data)
    assert [(a.id, a.name) for a in plan.assets] == [names.cash, names.depot]
    assert [(s.name, s.cat) for s in plan.streams if s.kind is not StreamKind.SAVINGS] == [
        names.salary,
        names.pension,
        names.living,
    ]
    assert [s.name for s in plan.streams if s.kind is StreamKind.SAVINGS] == [names.savings]
    assert all(a.id.isascii() for a in plan.assets)


GOALS = dataclasses.replace(
    FULL, stop=55, lost=date.today().replace(day=1) + timedelta(days=400), home=300000, owed=150000
)


def test_the_goals_of_a_quick_start_go_into_its_one_revision(tmp_path: Path) -> None:
    """The age to stop moves the change to `retired`, which the work seek moves; a job loss is a
    scenario of its own that extends the plan (`scenariofiles.lost_job`), second in `app.yaml`; a
    property brings its loan. Each turns its feature on, all in the one revision of the start."""
    datadir.start_quick(data := tmp_path / "data", GOALS)
    assert [e.source for e in revisions.entries(data)] == [datadir.QUICK_START]
    loader.check(data)
    plan = _first(data)
    assert plan.scenario.phases[-1].at == aged(BORN, 55)
    dial = goalseek.work(plan)
    assert dial.month(dial.value) == (aged(BORN, 55), 55)
    stem = datadir.NAMES["en"].job_loss[0]
    assert loader.load_app_settings(data).scenarios == [datadir.SCENARIO, stem]
    lost = loader.load_plan(data, data / scenariofiles.scenario_file(stem))
    assert lost.scenario.phase_of(GOALS.lost.replace(day=1)) == "unemployed"  # type: ignore[union-attr]
    assert [s.kind for s in lost.streams if s.kind is StreamKind.ALG1] == [StreamKind.ALG1]
    loan = next(a for a in plan.assets if isinstance(a, Loan))
    assert (loan.balance, loan.annuity) == (-150000, datadir.payment(150000))
    off = set(loader.load_app_settings(data).features_off)
    assert {Feature.PROPERTY, Feature.JOB_LOSS}.isdisjoint(off)
    assert {f for f in Feature if mode.uses(data).used(f)} == {Feature.PROPERTY, Feature.JOB_LOSS}
    opts = Options(data=data, out=tmp_path, model="fixed", paths=1, seed=42, mortality=False)
    runs = [opts.run_one(data / scenariofiles.scenario_file(s)) for s in (datadir.SCENARIO, stem)]
    assert runs[1].total[0, -1] < runs[0].total[0, -1]  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("goals", "field"),
    [
        ({"stop": 30}, "stop"),  # past
        ({"lost": date(2020, 1, 1)}, "lost"),  # before the start
        ({"stop": 50, "lost": date(2040, 1, 1)}, "lost"),  # after the stop
        ({"gross": None, "lost": date(2030, 1, 1)}, "lost"),  # nothing to lose
        ({"home": None, "owed": 1000}, "owed"),
    ],
)
def test_a_goal_that_does_not_fit_is_refused(
    tmp_path: Path, goals: dict[str, Any], field: str
) -> None:
    quick = dataclasses.replace(FULL, **goals)
    assert list(datadir.misfits(quick)) == [field]
    with pytest.raises(ValueError, match=field):
        datadir.start_quick(tmp_path, quick)
    assert datadir.empty(tmp_path)


def test_the_budget_check_takes_the_net_of_the_salary() -> None:
    """The example of issue #20: 5,500 € gross leave less than 3,000 € of spending and 1,000 € of
    savings plan; a lower plan fits. More salary, more net; a PKV member pays no KV from it."""
    quick = datadir.Quick(BORN, gross=5500, spending=3000, plan=1000)
    assert quick.short > 0
    assert dataclasses.replace(quick, plan=300).short == 0
    assert quick.net < dataclasses.replace(quick, gross=6000).net < 6000
    assert dataclasses.replace(quick, pkv=True).net > quick.net
    owner = dataclasses.replace(quick, plan=300, home=300000, owed=150000)
    assert owner.out == 3300 + datadir.payment(150000) and owner.short > 0
    assert datadir.Quick(BORN, spending=3000).short == 0  # no salary and no plan: nothing to pay


def test_a_start_checks_again_under_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two starts at once (two tabs): the second passes the first check before the first writes,
    then finds its plan under the lock."""
    data = tmp_path / "data"
    datadir.start_empty(data, date(1985, 3, 14))
    check, seen = datadir.check_empty, list[Path]()
    monkeypatch.setattr(datadir, "check_empty", lambda d: seen.append(d) if not seen else check(d))
    with pytest.raises(InputError, match="holds a plan already"):
        datadir.start_example(data)
    assert len(revisions.entries(data)) == 1


@pytest.mark.parametrize("born", [date(1899, 12, 31), date.today() + timedelta(days=1)])
def test_an_empty_plan_refuses_an_implausible_date_of_birth(tmp_path: Path, born: date) -> None:
    with pytest.raises(ValueError, match="is no date of birth"):
        datadir.start_empty(tmp_path, born)
    assert datadir.empty(tmp_path)


def test_a_start_refuses_a_file(tmp_path: Path) -> None:
    (file := tmp_path / "data").write_text("")
    assert not datadir.empty(file)
    with pytest.raises(InputError, match="not a directory"):
        datadir.start_example(file)
    with pytest.raises(InputError, match="not a data directory"):
        datadir.open(file)


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("20.05.1986", "Born 20 May 1986, age 40."),  # a German user types day first
        ("1986-05-20", "Born 20 May 1986, age 40."),
        ("21.10.1986", "Born 21 October 1986, age 39."),  # the birthday is still to come
    ],
)
def test_the_start_page_reads_a_date_of_birth_and_says_it_back(text: str, said: str) -> None:
    born = welcome.birth(text)
    assert welcome.said(born, date(2026, 10, 13)) == said


@pytest.mark.parametrize(
    ("text", "problem"),
    [("20051986", "type it as"), ("1899-12-31", "is no date of birth"), ("32.01.1986", "type")],
)
def test_the_start_page_refuses_a_date_of_birth_with_what_to_type(text: str, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        welcome.birth(text)
