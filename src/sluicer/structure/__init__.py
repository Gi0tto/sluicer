"""Read pages that declare nothing, by what their markup repeats.

``induce`` is the one call; ``shape``, ``groups`` and ``records`` are its three
steps. The package is not named ``induce`` because the function exported from
``sluicer`` would shadow it and break ``import sluicer.induce.records``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lxml.html import HtmlElement

from sluicer.declared.merge import Record
from sluicer.document import Document, load
from sluicer.structure.groups import repeating_groups
from sluicer.structure.records import holds_a_fact, records_from

if TYPE_CHECKING:
    from sluicer.selectors import Page

__all__ = ["induce"]


def induce(
    doc: Document | str | bytes | Page, minimum: int = 3, *, url: str | None = None
) -> list[Record]:
    """Return one record per row of the page's most promising repeated shape.

    Args:
        doc: the page: its HTML, as ``extract`` takes it -- bytes are best --
            or a page ``sluicer.parse`` made, or a parsed ``Document``.
        minimum: the fewest repetitions that count as a listing.
        url: for HTML, the address the page came from, as for ``extract``.

    Returns:
        Records whose fields all have ``source="induced"`` and are named by
        where they sit (``div.meta>span.sku``), or ``[]``. Groups are tried in
        ranked order and the first that yields records wins: a group whose
        members hold bare text, in no element of their own, has nothing to name
        a field after and yields none.

    Raises:
        TypeError: ``doc`` is none of these.
    """
    doc = _document(doc, url)
    # Groups nest, so what each element holds is found once for all of them.
    below: dict[HtmlElement, tuple[bool, bool]] = {}
    for group in repeating_groups(doc.tree, minimum=minimum):
        if not holds_a_fact(group, below):
            continue
        records = records_from(group)
        if records:
            return records
    return []


def _document(doc: Document | str | bytes | Page, url: str | None) -> Document:
    """``doc`` as the ``Document`` induction reads. The public ``induce``
    took only a ``Document``, which nothing public makes: HTML, or a page
    ``sluicer.parse`` gave, raised AttributeError."""
    from sluicer.selectors import Page

    if isinstance(doc, Document):
        return doc
    if isinstance(doc, str | bytes):
        return load(doc, url=url)
    if isinstance(doc, Page):
        return doc._doc
    raise TypeError(
        "induce reads a page's HTML, as str or bytes, or a page sluicer.parse "
        f"made, not {type(doc).__name__}"
    )
