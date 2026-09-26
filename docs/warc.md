# Reading web archives

Two ways in: a WARC file you hold, and a page as the Wayback Machine
captured it.

A WARC file (ISO 28500) is how web archives store a crawl: the Internet
Archive's, Common Crawl's, and whatever wget, Browsertrix or warcio writes.
Each page is kept as its server sent it -- status, headers, body -- so
Sluicer reads it the way it reads a page it fetched itself, headers included.

```sh
sluicer warc crawl.warc.gz                   # one JSON line per page
sluicer warc a.warc.gz b.warc > pages.jsonl  # several files, in order
gzip -dc crawl.warc.gz | sluicer warc -     # standard input
```

```python
from sluicer.warc import Skipped, extract_warc

skipped = Skipped()
for page, read in extract_warc("crawl.warc.gz", skipped=skipped):
    print(page.url, page.date, read.summary.get("price"))
print(skipped)  # "3 revisit, 40 not HTML, 2 status 4xx"
```

`sluicer.warc.read_warc` gives the pages without extracting them. Each one
is a `WarcPage` with its URL, status, headers and decoded body, plus the
record's id, date, payload digest and truncation.

Nothing is fetched. An archive is read as it stands. Download it on the terms
its archive sets.

## A page as it was

Any command that reads a URL -- `extract`, `inspect`, `markdown`, `audit`,
`diff` -- reads it from the Wayback Machine instead with `--at DATE`:

```sh
sluicer extract https://shop.example/p --at 2024-01      # the capture nearest to it
sluicer diff https://shop.example/p https://shop.example/p --at 2024-01
```

The archive answers with its capture nearest to the date, which can be years
away, so the answer says which capture it read, never just the date asked for:

```json
"fetch": {
  "rung": "archive",
  "status": 200,
  "archived": {
    "archive": "web.archive.org",
    "asked": "202401",
    "captured": "20240117093012",
    "url": "https://shop.example/p"
  }
}
```

- The capture is read in the archive's `id_` form, the page as it was served,
  without the archive's toolbar or its rewritten links. Its links resolve
  against the address captured, as on the site.
- The headers the site sent then come back from the archive as
  `x-archive-orig-*`, and are read under their own names, so a `Link`
  canonical, `X-Robots-Tag` and the charset count as for a live page.
- It is a fetch like any other: over plain HTTP, through the archive's
  robots.txt (absent, which allows everything), the 16 MiB bound and the
  refusal of private addresses, and a redirect is followed only within the
  archive. A page the archive never captured is an error that says so.
- In `diff`, `--at` is BEFORE's date and AFTER is read live, so the command
  above is what changed since then. `audit` of a capture reads no robots.txt
  or llms.txt: today's files say nothing about a page of last year.

From Python: `fetch_archived(url, "2024-01")`, after
`from sluicer.fetch.archive import fetch_archived`, gives the `Fetched` page, with `archived` saying which capture it is. For an agent, the
MCP tools `extract_declared` and `page_markdown` take `at`; a page never
captured answers `fetch_failed` with `retryable` false, since asking again
will not make the archive have held it.

On python.org, `sluicer diff https://www.python.org/ https://www.python.org/
--at 2019-01` finds the PEP feed that moved to peps.python.org since then.

## Each line

A line is what `sluicer extract` answers for one page, plus a `warc` object
that says where in the archive the page came from, and `visible`, which is
always there and always empty, `{}`: `sluicer warc` does not guess from the
visible page.

```json
{
  "url": "https://shop.example/p",
  "warc": {
    "file": "crawl.warc.gz",
    "record_id": "<urn:uuid:...>",
    "date": "2026-09-23T10:00:00Z",
    "digest": "sha1:...",
    "status": 200
  },
  "summary": {},
  "normalised": {},
  "conflicts": [],
  "records": [],
  "sources": [],
  "links": {},
  "rights": {},
  "visible": {}
}
```

`truncated` is added when the archive cut the body short, with the reason it
gives: `length`, `time` and so on. Such a page is still read, but it may be
missing whatever came after the cut.

The page's headers are read the way `extract(headers=...)` reads them:

- the `Content-Type` charset decodes the body;
- a canonical, `hreflang` alternates, and the next and previous pages from the
  `Link` header join the markup's;
- `X-Robots-Tag` and TDMRep's headers are reported in `rights["http"]`.

## What is a page

- **A `response` record** holds an HTTP answer. Chunked transfer and gzip or
  deflate content codings are undone. An archive that stored the body already
  decoded but kept the header, as some writers do, is read as it stands.
- **A `resource` record** holds a body alone, with no HTTP answer. Its
  `status` is null.
- **Anything else is not a page.** `request`, `metadata`, `warcinfo` and
  `conversion` records are passed over without being counted.

A page-like record that is not read is counted under its reason, and the
counts are printed at the end:

| reason | the record |
|---|---|
| `revisit` | the archive saying "the same as before", with no body |
| `not HTML` | a body declared as something else. With no `Content-Type`, the archive's `WARC-Identified-Payload-Type` decides, and failing that how the body starts. |
| `status 3xx`, `status 4xx`, `status 5xx` | a redirect or an error page, whose declarations are the error page's |
| `not HTTP` | a `response` record that holds no HTTP answer, such as Heritrix's DNS lookups |
| `not an HTTP response` | a block with no readable status line |
| `compressed with br` (or another coding) | a content coding Python cannot undo without an extra |
| `too large` | a body over the 16 MiB a fetched page may have, before or after inflating |
| `stray bytes between records` | a damaged boundary, typically a `Content-Length` a few bytes short. The reader passes over the stray bytes to the next record, as warcio does. |

A file may be plain or gzipped, one gzip member per record or one for the
whole file. A file that is not a WARC, or that breaks off inside a record,
ends the run with exit code 2 and the number of pages read before the break.
The pages before the break have already been written.

## Checked against warcio

The reader was run over the eleven sample WARCs that
[warcio](https://github.com/webrecorder/warcio) tests itself with, and its
pages were compared with warcio's own reading, body by body:

- **On nine files the two agree** on every HTML page's URL, status and
  decoded body. These include a chunked iana.org response, a resource record,
  a wget WARC with a bad target URI, and a truncated file.
- **On `example-bad-non-chunked.warc.gz`**, a single gzip member holding
  several records, warcio refuses the file. Sluicer reads its one page.
- **On `example-wrong-chunks.warc.gz`**, whose gzip members split a record
  in two -- its head in one member, its body in the next -- warcio returns an
  empty body. Sluicer reads the members as one stream and gets the page's
  full HTML.

It was also run on a WARC written by warcio's `capture_http` from five live
requests. All five were gzip-coded, and three were chunked as well. The four
HTML pages were read with their titles, and the favicon was counted
`not HTML`.
