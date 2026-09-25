# Changelog

Dates are the day the work landed. Anything not listed here did not happen.

## Unreleased

### Added
- Every title, author and date scoreboard (WCXB, as served, news,
  trafilatura's set) scores `--visible` beside what the pages declare, as
  `bench/PREREG.md` fixed before it was first run on them: *declared* is the
  summary, *declared then `--visible`* adds a guess only where the summary has
  no answer. The guesses find more authors and dates -- on WCXB 0.649 and
  0.717 of them against 0.532 and 0.581, as served 0.752 and 0.855 against
  0.690 and 0.780, on trafilatura's set 0.548 and 0.701 against 0.468 and
  0.585, each called better by the paired comparison -- and invent: 33
  answers on WCXB's 511 pages, 15 as served, 15 on trafilatura's set, so the
  dates are right when answering less often on WCXB (0.823 against 0.917)
  and as served (0.701 against 0.734), both called worse. On the news pages
  little is left to guess. Each page counts what the guesses changed, their
  inventions apart, and pairs the second column with the first and with every
  other tool. The harness stops if `visible=True` changes the summary; it
  never did, and the guesses were the same under two hash seeds on all 2,124
  pages.
- html-to-markdown 3.14.3 (xberg-io, MIT) beside `sluicer.markdown` on
  trafilatura's set, from an environment of its own: it converts whole pages,
  so it finds 0.941 of the main-text snippets as markdown and 0.973 as plain
  text, and its precision is 0.56; `sluicer.markdown` is better on precision
  and F1 and worse on recall against each.
- anansi (mdowis/anansi, Apache-2.0, at `117fbe2`) on the drift pairs beside
  Scrapling, from an environment of its own, asked about the same item: right
  on 7 of 11, wrong on 3, nothing on 1; it healed on 2, silently.
- `sluicer fetch URL` prints the page as the ladder brought it back, to stdout
  or `-o FILE`, and each climb, where it landed, its status and rung to
  stderr; `--json` puts all of it, headers included, in one object.
- `headers=` and `cookies=` on `fetch`, `fetch_cached`, `crawl`,
  `extract_many` and `map_site`, and `--header 'NAME: VALUE'` (`-H`) and
  `--cookie NAME=VALUE` on every command that fetches: sent to the origin
  asked and never to another a redirect leads to. The User-Agent is never the
  caller's, and a header the transport writes is refused. A page the cache
  kept for a login is given back only to that login.
- `tests/live/browser_check.py` (headers and cookies to the site asked and no
  other, the proxy asked for, one browser) and `tests/live/extras_check.py`
  (each fetching extra installed and called for real) run in CI; the base
  install's job runs the live HTTP check with nothing else installed.
- `sluicer` on npm: the Python package itself, run in Pyodide 314.0.7, for
  Node 18 and later. `createSluicer()` installs the wheel the npm package
  carries, built from the same commit as the Python release of the same
  version, and hands `extract`, `compile`, `run` and `toMarkdown` to it; the
  answers are `dataclasses.asdict` of the Python ones, and the tests hold them
  to the native package's on 22 pages. Measured on an Apple M4 with Node
  26.1.0: it packs to 378 KB beside pyodide's 6.5 MB, `createSluicer()` takes
  1.30 s and downloads 2.25 MB (lxml and click, from jsDelivr) the first time,
  1.14 s and nothing after, and a warm `extract()` of the brake-pads example
  0.78 ms (`js/scripts/measure.mjs`). `docs/javascript.md` says how to
  install and call it, what it does not do -- it does not fetch: a page is
  handed to it, since Sluicer's fetching guards are not in this version --
  and which versions it pins. `.github/workflows/js.yml` runs the Node tests
  on Node 18, 22 and 24, fails when the committed native answers are not this
  commit's, holds the npm version to the Python one from both sides, and
  opens the try page in Chromium; its publish job, like PyPI's, runs only
  from a tag, in the `npm` environment, once `PUBLISH_TO_NPM` is true, and
  publishes with provenance through npm's trusted publishing, no token
  stored. Every action in every workflow is now held to a full commit by a
  test.
- A try page on the site (`try/`) that runs Sluicer in the reader's
  browser, in Pyodide, on HTML they paste: the wheel of the commit the site is
  built from, and the npm package's bridge. Nothing is sent anywhere: a
  Content-Security-Policy lets the page connect to its own site and jsDelivr
  only, every request it makes is made before Sluicer is ready, and a pasted
  page is text, never rendered. `scripts/check_try_page.py` opens it in
  Chromium, pastes 16 pages and requires the native answer on each; ready in
  1.8 s with an empty cache, after 8.9 MB (8.5 MB of it Pyodide and lxml).
- `sluicer serve` answers MCP over streamable HTTP at `/mcp`, for the clients
  that do not start servers over stdio, n8n's and Dify's among them: the MCP
  SDK's own transport over the same server, the same ten tools with the same
  schemas and bounds, on the same workers within the same `--timeout`.
  Stateless, POST only, JSON answers. The token and the `Host` check hold as
  for the other routes, and a request whose `Origin` is not the server's own
  is refused with 403 (`cross_origin`), as the transport requires. A tool call
  past its time is a failed call (`isError`, `timed_out:`); a refusal of the
  door is a JSON-RPC error whose `data` carries its code. Configurations for
  n8n and Dify are in `docs/agents.md` and `docs/http-api.md`, and CI's
  with-extras job connects the `mcp` package's own client to a real
  `sluicer serve` (`tests/live/mcp_http_check.py`).
- The image on the GitHub Container Registry: `ghcr.io/gi0tto/sluicer`, for
  amd64 and arm64, at each release's version and at `latest`. The release
  builds it from the tagged source on a runner of each architecture, and
  pushes it only after a client has listed its ten tools from it over stdio,
  its HTTP API has listed them too, it has been seen to run unprivileged, and
  its licences have been found in it. The push waits for the repository
  variable `PUBLISH_TO_GHCR`, as PyPI's waits for `PUBLISH_TO_PYPI`.
- The image carries, under `/usr/share/licenses/sluicer/`, Sluicer's LICENSE,
  NOTICE and LICENSES/, and in `THIRD-PARTY.txt` the licence text of every
  Python package installed in it, lxml's bundled libxml2 and libxslt among
  them; the build stops when a package installed no licence file.
- The repository is an Agent Plugin: `plugin.json` and `mcp.json` at its root,
  in the Agent Plugins 1.0 format that VS Code, GitHub Copilot, Cursor and
  Codex load, with the skill from `skills/` and the server started as
  `uvx --with "sluicer[mcp]==VERSION" sluicer mcp`. A test holds both files
  to the standard's closed fields, to `.claude-plugin/plugin.json` and to
  `server.json`'s command. Codex 0.157.0 installed it from a local copy, and
  Claude Code still loads its own plugin beside it.
- `sluicer-VERSION.mcpb`, the server as an MCPB bundle for Claude Desktop, on
  each release: 134 KB, no Python in it, the host installing `sluicer[mcp]`
  at that version with uv, with the two settings the server reads. The
  release stages it with `packaging/build_assets.py`, passes it through the
  official validator (`@anthropic-ai/mcpb` 2.1.2), packs it, unpacks it and
  lists its ten tools from it before attaching it, once PyPI serves the
  version and the repository variable `PUBLISH_RELEASE_ASSETS` is true.
- The documentation site serves `llms.txt`, in llmstxt.org's format, and every
  page's markdown at its path with `.md`. `scripts/docs_llms.py`, a hook of
  the docs build, writes both from the nav and each page's opening paragraph,
  so neither can fall behind; the suite holds the result to the format with
  the reader `sluicer audit` uses, and fails on a page the nav leaves out.
- `context7.json`: Context7 indexes `docs/` without the changelog, roadmap and
  contributing guide, and gives agents five rules; the suite holds each
  command, option, extra and name a rule gives to one Sluicer has.
- A GitHub Action, `action.yml` at the root: `sluicer audit` on the pages a
  workflow names, failing the step on a broken rule (or, with `fail-on`, on a
  warning, or never), each error an annotation with its rule, a summary table,
  and the counts and a JSON-lines report as outputs. Its inputs reach the
  script through the environment only, and each page is handed to `sluicer
  audit` after `--`, so one named like an option is a page.
  `docs/github-action.md` says how to use it;
  `.github/workflows/github-action.yml` runs it on pages its job serves on
  the runner's loopback.
- `sluicer-skill-VERSION.zip` on each release: `skills/sluicer` with the
  folder at the zip's root, the shape claude.ai's skill upload takes and what
  unzipping into `~/.agents/skills/` wants, the same bytes from the same tree.
- The Docker MCP Catalog entry, `packaging/docker-mcp-registry/servers/sluicer/server.yaml`,
  the file a pull request to docker/mcp-registry adds, with `SLUICER_MCP_TOOLS`
  as its one setting. The release writes it pinned to the tagged commit and
  attaches it as `docker-mcp-registry-server.yaml`; the registry's own
  validator (`cmd/validate` at 49b643c) passes it. No pull request is opened.
- A crawl asks a page again when it may answer later: a connection reset, a
  timeout, a name that did not resolve, a robots.txt nobody could read, or an
  answer of 429 or a 5xx. Twice by default (`--retries`, `retries=`), after
  twice the site's delay and then four times it, or its `Retry-After` when
  longer, never past `max_delay` or the time budget; never a 4xx but 429. A
  site whose page failed through all its retries is asked once a page until
  it answers. Each retry is in the page's line, `"retries": [{"reason",
  "after"}]`, on stderr and in the MCP crawl answers.
- A crawl's pace follows its sites: each request is timed, and a site that
  has lately taken longer to answer than its delay waits that long before
  the next request (each request's seconds averaged with the pace before,
  as Scrapy's AutoThrottle keeps one request in flight), never more than
  `max_delay` and never in place of the floor or the `Crawl-delay`.
- `--jobs N` on `crawl` and `batch`: how many sites are asked at once (4),
  each still one request at a time. Measured on eight local sites of five
  pages at `--delay 0.5`: 6.2 s with 1, 3.3 s with 4, 2.7 s with 8.
- `--format csv` on `crawl`, `batch` and `map`: a row per page, its columns
  fixed and its summary flattened into `summary.<question>` columns
  (docs/crawling.md lists them), or a row per address for `map`. A cell a
  spreadsheet would run as a formula is written after a `'`. A table cannot
  be resumed, and `--resume` says so. `sluicer.crawl.table` flattens a line.
- On a terminal, `crawl` and `batch` show one progress bar on stderr instead
  of a line a page; anywhere else, the line a page as before.
- `sluicer crawl URL --template sitemap` reads the pages a site's sitemaps
  list in one process, the delay kept between the map and the pages, with
  `--include`, `--exclude` and `--max-pages`; `--template shopify` reads a
  Shopify shop's products from `/products.json`, page by page and politely,
  a line per product with a `Product` record of Shopify's fields (source
  `shopify`, each with its JSON pointer) and a summary of them. From
  Python, `sitemap_pages()` and `shopify_products()`. Tested on local
  fixtures only.
- The twelfth MCP tool, `extract_many(urls, records=false, induce,
  respect_tdm)`: up to 25 addresses at each site's pace, within a minute,
  each page's summary and types, and its records when asked, as far as the
  75,000-byte bound allows, the heaviest pages' records left out first. The
  HTTP API serves it at `/v1/tools/extract_many`.
- A configuration file for the command line: `sluicer.toml`, or a
  `[tool.sluicer]` table in `pyproject.toml`, the nearest in the working
  directory or above it; or the file `SLUICER_CONFIG` or `--config FILE`
  names; `--no-config`, or `SLUICER_CONFIG` empty, reads none. Its keys are
  the options' own names -- `proxy`, `header`, `cookie`, `cache`, `max-age`,
  `no-robots`, `respect`, `delay`, `json`, `max-pages` and the rest -- at the
  top for every command that takes one with that value, and in a command's
  own table over that: `format = "jsonl"` at the top is `crawl`'s and
  `batch`'s, and `map`, which writes `json` or `csv`, keeps its own, where a
  value no command taking the key accepts is refused, naming them. The
  command line wins, then `SLUICER_PROXY` and `SLUICER_MCP_TOOLS`, then the
  file, then the built-in defaults; each flag a file may turn on has
  its opposite for one run (`--no-json`, `--robots`). A file is refused
  before anything runs, naming the file and the key, for an unknown key (with
  the nearest known), a key its command does not take, a value of the wrong
  type, or an option that belongs to one run (`--out`, `--stealth`,
  `serve --allow-unauthenticated` among them); no message repeats a proxy,
  header or cookie value. A file found by searching may be a repository's
  the user cloned, so it may not set `proxy`, `header`, `cookie`, `cache`,
  `host` or `no-robots`: only a file named by `--config` or `SLUICER_CONFIG`
  says what is sent, to whom, through what, where pages are kept, who
  reaches `serve` and whether robots.txt is obeyed, and a found file that
  tries is refused, naming the key. It must also be the user's and writable
  by no one else, through its mode or a macOS access list, which the mode
  does not show. `no-robots = true` from a file is said on stderr on every
  run. `docs/configuration.md` and `SECURITY.md` say all of it.
- `tomli>=1.0.3` on Python 3.10 only, to read that file: 3.10 has no
  `tomllib`. MIT, pure Python, no dependencies; 1.0.3 is the first that
  raises its own error for an impossible date, measured, and the floors job
  installs and asserts it.
- Shell completion for bash (4.4 and later), zsh and fish, click's own:
  `_SLUICER_COMPLETE=zsh_source sluicer` prints the script, and
  `docs/getting-started.md` says where each shell wants it. The suite
  generates the three scripts, has bash and zsh parse theirs where they are
  installed, and completes a command and an option.
- `sluicer.aextract` and `sluicer.fetch.afetch`: `extract` and `fetch` for a
  caller on an event loop, the same parameters, answers and exceptions, run
  on a worker thread of the loop's default executor so the loop keeps
  running. Politeness is the gate's, as for threads: six `afetch` of one site
  gathered at once read its robots.txt once and ask it one request at a
  time, the gate's delay apart, and coroutines, threads and crawls of one
  site wait for each other. Coroutines waiting for one site wait on the loop
  and take a thread only in their turn: with two worker threads and five
  fetches of one site queued, a sixth to another site starts at once. A
  coroutine cancelled while it waits asks nothing. `asyncio` is imported only
  when one is called. In `docs/getting-started.md` and the Python reference.
- `packaging/homebrew/sluicer.rb` and `packaging/conda-forge/recipe/recipe.yaml`,
  a Homebrew formula and a conda-forge recipe (the v1 format conda-forge asks
  of new recipes) for the base install, prepared and not submitted.
  `packaging/recipes.py` writes both from one `VERSION`, 0.8.0, and fills in
  the sdist's checksum from PyPI once the release is there, or from
  `--sdist PATH`; until then both carry a placeholder that says so.
  `tests/test_recipes.py` holds them to the script and to pyproject's
  dependencies, floors and licence. Checked on an sdist of this branch built
  as 0.8.0: `brew install --build-from-source` and `brew test` pass, and
  `brew style` and `brew audit --new --strict --online` pass on the same
  formula pointed at 0.7.0 on PyPI (on the committed file they fail only on
  the placeholder's address, which 0.8.0's publication replaces);
  `rattler-build build` with its tests on Python 3.11 and 3.14, and
  `conda-smithy recipe-lint --conda-forge`, pass. The formula installs
  click's completions for bash, zsh and fish. Sluicer does not yet meet
  homebrew-core's notability rules.
- Selectors a person writes, CSS or XPath. `sluicer.parse(html, url)` gives a
  `Page` whose `css()`, `xpath()` and `select()` return a `Selection` of
  values, `get()` and `getall()` as in parsel, each a `Selected` with its
  `value` and `where`, the XPath of its element as every other place Sluicer
  gives is spelt; an element's selection selects inside it, for a listing's
  rows. CSS takes Scrapy's `::text` (an element's own text nodes) and
  `::attr(name)`; `select()` tells the languages apart by how a selector
  begins, or by `css:` and `xpath:`. Values are read as an extractor reads
  them, spaces collapsed and `href` and `src` resolved. A selector that
  cannot be read -- a bracket left open, a pseudo-element Sluicer does not
  read, an XPath that counts instead of selecting, a function lxml does not
  know -- raises `SelectorError`, a `ValueError` naming it, never an empty
  selection. `sluicer select PAGE SELECTOR` prints each value, a tab and its
  place, or `--json`; it exits 1 when the selector gives nothing and 2 when
  it cannot be read, before anything is fetched.
- Extractors written by selector: `sluicer compile [PAGES] --select
  NAME=SELECTOR [--rows SELECTOR] -o FILE`, and `compile_extractor(pages,
  select=..., rows=...)`. The fields are where the selectors say; from the
  pages, when any are given, each field's share of rows, shape and reading,
  the rows' empty share and what the pages declare are learnt, and a run is
  held to them by the learnt extractor's own checks, the listing's by the
  same code, so the same drift fails in the same words. A selector that
  finds nothing, rows that are gone, a field found twice where it was found
  once -- an old price beside the new -- fail the run, exit 3, and a
  redesign never gives empty rows with exit 0. With no page given every
  check is at its strictest. The file is format 3; formats 1 and 2 are read
  as before, and a file with selectors marked 1 or 2 is refused, since an
  older release would check none of them. `heal` does not rewrite a selector
  a person wrote: one the new pages break is `broken`, a new kind among the
  losses, kept as written, and heal exits 3.
- The MCP tool `select_values(html_or_url, selector)`, the eleventh: each
  value with its place, a `count`, and `values_left_out` past the 75,000-byte
  bound. `compile_extractor` takes `select` and `rows`. A configuration file
  cannot set `select` or `rows`, as it cannot set `want`: each names one
  extractor's fields.
- `bench/stats.py`: how sure a scoreboard's number is, and how a difference
  is called, as `bench/PREREG.md` fixed them before any was computed: the 95%
  Wilson score interval of a rate, printed with its bounds rounded outwards,
  and a paired bootstrap over pages -- 10,000 samples drawn by
  `random.Random(20260924).choices`, every comparison from the seed again --
  whose percentile interval calls a difference better, worse or
  inconclusive. Its tests hold it to Wilson intervals published for known
  counts (Newcombe 1998) and to the bootstrap written out the slow way.
- `bench/timing.py` and `docs/speed.md`, speed and weight: every tool of a
  table timed in one run on one machine, five rounds whose order turns, each
  a fresh process in the tool's own environment that reads every page once
  untimed and times one pass of the call its scoreboard scores; the median
  with the fastest and slowest pass, seconds per page, pages per second, peak
  memory, install size and packages, and the machine, as PREREG's "How a
  second is measured" fixes it. Three tables: WCXB's and the news pages'
  four tools, and extruct beside `sluicer.compat.extruct`.
- `docs/conformance-jsonld.md`: the W3C JSON-LD 1.1 test suite's 50 tests of
  JSON-LD in HTML, run against Sluicer's JSON-LD reader,
  `sluicer.compat.extruct` and extruct by `bench/w3c_jsonld.py`. The suite is
  downloaded at a pinned commit, never vendored; each reader's answer is
  processed by PyLD with the test's options and compared by the suite's own
  rules, and PyLD reading the pages itself checks the harness. Every failure
  is listed with its reason, the rules fixed in `bench/PREREG.md` first.
- `bench/rdfa_conformance.py` and `docs/scoreboard-rdfa.md`: Sluicer's two
  RDFa readers and extruct's against the W3C RDFa test suite, as rdfa.info
  runs it, from `rdfa/rdfa.github.io` at a pinned commit (W3C Test Suite
  License and W3C 3-clause BSD License), downloaded into `bench/cache/rdfa/`
  and never committed. Every test written for HTML5 is run under each RDFa
  1.1 set it is listed in, 237 runs; each answer is read into a graph and
  asked the test's own SPARQL query by rdflib, in an environment of its own
  (`bench/requirements/rdflib.txt`) that no install of Sluicer needs. On RDFa
  1.1's 170 tests `sluicer.compat.extruct` passes 137 and extruct 132, which
  raises on five documents that write `about="[]"` or `resource="[]"`;
  `extract()`'s reader, which reads RDFa Lite into records that name no
  subject, passes 7, and 21 of the 162 runs that name a subject when the
  names are set aside. Held against the suite's expected graphs, subjects
  aside, that reader gives 99 of RDFa 1.1's values right and 1 wrong, a
  term with no `vocab` read as schema.org's, and misses 248, where
  `compat.extruct` gives 333 right and 13 wrong, extruct's own 13. The
  scoreboard files each test under a feature and says, for every test the
  reader fails, which part of RDFa it leaves out on purpose;
  `docs/known-limits.md` now names each of those parts.

### Changed
- **Upgrading.** A type of another vocabulary than schema.org that a page's
  JSON-LD names through a prefix of its context is now named by its
  address, in what `extract` gives and in what `compile` learns:
  `contao:Page` under `{"contao": "https://schema.contao.org/"}` is
  `https://schema.contao.org/Page`. An extractor written before 0.8 learnt
  `contao:Page`, and is read with either spelling, the prefix taken to the
  address the page's own context gives it, so it passes the page it was
  learnt from; `heal` does not call the type lost, and writes the address.
  0.8's own files hold a page to the address alone.
- Internal: `sluicer/cli.py` is a package, `sluicer/cli/`, a module per group
  of commands; every command, option, message and exit code is as it was.
- `cssselect` (1.2 or later) joins the base install, for the CSS selectors:
  one pure-Python wheel of 21 KB with no dependency, BSD-3-Clause, which
  Pyodide ships, so the npm package loads it beside lxml and click. The
  floors job checks it at 1.2, the first with `:is()`, `:where()`, `:has()`
  and types.
- `sluicer compile` with no page and no `--select` says it needs one of
  them, where click reported a missing argument; both exit 2.
- Fetching needs no extra. The base install fetches over plain HTTP with the
  standard library's `http.client`, `ssl` and `socket`, and brings `protego`
  for robots.txt: 21.7 MB installed against 21.6 MB for 0.7.1's base, which
  could not fetch at all (Python 3.13, macOS arm64). curl_cffi, which would
  have added 8.0 MB installed and a 13.5 MB wheel on Linux x86-64, and no
  wheel for Pyodide, is no longer used. Every guarantee of the curl rung is
  kept and tested on real HTTP bytes: 16 MiB after decompression, an
  announced length past it refused unread, one deadline for every wait on the
  connection, redirects one hop at a time with their scheme judged, the
  connection made only to the checked addresses, no proxy unless asked
  (`http://`, `socks5://`, `socks5h://`). It speaks HTTP/1.1 only, and its
  TLS handshake is Python's.
- One connection per site. The HTTP rung keeps the connection a page came on
  and asks the site's next page on it; a kept connection is used only while
  its address is still among the checked ones. Twenty pages of one local
  site: 20 connections before, 1 now; over HTTPS 33.3 ms before (0.7.1's curl
  rung), 29.4 ms with the pool off, 4.9 ms with it on; through the whole
  ladder, 55.6, 49.5 and 24.7 ms (medians of five runs, the gate's delay at
  0).
- Requests say `Accept`, and `Accept-Encoding: gzip, deflate`, with `zstd`
  on Python 3.14 or with `backports.zstd`. Brotli is not asked for, having no
  bounded decoder in the standard library; a body sent in it anyway fails the
  rung, and the ladder climbs.
- The browser rung drives Playwright directly, not through scrapling: one
  browser for the process, on a thread of its own, and a new context per page,
  told our User-Agent, no service workers and no proxy unless asked, the
  guard installed on each context. None of scrapling's defaults its own
  comments call anti-detection (no `--enable-automation`, a dark scheme, a
  doubled pixel ratio). `SLUICER_CDP_URL` drives a Chromium running
  elsewhere; `SLUICER_BROWSER=none` turns the rung off. Without Playwright the
  climb fails, is recorded with the install line, and the HTTP page comes
  back.
- A site's next page starts at the rung its last one needed. Once a page came
  back only from the browser, because plain HTTP's was a refusal, a challenge
  or a shell, the site's next pages start there, for the process and a day,
  and say so in their first climb. A five-page JS site crawled with the
  one-second delay: 10 document requests before, 6 now; 13.5 to 14.6 s with
  the new browser and no memory, 9.0 to 10.1 s with it (0.7.1, a scrapling
  browser per page: 18.1 to 107.3 s).
- Extras: `browser` (playwright) and `stealth` (scrapling) are new; `fetch`
  is deprecated and installs both, what it installed before; `mcp` no longer
  brings a browser: 95.7 MB installed against 379.5 MB, `sluicer[mcp,browser]`
  233.3 MB. Install the browser once with `playwright install chromium`.
- The stealth rung is the only place scrapling is used, still opt-in and one
  page at a time, never in a crawl, and never remembered as a site's rung. It
  sends none of the caller's headers or cookies.
- CLDR's month and weekday names are package data, `sluicer/calendar_names.json`
  (48 KB, the one file under the Unicode License v3), no longer a Python
  module of 2,731 lines; `sluicer.calendar_names` reads it at import and
  gives the same `MONTHS` and `WEEKDAYS`, all 1,568 and 1,140 entries
  compared. Importing it takes 1.0 ms with bytecode cached, as before
  (0.95 ms), and 1.2 ms without, against 11 ms to compile the module, which
  is what Pyodide pays (medians, Python 3.14, Apple M4).
  `scripts/cldr_calendar.py --check`, run in CI, fails when the committed file
  is not exactly what the pinned CLDR release gives.
- The WCXB and news scoreboards and `docs/extruct.md` print seconds only from
  `bench/timing.py`'s record, and refuse one that is not all one run of the
  commit they name, on a clean tree, of the versions they score. Each had
  printed the seconds each tool's harness summed on its own run: commit
  `b8f525e` re-timed Sluicer alone and printed its time beside the others'
  older ones. The products scoreboard and the drift page print no seconds.
  The scoreboards' generators no longer count one another's pages as
  uncommitted changes, so all can be regenerated at one commit.
- Every scoreboard prints how sure its numbers are and calls a difference
  only as the paired comparison does. The title, author and date scoreboards
  print each hit rate and share right when answering with its Wilson
  interval, and a table of Sluicer against each other tool on both rates,
  every row a difference, its interval and a verdict; the pages as served add
  every tool served against WCXB's copy of the same pages. Products compare
  F1s by Zyte's own matching and formula (`bench/zyte.py` imports them from
  its `evaluate.py`), beside Zyte's ±. SWDE and trafilatura's main-text
  snippets bootstrap over sites and over pages, since their trials are not
  independent. The sentences that ranked tools by their printed rates --
  "Sluicer's hit rate is below another tool's on...", "Sluicer is second of
  4, behind..." -- now say ahead, behind or not told apart where the
  verdicts do: on the pages as served, "fourth of 4, behind trafilatura
  0.855, metascraper 0.811, newspaper4k 0.786" on dates is now behind
  trafilatura and not told apart from metascraper and newspaper4k.
- `bench/gate.py` fails on a drop the paired comparison of today's outcomes
  with the baseline's calls worse, or one past the floor's tolerance, and
  reports a floor missed within both as held within noise, as PREREG's "What
  counts as worse" writes it; `bench/floors-pages.json` is the baseline.
  `--raise` wrote it from 0.7.1's results and raised four floors: trafilatura's
  set's date (0.584 to 0.585, 0.791 to 0.793) and SWDE's silent wrong answers
  (2,921 to 2,346 and 8,797 to 7,715 as ceilings).
- SWDE's scoreboard prints no seconds, as PREREG's "How a second is measured"
  says: its CPU times were measured once, not as that section fixes.

### Fixed
- A selector with `:has()` is refused where the installed cssselect is
  older than 1.5, which the declared floor allows and Pyodide ships:
  cssselect 1.2 to 1.4 translate `p + p:has(b)` to an XPath lxml
  rejects, and `p:not(:has(b))` to one that selects every `p`. The error
  says which cssselect it needs. Found by the CI job that runs the
  declared minimum versions.
- `--visible` reads a page whose boxes nest deep in step with its size.
  Each date asked every box round it whether it was hidden and whether it
  sat in a link, a `<time>` had its whole text read, every `<time>` inside
  it included, and a "By" line read the whole text of the boxes round it to
  learn it was longer than a byline: a chain of 2,000 nested `<time>`, as
  deep as the parser nests, took 1.3 s for 30 KB, and 1 MiB of such chains
  46 s; 2 MiB of nested "By" lines took 10.4 s. Each box is asked once now,
  a `<time>` holding more than a dozen elements is a container, as an
  element named as a date's already was, and a line's box is read only as
  far as its 80 characters: 1.1 s for each page, and the answers are the
  same on all 3,988 cached corpus pages, none of whose 11,062 `<time>`
  holds more than seven elements. Also in 0.7.1. Found while checking the
  second security review's item on author candidates, whose one XPath
  query per candidate is asked of three at most and grows with the page.
- A password in an address (`https://user:password@host/page`) is sent to
  the origin it names and never repeated. Every exception a fetch raises and
  its `url`, `Fetched.url` and its climbs, `fetch_page`'s and every tool's
  answer over MCP and the HTTP API (`url` on success, `message` and `url` on
  failure), the command line's messages, a batch's lines and the cache's
  entries write it `user:***`, as a proxy's password already was; the cache
  still keeps two logins' pages apart, by a digest of the whole address. Each
  repeated it, also in 0.7.1 (the second security review's `userinfo.py`).
  `--at` also put the whole address in the path of its request to the
  Wayback Machine, also in 0.7.1: the archive is asked for the page without
  it now, as are a site's `llms.txt` and TDMRep file read from a page's
  address.
- The page cache (`--cache`, `Cache`) keeps each page in a file only its
  user can read (0600), in a directory it makes 0700, whatever the umask.
  Under the usual umask they were 0644 and 0755, also in 0.7.1, so a page
  fetched behind a login with `--header` or `--cookie` was readable by anyone
  on the machine (the second security review's `cache_creds.py`). A cache
  directory that exists already keeps its mode: it is the user's, and may be
  shared on purpose. Each entry is written under a name of its own before it
  is moved into place, so two writers of one page no longer share a partial
  file. Windows has no such modes.
- A JSON-LD word a context defines as schema.org's namespace is schema.org's
  prefix however the address is written: `{"schema": "http://schema.org"}`,
  with no `/` to end in, and `{"schema": {"@id": "http://schema.org/"}}`,
  with no `@prefix`, left `schema:Product` and `schema:name` as written, and
  the page lost its type, title and price. JSON-LD 1.1
  reads such a word as no prefix, so PyLD keeps `schema:Product` as an
  address whose scheme is `schema` (in 1.0 it is `http://schema.orgProduct`):
  neither is anything a reader goes by, and a page that writes it means
  schema.org's. A word defined as any other address is a prefix only as
  JSON-LD 1.1 says, as before. All 3,976 cached corpus pages answer as
  before. Found by the second correctness review.
- A JSON-LD `null` past the 32 contexts a word is named through still clears
  them all. The contexts of nested graphs were cut to the outermost 32, so in
  33 graphs around one whose context is `[null, "https://schema.org"]`, the
  outermost naming FOAF's `name`, the Product's `name` was FOAF's and the
  page had no title; the contexts from the last `null` on are carried now.
  Past the 32, an object's words are kept as written, as under a context
  elsewhere, instead of named through the 32 that were read, which one past
  them could redefine; a context named by an address elsewhere counts toward
  the 32, as each one carried beside a graph does. All 3,976 cached corpus
  pages answer as before. Found by the second correctness review.
- A found configuration file its owner's own group may write is read. Ubuntu
  and Fedora give each user a group of their own and a umask of 002, so
  every `sluicer.toml` made there is 664, and each was refused as writable by
  others. A group counts as the owner's when every user whose primary group
  it is, and every member it lists, is the owner, as Debian's OpenSSH reads
  an `authorized_keys`; a group anyone else is in, a file writable by all, or
  a Linux file with an access list, whose group bits are the list's mask, is
  refused as before. Found by the second correctness review.
- A found configuration file whose macOS access list lets only its owner
  write it is read: `chmod +a "user:$(whoami) allow write"` counted as
  others writing it. One whose list lets anyone else write it is refused as
  before, now saying how to remove the entry (`chmod -a# N`, or `chmod -N`
  for the whole list) instead of `chmod go-w`, which changes the mode bits
  and leaves the list as it was. Found by the second correctness review.
- A value at the top of a configuration file is judged by every command that
  takes its key, whether or not the command's own table sets the key too.
  `format = "jsonl"` with `[crawl]` and `[batch]` each setting `format =
  "csv"` was refused, since map, which writes `json` or `csv`, was the only
  command left to judge it; and `format = "xml"` was accepted wherever every
  such command's table set its own. Found by the second correctness review.
- `sluicer.compat.extruct`'s Dublin Core copies an element's attributes as
  extruct does, pair by pair. Copied by key, an attribute a page names `{},`,
  `{a}b` or `{` was read by lxml as a namespaced name and raised `KeyError` or
  `ValueError`, or dropped the page's Dublin Core under `errors="ignore"`,
  where extruct 0.18 reads the element with it. The compatibility bench's
  pages answer exactly as before. Found by the second correctness review;
  also in 0.7.1.
- `extract(visible=True)`, `--visible` and the MCP tools' `visible` read a
  page whose date sits in a link to an address that is not a URL -- an
  unfilled template's `https://[domain]/story`, or `http://[::1` -- and a
  page at such an address. `urlsplit` refuses those with a `ValueError`, which
  was raised to the caller; such a link is now another page's, and such a
  page's address gives no date. All 3,976 cached corpus pages answer as
  before. Found by the second correctness review's fuzzer; also in 0.7.1.
- The browser's guard proxy serves only the browser it was made for. It
  listened on 127.0.0.1 with no credentials, so any process on the machine
  could use it, and through it the caller's own proxy, whose credentials it
  adds; each guard proxy now makes its own at random and answers 407 without
  them. Found by the review of the guard proxy.
- `--visible` chooses a page's text nodes in one pass. The XPath predicate it
  used, `string-length(normalize-space()) > 1`, cost libxml2 the square of a
  page's tail texts: 16,000 took 2.2 seconds, and four 3.6 MB pages held
  `sluicer serve`'s workers for about a minute and a half past their budget.
  The same nodes are chosen, on all 3,976 cached corpus pages. Found by the
  second security review; also in 0.7.1.
- A CSS descendant step costs the elements it can match, not every element
  under its ancestor. cssselect writes `div a` as
  `div/descendant-or-self::*/a`, every element under every div and then the
  children of each, which libxml2 gathers and sorts div by div: 1.2 seconds
  for `div a` and 3.4 for `div div div a` on a 390 KB page of the products
  corpus, and 35.7 seconds for an honest `div a` on a 5.3 MB page, past the
  30 seconds a selector is given over MCP. Such a step before a tag is now
  read as `div/descendant::a`, 17 ms, 70 ms and 0.3 seconds there, when the
  tag's tests ask what an element is and not where it stands among the
  step's elements, as every test cssselect writes does; one that says
  `position()` or `last()`, or is a number, is left as cssselect wrote it.
  The same elements come back in the same order: on 589 cached corpus pages
  and 44 selectors, from the page and from its rows, and in a property that
  draws trees and selectors with every pseudo-class that counts siblings,
  `:has`, `:is`, `:not`, `:lang` and every combinator. `sluicer select`,
  written extractors and the MCP tools read it so alike.
- The child process that evaluates an agent's selectors starts in Python's
  isolated mode: with `-c` alone it put its working directory first on its
  path, and a `pickle.py` in the folder `sluicer mcp` was started in ran when a
  selector tool was called. Its evaluation stops at 30 seconds whatever the
  call's budget, which let four hostile selectors hold `sluicer serve`'s
  reading workers for two minutes. Found by the second security review.
- A caller's selectors can no longer hold a server's workers. XPath lets one
  line cost the cube of a page's size -- `//p[count(//p[count(//p) > 0]) >
  0]` on a 9 KB page of 3,000 paragraphs runs for minutes -- and CSS's
  `p ~ p` took 110 s on 8,000; lxml evaluates both in C, where no thread can
  be stopped. Four such `select_values` calls to `sluicer serve --timeout 15`
  were answered 504 and kept every worker busy, so every later call was a
  504 too. The MCP tools that evaluate a caller's selectors --
  `select_values`, and `compile_extractor`, `run_extractor` and
  `heal_extractor` with an extractor written by selectors -- now evaluate
  them in a process of their own (`sluicer.isolated`), killed half a second
  before the call's budget ends over HTTP (a quarter of a budget under two
  seconds), or after 30 seconds (`sluicer.isolated.SECONDS`) whatever the
  budget, and such a call is answered `bad_input`, the selector's fault, over
  REST and at `/mcp` alike: stopped at the budget's end itself, the request's
  own timer won, and the call was a 504 `timed_out` that said to try again.
  Starting the process costs a call 77 ms, the median of 30 `select_values`
  calls on an idle Apple M4 with Python 3.14; a busy machine pays more. The command line and the library evaluate selectors as before, in
  their own process. `tests/live/api_check.py` sends four such selectors to
  a real server and then a harmless one, answered at once.
- A listing page with three or four values of a column that reads as an
  amount or a date is held to one of them at least reading so: three rows
  whose price says "Call" fail a price learnt as an amount, learnt or
  written. Under five values the `reads` check was skipped, since 0.7.1, and
  such a page passed. A page of one or two values is held to nothing of
  them, as before -- the last page of a pagination, one part priced "From
  £12.99" -- nor is a page of fewer than five to its shape: one row whose
  part is "Bosch Aerotwin AR601S" is no drift of names learnt as letters,
  and an extractor 0.7.1 wrote passes it as 0.7.1 did. One odd value among
  three still passes. The drift pairs and SWDE answer exactly as before.
- A thing declared on one of a page's repeated rows, or at most two levels
  inside it, is one of the listing's items; one declared deeper inside a
  repeated block is the page's subject, as in 0.7.1. Two pages of the
  products corpus stack their layout in alike tables, the product declared
  five levels inside one of them: taken for a row, it would have the tables
  learnt as the page's listing, 1,452 and 1,618 columns of site furniture,
  replayed with ok=True, where 0.7.1 learns no listing. Over the products
  corpus and the test fixtures (152 pages) compile learns what 0.7.1 learnt
  on every page, and quotes.toscrape.com, whose quote is declared on its
  row, keeps its listing. The drift pairs and SWDE never ask this (a listing is
  asked for, or examples choose it), and are unchanged.
- A page field learnt by its place is read after its label instead when
  another page given puts another labelled value there and says the
  example's own label elsewhere among the same labels: PEP 257 puts its
  Discussions-To where PEP 8 puts its status, and says "Status:" a row
  further down. With every value plain text nothing contradicted the place,
  and PEP 257's status read "Doc-SIG list" with the run passing; only a
  label the example's own page says counted. The label said outside that
  list says nothing of the place: a film that labels its director
  "Directors:" and has a crew table with its own "Director:" further down
  keeps the director where the other films have it, as 0.7.1 learnt it.
- A column of a hand-written listing that fewer than half the learnt rows
  carried -- a sale badge on three rows in ten -- fails a page none of whose
  rows carries it when that is under a 1% chance (`written.BY_CHANCE`): from
  13 rows for that badge, and 0.08% for twenty. A learnt listing checks such
  a column's presence nowhere; checked nowhere, a redesign that broke its
  selector would pass every page with exit 0. `heal` reports it `broken`,
  not `kept`, when the new pages' rows together make that as unlikely. Ten rows without the badge
  (2.8%) still pass, and a page of twenty on which truly nothing is on sale
  fails as a redesign would. The rows of one page are not what a badge comes
  by, though: a column a page it was learnt from carried in no row holds no
  page to it, so an extractor learnt from three category pages of thirty, a
  "Sold out" badge on half of one and on none of the others, passes the two
  without it (they were a 0.42% chance, taken row by row), and fails nothing
  for a badge truly gone from such a template either
  (`docs/known-limits.md`).
- A listing learnt or written from several pages no longer fails one of them
  for what the pages' rows said only when pooled. A column most rows carried
  was held to some row on every page, though a page it was learnt from had
  it in none; a column of three values was held to differ from row to row,
  though each page gave it one value in every row -- a brand, on each
  brand's page. The extractor failed the pages it was learnt from, with
  exit 3, since 0.7.1 for a learnt listing. Each column's file now says
  when a page it was learnt from carried it in no row
  (`"absent_on_a_page": true`) or gave it one value in every row
  (`"alike_on_a_page": true`), and that check is not made; a file without
  them, 0.7.1's among them, keeps every check.
- A hand-written field is taken for an address, with no shape or reading to
  hold it to, only when its values are read from an `href` or a `src`, not
  by how its selector's text ends: `.//a[@href]` -- the links that have an
  href, read as their text -- ends like an address and is text, held to its
  shape and reading, so a title that turns into a number fails; and
  `(.//a/@href)[1]` is an address, as it reads one.
- CSS's `::text` and `::attr()` are read as parsel, Scrapy's selectors,
  reads them, as the selector language says. After a space, `div.price
  ::text` is every text node inside the element -- `Price:`, `12` and `EUR`
  -- not the text of the elements inside it, `12` alone, and `h1 ::text` is
  the heading's text, not nothing. `ol ::attr(class)` reads the `ol`'s own
  class too. Text nodes come in the page's order, so `div.x::text` on a
  `div.x` inside another reads `A`, `B`, `C`, not `A`, `C`, `B`.
- `sluicer compile` refuses a field named twice, `--select x=h1 --select
  x=h2` or `--want x=a --want x=b`, exit 2, as an extractor file with two
  fields of one name is refused. The last one was kept and the first dropped
  without a word.
- `select_values` answers `bad_input` for a selector that selects a comment
  on the page it is asked of, and for one with a NUL or a control character,
  which lxml refuses with a `ValueError` of its own; both reached the agent as
  the SDK's bare "Error executing tool". Such a selector is a `SelectorError`
  wherever it is read: `selector()`, `Page.select()`, `sluicer select` (exit
  2) and an extractor's file.
- A hand-written listing whose rows selector cannot be read on one page --
  an XPath that selects a comment there, as `//li | //comment()` does -- fails
  that page's listing check, exit 3, with why. It escaped as a traceback:
  `sluicer run` and `heal` stopped with exit 1, and the other pages went
  unread.
- The check a sitemap or a feed passes before libxml2 reads it finds a
  declared entity or document type in every encoding libxml2 reads: UTF-16
  without a byte order mark and UTF-32, which libxml2 tells from the bytes of
  `<?` or `<`, were searched as they were, mostly zero bytes, and handed to
  the parser unchecked. The parser leaves entities unexpanded and the readers
  refuse a document type at the root, so nothing expanded; the check is there
  not to rely on that.
- The RDFa reader reads each element's `vocab` and `prefix` once. Every
  property read every `prefix` attribute of every element around it again,
  so 8,000 prefixes over 8,000 properties (478 KB) took 8 seconds, 26 on
  the reviewer's machine; 0.03 now. A prefix is looked up element by
  element, nearest first, as before, so nothing is copied into each one.
- An llms.txt heading line is read in time proportional to it. The pattern
  that read one took the text lazily and then spaces, marks and spaces to the
  end, so a line ending in anything else was tried at every split of it: "#
  a", 2,000 spaces and a "b" took 5.7 seconds, 4,000 a minute, in every
  `sluicer audit` and `audit_page` that reads the site's files. It is read
  by hand now, as the pattern read it (a test holds the two equal); 400 KB
  of such a line takes under a hundredth of a second.
- A JSON-LD block that went on past a closing `-->` or `]]>` -- the mark,
  whitespace, then anything else -- is read in time proportional to it. The
  pattern that took the wrapper off had two runs of whitespace side by side
  before the end of the text, which backtracked against each other: `-->`,
  40,000 spaces and a letter took 7.4 seconds in `extract()` and every
  command and tool that reads JSON-LD, on any page. The wrapper is now taken
  off from the end, as the pattern took it off (a test holds the two equal).
- The records' documentation says what a JSON-LD number becomes: the text
  the page wrote, `"41.90"` and not `41.9`, as every value in a record is
  text (`Field`, the getting-started guide). It always was, on purpose, and
  was said only in the reader's docstring. The W3C conformance page says it
  too; none of the suite's HTML pages writes a number.
- A JSON-LD record names its properties and types through the block's
  `@context`, as RDFa's are named through `vocab` and `prefix`: a schema.org
  word by its own name, however it is written (`schema:name`,
  `http://schema.org/name`, a prefix of the block's own), and another
  vocabulary's by its full address. A word a context mapped elsewhere kept
  its bare spelling, so a `name` defined as FOAF's was schema.org's `name`,
  the product's title, and `ex:foo` stayed a word no one could read. A word
  the context says nothing about is kept as written, as before: only
  schema.org's context is known, nothing is fetched, and a definition naming
  no address is not followed. A context's `@vocab` is read as JSON-LD 1.1
  and PyLD read it, through the prefixes and terms of the contexts around
  it and never its own: `{"@vocab": "ex:", "ex": ...}` names `ex:name`.
  schema.org's namespace is schema.org's however it is written, with a
  fragment's `#` too (`"@vocab": "http://schema.org/#"`), and `schema:` is
  schema.org's prefix unless the context defines `schema` as a word of its
  own. The audit names them the same way. Two words
  of one object that name one property -- `price` and `schema:price` under
  schema.org's context -- give the value of the one written as the name
  itself, wherever the object lists it, as 0.7.1 and every reader that goes
  by the key read it; failing that, the first written. A value's place
  points at the key the page wrote, `#/offers/schema:price`, never at the
  name the record gives it. Naming costs what the block's contexts cost:
  each is read once, as a layer over those around it holding only what it
  defines, never a copy of them, so a graph of 6,000 nodes each with a
  context of its own under 6,000 terms is named in a tenth of a second, and
  a word is looked up through at most 32 contexts, one declared past them
  not being read. Over the
  3,976 cached corpus pages the summary, `normalised` and conflicts are
  unchanged; records change on 5 pages, each a word of another vocabulary now
  named by its address: Contao's `contao:` properties and `contao:Page` type
  (2 pages), Parse.ly's `asciiDescription` (2), a CSV on the Web table's
  `csvw:` words (1).
- A node the JSON-LD reader takes out of a `@graph` keeps the block's
  `@context`, before any context of its own. Taken out without it, a term the
  block defined -- `ex:foo` under `{"ex": "http://example.com/"}` -- named
  nothing, to a JSON-LD processor or to sluicer: the W3C JSON-LD suite's
  tests e004, c004 and r004 showed it. A term a context defines as
  `{"@id": ...}` is no longer taken for a reference to a node, and a context
  is shared by the nodes it covers, never copied or paid for from the
  reference budget: the nodes of one graph that have no context of their own
  share one list of the graphs' contexts, of which at most 32 are carried. Over the 3,976 cached corpus pages, `extract()` and the
  audit answer exactly as before; the reader's answer gains the context on
  624 of them.
- `sluicer.compat.extruct` reads a JSON-LD block's text as extruct does:
  `json.loads`, then without a comment on its first line and without
  JavaScript's comments and trailing commas. It read blocks as
  `sluicer.extract` reads them, so a comment wrapped around the JSON, one
  never closed or never opened, a CDATA wrapper, a byte order mark or a
  comment left open at the end gave objects where extruct raises, and the W3C
  JSON-LD suite's tests e014 to e016 and r014 to r016, which want that
  refusal, failed. Such a block is now skipped and the page's other blocks
  kept, as a block that is not JSON already was; a block whose first line is
  a comment, which extruct reads, is now read too. `sluicer.extract` still
  forgives every one of them. A comment ends where jstyleson 0.0.2 ends it,
  a block comment at the first `/` after any `*` in it, so
  `{"a": /* x * y / 1 */ 2}`, which extruct refuses, is refused too: over a
  million random blocks of brackets, strings, slashes and stars the answer
  is extruct's. A comment never closed is read once, to the end of the
  block: 60 KB of `/*a` took 2.6 seconds.
- A crawl's `headers=` and `cookies=`, and `--header` and `--cookie` on
  `crawl`, `batch` and `map`, reached no request: the crawl's web was built
  without them. They now go with every page, robots.txt and sitemap, to the
  origin asked.
- Within a crawl, a site's listing pages stay on plain HTTP after one of its
  product pages needed the browser: the rung each part of the site (an
  address's directory) needed is kept beside the site's. Measured on a local
  shop, 3 of 7 listing pages were rendered in the browser, about 0.7 s each
  against 2 ms; now none, with the same 30 document requests.
- A page field no longer reads another field on a page it was learnt from.
  Learnt from PEPs 8, 20 and 257 with `--want status=Active type=Process
  created=05-Jul-2001`, the type and the date were read by their place in the
  header, and PEP 257's extra Discussions-To row moved both: its type came
  back "Active", its status, and its date "Informational", its type, with
  every check passing. Two causes. A label written with its colon in an
  element of its own, `Status<span class="colon">:</span>`, was two texts,
  `Status` and `:`, and the text before every value was `:`, said many times
  on a page, so no label was found; the colon is now the label's. And a place
  one page given puts after a label another gives one of its own values was
  not held to be contradicted; it now is, and the field is read after its
  own label, or refused with a message where there is none. On SWDE, 902
  wrong answers become right and 879 right ones flagged misses; mean F1
  0.849 to 0.850. The drift benchmark is unchanged: no silent failure, no
  false alarm. `heal` keeps no field at such a
  place and moves none to one. On the six PEPs of the registry's entry, the
  three fields are read right on every page. An extractor learnt before whose
  label was a colon standing alone, said once on every page, no longer finds
  it and fails its runs until it is compiled again.
- `compile --listing --want ...` no longer learns the page's own values
  when no repeated group holds every example: on quotes.toscrape.com, with
  the tags as the row's `<meta itemprop="keywords">` declares them, which is
  no column of a row, it learnt the first quote's text, read after "Login",
  and passed every page reading one quote of ten. A listing asked for and
  not found is now the error that names the example. Without `--listing`,
  a thing declared on one of the listing's rows -- one quote of ten in
  microdata -- is no longer the page's subject, and the listing is learnt;
  a page whose every row is declared already learnt it, as it does on
  quotes.toscrape.com, whose microdata the report blamed. A `<meta>` in a
  row stays no column, and `docs/known-limits.md` says why.
- PyPI's "Client Challenge" page, Fastly's answer to a client without
  JavaScript (3 kB, status 200), is recognised as a challenge: the ladder
  climbs past it, and a last rung that brings it back is the site refusing,
  not a page. So are the other interstitials the cached benchmark pages hold
  and nothing recognised: Imperva's (`/_Incapsula_Resource`), HUMAN's
  (`px-captcha`), Anubis's ("Making sure you're not a bot!", its title now
  read with its entities), and a "One moment, please..." waiting room met on
  four sites. On the 3,988 cached pages, 11 are now challenges, and each is
  one; `extract()` is unchanged on all of them.
- Without scrapling, 0.7.x could not fetch even over plain HTTP: `fetch()`
  imported scrapling's browsers before it built the HTTP rung, and raised
  `FetchExtraMissing`.
- The HTTP rung's name lookups are inside its twenty seconds.
- `sluicer serve`: a call that fetches nothing no longer waits behind calls
  that fetch. Four slow sites held every worker, and `extract_declared` on
  HTML handed in waited behind them, about 65 s with 0.7.1's fetch deadlines
  and until the sites answered before them. A call whose every page is handed
  in now runs on four workers of its own (`MAX_READS`).
- The image's wheel was built without NOTICE and LICENSES/, since the
  Dockerfile copied LICENSE alone: 0.7.0's image shipped schema.org's and
  CLDR's data with neither their licences nor the notice saying which files
  they cover.
- The HTTP rung never returns part of a body as the page. A server that
  announced a `Content-Length` and closed the connection before sending it
  all had what came returned with its status, 200, and kept by `--cache` as
  the page: the standard library's `read1()` answers an empty read at the end
  of the connection, which was taken for the end of the body. It is a
  `BodyCutShort`, a `ProtocolError` worth asking again, as is a chunked body
  without its last chunk; that connection is not kept, and the ladder does
  not climb past it: the browser, sent the same cut, returned half the page
  with 200. `tests/live/browser_check.py` counts the requests.
- A body whose framing came whole and whose gzip, deflate or zstd stream
  stops mid-way is `BodyUnfinished`, not the page it began, and not worth
  asking again at once: the server sent what it meant to. 0.7.1 returned the
  words it held as the page too. A whole body whose stream lacks only its
  formal end -- gzip's trailer or part of it, zlib's checksum, the final
  block after a flush -- is the page, as 0.7.1 and curl read it and Chromium
  does: it is taken when it ends where a whole stream could, checked by
  gzip's and zlib's checksums against what it gave. Delimited only by the
  close, the same stream is `BodyCutShort`, since nothing says the
  connection did not lose its end; 0.7.1 returned it.
- A raw deflate body whose first read brought one byte is decoded: whether
  deflate is zlib's or raw was decided on that byte, which is no zlib header
  yet, and the next read failed zlib's check.
- A body of thousands of gzip or zstd members is read in a loop: each member
  was read by a call inside the last one's, and 3,000 empty gzip members,
  60 KB, raised `RecursionError`.
- A caller's headers and cookies go to the origin the caller named, fixed
  before the first request, and to no other. The ladder read the robots.txt
  of the origin a redirect landed on through the rung built with them, which
  took that robots.txt for the address asked and sent it the caller's
  `Authorization` and cookies. A crawl sent them to every address of the
  site, so a crawl of an https site followed its http links and sent the
  cookie in clear text, and to its `www.` twin; a map sent them to a sitemap
  robots.txt names on any host; a batch sent them to a redirect's target,
  read in its own turn. Now a fetch sends them to the origin of its address,
  a crawl, a map and the pages of a sitemap to the origin they start at, a
  batch to the origins of the addresses it is given; in the browser a cookie
  set for an https origin is sent over https alone.
- robots.txt is read without the caller's headers and cookies, as anyone
  reads it: the answer is kept for the site for a day and given to every
  caller, so an answer read behind one login was given to every other
  caller, with that login or without it.
- The robots.txt of the origin a redirect lands on is read when only the
  port differs: a redirect from `https://example.com/` to
  `https://example.com:8443/` was taken for the same origin, and that
  server's robots.txt was never asked.
- A rung remembered for a site whose page is one to climb past -- a
  refusal, a challenge, an empty shell -- is forgotten, and the ladder starts
  again from plain HTTP, the remembered rung's page kept rather than asked
  for twice. The memory was dropped only when the remembered rung raised:
  measured with a real browser, once a site's script-drawn page had taught
  it the browser, its articles, which plain HTTP read whole and the browser
  was refused, came back as the browser's 403, every one of them, and a
  crawl's parts did the same.
- A crawl asks a page again only when what failed may pass: a connection
  refused or reset, a timeout, an answer cut short, a name the resolver could
  not look up for now, a robots.txt nobody could read, or a 429 or a 5xx.
  Every failed fetch was asked again: measured, a redirect loop was followed
  three times over, 33 requests, before the site was taken for failing, and
  so was an encoding the fetch cannot read. `FetchFailed.transient` says
  which it is, and a crawled page's `retryable`, and the MCP tools' and the
  HTTP API's, is false for one that would fail again.
- An empty 4xx or 5xx is that status's answer about the address, as the same
  status with a body is: the HTTP rung reported an empty 404 as a rung that
  failed, so a crawl asked for it three times and ended `fetch_failed`, not
  404, and the ladder climbed past an empty 404 to the browser.
- A `Retry-After` of digits that are not ASCII's -- `²`, which is a digit to
  Python's `str.isdigit` and not to `float` -- raised out of the crawl and
  ended a whole run of many sites at the first site that sent it. It is no
  `Retry-After`, as RFC 9110's grammar has it, and a wait is read as a year
  at most.
- A cache entry stored at a time still to come, or at none (`NaN`, text), is
  no entry: its age read as 0, so under `--max-age` it was given back without
  asking its site for as long as that lasted, forever for one planted a
  thousand years ahead. An entry whose status, headers or address are not
  what the cache writes is no entry either. Also in 0.7.1.
- A proxy address Sluicer cannot use is named without its password: the
  whole address was in the message, and so in the MCP server's log. The MCP
  server and `sluicer serve` refuse a `SLUICER_PROXY` they cannot use when
  they start, exit 2 and one line, where the first tool that fetched answered
  `internal_error` and logged the traceback.
- A map queues each sitemap once, however often its indexes name it, and
  reads a repeated address once: fifty indexes each naming the next and
  itself 20,000 times took 10.7 s to map, every repeat queued, taken off the
  front of a list and normalised, and 1.7 s now on the same machine.
- `sluicer map --time-budget SECONDS` stops asking for sitemaps once the time
  is spent, as `map_site(time_budget=)` and the MCP tool already did; the
  command line had no bound but the fifty sitemaps, each after the site's
  delay of up to a minute.
- The Shopify template reads a products.json nested past any shop: a
  product whose tags nested 5,000 lists deep raised `RecursionError` out of
  the crawl, and 100,000 did so from the JSON parser. What nests deeper than
  a page's JSON-LD is read is left out, and JSON too deep to parse is not a
  products.json.
- The browser rung launches Chromium in its sandbox. Playwright passes
  `--no-sandbox` unless told otherwise, and the browser that renders any page
  it is sent ran its renderers unsandboxed. A sandbox that cannot start --
  Docker's default seccomp profile, an Ubuntu that restricts user namespaces
  -- fails the launch with a message that says what to allow, or that
  `SLUICER_BROWSER_SANDBOX=0` runs it without one; SECURITY.md and the
  Dockerfile say what a container needs. `tests/live/browser_check.py` fails
  when the browser it starts has `--no-sandbox`.
- The guarded browser reaches no private address by the requests it makes
  for a page, which no route of the page sees. Measured with the guard
  installed, a speculation rule's prefetch and prerender -- written in the
  page, sent in a `Speculation-Rules` header, added by a script, aimed at
  another site -- and a WebRTC connection to a STUN or a TURN server each
  reached a private address. Every connection of a guarded page now goes
  through a proxy on this machine's loopback (`sluicer.fetch.browser_proxy`)
  that judges each host and port as the HTTP rung does and connects only to
  the addresses it checked, a proxy the caller asked for its way out;
  Chromium is told not to pass loopback by it, WebRTC's UDP, which no proxy
  carries, is off, and a page has no WebRTC. So the browser resolves no name
  itself, and DNS rebinding reaches nothing new through it either, as
  through the HTTP rung. A browser driven elsewhere (`SLUICER_CDP_URL`)
  cannot reach that proxy and is judged by the routes alone, as SECURITY.md
  says. `tests/live/guard_check.py` tries thirteen routes, these among them.
- `sluicer serve` closes a connection that has not sent a request's line and
  headers within ten seconds of opening, or of its last answer
  (`HEAD_SECONDS`), and a request that arrives with all 64 places taken
  closes the connections that have waited longest for a request until there
  is room for it. uvicorn times a connection out only between two requests,
  and counts one that has sent nothing toward its 64: 64 connections that
  sent nothing held every one it serves at once, and every later request,
  `/health` included, was answered 503 for as long as they stayed; closed at
  ten seconds and each opened again at once, they kept 60 probes of 60 over
  a minute at 503. Now 64, 128 or 256 such connections leave 60 of 60
  answered 200, and it answers 503 only when 63 connections are inside a
  request. Connections that send nothing never close each other.
  `tests/live/mcp_http_check.py` holds 64 open, each opened again when
  closed.
- A CSV cell is judged as a spreadsheet may read it: behind the spaces,
  line breaks and no-break spaces it may trim, with a fullwidth `＝` or `＋`
  as the sign it looks like, and with a number made of ASCII digits. Only
  the first character was looked at, so ` =1+1`, `\n=1+1` and `＝1+1` were
  written as they came.
- The private-address filter refuses what Python's `is_global` counts as
  global and the web is not: multicast (`224.0.0.0/4`, `ff00::/8`), SIIT's
  IPv4-translated addresses (`::ffff:0:a.b.c.d`), judged by the IPv4 address
  they carry as a mapped one is, SRv6's segment identifiers (`5f00::/16`)
  and the deprecated site-local range (`fec0::/10`). Also in 0.7.1.
- A crawl asks 32 sites at once at most (`MAX_CONCURRENCY`) and a page ten
  more times at most (`MAX_RETRIES`), whether `--jobs` and `--retries`, the
  library's `concurrency=` and `retries=`, or a `sluicer.toml` asks for more:
  a file in a directory above is read by every command run below it, and one
  asking for a million jobs started a thread for every site of a batch.
- The HTTP rung reads past an interim answer -- a 102, a 103 Early Hints --
  to the answer it precedes. The standard library skips a 100 and no other:
  a 103 came back as the answer, empty, its connection was kept with the
  real answer unread on it, and the next request to the site was handed
  that answer as its own -- in a crawl, `/p/p3` recorded Product p2 with no
  error, and `fetch` returned the site's robots.txt as a page. A 101 nobody
  asked for is a `ProtocolError`, and its connection is not kept. A 204 that
  names a length for a body is not kept either: the bytes sent after its
  headers were read by the next request as the start of its answer.
  `tests/live/http_check.py` sends both in a segment of their own.
- A network that failed for now is worth asking again: no route to the host
  or its network (`EHOSTUNREACH`, `ENETUNREACH`), one of them down
  (`ENETDOWN`, `EHOSTDOWN`), a connection the network dropped (`ENETRESET`),
  a host with no address to connect to, and the browser's
  `net::ERR_ADDRESS_UNREACHABLE`. None was counted as transient, so a crawl
  never asked a page again when the network flapped once, and the MCP tools
  said `retryable: false`. An aborted connection and a broken pipe already
  were, as the `ConnectionError`s Python raises for them.
- The failure a robots.txt's 5xx ends a fetch with says what the 5xx means:
  RFC 9309 reads it as nothing allowed until the robots.txt answers
  otherwise, and the robots.txt was asked without the caller's headers and
  cookies, so a site that answers 500 to anyone not logged in has its
  logged-in pages refused. It said only that the robots.txt answered 500.
  Nothing on such a site is fetched, as in 0.7.1.
- `run` and `heal` do not hold an extractor to a page the site answered
  with a status outside 2xx: they exit 2, naming the status. An empty 503
  was replayed as the page, and `run` exited 3 blaming the extractor's
  contract and `heal` 3 for the fields it lost, neither naming the status.
  `extract` on an empty error page names the status, where it suggested
  `compile --want` on the site's error. A crawl and the MCP tools record
  the status as before.
- RDFa: a property on an element whose `rel` or `rev` names a term takes the
  element's words, not its address, which is the link's: data-vocabulary.org's
  breadcrumbs, `<a href="/" rel="v:url" property="v:title">Home</a>`, gave
  the address as the title, on 10 of the 3,976 cached corpus pages, and now
  give `Home`, as RDFa Core's processing rules and the W3C suite's test 0334
  say.
  A `rel` of HTML's own words, such as `nofollow`, still leaves the address
  to the property, as HTML+RDFa says (test 0312). No summary changes.
- RDFa: a `typeof` element whose `property` has `content` or `datatype` is a
  subject holding that property, as RDFa Core's processing rules say and the
  W3C suite's test 0317 checks; it was read as a link to an empty subject and
  dropped. A `datatype` asks for the words, never the element's address.
  Drupal 7 writes a node's author and tags this way, `<span
  typeof="sioc:UserAccount" property="foaf:name" datatype="">`: over the
  3,976 cached corpus pages, 8 pages gain 36 records -- 13 accounts and
  people with their names, 23 tags with their labels -- and one record, a
  tag, gains its label. That tag's page had it as its summary type,
  `skos:Concept`, since OpenGraph's fields were folded into it; with seven
  tags the page is a listing of them, and its type is `og:type`'s `article`.
  Nothing else in `extract()`'s answer over the corpus moves.

## 0.7.1 - 2026-09-25

### Added
- `docs/stability.md`: what is stable before 1.0 (`extract()` and
  `Extraction`, the summary's questions, the extractor file and its exit
  codes, the MCP tools and their documented fields), what is experimental
  (crawl, warc, feed, audit, diff, induce, `--visible`, the HTTP API), the
  deprecation policy -- one minor release of warning, in this changelog,
  before a stable part is removed -- and that one person maintains Sluicer on
  a best-effort basis.
- `extract` and `inspect` of a page that gives nothing say what may still read
  it: `--induce` for the rows it repeats, `--visible` for the byline and dates
  it shows, and `sluicer compile PAGE --want NAME=VALUE` for the fields a
  person can point to, leaving out the options already given.
- `fetch(proxy=...)`, `SLUICER_PROXY` and `--proxy` on every command that
  fetches: the proxy every request goes through, the HTTP rung's and the
  browsers'. Crawls, maps, batches, the cache, the archive, the MCP server and
  the HTTP API read `SLUICER_PROXY`.

### Changed
- **Upgrading.** Fetching through a proxy now needs `SLUICER_PROXY` or
  `--proxy`: `HTTPS_PROXY` and `HTTP_PROXY` are no longer read (see Fixed).
  A challenge page and a 402 Payment Required are now errors where the page
  used to be returned: `fetch()` raises `SiteRefused` or `PaymentRequired`,
  and the MCP server and the HTTP API answer the new codes `refused_by_site`
  and `payment_required`.
- The README is half as long and leads with one thing: extractors that fail
  loudly when a site changes, with the redesign demo at the top. It keeps the
  quick start, one benchmark table and a "When not to use Sluicer" section;
  the FAQ and the principles moved to `docs/faq.md`. A test checks every
  number in the benchmark table against the scoreboard it links to.
- The benchmark's date rule no longer depends on the day it runs: dateutil
  filled a part a date does not write with today's, so "March 2021" matched
  2021-03-24 on the 24th of a month only. A date is now a hit when the answer
  writes every part the label writes, alike; dots are read day first, slashes
  month first, and with a UTC offset on both the answer is read in the
  label's (`bench/PREREG.md`). It changes five outcomes on the news
  scoreboard and trafilatura's set, all from wrong to hit; this release's
  scoreboards are scored by it.
- Every sentence a scoreboard's generator writes about its results is
  counted from them. `bench/run.py` wrote "Sluicer gives none where the page
  states none" beside a table in which it invented 42 authors and 8 dates,
  and "authors and dates are where the gap is" whatever the run; the products
  scoreboard's error classes, the news scoreboard's "most of the authors",
  trafilatura's set's "nearly every snippet", the extruct page's "raises on
  none" and "for the same reasons", and the served scoreboard's capture
  scores were written once by hand and printed on every run. This release's
  scoreboards are the first written this way.
- `sluicer --help` lists the commands in four sections -- Read a page, Whole
  sites, Extractors, Servers -- instead of one alphabetical list.
- The suite runs in a random order (pytest-randomly, now a development
  dependency), and CI seeds the order with the run's id. Two tests passed only
  in file order: one cleared the `mcp` package from `sys.modules` but not
  `mcp.server.mcpserver`, and one failed after a test that reloaded
  `sluicer.markdown`, which left a second `MarkdownExtraMissing` class the CLI
  did not catch. No test reloads a module now.
- `compile`, `run` and `heal` parse each page once. They parsed it again to
  read what it declares, and `heal` again for each part it healed. The groups a
  page repeats and its text nodes are worked out once per page while learning,
  not once per example, and a label is looked up rather than searched for on
  every candidate, which made a page of labelled rows quadratic: 4,000 rows
  took 1.86 s, now 0.19 s. On 11 of SWDE's development sites, three seed
  pages each and 200 pages run, best of three runs interleaved: `compile`
  1.14 s to 0.52 s, `run` 278 to 321 pages a second. Every output is the
  same: the extractors, the runs and the heals there, SWDE's development half
  answer for answer, and the drift benchmark's results.

- `extract()` is 25-41% faster on the benchmark corpora, with the same
  answers byte for byte: the microdata reader stops at once on a page with no
  item, links are resolved only for the relations read, an address's spaces
  are found by one search in C, and the `<meta>` tags are scanned once a page
  instead of once for each reader and summary question that reads them.

- The sdist is 0.78 MB, from 1.98 MB. It leaves out `uv.lock`, which pins the
  development environment, the CI workflows, and the pictures under
  `docs/assets`, which PyPI shows from the repository because the README names
  them by absolute address. It still carries the source, the tests and all they
  read, and the suite passes from it unpacked; the wheel is unchanged.

### Fixed
- A month named like an English weekday is a month. A date's leading "Sat" or
  "Sun" was taken off as Saturday's or Sunday's, and Hausa writes September
  "Sat": "Sat 1, 2000" was no date. Where the rest reads as no date, the
  whole text is read again with the word as its month. Found by the weekly
  fuzz profile; no answer changed on the 5,976 cached corpus pages.
- A robots.txt is parsed once, not once for every address asked about it:
  its text was remembered and parsed again each time, and a crawl asks for
  every page it reads, 2.5 seconds each for one of 16 MiB. The last 64
  parsed are kept, by their text. Found by review.
- `--visible` reads a page in step with its size. Each "By" line and each
  date read the whole text of the boxes round it, and a box that holds them
  all was read once for each: 8,000 in one article, 583 KB, took 22 seconds.
  Each element's text is now read once per page, and a date's label is read
  from the words just before it rather than from its box's whole text. No
  answer changed on the 5,976 cached corpus pages. Found by review.
- Every extractor `compile` writes is one `from_json` reads. lxml 6 keeps
  tags such as `<a@b>` and `<p]>` as the page wrote them, and compile wrote
  paths such as `div.product>a@b.price`, which the reader refused as no path
  (0.7.0 read it back, as the attribute `b.price` of an `<a>`); `<x[1]>` made
  compile raise a bare `ValueError`, and a row's tag `<x.y>` another, where
  it found no rows of its own kind. A row carrying Tailwind's `@container`
  was written `li.@container.item`, refused too. Such a character in a tag is
  now written as `%` and its code, `a%40b`, and a class that holds one is
  left out of the row's kind; other paths and kinds are as they were. A
  property draws tags and classes of those characters and holds compile's
  output to reading back as it was. Found by review.
- A numbered listing is the box its heading says. Learnt at
  `section.box[2]`, the books among three boxes, a page with the first box
  gone and another added at the end still had three, and the run read the
  second, the recent books, 6 rows of another listing, and passed; a box put
  in the books' place passed too. And a box added after the books, the
  second still theirs, failed with four boxes where there were three. An
  extractor now learns the text each numbered step's element begins with,
  its rows aside, when every page learnt agrees on it and no other element
  of its kind begins so (`marks`): a step whose element begins so is the
  listing, however many boxes the page has, and one whose element does not,
  while another does, fails the `listing` check. Where the heading is not
  learnt, or the page says it on no box, the count decides, as before. A
  file without `marks` is read as before. Found by review.
- A page field whose row moved fails however the page says its label. The
  check asked for the label said once, exactly as learnt: rows swapped, and
  a second "SKU" anywhere on the page, or the label written "SKU:", read the
  weight, "3 kg", as the SKU and passed; with fewer than five pages learnt
  no shape guarded it. A page that still says the label, once or more, its
  colon and its case aside, and not right before the place now fails the
  `field` check. A page that no longer says it is read at the place, as
  before. Found by review.
- `diff` reports a price JSON writes with an exponent as the number it is:
  `1500` before and `1.5e3` after, on a page that declares no currency, was
  `changed`, since the `e` left once the digits and points were taken away
  was read as a currency sign. A number written with an exponent now has no
  sign, and the two are `rewritten`. Found by review.
- A date's offset is only a zone the date writes. `email.utils` reads any
  word after the time as the zone, and once "PM" was read as the half of the
  day it no longer held that place: "May 24, 2026 10:05 am 4 min read" was
  at +00:04, on a page of the news corpus. A word after the time that is
  neither a signed offset, a zone `email.utils` knows by name, nor the
  year ends the date, which has no offset. Found by review.
- A tag a page opens and never closes costs what the page costs. Telling a
  challenge page from content stripped tags with a pattern that looked for a
  `<script>`'s end tag again from every place one opened, and read the
  `<title>` the same way; sniffing a page's encoding dropped `<!--` comments
  alike. Unclosed, each asked the rest of the page every time: 256 KiB of
  `<script>` took 76 seconds per rung, after the fetch and outside every
  deadline, and on `sluicer serve` it held the worker and slowed `/health`;
  64 KiB of `<!--` took four seconds. Each is now one pass, with the same
  result as the pattern on 6,000 drawn pages and the 3,976 cached corpus
  pages. Found by review.
- Four readers kept each name once by asking a list, for every new name,
  whether it held it already: the head's canonicals (and so the audit's), a
  JSON-LD author list, an RDFa attribute's terms and a robots.txt's
  `User-agent` lines. Forty thousand of any took about four and a half
  seconds, and the sixteen mebibytes a fetch allows would have taken
  minutes; each now takes 0.02 to 0.1 s. The answers are the same, in the
  same order: `extract()` gives byte-identical output on the 5,976 cached
  corpus pages. A fifth, a page's oEmbed links, was found by review
  and fixed the same way.
- The scoreboards say which pages Sluicer's rules were made on. Five of the
  six, and the drift benchmark, had rules written, measured on their pages and
  kept because the numbers there rose -- `b86aa19` was "Measured on WCXB's
  511-page test split", `9548a35` added SKU names to pass extruct on the
  products benchmark -- while `bench/products.py` said "Nothing is tuned to
  these pages" and `bench/PREREG.md` called the scoreboards held out. PREREG
  now lists the commits per scoreboard, each generator opens its page by
  saying so, and only SWDE's held-out half, less its camera sites, is called a
  held-out test.
- The README's facts: the dates chart's alt text said metascraper found 0.384
  of the dates and was right on 0.271 where the chart and the scoreboard say
  0.811 and 0.573; the README said WCXB's pages are read in 1.4 s where the
  scoreboard says 1.50; and "five of these scoreboards" measure title, author
  and date where four do. `scripts/readme_assets.py` now writes both charts'
  alt texts and the timings from the scoreboards it draws the charts from, and
  a test fails when the README falls behind them.
- SECURITY.md and the skill said `fetch_page` returns up to 200,000
  characters; it has returned at most 60,000 since 0.7.0.
- The README said exit code 1 meant "nothing declared", and a page with only a
  `<title>` exits 0. The code is what was meant: the title is declared, read
  into the summary with its source, and a script handed the page has an
  answer. The README and the skill now say a `<title>` alone counts.
- No MCP answer weighs more than 75,000 bytes of JSON (`MOST_ANSWER_BYTES`),
  whatever the page. Only `extract_declared`'s records were bounded: a
  200,000-character `<title>` made a 200 KB answer even with `records=False`,
  60,000 characters of Chinese a 180 KB `fetch_page` slice, 60 products a
  570 KB audit, and a feed, a map, a crawl or an extractor's rows had no bound
  in bytes at all. Each tool now leaves out what its answer can do without and
  says what: the records, then `conflicts_left_out`, then the heaviest summary
  answers named in `summary_left_out` (and `visible_left_out`,
  `normalised_left_out`, `links_left_out`); `items_left_out`,
  `urls_left_out`, `rows_left_out`, an audit's `records_left_out`,
  `page_left_out` and `other_agents_left_out`; a crawl's heaviest summary
  answers per page, then `pages_left_out`; a page's or markdown's slice is
  shortened and `next_offset` says where the rest starts. An answer that
  cannot be cut, such as an extractor learnt from a page with a huge value, is
  `too_large`.
- `sluicer mcp --tools bogus`, and `SLUICER_MCP_TOOLS=bogus sluicer-mcp`,
  printed a traceback; they print the one line that lists the ten tools and
  exit 2, as a wrong option does.
- A column or an answer made only of characters with no letter, digit,
  punctuation or symbol in them, a combining accent alone, is learnt with no
  shape. It was learnt with the empty one, and `compile` wrote a file that
  `run` refused.
- An extractor file is checked value by value when it is read. Edited by hand
  to `"missing": "nan"`, a field's presence was never checked again: no
  comparison is true of NaN, and the run passed a page without the field. So
  did a `missing` of `true`, `1.5` or `"0"`, an `empty` of 5, and rows or
  counts written as text. Shares must be numbers from 0 to 1, rows two counts,
  shapes made of L, N, P and S, lists lists, names one per field and paths
  paths; any other file is refused with a message naming the value, and the
  command line exits 2, as it does for a file that is not JSON.
- `heal` never moves a listing chosen by examples on one coincidence. With
  its old place gone and every item new, one related product costing what a
  book used to drew the listing of prices into the related strip, a move and
  no loss, so it was written. A group must now hold at least half of one
  column's old values to be where the listing went; otherwise it is lost.
- `heal` keeps a listing chosen by examples where it is while it keeps its
  contract there. On a page that had not changed it moved the listing to a
  sidebar listing the same books, and wrote it; on the same template with
  every item new it reported the listing lost. And a lost listing now stays in
  the healed extractor as it was: written with `--force`, an extractor without
  it passed every page, those with no rows at all among them.
- `heal` never moves a page field into another product's place. After a
  redesign that also changed the product's price, a related product costing
  the old price drew the field into the related strip, and the healed
  extractor read that product's price and passed. A page field now moves only
  among the page's own places, never its navigation, asides or listings, and
  a move two own places claim, reading different values, is `ambiguous`. A
  heal of page fields on pages that declare nothing no longer stops with
  "nothing to heal from".
- A box of the same kind inserted before a numbered listing fails the run.
  The listing at `section.box[2]` read the box that became second, 4 rows
  instead of 12, and passed, although the docs promised a strip inserted
  before a listing is caught. An extractor now learns how many elements
  matched each step of its listing's path on the pages learnt (`siblings`),
  and a numbered step with more or fewer of its kind fails the `listing`
  check. A file from 0.7.0 has none and is read as before. The drift
  benchmark's outcomes are unchanged: 23 survived, 21 failed loudly, none
  silently, no false alarm.
- `diff` reports a price in another currency as `changed`, not `rewritten`:
  `£41.90` and `$41.90` are the same number, and were read as noise. A price's
  currency is the one its sign or code names, `£` and `GBP` alike, else the
  one the page declares; `$`, which names several, is only itself.
- A page field read by its place fails when its row moved. Learnt from pages
  that agreed on the SKU's row, a page with its table's rows in another order
  read the weight, "1 kg", as the SKU and passed. A field read by its place
  now learns the label every page given puts right before it, once -- text
  ending with a colon, or in a `<th>`, `<dt>` or `<label>` -- and a page that
  says the label once, before something else, fails the `field` check; `heal`
  then reads the field after its label. On SWDE's development half this flags
  575 wrong answers that passed (2,921 to 2,346 unflagged) and no right one;
  a label taken from any text, links included, flagged 1,204 right answers.
- Two examples one column holds are no listing. `compile --want price=41.90
  --want sku=BP-1` on a product's table, the price and the SKU in two of its
  rows, learnt a listing of the table's rows with both columns the same `td`,
  and a new page read price "Bosch", sku "Bosch" and exited 0. Each example
  now needs a column of its own; with none, the examples are the page's own
  values, and the price and the SKU are read where each sits.
- An example is one amount however many zeros it is written with: `--want
  price=8` finds the page's `£8.00`, on the page, in a listing's rows and after
  a label. Amounts were compared as the text `amount` gives back, `8` against
  `8.00`, and the comparison was written out three times; it is one now, and
  numeric.
- A redirect can no longer take a fetch off the web. The HTTP rung followed a
  `Location` to any scheme its libcurl speaks: with the defaults every command
  has, a server answering `302 gopher://127.0.0.1:6379/_SET...` had Sluicer send
  those bytes to a Redis on the same machine, and `302 file:///etc/hosts` made
  `sluicer markdown` print the file. Every hop must now be http or https, private
  addresses allowed or not, curl is told to speak nothing else, the ladder
  refuses an address off the web before any rung, and a page that landed off it
  is refused (`AddressRefused`, `refused_address`).
- The HTTP rung's twenty seconds now cover the body. curl_cffi turns a timeout
  on a streamed response into "under a byte a second for that long", so a
  server sending eight bytes a second held a request for as long as it kept
  sending, and four of them held every worker of `sluicer serve`, which then
  answered nothing, calls that fetch nothing included. One address -- connecting,
  every redirect hop, every byte -- now ends by `HTTP_TIMEOUT_SECONDS` with a
  `TimeoutError`. SECURITY.md said a map or a crawl took "a minute each"; it
  stops starting requests after a minute, and now says so, with each request's
  own bound.
- robots.txt is read as text. The fetch ladder passed it through the HTML
  parser, so a line like `Disallow: /a<b` opened a tag that swallowed every
  rule after it, and pages the site disallowed were fetched; `&amp;` in a rule
  became `&`. The audit already read the file raw, so the two could disagree
  about one robots.txt. Only a body that is a whole HTML document, a browser's
  rendering of a text file, has its text taken out.
- A robots.txt group applies to Sluicer when it names Sluicer's product token,
  as RFC 9309 says, not when its name is found anywhere in the user agent:
  `User-agent: https`, `github` or `com` matched
  `Sluicer/0.7.0 (+https://github.com/Gi0tto/sluicer)`, so another crawler's
  rules refused Sluicer and its `Crawl-delay` paced it. `PRODUCT_TOKEN` is
  what the ladder, the crawler and the audit's site files ask with.
- The page cache never keeps a challenge page. When every rung got a
  "Just a moment..." page served with 200, `--cache` kept it and gave it back
  as the page, for `--max-age`, without asking the site; the docs said a
  challenge was never kept, and now it is not.
- A challenge page is never an answer. When the last rung also got one, or a
  cheaper rung got one and the rung above it failed, the ladder returned it
  as the page and the MCP server answered `ok: true`. It now raises
  `SiteRefused`, a `FetchFailed`, answered as the new error code
  `refused_by_site` (HTTP 403, not retryable) by the MCP server, the HTTP API
  and a crawl's page.
- A 402 Payment Required is an answer, not a page. Its body was extracted as
  the site's, and when it looked like a challenge the browser was sent to ask
  again. Any rung answered 402 now raises `PaymentRequired`, a `FetchFailed`,
  and no other rung is asked; the MCP server, the HTTP API (402) and a crawl's
  page say `payment_required`, not retryable. Sluicer never pays.
- One request at a time per site now holds for the whole process. Two crawls
  of one site at once asked it in pairs 0.000 s apart, and parallel MCP
  `extract_declared` calls -- the SDK runs each on a thread -- arrived within
  3 ms of each other, each reading robots.txt again, while the docs promised
  one request at a time with its delay. Every fetch of the real web now holds
  its site in `sluicer.fetch.gate`: a crawl, a map or a batch for each
  request, with its delay; a single fetch, from the command line, the MCP
  server or the HTTP API, for its whole visit, a second after the site's last
  request. Measured on a local site, four parallel `extract_declared` calls:
  8 requests 0.000 s apart before, 5 requests a second apart now.
- `crawl --resume` and `batch --resume` read the file before they touch it.
  They cut an unfinished last line off first and checked the file was a
  crawl's after: pointed at a file of notes, `--resume` destroyed its last
  line and then refused it, and a file with no newline at all was emptied and
  crawled into. The file is now accepted first -- every line a page, the last
  one the start of a page's line, the order this crawl's -- and only then is a
  line a stopped crawl left half written cut off. A file refused is left as it
  was.
- No proxy is used unless one is asked for. libcurl read `HTTPS_PROXY` and
  `HTTP_PROXY` itself, so a fetch went through whatever proxy the environment
  named (measured: a CONNECT reached a local proxy nobody had given Sluicer),
  and with a proxy the check against private addresses no longer pinned the
  connection. The HTTP rung now tells curl to use none, and the browser is
  launched with `--no-proxy-server`. SECURITY.md says what the check does and
  does not do through a proxy.
- The stealth rung no longer claims to come from Google. It inherited
  scrapling's `google_search`, so every page it fetched was sent `Referer:
  https://www.google.com/` (measured on a local server); it now sends none, as
  the browser rung already did, and like it tries once within thirty seconds
  instead of scrapling's three tries.

- A page declaring thousands of products costs what its size does. Three
  parts of `extract()` grew with the square of a listing: the summary asked,
  for each product, which one the page was about; the merge walked every
  record for each item it folded; and each place written counted all its
  element's siblings again. 4,000 products in JSON-LD, microdata and RDFa
  took 5.0 seconds and take 0.28; 16,000 in microdata alone, a 2 MB page,
  0.38. The answers are the same, byte for byte, on the benchmark pages.
- A GTIN holding a superscript or circled digit -- which `str.isdigit` takes
  and `int` refuses -- no longer makes `extract()` raise; it has no normalised
  value. A GTIN or an amount written in another script's decimal digits,
  fullwidth or Arabic-Indic, is normalised in ASCII digits, as a date already
  was, and so is a date's offset.
- A summary answer read from JSON-LD keeps an address's query:
  `?id=1&region=us&section=a` was `?id=1®ion=us§ion=a`, the old entity
  names HTML lets go without a semicolon read even before a letter. They are
  now read as an attribute's are, which is how a browser keeps them in an
  `href`; `&amp;`, `&#39;` and the rest are read as before. No answer on the
  benchmark pages changed.
- A JSON-LD node that holds a `@graph` and properties of its own -- a Product
  carrying the page's other nodes -- is read as a node too, after the nodes in
  its graph. Only its graph was read, and the Product was lost. On the
  benchmark pages, two product pages gain the Brand that wraps their
  Products; no summary answer changed.
- JSON-LD with JavaScript comments, `//` or `/* */`, is read: it was
  skipped, though extruct reads it, so `sluicer.compat.extruct` did worse than
  extruct. Comments are dropped outside strings only, and a trailing comma is
  now mended outside strings only too: `"Pad, ]"` was read as `"Pad]"`. On
  the benchmark pages, two of WCXB's development pages gain six records; no
  summary answer changed.
- `normalise.amount("12 50")` is None: every space and apostrophe was dropped,
  so it was 1250. Digits grouped by a space or an apostrophe must now be
  grouped in thousands, as those grouped by a point or a comma already were.
  No answer on the benchmark pages reads differently; of the 259,520
  distinct values SWDE labels, 163 phone numbers, `202 244 2044`, no longer
  read as amounts.
- An RFC 2822 date needs its year in four digits: `email.utils` read
  `Tue, 03 Jun 25 10:00:00 GMT` as 2025 by a rule of its own, and a
  three-digit year as the first millennium's. Such a date now has no
  normalised value.
- A twelve-hour clock is read with its half of the day: `Jun 16, 2025, 10:00
  PM` was normalised to 10:00, the morning, since `email.utils` took "PM" for
  a zone it did not know, and `Dec 1, 2024 11:30 PM EST` lost its zone too.
  An hour no such clock shows, `13:05 PM`, is not read. A trailing `UTC` with
  no offset before it is now the offset `+00:00`: it was read and dropped. On
  the benchmark pages, seven dates on four pages that end in `UTC` gain their
  offset.
- A breadcrumb item whose `position` is `NaN` or an infinity is placed where
  it was written: a NaN compares false with everything, and the crumbs came
  out in no order.
- A JSON-LD price JSON wrote with an exponent, `1.5e3`, is the summary's
  price and normalises to `1500`: the summary counted two numbers in it and
  refused it, and `amount()` could not read it.
- An inline SVG's or MathML's `<title>` is no longer the summary's title on a
  page with no head title, nor weighed as the page's title between a headline
  and a name: libxml2 has no namespaces, and an icon's "Close menu" was the
  page's title.
- A page lxml takes for a fragment -- no head, and neither `<html>` nor a
  doctype at its start, as a page a PHP warning is printed before -- is parsed as
  a whole document. `lxml.html.fromstring` renamed its `<body>` to a `<div>`,
  so every place on it went through an element the page never had,
  `/html/div[1]/title[1]` for `/html/body/title[1]`; an extractor could not
  find a path on such a page at all. On the benchmark pages, three evaldata
  pages' title place changes so; no value changes.
- A page's newlines are read as the HTML standard reads them, CR LF and a
  lone CR as LF, before lxml parses it. lxml 6 did so and lxml 5.3, the
  declared floor, did not, so a description or a review kept its CR LF on one
  and not the other: on the benchmark pages, 13 of the 55 pages whose answer
  depended on the lxml version no longer do. No answer on lxml 6 changed.

- `induce` costs in step with the page. Telling rows from sections compared
  every repeated group with every other one, measuring each group's members
  again for each comparison, so a 363 KB page of two thousand small lists took
  35 seconds, and a table of two thousand rows seven. Each group is now
  credited to the elements above it once: the first page takes 73 ms. The
  records and the ranking are the same on the 3,948 pages of the benchmark
  corpora. `induce` runs on pages nobody vouches for, through the MCP server's
  `extract_declared` and the HTTP API, and a call that times out still runs to
  its end on its worker: this was also a way to hold a worker for minutes.
- Gathering a parent's children into groups compared each child with every
  group of its kind begun before it, so two thousand children that share three
  parts and differ in a fourth made two million comparisons. Past sixteen
  groups of one kind, a child is now compared only with the groups whose first
  members share one of its rarest paths, which is where any match must be, and
  with at most 64 of those; on the benchmark corpora no child needed more than
  nine, and the groups are the same.
- Reading a CSS module's class (`Card_title__a1B2c` is `Card_title`) used a
  pattern that tried every `__` in a class and scanned to its end from each:
  a 90 KB class took seven seconds, on every row it sat on, in `induce` and
  in `compile`. The name and hash are now counted, the same answer in
  milliseconds.
- A part of an induced row carried the whole path down to it, copied at each
  level and hashed again to number it, so every wrapper around a row cost
  every part below it once more: forty thousand parts under two thousand
  wrappers took 1.4 seconds to name, and take 0.1.
- Listings nested inside listings cost the square of their depth: each
  member's worth was read off all the text and links below it, again for
  every member around it, and `induce` walked every group's rows in full
  before trying the next, even a group with nothing in it to name. A 93 KB
  page of them took seven seconds, and twenty with no text in it. Each
  element is now measured once from its children's measures, and a group is
  passed over when no part of it carries a fact, found the same way: both
  pages take 0.1 seconds, with the same records.
- Two slots of an induced row could share a name, and one value overwrote the
  other: two `<span class="tag">` are numbered `span.tag1` and `span.tag2`,
  and a card's own `<span class="tag1">` is `span.tag1` too. The class the
  page wrote keeps its name and the numbers of the slot that would clash are
  written after a `#`: `span.tag#1`, `span.tag#2`. What still clashes, a tag
  such as `a@href` that libxml2 keeps as written, takes `~2`. Names that do not
  clash are as they were; on the benchmark corpora two pages' first groups
  are renamed, where `div.col-12` named both the second of three `div.col-1`
  and a `div.col-12`, and no page's `induce` output changes.

- `audit` read `<link rel=canonical>` anywhere on the page, while `extract`
  reads the head only, as Google does: a canonical a comment put in the body
  made the audit warn `canonicals-disagree` about an address `links` never
  saw, and a page whose only canonical was in the body passed. The audit now
  reads the canonicals `links` reads, and two that resolve to one address, as
  `/pads` and `https://example.com/pads` on that site, are one canonical there
  too; the relative one is still `canonical-relative`.

## 0.7.0 - 2026-09-24

### Added
- `--visible`: `sluicer extract --visible`, `inspect --visible`,
  `extract(..., visible=True)` and `extract_declared`'s `visible` guess the
  heading, byline, publication date and update date a page shows a reader, by
  Sluicer's own rules and no model or clock (`sluicer.visible`,
  `read_visible`). Each guess names its element and rule and goes in a field
  of its own, `visible`, never in the summary; a date the page calls an
  update's is `modified`, never `published`, and a page showing more than
  three bylines or dates is taken for a listing. Made on WCXB's development
  pages only: there, what is declared and then the guesses find the author on
  0.701 of pages, right on 0.849 of answers, 58 invented (trafilatura 0.698,
  0.756, 86), and the date on 0.736, 0.779, 83 (trafilatura 0.833, 0.441,
  630), in 3.4 ms a page. The scoreboards do not measure it yet.
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
