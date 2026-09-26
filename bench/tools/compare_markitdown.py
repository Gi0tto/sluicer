"""markitdown on ``docs/scoreboard-tools.md``'s pages.

Run in an environment holding exactly ``bench/requirements/markitdown.txt``,
its base install. The timed call is ``convert_stream`` of the page's bytes,
told they are HTML from the page's address; it answers a title and markdown,
and no author or date.

    python compare_markitdown.py PAGES OUT
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

from markitdown import MarkItDown, StreamInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_common import answered, run, text_or_none

NAME = "markitdown"
DISTRIBUTION = "markitdown"
_CONVERTER = MarkItDown()


@answered
def extract(html: bytes, url: str | None) -> dict[str, Any]:
    """The call the scoreboard scores and ``bench/timing.py`` times."""
    found = _CONVERTER.convert_stream(
        io.BytesIO(html),
        stream_info=StreamInfo(extension=".html", mimetype="text/html", url=url),
    )
    return {
        "title": text_or_none(found.title),
        "author": None,
        "date": None,
        "text": found.markdown,
    }


if __name__ == "__main__":
    run(sys.modules[__name__], DISTRIBUTION, sys.argv[1], sys.argv[2])
