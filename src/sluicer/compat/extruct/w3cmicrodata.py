"""Microdata in extruct's shape, read by the WHATWG standard's rules.

extruct's item is ``{"type", "id", "properties"}``: ``type`` the ``itemtype``
as written, a string for one and a list for several; ``id`` the ``itemid``;
``properties`` a mapping of each name to its value, or to a list when the name
is declared more than once. An item that declares no property is ``{"type",
"value"}``, its value read as a property's would be. A property's value is an
attribute (``content``, ``src``, ``href``, ``data``, ``value``, ``datetime``)
as written, or the element's text laid out by html-text's rules (see
``sluicer.compat.extruct.text``), or, for an item, the item.

Three of extruct's answers are not the standard's, and are not kept:

* ``itemref``. extruct walks every ``itemscope`` in document order and reads an
  item once. An item named by ``itemref`` from an item further down the page
  is therefore read as a top-level item of its own, and the property that
  names it is ``None``; so is every property naming an item a second time,
  as two products sharing one brand do. Here a property naming an item holds
  that item, wherever it sits and however many name it, an item that is some
  other item's property is never top-level, and properties are in tree
  order, as the standard orders them. A property that would hold an item
  already being read around it -- a cycle -- is left out.
* ``<base href>``. extruct resolves an address against the ``base_url`` it was
  given; the standard resolves it against the document's base URL, which the
  page's ``<base href>`` sets.
* ``<time>`` without ``datetime``. extruct answers ``""``; the standard's value
  is then the element's text.

An address attribute that is absent is ``""``, as the standard says; extruct
resolves it to the page's own address. An address that is present is
resolved with ``urljoin``, as extruct resolves it, and kept as written where
``urljoin`` refuses it and extruct raises.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Budget, Page, of_tree, read_page
from sluicer.compat.extruct.text import readable

# The elements whose value is an address, and the attribute that holds it.
_ADDRESSES = {
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
}
# The HTML standard's space characters, which an address may be wrapped in.
_SPACE = " \t\n\r\x0c"
# Deeper than any real page nests items; a bound so a hostile one costs a
# fixed amount of stack. extruct has none, and raises RecursionError on items
# nested about four hundred deep.
_MAX_DEPTH = 64


class _Spent(Exception):
    """The page's budget ran out; what was read before it is the answer."""


class LxmlMicrodataExtractor:
    """extruct's microdata extractor, with its four options.

    ``nested=False`` answers every item on the page, each with an ``iid``, its
    place among the page's items, and names an item held by a property as
    ``{"iid_ref": ...}``; ``strict=True`` makes every type and every property
    a list; ``add_text_content`` adds each item's text as ``textContent``;
    ``add_html_node`` adds its element as ``htmlNode``.
    """

    def __init__(
        self,
        nested: bool = True,
        strict: bool = False,
        add_text_content: bool = False,
        add_html_node: bool = False,
    ) -> None:
        self.nested = nested
        self.strict = strict
        self.add_text_content = add_text_content
        self.add_html_node = add_html_node

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
    ) -> list[dict[str, Any]]:
        return self.read(read_page(htmlstring, base_url, encoding))

    def extract_items(
        self, document: HtmlElement, base_url: str | None = None
    ) -> list[dict[str, Any]]:
        return self.read(of_tree(document, base_url))

    def read(self, page: Page) -> list[dict[str, Any]]:
        """Every top-level item on ``page``, in document order."""
        return _Walk(self, page).items()


MicrodataExtractor = LxmlMicrodataExtractor


class _Walk:
    """One page's items: its ids, its order, and its budget."""

    def __init__(self, options: LxmlMicrodataExtractor, page: Page) -> None:
        self.options = options
        self.page = page
        self.budget: Budget = page.budget()
        root = page.tree.getroottree().getroot()
        self.by_id: dict[str, HtmlElement] = {}
        for element in root.xpath("//*[@id]"):
            # The first element with an id, as the standard and XPath's id() say.
            self.by_id.setdefault(element.get("id"), element)
        self.order = {element: index for index, element in enumerate(root.iter())}
        self.number = {
            element: index + 1
            for index, element in enumerate(
                root.xpath("descendant-or-self::*[@itemscope]")
            )
        }

    def items(self) -> list[dict[str, Any]]:
        referenced = {
            self.by_id[ref]
            for scope in self.page.tree.xpath("descendant-or-self::*[@itemref]")
            for ref in (scope.get("itemref") or "").split()
            if ref in self.by_id
        }
        found: list[dict[str, Any]] = []
        for scope in self.page.tree.xpath("descendant-or-self::*[@itemscope]"):
            if (
                self.options.nested
                and scope.get("itemprop") is not None
                and (_nearest_scope(scope) is not None or _inside(scope, referenced))
            ):
                continue
            try:
                found.append(self.item(scope, frozenset({scope})))
            except _Spent:
                break
        return found

    def pay(self, cost: int) -> None:
        if not self.budget.pay(cost):
            raise _Spent

    def item(self, scope: HtmlElement, chain: frozenset[HtmlElement]) -> dict[str, Any]:
        options = self.options
        item: dict[str, Any] = {}
        if not options.nested:
            item["iid"] = self.number.get(scope, 0)
        types = (scope.get("itemtype") or "").split()
        if types:
            self.pay(sum(len(name) for name in types))
            item["type"] = types[0] if not options.strict and len(types) == 1 else types
            identifier = scope.get("itemid")
            if identifier:
                self.pay(len(identifier))
                item["id"] = identifier.strip()
        properties: dict[str, list[Any]] = {}
        for prop in self.properties(scope):
            names = (prop.get("itemprop") or "").split()
            before = self.budget.left
            value = self.value(prop, chain)
            if value is _CYCLE:
                continue
            size = before - self.budget.left
            for index, name in enumerate(names):
                # Every name after the first is one more copy of the value.
                self.pay(len(name) + (size if index else 0))
                properties.setdefault(name, []).append(value)
        if properties:
            item["properties"] = {
                name: values[0] if not options.strict and len(values) == 1 else values
                for name, values in properties.items()
            }
        else:
            item["value"] = self.value(scope, chain, force=True)
        if options.add_text_content:
            text = self.text(scope)
            if text:
                item["textContent"] = text
        if options.add_html_node:
            item["htmlNode"] = scope
        return item

    def properties(self, scope: HtmlElement) -> list[HtmlElement]:
        """The elements carrying ``scope``'s properties, in tree order.

        The standard's crawl: its own descendants, and the elements it names
        with ``itemref`` with theirs, stopping at any item on the way down,
        since what is inside that is that item's.
        """
        roots = [scope] + [
            self.by_id[ref]
            for ref in (scope.get("itemref") or "").split()
            if ref in self.by_id and self.by_id[ref] is not scope
        ]
        found: list[HtmlElement] = []
        seen: set[HtmlElement] = set()
        for root in roots:
            pending = [root] if root is not scope else list(reversed(root))
            while pending:
                element = pending.pop()
                if not isinstance(element.tag, str) or element in seen:
                    continue
                self.pay(1)
                seen.add(element)
                if element.get("itemprop") is not None:
                    found.append(element)
                if element.get("itemscope") is None:
                    pending.extend(reversed(element))
        return sorted(found, key=lambda element: self.order.get(element, 0))

    def value(
        self,
        element: HtmlElement,
        chain: frozenset[HtmlElement],
        force: bool = False,
    ) -> Any:
        """What one property declares, by the element carrying it."""
        if not force and element.get("itemscope") is not None:
            if not self.options.nested:
                return {"iid_ref": self.number.get(element, 0)}
            if element in chain or len(chain) > _MAX_DEPTH:
                return _CYCLE
            return self.item(element, chain | {element})
        tag = element.tag
        if tag == "meta":
            return self.paid(element.get("content", ""))
        attribute = _ADDRESSES.get(tag)
        if attribute is not None:
            address = element.get(attribute)
            if address is None:
                return ""
            return self.paid(_resolve(self.page.base, address.strip(_SPACE)))
        if tag in ("data", "meter"):
            return self.paid(element.get("value", ""))
        if tag == "time":
            declared = element.get("datetime")
            return self.text(element) if declared is None else self.paid(declared)
        content = element.get("content")
        if content:
            return self.paid(content)
        name = element.get("itemprop") or ""
        if name.endswith(("-input", "-output")):
            # schema.org's actions: the input's name, and whether it is required.
            action: dict[str, Any] = {}
            if "required" in element.attrib:
                action["valueRequired"] = True
            field_name = element.get("name")
            if field_name:
                action["valueName"] = self.paid(field_name)
            return action
        return self.text(element)

    def paid(self, text: str) -> str:
        self.pay(len(text))
        return text

    def text(self, element: HtmlElement) -> str:
        text = readable(element, self.budget)
        if text is None:
            raise _Spent
        return text


# A property that would hold an item already being read around it.
_CYCLE: Any = object()


def _resolve(base: str | None, address: str) -> str:
    """``address`` resolved as extruct resolves it, with ``urljoin``.

    Kept as written when ``urljoin`` refuses it -- the ``https://[domain]/``
    of an unfilled template -- where extruct raises.
    """
    if not base:
        return address
    try:
        return urljoin(base, address)
    except ValueError:
        return address


def _nearest_scope(element: HtmlElement) -> HtmlElement | None:
    """The closest ``itemscope`` ancestor of ``element``, or None."""
    parent = element.getparent()
    while parent is not None:
        if parent.get("itemscope") is not None:
            return parent
        parent = parent.getparent()
    return None


def _inside(element: HtmlElement, roots: set[HtmlElement]) -> bool:
    """Whether ``element`` is one of ``roots`` or sits inside one of them."""
    node: HtmlElement | None = element
    while node is not None:
        if node in roots:
            return True
        node = node.getparent()
    return False
