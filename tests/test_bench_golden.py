"""The golden-output harness notices any change in what a page gives.

``bench/golden.py`` is what proves a speed change kept every answer
byte-identical on the cached corpus. These hold it to noticing: the same page
read twice gives the same digests, and a page that says one thing
differently changes the digests of every reading that shows it. The harness
is not in the sdist: without it, this skips.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "golden.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
sys.path.insert(0, str(BENCH))

import golden  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _page(name: str, body: bytes) -> golden.Page:
    return golden.Page(name, body, "https://shop.example/p", "text/html; charset=utf-8")


def test_a_page_read_twice_gives_the_same_digests():
    body = (FIXTURES / "product_jsonld.html").read_bytes()
    first = golden.read_page(_page("p", body), markdown=False)
    assert first == golden.read_page(_page("p", body), markdown=False)
    assert set(first) == {
        "extract",
        "found",
        "extract+headers",
        "visible",
        "induce",
        "fetch",
    }
    assert first["found"] == "True"


def test_a_page_that_says_one_thing_differently_changes_its_digests():
    body = (FIXTURES / "product_jsonld.html").read_bytes()
    declared = b'"name":"Brake pad set"'
    assert declared in body
    before = {"p": golden.read_page(_page("p", body), markdown=False)}
    changed = body.replace(declared, b'"name":"Brake pads"')
    after = {"p": golden.read_page(_page("p", changed), markdown=False)}
    for reading in ("extract", "extract+headers", "visible", "induce", "fetch"):
        assert before["p"][reading] != after["p"][reading], reading
    assert golden._compare(before, before) == 0
    assert golden._compare(before, after) == 1


def test_a_warc_of_the_pages_is_read_and_each_page_extracted():
    pages = [
        _page(path.name, path.read_bytes())
        for path in sorted((FIXTURES / "books_product").glob("*.html"))
    ]
    found = golden.read_warcs(pages)
    assert {f"warc/{n}" for n in range(len(pages))} < set(found)
    assert found == golden.read_warcs(pages)


def test_an_extractor_is_learnt_replayed_and_healed():
    pages = [
        (path.read_bytes(), f"https://books.example/{path.name}")
        for path in sorted((FIXTURES / "books_product").glob("*.html"))
    ]
    found = golden.compile_one(("books", pages[:2], pages[2:], None))
    assert set(found) == {"compile", "run/0", "run/1", "heal"}
    assert not any(value.startswith("raised:") for value in found.values())
