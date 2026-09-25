"""JSON-LD in extruct's shape: each block's objects, exactly as the page wrote them.

No ``@graph`` is flattened and no reference resolved, as in extruct; numbers
are Python numbers, as ``json.loads`` makes them. A block's text is read as
extruct reads it: with ``json.loads``; failing that, with its first line
dropped when that line is a comment, and JavaScript's comments and a trailing
comma removed, as the jstyleson extruct calls removes them. So a block extruct
cannot read gives nothing here either: a comment or CDATA wrapper around the
JSON, a byte order mark, a comment left open. sluicer's own reader (see
``sluicer.declared.jsonld``) forgives all of those, and ``sluicer.extract``
keeps them; extruct's interface answers what extruct answers.

Two things differ, both documented in ``docs/extruct.md``. Which blocks are
read: extruct reads a block whose ``type`` is ``application/ld+json`` spelt
exactly so, and here the media type is matched ignoring case and parameters,
as sluicer's reader matches it. And what a block that is not JSON does:
extruct raises, and with its default ``errors="strict"`` that one block loses
the whole page's extraction, every other syntax included; here it is skipped,
so the page's other blocks are kept. Measured on the 360 WCXB pages as
served, four pages raise so in extruct; two of them for a block holding
nothing but whitespace.
"""

from __future__ import annotations

import json
import re
from typing import Any

from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Page, of_tree, read_page
from sluicer.declared.jsonld import _STRING, _TRAILING_COMMA, _is_ld_json

# extruct's HTML_OR_JS_COMMENTLINE: a comment on the block's first line, and
# only there, since neither ``^`` nor ``.`` crosses a line.
_FIRST_LINE_COMMENT = re.compile(r"^\s*(//.*|<!--.*-->)")
# jstyleson's comments: a line comment with the line's end, a block comment
# closed. One left open at the end of the text is kept, and fails to parse.
_CLOSED_COMMENT = re.compile(_STRING + r"|//[^\n]*\n|/\*.*?\*/", re.DOTALL)


class JsonLdExtractor:
    """extruct's JSON-LD extractor."""

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
    ) -> list[Any]:
        return self.read(read_page(htmlstring, base_url, encoding))

    def extract_items(
        self, document: HtmlElement, base_url: str | None = None
    ) -> list[Any]:
        return self.read(of_tree(document, base_url))

    def read(self, page: Page) -> list[Any]:
        """Every object in every block, a block's top-level list unwrapped.

        What is falsy -- an empty object, a ``null`` in a top-level list -- is
        dropped, as extruct drops it.
        """
        found: list[Any] = []
        for script in page.tree.xpath("descendant-or-self::script[@type]"):
            if not _is_ld_json(script.get("type") or ""):
                continue
            # Unstripped, as extruct reads it: a line comment ends at the
            # line's end, and the text's last one may end the text.
            raw = script.text_content() or ""
            if not raw.strip():
                continue
            parsed = _as_extruct_reads(raw)
            if isinstance(parsed, list):
                found.extend(item for item in parsed if item)
            elif isinstance(parsed, dict) and parsed:
                found.append(parsed)
        return found


def _as_extruct_reads(raw: str) -> object | None:
    """The JSON in one block as extruct reads it, or None where extruct raises."""
    try:
        parsed: object = json.loads(raw, strict=False)
    except RecursionError:
        return None
    except ValueError:
        pass
    else:
        return parsed
    text = _FIRST_LINE_COMMENT.sub("", raw)
    # Outside strings only, as jstyleson reads them; a comment is removed, not
    # made a space.
    text = _CLOSED_COMMENT.sub(lambda m: m[0] if m[0].startswith('"') else "", text)
    text = _TRAILING_COMMA.sub(lambda m: m[0] if m[0].startswith('"') else "", text)
    try:
        parsed = json.loads(text, strict=False)
    except (ValueError, RecursionError):
        return None
    return parsed
