"""What changed between two readings of a page, question by question.

A price that went from 41.90 to 39.90, an availability that became OutOfStock,
a canonical that moved, a page that started reserving its text and data mining
rights: the summary and the page's declarations of two readings, compared, each
difference naming the source and key of both sides.

A value written differently and meaning the same -- ``41.90`` and ``41.9``,
``2025-06-16`` and ``Jun 16, 2025`` -- is reported as ``rewritten``, not
``changed``: the page said the same thing, in other words.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sluicer.api import Extraction
from sluicer.summary import FIELDS


@dataclass(frozen=True)
class Difference:
    """One question whose answer differs between the two readings.

    ``kind`` is ``changed``, ``rewritten`` (the same normalised value, written
    differently), ``added`` (only the second reading answers it) or
    ``removed``. ``before`` and ``after`` are the answers, and ``source`` the
    reader and key of each, None on the side that does not answer.
    """

    question: str
    kind: str
    before: str | None
    after: str | None
    before_source: str | None
    after_source: str | None


def compare(before: Extraction, after: Extraction) -> list[Difference]:
    """Every summary question, link relation and usage declaration that differs.

    In the order of ``sluicer.summary.FIELDS``, then the links, then the
    rights, so two runs over the same pair give the same list.
    """
    found: list[Difference] = []
    for question in FIELDS:
        old, new = before.summary.get(question), after.summary.get(question)
        if old is None and new is None:
            continue
        old_value = old.value if old else None
        new_value = new.value if new else None
        if old_value == new_value:
            continue
        kind = (
            "added"
            if old is None
            else "removed"
            if new is None
            else "rewritten"
            if _same_meaning(
                question,
                before.normalised.get(question),
                after.normalised.get(question),
            )
            else "changed"
        )
        found.append(
            Difference(
                question,
                kind,
                old_value,
                new_value,
                f"{old.source} {old.key}" if old else None,
                f"{new.source} {new.key}" if new else None,
            )
        )
    found.extend(_declared("links", before.links, after.links))
    found.extend(_declared("rights", before.rights, after.rights))
    return found


def _same_meaning(question: str, old: str | None, new: str | None) -> bool:
    """Whether two normalised answers mean the same: amounts as numbers."""
    if old is None or new is None:
        return False
    if question.startswith("price"):
        return Decimal(old) == Decimal(new)
    return old == new


def _declared(part: str, before: Any, after: Any) -> list[Difference]:
    """The keys of a document-level declaration that differ, as JSON text."""
    found = []
    for key in sorted(set(before) | set(after)):
        old = json.dumps(before[key], sort_keys=True) if key in before else None
        new = json.dumps(after[key], sort_keys=True) if key in after else None
        if old == new:
            continue
        kind = "added" if old is None else "removed" if new is None else "changed"
        # What the response's headers declared came over HTTP, not in markup.
        where = f"{'http' if key == 'http' else 'html'} {part}.{key}"
        found.append(
            Difference(
                f"{part}.{key}",
                kind,
                old,
                new,
                where if old is not None else None,
                where if new is not None else None,
            )
        )
    return found
