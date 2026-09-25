# Contributing

Thank you for looking. This is a small project with strong opinions, and the
opinions are the reason it exists, so it is worth knowing them before you spend
an evening on a patch. A question, or an idea you would like to talk through
first, goes to [Discussions](https://github.com/Gi0tto/sluicer/discussions); a
page Sluicer read wrong is an issue.

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

It runs in a random order each time (pytest-randomly), so a test that passes
only because of the one before it fails. The header prints the order's seed
(`Using --randomly-seed=...`, shown without `-q`); `pytest -p randomly
--randomly-seed=N` replays it, and CI seeds each run with its run id.
`-p no:randomly` runs the tests in file order.

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
| `tests/` | the suite; `tests/properties/` the properties; `tests/live/` the checks CI runs against real sockets, browsers and installs |
| `bench/` | the scoreboards and the drift benchmark; [`bench/README.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/README.md) says how each is run |
| `examples/` | scripts that run as they are, on `examples/site/`, a made-up site served on your machine |
| `docs/` | the documentation site |
| `scripts/` | the generators of the files below, and the hook that publishes `examples/site/` with the documentation |

## Files that are generated

Edit the source, then run its generator. For the documentation's home and the
reference pages a test fails when the two disagree; the others are regenerated
before a release.

| file | generated from | by |
|---|---|---|
| `docs/index.md` | `README.md` | `uv run scripts/docs_home.py` |
| `docs/reference/*.md` | the commands' help, the MCP server's tools, the public docstrings | `uv run scripts/reference.py` |
| `docs/assets/inspect.svg`, `dates-*.svg`, `swde-*.svg`, and the README's charts' alt texts and WCXB timings | `examples/brake-pads.html`, `docs/scoreboard-served.md`, `docs/scoreboard-swde.md`, `docs/scoreboard.md` | `uv run scripts/readme_assets.py` |
| `docs/assets/demo.cast`, `demo.gif` | four Wayback Machine captures of a software directory, named in the script | `uv run scripts/demo.py`, with [agg](https://github.com/asciinema/agg) |
| `docs/assets/social-preview.png` | the card's words, in the script | `uv run scripts/social_card.py` |
| `src/sluicer/calendar_names.json` | the Unicode CLDR, at a pinned release | `uv run scripts/cldr_calendar.py` (CI runs it with `--check`) |
| `packaging/homebrew/sluicer.rb`, `packaging/conda-forge/recipe/recipe.yaml` | `VERSION` and the pinned resources in `packaging/recipes.py`, and the sdist on PyPI | `python packaging/recipes.py` (`--sdist PATH` for a local build, `--check` to compare) |
| `docs/scoreboard*.md`, `docs/drift.md` | the benchmarks' pinned pages | the scripts in `bench/`, see [`bench/README.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/README.md) |

`docs/changelog.md`, `docs/roadmap.md`, `docs/contributing.md` and
`docs/security.md` are symlinks to the files of the same name in the repository
root: edit the root file, and the site follows. The site also publishes
`examples/site/` at `demo/`, through `scripts/docs_demo.py`, a hook `mkdocs.yml`
names; and `scripts/docs_llms.py`, another, writes the site's `llms.txt` from
the nav and each page's opening paragraph, with every page's markdown beside
it. A page outside the nav fails the suite, since `llms.txt` would not list it.
`context7.json` tells Context7 which of the docs to index; the suite holds its
rules to the commands, options, extras and names that exist.

### The Homebrew formula and the conda-forge recipe

Both are for the base install, and neither is edited by hand: change
`VERSION` in `packaging/recipes.py` and run it, and it takes the sdist's
address and checksum from PyPI once the release is published; until then
both files carry a placeholder checksum that says so. The formula is written
for homebrew-core, which takes it once Sluicer meets its notability rules (75
stars, or 30 forks or watchers, and a repository 30 days old); until then it
can be served from a tap of our own. The recipe is conda-forge's v1 format,
for staged-recipes, and installs on conda-forge's minimum Python, 3.11 today.
Nothing submits either: a person does, after the release.

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
