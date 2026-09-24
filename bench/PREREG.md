# What the scoreboards fix before they are run

A scoreboard is only a measure if what it measures, how it scores and what
counts as better are decided before the numbers are read. This file says what
is fixed. Changing any of it is a change to the scoreboards, made in its own
commit, with the pages it changes regenerated in that commit.

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
  tokens cover half the label's and a quarter of the answer's; a date when
  both parse to the same calendar day. An answer where the label is empty is
  an invention.
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
| 2026-09-24 | branch `toward-070` at `1b85481` | whether read-after-label held beyond development |

The next reading is the release of 0.7.0. All ten camera sites were read
while the benchmark was built, before the split, so the held-out camera sites
are not a clean test; the scoreboard says so.

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
