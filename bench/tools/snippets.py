"""How trafilatura's evaluation counts a main text's snippets, for every output.

Imported by ``evaldata_body.py`` and ``evaldata_html_to_markdown.py``, which
run in different environments, so it needs nothing but Python. A page's
"with" snippet found in the output is a true positive, a "without" snippet
found a false positive, spaces normalised on both sides
(``tests/eval_common.py``, count_item).
"""

from __future__ import annotations

import codecs
import re
from typing import Any

# The charset a page declares, in a <meta> or an http-equiv content.
_CHARSET = re.compile(rb"""charset\s*=\s*["']?\s*([A-Za-z0-9._:-]+)""", re.I)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def counted(page: dict[str, Any], output: str | None) -> list[int]:
    """``[found, leaked, missed, kept out]`` for one page's output."""
    text = norm(output or "")
    found = sum(1 for snippet in page["with"] if norm(snippet) in text)
    leaked = sum(1 for snippet in page["without"] if norm(snippet) in text)
    return [found, leaked, len(page["with"]) - found, len(page["without"]) - leaked]


def as_text(html: bytes) -> str:
    """A page's bytes as text, for a tool that takes only text: UTF-8 when
    they are UTF-8, otherwise the charset the first 5,000 bytes declare,
    otherwise windows-1252, a byte that does not decode replaced
    (``bench/PREREG.md``)."""
    try:
        return html.decode("utf-8")
    except UnicodeDecodeError:
        pass
    declared = _CHARSET.search(html[:5000])
    if declared:
        try:
            encoding = codecs.lookup(declared.group(1).decode("ascii")).name
        except (LookupError, UnicodeDecodeError):
            encoding = ""
        if encoding:
            return html.decode(encoding, "replace")
    return html.decode("windows-1252", "replace")
