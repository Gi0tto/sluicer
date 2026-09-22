<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <img src="docs/assets/logo.png" alt="Sluicer" width="440">
  </picture>
</p>

<p align="center">
  <strong>Turn a web page into structured data. No model, no API key, no bill.</strong>
</p>

<p align="center">
  <a href="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml"><img src="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/network%20in%20tests-none-blue" alt="no network in tests">
  <img src="https://img.shields.io/badge/LLM%20calls-none-blue" alt="no LLM calls">
  <a href="LICENSE"><img src="https://img.shields.io/badge/licence-MIT-yellow.svg" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

A sluice box separates gold from gravel with water and gravity. No mercury, no
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

## What it does

**Reads what the page already declares.** JSON-LD, microdata, OpenGraph. On a
large part of the commercial web the structured data is sitting in the source
and nobody reads it.

**Keeps the provenance of every field.** Precedence is JSON-LD, then microdata,
then OpenGraph, and each value carries the reader that won it. You always know
where a number came from before you act on it.

**Merges across vocabularies, never inside one.** The same product described
twice becomes one record. Two products on a listing page stay two products:
folding them would splice one product's name onto another's price.

**Fetches at the lowest price that works.** Plain HTTP first, and a browser only
when a measurement says the cheap rung brought back a refusal, a challenge or a
skeleton. Every climb is reported with the reason that forced it, so you can see
what a page cost.

**Turns a page into markdown.** The article without the navigation, the cookie
banner or the footer.

**Answers an agent.** An MCP server with three tools, so Claude Code, Codex and
anything else that speaks the protocol can call it directly.

## Use it

From the command line:

```bash
sluicer extract page.html                      # a file you already have
sluicer extract https://example.com/product    # or a URL
sluicer markdown https://example.com/article   # the readable content
```

From Python:

```python
import sluicer

result = sluicer.extract(html, url="https://example.com/p")
for record in result.records:
    for name, field in record.fields.items():
        print(name, field.value, "via", field.source)
```

From an agent, in your project's `.mcp.json`:

```json
{ "mcpServers": { "sluicer": { "command": "sluicer-mcp" } } }
```

Or in one line: `claude mcp add sluicer -- sluicer-mcp`. Three tools arrive with
it. `extract_declared` returns the declared data with its provenance.
`page_markdown` returns the readable content. `fetch_page` returns the page and
the record of what it cost to get.

## Install

```bash
uv tool install sluicer                            # the command
uv pip install sluicer                             # the library
uv pip install 'sluicer[fetch,markdown,mcp]'       # everything
```

The base install is `lxml` and `click`. Fetching, markdown and the MCP server
each sit behind an extra, so a reader who only parses HTML never carries a
browser.

## Principles

These are constraints, not preferences, and a test enforces the first two.

**No LLM call, anywhere in the path.** Not as a fallback, not for the hard
pages. A test walks the source and fails the build if a model client is ever
imported.

**No paid API.** If a feature needs somebody's key to work, it does not ship.

**Deterministic.** The same page always gives the same answer. That is what
makes a scoreboard possible, and a scoreboard is where this project is going.

**Honest about failure.** A page that cannot be read says so. Nothing here
returns a plausible answer where the truth was unavailable.

## Documentation

- [Roadmap](ROADMAP.md): what is coming, and in what order
- [Known limits](docs/known-limits.md): where Sluicer stops, stated plainly
- [The field, measured](docs/field-survey.md): 1,926 repositories counted, and
  why this project builds what it builds
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md)

## Licence

MIT, and no vendored code, so nothing here is infected by what it depends on.
The base install needs `lxml` and `click`, both BSD-3-Clause. The optional
extras pull a wider tree that is not all permissive: `tld` is tri-licensed
MPL-1.1, GPL-2.0-only or LGPL-2.1-or-later, and `orjson` is MPL-2.0 alongside
Apache-2.0 or MIT. They are dependencies rather than vendored source, so none of
that reaches your code. See [the licence notes](docs/known-limits.md) before you
ship.
