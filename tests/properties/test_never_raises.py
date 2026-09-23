"""Whatever it is handed, ``extract`` answers, and so does ``induce``.

Its docstring promises exactly one exception, ``MicroformatsExtraMissing``,
and "nothing else: any input, however broken, is read or reported empty". An
agent can point the MCP server at any page, so that promise is what stands
between a hostile page and a traceback in someone else's pipeline.

Each page is read with the stack a caller has, not the one Hypothesis lends a
test (see ``a_callers_stack``): the first run of these properties under
Hypothesis's own could not have found the ``RecursionError`` it was there for.
"""

from __future__ import annotations

import importlib.util

import pytest
from hypothesis import given, settings, strategies as st
from strategies import (
    a_callers_stack,
    broken_pages,
    encoded_pages,
    page_urls,
    pages,
    styles,
)

from sluicer import extract, induce as induce_records
from sluicer.document import load


def read(html: str | bytes, url: str | None = None, induce: bool = False) -> None:
    """``extract`` the page with the stack a caller has, and then ``induce`` it.

    ``extract`` induces only on a page that declares nothing about its things,
    and ``induce`` is public: asked of any page, it answers too.
    """
    with a_callers_stack():
        extract(html, url=url, induce=induce)
        induce_records(load(html, url=url))


# A str may hold what no encoding can: lone surrogates, NUL, every control.
any_text = st.text(
    alphabet=st.one_of(st.characters(), st.characters(categories=["Cs"]))
)


@given(any_text, page_urls, st.booleans())
def test_any_text_is_read_or_reported_empty(html, url, induce):
    read(html, url=url, induce=induce)


@given(st.binary(), page_urls, st.booleans())
def test_any_bytes_are_read_or_reported_empty(html, url, induce):
    read(html, url=url, induce=induce)


@given(pages(), styles(), st.booleans())
def test_a_drawn_page_is_read(page, style, induce):
    read(page.html(style), url=page.url, induce=induce)


@given(broken_pages(), st.booleans())
def test_a_broken_page_is_read(page, induce):
    html, url = page
    read(html, url=url, induce=induce)


@given(encoded_pages(), st.booleans())
def test_a_page_in_any_encoding_declared_any_way_is_read(page, induce):
    html, url = page
    read(html, url=url, induce=induce)


@pytest.mark.skipif(
    importlib.util.find_spec("mf2py") is None, reason="needs sluicer[microformats]"
)
# mf2py is slow, and the extra is not in CI's default environment; a fifth of
# what the profile asks for is enough to know the reader is wired in safely.
@settings(max_examples=max(1, settings.default.max_examples // 5))
@given(st.one_of(broken_pages(), encoded_pages()))
def test_microformats_read_a_broken_page_too(page):
    html, url = page
    with a_callers_stack():
        extract(html, url=url, microformats=True)
