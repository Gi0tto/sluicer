"""Read RDFa Lite: vocab, typeof, property, resource, prefix.

RDFa Lite is the subset the W3C itself recommends to authors, and it is the
part real pages carry: a ``typeof`` naming a subject, ``property`` naming its
fields, ``vocab`` and ``prefix`` saying which vocabulary those names come
from, ``resource`` giving a value that is an address rather than a text.
Full RDFa is a graph language, and reading it properly means a triple store:
that is why ``extruct`` pulls in ``rdflib`` and ``pyrdfa3`` and still calls
its own RDFa support experimental. This module reads the Lite subset in pure
``lxml``, adds no dependency to the base install, and stops where the graph
begins. Anyone who needs the full graph -- chained subjects, typed literals,
inference -- is better served by a triple store than by this pretending.

Two limits follow from that, and both are deliberate.

Every term is resolved through ``vocab`` and ``prefix`` -- the page's own and
RDFa's initial context -- before it is named. A schema.org term is then named
the way every other reader names it: under ``vocab="https://schema.org/"`` the
property ``name``, the CURIE ``schema:name`` and the full IRI all arrive as
``name``. A term from any other vocabulary keeps its full IRI, so a FOAF
``name`` never collides with a schema.org one. A CURIE whose prefix nobody
declared -- MediaWiki's ``typeof="mw:Transclusion"`` on every Wikipedia page --
is not a term at all and is not read as one. OpenGraph terms are left to the
OpenGraph reader, which reads the same ``<meta property>`` tags.

A ``property`` that is itself a ``typeof`` has that subject as its value,
nested, as a microdata item inside another does. A property declared twice is
a list in document order.

RDFa is rare on today's web: across twenty well-known pages measured while
this was written, one carried it. The reader is here for compatibility --
so a page that does declare its rows this way is not read as declaring
nothing -- not because the vocabulary is winning. A ``typeof`` subject
describes a thing on the page rather than the page itself, which is why
``sluicer.api.ABOUT_A_THING`` counts this vocabulary, under the name
``rdfa``, among those that answer "what is in this list".
"""

from __future__ import annotations

from typing import Any

from lxml.html import HtmlElement

from sluicer.declared.types import type_name
from sluicer.document import Document

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


def read_rdfa(doc: Document) -> list[dict[str, Any]]:
    """Return one dict per top-level ``typeof`` subject found in the page.

    A property belongs to the nearest subject enclosing it, so the properties
    of a nested subject stay with that subject and never leak into the one
    around it. ``typeof`` may name several types, and ``property`` several
    fields, each of which gets the value, because that is what the page said.
    """
    found: list[dict[str, Any]] = []
    for subject in doc.tree.xpath("//*[@typeof]"):
        is_a_property = subject.get("property") is not None
        if is_a_property and _nearest_subject(subject) is not None:
            continue
        item = _subject(subject, 0)
        if item:
            found.append(item)
    return found


def _subject(subject: HtmlElement, depth: int) -> dict[str, Any]:
    item: dict[str, Any] = {}
    types = _names(subject, subject.get("typeof"))
    if types:
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
            value = _subject(prop, depth + 1)
            if not any(not key.startswith("@") for key in value):
                continue
        else:
            value = _value(prop)
            if not value:
                # An empty value is not a value: recording it here would
                # shadow the real one another reader may carry.
                continue
        for name in names:
            if name not in item:
                item[name] = value
            elif name in repeated:
                item[name].append(value)
            else:
                item[name] = [item[name], value]
                repeated.add(name)
    return item


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


def _value(element: HtmlElement) -> str:
    """The value one property declares.

    ``content`` first, because it is there precisely to say what the visible
    text means; then ``resource``, then the element's own address attribute,
    because the value of a link is where it points and not the words on it;
    and only then the text.
    """
    content: str | None = element.get("content")
    if content:
        return content.strip()
    resource: str | None = element.get("resource")
    if resource:
        return resource.strip()
    attr = _VALUE_ATTRS.get(element.tag)
    if attr is not None:
        declared: str | None = element.get(attr)
        if declared:
            return declared.strip()
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
    # A bare term with no vocab in scope is read as written, as it always was
    # here: pages write typeof="Product" and mean schema.org by it.
    return vocab + token if vocab else token


def _context(element: HtmlElement) -> tuple[str | None, dict[str, str]]:
    """The ``vocab`` and the prefix mappings in force at ``element``."""
    vocab: str | None = None
    prefixes: dict[str, str] = {}
    node: HtmlElement | None = element
    while node is not None:
        if vocab is None and node.get("vocab") is not None:
            vocab = node.get("vocab").strip() or None
        tokens = (node.get("prefix") or "").split()
        for name, iri in zip(tokens[::2], tokens[1::2], strict=False):
            if name.endswith(":"):
                prefixes.setdefault(name[:-1].lower(), iri)
        node = node.getparent()
    for name, iri in _INITIAL_CONTEXT.items():
        prefixes.setdefault(name, iri)
    return vocab, prefixes
