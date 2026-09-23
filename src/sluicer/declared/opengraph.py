"""Read the OpenGraph meta tags.

The protocol's own namespace, ``og:``, the vertical namespaces it defines
(``article:``, ``book:``, ``profile:``, ``video:``, ``music:``), and Facebook's
``product:`` type, which its catalogues read. The verticals
are part of the protocol: ``og:type`` names one and the page describes that
type in its namespace, so reading ``og:`` alone reads the label and drops the
statement. Measured on 2026-09-22 across the 359 WCXB pages Sluicer targets,
``article:published_time`` is on 33% of them. ``fb:`` and ``al:`` are
Facebook's and Apple's app plumbing, not statements about the page, and stay
out.

The Twitter card has its own reader, which runs after this one, so OpenGraph
wins a key the two share (``title``, ``description``, ``image:alt``).
OpenGraph describes the document, so it is not in
``sluicer.declared.merge.ABOUT_A_THING``.
"""

from __future__ import annotations

from typing import TypeAlias

from sluicer.declared.meta import meta_tags
from sluicer.document import Document

# As ``sluicer.declared.merge`` spells it; merge imports the readers, so this
# module cannot import it back.
JsonValue: TypeAlias = "str | list[JsonValue] | dict[str, JsonValue]"

_PREFIX = "og:"

# The vertical object types the OpenGraph protocol defines, checked against
# the specification at https://ogp.me/ on 2026-09-22 rather than remembered.
# The page defines each one with its own namespace URI and its own properties
# -- article:published_time, article:author, article:section, article:tag,
# book:author, profile:first_name, video:actor, music:musician -- and this
# tuple is that list and nothing else, so a site's own inventions, fb:app_id
# and al:* are not reported as a vocabulary they do not belong to.
VERTICALS = ("article:", "book:", "profile:", "video:", "music:")

# Facebook's own object type for a thing for sale, not one of ogp.me's: Meta
# documents ``product:price:amount``, ``product:price:currency``,
# ``product:availability``, ``product:brand`` and ``product:retailer_item_id``
# for its catalogues, and about 1,900 files on GitHub write them. Read like a
# vertical, namespace kept, so the key says whose they are.
FACEBOOK_TYPES = ("product:",)

NAMESPACES = VERTICALS + FACEBOOK_TYPES
"""Every namespace read besides ``og:``, whose keys keep their namespace."""


# ogp.me's structured properties: a root, and the properties that describe the
# root declared before them -- og:image:width is the width of the og:image above
# it. Checked against https://ogp.me/#structured and the verticals' own lists.
STRUCTURED = {
    "image": frozenset({"url", "secure_url", "type", "width", "height", "alt"}),
    "video": frozenset({"url", "secure_url", "type", "width", "height"}),
    "audio": frozenset({"url", "secure_url", "type"}),
    "music:song": frozenset({"disc", "track"}),
    "music:album": frozenset({"disc", "track"}),
    "video:actor": frozenset({"role"}),
}
# The properties ogp.me defines as arrays, each tag another value: the media
# roots, the alternate locales, and the verticals' authors, tags, cast, songs
# and albums. Any other property declared twice is a conflict, and the first
# tag wins it, as the protocol says. Checked against https://ogp.me/ on
# 2026-09-23.
ARRAYS = frozenset(
    {
        *STRUCTURED,
        "locale:alternate",
        "music:musician",
        "video:director",
        "video:writer",
        "video:tag",
        "article:author",
        "article:tag",
        "book:author",
        "book:tag",
    }
)
# The most values kept of one property: a page is not a gallery, and a hostile
# one should not make the answer grow with it.
_MOST = 100


def read_opengraph(doc: Document) -> dict[str, str]:
    """Return one value per OpenGraph property: the one the protocol prefers.

    ``og:`` stripped and the verticals' namespace kept -- see
    ``read_opengraph_declared`` for why -- and for a property declared several
    times its first value, since "the first tag (from top to bottom) is given
    preference during conflicts", as ogp.me says. A structured property is the
    first root's: ``image:width`` is the width of the first image, and absent
    when only a later image has one. Every key is one the page wrote: an image
    named only by ``og:image:url`` is ``image:url`` here, not ``image``.
    """
    return _read(doc)[1]


def read_opengraph_declared(doc: Document) -> dict[str, JsonValue]:
    """Return every OpenGraph property the page declares, arrays and structure kept.

    Two spellings of one key, on purpose. ``og:`` is the protocol's own
    namespace and says nothing beyond "this is OpenGraph", so it is stripped:
    ``og:title`` is a title. A vertical is a type, and the type is part of the
    fact, so it is kept: ``article:published_time`` is when *the article* was
    published, which is not the same statement as an undated ``published_time``
    and is not the same key as a ``book:published_time`` would be.
    ``article:author`` and ``book:author`` collapsing onto one ``author`` is
    the defect this avoids.

    A property declared once is its text, as ``read_opengraph`` gives it. One
    of the protocol's arrays (``ARRAYS``: ``article:tag``, ``locale:alternate``,
    ``article:author``...) declared several times with different values is a
    list of them, in order: that is how OpenGraph writes an array, as JSON-LD
    writes one with brackets. Any other property declared twice is a conflict,
    and its first tag wins.
    A root declared several times -- three ``og:image`` -- is a list of
    objects, each the root's ``url`` and the structured properties that
    followed it, as ogp.me's own example reads: its first image 300 by 300, the
    second with no size, the third 1000 tall. A structured property written
    before any root is the first root's, which is what the two cached pages
    that write one ahead of their image mean by it. ``og:image:url`` with no
    ``og:image`` before it starts an image, since the protocol calls the two
    identical, and after one restates it; one address declared twice in a row
    is one image.

    ``og:`` is read first, so on the pathological page that writes both
    ``og:article:tag`` and ``article:tag`` the protocol's own namespace comes
    first, deterministically and not by document order.
    """
    return _read(doc)[0]


def _read(doc: Document) -> tuple[dict[str, JsonValue], dict[str, str]]:
    """Both readings from one scan: every value declared, and the preferred one.

    A root's own value is kept in its group under ``""`` and an ``:url`` under
    ``url``, so the preferred reading can name the tag each came from.
    """
    plain: dict[str, list[str]] = {}
    groups: dict[str, list[dict[str, str]]] = {}
    before: dict[str, dict[str, str]] = {}
    for key, content in _tags(doc):
        root, _, part = key.rpartition(":")
        if key in STRUCTURED:
            _start(groups.setdefault(key, []), content)
        elif part == "url" and root in STRUCTURED and not groups.get(root):
            groups[root] = [{"url": content}]
        elif root in STRUCTURED and part in STRUCTURED[root]:
            declared = groups.get(root)
            into = declared[-1] if declared else before.setdefault(root, {})
            into.setdefault(part, content)
        else:
            values = plain.setdefault(key, [])
            room = _MOST if key in ARRAYS else 1
            if content not in values and len(values) < room:
                values.append(content)
    for root, parts in before.items():
        for part, content in parts.items():
            if root in groups:
                groups[root][0].setdefault(part, content)
    found: dict[str, JsonValue] = {}
    flat: dict[str, str] = {}
    for key, values in plain.items():
        found[key] = values[0] if len(values) == 1 else list(values)
        flat[key] = values[0]
    for root, parts in before.items():
        if root not in groups:
            # The parts of an image the page never names describe nothing we
            # can point at; they are kept as written, as they always were.
            for part, content in parts.items():
                found.setdefault(f"{root}:{part}", content)
                flat.setdefault(f"{root}:{part}", content)
    for root, declared in groups.items():
        for part, content in declared[0].items():
            flat.setdefault(f"{root}:{part}" if part else root, content)
        if len(declared) == 1:
            for part, content in declared[0].items():
                found.setdefault(f"{root}:{part}" if part else root, content)
        else:
            found[root] = [_as_object(group) for group in declared]
    return found, flat


def _start(declared: list[dict[str, str]], address: str) -> None:
    """A root's value starts a new one, unless it names the last one again."""
    if declared and address in (declared[-1].get(""), declared[-1].get("url")):
        declared[-1].setdefault("", address)
    elif len(declared) < _MOST:
        declared.append({"": address})


def _as_object(group: dict[str, str]) -> JsonValue:
    """One root of an array, as ogp.me names its parts: ``url`` and the rest."""
    address = group.get("") or group.get("url")
    parts = {part: text for part, text in group.items() if part not in ("", "url")}
    return {"url": address, **parts} if address else dict(parts)


def _tags(doc: Document) -> list[tuple[str, str]]:
    """Every OpenGraph tag, ``og:`` first and then the namespaces, each in order."""
    protocol: list[tuple[str, str]] = []
    namespaced: list[tuple[str, str]] = []
    for keys, _name, content in meta_tags(doc):
        own = next((key for key in keys if key.startswith(_PREFIX)), None)
        if own is not None:
            protocol.append((own[len(_PREFIX) :], content))
        vertical = next(
            (key for key in keys for prefix in NAMESPACES if key.startswith(prefix)),
            None,
        )
        if vertical is not None:
            namespaced.append((vertical, content))
    return protocol + namespaced
