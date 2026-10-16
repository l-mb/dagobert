"""What a German render of a page checks: no text shows the English of a message that the catalogue
translates. And `edited`, the edits of a grid as a browser sends them over a language switch."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any, override

from dagobert import i18n

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from streamlit.testing.v1 import AppTest

# A page drawn alone in a test takes the language of the session first, as `main.py` does
ACTIVATE = "from dagobert import i18n, ui\ni18n.activate(ui.language())\n"


def edited(at: AppTest, key: str, state: dict[str, Any]) -> AppTest:
    """A run with the edits `state` in the grid `key` and the widgets as set, as a browser sends
    them: the API of `AppTest` sets no edits of a data editor. It drives the internals of
    `AppTest` in Streamlit 1.65 (`_tree.get_widget_states`, `_run`): check it after an upgrade."""
    grid = next(g for g in at.dataframe if g.key == key)
    states = at._tree.get_widget_states()
    states.widgets.add(id=grid.proto.id, string_value=json.dumps(state))
    return at._run(states)


# a percent written the English way: `36.6%`, `36.6 %`, `36%` (German `36,6 %`, rule `money`)
ENGLISH_PERCENT = re.compile(r"\d\.\d+\s?%|\d%")


def leaks(texts: Iterable[str], *, inside: bool = True) -> list[str]:
    """The texts that show English where the catalogue has German: a message as it is, or with
    `inside` one or more words inside a text (a page whose sentences stay English for now takes
    the message as it is only), and a percent written the English way. A message with a context
    (a key of the inputs, `Plan` of the navigation) is a word that a page may say in another
    sense: it does not count."""
    english = [
        m.id
        for m in i18n.read("de")
        if isinstance(m.id, str) and m.id and not m.context and m.string != m.id
    ]
    texts = list(texts)
    return [
        *(t for t in texts for e in english if t == e or (inside and " " in e and e in t)),
        *(t for t in texts if ENGLISH_PERCENT.search(t)),
    ]


def words(at: AppTest) -> list[str]:
    """The words of a run: titles, headings, captions, text, notices, labels, helps and
    placeholders of the widgets."""
    texts = [
        e.value
        for e in (*at.title, *at.header, *at.subheader, *at.caption, *at.markdown, *at.error)
    ]
    texts += [e.value for e in (*at.warning, *at.info, *at.success)]
    widgets = [
        *at.button,
        *at.button_group,
        *at.checkbox,
        *at.multiselect,
        *at.number_input,
        *at.radio,
        *at.selectbox,
        *at.slider,
        *at.text_area,
        *at.text_input,
        *at.toggle,
    ]
    texts += [w.label for w in widgets]
    texts += [h for w in widgets if (h := getattr(w, "help", None))]
    texts += [p for w in widgets if (p := getattr(w, "placeholder", None))]
    texts += [e.label for e in at.expander]
    texts += [t.label for t in at.tabs]
    texts += [p.proto.popover.label for p in at.get("popover")]
    return [str(t) for t in texts if t]


class _Text(HTMLParser):
    """The text of a page outside its scripts and styles, and its tips (`title`, `aria-label`)."""

    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []
        self.hidden = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.hidden = tag in {"script", "style"}
        self.texts += [v for k, v in attrs if k in {"title", "aria-label"} and v]

    @override
    def handle_endtag(self, tag: str) -> None:
        self.hidden = False

    @override
    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.texts.append(data.strip())


FIGURE = re.compile(r'<script type="application/json" id="data-[^"]*">(.*?)</script>', re.S)
# the fields of a plotly figure that a reader sees: titles, names, labels and hover texts
FIGURE_TEXT = frozenset(
    {"text", "name", "label", "hovertext", "hovertemplate", "ticktext", "customdata"}
)


def _figure_words(value: object, key: str = "") -> Iterator[str]:
    match value:
        case dict():
            for k, v in value.items():
                yield from _figure_words(v, str(k))
        case list():
            for v in value:
                yield from _figure_words(v, key)
        case str() if key in FIGURE_TEXT:
            yield from value.split("<br>")


def report_words(page: str) -> list[str]:
    """The words of an HTML report, each once: its text and tips, and the words of its figures
    line by line."""
    text = _Text()
    text.feed(page)
    figures = (w for m in FIGURE.finditer(page) for w in _figure_words(json.loads(m.group(1))))
    return sorted({*text.texts, *figures})
