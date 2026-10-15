"""The base of the input model: `Strict`, the unit of each number and date field (`units`), the
description and the label of a field."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from enum import StrEnum
from functools import cache
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    TypeAdapter,
    ValidationError,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, InitErrorDetails


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def refuse_all(model: BaseModel, found: list[InitErrorDetails]) -> None:
    """Raise `found`, the errors of an after-validator of `model`, as one `ValidationError`, if
    there are any."""
    if found:
        raise ValidationError.from_exception_data(type(model).__name__, found)


TITLES = "titles"  # the JSON schema key of the options of a `Titled` in words


class Titled(StrEnum):
    """A choice whose options read in words in the selects of the forms and grids (`titles`, in the
    JSON schema under `TITLES`): the file keeps the value."""

    @classmethod
    def titles(cls) -> dict[str, str]:
        return {}

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        found = handler.resolve_ref_schema(handler(core))
        found[TITLES] = cls.titles()
        return found


class Unit(StrEnum):
    """What a number or date field holds: the editors show and read it by its unit, which the
    JSON schema of the field carries (`units`). The files keep fractions and full dates."""

    EUR = "eur"
    PERCENT = "percent"  # a share or a rate, typed in percent: 2.5 for 0.025
    FACTOR = "factor"  # a multiplier: 1 leaves the amount as it is
    MONTHS = "months"  # a number of months
    YEARS = "years"  # an age
    NUMBER = "number"  # plain: a count, units of a security, m², Rentenpunkte, a correlation
    DATE = "date"  # a day
    MONTH = "month"  # a calendar month: any day reads as the first

    @property
    def step(self) -> float | None:
        """The finest step that an editor takes, in the unit shown. An `int` field steps by 1."""
        return {Unit.EUR: 0.01, Unit.PERCENT: 0.001}.get(self)


def unit(of: Unit) -> Any:  # noqa: ANN401 a `FieldInfo`, typed `Any` like `Field`
    """The marker of a field's unit, for `Annotated`."""
    return Field(json_schema_extra={"unit": of.value})


Euros = Annotated[float, unit(Unit.EUR)]
Percent = Annotated[float, unit(Unit.PERCENT)]
Factor = Annotated[float, unit(Unit.FACTOR), Field(ge=0)]
Months = Annotated[float, unit(Unit.MONTHS)]
Years = Annotated[float, unit(Unit.YEARS)]
Number = Annotated[float, unit(Unit.NUMBER)]
Day = Annotated[date, unit(Unit.DATE)]
Month = Annotated[
    date,
    AfterValidator(lambda d: d.replace(day=1)),
    unit(Unit.MONTH),
    Field(description="Any day of the month; the day is ignored"),
]
EACH = "*"  # in a key path of `units`: every key of a mapping, every item of a list
KeyPath = tuple[str, ...]


def units(of: Any) -> dict[KeyPath, Unit]:  # noqa: ANN401 a model or another type
    """The unit of every number and date field of the model or type `of` by key path, from its
    JSON schema. A discriminated union adds the tag of each member (`assets.*.term_deposit.start`),
    as a pydantic error location does. A number or date without a unit raises `TypeError`, unless
    it is a choice (`enum`)."""
    schema = TypeAdapter(of).json_schema()
    return dict(_units(schema, schema, ()))


def _units(
    spec: dict[str, Any], schema: dict[str, Any], path: KeyPath
) -> Iterator[tuple[KeyPath, Unit]]:
    if "$ref" in spec:
        spec = schema["$defs"][spec["$ref"].rsplit("/", 1)[1]]
    if "unit" in spec:
        yield path, Unit(spec["unit"])
        return
    inner = (
        [({"$ref": ref}, (*path, tag)) for tag, ref in tags.items()]
        if (tags := spec.get("discriminator", {}).get("mapping"))
        else [
            *((prop, (*path, name)) for name, prop in spec.get("properties", {}).items()),
            *((option, path) for option in spec.get("anyOf", [])),
            *(
                (spec[key], (*path, EACH))
                for key in ("items", "additionalProperties")
                if isinstance(spec.get(key), dict)
            ),
        ]
    )
    if not inner and "enum" not in spec and _dated_or_numeric(spec):
        msg = f"{'.'.join(path)}: a number or a date needs a unit"
        raise TypeError(msg)
    for sub, at in inner:
        yield from _units(sub, schema, at)


def _dated_or_numeric(spec: dict[str, Any]) -> bool:
    return spec.get("type") in {"number", "integer"} or spec.get("format") == "date"


@cache
def description(of: type[BaseModel], path: KeyPath) -> str:
    """The description of the field at `path` of the model `of`, on one line and without a final
    stop: the one text of a field that the editors and the explorer's sliders build their help
    from."""
    schema = of.model_json_schema()
    spec: dict[str, Any] = schema
    for key in path:
        spec = _model(spec, schema)["properties"][key]
    return " ".join(spec.get("description", "").split()).rstrip(".")


ACRONYMS = {
    "afa": "AfA",
    "bav": "bAV",
    "etf": "ETF",
    "kv": "KV",
    "kvdr": "KVdR",
    "pkv": "PKV",
    "rv": "RV",
    "sv": "SV",
    "vpw": "VPW",
}


def named(key: str) -> str:
    """A key of the inputs as a label: words apart, the first capital, an acronym as written:
    `bav_return` reads `bAV return`."""
    words = [ACRONYMS.get(w.lower(), w) for w in key.replace("_", " ").replace("-", " ").split()]
    first = words[0] if words else ""
    return " ".join(
        [first if first in ACRONYMS.values() else first[:1].upper() + first[1:], *words[1:]]
    )


def _model(spec: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """The model of a field, of an optional one the member that is no null."""
    for option in spec.get("anyOf", [spec]):
        found: dict[str, Any] = (
            schema["$defs"][option["$ref"].rsplit("/", 1)[1]] if "$ref" in option else option
        )
        if "properties" in found:
            return found
    msg = f"no model in {spec}"
    raise KeyError(msg)


def exactly_one(*present: bool) -> bool:
    return sum(present) == 1
