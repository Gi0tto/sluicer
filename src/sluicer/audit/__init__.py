"""Hold what a page declares to what the documentation asks of it.

``audit`` is the one call. It reads every record JSON-LD, microdata and RDFa
declare and says which of Google's rich-result features each is documented
for, which required and recommended properties it lacks, and which of its
values are in a form the documentation or schema.org refuses; then what the
page as a whole lacks, and where two vocabularies contradict each other.

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
from sluicer.audit import records
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
from sluicer.declared.readers import BY_NAME
from sluicer.document import load

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
    "audit",
]


def audit(page: str | bytes | Extraction, url: str | None = None) -> Audit:
    """Audit what ``page`` declares against what its documentation asks.

    Args:
        page: the HTML -- bytes are best, as for ``extract`` -- or an
            ``Extraction`` already made. An ``Extraction`` holds the merged
            records and not the page, so its records are audited as merged,
            each finding naming the reader of the property it is about, and the
            checks that need the page itself are listed in ``not_checked``.
        url: the address the page came from.

    Returns:
        An ``Audit``. Nothing is fetched here.
    """
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
        found = {
            name: [
                node
                for item in BY_NAME[name].read(doc)
                if isinstance(node := records.normalise(item), dict)
            ]
            for name in records.AUDITED_READERS
        }
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
    findings = result.findings()
    result.errors = sum(1 for finding in findings if finding.severity == "error")
    result.warnings = sum(1 for finding in findings if finding.severity == "warning")
    result.notes = sum(1 for finding in findings if finding.severity == "info")
    return result


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
