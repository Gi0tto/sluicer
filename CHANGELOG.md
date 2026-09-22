# Changelog

Dates are the day the work landed. Anything not listed here did not happen.

## Unreleased

### Added
- `extract()` returns a `summary`: title, description, url, image, author,
  published, modified, language, site_name, publisher, type, price, currency,
  availability, brand and sku, one value each, chosen by fixed rules in a fixed
  order and each naming its reader and its key. `<title>`, `<html lang>` and
  `<link rel=canonical>` are read for it.
- Nested values reach the record whole: `Field.value` is the JSON the page
  declared -- an object keeps its `@type`, a list keeps its order, every leaf is
  text -- and a JSON-LD reference to another node on the page is replaced by
  that node, one hop deep and safe from cycles.
- `sluicer extract --induce`, `--microformats`, and on both commands
  `--stealth`, `--no-robots`, `--url`, and `-` for standard input.
- `fetch(..., allow_private=False)` refuses addresses off the public internet
  before any request and after any redirect, raising `AddressRefused`; the MCP
  server sets it unless `SLUICER_ALLOW_PRIVATE=1`. `FetchFailed` is raised when
  every rung failed, naming what each one said.
- The MCP server reports its version, `extract_declared` can induce, and
  `fetch_page` cuts a page at 200,000 characters and says so.
- Python 3.14 in the test matrix, issue forms, a Docker build in CI.

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
  robots file that cannot be read is treated as a full disallow, per RFC 9309.

### Fixed
- Bytes are decoded the way a browser decodes them. libxml2 commits to Latin-1
  at the first non-ASCII byte, so any UTF-8 page whose `<title>` came before its
  `<meta charset>` -- the Guardian's article template -- or that declared no
  charset at all came back as mojibake in every field.
- Three microdata or RDFa products on one page folded into one record, and a
  related product's SKU and price landed on the main product. A vocabulary now
  folds only into earlier vocabularies' records, one item per record.
- Microdata follows the WHATWG rules: `itemref`, several names in one
  `itemprop`, repeated properties as a list, every `itemtype` token, and the
  standard's full list of value attributes (`data`, `meter`, `video` and the
  rest). Properties are no longer lost on large pages, where lxml reuses the
  `id()` of freed elements.
- RDFa resolves terms through `vocab`, `prefix` and the initial context.
  Wikipedia's `typeof="mw:Transclusion"` produced eleven empty records, and
  OpenGraph tags under an `<html typeof>` became RDFa fields that switched
  induction off.
- JSON-LD with a raw newline inside a string, wrapped in a comment or CDATA,
  with a byte order mark or a trailing comma is read instead of dropped. A block
  nested past the parser's limit no longer raises out of `extract()`. Numbers
  keep the spelling the page wrote, and `NaN` is not a value.
- Microdata and RDFa addresses resolve against the page and its `<base>`.
  Content deeper than 256 elements is no longer dropped by libxml2. `OG:Title`
  and a tag whose `property` holds something else are read.
- The fetch no longer sends scrapling's `Referer: https://www.google.com/` or a
  Chrome TLS fingerprint. One try per rung and bounded timeouts replace three
  tries of thirty seconds.
- The ladder no longer climbs a small complete page or a 404, and a theme-color
  in an empty React shell no longer counts as delivered data. A failed climb
  returns what the cheaper rung had instead of a traceback.
- A redirect to another host is checked against that host's robots.txt. A
  robots.txt that cannot be read -- nothing answered, or a 5xx -- stops the
  fetch, per RFC 9309, reported as a failed fetch rather than as the site
  refusing us, and it is not remembered: a 503 used to keep a long-running
  server away from a site for a day.
- The CLI passed a file's path to the readers as the page's URL, so relative
  links resolved against the file name. A browser timeout was a traceback.
- The MCP tools answered a failed fetch with the SDK's bare "Error executing
  tool". They now return an error the agent can read.
- The Claude Code plugin loaded neither its server nor its skill.
- Hostile pages cost a bounded amount: microdata items that name each other
  with `itemref` were exponential (four of them, an estimated half hour), and
  thousands of JSON-LD references to one large node were copied each time
  (4 GB from a 119 KB page). Both now have a budget and a memory.
- A template placeholder such as `https://[domain]/p` raised a `ValueError`
  out of `extract()`; it is kept as written. A `<body` inside a comment in the
  head no longer ends the charset search. The CJK, Turkish and Thai charset
  labels decode as browsers decode them, and UTF-7 is refused.
- The address filter reads a host the way the client will: percent-encoded,
  octal, hex and short numeric hosts, a backslash before an `@`, and IPv4
  addresses inside IPv6 ones (mapped, compatible, NAT64) no longer pass.
- The summary takes price, currency and availability from one offer, prefers
  `name` over `headline` when only `name` is in the page's shown title
  (Wikipedia), and says which reader declared the `type`. Every record has a
  `source`. JSON-LD `@list` and `@set` are their items. An empty RDFa `vocab`
  resets the vocabulary.
- `HTTPS://` is an address at the command line and in the server.
- Records carrying no field are no longer reported.
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
- Exit codes follow grep: 0 found, 1 read but nothing declared, 2 could not be
  read. Errors used to exit 1, the same as a page that declares nothing.
- `Field.value` is `str | list | dict`, not always `str`, and microdata items
  nested in another are values of their parent rather than records of their own.
- `RobotsRefused` carries a `reason`. `robots_refusal()` says why;
  `robots_allows()` still says only whether.
- The Twitter card is a reader of its own, and its fields say
  `source="twitter"`. `read_opengraph` used to return `og:` and `twitter:` alike
  and label everything `opengraph`, so a value a card had won named a reader
  that had not won it, and a key the two share -- `title`, `description`,
  `image:alt` -- went to whichever tag the page's author happened to type first.
  OpenGraph now runs first, the card fills what OpenGraph left empty, and the
  rule is stated rather than emergent.
- `merge()` takes eight findings rather than three, so a caller invoking it
  directly has to widen the call. `extract()` is unaffected. The seventh,
  `microformats`, is an empty list on every call that did not ask for the
  reader: a reader that is off is a reader that found nothing.
- The stealth rung has left the automatic ladder. `fetch(url, stealth=True)` adds
  it back for a caller who wants it.
- An element whose whole text is its children's no longer carries a text fact of
  its own, so a wrapper around a single value stops reporting that value twice.
- A bad argument to `sluicer extract` now exits with our own message rather
  than with click's. A missing file and a directory are both covered.

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
