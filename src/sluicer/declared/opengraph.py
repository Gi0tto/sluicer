"""Read the OpenGraph meta tags.

The protocol's own namespace, ``og:``, and the vertical namespaces it defines
on top of it. This reader used to return the Twitter card as well and label
every value ``source="opengraph"``, which made the provenance false for any
field a card had won and left the choice between the two vocabularies to
whichever tag the page's author typed first. The card is now
``sluicer.declared.twitter``, it runs after this reader, and the keys they
share -- ``title``, ``description``, ``image``, ``image:alt`` -- resolve by a
stated precedence rather than by document order.

The verticals are the protocol's, not an extension of it: ``og:type`` names
one of them and the page then describes that type in its own namespace, as
``https://ogp.me/ns/article#``. Reading ``og:`` alone therefore read the
label and dropped the statement -- measured on 2026-09-22 across the 359 WCXB
pages Sluicer targets, ``article:published_time`` is on 33% of them and
``article:author`` on 8%, and none of it was read. ``fb:`` and ``al:`` are
Facebook's and Apple's and stay out: what makes a namespace OpenGraph is the
specification defining it, not the colon in the attribute.

OpenGraph describes the *document*: ``og:title`` and ``og:site_name`` answer
"what is this page", never "what is in this list". That is why this reader is
absent from ``sluicer.api.ABOUT_A_THING``, and why a page whose only
declaration is OpenGraph is still a page that declared nothing about its rows.
"""

from __future__ import annotations

from sluicer.declared.meta import read_namespaced_meta, read_prefixed_meta
from sluicer.document import Document

_PREFIX = "og:"

# The vertical object types the OpenGraph protocol defines, checked against
# the specification at https://ogp.me/ on 2026-09-22 rather than remembered.
# The page defines each one with its own namespace URI and its own properties
# -- article:published_time, article:author, article:section, article:tag,
# book:author, profile:first_name, video:actor, music:musician -- and this
# tuple is that list and nothing else, so a site's own inventions, fb:app_id
# and al:* are not reported as a vocabulary they do not belong to.
VERTICALS = ("article:", "book:", "profile:", "video:", "music:")


def read_opengraph(doc: Document) -> dict[str, str]:
    """Return the og: tags, prefix stripped, and the verticals, namespace kept.

    Two spellings of one key, on purpose. ``og:`` is the protocol's own
    namespace and says nothing beyond "this is OpenGraph", so it is stripped:
    ``og:title`` is a title. A vertical is a type, and the type is part of the
    fact, so it is kept: ``article:published_time`` is when *the article* was
    published, which is not the same statement as an undated ``published_time``
    and is not the same key as a ``book:published_time`` would be.
    ``article:author`` and ``book:author`` collapsing onto one ``author`` is
    the defect this avoids.

    ``og:`` is read first, so on the pathological page that writes both
    ``og:article:tag`` and ``article:tag`` the protocol's own namespace wins
    its key, deterministically and not by document order.
    """
    found = read_prefixed_meta(doc, _PREFIX)
    for key, content in read_namespaced_meta(doc, VERTICALS).items():
        found.setdefault(key, content)
    return found
