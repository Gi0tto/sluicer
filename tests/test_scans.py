"""What a page costs to read: the whole-document scans ``extract`` makes.

Speed is measured on the benchmark pages (``bench/golden.py time``, which
also proves every answer unchanged); what can be held here is the shape of
the work. libxml2 tests a predicate written on ``//*`` or ``//meta`` against
every element it walks, and finds the same elements, in the same order, three
times faster through the attribute axis, ``//@itemscope/..``.
"""

from __future__ import annotations

import re
from pathlib import Path

import lxml.html
import pytest

from sluicer import extract

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# A whole-document step that tests an attribute on each element it walks.
_PREDICATE_ON_EVERY_ELEMENT = re.compile(r"//(?:\*|[a-z]+)\[@")


@pytest.fixture
def scans(monkeypatch):
    asked: list[str] = []
    xpath = lxml.html.HtmlElement.xpath

    def recorded(self, path, *args, **kwargs):
        asked.append(path)
        return xpath(self, path, *args, **kwargs)

    monkeypatch.setattr(lxml.html.HtmlElement, "xpath", recorded, raising=False)
    return asked


@pytest.mark.parametrize(
    "page", ["product_all_three.html", "article_relative_links.html"]
)
def test_no_whole_document_scan_tests_an_attribute_on_every_element(scans, page):
    extract((FIXTURES / page).read_bytes(), url="https://shop.example/p")
    assert scans
    walked = [path for path in scans if _PREDICATE_ON_EVERY_ELEMENT.search(path)]
    assert walked == []


@pytest.mark.parametrize(
    "page", ["product_all_three.html", "article_relative_links.html"]
)
def test_the_page_is_asked_each_question_once(scans, page):
    """Five readers asked for the ``<meta>`` tags, two for the elements with
    a ``rel``, and the links and the summary both for the canonicals: each
    whole-document question is now asked once, and every reader filters the
    one answer."""
    extract((FIXTURES / page).read_bytes(), url="https://shop.example/p")
    whole = [path for path in scans if path.startswith(("//", "(//"))]
    assert len(whole) == len(set(whole)), whole
    assert len([path for path in whole if "meta" in path]) == 1, whole
    assert len([path for path in whole if "@rel" in path]) == 2, whole  # + head


def test_the_elements_carrying_an_attribute_are_found_in_linear_time():
    """``//@itemscope/..`` finds the same elements as ``//*[@itemscope]``,
    faster on a real page, but libxml2 merges each parent into the set
    against all it holds: 4.8 s for eighty thousand items. The parents are
    taken in Python instead."""
    import time

    from sluicer.document import carrying, load

    many = 80_000
    doc = load(
        "<html><body>"
        + "<div itemscope typeof=Thing id=a rel=next href=/n>x</div>" * many
        + "</body></html>"
    )
    for attribute in ("itemscope", "typeof", "id", "rel"):
        started = time.perf_counter()
        found = carrying(doc.tree, f"//@{attribute}")
        assert time.perf_counter() - started < 1, attribute
        assert found == doc.tree.xpath(f"//*[@{attribute}]")
