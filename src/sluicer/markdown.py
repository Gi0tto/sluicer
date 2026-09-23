"""A page's main content, as markdown, with the furniture removed.

Finding the article and leaving the navigation behind is trafilatura's work,
full time; Sluicer hands the page over and passes the result back. It sits
behind the ``markdown`` extra, so a reader who never asks for markdown does not
carry it.
"""

from __future__ import annotations

import json
from types import ModuleType

from sluicer.extras import MissingExtra, import_extra


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
    # trafilatura is imported by name, so what it returns is untyped; the
    # annotation states what its ``extract`` documents.
    produced: str | None = _trafilatura().extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        url=url,
    )
    if not produced or not front_matter:
        return produced or ""
    return declared_front_matter(html, url) + produced


def declared_front_matter(html: str | bytes, url: str | None = None) -> str:
    """A YAML front matter block of the page's summary, with each answer's source.

    Every value is written as a JSON string, which is a YAML string, so no
    value a page declares can break the block or be read as YAML syntax. A
    date or price is written normalised where ``Extraction.normalised`` has it,
    and as the page wrote it otherwise. ``""`` when the page answers nothing.
    """
    # Imported here: the summary is the library's heaviest import, and a caller
    # who never asks for front matter should not pay for it.
    from sluicer.api import extract

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
