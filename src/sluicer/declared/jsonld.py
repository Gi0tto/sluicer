"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json
import re
from typing import Any

from sluicer.declared.located import Located, Place, xpath_of
from sluicer.document import Document

_XPATH = "//script[@type]"
# How many references one path may follow. One is enough for an article's
# author, publisher and image, and keeps the output in proportion: measured on
# 2026-09-22 on a Yoast blog post, one hop gives 22 KB of JSON against 10 KB
# with none and 38 KB with three, because every record re-expands the graph.
MAX_REFERENCE_HOPS = 1
# Deeper than anything downstream reads; see ``_Walk.resolve``.
_MAX_DEPTH = 32
_MEDIA_TYPE = "application/ld+json"


def read_jsonld(doc: Document) -> list[dict[str, Any]]:
    """Return every JSON-LD object in the page, with ``@graph`` flattened.

    A reference -- an object carrying nothing but an ``@id`` -- is replaced by
    the node on the page that defines that ``@id``, in whichever block it sits,
    so an article that names its author by reference (every Yoast page does)
    arrives with the author. A reference nobody defines stays a reference. A
    cycle ends, expansion stops at ``MAX_REFERENCE_HOPS``, and the total copied
    is bounded by a budget, so a hostile graph costs a fixed amount.

    Numbers keep the text the page wrote: ``41.90`` stays ``41.90``.

    Blocks are read as leniently as the consumers pages are written for: a raw
    newline inside a string, an HTML comment or CDATA wrapper, a byte order
    mark and a trailing comma are all common and none loses the block. What
    still is not JSON is skipped, and so is a block nested past the parser's
    limit; the good blocks on the page are kept.

    The media type is matched ignoring case, whitespace and parameters:
    "application/ld+json;charset=UTF-8" is "application/LD+JSON".
    """
    found: list[dict[str, Any]] = []
    places: list[Place] = []
    for script in doc.tree.xpath(_XPATH):
        if not _is_ld_json(script.get("type") or ""):
            continue
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        parsed = _parse(raw)
        if parsed is not None:
            # Every node of one block is placed from one string, its own.
            block: Place = xpath_of(script) + "#"
            for node, steps in _flatten(parsed):
                found.append(node)
                at = block
                for step in steps:
                    at = (at, step)
                places.append(at)
    index, defined_at = _definitions(found, places)
    # Every copy a reference makes is paid for from one budget, ten times what
    # the page holds, in values and in characters: four thousand references to
    # one node of four thousand items were four gigabytes of copies from a
    # 119 KB page. Past the budget
    # a reference stays a reference, in document order, so the answer is
    # deterministic.
    walk = _Walk(index, [max(10_000, 10 * _size(found))], defined_at)
    # A top-level node is a dict, and resolving one gives a dict back; one
    # that was only a reference is where its definition is.
    return [
        resolved
        if isinstance(resolved := walk.resolve(node, _own_id(node), 0), Located)
        else Located(resolved, at)
        for node, at in zip(found, places, strict=True)
    ]


_OPENING = re.compile(r"^\s*(?:(?://|/\*)\s*)?(?:<!\[CDATA\[|<!--)\s*(?:\*/)?")
_CLOSING = re.compile(r"(?:(?://|/\*)\s*)?(?:\]\]>|-->)\s*(?:\*/)?\s*$")
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _parse(raw: str, as_written: bool = True) -> object | None:
    """The JSON in one block, or None when there is none to be had.

    ``as_written`` keeps every number as its text; without it the block is
    read as ``json.loads`` reads it, which is what extruct's callers get.
    """
    unwrapped = raw.lstrip("\ufeff")
    for _ in range(2):
        unwrapped = _CLOSING.sub("", _OPENING.sub("", unwrapped))
    # The cleaned spellings are tried only after the text as written fails, so
    # a block that is valid JSON is never rewritten.
    for candidate in dict.fromkeys(
        (raw, unwrapped, _TRAILING_COMMA.sub(r"\1", unwrapped))
    ):
        try:
            parsed: object = (
                json.loads(
                    candidate,
                    strict=False,
                    parse_float=str,
                    parse_int=str,
                    parse_constant=lambda _name: None,
                )
                if as_written
                else json.loads(candidate, strict=False)
            )
        except (ValueError, RecursionError):
            continue
        return parsed
    return None


def _is_ld_json(declared: str) -> bool:
    """Is this script's type attribute the JSON-LD media type?"""
    return declared.split(";", 1)[0].strip().lower() == _MEDIA_TYPE


def _flatten(parsed: object) -> list[tuple[dict[str, Any], tuple[str | int, ...]]]:
    """Every top-level node in one block, ``@graph`` and arrays unwrapped.

    Each with the steps that lead to it inside the block -- ``("@graph", 1)``
    -- which make its JSON pointer.
    """
    found: list[tuple[dict[str, Any], tuple[str | int, ...]]] = []
    pending: list[tuple[object, tuple[str | int, ...]]] = [(parsed, ())]
    while pending:
        value, steps = pending.pop()
        if isinstance(value, list):
            pending.extend(
                (item, (*steps, n)) for n, item in reversed(list(enumerate(value)))
            )
        elif isinstance(value, dict):
            if "@graph" in value:
                pending.append((value["@graph"], (*steps, "@graph")))
            else:
                found.append((value, steps))
    return found


def _own_id(node: dict[str, Any]) -> frozenset[str]:
    identifier = node.get("@id")
    return frozenset({identifier}) if isinstance(identifier, str) else frozenset()


def _definitions(
    nodes: list[dict[str, Any]], places: list[Place]
) -> tuple[dict[str, dict[str, Any]], dict[str, Place]]:
    """Every node on the page that defines an ``@id``, first definition first.

    A definition says something besides its identity; ``{"@id": ...}`` alone is
    a reference, and a reference is not what it refers to. Beside the index,
    where each definition sits.
    """
    index: dict[str, dict[str, Any]] = {}
    defined_at: dict[str, Place] = {}
    # A stack pushed in reverse, so nodes are met in document order and the
    # first definition of an ``@id`` is the one kept.
    pending: list[tuple[object, Place]] = list(
        reversed(list(zip(nodes, places, strict=True)))
    )
    while pending:
        value, chain = pending.pop()
        if isinstance(value, list):
            pending.extend(
                (item, (chain, n)) for n, item in reversed(list(enumerate(value)))
            )
        elif isinstance(value, dict):
            identifier = value.get("@id")
            if (
                isinstance(identifier, str)
                and not _is_reference(value)
                and identifier not in index
            ):
                index[identifier] = value
                defined_at[identifier] = chain
            pending.extend(
                (item, (chain, key)) for key, item in reversed(list(value.items()))
            )
    return index, defined_at


def _is_reference(value: dict[str, Any]) -> bool:
    return isinstance(value.get("@id"), str) and all(
        key.startswith("@") and key != "@value" for key in value
    )


class _Walk:
    """Reference resolution for one page: its definitions, and its budget."""

    def __init__(
        self,
        index: dict[str, dict[str, Any]],
        budget: list[int],
        defined_at: dict[str, Place],
    ) -> None:
        self.index = index
        self.budget = budget
        self.defined_at = defined_at
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
            # What a reference is replaced by was declared at its definition.
            return Located(
                self.resolve(target, path | {identifier}, hops + 1, depth + 1),
                self.defined_at[identifier],
            )
        return {
            key: self.resolve(item, path | _own_id(value), hops, depth + 1)
            for key, item in value.items()
        }


def _size(value: Any) -> int:
    """What a copy of ``value`` costs, counted without recursing.

    One for every value, itself included, and one for every character of its
    text and of its keys. Counting values alone priced a node holding one long
    string at three, so four hundred references to a 4,000-character name were
    copied in full: 1.6 MB of JSON from a 10 KB page.
    """
    count = 0
    pending = [value]
    while pending:
        item = pending.pop()
        count += 1
        if isinstance(item, str):
            count += len(item)
        elif isinstance(item, dict):
            count += sum(len(key) for key in item)
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return count
