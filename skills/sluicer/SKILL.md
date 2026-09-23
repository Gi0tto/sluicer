---
name: sluicer
description: Read the structured data a web page already declares (JSON-LD, microdata, RDFa, Dublin Core, OpenGraph, Twitter cards, HTML's own meta names, and microformats2 on request) and get back a summary -- title, author, date, price, currency, availability, brand, SKU -- plus full records, every value naming the vocabulary and key it came from, with no model and no API key. Use when asked for a product's price, an article's author or date, a recipe's ingredients, a book's metadata, or any field a page states about itself; when a scrape must be reproducible or auditable; when you need a page as clean markdown; or when fetching should announce itself and obey robots.txt.
version: "0.3.0"
license: MIT
metadata:
  homepage: "https://github.com/Gi0tto/sluicer"
---

# Sluicer

Most commercial pages already state their own facts in machine-readable form,
in several vocabularies at once. Sluicer reads eight of them, merges them by a
stated order of precedence, and hands back both a one-line-per-question summary
and the full records, every value naming where it came from. No model is asked
for an opinion, so the same page always gives the same answer.

## When to reach for this

When the answer is a field the page states about itself: a price, a SKU, an
author, a publication date, a rating, an ingredient list, a book's language.
When the result has to be defensible, because every value carries its source.
When you want the readable article without the navigation and the cookie banner.

Not when the page states nothing about itself. Sluicer then says so rather than
guessing, and reading the page yourself is the right move. For a listing that
declares nothing, `induce=True` reads the rows the page repeats, and every such
field says `"source": "induced"`.

## The MCP tools

- `extract_declared(html_or_url, induce=false)` -- the summary and the records.
- `page_markdown(html_or_url)` -- the main content as markdown.
- `fetch_page(url)` -- the HTML (cut at 200,000 characters) and what the fetch
  cost. Prefer the other two: they return what is in the page, not all of it.
- `compile_extractor(pages)` -- learn an extractor from two or three pages of one
  template. Keep the object it returns.
- `run_extractor(extractor, html_or_url)` -- replay it on any page of that
  template: plain rows, and `ok: false` with the reason when the page drifted.
  Never use rows from a run that is not ok as if nothing happened.
- `heal_extractor(extractor, pages)` -- after a redesign, what moved where, with
  how many of each field's old values were found in its new place; moved fields
  keep their names.
- `audit_page(html_or_url, site=true)` -- every JSON-LD, microdata and RDFa
  record held to the rich-result features Google documents for its type: which
  required and recommended properties it lacks, which values are malformed,
  each finding with its path and the URL of its rule; then the page's title,
  description, canonical and OpenGraph, and for a URL which AI agents the
  site's robots.txt admits and whether its llms.txt keeps to llmstxt.org. Use it
  instead of reading markup and guessing what Google wants.
- `map_site(url, limit=100)` -- a site's addresses from its sitemaps (up to
  1,000, from up to ten sitemaps), or its start page's links when it has none.
- `crawl_site(url, max_pages=10, max_depth=2, include, exclude)` -- follow a
  site's links, up to 25 pages on its own site, and get each page's summary and
  the types it declared; `extract_declared` on a page gives its records.
  `include` and `exclude` are plain text an address must or must not contain.
  Both take at most a minute, ask the site one request at a time, a second
  apart or its `Crawl-delay`, and say `truncated` or `stopped` when a bound
  cut them short.

Every answer carries `ok`: true exactly when it can be used as it is. When it
is false, the answer says why: `error` with a `code` -- `refused_by_robots`,
`refused_address`, `fetch_failed`, `too_large`, `missing_extra` or `bad_input`,
and on a crawled page `redirected_off_site` (with its `target`) or
`crawl_delay_too_long` -- a `message` and `retryable` (true only for
`fetch_failed`); or, from
`run_extractor`, `failed`, the checks the page broke; or, from
`heal_extractor`, `lost`, when the page no longer has a field the old extractor
read. An error is never text that could be mistaken for the page. The server
refuses addresses off the public internet (`localhost`, `10.x`, cloud metadata)
-- redirects and a browser's requests included -- unless it was started with
`SLUICER_ALLOW_PRIVATE=1`.

## What comes back

From `extract_declared`:

```json
{
  "ok": true,
  "url": "https://example.com/product",
  "summary": {
    "title":    { "value": "Brake pad set", "source": "jsonld", "key": "Product.name" },
    "image":    { "value": "https://example.com/i/pads.jpg", "source": "opengraph", "key": "og:image" },
    "language": { "value": "en", "source": "html", "key": "<html lang>" },
    "type":     { "value": "Product", "source": "jsonld", "key": "@type" },
    "price":    { "value": "41.90", "source": "jsonld", "key": "Product.offers.price" },
    "currency": { "value": "EUR", "source": "jsonld", "key": "Product.offers.priceCurrency" },
    "sku":      { "value": "BP-1187", "source": "jsonld", "key": "Product.sku" }
  },
  "records": [
    {
      "type": "Product",
      "types": ["Product"],
      "fields": {
        "name":   { "value": "Brake pad set", "source": "jsonld" },
        "sku":    { "value": "BP-1187", "source": "jsonld" },
        "offers": {
          "value": { "@type": "Offer", "price": "41.90", "priceCurrency": "EUR" },
          "source": "jsonld"
        },
        "mpn":    { "value": "BP-2210", "source": "microdata" },
        "image":  { "value": "https://example.com/i/pads.jpg", "source": "opengraph" }
      },
      "source": "jsonld"
    }
  ],
  "sources": ["jsonld", "microdata", "opengraph"]
}
```

Read `summary` first; go to `records` for anything it does not answer, such as
`recipeIngredient` or `aggregateRating`, which arrive whole as lists and objects.

## From the command line or Python

```bash
sluicer extract https://example.com/product      # summary and records, as JSON
sluicer extract saved.html --url https://x.example/p   # a file, and where it came from
sluicer extract listing.html --induce            # rows of a page that declares nothing
sluicer markdown https://example.com/article
sluicer compile page1.html page2.html -o shop.json   # an extractor, learnt once
sluicer run shop.json https://shop.example/c?page=7  # exit 3 if the page drifted
sluicer audit https://example.com/product            # exit 3 if a documented rule is broken
sluicer map https://example.com/ --plain         # a site's addresses, one a line
sluicer crawl https://example.com/ --max-pages 50 -o site.jsonl   # --resume continues it
```

Exit codes: 0 something found (a record or a summary answer), 1 the page gives
nothing at all, 2 could not be read, 3 a page broke an extractor's contract, or
an audit found a documented rule broken.

When the same kind of page will be read again and again -- a listing checked
daily, a product page watched -- compile an extractor once and run it: each run
is free and says when the site changed, instead of returning nulls.

```python
import sluicer
from sluicer.fetch import fetch

page = fetch("https://example.com/product")   # climbs to a browser only if it must
result = sluicer.extract(page.html, url=page.url)
print(result.summary["title"].value, result.summary["title"].source)
```

## Things worth knowing

**It announces itself.** Every request says `Sluicer/<version>` with a link to
the project, sends no borrowed referer, and `robots.txt` is obeyed by default,
including for a redirect to another host. A robots.txt that cannot be read -- no
answer, or a 5xx -- means nothing is fetched, as RFC 9309 says; that comes back
as `fetch_failed`, which is worth retrying later (`retryable: true`), not as
`refused_by_robots`, which is not. Pass `obey_robots=False` (`--no-robots`) only when you
have a reason you would defend.

**It climbs only on a measurement.** Plain HTTP first; a browser only for a
refusal, a challenge, or a page that is a script waiting to render. The stealth
rung is never automatic. The browser needs installing once:
`uvx --from 'sluicer[fetch]' scrapling install`; without it, a climb falls back
to what plain HTTP brought back and says so.

**Two products on one page stay two products.** Records merge across
vocabularies, never within one.

**Empty means empty.** No records means the page declared nothing, and no value
is ever invented to fill the gap.
