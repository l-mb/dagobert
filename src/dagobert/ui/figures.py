"""The figures of the Explorer, kept as their JSON by what they show, for every session: a revisit
draws them without building them again and sends the same bytes, which the browser keeps. And the
lines that the viewer hid in their legends, which each new figure hides again."""

from __future__ import annotations

from typing import TYPE_CHECKING

import plotly.io
import streamlit as st
from streamlit.components import v2

from dagobert.i18n import language
from dagobert.ui import chart
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


# the lines hidden in the legends of the page, by the key of their chart: Streamlit 1.65 mounts a
# new chart for each new figure (its element id hashes the figure, also with a key), so plotly
# forgot them at each move of a slider. The state of the component `_KEEPER`, `{"hidden": {key:
# [name, ...]}}`, which a click on a legend sets: a rerun (`keep_hidden`)
HIDDEN = "explorer-hidden"
# a script of the page (components v2, the DOM of Streamlit 1.65: check it after an upgrade): each
# chart of a container `st-key-<key>` reports the names of its hidden lines after a restyle, as a
# click on its legend makes; `data` holds those that the page knows, which it adds to
_SCRIPT = """
export default function ({ data, setStateValue }) {
  const held = (window.dagobertHidden ??= {});
  held.known = data ?? {};
  held.set = setStateValue;
  const hook = () => {
    for (const gd of document.querySelectorAll('[class*="st-key-"] .js-plotly-plot')) {
      if (gd.dagobertHooked || !gd.on) continue;
      gd.dagobertHooked = true;
      gd.on('plotly_restyle', () => {
        const box = gd.closest('[class*="st-key-"]');
        const key = [...box.classList].find((c) => c.startsWith('st-key-')).slice(7);
        const names = gd._fullData.filter((t) => t.visible === 'legendonly').map((t) => t.name);
        held.set('hidden', { ...held.known, [key]: names });
      });
    }
  };
  hook();
  const observer = new MutationObserver(hook);
  observer.observe(document.body, { childList: true, subtree: true });
  return () => observer.disconnect();
}
"""


def _hidden() -> dict[str, list[str]]:
    held = st.session_state.get(HIDDEN)
    return dict(held["hidden"]) if held else {}


def keep_hidden() -> None:
    """The script that keeps the lines hidden in the legends (`_SCRIPT`), once per run before the
    charts: it hooks every chart of the page. Its box takes no room (`ui/page.css`). Registered in
    each run, as each runtime holds its own registry (an `AppTest` too); the same definition again
    is no change."""
    keeper = v2.component("dagobert_hidden_lines", js=_SCRIPT)
    keeper(key=HIDDEN, data=_hidden(), default={"hidden": {}}, on_hidden_change=lambda: None)


def draw(fig: go.Figure, *, key: str) -> None:
    """`ui.chart` of `fig` with the lines that the viewer hid in the legend of the chart `key`
    hidden (`keep_hidden`), by their names: a language switch shows them again."""
    names = set(_hidden().get(key, ()))
    for trace in fig.data:
        if getattr(trace, "name", None) in names:
            trace.visible = "legendonly"  # pyright: ignore[reportAttributeAccessIssue]
    chart(fig, key=key)
