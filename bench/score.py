"""Score a tool's answers against the WCXB labels, four outcomes per field.

Where a page has a label, a tool's answer is a **hit** when it matches, **wrong**
when it does not, and a **silent miss** when there is no answer. Where a page
has no label, no answer is a **correct silence** and any answer is an
**invention**. WCXB leaves labels empty on purpose -- author on 63% of the
test pages, date on 48% -- so the last column measures whether a tool makes
things up.

The matching rules:

- title: lowercased and whitespace collapsed; equal, or one contains the other
  and the shorter is at least 0.6 of the longer.
- author: the letter runs of each, lowercased, less "by", "and", "the",
  "staff", "team", "editor(s)", "writer", "de", "von"; a hit when the shared
  tokens cover at least half of the label's and a quarter of the answer's, so
  a whole byline paragraph that happens to contain the name is not a hit.
- date: both parsed with dateutil, by the rule ``bench/PREREG.md`` writes
  under "How an answer is scored": a hit when the answer says every part of
  the date the label says -- year, month, day -- and each is the label's.
  Numbers written with dots are read day first, with slashes month first;
  when both carry a UTC offset the answer is read in the label's.
"""

from __future__ import annotations

import datetime
import re
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any

import stats
from dateutil import parser as dates

FIELDS = ("title", "author", "date")
OUTCOMES = ("hit", "wrong", "silent", "correct_silence", "invention")
COMMERCIAL = frozenset({"article", "listing", "collection", "product"})
_STOP = {
    "by",
    "and",
    "the",
    "staff",
    "team",
    "editor",
    "editors",
    "writer",
    "de",
    "von",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


def as_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value if item)
    text = str(value).strip()
    return text or None


def title_matches(got: str, want: str) -> bool:
    a, b = _norm(got), _norm(want)
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return bool(short) and short in long_ and len(short) / len(long_) >= 0.6


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", _norm(text))
        if token not in _STOP and len(token) > 1
    }


def author_matches(got: str, want: str) -> bool:
    a, b = _tokens(got), _tokens(want)
    if not a or not b:
        return False
    shared = a & b
    return len(shared) / len(b) >= 0.5 and len(shared) / len(a) >= 0.25


# Two defaults that differ in every part, and whose day every month has: a
# part the text writes is the same under both, a part it does not write is
# not. Without a default, dateutil fills a missing part with today's, and
# "March 2021" matched 2021-03-24 on the 24th of a month and no other day.
_DEFAULTS = (datetime.datetime(2000, 1, 1), datetime.datetime(2001, 12, 28))
_PARTS = ("year", "month", "day")
# 10.12.2022: dots are day first in every language that writes dates with them.
_DOTTED = re.compile(r"^\D*\d{1,2}\.\d{1,2}\.\d{2,4}")


def _read_date(text: str) -> tuple[datetime.datetime, frozenset[str]]:
    """The date ``text`` writes, and which of its parts it writes."""
    dayfirst = bool(_DOTTED.match(text))
    first, second = (
        dates.parse(text, default=default, dayfirst=dayfirst) for default in _DEFAULTS
    )
    written = frozenset(
        part for part in _PARTS if getattr(first, part) == getattr(second, part)
    )
    return first, written


def date_matches(got: str, want: str) -> bool:
    """Whether the answer says the label's date, on any day this is run.

    The label decides what must be said: every part it writes -- year, month,
    day -- the answer must write too, and alike. When both carry a UTC offset,
    the answer is moved to the label's before its calendar date is read, since
    they then name the same instant; otherwise each date is read as written.
    """
    try:
        answer, said = _read_date(str(got))
        label, asked = _read_date(str(want))
        if not asked or not asked <= said:
            return False
        if answer.tzinfo is not None and label.tzinfo is not None:
            answer = answer.astimezone(label.tzinfo)
        return all(getattr(answer, part) == getattr(label, part) for part in asked)
    except (ValueError, OverflowError, TypeError):
        return False


MATCHERS: dict[str, Callable[[str, str], bool]] = {
    "title": title_matches,
    "author": author_matches,
    "date": date_matches,
}


def outcome(field: str, got: Any, want: Any) -> str:
    """One of ``OUTCOMES`` for one answer against one label."""
    answer, label = as_text(got), as_text(want)
    if label:
        if not answer:
            return "silent"
        return "hit" if MATCHERS[field](answer, label) else "wrong"
    return "invention" if answer else "correct_silence"


def outcomes(
    results: Iterable[dict[str, Any]], pages: dict[str, dict[str, Any]]
) -> dict[str, dict[str, str]]:
    """Every page's outcome per field, keyed by page id."""
    return {
        row["id"]: {
            field: outcome(field, row.get(field), pages[row["id"]][field])
            for field in FIELDS
        }
        for row in results
    }


def tally(
    per_page: dict[str, dict[str, str]],
    pages: dict[str, dict[str, Any]],
    types: frozenset[str] | None = None,
) -> dict[str, Counter[str]]:
    """Outcome counts per field, over every page or over ``types`` only."""
    counts: dict[str, Counter[str]] = {field: Counter() for field in FIELDS}
    for page_id, fields in per_page.items():
        if types is not None and pages[page_id]["page_type"] not in types:
            continue
        for field, result in fields.items():
            counts[field][result] += 1
    return counts


def hit_rate(counts: Counter[str]) -> float:
    """Hits over the pages that carry a label."""
    labelled = counts["hit"] + counts["wrong"] + counts["silent"]
    return counts["hit"] / labelled if labelled else 0.0


def right_when_answering(counts: Counter[str]) -> float:
    """Hits over every answer given, inventions included."""
    answered = counts["hit"] + counts["wrong"] + counts["invention"]
    return counts["hit"] / answered if answered else 0.0


# What a rate counts its trials over: a hit rate the labelled pages, a share
# right when answering the answers given.
TRIALS = {
    "hit": ("hit", "wrong", "silent"),
    "right": ("hit", "wrong", "invention"),
}


def rate(counts: Counter[str], measure: str) -> str:
    """A hit rate (``hit``) or a share right when answering (``right``), with
    its Wilson interval, as ``bench/stats.py`` prints it."""
    return stats.rate(counts["hit"], sum(counts[k] for k in TRIALS[measure]))


def columns(per_page: dict[str, str], ids: list[str], measure: str) -> list[list[int]]:
    """One field's hits and trials, page by page, in the order of ``ids``."""
    trials = TRIALS[measure]
    return [
        [int(per_page[page_id] == "hit") for page_id in ids],
        [int(per_page[page_id] in trials) for page_id in ids],
    ]


def paired(
    ours: dict[str, dict[str, str]],
    theirs: dict[str, dict[str, str]],
    field: str,
    measure: str,
) -> stats.Comparison:
    """Our rate on ``field`` minus theirs, over the pages both scored, paired
    page by page as ``bench/PREREG.md`` writes it."""
    ids = sorted(set(ours) & set(theirs))
    mine = {page_id: ours[page_id][field] for page_id in ids}
    other = {page_id: theirs[page_id][field] for page_id in ids}
    return stats.rate_difference(
        *columns(mine, ids, measure), *columns(other, ids, measure)
    )
