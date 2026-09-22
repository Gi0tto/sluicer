# Known limits

Everything here is deliberate, measured, and open. It is not a bug list: it is
the set of places where Sluicer currently stops, written down so nobody has to
rediscover them, and so the next plan inherits decided questions instead of
surprises.

## In the extraction path

**A reference is followed one hop.** A JSON-LD node that names another by
`@id` gets that node in its place, so an article's author and publisher arrive
whole; a reference inside the node that replaced it stays a reference. Measured
on a Yoast blog post, following every reference tripled the output, because
every record re-expanded the same graph.

**The summary answers by rule, not by judgement.** Its subject is the first
declared record about a thing, ahead of pages, sites and furniture, and each
question takes the first candidate in a stated list. A page that misuses a term
is answered by that misuse: Wikipedia's `headline` is its short description, so
its summary title is "hydraulic structure" rather than "Sluice".

**Gap-filling targets the first record of a type.** When a page declares several
records sharing a type, a lower-precedence reader fills the first one in document
order. On a page whose `@graph` opens with a `BreadcrumbList`, an `og:title`
lands on the breadcrumb rather than the product. Document order is the only
deterministic signal available in this slice; trust scoring is where a better one
can come from.

**A declared encoding can still disagree with the bytes.** Bytes are decoded
the way a browser decodes them: a byte order mark, then an XML declaration or a
`<meta charset>` anywhere in the head, then UTF-8 if the bytes are valid UTF-8,
then windows-1252. A page whose declaration lies about its bytes is read as it
declares, as a browser reads it. A caller holding the transport's charset header
has better information than the page, and nothing currently accepts it. When
only text is available and lxml cannot parse it, the retry reads it as UTF-8
whatever the document claims, because the text has already been decoded.

**RDFa is read as Lite, not as a graph.** `declared` covers JSON-LD, microdata,
microformats, RDFa, Dublin Core, OpenGraph and the Twitter card today. The RDFa
reader stops where the graph begins: `vocab`, `prefix`, `typeof`, `property` and
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
`title` lands on the same key as an `og:title`; and RDFa folds `vocab` and
`prefix` away, so two vocabularies sharing a term name share a key. The
precedence decides who wins -- JSON-LD, microdata, microformats, RDFa, Dublin
Core, OpenGraph, the Twitter card -- so the answer is stated and stable rather
than decided by the order the page's author typed. What is lost is the loser: it
is dropped, not kept under a qualified name. Microformats keeps its own type
spelling while it is at it: an `h-entry` records `@type` as `h-entry`, so it
never folds with a schema.org `Article` that means the same thing.

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
within twenty-four hours, not immediately, and the cache is unbounded in the
number of hosts it remembers. On a long-running server that is a slow leak and a
slow update; both are acceptable today and neither is measured.

**A redirect is checked where it landed, after it landed.** A page whose
redirects ended on another host is refused if that host's robots.txt says no,
and with `allow_private=False` one that ended on a private address is refused
too -- but the request has already been made by then. Plain HTTP refuses to
follow a redirect into a private address on its own; the browser rung does not,
so behind `allow_private=False` a browser can still be steered into one by a
redirect, and only the answer is withheld.

**`Crawl-delay` is read by nobody.** Sluicer fetches one page when you ask for
one page, so there is nothing yet to pace, and that stops being true the day it
crawls.

**The stealth rung does not announce itself, deliberately.** It exists to not be
recognised, and announcing yourself and then evading is incoherent. It is no
longer part of the automatic ladder for the same reason: climbing on a
measurement from plain HTTP to a browser is a change of cost, while climbing
from announcing yourself to hiding is a change of character, and it should not
happen to a caller who never asked for it.

## In fetching

**A challenge is detected by matching words against the whole page.** A page
whose prose legitimately contains "just a moment" climbs a rung it did not need
to. The cost is one wasted browser fetch and a reason string that names the
marker it matched, so the mistake is visible rather than silent.

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

**The redirect-to-login measurement named in the design is not implemented.**
The other two, a refusal and a skeletal body, are.

**The fetch layer holds bytes and passes text.** `load()` learned to take bytes
so a document's own encoding wins, and the adapter still hands it
`response.html_content`, which scrapling has already decoded. Deciding which of
the two is more trustworthy needs a measurement nobody has taken yet.

**The same page is parsed twice on a successful URL fetch**, once by the ladder
to decide whether to climb and once by the caller. Deterministic, so the cost is
time rather than correctness.

## In the MCP server

**The address filter is a filter.** The server refuses addresses off the public
internet before a request and after its redirects, which stops an agent being
told to read `http://localhost:8080` or a cloud metadata endpoint. It does not
stop DNS rebinding, and a redirect the browser rung follows into a private
address has been requested by the time it is refused. SECURITY.md says so too.

**What reaches an agent is cut, what the server holds is not.** `fetch_page`
returns at most 200,000 characters and says when it cut; the fetch underneath
has no size limit, and a 200 MB response was measured holding 1.14 GB.

**A missing extra answers with `is_error` false.** It is a result, not a
protocol failure, so an agent that branches only on that flag will not notice.
The payload is unmistakable and the alternative is worse: a raised exception
becomes `UnexpectedToolError: Error executing tool fetch_page` and the install
sentence is discarded by the SDK. Measured against mcp 2.2.0.

**Nothing validates the shape a tool returns.** `structured_content` is None in
mcp 2.2.0 even for a tool annotated as returning a mapping, so the contract
between us and an agent is prose, not schema.

**The three tools are pinned by set equality**, so a fourth cannot appear
unnoticed.

## In the shape of the code

**Adding a reader touches three places.** The reader names are written into
`merge`'s keyword signature, into the fold's source labels, and into the tuple
in `api`. The cost is now measured rather than predicted: four readers arrived
this way, `merge` takes seven parameters, and each addition was a breaking
change to a published signature plus edits in two modules -- the microformats
one also had to be threaded through as a flag, since it is optional. The seam
belongs one level up, as a sequence of named findings or a registry. Worth
moving before the first release, cheap while nobody depends on it.

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
