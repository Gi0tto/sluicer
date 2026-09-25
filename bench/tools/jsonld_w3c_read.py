"""A reader's JSON-LD answer on every HTML page of the W3C JSON-LD test suite.

    python jsonld_w3c_read.py TOOL TESTS OUT

Run by ``bench/w3c_jsonld.py``, Sluicer's readers in an environment holding
this checkout, installed editable, extruct in one holding exactly
``bench/requirements/extruct.txt``. Each reader is given the page's bytes and
its address, as every scoreboard gives them, and nothing of the test's
options: a reader has none. What it answers, or raises, is written as it is.

- ``sluicer``: the JSON-LD reader, ``sluicer.declared.jsonld.read_jsonld``,
  on the page as ``sluicer.document.load`` parses it -- what the records and
  the summary are made from.
- ``sluicer.compat.extruct``: ``extract(html, base_url=url,
  syntaxes=["json-ld"])``, extruct's interface.
- ``extruct``: the same call to extruct itself.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _reader(tool: str) -> tuple[Callable[[bytes, str], Any], str]:
    if tool == "sluicer":
        from sluicer.declared.jsonld import read_jsonld
        from sluicer.document import load

        return (lambda html, url: read_jsonld(load(html, url=url))), "sluicer"
    if tool == "sluicer.compat.extruct":
        from sluicer.compat import extruct as compat

        def compat_read(html: bytes, url: str) -> Any:
            return compat.extract(html, base_url=url, syntaxes=["json-ld"])["json-ld"]

        return compat_read, "sluicer"
    import extruct

    def extruct_read(html: bytes, url: str) -> Any:
        return extruct.extract(html, base_url=url, syntaxes=["json-ld"])["json-ld"]

    return extruct_read, "extruct"


def main(tool: str, tests_path: str, out_path: str) -> None:
    read, distribution = _reader(tool)
    tests = json.loads(Path(tests_path).read_text(encoding="utf-8"))
    answers: dict[str, Any] = {}
    for test in tests:
        html = Path(test["path"]).read_bytes()
        try:
            # As JSON carries it: Sluicer's nodes are dicts that know their place.
            answers[test["id"]] = {
                "answer": json.loads(json.dumps(read(html, test["url"])))
            }
        except Exception as raised:  # noqa: BLE001 -- what a reader raises is its answer
            answers[test["id"]] = {"error": f"{type(raised).__name__}: {raised}"[:300]}
    Path(out_path).write_text(
        json.dumps(
            {
                "tool": tool,
                "version": importlib.metadata.version(distribution),
                "answers": answers,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{tool}: {len(answers)} pages")


if __name__ == "__main__":
    main(*sys.argv[1:4])
