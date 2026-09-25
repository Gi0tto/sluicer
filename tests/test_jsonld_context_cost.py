"""What naming a JSON-LD block's words through its contexts costs grows with the page.

Found by review: every node of a ``@graph`` was handed a context list of its
own, so the table that names words was read again for each node, and every
read copied the table of the contexts around it. A block of three thousand
terms and three thousand nodes, 216 KB, took five seconds where 0.7.1 took
seven hundredths, and six thousand of each took twenty-four; nested values
each declaring an empty context of their own kept a copy of the whole table
apiece, and a 517 KB page held 1.76 GB.

The work is counted as ``tests/properties/test_linear_cost.py`` counts it:
functions called, which is the same on any machine. A copy is one call
whatever it copies, so the copies are bounded by the clock, with a wide
margin, as in that file.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from functools import partial
from typing import Any

import pytest

from sluicer import extract
from sluicer.audit import audit

# A page twice the size may cost this many times as much, and no more.
_GROWTH = 2.5


def _work(call: Callable[[], Any]) -> int:
    count = 0

    def tick(frame: Any, event: str, arg: Any) -> None:
        nonlocal count
        if event in ("call", "c_call"):
            count += 1

    before = sys.getprofile()
    sys.setprofile(tick)
    try:
        call()
    finally:
        sys.setprofile(before)
    return count


def _page(block: dict[str, Any]) -> str:
    script = f'<script type="application/ld+json">{json.dumps(block)}</script>'
    return f"<html><head>{script}</head></html>"


def _terms(n: int) -> dict[str, str]:
    return {f"t{i}": f"http://ex.example/v{i}" for i in range(n)}


def _graph(n: int) -> str:
    """``n`` terms, and ``n`` nodes in the graph they cover."""
    return _page(
        {
            "@context": _terms(n),
            "@graph": [{"@type": "Thing", "name": f"n{i}"} for i in range(n)],
        }
    )


def _graph_in_a_graph(n: int) -> str:
    """The same one graph further in, under a context of its own."""
    inner = {
        "@context": {"q": "http://q.example/"},
        "@graph": [{"@type": "Thing", "name": f"n{i}"} for i in range(n)],
    }
    return _page({"@context": _terms(n), "@graph": [inner]})


def _nodes_with_contexts(n: int) -> str:
    """``n`` nodes each naming schema.org's context, and ``n`` terms around them."""
    return _page(
        {
            "@context": _terms(n),
            "@graph": [
                {"@context": "https://schema.org", "@type": "Thing", "name": f"n{i}"}
                for i in range(n)
            ],
        }
    )


def _nodes_with_terms(n: int) -> str:
    """``n`` nodes each defining a term of their own."""
    return _page(
        {
            "@context": _terms(n),
            "@graph": [
                {"@context": {f"q{i}": "http://q.example/"}, "@type": "Thing", "n": i}
                for i in range(n)
            ],
        }
    )


def _values_with_contexts(n: int) -> str:
    """One node of ``n`` values, each declaring an empty context of its own."""
    return _page(
        {
            "@context": _terms(n),
            "@type": "Thing",
            "x": [{"@context": {}, "n": i} for i in range(n)],
        }
    )


PAGES = {
    "a graph under a context of many terms": _graph,
    "a graph inside a graph": _graph_in_a_graph,
    "nodes naming a context of their own": _nodes_with_contexts,
    "nodes defining terms of their own": _nodes_with_terms,
    "values declaring contexts of their own": _values_with_contexts,
}


def _growth(call: Callable[[str], Any], build: Callable[[int], str], n: int) -> float:
    small, large = build(n), build(2 * n)
    # Paid once for the first page of any size: modules imported, tables built.
    call(small)
    return _work(lambda: call(large)) / _work(lambda: call(small))


@pytest.mark.parametrize("build", PAGES.values(), ids=list(PAGES))
def test_a_block_twice_the_size_costs_about_twice_as_much_to_extract(build):
    assert _growth(extract, build, 300) < _GROWTH


@pytest.mark.parametrize("build", PAGES.values(), ids=list(PAGES))
def test_a_block_twice_the_size_costs_about_twice_as_much_to_audit(build):
    assert _growth(audit, build, 300) < _GROWTH


def _seconds(call: Callable[[], Any]) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


@pytest.mark.parametrize("build", PAGES.values(), ids=list(PAGES))
def test_six_thousand_terms_and_six_thousand_nodes_are_named_in_a_moment(build):
    """Six thousand of each took twenty-four seconds; a tenth of a second
    now, on the machine that measured both."""
    page = build(6_000)

    assert _seconds(lambda: extract(page)) < 10
    assert _seconds(lambda: audit(page)) < 10


def test_values_each_declaring_a_context_hold_no_copy_of_the_terms_around_them():
    """Each empty context below two thousand terms kept a copy of them all:
    two thousand copies. The page's own size, give or take, now."""
    import tracemalloc

    page = _values_with_contexts(2_000)
    extract(page)
    tracemalloc.start()
    try:
        extract(page)
        audit(page)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert peak < 40_000_000


def _listed_contexts(n: int) -> str:
    """One node under a list of ``n`` contexts, and ``n`` words written under them."""
    return _page(
        {
            "@context": [{f"p{i}": f"http://p{i}.example/"} for i in range(n)],
            "@type": "Thing",
            **{f"p{i % 40}:w{i}": "v" for i in range(n)},
        }
    )


def _nested_graphs(n: int) -> str:
    """``n`` graphs one inside the next, each with a context, and ``n`` nodes
    in the innermost, each with a context of its own."""
    block: dict[str, Any] = {
        "@graph": [
            {"@context": {"q": "http://q.example/"}, "@type": "Thing", "q:n": i}
            for i in range(n)
        ]
    }
    for i in range(min(n, 400)):
        block = {"@context": {f"g{i}": "http://g.example/"}, "@graph": [block]}
    return _page(block)


def test_a_word_under_thousands_of_contexts_is_named_in_a_moment():
    """A word is looked up context by context, and only the first
    ``_MAX_CONTEXTS`` are read: twenty thousand listed, or four hundred
    graphs nested, would otherwise make every word as many lookups. The
    nested graphs took six seconds, a tenth of it now, most of that placing
    each node four hundred graphs deep, as 0.7.1 did."""
    for page in (_listed_contexts(20_000), _nested_graphs(5_000)):
        assert _seconds(partial(extract, page)) < 10
        assert _seconds(partial(audit, page)) < 10


def test_a_context_past_the_most_that_are_read_is_not_read():
    from sluicer.declared.jsonld import _MAX_CONTEXTS

    contexts: list[Any] = [
        {f"p{i}": f"http://p{i}.example/"} for i in range(_MAX_CONTEXTS + 2)
    ]
    first, last = "p0:x", f"p{_MAX_CONTEXTS}:x"
    record = extract(
        _page({"@context": contexts, "@type": "Thing", first: "a", last: "b"})
    ).records[0]
    # Not named through the contexts that were read: one past them may
    # define p0 again, as a word no context names is left as written.
    assert list(record.fields) == [first, last]

    # A null clears them all, and what follows it is read.
    contexts += [None, {"z": "http://z.example/"}]
    record = extract(
        _page({"@context": contexts, "@type": "Thing", first: "a", "z:x": "c"})
    ).records[0]
    assert list(record.fields) == [first, "http://z.example/x"]


def test_a_null_past_the_most_that_are_read_still_clears_them_all():
    """Found by the second review: 33 graphs nested, each with a context, the
    outermost naming FOAF's ``name``, around a graph whose context is
    ``[null, "https://schema.org"]``. Only the outermost 32 were carried, the
    null among those dropped, and the Product's ``name`` was FOAF's: the
    page lost its title."""
    node: dict[str, Any] = {
        "@context": [None, "https://schema.org"],
        "@graph": [{"@type": "Product", "name": "Brake pad"}],
    }
    for i in range(33):
        context = (
            {"name": "http://xmlns.com/foaf/0.1/name"}
            if i == 32
            else {f"t{i}": f"http://ex.example/{i}/"}
        )
        node = {"@context": context, "@graph": [node]}

    read = extract(_page(node))

    assert [list(r.fields) for r in read.records] == [["name"]]
    assert read.summary["title"].value == "Brake pad"


def test_words_under_graphs_past_the_most_that_are_read_are_left_as_written():
    from sluicer.declared.jsonld import _MAX_CONTEXTS

    node: dict[str, Any] = {"@type": "Thing", "p0:x": "a"}
    for i in reversed(range(_MAX_CONTEXTS + 8)):
        node = {"@context": {f"p{i}": f"http://p{i}.example/"}, "@graph": [node]}

    assert list(extract(_page(node)).records[0].fields) == ["p0:x"]


def test_a_context_named_elsewhere_counts_toward_the_most_that_are_read():
    # Each is one of the contexts carried beside a graph's nodes, as a
    # context read is, so the two limits count the same contexts.
    from sluicer.declared.jsonld import _MAX_CONTEXTS

    contexts: list[Any] = [
        *(f"https://ctx.example/{i}" for i in range(_MAX_CONTEXTS)),
        {"p": "http://p.example/"},
    ]
    record = extract(
        _page({"@context": contexts, "@type": "Thing", "p:x": "a"})
    ).records[0]
    assert list(record.fields) == ["p:x"]
