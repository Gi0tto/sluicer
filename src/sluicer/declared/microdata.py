"""Read schema.org microdata: itemscope, itemtype, itemprop."""

from __future__ import annotations

from lxml.html import HtmlElement

from sluicer.document import Document

_VALUE_ATTRS = {
    "meta": "content",
    "a": "href",
    "link": "href",
    "img": "src",
    "time": "datetime",
}


def read_microdata(doc: Document) -> list[dict[str, str]]:
    """Return one dict per itemscope element found in the page.

    A property belongs to the nearest itemscope enclosing it, so the
    properties of a nested item stay with that item and never leak into the
    item around it. A property that is itself an itemscope declares an
    object, and this slice carries scalars only: rather than invent a value
    out of the nested block's text, it is left out of the enclosing item and
    survives as a record of its own. A lost block, never a wrong value."""
    found: list[dict[str, str]] = []
    for scope in doc.tree.xpath("//*[@itemscope]"):
        item: dict[str, str] = {}
        itemtype = scope.get("itemtype")
        if itemtype:
            item["@type"] = itemtype.rstrip("/").rsplit("/", 1)[-1]
        for prop in scope.xpath(".//*[@itemprop]"):
            if prop.get("itemscope") is not None:
                continue
            if _nearest_scope(prop) is not scope:
                continue
            name = prop.get("itemprop")
            if not name or name in item:
                continue
            value = _value(prop)
            if not value:
                # An empty value is not a value: recording it here would
                # shadow the real one another reader may carry.
                continue
            item[name] = value
        # Keep any non-empty item; filter out scopes that yielded nothing at all.
        if item:
            found.append(item)
    return found


def _nearest_scope(element: HtmlElement) -> HtmlElement | None:
    """The closest itemscope ancestor of ``element``, or None if it has none.

    ``HtmlElement`` and not ``object``: this walks ``getparent()`` and reads
    attributes, so the annotation said the function took anything at all while
    the body required a parsed element. lxml ships no type information, so the
    name resolves to ``Any`` and buys no checking -- but it is what a reader is
    told, and what was written down was not true.
    """
    parent = element.getparent()
    while parent is not None:
        if parent.get("itemscope") is not None:
            return parent
        parent = parent.getparent()
    return None


def _value(element: HtmlElement) -> str:
    """The text one itemprop declares: its value attribute, or its own text.

    Each attribute is read into a ``str | None`` before it is used rather than
    fetched twice, which is both what lxml returns and one call instead of two
    for the same answer.
    """
    attr = _VALUE_ATTRS.get(element.tag)
    if attr is not None:
        declared: str | None = element.get(attr)
        if declared:
            return declared.strip()
    content: str | None = element.get("content")
    if content:
        return content.strip()
    text: str | None = element.text_content()
    return (text or "").strip()
