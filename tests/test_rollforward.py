"""Roll forward: what blocks it, the consumer price factor and the amounts it re-bases."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
import yaml
from builders import fixed_run
from ruamel.yaml import YAML

from dagobert import revisions, rollforward, series
from dagobert.engine.simulation import before
from dagobert.loader import load_assumptions, load_plan, load_streams
from dagobert.result import TAX
from dagobert.series import MonthlySeries

# 100 in 2026-01, one point more each month until 2026-06
SERIES = MonthlySeries([date(2026, m, 1) for m in range(1, 7)], np.arange(100.0, 106.0))


def _fetched(data: Path, prices: MonthlySeries = SERIES) -> None:
    """Consumer prices fetched into the data directory: they replace the shipped months."""
    path = series.fetched_file(data, "vpi")
    path.parent.mkdir(exist_ok=True)
    rows = (f"{m:%Y-%m},{v},\n" for m, v in zip(prices.months, prices.values, strict=True))
    path.write_text("month,value,provisional\n" + "".join(rows))


def _scenario(data: Path, name: str, text: str) -> None:
    (data / "scenarios" / f"{name}.yaml").write_text(text)


def test_passed_items_per_file(data: Path) -> None:
    _scenario(
        data,
        "base",
        "name: base\n"
        "phases: [{from: 2026-01-01, phase: work}, {from: 2026-04-01, phase: retired}]\n"
        "events:\n"
        "  - {at: 2026-03-01, id: gift, type: lump_sum, amount: 100, note: Gift}\n"
        "  - {at: 2026-02-01, type: end_streams, names: [Miete]}\n",  # applies in the first month
    )
    _scenario(data, "later", "name: later\nextends: base\noverrides: {shift: {gift: 5}}\n")
    _scenario(data, "without", "name: without\nextends: base\ndrop: [gift]\n")
    _scenario(
        data,
        "tpl",
        "name: tpl\nextends: base\nabstract: true\n"
        "events: [{at: 2026-02-01, type: lump_sum, amount: 5}]\n",
    )
    _scenario(data, "leaf", "name: leaf\nextends: tpl\n")
    events, phases = rollforward.passed(data, date(2026, 5, 1))
    assert events == [
        rollforward.Passed(
            "scenarios/tpl.yaml", date(2026, 2, 1), "lump_sum", "lump_sum", ("leaf",)
        ),
        rollforward.Passed(
            "scenarios/base.yaml",
            date(2026, 3, 1),
            "lump_sum Gift (id gift)",
            "lump_sum",
            ("base", "leaf"),
        ),
    ]
    assert phases == [
        rollforward.Passed(
            "scenarios/base.yaml",
            date(2026, 1, 1),
            "phase work to 2026-03",
            None,
            ("base", "later", "leaf", "without"),
        )
    ]
    assert rollforward.passed(data, date(2026, 2, 1)) == ([], [])


def test_a_purchase_before_the_new_start_refuses_the_roll(data: Path) -> None:
    """Only the user knows what became of it: the property and its loan go into the assets."""
    _scenario(
        data,
        "base",
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
        "events: [{at: 2026-03-01, type: buy_property, price: 1, transfer_tax: 0,\n"
        "          property: {id: home}}]\n",
    )
    events, _ = rollforward.passed(data, date(2026, 5, 1))
    assert [e.kind for e in events] == ["buy_property"]


def test_a_forced_onset_before_the_new_start_refuses_the_roll(data: Path) -> None:
    """A plan cannot start disabled: the file that sets the nearest `disability.at` names it."""
    with (data / "assumptions.yaml").open("a") as f:
        f.write("disability: {at: 2026-03-01}\n")
    _scenario(
        data, "later", "name: later\nextends: base\noverrides: {disability: {at: 2027-01-01}}\n"
    )
    events, _ = rollforward.passed(data, date(2026, 5, 1))
    assert events == [
        rollforward.Passed(
            "assumptions.yaml", date(2026, 3, 1), "disability at", "disability", ("base",)
        )
    ]
    assert rollforward.passed(data, date(2026, 3, 1)) == ([], [])


def test_rebase_scales_the_premium_of_a_bu_policy_that_follows_the_prices(data: Path) -> None:
    """A BU is nominal by default (a guaranteed benefit): only one with `index: cpi` changes."""
    (data / "cashflows.yaml").write_text(
        "streams:\n"
        "  - {name: BU, kind: bu, amount: 2000, premium: -100}\n"
        "  - {name: BU dynamisch, kind: bu, amount: 1000, premium: -50, index: cpi}\n"
    )
    changes = rollforward.rebase(data, 1.1)
    assert {(c.item, c.new) for c in changes} == {
        ("BU dynamisch amount", 1100),
        ("BU dynamisch premium", -55),
    }


@pytest.mark.parametrize(
    ("old", "new", "factor", "estimated"),
    [
        (date(2026, 1, 1), date(2026, 4, 1), 1.03, 0),
        (date(2026, 4, 1), date(2026, 9, 1), 105 / 103 * 1.12**0.25, 3),
        (date(2026, 7, 1), date(2026, 10, 1), 1.12**0.25, 3),
    ],
)
def test_cpi_change_continues_the_series_at_the_mean(
    old: date, new: date, factor: float, estimated: int
) -> None:
    change = rollforward.cpi_change(old, new, 0.12, SERIES)
    assert change.factor == pytest.approx(factor)
    assert (change.last, change.estimated) == (date(2026, 6, 1), estimated)


def test_check_takes_the_consumer_prices_of_the_data_directory(data: Path) -> None:
    """The shipped series, then a fetched month in its place."""
    new = date(2026, 5, 1)
    prices = series.cpi(data)
    shipped = dict(zip(prices.months, prices.values, strict=True))
    factor = rollforward.check(data, new).cpi.factor
    assert factor == pytest.approx(shipped[new] / shipped[date(2026, 1, 1)])
    _fetched(data, MonthlySeries([new], np.array([2 * shipped[new]])))
    assert rollforward.check(data, new).cpi.factor == pytest.approx(2 * factor)


STREAMS = """\
streams:
  # rent
  - name: Miete
    cat: wohnen
    amount: -500
  - name: Gehalt
    kind: salary
    gross: 4000
  - name: Kredit VL
    kind: other_income
    amount: 40
    index: null
  - name: PKV
    cat: health
    amount: -300
    index: insurance
  - name: Rente
    kind: pension
    gross: 1500
    phases: [retired]
  - name: Rente aus Punkten
    kind: pension
    points: 30
    point_value: 40
    phases: [retired]
  # a savings plan runs nominal unless it names an index
  - name: ETF
    kind: savings
    amount: -500
  - name: ETF real
    kind: savings
    amount: -100
    index: cpi
"""
EVENTS = """\
name: base
phases: [{from: 2026-01-01, phase: work}]
events:
  - {at: 2027-01-01, type: set_stream, name: Miete, amount: -600}
  - {at: 2027-01-01, type: set_stream, name: PKV, amount: -350}
  - {at: 2027-01-01, type: set_stream, name: ETF, amount: -700}
  - {at: 2027-01-01, type: add_stream, stream: {name: Job, kind: salary, gross: 3000}}
  - {at: 2027-01-01, type: add_stream, stream: {name: Fix, amount: -9, index: null}}
  - {at: 2027-02-01, type: lump_sum, amount: 1000}
  - {type: sell, asset: flat, when: {liquid_below: 50000}}
overrides: {care: {cost: 2000}, spending: {reference: 80000}, tax: {werbungskosten: 1000}}
"""
VPW = "overrides: {spending: {trigger: 0, vpw: {floor: 900}}}\n"


def test_rebase_changes_what_follows_the_consumer_prices(data: Path) -> None:
    """Also the reference wealth and the VPW floor of the spending rule and the Werbungskosten,
    where a file sets them; a scenario without the floor gets none."""
    (data / "cashflows.yaml").write_text(STREAMS)
    with (data / "assumptions.yaml").open("a") as f:
        f.write("spending: {cut: 0.25, trigger: 0.5, reference: 100000}\n")
        f.write("tax: {werbungskosten: 2000}\n")
    _scenario(data, "base", EVENTS)
    _scenario(data, "other", "name: other\nextends: base\noverrides: {spending: {cut: 0.1}}\n")
    _scenario(data, "vpw", "name: vpw\nphases: [{from: 2026-01-01, phase: work}]\n" + VPW)
    changes = rollforward.rebase(data, 1.1)
    assert {(c.file, c.item): c.new for c in changes} == {
        ("cashflows.yaml", "Miete amount"): -550,
        ("cashflows.yaml", "Gehalt gross"): 4400,
        ("cashflows.yaml", "ETF real amount"): -110,
        ("cashflows.yaml", "Rente gross"): 1650,
        ("cashflows.yaml", "Rente aus Punkten point_value"): 44,
        ("scenarios/base.yaml", "Miete amount"): -660,
        ("scenarios/base.yaml", "Job gross"): 3300,
        ("scenarios/base.yaml", "sell flat liquid_below"): 55000,
        ("scenarios/base.yaml", "care cost"): 2200,
        ("assumptions.yaml", "spending reference"): 110_000,
        ("scenarios/base.yaml", "spending reference"): 88_000,
        ("assumptions.yaml", "werbungskosten"): 2200,
        ("scenarios/base.yaml", "werbungskosten"): 1100,
        ("scenarios/vpw.yaml", "spending vpw floor"): 990,
    }
    assert rollforward.rebase(data, 1.0) == []


@pytest.mark.parametrize(
    ("events", "child", "match"),
    [
        (
            "  - {at: 2027-01-01, type: add_stream, stream: {name: PKV, amount: -1}}\n"
            "  - {at: 2027-02-01, type: set_stream, name: PKV, amount: -2}\n",
            "",
            "set_stream PKV",
        ),
        (  # one override sets the amount of both, a nominal one and one in euros of the start
            "  - {at: 2027-01-01, type: set_stream, name: Miete, amount: -1, id: x}\n"
            "  - {at: 2027-02-01, type: lump_sum, amount: 5, id: x}\n",
            "overrides: {events: {x: {amount: -2}}}\n",
            "overrides.events.x.amount",
        ),
    ],
    ids=["set_stream", "override"],
)
def test_amounts_on_mixed_indices_raise(data: Path, events: str, child: str, match: str) -> None:
    (data / "cashflows.yaml").write_text(STREAMS)
    _scenario(data, "base", f"name: base\nevents:\n{events}{child}")
    with pytest.raises(ValueError, match=match):
        rollforward.rebase(data, 1.1)


@pytest.mark.parametrize(
    ("event", "override", "rebased"),
    [
        (
            "{at: 2027-01-01, type: set_stream, name: Miete, amount: -600, id: x}",
            "{amount: -700}",
            "{amount: -728}",
        ),
        (
            "{at: 2027-01-01, type: add_stream, id: x,"
            " stream: {name: Job, kind: salary, gross: 1}}",
            "{stream: {name: Job, kind: salary, gross: 3500}}",
            "{stream: {name: Job, kind: salary, gross: 3640}}",
        ),
        (
            "{type: sell, asset: flat, when: {liquid_below: 50000}, id: x}",
            "{when: {liquid_below: 60000}}",
            "{when: {liquid_below: 62400}}",
        ),
    ],
    ids=["set_stream", "add_stream", "sell"],
)
def test_apply_rebases_what_a_child_sets_on_an_event(
    data: Path, event: str, override: str, rebased: str
) -> None:
    """An amount that a child sets on an inherited event, in euros of the start: without the roll
    the child would drift from its parent by the consumer prices (1.04 here)."""
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - {id: flat, kind: property, sqm: 50, per_sqm: 3000}\n")
    _scenario(
        data,
        "base",
        f"name: base\nphases: [{{from: 2026-01-01, phase: work}}]\nevents: [{event}]\n",
    )
    child = "name: child\nextends: base\noverrides: {{events: {{x: {}}}}}  # mine\n"
    _scenario(data, "child", child.format(override))
    _fetched(data)
    rollforward.apply(data, date(2026, 5, 1), source="test")
    assert (data / "scenarios" / "child.yaml").read_text() == child.format(rebased)


def test_apply_rebases_what_a_template_sets_on_an_event_of_a_child(data: Path) -> None:
    """The override of a template reaches the event of its id that only a scenario below writes:
    the run of that scenario takes it in euros of the start too."""
    template = "name: tpl\nabstract: true\noverrides: {{events: {{x: {{amount: {}}}}}}}\n"
    _scenario(data, "tpl", template.format(-700))
    _scenario(
        data,
        "child",
        "name: child\nextends: tpl\nphases: [{from: 2026-01-01, phase: work}]\n"
        "events: [{at: 2027-01-01, type: set_stream, name: Miete, amount: -600, id: x}]\n",
    )
    _fetched(data)
    rollforward.apply(data, date(2026, 5, 1), source="test")
    assert (data / "scenarios" / "tpl.yaml").read_text() == template.format(-728)


def test_apply_keeps_a_let_property(data: Path) -> None:
    """The rent follows the consumer prices, the property stays as written: `bought_for` is
    nominal by law, and with `building_share` it keeps the AfA base."""
    with (data / "assets.yaml").open("a") as fh:
        fh.write(
            "  - {id: flat, kind: property, sqm: 50, per_sqm: 3000, bought: 2015-06-01,\n"
            "     bought_for: 120000, building_share: 0.7, afa: 0.02}\n"
        )
    with (data / "cashflows.yaml").open("a") as fh:
        fh.write("  - {name: Mieteinnahme, kind: other_income, amount: 800, property: flat}\n")
    before = (data / "assets.yaml").read_text()
    _fetched(data)
    rollforward.apply(data, date(2026, 5, 1), source="test")
    assert (data / "assets.yaml").read_text() == before
    assert {s.name: s.amount for s in load_streams(data)}["Mieteinnahme"] == 832


PERIODIC = """\
streams:
  - name: Kfz
    cat: auto
    amount: -600
    every: 12  # yearly
    index: null
  - name: Beitrag
    cat: verein
    amount: -120
    every: 12
    start: 2026-03-01
    index: null
"""
ABO = "{name: Abo, cat: medien, amount: -30, every: 3, index: null}"


def _paid(data: Path) -> dict[str, list[date]]:
    """The months in which a `fixed` run pays each stream."""
    r = fixed_run(data)
    assert r.ledger is not None
    return {
        item: [month for month, paid in zip(r.months, row, strict=True) if paid]
        for (_, _, item), row in r.ledger.entries.items()
        if item in ("Kfz", "Beitrag", "Abo")
    }


def test_apply_keeps_the_payment_months_of_periodic_streams(data: Path) -> None:
    (data / "cashflows.yaml").write_text(PERIODIC)
    _scenario(
        data,
        "base",
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
        f"events: [{{at: 2026-06-01, type: add_stream, stream: {ABO}}}]\n",
    )
    before = _paid(data)
    new = date(2026, 5, 1)
    roll = rollforward.apply(data, new, source="test")
    assert _paid(data) == {name: [m for m in paid if m >= new] for name, paid in before.items()}
    assert [(p.file, p.name, p.every) for p in roll.periodic] == [
        ("cashflows.yaml", "Kfz", 12),
        ("scenarios/base.yaml", "Abo", 3),
    ]
    text = (data / "cashflows.yaml").read_text()
    assert "    every: 12  # yearly\n    start: 2026-01-01\n" in text
    scenario = (data / "scenarios" / "base.yaml").read_text()
    assert ABO.replace("every: 3", "every: 3, start: 2026-01-01") in scenario


BUSINESS = "streams: [{name: Praxis, kind: self_employed, amount: 5000, index: null, start: "
FOUNDED, LATER = date(2026, 2, 1), date(2027, 3, 1)


def _business(data: Path, assumptions: str, scenario: str = "", start: date = FOUNDED) -> None:
    """A business from `start` and a run to 2033, past the years of the half Regelbeitrag."""
    (data / "cashflows.yaml").write_text(f"{BUSINESS}{start:%Y-%m-%d}}}]\n")
    path = data / "assumptions.yaml"
    path.write_text(path.read_text().replace("horizon_age: 51", "horizon_age: 56") + assumptions)
    with (data / "scenarios" / "base.yaml").open("a") as fh:
        fh.write(scenario)


def _full_rv(data: Path) -> date:
    """The first month of a `fixed` run of `base` that pays the whole Regelbeitrag: more than
    half again the RV of the first month that pays one (the price level rises each January)."""
    r = fixed_run(data)
    assert r.ledger is not None
    rv = r.ledger.entries[TAX, "", "RV"]
    half = next(paid for paid in rv if paid)
    return next(month for month, paid in zip(r.months, rv, strict=True) if paid > 1.5 * half)


@pytest.mark.parametrize(
    ("assumptions", "scenario", "file", "written"),
    [
        (
            "tax: {self_employed: {rv: regular}}\n",
            "",
            "assumptions.yaml",
            "tax: {self_employed: {rv: regular, founded: 2026-02-01}}\n",
        ),
        (
            "tax: {self_employed: {rv: none}}\n",
            "overrides:\n  tax:\n    self_employed:\n      rv: regular\n      founded: null\n",
            "scenarios/base.yaml",
            "      rv: regular\n      founded: 2026-02-01\n",
        ),
        (  # a null without text: ruamel.yaml places it at the next key
            "tax: {self_employed: {rv: none}}\n",
            "overrides:\n  tax:\n    self_employed:\n      founded:\n      rv: regular\n",
            "scenarios/base.yaml",
            "      founded: 2026-02-01\n      rv: regular\n",
        ),
    ],
    ids=["assumptions", "scenario", "empty"],
)
def test_apply_keeps_the_founding_of_a_running_business(
    data: Path, assumptions: str, scenario: str, file: str, written: str
) -> None:
    """§165 Abs. 1 S. 2 SGB VI: the half Regelbeitrag ends with the third calendar year after the
    founding, not after the new start. The roll writes the founding where the options are."""
    _business(data, assumptions, scenario)
    full = _full_rv(data)
    roll = rollforward.apply(data, LATER, source="test")
    assert [(f.file, f.month, f.scenarios) for f in roll.founded] == [(file, FOUNDED, ("base",))]
    assert written in (data / file).read_text()
    assert _full_rv(data) == full == date(2030, 1, 1)


@pytest.mark.parametrize(
    ("assumptions", "start"),
    [
        ("tax: {self_employed: {rv: regular, founded: 2025-06-01}}\n", FOUNDED),  # set already
        ("tax: {self_employed: {rv: regular}}\n", date(2027, 6, 1)),  # starts after the roll
        ("", FOUNDED),  # `rv: none` takes no founding
    ],
)
def test_check_writes_no_founding_that_a_run_does_not_derive(
    data: Path, assumptions: str, start: date
) -> None:
    _business(data, assumptions, start=start)
    assert rollforward.check(data, LATER).founded == []


LOSS = (
    "streams: [{name: Laden, kind: self_employed, amount: -1000, index: null, end: 2027-01-01}]\n"
)


@pytest.mark.parametrize(
    ("assumptions", "scenario", "file", "written"),
    [
        ("", "", "assumptions.yaml", "start: 2027-03-01\ntax: {loss_carryforward: 12000}\n"),
        (
            "tax: {pkv: true}\n",
            "",
            "assumptions.yaml",
            "tax: {pkv: true, loss_carryforward: 12000}",
        ),
        (
            "tax:\n  self_employed:\n    rv: income\n",
            "",
            "assumptions.yaml",
            "tax:\n  loss_carryforward: 12000\n  self_employed:\n    rv: income\n",
        ),
        (
            "tax: {self_employed: {rv: income}}\n",
            "",
            "assumptions.yaml",
            "tax: {loss_carryforward: 12000, self_employed: {rv: income, founded: 2026-01-01}}\n",
        ),
        ("tax: {}\n", "", "assumptions.yaml", "tax: {loss_carryforward: 12000}\n"),
        (
            "tax:\n  loss_carryforward: 5000\n",
            "overrides:\n  tax:\n    pkv: true\n",
            "scenarios/base.yaml",
            "    pkv: true\n    loss_carryforward: 17000\n",
        ),
    ],
    ids=["new", "assumptions", "nested", "nested flow", "empty", "scenario"],
)
def test_apply_keeps_the_losses_that_the_run_carries(
    data: Path, assumptions: str, scenario: str, file: str, written: str
) -> None:
    """§10d Abs. 2 EStG: the loss of a business in 2026 offsets the income of the years after; a
    run from the new start would lose it. The roll writes it as `tax.loss_carryforward` where the
    scenario takes its options, as their first entry where each of them holds a mapping, a new
    `tax` behind `start` where there are none; no key twice, the other options kept, and the next
    check finds nothing more to write."""
    (data / "cashflows.yaml").write_text(LOSS)
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write(assumptions)
    with (data / "scenarios" / "base.yaml").open("a") as fh:
        fh.write(scenario)
    base = data / "scenarios" / "base.yaml"
    rv = load_plan(data, base).assumptions.tax.self_employed.rv
    roll = rollforward.apply(data, LATER, source="test")
    pot = 17000.0 if scenario else 12000.0  # with the 5000 carried before
    assert {c.file: c.amount for c in roll.carried} == {file: pot}
    text = (data / file).read_text()
    assert written in text
    YAML().load(text)  # a key twice raises
    taken = load_plan(data, base).assumptions.tax
    assert (taken.loss_carryforward, taken.self_employed.rv) == (pot, rv)
    assert rollforward.check(data, date(2027, 4, 1)).carried == []


def test_scenarios_that_share_the_options_take_the_smallest_pot(data: Path) -> None:
    """A scenario whose other income takes up the loss of the business carries nothing: the
    options that it shares with `base` keep 0, so neither starts with losses it never built
    (errs towards more tax)."""
    (data / "cashflows.yaml").write_text(LOSS)
    income = "{name: Zins, kind: other_income, amount: 2000, index: null, end: 2027-01-01}"
    _scenario(
        data,
        "covered",
        "name: covered\nphases: [{from: 2026-01-01, phase: work}]\n"
        f"events: [{{at: 2026-01-01, type: add_stream, stream: {income}}}]\n",
    )
    assert rollforward.check(data, LATER).carried == []
    _scenario(data, "covered", "name: covered\nphases: [{from: 2026-01-01, phase: work}]\n")
    carried = rollforward.check(data, LATER).carried
    assert [(c.amount, c.scenarios) for c in carried] == [(12000.0, ("base", "covered"))]


def _losing_bond(data: Path) -> None:
    """A bond fund that loses 5% a year: a loss of capital income (§20 Abs. 6 EStG)."""
    path = data / "assumptions.yaml"
    path.write_text(
        path.read_text().replace("fixed_income: {mean: 0.03}", "fixed_income: {mean: -0.05}")
    )
    with (data / "assets.yaml").open("a") as fh:
        fh.write("  - id: bond\n    kind: fixed_income\n    value: 20000\n")


def _capital_losses(data: Path, scenario: str = "base") -> float:
    """The losses of capital income that a run of `scenario` carries to `LATER`."""
    engine = before(load_plan(data, data / "scenarios" / f"{scenario}.yaml"), LATER)
    assert engine is not None
    return round(float(engine.losses[0]), 2)


@pytest.mark.parametrize(
    ("assumptions", "written"),
    [
        ("", "start: 2027-03-01\ntax: {loss_carryforward: 12000, capital_losses: POT}\n"),
        ("tax: {}\n", "tax: {capital_losses: POT, loss_carryforward: 12000}\n"),
        ("tax:\n  pkv: true\n", "  pkv: true\n  capital_losses: POT\n  loss_carryforward: 12000\n"),
    ],
    ids=["new", "empty", "block"],
)
def test_apply_keeps_both_loss_pots_in_one_tax(data: Path, assumptions: str, written: str) -> None:
    """A loss of a business (§10d EStG) and of a bond fund (§20 Abs. 6 EStG) before the new start:
    the roll writes both pots into the one `tax` that the scenario takes, both nominal."""
    (data / "cashflows.yaml").write_text(LOSS)
    _losing_bond(data)
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write(assumptions)
    pot = _capital_losses(data)
    assert pot > 0
    rollforward.apply(data, LATER, source="test")
    assert written.replace("POT", str(pot)) in (data / "assumptions.yaml").read_text()
    taken = load_assumptions(data).tax
    assert (taken.loss_carryforward, taken.capital_losses) == (12000, pot)


def test_a_scenario_keeps_its_own_capital_losses(data: Path) -> None:
    """`tax.capital_losses` of a scenario that compares a decision of the BVerfG (2 BvL 3/21): the
    roll writes what its run carries to the new start into its overrides, less the capital income
    that the pot offset, nominal; `base` carries none."""
    seed = 30_000
    _scenario(
        data,
        "bverfg",
        f"name: bverfg\nextends: base\noverrides:\n  tax:\n    capital_losses: {seed}\n",
    )
    pot = _capital_losses(data, "bverfg")
    assert 0 < pot < seed
    roll = rollforward.apply(data, LATER, source="test")
    assert [(c.file, c.key, c.amount, c.scenarios) for c in roll.carried] == [
        ("scenarios/bverfg.yaml", rollforward.CAPITAL_LOSSES, pot, ("bverfg",))
    ]
    bverfg = load_plan(data, data / "scenarios" / "bverfg.yaml").assumptions.tax
    assert (bverfg.capital_losses, load_assumptions(data).tax.capital_losses) == (pot, 0)


@pytest.mark.parametrize(
    ("file", "text"),
    [
        ("cashflows.yaml", "streams:\n  - name: Miete\n    cat: wohnen\n    amount: -600\n"),
        ("scenarios/new.yaml", "name: new\nextends: base\n"),  # an input that the list lacked
    ],
    ids=["changed", "new"],
)
def test_apply_refuses_inputs_changed_since_the_list(data: Path, file: str, text: str) -> None:
    """The page lists the roll, then another device writes: the roll changes nothing."""
    shown, new = rollforward.seen(data), date(2026, 3, 1)
    revisions.write(data, "phone", lambda: {file: text})
    before = rollforward.inputs(data)
    with pytest.raises(revisions.ConflictError, match="by phone"):
        rollforward.apply(data, new, source="test", read=shown)
    assert rollforward.inputs(data) == before
    rollforward.apply(data, new, source="test", read=rollforward.seen(data))
    assert load_assumptions(data).start == new


def test_apply_refuses_a_passed_event_then_rolls(data: Path) -> None:
    (data / "cashflows.yaml").write_text(STREAMS)
    with (data / "assumptions.yaml").open("a") as fh:
        fh.write("indices: {insurance: {mean: 0.03}}\n")
    passed = "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
    _scenario(data, "base", passed + "events: [{at: 2026-03-01, type: lump_sum, amount: 5}]\n")
    before = (data / "assumptions.yaml").read_text()
    _fetched(data)
    with pytest.raises(ValueError, match="1 events lie before 2026-05"):
        rollforward.apply(data, date(2026, 5, 20), source="test")
    assert (data / "assumptions.yaml").read_text() == before
    _scenario(data, "base", passed)
    roll = rollforward.apply(data, date(2026, 5, 20), source="test")
    assert (roll.cpi.factor, len(roll.changes)) == (1.04, 5)
    assert load_assumptions(data).start == date(2026, 5, 1)
    assert (data / "assumptions.yaml").read_text() == before.replace("2026-01-01", "2026-05-01")
    streams = {s.name: s for s in load_streams(data)}
    assert (streams["Miete"].amount, streams["Gehalt"].gross) == (-520, 4160)
    assert streams["PKV"].amount == -300
    assert (streams["ETF"].amount, streams["ETF real"].amount) == (-500, -104)
    assert (streams["Rente"].gross, streams["Rente aus Punkten"].point_value) == (1560, 41.6)
    assert "# rent" in (data / "cashflows.yaml").read_text()
    assert yaml.safe_load((data / "cashflows.yaml").read_text())["streams"][0]["amount"] == -520


def _mutter(data: Path, given: str = "[]") -> None:
    """The relative `mutter` in `assumptions.yaml`, with her gifts before the start `given`."""
    path = data / "assumptions.yaml"
    path.write_text(
        path.read_text().replace(
            "person: {born: 1977-01-01, horizon_age: 51}\n",
            "person:\n  born: 1977-01-01\n  horizon_age: 51\n  relatives:\n"
            f"    mutter: {{born: 1950-05-01, sex: f, relation: parent, given: {given}}}\n",
        )
    )


@pytest.mark.parametrize(
    "gift", ["cash: 300000", "cash: 100000, equity: {value: 200000, cost_basis: 50000}"]
)
def test_a_passed_gift_moves_into_the_gifts_before_the_start(data: Path, gift: str) -> None:
    """A gift before the new start refuses no roll: it leaves its scenario for `given` of its
    relative, its cash and the value of its securities, with the Schenkungsteuer of §14 ErbStG on
    it and the gifts within ten years before it (300,000 over the Freibetrag at 11%). An
    inheritance without a month rebases its cash."""
    _mutter(data, "[{at: 2020-01-01, value: 300000, tax: 0}]")
    _scenario(
        data,
        "base",
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\nevents:\n"
        f"  - {{at: 2026-03-01, type: gift, from: mutter, {gift}}}  # passes\n"
        "  - {type: inheritance, from: mutter, cash: 100000}\n",
    )
    _fetched(data)
    roll = rollforward.check(data, date(2026, 5, 20))
    assert (roll.events, [g.item for g in roll.gifts], roll.gifts[0].tax) == (
        [],
        ["gift mutter"],
        22_000,
    )
    rollforward.apply(data, date(2026, 5, 20), source="test")
    given = load_assumptions(data).person.relatives["mutter"].given
    assert [(g.at, g.value, g.tax) for g in given] == [
        (date(2020, 1, 1), 300_000, 0),
        (date(2026, 3, 1), 300_000, 22_000),
    ]
    events = yaml.safe_load((data / "scenarios" / "base.yaml").read_text())["events"]
    assert events == [{"type": "inheritance", "from": "mutter", "cash": 104_000}]


def test_a_passed_gift_of_a_relative_of_the_overrides_refuses_the_roll(data: Path) -> None:
    """A relative that only a scenario defines has no `given` in `assumptions.yaml` to take it."""
    _scenario(
        data,
        "base",
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
        "overrides: {person: {relatives: {onkel: {born: 1950-01-01, sex: m, relation: other}}}}\n"
        "events: [{at: 2026-03-01, type: gift, from: onkel, cash: 1000}]\n",
    )
    _fetched(data)
    with pytest.raises(ValueError, match="names onkel, whom person"):
        rollforward.check(data, date(2026, 5, 20))


@pytest.mark.parametrize(
    ("at", "child", "refusal"),
    [
        ("2026-03-01", "overrides: {shift: {g: 6}}", "2026-03 falls in 2026-09 in the scenario"),
        ("2026-07-01", "overrides: {shift: {g: -3}}", "2026-07 falls in 2026-04 in the scenario"),
        ("2026-03-01", "overrides: {shift: {g: -1}}", "overrides.shift.g names the gift g"),
        ("2026-03-01", "overrides: {events: {g: {cash: 9}}}", "overrides.events.g names the"),
        ("2026-03-01", "drop: [g]", r"child.yaml: drop\[0\] names the gift g"),
    ],
    ids=["shifted after", "shifted before", "shifted", "overridden", "dropped"],
)
def test_a_gift_that_a_scenario_moves_or_names_refuses_the_roll(
    data: Path, at: str, child: str, refusal: str
) -> None:
    """The roll moves a gift by the month of its file: a child that shifts it across the new
    start, or names it by its id, which would name nothing after the move, refuses it before the
    write, the files unchanged."""
    _mutter(data)
    _scenario(
        data,
        "base",
        "name: base\nphases: [{from: 2026-01-01, phase: work}]\n"
        f"events: [{{at: {at}, type: gift, from: mutter, cash: 1000, id: g}}]\n",
    )
    _scenario(data, "child", f"name: child\nextends: base\n{child}\n")
    _fetched(data)
    before = rollforward.inputs(data)
    with pytest.raises(ValueError, match=refusal):
        rollforward.apply(data, date(2026, 5, 20), source="test")
    assert rollforward.inputs(data) == before
