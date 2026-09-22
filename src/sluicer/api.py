"""The one call most people will make."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.merge import Record, merge
from sluicer.declared.microdata import read_microdata
from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load
from sluicer.induce import induce as induce_records


@dataclass
class Extraction:
    """What Sluicer found in one page, and where it came from."""

    url: str | None = None
    records: list[Record] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def extract(
    html: str | bytes, url: str | None = None, induce: bool = False
) -> Extraction:
    """Read every kind of declared data in ``html`` and merge it.

    ``induce`` is off by default and stays off for any page that declared
    something. Declared data is what a page says about itself; induced data is
    what we noticed about its markup, and the two are not the same kind of
    claim. So induction runs only when asked and only when no reader fired at
    all, it never fills a gap in a declared record, and every field it produces
    carries ``source="induced"`` so the two can never be confused.
    """
    doc = load(html, url=url)
    jsonld = read_jsonld(doc)
    microdata = read_microdata(doc)
    opengraph = read_opengraph(doc)

    sources = [
        name
        for name, found in (
            ("jsonld", jsonld),
            ("microdata", microdata),
            ("opengraph", opengraph),
        )
        if found
    ]
    records = merge(jsonld=jsonld, microdata=microdata, opengraph=opengraph)
    if induce and not sources:
        # ``sources`` is empty exactly when no reader found anything, which is
        # the only case where a page has told us nothing to respect.
        induced = induce_records(doc)
        records = induced or records
        sources = ["induced"] if induced else sources
    return Extraction(url=url, records=records, sources=sources)
