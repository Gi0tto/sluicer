"""The drift benchmark: extractors learnt on old captures, replayed on later ones.

For every pair in ``pairs.json``: learn an extractor from capture A (and A2),
replay it on capture B, and ask an oracle that does not use the extractor
whether B's listing is still built the way A's was. Then heal on B and check
the healed extractor reads the same items as A did; and, beside it, ask
Scrapling's adaptive selectors to find one item's title and link again on B.

    uv run --with brotli --with 'scrapling>=0.4' bench/drift/run.py

writes ``docs/drift.md``. ``--no-scrapling`` leaves Scrapling out and
``--only`` runs the pairs whose id contains a word, without writing the page.
The captures come from the Wayback Machine, politely, and are cached under
``bench/cache/drift/``; nothing archived is committed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import lxml.html

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

from wayback import CACHE, Snapshot, snapshot  # noqa: E402

from sluicer import __version__  # noqa: E402
from sluicer.extractor import (  # noqa: E402
    LOSSES,
    Listing,
    NothingToLearn,
    compile_extractor,
    heal,
    run_extractor,
    shape,
)

OUTCOMES = ("failed silently", "false alarm", "failed loudly", "survived")
Row = dict[str, str]


# -- the oracle ----------------------------------------------------------------
# Written without the extractor's code: the learnt paths are walked here with
# plain lxml, so a bug in how the extractor finds its listing is not also the
# oracle's.


def oracle(listing: Listing, html: bytes) -> tuple[str, str]:
    """Whether B's listing is built as A's was: "same", or "drift" and why."""
    tree = lxml.html.document_fromstring(html)
    containers = _walk(tree, listing.container)
    if not containers:
        return "drift", "the listing's container is gone"
    if len(containers) > 1:
        return "drift", f"the container's path now leads to {len(containers)} places"
    tag, *classes = listing.member.split(".")
    rows = [
        child
        for child in containers[0]
        if isinstance(child.tag, str)
        and child.tag == tag
        and set(classes) <= set((child.get("class") or "").split())
        and _carries_something(child)
    ]
    if not rows:
        return "drift", f"no {listing.member} rows in the container"
    paths = {f.path for f in listing.fields}
    for f in listing.fields:
        if f.missing > 0 or _later_repeat(f.path, paths):
            continue
        share = sum(1 for row in rows if _present(row, f.path)) / len(rows)
        if share < 0.8:
            return "drift", f"{f.path} is in {share:.0%} of rows"
    return "same", ""


def _carries_something(member: Any) -> bool:
    """A row is a member with a part that holds text or an address; one with
    none -- a paragraph of bare text, a spacer -- is no row, as learnt."""
    return any(
        (part.text_content() or "").strip() or part.get("href") or part.get("src")
        for part in member.iterdescendants()
        if isinstance(part.tag, str)
    )


# The path grammar, read from its documentation rather than from its code: a
# step is the tag and the first class, in sorted order, that a person wrote --
# not one a build tool generated -- with ``[n]`` when siblings share the label.
_TOOLING = ("css-", "sc-", "jsx-", "dcr-", "svelte-", "astro-", "emotion-")
_HASHY = re.compile(r"[a-z]\d[a-z]|\d[a-z]\d", re.IGNORECASE)


def _written(token: str) -> str:
    if token.lower().startswith(_TOOLING) or set(token) & set("[]>@:/!()"):
        return ""
    module = re.fullmatch(r"(.+?)__([A-Za-z0-9_-]{5,})", token)
    if module and _hashy(module.group(2)):
        token = module.group(1)
    if any(_hashy(part) for part in re.split(r"[-_]+", token)):
        return ""
    return token


def _hashy(part: str) -> bool:
    if len(part) < 5:
        return False
    if _HASHY.search(part):
        return True
    flips = sum(
        1
        for x, y in pairwise(part)
        if x.isalpha() and y.isalpha() and x.islower() != y.islower()
    )
    return part.isalpha() and flips / len(part) >= 0.5


def _step(element: Any) -> str:
    if element.tag in ("html", "body"):
        return str(element.tag)
    for token in sorted((element.get("class") or "").split()):
        if _written(token):
            return f"{element.tag}.{_written(token)}"
    return str(element.tag)


def _walk(tree: Any, path: str) -> list[Any]:
    """Every element ``path`` names; more than one means it is ambiguous now."""
    steps = path.split(">")
    if tree.tag != steps[0]:
        return []
    nodes = [tree]
    for step in steps[1:]:
        label, _, ordinal = step.partition("[")
        found = []
        for node in nodes:
            same = [c for c in node if isinstance(c.tag, str) and _step(c) == label]
            if ordinal:
                index = int(ordinal.rstrip("]")) - 1
                found.extend(same[index : index + 1])
            else:
                found.extend(same)
        nodes = found
    return nodes


def _present(row: Any, path: str) -> bool:
    """Whether the part an induced field path names is under ``row``.

    Field steps number a label once it repeats in any row: ``a.tag2`` is the
    second ``a.tag``, ``span2`` the second unclassed ``span``.
    """
    head, _, attribute = path.partition("@")
    nodes = [row]
    for step in head.split(">"):
        nodes = [c for node in nodes for c in _field_children(node, step)]
    if attribute:
        return any((node.get(attribute) or "").strip() for node in nodes)
    return bool(nodes)


def _field_children(node: Any, step: str) -> list[Any]:
    kids = [c for c in node if isinstance(c.tag, str)]
    exact = [c for c in kids if _step(c) == step]
    if exact:
        return exact
    base = step.rstrip("0123456789")
    number = step[len(base) :]
    if not number:
        return []
    same = [c for c in kids if _step(c) == base]
    return same[int(number) - 1 : int(number)]


def _later_repeat(path: str, paths: set[str]) -> bool:
    head, at, attribute = path.partition("@")
    digits = len(head) - len(head.rstrip("0123456789"))
    if not digits or int(head[-digits:]) < 2:
        return False
    return head[:-digits] + "1" + at + attribute in paths


# -- judging heal ----------------------------------------------------------------


def _is_address(name: str) -> bool:
    return "@" in name.rsplit(">", 1)[-1]


_TRACKING = re.compile(r"^(ref_?|utm_.*|pf_rd_.*|src|source)$")


def _norm(name: str, value: str | None) -> str:
    """A value as two captures of one item would both give it."""
    if not value:
        return ""
    if _is_address(name):
        parts = urlsplit(value)
        host = parts.netloc.lower().removeprefix("www.")
        kept = [
            p
            for p in parts.query.split("&")
            if p and not _TRACKING.match(p.split("=")[0])
        ]
        return host + parts.path.rstrip("/") + ("?" + "&".join(kept) if kept else "")
    # A count or a date inside a title changes between captures of one item,
    # and a rank before it: "1. The Godfather" is "The Godfather".
    text = re.sub(r"\d+", "#", " ".join(value.split()).casefold())
    return re.sub(r"^#[.)]?\s+", "", text)


def _same(name: str, one: str | None, other: str | None) -> bool:
    """Whether two values of a field are one value. An address is the same
    when only a parameter was added: an image with a cache-busting ``?w=120``
    is the same image; ``?id=2`` is another item than ``?id=1``."""
    first, second = _norm(name, one), _norm(name, other)
    if not first or not second or not _is_address(name):
        return first == second
    (path, _, query), (path2, _, query2) = first.partition("?"), second.partition("?")
    mine, theirs = set(query.split("&")) - {""}, set(query2.split("&")) - {""}
    return path == path2 and (mine <= theirs or theirs <= mine)


def identity_fields(listing: Listing, rows: list[Row]) -> list[str]:
    """Fields that name the item: in almost every row, different in almost
    every row, with letters in it or an address -- not a rank, a score or a
    count, which change between captures without anything having moved."""
    names = []
    for f in listing.fields:
        values = [_norm(f.name, row.get(f.name)) for row in rows if row.get(f.name)]
        if len(values) < max(3, 0.8 * len(rows)):
            continue
        if len(set(values)) < 0.9 * len(values):
            continue
        if _is_address(f.name) or "L" in shape(values[0]):
            names.append(f.name)
    return names


def match_items(
    identity: list[str], a_rows: list[Row], b_rows: list[Row]
) -> list[tuple[Row, Row]]:
    """A and B rows that are one item: at least half of what names the A row
    -- its link, its title, values almost no other row shares -- is found
    somewhere in the B row. Found in any field, so a column heal put in the
    wrong place still matches."""
    matched: list[tuple[Row, Row]] = []
    taken: set[int] = set()
    b_values = [{_norm(n, v) for n, v in b.items()} - {""} for b in b_rows]
    for a in a_rows:
        names = {_norm(n, a.get(n)) for n in identity} - {""}
        if len(names) < 2 and len(identity) > 1:
            continue
        best, share = None, 0.0
        for index, held in enumerate(b_values):
            if index in taken:
                continue
            here = len(names & held) / len(names) if names else 0.0
            if here > share:
                best, share = index, here
        if best is not None and share >= 0.5:
            taken.add(best)
            matched.append((a, b_rows[best]))
    return matched


def judge_heal(
    listing: Listing, a_rows: list[Row], b_rows: list[Row], healed: set[str]
) -> dict[str, Any]:
    identity = identity_fields(listing, a_rows)
    if not identity:
        return {"verdict": "nothing to judge", "matched": 0, "fields": {}}
    matched = match_items(identity, a_rows, b_rows)
    if len(matched) < 2:
        return {"verdict": "nothing to match", "matched": len(matched), "fields": {}}
    fields: dict[str, float | None] = {}
    for name in identity:
        if name not in healed:
            fields[name] = None
            continue
        same = sum(1 for a, b in matched if _same(name, a.get(name), b.get(name)))
        fields[name] = round(same / len(matched), 2)
    agreements = [v for v in fields.values() if v is not None]
    if not agreements:
        verdict = "lost"
    elif min(agreements) < 0.5:
        verdict = "wrong"
    elif min(agreements) < 0.8 or len(agreements) < len(fields):
        verdict = "partly right"
    else:
        verdict = "right"
    return {"verdict": verdict, "matched": len(matched), "fields": fields}


# -- Scrapling beside it ----------------------------------------------------------


def scrapling_finds(
    pair_id: str, a: Snapshot, b: Snapshot, title: str, raw_href: str | None
) -> dict[str, Any]:
    """Save the element holding ``title`` on A, ask for it again on B, compare.

    Scrapling returns what the saved selector matches on B when it matches
    anything, and relocates by similarity only when it matches nothing.
    """
    from scrapling.parser import Selector

    store = CACHE / f"scrapling-{pair_id}.db"
    store.unlink(missing_ok=True)
    storage = {"storage_file": str(store), "url": a.url}
    page_a = Selector(a.html, url=a.url, adaptive=True, storage_args=storage)
    candidates = page_a.find_by_text(title, first_match=False, partial=False)
    if len(candidates) == 0:
        return {"result": "title not found on A"}
    # The one in the listing's row: the same text can sit in a sidebar too.
    element = next(
        (c for c in candidates if raw_href and _href_near(c) == raw_href),
        candidates[0],
    )
    selector = element.generate_css_selector
    page_a.css(selector, auto_save=True, identifier=pair_id)
    page_b = Selector(b.html, url=a.url, adaptive=True, storage_args=storage)
    relocated = len(page_b.css(selector)) == 0
    found = page_b.css(selector, adaptive=True, identifier=pair_id)
    if len(found) == 0:
        return {
            "result": "nothing found",
            "wanted": title[:80],
            "selector": selector,
            "relocated": relocated,
        }
    got = found[0]
    text = " ".join(str(got.get_all_text()).split())
    text_ok = _norm("title", text) == _norm("title", title)
    link_ok = raw_href is None or _norm(
        "a@href", urljoin(b.url, _href_near(got) or "")
    ) == _norm("a@href", urljoin(a.url, raw_href))
    return {
        "result": "right" if text_ok and link_ok else "wrong",
        "wanted": title[:80],
        "got": text[:80],
        "selector": selector,
        "relocated": relocated,
    }


def _href_near(element: Any) -> str | None:
    """The link an element is, or sits in, or holds."""
    node, steps = element, 0
    while node is not None and steps < 4:
        if node.attrib.get("href"):
            return str(node.attrib["href"])
        node, steps = node.parent, steps + 1
    inner = element.css("a[href]")
    return str(inner[0].attrib["href"]) if len(inner) else None


def _key(identity: list[str]) -> str | None:
    """The item's own link: a link whose text names the item too, else any
    link naming it."""
    links = [n for n in identity if n.endswith("@href")]
    return next((n for n in links if n.rsplit("@", 1)[0] in identity), None) or next(
        iter(links), None
    )


def _title_field(listing: Listing, identity: list[str]) -> str | None:
    """The field a person would call the row's title: the text of a link that
    names the item, else the first text naming it that is neither an image's
    nor a wrapper around other fields."""
    texts = [
        n
        for n in identity
        if not _is_address(n) and not n.rsplit(">", 1)[-1].startswith("img")
    ]
    linked = [n for n in texts if n + "@href" in identity]
    names = [f.name for f in listing.fields]
    leaves = [n for n in texts if not any(o.startswith(n + ">") for o in names)]
    return (linked or leaves or [None])[0]


def _scrapling_for(
    pair_id: str,
    listing: Listing,
    a: Snapshot,
    b: Snapshot,
    a_rows: list[Row],
) -> dict[str, Any]:
    """Follow the first A item still on B -- its title an element's text there,
    and its link among B's links -- read from B itself, not by any extractor."""
    identity = identity_fields(listing, a_rows)
    title_field = _title_field(listing, identity)
    if title_field is None:
        return {"result": "no title to follow"}
    key = _key(identity)
    link_field = key if key and _is_address(key) else None
    tree_b = lxml.html.document_fromstring(b.html)
    texts_b = {
        _norm("title", e.text_content())
        for e in tree_b.iter()
        if isinstance(e.tag, str)
    }
    links_b = {
        _norm("a@href", urljoin(b.url, e.get("href") or "")) for e in tree_b.iter("a")
    }
    raw = _raw_hrefs(listing, a) if link_field else {}
    for a_row in a_rows:
        title = a_row.get(title_field)
        if not title or _norm("title", title) not in texts_b:
            continue
        link = a_row.get(link_field) if link_field else None
        if link_field and (not link or _norm("a@href", link) not in links_b):
            continue
        try:
            return scrapling_finds(
                pair_id,
                a,
                b,
                " ".join(title.split()),
                raw.get(_norm("a@href", link)) if link else None,
            )
        except Exception as failure:  # noqa: BLE001 -- another project's code
            return {"result": f"error: {type(failure).__name__}: {failure}"[:120]}
    return {"result": "no A item is still on B"}


def _raw_hrefs(listing: Listing, a: Snapshot) -> dict[str, str]:
    """The ``href`` of each row's title link on A as written in the markup,
    keyed by the address it resolves to."""
    tree = lxml.html.document_fromstring(a.html)
    found: dict[str, str] = {}
    for container in _walk(tree, listing.container)[:1]:
        for element in container.iter("a"):
            href = element.get("href")
            if href:
                found.setdefault(_norm("a@href", urljoin(a.url, href)), href)
    return found


# -- one pair --------------------------------------------------------------------


def score_pair(pair: dict[str, Any], with_scrapling: bool) -> dict[str, Any]:
    learn = [s for s in (snapshot(pair["url"], ts) for ts in pair["learn"]) if s]
    b = snapshot(pair["url"], pair["b"])
    if not learn or b is None:
        return {**pair, "error": "a capture is missing"}
    try:
        extractor = compile_extractor([(s.html, s.url) for s in learn], listing=True)
    except NothingToLearn as nothing:
        return {**pair, "error": f"nothing to learn: {nothing}"}
    if extractor.listing is None:
        return {**pair, "error": "no listing learnt"}
    listing = extractor.listing
    run = run_extractor(extractor, b.html, b.url)
    truth, why = oracle(listing, b.html)
    outcome = {
        (True, "same"): "survived",
        (False, "drift"): "failed loudly",
        (True, "drift"): "failed silently",
        (False, "same"): "false alarm",
    }[(run.ok, truth)]
    a_rows = run_extractor(extractor, learn[0].html, learn[0].url).rows
    try:
        healed, changes = heal(extractor, [(b.html, b.url)])
    except NothingToLearn:
        # What the command line reports as "nothing to heal from".
        healed, changes = None, []
    if healed is None or healed.listing is None:
        judged = {"verdict": "no listing on B", "matched": 0, "fields": {}}
        b_rows: list[Row] = []
    else:
        b_rows = run_extractor(healed, b.html, b.url).rows
        names = {f.name for f in healed.listing.fields}
        judged = judge_heal(listing, a_rows, b_rows, names)
    result = {
        **pair,
        "a": learn[0].timestamp,
        "b_landed": b.landed if b.landed != pair["url"] else None,
        "container": listing.container,
        "member": listing.member,
        "fields": len(listing.fields),
        "notes": list(extractor.notes),
        "rows_learnt": list(listing.rows),
        "rows_b": len(run.rows),
        "ok": run.ok,
        "failed": [
            f"{c.name}: {c.expected} -> {c.got}" for c in run.checks if not c.ok
        ],
        "oracle": truth,
        "oracle_why": why,
        "outcome": outcome,
        "heal": judged,
        "heal_losses": [f"{c.kind}: {c.before}" for c in changes if c.kind in LOSSES],
        "heal_moves": [
            f"{c.before} -> {c.after}" for c in changes if c.kind == "moved"
        ],
    }
    if with_scrapling:
        result["scrapling"] = _scrapling_for(pair["id"], listing, learn[0], b, a_rows)
    return result


# -- the page ---------------------------------------------------------------------


def _scrapling_version(scr: list[dict[str, Any]]) -> str:
    if not scr:
        return ""
    from importlib.metadata import version

    return f", Scrapling {version('scrapling')}"


def _archive_errors() -> list[str]:
    """The pages whose captures the archive kept failing to give."""
    failed = []
    for line in (HERE / "discover.log").read_text(encoding="utf-8").splitlines():
        if line.startswith("{"):
            row = json.loads(line)
            roles = {"A": "A", "A2": "A2", "B_short": "short B", "B_long": "long B"}
            failed += [
                f"the {roles[role]} capture of {row['url']}"
                for role in row.get("archive_errors", {})
            ]
    return failed


def _count(items: list[str]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for item in items:
        tally[item] = tally.get(item, 0) + 1
    return tally


def write_page(results: list[dict[str, Any]], seconds: float) -> None:
    written = json.loads((HERE / "explanations.json").read_text(encoding="utf-8"))
    explained, notes = written["losses"], written["notes"]
    ok = [r for r in results if "error" not in r]
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        encoding="utf-8",
    ).stdout.strip()
    tally = _count([r["outcome"] for r in ok])
    drift = [r for r in ok if r["oracle"] == "drift"]
    same = [r for r in ok if r["oracle"] == "same"]
    heal_drift = _count([r["heal"]["verdict"] for r in drift])
    heal_same = _count([r["heal"]["verdict"] for r in same])
    scr = [r for r in ok if "scrapling" in r]
    tried = [
        r
        for r in scr
        if r["scrapling"]["result"] in ("right", "wrong", "nothing found")
    ]
    scr_tally = _count([r["scrapling"]["result"] for r in tried])
    lines = [
        "# Drift",
        "",
        "What an extractor does when the page it was learnt from changes. Each",
        "extractor is learnt on an old Wayback Machine capture of a listing page",
        "and replayed on a later one. An oracle that does not use the extractor's",
        "code judges the result. Losses come first.",
        "",
        f"Regenerated on {datetime.date.today().isoformat()} from commit",
        f"`{commit}` (sluicer {__version__}{_scrapling_version(scr)}) with",
        "`uv run --with brotli --with 'scrapling>=0.4' bench/drift/run.py`, in",
        f"{seconds:.0f} seconds from the cache.",
        "",
        '!!! warning "Read this before the numbers"',
        f"    This is {len(ok)} pairs on {len({r['url'] for r in ok})} sites,",
        "    chosen as described below. That is a small sample, and the oracle",
        "    judges structure, not meaning. The numbers show how the checks behave",
        "    on real captures; they are not a rate to expect on your sites.",
        "",
        *_losses(ok, scr, explained),
        "## Results",
        "",
        "| outcome | pairs | what it means |",
        "|---|---|---|",
        f"| failed silently | {tally.get('failed silently', 0)} | the oracle saw"
        " drift and the run passed: the failure this project exists to prevent |",
        f"| false alarm | {tally.get('false alarm', 0)} | the oracle saw the same"
        " template and the run failed |",
        f"| failed loudly | {tally.get('failed loudly', 0)} | drift, and the run"
        " said so |",
        f"| survived | {tally.get('survived', 0)} | same template, and the run"
        " passed |",
        "",
        "`heal` was run on every B capture. A heal counts as right when the healed",
        "extractor reads the items A and B share with the values A had.",
        "",
        "| heal | on the pairs with drift | on the pairs without |",
        "|---|---|---|",
    ]
    for verdict in (
        "right",
        "partly right",
        "wrong",
        "lost",
        "nothing to match",
        "nothing to judge",
        "no listing on B",
    ):
        if heal_drift.get(verdict) or heal_same.get(verdict):
            counts = f"{heal_drift.get(verdict, 0)} | {heal_same.get(verdict, 0)}"
            lines.append(f"| {verdict} | {counts} |")
    lines += [
        "",
        '"Nothing to match" means no item was on both captures, so there was',
        "nothing to judge the heal against. News front pages a month apart share",
        "no stories.",
        "",
    ]
    if scr:
        relocated = [r for r in tried if r["scrapling"].get("relocated")]
        lines += [
            "Scrapling's adaptive selectors were asked, on each pair where A and B",
            "share an item, to find that item's title and link again on B. This",
            f"ran on {len(tried)} pairs. It was right on {scr_tally.get('right', 0)}"
            f" and wrong on {scr_tally.get('wrong', 0)}, and found nothing on"
            f" {scr_tally.get('nothing found', 0)}. On {len(relocated)} of these",
            "pairs the saved selector matched nothing on B, so Scrapling fell back",
            "to relocating by similarity.",
            "The comparison is narrow. Scrapling follows one element it was shown;",
            "Sluicer checks and heals a whole listing. The two answer different",
            "questions and are not ranked.",
            "",
        ]
    lines += ["## What this benchmark found in Sluicer, and fixed", ""]
    lines += [f"- {defect}" for defect in written["fixed"]]
    lines += ["", "## Other pairs, read by hand", ""]
    for r in ok:
        if r["id"] in notes:
            lines += [f"**{r['id']}**, {r['outcome']}. {notes[r['id']]}", ""]
    lines += [
        "## Every pair",
        "",
        "| pair | rows A / B | oracle | run | outcome | heal | Scrapling |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['id']} | | | | {r['error']} | | |")
            continue
        run = (
            "passed"
            if r["ok"]
            else "failed: " + ", ".join(sorted({f.split(":")[0] for f in r["failed"]}))
        )
        oracle_txt = r["oracle"] + (f": {r['oracle_why']}" if r["oracle_why"] else "")
        heal_txt = r["heal"]["verdict"]
        if r["heal"].get("matched"):
            heal_txt += f" ({r['heal']['matched']} items)"
        scr_txt = r.get("scrapling", {}).get("result", "")
        lo, hi = r["rows_learnt"]
        rows = f"{lo}{'' if lo == hi else f'-{hi}'} / {r['rows_b']}"
        lines.append(
            f"| {r['id']} | {rows} | {_cell(oracle_txt)} | {_cell(run)} | "
            f"{r['outcome']} | {heal_txt} | {_cell(scr_txt)} |"
        )
    lines += ["", *_method_and_limits(ok)]
    (ROOT / "docs" / "drift.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace(">", "&gt;")


def _losses(
    ok: list[dict[str, Any]], scr: list[dict[str, Any]], explained: dict[str, str]
) -> list[str]:
    """Every silent failure, false alarm, heal that was not right, and
    Scrapling miss, each with what reading the pages by hand found."""
    lines = ["## The losses", ""]
    silent = [r for r in ok if r["outcome"] == "failed silently"]
    if not silent:
        lines += ["No pair failed silently.", ""]
    for kind in ("failed silently", "false alarm"):
        for r in ok:
            if r["outcome"] == kind:
                lines += [_explain(r, kind, explained), ""]
    for r in ok:
        if r["heal"]["verdict"] in ("wrong", "partly right", "lost"):
            lines += [_explain(r, "heal " + r["heal"]["verdict"], explained), ""]
    missed = [r for r in scr if r["scrapling"]["result"] in ("wrong", "nothing found")]
    if missed:
        lines += ["Scrapling's misses:", ""]
        for r in missed:
            got = r["scrapling"]
            found = f"returned {got['got']!r}" if "got" in got else "returned nothing"
            after = ", after relocating by similarity" if got.get("relocated") else ""
            wanted = got.get("wanted", "the title")
            lines.append(f"- **{r['id']}**: asked for {wanted!r}, {found}{after}.")
        lines.append("")
    return lines


def _explain(r: dict[str, Any], kind: str, explained: dict[str, str]) -> str:
    why = explained.get(r["id"], "Not yet explained by hand.")
    failed = "; ".join(f"`{f}`" for f in r["failed"][:3]) or "none"
    return (
        f"**{r['id']}**, {kind}. {why} The oracle: {r['oracle']}"
        f"{', ' + r['oracle_why'] if r['oracle_why'] else ''}. The checks that"
        f" failed: {failed}."
    )


def _method_and_limits(ok: list[dict[str, Any]]) -> list[str]:
    return [
        "## Method",
        "",
        "- **Pairs.** `discover.py` proposes 25 listing pages on varied sites,",
        "  each with four dates: A and A2 a week apart to learn from, a short B a",
        "  few weeks later, and a long B years later. The archive's nearest",
        "  captures are taken. `make_pairs.py` keeps, by rule, every page where a",
        "  listing was learnt, with each B that is a different capture from A.",
        "  The short pairs mostly test false alarms. The long pairs mostly cross",
        "  redesigns. `pairs.json` is the list of pairs; no archived page is",
        "  committed.",
        *(
            [
                "  The archive kept failing to give "
                + "; ".join(_archive_errors())
                + ", so the pair it belongs to is missing.",
            ]
            if _archive_errors()
            else []
        ),
        "- **The archive.** Captures are read in the `id_` form, one request a",
        "  second, with a user agent naming this benchmark, and cached. A body is",
        "  decoded from the encoding it was served in. When the site redirected,",
        "  the capture is the page the redirect led to, as a scraper would get it.",
        "- **Oracle.** It walks the learnt container path and row kind on B with",
        "  its own code. It then checks that every field every learnt row had is",
        "  in 80% of B's rows. Drift is any of these failing. The oracle judges",
        "  structure only: a template whose markup is intact but whose meaning",
        '  changed is "same" to it.',
        "- **Heal.** Some fields name the item: different in almost every row,",
        "  with letters or an address. An A row and a B row are one item when at",
        "  least half of what names the A row is found anywhere in the B row, so",
        "  a column heal put in the wrong place still matches. For each naming",
        "  field, the healed value on B must equal A's. Digits in text and a rank",
        "  before a title are ignored, and so is a parameter a link gained. The",
        "  verdicts:",
        "  - right: every naming field agrees on 80% of matched items;",
        "  - partly right: one agrees on fewer, or is gone;",
        "  - wrong: one agrees on fewer than half;",
        "  - lost: all of them are gone.",
        "- **Scrapling.** `css(selector, auto_save=True)` is called on A's element",
        "  holding the title of an item still listed on B, with the selector",
        "  Scrapling generates for it. `css(selector, adaptive=True)` is then",
        "  called on B, using Scrapling's own storage. The result is right when",
        "  the element returned has that title and, for a link, that address.",
        "",
        "## Limits",
        "",
        f"- {len(ok)} pairs on 25 sites chosen by hand is a small sample. Most",
        "  sites are news and link aggregators, and no real shop is among them.",
        "- Which group is the listing is read by eye: on all 25 sites the",
        "  learnt listing is the one a person would point at, and nothing here",
        "  measures that beyond these 25.",
        "- The oracle shares the extractor's notion of a path, so a change the",
        "  path cannot express is invisible to both.",
        "- Heal is judged only on items A and B share. Where they share none,",
        "  which is most news pages, heal is not judged at all.",
        "",
        "",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-scrapling", action="store_true")
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    pairs = json.loads((HERE / "pairs.json").read_text(encoding="utf-8"))
    if args.only:
        pairs = [p for p in pairs if any(o in p["id"] for o in args.only)]
    started = time.perf_counter()
    results = []
    for pair in pairs:
        result = score_pair(pair, with_scrapling=not args.no_scrapling)
        results.append(result)
        print(
            f"{pair['id']:52} {result.get('outcome', result.get('error'))}",
            f"| heal {result.get('heal', {}).get('verdict', '')}",
            f"| scrapling {result.get('scrapling', {}).get('result', '')}",
            flush=True,
        )
    seconds = time.perf_counter() - started
    (CACHE / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    if not args.only:
        write_page(results, seconds)


if __name__ == "__main__":
    main()
