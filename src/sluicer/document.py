"""The parsed page every reader works from."""

from __future__ import annotations

from dataclasses import dataclass

import lxml.etree
import lxml.html


@dataclass(frozen=True)
class Document:
    """A page that has been parsed once and is read many times."""

    html: str
    tree: lxml.html.HtmlElement
    url: str | None = None


def load(html: str, url: str | None = None) -> Document:
    """Parse ``html`` into a Document. This never raises.

    Broken markup is tolerated by the parser. When lxml cannot parse the
    document at all -- it is empty, or it carries nothing but a doctype, a
    comment, whitespace with a byte order mark, or an XML declaration -- the
    tree is an empty ``<html>`` element instead. Readers then find nothing
    and the caller truthfully reports that the page declares nothing, which
    is the honest answer for a page that declares nothing.

    ``html`` is kept verbatim either way, so what was given is never lost.
    """
    try:
        tree = lxml.html.fromstring(html)
    except (lxml.etree.LxmlError, ValueError):
        # lxml raises ParserError ("Document is empty") for a document it
        # considers empty, and ValueError for a str carrying an XML encoding
        # declaration. Neither is a reason to explode in the caller's face.
        tree = lxml.html.Element("html")
    return Document(html=html, tree=tree, url=url)
