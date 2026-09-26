"""A page's main content, as markdown, with the furniture removed.

Finding the article and leaving the navigation behind is trafilatura's work,
full time; Sluicer hands the page over and passes the result back. It is in
the base install since 0.10, imported when a page is first turned into
markdown, so ``import sluicer`` does not pay for it.
"""

from __future__ import annotations

import json
import re
from types import ModuleType

from sluicer.document import _base_of, join, trimmed
from sluicer.extras import MissingExtra, import_extra


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


def to_markdown(
    html: str | bytes, url: str | None = None, front_matter: bool = False
) -> str:
    """Return the page's main content as markdown, or ``""`` when it has none.

    Args:
        html: the page, passed to trafilatura as given. Prefer bytes: it
            detects the encoding from them, including a ``<meta charset>``.
        url: the address the page came from, used to resolve its links.
        front_matter: open the markdown with a YAML block of what the page
            declares about itself -- title, author, dates, url, and the rest of
            the summary -- and where each answer came from, the way static-site
            generators and retrieval pipelines read a document's metadata. The
            text itself is still trafilatura's.

    Raises:
        MarkdownExtraMissing: trafilatura is not installed.
    """
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
    if not produced or not front_matter:
        return produced or ""
    return declared_front_matter(html, url) + produced


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
        anchor.set("href", join(base, href))
    return tree


def _may_declare_a_base(html: str | bytes) -> bool:
    """Whether the page has a ``<base`` tag in it anywhere, cheaply."""
    if isinstance(html, bytes):
        return re.search(rb"<base\b", html, re.IGNORECASE) is not None
    return re.search(r"<base\b", html, re.IGNORECASE) is not None


def declared_front_matter(html: str | bytes, url: str | None = None) -> str:
    """A YAML front matter block of the page's summary, with each answer's source.

    Every value is written as a JSON string, which is a YAML string, so no
    value a page declares can break the block or be read as YAML syntax. A
    date or price is written normalised where ``Extraction.normalised`` has it,
    and as the page wrote it otherwise. ``""`` when the page answers nothing.
    """
    # Imported here: the summary is the library's heaviest import, and a caller
    # who never asks for front matter should not pay for it.
    from sluicer.api import _extract as extract

    result = extract(html, url=url)
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
    lines.append("---")
    return "\n".join(lines) + "\n\n"
