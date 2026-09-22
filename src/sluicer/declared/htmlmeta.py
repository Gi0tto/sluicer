"""Read the metadata names HTML defines for itself.

The oldest declaration on the web and still the most common: pages with no
JSON-LD, microdata or OpenGraph very often carry ``<meta name="description">``
and ``<meta name="author">``. Measured on 2026-09-22 across the 359 WCXB pages
Sluicer targets, ``description`` is on 87% of them and ``author`` on 29%.

It is a closed list: ``author``, ``description``, ``keywords``, ``generator``,
``application-name`` and ``theme-color``. Every ``name=`` attribute would
report a page's ``csrf-token`` and build id as statements about it; browser
directives (``robots``, ``viewport``) are instructions to a client, not
statements about the page's subject.

These values arrive as ``source="html"``: no vocabulary, no schema, no type.
Extruct files ``<meta name="description">`` under Dublin Core, which never
claimed it. The reader runs last, so any real vocabulary wins and a bare tag
only fills a gap. It describes the document, so it is not in
``sluicer.declared.merge.ABOUT_A_THING``.
"""

from __future__ import annotations

from sluicer.declared.meta import read_named_meta
from sluicer.document import Document

# The metadata names the HTML standard defines, and nothing else. Written as
# a frozenset because it is a membership test and a closed list, and the
# closedness is the design: every name added here is a claim that the name
# says something about the page's subject rather than about its plumbing.
NAMES = frozenset(
    {
        "author",
        "description",
        "keywords",
        "generator",
        "application-name",
        "theme-color",
    }
)


def read_htmlmeta(doc: Document) -> dict[str, str]:
    """Return the standard ``<meta name=...>`` metadata, keys lowercased."""
    return read_named_meta(doc, NAMES)
