"""newspaper4k over the test split, offline.

Run in an environment holding exactly ``bench/requirements/newspaper4k.txt``.
newspaper4k fetches images to size them, which hung the first run; image
fetching is turned off and the network is taken away, so it reads the same
bytes as every other tool and nothing else. Only ``download`` from the given
HTML and ``parse`` are timed, here and by ``bench/timing.py``, which times the
same function.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import socket
import sys
import time
from pathlib import Path


def _refuse(*args: object, **kwargs: object) -> None:
    raise RuntimeError("the scoreboard runs offline")


socket.create_connection = _refuse  # type: ignore[assignment]
socket.socket.connect = _refuse  # type: ignore[assignment,method-assign]
socket.getaddrinfo = _refuse  # type: ignore[assignment]

import newspaper  # noqa: E402 -- after the network is gone
from newspaper import Article, Config  # noqa: E402

# What the interpreter brings whatever is installed, and so not the tool's.
_INTERPRETER = {"pip", "setuptools", "wheel"}


_CONFIG = Config()
_CONFIG.fetch_images = False


def prepare(html: bytes) -> str:
    """The page as newspaper4k is handed it, decoded before the clock starts."""
    return html.decode("utf-8", "replace")


def extract(text: str, url: str | None) -> dict[str, str | None]:
    """The call a scoreboard scores and ``bench/timing.py`` times."""
    try:
        article = Article(url or "http://example.com/", config=_CONFIG)
        article.download(input_html=text)
        article.parse()
        return {
            "title": article.title or None,
            "author": ", ".join(article.authors) or None,
            "date": (
                article.publish_date.isoformat() if article.publish_date else None
            ),
        }
    except Exception:  # noqa: BLE001 -- a tool that raises answered nothing
        return {"title": None, "author": None, "date": None}


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    results, seconds = [], 0.0
    for page in pages:
        text = prepare(gzip.decompress((root / page["path"]).read_bytes()))
        started = time.perf_counter()
        row = extract(text, page["url"])
        seconds += time.perf_counter() - started
        results.append({"id": page["id"], **row})
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": "newspaper4k",
                "version": newspaper.__version__,
                "seconds": seconds,
                "packages": len(
                    {d.metadata["Name"] for d in importlib.metadata.distributions()}
                    - _INTERPRETER
                ),
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    print(f"newspaper4k {newspaper.__version__}: {len(results)} pages, {seconds:.2f} s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
