# Changelog

Dates are the day the work landed. Anything not listed here did not happen.

## Unreleased

### Added
- A fetch ladder that starts at plain HTTP and climbs to a browser only when a
  measurement says the cheap rung brought back a refusal, a challenge or a
  skeleton. Every climb is recorded with the reason that forced it.

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
