# Scoreboard, on pages as served

[The scoreboard](scoreboard.md) measures Sluicer on WCXB's copies of its
pages, and WCXB removed every `<script>` from them, JSON-LD included.
This page measures the same tools, with the same labels and the same
scorer, on the same pages as their servers sent them, scripts intact,
fetched from web archives. Every page is scored twice, once as served
and once as WCXB kept it, so the difference between the two columns is
the difference the scripts make, and nothing else.
Regenerated on 2026-09-26 from commit `8a426a2` by
`uv run bench/realweb.py`, from the captures pinned in
[`bench/realweb-manifest.json`](https://github.com/Gi0tto/sluicer/blob/main/bench/realweb-manifest.json).

!!! warning "Sluicer's rules were made on these pages"
    Rules were written, measured on these pages and kept because the
    numbers here rose (`8e723ed`, `7876710`, `074b4ad`, among others), so this measures
    Sluicer on pages it was fitted to, not on pages it has never seen.
    Of the scoreboards, only SWDE's held-out half is a held-out test;
    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) says which pages each rule was made on.

!!! warning "Read this before the numbers"
    These are 360 of WCXB's 511 test pages: the ones an
    archive holds near the date WCXB saved them, and whose archived text
    proves they are the page WCXB labelled. A page no archive kept, or
    kept only as a wall or a later rewrite, is left out and counted
    below. Pages that are archived are not a random sample of the web,
    so compare the two columns with each other, not with the full
    scoreboard.

## Coverage

| pages | count |
|---|---|
| attempted | 511 |
| fetched (at least one capture read) | 373 |
| matched, and scored below | **360** |
| excluded | 151 |

| excluded because | pages | meaning |
|---|---|---|
| not fetched | 116 | an index or a capture refused or failed every retry |
| not archived | 18 | no capture in either archive within the window |
| different text | 10 | captured, but the text is not the labelled document's |
| too little text to verify | 3 | the WCXB page and its label hold too little text |
| no text | 3 | captured, but the capture holds almost no visible text |
| no address in the corpus | 1 | WCXB gives no address for the page |

Of the 360 matched pages, 359 came from the Wayback Machine, 1 came from Common Crawl. The median capture is 23 days from the target date; the furthest is 240.

Of the 116 pages not fetched, 107 are pages the Wayback Machine holds no capture of, whose only other source, Common Crawl's index, failed every retry while this was built. They are not known to be unarchived. `uv run bench/realweb.py --discover`, on a day the index answers, asks it again; every capture already read comes from the cache.

| page type | test pages | matched |
|---|---|---|
| article | 257 | 182 |
| service | 59 | 53 |
| forum | 51 | 12 |
| documentation | 42 | 39 |
| listing | 40 | 28 |
| collection | 34 | 24 |
| product | 28 | 22 |

## Results

Hit rate is hits over the pages that carry a label (360 titles, 129 authors, 159 dates on the 360 matched pages). Right when answering is hits over every answer given, inventions included. An invention is an answer on a page whose label is empty.

The same 360 pages, stripped (WCXB's copy) and served (the archive's):

| tool | field | labelled pages | hit rate, stripped | hit rate, served | right when answering, stripped | right when answering, served | wrong, stripped | wrong, served | inventions, stripped | inventions, served |
|---|---|---|---|---|---|---|---|---|---|---|
| sluicer 0.9.1 | title | 360 | 0.714 (0.66–0.76) | **0.708 (0.65–0.76)** | 0.714 (0.66–0.76) | **0.708 (0.65–0.76)** | 103 | 105 | 0 | 0 |
| sluicer 0.9.1 | author | 129 | 0.450 (0.36–0.54) | **0.690 (0.60–0.77)** | 0.644 (0.54–0.74) | **0.636 (0.55–0.72)** | 9 | 7 | 23 | 44 |
| sluicer 0.9.1 | date | 159 | 0.585 (0.50–0.66) | **0.780 (0.70–0.84)** | 0.939 (0.87–0.98) | **0.734 (0.66–0.80)** | 1 | 9 | 5 | 36 |
| trafilatura 2.2.0 | title | 360 | 0.756 (0.70–0.80) | **0.756 (0.70–0.80)** | 0.756 (0.70–0.80) | **0.756 (0.70–0.80)** | 88 | 88 | 0 | 0 |
| trafilatura 2.2.0 | author | 129 | 0.736 (0.65–0.81) | **0.860 (0.79–0.91)** | 0.583 (0.50–0.66) | **0.575 (0.50–0.65)** | 13 | 11 | 55 | 71 |
| trafilatura 2.2.0 | date | 159 | 0.849 (0.78–0.90) | **0.855 (0.79–0.91)** | 0.403 (0.35–0.46) | **0.393 (0.34–0.45)** | 23 | 23 | 177 | 187 |
| metascraper 5.58.1 | title | 360 | 0.667 (0.61–0.72) | **0.667 (0.61–0.72)** | 0.667 (0.61–0.72) | **0.667 (0.61–0.72)** | 120 | 120 | 0 | 0 |
| metascraper 5.58.1 | author | 129 | 0.744 (0.66–0.82) | **0.845 (0.77–0.90)** | 0.508 (0.43–0.58) | **0.482 (0.41–0.55)** | 22 | 16 | 71 | 101 |
| metascraper 5.58.1 | date | 159 | 0.704 (0.62–0.77) | **0.811 (0.74–0.87)** | 0.574 (0.50–0.65) | **0.573 (0.50–0.64)** | 18 | 16 | 65 | 80 |
| newspaper4k 0.9.6 | title | 360 | 0.775 (0.72–0.82) | **0.767 (0.72–0.81)** | 0.775 (0.72–0.82) | **0.767 (0.72–0.81)** | 81 | 84 | 0 | 0 |
| newspaper4k 0.9.6 | author | 129 | 0.457 (0.37–0.55) | **0.705 (0.62–0.78)** | 0.578 (0.48–0.67) | **0.569 (0.49–0.65)** | 13 | 12 | 30 | 57 |
| newspaper4k 0.9.6 | date | 159 | 0.623 (0.54–0.70) | **0.786 (0.71–0.85)** | 0.656 (0.57–0.73) | **0.658 (0.58–0.73)** | 8 | 11 | 44 | 54 |

Each rate carries its 95% Wilson score interval, the bounds rounded
outwards to two places. In plain words, as served, with every
difference called by the paired comparisons below:

- **Title.** Hit rate served 0.708, against 0.714 on the WCXB copy of the same pages (inconclusive); Sluicer behind newspaper4k and not told apart from trafilatura and metascraper. Right when answering: newspaper4k 0.767, trafilatura 0.756, sluicer 0.708, metascraper 0.667; Sluicer behind newspaper4k and not told apart from trafilatura and metascraper. Inventions: newspaper4k 0, trafilatura 0, sluicer 0, metascraper 0.
- **Author.** Hit rate served 0.690, against 0.450 on the WCXB copy of the same pages (better); Sluicer behind trafilatura and metascraper and not told apart from newspaper4k. Right when answering: sluicer 0.636, trafilatura 0.575, newspaper4k 0.569, metascraper 0.482; Sluicer ahead of trafilatura, metascraper and newspaper4k. Inventions: sluicer 44, trafilatura 71, newspaper4k 57, metascraper 101.
- **Date.** Hit rate served 0.780, against 0.585 on the WCXB copy of the same pages (better); Sluicer behind trafilatura and not told apart from metascraper and newspaper4k. Right when answering: sluicer 0.734, newspaper4k 0.658, metascraper 0.573, trafilatura 0.393; Sluicer ahead of trafilatura, metascraper and newspaper4k. Inventions: sluicer 36, newspaper4k 54, metascraper 80, trafilatura 187.

One caution about inventions on served pages. WCXB's annotators labelled
what a reader sees, and left a label empty where the visible page states
none. A served page can still declare a date or an author in JSON-LD
that the visible page never shows; the scorer counts that answer as an
invention, here as on the full scoreboard, and the scorer's rules were not
changed for this page. The table below says how many of Sluicer's
inventions each source produced.

## What the pages declare

| vocabulary | pages declaring it, stripped | pages declaring it, served |
|---|---|---|
| JSON-LD | 0 | 236 |
| microdata | 87 | 85 |
| RDFa | 14 | 14 |
| OpenGraph | 310 | 310 |
| Twitter card | 272 | 272 |
| Dublin Core | 2 | 2 |
| HTML meta names | 341 | 340 |
| none of them | 4 | 4 |

Out of 360 pages, as Sluicer's readers see them.

## Where Sluicer's served answers came from

| field | source | answers | hit | wrong | invention |
|---|---|---|---|---|---|
| title | jsonld | 187 | 138 | 49 | 0 |
| title | opengraph | 114 | 88 | 26 | 0 |
| title | html | 41 | 16 | 25 | 0 |
| title | microdata | 16 | 12 | 4 | 0 |
| title | twitter | 2 | 1 | 1 | 0 |
| author | jsonld | 115 | 74 | 7 | 34 |
| author | html | 16 | 13 | 0 | 3 |
| author | microdata | 7 | 2 | 0 | 5 |
| author | opengraph | 2 | 0 | 0 | 2 |
| date | jsonld | 143 | 103 | 7 | 33 |
| date | opengraph | 10 | 7 | 1 | 2 |
| date | microdata | 10 | 9 | 1 | 0 |
| date | html | 6 | 5 | 0 | 1 |

## How sure, and what differs

Sluicer against each other tool, on the pages as served:

| Sluicer against | field | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| trafilatura 2.2.0 | title | hit rate | -0.047 (-0.095 to +0.003) | inconclusive |
| trafilatura 2.2.0 | title | right when answering | -0.047 (-0.095 to +0.003) | inconclusive |
| trafilatura 2.2.0 | author | hit rate | -0.171 (-0.241 to -0.103) | worse |
| trafilatura 2.2.0 | author | right when answering | +0.061 (+0.005 to +0.117) | better |
| trafilatura 2.2.0 | date | hit rate | -0.075 (-0.140 to -0.012) | worse |
| trafilatura 2.2.0 | date | right when answering | +0.341 (+0.283 to +0.399) | better |
| metascraper 5.58.1 | title | hit rate | +0.042 (0.000 to +0.084) | inconclusive |
| metascraper 5.58.1 | title | right when answering | +0.042 (0.000 to +0.084) | inconclusive |
| metascraper 5.58.1 | author | hit rate | -0.155 (-0.227 to -0.087) | worse |
| metascraper 5.58.1 | author | right when answering | +0.153 (+0.101 to +0.210) | better |
| metascraper 5.58.1 | date | hit rate | -0.031 (-0.080 to +0.014) | inconclusive |
| metascraper 5.58.1 | date | right when answering | +0.160 (+0.113 to +0.211) | better |
| newspaper4k 0.9.6 | title | hit rate | -0.058 (-0.109 to -0.008) | worse |
| newspaper4k 0.9.6 | title | right when answering | -0.058 (-0.109 to -0.008) | worse |
| newspaper4k 0.9.6 | author | hit rate | -0.016 (-0.055 to +0.023) | inconclusive |
| newspaper4k 0.9.6 | author | right when answering | +0.067 (+0.025 to +0.112) | better |
| newspaper4k 0.9.6 | date | hit rate | -0.006 (-0.040 to +0.026) | inconclusive |
| newspaper4k 0.9.6 | date | right when answering | +0.076 (+0.039 to +0.116) | better |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
18 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

Every tool on the pages as served against the same pages as WCXB kept
them, the served rate minus the stripped one:

| tool | field | rate | served minus stripped (95% interval) | verdict |
|---|---|---|---|---|
| sluicer 0.9.1 | title | hit rate | -0.006 (-0.045 to +0.034) | inconclusive |
| sluicer 0.9.1 | title | right when answering | -0.006 (-0.045 to +0.034) | inconclusive |
| sluicer 0.9.1 | author | hit rate | +0.240 (+0.168 to +0.317) | better |
| sluicer 0.9.1 | author | right when answering | -0.009 (-0.080 to +0.064) | inconclusive |
| sluicer 0.9.1 | date | hit rate | +0.195 (+0.125 to +0.268) | better |
| sluicer 0.9.1 | date | right when answering | -0.206 (-0.273 to -0.142) | worse |
| trafilatura 2.2.0 | title | hit rate | 0.000 (-0.012 to +0.012) | inconclusive |
| trafilatura 2.2.0 | title | right when answering | 0.000 (-0.012 to +0.012) | inconclusive |
| trafilatura 2.2.0 | author | hit rate | +0.124 (+0.065 to +0.187) | better |
| trafilatura 2.2.0 | author | right when answering | -0.008 (-0.047 to +0.031) | inconclusive |
| trafilatura 2.2.0 | date | hit rate | +0.006 (-0.031 to +0.044) | inconclusive |
| trafilatura 2.2.0 | date | right when answering | -0.010 (-0.029 to +0.009) | inconclusive |
| metascraper 5.58.1 | title | hit rate | 0.000 (-0.012 to +0.012) | inconclusive |
| metascraper 5.58.1 | title | right when answering | 0.000 (-0.012 to +0.012) | inconclusive |
| metascraper 5.58.1 | author | hit rate | +0.101 (+0.032 to +0.170) | better |
| metascraper 5.58.1 | author | right when answering | -0.026 (-0.070 to +0.020) | inconclusive |
| metascraper 5.58.1 | date | hit rate | +0.107 (+0.040 to +0.174) | better |
| metascraper 5.58.1 | date | right when answering | -0.001 (-0.046 to +0.044) | inconclusive |
| newspaper4k 0.9.6 | title | hit rate | -0.008 (-0.023 to +0.006) | inconclusive |
| newspaper4k 0.9.6 | title | right when answering | -0.008 (-0.023 to +0.006) | inconclusive |
| newspaper4k 0.9.6 | author | hit rate | +0.248 (+0.174 to +0.326) | better |
| newspaper4k 0.9.6 | author | right when answering | -0.010 (-0.082 to +0.061) | inconclusive |
| newspaper4k 0.9.6 | date | hit rate | +0.164 (+0.093 to +0.235) | better |
| newspaper4k 0.9.6 | date | right when answering | +0.002 (-0.049 to +0.054) | inconclusive |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
42 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## What `--visible` adds, as served

`extract(..., visible=True)`, `--visible` on the command line, also
guesses the title, byline and dates a page shows, and keeps each guess
apart from the summary. Its rules were made on WCXB's development split
only, which no scoreboard scores, so these pages are held out from them
([`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)). *Declared* is the summary, as above;
*declared then `--visible`* answers with the summary where it has an
answer and with the guess where it has none, never in its place.

| field | hit rate, declared | hit rate, declared then `--visible` | right when answering, declared | right when answering, declared then `--visible` | inventions, declared | silent miss made a hit | silent miss made wrong | inventions `--visible` added |
|---|---|---|---|---|---|---|---|---|
| title | 0.708 (0.65–0.76) | 0.708 (0.65–0.76) | 0.708 (0.65–0.76) | 0.708 (0.65–0.76) | 0 | 0 | 0 | 0 |
| author | 0.690 (0.60–0.77) | 0.752 (0.67–0.82) | 0.636 (0.55–0.72) | 0.642 (0.56–0.72) | 44 | 8 | 1 | 2 |
| date | 0.780 (0.70–0.84) | 0.855 (0.79–0.91) | 0.734 (0.66–0.80) | 0.701 (0.63–0.77) | 36 | 12 | 0 | 13 |

`--visible` answered 36 questions the summary left unanswered: 20 right and 1 wrong where the page carries a label, and 15 invented where it carries none. Each rate carries its 95% Wilson score interval. Declared then `--visible` against the declared answers alone and against each other tool:

| declared then `--visible`, against | field | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| sluicer 0.9.1, declared | title | hit rate | 0.000 (0.000 to 0.000) | inconclusive |
| sluicer 0.9.1, declared | title | right when answering | 0.000 (0.000 to 0.000) | inconclusive |
| sluicer 0.9.1, declared | author | hit rate | +0.062 (+0.023 to +0.109) | better |
| sluicer 0.9.1, declared | author | right when answering | +0.007 (-0.015 to +0.028) | inconclusive |
| sluicer 0.9.1, declared | date | hit rate | +0.075 (+0.037 to +0.119) | better |
| sluicer 0.9.1, declared | date | right when answering | -0.033 (-0.063 to -0.004) | worse |
| trafilatura 2.2.0 | title | hit rate | -0.047 (-0.095 to +0.003) | inconclusive |
| trafilatura 2.2.0 | title | right when answering | -0.047 (-0.095 to +0.003) | inconclusive |
| trafilatura 2.2.0 | author | hit rate | -0.109 (-0.172 to -0.048) | worse |
| trafilatura 2.2.0 | author | right when answering | +0.067 (+0.014 to +0.121) | better |
| trafilatura 2.2.0 | date | hit rate | 0.000 (-0.060 to +0.062) | inconclusive |
| trafilatura 2.2.0 | date | right when answering | +0.308 (+0.256 to +0.362) | better |
| metascraper 5.58.1 | title | hit rate | +0.042 (0.000 to +0.084) | inconclusive |
| metascraper 5.58.1 | title | right when answering | +0.042 (0.000 to +0.084) | inconclusive |
| metascraper 5.58.1 | author | hit rate | -0.093 (-0.160 to -0.025) | worse |
| metascraper 5.58.1 | author | right when answering | +0.160 (+0.111 to +0.214) | better |
| metascraper 5.58.1 | date | hit rate | +0.044 (-0.013 to +0.100) | inconclusive |
| metascraper 5.58.1 | date | right when answering | +0.128 (+0.083 to +0.175) | better |
| newspaper4k 0.9.6 | title | hit rate | -0.058 (-0.109 to -0.008) | worse |
| newspaper4k 0.9.6 | title | right when answering | -0.058 (-0.109 to -0.008) | worse |
| newspaper4k 0.9.6 | author | hit rate | +0.047 (+0.007 to +0.091) | better |
| newspaper4k 0.9.6 | author | right when answering | +0.074 (+0.031 to +0.118) | better |
| newspaper4k 0.9.6 | date | hit rate | +0.069 (+0.028 to +0.114) | better |
| newspaper4k 0.9.6 | date | right when answering | +0.043 (+0.011 to +0.077) | better |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
24 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## Where Sluicer loses, as served

- **Author.** Sluicer misses 40 labelled pages, and on 27 of them another tool finds the author.
- **Date.** Sluicer misses 35 labelled pages, and on 23 of them another tool finds the date.
- **Title.** Of 105 wrong titles, 43 contain the label whole: the page declares a longer title than the heading the labels use.

## Every outcome

The 360 pages as served:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.9.1 | title | 255 | 105 | 0 | 0 | 0 | 0.708 (0.65–0.76) | 0.708 (0.65–0.76) |
| sluicer 0.9.1 | author | 89 | 7 | 33 | 187 | 44 | 0.690 (0.60–0.77) | 0.636 (0.55–0.72) |
| sluicer 0.9.1 | date | 124 | 9 | 26 | 165 | 36 | 0.780 (0.70–0.84) | 0.734 (0.66–0.80) |
| trafilatura 2.2.0 | title | 272 | 88 | 0 | 0 | 0 | 0.756 (0.70–0.80) | 0.756 (0.70–0.80) |
| trafilatura 2.2.0 | author | 111 | 11 | 7 | 160 | 71 | 0.860 (0.79–0.91) | 0.575 (0.50–0.65) |
| trafilatura 2.2.0 | date | 136 | 23 | 0 | 14 | 187 | 0.855 (0.79–0.91) | 0.393 (0.34–0.45) |
| metascraper 5.58.1 | title | 240 | 120 | 0 | 0 | 0 | 0.667 (0.61–0.72) | 0.667 (0.61–0.72) |
| metascraper 5.58.1 | author | 109 | 16 | 4 | 130 | 101 | 0.845 (0.77–0.90) | 0.482 (0.41–0.55) |
| metascraper 5.58.1 | date | 129 | 16 | 14 | 121 | 80 | 0.811 (0.74–0.87) | 0.573 (0.50–0.64) |
| newspaper4k 0.9.6 | title | 276 | 84 | 0 | 0 | 0 | 0.767 (0.72–0.81) | 0.767 (0.72–0.81) |
| newspaper4k 0.9.6 | author | 91 | 12 | 26 | 174 | 57 | 0.705 (0.62–0.78) | 0.569 (0.49–0.65) |
| newspaper4k 0.9.6 | date | 125 | 11 | 23 | 147 | 54 | 0.786 (0.71–0.85) | 0.658 (0.58–0.73) |

The same 360 pages as WCXB kept them:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.9.1 | title | 257 | 103 | 0 | 0 | 0 | 0.714 (0.66–0.76) | 0.714 (0.66–0.76) |
| sluicer 0.9.1 | author | 58 | 9 | 62 | 208 | 23 | 0.450 (0.36–0.54) | 0.644 (0.54–0.74) |
| sluicer 0.9.1 | date | 93 | 1 | 65 | 196 | 5 | 0.585 (0.50–0.66) | 0.939 (0.87–0.98) |
| trafilatura 2.2.0 | title | 272 | 88 | 0 | 0 | 0 | 0.756 (0.70–0.80) | 0.756 (0.70–0.80) |
| trafilatura 2.2.0 | author | 95 | 13 | 21 | 176 | 55 | 0.736 (0.65–0.81) | 0.583 (0.50–0.66) |
| trafilatura 2.2.0 | date | 135 | 23 | 1 | 24 | 177 | 0.849 (0.78–0.90) | 0.403 (0.35–0.46) |
| metascraper 5.58.1 | title | 240 | 120 | 0 | 0 | 0 | 0.667 (0.61–0.72) | 0.667 (0.61–0.72) |
| metascraper 5.58.1 | author | 96 | 22 | 11 | 160 | 71 | 0.744 (0.66–0.82) | 0.508 (0.43–0.58) |
| metascraper 5.58.1 | date | 112 | 18 | 29 | 136 | 65 | 0.704 (0.62–0.77) | 0.574 (0.50–0.65) |
| newspaper4k 0.9.6 | title | 279 | 81 | 0 | 0 | 0 | 0.775 (0.72–0.82) | 0.775 (0.72–0.82) |
| newspaper4k 0.9.6 | author | 59 | 13 | 57 | 201 | 30 | 0.457 (0.37–0.55) | 0.578 (0.48–0.67) |
| newspaper4k 0.9.6 | date | 99 | 8 | 52 | 157 | 44 | 0.623 (0.54–0.70) | 0.656 (0.57–0.73) |

## How a capture is chosen and matched

- **When.** WCXB records no capture date. The latest dates written inside its test pages cluster on 13 and 14 March 2026, and the split was committed on 29 March 2026, so the target is 2026-03-14. Captures are ranked by distance from it, either side, and none further than 183 days is considered.
- **Where.** The Wayback Machine first, asked through its timemap, each capture read with `id_`, the bytes as archived; then Common Crawl, crawl by crawl nearest first, each record read by a byte-range request into its WARC file. Only captures that answered 200 with HTML count. Where the address carries a click-tracking parameter (`srsltid`, `utm_*`, `gclid`), the address without it is asked as well.
- **How many.** At most 3 distinct bodies per page per archive, nearest first; the first one that matches is kept.
- **Same document.** The visible text of both pages (everything but `script`, `style`, `template` and `svg`), cut into 5-word shingles. The evidence is the labelled main text as it appears on the WCXB page; the score is the share of it found in the archived page. Where the two share fewer than 25 shingles (a listing labelled in a few words, a page with no main text labelled), the evidence is the WCXB page's whole visible text; where the WCXB page holds almost no text (it was in the scripts WCXB removed), the labelled main text alone. The manifest records, per page, the score, its basis, and the containment and Jaccard of the whole visible text.
- **Threshold: 0.6.** Cut where the distribution of best scores, over every page where a capture was read, is thinnest:

| match score | pages |
|---|---|
| [0.0, 0.1) | 4 |
| [0.1, 0.2) | 2 |
| [0.2, 0.3) | 2 |
| [0.3, 0.4) | 1 |
| [0.4, 0.5) | 2 |
| [0.5, 0.6) | 2 |
| [0.6, 0.7) | 1 |
| [0.7, 0.8) | 6 |
| [0.8, 0.9) | 10 |
| [0.9, 1.0] | 343 |

  The 360 captures kept score a median of 1.00, the lowest 0.68.
  The 7 left out between 0.2 and 0.6 are 3 collection, 2 listing, 1 article, 1 service,
  by WCXB's page types: a page that changed that much is left out rather
  than argued for.
- **Bytes.** Every tool reads the bytes as the archive holds them. 1 of the 360 are not UTF-8; Sluicer and trafilatura honour the page's charset, the newspaper4k and metascraper harnesses decode UTF-8, as they do on the full scoreboard.
- **Pinned.** The manifest holds, per page, the archive, the timestamp, the address asked and the SHA-256 of the body, and for Common Crawl the WARC file, offset and length; for every excluded page, the reason and the best capture tried. `uv run bench/realweb.py` fetches exactly those and stops if any digest differs.
- **Scoring.** `bench/score.py` and the tool harnesses in `bench/tools/` and `bench/metascraper/`, unchanged, at the pins the full scoreboard uses.
