# The scoreboard

How often Sluicer's `summary` gets a page's title, author and publication date
right, measured beside trafilatura, metascraper and newspaper4k on a public
annotated corpus. The results, losses included, are in
[`docs/scoreboard.md`](../docs/scoreboard.md). This directory is how they are
made, so anyone can make them again.

```bash
uv run bench/run.py                    # everything, then docs/scoreboard.md
uv run bench/run.py --tools sluicer    # rerun one tool, reuse the others' results
```

It needs `uv` and, for metascraper, Node with `npm`. The first run downloads
the corpus, about 150 MB; after that it runs offline, in about two minutes.

## What is measured

The 511 pages of the test split of [WCXB](https://github.com/Murrough-Foley/web-content-extraction-benchmark),
the Web Content Extraction Benchmark by Murrough Foley, published under
CC-BY-4.0. `corpus.py` downloads it at one pinned commit into `bench/cache/`,
which is never committed. Its labels are `title`, `author` and `publish_date`,
and they are left empty on purpose where a page has none: author on 63% of the
pages, date on 48%.

**WCXB removed every `<script>` from its pages.** JSON-LD, the vocabulary
Sluicer reads first, is therefore invisible here, and Sluicer is measured
without its strongest reader. The scoreboard says so above its numbers and
counts it on every run.

The same labels are also scored on the pages **as their servers sent them**,
scripts intact, fetched from web archives: see below.

## How it is scored

`score.py`, four outcomes per field. With a label: **hit**, **wrong**, or
**silent miss**. Without one: **correct silence**, or **invention**. Hit rate is
hits over the labelled pages; right when answering is hits over every answer
given, inventions included.

- title: lowercased and whitespace collapsed; equal, or one contains the other
  and the shorter is at least 0.6 of the longer.
- author: letter runs, lowercased, less *by, and, the, staff, team, editor(s),
  writer, de, von*; a hit when the shared tokens cover half the label's and a
  quarter of the answer's, so a byline paragraph containing the name is not.
- date: both parsed with dateutil under a fixed default, never the day it runs;
  a hit when the answer writes every part of the date the label writes, year,
  month and day, alike. Dots are day first, slashes month first; with a UTC
  offset on both, the answer is read in the label's (`bench/PREREG.md`).

## How each tool runs

Each in an environment of its own, holding only what it needs, pinned with its
dependencies, given the same bytes and the page's address. Only the extraction
call is timed.

| tool | environment | call |
|---|---|---|
| Sluicer | this checkout, installed editable, base install | `extract(html, url=...).summary` |
| trafilatura | `requirements/trafilatura.txt` | `extract_metadata(html, default_url=...)` |
| metascraper | `metascraper/package-lock.json`, `npm ci` into the cache | the `title`, `author` and `date` rules |
| newspaper4k | `requirements/newspaper4k.txt` | `download(input_html=...)`, `parse()`, images off, no network |

Changing a pin, the corpus commit or a matching rule changes the scoreboard,
and belongs in the same commit as the regenerated `docs/scoreboard.md`.

## The same labels, on pages as served

[`docs/scoreboard-served.md`](../docs/scoreboard-served.md) scores the same
tools, with `score.py` and the same WCXB labels, on the test pages as they
were served, fetched from the Wayback Machine and Common Crawl, and on WCXB's
own copy of exactly the same pages beside it.

```bash
uv run bench/realweb.py                   # the pinned captures, then docs/scoreboard-served.md
uv run bench/realweb.py --tools sluicer   # rerun one tool, reuse the others' results
uv run bench/realweb.py --discover        # search the archives anew, rewrite the pins
```

The default run reads `realweb-manifest.json`, which pins, per page, the
archive, the capture's timestamp and address, and the SHA-256 of its body (and
for Common Crawl the WARC file, offset and length). It fetches exactly those
captures, once, into `bench/cache/realweb/`, and stops if any body no longer
hashes to its pin; after that it runs offline. Every excluded page is in the
manifest too, with the reason and the best capture tried.

`--discover` is what chose the pins, and rerunning it is a change to the
scoreboard. For each page it asks the Wayback Machine's timemap, then Common
Crawl's six crawls nearest the target, for captures that answered 200 with
HTML within 183 days of 14 March 2026, when WCXB saved its pages (WCXB records
no date; the latest dates inside its pages cluster there). It reads them
nearest first, at most three distinct bodies per archive, and keeps the first
whose visible text contains the page's labelled main text, measured in 5-word
shingles, at or above the threshold the scoreboard states and justifies. It is
polite: one request per second per archive host, four pages in flight, retries
with backoff on 429 and 5xx; a request that still fails is counted as not
fetched, never as an empty page. A full discovery takes about an hour.

## News in many languages

[`docs/scoreboard-news.md`](../docs/scoreboard-news.md) scores the same tools,
with `score.py`, on the parser fixtures of
[fundus](https://github.com/flairNLP/fundus) (MIT): one or two news pages per
publisher, from 42 countries' publishers, each with the title, authors and
publishing date fundus's hand-written parser for that publisher reads.

```bash
uv run bench/news.py                    # fundus at its pinned commit, then the scoreboard
uv run bench/news.py --tools sluicer    # rerun one tool, reuse the others
```

`news.py` downloads fundus at one pinned commit into `bench/cache/fundus/`
(about 17 MB) and pairs each page with its labels by running fundus's own
code, `bench/tools/fundus_labels.py`, in an environment holding that
checkout: the parser version valid on the day the page was crawled, as
fundus's test suite pairs them. Pages are grouped by the language their
`<html lang>` declares. The labels read the page a person sees, so a
headline the page declares for search and a different one it shows count as
a disagreement, and fundus stores its pages re-encoded as UTF-8 under their
original charset declaration.

## trafilatura's evaluation set

[`docs/scoreboard-evaldata.md`](../docs/scoreboard-evaldata.md) scores the
same tools, with `score.py`, on the 990 pages
[trafilatura](https://github.com/adbar/trafilatura) (Apache-2.0) evaluates
itself on, 851 of them annotated with their title, author and date; and it
scores `sluicer.markdown`'s main text against trafilatura's own text, as
trafilatura's evaluation scores it, by the snippets each output must and must
not hold.

```bash
uv run bench/evaldata.py                  # trafilatura at its pinned commit, then the scoreboard
uv run bench/evaldata.py --tools sluicer  # rerun one tool, reuse the others
```

`evaldata.py` downloads trafilatura at one pinned commit into
`bench/cache/evaldata/` and stores each page there, compressed, never in the
repository. The annotations were written to measure trafilatura, and follow
the byline and date a reader sees.

## extruct's interface, beside extruct

[`docs/extruct.md`](../docs/extruct.md) measures `sluicer.compat.extruct`
against extruct itself, syntax by syntax, on sluicer's test fixtures, the 360
pages as served and Zyte's 140 product pages.

```bash
uv run bench/extruct_compat.py            # both, then the table in docs/extruct.md
uv run bench/extruct_compat.py --reuse    # reuse extruct's last run
```

extruct runs in an environment of its own, pinned by
`requirements/extruct.txt`, on the interpreter running the script, since
`urljoin` changed between Python versions. It needs the served pages in
`bench/cache/realweb/`, which `bench/realweb.py` fetches, and downloads Zyte's
benchmark as `bench/products.py` does. A syntax is identical when the two
answers are equal as JSON, and RDFa when they are the same graph. Every
difference is put in the first category whose test explains it; one no test
explains fails the run.

## Extractors learnt from examples, on SWDE

[`docs/scoreboard-swde.md`](../docs/scoreboard-swde.md) measures what
`sluicer compile --want` promises: point at a value on a few pages of one
template, and read it on every other page of that template. The pages are
[SWDE](https://github.com/woailaosang/swde), the Structured Web Data Extraction
dataset (Hao, Cai, Pang and Zhang, SIGIR 2011, Microsoft Reciprocal License):
124,291 detail pages from 80 sites in 8 verticals, each labelled with the values
of three to five attributes. Scrapling's adaptive selectors are asked the same
thing, as the drift benchmark asks them.

```bash
uv run bench/swde.py                    # everything, then the scoreboard
uv run bench/swde.py --tools sluicer    # rerun one tool, reuse the other
uv run bench/swde.py --score-only       # score the last results again
```

`swde.py` downloads the nine archives of a GitHub mirror of SWDE's CodePlex
release at one pinned commit into `bench/cache/swde/` (about 200 MB), stops if
any does not hash to its pin, and unpacks them. For each site the first three
pages, in the dataset's order, are the seeds, and each attribute's example is
its first labelled value on the first seed that has one. The tools are given
the seeds and the examples, in `sites.json`, and never a test page's labels,
which only the scorer reads. Sluicer runs from this checkout, installed
editable; Scrapling from `requirements/scrapling.txt`.

A test page's answer is a hit when it equals one of the page's labels, spaces
collapsed and separators taken off both ends of both: SWDE labels whole text
nodes, so `ISBN-13<b>: 9780316125581` is labelled `: 9780316125581`. The labels'
HTML entities, stored undecoded, are decoded first.

**The sites are split in half, and the split was fixed before any full result
was read** (commit `fc72378`): in each vertical, in alphabetical order, sites
alternate between development and held-out. Rules for Sluicer are made while
reading only the development sites' pages and errors; the held-out sites are
only scored, and the scoreboard shows both halves. That half is the one
held-out test here: Sluicer's rules were made while the pages of the other
scoreboards and of the drift benchmark were read ([`PREREG.md`](PREREG.md)
says which).

## Before a release: the floors

[`PREREG.md`](PREREG.md) says what every scoreboard fixes before it is run:
the pinned corpora, how an answer is scored, SWDE's halves and how often the
held-out half has been read. After the scoreboards are run for a release,

```bash
uv run bench/gate.py --require    # fails if Sluicer does worse than bench/floors.json
uv run bench/gate.py --raise      # the floors follow the numbers up, never down
```

A floor is lowered only with `--allow-regression`, in a commit that says why.
