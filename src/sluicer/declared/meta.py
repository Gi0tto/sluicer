"""One scan of the ``<meta>`` tags, shared by the readers keyed on a prefix.

OpenGraph and the Twitter card are the same shape said twice: a flat set of
``<meta>`` tags whose names all begin with a prefix, describing the document
rather than anything on it. They are two readers, so a value can say which of
the two declared it, and one scan, so the two can never disagree about which
tags exist -- the only thing that separates them is the prefix they ask for.

``property`` and ``name`` are both accepted, whichever prefix is asked for.
The OpenGraph specification says ``property`` and the Twitter card
specification says ``name``; the web writes each of them for both, and a
reader that insisted on the right one would drop tags every other consumer
reads.

Three questions are asked of that one scan, because a prefix is not always
the same kind of thing and HTML's own metadata names have none. A prefix that
is the vocabulary's own name is stripped (``read_prefixed_meta``), since it
says only which vocabulary this is; a prefix that names a type within the
vocabulary is kept (``read_namespaced_meta``), since the type is part of the
fact; and a bare name is matched against a closed list of the names the HTML
standard defines (``read_named_meta``). What changes between the three is the
question, not the way a tag is found, so the xpath is written once.

Dublin Core is the same shape again and keeps its own scan: it matches two
prefixes case-insensitively and lowercases the key, which is a different
question to ask of a tag, not a different way of finding one.
"""

from __future__ import annotations

from collections.abc import Iterator

from sluicer.document import Document


def _meta_tags(doc: Document) -> Iterator[tuple[str, str, str]]:
    """Yield ``(property, name, content)`` for every ``<meta>`` carrying a value.

    The one place this package looks for a ``<meta>`` tag. An empty or
    whitespace-only ``content`` is not a value and never leaves here, so no
    caller has to remember to drop it and none of them can disagree about
    which tags the page has. A missing attribute is an empty string rather
    than ``None``, so a caller can ask ``startswith`` of it without checking.
    """
    for meta in doc.tree.xpath("//meta[@property or @name]"):
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        yield meta.get("property") or "", meta.get("name") or "", content


def read_prefixed_meta(doc: Document, prefix: str) -> dict[str, str]:
    """Return the meta tags whose name begins with ``prefix``, prefix stripped.

    The first declaration of a key wins, so a page that says ``og:title``
    twice has said it once as far as anything downstream is concerned. An
    empty or whitespace-only ``content`` is not a value and is dropped, here
    as everywhere else, so it cannot shadow the real value another reader
    carries.
    """
    found: dict[str, str] = {}
    for prop, name, content in _meta_tags(doc):
        key = prop or name
        if not key.startswith(prefix):
            continue
        found.setdefault(key[len(prefix):], content)
    return found


def read_namespaced_meta(
    doc: Document, prefixes: tuple[str, ...]
) -> dict[str, str]:
    """Return the meta tags under one of ``prefixes``, the prefix kept in the key.

    The counterpart of ``read_prefixed_meta``, for the case where the prefix
    is not the vocabulary's own name but a type inside it: OpenGraph's
    vertical namespaces. ``article:published_time`` stripped to
    ``published_time`` would be a different, weaker statement -- and the same
    key as a hypothetical ``book:published_time`` -- so the namespace stays.

    First-wins and the empty-content rule are ``read_prefixed_meta``'s, for
    the same reasons; ``prefixes`` is tried in the order given, and a tag
    stops at the first one that matches it.
    """
    found: dict[str, str] = {}
    for prop, name, content in _meta_tags(doc):
        key = prop or name
        for prefix in prefixes:
            if key.startswith(prefix):
                found.setdefault(key, content)
                break
    return found


def read_named_meta(doc: Document, names: frozenset[str]) -> dict[str, str]:
    """Return the ``<meta name=...>`` tags whose name is one of ``names``.

    ``names`` is a closed list and is matched case-insensitively, with the
    lowercased name as the key: the web writes ``<meta name="Author">`` and
    ``<meta name="author">`` for the one HTML metadata name, and a reader
    that treated those as two fields would report one page as declaring an
    author twice. Lowercasing before the first-wins is also what makes
    first-wins mean anything across those spellings.

    Only ``name`` is looked at here, unlike the prefixed readers. The HTML
    standard defines its metadata names for the ``name`` attribute, and
    ``property`` is the attribute the vocabularies with a prefix use; a page
    writing ``property="author"`` is saying something in a vocabulary this
    reader does not know.
    """
    found: dict[str, str] = {}
    for _prop, name, content in _meta_tags(doc):
        key = name.strip().lower()
        if key in names:
            found.setdefault(key, content)
    return found
