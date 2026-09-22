# Structure Induction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read pages that declare nothing, by finding the repeating shapes in their markup and returning the records those shapes describe.

**Architecture:** Three pure functions over an lxml tree, each testable on its own. A shape signature turns an element into a comparable string. A group finder returns the largest set of siblings sharing a signature. A record builder turns one such group into records whose fields are keyed by their position in the shape. Nothing fetches, nothing guesses beyond what the markup itself repeats.

**Tech Stack:** Python 3.10+, `lxml`. No new dependency, base install only.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`, section 4.2.3.

## Why this exists, measured

On twelve real pages of mixed kinds, nine declared structured data and two declared nothing at all: Hacker News and a Stack Overflow question list. Both are pages whose whole content is a repeating list, obvious to any human and invisible to Sluicer today. Roughly a quarter of the web Sluicer meets is in that state.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL.
- No LLM call anywhere. No paid API.
- **Deterministic**: the same markup always yields the same records, in the same order.
- English only everywhere including commit messages.
- Unit tests never touch the network; every fixture is a file under `tests/fixtures/`.
- Every public function typed, annotations honest. `ruff` and `mypy --strict` must stay green.
- Induced records are marked as induced. A caller must always be able to tell a field the page declared from a field we inferred.

---

## File Structure

| file | responsibility |
| --- | --- |
| `src/sluicer/induce/__init__.py` | the surface: `induce` |
| `src/sluicer/induce/shape.py` | `signature()`, what makes two elements the same shape |
| `src/sluicer/induce/groups.py` | `repeating_groups()`, finding the siblings that repeat |
| `src/sluicer/induce/records.py` | `records_from()`, turning one group into records |

---

### Task 1: The shape of an element

**Files:**
- Create: `src/sluicer/induce/__init__.py`, `src/sluicer/induce/shape.py`, `tests/test_shape.py`

**Interfaces:**
- Produces: `signature(element, depth: int = 3) -> str`.

**What a signature is:** a string describing an element's tag, its class attribute reduced to a sorted set, and the same for its descendants down to `depth`. Two elements with the same signature are the same kind of thing. Text is not part of it: two products differ in their words and agree in their shape, and it is the agreement we are looking for.

Classes are sorted so that `class="a b"` and `class="b a"` agree, and truncated to the first three so that a framework's long utility-class lists do not make every element unique.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shape.py
import lxml.html

from sluicer.induce.shape import signature


def element(html):
    return lxml.html.fromstring(html)


def test_two_items_of_the_same_kind_share_a_signature():
    one = element('<li class="row"><h3>A</h3><span class="price">1</span></li>')
    two = element('<li class="row"><h3>B</h3><span class="price">2</span></li>')

    assert signature(one) == signature(two)


def test_different_shapes_do_not_share_a_signature():
    item = element('<li class="row"><h3>A</h3></li>')
    other = element('<li class="row"><h3>A</h3><img src="x"></li>')

    assert signature(item) != signature(other)


def test_the_words_inside_do_not_change_the_shape():
    short = element("<li><p>hi</p></li>")
    long = element("<li><p>" + ("a lot of words " * 50) + "</p></li>")

    assert signature(short) == signature(long)


def test_class_order_does_not_change_the_shape():
    one = element('<li class="a b"><p>x</p></li>')
    two = element('<li class="b a"><p>x</p></li>')

    assert signature(one) == signature(two)


def test_depth_is_bounded_so_a_deep_page_stays_comparable():
    shallow = element("<div><p>x</p></div>")
    deep = element("<div><p>x<em><b><i><u>deep</u></i></b></em></p></div>")

    assert signature(shallow, depth=1) == signature(deep, depth=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_shape.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.induce'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/induce/__init__.py
"""Reading the pages that declare nothing, by what their markup repeats."""
```

```python
# src/sluicer/induce/shape.py
"""What makes two elements the same kind of thing.

A page that lists twenty products repeats one shape twenty times. The words
differ and the shape agrees, so the shape is what we compare. Text is
deliberately not part of a signature, and neither is anything below a bounded
depth: two cards that differ only in how deeply their prose is nested are still
two cards.
"""

from __future__ import annotations

from lxml.html import HtmlElement

_MAX_CLASSES = 3


def _own(element: HtmlElement) -> str:
    classes = sorted((element.get("class") or "").split())[:_MAX_CLASSES]
    tag = element.tag if isinstance(element.tag, str) else "?"
    return tag + ("." + ".".join(classes) if classes else "")


def signature(element: HtmlElement, depth: int = 3) -> str:
    """Return a string that two elements of the same kind share."""
    if depth <= 0:
        return _own(element)
    children = [
        signature(child, depth - 1)
        for child in element
        if isinstance(child.tag, str)
    ]
    return _own(element) + "(" + ",".join(children) + ")"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_shape.py -v`
Expected: PASS, all five

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/induce tests/test_shape.py
git commit -m "feat: a signature says when two elements are the same kind of thing"
```

---

### Task 2: The siblings that repeat

**Files:**
- Create: `src/sluicer/induce/groups.py`, `tests/test_groups.py`, `tests/fixtures/listing_no_declared_data.html`

**Interfaces:**
- Produces: `repeating_groups(tree: HtmlElement, minimum: int = 3) -> list[list[HtmlElement]]`, ordered best first.

**What counts as a group:** children of one parent, sharing a signature, at least `minimum` of them. Ordering is by how much they promise: the number of members times the number of distinct child positions in the shape, so twenty rich cards beat forty empty list items. Ties break on document order, because the answer must not depend on a dictionary's mood.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_groups.py
from pathlib import Path

import lxml.html

from sluicer.induce.groups import repeating_groups

FIXTURES = Path(__file__).parent / "fixtures"


def test_a_listing_page_yields_its_rows():
    tree = lxml.html.fromstring((FIXTURES / "listing_no_declared_data.html").read_text())

    groups = repeating_groups(tree)

    assert groups, "a page that is one long list should yield a group"
    assert len(groups[0]) == 4


def test_two_of_a_kind_is_not_a_pattern():
    tree = lxml.html.fromstring(
        "<div><p class='x'><b>a</b></p><p class='x'><b>b</b></p></div>"
    )

    assert repeating_groups(tree, minimum=3) == []


def test_the_richer_group_comes_first():
    tree = lxml.html.fromstring(
        "<body>"
        "<ul>" + "<li><a>x</a></li>" * 6 + "</ul>"
        "<div>" + "<article><h3>t</h3><p>b</p><span>s</span></article>" * 4 + "</div>"
        "</body>"
    )

    groups = repeating_groups(tree)

    assert len(groups[0]) == 4, "the four rich cards should beat the six thin links"


def test_the_order_is_stable_across_runs():
    html = "<div>" + "<li><a>x</a><b>y</b></li>" * 5 + "</div>"

    first = [len(g) for g in repeating_groups(lxml.html.fromstring(html))]
    second = [len(g) for g in repeating_groups(lxml.html.fromstring(html))]

    assert first == second
```

Fixture `tests/fixtures/listing_no_declared_data.html`:

```html
<!doctype html>
<html><head><title>Parts</title></head>
<body>
  <nav><a href="/">Home</a><a href="/help">Help</a></nav>
  <main>
    <div class="results">
      <div class="card"><h3 class="name">Brake pad set</h3><span class="price">41.99</span><a class="more" href="/p/1">details</a></div>
      <div class="card"><h3 class="name">Oil filter</h3><span class="price">8.50</span><a class="more" href="/p/2">details</a></div>
      <div class="card"><h3 class="name">Wiper blade</h3><span class="price">12.00</span><a class="more" href="/p/3">details</a></div>
      <div class="card"><h3 class="name">Spark plug</h3><span class="price">3.25</span><a class="more" href="/p/4">details</a></div>
    </div>
  </main>
  <footer><p>copyright</p></footer>
</body></html>
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_groups.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.induce.groups'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/induce/groups.py
"""Finding the siblings a page repeats.

A listing page is a parent whose children are the same shape over and over. We
look for exactly that, and rank what we find by how much each candidate
promises: many members, each with many parts. Two of a kind is a coincidence,
so the floor is three.
"""

from __future__ import annotations

from collections import defaultdict

from lxml.html import HtmlElement

from sluicer.induce.shape import signature


def repeating_groups(
    tree: HtmlElement, minimum: int = 3
) -> list[list[HtmlElement]]:
    """Return groups of same-shaped siblings, the most promising first."""
    found: list[tuple[int, int, list[HtmlElement]]] = []
    for order, parent in enumerate(tree.iter()):
        if not isinstance(parent.tag, str):
            continue
        by_shape: dict[str, list[HtmlElement]] = defaultdict(list)
        for child in parent:
            if isinstance(child.tag, str):
                by_shape[signature(child)].append(child)
        for members in by_shape.values():
            if len(members) >= minimum:
                parts = max(len(list(member)) for member in members)
                found.append((len(members) * max(parts, 1), order, members))
    found.sort(key=lambda item: (-item[0], item[1]))
    return [members for _, _, members in found]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_groups.py -v`
Expected: PASS, all four

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/induce/groups.py tests/test_groups.py tests/fixtures/listing_no_declared_data.html
git commit -m "feat: find the siblings a page repeats, best first"
```

---

### Task 3: Records from a group

**Files:**
- Create: `src/sluicer/induce/records.py`, `tests/test_induce.py`
- Modify: `src/sluicer/induce/__init__.py`, `src/sluicer/api.py`, `src/sluicer/__init__.py`

**Interfaces:**
- Produces: `records_from(group) -> list[Record]` and `induce(doc: Document, minimum: int = 3) -> list[Record]`, re-exported as `sluicer.induce`.
- `extract()` gains `induce: bool = False`. When it is true and the declared readers found nothing, induction runs and its records are added, each field carrying `source="induced"`.

**Field naming, and why it is honest:** we cannot know a field is called "price". We can know it is the second `span` of the card, and that it holds `41.99`. So a field is named by its position in the shape, plus its class when it has one, which is the most a page that declares nothing has told us. A caller sees `span.price` and decides what it means; nothing here pretends to have read the page's mind.

**The rule that matters:** induction never runs unless asked, and never overrides a declared field. Declared data is what a page says about itself; induced data is what we noticed. They are not the same kind of claim and they never share a name without the `source` saying which is which.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_induce.py
from pathlib import Path

import sluicer
from sluicer.document import load
from sluicer.induce import induce

FIXTURES = Path(__file__).parent / "fixtures"


def listing():
    return load((FIXTURES / "listing_no_declared_data.html").read_text())


def test_a_page_that_declares_nothing_still_yields_records():
    records = induce(listing())

    assert len(records) == 4


def test_every_induced_field_says_it_was_induced():
    records = induce(listing())

    for record in records:
        for field in record.fields.values():
            assert field.source == "induced"


def test_the_values_are_the_ones_on_the_page():
    records = induce(listing())

    values = {field.value for field in records[0].fields.values()}
    assert "Brake pad set" in values
    assert "41.99" in values


def test_a_link_keeps_its_address():
    records = induce(listing())

    values = {field.value for field in records[0].fields.values()}
    assert "/p/1" in values


def test_induction_is_off_unless_asked():
    html = (FIXTURES / "listing_no_declared_data.html").read_text()

    assert sluicer.extract(html).records == []
    assert sluicer.extract(html, induce=True).records


def test_a_page_that_declares_data_is_not_second_guessed():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, induce=True)

    assert result.sources == ["jsonld"], "declared data stands on its own"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_induce.py -v`
Expected: FAIL with `ImportError: cannot import name 'induce'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/induce/records.py
"""Turning one repeated shape into the records it describes.

A page that declares nothing has not told us what its fields are called, so we
do not invent names for them. A field is named by where it sits in the shape and
what class it carries, which is exactly as much as the page said, and every one
of them is marked as induced so a caller never mistakes it for a declaration.
"""

from __future__ import annotations

from lxml.html import HtmlElement

from sluicer.declared.merge import Field, Record

_ADDRESS = {"a": "href", "img": "src", "link": "href", "source": "src"}


def _name(element: HtmlElement, position: int) -> str:
    classes = sorted((element.get("class") or "").split())[:1]
    tag = element.tag if isinstance(element.tag, str) else "node"
    return f"{tag}.{classes[0]}" if classes else f"{tag}{position}"


def _value(element: HtmlElement) -> str:
    attribute = _ADDRESS.get(element.tag if isinstance(element.tag, str) else "")
    if attribute and element.get(attribute):
        return str(element.get(attribute)).strip()
    return " ".join((element.text_content() or "").split())


def records_from(group: list[HtmlElement]) -> list[Record]:
    """Return one record per member of ``group``."""
    records: list[Record] = []
    for member in group:
        record = Record(type=None)
        for position, part in enumerate(member.iter()):
            if part is member or not isinstance(part.tag, str):
                continue
            value = _value(part)
            if not value:
                continue
            name = _name(part, position)
            record.fields.setdefault(name, Field(value=value, source="induced"))
        if record.fields:
            records.append(record)
    return records
```

```python
# src/sluicer/induce/__init__.py
"""Reading the pages that declare nothing, by what their markup repeats."""

from __future__ import annotations

from sluicer.declared.merge import Record
from sluicer.document import Document
from sluicer.induce.groups import repeating_groups
from sluicer.induce.records import records_from

__all__ = ["induce"]


def induce(doc: Document, minimum: int = 3) -> list[Record]:
    """Return the records the page's most promising repeated shape describes."""
    groups = repeating_groups(doc.tree, minimum=minimum)
    return records_from(groups[0]) if groups else []
```

Then widen `extract()` in `src/sluicer/api.py` with `induce: bool = False`. When it is true **and** no declared record was found, run induction, put its records in `records`, and add `"induced"` to `sources`. Declared data always wins: if any reader fired, induction does not run at all. Re-export `induce` from the package root.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/induce src/sluicer/api.py src/sluicer/__init__.py tests/test_induce.py
git commit -m "feat: records from a page that declares nothing"
```

---

## Out of scope

Naming a field by reading a nearby label, aligning fields across two pages of the same template, nested records inside a record, and pagination. Each is its own plan.
