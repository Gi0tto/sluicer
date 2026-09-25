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


def _per_page(sluicer: dict[str, str], other: dict[str, str], pages: int = 30):
    return {
        "sluicer": {str(n): dict(sluicer) for n in range(pages)},
        "trafilatura": {str(n): dict(other) for n in range(pages)},
    }


def test_the_gap_is_named_where_the_paired_comparison_calls_it():
    per_page = _per_page(
        {"title": "hit", "author": "silent", "date": "hit"},
        {"title": "hit", "author": "hit", "date": "silent"},
    )
    said = board._gaps(board.comparisons(per_page))
    assert said.startswith(
        "By the paired comparisons below, Sluicer's hit rate is behind another "
        "tool's on author:"
    )
    assert "on author, behind trafilatura" in said
    assert "date" not in said and "title" not in said


def test_a_rate_a_page_above_another_is_called_inconclusive_not_a_loss():
    """One page in thirty is a difference resampling explains: PREREG says a
    scoreboard calls it inconclusive, where it had printed a loss."""
    per_page = _per_page(
        {"title": "hit", "author": "hit", "date": "hit"},
        {"title": "hit", "author": "hit", "date": "hit"},
    )
    per_page["trafilatura"]["0"]["author"] = "hit"
    per_page["sluicer"]["0"]["author"] = "silent"
    verdicts = board.comparisons(per_page)
    assert verdicts[("trafilatura", "author", "hit")].verdict == "inconclusive"
    assert "behind" not in board._gaps(verdicts)


def test_every_rate_is_printed_with_its_interval():
    pages = {str(n): {"page_type": "article"} for n in range(10)}
    per_page = {
        "sluicer": {
            str(n): {
                "title": "hit" if n < 5 else "wrong",
                "author": "hit",
                "date": "silent",
            }
            for n in range(10)
        }
    }
    runs = {"sluicer": {"tool": "sluicer", "version": "0"}}
    row = board._summary_table(runs, per_page, pages)[2]
    assert "| 0.500 (0.23\u20130.77) |" in row
    assert "| 1.000 (0.72\u20131.00) |" in row


def test_the_table_of_verdicts_says_how_many_it_makes():
    per_page = _per_page(
        {"title": "hit", "author": "silent", "date": "hit"},
        {"title": "hit", "author": "hit", "date": "silent"},
    )
    runs = {
        "sluicer": {"tool": "sluicer", "version": "0"},
        "trafilatura": {"tool": "trafilatura", "version": "1"},
    }
    table = " ".join(board.comparison_table(runs, board.comparisons(per_page)))
    assert "6 comparisons" in table and "no correction" in table
    assert (
        "| trafilatura 1 | author | hit rate | -1.000 (-1.000 to -1.000) | worse |"
        in (table)
    )
