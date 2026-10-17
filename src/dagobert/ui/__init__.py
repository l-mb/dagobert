"""The Streamlit app: the helpers that every page shares."""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import reduce
from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Literal, overload
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import streamlit as st

from dagobert import i18n, revisions, schema, series
from dagobert.cache import RUN_INPUTS
from dagobert.i18n import N_, _
from dagobert.loader import load_scenario
from dagobert.model.months import months_of_age
from dagobert.transfer import UPLOAD_MB
from dagobert.ui import gridstate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
    from datetime import tzinfo

    import plotly.graph_objects as go
    from streamlit.delta_generator import DeltaGenerator
    from streamlit.elements.plotly_chart import PlotlyState

# Set by `main.py` on every script run. `dagobert app` runs the server in the process of the
# CLI, so the CLI sees here whether a browser tab has connected.
session_seen = threading.Event()

# One value per server process. A tab that reconnects after a restart sees a new value
# and reloads itself, see `main.py`.
BOOT = str(time.time_ns())

# the words, a message of the catalogue, and the multiplier
PER = {"month": (N_("per month"), 1), "year": (N_("per year"), 12)}
# the help of `step_button` by the unit of its steps, back and forth
STEPS = {
    "month": (N_("Previous month"), N_("Next month")),
    "year": (N_("Previous year"), N_("Next year")),
}
HOW_TO_READ = N_("How to read this")  # the label of a folded help (`fold`, `note`)
# the total row of an `st.table` on a pandas `Styler`
TOTAL = "font-weight: 700; border-top: 2px solid #9aa4b2; "
# money in and money out in green and red, at least 4.5:1 on the light and the dark theme
GAIN, LOSS = "light-dark(#127a56, #199e70)", "light-dark(#b92d2d, #e5605d)"
# pixels left and right of the page content, instead of 80: the wide stream grids need the room
SIDE_PADDING = 16
PAGE_STYLE = (
    "<style>"
    + Template(Path(__file__).with_name("page.css").read_text(encoding="utf-8")).substitute(
        side=f"{SIDE_PADDING}px"
    )
    + "</style>"
)
# Streamlit 1.65 writes the words of its file uploader in English: another language writes them by
# CSS on their elements (the DOM of 1.65: check it after an upgrade), the English at a size of 0
# and the words of the catalogue after it at the size of Streamlit. The button, the words while a
# file is dragged over it, and the limit, without the types of files, which its label names.
# English keeps the words of Streamlit (`:lang(en)`, which the boot script of `main.py` sets).
UPLOADER_WORDS = Template(
    "<style>"
    "$zone button [data-testid=stMarkdownContainer] p, $zone > div:not([data-testid]) > span, "
    "$zone [data-testid=stFileUploaderDropzoneInstructions] span { font-size: 0; }"
    '$zone button [data-testid=stMarkdownContainer] p::after { content: "$upload"; }'
    '$zone > div:not([data-testid]) > span::after { content: "$drop"; }'
    '$zone [data-testid=stFileUploaderDropzoneInstructions] span::after { content: "$limit"; }'
    "$zone :is(p, span)::after { font-size: 0.875rem; }"
    "</style>"
)


def uploader_words() -> str:
    """The style of `UPLOADER_WORDS` in the language of the session, which `main.py` draws in
    every run."""
    return UPLOADER_WORDS.substitute(
        zone="html:not(:lang(en)) [data-testid=stFileUploaderDropzone]",
        upload=_("Upload"),
        drop=_("Drag and drop a file here"),
        limit=_("{mb} MB per file").format(mb=UPLOAD_MB),
    )


UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})  # spelled out in a `slug`
MOBILE = "ui-mobile"  # session state: the `mobile` query of this session
PAGE = "ui-page"  # session state: the title of the page that runs, set by `main.py`
CAME = "ui-came"  # session state: the title of the page of the run before, set by `main.py`
# session state: the `st.Page`s of the navigation by title, None where it leaves one out (the
# mode and the features), set by `main.py`
PAGES = "ui-pages"
# The query of a link to the Scenarios page: `?scenario=plan` opens a scenario, `&event=sell` on
# the type of its `Events` tab, `&tab=Phases` on another tab; `?main=open` opens the choice of the
# main scenario on a phone.
SCENARIO, EVENT, TAB, MAIN = "scenario", "event", "tab", "main"
# The query of a link to the Explorer: `?compare=buy-home` runs the scenario with the nearest one
# that it extends, and the difference of the two
COMPARE = "compare"
# the selections of the pages that hold a stem or an asset: they follow a rename and a delete
# (`fileactions.FOLLOW`, `rename.FOLLOW`)
CASHFLOWS_SCENARIO, FLOWS_SCENARIO = "cashflows-scenario", "flows-scenario"
SECURITIES_ASSET = "securities-asset"
# On a phone a chart keeps only Streamlit's Fullscreen: zoom and pan would trap the finger again.
PHONE_MODEBAR = {
    "modeBarButtonsToRemove": [
        "zoom2d",
        "pan2d",
        "zoomIn2d",
        "zoomOut2d",
        "autoScale2d",
        "resetScale2d",
        "toImage",
    ]
}


def is_mobile() -> bool:
    """A phone: `Mobile` in the user agent, unless the URL held `mobile=1` or `mobile=0` in this
    session. A page switch drops the query, so the session keeps it."""
    if (forced := st.query_params.get("mobile")) is not None:
        st.session_state[MOBILE] = forced == "1"
    return bool(st.session_state.get(MOBILE, "Mobile" in st.context.headers.get("User-Agent", "")))


LANGUAGE = "ui-language"  # session state, the key of the switch: the language of the session
CHOSEN = "ui-language-chosen"  # session state: the viewer chose the language on the switch
COOKIE = "dagobert-lang"  # the language that the viewer chose last, for the next visit
LANGUAGE_LABEL = ":material/translate: Sprache · Language"  # in both: found in the wrong one
ENDONYMS: dict[i18n.Language, str] = {"en": "English", "de": "Deutsch"}
# 400 days, the most that Chrome keeps; `path=/` for every page under a base URL path
SET_COOKIE = Template(
    '<script>document.cookie = "$cookie=$value; path=/; max-age=34560000; SameSite=Lax";</script>'
)


def language() -> i18n.Language:
    """The language of this session: `?lang=de` or `en` (tests and links; taken once, so the
    switch can change it), the language switch (`language_switch`), the cookie of an earlier
    choice, the language of the browser, its `Accept-Language` header, English."""
    lang = (
        i18n.negotiate([st.query_params.pop("lang", "")])
        or i18n.negotiate([str(st.session_state.get(LANGUAGE, ""))])
        or i18n.negotiate(
            [
                st.context.cookies.get(COOKIE, ""),
                st.context.locale or "",
                *i18n.preferred(st.context.headers.get("Accept-Language", "")),
            ]
        )
        or "en"
    )
    st.session_state[LANGUAGE] = lang
    return lang


def chose(chosen: str) -> None:
    """A choice on a switch of the viewer (`language_switch`, `mode.mode_switch`), noted in the
    session state `chosen` for its cookie (`remember`). The editable grids then take other words
    or columns: Streamlit keys a dynamic editor by its column config too and draws a new one,
    which would show the rows without their unsaved edits, so the edits move into the new grids
    (`gridstate.carry`)."""
    st.session_state[chosen] = True
    gridstate.carry(st.session_state.pop(gridstate.DRAWN, {}))


def remember(cookie: str, chosen: str, value: str) -> None:
    """The `value` of a switch in the `cookie` for the next visit, once the viewer chose it
    (`chosen`): Streamlit sets no cookie and reads those of the first request only, so a script
    writes it, in every run of the session after the choice."""
    if st.session_state.get(chosen):
        script = SET_COOKIE.substitute(cookie=cookie, value=value)
        st.sidebar.html(script, unsafe_allow_javascript=True)


def language_switch() -> None:
    """The language switch at the end of the sidebar. A choice persists in a cookie."""
    st.sidebar.segmented_control(
        LANGUAGE_LABEL,
        i18n.LANGUAGES,
        format_func=ENDONYMS.__getitem__,
        key=LANGUAGE,
        required=True,
        on_change=chose,
        args=(CHOSEN,),
    )
    remember(COOKIE, CHOSEN, st.session_state[LANGUAGE])


def arrived() -> bool:
    """Whether this run opens its page: from another page, by a link or the navigation, or anew.
    A rerun of the page, also after a save or a switch of the language, does not."""
    return bool(st.session_state.get(CAME) != st.session_state.get(PAGE, "app"))


def source(action: str = "") -> str:
    """The source of a write of this page in the revision log: its title, and `action` when the
    page writes more than one thing, `Overview: roll forward`. A page drawn alone, as in a test,
    is `app`."""
    page = str(st.session_state.get(PAGE, "app"))
    return f"{page}: {action}" if action else page


def page_said(source: str, *, action: bool = True) -> str:
    """A source of the revision log in the language of the session: the title of a page of the
    navigation translated, the action after it as written (`Annahmen: Markets`; without `action`
    the page alone), any other source (`import x.zip`, a page drawn alone) as it is. The log keeps
    the English."""
    page, colon, done = source.partition(": ")
    if page not in st.session_state.get(PAGES, {}):
        return source
    return f"{_(page)}{colon}{done}" if action else _(page)


def day_said(day: revisions.Day) -> str:
    """A day of the revisions in a select, its sources in words: a page of the navigation
    (`page_said`), an edit outside the app."""
    return day.said(
        lambda source: _("outside the app") if source == revisions.OUTSIDE else page_said(source)
    )


def page_link(
    title: str,
    label: str,
    query: Mapping[str, str] | None = None,
    *,
    icon: str = ":material/arrow_forward:",
) -> None:
    """A link to the page `title` of the navigation, with the query parameters `query`: the
    `st.Page` that `main.py` registers (`PAGES`). Streamlit finds a page by the hash of its
    `url_path`, so a page built again for a link could miss it without an error. A page drawn
    alone, as in a test, has no navigation and shows no link."""
    if (page := st.session_state.get(PAGES, {}).get(title)) is not None:
        st.page_link(page, label=label, icon=icon, query_params=dict(query) if query else None)


# Month labels (`%Y-%m` at 14 px) that fit across a chart without a turn: at 1,500 px with the
# sidebar open by the number of columns that share the page, and on a phone in portrait.
DESKTOP_MONTHS = {1: 20, 2: 9}
PHONE_MONTHS = 5


def month_labels(columns: int = 1) -> int:
    """The month labels that fit across a chart in one of `columns` columns."""
    return PHONE_MONTHS if is_mobile() else DESKTOP_MONTHS[columns]


@overload
def chart(fig: go.Figure, *, key: str) -> None: ...


@overload
def chart(fig: go.Figure, *, key: str, on_select: Literal["rerun"]) -> PlotlyState: ...


def chart(
    fig: go.Figure, *, key: str, on_select: Literal["rerun", "ignore"] = "ignore"
) -> PlotlyState | None:
    """Every chart of the app. On a phone a swipe over it scrolls the page (no drag mode) and
    its toolbar keeps only Fullscreen. A selection picks points. Streamlit turns the drag mode
    of a selecting chart into pan, so such a chart still holds the finger."""
    config = {}
    if is_mobile():
        fig.update_layout(dragmode=False)
        # without the drag mode a tap counts twice, touch and mouse: a double click resets the axes
        config = PHONE_MODEBAR | {"doubleClick": False}
    if on_select == "ignore":
        st.plotly_chart(fig, key=key, config=config)
        return None
    return st.plotly_chart(
        fig, key=key, config=config, on_select=on_select, selection_mode="points"
    )


TOLD = "ui-told"  # session state: the toasts of a save, for the run after its `st.rerun`


@dataclass(frozen=True)
class Outcome:
    """What a fetch, an import or a save did, kept for the run after its `st.rerun`."""

    ok: bool
    text: str


@dataclass(frozen=True)
class Toast:
    text: str
    warn: bool  # a warning icon, and it stays longer


def tell(text: str, *, warn: bool = False) -> None:
    """A toast for the next run, which `main.py` shows first (`told`): one shown before
    `st.rerun` or `st.switch_page` is lost (Streamlit 1.65), so a save that reruns the page said
    nothing."""
    st.session_state.setdefault(TOLD, []).append(Toast(text, warn))


def told() -> None:
    """The toasts that `tell` keeps, once."""
    for toast in st.session_state.pop(TOLD, []):
        st.toast(
            toast.text,
            icon=":material/warning:" if toast.warn else ":material/check:",
            duration="long" if toast.warn else "short",
        )


SAVED = "ui-saved"  # session state: the last save of the session, which `undo.line` offers


@dataclass(frozen=True)
class Saved:
    """The last save of a session: its revision, and of an undo the revision that it took back."""

    id: str
    undid: str | None = None


@contextmanager
def recording() -> Iterator[None]:
    """Keep the last revision that the block writes as the save of the session (`SAVED`), also
    when the block ends by `st.rerun`: `main.py` around a page, a dialog around its write (it
    reruns alone, without `main.py`). An undo inside it keeps the `Saved` that names what it took
    back."""
    with revisions.recorded() as written:
        try:
            yield
        finally:
            kept: Saved | None = st.session_state.get(SAVED)
            if written and (kept is None or kept.id != written[-1].id):
                st.session_state[SAVED] = Saved(written[-1].id)


def fold(text: str, label: str | None = None) -> None:
    """A long caption folded into a collapsed expander, on every device: `How to read this`
    without a `label`."""
    st.expander(label or _(HOW_TO_READ), icon=":material/info:").markdown(text)


def note(text: str, label: str | None = None) -> None:
    """A long caption: as is on a desktop, folded on a phone (`fold`)."""
    if is_mobile():
        fold(text, label)
    else:
        st.caption(text)


# characters: about three lines of a caption on a phone in portrait (380 px at 14 px). A shorter
# note takes no more room than the header of an expander.
SHORT_NOTE = 160


def joined(texts: Iterable[str]) -> str:
    """`texts` joined by `and` in the language of the session, as English joins two: `a and b and
    c`."""
    both = _("{first} and {then}")
    return reduce(lambda first, then: both.format(first=first, then=then), texts)


def literal(text: str) -> str:
    """`text` as it is in Markdown: no emphasis, link, code, LaTeX, heading, list or rule."""
    marked = re.sub(r"([\\`*_\[\]<>$~|#])", r"\\\1", text)
    return re.sub(r"(?m)^(\s*)(?:([-+=])|(\d+)([.)]))", r"\1\3\\\2\4", marked)


def scenario_note(text: str) -> None:
    """The `note` of a scenario as a caption, as written, a long one folded on a phone (`note`)."""
    if len(text) > SHORT_NOTE:
        note(literal(text), _("About the scenario"))
    elif text:
        st.caption(literal(text))


# The keyboard of a phone for the text fields by the start of their key. `decimal-`: the decimal
# keypad, as a number field would read `,` and `.` by the language of the browser (`20,50`
# becomes 2050 in English). `nocaps-`: no capital first letter, so a typed category matches.
KEYBOARD = """<script>
if (!window.dgKeys) {
  const keys = () => {
    document.querySelectorAll('[class*="st-key-decimal-"] input')
      .forEach((input) => { input.inputMode = "decimal"; });
    document.querySelectorAll('[class*="st-key-nocaps-"] input')
      .forEach((input) => { input.setAttribute("autocapitalize", "none"); });
  };
  window.dgKeys = new MutationObserver(keys);
  window.dgKeys.observe(document.body, {childList: true, subtree: true});
  keys();
}
</script>"""


def at_age(month: date, born: date | None) -> str:
    """A month with the age then in whole years, `2051-06 (age 65)`, the month alone without a
    date of birth: the month sliders of the Explorer, the phase changes of a scenario."""
    if born is None:
        return f"{month:%Y-%m}"
    return _("{month} (age {age})").format(
        month=f"{month:%Y-%m}", age=months_of_age(born, month) // 12
    )


def titled(stem: str, name: object) -> str:
    """A scenario in a select: `stem · name`, the stem alone where the name is the same."""
    return stem if not name or name == stem else f"{stem} · {name}"


def scenario_titles(concrete: Mapping[str, Path], main: str) -> dict[str, str]:
    """The scenarios that run (`scenariofiles.concrete_scenarios`) as their selects show them, the
    `main` one marked (`main_marked`)."""
    return main_marked(
        {stem: titled(stem, load_scenario(path).name) for stem, path in concrete.items()}, main
    )


def main_marked(shown: Mapping[str, str], main: str) -> dict[str, str]:
    """The words of each scenario in a select by stem, the `main` one
    (`scenariofiles.first_scenario`) marked `(main)`."""
    return {**shown, main: _("{scenario} (main)").format(scenario=shown[main])}


def slug(name: str) -> str:
    """The name of a file or an id that a name gives: lower case, umlauts spelled out, a dash for
    anything else, so the store takes it (`Früh in Rente!` gives `frueh-in-rente`)."""
    text = unicodedata.normalize("NFKD", name.lower().translate(UMLAUTS))
    return re.sub(r"[^a-z0-9]+", "-", text.encode("ascii", "ignore").decode()).strip("-")


def keyboard() -> None:
    st.html(KEYBOARD, unsafe_allow_javascript=True)


# The files that a cache of what the inputs give follows: the YAML inputs and the fetched series
STAMPED = (*(p for p in schema.INPUTS if p.endswith(".yaml")), f"{series.FETCHED}/*.csv")


type Stamp = tuple[int, int, int]


def data_stamp(data_dir: Path, inputs: Sequence[str] = STAMPED) -> Stamp:
    """The sums of the mtimes (ns) and of the sizes and the number of the files of `inputs`: a
    cache key that changes when one is changed, added or removed. A write after the read of a time
    takes a later one, but maybe the time of another file: the latest time missed such an edit;
    two writes within one tick of the clock of the kernel keep the time, mostly not the size."""
    stats = [p.stat() for pattern in inputs for p in data_dir.glob(pattern)]
    return sum(s.st_mtime_ns for s in stats), sum(s.st_size for s in stats), len(stats)


def run_stamp(data_dir: Path) -> Stamp:
    """The `data_stamp` of what a run reads (`cache.RUN_INPUTS`): the cache key of the runs and of
    what they give, which a save of `app.yaml` keeps."""
    return data_stamp(data_dir, RUN_INPUTS)


def timezone() -> tzinfo:
    """The time zone of the browser, UTC without one: the days of the revisions."""
    try:
        return ZoneInfo(st.context.timezone or "UTC")
    except ZoneInfoNotFoundError, ValueError:
        return UTC


def since(data_dir: Path, files: Callable[[str], bool]) -> dict[revisions.Day, str]:
    """The local days with a revision of `files`, newest first, each with the last revision
    before it began: the inputs that the changes of that day and after it apply to. A day
    without an earlier revision, such as the one of the baseline, drops out."""
    log, tz = revisions.entries(data_dir), timezone()
    found = (
        (day, revisions.before(log, datetime.combine(day.day, datetime.min.time(), tz)))
        for day in revisions.days(log, selected=files, tz=tz)
    )
    return {day: base for day, base in found if base is not None}


def per_control(column: DeltaGenerator, key: str) -> tuple[str, int]:
    """The "Amounts" segmented control (`per month`/`per year`): its words, in English (a message
    of the catalogue: `_()` where they show), and its multiplier."""
    per = column.segmented_control(
        _("Amounts"),
        list(PER),
        format_func=lambda option: _(PER[option][0]),
        default="month",
        required=True,
        key=key,
        wrap=True,
        help=_("Every amount per month, or 12 times that per year."),
    )
    return PER[per]


def _step(key: str, options: Sequence[object], by: int, after: Callable[[], None] | None) -> None:
    st.session_state[key] = options[options.index(st.session_state[key]) + by]
    if after:
        after()


def step_button(
    key: str,
    options: Sequence[object],
    by: int,
    unit: Literal["month", "year"],
    *,
    after: Callable[[], None] | None = None,
) -> None:
    """A chevron that moves the widget `key` to the previous (`by` -1) or the next of its
    `options`, off at the end; its help names the `unit` (`STEPS`). `after` runs after the
    step."""
    back = by < 0
    st.button(
        ":material/chevron_left:" if back else ":material/chevron_right:",
        key=f"{key}-{'back' if back else 'next'}",
        help=_(STEPS[unit][0 if back else 1]),
        on_click=_step,
        args=(key, options, by, after),
        disabled=not 0 <= options.index(st.session_state[key]) + by < len(options),
    )
