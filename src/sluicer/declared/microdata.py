"""Read microdata: itemscope, itemtype, itemprop, itemref.

The rules are the WHATWG HTML standard's, section "Microdata": a property
belongs to the nearest item enclosing it, or to an item that names it with
``itemref``; one ``itemprop`` can name several properties; a property that is
itself an item has that item as its value; and what the value of any other
property is depends on the element carrying it.
"""

from __future__ import annotations

from typing import Any

from lxml.html import HtmlElement

from sluicer.declared.types import type_name
from sluicer.document import Document, absolute

# The element whose value is an attribute rather than its text, and which one.
# The standard's list, in full: a ``<video itemprop>`` is its URL, not the
# fallback text inside it.
_VALUE_ATTRS = {
    "meta": "content",
    "audio": "src",
    "embed": "src",
    "iframe": "src",
    "img": "src",
    "source": "src",
    "track": "src",
    "video": "src",
    "a": "href",
    "area": "href",
    "link": "href",
    "object": "data",
    "data": "value",
    "meter": "value",
    "time": "datetime",
}

# The attributes among those that hold an address.
_ADDRESSES = frozenset({"src", "href", "data"})

# Deeper than any real page nests items; a bound so a hostile one costs a
# fixed amount. Loops through itemref are stopped by the chain in ``_item``.
_MAX_DEPTH = 16


def read_microdata(doc: Document) -> list[dict[str, Any]]:
    """Return one dict per top-level item, with nested items inside it.

    A top-level item is an ``itemscope`` that is not itself somebody's
    property. An item that is a property is that property's value, so an
    ``Offer`` inside a ``Product`` arrives as the product's ``offers`` rather
    than as a record of its own. A property declared more than once is a list
    in document order; declared once, it is its value.
    """
    by_id: dict[str | None, HtmlElement] = {}
    for element in doc.tree.xpath("//*[@id]"):
        # The standard's first element with an id, not the last.
        by_id.setdefault(element.get("id"), element)
    referenced = {
        by_id[ref]
        for scope in doc.tree.xpath("//*[@itemref]")
        for ref in (scope.get("itemref") or "").split()
        if ref in by_id
    }
    order = {element: index for index, element in enumerate(doc.tree.iter())}
    left = [max(_PAGE_FLOOR, 10 * len(doc.html))]
    found: list[dict[str, Any]] = []
    for scope in doc.tree.xpath("//*[@itemscope]"):
        if scope.get("itemprop") is not None and (
            _nearest_scope(scope) is not None or _inside(scope, referenced)
        ):
            continue
        context = _Context(doc, by_id, order, [_BUDGET], left)
        item = _item(context, scope, frozenset({scope}))
        if item:
            found.append(item)
    return found


# How many items one top-level item may expand, counting every nested one.
# Items that name each other with itemref form a graph, and walking every path
# through it is exponential: four such items were estimated at half an hour.
_BUDGET = 256

# What the whole page may cost, whatever its items: every element a walk visits
# and every character a value, a name or a type copies into the answer is paid
# for from one budget, ten times what the page holds and never less than this.
# The budget above is each top-level item's own, and it bounded the number of
# expansions, not what they copied: an element is a property of every item
# that names it with itemref, one itemprop can name forty properties, and
# nested itemprops each hold all the text below them, so a 59 KB page came out
# as 95 million characters. When a cost cannot be paid the budget is spent and
# the reader stops, so what it returns is the start of the answer in document
# order, the same every time.
_PAGE_FLOOR = 10_000


class _Context:
    """What every level of one top-level item's walk shares."""

    def __init__(
        self,
        doc: Document,
        by_id: dict[str | None, HtmlElement],
        order: dict[HtmlElement, int],
        budget: list[int],
        left: list[int],
    ) -> None:
        self.doc = doc
        self.by_id = by_id
        self.order = order
        self.budget = budget
        self.left = left

    def pay(self, cost: int) -> bool:
        """Take ``cost`` from what the page has left, or spend it all and say no."""
        if cost > self.left[0]:
            self.left[0] = 0
            return False
        self.left[0] -= cost
        return True


def _inside(element: HtmlElement, roots: set[HtmlElement]) -> bool:
    """Whether ``element`` is one of ``roots`` or sits inside one of them."""
    node: HtmlElement | None = element
    while node is not None:
        if node in roots:
            return True
        node = node.getparent()
    return False


def _item(
    context: _Context, scope: HtmlElement, chain: frozenset[HtmlElement]
) -> dict[str, Any]:
    """One item and, nested, the items it holds.

    ``chain`` is the items being expanded on the way down, the standard's
    "memory": an item that holds itself, directly or through itemref, is not
    expanded again inside itself.
    """
    item: dict[str, Any] = {}
    types = [
        name
        for token in (scope.get("itemtype") or "").split()
        if (name := type_name(token))
    ]
    if types and context.pay(sum(len(name) for name in types)):
        item["@type"] = types[0] if len(types) == 1 else types
    repeated: set[str] = set()
    for prop in _properties(scope, context):
        names = (prop.get("itemprop") or "").split()
        if not names:
            continue
        value: Any
        if prop.get("itemscope") is not None:
            if prop in chain or len(chain) > _MAX_DEPTH or context.budget[0] <= 0:
                continue
            context.budget[0] -= 1
            before = context.left[0]
            value = _item(context, prop, chain | {prop})
            if not any(not key.startswith("@") for key in value):
                continue
            # Its first copy was paid for as it was read.
            size, paid = before - context.left[0], True
        else:
            value = _value(context.doc, prop)
            if not value:
                # An empty value is not a value: recording it here would
                # shadow the real one another reader may carry.
                continue
            size, paid = len(value), False
        for name in names:
            # Every name the property carries is one more copy of its value.
            if not context.pay(len(name) + (0 if paid else size)):
                return item
            paid = False
            if name not in item:
                item[name] = value
            elif name in repeated:
                item[name].append(value)
            else:
                item[name] = [item[name], value]
                repeated.add(name)
    return item


def _properties(scope: HtmlElement, context: _Context) -> list[HtmlElement]:
    """The elements carrying ``scope``'s properties, in document order.

    Its own descendants whose nearest item is ``scope``, and the elements it
    names with ``itemref`` together with their descendants, stopping at any
    item on the way down, since what is inside that belongs to that item.
    Sorted into tree order, as the standard sorts them, whichever of the two
    each came from. Every element visited is paid for from the page's budget.
    """
    by_id = context.by_id
    roots = [scope] + [
        by_id[ref]
        for ref in (scope.get("itemref") or "").split()
        if ref in by_id and by_id[ref] is not scope
    ]
    found: list[HtmlElement] = []
    # The elements themselves, never their ``id()``: lxml makes a Python object
    # per element on demand and frees it after, so an ``id()`` is reused by the
    # next element and a set of them forgets properties on any large page.
    # Holding the element keeps its object alive, and lxml hands back that same
    # object for that element for as long as it lives.
    seen: set[HtmlElement] = set()
    for root in roots:
        pending = [root] if root is not scope else list(reversed(root))
        while pending:
            element = pending.pop()
            if not isinstance(element.tag, str) or element in seen:
                continue
            if not context.pay(1):
                break
            seen.add(element)
            if element.get("itemprop") is not None:
                found.append(element)
            if element.get("itemscope") is None:
                pending.extend(reversed(element))
    return sorted(found, key=lambda element: context.order.get(element, 0))


def _nearest_scope(element: HtmlElement) -> HtmlElement | None:
    """The closest itemscope ancestor of ``element``, or None if it has none."""
    parent = element.getparent()
    while parent is not None:
        if parent.get("itemscope") is not None:
            return parent
        parent = parent.getparent()
    return None


def _value(doc: Document, element: HtmlElement) -> str:
    """The text one itemprop declares: its value attribute, or its own text.

    An address attribute is resolved against the page, because the standard
    defines that property's value as the absolute URL and not as the text the
    attribute happens to hold.
    """
    attr = _VALUE_ATTRS.get(element.tag)
    if attr is not None:
        declared: str | None = element.get(attr)
        # A <time> without a datetime is its text; every other element in the
        # list is its attribute or nothing.
        if declared is not None or element.tag != "time":
            found = (declared or "").strip()
            return absolute(doc, found) if found and attr in _ADDRESSES else found
    content: str | None = element.get("content")
    if content:
        return content.strip()
    text: str | None = element.text_content()
    return " ".join((text or "").split())
