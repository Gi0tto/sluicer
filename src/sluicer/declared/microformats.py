"""Read microformats2, the vocabulary a page writes into its class attributes.

``<article class="h-entry">`` with ``<h1 class="p-name">`` inside it declares an
entry and its title in the same markup that styles them. The rules (implied
properties, value-class patterns, backcompat with the 2005 vocabularies, a
prefix table deciding what a value is) belong to a reference parser, ``mf2py``,
and this module calls it.

It is the only reader behind an extra, and off unless ``extract`` is called
with ``microformats=True``: an environment holding ``mf2py`` alone holds twelve
packages (measured on 2026-09-22) against a base install of three. Across
twenty live pages measured the same day, microformats appeared on one, which
carried OpenGraph too, so the reader buys compatibility with ``extruct``
rather than reach. Nothing is imported until it is called.

Microformats describes a thing, so it is in
``sluicer.declared.merge.ABOUT_A_THING``.
"""

from __future__ import annotations

import warnings
from types import ModuleType
from typing import Any

from sluicer.document import Document
from sluicer.extras import MissingExtra, import_extra


class MicroformatsExtraMissing(MissingExtra):
    """The optional ``microformats`` extra (mf2py) is not installed.

    Its message names the install line. What counts as missing, as opposed to
    broken, is ``sluicer.extras``'s rule.
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

    ``mf2py`` returns a tree; each top-level item becomes one flat dict:
    ``@type`` from its first class, as the page spelt it (``h-entry``), and one
    key per property, keeping the first value (a second ``p-category`` is
    dropped).

    A nested item such as an ``author`` h-card contributes its name under the
    property's name and its link under ``name@url`` (``author``,
    ``author@url``), the convention induction uses for an anchor. The link is
    read from the item's ``url`` property, not its ``value``: measured on mf2py
    2.0.2, ``value`` is whatever the nesting prefix asks for, the link for
    ``u-author h-card`` but the name for ``p-category h-card``. A nested item
    with neither is skipped rather than guessed at. An ``e-`` property arrives
    as its text.

    ``metaformats`` is pinned to ``False``: switched on, mf2py reports
    OpenGraph and Twitter card tags as microformats, and each of those has a
    reader of its own here.
    """
    mf2py = _mf2py()
    # mf2py warns on every XHTML page, into the caller's stderr, about a choice
    # it made itself; the caller can do nothing with it.
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

    mf2py returns a list here, but it is imported by name and never
    type-checked, so anything else is read as no value.
    """
    if isinstance(declared, list) and declared:
        return declared[0]
    return None


def _text(declared: Any) -> str:
    """One declared scalar as text, or "" when it carries nothing.

    mf2py reports the name of an h-card built from a bare link as ``""``, and
    an empty value must not shadow a real one another reader carries.
    """
    return declared.strip() if isinstance(declared, str) else ""
