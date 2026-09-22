"""The parsed page every reader works from."""

from __future__ import annotations

from dataclasses import dataclass

import lxml.html


@dataclass(frozen=True)
class Document:
    """A page that has been parsed once and is read many times."""

    html: str
    tree: lxml.html.HtmlElement
    url: str | None = None


def load(html: str, url: str | None = None) -> Document:
    """Parse ``html`` into a Document, tolerating broken markup."""
    tree = lxml.html.fromstring(html)
    return Document(html=html, tree=tree, url=url)
