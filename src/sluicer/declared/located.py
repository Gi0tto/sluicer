"""Where on the page a reader found an item, carried inside the item itself.

A reader about things returns plain JSON-like dicts, and every consumer --
the merge, the audit, the summary -- reads them as dicts. ``Located`` is a
dict that also knows where it was declared, as an attribute, so the place
travels with the value without becoming one of its keys: an ``@where`` key
would reach the audit as a property the page never declared.

A place, spelt, is an XPath to the element that declared the item -- for
JSON-LD, the ``<script>`` block's XPath and, after ``#``, a JSON pointer (RFC
6901) to the node inside it: ``/html/head/script[2]#/@graph/1``.

The place travels with the value because a path cannot be trusted to find
it: a JSON-LD reference is replaced by the node it names, which was declared
somewhere else, and a blank item dropped from a list shifts every index after
it. So a node reached through a reference carries its definition's place,
and ``place`` never counts its way into a list whose items carry none.

A place is kept as the element, or as the steps from another place, and
spelt only when it is asked for: an XPath string on every property of a
page nested two hundred deep would weigh more than the page.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Any, TypeAlias

from lxml.html import HtmlElement

Step: TypeAlias = "str | int"
# A place as it is kept: spelt already, an element, or a step from another.
Place: TypeAlias = "str | HtmlElement | Located | tuple[Place, Step]"
# A place to pay for: spelt, or what spells it when it is paid for.
Spelling: TypeAlias = "str | Callable[[], str | None] | None"


class Located(dict[str, Any]):
    """An item, where it was declared, and where each of its properties was.

    ``at`` is the item's place; ``props`` maps a property to the element that
    declared it, for a property declared once -- a repeated one has no single
    element, and is placed at its item.
    """

    def __init__(
        self,
        item: Any = (),
        at: Place | None = None,
        props: dict[str, Place] | None = None,
    ) -> None:
        super().__init__(item)
        self.at = at
        self.props = props or {}
        self._where: str | None = None
        self._spelt = False

    @property
    def where(self) -> str | None:
        """The item's place, spelt."""
        if not self._spelt:
            self._where, self._spelt = spell(self.at), True
        return self._where


def pointer(*steps: Step) -> str:
    """A JSON pointer's reference tokens joined, each escaped as RFC 6901 says."""
    return "".join(
        "/" + str(step).replace("~", "~0").replace("/", "~1") for step in steps
    )


# The elements a parsed page has one of each, whose steps need no position.
_ONCE = frozenset({"html", "head", "body"})
# A name XPath reads as written. A browser's parser makes an element of
# whatever follows a "<" -- ``h<ead``, ``fb:like``, ``a[1]`` -- and written
# as a step, those are a comparison, a prefix nothing binds, or a position.
_PLAIN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")


def xpath_of(element: HtmlElement) -> str:
    """Where an element is on its page, as an XPath nothing after it can change.

    lxml leaves out the position of an element that is the only one of its
    name, so a sibling added after it changed its place, ``meta`` to
    ``meta[1]``. Here every step carries its position, but ``html``, ``head``
    and ``body``, of which a parsed page has one each. The positions are
    lxml's, counted in C: counting siblings here would cost, for each of a
    page's ten thousand siblings, all those before it.

    A name XPath cannot read as written is matched by ``name()``, and one
    holding a quote or a ``#`` by its position among its parent's nodes: the
    path never holds a ``#``, so the first one in a place is where its JSON
    pointer starts.
    """
    chain = [*reversed(list(element.iterancestors())), element]
    written = str(element.getroottree().getpath(element)).split("/")[1:]
    if len(written) != len(chain):
        written = [_counted(node) for node in chain]
    steps = []
    for depth, (node, step) in enumerate(zip(chain, written, strict=True)):
        tag = str(node.tag)
        position = step[len(tag) :] if step.startswith(tag) else ""
        if not position and not (depth <= 1 and tag in _ONCE):
            position = "[1]"
        if _PLAIN.match(tag):
            steps.append(tag + position)
        elif not {"'", "#"} & set(tag):
            steps.append(f"*[name()='{tag}']{position}")
        else:
            steps.append(_by_position(node))
    return "/" + "/".join(steps)


def _counted(node: HtmlElement) -> str:
    """A step as lxml writes it, counted here: for a page it could not write."""
    same = [n for n in node.itersiblings(preceding=True) if n.tag == node.tag]
    return f"{node.tag}[{len(same) + 1}]"


def _by_position(node: HtmlElement) -> str:
    """A step to ``node`` by where it stands among the nodes that are not text.

    lxml's index counts elements, comments and processing instructions,
    which is what ``node()[not(self::text())]`` selects.
    """
    parent = node.getparent()
    if parent is None:
        return "*"
    return f"node()[not(self::text())][{parent.index(node) + 1}]"


def spell(at: Place | None) -> str | None:
    """A place as text: an XPath, and inside JSON-LD a pointer after ``#``."""
    steps: list[Step] = []
    while isinstance(at, tuple):
        at, step = at
        steps.append(step)
    if at is None:
        return None
    if isinstance(at, Located):
        base = at.where
    elif isinstance(at, str):
        base = at
    else:
        base = xpath_of(at)
    if base is None or "#" not in base:
        # Steps are a pointer's, and only a JSON-LD block has one.
        return base
    return base + pointer(*reversed(steps))


def place(value: Any, at: Place | None, steps: Sequence[Step]) -> str | None:
    """Where the value ``steps`` into ``value`` was declared, ``value`` being at ``at``.

    As finely as the page's items say, and never finer: each ``Located`` on
    the way names its own place, a property its element when its reader
    recorded one, and inside JSON-LD a pointer goes the rest of the way. An
    index into a list whose items carry no place stops the pointer at the
    list, since a blank item dropped from it would make the index wrong.
    """
    node, base, rest = value, at, list[Step]()
    for step in steps:
        if isinstance(node, Located):
            base, rest = node, []
            if isinstance(step, str) and step in node.props:
                base, node = node.props[step], node.get(step)
                continue
        if isinstance(step, int):
            child = node[step] if isinstance(node, list) and step < len(node) else None
            if not isinstance(child, Located):
                break
        else:
            child = node.get(step) if isinstance(node, dict) else None
            if child is None:
                break
        rest.append(step)
        node = child
    if isinstance(node, Located):
        base, rest = node, []
    for step in rest:
        base = (base, step)
    return spell(base)


def placed(
    item: dict[str, Any], at: Place, props: dict[str, Place], repeated: set[str]
) -> Located:
    """``item`` at ``at``, each property at its element but a repeated one's.

    A property declared more than once has no one element, and is placed at
    its item.
    """
    return Located(item, at, {n: p for n, p in props.items() if n not in repeated})


class Places:
    """What every place written into one answer is paid for from.

    A place costs its length. One that does not fit spends what is left and
    is not given, and neither is any after it, so which places an answer
    carries is decided by document order alone, and a hostile page's
    places cost at most the budget.
    """

    def __init__(self, left: int) -> None:
        self.left = left

    def pay(self, where: Spelling) -> str | None:
        """``where`` if it fits; one still to be spelt is spelt only if any is left."""
        if self.left <= 0:
            return None
        if callable(where):
            where = where()
        if where is None:
            return None
        if len(where) > self.left:
            self.left = 0
            return None
        self.left -= len(where)
        return where


def paid(places: Places | None, where: Spelling) -> str | None:
    """A place paid for from ``places``; None is no budget, for a trusted page."""
    if places is not None:
        return places.pay(where)
    return where() if callable(where) else where
