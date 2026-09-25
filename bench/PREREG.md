# What the scoreboards fix before they are run

A scoreboard is only a measure if what it measures, how it scores and what
counts as better are decided before the numbers are read. This file says what
is fixed. Changing any of it is a change to the scoreboards, made in its own
commit, with the pages it changes regenerated in that commit.

## Which pages Sluicer's rules were made on

Five of the six scoreboards, and the drift benchmark, had rules made while
their pages were read: a rule was written, measured on those pages, and kept
because the numbers there rose. Their numbers say how Sluicer does on pages it
was fitted to, not on pages it has never seen, and each of them says so. The
commits say it themselves:

| scoreboard | rules made while its pages were read, for example |
|---|---|
| WCXB, 511 test pages | `659f3a6`, `709856e` ("measured across the 359 WCXB pages"), `b86aa19` ("Measured on WCXB's 511-page test split") |
| as served, the same pages | `8e723ed` (the date and price forms they write), `7876710`, `074b4ad`, `f84541c` |
| news | `523e6b1`, `f84541c` ("Found on the multilingual news scoreboard"), `074b4ad` |
| trafilatura's set | `bebff9d` ("on the scoreboards' pages and trafilatura's evaluation set") |
| products | `7876710` ("Measured on Zyte's product benchmark"), `9548a35` (to pass extruct's SKU), `6fcbc7a` |
| drift | `92e5824`, `cd47d1b`, `af14095`, `f592d0c`, `faf097e`, `a8e7877` ("Found by the drift benchmark") |
| SWDE, development half | by design: `4978927` |

Held out, and only these:

- **SWDE's held-out half, less its camera sites.** Split before any full
  result was read; no rule was made reading its pages or its errors. Its
  numbers have been read three times, listed below, and one of those readings
  was to see whether a rule made on the development half held before it was
  kept. The ten camera sites were read before the split.
- **Every scoreboard, for `--visible` alone.** Its rules were made on WCXB's
  development split, which no scoreboard scores; the summary's rules were not.

Until 0.7.1, `bench/products.py` said "Nothing is tuned to these pages" and
this file called the scoreboards held out without saying for what; both were
wrong for the summary, and this section replaces them. From 0.7.1 on, a rule
measured on a scoreboard's pages names that scoreboard in its commit.

## The corpora, pinned

| scoreboard | corpus | pinned at | checked by |
|---|---|---|---|
| WCXB | Web Content Extraction Benchmark, test split, 511 pages | commit `c039d5ee9f5a` | `bench/corpus.py` |
| as served | the same pages from the Wayback Machine and Common Crawl, 360 | each capture's SHA-256 in `realweb-manifest.json` | `bench/realweb.py` stops on a mismatch |
| news | fundus parser fixtures, 263 pages, 42 countries | commit `c1b86b67501` | `bench/news.py` |
| trafilatura's set | trafilatura's evaluation pages, 990 (851 annotated) | commit `c852cae9708a` | `bench/evaldata.py` |
| products | Zyte's product-extraction benchmark, 140 pages | commit `cba97d7a8d42` | `bench/products.py` |
| drift | 44 Wayback pairs over 25 sites | `bench/drift/pairs.json` | `bench/drift/run.py` |
| SWDE | 80 sites, 124,291 pages, 9 archives | mirror commit `e9b60db`, each archive's SHA-256 | `bench/swde.py` stops on a mismatch |

No corpus is committed here; each is downloaded into `bench/cache/`.

## How an answer is scored

- Title, author and date (`bench/score.py`): a title is right when it equals
  the label, lowercased and spaces collapsed, or one contains the other and
  the shorter is at least 0.6 of the longer; an author when the shared name
  tokens cover half the label's and a quarter of the answer's; a date by the
  rule below. An answer where the label is empty is an invention.
- A date (fixed on 2026-09-24; before it, dateutil filled a part a date does
  not write with the day the scorer ran, so "March 2021" matched a label of
  2021-03-24 on the 24th of a month only, and "10:52" matched today). Both
  sides are parsed by dateutil with a fixed default, never the clock, and the
  parts each writes -- year, month, day -- are known by parsing it under two
  defaults that differ in every part.
  - **The label decides what must be said.** A hit when the answer writes
    every part the label writes, and each is the label's. A label of `2015-11`
    is matched by any day of November 2015; a label of `2018-07-10` is not
    matched by `July 2018`, nor by a time with no date.
  - **Day first or month first.** Numbers written with dots are read day
    first (`10.12.2022` is 10 December), as every language that writes dates
    with dots does; numbers written with slashes month first, dateutil's
    order (`11/01/2023` is 1 November). Every date label the scoreboards
    score is written year first: WCXB's (the as-served pages' too) and
    trafilatura's as `YYYY-MM-DD` (one WCXB label is `YYYY-MM`), fundus's as
    `YYYY-MM-DD hh:mm:ss`, most with a UTC offset. Only answers are written
    otherwise.
  - **Time zones.** When both carry a UTC offset they name an instant, and
    the answer is read in the label's offset before its calendar date is
    compared: metascraper writes every date in UTC, and fundus's labels in
    the publisher's own. Otherwise each date is read as written, since a
    label with no offset says no instant to convert to.
  - Measured on 2026-09-24 against the results then in `bench/cache/`: the
    old rule gave the same counts on every third day of 2026, and the new
    one changes five outcomes, all from wrong to hit -- metascraper's dates
    on four news pages (UTC against a label in +02:00 to +09:00) and one of
    Sluicer's on trafilatura's set (`10.12.2022`). The scoreboards to
    regenerate: news and trafilatura's set, whose numbers change, and the
    WCXB and as-served scoreboards, whose method text states the rule.
- Products: Zyte's `evaluate.py`, unchanged.
- SWDE (`bench/swde.py`): an answer is right when it equals one of the page's
  labels with spaces collapsed, the separators `: | , ; - – — > / · •` taken
  off both ends, and case folded, on both sides, for every tool alike. The
  labels' HTML entities are decoded first.
- Every tool is called for what the scoreboard asks: metascraper for its
  publication date, not its date, which puts the modification date first
  (fixed on 2026-09-24 after the first scoreboards had it wrong).

## SWDE's halves, and how often the held-out half is read

The sites were split before any full result was read, in commit `fc72378`
(2026-09-24): in each vertical, in alphabetical order, they alternate between
development and held-out. Rules are made reading the development half's pages
and errors only. The held-out half is scored, and read only as numbers:

| date | code | why |
|---|---|---|
| 2026-09-24 | 0.6.0 | the first scoreboard |
| 2026-09-24 | read-after-label, `4978927` (then `1b85481`, before a rebase) | whether it held beyond development |
| 2026-09-24 | 0.7.0 | the release's scoreboard |
| 2026-09-25 | 0.7.1 | the release's scoreboard |

The next reading is the release after 0.7.1. All ten camera sites were read
while the benchmark was built, before the split, so the held-out camera sites
are not a clean test; the scoreboard says so.

## `--visible`: made on WCXB's development split, measured on everything else

Fixed on 2026-09-24, before a line of it was written. The rules that read a
byline, a date or a title off the visible page are made reading only the
1,358 pages of WCXB's `dev` split, in the archive already pinned at
`c039d5e`, their labels, and Sluicer's answers on them. No scoreboard page is
read while they are made: WCXB's test split, the pages as served, the news
fixtures, trafilatura's set and Zyte's products are held out from
`--visible`'s rules -- not from the summary's, which were made on them, as the
first section says. When `--visible` is scored, each of them will show two
columns, what the page declares and what `--visible` adds; as of 0.7.1 none
does yet. A guess read off the visible page is never part of the summary, and
every invention it makes will be counted in its own column.

## What counts as worse

`bench/floors.json` holds, for every scoreboard, Sluicer's hit rate and share
right when answering per field, its inventions, SWDE's mean F1 per half and
its silent wrong answers. `uv run bench/gate.py --require` fails when a hit
rate or a share is below its floor or a count of inventions or silent wrong
answers is above its ceiling. It is run after every scoreboard before a
release is tagged. Floors rise with `--raise` when the numbers do, and are
lowered only with `--allow-regression`, in a commit that says why.

Planned, not yet done: a paired bootstrap over pages, with a fixed seed, so
that a difference between two versions or two tools is called better, worse
or inconclusive by a rule written here rather than by eye.

## The state of declared data: fixed before a WARC was read

Fixed on 2026-09-25, before any WARC file of the sample was downloaded and
before `bench/declared_report.py` was written. `docs/state-of-declared-data.md`
counts what pages declare about themselves on a sample of Common Crawl; this
says which sample, what a page is, and what is counted, so that nothing is
chosen after the counts are seen. A change to any of it is made in its own
commit, which says whether it was made after the counts were read.

**The crawl.** The first crawl listed in
<https://index.commoncrawl.org/collinfo.json> on 2026-09-25 whose
`warc.paths.gz` is published on `data.commoncrawl.org`: `CC-MAIN-2026-39`
(4 to 17 September 2026), the listing's `last-modified` 19 September 2026. The
listing is pinned by its SHA-256 in `bench/declared-manifest.json`.

**The files.** Four WARC files, chosen from the listing by position alone,
before any is opened: with the listing's N lines in the order it gives them,
the lines at 0-based index ⌊(2k+1)·N/8⌋ for k = 0, 1, 2, 3, the middle of
each quarter. Each is pinned by its path, size and SHA-256 in the manifest,
and the script stops if a file no longer hashes to its pin. They are
downloaded from `https://data.commoncrawl.org/` one after the other, never two
at once, with a pause of ten seconds between files, retrying with backoff on
503 and 5xx, under a User-Agent that names Sluicer and its repository.

**A page.** A WARC `response` record whose HTTP status is 200 and which
`sluicer.warc.read_warc` reads as HTML (its `Content-Type`, else Common
Crawl's `WARC-Identified-Payload-Type`, else how its body starts). Every other
record is counted by the reason it was left out, never silently dropped. A
record Common Crawl truncated (`WARC-Truncated`) is a page, as the crawler
kept it, and how many were truncated is reported.

**The reading.** Each page is read once, as `sluicer.extract` reads it, with
the headers it was served with, `microformats=True`, `induce=False` and
`visible=False`, by the Sluicer of this checkout; the last commit that touched
`src/`, and the versions of lxml, libxml2 and mf2py, are written into the
counts. Nothing is sampled within a file: every page is read.

**What is counted, per page.**

1. Which of Sluicer's readers found something (`Extraction.sources`): JSON-LD,
   microdata, microformats, RDFa (Lite, without OpenGraph's tags), Dublin
   Core, OpenGraph, the Twitter card, HTML's own meta names; and the pages
   with any of the first four, the vocabularies about things.
2. The schema.org types of the records (top 25, by pages declaring them). For
   JSON-LD also every typed node in every block as written, nested ones
   included, before references are resolved (top 20, by nodes).
3. Merging: pages with records from two or more of the vocabularies about
   things, and of those, the pages where one record holds fields from two or
   more of them.
4. Conflicts (`Extraction.conflicts`), per summary question: of the pages the
   summary answers it on, how many declare another answer that means
   something else; and which two readers disagree, most often.
5. JSON-LD blocks (`<script type="application/ld+json">`, not empty): how many
   are JSON as `json.loads` reads it by default, NaN and Infinity refused;
   how many more read as written once a raw control character inside a
   string is allowed; how many more Sluicer's lenient reader
   (`sluicer.declared.jsonld._parse`) recovers; how many are lost.
6. Normalisation: for the summary's `published`, `modified`, prices,
   `currency` and `gtin`, how many answers `Extraction.normalised` reads; for
   a GTIN, whether it has a GTIN's shape (8, 12, 13 or 14 digits once spaces
   and hyphens are dropped) and whether its check digit is right; the ten
   commonest shapes of the dates and prices that were not read (every digit
   written 9, every letter a).
7. `links`: a canonical, a canonical conflict, a canonical that is the page's
   own address exactly, `hreflang` alternates and `x-default`.
8. `rights`: `<meta name="robots">` and its directives, a crawler named in
   its place, `X-Robots-Tag`, TDMRep's `tdm-reservation` and `tdm-policy` in
   the page and in the headers, `rel=license`.

The sample itself is described by its pages, distinct hosts, top-level
domains and truncated records.

**Intervals.** Every rate is given with its 95% Wilson score interval, over
pages. Common Crawl takes many pages from one host, so pages are not
independent and the intervals are narrower than the sample's real
uncertainty; the report says so, and gives for the vocabularies the share of
hosts too (a host counts when any of its pages declares it).

**The comparison.** Only with what Web Data Commons publishes for the same
measure, from its latest extraction, the October 2024 Common Crawl
(`CC-MAIN-2024-42`), as its statistics page
<https://webdatacommons.org/structureddata/2024-12/stats/stats.html> gives it
on 2026-09-25: the share of parsed HTML pages with any triples, the pages per
format (embedded JSON-LD, microdata, RDFa, microformats' hCard), and the
JSON-LD classes by entities. WDC reads with Any23, full RDFa and
microformats1, on a crawl two years older; the report puts these beside
Sluicer's numbers, never inside them.

**Added after the counts were read** (2026-09-25, the one change so far). The
first count found microformats on nearly a third of the pages, four times Web
Data Commons' hCard, and among its commonest types `h-full` and `h-auto`:
Tailwind's and Bootstrap's height classes, which microformats2's parsing
rules take for roots, since any class of the form `h-` and letters is one.
So the microformats count is split, and the pages with any vocabulary about
things are counted again with microformats only where they are one of the
thirteen vocabularies the microformats wiki lists as microformats2's
(<https://microformats.org/wiki/microformats2#v2_vocabularies>, read on
2026-09-25: `h-adr`, `h-card`, `h-entry`, `h-event`, `h-feed`, `h-geo`,
`h-item`, `h-listing`, `h-product`, `h-recipe`, `h-resume`, `h-review`,
`h-review-aggregate`). A page with microformats is counted as one with a
record of one of those types, one whose records are all of other types, or
one whose roots gave no field at all; and the commonest microformats types
are listed. Nothing else changed, and the first count's other numbers stand.
