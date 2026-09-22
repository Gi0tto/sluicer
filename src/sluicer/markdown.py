"""A page's main content, as markdown, with the furniture removed.

Finding the article and leaving the navigation behind is trafilatura's work,
full time; Sluicer hands the page over and passes the result back. It sits
behind the ``markdown`` extra, so a reader who never asks for markdown does not
carry it.
"""

from __future__ import annotations

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


def to_markdown(html: str | bytes, url: str | None = None) -> str:
    """Return the page's main content as markdown, or ``""`` when it has none.

    Args:
        html: the page, passed to trafilatura as given. Prefer bytes: it
            detects the encoding from them, including a ``<meta charset>``.
        url: the address the page came from, used to resolve its links.

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
    return produced or ""
