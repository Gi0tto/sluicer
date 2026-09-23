"""An element's text, the two ways extruct reads it.

``readable`` is how extruct's microdata reader turns an element into text: a
copy of it with scripts, styles, comments, processing instructions, ``<link>``
and ``<meta>`` removed, laid out by html-text's rules, which put a line break
around a block such as ``<div>`` or ``<li>``, a blank line around a paragraph
or heading, a space between two inline runs of text unless the second begins
with punctuation or the first ends with an opening bracket, and collapse the
whitespace inside each run. extruct's callers compare those strings, so the
rules are followed exactly, down to where a removed comment's trailing text
lands. The rules are html-text's (MIT); this is its own implementation, over
the tree sluicer has already parsed.

``literal`` is what an RDFa processor reads as a plain literal: every text
node below the element, as written, comments' text included, which is what
pyRdfa's DOM walk over lxml hands it.

Both walk without recursing, so a page nested as deep as libxml2 allows is
read with a caller's stack, and both pay for every node they visit and every
character they return; with the budget spent they return None.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Budget

NEWLINE_TAGS = frozenset(
    {
        "article",
        "aside",
        "br",
        "dd",
        "details",
        "div",
        "dt",
        "fieldset",
        "figcaption",
        "footer",
        "form",
        "header",
        "hr",
        "legend",
        "li",
        "main",
        "nav",
        "table",
        "tr",
    }
)
DOUBLE_NEWLINE_TAGS = frozenset(
    {
        "blockquote",
        "dl",
        "figure",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ol",
        "p",
        "pre",
        "title",
        "ul",
    }
)
# What extruct's cleaner removes before the text is read. Comments and
# processing instructions go too; their tags are not strings.
_REMOVED = frozenset({"script", "style", "link", "meta"})

_WHITESPACE = re.compile(r"\s+")
_ENDS_IN_WHITESPACE = re.compile(r"\s$")
_PUNCTUATION_FIRST = re.compile(r'^[,:;.!?")]')
_OPEN_BRACKET_LAST = re.compile(r"\($")


def _removed(node: HtmlElement) -> bool:
    return not isinstance(node.tag, str) or node.tag in _REMOVED


def _own_text(element: HtmlElement) -> str:
    """The text an element starts with once the cleaner has run.

    A removed node's trailing text is kept and joins whatever precedes it:
    the element's own text, when no kept child comes first.
    """
    parts = [element.text or ""]
    for child in element:
        if not _removed(child):
            break
        parts.append(child.tail or "")
    return "".join(parts)


def _kept_children(element: HtmlElement) -> Iterator[tuple[HtmlElement, str]]:
    """Each child the cleaner keeps, with the trailing text it ends up with."""
    kept: HtmlElement | None = None
    tail: list[str] = []
    for child in element:
        if _removed(child):
            if kept is not None:
                tail.append(child.tail or "")
            continue
        if kept is not None:
            yield kept, "".join(tail)
        kept, tail = child, [child.tail or ""]
    if kept is not None:
        yield kept, "".join(tail)


# What the last thing written was, which decides what the next may add.
_AFTER_TEXT, _AFTER_LINE, _AFTER_BLANK_LINE = range(3)


class _Layout:
    """html-text's chunks, and what the last one was."""

    def __init__(self) -> None:
        self.chunks: list[str] = []
        self.after = _AFTER_BLANK_LINE
        # The raw text of the last run: its trailing whitespace decides whether
        # the next run is spaced from it.
        self.previous = ""

    def breaks(self, tag: str) -> None:
        if self.after == _AFTER_BLANK_LINE:
            return
        if tag in DOUBLE_NEWLINE_TAGS:
            self.chunks.append("\n" if self.after == _AFTER_LINE else "\n\n")
            self.after = _AFTER_BLANK_LINE
        elif tag in NEWLINE_TAGS:
            if self.after != _AFTER_LINE:
                self.chunks.append("\n")
            self.after = _AFTER_LINE

    def text(self, raw: str) -> int:
        """Write one run of text; return how many characters it added."""
        run = _WHITESPACE.sub(" ", raw.strip()) if raw else ""
        if not run:
            return 0
        space = ""
        if self.after == _AFTER_TEXT and (
            _ENDS_IN_WHITESPACE.search(self.previous)
            or (
                not _PUNCTUATION_FIRST.search(run)
                and not _OPEN_BRACKET_LAST.search(self.previous)
            )
        ):
            space = " "
        self.chunks.extend((space, run))
        self.previous, self.after = raw, _AFTER_TEXT
        return len(space) + len(run)


def readable(element: HtmlElement, budget: Budget) -> str | None:
    """The element's text as extruct's microdata reader gives it, or None.

    An element the cleaner removes whole -- a ``<script>`` or ``<style>`` that
    is itself the property -- is emptied rather than removed, so its text is
    empty.
    """
    if _removed(element):
        return ""
    layout = _Layout()
    if not budget.pay(1):
        return None
    layout.breaks(element.tag)
    if not budget.pay(layout.text(_own_text(element))):
        return None
    stack: list[tuple[HtmlElement, Iterator[tuple[HtmlElement, str]], str | None]] = [
        (element, _kept_children(element), None)
    ]
    while stack:
        current, children, tail = stack[-1]
        for child, child_tail in children:
            if not budget.pay(1):
                return None
            layout.breaks(child.tag)
            if not budget.pay(layout.text(_own_text(child))):
                return None
            stack.append((child, _kept_children(child), child_tail))
            break
        else:
            stack.pop()
            layout.breaks(current.tag)
            if tail is not None and not budget.pay(layout.text(tail)):
                return None
    return "".join(layout.chunks).strip()


def literal(element: HtmlElement, budget: Budget) -> str | None:
    """Every text node below ``element``, as written, or None.

    Comments and processing instructions count: pyRdfa's DOM over lxml hands
    their text to the literal like any other node's.
    """
    parts: list[str] = []
    pending: list[HtmlElement | str] = [element]
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            if not budget.pay(len(node)):
                return None
            parts.append(node)
            continue
        if not budget.pay(1 + len(node.text or "")):
            return None
        parts.append(node.text or "")
        for child in reversed(node):
            if child.tail:
                pending.append(child.tail)
            pending.append(child)
    return "".join(parts)
