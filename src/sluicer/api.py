"""The one call most people will make."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.dublincore import read_dublincore
from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.merge import Record, merge
from sluicer.declared.microdata import read_microdata
from sluicer.declared.opengraph import read_opengraph
from sluicer.declared.rdfa import read_rdfa
from sluicer.declared.twitter import read_twitter
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

    Six readers run, and they have a stated order of precedence: JSON-LD,
    microdata, RDFa, Dublin Core, OpenGraph, the Twitter card. Where two of
    them declare the same field the earlier one wins, and the field says which
    one that was. ``sources`` names every reader that found something, in that
    same order. The first three describe the thing the page is about, in
    decreasing order of how much of today's web uses them; the last three
    describe the document, which is why they come last.

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
    repository's own rule that an empty value is not a value. Dublin Core,
    OpenGraph and the Twitter card are counted out for a different reason:
    ``DC.title``, ``og:site_name`` and ``twitter:card`` describe the page or
    the site, and a page whose only declaration is that chrome has declared
    nothing about its rows. They are not counted out by name, though: the gate
    names the vocabularies that describe a *thing*, in ``ABOUT_A_THING``, and
    every other reader is taken to describe the document. Each of them still
    appears in ``sources`` when it parsed, because that is true; what changes
    is only what the gate decides on.

    When induction does run and finds something, its records are added to the
    declared ones rather than replacing them -- nothing parsed is thrown away --
    except that a declared record carrying no field at all is dropped, since it
    is exactly what the gate has just judged to be nothing.
    """
    doc = load(html, url=url)
    jsonld = read_jsonld(doc)
    microdata = read_microdata(doc)
    rdfa = read_rdfa(doc)
    dublincore = read_dublincore(doc)
    opengraph = read_opengraph(doc)
    twitter = read_twitter(doc)

    sources = [
        name
        for name, found in (
            ("jsonld", jsonld),
            ("microdata", microdata),
            ("rdfa", rdfa),
            ("dublincore", dublincore),
            ("opengraph", opengraph),
            ("twitter", twitter),
        )
        if found
    ]
    records = merge(
        jsonld=jsonld,
        microdata=microdata,
        rdfa=rdfa,
        dublincore=dublincore,
        opengraph=opengraph,
        twitter=twitter,
    )
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
# The Twitter card is what that bought: a sixth reader, document-level like
# OpenGraph, wired in without a line changing here.
#
# ``microformats`` is named before its reader exists: the set is the statement
# of the rule, and a rule written down in instalments judges pages by half of
# itself in between.
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
