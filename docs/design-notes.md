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

## OpenGraph's arrays are read by position

OpenGraph writes a list by repeating a tag, and describes an image by the tags
that follow it: an `og:image:width` is the width of the `og:image` above it,
and the next `og:image` starts another image. That is ogp.me's own rule, and
its own example -- three images, the first 300 by 300, the second unsized, the
third 1000 tall -- is a test here. Read by index instead, as openGraphScraper
does, the third image's height lands on the second.

So a record's OpenGraph fields are the page's arrays: several `og:image` are a
list of `{url, width, height, alt...}`, and `article:tag` or
`og:locale:alternate` declared several times is a list of their values. Only
the properties the protocol calls arrays are lists; any other declared twice
is a conflict, and "the first tag is given preference". The summary asks each
property's preferred value, the first, so `image` answers the first image and
never a size that belongs to another. Of the 1,012 cached benchmark pages
with OpenGraph tags, 841 name an image, a video or a sound, 384 describe one
with structured properties and 47 declare more than one `og:image`. Two write
a property ahead of the image it describes, and it is read as that image's.

## The summary answers by rule

`summary` asks a fixed list of questions (`sluicer.summary.FIELDS`, 25 of
them) and takes, for each, the first candidate in a stated list
(`sluicer/summary.py`). Its subject is the first declared record about a thing,
ahead of pages, sites and furniture; a type declared on three or more records
is a listing and none of its items is the subject, unless exactly one of them
carries an offer -- the product among its related products -- or all of them
bear one name, as a product declared once per colour does, and then only the
answers every variant agrees on are given. A
page that misuses a term is answered by that misuse, which is why every answer
names the key it was read from.

## Politeness is the product

A crawler is judged by the sites it visits, so the rules are the site's before
they are ours. Every request -- a robots.txt, a sitemap, a redirect's hop, a
rung the ladder climbs to -- waits its site's delay after the last request
ended, a second or the site's `Crawl-delay`, counted from the end so that a
slow answer is never a reason to ask sooner. One request at a time per site,
where a site is a host with or without `www.`: pacing `www.example.com` and
`example.com` apart would ask the same machines twice as often. The time each
site was last asked is kept for the process, as the robots.txt answers are,
because the first real crawls found three places where a request followed
another by 0.00 s, each between two pieces of code that each paced only
themselves. A crawl has no switch to skip robots.txt and never climbs to the
stealth rung: a single fetch is one decision about one page, a crawl is many
pages on one decision. It lives in `sluicer/crawl/schedule.py`.

## A crawl's order is decided, not raced

Addresses are numbered as they are admitted, pages come back in that order
whatever order their fetches finished in, and what a page admits is decided
when its turn comes, not when its fetch happens to return. So the same site
crawled twice gives the same file, whatever the concurrency, and the file is
the whole state: replaying it admits again exactly what it admitted, and a
stopped crawl continues without asking for any page twice. A page that was
fetched but whose turn never came -- the time ran out on a page before it -- is
dropped rather than written out of order. It lives in `sluicer/crawl/pages.py`.

## Arriving under our own name

Every request says `Sluicer/<version>` with a link to the repository and sends
no borrowed referer or fingerprint, so a site can refuse us with one line of
robots.txt, which is obeyed by default. The stealth rung is never automatic:
climbing from plain HTTP to a browser is a change of cost, climbing to a
disguise is a change of character. What a rung sends is checked against a real
server, because a faked library accepts whatever keyword it is handed.

## Why the audit reads each vocabulary on its own

`extract` folds JSON-LD, microdata and RDFa into one record per thing, which is
what a caller asking "what is this product" wants. An audit asks a different
question -- does this markup meet this rule -- and Google answers it for each
syntax on its own: a product declared twice is two items to its validator. So
the audit takes each reader's items before any folding, names the vocabulary
of every finding, and compares the vocabularies only where each declares one
record of a type (`sluicer/audit/records.py`). The rules themselves are data,
one entry per documented type, in `sluicer/audit/google.py`, so a change on
Google's side is a change to a table and to nothing that walks it.
