"""One spelling per address, which addresses make a site, and a page's links.

A crawl that compares addresses as they were written fetches one page many
times: ``HTTP://Example.com:80/a#top`` and ``http://example.com/a`` are the
same request. ``normalise`` writes every address the one way the crawl
compares, and each rule is a claim about what a server does, so they are few
and stated:

* the scheme and host are lowercased, a host's trailing dot dropped, a name
  outside ASCII written in its IDNA form, and a default port (80 for http,
  443 for https) removed;
* the fragment is dropped: it never reaches the server;
* an empty path is ``/``, and ``.`` and ``..`` segments are resolved;
* characters an address cannot carry are percent-encoded, and every escape is
  written in capitals, ``%2F`` rather than ``%2f``;
* the query is kept as written, its order included: a server may read
  ``?a=1&b=2`` and ``?b=2&a=1`` differently;
* a trailing slash is kept: ``/a`` and ``/a/`` are two addresses, because a
  server may answer them differently. Most sites redirect one to the other,
  and where a redirect landed is marked seen, so the second spelling is
  fetched again only when it was queued before the first was read.

An address carrying a user name or password, or a scheme other than http and
https, is not one a crawl takes.
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlsplit, urlunsplit

from sluicer.document import Document, absolute

MAX_LINKS_PER_PAGE = 5000
"""The most links one page contributes, in document order.

A page of fifty thousand links is a sitemap drawn in HTML, and every one of
them would be carried on that page's line of a crawl's output.
"""

_DEFAULT_PORTS = {"http": 80, "https": 443}
_ESCAPE = re.compile(r"%[0-9a-fA-F]{2}")
_PATH_SAFE = "/%:@!$&'()*+,;=-._~"
_QUERY_SAFE = _PATH_SAFE + "?"
# What a browser strips from inside an href before it reads it.
_INVISIBLE = str.maketrans("", "", "\t\n\r")

# Addresses that name a file rather than a page, by their last extension. A
# crawl reads pages; fetching a video to learn it declares nothing costs the
# site the video.
_FILES = frozenset(
    # One string, split: a list of seventy literals is seventy lines to read.
    (  # noqa: SIM905
        ".7z .aac .apk .avi .bin .bmp .bz2 .css .csv .deb .dmg .doc .docx .eot "
        ".epub .exe .flac .flv .gif .gz .heic .ico .iso .jar .jpeg .jpg .js .json "
        ".m4a .m4v .mkv .mov .mp3 .mp4 .mpeg .mpg .msi .odp .ods .odt .ogg .otf "
        ".pdf .png .ppt .pptx .rar .rpm .rss .svg .tar .tgz .tif .tiff .ttf .txt "
        ".wav .webm .webp .wmv .woff .woff2 .xls .xlsx .xml .xz .zip"
    ).split()
)


def normalise(url: str) -> str | None:
    """``url`` written the one way a crawl compares it, or None when a crawl
    cannot take it: not http(s), no host, a bad port, or credentials."""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or parts.username or parts.password:
        return None
    host = (parts.hostname or "").rstrip(".")
    if not host:
        return None
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            return None
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"
    path = _capitals(quote(_without_dot_segments(parts.path or "/"), safe=_PATH_SAFE))
    query = _capitals(quote(parts.query, safe=_QUERY_SAFE))
    return urlunsplit((scheme, netloc, path, query, ""))


def site_of(url: str) -> str:
    """The site ``url`` belongs to: its host without a leading ``www.``, and its
    port when that is not the default. Empty for an address a crawl cannot take.

    http and https are one site, and so are ``www.example.com`` and
    ``example.com``: a site serves both from the same machines far more often
    than not, and a crawl that paced them apart would ask it twice as often.
    Every other subdomain is a site of its own.
    """
    address = normalise(url)
    if address is None:
        return ""
    netloc = urlsplit(address).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def names_a_file(url: str) -> bool:
    """Whether ``url``'s path ends in an extension that names a file, not a page."""
    path = urlsplit(url).path.lower()
    last = path.rsplit("/", 1)[-1]
    return "." in last and last[last.rindex(".") :] in _FILES


def links_on(doc: Document) -> list[str]:
    """Every address the page lets a crawl follow, normalised, each once, in
    document order: ``<a href>`` and ``<area href>``, resolved against the
    page's ``<base>``.

    A page whose ``<meta name="robots">`` (or ``name="sluicer"``) says
    ``nofollow`` or ``none`` gives none, and a link marked ``rel="nofollow"``
    is left out: both are the site asking not to be walked from there.
    """
    if _says_nofollow(doc):
        return []
    found: dict[str, None] = {}
    for element in doc.tree.xpath("//a[@href] | //area[@href]"):
        if "nofollow" in (element.get("rel") or "").lower().split():
            continue
        href = (element.get("href") or "").strip().translate(_INVISIBLE)
        address = normalise(absolute(doc, href)) if href else None
        if address is not None:
            found.setdefault(address)
            if len(found) >= MAX_LINKS_PER_PAGE:
                break
    return list(found)


def canonical_of(doc: Document) -> str | None:
    """The page's ``<link rel="canonical">``, resolved and normalised, or None."""
    for element in doc.tree.xpath("//link[@rel][@href]"):
        if "canonical" in (element.get("rel") or "").lower().split():
            href = (element.get("href") or "").strip()
            if href:
                return normalise(absolute(doc, href))
    return None


def _says_nofollow(doc: Document) -> bool:
    for element in doc.tree.xpath("//meta[@name][@content]"):
        if (element.get("name") or "").strip().lower() in ("robots", "sluicer"):
            said = re.split(r"[\s,]+", (element.get("content") or "").lower())
            if "nofollow" in said or "none" in said:
                return True
    return False


def _without_dot_segments(path: str) -> str:
    """``path`` with ``.`` and ``..`` resolved, as RFC 3986 section 5.2.4 does."""
    kept: list[str] = []
    for segment in path.split("/"):
        if segment == "..":
            if len(kept) > 1:
                kept.pop()
        elif segment != ".":
            kept.append(segment)
    if path.endswith(("/.", "/..")):
        kept.append("")
    resolved = "/".join(kept)
    return resolved if resolved.startswith("/") else "/" + resolved


def _capitals(text: str) -> str:
    return _ESCAPE.sub(lambda escape: escape.group(0).upper(), text)
