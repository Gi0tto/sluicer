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
`run_extractor` and `heal_extractor`. Their answers carry `ok`, false for a page
that drifted (with `failed`, the checks it broke) and for a heal that lost data
(with `lost`), exactly where the command line exits 3.

## What an extractor learns

- **What the pages declare.** Every summary question all the pages answered --
  title, price, sku, published date -- and every declared record type they all
  carried. For a structured answer (price, currency, dates, sku, availability)
  learnt from two pages or more, also the shape of the answer: `41.90` is `NP`,
  `£51.77` is `NPS`.
- **The listing the pages repeat**, unless a page declares its own subject -- a
  product page, an article; a thing declared on one of the listing's rows,
  as a quote in microdata is, is a row and not the page's subject -- or
  always with `--listing`: where it sits (`html>body>div.page>ol.row`), what one
  row looks like (`li.product`), how many rows each page had, and for every
  field its share of empty rows, the one shape its values shared if they did,
  and a few sample values.

The file is plain JSON, meant to be read and, if you need to, edited. Every
value is checked when it is read, not only its key: a share that is not a
number from 0 to 1 (`"missing": "nan"`), rows that are not two counts, a shape
of other letters than L, N, P and S, two fields of one name, a path that is not
one. An edit that would quietly turn a check off is refused with a message
naming it, and `sluicer run` and `heal` exit 2, as for a file that is not JSON.
Every file `compile` and `heal` write is one this reading accepts: a tag the
page spelt with a character a path parts its steps by, which lxml keeps as
written (`<a@b>`, `<x[1]>`), is written with it as `%` and its code,
`a%40b`, and a row's class that holds one, Tailwind's `@container`, is left
out of the row's kind.

## Pointing at what you want

Left to itself, `compile` takes the page's most promising repeated group and
every field its rows carry, named by where they sit (`span.price`). Given
examples, it takes the listing whose rows hold them, and only the columns they
name:

```bash
sluicer compile page1.html page2.html -o books.json \
    --want title="A Light in the Attic" --want price=51.77
```

- **The examples choose the listing.** The first repeated group, in each page's
  order, whose rows hold every example, each in a column of its own, is the
  listing, even in a sidebar or a menu, where `compile` alone never looks. An
  example no row holds is an error that names it. Examples held by two
  different groups, or by one column -- a product's table, its price and its
  SKU in two rows of the same `td` -- are no listing's: they are read as the
  page's own values, below.
- **They name the columns.** The rows `run` gives are `{"title": ..., "price":
  ...}`, and no other column is learnt or checked. A value matches when it says
  the same with its spaces collapsed, or is the same amount: `51.77` is the
  row's `£51.77`, and `8` is `8.00`. A value in two places in a row takes the first no other
  example needs, and the compile notes it.
- **The contract is the same.** The listing's place, its rows, each column's
  presence, shape and reading are checked as for any extractor. `heal` keeps
  the listing where it is while it keeps its contract there -- its items may
  all be new, and a sidebar listing some of the old ones is not where it went
  -- and otherwise finds it again by the values its columns held, in a group
  holding at least half of one column's: one related product that costs what a
  book used to is a coincidence. It keeps the names, and adds no column the
  examples did not name.

On books.toscrape.com, learnt from its first two pages with `title`, `price`
and `stock`, the third page replays as 20 rows of those three columns, and a
page of another site fails with the listing not found.

**A page with no listing is read the same way.** When no one repeated group
holds every example -- a product page that declares nothing -- or with
`--no-listing`, the examples are the page's own values, each learnt where it
sits. With `--listing`, no group holding them is an error: read as the page's
own values, they would be the first row's, on every page. A row's columns
are what a reader sees -- each part's text, an image's alt text, the address
a link or an image points to -- so a value only a `<meta>` in the row
declares, quotes.toscrape.com's `<meta itemprop="keywords" content=...>`, is
no column; point at the tags' links, or read the declaration with
`extract()`:

```bash
sluicer compile a-light-in-the-attic.html tipping-the-velvet.html -o book.json \
    --want title="A Light in the Attic" --want price=51.77
```

- The place is the deepest element whose whole text is the example, or an
  attribute holding it (`img.photo@src`), never a script's text. A title is
  said three times on most product pages; the page's own place comes before
  its navigation, asides, breadcrumb trail and listings, so it is the `<h1>`
  and not the trail's last step or a related product's link.
- `run` gives the values as `fields`, `{"title": ..., "price": ...}`, and checks
  each is still there, reads as it did (a price that reads as an amount on the
  learnt pages must still read as one: "Add to basket" fails the `reads`
  check), and keeps its shape when five pages or more taught it one.
- A field whose place the pages given contradict is read after its label: the
  place holds nothing on one of them, or a value that does not read as the
  example does, or another page puts it right after a label the example's
  own page gives another of its values -- a PEP's header has a
  Discussions-To row on PEP 257 and not on PEP 8, so PEP 8's type is PEP
  257's status, after `Status:`. A label the example's page does not say
  moves nothing: "Directors:" on one film and "Director:" on another is one
  field. The label is the text every page
  says once right before the value, `Type:`; a colon in an element of its
  own, `Type<span class="colon">:</span>`, is the label's. Where the pages
  label the place differently and no such label is found, `compile` refuses
  the example with a message: read by its place, the field would be another
  field on a page it was learnt from. `heal` does not keep or move a field to
  such a place either: it reads it after a label, or leaves the move to a
  person.
- A field read by its place also learns its label, when every page given puts
  the same one right before it, once: text that ends with a colon, or is in a
  `<th>`, `<dt>` or `<label>`. A page that still says the label, once or
  more, with or without its colon, in any case, and not right before the
  place has moved the row -- the weight where the SKU was -- and the run
  fails rather than read the weight as the SKU. A page that does not say the
  label at all is read at the place, as learnt: a label renamed is not a row
  moved. Two pages at least teach a label; one cannot tell its template's
  words from its own.
- `heal` keeps a field where its place still holds a value that reads as it
  did and its label still stands before it, reads it after its label when the
  label moved, moves it to where the new pages show one of its old values,
  and reports it vanished when none is so. It moves a field only among the
  page's own places, never into its navigation, asides or listings: the old
  price in a related products strip is another product's. When two own places
  hold an old value and read different values on the pages given, the move is
  `ambiguous`, left for a person.

On books.toscrape.com, whose product pages declare nothing, two product pages
with `title`, `price` and a `upc` from the product table replay on a third
with all three read, the title from its `<h1>`.

## Writing the fields yourself

When you already know where each field is, name it by selector instead of
by example, and nothing is learnt of where it is:

```bash
# Try a selector first: each value, a tab, and the XPath of its element.
sluicer select https://shop.example/c/brakes 'li.product span.price::text'

sluicer compile page1.html page2.html -o brakes.json --rows li.product \
    --select title='h3 a::attr(title)' --select price='span.price::text' \
    --select link='h3 a::attr(href)'
```

- **A selector is CSS or XPath.** CSS takes Scrapy's `::text`, an element's
  own text nodes, and `::attr(name)`, an attribute, read as parsel reads them:
  after a space, `div ::text` is every text node inside the element and
  `div ::attr(class)` the attribute of the element and of everything inside
  it. Without either the value is the element's whole text. A selector beginning with `/`, `./`, `(` or
  `@` is XPath, anything else CSS, and `xpath:` or `css:` before it says
  which. Values are read as a learnt field's are: spaces collapsed, `href`
  and `src` resolved against the page, a value of spaces alone no value.
- **`--rows` makes a listing.** Each field is then read inside each row,
  and an XPath there begins with `.`, as `.//a`: `//a` would read the whole
  page in every row, and is refused. Without `--rows` the fields are the
  page's own.
- **Pages are optional.** Given pages, `compile` learns what they show of
  each field -- the share of rows that carry it, its shape, whether it reads
  as an amount or a date, whether it was ever found twice -- and what the
  pages declare, as for any extractor; a selector that gives nothing on a
  page given is an error that names both. Given none, every check is at its
  strictest: each field required in every row, and held to one value.
- **The checks are the same.** A field that finds nothing is `field` failed;
  a listing's columns are held to `field`, `shape`, `reads` and `values` by
  the learnt extractor's own code, and the rows to `rows`. A selector that
  gives no rows fails `listing`. A field found twice where the pages showed
  it once fails `field` too: when a sale puts the old price beside the new,
  the first is the wrong one. A field the pages showed twice reads the
  first, and `compile` says so. A column fewer than half the rows carried
  -- a sale badge -- fails `field` on a page none of whose rows carries it,
  once that is under a 1% chance: from 13 rows for a badge three rows in
  ten carry.
- **`heal` does not rewrite them.** A selector is what a person said, and
  `heal` cannot say it for you: one the new pages still bear out is kept and
  its profile learnt again; one they break is reported `broken`, a loss, and
  kept as written, so `heal` exits 3 and the extractor keeps failing until
  you write the new one. `sluicer select` on the new page, or `compile
  --want` with one of the old values, finds where the value went.

The file is format 3, and every key but a field's `name` and `selector`
may be left out when you write one by hand; a key left out takes its
strictest value, so leaving one out never turns a check off:

```json
{
  "format": 3,
  "select": {
    "rows": "li.product",
    "fields": [
      {"name": "title", "selector": "h3 a::attr(title)"},
      {"name": "price", "selector": "xpath:.//p[@class='price_color']"}
    ]
  }
}
```

From Python, `compile_extractor(pages, select={...}, rows="li.product")`
writes one, and `sluicer.parse(html, url)` gives a page to try selectors on:
`page.css("span.price::text").getall()`, and each value's `.where`. An agent
has `select_values` and `compile_extractor`'s `select` and `rows`.

On the shop fixture in the test suite, an extractor written with `--rows
li.product` and three selectors fails the redesign with `listing` -- no
`li.product` left -- where a hand-written scraper returns no rows and exits
0, and the page whose price slot holds a button fails `reads`, `shape` and
`values`, as the learnt extractor does.

## What a run checks

| check | fails when |
|---|---|
| `listing` | the listing is no longer where it was, or two places now match where one did -- a sponsored strip of the same kind inserted before it -- or, where the path counts places, `section.box[2]`, the second box no longer begins with the heading it began with on every learnt page while another box does, or, where the heading is not learnt or is on no box, there are more or fewer boxes than on every learnt page: a box inserted before the second makes another box the second |
| `rows` | there are no rows, or on a listing of five members or more, more of them are empty shells than the learnt pages had, plus 20% -- skeletons waiting for a script |
| `field` | a field every learnt row had is missing from more than 20% of rows, or a field most learnt rows had is missing from every row; a page field is not found, or its label now stands before something else |
| `shape` | fewer than half of a field's values keep the characters it was learnt with -- a price slot that now says "Add to basket" -- or a structured summary answer changed shape; `42` still fits a price learnt as `41.90` |
| `reads` | a field every learnt value of which read as an amount or a date (see `sluicer.normalise`) reads so in fewer than half its values: a price column that now holds dates keeps its shape, and not its reading |
| `values` | on a page of five rows or more, a field that held different values in every row now says the same thing in all of them: a page of placeholders, "Loading" |
| `summary` | a summary question every learnt page answered goes unanswered |
| `type` | a declared record type every learnt page carried is gone |
| `extractor` | the extractor checks nothing at all, so a pass would mean nothing |

For a field written as a selector, `field` also fails when the selector
finds nothing, or finds two values where the pages it was written from
showed one, and `listing` when the rows' selector finds none.

A row that gains a class -- `on-sale` -- is still a row, a short page of the same
template -- the last of a pagination -- passes, and the second or third tag of a
card is a count, not a column, so pages with fewer tags pass too.

`sluicer run` prints every page's rows and failed checks as JSON and exits 3 when
any page failed any check. A run that broke its contract never exits 0.

## What healing does

`heal` learns the new pages from scratch, then matches each old field to its new
place:

- The new field that holds most of the sample values the old one held. Of two
  that hold as many, the one more rows carry. Two columns that swapped are two
  moves, not two fields kept in place.
- Else its own place, when that is still there and holds values of the shape the
  field was learnt with: a listing's items change between two visits.
- A numbered slot -- the third tag, the second author -- whose own place is still
  there never moves to another slot of its group, because one tag turning up in
  another slot moved nothing.
- Links are compared by path and parameters. A link that gained a tracking
  parameter, `?ref_=list_1`, is the same link; `?id=2` is another item than
  `?id=1`.

A field written as a selector is never moved: see [Writing the fields
yourself](#writing-the-fields-yourself).

A field found in none of these ways is reported as `vanished`, even if a new
field has the same shape, because a guess would put the wrong column under the
old name. A field that moved keeps its old name, so rows read with the healed
extractor have the columns downstream code expects.

Every field kept or moved carries its evidence: how many of the values it was
learnt with were found in the new place, of how many, and how many the next
best place held. It is reported, never used to decide. A move that rests on
five values of five, with nothing else close, needs no second look; a move that
rests on two of five, with a runner-up at one, is a reason for a person to look
before the healed extractor is trusted. `heal` never heals itself above some
confidence, because a wrong move is exactly the silent failure an extractor
exists to prevent.

When anything was lost -- a field, a summary answer, a declared type, the listing
itself -- `sluicer heal` exits 3 and does not write the healed extractor unless
given `--force`: the old one keeps failing, which is the honest state until a
person looks. A listing that was lost stays in the healed extractor as it was,
so even a forced one fails every page without it, rather than pass them all
with no rows.

On the shop fixture in the test suite, a redesign that renamed every class and
wrapped the listing in a new element moves all four fields to their new places:

```text
container: html>body>div.page>ol.row -> html>body>main.content>div.page>section.grid
member: li.product -> div.card
moved: a.title -> h2.name>a (5 of 5 learnt values found there; the next best place had 0)
moved: a.title@href -> h2.name>a@href (5 of 5 learnt values found there; the next best place had 0)
moved: span.price -> div.cost (5 of 5 learnt values found there; the next best place had 0)
moved: span.stock -> span.availability (2 of 2 learnt values found there; the next best place had 0)
```

## Limits

- The listing's place is an exact path. Any new wrapper or renamed class above
  the rows fails the `listing` check; that is the point, and `heal` finds the new
  place.
- A numbered step is held to the text its element began with, its rows
  aside -- a box's heading -- when every learnt page began it so and no other
  box: a box added after the listing then passes, and one inserted before,
  or the first box removed and another added at the end, fails. Where there
  is no such heading, or the page says it on no box, the step is held to the
  number of its kind the learnt pages had, and a box added after the listing
  fails too: the count cannot tell after from before. Where the learnt pages
  had different numbers, the step is not held to one.
- One listing per extractor: the page's most promising repeated group, or the
  one the examples point at.
- A page field is an element's whole text, or one attribute. A value written
  inside a sentence -- one element saying `Price: £41.90` -- is not found by
  `--want price=41.90`; one split across elements (`£41<small>.90</small>`) is,
  at the element that holds both.
- Healing matches by values seen before. A redesign that changes both the
  markup and every value at once -- a different page altogether -- is reported
  as fields vanished and new, not as moves.
- The thresholds (20% missing for a required field, half the values keeping
  their shape, five values before a shape is learnt or checked) are fixed.
- Two text fields of the same shape that swap values on a page the extractor was
  not learnt from pass the shape checks; the `reads` check catches the swap
  when one side read as an amount or a date, and the `values` check when one
  side becomes the same in every row. Two free-text columns that swap pass.
- How extractors behave across real changes, and how often healing is right, is
  measured on Wayback Machine captures in [drift](drift.md), losses first.
