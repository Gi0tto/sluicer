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

- Readers for Dublin Core (`DC.` and `DCTERMS.` meta tags) and RDFa Lite
  (`vocab`, `prefix`, `typeof`, `property`, `resource`), both written in `lxml`
  alone so the base install gains no dependency. `extract()` now runs six
  readers with a stated order of precedence -- JSON-LD, microdata, RDFa, Dublin
  Core, OpenGraph, the Twitter card -- and `sources` names each one that fired,
  in that order. Measured on 2026-09-22 across twenty pages, the added
  vocabularies unlock no page the old ones did not already cover; what they buy
  is compatibility with `extruct`, which reads six.
- A microformats2 reader, behind `sluicer[microformats]` and off by default:
  `extract(html, microformats=True)`. It is the seventh vocabulary and sits
  third in precedence, after microdata and before RDFa, because it describes a
  thing on the page rather than the page. Parsing is `mf2py`'s, which costs
  twelve packages against a base install of three; without the extra the call
  raises `MicroformatsExtraMissing`, whose message names the install line. A
  nested item keeps both of its facts under the convention induction already
  uses for an anchor -- `author` for the name, `author@url` for the link -- and
  one that carries neither is skipped rather than guessed at. Measured on
  2026-09-22 across twenty live pages, microformats appeared on exactly one,
  which carried OpenGraph too: this buys compatibility with `extruct`, not
  reach.

- An identifiable user agent on every request, `robots.txt` obeyed by default,
  and `RobotsRefused` when a site says no. The answer is cached for a day, and a
  robots file that answers 5xx is treated as a full disallow, per RFC 9309.

### Changed
- The Twitter card is a reader of its own, and its fields say
  `source="twitter"`. `read_opengraph` used to return `og:` and `twitter:` alike
  and label everything `opengraph`, so a value a card had won named a reader
  that had not won it, and a key the two share -- `title`, `description`,
  `image:alt` -- went to whichever tag the page's author happened to type first.
  OpenGraph now runs first, the card fills what OpenGraph left empty, and the
  rule is stated rather than emergent.
- `merge()` takes seven findings rather than three, so a caller invoking it
  directly has to widen the call. `extract()` is unaffected. The seventh,
  `microformats`, is an empty list on every call that did not ask for the
  reader: a reader that is off is a reader that found nothing.
- The stealth rung has left the automatic ladder. `fetch(url, stealth=True)` adds
  it back for a caller who wants it.
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
