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
```

A page that failed is an answer like any other: it comes back with its
`error`, and the crawl goes on.

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
  once, four by default, never more than once each.
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
- **Under our own name.** Every request says `Sluicer/<version>`. The stealth
  rung is never part of a crawl.

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

## What a crawl follows

Breadth first from the start, `max_depth` links deep (3 by default), taking at
most `max_pages` addresses (100) whatever becomes of them, so a page that
failed counts. A link is followed when:

- it is an `<a href>` or `<area href>`, resolved against the page's `<base>`;
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
 "summary": {"title": {"value": "Brake pad set", "source": "jsonld", "key": "Product.name"}},
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
page taken again. Without `--resume`, a file that already holds pages is never
appended to.

A batch resumes the same way, skipping every address its file holds.

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

Two MCP tools, each small and on a clock, each answering with `ok` like the
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

Both refuse addresses off the public internet, every page and every sitemap,
unless the server was started with `SLUICER_ALLOW_PRIVATE=1`. The minute stops
the tool starting requests; a page already started finishes.

## What it does not do

The places where the crawler stops, and why, are in
[known limits](known-limits.md#in-crawling).
