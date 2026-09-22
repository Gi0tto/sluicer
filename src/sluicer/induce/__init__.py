"""Reading the pages that declare nothing, by what their markup repeats."""

from __future__ import annotations

from sluicer.declared.merge import Record
from sluicer.document import Document
from sluicer.induce.groups import repeating_groups
from sluicer.induce.records import records_from

__all__ = ["induce"]


def induce(doc: Document, minimum: int = 3) -> list[Record]:
    """Return the records the page's most promising repeated shape describes.

    The ranking is a guess about which repeated shape is the content, and a
    guess can be right about the shape and still yield nothing: a group whose
    members hold their text directly, in no element of their own, has no part
    to name a field after, and comes back empty. Reading only the first group
    would then report a page with a visible list as inducing nothing at all, so
    each group is tried in turn and the first one that yields records is the
    answer.
    """
    for group in repeating_groups(doc.tree, minimum=minimum):
        records = records_from(group)
        if records:
            return records
    return []
