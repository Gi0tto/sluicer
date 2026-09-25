"""The W3C JSON-LD suite's HTML tests are scored by the suite's own rules
(``bench/PREREG.md``, "The W3C JSON-LD tests in HTML").

The comparison is the suite README's "JSON-LD object comparison"; a reader
passes a negative test by refusing; and every failure is given the first
reason that holds. The harness is not in the sdist: without it, this skips.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
SCORER = BENCH / "tools" / "jsonld_w3c_score.py"
if not SCORER.exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
spec = importlib.util.spec_from_file_location("jsonld_w3c_score", SCORER)
assert spec is not None and spec.loader is not None
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)

EXPAND = ["jld:PositiveEvaluationTest", "jld:ExpandTest", "jld:HtmlTest"]
REFUSE = ["jld:NegativeEvaluationTest", "jld:ExpandTest", "jld:HtmlTest"]
TWO = (
    '<html><head><script type="application/ld+json">{"a": 1}</script>'
    '<script type="application/ld+json">[{"b": 2}, {"c": 3}]</script></head></html>'
)


def test_arrays_compare_in_any_order_but_a_list_s():
    assert score.same([{"a": 1}, {"b": 2}], [{"b": 2}, {"a": 1}])
    assert not score.same({"@list": [1, 2]}, {"@list": [2, 1]})
    assert score.same({"x": {"@list": [1, 2]}}, {"x": {"@list": [1, 2]}})
    # One item may not stand for two.
    assert not score.same([{"a": 1}, {"a": 1}], [{"a": 1}, {"b": 2}])


def test_values_compare_strictly_and_language_tags_in_any_case():
    assert not score.same({"n": 3}, {"n": "3"})
    assert not score.same({"n": 1}, {"n": True})
    assert score.same({"@language": "en-US"}, {"@language": "en-us"})


def test_a_reader_passes_a_negative_test_by_refusing():
    test = {"@id": "#t", "@type": REFUSE, "input": "html/x.html"}
    run = pytest.fail  # never processed
    assert score.judge_reader(test, {"answer": []}, run, None) == (
        True,
        "answered nothing",
    )
    assert score.judge_reader(test, {"error": "JSONDecodeError: x"}, run, None) == (
        True,
        "raised JSONDecodeError",
    )
    assert score.judge_reader(test, {"answer": [{"a": 1}]}, run, None)[0] is False


def test_a_reader_that_raises_on_a_positive_test_fails_it():
    test = {"@id": "#t", "@type": EXPAND, "input": "html/x.html"}
    assert (
        score.judge_reader(test, {"error": "ValueError: no"}, pytest.fail, [])[0]
        is False
    )


def test_the_first_reason_that_holds_is_given():
    first = {"@id": "#t", "@type": EXPAND, "input": "html/x.html", "option": {}}
    reason, said = score.why(first, TWO, [{"a": 1}, {"b": 2}, {"c": 3}])
    assert reason == "first" and "the first of the page's 2 scripts" in said
    targeted = {**first, "input": "html/x.html#second"}
    assert score.why(targeted, TWO, [])[0] == "fragment"
    every = {**first, "option": {"extractAllScripts": True}}
    reason, said = score.why(every, TWO, [{"a": 1}, {"b": 2}])
    assert reason == "json" and "2 values where the scripts hold 3" in said
    refused = {**every, "@type": REFUSE, "expectErrorCode": "invalid script element"}
    reason, said = score.why(refused, TWO, [{"a": 1}])
    assert reason == "refuse" and said.endswith("answered 1 value.")


def test_a_graph_answered_as_loose_nodes_is_named():
    page = (
        '<script type="application/ld+json">{"@context": {"ex": "http://e/"},'
        ' "@graph": [{"ex:a": 1}, {"ex:b": 2}]}</script>'
    )
    test = {
        "@id": "#t",
        "@type": EXPAND,
        "input": "html/x.html",
        "option": {"extractAllScripts": True},
    }
    assert score.why(test, page, [{"ex:a": 1}, {"ex:b": 2}])[0] == "graph"


def test_a_script_that_is_not_json_is_not_part_of_what_the_page_holds():
    page = (
        '<script type="application/ld+json"><!-- {"a": 1} --></script>'
        '<script type="application/LD+JSON; charset=utf-8">{"b": 2}</script>'
    )
    assert [script["json"] for script in score.scripts(page)] == [None, {"b": 2}]


def test_the_results_table_has_a_cell_for_every_column():
    pytest.importorskip("dateutil")
    import sys

    sys.path.insert(0, str(BENCH))
    import w3c_jsonld

    readers = ("pyld", *w3c_jsonld.READERS)
    scored = {
        "readers": {who: {"version": "1"} for who in readers},
        "tests": [
            {
                "kind": kind,
                "negative": False,
                "outcomes": {who: {"passed": True} for who in readers},
            }
            for kind in w3c_jsonld.KINDS
        ],
    }
    lines = w3c_jsonld._table(scored)
    assert len({line.count("|") for line in lines}) == 1, lines[:2]
