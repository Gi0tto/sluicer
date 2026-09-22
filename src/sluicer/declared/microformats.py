"""Read microformats2, the vocabulary a page writes into its class attributes.

``<article class="h-entry">`` with ``<h1 class="p-name">`` inside it is a page
declaring an entry and its title, in the same markup that styles them. Parsing
it is not a job for a handful of XPath expressions the way Dublin Core or RDFa
Lite are: the rules cover implied properties, value-class patterns, backcompat
with the 2005 vocabularies and a prefix table that decides what a property's
value even is. ``mf2py`` is the reference implementation of those rules and it
is what this module calls.

That is why this reader, alone among the seven, sits behind an extra. A clean
environment holding ``mf2py`` and nothing else holds twelve packages, measured
on 2026-09-22, against a base install of three; a reader who never asks for
microformats should not carry the other nine. ``extract`` therefore takes
``microformats=False`` and this module imports nothing until it is called.

**What it is worth, stated honestly.** ``mf2py`` takes 531,588 installs a month,
so the demand is real, but across twenty live pages measured on 2026-09-22
microformats appeared on exactly one -- and that page carried OpenGraph too, so
it was already readable. This reader does not make Sluicer read more of the web.
What it buys is compatibility with ``extruct``, which reads six vocabularies and
has not shipped in 683 days.

Microformats describes a *thing* -- an entry, a card, a product -- and not the
document around it, so it is named in ``sluicer.api.ABOUT_A_THING`` and a page
whose only declaration is an ``h-entry`` has declared something about its own
subject.
"""

from __future__ import annotations

import warnings
from types import ModuleType
from typing import Any

from sluicer.document import Document
from sluicer.extras import MissingExtra, import_extra


class MicroformatsExtraMissing(MissingExtra):
    """The optional ``microformats`` extra (mf2py) is not installed.

    A name of its own, so a caller who turned ``microformats=True`` on can
    catch exactly this and print the install line instead of a traceback. What
    "missing" means, and why a broken install keeps its traceback instead, is
    stated once in ``sluicer.extras``.
    """


def _mf2py() -> ModuleType:
    """Import mf2py, or say the extra is not installed."""
    return import_extra(
        "mf2py",
        "microformats",
        doing="Reading microformats",
        error=MicroformatsExtraMissing,
    )


def read_microformats(doc: Document) -> list[dict[str, str]]:
    """Return one flat dict per top-level microformat item on the page.

    ``mf2py`` returns a tree; a record here is flat, so each top-level item
    becomes one dict: ``@type`` from the first class it declares, kept verbatim
    as the page spelled it (``h-entry``, not ``entry``), and one key per
    property.

    Every property's value is a list even when the page declared one of them,
    and the first element is what is kept. A second ``p-category`` is dropped:
    a record maps one name to one value, and a list-valued field would be a
    second kind of record for every caller to handle.

    **A nested item is a name and an address, and both are kept.** An ``author``
    is not a string but an ``h-card`` -- its name at ``properties["name"][0]``,
    its link at ``properties["url"][0]`` -- and this is the problem
    ``sluicer.structure.records`` already faced with an anchor. Its convention
    is followed exactly: the name takes the slot's own name and the address
    takes that name with the attribute appended, ``author`` and ``author@url``.
    A nested item carrying neither is skipped rather than guessed at, so an
    ``h-geo`` holding only a latitude contributes nothing instead of a
    plausible-looking wrong value.

    The address is read from the ``url`` property and deliberately not from the
    nested item's ``value``, which is the one thing measurement changed here.
    ``value`` is not the address: it is whatever the *prefix* that nested the
    item asks for. Measured on mf2py 2.0.2, ``u-author h-card`` gives a value of
    ``/~dimonomid`` -- the link -- while ``p-category h-card`` gives ``kellan``
    -- the name, with the link sitting unread in ``properties["url"]``. Taking
    the value would therefore put a name in an address slot on every ``p-``
    prefixed item and throw the real address away. On the pages where the two
    agree the answer is identical, so nothing is lost by reading the property.

    A dict carrying no ``properties`` is not a nested item at all: it is how
    mf2py returns an ``e-`` property, ``{"html": ..., "value": ...}``, whose
    value is the text of that markup. It takes the slot's own name, so an
    entry's ``content`` arrives as its text.

    ``metaformats`` is passed as ``False``, which is also mf2py's default and
    is pinned here rather than inherited: switched on, mf2py reports OpenGraph
    and Twitter card meta tags as microformats, and this package has a reader
    for each of those, every field naming the vocabulary it truly came from.
    """
    mf2py = _mf2py()
    # mf2py's own parser warns on every XHTML page, into the caller's stderr,
    # about a choice it made itself; the caller can do nothing with it.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed: dict[str, Any] = mf2py.parse(
            doc=doc.html, url=doc.url, metaformats=False
        )
    found: list[dict[str, str]] = []
    for item in parsed.get("items") or []:
        flat = _flatten(item)
        if flat:
            found.append(flat)
    return found


def _flatten(item: dict[str, Any]) -> dict[str, str]:
    """One top-level item, as a flat mapping of name to value."""
    flat: dict[str, str] = {}
    declared_type = _text(_first(item.get("type")))
    if declared_type:
        flat["@type"] = declared_type
    properties = item.get("properties")
    if isinstance(properties, dict):
        for key, declared in properties.items():
            _place(flat, str(key), _first(declared))
    return flat


def _place(flat: dict[str, str], key: str, declared: Any) -> None:
    """Record what one property declared, under ``key``, or record nothing."""
    if isinstance(declared, dict):
        _place_nested(flat, key, declared)
        return
    text = _text(declared)
    if text:
        flat[key] = text


def _place_nested(flat: dict[str, str], key: str, declared: dict[str, Any]) -> None:
    """Record a nested item's name under ``key`` and its address under ``key@url``."""
    properties = declared.get("properties")
    if not isinstance(properties, dict):
        # No ``properties`` means this is not a nested microformat but mf2py's
        # parse of an ``e-`` property: markup, whose ``value`` is its text.
        text = _text(declared.get("value"))
        if text:
            flat[key] = text
        return
    name = _text(_first(properties.get("name")))
    address = _text(_first(properties.get("url")))
    if name:
        flat[key] = name
    if address:
        flat[f"{key}@url"] = address


def _first(declared: Any) -> Any:
    """The first element of a property's list, or None when there is not one.

    mf2py always returns a list here. "Always" is a promise about a library
    this package imports by name and never type-checks, so a value that is not
    a list is read as no value rather than indexed into.
    """
    if isinstance(declared, list) and declared:
        return declared[0]
    return None


def _text(declared: Any) -> str:
    """One declared scalar as text, or "" when it carries nothing.

    Empty is not a value, here as everywhere else in this package: mf2py
    reports the name of an h-card built from a bare link as ``""``, and
    recording that would shadow a real name another reader carries.
    """
    return declared.strip() if isinstance(declared, str) else ""
