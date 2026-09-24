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

import heapq
from collections import Counter, defaultdict
from collections.abc import Callable

from lxml.html import HtmlElement

from sluicer.structure.records import address_of
from sluicer.structure.shape import alike, kind, outline, telling

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

# How many groups of one kind a parent's children are compared with one by one.
# Past this many, a child is compared only with groups whose first members
# share one of its telling paths, and with the earliest ``_COMPARED`` of those.
# On the 3,948 pages of the benchmark corpora no parent held more than forty
# groups of one kind, and no child needed more than nine comparisons once the
# groups were found by their paths. A page of thousands of children that share
# most of their parts and are still not alike would otherwise compare each
# child with every one before it; past the limit, a child that matched none
# begins a group of its own.
_SCANNED = 16
_COMPARED = 64

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


def _worth(member: HtmlElement, worths: dict[HtmlElement, _Measure]) -> int:
    """How much of a record this member holds: its text, and where it points.

    The text is counted as a reader sees it, its whitespace collapsed. Each
    element is measured once, from its children's measures, and kept in
    ``worths``: a member inside another member is not measured again, and
    listings nested inside listings, measured member by member, cost the
    square of their depth, seven seconds for a 93 KB page.
    """
    text, addresses = _measured(member, worths)
    length = text[0] + max(text[1] - 1, 0) if text else 0
    return length + addresses * _ADDRESS_WORTH


# An element's text once its whitespace is collapsed, as what makes it up: the
# characters that are not space, the words, and whether it starts and ends
# inside a word, which decides whether two pieces written one after the other
# join into one word. None is no text at all.
_Text = tuple[int, int, bool, bool] | None
# An element's text, and how many parts at or below it point somewhere.
_Measure = tuple[_Text, int]


def _piece(text: str | None) -> _Text:
    if not text:
        return None
    words = text.split()
    if not words:
        return (0, 0, False, False)
    return (
        sum(map(len, words)),
        len(words),
        not text[0].isspace(),
        not text[-1].isspace(),
    )


def _measured(element: HtmlElement, worths: dict[HtmlElement, _Measure]) -> _Measure:
    """``element``'s text, as ``text_content`` reads it, and its addresses.

    Each element is measured from its children's measures, so the elements
    under ``element`` not measured yet are gathered first, parents before
    children, and measured in the other order. A comment's words are not
    text, and what follows it is.
    """
    held = worths.get(element)
    if held is not None:
        return held
    # Each element not measured yet, with its children, parents first: a
    # child is walked to once, and its children are read once.
    order: list[tuple[HtmlElement, list[HtmlElement]]] = []
    pending = [element]
    while pending:
        node = pending.pop()
        children = list(node)
        order.append((node, children))
        pending.extend(
            child
            for child in children
            if isinstance(child.tag, str) and child not in worths
        )
    for node, children in reversed(order):
        text = _piece(node.text)
        addresses = 1 if address_of(node) else 0
        for child in children:
            if isinstance(child.tag, str):
                inner, below = worths[child]
                addresses += below
            else:
                inner = None
            tail = child.tail
            for other in (inner, _piece(tail) if tail else None):
                # The text so far, and then ``other``: two words written one
                # after the other with no space between are one word.
                if other is None:
                    continue
                if text is None:
                    text = other
                else:
                    joined = 1 if text[3] and other[2] else 0
                    text = (
                        text[0] + other[0],
                        text[1] + other[1] - joined,
                        text[2],
                        other[3],
                    )
        worths[node] = (text, addresses)
    return worths[element]


def _same_shape_siblings(parent: HtmlElement) -> list[list[HtmlElement]]:
    """``parent``'s children, gathered into groups of one kind, in document order.

    A child joins the first group whose first member it matches, so the answer
    depends on nothing but the page.
    """
    children = [
        (child, kind(child), outline(child)) for child in parent if _member(child)
    ]
    outlines: dict[str, list[frozenset[str]]] = {}

    def of_kind(own: str) -> list[frozenset[str]]:
        # Asked only of a kind with many groups, and gathered for all kinds
        # at once, so the children are looked through once whatever the page.
        if not outlines:
            for _, other, inside in children:
                outlines.setdefault(other, []).append(inside)
        return outlines[own]

    kinds: dict[str, _Kind] = {}
    ordered: list[list[HtmlElement]] = []
    for child, own, inside in children:
        found = kinds.get(own)
        if found is None:
            found = kinds[own] = _Kind(own, of_kind)
        members = found.place(child, inside)
        if members is not None:
            ordered.append(members)
    return ordered


class _Kind:
    """The groups begun so far among one parent's children of one kind.

    A child is compared with each group's first member in turn, while there
    are few groups. Past ``_SCANNED`` groups, only the groups whose first
    members share one of its telling paths can match it (``telling``), ranked
    rarest first among the children of this kind, and it is compared with the
    earliest ``_COMPARED`` of those. Two thousand children none of which was
    alike, each compared with every group before it, took seconds.
    """

    def __init__(
        self, own: str, of_kind: Callable[[str], list[frozenset[str]]]
    ) -> None:
        self.own = own
        self.of_kind = of_kind
        self.groups: list[tuple[frozenset[str], list[HtmlElement]]] = []
        self.by_path: dict[str, list[int]] | None = None
        self.held: dict[str, int] = {}
        # The first group begun by a child with no paths below it.
        self.blank: list[HtmlElement] | None = None

    def place(
        self, child: HtmlElement, inside: frozenset[str]
    ) -> list[HtmlElement] | None:
        """Add ``child`` to the first group it matches, or begin a group with it.

        Returns the group begun, or None when ``child`` joined one.
        """
        if self.by_path is None:
            for first, members in self.groups:
                if alike(first, inside):
                    members.append(child)
                    return None
        elif self._joined(child, inside):
            return None
        members = [child]
        self.groups.append((inside, members))
        if not inside and self.blank is None:
            self.blank = members
        if self.by_path is not None:
            self._index(len(self.groups) - 1)
        elif len(self.groups) == _SCANNED:
            self.held = Counter(
                path for paths in self.of_kind(self.own) for path in paths
            )
            self.by_path = defaultdict(list)
            for number in range(len(self.groups)):
                self._index(number)
        return members

    def _rank(self, path: str) -> tuple[int, str]:
        return self.held[path], path

    def _index(self, number: int) -> None:
        assert self.by_path is not None
        for path in telling(self.groups[number][0], self._rank):
            self.by_path[path].append(number)

    def _joined(self, child: HtmlElement, inside: frozenset[str]) -> bool:
        assert self.by_path is not None
        if not inside:
            # An outline with no paths is alike only to another with none.
            if self.blank is None:
                return False
            self.blank.append(child)
            return True
        paths = telling(inside, self._rank)
        compared = 0
        last = -1
        # Each list holds the numbers of groups in the order they were begun,
        # so the merge meets the groups in that order, and meets a group that
        # two lists hold twice in a row.
        for number in heapq.merge(*(self.by_path.get(path, []) for path in paths)):
            if number == last:
                continue
            last = number
            first, members = self.groups[number]
            if alike(first, inside):
                members.append(child)
                return True
            compared += 1
            if compared == _COMPARED:
                break
        return False


def repeating_groups(
    tree: HtmlElement, minimum: int = 3, furniture_too: bool = False
) -> list[list[HtmlElement]]:
    """Return groups of same-shaped siblings, the most promising first.

    Groups inside the page's furniture -- its navigation, its asides, what it
    hides -- are left out, unless ``furniture_too``: a person who points at a
    value there means that group.
    """
    found: list[tuple[int, int, list[HtmlElement]]] = []
    worths: dict[HtmlElement, _Measure] = {}
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
    worths: dict[HtmlElement, _Measure],
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
    worths: dict[HtmlElement, _Measure],
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
