"""What a page shows a reader and does not declare: a byline, a date, a heading.

``read_visible`` is the ``--visible`` reading, on by default since 0.10 and
off with ``--no-visible`` or ``visible=False``. Every answer is a guess,
kept apart from the summary, which only ever holds what a page declares, and
each names the element it was read from and the rule that read it. The rules
are deterministic: no clock is read, so the same page gives the same guesses,
and a date is read only as ``sluicer.normalise.iso_date`` reads one, so no
all-number form is taken for a day.

The rules are Sluicer's own, written after reading how Readability, defuddle,
htmldate, trafilatura, newspaper4k and metascraper look for the same things,
and made on WCXB's development split only (``bench/PREREG.md``).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from itertools import islice
from typing import Any
from urllib.parse import urlsplit

from lxml.html import HtmlElement

from sluicer.document import Document, join, load
from sluicer.normalise import iso_date
from sluicer.structure.groups import chrome

__all__ = ["Guess", "read_visible"]


@dataclass(frozen=True)
class Guess:
    """One answer read off the visible page: its value, the XPath of the
    element it came from, and the rule that read it."""

    value: str
    where: str
    rule: str


# Elements whose text a reader does not take for the article's own.
_AWAY = frozenset({"script", "style", "noscript", "template", "head", "title"})
# Containers of other people's words and other pages' cards. These three are
# searched in class and id names lowercased, so they need no case folding.
_ASIDE = re.compile(
    r"comment|related|sidebar|widget|footer|share|social|newsletter|promo|"
    r"recommend|popular|trending|breadcrumb|nav|menu|advert|sponsor"
)
# Named as a byline: whole words, so authorization and authentic are not.
_BYLINE = re.compile(
    r"\b(?:byline|author(?:s|name|_name)?|writtenby|written-by|contributor)\b"
)
_DATE = re.compile(r"date|time|publish|posted|byline|meta")
_PUBLISHED = re.compile(r"entry-date|published|pubdate|post-date|publish", re.I)
_BY = re.compile(
    r"^\s*(?:(?:written|posted|authored|story|words|article)\s+)?"
    r"(?:by|von|par|por|di|door|av|af)\s*:?\s+(.{2,80}?)\s*$",
    re.I,
)
# A byline's label with nothing after it: the name is the next text.
_LABEL_ONLY = re.compile(
    r"^\s*(?:(?:written|posted|authored|reviewed|story|words)\s+)?(?:by|author)\s*:?\s*$",
    re.I,
)
# The first words of a "By X" line, to find its text before reading it all.
_OPENS_BY = re.compile(
    r"\s*(?:(?:written|posted|authored|story|words|article)\s+)?"
    r"(?:by|von|par|por|di|door|av|af)\b",
    re.I,
)
_NOT_A_NAME = re.compile(r"@|https?:|www\.|\d|&", re.I)
# The lowercase words a name may hold: its particles, as in Ludwig van Beethoven.
_PARTICLES = frozenset(
    (  # noqa: SIM905 -- read as a line of words
        "van von der den de del della da di du dos das la le bin ibn al el y and the"
    ).split()
)
# Words of a byline's box that are its labels, not somebody's name.
_LABEL_WORDS = frozenset(
    (  # noqa: SIM905 -- read as a line of words
        "staff writer writers editor editors team author authors "
        "contributor contributors bio reporter reporters correspondent "
        "desk admin newsroom content blog about"
    ).split()
)
# A role written after a name, "Jeff Hoyt Editor in Chief": the name ends there.
_ROLES = frozenset(
    (  # noqa: SIM905 -- read as a line of words
        "editor writer reporter correspondent contributor columnist"
    ).split()
)
# Words that say what follows a name's comma is somebody's role, "Sean Peek,
# Senior Analyst": the name ends at that comma.
_ROLE_WORDS = frozenset(
    (  # noqa: SIM905 -- read as a line of words
        "founder co-founder cofounder ceo cto coo cfo cmo cpo president chair "
        "chairman chairwoman director head lead manager editor writer reporter "
        "correspondent contributor columnist journalist author engineer "
        "researcher scientist analyst partner professor lecturer fellow "
        "designer developer consultant advisor adviser specialist expert "
        "officer chief senior principal vp owner producer strategist attorney "
        "lawyer dietitian physician nurse therapist coach educator teacher "
        "student intern executive"
    ).split()
)
# The most words a role after a name's comma may hold.
_ROLE_MOST_WORDS = 6
# A date a page says it was changed on, not published on: its label, in the
# text just before it, or its element's name.
_UPDATED = re.compile(
    r"updat|modifi|revis|edited|aktualisiert|ge(?:ä|ae)ndert|mis\s+(?:à|a)\s+jour|"
    r"actualiz|aggiornat|bijgewerkt",
    re.I,
)
# The word just before a date that says it is an update's: "Updated on", not
# "M&A Updates".
_UPDATED_WORD = re.compile(
    r"updated?|modified|revised|edited|aktualisiert|ge(?:ä|ae)ndert|jour|"
    r"actualizad[oa]|aggiornato|bijgewerkt",
    re.I,
)
# Boxes that hold the whole page, not a header.
_PAGE_BOXES = frozenset({"html", "body", "main"})
# The boxes that hold the whole page or all of an article: none of them is a
# byline, whatever its classes say.
_NO_BYLINE_BOX = frozenset({"html", "body", "main", "article"})
# A class that says there is no byline: "no-byline", "hide-author".
_NO_BYLINE = re.compile(r"\b(?:no|hide|hidden)-\S*")
# The most different dates a page may show before it is taken for a listing,
# whose dates are its cards' and are read only next to its heading.
_MOST_DATES = 3
_URL_DATE = re.compile(r"/(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$)")
# The most elements a byline selector may match: more is testimonials or
# comments, not the article's author.
_MOST_BYLINES = 3


def read_visible(
    html: str | bytes | Document, url: str | None = None
) -> dict[str, Guess]:
    """The page's visible title, author, publication date and update date,
    where it shows them, keyed by the summary's question names: ``title``,
    ``author``, ``published``, ``modified``. A question the page shows no
    answer to is absent."""
    doc = html if isinstance(html, Document) else load(html, url=url)
    page = _Page(doc)
    guesses: dict[str, Guess] = {}
    for question, read in (
        ("title", _title),
        ("author", _author),
        ("published", _date),
        ("modified", _modified),
    ):
        found = read(page)
        if found is not None:
            guesses[question] = found
    return guesses


class _Page:
    """A page, with what several rules look at found once: the elements named
    by a class or an id, the one heading, and the elements round it."""

    def __init__(self, doc: Document) -> None:
        self.doc = doc
        self.tree = doc.tree
        # Whether an element or a box round it is chrome, hidden, or a link
        # away: each box asked once. Asked of every box round each date, a
        # chain of <time> nested 2,000 deep cost the square of its depth,
        # and 30 KB of it 1.3 s.
        self._aside: dict[HtmlElement, bool] = {}
        self._hidden: dict[HtmlElement, bool] = {}
        self._linked: dict[HtmlElement, bool] = {}
        # Each element's text, read once: a "By" line or a date climbs to
        # boxes it shares with every other one, and reading such a box for
        # each of them cost its square -- 8,000 in one article took 22 s.
        self._raw: dict[HtmlElement, str] = {}
        self._text: dict[HtmlElement, str] = {}

    def raw(self, element: HtmlElement) -> str:
        """``element``'s text as lxml joins it, read once."""
        found = self._raw.get(element)
        if found is None:
            found = self._raw[element] = element.text_content()
        return found

    def text(self, element: HtmlElement) -> str:
        """``element``'s text with its white space collapsed, read once."""
        found = self._text.get(element)
        if found is None:
            found = self._text[element] = " ".join(self.raw(element).split())
        return found

    def short(self, element: HtmlElement, most: int) -> str | None:
        """``element``'s text as ``text`` gives it, or None when that is
        longer than ``most``: read only as far as it takes to know. A box
        holds the text of every box inside it, and reading each whole of a
        chain of them nested 2,000 deep cost the square of its depth."""
        found = self._text.get(element)
        if found is None:
            read: list[str] = []
            size = 0
            for piece in element.itertext():
                read.append(piece)
                size += len(piece)
                # Collapsed, what was read begins what the whole collapses to.
                if size > most and len(" ".join("".join(read).split())) > most:
                    return None
            found = self.text(element)
        return found if len(found) <= most else None

    def aside(self, element: HtmlElement) -> bool:
        """Whether ``element`` sits in the page's chrome or another voice's
        box: `_own_aside` of it or of a box round it, each box asked once."""
        return _up(element, _own_aside, self._aside)

    def hidden(self, element: HtmlElement) -> bool:
        """Whether ``element`` or a box round it is hidden from a reader."""
        return _up(element, _own_hidden, self._hidden)

    def linked(self, element: HtmlElement) -> bool:
        """Whether ``element`` sits in a link to another page: another
        article's card. A link to the page itself, WordPress's permalink round
        its date, is not one."""
        here = _path_of(self.doc.url)
        return _up(
            element, lambda node: _links_away(node, self.doc, here), self._linked
        )

    @cached_property
    def named(self) -> list[tuple[HtmlElement, str]]:
        """The elements with a class or an id, in document order, with their
        names lowercased. Tested in Python on each element: asked as
        ``//*[@class or @id]``, libxml2 took the square of their number,
        31 s for a 10 MB page of 60,000 rows."""
        found = []
        for e in self.tree.iter():
            if not isinstance(e.tag, str) or e.tag in _AWAY:
                continue
            classes, key = e.get("class"), e.get("id")
            if classes is not None or key is not None:
                found.append((e, f"{classes or ''} {key or ''}".lower()))
        return found

    @cached_property
    def named_bylines(self) -> list[tuple[HtmlElement, str]]:
        """The elements a class or an id names as a byline's, with their
        names, found once for the author and for the date in a byline's line."""
        return [(e, names) for e, names in self.named if _BYLINE.search(names)]

    @cached_property
    def named_dates(self) -> list[HtmlElement]:
        """The small elements a class or an id names as a date's."""
        return [e for e, names in self.named if _DATE.search(names) and _small(e)]

    @cached_property
    def texts(self) -> list[Any]:
        """The page's text nodes of more than one character, in order, each
        knowing its element: where a "By" or a "Published" line opens."""
        # The XPath predicate string-length(normalize-space()) > 1 cost libxml2
        # the square of a page's tail texts: 16,000 took 2.2 s, a 3.6 MB page
        # held a server's workers past their budget. The same test, in Python.
        # Collapsed, a text is longer than one character exactly when it is
        # once its ends are stripped of the same four characters: read so,
        # since collapsing every text node of a page cost a third of --visible.
        return [
            text
            for text in self.tree.xpath("//text()")
            if len(text.strip(_XML_SPACE_CHARACTERS)) > 1
        ]

    @cached_property
    def times(self) -> list[HtmlElement]:
        """The page's ``<time>`` elements that may be a date's: one holding
        more than ``_MOST_INSIDE`` elements is a container, as an element
        named as a date's is, and its whole text is never read. A chain of
        them nested 2,000 deep was read in the square of its depth; none of
        the 11,062 on the cached corpus pages holds more than seven."""
        return [t for t in self.tree.iter("time") if _small(t)]

    @cached_property
    def listing(self) -> bool:
        """Whether the page shows more different dates than an article's
        header does: a listing's, whose dates are its cards'."""
        shown = {t.get("datetime") or _text(t) for t in self.times}
        shown |= {_text(e) for e in self.named_dates if iso_date(_text(e))}
        return len(shown) > _MOST_DATES

    def in_the_header(self, element: HtmlElement) -> bool:
        """Whether ``element`` shares a box with the page's heading: its
        parent's or grandparent's, where an article's header puts its date."""
        if self.heading is None:
            return False
        boxes = [self.heading.getparent()]
        if boxes[0] is not None:
            boxes.append(boxes[0].getparent())
        boxes = [b for b in boxes if b is not None and b.tag not in _PAGE_BOXES]
        return any(box in element.iterancestors() for box in boxes)

    @cached_property
    def heading(self) -> HtmlElement | None:
        headings = [h for h in self.tree.iter("h1") if not self.aside(h) and _text(h)]
        return headings[0] if len(headings) == 1 else None

    @cached_property
    def near(self) -> list[HtmlElement]:
        """The elements just after the page's one heading, then just before
        it; none when the page has no heading or several."""
        if self.heading is None:
            return []
        after = self.heading.xpath(f"following::*[position() <= {_AFTER_HEADING}]")
        before = self.heading.xpath(f"preceding::*[position() <= {_BEFORE_HEADING}]")
        return [e for e in (*after, *before) if e.tag not in _AWAY]


# What XPath's normalize-space() collapses: XML's four white-space characters,
# not a no-break space.
_XML_SPACE_CHARACTERS = " \t\n\r"


def _text(element: HtmlElement) -> str:
    return " ".join(element.text_content().split())


def _where(element: HtmlElement) -> str:
    return str(element.getroottree().getpath(element))


def _own_aside(node: HtmlElement) -> bool:
    """Whether ``node`` itself is chrome or another voice's box."""
    if not isinstance(node.tag, str):
        return False
    if node.tag in _AWAY or chrome(node) or node.tag in ("blockquote", "figure"):
        return True
    named = f"{node.get('class') or ''} {node.get('id') or ''}".lower()
    return bool(named.strip() and _ASIDE.search(named))


def _title(page: _Page) -> Guess | None:
    """The page's one ``h1`` outside its chrome: the heading a reader sees."""
    if page.heading is None:
        return None
    text = _text(page.heading)
    if not 3 <= len(text) <= 300:
        return None
    return Guess(text, _where(page.heading), "h1")


def _name(text: str) -> str | None:
    """A byline's text as a person's name, or None when it is not one."""
    text = " ".join(text.split())
    by = _BY.match(text)
    if by:
        text = by.group(1)
    text = re.split(r"\s*[|•·⋅]\s*|\s+-\s+|,\s*(?=\d)|\s+on\s+", text)[0].strip(" ,;:")
    # "Jane Doe, Senior Writer": the name ends at a comma a role follows.
    # Not at one a credential, a place or another name follows ("Ann Lee,
    # Ph.D.", "Bo Li, Zürich", "Ann Lee, Bo Li"), each kept as before.
    name, comma, after = text.partition(",")
    if comma and _a_role(after):
        text = name.strip()
    if (
        not text
        or _NOT_A_NAME.search(text)
        or text.lower() in {"author", "by", "admin"}
    ):
        return None
    words = text.split()
    role = next(
        (n for n, w in enumerate(words) if n >= 2 and w.lower() in _ROLES), None
    )
    if role is not None:
        words = words[:role]
        text = " ".join(words)
    if not 2 <= len(words) <= 5 or len(text) > 60:
        return None
    bare = [word.strip(".,'\u2019()").lower() for word in words]
    if all(word in _LABEL_WORDS or word in _PARTICLES for word in bare):
        return None
    for word in words:
        if word[:1].islower() and word not in _PARTICLES:
            return None
    return text


def _a_role(part: str) -> bool:
    """Whether ``part``, what follows a name's comma, is somebody's role."""
    words = [word.strip(".'\u2019&").lower() for word in part.split()]
    return 1 <= len(words) <= _ROLE_MOST_WORDS and bool(
        _ROLE_WORDS.intersection(words) or _LABEL_WORDS.intersection(words)
    )


def _first_name(element: HtmlElement) -> str | None:
    """The first of an element's pieces of text that is a name: pieces, since
    text_content runs "Preetam Jinka" and "Co-founder" into one word, and a
    label alone, "Written by", only says the name comes next."""
    pieces = [" ".join(t.split()) for t in element.itertext()]
    pieces = [p for p in pieces if p]
    for n, piece in enumerate(pieces):
        if _LABEL_ONLY.match(piece):
            continue
        if n and _LABEL_ONLY.match(pieces[n - 1]) and (name := _name(piece)):
            return name
        if name := _name(piece):
            return name
    return None


def _author(page: _Page) -> Guess | None:
    """A byline: a link marked rel=author, then an element named as a byline,
    then a "By X" line; a card a selector matches more than three times of is
    testimonials or comments, and is passed over. A line with no such mark,
    "Name, role" under the heading, is not read: nothing in it tells a
    byline from a deck, a team's list or a job's department."""
    marked = [
        e
        for e in page.tree.xpath(
            "//a[contains(concat(' ', normalize-space(@rel), ' '), ' author ')]"
        )
        if not page.aside(e)
    ]
    if 0 < len(marked) <= _MOST_BYLINES and (name := _first_name(marked[0])):
        return Guess(name, _where(marked[0]), "rel-author")
    named = [
        e
        for e, names in page.named_bylines
        if _BYLINE.search(_NO_BYLINE.sub("", names))
        and e.tag not in _NO_BYLINE_BOX
        and not page.aside(e)
    ]
    # The innermost of nested byline boxes, since the outer ones hold dates too.
    boxes = set(named)
    leaves = [e for e in named if not any(c in boxes for c in e.iterdescendants())]
    if 0 < len(leaves) <= _MOST_BYLINES:
        for element in leaves:
            person = element.xpath(".//*[@itemprop='name']")
            if person and (name := _name(_text(person[0]))):
                return Guess(name, _where(element), "byline")
            if name := _first_name(element):
                return Guess(name, _where(element), "byline")
    # A "By X" line: looked for from the text that opens it, since reading
    # every container's whole text to find the short ones costs the most. A
    # page with more than three of them, each naming somebody else, is a
    # listing of other pages' cards.
    # The names are counted as they come, and only the first line's place is
    # written: counting them all again for each line, and writing each one's
    # place, cost the square of their number, 2 s for 16,000 "By" lines.
    first: tuple[str, HtmlElement] | None = None
    names: set[str] = set()
    for opening in page.texts:
        if not _OPENS_BY.match(opening):
            continue
        element = _box_of(opening)
        if element is None or _in_a_card(page, element):
            continue
        found = _by_line(page, opening, element)
        if found is not None:
            first = first or found
            names.add(found[0])
            if len(names) > _MOST_BYLINES:
                return None
    if first is not None:
        return Guess(first[0], _where(first[1]), "by-line")
    return None


# Somebody a line names who is not the author: "Medically reviewed by".
_NOT_THE_AUTHOR = re.compile(
    r"(?:review|edit|fact|check|photo|illustrat|image|video|translat|sponsor|"
    r"present|power|host|design|develop|built|made)\w*\s*(?:by)?\s*:?\s*$",
    re.I,
)


def _by_line(
    page: _Page, opening: str, element: HtmlElement | None
) -> tuple[str, HtmlElement] | None:
    """The author a "By X" line starting with ``opening`` names, and the
    element it is read from, climbing from its element to the short box that
    holds the whole line."""
    for _ in range(5):
        if element is None or not isinstance(element.tag, str):
            return None
        text = page.short(element, 80)
        if text is None:
            return None
        if element.tag in ("p", "span", "div", "address") and not page.aside(element):
            before = (
                text[: text.find(opening.strip())] if opening.strip() in text else ""
            )
            if _NOT_THE_AUTHOR.search(before):
                return None
            if _BY.match(text) and (name := _name(text)):
                return name, element
            # "Written by" and the name in two texts, glued by text_content.
            if _LABEL_ONLY.match(opening) and (name := _name_after(element, opening)):
                return name, element
        element = element.getparent()
    return None


# The most text a link round a byline may hold beyond it and still be the
# author's own link, not another article's card.
_CARD_MOST = 40


def _in_a_card(page: _Page, element: HtmlElement) -> bool:
    """Whether ``element`` sits in a link to another page that holds more than
    a byline: another article's card, its title and "By Noah Cortez"."""
    if not page.linked(element):
        return False
    link = (
        element
        if element.tag == "a" and element.get("href")
        else next((a for a in element.iterancestors("a") if a.get("href")), None)
    )
    if link is None:
        return False
    return page.short(link, len(page.text(element)) + _CARD_MOST) is None


def _box_of(text: Any) -> HtmlElement | None:
    """The element whose text ``text``, a text node lxml gave, is: its
    parent's, when it is the tail after a child."""
    element: HtmlElement | None = text.getparent()
    if text.is_tail and element is not None:
        element = element.getparent()
    return element


def _name_after(element: HtmlElement, label: str) -> str | None:
    """The name in the text right after ``label`` inside ``element``."""
    pieces = [" ".join(t.split()) for t in element.itertext()]
    pieces = [piece for piece in pieces if piece]
    at = next((n for n, piece in enumerate(pieces) if piece == label.strip()), None)
    if at is None or at + 1 >= len(pieces):
        return None
    return _name(pieces[at + 1])


def _modified(page: _Page) -> Guess | None:
    """The date the page says it was last updated on: a date whose label or
    element's name says so, in the places a publication date is looked for."""
    for element in _date_places(page):
        if not _an_update(page, element):
            continue
        text = re.sub(
            r"^\s*(?:last\s+)?\w*\s*(?:on)?\s*:?\s*", "", _text(element), count=1
        )
        value = (
            iso_date(element.get("datetime") or "")
            or iso_date(_text(element))
            or iso_date(text)
        )
        if value:
            return Guess(value, _where(element), "updated")
    return _date_in_a_line(page, updates=True)


# The longest a line a date is read from inside may be: a byline with its
# date, "By Lisa Jennings on Dec. 19, 2025", not a paragraph.
_LINE_MOST = 160
# A line that says it opens with its publication date.
_PUBLISHED_LINE = re.compile(r"^\s*(?:published|posted|first published)\b", re.I)
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_WORD_START = re.compile(r"(?:^|(?<=\s))\S")


def _date_in_a_line(page: _Page, updates: bool) -> Guess | None:
    """A date written inside a short line of the article's header: its
    byline's box, an element named as a date's, a line that opens with
    "Published", or one of the few round the heading. A date the line says is
    an update's is ``modified``'s, and read only when ``updates``."""
    lines: list[HtmlElement] = []
    if not page.listing:
        lines += [e for e, _names in page.named_bylines if _small(e)]
        lines += page.named_dates
    lines += [e for e in page.near if _small(e)]
    seen: set[HtmlElement] = set()
    for element in lines:
        if element in seen:
            continue
        seen.add(element)
        text = _text(element)
        if not 8 <= len(text) <= _LINE_MOST:
            continue
        if page.aside(element) or page.hidden(element) or page.linked(element):
            continue
        labelled = _an_update(page, element)
        for start, value in _dates_in(text):
            if (labelled or _said_updated(text[:start])) is updates:
                rule = "updated, in a line" if updates else "in a line"
                return Guess(value, _where(element), rule)
    if updates or page.listing:
        return None
    for opening in page.texts:
        if not _PUBLISHED_LINE.match(opening):
            continue
        element = _box_of(opening)
        if element is None or not _small(element) or page.aside(element):
            continue
        text = _text(element)
        if len(text) <= _LINE_MOST:
            for start, value in _dates_in(text):
                if not _said_updated(text[:start]):
                    return Guess(value, _where(element), "published line")
    return None


def _dates_in(text: str) -> list[tuple[int, str]]:
    """The dates written in ``text``, each with where it starts: for every
    year, the longest run of two to five words ending with it that
    ``iso_date`` reads, and every ISO 8601 date."""
    found: list[tuple[int, str]] = []
    starts = [m.start() for m in _WORD_START.finditer(text)]
    for year in _YEAR.finditer(text):
        end = year.end()
        before = [at for at in starts if at < year.start()][-5:]
        for at in before:
            words = text[at:end].lstrip("•|·-\u2013\u2014,:;( ")
            value = iso_date(words)
            if value:
                found.append((end - len(words), value))
                break
    for iso in re.finditer(
        r"\d{4}-\d{2}-\d{2}(?:T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?", text
    ):
        value = iso_date(iso.group())
        if value:
            found.append((iso.start(), value))
    return sorted(found)


# An update's word a few words before a date, glued to a name before it or
# not: "ZamanUpdated on", "We updated this article on", "Modified: 10:31am On".
_SAID_UPDATED = re.compile(
    r"(?:updated?|modified|revised|edited|aktualisiert|ge(?:ä|ae)ndert|mis à jour|"
    r"actualizad[oa]|aggiornato|bijgewerkt)\b[^.!?]{0,28}$",
    re.I,
)


def _said_updated(before: str) -> bool:
    """Whether the words just before a date say it is an update's."""
    return bool(_SAID_UPDATED.search(before[-40:]))


def _date_places(page: _Page) -> list[HtmlElement]:
    """The elements a date is looked for in, in order: <time>, elements named
    as dates, and the few round the page's heading; none a reader cannot see,
    in the page's chrome, or in a link to another page."""
    named = [e for e in _named_dates(page) if 6 <= len(_text(e)) <= 52]
    near = [e for e in page.near if _small(e) and 6 <= len(_text(e)) <= 40]
    found: list[HtmlElement] = []
    seen: set[HtmlElement] = set()
    for element in [*page.times, *named, *near]:
        if element in seen:
            continue
        seen.add(element)
        if page.aside(element) or page.hidden(element) or page.linked(element):
            continue
        found.append(element)
    return found


# The most elements under one a date's text is read from: more is a container.
_MOST_INSIDE = 12


def _small(element: HtmlElement) -> bool:
    """Whether ``element`` holds few enough elements to be a date's box, so
    that a container's whole text is never read to learn it is too long."""
    return (
        sum(1 for _ in islice(element.iterdescendants(), _MOST_INSIDE + 1))
        <= _MOST_INSIDE
    )


def _named_dates(page: _Page) -> list[HtmlElement]:
    return page.named_dates


def _date(page: _Page) -> Guess | None:
    """A publication date: a <time> marked as the publication's, then a short
    text named as a date, then the page address's /YYYY/MM/DD/. Never a date
    inside a link to another page, which is another article's card, nor one the
    page says it was updated on, which is ``modified``'s."""
    doc = page.doc
    times = [
        t
        for t in page.times
        if not page.aside(t)
        and not page.linked(t)
        and not page.hidden(t)
        and not _an_update(page, t)
    ]
    shown = {t.get("datetime") or _text(t) for t in times}
    if len(shown) > _MOST_DATES:
        near = set(page.near)
        times = [t for t in times if t in near and page.in_the_header(t)]
    marked = [
        t
        for t in times
        if t.get("pubdate") is not None
        or _PUBLISHED.search(f"{t.get('class') or ''} {t.get('itemprop') or ''}")
    ]
    for element in marked + times:
        value = iso_date(element.get("datetime") or "") or iso_date(_text(element))
        if value:
            return Guess(value, _where(element), "time")
    for element in _named_dates(page):
        text = _text(element)
        if not 6 <= len(text) <= 52 or page.aside(element) or page.linked(element):
            continue
        if page.hidden(element) or _an_update(page, element):
            continue
        value = iso_date(
            re.sub(r"^\s*(?:published|posted|on)\s*:?\s*", "", text, flags=re.I)
        )
        if value:
            return Guess(value, _where(element), "date-text")
    beside = _date_near_heading(page)
    if beside is not None:
        return beside
    written = _date_in_a_line(page, updates=False)
    if written is not None:
        return written
    found = _URL_DATE.search(_path(doc.url))
    if found:
        year, month, day = (int(g) for g in found.groups())
        if 1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return Guess(f"{year:04d}-{month:02d}-{day:02d}", "url", "url-date")
    return None


def _up(
    element: HtmlElement,
    own: Callable[[HtmlElement], bool],
    known: dict[HtmlElement, bool],
) -> bool:
    """Whether ``own`` holds of ``element`` or of a box round it, ``known``
    remembering the answer for every box asked, so none is asked twice."""
    chain: list[HtmlElement] = []
    node: HtmlElement | None = element
    found = False
    while node is not None:
        if node in known:
            found = known[node]
            break
        chain.append(node)
        if own(node):
            found = True
            break
        node = node.getparent()
    for seen in chain:
        known[seen] = found
    return found


def _own_hidden(node: HtmlElement) -> bool:
    """Whether ``node`` itself is hidden from a reader."""
    style = (node.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or node.get("hidden") is not None:
        return True
    return bool(node.get("aria-hidden") == "true")


def _an_update(page: _Page, element: HtmlElement) -> bool:
    """Whether the page says ``element``'s date is when it was changed: by
    the element's own name or text, or by the few words just before it."""
    named = " ".join(element.get(name) or "" for name in ("class", "id", "itemprop"))
    if _UPDATED.search(named) and not _PUBLISHED.search(named):
        return True
    own = page.text(element)
    if _UPDATED.search(own[:24]):
        return True
    if element.getparent() is None or not own:
        return False
    before = _just_before(page, element)
    label = re.search(r"(\w+)(?:\s+on)?\s*:?\s*$", before[-32:])
    return bool(label and _UPDATED_WORD.fullmatch(label.group(1)))


# How much text before an element is read for the word that labels it, and
# past how many of its siblings: the label is the last word of 32 characters.
_BEFORE_CHARACTERS = 40
_BEFORE_SIBLINGS = 64


def _just_before(page: _Page, element: HtmlElement) -> str:
    """The text written just before ``element`` inside its parent, collapsed.

    The parent's whole text was read, and cut where ``element``'s text first
    appeared in it: for each date, the whole of a box that may hold them all,
    and for a date whose text also came earlier, the words before the earlier
    one. Here the siblings before it are read back until there is enough.
    """
    pieces: list[str] = []
    collected = 0
    node = element.getprevious()
    for _ in range(_BEFORE_SIBLINGS):
        if node is None:
            parent = element.getparent()
            pieces.append((parent.text if parent is not None else None) or "")
            break
        pieces += (node.tail or "", page.raw(node) if isinstance(node.tag, str) else "")
        collected += len(pieces[-2].strip()) + len(pieces[-1].strip())
        if collected > _BEFORE_CHARACTERS:
            break
        node = node.getprevious()
    raw = "".join(reversed(pieces))
    before = " ".join(raw.split())
    if before and (raw[-1:].isspace() or page.raw(element)[:1].isspace()):
        # Collapsed with the element's text, a space stood between them.
        before += " "
    return before


def _links_away(node: HtmlElement, doc: Document, here: str) -> bool:
    """Whether ``node`` itself is a link to a page other than ``here``."""
    if isinstance(node.tag, str) and node.tag == "a" and (href := node.get("href")):
        return not here or _path_of(join(doc.base, href)) != here
    return False


def _path_of(address: str | None) -> str:
    """``address``'s host and path, as the same page is written either way.

    An address ``urlsplit`` refuses, an unfilled template's
    ``https://[domain]/p`` or ``http://[::1``, gives none: it is no page's, so
    a link to it is to another page, and a page at it has no permalink.
    """
    try:
        parts = urlsplit(address) if address else None
    except ValueError:
        return ""
    if parts is None:
        return ""
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"


def _path(address: str | None) -> str:
    """``address``'s path, or none where ``urlsplit`` refuses it."""
    try:
        return urlsplit(address).path if address else ""
    except ValueError:
        return ""


# How many text nodes after the heading, and before it, a date is looked for in.
_AFTER_HEADING, _BEFORE_HEADING = 40, 10


def _date_near_heading(page: _Page) -> Guess | None:
    """A date written alone, as the whole text of a short element, just after
    the page's one heading or just before it: where an article's header puts
    it, whatever its classes are called."""
    for element in page.near:
        if not _small(element):
            continue
        text = _text(element)
        if not 6 <= len(text) <= 40 or page.aside(element) or page.linked(element):
            continue
        if page.hidden(element) or _an_update(page, element):
            continue
        value = iso_date(
            re.sub(r"^\s*(?:published|posted|on)\s*:?\s*", "", text, flags=re.I)
        )
        if value:
            return Guess(value, _where(element), "near-heading")
    return None
