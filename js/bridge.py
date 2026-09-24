"""The calls the JavaScript package makes into Sluicer, each answering in JSON.

Run by ``index.js`` inside Pyodide, after the wheel is installed. Each call
takes the page (or pages) as they came from JavaScript and its options as one
JSON text, which keeps JavaScript's ``null`` and ``undefined`` out of the
conversion. Each returns one JSON text: ``{"ok": answer}``, or
``{"error": {"type", "message"}}`` when Sluicer raised, so JavaScript gets the
Python exception's name and words rather than a Pyodide traceback. The answers
are the dataclasses the Python package returns, through
``dataclasses.asdict``: the same fields, under the same names, as the JSON
``sluicer extract`` prints.
"""

import json
import sys
from dataclasses import asdict

import lxml

import sluicer
from sluicer.extractor import Extractor, compile_extractor, run_extractor


def _page(html):
    # A JavaScript string arrives as a str. A Uint8Array arrives as a proxy and
    # is read as bytes, so the page's own charset is honoured, as in Python.
    return html if isinstance(html, str) else html.to_bytes()


def _answer(call):
    try:
        return json.dumps({"ok": call()}, ensure_ascii=False)
    # Every error is handed to JavaScript as it was raised, whatever its kind.
    except Exception as error:  # noqa: BLE001
        return json.dumps(
            {"error": {"type": type(error).__name__, "message": str(error)}},
            ensure_ascii=False,
        )


def extract(html, options):
    def call():
        given = json.loads(options)
        return asdict(
            sluicer.extract(
                _page(html),
                url=given.get("url"),
                induce=bool(given.get("induce")),
                visible=bool(given.get("visible")),
                headers=given.get("headers"),
            )
        )

    return _answer(call)


def to_markdown(html, options):
    return _answer(
        lambda: sluicer.to_markdown(_page(html), url=json.loads(options).get("url"))
    )


def compile(pages, options):
    def call():
        given = json.loads(options)
        urls = given.get("urls") or []
        found = [
            (_page(html), urls[n] if n < len(urls) else None)
            for n, html in enumerate(pages)
        ]
        extractor = compile_extractor(
            found,
            listing=given.get("listing"),
            names=given.get("names"),
            want=given.get("want"),
        )
        return json.loads(extractor.to_json())

    return _answer(call)


def run(extractor, html, options):
    def call():
        replayed = run_extractor(
            Extractor.from_json(extractor), _page(html), json.loads(options).get("url")
        )
        return asdict(replayed)

    return _answer(call)


def about():
    return json.dumps(
        {
            "sluicer": sluicer.__version__,
            "python": sys.version.split()[0],
            "lxml": lxml.__version__,
        }
    )
