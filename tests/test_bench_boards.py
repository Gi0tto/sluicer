"""Every scoreboard prints how sure its numbers are, and calls a difference
only as the paired comparison does (``bench/PREREG.md``).

Each generator is fed a few made-up pages here, never a corpus. The harness is
not in the sdist, and its scorer needs dateutil: without either, this skips.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "evaldata.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("dateutil")
sys.path.insert(0, str(BENCH))

import evaldata  # noqa: E402
import realweb  # noqa: E402
import swde  # noqa: E402
import zyte  # noqa: E402

DASH = "\u2013"
KEYS = ("tp", "fp", "fn", "tn")


# --- trafilatura's main-text snippets --------------------------------------------


def _body(pages: int) -> dict:
    """``pages`` pages, six snippets each: the markdown finds five of each
    page's, trafilatura's text all six."""
    per_page = {
        f"p{n:02}": {
            "sluicer.markdown": [5, 1, 1, 5],
            "sluicer.markdown, its syntax taken out": [6, 1, 0, 5],
            "trafilatura text": [6, 0, 0, 6],
        }
        for n in range(pages)
    }
    totals = {
        name: dict(zip(KEYS, map(sum, zip(*rows, strict=True)), strict=True))
        for name, rows in (
            (name, [page[name] for page in per_page.values()])
            for name in per_page["p00"]
        )
    }
    return {"pages": pages, "outputs": totals, "per_page": per_page}


def test_the_snippets_carry_intervals_bootstrapped_over_pages():
    table = evaldata._body_table(_body(20))
    row = next(line for line in table if line.startswith("| sluicer.markdown |"))
    # Precision 100/120: every page alike, so every resample alike too.
    assert f"| 0.833 (0.83{DASH}0.84) |" in row


def test_the_markdown_is_called_against_trafilatura_s_text_by_the_pairs():
    lines = evaldata._body_comparisons(_body(20))
    recall = next(
        line for line in lines if "| recall |" in line and "taken" not in line
    )
    assert recall.endswith("| worse |")
    # With its syntax taken out it finds every snippet trafilatura does.
    same = next(line for line in lines if "| recall |" in line and "taken" in line)
    assert same.endswith("| inconclusive |")


# --- Zyte's products -------------------------------------------------------------


@pytest.fixture
def evaluator():
    """Zyte's evaluate.py, from the benchmark as ``bench/products.py`` fetches
    it; this checkout does not carry it, so without the cache these skip."""
    if not zyte.EVALUATE.exists():
        pytest.skip("Zyte's benchmark is not in bench/cache")
    return zyte.evaluator()


def test_zyte_s_matching_is_counted_page_by_page(evaluator):
    truth = {"a": {"price": ["10.00"]}, "b": {"price": ["5"]}, "c": {}}
    predicted = {"a": {"price": "10"}, "b": {"price": "6"}, "c": {"price": "1"}}
    assert zyte.counts(truth, predicted, "price", evaluator) == [
        (1, 0, 0),
        (0, 1, 1),
        (0, 1, 0),
    ]


def test_zyte_s_f1_is_its_own_formula(evaluator):
    # No false positive and no false negative is a precision and recall of 1.
    assert zyte.f1([0.0, 0.0, 0.0], evaluator) == 1.0
    assert zyte.f1([3.0, 1.0, 1.0], evaluator) == pytest.approx(0.75)


def test_a_system_right_on_every_page_another_misses_is_called_better(evaluator):
    truth = {f"p{n:02}": {"sku": [str(n)]} for n in range(30)}
    ours = {f"p{n:02}": {"sku": str(n)} for n in range(30)}
    theirs: dict[str, dict[str, str]] = {f"p{n:02}": {} for n in range(30)}
    found = zyte.compare(
        zyte.counts(truth, ours, "sku", evaluator),
        zyte.counts(truth, theirs, "sku", evaluator),
        evaluator,
    )
    assert found.verdict == "better" and found.observed == 1.0


# --- SWDE ------------------------------------------------------------------------


def _site_tallies(hits: int, wrong: int) -> dict:
    return {"title": Counter(hit=hits, wrong=wrong), "isbn": Counter(hit=hits)}


def test_swde_s_mean_f1_is_resampled_by_site():
    per = {}
    for n in range(12):
        for attribute, tally in _site_tallies(8 + n % 3, 2).items():
            per[(f"book-s{n:02}", attribute)] = tally
    keys = sorted(per)
    mean, low, high = swde.f1_interval(per, keys)
    assert mean == pytest.approx(swde._mean_f1(per, keys))
    assert low < mean < high


def test_swde_compares_the_two_tools_site_by_site():
    ours, theirs = {}, {}
    for n in range(12):
        for attribute, tally in _site_tallies(9, 1).items():
            ours[(f"book-s{n:02}", attribute)] = tally
        for attribute, tally in _site_tallies(5, 5).items():
            theirs[(f"book-s{n:02}", attribute)] = tally
    found = swde.f1_difference(ours, theirs, sorted(ours))
    assert found.verdict == "better"


# --- pages as served -------------------------------------------------------------


def _served(sluicer: str, other: str, pages: int = 30):
    ids = [str(n) for n in range(pages)]
    fields = ("title", "author", "date")
    return {
        side: {
            "sluicer": {i: dict.fromkeys(fields, sluicer) for i in ids},
            "trafilatura": {i: dict.fromkeys(fields, other) for i in ids},
        }
        for side in ("served", "stripped")
    }, {i: {"title": "t", "author": "a", "date": "d"} for i in ids}


def test_the_served_prose_says_behind_only_where_the_pairs_call_it():
    per_page, pages = _served("silent", "hit")
    runs = {
        side: {
            "sluicer": {"tool": "sluicer", "version": "0"},
            "trafilatura": {"tool": "trafilatura", "version": "1"},
        }
        for side in ("served", "stripped")
    }
    said = " ".join(realweb._plainly(runs, per_page, pages, realweb.verdicts(per_page)))
    assert "behind trafilatura" in said
    per_page["served"]["trafilatura"]["0"]["title"] = "silent"
    per_page["served"]["sluicer"]["0"]["title"] = "hit"
    for page in list(pages)[1:]:
        per_page["served"]["sluicer"][page]["title"] = "hit"
    said = " ".join(realweb._plainly(runs, per_page, pages, realweb.verdicts(per_page)))
    assert "**Title.**" in said
    title = next(line for line in said.split("- ") if "**Title.**" in line)
    assert "not told apart from trafilatura" in title
