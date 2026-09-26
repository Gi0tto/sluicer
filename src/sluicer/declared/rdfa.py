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
``typeof="mw:Transclusion"`` on every page it renders) is not a term. OpenGraph
terms are left to the OpenGraph reader, which reads the same ``<meta
property>`` tags.

A ``property`` that is itself a ``typeof`` has that subject as its value,
nested, as in microdata, unless its ``content`` or ``datatype`` asks for a
literal: then the property is the new subject's own. A property declared twice
is a list in document order.

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
    scopes = _Scopes()
    found: list[dict[str, Any]] = []
    for subject in doc.tree.xpath("//@typeof/.."):
        if not left[0]:
            # The page's budget is spent: reading more subjects, each
            # walking its words, would cost what no answer can hold.
            break
        is_a_property = subject.get("property") is not None and not _own(subject)
        if is_a_property and _nearest_subject(subject) is not None:
            continue
        item = _subject(doc, subject, 0, left, scopes)
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
    doc: Document, subject: HtmlElement, depth: int, left: list[int], scopes: _Scopes
) -> Located:
    item: dict[str, Any] = {}
    props: dict[str, Place] = {}
    types = _names(subject, subject.get("typeof"), scopes)
    if types and _pay(left, sum(len(name) for name in types)):
        item["@type"] = types[0] if len(types) == 1 else types
    repeated: set[str] = set()
    for prop in _properties(subject):
        if not left[0]:
            break
        names = _names(prop, prop.get("property"), scopes)
        if not names:
            continue
        value: Any
        if (
            prop is not subject
            and prop.get("typeof") is not None
            and not _types_its_link(prop)
        ):
            if depth >= _MAX_DEPTH:
                continue
            before = left[0]
            value = _subject(doc, prop, depth + 1, left, scopes)
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
    """The elements carrying ``subject``'s properties, in document order.

    A subject that holds its own property is the first of them, and one
    below ``subject`` is not among them: it is a subject of its own.
    """
    found: list[HtmlElement] = [subject] if _own(subject) else []
    pending = list(reversed(subject))
    while pending:
        element = pending.pop()
        if not isinstance(element.tag, str):
            continue
        if element.get("property") is not None and not _own(element):
            found.append(element)
        if element.get("typeof") is None:
            pending.extend(reversed(element))
    return found


def _own(element: HtmlElement) -> bool:
    """Whether ``element`` is a subject whose ``property`` is its own.

    ``typeof`` with ``property`` makes a new subject, and the property links
    the subject around it to the new one -- unless ``content`` or ``datatype``
    asks for a literal. Then, as RDFa Core's processing rules have it, the
    property and its literal belong to the new subject, and nothing links to
    it: Drupal 7's ``<span typeof="sioc:UserAccount" property="foaf:name"
    datatype="">`` is an account and its name.
    """
    return (
        element.get("typeof") is not None
        and element.get("property") is not None
        and _asks_literal(element)
        and not _links(element)
    )


def _asks_literal(element: HtmlElement) -> bool:
    """Whether ``element``'s property asks for a literal: ``content`` or
    ``datatype``."""
    return element.get("content") is not None or element.get("datatype") is not None


def _types_its_link(element: HtmlElement) -> bool:
    """Whether ``element``'s ``typeof`` types the object of its ``rel`` or
    ``rev``, and its literal property belongs to the subject around it: as
    RDFa Core's processing rules have it, ``<a rel="schema:author" href="/u"
    typeof="Person" property="name" datatype="">Ann</a>`` names the enclosing
    subject ``Ann`` and makes ``/u`` a Person."""
    return (
        element.get("typeof") is not None
        and element.get("property") is not None
        and _asks_literal(element)
        and _links(element)
    )


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

    A ``rel`` or ``rev`` on the same element takes its addresses for itself:
    in ``<a href rel="v:url" property="v:title">Home</a>`` the address is the
    link's object and the title is the words, as RDFa Core's processing rules
    have it. HTML+RDFa ignores the plain words HTML writes there, such as
    ``nofollow``, on an element with a property, so only a ``rel`` or ``rev``
    naming a term, a CURIE or an IRI, takes the addresses. A ``datatype``
    asks for a literal, so its value is the words too: a Drupal tag,
    ``<a href="/tags/x" property="rdfs:label" datatype="">x</a>``, is labelled
    ``x``. The words are kept and the type is not.
    """
    content: str | None = element.get("content")
    if content is not None:
        # Empty is still the page's answer: the words under it are not.
        return content.strip()
    literal = element.get("datatype") is not None or _links(element)
    resource = trimmed(element.get("resource"))
    if resource and not literal:
        return absolute(doc, resource)
    attr = _VALUE_ATTRS.get(element.tag)
    if attr is not None and (attr == "datetime" or not literal):
        declared: str | None = element.get(attr)
        found = (declared or "").strip() if attr == "datetime" else trimmed(declared)
        if found:
            return found if attr == "datetime" else absolute(doc, found)
    text: str | None = element.text_content()
    return " ".join((text or "").split())


def _links(element: HtmlElement) -> bool:
    """Whether ``element``'s ``rel`` or ``rev`` names a term: a CURIE or an IRI,
    which is what carries a colon."""
    return any(
        ":" in token
        for attr in ("rel", "rev")
        for token in (element.get(attr) or "").split()
    )


def _names(element: HtmlElement, declared: str | None, scopes: _Scopes) -> list[str]:
    """The names of a whitespace-separated list of terms, resolved in context.

    A term that resolves to nothing -- a CURIE whose prefix nobody declared --
    and an OpenGraph term are left out. ``scopes`` holds the contexts one
    page's reading has found, read once each.
    """
    scope = scopes.at(element)
    # Once each, in order: a list asked for each term whether it held it, and
    # an attribute of forty thousand terms took four seconds.
    names: dict[str, None] = {}
    for token in (declared or "").split():
        iri = _resolve(token, scope)
        if iri is None or iri.startswith(_OPENGRAPH):
            continue
        name = type_name(iri)
        if name:
            names.setdefault(name)
    return list(names)


def _resolve(token: str, scope: _Scope | None) -> str | None:
    if "://" in token:
        return token
    if ":" in token:
        prefix, _, reference = token.partition(":")
        base = _prefix(scope, prefix.lower())
        return base + reference if base is not None and reference else None
    # A bare term with no vocab in scope is read as written: pages write
    # typeof="Product" and mean schema.org by it.
    vocab = scope.vocab if scope is not None else None
    return vocab + token if vocab else token


class _Scope:
    """What one element declares, ``vocab`` and ``prefix``, over what is in
    force around it. The ``vocab`` in force is carried; a prefix is looked up
    element by element, nearest first, so no element copies the prefixes of
    those around it."""

    def __init__(self, element: HtmlElement, outer: _Scope | None) -> None:
        declared = element.get("vocab")
        if declared is not None:
            # The nearest vocab decides, and an empty one means none at all.
            self.vocab: str | None = declared.strip() or None
        else:
            self.vocab = outer.vocab if outer is not None else None
        self.prefixes: dict[str, str] = {}
        tokens = (element.get("prefix") or "").split()
        for name, iri in zip(tokens[::2], tokens[1::2], strict=False):
            if name.endswith(":"):
                self.prefixes.setdefault(name[:-1].lower(), iri)
        self.outer = outer


def _prefix(scope: _Scope | None, name: str) -> str | None:
    """The address ``name`` stands for in ``scope``: the nearest element's
    declaring it, then RDFa's initial context."""
    while scope is not None:
        found = scope.prefixes.get(name)
        if found is not None:
            return found
        scope = scope.outer
    return _INITIAL_CONTEXT.get(name)


class _Scopes:
    """The scope in force at each element one reading asks about, each read
    once: asked of every property, every element around it was read again,
    and a page of four thousand prefixes and properties took two seconds."""

    def __init__(self) -> None:
        self.found: dict[HtmlElement, _Scope | None] = {}

    def at(self, element: HtmlElement) -> _Scope | None:
        # The elements up to the first one already read, then down again.
        chain: list[HtmlElement] = []
        node: HtmlElement | None = element
        while node is not None and node not in self.found:
            chain.append(node)
            node = node.getparent()
        scope = self.found[node] if node is not None else None
        for node in reversed(chain):
            if node.get("vocab") is not None or node.get("prefix") is not None:
                scope = _Scope(node, scope)
            self.found[node] = scope
        return self.found[element]
