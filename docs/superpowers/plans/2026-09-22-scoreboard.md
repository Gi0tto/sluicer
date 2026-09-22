# Scoreboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a ruler. Score Sluicer and the alternatives on a public annotated corpus, on every run, and publish the losses with the wins.

**Architecture:** A `scoreboard/` directory outside the package: a corpus loader that materialises WCXB into a git-ignored cache, per-field metrics, a runner per tool, and one committed results table. Nothing here ships in the wheel.

**Tech Stack:** Python 3.10+, the installed `sluicer`, and the competitors in their own virtual environments so their dependencies never touch ours.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`

## Why this exists

Every project in this field claims to extract well. Across 295 live repositories surveyed on 2026-09-22, **one** published a benchmark, and it measures OCR. "The best extractor" is an unfalsifiable claim across an entire field, including in this repository, which is why `ROADMAP.md` says Sluicer makes no comparative claim until this exists.

## The corpus, opened and counted before planning

**WCXB** — `Murrough-Foley/web-content-extraction-benchmark`, **CC-BY-4.0**.
GitHub's API reports `NOASSERTION` because the LICENSE file is a plain-text
summary rather than the canonical text; `metadata.json` states
`"license": "CC-BY-4.0"` and the LICENSE text is the CC-BY-4.0 grant. 153 MB,
cloned and inspected on 2026-09-22 rather than described from its README.

**What is where, measured:**

- `test/ground-truth/*.json` — **511 files**. Every one carries
  `ground_truth` as a **dict** (never a string), and every one has all six keys:
  `title`, `author`, `publish_date`, `main_content`, `with`, `without`.
- `test/html/*.html` — 511 files. **The corpus runs entirely offline.**
- `page_type` is **not** in the ground-truth files — 487 of 511 leave it blank.
  It lives in `metadata.json`, whose `files` map covers all 511 test ids.
- Test-split page types: article 257, service 59, forum 51, documentation 42,
  listing 40, collection 34, product 28. **359 of the 511 are the four types
  this scoreboard scores.**

**The finding that shapes the metric:** the labels are deliberately sparse.
Across the 511 test pages, `title` is missing on 2 and `main_content` on 6 —
but **`author` is missing on 323 (63%) and `publish_date` on 246 (48%)**.

That is not a defect in the corpus. It is the corpus saying *this page has no
author*, and it makes possible the measurement this field never publishes:
**how often does a tool invent a value that is not there?** A deterministic
reader should score near-perfectly on absence, because it only reports what the
page declared. A heuristic guesser should not. Whether that is true of Sluicer
is exactly what we do not yet know, and printing it is the point.

## The corpus limit that must be printed beside every number

**WCXB has every `<script>` tag removed.** Checked across all 359 pages of the
four scored types on 2026-09-22: zero `<script>`, zero `<style>`, zero
`<noscript>`, zero `<iframe>`, and zero occurrences of `ld+json` anywhere.

So **JSON-LD cannot be measured on this corpus at all**, and JSON-LD is
Sluicer's first reader and the modern web's commonest way to declare anything.
Every number from WCXB is therefore a score for a reader with its main
vocabulary removed, and a table that does not say so is lying by omission.

The second corpus exists for exactly this. `scrapinghub/article-extraction-benchmark`
(MIT, 181 pages) is intact: all 181 keep their scripts, **128 carry JSON-LD**,
174 OpenGraph, 62 microdata. Its ground truth is only `articleBody`, so it
cannot score title, author or date — but it can score `main_content`, which is
its purpose, and it is the only place a JSON-LD claim can be checked.

**Neither corpus alone is sufficient, and the report must name which corpus
produced each number, on the same line as the number.**

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL. The corpus is CC-BY-4.0 and **must be attributed wherever a number from it is published**.
- No LLM call anywhere. No paid API.
- The corpus is **never committed**. It is fetched into `scoreboard/.cache/` (git-ignored) by a loader that verifies what it downloaded.
- The package's own test suite still touches no network. Scoreboard code lives outside `src/` and outside `tests/`, and its own tests use three hand-written pages.
- English everywhere including commit messages.
- `ruff` and `mypy --strict` stay green on `scoreboard/` too.

## The honesty rules, which are requirements and not preferences

1. **`main_content` is not our number.** Sluicer's markdown extra calls `trafilatura`. Scoring `main_content` and printing it beside our name would claim a dependency's work. That row is labelled `sluicer[markdown] (trafilatura)` in every table, or it is not printed.
2. **`title`, `author`, `publish_date` are our number.** They come from declared data our own readers parse. This is the comparison nobody has published, and it is the one that matters to us.
3. **Losses are published.** Every table prints every tool's score on every field, including the fields where Sluicer is last.
4. **The corpus's own metric is used**, not one invented here. WCXB ships `evaluate.py`; its scoring is the scoring.
5. **A page we return nothing for counts as a miss**, never as an abstention.

---

## File Structure

| file | responsibility |
| --- | --- |
| `scoreboard/corpus.py` | fetch WCXB into `.cache/`, verify it, iterate `(html, ground_truth, page_type)` |
| `scoreboard/metrics.py` | per-field scoring, delegating to WCXB's own comparison where it defines one |
| `scoreboard/runners.py` | one function per tool under test, each returning the same record shape |
| `scoreboard/report.py` | the markdown table, and the loss column |
| `scoreboard/run.py` | the entry point: `python -m scoreboard.run --split test` |
| `results/latest.md` | committed output, regenerated and committed on every run |
| `scoreboard/tests/` | three hand-written pages that exercise the metrics and the report |

---

### Task 1: The corpus loader

**Files:**
- Create: `scoreboard/__init__.py`, `scoreboard/corpus.py`, `scoreboard/tests/test_corpus.py`, `scoreboard/.gitignore`

**Interfaces:**
- Produces: `Page(file_id: str, url: str, html: bytes, truth: dict, page_type: str, split: str)` and `load(split: str = "test") -> Iterator[Page]`.

**What to build:** a loader that downloads the WCXB tarball once into `scoreboard/.cache/wcxb/`, refuses to proceed if `metadata.json` does not say `"license": "CC-BY-4.0"`, and yields one `Page` per ground-truth file with its HTML read as **bytes** (the page's own encoding declaration must win — `sluicer.load` already relies on that, and decoding here would corrupt exactly the non-English pages that matter).

- [ ] **Step 1: Write the failing test**

```python
# scoreboard/tests/test_corpus.py
from scoreboard.corpus import Page, licence_is_open


def test_a_corpus_whose_licence_changed_is_refused():
    """The licence is a precondition, not a footnote: it is checked in code."""
    assert licence_is_open({"license": "CC-BY-4.0"}) is True
    assert licence_is_open({"license": "CC-BY-NC-4.0"}) is False
    assert licence_is_open({}) is False


def test_a_page_keeps_its_html_as_bytes():
    """Decoding here would lose the page's own encoding declaration."""
    page = Page(file_id="1", url="u", html=b"<html>caf\xe9</html>",
                truth={"title": "t"}, page_type="article", split="test")

    assert isinstance(page.html, bytes)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest scoreboard/tests/test_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scoreboard'`.

- [ ] **Step 3: Write the loader**

`licence_is_open(metadata)` returns True only for `"CC-BY-4.0"`. `load(split)`
reads `.cache/wcxb/metadata.json`, calls `licence_is_open` and raises
`LicenceChanged` when it is False, then yields a `Page` per entry whose `split`
matches, reading `<split>/html/<file_id>.html` as **bytes** and
`<split>/ground-truth/<file_id>.json` as JSON.

Two things checked by opening the files, so do not code around cases that do not
exist and do not assume the ones that do:

- `ground_truth` is **always a dict**, in all 511 test files. There is no
  string case to parse.
- `page_type` must be read from `metadata.json["files"][file_id]["page_type"]`,
  **not** from the ground-truth file, which leaves it blank on 487 of 511. A
  `file_id` absent from `metadata.json` raises rather than defaulting to a type,
  because a page silently typed `article` would be scored against the wrong
  expectation.

- [ ] **Step 4: Run it and watch it pass**

- [ ] **Step 5: Fetch the corpus for real and print what arrived**

Run: `uv run python -m scoreboard.corpus --fetch` then
`uv run python -c "from scoreboard.corpus import load; import collections; c=collections.Counter(p.page_type for p in load('test')); print(sum(c.values()), c)"`
Expected: 511 pages, and the seven page types.

- [ ] **Step 6: Commit**

```bash
git add scoreboard/ && git commit -m "feat(scoreboard): load WCXB, and refuse it if its licence changed"
```

---

### Task 2: The metrics

**Files:**
- Create: `scoreboard/metrics.py`, `scoreboard/tests/test_metrics.py`

**Interfaces:**
- Produces: `score_field(predicted: str | None, truth: str | None) -> float` and `score_page(predicted: dict, truth: dict, fields: list[str]) -> dict[str, float]`.

**What to build:** exact match after normalisation for `title` and `author`;
date equality after parsing for `publish_date`; word-level F1 for
`main_content`, taken from WCXB's own `evaluate.py` rather than rewritten.

**The hard part is absence, and it is the part worth building.** 63% of test
pages have no `author` and 48% have no `publish_date`. So a field has four
outcomes, not two, and they must not be averaged into one number:

| ground truth | prediction | outcome | why it matters |
| --- | --- | --- | --- |
| present | matches | `hit` | the tool found what was there |
| present | wrong or missing | `miss` | the tool failed to find it |
| absent | absent | `correct_silence` | the tool did not invent |
| absent | present | **`invention`** | the tool reported something the page never said |

`score_page` returns these four counts per field, not a float. The mean is
computed once, at report time, as `hit / (hit + miss)` — **recall on the pages
that have the field** — and `invention` is printed as its own column, never
folded in. A tool that invents an author on every unlabelled page would
otherwise be hidden behind a good recall number.

`invention` is the column this scoreboard exists to print. Sluicer only reports
what a page declared, so it should be near zero; if it is not, that is a defect
in Sluicer and the table says so before anyone else finds it.

- [ ] **Step 1: Write the failing test**

```python
# scoreboard/tests/test_metrics.py
from scoreboard.metrics import score_field, score_page


def test_silence_where_there_was_something_is_a_miss():
    """A tool that stays quiet on hard pages must not score better for it."""
    assert score_field(None, "The Best Cheap Laptops") == "miss"


def test_a_title_matches_past_whitespace_and_case():
    assert score_field("  the BEST cheap laptops ", "The Best Cheap Laptops") == "hit"


def test_silence_where_there_was_nothing_is_not_a_miss():
    """63% of these pages have no author. Reporting none is the right answer."""
    assert score_field(None, None) == "correct_silence"


def test_naming_an_author_the_page_never_had_is_an_invention():
    """The column this scoreboard exists to print."""
    assert score_field("A. Nonymous", None) == "invention"


def test_a_page_is_scored_field_by_field():
    truth = {"title": "A", "author": None, "publish_date": "2018-07-10"}
    got = score_page({"title": "A", "author": "X"}, truth,
                     ["title", "author", "publish_date"])

    assert got == {"title": "hit", "author": "invention", "publish_date": "miss"}
```

- [ ] **Step 2: Run it and watch it fail**
- [ ] **Step 3: Write the metrics**
- [ ] **Step 4: Run it and watch it pass**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(scoreboard): score a field, and count silence as a miss"
```

---

### Task 3: The runners and the table

**Files:**
- Create: `scoreboard/runners.py`, `scoreboard/report.py`, `scoreboard/run.py`, `scoreboard/tests/test_report.py`

**Interfaces:**
- Produces: `RUNNERS: dict[str, Callable[[bytes, str], dict]]` and `render(rows) -> str`.

**Who is measured, and why each one:**

| runner | what it is | which fields |
| --- | --- | --- |
| `sluicer` | declared readers only, base install | title, author, publish_date |
| `sluicer+induce` | the same with `induce=True` | title, author, publish_date |
| `extruct` | the incumbent: 540,765 installs a month, last release 683 days ago | title, author, publish_date |
| `trafilatura` | the article extractor | all four |
| `readability-lxml` | the classic | title, main_content |
| `sluicer[markdown] (trafilatura)` | our markdown extra, labelled as what it is | main_content |

`extruct` is the row that matters: it is the library doing our job, and no one has published this comparison. `trafilatura` will win `main_content` and should — printing that is the point.

Each competitor runs in its own venv under `scoreboard/.venvs/`, created by the runner, so their dependency trees never enter ours.

- [ ] **Step 1: Write the failing test for the report**

```python
# scoreboard/tests/test_report.py
from scoreboard.report import render


def test_the_table_prints_the_field_we_lose():
    rows = [
        {"tool": "sluicer", "title": 0.91, "author": 0.62, "main_content": None},
        {"tool": "trafilatura", "title": 0.88, "author": 0.71, "main_content": 0.94},
    ]

    table = render(rows)

    assert "0.62" in table and "0.71" in table, "a lost field was dropped"
    assert "trafilatura" in table


def test_a_field_a_tool_does_not_attempt_is_blank_not_zero():
    """Not attempting is different from attempting and failing."""
    table = render([{"tool": "sluicer", "title": 0.91, "main_content": None}])

    assert "0.00" not in table


def test_inventions_get_their_own_column_and_are_never_folded_in():
    """A tool inventing an author on every blank page must not hide behind recall."""
    rows = [{"tool": "guesser", "author": 0.95, "author_invented": 300}]

    table = render(rows)

    assert "300" in table, "the invention count was dropped from the table"
```

- [ ] **Step 2: Run it and watch it fail**
- [ ] **Step 3: Write the runners, the report, and the glue**

`runners.py` holds one function per row of the table above, each with the same
signature and the same return shape:

```python
# scoreboard/runners.py
def run_sluicer(html: bytes, url: str) -> dict[str, str | None]:
    """Declared readers only. Returns the three fields, or None where absent."""
    from sluicer import extract
    fields: dict[str, Field] = {}
    for record in extract(html, url=url).records:
        for name, field in record.fields.items():
            fields.setdefault(name, field)
    return {
        "title": _first(fields, "headline", "name", "title"),
        "author": _first(fields, "author", "creator"),
        "publish_date": _first(fields, "datePublished", "date", "publish_date"),
    }
```

`_first(fields, *names)` returns the value of the first name present, or None.
The alias lists are deliberately short and written here rather than inferred:
a scoreboard whose mapping is clever is a scoreboard measuring the mapping.

`run.py` is the glue, and it is the whole file:

```python
# scoreboard/run.py
import argparse, collections
from scoreboard.corpus import load
from scoreboard.metrics import score_page
from scoreboard.report import render
from scoreboard.runners import RUNNERS, FIELDS_ATTEMPTED

SCORED_TYPES = {"article", "listing", "collection", "product"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", default="results/latest.md")
    args = parser.parse_args()

    # (tool, field) -> Counter of hit / miss / correct_silence / invention
    tally: dict[tuple[str, str], collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    pages = [p for p in load(args.split) if p.page_type in SCORED_TYPES]
    for page in pages:
        for tool, run in RUNNERS.items():
            got = run(page.html, page.url)
            for field, outcome in score_page(got, page.truth, FIELDS_ATTEMPTED[tool]).items():
                tally[(tool, field)][outcome] += 1

    rows = []
    for tool in RUNNERS:
        row: dict[str, object] = {"tool": tool}
        for field in ("title", "author", "publish_date", "main_content"):
            counts = tally.get((tool, field))
            if not counts:
                row[field] = None          # the tool never attempts this field
                continue
            found = counts["hit"] + counts["miss"]
            row[field] = counts["hit"] / found if found else None
            row[field + "_invented"] = counts["invention"]
        rows.append(row)

    with open(args.out, "w") as handle:
        handle.write(render(rows, pages=len(pages), split=args.split))


if __name__ == "__main__":
    main()
```

`FIELDS_ATTEMPTED` is a dict beside `RUNNERS` naming which fields each tool
tries, so a field a tool never attempts stays `None` in the table instead of
becoming a zero it did not earn.
- [ ] **Step 4: Run it and watch it pass**
- [ ] **Step 5: Commit**

```bash
git commit -am "feat(scoreboard): run every tool, print every field, hide no loss"
```

---

### Task 4: Run it for real, and commit the numbers

**Files:**
- Create: `results/latest.md`
- Modify: `README.md`, `ROADMAP.md`, `.github/workflows/scoreboard.yml`

- [ ] **Step 1: Run the whole thing on the test split**

Run: `uv run python -m scoreboard.run --split test --out results/latest.md`

- [ ] **Step 2: Read the output before publishing it**

Look at the rows where Sluicer loses and at any field where it scores suspiciously high. A score of 1.00 on a field is a bug until proven otherwise: check three pages by hand against their ground truth, and write what you checked into the report.

- [ ] **Step 3: Write the numbers into the README, with the losses**

The README may state a comparison **only** now, and only as the table states it. Attribute WCXB (CC-BY-4.0, Murrough Foley) at the point of use.

- [ ] **Step 4: Move the scoreboard from Next to Shipped in `ROADMAP.md`**, and delete the sentence saying this repository makes no comparative claim, because it now makes one and backs it.

- [ ] **Step 5: A weekly workflow that re-runs it**

A scoreboard that is run once is a screenshot. `scoreboard.yml` runs weekly and on demand, and fails the run if any score moves by more than 0.05 without `results/latest.md` changing in the same commit.

- [ ] **Step 6: Commit**

---

## Out of scope

Scoring `forum`, `documentation` and `service` pages, which have no declared-data expectation to score against. A leaderboard site. Any claim about speed — that is a different measurement and mixing it in here would let a slow, accurate tool look bad for the wrong reason.
