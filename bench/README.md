# The scoreboard

How often Sluicer's `summary` gets a page's title, author and publication date
right, measured beside trafilatura, metascraper and newspaper4k on a public
annotated corpus. The results, losses included, are in
[`docs/scoreboard.md`](../docs/scoreboard.md). This directory is how they are
made, so anyone can make them again.

```bash
uv run bench/run.py                    # everything, then docs/scoreboard.md
uv run bench/run.py --tools sluicer    # rerun one tool, reuse the others' results
```

It needs `uv` and, for metascraper, Node with `npm`. The first run downloads
the corpus, about 150 MB; after that it runs offline, in about two minutes.

## What is measured

The 511 pages of the test split of [WCXB](https://github.com/Murrough-Foley/web-content-extraction-benchmark),
the Web Content Extraction Benchmark by Murrough Foley, published under
CC-BY-4.0. `corpus.py` downloads it at one pinned commit into `bench/cache/`,
which is never committed. Its labels are `title`, `author` and `publish_date`,
and they are left empty on purpose where a page has none: author on 63% of the
pages, date on 48%.

**WCXB removed every `<script>` from its pages.** JSON-LD, the vocabulary
Sluicer reads first, is therefore invisible here, and Sluicer is measured
without its strongest reader. The scoreboard says so above its numbers and
counts it on every run.

## How it is scored

`score.py`, four outcomes per field. With a label: **hit**, **wrong**, or
**silent miss**. Without one: **correct silence**, or **invention**. Hit rate is
hits over the labelled pages; right when answering is hits over every answer
given, inventions included.

- title: lowercased and whitespace collapsed; equal, or one contains the other
  and the shorter is at least 0.6 of the longer.
- author: letter runs, lowercased, less *by, and, the, staff, team, editor(s),
  writer, de, von*; a hit when the shared tokens cover half the label's and a
  quarter of the answer's, so a byline paragraph containing the name is not.
- date: both parsed with dateutil; a hit when the calendar dates are equal.

## How each tool runs

Each in an environment of its own, holding only what it needs, pinned with its
dependencies, given the same bytes and the page's address. Only the extraction
call is timed.

| tool | environment | call |
|---|---|---|
| Sluicer | this checkout, installed editable, base install | `extract(html, url=...).summary` |
| trafilatura | `requirements/trafilatura.txt` | `extract_metadata(html, default_url=...)` |
| metascraper | `metascraper/package-lock.json`, `npm ci` into the cache | the `title`, `author` and `date` rules |
| newspaper4k | `requirements/newspaper4k.txt` | `download(input_html=...)`, `parse()`, images off, no network |

Changing a pin, the corpus commit or a matching rule changes the scoreboard,
and belongs in the same commit as the regenerated `docs/scoreboard.md`.
