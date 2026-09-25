# Crawling a site, politely

`extract` reads the page you name. A site is many pages, and there are three
ways to read one: from the list its sitemaps give (`map`), by following its
links (`crawl`), or from a list you already have (`batch`). Every page goes
through the same fetch ladder as one page does, so `robots.txt`, the address
guard and the 16 MiB bound apply to each of them, and every site is asked one
request at a time with its delay between. Politeness is not an option here; it
is what the feature is.

## Map, crawl, batch

```bash
sluicer map https://shop.example/                                  # its addresses, from its sitemaps
sluicer map https://shop.example/ --plain | sluicer batch - -o pages.jsonl   # read each one
sluicer crawl https://shop.example/ --max-pages 200 -o shop.jsonl  # follow its links instead
sluicer crawl https://shop.example/ --max-pages 500 -o shop.jsonl --resume   # and continue later
sluicer crawl https://shop.example/ --template sitemap -o pages.jsonl        # what its sitemaps list
sluicer crawl https://shop.example/ --template shopify --format csv > products.csv   # a Shopify shop's products
sluicer batch urls.txt --jobs 8 --format csv > pages.csv          # eight sites at once, as a table
```

From Python:

```python
from sluicer.crawl import crawl, extract_many, map_site

site = map_site("https://shop.example/")
print(site.source, len(site.urls), [read.error for read in site.sitemaps])

run = crawl("https://shop.example/", max_pages=50, state="shop.jsonl")
for page in run:
    if page.ok:
        print(page.url, page.extraction.summary.get("price"))
    else:
        print(page.url, page.error.code, page.error.message)
print(run.stopped)  # "done", "max_pages" or "time_budget"

for page in extract_many(["https://shop.example/p/1", "https://shop.example/p/2"]):
    ...

from sluicer.crawl import shopify_products, sitemap_pages

for product in shopify_products("https://shop.example/"):
    print(product.url, product.extraction.summary["price"].value)
```

A page that failed is an answer like any other: it comes back with its
`error`, and the crawl goes on. On a terminal, stderr shows one bar of the
pages taken, the last one's status and address beside it; anywhere else,
a log, one line a page.

## What polite means here

- **robots.txt, for every request.** Every page and every sitemap is asked of
  the site's `robots.txt` first, and a crawl has no switch to skip it: a
  crawler that ignores it is the thing it exists to stop. A `robots.txt` that
  cannot be read -- no answer, or a 5xx -- means nothing on that site is
  fetched, as RFC 9309 says; the page says `fetch_failed`, worth retrying.
- **One request at a time per site.** A site is a host with or without
  `www.`, over http or https, with its port when that is not the default:
  `www.example.com` and `example.com` are usually the same machines, and
  pacing them apart would ask them twice as often. Several sites are asked at
  once, four by default (`--jobs`, `concurrency=`), never more than once
  each. One at a time holds for
  the whole process, not only for one crawl: two crawls of one site, a map
  beside them, or an agent's parallel `extract_declared` calls wait for each
  other (`sluicer.fetch.gate`). A single fetch -- `sluicer extract`, an MCP or
  HTTP API call -- is one visit: its `robots.txt`, the page and any climb follow
  each other, and the next caller waits a second after it ends. Measured on a
  local site, two crawls and four fetches at once: before, pairs of requests
  0.000 s apart and two in flight at once; now none closer than the site's
  `Crawl-delay`, never two at once.
- **A delay counted from the end.** No request to a site starts sooner than a
  second (`--delay`, `min_delay`) after the last one ended, or its
  `Crawl-delay` when that is longer, or the interval its `Request-rate`
  implies. Counted from the end, so a slow answer is never a reason to ask
  again sooner.
- **Every request counts.** The site's `robots.txt`, each sitemap, each hop of
  a redirect, and each rung the ladder climbs to is a request, and waits its
  turn. The record of when each site was last asked is kept for the whole
  process, as the `robots.txt` answers are, so a map followed by a crawl, or
  an agent calling the crawl tool twice, keeps the delay between them too.
- **A delay too long is an answer.** A site asking for more than a minute
  between requests (`max_delay`; ten seconds for the MCP tools) is not
  crawled for a week: its pages say `crawl_delay_too_long`, with the delay it
  asked for.
- **A site that says "too many" is heard.** A 429 or a 503 is the site asking
  to be asked less often. With a `Retry-After`, the next request to it waits
  that long, a date counted from the response's own `Date` so this machine's
  clock does not matter; one longer than `max_delay` answers the site's next
  pages `rate_limited`, retryable later. Without one, the site's delay doubles
  for the rest of the crawl, up to `max_delay`. Scrapy retries both statuses
  without reading `Retry-After`; Crawlee reads it on a 429 only, and only when
  the crawler is set to pace the site (a `ThrottlingRequestManager`, or
  `sameDomainDelaySecs` in its JavaScript version).
- **A slow site is asked as slowly.** A crawl times each request, and a
  site's pace is how long it has lately taken to answer: each request's
  seconds averaged with the pace before, as Scrapy's AutoThrottle does when
  it keeps one request in flight. The next request waits the pace when it is
  longer than the delay, never more than `max_delay`, and never instead of
  the floor or the `Crawl-delay`: a site answering in 3 s is asked every
  3 s, not every second. Measured on a local site with a 0.3 s delay: the
  request after a page that took 2.0 s waited 1.01 s, the next 0.51 s, then
  0.31 s. A redirect hop's rest is not counted as the site's slowness.
- **Asked again, a few times and later each time.** A page whose request
  did not answer -- a connection refused or reset, a timeout, an answer cut
  short, a name the resolver could not look up for now, a `robots.txt`
  nobody could read -- or answered 429 or a 5xx is
  asked again, twice at most by default (`--retries`, `retries=`; 0 asks
  once): the first time twice the site's delay after the failed request
  ended, the second four times it, or the site's `Retry-After` when that is
  longer, never more than `max_delay` and never past the time budget. A 4xx
  other than 429 is the site's answer about the page, with a body or empty,
  and is never asked again; nor is a failure asking again would meet again,
  a redirect loop, an encoding the fetch cannot read, a page with nothing in
  it, whose line says `fetch_failed` with `retryable` false. A site whose
  page failed through all its retries is asked once a
  page until one of its pages answers, so a site that is down costs its
  retries once, not once a page. The page's line says each time in
  `retries`, `[{"reason": "it answered 503", "after": 1.0}]`, and is what its
  last request came to. Measured on a local site with a 0.5 s delay: a page
  whose connection was reset was asked again 1.0 s later, and one that
  answered 503 twice 1.0 s and then 2.0 s later; a 404 beside them was asked
  once.
- **Asked once, not twice.** A page that plain HTTP brought back as an empty
  shell is asked again of the browser, which is two requests for one page. So
  a site that needed the browser once starts its next pages there, for the
  rest of the process and at most a day, and each such page's first climb
  says so: a JS site's crawl asks each page once. A rung that merely failed
  teaches nothing, and a remembered rung that fails is forgotten. Within a
  crawl the memory is also kept for each part of the site -- an address's
  directory, `/p/` for `/p/1` -- so a shop whose listings are plain HTML and
  whose products a script draws keeps its listings on plain HTTP after its
  first product needed the browser: a part whose page came back from plain
  HTTP starts there, one that needed the browser starts at it, and one not
  seen yet starts where the site's memory says. Measured on a local shop of 7
  listings and 21 script-drawn products, crawled with the real browser: 30
  document requests, as with the site's memory alone, and none of the
  listings rendered in the browser, where three were before (0.7 s each,
  against 2 ms over plain HTTP); with no memory at all, 50.
- **One connection per site.** Plain HTTP keeps the connection a page came on,
  while the server keeps it open, and asks the site's next page on it: one
  handshake for a site's pages rather than one each. Measured on a local
  server, twenty pages cost one connection instead of twenty.
- **Under our own name.** Every request says `Sluicer/<version>`. The stealth
  rung is never part of a crawl. `--header` and `--cookie` (`headers=`,
  `cookies=`) add to what a crawl sends -- a site's own login, for a site you
  may read behind it -- and never replace the name. They go to the origin the
  crawl starts at alone, scheme, host and port: its pages on `www.` or over
  plain http, a robots.txt, a sitemap on another host are asked without them.

Measured by the site being crawled, not by the crawler: `tests/live/crawl_check.py`
serves a local site whose `robots.txt` asks for a `Crawl-delay` of 0.5 s and
writes down when each request arrived and when its answer went out. Over the
nine requests of a crawl -- a redirect chain, a page that takes a second to
answer, a link loop and a redirect to another site among them -- the shortest
gap was 0.506 s, the request after the slow page waited 0.510 s from the end
of its answer, no two requests were ever in flight at once, and the other site
was never asked. Ignoring the `Crawl-delay`, or letting redirect hops go
unjudged, fails the check; both were tried.

On public sites that invite scraping, on 2026-09-23, timing every call the
crawler made to the web -- a `robots.txt`, a sitemap, or one rung's fetch of a
page -- with the default one-second delay:

| site | what | calls | seconds | shortest gap |
|---|---|---|---|---|
| books.toscrape.com | crawl, 15 pages | 16 | 26.3 | 1.00 s |
| quotes.toscrape.com | crawl, 10 pages | 12 | 20.8 | 1.00 s |
| web-scraping.dev, `Crawl-delay: 2` | crawl, 8 pages, one climb to the browser | 10 | 29.5 | 2.00 s |
| web-scraping.dev | map, 3 sitemaps | 4 | 9.0 | 2.00 s |
| scrapeme.live | map of 12 sitemaps to 400 addresses, then 5 products | 13 | 22.6 | 1.00 s |

A redirect's hops are inside one call and are paced too, which the local check
measures; the browser's own requests for a page's images and scripts are
inside its call and are not.

The first runs found three gaps of 0.00 s, each now closed: a `robots.txt` the
ladder read the moment a page redirected to the other scheme, a rung it
climbed to the moment the last came back, and a batch that began the moment
the map before it ended. The five scrapeme.live products each came back as a
`Product` with its price, read from its JSON-LD.

## Several sites at once

`--jobs N` on `batch` and `crawl` asks up to N sites at the same moment, each
still one request at a time with its delay between: a crawl kept to its site
asks one site whatever N is, so it matters to a batch and to `--any-site`.
The pages come back in the order given either way. Measured on eight local
sites of five pages each, with `--delay 0.5`: 6.2 s with `--jobs 1`, 3.3 s
with 4, 2.7 s with 8, the order kept every time, never two requests in
flight at one site, and no gap at a site shorter than 0.50 s.

## Ready crawls

`--template` names a crawl whose pages a site already lists.

- **`sitemap`** reads every address the site's sitemaps list, in their
  order, the way `sluicer map URL --plain | sluicer batch -` does, but in one
  process: the map's last request and the first page's are one site's, and
  wait its delay between (the pipe's second command starts as the first
  ends, and knows nothing of it). `--include` and `--exclude` choose among
  the addresses, and `--max-pages` bounds them; the run says it stopped at
  `max_pages` when the sitemaps listed more. A site with no sitemap gives the
  start page's links, as a map does. It resumes as a batch does.
- **`shopify`** reads a Shopify shop's products from the file every Shopify
  shop serves, `/products.json?limit=250&page=N`, from page 1 until a page is
  short or `--max-pages` pages were asked: each page through `robots.txt`,
  after the site's delay, and asked again as a page is. Each product is a line
  of its own, at its page's address, `/products/<handle>`, with `found_on`
  the products.json page. Its `records` hold one `Product` of the fields
  Shopify wrote, as Shopify named them, `source` `shopify`, each with its
  JSON pointer in that page (`/products/3/variants/0/price`); its `summary`
  answers the title, the description as text, the first image, the
  publication and update dates, the vendor as brand, the price -- or, when
  the variants differ, `price_low` and `price_high` -- the regular price
  (`compare_at_price`), the availability (in stock when any variant is) and,
  for a product of one variant, its SKU. The file names no currency, so the
  summary has none. A site that answers another status, or not a
  products.json, is answered `bad_input`: not a Shopify shop, or one that
  serves none. `--resume` asks the last page its file holds again and writes
  none of that page's products twice; another shop's file is refused.
  Measured on a local shop of 517 products with a `Crawl-delay` of 0.5: three
  requests after `robots.txt`, a second apart (the default delay being the
  longer), and 517 rows.

An option a template does not use -- `--max-depth` and `--any-site`, and for
`shopify` `--include`, `--exclude`, `--induce` and `--respect` -- is refused,
not ignored. From Python, `sitemap_pages()` and `shopify_products()` in
`sluicer.crawl` take `crawl`'s arguments.

## Rights a site reserves

`--respect tdm` (`respect_tdm=True`, and for an agent `respect_tdm` on
`crawl_site`, `extract_declared` and `page_markdown`) gives a page whose text
and data mining rights are reserved as an error, `tdm_reserved`, never its
data. The reservation is TDMRep's, a W3C Community Group final report of
2024-05-10 written for the EU's DSM Directive, Article 4, read in its own
order: the site's `/.well-known/tdmrep.json` first -- read once per site,
through its robots.txt and its delay -- then the page's `TDM-Reservation`
header, then its `<meta name="tdm-reservation">`, each later one superseding
the earlier, an absent one resetting nothing. In the file the first rule
whose `location` matches is the one, as the report says, not the longest.
The page is fetched either way: a reservation in its meta tags is only seen
in the page. The error says which declaration reserved it and the policy it
names, if any. Without `--respect`, nothing is refused, and the reservation
is still reported in each page's `rights`.

## What a crawl follows

Breadth first from the start, `max_depth` links deep (3 by default), taking at
most `max_pages` addresses (100) whatever becomes of them, so a page that
failed counts. A link is followed when:

- it is an `<a href>` or `<area href>`, resolved against the page's `<base>`,
  on a page that answered below 400: an error page's links, and its
  canonical, are the error page's, so a 404 is reported with its status and
  nothing is admitted from it;
- it is not `rel="nofollow"`, and its page's `<meta name="robots">` (or
  `name="sluicer"`) does not say `nofollow` or `none`;
- it is on the start's site, unless `--any-site` (`same_site=False`);
- it does not name a file by its extension -- `.pdf`, `.jpg`, `.zip` and the
  rest in `sluicer/crawl/urls.py`: fetching a video to learn it declares
  nothing costs the site the video;
- one `--include` pattern is found in it, when any is given, and no
  `--exclude` pattern is. Patterns are regular expressions searched in the
  whole address; they never apply to the start;
- it has not been seen. Where a page's redirects landed, and the canonical it
  declares on its own site, are marked seen too, so neither is fetched again
  under the other name.

A redirect that leaves the start's site is refused before the other site is
asked: the page says `redirected_off_site` and names its `target`. With
`--any-site`, and always in a batch, that target is taken in its own turn, as
an address of its own, so its site too is asked one request at a time.

## One spelling per address

Two spellings of one address are one address. The rules are few, because each
is a claim about what a server does:

- the scheme and host are lowercased, a host's trailing dot dropped, a name
  outside ASCII written in its IDNA form, and a default port removed;
- the fragment is dropped: it never reaches the server;
- an empty path is `/`, and `.` and `..` segments are resolved;
- characters an address cannot carry are percent-encoded, every escape in
  capitals;
- the query is kept as written, its order included, since a server may read
  `?a=1&b=2` and `?b=2&a=1` differently;
- a trailing slash is kept: `/a` and `/a/` are two addresses, because a server
  may answer them differently. Most sites redirect one to the other, and where
  a redirect landed is marked seen, so the second spelling is fetched again
  only when it was queued before the first was read.

An address with a user name or password in it, or a scheme other than http and
https, is never taken.

## The output is the state

Each page is one line of JSON, written the moment its turn comes:

```json
{"url": "https://shop.example/p/1", "ok": true, "depth": 1,
 "found_on": "https://shop.example/", "landed": "https://shop.example/p/1",
 "fetch": {"rung": "http", "status": 200, "seconds": 0.212, "climbs": []},
 "canonical": "https://shop.example/p/1",
 "summary": {"title": {"value": "Brake pad set", "source": "jsonld", "key": "Product.name",
                       "where": "/html/head/script[1]#/name"}},
 "records": [...], "sources": ["jsonld"],
 "links": ["https://shop.example/c/brakes", "..."]}
{"url": "https://shop.example/cart", "ok": false, "depth": 1,
 "found_on": "https://shop.example/",
 "error": {"code": "refused_by_robots", "message": "https://shop.example/cart is refused: its robots.txt disallows it", "retryable": false}}
```

`summary`, `records` and `sources` are what `sluicer extract` gives for the
page. `links` is every address it lets a crawl follow, whether or not the
crawl took it, so the file is also the site's link graph.

Handed the same file with `--resume` (`state=` in Python), a crawl replays its
lines to rebuild what it had seen and taken, and continues where they end,
fetching none of them again. That works because the order is decided, not
raced: every address is numbered as it is admitted, and what a page admits is
decided when its turn comes, never when its fetch happens to finish. The same
site crawled twice gives the same pages in the same order, whatever the
concurrency; a crawl stopped after four pages and resumed ends with the same
file as one that ran through, and the live check compares the two. A file
written by a crawl of another site or with other options is refused, not mixed
-- with one exception that is safe: a larger `--max-pages` continues where the
smaller stopped. A last line cut off by a stop mid-write is dropped and its
page taken again, once the rest of the file is known to be this crawl's; a
file that is not is refused and left as it was. Without `--resume`, a file
that already holds pages is never appended to.

A batch resumes the same way, skipping every address its file holds.

## As a table

`--format csv` on `crawl` and `batch` writes a row per page instead of a JSON
line, to stdout or `--out`, for a spreadsheet. The columns are fixed, so every
file has the same header, written before the first page is fetched:

| columns | what they hold |
|---|---|
| `url`, `ok`, `depth`, `found_on`, `landed`, `status`, `rung`, `seconds`, `canonical` | the page, as its line says |
| `climbs`, `retries`, `records`, `links` | how many its line lists |
| `error`, `message` | its error's code and sentence, empty when it has none |
| `sources`, `types` | the readers that found something and the types its records declared, each once, a space between |
| `summary.title` ... `summary.breadcrumb` | each summary question, in `sluicer.summary.FIELDS`'s order: the answer's value alone |

The summary's reader, key and place, and the records themselves, are in the
JSON line and not in the table. True and false are `true` and `false`, and
nothing is an empty cell. The pages are other people's, and a cell that
begins with `=`, `+`, `-`, `@`, a tab or a carriage return would run as a
formula in a spreadsheet: it is written after a `'`, as OWASP advises, unless
it is a number. A table holds no page's links, so it cannot be resumed:
`--resume` refuses it; crawl as JSON Lines and make the table after.
`sluicer map --format csv` is a row per address: `url`, `lastmod`,
`sitemap`. From Python, `sluicer.crawl.table.page_row()` flattens a page's
line.

## Exit codes

The single-page commands' three meanings, over the whole run, pages resumed
included: 0 when a page gave something -- a record or a summary answer -- 1
when pages were read and none did, 2 when none could be read or the command
could not start. `map` exits 0 when it found an address. Ctrl-C exits 130 with
what was written intact, and `--resume` continues it.

## Sitemaps

The sitemaps a map reads are the ones `robots.txt` names, in its order; when it
names none, `/sitemap.xml`, and `/sitemap_index.xml` if that could not be
read. An
index is followed to the sitemaps it lists on the same site; one `robots.txt`
names may live anywhere, since the site vouched for it. Only addresses on the
site are kept, each once, in the order the sitemaps list them, with their
`lastmod` as written. When the sitemaps give no address on the site, the start
page's links stand in, and `source` says so.

A sitemap is XML from a place you do not control, so it is read as an attack
would be written. No entity is resolved and nothing is fetched from inside it,
and a document that declares any document type is refused outright: a sitemap
never needs one, and billion laughs and external entities both arrive through
one. Gzip is told by its first bytes, not its name or a header, and inflated
no further than 16 MiB. A sitemap that stops being well-formed XML -- an
unescaped `&` in an address is the commonest bug -- keeps the entries before
the break and says where it broke. A sitemap that is a list of addresses, one
a line, is read too. A soft 404, the site's HTML where a sitemap was expected,
is reported as not a sitemap.

Every bound is stated: at most 50 sitemap files per map and 50,000 addresses,
the protocol's own limit for one file, and a sitemap listing more says so. The
answer's `truncated` is true whenever a bound -- the limit, the number of
sitemaps, the time -- stopped the map before the sitemaps were read out.

## For an agent

Three MCP tools, each small and on a clock, each answering with `ok` like the
rest:

- `map_site(url, limit=100)` -- up to 1,000 addresses from up to ten sitemaps,
  within a minute.
- `crawl_site(url, max_pages=10, max_depth=2, include, exclude)` -- up to 25
  pages, three links deep, on `url`'s site, within a minute. Each page comes
  back with its summary and the types it declared, not its records; call
  `extract_declared` on a page for those. `include` and `exclude` are plain
  text an address must or must not contain, not patterns. A site asking for
  more than ten seconds between requests is answered `crawl_delay_too_long`
  rather than holding the agent a minute a page. `ok` is false only when no
  page could be read, and `error` then says why.
- `extract_many(urls, records=false, induce, respect_tdm)` -- up to 25
  addresses the agent already has, on one site or several, in the order
  given, within a minute: each site one request at a time, several sites at
  once, where a loop of `extract_declared` calls waits a second behind each
  one and retries nothing. Each page comes back as `crawl_site`'s do, and with
  its records when `records` is true. Measured on the 140 pages of the product
  benchmark, a page's summary weighs 2.3 KB at the median and its records
  4.2 KB more: 25 summaries fit the 75,000-byte bound an answer is held to,
  25 pages' records do not, so past the bound the heaviest pages' records go
  first, counted in `records_left_out`.

A page of any of them asked again says so in `retries`.

All three refuse addresses off the public internet, every page and every sitemap,
unless the server was started with `SLUICER_ALLOW_PRIVATE=1`. The minute stops
the tool starting requests; a page already started finishes.

## What it does not do

The places where the crawler stops, and why, are in
[known limits](known-limits.md#in-crawling).
