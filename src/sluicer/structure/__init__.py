"""Read pages that declare nothing, by what their markup repeats.

``induce`` is the one call; ``shape``, ``groups`` and ``records`` are its three
steps. The package is not named ``induce`` because the function exported from
``sluicer`` would shadow it and break ``import sluicer.induce.records``.
"""

from __future__ import annotations

from lxml.html import HtmlElement

from sluicer.declared.merge import Record
from sluicer.document import Document
from sluicer.structure.groups import repeating_groups
from sluicer.structure.records import holds_a_fact, records_from

__all__ = ["induce"]


def induce(doc: Document, minimum: int = 3) -> list[Record]:
    """Return one record per row of the page's most promising repeated shape.

    Args:
        doc: the parsed page.
        minimum: the fewest repetitions that count as a listing.

    Returns:
        Records whose fields all have ``source="induced"`` and are named by
        where they sit (``div.meta>span.sku``), or ``[]``. Groups are tried in
        ranked order and the first that yields records wins: a group whose
        members hold bare text, in no element of their own, has nothing to name
        a field after and yields none.
    """
    # Groups nest, so what each element holds is found once for all of them.
    below: dict[HtmlElement, tuple[bool, bool]] = {}
    for group in repeating_groups(doc.tree, minimum=minimum):
        if not holds_a_fact(group, below):
            continue
        records = records_from(group)
        if records:
            return records
    return []
