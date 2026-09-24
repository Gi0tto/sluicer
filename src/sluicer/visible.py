"""What a page shows a reader and does not declare: a byline, a date, a heading.

``read_visible`` is the opt-in ``--visible`` reading. Every answer is a guess,
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
from dataclasses import dataclass
from functools import cached_property
from itertools import islice
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
        self._aside: dict[HtmlElement, bool] = {}

    def aside(self, element: HtmlElement) -> bool:
        """Whether ``element`` sits in the page's chrome or another voice's
        box: `_own_aside` of it or of a box round it, each box asked once."""
        chain: list[HtmlElement] = []
        node: HtmlElement | None = element
        found = False
        while node is not None:
            if node in self._aside:
                found = self._aside[node]
                break
            chain.append(node)
            if _own_aside(node):
                found = True
                break
            node = node.getparent()
        for seen in chain:
            self._aside[seen] = found
        return found

    @cached_property
    def named(self) -> list[tuple[HtmlElement, str]]:
        return [
            (e, f"{e.get('class') or ''} {e.get('id') or ''}".lower())
            for e in self.tree.xpath("//*[@class or @id]")
            if e.tag not in _AWAY
        ]

    @cached_property
    def named_dates(self) -> list[HtmlElement]:
        """The small elements a class or an id names as a date's."""
        return [e for e, names in self.named if _DATE.search(names) and _small(e)]

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
    text = re.split(r"\s*[|•·⋅]\s*|\s+-\s+|,\s*(?=\d)", text)[0].strip(" ,;:")
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
    testimonials or comments, and is passed over."""
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
        e for e, names in page.named if _BYLINE.search(names) and not page.aside(e)
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
    # every container's whole text to find the short ones costs the most.
    for opening in page.tree.xpath("//text()[string-length(normalize-space()) > 1]"):
        if not _OPENS_BY.match(opening):
            continue
        element = opening.getparent()
        if opening.is_tail and element is not None:
            element = element.getparent()
        for _ in range(5):
            if element is None or not isinstance(element.tag, str):
                break
            text = _text(element)
            if len(text) > 80:
                break
            if (
                element.tag in ("p", "span", "div", "address")
                and _BY.match(text)
                and not page.aside(element)
                and (name := _name(text))
            ):
                return Guess(name, _where(element), "by-line")
            element = element.getparent()
    return None


def _modified(page: _Page) -> Guess | None:
    """The date the page says it was last updated on: a date whose label or
    element's name says so, in the places a publication date is looked for."""
    for element in _date_places(page):
        if not _an_update(element):
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
    return None


def _date_places(page: _Page) -> list[HtmlElement]:
    """The elements a date is looked for in, in order: <time>, elements named
    as dates, and the few round the page's heading; none a reader cannot see,
    in the page's chrome, or in a link to another page."""
    named = [e for e in _named_dates(page) if 6 <= len(_text(e)) <= 52]
    near = [e for e in page.near if _small(e) and 6 <= len(_text(e)) <= 40]
    found: list[HtmlElement] = []
    seen: set[HtmlElement] = set()
    for element in [*page.tree.iter("time"), *named, *near]:
        if element in seen:
            continue
        seen.add(element)
        if page.aside(element) or _hidden(element) or _in_a_link(element, page.doc):
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
        for t in page.tree.iter("time")
        if not page.aside(t)
        and not _in_a_link(t, doc)
        and not _hidden(t)
        and not _an_update(t)
    ]
    shown = {t.get("datetime") or _text(t) for t in times}
    if len(shown) > _MOST_DATES:
        near = set(page.near)
        times = [t for t in times if t in near]
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
        if not 6 <= len(text) <= 52 or page.aside(element) or _in_a_link(element, doc):
            continue
        if _hidden(element) or _an_update(element):
            continue
        value = iso_date(
            re.sub(r"^\s*(?:published|posted|on)\s*:?\s*", "", text, flags=re.I)
        )
        if value:
            return Guess(value, _where(element), "date-text")
    near = _date_near_heading(page)
    if near is not None:
        return near
    address = doc.url or ""
    found = _URL_DATE.search(urlsplit(address).path)
    if found:
        year, month, day = (int(g) for g in found.groups())
        if 1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
            return Guess(f"{year:04d}-{month:02d}-{day:02d}", "url", "url-date")
    return None


def _hidden(element: HtmlElement) -> bool:
    """Whether ``element`` or a box round it is hidden from a reader."""
    for node in (element, *element.iterancestors()):
        style = (node.get("style") or "").replace(" ", "").lower()
        if "display:none" in style or node.get("hidden") is not None:
            return True
        if node.get("aria-hidden") == "true":
            return True
    return False


def _an_update(element: HtmlElement) -> bool:
    """Whether the page says ``element``'s date is when it was changed: by
    the element's own name or text, or by the few words just before it."""
    named = " ".join(element.get(name) or "" for name in ("class", "id", "itemprop"))
    if _UPDATED.search(named) and not _PUBLISHED.search(named):
        return True
    own = _text(element)
    if _UPDATED.search(own[:24]):
        return True
    parent = element.getparent()
    if parent is None:
        return False
    before = _text(parent)
    at = before.find(own) if own else -1
    before = before[:at] if at >= 0 else ""
    label = re.search(r"(\w+)(?:\s+on)?\s*:?\s*$", before[-32:])
    return bool(label and _UPDATED_WORD.fullmatch(label.group(1)))


def _in_a_link(element: HtmlElement, doc: Document) -> bool:
    """Whether ``element`` sits in a link to another page: another article's
    card. A link to the page itself, WordPress's permalink round its date, is
    not one."""
    here = _path_of(doc.url)
    for node in (element, *element.iterancestors()):
        if isinstance(node.tag, str) and node.tag == "a" and (href := node.get("href")):
            target = _path_of(join(doc.base, href))
            if not here or target != here:
                return True
    return False


def _path_of(address: str | None) -> str:
    if not address:
        return ""
    parts = urlsplit(address)
    return f"{parts.netloc.lower().removeprefix('www.')}{parts.path.rstrip('/')}"


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
        if (
            not 6 <= len(text) <= 40
            or page.aside(element)
            or _in_a_link(element, page.doc)
        ):
            continue
        if _hidden(element) or _an_update(element):
            continue
        value = iso_date(
            re.sub(r"^\s*(?:published|posted|on)\s*:?\s*", "", text, flags=re.I)
        )
        if value:
            return Guess(value, _where(element), "near-heading")
    return None
