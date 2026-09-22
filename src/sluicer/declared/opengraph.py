"""Read the OpenGraph meta tags.

Only ``og:``. This reader used to return the Twitter card as well and label
every value ``source="opengraph"``, which made the provenance false for any
field a card had won and left the choice between the two vocabularies to
whichever tag the page's author typed first. The card is now
``sluicer.declared.twitter``, it runs after this reader, and the keys they
share -- ``title``, ``description``, ``image``, ``image:alt`` -- resolve by a
stated precedence rather than by document order.

OpenGraph describes the *document*: ``og:title`` and ``og:site_name`` answer
"what is this page", never "what is in this list". That is why this reader is
absent from ``sluicer.api.ABOUT_A_THING``, and why a page whose only
declaration is OpenGraph is still a page that declared nothing about its rows.
"""

from __future__ import annotations

from sluicer.declared.meta import read_prefixed_meta
from sluicer.document import Document

_PREFIX = "og:"


def read_opengraph(doc: Document) -> dict[str, str]:
    """Return the og: meta tags, prefix stripped."""
    return read_prefixed_meta(doc, _PREFIX)
