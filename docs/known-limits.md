# Known limits

Everything here is deliberate, measured, and open. It is not a bug list: it is
the set of places where Sluicer currently stops, written down so nobody has to
rediscover them, and so a contributor inherits decided questions instead of
surprises.

## In the extraction path

**A reference is followed one hop.** A JSON-LD node that names another by
`@id` gets that node in its place, so an article's author and publisher arrive
whole; a reference inside the node that replaced it stays a reference. Measured
on a Yoast blog post, three hops instead of one took the output from 22 KB to
38 KB, because every record re-expanded the same graph.

**The summary answers by rule, not by judgement.** Its subject is the first
declared record about a thing, ahead of pages, sites and furniture, or the
thing such a record declares its main entity, and each
question takes the first candidate in a stated list. A page that misuses a term
is answered by that misuse, except where a rule was written for it: a site
that puts its short description in `headline` gets `name` as its title, when
only `name` appears in the title the page shows.

**A site signing its own page has named no author, and the labels disagree.**
An author bearing the site's name -- its `og:site_name`, its WebSite's name, its
host -- is left out, unless the page declares a publisher of that name a Person,
since a blogger's site bears their name. The scoreboards' labels part here.
fundus's news pages count the paper as the author when no one else is named;
WCXB's count such a page as unsigned. Without the rule the news pages would gain
17 answers their labels call right and 8 they call wrong, the pages as served 1
and 12, and WCXB's 2 and 10. Sluicer follows the second, and `records` keeps the
declared author either way. An author named as the page's publisher, but not as
its site, is kept: a broadcaster's news desk signing under a name the site
itself does not bear. A publisher declared an organisation is not always one --
Yoast declares a person's own site so, and a news agency publishes the stories
it writes -- and leaving such authors out, measured, drops 6 answers the labels
call right, both kinds among them, to drop 10 they call wrong. A question's
asker is its author: a question and answer page declares the question its main
entity, and the summary answers about it, where WCXB's labels count such a page,
and a forum thread, as unsigned -- 12 of its pages, and 6 of those as served. Of
the 17 authors trafilatura finds on the news pages and Sluicer does not, 12 are
the paper itself, left out by this rule, and 5 are people the page names only in
its visible byline or in a tag no vocabulary defines -- an analytics service's
`cXenseParse:author` or `DCSext.author` -- which are not read.

**Gap-filling targets the first record of a type.** When a page declares several
records sharing a type, a lower-precedence reader fills the first one in document
order. On a page whose `@graph` opens with a `BreadcrumbList`, an `og:title`
lands on the breadcrumb rather than the product. Document order is the only
deterministic signal available; the template contract planned in the roadmap is
where a better one can come from.

**A declared encoding can still disagree with the bytes.** Bytes are decoded
as a browser decodes them -- a byte order mark, then the response's charset
when `extract(headers=...)` is given it, then an XML declaration or a
`<meta charset>` anywhere in the head, then windows-1252 -- with one
departure: bytes that are valid UTF-8 and hold a character outside ASCII are
UTF-8, whatever is declared. A page saved or re-encoded by another tool keeps
its old `<meta charset=GB2312>` over UTF-8 bytes, and fundus's fixtures read
as mojibake until this; on 1,427 pages as their servers sent them, no page
changed. The one text read otherwise than a browser reads it is legacy text
that is also valid UTF-8, such as `Ã©` written in windows-1252, which is
mojibake already. A declaration that lies about bytes that are not UTF-8 is
still believed. When only text is available and lxml cannot parse it, the
retry reads it as UTF-8 whatever the document claims, because the text has
already been decoded.

**A guess from the visible page, on by default, and kept apart.** The
summary holds only what a page declares. `--visible` (`extract(...)`,
`extract_declared`'s `visible`), on by default since 0.10 and off with
`--no-visible` or `visible=False`, guesses the heading, byline and dates a
page shows, in `visible`, each with its element and rule; it adds 2 to 3 ms
to a page at the median, about four fifths more time on WCXB's development
pages. Its
rules were made on WCXB's development pages only, and every title, author and
date scoreboard scores it on pages it was not made on, a guess taken only
where the summary has no answer (`bench/PREREG.md`). It finds more: authors
0.532 to 0.649 and dates 0.581 to 0.717 on WCXB, 0.690 to 0.752 and 0.780 to
0.855 as served, 0.468 to 0.548 and 0.585 to 0.701 on trafilatura's set. And
it invents -- 33 answers on WCXB's 511 pages, 25 of them dates -- so dates
are right when answering less often with it, 0.823 against 0.917 on WCXB and
0.701 against 0.734 as served. Trafilatura, which
the base install brings, can guess too: `examples/04_a_guess_from_the_visible_page.py`
puts its guess beside Sluicer's answer, named a guess, when the page declares
no author or date. Measured where Sluicer answers nothing, the guess is right
on 48 of the 114 WCXB pages where it names an author and on 76 of the 312
where it names a date; on 23 of 64 and 17 of 178 of the same pages as served;
on 16 of 21 and 3 of 7 news pages; and on 110 of 183 and 190 of 311 of the
pages trafilatura annotated to measure itself. Inside the summary such an
answer would look exactly like a declared one; kept apart, it is taken for
what it is worth.

**A date's month is read by its name in any language CLDR covers.**
`normalised` reads a date's month by its name in any of the 430 languages and
regions CLDR 48.2 covers at its modern level (`sluicer/calendar_names.json`,
under the Unicode License v3, with its source), in the orders they write it:
`10. Mai 2023`, `10 de mayo de 2023`, Hungarian's `2023. május 10.`, and the
numbers with units of Chinese, Japanese and Korean, `2023年5月10日`. Five
names that mean two months in two languages are not read -- `listopad` is
November in Polish and October in Croatian -- nor a date with a time after
it in words, nor any all-number form but ISO's. A Thai month's year from 2400
on is the Buddhist era's and is converted. On the 2,680 pages of the
scoreboards and of trafilatura's evaluation set, pages declare dates in these
forms almost never: one more date is read, `28. Dezember 2022`, and none
changes.

**RDFa is read as Lite, not as a graph.** The RDFa reader stops where the graph begins: `vocab`, `prefix`, `typeof`, `property` and
`resource` are read, one record per `typeof`, and chained subjects, typed
literals and inference are not. A record names no subject: the address a
`resource`, `src` or `href` gives a `typeof`, and the page's own, are not kept,
as microdata's `itemid` is not. A property no `typeof` encloses is not read;
on the 3,976 cached corpus pages, measured on 2026-09-25, 544 such properties
sit on 205 pages, and most are `<meta property="description">`, `stylesheet`,
`robots` and analytics keys rather than statements. Links (`rel`, `rev`),
`about`, `inlist`, property copying (`rdfa:copy`), `role`, datatypes and
languages are not read: a `datatype` keeps the words it types, a `<time>` its
`datetime`, and a `rel` or `rev` naming a term only says the address is the
link's and not the property's; with a `typeof` and a literal property on
the same element, the `typeof` types the link's object, which is not kept, and
the property is the enclosing record's. Nor are the processor graph and
vocabulary expansion offered, the two options the suite's tests ask of a
processor. The [RDFa scoreboard](scoreboard-rdfa.md) runs the W3C RDFa test
suite through the reader and files every test it fails under one of these. Anyone who needs the full graph is better served by a triple store
than by this pretending, or by `sluicer.compat.extruct`, which builds one.

**Microformats is off unless you ask, and flattened when you do.** It is the
only reader behind an extra, because it is the only one that cannot be written
in the `lxml` the base install already carries: `mf2py` is the reference parser
and costs twelve packages against a base install of four. `extract(html,
microformats=True)` turns it on and raises `MicroformatsExtraMissing` when the
extra is absent. What it returns is flat, and a tree is not: a repeated property
keeps its first value, so a second `p-category` is dropped; a nested item
contributes its name and its link, `author` and `author@url`, and nothing else,
so an `h-geo` holding only a latitude contributes nothing at all. The address is
read from the nested item's `url` property rather than from its `value`, which
was measured rather than assumed -- for a `p-` prefixed item the value is the
name, not the link. `metaformats` is left off, so OpenGraph and Twitter card
tags are never reported as microformats; each has a reader of its own here.

**Conflicts are stated for four questions.** The price, the currency and
the dates of publication and modification are compared across the page's
declarations of them; titles, descriptions, authors, availability and
identifiers are not, since vocabularies word them differently on purpose,
or, for availability, name its values each their own way (`InStock`,
`instock`, `in stock`). Two dates on one day are one date, whatever their
times; two records of one thing that disagree in JSON-LD and microdata are
compared by `sluicer audit`, record against record, not here.

**Eight vocabularies fold onto one flat set of keys, and some of them collide.**
`og:image:alt` and `twitter:image:alt` both strip to `image:alt`; a Dublin Core
`title` lands on the same key as an `og:title`. RDFa and JSON-LD shorten
schema.org terms to the names the other readers use and keep other
vocabularies' full IRIs, so only schema.org terms collide across vocabularies:
a JSON-LD block's words are named through its `@context` -- `ex:colour` under
`{"ex": "http://example.com/"}` is `http://example.com/colour`, and a `name`
the context maps to FOAF is FOAF's -- while a word the context says nothing
about, or one a context elsewhere would define, is kept as written, since only
schema.org's own context is known and nothing is fetched; a word a context
defines as schema.org's namespace is schema.org's prefix however it is
written, `{"schema": "http://schema.org"}` too, where JSON-LD 1.1 asks a
prefix to end in `/` or say `@prefix` and PyLD keeps `schema:Product` as an
address of its own; a word is named
through at most 32 contexts since the last `null`, whether in a list or around
nested graphs, and past them an object's words are kept as written, as under a
context elsewhere, never named through the 32 alone. Two words of one
object that name one property -- `price` and `schema:price` -- give one value:
the word written as the name itself, wherever the object lists it, and failing
that the first written; its place points at the key the page wrote. The precedence decides who
wins -- JSON-LD, microdata, microformats, RDFa, Dublin Core, OpenGraph, the
Twitter card, HTML's own metadata names -- so the answer is stated and stable
rather than decided by the order the page's author typed. What is lost is the
loser: it is dropped, not kept under a qualified name. Microformats keeps its
own type spelling: an `h-entry` records `@type` as `h-entry`, so it
never folds with a schema.org `Article` that means the same thing.

**`:has()` needs cssselect 1.5.** The base install accepts cssselect 1.2,
and cssselect 1.2 to 1.4 translate `:has()` wrongly: `p + p:has(b)` to an
XPath lxml rejects, `p:not(:has(b))` to one that selects every `p`. Below
1.5 a selector with `:has()` is refused, with an error that says so;
`uv pip install -U cssselect` lifts it.

**A place is an XPath into the page as lxml parsed it, not as a browser
did.** libxml2 builds its own tree: it adds no `<tbody>` to a table, which a
browser always does, and it mends broken markup its own way, so a place such
as `/html/body/table[1]/tr[1]/td[1]` may select nothing in a browser's
developer tools; the same page parsed by `sluicer.document.load` finds it.
A fragment, or a page with no head that does not open with `<html>` or a
doctype, is parsed as a whole document, as lxml's `document_fromstring` and a
browser both build it, so its places start at `/html/body`.

**The same page can read differently on lxml 5.3 and on lxml 6.** The
floor, lxml 5.3.0, bundles libxml2 2.12; lxml 6 bundles 2.14, whose tokenizer
follows HTML5 while its tree building does not yet. Newlines are Sluicer's
own business -- CR LF and a lone CR are read as LF before either parses a
page -- but where each puts a stray `<title>` or `<link>`, and whether it
knows an HTML5-only name such as `&mldr;`, is libxml2's. Measured on 5,948
benchmark pages, 42 give a different answer on 5.3.0 than on 6.1.3, 38 of
them SWDE pages from 2010; the newlines had made 13 more.
Some values have no place at all: a meta tag's -- OpenGraph, the Twitter
card, Dublin Core and HTML's meta names return values, not elements, and
their key names the tag -- an induced row's, a microformats item's, an answer
joined from several tags, and any place past the page's budget for them,
which only a page nested far deeper than real ones reaches. A property
declared twice in microdata or RDFa is placed at its item, not at either
element.

## In extractors

**A listing's place is an exact path.** A new wrapper or a renamed class above
the rows fails the `listing` check. That is what makes the failure loud, and
`heal` finds the new place; it also means one cosmetic change upstream of the
rows is enough to fail a run.

**One listing per extractor**, the page's most promising repeated group. A page
with two listings that both matter needs two extractors, and there is no way yet
to point compile at the second.

**A listing's columns are what a reader sees.** Each part of a row gives
its text, an image its alt text, a link or an image its address. A `<meta>`
inside a row gives nothing, though its `content` is often the row's cleanest
value -- quotes.toscrape.com declares each quote's tags there, as
`change,deep-thoughts,thinking,world`. It is left out on purpose: such a
`<meta>` is a declaration, microdata's `itemprop` or RDFa's `property`, and
declared data is read by the declared readers, where `extract()` already
gives it (the CreativeWork's `keywords`), never by induction, which never
fills a gap in a declared record and marks what it finds `induced` (see
design-notes.md, "When induction runs"). `--want` a value only a `<meta>`
holds finds no listing; with `--listing`, that is an error.

**Healing matches by values.** A field is moved only when its new place holds
values it held before; a same-shaped field with new values is not a match, so a
redesign that changes the markup and every value at once is reported as fields
vanished and new, not as moves. The samples are five values, so on a listing
whose rows changed completely between learning and healing, heal finds nothing
to match and says so.

**Heal follows a field's label wherever the page says it.** A page field
learnt after its label, "Director:", is moved by heal to after that label's
new place, found anywhere on the page: where another block says the same
label -- a crew table's "Director:" beside a film's own -- heal can move the
field there, and the healed extractor then reads that block's value. `run`
counts the label only among the list it was learnt in; heal does not yet.
Found by review for 0.8; the same in 0.7.1.

**An extractor can fail a page it was learnt from.** On SWDE, 9 of the 80
learnt extractors fail one of their own three seed pages, each on a page
field that only some seeds carry (compile notes it as "at path on 1 of 3
pages"); and 27 single-page compiles over the products and markdown corpora
fail their own page, where learning and replay count different rows. Both
are the same in 0.7.1; refusing such extractors would hide the defects, so
they are listed here until each is fixed.

**The thresholds are fixed.** 20% of rows may lack a required field, half a
field's values must keep its shape, and a shape needs five values to be learnt
or to be held to that half; a page with three or four values of a column that
reads as an amount or a date is held to one of them reading so, and a page of
one or two values, or of fewer than five to a shape, to nothing: the last page
of a pagination, a single part priced "Call", passes.
Editing the JSON changes what was learnt, not the thresholds.

**A rare column is missed only from enough rows, and never by the page.** A
hand-written listing's column fewer than half the learnt rows carried -- a
sale badge -- fails a page none of whose rows carries it only when that is
under a 1% chance, taken row by row: a page of ten rows without a badge
three rows in ten carried is 2.8%, and passes, whether nothing is on sale
that day or a redesign broke the badge's selector. When a page it was
learnt from carried it in no row, no page is held to it at all, since
badges come by the page. A learnt listing holds a column fewer than half
its rows carried to nothing, and a column is not held to differ from row to
row when a page it was learnt from gave it one value in each of five rows or
more.

**Two free-text columns can swap unnoticed** on a page the extractor was not
learnt from: a title and a brand keep their shapes, and neither reads as an
amount or a date. A swap is caught when one side read as an amount or a date
(the `reads` check), or became the same in every row (the `values` check).

**A numbered listing can be swapped for a box that says nothing of it.** A
listing at `section.box[2]` is held to the heading its box began with on the
pages learnt, "Books", when no other box did. A page whose second box begins
otherwise while another box begins "Books" has moved it, and fails; but a
page where no box says "Books" is held only to the count of boxes, since a
heading the template writes from the page -- another category's name -- says
nothing about where the box went. The books' box replaced by a sponsored one,
as many boxes as before, passes unless the rows' own checks fail.

**A page field's row can move unnoticed under a renamed label.** A field read
by its place is held to the label the learnt pages put right before it, but a
page that no longer says that label at all is read at the place: a label
renamed, "SKU" to "Art. no.", is not a row moved, and the two cannot be told
apart. A page that renames the label and moves the row passes with the value
now at the place, unless the field reads as an amount or a date, or five pages
or more taught it a shape. "SKU" written "SKU:" or "sku" is the same label.

**A label without a colon is no label to a page field.** A text counts as
the label before a value only when it ends with a colon or sits in HTML's own
element for one (`th`, `dt`, `label`). A header written as
`<span>Status</span><span>Active</span>`, whose rows differ from page to
page -- one PEP with a Discussions-To row the others lack -- is learnt by the
place, and a page with the extra row reads its Discussions-To as the status
and passes. Taking any text the template says once on every page for a label
fixed that, and read "Only 2 left!" as the price of a page that put it
between "Write a Review" and the price, with the run passing: the text before
a value is often not its label, and without a colon or a label's element the
two cannot be told apart.

**Extractors are measured on 44 pairs of captures from 25 sites.** The drift
benchmark (docs/drift.md) shows no silent failure and no false alarm there, and
that is a small sample: mostly news and link aggregators, no real shop, and
heal judged only where the two captures share items, which on news pages they
rarely do.

## In announcing ourselves

**The user agent on the wire is verified by the live checks, not by the
suite.** The suite must never open a socket, so it reads what the HTTP rung
wrote to a fake one and what the browser rung told a fake context; what a
server actually receives is asked in CI by `tests/live/http_check.py`,
`browser_check.py` and `extras_check.py`, against local servers, and each
server saw `Sluicer/<version> (+https://github.com/Gi0tto/sluicer)` and no
referer. That gap has cost once: in 0.7.0 the browser rung, then scrapling's,
passed the name where the browser context silently overrode it, so the tests
passed while every site saw Chrome, and scrapling's defaults added `Referer:
https://www.google.com/`. Since 0.8 the browser rung is Playwright driven
directly, and is told our name and nothing else: no flag, colour scheme or
pixel ratio chosen to look like a person's browser. What Chromium itself
sends, it still sends: its `sec-ch-ua` names `HeadlessChrome`. If you change
how a rung is built, ask a real server what it saw.

**The HTTP rung's TLS is Python's.** It is `ssl` over the system's
certificates, so its handshake looks like any Python client's, which some
bot defences refuse more readily than curl's; a refusal is a measurement, and
the ladder climbs on it. A Python whose certificates were never installed --
the python.org installer on macOS, before its `Install Certificates` step --
verifies nothing and fails every https fetch; point `SSL_CERT_FILE` at a
bundle.

**A robots.txt group is ours when it names our product token.** `User-agent:
Sluicer`, in any case, is the group Sluicer obeys, and `*` when there is none.
Until 0.7.1 protego was handed the whole user agent, and a group for
`https`, `github` or `com` was taken for ours. protego still takes a group
named by the start of the name for ours, `User-agent: slu`, and one that writes
a version after it, `Sluicer/1.0`, for someone else's; RFC 9309 would do
neither.

**The robots answer is believed for a day.** A site that adds a rule is noticed
within twenty-four hours, not immediately. The process remembers the answers of
the 4,096 sites it used most recently (`ROBOTS_CACHE_HOSTS`); a site pushed out
is only asked again.

**Robots.txt is asked where a redirect landed, after it landed.** A page whose
redirects ended on another host is refused if that host's robots.txt says no,
but the hops in between were requested without asking theirs. Addresses are
stricter: with `allow_private=False` every hop is judged before it is requested,
by both rungs (see the MCP section below). A crawl is stricter still: it
refuses a hop that leaves the site before it is asked, so its redirects stay on
one site, whose robots.txt it has already read.

**The stealth rung does not announce itself, deliberately.** It exists to not be
recognised, and announcing yourself and then evading is incoherent. It is not
part of the automatic ladder for the same reason: climbing on a
measurement from plain HTTP to a browser is a change of cost, while climbing
from announcing yourself to hiding is a change of character, and it should not
happen to a caller who never asked for it. Not announcing is all it does: until
0.7.1 it inherited scrapling's `google_search` and sent `Referer:
https://www.google.com/`, claiming a visit from a search that never happened,
and three tries of thirty seconds. Measured on a local server, it now sends no
referer, and tries once, as the browser rung does. Since 0.8 it is the only
place scrapling is used, behind the `stealth` extra; it sends none of a
caller's headers or cookies, which would say who is asking, and no site is
ever remembered as needing it.

**Normalisation refuses what is ambiguous.** A date is read from ISO 8601 and
its common variants, RFC 2822, JavaScript's `Date.toString()`, and a month's
name in any language CLDR covers at its modern level, before or after the day
or after the year: "16 juin 2025" is 2025-06-16. Of the 669 dates the
benchmarks' pages declare, 6 are not read, each on purpose: two all-number
dates (`08/21/2025`), two six-digit ones (`240221`) and a date with a time
glued to it (`Jan 24, 2026T00:00:00-05:00`), twice. The pages are nearly all
English, so that count says little about other languages. An all-number date other than ISO's, an
amount whose only separator has exactly three digits after it (`1,299`), and a
bare `$`, `¥` or `kr` have no normalised value, since each means two things
somewhere. Indian digit grouping (`12,34,567`) is refused too. The currency
list is ISO 4217's as SIX published it on 2026-09-17, and is only as current as
that.

## In the audit

**It checks what Google documents, not what Google decides.** Google does not
publish the rules of its Rich Results Test, and a page that meets every
documented requirement may still not be shown. The rules here are the tables
of Google's pages as read on 2026-09-23, with the conditions their prose adds;
when Google changes a page, the audit is wrong until `sluicer/audit/google.py`
is read against it again. Every rule names its page, so the check is one link.

**A subtype counts only where the documentation says it does.** A `Restaurant`
is a local business because the local business page says to use the most
specific subtype; a `Car` is not a product, because the product pages say it
is not "automatically". Elsewhere the rule followed is schema.org's type tree
(release 30.1), which Google's validator may read differently: it is not known
whether it takes a `ReportageNewsArticle` for an article, and this audit does.

**What is served, not what is rendered.** The audit reads the HTML the fetch
brought back. Markup a page's script adds later is only there when the fetch
climbed to a browser, and the HTTP rung climbs only on a refusal, a challenge
or an empty shell. Measured on 2026-09-23, a Greenhouse job page is served
declaring no JobPosting and an Apple store page an empty breadcrumb, both
filled in by script.

**Nothing is compared with today's date.** A `priceValidUntil` in the past, an
event that is over and a job that has expired are not reported: the answer
would change with the clock, and the same page must get the same audit.

**Values are checked for their form, not their truth.** A price of `41.90` is
well formed whatever the product costs, a GTIN with a valid check digit may
name another product, and an `addressCountry` is not checked against ISO
3166, whose list has no free machine-readable source like ISO 4217's.

**An optional part's requirements are not the feature's.** Google writes of
shipping details, a video's clips and the like that their properties are
required "if you want" them used. A part that lacks one is reported as
`incomplete-part`, a warning; the feature can still be met. A product's
reviews are a part when the product also has offers or a rating, and needed
when they are all it has.

**Conflicts are compared one to one.** Two vocabularies are held to agree only
when each declares exactly one record of a shared type. A listing that
declares twenty products in JSON-LD and twenty in microdata gets no comparison,
since pairing them would be a guess.

**An Extraction is audited as merged.** Handed what `extract` returned, the
audit sees one record per thing with the winning value of each field, so a
disagreement between vocabularies was already settled, and the page's own
title, description, canonical and OpenGraph are not there to check. The audit
says so in `not_checked`.

**The AI agents are the vendors' lists of 2026-09-23.** Agents appear, are
renamed (Google-NotebookLM, supported until August 2026, is now
Google-GeminiNotebook) and are retired; an agent no vendor page names is reported only as a name the
robots.txt uses. Whether an agent may have the page is protego's reading of
its product token, the parser Sluicer obeys itself; a vendor's own parser may
pick a different group in edge cases, such as a group named by a prefix of the
token. The vendor's word on whether a user-requested fetch honours robots.txt
is reported beside the verdict, and not second-guessed.

**llms-full.txt is reported, not read.** The llms.txt proposal defines no
format for it, so only whether a site serves one, and how long it is, is
known.

**schema.org's names are copied, under their licence.** The type tree and
enumeration terms in `sluicer/audit/schema_org.py` are read from schema.org's
own export, which is published under CC BY-SA 3.0; the module names its source
and release, and it alone is distributed under CC BY-SA 3.0, as `NOTICE`
says, with the licence's text in `LICENSES/`. The rest of sluicer is MIT, but
for CLDR's month and weekday names, with which dates are read (see the
extraction path above).
Google's pages are CC BY 4.0, and each rule cites the page it comes from.

**TDMRep is read from HTML pages and their headers, and the site's file.**
Its metadata in EPUB and PDF files is not read, since sluicer reads no such
file. An archived capture is judged by its own headers and meta tags; today's
tdmrep.json says nothing about a page of last year. A TDM policy is reported
as its address, never fetched or read.

## In fetching

**Plain HTTP is HTTP/1.1.** The base install's client is the standard
library's, which speaks no HTTP/2 or HTTP/3: a site is asked one request at a
time on one kept connection, which is what the gate allows anyway. A
connection is kept up to a minute idle, 32 of them for the process; one the
server closed is found out before it is used, and a request that meets a
close anyway is sent once more, on a new connection. An interim answer (a
102, a 103 Early Hints) is read past to the answer it precedes; a 101 nobody
asked for is a failure. A 204 that names a length for a body it may not have
is not kept. A 304 is kept whatever length it names, as RFC 9110 lets it name
the page's: a server that sends a body after one anyway has it found by the
check before the connection is used again, or, when those bytes arrive later
still, read by the next request as the start of its answer, which fails as
unreadable and is worth asking again.

**A compressed stream without its end is the page only when its framing
says it is whole.** A body sent with a `Content-Length`, all of it, or in
chunks to the last one, whose gzip or deflate stream lacks only its formal
end -- gzip's trailer, zlib's checksum, the final block after a flush -- is
read as curl and Chromium read it: the page. Only its end is missing: the
decoder, handed the end a whole stream would have had, ends there, and
gzip's and zlib's checksums of what it gave agree. Raw deflate has no
checksum, and a stream cut exactly at the edge of one of its blocks passes
for one that was flushed there. A stream that stops mid-way, framing whole,
is refused (`BodyUnfinished`) and not asked again at once. The same stream
delimited only by the connection's close is refused as cut short
(`BodyCutShort`) and worth asking again: nothing says the connection did not
lose its end, where 0.7.1 returned what came. zstd is never read without its
end.

**Brotli is never asked for.** A body is decoded as it arrives and held to the
16 MiB bound as it grows, and the standard library has no brotli decoder to
hold to it: requests offer gzip and deflate, and zstd on Python 3.14 or with
`backports.zstd` installed. A server that sends brotli anyway has sent what the
rung cannot read: the rung fails, and the ladder climbs to the browser, which
can.

**A site's rung is remembered for a day.** Once a page of a site came back only
from the browser, the process starts that site's next pages at the browser for
24 hours, 4,096 sites at most, and says so in each page's first climb. A site
whose pages differ -- a listing that needs a script, articles that do not --
has its articles fetched by a browser too, which costs time and nothing else;
a site that moved back to rendering on the server is asked of plain HTTP again
the next day, or as soon as the remembered rung fails, or brings back a page
to climb past -- a refusal, a challenge, a shell: its page is kept, the
ladder starts again from plain HTTP, and the browser is not asked twice.

**One browser, one page at a time.** The process keeps one Chromium and loads
pages in it one after another, each in a context of its own, so pages that
need a browser, asked for by several callers at once -- a crawl of four sites,
parallel MCP calls -- wait in line, each for at most three minutes
(`WAIT_SECONDS`), then fail. A browser elsewhere (`SLUICER_CDP_URL`) is driven
the same way.

**The browser needs its sandbox to start.** Chromium is launched in its
sandbox, which needs unprivileged user namespaces: Docker's default seccomp
profile refuses them, and Ubuntu 23.10 and later lets only the programs
AppArmor names have them. There the browser rung fails, saying what to allow,
and a page that needed it comes back from plain HTTP; `SLUICER_BROWSER_SANDBOX=0`
runs Chromium without the sandbox, which is how Playwright runs it by default.

**A caller's headers and cookies go to the origin asked.** Scheme, host and
port, for the HTTP rung and for the headers a browser sends; a hop elsewhere
is sent none. A cookie in the browser follows the browser's own rules, under
which a cookie belongs to a host, not to a port; one set for an https origin
is sent over https alone. A crawl, a map and the pages of a sitemap send them
to the origin they start at, and to no other: a site's `www.` twin and its
pages over plain http are part of the crawl and are asked without them. A
batch sends them to the origin of every address it is given, as `curl -H`
sends them to every address, so a batch of several sites gives each site the
same cookie; a redirect's target, read in its own turn, is sent none.
robots.txt is always read without them, so its answer is the site's for
every caller, and so is a sitemap on another origin. A site that answers its
robots.txt with a 5xx to anyone not logged in has every page refused,
logged-in ones too: RFC 9309 reads a 5xx as nothing allowed until it
answers otherwise, and the failure says so. The archive (`--at`)
and the stealth rung are sent none.

**The cache serves single pages.** `--cache` is read by `fetch`, `extract`,
`inspect`, `markdown`, `audit`, `diff`, `feed` and `select`, not by `crawl` or `batch`, whose state file is
their memory, nor by the MCP server. A page that came from the browser rung is
not revalidated, since a browser sends no validators it was not given: it is
fetched again, and kept again.

**A challenge is detected by words, on a page that is not content.** A title
that is the challenge ("Just a moment...") counts on any page; a marker anywhere
else counts only on a page that declared nothing about a thing and carries less
than 1,500 characters of text. Until 0.3.0 any marker anywhere counted, and an
article quoting "just a moment", or any page carrying Cloudflare's bot-detection
script, bought a browser it did not need. A short challenge page that declares a
record would now be missed; none has been seen. The reason string names the
marker, so a mistake either way is visible. The words are the ones seen: Cloudflare's,
DDoS-Guard's, and those the cached benchmark pages hold -- Fastly's "Client
Challenge" (PyPI's), Imperva's `/_Incapsula_Resource`, HUMAN's `px-captcha`,
Anubis's, and a "One moment, please..." waiting room -- found on 11 of 3,988
pages, all of them interstitials. A vendor not among them is not recognised.

**A legitimately empty body is treated as a failed rung.** A site that answers
200 with nothing costs a climb. An empty robots.txt is the exception: it is a
file with no rules, and allows everything. Until the audit read one, the
robots reader took the rung's refusal for an unreachable robots.txt, and a site
whose robots.txt was an empty file could not be fetched at all. A response with no HTML is not a page, and the
ladder already knows how to climb past a failure, so this was the cheap side of
the trade.

**A failed climb returns the cheaper page.** When a rung fails after a cheaper
one brought something back -- a fresh install has no browser -- that page is
returned and the failure is recorded as a climb back down to it, so the caller
can see it is the HTTP rung's answer to a page that wanted a browser, unless
that page is a challenge. When every rung failed, `FetchFailed` says what each
one said; nothing is returned that could pass for a page.

**A challenge page is a refusal, never a page.** When the page the ladder is
left with -- its last rung's, or a cheaper one's after a rung above it failed
-- is a challenge, `SiteRefused` is raised (`refused_by_site` in the MCP
server, the HTTP API and a crawl's page): until 0.7.1 it was returned, and an
MCP answer said `ok: true` about a waiting room. A skeletal page or a refusing
status on the last rung is still returned as it came, with its status: a small
page is often simply small, and a 429's headers are what a crawl slows down
by.

**A redirect to a login page is not detected as a refusal.** A refusal status, a
challenge page and a skeletal body are.

**The browser decodes its own pages.** The HTTP rung decodes the bytes itself,
with the sniffing `load()` uses and the response's own charset where the HTML
standard puts it, between a byte order mark and the page's declaration. The
browser rungs hand over the DOM the browser built, decoded by the browser,
once the page has loaded and its network gone quiet for half a second, or
thirty seconds have passed: a page that never goes quiet is read as it stood.

**The same page is parsed twice on a successful URL fetch**, once by the ladder
to decide whether to climb and once by the caller, and three times in a crawl,
which reads its links as well. Deterministic, so the cost is time rather than
correctness; next to a second's delay between pages, it is not the time that
matters.

## In crawling

**The browser's own requests are not paced.** Every request the crawler makes
waits its site's delay -- robots.txt, sitemaps, each redirect hop, each rung --
but a page that climbs to the browser is loaded as a browser loads it, images,
scripts and all, inside one paced call. The ladder climbs only on a
measurement, so it is the rare page; it is still more requests than one.

**An unguarded browser follows a redirect itself.** With `allow_private=True`,
the default outside the MCP server, the browser rung is not routed, so a
redirect off the site it was sent to is seen only where the page landed: that
page is kept out of a crawl of one site, but the other site has had its
request. The HTTP rung, and the browser when guarded, refuse the hop before it
is asked.

**Pacing is kept per process.** When each site was last asked is remembered for
the whole process, and a site is asked by one caller at a time, so one crawl
after another, two at once, and single fetches beside them keep the delay; two
processes do not share it, and neither do `sluicer map --plain | sluicer batch
-`, whose second command starts as the first ends; `sluicer crawl --template
sitemap` reads the same pages in one process.

**The pace counts the browser's time too.** A request's seconds are the whole
call's, so a page the browser renders is timed with its rendering, half a
second or more, and the site is asked that much less often after it. It errs
on the slow side, which is the side a guess about someone else's server
should err on.

**A retry waits on a worker.** A page asked again waits its backoff in the
thread that fetched it, so while one site is being retried, one of the sites
a crawl asks at once is that one. The backoff is bounded by `max_delay`, a
minute by default and ten seconds for the MCP tools.

**A part of a site is its directory.** The crawl's memory of which rung each
part needed goes by the address's path without its last segment. A site whose
listings and products share a directory (`/shop?page=2` and `/shop?id=7`) is
one part, and is paced as the whole site was before.

**The Shopify template reads what `/products.json` serves.** It pages with
`?page=N`, as the file is served to anyone, and stops at the first short
page; a shop that hides products from that file, or a Shopify version that
stops honouring the page number, gives what the file gives. The file names
no currency, so neither does the summary. It is tested on local fixtures of
the file's shape, never against a shop.

**A single fetch waits a second, not a site's `Crawl-delay`.** A crawl reads a
site's `Crawl-delay` and waits it; a single fetch -- the command line, an MCP or
HTTP API call -- waits a second after the site's last request, whoever made
it, and then asks robots.txt, the page and any climb one after another, as one
visit. A redirect to another site inside that fetch is asked in the first
site's turn, not its own.

**A site is a host, not a domain.** `shop.example.com` and `blog.example.com`
are two sites, paced apart and, for a crawl kept to its site, not followed
between. The base install has no list of public suffixes to tell a registrable
domain from a host, and a wrong guess would pace two strangers as one. `www.`
is the one prefix folded.

**Two spellings of one page can both be fetched.** `index.html` is not folded
into its directory -- on books.toscrape.com, `/` and `/index.html` are one page
and both were read -- and neither is a tracking parameter stripped or a query
reordered, since a server may read each differently. A redirect and a
canonical are what fold two addresses into one.

**A file is told by its extension.** A PDF at an address without one is
fetched, up to 16 MiB, and read as a page that declares nothing.

**Only `<a href>` and `<area href>` are links.** Navigation a script builds, a
form, an `<iframe>` or a `<link rel="next">` is not followed. A page that
climbs to the browser is read for links in the HTML the browser rendered.

**Headers are read for `nofollow` and the canonical, and for nothing else.**
An `X-Robots-Tag` saying `nofollow` or `none`, for every crawler or for
`sluicer`, stops the walk from that page as the `<meta>` does, and a canonical
in the `Link` header counts with the head's. `noindex` is reported in the
page's `rights` and not acted on: a crawl that reads a page is not an index.

**`Request-rate` is read as a rate, all day.** A rate given for hours of the
day (`1/5s 0900-1700`) is kept at every hour.

**A time budget stops starting, it does not interrupt.** A page already being
fetched when the time is up finishes, within its requests' own bounds: twenty
seconds for each plain HTTP request, its robots.txt's included, and thirty for
each thing a browser waits on. An MCP answer can take that much longer than its
minute.

**A crawl resumes only with the options it was written with.** The file's
order is the order those options take the site in, so another start, depth or
pattern is refused rather than mixed. A larger `--max-pages` is the exception
that is safe, and continues.

**A redirect target in a batch goes to the end.** A batch reads its list in
order, and a cross-site redirect's target after the list, in that site's turn.

**Sitemaps are XML or plain text.** An RSS or Atom feed, which the protocol
also accepts, is reported as not a sitemap. A sitemap heavier than 16 MiB
inflated is not read at all, where the protocol allows 50 MB. `lastmod` is
passed on as written, never parsed.

**A crawl never climbs to the stealth rung and never skips robots.txt.** The
single-page commands keep `--stealth` and `--no-robots` for a person with a
reason; a crawl, which asks a site for many pages on one decision, has neither.

## In the MCP server

**The address filter covers every request, and the browser's names are its
own.** The server refuses addresses off the public internet before any
request, and both rungs judge every address a redirect names before asking it.
The HTTP rung connects only to the addresses it checked, so DNS rebinding
reaches nothing there. The browser rung routes every request the page makes --
images, frames, `fetch()`, websockets -- through the same judgement and never
lets the browser follow a redirect itself, and pages get no service workers,
which fetch outside any route, and no WebRTC. The requests the browser makes
for a page, which no route sees -- a speculation rule's prefetch and prerender
-- go with every other connection of a guarded page through a proxy on
loopback that judges them and connects only where it checked, so the
browser's names are resolved there too. What remains: a browser elsewhere
(`SLUICER_CDP_URL`) cannot reach that proxy, and is judged by the routes
alone, which a speculation rule and a name that rebinds reach past. SECURITY.md
says so too.

**A page is bounded at 16 MiB, and one answer to an agent at 75,000 bytes.**
Claude Code puts an answer over 25,000 tokens in a file rather than the
conversation, and 75,000 bytes of JSON stay under that. A longer page or
markdown is read in slices of at most 60,000 characters, fewer when their
bytes would pass the bound, each answer saying where the next starts
(`next_offset`). Every other tool leaves out what its answer can do without
and says what: `extract_declared` its records, then its conflicts, then its
heaviest summary answers, by name (`summary_left_out`); a feed's last items, a
map's last addresses, an extractor's last rows, an audit's last records, each
counted; a crawl the heaviest summary answers of any page, then its last
pages. An answer nothing can be cut from, an extractor learnt from pages with
a huge value, is `too_large`: `sluicer compile` writes it to a file. The HTTP rung stops reading past `MAX_RESPONSE_BYTES`, after
decompression, so a gzip that inflates to gigabytes costs the bound; before
0.3.0 a 200 MB response was measured holding 1.14 GB. The browser rungs are held
to the same bound only once the page is loaded: the browser's own memory is the
browser's.

**A tool's own error answers have `is_error` false.** Two answers are MCP's
failures instead, `isError` true: arguments that do not fit a tool's input
schema, which the MCP SDK refuses before the tool runs, and a call to `sluicer
serve`'s `/mcp` that runs past its time (`timed_out:`). A missing extra, a robots
refusal, a refused address, a failed fetch, a page too heavy and a bad input
come back as results, `{"ok": false, "error": {"code", "message",
"retryable"}}`, not as protocol failures, so an agent that branches only on the
protocol's flag will not notice; one that checks `ok` will. The alternative is
worse: a raised exception becomes `Error executing tool fetch_page` and the
sentence that says what happened is discarded by the SDK. Measured against mcp
2.2.0.

**The output schemas stop at the extractor.** Every tool publishes an output
schema built from `sluicer.mcp_answers`, and `ok` is its one required key.
Records, fields and summary answers are typed; a field's value is any JSON, as
the page declared it, and the extractor object is a plain mapping whose shape
is documented in [extractors](extractors.md), not in the schema.

**The twelve tools are pinned by set equality**, so a thirteenth cannot appear
unnoticed. The HTTP door is held to that same list, not to a second one.

## In the HTTP API

**A call that runs out of time still runs to its end.** The 504 is sent when
the budget runs out, and whatever the call brings later is dropped: a thread
cannot be stopped from outside, so a fetch keeps its worker until its own
timeouts end it: twenty seconds for each plain HTTP request, the body included,
and thirty for each thing a browser waits on. Four
workers bound how many such calls there can be, and a call still waiting for
one when its budget runs out is never started. On SIGTERM, which is what
`docker stop` sends, uvicorn shuts down and then re-raises the signal, so the
process ends at once and a call still fetching ends with it: measured, 0.1 s
after the signal, with a page held for six.

**A status says less than its answer.** `too_large` is 413 for a fetched page
too heavy as much as for a request body too big, although HTTP's 413 is about
the request; one code keeps one status, and `error.url` names the page when it
was fetched. `fetch_failed` is 502 whatever each rung met, a rung's own timeout
included; the message says what each one said. Only the request's own budget is
a 504.

**One token, plain HTTP.** There is no identity per caller, no scope, no rate
limit, and no rotation short of a restart. The server speaks HTTP, not HTTPS;
beyond one machine, TLS belongs in front of it. [Security](security.md) says
what that leaves.

**The `Host` check holds on loopback only.** Listening on every interface, any
`Host` is answered, since the name other machines use to reach it is not one it
can know. There the token is what protects it, and with
`--allow-unauthenticated`, nothing in the server does.

**No CORS, no streaming, no batch.** A browser app on another origin needs the
middleware recipe in [the HTTP API](http-api.md). A call answers once, when it
is done, and a list of URLs handed to `compile_extractor` is one request inside
one budget: six pages that each take the plain HTTP rung's twenty seconds use
all of the default 120.

**`/mcp` keeps no session and sends nothing unasked.** It answers a POST
only: no notification or progress while a call runs, no resumable stream, and
a call's answer arrives when it is done, as JSON. A client's own timeout below
the server's `--timeout` gives up on a call the server is still running: n8n's
MCP nodes wait 60 seconds unless told otherwise. A page in a browser on
another origin is refused, a tool that connects from its own page on another
port of this machine included.

**Most bounds are not options of the command.** The 16 MiB body, the four
workers and the 64 connections are arguments of `build_app` or constants beside
it; only the time budget is a flag of `sluicer serve`. With 63 connections
inside a request, uvicorn answers 503 in plain text, not in the answers' JSON.

**The listing speaks MCP's names.** `GET /v1/tools` is the SDK's own listing,
so its keys are `inputSchema` and `outputSchema`, while the answers' keys are
snake_case, as the tools write them. Renaming either would make one of them a
copy.

**A tool without an output schema cannot be served.** It has no structured
answer, and the door answers 500 rather than make one up. Every tool here has
one, and a test holds them to it.

**The live check provokes every error but `internal_error`**, which only a bug
in the server can. The suite provokes it with a tool that raises.

## In the shape of the code

**A new reader answers summary questions only once the summary is taught.**
Adding a vocabulary is one entry in `sluicer.declared.readers.READERS`: its
name, its read function, whether it describes things or the page, and the
`extract` flag that turns it on if it is optional. The order of that tuple is
the precedence, and the fold, the `sources` list and `ABOUT_A_THING` all read
it. The summary still asks the document-level vocabularies by name, since
`og:title` and `twitter:title` are questions about what each one says, so a
new document-level reader fills records but answers no summary question until
`sluicer.summary` knows its keys. Until 0.3.0, a reader was written into three
places and `merge` took eight parameters.

**A hand-built `Record` can be silently inert.** `Record(type="Product")`
constructed by hand gets an empty `types`, and the fold reads `types`, so that
record never folds with anything. Nothing validates that the two agree. A
`__post_init__` would close it.

## In the tests

**The no-model test is a floor, not a ceiling.** It scans the source for the
network clients and the hosted and local model clients by name -- `openai`,
`anthropic`, `google.genai`, `litellm`, `ollama`, `transformers`, the
`langchain` and `llama_index` families and more -- in `import` statements and in
module names handed to `import_extra`, `import_module` and `__import__` as
strings. It does not catch `ftplib`, or a name built at runtime. `socket` is
allowed in `fetch/address.py`, for name resolution, and in `fetch/wire.py`, and
`http.client` in `fetch/http_rung.py`: those two are the HTTP rung, the one
client in the package.

**Determinism is tested within one process.** Two calls, one fixture, same
answer. Stability across processes and across two pages built from the same
template is what the design actually promises, and neither is covered yet.

## In the repository

**The gates cover `src`, and only what they can see.** ruff, mypy `--strict`
and a 97% coverage floor run on every push and pull request. What they do not
reach is worth naming. mypy checks `src` and not `tests`, so a test can still
say something untrue about a type. lxml ships no type information, so every
element this package touches is `Any` to the checker and the annotations
around it are documentation rather than proof. The optional extras are
imported by name at call time, which is the whole point, and means no checker
ever sees them -- the `with-extras` job is the only thing that does, and the
microformats reader was confirmed against the real `mf2py` by hand, in a
throwaway environment, because the suite fakes it. And a
gate answers "is this well formed", never "is this right": four review passes
found things no rule set encodes, and the gates were added so those passes
can spend their attention elsewhere, not so they can stop.
