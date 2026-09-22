"""The parsed page every reader works from."""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from urllib.parse import urljoin

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
_META = re.compile(rb"<meta\b([^>]*)>", re.IGNORECASE)
_ATTRIBUTE = re.compile(
    rb"""([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?"""
)
_CHARSET_IN_CONTENT = re.compile(rb"charset\s*=\s*[\"']?\s*([^\s\"';]+)", re.I)
_BODY = re.compile(rb"<body\b", re.IGNORECASE)
# How far a declaration is looked for when the body never starts. Bounded, so
# a page that is all head costs a fixed amount to sniff.
_SNIFF_LIMIT = 64 * 1024


def sniff_encoding(data: bytes) -> str:
    """The encoding a browser would decode ``data`` with, as a codec name.

    The order is the HTML standard's: a byte order mark, then a declaration,
    then the bytes themselves. The declaration is an XML one at the very start
    or a ``<meta charset>`` or ``http-equiv`` anywhere in the head, since real
    pages put it past the standard's first 1,024 bytes and a browser finds it
    there by re-parsing. With no declaration, bytes that are valid UTF-8 are
    UTF-8, and anything else is windows-1252, the web's legacy default.
    """
    for bom, name in _BOMS:
        if data.startswith(bom):
            return name
    declared = _declared_encoding(data)
    if declared is not None:
        return declared
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return "windows-1252"
    return "utf-8"


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
    for meta in _META.finditer(head):
        label = _charset_of(meta.group(1))
        found = _codec(label) if label else None
        if found is not None:
            return found
    return None


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
    """The codec a declared label names, or None when nobody knows it."""
    name = label.decode("ascii", "replace").strip().lower()
    if name in _REFUSED_LABELS:
        return None
    name = _BROWSER_LABELS.get(name, name)
    try:
        return codecs.lookup(name).name
    except LookupError:
        return None


# ``huge_tree``, because libxml2 otherwise stops at 256 levels of nesting and
# drops everything below without a word -- JSON-LD included. Unclosed <div>s
# add up on real pages, and a parser that silently loses the end of a page is
# the failure this package exists not to have.
_TEXT_PARSER = lxml.html.HTMLParser(huge_tree=True)
_UTF8_PARSER = lxml.html.HTMLParser(encoding="utf-8", huge_tree=True)


@dataclass(frozen=True)
class Document:
    """A page that has been parsed once and is read many times."""

    html: str | bytes
    tree: lxml.html.HtmlElement
    url: str | None = None


def load(html: str | bytes, url: str | None = None) -> Document:
    """Parse ``html`` into a Document. This never raises.

    Bytes are preferred when the caller has them, such as a response body
    straight off the wire, because the page's own declaration is still in
    them. They are decoded here the way a browser decodes them -- see
    ``sniff_encoding`` -- and never by libxml2, which commits to Latin-1 at the
    first non-ASCII byte and so misread every UTF-8 page whose ``<title>``
    came before its ``<meta charset>``.

    Broken markup is tolerated by the parser. A ``str`` document carrying an
    XML encoding declaration, as an XHTML page ordinarily does, is refused by
    lxml because a ``str`` is already decoded text and a declaration inside
    it would be a contradiction; it is read as UTF-8 bytes instead, whatever
    the document declares, because the ``str`` arrived here already decoded
    and a declaration that disagrees with it must not be given the chance to
    corrupt the text.

    When lxml cannot parse the document even then -- it is empty, or it
    carries nothing but a doctype, a comment, whitespace with a byte order
    mark, or an XML declaration -- the tree is an empty ``<html>`` element
    instead. Readers then find nothing and the caller truthfully reports that
    the page declares nothing, which is the honest answer for a page that
    declares nothing.

    ``html`` is kept verbatim either way, so what was given is never lost.
    """
    if isinstance(html, bytes):
        return Document(html=html, tree=_parse_bytes(html), url=url)
    try:
        tree = lxml.html.fromstring(html, parser=_TEXT_PARSER)
    except lxml.etree.LxmlError:
        # ParserError ("Document is empty") for a document lxml considers
        # empty. Not a reason to explode in the caller's face.
        tree = lxml.html.Element("html")
    except ValueError:
        # "Unicode strings with encoding declaration are not supported": the
        # refusal is about the str, not about the document, so the document
        # gets a second chance as bytes before it is called empty.
        # "replace": a lone surrogate is a character a str can hold and UTF-8
        # cannot, and this function promises never to raise.
        tree = _parse_utf8(html.encode("utf-8", "replace"))
    return Document(html=html, tree=tree, url=url)


def _parse_bytes(data: bytes) -> lxml.html.HtmlElement:
    """Decode ``data`` the way a browser would, then parse it.

    The decision is never left to libxml2: it settles on Latin-1 at the first
    non-ASCII byte it meets, so a curly quote in a ``<title>`` that precedes
    ``<meta charset="utf-8">`` turned every field on the page to mojibake.
    """
    text = data.decode(sniff_encoding(data), errors="replace")
    return _parse_utf8(text.encode("utf-8"))


def _parse_utf8(data: bytes) -> lxml.html.HtmlElement:
    """Parse UTF-8 bytes, telling lxml so, or return an empty ``<html>``."""
    try:
        tree: lxml.html.HtmlElement = lxml.html.fromstring(data, parser=_UTF8_PARSER)
    except (lxml.etree.LxmlError, ValueError):
        tree = lxml.html.Element("html")
    return tree


def base_url(doc: Document) -> str | None:
    """The address relative links on the page resolve against, or None.

    The page's own ``<base href>`` when it has one, itself resolved against the
    page's address, and the page's address otherwise.
    """
    for base in doc.tree.xpath("//base[@href]"):
        declared = (base.get("href") or "").strip()
        if declared:
            return _join(doc.url, declared) if doc.url else declared
    return doc.url


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
    """
    return _join(base, address) if base else address


def _join(base: str, address: str) -> str:
    try:
        return urljoin(base, address)
    except ValueError:
        return address
