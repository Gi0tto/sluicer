"""How the RDFa conformance run reads Sluicer's records and writes its scoreboard.

The harness is not in the sdist: without it, this skips.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "rdfa_conformance.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
sys.path.insert(0, str(BENCH))

import rdfa_conformance as board  # noqa: E402


def test_records_are_read_as_a_caller_reads_them():
    graph = board.records_as_graph(
        [
            {
                "@type": "Person",
                "name": ["Ada", "Ada Lovelace"],
                "http://xmlns.com/foaf/0.1/homepage": "https://ada.example/",
                "worksFor": {"@type": "Organization", "name": "Engine"},
                "description": "Note: https is not a scheme here",
            }
        ]
    )
    person, employer = graph
    assert person["@id"] == "_:r0" and employer["@id"] == "_:r1"
    assert person["@type"] == ["http://schema.org/Person"]
    assert person["http://schema.org/name"] == [
        {"@value": "Ada"},
        {"@value": "Ada Lovelace"},
    ]
    assert person["http://xmlns.com/foaf/0.1/homepage"] == [
        {"@id": "https://ada.example/"}
    ]
    assert person["http://schema.org/worksFor"] == [{"@id": "_:r1"}]
    assert person["http://schema.org/description"] == [
        {"@value": "Note: https is not a scheme here"}
    ]
    assert employer["http://schema.org/name"] == [{"@value": "Engine"}]


def _run(
    passed: dict[str, bool], document: Path, feature: str = "`vocab` and `prefix`"
) -> dict:
    test = {
        "key": "rdfa1.1/0001",
        "version": "rdfa1.1",
        "num": "0001",
        "description": "a | test",
        "option": None,
        "expected": True,
        "path": str(document),
        "feature": feature,
        "results": dict(passed),
        "passed": dict(passed),
        "names_a_subject": True,
        "unnamed": {reader: True for reader in board.READERS},
    }
    return {"tests": [test], "extruct": "0.18.0", "rdflib": "7.6.0", "sluicer": "0"}


def _page(tmp_path: Path, html: str) -> Path:
    path = tmp_path / "0001.html"
    path.write_text(html, encoding="utf-8")
    return path


def test_the_scoreboard_counts_what_the_run_found(tmp_path):
    page = _page(tmp_path, '<p typeof="Person"><span property="name">A</span></p>')
    run = _run({"sluicer": False, "compat": True, "extruct": False}, page)
    text = board.scoreboard(run, "abc1234", "2026-09-25")
    assert "| RDFa 1.1 | 1 | 0 | 1 | 0 |" in text
    assert "passes 1 extruct fails: 0001 (RDFa 1.1)" in text
    assert "1 of the 1 runs ask for a subject by its address" in text
    # A pipe in a description would split its row.
    assert "a \\| test" in text


def test_a_loss_is_filed_under_what_the_reader_leaves_out(tmp_path):
    lost = {"sluicer": False, "compat": True, "extruct": True}
    typed = _page(tmp_path, '<p typeof="Event"><time property="startDate">9</time>')
    (test,) = _run(lost, typed, "`<time>`")["tests"]
    assert board.why_sluicer_fails(test) == "typed literals are not read"
    (test,) = _run(lost, typed)["tests"]
    assert board.why_sluicer_fails(test) == "records name no subject"
    untyped = _page(tmp_path, '<p property="dc:title">A title</p>')
    (test,) = _run(lost, untyped)["tests"]
    assert board.why_sluicer_fails(test) == "no `typeof`, so no record"
