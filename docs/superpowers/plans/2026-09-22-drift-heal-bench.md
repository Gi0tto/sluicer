# Plan: extractors that fail loudly, heal visibly, and prove it

Status: proposal, not approved. Nothing here is built. Written 2026-09-22 after
the audit branch `audit-fixes`, from the market measurement in
`~/ricerche/mercato-2026-09-22/`.

## The problem, as the people who have it say it

Measured across 4,253 Reddit and Hacker News posts (74% from 2026), the most
repeated pain in scraping is not fetching and not parsing. It is that a scraper
**breaks in silence** when a site changes its markup, and keeps returning nulls
for weeks ("every time a website updates its layout or class names, the scraper
dies"; "maintenance time exceeds automation value"). The second is its twin: an
automation that **reports success when it failed**. The objection to every
answer on offer is that nobody shows evidence: "100% self-healing web scrapers
… is just marketing language".

This is Sluicer's own roadmap -- induce, trust, heal, bench -- with a market
reason attached, and with one lesson Sluicer's history already paid for: a
failure dressed as a success is the defect to design against.

## What exists today (on `audit-fixes`)

- Declared data from eight vocabularies, merged with provenance, and a summary.
- Induction: repeated rows of a page that declares nothing, named by stable
  paths (books.toscrape 20/20, quotes 10/10, HN 30/30, lobste.rs 25/25).
- A fetch ladder that records what each page cost.
- Deterministic output, which is what makes every step below testable.

## What to build, in order

**1. An extractor is an artifact.** `sluicer compile URL [URL...] -o shop.sluice`
induces an extractor from one or more pages of a template and writes it as a
small, versioned, human-readable file: the group signature, the field paths,
the declared-data fields it relies on, and a fingerprint of the pages it was
learnt from. `sluicer run shop.sluice URL` replays it with no induction and no
per-page cost. Exit criterion: the same file gives byte-identical output on the
pages it was compiled from, on any machine.

**2. A contract, checked on every run.** The artifact carries what a good run
looks like: the field set, row count bounds, null rate per field, and the
two-pages-one-template rule from `trust` (pages of one template must yield the
same fields). A run that breaks the contract exits non-zero with a report of
which expectation failed, by how much, on which page. Exit criterion: a
contract-breaking run can never exit 0; tested with pages mutated the way real
redesigns mutate them (renamed classes, a wrapper added, a field moved).

**3. Heal is a diff, not a guess.** When a contract fails, `sluicer heal`
re-induces on the new page and prints what changed: fields whose path moved,
fields gone, fields new, and whether the rows still align. It writes a new
artifact version only when asked. Exit criterion: on a mutated page, the diff
names every moved field, and the healed extractor passes the old contract.

**4. The bench is the claim.** A public drift benchmark built from Wayback
Machine snapshots of the same pages before and after real redesigns (listings
and product pages from sites whose markup changed; page pairs chosen by a
published rule, not by hand). Per tool: percent of extractors that survive a
redesign untouched, percent that fail loudly, percent that fail silently, and
percent healed. The silent-failure column is the headline. Competitors run on
the same pairs: Scrapling's adaptive selectors at least. Losses published.
Exit criterion: the numbers regenerate from one command.

**5. Only then, the README.** The positioning follows the bench, and the only
claims made are the bench's numbers.

## Who else is here (verified 2026-09-22)

- Scrapling (83k stars): adaptive selectors that relocate an element after a
  change. The nearest neighbour, and the one the bench must run.
- Lightpanda Agent and PandaScript (lightpanda-io/browser, 35.5k stars, AGPL,
  0.4.0 on 2026-08-31): natural language compiled into a deterministic script
  that needs no model at run time -- the "compile once, run forever" half of
  this plan. AGPL: study, never copy. A bench candidate if it can run offline.
- Stagehand (25k) caches browser actions; browser-use/workflow-use (4.2k)
  records and replays; `ashaychangwani/imprint` (22) turns a recording into an
  MCP tool.
- A wave of small "self-healing scraper" repos born July to September 2026
  (PyScrappy 257, anansi 115, mender, scrape-heal, driftguard). None has won,
  and none publishes a measurement.
- The largest extraction benchmark has 28 stars. The ruler does not exist yet.

## Not in this plan

- An anti-bot race, as before.
- A model anywhere in the run path, as before.

## The decision this plan cannot make

The market asks for "AI writes the scraper once". Sluicer's first constraint
is no model anywhere, not even as a fallback. The two are compatible only if a
model is confined to an optional, bring-your-own-key `compile` step whose
output is the same plain artifact induction produces, and the run path stays
model-free. That is Nichita's call. Until it is made, everything above is
built model-free, and nothing in it depends on the answer.
