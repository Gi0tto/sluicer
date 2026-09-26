"""What the default ``extract`` costs grows with the page, and no faster.

Found by the hostile review of 0.10: the guesses read off the visible page are
on by default since 0.10, and they found the elements with a class or an id
by ``//*[@class or @id]``, which libxml2 evaluates in the square of their
number. A 10.8 MB page of 60,000 rows took 31.7 s where 0.9.1 took 0.48 s,
and ``sluicer serve`` answered 504 to 11 of 16 such calls. Measured while
fixing it: a page of 16,000 "By" lines naming one author was read in the
square of their number too, 2.1 s, since each line counted every line before
it again and wrote its own place in the page.

The work is in libxml2 as much as in Python, so it is timed, not counted: a
page twice the size may take at most ``_GROWTH`` times as long, each size the
fastest of three runs so a busy machine does not fail it.
"""

from __future__ import annotations

import time

from sluicer import extract

# A page twice the size may cost this many times as much. Linear work doubles;
# the quadratic scans took 5.8 and 3.7 times as long.
_GROWTH = 3.0


def _fastest(page: str) -> float:
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        extract(page, url="https://example.com/big")
        best = min(best, time.perf_counter() - started)
    return best


def _growth(make) -> float:
    return _fastest(make(2)) / _fastest(make(1))


def _rows(scale: int) -> str:
    """A catalogue: rows each with a class and an id, as review's page."""
    rows = "\n".join(
        f'<div class="item" id="i{i}"><h3><a href="/x/{i}">Item {i}</a></h3>'
        f'<p>Some text {i}.</p><span class="price">{i}.99</span></div>'
        for i in range(16_000 * scale)
    )
    return (
        f"<html><head><title>Big</title></head><body><h1>Big</h1>{rows}</body></html>"
    )


def _by_lines(scale: int) -> str:
    """A page of many "By" lines, every one naming the same author."""
    lines = "<div><p>By John Smith</p></div>" * (16_000 * scale)
    return f"<html><body><h1>Head</h1>{lines}</body></html>"


def test_the_default_extract_of_a_catalogue_grows_with_its_rows():
    assert _growth(_rows) < _GROWTH


def test_the_default_extract_of_many_by_lines_grows_with_them():
    assert _growth(_by_lines) < _GROWTH


def test_the_elements_named_by_a_class_or_an_id_are_the_xpaths():
    """The elements are found in Python, the same ones in the same order as
    ``//*[@class or @id]`` found them, an empty class or id included."""
    from sluicer.document import load
    from sluicer.visible import _AWAY, _Page

    doc = load(
        '<html><head><title id="t">x</title><meta class="m"></head><body class="">'
        '<!-- c --><div id=""><p class="a" id="b">x</p><script id="s"></script>'
        "</div><span>y</span><i class='A B'>z</i></body></html>"
    )
    expected = [e for e in doc.tree.xpath("//*[@class or @id]") if e.tag not in _AWAY]
    assert len(expected) == 5
    assert [e for e, _names in _Page(doc).named] == expected
    assert [names for _e, names in _Page(doc).named][-1] == "a b "
