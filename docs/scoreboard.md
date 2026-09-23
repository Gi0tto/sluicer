# Scoreboard

How often Sluicer's `summary` gets a page's title, author and publication
date right, measured beside the tools people use for the same job, on a
public annotated corpus, with the losses in the same table as the wins.
Regenerated on 2026-09-23 from commit `eada8ca` by
`uv run bench/run.py`; the method and every pin are in
[`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).

!!! warning "Read this before the numbers"
    WCXB removed every `<script>` from its pages: of the 511 test
    pages, 0 carry a `<script>` and 0 carry JSON-LD. JSON-LD is the
    vocabulary Sluicer reads first, and the one many pages declare their
    article or product in, so here Sluicer is measured without its
    strongest reader.
    The other tools read JSON-LD too, but they also read visible text, and
    this corpus leaves them that. The same labels on the same pages as
    their servers sent them, scripts intact, are in
    [the scoreboard on pages as served](scoreboard-served.md).

## Results

Hit rate is hits over the pages that carry a label (509 titles, 188 authors, 265 dates on the 511 test pages). An invention is an answer on a page whose label is empty: WCXB leaves labels empty on purpose, so that column is how often a tool makes something up.

All 511 test pages:

| tool | title | author | date | authors invented | dates invented |
|---|---|---|---|---|---|
| sluicer 0.4.0 | 0.725 | 0.521 | 0.536 | 31 | 8 |
| trafilatura 2.2.0 | 0.745 | 0.750 | 0.838 | 98 | 216 |
| metascraper 5.58.1 | 0.654 | 0.787 | 0.374 | 125 | 84 |
| newspaper4k 0.9.6 | 0.768 | 0.532 | 0.645 | 50 | 52 |

The 359 article, listing, collection and product pages:

| tool | title | author | date | authors invented | dates invented |
|---|---|---|---|---|---|
| sluicer 0.4.0 | 0.745 | 0.521 | 0.598 | 19 | 3 |
| trafilatura 2.2.0 | 0.723 | 0.750 | 0.866 | 45 | 124 |
| metascraper 5.58.1 | 0.661 | 0.787 | 0.321 | 62 | 47 |
| newspaper4k 0.9.6 | 0.748 | 0.532 | 0.625 | 21 | 27 |

## Speed and size

| tool | seconds for all pages | packages installed |
|---|---|---|
| sluicer 0.4.0 | 1.37 | 3 |
| trafilatura 2.2.0 | 16.19 | 17 |
| metascraper 5.58.1 | 2.53 | 125 |
| newspaper4k 0.9.6 | 29.61 | 22 |

Seconds count only the extraction call, one page after another on one
core; packages count everything the tool's own environment holds.

## Where Sluicer loses, and why

- **Author.** Sluicer misses 90 labelled pages, and on 64 of them another tool finds the author.
- **Date.** Sluicer misses 123 labelled pages, and on 98 of them another tool finds the date.
- **Title.** Of 140 wrong titles, 64 contain the label whole: the page declares a longer title than the heading the labels use.

Authors and dates are where the gap is. The other tools also read bylines
and dates from the visible text of the page, where no vocabulary declares
them; Sluicer reads only what the page states in markup that means
something, and answers nothing rather than guess from prose. That is a
choice with a cost, and this is the cost.

## Where it wins

- **Title**, right when answering: newspaper4k 0.767, trafilatura 0.743, sluicer 0.724, metascraper 0.653. Fewest inventions: every tool ties at 1.
- **Author**, right when answering: sluicer 0.695, newspaper4k 0.599, trafilatura 0.551, metascraper 0.495. Fewest inventions: sluicer (31).
- **Date**, right when answering: sluicer 0.916, newspaper4k 0.710, trafilatura 0.463, metascraper 0.322. Fewest inventions: sluicer (8).

Right when answering counts every answer a tool gives, inventions
included. Sluicer gives none where the page states none; on a product or
category page with no publication date, a date is not a small error but a
fact that is not there.

Fastest: sluicer. Smallest install: sluicer.

## Every outcome

Right when answering is hits over every answer given, inventions
included.

All 511 test pages:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.4.0 | title | 369 | 140 | 0 | 1 | 1 | 0.725 | 0.724 |
| sluicer 0.4.0 | author | 98 | 12 | 78 | 292 | 31 | 0.521 | 0.695 |
| sluicer 0.4.0 | date | 142 | 5 | 118 | 238 | 8 | 0.536 | 0.916 |
| trafilatura 2.2.0 | title | 379 | 130 | 0 | 1 | 1 | 0.745 | 0.743 |
| trafilatura 2.2.0 | author | 141 | 17 | 30 | 225 | 98 | 0.750 | 0.551 |
| trafilatura 2.2.0 | date | 222 | 42 | 1 | 30 | 216 | 0.838 | 0.463 |
| metascraper 5.58.1 | title | 333 | 176 | 0 | 1 | 1 | 0.654 | 0.653 |
| metascraper 5.58.1 | author | 148 | 26 | 14 | 198 | 125 | 0.787 | 0.495 |
| metascraper 5.58.1 | date | 99 | 124 | 42 | 162 | 84 | 0.374 | 0.322 |
| newspaper4k 0.9.6 | title | 391 | 118 | 0 | 1 | 1 | 0.768 | 0.767 |
| newspaper4k 0.9.6 | author | 100 | 17 | 71 | 273 | 50 | 0.532 | 0.599 |
| newspaper4k 0.9.6 | date | 171 | 18 | 76 | 194 | 52 | 0.645 | 0.710 |

The 359 article, listing, collection and product pages:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.4.0 | title | 266 | 91 | 0 | 1 | 1 | 0.745 | 0.743 |
| sluicer 0.4.0 | author | 98 | 12 | 78 | 152 | 19 | 0.521 | 0.760 |
| sluicer 0.4.0 | date | 134 | 3 | 87 | 132 | 3 | 0.598 | 0.957 |
| trafilatura 2.2.0 | title | 258 | 99 | 0 | 1 | 1 | 0.723 | 0.721 |
| trafilatura 2.2.0 | author | 141 | 17 | 30 | 126 | 45 | 0.750 | 0.695 |
| trafilatura 2.2.0 | date | 194 | 29 | 1 | 11 | 124 | 0.866 | 0.559 |
| metascraper 5.58.1 | title | 236 | 121 | 0 | 1 | 1 | 0.661 | 0.659 |
| metascraper 5.58.1 | author | 148 | 26 | 14 | 109 | 62 | 0.787 | 0.627 |
| metascraper 5.58.1 | date | 72 | 111 | 41 | 88 | 47 | 0.321 | 0.313 |
| newspaper4k 0.9.6 | title | 267 | 90 | 0 | 1 | 1 | 0.748 | 0.746 |
| newspaper4k 0.9.6 | author | 100 | 17 | 71 | 150 | 21 | 0.532 | 0.725 |
| newspaper4k 0.9.6 | date | 140 | 12 | 72 | 108 | 27 | 0.625 | 0.782 |

## Method

- **Corpus.** The test split of [WCXB](https://github.com/Murrough-Foley/web-content-extraction-benchmark), the Web Content Extraction Benchmark by Murrough Foley, CC-BY-4.0, at commit `c039d5ee9f5a`.
  It is downloaded, never committed. Its labels are `title`, `author` and
  `publish_date`.
- **Outcomes.** With a label: hit, wrong, or silent miss. Without one:
  correct silence, or invention.
- **Title.** Lowercased, whitespace collapsed; equal, or one contains the
  other and the shorter is at least 0.6 of the longer.
- **Author.** Letter runs, lowercased, less *by, and, the, staff, team,
  editor(s), writer, de, von*; a hit when the shared tokens cover half the
  label's and a quarter of the answer's.
- **Date.** Both parsed with dateutil; a hit when the calendar dates are
  equal.
- **Sluicer.** `extract(html, url=...).summary`, fields `title`, `author`,
  `published`, base install, from this checkout.
- **trafilatura.** `extract_metadata(html, default_url=...)`.
- **metascraper.** The `title`, `author` and `date` rules, given the HTML
  and the page's address, on Node v26.1.0.
- **newspaper4k.** `Article.download(input_html=...)` then `parse()`, with
  image fetching off and the network taken away.
- **Environments.** Python 3.12 for the Python tools. Each tool is
  pinned, dependencies included, in `bench/requirements/` and
  `bench/metascraper/package-lock.json`.
