"""Read the metadata names HTML defines for itself.

The oldest declaration on the web and the most common one still: a page that
carries no JSON-LD, no microdata and no OpenGraph very often carries
``<meta name="description">`` and ``<meta name="author">`` anyway. Measured on
2026-09-22 across the 359 WCXB pages Sluicer targets, ``description`` is on
87% of them and ``author`` on 29%, and none of it was read -- while on the
pages that do declare an author, Sluicer recovered one in 130.

It is a closed list, not a catch-all: ``author``, ``description``,
``keywords``, ``generator``, ``application-name`` and ``theme-color``. A
reader that returned every ``name=`` attribute would report a page's
``csrf-token``, its ``msapplication-TileColor`` and its framework's build id
as things the page declared about itself, which is not reach but noise, and
it would make ``source="html"`` mean nothing in particular. The browser
directives -- ``robots``, ``viewport``, ``charset`` -- are out for the
neighbouring reason: they are instructions to a client, not statements about
the page's subject.

What this reader is *not* is the point of its existence. A value from
``<meta name="author">`` is not Dublin Core and not OpenGraph, and saying so
is the mistake ``extruct`` makes -- measured, a page whose only tag is
``<meta name="description">`` comes back from it under ``dublincore``. The
answer is not to leave the tag unread; it is to read it and call it what it
is, so ``source="html"`` says exactly how weak the claim is: no vocabulary,
no schema, no type.

That weakness is also its place in the precedence. This reader runs last, so
anything a real vocabulary declared wins and the bare tag only ever fills a
gap -- which matters, because ``<meta name="description">`` is very often the
same sentence as ``og:description``.

Like OpenGraph, Dublin Core and the Twitter card, these names describe the
*document*: ``<meta name="description">`` answers "what is this page", never
"what is in this list". So this reader is absent from
``sluicer.api.ABOUT_A_THING``, and a page whose only declaration is a
description has still declared nothing about its rows and is induced over.
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
