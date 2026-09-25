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
extruct and Zyte, a page with no availability counts as InStock.

Sluicer's rules were made while these pages were read: ``7876710`` was measured
here, and ``9548a35`` added the SKU names the extruct baseline reads, to pass it.
This said "Nothing is tuned to these pages" until 0.7.1; the scoreboard now
opens by saying they were, and ``bench/PREREG.md`` lists which pages each rule
was made on.
"""

from __future__ import annotations

import datetime
import gzip
import io
import json
import re
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

import sluicer  # noqa: E402 -- the checkout's own, whatever is installed

sys.path.insert(0, str(HERE))

import stats  # noqa: E402
import zyte  # noqa: E402

REPOSITORY = "scrapinghub/product-extraction-benchmark"
# Pinned in bench/zyte.py, which reads the same checkout page by page.
COMMIT = zyte.COMMIT
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"
CACHE = HERE / "cache" / "products"
BENCH = zyte.BENCH
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


def predict(bench: Path) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Sluicer's answer for every page, keyed as the ground truth is, and the
    pages that declare a price Sluicer could not read as a decimal. It is not
    timed: ``bench/PREREG.md`` measures a second only with every tool of a
    table in one run, and Zyte's and Diffbot's were measured by Zyte in 2021."""
    truth = json.loads(
        (bench / "dataset" / "ground-truth.json").read_text(encoding="utf-8")
    )
    predictions: dict[str, dict[str, str]] = {}
    unread: set[str] = set()
    for page_id, labels in truth.items():
        html = gzip.decompress(
            (bench / "dataset" / "html" / f"{page_id}.html.gz").read_bytes()
        )
        result = sluicer.extract(html, url=labels.get("url"))
        answer: dict[str, str] = {}
        if "price" in result.normalised:
            answer["price"] = result.normalised["price"]
        elif "price" in result.summary:
            unread.add(page_id)
        if "currency" in result.normalised:
            answer["currency"] = result.normalised["currency"]
        if "sku" in result.summary:
            answer["sku"] = result.summary["sku"].value
        declared = result.summary.get("availability")
        answer["availability"] = availability(declared.value if declared else None)
        answer[answer["availability"]] = answer["availability"]
        predictions[page_id] = answer
    return predictions, unread


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


def _host(url: str | None) -> str:
    host = urlsplit(url or "").hostname or "?"
    return host.removeprefix("www.")


def _number(text: str) -> float | None:
    try:
        return float(re.sub(r"[^0-9.]", "", text))
    except ValueError:
        return None


def _listed(items: list[str]) -> str:
    """``a, b and c``."""
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _errors(
    truth: dict[str, Any], predictions: dict[str, Any], unread: set[str]
) -> list[str]:
    """The error classes, counted from this run's answers and the labels.

    Before 0.7.1 this section was written by hand once and printed on every
    run, numbers included.
    """
    priced = [k for k in truth if truth[k].get("price")]
    missed = [k for k in priced if "price" not in predictions[k]]
    wrong = [
        k
        for k in priced
        if "price" in predictions[k]
        and not any(
            _number(label) == _number(predictions[k]["price"])
            for label in truth[k]["price"]
        )
    ]
    thousands = [
        k
        for k in wrong
        if any(
            (n := _number(label)) is not None
            and abs(n * 1000 - (_number(predictions[k]["price"]) or 0)) < 0.01
            for label in truth[k]["price"]
        )
    ]
    skus = [
        k
        for k in truth
        if truth[k].get("sku")
        and predictions[k].get("sku")
        and predictions[k]["sku"] not in truth[k]["sku"]
    ]
    spelt = [
        k
        for k in skus
        if any(
            "/" in label and label.replace("/", "") == predictions[k]["sku"]
            for label in truth[k]["sku"]
        )
    ]
    amazon = [k for k in truth if _host(truth[k].get("url")).startswith("amazon.")]
    undeclared = [k for k in missed if k not in unread]
    where = _listed([_host(truth[k]["url"]) for k in thousands])
    return [
        f"- **Labels that read a thousands point as a decimal one.** On "
        f"{len(thousands)} pages -- {where}"
        " -- Sluicer's price, read from the page's own markup, is a thousand",
        "  times the label's: "
        + _listed(
            [
                f"{predictions[k]['price']} against {' or '.join(truth[k]['price'])}"
                for k in thousands
            ]
        )
        + ". Read by hand at 0.7.0, these are prices written with a thousands",
        "  point, as in `24.990`, that the labels read as a decimal one.",
        f"- **Other wrong prices.** {len(wrong) - len(thousands)} more answered "
        "prices are accepted by no label.",
        "  Read by hand at 0.7.0, they are pages that declare one price and show",
        "  another: a discounted price shown over the regular one the markup",
        "  declares, an auction's current bid over its starting price. Zyte's own",
        "  error analysis names the same cause for its system.",
        f"- **SKUs.** {len(skus)} answered SKUs are accepted by no label. On "
        f"{len(spelt)} of them",
        "  the label accepts the SKU as the page shows it and not as it declares",
        "  it: "
        + _listed(
            [
                f"`{' or '.join(truth[k]['sku'])}` and not `{predictions[k]['sku']}`"
                f" ({_host(truth[k]['url'])})"
                for k in spelt
            ]
        )
        + ".",
        f"- **Prices not answered.** Sluicer answers no price on {len(missed)} of "
        f"the {len(priced)}",
        f"  pages labelled with one. On {len(undeclared)} of them no price reaches "
        "its summary",
        f"  -- {sum(k in amazon for k in undeclared)} of them among Amazon's "
        f"{len(amazon)} pages -- and on",
        f"  {len(missed) - len(undeclared)} the price declared does not read as "
        "one decimal. A price",
        "  shown and never declared is what the paid services read off the",
        "  visible page with trained models, and the difference between their",
        "  numbers and these.",
    ]


def _comparisons(labels: dict[str, str], systems: list[str]) -> list[str]:
    """Sluicer's F1 minus every other system's, paired page by page."""
    evaluate = zyte.evaluator(BENCH / "evaluate.py")
    truth = json.loads(
        (BENCH / "dataset" / "ground-truth.json").read_text(encoding="utf-8")
    )
    predicted = {
        system: json.loads(
            (BENCH / "dataset" / "output" / f"{system}.json").read_text(
                encoding="utf-8"
            )
        )
        for system in systems
    }
    lines = [
        "| attribute | Sluicer against | F1 difference (95% interval) | verdict |",
        "|---|---|---|---|",
    ]
    count = 0
    for attribute in zyte.ATTRIBUTES:
        ours = zyte.counts(truth, predicted["sluicer"], attribute, evaluate)
        for system in systems[1:]:
            theirs = zyte.counts(truth, predicted[system], attribute, evaluate)
            found = zyte.compare(ours, theirs, evaluate)
            count += 1
            lines.append(
                f"| {attribute} | {labels[system]} | {stats.difference(found)} "
                f"| {found.verdict} |"
            )
    return [
        *lines,
        "",
        "The interval is the 95% percentile interval of 10,000 resamples of the",
        "pages (`bench/stats.py`, seed 20260924): **better** when it is above",
        "zero, **worse** when below, **inconclusive** when it holds zero. These",
        f"are {count} comparisons, made with no correction for making many, so",
        "read them as a table, not one at a time.",
    ]


def publish(
    metrics: dict[str, Any],
    truth: dict[str, Any],
    predictions: dict[str, Any],
    unread: set[str],
) -> None:
    pages = len(predictions)
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
        f"`{COMMIT[:12]}`.",
        "",
        '!!! warning "Sluicer\'s rules were made on these pages"',
        "    Rules were written, measured on these pages and kept because the",
        "    numbers here rose (`7876710`; `9548a35` added the SKU names the",
        "    extruct baseline reads, to pass it), so this measures Sluicer on",
        "    pages it was fitted to, not on pages it has never seen. Of the",
        "    scoreboards, only SWDE's held-out half is a held-out test;",
        "    [`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)",
        "    says which pages each rule was made on.",
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
        "resamples of the pages (seed 42), kept as Zyte's evaluator prints it.",
        "Beside it, Sluicer against each system, by the same evaluator's",
        "matching and F1, the pages resampled together:",
        "",
        *_comparisons(labels, systems),
        "",
        "## Reading the errors",
        "",
        "Each class below is counted from this run's answers and the labels.",
        "",
        *_errors(truth, predictions, unread),
        "",
        "Rules made while reading these pages, before 0.7.0: a microdata price",
        "holding two numbers no longer blocks the page's clean",
        "`product:price:amount`, a product declared once per colour or beside",
        "related products is no longer taken for a listing with no subject",
        "(`7876710`), and an SKU is also read from `productID`, `og:sku` and",
        "`product:sku`, as the extruct baseline reads it (`9548a35`).",
        "",
    ]
    SCOREBOARD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    bench = ensure()
    predictions, unread = predict(bench)
    output = bench / "dataset" / "output" / "sluicer.json"
    output.write_text(
        json.dumps(predictions, indent=4, sort_keys=True) + "\n", encoding="utf-8"
    )
    metrics = evaluate(bench)
    truth = json.loads(
        (bench / "dataset" / "ground-truth.json").read_text(encoding="utf-8")
    )
    publish(metrics, truth, predictions, unread)
    for attribute in ("price", "sku", "availability"):
        row = "  ".join(
            f"{system} {metrics[system][attribute]['f1']:.3f}"
            for system in ("sluicer", "extruct", "Diffbot", "Zyte")
        )
        print(f"{attribute:13} {row}")
    print(f"wrote {SCOREBOARD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
