"""anansi is asked on the drift pairs what Scrapling is asked, as
``bench/PREREG.md`` fixed it before either was run: the same item, followed
from A to B, judged by the drift page's own comparison of titles.

anansi itself runs in an environment of its own; these hold the harness's
choice of the element on A, the judging, and what the page says. The harness
is not in the sdist: without it, this skips.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

DRIFT = Path(__file__).resolve().parent.parent / "bench" / "drift"
if not (DRIFT / "run.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)


def _load(name: str):
    sys.path.insert(0, str(DRIFT))
    spec = importlib.util.spec_from_file_location(name, DRIFT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the element anansi is shown on A ---------------------------------------------

LISTING = b"""<html><body>
<aside><h4>Seen elsewhere</h4><p><a href="/other">Brake pads, explained</a></p></aside>
<ul class="items">
  <li class="item"><h3 class="title"><a href="/pads">Brake
     pads,  explained</a></h3><span>3 comments</span></li>
  <li class="item"><h3 class="title"><a href="/discs">Discs</a></h3></li>
</ul></body></html>"""


def test_the_element_is_the_innermost_holding_the_title_by_the_item_s_link():
    pytest.importorskip("bs4")
    from bs4 import BeautifulSoup

    tool = _load("anansi_tool")
    soup = BeautifulSoup(LISTING, "lxml")
    found = tool.element(soup, "Brake pads, explained", "/pads")
    assert found is not None
    assert found.name == "a" and found["href"] == "/pads"
    # Without the item's link, the first of the innermost ones.
    first = tool.element(soup, "Brake pads, explained", None)
    assert first is not None and first["href"] == "/other"
    assert tool.element(soup, "Not on the page", None) is None


# --- judging and saying ---------------------------------------------------------


def test_anansi_s_answer_is_judged_as_the_page_compares_titles():
    board = _load("run")
    asked = {"wanted": "1. Brake pads, explained", "selector": "h3.title > a"}
    right = board.judged_anansi({**asked, "got": "Brake  pads, explained"})
    assert right["result"] == "right"
    wrong = board.judged_anansi({**asked, "got": "Discs"})
    assert wrong["result"] == "wrong"
    nothing = board.judged_anansi({**asked, "got": None})
    assert nothing["result"] == "nothing found"
    # What the harness could not ask is kept as it said it.
    assert board.judged_anansi({"result": "title not found on A"}) == {
        "result": "title not found on A"
    }


def _pair(pair_id: str, anansi: dict) -> dict:
    return {
        "id": pair_id,
        "url": f"https://{pair_id}.example/",
        "outcome": "survived",
        "oracle": "same",
        "oracle_why": "",
        "heal": {"verdict": "right"},
        "anansi": anansi,
    }


def test_the_page_counts_anansi_as_it_counts_scrapling():
    board = _load("run")
    results = [
        _pair("a", {"result": "right", "healed": False}),
        _pair("b", {"result": "wrong", "healed": True, "got": "x", "wanted": "y"}),
        _pair("c", {"result": "nothing found", "healed": True, "wanted": "z"}),
        _pair("d", {"result": "no A item is still on B"}),
    ]
    said = " ".join(board.anansi_lines(results, "1.1.0"))
    assert "ran on 3 pairs" in said
    assert "right on 1" in said and "wrong on 1" in said and "nothing on 1" in said
    assert "healed on 2" in said
    assert "does not tell its caller" in said
    assert "1.1.0" in said


def test_a_long_title_is_judged_whole_and_shown_cut():
    board = _load("run")
    wanted = "A" * 80 + " the end"
    judged = board.judged_anansi(
        {"wanted": wanted, "got": "A" * 80 + " another end", "selector": "a"}
    )
    assert judged["result"] == "wrong"
    assert len(judged["wanted"]) == 80 and len(judged["got"]) == 80


def test_the_page_names_the_commit_anansi_is_pinned_at():
    """Its package says 1.1.0 at the commit tagged v1.2.0, and it is not on
    PyPI: the version alone does not say which anansi ran."""
    board = _load("run")
    assert board._anansi_commit().startswith("117fbe27b3d6")
