"""The one call most people will make."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from sluicer.declared.headers import (
    charset,
    lowered,
    read_header_links,
    read_header_rights,
)
from sluicer.declared.links import Links, read_links
from sluicer.declared.located import Places
from sluicer.declared.merge import ABOUT_A_THING, Record, merge
from sluicer.declared.opengraph import read_opengraph
from sluicer.declared.readers import READERS
from sluicer.declared.rights import Rights, read_rights
from sluicer.document import Document, load
from sluicer.normalise import normalised
from sluicer.structure import induce as induce_records
from sluicer.summary import Conflict, SummaryField, read_summary
from sluicer.visible import Guess, read_visible

# The least a page's places are paid from: a small page's are never cut.
PLACES_FLOOR = 10_000


@dataclass
class Extraction:
    """What Sluicer found in one page, and where it came from.

    ``url`` is the address given to ``extract``. ``summary`` answers the
    questions most callers ask -- title, author, date, price -- one value each,
    chosen from the records by fixed rules, each naming its reader and key (see
    ``sluicer.summary.FIELDS``). ``records`` is everything the page declared.
    ``links`` is what the page's ``<link>`` elements declare about where else
    it lives: its canonical address, its other languages, its feeds, the pages
    before and after it (see ``sluicer.declared.links``). ``rights`` is what the
    page's own tags declare about how it may be used -- robots directives,
    TDMRep's reservation -- and nothing when it declares nothing (see
    ``sluicer.declared.rights``). ``sources`` names every
    reader that found something. ``normalised`` reads
    the summary's dates, price and currency into ISO 8601, a decimal and an ISO
    4217 code, where the page's text leaves no doubt (see ``sluicer.normalise``).
    ``conflicts`` is every question the page answers in two ways that mean
    different things -- a price in JSON-LD and another in OpenGraph -- the
    summary's answer first (see ``sluicer.summary.Conflict``). ``visible`` is
    empty unless ``extract`` was asked for it: then the title, author,
    publication and update dates the page shows a reader, each a guess naming
    its element and rule, kept apart from the summary, which holds only what
    the page declares (see ``sluicer.visible``).
    """

    url: str | None = None
    summary: dict[str, SummaryField] = field(default_factory=dict)
    normalised: dict[str, str] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    links: Links = field(default_factory=lambda: Links())
    rights: Rights = field(default_factory=lambda: Rights())
    visible: dict[str, Guess] = field(default_factory=dict)


def extract(
    html: str | bytes,
    url: str | None = None,
    induce: bool = False,
    microformats: bool = False,
    headers: Mapping[str, str] | None = None,
    visible: bool = False,
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
        headers: the response's headers, when the page came over HTTP. A
            canonical, ``hreflang`` alternates and the next and previous pages
            in its ``Link`` header join the markup's in ``links`` and the
            summary's ``url``; ``X-Robots-Tag`` and TDMRep's headers are
            reported in ``rights["http"]``; the ``Content-Type`` charset
            decodes bytes, ahead of the page's own declaration, as a browser
            does. ``Fetched.headers`` is this.
        visible: also read what the page shows and may not declare -- its
            heading, byline, publication and update dates -- into
            ``visible``, each answer a guess, never into the summary.

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
    sent = lowered(headers)
    doc = load(html, url=url, charset=charset(sent))
    return _extract_document(doc, sent, induce, microformats, visible)


def _extract_document(
    doc: Document,
    sent: dict[str, str],
    induce: bool = False,
    microformats: bool = False,
    visible: bool = False,
) -> Extraction:
    """``extract`` of a page already parsed, its headers already lowered: for
    a caller that walks the same tree itself, which then parses it once."""
    url = doc.url
    header_links = read_header_links(sent, url) if sent else None
    asked = {"microformats": microformats}
    found = {
        reader.name: (
            reader.read(doc)
            if reader.optional is None or asked[reader.optional]
            else None
        )
        for reader in READERS
    }
    sources = [name for name, declared in found.items() if declared]
    # Every place the answer gives is paid for, twice the page for the records
    # and the page again for the summary, so a page nested two hundred deep
    # cannot answer with an XPath per property longer than itself.
    records = merge(
        places=Places(max(PLACES_FLOOR, 2 * len(doc.html))),
        **{name: declared for name, declared in found.items() if declared},
    )
    # A record carrying no field is a type and nothing else -- a ``WebPage``
    # with only an ``@id``, a microformats root that was a CSS class -- and an
    # empty value is not a value, whole records included.
    records = [record for record in records if record.fields]
    summary, conflicts = read_summary(
        doc,
        records,
        found["dublincore"] or {},
        # One value per property, as the protocol prefers it; the records
        # keep the arrays.
        read_opengraph(doc) if found["opengraph"] else {},
        found["twitter"] or {},
        found["html"] or {},
        header_links["canonicals"] if header_links else None,
        places=Places(max(PLACES_FLOOR, len(doc.html))),
    )
    if induce and not _declared_about_its_things(records):
        induced = induce_records(doc)
        if induced:
            records = [*records, *induced]
            sources = [*sources, "induced"]
    return Extraction(
        url=url,
        summary=summary,
        normalised=normalised(summary),
        conflicts=conflicts,
        records=records,
        sources=sources,
        links=read_links(doc, header_links),
        rights=read_rights(doc, read_header_rights(sent) if sent else None),
        visible=read_visible(doc) if visible else {},
    )


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
