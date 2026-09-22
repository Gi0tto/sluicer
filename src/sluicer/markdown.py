"""A page's main content, as markdown, with the furniture removed.

Pulling the article out of a page and leaving the navigation behind is its own
problem, and `trafilatura` works on it full time. Sluicer does not reimplement
it; it hands the page over and passes the result back. The dependency is
optional because the base install reads structured data, and a reader who never
asks for markdown should not carry the tree that produces it.
"""

from __future__ import annotations


class MarkdownExtraMissing(ImportError):
    """The optional markdown extra is not installed.

    This means the package is absent, not that something inside a working
    installation failed to import. A broken install is a bug and must surface
    as one.
    """


_MISSING = (
    "Turning a page into markdown needs trafilatura, which is not installed. "
    "Install it with: uv pip install 'sluicer[markdown]'"
)


def _trafilatura():
    """Import trafilatura, or say the extra is not installed.

    Only a genuinely absent package raises ``MarkdownExtraMissing``: a
    ``ModuleNotFoundError`` whose ``.name`` is exactly ``"trafilatura"``.
    Anything else -- a plain ``ImportError`` raised from inside a working
    install, or a ``ModuleNotFoundError`` naming some other module -- is a
    broken install, and telling that user to install what is already there
    hides the bug. So it is re-raised untouched. This mirrors ``_fetchers()``
    in ``sluicer/fetch/scrapling_rungs.py``.
    """
    try:
        import trafilatura
    except ModuleNotFoundError as missing:
        if missing.name == "trafilatura":
            raise MarkdownExtraMissing(_MISSING) from missing
        raise
    return trafilatura


def to_markdown(html: str | bytes, url: str | None = None) -> str:
    """Return the page's main content as markdown, or an empty string.

    An empty string means the page had no main content to give. That is a fact
    about the page rather than a failure, and the caller decides what it means.

    ``html`` is passed to trafilatura exactly as given, whether ``str`` or
    ``bytes``. trafilatura does its own encoding detection from the bytes
    themselves, including a declared ``<meta charset>``, which a forced UTF-8
    decode here would only get wrong for non-UTF-8 pages.
    """
    produced = _trafilatura().extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        url=url,
    )
    return produced or ""
