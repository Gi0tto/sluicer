# Scoreboard, trafilatura's evaluation set

The same questions as the [scoreboard](scoreboard.md) -- a page's title,
author and publication date -- on the pages trafilatura evaluates itself
on, 990 saved with their scripts, 851 of them annotated for their metadata, and the main text beside them.
Regenerated on 2026-09-25 from commit `05dc717` by
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
| sluicer 0.7.1 | 0.776 (0.74–0.81) | 0.468 (0.42–0.52) | 0.585 (0.54–0.63) | 97 | 39 |
| trafilatura 2.2.0 | 0.738 (0.70–0.77) | 0.669 (0.62–0.71) | 0.865 (0.83–0.89) | 122 | 121 |
| metascraper 5.58.1 | 0.699 (0.66–0.73) | 0.662 (0.62–0.71) | 0.663 (0.62–0.70) | 153 | 62 |
| newspaper4k 0.9.6 | 0.756 (0.72–0.79) | 0.507 (0.46–0.55) | 0.668 (0.63–0.71) | 106 | 49 |

| tool | field | hit | wrong | silent miss | correct silence | invention | hit rate | right when answering |
|---|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | title | 656 | 189 | 0 | 0 | 6 | 0.776 (0.74–0.81) | 0.771 (0.74–0.80) |
| sluicer 0.7.1 | author | 252 | 47 | 239 | 216 | 97 | 0.468 (0.42–0.52) | 0.636 (0.58–0.69) |
| sluicer 0.7.1 | date | 426 | 72 | 230 | 84 | 39 | 0.585 (0.54–0.63) | 0.793 (0.75–0.83) |
| trafilatura 2.2.0 | title | 624 | 221 | 0 | 0 | 6 | 0.738 (0.70–0.77) | 0.733 (0.70–0.77) |
| trafilatura 2.2.0 | author | 360 | 74 | 104 | 191 | 122 | 0.669 (0.62–0.71) | 0.647 (0.60–0.69) |
| trafilatura 2.2.0 | date | 630 | 97 | 1 | 2 | 121 | 0.865 (0.83–0.89) | 0.743 (0.71–0.78) |
| metascraper 5.58.1 | title | 591 | 241 | 13 | 0 | 6 | 0.699 (0.66–0.73) | 0.705 (0.67–0.74) |
| metascraper 5.58.1 | author | 356 | 110 | 72 | 160 | 153 | 0.662 (0.62–0.71) | 0.575 (0.53–0.62) |
| metascraper 5.58.1 | date | 483 | 136 | 109 | 61 | 62 | 0.663 (0.62–0.70) | 0.709 (0.67–0.75) |
| newspaper4k 0.9.6 | title | 639 | 200 | 6 | 0 | 6 | 0.756 (0.72–0.79) | 0.756 (0.72–0.79) |
| newspaper4k 0.9.6 | author | 273 | 78 | 187 | 207 | 106 | 0.507 (0.46–0.55) | 0.597 (0.55–0.65) |
| newspaper4k 0.9.6 | date | 486 | 71 | 171 | 74 | 49 | 0.668 (0.63–0.71) | 0.802 (0.76–0.84) |

Each rate carries its 95% Wilson score interval, the bounds rounded
outwards to two places. Sluicer against each other tool:

| Sluicer against | field | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| trafilatura 2.2.0 | title | hit rate | +0.038 (+0.012 to +0.064) | better |
| trafilatura 2.2.0 | title | right when answering | +0.038 (+0.012 to +0.064) | better |
| trafilatura 2.2.0 | author | hit rate | -0.201 (-0.238 to -0.163) | worse |
| trafilatura 2.2.0 | author | right when answering | -0.011 (-0.043 to +0.022) | inconclusive |
| trafilatura 2.2.0 | date | hit rate | -0.280 (-0.315 to -0.246) | worse |
| trafilatura 2.2.0 | date | right when answering | +0.050 (+0.020 to +0.080) | better |
| metascraper 5.58.1 | title | hit rate | +0.077 (+0.053 to +0.102) | better |
| metascraper 5.58.1 | title | right when answering | +0.066 (+0.042 to +0.090) | better |
| metascraper 5.58.1 | author | hit rate | -0.193 (-0.233 to -0.153) | worse |
| metascraper 5.58.1 | author | right when answering | +0.061 (+0.025 to +0.098) | better |
| metascraper 5.58.1 | date | hit rate | -0.078 (-0.106 to -0.051) | worse |
| metascraper 5.58.1 | date | right when answering | +0.084 (+0.055 to +0.112) | better |
| newspaper4k 0.9.6 | title | hit rate | +0.020 (-0.008 to +0.048) | inconclusive |
| newspaper4k 0.9.6 | title | right when answering | +0.015 (-0.012 to +0.041) | inconclusive |
| newspaper4k 0.9.6 | author | hit rate | -0.039 (-0.072 to -0.007) | worse |
| newspaper4k 0.9.6 | author | right when answering | +0.039 (+0.002 to +0.076) | better |
| newspaper4k 0.9.6 | date | hit rate | -0.082 (-0.108 to -0.057) | worse |
| newspaper4k 0.9.6 | date | right when answering | -0.009 (-0.031 to +0.013) | inconclusive |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
18 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.

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
| sluicer.markdown | 2670/2951 | 2671/2966 | 0.901 (0.88–0.92) | 0.905 (0.89–0.92) | 0.903 (0.89–0.92) |
| sluicer.markdown, its syntax taken out | 2767/2951 | 2642/2966 | 0.895 (0.88–0.91) | 0.938 (0.92–0.95) | 0.916 (0.90–0.93) |
| trafilatura text | 2785/2951 | 2646/2966 | 0.897 (0.88–0.91) | 0.944 (0.93–0.96) | 0.920 (0.91–0.93) |

Several snippets sit on one page, so each interval here is the 95%
percentile interval of 10,000 resamples of the pages, not a Wilson
interval over snippets. Each of Sluicer's outputs against trafilatura's
text, the pages resampled together:

| output | against | rate | difference (95% interval) | verdict |
|---|---|---|---|---|
| sluicer.markdown | trafilatura text | precision | +0.004 (-0.002 to +0.009) | inconclusive |
| sluicer.markdown | trafilatura text | recall | -0.039 (-0.049 to -0.029) | worse |
| sluicer.markdown | trafilatura text | F1 | -0.017 (-0.023 to -0.011) | worse |
| sluicer.markdown, its syntax taken out | trafilatura text | precision | -0.002 (-0.005 to +0.002) | inconclusive |
| sluicer.markdown, its syntax taken out | trafilatura text | recall | -0.006 (-0.013 to -0.0003) | worse |
| sluicer.markdown, its syntax taken out | trafilatura text | F1 | -0.004 (-0.008 to -0.0004) | worse |

The difference is the first side's rate minus the second's, over the
same pages. Its interval is the 95% percentile interval of 10,000
resamples of the pages, drawn together for both sides (`bench/stats.py`,
seed 20260924): **better** when the interval is above zero, **worse**
when it is below, **inconclusive** when it holds zero. These are
6 comparisons, made with no correction for making many: where two
sides did not differ at all, about one in twenty would still be called
better or worse, so read the verdicts as a table, not one at a time.
