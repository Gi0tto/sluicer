# More Vocabularies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read every vocabulary the abandoned library half a million people still download reads, and stay lighter than it while doing so.

**Architecture:** Two new readers beside the three that exist, in the same shape: a pure function taking a `Document` and returning what the page declares. Dublin Core and RDFa Lite need nothing but `lxml`, which is already a base dependency. Microformats needs a real parser and therefore an optional extra, so the base install stays two packages.

**Tech Stack:** Python 3.10+, `lxml`. `mf2py` under a new `microformats` extra, and only there.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`, section 4.2.2.

## Why this exists, measured

`extruct` reads embedded metadata and is downloaded **540,765 times a month**. Its last release was 683 days ago, it has taken **zero commits in twelve months**, and 61 issues sit open. Half a million downloads a month rest on a library nobody maintains.

It reads six things: microdata, JSON-LD, microformats, OpenGraph, RDFa, Dublin Core. Sluicer reads three of them. Until the other three are here, "reads more, and is maintained" is not a sentence this project may write.

It pays for its six with eight dependencies: `lxml`, `lxml-html-clean`, `rdflib`, `pyrdfa3`, `mf2py`, `w3lib`, `html-text`, `jstyleson`. Sluicer's base install is `lxml` and `click`. Keeping that gap while closing the other one is the whole point of this plan: two of the three readers need nothing new at all.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL.
- No LLM call anywhere. No paid API.
- Deterministic: same page, same records, same order.
- English only everywhere including commit messages.
- Unit tests never touch the network; fixtures live under `tests/fixtures/`.
- `ruff` and `mypy --strict` stay green; coverage stays at or above its floor.
- **The base install gains no dependency.** Dublin Core and RDFa Lite use `lxml` only. Microformats lives behind `sluicer[microformats]` and follows the settled pattern: lazy import through `sluicer.extras.import_extra`, a named exception, an install hint.
- Every new field keeps provenance: `source` is `"dublincore"`, `"rdfa"` or `"microformats"`.

---

## File Structure

| file | responsibility |
| --- | --- |
| `src/sluicer/declared/dublincore.py` | `read_dublincore()` |
| `src/sluicer/declared/rdfa.py` | `read_rdfa()` |
| `src/sluicer/declared/microformats.py` | `read_microformats()`, behind the extra |
| `src/sluicer/declared/merge.py` | extended: the new sources take their place in the order of precedence |
| `src/sluicer/api.py` | extended: the new readers run, and report themselves in `sources` |

---

### Task 1: Dublin Core

**Files:**
- Create: `src/sluicer/declared/dublincore.py`, `tests/test_dublincore.py`

**Interfaces:**
- Produces: `read_dublincore(doc: Document) -> dict` — a flat mapping, prefixes stripped, empty when the page declares none.

**What it is:** a convention older than schema.org, still carried by libraries, universities, repositories and government sites: `<meta name="DC.title">`, `<meta name="DCTERMS.created">`, sometimes with a `scheme` attribute. The names are case-insensitive in practice, and both `DC.` and `DCTERMS.` prefixes appear, sometimes on the same page.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dublincore.py
from sluicer.declared.dublincore import read_dublincore
from sluicer.document import load


def test_it_reads_the_classic_prefix():
    doc = load(
        '<html><head>'
        '<meta name="DC.title" content="Of the Standard of Taste">'
        '<meta name="DC.creator" content="David Hume">'
        "</head><body></body></html>"
    )

    assert read_dublincore(doc) == {
        "title": "Of the Standard of Taste",
        "creator": "David Hume",
    }


def test_it_reads_the_terms_prefix_too():
    doc = load('<html><head><meta name="DCTERMS.created" content="1757"></head></html>')

    assert read_dublincore(doc) == {"created": "1757"}


def test_the_prefix_is_case_insensitive_because_the_web_is():
    doc = load('<html><head><meta name="dc.title" content="Lower"></head></html>')

    assert read_dublincore(doc) == {"title": "Lower"}


def test_an_empty_value_is_not_a_value():
    doc = load('<html><head><meta name="DC.title" content="   "></head></html>')

    assert read_dublincore(doc) == {}


def test_the_first_of_a_repeated_name_wins_as_everywhere_else():
    doc = load(
        '<html><head>'
        '<meta name="DC.subject" content="aesthetics">'
        '<meta name="DC.subject" content="philosophy">'
        "</head></html>"
    )

    assert read_dublincore(doc) == {"subject": "aesthetics"}


def test_a_page_declaring_none_returns_an_empty_mapping():
    assert read_dublincore(load("<html><body>hi</body></html>")) == {}


def test_an_unrelated_meta_is_not_mistaken_for_one():
    doc = load('<html><head><meta name="description" content="not dublin core"></head></html>')

    assert read_dublincore(doc) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dublincore.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared.dublincore'`

- [ ] **Step 3: Write minimal implementation**

Follow the house style of `opengraph.py` exactly: a module docstring saying what the file is for and why it exists, a private prefix constant, one typed public function, first-wins on a repeated name, and an empty or whitespace-only value dropped, as every reader in this package already does.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dublincore.py -v`
Expected: PASS, all seven

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared/dublincore.py tests/test_dublincore.py
git commit -m "feat: read Dublin Core, which the older web still carries"
```

---

- [ ] **Step 6: Write the failing test for the induction gate**

Dublin Core describes the *document*, exactly as OpenGraph does. The gate that
decides whether to induce asks `field.source != "opengraph"`, so the moment
`dublincore` lands, a page carrying `<meta name="DC.title">` counts as having
declared something about its rows and induction switches off there — silently,
with nothing failing.

```python
# add to tests/test_api.py
def test_a_document_level_declaration_does_not_switch_induction_off():
    """DC.title says what the page is, not what is in its list."""
    rows = "".join(
        f'<li class="row"><span class="sku">A{n}</span></li>' for n in range(5)
    )
    html = (
        '<html><head><meta name="DC.title" content="Catalogue"></head>'
        f"<body><ul>{rows}</ul></body></html>"
    )

    result = sluicer.extract(html, induce=True)

    assert "induced" in result.sources
    assert len([r for r in result.records if r.fields.get("span.sku")]) == 5
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py::test_a_document_level_declaration_does_not_switch_induction_off -v`
Expected: this end-to-end test **passes** today, because wiring the reader into
`extract()` is Task 3 and no page can yet reach the gate carrying a `dublincore`
field. Keep it as Task 3's regression guard, and add a test that does fail now,
asserting `_declared_about_its_things` directly on a `Record` whose field has
`source="dublincore"`. A step that predicts a failure which cannot happen is a
step that proves nothing.

- [ ] **Step 8: Invert the gate**

Do not add `"dublincore"` to the exclusion. An exclusion list fixes today and
breaks again on the next document-level vocabulary, because the list is where
the defect goes to live. Name instead the sources that describe a *thing*:

```python
# src/sluicer/api.py
# The vocabularies that describe a thing on the page rather than the page
# itself. Named positively on purpose: the gate used to ask which source was
# not OpenGraph, and every document-level vocabulary added after it would have
# switched induction off silently. A reader added here is a reader claiming to
# describe the page's subject; anything unlisted is taken to describe the
# document, which is the safe side -- it lets induction run.
ABOUT_A_THING = frozenset({"jsonld", "microdata", "rdfa", "microformats"})


def _declared_about_its_things(records: list[Record]) -> bool:
    """True when a reader produced a field about a thing on the page."""
    return any(
        field.source in ABOUT_A_THING
        for record in records
        for field in record.fields.values()
    )
```

`rdfa` and `microformats` are listed before their readers exist, in this one
task, because the set is the statement of the rule and splitting it across
three tasks would leave two windows where a page is judged by a half-written
rule.

- [ ] **Step 9: Run the whole suite and commit**

Run: `uv run pytest -q`
Expected: PASS, including every induction test that merged before this branch.

```bash
git add src/sluicer/api.py tests/test_api.py
git commit -m "fix: the induction gate names what describes a thing"
```

---

### Task 2: RDFa Lite

**Files:**
- Create: `src/sluicer/declared/rdfa.py`, `tests/test_rdfa.py`

**Interfaces:**
- Produces: `read_rdfa(doc: Document) -> list[dict]` — one dict per `typeof` subject, `@type` carrying the type's leaf name, exactly as microdata does.

**What we implement and what we do not, stated plainly:** RDFa Lite, which is the subset the W3C itself recommends for authors and which covers what real pages carry: `vocab`, `typeof`, `property`, `resource`, `prefix`. Full RDFa needs a triple store, which is why `extruct` pulls `rdflib` and `pyrdfa3` and still calls its support experimental. We do the Lite subset in pure `lxml`, name it honestly in the docstring and in the known limits, and add no dependency. A reader who needs the full graph is better served by a triple store than by us pretending.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rdfa.py
from sluicer.declared.rdfa import read_rdfa
from sluicer.document import load

PRODUCT = (
    '<html><body>'
    '<div vocab="https://schema.org/" typeof="Product">'
    '  <span property="name">Brake pad set</span>'
    '  <span property="sku">BP-1187</span>'
    '  <a property="url" href="/p/1">details</a>'
    '  <img property="image" src="/i/1.jpg" alt="a photo">'
    "</div></body></html>"
)


def test_it_reads_a_subject_and_its_properties():
    found = read_rdfa(load(PRODUCT))

    assert len(found) == 1
    assert found[0]["@type"] == "Product"
    assert found[0]["name"] == "Brake pad set"
    assert found[0]["sku"] == "BP-1187"


def test_an_address_comes_from_the_attribute_not_the_text():
    found = read_rdfa(load(PRODUCT))

    assert found[0]["url"] == "/p/1"
    assert found[0]["image"] == "/i/1.jpg"


def test_a_content_attribute_wins_over_the_text():
    doc = load(
        '<div vocab="https://schema.org/" typeof="Offer">'
        '<span property="price" content="41.99">forty-one ninety-nine</span></div>'
    )

    assert read_rdfa(doc)[0]["price"] == "41.99"


def test_two_subjects_stay_two():
    doc = load(
        '<body>'
        '<div vocab="https://schema.org/" typeof="Product"><span property="name">One</span></div>'
        '<div vocab="https://schema.org/" typeof="Product"><span property="name">Two</span></div>'
        "</body>"
    )

    found = read_rdfa(doc)

    assert [item["name"] for item in found] == ["One", "Two"]


def test_a_property_belongs_to_its_nearest_subject():
    doc = load(
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">Outer</span>'
        '<div typeof="Offer"><span property="price">1.00</span></div>'
        "</div>"
    )

    found = read_rdfa(doc)

    outer = next(item for item in found if item["@type"] == "Product")
    inner = next(item for item in found if item["@type"] == "Offer")
    assert "price" not in outer
    assert inner["price"] == "1.00"


def test_an_empty_value_is_not_a_value():
    doc = load('<div typeof="Product"><span property="name">   </span></div>')

    assert read_rdfa(doc) == [{"@type": "Product"}]


def test_a_page_with_no_rdfa_returns_nothing():
    assert read_rdfa(load("<html><body><p>hi</p></body></html>")) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rdfa.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared.rdfa'`

- [ ] **Step 3: Write minimal implementation**

Mirror `microdata.py`, which solved the same problem for a different attribute set. In particular reuse the rule that a property belongs to its **nearest** enclosing subject, walking ancestors in Python rather than writing unreadable XPath: that rule was a review finding on microdata and it applies identically here. Values come from `content` first, then from the address attribute for `a`, `img`, `link`, then from the text.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared/rdfa.py tests/test_rdfa.py
git commit -m "feat: read RDFa Lite, without a triple store"
```

---

### Task 3: The readers take their place

**Files:**
- Modify: `src/sluicer/api.py`, `src/sluicer/declared/merge.py`, `tests/test_api.py`, `tests/test_merge.py`

**Interfaces:**
- `extract()` runs all five readers. `sources` reports each that fired, in a fixed order.
- Precedence, stated once and tested: JSON-LD, then microdata, then RDFa, then Dublin Core, then OpenGraph.

**Why that order:** the first three describe the thing the page is about, in decreasing order of how much the modern web uses them. Dublin Core and OpenGraph describe the *document*, which is why they come last and why a page whose only declaration is OpenGraph still counts as having declared nothing about its rows, a rule the induction gate already relies on.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_api.py
def test_all_five_readers_are_reported():
    html = (
        '<html><head>'
        '<script type="application/ld+json">{"@type":"Product","name":"From JSON-LD"}</script>'
        '<meta name="DC.title" content="From Dublin Core">'
        '<meta property="og:site_name" content="From OpenGraph">'
        "</head><body>"
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="mpn">From microdata</span></div>'
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="gtin">From RDFa</span></div>'
        "</body></html>"
    )

    result = sluicer.extract(html)

    assert result.sources == ["jsonld", "microdata", "rdfa", "dublincore", "opengraph"]


def test_the_earlier_vocabulary_wins_the_field():
    html = (
        '<html><head>'
        '<script type="application/ld+json">{"@type":"Product","name":"From JSON-LD"}</script>'
        "</head><body>"
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="name">From RDFa</span></div>'
        "</body></html>"
    )

    record = sluicer.extract(html).records[0]

    assert record.fields["name"].value == "From JSON-LD"
    assert record.fields["name"].source == "jsonld"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL: `sources` has three entries, not five.

- [ ] **Step 3: Write minimal implementation**

Widen `merge()` to take the two new findings and fold them at their place in the order. Widen `extract()` to call the new readers and name them in `sources`. Nothing else changes: the folding rule, the provenance and the induction gate all stay exactly as they are.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer tests
git commit -m "feat: five vocabularies, in a stated order of precedence"
```

---

### Task 3b (folded into Task 3): the Twitter card stops calling itself OpenGraph

`src/sluicer/declared/opengraph.py` reads two vocabularies — `og:` and
`twitter:` — and labels every field it returns `source="opengraph"`, choosing
between them with `setdefault` over document order. Measured on the tree as it
stands:

```python
a = ('<meta name="twitter:title" content="FROM THE TWITTER CARD">'
     '<meta property="og:title" content="FROM OPENGRAPH">')
b = ('<meta property="og:title" content="FROM OPENGRAPH">'
     '<meta name="twitter:title" content="FROM THE TWITTER CARD">')
# a -> title = 'FROM THE TWITTER CARD', source='opengraph'
# b -> title = 'FROM OPENGRAPH',        source='opengraph'
```

Two promises break at once. The provenance is false: a value from a Twitter
card reports that an OpenGraph reader won it, and per-field provenance is this
project's first selling point. And the precedence between the two is written
nowhere — the winner is whichever the page's author typed first. The result
stays deterministic, so no test catches it.

The keys collide in the wild rather than in theory: `og:title` and
`twitter:title` both strip to `title`, `og:image:alt` and `twitter:image:alt`
both to `image:alt`. Across ten live pages measured on 2026-09-22, `card`
appeared on six and `site` on five — both Twitter-only keys, both reported as
OpenGraph today.

So: `read_opengraph` keeps only `og:`, a new `read_twitter` in
`src/sluicer/declared/twitter.py` returns `twitter:` with `source="twitter"`,
and it runs **after** OpenGraph so an `og:` value wins a colliding key. This
lands inside Task 3 because it rewrites the same precedence chain Task 3
rewrites; separating them would edit that chain twice and ship a README stating
a precedence already known to be wrong.

`ABOUT_A_THING` is not touched, and that is the point. A Twitter card describes
the document, so it stays outside the set and induction still runs on a page
whose only declaration is chrome. A gate that listed exclusions would have
needed editing here, and nothing would have failed if it had been forgotten.

---

### Task 4: Microformats, behind an extra

**Files:**
- Create: `src/sluicer/declared/microformats.py`, `tests/test_microformats.py`
- Modify: `pyproject.toml`, `src/sluicer/api.py`

**Interfaces:**
- Produces: `MicroformatsExtraMissing`, `read_microformats(doc: Document) -> list[dict]`.
- `extract()` gains `microformats: bool = False`. It is off by default because it needs a package the base install does not carry, and a reader that raises unless someone installed something is not a default.

**The pattern, already settled twice on this project:** lazy import through `sluicer.extras.import_extra`, a named exception subclassing `MissingExtra`, an install hint naming `sluicer[microformats]`, and only a genuinely absent package raising it. Tests fake `mf2py` through `sys.modules`; none of them may require it installed.

- [ ] **Step 1: Write the failing test**

Write it in the shape of `tests/test_markdown.py`, which faked `trafilatura` the same way: a fake `mf2py` module recording what it was given, a test that the parsed output becomes records, a test that an absent package raises with the install hint, and a test that a broken-but-present package re-raises untouched.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_microformats.py -v`

- [ ] **Step 3: Write minimal implementation**

`mf2py` returns a nested structure; flatten each top-level `h-*` item into one dict with `@type` from its first class and scalar properties from its `properties`, dropping nested items rather than guessing at them, and say so in the docstring. Add `microformats = ["mf2py>=2.0"]` to the optional dependencies.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared/microformats.py tests/test_microformats.py pyproject.toml src/sluicer/api.py
git commit -m "feat: read microformats when asked, behind its own extra"
```

---

## Out of scope

Full RDFa with a triple store, JSON-LD framing and context resolution, and nested microformat items. Each would need a graph library, and the point of this plan is to close the gap without becoming one.
