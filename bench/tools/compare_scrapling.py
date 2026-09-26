"""Scrapling's markdown on ``docs/scoreboard-tools.md``'s pages.

Run in an environment holding exactly
``bench/requirements/scrapling-markdown.txt``: Scrapling with its ``rag``
extra, which ``Response.markdown`` needs. The timed call builds a
``Response`` of the page, status 200, and asks ``markdown(main_content_only=
True)``, as Scrapling's own site-to-markdown spider does, and the title as
that spider reads it, ``<title>``'s text; it answers no author or date.

Scrapling's fetchers build a ``Response`` with the charset the server sent;
given bytes alone it reads them as UTF-8. So each page is handed to it as
text, decoded before the clock starts by the rule html-to-markdown is given
(``snippets.as_text``: UTF-8 when the bytes are, otherwise the charset the
page declares, otherwise windows-1252).

    python compare_scrapling.py PAGES OUT
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from scrapling.engines.toolbelt.custom import Response

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_common import answered, run, text_or_none
from snippets import as_text

NAME = "scrapling"
DISTRIBUTION = "scrapling"
# Every Response logs "Fetched (200)" at INFO: nothing was fetched here.
logging.disable(logging.CRITICAL)


def prepare(html: bytes) -> str:
    """The page as Scrapling is handed it, decoded before the clock starts."""
    return as_text(html)


@answered
def extract(text: str, url: str | None) -> dict[str, Any]:
    """The call the scoreboard scores and ``bench/timing.py`` times."""
    page = Response(url or "http://example.com/", text, 200, "OK", {}, {}, {})
    return {
        "title": text_or_none(page.css("title::text").get()),
        "author": None,
        "date": None,
        "text": page.markdown(main_content_only=True),
    }


if __name__ == "__main__":
    run(sys.modules[__name__], DISTRIBUTION, sys.argv[1], sys.argv[2])
