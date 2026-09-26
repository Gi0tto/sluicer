"""The main-text rules chosen on WCXB's dev split and not shipped in 0.10.

``sluicer.markdown`` as it stood at ``f196abe`` on the v010-text branch, kept
here so that ``bench/markdown_dev.py`` can reproduce every number
``bench/PREREG.md`` records under "The main text". Its rules were called
worse than trafilatura on trafilatura's evaluation set, and 0.10's main text
is 0.9.1's; nothing in ``src/`` imports this.

The module's own description, as it was:
A page's main content, as markdown, with the furniture removed.

Finding the article and leaving the navigation behind starts with trafilatura:
Sluicer hands it the page, links resolved, and then checks what came back
against the page itself, by rules made on WCXB's development pages and
measured on the scoreboards after (``bench/PREREG.md``, "The main text"):

1. When trafilatura's text is much shorter than the page's main region, the
   longer of it and trafilatura's own copy of readability; then, when that is
   much shorter than trafilatura's extraction favouring recall, that one.
2. The paragraphs the extraction left out between two it kept, in the element
   its text comes from, when they are sentences and not links (``_gaps_filled``).
3. The article text the page declares for itself, in JSON-LD or microdata,
   when it holds at least as many words (``_declared_text``).
4. The page's ``<h1>`` as the first heading, when it is the title the page
   declares and the text does not already hold it.

``read_markdown`` says which of these the text came from; ``to_markdown``
returns the text. ``full=True`` writes the whole page instead, like a
converter of pages (``sluicer.markdown_writer``). trafilatura sits behind the
``markdown`` extra, so a reader who never asks for the main text does not
carry it; the whole page needs only lxml.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import ModuleType
from urllib.parse import quote, urlsplit

import lxml.html

from sluicer.declared.merge import Record
from sluicer.document import Document, _base_of, join, load, trimmed
from sluicer.extras import MissingExtra, import_extra
from sluicer.markdown_writer import (
    element_markdown,
    fragment_markdown,
    shown_words,
    text_markdown,
)


class MarkdownExtraMissing(MissingExtra):
    """The optional ``markdown`` extra (trafilatura) is not installed.

    Its message names the install line. What counts as missing, as opposed to
    broken, is ``sluicer.extras``'s rule.
    """


def _trafilatura() -> ModuleType:
    """Import trafilatura, or say the extra is not installed."""
    return import_extra(
        "trafilatura",
        "markdown",
        doing="Turning a page into markdown",
        error=MarkdownExtraMissing,
    )


@dataclass(frozen=True)
class MainText:
    """A page's text as markdown, and where it came from.

    ``source`` is ``"declared"`` when the page's own article text was used,
    ``"extracted"`` when it was found in the page, ``"page"`` for the whole
    page (``full``), and ``""`` when there is no text. ``method`` says how:
    for declared text its reader, type and key (``"jsonld NewsArticle
    articleBody"``); for extracted text the extractor (``"trafilatura"``,
    ``"trafilatura favoring recall"`` or ``"readability"``), with ``" + gaps"``
    when paragraphs it left out were put back from the page, and ``" + h1"``
    when the page's heading was put first. ``where`` is the declared field's
    place, an XPath, and for JSON-LD the script's with a JSON pointer.
    """

    markdown: str
    source: str
    method: str
    where: str | None = None


def to_markdown(
    html: str | bytes,
    url: str | None = None,
    front_matter: bool = False,
    full: bool = False,
) -> str:
    """Return the page's main content as markdown, or ``""`` when it has none.

    Args:
        html: the page. Prefer bytes: trafilatura detects the encoding from
            them, including a ``<meta charset>``.
        url: the address the page came from, used to resolve its links.
        front_matter: open the markdown with a YAML block of what the page
            declares about itself -- title, author, dates, url, and the rest of
            the summary -- and where each answer came from, the way static-site
            generators and retrieval pipelines read a document's metadata;
            ``sources`` also says where the text came from (``text``), as
            ``read_markdown`` does.
        full: the whole page, not its main content: every heading, paragraph,
            list, table, link and image a reader is shown, menus and footers
            included, scripts and styles left out, links resolved. It needs
            no extra.

    Raises:
        MarkdownExtraMissing: trafilatura is not installed (not for ``full``).
    """
    found = read_markdown(html, url=url, full=full)
    if not found.markdown or not front_matter:
        return found.markdown
    return declared_front_matter(html, url, text=found) + found.markdown


def read_markdown(
    html: str | bytes, url: str | None = None, full: bool = False
) -> MainText:
    """The page's main content as markdown, and where it came from.

    As ``to_markdown``, with the text's source beside it (``MainText``).

    Raises:
        MarkdownExtraMissing: trafilatura is not installed (not for ``full``).
    """
    if full:
        written = _full_markdown(html, url)
        return MainText(written, "page" if written else "", "")
    return _main_text(html, url)


def _main_text(html: str | bytes, url: str | None) -> MainText:
    """The rules the module's docstring lists, in its order."""
    trafilatura = _trafilatura()
    # Imported here: the summary is the library's heaviest import.
    from sluicer.api import _extract as extract

    resolved = _with_links_resolved(trafilatura, html, url)

    def extracted(**options: bool) -> str:
        # trafilatura is imported by name, so what it returns is untyped; the
        # annotation states what its ``extract`` documents.
        produced: str | None = trafilatura.extract(
            resolved,
            output_format="markdown",
            include_links=True,
            include_tables=True,
            url=url,
            **options,
        )
        return produced or ""

    doc = load(html, url=url)
    text, method = extracted(), "trafilatura"
    words = _count(text)
    region = _region_words(doc)
    if words < _SHORT * region:
        rescued = _readability(trafilatura, html, doc)
        if _count(rescued) > words:
            text, method, words = rescued, "readability", _count(rescued)
    recalled = extracted(favor_recall=True)
    if words < _SHORT * _count(recalled) and _count(recalled) > words:
        text, method, words = recalled, "trafilatura favoring recall", _count(recalled)
    filled = _gaps_filled(doc, text, _LEAST)
    if filled is not None and filled != text:
        text, method, words = filled, f"{method} + gaps", _count(filled)
    result = extract(html, url=url)
    declared = _declared_text(doc, result.records)
    if declared is not None and _count(declared.markdown) >= words:
        found = MainText(declared.markdown, "declared", declared.said, declared.where)
    elif text:
        found = MainText(text, "extracted", method)
    else:
        return MainText("", "", "")
    title = result.summary.get("title")
    heading = _titled_heading(doc, str(title.value) if title else None)
    if heading and " ".join(_words(heading)) not in " ".join(_words(found.markdown)):
        return MainText(
            f"# {heading}\n\n{found.markdown}",
            found.source,
            f"{found.method} + h1",
            found.where,
        )
    return found


# Much shorter: under this share of what it is measured against.
_SHORT = 0.7
# A left-out paragraph is put back when it has this many words or more.
_LEAST = 12


def _readability(trafilatura: ModuleType, html: str | bytes, doc: Document) -> str:
    """The text trafilatura's own copy of readability finds, as markdown, or
    ``""`` where this trafilatura has none."""
    try:
        from trafilatura.external import try_readability
    except ImportError:
        return ""
    loaded = trafilatura.load_html(html)
    if loaded is None:
        return ""
    return element_markdown(try_readability(loaded), doc.base)


def _with_links_resolved(
    trafilatura: ModuleType, html: str | bytes, url: str | None
) -> object:
    """The page with every link resolved against the page, for trafilatura.

    trafilatura resolves a relative link against the site's root, not the
    page: on ``https://site/a/b/page.html``, ``c.html`` became
    ``https://site/c.html`` and ``#part`` ``https://site#part``, so every
    relative link in the markdown led somewhere else. The page is loaded the
    way trafilatura loads it (its own ``load_html``, so the encoding is still
    worked out from the bytes), and each ``<a href>`` is resolved against the
    page's ``<base href>`` or its address first; an absolute link is one
    trafilatura leaves alone. With neither to resolve against, the page goes
    over as given and its links stay as the page wrote them.
    """
    if url is None and not _may_declare_a_base(html):
        return html
    tree = trafilatura.load_html(html)
    if tree is None:
        return html
    base = _base_of(tree, url)
    if not base:
        return html
    for anchor in tree.iter("a"):
        href = anchor.get("href")
        # A template's ``{placeholder}`` is left as written, as trafilatura
        # leaves it.
        if href is None or trimmed(href).startswith("{"):
            continue
        anchor.set("href", _xml_safe(join(base, href)))
    return tree


# What an lxml attribute cannot hold: C0 controls, which the URL standard
# percent-encodes in an address, DEL, which it encodes too, and the two
# noncharacters XML refuses. A tab, a newline and a carriage return are never
# left in an address (``sluicer.document.clean_address``).
_NOT_XML = re.compile("[\x00-\x1f\x7f\ufffe\uffff]")


def _xml_safe(address: str) -> str:
    """``address`` with what an lxml attribute refuses percent-encoded.

    A share link on a real page held a backspace from a comment's text, and
    setting it raised "All strings must be XML compatible": the whole page
    gave no markdown.
    """
    return _NOT_XML.sub(lambda m: quote(m.group().encode("utf-8"), safe=""), address)


def _may_declare_a_base(html: str | bytes) -> bool:
    """Whether the page has a ``<base`` tag in it anywhere, cheaply."""
    if isinstance(html, bytes):
        return re.search(rb"<base\b", html, re.IGNORECASE) is not None
    return re.search(r"<base\b", html, re.IGNORECASE) is not None


def declared_front_matter(
    html: str | bytes, url: str | None = None, text: MainText | None = None
) -> str:
    """A YAML front matter block of the page's summary, with each answer's source.

    Every value is written as a JSON string, which is a YAML string, so no
    value a page declares can break the block or be read as YAML syntax. A
    date or price is written normalised where ``Extraction.normalised`` has it,
    and as the page wrote it otherwise. Given the page's ``text``, ``sources``
    also says where it came from, and ``text_where`` where the page declares
    it. ``""`` when the page answers nothing and no text is given.
    """
    # Imported here: the summary is the library's heaviest import, and a caller
    # who never asks for front matter should not pay for it.
    from sluicer.api import _extract as extract

    result = extract(html, url=url)
    said_text = _text_said(text)
    if not result.summary and not said_text:
        return ""
    lines = ["---"]
    for question, answer in result.summary.items():
        value = result.normalised.get(question, answer.value)
        lines.append(f"{question}: {json.dumps(value, ensure_ascii=False)}")
    if text is not None and text.where:
        lines.append(f"text_where: {json.dumps(text.where, ensure_ascii=False)}")
    lines.append("sources:")
    for question, answer in result.summary.items():
        said = f"{answer.source} {answer.key}"
        lines.append(f"  {question}: {json.dumps(said, ensure_ascii=False)}")
    if said_text:
        lines.append(f"  text: {json.dumps(said_text, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def _text_said(text: MainText | None) -> str:
    """Where a text came from, in one line: its source, then how."""
    if text is None or not text.source:
        return ""
    return f"{text.source} {text.method}".strip()


# --- the text a page declares ------------------------------------------------------

# schema.org's Article and every type under it.
_ARTICLES = frozenset(
    {
        "Article",
        "AdvertiserContentArticle",
        "NewsArticle",
        "AnalysisNewsArticle",
        "AskPublicNewsArticle",
        "BackgroundNewsArticle",
        "OpinionNewsArticle",
        "ReportageNewsArticle",
        "ReviewNewsArticle",
        "Report",
        "SatiricalArticle",
        "ScholarlyArticle",
        "MedicalScholarlyArticle",
        "SocialMediaPosting",
        "BlogPosting",
        "LiveBlogPosting",
        "DiscussionForumPosting",
        "TechArticle",
        "APIReference",
    }
)
_BODY_KEYS = ("articleBody", "text")
# A body written with HTML tags, as some sites put their article in JSON-LD.
_MARKUP = re.compile(r"</?(?:p|br|div|h[1-6]|ul|ol|li|a|em|strong|b|i|span)\b", re.I)


@dataclass(frozen=True)
class DeclaredText:
    """An article's text as the page declares it, and where."""

    markdown: str
    source: str
    type: str
    key: str
    where: str | None

    @property
    def said(self) -> str:
        return f"{self.source} {self.type} {self.key}"


def _same_page(declared: str, url: str) -> bool:
    """Whether an address a record names is the page's, its scheme, a
    ``www.``, a trailing slash and a fragment aside."""

    def key(address: str) -> tuple[str, str, str]:
        parts = urlsplit(trimmed(address))
        return (
            parts.netloc.lower().removeprefix("www."),
            parts.path.rstrip("/") or "/",
            parts.query,
        )

    return key(declared) == key(url)


def _declared_text(doc: Document, records: list[Record]) -> DeclaredText | None:
    """The page's own article text, when it declares one for itself.

    From the one record of type ``Article`` or a type under it, in JSON-LD or
    microdata, that carries ``articleBody`` (or ``text``); none when two carry
    one, since a page of several articles has no one text, or when the record
    names another page as its ``url`` or ``mainEntityOfPage``. A body ending
    in an ellipsis is a teaser, never used. A microdata body is its element,
    written as markdown; a JSON-LD body is converted when it holds HTML, and
    otherwise written a paragraph a line.
    """
    bodies = []
    for record in records:
        if record.source not in ("jsonld", "microdata"):
            continue
        if not _ARTICLES.intersection(record.types):
            continue
        for key in _BODY_KEYS:
            found = record.fields.get(key)
            if (
                found is not None
                and isinstance(found.value, str)
                and found.value.strip()
            ):
                bodies.append((record, key, found))
                break
    if len(bodies) != 1:
        return None
    record, key, found = bodies[0]
    if doc.url:
        for name in ("url", "mainEntityOfPage"):
            named = record.fields.get(name)
            value = named.value if named is not None else None
            if isinstance(value, dict):
                value = value.get("@id") or value.get("url")
            if (
                isinstance(value, str)
                and value.strip()
                and not _same_page(value, doc.url)
            ):
                return None
    text = str(found.value).strip()
    if text.endswith(("...", "\u2026")):
        return None
    if found.source == "microdata" and found.where:
        placed = doc.tree.xpath(found.where)
        markdown = (
            element_markdown(placed[0], doc.base)
            if placed and isinstance(placed[0], lxml.html.HtmlElement)
            else text_markdown(text)
        )
    elif _MARKUP.search(text):
        markdown = fragment_markdown(text, doc.base)
    else:
        markdown = text_markdown(text)
    if not markdown:
        return None
    return DeclaredText(markdown, found.source, record.type or "", key, found.where)


# --- the whole page ------------------------------------------------------------------


def _full_markdown(html: str | bytes, url: str | None) -> str:
    """The whole page's body as markdown, as a reader running no script is
    shown it."""
    doc = load(html, url=url)
    body = doc.tree.find("body")
    return element_markdown(
        body if body is not None else doc.tree, doc.base, noscript=True
    )


# --- counting what the extraction holds ----------------------------------------------

_WORD = re.compile(r"\w+")
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_LINK_TEXT = re.compile(r"\[([^\]]*)\]\(")


def _words(markdown: str) -> list[str]:
    """The words of a piece of markdown, lowercase, a link's address left out."""
    return _WORD.findall(_LINK_TARGET.sub("]", markdown).lower())


def _count(markdown: str) -> int:
    return len(_words(markdown))


_REGION_LEFT_OUT = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
    }
)


def _region_words(doc: Document) -> int:
    """The words of the page's main region a reader is shown: the first
    ``<main>``, else the first ``[role=main]``, else the page's one
    ``<article>``, else ``<body>``, without its navigation, header, footer,
    asides and forms."""
    import copy

    tree = doc.tree
    region = None
    for path in ("//main", "//*[@role='main']"):
        found = tree.xpath(path)
        if found:
            region = found[0]
            break
    if region is None:
        articles = tree.xpath("//article")
        region = articles[0] if len(articles) == 1 else tree.find("body")
    if region is None:
        return 0
    region = copy.deepcopy(region)
    for element in list(region.iter()):
        if not isinstance(element.tag, str):
            continue
        left_out = element.tag in _REGION_LEFT_OUT or element.get("hidden") is not None
        if left_out and element.getparent() is not None:
            element.drop_tree()
    return len(_WORD.findall(region.text_content()))


# --- the paragraphs the extraction left out -----------------------------------------

# Boxes beside an article's text, by what their class or id names.
_BOXES = re.compile(
    r"share|social|related|comment|newsletter|subscribe|cookie|breadcrumb|"
    r"sidebar|advert|promo|sponsor|popup|modal",
    re.IGNORECASE,
)
_AUTHOR_BOXES = re.compile(r"author|bio|byline", re.IGNORECASE)
_ROLES = frozenset({"navigation", "banner", "contentinfo", "complementary", "search"})
_OUT_OF_REGION = frozenset({"nav", "aside", "footer", "form"})
# A block of the extraction is found on the page by this many first words.
_KEY = 5
_LIST_ITEM = re.compile(r"^(?:[-*+]|\d{1,9}[.)]) ")
_HEADING_LINE = re.compile(r"^#{1,6} ")


def _boxed(element: lxml.html.HtmlElement, authors: bool = False) -> bool:
    """Whether an element is a box beside the text, not the text."""
    if not isinstance(element.tag, str):
        return False
    if element.tag.lower() in _OUT_OF_REGION:
        return True
    if (element.get("role") or "").strip().lower() in _ROLES:
        return True
    named = f"{element.get('class') or ''} {element.get('id') or ''}"
    return bool(_BOXES.search(named) or (authors and _AUTHOR_BOXES.search(named)))


def _region_of(
    tree: lxml.html.HtmlElement, extracted: str
) -> lxml.html.HtmlElement | None:
    """The deepest element holding four in five of the extraction's blocks of
    six words or more that are found on the page, unless it is the whole body."""
    body = tree.find("body")
    if body is None:
        return None
    words = shown_words(body)
    first: dict[tuple[str, ...], int] = {}
    for at in range(len(words) - _KEY + 1):
        first.setdefault(tuple(w for w, _ in words[at : at + _KEY]), at)
    anchors = []
    for block in extracted.split("\n\n"):
        said = _words(block)
        if len(said) < 6:
            continue
        found = first.get(tuple(said[:_KEY]))
        if found is not None:
            anchors.append(words[found][1])
    if not anchors:
        return None
    counts: dict[lxml.html.HtmlElement, int] = {}
    depth: dict[lxml.html.HtmlElement, int] = {}
    for anchor in anchors:
        chain = [anchor, *anchor.iterancestors()]
        for level, element in enumerate(reversed(chain)):
            counts[element] = counts.get(element, 0) + 1
            depth[element] = level
    needed = 0.8 * len(anchors)
    region = max((e for e, n in counts.items() if n >= needed), key=lambda e: depth[e])
    return None if str(region.tag).lower() in ("body", "html") else region


def _region_written(
    region: lxml.html.HtmlElement, base: str | None, authors: bool
) -> str:
    """The region as markdown, without images and without the boxes beside
    its text."""
    import copy

    region = copy.deepcopy(region)
    for element in list(region.iterdescendants()):
        if element.getparent() is not None and _boxed(element, authors):
            element.drop_tree()
    return element_markdown(region, base, images=False)


def _units(written: str) -> list[str]:
    """The region's blocks, each item of a list a unit of its own."""
    found: list[str] = []
    for block in written.split("\n\n"):
        if not _LIST_ITEM.match(block):
            found.append(block)
            continue
        item: list[str] = []
        for line in block.split("\n"):
            if _LIST_ITEM.match(line) and item:
                found.append("\n".join(item))
                item = []
            item.append(line)
        if item:
            found.append("\n".join(item))
    return [unit for unit in found if _words(unit)]


def _put_back(unit: str, least: int) -> bool:
    """Whether a left-out block reads as the text's own: a paragraph or a
    list item of ``least`` words or more, under half of them link text, not a
    heading, not a quotation, and not one phrase repeated."""
    if _HEADING_LINE.match(unit) or unit.startswith(">"):
        return False
    said = _words(unit)
    if len(said) < least or len(set(said)) < 0.5 * len(said):
        return False
    linked = sum(len(_WORD.findall(text)) for text in _LINK_TEXT.findall(unit))
    return linked < 0.5 * len(said)


def _gaps_filled(doc: Document, extracted: str, least: int) -> str | None:
    """The extraction, with the paragraphs it left out between two it kept.

    The element its text comes from is found (``_region_of``) and written as
    markdown; a block of it the extraction does not hold is put back when it
    lies between two blocks the extraction holds and reads as the text's own
    (``_put_back``), right after the block of the extraction that holds the
    one before it. None when no region is found.
    """
    region = _region_of(doc.tree, extracted)
    if region is None:
        return None
    units = _units(_region_written(region, doc.base, authors=True))
    blocks = extracted.split("\n\n")
    spoken = [" ".join(_words(block)) for block in blocks]
    whole = " ".join(spoken)
    held = [" ".join(_words(unit)) in whole for unit in units]
    kept_at = [i for i, h in enumerate(held) if h]
    if len(kept_at) < 2:
        return None
    after: dict[int, list[str]] = {}
    place = -1
    for i, unit in enumerate(units):
        if held[i]:
            words = " ".join(_words(unit))
            place = next((at for at, text in enumerate(spoken) if words in text), place)
        elif kept_at[0] < i < kept_at[-1] and _put_back(unit, least):
            after.setdefault(place, []).append(unit)
    if not after:
        return extracted
    # Put back before the first block when the block before it is held by the
    # extraction only across two of its blocks.
    out = list(after.get(-1, []))
    for at, block in enumerate(blocks):
        out.append(block)
        out.extend(after.get(at, []))
    return "\n\n".join(out)


# --- the heading ---------------------------------------------------------------------


def _titled_heading(doc: Document, title: str | None) -> str | None:
    """The page's one ``<h1>``, when it is the title the page declares: equal,
    or the shorter within the longer and at least 0.6 of it, lowercase and
    spaces collapsed."""
    if not title:
        return None
    headings = [
        " ".join(h.text_content().split())
        for h in doc.tree.iter("h1")
        if h.text_content().strip()
    ]
    if len(headings) != 1:
        return None
    heading = headings[0]
    a, b = (" ".join(x.lower().split()) for x in (heading, title))
    short, long = sorted((a, b), key=len)
    if a == b or (short in long and len(short) >= 0.6 * len(long)):
        return heading
    return None
