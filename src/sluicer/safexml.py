"""The checks every XML file sluicer reads goes through before libxml2 does.

A sitemap and a feed are files anyone can write, and XML can declare entities
that expand into more text than the file holds -- the billion laughs -- or
point outside the file. Such a document is refused before it is parsed, and
whatever is parsed is parsed with entities left alone and the network off.
"""

from __future__ import annotations

import re
from itertools import islice

_ENTITY = re.compile(rb"<!ENTITY", re.IGNORECASE)
_DOCTYPE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)
_EXTERNAL_OR_SUBSET = re.compile(rb"\[|\bSYSTEM\b|\bPUBLIC\b", re.IGNORECASE)


def declares_what_expands(text: bytes) -> bool:
    """Whether ``text`` declares an entity, or a document type with an internal
    subset or an external identifier -- or more than one document type, which
    no well-formed document has.

    A bare ``<!DOCTYPE html>`` holds nothing to expand, and is left to the
    parser, which reports the soft 404 it usually is as not a sitemap.
    """
    if _ENTITY.search(text):
        return True
    found = [match.end() for match in islice(_DOCTYPE.finditer(text), 2)]
    if not found:
        return False
    if len(found) > 1:
        return True
    end = text.find(b">", found[0])
    return bool(
        _EXTERNAL_OR_SUBSET.search(text, found[0], end if end >= 0 else len(text))
    )


def as_text(data: bytes) -> bytes:
    """``data`` as bytes a pattern can search: UTF-16 is decoded first, since
    its every other byte is zero and ``<!DOCTYPE`` would not be found in it."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace").encode("utf-8")
    return data
