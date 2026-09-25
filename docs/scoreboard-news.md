# Scoreboard, news in many languages

The same questions as the [scoreboard](scoreboard.md) -- a page's title,
author and publication date -- on news pages from 42 countries'
publishers, in 21 declared languages, with their scripts:
as fundus fetched them, stored re-encoded as UTF-8.
Regenerated on 2026-09-25 from commit `f042855` by
`uv run bench/news.py`, against fundus at `c1b86b675018`; the method is in
[`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).

!!! warning "Sluicer's rules were made on these pages"
    Rules were written, measured on these pages and kept because the
    numbers here rose (`523e6b1`, `f84541c`, `074b4ad`, among others), so this measures
    Sluicer on pages it was fitted to, not on pages it has never seen.
    Of the scoreboards, only SWDE's held-out half is a held-out test;
    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) says which pages each rule was made on.

!!! warning "Read this before the numbers"
    The labels are what fundus's parser for each publisher reads, and a
    parser reads the page a person sees: the headline shown, the byline.
    A page often declares something else -- a headline written for
    search, the publisher as the author -- and Sluicer answers what is
    declared, so a disagreement is counted here as wrong even when the
    declaration is the page's own. Where the page names no one else,
    fundus's labels count the paper itself the author, which Sluicer
    does not, as WCXB's labels do not: of the 25 pages where another
    tool finds the author and Sluicer does not, at least 13 are labelled
    with the publisher's own name (see the known limits). Many of
    fundus's parsers read the page's JSON-LD themselves, so part of the
    agreement is circular. And the pages are 1 to 4 per
    publisher, 109 of 263 declaring `de`: read a
    language's row as a handful of pages, not a rate.

## Results

Hit rate is hits over the pages that carry a label (263 titles, 257 authors, 263 dates on the 263 pages). fundus leaves a label empty where its parser found nothing, so an invention here is an answer where the page shows none, not necessarily one it does not declare.

| tool | title | author | date | authors invented | dates invented |
|---|---|---|---|---|---|
| sluicer 0.7.1 | 0.871 (0.82–0.91) | 0.829 (0.77–0.87) | 0.970 (0.94–0.99) | 4 | 0 |
| trafilatura 2.2.0 | 0.852 (0.80–0.89) | 0.879 (0.83–0.92) | 0.970 (0.94–0.99) | 3 | 0 |
| metascraper 5.58.1 | 0.726 (0.66–0.78) | 0.864 (0.81–0.91) | 0.981 (0.95–1.00) | 5 | 0 |
| newspaper4k 0.9.6 | 0.779 (0.72–0.83) | 0.767 (0.71–0.82) | 0.932 (0.89–0.96) | 1 | 0 |

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | title | 229 | 34 | 0 | 0 | 0 | 0.871 (0.82–0.91) | 0.871 (0.82–0.91) |
| sluicer 0.7.1 | author | 213 | 13 | 31 | 2 | 4 | 0.829 (0.77–0.87) | 0.926 (0.88–0.96) |
| sluicer 0.7.1 | date | 255 | 0 | 8 | 0 | 0 | 0.970 (0.94–0.99) | 1.000 (0.98–1.00) |
| trafilatura 2.2.0 | title | 224 | 39 | 0 | 0 | 0 | 0.852 (0.80–0.89) | 0.852 (0.80–0.89) |
| trafilatura 2.2.0 | author | 226 | 12 | 19 | 3 | 3 | 0.879 (0.83–0.92) | 0.938 (0.89–0.97) |
| trafilatura 2.2.0 | date | 255 | 8 | 0 | 0 | 0 | 0.970 (0.94–0.99) | 0.970 (0.94–0.99) |
| metascraper 5.58.1 | title | 191 | 72 | 0 | 0 | 0 | 0.726 (0.66–0.78) | 0.726 (0.66–0.78) |
| metascraper 5.58.1 | author | 222 | 31 | 4 | 1 | 5 | 0.864 (0.81–0.91) | 0.860 (0.81–0.90) |
| metascraper 5.58.1 | date | 258 | 2 | 3 | 0 | 0 | 0.981 (0.95–1.00) | 0.992 (0.97–1.00) |
| newspaper4k 0.9.6 | title | 205 | 44 | 14 | 0 | 0 | 0.779 (0.72–0.83) | 0.823 (0.77–0.87) |
| newspaper4k 0.9.6 | author | 197 | 32 | 28 | 5 | 1 | 0.767 (0.71–0.82) | 0.857 (0.80–0.90) |
| newspaper4k 0.9.6 | date | 245 | 0 | 18 | 0 | 0 | 0.932 (0.89–0.96) | 1.000 (0.98–1.00) |

## How sure, and what differs

Each rate above carries its 95% Wilson score interval, the bounds
rounded outwards to two places. Sluicer against each other tool:

| Sluicer against | field | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| trafilatura 2.2.0 | title | hit rate | +0.019 (-0.039 to +0.077) | inconclusive |
| trafilatura 2.2.0 | title | right when answering | +0.019 (-0.039 to +0.077) | inconclusive |
| trafilatura 2.2.0 | author | hit rate | -0.051 (-0.086 to -0.015) | worse |
| trafilatura 2.2.0 | author | right when answering | -0.012 (-0.042 to +0.018) | inconclusive |
| trafilatura 2.2.0 | date | hit rate | 0.000 (-0.020 to +0.023) | inconclusive |
| trafilatura 2.2.0 | date | right when answering | +0.030 (+0.011 to +0.054) | better |
| metascraper 5.58.1 | title | hit rate | +0.144 (+0.079 to +0.210) | better |
| metascraper 5.58.1 | title | right when answering | +0.144 (+0.079 to +0.210) | better |
| metascraper 5.58.1 | author | hit rate | -0.035 (-0.078 to +0.008) | inconclusive |
| metascraper 5.58.1 | author | right when answering | +0.066 (+0.034 to +0.101) | better |
| metascraper 5.58.1 | date | hit rate | -0.011 (-0.031 to +0.004) | inconclusive |
| metascraper 5.58.1 | date | right when answering | +0.008 (0.000 to +0.020) | inconclusive |
| newspaper4k 0.9.6 | title | hit rate | +0.091 (+0.038 to +0.145) | better |
| newspaper4k 0.9.6 | title | right when answering | +0.047 (-0.001 to +0.097) | inconclusive |
| newspaper4k 0.9.6 | author | hit rate | +0.062 (+0.011 to +0.114) | better |
| newspaper4k 0.9.6 | author | right when answering | +0.070 (+0.026 to +0.114) | better |
| newspaper4k 0.9.6 | date | hit rate | +0.038 (+0.011 to +0.069) | better |
| newspaper4k 0.9.6 | date | right when answering | 0.000 (0.000 to 0.000) | inconclusive |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
18 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## What `--visible` adds

`extract(..., visible=True)`, `--visible` on the command line, also
guesses the title, byline and dates a page shows, and keeps each guess
apart from the summary. Its rules were made on WCXB's development split
only, which no scoreboard scores, so these pages are held out from them
([`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)). *Declared* is the summary, as above;
*declared then `--visible`* answers with the summary where it has an
answer and with the guess where it has none, never in its place.

| field | hit rate, declared | hit rate, declared then `--visible` | right when answering, declared | right when answering, declared then `--visible` | inventions, declared | silent miss made a hit | silent miss made wrong | inventions `--visible` added |
|---|---|---|---|---|---|---|---|---|
| title | 0.871 (0.82–0.91) | 0.871 (0.82–0.91) | 0.871 (0.82–0.91) | 0.871 (0.82–0.91) | 0 | 0 | 0 | 0 |
| author | 0.829 (0.77–0.87) | 0.844 (0.79–0.89) | 0.926 (0.88–0.96) | 0.923 (0.88–0.96) | 4 | 4 | 1 | 0 |
| date | 0.970 (0.94–0.99) | 0.981 (0.95–1.00) | 1.000 (0.98–1.00) | 0.992 (0.97–1.00) | 0 | 3 | 2 | 0 |

`--visible` answered 10 questions the summary left unanswered: 7 right and 3 wrong where the page carries a label, and 0 invented where it carries none. Each rate carries its 95% Wilson score interval. Declared then `--visible` against the declared answers alone and against each other tool:

| declared then `--visible`, against | field | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| sluicer 0.7.1, declared | title | hit rate | 0.000 (0.000 to 0.000) | inconclusive |
| sluicer 0.7.1, declared | title | right when answering | 0.000 (0.000 to 0.000) | inconclusive |
| sluicer 0.7.1, declared | author | hit rate | +0.016 (+0.003 to +0.032) | better |
| sluicer 0.7.1, declared | author | right when answering | -0.003 (-0.012 to +0.003) | inconclusive |
| sluicer 0.7.1, declared | date | hit rate | +0.011 (0.000 to +0.027) | inconclusive |
| sluicer 0.7.1, declared | date | right when answering | -0.008 (-0.020 to 0.000) | inconclusive |
| trafilatura 2.2.0 | title | hit rate | +0.019 (-0.039 to +0.077) | inconclusive |
| trafilatura 2.2.0 | title | right when answering | +0.019 (-0.039 to +0.077) | inconclusive |
| trafilatura 2.2.0 | author | hit rate | -0.035 (-0.070 to -0.003) | worse |
| trafilatura 2.2.0 | author | right when answering | -0.014 (-0.043 to +0.014) | inconclusive |
| trafilatura 2.2.0 | date | hit rate | +0.011 (-0.004 to +0.031) | inconclusive |
| trafilatura 2.2.0 | date | right when answering | +0.023 (+0.007 to +0.042) | better |
| metascraper 5.58.1 | title | hit rate | +0.144 (+0.079 to +0.210) | better |
| metascraper 5.58.1 | title | right when answering | +0.144 (+0.079 to +0.210) | better |
| metascraper 5.58.1 | author | hit rate | -0.019 (-0.059 to +0.020) | inconclusive |
| metascraper 5.58.1 | author | right when answering | +0.063 (+0.031 to +0.098) | better |
| metascraper 5.58.1 | date | hit rate | 0.000 (-0.016 to +0.016) | inconclusive |
| metascraper 5.58.1 | date | right when answering | 0.000 (-0.012 to +0.012) | inconclusive |
| newspaper4k 0.9.6 | title | hit rate | +0.091 (+0.038 to +0.145) | better |
| newspaper4k 0.9.6 | title | right when answering | +0.047 (-0.001 to +0.097) | inconclusive |
| newspaper4k 0.9.6 | author | hit rate | +0.078 (+0.027 to +0.128) | better |
| newspaper4k 0.9.6 | author | right when answering | +0.067 (+0.024 to +0.111) | better |
| newspaper4k 0.9.6 | date | hit rate | +0.049 (+0.022 to +0.080) | better |
| newspaper4k 0.9.6 | date | right when answering | -0.008 (-0.020 to 0.000) | inconclusive |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
24 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

## By language

Each page is counted under the language its `<html lang>` declares.

### Title

| language | pages | sluicer 0.7.1 | trafilatura 2.2.0 | metascraper 5.58.1 | newspaper4k 0.9.6 |
|---|---|---|---|---|---|
| de | 109 | 94/109 | 91/109 | 87/109 | 85/109 |
| en | 90 | 76/90 | 74/90 | 58/90 | 74/90 |
| es | 8 | 8/8 | 8/8 | 6/8 | 8/8 |
| ja | 7 | 7/7 | 6/7 | 6/7 | 0/7 |
| none | 7 | 7/7 | 6/7 | 4/7 | 6/7 |
| fr | 5 | 4/5 | 5/5 | 3/5 | 4/5 |
| no | 5 | 3/5 | 5/5 | 5/5 | 5/5 |
| it | 4 | 4/4 | 3/4 | 1/4 | 3/4 |
| ko | 4 | 4/4 | 3/4 | 1/4 | 1/4 |
| tr | 4 | 4/4 | 4/4 | 2/4 | 4/4 |
| cs | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| sv | 3 | 3/3 | 3/3 | 3/3 | 2/3 |
| ar | 2 | 1/2 | 2/2 | 1/2 | 0/2 |
| da | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| pl | 2 | 1/2 | 1/2 | 1/2 | 1/2 |
| ru | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| hi | 1 | 1/1 | 1/1 | 1/1 | 0/1 |
| id | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| is | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| lt | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| nl | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| vi | 1 | 1/1 | 1/1 | 1/1 | 1/1 |

### Author

| language | pages | sluicer 0.7.1 | trafilatura 2.2.0 | metascraper 5.58.1 | newspaper4k 0.9.6 |
|---|---|---|---|---|---|
| de | 109 | 89/107 | 98/107 | 93/107 | 85/107 |
| en | 90 | 82/89 | 83/89 | 82/89 | 72/89 |
| es | 8 | 8/8 | 8/8 | 8/8 | 7/8 |
| ja | 7 | 1/6 | 2/6 | 5/6 | 0/6 |
| none | 7 | 3/7 | 2/7 | 3/7 | 3/7 |
| fr | 5 | 3/5 | 5/5 | 4/5 | 4/5 |
| no | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| it | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| ko | 4 | 4/4 | 4/4 | 3/4 | 1/4 |
| tr | 4 | 1/4 | 2/4 | 2/4 | 2/4 |
| cs | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| sv | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| ar | 2 | - | - | - | - |
| da | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| pl | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| ru | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| hi | 1 | 1/1 | 0/1 | 1/1 | 0/1 |
| id | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| is | 1 | 0/1 | 0/1 | 0/1 | 1/1 |
| lt | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| nl | 1 | 0/1 | 1/1 | 0/1 | 1/1 |
| vi | 1 | 0/1 | 0/1 | 0/1 | 0/1 |

### Date

| language | pages | sluicer 0.7.1 | trafilatura 2.2.0 | metascraper 5.58.1 | newspaper4k 0.9.6 |
|---|---|---|---|---|---|
| de | 109 | 104/109 | 105/109 | 107/109 | 106/109 |
| en | 90 | 89/90 | 87/90 | 90/90 | 90/90 |
| es | 8 | 8/8 | 8/8 | 8/8 | 8/8 |
| ja | 7 | 7/7 | 7/7 | 7/7 | 0/7 |
| none | 7 | 6/7 | 6/7 | 5/7 | 6/7 |
| fr | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| no | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| it | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| ko | 4 | 3/4 | 4/4 | 3/4 | 0/4 |
| tr | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| cs | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| sv | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| ar | 2 | 2/2 | 2/2 | 2/2 | 0/2 |
| da | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| pl | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| ru | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| hi | 1 | 1/1 | 1/1 | 1/1 | 0/1 |
| id | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| is | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| lt | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| nl | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| vi | 1 | 1/1 | 1/1 | 1/1 | 1/1 |

## Speed and size

Measured on 2026-09-25 by `uv run bench/timing.py news` at commit `f042855`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | Python 3.12.13 | 0.0046 | 1.21 (0.96–1.25) | 217 | 195.6 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0092 | 2.42 (2.05–2.58) | 109 | 247.2 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0117 | 3.07 (2.22–3.16) | 86 | 1398.5 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0690 | 18.14 (15.98–19.39) | 14 | 333.0 MiB | 39.4 MiB | 22 |

How install size and memory are counted, and the other tables, are in
[speed and weight](speed.md).
