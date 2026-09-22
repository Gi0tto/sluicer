"""What makes two elements the same kind of thing.

A page that lists twenty products repeats one shape twenty times. The words
differ and the shape agrees, so the shape is what we compare, in two parts.

The element itself is compared exactly: its tag and its first three classes.
The class attribute is most of what a page says about what a thing is, and it
is what keeps a story row apart from the subtext row beside it.

What is inside it is compared loosely. Its outline is the set of tag paths down
to a bounded depth -- tags only, and each path once -- and two outlines only
have to share most of their paths. A class below the member is a value as often
as a kind (``p.star-rating.Three``), a child repeated four times instead of two
is the same child, and an optional badge is still the same card; comparing any
of those exactly split one listing into several and read only the largest.
Text is never part of a shape.
"""

from __future__ import annotations

from lxml.html import HtmlElement

_MAX_CLASSES = 3

# How much of their outlines two members must share, as the size of what they
# have in common over the size of both together. Two thirds lets one optional
# part through in a card of a few parts, and stops a card whose inner element
# is a different one: {p, p/span, p/span/b} against {p, p/span, p/span/i} share
# half.
_ALIKE = 2 / 3


def kind(element: HtmlElement) -> str:
    """The element's own tag and first classes, which a member must match."""
    classes = sorted((element.get("class") or "").split())[:_MAX_CLASSES]
    tag = element.tag if isinstance(element.tag, str) else "?"
    return tag + ("." + ".".join(classes) if classes else "")


def outline(element: HtmlElement, depth: int = 3) -> frozenset[str]:
    """Every tag path below ``element``, down to ``depth`` levels."""
    found: set[str] = set()
    pending = [(child, str(child.tag), 1) for child in element]
    while pending:
        child, path, level = pending.pop()
        if not isinstance(child.tag, str):
            continue
        found.add(path)
        if level < depth:
            pending.extend(
                (grandchild, f"{path}/{grandchild.tag}", level + 1)
                for grandchild in child
            )
    return frozenset(found)


def alike(one: frozenset[str], other: frozenset[str]) -> bool:
    """True when two outlines share enough to be one kind of member."""
    union = one | other
    if not union:
        return True
    return len(one & other) / len(union) >= _ALIKE


def same_kind(one: HtmlElement, other: HtmlElement, depth: int = 3) -> bool:
    """True when ``one`` and ``other`` are two of the same kind of thing."""
    return kind(one) == kind(other) and alike(
        outline(one, depth), outline(other, depth)
    )
