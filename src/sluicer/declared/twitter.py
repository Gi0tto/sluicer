"""Read the Twitter card meta tags.

A second document-level vocabulary in the same shape as OpenGraph, and for a
while it was read by the same function: ``read_opengraph`` matched ``og:`` and
``twitter:`` alike and stamped ``source="opengraph"`` on everything it found.
Two things were wrong with that. A value a card declared reported a reader
that had not won it, which breaks the one promise every field here makes. And
where the two vocabularies collide -- ``twitter:title`` against ``og:title``,
``twitter:image:alt`` against ``og:image:alt``, both stripping to the same key
-- the winner was whichever tag the page's author happened to write first. The
answer stayed deterministic, so no test caught it, and it was still a rule
nobody could read off the code.

Split out, the rule is stated instead: this reader runs after OpenGraph, so
OpenGraph wins a colliding key and the card fills what OpenGraph left empty.
Keys only the card carries -- ``card`` itself, ``site`` -- now arrive saying
``twitter``, which is where they came from. Measured across ten live pages
while this was written, ``card`` appeared on six of them and ``site`` on five.

Like OpenGraph, a card describes the *document*, so this reader is absent
from ``sluicer.api.ABOUT_A_THING`` and a page whose only declaration is a card
has still declared nothing about its rows. Nothing had to be added to that
gate for it: naming the vocabularies that describe a thing, rather than the
ones that do not, is what made a new document-level reader free.
"""

from __future__ import annotations

from sluicer.declared.meta import read_prefixed_meta
from sluicer.document import Document

_PREFIX = "twitter:"


def read_twitter(doc: Document) -> dict[str, str]:
    """Return the twitter: meta tags, prefix stripped."""
    return read_prefixed_meta(doc, _PREFIX)
