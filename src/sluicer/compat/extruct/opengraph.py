"""OpenGraph in extruct's shape: ``{"namespace", "properties"}`` for the head.

extruct's rules, all of them: the ``<meta property content>`` tags that are
children of ``<head>``, in the order written, each a ``(property, content)``
pair as written; a property counts when its prefix is one of OpenGraph's own
namespaces -- ``og``, the verticals, and ``product`` -- or one the ``<html>`` or
``<head>`` declares in a ``prefix`` attribute, and ``namespace`` maps each
prefix used or declared to its IRI. ``name=`` is not read and neither is a tag
in ``<body>``, as in extruct; sluicer's own OpenGraph reader reads both.
"""

from __future__ import annotations

import re
from typing import Any

from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Page, of_tree, read_page

_PREFIX_PATTERN = re.compile(r"\s*(\w+):\s*([^\s]+)")
_OG_NAMESPACES = {
    "og": "http://ogp.me/ns#",
    "music": "http://ogp.me/ns/music#",
    "video": "http://ogp.me/ns/video#",
    "article": "http://ogp.me/ns/article#",
    "book": "http://ogp.me/ns/book#",
    "profile": "http://ogp.me/ns/profile#",
    # Not ogp.me's, but what Facebook's catalogues read, and extruct reads it.
    "product": "http://ogp.me/ns/product#",
}
_XHTML_HEAD = "{http://www.w3.org/1999/xhtml}head"


class OpenGraphExtractor:
    """extruct's OpenGraph extractor."""

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
    ) -> list[dict[str, Any]]:
        return self.read(read_page(htmlstring, base_url, encoding))

    def extract_items(
        self, document: HtmlElement, base_url: str | None = None
    ) -> list[dict[str, Any]]:
        return self.read(of_tree(document, base_url))

    def read(self, page: Page) -> list[dict[str, Any]]:
        """One object per ``<head>`` that declares something; a page has one."""
        found: list[dict[str, Any]] = []
        tree = page.tree
        # The document's first head decides which <html> is asked for prefixes,
        # whichever head is being read, as lxml's ``.head`` answers extruct.
        first = next(tree.getroottree().iter("head", _XHTML_HEAD), None)
        for head in tree.xpath("//head"):
            html = first.xpath("parent::html") if first is not None else []
            namespaces = _declared(html[0]) if html else {}
            namespaces.update(_declared(head))
            properties: list[tuple[str, str]] = []
            for meta in head.xpath("meta[@property and @content]"):
                prop = meta.attrib["property"]
                prefix = prop.partition(":")[0]
                if prefix in _OG_NAMESPACES:
                    namespaces[prefix] = _OG_NAMESPACES[prefix]
                if prefix in namespaces:
                    properties.append((prop, meta.attrib["content"]))
            if properties:
                found.append({"namespace": namespaces, "properties": properties})
        return found


def _declared(element: HtmlElement) -> dict[str, str]:
    """The prefixes an element's ``prefix`` attribute declares."""
    return dict(_PREFIX_PATTERN.findall(element.attrib.get("prefix", "")))
