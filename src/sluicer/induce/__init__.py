"""Reading the pages that declare nothing, by what their markup repeats."""

from __future__ import annotations

from sluicer.declared.merge import Record
from sluicer.document import Document
from sluicer.induce.groups import repeating_groups
from sluicer.induce.records import records_from

__all__ = ["induce"]


def induce(doc: Document, minimum: int = 3) -> list[Record]:
    """Return the records the page's most promising repeated shape describes."""
    groups = repeating_groups(doc.tree, minimum=minimum)
    return records_from(groups[0]) if groups else []
