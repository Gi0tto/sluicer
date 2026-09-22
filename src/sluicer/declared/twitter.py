"""Read the Twitter card meta tags.

A document-level vocabulary in the same shape as OpenGraph, read separately so
each value names the vocabulary that declared it. It runs after OpenGraph: on a
key the two share (``twitter:title`` and ``og:title`` both strip to ``title``)
OpenGraph wins and the card fills what OpenGraph left empty, a stated rule
rather than whichever tag the author wrote first. Keys only the card carries,
such as ``card`` and ``site``, arrive as ``twitter``.

A card describes the document, so it is not in
``sluicer.declared.merge.ABOUT_A_THING``.
"""

from __future__ import annotations

from sluicer.declared.meta import read_prefixed_meta
from sluicer.document import Document

_PREFIX = "twitter:"


def read_twitter(doc: Document) -> dict[str, str]:
    """Return the twitter: meta tags, prefix stripped."""
    return read_prefixed_meta(doc, _PREFIX)
