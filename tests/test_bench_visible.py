"""Every title, author and date scoreboard scores ``--visible`` beside what
the pages declare, as ``bench/PREREG.md`` fixed it before any was run.

Two columns: the summary alone, and the summary with ``--visible``'s guess
where the summary has no answer. What the guesses changed is counted apart,
their inventions in a column of their own, and the second column is paired
against the first and against every other tool. The harness is not in the
sdist, and its scorer needs dateutil: without either, this skips.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "run.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("dateutil")
sys.path.insert(0, str(BENCH))

import run as board  # noqa: E402
import score  # noqa: E402

DASH = "\u2013"


def _harness():
    spec = importlib.util.spec_from_file_location(
        "sluicer_tool", BENCH / "tools" / "sluicer_tool.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the harness ------------------------------------------------------------------

PAGE = b"""<html><head><title>Brake pads, explained</title>
<meta property="og:title" content="Brake pads, explained"></head><body>
<article><h1>Brake pads, explained</h1>
<p class="byline">By Ada Lovelace</p>
<p>Published <time>12 March 2024</time></p>
<p>Some text about brake pads and when to change them.</p></article>
</body></html>"""


def test_the_harness_records_the_guesses_beside_the_summary():
    harness = _harness()
    summary = harness.extract(PAGE, "https://example.com/pads")
    found = harness.guesses(PAGE, "https://example.com/pads", summary)
    assert set(found) == {"title", "author", "date"}
    assert found["author"] == "Ada Lovelace"
    # The declared answer is the summary's, untouched by the guesses.
    assert summary.get("author") is None


def test_the_harness_stops_when_the_summary_changes_with_visible(monkeypatch):
    harness = _harness()
    summary = harness.extract(PAGE, "https://example.com/pads")
    real = harness.sluicer.extract

    def meddling(html, url=None, visible=False, **kwargs):
        result = real(html, url=url, visible=visible, **kwargs)
        if visible:
            result.summary["title"] = None
        return result

    monkeypatch.setattr(harness.sluicer, "extract", meddling)
    with pytest.raises(SystemExit, match="summary"):
        harness.guesses(PAGE, "https://example.com/pads", summary)


# --- declared, then what --visible adds --------------------------------------------


def test_a_guess_answers_only_where_the_page_declares_nothing():
    run = {
        "tool": "sluicer",
        "version": "0",
        "results": [
            {
                "id": "a",
                "title": "Declared",
                "author": None,
                "date": None,
                "visible": {"title": "Shown", "author": "Ada", "date": None},
            }
        ],
    }
    added = board.with_visible(run)
    row = added["results"][0]
    assert row == {"id": "a", "title": "Declared", "author": "Ada", "date": None}
    assert added["version"] == "0"


def test_results_run_before_the_harness_recorded_guesses_are_refused():
    run = {"tool": "sluicer", "version": "0", "results": [{"id": "a"}]}
    with pytest.raises(SystemExit, match="--tools sluicer"):
        board.with_visible(run)


def _pages(labels):
    return {
        page_id: {"page_type": "article", "title": t, "author": a, "date": d}
        for page_id, (t, a, d) in labels.items()
    }


def _board(pages_count=30):
    """Thirty pages: the page declares every title and no author; the byline
    shown is right on twenty, wrong on five, and on five pages with no author
    label --visible names one anyway."""
    labels, rows, other = {}, [], []
    for n in range(pages_count):
        page_id = f"p{n:02}"
        labelled = n < 25
        labels[page_id] = ("Title", "Ada Lovelace" if labelled else None, None)
        shown = "Ada Lovelace" if n < 20 else "Charles Babbage"
        rows.append(
            {
                "id": page_id,
                "title": "Title",
                "author": None,
                "date": None,
                "visible": {"title": "Title", "author": shown, "date": None},
            }
        )
        other.append(
            {"id": page_id, "title": "Title", "author": "Ada Lovelace", "date": None}
        )
    runs = {
        "sluicer": {"tool": "sluicer", "version": "0", "results": rows},
        "trafilatura": {"tool": "trafilatura", "version": "1", "results": other},
    }
    return runs, _pages(labels)


def test_the_two_columns_and_what_visible_changed():
    runs, pages = _board()
    lines = board.visible_table(runs, pages)
    row = next(line for line in lines if line.startswith("| author |"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    # Declared: nothing answered. Declared, then --visible: 20 of 25 labelled.
    assert cells[1] == "0.000 (0.00" + DASH + "0.14)"
    assert cells[2].startswith("0.800 (")
    # Right when answering: none answered, then 20 of 30 answers.
    assert cells[3] == "0.000"
    assert cells[4].startswith("0.667 (")
    # Counted apart: silent to hit, silent to wrong, silence to invention.
    assert cells[5:] == ["0", "20", "5", "5"]


def test_visible_is_paired_against_the_declared_answers_and_every_other_tool():
    runs, pages = _board()
    verdicts = board.visible_comparisons(runs, pages)
    assert len(verdicts) == 2 * 3 * 2
    assert verdicts[("sluicer", "author", "hit")].verdict == "better"
    assert verdicts[("trafilatura", "author", "hit")].verdict == "worse"
    assert verdicts[("sluicer", "title", "hit")].verdict == "inconclusive"


def test_the_section_says_what_it_compares_and_how_many():
    runs, pages = _board()
    text = "\n".join(board.visible_section(runs, pages))
    assert "WCXB's development split" in text
    assert "12 comparisons" in text
    assert "| sluicer 0, declared | author | hit rate |" in text
    assert "| trafilatura 1 | author | hit rate |" in text
    # What it added is said as this run counted it.
    assert "30 questions the summary left unanswered" in text
    assert "20 right, 5 wrong and 5 invented" in text


def test_no_other_tool_leaves_only_the_pairing_with_the_declared_answers():
    runs, pages = _board()
    del runs["trafilatura"]
    verdicts = board.visible_comparisons(runs, pages)
    assert {against for against, _field, _measure in verdicts} == {"sluicer"}


def test_score_counts_a_guess_like_any_answer():
    runs, pages = _board()
    added = board.with_visible(runs["sluicer"])
    counts = score.tally(score.outcomes(added["results"], pages), pages)
    assert counts["author"]["hit"] == 20 and counts["author"]["invention"] == 5
