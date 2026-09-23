"""extruct itself over the comparison's pages, for ``bench/extruct_compat.py``.

Run in an environment holding exactly ``bench/requirements/extruct.txt`` and
nothing of sluicer. For every page it records what extruct answers for each
syntax asked alone, raising included, what the default call answers or raises,
and each syntax in uniform mode. Only the default call is timed.
"""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import sys
import time
from pathlib import Path
from typing import Any

import extruct

UNIFORM = ("microdata", "opengraph", "microformat", "dublincore")


def failure(error: Exception) -> dict[str, str]:
    return {"__error__": f"{type(error).__name__}: {str(error)[:300]}"}


def attempt(html: bytes, url: str | None, **options: Any) -> Any:
    try:
        return extruct.extract(html, base_url=url, **options)
    except Exception as error:  # noqa: BLE001 -- what extruct raised is the answer
        return failure(error)


def main(pages_path: str, out_path: str) -> None:
    pages = json.loads(Path(pages_path).read_text())
    results: dict[str, Any] = {}
    seconds = 0.0
    for page in pages:
        data = Path(page["path"]).read_bytes()
        html = gzip.decompress(data) if page["path"].endswith(".gz") else data
        url = page["url"]
        found: dict[str, Any] = {"syntax": {}, "uniform": {}}
        for syntax in extruct.SYNTAXES:
            answer = attempt(html, url, syntaxes=[syntax])
            found["syntax"][syntax] = answer.get(syntax, answer)
        for syntax in UNIFORM:
            answer = attempt(html, url, syntaxes=[syntax], uniform=True)
            found["uniform"][syntax] = answer.get(syntax, answer)
        started = time.perf_counter()
        whole = attempt(html, url)
        seconds += time.perf_counter() - started
        found["default"] = whole.get("__error__", "ok")
        results[page["key"]] = found
    version = importlib.metadata.version("extruct")
    Path(out_path).write_text(
        json.dumps({"version": version, "seconds": seconds, "pages": results})
    )
    print(f"extruct {version}: {len(results)} pages, {seconds:.1f} s")


if __name__ == "__main__":
    main(*sys.argv[1:3])
