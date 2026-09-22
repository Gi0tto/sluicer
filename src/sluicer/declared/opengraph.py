"""Read OpenGraph and twitter card meta tags."""

from __future__ import annotations

from sluicer.document import Document

_PREFIXES = ("og:", "twitter:")


def read_opengraph(doc: Document) -> dict[str, str]:
    """Return the og: and twitter: meta tags, prefixes stripped."""
    found: dict[str, str] = {}
    for meta in doc.tree.xpath("//meta[@property or @name]"):
        key = meta.get("property") or meta.get("name") or ""
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        for prefix in _PREFIXES:
            if key.startswith(prefix):
                found.setdefault(key[len(prefix):], content)
                break
    return found
