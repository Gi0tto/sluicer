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

The keys here are leaf names, so ``vocab`` and ``prefix`` fold away: under
``vocab="https://schema.org/"`` the property ``name``, the CURIE
``schema:name`` and the full ``https://schema.org/name`` all arrive as the
key ``name``. It is what makes the output the same flat shape microdata and
JSON-LD produce, and the price is that two vocabularies sharing a term name
share a key, where the first one written wins.

And a ``property`` that is itself a ``typeof`` declares an object, not a
scalar. Rather than invent a value out of that block's text, it is left out
of the enclosing subject and survives as a record of its own, exactly as
microdata does here. A lost link, never a wrong value.

RDFa is rare on today's web: across twenty well-known pages measured while
this was written, one carried it. The reader is here for compatibility --
so a page that does declare its rows this way is not read as declaring
nothing -- not because the vocabulary is winning. A ``typeof`` subject
describes a thing on the page rather than the page itself, which is why
``sluicer.api.ABOUT_A_THING`` counts this vocabulary, under the name
``rdfa``, among those that answer "what is in this list".
"""

from __future__ import annotations

from lxml.html import HtmlElement

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

# The separators an IRI or a CURIE puts before its leaf name, in the order a
# leaf is found: the fragment of `http://purl.org/goodrelations/v1#Offering`
# before its path, and the path before the colon of a CURIE, since an IRI
# carries a colon too and its scheme is not a prefix.
_SEPARATORS = ("#", "/", ":")


def read_rdfa(doc: Document) -> list[dict[str, str]]:
    """Return one dict per ``typeof`` subject found in the page.

    A property belongs to the nearest subject enclosing it, so the properties
    of a nested subject stay with that subject and never leak into the one
    around it. ``typeof`` may name several types; ``@type`` carries the first,
    because a record has one. ``property`` may name several fields, and each
    of them gets the value, because that is what the page said.
    """
    found: list[dict[str, str]] = []
    for subject in doc.tree.xpath("//*[@typeof]"):
        item: dict[str, str] = {}
        leaf = _leading_term(subject.get("typeof"))
        if leaf:
            item["@type"] = leaf
        for prop in subject.xpath(".//*[@property]"):
            if prop.get("typeof") is not None:
                continue
            if _nearest_subject(prop) is not subject:
                continue
            value = _value(prop)
            if not value:
                # An empty value is not a value: recording it here would
                # shadow the real one another reader may carry.
                continue
            for name in _terms(prop.get("property")):
                if name not in item:
                    item[name] = value
        # Keep any non-empty subject; drop the ones that yielded nothing at all.
        if item:
            found.append(item)
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
    and only then the text. Each attribute is read into a ``str | None`` once
    rather than fetched twice for the same answer.
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
    return (text or "").strip()


def _terms(declared: str | None) -> list[str]:
    """The leaf names of a whitespace-separated list of terms."""
    leaves = (_term(token) for token in (declared or "").split())
    return [leaf for leaf in leaves if leaf]


def _leading_term(declared: str | None) -> str:
    """The leaf name of the first term of such a list, or an empty string."""
    tokens = (declared or "").split()
    return _term(tokens[0]) if tokens else ""


def _term(token: str) -> str:
    """The leaf name of one term, however it was written.

    ``Product``, ``schema:Product`` and ``https://schema.org/Product`` are the
    three spellings a page uses for the same term, and they key alike here.
    """
    trimmed = token.rstrip("/")
    for separator in _SEPARATORS:
        if separator in trimmed:
            return trimmed.rsplit(separator, 1)[-1]
    return trimmed
