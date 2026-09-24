"""The parsed page every reader works from."""

from __future__ import annotations

import codecs
import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass
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
_COMMENT = re.compile(rb"<!--.*?-->", re.DOTALL)
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


def _declared_encoding(data: bytes) -> str | None:
    match = _XML_DECLARATION.match(data)
    if match:
        found = _codec(match.group(1))
        if found is not None:
            return found
    # Comments first: a "<body" written inside one ends nothing.
    head = _COMMENT.sub(b"", data[:_SNIFF_LIMIT])
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
    empty ``<html>`` element, so readers find nothing. ``html`` is kept
    verbatim on the result.
    """
    if isinstance(html, bytes):
        tree = _parse_bytes(html, charset)
        return Document(html=html, tree=tree, url=url, base=_base_of(tree, url))
    try:
        tree = lxml.html.document_fromstring(html, parser=_TEXT_PARSER)
    except lxml.etree.LxmlError:
        # ParserError ("Document is empty"): nothing to read, not an error.
        tree = lxml.html.Element("html")
    except ValueError:
        # "Unicode strings with encoding declaration are not supported": the
        # refusal is about the str, not about the document, so the document
        # gets a second chance as bytes before it is called empty.
        # "replace": a lone surrogate is a character a str can hold and UTF-8
        # cannot, and this function promises never to raise.
        tree = _parse_utf8(html.encode("utf-8", "replace"))
    return Document(html=html, tree=tree, url=url, base=_base_of(tree, url))


def _parse_bytes(data: bytes, charset: str | None = None) -> lxml.html.HtmlElement:
    """Decode ``data`` the way a browser would, then parse it.

    The decision is never left to libxml2: it settles on Latin-1 at the first
    non-ASCII byte it meets, so a curly quote in a ``<title>`` that precedes
    ``<meta charset="utf-8">`` turned every field on the page to mojibake.
    """
    text = data.decode(sniff_encoding(data, charset), errors="replace")
    return _parse_utf8(text.encode("utf-8"))


def _parse_utf8(data: bytes) -> lxml.html.HtmlElement:
    """Parse UTF-8 bytes, telling lxml so, or return an empty ``<html>``."""
    try:
        tree: lxml.html.HtmlElement = lxml.html.document_fromstring(
            data, parser=_UTF8_PARSER
        )
    except (lxml.etree.LxmlError, ValueError):
        tree = lxml.html.Element("html")
    return tree


def base_url(doc: Document) -> str | None:
    """The address relative links on the page resolve against, or None.

    The page's own ``<base href>`` when it has one, itself resolved against the
    page's address, and the page's address otherwise. Worked out once, when the
    page is loaded: asked for every link on a page of thousands, it was most of
    the time a page took.
    """
    return doc.base


def _base_of(tree: lxml.html.HtmlElement, url: str | None) -> str | None:
    for base in tree.xpath("//base[@href]"):
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
    if any(c.isspace() for c in text):
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
