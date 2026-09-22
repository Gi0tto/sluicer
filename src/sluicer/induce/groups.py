"""Finding the siblings a page repeats.

A listing page is a parent whose children are the same shape over and over. We
look for exactly that, and rank what we find by how much a reader would get out
of it. Two of a kind is a coincidence, so the floor is three.

Two things a reader does without thinking, and which ranking by shape alone does
not do, are done here.

The first is to ignore the page's furniture. The ``head`` repeats ``meta`` and
``link`` more often than any listing repeats a row, a ``nav`` repeats links, an
``aside`` repeats widgets and a ``footer`` repeats both -- and none of that is
what the page is about. Candidates sitting anywhere inside those four regions
are not considered at all, however many members they have: a group of ``meta``
elements is not a set of records. A ``script`` or a ``style`` is excluded the
same way, as a member rather than as a region, because that is the form the
problem actually takes: measured, lxml's HTML parser never gives either of them
element children, so nothing can sit *inside* one, while three inline scripts
sitting among the content are ordinary and carry more characters than any row.

The second is to count what the members carry rather than only how many parts
they have. A row of four empty ``<span>`` is four parts and no data; a headline
and a paragraph are two parts and a record. So the measure of a member is the
text it carries plus the addresses it points at, and a member with neither is
worth nothing -- which leaves its group scored at zero, behind every group that
holds something.
"""

from __future__ import annotations

from collections import defaultdict

from lxml.html import HtmlElement

from sluicer.induce.records import address_of
from sluicer.induce.shape import signature

# Regions a reader skips on the way to the content, wherever inside them the
# repetition sits.
_CHROME = frozenset({"head", "nav", "aside", "footer"})
# Elements that are code rather than content, and are never a record.
_CODE = frozenset({"script", "style"})

# An address carries no text to measure, so it is counted as one short word.
# The number matters far less than the fact that it is not zero: a member that
# is nothing but a link still points somewhere, and a member that is neither
# text nor link is worth nothing at all.
_ADDRESS_WORTH = 8


def _furniture(parent: HtmlElement) -> bool:
    """True when ``parent`` is, or sits inside, one of the page's chrome regions."""
    node: HtmlElement | None = parent
    while node is not None:
        tag = node.tag
        if isinstance(tag, str) and tag.lower() in _CHROME:
            return True
        node = node.getparent()
    return False


def _member(child: HtmlElement) -> bool:
    """True when ``child`` could be one row of a listing."""
    return isinstance(child.tag, str) and child.tag.lower() not in _CODE


def _worth(member: HtmlElement) -> int:
    """How much of a record this member holds: its text, and where it points."""
    text = " ".join((member.text_content() or "").split())
    addresses = sum(1 for part in member.iter() if address_of(part))
    return len(text) + addresses * _ADDRESS_WORTH


def repeating_groups(
    tree: HtmlElement, minimum: int = 3
) -> list[list[HtmlElement]]:
    """Return groups of same-shaped siblings, the most promising first."""
    found: list[tuple[int, int, list[HtmlElement]]] = []
    for order, parent in enumerate(tree.iter()):
        if _furniture(parent):
            continue
        by_shape: dict[str, list[HtmlElement]] = defaultdict(list)
        for child in parent:
            if _member(child):
                by_shape[signature(child)].append(child)
        for members in by_shape.values():
            if len(members) >= minimum:
                richest = max(_worth(member) for member in members)
                found.append((len(members) * richest, order, members))
    found.sort(key=lambda item: (-item[0], item[1]))
    return [members for _, _, members in found]
