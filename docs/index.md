# Sluicer

Turn a web page into structured data. No model, no API key, no bill.

A sluice box separates gold from gravel with water and gravity — no mercury, no
cyanide, nothing you have to buy. Sluicer treats a web page the same way: it
recovers your data from the structure already in the page, so the same page
always gives you the same answer, and a run costs CPU and nothing else.

```bash
uv tool install 'sluicer[fetch,markdown,mcp]'
sluicer extract https://example.com/product
```

```json
{
  "url": "https://example.com/product",
  "summary": {
    "title":    { "value": "Brake pad set", "source": "jsonld", "key": "Product.name" },
    "price":    { "value": "41.90",         "source": "jsonld", "key": "Product.offers" },
    "currency": { "value": "EUR",           "source": "jsonld", "key": "Product.offers" }
  },
  "records": [
    {
      "type": "Product",
      "fields": {
        "name":   { "value": "Brake pad set", "source": "jsonld" },
        "sku":    { "value": "BP-1187",       "source": "jsonld" },
        "offers": {
          "value": { "@type": "Offer", "price": "41.90", "priceCurrency": "EUR" },
          "source": "jsonld"
        },
        "mpn":    { "value": "BP-2210",       "source": "microdata" }
      }
    }
  ],
  "sources": ["jsonld", "microdata", "opengraph"],
  "fetch": { "rung": "http", "status": 200, "climbs": [] }
}
```

That page described the same product three times, in three vocabularies. You get
one record, a summary that answers the questions you came with, and every value
still says where it came from.

## Start here

**[Known limits](known-limits.md)** — where this stops, stated before you find
out the hard way.

**[The field, measured](field-survey.md)** — what else exists, counted rather
than asserted: 295 live projects, their install counts, and what an install of
each one costs.

**[Roadmap](roadmap.md)** — what has shipped, what is next, and what was
considered and declined.

**[Changelog](changelog.md)** — dates are the day the work landed. Anything not
listed there did not happen.

**[Contributing](contributing.md)** and **[Security](security.md)**.

## What it reads

Eight vocabularies, in a stated order of precedence: JSON-LD, microdata,
microformats, RDFa Lite, Dublin Core, OpenGraph — including the protocol's own
`article:`, `book:`, `profile:`, `video:` and `music:` namespaces — the Twitter
card, and last, the metadata names HTML itself defines (`author`,
`description`, `keywords`), which arrive marked `"source": "html"` rather than
borrowed from a vocabulary that never claimed them. Values
fold across vocabularies and never within one, so the same product described
twice becomes one record while two products on a listing page stay two.

When a page declares nothing at all, `induce=True` finds the shape the page
repeats and returns one record per repetition, every field marked
`"source": "induced"` so an inference is never mistaken for a declaration.

The full feature list, the fetch ladder and the MCP server are described in the
[project README](https://github.com/Gi0tto/sluicer#readme).
