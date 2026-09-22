<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <img src="docs/assets/logo.png" alt="Sluicer" width="440">
  </picture>
</p>

<p align="center">
  Turn a web page into structured data with no model in the loop.
</p>

<p align="center">
  <a href="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml"><img src="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/network%20in%20tests-none-blue" alt="no network in tests">
  <img src="https://img.shields.io/badge/LLM%20calls-none-blue" alt="no LLM calls">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-yellow.svg" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

A sluice box separates gold from gravel using water and gravity. No mercury, no
cyanide, nothing you have to buy. Sluicer treats a web page the same way: it
recovers your data from the structure that's already in the page, so there's no
API key, no token bill, and the same page always gives you the same answer.

> **Status: two slices, working.** Sluicer reads the structured data a page
> already declares, and fetches a page itself, starting cheap and climbing only
> when a measurement says it must. Structure induction, trust scoring and the
> public scoreboard are designed and not built. Until the scoreboard runs, this
> README makes no claim about being better than anything.

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
sluicer extract page.html          # a file you already have
sluicer extract https://example.com/product   # needs the fetch extra
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
        "sku":         { "value": "ATD-1187",                  "source": "jsonld" },
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

Give it a URL and the answer carries what the page cost:

```json
"fetch": {
  "rung": "browser",
  "status": 200,
  "climbs": [
    {
      "from_rung": "http",
      "to_rung": "browser",
      "reason": "the response is a challenge page, not the content: 'just a moment'"
    }
  ]
}
```

Sluicer starts at plain HTTP and climbs to a browser only when a measurement
says the cheap rung brought back a refusal, a challenge or a skeleton. Fetching
needs the extra: `uv pip install 'sluicer[fetch]'`, which brings in `scrapling`.

From Python:

```python
import sluicer

result = sluicer.extract(html, url="https://example.com/p")
for record in result.records:
    for name, field in record.fields.items():
        print(name, field.value, "via", field.source)
```

## Use it from an agent

Sluicer speaks MCP, so Claude Code, Codex and anything else that speaks the
protocol can call it directly. Install it with the extra and register it:

```bash
uv tool install 'sluicer[mcp,fetch,markdown]'
```

Claude Code, in your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "sluicer": { "command": "sluicer-mcp" }
  }
}
```

Or in one line: `claude mcp add sluicer -- sluicer-mcp`.

Three tools arrive with it. `extract_declared` returns the structured data a
page declares, with the provenance of every field. `page_markdown` returns the
readable content with the furniture stripped. `fetch_page` returns the raw page
and the record of what it cost to get: which rung, and every climb with the
measurement that forced it.

Each takes either a URL or the HTML itself, except `fetch_page`, which wants a
URL and says so rather than handing your own string back to you.

## Read a page as markdown

```bash
sluicer markdown page.html
sluicer markdown https://example.com/article
```

You get the main content and not the navigation, the cookie banner or the
footer. Boilerplate removal is `trafilatura`'s work, under the `markdown` extra;
Sluicer hands the page over and passes the result back.

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
- **No stealth arms race.** Fetching goes to `scrapling`, which does that job
  full time and does it well. Rewriting a browser is how side projects die.

## Not built yet

Structure induction for pages that declare nothing. Trust scoring, which
compares pages built from the same template and says how much to believe the
result. Schema healing, which names what broke when a site changes. An MCP
server, which the field survey showed nine percent of live projects now ship. And
the scoreboard: the free datasets plus a multilingual e-commerce split, scored on
every run, with the competition measured right next to us and the losses
published too.

## Licence

MIT.

We vendor no code, so nothing here is infected by what it depends on, and you
can drop Sluicer inside whatever you are building. The base install needs `lxml`
and `click`, both BSD-3-Clause.

The optional `fetch` extra pulls a wider tree, and it is not all permissive. Read
before you ship: `scrapling`, `cssselect` and `w3lib` are BSD-3-Clause,
`typing-extensions` is PSF-2.0, `orjson` is MPL-2.0 alongside Apache-2.0 or MIT,
and `tld` is tri-licensed MPL-1.1, GPL-2.0-only or LGPL-2.1-or-later. They are
dependencies rather than vendored source, so none of that reaches your code, but
this file said "everything underneath is permissive as well" until somebody
checked, and it was not true.
