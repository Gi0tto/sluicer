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

**A guess from the visible page only when asked, and not yet on the
scoreboards.** The summary holds only what a page declares. `--visible`
(`extract(..., visible=True)`, `extract_declared`'s `visible`) guesses the
heading, byline and dates a page shows, in `visible`, each with its element
and rule; its rules were made on WCXB's development pages only, and no
scoreboard has measured it yet (`bench/PREREG.md`). Trafilatura, which
`sluicer[markdown]` installs, can guess too: `examples/04_a_guess_from_the_visible_page.py`
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
regions CLDR 48.2 covers at its modern level (`sluicer/calendar_names.py`,
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
`resource` are read, and chained subjects, typed literals and inference are not.
Anyone who needs the full graph is better served by a triple store than by this
pretending.

**Microformats is off unless you ask, and flattened when you do.** It is the
only reader behind an extra, because it is the only one that cannot be written
in the `lxml` the base install already carries: `mf2py` is the reference parser
and costs twelve packages against a base install of three. `extract(html,
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
`title` lands on the same key as an `og:title`. RDFa shortens schema.org terms
to the names the other readers use and keeps other vocabularies' full IRIs, so
only schema.org terms collide across vocabularies. The precedence decides who
wins -- JSON-LD, microdata, microformats, RDFa, Dublin Core, OpenGraph, the
Twitter card, HTML's own metadata names -- so the answer is stated and stable
rather than decided by the order the page's author typed. What is lost is the
loser: it is dropped, not kept under a qualified name. Microformats keeps its
own type spelling: an `h-entry` records `@type` as `h-entry`, so it
never folds with a schema.org `Article` that means the same thing.

**A place is an XPath into the page as lxml parsed it, not as a browser
did.** libxml2 builds its own tree: it adds no `<tbody>` to a table, which a
browser always does, and it mends broken markup its own way, so a place such
as `/html/body/table[1]/tr[1]/td[1]` may select nothing in a browser's
developer tools; the same page parsed by `sluicer.document.load` finds it.
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

**Healing matches by values.** A field is moved only when its new place holds
values it held before; a same-shaped field with new values is not a match, so a
redesign that changes the markup and every value at once is reported as fields
vanished and new, not as moves. The samples are five values, so on a listing
whose rows changed completely between learning and healing, heal finds nothing
to match and says so.

**The thresholds are fixed.** 20% of rows may lack a required field, half a
field's values must keep its shape, and a shape needs five values to be learnt
or checked. Editing the JSON changes what was learnt, not the thresholds.

**Two free-text columns can swap unnoticed** on a page the extractor was not
learnt from: a title and a brand keep their shapes, and neither reads as an
amount or a date. A swap is caught when one side read as an amount or a date
(the `reads` check), or became the same in every row (the `values` check).

**Extractors are measured on 44 pairs of captures from 25 sites.** The drift
benchmark (docs/drift.md) shows no silent failure and no false alarm there, and
that is a small sample: mostly news and link aggregators, no real shop, and
heal judged only where the two captures share items, which on news pages they
rarely do.

## In announcing ourselves

**The user agent on the wire is verified by hand, not by the suite.** Both the
HTTP and the browser rung were confirmed on 2026-09-22 against a live request,
and the server saw `Sluicer/<version> (+https://github.com/Gi0tto/sluicer)` from
each. The suite cannot re-check it, because it must never open a socket, and a
faked library accepts whatever keyword you hand it. That gap is real and it has
already cost once: the browser rung was passing the name in `extra_headers`,
which the browser context silently overrides, so the tests passed while every
site saw Chrome. It now passes `useragent`, which reaches the wire. The same
check on 2026-09-22 found scrapling's defaults adding `Referer:
https://www.google.com/` and a Chrome TLS fingerprint under our name; both are
now turned off, and a local server confirmed neither reaches it. If you change
how a rung is built, ask a real server what it saw.

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
happen to a caller who never asked for it.

**Normalisation reads English and ISO, and refuses what is ambiguous.** A date
is read from ISO 8601 and its common variants, RFC 2822, JavaScript's
`Date.toString()`, and English month names before or after the day or after
the year; "16 juin 2025" is not read. Of the 669 dates the benchmarks' pages
declare, 6 are not read, each on purpose: two all-number dates
(`08/21/2025`), two six-digit ones (`240221`) and a date with a time glued to
it (`Jan 24, 2026T00:00:00-05:00`), twice. None was in another language, but
the pages are nearly all English, so that says little about other languages. An all-number date other than ISO's, an
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

**The cache serves single pages.** `--cache` is read by `extract`, `inspect`,
`markdown`, `audit` and `diff`, not by `crawl` or `batch`, whose state file is
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
marker, so a mistake either way is visible.

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
can see it is the HTTP rung's answer to a page that wanted a browser. When every
rung failed, `FetchFailed` says what each one said; nothing is returned that
could pass for a page.

**A redirect to a login page is not detected as a refusal.** A refusal status, a
challenge page and a skeletal body are.

**The browser decodes its own pages.** The HTTP rung decodes the bytes itself,
with the sniffing `load()` uses and the response's own charset where the HTML
standard puts it, between a byte order mark and the page's declaration. The
browser rungs hand over the DOM the browser built, decoded by the browser.

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
the whole process, so one crawl after another keeps the delay; two processes
do not share it, and neither do `sluicer map --plain | sluicer batch -`, whose
second command starts as the first ends. One request at a time per site holds
within a crawl; two crawls of one site running at once in one process each
keep their own.

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
which fetch outside any route. What remains: the browser resolves names in its
own network stack, so a name that answers differently between the check and the
connection is reached from there. SECURITY.md says so too.

**A page is bounded at 16 MiB, and one answer to an agent at 60,000
characters.** A longer page or markdown is read in slices, each answer saying
where the next starts (`next_offset`), and `extract_declared` leaves its records
out, counted, past 75,000 bytes: Claude Code puts an answer over 25,000 tokens
in a file rather than the conversation. The HTTP rung stops reading past `MAX_RESPONSE_BYTES`, after
decompression, so a gzip that inflates to gigabytes costs the bound; before
0.3.0 a 200 MB response was measured holding 1.14 GB. The browser rungs are held
to the same bound only once the page is loaded: the browser's own memory is the
browser's.

**Every error answer has `is_error` false.** A missing extra, a robots
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

**The ten tools are pinned by set equality**, so an eleventh cannot appear
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

**Most bounds are not options of the command.** The 16 MiB body, the four
workers and the 64 connections are arguments of `build_app` or constants beside
it; only the time budget is a flag of `sluicer serve`. Past 64 connections,
uvicorn answers 503 in plain text, not in the answers' JSON.

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
strings. It does not catch `http.client`, `ftplib`, or a name built at runtime.
`socket` is allowed in one file, `fetch/address.py`, for name resolution.

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
