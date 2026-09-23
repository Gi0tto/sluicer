"""The page every syntax reads: decoded once, parsed once, and what it may cost.

extruct parses bytes with ``lxml.html.HTMLParser(encoding="UTF-8")`` unless
told otherwise, so libxml2 is made to read every page as UTF-8, whatever the
page declares: a windows-1252 page comes back with its accents replaced, even
when its ``<meta charset>`` says windows-1252. Here the ``encoding`` a caller
passes is believed when the bytes are valid in it. UTF-8, the default, is
therefore believed exactly when the bytes are UTF-8, which is what extruct's
callers see on every page where extruct was right; otherwise the bytes are
decoded the way a browser decodes them (``sluicer.document.sniff_encoding``):
a byte order mark, the page's own declaration, UTF-8 when they are valid in
it, then windows-1252.
"""

from __future__ import annotations

from dataclasses import dataclass

import lxml.etree
from lxml.html import HtmlElement

from sluicer.document import (
    _BOMS,
    _base_of,
    _codec,
    _parse_utf8,
    load,
    sniff_encoding,
)

# What one page may cost a syntax that copies, in the terms sluicer's own
# readers use: every element a walk visits and every character copied into the
# answer is paid for from one budget, ten times what the page holds and never
# less than this. extruct has no such bound: a property nested in a property
# holds all the text below it, so a page of nested properties costs the square
# of its size, and a page of them nested a thousand deep is a page nobody can
# read. When the budget is spent, the syntax stops and returns the start of its
# answer in document order, the same every time.
_PAGE_FLOOR = 10_000


class Budget:
    """What is left to spend on one page, shared by everything that reads it."""

    def __init__(self, size: int) -> None:
        self.left = max(_PAGE_FLOOR, 10 * size)

    def pay(self, cost: int) -> bool:
        """Take ``cost`` from what is left, or spend it all and say no."""
        if cost > self.left:
            self.left = 0
            return False
        self.left -= cost
        return True


@dataclass(frozen=True)
class Page:
    """One page, parsed.

    ``base_url`` is what the caller passed, and what extruct resolves against;
    ``base`` is that address with the page's own ``<base href>`` applied, which
    is what the HTML standard resolves a microdata address against. ``text`` is
    the page as decoded, for mf2py, and None for a tree handed in already
    parsed. ``size`` is what the budgets are measured against.
    """

    tree: HtmlElement
    base_url: str | None
    base: str | None
    size: int
    text: str | None

    def budget(self) -> Budget:
        """A fresh budget for one syntax's reading of this page."""
        return Budget(self.size)


def decode(data: bytes, encoding: str | None) -> str:
    """The text of ``data``: in ``encoding`` when it is valid there, else sniffed.

    A byte order mark outranks both, as it does in a browser.
    """
    if encoding and not any(data.startswith(bom) for bom, _name in _BOMS):
        codec = _codec(encoding.encode("ascii", "replace"))
        if codec is not None:
            try:
                return data.decode(codec)
            except UnicodeDecodeError:
                pass
    return data.decode(sniff_encoding(data), errors="replace")


def read_page(
    html: str | bytes | HtmlElement, base_url: str | None, encoding: str | None
) -> Page:
    """Parse ``html``, or take the tree it already is. Never raises."""
    if isinstance(html, bytes):
        text = decode(html, encoding)
        # A decoded str holds no lone surrogate, so it always encodes.
        tree = _parse_utf8(text.encode("utf-8"))
        return Page(tree, base_url, _base_of(tree, base_url), len(text), text)
    if isinstance(html, str):
        doc = load(html, url=base_url)
        return Page(doc.tree, base_url, doc.base, len(html), html)
    return of_tree(html, base_url)


def of_tree(tree: HtmlElement, base_url: str | None) -> Page:
    """A page for a tree the caller parsed, as extruct's ``extract_items`` takes.

    Its size is its serialisation's: the tree is all there is to measure.
    """
    size = len(lxml.etree.tostring(tree, encoding="unicode"))
    return Page(tree, base_url, _base_of(tree, base_url), size, None)
