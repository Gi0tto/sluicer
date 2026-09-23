"""Read Dublin Core meta tags.

Older than schema.org, and still the only structured data on many library,
university, repository and government pages: flat ``<meta name="DC.title">``
tags, sometimes with a ``scheme`` attribute naming the value's encoding rather
than adding a field. ``DC.`` (the fifteen original elements) and ``DCTERMS.``
(the refined set) turn up on the same page and answer the same questions, so
both are read into one flat mapping.

The whole name is matched case-insensitively and the key lowercased: the 1997
examples wrote ``DC.Title``, the HTML that copied them ``dc.title``, and
first-wins only means something across one spelling.

Dublin Core describes the document, so it is not in
``sluicer.declared.merge.ABOUT_A_THING``.
"""

from __future__ import annotations

from sluicer.document import Document

_PREFIXES = ("dc.", "dcterms.")


def read_dublincore(doc: Document) -> dict[str, str]:
    """Return the Dublin Core meta tags, prefixes stripped, keys lowercased."""
    found: dict[str, str] = {}
    for meta in doc.tree.xpath("//meta[@name]"):
        name = (meta.get("name") or "").strip().lower()
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        for prefix in _PREFIXES:
            if name.startswith(prefix):
                found.setdefault(name[len(prefix) :], content)
                break
    return found
