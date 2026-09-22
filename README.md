<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <img src="docs/assets/logo.png" alt="Sluicer" width="440">
  </picture>
</p>

<p align="center">
  Turn a web page into structured data with no model in the loop.
</p>

---

A sluice box separates gold from gravel using water and gravity. No mercury, no
cyanide, nothing you have to buy. Sluicer treats a web page the same way: it
recovers your data from the structure that's already in the page, so there's no
API key, no token bill, and the same page always gives you the same answer.

> **Status: first slice, working.** Sluicer reads the structured data a page
> already declares and tells you where every value came from. The fetch ladder,
> structure induction, trust scoring and the public scoreboard are designed and
> not built. Until the scoreboard runs, this README makes no claim about being
> better than anything.

## Why another one of these

We counted the field first. 823 crawler and scraper repositories pulled from
GitHub, 240 of them alive: pushed in the last twelve months, not archived, at
least 1,000 stars. Here's where all that work goes.

| layer | share of the 240 |
| --- | --- |
| browsers, stealth, anti-bot | 32% |
| LLM and agents | 31% |
| crawl frameworks | 21% |
| parsing and extraction | 10% |
| markdown and document conversion | 4% |
| no-code and visual builders | 2% |

Two thirds of the field is busy fetching the page or handing it to a model. The
layer that turns a page into data without a model is the thinnest one on the
board, and the deterministic tools inside it have been left to rot. Look at the
last twelve months: `autoscraper` has 7,990 stars and **one commit**. `extruct`
has **zero**. Only `trafilatura` is healthy, and it pulls article text, which is
one page type out of many.

The benchmark people arrive at the same place from the other side. WCXB exists
(2,008 hand-reviewed pages, 1,613 domains) because the older benchmarks only ever
measured news articles, and extraction systems fail hardest on product pages,
listings, forums and documentation. That's most of the commercial web.

So the hole isn't another fetcher. It's the step right after the fetch, and the
fact that nobody is keeping score.

## Install

Not on PyPI yet. From a clone:

```bash
uv tool install .      # the sluicer command
uv pip install -e .    # or the library, editable
```

## Use it

```bash
sluicer extract page.html
```

```json
{
  "url": "page.html",
  "records": [
    {
      "type": "Product",
      "types": ["Product"],
      "fields": {
        "name":        { "value": "Brake pad set",             "source": "jsonld" },
        "sku":         { "value": "BP-1187",                  "source": "jsonld" },
        "mpn":         { "value": "GDB1330",                   "source": "microdata" },
        "title":       { "value": "Brake pad set, front axle", "source": "opengraph" }
      }
    }
  ],
  "sources": ["jsonld", "microdata", "opengraph"]
}
```

That page declared the same product three times, in three vocabularies. You get
one record, and every field still says which vocabulary it came from.

From Python:

```python
import sluicer

result = sluicer.extract(html, url="https://example.com/p")
for record in result.records:
    for name, field in record.fields.items():
        print(name, field.value, "via", field.source)
```

## How it reads a page

**One cascade, deterministic at every step.**

1. **Read what the page already tells you.** JSON-LD, microdata, OpenGraph. On a
   big slice of the commercial web the structured data is sitting right there in
   the source and nobody reads it.
2. **Merge across vocabularies, not within one.** When microdata describes the
   same type a JSON-LD record already carries, it fills that record's gaps. Two
   products in one `@graph` stay two products: folding them would splice one
   product's name onto another's sku.
3. **Keep the provenance.** Precedence is JSON-LD, then microdata, then
   OpenGraph, and every field remembers which reader won it.

## What Sluicer won't do

- **No LLM. Anywhere, ever.** Not as a fallback, not for the hard pages. A run
  costs you CPU and nothing else. A test walks the source and fails the build if
  a model client or a network library ever gets imported.
- **No paid API.** If a feature needs somebody's key to work, it doesn't ship.
- **No stealth arms race.** Fetching will go to `scrapling`, which does that job
  full time and does it well. Rewriting a browser is how side projects die.

## Not built yet

The fetch ladder that climbs from plain HTTP to a browser only when a
measurement says it must. Structure induction for pages that declare nothing.
Trust scoring, which compares pages built from the same template and says how
much to believe the result. Schema healing, which names what broke when a site
changes. And the scoreboard: the free datasets plus a multilingual e-commerce
split, scored on every run, with the competition measured right next to us and
the losses published too.

## Licence

MIT. Everything underneath is permissive as well: `lxml` (BSD-3) and `click`
(BSD-3), with `trafilatura` (Apache-2.0) and `scrapling` (BSD-3) to come. We
vendor no AGPL code, so you can drop Sluicer inside whatever you're building.
