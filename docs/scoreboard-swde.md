# Scoreboard, extractors learnt from examples

What `sluicer compile --want` promises, measured: point at a value on a
few pages of one template, and read it on every other page of that
template. The pages are [SWDE](https://github.com/woailaosang/swde), the
Structured Web Data Extraction dataset (Hao, Cai, Pang and Zhang, SIGIR
2011): 124,291 detail pages from 80 sites in 8
verticals, crawled around 2010, each labelled with the values of three to
five attributes. It is the dataset wrapper induction is measured on.

For each site the first three pages, in the dataset's order, are the
seeds, and each attribute's example is its first labelled value on the
first seed that has one. The tools are given the seeds and the examples;
every other page, 124,051 in all, is read and scored. Beside
Sluicer, [Scrapling](https://github.com/D4Vinci/Scrapling)'s adaptive
selectors, which promise to find an element again when a page changes,
are asked the same thing, as [the drift benchmark](drift.md) asks them.

Regenerated on 2026-09-26 from commit `5e97f6b` by `uv run bench/swde.py`, against the mirror at `e9b60dbbcb89`, every
archive checked against its SHA-256. No seconds are printed: five
timed rounds of every tool would take nearly seven hours
([`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md),
"How a second is measured").

!!! warning "Read this before the numbers"
    These pages declare almost nothing, so every value here is learnt from
    where the example sits. A value that is part of a longer text, as in
    `Price: $129.00` in one cell, cannot be pointed at by either tool, and
    counts as not learnt. SWDE's labels were made by regular expressions
    over text nodes and stored with their HTML entities undecoded; they
    are decoded here before any comparison.

## Every site and attribute

F1 is averaged over the site-attributes, as SWDE's results are reported;
precision and recall pool every page. One extractor is learnt per site
and its pages stand or fall together, so each interval is the 95%
percentile interval of 10,000 resamples of the sites, not of the pages.

| system | mean F1 | precision | recall |
|---|---|---|---|
| **sluicer 0.10.0** | 0.850 (0.81–0.89) | 0.974 (0.95–0.99) | 0.849 (0.80–0.89) |
| Scrapling 0.4.15, adaptive | 0.671 (0.60–0.74) | 0.864 (0.81–0.91) | 0.710 (0.64–0.78) |

| Sluicer against Scrapling | difference (95% interval) | verdict |
|---|---|---|
| mean F1 | +0.179 (+0.124 to +0.237) | better |
| precision | +0.111 (+0.070 to +0.157) | better |
| recall | +0.139 (+0.084 to +0.198) | better |

The difference is Sluicer's minus Scrapling's; its interval is the 95%
percentile interval of 10,000 resamples of the sites, drawn together for
both (`bench/stats.py`, seed 20260924): **better** above zero, **worse**
below, **inconclusive** when it holds zero. With the two halves below,
these are five comparisons, made with no correction for making many, so
read them as a table, not one at a time.

| system | wrong answers | of them flagged by the run | not learnt (site-attributes) |
|---|---|---|---|
| **sluicer 0.10.0** | 11,156 | 1,999 (18%) | 20 of 320 |
| Scrapling 0.4.15, adaptive | 56,058 | no checks | 63 of 320 |

A wrong answer is a value that is not the page's, or a value where the
page has none. Sluicer's run checks each value it learnt: that its place
is still there, and that it still reads and is shaped as it was learnt.
A wrong answer those checks caught makes `sluicer run` exit 3; one they
did not is silent. Scrapling returns what it finds and has no check.

## By half

The sites were split before any full result was read (commit
`fc72378`): in each vertical, in alphabetical order, they alternate
between development and held-out. Sluicer's rules are made reading the
development sites only, so the development half measures Sluicer on
pages it was fitted to; the held-out ones are only scored, and are the
one held-out test of all the scoreboards. Their numbers have been read
at the releases and once to see whether a rule made on the development
half held before it was kept; [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) lists each
reading. One exception: all ten camera sites were read while the
benchmark was being built, before the split, so the held-out camera
sites are not a clean test.

| half | site-attributes | sluicer F1 | Scrapling F1 | difference (95% interval) | verdict |
|---|---|---|---|---|---|
| development | 160 | 0.855 (0.80–0.91) | 0.675 (0.59–0.76) | +0.180 (+0.107 to +0.253) | better |
| held-out | 160 | 0.845 (0.79–0.90) | 0.667 (0.57–0.77) | +0.178 (+0.097 to +0.261) | better |

## By vertical

| vertical | site-attributes | sluicer F1 | Scrapling F1 |
|---|---|---|---|
| auto | 40 | 0.869 | 0.688 |
| book | 50 | 0.797 | 0.524 |
| camera | 30 | 0.856 | 0.817 |
| job | 40 | 0.811 | 0.724 |
| movie | 40 | 0.860 | 0.842 |
| nbaplayer | 40 | 0.886 | 0.399 |
| restaurant | 40 | 0.903 | 0.692 |
| university | 40 | 0.832 | 0.756 |

## By attribute

| vertical | attribute | sluicer F1 | Scrapling F1 |
|---|---|---|---|
| auto | engine | 0.665 | 0.565 |
| auto | fuel_economy | 0.974 | 0.576 |
| auto | model | 1.000 | 0.900 |
| auto | price | 0.838 | 0.711 |
| book | author | 0.876 | 0.990 |
| book | isbn_13 | 0.889 | 0.238 |
| book | publication_date | 0.780 | 0.271 |
| book | publisher | 0.779 | 0.430 |
| book | title | 0.662 | 0.692 |
| camera | manufacturer | 0.896 | 0.893 |
| camera | model | 0.810 | 0.789 |
| camera | price | 0.862 | 0.770 |
| job | company | 0.844 | 0.798 |
| job | date_posted | 0.684 | 0.415 |
| job | location | 0.845 | 0.782 |
| job | title | 0.869 | 0.899 |
| movie | director | 0.835 | 0.877 |
| movie | genre | 0.933 | 0.891 |
| movie | mpaa_rating | 0.821 | 0.805 |
| movie | title | 0.850 | 0.793 |
| nbaplayer | height | 0.905 | 0.200 |
| nbaplayer | name | 0.986 | 0.786 |
| nbaplayer | team | 0.852 | 0.410 |
| nbaplayer | weight | 0.800 | 0.200 |
| restaurant | address | 0.800 | 0.616 |
| restaurant | cuisine | 0.959 | 0.793 |
| restaurant | name | 0.992 | 0.800 |
| restaurant | phone | 0.862 | 0.560 |
| university | name | 0.967 | 0.896 |
| university | phone | 0.512 | 0.387 |
| university | type | 0.966 | 0.840 |
| university | website | 0.883 | 0.900 |

## Since 0.6.0

0.6.0, measured on these pages on 2026-09-24 by the same code: mean F1
0.686 on each half, 13,058 wrong answers of which 2,014 were flagged, and
66 of 320 site-attributes not learnt. It read every page at the place the
example was on the first, and could not learn a value that shares its
element with its label.

## Reading the errors, by hand, at 0.7.0

The wrong answers were read by hand on the development sites only, looking
for rules Sluicer had wrong rather than for rules that would fit these
pages. The held-out sites were scored and not read.

- **A place that moves from page to page.** A product page's rows depend on
  the product: a saving row appears when there is a saving, and the price
  moves down one. 0.6.0 read every page at the place the example was on the
  first page, and on one camera site gave the saving as the price on 62
  pages in 100 with nothing flagged. 0.7.0 keeps the place while every page
  given agrees with it, and reads after the page's own label, as `Price:`,
  when one of them does not.
- **A value that shares its element with its label.** `ISBN: 978...`,
  `Phone: 907/279-7311`, `Engine: 3.0L Gas I6`: no element's whole text is
  the value, and 0.6.0 could not learn it at all. 0.7.0 reads the rest of
  the text the label opens.
- **What is left.** A place kept because the three pages agreed, on a page
  where the row above is missing: a job's location read as
  "Full-Time, Employee", a restaurant's cuisine as its "Reserve Online"
  button. A check was tried and left out: comparing the text before each
  value with the pages' own label caught 953 of these on the development
  sites and flagged 5,032 right answers, five false alarms for each catch.
- **The labels.** SWDE labels whole text nodes by regular expressions, so
  a label can be a fragment of the value the page shows ("Spy Kids 3D:"
  for "Spy Kids 3D: Game Over") or carry the template's separators
  (": 9780316125581"). Separators and case are set aside on both sides,
  for every tool; fragments are counted wrong, for every tool.

Scrapling's wrong answers are of the kind its design allows: a selector
that still matches on another page returns what is there, and it has no
check to say it is not the value it was saved for.
