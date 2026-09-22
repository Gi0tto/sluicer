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
# fixed amount, and so an itemref that points back up cannot loop.
_MAX_DEPTH = 16


def read_microdata(doc: Document) -> list[dict[str, Any]]:
    """Return one dict per top-level item, with nested items inside it.

    A top-level item is an ``itemscope`` that is not itself somebody's
    property. An item that is a property is that property's value, so an
    ``Offer`` inside a ``Product`` arrives as the product's ``offers`` rather
    than as a record of its own. A property declared more than once is a list
    in document order; declared once, it is its value.
    """
    by_id = {
        element.get("id"): element for element in doc.tree.xpath("//*[@id]")
    }
    found: list[dict[str, Any]] = []
    for scope in doc.tree.xpath("//*[@itemscope]"):
        if scope.get("itemprop") is not None and _nearest_scope(scope) is not None:
            continue
        item = _item(doc, scope, by_id, 0)
        if item:
            found.append(item)
    return found


def _item(
    doc: Document,
    scope: HtmlElement,
    by_id: dict[str | None, HtmlElement],
    depth: int,
) -> dict[str, Any]:
    item: dict[str, Any] = {}
    types = [
        name
        for token in (scope.get("itemtype") or "").split()
        if (name := type_name(token))
    ]
    if types:
        item["@type"] = types[0] if len(types) == 1 else types
    repeated: set[str] = set()
    for prop in _properties(scope, by_id):
        names = (prop.get("itemprop") or "").split()
        if not names:
            continue
        value: Any
        if prop.get("itemscope") is not None:
            if depth >= _MAX_DEPTH:
                continue
            value = _item(doc, prop, by_id, depth + 1)
            if not any(not key.startswith("@") for key in value):
                continue
        else:
            value = _value(doc, prop)
            if not value:
                # An empty value is not a value: recording it here would
                # shadow the real one another reader may carry.
                continue
        for name in names:
            if name not in item:
                item[name] = value
            elif name in repeated:
                item[name].append(value)
            else:
                item[name] = [item[name], value]
                repeated.add(name)
    return item


def _properties(
    scope: HtmlElement, by_id: dict[str | None, HtmlElement]
) -> list[HtmlElement]:
    """The elements carrying ``scope``'s properties, in document order.

    Its own descendants whose nearest item is ``scope``, and the elements it
    names with ``itemref`` together with their descendants, stopping at any
    item on the way down, since what is inside that belongs to that item.
    """
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
            seen.add(element)
            if element.get("itemprop") is not None:
                found.append(element)
            if element.get("itemscope") is None:
                pending.extend(reversed(element))
    return found


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
