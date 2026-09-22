# The field, measured

Claims about being better than the alternatives are worth nothing without a
count. This is the count, taken on 2026-09-22, and it is reproducible: the
queries are at the bottom.

## Method

Twenty-six GitHub search queries across scraping, crawling, extraction,
structured data, markdown conversion, document parsing and SEO. **1,926 unique
repositories** came back. Filtered to the ones still alive, meaning pushed
within twelve months, not archived, and at least 1,000 stars, and then to the
ones actually in this domain rather than merely matching a keyword: markdown
editors, static site generators and note apps are not competitors even though
they answer to the word "markdown".

**295 live repositories** remain. Everything below counts those.

## What the field builds

| capability | repos | share |
| --- | --- | --- |
| extraction with an LLM | 65 | 22% |
| browser and headless | 55 | 18% |
| SEO tooling | 49 | 16% |
| markdown for LLMs | 41 | 13% |
| crawling at scale | 41 | 13% |
| stealth and anti-bot | 34 | 11% |
| documents, PDF and OCR | 29 | 9% |
| an MCP server | 27 | 9% |
| reading declared structured data | 19 | 6% |
| parsing and selectors | 10 | 3% |
| main-content text extraction | 8 | 2% |
| **self-healing when a site changes** | **1** | **0%** |
| **a published benchmark** | **1** | **0%** |

## The two lanes nobody is in

**Self-healing: one repository out of 295.** It is Scrapling, and its healing
works at the level of a single element: pass `adaptive=True` and it relocates a
selector after the page changes. Nothing in the field heals at the level of a
schema, which is the level at which a site redesign actually breaks a pipeline.

**A benchmark: one repository out of 295**, and it measures OCR research, not
web extraction. The extraction benchmarks that do exist are academic and small:
the largest, WCXB, has 2,008 hand-reviewed pages and eleven stars. So "the best
extractor" is currently an unfalsifiable claim across an entire field.

## The lane we chose, checked properly

Of the 295, nineteen mention reading declared structured data, and fifteen of
those do it without an LLM. Read those fifteen and the picture changes again:
most of them **write** metadata rather than read it. Yoast, next-seo, Laravel
SEO Tools, Rails meta-tags and the Jekyll SEO plugin all help a site publish
schema.org. Two more are domain-specific, and one is the schema.org
specification itself.

Generic readers of declared data, still maintained, above 1,000 stars:

| repo | stars | language |
| --- | --- | --- |
| `microlinkhq/metascraper` | 2,738 | JavaScript |
| `php-embed/Embed` | 2,140 | PHP |

In Python there is nobody. `extruct` held that ground and has not taken a commit
in twelve months.

## What this changes

**An MCP server is table stakes, not a differentiator.** Twenty-seven live
projects ship one, nine percent of the field and climbing. A tool that an agent
cannot install is a tool an agent will not use. It moves onto the roadmap.

**Competing on fetching is still a losing move.** Eighteen percent of the field
builds browsers and eleven percent fights anti-bot full time, including a browser
written in Zig and a patched Firefox. We delegate that and say so.

**The extraction and measurement lane is as empty as it looked**, on a sample
four times larger than the first survey. One self-healer, one benchmark, and no
Python reader of declared data left standing.

## Reproduce it

```bash
gh api -X GET "search/repositories?q=topic:web-scraping&sort=stars&per_page=100" \
  --jq '.items[] | {full_name,stargazers_count,pushed_at,archived,description,topics}'
```

Repeat for: `topic:scraper`, `topic:crawler`, `topic:web-crawler`,
`topic:scraping`, `topic:headless-browser`, `topic:data-extraction`,
`topic:html-to-markdown`, `topic:anti-bot`, `topic:browser-automation`,
`topic:structured-data`, `topic:schema-org`, `topic:seo`, `topic:seo-tools`,
`topic:technical-seo`, `topic:sitemap`, `topic:markdown`,
`topic:document-parsing`, `topic:pdf-extraction`, `topic:rss`, and the keyword
searches for web scraping frameworks, content extraction, markdown converters,
scraping APIs, stealth browsers and `llms.txt`.

Then keep what was pushed within twelve months, is not archived, and has at
least 1,000 stars.
