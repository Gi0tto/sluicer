"""The benchmark's date rule gives the same answer on every day it is run.

dateutil fills a part a date does not write with today's, so "March 2021"
matched a label of 2021-03-24 on the 24th of a month and no other day, and
"10:52" matched today's date. The harness is not in the sdist, and its scorer
needs dateutil: without either, this skips.
"""

from __future__ import annotations

import datetime
import sys
import types
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "score.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
parser_module = pytest.importorskip("dateutil.parser._parser")
sys.path.insert(0, str(BENCH))

import score  # noqa: E402

# Each answer, a label, and the verdict bench/PREREG.md's rule gives.
PAIRS = [
    # The label has a day and the answer says none: wrong, whatever today is.
    ("March 2021", "2021-03-24", False),
    ("March 2021", "2021-03-01", False),
    # The label says only a month, and the answer's is that month.
    ("2021-03-17", "2021-03", True),
    # No year, month or day at all.
    ("10:52", "2026-09-24", False),
    ("2:33 PM", "2026-03-09", False),
    ("2023 Jan 7", "2023-01-07", True),
    # Numbers written with dots are day first; with slashes, month first.
    ("10.12.2022, 07:00:03", "2022-12-10", True),
    ("11/01/2023 12:43:42", "2023-11-01", True),
    # Both with an offset: the same instant, read in the label's offset.
    ("2025-06-04T22:30:00Z", "2025-06-05 00:30:00+02:00", True),
    # A label with no offset: the answer's calendar date as it writes it.
    ("2025-06-04T22:30:00Z", "2025-06-05", False),
]


def _on(monkeypatch, day: datetime.datetime) -> list[bool]:
    """Every pair's verdict, with dateutil's clock set to ``day``."""

    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return day

    clock = types.SimpleNamespace(**vars(datetime))
    clock.datetime = Clock
    monkeypatch.setattr(parser_module, "datetime", clock)
    return [score.date_matches(got, want) for got, want, _ in PAIRS]


def test_a_date_is_scored_alike_on_any_day(monkeypatch):
    days = [
        datetime.datetime(2026, 9, 24),
        datetime.datetime(2026, 3, 9),
        datetime.datetime(2027, 1, 1),
    ]
    verdicts = [_on(monkeypatch, day) for day in days]
    assert verdicts[0] == verdicts[1] == verdicts[2]


def test_the_rule_prereg_writes():
    """bench/PREREG.md, "How an answer is scored"."""
    for got, want, verdict in PAIRS:
        assert score.date_matches(got, want) is verdict, (got, want)
