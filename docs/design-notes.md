# Design notes

The reasons behind rules the code states tersely. Each note says what the rule
is, what it protects against, and where it lives.

## The order of precedence

Eight readers, one order: JSON-LD, microdata, microformats, RDFa, Dublin Core,
OpenGraph, the Twitter card, HTML's own metadata names. Where two declare the
same field the earlier one wins, and the field says which one did. The first
four describe the thing the page is about and fold by type; the last four
describe the document, declare no type, and fill the first record on the page.
The order is written once, as the parameter order of `merge()`
(`sluicer/declared/merge.py`), and no parameter has a default, so a reader
added later cannot be silently left out of a call site.

## Why HTML's own metadata names come last

`<meta name="description">` is on 87% of real pages (measured on 2026-09-22
across the 359 WCXB pages Sluicer targets) and is very often the same sentence
as `og:description`. It is also the weakest statement a page makes -- no
vocabulary, no schema, no type -- so it fills what the others left empty and
never overrides one of them. It is read at all because it reaches the most
pages: it and `<meta name="author">` are often the only declarations a page
has. Its values say `"source": "html"`, never a vocabulary that did not claim
them.

## Why microformats is off by default

Every other reader is written in the `lxml` the base install already carries.
Microformats2 has a reference parser, `mf2py`, and an environment holding it
alone holds twelve packages against a base install of three. A reader that
raises unless someone installed something is not a default, so it is behind
`sluicer[microformats]` and `extract(html, microformats=True)`. It buys
compatibility with `extruct` rather than reach: across twenty live pages
measured on 2026-09-22, microformats appeared on one, which carried OpenGraph
too.

## When induction runs

Declared data is what a page says about itself; induced data is what we
noticed about its markup, and they are not the same kind of claim. So
induction runs only when asked, only on a page that declared nothing about the
things on it, never fills a gap in a declared record, and marks every field
`source="induced"`.

"Declared something" is counted in fields, not parses. An empty
`<script type="application/ld+json">{}</script>`, an object that is only an
`@type`, and an `itemscope` with no property all parse and say nothing;
counting them blocked induction on pages whose list was right there. Dublin
Core, OpenGraph, the Twitter card and HTML's meta names never count, since
`og:site_name` or `<meta name="description">` describe the page, not its rows.
The gate names the readers that describe a thing -- `ABOUT_A_THING` in
`sluicer/declared/merge.py` -- so a new document-level reader needs no change
there; a new reader that describes a thing must be added to it.

A declared record with no field is never reported: it is a type and nothing
else. When induction finds rows they are added after the declared records.

## Nested values and references

A nested value -- an author, an `offers` block, a recipe's ingredients -- is
carried whole as the JSON the page declared, every leaf as text, with `@type`
kept. A JSON-LD reference to another node on the page is replaced by that node,
one hop deep: measured on a Yoast blog post, one hop gives 22 KB of output,
three give 38 KB, because every record re-expands the same graph. Every walk
over a graph the page declares has a memory, so a cycle ends, and a budget, so
a hostile page costs a bounded amount: without them, four microdata items
naming each other with `itemref` were estimated at half an hour, and four
thousand JSON-LD references to one node were four gigabytes from a 119 KB page.

## The summary answers by rule

`summary` asks sixteen fixed questions and takes, for each, the first candidate
in a stated list (`sluicer/summary.py`). Its subject is the first declared
record about a thing, ahead of pages, sites and furniture; a type declared on
three or more records is a listing and none of its items is the subject. A
page that misuses a term is answered by that misuse, which is why every answer
names the key it was read from.

## Arriving under our own name

Every request says `Sluicer/<version>` with a link to the repository and sends
no borrowed referer or fingerprint, so a site can refuse us with one line of
robots.txt, which is obeyed by default. The stealth rung is never automatic:
climbing from plain HTTP to a browser is a change of cost, climbing to a
disguise is a change of character. What a rung sends is checked against a real
server, because a faked library accepts whatever keyword it is handed.
