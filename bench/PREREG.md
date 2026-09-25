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
  numbers have been read at the readings listed below, and one of those readings
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
| W3C JSON-LD in HTML | the JSON-LD 1.1 test suite's `html-manifest.jsonld`, 50 tests | commit `ffdb326121ea` | `bench/w3c_jsonld.py` |

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

## The W3C JSON-LD tests in HTML

Fixed on 2026-09-25, while the harness was built and before its page was
first published. Building it, the readers' answers on eight of the pages were
read to learn what each returns, and the harness was run until PyLD, reading
the pages itself, was scored as the suite scores a processor: that is when
the page's loader began to keep a fragment, and to read the error code PyLD
wraps when it turns a document into RDF. The rules below were not changed by
the readers' results. No rule of Sluicer's was changed, and none is to be made
reading this suite's pages: the page is a conformance check, not a scoreboard
to tune to.

- **The suite.** `w3c/json-ld-api` at commit `ffdb326121ea`, its
  `tests/html-manifest.jsonld`, under the W3C Software and Document License:
  downloaded into `bench/cache/`, never vendored.
- **A reader** is given the page's bytes and its address (the suite's base
  IRI and the test's input, fragment included) and nothing of the test's
  options, since a reader takes none. Its answer, a list of values, or what it
  raised, is recorded as it is.
- **Processing.** PyLD, pinned in `bench/requirements/pyld.txt`, processes the
  answer as the document of the test's operation (expand, compact with the
  test's context, flatten, to N-Quads), with the test's `base` option or else
  the page's address as base, in JSON-LD 1.1's processing mode.
- **Comparison.** The suite README's JSON-LD object comparison: objects member
  by member, arrays in any order except a `@list`'s, values by strict
  equality, language tags case-insensitively; a flattened result is also
  right when it equals the expected one with every blank node label written
  alike and both are the same RDF graph; an RDF result by its canonical
  N-Quads (URDNA2015) against the expected file's.
- **A negative test** passes for a reader that answers nothing or raises, the
  two ways a reader refuses; any answer fails it.
- **The check on the harness.** PyLD reads every page itself with the test's
  options, through a loader that serves the suite from disk, and passes a
  negative test only by raising the test's error code. Every test PyLD fails
  is listed on the page.
- **Every failure** is given the first reason of these that holds: the test
  names a script by fragment; it wants the first script of several; it is a
  negative test the reader answered; the page sets a `<base href>`; the
  reader's answer is not the JSON the scripts hold; otherwise, the result
  differs.
- Sluicer's reader against extruct and against its own extruct interface are
  paired comparisons over the 50 tests, as above.

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
| 2026-09-25 | 0.7.1, the same results scored again | its intervals and the paired comparison with Scrapling, first printed |
| 2026-09-25 | 0.8.0 | the release's scoreboard |

The next reading is the release after 0.8.0. All ten camera sites were read
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

## How sure a number is, and how a difference is called

Fixed on 2026-09-24, before any interval or verdict was computed on a
scoreboard's results. `bench/stats.py` computes both, and its tests hold it to
hand computations.

- **A rate.** Every hit rate and share right when answering a scoreboard
  prints carries its 95% Wilson score interval. For k hits in n trials,
  p = k/n and z = 1.959963984540054, the normal's 97.5th percentile:
  centre (p + z²/2n) / (1 + z²/n), half-width
  z / (1 + z²/n) · √(p(1 − p)/n + z²/4n²). Wilson rather than p ± z·√(p(1−p)/n),
  since it stays inside 0 and 1 and is not zero wide at either, where several
  rates sit (the news dates are 1.000 right when answering). It is printed
  beside the rate, its bounds to two places rounded outwards, the lower down
  and the upper up, so what is printed always holds what was computed:
  `0.727 (0.68–0.77)`. A rate over no trials has no interval.
- **The trials are pages**, taken as independent: a hit rate's trials are the
  labelled pages, a share's the answers. Where they are not independent the
  interval is bootstrapped over what is: over sites for SWDE, since one
  extractor is learnt per site and its pages stand or fall together; over
  pages for trafilatura's main-text snippets, several of which sit on one page.
  A bootstrapped interval is the percentile interval below.
- **A difference.** Sluicer against another tool on the same pages, a page as
  served against the same page as WCXB kept it, and Sluicer today against the
  baseline its floors were written from are paired comparisons: both sides
  are scored on the same pages, so the pages are resampled together.
  - 10,000 samples of n pages drawn with replacement from the n scored, by
    Python's `random.Random(20260924).choices`, the pages listed in the order
    of their ids. Every comparison starts again from the seed, so each can be
    reproduced alone, whatever else the page compares.
  - On each sample the statistic is recomputed: the difference of the two hit
    rates, of the two shares right when answering, of two F1s (products, by
    Zyte's evaluator's own matching and formula), or of two mean F1s over
    sites (SWDE), always Sluicer's minus the other's, the served page's minus
    the stripped one's, today's minus the baseline's. A rate over no trials
    in a sample counts 0, as `bench/score.py` counts it.
  - The interval is the 95% percentile interval: of the 10,000 differences in
    ascending order, the 251st and the 9,750th.
  - The verdict: **better** when the interval's lower bound is above zero,
    **worse** when its upper bound is below zero, **inconclusive** otherwise,
    a bound of exactly zero included. A scoreboard's prose calls Sluicer ahead
    of or behind a tool only where the verdict does, and names an
    inconclusive difference as one.
  - No correction for making many comparisons. A scoreboard makes eighteen,
    three fields by three other tools by two rates; where the tools did not
    differ at all, about one in twenty would still be called better or worse.
    The verdicts are read as a table, not one at a time, and each page says
    so.
- Zyte's evaluator prints its own bootstrap standard deviation of each F1
  (1,000 resamples, seed 42); that ± is Zyte's and is kept as it is. The
  paired comparison beside it is this file's.

## How a second is measured

Fixed on 2026-09-24, after commit `b8f525e` re-timed Sluicer alone "on a
quieter machine" and published its new time beside the other tools' old ones.
`bench/timing.py` measures, and a generator publishes no second it did not
measure this way.

- Every tool in a table is timed in one run of `bench/timing.py`, on one
  machine, on the same pages: five rounds, each running every tool once, the
  tools' order turned by one place each round, so that a machine that slows
  down weighs on all of them.
- Each run is a fresh process in the tool's own environment. It reads every
  page once untimed, a warm-up that is thrown away, then times one pass over
  every page, the extraction call only.
- Printed: the median of the five timed passes, the fastest and the slowest
  beside it; pages per second is the pages over the median. Peak memory is
  the largest peak resident size (`getrusage`) of the five processes.
- Written on the page: the day it was measured, the platform, the CPU model,
  its cores and the machine's memory, the Python version, each tool's version,
  and the commit of this checkout.
- A generator refuses to publish a timing that is not all one run: a tool of
  its table missing from the record, a tool timed in another run than the
  others, a tool's version other than the one whose answers the page scores,
  a commit other than the one the page names, or a tree with uncommitted
  changes. A timing is reused only when none of these holds.
- SWDE takes 13 minutes of one pass for Sluicer and 28 for Scrapling; five
  rounds of a warm-up and a timed pass would take nearly seven hours, so its
  scoreboard prints no seconds. The drift benchmark prints none either: its
  run time is mostly reading the archive's captures.

## What counts as worse

`bench/floors.json` holds, for every scoreboard, Sluicer's hit rate and share
right when answering per field, its inventions, the products' F1s, SWDE's
mean F1 per half and its silent wrong answers; `bench/floors-pages.json`
holds the outcome of every page (every site-attribute for SWDE) the floors
were written from, the baseline. `uv run bench/gate.py --require` pairs
today's outcomes with the baseline's, page by page, and a floor is breached
when either holds:

1. **The drop is significant**: the paired comparison above calls today
   worse than the baseline. However small, the pages that got worse
   outnumber those that got better by more than resampling explains.
2. **The drop is past the floor's tolerance**: a rate or an F1 more than
   0.010 below its floor, or a count of inventions or silent wrong answers
   above its ceiling by more than 1% of what it is counted over (the pages
   scored; SWDE's labelled page-attributes of that half), whatever the
   comparison says, so a large change on few pages is never waved through
   as inconclusive.

A number past its floor but within the tolerance and not called worse is
reported as held within noise, and passes. The reason: Sluicer is
deterministic, so a number moves only when pages change outcome, and what the
gate asks is whether a change makes Sluicer worse beyond the pages that
happened to be sampled. On these corpora a page is 0.1 to 0.4 points, and the
Wilson interval of a rate over 500 pages is about eight points wide; a floor
missed by one page traded for another says nothing, yet it made a release
choose between failing and `--allow-regression`, and a gate lowered by hand
each time is no gate. The tolerance bounds what such trades can add up to:
`--raise` never lowers a floor, so small drops one after another can never
take a number more than 0.010 below it. `--raise` rewrites a scoreboard's
baseline only when every one of its numbers is at or above its floor (or with
`--allow-regression`), so a drop within the tolerance is compared with the
outcomes before it, not with itself. The gate is run after every scoreboard
before a release is tagged; floors rise with `--raise` when the numbers do,
and are lowered only with `--allow-regression`, in a commit that says why.
