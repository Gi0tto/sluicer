# /// script
# requires-python = ">=3.10"
# ///
"""The markdown's rules, on WCXB's development split, the only pages they are made on.

    .venv/bin/python bench/markdown_dev.py                 # every candidate, the table
    .venv/bin/python bench/markdown_dev.py --only baseline,recall
    .venv/bin/python bench/markdown_dev.py --show recall --pages 0001,0002

Run from the checkout's own environment, so the Sluicer measured is the one
being changed. Each candidate's markdown on each of the 1,358 dev pages is
written as plain text and its snippets counted by the every-tool scoreboard's
own functions (``tools_compare.plain``, ``snippets.counted``), and compared
with the 0.9.1 call, ``baseline``, paired by page, as ``bench/PREREG.md``
fixes under "The main text". No scoreboard page is read here.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.path.insert(0, str(HERE.parent / "src"))

import evaldata  # noqa: E402
import stats  # noqa: E402
from snippets import counted  # noqa: E402
from tools_compare import plain, word_scores  # noqa: E402

CORPUS = HERE / "cache" / "wcxb"
OUT = HERE / "cache" / "markdown-dev"
MAX_CHUNKS = evaldata.MAX_CHUNKS
_WORD = re.compile(r"\w+")


def pages() -> list[dict[str, Any]]:
    """The dev pages, in id order, with the labels the text is scored on."""
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
                "html": str(CORPUS / "dev" / "html" / f"{file_id}.html.gz"),
                "with": list(labels.get("with") or [])[:MAX_CHUNKS],
                "without": list(labels.get("without") or [])[:MAX_CHUNKS],
                "main_content": labels.get("main_content") or None,
            }
        )
    return found


def words(text: str | None) -> int:
    return len(_WORD.findall(plain(text)))


# --- what each page gives the candidates, computed once ----------------------------

_REGION_DROPPED = (
    "script", "style", "noscript", "template", "nav", "header", "footer",
    "aside", "form",
)  # fmt: skip


def _region_words(tree: Any) -> int:
    """Words of the page's main region's visible text (bench/PREREG.md)."""
    import copy

    region = None
    for path in ("//main", "//*[@role='main']"):
        found = tree.xpath(path)
        if found:
            region = found[0]
            break
    if region is None:
        articles = tree.xpath("//article")
        region = articles[0] if len(articles) == 1 else tree.find("body")
    if region is None:
        return 0
    region = copy.deepcopy(region)
    for element in list(region.iter()):
        if not isinstance(element.tag, str):
            continue
        if element.tag in _REGION_DROPPED or element.get("hidden") is not None:
            if element.getparent() is not None:
                element.drop_tree()
    return len(_WORD.findall(region.text_content()))


# --- the candidates not kept, as they were run (bench/PREREG.md) ----------------------
# They build on bench/markdown_rules.py's helpers, which the chosen rule kept.


def _proto_container(doc: Any, extracted: str, share: float) -> str | None:
    """container-K: the extraction's region written whole, within K times its
    words."""
    import markdown_rules as md

    region = md._region_of(doc.tree, extracted)
    if region is None:
        return None
    written = md._region_written(region, doc.base, authors=False)
    have, had = md._count(written), md._count(extracted)
    return written if had <= have <= share * had else None


def _proto_merged(doc: Any, extracted: str, least: int) -> str | None:
    """merge-W: the region's blocks in order, kept when the extraction holds
    them or they are long and mostly not links; then the rest of the
    extraction."""
    import markdown_rules as md

    region = md._region_of(doc.tree, extracted)
    if region is None:
        return None
    written = md._region_written(region, doc.base, authors=True)
    had = " ".join(md._words(extracted))
    kept: list[str] = []
    for block in written.split("\n\n"):
        said = md._words(block)
        if not said:
            continue
        linked = sum(len(md._WORD.findall(t)) for t in md._LINK_TEXT.findall(block))
        if " ".join(said) in had or (len(said) >= least and linked < 0.5 * len(said)):
            kept.append(block)
    holding = " ".join(md._words("\n\n".join(kept)))
    for block in extracted.split("\n\n"):
        said = md._words(block)
        if said and " ".join(said) not in holding:
            kept.append(block)
    return "\n\n".join(kept)


def _proto_gaps(doc: Any, extracted: str, least: int, strict: bool) -> str | None:
    """gap-W (``strict`` False) and gap2-W (True), as they were run; gap2-W is
    what ``markdown_rules._gaps_filled`` keeps."""
    import markdown_rules as md

    if strict:
        return md._gaps_filled(doc, extracted, least)
    region = md._region_of(doc.tree, extracted)
    if region is None:
        return None
    units = md._units(md._region_written(region, doc.base, authors=True))
    blocks = extracted.split("\n\n")
    spoken = [" ".join(md._words(block)) for block in blocks]
    whole = " ".join(spoken)
    held = [" ".join(md._words(unit)) in whole for unit in units]
    kept_at = [i for i, h in enumerate(held) if h]
    if len(kept_at) < 2:
        return None
    added = [False] * len(units)
    for i in range(kept_at[-1] - 1, kept_at[0], -1):
        if held[i]:
            continue
        unit = units[i]
        said = md._words(unit)
        if md._HEADING_LINE.match(unit):
            added[i] = added[i + 1]
            continue
        linked = sum(len(md._WORD.findall(t)) for t in md._LINK_TEXT.findall(unit))
        added[i] = len(said) >= least and linked < 0.5 * len(said)
    if not any(added):
        return extracted
    after: dict[int, list[str]] = {}
    place = -1
    for i, unit in enumerate(units):
        if held[i]:
            said_words = " ".join(md._words(unit))
            place = next(
                (at for at, text in enumerate(spoken) if said_words in text), place
            )
        elif added[i]:
            after.setdefault(place, []).append(unit)
    out = [*after.get(-1, [])]
    for at, block in enumerate(blocks):
        out.append(block)
        out.extend(after.get(at, []))
    return "\n\n".join(out)


def primitives(page: dict[str, Any]) -> dict[str, Any]:
    """Every output a candidate is built from, for one page."""
    import logging

    import trafilatura
    from trafilatura.external import try_justext, try_readability

    import markdown_rules as md
    from sluicer.document import load
    from sluicer.markdown_writer import element_markdown

    logging.disable(logging.CRITICAL)
    html = gzip.decompress(Path(page["html"]).read_bytes())
    url = page["url"]
    resolved = md._with_links_resolved(trafilatura, html, url)

    def extract(**options: Any) -> str:
        return (
            trafilatura.extract(
                resolved,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                url=url,
                **options,
            )
            or ""
        )

    doc = load(html, url=url)
    row: dict[str, Any] = {
        "id": page["id"],
        "baseline": extract(),
        "recall": extract(favor_recall=True),
        "precision": extract(favor_precision=True),
        "no-comments": extract(include_comments=False),
        "region_words": _region_words(doc.tree),
        "sluicer": md.to_markdown(html, url=url),
    }
    loaded = trafilatura.load_html(html)
    row["readability"] = (
        element_markdown(try_readability(loaded), doc.base)
        if loaded is not None
        else ""
    )
    loaded = trafilatura.load_html(html)
    row["justext"] = (
        element_markdown(try_justext(loaded, url, None), doc.base)
        if loaded is not None
        else ""
    )
    from sluicer.api import _extract

    result = _extract(html, url=url)
    found = md._declared_text(doc, result.records)
    row["declared"] = found.markdown if found else ""
    row["declared_from"] = found.said if found else None
    h1s = [
        " ".join(h.text_content().split())
        for h in doc.tree.iter("h1")
        if h.text_content().strip()
    ]
    row["h1"] = h1s[0] if len(h1s) == 1 else None
    row["full"] = md._full_markdown(html, url)
    for share in (1.25, 1.5, 2.0):
        row[f"container-{share}"] = _proto_container(doc, row["baseline"], share)
    for least in (8, 12, 16):
        row[f"merge-{least}"] = _proto_merged(doc, row["baseline"], least)
    for least in (8, 12, 16):
        row[f"gap-{least}"] = _proto_gaps(doc, row["baseline"], least, False)
    readable = _longer_if_short("readability", 0.7, "region")(row)
    for least in (12, 16):
        for name, text in (
            ("gap2", row["baseline"]),
            ("read-gap2", readable),
            ("nc-gap2", row["no-comments"]),
        ):
            row[f"{name}-{least}"] = _proto_gaps(doc, text, least, True) or text
    for name, against in (("read-recall", "recall"), ("read-region", "region")):
        chosen = readable
        limit = row["region_words"] if against == "region" else words(row["recall"])
        if words(chosen) < 0.7 * limit and words(row["recall"]) > words(chosen):
            chosen = row["recall"]
        row[f"{name}-gap2-12"] = _proto_gaps(doc, chosen, 12, True) or chosen
    title = result.summary.get("title")
    row["title"] = str(title.value) if title else None
    return row


def computed(fresh: bool, all_pages: list[dict[str, Any]]) -> dict[str, dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "primitives.json.gz"
    if path.exists() and not fresh:
        return {row["id"]: row for row in json.loads(gzip.decompress(path.read_bytes()))}
    with ProcessPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(primitives, all_pages, chunksize=8))
    path.write_bytes(gzip.compress(json.dumps(rows).encode("utf-8"), mtime=0))
    return {row["id"]: row for row in rows}


# --- the candidates, from the primitives ------------------------------------------


def _longer_if_short(key: str, share: float, against: str) -> Callable[[dict], str]:
    def pick(row: dict) -> str:
        base = row["baseline"]
        limit = row["region_words"] if against == "region" else words(row[key])
        if words(base) < share * limit and words(row[key]) > words(base):
            return str(row[key])
        return str(base)

    return pick


def _declared_first(share: float) -> Callable[[dict], str]:
    def pick(row: dict) -> str:
        if row["declared"] and words(row["declared"]) >= share * words(row["baseline"]):
            return str(row["declared"])
        return str(row["baseline"])

    return pick


def _declared_rescue(row: dict) -> str:
    if row["declared"] and words(row["baseline"]) < 0.5 * words(row["declared"]):
        return str(row["declared"])
    return str(row["baseline"])


def _with_h1(row: dict, titled: bool = False) -> str:
    base = str(row["baseline"])
    h1 = row["h1"]
    if titled and not (h1 and row["title"] and _one_title(h1, row["title"])):
        return base
    if h1 and base and plain(h1) not in plain(base):
        return f"# {h1}\n\n{base}"
    return base


def _one_title(a: str, b: str) -> bool:
    """bench/score.py's rule for a title."""
    a, b = (" ".join(x.lower().split()) for x in (a, b))
    if a == b:
        return True
    short, long = sorted((a, b), key=len)
    return short in long and len(short) >= 0.6 * len(long)


def _container(share: float) -> Callable[[dict], str]:
    def pick(row: dict) -> str:
        return str(row[f"container-{share}"] or row["baseline"])

    return pick


CANDIDATES: dict[str, Callable[[dict], str]] = {
    "baseline": lambda row: str(row["baseline"]),
    "sluicer": lambda row: str(row["sluicer"]),
    "declared-first-0.5": _declared_first(0.5),
    "declared-first-0.8": _declared_first(0.8),
    "declared-first-1.0": _declared_first(1.0),
    "declared-rescue": _declared_rescue,
    "recall": lambda row: str(row["recall"]),
    "recall-if-short-0.5": _longer_if_short("recall", 0.5, "recall"),
    "recall-if-short-0.7": _longer_if_short("recall", 0.7, "recall"),
    "region-0.5": _longer_if_short("recall", 0.5, "region"),
    "region-0.7": _longer_if_short("recall", 0.7, "region"),
    "readability-0.5": _longer_if_short("readability", 0.5, "region"),
    "readability-0.7": _longer_if_short("readability", 0.7, "region"),
    "justext-0.5": _longer_if_short("justext", 0.5, "region"),
    "justext-0.7": _longer_if_short("justext", 0.7, "region"),
    "no-comments": lambda row: str(row["no-comments"]),
    "precision": lambda row: str(row["precision"]),
    "h1": _with_h1,
    "h1-titled": lambda row: _with_h1(row, titled=True),
    "container-1.25": _container(1.25),
    "container-1.5": _container(1.5),
    "container-2.0": _container(2.0),
    "merge-8": lambda row: str(row["merge-8"] or row["baseline"]),
    "merge-12": lambda row: str(row["merge-12"] or row["baseline"]),
    "merge-16": lambda row: str(row["merge-16"] or row["baseline"]),
    "gap-8": lambda row: str(row["gap-8"] or row["baseline"]),
    "gap-12": lambda row: str(row["gap-12"] or row["baseline"]),
    "gap-16": lambda row: str(row["gap-16"] or row["baseline"]),
    **{
        f"{name}-{least}": (lambda row, key=f"{name}-{least}": str(row[key]))
        for name in ("gap2", "read-gap2", "nc-gap2")
        for least in (12, 16)
    },
    "read-recall-gap2-12": lambda row: str(row["read-recall-gap2-12"]),
    "read-region-gap2-12": lambda row: str(row["read-region-gap2-12"]),
    "full": lambda row: str(row["full"]),
}


# --- scoring --------------------------------------------------------------------------


def text_rows(all_pages: list[dict[str, Any]], outputs: dict[str, str]) -> dict:
    found = {}
    for page in all_pages:
        text = plain(outputs[page["id"]])
        snippets = counted(page, text)
        found[page["id"]] = {
            "snippets": snippets,
            "has_without": bool(page["without"]),
            "clean": snippets[1] == 0,
            "empty": not text and bool(page["with"]),
            "words": word_scores(text, page["main_content"])
            if page["main_content"]
            else None,
        }
    return found


def _columns(rows: dict, ids: list[str]) -> list[list[int]]:
    return [[rows[i]["snippets"][k] for i in ids] for k in range(3)]


def _clean(rows: dict, ids: list[str]) -> list[list[int]]:
    return [
        [int(rows[i]["has_without"] and rows[i]["clean"]) for i in ids],
        [int(rows[i]["has_without"]) for i in ids],
    ]


def summary(rows: dict, ids: list[str]) -> dict[str, Any]:
    sums = [float(sum(column)) for column in _columns(rows, ids)]
    rates = evaldata._snippet_rates(sums)
    hits, trials = (sum(column) for column in _clean(rows, ids))
    scored = [rows[i]["words"] for i in ids if rows[i]["words"]]
    return {
        **rates,
        "clean": stats.ratio(hits, trials),
        "clean_rate": stats.rate(hits, trials),
        "word F1": sum(w[2] for w in scored) / len(scored) if scored else 0.0,
        "word R": sum(w[1] for w in scored) / len(scored) if scored else 0.0,
        "empty": sum(1 for i in ids if rows[i]["empty"]),
    }


def paired(ours: dict, theirs: dict, ids: list[str]) -> dict[str, stats.Comparison]:
    found = {}
    for measure in ("precision", "recall", "F1"):
        found[measure] = stats.compare(
            [*_columns(ours, ids), *_columns(theirs, ids)],
            lambda s, m=measure: (
                evaldata._snippet_rates(s[:3])[m] - evaldata._snippet_rates(s[3:])[m]
            ),
        )
    found["clean"] = stats.rate_difference(*_clean(ours, ids), *_clean(theirs, ids))
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="candidates, comma-separated")
    parser.add_argument("--fresh", action="store_true", help="recompute the outputs")
    parser.add_argument("--show", help="print one candidate's output on --pages")
    parser.add_argument("--pages", help="page ids, comma-separated")
    parser.add_argument("--by-type", action="store_true", help="F1 by page type")
    parser.add_argument(
        "--against", default="baseline", help="the candidate compared with"
    )
    args = parser.parse_args()
    all_pages = pages()
    rows = computed(args.fresh, all_pages)
    if args.show:
        for page_id in (args.pages or "").split(","):
            print(f"=== {page_id}\n{CANDIDATES[args.show](rows[page_id])}\n")
        return
    names = args.only.split(",") if args.only else list(CANDIDATES)
    ids = [page["id"] for page in all_pages]
    declared = sum(1 for row in rows.values() if row["declared"])
    print(f"{len(ids)} dev pages; {declared} with a declared article text\n")
    base = text_rows(all_pages, {i: CANDIDATES[args.against](rows[i]) for i in ids})
    print(f"compared with {args.against}\n")
    print(
        "| candidate | precision | recall | F1 | clean | word R | word F1 | empty "
        "| F1, paired | clean, paired |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for name in names:
        scored = text_rows(all_pages, {i: CANDIDATES[name](rows[i]) for i in ids})
        s = summary(scored, ids)
        versus = paired(scored, base, ids) if name != args.against else None
        f1 = f"{stats.difference(versus['F1'])} {versus['F1'].verdict}" if versus else ""
        clean = (
            f"{stats.difference(versus['clean'])} {versus['clean'].verdict}"
            if versus
            else ""
        )
        print(
            f"| {name} | {s['precision']:.3f} | {s['recall']:.3f} | {s['F1']:.3f} "
            f"| {s['clean_rate']} | {s['word R']:.3f} | {s['word F1']:.3f} "
            f"| {s['empty']} | {f1} | {clean} |",
            flush=True,
        )
        if args.by_type:
            kinds = sorted({p["page_type"] for p in all_pages})
            for kind in kinds:
                kind_ids = [p["id"] for p in all_pages if p["page_type"] == kind]
                k = summary(scored, kind_ids)
                print(
                    f"|   {kind} ({len(kind_ids)}) | {k['precision']:.3f} "
                    f"| {k['recall']:.3f} | {k['F1']:.3f} | {k['clean']:.3f} "
                    f"| {k['word R']:.3f} | {k['word F1']:.3f} | {k['empty']} | | |"
                )


if __name__ == "__main__":
    main()
