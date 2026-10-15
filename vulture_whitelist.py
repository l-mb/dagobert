"""The names that vulture takes for unused, as a library uses them by name. `uvx vulture` reads
the paths and the ignored decorators from `pyproject.toml`."""

from ruamel.yaml import YAML

from dagobert.model.base import Strict
from dagobert.model.taxes import Land

yaml = YAML()
_ = (
    Strict.model_config,  # pydantic
    yaml.preserve_quotes,  # ruamel.yaml: `files.yaml`
    yaml.representer.ignore_aliases,
    yaml.allow_duplicate_keys,  # `problems.with_lines`
    # the options of a select, read from the files by value
    *(Land.BW, Land.BY, Land.BE, Land.BB, Land.HB, Land.HH, Land.HE, Land.NI, Land.MV),
    *(Land.NW, Land.RP, Land.SL, Land.SN, Land.ST, Land.SH, Land.TH),
)
