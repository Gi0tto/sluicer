# Declared-Data Spine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the first working slice of Sluicer: read the structured data a page already declares (JSON-LD, microdata, OpenGraph), merge it into one record set with provenance, and expose it through a Python API and a CLI.

**Architecture:** A pure function core. `load()` turns bytes into a parsed document, three independent readers each return their own findings, `merge()` folds them into a single record list where every field remembers which reader produced it. No network, no model, no global state. Later plans add the fetch ladder, structure induction, trust scoring and the scoreboard on top of this spine.

**Tech Stack:** Python 3.10+, `lxml` (parsing), `pytest` (tests), `click` (CLI), `uv` (env and install). No network dependency in this plan.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`

## Global Constraints

- Python `>=3.10`.
- Licence MIT. No AGPL code vendored, ever.
- No LLM call anywhere in the path, not even as a fallback.
- No paid API, and no feature that requires somebody's key to work.
- Deterministic: the same input bytes must always produce the same output.
- English only: code, comments, docstrings, test names, commit messages, docs.
- Unit tests never touch the network. Fixtures live on disk under `tests/fixtures/`.
- Every public function is typed. The public surface (`extract`, `merge`) returns
  dataclasses; the declared-data readers return the shapes the page itself uses
  (`list[dict]`, `dict`), because the schema.org vocabulary is open-ended and a
  dataclass per vocabulary would be waste.

---

## File Structure

| file | responsibility |
| --- | --- |
| `pyproject.toml` | package metadata, deps, CLI entry point |
| `src/sluicer/__init__.py` | public surface: `extract`, `__version__` |
| `src/sluicer/document.py` | `Document` dataclass, `load()` |
| `src/sluicer/declared/jsonld.py` | JSON-LD reader |
| `src/sluicer/declared/microdata.py` | microdata reader |
| `src/sluicer/declared/opengraph.py` | OpenGraph and twitter meta reader |
| `src/sluicer/declared/merge.py` | `Field`, `Record`, `merge()` |
| `src/sluicer/api.py` | `extract()` orchestration |
| `src/sluicer/cli.py` | `sluicer extract` command |
| `tests/fixtures/*.html` | saved pages, one per shape |

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`, `src/sluicer/__init__.py`, `tests/test_package.py`

**Interfaces:**
- Consumes: nothing.
- Produces: importable package `sluicer` exposing `__version__: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_package.py
def test_package_exposes_a_version():
    import sluicer

    assert sluicer.__version__.count(".") == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "sluicer"
version = "0.0.1"
description = "Turn a web page into structured data with no model in the loop."
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
dependencies = ["lxml>=5.0", "click>=8.1"]

[project.scripts]
sluicer = "sluicer.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/sluicer"]

[dependency-groups]
dev = ["pytest>=8.0"]
```

```python
# src/sluicer/__init__.py
"""Deterministic extraction of the data a web page already declares."""

__version__ = "0.0.1"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_package.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/sluicer/__init__.py tests/test_package.py
git commit -m "feat: package scaffolding with version surface"
```

---

### Task 2: Document loading

**Files:**
- Create: `src/sluicer/document.py`, `tests/test_document.py`, `tests/fixtures/plain.html`

**Interfaces:**
- Consumes: nothing.
- Produces: `Document(url: str | None, html: str, tree: lxml.html.HtmlElement)` and `load(html: str, url: str | None = None) -> Document`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_document.py
from pathlib import Path

from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_parses_html_and_keeps_the_source():
    html = (FIXTURES / "plain.html").read_text()

    doc = load(html, url="https://example.com/a")

    assert doc.url == "https://example.com/a"
    assert doc.html == html
    assert doc.tree.findtext(".//title") == "Plain page"


def test_load_survives_broken_markup():
    doc = load("<html><body><p>unclosed")

    assert doc.tree.findtext(".//p") == "unclosed"
```

Fixture `tests/fixtures/plain.html`:

```html
<!doctype html>
<html><head><title>Plain page</title></head>
<body><p>Nothing declared here.</p></body></html>
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_document.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.document'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/document.py
"""The parsed page every reader works from."""

from __future__ import annotations

from dataclasses import dataclass

import lxml.html


@dataclass(frozen=True)
class Document:
    """A page that has been parsed once and is read many times."""

    html: str
    tree: lxml.html.HtmlElement
    url: str | None = None


def load(html: str, url: str | None = None) -> Document:
    """Parse ``html`` into a Document, tolerating broken markup."""
    tree = lxml.html.fromstring(html)
    return Document(html=html, tree=tree, url=url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_document.py -v`
Expected: PASS, both tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/document.py tests/test_document.py tests/fixtures/plain.html
git commit -m "feat: parse a page once into a Document"
```

---

### Task 3: JSON-LD reader

**Files:**
- Create: `src/sluicer/declared/__init__.py`, `src/sluicer/declared/jsonld.py`, `tests/test_jsonld.py`, `tests/fixtures/product_jsonld.html`

**Interfaces:**
- Consumes: `Document` from Task 2.
- Produces: `read_jsonld(doc: Document) -> list[dict]` - every JSON-LD object found, `@graph` flattened, malformed blocks skipped.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jsonld.py
from pathlib import Path

from sluicer.declared.jsonld import read_jsonld
from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_a_product_block():
    doc = load((FIXTURES / "product_jsonld.html").read_text())

    found = read_jsonld(doc)

    assert {"Product", "BreadcrumbList"} == {item["@type"] for item in found}
    product = next(i for i in found if i["@type"] == "Product")
    assert product["name"] == "Brake pad set"
    assert product["offers"]["price"] == "41.99"


def test_a_malformed_block_is_skipped_not_fatal():
    doc = load(
        '<html><head>'
        '<script type="application/ld+json">{"@type": "Thing"}</script>'
        '<script type="application/ld+json">{not json at all</script>'
        "</head><body></body></html>"
    )

    found = read_jsonld(doc)

    assert found == [{"@type": "Thing"}]
```

Fixture `tests/fixtures/product_jsonld.html`:

```html
<!doctype html>
<html><head><title>Brake pad set</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
 {"@type":"Product","name":"Brake pad set","sku":"ATD-1187",
  "offers":{"@type":"Offer","price":"41.99","priceCurrency":"EUR"}},
 {"@type":"BreadcrumbList","itemListElement":[]}]}
</script>
</head><body><h1>Brake pad set</h1></body></html>
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jsonld.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/declared/__init__.py
"""Readers for the structured data a page already declares."""
```

```python
# src/sluicer/declared/jsonld.py
"""Read the JSON-LD blocks a page carries in its head or body."""

from __future__ import annotations

import json

from sluicer.document import Document

_XPATH = '//script[@type="application/ld+json"]'


def read_jsonld(doc: Document) -> list[dict]:
    """Return every JSON-LD object in the page, with ``@graph`` flattened.

    Blocks that are not valid JSON are skipped: a broken block is a fact about
    the page, not a reason to lose the good ones.
    """
    found: list[dict] = []
    for script in doc.tree.xpath(_XPATH):
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except ValueError:
            continue
        found.extend(_flatten(parsed))
    return found


def _flatten(parsed: object) -> list[dict]:
    if isinstance(parsed, list):
        return [item for entry in parsed for item in _flatten(entry)]
    if isinstance(parsed, dict):
        if "@graph" in parsed:
            return _flatten(parsed["@graph"])
        return [parsed]
    return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_jsonld.py -v`
Expected: PASS, both tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared tests/test_jsonld.py tests/fixtures/product_jsonld.html
git commit -m "feat: read JSON-LD blocks, skipping malformed ones"
```

---

### Task 4: Microdata reader

**Files:**
- Create: `src/sluicer/declared/microdata.py`, `tests/test_microdata.py`, `tests/fixtures/product_microdata.html`

**Interfaces:**
- Consumes: `Document` from Task 2.
- Produces: `read_microdata(doc: Document) -> list[dict]` - one dict per `itemscope`, `@type` carrying the `itemtype` leaf name.

**Known limitation, deferred on purpose:** a nested `itemscope` has its properties absorbed by the outer scope. Real nesting arrives with the structure induction plan, which needs the same tree walk; building it twice would be waste.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_microdata.py
from pathlib import Path

from sluicer.declared.microdata import read_microdata
from sluicer.document import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_reads_itemprops_of_one_itemscope():
    doc = load((FIXTURES / "product_microdata.html").read_text())

    found = read_microdata(doc)

    assert len(found) == 1
    assert found[0]["@type"] == "Product"
    assert found[0]["name"] == "Oil filter"
    assert found[0]["sku"] == "ATD-2290"


def test_content_attribute_wins_over_text():
    doc = load(
        '<div itemscope itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="19.50">'
        "</div>"
    )

    assert read_microdata(doc)[0]["price"] == "19.50"
```

Fixture `tests/fixtures/product_microdata.html`:

```html
<!doctype html>
<html><body>
<div itemscope itemtype="https://schema.org/Product">
  <h1 itemprop="name">Oil filter</h1>
  <span itemprop="sku">ATD-2290</span>
</div>
</body></html>
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_microdata.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared.microdata'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/declared/microdata.py
"""Read schema.org microdata: itemscope, itemtype, itemprop."""

from __future__ import annotations

from sluicer.document import Document

_VALUE_ATTRS = {
    "meta": "content",
    "a": "href",
    "link": "href",
    "img": "src",
    "time": "datetime",
}


def read_microdata(doc: Document) -> list[dict]:
    """Return one dict per itemscope element found in the page."""
    found: list[dict] = []
    for scope in doc.tree.xpath("//*[@itemscope]"):
        item: dict = {}
        itemtype = scope.get("itemtype")
        if itemtype:
            item["@type"] = itemtype.rstrip("/").rsplit("/", 1)[-1]
        for prop in scope.xpath(".//*[@itemprop]"):
            name = prop.get("itemprop")
            if name and name not in item:
                item[name] = _value(prop)
        if len(item) > 1 or (item and "@type" not in item):
            found.append(item)
    return found


def _value(element) -> str:
    attr = _VALUE_ATTRS.get(element.tag)
    if attr and element.get(attr):
        return element.get(attr).strip()
    if element.get("content"):
        return element.get("content").strip()
    return (element.text_content() or "").strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_microdata.py -v`
Expected: PASS, both tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared/microdata.py tests/test_microdata.py tests/fixtures/product_microdata.html
git commit -m "feat: read schema.org microdata"
```

---

### Task 5: OpenGraph reader

**Files:**
- Create: `src/sluicer/declared/opengraph.py`, `tests/test_opengraph.py`

**Interfaces:**
- Consumes: `Document` from Task 2.
- Produces: `read_opengraph(doc: Document) -> dict` - flat mapping, `og:` and `twitter:` prefixes stripped, empty dict when the page declares none.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_opengraph.py
from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load


def test_reads_og_and_twitter_tags():
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="Brake pad set">'
        '<meta property="og:type" content="product">'
        '<meta name="twitter:card" content="summary">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {
        "title": "Brake pad set",
        "type": "product",
        "card": "summary",
    }


def test_a_page_declaring_nothing_returns_an_empty_mapping():
    assert read_opengraph(load("<html><body>hi</body></html>")) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_opengraph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared.opengraph'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/declared/opengraph.py
"""Read OpenGraph and twitter card meta tags."""

from __future__ import annotations

from sluicer.document import Document

_PREFIXES = ("og:", "twitter:")


def read_opengraph(doc: Document) -> dict:
    """Return the og: and twitter: meta tags, prefixes stripped."""
    found: dict = {}
    for meta in doc.tree.xpath("//meta[@property or @name]"):
        key = meta.get("property") or meta.get("name") or ""
        content = (meta.get("content") or "").strip()
        if not content:
            continue
        for prefix in _PREFIXES:
            if key.startswith(prefix):
                found.setdefault(key[len(prefix):], content)
                break
    return found
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_opengraph.py -v`
Expected: PASS, both tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared/opengraph.py tests/test_opengraph.py
git commit -m "feat: read OpenGraph and twitter meta tags"
```

---

### Task 6: Merge with provenance

**Files:**
- Create: `src/sluicer/declared/merge.py`, `tests/test_merge.py`

**Interfaces:**
- Consumes: outputs of Tasks 3, 4, 5.
- Produces: `Field(value: str, source: str)`, `Record(type: str | None, fields: dict[str, Field])`, and `merge(jsonld: list[dict], microdata: list[dict], opengraph: dict) -> list[Record]`.

**Precedence, fixed and documented:** JSON-LD beats microdata beats OpenGraph. Records of the same `@type` are folded into one: microdata fills the gaps a JSON-LD record left, it does not create a duplicate record beside it. The first reader to declare a field owns it, and `Field.source` always says which one did. OpenGraph alone never creates a record on its own; it only fills gaps in an existing one, or forms a single record when nothing else was declared.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_merge.py
from sluicer.declared.merge import merge


def test_jsonld_wins_and_provenance_is_kept():
    records = merge(
        jsonld=[{"@type": "Product", "name": "From JSON-LD"}],
        microdata=[{"@type": "Product", "name": "From microdata", "sku": "X1"}],
        opengraph={"title": "From OpenGraph"},
    )

    assert len(records) == 1
    assert records[0].type == "Product"
    assert records[0].fields["name"].value == "From JSON-LD"
    assert records[0].fields["name"].source == "jsonld"
    assert records[0].fields["sku"].source == "microdata"


def test_opengraph_alone_still_produces_one_record():
    records = merge(jsonld=[], microdata=[], opengraph={"title": "Only OG"})

    assert records[0].fields["title"].source == "opengraph"
    assert records[0].type is None


def test_nothing_declared_gives_no_records():
    assert merge(jsonld=[], microdata=[], opengraph={}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_merge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.declared.merge'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/declared/merge.py
"""Fold the readers' findings into records that remember their source."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Field:
    """One extracted value and the reader that produced it."""

    value: str
    source: str


@dataclass
class Record:
    """A set of fields describing one thing on the page."""

    type: str | None = None
    fields: dict[str, Field] = field(default_factory=dict)


def merge(
    jsonld: list[dict],
    microdata: list[dict],
    opengraph: dict,
) -> list[Record]:
    """Merge reader output. Earlier sources win; every field keeps its source."""
    records: list[Record] = []
    by_type: dict[str | None, Record] = {}

    for item in jsonld:
        record = _record_from(item, "jsonld")
        records.append(record)
        by_type.setdefault(record.type, record)

    for item in microdata:
        record = _record_from(item, "microdata")
        target = by_type.get(record.type)
        if target is None:
            records.append(record)
            by_type.setdefault(record.type, record)
            continue
        for key, value in record.fields.items():
            target.fields.setdefault(key, value)

    if opengraph:
        target = records[0] if records else Record()
        for key, value in opengraph.items():
            target.fields.setdefault(key, Field(value=str(value), source="opengraph"))
        if not records:
            records.append(target)
    return records


def _record_from(item: dict, source: str) -> Record:
    record = Record(type=item.get("@type"))
    for key, value in item.items():
        if key.startswith("@"):
            continue
        if isinstance(value, (dict, list)):
            continue
        record.fields[key] = Field(value=str(value), source=source)
    return record
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_merge.py -v`
Expected: PASS, all three tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/declared/merge.py tests/test_merge.py
git commit -m "feat: merge reader findings keeping provenance per field"
```

---

### Task 7: Public extract() API

**Files:**
- Create: `src/sluicer/api.py`, `tests/test_api.py`
- Modify: `src/sluicer/__init__.py`

**Interfaces:**
- Consumes: `load`, `read_jsonld`, `read_microdata`, `read_opengraph`, `merge`.
- Produces: `Extraction(url: str | None, records: list[Record], sources: list[str])` and `extract(html: str, url: str | None = None) -> Extraction`, re-exported as `sluicer.extract`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api.py
from pathlib import Path

import sluicer

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_reports_records_and_which_readers_fired():
    html = (FIXTURES / "product_jsonld.html").read_text()

    result = sluicer.extract(html, url="https://example.com/p")

    assert result.url == "https://example.com/p"
    assert result.sources == ["jsonld"]
    assert any(r.fields.get("sku") and r.fields["sku"].value == "ATD-1187" for r in result.records)


def test_a_page_declaring_nothing_extracts_nothing_and_says_so():
    result = sluicer.extract((FIXTURES / "plain.html").read_text())

    assert result.records == []
    assert result.sources == []


def test_extraction_is_deterministic():
    html = (FIXTURES / "product_jsonld.html").read_text()

    first = sluicer.extract(html)
    second = sluicer.extract(html)

    assert first == second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with `AttributeError: module 'sluicer' has no attribute 'extract'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/api.py
"""The one call most people will make."""

from __future__ import annotations

from dataclasses import dataclass, field

from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.merge import Record, merge
from sluicer.declared.microdata import read_microdata
from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load


@dataclass
class Extraction:
    """What Sluicer found in one page, and where it came from."""

    url: str | None = None
    records: list[Record] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def extract(html: str, url: str | None = None) -> Extraction:
    """Read every kind of declared data in ``html`` and merge it."""
    doc = load(html, url=url)
    jsonld = read_jsonld(doc)
    microdata = read_microdata(doc)
    opengraph = read_opengraph(doc)

    sources = [
        name
        for name, found in (
            ("jsonld", jsonld),
            ("microdata", microdata),
            ("opengraph", opengraph),
        )
        if found
    ]
    return Extraction(
        url=url,
        records=merge(jsonld=jsonld, microdata=microdata, opengraph=opengraph),
        sources=sources,
    )
```

```python
# src/sluicer/__init__.py
"""Deterministic extraction of the data a web page already declares."""

from sluicer.api import Extraction, extract

__all__ = ["Extraction", "extract", "__version__"]
__version__ = "0.0.1"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/api.py src/sluicer/__init__.py tests/test_api.py
git commit -m "feat: public extract() returning records and their sources"
```

---

### Task 8: CLI

**Files:**
- Create: `src/sluicer/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `extract` from Task 7.
- Produces: console script `sluicer extract <path>` printing JSON to stdout; exit code 1 and a message on stderr when nothing was declared.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json
from pathlib import Path

from click.testing import CliRunner

from sluicer.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_prints_json_records():
    result = CliRunner().invoke(main, ["extract", str(FIXTURES / "product_jsonld.html")])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["sources"] == ["jsonld"]
    assert payload["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_page_with_nothing_declared_exits_one():
    result = CliRunner().invoke(main, ["extract", str(FIXTURES / "plain.html")])

    assert result.exit_code == 1
    assert "declares no structured data" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/cli.py
"""Command line front door."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from sluicer.api import extract as extract_html


@click.group()
@click.version_option(package_name="sluicer")
def main() -> None:
    """Turn a web page into structured data with no model in the loop."""


@main.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def extract(source: Path) -> None:
    """Read the declared structured data of a saved HTML file."""
    result = extract_html(source.read_text(errors="replace"), url=str(source))
    if not result.records:
        click.echo("This page declares no structured data.")
        raise SystemExit(1)
    click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/cli.py tests/test_cli.py
git commit -m "feat: sluicer extract command"
```

---

## Follow-up plans (not in this one)

Each is its own plan, each ships working software on its own:

1. **Fetch ladder** - `ladder`, plus `sluicer extract <url>` over the network.
2. **Structure induction** - `induce`, repeating-subtree detection.
3. **Trust scoring** - `trust`, cross-page template comparison.
4. **Schema healing** - `heal`, diff between runs.
5. **The scoreboard** - `bench` over WCXB, WebMainBench, ChatNoir.
6. **MCP server and Claude Code plugin** - the remaining two front doors.
