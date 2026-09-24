"""Fetch the WCXB test split at one pinned commit, and list its pages.

WCXB -- the Web Content Extraction Benchmark by Murrough Foley,
https://github.com/Murrough-Foley/web-content-extraction-benchmark -- is
published under CC-BY-4.0. It is downloaded into ``bench/cache/`` and never
committed here. The commit is pinned so every run scores the same pages
against the same labels; moving it is a change to the scoreboard and says so
in the diff.
"""

from __future__ import annotations

import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

REPOSITORY = "Murrough-Foley/web-content-extraction-benchmark"
COMMIT = "c039d5ee9f5a3a984a0e167e63aacd04e76e78a9"
ARCHIVE = f"https://codeload.github.com/{REPOSITORY}/tar.gz/{COMMIT}"

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CORPUS = CACHE / "wcxb"
PAGES = CACHE / "pages.json"

# What the scoreboard reads from the archive. The dev split is not scored.
_WANTED = ("test/", "metadata.json", "LICENSE", "README.md")


def ensure() -> Path:
    """The page list for the pinned test split, downloading it the first time."""
    marker = CORPUS / "COMMIT"
    if (
        PAGES.exists()
        and marker.exists()
        and marker.read_text(encoding="utf-8").strip() == COMMIT
    ):
        return PAGES
    _download()
    marker.write_text(COMMIT + "\n", encoding="utf-8")
    PAGES.write_text(json.dumps(_pages(), indent=1) + "\n", encoding="utf-8")
    return PAGES


def _download() -> None:
    if CORPUS.exists():
        shutil.rmtree(CORPUS)
    CORPUS.mkdir(parents=True)
    archive = CACHE / f"wcxb-{COMMIT[:12]}.tar.gz"
    if not archive.exists():
        print(f"downloading WCXB at {COMMIT[:12]} (about 150 MB, once)", flush=True)
        partial = archive.with_suffix(".part")
        with urllib.request.urlopen(ARCHIVE) as response, partial.open("wb") as out:
            shutil.copyfileobj(response, out)
        partial.rename(archive)
    prefix = f"web-content-extraction-benchmark-{COMMIT}/"
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.name.startswith(prefix) or not member.isfile():
                continue
            relative = member.name[len(prefix) :]
            if not relative.startswith(_WANTED):
                continue
            target = CORPUS / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is not None:
                target.write_bytes(source.read())


def _pages() -> list[dict[str, str | None]]:
    """Every test page: its id, address, type, HTML path and three labels."""
    metadata = json.loads((CORPUS / "metadata.json").read_text(encoding="utf-8"))
    pages = []
    for file_id, info in sorted(metadata["files"].items()):
        if info.get("split") != "test":
            continue
        truth = json.loads(
            (CORPUS / "test" / "ground-truth" / f"{file_id}.json").read_text(
                encoding="utf-8"
            )
        )
        labels = truth.get("ground_truth") or {}
        pages.append(
            {
                "id": file_id,
                "url": truth.get("url"),
                "page_type": info.get("page_type"),
                "path": f"wcxb/test/html/{file_id}.html.gz",
                "title": labels.get("title"),
                "author": labels.get("author"),
                "date": labels.get("publish_date"),
            }
        )
    return pages


if __name__ == "__main__":
    print(ensure())
