"""A page cache that asks the site whether a page changed, not guesses.

Opt-in and on disk: ``Cache(directory)`` keeps each page a fetch brought
back with the validators its server sent, ``ETag`` and ``Last-Modified``.
Asked for the page again, ``fetch_cached`` sends them (``If-None-Match``,
``If-Modified-Since``), and a server that answers 304 has said nothing
changed: the kept page is given back, marked ``revalidated``, for the price of
a request with no body. That is the whole of it for freshness, save one rule
the caller states: with ``max_age``, a page younger than that is given back
without asking the site at all. Nothing is guessed from ``Last-Modified``, as
HTTP caches may, and ``Cache-Control`` is not read: a monitor asks what it
means to ask.

Only a page that answered 2xx and is not a challenge is kept, so a refusal,
an error page or a waiting room served with 200 is never given back as the
page. The revalidating request is a
fetch like any other -- robots.txt, the size bound, private addresses
refused -- and a page that changed into one a browser must fetch is fetched
again through the whole ladder. Every page given back from the cache says so,
in ``Fetched.cached``, with its age.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from sluicer.api import extract
from sluicer.declared.headers import charset
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import sniff_encoding
from sluicer.fetch.address import _resolve
from sluicer.fetch.http_rung import Response
from sluicer.fetch.ladder import (
    FetchFailed,
    PaymentRequired,
    fetch,
    robots_reader_from,
)
from sluicer.fetch.result import MAX_RESPONSE_BYTES, CacheHit, EmptyBody, Fetched, Rung
from sluicer.fetch.rules import challenge_marker, why_climb

# Bumped when what an entry holds changes, so an old entry is not trusted.
_FORMAT = 1
# The headers kept with a page: what reading it needs, and its validators.
# Never its cookies.
_KEPT = frozenset(
    {
        "content-type",
        "link",
        "x-robots-tag",
        "tdm-reservation",
        "tdm-policy",
        "content-usage",
        "etag",
        "last-modified",
    }
)

Transport = Callable[[str, Mapping[str, str]], Response]
"""An address and the headers to send in, the ``Response`` out."""


class Cache:
    """Pages kept in ``directory``, one JSON file each, keyed by their address.

    ``max_age`` is the seconds a page is given back without asking its site;
    None, the default, asks every time. ``clock`` is the time in seconds,
    injected by tests.
    """

    def __init__(
        self,
        directory: str | Path,
        max_age: float | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_age is not None and max_age < 0:
            raise ValueError(f"max_age is seconds, and not negative: {max_age}")
        self.directory = Path(directory)
        self.max_age = max_age
        self.clock = clock

    def _path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8", "replace")).hexdigest()[:32]
        return self.directory / f"{key}.json"

    def read(self, url: str) -> dict[str, Any] | None:
        """The entry kept for ``url``, or None; a broken one is no entry."""
        try:
            entry = json.loads(self._path(url).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or entry.get("format") != _FORMAT:
            return None
        if entry.get("url") != url or not isinstance(entry.get("html"), str):
            return None
        return entry

    def write(self, url: str, fetched: Fetched) -> None:
        """Keep ``fetched`` for ``url``: only a 2xx page, and never its cookies."""
        if not 200 <= fetched.status < 300:
            return
        html = fetched.html
        if isinstance(html, bytes):
            html = html.decode(sniff_encoding(html), errors="replace")
        self._put(
            url,
            {
                "format": _FORMAT,
                "url": url,
                "landed": fetched.url,
                "status": fetched.status,
                "rung": fetched.rung,
                "stored": self.clock(),
                "headers": {k: v for k, v in fetched.headers.items() if k in _KEPT},
                "html": html,
            },
        )

    def _put(self, url: str, entry: dict[str, Any]) -> None:
        # Written aside and moved into place, so a reader never meets half.
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(url)
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        partial.replace(path)


def fetch_cached(
    url: str,
    cache: Cache,
    obey_robots: bool = True,
    stealth: bool = False,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    transport: Transport | None = None,
) -> Fetched:
    """``fetch``, through ``cache``: the kept page when it is young enough or
    its site says it has not changed, else the page as fetched now, kept.

    ``rungs`` is the ladder, as for ``fetch``; ``transport`` is how the
    revalidating request is sent, ``http_responses`` by default. Both are
    injected by tests.

    Raises:
        What ``fetch`` raises.
    """
    entry = cache.read(url)
    now = cache.clock()
    if entry is not None:
        age = max(0.0, now - float(entry["stored"]))
        if cache.max_age is not None and age <= cache.max_age:
            return _kept(entry, CacheHit(round(age, 3), revalidated=False))
        validators = _validators(entry["headers"])
        if validators and entry["rung"] == "http":
            try:
                answered = fetch(
                    url,
                    rungs=[
                        (
                            "http",
                            _asking(
                                validators, transport, allow_private, resolve, max_bytes
                            ),
                        )
                    ],
                    obey_robots=obey_robots,
                    robots_reader=robots_reader_from(
                        rungs[0][1]
                        if rungs
                        else _plain(allow_private, resolve, max_bytes)
                    ),
                    allow_private=allow_private,
                    resolve=resolve,
                    max_bytes=max_bytes,
                )
            except PaymentRequired:
                # The site's answer, which no rung asked again changes.
                raise
            except FetchFailed:
                # The question could not be put; the whole ladder may still
                # reach the page, a browser included.
                answered = None
            if answered is not None and answered.status == 304:
                entry["stored"] = now
                cache._put(url, entry)
                return _kept(entry, CacheHit(0.0, revalidated=True))
            if answered is not None and _enough(answered):
                cache.write(url, answered)
                return answered
    fetched = fetch(
        url,
        rungs=rungs,
        obey_robots=obey_robots,
        stealth=stealth,
        allow_private=allow_private,
        resolve=resolve,
        max_bytes=max_bytes,
    )
    # The ladder hands back its last rung's page whatever it was; a challenge
    # kept here would be given back as the page, asking nobody, for max_age.
    if not _challenge(fetched):
        cache.write(url, fetched)
    return fetched


def _validators(headers: Mapping[str, str]) -> dict[str, str]:
    """The conditional request's headers, from what the server sent."""
    sent: dict[str, str] = {}
    if headers.get("etag"):
        sent["If-None-Match"] = headers["etag"]
    if headers.get("last-modified"):
        sent["If-Modified-Since"] = headers["last-modified"]
    return sent


def _asking(
    validators: dict[str, str],
    transport: Transport | None,
    allow_private: bool,
    resolve: Callable[[str], Iterable[str]],
    max_bytes: int,
) -> Rung:
    """The plain HTTP rung, sending ``validators``: a 304 is an answer, not a
    failure, and any other answer is read as the HTTP rung reads it."""
    if transport is None:
        from sluicer.fetch.http_rung import http_responses
        from sluicer.fetch.scrapling_rungs import FetchExtraMissing

        def transport(address: str, send: Mapping[str, str]) -> Response:
            get = http_responses(
                allow_private, resolve, max_bytes, FetchExtraMissing, send=send
            )
            return get(address)

    def rung(address: str) -> Fetched:
        response = transport(address, validators)
        if response.status == 304:
            return Fetched(url=response.url, html=" ", status=304, rung="http")
        body = response.body
        sent = charset({"content-type": response.content_type})
        html = body.decode(sniff_encoding(body, sent), errors="replace")
        if not html:
            raise EmptyBody(address, "http", response.status)
        return Fetched(
            url=response.url,
            html=html,
            status=response.status,
            rung="http",
            headers=response.headers,
        )

    return rung


def _plain(
    allow_private: bool, resolve: Callable[[str], Iterable[str]], max_bytes: int
) -> Rung:
    """The plain HTTP rung, for the robots.txt a revalidation asks first."""
    from sluicer.fetch.http_rung import http_rung
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    return http_rung(allow_private, resolve, max_bytes, error=FetchExtraMissing)


def _enough(fetched: Fetched) -> bool:
    """Whether a changed page is the page, as the ladder would have judged it:
    a 2xx that is neither a challenge nor an empty shell."""
    if not 200 <= fetched.status < 300:
        return False
    return why_climb(fetched.status, _html(fetched), _found(fetched)) is None


def _challenge(fetched: Fetched) -> bool:
    """Whether a 2xx page is a challenge standing in front of the page."""
    if not 200 <= fetched.status < 300:
        return False
    return challenge_marker(_html(fetched), _found(fetched)) is not None


def _found(fetched: Fetched) -> bool:
    """Whether the page declares something about a thing, as the ladder asks."""
    records = extract(fetched.html, url=fetched.url).records
    return any(
        field.source in ABOUT_A_THING
        for record in records
        for field in record.fields.values()
    )


def _html(fetched: Fetched) -> str:
    return fetched.html if isinstance(fetched.html, str) else fetched.html.decode()


def _kept(entry: dict[str, Any], hit: CacheHit) -> Fetched:
    return Fetched(
        url=str(entry["landed"]),
        html=str(entry["html"]),
        status=int(entry["status"]),
        rung=str(entry["rung"]),
        headers=dict(entry["headers"]),
        cached=hit,
    )
