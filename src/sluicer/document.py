"""The parsed page every reader works from."""

from __future__ import annotations

from dataclasses import dataclass

import lxml.etree
import lxml.html


@dataclass(frozen=True)
class Document:
    """A page that has been parsed once and is read many times."""

    html: str | bytes
    tree: lxml.html.HtmlElement
    url: str | None = None


def load(html: str | bytes, url: str | None = None) -> Document:
    """Parse ``html`` into a Document. This never raises.

    Bytes are preferred when the caller has them, such as a response body
    straight off the wire: handed to lxml as bytes, they let the parser
    honour the document's own encoding declaration (a ``<meta charset>`` or
    an XML declaration) instead of guessing, because lxml only reads that
    declaration when it is not told to assume the input is already decoded
    text. Bytes are passed straight through, unmodified, since they need no
    encoding decision made for them.

    Broken markup is tolerated by the parser. A ``str`` document carrying an
    XML encoding declaration, as an XHTML page ordinarily does, is refused by
    lxml because a ``str`` is already decoded text and a declaration inside
    it would be a contradiction; it is read as UTF-8 bytes instead, so a page
    that declares data is never quietly reported as declaring none. That
    retry reads the bytes as UTF-8 whatever the document declares, because
    UTF-8 is what they are: the ``str`` arrived here already decoded, and a
    declaration that disagrees with those bytes must not be given the chance
    to corrupt the text. This retry applies only to the ``str`` path; bytes
    given directly need no such rescue, since they carry no prior decoding
    to contradict.

    When lxml cannot parse the document even then -- it is empty, or it
    carries nothing but a doctype, a comment, whitespace with a byte order
    mark, or an XML declaration -- the tree is an empty ``<html>`` element
    instead. Readers then find nothing and the caller truthfully reports that
    the page declares nothing, which is the honest answer for a page that
    declares nothing.

    ``html`` is kept verbatim either way, so what was given is never lost.
    """
    try:
        tree = lxml.html.fromstring(html)
    except lxml.etree.LxmlError:
        # ParserError ("Document is empty") for a document lxml considers
        # empty. Not a reason to explode in the caller's face.
        tree = lxml.html.Element("html")
    except ValueError:
        # "Unicode strings with encoding declaration are not supported": the
        # refusal is about the str, not about the document, so the document
        # gets a second chance as bytes before it is called empty.
        #
        # Bytes get no such retry, and the guard is not decoration. The retry
        # re-encodes the document, which only a str can be asked to do; a
        # bytes document arriving here would reach `.encode` and leave as an
        # AttributeError, out of a function whose first line promises it never
        # raises. Today lxml refuses bytes with an LxmlError and this branch
        # only ever sees strings, so the guard costs one comparison and closes
        # the hole the paragraph above already said was closed.
        if isinstance(html, bytes):
            tree = lxml.html.Element("html")
        else:
            try:
                tree = lxml.html.fromstring(
                    html.encode("utf-8"),
                    parser=lxml.html.HTMLParser(encoding="utf-8"),
                )
            except (lxml.etree.LxmlError, ValueError):
                tree = lxml.html.Element("html")
    return Document(html=html, tree=tree, url=url)
