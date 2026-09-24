"""Turn the discovery log into ``pairs.json`` by fixed rules, not by hand.

A candidate that learnt a listing gives up to two pairs: a short one, B a few
weeks after A, and a long one, B years after. A pair is dropped when B is the
same capture as A or A2 (the archive had nothing nearer), or when B is missing.
Which pairs cross a real change is not decided here: the oracle in ``run.py``
decides that from the pages themselves.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    pairs = []
    for line in (HERE / "discover.log").read_text(encoding="utf-8").splitlines():
        if not line.startswith("{"):
            continue
        row = json.loads(line)
        if row["verdict"] != "listing":
            continue
        stamps = row["stamps"]
        learnt = sorted({s for s in (stamps["A"], stamps["A2"]) if s})
        for kind, why in (
            ("short", "B a few weeks after A: the template usually unchanged"),
            ("long", "B years after A: across a redesign when the site had one"),
        ):
            b = stamps[f"B_{kind}"]
            if not b or b in learnt:
                continue
            pairs.append(
                {
                    "id": f"{_slug(row['url'])}-{kind}",
                    "url": row["url"],
                    "learn": learnt,
                    "b": b,
                    "kind": kind,
                    "why": why,
                    # Where the site redirected a capture, which is what a
                    # scraper asking for the address would have read.
                    "redirected": {
                        role: address
                        for role, address in row.get("landed", {}).items()
                        if role in ("A", "A2", f"B_{kind}")
                    },
                }
            )
    (HERE / "pairs.json").write_text(
        json.dumps(pairs, indent=2) + "\n", encoding="utf-8"
    )
    print(len(pairs), "pairs")


def _slug(url: str) -> str:
    body = url.split("://", 1)[1].rstrip("/")
    return "".join(c if c.isalnum() else "-" for c in body).strip("-")[:48]


if __name__ == "__main__":
    main()
