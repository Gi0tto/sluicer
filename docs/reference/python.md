# Python

The functions and types a program calls, with their signatures and their
own docstrings. Generated from the code by `scripts/reference.py`.

## Reading a page

### `sluicer.extract`

```python
extract(
    html: str | bytes,
    url: str | None = None,
    induce: bool = False,
    microformats: bool = False,
    headers: Mapping[str, str] | None = None,
    visible: bool = False,
) -> Extraction
```

Read the structured data ``html`` declares, merged, with its provenance.

**Arguments**

- `html`: the page. Bytes are best: the page's own charset is then honoured (see ``sluicer.document.load``).
- `url`: the address the page came from, used to resolve its links.
- `induce`: when the page declares nothing about the things on it, also read the rows its markup repeats; those fields say ``source="induced"``. Never fills a gap in a declared record.
- `microformats`: also read microformats2. Off by default; needs ``sluicer[microformats]``.
- `headers`: the response's headers, when the page came over HTTP. A canonical, ``hreflang`` alternates and the next and previous pages in its ``Link`` header join the markup's in ``links`` and the summary's ``url``; ``X-Robots-Tag`` and TDMRep's headers are reported in ``rights["http"]``; the ``Content-Type`` charset decodes bytes, ahead of the page's own declaration, as a browser does. ``Fetched.headers`` is this.
- `visible`: also read what the page shows and may not declare -- its heading, byline, publication and update dates -- into ``visible``, each answer a guess, never into the summary.

**Returns**

An ``Extraction``: the ``summary``, the ``records`` (a record with no field is never reported), and the ``sources`` that found something, in the order of precedence -- JSON-LD, microdata, microformats, RDFa, Dublin Core, OpenGraph, the Twitter card, HTML's own meta names.

**Raises**

- `MicroformatsExtraMissing`: ``microformats=True`` without the extra.
- Nothing else: any input, however broken, is read or reported empty.

Why the order is what it is, and when induction runs, is in
``docs/design-notes.md``.

### `sluicer.Extraction`

```python
class Extraction:
    url: str | None
    summary: dict[str, SummaryField]
    normalised: dict[str, str]
    conflicts: list[Conflict]
    records: list[Record]
    sources: list[str]
    links: Links
    rights: Rights
    visible: dict[str, Guess]
```

What Sluicer found in one page, and where it came from.

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

### `sluicer.SummaryField`

```python
class SummaryField:
    value: str
    source: str
    key: str
    where: str | None
```

One answer, the reader that declared it, and the key it was read from.

``value`` is text. ``source`` is a reader name, as on ``Field``, with
``"html"`` also covering ``<title>``, ``<html lang>``, ``<link
rel=canonical>`` and meta names outside any vocabulary. ``key`` is what was
read: ``Product.offers``, ``og:title``, ``<title>``, ``meta name=author``.
``where`` is where on the page it was declared, as ``Field.where``: an
XPath, for JSON-LD with a pointer to the value after ``#``. None when the
key is the whole of what is known, as for ``og:title``.

### `sluicer.Record`

```python
class Record:
    type: str | None
    types: tuple[str, ...]
    fields: dict[str, Field]
    source: str | None
    where: str | None
```

A set of fields describing one thing on the page.

``type`` is the first type the page declared for this thing; ``types`` is
every type it declared (Yoast writes ``["Person", "Organization"]``), and
the whole tuple is what folding matches on.

``source`` is the reader that declared the record: ``"induced"`` for a row
induction found, and None for the one record the document-level
vocabularies make when nothing else declared a thing. Fields folded in from
other readers keep their own sources.

### `sluicer.Field`

```python
class Field:
    value: JsonValue
    source: str
    where: str | None
```

One extracted value and the reader that produced it.

``value`` is text for a scalar, and for a nested value the JSON the page
declared, with every leaf as text.

### `sluicer.induce`

```python
induce(doc: Document, minimum: int = 3) -> list[Record]
```

Return one record per row of the page's most promising repeated shape.

**Arguments**

- `doc`: the parsed page.
- `minimum`: the fewest repetitions that count as a listing.

**Returns**

Records whose fields all have ``source="induced"`` and are named by where they sit (``div.meta>span.sku``), or ``[]``. Groups are tried in ranked order and the first that yields records wins: a group whose members hold bare text, in no element of their own, has nothing to name a field after and yields none.

## The main content as markdown

### `sluicer.to_markdown`

```python
to_markdown(
    html: str | bytes,
    url: str | None = None,
    front_matter: bool = False,
) -> str
```

Return the page's main content as markdown, or ``""`` when it has none.

**Arguments**

- `html`: the page, passed to trafilatura as given. Prefer bytes: it detects the encoding from them, including a ``<meta charset>``.
- `url`: the address the page came from, used to resolve its links.
- `front_matter`: open the markdown with a YAML block of what the page declares about itself -- title, author, dates, url, and the rest of the summary -- and where each answer came from, the way static-site generators and retrieval pipelines read a document's metadata. The text itself is still trafilatura's.

**Raises**

- `MarkdownExtraMissing`: trafilatura is not installed.

## What a value means

### `sluicer.normalise.iso_date`

```python
iso_date(text: str) -> str | None
```

``text`` as an ISO 8601 date or date-time, or None when it is not sure.

Read: ISO 8601 and its common variants (a space for the ``T``, an offset
without a colon, a trailing ``UTC``), RFC 2822 (``Tue, 03 Jun 2025 10:00:00
GMT``), a month's name in any language CLDR covers either side of the day
(``Jun 16, 2025``, ``16 June 2025``, ``10. Mai 2023``, ``10 de mayo de
2023``, Russian's with its year mark) or after the year (PubMed's ``2023 Jan 7``,
Hungarian's ``2023. május 10.``), a weekday before it with its comma,
the numbers with units Chinese, Japanese and Korean write (``2023年5月10日``),
and JavaScript's ``Date.toString()`` (``Fri Oct 24 2025 03:22:33 GMT+0000
(GMT)``). A Thai month's year from 2400 on is the Buddhist era's, and is
converted. Not read: all-number forms other than ISO's, since
``03/04/2025`` is March in one country and April in another.

### `sluicer.normalise.amount`

```python
amount(text: str) -> str | None
```

``text`` as a decimal amount with a point, or None when it is not sure.

A currency symbol or code around the number is dropped. When both a point
and a comma appear, the last one is the decimal separator. When only one
appears once, it is the decimal separator unless exactly three digits follow
it: ``1,299`` and ``1.299`` are refused, since each is a thousand somewhere
and a little over one somewhere else (``0.999`` is not ambiguous). Digits
grouped by a separator, a space or an apostrophe are grouped in thousands,
``1 299,00`` or ``1'299.00``, or the text is refused: ``12 50`` is not 1250.
A number JSON writes with an exponent, ``1.5e3``, is the amount it names.

### `sluicer.normalise.currency`

```python
currency(text: str) -> str | None
```

``text`` as an ISO 4217 code, or None when it names no one currency.

### `sluicer.normalise.gtin`

```python
gtin(text: str) -> str | None
```

``text`` as a GTIN whose check digit is right, or None.

GTIN-8, -12, -13 and -14, and an ISBN-13, which is a GTIN-13; spaces and
hyphens dropped. A wrong check digit is a typo or an invention, and the
number it would normalise to identifies some other product, or none.
Measured on the pages as served that the scoreboard holds: 12 of 17 GTINs
were wrong.

## Fetching

### `sluicer.fetch.fetch`

```python
fetch(
    url: str,
    rungs: Sequence[tuple[str, Rung]] | None = None,
    obey_robots: bool = True,
    stealth: bool = False,
    robots_reader: Callable[[str], str | None] | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = 16777216,
    proxy: str | None = None,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
    memory: RungMemory | None = None,
) -> Fetched
```

Fetch ``url``, climbing to a costlier rung only when a measurement says so.

**Arguments**

- `url`: an http(s) address.
- `rungs`: ``(name, rung)`` pairs, cheapest first; plain HTTP then a browser by default, the browser when the ``browser`` extra is installed (without it, a climb to it fails and is recorded, and the HTTP page comes back). Injected so tests stay off the network. The default rungs are the real web, so a fetch with them holds the site in ``sluicer.fetch.gate`` for its whole length -- robots.txt, the page, any climb -- a second after anyone's last request to it. Injected rungs are the caller's to pace, as a crawl paces its own.
- `obey_robots`: ask the site's robots.txt first (the default), and again for the host a redirect ended on.
- `stealth`: append the stealth rung, which does not announce itself. Never automatic; it needs the ``stealth`` extra.
- `robots_reader`: how robots.txt is read; built from the cheapest rung by default.
- `allow_private`: when false, refuse addresses off the public internet: the one asked for before any request, and every one a redirect or the page itself names before it is requested. The MCP server sets it.
- `resolve`: the name lookup ``allow_private`` decides with.
- `max_bytes`: the most a page may weigh; heavier is ``ResponseTooLarge``, and never a reason to climb.
- `proxy`: the proxy the default rungs and the stealth rung go through; ``SLUICER_PROXY`` when None, and none when that is unset. The environment's ``HTTPS_PROXY`` is never used. Through a proxy the private-network check still judges every address here, but the connection is the proxy's: see SECURITY.md.
- `headers`: sent with every request for the origin asked -- scheme, host and port -- and left off any hop a redirect takes elsewhere: an ``Authorization``, a header an API wants. Never ``User-Agent``: Sluicer always says who it is, so a site can refuse it.
- `cookies`: sent as one ``Cookie`` header the same way, and set in the browser's context for the host asked, where a browser's own cookie rules apply (a cookie belongs to a host, not a port).
- `memory`: what each site needed before, and learns what this page needs: a site whose page came back only from the browser starts its next page there. The process's (``STICKY``) with the default rungs; none with injected ones unless handed one.

**Returns**

The ``Fetched`` page, with every climb, the final URL, and how long each rung took.

**Raises**

- `RobotsRefused`: the site's robots.txt disallows the URL.
- `SiteRefused`: the page the ladder was left with is a challenge page.
- `PaymentRequired`: a rung was answered 402; no other rung is asked.
- `AddressRefused`: the address, or one a redirect led to, is not http or https; or ``allow_private`` is false and it is private.
- `ResponseTooLarge`: the page is heavier than ``max_bytes``.
- `RedirectRefused`: an injected rung was given a rule for redirects, and a hop broke it.
- `ValueError`: ``headers`` hold a ``User-Agent``, or a header the transport writes, or a header or cookie that would break the request; or they were given with injected ``rungs``, which send what their caller built them to, or with ``stealth``, which sends nothing that says who is asking.
- `FetchFailed`: every rung failed, the URL is invalid, or its robots.txt could not be read.
- `FetchExtraMissing`: ``stealth`` was asked for and the ``stealth`` extra is not installed.

### `sluicer.fetch.Fetched`

```python
class Fetched:
    url: str
    html: str
    status: int
    rung: str
    climbs: list[Climb]
    seconds: float
    headers: dict[str, str]
    archived: Capture | None
    cached: CacheHit | None
```

A page, the rung that got it, and every climb along the way.

``url`` is where the fetch landed, after redirects, and is what the page's
relative links resolve against; ``status`` is the HTTP status; ``seconds``
is how long the rung that got it took.

## Extractors

### `sluicer.extractor.compile_extractor`

```python
compile_extractor(
    pages: Sequence[Page],
    listing: bool | None = None,
    names: Sequence[str] | None = None,
    want: Mapping[str, str] | None = None,
) -> Extractor
```

Learn an extractor from pages of one template.

**Arguments**

- `pages`: the pages, each as ``(html, url)``.
- `listing`: learn the listing the pages repeat. None, the default, learns one unless a page declares its own subject -- a product, an article -- whose page it is; a thing declared on one of the listing's rows is not. True looks for one anyway, and with ``want``, requires one.
- `names`: what to call each page in ``learnt_from``; its address by default.
- `want`: example values, by the name each is to have: ``{"price": "41.90", "title": "Brake pad set"}``. When a repeated group's rows hold every one, each in a column of its own -- the first such group, in page order -- they choose the listing and its columns, which are only the ones named. When no one group holds them all, or with ``listing=False``, they are the page's own values, a product page's price and title, each learnt where it sits on the page, the page's own place before its furniture and its listings; with ``listing=True``, no group holding them is an error. A value matches when it says the same with its spaces collapsed, or is the same amount.

**Raises**

- `NothingToLearn`: the pages declare nothing and repeat nothing; or no repeated group holds every example in ``want``, and a listing was asked for or an example is on no page; or a page's own value is in a place another page puts after a label the first gives another of its values, and no label they all say once stands before it: read by its place, it would be another field there.
- `ValueError`: ``want`` with ``listing=False``, or a name that is empty.

### `sluicer.extractor.run_extractor`

```python
run_extractor(
    extractor: Extractor,
    html: str | bytes,
    url: str | None = None,
) -> Run
```

Replay ``extractor`` on one page and check it against what it learnt.

An extractor that checks nothing fails: a run with no checks is a pass
nobody could have earned.

### `sluicer.extractor.heal`

```python
heal(
    extractor: Extractor,
    pages: Sequence[Page],
    names: Sequence[str] | None = None,
) -> tuple[Extractor, list[Change]]
```

Learn ``pages`` again and match what moved to what ``extractor`` knew.

Every old field is matched to at most one new place: the one holding most of
the values it used to hold, else its own, when that still holds values of
the old shape -- a listing's items change between visits. A numbered slot
whose own place is still there never moves to another slot of its group:
the third tag of a row is a count, and one tag turning up in another slot
moved nothing. A field found in none of these ways is vanished, even if
some new field has the same shape, because a guess would move the wrong
column under the old name. A field that moved keeps its old name, so a row
read with the healed extractor has the columns it always had.

**Returns**

The healed extractor, and every change found, in a stable order. Any change in ``LOSSES`` is data the page no longer has.

**Raises**

- `NothingToLearn`: the new pages hold nothing an extractor could be learnt from -- no declared answer, no type, no listing.

### `sluicer.extractor.Extractor`

```python
class Extractor:
    learnt_from: tuple[str, ...]
    summary: dict[str, str | None]
    types: tuple[str, ...]
    listing: Listing | None
    notes: tuple[str, ...]
    version: str
    fields: tuple[PageField, ...]
```

What a template's pages were learnt to hold, as a replayable contract.

``summary`` maps each summary question every page answered to the one shape
of its answers, or None when unknown. ``types`` are the declared record
types every page carried.

### `sluicer.extractor.Run`

```python
class Run:
    url: str | None
    ok: bool
    rows: list[dict[str, str]]
    summary: dict[str, str]
    checks: list[Check]
    fields: dict[str, str]
```

An extractor replayed on one page. ``ok`` is False when any check failed.

## Many pages

### `sluicer.crawl.map_site`

```python
map_site(
    url: str,
    limit: int = 50000,
    max_sitemaps: int = 50,
    min_delay: float = 1.0,
    max_delay: float = 60.0,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = 16777216,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> SiteMap
```

The addresses of ``url``'s site, from its sitemaps or, failing those, the
links on the page at ``url``.

The sitemaps are the ones its robots.txt names, in its order; when it names
none, ``/sitemap.xml`` and then ``/sitemap_index.xml``. An index is followed
to the sitemaps it lists on the same site; one robots.txt names may live
anywhere, since the site vouched for it. Only addresses on the site are
kept -- the same host, with or without ``www.``, http or https -- each once,
in the order the sitemaps list them.

**Arguments**

- `url`: where the site starts; its links are the fallback.
- `limit`: the most addresses kept.
- `max_sitemaps`: the most sitemap files read.
- `min_delay`: the least seconds between two requests to one site.
- `max_delay`: the longest ``Crawl-delay`` waited for; a sitemap behind a longer one is reported unread.
- `time_budget`: seconds after which no further sitemap is asked for.
- `allow_private`: when false, refuse addresses off the public internet.
- `resolve`: the name lookup ``allow_private`` decides with.
- `max_bytes`: the most a sitemap, inflated, or a page may weigh.
- `web`: how the site is reached; the real web by default.
- clock, sleep: the time, injected so a test can pace a map.

**Returns**

A ``SiteMap``, with every sitemap tried and what became of it.

**Raises**

- `FetchFailed`: ``url`` is not an http(s) address, its robots.txt could not be read, or its sitemaps gave nothing and the page failed too.
- `AddressRefused`: ``allow_private`` is false and ``url`` is private.
- RobotsRefused, ResponseTooLarge: the sitemaps gave nothing, and this is what happened to the page.

### `sluicer.crawl.crawl`

```python
crawl(
    start: str,
    max_pages: int = 100,
    max_depth: int = 3,
    same_site: bool = True,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    state: str | Path | None = None,
    induce: bool = False,
    respect_tdm: bool = False,
    min_delay: float = 1.0,
    max_delay: float = 60.0,
    concurrency: int = 4,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = 16777216,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Crawl
```

Crawl from ``start``, following links breadth first, one page at a time
per site, and hand back each page as its turn comes.

**Arguments**

- `start`: where the crawl begins; always taken.
- `max_pages`: the most addresses taken, whatever becomes of them.
- `max_depth`: the most links from ``start``; 0 takes ``start`` alone.
- `same_site`: follow only links on ``start``'s site -- its host, with or without ``www.``, over http or https. A redirect off the site is then refused before the other site is asked.
- `include`: regular expressions; when given, a link is followed only if one of them is found in its address.
- `exclude`: regular expressions; a link in whose address one is found is not followed. Neither applies to ``start``.
- `state`: a JSON Lines file: pages it already holds are not fetched again, and every new page is appended as its turn comes.
- `induce`: also read repeated rows from a page that declares nothing.
- `respect_tdm`: give a page whose site reserves its text and data mining rights (TDMRep: its tdmrep.json, headers or meta tags) as a ``tdm_reserved`` error, never its data.
- `min_delay`: the least seconds between two requests to one site.
- `max_delay`: the longest robots.txt ``Crawl-delay`` waited for.
- `concurrency`: how many sites may be asked at once.
- `time_budget`: seconds after which no further page is started.
- `allow_private`: when false, refuse addresses off the public internet.
- `resolve`: the name lookup ``allow_private`` decides with.
- `max_bytes`: the most one page may weigh.
- `web`: how sites are reached; the real web by default.
- clock, sleep: the time, injected so a test can pace a crawl.
- headers, cookies: ``fetch``'s, sent with every request of the crawl -- pages, robots.txt, sitemaps -- to the origin it asks, and with no hop a redirect takes elsewhere. Never a ``User-Agent``.

**Returns**

A ``Crawl`` to iterate for its ``Page``s.

**Raises**

- `ValueError`: ``start`` is not an http(s) address, or a pattern is not a regular expression; or ``headers`` and ``cookies`` are refused as ``fetch`` refuses them, or given with a ``web`` of the caller's.
- `StateMismatch`: ``state`` holds another crawl.

### `sluicer.crawl.extract_many`

```python
extract_many(
    urls: Iterable[str],
    state: str | Path | None = None,
    induce: bool = False,
    respect_tdm: bool = False,
    min_delay: float = 1.0,
    max_delay: float = 60.0,
    concurrency: int = 4,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = 16777216,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Crawl
```

Read every address in ``urls``, politely, and hand back each page in the
order the addresses were given.

The same scheduler as ``crawl``: one request at a time per site, its delay
between, ``concurrency`` sites at once. No link is followed. A redirect to
another site is not followed inside the fetch: that page says
``redirected_off_site``, and its target is read in its own turn, at the
end of the list, so every site is asked one request at a time however the
list's addresses redirect. An address given twice is read once; one that
is not an http(s) address comes back as a ``bad_input`` page. With
``state``, an address the file already holds is skipped, and every new
page is appended. The other arguments are ``crawl``'s; ``headers`` and
``cookies`` go to every address's own origin, as a list of addresses
handed to ``curl -H`` has them sent to each.

## Feeds

### `sluicer.feeds.read_feed`

```python
read_feed(data: str | bytes, url: str | None = None) -> Feed | None
```

The feed ``data`` is, or None when it is not one.

``url`` is the address the feed came from, which relative links resolve
against. Never raises: a document that is not a feed, or not well formed,
is None.

## Web archives

### `sluicer.warc.read_warc`

```python
read_warc(
    source: str | Path | BinaryIO,
    skipped: Skipped | None = None,
) -> Iterator[WarcPage]
```

Every page ``source`` holds, in file order.

``source`` is a path, ``-`` for standard input, or a binary file object.
``skipped`` counts the page-like records left out, by reason.

**Raises**

- `WarcError`: the file is not a WARC or breaks off inside a record; the pages before the break have been given.
- `OSError`: the file cannot be opened.

### `sluicer.warc.extract_warc`

```python
extract_warc(
    source: str | Path | BinaryIO,
    induce: bool = False,
    microformats: bool = False,
    skipped: Skipped | None = None,
) -> Iterator[tuple[WarcPage, Extraction]]
```

``sluicer.extract`` over every page ``source`` holds, with its headers.

The arguments are ``extract``'s and ``read_warc``'s. A page that declares
nothing is still given, with an empty extraction: that it said nothing is
a finding too.

## What changed

### `sluicer.diff.compare`

```python
compare(before: Extraction, after: Extraction) -> list[Difference]
```

Every summary question, link relation and usage declaration that differs.

In the order of ``sluicer.summary.FIELDS``, then the links, then the
rights, so two runs over the same pair give the same list.

## Audit

### `sluicer.audit.audit`

```python
audit(
    page: str | bytes | Extraction,
    url: str | None = None,
    site: Site | None = None,
) -> Audit
```

Audit what ``page`` declares against what its documentation asks.

**Arguments**

- `page`: the HTML -- bytes are best, as for ``extract`` -- or an ``Extraction`` already made. An ``Extraction`` holds the merged records and not the page, so its records are audited as merged, each finding naming the reader of the property it is about, and the checks that need the page itself are listed in ``not_checked``.
- `url`: the address the page came from.
- `site`: what the site serves beside the page, as ``sluicer.fetch.site.read_site`` reads it; without it the AI agents and llms.txt are not checked, and ``not_checked`` says so.

**Returns**

An ``Audit``. Nothing is fetched here: ``site`` is read by the caller.

**Raises**

- `ValueError`: ``site`` without ``url``: which page the agents may have is a question about an address.
