"""The one call most people will make."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.dublincore import read_dublincore
from sluicer.declared.htmlmeta import read_htmlmeta
from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.merge import ABOUT_A_THING, Record, merge
from sluicer.declared.microdata import read_microdata
from sluicer.declared.microformats import read_microformats
from sluicer.declared.opengraph import read_opengraph
from sluicer.declared.rdfa import read_rdfa
from sluicer.declared.twitter import read_twitter
from sluicer.document import load
from sluicer.structure import induce as induce_records
from sluicer.summary import SummaryField, summarise


@dataclass
class Extraction:
    """What Sluicer found in one page, and where it came from.

    ``url`` is the address given to ``extract``. ``summary`` answers the
    questions most callers ask -- title, author, date, price -- one value each,
    chosen from the records by fixed rules, each naming its reader and key (see
    ``sluicer.summary.FIELDS``). ``records`` is everything the page declared.
    ``sources`` names every reader that found something.
    """

    url: str | None = None
    summary: dict[str, SummaryField] = field(default_factory=dict)
    records: list[Record] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def extract(
    html: str | bytes,
    url: str | None = None,
    induce: bool = False,
    microformats: bool = False,
) -> Extraction:
    """Read the structured data ``html`` declares, merged, with its provenance.

    Args:
        html: the page. Bytes are best: the page's own charset is then honoured
            (see ``sluicer.document.load``).
        url: the address the page came from, used to resolve its links.
        induce: when the page declares nothing about the things on it, also
            read the rows its markup repeats; those fields say
            ``source="induced"``. Never fills a gap in a declared record.
        microformats: also read microformats2. Off by default; needs
            ``sluicer[microformats]``.

    Returns:
        An ``Extraction``: the ``summary``, the ``records`` (a record with no
        field is never reported), and the ``sources`` that found something,
        in the order of precedence -- JSON-LD, microdata, microformats, RDFa,
        Dublin Core, OpenGraph, the Twitter card, HTML's own meta names.

    Raises:
        MicroformatsExtraMissing: ``microformats=True`` without the extra.
        Nothing else: any input, however broken, is read or reported empty.

    Why the order is what it is, and when induction runs, is in
    ``docs/design-notes.md``.
    """
    doc = load(html, url=url)
    jsonld = read_jsonld(doc)
    microdata = read_microdata(doc)
    # Not calling the reader is what keeps mf2py unimported on a base install.
    found_microformats = read_microformats(doc) if microformats else []
    rdfa = read_rdfa(doc)
    dublincore = read_dublincore(doc)
    opengraph = read_opengraph(doc)
    twitter = read_twitter(doc)
    htmlmeta = read_htmlmeta(doc)

    sources = [
        name
        for name, found in (
            ("jsonld", jsonld),
            ("microdata", microdata),
            ("microformats", found_microformats),
            ("rdfa", rdfa),
            ("dublincore", dublincore),
            ("opengraph", opengraph),
            ("twitter", twitter),
            ("html", htmlmeta),
        )
        if found
    ]
    records = merge(
        jsonld=jsonld,
        microdata=microdata,
        microformats=found_microformats,
        rdfa=rdfa,
        dublincore=dublincore,
        opengraph=opengraph,
        twitter=twitter,
        htmlmeta=htmlmeta,
    )
    # A record carrying no field is a type and nothing else -- a ``WebPage``
    # with only an ``@id``, a microformats root that was a CSS class -- and an
    # empty value is not a value, whole records included.
    records = [record for record in records if record.fields]
    summary = summarise(doc, records, dublincore, opengraph, twitter, htmlmeta)
    if induce and not _declared_about_its_things(records):
        induced = induce_records(doc)
        if induced:
            records = [*records, *induced]
            sources = [*sources, "induced"]
    return Extraction(url=url, summary=summary, records=records, sources=sources)


def _declared_about_its_things(records: list[Record]) -> bool:
    """True when a reader produced a field about a thing on the page.

    A field, not a parse: an empty declaration produces a record with nothing in
    it. And a field about a thing: OpenGraph describes the page it sits on, so
    its fields answer "what is this page", never "what is in this list".
    """
    return any(
        field.source in ABOUT_A_THING
        for record in records
        for field in record.fields.values()
    )
