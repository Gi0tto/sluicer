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

## Stars are the wrong unit

Everything above counts repositories by stars, because that is what a GitHub
search returns. Stars turn out to measure something else than use.

For the 140 largest repositories in this field, we resolved the package name
each project *declares* in its own `pyproject.toml`, `setup.py` or
`package.json` — not the name guessed from the repository — and asked PyPI and
npm how often it was installed in the last month. Seventy of the 140 publish a
package we could measure; ten publish nothing; the rest are lists, monorepos
without a root manifest, or projects in languages with no central registry.

Across those seventy, the rank correlation between stars and installs is
**+0.47**. Stars account for about a fifth of the variation in how much a
project is actually used. Watchers predict it even less: **+0.36**.

The distance is not a rounding error. It is the whole ranking:

| project | stars | rank by stars | installs / month | rank by installs |
| --- | --- | --- | --- | --- |
| `trafilatura` | 6,847 | 48 | 11,451,983 | 7 |
| `curl_cffi` | 6,543 | 50 | 33,025,458 | 4 |
| `maxun` | 17,537 | 21 | 1,057 | 58 |
| `ego-lite` | 16,375 | 22 | 581 | 59 |

A star is someone saying *this looks interesting*. An install is someone's
build failing without you. The projects the field admires and the projects the
field depends on are largely two different sets, and only one of them is a
market.

## The lane, measured in installs

Asking the lane question again in installs rather than stars changes the
answer's size. These are last-month installs for every maintained reader of
declared metadata we could find on either registry:

| package | registry | installs / month | last release | reads |
| --- | --- | --- | --- | --- |
| `open-graph-scraper` | npm | 1,187,550 | current | OpenGraph |
| `metascraper` | npm | 594,788 | current | its own concepts |
| `extruct` | PyPI | 540,765 | **2024-11-08** | 6 formats |
| `mf2py` | PyPI | 531,588 | current | microformats |
| `pyrdfa3` | PyPI | 524,105 | current | RDFa |
| `newspaper3k` | PyPI | 473,466 | **2018-09-28** | article text |
| `microdata-node` | npm | 194,139 | current | microdata |
| `web-auto-extractor` | npm | 87,285 | current | 3 formats |
| `metadata-parser` | PyPI | 11,107 | current | mixed |

Three things fall out of that table.

**The demand is one to two million installs a month**, and it is split across
packages that each read one format. A page carries several at once, so reading
one format means the caller stacks two or three libraries and reconciles their
disagreements by hand. `open-graph-scraper` alone moves 1.19M installs a month
reading a single vocabulary.

**The one package that read six formats stopped shipping.** `extruct` still
takes 540,765 installs a month with its last release 683 days behind it. That
number is not a legacy tail — it is a demand with nothing current to answer it.

**Abandonment does not reduce use.** `newspaper3k` last shipped in September
2018 and is still installed 473,466 times a month. In this field, users do not
leave when a library stops; they stay and work around it, because the
alternative is writing the parser themselves.

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

**And it is not a small empty lane.** Counted in installs rather than stars, the
readers of declared metadata move over a million a month between them, one
vocabulary per package, with the only package that ever covered the whole set
683 days without a release. That is the measurement this project was built
against.

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
