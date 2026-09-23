"""robots.txt's path patterns, which TDMRep and the aipref drafts reuse.

A pattern matches a URL's path, query included, as a prefix: ``*`` is any run
of characters and a final ``$`` ends the path (RFC 9309, section 2.2.3). One
matcher for every file that writes them -- robots.txt's Content-Usage and
Content-Signal rules, TDMRep's ``tdmrep.json`` -- so they cannot disagree.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def target_of(url: str) -> str:
    """The part of ``url`` a path pattern is matched against."""
    parts = urlsplit(url)
    return (parts.path or "/") + (f"?{parts.query}" if parts.query else "")


def matches(pattern: str, target: str) -> bool:
    """Whether ``pattern`` matches ``target``, a path with its query.

    Matched with two pointers, not a regular expression: ``/*a*a*a*a*b$`` took
    a backtracking regular expression 13 seconds against a 300-character
    path, and these files are anyone's to write.
    """
    anchored = pattern.endswith("$")
    written = pattern[:-1] if anchored else pattern + "*"
    at = seen = 0
    star = mark = -1
    while seen < len(target):
        if at < len(written) and written[at] == "*":
            star, mark = at, seen
            at += 1
        elif at < len(written) and written[at] == target[seen]:
            at += 1
            seen += 1
        elif star != -1:
            at, mark = star + 1, mark + 1
            seen = mark
        else:
            return False
    return all(char == "*" for char in written[at:])
