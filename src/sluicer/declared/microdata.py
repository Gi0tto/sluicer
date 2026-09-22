"""Read schema.org microdata: itemscope, itemtype, itemprop."""

from __future__ import annotations

from sluicer.document import Document

_VALUE_ATTRS = {
    "meta": "content",
    "a": "href",
    "link": "href",
    "img": "src",
    "time": "datetime",
}


def read_microdata(doc: Document) -> list[dict]:
    """Return one dict per itemscope element found in the page."""
    found: list[dict] = []
    for scope in doc.tree.xpath("//*[@itemscope]"):
        item: dict = {}
        itemtype = scope.get("itemtype")
        if itemtype:
            item["@type"] = itemtype.rstrip("/").rsplit("/", 1)[-1]
        for prop in scope.xpath(".//*[@itemprop]"):
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


def _value(element: object) -> str:
    attr = _VALUE_ATTRS.get(element.tag)
    if attr and element.get(attr):
        return element.get(attr).strip()
    if element.get("content"):
        return element.get("content").strip()
    return (element.text_content() or "").strip()
