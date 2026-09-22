"""When a cheap fetch is not good enough, and how we know.

Every rule here answers one question: did we get the page, or did we get
something standing in front of it? A rule that cannot be measured from the
response alone does not belong in this file.
"""

from __future__ import annotations

import re

TEXT_FLOOR = 200
"""Characters of visible text below which a page has told us almost nothing."""

MARKUP_CEILING = 2000
"""Characters of markup above which a page promised more than it delivered."""

_REFUSING_STATUSES = frozenset({401, 403, 407, 429})

_CHALLENGE_MARKERS = (
    "cf-challenge",
    "challenge-platform",
    "just a moment",
    "checking your browser",
    "__cf_chl",
    "enable javascript and cookies to continue",
)

_TAGS = re.compile(r"(?s)<(script|style).*?</\1>|<[^>]+>")


def why_climb(status: int, html: str, found_records: bool) -> str | None:
    """Return the reason to climb a rung, or None to stay where we are."""
    if status in _REFUSING_STATUSES:
        return f"the server refused: status {status}"
    if status >= 500:
        return None

    lowered = html.lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            return f"the response is a challenge page, not the content: {marker!r}"

    text = _TAGS.sub(" ", html).strip()
    if len(text) < TEXT_FLOOR and len(html) > MARKUP_CEILING:
        return (
            f"the body is skeletal: {len(text)} characters of text "
            f"inside {len(html)} of markup"
        )
    if not found_records and len(text) < TEXT_FLOOR:
        return f"nothing was declared and there are only {len(text)} characters of text"
    return None
