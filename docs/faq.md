# FAQ

## Does Sluicer use an LLM anywhere?

No. A test fails the build if a model client is ever imported, and no feature
needs anybody's API key. Because no model is involved, the same page always
gives the same answer, and a run costs nothing but CPU time.

## What if a page declares nothing?

`sluicer extract --induce` reads the rows the page's markup repeats, a
listing's cards or a table's lines, marked `source="induced"`. And
`sluicer compile --want price=41.90` learns, from one example value, where that
value sits, on listings and on product pages that declare nothing. What it learns is
checked on every page it reads, so a price slot that starts saying "Add to
basket" fails instead of being returned.

## Will it get past a site's bot protection?

It is not built to. Every request says `Sluicer/<version>` with the project's
address, and robots.txt is obeyed. Only the stealth fetcher leaves Sluicer's
name out, and only a command that reads single pages or learns an extractor
uses it, when given `--stealth`; `map`, `crawl` and `batch` never do. In a crawl, a site that answers 429 or 503 is asked again only
after its `Retry-After`.

## Does it work in my language?

Declared data is the same in every language. The news scoreboard measures 21
languages, one to four pages for most of them: too few to rank languages. Dates
written in words are read with the month names of the 430 languages and regions
the Unicode CLDR covers at its modern level, and Chinese, Japanese and Korean
dates written with 年, 月 and 日 (or 년, 월, 일) are read too.

## Can I get a guess from the visible page when nothing is declared?

Yes, by default since 0.10: `sluicer extract`, `extract(...)` and
`extract_declared` read the heading, the byline and the publication and update
dates the page shows, by Sluicer's own rules and no model; `--no-visible`,
`visible=False` or `"visible": false` read what the page declares alone, a
few milliseconds a page faster. Each answer is a guess naming its element and rule, in a field of its
own, `visible`, never in the summary, where it would look exactly like a
declared one. An update date is never given as a publication date. The rules were made on WCXB's development pages alone, and there, with what is
declared first and the guesses after it:

| | author found | right when answered | invented |
|---|---|---|---|
| Sluicer | 70.1% | 84.9% | 58 |
| trafilatura | 69.8% | 75.6% | 86 |

| | date found | right when answered | invented |
|---|---|---|---|
| Sluicer | 73.6% | 77.9% | 83 |
| trafilatura | 83.3% | 44.1% | 630 |

On the pages it was not made on, each scoreboard's section "What `--visible`
adds" scores it: it finds more authors and dates -- on WCXB 0.649 and 0.717
of them against 0.532 and 0.581 -- and invents some, 33 answers on WCXB's 511
pages, so its dates are right less often when it answers (0.823 against
0.917).

## Is it ready for production?

It is Beta: the interface may still change before 1.0, and every change is in
the [changelog](changelog.md). [What is stable](stability.md) says which parts
will not change without one release of warning first. Every push runs the full
test suite on Python 3.10 to 3.14, with property tests drawing hundreds of
hostile pages per property, and thousands in a weekly run; before a release is
tagged, every scoreboard is measured again.
[Known limits](known-limits.md) lists what it does not do, measured.

## What does the project hold itself to?

- **No LLM call, anywhere in the path.** A test fails the build if a model
  client is ever imported.
- **No paid API.** A feature that needs somebody's key does not ship.
- **Deterministic.** The same page always gives the same answer, which is what
  makes the scoreboards reproducible.
- **Honest about failure.** A page that cannot be read says so, and no command
  makes up an answer when the page gives none.
