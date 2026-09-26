"""trafilatura on ``docs/scoreboard-tools.md``'s pages.

Run in an environment holding exactly ``bench/requirements/trafilatura.txt``.
The timed call is ``extract_metadata``, as the other scoreboards call it, and
``extract`` with ``output_format="markdown"``, its defaults otherwise.

    python compare_trafilatura.py PAGES OUT
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import trafilatura

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_common import answered, run, text_or_none

NAME = "trafilatura"
DISTRIBUTION = "trafilatura"
logging.disable(logging.CRITICAL)


@answered
def extract(html: bytes, url: str | None) -> dict[str, Any]:
    """The call the scoreboard scores and ``bench/timing.py`` times."""
    found = trafilatura.extract_metadata(html, default_url=url)
    text = trafilatura.extract(html, url=url, output_format="markdown")
    return {
        "title": text_or_none(getattr(found, "title", None)),
        "author": text_or_none(getattr(found, "author", None)),
        "date": text_or_none(getattr(found, "date", None)),
        "text": text,
    }


if __name__ == "__main__":
    run(sys.modules[__name__], DISTRIBUTION, sys.argv[1], sys.argv[2])
