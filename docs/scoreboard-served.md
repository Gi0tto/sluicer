# Scoreboard, on pages as served

[The scoreboard](scoreboard.md) measures Sluicer on WCXB's copies of its
pages, and WCXB removed every `<script>` from them, JSON-LD included.
This page measures the same tools, with the same labels and the same
scorer, on the same pages as their servers sent them, scripts intact,
fetched from web archives. Every page is scored twice, once as served
and once as WCXB kept it, so the difference between the two columns is
the difference the scripts make, and nothing else.
Regenerated on 2026-09-23 from commit `65cafca` by
`uv run bench/realweb.py`, from the captures pinned in
[`bench/realweb-manifest.json`](https://github.com/Gi0tto/sluicer/blob/main/bench/realweb-manifest.json).

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
| sluicer 0.3.0 | title | 360 | 0.711 | **0.706** | 0.711 | **0.706** | 104 | 106 | 0 | 0 |
| sluicer 0.3.0 | author | 129 | 0.434 | **0.674** | 0.651 | **0.649** | 10 | 7 | 20 | 40 |
| sluicer 0.3.0 | date | 159 | 0.553 | **0.748** | 0.936 | **0.735** | 1 | 9 | 5 | 34 |
| trafilatura 2.2.0 | title | 360 | 0.756 | **0.756** | 0.756 | **0.756** | 88 | 88 | 0 | 0 |
| trafilatura 2.2.0 | author | 129 | 0.736 | **0.860** | 0.583 | **0.575** | 13 | 11 | 55 | 71 |
| trafilatura 2.2.0 | date | 159 | 0.849 | **0.855** | 0.403 | **0.393** | 23 | 23 | 177 | 187 |
| metascraper 5.58.1 | title | 360 | 0.667 | **0.667** | 0.667 | **0.667** | 120 | 120 | 0 | 0 |
| metascraper 5.58.1 | author | 129 | 0.744 | **0.845** | 0.508 | **0.482** | 22 | 16 | 71 | 101 |
| metascraper 5.58.1 | date | 159 | 0.358 | **0.384** | 0.292 | **0.271** | 73 | 84 | 65 | 80 |
| newspaper4k 0.9.6 | title | 360 | 0.775 | **0.767** | 0.775 | **0.767** | 81 | 84 | 0 | 0 |
| newspaper4k 0.9.6 | author | 129 | 0.457 | **0.705** | 0.578 | **0.569** | 13 | 12 | 30 | 57 |
| newspaper4k 0.9.6 | date | 159 | 0.623 | **0.786** | 0.656 | **0.658** | 8 | 11 | 44 | 54 |

In plain words, as served:

- **Title.** Hit rate served 0.706, against 0.711 on the WCXB copy of the same pages. Sluicer is third of 4, behind newspaper4k 0.767, trafilatura 0.756. Right when answering: newspaper4k 0.767, trafilatura 0.756, sluicer 0.706, metascraper 0.667. Inventions: newspaper4k 0, trafilatura 0, sluicer 0, metascraper 0.
- **Author.** Hit rate served 0.674, against 0.434 on the WCXB copy of the same pages. Sluicer is fourth of 4, behind trafilatura 0.860, metascraper 0.845, newspaper4k 0.705. Right when answering: sluicer 0.649, trafilatura 0.575, newspaper4k 0.569, metascraper 0.482. Inventions: sluicer 40, trafilatura 71, newspaper4k 57, metascraper 101.
- **Date.** Hit rate served 0.748, against 0.553 on the WCXB copy of the same pages. Sluicer is third of 4, behind trafilatura 0.855, newspaper4k 0.786. Right when answering: sluicer 0.735, newspaper4k 0.658, trafilatura 0.393, metascraper 0.271. Inventions: sluicer 34, newspaper4k 54, trafilatura 187, metascraper 80.

One caution about inventions on served pages. WCXB's annotators labelled
what a reader sees, and left a label empty where the visible page states
none. A served page can still declare a date or an author in JSON-LD
that the visible page never shows; the scorer counts that answer as an
invention, here as on the full scoreboard, and the rules were not
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
| title | jsonld | 184 | 136 | 48 | 0 |
| title | opengraph | 117 | 90 | 27 | 0 |
| title | html | 41 | 15 | 26 | 0 |
| title | microdata | 16 | 12 | 4 | 0 |
| title | twitter | 2 | 1 | 1 | 0 |
| author | jsonld | 113 | 72 | 7 | 34 |
| author | html | 16 | 13 | 0 | 3 |
| author | microdata | 3 | 2 | 0 | 1 |
| author | opengraph | 2 | 0 | 0 | 2 |
| date | jsonld | 141 | 103 | 7 | 31 |
| date | opengraph | 10 | 7 | 1 | 2 |
| date | html | 6 | 5 | 0 | 1 |
| date | microdata | 5 | 4 | 1 | 0 |

## Where Sluicer loses, as served

- **Author.** Sluicer misses 42 labelled pages, and on 29 of them another tool finds the author.
- **Date.** Sluicer misses 40 labelled pages, and on 28 of them another tool finds the date.
- **Title.** Of 106 wrong titles, 45 contain the label whole: the page declares a longer title than the heading the labels use.

## Every outcome

The 360 pages as served:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.3.0 | title | 254 | 106 | 0 | 0 | 0 | 0.706 | 0.706 |
| sluicer 0.3.0 | author | 87 | 7 | 35 | 191 | 40 | 0.674 | 0.649 |
| sluicer 0.3.0 | date | 119 | 9 | 31 | 167 | 34 | 0.748 | 0.735 |
| trafilatura 2.2.0 | title | 272 | 88 | 0 | 0 | 0 | 0.756 | 0.756 |
| trafilatura 2.2.0 | author | 111 | 11 | 7 | 160 | 71 | 0.860 | 0.575 |
| trafilatura 2.2.0 | date | 136 | 23 | 0 | 14 | 187 | 0.855 | 0.393 |
| metascraper 5.58.1 | title | 240 | 120 | 0 | 0 | 0 | 0.667 | 0.667 |
| metascraper 5.58.1 | author | 109 | 16 | 4 | 130 | 101 | 0.845 | 0.482 |
| metascraper 5.58.1 | date | 61 | 84 | 14 | 121 | 80 | 0.384 | 0.271 |
| newspaper4k 0.9.6 | title | 276 | 84 | 0 | 0 | 0 | 0.767 | 0.767 |
| newspaper4k 0.9.6 | author | 91 | 12 | 26 | 174 | 57 | 0.705 | 0.569 |
| newspaper4k 0.9.6 | date | 125 | 11 | 23 | 147 | 54 | 0.786 | 0.658 |

The same 360 pages as WCXB kept them:

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.3.0 | title | 256 | 104 | 0 | 0 | 0 | 0.711 | 0.711 |
| sluicer 0.3.0 | author | 56 | 10 | 63 | 211 | 20 | 0.434 | 0.651 |
| sluicer 0.3.0 | date | 88 | 1 | 70 | 196 | 5 | 0.553 | 0.936 |
| trafilatura 2.2.0 | title | 272 | 88 | 0 | 0 | 0 | 0.756 | 0.756 |
| trafilatura 2.2.0 | author | 95 | 13 | 21 | 176 | 55 | 0.736 | 0.583 |
| trafilatura 2.2.0 | date | 135 | 23 | 1 | 24 | 177 | 0.849 | 0.403 |
| metascraper 5.58.1 | title | 240 | 120 | 0 | 0 | 0 | 0.667 | 0.667 |
| metascraper 5.58.1 | author | 96 | 22 | 11 | 160 | 71 | 0.744 | 0.508 |
| metascraper 5.58.1 | date | 57 | 73 | 29 | 136 | 65 | 0.358 | 0.292 |
| newspaper4k 0.9.6 | title | 279 | 81 | 0 | 0 | 0 | 0.775 | 0.775 |
| newspaper4k 0.9.6 | author | 59 | 13 | 57 | 201 | 30 | 0.457 | 0.578 |
| newspaper4k 0.9.6 | date | 99 | 8 | 52 | 157 | 44 | 0.623 | 0.656 |

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

  A capture of the same page scores near 1 even when a sidebar, a
  comment count or a price has moved; a homepage, a wall or another
  article scores near 0. What falls between is mostly a listing whose
  items have turned over, and is left out rather than argued for.
- **Bytes.** Every tool reads the bytes as the archive holds them. 1 of the 360 are not UTF-8; Sluicer and trafilatura honour the page's charset, the newspaper4k and metascraper harnesses decode UTF-8, as they do on the full scoreboard.
- **Pinned.** The manifest holds, per page, the archive, the timestamp, the address asked and the SHA-256 of the body, and for Common Crawl the WARC file, offset and length; for every excluded page, the reason and the best capture tried. `uv run bench/realweb.py` fetches exactly those and stops if any digest differs.
- **Scoring.** `bench/score.py` and the tool harnesses in `bench/tools/` and `bench/metascraper/`, unchanged, at the pins the full scoreboard uses.
