"""The examples run, and print what their docstrings promise.

Each runs as its own process, as a reader runs it, against the small made-up
site that ``examples/_site.py`` serves on this machine from ``examples/site``.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

pytest.importorskip("protego", reason="the examples fetch, which the base install does")
pytest.importorskip("trafilatura", reason="two examples need sluicer[markdown]")


def _run(example: str) -> str:
    done = subprocess.run(
        [sys.executable, example],
        cwd=EXAMPLES,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        # print() writes a pipe in the locale's code page, cp1252 on Windows.
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        encoding="utf-8",
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_declared_fields_come_with_their_reader_and_key():
    out = _run("01_declared_fields.py")
    assert out.startswith("got it on the http rung, after 0 climbs\n")
    assert "vocabularies that fired: ['jsonld', 'opengraph', 'html']" in out
    assert "headline               'How a sluice gate works'  via jsonld" in out
    assert "author       'Jane Doe'  jsonld Article.author" in out


def test_a_page_robots_txt_keeps_crawlers_from_is_not_asked_for():
    lines = _run("02_respecting_a_refusal.py").splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("fetched  http://127.0.0.1:")
    assert lines[0].endswith("/article.html  on the http rung")
    assert lines[1].startswith("refused  http://127.0.0.1:")
    assert lines[1].endswith("/drafts/winter.html  by the site's own rules")


def test_the_article_as_markdown_leaves_the_furniture_out():
    out = _run("03_page_as_markdown.py")
    assert out.startswith("# How a sluice gate works\n\nA sluice gate is a plate")
    assert "Articles" not in out, "the navigation is furniture"


def test_what_the_page_does_not_declare_is_a_guess_and_says_so():
    assert _run("04_a_guess_from_the_visible_page.py").splitlines() == [
        "author: 'Jane Doe'  a guess from the visible page",
        "published: '2025-04-14'  a guess from the visible page",
    ]
