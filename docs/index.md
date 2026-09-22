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
  "records": [
    {
      "type": "Product",
      "fields": {
        "name": { "value": "Brake pad set",             "source": "jsonld" },
        "sku":  { "value": "BP-1187",                  "source": "jsonld" },
        "mpn":  { "value": "GDB1330",                   "source": "microdata" },
        "title":{ "value": "Brake pad set, front axle", "source": "opengraph" }
      }
    }
  ],
  "sources": ["jsonld", "microdata", "opengraph"],
  "fetch": { "rung": "http", "status": 200, "climbs": [] }
}
```

That page described the same product three times, in three vocabularies. You get
one record, and every field still says which vocabulary it came from.

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

Seven vocabularies, in a stated order of precedence: JSON-LD, microdata,
microformats, RDFa Lite, Dublin Core, OpenGraph, and the Twitter card. Values
fold across vocabularies and never within one, so the same product described
twice becomes one record while two products on a listing page stay two.

When a page declares nothing at all, `induce=True` finds the shape the page
repeats and returns one record per repetition, every field marked
`"source": "induced"` so an inference is never mistaken for a declaration.

The full feature list, the fetch ladder and the MCP server are described in the
[project README](https://github.com/Gi0tto/sluicer#readme).
