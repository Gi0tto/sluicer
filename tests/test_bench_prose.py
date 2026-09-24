"""What a scoreboard's generator says about its results is counted from them.

``bench/run.py`` printed "Sluicer gives none where the page states none" on
every run, beside a table in which Sluicer invented 42 authors. The harness is
not in the sdist, and its scorer needs dateutil: without either, this skips.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "run.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("dateutil")
sys.path.insert(0, str(BENCH))

import run as board  # noqa: E402


def _counts(**inventions: dict[str, int]) -> dict[str, dict[str, Counter[str]]]:
    return {
        tool: {
            field: Counter(invention=made.get(field, 0), hit=10)
            for field in ("title", "author", "date")
        }
        for tool, made in inventions.items()
    }


def test_what_a_tool_invented_is_said_as_the_run_counted_it():
    said = " ".join(
        board._inventions(
            _counts(sluicer={"author": 42, "date": 8}, trafilatura={"date": 216})
        )
    )
    assert "gives none" not in said
    assert "sluicer 42 authors and 8 dates" in said
    assert "trafilatura 216 dates" in said


def test_a_tool_that_invented_nothing_is_said_to():
    said = " ".join(board._inventions(_counts(sluicer={}, trafilatura={"title": 1})))
    assert "sluicer nothing" in said and "trafilatura 1 title;" not in said
    assert "trafilatura 1 title." in said


def test_the_gap_is_named_where_the_run_shows_one():
    pages = {str(n): {"page_type": "article"} for n in range(4)}
    per_page = {
        "sluicer": {
            str(n): {"title": "hit", "author": "silent", "date": "hit"}
            for n in range(4)
        },
        "trafilatura": {
            str(n): {"title": "hit", "author": "hit", "date": "silent"}
            for n in range(4)
        },
    }
    said = board._gaps(per_page, pages)
    assert said.startswith("Sluicer's hit rate is below another tool's on author")
    assert "date" not in said and "title" not in said
