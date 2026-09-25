"""The gate fails on a drop the paired comparison calls worse, or one past the
floor's tolerance, and on nothing else (``bench/PREREG.md``, "What counts as
worse").

It failed on a floor missed by one page traded for another, which made a
release choose between failing and ``--allow-regression``. The harness is not
in the sdist, and its scorer needs dateutil: without either, this skips.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "gate.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("dateutil")
sys.path.insert(0, str(BENCH))

import gate  # noqa: E402


def _pages(outcomes: list[str], field: str = "author") -> dict[str, dict[str, str]]:
    return {
        f"p{n:04}": {"title": "hit", "author": "hit", "date": "hit", field: outcome}
        for n, outcome in enumerate(outcomes)
    }


def _judge(today, base, name="wcxb.author.hit"):
    numbers = gate.labelled_numbers("wcxb", today)
    floor = gate.labelled_numbers("wcxb", base)[name]
    found = gate.labelled_comparisons("wcxb", today, base, only=name)[name]
    return gate.check(name, numbers[name], floor, found, len(today))


def test_one_page_traded_for_another_is_held_within_noise():
    base = _pages(["hit"] * 400 + ["silent"] * 200)
    today = dict(base)
    # Two pages lost, one gained: a page below the floor, on 600.
    for lost in ("p0000", "p0001"):
        today[lost] = {**base[lost], "author": "silent"}
    today["p0500"] = {**base["p0500"], "author": "hit"}
    judged = _judge(today, base)
    assert judged.today < judged.floor
    assert not judged.breached and judged.status == "held within noise"


def test_a_small_drop_on_many_pages_that_resampling_does_not_explain_fails():
    base = _pages(["hit"] * 1500 + ["silent"] * 500)
    today = dict(base)
    for n in range(15):
        today[f"p{n:04}"] = {**base[f"p{n:04}"], "author": "silent"}
    judged = _judge(today, base)
    # 0.0075 below: within the tolerance, but called worse.
    assert judged.floor - judged.today < gate.TOLERANCE
    assert judged.comparison.verdict == "worse"
    assert judged.breached and "called worse" in judged.status


def test_a_large_drop_on_few_pages_fails_although_inconclusive():
    base = _pages(["hit"] * 15 + ["silent"] * 5)
    today = dict(base)
    today["p0000"] = {**base["p0000"], "author": "silent"}
    judged = _judge(today, base)
    assert judged.comparison.verdict == "inconclusive"
    assert judged.breached and "tolerance" in judged.status


def test_a_number_at_its_floor_is_held():
    base = _pages(["hit"] * 15 + ["silent"] * 5)
    judged = _judge(base, base)
    assert judged.status == "held" and not judged.breached


def test_inventions_have_a_ceiling_and_a_tolerance_of_one_percent_of_the_pages():
    base = {
        f"p{n:04}": {"title": "hit", "author": "correct_silence", "date": "hit"}
        for n in range(300)
    }
    today = dict(base)
    for n in range(3):
        today[f"p{n:04}"] = {**base[f"p{n:04}"], "author": "invention"}
    judged = _judge(today, base, "wcxb.author.inventions")
    # Three more over 300 pages: at the tolerance, not past it; and three
    # pages alone do not tell today from the baseline.
    assert judged.today == 3 and judged.floor == 0
    assert judged.comparison.verdict == "inconclusive"
    assert judged.status == "held within noise"
    today["p0003"] = {**base["p0003"], "author": "invention"}
    judged = _judge(today, base, "wcxb.author.inventions")
    assert judged.breached


def test_raise_rewrites_a_board_s_baseline_only_when_all_its_numbers_hold():
    floors = {"wcxb.author.hit": 0.8, "wcxb.date.hit": 0.5}
    held = {"wcxb.author.hit": 0.8, "wcxb.date.hit": 0.6}
    dropped = {"wcxb.author.hit": 0.79, "wcxb.date.hit": 0.6}
    assert gate.rebaseline("wcxb", held, floors, allow_regression=False)
    assert not gate.rebaseline("wcxb", dropped, floors, allow_regression=False)
    assert gate.rebaseline("wcxb", dropped, floors, allow_regression=True)


def test_the_baseline_is_written_and_read_back_alike(tmp_path):
    outcomes = {
        "wcxb": _pages(["hit", "silent", "wrong"]),
        "swde": {("book-a", "isbn"): Counter(hit=3, wrong=1)},
        "products": {"p1": {"price": (1, 0, 0)}},
    }
    path = tmp_path / "floors-pages.json"
    gate.write_baseline(path, outcomes)
    assert gate.read_baseline(path) == outcomes
    assert json.loads(path.read_text(encoding="utf-8"))["swde"] == {
        "book-a": {"isbn": {"hit": 3, "wrong": 1}}
    }
