"""newspaper4k on ``docs/scoreboard-tools.md``'s pages, offline.

Run in an environment holding exactly ``bench/requirements/newspaper4k.txt``.
``newspaper_tool`` takes the network away and turns image fetching off when
it is imported, and decodes each page before the clock starts, as on the
other scoreboards. The timed call is ``download(input_html=...)`` and
``parse()``; its text is ``article.text``, plain text, since it writes no
markdown.

    python compare_newspaper4k.py PAGES OUT
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_common import answered, run, text_or_none
from newspaper_tool import _CONFIG, Article, prepare  # noqa: F401

NAME = "newspaper4k"
DISTRIBUTION = "newspaper4k"


@answered
def extract(text: str, url: str | None) -> dict[str, Any]:
    """The call the scoreboard scores and ``bench/timing.py`` times."""
    article = Article(url or "http://example.com/", config=_CONFIG)
    article.download(input_html=text)
    article.parse()
    return {
        "title": text_or_none(article.title),
        "author": text_or_none(", ".join(article.authors)),
        "date": article.publish_date.isoformat() if article.publish_date else None,
        "text": article.text,
    }


if __name__ == "__main__":
    run(sys.modules[__name__], DISTRIBUTION, sys.argv[1], sys.argv[2])
