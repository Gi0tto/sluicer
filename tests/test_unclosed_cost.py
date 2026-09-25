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

    # 0.86 s here, 23 s before the fix: CI's runners are up to 2.5 times slower.
    assert _seconds(lambda: extract(page, visible=True)) < 8


def test_a_page_of_many_short_lines_is_read_for_its_bylines_in_a_moment():
    """Found by the second security review: the page's text nodes were chosen
    by an XPath predicate libxml2 evaluates in the square of the page's tail
    texts, 16,000 of them in 2.2 s, and extract(visible=True) ran it on
    sluicer serve's own threads."""
    from sluicer import extract

    page = (
        "<html><body><h1>t</h1>"
        + "<p><time>2020-01-01</time> Updated 1 Jan 2020 by Ann</p>" * 64_000
        + "</body></html>"
    )

    assert _seconds(lambda: extract(page, visible=True)) < 20


def test_a_page_of_deeply_nested_dates_is_read_in_a_moment():
    """Measured while checking the second security review's author item: a
    chain of <time> nested 2,000 deep, as deep as the parser nests, cost the
    square of its depth twice over. Each <time> walked every box round it,
    to learn whether it was hidden and whether it sat in a link, and its
    whole text was read, which holds every <time> inside it. 30 KB of such a
    chain took 1.3 s, and a page of 35 of them, 1 MiB, 46 s; 1.1 s now."""
    from sluicer import extract

    chain = "<time>x " * 2_000 + "</time>" * 2_000
    page = "<html><body><h1>t</h1>" + chain * 35 + "</body></html>"

    assert _seconds(lambda: extract(page, visible=True)) < 5


def test_a_time_that_holds_a_dozen_elements_is_a_container_not_a_date():
    """As an element named as a date's is: none of the 11,062 <time>
    elements on the 3,988 cached corpus pages holds more than seven."""
    from sluicer import read_visible

    def published(inside):
        page = (
            f"<html><body><h1>t</h1><time>{inside}1 January 2020</time></body></html>"
        )
        return read_visible(page).get("published")

    assert published("<b></b>" * 12).value == "2020-01-01"
    assert published("<b></b>" * 13) is None


def test_a_page_of_deeply_nested_by_lines_is_read_in_a_moment():
    """Measured with the dates above: each "By" line in a chain of boxes
    nested 2,000 deep read the whole text of the boxes round it to learn it
    was longer than a byline, and each holds every box inside it: 2 MiB of
    such chains took 10.4 s, and 1.1 s now."""
    from sluicer import extract

    chain = "<div>By Ann Lee " * 2_000 + "</div>" * 2_000
    page = "<html><body><h1>t</h1>" + chain * 48 + "</body></html>"

    assert _seconds(lambda: extract(page, visible=True)) < 5
