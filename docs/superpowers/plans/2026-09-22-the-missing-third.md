# The Fields People Actually Want — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the two declaration styles that carry `author` and `publish_date` on real pages and that Sluicer currently ignores.

**Architecture:** One prefix widening in the existing OpenGraph reader, and one new reader for HTML's own metadata names. No new dependency; both are `lxml` over `<meta>` tags, and `src/sluicer/declared/meta.py` already holds the scan both need.

**Tech Stack:** Python 3.10+, `lxml`.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`

## Why this exists, measured

Measured on 2026-09-22 across the **359 WCXB pages** of the four types Sluicer targets (article, listing, collection, product), counting what each page declares:

| declaration | pages | share | read today |
| --- | --- | --- | --- |
| `<meta name="description">` | 313 | **87%** | no |
| `article:modified_time` | 127 | 35% | no |
| `article:published_time` | 119 | **33%** | no |
| `<meta name="author">` | 107 | **29%** | no |
| `<meta name="keywords">` | 52 | 14% | no |
| `itemprop="author"` | 39 | 10% | yes |
| `article:section` / `article:tag` | 35 | 9% | no |
| `article:author` | 29 | 8% | no |

For comparison, the three vocabularies added by the `more-vocabularies` branch — Dublin Core, RDFa and microformats — unlock **zero** pages that JSON-LD, microdata or OpenGraph do not already cover. They bought compatibility with `extruct`. This buys reach, and it is the first work on this project that does.

The consequence is concrete and was measured, not inferred: on WCXB pages that **do** declare an author, Sluicer recovers **1 in 130**. Three of the first five such pages declare it as `<meta name="author">`, one as `article:author`, one as `itemprop="author"` — and only the last is read today.

## The gain, simulated before building

The two readers were simulated over the same 359 pages on 2026-09-22 — the
current `extract()` output, plus exactly what these two readers would add,
scored against WCXB's labels:

| field | today | with this plan |
| --- | --- | --- |
| `author` | 1 of 188 — **0.01** | 45 of 188 — **0.24** |
| `publish_date` | 14 of 224 — **0.06** | 113 of 224 — **0.50** |

**This is the acceptance criterion.** Task 3 re-measures against the real
implementation; if `author` does not land near 0.24 and `publish_date` near
0.50, the readers are not doing what the simulation did and the difference must
be explained before the branch merges. A number that comes out *higher* is as
suspect as one that comes out lower.

The remaining misses are honest: the rest of those pages do not declare the
field at all, and a reader of declared data cannot invent it. That is the
`invention` column's whole point.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL. **No new dependency, in the base install or an extra.**
- No LLM call anywhere. No paid API.
- Deterministic: same page, same records, same order.
- English only everywhere including commit messages.
- Unit tests never touch the network; fixtures live under `tests/fixtures/`.
- `ruff` and `mypy --strict` stay green; coverage at or above 97%.
- Every field keeps honest provenance. **A value from `<meta name="author">` is not OpenGraph and not Dublin Core.** Reporting a plain HTML meta tag as Dublin Core is exactly the mistake `extruct` makes — measured: a page whose only tag is `<meta name="description">` comes back from `extruct` under `dublincore`. The answer is not to ignore the tag; it is to read it and call it what it is.

---

## File Structure

| file | responsibility |
| --- | --- |
| `src/sluicer/declared/opengraph.py` | extended: the protocol's vertical namespaces, not just `og:` |
| `src/sluicer/declared/htmlmeta.py` | new: HTML's own metadata names, `source="html"` |
| `src/sluicer/api.py` | extended: the seventh reader, last in precedence |

---

### Task 1: OpenGraph is more than `og:`

**Files:**
- Modify: `src/sluicer/declared/opengraph.py`, `tests/test_opengraph.py`

**Interfaces:**
- `read_opengraph(doc) -> dict[str, str]` — unchanged signature; it now also returns the vertical-namespace properties, keyed with the namespace kept: `article:published_time`, not `published_time`.

**Why the key keeps its namespace:** `og:type` and `article:section` are different statements, and `article:tag` collides with nothing only as long as it stays distinguishable from a hypothetical `og:tag`. Stripping `article:` would also make `article:author` and a future `book:author` the same key. The `og:` prefix is stripped because it is the protocol's own namespace; a vertical is a type, and the type is part of the fact.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_opengraph.py
def test_the_protocol_s_vertical_namespaces_are_opengraph_too():
    """article:published_time is how a third of real pages state a date."""
    doc = load(
        '<html><head>'
        '<meta property="og:type" content="article">'
        '<meta property="article:published_time" content="2018-07-10T09:00:00Z">'
        '<meta property="article:author" content="Kimber Streams">'
        '<meta property="article:section" content="Laptops">'
        "</head></html>"
    )

    got = read_opengraph(doc)

    assert got["type"] == "article"
    assert got["article:published_time"] == "2018-07-10T09:00:00Z"
    assert got["article:author"] == "Kimber Streams"
    assert got["article:section"] == "Laptops"


def test_a_vertical_that_is_not_the_protocol_s_is_left_alone():
    """Only the namespaces the OpenGraph protocol defines; not every colon."""
    doc = load('<html><head><meta property="fb:app_id" content="1234"></head></html>')

    assert read_opengraph(doc) == {}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_opengraph.py -v`
Expected: FAIL with `KeyError: 'article:published_time'`.

- [ ] **Step 3: Widen the prefix**

The OpenGraph protocol defines vertical object types with their own namespaces. Accept exactly these, and no others, so that `fb:`, `al:` and a site's own inventions stay out:

```python
# src/sluicer/declared/opengraph.py
VERTICALS = ("article:", "book:", "profile:", "video:", "music:")
```

`og:` keeps its prefix stripped; a vertical keeps its namespace in the key, for the reason in this task's Interfaces.

- [ ] **Step 4: Run it and watch it pass**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat: OpenGraph's vertical namespaces are OpenGraph"
```

---

### Task 2: HTML's own metadata names

**Files:**
- Create: `src/sluicer/declared/htmlmeta.py`, `tests/test_htmlmeta.py`
- Modify: `src/sluicer/api.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `read_htmlmeta(doc: Document) -> dict[str, str]`, `source="html"`.
- `extract()` runs it **last**, after `twitter`, so anything a real vocabulary declared wins.

**What it reads, and nothing else:** the metadata names the HTML standard defines — `author`, `description`, `keywords`, `generator`, `application-name`, `theme-color` — matched case-insensitively on `<meta name=...>`. **A closed list, not a catch-all.** A page's own `<meta name="csrf-token">` is not metadata about the page's subject, and a reader that returns every `name=` attribute would flood a record with site plumbing and make provenance meaningless.

**Why it is last in precedence:** `<meta name="description">` is on 87% of pages and is very often the same sentence as `og:description`. It is the weakest statement of the seven — no vocabulary, no schema, no type — so it fills gaps and never overrides.

**Why it is not in `ABOUT_A_THING`:** these names describe the document, exactly as OpenGraph and Dublin Core do. A page whose only declaration is `<meta name="description">` has said nothing about its rows, and induction must still run there. The gate needs no edit, which is the property inverting it bought.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_htmlmeta.py
from sluicer.declared.htmlmeta import read_htmlmeta
from sluicer.document import load


def test_the_standard_metadata_names_are_read():
    doc = load(
        '<html><head>'
        '<meta name="author" content="Nancy Peyer">'
        '<meta name="description" content="A sentence about the page.">'
        '<meta name="keywords" content="one, two">'
        "</head></html>"
    )

    assert read_htmlmeta(doc) == {
        "author": "Nancy Peyer",
        "description": "A sentence about the page.",
        "keywords": "one, two",
    }


def test_a_site_s_own_meta_name_is_not_metadata_about_the_page():
    """A catch-all would fill a record with plumbing and empty the provenance."""
    doc = load('<html><head><meta name="csrf-token" content="abc123"></head></html>')

    assert read_htmlmeta(doc) == {}


def test_the_name_is_matched_without_regard_to_case():
    doc = load('<html><head><meta name="Author" content="Nancy Peyer"></head></html>')

    assert read_htmlmeta(doc) == {"author": "Nancy Peyer"}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_htmlmeta.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared.htmlmeta'`.

- [ ] **Step 3: Write the reader**

Use the shared `<meta>` scan in `src/sluicer/declared/meta.py` rather than a fourth copy of the same xpath.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Wire it last, and prove the precedence**

```python
# add to tests/test_api.py
def test_a_real_vocabulary_beats_a_bare_meta_name():
    html = (
        '<html><head>'
        '<meta property="og:description" content="FROM OPENGRAPH">'
        '<meta name="description" content="FROM THE BARE META TAG">'
        "</head></html>"
    )

    field = sluicer.extract(html).records[0].fields["description"]

    assert field.value == "FROM OPENGRAPH"
    assert field.source == "opengraph"


def test_a_bare_meta_name_does_not_switch_induction_off():
    rows = "".join(f'<li class="r"><span class="sku">A{n}</span></li>' for n in range(5))
    html = (
        '<html><head><meta name="description" content="A catalogue."></head>'
        f"<body><ul>{rows}</ul></body></html>"
    )

    assert "induced" in sluicer.extract(html, induce=True).sources
```

- [ ] **Step 6: Run the whole suite and commit**

```bash
git add src/sluicer/declared/htmlmeta.py tests/test_htmlmeta.py src/sluicer/api.py tests/test_api.py
git commit -m "feat: read HTML's own metadata names, and say that is what they are"
```

---

### Task 3: Measure the gain, and write down what it was

**Files:**
- Modify: `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `docs/field-survey.md`, `agent-skill/sluicer/SKILL.md`

- [ ] **Step 1: Re-measure against the corpus**

Against the 359 WCXB pages of the four target types, count how many now yield an `author` and a `publish_date` where one is declared, and compare with the number before this branch (author: 1 of 130 judgeable pages; publish_date: 13 of 137).

- [ ] **Step 2: Write the measured numbers into `docs/field-survey.md`**, in the same shape as the table in "Why this exists" — before and after, on the same corpus, with the corpus named and attributed (WCXB, CC-BY-4.0, Murrough Foley).

- [ ] **Step 3: Update the README's vocabulary list and the precedence sentence.** The order becomes: JSON-LD, microdata, microformats, RDFa, Dublin Core, OpenGraph, Twitter card, HTML metadata names.

- [ ] **Step 4: Commit**

---

## Out of scope

`<meta name="robots">`, `viewport`, `charset` and the rest of the browser-directive names: they are instructions to a client, not statements about the page's subject, and putting them in a record would be the same category error as the catch-all this plan refuses.
