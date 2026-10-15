"""The German catalogue against the code (rule `i18n`), for `scripts/i18n` and
`tests/test_i18n.py`: the extraction of the messages (`extract`, the Babel methods of `MAPPING`),
the write of the catalogue, its problems and the lint of the pages. No page imports it."""

from __future__ import annotations

import ast
import re
from collections import Counter
from importlib import import_module
from io import BytesIO
from pathlib import Path
from string import Formatter
from typing import TYPE_CHECKING

from babel.messages import Catalog, pofile
from babel.messages.extract import DEFAULT_KEYWORDS, extract_from_dir
from pydantic import BaseModel

from dagobert.i18n import DOMAIN, PACKAGE, Language, catalogue_path

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from typing import IO

    from babel.messages.catalog import Message


def write(catalogue: Catalog, lang: Language) -> None:
    """Sorted by file without line numbers, so a moved line changes nothing, and without the
    messages that the code dropped. The header names no address: Babel fills the empty ones with
    its templates (`EMAIL@ADDRESS`)."""
    catalogue.msgid_bugs_address = catalogue.last_translator = ""
    out = BytesIO()
    pofile.write_po(out, catalogue, ignore_obsolete=True, sort_by_file=True, include_lineno=False)
    catalogue_path(lang).write_bytes(out.getvalue())


# The modules whose words all go through the catalogue (`untranslated`), by path in the package:
# every module of the pages and of the report, also a new one
TRANSLATED = tuple(
    sorted(
        path.relative_to(PACKAGE).as_posix()
        for package in ("ui", "report")
        for path in (PACKAGE / package).glob("*.py")
    )
)
# Streamlit calls that show text, with the index of the positional argument that holds it, and
# their keywords of text
# fmt: off
SHOWN = dict.fromkeys((
    "title", "header", "subheader", "caption", "markdown", "text", "write", "error", "warning",
    "info", "success", "toast", "button", "download_button", "form_submit_button", "expander",
    "popover", "tabs", "dialog", "spinner", "metric", "text_input", "text_area", "number_input",
    "selectbox", "multiselect", "radio", "segmented_control", "pills", "toggle", "checkbox",
    "slider", "select_slider", "date_input", "file_uploader",
), 0) | {"page_link": 1}
# fmt: on
TEXT_KEYWORDS = frozenset({"label", "help", "placeholder", "caption", "body"})
ICON = re.compile(r":material/\w+:")
WORD = re.compile(r"[^\W\d_]")
# The Babel extractors by glob in the package, the first that matches a file: the words of the
# models (`schema`), the marks of the code
MAPPING = [("model/*.py", f"{__name__}:schema"), ("**.py", "python")]
KEYWORDS = DEFAULT_KEYWORDS | {"NP_": ((1, "c"), 2)}
# a conversion of Streamlit's sprintf: `'c` pads with the character c, which the flag `,` takes as
# the thousands separator (`%'.,.0f`, `money.GROUPED`)
SPRINTF = re.compile(r"%(?:'.|[-+ 0#,])*\d*(?:\.\d+)?[a-zA-Z%]")
FIELDS, CODE = Formatter(), "`[^`]*`"


def extract() -> Catalog:
    """The messages that the code marks (`_`, `N_`, `NP_`, `ngettext`, `pgettext`) and the words of
    the models (`schema`), with their files."""
    found = Catalog(domain=DOMAIN)
    for path, line, message, comments, context in extract_from_dir(
        PACKAGE, MAPPING, keywords=KEYWORDS
    ):
        found.add(message, locations=[(path, line)], auto_comments=comments, context=context)
    return found


def schema(
    fileobj: IO[bytes], keywords: object, comment_tags: object, options: object
) -> Iterator[tuple[int, str | None, str | tuple[str, str], list[str]]]:
    """A Babel extractor (`MAPPING`) of a module of `model/`: the words that the forms and the
    grids show of each model that it defines (`ui.fields.messages`), a key in the context `key`
    (`ui.gridcolumns.keyword`). The model itself stays English; the app imports Streamlit, so the
    import waits for an extraction."""
    del keywords, comment_tags, options
    from dagobert.ui.fields import messages  # noqa: PLC0415

    module = import_module(f"{__package__}.model.{Path(str(fileobj.name)).stem}")
    for model in vars(module).values():
        if (
            isinstance(model, type)
            and issubclass(model, BaseModel)
            and model.__module__ == module.__name__
        ):
            for context, text in messages(model):
                yield 0, "pgettext" if context else None, (context, text) if context else text, []


def _key(message: Message) -> tuple[str, str | None]:
    return (message.id if isinstance(message.id, str) else message.id[0]), message.context


def _forms(message: Message) -> list[tuple[str, str]]:
    """Each English form with the German one that stands for it."""
    ids = [message.id] if isinstance(message.id, str) else list(message.id)
    strings = [message.string] if isinstance(message.string, str) else list(message.string or ())
    return [(ids[min(i, len(ids) - 1)], s) for i, s in enumerate(strings)]


def _fields(text: str) -> Counter[str]:
    """The replacement fields of a `str.format` text, `{age}` and `{x:.1f}`."""
    return Counter(
        f"{name}!{conv}:{spec}" for _t, name, spec, conv in FIELDS.parse(text) if name is not None
    )


def _differences(message: Message, said: Mapping[str, str]) -> list[str]:
    """What a translation must keep of its English: the fields of `str.format`, the `%`
    conversions of a sprintf format (the context `sprintf`) and the code spans: a YAML key as it
    is, the name of a button as it is or as the catalogue says it (`said`: `Rename` is
    `Umbenennen`)."""
    found = []
    for english, german in (form for form in _forms(message) if form[1]):
        try:
            if _fields(english) != _fields(german):
                found.append("its str.format fields differ")
        except ValueError as err:
            found.append(f"its braces do not parse: {err}")
        if message.context == "sprintf" and SPRINTF.findall(english) != SPRINTF.findall(german):
            found.append("its % conversions differ")
        spans = Counter(re.findall(CODE, german))
        kept = [
            s if spans[s] or s[1:-1] not in said else f"`{said[s[1:-1]]}`"
            for s in re.findall(CODE, english)
        ]
        if Counter(kept) != spans:
            found.append("its `code` differs")
    return found


def _named(key: tuple[str, str | None]) -> str:
    msgid, context = key
    return f"{msgid!r} ({context})" if context else repr(msgid)


def problems(catalogue: Catalog, code: Catalog) -> list[str]:
    """Why `catalogue` does not serve `code`: a message that it lacks, holds without the code
    (stale or obsolete), leaves untranslated or fuzzy, or translates without its placeholders."""
    have = {_key(m): m for m in catalogue if m.id}
    need = {_key(m) for m in code if m.id}
    out = [f"{_named(k)}: not in the catalogue: run update" for k in need - have.keys()]
    out += [f"{_named(k)}: not in the code" for k in have.keys() - need]
    out += [f"{_named(_key(m))}: obsolete" for m in catalogue.obsolete.values()]
    said = {
        m.id: m.string
        for m in have.values()
        if isinstance(m.id, str) and isinstance(m.string, str) and not m.context
    }
    for key, message in have.items():
        if message.fuzzy:
            out.append(f"{_named(key)}: fuzzy, confirm the translation")
        if not all(german for _e, german in _forms(message)):
            out.append(f"{_named(key)}: not translated")
        out += [f"{_named(key)}: {why}" for why in _differences(message, said)]
    return sorted(out)


def _marked(tree: ast.Module) -> frozenset[str]:
    """The names that a module binds to a constant marked `N_` or `NP_`: English until `_()`,
    also in a tuple assignment."""

    def mark(value: ast.expr | None) -> bool:
        return isinstance(value, ast.Call) and getattr(value.func, "id", "") in {"N_", "NP_"}

    names: set[str] = set()
    for node in tree.body:
        match node:
            case ast.Assign(targets=targets, value=ast.Tuple(elts=values)):
                names |= {
                    t.id
                    for tuple_ in targets
                    if isinstance(tuple_, ast.Tuple) and len(tuple_.elts) == len(values)
                    for t, v in zip(tuple_.elts, values, strict=True)
                    if isinstance(t, ast.Name) and mark(v)
                }
            case ast.Assign(targets=targets, value=value) if mark(value):
                names |= {t.id for t in targets if isinstance(t, ast.Name)}
            case ast.AnnAssign(target=ast.Name(id=name), value=value) if mark(value):
                names.add(name)
    return frozenset(names)


def _english(node: ast.expr, marked: frozenset[str]) -> bool:
    """A text that shows English: a literal with words (an icon is none) or a constant of
    `marked`, also inside an f-string or a list and before `.format`."""
    match node:
        case ast.List(elts=items) | ast.Tuple(elts=items) | ast.JoinedStr(values=items):
            return any(_english(item, marked) for item in items)
        case (
            ast.FormattedValue(value=inner)
            | ast.Call(func=ast.Attribute(value=inner, attr="format"))
        ):
            return _english(inner, marked)
        case ast.Name(id=constant):
            return constant in marked
        case ast.Constant(value=str(text)):
            return bool(WORD.search(ICON.sub("", text)))
    return False


def untranslated(source: str, name: str) -> list[str]:
    """The lines of `source` where a Streamlit call shows English outside `_()`. A variable or an
    attribute that holds English (`ex.title`) passes: the German render test catches it."""
    out = []
    tree = ast.parse(source)
    marked = _marked(tree)
    calls = (node for node in ast.walk(tree) if isinstance(node, ast.Call))
    for call in sorted(calls, key=lambda c: (c.lineno, c.col_offset)):
        func = call.func
        shown = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if (at := SHOWN.get(shown)) is None:
            continue
        texts = [
            *call.args[at : at + 1],
            *(k.value for k in call.keywords if k.arg in TEXT_KEYWORDS),
        ]
        out += [
            f"{name}:{t.lineno}: words outside _() in {shown}" for t in texts if _english(t, marked)
        ]
    return out


def lint() -> list[str]:
    """`untranslated` over the modules of `TRANSLATED`."""
    return [
        line
        for path in TRANSLATED
        for line in untranslated((PACKAGE / path).read_text(encoding="utf-8"), path)
    ]
