"""The one call most people will make."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.merge import Record, merge
from sluicer.declared.microdata import read_microdata
from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load


@dataclass
class Extraction:
    """What Sluicer found in one page, and where it came from."""

    url: str | None = None
    records: list[Record] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def extract(html: str | bytes, url: str | None = None) -> Extraction:
    """Read every kind of declared data in ``html`` and merge it."""
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
    return Extraction(
        url=url,
        records=merge(jsonld=jsonld, microdata=microdata, opengraph=opengraph),
        sources=sources,
    )
