"""Hold what a page declares to what the documentation asks of it.

``audit`` is the one call. It reads every record JSON-LD, microdata and RDFa
declare and says which of Google's rich-result features each is documented
for, which required and recommended properties it lacks, and which of its
values are in a form the documentation or schema.org refuses; then what the
page as a whole lacks, where two vocabularies contradict each other, and,
given what the site serves beside the page, which AI agents its robots.txt
admits and whether its llms.txt keeps to llmstxt.org's format.

Every rule names the page it comes from. No model reads anything and no clock
is consulted, so the same page always gets the same audit. What Google's own
validator decides is not known to anyone outside Google; this checks what its
documentation says.

The package is not re-exported from ``sluicer`` as a function: ``sluicer.audit``
is this package, and a function of the same name would shadow it.
"""

from __future__ import annotations

from typing import Any

from sluicer.api import Extraction
from sluicer.audit import crawlers, llmstxt, records
from sluicer.audit.page import page_findings
from sluicer.audit.report import (
    Audit,
    CrawlerVerdict,
    FeatureVerdict,
    Finding,
    LlmsSection,
    LlmsTxt,
    RecordAudit,
    Site,
    SiteFile,
)
from sluicer.declared.jsonld import Terms
from sluicer.declared.readers import BY_NAME
from sluicer.declared.rights import read_rights
from sluicer.declared.tdmrep import read_tdmrep, reservation
from sluicer.document import Document, load

__all__ = [
    "Audit",
    "CrawlerVerdict",
    "FeatureVerdict",
    "Finding",
    "LlmsSection",
    "LlmsTxt",
    "RecordAudit",
    "Site",
    "SiteFile",
    "answered_with",
    "audit",
]


def audit(
    page: str | bytes | Extraction,
    url: str | None = None,
    site: Site | None = None,
) -> Audit:
    """Audit what ``page`` declares against what its documentation asks.

    Args:
        page: the HTML -- bytes are best, as for ``extract`` -- or an
            ``Extraction`` already made. An ``Extraction`` holds the merged
            records and not the page, so its records are audited as merged,
            each finding naming the reader of the property it is about, and the
            checks that need the page itself are listed in ``not_checked``.
        url: the address the page came from.
        site: what the site serves beside the page, as
            ``sluicer.fetch.site.read_site`` reads it; without it the AI
            agents and llms.txt are not checked, and ``not_checked`` says so.

    Returns:
        An ``Audit``. Nothing is fetched here: ``site`` is read by the caller.

    Raises:
        ValueError: ``site`` without ``url``: which page the agents may have is
            a question about an address.
    """
    if site is not None and url is None:
        raise ValueError("auditing what a site serves needs the page's address")
    result = Audit(url=url if url is not None else _url_of(page))
    if isinstance(page, Extraction):
        result.records = _merged(page)
        result.not_checked.append(
            "The page itself -- its title, description, canonical and OpenGraph -- "
            "and conflicts between vocabularies: an Extraction holds the merged "
            "records, not the page."
        )
    else:
        doc = load(page, url=url)
        found = {name: _normalised(name, doc) for name in records.AUDITED_READERS}
        defined = {name: records.definitions(nodes) for name, nodes in found.items()}
        known_base = doc.base is not None
        for name, nodes in found.items():
            own = frozenset(
                node["@id"] for node in nodes if isinstance(node.get("@id"), str)
            )
            result.records.extend(
                records.audit_record(
                    name, index, node, defined[name], own, check_urls=known_base
                )
                for index, node in enumerate(nodes)
            )
        if not known_base and (found["microdata"] or found["rdfa"]):
            result.not_checked.append(
                "Whether microdata and RDFa URLs are absolute: those readers "
                "resolve links against the page's address, which was not given."
            )
        result.page = [*page_findings(doc), *records.conflicts(found)]
    if site is None or url is None:
        result.not_checked.append(
            "The AI agents robots.txt admits, and llms.txt: the site was not read."
        )
    else:
        _site(result, url, site)
    rules = read_tdmrep(site.tdmrep.text) if site and site.tdmrep else []
    if isinstance(page, Extraction):
        rights = page.rights
    else:
        rights = read_rights(load(page, url=url))
    result.tdm = reservation(rules, url, rights)
    findings = result.findings()
    result.errors = sum(1 for finding in findings if finding.severity == "error")
    result.warnings = sum(1 for finding in findings if finding.severity == "warning")
    result.notes = sum(1 for finding in findings if finding.severity == "info")
    return result


def answered_with(status: int) -> str:
    """The sentence an audit of a page that answered ``status`` carries.

    A fetch that climbed as far as it could returns what the site answered, a
    403 or a 404 included; the audit of that answer is not the audit of the
    page asked for, and says so first.
    """
    return (
        f"The page asked for: the site answered status {status}, and what is "
        "audited is that answer."
    )


def _normalised(name: str, doc: Document) -> list[dict[str, Any]]:
    """What reader ``name`` declares on the page, each item as the audit reads
    it: JSON-LD's words named through their context, as the records name them."""
    terms = Terms() if name == "jsonld" else None
    return [
        node
        for item in BY_NAME[name].read(doc)
        if isinstance(node := records.normalise(item, terms=terms), dict)
    ]


def _url_of(page: str | bytes | Extraction) -> str | None:
    return page.url if isinstance(page, Extraction) else None


def _merged(extraction: Extraction) -> list[RecordAudit]:
    audited: list[RecordAudit] = []
    counted: dict[str, int] = {}
    for record in extraction.records:
        if record.source not in records.AUDITED_READERS:
            continue
        kept = {
            key: found
            for key, found in record.fields.items()
            if found.source in records.AUDITED_READERS
        }
        node: dict[str, Any] = {"@type": list(record.types)} if record.types else {}
        node.update({key: found.value for key, found in kept.items()})
        index = counted.get(record.source, 0)
        counted[record.source] = index + 1
        audited.append(
            records.audit_record(
                record.source,
                index,
                node,
                {},
                frozenset(),
                check_urls=extraction.url is not None,
                field_sources={key: found.source for key, found in kept.items()},
            )
        )
    return audited


def _site(result: Audit, url: str, site: Site) -> None:
    result.crawlers, result.other_agents = crawlers.verdicts(url, site.robots)
    result.robots_txt = SiteFile(
        url=site.robots.url, status=site.robots.status, error=site.robots.error
    )
    result.llms_txt = llmstxt.read_llms_txt(site.llms_txt)
    result.llms_full_txt = llmstxt.read_llms_full_txt(site.llms_full_txt)
