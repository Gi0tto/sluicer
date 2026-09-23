"""A polite, cached reader of Wayback Machine snapshots.

One request a second at most, a user agent that names this project, a back-off
on 429 and 5xx, and every answer kept under ``bench/cache/drift/`` so a rerun
asks the archive for nothing it already gave. Snapshots are read in the
``id_`` form, which returns the page as it was captured, without the
archive's toolbar or its rewritten links -- and with the encoding it was
served in, so a gzip or brotli body is decoded here.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "sluicer-drift-bench/0.2 (+https://gi0tto.github.io/sluicer/drift/)"
CACHE = Path(__file__).resolve().parent.parent / "cache" / "drift"
# Bumped when what a cached entry holds changes, so an old cache is not trusted.
_CACHE_FORMAT = "2"
_last_request = [0.0]


@dataclass(frozen=True)
class Snapshot:
    """One capture: the address asked for, when it was captured, where the
    archive's redirects landed -- another address when the site redirected --
    and the page's decoded bytes."""

    url: str
    timestamp: str
    landed: str
    html: bytes


def snapshot(url: str, when: str) -> Snapshot | None:
    """The capture of ``url`` nearest to ``when`` (YYYYMMDD[hhmmss]), or None.

    The archive redirects a request for any date to its nearest capture; the
    capture's own timestamp is read from where the redirect lands.
    """
    meta, body = _paths(url, when)
    if meta.exists():
        record = json.loads(meta.read_text())
        if record.get("missing"):
            return None
        return Snapshot(url, record["timestamp"], record["landed"], body.read_bytes())
    CACHE.mkdir(parents=True, exist_ok=True)
    landed, encoding, raw = _get(f"https://web.archive.org/web/{when}id_/{url}")
    if raw is None or landed is None or "id_/" not in landed:
        meta.write_text(json.dumps({"missing": True}))
        return None
    timestamp = landed.split("/web/", 1)[1].split("id_/", 1)[0]
    original = landed.split("id_/", 1)[1]
    html = _decode(raw, encoding)
    for key in (when, timestamp):
        meta, body = _paths(url, key)
        body.write_bytes(html)
        meta.write_text(
            json.dumps({"url": url, "timestamp": timestamp, "landed": original})
        )
    return Snapshot(url, timestamp, original, html)


def _paths(url: str, when: str) -> tuple[Path, Path]:
    key = hashlib.sha256(f"{_CACHE_FORMAT}:{url}@{when}".encode()).hexdigest()[:24]
    return CACHE / f"{key}.json", CACHE / f"{key}.html"


def _decode(raw: bytes, encoding: str) -> bytes:
    encoding = encoding.strip().lower()
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        return gzip.decompress(raw)
    if encoding == "deflate":
        return zlib.decompress(raw)
    if encoding == "br":
        import brotli  # type: ignore[import-not-found]  # run with --with brotli

        return bytes(brotli.decompress(raw))
    return raw


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _get(address: str) -> tuple[str | None, str, bytes | None]:
    """Where the address landed, its encoding and its body; None for a capture
    the archive does not have. Redirects are followed here, one request a
    second like the rest. An archive that keeps failing is an error, not an
    absence, so it is never cached as one."""
    failures = 0
    for _hop in range(10):
        wait = 1.1 - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
        request = urllib.request.Request(address, headers={"User-Agent": USER_AGENT})
        try:
            with _opener.open(request, timeout=60) as response:
                encoding = response.headers.get("Content-Encoding") or ""
                return address, encoding, response.read()
        except urllib.error.HTTPError as failure:
            if (
                failure.code in (301, 302, 303, 307, 308)
                and failure.headers["Location"]
            ):
                address = urllib.parse.urljoin(address, failure.headers["Location"])
                continue
            if failure.code in (429, 500, 502, 503, 504) and failures < 3:
                failures += 1
                time.sleep(5 * failures)
                continue
            if failure.code in (429, 500, 502, 503, 504):
                break
            return None, "", None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if failures >= 3:
                break
            failures += 1
            time.sleep(5 * failures)
    raise RuntimeError(f"the archive kept failing for {address}; try again later")
