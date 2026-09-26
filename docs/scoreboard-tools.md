# Every tool, on the same pages

The tools people reach for to turn a web page into its title, author,
date and text, each in an environment of its own, pinned, given the same
bytes of the same pages as their servers sent them, scripts intact, and
scored one way: which answers are right, which are wrong with nothing to
say so, how much of the main text each keeps, and how much of the
site's menus and footers comes with it.
Regenerated on 2026-09-26 from commit `5e97f6b` by
`uv run bench/tools_compare.py`; what is asked and how it is scored were
fixed in [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) before any tool was run.

!!! warning "Sluicer's rules were made on these pages"
    Rules were written, measured on these pages and kept because the
    numbers here rose (`659f3a6`, `8e723ed`, `bebff9d`, among others), so this measures
    Sluicer on pages it was fitted to, not on pages it has never seen.
    Of the scoreboards, only SWDE's held-out half is a held-out test;
    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) says which pages each rule was made on.

!!! note "What this is not"
    Sluicer's text is trafilatura's extraction written as markdown, by
    design (`sluicer.markdown`), so on the text the two differ by how
    trafilatura is called, not by two ways of finding it. Sluicer's
    summary holds only what a page declares in markup; `--visible` adds
    what the page shows, kept apart. Firecrawl is left out: its service
    needs an account and a key, and its self-hosted form is a Docker
    Compose of several services, not a package to pin beside the others.
    Scrapy has no reading of its own for a title, a date or a text, only
    the selectors someone writes.

## The pages

- **WCXB's test pages as served**: WCXB's test pages as the Wayback Machine and
  Common Crawl kept them, pinned by `bench/realweb-manifest.json`, with
  WCXB's labels (drafted with a language model, then reviewed by people):
  360 pages; 360 annotated for their metadata, 360 with a title, 129 with an author, 159 with a date; 1457 `with` and 1208 `without` snippets; the whole main text on 358.
- **trafilatura's evaluation set**: the pages trafilatura evaluates itself on,
  annotated by hand by its authors, at the commit `bench/evaldata.py` pins:
  990 pages; 851 annotated for their metadata, 845 with a title, 538 with an author, 728 with a date; 2951 `with` and 2966 `without` snippets.
- **the page added by hand**: one page, written into
  `bench/tools-added.json` with labels written by hand. One page carries
  no rate; it is shown answer by answer, below, and pooled into nothing.

A dash is a question the tool does not answer, never a zero.

## Where Sluicer stands

As the paired comparisons below call it, and nowhere else: ahead or
behind only where the 95% interval of the difference leaves out zero.

On WCXB's test pages as served:

- **title, hit rate**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0 and metascraper 5.58.1.
- **title, right when answering**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0 and metascraper 5.58.1.
- **author, hit rate**: behind trafilatura 2.2.0 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.
- **author, right when answering**: ahead of trafilatura 2.2.0, newspaper4k 0.9.6 and metascraper 5.58.1.
- **date, hit rate**: behind trafilatura 2.2.0; not told apart from newspaper4k 0.9.6 and metascraper 5.58.1.
- **date, right when answering**: ahead of trafilatura 2.2.0, newspaper4k 0.9.6 and metascraper 5.58.1.
- **text, F1**: ahead of newspaper4k 0.9.6, markitdown 0.1.8 and scrapling 0.4.15; not told apart from trafilatura 2.2.0.
- **text, pages kept clean**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0.
- **text, precision**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind trafilatura 2.2.0 and newspaper4k 0.9.6.
- **text, recall**: ahead of newspaper4k 0.9.6; behind markitdown 0.1.8 and scrapling 0.4.15; not told apart from trafilatura 2.2.0.
- **text, word F1**: ahead of newspaper4k 0.9.6, markitdown 0.1.8 and scrapling 0.4.15; not told apart from trafilatura 2.2.0.

With `--visible`'s guesses where the summary is silent, on WCXB's test pages as served:

- **title, hit rate**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0 and metascraper 5.58.1.
- **title, right when answering**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0 and metascraper 5.58.1.
- **author, hit rate**: ahead of newspaper4k 0.9.6; behind trafilatura 2.2.0 and metascraper 5.58.1.
- **author, right when answering**: ahead of trafilatura 2.2.0, newspaper4k 0.9.6 and metascraper 5.58.1.
- **date, hit rate**: ahead of newspaper4k 0.9.6; not told apart from trafilatura 2.2.0 and metascraper 5.58.1.
- **date, right when answering**: ahead of trafilatura 2.2.0, newspaper4k 0.9.6 and metascraper 5.58.1.

On trafilatura's evaluation set:

- **title, hit rate**: ahead of trafilatura 2.2.0, markitdown 0.1.8, scrapling 0.4.15 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.
- **title, right when answering**: ahead of trafilatura 2.2.0, markitdown 0.1.8, scrapling 0.4.15 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.
- **author, hit rate**: behind trafilatura 2.2.0, newspaper4k 0.9.6 and metascraper 5.58.1.
- **author, right when answering**: ahead of newspaper4k 0.9.6 and metascraper 5.58.1; not told apart from trafilatura 2.2.0.
- **date, hit rate**: behind trafilatura 2.2.0, newspaper4k 0.9.6 and metascraper 5.58.1.
- **date, right when answering**: ahead of trafilatura 2.2.0 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.
- **text, F1**: ahead of newspaper4k 0.9.6, markitdown 0.1.8 and scrapling 0.4.15; not told apart from trafilatura 2.2.0.
- **text, pages kept clean**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0.
- **text, precision**: ahead of markitdown 0.1.8 and scrapling 0.4.15; behind newspaper4k 0.9.6; not told apart from trafilatura 2.2.0.
- **text, recall**: ahead of newspaper4k 0.9.6; behind markitdown 0.1.8 and scrapling 0.4.15; not told apart from trafilatura 2.2.0.

With `--visible`'s guesses where the summary is silent, on trafilatura's evaluation set:

- **title, hit rate**: ahead of trafilatura 2.2.0, markitdown 0.1.8, scrapling 0.4.15 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.
- **title, right when answering**: ahead of trafilatura 2.2.0, markitdown 0.1.8, scrapling 0.4.15 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.
- **author, hit rate**: ahead of newspaper4k 0.9.6; behind trafilatura 2.2.0 and metascraper 5.58.1.
- **author, right when answering**: ahead of newspaper4k 0.9.6 and metascraper 5.58.1; not told apart from trafilatura 2.2.0.
- **date, hit rate**: ahead of newspaper4k 0.9.6 and metascraper 5.58.1; behind trafilatura 2.2.0.
- **date, right when answering**: ahead of trafilatura 2.2.0 and metascraper 5.58.1; not told apart from newspaper4k 0.9.6.

## Title, author and date: WCXB's test pages as served

Hit rate, over the pages whose label is not empty:

| tool | title | author | date |
|---|---|---|---|
| sluicer 0.10.0 | 0.708 (0.65–0.76) | 0.698 (0.61–0.78) | 0.780 (0.70–0.84) |
| sluicer 0.10.0, declared then `--visible` | 0.708 (0.65–0.76) | 0.760 (0.67–0.83) | 0.855 (0.79–0.91) |
| trafilatura 2.2.0 | 0.756 (0.70–0.80) | 0.860 (0.79–0.91) | 0.855 (0.79–0.91) |
| newspaper4k 0.9.6 | 0.767 (0.72–0.81) | 0.705 (0.62–0.78) | 0.786 (0.71–0.85) |
| markitdown 0.1.8 | 0.622 (0.57–0.68) | -- | -- |
| scrapling 0.4.15 | 0.622 (0.57–0.68) | -- | -- |
| metascraper 5.58.1 | 0.667 (0.61–0.72) | 0.845 (0.77–0.90) | 0.811 (0.74–0.87) |

Right when answering, over every answer given, inventions included:

| tool | title | author | date |
|---|---|---|---|
| sluicer 0.10.0 | 0.708 (0.65–0.76) | 0.638 (0.55–0.72) | 0.734 (0.66–0.80) |
| sluicer 0.10.0, declared then `--visible` | 0.708 (0.65–0.76) | 0.649 (0.57–0.73) | 0.701 (0.63–0.77) |
| trafilatura 2.2.0 | 0.756 (0.70–0.80) | 0.575 (0.50–0.65) | 0.393 (0.34–0.45) |
| newspaper4k 0.9.6 | 0.767 (0.72–0.81) | 0.569 (0.49–0.65) | 0.658 (0.58–0.73) |
| markitdown 0.1.8 | 0.622 (0.57–0.68) | -- | -- |
| scrapling 0.4.15 | 0.622 (0.57–0.68) | -- | -- |
| metascraper 5.58.1 | 0.667 (0.61–0.72) | 0.482 (0.41–0.55) | 0.573 (0.50–0.64) |

**Silent wrong**: an answer wrong or invented with nothing in the
tool's output to warn of it, over the answers given. The one warning
any of these tools gives is Sluicer's `conflicts`, a question the page
answers two ways that mean different things; those are counted in the
last column and not as silent. A guess of `--visible` carries none.
A title counts wrong by `bench/score.py`'s rule, so a page's longer
title, its site's name added, is wrong where the label is the
heading alone and the shorter is under 0.6 of the longer.

| tool | title | author | date | wrong, with a warning |
|---|---|---|---|---|
| sluicer 0.10.0 | 105 of 360: 0.292 (0.24–0.35) | 51 of 141: 0.362 (0.28–0.45) | 44 of 169: 0.260 (0.20–0.34) | 1 |
| sluicer 0.10.0, declared then `--visible` | 105 of 360: 0.292 (0.24–0.35) | 53 of 151: 0.351 (0.27–0.43) | 57 of 194: 0.294 (0.23–0.37) | 1 |
| trafilatura 2.2.0 | 88 of 360: 0.244 (0.20–0.30) | 82 of 193: 0.425 (0.35–0.50) | 210 of 346: 0.607 (0.55–0.66) | 0 |
| newspaper4k 0.9.6 | 84 of 360: 0.233 (0.19–0.28) | 69 of 160: 0.431 (0.35–0.51) | 65 of 190: 0.342 (0.27–0.42) | 0 |
| markitdown 0.1.8 | 136 of 360: 0.378 (0.32–0.43) | -- | -- | 0 |
| scrapling 0.4.15 | 136 of 360: 0.378 (0.32–0.43) | -- | -- | 0 |
| metascraper 5.58.1 | 120 of 360: 0.333 (0.28–0.39) | 117 of 226: 0.518 (0.45–0.59) | 96 of 225: 0.427 (0.36–0.50) | 0 |

## The main text: WCXB's test pages as served

Every tool's text written as plain text by one rule first, so
markdown is not scored for its syntax. A `with` snippet the text
holds is found; a `without` snippet, the page's menus, footers and
banners, has leaked. Precision, recall and F1 over the summed
snippets, each with a 95% interval bootstrapped over pages. *Pages
kept clean*: no `without` snippet leaked, over the pages that have
one, with its Wilson interval. *Silent empty*: no text and no error,
on a page with main text.

| tool | snippets found | snippets leaked | precision | recall | F1 | pages kept clean | silent empty | raised |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.10.0 | 1139/1457 | 56/1208 | 0.953 (0.93–0.97) | 0.782 (0.75–0.82) | 0.859 (0.83–0.88) | 0.897 (0.86–0.93) | 0 | 0 |
| trafilatura 2.2.0 | 1145/1457 | 54/1208 | 0.955 (0.93–0.97) | 0.786 (0.75–0.82) | 0.862 (0.84–0.89) | 0.900 (0.86–0.93) | 0 | 0 |
| newspaper4k 0.9.6 | 883/1457 | 21/1208 | 0.977 (0.96–0.99) | 0.606 (0.56–0.65) | 0.748 (0.71–0.78) | 0.950 (0.92–0.97) | 10 | 0 |
| markitdown 0.1.8 | 1314/1457 | 1152/1208 | 0.533 (0.52–0.55) | 0.902 (0.88–0.93) | 0.670 (0.65–0.69) | 0.006 (0.00–0.03) | 0 | 0 |
| scrapling 0.4.15 | 1308/1457 | 1103/1208 | 0.543 (0.53–0.56) | 0.898 (0.87–0.92) | 0.676 (0.66–0.69) | 0.017 (0.00–0.04) | 0 | 0 |

| tool | word precision | word recall | word F1 |
|---|---|---|---|
| sluicer 0.10.0 | 0.880 (0.85–0.91) | 0.883 (0.86–0.91) | 0.861 (0.83–0.89) |
| trafilatura 2.2.0 | 0.884 (0.86–0.91) | 0.883 (0.86–0.91) | 0.863 (0.84–0.89) |
| newspaper4k 0.9.6 | 0.889 (0.86–0.92) | 0.687 (0.65–0.73) | 0.732 (0.69–0.77) |
| markitdown 0.1.8 | 0.586 (0.55–0.62) | 0.993 (0.99–1.00) | 0.702 (0.67–0.73) |
| scrapling 0.4.15 | 0.608 (0.58–0.64) | 0.986 (0.97–1.00) | 0.719 (0.69–0.75) |

The word scores are WCXB's own: each text against the page's
whole labelled main text, words counted as a multiset, averaged
over the pages, each with a 95% interval bootstrapped over pages.

## Title, author and date: trafilatura's evaluation set

Hit rate, over the pages whose label is not empty:

| tool | title | author | date |
|---|---|---|---|
| sluicer 0.10.0 | 0.776 (0.74–0.81) | 0.472 (0.43–0.52) | 0.588 (0.55–0.63) |
| sluicer 0.10.0, declared then `--visible` | 0.776 (0.74–0.81) | 0.552 (0.50–0.60) | 0.701 (0.66–0.74) |
| trafilatura 2.2.0 | 0.738 (0.70–0.77) | 0.669 (0.62–0.71) | 0.865 (0.83–0.89) |
| newspaper4k 0.9.6 | 0.756 (0.72–0.79) | 0.507 (0.46–0.55) | 0.668 (0.63–0.71) |
| markitdown 0.1.8 | 0.579 (0.54–0.62) | -- | -- |
| scrapling 0.4.15 | 0.580 (0.54–0.62) | -- | -- |
| metascraper 5.58.1 | 0.699 (0.66–0.73) | 0.662 (0.62–0.71) | 0.663 (0.62–0.70) |

Right when answering, over every answer given, inventions included:

| tool | title | author | date |
|---|---|---|---|
| sluicer 0.10.0 | 0.771 (0.74–0.80) | 0.638 (0.58–0.69) | 0.799 (0.76–0.84) |
| sluicer 0.10.0, declared then `--visible` | 0.771 (0.74–0.80) | 0.657 (0.61–0.70) | 0.806 (0.77–0.84) |
| trafilatura 2.2.0 | 0.733 (0.70–0.77) | 0.647 (0.60–0.69) | 0.743 (0.71–0.78) |
| newspaper4k 0.9.6 | 0.756 (0.72–0.79) | 0.597 (0.55–0.65) | 0.802 (0.76–0.84) |
| markitdown 0.1.8 | 0.575 (0.54–0.61) | -- | -- |
| scrapling 0.4.15 | 0.576 (0.54–0.61) | -- | -- |
| metascraper 5.58.1 | 0.705 (0.67–0.74) | 0.575 (0.53–0.62) | 0.709 (0.67–0.75) |

**Silent wrong**: an answer wrong or invented with nothing in the
tool's output to warn of it, over the answers given. The one warning
any of these tools gives is Sluicer's `conflicts`, a question the page
answers two ways that mean different things; those are counted in the
last column and not as silent. A guess of `--visible` carries none.
A title counts wrong by `bench/score.py`'s rule, so a page's longer
title, its site's name added, is wrong where the label is the
heading alone and the shorter is under 0.6 of the longer.

| tool | title | author | date | wrong, with a warning |
|---|---|---|---|---|
| sluicer 0.10.0 | 195 of 851: 0.229 (0.20–0.26) | 144 of 398: 0.362 (0.31–0.42) | 103 of 536: 0.192 (0.16–0.23) | 5 |
| sluicer 0.10.0, declared then `--visible` | 195 of 851: 0.229 (0.20–0.26) | 155 of 452: 0.343 (0.30–0.39) | 118 of 633: 0.186 (0.15–0.22) | 5 |
| trafilatura 2.2.0 | 227 of 851: 0.267 (0.23–0.30) | 196 of 556: 0.353 (0.31–0.40) | 218 of 848: 0.257 (0.22–0.29) | 0 |
| newspaper4k 0.9.6 | 206 of 845: 0.244 (0.21–0.28) | 184 of 457: 0.403 (0.35–0.45) | 120 of 606: 0.198 (0.16–0.24) | 0 |
| markitdown 0.1.8 | 361 of 850: 0.425 (0.39–0.46) | -- | -- | 0 |
| scrapling 0.4.15 | 360 of 850: 0.424 (0.39–0.46) | -- | -- | 0 |
| metascraper 5.58.1 | 247 of 838: 0.295 (0.26–0.33) | 263 of 619: 0.425 (0.38–0.47) | 198 of 681: 0.291 (0.25–0.33) | 0 |

## The main text: trafilatura's evaluation set

Every tool's text written as plain text by one rule first, so
markdown is not scored for its syntax. A `with` snippet the text
holds is found; a `without` snippet, the page's menus, footers and
banners, has leaked. Precision, recall and F1 over the summed
snippets, each with a 95% interval bootstrapped over pages. *Pages
kept clean*: no `without` snippet leaked, over the pages that have
one, with its Wilson interval. *Silent empty*: no text and no error,
on a page with main text.

| tool | snippets found | snippets leaked | precision | recall | F1 | pages kept clean | silent empty | raised |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.10.0 | 2758/2951 | 323/2966 | 0.895 (0.88–0.91) | 0.935 (0.92–0.95) | 0.914 (0.90–0.93) | 0.756 (0.72–0.79) | 0 | 0 |
| trafilatura 2.2.0 | 2762/2951 | 321/2966 | 0.896 (0.88–0.91) | 0.936 (0.92–0.95) | 0.915 (0.90–0.93) | 0.758 (0.72–0.79) | 0 | 0 |
| newspaper4k 0.9.6 | 2209/2951 | 161/2966 | 0.932 (0.92–0.95) | 0.749 (0.72–0.77) | 0.830 (0.81–0.85) | 0.873 (0.85–0.90) | 51 | 2 |
| markitdown 0.1.8 | 2892/2951 | 2558/2966 | 0.531 (0.52–0.54) | 0.980 (0.97–0.99) | 0.688 (0.68–0.70) | 0.029 (0.02–0.05) | 0 | 0 |
| scrapling 0.4.15 | 2883/2951 | 2532/2966 | 0.532 (0.52–0.54) | 0.977 (0.96–0.99) | 0.689 (0.68–0.70) | 0.037 (0.02–0.06) | 1 | 0 |


## The page added by hand

**<https://typesafe.ai/blog/introducing-system-one-models-and-jev>**, as the Wayback Machine captured it at `20260922123749`. The page that prompted the comparison: a blog post built with Framer, which declares no author or date in markup, shows its date above the title and its author in a byline under it, and writes the time the site was last built in an HTML comment (<!-- Published Sep 22, 2026, 4:54 AM UTC --> in this capture). Labels: title `Introducing System One Models & Jev`, author `Diogo Almeida`, date `2026-09-15`.

| tool | title | author | date | snippets found | snippets leaked |
|---|---|---|---|---|---|
| sluicer 0.10.0 | `Introducing System One Models & Jev - TypeSafe AI Blog` (right, from opengraph og:title) | no answer | no answer | 6 of 6 | 0 of 6 |
| sluicer 0.10.0, declared then `--visible` | `Introducing System One Models & Jev - TypeSafe AI Blog` (right) | no answer | `2026-09-15` (right) | -- | -- |
| trafilatura 2.2.0 | `Introducing System One Models & Jev - TypeSafe AI Blog` (right) | no answer | `2026-09-21` (wrong) | 6 of 6 | 0 of 6 |
| newspaper4k 0.9.6 | `Introducing System One Models & Jev` (right) | no answer | no answer | 5 of 6 | 0 of 6 |
| markitdown 0.1.8 | `Introducing System One Models & Jev - TypeSafe AI Blog` (right) | -- | -- | 6 of 6 | 6 of 6 |
| scrapling 0.4.15 | `Introducing System One Models & Jev - TypeSafe AI Blog` (right) | -- | -- | 5 of 6 | 6 of 6 |
| metascraper 5.58.1 | `Introducing System One Models & Jev - TypeSafe AI Blog` (right) | no answer | no answer | -- | -- |

## Silent wrong answers, by example

The first three of each tool's, per question, in page id order, with
the label and the answer. All of them are in each tool's results.

### WCXB's test pages as served

- **sluicer 0.10.0, title**: 105 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: label `Best Large Exercise Mats and Yoga Mats for Your Home`, answered `Premium Large Exercise Mat`
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `Trekking Backpack 40L / Lightweight & Adventure-Ready`
  - `4035` <https://www.humanscale.com/products/monitor-arms?srsltid=AfmBOorWo4qFWcX0CYcBL2fZWbAhiO3F8Xs2tZ9wE1GKgmLXE_E4u2_W>: label `Monitor Arms`, answered `Humanscale M/Class Monitor Arms – Up to 79% More Weight Capacity`
- **sluicer 0.10.0, author**: 51 silent wrong answers; the first by id:
  - `4060` <https://www.uclahealth.org/news/article/the-link-between-exercise-and-mental-health>: no label, answered `uclahealth`
  - `4108` <https://www.thegoodtrade.com/features/plus-size-ethical-fashion/>: no label, answered `Our Editors`
  - `4168` <https://www.lttlabs.com/products/keyboards/keychron-k2-wireless-mechanical-keyboard-version-2>: no label, answered `Labs Web Team`
- **sluicer 0.10.0, date**: 44 silent wrong answers; the first by id:
  - `4048` <https://www.consumerreports.org/cars/hybrids-evs/buying-guide/>: label `2026-03-11`, answered `240221`
  - `4052` <https://www.topgear.com/car-news/electric/top-gears-top-20-electric-cars>: label `2026-03-11`, answered `2025-10-15T05:00:00+01:00`
  - `4219` <https://www.samsung.com/levant/tablets/galaxy-tab-s/galaxy-tab-s9-fe-wifi-gray-128gb-sm-x510nzaamea/>: no label, answered `2023-11-02`
- **sluicer 0.10.0, declared then `--visible`, title**: 105 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: label `Best Large Exercise Mats and Yoga Mats for Your Home`, answered `Premium Large Exercise Mat`
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `Trekking Backpack 40L / Lightweight & Adventure-Ready`
  - `4035` <https://www.humanscale.com/products/monitor-arms?srsltid=AfmBOorWo4qFWcX0CYcBL2fZWbAhiO3F8Xs2tZ9wE1GKgmLXE_E4u2_W>: label `Monitor Arms`, answered `Humanscale M/Class Monitor Arms – Up to 79% More Weight Capacity`
- **sluicer 0.10.0, declared then `--visible`, author**: 53 silent wrong answers; the first by id:
  - `4060` <https://www.uclahealth.org/news/article/the-link-between-exercise-and-mental-health>: no label, answered `uclahealth`
  - `4108` <https://www.thegoodtrade.com/features/plus-size-ethical-fashion/>: no label, answered `Our Editors`
  - `4168` <https://www.lttlabs.com/products/keyboards/keychron-k2-wireless-mechanical-keyboard-version-2>: no label, answered `Labs Web Team`
- **sluicer 0.10.0, declared then `--visible`, date**: 57 silent wrong answers; the first by id:
  - `4048` <https://www.consumerreports.org/cars/hybrids-evs/buying-guide/>: label `2026-03-11`, answered `240221`
  - `4052` <https://www.topgear.com/car-news/electric/top-gears-top-20-electric-cars>: label `2026-03-11`, answered `2025-10-15T05:00:00+01:00`
  - `4219` <https://www.samsung.com/levant/tablets/galaxy-tab-s/galaxy-tab-s9-fe-wifi-gray-128gb-sm-x510nzaamea/>: no label, answered `2023-11-02`
- **trafilatura 2.2.0, title**: 88 silent wrong answers; the first by id:
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `Trekking Backpack 40L / Lightweight & Adventure-Ready`
  - `4035` <https://www.humanscale.com/products/monitor-arms?srsltid=AfmBOorWo4qFWcX0CYcBL2fZWbAhiO3F8Xs2tZ9wE1GKgmLXE_E4u2_W>: label `Monitor Arms`, answered `Humanscale M/Class Monitor Arms – Up to 79% More Weight Capacity`
  - `4044` <https://www.charlestoncoffeeroasters.com/brief-history-of-coffee/?srsltid=AfmBOopF3oGqvNbKG9KDw1o2zDRDW1jSLz1cvhbHYCO2T_moZvzQCJZ3>: label `Brief History of Coffee`, answered `Brief History of Coffee - Charleston Coffee Roasters`
- **trafilatura 2.2.0, author**: 82 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: no label, answered `Yo Gorilla Mats`
  - `4051` <https://podenergy.com/guides/your-guide-to-choosing-an-ev?srsltid=AfmBOorhfDqMziMKLsdyLLwLRD7ZS7HLaoeMqOEftExeFDPLuXI5zKtv>: no label, answered `Admin`
  - `4052` <https://www.topgear.com/car-news/electric/top-gears-top-20-electric-cars>: no label, answered `TopGear com Published`
- **trafilatura 2.2.0, date**: 210 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: no label, answered `2026-02-03`
  - `4024` <https://maelstromdirect.com/products/maelstrom-hiking-backpack-40l>: no label, answered `2026-01-01`
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: no label, answered `2026-02-09`
- **newspaper4k 0.9.6, title**: 84 silent wrong answers; the first by id:
  - `4016` <https://www.brettlarkin.com/best-non-slip-yoga-mat/>: label `What Is The Ultimate Best Non-Slip Yoga Mat? Here Are My Top 3 Picks`, answered `Slip Yoga Mat? Here Are My Top 3 Picks – Brett Larkin Yoga`
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `Trekking Backpack 40L / Lightweight & Adventure-Ready`
  - `4029` <https://lafeeca.com/products/dj-electric-kettle?srsltid=AfmBOor2wDNsS-upWLtRMj-ijC0iojbHlKyuTjUBX5CRujAK25gUxQx4>: label `Pour Over Electric Kettle`, answered `Lafeeca DJ Kettle – Stainless Steel Gooseneck Electric Kettle`
- **newspaper4k 0.9.6, author**: 69 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: no label, answered `Yo Gorilla Mats`
  - `4016` <https://www.brettlarkin.com/best-non-slip-yoga-mat/>: label `Brett Larkin`, answered `Brett, Yoga Life, Healing With Somatic Yoga`
  - `4048` <https://www.consumerreports.org/cars/hybrids-evs/buying-guide/>: label `Keith Barry`, answered `Consumer Reports`
- **newspaper4k 0.9.6, date**: 65 silent wrong answers; the first by id:
  - `4048` <https://www.consumerreports.org/cars/hybrids-evs/buying-guide/>: label `2026-03-11`, answered `2021-02-24T00:00:00`
  - `4052` <https://www.topgear.com/car-news/electric/top-gears-top-20-electric-cars>: label `2026-03-11`, answered `2025-10-15T05:00:00+01:00`
  - `4098` <https://prismfitnessgroup.com/product/selfguided-roller/?srsltid=AfmBOornXIQqVZ6xvTB-CK6sNBe0t1PCNx4eRPPEpk2gCZlUcXc05Qjb>: no label, answered `2015-07-09T08:09:04+00:00`
- **markitdown 0.1.8, title**: 136 silent wrong answers; the first by id:
  - `4011` <https://www.nytimes.com/wirecutter/reviews/best-laptop-under-500/>: label `The Best Cheap Laptops Under $500`, answered `The Best Cheap Laptops Under $500 for 2026 / Reviews by Wirecutter`
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `40L Trekking Backpack – Lightweight & Built for Adventure / Hike Summit`
  - `4028` <https://www.publichealth.columbia.edu/news/how-climate-change-stressing-global-food-supply-public-health>: label `How Climate Change Is Stressing the Global Food Supply and Public Health`, answered `How Climate Change Is Stressing the Global Food Supply and Public Health / Columbia Univer...`
- **scrapling 0.4.15, title**: 136 silent wrong answers; the first by id:
  - `4011` <https://www.nytimes.com/wirecutter/reviews/best-laptop-under-500/>: label `The Best Cheap Laptops Under $500`, answered `The Best Cheap Laptops Under $500 for 2026 / Reviews by Wirecutter`
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `40L Trekking Backpack – Lightweight & Built for Adventure / Hike Summit`
  - `4028` <https://www.publichealth.columbia.edu/news/how-climate-change-stressing-global-food-supply-public-health>: label `How Climate Change Is Stressing the Global Food Supply and Public Health`, answered `How Climate Change Is Stressing the Global Food Supply and Public Health / Columbia Univer...`
- **metascraper 5.58.1, title**: 120 silent wrong answers; the first by id:
  - `4026` <https://hike-summit.com/trekking-backpack-40l-lightweight-adventure-ready/>: label `Trekking Backpack 40L`, answered `Trekking Backpack 40L / Lightweight & Adventure-Ready`
  - `4035` <https://www.humanscale.com/products/monitor-arms?srsltid=AfmBOorWo4qFWcX0CYcBL2fZWbAhiO3F8Xs2tZ9wE1GKgmLXE_E4u2_W>: label `Monitor Arms`, answered `Humanscale M/Class Monitor Arms – Up to 79% More Weight Capacity`
  - `4044` <https://www.charlestoncoffeeroasters.com/brief-history-of-coffee/?srsltid=AfmBOopF3oGqvNbKG9KDw1o2zDRDW1jSLz1cvhbHYCO2T_moZvzQCJZ3>: label `Brief History of Coffee`, answered `Brief History of Coffee - Charleston Coffee Roasters`
- **metascraper 5.58.1, author**: 117 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: no label, answered `Yo Gorilla Mats`
  - `4024` <https://maelstromdirect.com/products/maelstrom-hiking-backpack-40l>: no label, answered `Maelstrom`
  - `4048` <https://www.consumerreports.org/cars/hybrids-evs/buying-guide/>: label `Keith Barry`, answered `Consumer Reports`
- **metascraper 5.58.1, date**: 96 silent wrong answers; the first by id:
  - `4015` <https://yogorillamats.com/?srsltid=AfmBOorSzHjzn508MwUjLZs-9yNjZot3FdDZcgVRWmaGV6mWrDCI82jI>: no label, answered `2026-03-02T10:00:00.000Z`
  - `4048` <https://www.consumerreports.org/cars/hybrids-evs/buying-guide/>: label `2026-03-11`, answered `2025-05-23T09:00:00.000Z`
  - `4052` <https://www.topgear.com/car-news/electric/top-gears-top-20-electric-cars>: label `2026-03-11`, answered `2025-10-15T04:00:00.000Z`

### Trafilatura's evaluation set

- **sluicer 0.10.0, title**: 195 silent wrong answers; the first by id:
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis-Tickets`
  - `0b4609a864eb4fa0bbcb2b395f6be9eb.html` <https://www.ardmediathek.de/swr/player/Y3JpZDovL3N3ci5kZS9hZXgvbzExNjIyMjY/nahrungsergaenzungsmittel-das-dubiose-geschaeft-mit-der-hoffnung>: label `betrifft: ...: Nahrungsergänzungsmittel - Das dubiose Geschäft mit der Hoffnung / Video de...`, answered `Nahrungsergänzungsmittel - Das dubiose Geschäft mit der Hoffnung / Video`
  - `24ora.com-internationalschol.html` <https://24ora.com/minister-president-presente-ne-trashion-fashion-show-di-international-school/>: label `MINISTER-PRESIDENT PRESENTE N’E “TRASHION FASHION SHOW” DI INTERNATIONAL SCHOOL`, answered `Minister-president presente n'e “Trashion Fashion Show” di International School - 24ora.co...`
- **sluicer 0.10.0, author**: 144 silent wrong answers; the first by id:
  - `0a6291ebbce449b3b04256b43c73e39d.html` <https://wien.orf.at/stories/3017954/>: label `red, wien.ORF.at/Agenturen`, answered `ORF.at`
  - `24ora.com-internationalschol.html` <https://24ora.com/minister-president-presente-ne-trashion-fashion-show-di-international-school/>: no label, answered `Tango`
  - `Lebensmittelpraxis.de-Stadtzentrum.html` <https://lebensmittelpraxis.de/handel-aktuell/38519-olympische-spiele-in-paris-getraenke-per-schiff-ins-stadtzentrum.html>: no label, answered `Lebensmittel Praxis`
- **sluicer 0.10.0, date**: 103 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `2019-10-16`, answered `2019-10-19T19:08:22+02:00`
  - `0b96fc66e2c94f45a1b923ec9a31fcf2.html` <https://www.nachrichten.at/meine-welt/gesundheit/was-bringen-alternative-therapien-bei-krebs;art114,3177663>: label `2019-10-19`, answered `2019-10-18T22:04:00Z`
  - `24ora.com-internationalschol.html` <https://24ora.com/minister-president-presente-ne-trashion-fashion-show-di-international-school/>: label `2022-05-03`, answered `2022-05-04T03:37:37+00:00`
- **sluicer 0.10.0, declared then `--visible`, title**: 195 silent wrong answers; the first by id:
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis-Tickets`
  - `0b4609a864eb4fa0bbcb2b395f6be9eb.html` <https://www.ardmediathek.de/swr/player/Y3JpZDovL3N3ci5kZS9hZXgvbzExNjIyMjY/nahrungsergaenzungsmittel-das-dubiose-geschaeft-mit-der-hoffnung>: label `betrifft: ...: Nahrungsergänzungsmittel - Das dubiose Geschäft mit der Hoffnung / Video de...`, answered `Nahrungsergänzungsmittel - Das dubiose Geschäft mit der Hoffnung / Video`
  - `24ora.com-internationalschol.html` <https://24ora.com/minister-president-presente-ne-trashion-fashion-show-di-international-school/>: label `MINISTER-PRESIDENT PRESENTE N’E “TRASHION FASHION SHOW” DI INTERNATIONAL SCHOOL`, answered `Minister-president presente n'e “Trashion Fashion Show” di International School - 24ora.co...`
- **sluicer 0.10.0, declared then `--visible`, author**: 155 silent wrong answers; the first by id:
  - `0a6291ebbce449b3b04256b43c73e39d.html` <https://wien.orf.at/stories/3017954/>: label `red, wien.ORF.at/Agenturen`, answered `ORF.at`
  - `24ora.com-internationalschol.html` <https://24ora.com/minister-president-presente-ne-trashion-fashion-show-di-international-school/>: no label, answered `Tango`
  - `Lebensmittelpraxis.de-Stadtzentrum.html` <https://lebensmittelpraxis.de/handel-aktuell/38519-olympische-spiele-in-paris-getraenke-per-schiff-ins-stadtzentrum.html>: no label, answered `Lebensmittel Praxis`
- **sluicer 0.10.0, declared then `--visible`, date**: 118 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `2019-10-16`, answered `2019-10-19T19:08:22+02:00`
  - `0b96fc66e2c94f45a1b923ec9a31fcf2.html` <https://www.nachrichten.at/meine-welt/gesundheit/was-bringen-alternative-therapien-bei-krebs;art114,3177663>: label `2019-10-19`, answered `2019-10-18T22:04:00Z`
  - `24ora.com-internationalschol.html` <https://24ora.com/minister-president-presente-ne-trashion-fashion-show-di-international-school/>: label `2022-05-03`, answered `2022-05-04T03:37:37+00:00`
- **trafilatura 2.2.0, title**: 227 silent wrong answers; the first by id:
  - `0a24692a9ea846c1819bd6a5f92a8874.html` <https://www.watson.ch/leben/drinks/453207266-sazerac-alles-ueber-den-cocktail-klassiker-aus-new-orleans>: label `Sazerac - alles über den Cocktail-Klassiker aus New Orleans`, answered `Sazerac! Alles über den Cocktail-Klassiker aus New Orleans`
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis-Tickets`
  - `0af99c85f22b451a93a75bbf99ac412e.html` <https://www.mz-web.de/dessau-rosslau/hingucker-beim-flugplatzfest-zweite-f13-kurz-vor-der-zulassung-33328852>: label `Hingucker beim Flugplatzfest in Dessau: Zweite F13 kurz vor der Zulassung`, answered `Hingucker beim Flugplatzfest: Zweite F13 kurz vor der Zulassung`
- **trafilatura 2.2.0, author**: 196 silent wrong answers; the first by id:
  - `0ac0531f1f0543f4a3f68159e5fd1875.html` <https://www.dealdoktor.de/user-deals/deals/gutscheine-deals/jacobs-gold-instant-kaffee-2-glaeser-fuer-480-e/>: label `MikeNils`, answered `D-Zug`
  - `0b66696af800472190a76b26faa845d4.html` <https://jungefreiheit.de/debatte/kommentar/2019/kaisers-royaler-wochenrueckblick-31/>: label `Boris T. Kaiser`, answered `Jungefreiheit De`
  - `1hundetagebuch.wordpress.com.langer.html` <https://1hundetagebuch.wordpress.com/2019/10/31/nach-viel-zu-langer-zeit-mal-wieder/>: label `Donald Townsend`, answered `DT`
- **trafilatura 2.2.0, date**: 218 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `2019-10-16`, answered `2019-10-19`
  - `0a29620f9c4347758c146ed06dab6f3e.html` <https://www.tagblatt.ch/kultur/mit-allen-wassern-gewaschen-ld.1161246>: label `2019-10-19`, answered `2019-10-18`
  - `1337kultur.de.picard.html` <https://1337kultur.de/2020/folge-70-star-trek-picard/>: no label, answered `2020-02-25`
- **newspaper4k 0.9.6, title**: 206 silent wrong answers; the first by id:
  - `0a24692a9ea846c1819bd6a5f92a8874.html` <https://www.watson.ch/leben/drinks/453207266-sazerac-alles-ueber-den-cocktail-klassiker-aus-new-orleans>: label `Sazerac - alles über den Cocktail-Klassiker aus New Orleans`, answered `Klassiker aus New Orleans`
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis`
  - `0b4609a864eb4fa0bbcb2b395f6be9eb.html` <https://www.ardmediathek.de/swr/player/Y3JpZDovL3N3ci5kZS9hZXgvbzExNjIyMjY/nahrungsergaenzungsmittel-das-dubiose-geschaeft-mit-der-hoffnung>: label `betrifft: ...: Nahrungsergänzungsmittel - Das dubiose Geschäft mit der Hoffnung / Video de...`, answered `Nahrungsergänzungsmittel - Das dubiose Geschäft mit der Hoffnung`
- **newspaper4k 0.9.6, author**: 184 silent wrong answers; the first by id:
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `David`, answered `www.facebook.com`
  - `0b66696af800472190a76b26faa845d4.html` <https://jungefreiheit.de/debatte/kommentar/2019/kaisers-royaler-wochenrueckblick-31/>: label `Boris T. Kaiser`, answered `jungefreiheit.de`
  - `24horas.cl-segundo.html` <https://www.24horas.cl/politica/presidente-boric-inicia-gira-por-magallanes-este-miercoles-5287894>: label `Agencia EFE`, answered `24horas.cl, www.facebook.com`
- **newspaper4k 0.9.6, date**: 120 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `2019-10-16`, answered `2019-10-19T19:08:22+02:00`
  - `0b96fc66e2c94f45a1b923ec9a31fcf2.html` <https://www.nachrichten.at/meine-welt/gesundheit/was-bringen-alternative-therapien-bei-krebs;art114,3177663>: label `2019-10-19`, answered `2019-10-18T22:04:00+00:00`
  - `1337kultur.de.picard.html` <https://1337kultur.de/2020/folge-70-star-trek-picard/>: no label, answered `2020-02-25T13:02:01+01:00`
- **markitdown 0.1.8, title**: 361 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `Bohren, bis es heiß wird`, answered `Klimaschutz: Bohren, bis es heiß wird / ZEIT ONLINE`
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis-Tickets`
  - `0a6291ebbce449b3b04256b43c73e39d.html` <https://wien.orf.at/stories/3017954/>: label `Lotte Tobisch ist tot`, answered `Chronik: Lotte Tobisch ist tot - wien.ORF.at`
- **scrapling 0.4.15, title**: 360 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `Bohren, bis es heiß wird`, answered `Klimaschutz: Bohren, bis es heiß wird / ZEIT ONLINE`
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis-Tickets`
  - `0a6291ebbce449b3b04256b43c73e39d.html` <https://wien.orf.at/stories/3017954/>: label `Lotte Tobisch ist tot`, answered `Chronik: Lotte Tobisch ist tot - wien.ORF.at`
- **metascraper 5.58.1, title**: 247 silent wrong answers; the first by id:
  - `0a24692a9ea846c1819bd6a5f92a8874.html` <https://www.watson.ch/leben/drinks/453207266-sazerac-alles-ueber-den-cocktail-klassiker-aus-new-orleans>: label `Sazerac - alles über den Cocktail-Klassiker aus New Orleans`, answered `Sazerac! Alles über den Cocktail-Klassiker aus New Orleans`
  - `0a4a8ab61c054192b1ec70cc3570cf45.html` <https://www.zugreiseblog.de/db-lounge-zutritt-sparpreis/>: label `DB Lounge: Kein Zugang mehr mit Sparpreis-Ticket`, answered `DB Lounge: Kein Zutritt mehr mit Sparpreis-Tickets`
  - `0af99c85f22b451a93a75bbf99ac412e.html` <https://www.mz-web.de/dessau-rosslau/hingucker-beim-flugplatzfest-zweite-f13-kurz-vor-der-zulassung-33328852>: label `Hingucker beim Flugplatzfest in Dessau: Zweite F13 kurz vor der Zulassung`, answered `Hingucker beim Flugplatzfest: Zweite F13 kurz vor der Zulassung`
- **metascraper 5.58.1, author**: 263 silent wrong answers; the first by id:
  - `0ac0531f1f0543f4a3f68159e5fd1875.html` <https://www.dealdoktor.de/user-deals/deals/gutscheine-deals/jacobs-gold-instant-kaffee-2-glaeser-fuer-480-e/>: label `MikeNils`, answered `Montana`
  - `0b66696af800472190a76b26faa845d4.html` <https://jungefreiheit.de/debatte/kommentar/2019/kaisers-royaler-wochenrueckblick-31/>: label `Boris T. Kaiser`, answered `19. Oktober 2019 um 14:37 Uhr`
  - `1337kultur.de.picard.html` <https://1337kultur.de/2020/folge-70-star-trek-picard/>: no label, answered `Harm Otten sagt:`
- **metascraper 5.58.1, date**: 198 silent wrong answers; the first by id:
  - `0a12df42d1764095989ab078ee0f940b.html` <https://www.zeit.de/2019/43/klimaschutz-banken-unternehmen-fracking-oelfoerderung-fossile-brennstoffe>: label `2019-10-16`, answered `2019-10-19T17:08:22.000Z`
  - `0b66696af800472190a76b26faa845d4.html` <https://jungefreiheit.de/debatte/kommentar/2019/kaisers-royaler-wochenrueckblick-31/>: label `2019-10-19`, answered `2026-09-26T11:37:00.000Z`
  - `0b96fc66e2c94f45a1b923ec9a31fcf2.html` <https://www.nachrichten.at/meine-welt/gesundheit/was-bringen-alternative-therapien-bei-krebs;art114,3177663>: label `2019-10-19`, answered `2019-10-18T22:04:00.000Z`

## Speed and install

| tool | install line |
|---|---|
| sluicer | `pip install "sluicer[markdown]"` |
| trafilatura | `pip install trafilatura==2.2.0` |
| newspaper4k | `pip install newspaper4k==0.9.6` |
| markitdown | `pip install markitdown==0.1.8` |
| scrapling | `pip install "scrapling[rag]==0.4.15"` |
| metascraper | `npm install metascraper@5.58.1 metascraper-title@5.56.2 metascraper-author@5.56.2 metascraper-date@5.56.2` |

Seconds per page are for everything the tool is asked here, on the
360 pages as served; Sluicer's `--visible` is not timed.

Measured on 2026-09-26 by `uv run bench/timing.py tools` at commit `5e97f6b`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 360 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.10.0 | Python 3.12.13 | 0.0246 | 8.85 (8.82–8.86) | 41 | 241.0 MiB | 58.7 MiB | 21 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0567 | 20.41 (20.36–20.51) | 18 | 287.1 MiB | 58.2 MiB | 17 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0641 | 23.07 (22.87–23.13) | 16 | 333.3 MiB | 39.4 MiB | 22 |
| markitdown 0.1.8 | Python 3.12.13 | 0.0267 | 9.60 (9.52–10.12) | 37 | 223.1 MiB | 129.3 MiB | 20 |
| scrapling 0.4.15 | Python 3.12.13 | 0.0201 | 7.23 (7.17–7.27) | 50 | 352.1 MiB | 296.8 MiB | 26 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0077 | 2.79 (2.77–2.83) | 129 | 990.3 MiB | 55.5 MiB | 125 |

## How sure, and what differs

Sluicer, and Sluicer declared then `--visible`, against each other
tool, on every rate both answer, paired by page.

### WCXB's test pages as served

| side | against | question | rate | difference (95% interval) | verdict |
|---|---|---|---|---|---|
| sluicer 0.10.0 | trafilatura 2.2.0 | title | hit rate | -0.047 (-0.095 to +0.003) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | title | right when answering | -0.047 (-0.095 to +0.003) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | author | hit rate | -0.163 (-0.232 to -0.097) | worse |
| sluicer 0.10.0 | trafilatura 2.2.0 | author | right when answering | +0.063 (+0.008 to +0.119) | better |
| sluicer 0.10.0 | trafilatura 2.2.0 | date | hit rate | -0.075 (-0.140 to -0.012) | worse |
| sluicer 0.10.0 | trafilatura 2.2.0 | date | right when answering | +0.341 (+0.283 to +0.399) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | title | hit rate | -0.058 (-0.109 to -0.008) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | title | right when answering | -0.058 (-0.109 to -0.008) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | author | hit rate | -0.008 (-0.050 to +0.033) | inconclusive |
| sluicer 0.10.0 | newspaper4k 0.9.6 | author | right when answering | +0.070 (+0.026 to +0.116) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | date | hit rate | -0.006 (-0.040 to +0.026) | inconclusive |
| sluicer 0.10.0 | newspaper4k 0.9.6 | date | right when answering | +0.076 (+0.039 to +0.116) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | title | hit rate | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | title | right when answering | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | title | hit rate | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | title | right when answering | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0 | metascraper 5.58.1 | title | hit rate | +0.042 (0.000 to +0.084) | inconclusive |
| sluicer 0.10.0 | metascraper 5.58.1 | title | right when answering | +0.042 (0.000 to +0.084) | inconclusive |
| sluicer 0.10.0 | metascraper 5.58.1 | author | hit rate | -0.147 (-0.221 to -0.076) | worse |
| sluicer 0.10.0 | metascraper 5.58.1 | author | right when answering | +0.156 (+0.103 to +0.213) | better |
| sluicer 0.10.0 | metascraper 5.58.1 | date | hit rate | -0.031 (-0.080 to +0.014) | inconclusive |
| sluicer 0.10.0 | metascraper 5.58.1 | date | right when answering | +0.160 (+0.113 to +0.211) | better |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | title | hit rate | -0.047 (-0.095 to +0.003) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | title | right when answering | -0.047 (-0.095 to +0.003) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | author | hit rate | -0.101 (-0.163 to -0.042) | worse |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | author | right when answering | +0.074 (+0.022 to +0.126) | better |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | date | hit rate | 0.000 (-0.060 to +0.062) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | date | right when answering | +0.308 (+0.256 to +0.362) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | title | hit rate | -0.058 (-0.109 to -0.008) | worse |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | title | right when answering | -0.058 (-0.109 to -0.008) | worse |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | author | hit rate | +0.054 (+0.013 to +0.102) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | author | right when answering | +0.080 (+0.036 to +0.127) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | date | hit rate | +0.069 (+0.028 to +0.114) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | date | right when answering | +0.043 (+0.011 to +0.077) | better |
| sluicer 0.10.0, declared then `--visible` | markitdown 0.1.8 | title | hit rate | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0, declared then `--visible` | markitdown 0.1.8 | title | right when answering | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0, declared then `--visible` | scrapling 0.4.15 | title | hit rate | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0, declared then `--visible` | scrapling 0.4.15 | title | right when answering | +0.086 (+0.036 to +0.137) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | title | hit rate | +0.042 (0.000 to +0.084) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | title | right when answering | +0.042 (0.000 to +0.084) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | author | hit rate | -0.085 (-0.153 to -0.016) | worse |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | author | right when answering | +0.167 (+0.117 to +0.223) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | date | hit rate | +0.044 (-0.013 to +0.100) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | date | right when answering | +0.128 (+0.083 to +0.175) | better |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | precision | -0.002 (-0.005 to -0.00004) | worse |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | recall | -0.004 (-0.012 to +0.003) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | F1 | -0.003 (-0.009 to +0.001) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | pages kept clean | -0.003 (-0.009 to 0.000) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | word F1 | -0.002 (-0.006 to +0.001) | inconclusive |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | precision | -0.024 (-0.040 to -0.009) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | recall | +0.176 (+0.140 to +0.213) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | F1 | +0.111 (+0.084 to +0.140) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | pages kept clean | -0.053 (-0.087 to -0.022) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | word F1 | +0.130 (+0.102 to +0.158) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | text | precision | +0.420 (+0.402 to +0.438) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | text | recall | -0.120 (-0.146 to -0.095) | worse |
| sluicer 0.10.0 | markitdown 0.1.8 | text | F1 | +0.189 (+0.170 to +0.207) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | text | pages kept clean | +0.891 (+0.858 to +0.923) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | text | word F1 | +0.160 (+0.140 to +0.180) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | precision | +0.411 (+0.392 to +0.429) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | recall | -0.116 (-0.143 to -0.090) | worse |
| sluicer 0.10.0 | scrapling 0.4.15 | text | F1 | +0.183 (+0.163 to +0.201) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | pages kept clean | +0.880 (+0.845 to +0.912) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | word F1 | +0.143 (+0.123 to +0.163) | better |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
64 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

### Trafilatura's evaluation set

| side | against | question | rate | difference (95% interval) | verdict |
|---|---|---|---|---|---|
| sluicer 0.10.0 | trafilatura 2.2.0 | title | hit rate | +0.038 (+0.012 to +0.064) | better |
| sluicer 0.10.0 | trafilatura 2.2.0 | title | right when answering | +0.038 (+0.012 to +0.064) | better |
| sluicer 0.10.0 | trafilatura 2.2.0 | author | hit rate | -0.197 (-0.235 to -0.159) | worse |
| sluicer 0.10.0 | trafilatura 2.2.0 | author | right when answering | -0.009 (-0.041 to +0.024) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | date | hit rate | -0.277 (-0.312 to -0.244) | worse |
| sluicer 0.10.0 | trafilatura 2.2.0 | date | right when answering | +0.056 (+0.025 to +0.085) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | title | hit rate | +0.020 (-0.008 to +0.048) | inconclusive |
| sluicer 0.10.0 | newspaper4k 0.9.6 | title | right when answering | +0.015 (-0.012 to +0.041) | inconclusive |
| sluicer 0.10.0 | newspaper4k 0.9.6 | author | hit rate | -0.035 (-0.069 to -0.003) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | author | right when answering | +0.041 (+0.004 to +0.078) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | date | hit rate | -0.080 (-0.105 to -0.055) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | date | right when answering | -0.003 (-0.025 to +0.017) | inconclusive |
| sluicer 0.10.0 | markitdown 0.1.8 | title | hit rate | +0.198 (+0.168 to +0.228) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | title | right when answering | +0.196 (+0.166 to +0.226) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | title | hit rate | +0.196 (+0.167 to +0.227) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | title | right when answering | +0.194 (+0.165 to +0.225) | better |
| sluicer 0.10.0 | metascraper 5.58.1 | title | hit rate | +0.077 (+0.053 to +0.102) | better |
| sluicer 0.10.0 | metascraper 5.58.1 | title | right when answering | +0.066 (+0.042 to +0.090) | better |
| sluicer 0.10.0 | metascraper 5.58.1 | author | hit rate | -0.190 (-0.229 to -0.150) | worse |
| sluicer 0.10.0 | metascraper 5.58.1 | author | right when answering | +0.063 (+0.026 to +0.099) | better |
| sluicer 0.10.0 | metascraper 5.58.1 | date | hit rate | -0.076 (-0.103 to -0.048) | worse |
| sluicer 0.10.0 | metascraper 5.58.1 | date | right when answering | +0.089 (+0.062 to +0.117) | better |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | title | hit rate | +0.038 (+0.012 to +0.064) | better |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | title | right when answering | +0.038 (+0.012 to +0.064) | better |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | author | hit rate | -0.117 (-0.155 to -0.079) | worse |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | author | right when answering | +0.010 (-0.021 to +0.041) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | date | hit rate | -0.165 (-0.196 to -0.135) | worse |
| sluicer 0.10.0, declared then `--visible` | trafilatura 2.2.0 | date | right when answering | +0.063 (+0.035 to +0.090) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | title | hit rate | +0.020 (-0.008 to +0.048) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | title | right when answering | +0.015 (-0.012 to +0.041) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | author | hit rate | +0.045 (+0.010 to +0.079) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | author | right when answering | +0.060 (+0.023 to +0.096) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | date | hit rate | +0.033 (+0.008 to +0.058) | better |
| sluicer 0.10.0, declared then `--visible` | newspaper4k 0.9.6 | date | right when answering | +0.004 (-0.017 to +0.024) | inconclusive |
| sluicer 0.10.0, declared then `--visible` | markitdown 0.1.8 | title | hit rate | +0.198 (+0.168 to +0.228) | better |
| sluicer 0.10.0, declared then `--visible` | markitdown 0.1.8 | title | right when answering | +0.196 (+0.166 to +0.226) | better |
| sluicer 0.10.0, declared then `--visible` | scrapling 0.4.15 | title | hit rate | +0.196 (+0.167 to +0.227) | better |
| sluicer 0.10.0, declared then `--visible` | scrapling 0.4.15 | title | right when answering | +0.194 (+0.165 to +0.225) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | title | hit rate | +0.077 (+0.053 to +0.102) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | title | right when answering | +0.066 (+0.042 to +0.090) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | author | hit rate | -0.110 (-0.147 to -0.071) | worse |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | author | right when answering | +0.082 (+0.048 to +0.116) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | date | hit rate | +0.037 (+0.008 to +0.067) | better |
| sluicer 0.10.0, declared then `--visible` | metascraper 5.58.1 | date | right when answering | +0.096 (+0.068 to +0.124) | better |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | precision | -0.001 (-0.003 to +0.002) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | recall | -0.001 (-0.006 to +0.003) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | F1 | -0.001 (-0.004 to +0.002) | inconclusive |
| sluicer 0.10.0 | trafilatura 2.2.0 | text | pages kept clean | -0.002 (-0.009 to +0.004) | inconclusive |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | precision | -0.037 (-0.048 to -0.026) | worse |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | recall | +0.186 (+0.165 to +0.208) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | F1 | +0.084 (+0.070 to +0.099) | better |
| sluicer 0.10.0 | newspaper4k 0.9.6 | text | pages kept clean | -0.117 (-0.142 to -0.092) | worse |
| sluicer 0.10.0 | markitdown 0.1.8 | text | precision | +0.365 (+0.352 to +0.377) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | text | recall | -0.045 (-0.057 to -0.034) | worse |
| sluicer 0.10.0 | markitdown 0.1.8 | text | F1 | +0.226 (+0.217 to +0.235) | better |
| sluicer 0.10.0 | markitdown 0.1.8 | text | pages kept clean | +0.726 (+0.698 to +0.754) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | precision | +0.363 (+0.350 to +0.375) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | recall | -0.042 (-0.055 to -0.030) | worse |
| sluicer 0.10.0 | scrapling 0.4.15 | text | F1 | +0.225 (+0.216 to +0.234) | better |
| sluicer 0.10.0 | scrapling 0.4.15 | text | pages kept clean | +0.718 (+0.689 to +0.746) | better |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
60 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## Method

- **Title, author, date**: `bench/score.py`, as on every scoreboard.
- **Sluicer**: `extract(html, url=...).summary`'s `title`, `author`,
  `published`, and `sluicer.markdown.to_markdown(html, url=...)`; with
  `--visible`, the guess of `extract(..., visible=True)` where the summary
  has no answer.
- **trafilatura**: `extract_metadata(html, default_url=...)` and
  `extract(html, url=..., output_format="markdown")`.
- **newspaper4k**: `download(input_html=...)` and `parse()`, network taken
  away and images off; its text is plain text.
- **markitdown**: `MarkItDown().convert_stream(...)` of the bytes, told
  they are HTML from the page's address: `.title` and `.markdown`.
- **Scrapling**: `Response(...).markdown(main_content_only=True)`, as its
  site-to-markdown spider asks it, and `<title>`'s text; given the page
  decoded as html-to-markdown is given it, since its fetchers pass the
  charset the server sent.
- **metascraper**: its `title`, `author` and `date` rules, as on the other
  scoreboards.
- **Environments**: Python 3.12, each tool pinned with its
  dependencies in `bench/requirements/` or `bench/metascraper/`.
