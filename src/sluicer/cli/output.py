"""Lines written for a person, shared by the commands that print a report."""

from __future__ import annotations

import json
from typing import Any


def _kept_line(hit: Any) -> str:
    """How a page came from the cache, said for a person."""
    if hit.revalidated:
        return "kept, and the site said it has not changed (304)"
    return f"kept {hit.age:.0f} s ago, within --max-age: the site was not asked"


def _moment(stamp: str) -> str:
    """An archive's ``YYYYMMDDhhmmss``, as far as it goes, written as ISO."""
    parts = [stamp[:4], stamp[4:6], stamp[6:8]]
    day = "-".join(part for part in parts if part)
    time_ = ":".join(p for p in (stamp[8:10], stamp[10:12], stamp[12:14]) if p)
    return f"{day} {time_}" if time_ else day


def _brief(value: object, limit: int = 72) -> str:
    """A value on one line: text as it is, a nested value as compact JSON."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
