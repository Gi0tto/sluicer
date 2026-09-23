"""Read the OpenGraph meta tags.

The protocol's own namespace, ``og:``, the vertical namespaces it defines
(``article:``, ``book:``, ``profile:``, ``video:``, ``music:``), and Facebook's
``product:`` type, which its catalogues read. The verticals
are part of the protocol: ``og:type`` names one and the page describes that
type in its namespace, so reading ``og:`` alone reads the label and drops the
statement. Measured on 2026-09-22 across the 359 WCXB pages Sluicer targets,
``article:published_time`` is on 33% of them. ``fb:`` and ``al:`` are
Facebook's and Apple's app plumbing, not statements about the page, and stay
out.

The Twitter card has its own reader, which runs after this one, so OpenGraph
wins a key the two share (``title``, ``description``, ``image:alt``).
OpenGraph describes the document, so it is not in
``sluicer.declared.merge.ABOUT_A_THING``.
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

# Facebook's own object type for a thing for sale, not one of ogp.me's: Meta
# documents ``product:price:amount``, ``product:price:currency``,
# ``product:availability``, ``product:brand`` and ``product:retailer_item_id``
# for its catalogues, and about 1,900 files on GitHub write them. Read like a
# vertical, namespace kept, so the key says whose they are.
FACEBOOK_TYPES = ("product:",)

NAMESPACES = VERTICALS + FACEBOOK_TYPES
"""Every namespace read besides ``og:``, whose keys keep their namespace."""


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
    for key, content in read_namespaced_meta(doc, NAMESPACES).items():
        found.setdefault(key, content)
    return found
