"""Forms from the model: the fields of a model, how a value shows and reads in its unit, the edits
of a form, the save guard's list, a save refused after a change on disk, and one render."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from builders import seen
from streamlit.testing.v1 import AppTest

from dagobert import i18n, revisions, store
from dagobert.loader import load_assumptions, read_yaml
from dagobert.model.assumptions import Assumptions
from dagobert.model.base import KeyPath, Unit
from dagobert.model.events import BuyPropertyEvent, LumpSumEvent
from dagobert.model.plan import Scenario
from dagobert.model.streams import Stream
from dagobert.overrides import ASSUMPTIONS, DEFAULT, Leaf, own
from dagobert.problems import Problem
from dagobert.store import NULL
from dagobert.ui import fields, formguard, forms, gridcolumns, widgets
from dagobert.ui.fields import ABSENT, Kind

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import BaseModel

FIELDS = {f.path: f for f in fields.of(Assumptions)}
SUM = {f.path: f for f in fields.of(LumpSumEvent)}[("amount",)]  # signed euros
SCENARIO = {f.path: f for f in fields.of(Scenario)}
GLIDE = [{"age": 50, "share": 0.3}]
RETURNS = {k: {"mean": 0.02} for k in ("equity", "fixed_income", "cash", "property")}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("20", 20.0),
        ("20,5", 20.5),
        ("20.50", 20.5),
        (" 1.234,56 € ", 1234.56),
        ("1,234.56", 1234.56),
        ("1.234", 1234.0),  # three digits after a mark group thousands
        ("1.234.567", 1234567.0),
        ("1,234,56", None),  # one mark for both
        ("20,505", 20505.0),
        ("-20", None),  # spending is stored below zero, no minus
        ("20,", None),
        ("zwanzig", None),
        ("", None),
    ],
)
def test_euros_read_a_comma_and_a_point_alike(text: str, expected: float | None) -> None:
    assert fields.euros(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"), [("-20", -20.0), ("-1.234,56", -1234.56), ("--20", None), ("2-0", None)]
)
def test_signed_euros_take_a_minus(text: str, expected: float | None) -> None:
    assert fields.euros(text, signed=True) == expected


@pytest.mark.parametrize(
    ("path", "kind", "unit", "default"),
    [
        (("care", "cost"), Kind.NUMBER, Unit.EUR, ABSENT),
        (("care", "duration", "mean"), Kind.NUMBER, Unit.MONTHS, ABSENT),
        (("inflation", "mean"), Kind.NUMBER, Unit.PERCENT, ABSENT),  # required in `inflation`
        (("person", "horizon_age"), Kind.INTEGER, Unit.YEARS, 105),
        (("start",), Kind.DATE, Unit.MONTH, ABSENT),
        (("tax", "year"), Kind.CHOICE, None, None),  # empty: the year of `start`
        (("tax", "pkv"), Kind.BOOL, None, True),
        (("allocation",), Kind.SECTION, None, None),
        (("allocation", "fixed_income"), Kind.ROWS, None, ABSENT),
        (("allocation", "rebalance_every"), Kind.INTEGER, Unit.MONTHS, 12),
        (("spending", "categories"), Kind.NAMES, None, []),
        (("scale", "salary"), Kind.MAP, None, {}),
        (("returns",), Kind.MAP, None, ABSENT),
        (("phases",), Kind.MAP, None, ABSENT),
    ],
)
def test_a_field_takes_its_kind_unit_and_default_from_the_schema(
    path: KeyPath, kind: Kind, unit: Unit | None, default: object
) -> None:
    field = FIELDS[path]
    assert (field.kind, field.unit, field.default) == (kind, unit, default)


def test_a_mapping_of_numbers_takes_a_number_per_name() -> None:
    """`scale.salary` per phase of the inputs: empty counts as 1."""
    found = fields.entries(FIELDS[("scale", "salary")], ["work", "part-time"])
    assert [(f.path, f.kind, f.unit, f.low, f.entry) for f in found] == [
        (("scale", "salary", name), Kind.NUMBER, Unit.FACTOR, 0, True)
        for name in ("work", "part-time")
    ]
    assert found[0].label == "Salary work"


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (("cash_buffer_months",), "Cash buffer months"),
        (("tax", "pkv"), "PKV"),
        (("tax", "kv_zusatz"), "KV zusatz %"),
        (("person", "rv_since"), "RV since"),
    ],
)
def test_a_label_reads_its_key_in_words_and_an_acronym_as_written(
    path: KeyPath, label: str
) -> None:
    assert FIELDS[path].label == label


def test_a_field_and_a_column_say_their_words_in_the_language_of_the_session() -> None:
    """A field and a column keep the English of the model, built once: their label, header and
    help speak the language of the session where they show, the name of an entry as written."""
    share = FIELDS[("tax", "teilfreistellung")]
    [work] = fields.entries(FIELDS[("scale", "salary")], ["work"])
    amount = next(c for c in gridcolumns.columns(Stream) if c.name == "amount")
    english = (share.label, share.help, work.label, amount.header)
    with i18n.use("de"):
        assert (share.label, work.label, amount.header) == (
            "Teilfreistellung %",
            "Gehalt work",
            "Betrag",
        )
        assert share.help == (
            "Steuerfreier Anteil der Gewinne eines Aktienfonds, für jedes Depot ohne eigenen "
            "(Standard: 30\u00a0%). In Prozent: 2,5 für 2,5\u00a0%."
        )
    assert english == (
        "Teilfreistellung %",
        "Share of the gains of an equity fund free of tax, for every depot without its own "
        "(default: 30%). In percent: 2.5 for 2.5%.",
        "Salary work",
        "amount",
    )


@pytest.mark.parametrize(
    ("path", "default"),
    [
        (("refinance_rate",), "(default: 4%)"),
        (("inflation", "mean"), "(default: 2%)"),  # of the mapping: `inflation` is optional
        (("tax", "sparer_pauschbetrag"), "(default: 1.000 €)"),
        (("tax", "pkv"), "(default: on)"),
    ],
)
def test_the_help_of_a_field_names_its_default(path: KeyPath, default: str) -> None:
    assert default in FIELDS[path].help


def test_a_field_of_an_optional_section_names_it() -> None:
    assert FIELDS[("care", "duration", "mean")].section == ("care",)
    assert FIELDS[("inflation", "mean")].section is None
    assert ("type",) not in {f.path for f in fields.of(LumpSumEvent)}  # a tag is no field


@pytest.mark.parametrize(
    ("field", "text", "expected"),
    [
        (FIELDS[("care", "cost")], "1.234,50", 1234.5),
        (FIELDS[("care", "cost")], "1,234.50", 1234.5),
        (FIELDS[("care", "cost")], "1.234", 1234.0),
        (SUM, "-1.234,5", -1234.5),  # a sum that pays out
        (FIELDS[("inflation", "mean")], "2,5", 0.025),
        (FIELDS[("inflation", "mean")], "2.5%", 0.025),
        (FIELDS[("inflation", "mean")], "-0.5", -0.005),  # a rate may fall
        (FIELDS[("cash_buffer_months",)], "4,5", 4.5),
        (FIELDS[("person", "horizon_age")], "95", 95),
        (FIELDS[("start",)], "2027-05", date(2027, 5, 1)),
        (FIELDS[("start",)], "2027-05-17", date(2027, 5, 1)),
        (FIELDS[("start",)], "05.2027", date(2027, 5, 1)),  # a German user types day first
        (FIELDS[("start",)], "17.5.2027", date(2027, 5, 1)),
        (FIELDS[("person", "born")], "1965-03-14", date(1965, 3, 14)),
        (FIELDS[("person", "born")], "14.03.1965", date(1965, 3, 14)),
        (FIELDS[("tax", "year")], "2026", 2026),
        (FIELDS[("tax", "pkv")], "false", False),
        (FIELDS[("care", "index")], "null", NULL),  # nominal, not the default `cpi`
        (FIELDS[("care", "cost")], " ", None),  # the fallback
    ],
)
def test_parse_reads_a_text_in_the_unit_of_its_field(
    field: fields.Field, text: str, expected: object
) -> None:
    assert fields.parse(field, text) == expected


@pytest.mark.parametrize(
    ("path", "text", "problem"),
    [
        (("care", "cost"), "-5", "above 0 €"),
        (("tax", "teilfreistellung"), "150", "at most 100%"),
        (("tax", "teilfreistellung"), "-1", "at least 0%"),
        (("cash_buffer_months",), "-1", "at least 0"),
        (("person", "horizon_age"), "85,5", "whole number"),
        (("person", "horizon_age"), "0", "at least 1"),
        (("start",), "2027-13", "a month"),
        (("person", "born"), "14031965", "a date"),  # either order
        (("person", "born"), "31.02.1965", "a date"),
        (("start",), "13.2027", "a month"),
        (("inflation", "mean"), "1.234,5", "a number"),  # a percent takes no thousands groups
        (("tax", "year"), "2019", "one of 2026"),
    ],
)
def test_parse_refuses_a_text_with_what_to_type(path: KeyPath, text: str, problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        fields.parse(FIELDS[path], text)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (FIELDS[("inflation", "mean")], 0.1),
        (FIELDS[("inflation", "mean")], 0.025),
        (FIELDS[("inflation", "mean")], -0.02),
        (FIELDS[("refinance_rate",)], 0.011),
        (FIELDS[("care", "cost")], 1234.56),
        (FIELDS[("care", "cost")], 1000),
        (SUM, -0.02),
        (FIELDS[("start",)], date(2027, 5, 1)),
    ],
)
def test_a_shown_value_reads_back_the_same(field: fields.Field, value: object) -> None:
    assert fields.parse(field, fields.shown(field, value)) == value


@pytest.mark.parametrize(
    ("path", "text", "expected"),
    [
        (("cash_buffer_months",), "4", 4),
        (("care", "cost"), "1.000", 1000),
        (("tax", "teilfreistellung"), "100", 1),
        (("cash_buffer_months",), "4,5", 4.5),
    ],
)
def test_a_whole_number_is_written_as_an_int(path: KeyPath, text: str, expected: float) -> None:
    """`4`, not `4.0`, as the other writers keep it."""
    value = fields.parse(FIELDS[path], text)
    assert (value, type(value)) == (expected, type(expected))


def test_an_untouched_text_keeps_what_it_cannot_show() -> None:
    cost = FIELDS[("care", "cost")]
    assert fields.shown(cost, 1234.567) == "1.234,57"
    assert fields.read(cost, "1.234,57", 1234.567) == 1234.567
    assert fields.read(cost, "", 1234.567) is ABSENT


def test_a_placeholder_names_the_fallback_and_its_source() -> None:
    mean = FIELDS[("inflation", "mean")]
    assert fields.placeholder(mean, Leaf(0.02, DEFAULT)) == "2 (default)"
    assert fields.placeholder(mean, Leaf(0.03, "base")) == "3 from base"
    pauschbetrag = FIELDS[("tax", "sparer_pauschbetrag")]
    assert (
        fields.placeholder(pauschbetrag, Leaf(1000, ASSUMPTIONS)) == "1.000 from assumptions.yaml"
    )
    assert fields.placeholder(mean, None) == ""


@pytest.mark.parametrize(
    ("field", "start"),
    [
        (FIELDS[("cash_buffer_months",)], "decimal-"),  # no minus: the decimal keypad
        (FIELDS[("care", "cost")], "decimal-"),
        (FIELDS[("inflation", "mean")], ""),  # a rate may fall, the keypad may lack the minus
        (FIELDS[("start",)], ""),
        (FIELDS[("care", "index")], "nocaps-"),
        (SCENARIO[("extends",)], "nocaps-"),
        (SCENARIO[("name",)], ""),  # for people
    ],
)
def test_the_keyboard_of_a_phone_follows_the_field(field: fields.Field, start: str) -> None:
    assert widgets.prefix(field) == start


def test_changes_show_each_field_in_its_unit() -> None:
    old = {
        "care": {"hazard": [{"age": 80, "factor": 0.01}], "cost": 1000, "duration": {"mean": 24}},
        "tax": {"teilfreistellung": 0.3},
    }
    new = {
        "care": {"hazard": [{"age": 80, "factor": 0.02}], "cost": 1200.5, "duration": {"mean": 30}},
        "tax": {"teilfreistellung": 0.15},
    }
    assert [c.text for c in formguard.changes(old, new, list(FIELDS.values()))] == [
        "**care hazard 1 factor** 1% → 2%",
        "**care cost** 1.000,00 € → 1.200,50 €",
        "**care duration mean** 24 → 30",
        "**tax teilfreistellung** 30% → 15%",
    ]


def test_a_section_shows_on_or_off_and_not_its_fields() -> None:
    old = {"allocation": {"fixed_income": GLIDE}}
    assert [c.text for c in formguard.changes(old, {}, list(FIELDS.values()))] == [
        "**allocation** on → off"
    ]
    assert [c.text for c in formguard.changes(old, {}, list(FIELDS.values()), override=True)] == [
        "**allocation** on → empty",
        "**allocation fixed\\_income 1 age** 50 → empty",
        "**allocation fixed\\_income 1 share** 30% → empty",
    ]


FORM = forms.Form("form", "assumptions.yaml", tuple(FIELDS.values()), Assumptions)
OFF = forms.Typed({}, {("allocation",): False}, {})
ON = forms.Typed({}, {("allocation",): True}, {})


@pytest.mark.parametrize(
    ("override", "part", "typed", "fallback", "after"),
    [
        (False, {"allocation": {"fixed_income": GLIDE}}, OFF, {}, ABSENT),  # no key
        # an override switches off what it inherits
        (True, {}, OFF, {("allocation", "fixed_income"): Leaf(GLIDE, ASSUMPTIONS)}, None),
        (True, {}, OFF, {}, ABSENT),  # nothing to switch off
        (False, {}, ON, {}, {}),  # on with the defaults
        (
            True,
            {"allocation": None},
            ON,
            {("allocation", "fixed_income"): Leaf(GLIDE, "base")},
            ABSENT,
        ),
    ],
)
def test_a_section_off_goes_from_assumptions_and_is_null_in_an_override(
    override: bool,
    part: dict[str, Any],
    typed: forms.Typed,
    fallback: dict[KeyPath, Leaf],
    after: object,
) -> None:
    form = replace(FORM, override=override)
    assert own(part, forms.edits(form, part, typed, fallback)).get("allocation", ABSENT) == after


def test_an_untouched_form_has_no_edits() -> None:
    part = {"inflation": {"mean": 0.025}, "allocation": {"fixed_income": GLIDE}}
    held: dict[KeyPath, Any] = {("inflation", "mean"): 0.025, ("allocation", "fixed_income"): GLIDE}
    typed = forms.Typed(held, {("allocation",): True}, {})
    assert forms.edits(FORM, part, typed, fields.fallback(Assumptions, part)) == {}


def test_the_model_names_what_it_refuses_by_key_path() -> None:
    twice = [{"age": 50, "share": 0.3}, {"age": 50, "share": 0.4}]
    mapping = {
        "person": {"born": date(1965, 3, 14)},
        "start": date(2026, 1, 1),
        "phases": {"work": {}},
        "returns": RETURNS,
        "allocation": {"fixed_income": twice},
    }
    found = forms.problems(Assumptions, mapping, "assumptions.yaml")
    assert [forms.explain(p) for p in found] == ["allocation.fixed_income: each age once: 50 twice"]


def test_the_edits_of_one_file_write_together() -> None:
    rows: dict[store.Way, store.RowEdits] = {
        ("allocation", "fixed_income"): store.RowEdits(added=[GLIDE[0]])
    }
    found = forms.merged(
        [
            store.Edit("assumptions.yaml", {("seed",): 3}),
            store.Edit("app.yaml", {("scenarios",): ["base"]}),
            store.Edit("assumptions.yaml", rows=rows),
            store.Edit("scenarios/new.yaml", {("name",): "new"}, create=True),
            store.Edit("scenarios/new.yaml", {("extends",): "base"}),
            store.Edit("scenarios/old.yaml", remove=True),
            store.Edit("scenarios/old.yaml"),
        ]
    )
    assert found == [
        store.Edit("assumptions.yaml", {("seed",): 3}, rows),
        store.Edit("app.yaml", {("scenarios",): ["base"]}),
        store.Edit("scenarios/new.yaml", {("name",): "new", ("extends",): "base"}, create=True),
        store.Edit("scenarios/old.yaml", remove=True),
    ]


def test_a_form_whose_part_changed_on_disk_is_refused_and_names_the_change(data: Path) -> None:
    inflation = replace(FORM, fields=tuple(f for f in FORM.fields if f.path[0] == "inflation"))
    seed = replace(FORM, fields=(FIELDS[("seed",)],))
    doc = read_yaml(data / "assumptions.yaml")
    bases = {
        form.key: forms.Base(form.part(doc), seen(data, form.file, form.part(doc)))
        for form in (inflation, replace(seed, key="seed"))
    }
    elsewhere = store.Edit("assumptions.yaml", {("inflation", "mean"): 0.03})
    store.write(data, [elsewhere], source="Elsewhere")
    mine: dict[KeyPath, Any] = {("inflation", "mean"): 0.025}
    shown = forms.Shown(data, inflation, bases["form"], forms.Typed(mine, {}, {}), mine, stale=True)
    with pytest.raises(revisions.ConflictError, match="Elsewhere"):
        store.write(data, [shown.edit()], source="form", check=shown.check)
    assert load_assumptions(data).inflation.mean == 0.03
    now = inflation.part(read_yaml(data / "assumptions.yaml"))
    assert [c.text for c in formguard.changes(bases["form"].part, now, inflation.fields)] == [
        "**inflation mean** empty → 3%"
    ]
    assert forms.conflict(data, replace(seed, key="seed"), bases["seed"]) is None  # another part


HARNESS = """
from pathlib import Path
from dagobert.model.assumptions import Assumptions
from dagobert.ui import fields, forms, guard
data = Path({data!r})
found = tuple(f for f in fields.of(Assumptions) if f.kind is not fields.Kind.MAP)
shown = forms.show(data, forms.Form("harness", "assumptions.yaml", found, model=Assumptions))
flagged = guard.review(shown.changes(), key="harness", hint="")
forms.save(data, [shown], key="harness-save", flagged=flagged)
"""


@pytest.mark.parametrize("mobile", ["0", "1"])
def test_a_form_renders_and_saves_one_revision(data: Path, mobile: str) -> None:
    at = AppTest.from_string(HARNESS.format(data=str(data)), default_timeout=30)
    at.query_params["mobile"] = mobile
    at.run()
    assert not at.exception
    share = next(w for w in at.text_input if w.label == "Teilfreistellung %")
    share.input("150").run()
    assert any("at most 100%" in w.value for w in at.warning)
    assert next(b for b in at.button if b.label.startswith("Save")).disabled
    share.input("").run()
    next(w for w in at.text_input if w.label == "Cash buffer months").input("4,5").run()
    assert any("4.5" in c.value for c in at.caption)  # the list of the save guard
    next(b for b in at.button if b.label.startswith("Save")).click().run()
    assert not at.exception
    assert load_assumptions(data).cash_buffer_months == 4.5
    assert revisions.entries(data)[-1].source == "app"


def test_a_write_between_the_revision_and_the_read_counts_as_a_change(
    data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The form takes the revision before it reads the file: the base then holds the revision
    from before the write, so a later check cannot take the read for the revision."""
    before = revisions.last_change(data, "assumptions.yaml")
    read = forms._doc

    def raced(data_dir: Path, form: forms.Form) -> dict[str, Any]:
        monkeypatch.setattr(forms, "_doc", read)
        store.write(
            data_dir, [store.Edit(form.file, {("cash_buffer_months",): 9})], source="Elsewhere"
        )
        return read(data_dir, form)

    monkeypatch.setattr(forms, "_doc", raced)
    at = AppTest.from_string(HARNESS.format(data=str(data)), default_timeout=30).run()
    assert not at.exception
    held = at.session_state["harness-base"]
    assert held.seen.revision == before != revisions.last_change(data, "assumptions.yaml")
    assert held.part["cash_buffer_months"] == 9


def test_save_pressed_with_an_edit_that_moves_a_fallback_saves(data: Path) -> None:
    """Typing the inflation mean changes what its stdev falls back to (1% to 0%): a rerun for the
    placeholder must not drop the press of Save that came with the typing."""
    at = AppTest.from_string(HARNESS.format(data=str(data)), default_timeout=30)
    at.run()
    next(w for w in at.text_input if w.label == "Cash buffer months").input("4").run()
    next(w for w in at.text_input if w.label == "Mean %").input("2,5")
    next(b for b in at.button if b.label.startswith("Save")).click().run()
    assert not at.exception
    saved = load_assumptions(data)
    assert (saved.cash_buffer_months, saved.inflation.mean, saved.inflation.stdev) == (4, 0.025, 0)
    assert "cash_buffer_months: 4\n" in (data / "assumptions.yaml").read_text()


@pytest.mark.parametrize(
    ("candidate", "path", "expected"),
    [
        ({}, ("inflation", "mean"), Leaf(0.02, DEFAULT)),  # the default of `inflation`
        ({}, ("inflation", "stdev"), Leaf(0.01, DEFAULT)),
        ({"inflation": {"mean": 0.03}}, ("inflation", "stdev"), Leaf(0.0, DEFAULT)),  # its own
        ({"inflation": {"stdev": 0.03}}, ("inflation", "mean"), None),  # required
        ({"allocation": {}}, ("allocation", "rebalance_every"), Leaf(12, DEFAULT)),
    ],
)
def test_an_empty_field_falls_back_to_what_the_model_takes_from_the_candidate(
    candidate: dict[str, Any], path: KeyPath, expected: Leaf | None
) -> None:
    assert fields.fallback(Assumptions, candidate).get(path) == expected


def test_a_list_of_a_union_is_a_list_of_rows() -> None:
    assert SCENARIO[("events",)].kind is Kind.ROWS


def test_a_section_held_empty_gives_no_edit() -> None:
    part: dict[str, Any] = {"spending": {}}
    on = forms.Typed({}, {("spending",): True}, {})
    assert forms.edits(FORM, part, on, fields.fallback(Assumptions, part)) == {}


def test_a_mapping_by_name_changes_per_entry_and_field() -> None:
    part = {"returns": {"equity": {"mean": 0.05, "stdev": 0.1}, "gold": {"mean": 0.01}}}
    new = {"equity": {"mean": 0.06, "stdev": 0.1}, "bitcoin": {"mean": 0.1}}
    typed = forms.Typed({("returns",): new}, {}, {})
    assert forms.edits(FORM, part, typed, {}) == {
        ("returns", "gold"): None,
        ("returns", "equity", "mean"): 0.06,
        ("returns", "bitcoin"): {"mean": 0.1},
    }
    assert [c.text for c in formguard.changes(part, {"returns": new}, [FIELDS[("returns",)]])] == [
        "**returns equity mean** 5% → 6%",
        "**returns gold mean** 1% → empty",
        "**returns bitcoin mean** empty → 10%",
    ]


EVENTS = """\
name: base
events:
  - {at: 2027-01-01, type: lump_sum, amount: 1000}
  - {at: 2028-01-01, type: lump_sum, amount: 2000}
"""
LUMP = tuple(fields.of(LumpSumEvent))


def test_a_form_on_an_item_of_a_list_edits_it_and_sees_an_insert(data: Path) -> None:
    (data / "scenarios" / "base.yaml").write_text(EVENTS)
    form = forms.Form("event", "scenarios/base.yaml", LUMP, LumpSumEvent, keys=("events", 1))
    doc = read_yaml(data / form.file)
    assert form.part(doc) == {"at": date(2028, 1, 1), "amount": 2000}
    base = forms.Base(form.part(doc), seen(data, form.file, form.part(doc)))
    mine: dict[KeyPath, Any] = {("amount",): 2500}
    shown = forms.Shown(data, form, base, forms.Typed(mine, {}, {}), mine, stale=False)
    store.write(data, [shown.edit()], source="form", check=shown.check)
    assert read_yaml(data / form.file)["events"][1]["amount"] == 2500
    first = {"at": date(2026, 6, 1), "type": "lump_sum", "amount": 5}
    store.write(
        data,
        [store.Edit(form.file, {("events",): [first, *read_yaml(data / form.file)["events"]]})],
        source="Elsewhere",
    )
    assert forms.conflict(data, form, replace(base, part=base.part | {"amount": 2500})) is not None


def test_a_new_row_takes_its_fixed_type(data: Path) -> None:
    (data / "scenarios" / "base.yaml").write_text(EVENTS)
    form = forms.Form(
        "add", "scenarios/base.yaml", LUMP, LumpSumEvent, keys=("events",), new={"type": "lump_sum"}
    )
    assert ("amount",) not in form.leaves(data, {})  # required: Save stays off
    assert ("at",) not in form.leaves(data, {})  # every event but a sale has a month
    doc = read_yaml(data / form.file)
    assert [forms.explain(p) for p in form.problems(data, doc, {"amount": 5})] == [
        "events[2].at: Field required"
    ]
    mine: dict[KeyPath, Any] = {("at",): date(2029, 1, 1), ("amount",): 300}
    shown = forms.Shown(
        data, form, forms.Base({}, None), forms.Typed(mine, {}, {}), mine, stale=False
    )
    store.write(data, [shown.edit()], source="form", check=shown.check)
    assert read_yaml(data / form.file)["events"][-1] == {
        "at": date(2029, 1, 1),
        "type": "lump_sum",
        "amount": 300,
    }


def test_a_list_of_the_file_keeps_its_comments_and_layout(data: Path) -> None:
    path = data / "assumptions.yaml"
    path.write_text(
        path.read_text() + "allocation:\n  fixed_income:\n    - {age: 48, share: 0.1}\n"
        "    # bonds later\n    - {age: 62, share: 0.2}\n"
    )
    glide = replace(FORM, fields=(FIELDS[("allocation", "fixed_income")],))
    rows: dict[KeyPath, store.RowEdits] = {
        ("allocation", "fixed_income"): store.RowEdits(edited={1: {"share": 0.25}})
    }
    part = glide.part(read_yaml(path))
    shown = forms.Shown(
        data, glide, forms.Base(part, None), forms.Typed({}, {}, {}, rows), {}, stale=False
    )
    assert [c.text for c in shown.changes()] == ["**allocation fixed\\_income 2 share** 20% → 25%"]
    store.write(data, [shown.edit()], source="form")
    text = path.read_text()
    assert "{age: 48, share: 0.1}\n    # bonds later\n    - {age: 62, share: 0.25}" in text


def test_an_override_is_checked_merged_into_the_assumptions(data: Path) -> None:
    form = forms.Form(
        "o", "scenarios/base.yaml", LUMP, Assumptions, keys=("overrides",), override=True
    )
    doc = read_yaml(data / form.file)
    found = form.problems(data, doc, {"inflation": {"stdev": -0.01}})
    assert [forms.explain(p) for p in found] == [
        "overrides.inflation.stdev: Input should be greater than or equal to 0"
    ]
    assert form.problems(data, doc, {"inflation": {"stdev": 0.01}}) == []


def test_a_label_can_be_replaced() -> None:
    form = replace(FORM, labels={("person", "rv_since"): "Insured since"})
    assert form.label(FIELDS[("person", "rv_since")]) == "Insured since"
    assert form.label(FIELDS[("tax", "pkv")]) == "PKV"


@pytest.mark.parametrize(
    ("model", "key", "value", "words"),
    [
        (Stream, "kind", "self_employed", "Self-employed profit"),
        (BuyPropertyEvent, "land", "NI", "Lower Saxony"),  # optional: `Land | None`
    ],
)
def test_a_choice_reads_in_words_and_the_file_keeps_its_value(
    model: type[BaseModel], key: str, value: str, words: str
) -> None:
    [field] = [f for f in fields.of(model) if f.path == (key,)]
    [column] = [c for c in gridcolumns.columns(model) if c.name == key]
    for found in (field, column):
        assert dict(found.titles)[value] == words
        assert value in found.options
    assert dict(FIELDS[("tax", "land")].titles)["BY"] == "Bavaria"


def test_a_new_row_names_a_problem_by_the_words_of_its_form() -> None:
    """The row is no line of the file yet: no key path, its type and id dropped, a check in plain
    words."""
    form = forms.Form(
        "add",
        "scenarios/a.yaml",
        tuple(fields.of(BuyPropertyEvent)),
        BuyPropertyEvent,
        keys=("events",),
        new={"type": "buy_property"},
        labels={("loan", "balance"): "Loan amount €"},
        plain={"of `land` and `transfer_tax`": "Choose one."},
    )
    said = [
        ("events[3]", "buy_property x: needs exactly one of `land` and `transfer_tax`"),
        ("events[3].loan.balance", "Input should be less than 0"),
        ("events[3].loan.rate", "Field required"),
    ]
    assert [form.explain(Problem("scenarios/a.yaml", None, *p)) for p in said] == [
        "Choose one.",
        "Loan amount: Input should be less than 0",
        "Loan · Rate: Field required",
    ]


SPENDING = """
from pathlib import Path
from dagobert.model.assumptions import Assumptions
from dagobert.ui import fields, forms, guard
data = Path({data!r})
found = tuple(f for f in fields.of(Assumptions) if f.path[0] == "spending")
nulls = {{("spending", "age_categories"): "Every category"}}
form = forms.Form("spending", "assumptions.yaml", found, Assumptions, nulls=nulls)
shown = forms.show(data, form)
forms.save(data, [shown], key="spending-save", flagged=guard.review(shown.changes(), key="s"))
"""


def test_an_empty_list_is_a_value_of_its_own(data: Path) -> None:
    """`age_categories: []` reaches no category, null every one."""
    at = AppTest.from_string(SPENDING.format(data=str(data)), default_timeout=30)
    at.run()
    next(t for t in at.toggle if t.label == "Use").set_value(True).run()
    next(t for t in at.toggle if t.label == "Every category").set_value(False).run()
    next(b for b in at.button if b.label.startswith("Save")).click().run()
    assert not at.exception
    spending = load_assumptions(data).spending
    assert spending is not None
    assert spending.age_categories == []
