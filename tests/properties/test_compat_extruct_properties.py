"""extruct's interface answers whatever it is handed, in proportion to it.

extruct raises on a page it cannot read, and with its default
``errors="strict"`` one broken block loses the whole page; its microdata
recurses once a level, and its reading of properties nested in properties
grows with the square of the page. ``sluicer.compat.extruct`` promises the
opposite of each: no page makes a syntax raise, and what a page yields is
bounded by its size, as sluicer's own readers are (see
``test_bounded_output``).

The bound, in the same terms. Each syntax that copies -- microdata and RDFa --
pays from a budget of ``B(n) = max(10_000, 10 n)`` for every element it walks
and every character it copies, and wraps what it paid for in at most twice as
much; JSON-LD returns what it parsed, at most ``2 n``; OpenGraph and Dublin
Core copy each tag's attributes once, beside an address of at most fifty
characters per tag. So the answer weighs at most ``4 B(n) + 12 n``.
Microformats are mf2py's, and are left out of the bound. Measured on these
strategies under the search profile, the largest answer is near 14 times the
page.
"""

from __future__ import annotations

import importlib.util

import pytest
from hypothesis import given, settings, strategies as st, target
from strategies import (
    SHAPES,
    a_callers_stack,
    broken_pages,
    encoded_pages,
    multiplying_pages,
    page_urls,
    pages,
    styles,
)
from test_bounded_output import budget, weight

from sluicer.compat import extruct

# Every syntax but mf2py's, which is slow and not sluicer's.
OURS = ["microdata", "opengraph", "json-ld", "rdfa", "dublincore"]


def answer(html: str | bytes, url: str | None, uniform: bool = False) -> object:
    with a_callers_stack():
        return extruct.extract(html, base_url=url, syntaxes=OURS, uniform=uniform)


any_text = st.text(
    alphabet=st.one_of(st.characters(), st.characters(categories=["Cs"]))
)


@given(any_text, page_urls, st.booleans())
def test_any_text_is_answered(html, url, uniform):
    answer(html, url, uniform)


@given(st.binary(), page_urls)
def test_any_bytes_are_answered(html, url):
    answer(html, url)


@given(pages(), styles(), st.booleans())
def test_a_drawn_page_is_answered(page, style, uniform):
    answer(page.html(style), page.url, uniform)


@given(st.one_of(broken_pages(), encoded_pages()))
def test_a_broken_page_or_one_in_any_encoding_is_answered(page):
    html, url = page
    answer(html, url)


@pytest.mark.skipif(
    importlib.util.find_spec("mf2py") is None, reason="needs sluicer[microformats]"
)
@settings(max_examples=max(1, settings.default.max_examples // 5))
@given(st.one_of(broken_pages(), encoded_pages()))
def test_microformats_answer_a_broken_page_too(page):
    html, url = page
    with a_callers_stack():
        extruct.extract(html, base_url=url, syntaxes=["microformat"], uniform=True)


def assert_bounded(page) -> None:
    html = page.html()
    n = len(html) + len(page.url or "")
    found = weight(answer(html, page.url))
    target(found / n, label="answer per character of page")
    assert found <= 4 * budget(n) + 12 * n, (found, n)


@pytest.mark.parametrize("shape", SHAPES)
@given(data=st.data())
def test_a_page_built_to_multiply_yields_in_proportion_to_its_size(shape, data):
    assert_bounded(data.draw(multiplying_pages(shape)))


@given(st.one_of(multiplying_pages(), pages()))
def test_what_any_page_yields_is_bounded_by_its_size(page):
    assert_bounded(page)
