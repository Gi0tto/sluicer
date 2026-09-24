# Contributing

Thank you for looking. This is a small project with strong opinions, and the
opinions are the reason it exists, so it is worth knowing them before you spend
an evening on a patch.

## The three rules that are not negotiable

**No LLM call, anywhere in the path.** Not as a fallback, not for the hard
pages, not behind a flag. A run costs CPU and nothing else. A test walks the
source and fails if a model client is ever imported; if your change needs a
model, it belongs in a different project.

**No paid API.** If a feature only works when somebody pays for a key, it does
not ship here.

**Deterministic.** The same input gives the same answer, every time. This is not
a style preference: it is what makes the scoreboards honest. A change that makes
output depend on timing, network weather, today's date or dictionary ordering
will be sent back.

## Set up

You need [uv](https://docs.astral.sh/uv/) and Git; uv brings the Python.

```bash
git clone https://github.com/Gi0tto/sluicer.git
cd sluicer
uv run --extra api pytest -q        # the whole suite, as CI runs it
```

The first run creates `.venv` with the package, its extras and the development
tools. The suite is about 1,800 tests, takes half a minute, and never touches
the network: a CI job runs it with the network taken away.

## Before you open a pull request

Format the code in its one style, then run what CI refuses a change for
failing:

```bash
uv run ruff format src tests bench scripts examples
uv run ruff check src tests bench scripts examples
uv run mypy                                           # strict, at the 3.10 floor
uv run --extra api pytest -q --cov                    # coverage stays at or above 97%
```

And the properties, which draw pages at random -- hostile ones included -- and
hold what must be true of every page. Locally each draws 15 examples; CI draws
300 on every push, and 2,500 every week and before a release:

```bash
HYPOTHESIS_PROFILE=search uv run --extra microformats pytest -q tests/properties
```

## How to work

Tests first. Every behavioural change arrives with a test that fails before it
and passes after, and the failure has to be for the right reason. A test that
cannot fail is not protecting anything: break the code on purpose once and
watch your test go red.

If a test of yours needs a page, save it under `tests/fixtures/` and read it
from disk. If it needs a fetch, inject a fake rung the way
`tests/test_fetch_ladder.py` does, or a fake site the way `tests/fake_site.py`
serves one to the crawler.

A change that alters what Sluicer answers is measured before it is merged: run
the scoreboards (below) before and after, and say in the pull request which
answers changed, on how many pages, and whether the labels call them right.

## Where things are

| path | what it holds |
|---|---|
| `src/sluicer/api.py` | `extract`, the one call most people make |
| `src/sluicer/declared/` | a reader per vocabulary, and the merge that keeps each value's source and place |
| `src/sluicer/summary.py` | the 25 questions, the order candidates are asked in, and the conflicts |
| `src/sluicer/normalise.py` | what dates, prices and currencies mean, when that is certain |
| `src/sluicer/fetch/` | the ladder: plain HTTP, then a browser only when a measurement says so |
| `src/sluicer/structure/`, `extractor.py` | induction, and extractors that are learnt, replayed and healed |
| `src/sluicer/crawl/` | maps, crawls and batches, and the politeness that paces them |
| `src/sluicer/audit/` | a page's markup held to what Google documents |
| `src/sluicer/cli.py`, `mcp_server.py`, `http_api.py` | the command line, the MCP server and the HTTP door |
| `tests/` | the suite; `tests/properties/` the properties; `tests/live/` the checks CI runs against real curl, browsers and installs |
| `bench/` | the scoreboards and the drift benchmark; [`bench/README.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/README.md) says how each is run |
| `docs/` | the documentation site |
| `scripts/` | the generators of the files below |

## Files that are generated

Edit the source, then run its generator. For the documentation's home and the
reference pages a test fails when the two disagree; the others are regenerated
before a release.

| file | generated from | by |
|---|---|---|
| `docs/index.md` | `README.md` | `uv run scripts/docs_home.py` |
| `docs/reference/*.md` | the commands' help, the MCP server's tools, the public docstrings | `uv run scripts/reference.py` |
| `docs/assets/inspect.svg`, `dates-*.svg` | `examples/brake-pads.html`, `docs/scoreboard-served.md` | `uv run scripts/readme_assets.py` |
| `docs/assets/demo.cast`, `demo.gif` | four Wayback Machine captures of a software directory, named in the script | `uv run scripts/demo.py`, with [agg](https://github.com/asciinema/agg) |
| `docs/assets/social-preview.png` | the card's words, in the script | `uv run scripts/social_card.py` |
| `src/sluicer/calendar_names.py` | the Unicode CLDR, at a pinned release | `uv run scripts/cldr_calendar.py` |
| `docs/scoreboard*.md`, `docs/drift.md` | the benchmarks' pinned pages | the scripts in `bench/`, see [`bench/README.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/README.md) |

`docs/changelog.md`, `docs/roadmap.md`, `docs/contributing.md` and
`docs/security.md` are symlinks to the files of the same name in the repository
root: edit the root file, and the site follows.

## The documentation site

```bash
uvx --from 'mkdocs>=1.6,<2' --with 'mkdocs-material>=9.7,<10' mkdocs serve
```

serves it at <http://127.0.0.1:8000> as you edit. CI builds it with
`mkdocs build --strict`, which refuses a broken link. The README's links are
absolute, because the README is also the PyPI page; the site's are relative,
and `scripts/docs_home.py` rewrites the one into the other.

## What gets a patch rejected

Code that guesses. This project would rather lose a block than invent a value:
if a page cannot be read, we say so and move on. A change that returns something
plausible where the truth was unavailable is the one kind of bug we take
personally.

Silent failure. An empty result that could mean either "the page declares
nothing" or "we broke" is worse than a loud error.

Claims without measurement. If your patch is faster, or reads more pages, say by
how much and against what. `docs/known-limits.md` exists so the project can
state its own limits; a pull request should hold itself to the same standard.

## Style

Follow the file next to yours. Module docstring saying what the file is for,
typed public functions, short docstrings that say what comes back. Annotations
must be honest: if you know the type, write it, and do not annotate something as
`object` to silence a checker.

English everywhere: code, comments, tests, commit messages, documentation.

## Pull requests

One change per pull request, with its test, and a line in `CHANGELOG.md` under
`Unreleased` when a user would notice it. If you used AI assistance, say so and
roughly how much, as [`AI_POLICY.md`](https://github.com/Gi0tto/sluicer/blob/main/AI_POLICY.md) asks. Security issues go
through [`SECURITY.md`](https://github.com/Gi0tto/sluicer/blob/main/SECURITY.md), not a public issue.
