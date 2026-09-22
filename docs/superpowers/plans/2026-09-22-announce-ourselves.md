# Announce Ourselves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Sluicer identify itself, obey `robots.txt` by default, and stop climbing to the stealth rung unless the caller asked for it.

**Architecture:** One small module owns the identity and the robots decision. The ladder consults it before the first rung. The stealth rung leaves the default ladder and is added only on request, so the automatic path never turns an announced fetcher into a disguised one.

**Tech Stack:** Python 3.10+, `protego` for parsing `robots.txt`. It arrives transitively with `scrapling[fetchers]`, and the `fetch` extra declares it anyway: a transitive dependency is not a declared one, and this project has already shipped that mistake twice.

**Spec:** `docs/superpowers/specs/2026-09-22-sluicer-design.md`. The demand is recorded in `ROADMAP.md`: the most requested unaddressed issue on the largest project in this field asks for an identifiable user agent so a site owner can refuse it.

## Global Constraints

- Python `>=3.10`. Licence MIT. No vendored AGPL code.
- No LLM call anywhere. No paid API.
- Deterministic.
- English only everywhere including commit messages.
- **Unit tests never touch the network.** `protego` and the fetching are injected or faked.
- `import sluicer` keeps working with every extra absent.
- Every public function typed, annotations honest.
- A missing optional extra raises through `sluicer.extras.import_extra`, never a bare `ImportError`.

---

## File Structure

| file | responsibility |
| --- | --- |
| `src/sluicer/fetch/identity.py` | `USER_AGENT`, `robots_allows()`, the per-host cache |
| `src/sluicer/fetch/scrapling_rungs.py` | extended: send the user agent, and stealth is no longer in the default set |
| `src/sluicer/fetch/ladder.py` | extended: consult robots before the first rung; accept a stealth rung on request |

---

### Task 1: Who we are, and what a site allows

**Files:**
- Create: `src/sluicer/fetch/identity.py`, `tests/test_identity.py`

**Interfaces:**
- Produces: `USER_AGENT: str`, `robots_url_for(url: str) -> str`, and `robots_allows(url: str, read: Callable[[str], str | None], cache: dict | None = None) -> bool`.
- `read` is injected: it takes the robots URL and returns its text, or None when there is none to read. That keeps this module free of any fetching and makes every test offline.

**The rules, stated once so the tests can pin them:**
- No `robots.txt`, or one that cannot be read, means allowed. A site that publishes no rules has not refused.
- A `robots.txt` that exists and disallows the path means not allowed, and nothing climbs. A refusal we were told about is not a challenge to get around.
- The answer is cached per host, because asking again for every page on a site is its own kind of rude.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identity.py
from sluicer.fetch.identity import USER_AGENT, robots_allows, robots_url_for

ALLOW_ALL = "User-agent: *\nAllow: /\n"
REFUSE_US = "User-agent: Sluicer\nDisallow: /private/\n\nUser-agent: *\nAllow: /\n"


def test_the_user_agent_says_who_we_are_and_where_to_find_us():
    assert "Sluicer" in USER_AGENT
    assert "https://github.com/" in USER_AGENT


def test_robots_lives_at_the_root_of_the_host():
    assert robots_url_for("https://example.com/deep/page?x=1") == "https://example.com/robots.txt"


def test_a_site_with_no_robots_allows_us():
    assert robots_allows("https://example.com/p", read=lambda url: None) is True


def test_a_site_that_refuses_us_is_obeyed():
    assert robots_allows("https://example.com/private/p", read=lambda url: REFUSE_US) is False


def test_a_path_that_same_site_allows_is_allowed():
    assert robots_allows("https://example.com/public", read=lambda url: REFUSE_US) is True


def test_the_answer_is_cached_per_host():
    calls = []

    def read(url):
        calls.append(url)
        return ALLOW_ALL

    cache: dict = {}
    robots_allows("https://example.com/a", read=read, cache=cache)
    robots_allows("https://example.com/b", read=read, cache=cache)
    robots_allows("https://other.com/a", read=read, cache=cache)

    assert calls == ["https://example.com/robots.txt", "https://other.com/robots.txt"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sluicer.fetch.identity'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/sluicer/fetch/identity.py
"""Who Sluicer says it is, and whether a site has asked it not to come.

A fetcher that hides behind a browser's user agent cannot be refused, because
nobody can tell it apart from a person. The most requested unaddressed issue on
the largest project in this field asks for exactly the opposite of that, so
Sluicer arrives under its own name and obeys what it is told.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import urlsplit, urlunsplit

from sluicer import __version__
from sluicer.extras import import_extra

USER_AGENT = f"Sluicer/{__version__} (+https://github.com/Gi0tto/sluicer)"
"""What every request says it is. One line in robots.txt is enough to refuse it."""


def robots_url_for(url: str) -> str:
    """Return the address of the robots file governing ``url``."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))


def robots_allows(
    url: str,
    read: Callable[[str], str | None],
    cache: dict | None = None,
) -> bool:
    """Say whether ``url`` may be fetched, according to the site's own rules.

    ``read`` is given the robots address and returns its text, or None when
    there is nothing to read. Injecting it keeps this module out of the
    fetching business and every test off the network.

    A site that publishes no rules has not refused, so a missing or unreadable
    robots file means yes. A site that publishes a refusal is obeyed: a rule we
    were told about is not an obstacle to route around.
    """
    host = urlsplit(url).netloc
    store = cache if cache is not None else _CACHE
    if host not in store:
        store[host] = read(robots_url_for(url))
    text = store[host]
    if not text:
        return True
    protego = import_extra("protego", "fetch")
    return bool(protego.Protego.parse(text).can_fetch(url, USER_AGENT))


_CACHE: dict[str, str | None] = {}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_identity.py -v`
Expected: PASS, all six tests

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch/identity.py tests/test_identity.py
git commit -m "feat: arrive under our own name, and obey what a site says"
```

---

### Task 2: The rungs say who they are, and stealth leaves the default

**Files:**
- Modify: `src/sluicer/fetch/scrapling_rungs.py`
- Test: `tests/test_scrapling_rungs.py`

**Interfaces:**
- `default_rungs()` returns `http` and `browser` only.
- New: `stealth_rung() -> tuple[str, Rung]`, so a caller who wants the third rung asks for it by name.
- The `http` and `browser` rungs send `USER_AGENT`.

**Why stealth leaves the default:** climbing from announcing ourselves to disguising ourselves is a change of character, not a change of technique. Making it automatic means a caller who never asked ends up evading a site that refused them. It stays available, one argument away, for someone who has decided they want it.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_scrapling_rungs.py
def test_the_default_ladder_does_not_include_stealth(monkeypatch):
    fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import default_rungs

    assert [name for name, _ in default_rungs()] == ["http", "browser"]


def test_stealth_is_available_to_a_caller_who_asks(monkeypatch):
    fake_scrapling(monkeypatch)
    from sluicer.fetch.scrapling_rungs import stealth_rung

    name, rung = stealth_rung()

    assert name == "stealth"
    result = rung("https://example.com/p")
    assert result.rung == "stealth"


def test_the_http_rung_says_who_it_is(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    dict(default_rungs())["http"]("https://example.com/p")

    headers = seen["http"][1].get("headers") or {}
    assert headers.get("User-Agent") == USER_AGENT


def test_the_browser_rung_says_who_it_is(monkeypatch):
    seen = fake_scrapling(monkeypatch)
    from sluicer.fetch.identity import USER_AGENT
    from sluicer.fetch.scrapling_rungs import default_rungs

    dict(default_rungs())["browser"]("https://example.com/p")

    headers = seen["browser"][1].get("extra_headers") or seen["browser"][1].get("headers") or {}
    assert headers.get("User-Agent") == USER_AGENT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scrapling_rungs.py -v`
Expected: FAIL, the default ladder still has three rungs and no rung sends a user agent.

- [ ] **Step 3: Write minimal implementation**

Change `default_rungs()` to return `http` and `browser`. Add `stealth_rung()` returning the third. Give the `http` rung `headers={"User-Agent": USER_AGENT}` and the `browser` rung the equivalent scrapling accepts; read scrapling's own type definitions rather than guessing which keyword it takes, and say in your report which one you used and how you confirmed it. Do not give the stealth rung a user agent: its whole purpose is not to be recognised, and a caller who asked for it has decided that.

Every existing test that asserted three rungs needs updating to the new default. Do not delete those assertions: move them onto `stealth_rung()` where they still apply.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch/scrapling_rungs.py tests/test_scrapling_rungs.py
git commit -m "feat: the rungs say who they are, and stealth is asked for"
```

---

### Task 3: The ladder asks first

**Files:**
- Modify: `src/sluicer/fetch/ladder.py`
- Test: `tests/test_fetch_ladder.py`

**Interfaces:**
- `fetch(url, rungs=None, obey_robots: bool = True, stealth: bool = False) -> Fetched`.
- When `obey_robots` is true and the site refuses, `fetch` raises `RobotsRefused(url)`, a new exception exported from `sluicer.fetch`.
- When `stealth` is true, the stealth rung is appended to the ladder.

**Why an exception rather than an empty result:** a refusal is not a page. Returning an empty `Fetched` would put "the site said no" and "the site had nothing" into the same shape, which is the failure this project spends its time removing.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_fetch_ladder.py
import pytest

from sluicer.fetch.ladder import RobotsRefused, fetch


def test_a_refusal_stops_the_ladder_before_the_first_rung():
    http = rung("http", RICH)

    with pytest.raises(RobotsRefused):
        fetch(
            "https://example.com/private/p",
            rungs=[("http", http)],
            robots_reader=lambda url: "User-agent: Sluicer\nDisallow: /private/\n",
        )

    assert http.calls == []


def test_a_site_with_no_robots_is_fetched():
    http = rung("http", RICH)

    result = fetch(
        "https://example.com/p", rungs=[("http", http)], robots_reader=lambda url: None
    )

    assert result.rung == "http"


def test_robots_can_be_turned_off_deliberately():
    http = rung("http", RICH)

    result = fetch(
        "https://example.com/private/p",
        rungs=[("http", http)],
        obey_robots=False,
        robots_reader=lambda url: "User-agent: Sluicer\nDisallow: /private/\n",
    )

    assert result.rung == "http"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_fetch_ladder.py -v`
Expected: FAIL, `RobotsRefused` does not exist and `fetch` takes no such arguments.

- [ ] **Step 3: Write minimal implementation**

Add `RobotsRefused(Exception)` with a message naming the URL and saying the site's own rules refused it. Add the two keyword arguments plus `robots_reader`, injected exactly as the rungs are, defaulting to a reader built from the cheapest rung so production needs no wiring. Consult `robots_allows` before the loop. Append `stealth_rung()` when `stealth` is true. Export `RobotsRefused` from `src/sluicer/fetch/__init__.py`.

The CLI must turn `RobotsRefused` into a message and exit 1, joining the operational failures it already handles rather than reaching the user as a traceback.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest -v`
Expected: PASS, whole suite

- [ ] **Step 5: Commit**

```bash
git add src/sluicer/fetch/ladder.py src/sluicer/fetch/__init__.py src/sluicer/cli.py tests/
git commit -m "feat: ask the site first, and take no for an answer"
```

---

## Out of scope

`Crawl-delay` and rate limiting, a sitemap reader, and any allowlist for the MCP server. Each is its own plan.
