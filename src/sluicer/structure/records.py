"""Turning one repeated shape into the records it describes.

A page that declares nothing has not told us what its fields are called, so we
do not invent names for them. A field is named by where it sits in the shape and
what class it carries, which is exactly as much as the page said, and every one
of them is marked as induced so a caller never mistakes it for a declaration.

**The names come from the group, not from each member.** A record is a row only
if the same slot has the same name in every record; a name derived from a
member's own document order drifts the moment one member holds an element the
others do not, and members that differ below the depth shapes are compared at --
an optional ``<em>``, a second badge -- are routine. So a slot is named by the
path down to it: the tag and first hand-written class of each ancestor inside the
member, then its own, as ``div.meta>span.sku``. Two members that differ deep
inside one branch still agree about every other branch, and a slot a member does
not have is simply absent from that record rather than pushing its neighbours'
names along.

**Nothing repeated is dropped.** Three ``<span class="tag">`` in one card are
three facts. Naming them all ``span.tag`` and keeping the first would silently
lose two, so repeated siblings are numbered -- ``span.tag1``, ``span.tag2``,
``span.tag3`` -- and the decision to number is taken once for the whole group,
from the member that holds the most. A card with one tag in a group where some
card holds three therefore calls its tag ``span.tag1``, and the columns still
line up. Numbering rather than collecting keeps ``Record.fields`` a flat map of
one name to one value, which is what a declared record is; a list-valued field
would be a second kind of record for a caller to handle.

Some parts carry two facts rather than one, and both are kept. An anchor is the
clearest case: ``<a href="/p0">Product name 0</a>`` is a name *and* a link, and
returning only the address loses the product's name on the commonest listing
shape on the web. An image is the same, with its alt text and its src. The
convention is that the text takes the slot's own name and the address takes that
name with the attribute appended -- ``a.more`` and ``a.more@href``, ``img.photo``
and ``img.photo@src`` -- so the two are visibly one slot, and a caller reading a
record never has to guess which name belongs to which.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from itertools import pairwise

from lxml.html import HtmlElement

from sluicer.declared.merge import Field, Record

# The prefixes CSS-in-JS tools put before a hash: emotion, styled-components,
# styled-jsx, the Guardian's DCR, Svelte and Astro.
_TOOLING_PREFIXES = ("css-", "sc-", "jsx-", "dcr-", "svelte-", "astro-", "emotion-")
_CSS_MODULE = re.compile(r"(.+?)__([A-Za-z0-9_-]{5,})")
_INTERLEAVED = re.compile(r"[a-z]\d[a-z]|\d[a-z]\d", re.IGNORECASE)

# Which attribute carries the address, per tag. Named without an underscore
# because the ranking in ``groups`` asks the same question -- an element that
# points somewhere carries something, whether or not it also carries text --
# and one table is the only way the two can never disagree.
ADDRESS = {"a": "href", "img": "src", "link": "href", "source": "src"}

# The text of an image is the text its author wrote for the people who cannot
# see it. Every other element's text is the text inside it.
_TEXT_ATTRIBUTE = {"img": "alt"}

# One step of the path to a slot: the tag, the first hand-written class, and
# which of the same-named siblings this is.
_Step = tuple[str, str, int]
_Path = tuple[_Step, ...]


def address_of(element: HtmlElement) -> str | None:
    """Return the address ``element`` points at, or None when it points nowhere."""
    if not isinstance(element.tag, str):
        return None
    attribute = ADDRESS.get(element.tag)
    if not attribute:
        return None
    value = element.get(attribute)
    return value.strip() if value else None


def _text(element: HtmlElement) -> str:
    attribute = _TEXT_ATTRIBUTE.get(str(element.tag))
    if attribute:
        return " ".join((element.get(attribute) or "").split())
    return " ".join((element.text_content() or "").split())


def _says_something(text: str | None) -> bool:
    """True when ``text`` holds more than whitespace and separators.

    A letter, a digit, a currency sign or a ``%`` is something; ``|``, ``·``
    and a comma between two links are not.
    """
    return any(
        char in "%#@°" or unicodedata.category(char)[0] in "LN"
        or unicodedata.category(char) == "Sc"
        for char in text or ""
    )


def _carries_only_its_children(element: HtmlElement) -> bool:
    """True when every word of ``element``'s text already belongs to a child.

    A wrapper is not a fact. Hacker News puts each rank inside a ``<td>`` that
    holds one ``<span>`` and nothing else, so emitting both gave the same "1."
    under two names and left the caller to work out they were one thing. An
    element earns a text fact only by contributing text of its own -- the
    "Price:" in ``<p>Price: <b>18.40</b></p>`` exists nowhere else, so that
    paragraph keeps its text while the bare wrapper loses it.

    Its own text is what sits outside its children: its ``text`` and the
    ``tail`` of each child. Comparing whole strings instead failed on every
    wrapper of two or more children, because ``text_content`` runs them
    together with no space between.
    """
    children = [child for child in element if isinstance(child.tag, str)]
    if not children:
        return False
    own = [element.text, *(child.tail for child in element)]
    return not any(_says_something(text) for text in own)


def _facts(element: HtmlElement) -> list[tuple[str, str]]:
    """The facts one part carries, each with the suffix its name takes."""
    facts = []
    text = _text(element)
    if text and not _carries_only_its_children(element):
        facts.append(("", text))
    address = address_of(element)
    if address:
        facts.append(("@" + str(ADDRESS[str(element.tag)]), address))
    return facts


def _label(element: HtmlElement) -> str:
    """The first class a person wrote on ``element``, or nothing."""
    for token in sorted((element.get("class") or "").split()):
        written = _written_by_a_person(token)
        if written:
            return written
    return ""


def _written_by_a_person(token: str) -> str | None:
    """``token`` as a stable name, or None when a build tool generated it.

    A generated class is renamed on every deploy -- ``dcr-1t2r5md``,
    ``css-1x2y3z``, ``sc-bdVaJa kPXmIq`` -- so a field named after one is a
    field that moves. A CSS module keeps the part a person wrote:
    ``Card_title__a1B2c`` is ``Card_title``.
    """
    if token.lower().startswith(_TOOLING_PREFIXES):
        return None
    module = _CSS_MODULE.fullmatch(token)
    if module and _random(module.group(2)):
        token = module.group(1)
    if any(_random(segment) for segment in re.split(r"[-_]+", token)):
        return None
    return token


def _random(segment: str) -> bool:
    """True when ``segment`` reads as a hash rather than a word.

    Letters and digits interleaved (``1t2r5md``, ``tx1zxd``), or case flipping
    on every other letter (``kPXmIq``). A word with a number after it --
    ``title1``, ``col-md-6`` -- is a person's.
    """
    if len(segment) < 5:
        return False
    if _INTERLEAVED.search(segment):
        return True
    flips = sum(
        1
        for one, two in pairwise(segment)
        if one.isalpha() and two.isalpha() and one.islower() != two.islower()
    )
    return segment.isalpha() and flips / len(segment) >= 0.5


def _parts(parent: HtmlElement, path: _Path) -> Iterator[tuple[HtmlElement, _Path]]:
    """Every element under ``parent``, each with the path that reaches it."""
    counts: dict[tuple[str, str], int] = {}
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        label = (child.tag, _label(child))
        counts[label] = counts.get(label, 0) + 1
        here = (*path, (*label, counts[label]))
        yield child, here
        yield from _parts(child, here)


def _repeated(walked: list[list[tuple[HtmlElement, _Path]]]) -> set[_Path]:
    """The slots some member of the group fills more than once."""
    return {
        (*path[:-1], (path[-1][0], path[-1][1], 0))
        for parts in walked
        for _, path in parts
        if path[-1][2] > 1
    }


def _name(path: _Path, repeated: set[_Path]) -> str:
    """The field name for one slot, numbered where the group needs it numbered."""
    segments = []
    for depth, (tag, css_class, ordinal) in enumerate(path):
        segment = f"{tag}.{css_class}" if css_class else tag
        if (*path[:depth], (tag, css_class, 0)) in repeated:
            segment += str(ordinal)
        segments.append(segment)
    return ">".join(segments)


def records_from(group: list[HtmlElement]) -> list[Record]:
    """Return one record per member of ``group``, all named the same way."""
    walked = [list(_parts(member, ())) for member in group]
    repeated = _repeated(walked)
    records: list[Record] = []
    for parts in walked:
        record = Record(type=None)
        for part, path in parts:
            name = _name(path, repeated)
            for suffix, value in _facts(part):
                record.fields[name + suffix] = Field(value=value, source="induced")
        if record.fields:
            records.append(record)
    return records
