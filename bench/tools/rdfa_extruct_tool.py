"""extruct's RDFa over the W3C RDFa test suite, for ``bench/rdfa_conformance.py``.

Run in an environment holding exactly ``bench/requirements/extruct.txt`` and
nothing of sluicer. Every test document gets the call a caller of extruct
writes, ``extract(html, base_url=url, syntaxes=["rdfa"])``, and what it
answers, or what it raised, is recorded as it came.
"""

from __future__ import annotations

import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any

import extruct


def main(tests_path: str, out_path: str) -> None:
    tests = json.loads(Path(tests_path).read_text(encoding="utf-8"))
    answers: dict[str, Any] = {}
    for test in tests:
        html = Path(test["path"]).read_bytes()
        try:
            found = extruct.extract(html, base_url=test["url"], syntaxes=["rdfa"])
            answers[test["key"]] = found["rdfa"]
        except Exception as error:  # noqa: BLE001 -- what extruct raised is the answer
            answers[test["key"]] = {"__error__": f"{type(error).__name__}: {error}"}
    version = importlib.metadata.version("extruct")
    Path(out_path).write_text(
        json.dumps({"version": version, "answers": answers}), encoding="utf-8"
    )
    print(f"extruct {version}: {len(answers)} test documents")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
