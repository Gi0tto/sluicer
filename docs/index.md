<!-- mcp-name: io.github.Gi0tto/sluicer -->

<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/logo-dark.png">
    <img src="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/logo.png" alt="Sluicer" width="440">
  </picture>
</h1>

<p align="center">
  <strong>Web scrapers that fail loudly when a site's layout changes,<br>instead of quietly returning empty values.</strong><br>
  No model, no API key, no bill.
</p>

<p align="center">
  <a href="https://pypi.org/project/sluicer/"><img src="https://img.shields.io/pypi/v/sluicer" alt="PyPI"></a>
  <a href="https://pypi.org/project/sluicer/"><img src="https://img.shields.io/pypi/pyversions/sluicer" alt="Python versions"></a>
  <a href="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml"><img src="https://github.com/Gi0tto/sluicer/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Gi0tto/sluicer/blob/main/NOTICE"><img src="https://img.shields.io/badge/licence-MIT%2C%20two%20data%20files%20their%20own-yellow.svg" alt="MIT, two data files under their own licences"></a>
  <img src="https://img.shields.io/badge/LLM%20calls-none-blue" alt="no LLM calls">
</p>

<p align="center">
  <a href="https://gi0tto.github.io/sluicer/"><b>Documentation</b></a> ·
  <a href="getting-started.md"><b>Getting started</b></a> ·
  <a href="agents.md"><b>In your agent</b></a> ·
  <a href="scoreboard.md"><b>Scoreboards</b></a> ·
  <a href="faq.md"><b>FAQ</b></a> ·
  <a href="changelog.md"><b>Changelog</b></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/demo.gif" alt="An extractor learnt from a software directory in January 2016 replays a page of February 2016 and exits 0; on the page of June 2024, after the site's redesign, it fails loudly with exit 3; heal then proposes new places for the listing and five of its ten fields, each resting on one of five learnt values, which is a reason to check each move by hand" width="860">
</p>
<p align="center"><em>
  A real site, as the Wayback Machine kept it. The extractor learnt in January
  2016 still fits in February. After the 2024 redesign it stops with exit code
  3. <code>heal</code> then proposes new places for the listing and five of its
  ten fields, each move resting on one of five learnt values: moves to check,
  not a repair.
</em></p>

Most scrapers break without a sound. The site changes its markup, and the
scraper keeps running and returns nulls, or the wrong column, for weeks before
anyone notices.

Sluicer works the other way round. Show it a value on a few pages of a site
(a price, a title, a date) and it learns where that value lives. On every
page it reads after that, it checks the page against what it learnt. If the
layout has changed, the run fails with exit code 3 and names the check that
broke. `sluicer heal` then proposes where each field went, when the new page
still shows values the extractor was learnt from.

It also reads everything a page already declares about itself: JSON-LD,
microdata, RDFa, OpenGraph and four more vocabularies, merged into one record
per thing, with every value pointing to the exact place on the page it came
from. No model reads any page, so the same page always gives the same answer.

## Quick start

```bash
pip install sluicer   # or: uv tool install sluicer, pipx install sluicer

# Learn where a book's title and price sit, from two pages of one template.
sluicer compile https://books.toscrape.com/catalogue/page-1.html \
  https://books.toscrape.com/catalogue/page-2.html \
  --want title="A Light in the Attic" --want price=51.77 -o books.json

# Replay it on another page of that template: 20 rows of title and price, exit 0.
sluicer run books.json https://books.toscrape.com/catalogue/page-3.html

# A page it was not learnt for: exit 3, naming the check that failed.
sluicer run books.json https://quotes.toscrape.com/
```

books.toscrape.com and quotes.toscrape.com are public sandboxes made for
trying scrapers on. The last command prints `FAILED https://quotes.toscrape.com/:
expected the listing at html>body>…>ol.row, got not found`, its path shortened
here, and exits 3.

After a redesign, `sluicer heal` looks on the new page for the values the
extractor was learnt from, and proposes a new place for each field it finds
them in. In a clone of this repository, `examples/shop/` holds a made-up shop
before and after a redesign that renamed every class:

```bash
sluicer compile examples/shop/before-1.html examples/shop/before-2.html \
  --want title="A Light in the Attic" --want price=51.77 -o shop.json
sluicer run shop.json examples/shop/after.html   # exit 3: the listing is not found
sluicer heal shop.json examples/shop/after.html -o shop-healed.json
```

```text
container: html>body>div.page>ol.row -> html>body>main.content>div.page>section.grid
member: li.product -> div.card
moved: title -> h2.name>a (5 of 5 learnt values found there; the next best place had 0)
moved: price -> div.cost (5 of 5 learnt values found there; the next best place had 0)
Wrote shop-healed.json.
```

Each move says how many of the field's learnt values were found in its new
place, and how many the next best place held. `heal` proposes; it does not
repair. It can only move a field whose old values the new page still shows, so
run it on a page you learnt from, or one listing the same items. On the
[drift](drift.md) benchmark's
21 real redesigns, 18 of the new pages shared no item with the old ones, and
heal was fully right on none and partly right on 2. When a field or the listing
is lost, it exits 3 and writes nothing unless given `--force`.

Exit codes follow grep: 0 found -- a record or a summary answer, a `<title>`
alone included -- 1 found nothing, 2 could not read the page, and 3 when a page
broke its extractor's checks, a heal lost a field or left a move undecided, or
an audit found a documented rule broken. `diff` exits 1 when something changed.

The checks are about structure, not truth: a run fails when a field is no
longer where it was learnt, no longer reads the way it did, or no longer has
its shape. A change that keeps all three, such as a different number in the
price's place, passes. On SWDE, the checks flagged 18% of the extractors' wrong
answers; the other 82% passed.

Reading what a page declares needs no example at all. The product page read
here is
[`examples/brake-pads.html`](https://github.com/Gi0tto/sluicer/blob/main/examples/brake-pads.html),
in a clone of this repository; without one, fetch it first with
`mkdir -p examples && curl -o examples/brake-pads.html https://raw.githubusercontent.com/Gi0tto/sluicer/main/examples/brake-pads.html`.
The library is imported from the Python you ran `pip install sluicer` in:

```python
>>> import sluicer
>>> page = open("examples/brake-pads.html", "rb").read()
>>> result = sluicer.extract(page, url="https://example.com/p/bp-2210")
>>> price = result.summary["price"]
>>> price.value, price.source, price.key
('41.90', 'jsonld', 'Product.offers.price')
>>> price.where
'/html/head/script[1]#/offers/price'
>>> result.normalised
{'price': '41.90', 'currency': 'EUR', 'gtin': '4006381333931'}
>>> [(answer.value, answer.source) for answer in result.conflicts[0].answers]
[('41.90', 'jsonld'), ('39.90', 'opengraph')]
```

The page states one price in its JSON-LD and another in its OpenGraph tags;
Sluicer reports the conflict instead of picking one in silence. `sluicer inspect
page.html` shows the same reading laid out for a person.

## Install

```bash
pip install sluicer
```

That is the whole install for every command but one kind of page: it reads
HTML you have, fetches and crawls over plain HTTP, audits, learns extractors
and turns a page into markdown. For the `sluicer` command in an environment of
its own, `uv tool install sluicer` or `pipx install sluicer`; to run it once,
installing nothing, `uvx sluicer --version`; in a uv project, `uv add sluicer`.

A page a script draws, which plain HTTP brings back as an empty shell, needs a
browser: add the `browser` extra, then let Sluicer download Playwright's
Chromium once.

```bash
pip install "sluicer[browser]"
sluicer install browser
```

`sluicer doctor` says what is installed, what each missing piece is for, and
the command that adds it for the way you installed Sluicer (pip, uv tool, pipx
or uvx); a command that needs a missing extra names the same command.

<details>
<summary>What each extra adds</summary>

| extra | adds |
|---|---|
| `browser` | a browser, Playwright's Chromium, for a page plain HTTP brings back as an empty shell; download Chromium with `sluicer install browser` |
| `mcp` | the MCP server; add `browser` for pages that need one |
| `api` | the HTTP API, with `mcp` |
| `microformats` | microformats2, which is off by default |
| `all` | every extra above |
| `stealth` | the stealth rung, by scrapling: one page, only when asked with `--stealth`, never in a crawl; never in `all` |
| `markdown` | nothing more since 0.10, when trafilatura joined the base install; kept so an older install line still works |
| `fetch` | deprecated since 0.8: `browser` and `stealth` together, what it installed before |

The base install is `lxml`, `click`, `cssselect` (CSS selectors), `protego`
(robots.txt) and `trafilatura` (markdown), and `tomli` on Python 3.10 to read a
[configuration file](https://gi0tto.github.io/sluicer/configuration/): the
HTTP client is Python's own.

</details>

## What you can give it

| you have | run | and get |
|---|---|---|
| a page, as HTML or a URL | `sluicer extract page.html` | every record it declares, a summary that answers 25 questions, its conflicts, each value with where it came from |
| many pages of one template | `sluicer compile ... --want price=41.90`, then `sluicer run` | the fields you gave an example of, from every page, checked |
| the selectors you already know | `sluicer compile --select price='span.price::text' ...`, then `sluicer run` | the fields you named, held to the same checks: a selector a redesign broke fails the run |
| a page that declares nothing | `sluicer extract page.html --induce` | the rows its markup repeats: a listing's cards, a table's lines |
| a whole site | `sluicer map URL`, `sluicer crawl URL -o site.jsonl` | its addresses from its sitemaps, or every page it links to, read politely |
| a list of URLs, a web archive | `sluicer batch urls.txt`, `sluicer warc crawl.warc.gz` | one JSON line per page |
| a feed | `sluicer feed URL` | its items, as one JSON document |
| an article | `sluicer markdown URL` | its main text as Markdown |

Every request names Sluicer, and robots.txt and `Crawl-delay` are obeyed; a
crawl waits when a site asks it to. Only a command that reads single pages or
learns an extractor can be told otherwise, with `--stealth` or `--no-robots`;
`map`, `crawl` and `batch` cannot. `sluicer --help` lists every command, and
[the command line reference](reference/cli.md)
explains each one.

## In your agent

```bash
claude mcp add sluicer -- uvx --with "sluicer[mcp]" sluicer mcp   # Claude Code
codex mcp add sluicer -- uvx --with "sluicer[mcp]" sluicer mcp    # Codex
```

The MCP server has twelve read-only tools, among them `extract_declared`,
`select_values`, `compile_extractor`, `run_extractor` and `heal_extractor`. Every answer carries
`ok`, true only when it can be used as it is. The server does not fetch
localhost, private networks or cloud metadata addresses unless it is started
with `SLUICER_ALLOW_PRIVATE=1`.
[In your agent](agents.md)
covers Cursor, VS Code, Gemini CLI, Claude Desktop, Zed, LangChain, the OpenAI
Agents SDK and Pydantic AI. For any other language, `sluicer serve` offers the
same tools over HTTP ([HTTP API](http-api.md)),
and at `/mcp` the MCP server itself over streamable HTTP, for n8n, Dify and any
client that does not start servers over stdio
([Over HTTP](agents.md#over-http-n8n-and-dify)).

## Measured, losses included

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/swde-dark.svg">
    <img src="https://raw.githubusercontent.com/Gi0tto/sluicer/main/docs/assets/swde-light.svg" alt="Extractors learnt from three pages of each of 80 real sites and read on their other 124,051 pages: Sluicer scores a mean F1 of 0.850 and is right on 0.974 of its answers, with 11,156 wrong answers; Scrapling's adaptive selectors score 0.671 and 0.864, with 56,058" width="760">
  </picture>
</p>

Every number below comes from a public test set, and every scoreboard gives the
command that produces it again. Where another tool does better on what a row
measures, the row shows it.

| scoreboard | what is measured | Sluicer | beside it |
|---|---|---|---|
| [SWDE](scoreboard-swde.md), 80 sites | extractors learnt from three pages, run on the other 124,051 | F1 0.850, 11,156 wrong answers | Scrapling 0.671, 56,058 wrong |
| [Drift](drift.md), 44 before/after pairs on 25 sites | a change noticed: 21 changed, 23 did not | 0 failed silently, 0 false alarms | -- |
| [Products](scoreboard-products.md), 140 pages | price, availability (F1) | 0.750, 0.907 | Zyte's paid API 0.918, 0.957 |
| [WCXB](scoreboard.md), 511 pages | title, author, date found; dates invented | 0.727, 0.532, 0.581; 8 invented | trafilatura 0.745, 0.750, 0.838; 216 invented |
| [As served](scoreboard-served.md), 360 pages | dates found; right when it answers | 0.780; 0.734 | trafilatura 0.855; 0.393 |
| [News](scoreboard-news.md), 21 languages | title, author, date found | 0.871, 0.829, 0.970 | trafilatura 0.852, 0.879, 0.970 |
| [trafilatura's set](scoreboard-evaldata.md), 851 annotated pages | title, author, date found | 0.776, 0.468, 0.585 | trafilatura 0.738, 0.669, 0.865 |

Sluicer reads only what a page states in its markup, so on titles, authors and
dates it answers less often than tools that also read the visible text, and it
invents far fewer dates. Its rules were written while reading the pages of these
scoreboards, so the numbers show how it does on pages it was tuned on. The one
held-out test is the half of SWDE's sites whose pages and errors were not read
while making the rules; its numbers were read at each release and a few times
besides, each listed there, once to decide whether to keep a rule. There it scores 0.845, including five camera sites that
were read before the split and so are not a clean test.
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
records which pages each rule was made on.

## When not to use Sluicer

- **You need authors or dates that pages do not declare.** trafilatura reads
  them from the visible text and finds more of them. Sluicer's `--visible`
  option guesses them too: on the scoreboards it finds more of them and
  invents some, and on two of them its dates are right less often when it
  answers.
- **You need an article's full text.** `sluicer markdown` uses trafilatura for
  it; if you need trafilatura's options or other output formats, use it
  directly.
- **The site blocks bots.** Sluicer is not built to get past bot protection:
  every request names it, unless a single-page command is given `--stealth`.

[Why Sluicer](why.md) compares
it with extruct, trafilatura, Scrapling, Crawl4AI and Firecrawl, and says when
each is the better choice.

## Learn more

- [Getting started](getting-started.md),
  a ten-minute tour, and [Extractors](extractors.md),
  how learning, checking and healing work.
- [FAQ](faq.md),
  [Known limits](known-limits.md)
  and [What is stable](stability.md)
  before 1.0.
- [Moving from extruct](extruct.md):
  `from sluicer.compat import extruct` answers extruct's own calls.
- The full documentation is at <https://gi0tto.github.io/sluicer/>.

## Community

Questions, ideas and what you built go to
[Discussions](https://github.com/Gi0tto/sluicer/discussions). A page Sluicer
read wrong is [an issue](https://github.com/Gi0tto/sluicer/issues/new/choose):
attach the page, so the fix comes with a test. Report a vulnerability privately,
as [SECURITY.md](security.md)
explains, and see
[CONTRIBUTING.md](contributing.md)
to set up a checkout.

Sluicer is built and maintained by one person. If it saves you time or money,
[sponsoring it](https://github.com/sponsors/Gi0tto) pays for keeping the
scoreboards measured and the extractors working as the web changes.

## Licence

MIT, except two data files under their own licences: schema.org's type names
(CC BY-SA 3.0) and CLDR's month and weekday names (Unicode License v3); the
package's licence expression is `MIT AND CC-BY-SA-3.0 AND Unicode-3.0`. The base
install needs `lxml`, `click`, `cssselect` and `protego`, all BSD-3-Clause,
`trafilatura`, Apache-2.0, and on Python 3.10 `tomli`, MIT. The tree under
trafilatura and the extras is not all permissive: `tld` is MPL-1.1,
GPL-2.0-only or LGPL-2.1-or-later, and `certifi` is MPL-2.0, both brought by
trafilatura, and `orjson`, from an extra, is MPL-2.0 alongside Apache-2.0 or
MIT. CI lists every licence in that tree and fails on one
nobody has read; [NOTICE](https://github.com/Gi0tto/sluicer/blob/main/NOTICE)
says more.
