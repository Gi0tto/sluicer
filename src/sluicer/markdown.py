"""A page's main content, as markdown, with the furniture removed.

Pulling the article out of a page and leaving the navigation behind is its own
problem, and `trafilatura` works on it full time. Sluicer does not reimplement
it; it hands the page over and passes the result back. The dependency is
optional because the base install reads structured data, and a reader who never
asks for markdown should not carry the tree that produces it.
"""

from __future__ import annotations

from types import ModuleType

from sluicer.extras import MissingExtra, import_extra


class MarkdownExtraMissing(MissingExtra):
    """The optional ``markdown`` extra (trafilatura) is not installed.

    A name of its own, so ``sluicer.cli`` can catch exactly this and print the
    install line instead of a traceback. What "missing" means, and why a broken
    install keeps its traceback instead, is stated once in ``sluicer.extras``.
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
    """Return the page's main content as markdown, or an empty string.

    An empty string means the page had no main content to give. That is a fact
    about the page rather than a failure, and the caller decides what it means.

    ``html`` is passed to trafilatura exactly as given, whether ``str`` or
    ``bytes``. trafilatura does its own encoding detection from the bytes
    themselves, including a declared ``<meta charset>``, which a forced UTF-8
    decode here would only get wrong for non-UTF-8 pages.
    """
    # Annotated on the way in, not asserted on the way out: trafilatura is an
    # optional extra imported by name, so everything it returns is untyped.
    # ``str | None`` is what its ``extract`` documents and what this function
    # is written against, and saying so here is what makes the ``-> str``
    # below something a checker can hold us to.
    produced: str | None = _trafilatura().extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        url=url,
    )
    return produced or ""
