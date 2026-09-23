"""What a page yields is bounded by the size of the page.

A reader that follows references or copies a value into several places can
turn a small page into a large answer, and the answer is what the MCP server
serialises and hands to an agent. Two such bugs were found by review --
microdata ``itemref`` expanded exponentially, JSON-LD references quadratically
-- and were fixed with budgets. The first run of these properties found a
dozen shapes those budgets did not see, in four readers, each growing with the
square of the page: a reference to one long string, an element named by many
items or naming many properties, properties nested in properties, a long base
or vocabulary written into every address or name, a row nested a thousand
deep. Each reader now pays for what it copies from one budget for the page.

The bound is stated in the budgets' own terms. ``weight`` is one for every
value in the answer and one for every character of its text and of its keys:
the size of its JSON without the punctuation and the escaping, which would
otherwise let a page of control characters look six times larger than it is
without anything having been copied. ``n`` is the length of the page, and of
the address it was given with.

Each reader that copies pays from a budget of ``B(n) = max(10_000, 10 n)``:

* JSON-LD pays one per value and one per character for every copy a
  reference makes, and what it parsed weighs at most ``2 n`` (a one-digit
  number is one value and one character), so it returns at most
  ``2 n + 2 B(n)``;
* microdata pays for every element it walks and every character of a value, a
  name or a type, and wraps what it paid for in at most one key and two
  values more, so at most ``n + 2 B(n)``;
* RDFa pays for characters only, and wraps them in at most three times as
  much, so at most ``n + 3 B(n)``;
* induction pays for every name and value a record holds, at most ``2 B(n)``.

The four readers of the document's own metadata copy each tag's content once,
at most ``2 n``. And ``extract`` does not multiply what they return: merge
carries each value once, in a field and a record that add a few keys each --
five times the smallest record a page can declare, ten characters of JSON-LD --
and the summary is sixteen answers, each one value of one field or one tag of
the page. Each field, record and answer also says where it was declared: one
key more, ``where``, which puts a field at six times the smallest a page can
declare where it was five, and a place, and every place is paid for from
``max(10_000, 2 n)`` for the records and ``max(10_000, n)`` for the summary.
So the whole answer weighs at most ``10 R + 15 n + 30_000``, where ``R`` is
what the readers returned.

Measured on these strategies, the largest ratios are near 10 for a reader and
near 22 for the whole answer. Each of the bugs these properties caught was
between 89 and 1,600 times the page, and growing.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from hypothesis import given, strategies as st, target
from strategies import SHAPES, a_callers_stack, multiplying_pages, pages

from sluicer import extract
from sluicer.declared.dublincore import read_dublincore
from sluicer.declared.htmlmeta import read_htmlmeta
from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.microdata import read_microdata
from sluicer.declared.opengraph import read_opengraph
from sluicer.declared.rdfa import read_rdfa
from sluicer.declared.twitter import read_twitter
from sluicer.document import load
from sluicer.structure import induce


def weight(value: Any) -> int:
    """One for every value, one for every character of every string and key."""
    count = 0
    pending = [value]
    while pending:
        item = pending.pop()
        count += 1
        if isinstance(item, str):
            count += len(item)
        elif isinstance(item, dict):
            for key, inner in item.items():
                count += len(key)
                pending.append(inner)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return count


def budget(n: int) -> int:
    """What a copying reader may spend on a page of ``n`` characters."""
    return max(10_000, 10 * n)


READERS = {
    "jsonld": read_jsonld,
    "microdata": read_microdata,
    "rdfa": read_rdfa,
    "dublincore": read_dublincore,
    "opengraph": read_opengraph,
    "twitter": read_twitter,
    "html": read_htmlmeta,
}

BOUNDS = {
    "jsonld": lambda n: 2 * n + 2 * budget(n),
    "microdata": lambda n: n + 2 * budget(n),
    "rdfa": lambda n: n + 3 * budget(n),
    "induced": lambda n: 2 * budget(n),
    "dublincore": lambda n: 2 * n,
    "opengraph": lambda n: 2 * n,
    "twitter": lambda n: 2 * n,
    "html": lambda n: 2 * n,
}


def assert_bounded(page) -> None:
    """Every reader, and ``extract``, within its bound on ``page``.

    Run with the stack a caller has, so that a walk that recurses too deep is
    an error here rather than room Hypothesis lends it.
    """
    with a_callers_stack():
        _assert_bounded(page)


def _assert_bounded(page) -> None:
    html = page.html()
    n = len(html) + len(page.url or "")
    doc = load(html, url=page.url)

    returned = {name: weight(read(doc)) for name, read in READERS.items()}
    returned["induced"] = weight(
        [{name: f.value for name, f in r.fields.items()} for r in induce(doc)]
    )
    for name, found in returned.items():
        # Guides the search towards the pages that multiply most.
        target(found / n, label=f"{name} per character of page")
        assert found <= BOUNDS[name](n), (name, found, n)

    answer = weight(asdict(extract(html, url=page.url, induce=True)))
    readers = sum(returned.values())
    target(answer / n, label="answer per character of page")
    assert answer <= 10 * readers + 15 * n + 30_000, (answer, readers, n)


@pytest.mark.parametrize("shape", SHAPES)
@given(data=st.data())
def test_a_page_built_to_multiply_yields_in_proportion_to_its_size(shape, data):
    assert_bounded(data.draw(multiplying_pages(shape)))


@given(st.one_of(multiplying_pages(), pages()))
def test_what_any_page_yields_is_bounded_by_its_size(page):
    assert_bounded(page)
