"""Prove a change to the code keeps every answer byte-identical, and time it.

    .venv/bin/python bench/golden.py record OUT.json   # every page's digests
    .venv/bin/python bench/golden.py check OUT.json    # 0 differences, or exit 1
    .venv/bin/python bench/golden.py time              # ms per page, this tree
    .venv/bin/python bench/golden.py time --src ../other/src   # another tree

A speed change is only worth having when nothing a caller can see moves. This
reads every page the benchmarks keep under ``bench/cache/`` -- never writing
there -- and a digest of what each public reading of it gives:

- ``extract`` as the ladder calls it (address, no headers), with the page's
  ``Content-Type`` when the corpus kept it, ``visible=True`` and
  ``induce=True``; each digest covers ``repr()`` and the JSON the command line
  prints;
- the ladder's verdict, "declares a thing", from the full extraction;
- ``to_markdown`` when the ``markdown`` extra is installed;
- a fetch through the real ladder, with rungs that hand the page back, and the
  extraction a caller makes of it;
- ``read_warc`` and ``extract_warc`` of a WARC file built from the pages that
  kept their headers;
- ``compile_extractor`` and ``run_extractor`` (and ``heal``) on the drift
  benchmark's cached captures, and on the first pages of every SWDE site,
  which are also the corpus's ``str`` pages.

``record`` writes the digests; ``check`` reads them again and names every
page and reading that changed. ``time`` times the three extractions and the
fetch path, one page at a time, the best of a few rounds each, and prints the
median and the 95th percentile; ``--src`` times another checkout's ``src`` in
a process of its own, so two trees can be timed turn about on a busy machine.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
ROOT = HERE.parent
SWDE_PAGES_PER_SITE = 8
SWDE_LEARN = 3


@dataclass(frozen=True)
class Page:
    """One cached page: a name unique in the corpus, its body, its address,
    and its ``Content-Type`` when the corpus kept it."""

    name: str
    body: bytes | str
    url: str | None
    content_type: str | None = None


def _gz(path: Path) -> bytes:
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _pages() -> Iterator[Page]:
    """Every cached page, in a fixed order."""
    for kind in ("wayback", "commoncrawl"):
        folder = CACHE / "realweb" / "bodies" / kind
        for body in sorted(folder.glob("*.html.gz")):
            meta = _json(body.with_name(body.name.replace(".html.gz", ".json")))
            yield Page(
                f"realweb/{kind}/{body.name}",
                _gz(body),
                meta.get("served_url"),
                meta.get("content_type"),
            )
    for split in ("dev", "test"):
        folder = CACHE / "wcxb" / split
        for body in sorted((folder / "html").glob("*.html.gz")):
            stem = body.name.split(".")[0]
            truth = folder / "ground-truth" / f"{stem}.json"
            url = _json(truth).get("url") if truth.exists() else None
            yield Page(f"wcxb/{split}/{body.name}", _gz(body), url)
    for body in sorted((CACHE / "evaldata" / "pages").glob("*.html.gz")):
        yield Page(
            f"evaldata/{body.name}", _gz(body), f"https://evaldata.example/{body.name}"
        )
    for body in sorted(CACHE.glob("products/*/dataset/html/*.html.gz")):
        yield Page(
            f"products/{body.name}", _gz(body), f"https://products.example/{body.name}"
        )
    for body in sorted(CACHE.glob("fundus/*/tests/resources/parser/test_data/*/*")):
        if body.name.endswith((".html.gz", ".html")):
            name = f"{body.parent.name}/{body.name}"
            yield Page(f"fundus/{name}", _gz(body), f"https://fundus.example/{name}")
    for body in sorted((CACHE / "drift").glob("*.html")):
        meta_path = body.with_suffix(".json")
        meta = _json(meta_path) if meta_path.exists() else {}
        yield Page(f"drift/{body.name}", body.read_bytes(), meta.get("landed"))
    for body in sorted((CACHE / "drift" / "anansi").glob("*.html")):
        yield Page(
            f"drift/anansi/{body.name}",
            body.read_bytes(),
            f"https://anansi.example/{body.name}",
        )
    for group in ("rdfa", "w3c-jsonld", "demo"):
        for body in sorted((CACHE / group).rglob("*.html")):
            name = str(body.relative_to(CACHE))
            yield Page(name, body.read_bytes(), f"https://{group}.example/{name}")
    for body in sorted((ROOT / "tests" / "fixtures").rglob("*.html")):
        name = str(body.relative_to(ROOT))
        yield Page(name, body.read_bytes(), f"https://fixtures.example/{name}")
    for site, pages in _swde_sites():
        for key in sorted(pages)[:SWDE_PAGES_PER_SITE]:
            yield Page(
                f"swde/{site}/{key}", pages[key], f"https://{site}.example/{key}"
            )


def _swde_sites() -> Iterator[tuple[str, dict[str, str]]]:
    for bundle in sorted((CACHE / "swde" / "bundles").glob("*.json.gz")):
        pages: dict[str, str] = json.loads(gzip.decompress(bundle.read_bytes()))
        site = bundle.name.split(".")[0]
        yield site, {key: pages[key] for key in sorted(pages)[:SWDE_PAGES_PER_SITE]}


def _digest(*parts: object) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else str(part).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:20]


def _extraction(result: Any) -> str:
    """What a caller can see of an ``Extraction``: its ``repr`` and the JSON
    the command line prints."""
    return _digest(
        repr(result),
        json.dumps(asdict(result), indent=2, ensure_ascii=False, default=repr),
    )


def _failure(error: BaseException) -> str:
    return _digest(type(error).__name__, str(error))


def _guarded(read: Callable[[], str]) -> str:
    try:
        return read()
    except Exception as error:  # noqa: BLE001 -- an answer that must not change
        return "raised:" + _failure(error)


def _headers(page: Page) -> dict[str, str] | None:
    return {"content-type": page.content_type} if page.content_type else None


def _fetched(page: Page) -> Any:
    """``page`` fetched through the real ladder, two rungs handing it back,
    and read the way a caller reads it: the verdict each rung got is in the
    climbs."""
    from sluicer.api import extract
    from sluicer.declared.headers import charset
    from sluicer.document import sniff_encoding
    from sluicer.fetch.ladder import fetch
    from sluicer.fetch.result import Fetched

    url = page.url or "https://golden.example/page"
    body = page.body
    headers = _headers(page) or {}
    if isinstance(body, bytes):
        html = body.decode(sniff_encoding(body, charset(headers)), errors="replace")
    else:
        html = body

    def rung(name: str) -> Callable[[str], Fetched]:
        def answer(asked: str) -> Fetched:
            return Fetched(
                url=asked, html=html, status=200, rung=name, headers=dict(headers)
            )

        return answer

    fetched = fetch(
        url,
        rungs=[("http", rung("http")), ("browser", rung("browser"))],
        obey_robots=False,
    )
    return fetched, extract(fetched.html, url=fetched.url, headers=fetched.headers)


def read_page(page: Page, markdown: bool) -> dict[str, str]:
    """Every reading of one page, each as a digest."""
    from sluicer.api import _declared_about_its_things, extract

    headers = _headers(page)
    out: dict[str, str] = {}
    plain = extract(page.body, url=page.url)
    out["extract"] = _extraction(plain)
    out["found"] = str(_declared_about_its_things(plain.records))
    if headers:
        out["extract+headers"] = _extraction(
            extract(page.body, url=page.url, headers=headers)
        )
    out["visible"] = _extraction(extract(page.body, url=page.url, visible=True))
    out["induce"] = _extraction(extract(page.body, url=page.url, induce=True))
    if markdown:
        from sluicer.markdown import to_markdown

        out["markdown"] = _guarded(lambda: _digest(to_markdown(page.body, page.url)))

    def fetched() -> str:
        got, extraction = _fetched(page)
        climbs = [(c.from_rung, c.to_rung, c.reason) for c in got.climbs]
        return _digest(got.rung, got.url, climbs, _extraction(extraction))

    out["fetch"] = _guarded(fetched)
    return out


def _warc_record(page: Page, number: int) -> bytes:
    body = page.body if isinstance(page.body, bytes) else page.body.encode()
    http = (
        b"HTTP/1.1 200 OK\r\n"
        + f"Content-Type: {page.content_type}\r\n".encode()
        + f"Content-Length: {len(body)}\r\n\r\n".encode()
        + body
    )
    head = (
        "WARC/1.0\r\n"
        "WARC-Type: response\r\n"
        f"WARC-Record-ID: <urn:uuid:00000000-0000-0000-0000-{number:012d}>\r\n"
        "WARC-Date: 2026-01-01T00:00:00Z\r\n"
        f"WARC-Target-URI: {page.url}\r\n"
        "Content-Type: application/http; msgtype=response\r\n"
        f"Content-Length: {len(http)}\r\n\r\n"
    ).encode()
    return gzip.compress(head + http + b"\r\n\r\n", mtime=0)


def read_warcs(pages: list[Page]) -> dict[str, dict[str, str]]:
    """``read_warc`` and ``extract_warc`` over one WARC of every page that
    kept its headers."""
    from sluicer.warc import Skipped, extract_warc, read_warc

    kept = [page for page in pages if page.content_type and page.url]
    data = b"".join(_warc_record(page, n) for n, page in enumerate(kept))
    out: dict[str, dict[str, str]] = {}
    skipped = Skipped()
    for n, (warc_page, extraction) in enumerate(
        extract_warc(io.BytesIO(data), skipped=skipped)
    ):
        out[f"warc/{n}"] = {
            "page": _digest(repr(warc_page)),
            "extract_warc": _extraction(extraction),
        }
    out["warc/read"] = {
        "pages": _digest([repr(p) for p in read_warc(io.BytesIO(data))]),
        "skipped": _digest(repr(skipped)),
    }
    return out


def _drift_snapshot(url: str, when: str) -> tuple[bytes, str] | None:
    """A drift capture from the cache, never from the archive."""
    key = hashlib.sha256(f"2:{url}@{when}".encode()).hexdigest()[:24]
    meta_path = CACHE / "drift" / f"{key}.json"
    if not meta_path.exists():
        return None
    meta = _json(meta_path)
    if meta.get("missing"):
        return None
    return (CACHE / "drift" / f"{key}.html").read_bytes(), meta["landed"]


def compile_one(task: tuple[str, list[Any], list[Any], bool | None]) -> dict[str, str]:
    """Learn an extractor from ``learn`` and replay it on ``replay``, and heal
    it on them, each answer a digest."""
    from sluicer.extractor import compile_extractor, heal, run_extractor

    _name, learn, replay, listing = task
    out: dict[str, str] = {}
    try:
        extractor = compile_extractor([tuple(page) for page in learn], listing=listing)
    except Exception as error:  # noqa: BLE001 -- refusing is an answer too
        return {"compile": "raised:" + _failure(error)}
    out["compile"] = _digest(extractor.to_json())
    for n, (html, url) in enumerate(replay):
        out[f"run/{n}"] = _guarded(
            lambda html=html, url=url: _digest(
                repr(run_extractor(extractor, html, url))
            )
        )
    out["heal"] = _guarded(
        lambda: _digest(repr(heal(extractor, [tuple(page) for page in replay])))
    )
    return out


def _compile_tasks() -> Iterator[tuple[str, list[Any], list[Any], bool | None]]:
    for pair in _json(HERE / "drift" / "pairs.json"):
        learn = [_drift_snapshot(pair["url"], when) for when in pair["learn"]]
        b = _drift_snapshot(pair["url"], pair["b"])
        if b is None or not all(learn):
            continue
        yield f"drift/{pair['id']}", learn, [b, learn[0]], True
    for site, pages in _swde_sites():
        keys = sorted(pages)
        pairs = [(pages[k], f"https://{site}.example/{k}") for k in keys]
        yield f"swde/{site}", pairs[:SWDE_LEARN], pairs[SWDE_LEARN:], None


def _read_one(job: tuple[Page, bool]) -> tuple[str, dict[str, str]]:
    page, markdown = job
    return page.name, read_page(page, markdown)


def _compile_named(
    task: tuple[str, list[Any], list[Any], bool | None],
) -> tuple[str, dict[str, str]]:
    return "compile/" + task[0], compile_one(task)


def digests(workers: int) -> dict[str, dict[str, str]]:
    try:
        import trafilatura  # noqa: F401

        markdown = True
    except ImportError:
        markdown = False
    pages = list(_pages())
    names = [page.name for page in pages]
    if len(set(names)) != len(names):
        raise SystemExit("two pages share a name")
    found: dict[str, dict[str, str]] = {}
    with ProcessPoolExecutor(workers) as pool:
        for name, answer in pool.map(
            _read_one, [(page, markdown) for page in pages], chunksize=8
        ):
            found[name] = answer
        for name, answer in pool.map(_compile_named, list(_compile_tasks())):
            found[name] = answer
    found.update(read_warcs(pages))
    return found


def _compare(old: dict[str, dict[str, str]], new: dict[str, dict[str, str]]) -> int:
    changed = 0
    for name in sorted(set(old) | set(new)):
        a, b = old.get(name), new.get(name)
        if a == b:
            continue
        changed += 1
        if a is None or b is None:
            print(f"{name}: {'new' if a is None else 'gone'}")
            continue
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                print(f"{name}: {key} {a.get(key)} -> {b.get(key)}")
    return changed


# -- timing ------------------------------------------------------------------


def _timed_pages() -> list[Page]:
    """The pages timed: every real page served with its scripts (realweb,
    products, fundus), and the first 200 of WCXB's and of evaldata's."""
    picked: list[Page] = []
    counts: dict[str, int] = {}
    for page in _pages():
        group = page.name.split("/")[0]
        if group in ("realweb", "products", "fundus"):
            picked.append(page)
        elif group in ("wcxb", "evaldata") and counts.get(group, 0) < 200:
            counts[group] = counts.get(group, 0) + 1
            picked.append(page)
    return picked


def _fetched_or_refused(page: Page) -> object:
    try:
        return _fetched(page)
    except Exception as error:  # noqa: BLE001 -- a challenge page, refused
        return error


def _time_here(rounds: int, modes: list[str] | None) -> dict[str, list[float]]:
    from sluicer.api import extract

    pages = _timed_pages()
    calls: dict[str, Callable[[Page], object]] = {
        "extract": lambda p: extract(p.body, url=p.url),
        "visible": lambda p: extract(p.body, url=p.url, visible=True),
        "induce": lambda p: extract(p.body, url=p.url, induce=True),
        "fetch+extract": _fetched_or_refused,
    }
    times: dict[str, list[float]] = {}
    for mode, call in calls.items():
        if modes and mode not in modes:
            continue
        for page in pages[:20]:  # warm-up
            call(page)
        best = [float("inf")] * len(pages)
        for _ in range(rounds):
            for n, page in enumerate(pages):
                started = time.perf_counter()
                call(page)
                best[n] = min(best[n], time.perf_counter() - started)
        times[mode] = [t * 1000 for t in best]
    return times


def _summary(times: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    out = {}
    for mode, values in times.items():
        ordered = sorted(values)
        out[mode] = {
            "median": round(statistics.median(ordered), 3),
            "p95": round(ordered[int(0.95 * (len(ordered) - 1))], 3),
            "total_s": round(sum(ordered) / 1000, 3),
            "pages": len(ordered),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("record", "check"):
        one = sub.add_parser(command)
        one.add_argument("path", type=Path)
        one.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    timing = sub.add_parser("time")
    timing.add_argument("--src", type=Path, default=ROOT / "src")
    timing.add_argument("--rounds", type=int, default=3)
    timing.add_argument(
        "--modes", help="comma-separated: extract,visible,induce,fetch+extract"
    )
    timing.add_argument("--json", action="store_true")
    timing.add_argument("--here", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.command == "time" and not args.here:
        # Its own process, with its own tree's code first on the path.
        env = {**os.environ, "PYTHONPATH": str(args.src.resolve())}
        command = [sys.executable, __file__, "time", "--here", "--json"]
        command += ["--rounds", str(args.rounds)]
        command += ["--modes", args.modes] if args.modes else []
        answer = subprocess.run(
            command, env=env, check=True, stdout=subprocess.PIPE, text=True
        )
        result = json.loads(answer.stdout)
        print(json.dumps(result, indent=1) if args.json else _table(result))
        return
    if args.command == "time":
        import sluicer

        modes = args.modes.split(",") if args.modes else None
        summary = _summary(_time_here(args.rounds, modes))
        summary["src"] = {"path": str(Path(sluicer.__file__).parent)}  # type: ignore[dict-item]
        print(json.dumps(summary))
        return
    started = time.monotonic()
    found = digests(args.workers)
    seconds = time.monotonic() - started
    if args.command == "record":
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(json.dumps(found, indent=0, sort_keys=True))
        readings = sum(len(v) for v in found.values())
        print(f"recorded {len(found)} entries, {readings} readings, {seconds:.0f} s")
        return
    old = json.loads(args.path.read_text())
    changed = _compare(old, found)
    readings = sum(len(v) for v in found.values())
    print(
        f"{changed} of {len(found)} entries differ ({readings} readings, "
        f"{seconds:.0f} s)"
    )
    raise SystemExit(1 if changed else 0)


def _table(result: dict[str, Any]) -> str:
    lines = [f"src: {result.pop('src')['path']}"]
    for mode, row in result.items():
        lines.append(
            f"{mode:14} median {row['median']:7.3f} ms  p95 {row['p95']:7.3f} ms  "
            f"total {row['total_s']:7.3f} s  ({row['pages']} pages)"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
