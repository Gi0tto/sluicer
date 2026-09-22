"""The one call most people will make."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.merge import Record, merge
from sluicer.declared.microdata import read_microdata
from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load
from sluicer.structure import induce as induce_records


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
    something about the things on it. Declared data is what a page says about
    itself; induced data is what we noticed about its markup, and the two are
    not the same kind of claim. So induction runs only when asked, it never
    fills a gap in a declared record, and every field it produces carries
    ``source="induced"`` so the two can never be confused.

    What "declared something" means is counted in fields, not in parses. An
    empty ``<script type="application/ld+json">{}</script>``, an object that is
    nothing but an ``@type``, and an ``itemscope`` with no property all parse,
    and all say nothing about anything; treating them as a declaration blocked
    induction on pages whose list was right there, and contradicted this
    repository's own rule that an empty value is not a value. OpenGraph is
    counted out for a different reason: ``og:title`` and ``og:site_name``
    describe the page or the site, and a page whose only declaration is that
    chrome has declared nothing about its rows. It is not counted out by name,
    though: the gate names the vocabularies that describe a *thing*, in
    ``ABOUT_A_THING``, and every other reader is taken to describe the
    document. Both readers still appear in ``sources`` when they parsed,
    because that is true; what changes is only what the gate decides on.

    When induction does run and finds something, its records are added to the
    declared ones rather than replacing them -- nothing parsed is thrown away --
    except that a declared record carrying no field at all is dropped, since it
    is exactly what the gate has just judged to be nothing.
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
    if induce and not _declared_about_its_things(records):
        induced = induce_records(doc)
        if induced:
            records = [record for record in records if record.fields] + induced
            sources = [*sources, "induced"]
    return Extraction(url=url, records=records, sources=sources)


# The vocabularies that describe a thing on the page rather than the page
# itself. Named positively on purpose: the gate used to ask which source was
# not OpenGraph, and every document-level vocabulary added after it would have
# switched induction off silently. A reader added here is a reader claiming to
# describe the page's subject; anything unlisted is taken to describe the
# document, which is the safe side -- it lets induction run.
#
# ``rdfa`` and ``microformats`` are named before their readers exist: the set
# is the statement of the rule, and a rule written down in instalments judges
# pages by half of itself in between.
ABOUT_A_THING = frozenset({"jsonld", "microdata", "rdfa", "microformats"})


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
