"""Any part of a page written as markdown, by lxml alone.

``sluicer.markdown`` hands the finding of a page's main text to trafilatura;
this module writes markdown from an element Sluicer already holds: the whole
page, for ``to_markdown(full=True)``, and the element a page declares as its
article's body. It needs nothing beyond lxml, so it is part of the base
install.

What it writes: headings, paragraphs, lists (nested, numbered from where an
``<ol start>`` says), block quotes, code blocks and inline code, emphasis,
links and images resolved against the page, tables whose cells hold only
text, and a horizontal rule. What it leaves out: scripts, styles and the rest
a reader never sees (``_UNSEEN``), form controls, and anything ``hidden``.
The same element always gives the same markdown.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import lxml.etree
import lxml.html

from sluicer.document import join, trimmed

# Never shown to a reader, or not text: left out with everything inside.
_UNSEEN = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "math",
        "iframe",
        "object",
        "embed",
        "canvas",
        "head",
        "title",
        "meta",
        "link",
        "base",
        "input",
        "select",
        "option",
        "optgroup",
        "datalist",
        "textarea",
        "button",
        "audio",
        "video",
        "source",
        "track",
        "map",
        "area",
        "dialog",
    }
)
# Elements that start a block of their own.
_BLOCKS = frozenset(
    {
        "address",
        "article",
        "aside",
        "body",
        "caption",
        "center",
        "dd",
        "details",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "header",
        "hgroup",
        "html",
        "legend",
        "main",
        "nav",
        "p",
        "section",
        "summary",
        "tbody",
        "tfoot",
        "thead",
        "tr",
        "td",
        "th",
        "li",
        "ul",
        "ol",
        "menu",
        "blockquote",
        "pre",
        "table",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)
_HEADINGS = {f"h{level}": level for level in range(1, 7)}
_STRONG = frozenset({"strong", "b"})
_EMPHASIS = frozenset({"em", "i", "cite", "dfn"})
_CODE = frozenset({"code", "kbd", "samp", "tt"})
_SPACES = re.compile(r"[ \t\n\r\f\v]+")
_WORD = re.compile(r"\w+")
# A hard line break, kept through the collapsing of spaces as one character a
# page cannot write: a private-use code point.
_BREAK = ""
# Characters that mean markdown syntax wherever they are.
_ESCAPED = re.compile(r"([\\`*\[\]])")
# An underscore that could open or close emphasis: not between two letters.
_UNDERSCORE = re.compile(r"(?<![0-9A-Za-z])_|_(?![0-9A-Za-z])")
# What a line may open with that markdown would read as a block's mark.
_LINE_MARK = re.compile(r"^(\s*)(#{1,6}(?=\s|$)|[>+=-])")
_NUMBERED = re.compile(r"^(\s*\d{1,9})([.)])(?=\s|$)")
_NOT_LINKS = ("javascript:", "vbscript:", "data:")


def _escaped(text: str) -> str:
    return _UNDERSCORE.sub(r"\\_", _ESCAPED.sub(r"\\\1", text))


def _hidden(element: lxml.html.HtmlElement) -> bool:
    if element.get("hidden") is not None:
        return True
    style = (element.get("style") or "").replace(" ", "").lower()
    return "display:none" in style or "visibility:hidden" in style


def _tag(element: object) -> str | None:
    """An element's tag, lowercase, or None for a comment or an instruction."""
    tag = getattr(element, "tag", None)
    return tag.lower() if isinstance(tag, str) else None


class _Writer:
    def __init__(self, base: str | None, images: bool, noscript: bool) -> None:
        self.base = base
        self.images = images
        self.noscript = noscript

    def shown(self, element: lxml.html.HtmlElement, tag: str | None) -> bool:
        """Whether a reader is shown the element: a ``<noscript>`` only when
        the writer reads as a reader who runs no script."""
        if tag is None or _hidden(element):
            return False
        if tag == "noscript":
            return self.noscript
        return tag not in _UNSEEN

    def without_images(self) -> _Writer:
        return _Writer(self.base, False, self.noscript)

    # --- inline ---------------------------------------------------------------

    def inline(self, element: lxml.html.HtmlElement) -> str:
        """The element's content as one line of inline markdown, spaces not yet
        collapsed."""
        parts: list[str] = []
        if element.text:
            parts.append(_escaped(element.text))
        for child in element:
            parts.append(self.inline_element(child))
            if child.tail:
                parts.append(_escaped(child.tail))
        return "".join(parts)

    def inline_element(self, element: lxml.html.HtmlElement) -> str:
        tag = _tag(element)
        if not self.shown(element, tag):
            return ""
        if tag == "noscript":
            # What it holds is shown, but not its images: in a page, they are
            # tracking pixels far more often than pictures.
            return self.without_images().inline(element)
        if tag == "br":
            return _BREAK
        if tag == "img":
            return self.image(element)
        if tag in _CODE:
            return _code(element.text_content())
        inner = self.inline(element)
        if tag == "a":
            return self.link(element, inner)
        if tag in _STRONG or tag in _EMPHASIS:
            mark = "**" if tag in _STRONG else "*"
            words = _SPACES.sub(" ", inner)
            core = words.strip()
            if not core or _BREAK in core:
                return inner
            lead = " " if words.startswith(" ") else ""
            trail = " " if words.endswith(" ") else ""
            return f"{lead}{mark}{core}{mark}{trail}"
        if tag in _BLOCKS:
            # A block inside a line (a <div> inside a link): its words, set
            # apart by spaces.
            return f" {inner} "
        return inner

    def address(self, element: lxml.html.HtmlElement, attribute: str) -> str | None:
        value = trimmed(element.get(attribute))
        if not value or value.lower().startswith(_NOT_LINKS):
            return None
        resolved = join(self.base, value)
        if re.search(r"[\s()<>]", resolved):
            return f"<{resolved.replace('>', '%3E').replace('<', '%3C')}>"
        return resolved

    def link(self, element: lxml.html.HtmlElement, inner: str) -> str:
        text = _SPACES.sub(" ", inner).strip()
        href = self.address(element, "href")
        # A link to a script, or with no words to show, keeps its words alone.
        # A link within the page resolves against it, as the main text's do.
        if not text or href is None:
            return inner
        return f"[{text.replace(_BREAK, ' ')}]({href})"

    def image(self, element: lxml.html.HtmlElement) -> str:
        if not self.images:
            return ""
        src = self.address(element, "src")
        if src is None:
            return ""
        alt = _escaped(_SPACES.sub(" ", element.get("alt") or "").strip())
        return f"![{alt}]({src})"

    # --- blocks ---------------------------------------------------------------

    def blocks(self, element: lxml.html.HtmlElement) -> list[str]:
        """The element's content as markdown blocks."""
        found: list[str] = []
        line: list[str] = []

        def flush() -> None:
            text = _paragraph("".join(line))
            if text:
                found.append(text)
            line.clear()

        if element.text:
            line.append(_escaped(element.text))
        for child in element:
            tag = _tag(child)
            if tag == "noscript" and self.shown(child, tag):
                flush()
                found.extend(self.without_images().blocks(child))
            elif tag is not None and tag in _BLOCKS and not _hidden(child):
                flush()
                found.extend(self.block(child, tag))
            else:
                line.append(self.inline_element(child))
            if child.tail:
                line.append(_escaped(child.tail))
        flush()
        return found

    def block(self, element: lxml.html.HtmlElement, tag: str) -> list[str]:
        if tag in _HEADINGS:
            text = _one_line(self.inline(element))
            return [f"{'#' * _HEADINGS[tag]} {text}"] if text else []
        if tag == "hr":
            return ["---"]
        if tag == "pre":
            return _fenced(element)
        if tag in ("ul", "ol", "menu"):
            return self.listing(element, ordered=tag == "ol")
        if tag == "blockquote":
            inner = "\n\n".join(self.blocks(element))
            if not inner:
                return []
            return ["\n".join(f"> {row}" if row else ">" for row in inner.split("\n"))]
        if tag == "table":
            return self.table(element)
        return self.blocks(element)

    def listing(self, element: lxml.html.HtmlElement, ordered: bool) -> list[str]:
        items: list[str] = []
        try:
            number = int(element.get("start") or 1)
        except ValueError:
            number = 1
        loose: list[lxml.html.HtmlElement] = []
        for child in element:
            tag = _tag(child)
            if tag is None or tag in _UNSEEN or _hidden(child):
                continue
            if tag != "li":
                loose.append(child)
                continue
            content = "\n".join(self.blocks(child))
            if not content:
                continue
            mark = f"{number}. " if ordered else "- "
            number += 1
            indent = " " * len(mark)
            rows = content.split("\n")
            items.append(
                "\n".join(
                    [
                        mark + rows[0],
                        *(indent + row if row else row for row in rows[1:]),
                    ]
                )
            )
        if not items:
            # A list whose items are not <li>: its content, as blocks.
            return [block for child in loose for block in self.blocks(child)]
        return ["\n".join(items)]

    def table(self, element: lxml.html.HtmlElement) -> list[str]:
        rows = [
            row
            for row in element.iter("tr")
            if _nearest_table(row) is element and not _hidden(row)
        ]
        if not rows or not _holds_data(element, rows):
            # A table that lays out the page, not one that holds data: its
            # cells' content, in order, as blocks.
            return [
                block
                for row in rows
                for cell in row
                if _tag(cell) in ("td", "th")
                for block in self.blocks(cell)
            ] or self.blocks(element)
        grid: list[list[str]] = []
        for row in rows:
            cells: list[str] = []
            for cell in row:
                if _tag(cell) not in ("td", "th"):
                    continue
                text = _one_line(self.inline(cell)).replace("|", "\\|")
                cells.append(text)
                try:
                    span = min(int(cell.get("colspan") or 1), 50)
                except ValueError:
                    span = 1
                cells.extend([""] * (span - 1))
            if any(cells):
                grid.append(cells)
        if not grid:
            return []
        width = max(len(cells) for cells in grid)
        lines = [
            "| " + " | ".join(cells + [""] * (width - len(cells))) + " |"
            for cells in grid
        ]
        lines.insert(1, "|" + "---|" * width)
        caption = element.find("caption")
        head = [_one_line(self.inline(caption))] if caption is not None else []
        return [text for text in head if text] + ["\n".join(lines)]


def _nearest_table(element: lxml.html.HtmlElement) -> lxml.html.HtmlElement | None:
    parent = element.getparent()
    while parent is not None and _tag(parent) != "table":
        parent = parent.getparent()
    return parent


def _holds_data(
    table: lxml.html.HtmlElement, rows: list[lxml.html.HtmlElement]
) -> bool:
    """Whether a table holds data: no table inside it, no cell holding a block
    other than a paragraph, and a row of two cells or more."""
    if any(_tag(inner) == "table" for inner in table.iterdescendants()):
        return False
    widest = 0
    for row in rows:
        cells = [cell for cell in row if _tag(cell) in ("td", "th")]
        widest = max(widest, len(cells))
        for cell in cells:
            for inner in cell.iterdescendants():
                tag = _tag(inner)
                if tag in _BLOCKS and tag != "p":
                    return False
    return widest >= 2


def _paragraph(text: str) -> str:
    """A run of inline markdown as a paragraph: spaces collapsed, ends trimmed,
    a line that opens with a block's mark escaped."""
    collapsed = _SPACES.sub(" ", text)
    rows = [row.strip() for row in collapsed.split(_BREAK)]
    while rows and not rows[-1]:
        rows.pop()
    while rows and not rows[0]:
        rows.pop(0)
    return "\\\n".join(_unmarked(row) for row in rows)


def _unmarked(row: str) -> str:
    """A line with the mark it opens with escaped, so it stays text."""
    return _NUMBERED.sub(r"\1\\\2", _LINE_MARK.sub(r"\1\\\2", row))


def _one_line(text: str) -> str:
    return _SPACES.sub(" ", text.replace(_BREAK, " ")).strip()


def _code(text: str) -> str:
    text = _SPACES.sub(" ", text).strip()
    if not text:
        return ""
    fence = "`"
    while fence in text:
        fence += "`"
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _fenced(element: lxml.html.HtmlElement) -> list[str]:
    text = "".join(_seen_text(element)).strip("\n")
    if not text.strip():
        return []
    language = ""
    for owner in (element, *element.iter("code")):
        for name in (owner.get("class") or "").split():
            if name.startswith(("language-", "lang-")):
                language = name.split("-", 1)[1]
                break
        if language:
            break
    fence = "```"
    while fence in text:
        fence += "`"
    return [f"{fence}{language}\n{text}\n{fence}"]


def _seen_text(element: lxml.html.HtmlElement) -> Iterable[str]:
    """An element's text as written, spaces kept, without what is never seen."""
    if element.text:
        yield element.text
    for child in element:
        tag = _tag(child)
        if tag == "br":
            yield "\n"
        elif tag is not None and tag not in _UNSEEN and not _hidden(child):
            yield from _seen_text(child)
        if child.tail:
            yield child.tail


def shown_words(
    element: lxml.html.HtmlElement,
) -> list[tuple[str, lxml.html.HtmlElement]]:
    """Every word of an element a reader is shown, lowercase, each with the
    element whose own text holds it, in the page's order."""
    found: list[tuple[str, lxml.html.HtmlElement]] = []

    def walk(node: lxml.html.HtmlElement) -> None:
        if node.text:
            found.extend((w, node) for w in _WORD.findall(node.text.lower()))
        for child in node:
            tag = _tag(child)
            if tag is not None and tag not in _UNSEEN and not _hidden(child):
                walk(child)
            if child.tail:
                found.extend((w, node) for w in _WORD.findall(child.tail.lower()))

    walk(element)
    return found


def element_markdown(
    element: lxml.html.HtmlElement,
    base: str | None = None,
    images: bool = True,
    noscript: bool = False,
) -> str:
    """An element and everything in it, as markdown; ``""`` when it shows no
    text.

    Args:
        element: an lxml element, a whole page or any part of one.
        base: what its links and images resolve against, or None to keep
            them as written.
        images: write each ``<img>`` as ``![alt](src)``.
        noscript: write what a ``<noscript>`` holds, as a reader who runs no
            script is shown it, its images aside.
    """
    writer = _Writer(base, images, noscript)
    tag = _tag(element)
    if not writer.shown(element, tag):
        return ""
    found = writer.block(element, tag) if tag in _BLOCKS else writer.blocks(element)
    return "\n\n".join(found)


def fragment_markdown(html: str, base: str | None = None) -> str:
    """A piece of HTML, such as an ``articleBody`` written with tags, as
    markdown."""
    try:
        holder = lxml.html.fragment_fromstring(html, create_parent="div")
    except (lxml.etree.LxmlError, ValueError):
        return ""
    return element_markdown(holder, base)


def text_markdown(text: str) -> str:
    """Plain text, such as an ``articleBody`` written without tags, as
    markdown: a paragraph per line, markdown's characters escaped."""
    rows = [_SPACES.sub(" ", row).strip() for row in text.splitlines()]
    return "\n\n".join(_paragraph(_escaped(row)) for row in rows if row)
