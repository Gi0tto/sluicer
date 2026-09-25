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

CHALLENGE_TEXT_CEILING = 1500
"""Characters of visible text above which a page is content, whatever it says.

A challenge page is a sentence or two. An article that quotes "just a moment",
or a shop page carrying Cloudflare's bot-detection script, is not one.
"""

# A title that is the challenge itself, compared whole: "Just a moment: the
# minister answers" is a headline, "Just a moment..." is a waiting room.
_CHALLENGE_TITLES = frozenset(
    {"just a moment", "attention required! | cloudflare", "ddos-guard"}
)
_CHALLENGE_TITLE_PREFIXES = ("checking your browser",)

# Anywhere on a page that is not content. ``challenge-platform`` alone is not
# enough on a full page: Cloudflare injects a script from that path into
# ordinary pages it only watches.
_CHALLENGE_MARKERS = (
    "cf-challenge",
    "challenge-platform",
    "just a moment",
    "checking your browser",
    "__cf_chl",
    "enable javascript and cookies to continue",
)

_TITLE = re.compile(r"(?is)<title\b[^>]*>(.*?)</title>")
_TAGS = re.compile(r"(?s)<(script|style).*?</\1>|<[^>]+>")
# A script that runs: one with a source, or an inline one that is not data.
_SCRIPT = re.compile(
    r"<script\b(?![^>]*\btype\s*=\s*[\"']?application/(?:ld\+)?json)[^>]*>",
    re.IGNORECASE,
)


def why_climb(status: int, html: str, found_records: bool) -> str | None:
    """Return the reason to climb a rung, or None to stay where we are."""
    text = _TAGS.sub(" ", html).strip()
    marker = _challenge(html, text, found_records)
    if marker is not None:
        # Before the status: "a page standing in front of the content" is the
        # more useful diagnosis, and says a browser will likely get through.
        return f"the response is a challenge page, not the content: {marker!r}"

    if status in _REFUSING_STATUSES:
        return f"the server refused: status {status}"
    if status >= 400:
        # A 404 or a 5xx is the site's answer about this address, and a browser
        # asking the same question gets the same answer.
        return None

    # Both remaining rules are about a page that gave us nothing, so both are
    # off once something was declared about a thing: _TAGS strips <script>
    # bodies, so a complete JSON-LD block counts as zero characters of text,
    # and climbing would buy a browser for a page already extracted.
    if found_records or len(text) >= TEXT_FLOOR:
        return None
    if len(html) > MARKUP_CEILING:
        return (
            f"the body is skeletal: {len(text)} characters of text "
            f"inside {len(html)} of markup"
        )
    # A small page is often simply small -- example.com is 152 characters and
    # complete. It is only a shell waiting for a browser when it runs a script
    # that could fill it.
    if _SCRIPT.search(html):
        return (
            f"nothing was declared, there are only {len(text)} characters of "
            "text, and the page runs a script that may render the rest"
        )
    return None


def challenge_marker(html: str, found_records: bool) -> str | None:
    """The marker that makes ``html`` a challenge page, or None when it is not.

    ``why_climb``'s first rule, alone: whatever the status, a page that is
    this is the site standing in front of the content, never the content.
    """
    return _challenge(html, _TAGS.sub(" ", html).strip(), found_records)


def _challenge(html: str, text: str, found_records: bool) -> str | None:
    """The marker that makes ``html`` a challenge page, or None when it is not.

    A title that is the challenge counts on any page. A marker anywhere else
    counts only on a page that is not content: nothing declared about a thing,
    and less visible text than ``CHALLENGE_TEXT_CEILING``.
    """
    title = _TITLE.search(html)
    if title is not None:
        said = " ".join(title.group(1).split()).lower().rstrip(".\u2026 ")
        if said in _CHALLENGE_TITLES or said.startswith(_CHALLENGE_TITLE_PREFIXES):
            return said
    if found_records or len(text) >= CHALLENGE_TEXT_CEILING:
        return None
    lowered = html.lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            return marker
    return None
