---
name: sluicer
description: Read the structured data a web page already declares (JSON-LD, microdata, RDFa, Dublin Core, OpenGraph, Twitter cards, HTML's own meta names, and microformats2 on request) and get back a summary -- title, author, date, price, currency, availability, brand, SKU -- plus full records, every value naming the vocabulary and key it came from, with no model and no API key. Use when asked for a product's price, an article's author or date, a recipe's ingredients, a book's metadata, or any field a page states about itself; when a scrape must be reproducible or auditable; when you need a page as clean markdown; or when fetching should announce itself and obey robots.txt.
version: "0.0.1"
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

## The three MCP tools

- `extract_declared(html_or_url, induce=false)` -- the summary and the records.
- `page_markdown(html_or_url)` -- the main content as markdown.
- `fetch_page(url)` -- the HTML (cut at 200,000 characters) and what the fetch
  cost. Prefer the other two: they return what is in the page, not all of it.

A failure is always `{"error": ...}` with a key saying which kind:
`refused_by_robots`, `refused_address`, `fetch_failed`, `missing_extra` or
`bad_input`. It is never text that could be mistaken for the page. The server
refuses addresses off the public internet (`localhost`, `10.x`, cloud metadata)
unless it was started with `SLUICER_ALLOW_PRIVATE=1`.

## What comes back

```json
{
  "url": "https://example.com/p",
  "summary": {
    "title": { "value": "Brake pad set", "source": "jsonld", "key": "Product.name" },
    "price": { "value": "41.90", "source": "jsonld", "key": "Product.offers" },
    "currency": { "value": "EUR", "source": "jsonld", "key": "Product.offers" }
  },
  "records": [
    {
      "type": "Product",
      "fields": {
        "name": { "value": "Brake pad set", "source": "jsonld" },
        "offers": {
          "value": { "@type": "Offer", "price": "41.90", "priceCurrency": "EUR" },
          "source": "jsonld"
        },
        "mpn": { "value": "BP-2210", "source": "microdata" }
      }
    }
  ],
  "sources": ["jsonld", "microdata"]
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
```

Exit codes: 0 found, 1 read but nothing declared, 2 could not be read.

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
as `fetch_failed`, which is worth retrying later, not as `refused_by_robots`,
which is not. Pass `obey_robots=False` (`--no-robots`) only when you
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
