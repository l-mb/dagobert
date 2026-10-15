"""The words of the app in the language of its viewer: gettext with Babel (rule `i18n`).

The English text is the msgid, `locale/de/LC_MESSAGES/dagobert.po` the one catalogue, compiled in
memory once per process. The language is a context variable: every session of the app runs in
threads of its own, and the report takes the language of `use`. The checks of the catalogue
against the code: `i18n_check`."""

from __future__ import annotations

import gettext
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Literal, LiteralString, get_args

from babel.core import negotiate_locale
from babel.messages import mofile, pofile

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from babel.messages import Catalog

Language = Literal["en", "de"]
LANGUAGES: tuple[Language, ...] = get_args(Language)
DOMAIN = "dagobert"
PACKAGE = Path(__file__).parent
_language: ContextVar[Language] = ContextVar("language", default="en")


def catalogue_path(lang: Language) -> Path:
    return PACKAGE / "locale" / lang / "LC_MESSAGES" / f"{DOMAIN}.po"


def read(lang: Language) -> Catalog:
    with catalogue_path(lang).open("rb") as fh:
        return pofile.read_po(fh, locale=lang, domain=DOMAIN)


@cache
def translations(lang: Language) -> gettext.NullTranslations:
    """The catalogue of `lang` compiled in memory, without its fuzzy entries; English as written."""
    if lang == "en":
        return gettext.NullTranslations()
    compiled = BytesIO()
    mofile.write_mo(compiled, read(lang))
    compiled.seek(0)
    return gettext.GNUTranslations(compiled)


def _(message: str) -> str:
    return translations(_language.get()).gettext(message)


def N_(message: LiteralString) -> LiteralString:  # noqa: N802
    """Marks a constant for the catalogue: `_()` translates it where it shows."""
    return message


def NP_(context: LiteralString, message: LiteralString) -> LiteralString:  # noqa: N802
    """Marks a constant for the catalogue in a context: `pgettext(context, …)` translates it where
    it shows, such as a sprintf format of a slider (`NP_("sprintf", "%.0f months")`)."""
    del context
    return message


def ngettext(singular: str, plural: str, n: int) -> str:
    return translations(_language.get()).ngettext(singular, plural, n)


def pgettext(context: str, message: str) -> str:
    """One English word with two German ones: `pgettext("navigation", "Plan")`."""
    return translations(_language.get()).pgettext(context, message)


def language() -> Language:
    return _language.get()


def activate(lang: Language) -> None:
    """The language of this thread from now on: `main.py` sets it first in every run."""
    _language.set(lang)


@contextmanager
def use(lang: Language) -> Iterator[None]:
    """The language `lang` inside the block, the one before it after."""
    token = _language.set(lang)
    try:
        yield
    finally:
        _language.reset(token)


def negotiate(tags: Iterable[str]) -> Language | None:
    """The first of `LANGUAGES` that language tags in the order of preference name: `de-CH` is
    `de`, `fr` is none."""
    found = negotiate_locale(
        [tag.strip().replace("_", "-").lower() for tag in tags], LANGUAGES, sep="-", aliases={}
    )
    return next((lang for lang in LANGUAGES if lang == found), None)


# a tag and its weight (RFC 9110: 0 to 1, three decimals at most): a malformed one weighs 1
ACCEPT = re.compile(
    r"([A-Za-z]{1,8}(?:-[A-Za-z0-9]{1,8})*|\*)\s*(?:;\s*q\s*=\s*([01](?:\.\d{0,3})?))?"
)


def preferred(header: str) -> list[str]:
    """The language tags of an `Accept-Language` header by weight, the first of equals first:
    `de-CH, de;q=0.9, en;q=0.8`. A weight of 0 refuses the tag."""
    weighted = [(float(q or 1), tag) for tag, q in ACCEPT.findall(header)]
    return [tag for q, tag in sorted(weighted, key=lambda w: -w[0]) if q > 0]
