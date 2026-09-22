"""What makes two elements the same kind of thing.

A page that lists twenty products repeats one shape twenty times. The words
differ and the shape agrees, so the shape is what we compare. Text is
deliberately not part of a signature, and neither is anything below a bounded
depth: two cards that differ only in how deeply their prose is nested are still
two cards.
"""

from __future__ import annotations

from lxml.html import HtmlElement

_MAX_CLASSES = 3


def _own(element: HtmlElement) -> str:
    classes = sorted((element.get("class") or "").split())[:_MAX_CLASSES]
    tag = element.tag if isinstance(element.tag, str) else "?"
    return tag + ("." + ".".join(classes) if classes else "")


def signature(element: HtmlElement, depth: int = 3) -> str:
    """Return a string that two elements of the same kind share."""
    if depth <= 0:
        return _own(element)
    children = [
        signature(child, depth - 1)
        for child in element
        if isinstance(child.tag, str)
    ]
    return _own(element) + "(" + ",".join(children) + ")"
