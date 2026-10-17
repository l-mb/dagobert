"""The figures of the Explorer, kept as their JSON by what they show, for every session: a revisit
draws them without building them again and sends the same bytes, which the browser keeps."""

from __future__ import annotations

from typing import TYPE_CHECKING

import plotly.io
import streamlit as st

from dagobert.i18n import language
from dagobert.ui.runs import keep

if TYPE_CHECKING:
    from functools import partial

    import plotly.graph_objects as go

# the JSON of the figures that the process keeps: the Explorer of two scenarios takes about 2 MB
FIGURES_BYTES = 64 << 20


@st.cache_resource(show_spinner=False)
def _figures() -> dict[tuple[object, ...], str]:
    return {}


def kept(build: partial[go.Figure], *keys: object) -> go.Figure:
    """The figure of `build`, kept as its JSON, the least recently used out first beyond
    `FIGURES_BYTES`, by its builder, its keyword arguments (the nominal switch, phone or desktop),
    the language of the page and `keys`, which stand for its other arguments: the keys of its runs
    (`explorer.Ran.key`) and what else it shows: the key leaves out the positional arguments of
    `build`, so a caller that passes data without its key gets the figure of other data. A figure
    of `report.charts.figure` gives the same bytes from its JSON, so a revisit sends the bytes of
    the first draw."""
    found = _figures()
    key = (build.func, *keys, *sorted(build.keywords.items()), language())
    if (spec := found.get(key)) is not None:
        return plotly.io.from_json(keep(found, key, spec, FIGURES_BYTES, len))
    fig = build()
    keep(found, key, str(fig.to_json()), FIGURES_BYTES, len)
    return fig
