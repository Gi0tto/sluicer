"""A page's main content, as markdown, with the furniture removed.

Finding the article and leaving the navigation behind is trafilatura's work,
full time; Sluicer hands the page over, its links resolved, and passes the
result back. It is in the base install since 0.10, imported when a page is
first turned into markdown, so ``import sluicer`` does not pay for it.
``full=True`` writes the whole page instead, menus and footers included
(``sluicer.markdown_writer``), and needs only lxml. ``read_markdown`` says
which of the two the text is.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from types import ModuleType
from urllib.parse import quote

from sluicer.document import _base_of, join, let_go, load_kept, trimmed
from sluicer.extras import MissingExtra, import_extra
from sluicer.markdown_writer import element_markdown


class MarkdownExtraMissing(MissingExtra):
    """trafilatura, which the base install brings, is not installed here.

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

    ``source`` is ``"extracted"`` for the main content, found in the page by
    ``method`` (``"trafilatura"``); ``"page"`` for the whole page (``full``),
    with no method; ``""`` when there is no text. ``where`` is the place on the
    page the text was declared, for a source that names one; neither of these
    does, so it is None.
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
        html: the page, passed to trafilatura as given. Prefer bytes: it
            detects the encoding from them, including a ``<meta charset>``.
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
    # trafilatura parses the page its own way (comments dropped, the
    # encoding its own guess), so a page a fetch kept parsed is of no use to
    # it: let go here, the kept tree would otherwise stay as long as the
    # thread.
    let_go()
    trafilatura = _trafilatura()
    # trafilatura is imported by name, so what it returns is untyped; the
    # annotation states what its ``extract`` documents.
    produced: str | None = trafilatura.extract(
        _with_links_resolved(trafilatura, html, url),
        output_format="markdown",
        include_links=True,
        include_tables=True,
        url=url,
    )
    if not produced:
        return MainText("", "", "")
    return MainText(produced, "extracted", "trafilatura")


def _full_markdown(html: str | bytes, url: str | None) -> str:
    """The whole page's body as markdown, as a reader running no script is
    shown it: the tree a fetch of this very page kept, when it kept one,
    which is then let go."""
    doc = load_kept(html, url=url)
    body = doc.tree.find("body")
    return element_markdown(
        body if body is not None else doc.tree, doc.base, noscript=True
    )


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
    also says where it came from. ``""`` when the page answers nothing.
    """
    # Imported here: the summary is the library's heaviest import, and a caller
    # who never asks for front matter should not pay for it.
    from sluicer.api import _extract as extract

    result = extract(html, url=url, visible=False)
    if not result.summary:
        return ""
    lines = ["---"]
    for question, answer in result.summary.items():
        value = result.normalised.get(question, answer.value)
        lines.append(f"{question}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("sources:")
    for question, answer in result.summary.items():
        said = f"{answer.source} {answer.key}"
        lines.append(f"  {question}: {json.dumps(said, ensure_ascii=False)}")
    if text is not None and text.source:
        said = f"{text.source} {text.method}".strip()
        lines.append(f"  text: {json.dumps(said, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"
