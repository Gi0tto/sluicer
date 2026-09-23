"""JSON-LD in extruct's shape: each block's objects, exactly as the page wrote them.

No ``@graph`` is flattened and no reference resolved, as in extruct; numbers
are Python numbers, as ``json.loads`` makes them. What differs is which blocks
are read. extruct reads a block whose ``type`` is ``application/ld+json``
spelt exactly so, and reads it with ``json.loads``, then with the first line
removed if it is a comment; a block that still is not JSON raises, and with
extruct's default ``errors="strict"`` that one block loses the whole page's
extraction, every other syntax included. Measured on the 360 WCXB pages as
served, four pages raise so; two of them for a block holding nothing but
whitespace. Here a block is read the way sluicer's own reader reads it (see
``sluicer.declared.jsonld``): the media type ignoring case and parameters, a
comment or CDATA wrapper, a byte order mark or a trailing comma forgiven, and a
block that is still not JSON skipped, so the page's other blocks are kept.
"""

from __future__ import annotations

from typing import Any

from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Page, of_tree, read_page
from sluicer.declared.jsonld import _is_ld_json, _parse


class JsonLdExtractor:
    """extruct's JSON-LD extractor."""

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
    ) -> list[Any]:
        return self.read(read_page(htmlstring, base_url, encoding))

    def extract_items(
        self, document: HtmlElement, base_url: str | None = None
    ) -> list[Any]:
        return self.read(of_tree(document, base_url))

    def read(self, page: Page) -> list[Any]:
        """Every object in every block, a block's top-level list unwrapped.

        What is falsy -- an empty object, a ``null`` in a top-level list -- is
        dropped, as extruct drops it.
        """
        found: list[Any] = []
        for script in page.tree.xpath("descendant-or-self::script[@type]"):
            if not _is_ld_json(script.get("type") or ""):
                continue
            raw = (script.text_content() or "").strip()
            if not raw:
                continue
            parsed = _parse(raw, as_written=False)
            if isinstance(parsed, list):
                found.extend(item for item in parsed if item)
            elif isinstance(parsed, dict) and parsed:
                found.append(parsed)
        return found
