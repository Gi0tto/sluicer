# Scoreboard, trafilatura's evaluation set

The same questions as the [scoreboard](scoreboard.md) -- a page's title,
author and publication date -- on the pages trafilatura evaluates itself
on, 990 saved with their scripts, 851 of them annotated for their metadata, and the main text beside them.
Regenerated on 2026-09-25 from commit `4ec92b0` by
`uv run bench/evaldata.py`, against trafilatura at `c852cae9708a`; the
method is in [`bench/`](https://github.com/Gi0tto/sluicer/tree/main/bench).

!!! warning "Sluicer's rules were made on these pages"
    Rules were written, measured on these pages and kept because the
    numbers here rose (`bebff9d`, among others), so this measures
    Sluicer on pages it was fitted to, not on pages it has never seen.
    Of the scoreboards, only SWDE's held-out half is a held-out test;
    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md) says which pages each rule was made on.

!!! warning "Read this before the numbers"
    trafilatura's authors annotated these pages to measure trafilatura,
    so the labels follow what it is built to find: the byline and the date
    a reader sees, which Sluicer does not read, as the known limits say.
    The pages are mostly German blogs and small sites. An empty annotation
    is a page the annotators saw no author or date on, so an invention
    here is an answer where the page shows none, not one it does not
    declare.

## Title, author, date

Hit rate is hits over the pages that carry a label (845 titles, 538 authors, 728 dates on the 851 annotated pages).

| tool | title | author | date | authors invented | dates invented |
|---|---|---|---|---|---|
| sluicer 0.7.1 | 0.776 | 0.468 | 0.585 | 97 | 39 |
| trafilatura 2.2.0 | 0.738 | 0.669 | 0.865 | 122 | 121 |
| metascraper 5.58.1 | 0.699 | 0.662 | 0.663 | 153 | 62 |
| newspaper4k 0.9.6 | 0.756 | 0.507 | 0.668 | 106 | 49 |

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | title | 656 | 189 | 0 | 0 | 6 | 0.776 | 0.771 |
| sluicer 0.7.1 | author | 252 | 47 | 239 | 216 | 97 | 0.468 | 0.636 |
| sluicer 0.7.1 | date | 426 | 72 | 230 | 84 | 39 | 0.585 | 0.793 |
| trafilatura 2.2.0 | title | 624 | 221 | 0 | 0 | 6 | 0.738 | 0.733 |
| trafilatura 2.2.0 | author | 360 | 74 | 104 | 191 | 122 | 0.669 | 0.647 |
| trafilatura 2.2.0 | date | 630 | 97 | 1 | 2 | 121 | 0.865 | 0.743 |
| metascraper 5.58.1 | title | 591 | 241 | 13 | 0 | 6 | 0.699 | 0.705 |
| metascraper 5.58.1 | author | 356 | 110 | 72 | 160 | 153 | 0.662 | 0.575 |
| metascraper 5.58.1 | date | 483 | 136 | 109 | 61 | 62 | 0.663 | 0.709 |
| newspaper4k 0.9.6 | title | 639 | 200 | 6 | 0 | 6 | 0.756 | 0.756 |
| newspaper4k 0.9.6 | author | 273 | 78 | 187 | 207 | 106 | 0.507 | 0.597 |
| newspaper4k 0.9.6 | date | 486 | 71 | 171 | 74 | 49 | 0.668 | 0.802 |

## The main text

`sluicer.markdown` is trafilatura's extraction, written as markdown with
links and tables kept, so the page's text is trafilatura's by design;
what this measures is what writing it as markdown costs. A link is
written `[its text](its address)`, so a snippet that runs across one is
not found as written: the markdown finds 2,670 of the 2,951 snippets, and
with its syntax taken out 2,767 of the 2,951, where trafilatura's text finds 2,785 of the 2,951.
The syntax is taken out roughly, which also takes the underscore out
of `Liebe_r`. Scored on all 990 pages, as trafilatura scores itself.

| output | snippets found | snippets kept out | precision | recall | F1 |
|---|---|---|---|---|---|
| sluicer.markdown | 2670/2951 | 2671/2966 | 0.901 | 0.905 | 0.903 |
| sluicer.markdown, its syntax taken out | 2767/2951 | 2642/2966 | 0.895 | 0.938 | 0.916 |
| trafilatura text | 2785/2951 | 2646/2966 | 0.897 | 0.944 | 0.920 |
