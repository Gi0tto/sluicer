"""One scan of the ``<meta>`` tags, shared by the readers keyed on a name.

OpenGraph and the Twitter card are the same shape twice: flat ``<meta>`` tags
whose names share a prefix. They are two readers, so each value names its
vocabulary, and one scan, so they can never disagree about which tags exist.

``property`` and ``name`` are both read whatever the prefix: OpenGraph's
specification says ``property`` and the card's says ``name``, and the web
writes each for both.

Three questions are asked of the scan. ``read_prefixed_meta`` strips a prefix
that only names the vocabulary (``og:title`` is a title);
``read_namespaced_meta`` keeps a prefix that names a type within it
(``article:published_time``); ``read_named_meta`` matches a closed list of
bare names (HTML's own). Dublin Core keeps its own scan, since it matches two
prefixes case-insensitively on ``name`` only.
"""

from __future__ import annotations

from collections.abc import Iterator

from sluicer.document import Document


def _meta_tags(doc: Document) -> Iterator[tuple[list[str], str, str]]:
    """Yield ``(keys, name, content)`` for every ``<meta>`` carrying a value.

    ``keys`` holds the ``property`` and then the ``name`` attribute, trimmed and
    lowercased, so ``OG:Title`` is ``og:title`` and a tag whose ``property``
    says something else is still read by its ``name``. ``name`` is also given
    as written, for the reader that matches HTML's own metadata names.

    An empty or whitespace-only ``content`` is not a value and never leaves
    here, so no caller has to remember to drop it.
    """
    for meta in doc.tree.xpath("//meta[@property or @name]"):
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        name = meta.get("name") or ""
        prop = (meta.get("property") or "").strip().lower()
        keys = [key for key in (prop, name.strip().lower()) if key]
        yield keys, name, content


def read_prefixed_meta(doc: Document, prefix: str) -> dict[str, str]:
    """Return the meta tags whose name begins with ``prefix``, prefix stripped.

    The first declaration of a key wins.
    """
    found: dict[str, str] = {}
    for keys, _name, content in _meta_tags(doc):
        for key in keys:
            if key.startswith(prefix):
                found.setdefault(key[len(prefix) :], content)
                break
    return found


def read_namespaced_meta(doc: Document, prefixes: tuple[str, ...]) -> dict[str, str]:
    """Return the meta tags under one of ``prefixes``, the prefix kept in the key.

    For a prefix that names a type inside the vocabulary, as OpenGraph's
    verticals do: ``article:published_time`` stripped to ``published_time``
    would be a weaker statement, and collide with ``book:published_time``.
    The first declaration of a key wins.
    """
    found: dict[str, str] = {}
    for keys, _name, content in _meta_tags(doc):
        match = next(
            (key for key in keys for prefix in prefixes if key.startswith(prefix)),
            None,
        )
        if match is not None:
            found.setdefault(match, content)
    return found


def read_named_meta(doc: Document, names: frozenset[str]) -> dict[str, str]:
    """Return the ``<meta name=...>`` tags whose name is one of ``names``.

    ``names`` is matched case-insensitively and the key lowercased, so
    ``Author`` and ``author`` are one field. Only ``name`` is read: the HTML
    standard defines its metadata names for that attribute, and a page writing
    ``property="author"`` is using some other vocabulary.
    """
    found: dict[str, str] = {}
    for _keys, name, content in _meta_tags(doc):
        key = name.strip().lower()
        if key in names:
            found.setdefault(key, content)
    return found
