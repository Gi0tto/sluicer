"""How sure a scoreboard's number is, and how a difference is called.

``bench/PREREG.md`` fixes both before any was computed: a Wilson score
interval for every rate, and a paired bootstrap, from one seed, whose
percentile interval calls a difference better, worse or inconclusive. These
hold ``bench/stats.py`` to intervals published for known counts and to the
computation PREREG writes out, done the slow way. The harness is not in the
sdist: without it, this skips.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "stats.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
sys.path.insert(0, str(BENCH))

import stats  # noqa: E402

# Wilson 95% intervals as published. The first three are what any Wilson
# calculator gives; the last four are Newcombe (1998), "Two-sided confidence
# intervals for the single proportion", Statistics in Medicine 17, table II,
# method 3, to four places.
PUBLISHED = [
    (0, 10, 0.0, 0.2775328),
    (10, 10, 0.7224672, 1.0),
    (5, 10, 0.2365931, 0.7634069),
    (81, 263, 0.2553, 0.3662),
    (15, 148, 0.0624, 0.1605),
    (0, 20, 0.0, 0.1611),
    (1, 29, 0.0061, 0.1718),
]


@pytest.mark.parametrize(("hits", "trials", "low", "high"), PUBLISHED)
def test_wilson_is_the_published_interval(hits, trials, low, high):
    places = 7 if trials == 10 else 4
    found = stats.wilson(hits, trials)
    assert found is not None
    assert round(found[0], places) == low
    assert round(found[1], places) == high


def test_wilson_stays_inside_zero_and_one_and_is_never_zero_wide():
    assert stats.wilson(0, 3) == (0.0, pytest.approx(0.5614970))
    assert stats.wilson(3, 3) == (pytest.approx(0.4385030), 1.0)


def test_a_rate_over_no_trials_has_no_interval():
    assert stats.wilson(0, 0) is None
    assert stats.rate(0, 0) == "0.000"


def test_a_rate_is_printed_with_its_bounds_rounded_outwards():
    assert stats.rate(5, 10) == "0.500 (0.23\u20130.77)"
    assert stats.rate(0, 10) == "0.000 (0.00\u20130.28)"
    assert stats.rate(10, 10) == "1.000 (0.72\u20131.00)"
    for hits, trials in [(372, 511), (1, 3), (263, 263), (97, 851)]:
        low, high = stats.wilson(hits, trials)
        printed = stats.rate(hits, trials).split("(")[1].rstrip(")").split(stats.DASH)
        assert float(printed[0]) <= low and float(printed[1]) >= high


def test_the_samples_are_python_s_choices_from_the_seed_over_the_pages_in_id_order():
    pages = sorted(["p3", "p1", "p2", "p10"])
    rng = random.Random(stats.SEED)
    expected = [rng.choices(pages, k=len(pages)) for _ in range(50)]
    drawn = [[pages[i] for i in draw] for draw in stats.draws(len(pages), 50)]
    assert drawn == expected


def test_every_comparison_starts_again_from_the_seed():
    ours, theirs = [1, 0, 1, 1, 0, 1, 0, 1], [0, 0, 1, 0, 0, 1, 1, 0]
    ones = [1] * 8
    first = stats.rate_difference(ours, ones, theirs, ones)
    stats.rate_difference(theirs, ones, ours, ones, samples=300)
    assert stats.rate_difference(ours, ones, theirs, ones) == first


def _slow(ours, theirs, samples):
    """PREREG's paired bootstrap written out: resample the pages, recompute
    both hit rates, take the 2.5th and 97.5th percentiles of the differences."""
    rng = random.Random(stats.SEED)
    n = len(ours)
    differences = []
    for _ in range(samples):
        picked = rng.choices(range(n), k=n)
        differences.append(
            sum(ours[i] for i in picked) / n - sum(theirs[i] for i in picked) / n
        )
    differences.sort()
    return differences[int(samples * 0.025)], differences[int(samples * 0.975) - 1]


def test_the_paired_bootstrap_is_the_computation_prereg_writes():
    flip = random.Random(7)
    ours = [int(flip.random() < 0.7) for _ in range(60)]
    theirs = [int(flip.random() < 0.5) for _ in range(60)]
    ones = [1] * 60
    found = stats.rate_difference(ours, ones, theirs, ones, samples=2000)
    low, high = _slow(ours, theirs, 2000)
    assert found.observed == pytest.approx(sum(ours) / 60 - sum(theirs) / 60)
    assert (found.low, found.high) == (pytest.approx(low), pytest.approx(high))


def test_the_percentile_interval_is_the_251st_and_the_9750th_of_10000():
    assert stats.percentiles([float(v) for v in range(10_000, 0, -1)]) == (
        251.0,
        9750.0,
    )


def test_a_difference_is_called_by_where_its_interval_lies():
    assert stats.Comparison(0.1, 0.01, 0.2).verdict == "better"
    assert stats.Comparison(-0.1, -0.2, -0.01).verdict == "worse"
    assert stats.Comparison(0.1, -0.01, 0.2).verdict == "inconclusive"
    # A bound of exactly zero is not past it.
    assert stats.Comparison(0.1, 0.0, 0.2).verdict == "inconclusive"
    assert stats.Comparison(-0.1, -0.2, 0.0).verdict == "inconclusive"


def test_the_same_pages_with_the_same_outcomes_differ_by_nothing():
    same = [1, 0, 1, 1, 0]
    ones = [1] * 5
    found = stats.rate_difference(same, ones, same, ones)
    assert (found.observed, found.low, found.high, found.verdict) == (
        0.0,
        0.0,
        0.0,
        "inconclusive",
    )


def test_a_tool_right_on_every_page_the_other_misses_is_better():
    found = stats.rate_difference([1] * 30, [1] * 30, [0] * 30, [1] * 30)
    assert found.verdict == "better" and found.low == found.high == 1.0


def test_a_rate_over_no_trials_in_a_sample_counts_zero():
    # One page answered, by one side: most samples hold it, some do not.
    hits, trials = [1, 0, 0, 0], [1, 0, 0, 0]
    found = stats.rate_difference(hits, trials, [0] * 4, [0] * 4, samples=500)
    assert found.low == 0.0 and found.high == 1.0


def test_a_difference_is_printed_signed_with_its_bounds_outwards():
    printed = stats.difference(stats.Comparison(0.0213, -0.01049, 0.05201))
    assert printed == "+0.021 (-0.011 to +0.053)"
    assert stats.difference(stats.Comparison(0.0, 0.0, 0.0)) == "0.000 (0.000 to 0.000)"


def test_a_bootstrapped_interval_of_one_number():
    # A mean of per-site sums over per-site counts, resampled by site.
    sums, counts = [2.0, 0.5, 1.0, 3.0], [2, 1, 1, 3]
    observed, low, high = stats.interval([sums, counts], lambda s: s[0] / s[1])
    assert observed == pytest.approx(6.5 / 7)
    assert low <= observed <= high <= 1.0
