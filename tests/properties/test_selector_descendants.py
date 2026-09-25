"""A CSS selector's descendant steps select what cssselect's own XPath selects.

cssselect writes ``div a`` as ``div/descendant-or-self::*/a``, which libxml2
evaluates in the square of a page's nesting, and ``sluicer.selectors`` reads
it as ``div/descendant::a``. The two are the same elements in the same order
only while the step after them asks what an element is, never where it
stands among the step's elements, so the property draws the selectors whose
predicates cssselect writes -- every pseudo-class that counts siblings,
``:has``, ``:is``, ``:not``, ``:lang``, attribute tests with brackets in their
strings, and every combinator -- and the trees they are asked of, and holds
the two to the same answer, from the page and from each element of it, as a
field is read inside a row.

Nothing here decides what to draw from the code under test.
"""

from __future__ import annotations

import cssselect
from hypothesis import given, strategies as st
from lxml import html

from sluicer.selectors import HAS_READ, selector

TAGS = ["div", "a", "p", "span", "li", "ul", "b"]
CLASSES = ["x", "y"]

_translator = cssselect.HTMLTranslator()


@st.composite
def trees(draw, depth: int = 0) -> str:
    """An element and what it holds, as HTML."""
    tag = draw(st.sampled_from(TAGS))
    attributes = ""
    if draw(st.booleans()):
        attributes += f' class="{" ".join(draw(st.sets(st.sampled_from(CLASSES))))}"'
    if draw(st.integers(0, 4)) == 0:
        attributes += f' lang="{draw(st.sampled_from(["en", "en-GB", "fr"]))}"'
    if draw(st.integers(0, 3)) == 0:
        attributes += ' href="/x" title="x]y"'
    children = draw(st.lists(trees(depth + 1), max_size=4)) if depth < 5 else []
    text = draw(st.sampled_from(["", "t"]))
    return f"<{tag}{attributes}>{text}{''.join(children)}</{tag}>"


PSEUDO = [
    "",
    ":first-child",
    ":last-child",
    ":only-child",
    ":nth-child(2)",
    ":nth-child(2n+1)",
    ":nth-child(-n+2)",
    ":nth-last-child(2)",
    ":nth-of-type(2)",
    ":first-of-type",
    ":last-of-type",
    ":only-of-type",
    ":nth-last-of-type(1)",
    ":empty",
    ":not(.x)",
    ":not(:first-child)",
    ":has(b)",
    ":has(> a)",
    ":is(a, p)",
    ":where(.y)",
    ":lang(en)",
    ":hover",
    ":link",
    ":root",
    "[href]",
    '[title="x]y"]',
    "[class~=y]",
    '[title^="x]"]',
]
# cssselect before 1.5 translates :has() wrongly, and Sluicer refuses it
# there (HAS_READ): the floors job runs 1.2, Pyodide ships 1.4.
if not HAS_READ:
    PSEUDO = [one for one in PSEUDO if ":has" not in one]


@st.composite
def compounds(draw) -> str:
    tag = draw(st.sampled_from([*TAGS, "*", ""]))
    cls = draw(st.sampled_from(["", ".x", ".y"]))
    pseudo = draw(st.sampled_from(PSEUDO))
    compound = tag + cls + pseudo
    return compound or "*"


@st.composite
def css(draw) -> str:
    """A selector of one to four compounds joined by any combinator, or a
    group of two."""
    parts = [draw(compounds())]
    for _ in range(draw(st.integers(0, 3))):
        parts.append(draw(st.sampled_from([" ", " > ", " + ", " ~ ", " "])))
        parts.append(draw(compounds()))
    one = "".join(parts)
    return one + (
        f", {draw(compounds())} {draw(compounds())}" if draw(st.booleans()) else ""
    )


@given(
    page=st.lists(trees(), min_size=1, max_size=4),
    written=st.lists(css(), min_size=10, max_size=10),
)
def test_descendant_steps_select_what_cssselect_s_own_xpath_selects(page, written):
    tree = html.fromstring(f"<html><body>{''.join(page)}</body></html>")
    contexts = [tree, *tree.iter()]
    for text in written:
        try:
            theirs = _translator.css_to_xpath(text)
        except cssselect.ExpressionError:
            # What cssselect does not translate -- *:nth-of-type() -- is
            # refused by both, and asks nothing of the rewriting.
            continue
        ours = selector(text).xpath
        for context in contexts:
            assert context.xpath(ours) == context.xpath(theirs), (text, ours)
