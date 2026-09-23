"""Every reader, in the order of precedence, in one place.

Adding a vocabulary is one entry here: the name every field it produces carries
as its ``source``, the function that reads a document, and whether it
describes the things on a page -- and folds with them by type -- or the page
itself, and fills the first record. The order is the precedence: an earlier
reader's field wins, a later one only fills gaps. Why it is this order is in
``docs/design-notes.md``.

The summary asks the document-level vocabularies by name (``og:title``,
``twitter:title``), so a new one answers summary questions only once
``sluicer.summary`` is taught what it says.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sluicer.declared.dublincore import read_dublincore
from sluicer.declared.htmlmeta import read_htmlmeta
from sluicer.declared.jsonld import read_jsonld
from sluicer.declared.microdata import read_microdata
from sluicer.declared.microformats import read_microformats
from sluicer.declared.opengraph import read_opengraph
from sluicer.declared.rdfa import read_rdfa
from sluicer.declared.twitter import read_twitter
from sluicer.document import Document


@dataclass(frozen=True)
class Reader:
    """One vocabulary sluicer reads.

    ``read`` returns a list of items, each a mapping with an optional
    ``@type``, for a reader ``about_things``; and one mapping of names to text
    for a reader about the document. ``optional`` names the ``extract``
    argument that turns the reader on, when it is off by default.
    """

    name: str
    read: Callable[[Document], Any]
    about_things: bool
    optional: str | None = None


READERS: tuple[Reader, ...] = (
    Reader("jsonld", read_jsonld, about_things=True),
    Reader("microdata", read_microdata, about_things=True),
    # Off by default: it needs sluicer[microformats], and not calling it is what
    # keeps mf2py unimported on a base install.
    Reader(
        "microformats", read_microformats, about_things=True, optional="microformats"
    ),
    Reader("rdfa", read_rdfa, about_things=True),
    Reader("dublincore", read_dublincore, about_things=False),
    Reader("opengraph", read_opengraph, about_things=False),
    Reader("twitter", read_twitter, about_things=False),
    Reader("html", read_htmlmeta, about_things=False),
)

BY_NAME = {reader.name: reader for reader in READERS}
