# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""The WCXB labels, scored on the pages as they were served, scripts intact.

    uv run bench/realweb.py               # refetch the pinned captures, score, publish
    uv run bench/realweb.py --discover    # search the archives anew, rewrite the pins
    uv run bench/realweb.py --tools sluicer   # rerun one tool, reuse the others

WCXB removed every ``<script>`` from its HTML, JSON-LD included. This takes each
test page's address to the Wayback Machine, then to Common Crawl, fetches the
capture closest to when WCXB saved the page, keeps it only if its visible text
proves it is the same document, and runs the same tools, the same scorer and
the same labels as ``bench/run.py`` on it -- and on the WCXB copy of the very
same pages, so served and stripped are compared on identical pages.

The captures chosen are pinned in ``bench/realweb-manifest.json``: archive,
timestamp, SHA-256 of the body and match score per page, and why every
excluded page was excluded. The default run fetches exactly those captures,
checks every digest, and fails if one differs. ``--discover`` is the only
thing that chooses captures, and its output is a change to the scoreboard.

Everything fetched is cached under ``bench/cache/realweb/``, so an interrupted
run resumes where it stopped. A request that was refused (429), failed (5xx)
or timed out is retried with backoff and, failing that, counted as not
fetched -- never as an empty page, and never cached.
"""

from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import html
import http.client
import json
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import corpus  # noqa: E402
import run as board  # noqa: E402
import score  # noqa: E402

CACHE = corpus.CACHE / "realweb"
MANIFEST = HERE / "realweb-manifest.json"
SCOREBOARD = ROOT / "docs" / "scoreboard-served.md"
USER_AGENT = (
    "sluicer-bench/1.0 (+https://github.com/Gi0tto/sluicer/tree/main/bench; "
    "scores the WCXB labels on archived pages)"
)

# WCXB records no capture date. The latest dates written inside its test
# pages cluster on 13-14 March 2026 and the split was committed on 29 March
# 2026, so the pages were saved in mid-March: captures are ranked by their
# distance from this instant.
TARGET = datetime.datetime(2026, 3, 14, tzinfo=datetime.timezone.utc)
# Captures further than this from the target are not considered at all.
WINDOW = datetime.timedelta(days=183)
# Distinct bodies fetched per page and per archive before giving up on it.
TRIES = 3
# Common Crawl indexes each crawl apart, one query per crawl per address, and
# its index server is often overloaded: only the crawls nearest the target are
# asked.
CRAWLS = 6
# A 5-word shingle is long enough that a shared one is a shared sentence, and
# short enough that one edited word costs five shingles, not a paragraph.
SHINGLE = 5
# The least evidence a verdict may rest on, in shingles.
EVIDENCE = 25
# The share of the WCXB text that must be found in the archived page. Chosen
# from the distribution of scores over every fetched capture: see the
# scoreboard's "How a capture is matched" section, which prints it each run.
THRESHOLD = 0.6
# Query parameters that name a click or a campaign, not a document. Google's
# `srsltid` is on 47 of the 511 addresses and is unique per click, so no
# archive holds the address as WCXB wrote it.
TRACKING = re.compile(r"^(srsltid|gclid|fbclid|msclkid|mc_cid|mc_eid|utm_\w+)$")

WAYBACK = "wayback"
COMMONCRAWL = "commoncrawl"
ARCHIVES = (WAYBACK, COMMONCRAWL)

# How long to wait between two requests to one host, in seconds, whatever the
# number of pages in flight.
_INTERVAL = {
    "web.archive.org": 1.0,
    "index.commoncrawl.org": 1.0,
    "data.commoncrawl.org": 0.5,
}
_WORKERS = 4
_BACKOFF = (10, 30, 90, 180)
_DOWN_AFTER = 3


# --- HTTP, politely ------------------------------------------------------------


class NotFetched(Exception):
    """A request that failed every retry: an absence of evidence, not a page."""


@dataclass
class Response:
    status: int
    url: str
    headers: dict[str, str]
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class _Polite:
    """One request start per host per interval, across every thread.

    And a host that failed every retry of ``_DOWN_AFTER`` requests in a row is
    left alone for the rest of the run: what it would have answered is counted
    as not fetched, and the next run, resuming from the cache, asks again.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}
        self._failed: dict[str, int] = {}

    def wait(self, host: str) -> None:
        with self._lock:
            if self._failed.get(host, 0) >= _DOWN_AFTER:
                raise NotFetched(f"{host} failed {_DOWN_AFTER} requests in a row")
            now = time.monotonic()
            start = max(now, self._next.get(host, now))
            self._next[host] = start + _INTERVAL.get(host, 1.0)
        time.sleep(max(0.0, start - now))

    def answered(self, host: str) -> None:
        with self._lock:
            self._failed[host] = 0

    def gave_up(self, host: str) -> None:
        with self._lock:
            self._failed[host] = self._failed.get(host, 0) + 1


_POLITE = _Polite()
_OPENER = urllib.request.build_opener(_NoRedirect())


def _get(url: str, headers: dict[str, str] | None = None) -> Response:
    """GET ``url``; any answer but 429 and 5xx is returned, those are retried.

    Redirects are returned, not followed, so the caller sees where a capture
    points before deciding whether that is still the page it asked for.
    """
    host = urllib.parse.urlsplit(url).hostname or ""
    request_headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    request_headers.update(headers or {})
    last = "no attempt"
    for attempt in range(len(_BACKOFF) + 1):
        if attempt:
            time.sleep(_BACKOFF[attempt - 1])
        _POLITE.wait(host)
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with _OPENER.open(request, timeout=60) as found:
                answer = Response(
                    found.status, url, _lower(found.headers), found.read()
                )
        except urllib.error.HTTPError as error:
            if error.code == 429 or error.code >= 500:
                last = f"HTTP {error.code}"
                retry_after = error.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    time.sleep(min(int(retry_after), 300))
                continue
            answer = Response(
                error.code, url, _lower(error.headers), error.read() or b""
            )
        # Timeouts and resets are OSError; a body cut short is an HTTPException.
        except (OSError, ValueError, http.client.HTTPException) as error:
            last = type(error).__name__
            continue
        _POLITE.answered(host)
        return answer
    _POLITE.gave_up(host)
    raise NotFetched(f"{last} after {len(_BACKOFF) + 1} attempts: {url}")


def _lower(headers: Any) -> dict[str, str]:
    """Header names in lower case: HTTP/2 sends them so, HTTP/1.1 need not."""
    return {name.lower(): value for name, value in headers.items()}


def _decoded(body: bytes, encoding: str) -> bytes:
    encoding = encoding.strip().lower()
    if encoding in ("", "identity", "none"):
        # A server that compressed twice, or forgot to say it compressed.
        return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
    if encoding in ("gzip", "x-gzip"):
        return _decoded(gzip.decompress(body), "")
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    raise NotFetched(f"content-encoding {encoding!r} is not decoded here")


def _dechunked(body: bytes) -> bytes:
    out, rest = bytearray(), body
    while rest:
        size_line, _, rest = rest.partition(b"\r\n")
        size = int(size_line.split(b";")[0].strip() or b"0", 16)
        if size == 0:
            break
        out += rest[:size]
        rest = rest[size + 2 :]
    return bytes(out)


# --- where the page was archived -----------------------------------------------


def _variants(url: str) -> list[str]:
    """The address as WCXB wrote it, then without its click-tracking parameters."""
    parts = urllib.parse.urlsplit(url)
    query = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if not TRACKING.match(key)
    ]
    clean = urllib.parse.urlunsplit(
        parts._replace(query=urllib.parse.urlencode(query), fragment="")
    )
    return [url] if clean == url else [url, clean]


def _instant(timestamp: str) -> datetime.datetime:
    return datetime.datetime.strptime(timestamp[:14], "%Y%m%d%H%M%S").replace(
        tzinfo=datetime.timezone.utc
    )


def _distance(timestamp: str) -> float:
    return abs((_instant(timestamp) - TARGET).total_seconds())


def _in_window(timestamp: str) -> bool:
    return _distance(timestamp) <= WINDOW.total_seconds()


def _cached_json(path: Path, make: Any) -> Any:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = make()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def _wayback_index(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Every Wayback capture of the page in the window that answered 200 HTML."""

    def query() -> dict[str, Any]:
        found = {}
        low = (TARGET - WINDOW).strftime("%Y%m%d")
        high = (TARGET + WINDOW).strftime("%Y%m%d")
        for variant in _variants(page["url"]):
            params = urllib.parse.urlencode({"url": variant, "from": low, "to": high})
            answer = _get(f"https://web.archive.org/web/timemap/json?{params}")
            if answer.status != 200:
                raise NotFetched(f"Wayback timemap answered {answer.status}")
            text = _decoded(answer.body, answer.headers.get("content-encoding", ""))
            rows = json.loads(text) if text.strip() else []
            found[variant] = rows
        return found

    answered = _cached_json(CACHE / WAYBACK / "index" / f"{page['id']}.json", query)
    captures = []
    for rows in answered.values():
        if not rows:
            continue
        header = rows[0]
        for row in rows[1:]:
            item = dict(zip(header, row, strict=False))
            if item.get("statuscode") != "200" or "html" not in item.get(
                "mimetype", ""
            ):
                continue
            captures.append(
                {
                    "archive": WAYBACK,
                    "timestamp": item["timestamp"],
                    "original": item["original"],
                    "archive_digest": item.get("digest"),
                }
            )
    return captures


def _crawls() -> list[tuple[str, datetime.datetime]]:
    """Common Crawl's crawls whose week falls in the window, nearest first."""

    def query() -> Any:
        answer = _get("https://index.commoncrawl.org/collinfo.json")
        if answer.status != 200:
            raise NotFetched(f"Common Crawl collinfo answered {answer.status}")
        return json.loads(
            _decoded(answer.body, answer.headers.get("content-encoding", ""))
        )

    crawls = []
    for crawl in _cached_json(CACHE / COMMONCRAWL / "collinfo.json", query):
        named = re.fullmatch(r"CC-MAIN-(\d{4})-(\d{2})", crawl["id"])
        if not named:
            continue
        week = datetime.datetime.fromisocalendar(
            int(named[1]), int(named[2]), 1
        ).replace(tzinfo=datetime.timezone.utc)
        if abs(week - TARGET) <= WINDOW:
            crawls.append((crawl["id"], week))
    return sorted(crawls, key=lambda crawl: abs(crawl[1] - TARGET))


def _commoncrawl_index(page: dict[str, Any], crawl: str) -> list[dict[str, Any]]:
    """Every capture of the page in one crawl that answered 200 HTML."""

    def query() -> dict[str, Any]:
        found = {}
        for variant in _variants(page["url"]):
            params = urllib.parse.urlencode({"url": variant, "output": "json"})
            answer = _get(f"https://index.commoncrawl.org/{crawl}-index?{params}")
            if answer.status == 404:  # the index's answer for "no capture"
                found[variant] = []
                continue
            if answer.status != 200:
                raise NotFetched(f"Common Crawl index answered {answer.status}")
            text = _decoded(answer.body, answer.headers.get("content-encoding", ""))
            found[variant] = [json.loads(line) for line in text.splitlines() if line]
        return found

    path = CACHE / COMMONCRAWL / "index" / crawl / f"{page['id']}.json"
    captures = []
    for rows in _cached_json(path, query).values():
        for item in rows:
            if item.get("status") != "200" or "html" not in item.get("mime", ""):
                continue
            captures.append(
                {
                    "archive": COMMONCRAWL,
                    "timestamp": item["timestamp"],
                    "original": item["url"],
                    "archive_digest": item.get("digest"),
                    "warc": {
                        "filename": item["filename"],
                        "offset": int(item["offset"]),
                        "length": int(item["length"]),
                    },
                }
            )
    return captures


# --- the body of one capture ---------------------------------------------------


def _body_path(page_id: str, capture: dict[str, Any]) -> Path:
    return CACHE / "bodies" / capture["archive"] / f"{page_id}-{capture['timestamp']}"


def fetch(page_id: str, capture: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    """The bytes the capture holds, as its server sent them, and what we know."""
    path = _body_path(page_id, capture)
    body_file, meta_file = path.with_suffix(".html.gz"), path.with_suffix(".json")
    if body_file.exists() and meta_file.exists():
        return gzip.decompress(body_file.read_bytes()), json.loads(
            meta_file.read_text(encoding="utf-8")
        )
    try:
        if capture["archive"] == WAYBACK:
            body, meta = _fetch_wayback(capture)
        else:
            body, meta = _fetch_commoncrawl(capture)
    except (OSError, EOFError, zlib.error, ValueError) as error:  # a body cut short
        raise NotFetched(f"{type(error).__name__} decoding {capture}") from error
    meta["sha256"] = hashlib.sha256(body).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    body_file.write_bytes(gzip.compress(body, mtime=0))
    meta_file.write_text(json.dumps(meta), encoding="utf-8")
    return body, meta


def _fetch_wayback(capture: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    # `id_` asks for the bytes as archived, without the Wayback toolbar or any
    # rewritten link.
    url = f"https://web.archive.org/web/{capture['timestamp']}id_/{capture['original']}"
    for _hop in range(5):
        answer = _get(url)
        if answer.status in (301, 302, 303, 307, 308):
            # The archive moves a request to the nearest capture it holds of
            # the same address; anything else is followed and then judged.
            url = urllib.parse.urljoin(url, answer.headers.get("location", ""))
            continue
        break
    if answer.status != 200:
        raise NotFetched(f"Wayback answered {answer.status} for {url}")
    body = _decoded(answer.body, answer.headers.get("content-encoding", ""))
    served = re.match(r"https://web\.archive\.org/web/(\d{14})id_/(.*)", url)
    return body, {
        "fetched_from": url,
        "served_timestamp": served[1] if served else None,
        "served_url": served[2] if served else url,
        "content_type": answer.headers.get("content-type", ""),
    }


def _fetch_commoncrawl(capture: dict[str, Any]) -> tuple[bytes, dict[str, Any]]:
    warc = capture["warc"]
    first, last = warc["offset"], warc["offset"] + warc["length"] - 1
    url = f"https://data.commoncrawl.org/{warc['filename']}"
    answer = _get(url, {"Range": f"bytes={first}-{last}"})
    if answer.status != 206:
        raise NotFetched(f"Common Crawl data answered {answer.status} for {url}")
    record = gzip.decompress(answer.body)
    warc_head, _, block = record.partition(b"\r\n\r\n")
    length = re.search(rb"(?im)^content-length:\s*(\d+)", warc_head)
    if length:
        block = block[: int(length[1])]
    http_head, _, body = block.partition(b"\r\n\r\n")
    headers: dict[str, str] = {}
    for line in http_head.decode("latin-1").split("\r\n")[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    if "chunked" in headers.get("transfer-encoding", "").lower():
        body = _dechunked(body)
    body = _decoded(body, headers.get("content-encoding", ""))
    return body, {
        "fetched_from": f"{url} bytes {first}-{last}",
        "served_timestamp": capture["timestamp"],
        "served_url": capture["original"],
        "content_type": headers.get("content-type", ""),
    }


# --- is it the same document ---------------------------------------------------


class _Visible(HTMLParser):
    """The text a reader sees: everything but script, style, template and SVG.

    ``<noscript>`` is kept: some sites serve their text there, and WCXB kept it.
    """

    _HIDDEN = frozenset({"script", "style", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._HIDDEN:
            self._hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._HIDDEN and self._hidden:
            self._hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self.parts.append(data)


def _charset(body: bytes, content_type: str) -> str:
    declared = re.search(r"charset=[\"']?([\w-]+)", content_type, re.I)
    if not declared:
        declared = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
        name = declared[1].decode("ascii") if declared else "utf-8"
    else:
        name = declared[1]
    try:
        "".encode(name)
    except LookupError:
        return "utf-8"
    return name


def visible_text(body: bytes, content_type: str = "") -> str:
    parser = _Visible()
    parser.feed(body.decode(_charset(body, content_type), "replace"))
    parser.close()
    return html.unescape(" ".join(parser.parts))


def shingles(text: str) -> set[tuple[str, ...]]:
    words = re.findall(r"\w+", text.lower())
    return {tuple(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}


@dataclass
class Evidence:
    """What an archived copy must contain to be the page WCXB labelled.

    The labelled main text as it appears on the WCXB page, where there is
    enough of it: the labels' own formatting (bullets, joined table cells)
    then costs nothing, since only text both share is asked for. Where the
    two share too little -- a listing labelled as a few words, a page with no
    main text labelled -- the WCXB page's whole visible text. Where the WCXB
    page holds almost none -- its text was in the scripts WCXB removed -- the
    labelled main text alone.
    """

    shingles: set[tuple[str, ...]]
    basis: str
    page: set[tuple[str, ...]]

    @classmethod
    def of(cls, page: dict[str, Any]) -> Evidence:
        truth = json.loads(
            (corpus.CORPUS / "test" / "ground-truth" / f"{page['id']}.json").read_text(
                encoding="utf-8"
            )
        )
        main = shingles((truth.get("ground_truth") or {}).get("main_content") or "")
        wcxb = gzip.decompress((corpus.CACHE / page["path"]).read_bytes())
        on_page = shingles(visible_text(wcxb))
        if len(main & on_page) >= EVIDENCE:
            return cls(main & on_page, "labelled main text on the WCXB page", on_page)
        if len(on_page) >= EVIDENCE:
            return cls(on_page, "WCXB page text", on_page)
        return cls(main, "labelled main text", on_page)

    def match(self, body: bytes, content_type: str) -> dict[str, Any]:
        archived = shingles(visible_text(body, content_type))
        found = len(self.shingles & archived) / len(self.shingles)
        page = len(self.page & archived) / len(self.page) if self.page else 0.0
        union = self.page | archived
        return {
            "score": round(found, 4),
            "basis": self.basis,
            "evidence": len(self.shingles),
            "page_containment": round(page, 4),
            "page_jaccard": round(len(self.page & archived) / len(union), 4)
            if union
            else 0.0,
            "archived_shingles": len(archived),
        }


_CHALLENGE = re.compile(
    rb"(just a moment\.\.\.|cf-browser-verification|challenge-platform|"
    rb"enable javascript and cookies to continue|are you a robot|"
    rb"access denied|captcha)",
    re.I,
)


def _why_not(body: bytes, verdict: dict[str, Any]) -> str:
    """Why a fetched capture is not the labelled document, in one word."""
    if verdict["archived_shingles"] < EVIDENCE:
        return "a challenge page" if _CHALLENGE.search(body[:20000]) else "no text"
    if _CHALLENGE.search(body[:20000]) and verdict["page_containment"] < 0.2:
        return "a challenge page"
    return "different text"


# --- one page, from address to verdict -----------------------------------------


def _batches(page: dict[str, Any], archive: str, failures: list[str]) -> Any:
    """The archive's captures of the page, one batch per index asked."""
    if archive == WAYBACK:
        try:
            yield _wayback_index(page)
        except NotFetched as error:
            failures.append(f"wayback index: {error}")
        return
    for crawl, _week in _crawls()[:CRAWLS]:
        try:
            yield _commoncrawl_index(page, crawl)
        except NotFetched as error:  # one crawl down is not every crawl down
            failures.append(f"{crawl} index: {error}")


def _candidates(page: dict[str, Any], archive: str, failures: list[str]) -> Any:
    """Captures in the window, nearest the target first, one per distinct body.

    Common Crawl is asked crawl by crawl, nearest first, and only as far as it
    takes: a page found in the nearest crawl costs one query, not twelve.
    """
    seen: set[str] = set()
    for batch in _batches(page, archive, failures):
        for capture in sorted(batch, key=lambda c: _distance(c["timestamp"])):
            digest = capture.get("archive_digest") or capture["timestamp"]
            if not _in_window(capture["timestamp"]) or digest in seen:
                continue
            seen.add(digest)
            yield capture


def discover(page: dict[str, Any]) -> dict[str, Any]:
    """Find the nearest capture that is provably the page, or say why not."""
    entry: dict[str, Any] = {"id": page["id"], "url": page["url"]}
    if not page["url"]:
        return {**entry, "included": False, "reason": "no address in the corpus"}
    evidence = Evidence.of(page)
    if len(evidence.shingles) < EVIDENCE:
        return {**entry, "included": False, "reason": "too little text to verify"}
    tried: list[dict[str, Any]] = []
    failures: list[str] = []
    for archive in ARCHIVES:
        fetched_here = 0
        for capture in _candidates(page, archive, failures):
            if fetched_here == TRIES:
                break
            try:
                body, meta = fetch(page["id"], capture)
            except NotFetched as error:
                failures.append(str(error))
                continue
            fetched_here += 1
            verdict = evidence.match(body, meta["content_type"])
            attempt = {**_pin(capture, meta), "match": verdict}
            if verdict["score"] >= THRESHOLD:
                return {**entry, "included": True, **attempt, "tried": len(tried)}
            attempt["why_not"] = _why_not(body, verdict)
            tried.append(attempt)
    if tried:
        best = max(tried, key=lambda attempt: attempt["match"]["score"])
        return {
            **entry,
            "included": False,
            "reason": best.pop("why_not"),
            "tried": len(tried),
            "best": best,
        }
    if failures:
        return {**entry, "included": False, "reason": "not fetched", "errors": failures}
    return {**entry, "included": False, "reason": "not archived"}


def _pin(capture: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    pinned = {
        "archive": capture["archive"],
        "timestamp": capture["timestamp"],
        "original": capture["original"],
        "sha256": meta["sha256"],
        "content_type": meta["content_type"],
    }
    if meta.get("served_timestamp") not in (None, capture["timestamp"]):
        pinned["served_timestamp"] = meta["served_timestamp"]
    if "warc" in capture:
        pinned["warc"] = capture["warc"]
    return pinned


# --- the manifest ---------------------------------------------------------------


def discover_all(pages: list[dict[str, Any]]) -> dict[str, Any]:
    done = 0
    lock = threading.Lock()

    def one(page: dict[str, Any]) -> dict[str, Any]:
        nonlocal done
        entry = discover(page)
        with lock:
            done += 1
            if done % 25 == 0 or done == len(pages):
                print(f"  {done}/{len(pages)} pages", flush=True)
        return entry

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        entries = list(pool.map(one, pages))
    return {
        "corpus": {"repository": corpus.REPOSITORY, "commit": corpus.COMMIT},
        "target": TARGET.isoformat(),
        "window_days": WINDOW.days,
        "threshold": THRESHOLD,
        "shingle_words": SHINGLE,
        "tries_per_archive": TRIES,
        "discovered_on": datetime.date.today().isoformat(),
        "pages": entries,
    }


def refetch(manifest: dict[str, Any]) -> None:
    """Fetch exactly the pinned captures, and fail on any digest that moved."""
    moved = []
    for entry in manifest["pages"]:
        if not entry["included"]:
            continue
        body, _meta = fetch(entry["id"], entry)
        digest = hashlib.sha256(body).hexdigest()
        if digest != entry["sha256"]:
            moved.append(f"{entry['id']} {entry['archive']} {entry['timestamp']}")
    if moved:
        raise SystemExit(
            "these captures no longer hold the pinned bytes:\n  " + "\n  ".join(moved)
        )


# --- the tools, on both copies of the same pages --------------------------------

SIDES = ("served", "stripped")


def _pages_files(manifest: dict[str, Any], pages: dict[str, Any]) -> dict[str, Path]:
    """Two page lists for the tools, over the same pages: as served, as WCXB."""
    listed: dict[str, list[dict[str, Any]]] = {side: [] for side in SIDES}
    for entry in manifest["pages"]:
        if not entry["included"]:
            continue
        page = pages[entry["id"]]
        served = _body_path(entry["id"], entry).with_suffix(".html.gz")
        # The tools read each path relative to the list's own directory.
        listed["served"].append({**page, "path": str(served.relative_to(CACHE))})
        listed["stripped"].append({**page, "path": f"../{page['path']}"})
    files = {}
    for side, entries in listed.items():
        files[side] = CACHE / f"{side}.json"
        files[side].write_text(json.dumps(entries, indent=1) + "\n", encoding="utf-8")
    return files


def _results(side: str) -> Path:
    return CACHE / "results" / side


def run_tools(files: dict[str, Path], tools: list[str]) -> None:
    for side, pages_file in files.items():
        _results(side).mkdir(parents=True, exist_ok=True)
        for tool in tools:
            command, env = board._command(
                tool, pages_file, _results(side) / f"{tool}.json"
            )
            subprocess.run(command, cwd=ROOT, env=env, check=True)
        # Which vocabularies each page declares, as Sluicer's readers see them.
        command = board._uv(
            ["--with-editable", str(ROOT)],
            "sluicer_sources.py",
            pages_file,
            _results(side) / "sources.json",
        )
        subprocess.run(command, cwd=ROOT, check=True)


# --- the document ---------------------------------------------------------------

_ARCHIVE_NAMES = {WAYBACK: "the Wayback Machine", COMMONCRAWL: "Common Crawl"}

_REASONS = {
    "not archived": "no capture in either archive within the window",
    "not fetched": "an index or a capture refused or failed every retry",
    "different text": "captured, but the text is not the labelled document's",
    "no text": "captured, but the capture holds almost no visible text",
    "a challenge page": "captured, but what was captured is a bot or cookie wall",
    "too little text to verify": "the WCXB page and its label hold too little text",
    "no address in the corpus": "WCXB gives no address for the page",
}


def _coverage(manifest: dict[str, Any], pages: dict[str, Any]) -> list[str]:
    entries = manifest["pages"]
    included = [e for e in entries if e["included"]]
    fetched = [e for e in entries if e["included"] or e.get("best")]
    reasons = Counter(e["reason"] for e in entries if not e["included"])
    archives = Counter(e["archive"] for e in included)
    days = sorted(
        abs((_instant(e.get("served_timestamp") or e["timestamp"]) - TARGET).days)
        for e in included
    )
    median = days[len(days) // 2] if days else 0
    lines = [
        "| pages | count |",
        "|---|---|",
        f"| attempted | {len(entries)} |",
        f"| fetched (at least one capture read) | {len(fetched)} |",
        f"| matched, and scored below | **{len(included)}** |",
        f"| excluded | {len(entries) - len(included)} |",
        "",
        "| excluded because | pages | meaning |",
        "|---|---|---|",
        *[
            f"| {reason} | {count} | {_REASONS.get(reason, '')} |"
            for reason, count in reasons.most_common()
        ],
        "",
        f"Of the {len(included)} matched pages, "
        + ", ".join(
            f"{count} came from {_ARCHIVE_NAMES[name]}"
            for name, count in archives.most_common()
        )
        + f". The median capture is {median} days from the target date; "
        f"the furthest is {days[-1] if days else 0}.",
        *_why_not_fetched(entries),
        "",
        "| page type | test pages | matched |",
        "|---|---|---|",
    ]
    by_type = Counter(page["page_type"] for page in pages.values())
    matched = Counter(pages[e["id"]]["page_type"] for e in included)
    for page_type, count in by_type.most_common():
        lines.append(f"| {page_type} | {count} | {matched[page_type]} |")
    return lines


def _why_not_fetched(entries: list[dict[str, Any]]) -> list[str]:
    """What the pages no archive answered for were refused by, when one index
    refused them all: a scoreboard built on a day an archive was down says so."""
    unfetched = [e for e in entries if e.get("reason") == "not fetched"]
    only_cc = [
        e
        for e in unfetched
        if e.get("errors")
        and all(
            "index.commoncrawl.org" in error or "CC-MAIN" in error
            for error in e["errors"]
        )
    ]
    if not only_cc:
        return []
    return [
        "",
        f"Of the {len(unfetched)} pages not fetched, {len(only_cc)} are pages the "
        "Wayback Machine holds no capture of, whose only other source, Common "
        "Crawl's index, failed every retry while this was built. They are not "
        "known to be unarchived. `uv run bench/realweb.py --discover`, on a day "
        "the index answers, asks it again; every capture already read comes "
        "from the cache.",
    ]


def _histogram(manifest: dict[str, Any]) -> list[str]:
    """Every fetched page's best score, in tenths: what the threshold was cut on."""
    scores = []
    for entry in manifest["pages"]:
        if entry["included"]:
            scores.append(entry["match"]["score"])
        elif entry.get("best"):
            scores.append(entry["best"]["match"]["score"])
    bins = Counter(min(int(value * 10), 9) for value in scores)
    lines = ["| match score | pages |", "|---|---|"]
    for tenth in range(10):
        low, high = tenth / 10, (tenth + 1) / 10
        bracket = "]" if tenth == 9 else ")"
        lines.append(f"| [{low:.1f}, {high:.1f}{bracket} | {bins[tenth]} |")
    return lines


def _between(manifest: dict[str, Any], pages: dict[str, Any]) -> list[str]:
    """What the scores say about the cut, counted from the manifest.

    It said a capture of the same page "scores near 1" and what falls between
    "is mostly a listing" on every run, whatever the manifest held.
    """
    kept = [e["match"]["score"] for e in manifest["pages"] if e["included"]]
    between = Counter(
        pages[e["id"]]["page_type"]
        for e in manifest["pages"]
        if not e["included"]
        and e.get("best")
        and 0.2 <= e["best"]["match"]["score"] < THRESHOLD
    )
    kinds = ", ".join(f"{n} {kind}" for kind, n in between.most_common())
    return [
        f"  The {len(kept)} captures kept score a median of "
        f"{statistics.median(kept) if kept else 0:.2f}, the lowest "
        f"{min(kept) if kept else 0:.2f}.",
        f"  The {sum(between.values())} left out between 0.2 and {THRESHOLD} are "
        f"{kinds or 'none'},",
        "  by WCXB's page types: a page that changed that much is left out rather",
        "  than argued for.",
    ]


def _side_by_side(runs: dict[str, Any], per_page: dict[str, Any], pages: Any) -> Any:
    lines = [
        "| tool | field | labelled pages | hit rate, stripped | hit rate, served "
        "| right when answering, stripped | right when answering, served "
        "| wrong, stripped | wrong, served | inventions, stripped "
        "| inventions, served |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for tool in runs["served"]:
        name = board._name(runs["served"][tool])
        served = score.tally(per_page["served"][tool], pages)
        stripped = score.tally(per_page["stripped"][tool], pages)
        for field in score.FIELDS:
            s, w = served[field], stripped[field]
            labelled = s["hit"] + s["wrong"] + s["silent"]
            lines.append(
                f"| {name} | {field} | {labelled} "
                f"| {score.hit_rate(w):.3f} | **{score.hit_rate(s):.3f}** "
                f"| {score.right_when_answering(w):.3f} "
                f"| **{score.right_when_answering(s):.3f}** "
                f"| {w['wrong']} | {s['wrong']} "
                f"| {w['invention']} | {s['invention']} |"
            )
    return lines


_VOCABULARIES = (
    ("jsonld", "JSON-LD"),
    ("microdata", "microdata"),
    ("rdfa", "RDFa"),
    ("opengraph", "OpenGraph"),
    ("twitter", "Twitter card"),
    ("dublincore", "Dublin Core"),
    ("html", "HTML meta names"),
)


def _vocabularies(sources: dict[str, dict[str, list[str]]], total: int) -> list[str]:
    lines = [
        "| vocabulary | pages declaring it, stripped | pages declaring it, served |",
        "|---|---|---|",
    ]
    for key, label in _VOCABULARIES:
        counts = {
            side: sum(key in found for found in sources[side].values())
            for side in SIDES
        }
        lines.append(f"| {label} | {counts['stripped']} | {counts['served']} |")
    none = {side: sum(not found for found in sources[side].values()) for side in SIDES}
    lines.append(f"| none of them | {none['stripped']} | {none['served']} |")
    lines += ["", f"Out of {total} pages, as Sluicer's readers see them."]
    return lines


def _answered_from(runs: dict[str, Any], per_page: dict[str, Any]) -> list[str]:
    """Where Sluicer's served answers came from, and how each source did."""
    rows = {row["id"]: row for row in runs["served"]["sluicer"]["results"]}
    lines = [
        "| field | source | answers | hit | wrong | invention |",
        "|---|---|---|---|---|---|",
    ]
    for field in score.FIELDS:
        by_source: dict[str, Counter[str]] = {}
        for page_id, fields in per_page["served"]["sluicer"].items():
            source = rows[page_id].get(f"{field}_from")
            if not source:
                continue
            reader = source.split(" ", 1)[0]
            by_source.setdefault(reader, Counter())[fields[field]] += 1
        for reader, counts in sorted(by_source.items(), key=lambda kv: -kv[1].total()):
            lines.append(
                f"| {field} | {reader} | {counts.total()} | {counts['hit']} "
                f"| {counts['wrong']} | {counts['invention']} |"
            )
    return lines


def _plainly(runs: dict[str, Any], per_page: dict[str, Any], pages: Any) -> list[str]:
    """Who leads each field on served pages, and where Sluicer stands."""
    lines = []
    for field in score.FIELDS:
        counts = {
            tool: score.tally(per_page["served"][tool], pages)[field]
            for tool in runs["served"]
        }
        by_right = sorted(
            counts, key=lambda tool: -score.right_when_answering(counts[tool])
        )
        before = score.tally(per_page["stripped"]["sluicer"], pages)[field]
        mine = counts["sluicer"]
        # Rates are compared as printed, so a tie on the page is a tie here.
        rate = {tool: round(score.hit_rate(counts[tool]), 3) for tool in counts}
        ahead = sorted(
            (tool for tool in counts if rate[tool] > rate["sluicer"]),
            key=lambda tool: -rate[tool],
        )
        level = [t for t in counts if t != "sluicer" and rate[t] == rate["sluicer"]]
        if ahead:
            verdict = (
                f"Sluicer is {_ordinal(len(ahead) + 1)} of {len(counts)}, behind "
                + ", ".join(f"{tool} {rate[tool]:.3f}" for tool in ahead)
            )
        else:
            verdict = "Sluicer has the highest hit rate"
        if level:
            verdict += ", level with " + ", ".join(level)
        lines.append(
            f"- **{field.capitalize()}.** Hit rate served "
            f"{score.hit_rate(mine):.3f}, against {score.hit_rate(before):.3f} "
            f"on the WCXB copy of the same pages. {verdict}. Right when "
            "answering: "
            + ", ".join(
                f"{tool} {score.right_when_answering(counts[tool]):.3f}"
                for tool in by_right
            )
            + ". Inventions: "
            + ", ".join(f"{tool} {counts[tool]['invention']}" for tool in by_right)
            + "."
        )
    return lines


def _ordinal(place: int) -> str:
    return {1: "first", 2: "second", 3: "third", 4: "fourth"}.get(place, str(place))


def _non_utf8(manifest: dict[str, Any]) -> int:
    count = 0
    for entry in manifest["pages"]:
        if not entry["included"]:
            continue
        body, _meta = fetch(entry["id"], entry)
        try:
            body.decode("utf-8")
        except UnicodeDecodeError:
            count += 1
    return count


def publish(manifest: dict[str, Any]) -> None:
    pages_list = json.loads(corpus.PAGES.read_text(encoding="utf-8"))
    everything = {page["id"]: page for page in pages_list}
    included = {e["id"] for e in manifest["pages"] if e["included"]}
    pages = {page_id: everything[page_id] for page_id in included}
    runs: dict[str, dict[str, Any]] = {}
    per_page: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, list[str]]] = {}
    for side in SIDES:
        runs[side] = {
            tool: json.loads(
                (_results(side) / f"{tool}.json").read_text(encoding="utf-8")
            )
            for tool in board.TOOLS
            if (_results(side) / f"{tool}.json").exists()
        }
        per_page[side] = {
            tool: score.outcomes(found["results"], pages)
            for tool, found in runs[side].items()
        }
        sources[side] = json.loads(
            (_results(side) / "sources.json").read_text(encoding="utf-8")
        )
    SCOREBOARD.write_text(
        _document(manifest, everything, pages, runs, per_page, sources),
        encoding="utf-8",
    )
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


def _document(manifest, everything, pages, runs, per_page, sources) -> str:
    today = datetime.date.today().isoformat()
    commit = board._git("rev-parse", "--short", "HEAD")
    changed = board._git(
        "status", "--porcelain", "--", ".", ":!docs/scoreboard-served.md"
    )
    dirty = " (with uncommitted changes)" if changed else ""
    n = len(pages)
    labelled = {
        field: sum(1 for page in pages.values() if score.as_text(page[field]))
        for field in score.FIELDS
    }
    lines = [
        "# Scoreboard, on pages as served",
        "",
        "[The scoreboard](scoreboard.md) measures Sluicer on WCXB's copies of its",
        "pages, and WCXB removed every `<script>` from them, JSON-LD included.",
        "This page measures the same tools, with the same labels and the same",
        "scorer, on the same pages as their servers sent them, scripts intact,",
        "fetched from web archives. Every page is scored twice, once as served",
        "and once as WCXB kept it, so the difference between the two columns is",
        "the difference the scripts make, and nothing else.",
        f"Regenerated on {today} from commit `{commit}`{dirty} by",
        "`uv run bench/realweb.py`, from the captures pinned in",
        "[`bench/realweb-manifest.json`]"
        "(https://github.com/Gi0tto/sluicer/blob/main/bench/realweb-manifest.json).",
        "",
        '!!! warning "Read this before the numbers"',
        f"    These are {n} of WCXB's {len(everything)} test pages: the ones an",
        "    archive holds near the date WCXB saved them, and whose archived text",
        "    proves they are the page WCXB labelled. A page no archive kept, or",
        "    kept only as a wall or a later rewrite, is left out and counted",
        "    below. Pages that are archived are not a random sample of the web,",
        "    so compare the two columns with each other, not with the full",
        "    scoreboard.",
        "",
        "## Coverage",
        "",
        *_coverage(manifest, everything),
        "",
        "## Results",
        "",
        f"Hit rate is hits over the pages that carry a label ({labelled['title']} "
        f"titles, {labelled['author']} authors, {labelled['date']} dates on the "
        f"{n} matched pages). Right when answering is hits over every answer "
        "given, inventions included. An invention is an answer on a page whose "
        "label is empty.",
        "",
        f"The same {n} pages, stripped (WCXB's copy) and served (the archive's):",
        "",
        *_side_by_side(runs, per_page, pages),
        "",
        "In plain words, as served:",
        "",
        *_plainly(runs, per_page, pages),
        "",
        "One caution about inventions on served pages. WCXB's annotators labelled",
        "what a reader sees, and left a label empty where the visible page states",
        "none. A served page can still declare a date or an author in JSON-LD",
        "that the visible page never shows; the scorer counts that answer as an",
        "invention, here as on the full scoreboard, and the rules were not",
        "changed for this page. The table below says how many of Sluicer's",
        "inventions each source produced.",
        "",
        "## What the pages declare",
        "",
        *_vocabularies(sources, n),
        "",
        "## Where Sluicer's served answers came from",
        "",
        *_answered_from(runs, per_page),
        "",
        "## Where Sluicer loses, as served",
        "",
        *board._losses(runs["served"], per_page["served"], pages),
        "",
        "## Every outcome",
        "",
        f"The {n} pages as served:",
        "",
        *board._full_table(runs["served"], per_page["served"], pages),
        "",
        f"The same {n} pages as WCXB kept them:",
        "",
        *board._full_table(runs["stripped"], per_page["stripped"], pages),
        "",
        "## How a capture is chosen and matched",
        "",
        f"- **When.** WCXB records no capture date. The latest dates written "
        "inside its test pages cluster on 13 and 14 March 2026, and the split "
        f"was committed on 29 March 2026, so the target is "
        f"{TARGET.date().isoformat()}. Captures are ranked by distance from it, "
        f"either side, and none further than {WINDOW.days} days is considered.",
        "- **Where.** The Wayback Machine first, asked through its timemap, "
        "each capture read with `id_`, the bytes as archived; then Common Crawl, "
        "crawl by crawl nearest first, each record read by a byte-range request "
        "into its WARC file. Only captures that answered 200 with HTML count. "
        "Where the address carries a click-tracking parameter (`srsltid`, "
        "`utm_*`, `gclid`), the address without it is asked as well.",
        f"- **How many.** At most {TRIES} distinct bodies per page per archive, "
        "nearest first; the first one that matches is kept.",
        f"- **Same document.** The visible text of both pages (everything but "
        f"`script`, `style`, `template` and `svg`), cut into {SHINGLE}-word "
        "shingles. The evidence is the labelled main text as it appears on the "
        "WCXB page; the score is the share of it found in the archived page. "
        f"Where the two share fewer than {EVIDENCE} shingles (a listing "
        "labelled in a few words, a page with no main text labelled), the "
        "evidence is the WCXB page's whole visible text; where the WCXB page "
        "holds almost no text (it was in the scripts WCXB removed), the "
        "labelled main text alone. The manifest records, per page, the score, "
        "its basis, and the containment and Jaccard of the whole visible text.",
        f"- **Threshold: {THRESHOLD}.** Cut where the distribution of best "
        "scores, over every page where a capture was read, is thinnest:",
        "",
        *_histogram(manifest),
        "",
        *_between(manifest, everything),
        f"- **Bytes.** Every tool reads the bytes as the archive holds them. "
        f"{_non_utf8(manifest)} of the {n} are not UTF-8; Sluicer and "
        "trafilatura honour the page's charset, the newspaper4k and metascraper "
        "harnesses decode UTF-8, as they do on the full scoreboard.",
        "- **Pinned.** The manifest holds, per page, the archive, the "
        "timestamp, the address asked and the SHA-256 of the body, and for "
        "Common Crawl the WARC file, offset and length; for every excluded page, "
        "the reason and the best capture tried. `uv run bench/realweb.py` fetches "
        "exactly those and stops if any digest differs.",
        "- **Scoring.** `bench/score.py` and the tool harnesses in "
        "`bench/tools/` and `bench/metascraper/`, unchanged, at the pins the "
        "full scoreboard uses.",
        "",
    ]
    return "\n".join(lines)


# --- entry point -----------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--discover",
        action="store_true",
        help="search the archives anew and rewrite the manifest",
    )
    parser.add_argument(
        "--tools",
        default=",".join(board.TOOLS),
        help="comma-separated tools to rerun; the others' last results are reused",
    )
    args = parser.parse_args()
    started = time.perf_counter()
    pages_list = json.loads(corpus.ensure().read_text(encoding="utf-8"))
    pages = {page["id"]: page for page in pages_list}
    if args.discover:
        print(f"searching the archives for {len(pages_list)} pages", flush=True)
        manifest = discover_all(pages_list)
        MANIFEST.write_text(
            json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"wrote {MANIFEST.relative_to(ROOT)}")
    else:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        refetch(manifest)
    files = _pages_files(manifest, pages)
    tools = [tool.strip() for tool in args.tools.split(",") if tool.strip()]
    run_tools(files, tools)
    publish(manifest)
    print(f"done in {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()
