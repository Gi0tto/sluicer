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
| Says where every value came from | yes, reader and key | per vocabulary | no | no | no |
| Same page, same answer | yes | yes | yes | yes | no |
| Notices when a site's layout changes | yes, exit 3 | no | no | no, returns nulls | no |
| Says what moved after a redesign | yes, `heal` | no | no | no | no |
| Fetches JavaScript-rendered pages | yes, a browser when measured necessary | no | no | depends | depends |
| Cost per page | CPU | CPU | CPU | CPU | tokens |

"Partly", "varies" and "depends" are honest: trafilatura reads some metadata
tags on its way to the text, an LLM scraper's behaviour is its prompt's, and a
hand-written scraper does whatever its author wrote.

## What Sluicer adds

**One record per thing, with its provenance.** A page that describes the same
product in JSON-LD, microdata and OpenGraph gives one record, and every field
still names the vocabulary that declared it. Folding happens across
vocabularies, never inside one: two products on a listing stay two products,
because folding them would splice one's name onto the other's price.

**A summary that answers the usual questions, and says how.** Title,
description, author, dates, image, language, site name, publisher, type, price,
currency, availability, brand and SKU, one value each, chosen by fixed rules --
the article's `headline` before the site's name, `og:title` before `<title>`,
the price from inside `offers` -- and each naming its reader and key, so it can
be checked against the records.

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

**A tool an agent can trust.** Six MCP tools, each answer with `ok` and an
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
- **You are crawling a site.** Sluicer fetches the page you ask for; it does
  not follow links, pace itself by `Crawl-delay`, or keep a frontier. Put it
  behind a crawler.
- **You only need one vocabulary, raw.** extruct returns each vocabulary as the
  page wrote it, which is what you want when the merge is not.
