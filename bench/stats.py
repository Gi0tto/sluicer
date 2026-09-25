"""How sure a scoreboard's number is, and how a difference between two is called.

Both are fixed in ``bench/PREREG.md``, "How sure a number is, and how a
difference is called", written before any interval or verdict was computed on
a result.

- **A rate** carries its 95% Wilson score interval, printed beside it with its
  bounds to two places rounded outwards, so what is printed always holds what
  was computed: ``0.727 (0.68-0.77)``, the bounds joined by an en dash. A
  rate over no trials has none.
- **A difference** between two things scored on the same pages -- Sluicer and
  another tool, a page as served and as WCXB kept it, today and the baseline
  -- is a paired bootstrap: 10,000 samples of the n pages drawn with
  replacement by ``random.Random(20260924).choices``, the pages in the order
  of their ids, the statistic recomputed on each, and the 251st and 9,750th of
  the sorted results taken as its interval. Every comparison starts again from
  the seed, so each can be reproduced alone. **Better** when the interval is
  above zero, **worse** when below, **inconclusive** when it holds zero.

Every statistic here is a function of sums over the pages (hits and trials,
true and false positives, an F1 total and a count of site-attributes), so a
sample is summed column by column and the statistic applied to the sums. A
rate over no trials in a sample counts 0, as ``bench/score.py`` counts it.
"""

from __future__ import annotations

import math
import random
from array import array
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

# The normal distribution's 97.5th percentile.
Z = 1.959963984540054
SEED = 20260924
SAMPLES = 10_000
# Between an interval's bounds, as PREREG prints them.
DASH = "\u2013"


# --- a rate ---------------------------------------------------------------------


def wilson(hits: int, trials: int) -> tuple[float, float] | None:
    """The 95% Wilson score interval of ``hits`` in ``trials``, or None.

    Centre (p + z²/2n) / (1 + z²/n), half-width
    z / (1 + z²/n) · √(p(1 - p)/n + z²/4n²). Unlike p ± z·√(p(1-p)/n) it stays
    inside 0 and 1 and is not zero wide at either, where several rates sit.
    """
    if trials <= 0:
        return None
    p = hits / trials
    z2 = Z * Z
    scale = 1 + z2 / trials
    centre = (p + z2 / (2 * trials)) / scale
    half = Z / scale * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials))
    # At 0 or n the bound is 0 or 1 exactly; computed, it is off by a rounding.
    low = 0.0 if hits == 0 else max(0.0, centre - half)
    high = 1.0 if hits == trials else min(1.0, centre + half)
    return low, high


def _down(value: float, places: int) -> str:
    step = 10**places
    return f"{math.floor(Fraction(value) * step) / step:.{places}f}"


def _up(value: float, places: int) -> str:
    step = 10**places
    return f"{math.ceil(Fraction(value) * step) / step:.{places}f}"


def rate(hits: int, trials: int) -> str:
    """``0.727 (0.68-0.77)``, an en dash between the bounds: hits over
    trials, and its Wilson interval with the lower bound rounded down and the
    upper up. Over no trials, ``0.000`` alone, as ``bench/score.py`` counts
    such a rate."""
    bounds = wilson(hits, trials)
    value = hits / trials if trials else 0.0
    if bounds is None:
        return f"{value:.3f}"
    return f"{value:.3f} ({_down(bounds[0], 2)}{DASH}{_up(bounds[1], 2)})"


# --- a difference ---------------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    """A statistic on every page, and its 95% percentile interval."""

    observed: float
    low: float
    high: float

    @property
    def verdict(self) -> str:
        """Better, worse or inconclusive; a bound of exactly zero is not past it."""
        if self.low > 0:
            return "better"
        if self.high < 0:
            return "worse"
        return "inconclusive"


@lru_cache(maxsize=4)
def draws(n: int, samples: int = SAMPLES, seed: int = SEED) -> tuple[array, ...]:
    """The pages each sample holds, as positions in the id-ordered list.

    ``choices`` picks ``population[floor(random() * n)]``, so drawing
    positions is drawing the pages themselves. Kept, since every comparison
    over n pages starts from the same seed and so draws the same samples.
    """
    rng = random.Random(seed)
    positions = range(n)
    return tuple(array("I", rng.choices(positions, k=n)) for _ in range(samples))


def percentiles(values: list[float]) -> tuple[float, float]:
    """The 95% percentile interval: of the values in ascending order, the
    251st and the 9,750th of 10,000."""
    ordered = sorted(values)
    count = len(ordered)
    return ordered[int(count * 0.025)], ordered[int(count * 0.975) - 1]


def _resampled(
    columns: Sequence[Sequence[float]],
    statistic: Callable[[list[float]], float],
    samples: int,
    seed: int,
) -> tuple[float, float, float]:
    n = len(columns[0])
    if any(len(column) != n for column in columns):
        raise ValueError("every column holds one value per page")
    observed = statistic([float(sum(column)) for column in columns])
    readers = [column.__getitem__ for column in columns]
    values = [
        statistic([float(sum(map(read, draw))) for read in readers])
        for draw in draws(n, samples, seed)
    ]
    low, high = percentiles(values)
    return observed, low, high


def compare(
    columns: Sequence[Sequence[float]],
    statistic: Callable[[list[float]], float],
    *,
    samples: int = SAMPLES,
    seed: int = SEED,
) -> Comparison:
    """A difference, paired page by page.

    ``columns`` hold one value per page, the pages in the order of their ids;
    ``statistic`` takes the columns' sums over a sample and returns the
    difference, this side's minus the other's.
    """
    return Comparison(*_resampled(columns, statistic, samples, seed))


def interval(
    columns: Sequence[Sequence[float]],
    statistic: Callable[[list[float]], float],
    *,
    samples: int = SAMPLES,
    seed: int = SEED,
) -> tuple[float, float, float]:
    """One number and its bootstrapped percentile interval, for a rate whose
    trials are not independent: resampled over what is (SWDE's sites, the
    pages several snippets sit on)."""
    return _resampled(columns, statistic, samples, seed)


def ratio(numerator: float, denominator: float) -> float:
    """A rate, 0 over no trials."""
    return numerator / denominator if denominator else 0.0


def rate_difference(
    our_hits: Sequence[float],
    our_trials: Sequence[float],
    their_hits: Sequence[float],
    their_trials: Sequence[float],
    *,
    samples: int = SAMPLES,
    seed: int = SEED,
) -> Comparison:
    """Our rate minus theirs, on the same pages."""
    return compare(
        [our_hits, our_trials, their_hits, their_trials],
        lambda s: ratio(s[0], s[1]) - ratio(s[2], s[3]),
        samples=samples,
        seed=seed,
    )


def _signed(value: float, rounded: str) -> str:
    return rounded if float(rounded) == 0 else ("+" if value > 0 else "") + rounded


def difference(comparison: Comparison) -> str:
    """``+0.021 (-0.011 to +0.053)``: the difference, and its interval with
    the lower bound rounded down and the upper up, to three places."""
    observed = f"{comparison.observed:.3f}"
    if float(observed) == 0:
        observed = f"{0:.3f}"
    low = _down(comparison.low, 3)
    high = _up(comparison.high, 3)
    return (
        f"{_signed(comparison.observed, observed)} "
        f"({_signed(comparison.low, low)} to {_signed(comparison.high, high)})"
    )
