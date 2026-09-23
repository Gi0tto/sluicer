"""What the page as a whole should say about itself, and does not.

Not rich results: the four things every page is asked for by the standard or
the vocabulary that defines them -- a ``<title>``, a meta description, one
canonical address, and OpenGraph's four basic properties. Each is a warning:
a page lacking one breaks no rule a search engine enforces.
"""

from __future__ import annotations

from sluicer.audit.report import Finding
from sluicer.declared.opengraph import read_opengraph
from sluicer.document import Document, trimmed

_GOOGLE = "https://developers.google.com/search/docs/"
TITLE_RULE = _GOOGLE + "appearance/title-link"
"""'Make sure every page on your site has a title specified in the <title>
element.' Last updated 2025-12-10, read 2026-09-23."""
DESCRIPTION_RULE = _GOOGLE + "appearance/snippet"
"""Google may use the meta description for the snippet."""
CANONICAL_RULE = _GOOGLE + "crawling-indexing/consolidate-duplicate-urls"
"""'Use absolute paths rather than relative paths with the rel="canonical" link
element', and 'Don't specify different URLs as canonical for the same page'."""
OPENGRAPH_RULE = "https://ogp.me/"
"""'The four required properties for every page are: og:title, og:type,
og:image, og:url.'"""

_OPENGRAPH = (
    ("title", ("title",)),
    ("type", ("type",)),
    ("image", ("image", "image:url", "image:secure_url")),
    ("url", ("url",)),
)


def page_findings(doc: Document) -> list[Finding]:
    """The page-level findings for ``doc``, in a fixed order."""
    found: list[Finding] = []
    titles = [
        " ".join(element.text_content().split())
        for element in doc.tree.xpath("//title")
    ]
    if not any(titles):
        found.append(
            _warning("missing-title", "the page has no <title>", "html", TITLE_RULE)
        )
    descriptions = [
        (meta.get("content") or "").strip()
        for meta in doc.tree.xpath("//meta[@name]")
        if (meta.get("name") or "").strip().lower() == "description"
    ]
    if not any(descriptions):
        found.append(
            _warning(
                "missing-description",
                'the page has no <meta name="description">',
                "html",
                DESCRIPTION_RULE,
            )
        )
    found.extend(_canonical(doc))
    opengraph = read_opengraph(doc)
    for name, keys in _OPENGRAPH:
        if not any(opengraph.get(key) for key in keys):
            found.append(
                _warning(
                    "missing-opengraph",
                    f"og:{name} is absent; OpenGraph requires it on every page",
                    "opengraph",
                    OPENGRAPH_RULE,
                    path=f"og:{name}",
                )
            )
    return found


def _canonical(doc: Document) -> list[Finding]:
    declared = [
        trimmed(link.get("href"))
        for link in doc.tree.xpath("//link[@rel][@href]")
        if "canonical" in (link.get("rel") or "").lower().split()
    ]
    declared = [href for href in declared if href]
    if not declared:
        return [
            _warning(
                "missing-canonical",
                'the page has no <link rel="canonical">',
                "html",
                CANONICAL_RULE,
            )
        ]
    found: list[Finding] = []
    distinct = list(dict.fromkeys(declared))
    if len(distinct) > 1:
        found.append(
            _warning(
                "canonicals-disagree",
                f"the page names {len(distinct)} different canonical addresses: "
                + ", ".join(distinct),
                "html",
                CANONICAL_RULE,
                value=distinct[1],
            )
        )
    for href in distinct:
        if not href.lower().startswith(("http://", "https://")):
            found.append(
                _warning(
                    "canonical-relative",
                    f"the canonical address {href} is relative; Google advises "
                    "absolute ones",
                    "html",
                    CANONICAL_RULE,
                    value=href,
                )
            )
    return found


def _warning(
    code: str,
    message: str,
    source: str,
    rule: str,
    path: str = "",
    value: str | None = None,
) -> Finding:
    return Finding(
        severity="warning",
        code=code,
        message=message,
        source=source,
        path=path,
        value=value,
        rule=rule,
    )
