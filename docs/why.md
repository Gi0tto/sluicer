# Why Sluicer

Most of what a scraper is asked for is already written into the page it
scrapes. A product page carries its name, price, currency and SKU in JSON-LD
for search engines; an article carries its headline, author and dates in
OpenGraph and meta tags. Sluicer reads that, rather than guessing it from the
visible text or asking a model to.

This page says where that puts it among the tools people reach for, and where
another tool is the better choice. It is a map, not a race.

## Where it sits

| | Sluicer | extruct | trafilatura | CSS-selector scraper | LLM scraper |
|---|---|---|---|---|---|
| Reads declared data (JSON-LD, microdata, RDFa, OpenGraph...) | yes, merged | yes, per vocabulary | partly | if you write it | if the model notices |
| Reads authors and dates from the visible prose | no | no | yes | if you write it | yes |
| One record per thing, across vocabularies | yes | no | no | no | varies |
| Says where every value came from | yes: reader, key and place on the page | per vocabulary | no | no | no |
| Same page, same answer | yes | yes | yes | yes | no |
| Notices when a site's layout changes | yes, exit 3 | no | no | no, returns nulls | no |
| Says what moved after a redesign | yes, `heal` | no | no | no | no |
| Fetches JavaScript-rendered pages | yes, a browser when measured necessary | no | no | depends | depends |
| Cost per page | CPU | CPU | CPU | CPU | tokens |

"Partly", "varies" and "depends" are honest: trafilatura reads some metadata
tags on its way to the text, an LLM scraper's behaviour is its prompt's, and a
hand-written scraper does whatever its author wrote.

## Beside the tools people star most

The same questions, asked of the scraping projects with the most stars and of
the two libraries nearest Sluicer's job. They do different work: Scrapling,
Crawl4AI and Firecrawl fetch and crawl, and Sluicer reads what any of them
fetched ([with other tools](agents.md#with-other-tools)). A `?` is a cell that
could not be checked from the project's own code or README.

| | Sluicer 0.7.0 | Scrapling 0.4.15 | Crawl4AI 0.9.4 | Firecrawl | extruct 0.18.0 | trafilatura 2.2.0 |
|---|---|---|---|---|---|---|
| Built for | reading what a page declares | fetching past defences, and parsing | crawling into markdown for models | a hosted API to scrape, crawl and search | the structured data syntaxes | a page's main text and metadata |
| Licence | MIT; two data files their own | BSD-3-Clause | Apache-2.0 | AGPL-3.0 | BSD-3-Clause | Apache-2.0 |
| JSON-LD, microdata, RDFa, OpenGraph | all, merged into one record per thing | none; you select elements | meta tags and OpenGraph; raw JSON-LD in its URL seeder | meta tags, OpenGraph and Dublin Core | all, one list per syntax | JSON-LD and meta tags, for its metadata fields |
| Where each value came from | vocabulary, key and place | -- | -- | -- | its syntax | -- |
| A model for structured output | never | never | optional; CSS and XPath strategies need none | for its JSON output | never | never |
| robots.txt, by default | obeyed, and not fetched when it cannot be read | not obeyed unless `robots_txt_obey` | not checked unless `check_robots_txt` | obeyed in a crawl; a single scrape only under a team setting | does not fetch | obeyed by its spider |
| Bot protection | none: it announces itself | its fetchers bypass anti-bot systems, its README says | a stealth mode, its README says | the service's job, its README says | does not fetch | does not fetch |
| When a site's layout changes | fails loudly, exit 3; `heal` says what moved | relocates an element by similarity, when asked | ? | ? | -- | -- |
| MCP server | ten tools, each annotated read-only | yes | in its Docker server | yes | no | no |
| Where it runs | your machine | your machine | your machine, or its Docker server | its cloud with a key, or self-hosted | your machine | your machine |

Read from each project at one commit on 2026-09-24 -- Scrapling `0b85f7e`,
Crawl4AI `86e6464`, Firecrawl `fd9c74c`, extruct `a31daaa`, trafilatura
`c852cae` -- among them Scrapling's `spiders/spider.py`
(`robots_txt_obey: bool = False`) and `parser.py` (`relocate`), Crawl4AI's
`async_configs.py` (`check_robots_txt: bool = False`), `utils.py`
(`extract_metadata`) and `async_url_seeder.py`, Firecrawl's
`controllers/v2/types.ts` (`ignoreRobotsTxt` defaulting to false),
`scrapeURL/shouldCheckRobots.ts`, `scrapeURL/lib/extractMetadata.ts` and
`scrapeURL/transformers/llmExtract.ts`, and trafilatura's `spider.py` and
`metadata.py`. The bot-protection row repeats
what each README claims; it was not tested here.

## What Sluicer adds

**One record per thing, with its provenance.** A page that describes the same
product in JSON-LD, microdata and OpenGraph gives one record, and every field
still names the vocabulary that declared it. Folding happens across
vocabularies, never inside one: two products on a listing stay two products,
because folding them would splice one's name onto the other's price.

**A summary that answers the usual questions, and says how.** Title,
description, author, dates, image, language, site name, publisher, type,
prices as Google reads them (the active one, the regular one, a range),
currency, availability, brand, SKU, GTIN, MPN, rating and breadcrumb, one value
each, chosen by fixed rules --
the article's `headline` before the site's name, `og:title` before `<title>`,
the price from inside `offers` -- and each naming its reader and key, so it can
be checked against the records.

**A page that contradicts itself, said so.** When the page declares a price,
a currency or a date two ways that mean different things -- 41.90 in JSON-LD
and 39.90 in OpenGraph -- `conflicts` lists both, with their places, instead of
choosing one silently. Four of Zyte's 140 product pages do.

**The tags nobody owns.** Across the 359 commercial pages of a public annotated
corpus, `article:published_time` is on 33% and `<meta name="author">` on 29%.
The first is OpenGraph's `article:` namespace; the second belongs to no
vocabulary, and Sluicer reports it as `"source": "html"`, because that is what
it is.

**Extractors that fail loudly.** Learn an extractor from two or three pages of
a template, replay it on any page of that template, and a page that drifted --
the listing moved, a field emptied, a price slot now says "Add to basket" --
fails with exit code 3 and the check that broke, instead of returning nulls
for weeks. After a redesign, `heal` says which field moved where, how many of
its old values were found in the new place, and keeps the column names your
code reads. See [extractors](extractors.md).

**A fetch that announces itself.** Plain HTTP first, a browser only when a
measurement says the cheap rung got a refusal, a challenge or an empty shell,
and every climb reported with its reason and its cost in seconds. Every
request says `Sluicer/<version>`, borrows no browser's referer or fingerprint,
and obeys `robots.txt` -- and nothing is fetched when `robots.txt` cannot be
read, as RFC 9309 says. The stealth rung exists and never runs unless asked.

**A tool an agent can trust.** Ten MCP tools, each answer with `ok` and an
output schema, an error that can never be mistaken for the page, and a server
that keeps every request -- redirects, images, frames, websockets -- off
private addresses unless told otherwise.

## When to use something else

- **You need the author or date of pages that do not declare them.**
  trafilatura reads them from the visible text, and on the WCXB corpus it finds
  far more of them. It also dates 216 pages that have no date; Sluicer
  answers less often and is wrong less often. See the
  [scoreboard](scoreboard.md).
- **You need the article's text.** `sluicer markdown` uses trafilatura for
  exactly that; for anything beyond it, use trafilatura directly.
- **The data is not declared and the pages are not a repeated template.**
  Induction reads listings and feeds; it does not read an arbitrary page's
  prose into fields. That is a model's job, and its answers should be checked.
- **You are crawling the web.** `sluicer crawl` reads a site politely -- one
  request at a time, a second apart or its `Crawl-delay`, resumable from its
  own output -- which is built for hundreds or thousands of pages of one site,
  not millions of many: its frontier lives in memory, and its pace is the
  site's. For a crawl at that scale, put Sluicer's extraction behind a crawler
  built for it.
- **You only need one vocabulary, raw.** extruct returns each vocabulary as the
  page wrote it, which is what you want when the merge is not.
