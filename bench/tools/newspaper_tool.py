"""newspaper4k over the test split, offline.

Run in an environment holding exactly ``bench/requirements/newspaper4k.txt``.
newspaper4k fetches images to size them, which hung the first run; image
fetching is turned off and the network is taken away, so it reads the same
bytes as every other tool and nothing else. Only ``download`` from the given
HTML and ``parse`` are timed.
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


def main(pages_path: str, out_path: str) -> None:
    root = Path(pages_path).parent
    pages = json.loads(Path(pages_path).read_text())
    config = Config()
    config.fetch_images = False
    results, seconds = [], 0.0
    for page in pages:
        html = gzip.decompress((root / page["path"]).read_bytes())
        text = html.decode("utf-8", "replace")
        started = time.perf_counter()
        try:
            article = Article(page["url"] or "http://example.com/", config=config)
            article.download(input_html=text)
            article.parse()
            row = {
                "title": article.title or None,
                "author": ", ".join(article.authors) or None,
                "date": (
                    article.publish_date.isoformat() if article.publish_date else None
                ),
            }
        except Exception:  # noqa: BLE001 -- a tool that raises answered nothing
            row = {"title": None, "author": None, "date": None}
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
        )
    )
    print(f"newspaper4k {newspaper.__version__}: {len(results)} pages, {seconds:.2f} s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
