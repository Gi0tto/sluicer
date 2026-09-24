# Changelog

Dates are the day the work landed. Anything not listed here did not happen.

## 0.7.0 - 2026-09-24

### Added
- A page field is read after its label when the pages it was learnt from
  contradict its place. `compile --want` still learns where the example sits;
  when that place holds nothing on another of the pages given, or a value that
  does not read as the example does -- the saving, where a row the product
  lacked moved the price down -- the field is read after the text every page
  puts once before it, as `Price:`, and a note says why. A value that shares
  its element with its label, `<b>ISBN:</b> 978...` or `Pages: 310`, is learnt
  the same way, where before it could not be learnt at all. Two pages at least
  are needed: one cannot tell its template's words from its own. A page
  without the label, or with it twice, fails the run, and `heal` follows a
  field to its new label by its old values. An extractor with such a field is
  written as format 2, which 0.6 refuses rather than reading the place alone.
  On SWDE's half of sites never read while it was built, `compile --want`
  goes from F1 0.686 to 0.845 and answers 37,801 more pages right. Its silent
  wrong answers there rise in number, from 7,372 to 8,797, and fall as a share
  of its answers, from 4.2% to 4.1%; `bench/floors.json` was raised for that
  one count on purpose.
- A sixth scoreboard, on SWDE: 80 sites, 124,291 pages, `compile --want` given
  three pages of each site and one example per attribute, beside Scrapling's
  adaptive selectors. Its sites were split into a development and a held-out
  half before any full result was read; see `bench/PREREG.md`. `bench/gate.py`
  now fails a release that does worse than `bench/floors.json` on any scoreboard.
- No MCP answer is larger than a client takes. `fetch_page` and
  `page_markdown` answer a slice of at most 60,000 characters, 30,000 unless
  asked, with `offset`, `max_chars`, the whole length, and `next_offset` where
  the next slice starts: Claude Code puts an answer over 25,000 tokens in a
  file, and the 200,000 characters `fetch_page` returned were over that on 302
  of 386 real pages. `extract_declared` takes `records=False` for the summary
  alone, 1.4 KB instead of 5.9 KB at the median, and leaves its records out,
  counted in `records_left_out`, past 75,000 bytes.
- Every parameter of every MCP tool says what it is in the schema a client
  reads, taken word for word from the tool's own description: all 28 said
  nothing there, and clients and directories read it from there. A tool
  that leaves a parameter unexplained is refused when the server starts.
- `heal` leaves a move to a person when two new places have equal claim to
  a field: as many of its old values, on as many rows, in the same kind of
  element, and they read other values. It reported the runner-up but moved anyway, by page order, which
  is a guess; the change is now `ambiguous`, the field is left out, and heal
  does not write the extractor without `--force`. A tie the old element's
  kind decides -- the old title was a link, and only one place is -- is
  still a move, and so is one between two places that read the same values,
  as a film's poster and its title both linking to the film.
- `sluicer mcp --tools extract_declared,page_markdown`, or
  `SLUICER_MCP_TOOLS`, registers only the tools named: each registered tool
  costs an agent context whether it is called or not. A name that is not a
  tool stops the server with the list of the ten.
- `python -m sluicer` is the command line, for a Python whose scripts are
  not on PATH; `python -m sluicer mcp` starts the MCP server.

### Changed
- `LICENSE` holds the MIT License's text alone, so that GitHub and the
  tools that ask it recognise the licence; the two data files under their
  own licences are named in `NOTICE`, which the package carries beside it.
  Nothing is licensed differently.

### Fixed
- The scoreboards asked metascraper for the wrong date. Its `date` puts
  `dateModified` first, and the scoreboards score publication dates, so on
  every page declaring both it was scored wrong for how it was called. It is
  now asked for its publication date, and its dates go from 0.374 to 0.725 on
  WCXB and from 0.384 to 0.811 on the pages as served; Sluicer's answers are
  still the most often right when it answers a date, 0.734 against 0.573.

## 0.6.0 - 2026-09-24

### Added
- A date's month is read by its name in any of the 430 languages and regions
  CLDR 48.2 covers at its modern level, in the orders they write it --
  `10. Mai 2023`, `10 de mayo de 2023`, `10 мая 2023 г.`, Hungarian's
  `2023. május 10.`, a weekday and its comma before it -- and the numbers with
  units of Chinese, Japanese and Korean, `2023年5月10日`; a Thai month's year
  from 2400 on is the Buddhist era's, and converted. `normalised` and the
  conflicts read them. The names are generated from CLDR by
  `scripts/cldr_calendar.py` into `sluicer/calendar_names.py`, the one file
  under the Unicode License v3, so the licence expression is now
  `MIT AND CC-BY-SA-3.0 AND Unicode-3.0`. On 2,680 pages one more date is
  read and none changes: pages rarely declare dates so.
- A crawl hears a site that says it is asked too often. After a 429 or a 503
  the next request to the site waits its `Retry-After`, a date counted from
  the response's own `Date`; one longer than the crawl's `max_delay` answers
  the site's next pages `rate_limited`, retryable. Without a `Retry-After`
  the site's delay doubles for the rest of the crawl, up to `max_delay`.
  Taken from Crawlee, which reads the header; Scrapy retries both statuses
  without it.
- A scoreboard on trafilatura's evaluation set (`bench/evaldata.py`,
  `docs/scoreboard-evaldata.md`): 990 pages, 851 annotated with their title,
  author and date, and the main text of all of them scored by the snippets
  it must and must not hold. Sluicer's titles are the most often right of
  the four tools; its authors and dates are behind the tools that read the
  visible page, as on the other scoreboards. Its markdown holds 2,670 of the
  2,951 snippets trafilatura's text holds 2,785 of, the difference the
  markdown's own syntax: a link written `[text](address)` splits a snippet
  that runs across it.
- `examples/04_a_guess_from_the_visible_page.py`: trafilatura's guess at an
  author or date beside what the page declares, named a guess, for a caller
  who wants one. It stays out of the summary, and the known limits say why,
  with how often it is right where nothing is declared.
- The examples need no web: `examples/_site.py` serves a small made-up site
  from `examples/site/` on the machine, and a test runs every example and
  checks what it prints. Given an address, an example reads that page instead.
  The documentation publishes the same site under `demo/`, where Getting
  started reads a page from the command line.
- The README shows an extractor meeting a real redesign: learnt from Wayback
  Machine captures of a software directory in 2016, it fails loudly on the
  2024 page and `heal` says what moved. `scripts/demo.py` records it from the
  commands as they ran. `scripts/social_card.py` draws the card a shared link
  shows, and every page of the documentation now declares it, with the page's
  title, in OpenGraph.

### Changed
- The README is rewritten to be read in a minute: highlights, install, a quick
  start whose every line a test runs, the uses by audience, a comparison
  table, and the scoreboards with a chart. Its pictures are generated, not
  drawn: `scripts/readme_assets.py` runs `sluicer inspect` on
  `examples/brake-pads.html` and charts the published scoreboard. The
  documentation's home is the README (`scripts/docs_home.py`), held to it by a
  test, since a copy kept by hand fell behind twice.
- The documentation site has a path through it: Getting started, guides, a
  reference, the scoreboards and the project, with search and navigation. The
  reference is generated from the code -- every command's `--help`, every MCP
  tool as the server lists it, the public functions with their docstrings --
  and held to it by tests. CONTRIBUTING says how to set up, what CI refuses,
  where each part of the code lives and which files are generated.
- Development status is Beta. The public interface -- `extract`, the
  summary's questions, the MCP tools -- may still change before 1.0; every
  change is in this file.
- The names content systems give an account nobody named -- WordPress's
  `admin`, Joomla's `Super User`, Blogger's `Unknown` -- are no author.
- The tests, comments, documentation and this changelog name no site or person
  they do not need to. A fixture is a made-up site on a reserved `.example`
  domain, and a regression says the shape of the page that showed it, not
  whose it was. Specifications, the tools compared, the sandboxes built for
  scraping practice and the benchmarks' own pages are still named, as their
  sources. `docs/audit.md` audits `examples/brake-pads.html` rather than a
  table of real sites.
- The suite runs on macOS and Windows too, where it had only ever run on
  Linux. Every text the repository reads or writes names its encoding, and a
  test reads every Python file to hold it so: on Windows the default is the
  ANSI code page, and eleven tests read UTF-8 as cp1252. The install commands
  are quoted with double quotes, which cmd, PowerShell and every POSIX shell
  read alike.
- Questions and ideas go to Discussions, each category with a form of its
  own, and the issue chooser points there; a page read wrong is still an
  issue. The README and CONTRIBUTING say where each kind of message goes, and
  the documentation's footer links GitHub, Discussions and PyPI.
- Sluicer can be sponsored: GitHub shows the button, the package's metadata
  names the page as its funding, and the README and the documentation link
  it.

### Fixed
- On Windows the command line wrote its JSON and markdown to a file or a pipe
  in the ANSI code page: `sluicer extract URL > out.json` on a page titled in
  Chinese raised UnicodeEncodeError, and addresses piped to `batch` were read
  in cp1252. Its standard streams are UTF-8 on every system now.
- The CI no longer cancels one kind of run with another: dispatching the full
  run on main cancelled the push's run of the same commit, and 0.5.0's commit
  showed as failed though every check had passed.
- The documentation's home page had lost the licence's exception for
  schema.org's names that the README states.
- The documentation site was not rebuilt when only the changelog,
  CONTRIBUTING or SECURITY changed, though it publishes all three.

## 0.5.0 - 2026-09-24

### Added
- `Extraction.conflicts`: every question the page answers in two ways that
  mean different things -- a price, its currency, the date of publication
  or of modification -- the summary's answer first, each with its source,
  key and place. `sluicer inspect` shows them under the summary, and the MCP
  and HTTP answers carry them. Compared by meaning: `126` and `126.00` are
  one price, two dates agree when they are one instant or name one day as
  written, and a value no rule reads is no disagreement. On the 1,690 pages
  of the scoreboards there are 12: 4 of Zyte's product pages state two
  prices (150 and 200, 997.00 and 1148.00, 32.00 and 36.49, 90 and 400) and
  8 pages two days, 2023 against 2026 among them.

### Fixed
- A page's declared main entity is what the summary is about. schema.org's
  `mainEntity` names the thing a page describes, and two news sites and a
  journal declare a WebPage whose main entity is the NewsArticle: their
  authors went unread, and the journal's came from Dublin Core one name of
  five. The entity is the subject when it ranks ahead of the
  record holding it, and only a single one: an FAQ page's questions are its
  parts, an about page's organisation is the site. Each answer read from it
  is placed inside it. On the scoreboards' pages 5 authors and 19 dates
  more are right and 3 dates are wrong or where the labels have none; one
  title is the article's shorter headline where the label has the longer;
  and a question and answer page's subject is its question, whose asker is
  its author, on 12 of WCXB's pages and 6 of them as served that its labels
  count unsigned.
- Every `<meta name="author">` is read, and one naming the site is passed
  over for the next: a paper whose first names the paper and whose second
  names the reporter had the first alone read. Two answers change on the
  scoreboards' pages, both right.
- A blogger's site bears their name, and the author of that name is theirs:
  an author named as the site is still left out, as the site signing its
  own page, unless the page declares a publisher of that name a Person.
  A blog published under its owner's name had no author. A Person record
  alone is not enough, since WordPress declares one for every user: on the
  scoreboards that would have given two sites' own names as authors.
  One answer changes on the scoreboards' pages, and it is right.

## 0.4.1 - 2026-09-24

### Added
- A scoreboard on news in many languages (`bench/news.py`,
  `docs/scoreboard-news.md`): fundus's parser fixtures, 263 news pages from
  42 countries' publishers in 21 declared languages, with scripts, each
  paired with its labels by fundus's own code. The same questions, tools and
  scoring as the other scoreboards, and a table per language. Sluicer's
  titles are the most often right of the four tools (0.875), its dates are
  never wrong when it answers one, and trafilatura finds more authors, which
  it also reads from the visible byline.
- `docs/agents.md` shows Sluicer in LangChain, the OpenAI Agents SDK and
  Pydantic AI, and after Playwright, Crawl4AI, Scrapling, Scrapy, httpx and
  Firecrawl, each run on a local page but Firecrawl, whose service needs a
  key. Gemini CLI was run too: `gemini mcp add` writes the entry the page
  shows, and connects in a folder it trusts. Measured: `langchain-mcp-adapters`
  0.3.1 resolves mcp 1.30 and fails to import against the mcp 2.2 Sluicer
  needs, so the page says to run the server as its own process, where the
  two speak MCP to each other.

### Fixed
- Bytes that are valid UTF-8 and hold a character outside ASCII are read as
  UTF-8, whatever the page or the response declares. A page another tool
  saved or re-encoded keeps its old declaration over UTF-8 bytes: fundus's
  fixtures of a Chinese paper (`<meta charset=GB2312>`) and a Spanish one
  (`iso-8859-15`) read as mojibake, and now read right. On 1,427 pages as
  their servers sent them, none is read differently. Found by the
  multilingual news scoreboard.
- The journal or newspaper a page is published in is what the page belongs
  to, not what it is about, as the site and its organisation are: `Periodical`,
  `Newspaper` and every kind of `...Organization`. A journal declares its
  Periodical in the footer of every article, and the journal's name was
  every article's title.
- On a page that declares an article, a record named as the site or its
  publisher comes after the article: a paper's own app, named as the paper
  is, was the story's title, type and price ("0 INR"). Beside anything
  but an article such a record keeps its place, so a business's page with
  its reviews still answers the business.
- An author is a name: one with no letter in it (a paper writes an id, `105092`)
  or that is the page's own host (`news.example`) is not answered, and a title
  from the page's tags ending in its host has it cut: "Volunteer with us |
  town.example" on town.example is "Volunteer with us". Measured on the 1,688
  pages of every scoreboard: 9 answers are righter and 2 fundus labels that name
  a site's domain as the author are no longer matched. On the scoreboards,
  WCXB's titles go from 0.725 to 0.727 and the same pages as served from 0.700
  to 0.706, with one author fewer invented on each.
- `pytest` collects `tests/` only: a benchmark's cache under `bench/` holds
  other projects' checkouts, with test suites of their own.

## 0.4.0 - 2026-09-23

### Changed
- The licence is `MIT AND CC-BY-SA-3.0`: `sluicer/audit/schema_org.py`, which
  holds schema.org's type and enumeration names, is distributed under CC BY-SA
  3.0, as schema.org publishes its vocabulary, and says so in its header;
  `LICENSE` names the exception and `LICENSES/CC-BY-SA-3.0.txt` holds the
  licence's text. Everything else stays MIT.
- OpenGraph's arrays and structured properties are read as ogp.me reads
  them. A record's OpenGraph field is a list when the page repeats one of the
  protocol's arrays -- several `og:image` are a list of `{url, width, height,
  alt...}`, several `article:tag` a list of tags -- and each `og:image:width`
  belongs to the image above it. It was the first width anywhere, so a page
  with two images could answer the second one's size for the first. A
  single-valued property declared twice still keeps its first. ogp.me's own
  three-image example is a test. The summary is unchanged: it answers each
  property's first value.
- A price's key is the path it was read at -- `Product.offers.price`,
  `Product.offers[1].priceSpecification[0].price` -- rather than
  `Product.offers` for every offer answer.
- An `AggregateOffer`'s `lowPrice` and `highPrice` answer `price_low` and
  `price_high`, new summary questions, and no longer a plain `price`: "from 19"
  is not a price of 19.

### Added
- Every MCP tool has a title and says in its annotations that it only reads,
  destroys nothing and may reach the web (`readOnlyHint`, `destructiveHint`,
  `idempotentHint`, `openWorldHint`). A client that asks before a tool writes
  now runs Sluicer's without asking: measured with Codex 0.144.4, `codex exec`
  cancelled every call unless the tools were approved in advance, and with
  the annotations it runs them in its default, `writes` and `auto` modes.
- `sluicer mcp`, the MCP server as a subcommand, which is how the MCP Registry
  starts a package: `uvx --with 'sluicer[mcp]' sluicer mcp`. `sluicer-mcp`
  stays. `server.json` lists the server in the registry as
  `io.github.Gi0tto/sluicer`, the README carries the `mcp-name` line the
  registry checks on PyPI, and a test holds the entry to the package's
  version. The release workflow publishes it after PyPI, with a pinned and
  checksummed `mcp-publisher` and the workflow's own identity, once the
  repository variable `PUBLISH_TO_MCP_REGISTRY` is true.
- `docs/agents.md`: the server in Claude Code, Codex, Cursor, VS Code, Gemini
  CLI, Claude Desktop and Zed, the skill in Codex, and a page another
  crawler fetched. Claude Code and Codex were run end to end; the others are
  written from their own documentation, and say so.
- Two more ways of writing a date are read into ISO 8601: the year first, as
  PubMed writes a citation's date (`2023 Jan 7`), and JavaScript's
  `Date.toString()`, which one page wrote into its JSON-LD (`Fri Oct 24 2025
  03:22:33 GMT+0000 (GMT)`), at its offset. Of the 669 dates the benchmarks'
  pages declare, the ones not read go from 11 to 6, all six refused on
  purpose.
- Every value says where on the page it was declared. `Field.where`,
  `Record.where` and `SummaryField.where` are an XPath to the element that
  declared it -- for JSON-LD, the `<script>` block's, with a JSON pointer (RFC
  6901) to the value after `#`: `/html/head/script[1]#/offers/1/price`. A
  microdata or RDFa property is placed at its own element, even one `itemref`
  brought from elsewhere, and a value inside a nested item at that item's.
  The place travels with the value rather than being worked out from its key,
  since a key cannot find it: a JSON-LD reference is replaced by the node it
  names, and that node's own place comes with it -- Yoast's author, declared
  in another block, is pointed to there -- and a blank item dropped from a
  list shifts every index after it, which the key reflects and the place
  does not. Where a place cannot be given exactly it is given coarser, never
  wrong: a property declared twice is placed at its item, an answer joined
  from several tags has none, and a meta tag's key is its place. Every step of
  an XPath carries its position, so a sibling added after an element never
  moves it, and the first `#` always starts the pointer, since a path never
  holds one. Every place in an answer is paid for from a budget of twice the
  page for the records and once the page for the summary, so a page nested
  two hundred deep cannot answer with an XPath per property longer than
  itself. The MCP and HTTP answers carry `where` too. A property test follows
  every place on every drawn page, hostile and broken ones included, and
  finds the declared value there.
- `sluicer.compat.extruct`, extruct's interface answered by sluicer's own
  readers: `from sluicer.compat import extruct` in place of `import extruct`.
  `extract` takes every argument extruct 0.18 takes and answers its six
  syntaxes in extruct's shapes, `uniform=True` included; the extractor
  classes are under extruct's module names. RDFa is read by a processor of
  its own, in the `lxml` the base install carries, that answers what pyRdfa
  and rdflib answer for extruct, so nothing extruct needs is installed but
  mf2py for microformats. On sluicer's fixtures, the 360 pages as served and
  Zyte's 140 product pages, JSON-LD, OpenGraph, RDFa and microformats are
  identical on every page extruct reads, and microdata on all but four;
  every difference is one where extruct is wrong: a JSON-LD block that is not
  JSON loses extruct the whole page, an item named by `itemref` is `null` in
  it, a `<time>` without `datetime` is `""`, an absent `href` is the page's
  own address, and names Dublin Core never claimed, `<meta name="description">`
  first, are Dublin Core to it, on 448 of the 520 pages; two of them write a
  Dublin Core name. Bytes are read as their charset says, where extruct reads
  every page as UTF-8, and no page makes a syntax raise. `docs/extruct.md`
  has the migration, the measured table and every difference;
  `bench/extruct_compat.py` regenerates the table, running extruct in an
  environment of its own.
- `sluicer diff BEFORE AFTER` and `sluicer.diff.compare`: what changed between
  two readings of a page, question by question -- a price, an availability, a
  canonical that moved, a page that started reserving its rights -- each side
  naming its source and key. A value written differently with the same
  meaning (`41.90`, `41.9`) is `rewritten`, not `changed`. Exit codes are
  diff's: 0 same, 1 different, 2 unreadable.
- A `reads` check in extractors: a listing field whose every learnt value read
  as an amount or a date must still read so in half its values. The shape
  check could not tell `12.99` from `2025-01-02`, both digits and
  punctuation, so a price column and a date column that swapped passed it.
  A 0.3 extractor file, which learnt no reading, still loads. The drift
  benchmark still shows no false alarm.
- A scoreboard on product pages (`bench/products.py`,
  `docs/scoreboard-products.md`): Zyte's product-extraction benchmark, 140
  pages as served with price, SKU and availability labelled by hand, scored by
  Zyte's own evaluator beside Zyte's and Diffbot's paid APIs and an extruct
  baseline. Price F1 0.750 against extruct's 0.685, availability 0.907 against
  0.626, SKU 0.541 against 0.537; the paid services, reading the visible page
  with trained models, are ahead on all three.
- `sku` falls back to `productID`, then Facebook's `product:retailer_item_id`,
  `og:sku` and `product:sku`: identifiers the page declares under other names.
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
- `sluicer compile --want NAME=VALUE` (and `want=` for `compile_extractor`, in
  Python and over MCP): examples of what one row holds choose the listing --
  the first repeated group whose rows hold them all, even in a sidebar, where
  compile alone never looks -- and name its columns, and only those are learnt
  and checked. A value matches as written with spaces collapsed, or as the same
  amount (`51.77` is `£51.77`). An example no row holds is an error naming it.
  `heal` finds such a listing again by the values its columns held, keeps the
  names, and adds no column. On books.toscrape.com: `--want title=... --want
  price=51.77 --want stock="In stock"` learns the 20-row catalogue and
  replays page 3 with those three columns.
- A page that declares nothing and lists nothing -- a product page -- is
  learnt the same way: when no one repeated group holds every example, or
  with `--no-listing`, the examples are the page's own values
  (`Extractor.fields`, `Run.fields`), each where it sits, the page's own
  place before its navigation, breadcrumb trail and listings, so a title is
  the `<h1>` and not the trail's last step. `run` checks each is there and
  reads as it did, and "Add to basket" in a price's place fails; `heal` keeps,
  moves or loses each by its values. The extractor file gains a `fields` key,
  written only when there are any.
- A `ProductGroup`'s summary reads its variants, in both shapes Google
  documents: listed in `hasVariant`, or each its own node pointing at the
  group with `isVariantOf` or `inProductGroupWithID`. What the group leaves to
  its variants is answered only when every variant says the same -- a price,
  a currency, an availability, an MPN -- with the first variant's key. Prices
  that differ are a range: `price_low` and `price_high` are the lowest and
  highest a variant declares, each with its own key
  (`ProductGroup.hasVariant[2].offers.price`), when two or more variants have
  one, all read as amounts and all are in one currency. No variant is ever
  picked: on Google's page-per-variant example, which prices one variant and
  links the rest, the group has no price. On Google's own example the summary
  had only title, brand and type.
- `sluicer feed SOURCE`, `sluicer.feeds.read_feed` and the MCP tool
  `read_feed`: a feed's items -- RSS 2.0, RSS 1.0, Atom 1.0 with its
  `xml:base`, JSON Feed 1.0 and 1.1 -- each with its title, link, id, dates
  (normalised as ISO 8601 beside the feed's own), authors, categories,
  enclosures, summary and content. A page that is not a feed but declares one
  is followed to it. XML declaring an entity or an external document type is
  refused before it is parsed (`sluicer.safexml`, shared with the sitemaps).
  The MCP server has ten tools.
- `--cache DIR` and `--max-age SECONDS` on every command that reads a page,
  and `sluicer.fetch.cache`: a page is kept with its `ETag` and
  `Last-Modified`, and the next fetch asks the site with `If-None-Match` and
  `If-Modified-Since`; a 304 gives the kept page back, marked `revalidated`.
  The only other freshness rule is the caller's `--max-age`, within which the
  site is not asked; nothing is guessed from `Last-Modified`. Only 2xx pages
  are kept, never their cookies, and a page that changed into a challenge
  goes up the whole ladder again. `fetch.cached` says the page's age and
  whether the site was asked.
- `--respect tdm` on every command that reads a page, `crawl` and `batch`
  included (`respect_tdm` in Python and on the MCP tools `extract_declared`,
  `page_markdown` and `crawl_site`): a page whose text and data mining rights
  TDMRep reserves is refused, an error `tdm_reserved` (HTTP 451 at the HTTP
  door, RFC 7725's Unavailable For Legal Reasons), never its data. The site's
  `/.well-known/tdmrep.json` is read -- once per site in a crawl, through its
  robots.txt and its delay -- then the `TDM-Reservation` header, then the
  meta tag, each superseding the earlier as the report's section 6.7 says; in
  the file the first rule that matches wins, not the longest. The audit
  reports the page's reservation as `tdm`. `sluicer.declared.tdmrep` and
  `sluicer.pathmatch`, robots.txt's path patterns in one matcher for every
  file that writes them.
- `--at DATE` on every command that reads a URL, and
  `sluicer.fetch.archive.fetch_archived`: the page as the Wayback Machine
  captured it nearest to the date, in its `id_` form, so a reading is
  reproducible across time and costs the site nothing. The answer says which
  capture it read (`fetch.archived`: asked, captured, the address captured),
  never passes the date asked for off as the capture's; the site's headers
  of then, which the archive returns as `x-archive-orig-*`, are read as a live
  page's. It is an ordinary fetch -- plain HTTP, the archive's robots.txt, the
  size bound, private addresses refused -- that follows redirects only within
  the archive. `sluicer diff URL URL --at 2024-01` reads BEFORE from the
  archive and AFTER live: what changed since then. The MCP tools
  `extract_declared` and `page_markdown` take `at` too; a page the archive
  never captured is `fetch_failed` with `retryable` false.
- `sluicer warc FILES` and `sluicer.warc`: the pages a WARC file holds, as
  Common Crawl, the Internet Archive, wget, Browsertrix and warcio write them,
  one JSON line each with the record it came from. Every page is read with
  the headers it was served with; chunked and gzip or deflate bodies are
  undone; revisits, non-HTML bodies, error answers and bodies too large are
  counted by reason, not silently dropped. Plain or gzipped, one member per
  record or one for all, and a damaged record boundary is passed over to the
  next record. On warcio's own eleven sample files it agrees with warcio on
  nine and reads the two warcio refuses or empties. See
  `docs/warc.md`. No new dependency.
- More of what a page and its server say about use. `rights["license"]`
  holds the addresses a `rel=license` names -- the HTML standard's "the main
  content is covered by the license described by the referenced document",
  on 12 of 1,234 cached pages, all Creative Commons. `rights["http"]
  ["content_usage"]` holds the IETF aipref drafts' `Content-Usage` header
  (`train-ai=n, search=y`), read as their vocabulary says: a Structured
  Fields dictionary (RFC 9651, parsed in full, since one that does not parse
  leaves every preference unknown), `y` is allow and `n` disallow, anything
  else unknown and not reported. Both drafts are working-group drafts, not
  RFCs. `sluicer inspect` shows both.
- `sluicer audit` reads what robots.txt says about use, beside what it lets
  be fetched: the aipref drafts' `Content-Usage` rules and Cloudflare's
  `Content-Signal`, which protego passes over, for the group that decides each
  agent, the longest matching path winning and rules on one path combining
  most-restrictive-first, as draft-ietf-aipref-attach-05 says. A page the agent
  may not fetch has none. Each `CrawlerVerdict` carries `content_usage` and
  `content_signal`, the MCP and HTTP answers too, and the text report says
  them once per group. On blog.cloudflare.com: `search=allow, ai-input=allow,
  ai-train=allow`.
- The crawler honours an `X-Robots-Tag: nofollow` or `none`, for every
  crawler or for `sluicer`, as it honours the `<meta>`, and counts a `Link`
  header canonical with the head's. Its canonical was read from anywhere in
  the page, the body included, where the page's own content can put one; it
  is now the head's only, and a head naming two addresses names none, as
  the summary already read it.
- The response's headers, kept and read. `Fetched.headers` holds them, names
  lowercased; `extract(headers=...)` reads them, and the CLI, the MCP server
  and the crawler pass them for every page they fetch. A canonical, `hreflang`
  alternates and the next and previous pages in the `Link` header (RFC 8288)
  join the markup's -- Google accepts a canonical there as it does in the
  head, so a head and a header naming two addresses are a conflict and answer
  no `url`. `X-Robots-Tag`, per crawler as Google documents it, and TDMRep's
  `TDM-Reservation` and `TDM-Policy` headers are reported in `rights["http"]`,
  apart from what the page's own tags say. The `Content-Type` charset decodes
  bytes ahead of the page's declaration, as a browser does. The headers
  themselves are never sent back to an MCP client: a response's cookies are
  not the agent's to see.
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
- `sluicer audit SOURCE [--json]`, `sluicer.audit.audit()` and the MCP tool
  `audit_page`: every record JSON-LD, microdata and RDFa declare, held to the
  rich-result features Google documents for its type -- product snippets and
  merchant listings, review snippets, articles, breadcrumbs, organizations,
  local businesses, recipes, events, job postings, videos, software apps,
  course lists, datasets, Book actions, Q&A, discussion forums, profile pages
  and site names -- with the required and recommended properties it lacks and
  the values in a form the documentation or schema.org refuses: prices, ISO
  4217 currencies, ISO 8601 dates and durations, absolute URLs, schema.org
  enumerations, ratings on their scale, GTIN and ISBN check digits. Features
  Google has retired (FAQ, How-to, the sitelinks search box, and the seven
  phased out in 2025) are named as retired, with their dates. Every finding
  names the vocabulary, the record, the property path and the page its rule is
  written on; the requirements are data, read from Google Search Central on
  2026-09-23 (`sluicer/audit/google.py`, `docs/audit.md`).
- The page as a whole: `<title>`, meta description, one absolute canonical, and
  OpenGraph's four required properties; facts two vocabularies state
  differently about one thing.
- For a URL, the site beside it (`sluicer.fetch.site.read_site`): which of 25
  AI agents, each from its vendor's own page, the robots.txt admits and what
  each is for, the `User-agent` names no vendor documents, and llms.txt read
  against llmstxt.org's format. Exit codes: 3 when anything is an error, 1 when
  nothing is declared, 0 otherwise, 2 when the page could not be read.
- MCP: `audit_page`, with an output schema like the others. The server has
  nine tools with `map_site` and `crawl_site`.
- **Crawling, politely** (`sluicer.crawl`, `docs/crawling.md`). `map_site` lists
  a site's addresses from its sitemaps -- the ones robots.txt names, or
  `/sitemap.xml` and `/sitemap_index.xml` -- following an index on the same
  site, gzip told by its bytes, and the start page's links when there is no
  sitemap. `crawl` follows a site's links breadth first and hands back each
  page's extraction or the reason it has none; `extract_many` reads a list.
  Every page goes through the ladder, robots.txt included, and every site is
  asked one request at a time, no sooner than a second after the last ended or
  its `Crawl-delay` or `Request-rate` if longer -- robots.txt, sitemaps, each
  redirect hop and each rung included, and remembered for the process. A crawl
  refuses a redirect that leaves its site before the other site is asked, marks
  where a page landed and its canonical seen, skips links that name a file, and
  admits nothing from a page that answered 4xx or 5xx. The same site crawled
  twice gives the same pages in the same order, and the output, one JSON line
  per page, is the state a crawl resumes from without asking for any page again.
- `sluicer map`, `sluicer crawl` and `sluicer batch`, writing JSON Lines to
  stdout or `--out`, `--resume` to continue, and the grep exit codes over the
  whole run.
- MCP tools `map_site` and `crawl_site`, bounded to a thousand addresses or 25
  pages and a minute, with the error codes `redirected_off_site` and
  `crawl_delay_too_long` for a crawled page.
- Sitemaps are parsed with no entity resolved, nothing fetched from inside,
  any document type refused, and gzip inflated no further than 16 MiB;
  billion laughs and XXE are tested.
- `http_responses`, the HTTP rung's transport answering bytes; a caller's rule
  for redirects, asked before every hop by the HTTP rung and the guarded
  browser, with `RedirectRefused` final on the ladder; `robots_delay` and
  `robots_sitemaps`, read through the robots.txt cache; `robots_reader_from`,
  `RedirectRefused` and `ResponseTooLarge` exported from `sluicer.fetch`.
- CI: `tests/live/crawl_check.py`, a crawl of a local site that measures its
  own politeness from the server's side, in the `live` job; the real protego's
  `Crawl-delay` and `Sitemap` reading in the `with-extras` job.

### Fixed
- An address read from an attribute or a `Link` header lost a no-break space
  or an ideographic space at its ends: `str.strip` takes them, and the URL
  standard trims only controls and ASCII spaces, so a browser keeps them and
  percent-encodes them. Seven readers did it -- the `<base>`, `<link>` and
  `rel=license` addresses, a `Link` header's, microdata and RDFa address
  properties, the crawler's links and the audit's canonicals -- and now each
  resolves `\u00a0x` to `%C2%A0x`, as Node's WHATWG `URL` does on the same
  base. Found by the fuzz profile.
- The skill's frontmatter had a top-level `version`, which the Agent Skills
  standard does not allow and its own validator refused, so a client that
  reads the standard, as Codex does, could refuse the skill. The version is
  under `metadata`, `compatibility` says what the skill needs, and a test
  holds the frontmatter to the fields the standard names.
- A `url` or `image` that cleans to nothing -- a JSON-LD `url` of one control
  character -- was answered as the empty text rather than passed over for the
  next declaration: addresses are now resolved before one is chosen. Found by
  the fuzz profile.
- The MCP module's docstring still said nine tools after `read_feed` made ten;
  a test now holds its list to the tools the server registers.
- The CI's check of the installed extras still expected nine MCP tools, so it
  failed from the day `read_feed` made ten; it now lists ten and calls
  `read_feed` through the SDK's dispatch too. The release workflow's test gate
  ran without the `api` extra, so it skipped the HTTP door's tests the CI
  runs: it now runs what the CI's coverage step runs, floor included. The
  plugin's manifest still said nine tools and, with the citation file, MIT
  alone; both now say what the package says, and a test holds the version and
  the licence alike in every file that states them.
- The audit matched a robots.txt path pattern with a regular expression that
  backtracked: `Content-Usage: /*a*a*a*a*b$ ...` took 13 seconds against a
  300-character path, and any site's robots.txt could stall an audit or an
  agent's `audit_page`. It is matched with two pointers now, in no time at
  64 wildcards and 2,000 characters. protego, which decides what may be
  fetched, was never affected.
- Reading a text as an amount lowercased it once for every currency symbol
  there is, whatever its length, and a page's wrapper was read as an amount
  with the whole page's text in it: pointing at a price on a 1.5 MB page with
  `--want` did not finish in ten minutes, and takes 0.06 s. An amount is now
  refused past 64 characters, and the search reads no element whose child's
  text is already longer than the example could be.
- A healed listing forgot the share of empty rows its pages always had, so a
  page with the spacer rows the extractor was learnt with failed the healed
  extractor's empty-rows check.
- An address resolves alike on every Python. 3.14's `urljoin` keeps a bare
  `?` or `#` that 3.13's drops, so `href="/p?"` answered `https://site/p?` on
  one and `https://site/p` on the other; the empty query and fragment are now
  dropped on both. Found by the 3.14 job.
- An address is read as the URL standard reads it out of an attribute: its
  ends stripped, every tab and newline inside dropped, any other white space
  percent-encoded. `href="0<CR>?"` was answered as `https://shop.example/c/0 `,
  with a space the page never wrote -- the return became a space, and the
  empty query took what followed it. Found by the property search.
- A product declared once per colour or size, or beside related products that
  carry no offer, as two shops on Zyte's benchmark declare theirs, was taken for
  a listing, and the page had no subject and no price. Records of one name are
  now one product, answering only what they all agree on -- the price, not the
  sku of one colour -- and the one record of a type that carries an offer is the
  subject. A price whose text holds two numbers (`71,91 € 79,90 €`) is no price
  and gives way to the next declaration. On two of one shop's pages the title is
  now the product's declared name, shorter than the heading WCXB labels, so the
  served scoreboard counts two titles fewer.
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
  sites: a language menu of 491 links, a forum's sidebar lists, the paragraphs
  of one blog post, page sections on two news sites, and a package index's three
  day-tables. Regions the page marks with an ARIA role such as `menu` or
  `navigation`, or hides, are now furniture; a group whose members are mostly
  another listing is sections, not rows; and classes that name one item, a
  position or a state (`id-t3_8gxz1`, `odd`, `category-reviews`,
  `has-post-thumbnail`) no longer split one listing into as many kinds as rows.
  All 25 now learn the listing a person would point at, and the benchmark still
  shows no silent failure and no false alarm.
- A numbered slot in the middle of a path -- the link in a row's second span --
  was held as a column, so a row with one item fewer, which renumbers the rest,
  failed a page of the same template. A numbered slot at any step is now a
  count, and the first slot of a group is held to some rows rather than every
  row.
- The `mcp` extra needs `mcp>=2.1`. On Python 3.10, mcp 2.0.0 and 2.0.1 cannot
  build the server at all: they refuse the `Required[...]` keys of its output
  schemas. The suite fakes the SDK, so the floors job, which installs 2.0.0 on
  3.10, had never built it for real.
- A site whose robots.txt was an empty file could not be fetched: the HTTP
  rung refuses an empty body, and the robots reader took that refusal for an
  unreachable robots.txt, which RFC 9309 treats as a full disallow. An empty
  robots.txt now allows everything; a 5xx with an empty body is still
  unreachable.


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
  (images, frames, `fetch()`, websockets, each hop of a redirect) through the
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
  another slot: a bookmarking site's first tag to the fourth place, and a
  preprint listing's ninth author who was a first author a month later onto
  the first-author column,
  which it then called vanished. A slot whose own place is still there now
  never moves to another slot of its group. Both were found by the drift
  benchmark, on four listings captured a month apart, each of the same
  template.
- `run` failed a page of the same template when one row renumbered a step in the
  middle of a path: one user of a question site with a second kind of badge, or
  one news story with a second author, turned `span>span.badgecount` into
  `span1>span.badgecount` for every row, and the field was found in none.
  Renumbering is now read at every step, not only the last.
- `heal` called a link vanished when the site tagged it with a new parameter:
  after a film chart's 2023 redesign every film's link carries
  `?ref_=chttp_t_1`. A link with the same path, whose parameters are all among
  the other's, is now the same link; `?id=2` is still another item than `?id=1`.
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
  their paths' alphabetical order. After a software directory's redesign a
  project's name is its heading in every row and its icon's alt text in the rows
  that have an icon, and heal took the icon. The place more rows carry now wins.

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
  `<meta charset>` -- a news site's article template -- or that declared no
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
  MediaWiki's `typeof="mw:Transclusion"` produced eleven empty records, and
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
  `name` over `headline` when only `name` is in the page's shown title (as an
  encyclopedia's is), and says which reader declared the `type`. Every record
  has a `source`. JSON-LD `@list` and `@set` are their items. An empty RDFa
  `vocab` resets the vocabulary.
- `HTTPS://` is an address at the command line and in the server.
- Records carrying no field are no longer reported.
- Induction reads the whole listing. Members were compared by the classes of
  everything inside them, so a rating written as `p.star-rating.Three` or a
  quote with five tags instead of two made a new kind of row: books.toscrape.com
  gave 6 of its 20 books and quotes.toscrape.com 3 of its 10. A member now
  matches its own tag and classes exactly and its inside loosely, by the tag
  paths it shares with the first member: 20 of 20 and 10 of 10, with a news
  aggregator's front page still 30 of 30.
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
- The stealth rung has left the automatic ladder. `fetch(url, stealth=True)`
  adds it back for a caller who wants it.
- An element whose whole text is its children's no longer carries a text fact of
  its own, so a wrapper around a single value stops reporting that value twice.
- A bad argument to `sluicer extract` now exits with our own message rather
  than with click's. A missing file and a directory are both covered.
