"""One spelling for a type, whichever vocabulary syntax declared it.

JSON-LD writes ``Product``, ``schema:Product`` or ``http://schema.org/Product``;
microdata writes ``https://schema.org/Product``; RDFa writes a term under a
``vocab``. They are one type, and records fold on types, so they are read to one
name here, in one place, for every reader. Only schema.org is shortened: a type
from any other vocabulary keeps its full IRI, so a FOAF ``Person`` is never
mistaken for a schema.org one.
"""

from __future__ import annotations

import re

_SCHEMA_ORG = re.compile(r"(?i:https?://(?:www\.)?schema\.org/|schema:)([^\s/#?]+)/?")


def type_name(declared: str) -> str | None:
    """The name records fold on for one declared type, or None for nothing."""
    token = declared.strip()
    if not token:
        return None
    match = _SCHEMA_ORG.fullmatch(token)
    return match.group(1) if match else token
