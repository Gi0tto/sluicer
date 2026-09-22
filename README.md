# Sluicer

Turn a web page into structured data with no model in the loop.

A sluice box separates gold from gravel using water and gravity. No mercury, no
cyanide, nothing you have to buy. Sluicer treats a web page the same way: it
recovers your data from the structure that's already in the page, so there's no
API key, no token bill, and the same page always gives you the same answer.

> **Status: scaffolding.** None of what follows works yet. This file is the plan
> and the standard we've agreed to be judged against. We're building the
> scoreboard before the claims, not after.

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

## What Sluicer does

One cascade, deterministic at every step.

1. **Read what the page already tells you.** JSON-LD, microdata, RDFa,
   OpenGraph. On a big slice of the commercial web the structured data is
   sitting right there in the source and nobody reads it.
2. **Induce the structure when nothing is declared.** Find the repeating
   subtrees, align the fields across them, hand back records.
3. **Fall back to the text.** Article body and boilerplate removal, delegated to
   `trafilatura`.

Then it tells you how much to trust what came out. Two pages built from the same
template have to produce the same fields. When they don't, the extraction is
suspect and Sluicer says so, with a number. Nothing gets asked for an opinion.

And it repairs itself. When a site changes its markup, you get a schema diff
naming what broke, instead of a quietly empty list.

## What Sluicer won't do

- **No LLM. Anywhere, ever.** Not as a fallback, not for the hard pages. A run
  costs you CPU and nothing else.
- **No paid API.** If a feature needs somebody's key to work, it doesn't ship.
- **No stealth arms race.** Fetching goes to `scrapling`, which does that job
  full time and does it well. Rewriting a browser is how side projects die.

## Keeping score

Every claim about being the best is marketing until somebody publishes the
ruler. So Sluicer ships a public scoreboard: the free datasets (WCXB,
WebMainBench, the combined ChatNoir set) plus a multilingual e-commerce split,
scored on every run, with the competition measured right next to us.

We publish the losses too. If Sluicer loses a category, you'll see it lose.

## Install

Not yet. When the first release lands you'll be able to install it as a CLI, as
a Python library, and as an MCP server, so Claude Code, Codex or anything else
that speaks the protocol can use it directly.

## Licence

MIT. Everything underneath is permissive as well: `scrapling` (BSD-3),
`trafilatura` (Apache-2.0), `lxml` (BSD-3). We vendor no AGPL code, so you can
drop Sluicer inside whatever you're building.
