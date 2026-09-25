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
reads them and scores them with the same code the scoreboards use.
``bench/floors.json`` holds Sluicer's numbers when the floors were written, and
``bench/floors-pages.json`` every page's outcome they were computed from, the
baseline. A floor is breached, as ``bench/PREREG.md`` fixes it under "What
counts as worse", when either holds:

1. the paired comparison of today's outcomes with the baseline's, page by page
   (site by site for SWDE), calls today worse; or
2. the number is past the floor by more than its tolerance: a rate or an F1
   more than 0.010 below it, a count of what went wrong above it by more than
   1% of what it is counted over.

A number past its floor, within the tolerance and not called worse, is held
within noise. Floors only rise unless ``--allow-regression`` is given, and a
scoreboard's baseline is rewritten only when every one of its numbers is at or
above its floor, so a drop within the tolerance is compared with the outcomes
before it, not with itself. Nothing here downloads or runs a tool.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import types
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import score  # noqa: E402
import stats  # noqa: E402
import zyte  # noqa: E402

CACHE = HERE / "cache"
FLOORS = HERE / "floors.json"
BASELINE = HERE / "floors-pages.json"
TOLERANCE = 0.010
COUNT_TOLERANCE = 0.01

# The title, author and date scoreboards: Sluicer's answers, and the labels.
LABELLED = {
    "wcxb": ("results/sluicer.json", "pages.json"),
    "served": ("realweb/results/served/sluicer.json", "realweb/served.json"),
    "news": ("fundus/results/sluicer.json", "fundus/pages.json"),
    "evaldata": ("evaldata/results/sluicer.json", "evaldata/labelled.json"),
}
PRODUCTS = ("price", "sku", "availability")
HALVES = ("development", "held-out")
# What a count of what went wrong is: a ceiling, not a floor.
COUNTS = (".inventions", ".silent_wrong")


def _json(relative: str) -> Any:
    return json.loads((CACHE / relative).read_text(encoding="utf-8"))


def _swde_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("swde", HERE / "swde.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- today's outcomes ------------------------------------------------------------


def outcomes() -> tuple[dict[str, Any], list[str]]:
    """Every page's outcome per scoreboard, and the scoreboards with none."""
    found: dict[str, Any] = {}
    missing: list[str] = []
    for board, (answers, labels) in LABELLED.items():
        if not (CACHE / answers).exists() or not (CACHE / labels).exists():
            missing.append(board)
            continue
        rows = _json(answers)["results"]
        pages = {page["id"]: page for page in _json(labels)}
        found[board] = score.outcomes(rows, pages)
    sluicer = zyte.BENCH / "dataset" / "output" / "sluicer.json"
    if sluicer.exists() and zyte.EVALUATE.exists():
        evaluate = zyte.evaluator()
        truth = json.loads(
            (zyte.BENCH / "dataset" / "ground-truth.json").read_text(encoding="utf-8")
        )
        predicted = json.loads(sluicer.read_text(encoding="utf-8"))
        per_attribute = {
            attribute: zyte.counts(truth, predicted, attribute, evaluate)
            for attribute in PRODUCTS
        }
        found["products"] = {
            key: {attribute: per_attribute[attribute][n] for attribute in PRODUCTS}
            for n, key in enumerate(sorted(truth))
        }
    else:
        missing.append("products")
    swde = _swde_outcomes()
    if swde:
        found["swde"] = swde
    else:
        missing.append("swde")
    return found, missing


def _swde_outcomes() -> dict[tuple[str, str], Counter[str]]:
    """Every site-attribute's outcomes on SWDE, from its cache."""
    results = CACHE / "swde" / "results" / "sluicer.json"
    if not results.exists():
        return {}
    swde = _swde_module()
    sites = json.loads((CACHE / "swde" / "sites.json").read_text(encoding="utf-8"))
    truth = json.loads((CACHE / "swde" / "labels.json").read_text(encoding="utf-8"))
    data = json.loads(results.read_text(encoding="utf-8"))["sites"]
    found: dict[tuple[str, str], Counter[str]] = {}
    for site in sites:
        for attribute, tally in swde.outcomes(
            site, truth[site["id"]], data[site["id"]]
        ).items():
            found[(site["id"], attribute)] = tally
    return found


# --- the numbers, from outcomes ----------------------------------------------------


def labelled_numbers(board: str, per_page: dict[str, dict[str, str]]) -> dict:
    """A title, author and date scoreboard's floors' numbers."""
    numbers: dict[str, float] = {}
    counts: dict[str, Counter[str]] = {field: Counter() for field in score.FIELDS}
    for fields in per_page.values():
        for field, result in fields.items():
            counts[field][result] += 1
    for field, tally in counts.items():
        numbers[f"{board}.{field}.hit"] = round(score.hit_rate(tally), 3)
        numbers[f"{board}.{field}.right"] = round(score.right_when_answering(tally), 3)
        numbers[f"{board}.{field}.inventions"] = tally["invention"]
    return numbers


def _swde_keys(per: dict[tuple[str, str], Counter[str]], half: str) -> list:
    swde = _swde_module()
    return sorted(key for key in per if swde.half(key[0]) == half)


def _silent_wrong(tally: Counter[str]) -> int:
    return sum(v for k, v in tally.items() if k in ("wrong", "invented"))


def numbers(board: str, found: Any) -> dict[str, float]:
    """A scoreboard's floors' numbers, computed from its outcomes."""
    if board in LABELLED:
        return labelled_numbers(board, found)
    if board == "products":
        evaluate = zyte.evaluator()
        return {
            f"products.{attribute}.f1": round(
                zyte.f1(
                    [
                        sum(page[attribute][i] for page in found.values())
                        for i in range(3)
                    ],
                    evaluate,
                ),
                3,
            )
            for attribute in PRODUCTS
        }
    swde = _swde_module()
    out: dict[str, float] = {}
    for half in HALVES:
        keys = _swde_keys(found, half)
        out[f"swde.{half}.f1"] = round(swde._mean_f1(found, keys), 3)
        out[f"swde.{half}.silent_wrong"] = sum(_silent_wrong(found[k]) for k in keys)
    return out


# --- today against the baseline -------------------------------------------------


def labelled_comparisons(
    board: str,
    today: dict[str, dict[str, str]],
    base: dict[str, dict[str, str]],
    only: str | None = None,
) -> dict[str, stats.Comparison]:
    """Today minus the baseline, on each of a scoreboard's numbers (or on
    ``only``), paired page by page. A count of inventions is compared the
    other way round, the baseline's minus today's, so that worse still means
    worse."""
    found = {}
    ids = sorted(set(today) & set(base))
    for field in score.FIELDS:
        for measure in ("hit", "right"):
            name = f"{board}.{field}.{measure}"
            if only in (None, name):
                found[name] = score.paired(today, base, field, measure)
        name = f"{board}.{field}.inventions"
        if only not in (None, name):
            continue
        found[name] = stats.compare(
            [
                [int(base[i][field] == "invention") for i in ids],
                [int(today[i][field] == "invention") for i in ids],
            ],
            lambda s: s[0] - s[1],
        )
    return found


def comparisons(board: str, today: Any, base: Any) -> dict[str, stats.Comparison]:
    """Today against the baseline on every number of ``board``."""
    if board in LABELLED:
        return labelled_comparisons(board, today, base)
    if board == "products":
        evaluate = zyte.evaluator()
        ids = sorted(set(today) & set(base))
        return {
            f"products.{attribute}.f1": zyte.compare(
                [today[i][attribute] for i in ids],
                [base[i][attribute] for i in ids],
                evaluate,
            )
            for attribute in PRODUCTS
        }
    swde = _swde_module()
    found = {}
    for half in HALVES:
        keys = [key for key in _swde_keys(today, half) if key in base]
        found[f"swde.{half}.f1"] = swde.f1_difference(today, base, keys)
        sites = sorted({site for site, _ in keys})

        def per_site(per: dict, site: str, keys: list = keys) -> int:
            return sum(_silent_wrong(per[k]) for k in keys if k[0] == site)

        found[f"swde.{half}.silent_wrong"] = stats.compare(
            [
                [per_site(base, site) for site in sites],
                [per_site(today, site) for site in sites],
            ],
            lambda s: s[0] - s[1],
        )
    return found


def counted_over(board: str, found: Any, name: str) -> int:
    """What a count of what went wrong is counted over: the pages scored, or
    for SWDE the labelled page-attributes of that half."""
    if board != "swde":
        return len(found)
    swde = _swde_module()
    half = name.split(".")[1]
    return sum(swde.metrics_counts(found[key])[2] for key in _swde_keys(found, half))


@dataclass(frozen=True)
class Judged:
    name: str
    today: float
    floor: float
    comparison: stats.Comparison | None
    status: str

    @property
    def breached(self) -> bool:
        return self.status.startswith("breached")


def check(
    name: str,
    today: float,
    floor: float,
    comparison: stats.Comparison | None,
    over: int,
) -> Judged:
    """Held, held within noise, or breached, and why, by PREREG's two rules."""
    if name.endswith(COUNTS):
        below = today > floor
        past = today - floor > COUNT_TOLERANCE * over
        tolerance = f"more than 1% of {over:,} above its ceiling"
    else:
        below = today < floor
        past = round(floor - today, 6) > TOLERANCE
        tolerance = f"more than {TOLERANCE:.3f} below its floor, past its tolerance"
    reasons = []
    if comparison is not None and comparison.verdict == "worse":
        reasons.append("called worse than the baseline by the paired comparison")
    if past:
        reasons.append(tolerance)
    if reasons:
        status = "breached: " + "; ".join(reasons)
    elif below:
        status = "held within noise"
    else:
        status = "held"
    return Judged(name, today, floor, comparison, status)


def rebaseline(
    board: str,
    today: dict[str, float],
    floors: dict[str, float],
    allow_regression: bool,
) -> bool:
    """Whether ``--raise`` rewrites ``board``'s baseline: only when every one
    of its numbers is at or above its floor, or on purpose."""
    if allow_regression:
        return True
    return all(
        not (value > floors[name] if name.endswith(COUNTS) else value < floors[name])
        for name, value in today.items()
        if name.startswith(f"{board}.") and name in floors
    )


# --- the baseline on disk ---------------------------------------------------------


def write_baseline(path: Path, found: dict[str, Any]) -> None:
    """Every page's outcome, per scoreboard; SWDE's per site, then attribute."""
    plain: dict[str, Any] = {}
    for board, per in sorted(found.items()):
        if board == "swde":
            sites: dict[str, dict[str, dict[str, int]]] = {}
            for (site, attribute), tally in sorted(per.items()):
                sites.setdefault(site, {})[attribute] = dict(sorted(tally.items()))
            plain[board] = sites
        elif board == "products":
            plain[board] = {
                page: {
                    attribute: list(value) for attribute, value in sorted(row.items())
                }
                for page, row in sorted(per.items())
            }
        else:
            plain[board] = {page: per[page] for page in sorted(per)}
    path.write_text(
        json.dumps(plain, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_baseline(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    plain = json.loads(path.read_text(encoding="utf-8"))
    found: dict[str, Any] = {}
    for board, per in plain.items():
        if board == "swde":
            found[board] = {
                (site, attribute): Counter(tally)
                for site, attributes in per.items()
                for attribute, tally in attributes.items()
            }
        elif board == "products":
            found[board] = {
                page: {attribute: tuple(value) for attribute, value in row.items()}
                for page, row in per.items()
            }
        else:
            found[board] = per
    return found


# --- the run ----------------------------------------------------------------------


def _board(name: str) -> str:
    return name.split(".", 1)[0]


def _said(judged: Judged) -> str:
    compared = (
        f", today minus baseline {stats.difference(judged.comparison)}, "
        f"{judged.comparison.verdict}"
        if judged.comparison is not None
        else ", no baseline to pair with"
    )
    return (
        f"{judged.name}: {judged.today} against {judged.floor}{compared}: "
        f"{judged.status}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--require", action="store_true")
    parser.add_argument("--raise", dest="raise_", action="store_true")
    parser.add_argument("--allow-regression", action="store_true")
    args = parser.parse_args()
    today, missing = outcomes()
    baseline = read_baseline(BASELINE)
    floors: dict[str, Any] = (
        json.loads(FLOORS.read_text(encoding="utf-8")) if FLOORS.exists() else {}
    )
    measured: dict[str, float] = {}
    judged: list[Judged] = []
    for board, found in today.items():
        mine = numbers(board, found)
        measured.update(mine)
        base = baseline.get(board)
        if base is not None and set(base) != set(found):
            print(
                f"{board}: the baseline was written on other pages; its numbers are "
                "checked against their floors' tolerance only"
            )
            base = None
        paired = comparisons(board, found, base) if base is not None else {}
        for name, value in mine.items():
            if name in floors:
                judged.append(
                    check(
                        name,
                        value,
                        floors[name],
                        paired.get(name),
                        counted_over(board, found, name),
                    )
                )
    breached = [j for j in judged if j.breached]
    noise = [j for j in judged if j.status == "held within noise"]
    if args.raise_:
        for name, value in measured.items():
            lowers = name in floors and (
                value > floors[name] if name.endswith(COUNTS) else value < floors[name]
            )
            if name not in floors or args.allow_regression or not lowers:
                floors[name] = value
        text = json.dumps(floors, indent=1, sort_keys=True) + "\n"
        FLOORS.write_text(text, encoding="utf-8")
        print(f"wrote {FLOORS.relative_to(HERE.parent)}: {len(floors)} floors")
        rewritten = {
            board: found
            for board, found in today.items()
            if rebaseline(board, measured, floors, args.allow_regression)
        }
        kept = {b: v for b, v in baseline.items() if b not in rewritten}
        write_baseline(BASELINE, {**kept, **rewritten})
        print(
            f"wrote {BASELINE.relative_to(HERE.parent)}: the baseline of "
            + ", ".join(sorted(rewritten))
        )
        if breached and not args.allow_regression:
            print("kept, not lowered:\n  " + "\n  ".join(map(_said, breached)))
            raise SystemExit(1)
        return
    for board in missing:
        print(f"no results for {board}: run its scoreboard first")
    if noise:
        print("held within noise:\n  " + "\n  ".join(map(_said, noise)))
    if breached:
        print("regressions:\n  " + "\n  ".join(map(_said, breached)))
    unmeasured = sorted(name for name in floors if name not in measured)
    held = len(floors) - len(unmeasured) - len(breached)
    print(f"{held} of {len(floors)} floors held")
    if breached or (args.require and missing):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
