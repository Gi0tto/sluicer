# Scoreboard, news in many languages

The same questions as the [scoreboard](scoreboard.md) -- a page's title,
author and publication date -- on news pages from 42 countries'
publishers, in 21 declared languages, with their scripts:
as fundus fetched them, stored re-encoded as UTF-8.
Regenerated on 2026-09-24 from commit `574d6c8` by
`uv run bench/news.py`, against fundus at `c1b86b675018`; the method is in
[`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).

!!! warning "Read this before the numbers"
    The labels are what fundus's parser for each publisher reads, and a
    parser reads the page a person sees: the headline shown, the byline.
    A page often declares something else -- a headline written for
    search, the publisher as the author -- and Sluicer answers what is
    declared, so a disagreement is counted here as wrong even when the
    declaration is the page's own. Where the page names no one else,
    fundus's labels count the paper itself the author, which Sluicer
    does not, as WCXB's labels do not: that is most of the authors
    another tool finds here and Sluicer does not (see the known
    limits). Many of fundus's parsers read the
    page's JSON-LD themselves, so part of the agreement is circular. And
    the pages are one or two per publisher, German-heavy: read a
    language's row as a handful of pages, not a rate.

## Results

Hit rate is hits over the pages that carry a label (263 titles, 257 authors, 263 dates on the 263 pages). fundus leaves a label empty where its parser found nothing, so an invention here is an answer where the page shows none, not necessarily one it does not declare.

| tool | title | author | date | authors invented | dates invented |
|---|---|---|---|---|---|
| sluicer 0.7.0 | 0.871 | 0.829 | 0.970 | 4 | 0 |
| trafilatura 2.2.0 | 0.852 | 0.879 | 0.970 | 3 | 0 |
| metascraper 5.58.1 | 0.726 | 0.864 | 0.966 | 5 | 0 |
| newspaper4k 0.9.6 | 0.779 | 0.767 | 0.932 | 1 | 0 |

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.7.0 | title | 229 | 34 | 0 | 0 | 0 | 0.871 | 0.871 |
| sluicer 0.7.0 | author | 213 | 13 | 31 | 2 | 4 | 0.829 | 0.926 |
| sluicer 0.7.0 | date | 255 | 0 | 8 | 0 | 0 | 0.970 | 1.000 |
| trafilatura 2.2.0 | title | 224 | 39 | 0 | 0 | 0 | 0.852 | 0.852 |
| trafilatura 2.2.0 | author | 226 | 12 | 19 | 3 | 3 | 0.879 | 0.938 |
| trafilatura 2.2.0 | date | 255 | 8 | 0 | 0 | 0 | 0.970 | 0.970 |
| metascraper 5.58.1 | title | 191 | 72 | 0 | 0 | 0 | 0.726 | 0.726 |
| metascraper 5.58.1 | author | 222 | 31 | 4 | 1 | 5 | 0.864 | 0.860 |
| metascraper 5.58.1 | date | 254 | 6 | 3 | 0 | 0 | 0.966 | 0.977 |
| newspaper4k 0.9.6 | title | 205 | 44 | 14 | 0 | 0 | 0.779 | 0.823 |
| newspaper4k 0.9.6 | author | 197 | 32 | 28 | 5 | 1 | 0.767 | 0.857 |
| newspaper4k 0.9.6 | date | 245 | 0 | 18 | 0 | 0 | 0.932 | 1.000 |

## By language

Each page is counted under the language its `<html lang>` declares.

### Title

| language | pages | sluicer 0.7.0 | trafilatura 2.2.0 | metascraper 5.58.1 | newspaper4k 0.9.6 |
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

| language | pages | sluicer 0.7.0 | trafilatura 2.2.0 | metascraper 5.58.1 | newspaper4k 0.9.6 |
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

| language | pages | sluicer 0.7.0 | trafilatura 2.2.0 | metascraper 5.58.1 | newspaper4k 0.9.6 |
|---|---|---|---|---|---|
| de | 109 | 104/109 | 105/109 | 107/109 | 106/109 |
| en | 90 | 89/90 | 87/90 | 90/90 | 90/90 |
| es | 8 | 8/8 | 8/8 | 7/8 | 8/8 |
| ja | 7 | 7/7 | 7/7 | 6/7 | 0/7 |
| none | 7 | 6/7 | 6/7 | 4/7 | 6/7 |
| fr | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| no | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| it | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| ko | 4 | 3/4 | 4/4 | 2/4 | 0/4 |
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

| tool | seconds for all pages | packages installed |
|---|---|---|
| sluicer 0.7.0 | 1.19 | 3 |
| trafilatura 2.2.0 | 2.10 | 17 |
| metascraper 5.58.1 | 2.39 | 125 |
| newspaper4k 0.9.6 | 15.71 | 22 |
