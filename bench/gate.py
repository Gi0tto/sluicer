# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Fail when Sluicer does worse on a scoreboard than the floors say it did.

    uv run bench/gate.py                     # check every scoreboard in the cache
    uv run bench/gate.py --require           # ... and fail if one has no results
    uv run bench/gate.py --raise             # write the floors up to today's numbers
    uv run bench/gate.py --raise --allow-regression   # ... down too, on purpose

Each scoreboard's own run leaves Sluicer's answers in ``bench/cache/``; this
reads them, scores them with the same code the scoreboards use, and compares
with ``bench/floors.json``: a hit rate or a share right when answering below
its floor, or more inventions than its ceiling, is a regression. Floors only
rise unless ``--allow-regression`` is given, as trafilatura and htmldate hold
theirs; lowering one is a decision a commit has to say, never a side effect.
Nothing here downloads or runs a tool: a scoreboard's own script does that.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import score  # noqa: E402

CACHE = HERE / "cache"
FLOORS = HERE / "floors.json"

# The title, author and date scoreboards: Sluicer's answers, and the labels.
LABELLED = {
    "wcxb": ("results/sluicer.json", "pages.json"),
    "served": ("realweb/results/served/sluicer.json", "realweb/served.json"),
    "news": ("fundus/results/sluicer.json", "fundus/pages.json"),
    "evaldata": ("evaldata/results/sluicer.json", "evaldata/labelled.json"),
}
PRODUCTS = (
    "products/product-extraction-benchmark-cba97d7a8d42aeefd4021bc15d482f297faceaa3"
    "/metrics-with-sluicer.json"
)


def measured() -> tuple[dict[str, dict[str, float]], list[str]]:
    """Today's numbers per scoreboard, and the scoreboards with no results."""
    numbers: dict[str, dict[str, float]] = {}
    missing: list[str] = []
    for board, (answers, labels) in LABELLED.items():
        if not (CACHE / answers).exists() or not (CACHE / labels).exists():
            missing.append(board)
            continue
        rows = _json(answers)["results"]
        pages = {page["id"]: page for page in _json(labels)}
        counts = score.tally(score.outcomes(rows, pages), pages)
        for field, tally in counts.items():
            numbers[f"{board}.{field}.hit"] = round(score.hit_rate(tally), 3)
            right = score.right_when_answering(tally)
            numbers[f"{board}.{field}.right"] = round(right, 3)
            numbers[f"{board}.{field}.inventions"] = tally["invention"]
    if (CACHE / PRODUCTS).exists():
        metrics = json.loads((CACHE / PRODUCTS).read_text(encoding="utf-8"))["sluicer"]
        for attribute in ("price", "sku", "availability"):
            numbers[f"products.{attribute}.f1"] = round(metrics[attribute]["f1"], 3)
    else:
        missing.append("products")
    swde = _swde()
    if swde:
        numbers.update(swde)
    else:
        missing.append("swde")
    return numbers, missing


def _json(relative: str) -> Any:
    return json.loads((CACHE / relative).read_text(encoding="utf-8"))


def _swde() -> dict[str, float]:
    """SWDE's mean F1 per half, and its silent wrong answers, from its cache."""
    results = CACHE / "swde" / "results" / "sluicer.json"
    if not results.exists():
        return {}
    spec = importlib.util.spec_from_file_location("swde", HERE / "swde.py")
    assert spec and spec.loader
    swde = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(swde)
    sites = json.loads((CACHE / "swde" / "sites.json").read_text(encoding="utf-8"))
    truth = json.loads((CACHE / "swde" / "labels.json").read_text(encoding="utf-8"))
    data = json.loads(results.read_text(encoding="utf-8"))["sites"]
    out: dict[str, float] = {}
    for half in ("development", "held-out"):
        f1: list[float] = []
        silent: Counter[str] = Counter()
        for site in (s for s in sites if swde.half(s["id"]) == half):
            counts = swde.outcomes(site, truth[site["id"]], data[site["id"]])
            for tally in counts.values():
                f1.append(swde.metrics(tally)["f1"])
                silent.update(
                    {k: v for k, v in tally.items() if k in ("wrong", "invented")}
                )
        out[f"swde.{half}.f1"] = round(statistics.fmean(f1), 3)
        out[f"swde.{half}.silent_wrong"] = sum(silent.values())
    return out


def worse(name: str, today: float, floor: float) -> bool:
    """Counts of what went wrong have a ceiling; every other number a floor."""
    if name.endswith((".inventions", ".silent_wrong")):
        return today > floor
    return today < floor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--require", action="store_true")
    parser.add_argument("--raise", dest="raise_", action="store_true")
    parser.add_argument("--allow-regression", action="store_true")
    args = parser.parse_args()
    numbers, missing = measured()
    floors: dict[str, Any] = (
        json.loads(FLOORS.read_text(encoding="utf-8")) if FLOORS.exists() else {}
    )
    regressions = [
        f"{name}: {numbers[name]} against {floor}"
        for name, floor in sorted(floors.items())
        if name in numbers and worse(name, numbers[name], floor)
    ]
    if args.raise_:
        for name, today in numbers.items():
            lowers = name in floors and worse(name, today, floors[name])
            if name not in floors or args.allow_regression or not lowers:
                floors[name] = today
        text = json.dumps(floors, indent=1, sort_keys=True) + "\n"
        FLOORS.write_text(text, encoding="utf-8")
        print(f"wrote {FLOORS.relative_to(HERE.parent)}: {len(floors)} floors")
        if regressions and not args.allow_regression:
            print("kept, not lowered:\n  " + "\n  ".join(regressions))
            raise SystemExit(1)
        return
    for board in missing:
        print(f"no results for {board}: run its scoreboard first")
    unmeasured = sorted(name for name in floors if name not in numbers)
    if regressions:
        print("regressions:\n  " + "\n  ".join(regressions))
    held = len(floors) - len(unmeasured) - len(regressions)
    print(f"{held} of {len(floors)} floors held")
    if regressions or (args.require and missing):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
