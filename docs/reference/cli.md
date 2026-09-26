# Command line

Every command's own `--help`, as `sluicer` prints it. Generated from the
code by `scripts/reference.py`. Commands and options complete in bash, zsh
and fish: see [Shell completion](../getting-started.md#shell-completion);
their defaults can come from a file: see [Configuration](../configuration.md).

```text
$ sluicer --help
Usage: sluicer [OPTIONS] COMMAND [ARGS]...

  Turn a web page into structured data with no model in the loop.

  SOURCE is a URL, a saved HTML file, or - for standard input.

Options:
  --version      Show the version and exit.
  --config FILE  Take defaults from this TOML file; else SLUICER_CONFIG, else the
                 nearest sluicer.toml or [tool.sluicer].
  --no-config    Read no configuration file.
  --help         Show this message and exit.

Read a page:
  fetch     Fetch a URL and print the page, as the ladder brought it back.
  extract   Read the structured data a URL, a file or stdin declares.
  select    Print what a CSS or XPath selector gives on a page, and where.
  inspect   Show, for a person, what a page declares and where each answer came from.
  markdown  Print the main content of a URL, a file or stdin as markdown.
  diff      Say what changed between two readings of a page, question by question.
  audit     Check what a page declares against what Google documents, and more.

Whole sites:
  map       List a site's addresses, from its sitemaps or its start page's links.
  crawl     Crawl a site from URL, politely, one JSON line per page.
  batch     Read every address in URLS_FILE, politely, one JSON line per page.
  feed      Read a feed's items: RSS, Atom or JSON Feed, from a URL, a file or stdin.
  warc      Read every page the WARC FILES hold, one JSON line per page.

Extractors:
  compile   Learn an extractor from pages of one template, and write it to a file.
  run       Replay an extractor on pages, and exit 3 if any page broke its contract.
  heal      Learn pages again and say what moved; write the result only with -o.

Servers:
  mcp       Run the MCP server over stdio (needs sluicer[mcp]), as sluicer-mcp does.
  serve     Serve the MCP server's tools over HTTP (needs sluicer[api]).
```

## `sluicer audit`

```text
Usage: sluicer audit [OPTIONS] SOURCE

  Check what a page declares against what Google documents, and more.

  For every record JSON-LD, microdata and RDFa declare: the rich-result features its
  type is documented for, the required and recommended properties it lacks, and the
  values in a form the documentation refuses. Then what the page lacks -- a title, a
  description, a canonical, OpenGraph -- and where two vocabularies contradict each
  other. For a URL, also which AI agents the site's robots.txt admits and whether its
  llms.txt keeps to llmstxt.org's format; a file or stdin reads no site.

  Exits 3 when anything is an error -- a required property missing, a value refused, an
  llms.txt with no name -- whatever else is true, since that is a page breaking a stated
  rule. Otherwise 1 when no record was declared, since there was nothing to audit, and
  0. 2, as everywhere, when the page could not be read.

Options:
  --json / --no-json          Print the audit as JSON.
  --no-site / --site          Do not read the site's robots.txt and llms.txt for a URL.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --stealth                   Allow the stealth rung, which does not announce itself.
  --no-robots / --robots      Fetch even where the site's robots.txt says no.
  --url URL                   The address a file or stdin came from, to resolve its
                              links.
  --respect [tdm]             Refuse a page whose rights are reserved: tdm reads
                              TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                 Keep fetched pages in DIR, and ask the site with their
                              ETag or Last-Modified whether a page changed before
                              fetching it again.
  --max-age SECONDS           With --cache, give a page kept for less than SECONDS back
                              without asking its site at all.  [x>=0]
  --at DATE                   Read a URL as the Wayback Machine captured it nearest to
                              DATE (2025, 2025-06, 2025-06-01), not from its site.
  --help                      Show this message and exit.
```

## `sluicer batch`

```text
Usage: sluicer batch [OPTIONS] URLS_FILE

  Read every address in URLS_FILE, politely, one JSON line per page.

  One address a line, blank lines and # comments skipped; - reads stdin, so `sluicer map
  URL --plain | sluicer batch -` reads a site's sitemap. No link is followed. Several
  sites are asked at once, each one request at a time, and the pages come out in the
  order the file lists them.

Options:
  -o, --out FILE              Write one JSON line per page here, not to stdout; the file
                              is the state --resume continues from.
  --format [jsonl|csv]        jsonl: a JSON line per page; csv: a row per page, its
                              summary flattened into a column a question
                              (docs/crawling.md says which).  [default: jsonl]
  --resume                    Continue what --out already holds, fetching none of it
                              again.
  --delay FLOAT RANGE         The least seconds between two requests to one site; its
                              robots.txt Crawl-delay wins when longer.  [default: 1.0;
                              x>=0]
  --retries INTEGER RANGE     Ask a page again this many times when it did not answer,
                              or answered 429 or a 5xx, each time twice as late; never
                              another 4xx.  [default: 2; 0<=x<=10]
  --jobs INTEGER RANGE        How many sites are asked at once, each still one request
                              at a time.  [default: 4; 1<=x<=32]
  --induce / --no-induce      Also read the rows a page repeats when it declares nothing
                              about them.
  --respect [tdm]             Give a page whose rights are reserved as an error, not its
                              data: tdm reads TDMRep's tdmrep.json, headers and meta
                              tags.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --help                      Show this message and exit.
```

## `sluicer compile`

```text
Usage: sluicer compile [OPTIONS] [SOURCES]...

  Learn an extractor from pages of one template, and write it to a file.

  With --want, the examples say which repeated group is the listing and what its columns
  are called: --want title="Brake pad set" --want price=41.90 learns the listing whose
  rows hold both, with those two columns. When no repeated group holds them -- a product
  page -- or with --no-listing, they are the page's own values, each learnt where it
  sits. A value that is nowhere is an error that names it.

  With --select, you name each field by selector instead, and --rows the listing's rows:
  nothing is learnt of where they are, and from the pages, if any are given, what each
  field looks like, as for any extractor. A selector that gives nothing on a page given
  is an error that names it.

Options:
  -o, --output TEXT           Where to write the extractor.  [required]
  --listing / --no-listing    Learn the rows the pages repeat (default: only if they
                              declare no thing).
  --want NAME=VALUE           A value one row holds, and the column's name: --want
                              price=41.90. Chooses the listing and keeps only the
                              columns named.
  --select NAME=SELECTOR      A field you name by CSS or XPath instead of an example:
                              --select price='span.price::text'. No page is needed.
  --rows SELECTOR             With --select, the rows of a listing, each field read
                              inside each: --rows li.product.
  --stealth                   Allow the stealth rung.
  --no-robots / --robots      Fetch even where robots.txt says no.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --help                      Show this message and exit.
```

## `sluicer crawl`

```text
Usage: sluicer crawl [OPTIONS] URL

  Crawl a site from URL, politely, one JSON line per page.

  Breadth first, on URL's site unless --any-site, every page through robots.txt and one
  request at a time with the site's delay between. Run twice, it takes the same pages in
  the same order. --template sitemap reads the pages the site's sitemaps list instead,
  --include and --exclude choosing among them; --template shopify reads a Shopify shop's
  products from its /products.json, --max-pages of them at 250 a page.

Options:
  --max-pages INTEGER RANGE     The most addresses taken, whatever becomes of them.
                                [default: 100; x>=1]
  --max-depth INTEGER RANGE     The most links from URL; 0 reads URL alone.  [default:
                                3; x>=0]
  --include REGEX               Follow only links whose address this is found in;
                                repeatable.
  --exclude REGEX               Do not follow links whose address this is found in;
                                repeatable.
  --any-site                    Follow links that leave URL's site too.
  --template [sitemap|shopify]  A ready crawl: sitemap reads the pages URL's sitemaps
                                list; shopify reads a Shopify shop's /products.json, a
                                line per product.
  -o, --out FILE                Write one JSON line per page here, not to stdout; the
                                file is the state --resume continues from.
  --format [jsonl|csv]          jsonl: a JSON line per page; csv: a row per page, its
                                summary flattened into a column a question
                                (docs/crawling.md says which).  [default: jsonl]
  --resume                      Continue what --out already holds, fetching none of it
                                again.
  --delay FLOAT RANGE           The least seconds between two requests to one site; its
                                robots.txt Crawl-delay wins when longer.  [default: 1.0;
                                x>=0]
  --retries INTEGER RANGE       Ask a page again this many times when it did not answer,
                                or answered 429 or a 5xx, each time twice as late; never
                                another 4xx.  [default: 2; 0<=x<=10]
  --jobs INTEGER RANGE          How many sites are asked at once, each still one request
                                at a time.  [default: 4; 1<=x<=32]
  --induce / --no-induce        Also read the rows a page repeats when it declares
                                nothing about them.
  --respect [tdm]               Give a page whose rights are reserved as an error, not
                                its data: tdm reads TDMRep's tdmrep.json, headers and
                                meta tags.
  --proxy URL                   Fetch through this proxy (http://host:port,
                                socks5h://host:port); the environment's HTTPS_PROXY is
                                never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'    Send this header to the site asked, and to no other it
                                redirects to; again for more. Never User-Agent: Sluicer
                                always says who it is.
  --cookie NAME=VALUE           Send this cookie to the site asked, as --header does;
                                again for more.
  --help                        Show this message and exit.
```

## `sluicer diff`

```text
Usage: sluicer diff [OPTIONS] BEFORE AFTER

  Say what changed between two readings of a page, question by question.

  BEFORE and AFTER are each a URL, a file or - for stdin; --at reads BEFORE as the
  Wayback Machine captured it, so `sluicer diff URL URL --at 2024-01` is what changed
  since then. Exit codes are diff's: 0 when nothing differs, 1 when something does, 2
  when either could not be read. A value written differently with the same meaning
  (41.90 and 41.9) is reported as rewritten; a price in another currency (£41.90 and
  $41.90) is changed.

Options:
  --json / --no-json          Print the differences as JSON.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --stealth                   Allow the stealth rung, which does not announce itself.
  --no-robots / --robots      Fetch even where the site's robots.txt says no.
  --url URL                   The address a file or stdin came from, to resolve its
                              links.
  --respect [tdm]             Refuse a page whose rights are reserved: tdm reads
                              TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                 Keep fetched pages in DIR, and ask the site with their
                              ETag or Last-Modified whether a page changed before
                              fetching it again.
  --max-age SECONDS           With --cache, give a page kept for less than SECONDS back
                              without asking its site at all.  [x>=0]
  --at DATE                   Read a URL as the Wayback Machine captured it nearest to
                              DATE (2025, 2025-06, 2025-06-01), not from its site.
  --help                      Show this message and exit.
```

## `sluicer extract`

```text
Usage: sluicer extract [OPTIONS] SOURCE

  Read the structured data a URL, a file or stdin declares.

Options:
  --induce / --no-induce          Also read the rows a page repeats when it declares
                                  nothing about them.
  --microformats / --no-microformats
                                  Also read microformats2 (needs sluicer[microformats]).
  --visible / --no-visible        Also guess the title, byline and dates the page shows,
                                  not in the summary.
  --proxy URL                     Fetch through this proxy (http://host:port,
                                  socks5h://host:port); the environment's HTTPS_PROXY is
                                  never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'      Send this header to the site asked, and to no other it
                                  redirects to; again for more. Never User-Agent:
                                  Sluicer always says who it is.
  --cookie NAME=VALUE             Send this cookie to the site asked, as --header does;
                                  again for more.
  --stealth                       Allow the stealth rung, which does not announce
                                  itself.
  --no-robots / --robots          Fetch even where the site's robots.txt says no.
  --url URL                       The address a file or stdin came from, to resolve its
                                  links.
  --respect [tdm]                 Refuse a page whose rights are reserved: tdm reads
                                  TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                     Keep fetched pages in DIR, and ask the site with their
                                  ETag or Last-Modified whether a page changed before
                                  fetching it again.
  --max-age SECONDS               With --cache, give a page kept for less than SECONDS
                                  back without asking its site at all.  [x>=0]
  --at DATE                       Read a URL as the Wayback Machine captured it nearest
                                  to DATE (2025, 2025-06, 2025-06-01), not from its
                                  site.
  --help                          Show this message and exit.
```

## `sluicer feed`

```text
Usage: sluicer feed [OPTIONS] SOURCE

  Read a feed's items: RSS, Atom or JSON Feed, from a URL, a file or stdin.

  A page that is not a feed but declares one, with <link rel=alternate>, is followed to
  it. Prints the feed as JSON: what it says about itself and every item, dates also
  normalised. Exits 1 for a feed with no item, 2 for what is not a feed.

Options:
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --stealth                   Allow the stealth rung, which does not announce itself.
  --no-robots / --robots      Fetch even where the site's robots.txt says no.
  --url URL                   The address a file or stdin came from, to resolve its
                              links.
  --respect [tdm]             Refuse a page whose rights are reserved: tdm reads
                              TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                 Keep fetched pages in DIR, and ask the site with their
                              ETag or Last-Modified whether a page changed before
                              fetching it again.
  --max-age SECONDS           With --cache, give a page kept for less than SECONDS back
                              without asking its site at all.  [x>=0]
  --at DATE                   Read a URL as the Wayback Machine captured it nearest to
                              DATE (2025, 2025-06, 2025-06-01), not from its site.
  --help                      Show this message and exit.
```

## `sluicer fetch`

```text
Usage: sluicer fetch [OPTIONS] URL

  Fetch a URL and print the page, as the ladder brought it back.

  The HTML goes to stdout, or to --output, and what it cost -- each climb, where the
  page landed, its status and rung -- to stderr; with --json, all of it is one object on
  stdout. The input compile, extract and the rest can then read from a file, the same
  bytes every time. Exits 0 with a page, whatever its status, and 2 when none could be
  fetched.

Options:
  -o, --output FILE           Write the page to this file rather than to stdout.
  --json / --no-json          Print one JSON object: the page, where it landed, its
                              status, rung, climbs and headers.
  --stealth                   Allow the stealth rung, which does not announce itself.
  --no-robots / --robots      Fetch even where the site's robots.txt says no.
  --cache DIR                 Keep fetched pages in DIR, and ask the site with their
                              ETag or Last-Modified whether a page changed before
                              fetching it again.
  --max-age SECONDS           With --cache, give a page kept for less than SECONDS back
                              without asking its site at all.  [x>=0]
  --at DATE                   Read the URL as the Wayback Machine captured it nearest to
                              DATE.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --help                      Show this message and exit.
```

## `sluicer heal`

```text
Usage: sluicer heal [OPTIONS] EXTRACTOR_FILE SOURCES...

  Learn pages again and say what moved; write the result only with -o.

  Exits 3 when a field, a summary answer, a type or the listing was lost for good:
  healing moved what it could, and what it could not needs a person. Nothing is written
  then without --force, so a lossy extractor never quietly replaces the one that would
  have kept failing.

Options:
  -o, --output TEXT           Where to write the healed extractor.
  --force                     Write the healed extractor even when healing lost
                              something; a lost listing is kept as it was.
  --stealth                   Allow the stealth rung.
  --no-robots / --robots      Fetch even where robots.txt says no.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --help                      Show this message and exit.
```

## `sluicer inspect`

```text
Usage: sluicer inspect [OPTIONS] SOURCE

  Show, for a person, what a page declares and where each answer came from.

  The same reading as ``extract``, laid out to be read rather than parsed: what the
  fetch cost, which vocabularies said something, every record with the source of each
  field, and every summary answer with its source and key. Exit codes are ``extract``'s.

Options:
  --induce / --no-induce          Also read the rows a page repeats when it declares
                                  nothing about them.
  --microformats / --no-microformats
                                  Also read microformats2 (needs sluicer[microformats]).
  --visible / --no-visible        Also guess the title, byline and dates the page shows,
                                  not in the summary.
  --proxy URL                     Fetch through this proxy (http://host:port,
                                  socks5h://host:port); the environment's HTTPS_PROXY is
                                  never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'      Send this header to the site asked, and to no other it
                                  redirects to; again for more. Never User-Agent:
                                  Sluicer always says who it is.
  --cookie NAME=VALUE             Send this cookie to the site asked, as --header does;
                                  again for more.
  --stealth                       Allow the stealth rung, which does not announce
                                  itself.
  --no-robots / --robots          Fetch even where the site's robots.txt says no.
  --url URL                       The address a file or stdin came from, to resolve its
                                  links.
  --respect [tdm]                 Refuse a page whose rights are reserved: tdm reads
                                  TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                     Keep fetched pages in DIR, and ask the site with their
                                  ETag or Last-Modified whether a page changed before
                                  fetching it again.
  --max-age SECONDS               With --cache, give a page kept for less than SECONDS
                                  back without asking its site at all.  [x>=0]
  --at DATE                       Read a URL as the Wayback Machine captured it nearest
                                  to DATE (2025, 2025-06, 2025-06-01), not from its
                                  site.
  --help                          Show this message and exit.
```

## `sluicer map`

```text
Usage: sluicer map [OPTIONS] URL

  List a site's addresses, from its sitemaps or its start page's links.

  Each sitemap is asked politely, through robots.txt and after the site's delay, and
  stderr says what became of each one.

Options:
  --limit INTEGER RANGE       The most addresses listed.  [default: 50000; x>=1]
  --plain / --no-plain        One address a line, for `sluicer batch -`.
  --format [json|csv]         json: the map as one object; csv: a row per address (url,
                              lastmod, sitemap).  [default: json]
  --time-budget SECONDS       Ask for no further sitemap once this many seconds have
                              passed; the map is then cut short. None by default.
                              [x>=0]
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --help                      Show this message and exit.
```

## `sluicer markdown`

```text
Usage: sluicer markdown [OPTIONS] SOURCE

  Print the main content of a URL, a file or stdin as markdown.

  The main content is trafilatura's extraction; --full prints the whole page instead,
  menus and footers included.

Options:
  --front-matter / --no-front-matter
                                  Open with a YAML block of what the page declares, and
                                  where the text and each answer came from.
  --full                          The whole page, menus and footers included, not its
                                  main content.
  --proxy URL                     Fetch through this proxy (http://host:port,
                                  socks5h://host:port); the environment's HTTPS_PROXY is
                                  never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'      Send this header to the site asked, and to no other it
                                  redirects to; again for more. Never User-Agent:
                                  Sluicer always says who it is.
  --cookie NAME=VALUE             Send this cookie to the site asked, as --header does;
                                  again for more.
  --stealth                       Allow the stealth rung, which does not announce
                                  itself.
  --no-robots / --robots          Fetch even where the site's robots.txt says no.
  --url URL                       The address a file or stdin came from, to resolve its
                                  links.
  --respect [tdm]                 Refuse a page whose rights are reserved: tdm reads
                                  TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                     Keep fetched pages in DIR, and ask the site with their
                                  ETag or Last-Modified whether a page changed before
                                  fetching it again.
  --max-age SECONDS               With --cache, give a page kept for less than SECONDS
                                  back without asking its site at all.  [x>=0]
  --at DATE                       Read a URL as the Wayback Machine captured it nearest
                                  to DATE (2025, 2025-06, 2025-06-01), not from its
                                  site.
  --help                          Show this message and exit.
```

## `sluicer mcp`

```text
Usage: sluicer mcp [OPTIONS]

  Run the MCP server over stdio (needs sluicer[mcp]), as sluicer-mcp does.

  For a client that starts a package's own command, as the MCP Registry's entry does:
  uvx --with "sluicer[mcp]" sluicer mcp. Each tool registered costs an agent context
  whether it is called or not; --tools, or the SLUICER_MCP_TOOLS variable, keeps only
  those named.

Options:
  --tools TEXT  Register only these tools, comma-separated: --tools
                extract_declared,page_markdown. All twelve by default.
  --help        Show this message and exit.
```

## `sluicer run`

```text
Usage: sluicer run [OPTIONS] EXTRACTOR_FILE SOURCES...

  Replay an extractor on pages, and exit 3 if any page broke its contract.

Options:
  --stealth                   Allow the stealth rung.
  --no-robots / --robots      Fetch even where robots.txt says no.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --help                      Show this message and exit.
```

## `sluicer select`

```text
Usage: sluicer select [OPTIONS] SOURCE SELECTOR

  Print what a CSS or XPath selector gives on a page, and where.

  One value a line, a tab, then the XPath of its element: 'h1', 'span.price::text',
  'a::attr(href)' or '//li/a/@href'. A selector that cannot be read exits 2 naming it,
  before any page is fetched; one that gives nothing exits 1.

Options:
  --json / --no-json          Print the values as a JSON list.
  --proxy URL                 Fetch through this proxy (http://host:port,
                              socks5h://host:port); the environment's HTTPS_PROXY is
                              never used. Same as SLUICER_PROXY.
  -H, --header 'NAME: VALUE'  Send this header to the site asked, and to no other it
                              redirects to; again for more. Never User-Agent: Sluicer
                              always says who it is.
  --cookie NAME=VALUE         Send this cookie to the site asked, as --header does;
                              again for more.
  --stealth                   Allow the stealth rung, which does not announce itself.
  --no-robots / --robots      Fetch even where the site's robots.txt says no.
  --url URL                   The address a file or stdin came from, to resolve its
                              links.
  --respect [tdm]             Refuse a page whose rights are reserved: tdm reads
                              TDMRep's tdmrep.json, headers and meta tags.
  --cache DIR                 Keep fetched pages in DIR, and ask the site with their
                              ETag or Last-Modified whether a page changed before
                              fetching it again.
  --max-age SECONDS           With --cache, give a page kept for less than SECONDS back
                              without asking its site at all.  [x>=0]
  --at DATE                   Read a URL as the Wayback Machine captured it nearest to
                              DATE (2025, 2025-06, 2025-06-01), not from its site.
  --help                      Show this message and exit.
```

## `sluicer serve`

```text
Usage: sluicer serve [OPTIONS]

  Serve the MCP server's tools over HTTP (needs sluicer[api]).

  POST /v1/tools/<name> with the tool's arguments as a JSON object answers what the tool
  answers; GET /v1/tools and /openapi.json describe them. /mcp is the MCP server itself
  over streamable HTTP, stateless, for a client that does not start servers over stdio,
  as n8n's and Dify's do not. The token, when SLUICER_API_TOKEN is set, goes in
  "Authorization: Bearer". Private addresses are refused unless SLUICER_ALLOW_PRIVATE=1,
  as for the MCP server. Exits 2 without listening when it cannot serve safely.

Options:
  --host TEXT              Where to listen. Anything but loopback needs
                           SLUICER_API_TOKEN.  [default: 127.0.0.1]
  --port INTEGER RANGE     [default: 8000; 0<=x<=65535]
  --timeout FLOAT RANGE    Seconds a request may take before it is answered 504.
                           [default: 120.0; x>0]
  --allow-unauthenticated  Listen beyond loopback with no token, behind something that
                           already decides who may call.
  --help                   Show this message and exit.
```

## `sluicer warc`

```text
Usage: sluicer warc [OPTIONS] FILES...

  Read every page the WARC FILES hold, one JSON line per page.

  Plain or gzipped, as web archives and Common Crawl write them; - reads stdin. Each
  line is extract's answer, read with the headers the page was served with, and a "warc"
  object naming the file and the record. Nothing is fetched. Records that are not pages
  are passed over, and those left out -- revisits, non-HTML bodies, error answers -- are
  counted at the end.

Options:
  --induce / --no-induce          Also read the rows a page repeats when it declares
                                  nothing about them.
  --microformats / --no-microformats
                                  Also read microformats2 (needs sluicer[microformats]).
  --help                          Show this message and exit.
```
