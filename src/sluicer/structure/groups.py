"""Finding the siblings a page repeats.

A listing is a parent whose children are the same shape over and over. Groups
of at least three are found and ranked by how much a reader would get out of
them.

Two things a reader does without thinking are done here. The page's furniture
is ignored: anything inside ``head``, ``nav``, ``aside`` or ``footer`` repeats
more than any listing and is never the content, and ``script`` and ``style``
are never members (lxml gives them no element children, but inline scripts sit
among content and carry more characters than any row). And members are
measured by what they carry -- their text plus the addresses they point at --
so a row of empty ``<span>`` is worth nothing, however many parts it has.
"""

from __future__ import annotations

from collections import defaultdict

from lxml.html import HtmlElement

from sluicer.structure.records import address_of
from sluicer.structure.shape import alike, kind, outline

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


def _same_shape_siblings(parent: HtmlElement) -> list[list[HtmlElement]]:
    """``parent``'s children, gathered into groups of one kind, in document order.

    A child joins the first group whose first member it matches, so the answer
    depends on nothing but the page.
    """
    groups: dict[str, list[tuple[frozenset[str], list[HtmlElement]]]] = defaultdict(
        list
    )
    ordered: list[list[HtmlElement]] = []
    for child in parent:
        if not _member(child):
            continue
        own, inside = kind(child), outline(child)
        for first, members in groups[own]:
            if alike(first, inside):
                members.append(child)
                break
        else:
            members = [child]
            groups[own].append((inside, members))
            ordered.append(members)
    return ordered


def repeating_groups(tree: HtmlElement, minimum: int = 3) -> list[list[HtmlElement]]:
    """Return groups of same-shaped siblings, the most promising first."""
    found: list[tuple[int, int, list[HtmlElement]]] = []
    for order, parent in enumerate(tree.iter()):
        if _furniture(parent):
            continue
        for members in _same_shape_siblings(parent):
            if len(members) >= minimum:
                richest = max(_worth(member) for member in members)
                found.append((len(members) * richest, order, members))
    found.sort(key=lambda item: (-item[0], item[1]))
    return [members for _, _, members in found]
