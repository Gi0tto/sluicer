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
    lowered = html.lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            # Check challenge markers before status: the more specific diagnosis
            # (a page standing in front of the content) is more useful than the
            # general status code. A reader learns a browser will likely succeed.
            return f"the response is a challenge page, not the content: {marker!r}"

    if status in _REFUSING_STATUSES:
        return f"the server refused: status {status}"
    if status >= 500:
        return None

    text = _TAGS.sub(" ", html).strip()
    # Both remaining rules are about a page that gave us nothing, so both are
    # off once records were found: a page that declared its data has delivered,
    # whatever its visible text looks like, and _TAGS strips <script> bodies,
    # so a complete JSON-LD block counts as zero characters of text. Climbing
    # there would buy a browser for a page we have already extracted.
    if not found_records and len(text) < TEXT_FLOOR and len(html) > MARKUP_CEILING:
        return (
            f"the body is skeletal: {len(text)} characters of text "
            f"inside {len(html)} of markup"
        )
    if not found_records and len(text) < TEXT_FLOOR:
        return f"nothing was declared and there are only {len(text)} characters of text"
    return None
