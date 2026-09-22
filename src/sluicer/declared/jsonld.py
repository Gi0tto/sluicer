"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json

from sluicer.document import Document

_XPATH = "//script[@type]"
_MEDIA_TYPE = "application/ld+json"


def read_jsonld(doc: Document) -> list[dict]:
    """Return every JSON-LD object in the page, with ``@graph`` flattened.

    Blocks that are not valid JSON are skipped: a broken block is a fact about
    the page, not a reason to lose the good ones.

    Real pages spell the media type in every legal way, so it is matched
    ignoring case, surrounding whitespace and any parameters after a
    semicolon: "application/ld+json;charset=UTF-8" is the same media type as
    "application/LD+JSON".
    """
    found: list[dict] = []
    for script in doc.tree.xpath(_XPATH):
        if not _is_ld_json(script.get("type") or ""):
            continue
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        found.extend(_flatten(parsed))
    return found


def _is_ld_json(declared: str) -> bool:
    """Is this script's type attribute the JSON-LD media type?"""
    return declared.split(";", 1)[0].strip().lower() == _MEDIA_TYPE


def _flatten(parsed: object) -> list[dict]:
    if isinstance(parsed, list):
        return [item for entry in parsed for item in _flatten(entry)]
    if isinstance(parsed, dict):
        if "@graph" in parsed:
            return _flatten(parsed["@graph"])
        return [parsed]
    return []
