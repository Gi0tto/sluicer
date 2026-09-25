"""The RDFa test suite's ASK queries over each reader's graph.

Run by ``bench/rdfa_conformance.py`` in an environment holding exactly
``bench/requirements/rdflib.txt``: rdflib parses each answer, written as
expanded JSON-LD, into a graph and evaluates the test's query on it. What
the query answers is recorded, ``true`` or ``false``; an answer rdflib cannot
read, or a reader that raised, is recorded as the error.

Each query is also asked a second time with every subject it names by address
replaced by a variable, the same address by the same variable wherever it
appears: what a reader that names no subject can be asked. That query is the
suite's with names taken out, never with anything put in.
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
import sys
from pathlib import Path
from typing import Any

from rdflib import Graph, URIRef, Variable
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.sparql import Query

# rdflib warns about each literal it cannot convert to a Python value; the
# query compares the lexical forms, which is what the suite asks for.
logging.getLogger("rdflib").setLevel(logging.ERROR)


def unnamed(text: str) -> tuple[Query, bool]:
    """``text`` prepared with its named subjects as variables, and whether it
    named any."""
    query = prepareQuery(text)
    patterns = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if getattr(node, "name", None) == "BGP":
                patterns.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(query.algebra)
    named = sorted(
        {s for bgp in patterns for s, _p, _o in bgp["triples"] if isinstance(s, URIRef)}
    )
    names = {iri: Variable(f"named{n}") for n, iri in enumerate(named)}
    for bgp in patterns:
        bgp["triples"] = [
            (names.get(s, s), p, names.get(o, o)) for s, p, o in bgp["triples"]
        ]
    return query, bool(named)


def ask(answer: Any, query: str | Query) -> bool | str:
    if isinstance(answer, dict) and "__error__" in answer:
        return f"raised {answer['__error__']}"
    graph = Graph()
    try:
        graph.parse(data=json.dumps(answer), format="json-ld")
    except Exception as error:  # noqa: BLE001 -- an unreadable answer is recorded
        return f"unreadable: {type(error).__name__}: {error}"
    return bool(graph.query(query).askAnswer)


def main(tests_path: str, answers_path: str, out_path: str) -> None:
    tests = json.loads(Path(tests_path).read_text(encoding="utf-8"))
    answers = json.loads(Path(answers_path).read_text(encoding="utf-8"))
    queries = {
        test["key"]: Path(test["query"]).read_text(encoding="utf-8") for test in tests
    }
    results = {
        reader: {key: ask(found[key], queries[key]) for key in queries}
        for reader, found in answers.items()
    }
    # Only where the suite expects a match: a query that must fail proves
    # nothing once its names are taken out.
    relaxed = {
        test["key"]: unnamed(queries[test["key"]])
        for test in tests
        if test["expected"] is True
    }
    unnamed_results = {
        reader: {
            key: ask(found[key], query)
            for key, (query, named) in relaxed.items()
            if named
        }
        for reader, found in answers.items()
    }
    Path(out_path).write_text(
        json.dumps(
            {
                "rdflib": importlib.metadata.version("rdflib"),
                "results": results,
                "unnamed": unnamed_results,
                "names_a_subject": sorted(k for k, (_q, n) in relaxed.items() if n),
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
