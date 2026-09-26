"""Every tool on the same pages (``bench/tools_compare.py``), scored as
``bench/PREREG.md`` fixed it: one plain-text rule for every tool's text, WCXB's
word scores, and a wrong answer counted silent unless the tool warned of it.

Fed made-up pages and runs here, never a corpus. The harness is not in the
sdist, and its scorer needs dateutil: without either, this skips.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "tools_compare.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("dateutil")
sys.path.insert(0, str(BENCH))

import tools_compare as board  # noqa: E402

sys.path.insert(0, str(BENCH / "tools"))
from compare_common import answered, text_or_none  # noqa: E402

# --- one rule for every tool's text ---------------------------------------------


def test_markdown_and_plain_text_of_one_page_read_alike():
    markdown = (
        "Hello\n=====\n\n## Part\n\n- By **Jane** Doe\n1. Some [text](/y) here\n\n"
        "| a | b |\n|---|---|\n| c | d |\n\n[![logo](/i.png)](/) Liebe\\_r"
    )
    text = "Hello Part By Jane Doe Some text here a b c d logo Liebe_r"
    assert board.plain(markdown) == text
    assert board.plain(text) == text


def test_no_text_is_the_empty_string():
    assert board.plain(None) == ""
    assert board.plain("  \n ") == ""


# --- WCXB's word scores -----------------------------------------------------------


def test_the_word_scores_count_words_as_a_multiset():
    precision, recall, f1 = board.word_scores("the cat the dog", "The cat sat")
    # Overlap: one "the", one "cat", of 4 words given and 3 labelled.
    assert precision == pytest.approx(2 / 4)
    assert recall == pytest.approx(2 / 3)
    assert f1 == pytest.approx(2 * (1 / 2) * (2 / 3) / (1 / 2 + 2 / 3))


def test_no_text_scores_zero_on_a_page_with_main_text():
    assert board.word_scores("", "some main text") == (0.0, 0.0, 0.0)


# --- silent wrong -------------------------------------------------------------------


def _page(page_id, **labels):
    return {
        "id": page_id,
        "url": f"https://example.com/{page_id}",
        "metadata": True,
        "with": ["kept text"],
        "without": ["Menu item"],
        "title": labels.get("title"),
        "author": labels.get("author"),
        "date": labels.get("date"),
    }


def test_a_wrong_date_is_silent_unless_the_tool_warned_of_it():
    pages = [
        _page("a", date="2026-09-15"),
        _page("b", date="2026-09-15"),
        _page("c"),
    ]
    run = {
        "tool": "sluicer",
        "version": "0",
        "results": [
            {"id": "a", "date": "2026-09-22", "flagged": []},
            {"id": "b", "date": "2026-09-22", "flagged": ["date"]},
            {"id": "c", "date": "2026-09-22", "flagged": []},
        ],
    }
    per_page = board.meta_outcomes(pages, run)
    found = board.silent_wrong(per_page, run, "date")
    # "c" has no date label: an answer there is invented, and silent too.
    assert found == {"silent": ["a", "c"], "flagged": ["b"], "given": 3}


def test_a_guess_of_visible_fills_only_a_silent_summary_and_is_never_flagged():
    run = {
        "tool": "sluicer",
        "version": "0",
        "results": [
            {
                "id": "a",
                "title": "Declared",
                "author": None,
                "date": None,
                "flagged": ["title", "author"],
                "visible": {"title": "Seen", "author": "Jane Doe", "date": None},
            }
        ],
    }
    row = board.with_visible(run)["results"][0]
    assert (row["title"], row["author"], row["date"]) == ("Declared", "Jane Doe", None)
    assert row["flagged"] == ["title"]


# --- the text -----------------------------------------------------------------------


def test_a_menu_that_leaks_makes_a_page_unclean_and_no_text_is_silent_empty():
    pages = [_page("a"), _page("b"), _page("c")]
    run = {
        "tool": "t",
        "version": "0",
        "results": [
            {"id": "a", "text": "[Menu item](/m)\n\nkept **text**"},
            {"id": "b", "text": ""},
            {"id": "c", "text": None, "raised": "ValueError: x"},
        ],
    }
    rows = board.text_rows(pages, run)
    assert rows["a"]["snippets"] == [1, 1, 0, 0]
    assert rows["a"]["clean"] is False
    assert rows["b"]["empty"] is True
    # A raise is loud: it is counted as raised, not as silently empty.
    assert (rows["c"]["empty"], rows["c"]["raised"]) == (False, True)


def test_a_question_a_tool_does_not_answer_is_not_compared():
    pages = [_page(f"p{n}", title="Hello", author="Jane Doe") for n in range(5)]
    runs = {
        "sluicer": {
            "tool": "sluicer",
            "version": "0",
            "results": [
                {"id": p["id"], "title": "Hello", "author": None, "text": "kept text"}
                for p in pages
            ],
        },
        "markitdown": {
            "tool": "markitdown",
            "version": "0",
            "results": [
                {"id": p["id"], "title": "Hello", "text": "Menu item kept text"}
                for p in pages
            ],
        },
    }
    per_page = {tool: board.meta_outcomes(pages, run) for tool, run in runs.items()}
    texts = {tool: board.text_rows(pages, run) for tool, run in runs.items()}
    found = board.comparisons(per_page, texts)
    questions = {field for (_ours, _tool, field, _measure) in found}
    assert questions == {"title", "text"}
    kept_clean = found[("sluicer", "markitdown", "text", "pages kept clean")]
    assert kept_clean.verdict == "better"


# --- the harness ----------------------------------------------------------------------


def test_a_tool_that_raises_answers_nothing_and_says_what_it_raised():
    @answered
    def extract(html, url):
        raise ValueError("no page")

    assert extract(b"", None) == {
        "title": None,
        "author": None,
        "date": None,
        "text": None,
        "raised": "ValueError: no page",
    }


def test_an_answer_of_several_names_is_one_text():
    assert text_or_none(["Jane Doe", "", "John Roe"]) == "Jane Doe, John Roe"
    assert text_or_none("  ") is None


def test_every_page_added_by_hand_is_pinned_and_labelled():
    added = json.loads((BENCH / "tools-added.json").read_text(encoding="utf-8"))
    for page in added["pages"]:
        assert len(page["sha256"]) == 64
        assert page["archive"] == "wayback" and len(page["timestamp"]) == 14
        assert all(page[field] for field in ("title", "author", "date"))
        assert 0 < len(page["with"]) <= 6 and 0 < len(page["without"]) <= 6
