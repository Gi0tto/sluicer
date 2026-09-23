"""Read what a page declares about how it may be used.

Three mechanisms live in a page's own markup, each with its own standing:

* ``<meta name="robots">``, and the same with a crawler's name in place of
  ``robots`` (``googlebot``, ``bingbot``...): the directives search engines
  document, ``noindex``, ``nofollow``, ``noarchive``, ``nosnippet`` and the
  rest. ``noai`` and ``noimageai`` are read the same way; no search engine
  documents them, but pages write them to object to AI training.
* TDMRep's ``<meta name="tdm-reservation">`` and ``<meta name="tdm-policy">``:
  a W3C Community Group final report of 2024-05-10, written for the text and
  data mining opt-out of the EU's DSM Directive, Article 4. A Community Group
  report is not a W3C standard.

What is reported is what the page says, verbatim and lowercased, never what it
therefore permits: a page that declares nothing is reported as declaring
nothing, which is not the same as allowing everything. Site-level rules --
robots.txt, TDMRep's ``/.well-known/tdmrep.json`` -- are not the page's and are
not read here. The response's headers -- ``X-Robots-Tag``, TDMRep's
``TDM-Reservation`` and ``TDM-Policy`` -- are reported apart, under ``http``,
when the headers were given: the page and its server can disagree, and which
one a reader obeys is its own rule.
"""

from __future__ import annotations

from typing import TypedDict

from sluicer.declared.headers import HeaderRights
from sluicer.document import Document

# Crawler names a page may put in place of ``robots``, as the engines document
# them. A name outside this list is some other meta tag, not a directive.
_CRAWLERS = frozenset(
    {
        "googlebot",
        "googlebot-news",
        "googlebot-image",
        "googlebot-video",
        "google-extended",
        "bingbot",
        "msnbot",
        "slurp",
        "yandex",
        "baiduspider",
        "duckduckbot",
        "applebot",
        "gptbot",
        "ccbot",
    }
)
# The most directives kept per agent: a page is not a policy document, and a
# hostile one should not make the answer grow with it.
_MOST = 50


class Rights(TypedDict, total=False):
    robots: list[str]
    agents: dict[str, list[str]]
    tdm_reservation: str
    tdm_policy: str
    http: HeaderRights


def read_rights(doc: Document, header: HeaderRights | None = None) -> Rights:
    """The usage directives the page's own ``<meta>`` tags declare.

    Directives from several tags for one agent are gathered in order, each
    once. ``tdm_reservation`` is as the page wrote it -- ``1`` reserves the
    rights, ``0`` does not -- and the first tag wins. ``header`` is what the
    response's headers declare (``sluicer.declared.headers.read_header_rights``),
    kept under ``http`` when it says anything.
    """
    found: Rights = {}
    general: list[str] = []
    agents: dict[str, list[str]] = {}
    for meta in doc.tree.xpath("//meta[@name][@content]"):
        name = (meta.get("name") or "").strip().lower()
        content = " ".join((meta.get("content") or "").split())
        if not content:
            continue
        if name == "tdm-reservation":
            found.setdefault("tdm_reservation", content)
        elif name == "tdm-policy":
            found.setdefault("tdm_policy", content)
        elif name == "robots" or name in _CRAWLERS:
            into = general if name == "robots" else agents.setdefault(name, [])
            for directive in content.lower().split(","):
                directive = directive.strip()
                if directive and directive not in into and len(into) < _MOST:
                    into.append(directive)
    if general:
        found["robots"] = general
    if agents:
        found["agents"] = {name: rules for name, rules in agents.items() if rules}
    if header:
        found["http"] = header
    return found
