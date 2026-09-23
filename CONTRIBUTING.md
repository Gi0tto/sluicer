# Contributing

Thank you for looking. This is a small project with strong opinions, and the
opinions are the reason it exists, so it is worth knowing them before you spend
an evening on a patch.

## The three rules that are not negotiable

**No LLM call, anywhere in the path.** Not as a fallback, not for the hard
pages, not behind a flag. A run costs CPU and nothing else. There is a test that
walks the source and fails if a model client is ever imported; if your change
needs a model, it belongs in a different project.

**No paid API.** If a feature only works when somebody pays for a key, it does
not ship here.

**Deterministic.** The same input gives the same answer, every time. This is not
a style preference: it is what makes the scoreboard honest. A change that makes
output depend on timing, network weather or dictionary ordering will be sent
back.

## How to work

Tests first. Every behavioural change arrives with a test that fails before it
and passes after, and the failure has to be for the right reason. A test that
cannot fail is not protecting anything.

Run the suite from the repository root:

```bash
uv run pytest
```

CI also runs these, and refuses a change that fails any of them:

```bash
uv run ruff check src tests bench
uv run mypy
uv run pytest --cov          # coverage must stay at or above 97%
```

The suite takes a second or two and it never touches the network. If a test of
yours needs a page, save it under `tests/fixtures/` and read it from disk. If it
needs a fetch, inject a fake rung the way `tests/test_fetch_ladder.py` does.

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

English everywhere: code, comments, tests, commit messages.

## The documentation site

`docs/changelog.md`, `docs/roadmap.md`, `docs/contributing.md` and
`docs/security.md` are symlinks to the files of the same name in the repository
root. Edit the root file; the site follows.

`docs/index.md` is **not** a copy of the README and should not become one. A
README sells the project to someone deciding whether to try it; a documentation
home orients someone who has already decided. The README's links are absolute,
because it is also the PyPI page; the site's pages link relatively, and
`mkdocs build --strict` in CI refuses a broken one.
