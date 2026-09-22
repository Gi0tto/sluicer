"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json
from typing import Any

from sluicer.document import Document

_XPATH = "//script[@type]"
# How many references one path may follow. Enough for an article's publisher's
# logo, which is three hops on a Yoast page; bounded so a graph where every node
# points at every other still costs a fixed amount per record.
MAX_REFERENCE_HOPS = 3
_MEDIA_TYPE = "application/ld+json"


def read_jsonld(doc: Document) -> list[dict[str, Any]]:
    """Return every JSON-LD object in the page, with ``@graph`` flattened.

    A reference -- an object carrying nothing but an ``@id`` -- is replaced by
    the node on the same page that defines that ``@id``, in whichever block it
    sits, so an article that names its author by reference, as every Yoast
    page does, arrives with the author. A reference nobody on the page defines
    stays a reference. A node already being expanded on the way down is not
    expanded again, so a cycle ends, and neither is anything more than
    ``MAX_REFERENCE_HOPS`` references deep, so a graph where everything points
    at everything costs a bounded amount.

    Numbers are kept as the text the page wrote, so ``41.90`` stays ``41.90``
    rather than becoming the float ``41.9``.

    Blocks that are not valid JSON are skipped: a broken block is a fact about
    the page, not a reason to lose the good ones.

    Real pages spell the media type in every legal way, so it is matched
    ignoring case, surrounding whitespace and any parameters after a
    semicolon: "application/ld+json;charset=UTF-8" is the same media type as
    "application/LD+JSON".
    """
    found: list[dict[str, Any]] = []
    for script in doc.tree.xpath(_XPATH):
        if not _is_ld_json(script.get("type") or ""):
            continue
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw, parse_float=str, parse_int=str)
        except ValueError:
            continue
        found.extend(_flatten(parsed))
    index = _definitions(found)
    return [_resolve(node, index, _own_id(node), 0) for node in found]


def _is_ld_json(declared: str) -> bool:
    """Is this script's type attribute the JSON-LD media type?"""
    return declared.split(";", 1)[0].strip().lower() == _MEDIA_TYPE


def _flatten(parsed: object) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [item for entry in parsed for item in _flatten(entry)]
    if isinstance(parsed, dict):
        if "@graph" in parsed:
            return _flatten(parsed["@graph"])
        return [parsed]
    return []


def _own_id(node: dict[str, Any]) -> frozenset[str]:
    identifier = node.get("@id")
    return frozenset({identifier}) if isinstance(identifier, str) else frozenset()


def _definitions(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Every node on the page that defines an ``@id``, first definition first.

    A definition says something besides its identity; ``{"@id": ...}`` alone is
    a reference, and a reference is not what it refers to.
    """
    index: dict[str, dict[str, Any]] = {}
    # A stack pushed in reverse, so nodes are met in document order and the
    # first definition of an ``@id`` is the one kept.
    pending: list[object] = list(reversed(nodes))
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(reversed(value))
        elif isinstance(value, dict):
            identifier = value.get("@id")
            if isinstance(identifier, str) and not _is_reference(value):
                index.setdefault(identifier, value)
            pending.extend(reversed(list(value.values())))
    return index


def _is_reference(value: dict[str, Any]) -> bool:
    return isinstance(value.get("@id"), str) and all(
        key.startswith("@") and key != "@value" for key in value
    )


def _resolve(
    value: Any, index: dict[str, dict[str, Any]], path: frozenset[str], hops: int
) -> Any:
    """``value`` with every reference it holds replaced by what it names."""
    if isinstance(value, list):
        return [_resolve(item, index, path, hops) for item in value]
    if not isinstance(value, dict):
        return value
    if _is_reference(value):
        identifier = value["@id"]
        target = index.get(identifier)
        if target is None or identifier in path or hops >= MAX_REFERENCE_HOPS:
            return value
        return _resolve(target, index, path | {identifier}, hops + 1)
    return {
        key: _resolve(item, index, path | _own_id(value), hops)
        for key, item in value.items()
    }
