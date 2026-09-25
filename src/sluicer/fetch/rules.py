"""When a cheap fetch is not good enough, and how we know.

Every rule here answers one question: did we get the page, or did we get
something standing in front of it? A rule that cannot be measured from the
response alone does not belong in this file.
"""

from __future__ import annotations

import re
from html import unescape

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
# "Client Challenge" is Fastly's, which PyPI answers a client without
# JavaScript with; "Making sure you're not a bot!" is Anubis's; "One moment,
# please..." a waiting room that posts a form and reloads, met on four sites.
_CHALLENGE_TITLES = frozenset(
    {
        "just a moment",
        "attention required! | cloudflare",
        "ddos-guard",
        "client challenge",
        "making sure you're not a bot!",
        "one moment, please",
    }
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
    # Fastly's challenge serves its scripts and styles from this path, Imperva
    # its own from /_Incapsula_Resource, HUMAN draws its puzzle into
    # #px-captcha, and Anubis hands its proof of work over in a script of
    # this id; a page that names them in its text is past the text ceiling.
    "/_fs-ch-",
    "/_incapsula_resource",
    "px-captcha",
    "anubis_challenge",
)

_TITLE_OPENS = re.compile(r"(?i)<title\b")
_TITLE_CLOSES = re.compile(r"(?i)</title>")
# The elements whose content is stripped with their tags: a script's code and
# a style sheet are no text a reader sees.
_STRIPPED_WHOLE = ("script", "style")
# A script that runs: one with a source, or an inline one that is not data.
_SCRIPT = re.compile(
    r"<script\b(?![^>]*\btype\s*=\s*[\"']?application/(?:ld\+)?json)[^>]*>",
    re.IGNORECASE,
)


def why_climb(status: int, html: str, found_records: bool) -> str | None:
    """Return the reason to climb a rung, or None to stay where we are."""
    text = strip_tags(html).strip()
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
    # off once something was declared about a thing: strip_tags drops <script>
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
    return _challenge(html, strip_tags(html).strip(), found_records)


def _challenge(html: str, text: str, found_records: bool) -> str | None:
    """The marker that makes ``html`` a challenge page, or None when it is not.

    A title that is the challenge counts on any page. A marker anywhere else
    counts only on a page that is not content: nothing declared about a thing,
    and less visible text than ``CHALLENGE_TEXT_CEILING``.
    """
    title = page_title(html)
    if title is not None:
        said = " ".join(unescape(title).split()).lower().rstrip(".\u2026 ")
        if said in _CHALLENGE_TITLES or said.startswith(_CHALLENGE_TITLE_PREFIXES):
            return said
    if found_records or len(text) >= CHALLENGE_TEXT_CEILING:
        return None
    lowered = html.lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            return marker
    return None


def strip_tags(html: str) -> str:
    """``html`` with each tag, and each script and style whole, as one space.

    A ``<script>`` or ``<style>`` goes with everything up to its end tag, and
    one never closed is a tag like any other; a ``<`` with no ``>`` after it
    is text. The pattern that did this, ``<(script|style).*?</\\1>|<[^>]+>``,
    looked for the end tag again from every place one opened: a page of a
    hundred thousand unclosed ``<script>`` tags took a minute, after its
    fetch and outside every deadline. Here each end is looked for once.
    """
    ends = {name: _Next(html, f"</{name}>") for name in _STRIPPED_WHOLE}
    closing = _Next(html, ">")
    kept: list[str] = []
    copied = at = 0
    while (at := html.find("<", at)) != -1:
        end = -1
        for name in _STRIPPED_WHOLE:
            if html.startswith(name, at + 1):
                close = ends[name].at_or_after(at + 1 + len(name))
                if close != -1:
                    end = close + len(name) + 3
                break
        if end == -1:
            close = closing.at_or_after(at + 1)
            if close > at + 1:
                end = close + 1
        if end == -1:
            at += 1
            continue
        kept += (html[copied:at], " ")
        copied = at = end
    kept.append(html[copied:])
    return "".join(kept)


def page_title(html: str) -> str | None:
    """The text of the page's first ``<title>``, as written, or None.

    Only the first opening can answer: a later one has its ``>`` and its end
    tag no sooner. Asked from every opening, as a pattern does, a page of
    forty thousand unclosed ``<title>`` tags took seconds.
    """
    opening = _TITLE_OPENS.search(html)
    if opening is None:
        return None
    start = html.find(">", opening.end())
    if start == -1:
        return None
    close = _TITLE_CLOSES.search(html, start + 1)
    return html[start + 1 : close.start()] if close else None


class _Next:
    """Where ``needle`` next starts in ``text``, asked at points that only
    move forward: each place is found once, whatever the number of askings.
    """

    __slots__ = ("found", "needle", "text")

    def __init__(self, text: str, needle: str) -> None:
        self.text, self.needle = text, needle
        self.found: int | None = None

    def at_or_after(self, point: int) -> int:
        found = self.found
        if found is not None and (found == -1 or found >= point):
            return found
        self.found = found = self.text.find(self.needle, point)
        return found
