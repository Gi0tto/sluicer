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
from the member that holds the most.

A part can carry two facts: an anchor is a name and a link, an image its alt
text and its source. The text takes the slot's name and the address takes the
name with the attribute appended: ``a.more`` and ``a.more@href``.
"""

from __future__ import annotations

import re
import unicodedata
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

# One step of the path to a slot: the tag, the first hand-written class, and
# which of the same-named siblings this is.
_Step = tuple[str, str, int]
_Path = tuple[_Step, ...]
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


def _parts(parent: HtmlElement, path: _Path) -> Iterator[tuple[HtmlElement, _Path]]:
    """Every element under ``parent``, each with the path that reaches it.

    In document order, walked with a stack of its own: libxml2 nests elements
    two thousand deep, and a recursive walk ran out of Python's stack on a row
    a thousand deep.
    """
    pending = list(reversed(_steps(parent, path)))
    while pending:
        child, here = pending.pop()
        yield child, here
        pending.extend(reversed(_steps(child, here)))


def _steps(parent: HtmlElement, path: _Path) -> list[tuple[HtmlElement, _Path]]:
    """``parent``'s element children, each with the path one step further."""
    counts: dict[tuple[str, str], int] = {}
    steps = []
    for child in parent:
        if not isinstance(child.tag, str):
            continue
        label = (child.tag, _label(child))
        counts[label] = counts.get(label, 0) + 1
        steps.append((child, (*path, (*label, counts[label]))))
    return steps


def _repeated(walked: list[list[tuple[HtmlElement, _Path]]]) -> set[_Path]:
    """The slots some member of the group fills more than once."""
    return {
        (*path[:-1], (path[-1][0], path[-1][1], 0))
        for parts in walked
        for _, path in parts
        if path[-1][2] > 1
    }


def _last_step(path: _Path, repeated: set[_Path]) -> str:
    """The last step of a slot's name, numbered where the group needs it numbered."""
    tag, css_class, ordinal = path[-1]
    segment = f"{tag}.{css_class}" if css_class else tag
    if (*path[:-1], (tag, css_class, 0)) in repeated:
        segment += str(ordinal)
    return segment


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
    walked = [list(_parts(member, ())) for member in group]
    repeated = _repeated(walked)
    left = max(_FLOOR, 10 * sum(_held(member) for member in group))
    # Each part's name is its parent's and one step more: spelt out from the
    # whole path for every part, three rows a thousand deep took 2.5 seconds.
    trails: dict[HtmlElement, _Trail] = {}
    records: list[Record] = []
    for parts in walked:
        record = Record(type=None, source="induced")
        for part, path in parts:
            trail = trails[part] = (
                trails.get(part.getparent()),
                _last_step(path, repeated),
            )
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
