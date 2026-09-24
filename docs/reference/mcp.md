# MCP tools

The 10 tools the server lists to an agent, each with its
description and parameters exactly as the agent receives them. Generated
from the running server by `scripts/reference.py`; how to add the server to
a client is in [In your agent](../agents.md).

## `extract_declared`

**Extract a page's declared data**

Read the structured data a page declares, with where each value came from.

- `html_or_url`: an http(s) URL to fetch, or the HTML itself.
- `induce`: also read repeated rows (a listing, a feed) from a page that declares nothing about them; those fields say source "induced".
- `at`: a date (2024, 2024-06, 2024-06-01): read the URL as the Wayback Machine captured it nearest to then; "fetch" says which capture.
- `respect_tdm`: answer tdm_reserved instead of the page when the site reserves its text and data mining rights (TDMRep: its tdmrep.json, headers or meta tags).
- `records`: also return every record, not only the summary and what was normalised; false keeps the answer small. Records that would make the answer larger than 75,000 bytes are left out and counted in records_left_out.
- `visible`: also guess the title, author, publication and update dates the page shows a reader, in "visible", each {"value", "where", "rule"}; guesses, never part of the summary, which holds only what the page declares.

Returns {"ok", "url", "summary", "records", "sources"}, and "fetch"
for a URL. records are typed fields, each {"value", "source",
"where"}: source is the vocabulary that declared it (jsonld,
microdata, opengraph, html, ...), where the XPath of the element that
did -- for JSON-LD the &lt;script&gt; block's, with a JSON pointer after
"#" -- or null for a meta tag, whose key is its place. A nested value
such as a price inside "offers" arrives whole. summary answers title,
author, date, price and the rest, one value each, naming its source,
key and where. conflicts lists each question the page answers two
ways that mean different things -- a price of 41.90 in JSON-LD and
39.90 in OpenGraph -- the summary's answer first: say so rather than
trusting either. On failure ok is false and "error" says why; there
is never a record.

| parameter | type | default |
|---|---|---|
| `html_or_url` | string | required |
| `induce` | boolean | `False` |
| `at` | string or null | `None` |
| `respect_tdm` | boolean | `False` |
| `records` | boolean | `True` |
| `visible` | boolean | `False` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `page_markdown`

**Read a page as markdown**

Return a page's main content as markdown, without navigation or footer.

- `html_or_url`: an http(s) URL to fetch, or the HTML itself.
- `front_matter`: open the markdown with a YAML block of what the page declares about itself (title, author, dates, url...) and each answer's source.
- `at`: a date: read the URL as the Wayback Machine captured it then.
- `respect_tdm`: answer tdm_reserved when the site reserves its text and data mining rights (TDMRep).
- `offset`: where in the markdown this answer starts, 0 for the beginning; the answer before gives the next as next_offset.
- `max_chars`: how many characters this answer carries, 1 to 60,000.

Returns {"ok", "markdown", "url", "length", "next_offset"}, and
"fetch" for a URL: markdown is one slice, length the whole markdown's,
next_offset where the next slice starts or null at the end. The
markdown is always the page's own content: a failure is ok false with
"error", never text that could be mistaken for the page.

| parameter | type | default |
|---|---|---|
| `html_or_url` | string | required |
| `front_matter` | boolean | `False` |
| `at` | string or null | `None` |
| `respect_tdm` | boolean | `False` |
| `offset` | integer | `0` |
| `max_chars` | integer | `30000` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `fetch_page`

**Fetch a page**

Fetch a page's HTML, and say what it cost: plain HTTP or a browser.

- `url`: an http(s) URL. Literal HTML is refused, since nothing would be fetched.
- `offset`: where in the HTML this answer starts, 0 for the beginning; the answer before gives the next as next_offset.
- `max_chars`: how many characters this answer carries, 1 to 60,000.

Returns {"ok", "html", "url", "fetch", "truncated", "length",
"next_offset"}: html is one slice of the page, length the whole
page's, and next_offset where the next slice starts, or null when
this one reaches the end. Prefer extract_declared or page_markdown,
which return what is in the page rather than all of it.

| parameter | type | default |
|---|---|---|
| `url` | string | required |
| `offset` | integer | `0` |
| `max_chars` | integer | `30000` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `compile_extractor`

**Learn an extractor**

Learn an extractor from pages of one template, to replay later for free.

- `pages`: http(s) URLs, or the HTML itself, of pages built from one template -- two or three pages of one listing, or of one kind of product page.
- `listing`: learn the rows the pages repeat; by default only where they declare nothing about a thing.
- `want`: example values one row of the listing holds, by the name each column is to have, as {"price": "41.90", "title": "Brake pad set"}: they choose the listing and the columns, and only those columns are kept. A value that no row holds is an error that names it.

Returns {"ok", "extractor"}: keep that object and hand it to
run_extractor. It holds what the pages declared, the listing's place,
its fields, and what every field looked like.

| parameter | type | default |
|---|---|---|
| `pages` | array | required |
| `listing` | boolean or null | `None` |
| `want` | object or null | `None` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `run_extractor`

**Run an extractor**

Replay an extractor on one page, and check the page still keeps to it.

- `extractor`: the object compile_extractor returned.
- `html_or_url`: an http(s) URL to fetch, or the HTML itself.

Returns {"ok", "rows", "fields", "summary", "failed"}; "fields" holds
the page's own values an extractor learnt from examples. ok is false
when the page drifted -- the listing moved, rows or a field vanished, a price no
longer looks like a price -- and "failed" says which expectation broke.
Never read rows from an answer whose ok is false as if nothing happened.

| parameter | type | default |
|---|---|---|
| `extractor` | object | required |
| `html_or_url` | string | required |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `heal_extractor`

**Heal an extractor**

Learn pages again after a redesign, and say what moved where.

- `extractor`: the object compile_extractor returned.
- `pages`: http(s) URLs, or the HTML itself, of the redesigned pages.

Returns {"ok", "extractor", "changes", "lost"}. A field that moved
keeps its old name, so rows read with the healed extractor keep their
columns, and its change carries the evidence: how many of the values it
was learnt with were found in the new place. "lost" is true when a
change is data the page no longer has -- vanished, summary-lost,
type-lost, listing-lost -- and then ok is false: the old extractor,
which keeps failing, is the safer one to keep until a person looks.

| parameter | type | default |
|---|---|---|
| `extractor` | object | required |
| `pages` | array | required |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `audit_page`

**Audit a page's markup**

Check a page's structured data against what Google documents for it.

- `html_or_url`: an http(s) URL to fetch, or the HTML itself.
- `site`: for a URL, also read the site's robots.txt, llms.txt and llms-full.txt.

Returns {"ok", "url", "records", "page", "not_checked", "errors",
"warnings", "notes"}, and for a URL read with site "crawlers",
"robots_txt", "other_agents", "llms_txt", "llms_full_txt" and "fetch".
Every JSON-LD, microdata and RDFa record lists the rich-result features
its type is documented for, each with requirements_met and the
required and recommended properties it lacks, and findings that each
name a severity, the record's source, the property path and the URL of
the rule. crawlers says, per AI agent from its vendor's own page,
whether robots.txt admits the page. ok is true whenever the audit ran:
a page with errors is an answer; "not_checked" says what was not.

| parameter | type | default |
|---|---|---|
| `html_or_url` | string | required |
| `site` | boolean | `True` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `read_feed`

**Read a feed**

Read a feed's items: RSS, Atom or JSON Feed.

- `url_or_text`: an http(s) URL of a feed -- or of a page that declares one, which is followed to it -- or the feed itself.
- `limit`: the most items answered, 1 to 500; items_total says how many the feed holds.

Returns {"ok", "url", "format", "title", "link", "description",
"items", "items_total"}, each item {"title", "link", "id",
"published", "updated", "summary", "content", "authors",
"categories", "enclosures", "normalised"}, dates in normalised as ISO
8601. What is not a feed, and declares none, is bad_input.

| parameter | type | default |
|---|---|---|
| `url_or_text` | string | required |
| `limit` | integer | `50` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `map_site`

**Map a site**

List a site's addresses, from its sitemaps or its start page's links.

- `url`: an http(s) address on the site; its links stand in when the site has no sitemap.
- `limit`: the most addresses returned, 1 to 1,000.

Returns {"ok", "url", "source", "urls", "sitemaps", "truncated"}.
source is "sitemaps" or "links"; each of urls is {"url", "lastmod",
"sitemap"}, only addresses on the site, in the order the sitemaps list
them; sitemaps says what became of each one tried. At most ten
sitemaps are read, politely, within a minute; truncated is true when a
bound cut the map short. Hand the addresses worth reading to
extract_declared, or crawl_site to follow links from one.

| parameter | type | default |
|---|---|---|
| `url` | string | required |
| `limit` | integer | `100` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.

## `crawl_site`

**Crawl a site**

Crawl a site from url, following its links, and summarise every page.

- `url`: an http(s) address where the crawl starts; only links on its site are followed.
- `max_pages`: the most pages taken, 1 to 25.
- `max_depth`: the most links from url, 0 to 3; 0 reads url alone.
- `respect_tdm`: give a page whose site reserves its text and data mining rights (TDMRep) as a tdm_reserved error, never its summary.
- `include`: text an address must contain for its link to be followed (any one of them); plain text, not a pattern.
- `exclude`: text that stops a link being followed when its address contains it.

Returns {"ok", "url", "pages", "stopped"}. Pages come breadth first,
each {"ok", "url", "depth", "found_on", "landed", "fetch", "canonical",
"summary", "sources", "types", "links"} -- the summary and the types
declared, not the records; call extract_declared on a page for those
-- or, when it has nothing, {"ok": false, "error"} with the page's
reason. stopped is "done", "max_pages" (links were left unfollowed)
or "time_budget" (a minute passed). One request at a time, a second
apart or the site's Crawl-delay, robots.txt obeyed. ok is false only
when no page could be read, and error then says why.

| parameter | type | default |
|---|---|---|
| `url` | string | required |
| `max_pages` | integer | `10` |
| `max_depth` | integer | `2` |
| `include` | array or null | `None` |
| `exclude` | array or null | `None` |
| `respect_tdm` | boolean | `False` |

Its annotations say it only reads, changes nothing, gives the same answer when called again and may reach the web.
