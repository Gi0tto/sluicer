"""Dublin Core in extruct's shape: ``{"namespaces", "elements", "terms"}``.

One object for every page, as extruct answers it: ``namespaces`` from each
``<link rel="schema.X">`` naming one of Dublin Core's two namespaces,
``elements`` and ``terms`` a copy of each ``<meta name>`` or ``<link rel>``
element's attributes with a ``URI`` added. A name among the fifteen elements
is an element, whether it was written ``DC.`` or ``DCTERMS.``, and a refined
term is a term, as extruct files them.

What counts as Dublin Core is not extruct's rule. extruct takes whatever
follows a name's last dot, or the whole name when it has none, so
``<meta name="description">`` is filed as a Dublin Core element, and so are
``name="title"``, ``citation.date`` and ``<link rel="license">``, none of which
Dublin Core claimed; ``description`` alone is on 87% of the WCXB pages. Here a
name is Dublin Core when its first segment is ``DC`` or ``DCTERMS``, in any
case, or a prefix the page declares for one of Dublin Core's namespaces with
``<link rel="schema.X">``: the convention the Dublin Core HTML recommendation
describes. sluicer's own reader keeps that line too, and reads ``<meta
name="description">`` as HTML's own metadata instead.
"""

from __future__ import annotations

import re
from typing import Any

from lxml.html import HtmlElement

from sluicer.compat.extruct.page import Page, of_tree, read_page

_ELEMENTS_NS = "http://purl.org/dc/elements/1.1/"
_TERMS_NS = "http://purl.org/dc/terms/"
_NAMESPACES = (_TERMS_NS, _ELEMENTS_NS)
_SPACE = " \t\n\r\x0c"

# The fifteen elements of the Dublin Core Metadata Element Set 1.1.
_ELEMENTS = {
    name: _ELEMENTS_NS + name
    for name in (
        "contributor",
        "coverage",
        "creator",
        "date",
        "description",
        "format",
        "identifier",
        "language",
        "publisher",
        "relation",
        "rights",
        "source",
        "subject",
        "title",
        "type",
    )
}
# The DCMI terms extruct recognises, looked up by their name in lower case.
_TERMS = {
    name.lower(): _TERMS_NS + name
    for name in (
        "abstract",
        "accessRights",
        "RightsStatement",
        "accrualMethod",
        "Collection",
        "MethodOfAccrual",
        "accrualPeriodicity",
        "Frequency",
        "accrualPolicy",
        "Policy",
        "alternative",
        "audience",
        "AgentClass",
        "available",
        "bibliographicCitation",
        "BibliographicResource",
        "conformsTo",
        "Standard",
        "Agent",
        "LocationPeriodOrJurisdiction",
        "created",
        "dateAccepted",
        "dateCopyrighted",
        "dateSubmitted",
        "educationLevel",
        "extent",
        "SizeOrDuration",
        "MediaTypeOrExtent",
        "hasFormat",
        "hasPart",
        "hasVersion",
        "instructionalMethod",
        "MethodOfInstruction",
        "isFormatOf",
        "isPartOf",
        "isReferencedBy",
        "isReplacedBy",
        "isRequiredBy",
        "issued",
        "isVersionOf",
        "LinguisticSystem",
        "license",
        "LicenseDocument",
        "mediator",
        "medium",
        "PhysicalResource",
        "PhysicalMedium",
        "modified",
        "provenance",
        "ProvenanceStatement",
        "references",
        "replaces",
        "requires",
        "rightsHolder",
        "spatial",
        "Location",
        "tableOfContents",
        "temporal",
        "PeriodOfTime",
        "valid",
    )
}
# The prefixes every page may use without declaring them.
_CONVENTIONAL = frozenset({"dc", "dcterms"})
_SCHEMA = re.compile(r"schema\.")


def local_name(name: str) -> str:
    """What extruct matches a name by: after its last dot, in lower case."""
    return re.sub(r".*\.", "", name).lower()


class DublinCoreExtractor:
    """extruct's Dublin Core extractor, with Dublin Core's own idea of a name."""

    def extract(
        self,
        htmlstring: str | bytes,
        base_url: str | None = None,
        encoding: str = "UTF-8",
    ) -> list[dict[str, Any]]:
        return self.read(read_page(htmlstring, base_url, encoding))

    def extract_items(
        self, document: HtmlElement, base_url: str | None = None
    ) -> list[dict[str, Any]]:
        return self.read(of_tree(document, base_url))

    def read(self, page: Page) -> list[dict[str, Any]]:
        tree = page.tree
        namespaces: dict[str, str] = {}
        prefixes = set(_CONVENTIONAL)
        for link in tree.xpath('//link[contains(@rel,"schema")]'):
            address = (link.get("href") or "").strip(_SPACE)
            if address in _NAMESPACES:
                rel = link.get("rel") or ""
                namespaces[_SCHEMA.sub("", rel)] = address
                prefixes.add(rel.strip().lower().removeprefix("schema."))
        elements: list[dict[str, str]] = []
        terms: list[dict[str, str]] = []
        for element, attribute in [
            *((meta, "name") for meta in tree.xpath("//meta")),
            *((link, "rel") for link in tree.xpath("//link")),
        ]:
            name = element.get(attribute) or ""
            prefix, dot, _rest = name.partition(".")
            if not dot or prefix.strip().lower() not in prefixes:
                continue
            local = local_name(name)
            if local in _ELEMENTS:
                elements.append({**element.attrib, "URI": _ELEMENTS[local]})
            elif local in _TERMS:
                terms.append({**element.attrib, "URI": _TERMS[local]})
        return [{"namespaces": namespaces, "elements": elements, "terms": terms}]
