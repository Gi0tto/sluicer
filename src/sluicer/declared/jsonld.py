"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json
import re
from typing import Any

from sluicer.document import Document

_XPATH = "//script[@type]"
# How many references one path may follow. One is enough for what a reader of
# a record asks for -- an article's author, its publisher, its image -- and it is
# what keeps the output in proportion: measured on 2026-09-22 on a Yoast blog
# post, one hop gives 22 KB of JSON against 10 KB with none and 38 KB with
# three, because every record re-expands the same dense graph.
MAX_REFERENCE_HOPS = 1
# Deeper than anything downstream reads; see ``_resolve``.
_MAX_DEPTH = 32
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

    Blocks are read the way the consumers pages are written for read them: a
    raw newline inside a string, a block wrapped in an HTML comment or a CDATA
    section, a leading byte order mark and a trailing comma are all common, and
    none of them loses the block. What still is not JSON is skipped, and so is a
    block nested deeper than the parser can follow: a broken block is a fact
    about the page, not a reason to lose the good ones.

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
        parsed = _parse(raw)
        if parsed is not None:
            found.extend(_flatten(parsed))
    index = _definitions(found)
    # Every copy a reference makes is paid for from one budget, a multiple of
    # what the page itself holds: four thousand references to one node of four
    # thousand items were four gigabytes of copies from a 119 KB page. Past
    # the budget a reference stays a reference, in document order, so the
    # answer is the same every time.
    walk = _Walk(index, [max(10_000, 10 * _size(found))])
    return [walk.resolve(node, _own_id(node), 0) for node in found]


_OPENING = re.compile(r"^\s*(?:(?://|/\*)\s*)?(?:<!\[CDATA\[|<!--)\s*(?:\*/)?")
_CLOSING = re.compile(r"(?:(?://|/\*)\s*)?(?:\]\]>|-->)\s*(?:\*/)?\s*$")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _parse(raw: str) -> object | None:
    """The JSON in one block, or None when there is none to be had."""
    unwrapped = raw.lstrip("\ufeff")
    for _ in range(2):
        unwrapped = _CLOSING.sub("", _OPENING.sub("", unwrapped))
    # The cleaned spellings are tried only after the text as written fails, so
    # a block that is valid JSON is never rewritten.
    for candidate in dict.fromkeys(
        (raw, unwrapped, _TRAILING_COMMA.sub(r"\1", unwrapped))
    ):
        try:
            parsed: object = json.loads(
                candidate,
                strict=False,
                parse_float=str,
                parse_int=str,
                parse_constant=lambda _name: None,
            )
        except (ValueError, RecursionError):
            continue
        return parsed
    return None


def _is_ld_json(declared: str) -> bool:
    """Is this script's type attribute the JSON-LD media type?"""
    return declared.split(";", 1)[0].strip().lower() == _MEDIA_TYPE


def _flatten(parsed: object) -> list[dict[str, Any]]:
    """Every top-level node in one block, ``@graph`` and arrays unwrapped."""
    found: list[dict[str, Any]] = []
    pending = [parsed]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(reversed(value))
        elif isinstance(value, dict):
            if "@graph" in value:
                pending.append(value["@graph"])
            else:
                found.append(value)
    return found


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


class _Walk:
    """Reference resolution for one page: its definitions, and its budget."""

    def __init__(self, index: dict[str, dict[str, Any]], budget: list[int]) -> None:
        self.index = index
        self.budget = budget
        self.sizes: dict[str, int] = {}

    def resolve(
        self, value: Any, path: frozenset[str], hops: int, depth: int = 0
    ) -> Any:
        """``value`` with every reference it holds replaced by what it names.

        Below ``_MAX_DEPTH`` a value is returned as it is: nothing reads that
        deep, and a block nested nearly as far as the JSON parser allows would
        otherwise take this walk past Python's own recursion limit.
        """
        if depth > _MAX_DEPTH:
            return value
        if isinstance(value, list):
            return [self.resolve(item, path, hops, depth + 1) for item in value]
        if not isinstance(value, dict):
            return value
        if _is_reference(value):
            identifier = value["@id"]
            target = self.index.get(identifier)
            if target is None or identifier in path or hops >= MAX_REFERENCE_HOPS:
                return value
            # Not ``setdefault``: its default is evaluated on every call, and
            # sizing the same large node once per reference was the whole cost.
            size = self.sizes.get(identifier)
            if size is None:
                size = self.sizes[identifier] = _size(target)
            if size > self.budget[0]:
                return value
            self.budget[0] -= size
            return self.resolve(target, path | {identifier}, hops + 1, depth + 1)
        return {
            key: self.resolve(item, path | _own_id(value), hops, depth + 1)
            for key, item in value.items()
        }


def _size(value: Any) -> int:
    """How many values ``value`` holds, itself included, counted without recursing."""
    count = 0
    pending = [value]
    while pending:
        item = pending.pop()
        count += 1
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return count
