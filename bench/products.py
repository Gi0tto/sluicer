"""Sluicer on Zyte's product-extraction benchmark, scored by Zyte's own evaluator.

The benchmark -- https://github.com/scrapinghub/product-extraction-benchmark,
MIT, archived -- is 140 product pages as they were served in 2021, scripts
intact, with price, sku and availability labelled by hand and several accepted
values where a page shows more than one. It ships the predictions of Zyte's
Automatic Extraction, Diffbot and an extruct baseline, and ``evaluate.py``,
which scores them. This script adds Sluicer's predictions beside those and runs
that evaluator unchanged, so every number is Zyte's rules, not ours.

    uv run bench/products.py        # writes docs/scoreboard-products.md

Sluicer answers from its summary: ``normalised.price`` for the price (a
decimal, or nothing when the page's text is ambiguous), ``sku`` as declared,
and ``availability`` mapped to InStock or OutOfStock. As the benchmark does for
extruct and Zyte, a page with no availability counts as InStock. Nothing is
tuned to these pages.
"""

from __future__ import annotations

import datetime
import gzip
import io
import json
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

import sluicer  # noqa: E402 -- the checkout's own, whatever is installed

REPOSITORY = "scrapinghub/product-extraction-benchmark"
COMMIT = "cba97d7a8d42aeefd4021bc15d482f297faceaa3"
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"
CACHE = HERE / "cache" / "products"
BENCH = CACHE / f"product-extraction-benchmark-{COMMIT}"
SCOREBOARD = ROOT / "docs" / "scoreboard-products.md"

# Availability values that mean a buyer cannot have it now. Everything else a
# page declares -- InStock, LimitedAvailability, PreOrder, BackOrder, OnlineOnly
# -- is InStock by the benchmark's two-value rule.
_OUT = frozenset({"outofstock", "soldout", "discontinued", "out of stock", "sold out"})


def ensure() -> Path:
    """The benchmark at the pinned commit, downloaded into the cache once."""
    if (BENCH / "dataset" / "ground-truth.json").exists():
        return BENCH
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f"downloading {REPOSITORY} at {COMMIT[:12]}", flush=True)
    with urllib.request.urlopen(ARCHIVE) as response:
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(CACHE, filter="data")
    return BENCH


def availability(value: str | None) -> str:
    """The benchmark's two values for what the page declared."""
    if value and value.strip().lower().replace("_", " ") in _OUT:
        return "OutOfStock"
    return "InStock"


def predict(bench: Path) -> tuple[dict[str, dict[str, str]], float]:
    """Sluicer's answer for every page, keyed as the ground truth is."""
    truth = json.loads(
        (bench / "dataset" / "ground-truth.json").read_text(encoding="utf-8")
    )
    predictions: dict[str, dict[str, str]] = {}
    started = time.perf_counter()
    for page_id, labels in truth.items():
        html = gzip.decompress(
            (bench / "dataset" / "html" / f"{page_id}.html.gz").read_bytes()
        )
        result = sluicer.extract(html, url=labels.get("url"))
        answer: dict[str, str] = {}
        if "price" in result.normalised:
            answer["price"] = result.normalised["price"]
        if "currency" in result.normalised:
            answer["currency"] = result.normalised["currency"]
        if "sku" in result.summary:
            answer["sku"] = result.summary["sku"].value
        declared = result.summary.get("availability")
        answer["availability"] = availability(declared.value if declared else None)
        answer[answer["availability"]] = answer["availability"]
        predictions[page_id] = answer
    return predictions, time.perf_counter() - started


def evaluate(bench: Path) -> dict[str, Any]:
    """Zyte's evaluate.py, unchanged, over every system's predictions."""
    metrics = bench / "metrics-with-sluicer.json"
    subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--with",
            "tabulate==0.9.0",
            "python",
            "evaluate.py",
            "--output",
            str(metrics),
        ],
        cwd=bench,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return json.loads(metrics.read_text(encoding="utf-8"))


def publish(metrics: dict[str, Any], seconds: float, pages: int) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
    ).stdout.strip()
    systems = ["sluicer", "extruct", "Diffbot", "Zyte"]
    labels = {
        "sluicer": f"**sluicer {sluicer.__version__}**",
        "extruct": "extruct + price-parser",
        "Diffbot": "Diffbot (paid API, 2021)",
        "Zyte": "Zyte Automatic Extraction (paid API, 2021)",
    }
    lines = [
        "# Scoreboard, on product pages",
        "",
        "Sluicer on [Zyte's product-extraction benchmark]"
        f"(https://github.com/{REPOSITORY}): {pages} product pages as they",
        "were served in 2021, scripts intact, with price, SKU and availability",
        "labelled by hand. The benchmark ships the predictions of Zyte's and",
        "Diffbot's paid extraction APIs and an open-source baseline built on",
        "extruct and price-parser, and the evaluator that scores them. Sluicer's",
        "predictions are added beside theirs and that evaluator runs unchanged, so",
        "every rule below is Zyte's: a price matches as a decimal, several values",
        "can be right, and a page with no availability counts as in stock.",
        "",
        f"Regenerated on {datetime.date.today().isoformat()} from commit "
        f"`{commit}` by `uv run bench/products.py`, against the benchmark at "
        f"`{COMMIT[:12]}`. Sluicer read the {pages} pages in {seconds:.1f} s.",
        "",
        '!!! warning "Read this before the numbers"',
        "    Zyte and Diffbot are commercial services built on trained models,",
        "    measured by Zyte in 2021 on pages it served them; Sluicer reads only",
        "    what the page declares and runs no model. A price shown on the page",
        "    and declared nowhere is a price Sluicer does not answer.",
        "",
        "| attribute | system | F1 | precision | recall | pages labelled |",
        "|---|---|---|---|---|---|",
    ]
    for attribute in ("price", "sku", "availability", "InStock", "OutOfStock"):
        for system in systems:
            m = metrics[system][attribute]
            lines.append(
                f"| {attribute} | {labels[system]} | {m['f1']:.3f} ± "
                f"{m['f1_std']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} "
                f"| {m['support']} |"
            )
    lines += [
        "",
        "The ± is the evaluator's bootstrap standard deviation over 1,000",
        "resamples of the pages.",
        "",
        "## Reading the errors",
        "",
        "Every wrong price and every miss was read by hand, looking for rules",
        "Sluicer had wrong rather than for rules that would fit these pages.",
        "",
        "- **Labels that read a thousands point as a decimal one.** Three pages in",
        "  Chile, Pakistan and Argentina show `24.990`, `23.450` and `2.449`, which",
        "  are thousands in their currencies and are labelled as 24.99, 23.45 and",
        "  2.449. Sluicer, reading the page's own markup, answers 24990, 23450 and",
        "  2449, and is scored wrong on all three.",
        "- **Pages that declare one price and show another.** A discounted price",
        "  shown over the regular one the markup declares, an auction's current",
        "  bid over its starting price. Zyte's own error analysis names the same",
        "  cause for its system.",
        "- **A label that accepts one spelling of an SKU on one Argos page and two",
        "  on the other.** `924/9556` and `9249556` are both right on one; on the",
        "  other only `466/7999` is, and Sluicer's declared `4667999` is scored",
        "  wrong.",
        "- **Pages that declare nothing.** Amazon's 20 pages declare no price in",
        "  any vocabulary, and 15 of them are labelled with one: most of the 37",
        "  prices Sluicer does not answer are on pages like these, shown and never",
        "  declared. That is the difference between these numbers and the paid",
        "  services', which read the visible page with trained models.",
        "",
        "What the benchmark found in Sluicer, and is fixed: a microdata price",
        "holding two numbers blocked the page's clean `product:price:amount`,",
        "and a product declared once per colour, or beside related products,",
        "was taken for a listing with no subject.",
        "",
    ]
    SCOREBOARD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    bench = ensure()
    predictions, seconds = predict(bench)
    output = bench / "dataset" / "output" / "sluicer.json"
    output.write_text(
        json.dumps(predictions, indent=4, sort_keys=True) + "\n", encoding="utf-8"
    )
    metrics = evaluate(bench)
    publish(metrics, seconds, len(predictions))
    for attribute in ("price", "sku", "availability"):
        row = "  ".join(
            f"{system} {metrics[system][attribute]['f1']:.3f}"
            for system in ("sluicer", "extruct", "Diffbot", "Zyte")
        )
        print(f"{attribute:13} {row}")
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
