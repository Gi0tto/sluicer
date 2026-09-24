<!-- mcp-name: io.github.Gi0tto/sluicer -->

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
  <a href="https://pypi.org/project/sluicer/"><img src="https://img.shields.io/pypi/v/sluicer" alt="PyPI"></a>
  <a href="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml"><img src="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/network%20in%20tests-none-blue" alt="no network in tests">
  <img src="https://img.shields.io/badge/LLM%20calls-none-blue" alt="no LLM calls">
  <a href="https://github.com/Gi0tto/sluicer/blob/main/LICENSE"><img src="https://img.shields.io/badge/licence-MIT%2C%20one%20file%20CC%20BY--SA%203.0-yellow.svg" alt="MIT, one file CC BY-SA 3.0"></a>
  <a href="https://pypi.org/project/sluicer/"><img src="https://img.shields.io/pypi/pyversions/sluicer" alt="Python versions"></a>
</p>

---

Sluicer reads the structured data a web page already declares -- JSON-LD,
microdata, RDFa, OpenGraph, the Twitter card, HTML's own meta names -- and
merges it into one record per thing, every value naming the vocabulary, the key
and the place on the page it came from. No model reads the page, so the same
page always gives the same answer and a run costs CPU. Learn an extractor from
a few pages of a template and every replay checks the page still keeps to it: a
site that changed its layout fails loudly, and `heal` says what moved where.

```bash
uv tool install 'sluicer[fetch,markdown,mcp]'
sluicer extract product.html --url https://example.com/product
```

It prints, abridged:

```json
{
  "summary": {
    "title":    { "value": "Brake pad set", "source": "jsonld", "key": "Product.name",
                  "where": "/html/head/script[1]#/name" },
    "price":    { "value": "41.90", "source": "jsonld", "key": "Product.offers.price",
                  "where": "/html/head/script[1]#/offers/price" },
    "currency": { "value": "EUR", "source": "jsonld", "key": "Product.offers.priceCurrency",
                  "where": "/html/head/script[1]#/offers/priceCurrency" },
    "image":    { "value": "https://example.com/i/pads.jpg", "source": "opengraph", "key": "og:image",
                  "where": null }
  },
  "normalised": { "price": "41.90", "currency": "EUR" },
  "records": [
    {
      "type": "Product",
      "fields": {
        "name":   { "value": "Brake pad set", "source": "jsonld", "where": "/html/head/script[1]#/name" },
        "offers": { "value": { "@type": "Offer", "price": "41.90", "priceCurrency": "EUR" }, "source": "jsonld",
                    "where": "/html/head/script[1]#/offers" },
        "mpn":    { "value": "BP-2210", "source": "microdata", "where": "/html/body/div[1]/span[1]" },
        "image":  { "value": "https://example.com/i/pads.jpg", "source": "opengraph", "where": null }
      }
    }
  ],
  "sources": ["jsonld", "microdata", "opengraph"]
}
```

That page described one product three times, in three vocabularies. You get one
record, a summary of the questions you came with, and the provenance of every
value: the vocabulary, and where on the page -- an XPath, and inside JSON-LD a
pointer to the value, even one a reference fetched from elsewhere in the page.
A meta tag's place is its key. When the page answers one question two ways
-- a price of 41.90 in JSON-LD and 39.90 in OpenGraph -- `conflicts` says so,
both answers with their places. `sluicer inspect` prints the same reading laid
out for a person.

## How it differs

- **From extruct**, which returns each vocabulary as the page wrote it: Sluicer
  merges them into one record per thing, keeps where each field came from,
  answers a summary with its reader and key, and resolves JSON-LD references.
  `from sluicer.compat import extruct` answers extruct's own calls, in its
  shapes, for code written against it -- see
  [moving from extruct](https://github.com/Gi0tto/sluicer/blob/main/docs/extruct.md).
- **From trafilatura and newspaper4k**, which read authors and dates from the
  visible text: Sluicer reads only what the page declares. It answers less
  often, and is wrong less often -- see [the numbers](#measured-losses-included).
- **From a scraper of CSS selectors**: an extractor checks every page it reads
  against what it learnt, and a page that drifted fails with exit code 3
  instead of returning nulls for weeks.
- **From autoscraper**, which learns where values are from examples of them:
  so does `compile --want`, on listings and on product pages that declare
  nothing, and what it learns is still checked on every page, so a price
  slot that starts saying "Add to basket" fails instead of being returned.
- **From an LLM scraper**: no model, no key, no bill, and the same answer
  every time.

[Why Sluicer](https://github.com/Gi0tto/sluicer/blob/main/docs/why.md) has the
full comparison, and when another tool is the better choice.

## Use it

```bash
sluicer extract page.html                           # a file, a URL, or - for stdin
sluicer inspect https://example.com/product         # the same, for a person to read
sluicer extract listing.html --induce               # rows of a page that declares nothing
sluicer markdown https://example.com/article        # the readable content
sluicer diff yesterday.html https://shop.example/p  # what changed, and where from
sluicer diff URL URL --at 2024-01                   # since the Wayback Machine's capture
sluicer extract URL --cache ~/.cache/sluicer        # ask the site if it changed (304)
sluicer audit https://example.com/product           # its markup against Google's documentation

sluicer compile page1.html page2.html -o shop.json  # learn an extractor
sluicer compile p1.html p2.html -o shop.json --want price=41.90 --want title="Brake pads"
sluicer run shop.json https://shop.example/c?p=7    # replay it, checked
sluicer heal shop.json https://shop.example/c -o shop.json  # after a redesign

sluicer map https://shop.example/                   # a site's addresses, from its sitemaps
sluicer crawl https://shop.example/ -o shop.jsonl   # follow its links, politely; --resume
sluicer batch urls.txt -o pages.jsonl               # read a list, one JSON line per page
sluicer warc crawl.warc.gz > pages.jsonl            # the pages a web archive holds
sluicer feed https://blog.example/                  # a feed's items, from the page that declares it
```

Exit codes follow grep: 0 found, 1 nothing declared, 2 could not read, and 3
for a page that broke its extractor, a heal that lost a field, or an audit that
found a documented rule broken. A drifted page never exits 0.

```python
import sluicer

result = sluicer.extract(html, url="https://example.com/p")
print(result.summary["title"].value, "via", result.summary["title"].key)
```

For an agent: `uvx --with 'sluicer[mcp]' sluicer mcp` is the MCP server, and
`claude mcp add sluicer -- uvx --with 'sluicer[mcp]' sluicer mcp` or
`codex mcp add sluicer -- uvx --with 'sluicer[mcp]' sluicer mcp` adds it;
Cursor, VS Code, Gemini CLI, Claude Desktop and Zed are in
[In your agent](https://github.com/Gi0tto/sluicer/blob/main/docs/agents.md).
The repository is also a Claude Code plugin, and its skill keeps to the open
Agent Skills format Codex reads. Ten tools --
`extract_declared`, `page_markdown`, `fetch_page`, `compile_extractor`,
`run_extractor`, `heal_extractor`, `audit_page`, `read_feed`, `map_site`,
`crawl_site` --
each answering with `ok`, which is true exactly when the answer can be used as
it is, and an output schema, and each saying in its annotations that it only
reads, so a client that asks before a tool writes runs it without asking. The
server fetches nothing on `localhost`, a
private network or a cloud's metadata endpoint -- redirects and a browser's
requests included -- unless started with `SLUICER_ALLOW_PRIVATE=1`.

For any other language: `sluicer serve` answers the same tools over HTTP,
`POST /v1/tools/<name>` with the tool's arguments as JSON, and describes them at
`/openapi.json`. It listens on loopback; anywhere else it needs
`SLUICER_API_TOKEN`. See [the HTTP API](https://github.com/Gi0tto/sluicer/blob/main/docs/http-api.md).

```bash
sluicer serve                                       # 127.0.0.1:8000
curl -s http://127.0.0.1:8000/v1/tools/extract_declared \
  -H 'Content-Type: application/json' -d '{"html_or_url": "https://example.com/p"}'
```

## Install

```bash
uv pip install sluicer                          # the library and the command: lxml and click
uv pip install 'sluicer[fetch,markdown,mcp]'    # fetching, markdown, the MCP server
uv pip install 'sluicer[api]'                   # the HTTP API, which brings those three
uv pip install 'sluicer[microformats]'          # microformats2, off by default
uvx --from 'sluicer[fetch]' scrapling install   # the browser, once, for the browser rung
```

Without a browser, plain HTTP still works, and a page that wanted one comes back
from the HTTP rung with the failed climb recorded.

## Measured, losses included

The summary beside the tools people use for the same job, on the 511 annotated
test pages of the public WCXB corpus. Hit rate is right answers over the pages
that carry a label; an invention is an answer on a page whose label is empty.

| | title | author | date | dates invented | seconds | packages |
|---|---|---|---|---|---|---|
| **sluicer 0.5.0** | 0.727 | 0.532 | 0.581 | **8** | **1.4** | **3** |
| trafilatura 2.2.0 | 0.745 | 0.750 | 0.838 | 216 | 16.2 | 17 |
| newspaper4k 0.9.6 | 0.768 | 0.532 | 0.645 | 52 | 29.6 | 22 |
| metascraper 5.58.1 | 0.654 | 0.787 | 0.374 | 84 | 2.5 | 125 |

WCXB strips every `<script>`, so JSON-LD, the vocabulary Sluicer reads first, is
not measured there. The same labels on the 360 of those pages that a web archive
holds as their servers sent them, scripts intact:

| as served | title | author | date | right when it answers a date | dates invented |
|---|---|---|---|---|---|
| **sluicer 0.5.0** | 0.708 | 0.690 | 0.780 | **0.734** | **36** |
| trafilatura 2.2.0 | 0.756 | 0.860 | 0.855 | 0.393 | 187 |
| newspaper4k 0.9.6 | 0.767 | 0.705 | 0.786 | 0.658 | 54 |
| metascraper 5.58.1 | 0.667 | 0.845 | 0.384 | 0.271 | 80 |

With the scripts back, JSON-LD appears on 236 of the 360 pages, and Sluicer's
author and date hit rates rise from 0.450 and 0.585 on WCXB's copies of the same
pages to 0.690 and 0.780. It still finds fewer authors and dates than
trafilatura, which also reads them from the visible text, and it is still the
most often right when it answers a date. 33 of its 36 invented dates are dates
the page declares in its own JSON-LD and does not show a reader, which is what
the labels describe. The method, every outcome and the commands that regenerate
both tables are in
[the scoreboard](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard.md)
and [the scoreboard on pages as served](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard-served.md).

On product pages -- Zyte's benchmark of 140, scored by Zyte's own evaluator --
Sluicer's price F1 is 0.750 and its availability F1 0.907, against 0.685 and
0.626 for the extruct baseline Zyte published and 0.918 and 0.957 for Zyte's
paid API, which reads the visible page with trained models. See
[the product scoreboard](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard-products.md).

On news in many languages -- fundus's fixtures, 263 pages from 42 countries'
publishers in 21 declared languages -- Sluicer's titles are the most often
right of the four tools, 0.871 against trafilatura's 0.852, and its dates are
never wrong when it answers one; trafilatura finds more authors, 0.879 against
0.829, and 12 of the 17 it finds and Sluicer does not are the paper's own
name, which Sluicer does not count an author. See
[the scoreboard on news in many languages](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard-news.md),
with a table per language.

Extractors are measured too: learnt on Wayback Machine captures of 25 sites and
replayed on later ones, 44 pairs, none failed silently and none raised a false
alarm. See [drift](https://github.com/Gi0tto/sluicer/blob/main/docs/drift.md).

## Principles

- **No LLM call, anywhere in the path.** A test fails the build if a model
  client is ever imported.
- **No paid API.** A feature that needs somebody's key does not ship.
- **Deterministic.** The same page always gives the same answer, which is what
  makes the scoreboard reproducible.
- **Honest about failure.** A page that cannot be read says so, and nothing
  returns a plausible answer where the truth was unavailable.

## Documentation

At <https://gi0tto.github.io/sluicer/>, or in the repository:
[Why Sluicer](https://github.com/Gi0tto/sluicer/blob/main/docs/why.md) ·
[Extractors](https://github.com/Gi0tto/sluicer/blob/main/docs/extractors.md) ·
[In your agent](https://github.com/Gi0tto/sluicer/blob/main/docs/agents.md) ·
[HTTP API](https://github.com/Gi0tto/sluicer/blob/main/docs/http-api.md) ·
[Audit](https://github.com/Gi0tto/sluicer/blob/main/docs/audit.md) ·
[Crawling](https://github.com/Gi0tto/sluicer/blob/main/docs/crawling.md) ·
[Scoreboard](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard.md) ·
[Scoreboard, as served](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard-served.md) ·
[Scoreboard, products](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard-products.md) ·
[Scoreboard, news](https://github.com/Gi0tto/sluicer/blob/main/docs/scoreboard-news.md) ·
[Drift](https://github.com/Gi0tto/sluicer/blob/main/docs/drift.md) ·
[Known limits](https://github.com/Gi0tto/sluicer/blob/main/docs/known-limits.md) ·
[Design notes](https://github.com/Gi0tto/sluicer/blob/main/docs/design-notes.md) ·
[Examples](https://github.com/Gi0tto/sluicer/tree/main/examples) ·
[Roadmap](https://github.com/Gi0tto/sluicer/blob/main/ROADMAP.md) ·
[Changelog](https://github.com/Gi0tto/sluicer/blob/main/CHANGELOG.md) ·
[Security](https://github.com/Gi0tto/sluicer/blob/main/SECURITY.md) ·
[Contributing](https://github.com/Gi0tto/sluicer/blob/main/CONTRIBUTING.md)

## Licence

MIT, with no vendored code, and two exceptions: `sluicer/audit/schema_org.py`
holds schema.org's type and enumeration names, which schema.org publishes
under CC BY-SA 3.0, and `sluicer/calendar_names.py` holds CLDR's month and
weekday names, which Unicode publishes under the Unicode License v3; each of
the two files is distributed under its own (the package's licence expression
is `MIT AND CC-BY-SA-3.0 AND Unicode-3.0`). The base install needs `lxml`
and `click`, both BSD-3-Clause. The extras pull a wider tree that is not all permissive: `tld` is
tri-licensed MPL-1.1, GPL-2.0-only or LGPL-2.1-or-later, `orjson` is MPL-2.0
alongside Apache-2.0 or MIT, and `certifi` is MPL-2.0. CI lists every licence
in that tree and fails on one nobody has read; see
[the licence notes](https://github.com/Gi0tto/sluicer/blob/main/docs/known-limits.md).
