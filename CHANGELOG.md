# Changelog

Dates are the day the work landed. Anything not listed here did not happen.

## Unreleased

### Added
- A fetch ladder that starts at plain HTTP and climbs to a browser only when a
  measurement says the cheap rung brought back a refusal, a challenge or a
  skeleton. Every climb is recorded with the reason that forced it, and the
  reasons reach the user.
- `sluicer extract` now takes a URL as well as a path. Fetching needs the
  optional extra: `uv pip install 'sluicer[fetch]'`.
- `load()` and `extract()` accept bytes, so a document's own encoding
  declaration wins over a guess.
- Continuous integration: the suite on four Python versions, a build check, a
  job proving the base install imports without the fetch extra, and one that
  removes the socket entirely and runs the suite to prove no test touches the
  network.
- `docs/field-survey.md`, a reproducible count of 1,926 repositories in this
  field, and `AI_POLICY.md`.

- `to_markdown()` and `sluicer markdown`, which return a page's main content as
  markdown with the boilerplate gone, under the `markdown` extra.
- An MCP server and the `sluicer-mcp` command, exposing three tools to any agent
  that speaks the protocol, under the `mcp` extra.

### Changed
- A bad argument to `sluicer extract` now exits 1 with our own message rather
  than exiting 2 with click's. A missing file and a directory are both covered.

## 0.0.1 - 2026-09-22

The first slice: read what a page already declares, and say where every value
came from.

### Added
- Readers for JSON-LD, microdata and OpenGraph.
- A merge that folds records across vocabularies while keeping two products on
  one page apart, with per-field provenance.
- `sluicer.extract()` and the `sluicer extract` command.
- `docs/known-limits.md`, stating where the project stops.
- A test that fails the build if a model client or a network library is ever
  imported into the package.
