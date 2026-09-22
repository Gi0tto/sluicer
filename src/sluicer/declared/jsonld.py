"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json

from sluicer.document import Document

_XPATH = '//script[@type="application/ld+json"]'


def read_jsonld(doc: Document) -> list[dict]:
    """Return every JSON-LD object in the page, with ``@graph`` flattened.

    Blocks that are not valid JSON are skipped: a broken block is a fact about
    the page, not a reason to lose the good ones.
    """
    found: list[dict] = []
    for script in doc.tree.xpath(_XPATH):
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        found.extend(_flatten(parsed))
    return found


def _flatten(parsed: object) -> list[dict]:
    if isinstance(parsed, list):
        return [item for entry in parsed for item in _flatten(entry)]
    if isinstance(parsed, dict):
        if "@graph" in parsed:
            return _flatten(parsed["@graph"])
        return [parsed]
    return []
