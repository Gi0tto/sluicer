"""A tag a page opens and never closes costs what the page costs, once.

Three patterns asked, at every place a tag opened, for the first place it
closed: ``<script>`` or ``<style>`` and its end tag, ``<title>`` and its end
tag, ``<!--`` and ``-->``. Where the page never closed it, each asked the rest
of the page, from every place it opened: a page of a hundred thousand
unclosed ``<script>`` tags took a minute to be judged a challenge or not, after
its fetch and outside every fetch deadline, and 64 KiB of ``<!--`` took four
seconds to be sniffed for its encoding. The rules are the same; the patterns
are kept here as the oracle the scans must agree with.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from hypothesis import given, settings, strategies as st

from sluicer.document import sniff_encoding
from sluicer.fetch import rules

_TAGS = re.compile(r"(?s)<(script|style).*?</\1>|<[^>]+>")
_TITLE = re.compile(r"(?is)<title\b[^>]*>(.*?)</title>")
_COMMENT = re.compile(rb"<!--.*?-->", re.DOTALL)

# Pieces that make the patterns' edges meet: tags closed and not, a lone "<",
# an empty "<>", "<scriptx", the case of TITLE, U+0130, which IGNORECASE reads
# as an "i", and comment marks.
_PIECES = st.sampled_from(
    [
        "<",
        ">",
        "<>",
        "/",
        "<script>",
        "</script>",
        "<scriptx>",
        "<style>",
        "</style>",
        "<title>",
        "</title>",
        "<TITLE a=1>",
        "</Title>",
        "<tİtle>",
        "<titlex>",
        "<title",
        "x",
        " ",
        "\n",
        "<!--",
        "-->",
        "--",
        "<b>",
        "é",
    ]
)
_PAGES = st.lists(_PIECES, max_size=40).map("".join)


@settings(max_examples=2000)
@given(_PAGES)
def test_the_scan_strips_what_the_pattern_stripped(page):
    assert rules.strip_tags(page) == _TAGS.sub(" ", page)


@settings(max_examples=2000)
@given(_PAGES)
def test_the_scan_finds_the_title_the_pattern_found(page):
    found = _TITLE.search(page)
    assert rules.page_title(page) == (found.group(1) if found else None)


@settings(max_examples=2000)
@given(_PAGES)
def test_the_scan_drops_the_comments_the_pattern_dropped(page):
    data = page.encode("utf-8")
    from sluicer.document import _without_comments

    assert _without_comments(data) == _COMMENT.sub(b"", data)


def _seconds(call: Callable[[], Any]) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


def test_a_page_of_unclosed_scripts_is_judged_in_a_moment():
    page = "<html><body>" + "<script>" * 40_000 + "</body></html>"

    assert _seconds(lambda: rules.why_climb(200, page, False)) < 1
    assert _seconds(lambda: rules.challenge_marker(page, False)) < 1


def test_a_page_of_unclosed_titles_is_judged_in_a_moment():
    page = "<title>" * 40_000

    assert _seconds(lambda: rules.challenge_marker(page, False)) < 1


def test_a_page_of_unclosed_brackets_is_judged_in_a_moment():
    page = "<" * 400_000

    assert _seconds(lambda: rules.challenge_marker(page, False)) < 1


def test_a_head_of_unclosed_comments_is_sniffed_in_a_moment():
    assert _seconds(lambda: sniff_encoding(b"<!--" * 16_384)) < 0.5


def test_a_page_of_many_bylines_and_dates_is_read_in_a_moment():
    """Found by review: each "By" line and each date asked its enclosing box's
    whole text, and a box holding them all cost the square of the box. 8,000
    of them in one article, 583 KB, took 22 s with visible=True."""
    from sluicer import extract

    page = (
        "<html><body><article>"
        + "".join(
            f"<p class=byline>By Ann Lee {i}</p><time datetime=2025-01-0{1 + i % 9}>"
            f"x{i}</time>"
            for i in range(8_000)
        )
        + "</article></body></html>"
    )

    assert _seconds(lambda: extract(page, visible=True)) < 2
