"""What induction costs grows in step with the page.

``induce`` runs on pages nobody vouches for: the MCP server and the HTTP API
hand it whatever an agent points them at. A reader whose work grows with the
square of the page is a page that holds a worker for minutes, and one did:
ranking the groups compared every group with every other, and a 363 KB page of
two thousand small lists took 24 seconds.

The cost is counted, not timed. ``work`` is how many functions a call makes,
Python's and C's, as the interpreter's profiler sees them: the same page gives
the same count on any machine, however loaded. A page twice the size of another
should cost about twice as much, and a path that compares everything with
everything costs four times as much; a ratio of 2.5 lets through what grows as
``n log n`` and stops what grows as the square.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given, strategies as st
from strategies import Element, listings, render

from sluicer import extract

# A page twice the size may cost this many times as much, and no more.
_GROWTH = 2.5


def work(call: Callable[[], Any]) -> int:
    """How many functions ``call`` calls, counted by the profiler."""
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


def growth(build: Callable[[int], str], n: int) -> float:
    """What ``extract(..., induce=True)`` costs on ``build(2 n)`` over ``build(n)``."""
    small, large = build(n), build(2 * n)
    # Paid once for the first page of any size: modules imported, tables built.
    extract(small, induce=True)
    return work(lambda: extract(large, induce=True)) / work(
        lambda: extract(small, induce=True)
    )


def _boxes(n: int) -> str:
    """``n`` small lists side by side: the page that took 24 seconds."""
    return (
        "<html><body>"
        + "".join(
            "<div class='box'><ul>"
            + "".join(
                f"<li><a href='/{i}/{j}'>item {i} {j}</a> <b>{j}</b></li>"
                for j in range(3)
            )
            + "</ul></div>"
            for i in range(n)
        )
        + "</body></html>"
    )


def _table(n: int) -> str:
    """A table of ``n`` rows of ten cells: a group of rows, and a group per row."""
    rows = "".join(
        "<tr>" + "".join(f"<td>r{r}c{c}</td>" for c in range(10)) + "</tr>"
        for r in range(n)
    )
    return f"<html><body><table>{rows}</table></body></html>"


def _nested(n: int) -> str:
    """Listings ``n`` deep, each of three sections, the first holding the next."""
    leaf = "<div><div><div>x</div></div></div>"
    html = "x"
    for _ in range(n):
        html = (
            f"<section><div class=c><div><div>{html}</div></div></div>"
            f"<div class=c>{leaf}</div><div class=c>{leaf}</div></section>"
        )
    return "<html><body>" + html + "</body></html>"


def _deep_rows(n: int) -> str:
    """Three rows, each ``n`` deep with text at every level."""
    return "<html><body><ul>" + ("<li>" + "<b>x" * n + "</li>") * 3 + "</ul></body>"


def _wide_rows(n: int) -> str:
    """Three rows of ``n`` parts each, every part a slot of its own."""
    return (
        "<html><body><ul>"
        + ("<li>" + "".join(f"<span class='s{i % 7}'>v{i}</span>" for i in range(n)))
        * 3
        + "</ul></body></html>"
    )


PATHOLOGICAL = {
    "two thousand small lists": (_boxes, 500),
    "a table of a thousand rows": (_table, 500),
    "listings nested inside listings": (_nested, 150),
    "rows a thousand deep": (_deep_rows, 500),
    "rows a thousand parts wide": (_wide_rows, 1000),
}


@pytest.mark.parametrize(("build", "n"), PATHOLOGICAL.values(), ids=list(PATHOLOGICAL))
def test_a_page_twice_the_size_costs_about_twice_as_much(build, n):
    assert growth(build, n) < _GROWTH


@given(listing=listings(), copies=st.integers(20, 40))
def test_a_page_of_many_listings_costs_in_step_with_how_many(listing, copies):
    """Found by review: every group was checked against every other group.

    A drawn listing, copied ``copies`` times and twice as many times, side by
    side: each copy is a group of its own, and each copy should cost the same.
    """

    def build(k: int) -> str:
        return render(Element("html", [], [Element("body", [], [listing] * k)]))

    assert growth(build, copies) < _GROWTH
