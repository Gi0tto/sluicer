# What is stable

Sluicer is Beta, and 1.0 is not out. This page says which parts you can build
on now, which may still change, and how a change reaches you.

## Stable before 1.0

These change only through the deprecation policy below: a release that would
remove or rename one of them warns first.

- **`extract()` and `Extraction`.** The function's parameters, and the fields
  of what it returns: `url`, `summary`, `normalised`, `conflicts`, `records`,
  `sources`, `links`, `rights` and `visible`, with `SummaryField`, `Record` and
  `Field` as the [Python reference](reference/python.md) documents them.
- **The summary's questions.** The 25 names in `sluicer.summary.FIELDS` --
  `title`, `description`, `url`, `image`, `author`, `published`, `modified`,
  `language`, `site_name`, `publisher`, `type`, `price`, `price_regular`,
  `price_low`, `price_high`, `currency`, `availability`, `brand`, `sku`,
  `gtin`, `mpn`, `rating`, `rating_best`, `rating_count`, `breadcrumb` -- and
  what each answer carries: its value, its source, its key and where on the
  page it was declared. Questions may be added. Which record answers a
  question is Sluicer's rules, and those improve from release to release: the
  answer a page gives may change, the shape of the answer does not.
- **The extractor file and its exit codes.** A file `sluicer compile` writes
  is read by every later release: the `format` field says which version it
  is (1, or 2 for a field read after its label), and a release refuses a
  format newer than it knows rather than reading it wrong. `sluicer run`
  exits 0 when every page kept to the extractor and 3 when one broke it;
  `sluicer heal` exits 3 when a field, a summary answer, a type or the listing
  was lost; 2 is a page that could not be read. See [Extractors](extractors.md).
- **The MCP tools.** The eleven tool names -- `extract_declared`,
  `page_markdown`, `fetch_page`, `compile_extractor`, `run_extractor`,
  `heal_extractor`, `audit_page`, `read_feed`, `map_site`, `crawl_site`,
  `extract_many` -- their
  parameters, and the answer fields the [MCP reference](reference/mcp.md)
  documents, `ok` and the error codes among them. Fields and error codes may
  be added, so an agent should ignore what it does not know; `ok` keeps its
  meaning: true exactly when the answer can be used as it is.

## Experimental

These work, are tested and are measured where a benchmark exists, and may
still change shape in a minor release, said in the changelog, without a
release of warning first:

- `sluicer crawl`, `map` and `batch`, and `sluicer.crawl`
- `sluicer warc` and `sluicer.warc`
- `sluicer feed` and `sluicer.feeds`
- `sluicer audit` and `sluicer.audit`, whose findings follow Google's
  documentation as it changes
- `sluicer diff` and `sluicer.diff`
- `--induce` and `sluicer.induce`: which rows are read from a page that
  declares nothing
- `--visible` and `visible=True`: the guesses, their rules and the `rule`
  names they carry
- the HTTP API, `sluicer serve`: its paths, statuses and the OpenAPI document
  it serves
- the configuration file: where it is looked for, and which keys it takes
- `sluicer.aextract` and `sluicer.fetch.afetch`, which follow `extract` and
  `fetch`'s parameters as those change

The command line's output for a person -- `inspect`, the messages on stderr,
the order of `--help` -- is not an interface; its JSON output and exit codes
follow the parts above.

## How a change reaches you

- **Deprecation.** Before a stable part is removed or renamed, one minor
  release keeps it working and warns: a `DeprecationWarning` in Python, a line
  on stderr from the command line, a note in the tool's description for the
  MCP server. The changelog lists it under **Deprecated** in that release and
  under **Removed** in the release that removes it. 0.8 can remove what 0.7
  deprecated, never what it did not.
- **Every change is in the [changelog](changelog.md)**, under the release it
  shipped in, and what is not there did not happen.
- **After 1.0** the stable parts follow semantic versioning: removing one
  needs a major release.

## Who keeps it

Sluicer is written and maintained by one person, on a best-effort basis:
there is no support contract, no guaranteed response time and no promise of
a release date. Fixes ship in the latest release only. Security reports are
answered first ([Security](security.md)); issues and pull requests as time
allows. Pin the version you depend on, and read the changelog before you
move.
