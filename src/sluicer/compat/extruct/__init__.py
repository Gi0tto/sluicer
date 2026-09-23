"""extruct's interface, answered by sluicer: ``from sluicer.compat import extruct``.

``extruct.extract(html)`` returns what extruct 0.18 returns -- the keys
``microdata``, ``json-ld``, ``opengraph``, ``microformat``, ``rdfa`` and
``dublincore``, each a list in extruct's own shape for that syntax -- and takes
the same arguments; ``uniform=True`` gives extruct's uniform shape. The
extractor classes are here too, under the module names extruct gives them, so
``from sluicer.compat.extruct.jsonld import JsonLdExtractor`` replaces
``from extruct.jsonld import JsonLdExtractor``.

Nothing extruct needs is installed for it. Microformats need mf2py, which is
``sluicer[microformats]``, as they need it in extruct; RDFa is read by
sluicer's own processor, with no rdflib and no pyRdfa.

Where the answer differs from extruct's it is because extruct's is wrong, and
each module says how: encoding in ``page``, JSON-LD in ``jsonld``, microdata in
``w3cmicrodata``, Dublin Core in ``dublincore``, RDFa in ``rdfa``. The measured
differences on real pages are in ``docs/extruct.md``.
"""

from __future__ import annotations

import logging
import warnings
from collections.abc import Callable
from typing import Any

from lxml.html import HtmlElement

from sluicer.compat.extruct.dublincore import DublinCoreExtractor
from sluicer.compat.extruct.jsonld import JsonLdExtractor
from sluicer.compat.extruct.microformat import MicroformatExtractor
from sluicer.compat.extruct.opengraph import OpenGraphExtractor
from sluicer.compat.extruct.page import Page, of_tree, read_page
from sluicer.compat.extruct.rdfa import RDFaExtractor
from sluicer.compat.extruct.uniform import (
    _udublincore,
    _umicrodata_microformat,
    _uopengraph,
)
from sluicer.compat.extruct.w3cmicrodata import (
    LxmlMicrodataExtractor,
    MicrodataExtractor,
)

__all__ = [
    "SYNTAXES",
    "DublinCoreExtractor",
    "JsonLdExtractor",
    "LxmlMicrodataExtractor",
    "MicrodataExtractor",
    "MicroformatExtractor",
    "OpenGraphExtractor",
    "RDFaExtractor",
    "extract",
]

logger = logging.getLogger(__name__)
SYNTAXES = ["microdata", "opengraph", "json-ld", "microformat", "rdfa", "dublincore"]
_ERRORS = ("log", "ignore", "strict")


def extract(
    htmlstring_or_tree: str | bytes | HtmlElement,
    base_url: str | None = None,
    encoding: str = "UTF-8",
    syntaxes: list[str] = SYNTAXES,
    errors: str = "strict",
    uniform: bool = False,
    return_html_node: bool = False,
    schema_context: str = "http://schema.org",
    with_og_array: bool = False,
    url: str | None = None,
) -> dict[str, list[Any]]:
    """Every syntax in ``syntaxes``, each in extruct's shape for it.

    Args:
        htmlstring_or_tree: the page, as text, as bytes -- best, since its
            charset declaration is then read -- or as a tree already parsed
            with ``lxml.html``.
        base_url: the page's address, which relative addresses resolve against.
        encoding: the encoding of the bytes. It is believed when the bytes are
            valid in it; otherwise the page is decoded as a browser decodes it.
        syntaxes: which of ``SYNTAXES`` to read, as a list.
        errors: what a syntax that fails does: ``"strict"`` raises, ``"log"``
            logs it and leaves its key out, ``"ignore"`` leaves its key out.
            The one failure a page can cause is microformats without mf2py:
            no page makes a syntax here raise.
        uniform: every syntax as a list of ``{"@context", "@type", ...}``
            objects, as extruct's ``uniform`` gives them.
        return_html_node: each microdata item also holds its element, under
            ``htmlNode``.
        schema_context: the ``@context`` a microdata item with several types
            is given in uniform mode.
        with_og_array: in uniform mode, a repeated OpenGraph property keeps
            every value, as a list, rather than its first.
        url: extruct's old name for ``base_url``, deprecated there too.

    Raises:
        ValueError: ``syntaxes`` or ``errors`` is not one extruct accepts, or
            microformats are asked of a tree, which mf2py cannot read.
        MicroformatsExtraMissing: microformats asked for, with ``errors``
            strict, and mf2py not installed.
    """
    if base_url is None and url is not None:
        warnings.warn(
            '"url" argument is deprecated, please use "base_url"',
            DeprecationWarning,
            stacklevel=2,
        )
        base_url = url
    if not (isinstance(syntaxes, list) and all(v in SYNTAXES for v in syntaxes)):
        raise ValueError(
            "syntaxes must be a list with any or all (default) of"
            f"these values: {SYNTAXES}"
        )
    if errors not in _ERRORS:
        raise ValueError(
            'Invalid error command, valid values are either "log", "ignore" or "strict"'
        )
    page: Page
    if isinstance(htmlstring_or_tree, (str, bytes)):
        page = read_page(htmlstring_or_tree, base_url, encoding)
    else:
        if "microformat" in syntaxes:
            raise ValueError(
                "'microformat' syntax requires a string, not a parsed tree. "
                "Consider adjusting the 'syntaxes' argument to exclude it, "
                "or passing an HTML string or bytes."
            )
        page = of_tree(htmlstring_or_tree, base_url)
    readers: dict[str, Callable[[Page], list[Any]]] = {
        "microdata": MicrodataExtractor(add_html_node=return_html_node).read,
        "json-ld": JsonLdExtractor().read,
        "opengraph": OpenGraphExtractor().read,
        "microformat": MicroformatExtractor().read,
        "rdfa": RDFaExtractor().read,
        "dublincore": DublinCoreExtractor().read,
    }
    output: dict[str, list[Any]] = {}
    # extruct's order, which is the order of the answer's keys.
    for syntax, read in readers.items():
        if syntax not in syntaxes:
            continue
        found = _guarded(errors, syntax, read, page)
        if found is not None:
            output[syntax] = found
    if uniform:
        shapes: dict[str, Callable[[list[Any]], list[Any]]] = {
            "microdata": lambda found: _umicrodata_microformat(found, schema_context),
            "microformat": lambda found: _umicrodata_microformat(
                found, "http://microformats.org/wiki/"
            ),
            "opengraph": lambda found: _uopengraph(found, with_og_array=with_og_array),
            "dublincore": _udublincore,
        }
        for syntax, shape in shapes.items():
            if syntax in output:
                output[syntax] = shape(output[syntax])
    return output


def _guarded(
    errors: str, syntax: str, read: Callable[[Page], list[Any]], page: Page
) -> list[Any] | None:
    """``read(page)``, or None when it failed and ``errors`` says not to raise."""
    if errors == "strict":
        return read(page)
    try:
        return read(page)
    # Blind on purpose: "log" and "ignore" are extruct's promise that no syntax
    # raises, whatever went wrong in it, and a caller who chose them relies on it.
    except Exception as error:
        if errors == "log":
            logger.exception("Failed to extract %s, raises %s", syntax, error)
        return None
