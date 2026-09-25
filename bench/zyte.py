"""Zyte's product evaluator, page by page, for the paired comparison.

``bench/products.py`` runs Zyte's ``evaluate.py`` unchanged for the numbers it
prints. ``bench/PREREG.md`` compares two systems' F1s "by Zyte's evaluator's
own matching and formula", which needs what that evaluator only sums: each
page's true positives, false positives and false negatives. So its matching
functions and its F1 are imported from the file itself, as the benchmark
ships it into ``bench/cache/``, never rewritten here.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import stats

HERE = Path(__file__).resolve().parent
COMMIT = "cba97d7a8d42aeefd4021bc15d482f297faceaa3"
BENCH = HERE / "cache" / "products" / f"product-extraction-benchmark-{COMMIT}"
EVALUATE = BENCH / "evaluate.py"
# The attributes Zyte's evaluator scores, and how each is matched.
ATTRIBUTES = {
    "price": "decimal_matching",
    "sku": "hard_matching",
    "availability": "hard_matching",
    "InStock": "hard_matching",
    "OutOfStock": "hard_matching",
}


def evaluator(path: Path = EVALUATE) -> types.ModuleType:
    """``evaluate.py``, imported. It imports ``tabulate`` for the table its
    ``main`` prints, which nothing here calls; when that is not installed, an
    empty module stands in for it."""
    if "tabulate" not in sys.modules:
        try:
            import tabulate  # noqa: F401
        except ImportError:
            sys.modules["tabulate"] = types.ModuleType("tabulate")
    spec = importlib.util.spec_from_file_location("zyte_evaluate", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def counts(
    truth: dict[str, dict[str, Any]],
    predicted: dict[str, dict[str, Any]],
    attribute: str,
    evaluate: types.ModuleType,
) -> list[tuple[int, int, int]]:
    """Every page's (tp, fp, fn) on ``attribute``, the pages in id order, as
    ``evaluate.evaluate`` counts them before it sums them."""
    match = getattr(evaluate, ATTRIBUTES[attribute])
    return [
        tuple(match(set(truth[key].get(attribute, [])), predicted[key].get(attribute)))
        for key in sorted(truth)
    ]


def f1(sums: Sequence[float], evaluate: types.ModuleType) -> float:
    """Zyte's F1 of summed (tp, fp, fn), by its own formula: a precision and
    recall of 1 when there is no false positive and no false negative."""
    found = evaluate.metrics_from_tp_fp_fns([tuple(int(v) for v in sums)])
    return float(found["f1"])


def compare(
    ours: Sequence[tuple[int, int, int]],
    theirs: Sequence[tuple[int, int, int]],
    evaluate: types.ModuleType,
) -> stats.Comparison:
    """Our F1 minus theirs, the pages resampled together."""
    columns = [[page[i] for page in ours] for i in range(3)] + [
        [page[i] for page in theirs] for i in range(3)
    ]
    return stats.compare(columns, lambda s: f1(s[:3], evaluate) - f1(s[3:], evaluate))
