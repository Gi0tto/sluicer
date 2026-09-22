---
name: sluicer
description: Read the structured data a web page already declares (JSON-LD, microdata, RDFa, Dublin Core, OpenGraph, Twitter cards, and microformats2 on request) and get back records where every field says which vocabulary it came from, with no model and no API key. Use when asked for a product's price, an article's author or date, a recipe's ingredients, a book's metadata, or any field that a page states about itself; when a scrape must be reproducible or auditable; when you need a page as clean markdown; or when fetching should announce itself and obey robots.txt.
version: "0.0.1"
license: MIT
metadata:
  homepage: "https://github.com/Gi0tto/sluicer"
---

# Sluicer

Most commercial pages already state their own facts in machine-readable form, in
the source, in several vocabularies at once. Sluicer reads seven of them and
hands the result back with the provenance attached, the reader that won each
field decided by a stated order of precedence rather than by the order the
page's author typed. No model is asked for an opinion, so the same
page always gives the same answer and a run costs CPU and nothing else.

## When to reach for this

Reach for it when the answer is a field the page states about itself: a price, a
SKU, an author, a publication date, a rating, an ingredient list, a book's
language. Reach for it when the result has to be defensible, because every value
carries the vocabulary that produced it. Reach for it when you want the readable
article without the navigation and the cookie banner.

Do not reach for it when the page states nothing about itself, which is roughly
one page in four. Sluicer will tell you honestly that it found nothing rather
than guessing, and at that point reading the page yourself is the right move.

## Install

```bash
uv tool install 'sluicer[fetch,markdown]'
```

Fetching needs the `fetch` extra, markdown needs the `markdown` extra, and the
base install reads HTML you already have.

Six of the seven vocabularies are read by the base install. The seventh,
microformats2, needs `sluicer[microformats]` and is off until asked for:
`sluicer.extract(html, microformats=True)`. Do not install it expecting to read
more pages -- measured across twenty live pages, microformats appeared on one,
which declared OpenGraph as well. Install it when you need parity with
`extruct`.

## Use it

```bash
sluicer extract https://example.com/product   # the declared data, as JSON
sluicer extract saved-page.html               # a file you already have
sluicer markdown https://example.com/article  # the readable content
```

From Python:

```python
import sluicer
from sluicer.fetch import fetch, RobotsRefused

page = fetch("https://example.com/product")   # climbs only if it must
result = sluicer.extract(page.html, url=page.url)

for record in result.records:
    for name, field in record.fields.items():
        print(name, field.value, "via", field.source)
```

## What comes back

```json
{
  "url": "https://example.com/p",
  "records": [
    {
      "type": "Product",
      "fields": {
        "name": { "value": "Brake pad set", "source": "jsonld" },
        "mpn":  { "value": "GDB1330",       "source": "microdata" }
      }
    }
  ],
  "sources": ["jsonld", "microdata"],
  "fetch": { "rung": "http", "status": 200, "climbs": [] }
}
```

`sources` names the vocabularies that fired. `fetch.rung` says how the page was
got, and `fetch.climbs` lists each escalation with the measurement that forced
it, so you can see what a page cost.

## Runnable examples

Three of them live in [`examples/`](../../examples) at the root of this
repository: the declared fields with their provenance, a site refusing us and
being obeyed, and a page turned into markdown.

## Things worth knowing before you use it

**It announces itself.** Every request says `Sluicer/<version>` with a link to
the project, and `robots.txt` is obeyed by default. A refusal raises
`RobotsRefused` rather than returning an empty page, so you never mistake "the
site said no" for "the page had nothing". Pass `obey_robots=False` only when you
have a reason you would defend.

**It climbs only on a measurement.** Plain HTTP first; a browser only when the
response was a refusal, a challenge, or a skeleton. The stealth rung exists and
is not automatic: ask for it with `fetch(url, stealth=True)`.

**Two products on one page stay two products.** Records merge across
vocabularies, never within one, so a listing page does not collapse into a
single confused record.

**Empty means empty.** No records means the page declared nothing. That is a
fact about the page, not a failure, and Sluicer will not invent a plausible
answer to fill the gap.
