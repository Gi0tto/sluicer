"""Read RDFa Lite: vocab, typeof, property, resource, prefix.

RDFa Lite is the subset the W3C recommends to authors, and the part real pages
carry: ``typeof`` names a subject, ``property`` its fields, ``vocab`` and
``prefix`` the vocabulary those names come from, ``resource`` a value that is
an address. Full RDFa is a graph language that needs a triple store (extruct
pulls in ``rdflib`` and ``pyrdfa3`` for it and still calls it experimental).
This reader covers Lite in ``lxml`` alone and stops where the graph begins:
chained subjects, typed literals and inference are not read.

Every term is resolved through ``vocab`` and ``prefix`` -- the page's own and
RDFa's initial context -- before it is named. A schema.org term gets the name
every reader uses: under ``vocab="https://schema.org/"`` the property ``name``,
the CURIE ``schema:name`` and the full IRI all arrive as ``name``. A term from
another vocabulary keeps its full IRI, so a FOAF ``name`` never collides with
a schema.org one. A CURIE whose prefix nobody declared (MediaWiki's
``typeof="mw:Transclusion"`` on every Wikipedia page) is not a term. OpenGraph
terms are left to the OpenGraph reader, which reads the same ``<meta
property>`` tags.

A ``property`` that is itself a ``typeof`` has that subject as its value,
nested, as in microdata. A property declared twice is a list in document order.

RDFa is rare: across twenty well-known pages measured on 2026-09-22, one
carried it. The reader exists for compatibility. It describes things, so it is
in ``sluicer.declared.merge.ABOUT_A_THING`` as ``rdfa``.
"""

from __future__ import annotations

from typing import Any

from lxml.html import HtmlElement

from sluicer.declared.located import Located, Place, placed
from sluicer.declared.types import type_name
from sluicer.document import Document, absolute, trimmed

# The address attributes RDFa reads a value from when an element carries no
# `content` and no `resource`. `href` on the elements HTML gives it, `src` on
# an image, and `datetime` on a `time`, whose text is for a reader and whose
# attribute is the machine-readable date.
_VALUE_ATTRS = {
    "a": "href",
    "link": "href",
    "img": "src",
    "time": "datetime",
}

# The prefixes RDFa 1.1's initial context defines that pages actually use,
# checked against https://www.w3.org/2011/rdfa-context/rdfa-1.1 on 2026-09-22.
_INITIAL_CONTEXT = {
    "schema": "http://schema.org/",
    "og": "http://ogp.me/ns#",
    "dc": "http://purl.org/dc/terms/",
    "dcterms": "http://purl.org/dc/terms/",
    "foaf": "http://xmlns.com/foaf/0.1/",
    "gr": "http://purl.org/goodrelations/v1#",
    "sioc": "http://rdfs.org/sioc/ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "vcard": "http://www.w3.org/2006/vcard/ns#",
    "v": "http://rdf.data-vocabulary.org/#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
# The OpenGraph reader's, and read there.
_OPENGRAPH = ("http://ogp.me/ns", "https://ogp.me/ns")
_MAX_DEPTH = 16

# What the whole page may copy into the answer: every character of a value, a
# name or a type is paid for from one budget, ten times what the page holds and
# never less than this. A property nested in another holds all the text below
# it, one ``property`` can name hundreds of fields, and a long ``vocab`` or
# ``prefix`` is written into every name resolved under it, so each of those made
# 1.6 MB of JSON from a page of a few kilobytes. When a cost cannot be paid the
# budget is spent and the reader stops, so a hostile page gets the start of its
# answer in document order, the same every time.
_PAGE_FLOOR = 10_000


def read_rdfa(doc: Document) -> list[dict[str, Any]]:
    """Return one dict per top-level ``typeof`` subject found in the page.

    A property belongs to the nearest subject enclosing it, so the properties
    of a nested subject stay with that subject and never leak into the one
    around it. ``typeof`` may name several types, and ``property`` several
    fields, each of which gets the value, because that is what the page said.
    """
    left = [max(_PAGE_FLOOR, 10 * len(doc.html))]
    found: list[dict[str, Any]] = []
    for subject in doc.tree.xpath("//*[@typeof]"):
        is_a_property = subject.get("property") is not None
        if is_a_property and _nearest_subject(subject) is not None:
            continue
        item = _subject(doc, subject, 0, left)
        if item:
            found.append(item)
    return found


def _pay(left: list[int], cost: int) -> bool:
    """Take ``cost`` from what the page has left, or spend it all and say no."""
    if cost > left[0]:
        left[0] = 0
        return False
    left[0] -= cost
    return True


def _subject(
    doc: Document, subject: HtmlElement, depth: int, left: list[int]
) -> Located:
    item: dict[str, Any] = {}
    props: dict[str, Place] = {}
    types = _names(subject, subject.get("typeof"))
    if types and _pay(left, sum(len(name) for name in types)):
        item["@type"] = types[0] if len(types) == 1 else types
    repeated: set[str] = set()
    for prop in _properties(subject):
        names = _names(prop, prop.get("property"))
        if not names:
            continue
        value: Any
        if prop.get("typeof") is not None:
            if depth >= _MAX_DEPTH:
                continue
            before = left[0]
            value = _subject(doc, prop, depth + 1, left)
            if not any(not key.startswith("@") for key in value):
                continue
            # Its first copy was paid for as it was read.
            size, paid = before - left[0], True
        else:
            value = _value(doc, prop)
            if not value:
                # An empty value is not a value: recording it here would
                # shadow the real one another reader may carry.
                continue
            size, paid = len(value), False
        for name in names:
            # Every name the property carries is one more copy of its value.
            if not _pay(left, len(name) + (0 if paid else size)):
                return placed(item, subject, props, repeated)
            paid = False
            if name not in item:
                props[name] = prop
                item[name] = value
            elif name in repeated:
                item[name].append(value)
            else:
                item[name] = [item[name], value]
                repeated.add(name)
    return placed(item, subject, props, repeated)


def _properties(subject: HtmlElement) -> list[HtmlElement]:
    """The elements carrying ``subject``'s properties, in document order."""
    found: list[HtmlElement] = []
    pending = list(reversed(subject))
    while pending:
        element = pending.pop()
        if not isinstance(element.tag, str):
            continue
        if element.get("property") is not None:
            found.append(element)
        if element.get("typeof") is None:
            pending.extend(reversed(element))
    return found


def _nearest_subject(element: HtmlElement) -> HtmlElement | None:
    """The closest ``typeof`` ancestor of ``element``, or None if it has none."""
    parent = element.getparent()
    while parent is not None:
        if parent.get("typeof") is not None:
            return parent
        parent = parent.getparent()
    return None


def _value(doc: Document, element: HtmlElement) -> str:
    """The value one property declares.

    ``content`` first, because it is there precisely to say what the visible
    text means; then ``resource``, then the element's own address attribute,
    because the value of a link is where it points and not the words on it;
    and only then the text. The two addresses are resolved against the page.
    """
    content: str | None = element.get("content")
    if content:
        return content.strip()
    resource = trimmed(element.get("resource"))
    if resource:
        return absolute(doc, resource)
    attr = _VALUE_ATTRS.get(element.tag)
    if attr is not None:
        declared: str | None = element.get(attr)
        found = (declared or "").strip() if attr == "datetime" else trimmed(declared)
        if found:
            return found if attr == "datetime" else absolute(doc, found)
    text: str | None = element.text_content()
    return " ".join((text or "").split())


def _names(element: HtmlElement, declared: str | None) -> list[str]:
    """The names of a whitespace-separated list of terms, resolved in context.

    A term that resolves to nothing -- a CURIE whose prefix nobody declared --
    and an OpenGraph term are left out.
    """
    vocab, prefixes = _context(element)
    names: list[str] = []
    for token in (declared or "").split():
        iri = _resolve(token, vocab, prefixes)
        if iri is None or iri.startswith(_OPENGRAPH):
            continue
        name = type_name(iri)
        if name and name not in names:
            names.append(name)
    return names


def _resolve(token: str, vocab: str | None, prefixes: dict[str, str]) -> str | None:
    if "://" in token:
        return token
    if ":" in token:
        prefix, _, reference = token.partition(":")
        base = prefixes.get(prefix.lower())
        return base + reference if base is not None and reference else None
    # A bare term with no vocab in scope is read as written: pages write
    # typeof="Product" and mean schema.org by it.
    return vocab + token if vocab else token


def _context(element: HtmlElement) -> tuple[str | None, dict[str, str]]:
    """The ``vocab`` and the prefix mappings in force at ``element``."""
    vocab: str | None = None
    vocab_found = False
    prefixes: dict[str, str] = {}
    node: HtmlElement | None = element
    while node is not None:
        if not vocab_found and node.get("vocab") is not None:
            # The nearest vocab decides, and an empty one means none at all.
            vocab_found = True
            vocab = node.get("vocab").strip() or None
        tokens = (node.get("prefix") or "").split()
        for name, iri in zip(tokens[::2], tokens[1::2], strict=False):
            if name.endswith(":"):
                prefixes.setdefault(name[:-1].lower(), iri)
        node = node.getparent()
    for name, iri in _INITIAL_CONTEXT.items():
        prefixes.setdefault(name, iri)
    return vocab, prefixes
