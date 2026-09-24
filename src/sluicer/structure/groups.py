"""Finding the siblings a page repeats.

A listing is a parent whose children are the same shape over and over. Groups
of at least three are found and ranked by how much a reader would get out of
them.

Three things a reader does without thinking are done here. The page's
furniture is ignored: anything inside ``head``, ``nav``, ``aside`` or
``footer``, anything the page marks as a menu, a navigation, a sidebar, a
dialog or a toolbar with its ARIA ``role``, and anything it hides, repeats more
than any listing and is never the content; and ``script`` and ``style`` are
never members (lxml gives them no element children, but inline scripts sit
among content and carry more characters than any row). Members are measured by
what they carry -- their text plus the addresses they point at -- so a row of
empty ``<span>`` is worth nothing, however many parts it has. And a group whose
members are mostly another listing is sections, not rows: the three columns of
a news page are not three stories, and the stories inside them are ranked on
their own.
"""

from __future__ import annotations

from collections import defaultdict

from lxml.html import HtmlElement

from sluicer.structure.records import address_of
from sluicer.structure.shape import alike, kind, outline

# Regions a reader skips on the way to the content, wherever inside them the
# repetition sits.
_CHROME = frozenset({"head", "nav", "aside", "footer", "template", "dialog"})
# The same regions, as the page names them with ARIA. Measured on the drift
# benchmark: a code host's trending page holds a language menu of 491 links,
# role "menu", which outweighed the 25 repositories it lists.
_CHROME_ROLES = frozenset(
    {
        "navigation",
        "menu",
        "menubar",
        "complementary",
        "contentinfo",
        "banner",
        "search",
        "dialog",
        "alertdialog",
        "toolbar",
        "tablist",
        "listbox",
        "tree",
    }
)
# How much of a member a listing inside it must carry for the member to be a
# section holding rows rather than a row.
_SECTION = 0.5
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
        if chrome(node):
            return True
        node = node.getparent()
    return False


def chrome(element: HtmlElement) -> bool:
    """Whether ``element`` is one of the page's chrome regions: its navigation,
    its asides, a region it hides or marks with an ARIA chrome role."""
    tag = element.tag
    if not isinstance(tag, str):
        return False
    if tag.lower() in _CHROME or element.get("hidden") is not None:
        return True
    if (element.get("aria-hidden") or "").strip().lower() == "true":
        return True
    roles = (element.get("role") or "").lower().split()
    return any(role in _CHROME_ROLES for role in roles)


def _member(child: HtmlElement) -> bool:
    """True when ``child`` could be one row of a listing."""
    return isinstance(child.tag, str) and child.tag.lower() not in _CODE


def _worth(member: HtmlElement, worths: dict[HtmlElement, int]) -> int:
    """How much of a record this member holds: its text, and where it points.

    Kept in ``worths``, since one member is asked about more than once.
    """
    held = worths.get(member)
    if held is None:
        text = " ".join((member.text_content() or "").split())
        addresses = sum(1 for part in member.iter() if address_of(part))
        held = worths[member] = len(text) + addresses * _ADDRESS_WORTH
    return held


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


def repeating_groups(
    tree: HtmlElement, minimum: int = 3, furniture_too: bool = False
) -> list[list[HtmlElement]]:
    """Return groups of same-shaped siblings, the most promising first.

    Groups inside the page's furniture -- its navigation, its asides, what it
    hides -- are left out, unless ``furniture_too``: a person who points at a
    value there means that group.
    """
    found: list[tuple[int, int, list[HtmlElement]]] = []
    worths: dict[HtmlElement, int] = {}
    # Decided once per element, from its parent's answer, since the walk meets
    # a parent before its children. Asked of every element by climbing to the
    # root, a listing under two thousand wrappers took three seconds of an
    # 85 KB page, and the climb was all of it.
    furniture: dict[HtmlElement, bool] = {}
    for order, parent in enumerate(tree.iter()):
        above = furniture.get(parent.getparent())
        furniture[parent] = (
            _furniture(parent) if above is None else above or chrome(parent)
        )
        if furniture[parent] and not furniture_too:
            continue
        if len(parent) < minimum:
            # Fewer children than a listing has rows, comments counted.
            continue
        for members in _same_shape_siblings(parent):
            if len(members) >= minimum:
                richest = max(_worth(member, worths) for member in members)
                found.append((len(members) * richest, order, members))
    # The walk met every element in document order, which is the order the
    # furniture was decided in.
    inside = _carried_inside(found, list(furniture), worths)
    rows = [item for item in found if not _sections(item[2], inside, worths)]
    rows.sort(key=lambda item: (-item[0], item[1]))
    return [members for _, _, members in rows]


def _carried_inside(
    found: list[tuple[int, int, list[HtmlElement]]],
    walked: list[HtmlElement],
    worths: dict[HtmlElement, int],
) -> dict[HtmlElement, int]:
    """For every element, the most that one group at or below it carries.

    Only groups whose members have parts of their own count: a story has a
    link, a line and a date, while a quote's five tags are five words, and a
    quote is not a section of tags.

    Each group is credited to its parent, and each element then passes the
    most it holds up to its own parent, children before parents, so the page
    is walked once. Checked group against group, which is what this replaced,
    a page of two thousand small lists took 24 seconds: each of its groups was
    measured again for every other one.
    """
    inside: dict[HtmlElement, int] = {}
    for _, _, group in found:
        if sum(1 for member in group if len(member)) * 2 <= len(group):
            continue
        carried = sum(_worth(member, worths) for member in group)
        parent = group[0].getparent()
        inside[parent] = max(inside.get(parent, 0), carried)
    for element in reversed(walked):
        held = inside.get(element)
        above = element.getparent()
        if held is not None and above is not None:
            inside[above] = max(inside.get(above, 0), held)
    return inside


def _sections(
    members: list[HtmlElement],
    inside: dict[HtmlElement, int],
    worths: dict[HtmlElement, int],
) -> bool:
    """Whether most of ``members`` are mostly one of the other groups found.

    A member is a section when a group inside it carries at least
    ``_SECTION`` of what the member carries (``inside``, from
    ``_carried_inside``). Most members, not all: one column of a page may hold
    a single story. A group is never inside one of its own members, so it is
    never counted against itself.
    """
    sections = sum(
        1
        for member in members
        if inside.get(member, 0) >= _SECTION * max(_worth(member, worths), 1)
    )
    return sections * 2 > len(members)
