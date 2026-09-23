# Changelog

Dates are the day the work landed. Anything not listed here did not happen.

## Unreleased

### Changed
- A price's key is the path it was read at -- `Product.offers.price`,
  `Product.offers[1].priceSpecification[0].price` -- rather than
  `Product.offers` for every offer answer.
- An `AggregateOffer`'s `lowPrice` and `highPrice` answer `price_low` and
  `price_high`, new summary questions, and no longer a plain `price`: "from 19"
  is not a price of 19.

### Added
- A scoreboard on product pages (`bench/products.py`,
  `docs/scoreboard-products.md`): Zyte's product-extraction benchmark, 140
  pages as served with price, SKU and availability labelled by hand, scored by
  Zyte's own evaluator beside Zyte's and Diffbot's paid APIs and an extruct
  baseline. Price F1 0.750 against extruct's 0.685, availability 0.907 against
  0.626, SKU 0.527 against 0.537; the paid services, reading the visible page
  with trained models, are ahead on all three.
- `sluicer serve`, the MCP server's tools over HTTP, behind a new `api` extra
  (`starlette>=1.2`, `uvicorn>=0.31.1`, and the `mcp` extra). `POST
  /v1/tools/<name>` takes a tool's arguments as a JSON object and answers what
  the tool answers; `GET /v1/tools` lists the tools with their input and output
  schemas, and `GET /openapi.json` is generated from those same schemas. Built
  from the server `build_server` returns, through the SDK's own `list_tools`
  and `call_tool`, so a tool added there is served with nothing else to change.
  The status follows the answer: 200 for anything a tool answered, a page that
  drifted included, and a stated status for each error code. It listens on
  loopback and there answers only requests addressed to it; beyond loopback it
  needs `SLUICER_API_TOKEN` or `--allow-unauthenticated`. JSON bodies only,
  bounded at 16 MiB, a time budget per request, four calls at once, no CORS.
  `docs/http-api.md` says all of it; `tests/live/api_check.py` asks a real
  server over a real socket; the image serves it.

- `sluicer markdown --front-matter` (and `to_markdown(front_matter=True)`, and
  the MCP tool's `front_matter`): the markdown opens with a YAML block of the
  page's summary, normalised where it can be, and each answer's source, the
  way static-site generators and retrieval pipelines read a document's
  metadata. Every value is written as a JSON string, so nothing a page
  declares can break the block.
- `Extraction.rights`: what the page's own tags declare about how it may be
  used -- `<meta name="robots">` and its per-crawler forms (`googlebot`...),
  the unofficial `noai` and `noimageai`, and TDMRep's `tdm-reservation` and
  `tdm-policy` (a W3C Community Group report, not a standard) -- verbatim, and
  nothing when the page declares nothing, which is not the same as allowing
  everything. `sluicer inspect` says which.
- `Extraction.links`: what the page's `<link>` elements declare about where
  else it lives -- its canonical address, every `hreflang` alternate, its RSS,
  Atom and JSON feeds, `next` and `prev` (from `<a>` too, where pagination
  usually is), AMP, the web app manifest and oEmbed endpoints -- each address
  resolved against the page's base. WordPress's REST API, which every
  WordPress page declares as `rel=alternate type=application/json`, is not
  taken for a feed. Shown in `sluicer inspect` and in the MCP answer.
- `Extraction.normalised`: the summary's `published`, `modified`, `price` and
  `currency` read into ISO 8601, a decimal with a point and an ISO 4217 code,
  where the page's text leaves no doubt. The summary keeps what the page wrote.
  `03/04/2025`, `1,299` and `$` are each two things somewhere, so they have no
  normalised value. A date keeps its offset and is never moved to UTC. Also in
  the MCP answer and beside each answer in `sluicer inspect`.
- Six summary questions: `gtin` (from `gtin14`, `gtin13`, `gtin12`, `gtin8`,
  `gtin` or `isbn`, the key naming which), `mpn`, `rating`, `rating_best` and
  `rating_count` from the subject's `aggregateRating` -- never rescaled, so 8 of
  10 is 8 with 10 beside it -- and `breadcrumb`, the names of the page's last
  `BreadcrumbList` in the order of their `position`, joined with " > ".
- `normalised.gtin`, only when the check digit is right: 12 of the 17 GTINs on
  the scoreboard's pages as served are wrong, and a wrong one names another
  product. The GTIN the suite used for years was one of them.
- Facebook's `product:` Open Graph type (`product:price:amount`,
  `product:price:currency`, `product:availability`, `product:brand`,
  `product:retailer_item_id`), which Meta's catalogues read, answers price,
  currency, availability, brand and sku after the page's own offers.

### Fixed
- A product declared once per colour or size, as Zara declares it, or beside
  related products that carry no offer, as Argos does, was taken for a
  listing, and the page had no subject and no price. Records of one name are
  now one product, answering only what they all agree on -- the price, not
  the sku of one colour -- and the one record of a type that carries an offer
  is the subject. A price whose text holds two numbers (`71,91 € 79,90 €`) is
  no price and gives way to the next declaration. On two YETI pages the
  title is now the product's declared name, shorter than the heading WCXB
  labels, so the served scoreboard counts two titles fewer.
- The summary's price followed the page's order, so on markup Google documents
  it answered the wrong one: a strikethrough price or a member price listed
  before the active price was taken for the price, and an `AggregateOffer`
  wrapping its sellers' `offers` gave none. The price is now chosen by Google's
  merchant-listing rule -- an active price has neither a `priceType` nor a
  `validForMemberTier` -- and a strikethrough price of the same offer is
  `price_regular`. Currency and availability come from the offer the price
  came from. Found by the survey of other projects, with probes it wrote.
- A `<link rel=canonical>` in the body was taken for the page's own address, so
  a page's content could name another host as the page. Google accepts a
  canonical only in the head, and so does Sluicer now; two different ones in
  the head are reported as `links.canonical_conflict` and answer no `url`, as
  Google then uses neither.
- `compile` took page furniture for the listing on 6 of the drift benchmark's 25
  sites: GitHub's language menu of 491 links, old Reddit's sidebar lists, the
  paragraphs of one Hackaday post, page sections on the BBC and Ars Technica,
  and metacpan's three day-tables. Regions the page marks with an ARIA role
  such as `menu` or `navigation`, or hides, are now furniture; a group whose
  members are mostly another listing is sections, not rows; and classes that
  name one item, a position or a state (`id-t3_8gxz1`, `odd`,
  `category-reviews`, `has-post-thumbnail`) no longer split one listing into as
  many kinds as rows. All 25 now learn the listing a person would point at, and
  the benchmark still shows no silent failure and no false alarm.
- A numbered slot in the middle of a path -- the link in a row's second span --
  was held as a column, so a row with one item fewer, which renumbers the rest,
  failed a page of the same template. A numbered slot at any step is now a
  count, and the first slot of a group is held to some rows rather than every
  row.
- The `mcp` extra needs `mcp>=2.1`. On Python 3.10, mcp 2.0.0 and 2.0.1 cannot
  build the server at all: they refuse the `Required[...]` keys of its output
  schemas. The suite fakes the SDK, so the floors job, which installs 2.0.0 on
  3.10, had never built it for real.

## 0.3.0 - 2026-09-23

### Changed
- **MCP answers, breaking for 0.2.0 clients.** Every answer carries `ok`, true
  exactly when it can be used as it is. An error is `{"ok": false, "error":
  {"code", "message", "retryable"}}`, with `url` or `extra` when there is one;
  the codes are `missing_extra`, `refused_by_robots`, `refused_address`,
  `fetch_failed` (the only retryable one), `too_large` and `bad_input`. Before,
  each kind was its own top-level key. `run_extractor` is not ok for a page
  that drifted, and `heal_extractor` now is not ok when it lost data, as the
  command line exits 3 for both. `page_markdown` answers `{ok, markdown, url}`
  rather than bare text.
- The plain HTTP rung is built on curl_cffi directly rather than through
  scrapling's fetcher, and decodes the body itself, with the response's
  charset where the HTML standard puts it. What it sends is unchanged,
  measured on the wire. The `fetch` extra now needs `scrapling>=0.4.6`, the
  first whose browsers take `page_setup`, and declares `curl_cffi>=0.15`.
- `merge` takes what each reader found by its source name, and the order of
  precedence lives in one registry, `sluicer.declared.readers.READERS`.
  Adding a reader is one entry there.

### Added
- Every fetched page is bounded at 16 MiB (`MAX_RESPONSE_BYTES`,
  `fetch(max_bytes=)`). The HTTP rung stops reading past it after
  decompression, so a small gzip that inflates to gigabytes costs the bound; a
  page too heavy raises `ResponseTooLarge` and never climbs. HTML handed to the
  MCP server directly is held to the same bound.
- With `allow_private=False`, every redirect hop is judged before it is asked,
  and the HTTP rung connects only to the addresses it checked, so DNS rebinding
  reaches nothing new there. The browser rung routes every request a page makes
  -- images, frames, `fetch()`, websockets, each hop of a redirect -- through the
  same judgement, and gives pages no service workers. Against a local private
  server, a real Chromium reached it by six routes without the guard and by
  none with it (`tests/live/guard_check.py`).
- `sluicer inspect`: the same reading as `extract`, laid out for a person --
  what the fetch cost, which vocabularies said something, every record with
  the source of each field, every summary answer with its source and key.
- `heal` reports the evidence for every field it kept or moved: how many of
  the values it was learnt with were found in the new place, and how many the
  next best place held. Reported, never used to decide.
- Every climb and every fetched page records how long its rung took.
- Output schemas for the six MCP tools, from `sluicer.mcp_answers`.
- CI: the HTTP rung and the browser guard checked against a real curl and a
  real Chromium; a licence report over the whole installed tree that fails on
  a licence nobody has read.
- `docs/why.md`: where Sluicer sits among the tools people reach for, and when
  another is the better choice.
- A drift benchmark (`bench/drift/`, `docs/drift.md`): extractors learnt on
  Wayback Machine captures of 25 sites and replayed on later captures, judged
  by an oracle that does not use the extractor's code, with Scrapling's
  adaptive selectors beside them. 44 pairs: no silent failure, no false alarm.
- A scoreboard on pages as served (`bench/realweb.py`,
  `docs/scoreboard-served.md`): WCXB's labels scored on the same pages as their
  servers sent them, scripts intact, found in web archives and proved to be the
  page WCXB labelled, every capture pinned by digest. On the 360 matched
  pages, JSON-LD appears on 236, and Sluicer's author and date hit rates rise
  from 0.434 and 0.553 on WCXB's copies to 0.674 and 0.748.
- Property-based tests with Hypothesis (`tests/properties/`): any input never
  raises, the same page gives the same answer, the answer is bounded by the
  page, every summary answer names a reader and a key the page has, and the
  extractor file round-trips. Fifteen examples each on every run, and a CI job
  that searches thousands.

### Fixed
- An article quoting "just a moment", or any page carrying Cloudflare's
  bot-detection script, was taken for a challenge page and bought a browser.
  A challenge is now a title that is one, or a marker on a page that is not
  content.
- The robots.txt cache kept one entry for every site a long-running server was
  ever sent to. It keeps the 4,096 used last.
- A page too heavy to fetch ended the command line in a traceback; it now exits
  2 with a message.
- `heal` on a page of the same template whose items had changed -- any live
  listing, a month later -- reported every title and link as `vanished`, so
  `sluicer heal` exited 3 on a page that had not drifted. A field whose place is
  still there, holding values of the shape it was learnt with, is now kept.
- `heal` moved numbered slots onto each other when one value turned up in
  another slot: the first Pinboard tag to the fourth place, and an arXiv ninth
  author who was a first author a month later onto the first-author column,
  which it then called vanished. A slot whose own place is still there now
  never moves to another slot of its group. Both were found by the drift
  benchmark, on Hacker News, Lobsters, arXiv and Pinboard captures a month
  apart, all of the same template.
- `run` failed a page of the same template when one row renumbered a step in
  the middle of a path: one Stack Overflow user with a second kind of badge,
  or one Verge story with a second author, turned `span>span.badgecount` into
  `span1>span.badgecount` for every row, and the field was found in none.
  Renumbering is now read at every step, not only the last.
- `heal` called a link vanished when the site tagged it with a new parameter:
  after IMDb's 2023 redesign every film's link carries `?ref_=chttp_t_1`. A
  link with the same path, whose parameters are all among the other's, is now
  the same link; `?id=2` is still another item than `?id=1`.
- A page whose rows had become empty shells -- skeletons waiting for a script
  -- passed as a short page, since a member that carries nothing is not a row.
  An extractor now learns the largest share of empty members its pages had
  (`Listing.empty`, read as 0 from a 0.2 file) and fails a page of five
  members or more with 20% more than that.
- The `values` check fired on three rows that said the same thing by chance:
  the drift benchmark's one false alarm, three day-tables headed alike. It is
  held from five rows up, as shapes are.
- Found by the property tests, each with the smallest page that shows it:
  `extract()` raised on a charset label naming a codec that is not text, and on
  a row nested deeper than Python's recursion limit; a JSON-LD page could still
  expand past its budget with long strings, microdata and RDFa per item rather
  than per page, and induced records with the square of their rows; a `>`
  inside a quoted meta value hid the charset after it; an availability that is
  only the schema.org address was an answer; a meta's `property` was read as
  one name rather than a list of terms, so two pages that differed only in
  spacing gave two answers; and a page mf2py refuses to read raised instead of
  declaring no microformats.
- `heal` broke a tie between two new places holding a field's old values by
  their paths' alphabetical order. After SourceForge's redesign a project's
  name is its heading in every row and its icon's alt text in the rows that
  have an icon, and heal took the icon. The place more rows carry now wins.

## 0.2.0 - 2026-09-23

### Added
- Extractors that fail loudly, in `sluicer.extractor` and as three commands.
  `sluicer compile` learns from a few pages of one template what they declare
  and the listing they repeat, and writes it to a JSON file. `sluicer run`
  replays it with no induction and checks each page: the listing is where it
  was and is the only one of its kind there, it has rows, every field every
  learnt row carried is in 80% of rows and no common field vanished, values
  keep their shape and do not collapse to one placeholder, and every summary
  answer and declared type is still there. A page that fails any check exits 3
  with the reason. `sluicer heal` learns the pages again, matches each field to
  its new place by the values it held, keeps the old names, and exits 3 --
  writing nothing without `--force` -- when a field, an answer, a type or the
  listing is lost for good.
- The MCP server gains `compile_extractor`, `run_extractor` and
  `heal_extractor`.
- `docs/extractors.md`.

## 0.1.0 - 2026-09-22

The first public release. Nothing was published before it: the entries below
under Fixed and Changed are against the private work that preceded it, kept
because each one is a trap somebody else building this would fall into.

### Added

Reading
- Eight readers in a stated order of precedence: JSON-LD, microdata,
  microformats2 (on request, behind `sluicer[microformats]`), RDFa Lite, Dublin
  Core, OpenGraph with its `article:`, `book:`, `profile:`, `video:` and
  `music:` namespaces, the Twitter card, and HTML's own metadata names. All but
  microformats2 are written in `lxml` alone, so the base install is three
  packages.
- Records merged across vocabularies and never within one, every field naming
  the reader that won it, and every record the reader that declared it.
- Nested values whole: `Field.value` is the JSON the page declared -- an object
  keeps its `@type`, a list keeps its order, every leaf is text -- and a JSON-LD
  reference to another node on the page is replaced by that node, one hop deep,
  cycle-safe and within a budget.
- `extract()` returns a `summary`: title, description, url, image, author,
  published, modified, language, site_name, publisher, type, price, currency,
  availability, brand and sku, one value each, chosen by fixed rules and each
  naming its reader and its key.
- Structure induction, `extract(html, induce=True)`: the rows of a page that
  declares nothing, one record per repetition, every field marked
  `source="induced"`.
- Bytes decoded the way a browser decodes them, and `to_markdown()` for a page's
  main content, under the `markdown` extra.

Fetching
- A ladder that starts at plain HTTP and climbs to a browser only when a
  measurement says the cheap rung brought back a refusal, a challenge or a
  script waiting to render, recording every climb and its reason.
- An identifiable user agent and no borrowed referer or fingerprint;
  `robots.txt` obeyed by default, for redirects too; `RobotsRefused`,
  `FetchFailed` and, with `allow_private=False`, `AddressRefused`.

Command line and agents
- `sluicer extract` and `sluicer markdown`, for a URL, a file or standard input,
  with `--induce`, `--microformats`, `--stealth`, `--no-robots` and `--url`, and
  exit codes that tell "nothing found" from "could not read".
- An MCP server, `sluicer-mcp`, with three tools and error answers an agent can
  read, refusing private addresses by default, and a Claude Code plugin that
  brings the server and a skill.

Measurement and project
- A scoreboard: the summary measured beside trafilatura, metascraper and
  newspaper4k on WCXB's 511 annotated test pages, every outcome including
  inventions, regenerated by `uv run bench/run.py` into `docs/scoreboard.md`.
- A test that fails the build if a model client or a network library is ever
  imported. CI on Python 3.10 to 3.14, at the declared minimum versions and at
  the newest extras, with the network taken away, and a Docker image.
- `docs/known-limits.md`, `docs/design-notes.md`, `docs/field-survey.md` and
  `AI_POLICY.md`.

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
- Exit codes follow grep: 0 something found (a record or a summary answer), 1
  the page gives nothing, 2 could not be read. Errors used to exit 1, the same
  as a page that declares nothing.
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
  directly has to widen the call. `extract()` is unaffected. `microformats` is
  an empty list on every call that did not ask for the reader: a reader that is
  off is a reader that found nothing.
- The stealth rung has left the automatic ladder. `fetch(url, stealth=True)` adds
  it back for a caller who wants it.
- An element whose whole text is its children's no longer carries a text fact of
  its own, so a wrapper around a single value stops reporting that value twice.
- A bad argument to `sluicer extract` now exits with our own message rather
  than with click's. A missing file and a directory are both covered.
