"""Score readers of JSON-LD in HTML against the W3C JSON-LD test suite's HTML tests.

    python jsonld_w3c_score.py SUITE ANSWERS... OUT

Run by ``bench/w3c_jsonld.py`` in an environment holding exactly
``bench/requirements/pyld.txt``. SUITE is the suite's ``tests`` directory at
the pinned commit; each ANSWERS file is one reader's answers, as
``jsonld_w3c_read.py`` writes them.

The HTML tests (``html-manifest.jsonld``) say what a JSON-LD *processor* must
make of a page: which scripts it extracts, the first, the one a fragment
names, or all; which script text is an error; which base IRI the page sets;
and the result of expanding, compacting, flattening or turning it into RDF. A
reader of JSON-LD -- Sluicer's, extruct's -- is not a processor: it gives the
JSON the page's scripts hold. So each reader's answer, as it gives it, is
handed to PyLD, a JSON-LD 1.1 processor, as the document to process, with the
test's options and the page's address as its base, and the result is compared
with the suite's expected result by the suite's own rules (its README, "JSON-LD
object comparison"; RDF by dataset isomorphism). What fails is what a reader's
answer does not carry: a script chosen, an error, a base, the scripts' JSON as
they wrote it.

A negative test wants an error. A reader's refusal is an answer of nothing or
a raise: either passes it; an answer fails it. PyLD also reads every page
itself, with the test's options, so the harness is checked by what a
processor does on the same tests.
"""

from __future__ import annotations

import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag

BASE = "https://w3c.github.io/json-ld-api/tests/"
LD_JSON = "application/ld+json"


# --- the suite's comparison ----------------------------------------------------


def _language(key: str) -> bool:
    return key == "@language"


def same(a: Any, b: Any, ordered: bool = False) -> bool:
    """JSON-LD object comparison, as the suite's README writes it: objects
    member by member, arrays without regard to order except a ``@list``'s,
    values by strict equality, language tags case-insensitively."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return False
        for key in a:
            if _language(key) and isinstance(a[key], str) and isinstance(b[key], str):
                if a[key].lower() != b[key].lower():
                    return False
            elif not same(a[key], b[key], ordered=key == "@list"):
                return False
        return True
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        if ordered:
            return all(same(x, y) for x, y in zip(a, b, strict=True))
        left = list(b)
        for item in a:
            match = next((i for i, other in enumerate(left) if same(item, other)), None)
            if match is None:
                return False
            left.pop(match)
        return True
    return type(a) is type(b) and a == b


def _blank(value: Any) -> Any:
    """``value`` with every blank node label written the same."""
    if isinstance(value, dict):
        return {k: _blank(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank(v) for v in value]
    if isinstance(value, str) and value.startswith("_:"):
        return "_:"
    return value


def _has_blank(value: Any) -> bool:
    return _blank(value) != value


# --- a test ---------------------------------------------------------------------


def kind(test: dict[str, Any]) -> str:
    """``expand``, ``compact``, ``flatten`` or ``toRdf``."""
    for name in ("Expand", "Compact", "Flatten", "ToRDF"):
        if f"jld:{name}Test" in test["@type"]:
            return {"ToRDF": "toRdf"}.get(name, name.lower())
    raise ValueError(f"{test['@id']}: no operation")


def negative(test: dict[str, Any]) -> bool:
    return "jld:NegativeEvaluationTest" in test["@type"]


def scripts(html: str) -> list[dict[str, Any]]:
    """Every ``application/ld+json`` script on the page: its id, and its
    JSON, or None where its text is not JSON."""
    import lxml.html

    found = []
    for script in lxml.html.fromstring(html).iter("script"):
        media = (script.get("type") or "").split(";")[0].strip().lower()
        if media != LD_JSON:
            continue
        text = script.text or ""
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        found.append({"id": script.get("id"), "json": parsed})
    return found


def _as_read(found: list[dict[str, Any]]) -> list[Any]:
    """The scripts' JSON as a reader gives it: each script's value, an
    array's items one by one."""
    read: list[Any] = []
    for script in found:
        value = script["json"]
        if value is None:
            continue
        read.extend(value if isinstance(value, list) else [value])
    return read


def asks(test: dict[str, Any], html: str) -> list[str]:
    """What ``test`` asks that no reader's answer can give, since a reader
    takes no option and reports no base: a script named by fragment, the
    first script alone of several, the page's ``<base href>``."""
    found = []
    if urldefrag(test["input"])[1]:
        found.append("fragment")
    options = test.get("option", {})
    if not options.get("extractAllScripts") and len(scripts(html)) > 1:
        found.append("first")
    if re.search(r"<base\s", html, re.I):
        found.append("base")
    return found


def _values(count: int) -> str:
    return f"{count} value" + ("" if count == 1 else "s")


def why(test: dict[str, Any], html: str, answer: list[Any] | None) -> tuple[str, str]:
    """Why a reader's answer fails ``test``, from what the test asks of the
    page and what the reader gave: the first reason that holds, tried in this
    order -- ``fragment``, ``first``, ``refuse``, ``base``, ``graph``,
    ``json``, ``differs`` (``bench/w3c_jsonld.py`` says what each counts) --
    and a sentence."""
    options = test.get("option", {})
    found = scripts(html)
    _, fragment = urldefrag(test["input"])
    given = len(answer or [])
    if fragment:
        return "fragment", (
            f"The test names the script `#{fragment}`; a reader is given no "
            f"fragment and answers every script ({_values(given)})."
        )
    if not options.get("extractAllScripts") and len(found) > 1 and not negative(test):
        return "first", (
            f"The test wants the first of the page's {len(found)} scripts; the "
            f"reader answers all of them ({_values(given)})."
        )
    if negative(test):
        return "refuse", (
            f"The test wants the error `{test.get('expectErrorCode')}`: the "
            f"script is not JSON-LD as written. The reader mended it and "
            f"answered {_values(given)}."
        )
    if re.search(r"<base\s", html, re.I):
        return "base", (
            "The page's `<base href>` sets the base IRI; a reader's answer does "
            "not carry it, so it is read against the page's address."
        )
    wanted = _as_read(found)
    if answer is not None and not same(answer, wanted):
        if any(_graph_split(value, answer) for value in wanted):
            return "graph", (
                "The reader answers the nodes of a script's `@graph` one by one, "
                "without the script's `@context`, so their terms no longer "
                "expand to what the script says."
            )
        return "json", (
            "The reader's answer is not the JSON the scripts hold: "
            + _first_difference(answer, wanted)
        )
    return "differs", "The result differs from the expected one."


def _graph_split(value: Any, answer: list[Any]) -> bool:
    """Whether ``answer`` holds ``value``'s ``@graph`` nodes as values of
    their own, and not ``value`` itself."""
    if not (isinstance(value, dict) and isinstance(value.get("@graph"), list)):
        return False
    if any(same(value, given) for given in answer):
        return False
    return all(any(same(node, given) for given in answer) for node in value["@graph"])


def _first_difference(answer: list[Any], wanted: list[Any]) -> str:
    """What the first differing value is, briefly."""
    if len(answer) != len(wanted):
        return f"{_values(len(answer))} where the scripts hold {len(wanted)}."
    for got, want in zip(answer, wanted, strict=True):
        if not same(got, want):
            return (
                f"`{json.dumps(got, ensure_ascii=False)[:90]}` for "
                f"`{json.dumps(want, ensure_ascii=False)[:90]}`."
            )
    return "the values differ in order only."


# --- processing -----------------------------------------------------------------


def _loader(suite: Path, pages: dict[str, tuple[str, str]]) -> Any:
    """A document loader that serves the suite from disk: the test's page as
    the test's media type, anything else under the suite as JSON-LD."""

    def load(url: str, options: Any = None) -> dict[str, Any]:
        address, _ = urldefrag(url)
        if address in pages:
            text, media = pages[address]
            # The address as asked, fragment included: it names the script.
            return {
                "contentType": media,
                "contextUrl": None,
                "documentUrl": url,
                "document": text,
            }
        if not address.startswith(BASE):
            raise ValueError(f"not in the suite: {address}")
        path = suite / address[len(BASE) :]
        return {
            "contentType": LD_JSON,
            "contextUrl": None,
            "documentUrl": address,
            "document": json.loads(path.read_text(encoding="utf-8")),
        }

    return load


def _canonical(nquads: str) -> list[str]:
    from pyld import jsonld

    normal = jsonld.normalize(
        nquads,
        {
            "algorithm": "URDNA2015",
            "inputFormat": "application/n-quads",
            "format": "application/n-quads",
        },
    )
    return sorted(line for line in normal.splitlines() if line.strip())


def process(test: dict[str, Any], document: Any, suite: Path, loader: Any) -> Any:
    """``test``'s operation on ``document`` (a reader's answer, or the page's
    address for PyLD to read itself), with the test's options."""
    from pyld import jsonld

    options = test.get("option", {})
    settings: dict[str, Any] = {
        "base": options.get("base", BASE + test["input"]),
        "processingMode": "json-ld-1.1",
        "documentLoader": loader,
    }
    if "extractAllScripts" in options:
        settings["extractAllScripts"] = options["extractAllScripts"]
    operation = kind(test)
    context = (
        json.loads((suite / test["context"]).read_text(encoding="utf-8"))
        if "context" in test
        else None
    )
    if operation == "expand":
        return jsonld.expand(document, settings)
    if operation == "compact":
        return jsonld.compact(document, context, settings)
    if operation == "flatten":
        return jsonld.flatten(document, context, settings)
    return _canonical(
        jsonld.to_rdf(document, {**settings, "format": "application/n-quads"})
    )


def expected(test: dict[str, Any], suite: Path) -> Any:
    text = (suite / test["expect"]).read_text(encoding="utf-8")
    return _canonical(text) if kind(test) == "toRdf" else json.loads(text)


def matches(test: dict[str, Any], result: Any, wanted: Any) -> bool:
    if kind(test) == "toRdf":
        return bool(result == wanted)
    if same(result, wanted):
        return True
    # Blank node labels are the processor's to choose: equal once they are
    # written alike, and the same graph.
    if kind(test) == "flatten" and _has_blank(wanted):
        return same(_blank(result), _blank(wanted)) and _rdf_equal(result, wanted)
    return False


def _rdf_equal(a: Any, b: Any) -> bool:
    from pyld import jsonld

    def quads(value: Any) -> list[str]:
        return _canonical(jsonld.to_rdf(value, {"format": "application/n-quads"}))

    return quads(a) == quads(b)


def judge_reader(
    test: dict[str, Any],
    reply: dict[str, Any],
    run: Any,
    wanted: Any,
) -> tuple[bool, str]:
    """Whether a reader's reply passes ``test``, and what it did.

    ``run`` is the test's operation, given the reader's answer.
    """
    error = reply.get("error")
    answer = reply.get("answer")
    if negative(test):
        if error:
            return True, f"raised {error.split(':')[0]}"
        if not answer:
            return True, "answered nothing"
        return False, "answered"
    if error:
        return False, f"raised {error.split(':')[0]}"
    try:
        result = run(answer or [])
    except Exception as failed:  # noqa: BLE001 -- the processor's refusal is the outcome
        return False, f"the processor refused the answer: {type(failed).__name__}"
    return (True, "matches") if matches(test, result, wanted) else (False, "differs")


def judge_processor(test: dict[str, Any], run: Any, wanted: Any) -> tuple[bool, str]:
    """Whether PyLD, reading the page itself, passes ``test``."""
    try:
        result = run()
    except Exception as failed:  # noqa: BLE001 -- an error is what a negative test wants
        codes = _codes(failed)
        if negative(test):
            wanted_code = test.get("expectErrorCode")
            said = wanted_code if wanted_code in codes else codes[0]
            return wanted_code in codes, f"raised `{said}`"
        return False, f"raised `{codes[0]}`"
    if negative(test):
        return False, "answered"
    return (True, "matches") if matches(test, result, wanted) else (False, "differs")


def _codes(failed: BaseException) -> list[str]:
    """Every error code PyLD raised, the outermost first: turning a document
    into RDF wraps the expansion's error in its own."""
    codes = []
    seen: BaseException | None = failed
    while seen is not None and len(codes) < 10:
        codes.append(str(getattr(seen, "code", None) or type(seen).__name__))
        cause = getattr(seen, "cause", None)
        seen = cause if isinstance(cause, BaseException) else seen.__cause__
    return codes


def main(suite_path: str, *paths: str) -> None:
    suite = Path(suite_path)
    *answer_paths, out_path = paths
    manifest = json.loads((suite / "html-manifest.jsonld").read_text(encoding="utf-8"))
    readers = [json.loads(Path(p).read_text(encoding="utf-8")) for p in answer_paths]
    results: dict[str, Any] = {"tests": [], "readers": {}}
    results["readers"]["pyld"] = {
        "tool": "PyLD",
        "version": importlib.metadata.version("pyld"),
    }
    for reader in readers:
        results["readers"][reader["tool"]] = {
            "tool": reader["tool"],
            "version": reader["version"],
        }
    for test in manifest["sequence"]:
        address, _ = urldefrag(BASE + test["input"])
        html_path = suite / urldefrag(test["input"])[0]
        html = html_path.read_text(encoding="utf-8")
        media = test.get("option", {}).get("contentType", "text/html")
        loader = _loader(suite, {address: (html, media)})
        wanted = None if negative(test) else expected(test, suite)
        row: dict[str, Any] = {
            "id": test["@id"].lstrip("#"),
            "name": test["name"],
            "kind": kind(test),
            "negative": negative(test),
            "asks": asks(test, html),
            "outcomes": {},
        }
        passed, did = judge_processor(
            test,
            lambda test=test, loader=loader: process(
                test, BASE + test["input"], suite, loader
            ),
            wanted,
        )
        row["outcomes"]["pyld"] = {"passed": passed, "did": did}
        for reader in readers:
            reply = reader["answers"][row["id"]]
            passed, did = judge_reader(
                test,
                reply,
                lambda answer, test=test, loader=loader: process(
                    test, answer, suite, loader
                ),
                wanted,
            )
            outcome: dict[str, Any] = {"passed": passed, "did": did}
            if not passed:
                outcome["reason"], outcome["why"] = why(test, html, reply.get("answer"))
            row["outcomes"][reader["tool"]] = outcome
        results["tests"].append(row)
    Path(out_path).write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    print(f"{len(results['tests'])} tests, {len(readers)} readers and PyLD")


if __name__ == "__main__":
    main(sys.argv[1], *sys.argv[2:])
