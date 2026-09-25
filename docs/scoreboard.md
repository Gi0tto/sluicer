# Scoreboard

How often Sluicer's `summary` gets a page's title, author and publication
date right, measured beside the tools people use for the same job, on a
public annotated corpus, with the losses in the same table as the wins.
Regenerated on 2026-09-25 from commit `a8ca1b1` by
`uv run bench/run.py`; the method and every pin are in
[`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).

!!! warning "Sluicer's rules were made on these pages"
    Rules were written, measured on these pages and kept because the
    numbers here rose (`659f3a6`, `709856e`, `b86aa19`, among others), so this measures
    Sluicer on pages it was fitted to, not on pages it has never seen.
    Of the scoreboards, only SWDE's held-out half is a held-out test;
    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) says which pages each rule was made on.

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
| sluicer 0.7.1 | 0.727 (0.68–0.77) | 0.532 (0.46–0.61) | 0.581 (0.52–0.64) | 42 | 8 |
| trafilatura 2.2.0 | 0.745 (0.70–0.79) | 0.750 (0.68–0.81) | 0.838 (0.78–0.88) | 98 | 216 |
| metascraper 5.58.1 | 0.654 (0.61–0.70) | 0.787 (0.72–0.84) | 0.725 (0.66–0.78) | 125 | 84 |
| newspaper4k 0.9.6 | 0.768 (0.72–0.81) | 0.532 (0.46–0.61) | 0.645 (0.58–0.71) | 50 | 52 |

The 359 article, listing, collection and product pages:

| tool | title | author | date | authors invented | dates invented |
|---|---|---|---|---|---|
| sluicer 0.7.1 | 0.748 (0.70–0.80) | 0.532 (0.46–0.61) | 0.598 (0.53–0.67) | 18 | 3 |
| trafilatura 2.2.0 | 0.723 (0.67–0.77) | 0.750 (0.68–0.81) | 0.866 (0.81–0.91) | 45 | 124 |
| metascraper 5.58.1 | 0.661 (0.61–0.71) | 0.787 (0.72–0.84) | 0.723 (0.66–0.78) | 62 | 47 |
| newspaper4k 0.9.6 | 0.748 (0.70–0.80) | 0.532 (0.46–0.61) | 0.625 (0.55–0.69) | 21 | 27 |

## Speed and size

Measured on 2026-09-25 by `uv run bench/timing.py wcxb` at commit `a8ca1b1`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | Python 3.12.13 | 0.0023 | 1.18 (1.11–1.62) | 434 | 88.7 MiB | 19.4 MiB | 3 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0316 | 16.13 (14.23–19.21) | 32 | 170.1 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0061 | 3.10 (2.83–6.33) | 165 | 718.0 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0696 | 35.57 (31.58–66.20) | 14 | 217.8 MiB | 39.4 MiB | 22 |

How install size and memory are counted, and the other tables, are in
[speed and weight](speed.md).

## Where Sluicer loses, and why

- **Author.** Sluicer misses 88 labelled pages, and on 62 of them another tool finds the author.
- **Date.** Sluicer misses 111 labelled pages, and on 86 of them another tool finds the date.
- **Title.** Of 139 wrong titles, 63 contain the label whole: the page declares a longer title than the heading the labels use.

By the paired comparisons below, Sluicer's hit rate is behind another tool's on title, author and date: on title, ahead of metascraper, behind newspaper4k and not told apart from trafilatura; on author, behind trafilatura and metascraper and not told apart from newspaper4k; on date, behind trafilatura, metascraper and newspaper4k.

The other tools also read bylines and dates from the visible text of
the page, where no vocabulary declares them; Sluicer reads only what the
page states in markup that means something, and answers nothing rather
than guess from prose. That is a choice with a cost, and the gap above
is the cost.

## Where it wins

- **Title**, right when answering: newspaper4k 0.767, trafilatura 0.743, sluicer 0.725, metascraper 0.653; Sluicer ahead of metascraper, behind newspaper4k and not told apart from trafilatura. Fewest inventions: every tool ties at 1.
- **Author**, right when answering: sluicer 0.654, newspaper4k 0.599, trafilatura 0.551, metascraper 0.495; Sluicer ahead of trafilatura and metascraper and not told apart from newspaper4k. Fewest inventions: sluicer (42).
- **Date**, right when answering: sluicer 0.917, newspaper4k 0.710, metascraper 0.625, trafilatura 0.463; Sluicer ahead of trafilatura, metascraper and newspaper4k. Fewest inventions: sluicer (8).

Right when answering counts every answer a tool gives, inventions
included. Where a page's label is empty, the tools answered all the
same: sluicer 1 title, 42 authors and 8 dates; trafilatura 1 title, 98 authors and 216 dates; metascraper 1 title, 125 authors and 84 dates; newspaper4k 1 title, 50 authors and 52 dates. On a product or category page with no
publication date, a date is not a small error but a fact that is not
there.

Fastest median pass: sluicer. Smallest install: sluicer; fewest packages: sluicer.

## How sure, and what differs

Each rate above carries its 95% Wilson score interval, the bounds
rounded outwards to two places. Sluicer against each other tool:

| Sluicer against | field | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| trafilatura 2.2.0 | title | hit rate | -0.018 (-0.052 to +0.016) | inconclusive |
| trafilatura 2.2.0 | title | right when answering | -0.018 (-0.051 to +0.016) | inconclusive |
| trafilatura 2.2.0 | author | hit rate | -0.218 (-0.296 to -0.145) | worse |
| trafilatura 2.2.0 | author | right when answering | +0.103 (+0.039 to +0.164) | better |
| trafilatura 2.2.0 | date | hit rate | -0.257 (-0.319 to -0.196) | worse |
| trafilatura 2.2.0 | date | right when answering | +0.454 (+0.403 to +0.506) | better |
| metascraper 5.58.1 | title | hit rate | +0.073 (+0.045 to +0.102) | better |
| metascraper 5.58.1 | title | right when answering | +0.073 (+0.045 to +0.101) | better |
| metascraper 5.58.1 | author | hit rate | -0.255 (-0.329 to -0.183) | worse |
| metascraper 5.58.1 | author | right when answering | +0.159 (+0.099 to +0.219) | better |
| metascraper 5.58.1 | date | hit rate | -0.143 (-0.198 to -0.091) | worse |
| metascraper 5.58.1 | date | right when answering | +0.291 (+0.237 to +0.349) | better |
| newspaper4k 0.9.6 | title | hit rate | -0.041 (-0.073 to -0.009) | worse |
| newspaper4k 0.9.6 | title | right when answering | -0.041 (-0.073 to -0.009) | worse |
| newspaper4k 0.9.6 | author | hit rate | 0.000 (-0.057 to +0.056) | inconclusive |
| newspaper4k 0.9.6 | author | right when answering | +0.055 (-0.006 to +0.116) | inconclusive |
| newspaper4k 0.9.6 | date | hit rate | -0.064 (-0.106 to -0.023) | worse |
| newspaper4k 0.9.6 | date | right when answering | +0.207 (+0.155 to +0.261) | better |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
18 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## Every outcome

Right when answering is hits over every answer given, inventions
included.

All 511 test pages:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | title | 370 | 139 | 0 | 1 | 1 | 0.727 (0.68–0.77) | 0.725 (0.68–0.77) |
| sluicer 0.7.1 | author | 100 | 11 | 77 | 281 | 42 | 0.532 (0.46–0.61) | 0.654 (0.57–0.73) |
| sluicer 0.7.1 | date | 154 | 6 | 105 | 238 | 8 | 0.581 (0.52–0.64) | 0.917 (0.86–0.95) |
| trafilatura 2.2.0 | title | 379 | 130 | 0 | 1 | 1 | 0.745 (0.70–0.79) | 0.743 (0.70–0.78) |
| trafilatura 2.2.0 | author | 141 | 17 | 30 | 225 | 98 | 0.750 (0.68–0.81) | 0.551 (0.48–0.62) |
| trafilatura 2.2.0 | date | 222 | 42 | 1 | 30 | 216 | 0.838 (0.78–0.88) | 0.463 (0.41–0.51) |
| metascraper 5.58.1 | title | 333 | 176 | 0 | 1 | 1 | 0.654 (0.61–0.70) | 0.653 (0.61–0.70) |
| metascraper 5.58.1 | author | 148 | 26 | 14 | 198 | 125 | 0.787 (0.72–0.84) | 0.495 (0.43–0.56) |
| metascraper 5.58.1 | date | 192 | 31 | 42 | 162 | 84 | 0.725 (0.66–0.78) | 0.625 (0.57–0.68) |
| newspaper4k 0.9.6 | title | 391 | 118 | 0 | 1 | 1 | 0.768 (0.72–0.81) | 0.767 (0.72–0.81) |
| newspaper4k 0.9.6 | author | 100 | 17 | 71 | 273 | 50 | 0.532 (0.46–0.61) | 0.599 (0.52–0.68) |
| newspaper4k 0.9.6 | date | 171 | 18 | 76 | 194 | 52 | 0.645 (0.58–0.71) | 0.710 (0.64–0.77) |

The 359 article, listing, collection and product pages:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | title | 267 | 90 | 0 | 1 | 1 | 0.748 (0.70–0.80) | 0.746 (0.69–0.79) |
| sluicer 0.7.1 | author | 100 | 11 | 77 | 153 | 18 | 0.532 (0.46–0.61) | 0.775 (0.69–0.84) |
| sluicer 0.7.1 | date | 134 | 3 | 87 | 132 | 3 | 0.598 (0.53–0.67) | 0.957 (0.90–0.99) |
| trafilatura 2.2.0 | title | 258 | 99 | 0 | 1 | 1 | 0.723 (0.67–0.77) | 0.721 (0.67–0.77) |
| trafilatura 2.2.0 | author | 141 | 17 | 30 | 126 | 45 | 0.750 (0.68–0.81) | 0.695 (0.62–0.76) |
| trafilatura 2.2.0 | date | 194 | 29 | 1 | 11 | 124 | 0.866 (0.81–0.91) | 0.559 (0.50–0.62) |
| metascraper 5.58.1 | title | 236 | 121 | 0 | 1 | 1 | 0.661 (0.61–0.71) | 0.659 (0.60–0.71) |
| metascraper 5.58.1 | author | 148 | 26 | 14 | 109 | 62 | 0.787 (0.72–0.84) | 0.627 (0.56–0.69) |
| metascraper 5.58.1 | date | 162 | 21 | 41 | 88 | 47 | 0.723 (0.66–0.78) | 0.704 (0.64–0.76) |
| newspaper4k 0.9.6 | title | 267 | 90 | 0 | 1 | 1 | 0.748 (0.70–0.80) | 0.746 (0.69–0.79) |
| newspaper4k 0.9.6 | author | 100 | 17 | 71 | 150 | 21 | 0.532 (0.46–0.61) | 0.725 (0.64–0.80) |
| newspaper4k 0.9.6 | date | 140 | 12 | 72 | 108 | 27 | 0.625 (0.55–0.69) | 0.782 (0.71–0.84) |

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
- **Date.** Both parsed with dateutil under a fixed default; a hit when
  the answer writes every part of the date the label writes, alike. Dots
  are day first, slashes month first; with a UTC offset on both, the
  answer is read in the label's. The rule is in `bench/PREREG.md`.
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
