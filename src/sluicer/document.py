"""The parsed page every reader works from."""

from __future__ import annotations

import codecs
import functools
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urljoin

import lxml.etree
import lxml.html

# The labels the HTML standard reads differently from Python's codec of the
# same name. A page saying iso-8859-1 means windows-1252 in every browser, and
# a <meta> claiming UTF-16 cannot be true of bytes that were ASCII enough to
# read it, so the standard reads it as UTF-8.
_BROWSER_LABELS = {
    "ascii": "windows-1252",
    "us-ascii": "windows-1252",
    "iso-8859-1": "windows-1252",
    "iso8859-1": "windows-1252",
    "latin1": "windows-1252",
    "latin-1": "windows-1252",
    "l1": "windows-1252",
    "x-user-defined": "windows-1252",
    "utf-16": "utf-8",
    "utf-16le": "utf-8",
    "utf-16be": "utf-8",
    # The CJK and Turkish/Thai labels browsers decode with the superset.
    "gb2312": "gb18030",
    "gbk": "gb18030",
    "x-gbk": "gb18030",
    "shift_jis": "cp932",
    "shift-jis": "cp932",
    "sjis": "cp932",
    "x-sjis": "cp932",
    "windows-31j": "cp932",
    "euc-kr": "cp949",
    "ks_c_5601-1987": "cp949",
    "big5": "big5hkscs",
    "iso-8859-9": "cp1254",
    "latin5": "cp1254",
    "iso-8859-11": "cp874",
    "tis-620": "cp874",
}
# Labels a browser refuses to decode with, however the page spells them.
_REFUSED_LABELS = frozenset({"utf-7", "utf7", "unicode-1-1-utf-7"})
_BOMS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_XML_DECLARATION = re.compile(rb"^\s*<\?xml[^>]*encoding\s*=\s*[\"']([^\"']+)")
_META = re.compile(rb"<meta\b", re.IGNORECASE)
_TAG_END = re.compile(rb"[>\"']")
_ATTRIBUTE = re.compile(
    rb"""([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?"""
)
_CHARSET_IN_CONTENT = re.compile(rb"charset\s*=\s*[\"']?\s*([^\s\"';]+)", re.I)
_BODY = re.compile(rb"<body\b", re.IGNORECASE)
# How far a declaration is looked for when the body never starts. Bounded, so
# a page that is all head costs a fixed amount to sniff.
_SNIFF_LIMIT = 64 * 1024
# What the URL standard strips from an address's ends: C0 controls and space.
_C0_OR_SPACE = "".join(chr(code) for code in range(0x21))
# ``str.isspace``'s characters, as one search in C: asked character by character
# in Python of every address on a page, it was a tenth of the time a page took.
# The two agree on every code point.
_ANY_SPACE = re.compile(r"\s")


def sniff_encoding(data: bytes, transport: str | None = None) -> str:
    """The encoding ``data`` is in, as a codec name.

    The order is the HTML standard's: a byte order mark, then the charset the
    response was sent with (``transport``, from its ``Content-Type``, when the
    bytes came over HTTP), then a declaration, then the bytes themselves. The
    declaration is an XML one at the very start or a ``<meta charset>`` or
    ``http-equiv`` anywhere in the head, since real pages put it past the
    standard's first 1,024 bytes and a browser finds it there by re-parsing.
    With no declaration, anything that is not UTF-8 is windows-1252, the web's
    legacy default.

    One departure from a browser: bytes that are valid UTF-8 and hold a
    character outside ASCII are UTF-8, whatever the header or the page
    declares. A page another tool saved or re-encoded keeps its old
    ``<meta charset=GB2312>`` over UTF-8 bytes, and read as declared it is
    mojibake; text in a legacy encoding that happens to be valid UTF-8 is
    text that already is mojibake. Measured on 1,427 pages as their servers
    sent them, none changes; on fundus's 263 fixtures, the three re-encoded
    ones read right.
    """
    for bom, name in _BOMS:
        if data.startswith(bom):
            return name
    sent = _codec(transport.encode("ascii", "replace")) if transport else None
    found = sent or _declared_encoding(data)
    if found is not None and (found == "utf-8" or data.isascii() or not _utf8(data)):
        return found
    if found is None and not _utf8(data):
        return "windows-1252"
    return "utf-8"


def _utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _without_comments(data: bytes) -> bytes:
    """``data`` without its ``<!-- -->`` comments, read to their first end.

    A comment never closed stays, and so does every one after it, which
    cannot close either. The pattern that did this asked the rest of the head
    for an end from every ``<!--``: 64 KiB of them took four seconds.
    """
    kept: list[bytes] = []
    copied = at = 0
    while (at := data.find(b"<!--", at)) != -1:
        close = data.find(b"-->", at + 4)
        if close == -1:
            break
        kept.append(data[copied:at])
        copied = at = close + 3
    kept.append(data[copied:])
    return b"".join(kept)


def _declared_encoding(data: bytes) -> str | None:
    match = _XML_DECLARATION.match(data)
    if match:
        found = _codec(match.group(1))
        if found is not None:
            return found
    # Comments first: a "<body" written inside one ends nothing.
    head = _without_comments(data[:_SNIFF_LIMIT])
    body = _BODY.search(head)
    if body:
        head = head[: body.start()]
    for attributes in _meta_attributes(head):
        label = _charset_of(attributes)
        found = _codec(label) if label else None
        if found is not None:
            return found
    return None


def _meta_attributes(head: bytes) -> Iterator[bytes]:
    """The attributes of each ``<meta>`` in ``head``, read the way the prescan is.

    A quoted value is read whole, so ``<meta content="a>b" charset="koi8-r">``
    declares KOI8-R; ending the tag at the first ``>`` lost every declaration
    written after a value holding one. And the reading only moves forward: a
    tag that never closes holds the rest of the head, as it does for the
    standard, instead of being tried again from every ``<meta`` inside it,
    which took seconds on a head of nothing but unclosed tags.
    """
    at = 0
    while opening := _META.search(head, at):
        start = at = opening.end()
        while True:
            stop = _TAG_END.search(head, at)
            if stop is None:
                return
            if stop.group() == b">":
                yield head[start : stop.start()]
                at = stop.end()
                break
            closing = head.find(stop.group(), stop.end())
            if closing < 0:
                return
            at = closing + 1


def _charset_of(attributes: bytes) -> bytes | None:
    """The label one ``<meta>`` declares, in either of its two spellings."""
    found: dict[bytes, bytes] = {}
    for match in _ATTRIBUTE.finditer(attributes):
        value = next((group for group in match.groups()[1:] if group), b"")
        found.setdefault(match.group(1).lower(), value)
    if b"charset" in found:
        return found[b"charset"]
    if found.get(b"http-equiv", b"").strip().lower() == b"content-type":
        declared = _CHARSET_IN_CONTENT.search(found.get(b"content", b""))
        if declared:
            return declared.group(1)
    return None


def _codec(label: bytes) -> str | None:
    """The codec a declared label names, or None when nobody knows it.

    Python's registry answers to more names than a browser does, and some of
    what it holds is not a text encoding at all: ``hex``, ``base64`` and
    ``zlib`` refuse to decode a page, ``idna`` refuses to decode one with
    ``replace``, and a label holding a NUL is refused by the lookup itself.
    Each of those was a traceback from a page that declared it.
    """
    name = label.decode("ascii", "replace").strip().lower()
    if name in _REFUSED_LABELS:
        return None
    name = _BROWSER_LABELS.get(name, name)
    try:
        codec = codecs.lookup(name).name
    except (LookupError, ValueError):
        return None
    return codec if _reads_ascii_as_ascii(codec) else None


# The bytes a declaration is written in. ESC is left out: ISO-2022-JP, which
# every browser reads, spends it on switching character sets.
_ASCII_TEXT = (0x09, 0x0A, 0x0D, *range(0x20, 0x7F))


@functools.cache
def _reads_ascii_as_ascii(codec: str) -> bool:
    """Whether ``codec`` decodes every printable ASCII byte as itself.

    A page had to be ASCII enough for its declaration to be read, which is the
    standard's reason for reading a UTF-16 label as UTF-8; a codec that reads
    those bytes as anything else -- EBCDIC, UTF-32, or not text at all -- cannot
    be what the page is written in, and is not believed.
    """
    try:
        return all(
            bytes([byte]).decode(codec, "replace") == chr(byte) for byte in _ASCII_TEXT
        )
    except (LookupError, ValueError):
        return False


# ``huge_tree``, because libxml2 otherwise stops at 256 levels of nesting and
# silently drops everything below, JSON-LD included; unclosed <div>s add up on
# real pages.
_TEXT_PARSER = lxml.html.HTMLParser(huge_tree=True)
_UTF8_PARSER = lxml.html.HTMLParser(encoding="utf-8", huge_tree=True)


@dataclass(frozen=True)
class Document:
    """A page that has been parsed once and is read many times."""

    html: str | bytes
    tree: lxml.html.HtmlElement
    url: str | None = None
    base: str | None = None
    """What relative links resolve against, worked out once by ``load``."""
    memo: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    """What several readers scan the page for, scanned once: the ``<meta>``
    tags, read by five of them. The tree is never changed after ``load``, so
    a scan stays true of it; what is kept here is never handed out to be
    changed."""


METAS = "//meta"
"""Every ``<meta>``: the readers keyed on a meta tag's name each filter it."""
RELATED = "//@rel"
"""Every element with a ``rel``: the ``<link>``, ``<a>`` and ``<area>`` the
link relations and the licences are read from, each reader keeping those
with an ``href``."""


def carrying(tree: lxml.html.HtmlElement, path: str) -> list[lxml.html.HtmlElement]:
    """The elements carrying the attributes ``path`` selects -- ``//@itemscope``,
    ``//meta/@name`` -- in document order.

    The attribute axis finds them two to three times faster than a predicate
    tested on every element (``//*[@itemscope]``); each element carries one
    attribute of a name, so each comes once. The parent is taken here and not
    in XPath: asked as ``//@itemscope/..``, libxml2 merges each parent into
    the node-set with a duplicate check against all it holds, the square of
    their number: 1.9 s for forty thousand items, 4.8 s for eighty.
    """
    return [attribute.getparent() for attribute in tree.xpath(path)]


def scan(doc: Document, path: str) -> tuple[lxml.html.HtmlElement, ...]:
    """The elements ``path`` finds in the whole page, in document order,
    found once per page whichever reader asks first.

    Five readers asked the page for its ``<meta>`` tags and two for its
    elements with a ``rel``, each walking the whole tree for its own filter
    of the same list; each now filters the one list, which comes out the same
    elements in the same order. A tuple, so no reader can change another's.
    A path whose last step is an attribute (``RELATED``) gives the elements
    carrying it, as ``carrying`` finds them.
    """
    key = f"scan {path}"
    found: tuple[lxml.html.HtmlElement, ...] | None = doc.memo.get(key)
    if found is None:
        found = doc.memo[key] = tuple(
            carrying(doc.tree, path)
            if "@" in path.rpartition("/")[2]
            else doc.tree.xpath(path)
        )
    return found


def load(
    html: str | bytes, url: str | None = None, charset: str | None = None
) -> Document:
    """Parse ``html`` into a ``Document``. Never raises.

    Args:
        html: the page. Prefer bytes when you have them, such as a response
            body: the page's own charset declaration is still in them, and
            they are decoded the way a browser decodes them (see
            ``sniff_encoding``), never by libxml2, which commits to Latin-1 at
            the first non-ASCII byte.
        url: the address the page came from, used to resolve its links.
        charset: the charset the response was sent with, from its
            ``Content-Type``; for bytes, it comes before the page's own
            declaration, as the HTML standard orders them.

    Always parsed as a whole document, whatever its start: ``lxml.html``'s
    ``fromstring`` renames the ``<body>`` of what it takes for a fragment -- no
    head, and neither ``<html>`` nor a doctype first -- to a ``<div>``, and
    every place on such a page went through a div the page never had.

    A ``str`` carrying an XML encoding declaration (ordinary XHTML) is refused
    by lxml, since a decoded string cannot also declare an encoding; it is
    parsed as UTF-8 whatever it declares. A document lxml cannot parse at all
    -- empty, only a doctype, a comment or an XML declaration -- becomes an
    empty ``<html>`` element, so readers find nothing. Its newlines are read
    as the HTML standard reads them, CR LF and a lone CR as LF, on every
    libxml2. ``html`` is kept verbatim on the result.
    """
    if isinstance(html, bytes):
        tree = _parse_bytes(html, charset)
        return Document(html=html, tree=tree, url=url, base=_base_of(tree, url))
    text = _newlines(html)
    try:
        # As UTF-8 bytes: libxml2 builds the same tree from them as from the
        # str, and faster than from a str lxml hands it as UCS-2 or UCS-4.
        data = text.encode("utf-8")
    except UnicodeEncodeError:
        # A lone surrogate, which a str can hold and UTF-8 cannot: the str
        # is parsed as it is, as it always was.
        pass
    else:
        tree = _parse_utf8(data)
        return Document(html=html, tree=tree, url=url, base=_base_of(tree, url))
    try:
        tree = lxml.html.document_fromstring(text, parser=_TEXT_PARSER)
    except lxml.etree.LxmlError:
        # ParserError ("Document is empty"): nothing to read, not an error.
        tree = lxml.html.Element("html")
    except ValueError:
        # "Unicode strings with encoding declaration are not supported": the
        # refusal is about the str, not about the document, so the document
        # gets a second chance as bytes before it is called empty.
        # "replace": a lone surrogate is a character a str can hold and UTF-8
        # cannot, and this function promises never to raise.
        tree = _parse_utf8(text.encode("utf-8", "replace"))
    return Document(html=html, tree=tree, url=url, base=_base_of(tree, url))


# The page this thread parsed last to judge it, for the extraction that
# follows to read: (the page, its address, its charset, the Document).
_KEPT = threading.local()

KEEP_AT_MOST = 1_000_000
"""The largest page, in bytes or characters, ``load_and_keep`` keeps parsed.

A parsed page weighs about ten times its HTML (a 10 MB page, about 100 MB),
and a page is kept per thread until it is extracted: sixteen threads that
fetched a 10 MB page each and extracted none held 1.4 to 1.9 GB, where 0.9.1
held 0.25 to 0.3 GB. A larger page is parsed again by its extraction, which
costs it the time the keeping saves and nothing more; 96% of WCXB's
development pages are smaller."""


def load_and_keep(
    html: str | bytes, url: str | None = None, charset: str | None = None
) -> Document:
    """``load``, keeping the Document as the page this thread parsed last.

    A fetch parses the page it is handed to judge it, and its caller then
    extracts the very same page: ``load_kept`` hands the kept Document to
    that extraction instead of parsing the page a second time, which was a
    third of what a fetched page cost. One page is kept per thread, until
    it is taken, another replaces it or ``let_go`` is called; a page larger
    than ``KEEP_AT_MOST`` is not kept, and lets go of the one before.
    """
    doc = _kept(html, url, charset)
    if doc is None:
        doc = load(html, url=url, charset=charset)
        small = len(html) <= KEEP_AT_MOST
        _KEPT.page = (html, url, _charset_key(html, charset), doc) if small else None
    return doc


def let_go() -> None:
    """Let go of the page this thread kept, if any.

    Called where a fetched page is not extracted: an MCP tool's call ending,
    a crawl's page read or dropped, a page turned into markdown. Kept past
    them, a parsed page stayed in memory for as long as its thread lived.
    """
    _KEPT.page = None


def load_kept(
    html: str | bytes, url: str | None = None, charset: str | None = None
) -> Document:
    """``load``, or the Document ``load_and_keep`` kept for this very page.

    The very page: the same object -- a fetch's ``html`` handed on as it
    came -- from the same address, and for bytes with the same charset, so
    the Document is the one ``load`` would give; it has only been read,
    and a tree is never changed after ``load``. Whatever is kept is let go
    here, so an extraction leaves nothing behind.
    """
    doc = _kept(html, url, charset)
    _KEPT.page = None
    return doc if doc is not None else load(html, url=url, charset=charset)


def _kept(html: str | bytes, url: str | None, charset: str | None) -> Document | None:
    kept = getattr(_KEPT, "page", None)
    if (
        kept is not None
        and kept[0] is html
        and kept[1] == url
        and kept[2] == _charset_key(html, charset)
    ):
        document: Document = kept[3]
        return document
    return None


def _charset_key(html: str | bytes, charset: str | None) -> str | None:
    """The charset a Document depends on: only bytes are decoded by it."""
    return charset if isinstance(html, bytes) else None


def _parse_bytes(data: bytes, charset: str | None = None) -> lxml.html.HtmlElement:
    """Decode ``data`` the way a browser would, then parse it.

    The decision is never left to libxml2: it settles on Latin-1 at the first
    non-ASCII byte it meets, so a curly quote in a ``<title>`` that precedes
    ``<meta charset="utf-8">`` turned every field on the page to mojibake.
    """
    encoding = sniff_encoding(data, charset)
    if encoding == "utf-8" and (data.isascii() or _utf8(data)):
        # Valid UTF-8 decodes and encodes back to itself, and a CR or an LF
        # byte in it is only ever that character: its newlines are read on
        # the bytes, which lxml is then handed as they are. The round trip
        # through a str was a tenth of what loading a page cost, and twice
        # the page in memory.
        return _parse_utf8(_newline_bytes(data))
    text = data.decode(encoding, errors="replace")
    return _parse_utf8(_newlines(text).encode("utf-8"))


def _newline_bytes(data: bytes) -> bytes:
    """``_newlines`` of UTF-8 bytes, on the bytes."""
    if b"\r" not in data:
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _newlines(text: str) -> str:
    """``text`` with CR LF and a lone CR as LF, as the HTML standard reads a page.

    The standard normalises a page's newlines before tokenising it, and
    libxml2 does too from 2.14, lxml 6's, but not in 2.12, lxml 5.3's, which
    this package also runs on: done here, the same page gives the same answer
    on both, where a description kept its CR LF on one and not the other. A
    reference to a CR, ``&#13;``, is not a newline written, and stays one.
    """
    if "\r" not in text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_utf8(data: bytes) -> lxml.html.HtmlElement:
    """Parse UTF-8 bytes, telling lxml so, or return an empty ``<html>``."""
    try:
        tree: lxml.html.HtmlElement = lxml.html.document_fromstring(
            data, parser=_UTF8_PARSER
        )
    except (lxml.etree.LxmlError, ValueError):
        tree = lxml.html.Element("html")
    return tree


_ADDRESS_ALONE = re.compile(rb"\s*https?://\S+\s*", re.IGNORECASE)


def an_address_alone(data: str | bytes) -> str | None:
    """The address ``data`` is, when it is an http(s) URL and nothing else,
    or None: what a caller who meant to fetch a page hands a function that
    reads one. Read as a page, it is a text that declares nothing."""
    raw = data.encode("utf-8", "replace") if isinstance(data, str) else data
    if len(raw) > 8192 or not _ADDRESS_ALONE.fullmatch(raw):
        return None
    return raw.strip().decode("utf-8", "replace")


def base_url(doc: Document) -> str | None:
    """The address relative links on the page resolve against, or None.

    The page's own ``<base href>`` when it has one, itself resolved against the
    page's address, and the page's address otherwise. Worked out once, when the
    page is loaded: asked for every link on a page of thousands, it was most of
    the time a page took.
    """
    return doc.base


def _base_of(tree: lxml.html.HtmlElement, url: str | None) -> str | None:
    for base in carrying(tree, "//base/@href"):
        declared = trimmed(base.get("href"))
        if declared:
            return _join(url, declared) if url else declared
    return url


def absolute(doc: Document, address: str) -> str:
    """``address`` resolved against the page, or as written with nothing to resolve
    it against."""
    base = base_url(doc)
    return _join(base, address) if base else address


def join(base: str | None, address: str) -> str:
    """``address`` resolved against ``base``, or as written when it cannot be.

    An unfilled template writes ``https://[domain]/p``, which is not a URL and
    which ``urljoin`` refuses with a ``ValueError``; a page is read whatever
    its links look like, so the link is kept the way the page wrote it.
    Either way the address is first cleaned as ``clean_address`` says.
    """
    return _join(base, address) if base else clean_address(address)


def trimmed(value: str | None) -> str:
    """An attribute's address with its ends trimmed as the URL standard trims
    them: controls and ASCII spaces, nothing else.

    ``str.strip`` also takes a no-break space or an ideographic space, which
    a browser keeps as part of the address and percent-encodes, so a
    ``<link href="\u00a0x">`` would have pointed somewhere else here.
    """
    return (value or "").strip(_C0_OR_SPACE)


def clean_address(address: str) -> str:
    """``address`` as the URL standard reads it out of an attribute.

    Controls and spaces at its ends are dropped, and every tab and newline
    inside it, so ``/p``, a carriage return and ``?`` is ``/p?``; any other
    white space left is
    percent-encoded, as a browser encodes it, so an address is never
    answered with a space in it or around it. Nothing else is encoded: an
    address written in Unicode stays readable.
    """
    text = address.strip(_C0_OR_SPACE)
    text = text.replace("\t", "").replace("\n", "").replace("\r", "")
    if _ANY_SPACE.search(text):
        text = "".join(quote(c, safe="") if c.isspace() else c for c in text)
    return text


def _join(base: str, address: str) -> str:
    address = clean_address(address)
    try:
        return _without_empty_parts(urljoin(base, address))
    except ValueError:
        return address


def _without_empty_parts(url: str) -> str:
    """``url`` without an empty query or an empty fragment, on every Python.

    Python 3.14's ``urljoin`` keeps a bare ``?`` or ``#`` that earlier ones
    drop, so ``/p?`` would answer ``https://site/p?`` on one and
    ``https://site/p`` on the other: the same page, two answers. Both mean
    the same address; the one without is kept.
    """
    head, hash_sign, fragment = url.partition("#")
    if hash_sign and not fragment:
        url = head
    elif hash_sign:
        return _without_empty_parts(head) + "#" + fragment
    if url.endswith("?") and url.index("?") == len(url) - 1:
        return url[:-1]
    return url
