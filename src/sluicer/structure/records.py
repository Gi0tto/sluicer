"""Turning one repeated shape into the records it describes.

A page that declares nothing has not named its fields, so no names are
invented: a field is named by where it sits and the class it carries, and
every field is marked induced.

The names come from the group, not from each member, so the columns line up.
A slot is named by the path down to it -- the tag and first hand-written class
of each ancestor inside the member, then its own: ``div.meta>span.sku``. A
member missing a slot simply lacks that field. Generated class names (CSS-in-JS
hashes such as ``dcr-1t2r5md``) are skipped, since they change every deploy.

Nothing repeated is dropped: three ``<span class="tag">`` in a card are
``span.tag1``, ``span.tag2``, ``span.tag3``, numbered once for the whole group
from the member that holds the most. No two slots share a name: where a number
would spell another slot's name -- a card's own ``<span class="tag1">`` -- the
numbers are written after a ``#``, ``span.tag#1``, ``span.tag#2``.

A part can carry two facts: an anchor is a name and a link, an image its alt
text and its source. The text takes the slot's name and the address takes the
name with the attribute appended: ``a.more`` and ``a.more@href``.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterator
from itertools import pairwise
from typing import TypeAlias

from lxml.html import HtmlElement

from sluicer.declared.merge import Field, Record

# The prefixes CSS-in-JS tools put before a hash: emotion, styled-components,
# styled-jsx, a news site's own renderer, Svelte and Astro.
_UTILITY = frozenset("[]>@:/!()")
_TOOLING_PREFIXES = ("css-", "sc-", "jsx-", "dcr-", "svelte-", "astro-", "emotion-")
# What a CSS module appends to a class after ``__``: letters, digits, ``_``
# and ``-``, five at least.
_HASH = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
_HASH_LEAST = 5
_INTERLEAVED = re.compile(r"[a-z]\d[a-z]|\d[a-z]\d", re.IGNORECASE)

# Which attribute carries the address, per tag. Named without an underscore
# because the ranking in ``groups`` asks the same question -- an element that
# points somewhere carries something, whether or not it also carries text --
# and one table is the only way the two can never disagree.
ADDRESS = {"a": "href", "img": "src", "link": "href", "source": "src"}

# The text of an image is the text its author wrote for the people who cannot
# see it. Every other element's text is the text inside it.
_TEXT_ATTRIBUTE = {"img": "alt"}

# A slot is where a part sits in its row, the same in every row of the group:
# its parent's slot (``_ROW`` for the row itself), its tag, its first
# hand-written class, and which of the same-named siblings it is. Each slot is
# numbered the first time the group's walk meets it, so a part carries its
# slot as one number rather than the whole path down to it: a path copied at
# every level of a row two thousand deep was most of the time of a large page.
_Slot = tuple[int, str, str, int]
_ROW = -1
# A slot's name as a link to its parent's and its own last step, spelt out only
# for a part that carries a fact.
_Trail: TypeAlias = "tuple[_Trail | None, str]"


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
        char in "%#@°"
        or unicodedata.category(char)[0] in "LN"
        or unicodedata.category(char) == "Sc"
        for char in text or ""
    )


def _carries_only_its_children(element: HtmlElement) -> bool:
    """True when every word of ``element``'s text already belongs to a child.

    A wrapper is not a fact: a news aggregator wraps each rank's ``<span>`` in
    a ``<td>``, and both would report "1.". An element keeps a text fact only for
    text of its own -- its ``text`` and each child's ``tail`` -- as the
    "Price:" in ``<p>Price: <b>18.40</b></p>`` is.
    """
    children = [child for child in element if isinstance(child.tag, str)]
    if not children:
        return False
    own = [element.text, *(child.tail for child in element)]
    return not any(_says_something(text) for text in own)


def _facts(element: HtmlElement) -> list[tuple[str, str]]:
    """The facts one part carries, each with the suffix its name takes."""
    facts = []
    # A wrapper's text is all its children's, and is not read at all: on a row
    # nested deep, reading it at every level was all the text below, again.
    text = "" if _carries_only_its_children(element) else _text(element)
    if text:
        facts.append(("", text))
    address = address_of(element)
    if address:
        facts.append(("@" + str(ADDRESS[str(element.tag)]), address))
    return facts


def holds_a_fact(
    group: list[HtmlElement], below: dict[HtmlElement, tuple[bool, bool]]
) -> bool:
    """Whether a part of some member of ``group`` carries a fact: whether
    ``records_from`` has anything to name.

    Answered without reading any text, from what each element and the parts
    under it hold, kept in ``below`` for the next group asked about. Groups
    nest, and a caller that tries one group after another, as ``induce``
    does, walked each group's rows in full to find nothing: listings nested a
    thousand deep, with no text in them, took twenty seconds.
    """
    return any(
        _below(child, below)[1]
        for member in group
        for child in member
        if isinstance(child.tag, str)
    )


def _below(
    element: HtmlElement, below: dict[HtmlElement, tuple[bool, bool]]
) -> tuple[bool, bool]:
    """Whether ``element``'s text holds a word, and whether it or a part under
    it carries a fact, as ``_facts`` would find one.

    Children first, with a stack of its own. A comment's own words are not
    text, and what follows it is, as ``text_content`` reads them.
    """
    pending = [(element, False)]
    while pending:
        node, ready = pending.pop()
        if node in below:
            continue
        if not ready:
            pending.append((node, True))
            pending.extend(
                (child, False)
                for child in node
                if isinstance(child.tag, str) and child not in below
            )
            continue
        worded = _worded(node.text)
        fact = bool(address_of(node))
        for child in node:
            if isinstance(child.tag, str):
                inner, deeper = below[child]
                worded = worded or inner
                fact = fact or deeper
            worded = worded or _worded(child.tail)
        attribute = _TEXT_ATTRIBUTE.get(str(node.tag))
        said = _worded(node.get(attribute)) if attribute else worded
        fact = fact or (said and not _carries_only_its_children(node))
        below[node] = (worded, fact)
    return below[element]


def _worded(text: str | None) -> bool:
    """Whether ``text`` holds more than whitespace."""
    return bool(text and not text.isspace())


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
    if any(char in _UTILITY for char in token):
        # Tailwind writes ``max-w-[1200px]``, ``md:w-1/2``, ``[&>li]:mt-2`` and
        # ``@container``: styling, not names, and characters a field name and
        # a path both use as separators.
        return None
    module = _css_module(token)
    if module and _random(module[1]):
        token = module[0]
    if any(_random(segment) for segment in re.split(r"[-_]+", token)):
        return None
    return token


def _css_module(token: str) -> tuple[str, str] | None:
    """``token`` as a CSS module writes it, the name and the hash after the
    first ``__`` that only a hash follows, or None.

    Counted rather than matched: the pattern this was, ``(.+?)__([A-Za-z0-9_-]{5,})``,
    tried every ``__`` and scanned to the end of the class from each, and a
    90 KB class, thirty thousand ``a__``, took seven seconds to read.
    """
    # Where the run of hash characters that ends the class begins.
    hashed = len(token.rstrip(_HASH))
    # The name is one character at least, and the hash is all that follows it.
    at = token.find("__", max(1, hashed - 2))
    if at < 0 or len(token) - at - 2 < _HASH_LEAST:
        return None
    return token[:at], token[at + 2 :]


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


def _parts(
    parent: HtmlElement, slots: dict[_Slot, int]
) -> Iterator[tuple[HtmlElement, int]]:
    """Every element under ``parent``, each with the number of its slot.

    In document order, walked with a stack of its own: libxml2 nests elements
    two thousand deep, and a recursive walk ran out of Python's stack on a row
    a thousand deep. ``slots`` numbers the slots met, and is shared by the
    rows of one group.
    """
    pending = list(reversed(_steps(parent, _ROW, slots)))
    while pending:
        child, here = pending.pop()
        yield child, here
        pending.extend(reversed(_steps(child, here, slots)))


def _steps(
    parent: HtmlElement, slot: int, slots: dict[_Slot, int]
) -> list[tuple[HtmlElement, int]]:
    """``parent``'s element children, each with its slot, one step below ``slot``."""
    counts: dict[tuple[str, str], int] = {}
    steps = []
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        label = (child.tag, _label(child))
        counts[label] = counts.get(label, 0) + 1
        step = (slot, *label, counts[label])
        number = slots.get(step)
        if number is None:
            number = slots[step] = len(slots)
        steps.append((child, number))
    return steps


def _segments(slots: dict[_Slot, int]) -> list[str]:
    """The last step of each slot's name, by number.

    A slot is numbered where the group needs it numbered: where some row fills
    it more than once. Two slots under one parent never share a name, or one
    value would overwrite the other: a numbered ``span.tag1`` is also what a
    card's own ``<span class="tag1">`` is called, and twelve ``span.tag`` make
    a ``span.tag12`` as two ``span.tag1`` do. The numbers of a slot whose name
    would clash are written after a ``#``, ``span.tag#1``, and the class the
    page wrote keeps its name. What still clashes -- libxml2 keeps any tag a
    page writes, ``a@href`` and ``span.x`` among them -- takes ``~2``, ``~3``,
    in the order the walk met it. A group whose names do not clash is named as
    it always was.
    """
    steps = list(slots)
    repeated = {
        (parent, tag, label) for parent, tag, label, ordinal in steps if ordinal > 1
    }
    segments = []
    for parent, tag, label, ordinal in steps:
        segment = f"{tag}.{label}" if label else tag
        if (parent, tag, label) in repeated:
            segment += str(ordinal)
        segments.append(segment)
    owners: dict[tuple[int, str], set[int]] = defaultdict(set)
    for number, (parent, tag, _, _) in enumerate(steps):
        for name in _names(segments[number], tag):
            owners[parent, name].add(number)
    clashing = {number for held in owners.values() if len(held) > 1 for number in held}
    if not clashing:
        return segments
    renumbered = {steps[number][:3] for number in clashing} & repeated
    taken: dict[int, set[str]] = defaultdict(set)
    tried: dict[tuple[int, str], int] = {}
    for number, (parent, tag, label, ordinal) in enumerate(steps):
        segment = segments[number]
        if (parent, tag, label) in renumbered:
            segment = (f"{tag}.{label}" if label else tag) + f"#{ordinal}"
        written, again = segment, tried.get((parent, segment), 1)
        while any(name in taken[parent] for name in _names(written, tag)):
            again += 1
            written = f"{segment}~{again}"
        tried[parent, segment] = again
        taken[parent].update(_names(written, tag))
        segments[number] = written
    return segments


def _names(segment: str, tag: str) -> tuple[str, ...]:
    """Every name a slot's facts can take: its text's, and its address's."""
    attribute = ADDRESS.get(tag)
    return (segment, f"{segment}@{attribute}") if attribute else (segment,)


# What one group's records may hold -- every name and every value they copy --
# is paid for from a budget of ten times what its rows hold, and never less than
# this. A field is named by the path down to it, and a part with text of its own
# holds all the text below it, so three rows six hundred deep with text at every
# level made 1.6 MB from a 7 KB page, and one long class over three hundred
# parts was written into three hundred names. When the budget runs out the
# records stop there, in document order, the same every time.
_FLOOR = 10_000


def records_from(group: list[HtmlElement]) -> list[Record]:
    """Return one record per member of ``group``, all named the same way."""
    slots: dict[_Slot, int] = {}
    walked = [list(_parts(member, slots)) for member in group]
    segments = _segments(slots)
    left = max(_FLOOR, 10 * sum(_held(member) for member in group))
    # Each slot's name is its parent's and one step more: spelt out from the
    # whole path for every part, three rows a thousand deep took 2.5 seconds.
    trails: list[_Trail] = []
    for (parent, *_), segment in zip(slots, segments, strict=True):
        # A slot is numbered after its parent's, so its parent's trail is made.
        trails.append((trails[parent] if parent != _ROW else None, segment))
    records: list[Record] = []
    for parts in walked:
        record = Record(type=None, source="induced")
        for part, slot in parts:
            trail = trails[slot]
            facts = _facts(part)
            if not facts:
                continue
            name = _spelt(trail)
            left -= sum(len(name) + len(suffix) + len(value) for suffix, value in facts)
            if left < 0:
                break
            for suffix, value in facts:
                record.fields[name + suffix] = Field(value=value, source="induced")
        if record.fields:
            records.append(record)
        if left < 0:
            break
    return records


def _spelt(trail: _Trail | None) -> str:
    steps = []
    while trail is not None:
        trail, step = trail
        steps.append(step)
    return ">".join(reversed(steps))


def _held(member: HtmlElement) -> int:
    """How much ``member`` holds: its tags, attributes and text, as written."""
    return sum(
        len(element.text or "")
        + len(element.tail or "")
        + (len(element.tag) if isinstance(element.tag, str) else 0)
        + sum(len(key) + len(value) for key, value in element.attrib.items())
        for element in member.iter()
    )
