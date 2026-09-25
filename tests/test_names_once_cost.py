"""Keeping each name once costs what the names cost, not their square.

Four readers kept a list of what they had found and asked, for each new
name, whether the list held it already: every name compared with every one
before it. The names come from the page -- its canonicals, its authors, an
RDFa attribute, its robots.txt -- and a page of forty
thousand of them held a reader for seconds; the sixteen mebibytes a fetch
allows would hold it for minutes. The comparisons happen inside one C call,
which the profiler counts as one, so these are bounded by the clock, with
margins of fifty or more.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sluicer.document import load

_MANY = 40_000


def _seconds(call: Callable[[], Any]) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


def test_forty_thousand_canonicals_are_read_in_a_moment():
    from sluicer.declared.links import canonicals

    doc = load(
        "<html><head>"
        + "".join(
            f"<link rel=canonical href='https://e.example/{i}'>" for i in range(_MANY)
        )
        + "</head></html>"
    )

    assert _seconds(lambda: canonicals(doc)) < 1
    assert len(canonicals(doc)) == _MANY


def test_forty_thousand_authors_are_named_in_a_moment():
    from sluicer.summary import _names

    authors = [{"@type": "Person", "name": f"Name {i}"} for i in range(_MANY)]

    assert _seconds(lambda: _names(authors)) < 1
    assert _names([*authors[:2], authors[0]]) == "Name 0, Name 1"


def test_forty_thousand_rdfa_terms_are_resolved_in_a_moment():
    from sluicer.declared.rdfa import _names

    doc = load(
        "<div vocab='http://schema.org/'><span property='"
        + " ".join(f"p{i}" for i in range(_MANY))
        + " p0'>x</span></div>"
    )
    (span,) = doc.tree.xpath("//span")
    declared = span.get("property")

    assert _seconds(lambda: _names(span, declared)) < 1
    assert len(_names(span, declared)) == _MANY


def test_forty_thousand_user_agent_lines_are_read_in_a_moment():
    from sluicer.audit.crawlers import user_agents

    text = "\n".join(f"User-agent: bot{i}\nDisallow: /" for i in range(_MANY))

    assert _seconds(lambda: user_agents(text)) < 1
    assert user_agents("User-agent: A\nUser-agent: a\nUser-agent: b") == ["a", "b"]


def test_forty_thousand_oembed_links_are_read_in_a_moment():
    """Found by review, the fifth of these: oEmbed addresses were kept once
    each by asking the list, 4.4 s for forty thousand."""
    from sluicer.declared.links import read_links

    doc = load(
        "<html><head>"
        + "".join(
            f"<link rel=alternate type=application/json+oembed href='/o/{i}'>"
            for i in range(_MANY)
        )
        + "<link rel=alternate type=application/json+oembed href='/o/0'>"
        + "</head></html>"
    )

    # 0.16 s here, 3.9 s before the fix.
    assert _seconds(lambda: read_links(doc)) < 2
    assert read_links(doc)["oembed"][:2] == ["/o/0", "/o/1"]
