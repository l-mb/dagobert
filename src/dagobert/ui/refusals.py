"""Why the model refuses a row of a stream grid, in words at its grid before the save: the row,
the fields as the grid heads them, what to enter. The problem of the inputs stays English
(`problems.InputError`, the command line and the `Not saved:` of a save); a page says the checks
of `model.streams.Stream` by their type."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from dagobert.i18n import N_, _, ngettext
from dagobert.model.streams import Stream, StreamKind
from dagobert.ui import guard, joined, literal
from dagobert.ui.gridcolumns import Row, columns, default_said, keywords, units

# What to do, per type of a check of `Stream`: `{kind}` the kind of the row in words, `{field}`
# the field that it needs, any other name the field of that key, as the grid heads it
SAID = {
    "deductible": N_(
        "{deductible} needs {health} or {deduct}: fill one of them, or empty {deductible}"
    ),
    "deduct": N_("{deduct} takes no {health} and no {property}: empty one of them"),
    "repays": N_("{repays} needs null in {index}"),
    "let_health": N_(
        "a cost of a let property ({property}) is no health premium ({health}): empty one of them"
    ),
    "let_taxable": N_("the rent of a property is taxable: tick {taxable}"),
    "bonus": N_("a bonus needs both {of} and {share}: fill the other one, or empty both"),
    "bonus_gross": N_("a bonus takes its amount from {of} and {share}: empty {gross}"),
    "course": N_("a course takes no {sperrzeit}: tick it on the ALG1 row before the course"),
    "contract": N_("a BU policy runs by its contract: set every phase to 1 and {every} to 1"),
    "pension": N_("enter either {gross} or {points} with {point_value}"),
    "needs": N_("enter {field}"),
    "outflow": N_(
        "the kind {kind} is money out: enter {amount} with a minus, or choose another kind"
    ),
    "benefit": N_("enter {amount} as 0 or more"),
}
# a bound of a field (pydantic), by its type: its key in the context and what to do
BOUNDS = {
    "less_than_equal": ("le", N_("enter {field} of at most {limit}")),
    "greater_than_equal": ("ge", N_("enter {field} of at least {limit}")),
    "less_than": ("lt", N_("enter {field} below {limit}")),
    "greater_than": ("gt", N_("enter {field} above {limit}")),
}
UNITS = units(columns(Stream))  # a bound shows in the unit of its field: 100% for a share
# a value that the field cannot read, by the end of the type of pydantic (`date_parsing`)
UNREAD = ("_parsing", "_type")
NEW_ROW = N_("new row")


def refusals(rows: Iterable[Row], titles: Mapping[str, str] | None = None) -> list[str]:
    """Why the model refuses each of `rows`, in the language of the session: the row by its name,
    the fields as its grid heads them (`titles`, the English of `Table.titles`, else the key in
    words) and what to enter, a bound in the unit of its field (`BOUNDS`). Any other error as
    the model writes it, after its field."""
    found: list[str] = []
    for row in rows:
        try:
            Stream.model_validate(row)
        except ValidationError as err:
            named = guard.label(row) or _(NEW_ROW)
            found += [
                f"**{literal(named)}**: {_said(e, titles or {})}"
                for e in err.errors(include_url=False)
            ]
    return found


def _said(error: ErrorDetails, titles: Mapping[str, str]) -> str:
    def header(key: object) -> str:
        return f"`{_(titles[str(key)]) if key in titles else keywords(str(key))}`"

    # no literal inside `_()`: Babel would take it for a message
    check, context = error["type"], error.get("ctx", {})
    words = {key: header(key) for key in Stream.model_fields}
    if "field" in context:
        words["field"] = header(context["field"])
    if (named := context.get("kind")) is not None:
        title = StreamKind.titles()[str(named)]
        words["kind"] = _(title)
    if check == "kind":
        odd = str(context["fields"]).split(", ")
        return ngettext(
            "{fields} does not belong to the kind {kind}: empty it, or choose another kind",
            "{fields} do not belong to the kind {kind}: empty them, or choose another kind",
            len(odd),
        ).format(fields=joined(map(header, odd)), kind=words["kind"])
    if check == "missing" and error["loc"]:  # a field left empty
        check, words["field"] = "needs", header(error["loc"][0])
    if (said := SAID.get(check)) is not None:
        return _(said).format(**words)
    field = error["loc"][:1]  # a field, or an entry of a mapping by its field
    if check.endswith(UNREAD) and field:
        return _("{field} holds no value that it can read: enter it again").format(
            field=header(field[0])
        )
    if check in BOUNDS and field:
        bound, text = BOUNDS[check]
        limit = default_said(context[bound], UNITS.get(str(field[0])))
        return _(text).format(field=header(field[0]), limit=limit)
    return ": ".join([*map(header, field), error["msg"]])
