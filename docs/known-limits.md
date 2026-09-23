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
declared record about a thing, ahead of pages, sites and furniture, and each
question takes the first candidate in a stated list. A page that misuses a term
is answered by that misuse, except where a rule was written for it: Wikipedia
puts its short description in `headline`, so when only `name` appears in the
title the page shows, `name` is the title.

**Gap-filling targets the first record of a type.** When a page declares several
records sharing a type, a lower-precedence reader fills the first one in document
order. On a page whose `@graph` opens with a `BreadcrumbList`, an `og:title`
lands on the breadcrumb rather than the product. Document order is the only
deterministic signal available; the template contract planned in the roadmap is
where a better one can come from.

**A declared encoding can still disagree with the bytes.** Bytes are decoded
the way a browser decodes them: a byte order mark, then an XML declaration or a
`<meta charset>` anywhere in the head, then UTF-8 if the bytes are valid UTF-8,
then windows-1252. A page whose declaration lies about its bytes is read as it
declares, as a browser reads it. A caller holding the transport's charset header
has better information than the page, and nothing currently accepts it. When
only text is available and lxml cannot parse it, the retry reads it as UTF-8
whatever the document claims, because the text has already been decoded.

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

**Two same-shaped text columns can swap unnoticed** on a page the extractor was
not learnt from: a title and a stock line are both letters. The `values` check
catches a swap only when one side becomes the same in every row.

**How often extractors survive real redesigns is not measured.** The fixtures
are written by hand; the benchmark on real before-and-after pages is next on the
roadmap.

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
by both rungs (see the MCP section below).

**`Crawl-delay` is read by nobody.** Sluicer fetches one page when you ask for
one page, so there is nothing yet to pace, and that stops being true the day it
crawls.

**The stealth rung does not announce itself, deliberately.** It exists to not be
recognised, and announcing yourself and then evading is incoherent. It is not
part of the automatic ladder for the same reason: climbing on a
measurement from plain HTTP to a browser is a change of cost, while climbing
from announcing yourself to hiding is a change of character, and it should not
happen to a caller who never asked for it.

**Normalisation reads English and ISO, and refuses what is ambiguous.** A date
is read from ISO 8601 and its common variants, RFC 2822, and English month
names; "16 juin 2025" is not read. An all-number date other than ISO's, an
amount whose only separator has exactly three digits after it (`1,299`), and a
bare `$`, `¥` or `kr` have no normalised value, since each means two things
somewhere. Indian digit grouping (`12,34,567`) is refused too. The currency
list is ISO 4217's as SIX published it on 2026-09-17, and is only as current as
that.

## In fetching

**A challenge is detected by words, on a page that is not content.** A title
that is the challenge ("Just a moment...") counts on any page; a marker anywhere
else counts only on a page that declared nothing about a thing and carries less
than 1,500 characters of text. Until 0.3.0 any marker anywhere counted, and an
article quoting "just a moment", or any page carrying Cloudflare's bot-detection
script, bought a browser it did not need. A short challenge page that declares a
record would now be missed; none has been seen. The reason string names the
marker, so a mistake either way is visible.

**A legitimately empty body is treated as a failed rung.** A site that answers
200 with nothing costs a climb. A response with no HTML is not a page, and the
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
to decide whether to climb and once by the caller. Deterministic, so the cost is
time rather than correctness.

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

**A page is bounded at 16 MiB, and what reaches an agent at 200,000
characters.** The HTTP rung stops reading past `MAX_RESPONSE_BYTES`, after
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

**The six tools are pinned by set equality**, so a seventh cannot appear
unnoticed.

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
