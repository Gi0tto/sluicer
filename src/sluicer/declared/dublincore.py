"""Read Dublin Core meta tags.

A convention older than schema.org, and still the only structured data on a
great many library, university, repository and government pages: a flat set
of ``<meta name="DC.title">`` tags, sometimes with a ``scheme`` attribute
that names the encoding of the value rather than adding a field. Two
prefixes are in use and both turn up on the same page -- ``DC.`` for the
fifteen original elements, ``DCTERMS.`` for the larger refined set -- so
both are read, and the two vocabularies are folded into one flat mapping,
since a page carrying ``DC.date`` and ``DCTERMS.created`` is answering the
same kind of question twice, not describing two things.

The whole name is matched case-insensitively, prefix and term alike,
because the web spells it every way there is: the 1997 examples wrote
``DC.Title``, the HTML that copied them wrote ``dc.title``, and a reader
that treated those as two fields would report one page as declaring a title
twice. The key is therefore lowercased, which is also what makes first-wins
mean anything across those spellings.

Dublin Core describes the *document*, the way OpenGraph does: ``DC.title``
answers "what is this page", never "what is in this list". Nothing here
knows that -- it is the caller's business -- but it is why this reader is
absent from ``sluicer.api.ABOUT_A_THING``.
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
                found.setdefault(name[len(prefix):], content)
                break
    return found
