# Sluicer design

Date: 2026-09-22. Author: Nichita Briculschi (with Claude).
Status: architecture approved, detail pending approval.

## 1. The problem

Getting from a web page to structured data costs you something today: either an
LLM per call (Firecrawl `extract`, ScrapeGraph), or hand-written selectors that
break at the next restyle. Both have a bill. The first is paid in tokens, the
second in human maintenance.

## 2. Evidence gathered 2026-09-22

Collection method: 14 GitHub search queries, **823 unique repositories**, filtered
down to **240 alive** (pushed < 12 months, not archived, >= 1,000 stars).

| layer | share of the 240 |
| --- | --- |
| browser / stealth / anti-bot | 32% |
| LLM / agents | 31% |
| crawl frameworks | 21% |
| **parsing / extraction** | **10%** |
| markdown / documents | 4% |
| no-code / visual | 2% |

Commits in the last 12 months inside the deterministic extraction layer:
`autoscraper` (7,990 stars) **1**; `extruct` (972) **0**; `trafilatura` (6,846)
57, the only healthy one, and it only handles article body text.

Existing benchmarks, free and reusable: **WCXB** (2,008 hand-reviewed pages, 7
page types, 1,613 domains, CC-BY-4.0, ships results for 14 systems),
**WebMainBench** (7,809 annotated pages, 5,434 domains, 46 languages,
Apache-2.0), **ChatNoir** (8 datasets unified). WCXB exists precisely because the
earlier benchmarks only measured news articles.

Precedent already taken: **`fastcrw/crw`** (Rust, AGPL, 1,061 stars, born
2026-03) is the "free Firecrawl" with a compatible API. That is not our ground.

## 3. Constraints, not preferences

1. **No LLM anywhere in the path.** Not even as a fallback.
2. **No paid API.** If a feature needs somebody's key to work, it does not ship.
3. **Permissive licence (MIT)** and **no vendored AGPL code**: Firecrawl and crw
   can be studied, not copied.
4. **Deterministic**: same page, same result, always. This is also what makes an
   honest benchmark possible.
5. **Maintainable by few hands**: no anti-bot arms race.
6. **English only** across code, comments, docs, commits and issues.

## 4. Architecture

### 4.1 What we compose (and do not rewrite)

| piece | delegated to | licence |
| --- | --- | --- |
| HTTP fetch with TLS impersonation, browser, stealth, spiders | `scrapling` | BSD-3 |
| article body and boilerplate removal | `trafilatura` | Apache-2.0 |
| HTML/XPath parsing | `lxml` | BSD-3 |

### 4.2 What we write (the product)

1. **`ladder`** - automatic cost ladder. Tries the cheapest rung (plain HTTP) and
   climbs to browser or stealth **only on a measurement**, never on a guess. The
   measurement is explicit and checkable: the response is a refusal in disguise
   (challenge page, 403 carrying a challenge body, redirect to login), or the
   body is skeletal against the weight of the page (useful text below threshold
   while the DOM declares empty containers), or declared data is missing **and**
   extracted text is below threshold. Every climb is recorded with its reason,
   and the reason travels in the result.
2. **`declared`** - reads what the page already states: JSON-LD, microdata, RDFa,
   OpenGraph. Picks up the inheritance of `extruct` (0 commits/year).
3. **`induce`** - structure induction: find repeating subtrees, align fields
   across records, return rows. Picks up the idea behind `autoscraper` (1
   commit/year) without needing hand-fed examples.
4. **`trust`** - confidence score **without an LLM**: two pages from the same
   template must yield the same fields, and divergence is the signal. With only
   one page available there is no comparison, and `trust` returns an explicit
   `unverified` rather than an invented number.
5. **`heal`** - schema diff between runs: when a site changes, it names **what**
   broke instead of returning a quietly empty list.
6. **`bench`** - the scoreboard: runs against the free datasets plus a
   multilingual e-commerce split, measures us **and the competition**, and
   publishes the losses too.

### 4.3 Flow

    URL/HTML -> ladder -> HTML + context
                            |
                    declared? --yes--> records
                            |no
                     induce? --yes--> records
                            |no
                     trafilatura --> text
                            |
                     trust (comparison across same-template pages)
                            |
                     heal (diff against previous run, when one exists)

## 5. How other people install it

One package, four front doors:

- **CLI**: `uv tool install sluicer` then `sluicer extract <url>`.
- **Python library**: `from sluicer import extract`.
- **MCP server** (stdio): for Claude Code, Codex, and anything else that speaks
  the protocol.
- **Claude Code plugin**: `.claude-plugin/marketplace.json` in the repo, the way
  linkedin-agent-skill does it, so installing takes two commands.

## 6. Testing

TDD, and every test must be able to fail for the right reason. Specifically:

- every layer has sample pages saved on disk, so unit tests never touch the
  network;
- for `trust`: a test that a **wrong but internally consistent** extraction is
  still flagged, and a test that a legitimately different page is **not**;
- for `ladder`: a test that the climb to a browser happens **only** when the
  measurement demands it, counted in requests;
- the scoreboard runs in CI and its output is a versioned file, not a log line.

## 7. Out of scope

Web search, distributed crawling across machines, captcha solving, any
model-based extraction, graphical interface.

## 8. Declared risks

- **Structure induction is the hard part**: it is old research (MDR, RoadRunner)
  that never shipped as a modern library. If it fails, `declared` + `trust` +
  the scoreboard still stand on their own.
- **The scoreboard can prove us wrong.** That is the point. We publish it anyway.
