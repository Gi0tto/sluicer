# Fetch Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Sluicer read a live URL, starting at the cheapest rung and climbing to a browser only when a measurement says it must, with every climb and its reason reported back to the caller.

**Architecture:** The ladder is a pure orchestrator over injectable rungs. A rung is any callable `(url) -> Fetched`. The decision to climb is a pure function of what came back, so the whole ladder is testable without a network. The real rungs are thin adapters over `scrapling`, imported lazily behind an optional extra, so the base install stays `lxml` + `click`.

**Tech Stack:** Python 3.10+, `lxml`, `click`, `pytest`; `scrapling>=0.4` only under the `fetch` extra.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`, section 4.2.1.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL code.
- No LLM call anywhere in the path, not even as a fallback.
- No paid API, and no feature that requires somebody's key to work.
- Deterministic: the same input always produces the same output.
- English only: code, comments, docstrings, test names, commit messages, docs.
- **Unit tests never touch the network.** Not once, not for a smoke test. Rungs are injected in tests.
- Every public function is typed, and annotations must be honest: if you know the type, write it.
- `scrapling` is an optional dependency. `import sluicer` must keep working with it absent.

---

## File Structure

| file | responsibility |
| --- | --- |
| `src/sluicer/fetch/__init__.py` | the package's fetch surface |
| `src/sluicer/fetch/result.py` | `Fetched`, `Climb` |
| `src/sluicer/fetch/rules.py` | `why_climb()`, the measurement and its named thresholds |
| `src/sluicer/fetch/ladder.py` | `fetch()`, the orchestration over rungs |
| `src/sluicer/fetch/scrapling_rungs.py` | the three real rungs, lazily imported |
| `src/sluicer/document.py` | extended: `load()` accepts bytes |
| `src/sluicer/cli.py` | extended: a URL argument |

---

### Task 1: The fetch result types

**Files:**
- Create: `src/sluicer/fetch/__init__.py`, `src/sluicer/fetch/result.py`, `tests/test_fetch_result.py`

**Interfaces:**
- Produces: `Climb(from_rung: str, to_rung: str, reason: str)` and `Fetched(url: str, html: str, status: int, rung: str, climbs: list[Climb])`, both dataclasses compared by value.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_result.py
from sluicer.fetch.result import Climb, Fetched


def test_a_fetch_that_never_climbed_says_so():
    result = Fetched(url="https://example.com", html="<html></html>", status=200, rung="http")

    assert result.climbs == []
    assert result.rung == "http"


def test_climbs_are_compared_by_value():
    one = Climb(from_rung="http", to_rung="browser", reason="the server refused: status 403")
    same = Climb(from_rung="http", to_rung="browser", reason="the server refused: status 403")

    assert one == same
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetch_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.fetch'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/fetch/__init__.py
"""Getting the page, at the lowest cost that works."""
```

```python
# src/sluicer/fetch/result.py
"""What a fetch returns, including how much it had to spend."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Climb:
    """One step up the ladder, and the measurement that forced it."""

    from_rung: str
    to_rung: str
    reason: str


@dataclass
class Fetched:
    """A page, the rung that got it, and every climb along the way."""

    url: str
    html: str
    status: int
    rung: str
    climbs: list[Climb] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fetch_result.py -v`
Expected: PASS, both tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch tests/test_fetch_result.py
git commit -m "feat: the fetch result carries every climb and its reason"
```

---

### Task 2: The climb rules

**Files:**
- Create: `src/sluicer/fetch/rules.py`, `tests/test_fetch_rules.py`

**Interfaces:**
- Produces: `why_climb(status: int, html: str, found_records: bool) -> str | None`, returning the reason to climb or None to stay. Also the named thresholds `TEXT_FLOOR` and `MARKUP_CEILING`.

**The rule, stated once:** climb when the response is a refusal in disguise, when the body is skeletal against the weight of the markup, or when nothing was declared and there is almost no text to fall back on. Never climb on a server error: a browser cannot fix a 500.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_rules.py
from sluicer.fetch.rules import why_climb

FULL_PAGE = "<html><body>" + ("Real sentences of real content. " * 40) + "</body></html>"


def test_a_good_page_does_not_climb():
    assert why_climb(200, FULL_PAGE, found_records=True) is None


def test_a_refusal_climbs_and_names_the_status():
    reason = why_climb(403, "<html><body>Forbidden</body></html>", found_records=False)

    assert reason is not None
    assert "403" in reason


def test_a_server_error_does_not_climb():
    assert why_climb(500, "<html><body>oops</body></html>", found_records=False) is None


def test_a_challenge_page_climbs_even_with_status_200():
    challenge = '<html><body><div id="cf-challenge-running"></div>Just a moment...</body></html>'

    reason = why_climb(200, challenge, found_records=False)

    assert reason is not None
    assert "challenge" in reason.lower()


def test_a_skeletal_body_climbs():
    skeleton = '<html><body><div id="app"></div>' + ('<script src="a.js"></script>' * 80) + "</body></html>"

    assert why_climb(200, skeleton, found_records=False) is not None


def test_a_thin_page_that_declared_records_stays_put():
    thin = "<html><body><p>Short.</p></body></html>"

    assert why_climb(200, thin, found_records=True) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetch_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.fetch.rules'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/fetch/rules.py
"""When a cheap fetch is not good enough, and how we know.

Every rule here answers one question: did we get the page, or did we get
something standing in front of it? A rule that cannot be measured from the
response alone does not belong in this file.
"""

from __future__ import annotations

import re

TEXT_FLOOR = 200
"""Characters of visible text below which a page has told us almost nothing."""

MARKUP_CEILING = 2000
"""Characters of markup above which a page promised more than it delivered."""

_REFUSING_STATUSES = frozenset({401, 403, 407, 429})

_CHALLENGE_MARKERS = (
    "cf-challenge",
    "challenge-platform",
    "just a moment",
    "checking your browser",
    "__cf_chl",
    "enable javascript and cookies to continue",
)

_TAGS = re.compile(r"(?s)<(script|style).*?</\1>|<[^>]+>")


def why_climb(status: int, html: str, found_records: bool) -> str | None:
    """Return the reason to climb a rung, or None to stay where we are."""
    lowered = html.lower()
    for marker in _CHALLENGE_MARKERS:
        if marker in lowered:
            return f"the response is a challenge page, not the content: {marker!r}"
    # Checked before the status, because when both are true the challenge is the
    # more useful diagnosis: it says a browser will probably get through, where a
    # bare status leaves the reader guessing whether it is worth trying.
    if status in _REFUSING_STATUSES:
        return f"the server refused: status {status}"
    if status >= 500:
        return None

    text = _TAGS.sub(" ", html).strip()
    if len(text) < TEXT_FLOOR and len(html) > MARKUP_CEILING:
        return (
            f"the body is skeletal: {len(text)} characters of text "
            f"inside {len(html)} of markup"
        )
    if not found_records and len(text) < TEXT_FLOOR:
        return f"nothing was declared and there are only {len(text)} characters of text"
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fetch_rules.py -v`
Expected: PASS, all six tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch/rules.py tests/test_fetch_rules.py
git commit -m "feat: name the measurements that justify climbing a rung"
```

---

### Task 3: The ladder

**Files:**
- Create: `src/sluicer/fetch/ladder.py`, `tests/test_fetch_ladder.py`

**Interfaces:**
- Consumes: `Fetched`, `Climb`, `why_climb`, and `sluicer.extract`.
- Produces: `Rung = Callable[[str], Fetched]` and `fetch(url: str, rungs: Sequence[tuple[str, Rung]] | None = None) -> Fetched`.

Injectable rungs are how this stays testable offline. When `rungs` is None the real ones are used, and those arrive in Task 4.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fetch_ladder.py
import pytest

from sluicer.fetch.ladder import fetch
from sluicer.fetch.result import Fetched

RICH = (
    '<html><head><script type="application/ld+json">'
    '{"@type":"Product","name":"Brake pad set"}</script></head>'
    "<body>" + ("Real content. " * 40) + "</body></html>"
)
REFUSED = "<html><body>Forbidden</body></html>"


def rung(name, html, status=200):
    calls = []

    def go(url):
        calls.append(url)
        return Fetched(url=url, html=html, status=status, rung=name)

    go.calls = calls
    return go


def test_the_cheapest_rung_is_enough_and_the_others_never_run():
    http = rung("http", RICH)
    browser = rung("browser", RICH)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "http"
    assert result.climbs == []
    assert browser.calls == []


def test_a_refusal_climbs_once_and_records_why():
    http = rung("http", REFUSED, status=403)
    browser = rung("browser", RICH)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "browser"
    assert len(result.climbs) == 1
    assert result.climbs[0].from_rung == "http"
    assert result.climbs[0].to_rung == "browser"
    assert "403" in result.climbs[0].reason


def test_the_last_rung_is_returned_even_when_it_is_still_poor():
    http = rung("http", REFUSED, status=403)
    browser = rung("browser", REFUSED, status=403)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "browser"
    assert len(result.climbs) == 1


def test_an_empty_ladder_is_a_programming_error():
    with pytest.raises(ValueError):
        fetch("https://example.com", rungs=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetch_ladder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.fetch.ladder'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/fetch/ladder.py
"""Climb only when the page makes us.

The ladder starts at the cheapest rung and stops the moment a rung brings back
something worth keeping. Every climb is recorded with the measurement that
forced it, so a caller can always see what a page cost and why.
"""

from __future__ import annotations

from typing import Callable, Sequence

from sluicer.api import extract
from sluicer.fetch.result import Climb, Fetched
from sluicer.fetch.rules import why_climb

Rung = Callable[[str], Fetched]


def fetch(url: str, rungs: Sequence[tuple[str, Rung]] | None = None) -> Fetched:
    """Fetch ``url``, climbing only when a measurement says the rung failed."""
    if rungs is None:
        from sluicer.fetch.scrapling_rungs import default_rungs

        rungs = default_rungs()
    if not rungs:
        raise ValueError("A ladder needs at least one rung.")

    climbs: list[Climb] = []
    for index, (name, rung) in enumerate(rungs):
        last = index == len(rungs) - 1
        try:
            result = rung(url)
        except Exception as failure:
            # A rung that raises is a rung that failed, and failing is what the
            # ladder exists to answer: a refused connection on plain HTTP says
            # nothing about whether a browser would get through. The last rung
            # is different, because swallowing it would hand the caller an empty
            # page pretending to be a real one.
            if last:
                raise
            climbs.append(
                Climb(
                    from_rung=name,
                    to_rung=rungs[index + 1][0],
                    reason=f"the rung failed: {type(failure).__name__}: {failure}",
                )
            )
            continue
        result.climbs = list(climbs)
        found = bool(extract(result.html, url=url).records)
        reason = why_climb(result.status, result.html, found_records=found)
        if reason is None or last:
            return result
        climbs.append(Climb(from_rung=name, to_rung=rungs[index + 1][0], reason=reason))
    raise AssertionError("unreachable: the loop returns or raises on the last rung")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_fetch_ladder.py -v`
Expected: PASS, all four tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch/ladder.py tests/test_fetch_ladder.py
git commit -m "feat: a ladder that climbs only on a measurement"
```

---

### Task 4: The real rungs

**Files:**
- Create: `src/sluicer/fetch/scrapling_rungs.py`, `tests/test_scrapling_rungs.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `default_rungs() -> list[tuple[str, Rung]]` giving `http`, `browser` and `stealth` in that order, each a thin adapter over `scrapling`.

**Measured facts about scrapling's API, so you do not have to guess:** `Fetcher.get(url, **kwargs)`, `DynamicFetcher.fetch(url, **kwargs)` and `StealthyFetcher.fetch(url, **kwargs)` each return a `Response` carrying `status: int`, `body: bytes`, `html_content: str`, `encoding: str`, `url: str` and `headers`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scrapling_rungs.py
import sys
import types

import pytest

from sluicer.fetch.result import Fetched


def fake_scrapling(monkeypatch, status=200, html="<html><body>hi</body></html>"):
    """Stand in for scrapling so no test ever opens a socket."""
    seen = {}

    class Response:
        def __init__(self, url):
            self.status = status
            self.html_content = html
            self.body = html.encode()
            self.encoding = "utf-8"
            self.url = url

    def get(url, **kwargs):
        seen["http"] = (url, kwargs)
        return Response(url)

    def dynamic(url, **kwargs):
        seen["browser"] = (url, kwargs)
        return Response(url)

    def stealthy(url, **kwargs):
        seen["stealth"] = (url, kwargs)
        return Response(url)

    module = types.ModuleType("scrapling.fetchers")
    module.Fetcher = types.SimpleNamespace(get=get)
    module.DynamicFetcher = types.SimpleNamespace(fetch=dynamic)
    module.StealthyFetcher = types.SimpleNamespace(fetch=stealthy)
    monkeypatch.setitem(sys.modules, "scrapling", types.ModuleType("scrapling"))
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", module)
    return seen


def test_the_three_rungs_come_back_in_cost_order(monkeypatch):
    fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    assert [name for name, _ in default_rungs()] == ["http", "browser", "stealth"]


def test_a_rung_returns_a_fetched_carrying_the_status(monkeypatch):
    seen = fake_scrapling(monkeypatch, status=403)
    from sluicer.fetch.scrapling_rungs import default_rungs

    name, rung = default_rungs()[0]
    result = rung("https://example.com/p")

    assert isinstance(result, Fetched)
    assert result.status == 403
    assert result.rung == "http"
    assert seen["http"][0] == "https://example.com/p"


def test_a_missing_scrapling_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "scrapling", None)
    monkeypatch.setitem(sys.modules, "scrapling.fetchers", None)
    import importlib

    import sluicer.fetch.scrapling_rungs as rungs_module

    importlib.reload(rungs_module)
    with pytest.raises(ImportError) as raised:
        rungs_module.default_rungs()

    assert "sluicer[fetch]" in str(raised.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scrapling_rungs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.fetch.scrapling_rungs'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/fetch/scrapling_rungs.py
"""The real rungs, each a thin adapter over scrapling.

scrapling is optional: the base install reads HTML you already have, and only
fetching from the web needs a browser stack. Importing this module must stay
free, so the dependency is looked up when a rung is built, not at import time.
"""

from __future__ import annotations

from sluicer.fetch.result import Fetched

_MISSING = (
    "Fetching a URL needs scrapling, which is not installed. "
    "Install it with: uv pip install 'sluicer[fetch]'"
)


def _fetchers():
    try:
        from scrapling.fetchers import DynamicFetcher, Fetcher, StealthyFetcher
    except ImportError as missing:  # pragma: no cover - exercised via sys.modules
        raise ImportError(_MISSING) from missing
    if Fetcher is None:
        raise ImportError(_MISSING)
    return Fetcher, DynamicFetcher, StealthyFetcher


def _as_fetched(response, rung: str) -> Fetched:
    return Fetched(
        url=getattr(response, "url", ""),
        html=response.html_content,
        status=response.status,
        rung=rung,
    )


def default_rungs():
    """Return the three rungs in the order they cost us."""
    fetcher, dynamic, stealthy = _fetchers()

    def http(url: str) -> Fetched:
        return _as_fetched(fetcher.get(url, timeout=30), "http")

    def browser(url: str) -> Fetched:
        return _as_fetched(dynamic.fetch(url, network_idle=True), "browser")

    def stealth(url: str) -> Fetched:
        return _as_fetched(stealthy.fetch(url, network_idle=True), "stealth")

    return [("http", http), ("browser", browser), ("stealth", stealth)]
```

In `pyproject.toml`, add under `[project]`:

```toml
[project.optional-dependencies]
fetch = ["scrapling>=0.4"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scrapling_rungs.py -v`
Expected: PASS, all three tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch/scrapling_rungs.py tests/test_scrapling_rungs.py pyproject.toml
git commit -m "feat: three real rungs over scrapling, behind an optional extra"
```

---

### Task 5: `load()` accepts bytes

**Files:**
- Modify: `src/sluicer/document.py`, `src/sluicer/api.py`
- Test: `tests/test_document.py`

**Interfaces:**
- Produces: `load(html: str | bytes, url: str | None = None) -> Document` and `extract(html: str | bytes, url: str | None = None) -> Extraction`.

**Why now:** `docs/known-limits.md` deferred this exact question to this plan. The fetch layer is where the raw bytes and the transport's charset first exist, so it is the layer that can hand lxml the bytes and let it honour the document's own declaration instead of guessing. Passing bytes through is the whole fix.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_document.py
def test_load_accepts_bytes_and_honours_the_declared_encoding():
    from sluicer.document import load

    page = (
        '<html><head><meta charset="iso-8859-1">'
        "<title>Bremsöl</title></head><body></body></html>"
    )
    latin1 = page.encode("latin-1")

    doc = load(latin1)

    assert doc.tree.findtext(".//title") == "Bremsöl"


def test_load_still_takes_text():
    from sluicer.document import load

    assert load("<html><body><p>hi</p></body></html>").tree.findtext(".//p") == "hi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_document.py -v`
Expected: FAIL on the bytes test, with a TypeError or the title mangled. The fixture declares its charset in a meta tag on purpose: bytes with no declaration at all leave lxml guessing, and a test whose outcome depends on a guess is not a test.

- [ ] **Step 3: Write minimal implementation**

In `src/sluicer/document.py`, widen the signature to `html: str | bytes`, store `html` as given, and pass bytes straight to `lxml.html.fromstring` without encoding them: lxml reads the document's own declaration when it is handed bytes. Keep the existing fallback for a document lxml cannot parse at all, and keep the UTF-8 retry for the `str` path exactly as it is. Update the docstring to say that bytes are preferred when the caller has them, and why. Widen `extract()`'s annotation to match.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/document.py src/sluicer/api.py tests/test_document.py
git commit -m "feat: load() takes bytes so the document's own encoding wins"
```

---

### Task 6: A URL on the command line

**Files:**
- Modify: `src/sluicer/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `sluicer extract <path-or-url>`, which fetches when the argument starts with `http://` or `https://` and reads a file otherwise. The JSON gains a `fetch` object naming the rung used and every climb.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
def test_a_url_is_fetched_and_the_ladder_is_reported(monkeypatch):
    import json

    from click.testing import CliRunner

    from sluicer.cli import main
    from sluicer.fetch.result import Climb, Fetched

    def fake_fetch(url, rungs=None):
        return Fetched(
            url=url,
            html='<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"Brake pad set"}</script></head><body></body></html>',
            status=200,
            rung="browser",
            climbs=[Climb(from_rung="http", to_rung="browser", reason="the server refused: status 403")],
        )

    monkeypatch.setattr("sluicer.cli.fetch_url", fake_fetch)

    result = CliRunner().invoke(main, ["extract", "https://example.com/p"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["fetch"]["rung"] == "browser"
    assert payload["fetch"]["climbs"][0]["reason"] == "the server refused: status 403"
    assert payload["records"][0]["fields"]["name"]["value"] == "Brake pad set"


def test_a_path_is_still_read_from_disk():
    from pathlib import Path

    from click.testing import CliRunner

    from sluicer.cli import main

    fixtures = Path(__file__).parent / "fixtures"
    result = CliRunner().invoke(main, ["extract", str(fixtures / "product_jsonld.html")])

    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL with `AttributeError: <module 'sluicer.cli'> has no attribute 'fetch_url'`

- [ ] **Step 3: Write minimal implementation**

In `src/sluicer/cli.py`: import the ladder's `fetch` as `fetch_url` at module level so tests can replace it, change the argument from `click.Path` to a plain string, and branch on whether it starts with `http://` or `https://`. On the URL branch, call `fetch_url(source)`, extract from `result.html`, and add a `fetch` key to the payload carrying `rung`, `status` and the list of climbs. On the file branch, keep today's behaviour byte for byte, including both stderr messages and the exit codes. A file that does not exist must still fail with a clear message rather than a traceback, since `click.Path(exists=True)` no longer guards it.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/cli.py tests/test_cli.py
git commit -m "feat: sluicer extract takes a URL and reports what it cost"
```

---

## Out of scope

Crawling more than one page, sessions and cookies, proxies, captcha solving, caching, concurrency, and the MCP server. Each is its own plan.
