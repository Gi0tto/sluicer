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

Dublin Core is the same shape again and keeps its own scan: it matches two
prefixes case-insensitively and lowercases the key, which is a different
question to ask of a tag, not a different way of finding one.
"""

from __future__ import annotations

from sluicer.document import Document


def read_prefixed_meta(doc: Document, prefix: str) -> dict[str, str]:
    """Return the meta tags whose name begins with ``prefix``, prefix stripped.

    The first declaration of a key wins, so a page that says ``og:title``
    twice has said it once as far as anything downstream is concerned. An
    empty or whitespace-only ``content`` is not a value and is dropped, here
    as everywhere else, so it cannot shadow the real value another reader
    carries.
    """
    found: dict[str, str] = {}
    for meta in doc.tree.xpath("//meta[@property or @name]"):
        key = meta.get("property") or meta.get("name") or ""
        if not key.startswith(prefix):
            continue
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        found.setdefault(key[len(prefix):], content)
    return found
