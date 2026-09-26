"""Sluicer on ``docs/scoreboard-tools.md``'s pages, from the checkout under test.

Run in an environment holding this checkout, installed editable, and the
trafilatura ``bench/requirements/trafilatura.txt`` pins for its ``markdown``
extra: ``pip install "sluicer[markdown]"``. The timed call is ``extract``'s
summary and ``sluicer.markdown.to_markdown``; ``--visible``'s guesses are read
after it, untimed, as every scoreboard reads them (``sluicer_tool.guesses``).
A question the page answers two ways that mean different things is flagged:
the one warning, of all the tools here, that goes with an answer.

    python compare_sluicer.py PAGES OUT
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import sluicer
import sluicer.markdown

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_common import answered, run, text_or_none
from sluicer_tool import FIELDS, guesses

NAME = "sluicer"
DISTRIBUTION = "sluicer"


@answered
def extract(html: bytes, url: str | None) -> dict[str, Any]:
    """The call the scoreboard scores and ``bench/timing.py`` times."""
    found = sluicer.extract(html, url=url, visible=False)
    row: dict[str, Any] = {}
    for field, question in FIELDS.items():
        answer = found.summary.get(question)
        row[field] = text_or_none(answer.value) if answer else None
        row[f"{field}_from"] = f"{answer.source} {answer.key}" if answer else None
    row["flagged"] = sorted(
        field
        for field, question in FIELDS.items()
        if any(conflict.question == question for conflict in found.conflicts)
    )
    row["text"] = sluicer.markdown.to_markdown(html, url=url)
    return row


def after(html: bytes, url: str | None, row: dict[str, Any]) -> None:
    """``--visible``'s guesses, untimed, beside the summary's answers."""
    summary = sluicer.extract(html, url=url, visible=False).summary
    row["visible"] = guesses(html, url, summary)


if __name__ == "__main__":
    run(sys.modules[__name__], DISTRIBUTION, sys.argv[1], sys.argv[2])
