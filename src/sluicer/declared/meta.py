"""One scan of the ``<meta>`` tags, shared by the readers keyed on a name.

OpenGraph and the Twitter card are the same shape twice: flat ``<meta>`` tags
whose names share a prefix. They are two readers, so each value names its
vocabulary, and one scan, so they can never disagree about which tags exist.

``property`` and ``name`` are both read whatever the prefix: OpenGraph's
specification says ``property`` and the card's says ``name``, and the web
writes each for both.

The scan is ``meta_tags``. ``read_prefixed_meta`` asks it for the tags whose
name begins with a prefix that only names the vocabulary, and strips it
(``twitter:title`` is a title); ``read_named_meta`` matches a closed list of
bare names (HTML's own). OpenGraph reads the scan itself, since it keeps its
tags' order to group its arrays. Dublin Core keeps its own scan, since it
matches two prefixes case-insensitively on ``name`` only.
"""

from __future__ import annotations

from collections.abc import Iterator

from sluicer.document import METAS, Document, scan


def meta_tags(doc: Document) -> Iterator[tuple[list[str], str, str]]:
    """Yield ``(keys, name, content)`` for every ``<meta>`` carrying a value.

    ``keys`` holds the terms of the ``property`` attribute and then the ``name``
    attribute, lowercased, so ``OG:Title`` is ``og:title`` and a tag whose
    ``property`` says something else is still read by its ``name``. RDFa, which
    OpenGraph is written in, makes ``property`` a list of terms, so
    ``property="og:title name"`` is ``og:title`` and ``name``; read as one name,
    it was a field called "title name", spelt with whatever whitespace the page
    put between the two. ``name`` is one name, and is also given as written,
    for the reader that matches HTML's own metadata names.

    An empty or whitespace-only ``content`` is not a value and never leaves
    here, so no caller has to remember to drop it.

    The page is scanned once, whichever reader asks first, and each caller is
    given its own ``keys``: OpenGraph, the Twitter card and HTML's names each
    scanned it again, and OpenGraph twice.
    """
    scanned: list[tuple[tuple[str, ...], str, str]] | None = doc.memo.get(_SCAN)
    if scanned is None:
        scanned = doc.memo[_SCAN] = list(_scan(doc))
    for keys, name, content in scanned:
        yield list(keys), name, content


_SCAN = "meta_tags"


def _scan(doc: Document) -> Iterator[tuple[tuple[str, ...], str, str]]:
    for meta in scan(doc, METAS):
        if meta.get("property") is None and meta.get("name") is None:
            continue
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        name = meta.get("name") or ""
        terms = (meta.get("property") or "").lower().split()
        keys = (*terms, name.strip().lower()) if name.strip() else tuple(terms)
        yield keys, name, content


def read_prefixed_meta(doc: Document, prefix: str) -> dict[str, str]:
    """Return the meta tags whose name begins with ``prefix``, prefix stripped.

    The first declaration of a key wins.
    """
    found: dict[str, str] = {}
    for keys, _name, content in meta_tags(doc):
        for key in keys:
            if key.startswith(prefix):
                found.setdefault(key[len(prefix) :], content)
                break
    return found


def read_named_meta(doc: Document, names: frozenset[str]) -> dict[str, str]:
    """Return the ``<meta name=...>`` tags whose name is one of ``names``.

    ``names`` is matched case-insensitively and the key lowercased, so
    ``Author`` and ``author`` are one field. Only ``name`` is read: the HTML
    standard defines its metadata names for that attribute, and a page writing
    ``property="author"`` is using some other vocabulary.
    """
    found: dict[str, str] = {}
    for _keys, name, content in meta_tags(doc):
        key = name.strip().lower()
        if key in names:
            found.setdefault(key, content)
    return found
