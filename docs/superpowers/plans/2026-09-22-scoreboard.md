# Scoreboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a ruler. Score Sluicer, and the free tools it is compared to, against a third-party annotated benchmark, on every run, and commit the result so anyone can dispute it.

**Architecture:** A `bench` package outside the installed library. It downloads a benchmark into a git-ignored cache, runs each competitor over the same pages, scores every prediction against the same gold labels with the same metric, and writes one versioned results file. Nothing in it is imported by `sluicer`, and none of it runs inside the unit suite.

**Tech Stack:** Python 3.10+, `lxml`, plus the competitors themselves. The benchmark is WCXB, CC-BY-4.0.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`, section 4.2.6.

## Why this exists, measured

Of 295 live repositories in this field, exactly one publishes a benchmark, and it measures OCR. So "the best extractor" is currently an unfalsifiable claim across an entire discipline, including in this repository, which is why its README refuses to make one.

WCXB is the ruler that fits: 2,008 hand-reviewed pages, 1,613 domains, seven page types, CC-BY-4.0, and it exists precisely because older benchmarks measured only news articles. Its own README states the gap this project was built around: "On articles, top extraction systems converge within 2-3 F1 points (0.91-0.93). But on forums, products, and collections, the gap widens to 20-30 F1 points."

Its gold labels carry `title`, `author`, `publish_date` and `main_content`. The first three are exactly what Sluicer produces from declared data, so this scores our real work against somebody else's answers. We are not the referee.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL, and the benchmark data is never committed.
- No LLM call anywhere. No paid API.
- **Deterministic**: the same data and the same code give the same table.
- English only everywhere including commit messages.
- **The unit suite never runs the benchmark and never touches the network.** `bench/` has its own tests, which use a tiny fixture corpus committed to the repository, not the real download.
- `ruff` and `mypy --strict` stay green. `bench/` is included in both.
- Every number published carries the commit it was produced at and the benchmark version.

---

## File Structure

| file | responsibility |
| --- | --- |
| `bench/__init__.py` | nothing but a docstring: this is not part of the library |
| `bench/corpus.py` | fetching and caching WCXB, and loading its pages and labels |
| `bench/score.py` | the metrics: word F1 for text, exact-after-normalising for fields |
| `bench/runners.py` | one adapter per tool under test, each returning the same shape |
| `bench/run.py` | the command: run everything, write the table |
| `bench/fixtures/` | four hand-made pages and labels, for the tests |
| `results/latest.md` | the table, committed, regenerated on every run |

---

### Task 1: The metrics

**Files:**
- Create: `bench/__init__.py`, `bench/score.py`, `tests/test_bench_score.py`

**Interfaces:**
- Produces: `word_f1(predicted: str, reference: str) -> float` and `field_match(predicted: str | None, reference: str | None) -> bool`.

**Why these two:** WCXB scores main content by word-level F1, and we use its metric rather than inventing one, because a ruler nobody else uses is not a ruler. Fields are different: a title is right or wrong, so it is compared after normalising whitespace, case and surrounding punctuation, and a missing prediction against a present label is simply wrong.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bench_score.py
from bench.score import field_match, word_f1


def test_identical_text_scores_one():
    assert word_f1("the cat sat", "the cat sat") == 1.0


def test_nothing_in_common_scores_zero():
    assert word_f1("aaa bbb", "ccc ddd") == 0.0


def test_half_the_words_scores_between():
    score = word_f1("the cat sat down", "the cat stood up")

    assert 0.0 < score < 1.0


def test_an_empty_prediction_scores_zero_rather_than_raising():
    assert word_f1("", "the cat sat") == 0.0
    assert word_f1("the cat sat", "") == 0.0


def test_repeated_words_are_counted_not_collapsed():
    assert word_f1("cat cat cat", "cat") < 1.0


def test_a_field_matches_despite_whitespace_and_case():
    assert field_match("  Brake Pad  Set ", "brake pad set") is True


def test_a_field_matches_despite_surrounding_punctuation():
    assert field_match('"Frankenstein"', "Frankenstein") is True


def test_a_missing_prediction_does_not_match_a_present_label():
    assert field_match(None, "Frankenstein") is False


def test_two_absences_agree():
    assert field_match(None, None) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_score.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench'`

- [ ] **Step 3: Write minimal implementation**

```python
# bench/__init__.py
"""The scoreboard. Not part of the library, never imported by it."""
```

```python
# bench/score.py
"""How a prediction is compared to an answer somebody else wrote.

Main content is scored with word-level F1, which is the metric the benchmark
itself publishes. Using somebody else's ruler is the point: a measure invented
here would be a measure only this project believes.

A field is not a bag of words. A title is right or wrong, so it is compared
after normalising the things that never carry meaning: surrounding space, case,
and the quotes and dashes that decorate one rendering of a title and not
another.
"""

from __future__ import annotations

from collections import Counter

_TRIM = " \t\r\n\"'“”‘’.,;:!?-–—"


def word_f1(predicted: str, reference: str) -> float:
    """Return the word-level F1 of ``predicted`` against ``reference``."""
    got = Counter(predicted.split())
    want = Counter(reference.split())
    if not got or not want:
        return 0.0
    shared = sum((got & want).values())
    if not shared:
        return 0.0
    precision = shared / sum(got.values())
    recall = shared / sum(want.values())
    return 2 * precision * recall / (precision + recall)


def field_match(predicted: str | None, reference: str | None) -> bool:
    """Say whether a single-value field is right, ignoring what never means anything."""
    if predicted is None or reference is None:
        return predicted is None and reference is None
    return _normalise(predicted) == _normalise(reference)


def _normalise(value: str) -> str:
    return " ".join(value.split()).strip(_TRIM).casefold()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bench_score.py -v`
Expected: PASS, all nine

- [ ] **Step 5: Commit**

```bash
git add bench tests/test_bench_score.py
git commit -m "feat: score with the benchmark's own ruler, not one of ours"
```

---

### Task 2: The corpus

**Files:**
- Create: `bench/corpus.py`, `bench/fixtures/` (four pages and four labels), `tests/test_bench_corpus.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `Page(file_id, url, page_type, html, title, author, publish_date, main_content)` and `load(directory: Path) -> list[Page]`, plus `download(cache: Path) -> Path` which fetches WCXB if it is not already there.

**The split of responsibility that keeps the tests offline:** `load` reads a directory and knows nothing about the network. `download` is the only thing that fetches, it is never called by a test, and the tests read `bench/fixtures/` instead.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bench_corpus.py
from pathlib import Path

from bench.corpus import load

FIXTURES = Path(__file__).parent.parent / "bench" / "fixtures"


def test_the_fixture_corpus_loads():
    pages = load(FIXTURES)

    assert len(pages) == 4


def test_a_page_carries_its_html_and_its_answers():
    page = next(p for p in load(FIXTURES) if p.file_id == "0001")

    assert "<html" in page.html.lower()
    assert page.title
    assert page.main_content


def test_pages_come_back_in_a_stable_order():
    first = [p.file_id for p in load(FIXTURES)]
    second = [p.file_id for p in load(FIXTURES)]

    assert first == second == sorted(first)


def test_a_page_with_no_author_says_none_rather_than_empty_string():
    page = next(p for p in load(FIXTURES) if p.file_id == "0004")

    assert page.author is None


def test_a_directory_with_nothing_in_it_loads_nothing(tmp_path):
    assert load(tmp_path) == []
```

Create four fixture pairs under `bench/fixtures/html/000N.html` and `bench/fixtures/ground-truth/000N.json`, matching WCXB's real schema: `url`, `file_id`, `_internal.page_type.primary`, and `ground_truth` with `title`, `author`, `publish_date`, `main_content`. Make `0001` an article with JSON-LD declaring its title and author, `0002` a product page with microdata, `0003` a listing page that declares nothing, and `0004` an article with no author at all. Keep each under thirty lines: they are for testing the harness, not the extractors.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.corpus'`

- [ ] **Step 3: Write minimal implementation**

`Page` is a frozen dataclass. `load` globs `ground-truth/*.json`, sorts by file id, reads the matching HTML, and returns `None` rather than `""` for a field the labels leave empty. `download` clones WCXB's dev split into the cache directory with `git clone --depth 1` if it is absent, prints what it did, and returns the path; it is documented as the only function here that touches the network. Add the cache directory to `.gitignore`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add bench/corpus.py bench/fixtures tests/test_bench_corpus.py .gitignore
git commit -m "feat: load a benchmark corpus, and download it only when asked"
```

---

### Task 3: The competitors, and the table

**Files:**
- Create: `bench/runners.py`, `bench/run.py`, `tests/test_bench_runners.py`
- Create: `results/latest.md` (generated)

**Interfaces:**
- Produces: `Prediction(title, author, publish_date, main_content)`, `RUNNERS: dict[str, Callable[[str], Prediction]]`, `score_all(pages, runners) -> dict[str, Scores]`, and `main()` writing the table.

**Who is on the table, and why:** Sluicer's declared extraction; Sluicer's markdown path; `trafilatura`; and `readability-lxml`. All free, all permissive, all installable. A tool that needs a key is not comparable on equal terms and is left off with that reason printed under the table.

**The rule this whole plan exists to honour:** the losses are published. If Sluicer is beaten on a page type, the table says so, with the number.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bench_runners.py
from pathlib import Path

from bench.corpus import load
from bench.runners import Prediction, score_all

FIXTURES = Path(__file__).parent.parent / "bench" / "fixtures"


def perfect(page):
    """A runner that knows every answer, to prove the scoring works."""
    return Prediction(
        title=page.title,
        author=page.author,
        publish_date=page.publish_date,
        main_content=page.main_content,
    )


def useless(page):
    return Prediction(title=None, author=None, publish_date=None, main_content="")


def test_a_runner_that_knows_everything_scores_perfectly():
    pages = load(FIXTURES)

    scores = score_all(pages, {"oracle": lambda html, page=None: perfect(page)})

    assert scores["oracle"].title_accuracy == 1.0
    assert scores["oracle"].content_f1 == 1.0


def test_a_runner_that_knows_nothing_scores_zero():
    pages = load(FIXTURES)

    scores = score_all(pages, {"nothing": lambda html, page=None: useless(page)})

    assert scores["nothing"].content_f1 == 0.0


def test_every_runner_sees_the_same_pages():
    pages = load(FIXTURES)
    seen: dict[str, int] = {}

    def counting(name):
        def run(html, page=None):
            seen[name] = seen.get(name, 0) + 1
            return useless(page)

        return run

    score_all(pages, {"a": counting("a"), "b": counting("b")})

    assert seen == {"a": len(pages), "b": len(pages)}


def test_a_runner_that_raises_scores_zero_rather_than_stopping_the_table():
    pages = load(FIXTURES)

    def broken(html, page=None):
        raise RuntimeError("this tool fell over")

    scores = score_all(pages, {"broken": broken})

    assert scores["broken"].content_f1 == 0.0
    assert scores["broken"].failures == len(pages)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bench_runners.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.runners'`

- [ ] **Step 3: Write minimal implementation**

`Scores` is a frozen dataclass carrying `title_accuracy`, `author_accuracy`, `date_accuracy`, `content_f1`, `failures`, and the per-page-type breakdown. `score_all` runs each runner over every page, catches any exception into a failure counted as zero rather than stopping the table, and averages. The real runners import their tool lazily so a missing competitor is skipped with a printed note rather than a crash. `main()` writes `results/latest.md` with the benchmark version, the commit, the date, the overall table and the table by page type, and prints the same to standard output.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add bench/runners.py bench/run.py tests/test_bench_runners.py
git commit -m "feat: run every tool over the same pages and publish the table"
```

---

### Task 4: Run it for real, and commit the numbers

**Files:**
- Create: `results/latest.md` with real numbers
- Modify: `README.md`, `.github/workflows/ci.yml`

- [ ] **Step 1: Download the benchmark and run the scoreboard**

Run: `uv run --with trafilatura --with readability-lxml python -m bench.run`
Record the real output. This is the first time this project has had a number.

- [ ] **Step 2: Commit the results file**

The numbers go in the repository, whatever they say.

- [ ] **Step 3: Put the headline in the README**

Replace the line that says this README makes no claim about being better than anything with the number, whichever way it falls, and a link to the table.

- [ ] **Step 4: Add a scheduled CI job**

Weekly, not on every push: the download is large. It regenerates the table and opens a pull request if the numbers moved.

- [ ] **Step 5: Commit**

```bash
git add results README.md .github/workflows/ci.yml
git commit -m "The first number this project has ever published"
```

---

## Out of scope

Scoring tools that need an API key, a benchmark of our own making, and per-domain drill-downs. The first is not comparable, the second makes us the referee, and the third is worth doing once the table exists.
