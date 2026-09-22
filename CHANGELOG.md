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

- Structure induction: `extract(html, induce=True)` reads a page that declares
  nothing by finding the shape it repeats and returning one record per
  repetition. Fields are named by the path down to them, repeated siblings are
  numbered rather than dropped, and every field carries `source="induced"` so an
  inference is never mistaken for a declaration. Induction runs only where the
  page declared nothing about its own subject.
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

### Fixed
- Bytes are decoded the way a browser decodes them, not the way libxml2 guesses.
  libxml2 commits to Latin-1 at the first non-ASCII byte it meets, so every UTF-8
  page whose `<title>` came before its `<meta charset>` -- the Guardian's article
  template among them -- and every UTF-8 page declaring no charset at all came
  back as mojibake in every field, from `sluicer extract page.html` and from
  `extract(bytes)`. A fetched page was unaffected, because it arrives as text.
- Induction reads the whole listing. Members were compared by the classes of
  everything inside them, so a rating written as `p.star-rating.Three` or a
  quote with five tags instead of two made a new kind of row: books.toscrape.com
  gave 6 of its 20 books and quotes.toscrape.com 3 of its 10. A member now
  matches its own tag and classes exactly and its inside loosely, by the tag
  paths it shares with the first member: 20 of 20 and 10 of 10, with Hacker News
  still 30 of 30.
- Induced field names no longer carry classes a build tool generated
  (`dcr-1t2r5md`, `css-1x2y3z`, `sc-bdVaJa`), which change on every deploy; a
  CSS module keeps the part a person wrote. A wrapper around several children,
  or around children and separators, no longer repeats their text as a field of
  its own.

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
- An element whose whole text is its children's no longer carries a text fact of
  its own, so a wrapper around a single value stops reporting that value twice.
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
