# FAQ

## Does Sluicer use an LLM anywhere?

No. A test fails the build if a model client is ever imported, and no feature
needs anybody's API key. That is what makes the same page give the same answer,
and a run cost only CPU.

## What if a page declares nothing?

`sluicer extract --induce` reads the rows the page's markup repeats, a
listing's cards or a table's lines, marked `source="induced"`. And
`sluicer compile --want price=41.90` learns where values sit from examples of
them, on listings and on product pages that declare nothing. What it learns is
checked on every page it reads, so a price slot that starts saying "Add to
basket" fails instead of being returned.

## Will it get past a site's bot protection?

It is not built to. Every request says `Sluicer/<version>` with the project's
address, and robots.txt is obeyed. A crawl never climbs to the one rung that
does not announce itself, which a single-page command reaches only with
`--stealth`. In a crawl, a site that answers 429 or 503 is asked again only
after its `Retry-After`.

## Does it work in my language?

Declared data is the same in every language, and the news scoreboard measures
21 of them; no miss there was down to a page's language. Dates written in words
are read with the month names of the 430 languages and regions the Unicode CLDR
covers at its modern level, and with the units Chinese, Japanese and Korean
write numbers with.

## Can I get a guess from the visible page when nothing is declared?

Yes, when you ask: `sluicer extract --visible`, `extract(..., visible=True)`
or `extract_declared` with `visible` read the heading, the byline and the
publication and update dates the page shows, by Sluicer's own rules and no
model. Each answer is a guess naming its element and rule, in a field of its
own, `visible`, never in the summary, where it would look exactly like a
declared one. An update date is never given as a publication date. On WCXB's
development pages, the only ones the rules were made on, what is declared and
then the guesses find the author on 0.701 of pages, right on 0.849 of answers
with 58 invented, where trafilatura finds 0.698, right on 0.756, with 86; and
the date on 0.736, right on 0.779 with 83 invented, where trafilatura finds
0.833, right on 0.441, with 630. The scoreboards have not measured it yet.

## Is it ready for production?

It is Beta: the interface may still change before 1.0, and every change is in
the [changelog](changelog.md). [What is stable](stability.md) says which parts
will not change without a release of warning. Each release passes the full
test suite on Python 3.10 to 3.14 and property tests that draw thousands of
hostile pages, and is measured again on every scoreboard, before it is tagged.
[Known limits](known-limits.md) lists what it does not do, measured.

## What does the project hold itself to?

- **No LLM call, anywhere in the path.** A test fails the build if a model
  client is ever imported.
- **No paid API.** A feature that needs somebody's key does not ship.
- **Deterministic.** The same page always gives the same answer, which is what
  makes the scoreboards reproducible.
- **Honest about failure.** A page that cannot be read says so, and nothing
  returns a plausible answer where the truth was unavailable.
