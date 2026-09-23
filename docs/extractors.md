# Extractors that fail loudly

The most common way a scraper fails is not a crash. The site changes its markup,
and the scraper keeps running and returns nulls, or the wrong column, for weeks
before anyone notices. An extractor is built the other way round: it is learnt
once from a few pages, kept in a small file, replayed for nothing, and every
replay checks the page against what was learnt. A page that drifted is a failed
run, never a quiet one. When it fails, `heal` says what moved and where.

No model is involved at any step. The same pages always give the same extractor,
and the same page always gives the same verdict.

## Learn, replay, heal

```bash
# Learn from two or three pages built from one template.
sluicer compile https://shop.example/c/brakes?page=1 https://shop.example/c/brakes?page=2 -o brakes.json

# Replay it on any page of that template: rows as JSON, exit 3 if the page drifted.
sluicer run brakes.json https://shop.example/c/brakes?page=7

# After a redesign: see what moved, and write the healed extractor.
sluicer heal brakes.json https://shop.example/c/brakes?page=1 -o brakes.json
```

From Python:

```python
from sluicer.extractor import compile_extractor, run_extractor, heal

extractor = compile_extractor([(html_1, url_1), (html_2, url_2)])
open("brakes.json", "w").write(extractor.to_json())

run = run_extractor(extractor, html, url)
if not run.ok:
    for check in run.checks:
        if not check.ok:
            print(check.name, check.expected, "->", check.got)
rows = run.rows  # a list of {field name: value}

healed, changes = heal(extractor, [(new_html, new_url)])
```

An agent gets the same three steps as MCP tools: `compile_extractor`,
`run_extractor` and `heal_extractor`.

## What an extractor learns

- **What the pages declare.** Every summary question all the pages answered --
  title, price, sku, published date -- and every declared record type they all
  carried. For a structured answer (price, currency, dates, sku, availability)
  learnt from two pages or more, also the shape of the answer: `41.90` is `NP`,
  `£51.77` is `NPS`.
- **The listing the pages repeat**, when they declare nothing about a thing, or
  always with `--listing`: where it sits (`html>body>div.page>ol.row`), what one
  row looks like (`li.product`), how many rows each page had, and for every
  field its share of empty rows, the one shape its values shared if they did,
  and a few sample values.

The file is plain JSON, meant to be read and, if you need to, edited.

## What a run checks

| check | fails when |
|---|---|
| `listing` | the listing is no longer where it was |
| `rows` | fewer than half the fewest rows it was learnt with, and never zero |
| `field` | a field every learnt row had is missing from more than 20% of rows |
| `shape` | fewer than half of a field's values keep the one shape it had, or a structured summary answer changed shape |
| `summary` | a summary question every learnt page answered goes unanswered |
| `type` | a declared record type every learnt page carried is gone |

`sluicer run` prints every page's rows and failed checks as JSON and exits 3 when
any page failed any check. A run that broke its contract never exits 0.

## What healing does

`heal` learns the new pages from scratch, then matches each old field to its new
place: the new field that holds most of the sample values the old one held, then
one with the same shape. A field that moved keeps its old name, so rows read with
the healed extractor have the columns downstream code expects. What cannot be
matched is reported as `vanished`, and `sluicer heal` exits 3, because data the
page no longer has needs a person, not a guess.

On the shop fixture in the test suite, a redesign that renamed every class and
wrapped the listing in a new element moves all four fields to their new places:

```text
container: html>body>div.page>ol.row -> html>body>main.content>div.page>section.grid
member: li.product -> div.card
moved: a.title -> h2.name>a
moved: a.title@href -> h2.name>a@href
moved: span.price -> div.cost
moved: span.stock -> span.availability
```

## Limits

- The listing's place is an exact path. Any new wrapper or renamed class above
  the rows fails the `listing` check; that is the point, and `heal` finds the new
  place.
- One listing per extractor: the page's most promising repeated group.
- Healing matches by values seen before and by shape. A redesign that changes
  both the markup and every value at once -- a different page altogether -- is
  reported as fields vanished and new, not as moves.
- The thresholds (20% missing, 50% shape kept, half the fewest rows) are fixed
  for now.
- How often extractors survive real redesigns, and how often healing is right, is
  not measured yet. That benchmark, built from Wayback Machine snapshots of the
  same pages before and after real redesigns, is next on the
  [roadmap](roadmap.md).
