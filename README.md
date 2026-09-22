<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/logo-dark.png">
    <img src="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/logo.png" alt="Sluicer" width="440">
  </picture>
</p>

<p align="center">
  <strong>Turn a web page into structured data. No model, no API key, no bill.</strong>
</p>

<p align="center">
  <a href="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml"><img src="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/network%20in%20tests-none-blue" alt="no network in tests">
  <img src="https://img.shields.io/badge/LLM%20calls-none-blue" alt="no LLM calls">
  <a href="https://github.com/Gi0tto/sluicer/blob/main/LICENSE"><img src="https://img.shields.io/badge/licence-MIT-yellow.svg" alt="MIT"></a>
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
  "url": "https://example.com/product",
  "summary": {
    "title":    { "value": "Brake pad set", "source": "jsonld",    "key": "Product.name" },
    "price":    { "value": "41.90",         "source": "jsonld",    "key": "Product.offers" },
    "currency": { "value": "EUR",           "source": "jsonld",    "key": "Product.offers" },
    "image":    { "value": "https://example.com/i/pads.jpg", "source": "opengraph", "key": "og:image" }
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
still says which vocabulary -- and for the summary, which key -- it came from.

## What it does

**Reads what the page already declares.** JSON-LD, microdata, RDFa, Dublin
Core, OpenGraph, the Twitter card, the metadata names HTML itself defines, and
microformats2 when you ask for it. On a large part of the commercial web the
structured data is sitting in the source and nobody reads it.

Two of those matter more than the rest, and the numbers say why. Measured across
the 359 commercial pages of a public annotated corpus: `article:published_time`
is on 33% of them and `<meta name="author">` on 29%, and reading those two took
recall on `publish_date` from 0.06 to **0.50** and on `author` from 0.01 to
**0.38**. The first is part of the OpenGraph protocol and was missed because
only the `og:` prefix was matched; the second is a tag no vocabulary owns, which
other tools either ignore or file under a vocabulary that never claimed it.

Dublin Core, RDFa and microformats buy something different — compatibility, not
reach. Measured across twenty live pages, they unlock zero pages that JSON-LD,
microdata or OpenGraph do not already cover. What they buy is parity with
`extruct`, which reads six vocabularies, takes 540,765 installs a month, and has
had no release in 683 days.

**Answers the questions you came with.** `summary` gives one value each for
title, description, url, image, author, published, modified, language,
site_name, publisher, type, price, currency, availability, brand and sku,
chosen by fixed rules in a fixed order: the article's `headline` before the
site's name, `og:title` before `<title>`, the price from inside `offers`. Each
answer names its reader and its key, so it can be checked against the records.
Measured on fourteen live pages, it names the Guardian's author, BBC Good Food's
recipe over the video embedded in it, and Yoast's article over its own graph.

**Keeps nested values whole.** An author, an `offers` block, a recipe's
ingredients and steps arrive as the JSON the page declared, with `@type` kept
and a reference to another node on the page replaced by that node.

**Keeps the provenance of every field.** Precedence is JSON-LD, then microdata,
then microformats, then RDFa, then Dublin Core, then OpenGraph, then the Twitter
card, then HTML's own metadata names, and each value carries the reader that won
it. A value from `<meta name="author">` says `"source": "html"`, because that is
what it is. You always know where a
number came from before you act on it.

**Reads pages that declare nothing.** Ask for it with `induce=True` and Sluicer
looks for the shape the page repeats -- the rows of a listing, the cards of a
feed -- and returns one record per repetition, naming each field by where it
sits. Every one of those fields says `"source": "induced"`, so a value the page
stated and a value we inferred are never the same kind of thing. Induction runs
only when the page declared nothing about its own subject, so a page that does
carry JSON-LD is never second-guessed.

**Merges across vocabularies, never inside one.** The same product described
twice becomes one record. Two products on a listing page stay two products:
folding them would splice one product's name onto another's price.

**Fetches at the lowest price that works.** Plain HTTP first, and a browser only
when a measurement says the cheap rung brought back a refusal, a challenge or a
script waiting to render. Every climb is reported with the reason that forced
it, so you can see what a page cost, and a climb that fails falls back to what
the cheaper rung already had.

**Arrives under its own name, and takes no for an answer.** Every request says
`Sluicer/<version>` with a link to this repository and borrows no browser's
referer or fingerprint, so a site owner can see it coming and refuse it with one
line of `robots.txt`, which Sluicer reads and obeys by default -- for a redirect
to another host too, and treating a robots.txt it cannot reach as a refusal, as
RFC 9309 says. The stealth rung exists, and it is not part of the automatic ladder:
climbing on a measurement from plain HTTP to a browser is a change of cost, while
climbing from announcing yourself to hiding is a change of character, and it does
not happen to a caller who never asked for it.

**Turns a page into markdown.** The article without the navigation, the cookie
banner or the footer.

**Answers an agent.** An MCP server with three tools, so Claude Code, Codex and
anything else that speaks the protocol can call it directly. A failure comes
back as an error the agent can read, never as text that looks like the page,
and the server will not fetch `localhost`, a private network or a cloud's
metadata endpoint unless started with `SLUICER_ALLOW_PRIVATE=1`.

## Use it

From the command line:

```bash
sluicer extract page.html                      # a file you already have
sluicer extract https://example.com/product    # or a URL
curl -s https://example.com | sluicer extract - --url https://example.com
sluicer extract listing.html --induce          # rows of a page that declares nothing
sluicer markdown https://example.com/article   # the readable content
```

Exit codes follow grep: 0 when something was found, 1 when the page was read and
declares nothing, 2 when it could not be read at all.

From Python:

```python
import sluicer

result = sluicer.extract(html, url="https://example.com/p")
print(result.summary["title"].value, "via", result.summary["title"].key)
for record in result.records:
    for name, field in record.fields.items():
        print(name, field.value, "via", field.source)
```

From an agent, in your project's `.mcp.json`:

```json
{ "mcpServers": { "sluicer": { "command": "sluicer-mcp" } } }
```

Or in one line: `claude mcp add sluicer -- sluicer-mcp`. The repository is also a
Claude Code plugin, so `/plugin install` brings the server and a skill that tells
an agent when to reach for it and when not to bother; the plugin runs the server
with `uvx`, so it needs [uv](https://docs.astral.sh/uv/) on the path. Three tools arrive with
it. `extract_declared` returns the declared data with its provenance.
`page_markdown` returns the readable content. `fetch_page` returns the page and
the record of what it cost to get.

## Install

```bash
uv tool install sluicer                            # the command
uv pip install sluicer                             # the library
uv pip install 'sluicer[fetch,markdown,mcp]'       # fetching, markdown, the server
uv pip install 'sluicer[microformats]'             # the seventh vocabulary
```

The base install is `lxml` and `click`. Fetching, markdown and the MCP server
each sit behind an extra, so a reader who only parses HTML never carries a
browser. The browser rung needs its browser installed once:

```bash
uvx --from 'sluicer[fetch]' scrapling install
```

Without it, plain HTTP still works, and a page that would have climbed comes
back from the HTTP rung with the failed climb recorded. The Docker image is
built the same way: HTTP only, unless built with `--build-arg WITH_BROWSER=1`.

Microformats is behind one too, and it is the only reader that is off by
default: its reference parser costs twelve packages against a base install of
three. Turn it on per call with `extract(html, microformats=True)`, and without
the extra that call raises `MicroformatsExtraMissing` with the install line in
the message. It is worth what it is worth: measured on 2026-09-22 across twenty
live pages, microformats appeared on exactly one, and that page carried
OpenGraph as well, so it was already readable. What it buys is compatibility
with `extruct`.

## Measured, losses included

The summary beside the tools people use for the same job, on the 511 annotated
test pages of the public WCXB corpus. Hit rate is right answers over the pages
that carry a label; an invention is an answer on a page whose label is empty.

| | title | author | date | dates invented | seconds | packages |
|---|---|---|---|---|---|---|
| **sluicer 0.1.0** | 0.725 | 0.521 | 0.536 | **8** | **1.3** | **3** |
| trafilatura 2.2.0 | 0.745 | 0.750 | 0.838 | 216 | 19.0 | 17 |
| newspaper4k 0.9.6 | 0.768 | 0.532 | 0.645 | 52 | 32.9 | 22 |
| metascraper 5.58.1 | 0.654 | 0.787 | 0.374 | 84 | 3.7 | 125 |

Sluicer loses on authors and dates, which the others also read from the visible
text of the page and Sluicer does not guess from prose. It invents least: when
it answers a date it is right 92% of the time, against 46% for trafilatura, which
dates 216 pages that have none. And the corpus strips every `<script>`, so
JSON-LD, the vocabulary Sluicer reads first, is not measured here at all. The
full table, the method and the command that regenerates it are in
[the scoreboard](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard.md).

## Principles

These are constraints, not preferences, and a test enforces the first two.

**No LLM call, anywhere in the path.** Not as a fallback, not for the hard
pages. A test walks the source and fails the build if a model client is ever
imported.

**No paid API.** If a feature needs somebody's key to work, it does not ship.

**Deterministic.** The same page always gives the same answer. That is what
makes a scoreboard possible, and the scoreboard above is regenerated by one
command.

**Honest about failure.** A page that cannot be read says so. Nothing here
returns a plausible answer where the truth was unavailable.

## Documentation

Also published as a site at <https://gi0tto.github.io/sluicer/>.

- [Examples](https://github.com/Gi0tto/sluicer/tree/main/examples): three runnable scripts, each verified against a live page
- [Roadmap](https://github.com/Gi0tto/sluicer/blob/main/ROADMAP.md): what is coming, and in what order
- [Scoreboard](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard.md): the numbers above, every outcome, and how to regenerate them
- [Known limits](https://github.com/Gi0tto/sluicer/blob/main/docs/known-limits.md): where Sluicer stops, stated plainly
- [Design notes](https://github.com/Gi0tto/sluicer/blob/main/docs/design-notes.md): why the rules are the rules
- [The field, measured](https://github.com/Gi0tto/sluicer/blob/main/docs/field-survey.md): 1,926 repositories counted, and
  why this project builds what it builds
- [Contributing](https://github.com/Gi0tto/sluicer/blob/main/CONTRIBUTING.md) · [Security](https://github.com/Gi0tto/sluicer/blob/main/SECURITY.md) · [Changelog](https://github.com/Gi0tto/sluicer/blob/main/CHANGELOG.md)

## Licence

MIT, and no vendored code, so nothing here is infected by what it depends on.
The base install needs `lxml` and `click`, both BSD-3-Clause. The optional
extras pull a wider tree that is not all permissive: `tld` is tri-licensed
MPL-1.1, GPL-2.0-only or LGPL-2.1-or-later, `orjson` is MPL-2.0 alongside
Apache-2.0 or MIT, and `certifi` is MPL-2.0. They are dependencies rather than
vendored source, so none of that reaches your code. See
[the licence notes](https://github.com/Gi0tto/sluicer/blob/main/docs/known-limits.md) before you ship.
