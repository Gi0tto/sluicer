# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""--visible on WCXB's development split, the only pages its rules are made on.

    .venv/bin/python bench/visible_dev.py            # the table
    .venv/bin/python bench/visible_dev.py --misses author   # examples to read

Run from the checkout's own environment, so the Sluicer measured is the one
being changed. Scores title, author and date with ``bench/score.py``, as the
scoreboards do, in four columns: what the page declares, what --visible reads
off the page alone, the two together (a guess only where nothing is
declared), and trafilatura's own guess for a reference. No scoreboard page is
read here; see ``bench/PREREG.md``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import score  # noqa: E402

import sluicer  # noqa: E402
from sluicer.visible import read_visible  # noqa: E402

CORPUS = HERE / "cache" / "wcxb"
QUESTIONS = {"title": "title", "author": "author", "date": "published"}


def pages() -> list[dict[str, Any]]:
    metadata = json.loads((CORPUS / "metadata.json").read_text(encoding="utf-8"))
    found = []
    for file_id, info in sorted(metadata["files"].items()):
        if info.get("split") != "dev":
            continue
        truth = json.loads(
            (CORPUS / "dev" / "ground-truth" / f"{file_id}.json").read_text(
                encoding="utf-8"
            )
        )
        labels = truth.get("ground_truth") or {}
        found.append(
            {
                "id": file_id,
                "url": truth.get("url"),
                "page_type": info.get("page_type"),
                "html": CORPUS / "dev" / "html" / f"{file_id}.html.gz",
                "title": labels.get("title"),
                "author": labels.get("author"),
                "date": labels.get("publish_date"),
            }
        )
    return found


def answers(all_pages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    import trafilatura

    rows: dict[str, list[dict[str, Any]]] = {
        "declared": [],
        "visible": [],
        "together": [],
        "trafilatura": [],
    }
    for page in all_pages:
        html = gzip.decompress(page["html"].read_bytes())
        result = sluicer.extract(html, url=page["url"])
        guesses = read_visible(html, url=page["url"])
        declared = {
            field: (a.value if (a := result.summary.get(q)) else None)
            for field, q in QUESTIONS.items()
        }
        visible = {
            field: (g.value if (g := guesses.get(q)) else None)
            for field, q in QUESTIONS.items()
        }
        rows["declared"].append({"id": page["id"], **declared})
        rows["visible"].append({"id": page["id"], **visible})
        rows["together"].append(
            {"id": page["id"], **{f: declared[f] or visible[f] for f in QUESTIONS}}
        )
        meta = trafilatura.extract_metadata(
            html.decode("utf-8", "replace"), default_url=page["url"]
        )
        rows["trafilatura"].append(
            {
                "id": page["id"],
                "title": meta.title if meta else None,
                "author": meta.author if meta else None,
                "date": meta.date if meta else None,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--misses", choices=list(QUESTIONS))
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    all_pages = pages()
    by_id = {p["id"]: p for p in all_pages}
    rows = answers(all_pages)
    print(f"{len(all_pages)} development pages of WCXB")
    print(f"{'':12} " + "  ".join(f"{f:>28}" for f in QUESTIONS))
    print(f"{'':12} " + "  ".join(f"{'hit  right  invented':>28}" for _ in QUESTIONS))
    for name, found in rows.items():
        counts = score.tally(score.outcomes(found, by_id), by_id)
        cells = [
            f"{score.hit_rate(counts[f]):.3f}  "
            f"{score.right_when_answering(counts[f]):.3f}  "
            f"{counts[f]['invention']:>4}"
            for f in QUESTIONS
        ]
        print(f"{name:12} " + "  ".join(f"{c:>28}" for c in cells))
    if args.misses:
        field = args.misses
        visible = {r["id"]: r[field] for r in rows["visible"]}
        shown = Counter()
        for row in rows["visible"]:
            page = by_id[row["id"]]
            got = visible[row["id"]]
            outcome = score.outcome(field, got, page[field])
            if (
                outcome in ("wrong", "invention", "silent")
                and shown[outcome] < args.limit
            ):
                shown[outcome] += 1
                print(
                    f"{outcome:9} {row['id']} "
                    f"want={str(page[field])[:50]!r} got={str(got)[:60]!r}"
                )


if __name__ == "__main__":
    main()
