# What the scoreboards fix before they are run

A scoreboard is only a measure if what it measures, how it scores and what
counts as better are decided before the numbers are read. This file says what
is fixed. Changing any of it is a change to the scoreboards, made in its own
commit, with the pages it changes regenerated in that commit.

## Which pages Sluicer's rules were made on

Five of the six scoreboards, and the drift benchmark, had rules made while
their pages were read: a rule was written, measured on those pages, and kept
because the numbers there rose. Their numbers say how Sluicer does on pages it
was fitted to, not on pages it has never seen, and each of them says so. The
commits say it themselves:

| scoreboard | rules made while its pages were read, for example |
|---|---|
| WCXB, 511 test pages | `659f3a6`, `709856e` ("measured across the 359 WCXB pages"), `b86aa19` ("Measured on WCXB's 511-page test split") |
| as served, the same pages | `8e723ed` (the date and price forms they write), `7876710`, `074b4ad`, `f84541c` |
| news | `523e6b1`, `f84541c` ("Found on the multilingual news scoreboard"), `074b4ad` |
| trafilatura's set | `bebff9d` ("on the scoreboards' pages and trafilatura's evaluation set") |
| products | `7876710` ("Measured on Zyte's product benchmark"), `9548a35` (to pass extruct's SKU), `6fcbc7a` |
| drift | `92e5824`, `cd47d1b`, `af14095`, `f592d0c`, `faf097e`, `a8e7877` ("Found by the drift benchmark") |
| SWDE, development half | by design: `4978927` |

Held out, and only these:

- **SWDE's held-out half, less its camera sites.** Split before any full
  result was read; no rule was made reading its pages or its errors. Its
  numbers have been read at the readings listed below, and one of those readings
  was to see whether a rule made on the development half held before it was
  kept. The ten camera sites were read before the split.
- **Every scoreboard, for `--visible` alone.** Its rules were made on WCXB's
  development split, which no scoreboard scores; the summary's rules were not.

Until 0.7.1, `bench/products.py` said "Nothing is tuned to these pages" and
this file called the scoreboards held out without saying for what; both were
wrong for the summary, and this section replaces them. From 0.7.1 on, a rule
measured on a scoreboard's pages names that scoreboard in its commit.

## The corpora, pinned

| scoreboard | corpus | pinned at | checked by |
|---|---|---|---|
| WCXB | Web Content Extraction Benchmark, test split, 511 pages | commit `c039d5ee9f5a` | `bench/corpus.py` |
| as served | the same pages from the Wayback Machine and Common Crawl, 360 | each capture's SHA-256 in `realweb-manifest.json` | `bench/realweb.py` stops on a mismatch |
| news | fundus parser fixtures, 263 pages, 42 countries | commit `c1b86b67501` | `bench/news.py` |
| trafilatura's set | trafilatura's evaluation pages, 990 (851 annotated) | commit `c852cae9708a` | `bench/evaldata.py` |
| products | Zyte's product-extraction benchmark, 140 pages | commit `cba97d7a8d42` | `bench/products.py` |
| drift | 44 Wayback pairs over 25 sites | `bench/drift/pairs.json` | `bench/drift/run.py` |
| SWDE | 80 sites, 124,291 pages, 9 archives | mirror commit `e9b60db`, each archive's SHA-256 | `bench/swde.py` stops on a mismatch |
| W3C JSON-LD in HTML | the JSON-LD 1.1 test suite's `html-manifest.jsonld`, 50 tests | commit `ffdb326121ea` | `bench/w3c_jsonld.py` |

No corpus is committed here; each is downloaded into `bench/cache/`.

## How an answer is scored

- Title, author and date (`bench/score.py`): a title is right when it equals
  the label, lowercased and spaces collapsed, or one contains the other and
  the shorter is at least 0.6 of the longer; an author when the shared name
  tokens cover half the label's and a quarter of the answer's; a date by the
  rule below. An answer where the label is empty is an invention.
- A date (fixed on 2026-09-24; before it, dateutil filled a part a date does
  not write with the day the scorer ran, so "March 2021" matched a label of
  2021-03-24 on the 24th of a month only, and "10:52" matched today). Both
  sides are parsed by dateutil with a fixed default, never the clock, and the
  parts each writes -- year, month, day -- are known by parsing it under two
  defaults that differ in every part.
  - **The label decides what must be said.** A hit when the answer writes
    every part the label writes, and each is the label's. A label of `2015-11`
    is matched by any day of November 2015; a label of `2018-07-10` is not
    matched by `July 2018`, nor by a time with no date.
  - **Day first or month first.** Numbers written with dots are read day
    first (`10.12.2022` is 10 December), as every language that writes dates
    with dots does; numbers written with slashes month first, dateutil's
    order (`11/01/2023` is 1 November). Every date label the scoreboards
    score is written year first: WCXB's (the as-served pages' too) and
    trafilatura's as `YYYY-MM-DD` (one WCXB label is `YYYY-MM`), fundus's as
    `YYYY-MM-DD hh:mm:ss`, most with a UTC offset. Only answers are written
    otherwise.
  - **Time zones.** When both carry a UTC offset they name an instant, and
    the answer is read in the label's offset before its calendar date is
    compared: metascraper writes every date in UTC, and fundus's labels in
    the publisher's own. Otherwise each date is read as written, since a
    label with no offset says no instant to convert to.
  - Measured on 2026-09-24 against the results then in `bench/cache/`: the
    old rule gave the same counts on every third day of 2026, and the new
    one changes five outcomes, all from wrong to hit -- metascraper's dates
    on four news pages (UTC against a label in +02:00 to +09:00) and one of
    Sluicer's on trafilatura's set (`10.12.2022`). The scoreboards to
    regenerate: news and trafilatura's set, whose numbers change, and the
    WCXB and as-served scoreboards, whose method text states the rule.
- Products: Zyte's `evaluate.py`, unchanged.
- SWDE (`bench/swde.py`): an answer is right when it equals one of the page's
  labels with spaces collapsed, the separators `: | , ; - – — > / · •` taken
  off both ends, and case folded, on both sides, for every tool alike. The
  labels' HTML entities are decoded first.
- Every tool is called for what the scoreboard asks: metascraper for its
  publication date, not its date, which puts the modification date first
  (fixed on 2026-09-24 after the first scoreboards had it wrong).

## The W3C JSON-LD tests in HTML

Fixed on 2026-09-25, while the harness was built and before its page was
first published. Building it, the readers' answers on eight of the pages were
read to learn what each returns, and the harness was run until PyLD, reading
the pages itself, was scored as the suite scores a processor: that is when
the page's loader began to keep a fragment, and to read the error code PyLD
wraps when it turns a document into RDF. The rules below were not changed by
the readers' results. No rule of Sluicer's was changed, and none is to be made
reading this suite's pages: the page is a conformance check, not a scoreboard
to tune to.

- **The suite.** `w3c/json-ld-api` at commit `ffdb326121ea`, its
  `tests/html-manifest.jsonld`, under the W3C Software and Document License:
  downloaded into `bench/cache/`, never vendored.
- **A reader** is given the page's bytes and its address (the suite's base
  IRI and the test's input, fragment included) and nothing of the test's
  options, since a reader takes none. Its answer, a list of values, or what it
  raised, is recorded as it is.
- **Processing.** PyLD, pinned in `bench/requirements/pyld.txt`, processes the
  answer as the document of the test's operation (expand, compact with the
  test's context, flatten, to N-Quads), with the test's `base` option or else
  the page's address as base, in JSON-LD 1.1's processing mode.
- **Comparison.** The suite README's JSON-LD object comparison: objects member
  by member, arrays in any order except a `@list`'s, values by strict
  equality, language tags case-insensitively; a flattened result is also
  right when it equals the expected one with every blank node label written
  alike and both are the same RDF graph; an RDF result by its canonical
  N-Quads (URDNA2015) against the expected file's.
- **A negative test** passes for a reader that answers nothing or raises, the
  two ways a reader refuses; any answer fails it.
- **The check on the harness.** PyLD reads every page itself with the test's
  options, through a loader that serves the suite from disk, and passes a
  negative test only by raising the test's error code. Every test PyLD fails
  is listed on the page.
- **Every failure** is given the first reason of these that holds: the test
  names a script by fragment; it wants the first script of several; it is a
  negative test the reader answered; the page sets a `<base href>`; the
  reader's answer is not the JSON the scripts hold; otherwise, the result
  differs.
- Sluicer's reader against extruct and against its own extruct interface are
  paired comparisons over the 50 tests, as above.

## SWDE's halves, and how often the held-out half is read

The sites were split before any full result was read, in commit `fc72378`
(2026-09-24): in each vertical, in alphabetical order, they alternate between
development and held-out. Rules are made reading the development half's pages
and errors only. The held-out half is scored, and read only as numbers:

| date | code | why |
|---|---|---|
| 2026-09-24 | 0.6.0 | the first scoreboard |
| 2026-09-24 | read-after-label, `4978927` (then `1b85481`, before a rebase) | whether it held beyond development |
| 2026-09-24 | 0.7.0 | the release's scoreboard |
| 2026-09-25 | 0.7.1 | the release's scoreboard |
| 2026-09-25 | 0.7.1, the same results scored again | its intervals and the paired comparison with Scrapling, first printed |
| 2026-09-25 | 0.8.0 | the release's scoreboard |
| 2026-09-25 | the 0.8 branch at `3f4435b` (`release-08` at `733b7ad`, its code unchanged by `--visible`'s scoreboards) | `bench/gate.py --require`: the shared cache held Sluicer's results of 24 September, before 0.7.1 |
| 2026-09-25 | 0.8.0 at `d5e8c10` | the documentation review, checking the README's numbers against the scoreboard |
| 2026-09-25 | 0.9.0 | the release's scoreboard |
| 2026-09-26 | 0.9.1 | the release's scoreboard |

The next reading is the release after 0.9.1. All ten camera sites were read
while the benchmark was built, before the split, so the held-out camera sites
are not a clean test; the scoreboard says so.

## `--visible`: made on WCXB's development split, measured on everything else

Fixed on 2026-09-24, before a line of it was written. The rules that read a
byline, a date or a title off the visible page are made reading only the
1,358 pages of WCXB's `dev` split, in the archive already pinned at
`c039d5e`, their labels, and Sluicer's answers on them. No scoreboard page is
read while they are made: WCXB's test split, the pages as served, the news
fixtures, trafilatura's set and Zyte's products are held out from
`--visible`'s rules -- not from the summary's, which were made on them, as the
first section says. When `--visible` is scored, each of them will show two
columns, what the page declares and what `--visible` adds; as of 0.7.1 none
does yet. A guess read off the visible page is never part of the summary, and
every invention it makes will be counted in its own column.

How it is scored was fixed on 2026-09-25, before `--visible` was run on any
scoreboard's pages: no guess on them had been read, nor any number made from
one.

- **The call.** Sluicer's harness (`bench/tools/sluicer_tool.py`) calls
  `extract(html, url=...)` as before, the call the scoreboards score and
  `bench/timing.py` times, and then, untimed, `extract(html, url=...,
  visible=True)`, and records its guesses of `title`, `author` and
  `published` beside the summary's answers. The second call's summary must
  equal the first's on those three questions; a page where it does not stops
  the run, since the summary would no longer hold only what the page declares.
- **The two columns.** "What the page declares" is the summary's answer,
  scored as before. "Declared, then what `--visible` adds" is, question by
  question, the summary's answer where it has one and `--visible`'s guess
  where it has none: a guess never replaces a declared answer. The guess of
  `modified` is not used.
- **The pages and the scorer** are each scoreboard's own, by `bench/score.py`:
  WCXB's 511 test pages; on the as-served scoreboard, its pages as served (their
  stripped copies are WCXB's own pages, which the WCXB scoreboard scores whole);
  the news pages; trafilatura's 851 annotated pages. Both columns print the
  hit rate and the share right when answering, each with its Wilson interval.
- **What `--visible` changed, counted apart.** The pages where it turned a
  silent miss into a hit, a silent miss into a wrong answer, and a correct
  silence into an invention. The last are `--visible`'s own inventions, in a
  column of their own beside the declared answers'.
- **The verdicts.** "Declared, then `--visible`" against what the page
  declares, and against every other tool the scoreboard runs, per field, on
  both rates, paired by page as the section on differences below fixes:
  with three other tools, 24 comparisons a scoreboard, uncorrected, read as a
  table.
- **Not floored.** `bench/gate.py` holds the summary's numbers; `--visible`'s
  are published and not held by a floor until a release adds one, in a commit
  of its own.
- **The rules stay as they are.** Nothing in `src/sluicer/visible.py` is
  changed on reading these numbers. A defect they show -- a crash, a guess
  that differs between runs -- is fixed with a failing test, named in its
  commit, and changes no rule.
- **No seconds.** The speed tables time `extract` without `visible`; no
  time of `--visible` is printed.

## Two more tools, beside the markdown and beside heal

Fixed on 2026-09-25, before either was run on a scoreboard's pages. Neither is
a dependency of Sluicer: each runs in an environment of its own, pinned with
its dependencies in `bench/requirements/`.

- **html-to-markdown** (`xberg-io/html-to-markdown`, MIT), 3.14.3 from PyPI,
  on Python 3.12, beside `sluicer.markdown` on trafilatura's set, where the
  main text is scored. Two outputs, its defaults otherwise, which convert the
  whole page and choose no main text: `convert(html).content`, its markdown,
  and `convert(html, ConversionOptions(output_format="plain")).content`, its
  plain text. It takes text, so a page's bytes are decoded as UTF-8 when they
  are UTF-8, otherwise by the charset its first 5,000 bytes declare, otherwise
  as windows-1252, a byte that does not decode replaced. Scored by the
  snippets as the other outputs are, on all 990 pages. Paired by page:
  `sluicer.markdown` against its markdown, and `sluicer.markdown` with its
  syntax taken out against its plain text, on precision, recall and F1.
- **anansi** (`mdowis/anansi`, Apache-2.0), the package `anansi-scraper`,
  which is not on PyPI, at commit `117fbe27b3d6` (tag `v1.2.0`), on Python
  3.12, on the drift pairs Scrapling is asked about and about the same item:
  the first item of A whose title and link are still on B. Its element on A
  is the innermost whose text is that title, or of several the one whose link
  is the item's; its selector is the one anansi writes for an element
  (`AdaptiveParser._tag_to_selector`). A capture's bytes are handed to it as
  they are, and BeautifulSoup, which it parses with, reads their encoding; the
  element on A is found by the same parse. `AdaptiveParser(db_path=...)`, a fresh
  store for each pair, is asked `extract(A, {"item": selector}, url=...)`,
  then the same on B, with the pair's address both times; no page-level
  property is named `item`, so its JSON-LD and Open Graph pre-pass answers
  nothing. Right when the text it returns is the title, compared as the drift
  page compares titles. It returns a value, not an element, so the item's
  link is not checked: a looser test than Scrapling's. Its decay (a selector
  unused for over seven days loses 1% a day, by the clock) cannot act here:
  A and B are replayed seconds apart, and the selector given is tried before
  any stored one. The page says where anansi healed -- the selector matched
  nothing on B -- and that it does not tell its caller when it does.

## Every tool on the same pages: title, author, date and the main text

Fixed on 2026-09-26, before any of the tools below was run on a page of the
sets below, and before `bench/tools_compare.py` was written. It makes one
page, `docs/scoreboard-tools.md`, that puts every tool people reach for to
turn a web page into its title, author, date and text on the same pages, as
served with their scripts, scored one way. What prompted it: on one blog post
built with Framer, one tool answered the date the site was last built, which
the page writes in an HTML comment, one kept the site's menu in its text, and
Sluicer missed the byline. One page is an anecdote; this is the count.

**The tools, each in an environment of its own**, pinned with its
dependencies in `bench/requirements/` (or the lockfile), on Python 3.12, given
the page's bytes and its address and nothing else:

| tool | version | what it is asked | install line printed |
|---|---|---|---|
| Sluicer | this checkout, editable, with trafilatura 2.2.0 for its `markdown` extra | `extract(html, url=...).summary`'s `title`, `author`, `published`; `sluicer.markdown.to_markdown(html, url=...)` | `pip install "sluicer[markdown]"` |
| Sluicer, declared then `--visible` | the same | the summary's answer, and where it has none the guess of `extract(..., visible=True)`, as every other scoreboard scores it; the text is Sluicer's | the same |
| trafilatura | 2.2.0 (`requirements/trafilatura.txt`) | `extract_metadata(html, default_url=...)`; `extract(html, url=..., output_format="markdown")` | `pip install trafilatura==2.2.0` |
| newspaper4k | 0.9.6 (`requirements/newspaper4k.txt`), network taken away, images off | `download(input_html=...)`, `parse()`: `title`, `authors`, `publish_date`, `text` (plain text: it writes no markdown) | `pip install newspaper4k==0.9.6` |
| markitdown | 0.1.8 from PyPI, base install (`requirements/markitdown.txt`) | `MarkItDown().convert_stream(bytes, stream_info=StreamInfo(extension=".html", mimetype="text/html", url=...))`: `.title` and `.markdown`; it answers no author or date | `pip install markitdown==0.1.8` |
| Scrapling | 0.4.15 with its `rag` extra (`requirements/scrapling-markdown.txt`), which its markdown needs | a `Response` of the bytes, status 200, and `.markdown(main_content_only=True)`, as its own site-to-markdown spider calls it; the title as that spider reads it, `<title>`'s text; it answers no author or date | `pip install "scrapling[rag]==0.4.15"` |
| metascraper | the lockfile in `bench/metascraper/` | its `title`, `author` and `date` rules, as the other scoreboards call them; it answers no text | `npm install metascraper@5.58.1 metascraper-title@5.56.2 metascraper-author@5.56.2 metascraper-date@5.56.2` |

Left out, and said so on the page: **Firecrawl**, whose service needs an
account and a key, and whose self-hosted form is a Docker Compose of several
services, not a package to pin in an environment like the others; **Scrapy**,
which has no reading of its own for a title, a date or a text, only the
selectors someone writes (the drift and SWDE benchmarks measure selectors);
**html-to-markdown**, a converter of whole pages already beside the markdown
on trafilatura's scoreboard.

Added while the harness was written, before it was run on any page:
Scrapling's fetchers build a `Response` with the charset the server sent, and
given bytes alone it reads them as UTF-8; so each page is handed to it as
text, decoded by the rule html-to-markdown is given above (`snippets.as_text`),
before the clock starts, as newspaper4k's page is decoded before it.

A tool that raises on a page answered nothing on it, and the raise is counted
apart. A question a tool does not answer (markitdown's and Scrapling's author
and date, metascraper's text) is not scored for it: the page prints a dash,
never a zero.

**The pages.** Only corpora already pinned here, whose labels were checked by
people, and scored with the scripts intact:

1. **As served**, the 360 WCXB test pages whose captures `realweb-manifest.json`
   pins, with WCXB's labels: title, author, date, and the main text, both whole
   (`main_content`) and as snippets it must hold (`with`) and boilerplate
   snippets it must not (`without`: navigation, footers, cookie banners). WCXB's
   labels were drafted with a language model and then reviewed by people in
   several passes, as its README says.
2. **trafilatura's evaluation set**, its 990 pages at the commit pinned in
   `bench/evaldata.py`, each with hand-written `with` and `without` snippets,
   and 851 with their title, author and date.
3. **One page added by hand**: the Framer blog post that prompted this
   comparison, `https://typesafe.ai/blog/introducing-system-one-models-and-jev`,
   as the Wayback Machine captured it at `20260922123749`, pinned by the
   SHA-256 of its bytes in `bench/tools-added.json`, where its labels are
   written by hand from the page a reader sees: its title, the byline's
   author, the date shown above the title (15 September 2026), six `with` and
   six `without` snippets. It is fetched into `bench/cache/`, never committed,
   and the run stops if its bytes no longer hash to the pin. One page carries
   no rate: it is printed apart, answer by answer, and pooled into nothing.

Not used: **WCXB's own copies** of the test pages, from which every `<script>`
was removed, so they are not pages as any server sends them (the served set
is the same pages whole); and **the news set**, whose labels are what fundus's
parsers read, not labels a person checked page by page. No new page is added
beyond the one above, and no label of the corpora is changed.

**The questions, and how an answer counts.**

- **Title, author, date**: `bench/score.py`, unchanged -- hit, wrong, silent
  miss with a label; correct silence or invention without one. Hit rate over
  the labelled pages and share right when answering over the answers given,
  inventions included, each with its Wilson interval.
- **Silent wrong**: an answer that is wrong or invented, given with nothing
  in the tool's own output to warn of it. The one warning any of these tools
  gives is Sluicer's `conflicts`: an answer to a question the page answers two
  ways that mean different things is flagged, and counted apart. A source or a
  provenance is not a warning. A guess of `--visible` is kept apart from the
  summary, but is counted like any other answer: it carries no warning. The
  page prints each tool's silent wrong answers per question, over the answers
  it gave, with their Wilson interval, and lists the first three per tool and
  question, by page id, with the label and the answer.
- **The main text**: every tool's text is first written as plain text by one
  function, the same for all -- a link or an image becomes its text, emphasis,
  heading and list marks, setext underlines, table bars and backslash escapes
  are taken out, spaces collapsed -- so that markdown is not scored against
  plain text for its syntax. Then:
  - **Snippets**, as trafilatura's evaluation counts them
    (`bench/tools/snippets.py`): a `with` snippet the text holds is found, a
    `without` snippet it holds has leaked, at most six of each per page.
    Precision, recall and F1 over the summed counts, each with a 95% interval
    bootstrapped over pages, on both sets.
  - **Boilerplate**: the share of pages kept clean, where no `without`
    snippet leaked, over the pages that have one, with its Wilson interval.
  - **Silent empty**: pages where the tool raised nothing and gave no text,
    or only spaces, though the page has `with` snippets. Counted per tool.
  - **The whole text** (the served set only, where WCXB writes it): word-level
    precision, recall and F1 against `main_content`, as WCXB's README computes
    them (lowercased `\w+` words, counted as a multiset), averaged over the
    pages, each with a 95% interval bootstrapped over pages. A page a tool gave
    no text for scores 0.
- **Paired comparisons**, as the section below fixes them: Sluicer, and
  Sluicer declared then `--visible`, against every other tool on every rate
  both answer (title, author, date by hit rate and by share right when
  answering; the text's snippet precision, recall and F1, the share of pages
  kept clean and the mean word F1), on the pages both scored, per set. No
  correction for making many; the page says how many it makes.
- **Seconds per page**: `bench/timing.py`, as fixed below, in one run of every
  tool on the 360 served pages, the timed call being everything the tool is
  asked above for one page (for Sluicer, `extract` and `to_markdown`; its
  `--visible` guesses untimed). Printed with each tool's install line, its
  packages and its install size.

**Not floored.** `bench/gate.py` is not given this page: its title, author
and date for Sluicer are already floored on the same pages by the served and
trafilatura scoreboards, and its main text is trafilatura's by design. A floor
is added, if at all, in a release's own commit.

**Sluicer's rules** were made while the pages of both sets were read (the
first section), and the page says so. No rule of Sluicer's is changed on
reading this page's numbers in the commit that first publishes it.

## The main text: made on WCXB's development split, measured on the scoreboards once

Fixed on 2026-09-26, before any rule below was written or run on a page. The
every-tool scoreboard found Sluicer's text level with trafilatura's, whose
extraction it is: on the served pages snippet F1 0.859 and pages kept clean
0.897, but recall 0.782, against 0.90 for markitdown and Scrapling, which keep
the menus (0.006 and 0.017 of pages clean). What follows says how
`sluicer.markdown.to_markdown`, the `markdown` command and the MCP
`page_markdown` may change to find more of the text without taking the menus
with it, on which pages that is decided, and how the result is read.

**The pages rules are made on**: WCXB's `dev` split, the 1,358 pages
`metadata.json` marks `dev`, in the archive already pinned at `c039d5e`, with
their labels (`with`, `without`, `main_content`) and every candidate's output
on them. They are WCXB's own copies, which lost many of their `<script>`s, so a
rule reading JSON-LD is measured only on the dev pages whose JSON-LD survived,
and the numbers say how many those are. No page of a scoreboard -- WCXB's test
split, its pages as served, trafilatura's set, the page added by hand, the news
fixtures -- is read while the rules are made, nor any tool's answer on one.

**The measure** (`bench/markdown_dev.py`, run from the checkout's
environment): each candidate's markdown on each dev page is written as plain
text by `bench/tools_compare.py`'s `plain`, the six first `with` and `without`
snippets of each page are counted by `bench/tools/snippets.py`'s `counted`, as
the served set is; printed are snippet precision, recall and F1 over the
summed counts, each with its interval bootstrapped over pages, the pages kept
clean with their Wilson interval, WCXB's mean word precision, recall and F1,
and the pages silently empty. Each candidate is compared with the 0.9.1 call
(`baseline`: trafilatura's markdown with links and tables, links resolved
against the page), paired by page, as the section on differences below fixes.

**The candidates**, measured one by one against `baseline`:

1. *Declared text.* The page's one record of type `Article` or a schema.org
   subtype of it (`NewsArticle`, `BlogPosting`, `Report`, `ScholarlyArticle`,
   `TechArticle`, `SocialMediaPosting` and theirs), from JSON-LD or microdata,
   carrying `articleBody` (or `text`). It is the page's main entity when it is
   the only such record carrying a body, and, when it names a `url` or
   `mainEntityOfPage` and the page's address is known, that address is the
   page's (scheme, a trailing slash and a fragment aside). It is written as
   markdown: a microdata body by converting its element, a JSON-LD body by
   converting it when it holds HTML markup, else as its paragraphs. Used first
   (`declared-first-R`) when it has at least R times the words of the
   extraction, R in 0.5, 0.8 and 1.0, else the extraction; used as a rescue
   (`declared-rescue`) only when the extraction has under half its words. A
   body ending in an ellipsis is truncated and never used.
2. *Recall.* trafilatura's `favor_recall=True` always (`recall`); only when
   the extraction has under X times the words of the recall extraction
   (`recall-if-short-X`, X in 0.5 and 0.7); or only when it has under X times
   the words of the page's main region's visible text (`region-X`, X in 0.5
   and 0.7): the first `<main>`, else the first `[role=main]`, else the page's
   one `<article>`, else `<body>`, without `script`, `style`, `noscript`,
   `template`, `nav`, `header`, `footer`, `aside`, `form` and `[hidden]`.
3. *A second extractor, as a rescue*: under the same trigger as `region-X`,
   the longer of the extraction and the text of trafilatura's own copy of
   readability or of jusText (both ship with trafilatura, so nothing is added
   to the install), written as markdown by Sluicer's converter
   (`readability-X`, `justext-X`).
4. *Precision*: `include_comments=False` (`no-comments`), and
   `favor_precision=True` (`precision`), for reference.
5. *The heading*: `# ` and the page's `<h1>`, the only one, before the text
   when the text does not already hold it (`h1`), on top of `baseline`.

**What is kept.** A candidate replaces `baseline` when on the dev pages its
snippet F1 is called better by the paired comparison, and its pages kept clean
are not called worse and are not more than 0.010 below `baseline`'s. Of several
that pass, the one with the highest F1. Combinations of passing candidates, and
any rule added after reading the dev pages' outputs, are recorded here before
they are measured, and pass the same test against `baseline`. The `h1` rule is
kept unless it is called worse on F1 or on pages kept clean: it is about the
markdown being right, not about the score.

**Added on 2026-09-26, after the first run of the candidates above on the
dev pages and before any of these was run.** That run found every candidate's
gain at most 0.011 of F1, and, reading the dev pages' misses only, that of the
6,044 `with` snippets 781 are in the page's own text and left out by the
extraction, on 378 pages, often a few paragraphs, a nested list or a card of
a region whose rest was kept. So:

6. *The extraction's own region* (`container-K`, K in 1.25, 1.5 and 2.0): the
   blocks of the extraction of six words or more are found in the page, by
   their first words, in the text of its elements; the deepest element that
   holds four in five of those found, when it is not `<body>` or `<html>`, is
   written as markdown by Sluicer's converter, without images and without
   `nav`, `aside`, `footer`, `form`, the ARIA roles `navigation`, `banner`,
   `contentinfo`, `complementary` and `search`, and elements whose class or id
   names a share, social, related, comment, newsletter, subscribe, cookie,
   breadcrumb, sidebar, advert, promo, sponsor, popup or modal box. It
   replaces the extraction when it holds at least the extraction's words and
   at most K times them; otherwise the extraction stands.
7. *The heading, when it is the title* (`h1-titled`): as `h1`, only when the
   `<h1>` and the title the page declares (the summary's) are one, the shorter
   within the longer, compared as `bench/score.py` compares titles.

And in `full`, `<noscript>` is kept, without the images in it: a reader that
runs no script is shown it, and a forum written for such readers keeps its
posts there. It is still chosen by nothing.

**`full`**, the whole page as markdown -- the body with `script`, `style`,
`noscript`, `template`, `svg`, `iframe` and `[hidden]` taken out, links and
images resolved against the page -- is an option, not a candidate for the
default: it is measured on the dev pages to be described, and chosen by
nothing.

**The scoreboards, once, at the end.** With the code chosen above committed,
`bench/tools/compare_sluicer.py` is run on the served pages, trafilatura's set
and the page added by hand, from the checkout's own environment, whose
trafilatura and its dependencies are exactly the pins of
`bench/requirements/trafilatura.txt`, since `uv run` is not used on this
branch. The other tools' results are those of v010-bench's run (`ed3b378`),
reused as they are. Scored by `bench/tools_compare.py`'s functions: snippet
precision, recall, F1, pages kept clean and word F1, each with its interval,
and Sluicer's paired comparisons with trafilatura, newspaper4k, markitdown and
Scrapling on them. The numbers are reported whatever they are, and no rule is
changed on reading them; if they are read more than once, the reason is written
here.

## How sure a number is, and how a difference is called

Fixed on 2026-09-24, before any interval or verdict was computed on a
scoreboard's results. `bench/stats.py` computes both, and its tests hold it to
hand computations.

- **A rate.** Every hit rate and share right when answering a scoreboard
  prints carries its 95% Wilson score interval. For k hits in n trials,
  p = k/n and z = 1.959963984540054, the normal's 97.5th percentile:
  centre (p + z²/2n) / (1 + z²/n), half-width
  z / (1 + z²/n) · √(p(1 − p)/n + z²/4n²). Wilson rather than p ± z·√(p(1−p)/n),
  since it stays inside 0 and 1 and is not zero wide at either, where several
  rates sit (the news dates are 1.000 right when answering). It is printed
  beside the rate, its bounds to two places rounded outwards, the lower down
  and the upper up, so what is printed always holds what was computed:
  `0.727 (0.68–0.77)`. A rate over no trials has no interval.
- **The trials are pages**, taken as independent: a hit rate's trials are the
  labelled pages, a share's the answers. Where they are not independent the
  interval is bootstrapped over what is: over sites for SWDE, since one
  extractor is learnt per site and its pages stand or fall together; over
  pages for trafilatura's main-text snippets, several of which sit on one page.
  A bootstrapped interval is the percentile interval below.
- **A difference.** Sluicer against another tool on the same pages, a page as
  served against the same page as WCXB kept it, and Sluicer today against the
  baseline its floors were written from are paired comparisons: both sides
  are scored on the same pages, so the pages are resampled together.
  - 10,000 samples of n pages drawn with replacement from the n scored, by
    Python's `random.Random(20260924).choices`, the pages listed in the order
    of their ids. Every comparison starts again from the seed, so each can be
    reproduced alone, whatever else the page compares.
  - On each sample the statistic is recomputed: the difference of the two hit
    rates, of the two shares right when answering, of two F1s (products, by
    Zyte's evaluator's own matching and formula), or of two mean F1s over
    sites (SWDE), always Sluicer's minus the other's, the served page's minus
    the stripped one's, today's minus the baseline's. A rate over no trials
    in a sample counts 0, as `bench/score.py` counts it.
  - The interval is the 95% percentile interval: of the 10,000 differences in
    ascending order, the 251st and the 9,750th.
  - The verdict: **better** when the interval's lower bound is above zero,
    **worse** when its upper bound is below zero, **inconclusive** otherwise,
    a bound of exactly zero included. A scoreboard's prose calls Sluicer ahead
    of or behind a tool only where the verdict does, and names an
    inconclusive difference as one.
  - No correction for making many comparisons. A scoreboard makes eighteen,
    three fields by three other tools by two rates; where the tools did not
    differ at all, about one in twenty would still be called better or worse.
    The verdicts are read as a table, not one at a time, and each page says
    so.
- Zyte's evaluator prints its own bootstrap standard deviation of each F1
  (1,000 resamples, seed 42); that ± is Zyte's and is kept as it is. The
  paired comparison beside it is this file's.

## How a second is measured

Fixed on 2026-09-24, after commit `b8f525e` re-timed Sluicer alone "on a
quieter machine" and published its new time beside the other tools' old ones.
`bench/timing.py` measures, and a generator publishes no second it did not
measure this way.

- Every tool in a table is timed in one run of `bench/timing.py`, on one
  machine, on the same pages: five rounds, each running every tool once, the
  tools' order turned by one place each round, so that a machine that slows
  down weighs on all of them.
- Each run is a fresh process in the tool's own environment. It reads every
  page once untimed, a warm-up that is thrown away, then times one pass over
  every page, the extraction call only.
- Printed: the median of the five timed passes, the fastest and the slowest
  beside it; pages per second is the pages over the median. Peak memory is
  the largest peak resident size (`getrusage`) of the five processes.
- Written on the page: the day it was measured, the platform, the CPU model,
  its cores and the machine's memory, the Python version, each tool's version,
  and the commit of this checkout.
- A generator refuses to publish a timing that is not all one run: a tool of
  its table missing from the record, a tool timed in another run than the
  others, a tool's version other than the one whose answers the page scores,
  a commit other than the one the page names, or a tree with uncommitted
  changes. A timing is reused only when none of these holds.
- SWDE takes 13 minutes of one pass for Sluicer and 28 for Scrapling; five
  rounds of a warm-up and a timed pass would take nearly seven hours, so its
  scoreboard prints no seconds. The drift benchmark prints none either: its
  run time is mostly reading the archive's captures.

## What counts as worse

`bench/floors.json` holds, for every scoreboard, Sluicer's hit rate and share
right when answering per field, its inventions, the products' F1s, SWDE's
mean F1 per half and its silent wrong answers; `bench/floors-pages.json`
holds the outcome of every page (every site-attribute for SWDE) the floors
were written from, the baseline. `uv run bench/gate.py --require` pairs
today's outcomes with the baseline's, page by page, and a floor is breached
when either holds:

1. **The drop is significant**: the paired comparison above calls today
   worse than the baseline. However small, the pages that got worse
   outnumber those that got better by more than resampling explains.
2. **The drop is past the floor's tolerance**: a rate or an F1 more than
   0.010 below its floor, or a count of inventions or silent wrong answers
   above its ceiling by more than 1% of what it is counted over (the pages
   scored; SWDE's labelled page-attributes of that half), whatever the
   comparison says, so a large change on few pages is never waved through
   as inconclusive.

A number past its floor but within the tolerance and not called worse is
reported as held within noise, and passes. The reason: Sluicer is
deterministic, so a number moves only when pages change outcome, and what the
gate asks is whether a change makes Sluicer worse beyond the pages that
happened to be sampled. On these corpora a page is 0.1 to 0.4 points, and the
Wilson interval of a rate over 500 pages is about eight points wide; a floor
missed by one page traded for another says nothing, yet it made a release
choose between failing and `--allow-regression`, and a gate lowered by hand
each time is no gate. The tolerance bounds what such trades can add up to:
`--raise` never lowers a floor, so small drops one after another can never
take a number more than 0.010 below it. `--raise` rewrites a scoreboard's
baseline only when every one of its numbers is at or above its floor (or with
`--allow-regression`), so a drop within the tolerance is compared with the
outcomes before it, not with itself. The gate is run after every scoreboard
before a release is tagged; floors rise with `--raise` when the numbers do,
and are lowered only with `--allow-regression`, in a commit that says why.

## The state of declared data: fixed before a WARC was read

Fixed on 2026-09-25, before any WARC file of the sample was downloaded and
before `bench/declared_report.py` was written. `docs/state-of-declared-data.md`
counts what pages declare about themselves on a sample of Common Crawl; this
says which sample, what a page is, and what is counted, so that nothing is
chosen after the counts are seen. A change to any of it is made in its own
commit, which says whether it was made after the counts were read.

**The crawl.** The first crawl listed in
<https://index.commoncrawl.org/collinfo.json> on 2026-09-25 whose
`warc.paths.gz` is published on `data.commoncrawl.org`: `CC-MAIN-2026-39`
(4 to 17 September 2026), the listing's `last-modified` 19 September 2026. The
listing is pinned by its SHA-256 in `bench/declared-manifest.json`.

**The files.** Four WARC files, chosen from the listing by position alone,
before any is opened: with the listing's N lines in the order it gives them,
the lines at 0-based index ⌊(2k+1)·N/8⌋ for k = 0, 1, 2, 3, the middle of
each quarter. Each is pinned by its path, size and SHA-256 in the manifest,
and the script stops if a file no longer hashes to its pin. They are
downloaded from `https://data.commoncrawl.org/` one after the other, never two
at once, with a pause of ten seconds between files, retrying with backoff on
503 and 5xx, under a User-Agent that names Sluicer and its repository.

**A page.** A WARC `response` record whose HTTP status is 200 and which
`sluicer.warc.read_warc` reads as HTML (its `Content-Type`, else Common
Crawl's `WARC-Identified-Payload-Type`, else how its body starts). Every other
record is counted by the reason it was left out, never silently dropped. A
record Common Crawl truncated (`WARC-Truncated`) is a page, as the crawler
kept it, and how many were truncated is reported.

**The reading.** Each page is read once, as `sluicer.extract` reads it, with
the headers it was served with, `microformats=True`, `induce=False` and
`visible=False`, by the Sluicer of this checkout; the last commit that touched
`src/`, and the versions of lxml, libxml2 and mf2py, are written into the
counts. Nothing is sampled within a file: every page is read.

**What is counted, per page.**

1. Which of Sluicer's readers found something (`Extraction.sources`): JSON-LD,
   microdata, microformats, RDFa (Lite, without OpenGraph's tags), Dublin
   Core, OpenGraph, the Twitter card, HTML's own meta names; and the pages
   with any of the first four, the vocabularies about things.
2. The schema.org types of the records (top 25, by pages declaring them). For
   JSON-LD also every typed node in every block as written, nested ones
   included, before references are resolved (top 20, by nodes).
3. Merging: pages with records from two or more of the vocabularies about
   things, and of those, the pages where one record holds fields from two or
   more of them.
4. Conflicts (`Extraction.conflicts`), per summary question: of the pages the
   summary answers it on, how many declare another answer that means
   something else; and which two readers disagree, most often.
5. JSON-LD blocks (`<script type="application/ld+json">`, not empty): how many
   are JSON as `json.loads` reads it by default, NaN and Infinity refused;
   how many more read as written once a raw control character inside a
   string is allowed; how many more Sluicer's lenient reader
   (`sluicer.declared.jsonld._parse`) recovers; how many are lost.
6. Normalisation: for the summary's `published`, `modified`, prices,
   `currency` and `gtin`, how many answers `Extraction.normalised` reads; for
   a GTIN, whether it has a GTIN's shape (8, 12, 13 or 14 digits once spaces
   and hyphens are dropped) and whether its check digit is right; the ten
   commonest shapes of the dates and prices that were not read (every digit
   written 9, every letter a).
7. `links`: a canonical, a canonical conflict, a canonical that is the page's
   own address exactly, `hreflang` alternates and `x-default`.
8. `rights`: `<meta name="robots">` and its directives, a crawler named in
   its place, `X-Robots-Tag`, TDMRep's `tdm-reservation` and `tdm-policy` in
   the page and in the headers, `rel=license`.

The sample itself is described by its pages, distinct hosts, top-level
domains and truncated records.

**Intervals.** Every rate is given with its 95% Wilson score interval, over
pages. Common Crawl takes many pages from one host, so pages are not
independent and the intervals are narrower than the sample's real
uncertainty; the report says so, and gives for the vocabularies the share of
hosts too (a host counts when any of its pages declares it).

**The comparison.** Only with what Web Data Commons publishes for the same
measure, from its latest extraction, the October 2024 Common Crawl
(`CC-MAIN-2024-42`), as its statistics page
<https://webdatacommons.org/structureddata/2024-12/stats/stats.html> gives it
on 2026-09-25: the share of parsed HTML pages with any triples, the pages per
format (embedded JSON-LD, microdata, RDFa, microformats' hCard), and the
JSON-LD classes by entities. WDC reads with Any23, full RDFa and
microformats1, on a crawl two years older; the report puts these beside
Sluicer's numbers, never inside them.

**Added after the counts were read** (2026-09-25, the one change so far). The
first count found microformats on nearly a third of the pages, four times Web
Data Commons' hCard, and among its commonest types `h-full` and `h-auto`:
Tailwind's and Bootstrap's height classes, which microformats2's parsing
rules take for roots, since any class of the form `h-` and letters is one.
So the microformats count is split, and the pages with any vocabulary about
things are counted again with microformats only where they are one of the
thirteen vocabularies the microformats wiki lists as microformats2's
(<https://microformats.org/wiki/microformats2#v2_vocabularies>, read on
2026-09-25: `h-adr`, `h-card`, `h-entry`, `h-event`, `h-feed`, `h-geo`,
`h-item`, `h-listing`, `h-product`, `h-recipe`, `h-resume`, `h-review`,
`h-review-aggregate`). A page with microformats is counted as one with a
record of one of those types, one whose records are all of other types, or
one whose roots gave no field at all; and the commonest microformats types
are listed. Nothing else changed, and the first count's other numbers stand.

**Corrected after the counts were read** (2026-09-25, after 0.9.0's review).
Five places where the script did not do what this section fixed, each put
right to what it says, none chosen by what it moved: every WARC record left
out is counted by why, the records that are no page (`request`, `metadata`,
`warcinfo`) by their kind, where they were dropped unsaid; item 2's types are
schema.org's, where every reader's were counted, microformats' roots and
other vocabularies' addresses among them; a JSON-LD context's term
definitions and a value object's datatype are no typed nodes; a block of
JSON `null` is valid, not lost; and the pages declaring `tdm-reservation` are
counted one by one, not summed from its five commonest values. Item 3's
merging counts keep every microformats root, as the first count did, since
the split above was added for the pages with any vocabulary alone; the
report says so where it gives them.
